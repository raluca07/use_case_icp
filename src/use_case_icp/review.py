from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from typing import Any, Iterable, Mapping

from .etiq_graph import fence_untrusted
from .records import (
    BoundaryHealth,
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EvidenceReviewUnit,
    ReviewDecision,
    ReviewDecisionStatus,
    ReviewReceipt,
    ReviewSection,
    TrustAnnotation,
    TrustLevel,
    new_id,
    stable_hash,
)


def _fenced_if_document(node: Any, content: Any) -> Any:
    """Fence free text handed to the reviewer. Structured artifacts are not fenced."""
    if getattr(node, "artifact_kind", None) == "document" and isinstance(content, str):
        return fence_untrusted(content)
    return content


def review_node_payload(node: Any) -> dict[str, Any]:
    artifact_content = node.artifact_content
    encoded_artifact = (
        json.dumps(artifact_content, ensure_ascii=False, default=str)
        if artifact_content is not None
        else ""
    )
    return {
        "node_ref": node.node_ref,
        "raw_id": node.raw_id,
        "names": node.names,
        "line_no": node.line_no,
        "state_type": node.state_type,
        "value_type": node.value_type,
        "func_stack": node.func_stack,
        "source": node.source,
        "scope_type": node.scope_type,
        "value_preview": node.value_preview,
        "preview_truncated": node.preview_truncated,
        "artifact_kind": node.artifact_kind,
        "artifact_size": node.artifact_size,
        "artifact_available": artifact_content is not None,
        "artifact_truncated": node.artifact_truncated,
        "artifact_value": (
            _fenced_if_document(node, artifact_content)
            if len(encoded_artifact) <= 4_000
            else None
        ),
        "raw_metadata_hash": stable_hash(node.raw_metadata),
    }


def review_relationship_payload(relationship: Any) -> dict[str, Any]:
    return {
        "relationship_ref": relationship.relationship_ref,
        "source_ref": relationship.source_ref,
        "target_ref": relationship.target_ref,
        "relationship_type": relationship.relationship_type,
        "direction": relationship.direction,
        "raw_metadata_hash": stable_hash(relationship.raw_metadata),
    }


def frame_name(frame: str) -> str:
    value = str(frame)
    name, separator, suffix = value.rpartition(",")
    if (
        separator
        and not suffix.startswith("#")
        and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", suffix)
    ):
        return name.strip()
    return value.strip()


def _canonical_stack(stack: Iterable[str]) -> tuple[str, ...]:
    return tuple(frame_name(str(frame)) for frame in stack)


def _prefixes(stack: Iterable[str]) -> list[tuple[str, ...]]:
    items = _canonical_stack(stack)
    return [items[:index] for index in range(1, len(items) + 1)]


def _starts_with(stack: Iterable[str], prefix: tuple[str, ...]) -> bool:
    values = _canonical_stack(stack)
    expected = _canonical_stack(prefix)
    return len(values) >= len(expected) and values[: len(expected)] == expected


def _boundary_relationships(
    prefix: tuple[str, ...],
    snapshot: EtiqEvidenceSnapshot,
    node_by_ref: Mapping[str, Any],
) -> list[str]:
    found: list[str] = []
    for relationship in snapshot.relationships:
        source = node_by_ref.get(relationship.source_ref)
        target = node_by_ref.get(relationship.target_ref)
        if source is None or target is None:
            continue
        if _starts_with(source.func_stack, prefix) != _starts_with(target.func_stack, prefix):
            found.append(relationship.relationship_ref)
    return found


