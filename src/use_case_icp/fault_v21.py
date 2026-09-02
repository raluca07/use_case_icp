"""Protocol-2.1 identity and realized-boundary mechanics.

This module contains only the v2.1 delta.  Execution, mutation, review, repair,
and package construction continue to use the existing experiment functions.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import keyword
from pathlib import PurePosixPath
import textwrap
from typing import Any, Iterable, Mapping

from .records import EtiqEvidenceSnapshot, GeneratedPipeline, stable_hash
from .review import frame_name, review_node_payload, review_relationship_payload
from .fault_injection import (
    _bundle_sha256,
    _candidates,
    _changed_source_regions,
    _indented_function_source,
    _mutate,
    _operator_name,
    normalize_pipeline,
)
from .fault_v2 import enumerate_reverse_ordering_sites_v2, inject_reverse_ordering_v2


PROTOCOL_ID = "neurips-2026-workshop-fault-localisation-v2"
PROTOCOL_VERSION = "2.1.0"
SEMANTIC_STAGES = frozenset(
    {
        "upstream_demand_selection",
        "upstream_evidence_normalization",
        "upstream_provenance_assembly",
        "downstream_coverage_mapping",
        "downstream_prioritization",
        "downstream_synthesis",
        "supporting",
    }
)
MANDATORY_STAGES = SEMANTIC_STAGES - {"supporting"}
IDENTITY_FIELDS = (
    "job_id",
    "source_path",
    "qualified_function_name",
    "function_source_sha256",
)
METADATA_FIELDS = tuple(f"v21_{field}" for field in IDENTITY_FIELDS)


def normalized_source_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("v2.1 source path is not normalized and relative")
    normalized = path.as_posix()
    if normalized != str(value).replace("\\", "/"):
        raise ValueError("v2.1 source path is not normalized and relative")
    return normalized


def canonical_qualified_function_name(value: str) -> str:
    """Return the exact lexical name, accepting only exact ``<locals>`` transport parts."""
    supplied = str(value)
    parts = supplied.split(".")
    if not supplied or any(not part for part in parts):
        raise ValueError("v2.1 qualified function name has an empty component")
    lexical: list[str] = []
    for part in parts:
        if part == "<locals>":
            continue
        if not part.isidentifier() or keyword.iskeyword(part):
            raise ValueError("v2.1 qualified function name is not lexical Python syntax")
        lexical.append(part)
    if not lexical:
        raise ValueError("v2.1 qualified function name has no lexical component")
    return ".".join(lexical)


def _function_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    normalized = ast.unparse(ast.fix_missing_locations(deepcopy(node))).strip() + "\n"
    return "sha256:" + hashlib.sha256(normalized.encode()).hexdigest()


def static_definitions(
    job_id: str, pipeline: GeneratedPipeline
) -> list[dict[str, Any]]:
    """Return every exact lexical function identity; generated classes fail closed."""
    pipeline.validate()
    definitions: list[dict[str, Any]] = []

    def visit(node: ast.AST, path: str, parents: tuple[str, ...]) -> None:
        if isinstance(node, ast.ClassDef):
            raise ValueError("v2.1 generated classes are prohibited")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified_name = ".".join((*parents, node.name))
            definitions.append(
                {
                    "job_id": str(job_id),
                    "source_path": path,
                    "qualified_function_name": qualified_name,
                    "function_source_sha256": _function_hash(node),
                    "definition_start_line": int(node.lineno),
                }
            )
            for child in ast.iter_child_nodes(node):
                visit(child, path, (*parents, node.name))
            return
        for child in ast.iter_child_nodes(node):
            visit(child, path, parents)

    for generated_file in sorted(pipeline.files, key=lambda item: item.path):
        path = normalized_source_path(generated_file.path)
        visit(ast.parse(generated_file.content, filename=path), path, ())
    return definitions


def resolve_static_identity(
    job_id: str,
    pipeline: GeneratedPipeline,
    *,
    source_path: str,
    qualified_function_name: str,
) -> dict[str, str]:
    expected_path = normalized_source_path(source_path)
    expected_name = canonical_qualified_function_name(qualified_function_name)
    matches = [
        definition
        for definition in static_definitions(job_id, pipeline)
        if definition["source_path"] == expected_path
        and definition["qualified_function_name"] == expected_name
    ]
    if len(matches) != 1:
        raise ValueError("v2.1 declaration does not resolve to exactly one AST function")
    return {field: str(matches[0][field]) for field in IDENTITY_FIELDS}


def parse_generated_pipeline(
    job_id: str, payload: Mapping[str, Any]
) -> GeneratedPipeline:
    """Parse authoring or stabilization output through the one v2.1 resolver."""
    pipeline = GeneratedPipeline.from_payload(payload)
    resolved: list[dict[str, Any]] = []
    identities: set[tuple[str, ...]] = set()
    boundary_ids: set[str] = set()
    for declaration in pipeline.review_boundaries:
        boundary_id = str(declaration.get("boundary_id") or "").strip()
        if not boundary_id or boundary_id in boundary_ids:
            raise ValueError("v2.1 boundary IDs must be non-empty and unique")
        boundary_ids.add(boundary_id)
        stage = str(declaration.get("semantic_stage") or "")
        if stage not in SEMANTIC_STAGES:
            raise ValueError("v2.1 declaration has an invalid semantic_stage")
        identity = resolve_static_identity(
            job_id,
            pipeline,
            source_path=str(declaration.get("source_path") or ""),
            qualified_function_name=str(
                declaration.get("qualified_function_name") or ""
            ),
        )
        key = tuple(identity[field] for field in IDENTITY_FIELDS)
        if key in identities:
            raise ValueError("v2.1 declarations contain a duplicate static identity")
        identities.add(key)
        resolved.append(
            {
                **declaration,
                **identity,
                "boundary_id": boundary_id,
                "function_name": identity["qualified_function_name"].split(".")[-1],
                "semantic_stage": stage,
            }
        )
    pipeline.review_boundaries = resolved
    pipeline.validate()
    return pipeline


def _canonical_stack(stack: Iterable[str]) -> tuple[str, ...]:
    return tuple(frame_name(str(value)) for value in stack)


def _starts_with(stack: Iterable[str], prefix: tuple[str, ...]) -> bool:
    canonical = _canonical_stack(stack)
    return canonical[: len(prefix)] == prefix


def _captured_function_evidence(nodes: Iterable[Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for node in nodes:
        marker = str(node.raw_metadata.get("source_node_type") or "")
        if marker not in {"FunctionDef", "AsyncFunctionDef"}:
            continue
        if not node.source:
            raise ValueError("v2.1 captured function evidence has no source")
        try:
            body = ast.parse(textwrap.dedent(str(node.source))).body
        except (IndentationError, SyntaxError) as error:
            raise ValueError("v2.1 captured function evidence is unparseable") from error
        if len(body) != 1 or not isinstance(
            body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            raise ValueError("v2.1 captured function evidence is incomplete")
        function = body[0]
        if type(function).__name__ != marker:
            raise ValueError("v2.1 captured function evidence has conflicting type")
        evidence.append(
            {
                "node_ref": node.node_ref,
                "function_name": function.name,
                "function_source_sha256": _function_hash(function),
                "line_no": int(node.line_no) if node.line_no is not None else None,
            }
        )
    return evidence


def enrich_snapshot_identities(
    snapshot: EtiqEvidenceSnapshot,
    *,
    job_id: str,
    pipeline: GeneratedPipeline,
) -> EtiqEvidenceSnapshot:
    """Resolve captured prefixes independently of which functions were declared."""
    if snapshot.job_id != job_id:
        raise ValueError("v2.1 capture belongs to the wrong job")
    enriched = deepcopy(snapshot)
    definitions = static_definitions(job_id, pipeline)
    prefixes = sorted(
        {
            _canonical_stack(node.func_stack[:depth])
            for node in enriched.nodes
            for depth in range(1, len(node.func_stack) + 1)
        },
        key=lambda value: (len(value), value),
    )
    resolved_prefixes: dict[tuple[str, ...], tuple[str, ...]] = {}
    for prefix in prefixes:
        direct = [
            node
            for node in enriched.nodes
            if _canonical_stack(node.func_stack) == prefix
        ]
        evidence = _captured_function_evidence(direct)
        metadata_presence = [
            any(field in node.raw_metadata for field in METADATA_FIELDS)
            for node in direct
        ]
        if not evidence:
            if any(metadata_presence):
                raise ValueError("v2.1 capture contains forged identity metadata")
            continue
        evidence_keys = {
            (
                item["function_name"],
                item["function_source_sha256"],
                item["line_no"],
            )
            for item in evidence
        }
        if len(evidence_keys) != 1:
            raise ValueError("v2.1 captured prefix has conflicting definition evidence")
        function_name, function_hash, line_no = next(iter(evidence_keys))
        matches = [
            definition
            for definition in definitions
            if definition["qualified_function_name"].split(".")[-1] == function_name
            and definition["function_source_sha256"] == function_hash
            and (line_no is None or definition["definition_start_line"] == line_no)
        ]
        if not matches:
            if any(metadata_presence):
                raise ValueError("v2.1 capture identity metadata conflicts with source")
            continue
        if len(matches) != 1:
            raise ValueError("v2.1 captured definition evidence is ambiguous")
        identity = {field: str(matches[0][field]) for field in IDENTITY_FIELDS}
        key = tuple(identity[field] for field in IDENTITY_FIELDS)
        if prefix in resolved_prefixes and resolved_prefixes[prefix] != key:
            raise ValueError("v2.1 captured prefix resolves to conflicting identities")
        resolved_prefixes[prefix] = key
        derivation = {
            "prefix": list(prefix),
            "static_identity": identity,
            "captured_definition_evidence": sorted(
                evidence, key=lambda item: item["node_ref"]
            ),
        }
        for node in direct:
            present = [field in node.raw_metadata for field in METADATA_FIELDS]
            if any(present) and not all(present):
                raise ValueError("v2.1 captured node has partial identity metadata")
            expected = tuple(identity[field] for field in IDENTITY_FIELDS)
            if all(present):
                observed = tuple(str(node.raw_metadata[field]) for field in METADATA_FIELDS)
                if observed != expected:
                    raise ValueError("v2.1 captured node identity conflicts with source")
            node.raw_metadata.update(dict(zip(METADATA_FIELDS, expected)))
            node.raw_metadata["v21_identity_derivation"] = deepcopy(derivation)
            node.raw_metadata["v21_identity_derivation_sha256"] = stable_hash(derivation)
    return enriched


def materialize_realized_boundaries(
    snapshot: EtiqEvidenceSnapshot,
    declarations: Iterable[Mapping[str, Any]],
    *,
    job_id: str,
    pipeline: GeneratedPipeline,
) -> dict[str, Any]:
    """Return exact declaration/capture intersection plus restricted unmatched audit."""
    if snapshot.job_id != job_id:
        raise ValueError("v2.1 boundary capture belongs to the wrong job")
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    if len(node_by_ref) != len(snapshot.nodes) or len(relationship_by_ref) != len(
        snapshot.relationships
    ):
        raise ValueError("v2.1 capture contains duplicate evidence references")
    if any(
        relationship.source_ref not in node_by_ref
        or relationship.target_ref not in node_by_ref
        for relationship in snapshot.relationships
    ):
        raise ValueError("v2.1 capture relationship has a missing endpoint")

    identities_by_prefix: dict[tuple[str, ...], tuple[str, ...]] = {}
    for node in snapshot.nodes:
        present = [field in node.raw_metadata for field in METADATA_FIELDS]
        if any(present) and not all(present):
            raise ValueError("v2.1 captured node has partial identity metadata")
        if not all(present):
            continue
        prefix = _canonical_stack(node.func_stack)
        identity = tuple(str(node.raw_metadata[field]) for field in METADATA_FIELDS)
        previous = identities_by_prefix.setdefault(prefix, identity)
        if previous != identity:
            raise ValueError("v2.1 captured prefix has conflicting identity evidence")

    realized: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_identities: set[tuple[str, ...]] = set()
    for declaration in declarations:
        boundary_id = str(declaration.get("boundary_id") or "").strip()
        if not boundary_id or boundary_id in seen_ids:
            raise ValueError("v2.1 boundary IDs must be non-empty and unique")
        seen_ids.add(boundary_id)
        stage = str(declaration.get("semantic_stage") or "")
        if stage not in SEMANTIC_STAGES:
            raise ValueError("v2.1 declaration has an invalid semantic_stage")
        identity = resolve_static_identity(
            job_id,
            pipeline,
            source_path=str(declaration.get("source_path") or ""),
            qualified_function_name=str(
                declaration.get("qualified_function_name") or ""
            ),
        )
        supplied_hash = str(declaration.get("function_source_sha256") or "")
        if supplied_hash and supplied_hash != identity["function_source_sha256"]:
            raise ValueError("v2.1 declaration has a conflicting source hash")
        identity_key = tuple(identity[field] for field in IDENTITY_FIELDS)
        if identity_key in seen_identities:
            raise ValueError("v2.1 declarations contain a duplicate static identity")
        seen_identities.add(identity_key)
        matched_prefixes = sorted(
            prefix
            for prefix, runtime_identity in identities_by_prefix.items()
            if runtime_identity == identity_key
        )
        if not matched_prefixes:
            unmatched.append(
                {
                    "boundary_id": boundary_id,
                    "static_identity": identity,
                    "semantic_stage": stage,
                    "reason": "no_exact_captured_prefix",
                }
            )
            continue
        inside_refs = {
            node.node_ref
            for node in snapshot.nodes
            if any(_starts_with(node.func_stack, prefix) for prefix in matched_prefixes)
        }
        relationship_refs = {
            edge.relationship_ref
            for edge in snapshot.relationships
            if edge.source_ref in inside_refs or edge.target_ref in inside_refs
        }
        input_refs = {
            edge.relationship_ref
            for edge in snapshot.relationships
            if edge.source_ref not in inside_refs and edge.target_ref in inside_refs
        }
        output_refs = {
            edge.relationship_ref
            for edge in snapshot.relationships
            if edge.source_ref in inside_refs and edge.target_ref not in inside_refs
        }
        helper_prefixes = sorted(
            {
                canonical[:depth]
                for node in snapshot.nodes
                for canonical in [_canonical_stack(node.func_stack)]
                for prefix in matched_prefixes
                if canonical[: len(prefix)] == prefix
                for depth in range(len(prefix) + 1, len(canonical) + 1)
            },
            key=lambda value: (len(value), value),
        )
        function_refs = sorted(
            node.node_ref
            for node in snapshot.nodes
            if _canonical_stack(node.func_stack) in matched_prefixes
            and node.state_type.casefold().replace("_", "") == "functionmapping"
        )
        boundary = {
            "boundary_id": boundary_id,
            "semantic_stage": stage,
            "role": str(declaration.get("role") or ""),
            "expected_inputs": list(declaration.get("expected_inputs", [])),
            "expected_outputs": list(declaration.get("expected_outputs", [])),
            "static_identity": identity,
            "function_name": identity["qualified_function_name"].split(".")[-1],
            "matched_prefix": list(matched_prefixes[0]),
            "matched_prefixes": [list(prefix) for prefix in matched_prefixes],
            "prefix_multiplicity": len(matched_prefixes),
            "matched_function_node_refs": function_refs,
            "matched_function_node_ref": function_refs[0]
            if function_refs
            else sorted(inside_refs)[0],
            "node_refs": sorted(inside_refs),
            "relationship_refs": sorted(relationship_refs),
            "input_relationship_refs": sorted(input_refs),
            "output_relationship_refs": sorted(output_refs),
            "helper_prefixes": [list(prefix) for prefix in helper_prefixes],
        }
        boundary["realized_boundary_sha256"] = stable_hash(boundary)
        realized.append(boundary)
    audit = {
        "job_id": job_id,
        "realized_boundary_count": len(realized),
        "unmatched_declaration_count": len(unmatched),
        "unmatched_declarations": sorted(unmatched, key=lambda item: item["boundary_id"]),
    }
    audit["audit_sha256"] = stable_hash(audit)
    return {
        "realized_boundaries": sorted(realized, key=lambda item: item["boundary_id"]),
        "boundary_realization_audit": audit,
    }


def grouped_boundary_selection(
    snapshot: EtiqEvidenceSnapshot,
    boundary: Mapping[str, Any],
    *,
    expanded_prefixes: Iterable[Iterable[str]] = (),
) -> dict[str, Any]:
    base = {tuple(prefix) for prefix in boundary["matched_prefixes"]}
    helpers = {tuple(prefix) for prefix in boundary["helper_prefixes"]}
    expanded = {tuple(str(value) for value in prefix) for prefix in expanded_prefixes}
    if not expanded.issubset(helpers):
        raise ValueError("v2.1 expansion is outside the realized boundary")
    if any(prefix[:-1] not in base | expanded for prefix in expanded):
        raise ValueError("v2.1 expansion is not a legal direct-child sequence")
    visible_prefixes = base | expanded
    node_refs = {
        node.node_ref
        for node in snapshot.nodes
        if _canonical_stack(node.func_stack) in visible_prefixes
    }
    crossing = set(boundary["input_relationship_refs"]) | set(
        boundary["output_relationship_refs"]
    )
    relationship_refs = {
        edge.relationship_ref
        for edge in snapshot.relationships
        if edge.relationship_ref in crossing
        or (edge.source_ref in node_refs and edge.target_ref in node_refs)
    }
    for edge in snapshot.relationships:
        if edge.relationship_ref in crossing:
            node_refs.update((edge.source_ref, edge.target_ref))
    result = {
        "boundary_id": boundary["boundary_id"],
        "node_refs": sorted(node_refs),
        "relationship_refs": sorted(relationship_refs),
        "expanded_prefixes": [list(prefix) for prefix in sorted(expanded)],
    }
    result["selection_sha256"] = stable_hash(result)
    return result


def eligible_direct_child_helpers(
    snapshot: EtiqEvidenceSnapshot, boundaries: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    boundaries = list(boundaries)
    declared_prefixes = {
        tuple(prefix)
        for boundary in boundaries
        for prefix in boundary["matched_prefixes"]
    }
    eligible: list[dict[str, Any]] = []
    for boundary in boundaries:
        base = {tuple(prefix) for prefix in boundary["matched_prefixes"]}
        initial = grouped_boundary_selection(snapshot, boundary)
        for helper in sorted({tuple(value) for value in boundary["helper_prefixes"]}):
            if helper in declared_prefixes or helper[:-1] not in base:
                continue
            direct_nodes = [
                node
                for node in snapshot.nodes
                if _canonical_stack(node.func_stack) == helper
            ]
            has_function = any(
                node.raw_metadata.get("source_node_type")
                in {"FunctionDef", "AsyncFunctionDef"}
                and (
                    node.state_type.casefold().replace("_", "")
                    == "functionmapping"
                    or node.value_preview is not None
                )
                for node in direct_nodes
            )
            if not has_function:
                continue
            expanded = grouped_boundary_selection(
                snapshot, boundary, expanded_prefixes=[helper]
            )
            new_nodes = sorted(set(expanded["node_refs"]) - set(initial["node_refs"]))
            new_edges = sorted(
                set(expanded["relationship_refs"])
                - set(initial["relationship_refs"])
            )
            if not new_nodes and not new_edges:
                continue
            eligible.append(
                {
                    "boundary_id": boundary["boundary_id"],
                    "helper_prefix": list(helper),
                    "incremental_node_refs": new_nodes,
                    "incremental_relationship_refs": new_edges,
                }
            )
    return eligible


def graph_size_report(
    snapshot: EtiqEvidenceSnapshot,
    boundaries: Iterable[Mapping[str, Any]],
    *,
    protocol_version: str = PROTOCOL_VERSION,
) -> dict[str, Any]:
    boundaries = list(boundaries)
    if protocol_version == "2.2.0":
        from .fault_experiment import graph_selection_for_mode

        full = graph_selection_for_mode(
            "etiq_full",
            snapshot,
            boundaries,
            include_projection_binding=True,
        )
        fixed = graph_selection_for_mode(
            "etiq_selected_fixed",
            snapshot,
            boundaries,
            include_projection_binding=True,
        )
        adaptive = graph_selection_for_mode(
            "etiq_selected_adaptive",
            snapshot,
            boundaries,
            include_projection_binding=True,
        )
        assert full is not None and fixed is not None and adaptive is not None
        if fixed["node_refs"] != adaptive["node_refs"] or fixed[
            "relationship_refs"
        ] != adaptive["relationship_refs"]:
            raise ValueError("v2.2 fixed and adaptive initial projections differ")
        if fixed["graph_evidence_sha256"] != adaptive["graph_evidence_sha256"]:
            raise ValueError("v2.2 fixed and adaptive initial graph bytes differ")
        if not set(fixed["node_refs"]).issubset(full["node_refs"]):
            raise ValueError("v2.2 selected node references are not contained in full")
        if not set(fixed["relationship_refs"]).issubset(
            full["relationship_refs"]
        ):
            raise ValueError(
                "v2.2 selected relationship references are not contained in full"
            )
        selected_bytes = int(fixed["graph_evidence_utf8_bytes"])
        full_bytes = int(full["graph_evidence_utf8_bytes"])
        return {
            "protocol_version": "2.2.0",
            "job_id": snapshot.job_id,
            "boundaries": [],
            "selected_total_bytes": selected_bytes,
            "full_total_bytes": full_bytes,
            "aggregate_ratio": selected_bytes / full_bytes if full_bytes else 1.0,
            "selected_projection": fixed,
            "full_projection": full,
            "adaptive_initial_projection_sha256": adaptive["projection_sha256"],
            "adaptive_initial_graph_evidence_sha256": adaptive[
                "graph_evidence_sha256"
            ],
            "fixed_adaptive_initial_equal": True,
            "selected_nodes_subset_of_full": True,
            "selected_relationships_subset_of_full": True,
        }
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    edge_by_ref = {edge.relationship_ref: edge for edge in snapshot.relationships}

    def encoded_size(node_refs: Iterable[str], edge_refs: Iterable[str]) -> int:
        payload = {
            "nodes": [review_node_payload(node_by_ref[ref]) for ref in sorted(node_refs)],
            "relationships": [
                review_relationship_payload(edge_by_ref[ref]) for ref in sorted(edge_refs)
            ],
        }
        return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())

    rows: list[dict[str, Any]] = []
    for boundary in boundaries:
        selected = grouped_boundary_selection(snapshot, boundary)
        selected_bytes = encoded_size(
            selected["node_refs"], selected["relationship_refs"]
        )
        full_node_refs = set(boundary["node_refs"])
        for edge_ref in boundary["input_relationship_refs"] + boundary["output_relationship_refs"]:
            edge = edge_by_ref[edge_ref]
            full_node_refs.update((edge.source_ref, edge.target_ref))
        full_bytes = encoded_size(full_node_refs, boundary["relationship_refs"])
        ratio = selected_bytes / full_bytes if full_bytes else 1.0
        rows.append(
            {
                "boundary_id": boundary["boundary_id"],
                "selected_bytes": selected_bytes,
                "full_bytes": full_bytes,
                "ratio": ratio,
            }
        )
    selected_total = sum(row["selected_bytes"] for row in rows)
    full_total = sum(row["full_bytes"] for row in rows)
    return {
        "boundaries": rows,
        "at_most_80_percent_count": sum(row["ratio"] <= 0.8 for row in rows),
        "selected_total_bytes": selected_total,
        "full_total_bytes": full_total,
        "aggregate_ratio": selected_total / full_total if full_total else 1.0,
    }


def qualify_realized_chain(
    job_realizations: Iterable[Mapping[str, Any]],
    *,
    handoffs: Iterable[Mapping[str, Any]],
    helper_evidence: Iterable[Mapping[str, Any]],
    graph_size_reports: Iterable[Mapping[str, Any]],
    has_join_or_aggregation: bool,
    protocol_version: str | None = None,
    evidence_budget_bytes: int = 360_000,
) -> dict[str, Any]:
    jobs = list(job_realizations)
    if len(jobs) != 2:
        raise ValueError("v2.1 qualification requires exactly two jobs")
    reports = list(graph_size_reports)
    version = protocol_version or (
        "2.2.0"
        if reports and all(report.get("protocol_version") == "2.2.0" for report in reports)
        else PROTOCOL_VERSION
    )
    if version != "2.2.0" and any(
        len(realization["realized_boundaries"])
        + int(
            realization["boundary_realization_audit"][
                "unmatched_declaration_count"
            ]
        )
        < 8
        for realization in jobs
    ):
        raise ValueError("v2.1 qualification requires at least eight declarations per job")
    boundaries = [
        boundary
        for realization in jobs
        for boundary in realization["realized_boundaries"]
    ]
    if version == "2.2.0" and any(
        not realization["realized_boundaries"] for realization in jobs
    ):
        raise ValueError("v2.2 qualification requires packageable realized boundaries in both jobs")
    if version != "2.2.0" and len(boundaries) < 12:
        raise ValueError("v2.1 qualification requires at least 12 realized boundaries")
    stages = {boundary["semantic_stage"] for boundary in boundaries}
    missing_stages = MANDATORY_STAGES - stages
    if version != "2.2.0" and missing_stages:
        raise ValueError(
            f"v2.1 qualification has an unmatched mandatory stage: {sorted(missing_stages)}"
        )
    handoffs = list(handoffs)
    if len(handoffs) < 2 or any(
        item.get("producer_sha256") != item.get("consumer_sha256")
        for item in handoffs
    ):
        raise ValueError("v2.1 qualification requires two exact-hash handoffs")
    helpers = list(helper_evidence)
    if version != "2.2.0" and len({tuple(item["helper_prefix"]) for item in helpers}) < 2:
        raise ValueError("v2.1 qualification requires two eligible helpers")
    if any(
        not item.get("incremental_node_refs")
        and not item.get("incremental_relationship_refs")
        for item in helpers
    ):
        raise ValueError("v2.2 counted helper expansion adds no evidence")
    if version != "2.2.0" and not has_join_or_aggregation:
        raise ValueError("v2.1 qualification requires downstream aggregation")
    rows = [row for report in reports for row in report["boundaries"]]
    if version != "2.2.0" and sum(row["ratio"] <= 0.8 for row in rows) * 2 < len(rows):
        raise ValueError("v2.1 selected evidence is not <=80% for half the boundaries")
    selected_total = sum(report["selected_total_bytes"] for report in reports)
    full_total = sum(report["full_total_bytes"] for report in reports)
    if version != "2.2.0" and (not full_total or selected_total / full_total > 0.9):
        raise ValueError(f"v{version} aggregate selected evidence exceeds 90% of full")
    if version == "2.2.0" and reports:
        if any(
            not report.get("fixed_adaptive_initial_equal")
            or not report.get("selected_nodes_subset_of_full")
            or not report.get("selected_relationships_subset_of_full")
            for report in reports
        ):
            raise ValueError("v2.2 canonical projection invariants failed")
        if full_total > evidence_budget_bytes:
            raise ValueError("v2.2 endpoint-complete full graph exceeds evidence budget")
    result = {
        "protocol_version": version,
        "job_count": 2,
        "realized_boundary_count": len(boundaries),
        "unmatched_declaration_count": sum(
            realization["boundary_realization_audit"]["unmatched_declaration_count"]
            for realization in jobs
        ),
        "mandatory_stages": sorted(MANDATORY_STAGES),
        "handoff_count": len(handoffs),
        "eligible_helper_count": len(helpers),
        "selected_to_full_ratio": selected_total / full_total if full_total else None,
        "selected_graph_evidence_bytes": selected_total,
        "full_graph_evidence_bytes": full_total,
        "full_graph_evidence_budget_bytes": evidence_budget_bytes,
        "projection_hashes": [
            {
                "job_id": report.get("job_id"),
                "selected_projection_sha256": report.get(
                    "selected_projection", {}
                ).get("projection_sha256"),
                "selected_graph_evidence_sha256": report.get(
                    "selected_projection", {}
                ).get("graph_evidence_sha256"),
                "full_projection_sha256": report.get("full_projection", {}).get(
                    "projection_sha256"
                ),
                "full_graph_evidence_sha256": report.get(
                    "full_projection", {}
                ).get("graph_evidence_sha256"),
            }
            for report in reports
        ] if version == "2.2.0" else [],
        "has_join_or_aggregation": bool(has_join_or_aggregation),
    }
    result["qualification_sha256"] = stable_hash(result)
    return result


def _target_function(
    pipeline: GeneratedPipeline, identity: Mapping[str, Any]
) -> tuple[dict[str, str], ast.FunctionDef | ast.AsyncFunctionDef]:
    exact = resolve_static_identity(
        str(identity.get("job_id") or ""),
        pipeline,
        source_path=str(identity.get("source_path") or ""),
        qualified_function_name=str(identity.get("qualified_function_name") or ""),
    )
    if any(str(identity.get(field) or "") != exact[field] for field in IDENTITY_FIELDS):
        raise ValueError("v2.1 mutation target identity conflicts with source")
    source = next(item.content for item in pipeline.files if item.path == exact["source_path"])
    matches: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def visit(body: Iterable[ast.stmt], parents: tuple[str, ...]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                raise ValueError("v2.1 generated classes are prohibited")
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            qualified = ".".join((*parents, node.name))
            if qualified == exact["qualified_function_name"]:
                matches.append(node)
            visit(node.body, (*parents, node.name))

    visit(ast.parse(source, filename=exact["source_path"]).body, ())
    if len(matches) != 1:
        raise ValueError("v2.1 mutation target does not resolve exactly")
    return exact, matches[0]


def enumerate_operator_sites(
    pipeline: GeneratedPipeline,
    *,
    target_identity: Mapping[str, Any],
    operator: str,
    parameter: str = "",
) -> list[dict[str, Any]]:
    clean = normalize_pipeline(pipeline)
    if operator == "reverse_ordering":
        return enumerate_reverse_ordering_sites_v2(
            clean, target_identity=target_identity
        )
    exact, function = _target_function(clean, target_identity)
    sites = _candidates(function, operator, parameter)
    return [
        {
            "file": exact["source_path"],
            "job_id": exact["job_id"],
            "qualified_function_name": exact["qualified_function_name"],
            "function_source_sha256": exact["function_source_sha256"],
            "occurrence": occurrence,
            "kind": _operator_name(operator, node, detail),
            "subsite": detail,
            "line": int(node.lineno),
            "column": int(node.col_offset),
        }
        for occurrence, (node, detail) in enumerate(sites)
    ]


def inject_operator_exact(
    pipeline: GeneratedPipeline,
    *,
    target_identity: Mapping[str, Any],
    operator: str,
    occurrence: int,
    parameter: str = "",
) -> dict[str, Any]:
    clean = normalize_pipeline(pipeline)
    if operator == "reverse_ordering":
        result = inject_reverse_ordering_v2(
            clean, target_identity=target_identity, occurrence=occurrence
        )
        return {**result, "protocol_version": PROTOCOL_VERSION}
    exact, original = _target_function(clean, target_identity)
    function = deepcopy(original)
    candidates = _candidates(function, operator, parameter)
    if occurrence < 0 or occurrence >= len(candidates):
        raise ValueError("v2.1 mutation occurrence is unavailable")
    node, detail = candidates[occurrence]
    site_kind = _operator_name(operator, node, detail)
    before = ast.dump(function, include_attributes=False)
    _mutate(operator, node, detail, parameter)
    function = ast.fix_missing_locations(function)
    if before == ast.dump(function, include_attributes=False):
        raise ValueError("v2.1 mutation changed nothing")
    original_source = _indented_function_source(original)
    mutant_source = _indented_function_source(function)
    original_span, mutant_span, original_snippet, mutant_snippet = _changed_source_regions(
        original_source, mutant_source, file_start_line=int(original.lineno)
    )
    scope = {
        "requested_mode": "boundary",
        "effective_mode": "boundary",
        "scope_kind": "function",
        "function_name": original.name,
        "file": exact["source_path"],
        "start_line": int(original.lineno),
        "end_line": int(original.end_lineno or original.lineno),
    }
    mutant = deepcopy(clean)
    target_file = next(item for item in mutant.files if item.path == exact["source_path"])
    lines = target_file.content.splitlines(keepends=True)
    replacement = mutant_source if mutant_source.endswith("\n") else mutant_source + "\n"
    target_file.content = "".join(
        [*lines[: int(original.lineno) - 1], replacement, *lines[int(original.end_lineno or original.lineno) :]]
    )
    for item in mutant.files:
        compile(item.content, item.path, "exec")
    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "fault_class": operator,
        "clean_pipeline": clean,
        "pipeline": mutant,
        "clean_bundle_sha256": _bundle_sha256(clean),
        "mutant_bundle_sha256": _bundle_sha256(mutant),
        "site": {
            "file": exact["source_path"],
            "job_id": exact["job_id"],
            "qualified_function_name": exact["qualified_function_name"],
            "function_source_sha256": exact["function_source_sha256"],
            "function_name": original.name,
            "occurrence": occurrence,
            "candidate_count": len(candidates),
            "kind": site_kind,
            "subsite": detail,
            "original_span": original_span,
            "mutant_span": mutant_span,
            "original_snippet": original_snippet,
            "mutant_snippet": mutant_snippet,
        },
    }


def freeze_operator_site_order(
    pipeline: GeneratedPipeline,
    *,
    target_identity: Mapping[str, Any],
    operator: str,
    seed: int,
    parameter: str = "",
) -> dict[str, Any]:
    clean = normalize_pipeline(pipeline)
    exact, _function = _target_function(clean, target_identity)
    clean_hash = _bundle_sha256(clean)
    candidates: list[dict[str, Any]] = []
    for site in enumerate_operator_sites(
        clean,
        target_identity=exact,
        operator=operator,
        parameter=parameter,
    ):
        material = {
            "mutation_seed": int(seed),
            "clean_bundle_sha256": clean_hash,
            "job_id": exact["job_id"],
            "source_path": exact["source_path"],
            "qualified_function_name": exact["qualified_function_name"],
            "function_source_sha256": exact["function_source_sha256"],
            "site_kind": site["kind"],
            "occurrence": site["occurrence"],
            "list_subsite": site.get("subsite"),
        }
        candidates.append({**site, "order_key": sha256_bytes_for_value(material)})
    result = {
        "operator": operator,
        "mutation_seed": int(seed),
        "clean_bundle_sha256": clean_hash,
        "target_identity": exact,
        "frozen_candidates": sorted(
            candidates, key=lambda item: (item["order_key"], item["occurrence"])
        ),
    }
    result["frozen_schedule_sha256"] = stable_hash(result)
    return result


def sha256_bytes_for_value(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
