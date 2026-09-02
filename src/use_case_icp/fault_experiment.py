from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import secrets
import stat
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping

from .records import (
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    GeneratedPipeline,
    jsonable,
)
from .review import (
    frame_name,
    match_observed_function_prefixes,
    review_node_payload,
    review_relationship_payload,
)


EVIDENCE_MODES = (
    "current_run",
    "history_full",
    "etiq_full",
    "etiq_selected_fixed",
    "etiq_selected_adaptive",
    "etiq_random_matched",
)
GRAPH_MODES = frozenset(EVIDENCE_MODES[2:])
PRIMARY_CONFIGURATIONS = (
    ("current_run", True),
    ("history_full", True),
    ("etiq_full", True),
    ("etiq_selected_adaptive", True),
)
ABLATION_SUBSET_INSTANCE_IDS = frozenset(
    {
        "instance-01",
        "instance-02",
        "instance-04",
        "instance-06",
        "instance-08",
        "instance-10",
    }
)
ALLOWED_HISTORY_KINDS = frozenset(
    {"task_input", "task_output", "stdout", "stderr", "source"}
)
MAX_HISTORY_BYTES = 240_000
MAX_PACKAGE_BYTES = 360_000
MAX_EVIDENCE_TOKENS = 90_000
MAX_REFERENCE_CANDIDATES = 3
MAX_STABILIZATION_CYCLES = 3
PROTOCOL_ID = "neurips-2026-workshop-fault-localisation"
PROTOCOL_VERSION = "1.3.1"
PROTOCOL_CONTENT_HASH = (
    "sha256:c5af2acbe1aa7ab473efad4d2fc3adb4183edaadf23165831cfb7b052a3b1d9f"
)
SETUP_RECORD_KINDS = frozenset(
    {
        "preflight",
        "authoring",
        "stabilization_repair",
        "rejected_candidate",
        "reference_execution",
        "reference_oracle",
        "complexity_gate",
    }
)
CONDITION_LABELS = frozenset(
    {
        "current_run",
        "history_full",
        "etiq_full",
        "etiq_selected_fixed",
        "etiq_selected_adaptive",
        "etiq_random_matched",
        "source_present",
        "source_absent",
        "complete_arm_matrix",
    }
)
FRAMING_CONDITION_TERMS = frozenset(
    {"current", "history", "full", "selected", "adaptive", "fixed", "random"}
)
GRAPH_NODE_SERIALIZATION_POLICY = (
    "preserve_complete_visible_etiq_node_serialization_across_source_bundle_settings"
)
FORBIDDEN_FIELDS = frozenset(
    {
        "boundary_health",
        "clean_output",
        "clean_validation",
        "condition_label",
        "condition_name",
        "evidence_mode",
        "fault_class",
        "fault_identity",
        "fault_label",
        "fault_manifest",
        "fault_target",
        "hidden_oracle",
        "injected_function",
        "injected_node",
        "injection",
        "injection_manifest",
        "oracle",
        "oracle_result",
        "oracle_results",
        "oracle_status",
        "prior_trust_judgment",
        "repair_target",
        "review_decision",
        "review_judgment",
        "source_setting",
        "trust_judgment",
        "trust_state",
    }
)


