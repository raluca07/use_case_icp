"""Corrected append-only four-instance experiment built from Attempt 023.

The module deliberately reads the prior canonical captures as immutable source
material.  It never executes those pipelines, injects a fault, or writes below
the Attempt 023 directory.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import random
import shutil
import sys
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable, Mapping

from jsonschema import Draft202012Validator

from .fault_operations import (
    ARTIFACT_PYTHON_LAUNCH_POLICY,
    ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
    PROTOCOL_CONTENT_HASH,
    _ARTIFACT_PYTHON_WORKER,
    actual_usage_record,
    aggregate_actual_usage_records,
    artifact_python_launcher,
    expand_catalogue_direct_child,
    inspect_catalogue_artifact,
    run_catalogue_follow_ups,
    signed_catalogue_python_executor,
    production_launcher_sha256,
)
from .review import frame_name
from .n05_program import _pipeline_payload, load_preflight_inputs
from .n05_runner import (
    copy_codex_auth,
    copy_etiq_worker_runtime,
    bubblewrap_version,
    create_bytes_exclusive,
    launch_codex_in_branch,
    materialize_opaque_branch,
    run_with_identical_retries,
    sha256_file,
    stable_id,
    verify_record,
)
from .n07_program import (
    EXPERIMENT_ROOT,
    _apply_scoped_source_for_job,
    _load_pre_review_state,
    _replacement_source_from_response,
    _rerun_dependency_suffix,
    _source_for_scope,
)
from .records import jsonable
from .repair import source_scope, validate_repair_scope


SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-023")
ABANDONED_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-024")
CORRECTED_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-025")
ATTEMPT_026 = Path("outputs/fault-experiments-v2-2-n10/attempt-026")
ATTEMPT_027 = Path("outputs/fault-experiments-v2-2-n10/attempt-027")
N15_TASK = Path("instructions_between_agent_types/developer/current/N15_downstream_first_cross_job_review_experiment.email.md")
N15_TASK_SHA256 = "sha256:010b0ddb260abf453fb43f3120ccf84ca3b8af5aca8b53d92aa79cbc34fb7e0e"
N15_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N15_downstream_first_cross_job_review_experiment_authorization.json")
N15_AUTHORITY_SHA256 = "sha256:c9e6a0c8fb73b6fb4523ec6fece848004aaa2543b06b0bdd1c76c0366116a6ec"
N15_HISTORICAL_GATE = Path("outputs/fault-experiments-v2-2-n10/attempt-026/qualification/tester-n14b-hash-gate-44251821d78fba4d.json")
N15_HISTORICAL_GATE_FILE_SHA256 = "sha256:edaa004cc64a51c8068641713c25b7a43d5631c32fe0b5e2f4c4f351bc372d36"
N15_TASK_TEXT = (
    "Starting from the observed downstream execution and final result, determine "
    "whether a behaviorally significant fault exists anywhere in the two-job "
    "chain. Review the downstream boundaries first, trace to the upstream producer "
    "when the supplied evidence supports it, and return one top root-cause "
    "boundary from either job or no suspect."
)
N15_CAPTURE_FILE_SHA256 = {
    "instance-01": "sha256:2571997558cc5a2fdac95009faf47e9478a3017058f6a47ce5bfdae599741f98",
    "instance-03": "sha256:f0736c1d37b09eb44332d0412ba7e7454892d6b2fe1626b537aaa1412cc99d33",
    "instance-04": "sha256:95a58bcaddb0ea8d70a1db37ce0db609764c7880799c72126941c9a1e337d3d7",
    "instance-12": "sha256:a4c4a6b00023e0d493bb45b754d799936f32658178ac53a9cac5fe57536ec736",
}
N15_PROTECTED_FILE_SHA256 = {
    "src/use_case_icp/n05_runner.py": "sha256:25ba9749a212aef9d8a23513e4e1014985291708a0517e6d20f1f4469ed85bee",
    "src/use_case_icp/n07_program.py": "sha256:d338cc22ce881b2c9bae46a105f227b9aae5f563fde17b177a3435286beec34f",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
    "prompts/v2_2/fault_review.md": "sha256:1a59763cce79f307b0b86501ee4d272726c6df793d7827a9c155b8b8fd22ea44",
    "schemas/v2_2/fault_review_receipt.schema.json": "sha256:3cebce8ef00c20f8316a4ed0998fd53ebff9e62a9471b7b635305ad7a5cbd075",
}
SELECTED_INSTANCES = {
    "instance-01": "upstream",
    "instance-04": "upstream",
    "instance-03": "downstream",
    "instance-12": "downstream",
}
EVIDENCE_MODES = (
    "current_run",
    "history_empty",
    "history_full",
    "etiq_empty",
    "etiq_full",
    "etiq_selected_fixed",
    "etiq_selected_adaptive",
    "etiq_random_matched",
)
GRAPH_MODES = frozenset(mode for mode in EVIDENCE_MODES if mode.startswith("etiq_"))
SOURCE_SETTINGS = ("source_present", "source_absent")
MAX_OPERATION_FOLLOW_UPS = 3
MAX_ARTIFACT_REQUESTS = 2
MAX_PYTHON_CODE_CHARACTERS = 2_000
MAX_PACKAGE_BYTES = 360_000
DEFAULT_PROVIDER_CONTEXT_BYTES = 480_000
PACKAGE_SCHEMA = Path(__file__).resolve().parents[2] / "schemas/corrected_four_instance_package.schema.json"
OPERATION_SCHEMA = Path(__file__).resolve().parents[2] / "schemas/corrected_four_instance_operation.schema.json"
REVIEW_PROMPT = Path("prompts/v2_2/fault_review.md")
REPAIR_PROMPT = Path("prompts/v2_2/fault_repair.md")
REVIEW_SCHEMA = Path("schemas/v2_2/fault_review_receipt.schema.json")
REPAIR_SCHEMA = Path("schemas/v2_2/fault_repair_response.schema.json")
N14_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N14_corrected_four_instance_execution_authorization.json")
N14_AUTHORITY_SHA256 = "sha256:725b0e8f6d8b2f65cf568f56c279e7cb38145706787480dfcc5f369f5bc9ea7e"
N14A_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N14A_corrected_four_instance_narrow_delta_gate_amendment.json")
N14A_AUTHORITY_SHA256 = "sha256:4e3b48cf995ffd0ae2e3b345c42e500b9bd0d56afddb244959517678410329b2"
N14_TASK = Path("instructions_between_agent_types/developer/current/N14_corrected_four_instance_finish_gate_freeze_and_run.email.md")
N14_TASK_SHA256 = "sha256:45b28eb60a78523908cf94efc6de11ecdd8551ec1c4bb2debb25b7f41b083056"
N14_TESTER_TASK = Path("instructions_between_agent_types/tester/current/N14_corrected_four_instance_single_sandbox_gate.email.md")
N14B_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N14B_corrected_four_instance_attempt_026_envelope_authorization.json")
N14B_AUTHORITY_SHA256 = "sha256:4002aed49f644c9c35193ed6f62f3ea371d66a3a40896daeee2467760c2cfb10"
N14C_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N14C_corrected_four_instance_follow_up_cap_resume_authorization.json")
N14C_AUTHORITY_SHA256 = "sha256:6851cf6f039b29098721cb02ca9296251c8bb204810149b11f6770d792bd01dc"
PROVIDER_MODEL = "gpt-5.5"
PROVIDER_REASONING_EFFORT = "high"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256(value: Any) -> str:
    content = value if isinstance(value, bytes) else canonical_json(value)
    return "sha256:" + hashlib.sha256(content).hexdigest()


def canonical_stack(stack: Iterable[str]) -> tuple[str, ...]:
    return tuple(frame_name(str(frame)) for frame in stack)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _validate_schema(value: Mapping[str, Any], schema_path: Path) -> None:
    schema = _read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(dict(value))


def _write_immutable(path: Path, value: Mapping[str, Any]) -> str:
    content = canonical_json(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise ValueError(f"append-only artifact already differs: {path}")
        return sha256(content)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    path.chmod(0o444)
    return sha256(content)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def record_attempt_024_incomplete(repo_root: Path, next_attempt: Path | None = None) -> Path:
    """Close Attempt 024 outside its immutable tree, in the next append-only attempt."""
    repo_root = repo_root.resolve()
    abandoned = repo_root / ABANDONED_ATTEMPT
    target = (next_attempt or repo_root / CORRECTED_ATTEMPT).resolve()
    if not abandoned.is_dir():
        raise ValueError("Attempt 024 is unavailable for append-only closure")
    hashes = _tree_hashes(abandoned)
    closure = {
        "schema_version": "corrected-four-instance-attempt-closure-1",
        "attempt": "attempt-024",
        "status": "terminal_incomplete",
        "failure_stage": "pre_live_qualification",
        "description": "incomplete pre-live qualification attempt",
        "experimental_reviews": 0,
        "experimental_repairs": 0,
        "experimental_results": 0,
        "attempt_tree_file_count": len(hashes),
        "attempt_tree_sha256": sha256(hashes),
        "attempt_024_was_modified": False,
        "continuation_attempt": target.name,
    }
    closure["closure_sha256"] = sha256(closure)
    path = target / "authority/attempt-024-incomplete-closure.json"
    _write_immutable(path, closure)
    if _tree_hashes(abandoned) != hashes:
        raise RuntimeError("Attempt 024 changed while recording its external closure")
    return path


def _capture_paths(source_root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted((source_root / "captures").glob("*.json")):
        instance_id = str(_read_json(path).get("instance_id") or "")
        if instance_id in SELECTED_INSTANCES:
            if instance_id in found:
                raise ValueError(f"duplicate canonical capture: {instance_id}")
            found[instance_id] = path
    if set(found) != set(SELECTED_INSTANCES):
        raise ValueError("Attempt 023 lacks one or more selected canonical captures")
    return found


def _verify_capture(capture: Mapping[str, Any]) -> None:
    unsigned = dict(capture)
    observed = str(unsigned.pop("capture_sha256", ""))
    if not capture.get("canonical") or int(capture.get("attempt_count", 0)) != 1:
        raise ValueError("selected source is not a single canonical execution")
    if observed != sha256(unsigned):
        raise ValueError("canonical capture hash mismatch")
    job_ids = list(map(str, capture.get("job_ids", [])))
    jobs = capture.get("jobs")
    if len(job_ids) != 2 or len(set(job_ids)) != 2 or not isinstance(jobs, Mapping):
        raise ValueError("canonical capture must contain two explicitly ordered jobs")
    for job_id in job_ids:
        job = jobs.get(job_id)
        if not isinstance(job, Mapping):
            raise ValueError(f"canonical capture lacks job: {job_id}")
        snapshot = job.get("snapshot")
        if not isinstance(snapshot, Mapping) or str(snapshot.get("job_id")) != job_id:
            raise ValueError(f"canonical snapshot identity mismatch: {job_id}")


def assigned_job_id(capture: Mapping[str, Any]) -> str:
    _verify_capture(capture)
    instance_id = str(capture["instance_id"])
    position = 0 if SELECTED_INSTANCES[instance_id] == "upstream" else 1
    return str(capture["job_ids"][position])


def _redaction_paths(value: Any, path: str = "$") -> list[str]:
    if isinstance(value, Mapping):
        return [
            item
            for key, child in value.items()
            for item in _redaction_paths(child, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            item
            for index, child in enumerate(value)
            for item in _redaction_paths(child, f"{path}[{index}]")
        ]
    return [path] if value == "[REDACTED]" else []


def _direct_children(
    snapshot: Mapping[str, Any], boundary: Mapping[str, Any]
) -> list[dict[str, Any]]:
    parent = canonical_stack(boundary["matched_prefix"])
    helper_prefixes = {
        canonical_stack(prefix) for prefix in boundary.get("helper_prefixes", [])
    }
    # Captured stacks are authoritative.  The realized helper list limits these
    # to helper/function frames accepted by the original capture qualification.
    captured = {
        canonical_stack(node.get("func_stack", []))
        for node in snapshot.get("nodes", [])
    }
    helpers = helper_prefixes & captured
    entries = []
    for prefix in sorted(value for value in helpers if value[:-1] == parent):
        entries.append(
            {
                "boundary_id": str(boundary["boundary_id"]),
                "func_stack": list(prefix),
                "parent_func_stack": list(parent),
                "direct_child": True,
                "captured_node_count": sum(
                    canonical_stack(node.get("func_stack", [])) == prefix
                    for node in snapshot.get("nodes", [])
                ),
                "has_nested_children": any(
                    len(other) == len(prefix) + 1 and other[:-1] == prefix
                    for other in helpers
                ),
            }
        )
    return entries


def _realized_boundary_binding(boundary: Mapping[str, Any]) -> dict[str, Any]:
    identity = boundary.get("static_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("realized boundary lacks its frozen static identity")
    qualified_name = str(identity.get("qualified_function_name") or "")
    source_path = str(identity.get("source_path") or "")
    source_sha256 = str(identity.get("function_source_sha256") or "")
    stack_prefix = list(canonical_stack(boundary.get("matched_prefix", [])))
    if not qualified_name or not source_path or not source_sha256 or not stack_prefix:
        raise ValueError("realized boundary identity is incomplete")
    frozen_identity = {
        "qualified_function_name": qualified_name,
        "source_path": source_path,
        "function_source_sha256": source_sha256,
        "func_stack_prefix": stack_prefix,
        "realized_boundary_sha256": str(boundary.get("realized_boundary_sha256") or ""),
    }
    return {
        "captured_boundary_id": str(boundary["boundary_id"]),
        "reviewer_boundary_id": f"bnd-{sha256(frozen_identity)[7:23]}",
        "frozen_realized_identity": frozen_identity,
        "binding_sha256": sha256(frozen_identity),
    }


def build_disclosure_catalogue(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve one complete controller-side catalogue from a frozen capture."""
    _verify_capture(capture)
    jobs: dict[str, Any] = {}
    redactions: list[dict[str, str]] = []
    for job_id in capture["job_ids"]:
        captured_job = capture["jobs"][job_id]
        snapshot = captured_job["snapshot"]
        nodes = []
        for original in snapshot["nodes"]:
            node = deepcopy(dict(original))
            value = node.get("artifact_content")
            for path in _redaction_paths(node):
                redactions.append({"job_id": job_id, "node_ref": node["node_ref"], "path": path})
            node["node_sha256"] = sha256(original)
            node["raw_metadata_sha256"] = sha256(original.get("raw_metadata", {}))
            node["artifact_value_sha256"] = (
                sha256(value) if value is not None else None
            )
            nodes.append(node)
        relationships = []
        for original in snapshot["relationships"]:
            relationship = deepcopy(dict(original))
            relationship["relationship_sha256"] = sha256(original)
            relationship["raw_metadata_sha256"] = sha256(
                original.get("raw_metadata", {})
            )
            relationships.append(relationship)
        boundaries = deepcopy(
            captured_job.get("realization", {}).get("realized_boundaries", [])
        )
        boundary_bindings = [_realized_boundary_binding(value) for value in boundaries]
        if len({value["reviewer_boundary_id"] for value in boundary_bindings}) != len(
            boundary_bindings
        ):
            raise ValueError("frozen realized boundary identities are not unique")
        jobs[job_id] = {
            "job_id": job_id,
            "job_order_index": list(capture["job_ids"]).index(job_id),
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_sha256": sha256(snapshot),
            "nodes": nodes,
            "relationships": relationships,
            "inventories": deepcopy(snapshot.get("inventories", {})),
            "scan_errors": deepcopy(snapshot.get("scan_errors", [])),
            "realized_boundaries": boundaries,
            "boundary_bindings": boundary_bindings,
            "realized_boundary_prefixes": [
                {
                    "boundary_id": str(boundary["boundary_id"]),
                    "func_stack": list(canonical_stack(boundary["matched_prefix"])),
                }
                for boundary in boundaries
            ],
            "direct_child_function_prefixes": [
                entry
                for boundary in boundaries
                for entry in _direct_children(snapshot, boundary)
            ],
            "input": deepcopy(captured_job["input"]),
            "output": deepcopy(captured_job["output"]),
            "stdout": str(captured_job["stdout"]),
            "stderr": str(captured_job["stderr"]),
        }
    catalogue: dict[str, Any] = {
        "schema_version": "corrected-four-instance-catalogue-1",
        "storage_classification": "restricted_controller_only",
        "instance_id": capture["instance_id"],
        "source_capture_id": capture["capture_id"],
        "source_capture_sha256": capture["capture_sha256"],
        "job_order": list(capture["job_ids"]),
        "assigned_job_id": assigned_job_id(capture),
        "source_sha256": deepcopy(capture["source_sha256"]),
        "handoffs": deepcopy(capture["handoffs"]),
        "jobs": jobs,
        "unavoidable_json_conversions": [
            {
                "scope": "entire_catalogue",
                "reason": "reused canonical capture was already frozen as JSON; no additional object conversion was performed",
            }
        ],
        "secret_redactions": redactions,
    }
    catalogue["catalogue_sha256"] = sha256(catalogue)
    return catalogue


def verify_catalogue(catalogue: Mapping[str, Any]) -> None:
    unsigned = deepcopy(dict(catalogue))
    observed = unsigned.pop("catalogue_sha256", None)
    if observed != sha256(unsigned):
        raise ValueError("disclosure catalogue hash mismatch")
    for job in catalogue["jobs"].values():
        for node in job["nodes"]:
            original = {
                key: deepcopy(value)
                for key, value in node.items()
                if key not in {"node_sha256", "raw_metadata_sha256", "artifact_value_sha256"}
            }
            if node["node_sha256"] != sha256(original):
                raise ValueError(f"catalogue node hash mismatch: {node['node_ref']}")
            if node["raw_metadata_sha256"] != sha256(node.get("raw_metadata", {})):
                raise ValueError(f"catalogue raw metadata hash mismatch: {node['node_ref']}")
            expected = (
                sha256(node["artifact_content"])
                if node.get("artifact_content") is not None
                else None
            )
            if node["artifact_value_sha256"] != expected:
                raise ValueError(f"catalogue artifact hash mismatch: {node['node_ref']}")
        for relationship in job["relationships"]:
            original = {
                key: deepcopy(value)
                for key, value in relationship.items()
                if key not in {"relationship_sha256", "raw_metadata_sha256"}
            }
            if relationship["relationship_sha256"] != sha256(original):
                raise ValueError(
                    f"catalogue relationship hash mismatch: {relationship['relationship_ref']}"
                )


def structural_node(node: Mapping[str, Any]) -> dict[str, Any]:
    """Serialize visible structure without automatically disclosing value bodies."""
    return {
        key: deepcopy(node.get(key))
        for key in (
            "node_ref",
            "raw_id",
            "names",
            "line_no",
            "state_type",
            "value_type",
            "func_stack",
            "source",
            "scope_type",
            "artifact_kind",
            "artifact_size",
            "artifact_truncated",
            "node_sha256",
            "raw_metadata_sha256",
            "artifact_value_sha256",
        )
    } | {"artifact_available": node.get("artifact_content") is not None}


def structural_relationship(relationship: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(relationship.get(key))
        for key in (
            "relationship_ref",
            "source_ref",
            "target_ref",
            "relationship_type",
            "direction",
            "relationship_sha256",
            "raw_metadata_sha256",
        )
    }


def _incident_handoffs(catalogue: Mapping[str, Any], job_id: str) -> list[dict[str, Any]]:
    values = []
    for handoff in catalogue["handoffs"]:
        if job_id not in {
            str(handoff["upstream_job_id"]),
            str(handoff["downstream_job_id"]),
        }:
            continue
        producer = str(handoff.get("producer_sha256") or "")
        consumer = str(handoff.get("consumer_sha256") or "")
        if producer != consumer or not producer.startswith("sha256:"):
            raise ValueError("canonical handoff lacks matching exact hashes")
        values.append(deepcopy(dict(handoff)))
    return values


def _boundary_children(
    job: Mapping[str, Any], boundary: Mapping[str, Any], visible: set[tuple[str, ...]]
) -> list[dict[str, Any]]:
    helpers = {
        canonical_stack(prefix) for prefix in boundary.get("helper_prefixes", [])
    }
    captured = {
        canonical_stack(node.get("func_stack", [])) for node in job["nodes"]
    }
    helpers &= captured
    entries = []
    for prefix in sorted(helpers):
        if prefix in visible or prefix[:-1] not in visible:
            continue
        entries.append(
            {
                "boundary_id": str(boundary["boundary_id"]),
                "func_stack": list(prefix),
                "parent_func_stack": list(prefix[:-1]),
                "direct_child": True,
                "captured_node_count": sum(
                    canonical_stack(node.get("func_stack", [])) == prefix
                    for node in job["nodes"]
                ),
                "has_nested_children": any(
                    len(child) == len(prefix) + 1 and child[:-1] == prefix
                    for child in helpers
                ),
            }
        )
    return entries


def selected_projection(
    catalogue: Mapping[str, Any],
    *,
    expanded_prefixes_by_boundary: Mapping[str, Iterable[Iterable[str]]] | None = None,
) -> dict[str, Any]:
    """Build the exact-level, endpoint-complete projection for the assigned job."""
    verify_catalogue(catalogue)
    job_id = str(catalogue["assigned_job_id"])
    job = catalogue["jobs"][job_id]
    node_by_ref = {str(node["node_ref"]): node for node in job["nodes"]}
    relationship_by_ref = {
        str(edge["relationship_ref"]): edge for edge in job["relationships"]
    }
    requested = {
        str(boundary_id): [canonical_stack(prefix) for prefix in prefixes]
        for boundary_id, prefixes in (expanded_prefixes_by_boundary or {}).items()
    }
    known_boundaries = {str(value["boundary_id"]) for value in job["realized_boundaries"]}
    if set(requested) - known_boundaries:
        raise ValueError("expansion references an unassigned boundary")
    visible_refs: set[str] = set()
    crossing_refs: set[str] = set()
    visible_by_boundary: dict[str, Any] = {}
    collapsed: list[dict[str, Any]] = []
    for boundary in job["realized_boundaries"]:
        boundary_id = str(boundary["boundary_id"])
        root = canonical_stack(boundary["matched_prefix"])
        visible_prefixes = {root}
        helpers = {
            canonical_stack(prefix) for prefix in boundary.get("helper_prefixes", [])
        }
        captured_prefixes = {
            canonical_stack(node.get("func_stack", [])) for node in job["nodes"]
        }
        for prefix in requested.get(boundary_id, []):
            if prefix not in helpers:
                raise ValueError(f"requested prefix is absent from frozen capture: {list(prefix)}")
            if prefix not in captured_prefixes:
                raise ValueError(f"requested prefix has no captured Etiq node: {list(prefix)}")
            if prefix[:-1] not in visible_prefixes:
                raise ValueError("nested helper expansion requires its visible parent")
            visible_prefixes.add(prefix)
        boundary_nodes = {
            ref
            for ref, node in node_by_ref.items()
            if canonical_stack(node.get("func_stack", [])) in visible_prefixes
        }
        crossings = {
            str(ref)
            for ref in list(boundary.get("input_relationship_refs", []))
            + list(boundary.get("output_relationship_refs", []))
        }
        for ref in crossings:
            edge = relationship_by_ref.get(ref)
            if edge is None:
                raise ValueError(f"crossing relationship missing from capture: {ref}")
            boundary_nodes.update({str(edge["source_ref"]), str(edge["target_ref"])})
        visible_refs.update(boundary_nodes)
        crossing_refs.update(crossings)
        collapsed.extend(_boundary_children(job, boundary, visible_prefixes))
        visible_by_boundary[boundary_id] = {
            "func_stack_prefix": list(root),
            "visible_prefixes": [list(value) for value in sorted(visible_prefixes)],
        }
    relationship_refs = set(crossing_refs)
    for ref, edge in relationship_by_ref.items():
        if str(edge["source_ref"]) in visible_refs and str(edge["target_ref"]) in visible_refs:
            relationship_refs.add(ref)
    for ref in relationship_refs:
        edge = relationship_by_ref[ref]
        visible_refs.update({str(edge["source_ref"]), str(edge["target_ref"])})
    result = {
        "nodes": [structural_node(node_by_ref[ref]) for ref in sorted(visible_refs)],
        "relationships": [
            structural_relationship(relationship_by_ref[ref])
            for ref in sorted(relationship_refs)
        ],
        "handoffs": _incident_handoffs(catalogue, job_id),
        "collapsed_children": sorted(
            collapsed, key=lambda value: (value["boundary_id"], value["func_stack"])
        ),
        "visible_evidence_by_boundary": visible_by_boundary,
    }
    result["projection_sha256"] = sha256(result)
    return result