def _order_units(
    units: list[EvidenceReviewUnit],
    snapshot: EtiqEvidenceSnapshot,
    node_by_ref: Mapping[str, Any],
) -> list[EvidenceReviewUnit]:
    unit_by_id = {unit.unit_id: unit for unit in units}

    def owner(node_ref: str) -> str | None:
        node = node_by_ref.get(node_ref)
        if node is None:
            return None
        matches = [
            unit for unit in units if _starts_with(node.func_stack, tuple(unit.func_stack_prefix))
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: len(item.func_stack_prefix)).unit_id

    edges: set[tuple[str, str]] = set()
    bridge_producers: dict[str, set[str]] = defaultdict(set)
    bridge_consumers: dict[str, set[str]] = defaultdict(set)
    for relationship in snapshot.relationships:
        source_owner = owner(relationship.source_ref)
        target_owner = owner(relationship.target_ref)
        if source_owner and target_owner and source_owner != target_owner:
            edges.add((source_owner, target_owner))
        elif source_owner and not target_owner:
            bridge_producers[relationship.target_ref].add(source_owner)
        elif target_owner and not source_owner:
            bridge_consumers[relationship.source_ref].add(target_owner)
    for bridge_ref in bridge_producers.keys() & bridge_consumers.keys():
        for source_owner in bridge_producers[bridge_ref]:
            for target_owner in bridge_consumers[bridge_ref]:
                if source_owner != target_owner:
                    edges.add((source_owner, target_owner))

    downstream: dict[str, set[str]] = defaultdict(set)
    indegree = {unit.unit_id: 0 for unit in units}
    for source, target in edges:
        if target in downstream[source]:
            continue
        downstream[source].add(target)
        indegree[target] += 1
        unit_by_id[source].downstream_unit_ids.append(target)
        unit_by_id[target].upstream_unit_ids.append(source)

    capture_index = {
        node.node_ref: index
        for index, node in enumerate(snapshot.nodes)
    }

    def sort_key(unit_id: str) -> tuple[int, tuple[str, ...]]:
        unit = unit_by_id[unit_id]
        ordinal = min((capture_index[ref] for ref in unit.node_refs), default=10**9)
        return ordinal, tuple(unit.func_stack_prefix)

    ready = sorted((item for item, degree in indegree.items() if degree == 0), key=sort_key)
    ordered_ids: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered_ids.append(current)
        for target in sorted(downstream.get(current, set()), key=sort_key):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=sort_key)

    if len(ordered_ids) != len(units):
        remaining = [unit_id for unit_id in unit_by_id if unit_id not in ordered_ids]
        ordered_ids.extend(sorted(remaining, key=sort_key))
        ordering_source = "captured_flow_cycle"
        degraded = True
    elif edges or len(units) <= 1:
        ordering_source = "captured_flow"
        degraded = False
    else:
        ordering_source = "captured_ordinal_fallback"
        degraded = True

    for unit in units:
        unit.upstream_unit_ids.sort()
        unit.downstream_unit_ids.sort()
        unit.boundary_health.ordering_source = ordering_source
        if degraded:
            unit.boundary_health.degraded = True
            unit.boundary_health.findings.append("observed_ordering_degraded")
    return [unit_by_id[unit_id] for unit_id in ordered_ids]


