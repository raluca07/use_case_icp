from __future__ import annotations

import json
import inspect
import os
import re
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .fault_experiment import GRAPH_MODES, PROTOCOL_CONTENT_HASH, _digest, _encode, graph_selection_for_mode
from .records import (
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    GeneratedPipeline,
    jsonable,
    new_id,
)
from .repair import source_scope, validate_repair_scope
from .review import inspect_artifact, retrace_node_refs, trusted_frontier, validate_review
from .review import review_node_payload, review_relationship_payload


OPERATION_CAPABILITIES = {
    "current_run": {"inspect": False, "expand": False, "retrace": False},
    "history_full": {"inspect": False, "expand": False, "retrace": False},
    "etiq_full": {"inspect": True, "expand": False, "retrace": True},
    "etiq_selected_fixed": {"inspect": True, "expand": False, "retrace": True},
    "etiq_selected_adaptive": {"inspect": True, "expand": True, "retrace": True},
    "etiq_random_matched": {"inspect": True, "expand": False, "retrace": True},
}
OPERATION_SEQUENCE = (
    "capture",
    "package_created",
    "review",
    "citation",
    "artifact_inspection",
    "helper_expansion",
    "boundary_judgment",
    "suspect_identification",
    "receipt_validation",
    "receipt_correction",
    "localisation_frozen",
    "retrace",
    "repair_target_selection",
    "scoped_repair",
    "rerun_recapture",
    "re_review",
    "trusted_frontier_recomputed",
    "resume",
    "blocked",
)
MAX_FOLLOW_UP_CALLS = 3
MAX_RECEIPT_CORRECTION_CALLS = 2
MAX_INSPECTIONS_PER_CALL = 2
MAX_REPAIR_GENERATION_CALLS = 1
MAX_INFRASTRUCTURE_RETRIES = 2


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _completed_operations(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [event for event in events if event.get("status") == "completed"]


def _allowed_next_operations(events: Iterable[Mapping[str, Any]]) -> set[str]:
    completed = _completed_operations(events)
    if not completed:
        return {"capture"}
    last = str(completed[-1]["operation"])
    if last == "capture":
        return {"package_created"}
    if last == "package_created":
        return {"review"}
    if last == "review":
        return {"citation"}
    if last in {"citation", "artifact_inspection", "helper_expansion"}:
        return {"artifact_inspection", "helper_expansion", "boundary_judgment"}
    if last == "boundary_judgment":
        return {"suspect_identification"}
    if last == "suspect_identification":
        return {"receipt_validation"}
    if last == "receipt_validation":
        valid = bool(completed[-1].get("details", {}).get("valid"))
        if valid:
            return (
                {"trusted_frontier_recomputed"}
                if any(event["operation"] == "re_review" for event in completed)
                else {"localisation_frozen"}
            )
        return {"receipt_correction"}
    if last == "receipt_correction":
        return {"receipt_validation"}
    if last == "localisation_frozen":
        return {"retrace", "repair_target_selection"}
    if last == "retrace":
        return {"repair_target_selection"}
    if last == "repair_target_selection":
        return {"scoped_repair"}
    if last == "scoped_repair":
        return {"rerun_recapture"}
    if last == "rerun_recapture":
        return {"re_review"}
    if last == "re_review":
        return {"citation"}
    if last == "trusted_frontier_recomputed":
        return {"resume", "blocked"}
    return set()


def _validate_operation_limits(
    events: Iterable[Mapping[str, Any]],
    operation: str,
    status: str,
    details: Mapping[str, Any],
) -> None:
    if status != "completed":
        return
    completed = _completed_operations(events)
    last_re_review = max(
        (
            index
            for index, event in enumerate(completed)
            if event["operation"] == "re_review"
        ),
        default=-1,
    )
    phase_events = completed[last_re_review + 1 :]
    follow_ups = sum(
        event["operation"] in {"artifact_inspection", "helper_expansion"}
        for event in phase_events
    )
    if operation in {"artifact_inspection", "helper_expansion"} and follow_ups >= MAX_FOLLOW_UP_CALLS:
        raise ValueError("operation exceeded three follow-up calls")
    if operation == "artifact_inspection" and int(details.get("request_count") or 0) > MAX_INSPECTIONS_PER_CALL:
        raise ValueError("artifact inspection exceeded two requests in one call")
    if operation == "helper_expansion" and int(details.get("expansion_count") or 0) > 1:
        raise ValueError("helper follow-up exceeded one direct-child expansion")
    corrections = sum(event["operation"] == "receipt_correction" for event in phase_events)
    if operation == "receipt_correction" and corrections >= MAX_RECEIPT_CORRECTION_CALLS:
        raise ValueError("operation exceeded two receipt correction calls")
    repairs = sum(event["operation"] == "scoped_repair" for event in completed)
    if operation == "scoped_repair" and repairs >= MAX_REPAIR_GENERATION_CALLS:
        raise ValueError("operation exceeded one repair-generation call")


def append_operation_event(
    branch_root: Path | str,
    event_log: Path | str,
    *,
    operation: str,
    status: str,
    call_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    evidence_added: Mapping[str, Any] | None = None,
    latency_seconds: float = 0.0,
    errors: Iterable[str] = (),
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if operation not in OPERATION_SEQUENCE:
        raise ValueError(f"unknown workshop operation: {operation}")
    if status not in {"started", "completed", "rejected", "failed"}:
        raise ValueError(f"invalid operation status: {status}")
    if any(value is not None and value < 0 for value in (input_tokens, output_tokens)):
        raise ValueError("operation token counts cannot be negative")
    root = Path(branch_root).resolve()
    path = Path(event_log).absolute()
    if not _inside(root, path) or any(
        candidate.exists() and candidate.is_symlink()
        for candidate in (path, *path.parents)
        if _inside(root, candidate)
    ):
        raise ValueError("operation log must be a non-symlink path inside the branch root")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    existing = [json.loads(line) for line in existing_lines]
    if any(
        event.get("status") == "completed"
        and event.get("operation") in {"resume", "blocked"}
        for event in existing
    ):
        raise ValueError("operation log is terminal; no event may follow resume or blocked")
    _validate_operation_limits(existing, operation, status, details or {})
    terminal_failure = (
        operation == "blocked"
        and status == "completed"
        and bool((details or {}).get("terminal_failure"))
        and bool(_completed_operations(existing))
    )
    if (
        status in {"started", "completed"}
        and not terminal_failure
        and operation not in _allowed_next_operations(existing)
    ):
        raise ValueError(
            f"operation {operation} is out of sequence; allowed next: "
            f"{sorted(_allowed_next_operations(existing))}"
        )
    event = {
        "schema_version": "1",
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "sequence": len(existing_lines) + 1,
        "event_id": new_id("operation"),
        "operation": operation,
        "status": status,
        "call_id": call_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "evidence_added": dict(evidence_added or {}),
        "latency_seconds": round(max(0.0, latency_seconds), 6),
        "errors": [str(error) for error in errors],
        "details": dict(details or {}),
        "recorded_unix_ns": time.time_ns(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def bind_operation_context(
    *,
    evidence_mode: str,
    package: Mapping[str, Any],
    package_manifest: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    realized_boundaries: Iterable[Mapping[str, Any]],
    declarations: Iterable[Mapping[str, Any]],
    pipeline: GeneratedPipeline,
    handoffs: Iterable[Mapping[str, Any]],
    dependencies: Mapping[str, Iterable[str]],
    immutable_common_artifact_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    boundaries = [dict(value) for value in realized_boundaries]
    declaration_values = [dict(value) for value in declarations]
    handoff_values = [dict(value) for value in handoffs]
    dependency_values = {
        str(job_id): [str(value) for value in upstream]
        for job_id, upstream in dependencies.items()
    }
    package_sha256 = _digest(_encode(package))
    if package_manifest.get("package_sha256") != package_sha256:
        raise ValueError("operation package does not match its frozen package manifest")
    binding = {
        "schema_version": "1",
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "branch_id": str(package_manifest["opaque_ids"]["branch_id"]),
        "evidence_mode": evidence_mode,
        "package_sha256": package_sha256,
        "package_manifest_sha256": _digest(_encode(package_manifest)),
        "snapshot_sha256": _digest(_encode(jsonable(snapshot))),
        "realized_boundaries_sha256": _digest(_encode(boundaries)),
        "boundary_hashes": {
            str(value["boundary_id"]): _digest(_encode(value)) for value in boundaries
        },
        "declarations_sha256": _digest(_encode(declaration_values)),
        "pipeline_sha256": _digest(_encode(jsonable(pipeline))),
        "handoffs_sha256": _digest(_encode(handoff_values)),
        "dependencies_sha256": _digest(_encode(dependency_values)),
        "immutable_common_artifact_hashes_sha256": _digest(
            _encode(dict(immutable_common_artifact_hashes or {}))
        ),
    }
    binding["binding_sha256"] = _digest(_encode(binding))
    return binding


def verify_operation_context(
    binding: Mapping[str, Any],
    *,
    evidence_mode: str,
    package: Mapping[str, Any],
    package_manifest: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    realized_boundaries: Iterable[Mapping[str, Any]],
    declarations: Iterable[Mapping[str, Any]],
    pipeline: GeneratedPipeline,
    handoffs: Iterable[Mapping[str, Any]],
    dependencies: Mapping[str, Iterable[str]],
    immutable_common_artifact_hashes: Mapping[str, str] | None = None,
) -> None:
    supplied = dict(binding)
    supplied_hash = supplied.pop("binding_sha256", None)
    if supplied_hash != _digest(_encode(supplied)):
        raise ValueError("operation context binding hash verification failed")
    expected = bind_operation_context(
        evidence_mode=evidence_mode,
        package=package,
        package_manifest=package_manifest,
        snapshot=snapshot,
        realized_boundaries=realized_boundaries,
        declarations=declarations,
        pipeline=pipeline,
        handoffs=handoffs,
        dependencies=dependencies,
        immutable_common_artifact_hashes=immutable_common_artifact_hashes,
    )
    if dict(binding) != expected:
        raise ValueError("operation inputs do not match the immutable branch context")


def _verify_binding_hash(binding: Mapping[str, Any]) -> None:
    value = dict(binding)
    digest = value.pop("binding_sha256", None)
    if digest != _digest(_encode(value)) or value.get("protocol_content_hash") != PROTOCOL_CONTENT_HASH:
        raise ValueError("operation context binding hash verification failed")


def _require_bound_value(binding: Mapping[str, Any], field: str, value: Any) -> None:
    _verify_binding_hash(binding)
    if binding.get(field) != _digest(_encode(jsonable(value))):
        raise ValueError(f"{field} does not match the immutable branch context")


def _require_bound_boundary(binding: Mapping[str, Any], boundary: Mapping[str, Any]) -> None:
    _verify_binding_hash(binding)
    boundary_id = str(boundary["boundary_id"])
    if binding.get("boundary_hashes", {}).get(boundary_id) != _digest(_encode(boundary)):
        raise ValueError("realized boundary does not match the immutable branch context")


def validate_citations(
    package: Mapping[str, Any], citations: Iterable[str], *, binding: Mapping[str, Any]
) -> list[str]:
    _require_bound_value(binding, "package_sha256", package)
    refs = [str(ref) for ref in citations]
    unknown = set(refs) - {str(ref) for ref in package.get("allowed_evidence_refs", [])}
    if unknown:
        raise ValueError(f"citations reference evidence outside the visible package: {sorted(unknown)}")
    return refs


def inspect_visible_artifacts(
    evidence_mode: str,
    package: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    requests: Iterable[Mapping[str, Any]],
    *,
    binding: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _require_bound_value(binding, "package_sha256", package)
    _require_bound_value(binding, "snapshot_sha256", snapshot)
    if evidence_mode not in GRAPH_MODES:
        raise ValueError(f"{evidence_mode} cannot inspect graph artifacts")
    values = list(requests)
    if len(values) > 2:
        raise ValueError("at most two artifact inspections are allowed per call")
    visible = {
        str(node["node_ref"]): node
        for node in package.get("runtime_evidence", {}).get("nodes", [])
    }
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    results = []
    for request in values:
        ref = str(request.get("node_ref") or "")
        if ref not in visible or ref not in node_by_ref:
            raise ValueError(f"artifact inspection must target a currently visible node: {ref}")
        if not visible[ref].get("artifact_available"):
            raise ValueError(f"visible node has no inspectable captured artifact: {ref}")
        results.append(inspect_artifact(node_by_ref[ref], request))
    return results


def expand_direct_child(
    evidence_mode: str,
    snapshot: EtiqEvidenceSnapshot,
    realized_boundaries: Iterable[Mapping[str, Any]],
    *,
    binding: Mapping[str, Any],
    package: Mapping[str, Any],
    boundary_id: str,
    requested_prefix: Iterable[str],
    expanded_prefixes_by_boundary: Mapping[str, Iterable[Iterable[str]]] | None = None,
    handoffs: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    if evidence_mode != "etiq_selected_adaptive":
        raise ValueError(f"{evidence_mode} cannot expand helper evidence")
    _require_bound_value(binding, "package_sha256", package)
    _require_bound_value(binding, "snapshot_sha256", snapshot)
    boundaries = [dict(boundary) for boundary in realized_boundaries]
    _require_bound_value(binding, "realized_boundaries_sha256", boundaries)
    assigned = set(package["common_base"]["section"]["assigned_boundary_ids"])
    if boundary_id not in assigned:
        raise ValueError("helper expansion must target a currently assigned boundary")
    requested = [str(frame) for frame in requested_prefix]
    collapsed = {
        (
            str(value.get("boundary_id")),
            tuple(str(frame) for frame in value.get("func_stack", [])),
        )
        for value in package.get("runtime_evidence", {}).get("collapsed_helpers", [])
    }
    if (boundary_id, tuple(requested)) not in collapsed:
        raise ValueError("helper expansion must target a currently visible collapsed child")
    current = {
        str(key): [list(prefix) for prefix in prefixes]
        for key, prefixes in (expanded_prefixes_by_boundary or {}).items()
    }
    current.setdefault(boundary_id, []).append(requested)
    return graph_selection_for_mode(
        evidence_mode,
        snapshot,
        boundaries,
        handoffs=handoffs,
        expanded_prefixes_by_boundary=current,
    )


def freeze_localisation(
    evidence_mode: str,
    package: Mapping[str, Any],
    *,
    top_suspect_boundary_id: str,
    suspect_node_ref: str | None,
    citations: Iterable[str],
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    _require_bound_value(binding, "package_sha256", package)
    assigned = set(package["common_base"]["section"]["assigned_boundary_ids"])
    if top_suspect_boundary_id not in assigned:
        raise ValueError("top suspect must be one assigned boundary")
    validated_citations = validate_citations(package, citations, binding=binding)
    visible_nodes = {
        str(node["node_ref"])
        for node in package.get("runtime_evidence", {}).get("nodes", [])
    }
    if evidence_mode in GRAPH_MODES:
        if suspect_node_ref is not None and suspect_node_ref not in visible_nodes:
            raise ValueError("graph suspect must be currently visible")
    elif suspect_node_ref is not None:
        raise ValueError("non-graph conditions cannot identify graph nodes")
    return {
        "localisation_id": new_id("localisation"),
        "frozen": True,
        "top_suspect_boundary_id": top_suspect_boundary_id,
        "suspect_node_ref": suspect_node_ref,
        "citation_refs": validated_citations,
    }


def retrace_frozen_localisation(
    evidence_mode: str,
    localisation: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    boundary: Mapping[str, Any],
    *,
    binding: Mapping[str, Any],
) -> list[str]:
    _require_bound_value(binding, "snapshot_sha256", snapshot)
    _require_bound_boundary(binding, boundary)
    if evidence_mode not in GRAPH_MODES:
        raise ValueError(f"{evidence_mode} cannot retrace graph relationships")
    if not localisation.get("frozen"):
        raise ValueError("localisation must be frozen before retrace")
    if str(localisation.get("top_suspect_boundary_id")) != str(boundary["boundary_id"]):
        raise ValueError("retrace boundary must be the branch's frozen top suspect")
    start = str(localisation.get("suspect_node_ref") or "")
    allowed_nodes = {str(ref) for ref in boundary["node_refs"]}
    allowed_relationships = {str(ref) for ref in boundary["relationship_refs"]}
    if start not in allowed_nodes:
        raise ValueError("retrace must start from the branch's visible suspect node")
    restricted = EtiqEvidenceSnapshot(
        snapshot_id=snapshot.snapshot_id,
        job_id=snapshot.job_id,
        run_id=snapshot.run_id,
        nodes=[node for node in snapshot.nodes if node.node_ref in allowed_nodes],
        relationships=[
            relationship
            for relationship in snapshot.relationships
            if relationship.relationship_ref in allowed_relationships
            and relationship.source_ref in allowed_nodes
            and relationship.target_ref in allowed_nodes
        ],
        inventories={},
        scan_errors=[],
    )
    return retrace_node_refs(restricted, [start])


def select_own_repair_target(
    pipeline: GeneratedPipeline,
    localisation: Mapping[str, Any],
    declarations: Iterable[Mapping[str, Any]],
    *,
    binding: Mapping[str, Any],
    retrace_refs: Iterable[str] = (),
) -> dict[str, Any]:
    declaration_values = [dict(value) for value in declarations]
    _require_bound_value(binding, "pipeline_sha256", pipeline)
    _require_bound_value(binding, "declarations_sha256", declaration_values)
    if not localisation.get("frozen"):
        raise ValueError("repair target selection requires frozen localisation")
    boundary_id = str(localisation["top_suspect_boundary_id"])
    matches = [value for value in declaration_values if str(value["boundary_id"]) == boundary_id]
    if len(matches) != 1:
        raise ValueError("frozen top suspect does not resolve to one declared boundary")
    target = source_scope(
        pipeline,
        function_name=str(matches[0]["function_name"]),
        mode="boundary",
    )
    target.update(
        {
            "boundary_id": boundary_id,
            "suspect_node_ref": localisation.get("suspect_node_ref"),
            "retrace_node_refs": [str(ref) for ref in retrace_refs],
            "selection_reason": "condition-owned frozen top suspect; no oracle fallback",
        }
    )
    return target


def validate_boundary_sized_repair(
    original: GeneratedPipeline,
    replacement: GeneratedPipeline,
    target: Mapping[str, Any],
) -> None:
    if target.get("effective_mode") != "boundary":
        raise ValueError("workshop repairs must use equal boundary-sized edit permission")
    validate_repair_scope(original, replacement, dict(target))


def downstream_rerun_job_ids(
    repaired_job_id: str,
    dependencies: Mapping[str, Iterable[str]],
) -> list[str]:
    all_jobs = set(dependencies)
    all_jobs.update(str(dep) for values in dependencies.values() for dep in values)
    if repaired_job_id not in all_jobs:
        raise ValueError(f"repaired job is absent from the frozen chain: {repaired_job_id}")
    selected = {repaired_job_id}
    changed = True
    while changed:
        changed = False
        for job_id, upstream in dependencies.items():
            if job_id not in selected and selected.intersection(str(value) for value in upstream):
                selected.add(job_id)
                changed = True
    ordered: list[str] = []
    remaining = set(selected)
    while remaining:
        ready = sorted(
            job_id
            for job_id in remaining
            if not (set(map(str, dependencies.get(job_id, ()))) & remaining)
        )
        if not ready:
            raise ValueError("frozen chain dependencies contain a cycle")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def two_job_suffix_rerun_job_ids(
    repaired_job_id: str,
    *,
    upstream_job_id: str,
    downstream_job_id: str,
    dependencies: Mapping[str, Iterable[str]],
) -> list[str]:
    """Freeze the protocol-1.3.1 dependency suffix without changing D04's generic helper."""
    expected = {
        str(upstream_job_id): [],
        str(downstream_job_id): [str(upstream_job_id)],
    }
    normalized = {
        str(job_id): [str(value) for value in values]
        for job_id, values in dependencies.items()
    }
    if normalized != expected:
        raise ValueError("protocol 1.3.1 requires the exact two-job dependency graph")
    return downstream_rerun_job_ids(repaired_job_id, normalized)


def require_fresh_branch_session(
    branch_root: Path | str,
    *,
    invocation_store: Path | str,
    working_directory: Path | str,
    fresh_session: bool,
) -> None:
    root = Path(branch_root).resolve()
    if not fresh_session:
        raise ValueError("review and repair operations require a fresh non-resumed session")
    if not _inside(root, Path(invocation_store)) or not _inside(root, Path(working_directory)):
        raise ValueError("invocation storage and cwd must remain inside the current branch")


def require_production_process_sandbox(
    branch_root: Path | str,
    isolation_gate: Mapping[str, Any] | None,
    *,
    production_launcher: Callable[..., Mapping[str, Any]],
    expected_gate_sha256: str,
    expected_launch_policy_sha256: str,
) -> None:
    """Require D09's exact signed production launcher; dictionaries alone never pass."""
    root = Path(branch_root).resolve()
    if not root.is_dir():
        raise RuntimeError("production branch root is unavailable")
    verify_signed_isolation_gate(
        isolation_gate,
        production_launcher,
        expected_gate_sha256=expected_gate_sha256,
        expected_launch_policy_sha256=expected_launch_policy_sha256,
    )


def verify_signed_isolation_gate(
    gate: Mapping[str, Any] | None,
    production_launcher: Callable[..., Mapping[str, Any]],
    *,
    expected_gate_sha256: str,
    expected_launch_policy_sha256: str,
) -> None:
    if not gate or gate.get("status") != "passed":
        raise RuntimeError("current signed Tester production-isolation gate is required")
    gate_value = dict(gate)
    signature = str(gate_value.pop("tester_signature", ""))
    if signature != _digest(_encode(gate_value)):
        raise RuntimeError("Tester isolation-gate signature verification failed")
    if _digest(_encode(gate)) != expected_gate_sha256:
        raise RuntimeError("Tester isolation-gate artifact hash is stale")
    launcher_hash = production_launcher_sha256(production_launcher)
    if str(getattr(production_launcher, "launcher_sha256", "")) != launcher_hash:
        raise RuntimeError("production launcher hash does not match its executable source")
    policy_hash = str(getattr(production_launcher, "launch_policy_sha256", ""))
    backend = str(getattr(production_launcher, "sandbox_backend", ""))
    backend_version = str(getattr(production_launcher, "sandbox_backend_version", ""))
    if not getattr(production_launcher, "production_launcher", False):
        raise RuntimeError("mock or simulated launchers cannot run operational trials")
    expected = {
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "production_launcher_sha256": launcher_hash,
        "launch_policy_sha256": expected_launch_policy_sha256,
        "sandbox_backend": backend,
        "sandbox_backend_version": backend_version,
    }
    for field, value in expected.items():
        if not value or gate.get(field) != value:
            raise RuntimeError(f"Tester isolation gate has a stale {field} binding")
    if policy_hash != expected_launch_policy_sha256:
        raise RuntimeError("production launcher does not match the frozen launch policy")
    if not str(gate.get("tester_identity") or "") or not str(gate.get("signed_at") or ""):
        raise RuntimeError("Tester isolation gate lacks identity or timestamp")
    try:
        datetime.fromisoformat(str(gate["signed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("Tester isolation gate has an invalid timestamp") from exc
    probes = list(gate.get("probe_results", []))
    if not probes or any(
        probe.get("status") != "passed" or probe.get("skipped") is True
        for probe in probes
    ):
        raise RuntimeError("Tester isolation gate contains failed or skipped probes")


def production_launcher_sha256(production_launcher: Callable[..., Any]) -> str:
    try:
        source = inspect.getsource(production_launcher)
    except (OSError, TypeError) as exc:
        raise RuntimeError("production launcher source is unavailable for hashing") from exc
    return _digest(source.encode("utf-8"))


def _usage(result: Mapping[str, Any]) -> tuple[int | None, int | None, float]:
    usage = result.get("usage", {})
    return (
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        float(usage.get("latency_seconds") or 0.0),
    )


def _launch_with_retries(
    production_launcher: Callable[..., Mapping[str, Any]],
    *,
    branch_root: Path,
    call_class: str,
    request: Mapping[str, Any],
    gate: Mapping[str, Any],
    expected_gate_sha256: str,
    expected_launch_policy_sha256: str,
) -> dict[str, Any]:
    last_error = ""
    frozen_request = deepcopy(dict(request))
    retry_identity_sha256 = _digest(_encode(frozen_request))
    event_operation = {
        "initial_review": "review",
        "receipt_correction": "receipt_correction",
        "repair": "scoped_repair",
        "rerun_recapture": "rerun_recapture",
        "re_review": "re_review",
    }.get(call_class, str(request.get("event_operation") or "review"))
    for attempt in range(MAX_INFRASTRUCTURE_RETRIES + 1):
        verify_signed_isolation_gate(
            gate,
            production_launcher,
            expected_gate_sha256=expected_gate_sha256,
            expected_launch_policy_sha256=expected_launch_policy_sha256,
        )
        attempt_request = deepcopy(frozen_request)
        result = dict(production_launcher(call_class, branch_root, attempt_request))
        if _digest(_encode(attempt_request)) != retry_identity_sha256:
            raise RuntimeError("production launcher mutated the frozen retry identity")
        reported_identity = result.get("retry_identity_sha256")
        if reported_identity is not None and reported_identity != retry_identity_sha256:
            raise RuntimeError("production launcher changed the retry identity")
        if result.get("status") != "infrastructure_failure":
            require_fresh_branch_session(
                branch_root,
                invocation_store=str(result["invocation_store"]),
                working_directory=str(result["working_directory"]),
                fresh_session=bool(result.get("fresh_session")),
            )
            result["infrastructure_attempt"] = attempt + 1
            result["retry_identity_sha256"] = retry_identity_sha256
            return result
        last_error = str(result.get("error") or "infrastructure failure")
        append_operation_event(
            branch_root,
            branch_root / "workspace/operation-events.jsonl",
            operation=event_operation,
            status="failed",
            call_id=str(result.get("call_id") or ""),
            errors=[last_error],
            details={
                "infrastructure_attempt": attempt + 1,
                "retry_identity_sha256": retry_identity_sha256,
            },
        )
    raise RuntimeError(
        f"{call_class} failed after the initial call and two infrastructure retries: {last_error}"
    )


def _rebind_visible_package(
    binding: Mapping[str, Any], old_package: Mapping[str, Any], new_package: Mapping[str, Any]
) -> dict[str, Any]:
    _require_bound_value(binding, "package_sha256", old_package)
    updated = dict(binding)
    updated["parent_binding_sha256"] = str(binding["binding_sha256"])
    updated["package_sha256"] = _digest(_encode(new_package))
    updated.pop("binding_sha256", None)
    updated["binding_sha256"] = _digest(_encode(updated))
    return updated


def _package_with_graph_selection(
    package: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    value = deepcopy(dict(package))
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    runtime = value["runtime_evidence"]
    runtime["nodes"] = [
        review_node_payload(node_by_ref[ref]) for ref in selection["node_refs"]
    ]
    runtime["relationships"] = [
        review_relationship_payload(relationship_by_ref[ref])
        for ref in selection["relationship_refs"]
    ]
    runtime["visible_evidence_by_boundary"] = deepcopy(
        selection["visible_evidence_by_boundary"]
    )
    runtime["collapsed_helpers"] = deepcopy(selection["collapsed_helpers"])
    allowed = set(value["allowed_evidence_refs"])
    allowed.update(selection["node_refs"])
    allowed.update(selection["relationship_refs"])
    value["allowed_evidence_refs"] = sorted(allowed)
    return value


def recalculate_exact_hash_handoffs(
    job_artifacts: Mapping[str, Mapping[str, Any]],
    dependencies: Mapping[str, Iterable[str]],
    rerun_job_ids: Iterable[str],
    *,
    immutable_upstream_artifact_hashes: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    rerun = set(map(str, rerun_job_ids))
    frozen = {
        str(job_id): str(artifact_hash)
        for job_id, artifact_hash in (immutable_upstream_artifact_hashes or {}).items()
    }
    handoffs = []
    for downstream in sorted(rerun):
        inputs = job_artifacts.get(downstream, {}).get("inputs_by_upstream", {})
        for upstream in map(str, dependencies.get(downstream, ())):
            if upstream not in job_artifacts or upstream not in inputs:
                raise ValueError(f"rerun is missing handoff artifacts: {upstream} -> {downstream}")
            output_hash = _digest(_encode(job_artifacts[upstream]["output"]))
            if upstream not in rerun:
                if upstream not in frozen:
                    raise ValueError(
                        f"immutable common capture lacks upstream artifact hash: {upstream}"
                    )
                if output_hash != frozen[upstream]:
                    raise ValueError(
                        f"unchanged upstream artifact differs from immutable common capture: {upstream}"
                    )
            input_hash = _digest(_encode(inputs[upstream]))
            if output_hash != input_hash:
                raise ValueError(f"rerun handoff hash mismatch: {upstream} -> {downstream}")
            handoffs.append(
                {
                    "handoff_ref": f"handoff:{upstream}:{downstream}:{output_hash[7:23]}",
                    "provenance_type": "controller_recorded_exact_hash_artifact_handoff",
                    "upstream_job_id": upstream,
                    "downstream_job_id": downstream,
                    "artifact_sha256": output_hash,
                }
            )
    return handoffs


def _immutable_hashes_from_frozen_handoffs(
    handoffs: Iterable[Mapping[str, Any]],
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for handoff in handoffs:
        upstream = str(handoff.get("upstream_job_id") or "")
        artifact_hash = str(handoff.get("artifact_sha256") or "")
        if not upstream or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_hash):
            raise ValueError("frozen common-capture handoff has invalid artifact identity")
        if upstream in hashes and hashes[upstream] != artifact_hash:
            raise ValueError(f"frozen common capture has conflicting hashes for {upstream}")
        hashes[upstream] = artifact_hash
    return hashes


def _snapshot_from_payload(payload: Mapping[str, Any]) -> EtiqEvidenceSnapshot:
    try:
        return EtiqEvidenceSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            job_id=str(payload["job_id"]),
            run_id=str(payload["run_id"]),
            nodes=[EtiqNodeRecord(**dict(value)) for value in payload["nodes"]],
            relationships=[
                EtiqRelationshipRecord(**dict(value)) for value in payload["relationships"]
            ],
            inventories=dict(payload.get("inventories", {})),
            scan_errors=list(payload.get("scan_errors", [])),
            created_at=str(payload["created_at"]),
            schema_version=str(payload.get("schema_version", "1")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("rerun capture contains an invalid assigned-job Etiq snapshot") from exc


def _verify_same_condition_manifest(
    original: Mapping[str, Any], rebuilt: Mapping[str, Any]
) -> None:
    for field in (
        "opaque_ids",
        "separate_source_bundle",
        "source_history",
        "graph_node_serialization_policy",
        "capability_flags",
    ):
        if rebuilt.get(field) != original.get(field):
            raise ValueError(f"rebuilt review package changed frozen condition field: {field}")


def _verify_package_uses_snapshot(
    package: Mapping[str, Any], snapshot: EtiqEvidenceSnapshot
) -> None:
    node_by_ref = {node.node_ref: review_node_payload(node) for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: review_relationship_payload(relationship)
        for relationship in snapshot.relationships
    }
    runtime = package.get("runtime_evidence", {})
    for node in runtime.get("nodes", []):
        ref = str(node.get("node_ref") or "")
        if ref not in node_by_ref or dict(node) != node_by_ref[ref]:
            raise ValueError("rebuilt review package contains stale snapshot node evidence")
    for relationship in runtime.get("relationships", []):
        ref = str(relationship.get("relationship_ref") or "")
        if ref not in relationship_by_ref or dict(relationship) != relationship_by_ref[ref]:
            raise ValueError("rebuilt review package contains stale snapshot relationship evidence")


def _verify_repaired_source_bundle(
    *,
    package: Mapping[str, Any],
    package_manifest: Mapping[str, Any],
    replacement: GeneratedPipeline,
    repaired_job_id: str,
) -> None:
    source_status = package_manifest.get("separate_source_bundle")
    if source_status == "withheld":
        if "source_bundle" in package:
            raise ValueError("source-withheld re-review package exposes a source bundle")
        return
    if source_status != "included":
        raise ValueError("rebuilt review package has an invalid source-bundle configuration")
    source_bundle = package.get("source_bundle")
    if not isinstance(source_bundle, list):
        raise ValueError("source-present re-review package lacks its source bundle")
    assigned_sources = [
        value for value in source_bundle
        if isinstance(value, Mapping) and str(value.get("job_id")) == repaired_job_id
    ]
    if len(assigned_sources) != 1:
        raise ValueError("source bundle must contain exactly one repaired-job source entry")
    actual_files = assigned_sources[0].get("files")
    expected_files = [jsonable(value) for value in replacement.files]
    if actual_files != expected_files:
        raise ValueError("source bundle does not contain the exact replacement pipeline")
    source_artifacts = [
        value for value in package_manifest.get("artifact_allowlist", [])
        if isinstance(value, Mapping) and value.get("path") == "source-bundle.json"
    ]
    encoded = _encode(source_bundle)
    if len(source_artifacts) != 1 or source_artifacts[0] != {
        "path": "source-bundle.json",
        "sha256": _digest(encoded),
        "utf8_bytes": len(encoded),
    }:
        raise ValueError("source bundle does not match its rebuilt package manifest")


def _verify_rebuilt_graph_selection(
    *,
    evidence_mode: str,
    package: Mapping[str, Any],
    package_manifest: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    boundaries: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    rebuilt: Mapping[str, Any],
) -> None:
    random_manifests = rebuilt.get("frozen_random_by_boundary")
    if evidence_mode == "etiq_random_matched" and not isinstance(random_manifests, Mapping):
        raise ValueError("random re-review requires its frozen projection manifests")
    expected = graph_selection_for_mode(
        evidence_mode,
        snapshot,
        boundaries,
        handoffs=handoffs,
        frozen_random_by_boundary=random_manifests,
        random_instance_id=str(package_manifest["opaque_ids"]["instance_id"]),
    )
    if expected is None:
        if "runtime_evidence" in package:
            raise ValueError("rebuilt non-graph condition contains graph evidence")
        return
    runtime = package.get("runtime_evidence", {})
    actual = {
        "node_refs": sorted(str(node.get("node_ref")) for node in runtime.get("nodes", [])),
        "relationship_refs": sorted(
            str(value.get("relationship_ref"))
            for value in runtime.get("relationships", [])
        ),
        "visible_evidence_by_boundary": runtime.get("visible_evidence_by_boundary", {}),
        "collapsed_helpers": runtime.get("collapsed_helpers", []),
        "handoffs": [
            {
                field: value.get(field)
                for field in (
                    "handoff_ref",
                    "upstream_job_id",
                    "downstream_job_id",
                    "artifact_sha256",
                )
            }
            for value in runtime.get("handoffs", [])
        ],
    }
    selected = {
        "node_refs": sorted(map(str, expected["node_refs"])),
        "relationship_refs": sorted(map(str, expected["relationship_refs"])),
        "visible_evidence_by_boundary": expected["visible_evidence_by_boundary"],
        "collapsed_helpers": expected["collapsed_helpers"],
        "handoffs": [
            {
                field: value.get(field)
                for field in (
                    "handoff_ref",
                    "upstream_job_id",
                    "downstream_job_id",
                    "artifact_sha256",
                )
            }
            for value in expected.get("handoffs", [])
        ],
    }
    if actual != selected:
        raise ValueError("rebuilt review package does not match the frozen evidence condition")


def _blocked_result(
    root: Path,
    log: Path,
    *,
    stage: str,
    error: Exception | str,
    binding_sha256: str | None = None,
    **partial: Any,
) -> dict[str, Any]:
    message = str(error)
    append_operation_event(
        root,
        log,
        operation="blocked",
        status="completed",
        errors=[message],
        details={
            "terminal_failure": True,
            "failure_stage": stage,
            "reason": message,
        },
    )
    return {
        "status": "blocked",
        "outcome": {
            "outcome": "blocked",
            "failure_stage": stage,
            "reason": message,
            "conversation_resumed": False,
        },
        "operation_event_log": str(log),
        "operation_event_log_sha256": _digest(log.read_bytes()),
        "binding_sha256": binding_sha256,
        **partial,
    }


def _run_review_evidence_phase(
    *,
    root: Path,
    log: Path,
    evidence_mode: str,
    response: Mapping[str, Any],
    package: Mapping[str, Any],
    binding: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    boundaries: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    production_launcher: Callable[..., Mapping[str, Any]],
    isolation_gate: Mapping[str, Any],
    isolation_gate_sha256: str,
    launch_policy_sha256: str,
    phase: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    current_response = dict(response)
    current_package = deepcopy(dict(package))
    current_binding = dict(binding)
    citations = validate_citations(
        current_package, current_response.get("citations", []), binding=current_binding
    )
    append_operation_event(
        root,
        log,
        operation="citation",
        status="completed",
        details={"citation_refs": citations, "phase": phase},
    )
    expanded: dict[str, list[list[str]]] = {}
    pending = list(current_response.get("follow_up_requests", []))
    current_response["follow_up_requests"] = []
    follow_up_calls = 0
    while pending:
        if follow_up_calls >= MAX_FOLLOW_UP_CALLS:
            raise ValueError("review exceeded three operation follow-up calls")
        request = pending.pop(0)
        if not isinstance(request, Mapping):
            raise ValueError("operation follow-up request must be an object")
        operation = str(request.get("operation"))
        if operation == "artifact_inspection":
            evidence = inspect_visible_artifacts(
                evidence_mode,
                current_package,
                snapshot,
                request.get("requests", []),
                binding=current_binding,
            )
        elif operation == "helper_expansion":
            prefixes = list(request.get("prefixes", []))
            if len(prefixes) != 1:
                raise ValueError("one helper expansion is allowed per follow-up call")
            boundary_id = str(request["boundary_id"])
            selection = expand_direct_child(
                evidence_mode,
                snapshot,
                boundaries,
                binding=current_binding,
                package=current_package,
                boundary_id=boundary_id,
                requested_prefix=prefixes[0],
                expanded_prefixes_by_boundary=expanded,
                handoffs=handoffs,
            )
            expanded.setdefault(boundary_id, []).append(list(prefixes[0]))
            new_package = _package_with_graph_selection(current_package, snapshot, selection)
            current_binding = _rebind_visible_package(
                current_binding, current_package, new_package
            )
            current_package = new_package
            evidence = {
                "node_refs": selection["node_refs"],
                "relationship_refs": selection["relationship_refs"],
            }
        else:
            raise ValueError(f"illegal operation request: {operation}")

        follow_up = _launch_with_retries(
            production_launcher,
            branch_root=root,
            call_class="operation_follow_up",
            request={
                "package": current_package,
                "binding_sha256": current_binding["binding_sha256"],
                "evidence_added": evidence,
                "event_operation": operation,
                "phase": phase,
            },
            gate=isolation_gate,
            expected_gate_sha256=isolation_gate_sha256,
            expected_launch_policy_sha256=launch_policy_sha256,
        )
        follow_up_calls += 1
        input_tokens, output_tokens, latency = _usage(follow_up)
        append_operation_event(
            root,
            log,
            operation=operation,
            status="completed",
            call_id=str(follow_up.get("call_id") or ""),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency,
            evidence_added={
                "node_count": len(evidence.get("node_refs", []))
                if isinstance(evidence, Mapping)
                else 0,
                "result_count": len(evidence) if isinstance(evidence, list) else 1,
            },
            details={
                "request_count": len(request.get("requests", []))
                if operation == "artifact_inspection"
                else 0,
                "expansion_count": 1 if operation == "helper_expansion" else 0,
                "phase": phase,
                "follow_up_call": follow_up_calls,
            },
        )
        pending.extend(list(follow_up.get("follow_up_requests", [])))
        for key in (
            "citations",
            "top_suspect_boundary_id",
            "suspect_node_ref",
            "receipt",
        ):
            if key in follow_up:
                current_response[key] = follow_up[key]
        validate_citations(
            current_package,
            current_response.get("citations", citations),
            binding=current_binding,
        )

    append_operation_event(
        root, log, operation="boundary_judgment", status="completed", details={"phase": phase}
    )
    append_operation_event(
        root,
        log,
        operation="suspect_identification",
        status="completed",
        details={
            "boundary_id": current_response.get("top_suspect_boundary_id"),
            "node_ref": current_response.get("suspect_node_ref"),
            "phase": phase,
        },
    )
    return current_response, current_package, current_binding


def run_operational_trial(
    *,
    branch_root: Path | str,
    evidence_mode: str,
    package: Mapping[str, Any],
    package_manifest: Mapping[str, Any],
    snapshot: EtiqEvidenceSnapshot,
    realized_boundaries: Iterable[Mapping[str, Any]],
    declarations: Iterable[Mapping[str, Any]],
    pipeline: GeneratedPipeline,
    handoffs: Iterable[Mapping[str, Any]],
    dependencies: Mapping[str, Iterable[str]],
    repaired_job_id: str,
    production_launcher: Callable[..., Mapping[str, Any]],
    isolation_gate: Mapping[str, Any],
    isolation_gate_sha256: str,
    launch_policy_sha256: str,
    receipt_validator: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
    rebuild_condition_package: Callable[..., Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute the complete hash-bound review-to-resume workshop trial."""
    root = Path(branch_root).resolve()
    log = root / "workspace/operation-events.jsonl"
    boundaries = [dict(value) for value in realized_boundaries]
    declaration_values = [dict(value) for value in declarations]
    handoff_values = [dict(value) for value in handoffs]
    dependency_values = {
        str(job_id): [str(value) for value in upstream]
        for job_id, upstream in dependencies.items()
    }
    immutable_hashes = _immutable_hashes_from_frozen_handoffs(handoff_values)
    current_package = deepcopy(dict(package))
    current_binding = bind_operation_context(
        evidence_mode=evidence_mode,
        package=current_package,
        package_manifest=package_manifest,
        snapshot=snapshot,
        realized_boundaries=boundaries,
        declarations=declaration_values,
        pipeline=pipeline,
        handoffs=handoff_values,
        dependencies=dependency_values,
        immutable_common_artifact_hashes=immutable_hashes,
    )
    verify_operation_context(
        current_binding,
        evidence_mode=evidence_mode,
        package=current_package,
        package_manifest=package_manifest,
        snapshot=snapshot,
        realized_boundaries=boundaries,
        declarations=declaration_values,
        pipeline=pipeline,
        handoffs=handoff_values,
        dependencies=dependency_values,
        immutable_common_artifact_hashes=immutable_hashes,
    )
    append_operation_event(
        root, log, operation="capture", status="completed",
        details={"snapshot_sha256": current_binding["snapshot_sha256"]},
    )
    append_operation_event(
        root, log, operation="package_created", status="completed",
        evidence_added={"utf8_bytes": len(_encode(current_package))},
        details={"package_sha256": current_binding["package_sha256"]},
    )

    try:
        response = _launch_with_retries(
            production_launcher,
            branch_root=root,
            call_class="initial_review",
            request={"package": current_package, "binding_sha256": current_binding["binding_sha256"]},
            gate=isolation_gate,
            expected_gate_sha256=isolation_gate_sha256,
            expected_launch_policy_sha256=launch_policy_sha256,
        )
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="initial_review", error=exc,
            binding_sha256=current_binding["binding_sha256"],
        )
    input_tokens, output_tokens, latency = _usage(response)
    append_operation_event(
        root, log, operation="review", status="completed",
        call_id=str(response.get("call_id") or ""), input_tokens=input_tokens,
        output_tokens=output_tokens, latency_seconds=latency,
    )
    try:
        response, current_package, current_binding = _run_review_evidence_phase(
            root=root,
            log=log,
            evidence_mode=evidence_mode,
            response=response,
            package=current_package,
            binding=current_binding,
            snapshot=snapshot,
            boundaries=boundaries,
            handoffs=handoff_values,
            production_launcher=production_launcher,
            isolation_gate=isolation_gate,
            isolation_gate_sha256=isolation_gate_sha256,
            launch_policy_sha256=launch_policy_sha256,
            phase="faulty_run",
        )
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="review_evidence", error=exc,
            binding_sha256=current_binding["binding_sha256"],
        )
    citations = list(response.get("citations", []))
    try:
        validation = dict(receipt_validator(response, current_package))
    except (KeyError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="receipt_validation", error=exc,
            binding_sha256=current_binding["binding_sha256"],
        )
    corrections = 0
    while True:
        append_operation_event(
            root, log, operation="receipt_validation", status="completed",
            details={"valid": bool(validation.get("valid")), "errors": validation.get("errors", [])},
        )
        if validation.get("valid"):
            break
        if corrections >= MAX_RECEIPT_CORRECTION_CALLS:
            return _blocked_result(
                root, log, stage="receipt_correction",
                error="review receipt remained invalid after two correction calls",
                binding_sha256=current_binding["binding_sha256"],
            )
        try:
            correction = _launch_with_retries(
                production_launcher,
                branch_root=root,
                call_class="receipt_correction",
                request={"package": current_package, "errors": validation.get("errors", [])},
                gate=isolation_gate,
                expected_gate_sha256=isolation_gate_sha256,
                expected_launch_policy_sha256=launch_policy_sha256,
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            return _blocked_result(
                root, log, stage="receipt_correction", error=exc,
                binding_sha256=current_binding["binding_sha256"],
            )
        corrections += 1
        input_tokens, output_tokens, latency = _usage(correction)
        append_operation_event(
            root, log, operation="receipt_correction", status="completed",
            call_id=str(correction.get("call_id") or ""), input_tokens=input_tokens,
            output_tokens=output_tokens, latency_seconds=latency,
        )
        response.update(correction)
        try:
            validation = dict(receipt_validator(response, current_package))
        except (KeyError, TypeError, ValueError) as exc:
            return _blocked_result(
                root, log, stage="receipt_validation", error=exc,
                binding_sha256=current_binding["binding_sha256"],
            )

    try:
        localisation = freeze_localisation(
            evidence_mode,
            current_package,
            top_suspect_boundary_id=str(response["top_suspect_boundary_id"]),
            suspect_node_ref=response.get("suspect_node_ref"),
            citations=response.get("citations", citations),
            binding=current_binding,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="localisation", error=exc,
            binding_sha256=current_binding["binding_sha256"],
        )
    append_operation_event(
        root, log, operation="localisation_frozen", status="completed",
        details=localisation,
    )
    try:
        boundary = next(
            value for value in boundaries
            if str(value["boundary_id"]) == localisation["top_suspect_boundary_id"]
        )
        retrace = []
        if OPERATION_CAPABILITIES[evidence_mode]["retrace"] and localisation.get("suspect_node_ref"):
            retrace = retrace_frozen_localisation(
                evidence_mode, localisation, snapshot, boundary, binding=current_binding
            )
            append_operation_event(
                root, log, operation="retrace", status="completed",
                evidence_added={"node_count": len(retrace)}, details={"node_refs": retrace},
            )
        target = select_own_repair_target(
            pipeline,
            localisation,
            declaration_values,
            binding=current_binding,
            retrace_refs=retrace,
        )
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="repair_target_selection", error=exc,
            binding_sha256=current_binding["binding_sha256"],
            localisation=localisation,
        )
    append_operation_event(
        root, log, operation="repair_target_selection", status="completed", details=target
    )
    try:
        repair = _launch_with_retries(
            production_launcher,
            branch_root=root,
            call_class="repair",
            request={"target": target, "package": current_package},
            gate=isolation_gate,
            expected_gate_sha256=isolation_gate_sha256,
            expected_launch_policy_sha256=launch_policy_sha256,
        )
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="scoped_repair", error=exc,
            binding_sha256=current_binding["binding_sha256"],
            localisation=localisation, repair_target=target,
        )
    try:
        replacement = GeneratedPipeline.from_payload(repair["replacement_pipeline"])
        validate_boundary_sized_repair(pipeline, replacement, target)
    except (KeyError, TypeError, ValueError) as exc:
        append_operation_event(
            root, log, operation="scoped_repair", status="failed", errors=[str(exc)]
        )
        return _blocked_result(
            root, log, stage="scoped_repair", error=exc,
            binding_sha256=current_binding["binding_sha256"],
            localisation=localisation, repair_target=target,
        )
    input_tokens, output_tokens, latency = _usage(repair)
    append_operation_event(
        root, log, operation="scoped_repair", status="completed",
        call_id=str(repair.get("call_id") or ""), input_tokens=input_tokens,
        output_tokens=output_tokens, latency_seconds=latency,
    )

    try:
        rerun_ids = downstream_rerun_job_ids(repaired_job_id, dependency_values)
    except ValueError as exc:
        return _blocked_result(
            root, log, stage="rerun_selection", error=exc,
            binding_sha256=current_binding["binding_sha256"],
            localisation=localisation, repair_target=target,
        )
    try:
        rerun = _launch_with_retries(
            production_launcher,
            branch_root=root,
            call_class="rerun_recapture",
            request={
                "rerun_job_ids": rerun_ids,
                "replacement_pipeline": jsonable(replacement),
                "reuse_only_immutable_upstream": True,
                "immutable_common_artifact_hashes": immutable_hashes,
            },
            gate=isolation_gate,
            expected_gate_sha256=isolation_gate_sha256,
            expected_launch_policy_sha256=launch_policy_sha256,
        )
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="rerun_recapture", error=exc,
            binding_sha256=current_binding["binding_sha256"],
            localisation=localisation, repair_target=target, rerun_job_ids=rerun_ids,
        )
    try:
        if list(rerun.get("rerun_job_ids", [])) != rerun_ids:
            raise ValueError("production rerun did not execute the frozen downstream job set")
        if not isinstance(rerun.get("capture"), Mapping) or not rerun["capture"]:
            raise ValueError("production rerun did not return a recaptured Etiq evidence set")
        captured_snapshot_payload = rerun["capture"].get("assigned_job_snapshot")
        if not isinstance(captured_snapshot_payload, Mapping):
            raise ValueError("rerun capture lacks the assigned-job serialized Etiq snapshot")
        repaired_snapshot = _snapshot_from_payload(captured_snapshot_payload)
        if repaired_snapshot.job_id != snapshot.job_id:
            raise ValueError("rerun capture changed the assigned job identity")
        new_handoffs = recalculate_exact_hash_handoffs(
            rerun["job_artifacts"], dependency_values, rerun_ids,
            immutable_upstream_artifact_hashes=immutable_hashes,
        )
    except (KeyError, TypeError, ValueError) as exc:
        append_operation_event(
            root, log, operation="rerun_recapture", status="failed", errors=[str(exc)]
        )
        return _blocked_result(
            root, log, stage="rerun_recapture", error=exc,
            binding_sha256=current_binding["binding_sha256"],
            localisation=localisation, repair_target=target, rerun_job_ids=rerun_ids,
        )
    append_operation_event(
        root, log, operation="rerun_recapture", status="completed",
        details={
            "rerun_job_ids": rerun_ids,
            "handoffs": new_handoffs,
            "capture_sha256": _digest(_encode(rerun["capture"])),
            "assigned_job_snapshot_sha256": _digest(_encode(jsonable(repaired_snapshot))),
        },
    )

    try:
        rebuilt = dict(
            rebuild_condition_package(
                evidence_mode=evidence_mode,
                rerun_capture=deepcopy(dict(rerun["capture"])),
                snapshot=repaired_snapshot,
                replacement_pipeline=replacement,
                handoffs=deepcopy(new_handoffs),
                original_package=deepcopy(dict(package)),
                original_package_manifest=deepcopy(dict(package_manifest)),
            )
        )
        repaired_package = deepcopy(dict(rebuilt["package"]))
        repaired_manifest = dict(rebuilt["package_manifest"])
        repaired_boundaries = [dict(value) for value in rebuilt["realized_boundaries"]]
        _verify_same_condition_manifest(package_manifest, repaired_manifest)
        _verify_repaired_source_bundle(
            package=repaired_package,
            package_manifest=repaired_manifest,
            replacement=replacement,
            repaired_job_id=repaired_job_id,
        )
        _verify_package_uses_snapshot(repaired_package, repaired_snapshot)
        _verify_rebuilt_graph_selection(
            evidence_mode=evidence_mode,
            package=repaired_package,
            package_manifest=repaired_manifest,
            snapshot=repaired_snapshot,
            boundaries=repaired_boundaries,
            handoffs=new_handoffs,
            rebuilt=rebuilt,
        )
        if repaired_package.get("common_base", {}).get("assigned_job", {}).get(
            "output"
        ) != rerun["job_artifacts"][snapshot.job_id]["output"]:
            raise ValueError("rebuilt review package does not contain the recaptured assigned output")
        for field in (
            "review_task",
            "behavioural_criteria",
            "semantic_declarations",
            "section",
        ):
            if repaired_package.get("common_base", {}).get(field) != package.get(
                "common_base", {}
            ).get(field):
                raise ValueError(f"rebuilt review package changed frozen condition content: {field}")
        repaired_binding = bind_operation_context(
            evidence_mode=evidence_mode,
            package=repaired_package,
            package_manifest=repaired_manifest,
            snapshot=repaired_snapshot,
            realized_boundaries=repaired_boundaries,
            declarations=declaration_values,
            pipeline=replacement,
            handoffs=new_handoffs,
            dependencies=dependency_values,
            immutable_common_artifact_hashes=immutable_hashes,
        )
        verify_operation_context(
            repaired_binding,
            evidence_mode=evidence_mode,
            package=repaired_package,
            package_manifest=repaired_manifest,
            snapshot=repaired_snapshot,
            realized_boundaries=repaired_boundaries,
            declarations=declaration_values,
            pipeline=replacement,
            handoffs=new_handoffs,
            dependencies=dependency_values,
            immutable_common_artifact_hashes=immutable_hashes,
        )
        re_review = _launch_with_retries(
            production_launcher,
            branch_root=root,
            call_class="re_review",
            request={
                "package": repaired_package,
                "package_manifest": repaired_manifest,
                "binding_sha256": repaired_binding["binding_sha256"],
                "capture_sha256": _digest(_encode(rerun["capture"])),
            },
            gate=isolation_gate,
            expected_gate_sha256=isolation_gate_sha256,
            expected_launch_policy_sha256=launch_policy_sha256,
        )
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="re_review_package", error=exc,
            binding_sha256=current_binding["binding_sha256"],
            localisation=localisation, repair_target=target, rerun_job_ids=rerun_ids,
            handoffs=new_handoffs,
        )
    input_tokens, output_tokens, latency = _usage(re_review)
    append_operation_event(
        root, log, operation="re_review", status="completed",
        call_id=str(re_review.get("call_id") or ""), input_tokens=input_tokens,
        output_tokens=output_tokens, latency_seconds=latency,
        details={
            "package_sha256": repaired_binding["package_sha256"],
            "snapshot_sha256": repaired_binding["snapshot_sha256"],
            "binding_sha256": repaired_binding["binding_sha256"],
        },
    )
    try:
        re_review, repaired_package, repaired_binding = _run_review_evidence_phase(
            root=root,
            log=log,
            evidence_mode=evidence_mode,
            response=re_review,
            package=repaired_package,
            binding=repaired_binding,
            snapshot=repaired_snapshot,
            boundaries=repaired_boundaries,
            handoffs=new_handoffs,
            production_launcher=production_launcher,
            isolation_gate=isolation_gate,
            isolation_gate_sha256=isolation_gate_sha256,
            launch_policy_sha256=launch_policy_sha256,
            phase="repaired_run",
        )
        re_validation = dict(receipt_validator(re_review, repaired_package))
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="re_review", error=exc,
            binding_sha256=repaired_binding["binding_sha256"],
            localisation=localisation, repair_target=target, rerun_job_ids=rerun_ids,
            handoffs=new_handoffs,
        )
    re_corrections = 0
    while True:
        append_operation_event(
            root, log, operation="receipt_validation", status="completed",
            details={
                "valid": bool(re_validation.get("valid")),
                "errors": re_validation.get("errors", []),
                "phase": "re_review",
            },
        )
        if re_validation.get("valid"):
            break
        if re_corrections >= MAX_RECEIPT_CORRECTION_CALLS:
            return _blocked_result(
                root, log, stage="re_review_receipt_correction",
                error="repaired-run receipt remained invalid after two correction calls",
                binding_sha256=repaired_binding["binding_sha256"],
                localisation=localisation, repair_target=target,
                rerun_job_ids=rerun_ids, handoffs=new_handoffs,
            )
        try:
            correction = _launch_with_retries(
                production_launcher,
                branch_root=root,
                call_class="receipt_correction",
                request={
                    "phase": "re_review",
                    "package": repaired_package,
                    "errors": re_validation.get("errors", []),
                },
                gate=isolation_gate,
                expected_gate_sha256=isolation_gate_sha256,
                expected_launch_policy_sha256=launch_policy_sha256,
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            return _blocked_result(
                root, log, stage="re_review_receipt_correction", error=exc,
                binding_sha256=repaired_binding["binding_sha256"],
                localisation=localisation, repair_target=target,
                rerun_job_ids=rerun_ids, handoffs=new_handoffs,
            )
        re_corrections += 1
        input_tokens, output_tokens, latency = _usage(correction)
        append_operation_event(
            root, log, operation="receipt_correction", status="completed",
            call_id=str(correction.get("call_id") or ""), input_tokens=input_tokens,
            output_tokens=output_tokens, latency_seconds=latency,
            details={"phase": "re_review"},
        )
        re_review.update(correction)
        try:
            re_validation = dict(receipt_validator(re_review, repaired_package))
        except (KeyError, TypeError, ValueError) as exc:
            return _blocked_result(
                root, log, stage="re_review_receipt_validation", error=exc,
                binding_sha256=repaired_binding["binding_sha256"],
                localisation=localisation, repair_target=target,
                rerun_job_ids=rerun_ids, handoffs=new_handoffs,
            )
    try:
        outcome = recompute_resume_outcome(
            list(re_validation.get("units", [])), list(re_validation.get("annotations", []))
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _blocked_result(
            root, log, stage="trusted_frontier_recomputed", error=exc,
            binding_sha256=repaired_binding["binding_sha256"],
            localisation=localisation, repair_target=target,
            rerun_job_ids=rerun_ids, handoffs=new_handoffs,
        )
    append_operation_event(
        root, log, operation="trusted_frontier_recomputed", status="completed",
        details=outcome["trusted_frontier"],
    )
    append_operation_event(
        root, log, operation=outcome["outcome"], status="completed", details=outcome
    )
    return {
        "status": "completed",
        "outcome": outcome,
        "localisation": localisation,
        "repair_target": target,
        "rerun_job_ids": rerun_ids,
        "handoffs": new_handoffs,
        "operation_event_log": str(log),
        "operation_event_log_sha256": _digest(log.read_bytes()),
        "binding_sha256": repaired_binding["binding_sha256"],
        "re_review_package_sha256": repaired_binding["package_sha256"],
        "re_review_snapshot_sha256": repaired_binding["snapshot_sha256"],
    }


def recompute_resume_outcome(units: list[Any], annotations: Iterable[Any]) -> dict[str, Any]:
    annotation_values = [jsonable(annotation) for annotation in annotations]
    frontier = trusted_frontier(units, annotation_values)
    blocked = sorted(
        str(annotation.get("unit_id"))
        for annotation in annotation_values
        if str(annotation.get("status"))
        in {"failed", "suspect", "invalidated_pending_repair"}
    )
    return {
        "outcome": "blocked" if blocked else "resume",
        "blocked_unit_ids": blocked,
        "trusted_frontier": frontier,
        "resume_semantics": "workflow_continuation_from_trusted_frontier",
        "conversation_resumed": False,
    }


def validate_section_receipt(**kwargs: Any) -> tuple[Any, list[Any]]:
    """Workshop entry point reusing the production receipt validator."""
    return validate_review(**kwargs)


def operation_capability_matrix() -> dict[str, Any]:
    common = [
        "capture",
        "review",
        "citation",
        "boundary_judgment",
        "suspect_identification",
        "receipt_validation_correction",
        "own_target_boundary_repair",
        "rerun_recapture",
        "re_review",
        "trusted_frontier_resume_or_blocked",
    ]
    return {
        mode: {**capabilities, "common_operations": common}
        for mode, capabilities in OPERATION_CAPABILITIES.items()
    }