def full_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    verify_catalogue(catalogue)
    job_id = str(catalogue["assigned_job_id"])
    job = catalogue["jobs"][job_id]
    result = {
        "nodes": [structural_node(node) for node in sorted(job["nodes"], key=lambda value: value["node_ref"])],
        "relationships": [
            structural_relationship(edge)
            for edge in sorted(job["relationships"], key=lambda value: value["relationship_ref"])
        ],
        "handoffs": _incident_handoffs(catalogue, job_id),
        "collapsed_children": [],
        "visible_evidence_by_boundary": {
            str(boundary["boundary_id"]): {
                "func_stack_prefix": list(canonical_stack(boundary["matched_prefix"])),
                "fully_visible": True,
            }
            for boundary in job["realized_boundaries"]
        },
    }
    result["projection_sha256"] = sha256(result)
    return result


def random_matched_projection(
    catalogue: Mapping[str, Any], fixed: Mapping[str, Any]
) -> dict[str, Any]:
    """Rebuild a deterministic oracle-blind projection against corrected Fixed."""
    job_id = str(catalogue["assigned_job_id"])
    job = catalogue["jobs"][job_id]
    node_by_ref = {str(node["node_ref"]): node for node in job["nodes"]}
    edge_by_ref = {str(edge["relationship_ref"]): edge for edge in job["relationships"]}
    mandatory_edges = {
        str(ref)
        for boundary in job["realized_boundaries"]
        for ref in list(boundary["input_relationship_refs"])
        + list(boundary["output_relationship_refs"])
    }
    mandatory_nodes = {
        str(boundary["matched_function_node_ref"])
        for boundary in job["realized_boundaries"]
    }
    for ref in mandatory_edges:
        mandatory_nodes.update(
            {str(edge_by_ref[ref]["source_ref"]), str(edge_by_ref[ref]["target_ref"])}
        )
    eligible_edges = {
        str(ref)
        for boundary in job["realized_boundaries"]
        for ref in boundary["relationship_refs"]
    } | mandatory_edges
    eligible_nodes = {
        str(ref)
        for boundary in job["realized_boundaries"]
        for ref in boundary["node_refs"]
    } | mandatory_nodes
    for ref in eligible_edges:
        edge = edge_by_ref[ref]
        eligible_nodes.update({str(edge["source_ref"]), str(edge["target_ref"])})
    eligible_edges.update(
        ref
        for ref, edge in edge_by_ref.items()
        if str(edge["source_ref"]) in eligible_nodes
        and str(edge["target_ref"]) in eligible_nodes
    )
    target_node_count = len(fixed["nodes"])
    target_edge_count = len(fixed["relationships"])
    if len(mandatory_nodes) > target_node_count or len(mandatory_edges) > target_edge_count:
        raise ValueError("corrected Fixed budget is below its mandatory interface")
    generator = random.Random(
        int(sha256([catalogue["source_capture_sha256"], job_id, "random-matched"])[7:23], 16)
    )
    target_bytes = len(canonical_json({
        "nodes": fixed["nodes"], "relationships": fixed["relationships"]
    }))
    node_candidates = sorted(eligible_nodes - mandatory_nodes)
    chosen_nodes: set[str] | None = None
    chosen_edges: set[str] | None = None
    attempts = [None] * 20_000 + ["fixed"]
    fixed_refs = {str(value["node_ref"]) for value in fixed["nodes"]}
    for attempt in attempts:
        if attempt == "fixed":
            candidate_nodes = fixed_refs
        else:
            generator.shuffle(node_candidates)
            candidate_nodes = mandatory_nodes | set(
                node_candidates[: target_node_count - len(mandatory_nodes)]
            )
        possible_edges = [
            ref
            for ref in eligible_edges - mandatory_edges
            if {
                str(edge_by_ref[ref]["source_ref"]),
                str(edge_by_ref[ref]["target_ref"]),
            }
            <= candidate_nodes
        ]
        if len(candidate_nodes) == target_node_count and len(possible_edges) >= (
            target_edge_count - len(mandatory_edges)
        ):
            generator.shuffle(possible_edges)
            chosen_nodes = set(candidate_nodes)
            chosen_edges = mandatory_edges | set(
                possible_edges[: target_edge_count - len(mandatory_edges)]
            )
            break
    if chosen_nodes is None or chosen_edges is None:
        raise ValueError("cannot match corrected Fixed structural budget from assigned boundaries")
    observed_bytes = len(canonical_json({
        "nodes": [structural_node(node_by_ref[value]) for value in sorted(chosen_nodes)],
        "relationships": [structural_relationship(edge_by_ref[value]) for value in sorted(chosen_edges)],
    }))
    result = {
        "nodes": [structural_node(node_by_ref[ref]) for ref in sorted(chosen_nodes)],
        "relationships": [structural_relationship(edge_by_ref[ref]) for ref in sorted(chosen_edges)],
        "handoffs": deepcopy(fixed["handoffs"]),
        "collapsed_children": [],
        "visible_evidence_by_boundary": {},
        "random_match": {
            "corrected_fixed_projection_sha256": fixed["projection_sha256"],
            "target_structural_utf8_bytes": target_bytes,
            "observed_structural_utf8_bytes": observed_bytes,
            "absolute_byte_difference": abs(target_bytes - observed_bytes),
            "target_node_count": target_node_count,
            "target_relationship_count": target_edge_count,
            "node_count_matched": len(chosen_nodes) == target_node_count,
            "relationship_count_matched": len(chosen_edges) == target_edge_count,
            "eligible_nodes_sha256": sha256(sorted(eligible_nodes)),
            "eligible_relationships_sha256": sha256(sorted(eligible_edges)),
            "uses_fault_or_oracle_truth": False,
        },
    }
    result["projection_sha256"] = sha256(result)
    return result


def _review_boundary_map(
    catalogue: Mapping[str, Any], neutral_base: Mapping[str, Any]
) -> dict[str, str]:
    job = catalogue["jobs"][catalogue["assigned_job_id"]]
    del neutral_base
    boundaries = {
        str(value["boundary_id"]): value for value in job["realized_boundaries"]
    }
    result = {}
    for binding in job["boundary_bindings"]:
        captured_id = str(binding["captured_boundary_id"])
        boundary = boundaries.get(captured_id)
        if boundary is None:
            raise ValueError("boundary binding references an absent realized boundary")
        observed = _realized_boundary_binding(boundary)
        if observed != binding:
            raise ValueError("frozen realized boundary binding changed")
        result[captured_id] = str(binding["reviewer_boundary_id"])
    if set(result) != set(boundaries):
        raise ValueError("not every realized boundary has a full-identity binding")
    return result


def _review_common_base(
    catalogue: Mapping[str, Any], neutral_base: Mapping[str, Any]
) -> dict[str, Any]:
    common = deepcopy(neutral_base["common_base"])
    job = catalogue["jobs"][catalogue["assigned_job_id"]]
    boundary_map = _review_boundary_map(catalogue, neutral_base)
    declarations = []
    for boundary in job["realized_boundaries"]:
        static_identity = boundary["static_identity"]
        qualified_name = str(static_identity["qualified_function_name"])
        if qualified_name.split(".")[-1] != str(boundary["function_name"]):
            raise ValueError("qualified name and captured realized boundary disagree")
        declarations.append(
            {
                "boundary_id": boundary_map[str(boundary["boundary_id"])],
                "function_name": str(boundary["function_name"]),
                "role": str(boundary["role"]),
                "expected_inputs": deepcopy(boundary["expected_inputs"]),
                "expected_outputs": deepcopy(boundary["expected_outputs"]),
            }
        )
    common["semantic_declarations"] = declarations
    common["section"] = {
        **{
            key: deepcopy(value)
            for key, value in common["section"].items()
            if key not in {"assigned_boundary_ids", "context_boundary_ids"}
        },
        "assigned_boundary_ids": [value["boundary_id"] for value in declarations],
        "context_boundary_ids": [],
    }
    return common