def build_review_units(
    snapshot: EtiqEvidenceSnapshot,
    *,
    declared_boundaries: list[dict[str, Any]] | None = None,
    max_descendant_frames: int = 128,
    max_nodes: int = 256,
    max_relationships: int = 512,
    max_nesting_depth: int = 8,
) -> list[EvidenceReviewUnit]:
    if min(max_descendant_frames, max_nodes, max_relationships, max_nesting_depth) < 1:
        raise ValueError("review-unit limits must be positive")
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    observed_prefixes: set[tuple[str, ...]] = set()
    for node in snapshot.nodes:
        observed_prefixes.update(_prefixes(node.func_stack))
    if not observed_prefixes:
        return []

    children_by_prefix: dict[tuple[str, ...], list[tuple[str, ...]]] = defaultdict(list)
    for prefix in observed_prefixes:
        if len(prefix) > 1:
            children_by_prefix[prefix[:-1]].append(prefix)
    for children in children_by_prefix.values():
        children.sort()

    metrics: dict[tuple[str, ...], dict[str, Any]] = {}

    def prefix_metrics(prefix: tuple[str, ...]) -> dict[str, Any]:
        cached = metrics.get(prefix)
        if cached is not None:
            return cached
        node_refs = [node.node_ref for node in snapshot.nodes if _starts_with(node.func_stack, prefix)]
        relationship_refs: list[str] = []
        for relationship in snapshot.relationships:
            source = node_by_ref.get(relationship.source_ref)
            target = node_by_ref.get(relationship.target_ref)
            if source is None or target is None:
                continue
            if _starts_with(source.func_stack, prefix) or _starts_with(target.func_stack, prefix):
                relationship_refs.append(relationship.relationship_ref)
        descendants = [
            item
            for item in observed_prefixes
            if len(item) > len(prefix) and item[: len(prefix)] == prefix
        ]
        direct_children = children_by_prefix.get(prefix, [])
        boundary_children = [
            child
            for child in direct_children
            if _boundary_relationships(child, snapshot, node_by_ref)
        ]
        cached = {
            "node_refs": node_refs,
            "relationship_refs": sorted(set(relationship_refs)),
            "descendants": sorted(descendants, key=lambda item: (len(item), item)),
            "direct_children": direct_children,
            "boundary_children": boundary_children,
        }
        metrics[prefix] = cached
        return cached

    limits = {
        "max_descendant_frames": max_descendant_frames,
        "max_nodes": max_nodes,
        "max_relationships": max_relationships,
        "max_nesting_depth": max_nesting_depth,
    }

    def exceeds_limits(prefix: tuple[str, ...]) -> bool:
        current = prefix_metrics(prefix)
        return (
            len(current["descendants"]) > max_descendant_frames
            or len(current["node_refs"]) > max_nodes
            or len(current["relationship_refs"]) > max_relationships
        )

    selected: list[tuple[tuple[str, ...], str]] = []

    def select_prefix(
        prefix: tuple[str, ...],
        *,
        unwrap_container: bool,
        relative_depth: int,
        origin: str,
    ) -> None:
        current = prefix_metrics(prefix)
        boundary_children = current["boundary_children"]
        can_descend = bool(boundary_children) and relative_depth < max_nesting_depth
        should_descend = can_descend and (unwrap_container or exceeds_limits(prefix))
        if should_descend:
            child_origin = "container_child" if unwrap_container else "parent_exceeded_limits"
            for child in boundary_children:
                select_prefix(
                    child,
                    unwrap_container=unwrap_container and len(boundary_children) == 1,
                    relative_depth=relative_depth + 1,
                    origin=child_origin,
                )
            return
        if exceeds_limits(prefix):
            terminal = "limit_reached_without_splittable_children"
        elif boundary_children:
            terminal = "within_limits"
        else:
            terminal = "leaf_or_no_child_boundaries"
        selected.append((prefix, f"{origin}:{terminal}"))

    declared_names = {
        str(item.get("function_name") or "").strip()
        for item in (declared_boundaries or [])
        if str(item.get("function_name") or "").strip()
    }
    missing_declared_names: set[str] = set()
    if declared_names:
        candidates = sorted(
            (
                prefix
                for prefix in observed_prefixes
                if frame_name(prefix[-1]) in declared_names
            ),
            key=lambda item: (len(item), item),
        )
        selected_candidates = [
            candidate
            for candidate in candidates
            if not any(
                len(parent) < len(candidate)
                and candidate[: len(parent)] == parent
                for parent in candidates
            )
        ]
        missing_declared_names = declared_names - {
            frame_name(prefix[-1]) for prefix in candidates
        }
        for candidate in selected_candidates:
            select_prefix(
                candidate,
                unwrap_container=False,
                relative_depth=0,
                origin="declared_boundary",
            )
    else:
        roots = sorted(prefix for prefix in observed_prefixes if len(prefix) == 1)
        for root in roots:
            select_prefix(
                root,
                unwrap_container=len(roots) == 1,
                relative_depth=0,
                origin="depth_one",
            )

    units: list[EvidenceReviewUnit] = []
    for prefix, selection_reason in selected:
        current = prefix_metrics(prefix)
        node_refs = current["node_refs"]
        input_refs: list[str] = []
        output_refs: list[str] = []
        relationship_refs: list[str] = current["relationship_refs"]
        for relationship in snapshot.relationships:
            source = node_by_ref.get(relationship.source_ref)
            target = node_by_ref.get(relationship.target_ref)
            if source is None or target is None:
                continue
            source_inside = _starts_with(source.func_stack, prefix)
            target_inside = _starts_with(target.func_stack, prefix)
            if not source_inside and target_inside:
                input_refs.append(relationship.relationship_ref)
            elif source_inside and not target_inside:
                output_refs.append(relationship.relationship_ref)
        helpers = [list(item) for item in current["descendants"]]
        findings: list[str] = []
        if not input_refs and not output_refs:
            findings.append("observed_stage_without_boundaries")
        findings.extend(
            f"declared_boundary_not_observed:{name}"
            for name in sorted(missing_declared_names)
        )
        invocation_frames = {
            node.func_stack[len(prefix) - 1]
            for node in snapshot.nodes
            if _starts_with(node.func_stack, prefix)
        }
        health = BoundaryHealth(
            grouping_mode=(
                "declared_boundary"
                if selection_reason.startswith("declared_boundary")
                else ("depth_one" if len(prefix) == 1 else "adaptive_nested")
            ),
            input_count=len(set(input_refs)),
            output_count=len(set(output_refs)),
            invocation_count=max(1, len(invocation_frames)),
            findings=findings,
            degraded=bool(findings or snapshot.scan_errors),
        )
        units.append(
            EvidenceReviewUnit(
                unit_id=f"unit:{stable_hash([snapshot.run_id, prefix])[:24]}",
                run_id=snapshot.run_id,
                function_name=frame_name(prefix[-1]),
                func_stack_prefix=list(prefix),
                node_refs=node_refs,
                relationship_refs=sorted(set(relationship_refs)),
                input_relationship_refs=sorted(set(input_refs)),
                output_relationship_refs=sorted(set(output_refs)),
                helper_prefixes=helpers,
                boundary_health=health,
                nesting_summary={
                    "selection_reason": selection_reason,
                    "selected_depth": len(prefix),
                    "direct_child_count": len(current["direct_children"]),
                    "boundary_child_count": len(current["boundary_children"]),
                    "descendant_frame_count": len(current["descendants"]),
                    "node_count": len(node_refs),
                    "relationship_count": len(relationship_refs),
                    "limits": limits,
                },
            )
        )
    return _order_units(units, snapshot, node_by_ref)