def _encode(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _canonical_stack(stack: Iterable[str]) -> tuple[str, ...]:
    return tuple(frame_name(str(frame)) for frame in stack)


def _starts_with(stack: Iterable[str], prefix: Iterable[str]) -> bool:
    values = _canonical_stack(stack)
    expected = _canonical_stack(prefix)
    return len(values) >= len(expected) and values[: len(expected)] == expected


def _capabilities(evidence_mode: str) -> dict[str, bool]:
    return {
        "inspect_visible_artifact": evidence_mode in GRAPH_MODES,
        "reveal_direct_child": evidence_mode == "etiq_selected_adaptive",
        "retrace_relationships_after_localisation": evidence_mode in GRAPH_MODES,
    }


def condition_configurations(instance_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Return the frozen D03 schedule without creating reviewer-visible labels."""
    ids = [str(value) for value in instance_ids]
    if len(ids) != 12 or len(set(ids)) != 12:
        raise ValueError("the fault experiment requires 12 unique instance IDs")
    missing_subset = ABLATION_SUBSET_INSTANCE_IDS - set(ids)
    if missing_subset:
        raise ValueError(f"missing prespecified ablation instances: {sorted(missing_subset)}")

    primary = set(PRIMARY_CONFIGURATIONS)
    configurations: list[dict[str, Any]] = []
    for evidence_mode, include_source_bundle in (
        (mode, setting)
        for mode in EVIDENCE_MODES
        for setting in (True, False)
    ):
        is_primary = (evidence_mode, include_source_bundle) in primary
        configurations.append(
            {
                "configuration_role": "primary" if is_primary else "ablation_only",
                "evidence_mode": evidence_mode,
                "source_setting": (
                    "source_present" if include_source_bundle else "source_absent"
                ),
                "include_source_bundle": include_source_bundle,
                "eligible_instance_ids": (
                    ids if is_primary else sorted(ABLATION_SUBSET_INSTANCE_IDS)
                ),
                "capabilities": _capabilities(evidence_mode),
            }
        )
    if sum(value["configuration_role"] == "primary" for value in configurations) != 4:
        raise AssertionError("frozen primary matrix changed")
    if sum(value["configuration_role"] == "ablation_only" for value in configurations) != 8:
        raise AssertionError("frozen ablation matrix changed")
    return configurations


def build_condition_manifests(
    instance_ids: Iterable[str],
    *,
    evidence_hashes: Mapping[tuple[str, str], str] | None = None,
    job_ids: tuple[str, str] = (
        "market_demand_research",
        "coverage_prioritization_and_synthesis",
    ),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build controller-only and reviewer-visible condition manifests.

    The caller must store the first result outside every branch sandbox.  Semantic
    labels occur only there.  The second result contains opaque IDs and neutral
    capability flags and is safe to copy into branch-controller input.
    """
    configurations = condition_configurations(instance_ids)
    if len(job_ids) != 2 or len(set(job_ids)) != 2:
        raise ValueError("condition configuration requires exact upstream/downstream job IDs")
    hashes = evidence_hashes or {}
    restricted: list[dict[str, Any]] = []
    visible: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    visible_branches: list[dict[str, Any]] = []
    opaque_instance_ids = {
        instance_id: f"ins-{secrets.token_hex(12)}"
        for instance_id in {
            value
            for item in configurations
            for value in item["eligible_instance_ids"]
        }
    }
    for configuration in configurations:
        condition_id = f"cfg-{secrets.token_hex(12)}"
        evidence_mode = configuration["evidence_mode"]
        source_setting = configuration["source_setting"]
        evidence_hash = hashes.get((evidence_mode, source_setting))
        if evidence_hash is not None and not re.fullmatch(
            r"sha256:[0-9a-f]{64}", evidence_hash
        ):
            raise ValueError("condition evidence hashes must be SHA-256 digests")
        entry = {
            **configuration,
            "condition_id": condition_id,
            "evidence_sha256": evidence_hash,
        }
        restricted.append(entry)
        visible.append(
            {
                "condition_id": condition_id,
                "capabilities": configuration["capabilities"],
                "evidence_sha256": evidence_hash,
            }
        )
        for instance_id in configuration["eligible_instance_ids"]:
            branch_id = f"brn-{secrets.token_hex(12)}"
            branches.append(
                {
                    "instance_id": instance_id,
                    "opaque_instance_id": opaque_instance_ids[instance_id],
                    "condition_id": condition_id,
                    "branch_id": branch_id,
                    "evidence_mode": evidence_mode,
                    "source_setting": source_setting,
                }
            )
            visible_branches.append(
                {
                    "instance_id": opaque_instance_ids[instance_id],
                    "condition_id": condition_id,
                    "branch_id": branch_id,
                    "capabilities": configuration["capabilities"],
                    "evidence_sha256": evidence_hash,
                }
            )
    return (
        {
            "schema_version": "1",
            "protocol_content_hash": PROTOCOL_CONTENT_HASH,
            "storage_classification": "restricted_controller_only",
            "job_positions": {"upstream": job_ids[0], "downstream": job_ids[1]},
            "configurations": restricted,
            "branches": branches,
        },
        {
            "schema_version": "1",
            "protocol_content_hash": PROTOCOL_CONTENT_HASH,
            "conditions": visible,
            "branches": visible_branches,
        },
    )


def materialize_realized_boundaries(
    snapshot: EtiqEvidenceSnapshot,
    declarations: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Strictly match declarations and materialize B_f from captured evidence."""
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    if len(node_by_ref) != len(snapshot.nodes):
        raise ValueError("captured snapshot contains duplicate node references")
    if len(relationship_by_ref) != len(snapshot.relationships):
        raise ValueError("captured snapshot contains duplicate relationship references")
    missing_endpoints = {
        endpoint
        for relationship in snapshot.relationships
        for endpoint in (relationship.source_ref, relationship.target_ref)
        if endpoint not in node_by_ref
    }
    if missing_endpoints:
        raise ValueError(
            f"captured relationships have missing endpoints: {sorted(missing_endpoints)}"
        )
    realized: list[dict[str, Any]] = []
    seen_boundaries: set[str] = set()
    seen_prefixes: set[tuple[str, ...]] = set()
    for declaration in declarations:
        boundary_id = _opaque_id(declaration.get("boundary_id"), "boundary_id")
        function_name = str(declaration.get("function_name") or "").strip()
        if not function_name:
            raise ValueError(f"declaration {boundary_id} requires function_name")
        if boundary_id in seen_boundaries:
            raise ValueError(f"duplicate declaration boundary ID: {boundary_id}")
        seen_boundaries.add(boundary_id)
        outermost = match_observed_function_prefixes(snapshot, function_name)
        if len(outermost) != 1:
            reason = "not observed" if not outermost else "matched multiple observed prefixes"
            raise ValueError(
                f"declared boundary {boundary_id} ({function_name}) {reason}; instance is invalid before review"
            )
        prefix = outermost[0]
        if prefix in seen_prefixes:
            raise ValueError(f"multiple declarations resolve to observed prefix: {list(prefix)}")
        seen_prefixes.add(prefix)
        direct_nodes = sorted(
            (
                node
                for node in snapshot.nodes
                if _canonical_stack(node.func_stack) == prefix
            ),
            key=lambda node: node.node_ref,
        )
        if not direct_nodes:
            raise ValueError(
                f"declared boundary {boundary_id} has no captured node at its matched prefix"
            )
        function_nodes = [
            node
            for node in direct_nodes
            if node.state_type.casefold().replace("_", "") == "functionmapping"
        ]
        matched_function_node_ref = (function_nodes or direct_nodes)[0].node_ref
        inside_refs = {
            node.node_ref
            for node in snapshot.nodes
            if _starts_with(node.func_stack, prefix)
        }
        relationship_refs: list[str] = []
        input_refs: list[str] = []
        output_refs: list[str] = []
        for relationship in snapshot.relationships:
            source_inside = relationship.source_ref in inside_refs
            target_inside = relationship.target_ref in inside_refs
            if source_inside or target_inside:
                relationship_refs.append(relationship.relationship_ref)
            if not source_inside and target_inside:
                input_refs.append(relationship.relationship_ref)
            elif source_inside and not target_inside:
                output_refs.append(relationship.relationship_ref)
        helper_prefixes = sorted(
            {
                _canonical_stack(node.func_stack[:depth])
                for node in snapshot.nodes
                if _starts_with(node.func_stack, prefix)
                for depth in range(len(prefix) + 1, len(node.func_stack) + 1)
            },
            key=lambda value: (len(value), value),
        )
        realized.append(
            {
                "boundary_id": boundary_id,
                "function_name": function_name,
                "matched_prefix": list(prefix),
                "matched_function_node_ref": matched_function_node_ref,
                "node_refs": sorted(inside_refs),
                "relationship_refs": sorted(set(relationship_refs)),
                "input_relationship_refs": sorted(set(input_refs)),
                "output_relationship_refs": sorted(set(output_refs)),
                "helper_prefixes": [list(value) for value in helper_prefixes],
            }
        )
    if not realized:
        raise ValueError("at least one semantic declaration is required")
    return realized


def graph_selection_for_mode(
    evidence_mode: str,
    snapshot: EtiqEvidenceSnapshot,
    realized_boundaries: Iterable[Mapping[str, Any]],
    *,
    handoffs: Iterable[Mapping[str, Any]] = (),
    expanded_prefixes_by_boundary: Mapping[str, Iterable[Iterable[str]]] | None = None,
    frozen_random_by_boundary: Mapping[str, Mapping[str, Any]] | None = None,
    random_instance_id: str | None = None,
    random_protocol_content_hash: str = PROTOCOL_CONTENT_HASH,
    include_projection_binding: bool = False,
) -> dict[str, Any] | None:
    """Return the canonical endpoint-complete graph projection for one job."""
    if evidence_mode not in EVIDENCE_MODES:
        raise ValueError(f"unknown evidence mode: {evidence_mode}")
    expanded = {
        str(boundary_id): [
            tuple(str(item) for item in prefix)
            for prefix in prefixes
        ]
        for boundary_id, prefixes in (expanded_prefixes_by_boundary or {}).items()
    }
    if evidence_mode != "etiq_selected_adaptive" and any(expanded.values()):
        raise ValueError(f"{evidence_mode} cannot expand helper prefixes")
    if evidence_mode not in GRAPH_MODES:
        return None
    boundaries = list(realized_boundaries)
    eligible_boundary_ids = {
        str(boundary["boundary_id"])
        for boundary in boundaries
    }
    unknown_expansion_boundaries = set(expanded) - eligible_boundary_ids
    if unknown_expansion_boundaries:
        raise ValueError(
            "expansion request references unknown realized boundary: "
            f"{sorted(unknown_expansion_boundaries)}"
        )
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    if len(node_by_ref) != len(snapshot.nodes) or len(relationship_by_ref) != len(
        snapshot.relationships
    ):
        raise ValueError("canonical projection requires unique captured evidence references")
    random = frozen_random_by_boundary or {}
    all_node_refs: set[str] = set()
    all_relationship_refs: set[str] = set()
    visible_by_boundary: dict[str, Any] = {}
    collapsed_helpers: list[dict[str, Any]] = []

    for boundary in boundaries:
        boundary_id = str(boundary["boundary_id"])
        base_prefixes = {
            tuple(str(value) for value in prefix)
            for prefix in boundary.get(
                "matched_prefixes", [boundary["matched_prefix"]]
            )
        }
        boundary_relationships = set(boundary["relationship_refs"])
        crossing_refs = set(boundary["input_relationship_refs"]) | set(
            boundary["output_relationship_refs"]
        )
        if evidence_mode == "etiq_full":
            node_refs = set(boundary["node_refs"])
            relationship_refs = boundary_relationships
        elif evidence_mode == "etiq_random_matched":
            if boundary_id not in random:
                raise ValueError(
                    f"random mode requires D05 frozen projection for boundary {boundary_id}"
                )
            frozen = random[boundary_id]
            if random_instance_id is None:
                raise ValueError("random mode requires its canonical instance identity")
            from .random_control import verify_random_projection_manifest

            frozen = verify_random_projection_manifest(
                snapshot,
                boundary,
                graph_selection_for_mode(
                    "etiq_selected_fixed",
                    snapshot,
                    [boundary],
                    handoffs=handoffs,
                ),
                frozen,
                instance_id=random_instance_id,
                handoffs=handoffs,
                protocol_content_hash=random_protocol_content_hash,
            )
            node_refs = {str(value) for value in frozen.get("node_refs", [])}
            relationship_refs = {
                str(value) for value in frozen.get("relationship_refs", [])
            }
            if not relationship_refs.issubset(boundary_relationships):
                raise ValueError(
                    f"random projection escapes realized boundary {boundary_id}"
                )
            eligible_nodes = set(boundary["node_refs"])
            for relationship_ref in boundary_relationships:
                relationship = relationship_by_ref[relationship_ref]
                eligible_nodes.update({relationship.source_ref, relationship.target_ref})
            if not node_refs.issubset(eligible_nodes):
                raise ValueError(f"random projection contains nodes outside boundary {boundary_id}")
            mandatory_relationship_refs = crossing_refs
            mandatory_node_refs = {str(boundary["matched_function_node_ref"])}
            for relationship_ref in mandatory_relationship_refs:
                relationship = relationship_by_ref[relationship_ref]
                mandatory_node_refs.update(
                    {relationship.source_ref, relationship.target_ref}
                )
            if (
                not mandatory_relationship_refs.issubset(relationship_refs)
                or not mandatory_node_refs.issubset(node_refs)
            ):
                raise ValueError(
                    f"random projection omits mandatory boundary interface for {boundary_id}"
                )
            for relationship_ref in relationship_refs:
                relationship = relationship_by_ref[relationship_ref]
                if (
                    relationship.source_ref not in node_refs
                    or relationship.target_ref not in node_refs
                ):
                    raise ValueError(
                        f"random projection is not endpoint-complete for {boundary_id}"
                    )
        else:
            requested = expanded.get(boundary_id, [])
            visible_prefixes = set(base_prefixes)
            helpers = {tuple(value) for value in boundary["helper_prefixes"]}
            for requested_prefix in requested:
                if (
                    requested_prefix not in helpers
                    or requested_prefix[:-1] not in visible_prefixes
                ):
                    raise ValueError(
                        f"expansion must reveal a direct child of visible evidence: {list(requested_prefix)}"
                    )
                visible_prefixes.add(requested_prefix)
            node_refs = {
                node.node_ref
                for node in snapshot.nodes
                if _canonical_stack(node.func_stack) in visible_prefixes
            }
            relationship_refs = set(crossing_refs)
            for relationship_ref in crossing_refs:
                relationship = relationship_by_ref[relationship_ref]
                node_refs.update({relationship.source_ref, relationship.target_ref})
            for relationship_ref in boundary_relationships:
                relationship = relationship_by_ref[relationship_ref]
                if (
                    relationship.source_ref in node_refs
                    and relationship.target_ref in node_refs
                ):
                    relationship_refs.add(relationship_ref)
            collapsed_helpers.extend(
                {
                    "boundary_id": boundary_id,
                    "func_stack": list(helper),
                }
                for helper in sorted(helpers)
                if helper not in visible_prefixes and helper[:-1] in visible_prefixes
            )

        for relationship_ref in relationship_refs:
            if relationship_ref not in relationship_by_ref:
                raise ValueError(f"edge absent from captured execution: {relationship_ref}")
            relationship = relationship_by_ref[relationship_ref]
            node_refs.update({relationship.source_ref, relationship.target_ref})
        if not node_refs.issubset(node_by_ref):
            raise ValueError(
                "selection references nodes absent from capture: "
                f"{sorted(node_refs - node_by_ref.keys())}"
            )
        all_node_refs.update(node_refs)
        all_relationship_refs.update(relationship_refs)
        visible_by_boundary[boundary_id] = {
            "node_refs": sorted(node_refs),
            "relationship_refs": sorted(relationship_refs),
            "expanded_prefixes": (
                [list(value) for value in sorted(visible_prefixes)]
                if evidence_mode in {"etiq_selected_fixed", "etiq_selected_adaptive"}
                else []
            ),
        }

    clean_handoffs: list[dict[str, Any]] = []
    for handoff in handoffs:
        handoff_ref = str(handoff.get("handoff_ref") or "")
        upstream = str(handoff.get("upstream_job_id") or "")
        downstream = str(handoff.get("downstream_job_id") or "")
        digest = str(handoff.get("artifact_sha256") or "")
        if (
            not handoff_ref
            or snapshot.job_id not in {upstream, downstream}
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        ):
            raise ValueError(
                "handoffs require an incident job and an exact SHA-256 artifact hash"
            )
        clean_handoffs.append(dict(handoff))
    collapsed_helpers = sorted(
        {
            (
                str(value["boundary_id"]),
                tuple(str(frame) for frame in value["func_stack"]),
            )
            for value in collapsed_helpers
        }
    )
    selection = {
        "node_refs": sorted(all_node_refs),
        "relationship_refs": sorted(all_relationship_refs),
        "visible_evidence_by_boundary": {
            key: visible_by_boundary[key] for key in sorted(visible_by_boundary)
        },
        "collapsed_helpers": [
            {"boundary_id": boundary_id, "func_stack": list(prefix)}
            for boundary_id, prefix in collapsed_helpers
        ],
        "handoffs": clean_handoffs,
    }
    selected_nodes = set(selection["node_refs"])
    for relationship_ref in selection["relationship_refs"]:
        relationship = relationship_by_ref[relationship_ref]
        if (
            relationship.source_ref not in selected_nodes
            or relationship.target_ref not in selected_nodes
        ):
            raise ValueError(
                f"canonical projection has a hidden relationship endpoint: {relationship_ref}"
            )
    if not include_projection_binding:
        return selection
    graph_evidence = {
        "nodes": [
            review_node_payload(node_by_ref[ref]) for ref in selection["node_refs"]
        ],
        "relationships": [
            review_relationship_payload(relationship_by_ref[ref])
            for ref in selection["relationship_refs"]
        ],
    }
    graph_bytes = _encode(graph_evidence)
    inputs = {
        "snapshot_id": snapshot.snapshot_id,
        "job_id": snapshot.job_id,
        "run_id": snapshot.run_id,
        "evidence_mode": evidence_mode,
        "realized_boundaries": boundaries,
        "expanded_prefixes_by_boundary": {
            key: [list(prefix) for prefix in value]
            for key, value in sorted(expanded.items())
        },
        "frozen_random_by_boundary": random,
        "random_instance_id": random_instance_id,
        "random_protocol_content_hash": random_protocol_content_hash,
        "handoffs": clean_handoffs,
    }
    binding = {
        "projection_inputs_sha256": _digest(_encode(inputs)),
        "node_refs_sha256": _digest(_encode(selection["node_refs"])),
        "relationship_refs_sha256": _digest(
            _encode(selection["relationship_refs"])
        ),
        "graph_evidence_sha256": _digest(graph_bytes),
        "graph_evidence_utf8_bytes": len(graph_bytes),
        "evidence_mode": evidence_mode,
    }
    binding["projection_sha256"] = _digest(_encode({**selection, **binding}))
    return {**selection, **binding}


def verify_canonical_graph_projection(
    snapshot: EtiqEvidenceSnapshot, projection: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify a frozen projection without rerunning its selection policy."""
    required = {
        "node_refs",
        "relationship_refs",
        "visible_evidence_by_boundary",
        "collapsed_helpers",
        "handoffs",
        "projection_inputs_sha256",
        "node_refs_sha256",
        "relationship_refs_sha256",
        "graph_evidence_sha256",
        "graph_evidence_utf8_bytes",
        "evidence_mode",
        "projection_sha256",
    }
    if not required.issubset(projection):
        raise ValueError("canonical projection binding is incomplete")
    node_refs = [str(value) for value in projection["node_refs"]]
    relationship_refs = [str(value) for value in projection["relationship_refs"]]
    if node_refs != sorted(set(node_refs)) or relationship_refs != sorted(
        set(relationship_refs)
    ):
        raise ValueError("canonical projection references are not unique and sorted")
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    missing_nodes = set(node_refs) - set(node_by_ref)
    missing_relationships = set(relationship_refs) - set(relationship_by_ref)
    if missing_nodes or missing_relationships:
        raise ValueError(
            "canonical projection references missing captured evidence: "
            f"nodes={sorted(missing_nodes)}, relationships={sorted(missing_relationships)}"
        )
    selected_nodes = set(node_refs)
    for ref in relationship_refs:
        relationship = relationship_by_ref[ref]
        if (
            relationship.source_ref not in selected_nodes
            or relationship.target_ref not in selected_nodes
        ):
            raise ValueError(
                f"canonical projection has a hidden relationship endpoint: {ref}"
            )
    graph_evidence = {
        "nodes": [review_node_payload(node_by_ref[ref]) for ref in node_refs],
        "relationships": [
            review_relationship_payload(relationship_by_ref[ref])
            for ref in relationship_refs
        ],
    }
    graph_bytes = _encode(graph_evidence)
    if projection["node_refs_sha256"] != _digest(_encode(node_refs)):
        raise ValueError("canonical projection node-reference hash changed")
    if projection["relationship_refs_sha256"] != _digest(
        _encode(relationship_refs)
    ):
        raise ValueError("canonical projection relationship-reference hash changed")
    if projection["graph_evidence_sha256"] != _digest(graph_bytes) or int(
        projection["graph_evidence_utf8_bytes"]
    ) != len(graph_bytes):
        raise ValueError("canonical projection serialized graph evidence changed")
    unsigned = {
        key: projection[key]
        for key in required
        if key != "projection_sha256"
    }
    if projection["projection_sha256"] != _digest(_encode(unsigned)):
        raise ValueError("canonical projection hash verification failed")
    visible_nodes = set(node_refs)
    visible_relationships = set(relationship_refs)
    for value in projection["visible_evidence_by_boundary"].values():
        if not set(map(str, value.get("node_refs", []))).issubset(visible_nodes):
            raise ValueError("boundary visibility exceeds canonical projection nodes")
        if not set(map(str, value.get("relationship_refs", []))).issubset(
            visible_relationships
        ):
            raise ValueError(
                "boundary visibility exceeds canonical projection relationships"
            )
    return dict(projection)


def build_condition_review_package(
    *,
    evidence_mode: str,
    snapshot: EtiqEvidenceSnapshot,
    declarations: Iterable[Mapping[str, Any]],
    handoffs: Iterable[Mapping[str, Any]] = (),
    expanded_prefixes_by_boundary: Mapping[str, Iterable[Iterable[str]]] | None = None,
    frozen_random_by_boundary: Mapping[str, Mapping[str, Any]] | None = None,
    random_instance_id: str | None = None,
    **package_inputs: Any,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Strict workshop entry point: match every declaration before packaging."""
    declaration_values = [dict(value) for value in declarations]
    realized = materialize_realized_boundaries(snapshot, declaration_values)
    selection = graph_selection_for_mode(
        evidence_mode,
        snapshot,
        realized,
        handoffs=handoffs,
        expanded_prefixes_by_boundary=expanded_prefixes_by_boundary,
        frozen_random_by_boundary=frozen_random_by_boundary,
        random_instance_id=random_instance_id,
    )
    package, manifest = build_fault_review_package(
        evidence_mode=evidence_mode,
        declarations=declaration_values,
        snapshot=snapshot if evidence_mode in GRAPH_MODES else None,
        graph_selection=selection,
        **package_inputs,
    )
    return package, manifest, realized


def _opaque_id(value: Any, field: str) -> str:
    identifier = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", identifier):
        raise ValueError(f"{field} must be an opaque 8-128 character identifier")
    normalized = identifier.casefold().replace("-", "_")
    if any(label in normalized for label in CONDITION_LABELS):
        raise ValueError(f"{field} discloses an experimental condition")
    return identifier


def _leaks(
    value: Any,
    path: str = "package",
    forbidden_strings: frozenset[str] = frozenset(),
) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        record_kind = str(value.get("record_kind") or "").casefold().replace("-", "_")
        if (
            value.get("storage_classification") == "restricted_controller_only"
            or record_kind in SETUP_RECORD_KINDS
            or "setup_usage" in value
        ):
            found.append(path)
        for key, item in value.items():
            normalized = re.sub(
                r"[^a-z0-9]+", "_", str(key).casefold()
            ).strip("_")
            item_path = f"{path}.{key}"
            padded = f"_{normalized}_"
            if (
                normalized in FORBIDDEN_FIELDS
                or any(f"_{label}_" in padded for label in CONDITION_LABELS)
                or (
                    any(
                        marker in item_path
                        for marker in (
                            ".review_task",
                            ".behavioural_criteria",
                            ".semantic_declarations",
                            ".section",
                        )
                    )
                    and any(
                        f"_{term}_" in padded for term in FRAMING_CONDITION_TERMS
                    )
                )
                or any(identifier in str(key) for identifier in forbidden_strings)
            ):
                found.append(item_path)
            found.extend(_leaks(item, item_path, forbidden_strings))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_leaks(item, f"{path}[{index}]", forbidden_strings))
    elif isinstance(value, str):
        normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
        padded = f"_{normalized}_"
        framing_path = any(
            marker in path
            for marker in (
                ".review_task",
                ".behavioural_criteria",
                ".semantic_declarations",
                ".section",
            )
        )
        if (
            any(f"_{label}_" in padded for label in CONDITION_LABELS)
            or (framing_path and any(f"_{term}_" in padded for term in FRAMING_CONDITION_TERMS))
            or any(identifier in value for identifier in forbidden_strings)
        ):
            found.append(path)
    return found


def _filter_history(
    values: Iterable[Mapping[str, Any]],
    *,
    branch_id: str,
    chain_id: str,
    include_source_bundle: bool,
) -> tuple[list[dict[str, Any]], int]:
    allowed: list[dict[str, Any]] = []
    omitted = 0
    for value in values:
        ref = str(value.get("ref") or "")
        kind = str(value.get("kind") or "").casefold().replace("-", "_")
        if not isinstance(value.get("source_bearing"), bool):
            raise ValueError(f"history artifact {ref or 'unidentified'} requires source_bearing")
        if kind in SETUP_RECORD_KINDS or kind not in ALLOWED_HISTORY_KINDS:
            omitted += 1
            continue
        if "scope" not in value or "chain_id" not in value:
            raise ValueError(
                f"history artifact {ref or 'unidentified'} requires explicit scope and chain_id provenance"
            )
        scope = str(value["scope"]).casefold().replace("-", "_")
        record_chain_id = _opaque_id(value["chain_id"], "history_chain_id")
        if scope not in {"canonical_chain", "faulty_chain", "branch"}:
            raise ValueError(f"history artifact {ref or 'unidentified'} has invalid scope")
        if scope in {"canonical_chain", "faulty_chain"} and value.get("branch_id"):
            raise ValueError(
                f"history artifact {ref or 'unidentified'} has ambiguous faulty-chain provenance"
            )
        if scope == "branch" and not value.get("branch_id"):
            raise ValueError(
                f"history artifact {ref or 'unidentified'} requires branch_id provenance"
            )
        record_branch_id = (
            _opaque_id(value["branch_id"], "history_branch_id")
            if scope == "branch"
            else None
        )
        permitted = (
            bool(ref)
            and record_chain_id == chain_id
            and (scope != "branch" or record_branch_id == branch_id)
            and (include_source_bundle or (kind != "source" and not value["source_bearing"]))
        )
        item = {
            "ref": ref,
            "job_id": _opaque_id(value.get("job_id"), "history_job_id"),
            "kind": kind,
            "content": value.get("content"),
        }
        if not permitted or _leaks(item, "history"):
            omitted += 1
            continue
        allowed.append(item)

    while allowed and len(_encode(allowed)) > MAX_HISTORY_BYTES:
        allowed.pop(0)
        omitted += 1
    return allowed, omitted


def validate_two_job_chain(
    job_ids: Iterable[str],
    dependencies: Mapping[str, Iterable[str]],
    handoffs: Iterable[Mapping[str, Any]],
) -> tuple[str, str]:
    """Validate the frozen upstream/downstream topology used by protocol 1.3.1."""
    jobs = tuple(str(value) for value in job_ids)
    if len(jobs) != 2 or len(set(jobs)) != 2:
        raise ValueError("protocol 1.3.1 requires exactly two unique executed jobs")
    upstream, downstream = jobs
    normalized = {
        str(job_id): tuple(str(value) for value in values)
        for job_id, values in dependencies.items()
    }
    if set(normalized) != set(jobs) or normalized[upstream] or normalized[downstream] != (upstream,):
        raise ValueError("two-job chain must be ordered as one upstream and one dependent downstream job")
    incident = [
        (
            str(value.get("handoff_ref") or "").strip(),
            str(value.get("artifact_sha256") or ""),
        )
        for value in handoffs
        if str(value.get("upstream_job_id")) == upstream
        and str(value.get("downstream_job_id")) == downstream
        and str(value.get("handoff_ref") or "").strip()
        and re.fullmatch(r"sha256:[0-9a-f]{64}", str(value.get("artifact_sha256") or ""))
    ]
    if len(set(incident)) < 2 or len({handoff_ref for handoff_ref, _ in incident}) < 2:
        raise ValueError(
            "two-job chain requires at least two distinct exact-hash handoff identities"
        )
    return upstream, downstream


def build_setup_record(
    record_kind: str,
    *,
    setup_id: str,
    job_ids: Iterable[str],
    payload: Mapping[str, Any],
    usage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create controller-only setup evidence that can never be a review-history item."""
    kind = str(record_kind).casefold().replace("-", "_")
    if kind not in SETUP_RECORD_KINDS:
        raise ValueError(f"unknown restricted setup record kind: {record_kind}")
    jobs = [str(value) for value in job_ids]
    if len(jobs) != 2 or len(set(jobs)) != 2:
        raise ValueError("setup records require the exact two executed job IDs")
    record = {
        "schema_version": "1",
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "storage_classification": "restricted_controller_only",
        "record_kind": kind,
        "setup_id": _opaque_id(setup_id, "setup_id"),
        "job_ids": jobs,
        "payload": dict(payload),
        "setup_usage": dict(usage or {}),
        "excluded_from_experimental_treatment_usage": True,
        "reviewer_visibility": "forbidden",
    }
    record["record_sha256"] = _digest(_encode(record))
    return record


def persist_setup_record(
    record: Mapping[str, Any],
    restricted_root: Path | str,
    *,
    sandbox_visible_roots: Iterable[Path | str] = (),
) -> Path:
    """Persist one immutable setup record outside every model-visible root."""
    root = Path(restricted_root).resolve()
    for visible_root in sandbox_visible_roots:
        visible = Path(visible_root).resolve()
        if root == visible or root in visible.parents or visible in root.parents:
            raise ValueError("restricted setup root overlaps a sandbox-visible root")
    value = dict(record)
    recorded_hash = str(value.pop("record_sha256", ""))
    if (
        value.get("storage_classification") != "restricted_controller_only"
        or value.get("record_kind") not in SETUP_RECORD_KINDS
        or recorded_hash != _digest(_encode(value))
    ):
        raise ValueError("invalid restricted setup record")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{value['setup_id']}-{value['record_kind']}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(dict(record), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def build_stabilization_evidence(
    *,
    failure_kind: str,
    failing_job_id: str,
    source: Iterable[Mapping[str, Any]],
    command: Iterable[str],
    exit_status: int,
    stdout: str,
    stderr: str,
    expected_interface: Mapping[str, Any],
    frozen_schema_and_criteria: Mapping[str, Any],
    partial_capture: Mapping[str, Any] | None = None,
    completed_upstream_capture: Mapping[str, Any] | None = None,
    completed_upstream_handoffs: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the frozen compile/runtime stabilization evidence ladder."""
    upstream_handoffs = [dict(value) for value in completed_upstream_handoffs]
    if failure_kind not in {"compile_import", "runtime", "validation"}:
        raise ValueError(
            "stabilization failure kind must be compile_import, runtime, or validation"
        )
    if failure_kind == "compile_import" and any(
        value is not None
        for value in (partial_capture, completed_upstream_capture)
    ):
        raise ValueError("compile/import stabilization evidence must not contain a graph")
    if failure_kind == "compile_import" and upstream_handoffs:
        raise ValueError("compile/import stabilization evidence must not contain a handoff")
    if failure_kind == "validation" and any(
        value is not None
        for value in (partial_capture, completed_upstream_capture)
    ):
        raise ValueError("oracle/complexity stabilization evidence must not contain a graph")
    if failure_kind == "validation" and upstream_handoffs:
        raise ValueError("oracle/complexity stabilization evidence must not contain a handoff")
    evidence = {
        "failure_kind": failure_kind,
        "failing_job_id": str(failing_job_id),
        "source": [dict(value) for value in source],
        "command": [str(value) for value in command],
        "exit_status": int(exit_status),
        "stdout": str(stdout),
        "stderr": str(stderr),
        "expected_interface": dict(expected_interface),
        "frozen_schema_and_criteria": dict(frozen_schema_and_criteria),
        "partial_capture": dict(partial_capture) if partial_capture is not None else None,
        "partial_capture_status": "labelled_partial" if partial_capture is not None else "absent",
        "completed_upstream_capture": (
            dict(completed_upstream_capture)
            if completed_upstream_capture is not None
            else None
        ),
        "completed_upstream_handoffs": upstream_handoffs,
        "editable_job_ids": [str(failing_job_id)],
        "complete_rerun_job_positions": ["upstream", "downstream"],
    }
    return evidence


def validate_reference_attempt(candidate_number: int, stabilization_cycle: int) -> None:
    """Apply the same frozen ceilings to preflight and experimental references."""
    if not 1 <= int(candidate_number) <= MAX_REFERENCE_CANDIDATES:
        raise ValueError("reference candidate limit is three")
    if not 0 <= int(stabilization_cycle) <= MAX_STABILIZATION_CYCLES:
        raise ValueError("stabilization cycle limit is three per candidate")


def validate_stabilization_replacement(
    original_jobs: Mapping[str, GeneratedPipeline],
    replacement_jobs: Mapping[str, GeneratedPipeline],
    *,
    failing_job_id: str,
) -> None:
    """Permit a setup patch only in the currently failing job."""
    if set(original_jobs) != set(replacement_jobs) or len(original_jobs) != 2:
        raise ValueError("stabilization must retain the same exact two job IDs")
    if failing_job_id not in original_jobs:
        raise ValueError("stabilization target is absent from the two-job candidate")
    for job_id in original_jobs:
        original_jobs[job_id].validate()
        replacement_jobs[job_id].validate()
        if job_id != failing_job_id and _encode(jsonable(original_jobs[job_id])) != _encode(
            jsonable(replacement_jobs[job_id])
        ):
            raise ValueError("stabilization changed the frozen other job")


def build_fault_review_package(
    *,
    evidence_mode: str,
    include_source_bundle: bool,
    opaque_ids: Mapping[str, Any],
    review_task: str,
    behavioural_criteria: Iterable[str],
    top_level_input: Any,
    final_output: Any,
    assigned_job: Mapping[str, Any],
    declarations: Iterable[Mapping[str, Any]],
    section: Mapping[str, Any],
    full_chain_source: Iterable[Mapping[str, Any]],
    history_chain_id: str,
    sibling_branch_ids: Iterable[str] = (),
    history: Iterable[Mapping[str, Any]] = (),
    snapshot: EtiqEvidenceSnapshot | None = None,
    graph_selection: Mapping[str, Any] | None = None,
    token_estimator: Callable[[str], int] | None = None,
    token_estimator_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if evidence_mode not in EVIDENCE_MODES:
        raise ValueError(f"unknown fault-experiment evidence mode: {evidence_mode}")
    source_jobs = [dict(value) for value in full_chain_source]
    source_job_ids = [str(value.get("job_id") or "") for value in source_jobs]
    if len(source_job_ids) != 2 or len(set(source_job_ids)) != 2:
        raise ValueError("protocol 1.3.1 packages require exactly two source job IDs")
    ids = {
        "instance_id": _opaque_id(opaque_ids.get("instance_id"), "instance_id"),
        "condition_id": _opaque_id(opaque_ids.get("condition_id"), "condition_id"),
        "branch_id": _opaque_id(opaque_ids.get("branch_id"), "branch_id"),
    }
    chain_id = _opaque_id(history_chain_id, "history_chain_id")
    sibling_ids = frozenset(
        _opaque_id(value, "sibling_branch_id") for value in sibling_branch_ids
    )
    if ids["branch_id"] in sibling_ids:
        raise ValueError("sibling branch IDs must not include the current branch")

    neutral_declarations = [
        {
            "boundary_id": _opaque_id(value.get("boundary_id"), "boundary_id"),
            "function_name": str(value.get("function_name") or ""),
            "role": str(value.get("role") or ""),
            "expected_inputs": [str(item) for item in value.get("expected_inputs", [])],
            "expected_outputs": [str(item) for item in value.get("expected_outputs", [])],
        }
        for value in declarations
    ]
    if not neutral_declarations or any(
        not value["function_name"] for value in neutral_declarations
    ):
        raise ValueError("every package requires named semantic declarations")
    boundary_ids = {value["boundary_id"] for value in neutral_declarations}
    if len(boundary_ids) != len(neutral_declarations):
        raise ValueError("semantic declaration boundary IDs must be unique")
    assigned_boundary_ids = [
        _opaque_id(value, "assigned_boundary_id")
        for value in section.get("assigned_boundary_ids", [])
    ]
    context_boundary_ids = [
        _opaque_id(value, "context_boundary_id")
        for value in section.get("context_boundary_ids", [])
    ]
    if not assigned_boundary_ids or not set(assigned_boundary_ids).issubset(boundary_ids):
        raise ValueError("section requires declared assigned boundaries")
    if not set(context_boundary_ids).issubset(boundary_ids):
        raise ValueError("section contains an undeclared context boundary")

    common_base = {
        "schema_version": "1",
        "review_task": str(review_task),
        "behavioural_criteria": [str(item) for item in behavioural_criteria],
        "top_level": {"input": top_level_input, "final_output": final_output},
        "assigned_job": {
            "job_id": _opaque_id(assigned_job.get("job_id"), "job_id"),
            "input": assigned_job.get("input"),
            "output": assigned_job.get("output"),
            "stdout": str(assigned_job.get("stdout") or ""),
            "stderr": str(assigned_job.get("stderr") or ""),
        },
        "semantic_declarations": neutral_declarations,
        "section": {
            "section_id": _opaque_id(section.get("section_id"), "section_id"),
            "section_index": int(section.get("section_index", 0)),
            "assigned_boundary_ids": assigned_boundary_ids,
            "context_boundary_ids": context_boundary_ids,
            "organization": section.get("organization", {}),
        },
    }
    package: dict[str, Any] = {
        "schema_version": "1",
        "opaque_ids": ids,
        "capabilities": _capabilities(evidence_mode),
        "common_base": common_base,
    }
    components: dict[str, Any] = {"common-base.json": common_base}
    omitted_history = 0

    if include_source_bundle:
        source_bundle: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for job in source_jobs:
            job_id = _opaque_id(job.get("job_id"), "source_job_id")
            files: list[dict[str, str]] = []
            for value in job.get("files", []):
                path = PurePosixPath(str(value.get("path") or ""))
                identity = (job_id, path.as_posix())
                if path.is_absolute() or ".." in path.parts or not path.parts:
                    raise ValueError(f"unsafe source path: {path}")
                if identity in seen:
                    raise ValueError(f"duplicate source file: {job_id}/{path}")
                seen.add(identity)
                files.append({"path": path.as_posix(), "content": str(value.get("content") or "")})
            if not files:
                raise ValueError(f"source job {job_id} has no files")
            source_bundle.append({"job_id": job_id, "files": files})
        if not source_bundle:
            raise ValueError("bundle-present packages require complete chain source")
        package["source_bundle"] = source_bundle
        components["source-bundle.json"] = source_bundle

    if evidence_mode == "history_full":
        prior_records, omitted_history = _filter_history(
            history,
            branch_id=ids["branch_id"],
            chain_id=chain_id,
            include_source_bundle=include_source_bundle,
        )
        package["prior_task_records"] = prior_records
        components["prior-task-records.json"] = prior_records

    if evidence_mode in GRAPH_MODES:
        if snapshot is None or graph_selection is None:
            raise ValueError("graph modes require an authoritative Etiq snapshot and selection")
        node_by_ref = {node.node_ref: node for node in snapshot.nodes}
        relationship_by_ref = {
            relationship.relationship_ref: relationship
            for relationship in snapshot.relationships
        }
        node_refs = [str(value) for value in graph_selection.get("node_refs", [])]
        relationship_refs = [
            str(value) for value in graph_selection.get("relationship_refs", [])
        ]
        if len(node_refs) != len(set(node_refs)) or len(relationship_refs) != len(
            set(relationship_refs)
        ):
            raise ValueError("graph selection contains duplicate evidence references")
        missing_nodes = set(node_refs) - set(node_by_ref)
        missing_relationships = set(relationship_refs) - set(relationship_by_ref)
        if missing_nodes or missing_relationships:
            raise ValueError(
                "graph selection references evidence absent from the Etiq snapshot: "
                f"nodes={sorted(missing_nodes)}, relationships={sorted(missing_relationships)}"
            )
        selected_nodes = set(node_refs)
        for ref in relationship_refs:
            relationship = relationship_by_ref[ref]
            if relationship.source_ref not in selected_nodes or relationship.target_ref not in selected_nodes:
                raise ValueError(f"selected relationship has a hidden endpoint: {ref}")
        visible_evidence_by_boundary: dict[str, Any] = {}
        for boundary_id, value in graph_selection.get(
            "visible_evidence_by_boundary", {}
        ).items():
            boundary_id = _opaque_id(boundary_id, "visible_boundary_id")
            visible_nodes = [str(ref) for ref in value.get("node_refs", [])]
            visible_relationships = [
                str(ref) for ref in value.get("relationship_refs", [])
            ]
            if boundary_id not in boundary_ids:
                raise ValueError(f"graph selection contains an undeclared boundary: {boundary_id}")
            if not set(visible_nodes).issubset(selected_nodes) or not set(
                visible_relationships
            ).issubset(relationship_refs):
                raise ValueError(f"boundary visibility exceeds selected Etiq evidence: {boundary_id}")
            visible_evidence_by_boundary[boundary_id] = {
                "node_refs": visible_nodes,
                "relationship_refs": visible_relationships,
                "expanded_prefixes": [
                    [str(frame) for frame in prefix]
                    for prefix in value.get("expanded_prefixes", [])
                ],
            }
        collapsed_helpers = [
            {
                "boundary_id": _opaque_id(
                    value.get("boundary_id"), "collapsed_helper_boundary_id"
                ),
                "func_stack": [str(frame) for frame in value.get("func_stack", [])],
            }
            for value in graph_selection.get("collapsed_helpers", [])
        ]
        if any(value["boundary_id"] not in boundary_ids for value in collapsed_helpers):
            raise ValueError("collapsed helper references an undeclared boundary")
        handoffs = [
            {
                "handoff_ref": str(value.get("handoff_ref") or ""),
                "provenance_type": "controller_recorded_exact_hash_artifact_handoff",
                "upstream_job_id": _opaque_id(
                    value.get("upstream_job_id"), "handoff_upstream_job_id"
                ),
                "downstream_job_id": _opaque_id(
                    value.get("downstream_job_id"), "handoff_downstream_job_id"
                ),
                "artifact_sha256": str(value.get("artifact_sha256") or ""),
            }
            for value in graph_selection.get("handoffs", [])
        ]
        if any(
            not value["handoff_ref"]
            or assigned_job["job_id"]
            not in {value["upstream_job_id"], value["downstream_job_id"]}
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", value["artifact_sha256"])
            for value in handoffs
        ):
            raise ValueError(
                "handoffs require an incident assigned job and an exact SHA-256 artifact hash"
            )
        runtime_evidence = {
            "nodes": [review_node_payload(node_by_ref[ref]) for ref in node_refs],
            "relationships": [
                review_relationship_payload(relationship_by_ref[ref])
                for ref in relationship_refs
            ],
            "visible_evidence_by_boundary": visible_evidence_by_boundary,
            "collapsed_helpers": collapsed_helpers,
            "handoffs": handoffs,
        }
        package["runtime_evidence"] = runtime_evidence
        components["runtime-evidence.json"] = runtime_evidence

    allowed_refs = {
        "review_task",
        "top_level_input",
        "final_output",
        "assigned_job_input",
        "assigned_job_output",
        "assigned_job_stdout",
        "assigned_job_stderr",
        *(value["boundary_id"] for value in neutral_declarations),
    }
    allowed_refs.update(value["ref"] for value in package.get("prior_task_records", []))
    for job in package.get("source_bundle", []):
        allowed_refs.update(f"source:{job['job_id']}:{value['path']}" for value in job["files"])
    runtime = package.get("runtime_evidence", {})
    allowed_refs.update(value["node_ref"] for value in runtime.get("nodes", []))
    allowed_refs.update(
        value["relationship_ref"] for value in runtime.get("relationships", [])
    )
    allowed_refs.update(value["handoff_ref"] for value in runtime.get("handoffs", []))
    package["allowed_evidence_refs"] = sorted(allowed_refs)

    leaks = _leaks(package, forbidden_strings=sibling_ids)
    if leaks:
        raise ValueError(f"review package contains forbidden controller evidence: {leaks}")
    package_bytes = _encode(package)
    if len(package_bytes) > MAX_PACKAGE_BYTES:
        raise ValueError(
            f"review package exceeds {MAX_PACKAGE_BYTES} UTF-8 bytes: {len(package_bytes)}"
        )
    estimate = token_estimator(package_bytes.decode("utf-8")) if token_estimator else None
    if estimate is not None and (
        not isinstance(estimate, int) or estimate < 0 or estimate > MAX_EVIDENCE_TOKENS
    ):
        raise ValueError("token estimate is invalid or exceeds the evidence budget")
    components["review-package.json"] = package
    artifacts = []
    for path, value in components.items():
        content = _encode(value)
        artifacts.append({"path": path, "sha256": _digest(content), "utf8_bytes": len(content)})
    manifest = {
        "schema_version": "1",
        "protocol": {
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        },
        "opaque_ids": ids,
        "artifact_allowlist": artifacts,
        "package_sha256": _digest(package_bytes),
        "common_base_sha256": _digest(_encode(common_base)),
        "canonical_serialized_utf8_bytes": len(package_bytes),
        "estimated_input_tokens": estimate,
        "token_estimator": token_estimator_name if token_estimator else "unavailable",
        "separate_source_bundle": "included" if include_source_bundle else "withheld",
        "source_history": (
            "eligible"
            if include_source_bundle and evidence_mode == "history_full"
            else "withheld"
            if evidence_mode == "history_full"
            else "not_applicable"
        ),
        "graph_node_serialization_policy": GRAPH_NODE_SERIALIZATION_POLICY,
        "history_items_withheld": omitted_history,
        "restricted_setup_records": "excluded",
        "capability_flags": package["capabilities"],
    }
    return package, manifest


def materialize_branch_package(
    branch_root: Path | str,
    package: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> Path:
    requested_root = Path(branch_root).absolute()
    if any(path.exists() and path.is_symlink() for path in (requested_root, *requested_root.parents)):
        raise ValueError("branch root and its existing parents must not be symlinks")
    if requested_root.exists() and (
        not requested_root.is_dir() or any(requested_root.iterdir())
    ):
        raise FileExistsError(f"branch root is not an empty directory: {requested_root}")
    requested_root.mkdir(parents=True, exist_ok=True)
    evidence_dir = requested_root / "evidence"
    workspace_dir = requested_root / "workspace"
    evidence_dir.mkdir()
    workspace_dir.mkdir()

    components: dict[str, Any] = {
        "common-base.json": package["common_base"],
        "review-package.json": package,
    }
    for package_key, filename in (
        ("source_bundle", "source-bundle.json"),
        ("prior_task_records", "prior-task-records.json"),
        ("runtime_evidence", "runtime-evidence.json"),
    ):
        if package_key in package:
            components[filename] = package[package_key]
    allowlist = {value["path"]: value for value in manifest["artifact_allowlist"]}
    if set(components) != set(allowlist):
        raise ValueError("package components do not match the manifest allowlist")
    for name, value in components.items():
        content = _encode(value)
        expected = allowlist[name]
        if _digest(content) != expected["sha256"] or len(content) != expected["utf8_bytes"]:
            raise ValueError(f"package component does not match manifest: {name}")
        path = evidence_dir / name
        path.write_bytes(content)
        path.chmod(0o444)

    manifest_bytes = _encode(manifest)
    (evidence_dir / "package-manifest.json").write_bytes(manifest_bytes)
    (evidence_dir / "package-manifest.json").chmod(0o444)
    branch_manifest = {
        "schema_version": "1",
        "branch_id": manifest["opaque_ids"]["branch_id"],
        "package_layout": {"evidence": "evidence", "workspace": "workspace"},
        "artifact_allowlist": [
            f"evidence/{value['path']}" for value in manifest["artifact_allowlist"]
        ],
        "package_manifest_sha256": _digest(manifest_bytes),
        "process_isolation_provided": False,
        "production_sandbox_required": True,
    }
    (requested_root / "branch-manifest.json").write_bytes(_encode(branch_manifest))
    (requested_root / "branch-manifest.json").chmod(0o444)
    evidence_dir.chmod(0o555)
    workspace_dir.chmod(0o700)
    requested_root.chmod(0o700)
    return requested_root


def verify_materialized_branch(branch_root: Path | str) -> dict[str, Any]:
    root = Path(branch_root).absolute()
    branch_manifest_path = root / "branch-manifest.json"
    package_manifest_path = root / "evidence/package-manifest.json"
    for path in (branch_manifest_path, package_manifest_path):
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink() or metadata.st_nlink != 1:
            raise ValueError(f"package metadata must be an independent regular file: {path.name}")
    branch_manifest = json.loads(branch_manifest_path.read_text(encoding="utf-8"))
    package_manifest_bytes = package_manifest_path.read_bytes()
    if _digest(package_manifest_bytes) != branch_manifest["package_manifest_sha256"]:
        raise ValueError("package manifest hash changed")
    package_manifest = json.loads(package_manifest_bytes)
    expected_names = {
        str(value["path"]) for value in package_manifest["artifact_allowlist"]
    } | {"package-manifest.json"}
    actual_names = {path.name for path in (root / "evidence").iterdir()}
    if actual_names != expected_names:
        raise ValueError("evidence directory does not match the artifact allowlist")
    checked = []
    for value in package_manifest["artifact_allowlist"]:
        relative = PurePosixPath(str(value["path"]))
        path = root / "evidence" / relative
        metadata = path.lstat()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not stat.S_ISREG(metadata.st_mode)
            or path.is_symlink()
            or metadata.st_nlink != 1
        ):
            raise ValueError(f"allowlisted evidence must be an independent regular file: {relative}")
        content = path.read_bytes()
        if _digest(content) != value["sha256"] or len(content) != value["utf8_bytes"]:
            raise ValueError(f"allowlisted artifact hash changed: {relative}")
        checked.append(relative.as_posix())
    return {
        "branch_id": branch_manifest["branch_id"],
        "verified": True,
        "checked_artifacts": checked,
        "common_base_sha256": package_manifest["common_base_sha256"],
        "package_sha256": package_manifest["package_sha256"],
    }


def run_fault_operational_trial(**kwargs: Any) -> dict[str, Any]:
    """Workshop production entry point for D04/D11 operational branches."""
    from .fault_operations import run_operational_trial

    return run_operational_trial(**kwargs)


def prepare_fault_evaluation_instance(
    *,
    pipeline: GeneratedPipeline,
    fresh_chain: bool,
    clean_control: bool,
    clean_execution: Mapping[str, Any],
    selection: Any,
    validator: Callable[[GeneratedPipeline, Any], Mapping[str, Any]] | None,
    capture: Callable[[GeneratedPipeline], Any],
    fan_out: Callable[[GeneratedPipeline, Any], Any],
    restricted_root: Path,
    expected_job_ids: tuple[str, str],
    sandbox_visible_roots: Iterable[Path] = (),
    reference_chain_accepted: bool | None = None,
    clean_chain_accepted: bool | None = None,
) -> dict[str, Any]:
    """Production order: reference acceptance, injection, capture, then fan-out."""
    from .fault_injection import (
        InjectionOutcome,
        enumerate_candidates,
        finalize_injection_after_captures,
        inject_after_clean_acceptance,
        persist_restricted_injection_records,
    )

    expected_jobs = tuple(str(value) for value in expected_job_ids)
    if len(expected_jobs) != 2 or len(set(expected_jobs)) != 2:
        raise ValueError(
            "production evaluation requires exact distinct upstream and downstream job IDs"
        )
    try:
        outcome = inject_after_clean_acceptance(
            pipeline,
            reference_chain_accepted=reference_chain_accepted,
            clean_chain_accepted=clean_chain_accepted,
            fresh_chain=fresh_chain,
            clean_control=clean_control,
            clean_execution=clean_execution,
            expected_job_ids=expected_jobs,
            selection=selection,
            validator=validator,
        )
    except ValueError as error:
        candidates = []
        if selection is not None:
            try:
                candidates = [
                    {**value, "job_id": selection.job_id}
                    for value in enumerate_candidates(
                        pipeline,
                        fault_class=selection.fault_class,
                        function_name=selection.function_name,
                        parameter=selection.parameter,
                    )
                ]
            except ValueError:
                pass
        reason = str(error)
        if "/" in reason or "\\" in reason:
            reason = "candidate rejected; controller path detail withheld"
        rejected = InjectionOutcome(
            evaluation_pipeline=pipeline,
            protocol_decision={
                "schema_version": "1",
                "protocol_version": PROTOCOL_VERSION,
                "protocol_content_hash": PROTOCOL_CONTENT_HASH,
                "storage_classification": "restricted_controller_only",
                "protocol_decision": "reject_instance_before_capture",
            },
            clean_execution=dict(clean_execution),
            candidate_records=candidates,
            rejection_records=[
                {
                    "status": "rejected",
                    "reason": reason,
                    "fault_class": getattr(selection, "fault_class", None),
                    "job_id": getattr(selection, "job_id", None),
                    "function_name": getattr(selection, "function_name", None),
                    "occurrence": getattr(selection, "occurrence", None),
                }
            ],
        )
        persist_restricted_injection_records(
            rejected,
            restricted_root,
            sandbox_visible_roots=sandbox_visible_roots,
        )
        raise ValueError(reason) from None

    persist_restricted_injection_records(
        outcome,
        restricted_root,
        sandbox_visible_roots=sandbox_visible_roots,
    )
    try:
        capture_set = capture(outcome.evaluation_pipeline)
        if isinstance(capture_set, EtiqEvidenceSnapshot):
            snapshots = [capture_set]
        elif isinstance(capture_set, Mapping):
            snapshots = list(capture_set.values())
        else:
            snapshots = list(capture_set)
        if not all(isinstance(value, EtiqEvidenceSnapshot) for value in snapshots):
            raise ValueError("capture must return EtiqEvidenceSnapshot records")
        expected = list(expected_jobs)
        observed = [value.job_id for value in snapshots]
        if observed != expected:
            raise ValueError(
                "canonical evaluation must return the ordered upstream and downstream captures"
            )
        finalized = finalize_injection_after_captures(outcome, snapshots)
    except Exception as error:
        message = str(error)
        if "not captured in the frozen selected-job snapshot" in message:
            reason_code = "uncaptured_selected_job_mutation"
            reason = "mutated statement was not captured in the frozen selected-job snapshot"
        elif message == "capture must return EtiqEvidenceSnapshot records":
            reason_code = "invalid_capture_records"
            reason = message
        else:
            reason_code = "capture_or_finalization_rejected"
            reason = "capture or ground-truth finalization rejected the mutant"
        rejected = replace(
            outcome,
            rejection_records=[
                *outcome.rejection_records,
                {
                    "status": "rejected",
                    "stage": "post_capture",
                    "reason_code": reason_code,
                    "reason": reason,
                    "fault_class": getattr(selection, "fault_class", None),
                    "job_id": getattr(selection, "job_id", None),
                    "function_name": getattr(selection, "function_name", None),
                    "occurrence": getattr(selection, "occurrence", None),
                },
            ],
        )
        persist_restricted_injection_records(
            rejected,
            restricted_root,
            sandbox_visible_roots=sandbox_visible_roots,
        )
        raise ValueError(reason) from None
    persist_restricted_injection_records(
        finalized,
        restricted_root,
        sandbox_visible_roots=sandbox_visible_roots,
        require_final=not clean_control,
    )
    fanout_result = fan_out(finalized.evaluation_pipeline, capture_set)
    return {
        "outcome": finalized,
        "capture_set": capture_set,
        "fanout_result": fanout_result,
    }


def _verify_fixture(fixture: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    snapshot_data = fixture["etiq_snapshot"]
    snapshot = EtiqEvidenceSnapshot(
        snapshot_id=str(snapshot_data["snapshot_id"]),
        job_id=str(snapshot_data["job_id"]),
        run_id=str(snapshot_data["run_id"]),
        nodes=[EtiqNodeRecord(**value) for value in snapshot_data["nodes"]],
        relationships=[
            EtiqRelationshipRecord(**value) for value in snapshot_data["relationships"]
        ],
        inventories=dict(snapshot_data.get("inventories", {})),
        scan_errors=list(snapshot_data.get("scan_errors", [])),
    )
    built: list[dict[str, Any]] = []
    branch_ids = {
        str(condition["opaque_ids"]["branch_id"])
        for condition in fixture["conditions"]
    }
    for index, condition in enumerate(fixture["conditions"]):
        own_branch_id = str(condition["opaque_ids"]["branch_id"])
        package, manifest = build_fault_review_package(
            evidence_mode=condition["evidence_mode"],
            include_source_bundle=bool(condition["include_source_bundle"]),
            opaque_ids=condition["opaque_ids"],
            review_task=fixture["review_task"],
            behavioural_criteria=fixture["behavioural_criteria"],
            top_level_input=fixture["top_level_input"],
            final_output=fixture["final_output"],
            assigned_job=fixture["assigned_job"],
            declarations=fixture["declarations"],
            section=fixture["section"],
            full_chain_source=fixture["full_chain_source"],
            history_chain_id=fixture["history_chain_id"],
            sibling_branch_ids=branch_ids - {own_branch_id},
            history=fixture["history"],
            snapshot=snapshot,
            graph_selection=fixture["graph_selection"],
            token_estimator=lambda text: math.ceil(len(text.encode("utf-8")) / 4),
            token_estimator_name="fixture_utf8_bytes_div_4_v1",
        )
        root = materialize_branch_package(
            output_root / f"opaque-copy-{index + 1:02d}", package, manifest
        )
        verify_materialized_branch(root)
        built.append(
            {
                "pair": condition["pair"],
                "bundle": "included" if condition["include_source_bundle"] else "withheld",
                "package": package,
                "manifest": manifest,
                "root": root,
            }
        )

    paired_graph_identity = True
    paired_artifact_identity = True
    graph_nodes_retain_source = True
    for pair in {value["pair"] for value in built}:
        values = [value for value in built if value["pair"] == pair]
        if "runtime_evidence" not in values[0]["package"]:
            continue
        left, right = values
        paired_graph_identity &= _encode(left["package"]["runtime_evidence"]) == _encode(
            right["package"]["runtime_evidence"]
        )
        paired_artifact_identity &= [
            (value["node_ref"], value["artifact_available"], value.get("artifact_value"))
            for value in left["package"]["runtime_evidence"]["nodes"]
        ] == [
            (value["node_ref"], value["artifact_available"], value.get("artifact_value"))
            for value in right["package"]["runtime_evidence"]["nodes"]
        ]
        graph_nodes_retain_source &= all(
            value.get("source") == "PIPELINE_SOURCE_SENTINEL"
            for package in (left["package"], right["package"])
            for value in package["runtime_evidence"]["nodes"]
        )

    reviewer_sibling_names_absent = True
    branch_manifest_sibling_names_absent = True
    activity_preserved_hashes = True
    independent_regular_files = True
    for value in built:
        root = value["root"]
        branch_manifest_text = (root / "branch-manifest.json").read_text(encoding="utf-8")
        own_id = value["manifest"]["opaque_ids"]["branch_id"]
        siblings = branch_ids - {own_id}
        reviewer_artifacts_text = "\n".join(
            (root / "evidence" / artifact["path"]).read_text(encoding="utf-8")
            for artifact in value["manifest"]["artifact_allowlist"]
        )
        reviewer_sibling_names_absent &= not any(
            sibling in reviewer_artifacts_text for sibling in siblings
        )
        branch_manifest_sibling_names_absent &= not any(
            sibling in branch_manifest_text for sibling in siblings
        )
        (root / "workspace/activity.txt").write_text("branch-local activity\n", encoding="utf-8")
        activity_preserved_hashes &= verify_materialized_branch(root)["verified"]
        independent_regular_files &= all(
            stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink() and path.lstat().st_nlink == 1
            for path in (root / "evidence").iterdir()
        )

    common_hashes = {value["manifest"]["common_base_sha256"] for value in built}
    source_hashes = {
        item["sha256"]
        for value in built
        for item in value["manifest"]["artifact_allowlist"]
        if item["path"] == "source-bundle.json"
    }
    return {
        "schema_version": "1",
        "protocol_version": PROTOCOL_VERSION,
        "package_count": len(built),
        "common_base_byte_identical": len(common_hashes) == 1,
        "source_bundle_byte_identical_when_included": len(source_hashes) == 1,
        "bundle_withheld_packages_omit_source_bundle": all(
            "source_bundle" not in value["package"]
            for value in built
            if value["bundle"] == "withheld"
        ),
        "bundle_withheld_history_omits_source_records": all(
            all(record["kind"] != "source" for record in value["package"].get("prior_task_records", []))
            for value in built
            if value["bundle"] == "withheld"
        ),
        "paired_graph_evidence_byte_identical": paired_graph_identity,
        "paired_graph_artifact_eligibility_identical": paired_artifact_identity,
        "visible_graph_nodes_retain_embedded_source": graph_nodes_retain_source,
        "non_graph_packages_have_no_graph": all(
            "runtime_evidence" not in value["package"]
            for value in built
            if value["pair"] in {"current", "history"}
        ),
        "reviewer_packages_have_no_forbidden_fields_or_labels": all(
            not _leaks(
                value["package"],
                forbidden_strings=frozenset(
                    branch_ids - {value["manifest"]["opaque_ids"]["branch_id"]}
                ),
            )
            for value in built
        ),
        "reviewer_packages_name_no_sibling": reviewer_sibling_names_absent,
        "branch_manifests_name_no_sibling": branch_manifest_sibling_names_absent,
        "branch_activity_preserved_allowlisted_hashes": activity_preserved_hashes,
        "evidence_files_are_independent_regular_copies": independent_regular_files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify D02 package fixtures")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args(argv)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    print(json.dumps(_verify_fixture(fixture, args.output_root.absolute()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