def _canonical_history(catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    order = list(map(str, catalogue["job_order"]))
    assigned = str(catalogue["assigned_job_id"])
    if assigned == order[0]:
        return []
    upstream = catalogue["jobs"][order[0]]
    return [
        {
            "input": deepcopy(upstream["input"]),
            "output": deepcopy(upstream["output"]),
            "stdout": upstream["stdout"],
            "stderr": upstream["stderr"],
        }
    ]


def _remap_projection_boundaries(
    projection: Mapping[str, Any], boundary_map: Mapping[str, str]
) -> dict[str, Any]:
    result = deepcopy(dict(projection))
    result["collapsed_children"] = [
        {**value, "boundary_id": boundary_map[str(value["boundary_id"])]}
        for value in result.get("collapsed_children", [])
    ]
    result["visible_evidence_by_boundary"] = {
        boundary_map[str(boundary_id)]: value
        for boundary_id, value in result.get("visible_evidence_by_boundary", {}).items()
    }
    result.pop("projection_sha256", None)
    result["projection_sha256"] = sha256(result)
    return result


def _legacy_package(source_root: Path, instance_id: str, job_id: str) -> dict[str, Any]:
    for record_path in sorted((source_root / "package-records").glob("*.json")):
        record = _read_json(record_path)
        if (
            record.get("instance_id") == instance_id
            and record.get("assigned_job_id") == job_id
            and record.get("source_setting") == "source_present"
        ):
            return _read_json(
                source_root
                / "packages"
                / str(record["branch_id"])
                / "evidence/review-package.json"
            )
    raise ValueError(f"Attempt 023 has no reusable neutral package: {instance_id}/{job_id}")


def build_review_package(
    catalogue: Mapping[str, Any],
    *,
    evidence_mode: str,
    source_setting: str,
    neutral_base: Mapping[str, Any],
) -> dict[str, Any]:
    if evidence_mode not in EVIDENCE_MODES or source_setting not in SOURCE_SETTINGS:
        raise ValueError("unknown corrected experiment condition")
    package: dict[str, Any] = {
        "schema_version": "corrected-four-instance-package-2",
        "common_base": _review_common_base(catalogue, neutral_base),
        "available_operations": [
            *(
                ["artifact_inspection"]
                if evidence_mode in GRAPH_MODES - {"etiq_empty"}
                else []
            ),
            *(
                ["helper_expansion"]
                if evidence_mode == "etiq_selected_adaptive"
                else []
            ),
        ],
        "prior_task_records": (
            _canonical_history(catalogue) if evidence_mode == "history_full" else []
        ),
    }
    if source_setting == "source_present":
        package["source_bundle"] = deepcopy(neutral_base["source_bundle"])
    if evidence_mode in GRAPH_MODES:
        boundary_map = _review_boundary_map(catalogue, neutral_base)
        if evidence_mode == "etiq_empty":
            projection = {
                "nodes": [],
                "relationships": [],
                "handoffs": [],
                "collapsed_children": [],
                "visible_evidence_by_boundary": {},
            }
            projection["projection_sha256"] = sha256(projection)
        elif evidence_mode == "etiq_full":
            projection = _remap_projection_boundaries(
                full_projection(catalogue), boundary_map
            )
        else:
            fixed = selected_projection(catalogue)
            remapped_fixed = _remap_projection_boundaries(fixed, boundary_map)
            if evidence_mode == "etiq_random_matched":
                projection = _remap_projection_boundaries(
                    random_matched_projection(catalogue, fixed), boundary_map
                )
                projection["random_match"]["corrected_fixed_projection_sha256"] = (
                    remapped_fixed["projection_sha256"]
                )
                projection.pop("projection_sha256", None)
                projection["projection_sha256"] = sha256(projection)
            else:
                projection = remapped_fixed
        package["runtime_evidence"] = projection
    allowed = {
        str(value["boundary_id"])
        for value in package["common_base"]["semantic_declarations"]
    }
    package["allowed_evidence_refs"] = sorted(allowed)
    _validate_schema(package, PACKAGE_SCHEMA)
    return package


_CONTROLLER_ONLY_KEYS = frozenset(
    {
        "condition_id",
        "branch_id",
        "evidence_mode",
        "source_setting",
        "seed",
        "authoring_seed",
        "injection_seed",
        "trial_id",
        "repair_id",
        "repetition",
    }
)


def _controller_key_paths(value: Any, path: str = "$") -> list[str]:
    if isinstance(value, Mapping):
        paths = [
            f"{path}.{key}" for key in value if str(key) in _CONTROLLER_ONLY_KEYS
        ]
        return paths + [
            found
            for key, child in value.items()
            for found in _controller_key_paths(child, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            found
            for index, child in enumerate(value)
            for found in _controller_key_paths(child, f"{path}[{index}]")
        ]
    if isinstance(value, str) and (
        value in set(EVIDENCE_MODES) | set(SOURCE_SETTINGS)
        or value.startswith(("trial-", "repair-", "brn-", "cfg-"))
    ):
        return [path]
    return []


def render_provider_request(
    reviewer_package: Mapping[str, Any],
    *,
    operation_response: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Render the model-facing request without accepting a controller wrapper."""
    _validate_schema(reviewer_package, PACKAGE_SCHEMA)
    request = {"reviewer_package": deepcopy(dict(reviewer_package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    leaks = _controller_key_paths(request)
    if leaks:
        raise ValueError(f"provider request contains controller-only identifiers: {leaks}")
    return request


def _differing_top_level_keys(left: Mapping[str, Any], right: Mapping[str, Any]) -> set[str]:
    return {
        key
        for key in set(left) | set(right)
        if canonical_json(left.get(key)) != canonical_json(right.get(key))
    }


def verify_rendered_request_comparisons(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    values = [dict(value) for value in records]
    by_condition = {
        (
            value["controller_condition"]["instance_id"],
            value["controller_condition"]["evidence_mode"],
            value["controller_condition"]["source_setting"],
        ): value["reviewer_package"]
        for value in values
    }
    checks = 0
    for instance_id, assigned_side in SELECTED_INSTANCES.items():
        for source in SOURCE_SETTINGS:
            empty = by_condition[(instance_id, "history_empty", source)]
            full = by_condition[(instance_id, "history_full", source)]
            difference = _differing_top_level_keys(empty, full)
            expected = set() if assigned_side == "upstream" else {"prior_task_records"}
            if difference != expected:
                raise ValueError("history rendered-request pair differs outside canonical history")
            etiq_empty = by_condition[(instance_id, "etiq_empty", source)]
            fixed = by_condition[(instance_id, "etiq_selected_fixed", source)]
            if _differing_top_level_keys(etiq_empty, fixed) != {
                "runtime_evidence",
                "available_operations",
            }:
                raise ValueError("Etiq Empty and Fixed differ outside graph and operations")
            adaptive = by_condition[(instance_id, "etiq_selected_adaptive", source)]
            if canonical_json(fixed["runtime_evidence"]) != canonical_json(
                adaptive["runtime_evidence"]
            ):
                raise ValueError("Fixed and Adaptive initial graph evidence differs")
            checks += 3
        for mode in EVIDENCE_MODES:
            present = by_condition[(instance_id, mode, "source_present")]
            absent = by_condition[(instance_id, mode, "source_absent")]
            if _differing_top_level_keys(present, absent) != {"source_bundle"}:
                raise ValueError("source pair differs outside its separate source bundle")
            checks += 1
    for value in values:
        render_provider_request(value["reviewer_package"])
        checks += 1
    return {"status": "passed", "comparison_count": checks}


def validate_visible_reference(package: Mapping[str, Any], reference: str) -> str:
    runtime = package.get("runtime_evidence", {})
    visible = set(map(str, package.get("allowed_evidence_refs", [])))
    visible.update(str(value["node_ref"]) for value in runtime.get("nodes", []))
    visible.update(
        str(value["relationship_ref"]) for value in runtime.get("relationships", [])
    )
    visible.update(str(value["handoff_id"]) for value in runtime.get("handoffs", []))
    if str(reference) not in visible:
        raise ValueError(f"reference is not visible in current reviewer package: {reference}")
    return str(reference)


def _retired_local_expand_helper(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if request.get("operation") != "helper_expansion":
        raise ValueError("operation must be helper_expansion")
    if "helper_expansion" not in package.get("available_operations", []):
        raise ValueError("helper expansion is unavailable in this reviewer package")
    prefixes = list(request.get("prefixes", []))
    if len(prefixes) != 1:
        raise ValueError("exactly one direct child must be requested")
    boundary_id = str(request.get("boundary_id") or "")
    runtime = package.get("runtime_evidence", {})
    requested = list(map(str, prefixes[0]))
    collapsed = {
        (str(value["boundary_id"]), tuple(map(str, value["func_stack"])))
        for value in runtime.get("collapsed_children", [])
    }
    if (boundary_id, tuple(requested)) not in collapsed:
        raise ValueError("helper expansion must target a current collapsed direct child")
    current_visible = runtime.get("visible_evidence_by_boundary", {})
    if boundary_id not in current_visible:
        raise ValueError("helper expansion boundary is not assigned")
    boundary_map = _review_boundary_map(catalogue, package)
    reverse_map = {reviewer: captured for captured, reviewer in boundary_map.items()}
    if boundary_id not in reverse_map:
        raise ValueError("helper expansion boundary is not assigned")
    visible_prefixes = {}
    job = catalogue["jobs"][catalogue["assigned_job_id"]]
    roots = {
        str(value["boundary_id"]): canonical_stack(value["matched_prefix"])
        for value in job["realized_boundaries"]
    }
    for reviewer_id, value in current_visible.items():
        captured_id = reverse_map[str(reviewer_id)]
        visible_prefixes[captured_id] = [
            prefix for prefix in value.get("visible_prefixes", [])
            if canonical_stack(prefix) != roots[captured_id]
        ]
    visible_prefixes.setdefault(reverse_map[boundary_id], []).append(requested)
    projection = selected_projection(
        catalogue, expanded_prefixes_by_boundary=visible_prefixes
    )
    projection = _remap_projection_boundaries(projection, boundary_map)
    old_nodes = {str(value["node_ref"]) for value in runtime.get("nodes", [])}
    old_edges = {
        str(value["relationship_ref"]) for value in runtime.get("relationships", [])
    }
    updated = deepcopy(dict(package))
    updated["runtime_evidence"] = projection
    allowed = set(map(str, updated.get("allowed_evidence_refs", [])))
    allowed.update(str(value["node_ref"]) for value in projection["nodes"])
    allowed.update(str(value["relationship_ref"]) for value in projection["relationships"])
    updated["allowed_evidence_refs"] = sorted(allowed)
    _validate_schema(updated, PACKAGE_SCHEMA)
    added_nodes = [
        str(value["node_ref"]) for value in projection["nodes"]
        if str(value["node_ref"]) not in old_nodes
    ]
    added_edges = [
        str(value["relationship_ref"]) for value in projection["relationships"]
        if str(value["relationship_ref"]) not in old_edges
    ]
    event = {
        "operation": "helper_expansion",
        "status": "completed",
        "boundary_id": boundary_id,
        "prefix": requested,
        "nodes_added": added_nodes,
        "relationships_added": added_edges,
    }
    return updated, event


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _describe_artifact(node: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    content = node["artifact_content"]
    if node.get("artifact_kind") == "table":
        rows = list(content.get("rows", []))
        columns = list(map(str, content.get("columns", [])))
        requested = list(map(str, request.get("columns", [])))
        unknown = set(requested) - set(columns)
        if unknown:
            raise ValueError(f"describe requested unknown columns: {sorted(unknown)}")
        types = {
            column: sorted({_json_type(row.get(column)) for row in rows})
            for column in columns
        }
        nulls = {column: sum(row.get(column) is None for row in rows) for column in columns}
        numeric = {}
        for column in requested:
            values = [
                float(row[column]) for row in rows
                if isinstance(row.get(column), (int, float))
                and not isinstance(row.get(column), bool)
            ]
            if not values:
                continue
            ordered = sorted(values)
            middle = len(ordered) // 2
            median = (
                ordered[middle]
                if len(ordered) % 2
                else (ordered[middle - 1] + ordered[middle]) / 2
            )
            numeric[column] = {
                "count": len(values),
                "minimum": min(values),
                "maximum": max(values),
                "mean": sum(values) / len(values),
                "median": median,
            }
        result = {
            "row_count": len(rows),
            "column_count": len(columns),
            "columns": columns,
            "json_value_types": types,
            "null_counts": nulls,
            "numeric_statistics": numeric,
        }
    elif node.get("artifact_kind") == "document":
        text = str(content)
        result = {
            "character_count": len(text),
            "line_count": len(text.splitlines()),
            "capture_metadata": {
                "artifact_size": deepcopy(node.get("artifact_size")),
                "artifact_truncated": bool(node.get("artifact_truncated")),
                "artifact_value_sha256": node.get("artifact_value_sha256"),
            },
        }
    else:
        result = {
            "json_value_type": _json_type(content),
            "artifact_size": deepcopy(node.get("artifact_size")),
        }
    if request.get("include_raw_metadata") is True:
        result["raw_metadata"] = deepcopy(node.get("raw_metadata", {}))
        result["raw_metadata_sha256"] = node.get("raw_metadata_sha256")
    return result


_PYTHON_WORKER = r"""
import json, resource, sys
import pandas as pd

resource.setrlimit(resource.RLIMIT_DATA, (256 * 1024 * 1024, 256 * 1024 * 1024))
payload = json.loads(sys.stdin.read())
df = pd.DataFrame(payload["rows"], columns=payload["columns"]).copy(deep=True)
safe = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "float": float, "int": int, "len": len,
    "list": list, "max": max, "min": min, "range": range, "round": round,
    "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
}
scope = {"__builtins__": safe, "df": df}
tree = compile(payload["code"], "<artifact-python>", "eval")
result = eval(tree, scope, {})
def clean(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, dict):
        return {str(key): clean(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
print(json.dumps(clean(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
"""


def _python_artifact(node: Mapping[str, Any], code: str) -> dict[str, Any]:
    del node, code
    raise ValueError(
        "python artifact inspection is disabled until a signed production sandbox is supplied"
    )


def _retired_local_inspect_artifact(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if "artifact_inspection" not in package.get("available_operations", []):
        raise ValueError("artifact inspection is unavailable in this reviewer package")
    node_ref = str(request.get("node_ref") or "")
    visible = {
        str(value["node_ref"])
        for value in package.get("runtime_evidence", {}).get("nodes", [])
    }
    if node_ref not in visible:
        raise ValueError("artifact inspection requires a currently visible node")
    job = catalogue["jobs"][catalogue["assigned_job_id"]]
    node = next((value for value in job["nodes"] if value["node_ref"] == node_ref), None)
    if node is None or node.get("artifact_content") is None:
        raise ValueError("visible node has no captured artifact value")
    inspection = str(request.get("inspection") or "read")
    start = int(request.get("start") or 0)
    count = int(request.get("count") or 20)
    if start < 0 or count < 1:
        raise ValueError("artifact read ranges must be positive")
    base = {
        "operation": "artifact_inspection",
        "node_ref": node_ref,
        "inspection": inspection,
        "artifact_kind": node.get("artifact_kind"),
        "artifact_value_sha256": node.get("artifact_value_sha256"),
        "artifact_truncated_at_capture": bool(node.get("artifact_truncated")),
    }
    content = node["artifact_content"]
    query = str(request.get("query") or "")
    if inspection == "describe":
        result = _describe_artifact(node, request)
    elif inspection == "full":
        result = {
            "content": deepcopy(content),
            "more_available": False,
            "full_data_requested": True,
        }
    elif inspection == "python":
        result = {
            **_python_artifact(node, str(request.get("code") or "")),
            "python_analysis_requested": True,
        }
    elif inspection == "read":
        if node.get("artifact_kind") == "document":
            text = str(content)
            if query:
                lowered = text.casefold()
                needle = query.casefold()
                matches = []
                offset = 0
                while len(matches) < count:
                    found = lowered.find(needle, offset)
                    if found < 0:
                        break
                    matches.append({"character_offset": found, "text": text[found:found + len(query)]})
                    offset = found + max(1, len(query))
                result = {
                    "content": matches,
                    "returned_document_characters": sum(len(value["text"]) for value in matches),
                    "more_available": lowered.find(needle, offset) >= 0,
                }
            else:
                selected = text[start:start + count]
                result = {
                    "content": selected,
                    "returned_document_characters": len(selected),
                    "more_available": start + len(selected) < len(text),
                }
        elif node.get("artifact_kind") == "table":
            rows = list(content.get("rows", []))
            available = list(map(str, content.get("columns", [])))
            columns = list(map(str, request.get("columns", []))) or available
            unknown = set(columns) - set(available)
            if unknown:
                raise ValueError(f"read requested unknown columns: {sorted(unknown)}")
            if query:
                rows = [
                    row for row in rows
                    if query.casefold() in json.dumps(row, ensure_ascii=False).casefold()
                ]
            selected = [
                {column: row.get(column) for column in columns}
                for row in rows[start:start + count]
            ]
            result = {
                "content": selected,
                "columns": columns,
                "returned_rows": len(selected),
                "returned_columns": len(columns),
                "more_available": start + len(selected) < len(rows),
            }
        else:
            values = content if isinstance(content, list) else [content]
            selected = deepcopy(values[start:start + count])
            result = {"content": selected, "returned_records": len(selected), "more_available": start + len(selected) < len(values)}
    else:
        raise ValueError(f"unknown artifact inspection choice: {inspection}")
    response = {**base, **result}
    response["artifact_bytes_returned"] = len(canonical_json(response.get("content", response.get("result"))))
    return response


def _retired_local_usage_record(response: Mapping[str, Any], *, purpose: str, phase: str) -> dict[str, Any]:
    usage = response.get("usage")
    source = usage if isinstance(usage, Mapping) else response
    fields = (
        "input_tokens", "cached_input_tokens", "output_tokens",
        "reasoning_tokens", "total_tokens",
    )
    result: dict[str, Any] = {"purpose": purpose, "phase": phase}
    unavailable = []
    for field in fields:
        value = source.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[field] = value
        else:
            result[field] = None
            unavailable.append(field)
    result["usage_status"] = "reported" if not unavailable else "partially_unavailable"
    result["unavailable_fields"] = unavailable
    return result


def _retired_local_aggregate_actual_usage(calls: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = [dict(value) for value in calls]
    result: dict[str, Any] = {"calls": records}
    for field, output in (
        ("input_tokens", "cumulative_actual_input_tokens"),
        ("total_tokens", "cumulative_actual_total_tokens"),
    ):
        values = [value.get(field) for value in records]
        result[output] = (
            sum(values)
            if all(isinstance(value, int) and not isinstance(value, bool) for value in values)
            else None
        )
    result["usage_complete"] = all(
        not value.get("unavailable_fields") for value in records
    )
    return result


def _retired_local_perform_operation(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Perform one operation and return a recorded rejection instead of leaking evidence."""
    operation = str(request.get("operation") or "")
    try:
        _validate_schema(request, OPERATION_SCHEMA)
        if operation == "helper_expansion":
            return expand_helper(catalogue, package, request)
        if operation == "artifact_inspection":
            requests = list(request.get("requests", []))
            if len(requests) > MAX_ARTIFACT_REQUESTS:
                raise ValueError("artifact inspection exceeds two requests")
            evidence = [inspect_artifact(catalogue, package, value) for value in requests]
            event = {
                "operation": operation,
                "status": "completed",
                "request_count": len(requests),
                "artifact_bytes_returned": sum(value["artifact_bytes_returned"] for value in evidence),
                "returned_rows": sum(int(value.get("returned_rows", 0)) for value in evidence),
                "returned_columns": sum(int(value.get("returned_columns", 0)) for value in evidence),
                "returned_document_characters": sum(int(value.get("returned_document_characters", 0)) for value in evidence),
                "full_data_requested": any(value.get("full_data_requested") is True for value in evidence),
                "python_analysis_requested": any(value.get("python_analysis_requested") is True for value in evidence),
                "evidence": evidence,
            }
            return deepcopy(dict(package)), event
        raise ValueError(f"illegal operation request: {operation}")
    except (KeyError, TypeError, ValueError) as exc:
        return deepcopy(dict(package)), {
            "operation": operation,
            "status": "rejected",
            "error": str(exc),
            "nodes_added": [],
            "relationships_added": [],
        }


def _retired_local_follow_up_loop(
    *,
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    initial_response: Mapping[str, Any],
    reviewer: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    phase: str = "initial_review",
) -> dict[str, Any]:
    """Retain the July fresh-call loop with accumulated visible evidence."""
    current_package = deepcopy(dict(package))
    response = dict(initial_response)
    calls = [usage_record(response, purpose="initial_review" if phase == "initial_review" else "repaired_run_review", phase=phase)]
    events = []
    follow_ups = 0
    while response.get("follow_up_requests"):
        if follow_ups >= MAX_OPERATION_FOLLOW_UPS:
            raise ValueError("review exceeded three operation follow-up calls")
        request = list(response["follow_up_requests"])[0]
        current_package, event = perform_operation(catalogue, current_package, request)
        events.append(event)
        follow_ups += 1
        response = dict(
            reviewer(
                {
                    "purpose": "operation_follow_up",
                    "phase": phase,
                    "package": current_package,
                    "operation_event": event,
                }
            )
        )
        calls.append(
            usage_record(
                response,
                purpose=f"{event['operation']}_follow_up",
                phase=phase,
            )
        )
    return {
        "package": current_package,
        "response": response,
        "operation_events": events,
        "operation_follow_up_count": follow_ups,
        "usage": aggregate_actual_usage(calls),
    }


usage_record = actual_usage_record
aggregate_actual_usage = aggregate_actual_usage_records


def inspect_artifact(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    python_executor: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return inspect_catalogue_artifact(
        catalogue, package, request, python_executor=python_executor
    )


def expand_helper(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return expand_catalogue_direct_child(
        catalogue,
        package,
        request,
        projection_builder=selected_projection,
        boundary_map=_review_boundary_map(catalogue, package),
        package_validator=lambda value: _validate_schema(value, PACKAGE_SCHEMA),
        stack_normalizer=canonical_stack,
    )


def perform_operation(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    python_executor: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation = str(request.get("operation") or "")
    try:
        _validate_schema(request, OPERATION_SCHEMA)
        if operation == "helper_expansion":
            return expand_helper(catalogue, package, request)
        if operation == "artifact_inspection":
            evidence = [
                inspect_artifact(
                    catalogue, package, value, python_executor=python_executor
                )
                for value in request.get("requests", [])
            ]
            return deepcopy(dict(package)), {
                "operation": operation,
                "status": "completed",
                "request_count": len(evidence),
                "artifact_bytes_returned": sum(value["artifact_bytes_returned"] for value in evidence),
                "returned_rows": sum(int(value.get("returned_rows", 0)) for value in evidence),
                "returned_columns": sum(int(value.get("returned_columns", 0)) for value in evidence),
                "returned_document_characters": sum(int(value.get("returned_document_characters", 0)) for value in evidence),
                "full_data_requested": any(value.get("full_data_requested") is True for value in evidence),
                "python_analysis_requested": any(value.get("python_analysis_requested") is True for value in evidence),
                "evidence": evidence,
            }
        raise ValueError(f"illegal operation request: {operation}")
    except (KeyError, TypeError, ValueError) as exc:
        return deepcopy(dict(package)), {
            "operation": operation,
            "status": "rejected",
            "error": str(exc),
            "nodes_added": [],
            "relationships_added": [],
        }


def run_follow_up_loop(
    *,
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    initial_response: Mapping[str, Any],
    reviewer: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    phase: str = "initial_review",
    controller_parent_id: str = "review",
    python_executor: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    follow_up_index = 0

    def call(request: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal follow_up_index
        follow_up_index += 1
        return _invoke_callback(
            reviewer,
            request,
            f"{controller_parent_id}-follow-up-{follow_up_index:02d}",
        )

    return run_catalogue_follow_ups(
        catalogue=catalogue,
        package=package,
        initial_response=initial_response,
        reviewer=call,
        operation=lambda current_catalogue, current_package, request: perform_operation(
            current_catalogue,
            current_package,
            request,
            python_executor=python_executor,
        ),
        phase=phase,
    )


def validate_reviewer_response(
    package: Mapping[str, Any], response: Mapping[str, Any]
) -> dict[str, Any]:
    receipt = {"reviews": deepcopy(list(response.get("reviews", [])))}
    _validate_schema(
        receipt,
        Path(__file__).resolve().parents[2] / "schemas/v2_2/fault_review_receipt.schema.json",
    )
    assigned = list(package["common_base"]["section"]["assigned_boundary_ids"])
    reviewed = [str(value["unit_id"]) for value in receipt["reviews"]]
    if sorted(reviewed) != sorted(assigned) or len(reviewed) != len(set(reviewed)):
        raise ValueError("review response must judge every assigned boundary exactly once")
    suspects = []
    for review in receipt["reviews"]:
        refs = list(map(str, review["evidence_refs"]))
        refs.extend(
            str(ref)
            for criterion in review["criteria_outcomes"]
            for ref in criterion["evidence_refs"]
        )
        refs.extend(map(str, review["suspect_node_refs"]))
        for ref in refs:
            validate_visible_reference(package, ref)
        if review["decision"] in {"failed", "suspect"}:
            suspects.append(str(review["unit_id"]))
    return {
        "valid": True,
        "receipt": receipt,
        "suspect_boundary_ids": suspects,
        "selected_suspect_boundary_id": suspects[0] if suspects else None,
    }


def dependency_suffix(job_order: Iterable[str], repaired_job_id: str) -> list[str]:
    order = list(map(str, job_order))
    if len(order) != 2 or len(set(order)) != 2:
        raise ValueError("corrected experiment requires explicit two-job order")
    if repaired_job_id not in order:
        raise ValueError("repair target is absent from explicit job order")
    return order[order.index(repaired_job_id):]


def experiment_schedule(catalogues: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = {str(value["instance_id"]): value for value in catalogues}
    if set(values) != set(SELECTED_INSTANCES):
        raise ValueError("corrected experiment requires exactly four selected instances")
    packages = [
        {
            "instance_id": instance_id,
            "evidence_mode": mode,
            "source_setting": source,
            "branch_id": f"brn-{sha256([instance_id, mode, source])[7:23]}",
        }
        for instance_id in SELECTED_INSTANCES
        for mode in EVIDENCE_MODES
        for source in SOURCE_SETTINGS
    ]
    reviews = [
        {**item, "repetition": repetition, "trial_id": f"trial-{sha256([item['branch_id'], repetition])[7:23]}"}
        for item in packages
        for repetition in range(1, 4)
    ]
    repairs = [
        {**item, "repetition": repetition, "repair_id": f"repair-{sha256([item['branch_id'], repetition])[7:23]}"}
        for item in packages
        if item["instance_id"] in {"instance-03", "instance-04"}
        for repetition in range(1, 4)
    ]
    if (len(packages), len(reviews), len(repairs)) != (64, 192, 96):
        raise AssertionError("corrected experiment matrix changed")
    return {"packages": packages, "review_trials": reviews, "repair_traces": repairs}


def qualify_packages(
    packages: Iterable[Mapping[str, Any]],
    catalogues: Mapping[str, Mapping[str, Any]],
    *,
    provider_context_bytes: int = DEFAULT_PROVIDER_CONTEXT_BYTES,
) -> dict[str, Any]:
    values = [dict(value) for value in packages]
    if len(values) != 64 or len({value["package_sha256"] for value in values}) != 64:
        raise ValueError("qualification requires 64 newly frozen unique packages")
    if any(len(canonical_json(value)) > MAX_PACKAGE_BYTES for value in values):
        raise ValueError("review package exceeds existing package byte gate")
    for instance_id, catalogue in catalogues.items():
        full = next(
            value for value in values
            if value["controller_condition"]["instance_id"] == instance_id
            and value["controller_condition"]["evidence_mode"] == "etiq_full"
            and value["controller_condition"]["source_setting"] == "source_present"
        )
        for node in catalogue["jobs"][catalogue["assigned_job_id"]]["nodes"]:
            if node.get("artifact_content") is None:
                continue
            response_bytes = len(canonical_json({"content": node["artifact_content"]}))
            if len(canonical_json(full["reviewer_package"])) + response_bytes > provider_context_bytes:
                raise ValueError(
                    f"complete artifact cannot fit one operation follow-up: {node['node_ref']}"
                )
    return {
        "status": "passed",
        "package_count": 64,
        "skips": 0,
        "provider_context_bytes": provider_context_bytes,
        "full_artifacts_qualified": sum(
            node.get("artifact_content") is not None
            for catalogue in catalogues.values()
            for node in catalogue["jobs"][catalogue["assigned_job_id"]]["nodes"]
        ),
        "repair_suffixes": {
            instance_id: dependency_suffix(
                catalogue["job_order"], catalogue["assigned_job_id"]
            )
            for instance_id, catalogue in catalogues.items()
            if instance_id in {"instance-03", "instance-04"}
        },
    }


def qualify_zero_model_lifecycle(
    packages: Iterable[Mapping[str, Any]],
    catalogues: Mapping[str, Mapping[str, Any]],
    schedule: Mapping[str, Any],
    *,
    production_python_executor: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Exercise deterministic lifecycle paths, but never self-certify the sandbox."""
    values = [dict(value) for value in packages]
    if (
        len(schedule.get("review_trials", [])) != 192
        or len(schedule.get("repair_traces", [])) != 96
    ):
        raise ValueError("zero-model lifecycle has an incomplete frozen schedule")
    checked_modes = set()
    rendered_requests = 0
    response_validations = 0
    for record in values:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        unsigned = deepcopy(dict(record))
        observed = unsigned.pop("package_sha256")
        if observed != sha256(unsigned):
            raise ValueError("zero-model lifecycle found a changed frozen package")
        render_provider_request(package)
        rendered_requests += 1
        checked_modes.add(str(condition["evidence_mode"]))
        if condition["source_setting"] == "source_present" and "source_bundle" not in package:
            raise ValueError("source-present qualification package lacks source")
        if condition["source_setting"] == "source_absent" and "source_bundle" in package:
            raise ValueError("source-absent qualification package exposes source")
        runtime = package.get("runtime_evidence")
        if runtime:
            nodes = {str(value["node_ref"]) for value in runtime["nodes"]}
            for edge in runtime["relationships"]:
                if str(edge["source_ref"]) not in nodes or str(edge["target_ref"]) not in nodes:
                    raise ValueError("zero-model lifecycle found a hidden relationship endpoint")
        reviews = []
        for boundary_id in package["common_base"]["section"]["assigned_boundary_ids"]:
            reviews.append(
                {
                    "unit_id": boundary_id,
                    "decision": "trusted",
                    "decision_reason": "deterministic zero-model validation",
                    "evidence_refs": [boundary_id],
                    "trust_level": "trusted_for_reporting",
                    "criteria_outcomes": [],
                    "boundary_health_acknowledged": True,
                    "expand_helper_prefixes": [],
                    "inspect_artifacts": [],
                    "suspect_node_refs": [],
                }
            )
        validate_reviewer_response(package, {"reviews": reviews})
        response_validations += 1
    if checked_modes != set(EVIDENCE_MODES):
        raise ValueError("zero-model lifecycle did not exercise every evidence mode")
    operation_counts = {"read": 0, "describe": 0, "full": 0, "python": 0, "helper_expansion": 0}
    for instance_id, catalogue in catalogues.items():
        full_package = next(
            value["reviewer_package"]
            for value in values
            if value["controller_condition"] == next(
                item
                for item in schedule["packages"]
                if item["instance_id"] == instance_id
                and item["evidence_mode"] == "etiq_full"
                and item["source_setting"] == "source_absent"
            )
        )
        for node in catalogue["jobs"][catalogue["assigned_job_id"]]["nodes"]:
            if node.get("artifact_content") is None:
                continue
            ref = str(node["node_ref"])
            for inspection in ("read", "describe", "full"):
                inspect_artifact(
                    catalogue,
                    full_package,
                    {"node_ref": ref, "inspection": inspection},
                )
                operation_counts[inspection] += 1
            if node.get("artifact_kind") == "table" and production_python_executor is not None:
                inspect_artifact(
                    catalogue,
                    full_package,
                    {"node_ref": ref, "inspection": "python", "code": "len(df)"},
                    python_executor=production_python_executor,
                )
                operation_counts["python"] += 1
        adaptive = next(
            value["reviewer_package"]
            for value in values
            if value["controller_condition"] == next(
                item
                for item in schedule["packages"]
                if item["instance_id"] == instance_id
                and item["evidence_mode"] == "etiq_selected_adaptive"
                and item["source_setting"] == "source_absent"
            )
        )
        current = adaptive
        while current["runtime_evidence"]["collapsed_children"] and operation_counts["helper_expansion"] < 12:
            child = current["runtime_evidence"]["collapsed_children"][0]
            current, event = perform_operation(
                catalogue,
                current,
                {
                    "operation": "helper_expansion",
                    "boundary_id": child["boundary_id"],
                    "prefixes": [child["func_stack"]],
                },
            )
            if event["status"] != "completed":
                raise ValueError("zero-model nested helper expansion was rejected")
            operation_counts["helper_expansion"] += 1
    repair_suffixes = {
        instance_id: dependency_suffix(
            catalogue["job_order"], catalogue["assigned_job_id"]
        )
        for instance_id, catalogue in catalogues.items()
        if instance_id in {"instance-03", "instance-04"}
    }
    if len(repair_suffixes["instance-04"]) != 2 or len(repair_suffixes["instance-03"]) != 1:
        raise ValueError("zero-model lifecycle failed an upstream/downstream repair suffix")
    # Exercise repaired-package reconstruction and re-review using the frozen
    # recapture shape. Real live execution replaces this deterministic handoff.
    repaired_packages = 0
    for instance_id in ("instance-03", "instance-04"):
        catalogue = catalogues[instance_id]
        source_root = Path(__file__).resolve().parents[2] / SOURCE_ATTEMPT
        rebuilt = build_review_package(
            catalogue,
            evidence_mode="etiq_selected_fixed",
            source_setting="source_absent",
            neutral_base=_legacy_package(source_root, instance_id, catalogue["assigned_job_id"]),
        )
        validate_reviewer_response(
            rebuilt,
            {
                "reviews": [
                    {
                        "unit_id": boundary_id,
                        "decision": "trusted",
                        "decision_reason": "deterministic repaired-run review",
                        "evidence_refs": [boundary_id],
                        "trust_level": "trusted_for_reporting",
                        "criteria_outcomes": [],
                        "boundary_health_acknowledged": True,
                        "expand_helper_prefixes": [],
                        "inspect_artifacts": [],
                        "suspect_node_refs": [],
                    }
                    for boundary_id in rebuilt["common_base"]["section"]["assigned_boundary_ids"]
                ]
            },
        )
        repaired_packages += 1
    sandbox_ready = production_python_executor is not None
    stages = {
        "reuse_capture": "passed",
        "catalogue": "passed",
        "package_rendering": "passed",
        "initial_review_stub": "passed",
        "reviewer_response_validation": "passed",
        "operation_follow_up": "passed",
        "nested_helper_expansion": "passed",
        "artifact_read_describe_full": "passed",
        "artifact_python_signed_sandbox": "passed" if sandbox_ready else "failed_closed",
        "repair_selection": "passed",
        "suffix_rerun_selection": "passed",
        "recapture_handoff_reconstruction": "passed",
        "repaired_package": "passed",
        "re_review": "passed",
        "analysis": "passed",
        "replay_resume": "passed",
        "terminal_closure": "terminal_incomplete" if not sandbox_ready else "passed",
    }
    return {
        "status": "passed" if sandbox_ready else "terminal_incomplete",
        "failure_classification": None if sandbox_ready else "sandbox_readiness_failure",
        "failure_stage": None if sandbox_ready else "artifact_python_signed_sandbox",
        "error": None if sandbox_ready else "current signed Tester production sandbox gate is unavailable",
        "model_calls": 0,
        "skips": 0,
        "stages": stages,
        "rendered_requests": rendered_requests,
        "reviewer_response_validations": response_validations,
        "operation_counts": operation_counts,
        "repaired_packages_exercised": repaired_packages,
        "scheduled_initial_reviews": 192,
        "scheduled_repair_traces": 96,
        "repair_suffixes": repair_suffixes,
    }


def terminal_incomplete(stage: str, error: Exception | str) -> dict[str, Any]:
    return {
        "status": "terminal_incomplete",
        "failure_classification": "controller_package_or_capture_failure",
        "failure_stage": str(stage),
        "error": str(error),
    }


def build_corrected_attempt(
    repo_root: Path,
    *,
    tester_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_root = repo_root.resolve() / SOURCE_ATTEMPT
    source_paths = _capture_paths(source_root)
    catalogues = {
        instance_id: build_disclosure_catalogue(_read_json(path))
        for instance_id, path in source_paths.items()
    }
    schedule = experiment_schedule(catalogues.values())
    packages = []
    for item in schedule["packages"]:
        catalogue = catalogues[item["instance_id"]]
        neutral = _legacy_package(
            source_root, item["instance_id"], str(catalogue["assigned_job_id"])
        )
        reviewer_package = build_review_package(
            catalogue,
            evidence_mode=item["evidence_mode"],
            source_setting=item["source_setting"],
            neutral_base=neutral,
        )
        record = {
            "schema_version": "corrected-four-instance-frozen-package-1",
            "controller_condition": deepcopy(item),
            "source_capture_sha256": catalogue["source_capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "reviewer_package": reviewer_package,
        }
        record["package_sha256"] = sha256(record)
        packages.append(record)
    # Only runtime graph evidence is required to be identical between Fixed and Adaptive.
    for instance_id in SELECTED_INSTANCES:
        for source_setting in SOURCE_SETTINGS:
            pair = {
                value["controller_condition"]["evidence_mode"]: value["reviewer_package"]
                for value in packages
                if value["controller_condition"]["instance_id"] == instance_id
                and value["controller_condition"]["source_setting"] == source_setting
                and value["controller_condition"]["evidence_mode"]
                in {"etiq_selected_fixed", "etiq_selected_adaptive"}
            }
            if canonical_json(pair["etiq_selected_fixed"]["runtime_evidence"]) != canonical_json(
                pair["etiq_selected_adaptive"]["runtime_evidence"]
            ):
                raise AssertionError("Fixed and Adaptive initial evidence differs")
    qualification = qualify_packages(packages, catalogues)
    rendered_request_comparisons = verify_rendered_request_comparisons(packages)
    python_executor = None
    sandbox_error = None
    if tester_gate is not None:
        try:
            python_executor = signed_catalogue_python_executor(
                gate=tester_gate,
                expected_gate_sha256=sha256(tester_gate),
                repo_root=repo_root,
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            sandbox_error = f"{type(exc).__name__}: {exc}"
    zero_model_lifecycle = qualify_zero_model_lifecycle(
        packages,
        catalogues,
        schedule,
        production_python_executor=python_executor,
    )
    if sandbox_error:
        zero_model_lifecycle["sandbox_activation_error"] = sandbox_error
    return {
        "catalogues": catalogues,
        "packages": packages,
        "schedule": schedule,
        "qualification": qualification,
        "rendered_request_comparisons": rendered_request_comparisons,
        "zero_model_lifecycle": zero_model_lifecycle,
        "source_capture_files": {
            key: {
                "path": path.relative_to(repo_root).as_posix(),
                "file_sha256": sha256(path.read_bytes()),
            }
            for key, path in source_paths.items()
        },
        "source_instance_files": {
            instance_id: {
                "path": (SOURCE_ATTEMPT / "instances" / f"{instance_id}.json").as_posix(),
                "file_sha256": sha256(
                    (repo_root / SOURCE_ATTEMPT / "instances" / f"{instance_id}.json").read_bytes()
                ),
                "instance_sha256": _read_json(
                    repo_root / SOURCE_ATTEMPT / "instances" / f"{instance_id}.json"
                )["instance_sha256"],
                "source_sha256": _read_json(
                    repo_root / SOURCE_ATTEMPT / "instances" / f"{instance_id}.json"
                )["source_sha256"],
                "mutation_sha256": sha256(
                    _read_json(
                        repo_root / SOURCE_ATTEMPT / "instances" / f"{instance_id}.json"
                    ).get("mutation")
                ),
                "qualification_sha256": _read_json(
                    repo_root / SOURCE_ATTEMPT / "instances" / f"{instance_id}.json"
                )["qualification"]["qualification_sha256"],
            }
            for instance_id in SELECTED_INSTANCES
        },
    }


def write_readiness_report(
    repo_root: Path,
    attempt_root: Path,
    *,
    tester_gate: Mapping[str, Any] | None = None,
) -> Path:
    built = build_corrected_attempt(repo_root.resolve(), tester_gate=tester_gate)
    lifecycle = built["zero_model_lifecycle"]
    report = {
        "schema_version": "corrected-four-instance-readiness-1",
        "status": "ready" if lifecycle["status"] == "passed" else "not_ready",
        "package_qualification": built["qualification"],
        "rendered_request_comparisons": built["rendered_request_comparisons"],
        "zero_model_lifecycle": lifecycle,
        "expected_counts": {"packages": 64, "initial_reviews": 192, "repair_traces": 96},
        "freeze_created": False,
        "live_model_calls_started": False,
        "blocker": None
        if lifecycle["status"] == "passed"
        else "a current independent Tester signature for the modified production sandbox is required",
    }
    report["readiness_sha256"] = sha256(report)
    state = "ready" if report["status"] == "ready" else "not-ready"
    path = (
        attempt_root.resolve()
        / "qualification"
        / f"developer-readiness-{state}-{report['readiness_sha256'][7:23]}.json"
    )
    _write_immutable(path, report)
    return path


def write_zero_model_orchestration_report(
    repo_root: Path,
    attempt_root: Path,
) -> Path:
    """Exercise the live orchestration matrix with deterministic zero-call boundaries."""
    repo_root = repo_root.resolve()
    built = build_corrected_attempt(repo_root)
    schedule = built["schedule"]
    source_captures = {
        instance_id: _read_json(repo_root / details["path"])
        for instance_id, details in built["source_capture_files"].items()
    }
    trial_instances = {
        str(value["trial_id"]): str(value["instance_id"])
        for value in schedule["review_trials"]
    }
    calls = {"review": 0, "repair": 0, "rerun": 0}

    def reviewer(
        request: Mapping[str, Any], *, controller_parent_id: str
    ) -> Mapping[str, Any]:
        calls["review"] += 1
        package = request["reviewer_package"]
        instance_id = trial_instances.get(controller_parent_id)
        suspect = instance_id in {"instance-03", "instance-04"}
        return {
            "usage": {
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_tokens": 0,
                "total_tokens": 2,
            },
            "reviews": [
                {
                    "unit_id": boundary_id,
                    "decision": "suspect" if suspect else "trusted",
                    "decision_reason": "deterministic zero-model orchestration",
                    "evidence_refs": [boundary_id],
                    "trust_level": "provisionally_trusted" if suspect else "trusted_for_reporting",
                    "criteria_outcomes": [],
                    "boundary_health_acknowledged": True,
                    "expand_helper_prefixes": [],
                    "inspect_artifacts": [],
                    "suspect_node_refs": [],
                }
                for boundary_id in package["common_base"]["section"]["assigned_boundary_ids"]
            ],
        }

    def repairer(
        _request: Mapping[str, Any], *, controller_parent_id: str
    ) -> Mapping[str, Any]:
        del controller_parent_id
        calls["repair"] += 1
        return {
            "usage": {
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_tokens": 0,
                "total_tokens": 2,
            }
        }

    def rerunner(
        catalogue: Mapping[str, Any],
        _response: Mapping[str, Any],
        suffix: list[str],
    ) -> Mapping[str, Any]:
        calls["rerun"] += 1
        del suffix
        return deepcopy(source_captures[str(catalogue["instance_id"])])

    with TemporaryDirectory(prefix="corrected-zero-model-") as temporary:
        synthetic = Path(temporary) / "attempt-025"
        for instance_id, catalogue in built["catalogues"].items():
            _write_immutable(synthetic / "catalogues" / f"{instance_id}.json", catalogue)
        for package_record in built["packages"]:
            branch_id = str(package_record["controller_condition"]["branch_id"])
            reviewer_package = package_record["reviewer_package"]
            _write_immutable(
                synthetic / "packages" / branch_id / "reviewer-package.json",
                reviewer_package,
            )
            manifest = {
                key: deepcopy(value)
                for key, value in package_record.items()
                if key != "reviewer_package"
            }
            manifest["reviewer_package_path"] = f"packages/{branch_id}/reviewer-package.json"
            manifest["reviewer_package_sha256"] = sha256(reviewer_package)
            _write_immutable(
                synthetic / "controller-manifests" / f"{branch_id}.json", manifest
            )
        _write_immutable(
            synthetic / "review-design.json",
            {"review_trials": schedule["review_trials"]},
        )
        _write_immutable(
            synthetic / "repair-design.json",
            {"repair_traces": schedule["repair_traces"]},
        )
        terminal_path = execute_resumable_lifecycle(
            repo_root,
            synthetic,
            reviewer=reviewer,
            repairer=repairer,
            rerunner=rerunner,
            tester_gate={},
            _preverified_zero_model=True,
        )
        first_calls = deepcopy(calls)
        resumed_path = execute_resumable_lifecycle(
            repo_root,
            synthetic,
            reviewer=reviewer,
            repairer=repairer,
            rerunner=rerunner,
            tester_gate={},
            _preverified_zero_model=True,
        )
        if calls != first_calls or resumed_path != terminal_path:
            raise ValueError("zero-model exact resume relaunched a completed logical call")
        terminal = _read_json(terminal_path)
        analysis = _read_json(synthetic / "analysis/summary.json")
        replay = _read_json(synthetic / "replay/reconciliation.json")
    report = {
        "schema_version": "corrected-four-instance-zero-model-orchestration-1",
        "status": terminal["status"],
        "real_provider_calls": 0,
        "packages": 64,
        "synthetic_initial_reviews": 192,
        "synthetic_repair_traces": 96,
        "synthetic_repaired_recaptures": calls["rerun"],
        "callback_invocations": calls,
        "operation_qualification": built["zero_model_lifecycle"]["operation_counts"],
        "exact_resume_relaunched_calls": 0,
        "analysis_sha256": analysis["analysis_sha256"],
        "replay_sha256": replay["replay_sha256"],
        "terminal_sha256": terminal["terminal_sha256"],
    }
    report["report_sha256"] = sha256(report)
    path = (
        attempt_root.resolve()
        / "qualification"
        / f"zero-model-orchestration-{report['report_sha256'][7:23]}.json"
    )
    _write_immutable(path, report)
    return path


def write_pre_tester_handoff(
    repo_root: Path,
    attempt_root: Path,
    *,
    tests_passed: int,
    subtests_passed: int,
    focused_tests_passed: int = 0,
    zero_model_report: Path | None = None,
) -> Path:
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    built = build_corrected_attempt(repo_root)
    files = [
        "src/use_case_icp/__main__.py",
        "src/use_case_icp/corrected_experiment.py",
        "src/use_case_icp/fault_operations.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/n07_program.py",
        "src/use_case_icp/n10_program.py",
        "schemas/corrected_four_instance_package.schema.json",
        "schemas/corrected_four_instance_operation.schema.json",
        REVIEW_PROMPT.as_posix(),
        REPAIR_PROMPT.as_posix(),
        REVIEW_SCHEMA.as_posix(),
        REPAIR_SCHEMA.as_posix(),
        "tests/test_corrected_experiment.py",
        "tests/test_n10_program.py",
        "pyproject.toml",
    ]
    if zero_model_report is None:
        candidates = sorted(
            (attempt_root / "qualification").glob("zero-model-orchestration-*.json")
        )
        if not candidates:
            raise ValueError("final handoff requires the zero-model orchestration report")
        zero_model_report = candidates[-1]
    zero_model = _read_json(zero_model_report)
    _verified_self_hash(zero_model, "report_sha256")
    if (
        zero_model.get("real_provider_calls") != 0
        or zero_model.get("packages") != 64
        or zero_model.get("synthetic_initial_reviews") != 192
        or zero_model.get("synthetic_repair_traces") != 96
        or zero_model.get("status") != "completed_experiment_and_analysis"
    ):
        raise ValueError("zero-model orchestration report is incomplete")
    authorities = {}
    for label, relative, expected in (
        ("N14", N14_AUTHORITY, N14_AUTHORITY_SHA256),
        ("N14A", N14A_AUTHORITY, N14A_AUTHORITY_SHA256),
        ("N14 developer task", N14_TASK, N14_TASK_SHA256),
    ):
        observed = sha256((repo_root / relative).read_bytes())
        if observed != expected:
            raise ValueError(f"{label} authority changed before handoff")
        authorities[label] = {"path": relative.as_posix(), "sha256": observed}
    authorities["N14 Tester task"] = {
        "path": N14_TESTER_TASK.as_posix(),
        "sha256": sha256((repo_root / N14_TESTER_TASK).read_bytes()),
    }
    experimental_counts = {
        "scientific_calls": len(list((attempt_root / "ledger/call-attempt").glob("*.json"))),
        "reviews": len(list((attempt_root / "reviews").glob("*.json"))),
        "repairs": len(list((attempt_root / "repairs").glob("*.json"))),
        "results": len(list((attempt_root / "analysis").glob("*.json"))),
    }
    if any(experimental_counts.values()):
        raise ValueError("pre-Tester handoff must precede every scientific record")
    handoff = {
        "schema_version": "corrected-four-instance-n14-developer-handoff-1",
        "status": "awaiting_independent_tester_gate",
        "attempt": attempt_root.name,
        "authorities": authorities,
        "attempt_024_preserved_and_closed_externally": True,
        "attempt_024_tree_sha256": sha256(_tree_hashes(repo_root / ABANDONED_ATTEMPT)),
        "preserved_tester_blocking_report": {
            "path": "outputs/fault-experiments-v2-2-n10/attempt-025/qualification/tester-blocking-artifact-python-positive.json",
            "file_sha256": sha256(
                (
                    attempt_root
                    / "qualification/tester-blocking-artifact-python-positive.json"
                ).read_bytes()
            ),
        },
        "tests": {
            "focused": {
                "command": ".venv/bin/python -m pytest -q tests/test_corrected_experiment.py",
                "passed": focused_tests_passed,
                "failures": 0,
                "skips": 0,
            },
            "full": {
                "command": ".venv/bin/python -m pytest -q",
                "passed": tests_passed,
                "subtests_passed": subtests_passed,
                "failures": 0,
                "skips": 0,
            },
        },
        "governed_files": {
            name: sha256((repo_root / name).read_bytes()) for name in files
        },
        "reused_attempt_023_authorities": {
            "source_capture_files": built["source_capture_files"],
            "source_instance_files": built["source_instance_files"],
        },
        "rendered_packages": {
            "count": len(built["packages"]),
            "hashes": [value["package_sha256"] for value in built["packages"]],
        },
        "schedules": {
            "review_design_sha256": sha256(built["schedule"]["review_trials"]),
            "repair_design_sha256": sha256(built["schedule"]["repair_traces"]),
            "counts": {"packages": 64, "initial_reviews": 192, "repair_traces": 96},
        },
        "zero_model_orchestration": {
            "path": zero_model_report.relative_to(repo_root).as_posix(),
            "file_sha256": sha256(zero_model_report.read_bytes()),
            "report_sha256": zero_model["report_sha256"],
        },
        "model_configuration": {
            "model": PROVIDER_MODEL,
            "reasoning_effort": PROVIDER_REASONING_EFFORT,
        },
        "sandbox_gate_required_bindings": {
            "protocol_content_hash": PROTOCOL_CONTENT_HASH,
            "artifact_python_worker_sha256": sha256(
                _ARTIFACT_PYTHON_WORKER.encode("utf-8")
            ),
            "launch_policy": deepcopy(ARTIFACT_PYTHON_LAUNCH_POLICY),
            "production_launcher_sha256": production_launcher_sha256(
                artifact_python_launcher
            ),
            "launch_policy_sha256": ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
            "sandbox_backend": "bubblewrap",
            "sandbox_backend_version": bubblewrap_version(),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "venv_python_sha256": sha256((repo_root / ".venv/bin/python").resolve().read_bytes()),
        },
        "experimental_counts_before_gate": experimental_counts,
        "freeze_or_live_started": False,
    }
    handoff["handoff_sha256"] = sha256(handoff)
    path = (
        attempt_root.resolve()
        / "qualification"
        / f"developer-to-tester-{handoff['handoff_sha256'][7:23]}.json"
    )
    _write_immutable(path, handoff)
    return path


def _freeze_attempt_026(
    repo_root: Path,
    target: Path,
    tester_gate: Mapping[str, Any],
) -> Path:
    """Copy the exact Attempt-025 experimental material into a new gate envelope."""
    source = repo_root / CORRECTED_ATTEMPT
    authority_hash = sha256((repo_root / N14B_AUTHORITY).read_bytes())
    if authority_hash != N14B_AUTHORITY_SHA256:
        raise ValueError("N14B authority changed")
    expected_authority = {
        "path": N14B_AUTHORITY.as_posix(),
        "sha256": N14B_AUTHORITY_SHA256,
    }
    if tester_gate.get("authorities", {}).get("N14B") != expected_authority:
        raise ValueError("Tester gate lacks the exact N14B Attempt-026 authority")
    signed_catalogue_python_executor(
        gate=tester_gate,
        expected_gate_sha256=sha256(tester_gate),
        repo_root=repo_root,
    )
    required = {
        "packages": "sha256:95437dc67a2d77c4ef3469c7fc31b2743323ff0fa6fdb32965ebfcaec85df7e8",
        "controller-manifests": "sha256:f2ea7f263bf245d39f62c810cffe895264b3e77bfd694978debcdac5847a44b8",
    }
    for relative, expected in required.items():
        if sha256(_tree_hashes(source / relative)) != expected:
            raise ValueError(f"Attempt 025 {relative} tree differs from N14B")
    expected_catalogues = {
        "instance-01": "sha256:0e05bf21825f8eaf1e6821704e326a295fd5ab0cb325ebc8bd340bce25cc6ef6",
        "instance-03": "sha256:c8b56cfcf9fcacbba002288443fa466debe09fb221447a3c57a525fb7a932d2e",
        "instance-04": "sha256:1d0306885763dc01fb4ed795947d8cb44c9c0c18dbc23673b633042738bce666",
        "instance-12": "sha256:4a989ff4e523b7efee28f01a42efd9c054d13a194c0f4b5af6d13aa205e08a72",
    }
    for instance_id, expected in expected_catalogues.items():
        if _read_json(source / "catalogues" / f"{instance_id}.json")["catalogue_sha256"] != expected:
            raise ValueError(f"Attempt 025 catalogue differs from N14B: {instance_id}")
    review_design = _read_json(source / "review-design.json")["review_trials"]
    repair_design = _read_json(source / "repair-design.json")["repair_traces"]
    if sha256(review_design) != "sha256:14af74db4a4bed0a79734b49c3341dca73c83d1a25f653318890c2bb2124e07d":
        raise ValueError("Attempt 025 review design differs from N14B")
    if sha256(repair_design) != "sha256:437daa86f34d0191856aab9471fc5417e69e98d995c53c018869588cf8b159cb":
        raise ValueError("Attempt 025 repair design differs from N14B")
    for relative in ("packages", "controller-manifests", "catalogues"):
        for path in sorted((source / relative).rglob("*")):
            if path.is_file() and not path.is_symlink():
                destination = target / path.relative_to(source)
                create_bytes_exclusive(destination, path.read_bytes())
    for name in ("review-design.json", "repair-design.json"):
        create_bytes_exclusive(target / name, (source / name).read_bytes())
    source_freeze = _read_json(source / "experiment-freeze.json")
    freeze = {
        "schema_version": "corrected-four-instance-freeze-2",
        "status": "frozen_before_first_experimental_review",
        "description": "N14B administrative envelope for unchanged four-instance experiment",
        "attempt": "attempt-026",
        "source_attempt": "attempt-023",
        "source_envelope_attempt": "attempt-025",
        "n14b_authority": expected_authority,
        "attempt_025_freeze_file_sha256": sha256(
            (source / "experiment-freeze.json").read_bytes()
        ),
        "attempt_025_freeze_sha256": source_freeze["freeze_sha256"],
        "source_attempt_authority_files_sha256": source_freeze[
            "source_attempt_authority_files_sha256"
        ],
        "selected_instances": deepcopy(source_freeze["selected_instances"]),
        "source_capture_files": deepcopy(source_freeze["source_capture_files"]),
        "source_instance_files": deepcopy(source_freeze["source_instance_files"]),
        "catalogue_hashes": deepcopy(source_freeze["catalogue_hashes"]),
        "package_hashes": deepcopy(source_freeze["package_hashes"]),
        "review_design_sha256": sha256(review_design),
        "repair_design_sha256": sha256(repair_design),
        "expected_counts": {
            "packages": 64,
            "catalogues": 4,
            "initial_reviews": 192,
            "repair_traces": 96,
        },
        "qualification": deepcopy(source_freeze["qualification"]),
        "rendered_request_comparisons": deepcopy(
            source_freeze["rendered_request_comparisons"]
        ),
        "zero_model_lifecycle": deepcopy(source_freeze["zero_model_lifecycle"]),
        "carried_evidence_only": True,
        "tester_sandbox_gate_sha256": sha256(tester_gate),
        "experimental_review_records_at_freeze": 0,
        "attempt_025_preserved": True,
        "source_attempt_preserved": True,
    }
    freeze["freeze_sha256"] = sha256(freeze)
    path = target / "experiment-freeze.json"
    _write_immutable(path, freeze)
    return path


def freeze_corrected_attempt(
    repo_root: Path,
    output_root: Path | None = None,
    *,
    tester_gate: Mapping[str, Any] | None = None,
) -> Path:
    repo_root = repo_root.resolve()
    target = (output_root or repo_root / CORRECTED_ATTEMPT).resolve()
    source = (repo_root / SOURCE_ATTEMPT).resolve()
    abandoned = (repo_root / ABANDONED_ATTEMPT).resolve()
    if target in {source, abandoned} or source in target.parents or abandoned in target.parents:
        raise ValueError("corrected attempt cannot write below Attempt 023 or Attempt 024")
    if tester_gate is None:
        raise RuntimeError(
            "zero-model lifecycle and freeze require the current signed Tester gate"
        )
    latest_path = str(tester_gate.get("latest_developer_handoff_path") or "")
    latest_hash = str(tester_gate.get("latest_developer_handoff_file_sha256") or "")
    if not latest_path or not latest_hash:
        raise ValueError("Tester gate does not bind the latest Developer handoff")
    handoff_path = (repo_root / latest_path).resolve()
    if target not in handoff_path.parents or sha256(handoff_path.read_bytes()) != latest_hash:
        raise ValueError("Tester gate has a stale Developer handoff binding")
    handoff = _read_json(handoff_path)
    _verified_self_hash(handoff, "handoff_sha256")
    if tester_gate.get("authorities") != handoff.get("authorities"):
        raise ValueError("Tester gate does not bind the handoff's N14/N14A authorities")
    for name, expected in handoff.get("governed_files", {}).items():
        if sha256((repo_root / str(name)).read_bytes()) != expected:
            raise ValueError(f"governed file changed after Tester gate: {name}")
    if target == (repo_root / ATTEMPT_026).resolve():
        return _freeze_attempt_026(repo_root, target, tester_gate)
    # Bind every reused authority file, rather than rehashing the 18 GB of
    # unrelated provider transcripts and results in the closed source attempt.
    authority_paths = [source / "experiment-freeze.json"]
    authority_paths.extend(_capture_paths(source).values())
    authority_paths.extend(
        source / "instances" / f"{instance_id}.json"
        for instance_id in SELECTED_INSTANCES
    )
    before = {
        path.relative_to(source).as_posix(): sha256(path.read_bytes())
        for path in sorted(authority_paths)
    }
    built = build_corrected_attempt(repo_root, tester_gate=tester_gate)
    if built["zero_model_lifecycle"].get("status") != "passed":
        raise RuntimeError("corrected attempt is not freeze-ready: zero-model lifecycle gate failed")
    record_attempt_024_incomplete(repo_root, target)
    for instance_id, catalogue in built["catalogues"].items():
        _write_immutable(target / "catalogues" / f"{instance_id}.json", catalogue)
    for package in built["packages"]:
        branch_id = package["controller_condition"]["branch_id"]
        reviewer_package = package["reviewer_package"]
        _write_immutable(
            target / "packages" / branch_id / "reviewer-package.json",
            reviewer_package,
        )
        manifest = {
            key: deepcopy(value)
            for key, value in package.items()
            if key != "reviewer_package"
        }
        manifest["reviewer_package_path"] = (
            f"packages/{branch_id}/reviewer-package.json"
        )
        manifest["reviewer_package_sha256"] = sha256(reviewer_package)
        _write_immutable(
            target / "controller-manifests" / f"{branch_id}.json", manifest
        )
    _write_immutable(target / "review-design.json", {"review_trials": built["schedule"]["review_trials"]})
    _write_immutable(target / "repair-design.json", {"repair_traces": built["schedule"]["repair_traces"]})
    after = {
        path.relative_to(source).as_posix(): sha256(path.read_bytes())
        for path in sorted(authority_paths)
    }
    if before != after:
        raise RuntimeError("Attempt 023 changed while freezing corrected attempt")
    freeze = {
        "schema_version": "corrected-four-instance-freeze-1",
        "status": "frozen_before_first_experimental_review",
        "description": "smaller four-instance experiment",
        "source_attempt": "attempt-023",
        "attempt": target.name,
        "source_attempt_authority_files_sha256": sha256(before),
        "selected_instances": deepcopy(SELECTED_INSTANCES),
        "source_capture_files": built["source_capture_files"],
        "source_instance_files": built["source_instance_files"],
        "catalogue_hashes": {
            key: value["catalogue_sha256"] for key, value in built["catalogues"].items()
        },
        "package_hashes": [value["package_sha256"] for value in built["packages"]],
        "review_design_sha256": sha256(built["schedule"]["review_trials"]),
        "repair_design_sha256": sha256(built["schedule"]["repair_traces"]),
        "expected_counts": {"packages": 64, "initial_reviews": 192, "repair_traces": 96},
        "qualification": built["qualification"],
        "rendered_request_comparisons": built["rendered_request_comparisons"],
        "zero_model_lifecycle": built["zero_model_lifecycle"],
        "tester_sandbox_gate_sha256": sha256(tester_gate),
        "experimental_review_records_at_freeze": 0,
        "source_attempt_preserved": True,
    }
    freeze["freeze_sha256"] = sha256(freeze)
    _write_immutable(target / "experiment-freeze.json", freeze)
    return target / "experiment-freeze.json"


def verify_frozen_attempt(
    repo_root: Path,
    attempt_root: Path | None = None,
    *,
    tester_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / CORRECTED_ATTEMPT).resolve()
    freeze = _read_json(target / "experiment-freeze.json")
    unsigned_freeze = deepcopy(freeze)
    observed_freeze_hash = unsigned_freeze.pop("freeze_sha256", None)
    if observed_freeze_hash != sha256(unsigned_freeze):
        raise ValueError("corrected experiment freeze hash mismatch")
    if tester_gate is None or freeze.get("tester_sandbox_gate_sha256") != sha256(tester_gate):
        raise ValueError("current Tester gate differs from the gate bound into the freeze")
    if target == (repo_root / ATTEMPT_026).resolve():
        expected_n14b = {
            "path": N14B_AUTHORITY.as_posix(),
            "sha256": N14B_AUTHORITY_SHA256,
        }
        if (
            freeze.get("n14b_authority") != expected_n14b
            or sha256((repo_root / N14B_AUTHORITY).read_bytes())
            != N14B_AUTHORITY_SHA256
        ):
            raise ValueError("Attempt-026 freeze has a stale N14B authority binding")
    source = repo_root / SOURCE_ATTEMPT
    for value in freeze["source_capture_files"].values():
        path = repo_root / str(value["path"])
        if source not in path.resolve().parents or sha256(path.read_bytes()) != value["file_sha256"]:
            raise ValueError("reused source capture file changed")
    for value in freeze["source_instance_files"].values():
        path = repo_root / str(value["path"])
        if source not in path.resolve().parents or sha256(path.read_bytes()) != value["file_sha256"]:
            raise ValueError("reused source instance, mutation, or oracle authority changed")
    catalogues = {}
    for instance_id, expected in freeze["catalogue_hashes"].items():
        catalogue = _read_json(target / "catalogues" / f"{instance_id}.json")
        verify_catalogue(catalogue)
        if catalogue["catalogue_sha256"] != expected:
            raise ValueError("frozen catalogue identity changed")
        catalogues[instance_id] = catalogue
    packages = []
    for path in sorted((target / "controller-manifests").glob("*.json")):
        manifest = _read_json(path)
        reviewer_package = _read_json(target / manifest["reviewer_package_path"])
        if manifest["reviewer_package_sha256"] != sha256(reviewer_package):
            raise ValueError(f"frozen reviewer package hash mismatch: {path.stem}")
        record = {
            **{
                key: value
                for key, value in manifest.items()
                if key not in {"reviewer_package_path", "reviewer_package_sha256"}
            },
            "reviewer_package": reviewer_package,
        }
        unsigned = deepcopy(record)
        observed = unsigned.pop("package_sha256", None)
        if observed != sha256(unsigned):
            raise ValueError(f"frozen package hash mismatch: {path.stem}")
        packages.append(record)
    if sorted(value["package_sha256"] for value in packages) != sorted(freeze["package_hashes"]):
        raise ValueError("frozen package membership changed")
    qualification = qualify_packages(packages, catalogues)
    schedule = {
        "packages": [
            deepcopy(value["controller_condition"])
            for value in packages
        ],
        "review_trials": _read_json(target / "review-design.json")["review_trials"],
        "repair_traces": _read_json(target / "repair-design.json")["repair_traces"],
    }
    python_executor = (
        signed_catalogue_python_executor(
            gate=tester_gate,
            expected_gate_sha256=sha256(tester_gate),
            repo_root=repo_root,
        )
        if tester_gate is not None
        else None
    )
    lifecycle = qualify_zero_model_lifecycle(
        packages,
        catalogues,
        schedule,
        production_python_executor=python_executor,
    )
    return {
        "status": "verified",
        "description": "smaller four-instance experiment",
        "freeze_sha256": observed_freeze_hash,
        "package_count": len(packages),
        "catalogue_count": len(catalogues),
        "qualification": qualification,
        "zero_model_lifecycle": lifecycle,
        "source_attempt_preserved": True,
    }


def _review_operation_requests(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    explicit = response.get("follow_up_requests")
    if explicit is not None:
        return [dict(value) for value in explicit]
    artifact_requests = []
    helper_requests = []
    for review in response.get("reviews", []):
        artifact_requests.extend(
            {
                "node_ref": value["node_ref"],
                "inspection": "read",
                "start": value["start"],
                "count": value["count"],
                "columns": value["columns"],
                "query": value["query"],
            }
            for value in review.get("inspect_artifacts", [])
        )
        helper_requests.extend(
            {
                "operation": "helper_expansion",
                "boundary_id": review["unit_id"],
                "prefixes": [prefix],
            }
            for prefix in review.get("expand_helper_prefixes", [])
        )
    return [
        {
            "operation": "artifact_inspection",
            "requests": artifact_requests[index:index + 2],
        }
        for index in range(0, len(artifact_requests), 2)
    ] + helper_requests


def _normalized_review_response(response: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(response),
        "follow_up_requests": _review_operation_requests(response),
    }


def _invoke_callback(
    callback: Callable[..., Mapping[str, Any]],
    request: Mapping[str, Any],
    controller_parent_id: str,
    **controller_context: Any,
) -> Mapping[str, Any]:
    """Keep controller identity at the Python boundary, never in model material."""
    parameters = inspect.signature(callback).parameters
    accepts_keywords = any(
        value.kind == inspect.Parameter.VAR_KEYWORD for value in parameters.values()
    )
    kwargs: dict[str, Any] = {}
    if accepts_keywords or "controller_parent_id" in parameters:
        kwargs["controller_parent_id"] = controller_parent_id
    if controller_context and (accepts_keywords or "controller_context" in parameters):
        kwargs["controller_context"] = controller_context
    return callback(request, **kwargs)


def _provider_call(
    repo_root: Path,
    attempt_root: Path,
    *,
    kind: str,
    model_request: Mapping[str, Any],
    controller_parent_id: str,
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    """Run one schema-constrained call in a fresh opaque Codex branch."""
    if kind not in {"review", "repair"}:
        raise ValueError(f"unknown corrected provider call class: {kind}")
    leaks = _controller_key_paths(model_request)
    if leaks:
        raise ValueError(f"provider request contains controller-only identifiers: {leaks}")
    prompt_relative = REVIEW_PROMPT if kind == "review" else REPAIR_PROMPT
    schema_relative = REVIEW_SCHEMA if kind == "review" else REPAIR_SCHEMA
    prompt_template = (repo_root / prompt_relative).read_text(encoding="utf-8")
    prompt = (
        prompt_template
        + "\n\nFrozen request:\n"
        + json.dumps(model_request, ensure_ascii=False, sort_keys=True)
    ).encode("utf-8")
    request_root = attempt_root / "provider-requests" / controller_parent_id / kind
    prompt_path = request_root / "prompt.md"
    create_bytes_exclusive(prompt_path, prompt)
    schema_path = repo_root / schema_relative
    codex_location = shutil.which("codex")
    if codex_location is None:
        raise RuntimeError("Codex CLI is required for corrected live execution")
    codex_binary = Path(codex_location).resolve(strict=True)
    codex_runtime_root = codex_binary.parent.parent
    codex_home = source_codex_home or Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    )

    def launch(call_id: str, _request_bytes: bytes) -> Mapping[str, Any]:
        branch_id = stable_id("branch", [controller_parent_id, kind, call_id], 0)
        branch = attempt_root / "provider-branches" / branch_id
        materialize_opaque_branch(
            branch,
            allowlist={"prompt.md": prompt_path, "schema.json": schema_path},
            manifest_identity={
                "branch_id": branch_id,
                "call_id": call_id,
                "call_class": kind,
            },
        )
        copy_codex_auth(branch, source_codex_home=codex_home)
        result = launch_codex_in_branch(
            branch,
            codex_runtime_root=codex_runtime_root,
            prompt_file="prompt.md",
            schema_file="schema.json",
            output_file="response.json",
            model=PROVIDER_MODEL,
            reasoning_effort=PROVIDER_REASONING_EFFORT,
        )
        return {**result, "branch_id": branch_id}

    outcome = run_with_identical_retries(
        attempt_root / "ledger",
        parent_id=controller_parent_id,
        call_class=kind,
        logical_request={
            "model_request_sha256": sha256(model_request),
            "prompt_sha256": sha256(prompt),
            "schema_sha256": sha256_file(schema_path),
            "model": PROVIDER_MODEL,
            "reasoning_effort": PROVIDER_REASONING_EFFORT,
        },
        launch=launch,
    )
    if outcome["status"] != "completed":
        raise RuntimeError(
            f"corrected {kind} provider request failed: {outcome['status']}"
        )
    result = dict(outcome["result"])
    response = dict(result["response"])
    return {
        **response,
        "usage": dict(result["usage"]) if isinstance(result.get("usage"), Mapping) else {},
        "request_sha256": sha256(model_request),
        "ledger_request_sha256": outcome["request_sha256"],
        "call_ids": [str(value["call_id"]) for value in outcome["attempts"]],
        "retry_lineage": [
            {
                key: deepcopy(value.get(key))
                for key in (
                    "call_id",
                    "attempt_index",
                    "status",
                    "failure_classification",
                    "record",
                )
            }
            for value in outcome["attempts"]
        ],
        "attempt_count": len(outcome["attempts"]),
    }


def production_reviewer(
    model_request: Mapping[str, Any],
    *,
    controller_parent_id: str,
    repo_root: Path,
    attempt_root: Path,
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    return _provider_call(
        repo_root,
        attempt_root,
        kind="review",
        model_request=model_request,
        controller_parent_id=controller_parent_id,
        source_codex_home=source_codex_home,
    )


def production_repairer(
    model_request: Mapping[str, Any],
    *,
    controller_parent_id: str,
    repo_root: Path,
    attempt_root: Path,
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    return _provider_call(
        repo_root,
        attempt_root,
        kind="repair",
        model_request=model_request,
        controller_parent_id=controller_parent_id,
        source_codex_home=source_codex_home,
    )


def _capture_rerun(
    instance_id: str,
    jobs: Mapping[str, Any],
    execution: Mapping[str, Any],
    repair_id: str,
) -> dict[str, Any]:
    captured_jobs = {}
    for job_id in jobs:
        item = execution["executions"][job_id]
        captured_jobs[job_id] = {
            "input": _read_json(item.run_dir / "pipeline-input.json"),
            "output": deepcopy(execution["outputs"][job_id]),
            "stdout": (item.run_dir / "pipeline-stdout.log").read_text(encoding="utf-8"),
            "stderr": (item.run_dir / "pipeline-stderr.log").read_text(encoding="utf-8"),
            "snapshot": jsonable(item.snapshot),
            "realization": deepcopy(execution["realizations"][job_id]),
        }
    capture = {
        "schema_version": "1",
        "capture_id": stable_id("rerun-capture", [repair_id, instance_id], 0),
        "instance_id": instance_id,
        "job_ids": list(jobs),
        "jobs": captured_jobs,
        "handoffs": deepcopy(execution["handoffs"]),
        "source_sha256": {
            job_id: sha256(_pipeline_payload(pipeline))
            for job_id, pipeline in jobs.items()
        },
        "canonical": True,
        "attempt_count": 1,
    }
    capture["capture_sha256"] = sha256(capture)
    _verify_capture(capture)
    return capture


def production_rerunner(
    catalogue: Mapping[str, Any],
    repair_response: Mapping[str, Any],
    suffix: list[str],
    *,
    controller_parent_id: str,
    controller_context: Mapping[str, Any],
    repo_root: Path,
    attempt_root: Path,
) -> dict[str, Any]:
    """Apply the selected scope and run the exact dependency suffix with Etiq."""
    instance_id = str(catalogue["instance_id"])
    instances, _, _ = _load_pre_review_state(repo_root / SOURCE_ATTEMPT)
    instance = next(value for value in instances if value["instance_id"] == instance_id)
    ordered_jobs = {
        job_id: instance["jobs"][job_id] for job_id in catalogue["job_order"]
    }
    repaired_job_id = str(catalogue["assigned_job_id"])
    target = dict(controller_context["repair_target"])
    _validate_schema(
        {
            "pipeline": deepcopy(repair_response.get("pipeline")),
            "change_summary": repair_response.get("change_summary"),
        },
        repo_root / REPAIR_SCHEMA,
    )
    replacement_source = _replacement_source_from_response(repair_response, target)
    replacement = _apply_scoped_source_for_job(
        repaired_job_id,
        ordered_jobs[repaired_job_id],
        target,
        replacement_source,
    )
    validate_repair_scope(ordered_jobs[repaired_job_id], replacement, target)
    rerun_jobs = dict(ordered_jobs)
    rerun_jobs[repaired_job_id] = replacement
    if suffix != dependency_suffix(catalogue["job_order"], repaired_job_id):
        raise ValueError("rerunner suffix differs from the frozen explicit dependency order")
    branch_id = stable_id("branch", [controller_parent_id, "repair-rerun"], 0)
    branch = attempt_root / "repair-branches" / branch_id
    fixture = repo_root / EXPERIMENT_ROOT
    materialize_opaque_branch(
        branch,
        allowlist={
            name: fixture / name
            for name in ("scenario.json", "corpus.json", "capabilities.json", "oracles.json")
        },
        manifest_identity={"branch_id": branch_id, "repair_id": controller_parent_id},
    )
    copy_etiq_worker_runtime(branch, repo_root / "src")
    scenario = load_preflight_inputs(repo_root, EXPERIMENT_ROOT)
    canonical_execution = instance["evaluation_execution"]
    canonical_execution = {
        **canonical_execution,
        "executions": {
            job_id: canonical_execution["executions"][job_id]
            for job_id in catalogue["job_order"]
        },
    }
    rerun = _rerun_dependency_suffix(
        branch,
        repo_root=repo_root,
        jobs=rerun_jobs,
        scenario=scenario,
        repaired_job_id=repaired_job_id,
        canonical_execution=canonical_execution,
        run_index=int(controller_context.get("repetition", 1)),
        stage=f"corrected-{controller_parent_id}",
    )
    if not bool(rerun.get("oracle", {}).get("passed")):
        # A scientifically unsuccessful repair remains a valid completed rerun.
        pass
    capture = _capture_rerun(
        instance_id, rerun_jobs, rerun, controller_parent_id
    )
    result = {
        **capture,
        "rerun_oracle": deepcopy(rerun["oracle"]),
        "executed_job_ids": list(suffix),
        "repair_target": target,
        "replacement_source_sha256": sha256(replacement_source.encode("utf-8")),
    }
    result.pop("capture_sha256", None)
    result["capture_sha256"] = sha256(result)
    _verify_capture(result)
    return result


def production_callbacks(
    repo_root: Path,
    attempt_root: Path,
    *,
    source_codex_home: Path | None = None,
) -> tuple[Callable[..., Mapping[str, Any]], Callable[..., Mapping[str, Any]], Callable[..., Mapping[str, Any]]]:
    def reviewer(request: Mapping[str, Any], *, controller_parent_id: str) -> Mapping[str, Any]:
        return production_reviewer(
            request,
            controller_parent_id=controller_parent_id,
            repo_root=repo_root,
            attempt_root=attempt_root,
            source_codex_home=source_codex_home,
        )

    def repairer(request: Mapping[str, Any], *, controller_parent_id: str) -> Mapping[str, Any]:
        return production_repairer(
            request,
            controller_parent_id=controller_parent_id,
            repo_root=repo_root,
            attempt_root=attempt_root,
            source_codex_home=source_codex_home,
        )

    def rerunner(
        catalogue: Mapping[str, Any],
        response: Mapping[str, Any],
        suffix: list[str],
        *,
        controller_parent_id: str,
        controller_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return production_rerunner(
            catalogue,
            response,
            suffix,
            controller_parent_id=controller_parent_id,
            controller_context=controller_context,
            repo_root=repo_root,
            attempt_root=attempt_root,
        )

    return reviewer, repairer, rerunner


def _verified_self_hash(value: Mapping[str, Any], field: str) -> str:
    unsigned = deepcopy(dict(value))
    observed = str(unsigned.pop(field, ""))
    if observed != sha256(unsigned):
        raise ValueError(f"record has an invalid {field}")
    return observed


def _validate_n14c_resume(
    repo_root: Path,
    attempt_root: Path,
    tester_gate: Mapping[str, Any],
) -> Path:
    authority_path = repo_root / N14C_AUTHORITY
    if sha256(authority_path.read_bytes()) != N14C_AUTHORITY_SHA256:
        raise ValueError("N14C authority changed")
    authority = _read_json(authority_path)
    preserved = authority["preserved_state"]
    bindings = {
        "freeze_file_sha256": attempt_root / "experiment-freeze.json",
        "live_consumption_file_sha256": attempt_root / "live-consumption.json",
        "tester_gate_file_sha256": repo_root / preserved["tester_gate_path"],
        "terminal_incomplete_file_sha256": repo_root
        / preserved["terminal_incomplete_path"],
    }
    for field, path in bindings.items():
        if sha256(path.read_bytes()) != preserved[field]:
            raise ValueError(f"N14C preserved binding changed: {field}")
    for path, field, self_hash in (
        (
            attempt_root / "experiment-freeze.json",
            "freeze_logical_sha256",
            "freeze_sha256",
        ),
        (
            attempt_root / "live-consumption.json",
            "live_consumption_logical_sha256",
            "consumption_sha256",
        ),
        (
            repo_root / preserved["terminal_incomplete_path"],
            "terminal_incomplete_logical_sha256",
            "terminal_sha256",
        ),
    ):
        if _verified_self_hash(_read_json(path), self_hash) != preserved[field]:
            raise ValueError(f"N14C preserved binding changed: {field}")
    if sha256(tester_gate) != preserved["tester_gate_logical_sha256"]:
        raise ValueError("N14C resume must use the preserved Tester gate")
    for field, relative in (
        ("package_tree_sha256", "packages"),
        ("controller_manifest_tree_sha256", "controller-manifests"),
        ("catalogue_tree_sha256", "catalogues"),
    ):
        if sha256(_tree_hashes(attempt_root / relative)) != preserved[field]:
            raise ValueError(f"N14C preserved binding changed: {field}")
    review_files = list((attempt_root / "reviews").glob("*.json"))
    call_files = list((attempt_root / "ledger/call-attempt").glob("*.json"))
    if len(review_files) == 80 and (
        sha256(_tree_hashes(attempt_root / "reviews"))
        != preserved["review_tree_sha256"]
    ):
        raise ValueError("N14C preserved review tree changed before resume")
    if len(call_files) == 91 and (
        sha256(_tree_hashes(attempt_root / "ledger/call-attempt"))
        != preserved["call_attempt_tree_sha256"]
    ):
        raise ValueError("N14C preserved call tree changed before resume")
    for value in authority["blocked_trial"]["preserved_calls_in_order"]:
        if sha256((repo_root / value["path"]).read_bytes()) != value["file_sha256"]:
            raise ValueError("N14C blocked-trial call changed")
    corrections = sorted(
        (attempt_root / "post-live").glob("n14c-follow-up-cap-correction-*.json")
    )
    if len(corrections) != 1:
        raise ValueError("N14C exact resume requires one post-live correction")
    correction = _read_json(corrections[0])
    _verified_self_hash(correction, "correction_sha256")
    if correction.get("n14c_authority") != {
        "path": N14C_AUTHORITY.as_posix(),
        "sha256": N14C_AUTHORITY_SHA256,
    } or correction.get("preserved_state") != preserved:
        raise ValueError("N14C correction has stale authority bindings")
    expected_before = {
        "src/use_case_icp/corrected_experiment.py": "sha256:3617b4d1a3d5ad8a38f571d6e2da5533632b8500d5120bda5c9f6cdfc0a61672",
        "src/use_case_icp/fault_operations.py": "sha256:6bdae9ed7453f28f56b26a724bcb75b99329dc48a520e8734172b7c93665d902",
        "tests/test_corrected_experiment.py": "sha256:c741e95b780227c150feaa57d1f1237420ca56597433fd37f29555214a7a3bb1",
    }
    for name, before in expected_before.items():
        delta = correction.get("code_delta", {}).get(name, {})
        if (
            delta.get("before_sha256") != before
            or delta.get("after_sha256") != sha256((repo_root / name).read_bytes())
        ):
            raise ValueError(f"N14C correction does not bind the code delta: {name}")
    if correction.get("replacement_calls") != 0:
        raise ValueError("N14C correction permits no replacement calls")
    return attempt_root / "live-consumption.json"


def create_live_consumption(
    repo_root: Path,
    attempt_root: Path,
    tester_gate: Mapping[str, Any],
) -> Path:
    """Exclusively bind the one authorized live run before its first call."""
    if (
        attempt_root.resolve() == (repo_root / ATTEMPT_026).resolve()
        and (attempt_root / "live-consumption.json").is_file()
    ):
        return _validate_n14c_resume(repo_root, attempt_root, tester_gate)
    authority_bindings = {}
    for label, relative, expected in (
        ("N14", N14_AUTHORITY, N14_AUTHORITY_SHA256),
        ("N14A", N14A_AUTHORITY, N14A_AUTHORITY_SHA256),
        ("N14 developer task", N14_TASK, N14_TASK_SHA256),
    ):
        observed = sha256((repo_root / relative).read_bytes())
        if observed != expected:
            raise ValueError(f"{label} authority changed")
        authority_bindings[label] = {"path": relative.as_posix(), "sha256": observed}
    authority_bindings["N14 Tester task"] = {
        "path": N14_TESTER_TASK.as_posix(),
        "sha256": sha256((repo_root / N14_TESTER_TASK).read_bytes()),
    }
    if attempt_root.resolve() == (repo_root / ATTEMPT_026).resolve():
        observed = sha256((repo_root / N14B_AUTHORITY).read_bytes())
        if observed != N14B_AUTHORITY_SHA256:
            raise ValueError("N14B authority changed")
        authority_bindings["N14B"] = {
            "path": N14B_AUTHORITY.as_posix(),
            "sha256": observed,
        }
    freeze = _read_json(attempt_root / "experiment-freeze.json")
    freeze_sha256 = _verified_self_hash(freeze, "freeze_sha256")
    gate_sha256 = sha256(tester_gate)
    if freeze.get("tester_sandbox_gate_sha256") != gate_sha256:
        raise ValueError("live gate differs from the gate bound into the freeze")
    latest_path = str(tester_gate.get("latest_developer_handoff_path") or "")
    latest_hash = str(tester_gate.get("latest_developer_handoff_file_sha256") or "")
    if not latest_path or not latest_hash:
        raise ValueError("Tester gate does not bind the latest Developer handoff")
    handoff_path = (repo_root / latest_path).resolve()
    if attempt_root not in handoff_path.parents or sha256(handoff_path.read_bytes()) != latest_hash:
        raise ValueError("Tester gate has a stale Developer handoff binding")
    handoff = _read_json(handoff_path)
    _verified_self_hash(handoff, "handoff_sha256")
    for name, expected in handoff.get("governed_files", {}).items():
        if sha256((repo_root / str(name)).read_bytes()) != expected:
            raise ValueError(f"governed file changed after Tester gate: {name}")
    if tester_gate.get("authorities") != authority_bindings:
        raise ValueError("Tester gate does not bind the exact N14/N14A authorities")
    governed = [
        "src/use_case_icp/__main__.py",
        "src/use_case_icp/corrected_experiment.py",
        "src/use_case_icp/fault_operations.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/n07_program.py",
        REVIEW_PROMPT.as_posix(),
        REPAIR_PROMPT.as_posix(),
        REVIEW_SCHEMA.as_posix(),
        REPAIR_SCHEMA.as_posix(),
        "schemas/corrected_four_instance_package.schema.json",
        "schemas/corrected_four_instance_operation.schema.json",
    ]
    controller_hashes = _tree_hashes(attempt_root / "controller-manifests")
    package_hashes = _tree_hashes(attempt_root / "packages")
    record = {
        "schema_version": "corrected-four-instance-live-consumption-1",
        "status": "consumed_for_exact_live_or_resume",
        "authorities": authority_bindings,
        "latest_developer_handoff": {"path": latest_path, "file_sha256": latest_hash},
        "tester_gate_sha256": gate_sha256,
        "freeze_sha256": freeze_sha256,
        "governed_files": {name: sha256((repo_root / name).read_bytes()) for name in governed},
        "controller_manifest_tree_sha256": sha256(controller_hashes),
        "reviewer_package_tree_sha256": sha256(package_hashes),
        "review_design_file_sha256": sha256((attempt_root / "review-design.json").read_bytes()),
        "repair_design_file_sha256": sha256((attempt_root / "repair-design.json").read_bytes()),
        "model": PROVIDER_MODEL,
        "reasoning_effort": PROVIDER_REASONING_EFFORT,
        "output_root": attempt_root.relative_to(repo_root).as_posix(),
        "expected_counts": {"packages": 64, "initial_reviews": 192, "repair_traces": 96},
        "source_attempt_authority_files_sha256": freeze["source_attempt_authority_files_sha256"],
    }
    record["consumption_sha256"] = sha256(record)
    path = attempt_root / "live-consumption.json"
    _write_immutable(path, record)
    return path


def _repair_scope_for_selected_boundary(
    repo_root: Path,
    catalogue: Mapping[str, Any],
    reviewer_boundary_id: str,
) -> tuple[dict[str, Any], Any]:
    binding = next(
        value
        for value in catalogue["jobs"][catalogue["assigned_job_id"]]["boundary_bindings"]
        if str(value["reviewer_boundary_id"]) == reviewer_boundary_id
    )
    captured_id = str(binding["captured_boundary_id"])
    realized = next(
        value
        for value in catalogue["jobs"][catalogue["assigned_job_id"]]["realized_boundaries"]
        if str(value["boundary_id"]) == captured_id
    )
    instances, _, _ = _load_pre_review_state(repo_root / SOURCE_ATTEMPT)
    instance = next(
        value for value in instances if value["instance_id"] == catalogue["instance_id"]
    )
    pipeline = instance["jobs"][catalogue["assigned_job_id"]]
    target = source_scope(
        pipeline,
        function_name=str(realized["static_identity"]["qualified_function_name"]).split(".")[-1],
        mode="boundary",
    )
    return target, pipeline


def _repair_model_request(
    package: Mapping[str, Any],
    receipt: Mapping[str, Any],
    target: Mapping[str, Any],
    pipeline: Any,
) -> dict[str, Any]:
    selected_source = {
        **dict(target),
        "content": _source_for_scope(pipeline, target),
    }
    selected_declaration = next(
        value
        for value in package["common_base"]["semantic_declarations"]
        if str(value["function_name"]) == str(target["function_name"])
    )
    request = {
        "selected_source": selected_source,
        "review_receipt": deepcopy(dict(receipt)),
        "neutral_task_contract": {
            "review_task": deepcopy(package["common_base"].get("review_task")),
            "behavioural_criteria": deepcopy(
                package["common_base"].get("behavioural_criteria", [])
            ),
            "semantic_declaration": deepcopy(selected_declaration),
        },
        "response_contract": {
            "pipeline.entry_file": str(target["file"]),
            "pipeline.files": "exactly one selected-source replacement",
            "pipeline.files[0].path": str(target["file"]),
            "pipeline.files[0].content": "complete replacement text for selected_source only",
            "pipeline.review_boundaries": [],
        },
    }
    leaks = _controller_key_paths(request)
    if leaks:
        raise ValueError(f"repair request contains controller-only identifiers: {leaks}")
    return request


def execute_resumable_lifecycle(
    repo_root: Path,
    attempt_root: Path,
    *,
    reviewer: Callable[..., Mapping[str, Any]],
    repairer: Callable[..., Mapping[str, Any]],
    rerunner: Callable[..., Mapping[str, Any]],
    tester_gate: Mapping[str, Any],
    _preverified_zero_model: bool = False,
) -> Path:
    """Run or resume all frozen review and repair records with injected live boundaries."""
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    n14c_resume = (
        attempt_root == (repo_root / ATTEMPT_026).resolve()
        and (attempt_root / "live-consumption.json").is_file()
    )
    if n14c_resume:
        _validate_n14c_resume(repo_root, attempt_root, tester_gate)
    verified = (
        {"zero_model_lifecycle": {"status": "passed"}}
        if _preverified_zero_model or n14c_resume
        else verify_frozen_attempt(repo_root, attempt_root, tester_gate=tester_gate)
    )
    if verified["zero_model_lifecycle"].get("status") != "passed":
        raise RuntimeError("frozen attempt no longer passes its zero-model lifecycle gate")
    live_frozen = (attempt_root / "experiment-freeze.json").is_file()
    if live_frozen:
        create_live_consumption(repo_root, attempt_root, tester_gate)
    python_executor = (
        signed_catalogue_python_executor(
            gate=tester_gate,
            expected_gate_sha256=sha256(tester_gate),
            repo_root=repo_root,
        )
        if live_frozen
        else None
    )
    packages = {
        path.stem: {
            **{
                key: value
                for key, value in _read_json(path).items()
                if key not in {"reviewer_package_path", "reviewer_package_sha256"}
            },
            "reviewer_package": _read_json(
                attempt_root / _read_json(path)["reviewer_package_path"]
            ),
        }
        for path in sorted((attempt_root / "controller-manifests").glob("*.json"))
    }
    catalogues = {
        path.stem: _read_json(path)
        for path in sorted((attempt_root / "catalogues").glob("*.json"))
    }
    review_design = _read_json(attempt_root / "review-design.json")["review_trials"]
    repair_design = _read_json(attempt_root / "repair-design.json")["repair_traces"]
    review_records = {}
    token_records = []
    for trial in review_design:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.is_file():
            record = _read_json(path)
            _verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("invalid partial or mismatched review record")
        else:
            package_record = packages[str(trial["branch_id"])]
            package = package_record["reviewer_package"]
            initial = _normalized_review_response(
                _invoke_callback(
                    reviewer,
                    render_provider_request(package),
                    str(trial["trial_id"]),
                )
            )

            def follow_up(
                request: Mapping[str, Any], *, controller_parent_id: str = ""
            ) -> Mapping[str, Any]:
                return _normalized_review_response(
                    _invoke_callback(
                        reviewer,
                        render_provider_request(
                            request["reviewer_package"],
                            operation_response=request["operation_response"],
                        ),
                        controller_parent_id,
                    )
                )

            followed = run_follow_up_loop(
                catalogue=catalogues[str(trial["instance_id"])],
                package=package,
                initial_response=initial,
                reviewer=follow_up,
                controller_parent_id=str(trial["trial_id"]),
                python_executor=python_executor,
            )
            validation = validate_reviewer_response(
                followed["package"], followed["response"]
            )
            record = {
                "schema_version": "corrected-four-instance-review-1",
                "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "receipt": validation["receipt"],
                "selected_suspect_boundary_id": validation["selected_suspect_boundary_id"],
                "operation_events": followed["operation_events"],
                "call_records": followed["call_records"],
                "usage": followed["usage"],
                "fault_detected": bool(validation["suspect_boundary_ids"]),
                "status": "complete",
            }
            record["review_sha256"] = sha256(record)
            _write_immutable(path, record)
        review_records[(trial["branch_id"], trial["repetition"])] = record
        token_records.extend(record.get("usage", {}).get("calls", []))
    repair_records = []
    for repair in repair_design:
        path = attempt_root / "repairs" / f"{repair['repair_id']}.json"
        if path.is_file():
            record = _read_json(path)
            _verified_self_hash(record, "repair_sha256")
            if record.get("controller_repair") != repair or record.get("status") != "complete":
                raise ValueError("invalid partial or mismatched repair record")
            repair_records.append(record)
            token_records.extend(record.get("usage", {}).get("calls", []))
            continue
        package_record = packages[str(repair["branch_id"])]
        package = package_record["reviewer_package"]
        review = review_records[(repair["branch_id"], repair["repetition"])]
        suspect = review.get("selected_suspect_boundary_id")
        catalogue = catalogues[str(repair["instance_id"])]
        reverse = {
            value["reviewer_boundary_id"]: value["captured_boundary_id"]
            for value in catalogue["jobs"][catalogue["assigned_job_id"]]["boundary_bindings"]
        }
        if suspect not in reverse:
            record = {
                "schema_version": "corrected-four-instance-repair-1",
                "controller_repair": deepcopy(repair),
                "paired_review_sha256": review["review_sha256"],
                "selected_suspect_boundary_id": suspect,
                "repair_attempted": False,
                "repair_success_without_regression": False,
                "failure_classification": "no_valid_reviewer_selected_boundary",
                "call_records": [],
                "usage": aggregate_actual_usage([]),
                "status": "complete",
            }
            record["repair_sha256"] = sha256(record)
            _write_immutable(path, record)
            repair_records.append(record)
            continue
        if live_frozen:
            target, pipeline = _repair_scope_for_selected_boundary(
                repo_root, catalogue, str(suspect)
            )
            model_request = _repair_model_request(
                package, review["receipt"], target, pipeline
            )
        else:
            target = {"file": "synthetic", "function_name": "synthetic"}
            model_request = {
                "reviewer_package": package,
                "review_receipt": review["receipt"],
                "selected_suspect_boundary_id": suspect,
            }
        repair_response = dict(
            _invoke_callback(
                repairer,
                model_request,
                str(repair["repair_id"]),
            )
        )
        repair_usage = actual_usage_record(
            repair_response, purpose="repair", phase="repair"
        )
        suffix = dependency_suffix(catalogue["job_order"], catalogue["assigned_job_id"])
        rerunner_parameters = inspect.signature(rerunner).parameters
        rerunner_kwargs: dict[str, Any] = {}
        if live_frozen and ("controller_parent_id" in rerunner_parameters or any(
            value.kind == inspect.Parameter.VAR_KEYWORD
            for value in rerunner_parameters.values()
        )):
            rerunner_kwargs = {
                "controller_parent_id": str(repair["repair_id"]),
                "controller_context": {
                    "repair_target": target,
                    "repetition": int(repair["repetition"]),
                    "selected_realized_boundary_id": reverse[suspect],
                },
            }
        recapture = dict(rerunner(catalogue, repair_response, suffix, **rerunner_kwargs))
        _verify_capture(recapture)
        if recapture.get("executed_job_ids", suffix) != suffix:
            raise ValueError("rerunner did not execute the exact dependency suffix")
        rebuilt_catalogue = build_disclosure_catalogue(recapture)
        rebuilt_package = build_review_package(
            rebuilt_catalogue,
            evidence_mode=str(repair["evidence_mode"]),
            source_setting=str(repair["source_setting"]),
            neutral_base=repair_response.get("neutral_base")
            or _legacy_package(
                repo_root / SOURCE_ATTEMPT,
                str(repair["instance_id"]),
                str(catalogue["assigned_job_id"]),
            ),
        )
        re_review_response = _normalized_review_response(
            _invoke_callback(
                reviewer,
                render_provider_request(rebuilt_package),
                f"{repair['repair_id']}-re-review",
            )
        )
        def re_follow_up(
            request: Mapping[str, Any], *, controller_parent_id: str = ""
        ) -> Mapping[str, Any]:
            return _normalized_review_response(
                _invoke_callback(
                    reviewer,
                    render_provider_request(
                        request["reviewer_package"],
                        operation_response=request["operation_response"],
                    ),
                    controller_parent_id,
                )
            )

        re_followed = run_follow_up_loop(
            catalogue=rebuilt_catalogue,
            package=rebuilt_package,
            initial_response=re_review_response,
            reviewer=re_follow_up,
            phase="repaired_run",
            controller_parent_id=f"{repair['repair_id']}-re-review",
            python_executor=python_executor,
        )
        re_review = validate_reviewer_response(
            re_followed["package"], re_followed["response"]
        )
        usage = aggregate_actual_usage(
            [repair_usage, *re_followed["usage"]["calls"]]
        )
        oracle_passed = bool(recapture.get("rerun_oracle", {}).get("passed"))
        no_regression = not bool(re_review["suspect_boundary_ids"])
        record = {
            "schema_version": "corrected-four-instance-repair-1",
            "controller_repair": deepcopy(repair),
            "paired_review_sha256": review["review_sha256"],
            "selected_suspect_boundary_id": suspect,
            "selected_realized_boundary_id": reverse[suspect],
            "repair_target": target,
            "repair_attempted": True,
            "rerun_job_ids": suffix,
            "recapture_sha256": recapture["capture_sha256"],
            "rerun_oracle": deepcopy(recapture.get("rerun_oracle")),
            "repaired_package_sha256": sha256(rebuilt_package),
            "re_review_receipt": re_review["receipt"],
            "re_review_operation_events": re_followed["operation_events"],
            "repair_success_without_regression": oracle_passed and no_regression,
            "call_records": [
                {
                    key: deepcopy(repair_response.get(key))
                    for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count")
                    if repair_response.get(key) is not None
                },
                *re_followed["call_records"],
            ],
            "usage": usage,
            "status": "complete",
        }
        record["repair_sha256"] = sha256(record)
        _write_immutable(path, record)
        repair_records.append(record)
        token_records.extend(usage["calls"])
    if len(packages) != 64 or len(review_records) != 192 or len(repair_records) != 96:
        raise ValueError("observed package, review, or repair counts are incomplete")
    all_call_ids = [
        str(call_id)
        for record in [*review_records.values(), *repair_records]
        for call in record.get("call_records", [])
        for call_id in call.get("call_ids", [])
    ]
    if len(all_call_ids) != len(set(all_call_ids)):
        raise ValueError("duplicate scientific call identity detected")
    if live_frozen:
        for call_id in all_call_ids:
            verify_record(
                attempt_root / "ledger",
                record_type="call-attempt",
                record_id=call_id,
            )
    rows = []
    for record in review_records.values():
        condition = record["controller_trial"]
        instance_id = str(condition["instance_id"])
        faulty = instance_id in {"instance-03", "instance-04"}
        detected = bool(record["fault_detected"])
        truth = None
        if faulty and live_frozen:
            instance_record = _read_json(
                repo_root / SOURCE_ATTEMPT / "instances" / f"{instance_id}.json"
            )
            mutation = instance_record["mutation"]
            bindings = catalogues[instance_id]["jobs"][mutation["target_job_id"]]["boundary_bindings"]
            truth = next(
                str(value["reviewer_boundary_id"])
                for value in bindings
                if str(value["frozen_realized_identity"]["qualified_function_name"])
                == str(mutation["site"]["qualified_function_name"])
            )
        rows.append(
            {
                **deepcopy(condition),
                "assignment": SELECTED_INSTANCES[instance_id],
                "designation": "fault" if faulty else "control",
                "detected": detected,
                "false_positive": detected and not faulty,
                "exact_boundary_localisation": faulty
                and record.get("selected_suspect_boundary_id") == truth,
                "usage": deepcopy(record["usage"]),
            }
        )

    if live_frozen and not all_call_ids:
        raise ValueError("live records lack scientific call lineage")

    def grouped(fields: tuple[str, ...]) -> list[dict[str, Any]]:
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(tuple(row[field] for field in fields), []).append(row)
        return [
            {
                **dict(zip(fields, key)),
                "n": len(values),
                "detections": sum(value["detected"] for value in values),
                "false_positives": sum(value["false_positive"] for value in values),
                "exact_boundary_localisations": sum(
                    value["exact_boundary_localisation"] for value in values
                ),
            }
            for key, values in sorted(groups.items())
        ]

    comparisons = [
        {"name": "placebo_current_run_vs_history_empty", "left": "current_run", "right": "history_empty"},
        {"name": "placebo_etiq_empty_vs_current_run", "left": "etiq_empty", "right": "current_run"},
        {"name": "history_full_vs_history_empty", "left": "history_full", "right": "history_empty"},
        {"name": "fixed_vs_empty", "left": "etiq_selected_fixed", "right": "etiq_empty"},
        {"name": "adaptive_vs_fixed", "left": "etiq_selected_adaptive", "right": "etiq_selected_fixed"},
        {"name": "random_vs_fixed", "left": "etiq_random_matched", "right": "etiq_selected_fixed"},
        {"name": "full_vs_empty", "left": "etiq_full", "right": "etiq_empty"},
    ]
    for comparison in comparisons:
        left = [value for value in rows if value["evidence_mode"] == comparison["left"]]
        right = [value for value in rows if value["evidence_mode"] == comparison["right"]]
        comparison["detection_rate_difference"] = (
            sum(value["detected"] for value in left) / len(left)
            - sum(value["detected"] for value in right) / len(right)
        )
    analysis = {
        "schema_version": "corrected-four-instance-analysis-1",
        "sample_size_limitation": "Four instances are a small experiment; estimates are descriptive and not population-powered.",
        "review_count": len(review_records),
        "repair_trace_count": len(repair_records),
        "headline_outcomes": {
            "fault_detection": {
                "numerator": sum(value["detected"] and value["designation"] == "fault" for value in rows),
                "denominator": sum(value["designation"] == "fault" for value in rows),
            },
            "control_false_positives": {
                "numerator": sum(value["false_positive"] for value in rows),
                "denominator": sum(value["designation"] == "control" for value in rows),
            },
            "exact_boundary_localisation": {
                "numerator": sum(value["exact_boundary_localisation"] for value in rows),
                "denominator": sum(value["designation"] == "fault" for value in rows),
            },
            "repair_success_without_regression": {
                "numerator": sum(value.get("repair_success_without_regression", False) for value in repair_records),
                "denominator": len(repair_records),
            },
        },
        "results_by": {
            "evidence_mode": grouped(("evidence_mode",)),
            "source_setting": grouped(("source_setting",)),
            "assignment": grouped(("assignment",)),
            "fault_control": grouped(("designation",)),
            "instance": grouped(("instance_id",)),
            "repetition": grouped(("repetition",)),
            "full_cells": grouped(("evidence_mode", "source_setting", "assignment", "designation", "instance_id", "repetition")),
        },
        "contrasts": comparisons,
        "raw_token_usage": token_records,
        "actual_usage": aggregate_actual_usage(token_records),
    }
    analysis["analysis_sha256"] = sha256(analysis)
    _write_immutable(attempt_root / "analysis/summary.json", analysis)
    replay = {
        "schema_version": "corrected-four-instance-replay-1",
        "review_hashes": sorted(value["review_sha256"] for value in review_records.values()),
        "repair_hashes": sorted(value["repair_sha256"] for value in repair_records),
        "observed_counts": {
            "packages": len(packages),
            "initial_reviews": len(review_records),
            "repair_traces": len(repair_records),
            "logical_call_ids": len(all_call_ids),
        },
        "all_record_hashes_recomputed": True,
        "duplicate_logical_calls": False,
    }
    replay["replay_sha256"] = sha256(replay)
    _write_immutable(attempt_root / "replay/reconciliation.json", replay)
    terminal = {
        "schema_version": "corrected-four-instance-terminal-1",
        "status": "completed_experiment_and_analysis",
        "package_count": len(packages),
        "review_count": len(review_records),
        "repair_trace_count": len(repair_records),
        "analysis_sha256": analysis["analysis_sha256"],
        "replay_sha256": replay["replay_sha256"],
    }
    terminal["terminal_sha256"] = sha256(terminal)
    _write_immutable(attempt_root / "terminal-state.json", terminal)
    return attempt_root / "terminal-state.json"


def run_corrected_lifecycle(
    repo_root: Path,
    attempt_root: Path,
    *,
    reviewer: Callable[..., Mapping[str, Any]],
    repairer: Callable[..., Mapping[str, Any]],
    rerunner: Callable[..., Mapping[str, Any]],
    tester_gate: Mapping[str, Any],
) -> Path:
    """Turn controller/package/capture/sandbox exceptions into terminal-incomplete state."""
    try:
        return execute_resumable_lifecycle(
            repo_root,
            attempt_root,
            reviewer=reviewer,
            repairer=repairer,
            rerunner=rerunner,
            tester_gate=tester_gate,
        )
    except Exception as exc:
        terminal = {
            "schema_version": "corrected-four-instance-terminal-1",
            "status": "terminal_incomplete",
            "failure_classification": "controller_package_capture_or_sandbox_failure",
            "failure_stage": "resumable_lifecycle",
            "error": f"{type(exc).__name__}: {exc}",
            "model_repair_failure": False,
            "completed_review_records": len(list((attempt_root / "reviews").glob("*.json"))),
            "completed_repair_records": len(list((attempt_root / "repairs").glob("*.json"))),
        }
        terminal["terminal_sha256"] = sha256(terminal)
        path = (
            attempt_root.resolve()
            / "terminal"
            / f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"
        )
        _write_immutable(path, terminal)
        return path


# N15: downstream-first, two-job review path.  The production provider and
# sandbox boundaries above are intentionally reused without modification.


def _verify_n15_authority(repo_root: Path) -> dict[str, str]:
    bindings = {
        "N15 task": (N15_TASK, N15_TASK_SHA256),
        "N15 authority": (N15_AUTHORITY, N15_AUTHORITY_SHA256),
        "historical N14B gate": (N15_HISTORICAL_GATE, N15_HISTORICAL_GATE_FILE_SHA256),
    }
    result = {}
    for label, (relative, expected) in bindings.items():
        observed = sha256((repo_root / relative).read_bytes())
        if observed != expected:
            raise ValueError(f"{label} changed")
        result[label] = observed
    for relative, expected in N15_PROTECTED_FILE_SHA256.items():
        if sha256((repo_root / relative).read_bytes()) != expected:
            raise RuntimeError(f"N15 protected boundary changed: {relative}")
    historical_gate = _read_json(repo_root / N15_HISTORICAL_GATE)
    current_isolation = {
        "artifact_python_worker_sha256": sha256(_ARTIFACT_PYTHON_WORKER.encode("utf-8")),
        "production_launcher_sha256": production_launcher_sha256(
            artifact_python_launcher
        ),
        "launch_policy_sha256": ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "model_configuration": {
            "model": PROVIDER_MODEL,
            "reasoning_effort": PROVIDER_REASONING_EFFORT,
        },
    }
    for field, observed in current_isolation.items():
        if historical_gate.get(field) != observed:
            raise RuntimeError(f"N15 isolation boundary changed: {field}")
    if (PROVIDER_MODEL, PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise RuntimeError("N15 model configuration changed")
    return result


def _catalogue_for_job(catalogue: Mapping[str, Any], job_id: str) -> dict[str, Any]:
    if job_id not in catalogue["jobs"]:
        raise ValueError("job is absent from two-job catalogue")
    value = deepcopy(dict(catalogue))
    value["assigned_job_id"] = job_id
    value.pop("catalogue_sha256", None)
    value["catalogue_sha256"] = sha256(value)
    return value


def _n15_boundary_bindings(catalogue: Mapping[str, Any]) -> list[dict[str, str]]:
    order = list(map(str, catalogue["job_order"]))
    rendered = []
    for job_id in reversed(order):
        job = catalogue["jobs"][job_id]
        boundaries = {
            str(value["boundary_id"]): value for value in job["realized_boundaries"]
        }
        for binding in job["boundary_bindings"]:
            captured = str(binding["captured_boundary_id"])
            if _realized_boundary_binding(boundaries[captured]) != binding:
                raise ValueError("frozen two-job boundary binding changed")
            rendered.append(
                {
                    "job_id": job_id,
                    "job_position": "downstream" if job_id == order[-1] else "upstream",
                    "captured_boundary_id": captured,
                    "reviewer_boundary_id": str(binding["reviewer_boundary_id"]),
                    "function_name": str(boundaries[captured]["function_name"]),
                    "qualified_function_name": str(
                        boundaries[captured]["static_identity"]["qualified_function_name"]
                    ),
                }
            )
    if len(rendered) != 6 or len({x["reviewer_boundary_id"] for x in rendered}) != 6:
        raise ValueError("N15 requires six unique two-job boundary bindings")
    return rendered


def _tag_job_projection(projection: Mapping[str, Any], job_id: str) -> dict[str, Any]:
    value = deepcopy(dict(projection))
    value["nodes"] = [{**node, "job_id": job_id} for node in value["nodes"]]
    value["relationships"] = [
        {**edge, "job_id": job_id} for edge in value["relationships"]
    ]
    for child in value.get("collapsed_children", []):
        child["job_id"] = job_id
    value.pop("projection_sha256", None)
    value["projection_sha256"] = sha256(value)
    return value


def _combine_n15_projections(
    catalogue: Mapping[str, Any], projections: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    order = list(map(str, catalogue["job_order"]))
    downstream_first = list(reversed(order))
    tagged = {
        job_id: _tag_job_projection(projections[job_id], job_id)
        for job_id in downstream_first
    }
    node_refs = [
        str(node["node_ref"])
        for job_id in downstream_first
        for node in tagged[job_id]["nodes"]
    ]
    edge_refs = [
        str(edge["relationship_ref"])
        for job_id in downstream_first
        for edge in tagged[job_id]["relationships"]
    ]
    if len(node_refs) != len(set(node_refs)) or len(edge_refs) != len(set(edge_refs)):
        raise ValueError("combined two-job graph identifiers are not unique")
    result = {
        "job_evidence_order": downstream_first,
        "nodes": [
            node for job_id in downstream_first for node in tagged[job_id]["nodes"]
        ],
        "relationships": [
            edge
            for job_id in downstream_first
            for edge in tagged[job_id]["relationships"]
        ],
        "handoffs": deepcopy(list(catalogue["handoffs"])),
        "collapsed_children": [
            child
            for job_id in downstream_first
            for child in tagged[job_id].get("collapsed_children", [])
        ],
        "visible_evidence_by_boundary": {
            key: value
            for job_id in downstream_first
            for key, value in tagged[job_id]
            .get("visible_evidence_by_boundary", {})
            .items()
        },
    }
    if len(result["handoffs"]) != 2:
        raise ValueError("N15 graph requires both exact-hash handoffs")
    result["projection_sha256"] = sha256(result)
    return result


def n15_selected_projection(
    catalogue: Mapping[str, Any],
    *,
    expanded_prefixes_by_job: Mapping[str, Mapping[str, Iterable[Iterable[str]]]] | None = None,
) -> dict[str, Any]:
    maps = _n15_boundary_maps(catalogue)
    projections = {}
    for job_id in catalogue["job_order"]:
        per_job = _catalogue_for_job(catalogue, str(job_id))
        projection = selected_projection(
            per_job,
            expanded_prefixes_by_boundary=(expanded_prefixes_by_job or {}).get(
                str(job_id), {}
            ),
        )
        projections[str(job_id)] = _remap_projection_boundaries(
            projection, maps[str(job_id)]
        )
    return _combine_n15_projections(catalogue, projections)


def n15_full_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    maps = _n15_boundary_maps(catalogue)
    return _combine_n15_projections(
        catalogue,
        {
            str(job_id): _remap_projection_boundaries(
                full_projection(_catalogue_for_job(catalogue, str(job_id))),
                maps[str(job_id)],
            )
            for job_id in catalogue["job_order"]
        },
    )


def _n15_boundary_maps(catalogue: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    return {
        str(job_id): _review_boundary_map(
            _catalogue_for_job(catalogue, str(job_id)), {}
        )
        for job_id in catalogue["job_order"]
    }


def n15_random_matched_projection(
    catalogue: Mapping[str, Any], fixed: Mapping[str, Any]
) -> dict[str, Any]:
    """Oracle-blind combined-pool sample with Fixed's exact structural counts."""
    node_by_ref: dict[str, tuple[str, Mapping[str, Any]]] = {}
    edge_by_ref: dict[str, tuple[str, Mapping[str, Any]]] = {}
    mandatory_nodes: set[str] = set()
    mandatory_edges: set[str] = set()
    eligible_nodes: set[str] = set()
    eligible_edges: set[str] = set()
    for job_id in map(str, catalogue["job_order"]):
        job = catalogue["jobs"][job_id]
        node_by_ref.update({str(x["node_ref"]): (job_id, x) for x in job["nodes"]})
        edge_by_ref.update(
            {str(x["relationship_ref"]): (job_id, x) for x in job["relationships"]}
        )
        for boundary in job["realized_boundaries"]:
            mandatory_nodes.add(str(boundary["matched_function_node_ref"]))
            mandatory_edges.update(
                map(
                    str,
                    list(boundary["input_relationship_refs"])
                    + list(boundary["output_relationship_refs"]),
                )
            )
            eligible_nodes.update(map(str, boundary["node_refs"]))
            eligible_edges.update(map(str, boundary["relationship_refs"]))
    for ref in mandatory_edges | eligible_edges:
        edge = edge_by_ref[ref][1]
        mandatory_nodes.update(
            {str(edge["source_ref"]), str(edge["target_ref"])}
            if ref in mandatory_edges
            else set()
        )
        eligible_nodes.update({str(edge["source_ref"]), str(edge["target_ref"])})
    eligible_nodes |= mandatory_nodes
    eligible_edges |= mandatory_edges
    eligible_edges.update(
        ref
        for ref, (_, edge) in edge_by_ref.items()
        if str(edge["source_ref"]) in eligible_nodes
        and str(edge["target_ref"]) in eligible_nodes
    )
    target_nodes = len(fixed["nodes"])
    target_edges = len(fixed["relationships"])
    if len(mandatory_nodes) > target_nodes or len(mandatory_edges) > target_edges:
        raise ValueError("combined Fixed budget is below mandatory two-job interface")
    generator = random.Random(
        int(sha256([catalogue["source_capture_sha256"], "n15-combined-random"])[7:23], 16)
    )
    candidates = sorted(eligible_nodes - mandatory_nodes)
    chosen_nodes = chosen_edges = None
    for _ in range(20_000):
        generator.shuffle(candidates)
        node_set = mandatory_nodes | set(candidates[: target_nodes - len(mandatory_nodes)])
        possible = [
            ref
            for ref in eligible_edges - mandatory_edges
            if {
                str(edge_by_ref[ref][1]["source_ref"]),
                str(edge_by_ref[ref][1]["target_ref"]),
            }
            <= node_set
        ]
        if len(node_set) == target_nodes and len(possible) >= target_edges - len(mandatory_edges):
            generator.shuffle(possible)
            chosen_nodes = node_set
            chosen_edges = mandatory_edges | set(possible[: target_edges - len(mandatory_edges)])
            break
    if chosen_nodes is None or chosen_edges is None:
        chosen_nodes = {str(x["node_ref"]) for x in fixed["nodes"]}
        chosen_edges = {str(x["relationship_ref"]) for x in fixed["relationships"]}
    nodes = [
        {**structural_node(node_by_ref[ref][1]), "job_id": node_by_ref[ref][0]}
        for ref in sorted(chosen_nodes, key=lambda x: (-catalogue["job_order"].index(node_by_ref[x][0]), x))
    ]
    edges = [
        {**structural_relationship(edge_by_ref[ref][1]), "job_id": edge_by_ref[ref][0]}
        for ref in sorted(chosen_edges, key=lambda x: (-catalogue["job_order"].index(edge_by_ref[x][0]), x))
    ]
    target_bytes = len(canonical_json({"nodes": fixed["nodes"], "relationships": fixed["relationships"]}))
    observed_bytes = len(canonical_json({"nodes": nodes, "relationships": edges}))
    result = {
        "job_evidence_order": list(reversed(catalogue["job_order"])),
        "nodes": nodes,
        "relationships": edges,
        "handoffs": deepcopy(list(catalogue["handoffs"])),
        "collapsed_children": [],
        "visible_evidence_by_boundary": {},
        "random_match": {
            "scope": "combined_two_job_pool",
            "combined_fixed_projection_sha256": fixed["projection_sha256"],
            "target_structural_utf8_bytes": target_bytes,
            "observed_structural_utf8_bytes": observed_bytes,
            "absolute_byte_difference": abs(target_bytes - observed_bytes),
            "target_node_count": target_nodes,
            "target_relationship_count": target_edges,
            "node_count_matched": len(nodes) == target_nodes,
            "relationship_count_matched": len(edges) == target_edges,
            "eligible_nodes_sha256": sha256(sorted(eligible_nodes)),
            "eligible_relationships_sha256": sha256(sorted(eligible_edges)),
            "uses_fault_or_oracle_truth": False,
        },
    }
    result["projection_sha256"] = sha256(result)
    return result


def _n15_common_base(
    catalogue: Mapping[str, Any], neutral_base: Mapping[str, Any]
) -> dict[str, Any]:
    order = list(map(str, catalogue["job_order"]))
    upstream, downstream = order
    bindings = _n15_boundary_bindings(catalogue)
    declarations = []
    for binding in bindings:
        job = catalogue["jobs"][binding["job_id"]]
        boundary = next(
            x
            for x in job["realized_boundaries"]
            if str(x["boundary_id"]) == binding["captured_boundary_id"]
        )
        declarations.append(
            {
                "boundary_id": binding["reviewer_boundary_id"],
                "job_id": binding["job_id"],
                "job_position": binding["job_position"],
                "function_name": str(boundary["function_name"]),
                "role": str(boundary["role"]),
                "expected_inputs": deepcopy(boundary["expected_inputs"]),
                "expected_outputs": deepcopy(boundary["expected_outputs"]),
            }
        )
    handoffs = [
        {
            "handoff_name": str(value["handoff_id"]),
            "upstream_job_id": str(value["upstream_job_id"]),
            "downstream_job_id": str(value["downstream_job_id"]),
            "direction": "upstream_to_downstream",
        }
        for value in catalogue["handoffs"]
    ]
    common = deepcopy(neutral_base["common_base"])
    common["review_task"] = N15_TASK_TEXT
    common["assigned_job"] = {
        "job_id": downstream,
        "observation_point": "downstream",
        "input": deepcopy(catalogue["jobs"][downstream]["input"]),
        "output": deepcopy(catalogue["jobs"][downstream]["output"]),
        "stdout": str(catalogue["jobs"][downstream]["stdout"]),
        "stderr": str(catalogue["jobs"][downstream]["stderr"]),
    }
    common["ordered_job_topology"] = [
        {"job_id": downstream, "position": "downstream", "observation_point": True},
        {"job_id": upstream, "position": "upstream", "observation_point": False},
    ]
    common["review_scope_sequence"] = [
        {
            "kind": "job_boundaries",
            "job_id": downstream,
            "boundary_ids": [x["boundary_id"] for x in declarations if x["job_id"] == downstream],
        },
        {"kind": "handoffs", "handoffs": handoffs},
        {
            "kind": "job_boundaries",
            "job_id": upstream,
            "boundary_ids": [x["boundary_id"] for x in declarations if x["job_id"] == upstream],
        },
    ]
    common["semantic_declarations"] = declarations
    common["section"] = {
        **{
            key: deepcopy(value)
            for key, value in common["section"].items()
            if key not in {"assigned_boundary_ids", "context_boundary_ids"}
        },
        "organization": {"kind": "downstream_first_two_job_boundaries"},
        "assigned_boundary_ids": [x["boundary_id"] for x in declarations],
        "context_boundary_ids": [],
    }
    return common


def build_n15_review_package(
    catalogue: Mapping[str, Any],
    *,
    evidence_mode: str,
    source_setting: str,
    neutral_base: Mapping[str, Any],
) -> dict[str, Any]:
    if evidence_mode not in EVIDENCE_MODES or source_setting not in SOURCE_SETTINGS:
        raise ValueError("unknown N15 condition")
    package: dict[str, Any] = {
        "schema_version": "corrected-four-instance-package-2",
        "common_base": _n15_common_base(catalogue, neutral_base),
        "available_operations": [
            *(["artifact_inspection"] if evidence_mode in GRAPH_MODES - {"etiq_empty"} else []),
            *(["helper_expansion"] if evidence_mode == "etiq_selected_adaptive" else []),
        ],
        "prior_task_records": (
            [
                {
                    "input": deepcopy(catalogue["jobs"][catalogue["job_order"][0]]["input"]),
                    "output": deepcopy(catalogue["jobs"][catalogue["job_order"][0]]["output"]),
                    "stdout": str(catalogue["jobs"][catalogue["job_order"][0]]["stdout"]),
                    "stderr": str(catalogue["jobs"][catalogue["job_order"][0]]["stderr"]),
                }
            ]
            if evidence_mode == "history_full"
            else []
        ),
    }
    if source_setting == "source_present":
        source = deepcopy(neutral_base["source_bundle"])
        if len(source) != 2:
            raise ValueError("N15 Source Present requires both complete source files")
        package["source_bundle"] = source
    if evidence_mode in GRAPH_MODES:
        if evidence_mode == "etiq_empty":
            projection = {
                "job_evidence_order": list(reversed(catalogue["job_order"])),
                "nodes": [],
                "relationships": [],
                "handoffs": [],
                "collapsed_children": [],
                "visible_evidence_by_boundary": {},
            }
            projection["projection_sha256"] = sha256(projection)
        elif evidence_mode == "etiq_full":
            projection = n15_full_projection(catalogue)
        else:
            fixed = n15_selected_projection(catalogue)
            projection = (
                n15_random_matched_projection(catalogue, fixed)
                if evidence_mode == "etiq_random_matched"
                else fixed
            )
        package["runtime_evidence"] = projection
    package["allowed_evidence_refs"] = sorted(
        x["boundary_id"] for x in package["common_base"]["semantic_declarations"]
    )
    _validate_schema(package, PACKAGE_SCHEMA)
    return package


def n15_schedule(catalogues: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = {str(x["instance_id"]) for x in catalogues}
    if values != set(SELECTED_INSTANCES):
        raise ValueError("N15 requires exactly four selected instances")
    packages = [
        {
            "instance_id": instance_id,
            "evidence_mode": mode,
            "source_setting": source,
            "branch_id": f"brn-{sha256(['n15', instance_id, mode, source])[7:23]}",
        }
        for instance_id in SELECTED_INSTANCES
        for mode in EVIDENCE_MODES
        for source in SOURCE_SETTINGS
    ]
    reviews = [
        {
            **package,
            "repetition": repetition,
            "trial_id": f"trial-{sha256(['n15', package['branch_id'], repetition])[7:23]}",
        }
        for package in packages
        for repetition in range(1, 4)
    ]
    if (len(packages), len(reviews)) != (64, 192):
        raise AssertionError("N15 review matrix changed")
    return {"packages": packages, "review_trials": reviews, "repair_traces": []}


def build_n15_attempt(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    _verify_n15_authority(repo_root)
    source_root = repo_root / SOURCE_ATTEMPT
    source_paths = _capture_paths(source_root)
    catalogues = {}
    for instance_id, path in source_paths.items():
        if sha256(path.read_bytes()) != N15_CAPTURE_FILE_SHA256[instance_id]:
            raise ValueError(f"N15 source capture changed: {instance_id}")
        catalogues[instance_id] = build_disclosure_catalogue(_read_json(path))
    schedule = n15_schedule(catalogues.values())
    packages = []
    for item in schedule["packages"]:
        catalogue = catalogues[item["instance_id"]]
        neutral = _legacy_package(
            source_root,
            str(item["instance_id"]),
            str(catalogue["assigned_job_id"]),
        )
        reviewer_package = build_n15_review_package(
            catalogue,
            evidence_mode=str(item["evidence_mode"]),
            source_setting=str(item["source_setting"]),
            neutral_base=neutral,
        )
        record = {
            "schema_version": "n15-downstream-first-frozen-package-1",
            "controller_condition": deepcopy(item),
            "source_capture_sha256": catalogue["source_capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "reviewer_package": reviewer_package,
        }
        record["package_sha256"] = sha256(record)
        packages.append(record)
    qualification = qualify_n15_packages(packages, catalogues, schedule)
    return {
        "catalogues": catalogues,
        "packages": packages,
        "schedule": schedule,
        "qualification": qualification,
        "source_capture_files": {
            key: {
                "path": path.relative_to(repo_root).as_posix(),
                "file_sha256": sha256(path.read_bytes()),
            }
            for key, path in source_paths.items()
        },
    }


def qualify_n15_packages(
    packages: Iterable[Mapping[str, Any]],
    catalogues: Mapping[str, Mapping[str, Any]],
    schedule: Mapping[str, Any],
) -> dict[str, Any]:
    values = list(packages)
    if (len(catalogues), len(values), len(schedule["review_trials"]), len(schedule["repair_traces"])) != (4, 64, 192, 0):
        raise ValueError("N15 count invariant failed")
    by_condition = {
        (
            x["controller_condition"]["instance_id"],
            x["controller_condition"]["evidence_mode"],
            x["controller_condition"]["source_setting"],
        ): x["reviewer_package"]
        for x in values
    }
    for record in values:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        catalogue = catalogues[str(condition["instance_id"])]
        ids = package["common_base"]["section"]["assigned_boundary_ids"]
        if len(ids) != 6 or set(ids) != {
            x["reviewer_boundary_id"] for x in _n15_boundary_bindings(catalogue)
        }:
            raise ValueError("N15 package does not expose exactly six boundaries")
        if package["common_base"]["assigned_job"]["job_id"] != catalogue["job_order"][-1]:
            raise ValueError("N15 package is not downstream-first")
        runtime = package.get("runtime_evidence")
        if runtime and runtime["nodes"]:
            if {x["job_id"] for x in runtime["nodes"]} != set(catalogue["job_order"]):
                raise ValueError("N15 graph lacks one job")
            if runtime["handoffs"] != catalogue["handoffs"]:
                raise ValueError("N15 graph lacks exact frozen handoffs")
        if len(canonical_json(record)) > MAX_PACKAGE_BYTES:
            raise ValueError("N15 package exceeds existing byte gate")
        render_provider_request(package)
    for instance_id in SELECTED_INSTANCES:
        for source in SOURCE_SETTINGS:
            fixed = by_condition[(instance_id, "etiq_selected_fixed", source)]
            adaptive = by_condition[(instance_id, "etiq_selected_adaptive", source)]
            if canonical_json(fixed["runtime_evidence"]) != canonical_json(adaptive["runtime_evidence"]):
                raise ValueError("N15 Fixed and Adaptive bytes differ")
            random_package = by_condition[(instance_id, "etiq_random_matched", source)]
            match = random_package["runtime_evidence"]["random_match"]
            if not match["node_count_matched"] or not match["relationship_count_matched"]:
                raise ValueError("N15 Random does not match combined Fixed")
            if len(by_condition[(instance_id, "history_full", source)]["prior_task_records"]) != 1:
                raise ValueError("N15 History Full lacks its upstream record")
            if by_condition[(instance_id, "history_empty", source)]["prior_task_records"]:
                raise ValueError("N15 History Empty is not empty")
        for mode in EVIDENCE_MODES:
            present = by_condition[(instance_id, mode, "source_present")]
            absent = by_condition[(instance_id, mode, "source_absent")]
            if _differing_top_level_keys(present, absent) != {"source_bundle"}:
                raise ValueError("N15 source pair differs outside source bundle")
        current = by_condition[(instance_id, "current_run", "source_absent")]
        history_empty = by_condition[(instance_id, "history_empty", "source_absent")]
        history_full = by_condition[(instance_id, "history_full", "source_absent")]
        graph_empty = by_condition[(instance_id, "etiq_empty", "source_absent")]
        fixed = by_condition[(instance_id, "etiq_selected_fixed", "source_absent")]
        adaptive = by_condition[(instance_id, "etiq_selected_adaptive", "source_absent")]
        if current != history_empty:
            raise ValueError("N15 Current and History Empty placebo requests differ")
        if _differing_top_level_keys(history_full, history_empty) != {"prior_task_records"}:
            raise ValueError("N15 history pair differs outside history payload")
        if _differing_top_level_keys(graph_empty, current) != {"runtime_evidence"}:
            raise ValueError("N15 Graph Empty differs outside graph envelope")
        if _differing_top_level_keys(fixed, graph_empty) != {"runtime_evidence", "available_operations"}:
            raise ValueError("N15 Fixed differs outside graph and operation payloads")
        if _differing_top_level_keys(adaptive, fixed) != {"available_operations"}:
            raise ValueError("N15 Adaptive differs from Fixed outside capability metadata")
    return {
        "status": "passed",
        "model_calls": 0,
        "catalogue_count": 4,
        "package_count": 64,
        "review_count": 192,
        "repair_count": 0,
        "downstream_first": True,
        "six_boundary_scope": True,
    }


def expand_n15_helper(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if "helper_expansion" not in package.get("available_operations", []):
        raise ValueError("helper expansion is unavailable in this reviewer package")
    prefixes = list(request.get("prefixes", []))
    if len(prefixes) != 1:
        raise ValueError("exactly one direct child must be requested")
    reviewer_id = str(request.get("boundary_id") or "")
    requested = list(map(str, prefixes[0]))
    runtime = package.get("runtime_evidence", {})
    collapsed = {
        (str(x["boundary_id"]), tuple(map(str, x["func_stack"])), str(x["job_id"]))
        for x in runtime.get("collapsed_children", [])
    }
    binding = next(
        (x for x in _n15_boundary_bindings(catalogue) if x["reviewer_boundary_id"] == reviewer_id),
        None,
    )
    if binding is None or (reviewer_id, tuple(requested), binding["job_id"]) not in collapsed:
        raise ValueError("helper expansion must target a current bound direct child")
    reverse = {
        value: (job_id, captured)
        for job_id, mapping in _n15_boundary_maps(catalogue).items()
        for captured, value in mapping.items()
    }
    expanded: dict[str, dict[str, list[list[str]]]] = {
        str(job_id): {} for job_id in catalogue["job_order"]
    }
    roots = {
        (str(job_id), str(x["boundary_id"])): canonical_stack(x["matched_prefix"])
        for job_id in catalogue["job_order"]
        for x in catalogue["jobs"][job_id]["realized_boundaries"]
    }
    for visible_id, details in runtime.get("visible_evidence_by_boundary", {}).items():
        job_id, captured = reverse[str(visible_id)]
        expanded[job_id][captured] = [
            list(map(str, prefix))
            for prefix in details.get("visible_prefixes", [])
            if canonical_stack(prefix) != roots[(job_id, captured)]
        ]
    job_id, captured = reverse[reviewer_id]
    expanded[job_id].setdefault(captured, []).append(requested)
    projection = n15_selected_projection(
        catalogue, expanded_prefixes_by_job=expanded
    )
    old_nodes = {str(x["node_ref"]) for x in runtime.get("nodes", [])}
    old_edges = {str(x["relationship_ref"]) for x in runtime.get("relationships", [])}
    updated = deepcopy(dict(package))
    updated["runtime_evidence"] = projection
    _validate_schema(updated, PACKAGE_SCHEMA)
    return updated, {
        "operation": "helper_expansion",
        "status": "completed",
        "boundary_id": reviewer_id,
        "resolved_job_id": job_id,
        "prefix": requested,
        "nodes_added": [str(x["node_ref"]) for x in projection["nodes"] if str(x["node_ref"]) not in old_nodes],
        "relationships_added": [str(x["relationship_ref"]) for x in projection["relationships"] if str(x["relationship_ref"]) not in old_edges],
    }


def perform_n15_operation(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    python_executor: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation = str(request.get("operation") or "")
    try:
        _validate_schema(request, OPERATION_SCHEMA)
        if operation == "helper_expansion":
            return expand_n15_helper(catalogue, package, request)
        if operation != "artifact_inspection":
            raise ValueError(f"illegal operation request: {operation}")
        evidence = []
        for value in request.get("requests", []):
            ref = str(value.get("node_ref") or "")
            owners = [
                str(job_id)
                for job_id in catalogue["job_order"]
                if any(str(node["node_ref"]) == ref for node in catalogue["jobs"][job_id]["nodes"])
            ]
            if len(owners) != 1:
                raise ValueError("artifact node does not resolve to exactly one bound job")
            result = inspect_catalogue_artifact(
                _catalogue_for_job(catalogue, owners[0]),
                package,
                value,
                python_executor=python_executor,
            )
            evidence.append({**result, "resolved_job_id": owners[0]})
        return deepcopy(dict(package)), {
            "operation": operation,
            "status": "completed",
            "request_count": len(evidence),
            "artifact_bytes_returned": sum(x["artifact_bytes_returned"] for x in evidence),
            "returned_rows": sum(int(x.get("returned_rows", 0)) for x in evidence),
            "returned_columns": sum(int(x.get("returned_columns", 0)) for x in evidence),
            "returned_document_characters": sum(int(x.get("returned_document_characters", 0)) for x in evidence),
            "full_data_requested": any(x.get("full_data_requested") is True for x in evidence),
            "python_analysis_requested": any(x.get("python_analysis_requested") is True for x in evidence),
            "evidence": evidence,
        }
    except (KeyError, TypeError, ValueError) as exc:
        return deepcopy(dict(package)), {
            "operation": operation,
            "status": "rejected",
            "error": str(exc),
            "nodes_added": [],
            "relationships_added": [],
        }


def run_n15_follow_up_loop(
    *,
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    initial_response: Mapping[str, Any],
    reviewer: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    controller_parent_id: str,
    python_executor: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    follow_up_index = 0

    def call(request: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal follow_up_index
        follow_up_index += 1
        return _invoke_callback(
            reviewer,
            request,
            f"{controller_parent_id}-follow-up-{follow_up_index:02d}",
        )

    return run_catalogue_follow_ups(
        catalogue=catalogue,
        package=package,
        initial_response=initial_response,
        reviewer=call,
        operation=lambda current_catalogue, current_package, request: perform_n15_operation(
            current_catalogue,
            current_package,
            request,
            python_executor=python_executor,
        ),
        phase="initial_review",
    )


def validate_n15_reviewer_response(
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_reviewer_response(package, response)
    selected = validation["selected_suspect_boundary_id"]
    binding = next(
        (x for x in _n15_boundary_bindings(catalogue) if x["reviewer_boundary_id"] == selected),
        None,
    )
    return {
        **validation,
        "selected_job_id": binding["job_id"] if binding else None,
        "selected_job_position": binding["job_position"] if binding else None,
        "selected_function_name": binding["function_name"] if binding else None,
    }


def score_n15_top_suspect(
    catalogue: Mapping[str, Any],
    instance_record: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    mutation = instance_record.get("mutation")
    if not mutation:
        return {
            "designation": "control",
            "fault_detected": bool(validation["suspect_boundary_ids"]),
            "false_positive": bool(validation["suspect_boundary_ids"]),
            "correct_job_localisation": False,
            "exact_boundary_localisation": False,
            "truth_job_id": None,
            "truth_reviewer_boundary_id": None,
            "truth_function_name": None,
        }
    truth_job = str(mutation["target_job_id"])
    qualified = str(mutation["site"]["qualified_function_name"])
    truth = next(
        x
        for x in _n15_boundary_bindings(catalogue)
        if x["job_id"] == truth_job and x["qualified_function_name"] == qualified
    )
    return {
        "designation": "upstream_fault" if truth_job == catalogue["job_order"][0] else "downstream_fault",
        "fault_detected": bool(validation["suspect_boundary_ids"]),
        "false_positive": False,
        "correct_job_localisation": validation.get("selected_job_id") == truth_job,
        "exact_boundary_localisation": validation.get("selected_suspect_boundary_id") == truth["reviewer_boundary_id"],
        "truth_job_id": truth_job,
        "truth_reviewer_boundary_id": truth["reviewer_boundary_id"],
        "truth_function_name": truth["function_name"],
    }


def _load_n15_frozen(attempt_root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    catalogues = {
        path.stem: _read_json(path)
        for path in sorted((attempt_root / "catalogues").glob("*.json"))
    }
    packages = {}
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = _read_json(path)
        reviewer_package = _read_json(attempt_root / manifest["reviewer_package_path"])
        if sha256(reviewer_package) != manifest["reviewer_package_sha256"]:
            raise ValueError("N15 frozen reviewer package changed")
        record = {
            **{k: v for k, v in manifest.items() if k not in {"reviewer_package_path", "reviewer_package_sha256"}},
            "reviewer_package": reviewer_package,
        }
        unsigned = deepcopy(record)
        if unsigned.pop("package_sha256", None) != sha256(unsigned):
            raise ValueError("N15 frozen package record changed")
        packages[path.stem] = record
        records.append(record)
    return catalogues, packages, records


def freeze_n15_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT_027).resolve()
    if target != (repo_root / ATTEMPT_027).resolve():
        raise ValueError("N15 freeze is authorized only for Attempt 027")
    if target.exists() and any(target.iterdir()):
        raise ValueError("Attempt 027 already contains artifacts; freeze is one-use")
    authorities = _verify_n15_authority(repo_root)
    preserved = {
        name: sha256(_tree_hashes(repo_root / "outputs/fault-experiments-v2-2-n10" / name))
        for name in ("attempt-023", "attempt-025", "attempt-026")
    }
    built = build_n15_attempt(repo_root)
    for instance_id, catalogue in built["catalogues"].items():
        _write_immutable(target / "catalogues" / f"{instance_id}.json", catalogue)
    for record in built["packages"]:
        branch_id = record["controller_condition"]["branch_id"]
        _write_immutable(target / "packages" / branch_id / "reviewer-package.json", record["reviewer_package"])
        manifest = {k: deepcopy(v) for k, v in record.items() if k != "reviewer_package"}
        manifest["reviewer_package_path"] = f"packages/{branch_id}/reviewer-package.json"
        manifest["reviewer_package_sha256"] = sha256(record["reviewer_package"])
        _write_immutable(target / "controller-manifests" / f"{branch_id}.json", manifest)
    _write_immutable(target / "review-design.json", {"review_trials": built["schedule"]["review_trials"]})
    _write_immutable(target / "repair-design.json", {"repair_traces": []})
    if preserved != {
        name: sha256(_tree_hashes(repo_root / "outputs/fault-experiments-v2-2-n10" / name))
        for name in preserved
    }:
        raise RuntimeError("a preserved attempt changed during N15 freeze")
    freeze = {
        "schema_version": "n15-downstream-first-freeze-1",
        "status": "frozen_before_first_experimental_review",
        "attempt": "attempt-027",
        "source_attempt": "attempt-023",
        "authority_bindings": authorities,
        "n15_authority": {"path": N15_AUTHORITY.as_posix(), "sha256": N15_AUTHORITY_SHA256},
        "source_capture_files": built["source_capture_files"],
        "catalogue_hashes": {k: v["catalogue_sha256"] for k, v in built["catalogues"].items()},
        "package_hashes": [x["package_sha256"] for x in built["packages"]],
        "review_design_sha256": sha256(built["schedule"]["review_trials"]),
        "repair_design_sha256": sha256([]),
        "expected_counts": {"catalogues": 4, "packages": 64, "reviews": 192, "repairs": 0},
        "qualification": built["qualification"],
        "protected_file_hashes_before_and_after_patch": deepcopy(N15_PROTECTED_FILE_SHA256),
        "code_hashes": {
            "src/use_case_icp/corrected_experiment.py": sha256((repo_root / "src/use_case_icp/corrected_experiment.py").read_bytes()),
            "src/use_case_icp/__main__.py": sha256((repo_root / "src/use_case_icp/__main__.py").read_bytes()),
            "tests/test_corrected_experiment.py": sha256((repo_root / "tests/test_corrected_experiment.py").read_bytes()),
        },
        "preserved_attempt_tree_hashes": preserved,
        "historical_isolation_gate_file_sha256": N15_HISTORICAL_GATE_FILE_SHA256,
        "model": PROVIDER_MODEL,
        "reasoning_effort": PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0,
    }
    freeze["freeze_sha256"] = sha256(freeze)
    path = target / "experiment-freeze.json"
    _write_immutable(path, freeze)
    return path


def verify_n15_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT_027).resolve()
    _verify_n15_authority(repo_root)
    freeze = _read_json(target / "experiment-freeze.json")
    observed = _verified_self_hash(freeze, "freeze_sha256")
    if freeze.get("n15_authority") != {"path": N15_AUTHORITY.as_posix(), "sha256": N15_AUTHORITY_SHA256}:
        raise ValueError("N15 freeze authority changed")
    for relative, expected in freeze["code_hashes"].items():
        if sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N15 frozen code changed: {relative}")
    for instance_id, binding in freeze["source_capture_files"].items():
        if binding["file_sha256"] != N15_CAPTURE_FILE_SHA256[instance_id] or sha256((repo_root / binding["path"]).read_bytes()) != binding["file_sha256"]:
            raise ValueError("N15 source capture binding changed")
    catalogues, _, records = _load_n15_frozen(target)
    for instance_id, catalogue in catalogues.items():
        verify_catalogue(catalogue)
        if catalogue["catalogue_sha256"] != freeze["catalogue_hashes"][instance_id]:
            raise ValueError("N15 catalogue changed")
    schedule = {
        "review_trials": _read_json(target / "review-design.json")["review_trials"],
        "repair_traces": _read_json(target / "repair-design.json")["repair_traces"],
    }
    qualification = qualify_n15_packages(records, catalogues, schedule)
    if sorted(x["package_sha256"] for x in records) != sorted(freeze["package_hashes"]):
        raise ValueError("N15 package membership changed")
    if sha256(schedule["review_trials"]) != freeze["review_design_sha256"] or sha256(schedule["repair_traces"]) != freeze["repair_design_sha256"]:
        raise ValueError("N15 schedule changed")
    return {
        "status": "verified",
        "freeze_sha256": observed,
        "qualification": qualification,
        "package_count": 64,
        "review_count": 192,
        "repair_count": 0,
    }


def create_n15_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    path = attempt_root / "live-consumption.json"
    if path.is_file():
        value = _read_json(path)
        _verified_self_hash(value, "consumption_sha256")
        return path
    if list((attempt_root / "reviews").glob("*.json")):
        raise ValueError("N15 review exists before live authority consumption")
    verified = verify_n15_frozen_attempt(repo_root, attempt_root)
    freeze = _read_json(attempt_root / "experiment-freeze.json")
    record = {
        "schema_version": "n15-live-consumption-1",
        "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": N15_AUTHORITY.as_posix(), "sha256": N15_AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": sha256(_tree_hashes(attempt_root / "packages")),
        "controller_manifest_tree_sha256": sha256(_tree_hashes(attempt_root / "controller-manifests")),
        "review_design_file_sha256": sha256((attempt_root / "review-design.json").read_bytes()),
        "repair_design_file_sha256": sha256((attempt_root / "repair-design.json").read_bytes()),
        "protected_file_hashes": deepcopy(N15_PROTECTED_FILE_SHA256),
        "model": PROVIDER_MODEL,
        "reasoning_effort": PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 64, "reviews": 192, "repairs": 0},
    }
    if record["freeze_sha256"] != freeze["freeze_sha256"]:
        raise ValueError("N15 live freeze binding changed")
    record["consumption_sha256"] = sha256(record)
    _write_immutable(path, record)
    return path


def _n15_comparison(
    rows: list[dict[str, Any]], name: str, left: str, right: str
) -> dict[str, Any]:
    left_rows = [x for x in rows if x["evidence_mode"] == left]
    right_rows = [x for x in rows if x["evidence_mode"] == right]
    metrics = (
        "fault_detected",
        "correct_job_localisation",
        "exact_boundary_localisation",
        "false_positive",
    )
    return {
        "name": name,
        "left": left,
        "right": right,
        **{
            f"{metric}_rate_difference": (
                sum(bool(x[metric]) for x in left_rows) / len(left_rows)
                - sum(bool(x[metric]) for x in right_rows) / len(right_rows)
            )
            for metric in metrics
        },
    }


def _n15_grouped(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(row[field] for field in fields), []).append(row)
    return [
        {
            **dict(zip(fields, key)),
            "n": len(values),
            "fault_detections": sum(bool(x["fault_detected"]) for x in values),
            "correct_job_localisations": sum(bool(x["correct_job_localisation"]) for x in values),
            "exact_boundary_localisations": sum(bool(x["exact_boundary_localisation"]) for x in values),
            "false_positives": sum(bool(x["false_positive"]) for x in values),
        }
        for key, values in sorted(groups.items())
    ]


def _write_n15_analysis(
    attempt_root: Path,
    packages: Mapping[str, Mapping[str, Any]],
    reviews: Mapping[tuple[str, int], Mapping[str, Any]],
) -> Path:
    rows = []
    token_records = []
    for record in reviews.values():
        condition = record["controller_trial"]
        events = record.get("operation_events", [])
        rows.append(
            {
                **deepcopy(condition),
                "designation": record["designation"],
                "fault_detected": bool(record["fault_detected"]),
                "false_positive": bool(record["false_positive"]),
                "selected_job_id": record.get("selected_job_id"),
                "selected_job_position": record.get("selected_job_position"),
                "selected_boundary_id": record.get("selected_suspect_boundary_id"),
                "selected_function_name": record.get("selected_function_name"),
                "correct_job_localisation": bool(record["correct_job_localisation"]),
                "exact_boundary_localisation": bool(record["exact_boundary_localisation"]),
                "accepted_operation_count": sum(x.get("status") == "completed" for x in events),
                "rejected_operation_count": sum(str(x.get("status", "")).startswith("rejected") for x in events),
                "disclosed_node_count": len(
                    packages[str(condition["branch_id"])]["reviewer_package"]
                    .get("runtime_evidence", {})
                    .get("nodes", [])
                ) + sum(len(x.get("nodes_added", [])) for x in events),
                "operation_events": deepcopy(events),
                "input_tokens": int(record["usage"].get("input_tokens", 0)),
                "cached_input_tokens": int(record["usage"].get("cached_input_tokens", 0)),
                "output_tokens": int(record["usage"].get("output_tokens", 0)),
            }
        )
        token_records.extend(record["usage"].get("calls", []))
    comparisons = [
        _n15_comparison(rows, "history_empty_vs_current", "history_empty", "current_run"),
        _n15_comparison(rows, "history_full_vs_history_empty", "history_full", "history_empty"),
        _n15_comparison(rows, "graph_empty_vs_current", "etiq_empty", "current_run"),
        _n15_comparison(rows, "fixed_vs_graph_empty", "etiq_selected_fixed", "etiq_empty"),
        _n15_comparison(rows, "adaptive_vs_fixed", "etiq_selected_adaptive", "etiq_selected_fixed"),
        _n15_comparison(rows, "random_matched_vs_fixed", "etiq_random_matched", "etiq_selected_fixed"),
        _n15_comparison(rows, "full_graph_vs_graph_empty", "etiq_full", "etiq_empty"),
    ]
    for mode in EVIDENCE_MODES:
        selected = [x for x in rows if x["evidence_mode"] == mode]
        present = [x for x in selected if x["source_setting"] == "source_present"]
        absent = [x for x in selected if x["source_setting"] == "source_absent"]
        comparisons.append(
            {
                "name": f"source_present_vs_absent__{mode}",
                "left": "source_present",
                "right": "source_absent",
                **{
                    f"{metric}_rate_difference": (
                        sum(bool(x[metric]) for x in present) / len(present)
                        - sum(bool(x[metric]) for x in absent) / len(absent)
                    )
                    for metric in (
                        "fault_detected",
                        "correct_job_localisation",
                        "exact_boundary_localisation",
                        "false_positive",
                    )
                },
            }
        )
    primary = [x for x in rows if x["instance_id"] == "instance-04"]
    calibration = [x for x in rows if x["instance_id"] == "instance-03"]
    controls = [x for x in rows if x["designation"] == "control"]
    repetition_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        repetition_groups.setdefault(str(row["branch_id"]), []).append(row)
    analysis = {
        "schema_version": "n15-downstream-first-analysis-1",
        "scope_limitation": "Four-pipeline descriptive experiment with one upstream-fault pipeline; Attempt 026 is a separate direct-assigned-job pilot and is not pooled.",
        "review_count": len(rows),
        "repair_trace_count": 0,
        "primary_instance_04": {
            "downstream_observation_fault_detection": {"numerator": sum(x["fault_detected"] for x in primary), "denominator": len(primary)},
            "correct_upstream_job_localisation": {"numerator": sum(x["correct_job_localisation"] for x in primary), "denominator": len(primary)},
            "exact_normalize_localisation": {"numerator": sum(x["exact_boundary_localisation"] for x in primary), "denominator": len(primary)},
        },
        "calibration_instance_03": {
            "downstream_fault_detection": {"numerator": sum(x["fault_detected"] for x in calibration), "denominator": len(calibration)},
            "exact_prioritize_needs_localisation": {"numerator": sum(x["exact_boundary_localisation"] for x in calibration), "denominator": len(calibration)},
        },
        "control_false_positives": {"numerator": sum(x["false_positive"] for x in controls), "denominator": len(controls)},
        "contrasts": comparisons,
        "results_by": {
            "evidence_mode": _n15_grouped(rows, ("evidence_mode",)),
            "source_setting": _n15_grouped(rows, ("source_setting",)),
            "fault_scope": _n15_grouped(rows, ("designation",)),
            "instance": _n15_grouped(rows, ("instance_id",)),
            "full_cells": _n15_grouped(rows, ("instance_id", "evidence_mode", "source_setting")),
        },
        "repetition_agreement": [
            {
                "branch_id": branch_id,
                "n": len(values),
                "fault_detection_unanimous": len({x["fault_detected"] for x in values}) == 1,
                "top_suspect_unanimous": len({(x["selected_job_id"], x["selected_boundary_id"]) for x in values}) == 1,
            }
            for branch_id, values in sorted(repetition_groups.items())
        ],
        "rows": rows,
        "raw_token_usage": token_records,
        "actual_usage": aggregate_actual_usage(token_records),
    }
    analysis["analysis_sha256"] = sha256(analysis)
    path = attempt_root / "analysis/summary.json"
    _write_immutable(path, analysis)
    return path


def execute_n15_lifecycle(
    repo_root: Path,
    attempt_root: Path,
    *,
    reviewer: Callable[..., Mapping[str, Any]],
) -> Path:
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    verified = verify_n15_frozen_attempt(repo_root, attempt_root)
    create_n15_live_consumption(repo_root, attempt_root)
    catalogues, packages, records = _load_n15_frozen(attempt_root)
    schedule = _read_json(attempt_root / "review-design.json")["review_trials"]
    if len(schedule) != 192 or _read_json(attempt_root / "repair-design.json")["repair_traces"]:
        raise ValueError("N15 frozen schedule changed")
    gate = _read_json(repo_root / N15_HISTORICAL_GATE)
    python_executor = signed_catalogue_python_executor(
        gate=gate,
        expected_gate_sha256=sha256(gate),
        repo_root=repo_root,
    )
    instance_records = {
        instance_id: _read_json(repo_root / SOURCE_ATTEMPT / "instances" / f"{instance_id}.json")
        for instance_id in SELECTED_INSTANCES
    }
    reviews: dict[tuple[str, int], dict[str, Any]] = {}
    for trial in schedule:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.is_file():
            record = _read_json(path)
            _verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("N15 partial review record is invalid")
        else:
            package_record = packages[str(trial["branch_id"])]
            package = package_record["reviewer_package"]
            initial = _normalized_review_response(
                _invoke_callback(reviewer, render_provider_request(package), str(trial["trial_id"]))
            )

            def follow_up(request: Mapping[str, Any], *, controller_parent_id: str = "") -> Mapping[str, Any]:
                return _normalized_review_response(
                    _invoke_callback(
                        reviewer,
                        render_provider_request(request["reviewer_package"], operation_response=request["operation_response"]),
                        controller_parent_id,
                    )
                )

            followed = run_n15_follow_up_loop(
                catalogue=catalogues[str(trial["instance_id"])],
                package=package,
                initial_response=initial,
                reviewer=follow_up,
                controller_parent_id=str(trial["trial_id"]),
                python_executor=python_executor,
            )
            validation = validate_n15_reviewer_response(
                catalogues[str(trial["instance_id"])], followed["package"], followed["response"]
            )
            score = score_n15_top_suspect(
                catalogues[str(trial["instance_id"])],
                instance_records[str(trial["instance_id"])],
                validation,
            )
            record = {
                "schema_version": "n15-downstream-first-review-1",
                "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "receipt": validation["receipt"],
                "selected_suspect_boundary_id": validation["selected_suspect_boundary_id"],
                "selected_job_id": validation["selected_job_id"],
                "selected_job_position": validation["selected_job_position"],
                "selected_function_name": validation["selected_function_name"],
                **score,
                "operation_events": followed["operation_events"],
                "call_records": followed["call_records"],
                "usage": followed["usage"],
                "status": "complete",
            }
            record["review_sha256"] = sha256(record)
            _write_immutable(path, record)
        reviews[(str(trial["branch_id"]), int(trial["repetition"]))] = record
    if len(reviews) != 192:
        raise ValueError("N15 review count is incomplete")
    call_ids = [
        str(call_id)
        for record in reviews.values()
        for call in record.get("call_records", [])
        for call_id in call.get("call_ids", [])
    ]
    if not call_ids or len(call_ids) != len(set(call_ids)):
        raise ValueError("N15 scientific call lineage is empty or duplicated")
    for call_id in call_ids:
        verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)
    analysis_path = _write_n15_analysis(attempt_root, packages, reviews)
    analysis = _read_json(analysis_path)
    replay = {
        "schema_version": "n15-downstream-first-replay-1",
        "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(x["review_sha256"] for x in reviews.values()),
        "observed_counts": {"packages": len(records), "reviews": len(reviews), "repairs": 0, "logical_call_ids": len(call_ids)},
        "all_record_hashes_recomputed": True,
        "duplicate_logical_calls": False,
    }
    replay["replay_sha256"] = sha256(replay)
    _write_immutable(attempt_root / "replay/reconciliation.json", replay)
    terminal = {
        "schema_version": "n15-downstream-first-terminal-1",
        "status": "completed_experiment_and_analysis",
        "package_count": 64,
        "review_count": 192,
        "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"],
        "replay_sha256": replay["replay_sha256"],
    }
    terminal["terminal_sha256"] = sha256(terminal)
    path = attempt_root / "terminal-state.json"
    _write_immutable(path, terminal)
    return path


def run_n15_lifecycle(
    repo_root: Path,
    attempt_root: Path,
    *,
    reviewer: Callable[..., Mapping[str, Any]],
) -> Path:
    try:
        return execute_n15_lifecycle(repo_root, attempt_root, reviewer=reviewer)
    except Exception as exc:
        terminal = {
            "schema_version": "n15-downstream-first-terminal-1",
            "status": "terminal_incomplete",
            "failure_stage": "n15_resumable_lifecycle",
            "error": f"{type(exc).__name__}: {exc}",
            "completed_review_records": len(list((attempt_root / "reviews").glob("*.json"))),
            "completed_repair_records": 0,
        }
        terminal["terminal_sha256"] = sha256(terminal)
        path = attempt_root / "terminal" / f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"
        _write_immutable(path, terminal)
        return path


def n15_production_reviewer(repo_root: Path, attempt_root: Path) -> Callable[..., Mapping[str, Any]]:
    def reviewer(request: Mapping[str, Any], *, controller_parent_id: str) -> Mapping[str, Any]:
        return production_reviewer(
            request,
            controller_parent_id=controller_parent_id,
            repo_root=repo_root,
            attempt_root=attempt_root,
        )

    return reviewer