def build_review_sections(
    units: list[EvidenceReviewUnit],
    *,
    section_size: int = 8,
    overlap: int = 1,
    max_nodes: int = 300,
    max_relationships: int = 512,
    max_helpers: int = 128,
) -> list[ReviewSection]:
    if min(section_size, max_nodes, max_relationships, max_helpers) < 1 or overlap < 0:
        raise ValueError("invalid section bounds")

    def footprint(selected_units: Iterable[EvidenceReviewUnit]) -> tuple[int, int, int]:
        node_refs: set[str] = set()
        relationship_refs: set[str] = set()
        helper_prefixes: set[tuple[str, ...]] = set()
        for unit in selected_units:
            node_refs.update(unit.node_refs)
            relationship_refs.update(unit.relationship_refs)
            helper_prefixes.update(tuple(prefix) for prefix in unit.helper_prefixes)
        return len(node_refs), len(relationship_refs), len(helper_prefixes)

    def within_budget(
        selected_units: list[EvidenceReviewUnit],
        *,
        enforce_unit_count: bool = True,
    ) -> bool:
        node_count, relationship_count, helper_count = footprint(selected_units)
        return (
            (not enforce_unit_count or len(selected_units) <= section_size)
            and node_count <= max_nodes
            and relationship_count <= max_relationships
            and helper_count <= max_helpers
        )

    groups: list[list[EvidenceReviewUnit]] = []
    current_group: list[EvidenceReviewUnit] = []
    for unit in units:
        if not within_budget([unit]):
            summary = unit.nesting_summary
            raise ValueError(
                "review unit exceeds section evidence limits after nesting selection: "
                f"{unit.function_name} nodes={len(unit.node_refs)} "
                f"relationships={len(unit.relationship_refs)} "
                f"helpers={len(unit.helper_prefixes)} reason={summary.get('selection_reason')}"
            )
        candidate = [*current_group, unit]
        if current_group and not within_budget(candidate):
            groups.append(current_group)
            current_group = [unit]
        else:
            current_group = candidate
    if current_group:
        groups.append(current_group)

    sections: list[ReviewSection] = []
    unit_index = {unit.unit_id: index for index, unit in enumerate(units)}
    for index, assigned_units in enumerate(groups, start=1):
        start = unit_index[assigned_units[0].unit_id]
        end = unit_index[assigned_units[-1].unit_id] + 1
        context_units = list(assigned_units)
        excluded_context: list[str] = []
        upstream_candidates = list(reversed(units[max(0, start - overlap):start]))
        downstream_candidates = list(units[end:min(len(units), end + overlap)])
        for candidate in upstream_candidates:
            if within_budget([candidate, *context_units], enforce_unit_count=False):
                context_units.insert(0, candidate)
            else:
                excluded_context.append(candidate.unit_id)
        for candidate in downstream_candidates:
            if within_budget([*context_units, candidate], enforce_unit_count=False):
                context_units.append(candidate)
            else:
                excluded_context.append(candidate.unit_id)
        sections.append(
            ReviewSection(
                section_id=f"section-{index:03d}",
                section_index=index,
                assigned_unit_ids=[unit.unit_id for unit in assigned_units],
                context_unit_ids=[unit.unit_id for unit in context_units],
                start_ordinal=start,
                end_ordinal=end - 1,
                excluded_context_unit_ids=excluded_context,
                construction_summary={
                    "assigned_unit_count": len(assigned_units),
                    "context_unit_count": len(context_units),
                    "context_node_count": footprint(context_units)[0],
                    "context_relationship_count": footprint(context_units)[1],
                    "context_helper_count": footprint(context_units)[2],
                    "limits": {
                        "max_assigned_units": section_size,
                        "max_context_nodes": max_nodes,
                        "max_context_relationships": max_relationships,
                        "max_context_helpers": max_helpers,
                        "requested_overlap": overlap,
                    },
                },
            )
        )
    return sections


def visible_evidence(
    unit: EvidenceReviewUnit,
    snapshot: EtiqEvidenceSnapshot,
    expanded_prefixes: Iterable[Iterable[str]] = (),
) -> dict[str, Any]:
    visible_prefixes = {
        tuple(unit.func_stack_prefix),
        *(tuple(prefix) for prefix in expanded_prefixes),
    }
    canonical_visible_prefixes = {
        _canonical_stack(prefix) for prefix in visible_prefixes
    }
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    node_refs = {
        node.node_ref
        for node in snapshot.nodes
        if _canonical_stack(node.func_stack) in canonical_visible_prefixes
    }
    boundary_refs = set(unit.input_relationship_refs) | set(unit.output_relationship_refs)
    relationship_refs: set[str] = set()
    for relationship in snapshot.relationships:
        if relationship.relationship_ref not in unit.relationship_refs:
            continue
        if relationship.relationship_ref in boundary_refs:
            relationship_refs.add(relationship.relationship_ref)
            node_refs.add(relationship.source_ref)
            node_refs.add(relationship.target_ref)
        elif relationship.source_ref in node_refs and relationship.target_ref in node_refs:
            relationship_refs.add(relationship.relationship_ref)
    collapsed = [
        prefix
        for prefix in unit.helper_prefixes
        if tuple(prefix) not in visible_prefixes
        and tuple(prefix[:-1]) in visible_prefixes
    ]
    return {
        "node_refs": sorted(ref for ref in node_refs if ref in node_by_ref),
        "relationship_refs": sorted(relationship_refs),
        "expanded_prefixes": [list(prefix) for prefix in sorted(visible_prefixes)],
        "collapsed_helper_prefixes": collapsed,
    }


def validate_expansion(
    unit: EvidenceReviewUnit,
    requested_prefix: Iterable[str],
    expanded_prefixes: Iterable[Iterable[str]],
) -> list[str]:
    requested = tuple(str(item) for item in requested_prefix)
    allowed_parents = {
        tuple(unit.func_stack_prefix),
        *(tuple(prefix) for prefix in expanded_prefixes),
    }
    helpers = {tuple(prefix) for prefix in unit.helper_prefixes}
    if requested not in helpers:
        raise ValueError(f"unknown helper prefix for {unit.unit_id}: {list(requested)}")
    if requested[:-1] not in allowed_parents:
        raise ValueError(
            f"expansion must request one direct child of visible evidence: {list(requested)}"
        )
    return list(requested)


def inspect_artifact(node: EtiqNodeRecord, request: Mapping[str, Any]) -> dict[str, Any]:
    start = max(0, int(request.get("start") or 0))
    count = max(1, min(100, int(request.get("count") or 20)))
    query = str(request.get("query") or "").strip()
    content = node.artifact_content
    result: dict[str, Any] = {
        "node_ref": node.node_ref,
        "artifact_kind": node.artifact_kind,
        "artifact_size": node.artifact_size,
        "artifact_truncated_at_capture": node.artifact_truncated,
        "start": start,
        "count": count,
        "query": query,
    }
    if content is None:
        return {**result, "content": None, "error": "artifact content was not captured"}
    if node.artifact_kind == "table":
        rows = list(content.get("rows", []))
        available_columns = [str(item) for item in content.get("columns", [])]
        requested_columns = [
            str(item) for item in request.get("columns", []) if str(item) in available_columns
        ]
        columns = requested_columns or available_columns
        matching_rows = (
            [
                row
                for row in rows
                if query.lower() in json.dumps(row, ensure_ascii=False, default=str).lower()
            ]
            if query
            else rows
        )
        selected_rows = [
            {column: row.get(column) for column in columns}
            for row in matching_rows[start:start + count]
        ]
        return {
            **result,
            "columns": columns,
            "content": selected_rows,
            "returned": len(selected_rows),
            "more_available": start + len(selected_rows) < len(matching_rows),
        }
    if node.artifact_kind == "document":
        text = str(content)
        if query:
            lowered = text.lower()
            needle = query.lower()
            matches: list[dict[str, Any]] = []
            position = 0
            while len(matches) < count:
                found = lowered.find(needle, position)
                if found < 0:
                    break
                context_start = max(0, found - 300)
                context_end = min(len(text), found + len(query) + 700)
                matches.append(
                    {
                        "character_offset": found,
                        "text": fence_untrusted(text[context_start:context_end]),
                    }
                )
                position = found + max(1, len(needle))
            return {
                **result,
                "content": matches,
                "returned": len(matches),
                "more_available": lowered.find(needle, position) >= 0,
            }
        char_count = min(20_000, count * 1_000)
        selected = text[start:start + char_count]
        return {
            **result,
            "count": char_count,
            "content": fence_untrusted(selected),
            "returned": len(selected),
            "more_available": start + len(selected) < len(text),
        }
    if isinstance(content, list):
        matching_items = (
            [
                item
                for item in content
                if query.lower() in json.dumps(item, ensure_ascii=False, default=str).lower()
            ]
            if query
            else content
        )
        selected = matching_items[start:start + count]
        return {
            **result,
            "content": selected,
            "returned": len(selected),
            "more_available": start + len(selected) < len(matching_items),
        }
    if isinstance(content, Mapping):
        keys = list(content)
        if query:
            keys = [
                key
                for key in keys
                if query.lower() in key.lower()
                or query.lower()
                in json.dumps(content[key], ensure_ascii=False, default=str).lower()
            ]
        requested_keys = [str(item) for item in request.get("columns", []) if str(item) in content]
        selected_keys = requested_keys or keys[start:start + count]
        return {
            **result,
            "content": {key: content[key] for key in selected_keys},
            "returned": len(selected_keys),
            "more_available": not requested_keys and start + len(selected_keys) < len(keys),
        }
    return {**result, "content": content, "returned": 1, "more_available": False}


def validate_review(
    *,
    review_job_id: str,
    section: ReviewSection,
    units: list[EvidenceReviewUnit],
    decisions: list[ReviewDecision],
    allowed_evidence_refs: set[str],
    receipt_ref: str,
    visible_node_refs_by_unit: Mapping[str, set[str]] | None = None,
) -> tuple[ReviewReceipt, list[TrustAnnotation]]:
    unit_by_id = {unit.unit_id: unit for unit in units}
    assigned = set(section.assigned_unit_ids)
    errors: list[str] = []
    reusable: list[str] = []
    non_pipeline: list[str] = []
    issues: list[str] = []
    suspect_node_refs: list[str] = []
    reviewed: list[str] = []
    for decision in decisions:
        decision_error_count = len(errors)
        if decision.unit_id not in assigned:
            errors.append(f"unassigned unit: {decision.unit_id}")
            continue
        if decision.unit_id in reviewed:
            errors.append(f"duplicate review: {decision.unit_id}")
            continue
        reviewed.append(decision.unit_id)
        unit = unit_by_id[decision.unit_id]
        unknown_evidence = set(decision.evidence_refs) - allowed_evidence_refs
        criterion_refs = {
            str(ref)
            for outcome in decision.criteria_outcomes
            for ref in outcome.get("evidence_refs", [])
        }
        unknown_evidence.update(criterion_refs - allowed_evidence_refs)
        allowed_suspects = set(unit.node_refs) | set(
            (visible_node_refs_by_unit or {}).get(decision.unit_id, set())
        )
        unknown_suspects = set(decision.suspect_node_refs) - allowed_suspects
        unknown_evidence.update(unknown_suspects)
        if unknown_evidence:
            errors.append(f"review cites evidence outside the section package: {decision.unit_id}")
        if unit.boundary_health.degraded and not decision.boundary_health_acknowledged:
            errors.append(f"degraded boundary not acknowledged: {decision.unit_id}")
        if decision.decision == ReviewDecisionStatus.TRUSTED:
            if decision.trust_level not in {str(item) for item in TrustLevel}:
                errors.append(f"trusted review lacks a valid trust level: {decision.unit_id}")
            if not decision.evidence_refs:
                errors.append(f"trusted review lacks evidence: {decision.unit_id}")
            if not decision.criteria_outcomes or any(
                item.get("verdict") != "met" or not item.get("evidence_refs")
                for item in decision.criteria_outcomes
            ):
                errors.append(f"trusted review has unmet or uncited criteria: {decision.unit_id}")
            if decision.trust_level == TrustLevel.REUSE and unit.boundary_health.degraded:
                errors.append(f"degraded boundary cannot be trusted for reuse: {decision.unit_id}")
            if (
                decision.trust_level == TrustLevel.REUSE
                and decision.reviewer_type == "codex"
                and len(errors) == decision_error_count
            ):
                reusable.append(decision.unit_id)
        elif decision.decision in {ReviewDecisionStatus.FAILED, ReviewDecisionStatus.SUSPECT}:
            issues.append(decision.unit_id)
            suspect_node_refs.extend(decision.suspect_node_refs)
        elif decision.decision == ReviewDecisionStatus.NOT_PIPELINE_STEP:
            non_pipeline.append(decision.unit_id)
        elif decision.decision != ReviewDecisionStatus.SUPERSEDED:
            errors.append(f"unknown review decision: {decision.unit_id}")

    invalidated: set[str] = set()
    queue = deque(issues)
    while queue:
        current = queue.popleft()
        current_unit = unit_by_id.get(current)
        if current_unit is None:
            continue
        for downstream in current_unit.downstream_unit_ids:
            if downstream not in invalidated:
                invalidated.add(downstream)
                queue.append(downstream)

    if errors:
        result, next_action = "rejected", "correct_review_records"
    elif issues:
        result, next_action = "blocked_for_repair", "start_repair"
    elif set(reviewed) != assigned:
        errors.append("section review is incomplete")
        result, next_action = "rejected", "complete_review"
    else:
        result, next_action = "passed", "continue"

    receipt = ReviewReceipt(
        receipt_id=new_id("receipt"),
        section_id=section.section_id,
        section_input_hash=section.section_input_hash,
        result=result,
        reviewed_unit_ids=reviewed,
        reusable_trusted_unit_ids=reusable if result != "rejected" else [],
        non_pipeline_unit_ids=non_pipeline if result != "rejected" else [],
        failed_or_suspect_unit_ids=issues,
        invalidated_unit_ids=sorted(invalidated),
        suspect_node_refs=sorted(set(suspect_node_refs)),
        errors=errors,
        next_action=next_action,
    )
    annotations: list[TrustAnnotation] = []
    if result in {"passed", "blocked_for_repair"}:
        decision_by_id = {decision.unit_id: decision for decision in decisions}
        for unit_id in reviewed:
            decision = decision_by_id[unit_id]
            status = (
                decision.trust_level
                if decision.decision == ReviewDecisionStatus.TRUSTED
                else decision.decision
            )
            annotations.append(
                TrustAnnotation(
                    annotation_id=new_id("annotation"),
                    unit_id=unit_id,
                    status=str(status),
                    authority="codex" if decision.reviewer_type == "codex" else "worker_proposal",
                    review_job_id=review_job_id,
                    run_id=unit_by_id[unit_id].run_id,
                    receipt_ref=receipt_ref,
                    evidence_refs=decision.evidence_refs,
                )
            )
        for unit_id in invalidated:
            annotations.append(
                TrustAnnotation(
                    annotation_id=new_id("annotation"),
                    unit_id=unit_id,
                    status="invalidated_pending_repair",
                    authority="system",
                    review_job_id=review_job_id,
                    run_id=unit_by_id[unit_id].run_id,
                    receipt_ref=receipt_ref,
                    evidence_refs=[],
                )
            )
    return receipt, annotations


def trusted_frontier(
    units: list[EvidenceReviewUnit],
    annotations: Iterable[TrustAnnotation | Mapping[str, Any]],
) -> dict[str, list[str]]:
    latest: dict[str, TrustAnnotation | Mapping[str, Any]] = {}
    for annotation in annotations:
        unit_id = (
            str(annotation.get("unit_id"))
            if isinstance(annotation, Mapping)
            else annotation.unit_id
        )
        latest[unit_id] = annotation

    def is_reusable(annotation: TrustAnnotation | Mapping[str, Any]) -> bool:
        if isinstance(annotation, Mapping):
            return (
                str(annotation.get("authority")) == "codex"
                and str(annotation.get("status")) == TrustLevel.REUSE
            )
        return annotation.authority == "codex" and annotation.status == TrustLevel.REUSE

    trusted_candidates = {
        unit_id
        for unit_id, annotation in latest.items()
        if is_reusable(annotation)
    }
    non_pipeline = {
        unit_id
        for unit_id, annotation in latest.items()
        if (
            str(annotation.get("status")) == ReviewDecisionStatus.NOT_PIPELINE_STEP
            if isinstance(annotation, Mapping)
            else annotation.status == ReviewDecisionStatus.NOT_PIPELINE_STEP
        )
    }
    unit_by_id = {unit.unit_id: unit for unit in units}
    trusted: set[str] = set()
    remaining = set(trusted_candidates)
    while remaining:
        progressed = False
        for unit_id in list(remaining):
            unit = unit_by_id.get(unit_id)
            if unit is None:
                remaining.remove(unit_id)
                continue
            relevant_upstream = {
                upstream
                for upstream in unit.upstream_unit_ids
                if upstream in unit_by_id and upstream not in non_pipeline
            }
            if relevant_upstream <= trusted:
                trusted.add(unit_id)
                remaining.remove(unit_id)
                progressed = True
        if not progressed:
            break
    frontier = {
        unit_id
        for unit_id in trusted
        if not any(
            downstream in trusted
            for downstream in unit_by_id[unit_id].downstream_unit_ids
        )
    }
    return {
        "trusted_unit_ids": sorted(trusted),
        "frontier_unit_ids": sorted(frontier),
        "non_pipeline_unit_ids": sorted(non_pipeline),
    }


def retrace_node_refs(
    snapshot: EtiqEvidenceSnapshot,
    start_refs: Iterable[str],
) -> list[str]:
    incoming: dict[str, list[str]] = defaultdict(list)
    for relationship in snapshot.relationships:
        incoming[relationship.target_ref].append(relationship.source_ref)
    found: list[str] = []
    seen: set[str] = set()
    queue = deque(str(ref) for ref in start_refs)
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        found.append(current)
        queue.extend(incoming.get(current, []))
    return found
