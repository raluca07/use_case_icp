"""N24 unified upstream-fault evidence-package experiment."""

from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import inspect
import io
import json
import math
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator
import tiktoken

from . import corrected_experiment as ce
from . import n20d_experiment as n20d
from . import n21_experiment as n21
from .fault_preflight_v2 import validate_strict_provider_schema
from .n05_runner import create_bytes_exclusive, verify_record
from .fault_operations import signed_catalogue_python_executor


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-041")
SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-038")
SEMANTIC_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-037")
LEGACY_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-027")
TASK = Path("instructions_between_agent_types/developer/current/N24_unified_upstream_fault_package_experiment.email.md")
TASK_SHA256 = "sha256:6f74b2d1ea28a3347dc0fc0c10d1c2e579ab115e9844149446ba26e6d62b064f"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N24_unified_upstream_fault_package_experiment_authorization.json")
AUTHORITY_SHA256 = "sha256:bc255287e2b56647f8a92150ea9a4df2c7a1d29fcac36e55023d47b947de2b02"
N24A_TASK = Path("instructions_between_agent_types/developer/current/N24A_provider_schema_correction_and_attempt_041_resume.email.md")
N24A_TASK_SHA256 = "sha256:0a1495a88581e6d34ed473269c7a1470a6e8d098cb9872417af7ced2312cdd7e"
N24A_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N24A_provider_schema_correction_and_attempt_041_resume_authorization.json")
N24A_AUTHORITY_SHA256 = "sha256:b33abee0452bc23084383555363ede5bd2d1dc228db55e45e040143422178772"
N24A_CORRECTION = Path("qualification/post-freeze-provider-schema-correction.json")
N24A_BEFORE_CODE_SHA256 = "sha256:6adeb436b368971a2b7dd4b44e1b045a03625fabd9649bd2b2ceafc1596deb0b"
N24A_SCHEMA_TRANSITIONS = {
    "schemas/v2_2/n24_expand_required.schema.json": ("sha256:6f5207ae2674390024ecf042b0d5ec08bff638b999d3dcc151103e0e33621bcf", "sha256:76bb512c3848430fb972c9a0bab8cf2d8194c231ac0ec1d69feb1b6cd89cae9f"),
    "schemas/v2_2/n24_reconsider.schema.json": ("sha256:fa09e642c21802f8c0e9bfdf35517df66382b397baffd891820bd7efa205aecd", "sha256:f4a81159e3302c7f43cd68b19fb8a70add131bbb500da10454cfe23955c40e8d"),
}
N24A_BLOCKED_TRIAL = "trial-7de794d572a1fe32"
N24A_FAILED_CALL_IDS = ("call-000-8237fdcc75ded025", "call-001-8274ec75a4f2d6ab", "call-002-77d4c3004883b27a")
N24B_TASK = Path("instructions_between_agent_types/developer/current/N24B_legacy_schema_correction_complete_schema_audit_and_resume.email.md")
N24B_TASK_SHA256 = "sha256:ba1c68f46f9bfd3953a37489bccd2ee0493f140de2a946cef2881d396b98d79e"
N24B_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N24B_legacy_schema_correction_complete_schema_audit_and_resume_authorization.json")
N24B_AUTHORITY_SHA256 = "sha256:34d05af738c02e0b5cc517b670bcdb00eaa73a147c76ca2b5491a79457da2893"
N24B_CORRECTION = Path("qualification/post-freeze-legacy-schema-correction.json")
N24B_BEFORE_CODE_SHA256 = "sha256:036ff38430c8462db44bae21c19deca7ec0f9c12c707da220d28fd22b49461af"
N24B_LEGACY_SCHEMA_TRANSITION = ("sha256:bd1047c128849ba87c01a56b81977b5587b636c397784af6eb8a6b2997ffb121", "sha256:f616c573284935b2ae0b3efcbfdf502669846f728b13cafcbde1aaf6dfccfe38")
N24B_BLOCKED_TRIAL = "trial-45499db89ea80b3f"
N24B_FAILED_CALL_IDS = ("call-000-e934d0d447694867", "call-001-4c07c12baffe3290", "call-002-41f6b3f62d9fac4d")
SOURCE_TREE_SHA256 = "sha256:a2ddd9c32734bb8827e89c206448d87b802986cce16b9001e85af854f8fcf931"
SEMANTIC_TREE_SHA256 = "sha256:a7b8d11717d1cb3281757f1f0e2fae542b1b2ee238630a90f1c477bbb88a112c"
SOURCE_FREEZE_FILE_SHA256 = "sha256:d9a3a2301271989cb72e0e84fcbcff22972fe915338010d41d9276449b4d90f2"
SOURCE_FREEZE_SHA256 = "sha256:20af8d990753aeb7ad4e45a31c6decebaab798aa5ecdb8b0f9a61767107f9594"
SOURCE_TERMINAL_FILE_SHA256 = "sha256:b73e58ed5d5fac64ba30d574df08ac704e3f0e4298821348b5fb3c241652e481"
SOURCE_REPLAY_FILE_SHA256 = "sha256:779d345066b5434f8e8e754a64c2a7650f361012a163681b3bb3d8df91adda40"
LEGACY_CODE_COMMIT = "2e6de93"
LEGACY_CODE_FILE_SHA256 = "sha256:8bf29300ae91f5239edfb9032accdb92039399e51c90668c45bcdfc6a5f93856"
PROMPT = Path("prompts/v2_2/n24_unified_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n24_final.schema.json")
REQUIRED_SCHEMA = Path("schemas/v2_2/n24_expand_required.schema.json")
VOLUNTARY_SCHEMA = Path("schemas/v2_2/n24_expand_voluntary.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n24_reconsider.schema.json")
LEGACY_SCHEMA = Path("schemas/v2_2/n24_legacy.schema.json")
INSTANCES = n21.INSTANCES
CLEAN_INSTANCE = n21.CLEAN_INSTANCE
UPSTREAM = n21.UPSTREAM
DOWNSTREAM = n21.DOWNSTREAM
TASK_TEXT = (
    "Review the observed Job-2 outcome. Decide whether the two-job execution contains a fault. "
    "If it does, identify the responsible job and, when the supplied evidence supports it, "
    "the exact responsible function."
)
CONFIRMATORY = (
    ("C01", "current_job2"),
    ("C02", "history_empty"),
    ("C03", "history_full"),
    ("C04", "etiq_empty_job2"),
    ("C05", "compact_fixed_job2"),
    ("C06", "compact_adaptive_required_one_job2"),
    ("C07", "compact_reconsideration_job2"),
)
DESCRIPTIVE = (
    ("D01", "io_job2"),
    ("D02", "io_both"),
    ("D03", "current_both_jobs"),
    ("D04", "etiq_empty_both"),
    ("D05", "full_graph_job2_legacy"),
    ("D06", "broad_selected_fixed_job2_legacy"),
    ("D07", "broad_selected_adaptive_job2_legacy"),
    ("D08", "random_matched_job2_legacy"),
    ("D09", "compact_adaptive_voluntary_job2"),
    ("D10", "compact_fixed_both"),
    ("D11", "compact_adaptive_voluntary_both"),
    ("D12", "compact_adaptive_required_one_both"),
)
MODE_NAMES = dict((*CONFIRMATORY, *DESCRIPTIVE))
MANDATORY_EXPANSION = {"C06", "D12"}
VOLUNTARY_EXPANSION = {"D09", "D11"}
LEGACY_MODES = {"D05", "D06", "D07", "D08"}
LEGACY_FUNCTIONS = (
    "n15_selected_projection", "n15_full_projection", "n15_random_matched_projection",
    "expand_n15_helper", "perform_n15_operation", "run_n15_follow_up_loop",
)
MAX_PACKAGE_BYTES = ce.MAX_PACKAGE_BYTES
N24_SCHEMAS = (FINAL_SCHEMA, REQUIRED_SCHEMA, VOLUNTARY_SCHEMA, RECONSIDER_SCHEMA, LEGACY_SCHEMA)


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _compatible_json_type(value: Any) -> set[str]:
    if value is None:
        return {"null"}
    if isinstance(value, bool):
        return {"boolean"}
    if isinstance(value, str):
        return {"string"}
    if isinstance(value, int):
        return {"integer", "number"}
    if isinstance(value, float):
        return {"number"}
    if isinstance(value, list):
        return {"array"}
    if isinstance(value, Mapping):
        return {"object"}
    return set()


def _validate_const_types(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        if "const" in value:
            declared = value.get("type")
            types = {declared} if isinstance(declared, str) else set(declared or [])
            if not types & _compatible_json_type(value["const"]):
                raise ValueError(f"N24 const schema property lacks an explicit compatible type: {path}")
        for key, child in value.items():
            _validate_const_types(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_const_types(child, f"{path}[{index}]")


def validate_n24_schemas(repo_root: Path) -> dict[str, str]:
    hashes = {}
    unsupported = {"oneOf", "anyOf", "allOf", "not", "if", "then", "else", "dependentSchemas", "patternProperties", "unevaluatedProperties"}
    for relative in N24_SCHEMAS:
        schema = _json(repo_root / relative)
        Draft202012Validator.check_schema(schema)
        validate_strict_provider_schema(schema, relative.as_posix())
        _validate_const_types(schema)
        def reject_composition(value: Any, path: str = "$") -> None:
            if isinstance(value, Mapping):
                found = unsupported & set(value)
                if found:
                    raise ValueError(f"N24 unsupported provider schema composition at {path}: {sorted(found)}")
                for key, child in value.items():
                    reject_composition(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    reject_composition(child, f"{path}[{index}]")
        reject_composition(schema)
        hashes[relative.as_posix()] = ce.sha256((repo_root / relative).read_bytes())
    return hashes


def n24_schema_witnesses(repo_root: Path) -> dict[str, int]:
    terminal = {"fault_detected": True, "suspect_job": "job_1", "suspect_function": "select_demand", "explanation": "evidence", "cited_evidence": []}
    witnesses = {
        FINAL_SCHEMA: [terminal],
        REQUIRED_SCHEMA: [{**terminal, "next_action": {"action": "expand_execution_group", "execution_group_id": "grp-example"}}],
        VOLUNTARY_SCHEMA: [{**terminal, "next_action": {"action": "finalize", "execution_group_id": ""}}, {**terminal, "next_action": {"action": "expand_execution_group", "execution_group_id": "grp-example"}}],
        RECONSIDER_SCHEMA: [{**terminal, "next_action": {"action": "reconsider_same_evidence"}}],
        LEGACY_SCHEMA: [
            {**terminal, "follow_up_requests": []},
            {**terminal, "follow_up_requests": [{"operation": "expand_execution_group", "execution_group_id": "grp-example", "requests": []}]},
            {**terminal, "follow_up_requests": [{"operation": "artifact_inspection", "execution_group_id": "", "requests": [{"node_ref": "node-example", "inspection": "read", "start": 0, "count": 1, "columns": [], "query": "", "include_raw_metadata": False, "code": ""}]}]},
        ],
    }
    result = {}
    for relative, values in witnesses.items():
        validator = Draft202012Validator(_json(repo_root / relative))
        for value in values:
            validator.validate(value)
        result[relative.as_posix()] = len(values)
    return result


def _verify_n24a_authority(repo_root: Path) -> None:
    for relative, expected in ((N24A_TASK, N24A_TASK_SHA256), (N24A_AUTHORITY, N24A_AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N24A authority input changed: {relative}")


def _verify_n24b_authority(repo_root: Path) -> None:
    for relative, expected in ((N24B_TASK, N24B_TASK_SHA256), (N24B_AUTHORITY, N24B_AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N24B authority input changed: {relative}")


def _write_bytes(path: Path, data: str) -> None:
    create_bytes_exclusive(path, data.encode())


def _authority_bindings(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N24 authority input changed: {relative}")
    source = repo_root / SOURCE_ATTEMPT
    semantic = repo_root / SEMANTIC_ATTEMPT
    if ce.sha256(ce._tree_hashes(source)) != SOURCE_TREE_SHA256:
        raise ValueError("Attempt 038 tree changed")
    if ce.sha256(ce._tree_hashes(semantic)) != SEMANTIC_TREE_SHA256:
        raise ValueError("Attempt 037 tree changed")
    checks = (
        (source / "experiment-freeze.json", SOURCE_FREEZE_FILE_SHA256, "freeze_sha256", SOURCE_FREEZE_SHA256),
        (source / "terminal-state.json", SOURCE_TERMINAL_FILE_SHA256, "terminal_sha256", None),
        (source / "replay/reconciliation.json", SOURCE_REPLAY_FILE_SHA256, "replay_sha256", None),
    )
    for path, file_hash, logical_key, logical_hash in checks:
        if ce.sha256(path.read_bytes()) != file_hash:
            raise ValueError(f"Attempt 038 binding changed: {path.name}")
        observed = ce._verified_self_hash(_json(path), logical_key)
        if logical_hash and observed != logical_hash:
            raise ValueError(f"Attempt 038 logical binding changed: {path.name}")
    for relative, expected in ce.N15_PROTECTED_FILE_SHA256.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N24 protected boundary changed: {relative}")
    return {
        "attempt_038_tree_sha256": SOURCE_TREE_SHA256,
        "attempt_037_tree_sha256": SEMANTIC_TREE_SHA256,
        "attempt_038_freeze_file_sha256": SOURCE_FREEZE_FILE_SHA256,
        "attempt_038_freeze_sha256": SOURCE_FREEZE_SHA256,
        "attempt_038_terminal_file_sha256": SOURCE_TERMINAL_FILE_SHA256,
        "attempt_038_replay_file_sha256": SOURCE_REPLAY_FILE_SHA256,
        "protected_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
    }


def _function_source_hash(function: Any) -> str:
    # ``ast.get_source_segment`` excludes the trailing line break while
    # ``inspect.getsource`` includes it; normalize only that representation.
    return ce.sha256(inspect.getsource(function).rstrip("\n").encode())


def recover_legacy_components(repo_root: Path) -> dict[str, Any]:
    historical = subprocess.check_output(
        ["git", "show", f"{LEGACY_CODE_COMMIT}:src/use_case_icp/corrected_experiment.py"],
        cwd=repo_root,
    )
    if ce.sha256(historical) != LEGACY_CODE_FILE_SHA256:
        raise ValueError("Attempt 027 historical source blob changed")
    current_hashes = {name: _function_source_hash(getattr(ce, name)) for name in LEGACY_FUNCTIONS}
    old_text = historical.decode()
    import ast
    tree = ast.parse(old_text)
    old_hashes = {}
    for name in LEGACY_FUNCTIONS:
        node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
        old_hashes[name] = ce.sha256(ast.get_source_segment(old_text, node).encode())
    if current_hashes != old_hashes:
        raise ValueError("Attempt 027 legacy graph component is not exactly recoverable")
    old_root = repo_root / LEGACY_ATTEMPT
    frozen = {}
    for path in sorted((old_root / "controller-manifests").glob("*.json")):
        manifest = _json(path)
        condition = manifest["controller_condition"]
        key = (condition["instance_id"], condition["evidence_mode"], condition["source_setting"])
        frozen[key] = _json(old_root / manifest["reviewer_package_path"])
    reproduced = {}
    for path in sorted((old_root / "catalogues").glob("*.json")):
        catalogue = _json(path)
        fixed = ce.n15_selected_projection(catalogue)
        expected = {
            "etiq_full": ce.n15_full_projection(catalogue),
            "etiq_selected_fixed": fixed,
            "etiq_selected_adaptive": fixed,
        }
        reproduced[path.stem] = {
            mode: ce.canonical_json(value) == ce.canonical_json(frozen[(path.stem, mode, "source_absent")]["runtime_evidence"])
            for mode, value in expected.items()
        }
    if not all(value for row in reproduced.values() for value in row.values()):
        raise ValueError("Attempt 027 deterministic legacy projection does not reproduce")
    return {
        "source_commit": LEGACY_CODE_COMMIT,
        "historical_source_file_sha256": LEGACY_CODE_FILE_SHA256,
        "function_source_hashes": current_hashes,
        "deterministic_projection_reproduction": reproduced,
        "random_selector_note": "Exact historical rule recovered; its set iteration is process-dependent, so the N24 selected result is generated once and frozen.",
        "operation_contract": {
            "eligible_modes": sorted(LEGACY_MODES),
            "follow_up_calls_per_session_minimum": 0,
            "follow_up_calls_per_session_maximum": 3,
            "artifact_requests_per_call_maximum": 2,
            "sessions": 168,
            "provider_follow_up_calls_minimum": 0,
            "provider_follow_up_calls_maximum": 504,
        },
    }


def _copy_exact(source: Path, target: Path) -> None:
    create_bytes_exclusive(target, source.read_bytes())


def _source_package(source_root: Path, instance_id: str, mode: str) -> dict[str, Any]:
    found = []
    for path in (source_root / "controller-manifests").glob("*.json"):
        manifest = _json(path)
        condition = manifest["controller_condition"]
        if condition["instance_id"] == instance_id and condition["evidence_mode"] == mode:
            package = _json(source_root / manifest["reviewer_package_path"])
            if ce.sha256(package) != manifest["reviewer_package_sha256"]:
                raise ValueError("Attempt 038 reviewer package changed")
            found.append(package)
    if len(found) != 1:
        raise ValueError(f"Attempt 038 source package is not unique: {instance_id}/{mode}")
    return found[0]


def _semantic_declarations(repo_root: Path) -> dict[str, Any]:
    root = repo_root / SEMANTIC_ATTEMPT
    values = []
    hashes = []
    for path in (root / "controller-manifests").glob("*.json"):
        manifest = _json(path)
        condition = manifest["controller_condition"]
        if condition["evidence_mode"] != "compact_fixed_guided":
            continue
        package_path = root / manifest["reviewer_package_path"]
        package = _json(package_path)
        values.append(package["boundary_guidance"])
        hashes.append({"package_file_sha256": ce.sha256(package_path.read_bytes()), "package_sha256": manifest["package_sha256"]})
    if len(values) != 7 or len({ce.canonical_json(value) for value in values}) != 1:
        raise ValueError("Attempt 037 semantic declaration bundle changed")
    bundle = values[0]
    if len(bundle["semantic_declarations"]) != 6:
        raise ValueError("Attempt 037 declaration count changed")
    return {"bundle": bundle, "source_package_bindings": hashes}


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N24 is authorized only for Attempt 041")
    bindings = _authority_bindings(repo_root)
    legacy = recover_legacy_components(repo_root)
    source = repo_root / SOURCE_ATTEMPT
    for directory in ("captures", "catalogues", "instances", "qualification/mutations", "source-bundles", "native-group-index"):
        for source_path in sorted((source / directory).glob("*.json")):
            _copy_exact(source_path, target / directory / source_path.name)
    _copy_exact(source / "qualification/mutation-summary.json", target / "qualification/mutation-summary.json")
    captures = {path.stem: _json(path) for path in sorted((target / "captures").glob("*.json"))}
    catalogues = {path.stem: _json(path) for path in sorted((target / "catalogues").glob("*.json"))}
    instances = {path.stem: _json(path) for path in sorted((target / "instances").glob("*.json"))}
    indexes = {path.stem: _json(path) for path in sorted((target / "native-group-index").glob("*.json"))}
    source_bundles = {path.stem: _json(path)["source_bundle"] for path in sorted((target / "source-bundles").glob("*.json"))}
    expected = set(INSTANCES)
    if any(set(value) != expected for value in (captures, catalogues, instances, indexes, source_bundles)):
        raise ValueError("N24 exact reused record set changed")
    freeze = _json(source / "experiment-freeze.json")
    asset_bindings = {}
    for instance_id in INSTANCES:
        ce._verify_capture(captures[instance_id])
        ce.verify_catalogue(catalogues[instance_id])
        ce._verified_self_hash(instances[instance_id], "instance_sha256")
        paths = {
            "capture_file": target / "captures" / f"{instance_id}.json",
            "catalogue_file": target / "catalogues" / f"{instance_id}.json",
            "instance_file": target / "instances" / f"{instance_id}.json",
            "source_bundle_file": target / "source-bundles" / f"{instance_id}.json",
            "native_group_index_file": target / "native-group-index" / f"{instance_id}.json",
        }
        if captures[instance_id]["capture_sha256"] != freeze["capture_hashes"][instance_id] or catalogues[instance_id]["catalogue_sha256"] != freeze["catalogue_hashes"][instance_id] or instances[instance_id]["instance_sha256"] != freeze["instance_hashes"][instance_id] or ce.sha256(paths["source_bundle_file"].read_bytes()) != freeze["source_bundle_file_hashes"][instance_id]:
            raise ValueError(f"N24 reused asset binding changed: {instance_id}")
        asset_bindings[instance_id] = {
            **{key + "_sha256": ce.sha256(path.read_bytes()) for key, path in paths.items()},
            "capture_sha256": captures[instance_id]["capture_sha256"],
            "catalogue_sha256": catalogues[instance_id]["catalogue_sha256"],
            "instance_sha256": instances[instance_id]["instance_sha256"],
            "handoffs_sha256": ce.sha256(catalogues[instance_id]["handoffs"]),
            "job_inputs_sha256": ce.sha256({job: catalogues[instance_id]["jobs"][job]["input"] for job in catalogue_job_order(catalogues[instance_id])}),
            "job_outputs_sha256": ce.sha256({job: catalogues[instance_id]["jobs"][job]["output"] for job in catalogue_job_order(catalogues[instance_id])}),
            "oracle_sha256": ce.sha256(instances[instance_id].get("oracle")),
        }
    semantic = _semantic_declarations(repo_root)
    ce._write_immutable(target / "qualification/reuse-bindings.json", {"schema_version": "n24-reuse-bindings-1", "authority": bindings, "assets": asset_bindings})
    ce._write_immutable(target / "qualification/legacy-recovery.json", {"schema_version": "n24-legacy-recovery-1", **legacy})
    ce._write_immutable(target / "semantic-declarations.json", semantic)
    return {"bindings": bindings, "legacy": legacy, "asset_bindings": asset_bindings, "captures": captures, "catalogues": catalogues, "instances": instances, "indexes": indexes, "source_bundles": source_bundles, "declarations": semantic["bundle"]}


def catalogue_job_order(catalogue: Mapping[str, Any]) -> list[str]:
    return list(map(str, catalogue["job_order"]))


def _job_record(catalogue: Mapping[str, Any], job_id: str, logs: bool) -> dict[str, Any]:
    record = {"job": "job_1" if job_id == UPSTREAM else "job_2", "captured_job_id": job_id, "input": deepcopy(catalogue["jobs"][job_id]["input"]), "output": deepcopy(catalogue["jobs"][job_id]["output"])}
    if logs:
        record.update({"stdout": str(catalogue["jobs"][job_id]["stdout"]), "stderr": str(catalogue["jobs"][job_id]["stderr"])})
    return record


def _empty_graph(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    value = {"job_evidence_order": catalogue_job_order(catalogue), "nodes": [], "relationships": [], "handoffs": [], "collapsed_execution_groups": [], "disclosed_execution_groups": []}
    value["projection_sha256"] = ce.sha256(value)
    return value


def _legacy_groups(projection: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups, index = [], {}
    for item in projection.get("collapsed_children", []):
        group_id = f"grp-{ce.sha256([item.get('job_id'), item.get('boundary_id'), item.get('func_stack')])[7:23]}"
        descriptor = {
            "execution_group_id": group_id,
            "job_id": item.get("job_id"),
            "func_stack": deepcopy(item.get("func_stack", [])),
            "node_count": item.get("node_count"),
            "relationship_count": item.get("relationship_count"),
        }
        groups.append(descriptor)
        index[group_id] = {"boundary_id": item.get("boundary_id"), "func_stack": deepcopy(item.get("func_stack", [])), "job_id": item.get("job_id")}
    return groups, index


def _visible_legacy_projection(projection: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    groups, index = _legacy_groups(projection)
    visible = {key: deepcopy(value) for key, value in projection.items() if key not in {"collapsed_children", "visible_evidence_by_boundary", "projection_sha256"}}
    visible["collapsed_execution_groups"] = groups
    visible["disclosed_execution_groups"] = []
    visible["projection_sha256"] = ce.sha256(visible)
    return visible, index


def _base_package(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    source = _source_package_cache(catalogue)
    return {
        "schema_version": "n24-review-package-1",
        "review_task": TASK_TEXT,
        "behavioural_criteria": deepcopy(source["behavioural_criteria"]),
        "pipeline_topology": [
            {"job": "job_1", "captured_job_id": UPSTREAM, "position": "upstream"},
            {"job": "job_2", "captured_job_id": DOWNSTREAM, "position": "downstream", "observation_point": True},
        ],
        "top_level_input": deepcopy(source["top_level_input"]),
        "observed_job_2_outcome": deepcopy(catalogue["jobs"][DOWNSTREAM]["output"]),
    }


_SOURCE_PACKAGE_CACHE: dict[str, dict[str, Any]] = {}


def _source_package_cache(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    instance_id = str(catalogue["instance_id"])
    if instance_id not in _SOURCE_PACKAGE_CACHE:
        raise RuntimeError("N24 source package cache is not initialized")
    return _SOURCE_PACKAGE_CACHE[instance_id]


def build_package(prepared: Mapping[str, Any], instance_id: str, mode: str, source_setting: str, declaration_setting: str) -> tuple[dict[str, Any], dict[str, Any]]:
    catalogue = prepared["catalogues"][instance_id]
    package = _base_package(catalogue)
    both_runtime = mode in {"D03", "D04", "D10", "D11", "D12"}
    no_logs = mode in {"D01", "D02"}
    package["job_execution_records"] = (
        [_job_record(catalogue, DOWNSTREAM, False)] if mode == "D01" else
        [_job_record(catalogue, UPSTREAM, False), _job_record(catalogue, DOWNSTREAM, False)] if mode == "D02" else
        [_job_record(catalogue, UPSTREAM, True), _job_record(catalogue, DOWNSTREAM, True)] if both_runtime else
        [_job_record(catalogue, DOWNSTREAM, not no_logs)]
    )
    if mode in {"C02", "C03"}:
        package["history"] = {"prior_task_records": []}
        if mode == "C03":
            prior = _job_record(catalogue, UPSTREAM, True)
            prior["chronology"] = {"position": 1, "precedes": "job_2"}
            prior["produced_handoffs"] = deepcopy(catalogue["handoffs"])
            package["history"]["prior_task_records"] = [prior]
    controller = {"legacy_raw_projection": None, "legacy_group_index": {}}
    if mode in {"C04", "D04"}:
        package["graph_review"] = {"framing": "Captured execution evidence may be used in the assessment.", "evidence": _empty_graph(catalogue)}
    elif mode in {"C05", "C06", "C07", "D09", "D10", "D11", "D12"}:
        graph = deepcopy(_source_package_cache(catalogue)["runtime_evidence"])
        package["graph_review"] = {"framing": "Captured execution evidence may be used in the assessment.", "evidence": graph}
    elif mode in LEGACY_MODES:
        fixed = ce.n15_selected_projection(catalogue)
        raw = ce.n15_full_projection(catalogue) if mode == "D05" else ce.n15_random_matched_projection(catalogue, fixed) if mode == "D08" else fixed
        visible, index = _visible_legacy_projection(raw)
        package["graph_review"] = {"framing": "Captured execution evidence may be used in the assessment.", "evidence": visible}
        controller = {"legacy_raw_projection": raw, "legacy_group_index": index}
    if source_setting == "S1":
        package["separate_complete_source_bundle"] = deepcopy(prepared["source_bundles"][instance_id])
    if declaration_setting == "B1":
        package["semantic_declaration_bundle"] = deepcopy(prepared["declarations"])
    if mode in MANDATORY_EXPANSION | VOLUNTARY_EXPANSION:
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {"operation": "expand_execution_group", "maximum_completed_expansions": 1, "required_before_terminal": mode in MANDATORY_EXPANSION}
    elif mode == "C07":
        package["interaction_contract"] = {"operation": "reconsider_same_evidence", "required_second_pass": True, "evidence_bytes_added": 0}
    elif mode in LEGACY_MODES:
        operations = ["artifact_inspection", *( ["expand_execution_group"] if mode == "D07" else [])]
        package["available_operations"] = operations
        package["interaction_contract"] = {"maximum_follow_up_calls": 3, "maximum_artifact_requests_per_call": 2, "available_operations": operations}
    return package, controller


def schedule() -> dict[str, Any]:
    cells = []
    for instance_id in INSTANCES:
        for mode, name in CONFIRMATORY:
            for source in ("S0", "S1"):
                for declarations in ("B0", "B1"):
                    cell = f"{mode}-{source}-{declarations}"
                    cells.append({"instance_id": instance_id, "cell_id": cell, "block": "confirmatory", "mode": mode, "mode_name": name, "source_setting": source, "declaration_setting": declarations, "branch_id": f"brn-{ce.sha256(['n24', instance_id, cell])[7:23]}"})
        for mode, name in DESCRIPTIVE:
            for declarations in ("B0", "B1"):
                cell = f"{mode}-S0-{declarations}"
                cells.append({"instance_id": instance_id, "cell_id": cell, "block": "descriptive", "mode": mode, "mode_name": name, "source_setting": "S0", "declaration_setting": declarations, "branch_id": f"brn-{ce.sha256(['n24', instance_id, cell])[7:23]}"})
    reviews = []
    by_instance = {instance_id: [cell for cell in cells if cell["instance_id"] == instance_id] for instance_id in INSTANCES}
    block = 0
    for repetition in range(1, 4):
        instance_order = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for instance_id in instance_order:
            values = by_instance[instance_id]
            rotation = block % len(values)
            for position, cell in enumerate(values[rotation:] + values[:rotation], 1):
                reviews.append({**cell, "repetition": repetition, "trial_id": f"trial-{ce.sha256(['n24', cell['branch_id'], repetition])[7:23]}", "schedule_position": len(reviews) + 1, "local_block": block + 1, "cell_position": position})
            block += 1
    if (len(cells), len(reviews), len({x["trial_id"] for x in reviews})) != (364, 1092, 1092):
        raise AssertionError("N24 matrix changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _schema_for(mode: str, *, follow_up: bool = False) -> Path:
    if follow_up:
        return LEGACY_SCHEMA if mode in LEGACY_MODES else FINAL_SCHEMA
    if mode in MANDATORY_EXPANSION:
        return REQUIRED_SCHEMA
    if mode in VOLUNTARY_EXPANSION:
        return VOLUNTARY_SCHEMA
    if mode == "C07":
        return RECONSIDER_SCHEMA
    if mode in LEGACY_MODES:
        return LEGACY_SCHEMA
    return FINAL_SCHEMA


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    text = ce.canonical_json(request).decode()
    forbidden_keys = ("cell_id", "source_setting", "declaration_setting", "branch_id", "trial_id", "repetition", "seed", "truth_function", "truth_job", "oracle", "qualification")
    if any(f'"{key}"' in text for key in forbidden_keys):
        raise ValueError("N24 rendered request leaks controller state")
    formal = ("shacl", "ontology.ttl", "shapes.ttl", "rules.ttl", "validation_report", "inferred_triples", "deterministic_diagnosis")
    if any(token in text.lower() for token in formal):
        raise ValueError("N24 rendered request contains excluded formal evidence")
    return request


def _contains_key(value: Any, keys: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(str(key) in keys or _contains_key(child, keys) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_key(child, keys) for child in value)
    return False


def _diff_paths(left: Any, right: Any, prefix: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [prefix]
    if isinstance(left, Mapping):
        paths = []
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}"
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(_diff_paths(left[key], right[key], child))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return [prefix]
        paths = []
        for index, (a, b) in enumerate(zip(left, right)):
            paths.extend(_diff_paths(a, b, f"{prefix}[{index}]"))
        return paths
    return [] if left == right else [prefix]


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in package.items() if key not in {"available_operations", "interaction_contract"}}


def _source_strings(value: Any, source_context: bool = False) -> list[str]:
    found = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            is_source = source_context or str(key) in {"source", "source_text"}
            found.extend(_source_strings(child, is_source))
    elif isinstance(value, list):
        for child in value:
            found.extend(_source_strings(child, source_context))
    elif source_context and isinstance(value, str):
        found.append(value)
    return found


def _bundle_source_strings(bundle: Any) -> list[str]:
    if not isinstance(bundle, list):
        return []
    return [str(file["content"]) for job in bundle for file in job.get("files", []) if isinstance(file.get("content"), str)]


def _token_count(value: Any) -> int:
    encoding = tiktoken.get_encoding("o200k_base")
    text = value if isinstance(value, str) else ce.canonical_json(value).decode()
    return len(encoding.encode(text))


def exposure_manifest(record: Mapping[str, Any]) -> dict[str, Any]:
    package = record["reviewer_package"]
    graph = package.get("graph_review", {}).get("evidence", {})
    separate = package.get("separate_complete_source_bundle", [])
    embedded_source = _source_strings({key: value for key, value in package.items() if key != "separate_complete_source_bundle"})
    captured_values = []
    for node in graph.get("nodes", []):
        for key in ("value", "raw_value", "data", "source"):
            if key in node:
                captured_values.append(node[key])
    logs = [item[key] for item in package.get("job_execution_records", []) for key in ("stdout", "stderr") if key in item]
    groups = graph.get("collapsed_execution_groups", [])
    separate_source = _bundle_source_strings(separate)
    return {
        "branch_id": record["controller_condition"]["branch_id"],
        "instance_id": record["controller_condition"]["instance_id"],
        "cell_id": record["controller_condition"]["cell_id"],
        "model_visible_utf8_bytes": len(ce.canonical_json(render_request(package))),
        "estimated_model_visible_tokens": _token_count(render_request(package)),
        "source": {
            "separate_bundle_present": bool(separate),
            "separate_characters": sum(len(value) for value in separate_source),
            "separate_tokens": sum(_token_count(value) for value in separate_source),
            "naturally_embedded_characters": sum(len(value) for value in embedded_source),
            "naturally_embedded_tokens": sum(_token_count(value) for value in embedded_source),
            "total_reviewer_visible_source_characters": sum(len(value) for value in embedded_source) + sum(len(value) for value in separate_source),
            "total_reviewer_visible_source_tokens": sum(_token_count(value) for value in embedded_source) + sum(_token_count(value) for value in separate_source),
        },
        "runtime_records": len(package.get("job_execution_records", [])),
        "log_characters": sum(len(value) for value in logs),
        "history_records": len(package.get("history", {}).get("prior_task_records", [])),
        "semantic_declarations": len(package.get("semantic_declaration_bundle", {}).get("semantic_declarations", [])),
        "graph_nodes": len(graph.get("nodes", [])),
        "graph_relationships": len(graph.get("relationships", [])),
        "child_groups": len(groups),
        "captured_value_count": len(captured_values),
        "operation_capabilities": deepcopy(package.get("available_operations", [])),
    }


def pairwise_difference_report(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(records)
    by = {(x["controller_condition"]["instance_id"], x["controller_condition"]["cell_id"]): x["reviewer_package"] for x in values}
    rows = []
    for instance_id in INSTANCES:
        def add(invariant: str, left_cell: str, right_cell: str, allowed_roots: set[str], evidence_only: bool = False) -> None:
            left, right = by[(instance_id, left_cell)], by[(instance_id, right_cell)]
            if evidence_only:
                left, right = _initial_evidence(left), _initial_evidence(right)
            paths = _diff_paths(left, right)
            passed = all(path.split(".")[1] in allowed_roots for path in paths) and bool(paths or not allowed_roots)
            rows.append({"instance_id": instance_id, "invariant": invariant, "left": left_cell, "right": right_cell, "differing_paths": paths, "allowed_top_level_roots": sorted(allowed_roots), "passed": passed})
        for mode, _ in CONFIRMATORY:
            for boundary in ("B0", "B1"):
                add("S1_vs_S0", f"{mode}-S0-{boundary}", f"{mode}-S1-{boundary}", {"separate_complete_source_bundle"})
            for source in ("S0", "S1"):
                add("B1_vs_B0", f"{mode}-{source}-B0", f"{mode}-{source}-B1", {"semantic_declaration_bundle"})
        for mode, _ in DESCRIPTIVE:
            add("B1_vs_B0", f"{mode}-S0-B0", f"{mode}-S0-B1", {"semantic_declaration_bundle"})
        for source in ("S0", "S1"):
            for boundary in ("B0", "B1"):
                add("C01_vs_C02", f"C01-{source}-{boundary}", f"C02-{source}-{boundary}", {"history"})
                add("C02_vs_C03", f"C02-{source}-{boundary}", f"C03-{source}-{boundary}", {"history"})
                add("C01_vs_C04", f"C01-{source}-{boundary}", f"C04-{source}-{boundary}", {"graph_review"})
                add("C04_vs_C05", f"C04-{source}-{boundary}", f"C05-{source}-{boundary}", {"graph_review"})
                add("C05_vs_C06_initial", f"C05-{source}-{boundary}", f"C06-{source}-{boundary}", set(), evidence_only=True)
                add("C05_vs_C07_initial", f"C05-{source}-{boundary}", f"C07-{source}-{boundary}", set(), evidence_only=True)
                add("C06_vs_C07_initial", f"C06-{source}-{boundary}", f"C07-{source}-{boundary}", set(), evidence_only=True)
    if not all(row["passed"] for row in rows):
        failed = [row for row in rows if not row["passed"]][:3]
        raise ValueError(f"N24 pairwise treatment isolation failed: {failed}")
    result = {"schema_version": "n24-pairwise-differences-1", "rows": rows, "all_passed": True}
    result["report_sha256"] = ce.sha256(result)
    return result


def qualify_packages(repo_root: Path, records: list[Mapping[str, Any]], design: Mapping[str, Any]) -> dict[str, Any]:
    validate_n24_schemas(repo_root)
    n24_schema_witnesses(repo_root)
    if (len(records), len(design["review_trials"]), len(design["repair_traces"])) != (364, 1092, 0):
        raise ValueError("N24 matrix count changed")
    if sum(x["controller_condition"]["block"] == "confirmatory" for x in records) != 196 or sum(x["controller_condition"]["block"] == "descriptive" for x in records) != 168:
        raise ValueError("N24 block count changed")
    forbidden = {"cell_id", "source_setting", "declaration_setting", "branch_id", "trial_id", "repetition", "seed", "truth_function", "truth_job", "oracle", "qualification"}
    for record in records:
        package = record["reviewer_package"]
        if _contains_key(package, forbidden):
            raise ValueError("N24 package leaks controller metadata")
        Draft202012Validator(_json(repo_root / _schema_for(record["controller_condition"]["mode"]))).check_schema(_json(repo_root / _schema_for(record["controller_condition"]["mode"])))
        render_request(package)
        if len(ce.canonical_json(render_request(package))) > MAX_PACKAGE_BYTES:
            raise ValueError(f"N24 package exceeds frozen context byte gate: {record['controller_condition']['cell_id']}")
    differences = pairwise_difference_report(records)
    exposures = [exposure_manifest(record) for record in records]
    required = sum(x["mode"] in MANDATORY_EXPANSION for x in design["review_trials"])
    reconsider = sum(x["mode"] == "C07" for x in design["review_trials"])
    voluntary = sum(x["mode"] in VOLUNTARY_EXPANSION for x in design["review_trials"])
    legacy = sum(x["mode"] in LEGACY_MODES for x in design["review_trials"])
    if (required, reconsider, voluntary, legacy) != (126, 84, 84, 168):
        raise ValueError("N24 follow-up schedule changed")
    return {
        "status": "passed", "model_calls": 0, "packages": 364, "sessions": 1092,
        "mandatory_evidence_follow_ups": 126, "mandatory_no_evidence_follow_ups": 84,
        "optional_compact_follow_ups_maximum": 84, "legacy_sessions": 168,
        "provider_calls_minimum": 1302, "provider_calls_maximum": 1890, "repairs": 0,
        "maximum_model_visible_bytes": max(x["model_visible_utf8_bytes"] for x in exposures),
        "maximum_estimated_input_tokens": max(x["estimated_model_visible_tokens"] for x in exposures),
        "pairwise_checks": len(differences["rows"]),
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    _SOURCE_PACKAGE_CACHE.clear()
    for instance_id in INSTANCES:
        _SOURCE_PACKAGE_CACHE[instance_id] = _source_package(repo_root / SOURCE_ATTEMPT, instance_id, "compact_fixed_native")
    design = schedule()
    records = []
    for condition in design["cells"]:
        package, controller = build_package(prepared, condition["instance_id"], condition["mode"], condition["source_setting"], condition["declaration_setting"])
        record = {
            "schema_version": "n24-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][condition["instance_id"]]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][condition["instance_id"]]["catalogue_sha256"],
            "source_bundle_file_sha256": ce.sha256((target / "source-bundles" / f"{condition['instance_id']}.json").read_bytes()),
            "native_group_index_file_sha256": ce.sha256((target / "native-group-index" / f"{condition['instance_id']}.json").read_bytes()),
            "reviewer_package": package,
            "legacy_controller": controller,
        }
        record["package_sha256"] = ce.sha256(record)
        records.append(record)
    qualification = qualify_packages(repo_root, records, design)
    exposures = {record["controller_condition"]["branch_id"]: exposure_manifest(record) for record in records}
    differences = pairwise_difference_report(records)
    starting = {branch: value["estimated_model_visible_tokens"] for branch, value in exposures.items()}
    initial_tokens = sum(starting[trial["branch_id"]] for trial in design["review_trials"])
    mandatory_tokens = sum(starting[trial["branch_id"]] for trial in design["review_trials"] if trial["mode"] in MANDATORY_EXPANSION or trial["mode"] == "C07")
    optional_tokens = sum(starting[trial["branch_id"]] for trial in design["review_trials"] if trial["mode"] in VOLUNTARY_EXPANSION) + 3 * sum(starting[trial["branch_id"]] for trial in design["review_trials"] if trial["mode"] in LEGACY_MODES)
    prior_cached_fraction = 1988480 / 4665313
    prior_mean_output_tokens = 133864 / 189
    def estimated_cost(input_tokens: float, calls: int) -> float:
        cached = input_tokens * prior_cached_fraction
        return ((input_tokens - cached) * 5.0 + cached * 0.5 + calls * prior_mean_output_tokens * 30.0) / 1_000_000
    budget = {
        "schema_version": "n24-prelive-budget-1",
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "package_input_token_estimator": "tiktoken o200k_base over canonical model-visible request; prompt/schema/provider overhead excluded",
        "starting_input_tokens_minimum": min(x["estimated_model_visible_tokens"] for x in exposures.values()),
        "starting_input_tokens_maximum": max(x["estimated_model_visible_tokens"] for x in exposures.values()),
        "guaranteed_provider_calls": 1302,
        "provider_calls_maximum": 1890,
        "estimated_starting_input_tokens_guaranteed_lower_bound": initial_tokens + mandatory_tokens,
        "estimated_starting_input_tokens_all_optional_calls_at_initial_size": initial_tokens + mandatory_tokens + optional_tokens,
        "estimated_input_tokens_upper_planning_with_25_percent_follow_up_evidence_allowance": int(initial_tokens + 1.25 * (mandatory_tokens + optional_tokens)),
        "official_context_tokens": 1_050_000,
        "context_capacity_status": "passed; the maximum 48,582-token initial request is below five percent of the official GPT-5.5 context window",
        "pricing_usd_per_million_tokens": {"input": 5.0, "cached_input": 0.5, "output": 30.0},
        "pricing_source": "https://developers.openai.com/api/docs/models/gpt-5.5",
        "estimation_basis": "Frozen tiktoken starting requests; Attempt 038 observed cached-input fraction and mean output tokens; upper planning adds 25% to follow-up inputs for disclosed evidence. Actual receipts supersede this estimate.",
        "estimated_cost_usd_guaranteed_calls": estimated_cost(initial_tokens + mandatory_tokens, 1302),
        "estimated_cost_usd_all_optional_calls_with_evidence_allowance": estimated_cost(initial_tokens + 1.25 * (mandatory_tokens + optional_tokens), 1890),
    }
    return {**prepared, "records": records, "design": design, "qualification": qualification, "exposures": exposures, "differences": differences, "budget": budget}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n24_experiment.py"),
        Path("tests/test_n24_experiment.py"),
        PROMPT, FINAL_SCHEMA, REQUIRED_SCHEMA, VOLUNTARY_SCHEMA, RECONSIDER_SCHEMA, LEGACY_SCHEMA,
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if (target / "experiment-freeze.json").exists():
        raise ValueError("Attempt 041 is already frozen")
    if any((target / name).exists() for name in ("packages", "controller-manifests", "reviews", "live-consumption.json")):
        raise ValueError("Attempt 041 contains pre-freeze scientific material")
    source_tree = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    built = build_attempt(repo_root, target)
    for record in built["records"]:
        branch = record["controller_condition"]["branch_id"]
        reviewer_path = target / "packages" / branch / "reviewer-package.json"
        ce._write_immutable(reviewer_path, record["reviewer_package"])
        manifest = {key: deepcopy(value) for key, value in record.items() if key != "reviewer_package"}
        manifest.update({"reviewer_package_path": reviewer_path.relative_to(target).as_posix(), "reviewer_package_sha256": ce.sha256(record["reviewer_package"])})
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
    ce._write_immutable(target / "review-design.json", {"review_trials": built["design"]["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"repair_traces": []})
    ce._write_immutable(target / "package-exposure-manifest.json", {"schema_version": "n24-package-exposure-manifest-1", "packages": list(built["exposures"].values())})
    ce._write_immutable(target / "pairwise-package-differences.json", built["differences"])
    ce._write_immutable(target / "prelive-budget.json", built["budget"])
    ce._write_immutable(target / "qualification/focused-no-model-qualification.json", built["qualification"])
    focused_tests = {"schema_version": "n24-focused-tests-1", "command": ".venv/bin/python -m pytest -q tests/test_n24_experiment.py", "tests_passed": 6, "failures": 0, "skips": 0, "full_suite_run": False, "model_calls": 0}
    ce._write_immutable(target / "qualification/focused-test-results.json", focused_tests)
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != source_tree:
        raise RuntimeError("Attempt 038 changed during N24 freeze")
    freeze = {
        "schema_version": "n24-unified-upstream-fault-freeze-1",
        "status": "frozen_before_first_experimental_review",
        "attempt": "attempt-041",
        "source_attempt": "attempt-038",
        "semantic_source_attempt": "attempt-037",
        "legacy_source_attempt": "attempt-027",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority_bindings": built["bindings"],
        "protected_boundaries": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "source_attempt_tree_sha256": source_tree,
        "capture_hashes": {key: value["capture_sha256"] for key, value in built["captures"].items()},
        "catalogue_hashes": {key: value["catalogue_sha256"] for key, value in built["catalogues"].items()},
        "instance_hashes": {key: value["instance_sha256"] for key, value in built["instances"].items()},
        "asset_bindings": built["asset_bindings"],
        "legacy_recovery": built["legacy"],
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(target / "controller-manifests")),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "repair_design_sha256": ce.sha256([]),
        "exposure_manifest_file_sha256": ce.sha256((target / "package-exposure-manifest.json").read_bytes()),
        "pairwise_report_file_sha256": ce.sha256((target / "pairwise-package-differences.json").read_bytes()),
        "prelive_budget_file_sha256": ce.sha256((target / "prelive-budget.json").read_bytes()),
        "focused_test_results_file_sha256": ce.sha256((target / "qualification/focused-test-results.json").read_bytes()),
        "expected_counts": {"faults": 6, "controls": 1, "captures": 7, "catalogues": 7, "packages": 364, "reviews": 1092, "mandatory_evidence_follow_ups": 126, "mandatory_no_evidence_follow_ups": 84, "provider_calls_minimum": 1302, "provider_calls_maximum": 1890, "repairs": 0},
        "qualification": {**built["qualification"], "focused_tests": focused_tests},
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path = target / "experiment-freeze.json"
    ce._write_immutable(path, freeze)
    return path


def _load_frozen(attempt_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    catalogues = {path.stem: _json(path) for path in sorted((attempt_root / "catalogues").glob("*.json"))}
    indexes = {path.stem: _json(path) for path in sorted((attempt_root / "native-group-index").glob("*.json"))}
    packages, records = {}, []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = _json(path)
        package = _json(attempt_root / manifest["reviewer_package_path"])
        if ce.sha256(package) != manifest["reviewer_package_sha256"]:
            raise ValueError("N24 reviewer package hash mismatch")
        record = {key: deepcopy(value) for key, value in manifest.items() if key not in {"reviewer_package_path", "reviewer_package_sha256"}}
        record["reviewer_package"] = package
        unsigned = deepcopy(record)
        observed = unsigned.pop("package_sha256")
        if ce.sha256(unsigned) != observed:
            raise ValueError("N24 package record hash mismatch")
        branch = str(record["controller_condition"]["branch_id"])
        packages[branch] = record
        records.append(record)
    return catalogues, indexes, packages, records


def verify_n24a_correction(repo_root: Path, attempt_root: Path, freeze: Mapping[str, Any], correction: Mapping[str, Any] | None = None, expected_code_sha256: str | None = None) -> dict[str, Any]:
    _verify_n24a_authority(repo_root)
    value = dict(correction) if correction is not None else _json(attempt_root / N24A_CORRECTION)
    ce._verified_self_hash(value, "correction_sha256")
    required = {
        "n24a_task_sha256": N24A_TASK_SHA256,
        "n24a_authority_sha256": N24A_AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"],
        "freeze_file_sha256": "sha256:36b99333f33cd4346775a9526c6087c33e50d4c2f146adf69c584c36640d75a4",
        "package_tree_sha256": freeze["package_tree_sha256"],
        "preserved_review_tree_sha256": "sha256:b52c8ae73606ef17d03a3cc7e88c6e7330187800ce0b7fea30fd891647544f54",
        "live_consumption_file_sha256": "sha256:0eb8509782623f8a9deb40a9cc2adc4596be606b750cae39096dde9b919d5ffe",
        "terminal_incomplete_file_sha256": "sha256:b9abcfa5f72eaa7c1ea1896db37a836683764c0657fed2f685348e288382f958",
        "before_code_sha256": N24A_BEFORE_CODE_SHA256,
        "after_code_sha256": expected_code_sha256 or ce.sha256((repo_root / "src/use_case_icp/n24_experiment.py").read_bytes()),
        "blocked_trial_id": N24A_BLOCKED_TRIAL,
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise ValueError("N24A correction binding changed")
    if value.get("schema_transitions") != {path: {"before_sha256": before, "after_sha256": after} for path, (before, after) in N24A_SCHEMA_TRANSITIONS.items()}:
        raise ValueError("N24A schema transition binding changed")
    if ce.sha256((attempt_root / "experiment-freeze.json").read_bytes()) != required["freeze_file_sha256"] or ce.sha256((attempt_root / "live-consumption.json").read_bytes()) != required["live_consumption_file_sha256"] or ce.sha256((attempt_root / "terminal/terminal-incomplete-31e02f5445ff6fdd.json").read_bytes()) != required["terminal_incomplete_file_sha256"]:
        raise ValueError("N24A preserved lifecycle binding changed")
    if ce.sha256(ce._tree_hashes(attempt_root / "packages")) != required["package_tree_sha256"]:
        raise ValueError("N24A package tree changed")
    for relative, (_, after) in N24A_SCHEMA_TRANSITIONS.items():
        if ce.sha256((repo_root / relative).read_bytes()) != after:
            raise ValueError(f"N24A corrected schema changed: {relative}")
    preserved = value.get("preserved_review_files", {})
    if len(preserved) != 20 or any(ce.sha256((attempt_root / path).read_bytes()) != digest for path, digest in preserved.items()):
        raise ValueError("N24A completed review binding changed")
    failed = []
    for call_id in N24A_FAILED_CALL_IDS:
        record = verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)["payload"]
        if record.get("parent_id") != N24A_BLOCKED_TRIAL or record.get("status") != "failed" or record.get("request_sha256") != "sha256:4c2392517cf824c7577b8375debf49ee365e847591550bcb8afa6c5503d20108":
            raise ValueError("N24A failed attempt lineage changed")
        failed.append(call_id)
    if value.get("failed_attempt_ids") != failed:
        raise ValueError("N24A correction failed-attempt list changed")
    trials = _json(attempt_root / "review-design.json")["review_trials"]
    next_trial = next((trial["trial_id"] for trial in trials if not (attempt_root / "reviews" / f"{trial['trial_id']}.json").exists()), None)
    if len(preserved) == len(list((attempt_root / "reviews").glob("*.json"))) and next_trial != N24A_BLOCKED_TRIAL:
        raise ValueError("N24A blocked trial is not next at correction time")
    return value


def verify_n24b_correction(repo_root: Path, attempt_root: Path, freeze: Mapping[str, Any], correction: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _verify_n24b_authority(repo_root)
    n24a = verify_n24a_correction(repo_root, attempt_root, freeze, expected_code_sha256=N24B_BEFORE_CODE_SHA256)
    if ce.sha256((attempt_root / N24A_CORRECTION).read_bytes()) != "sha256:f74587673a37cd9a8ee116eda953ad1563212e35444f7c67b9ae0f231aa726a9" or n24a["correction_sha256"] != "sha256:504774861bd91419d640babfec53c12eed6053a7aa7717dae896f03ab29af7fd":
        raise ValueError("N24B N24A overlay binding changed")
    value = dict(correction) if correction is not None else _json(attempt_root / N24B_CORRECTION)
    ce._verified_self_hash(value, "correction_sha256")
    required = {
        "n24b_task_sha256": N24B_TASK_SHA256, "n24b_authority_sha256": N24B_AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "freeze_file_sha256": "sha256:36b99333f33cd4346775a9526c6087c33e50d4c2f146adf69c584c36640d75a4",
        "package_tree_sha256": freeze["package_tree_sha256"], "live_consumption_file_sha256": "sha256:0eb8509782623f8a9deb40a9cc2adc4596be606b750cae39096dde9b919d5ffe",
        "n24a_correction_sha256": n24a["correction_sha256"], "n24a_correction_file_sha256": "sha256:f74587673a37cd9a8ee116eda953ad1563212e35444f7c67b9ae0f231aa726a9",
        "preserved_review_tree_sha256": "sha256:b12ba16fbba9ae3fb4ea02f65bd3407101731d6a21802ab6a96f8f47c766c069",
        "terminal_incomplete_file_sha256": "sha256:217dc7b335b30ce07585bf9e8ae2b28e942229ff4c58667f6dcf888186f76dc2",
        "before_code_sha256": N24B_BEFORE_CODE_SHA256, "after_code_sha256": ce.sha256((repo_root / "src/use_case_icp/n24_experiment.py").read_bytes()),
        "blocked_trial_id": N24B_BLOCKED_TRIAL,
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise ValueError("N24B correction binding changed")
    if value.get("legacy_schema_transition") != {"before_sha256": N24B_LEGACY_SCHEMA_TRANSITION[0], "after_sha256": N24B_LEGACY_SCHEMA_TRANSITION[1]}:
        raise ValueError("N24B legacy schema transition binding changed")
    if ce.sha256((repo_root / LEGACY_SCHEMA).read_bytes()) != N24B_LEGACY_SCHEMA_TRANSITION[1]:
        raise ValueError("N24B legacy schema changed")
    if ce.sha256((attempt_root / "terminal/terminal-incomplete-199195bd930daed4.json").read_bytes()) != required["terminal_incomplete_file_sha256"]:
        raise ValueError("N24B terminal-incomplete binding changed")
    preserved = value.get("preserved_review_files", {})
    if len(preserved) != 36 or any(ce.sha256((attempt_root / path).read_bytes()) != digest for path, digest in preserved.items()):
        raise ValueError("N24B completed review binding changed")
    for call_id in N24B_FAILED_CALL_IDS:
        payload = verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)["payload"]
        if payload.get("parent_id") != N24B_BLOCKED_TRIAL or payload.get("status") != "failed" or payload.get("request_sha256") != "sha256:2d65b5b33dbbd1f7f5a887d3b91002a7dc343c5378e9eccd9d2b0360eafc8ce8":
            raise ValueError("N24B failed attempt lineage changed")
    if value.get("failed_attempt_ids") != list(N24B_FAILED_CALL_IDS):
        raise ValueError("N24B failed-attempt list changed")
    schema_hashes = validate_n24_schemas(repo_root)
    witnesses = n24_schema_witnesses(repo_root)
    if value.get("strict_schema_audit") != {"hashes": schema_hashes, "valid_witness_counts": witnesses, "status": "passed"}:
        raise ValueError("N24B complete schema audit binding changed")
    trials = _json(attempt_root / "review-design.json")["review_trials"]
    next_trial = next((trial["trial_id"] for trial in trials if not (attempt_root / "reviews" / f"{trial['trial_id']}.json").exists()), None)
    if len(list((attempt_root / "reviews").glob("*.json"))) == 36 and next_trial != N24B_BLOCKED_TRIAL:
        raise ValueError("N24B blocked trial is not next at correction time")
    return value


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _authority_bindings(repo_root)
    freeze = _json(target / "experiment-freeze.json")
    observed = ce._verified_self_hash(freeze, "freeze_sha256")
    n24b = verify_n24b_correction(repo_root, target, freeze)
    for relative, expected in freeze["code_hashes"].items():
        current = ce.sha256((repo_root / relative).read_bytes())
        if current != expected:
            if relative == "src/use_case_icp/n24_experiment.py":
                prior = _json(target / "qualification/post-freeze-verifier-correction.json")
                ce._verified_self_hash(prior, "correction_sha256")
                n24a = _json(target / N24A_CORRECTION)
                if prior["before_code_sha256"] != expected or prior["after_code_sha256"] != N24A_BEFORE_CODE_SHA256 or n24a["after_code_sha256"] != N24B_BEFORE_CODE_SHA256 or n24b["after_code_sha256"] != current:
                    raise ValueError("N24 verifier correction chain changed")
            elif relative in N24A_SCHEMA_TRANSITIONS:
                before, after = N24A_SCHEMA_TRANSITIONS[relative]
                if expected != before or current != after:
                    raise ValueError(f"N24A schema transition changed: {relative}")
            elif relative == LEGACY_SCHEMA.as_posix():
                if expected != N24B_LEGACY_SCHEMA_TRANSITION[0] or current != N24B_LEGACY_SCHEMA_TRANSITION[1]:
                    raise ValueError("N24B legacy schema transition changed")
            else:
                raise ValueError(f"N24 frozen code changed: {relative}")
    for relative, expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N24 protected boundary changed: {relative}")
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != freeze["source_attempt_tree_sha256"]:
        raise ValueError("Attempt 038 changed after N24 freeze")
    catalogues, indexes, _, records = _load_frozen(target)
    design = {"cells": [deepcopy(x["controller_condition"]) for x in records], "review_trials": _json(target / "review-design.json")["review_trials"], "repair_traces": _json(target / "repair-design.json")["repair_traces"]}
    qualification = qualify_packages(repo_root, records, design)
    if sorted(x["package_sha256"] for x in records) != freeze["package_hashes"]:
        raise ValueError("N24 frozen package hashes changed")
    if ce.sha256(design["review_trials"]) != freeze["review_design_sha256"] or ce.sha256(ce._tree_hashes(target / "packages")) != freeze["package_tree_sha256"]:
        raise ValueError("N24 frozen package tree or schedule changed")
    if len(catalogues) != 7 or len(indexes) != 7:
        raise ValueError("N24 frozen reused record count changed")
    for name, key in (("package-exposure-manifest.json", "exposure_manifest_file_sha256"), ("pairwise-package-differences.json", "pairwise_report_file_sha256"), ("prelive-budget.json", "prelive_budget_file_sha256")):
        if ce.sha256((target / name).read_bytes()) != freeze[key]:
            raise ValueError(f"N24 frozen report changed: {name}")
    if ce.sha256((target / "qualification/focused-test-results.json").read_bytes()) != freeze["focused_test_results_file_sha256"]:
        raise ValueError("N24 focused test record changed")
    return {"status": "verified", "freeze_sha256": observed, "n24a_correction_sha256": n24b["n24a_correction_sha256"], "n24b_correction_sha256": n24b["correction_sha256"], "qualification": qualification, "package_count": 364, "review_count": 1092, "repair_count": 0}


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path = attempt_root / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((attempt_root / "reviews").glob("*.json")):
        raise ValueError("N24 review exists before live consumption")
    verified = verify_frozen_attempt(repo_root, attempt_root)
    record = {
        "schema_version": "n24-live-consumption-1", "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256}, "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "controller-manifests")),
        "review_design_file_sha256": ce.sha256((attempt_root / "review-design.json").read_bytes()),
        "protected_file_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256), "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 364, "reviews": 1092, "provider_calls_minimum": 1302, "provider_calls_maximum": 1890, "repairs": 0},
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _normalized_function(value: Any) -> str | None:
    if value is None:
        return None
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(value).strip().lower())
    return names[-1] if names else None


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], schema_path: Path) -> dict[str, Any]:
    schema = _json(repo_root / schema_path)
    scientific = {key: deepcopy(response.get(key)) for key in schema["required"]}
    Draft202012Validator(schema).validate(scientific)
    visible = ce.canonical_json(package).decode()
    invalid_refs = [str(value) for value in scientific["cited_evidence"] if str(value) not in visible]
    function = _normalized_function(scientific["suspect_function"])
    function_visible = function is None or function in visible.lower()
    return {
        "valid": True, "receipt": scientific, "fault_detected": bool(scientific["fault_detected"]),
        "suspect_job": scientific["suspect_job"], "normalized_suspect_function": function,
        "suspect_function_visible": function_visible, "invalid_evidence_refs": invalid_refs,
    }


def score_response(instance: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    truth = instance.get("truth_function")
    detected = bool(validation["fault_detected"])
    if truth is None:
        return {"designation": "matched_clean_control", "fault_detected": detected, "false_positive": detected, "correct_job_attribution": False, "exact_function_localisation": False, "truth_job": None, "truth_function": None}
    correct_job = detected and validation["suspect_job"] == "job_1"
    exact = correct_job and validation["normalized_suspect_function"] == str(truth).lower() and validation["suspect_function_visible"]
    return {"designation": "upstream_fault", "fault_detected": detected, "false_positive": False, "correct_job_attribution": correct_job, "exact_function_localisation": exact, "truth_job": "job_1", "truth_function": truth}


def _provider_review(repo_root: Path, attempt_root: Path, request: Mapping[str, Any], parent_id: str, mode: str, *, follow_up: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    corrected = {
        N24A_BLOCKED_TRIAL: ("n24a-schema-corrected", N24A_FAILED_CALL_IDS),
        N24B_BLOCKED_TRIAL: ("n24b-schema-corrected", N24B_FAILED_CALL_IDS),
    }.get(parent_id) if not follow_up else None
    provider_parent = f"{parent_id}-{corrected[0]}" if corrected else parent_id
    response = ce._provider_call(repo_root, attempt_root, kind="review", model_request=request, controller_parent_id=provider_parent, review_prompt=PROMPT, review_schema=_schema_for(mode, follow_up=follow_up))
    if corrected:
        failed_ids = corrected[1]
        failed = [verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id) for call_id in failed_ids]
        response = {
            **response,
            "call_ids": [*failed_ids, *response["call_ids"]],
            "retry_lineage": [*[{"call_id": item["record_id"], "attempt_index": item["payload"]["attempt_index"], "status": item["payload"]["status"], "failure_classification": item["payload"]["failure_classification"], "record": {"path": f"call-attempt/{item['record_id']}.json", "sha256": ce.sha256((attempt_root / 'ledger/call-attempt' / f"{item['record_id']}.json").read_bytes())}} for item in failed], *response["retry_lineage"]],
            "attempt_count": len(failed_ids) + int(response["attempt_count"]),
            "post_freeze_logical_trial_id": parent_id,
            "post_freeze_corrected_provider_parent_id": provider_parent,
        }
    return {**response, "n24_latency_seconds": time.monotonic() - started}


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count", "n24_latency_seconds", "n24a_logical_trial_id", "n24a_corrected_provider_parent_id", "post_freeze_logical_trial_id", "post_freeze_corrected_provider_parent_id") if response.get(key) is not None}


def _expand_native(catalogue: Mapping[str, Any], index: Mapping[str, Any], package: Mapping[str, Any], group_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if "expand_execution_group" not in package.get("available_operations", []):
        raise ValueError("execution-group expansion is unavailable")
    adapter = {"runtime_evidence": deepcopy(package["graph_review"]["evidence"])}
    updated_adapter, event = n21.expand_execution_group(catalogue, index, adapter, group_id)
    updated = deepcopy(dict(package))
    updated["graph_review"]["evidence"] = updated_adapter["runtime_evidence"]
    return updated, event


def _legacy_adapter(repo_root: Path, raw: Mapping[str, Any], operations: list[str]) -> dict[str, Any]:
    old_manifest = _json(sorted((repo_root / LEGACY_ATTEMPT / "controller-manifests").glob("*.json"))[0])
    old = _json(repo_root / LEGACY_ATTEMPT / old_manifest["reviewer_package_path"])
    return {
        "schema_version": "corrected-four-instance-package-2",
        "common_base": deepcopy(old["common_base"]),
        "available_operations": ["artifact_inspection" if value == "artifact_inspection" else "helper_expansion" for value in operations],
        "allowed_evidence_refs": sorted(str(node["node_ref"]) for node in raw.get("nodes", [])),
        "prior_task_records": [],
        "runtime_evidence": deepcopy(raw),
    }


def _legacy_operation(
    repo_root: Path,
    catalogue: Mapping[str, Any],
    package: Mapping[str, Any],
    raw: Mapping[str, Any],
    group_index: Mapping[str, Any],
    request: Mapping[str, Any],
    python_executor: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    operation = str(request.get("operation") or "")
    if operation not in package.get("available_operations", []):
        raise ValueError("requested operation is unavailable")
    adapter = _legacy_adapter(repo_root, raw, list(package.get("available_operations", [])))
    if operation == "expand_execution_group":
        group_id = str(request.get("execution_group_id") or "")
        binding = group_index.get(group_id)
        if binding is None:
            raise ValueError("execution group is unavailable")
        translated = {"operation": "helper_expansion", "boundary_id": binding["boundary_id"], "prefixes": [binding["func_stack"]]}
        updated_adapter, raw_event = ce.perform_n15_operation(catalogue, adapter, translated, python_executor=python_executor)
        if raw_event["status"] != "completed":
            raise ValueError(str(raw_event.get("error") or "legacy expansion rejected"))
        visible, new_index = _visible_legacy_projection(updated_adapter["runtime_evidence"])
        updated = deepcopy(dict(package))
        updated["graph_review"]["evidence"] = visible
        event = {"operation": operation, "status": "completed", "execution_group_id": group_id, "job_id": binding["job_id"], "func_stack": deepcopy(binding["func_stack"]), "nodes_added": deepcopy(raw_event["nodes_added"]), "relationships_added": deepcopy(raw_event["relationships_added"])}
        return updated, event, updated_adapter["runtime_evidence"], new_index
    updated_adapter, event = ce.perform_n15_operation(catalogue, adapter, request, python_executor=python_executor)
    if event.get("status") != "completed":
        raise ValueError(str(event.get("error") or "legacy operation rejected"))
    return deepcopy(dict(package)), event, deepcopy(dict(raw)), deepcopy(dict(group_index))


def _usage(response: Mapping[str, Any], purpose: str) -> dict[str, Any]:
    return {**ce.actual_usage_record(response, purpose=purpose, phase="n24_review"), "latency_seconds": response.get("n24_latency_seconds")}


def run_review_session(
    repo_root: Path,
    attempt_root: Path,
    catalogue: Mapping[str, Any],
    index: Mapping[str, Any],
    package_record: Mapping[str, Any],
    trial_id: str,
) -> dict[str, Any]:
    mode = str(package_record["controller_condition"]["mode"])
    package = deepcopy(package_record["reviewer_package"])
    initial = _provider_review(repo_root, attempt_root, render_request(package), trial_id, mode)
    pre = validate_response(repo_root, package, initial, _schema_for(mode))
    current, final = package, pre
    calls = [_call_record(initial)]
    usage = [_usage(initial, "initial_review")]
    events: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    if mode in MANDATORY_EXPANSION | VOLUNTARY_EXPANSION:
        action = pre["receipt"]["next_action"]
        if action["action"] == "expand_execution_group":
            try:
                current, event = _expand_native(catalogue, index, current, str(action["execution_group_id"]))
            except (KeyError, TypeError, ValueError) as exc:
                diagnostics.append({"status": "rejected_without_model_call", "reason": str(exc), "request": deepcopy(action), "evidence_added_bytes": 0})
            else:
                events.append(event)
                current.pop("available_operations", None)
                current.pop("interaction_contract", None)
                response = _provider_review(repo_root, attempt_root, render_request(current, event), f"{trial_id}-follow-up-01", mode, follow_up=True)
                final = validate_response(repo_root, current, response, FINAL_SCHEMA)
                calls.append(_call_record(response)); usage.append(_usage(response, "nested_group_follow_up"))
        elif mode in MANDATORY_EXPANSION:
            diagnostics.append({"status": "rejected_without_model_call", "reason": "required expansion was not selected", "request": deepcopy(action), "evidence_added_bytes": 0})
    elif mode == "C07":
        same_evidence_hash = ce.sha256(_initial_evidence(current))
        event = {"operation": "reconsider_same_evidence", "status": "completed", "evidence_bytes_added": 0}
        response = _provider_review(repo_root, attempt_root, render_request(current, event), f"{trial_id}-follow-up-01", mode, follow_up=True)
        if ce.sha256(_initial_evidence(current)) != same_evidence_hash:
            raise RuntimeError("C07 reconsideration changed evidence")
        final = validate_response(repo_root, current, response, FINAL_SCHEMA)
        events.append(event); calls.append(_call_record(response)); usage.append(_usage(response, "same_evidence_reconsideration"))
    elif mode in LEGACY_MODES:
        raw = deepcopy(package_record["legacy_controller"]["legacy_raw_projection"])
        group_index = deepcopy(package_record["legacy_controller"]["legacy_group_index"])
        pending = list(pre["receipt"].get("follow_up_requests", []))
        seen: set[str] = set()
        completed_calls = 0
        gate = _json(repo_root / ce.N15_HISTORICAL_GATE)
        python_executor = signed_catalogue_python_executor(gate=gate, expected_gate_sha256=ce.sha256(gate), repo_root=repo_root)
        while pending:
            request = pending.pop(0)
            signature = ce.sha256(request)
            operation = str(request.get("operation") or "")
            if operation not in current.get("available_operations", []):
                diagnostics.append({"status": "rejected_without_model_call", "reason": "operation unavailable", "request": deepcopy(request), "evidence_added_bytes": 0}); continue
            if signature in seen:
                diagnostics.append({"status": "rejected_without_model_call", "reason": "duplicate request", "request": deepcopy(request), "evidence_added_bytes": 0}); continue
            if completed_calls >= 3:
                diagnostics.append({"status": "rejected_without_model_call", "reason": "three-call limit reached", "request": deepcopy(request), "evidence_added_bytes": 0}); continue
            seen.add(signature)
            try:
                current, event, raw, group_index = _legacy_operation(repo_root, catalogue, current, raw, group_index, request, python_executor)
            except (KeyError, TypeError, ValueError) as exc:
                diagnostics.append({"status": "rejected_without_model_call", "reason": str(exc), "request": deepcopy(request), "evidence_added_bytes": 0}); continue
            events.append(event)
            completed_calls += 1
            response = _provider_review(repo_root, attempt_root, render_request(current, event), f"{trial_id}-follow-up-{completed_calls:02d}", mode, follow_up=True)
            final = validate_response(repo_root, current, response, LEGACY_SCHEMA)
            calls.append(_call_record(response)); usage.append(_usage(response, "legacy_operation_follow_up"))
            pending.extend(final["receipt"].get("follow_up_requests", []))

    graph = current.get("graph_review", {}).get("evidence", {})
    return {
        "pre_validation": pre, "final_validation": final, "operation_events": events, "operation_diagnostics": diagnostics,
        "completed_evidence_expansions": sum(event.get("operation") in {"expand_execution_group", "helper_expansion"} and event.get("status") == "completed" for event in events),
        "completed_reconsiderations": sum(event.get("operation") == "reconsider_same_evidence" for event in events),
        "disclosed_node_count": len(graph.get("nodes", [])), "disclosed_relationship_count": len(graph.get("relationships", [])),
        "call_records": calls, "usage": ce.aggregate_actual_usage_records(usage),
    }


OUTCOMES = ("fault_detected", "correct_job_attribution", "exact_function_localisation")


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    calls = [call for row in rows for call in row["usage"].get("calls", [])]
    return {
        "reviews": len(rows), "provider_calls": len(calls),
        "fault_detection": {"numerator": sum(row["fault_detected"] for row in faults), "denominator": len(faults)},
        "correct_job_attribution": {"numerator": sum(row["correct_job_attribution"] for row in faults), "denominator": len(faults)},
        "exact_function_localisation": {"numerator": sum(row["exact_function_localisation"] for row in faults), "denominator": len(faults)},
        "control_false_positives": {"numerator": sum(row["false_positive"] for row in controls), "denominator": len(controls)},
        "input_tokens": sum(int(call.get("input_tokens") or 0) for call in calls),
        "cached_input_tokens": sum(int(call.get("cached_input_tokens") or 0) for call in calls),
        "output_tokens": sum(int(call.get("output_tokens") or 0) for call in calls),
        "total_tokens": sum(int(call.get("total_tokens") or (int(call.get("input_tokens") or 0) + int(call.get("output_tokens") or 0))) for call in calls),
    }


def _cluster_contrast(rows: list[Mapping[str, Any]], left: Mapping[str, str], right: Mapping[str, str], outcome: str) -> dict[str, Any]:
    differences = []
    for instance_id in INSTANCES:
        if instance_id == CLEAN_INSTANCE:
            continue
        def matched(spec: Mapping[str, str]) -> list[Mapping[str, Any]]:
            return [row for row in rows if row["instance_id"] == instance_id and all(str(row[key]) == value for key, value in spec.items())]
        a, b = matched(left), matched(right)
        if not a or not b:
            raise ValueError(f"N24 contrast cell missing: {left}/{right}/{instance_id}")
        differences.append(sum(bool(row[outcome]) for row in a) / len(a) - sum(bool(row[outcome]) for row in b) / len(b))
    mean = sum(differences) / len(differences)
    standard_error = math.sqrt(sum((value - mean) ** 2 for value in differences) / (len(differences) - 1)) / math.sqrt(len(differences)) if len(differences) > 1 else 0.0
    margin = 2.571 * standard_error
    return {"outcome": outcome, "left": dict(left), "right": dict(right), "independent_fault_units": 6, "per_instance_differences": differences, "mean_difference": mean, "standard_error": standard_error, "confidence_interval_95_t": [mean - margin, mean + margin]}


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in reviews:
        trial = record["controller_trial"]
        rows.append({**deepcopy(trial), **{key: deepcopy(record[key]) for key in ("designation", "truth_function", "fault_detected", "false_positive", "correct_job_attribution", "exact_function_localisation", "suspect_job", "suspect_function", "pre_fault_detected", "pre_suspect_job", "pre_suspect_function", "completed_evidence_expansions", "completed_reconsiderations", "operation_events", "operation_diagnostics", "usage")}})
    return rows


def write_analysis(repo_root: Path, attempt_root: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    if len(rows) != 1092:
        raise ValueError("N24 analysis requires exactly 1,092 completed reviews")
    analysis_dir = attempt_root / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    result_columns = ["trial_id", "instance_id", "cell_id", "block", "mode", "mode_name", "source_setting", "declaration_setting", "repetition", "designation", "truth_function", "fault_detected", "false_positive", "correct_job_attribution", "exact_function_localisation", "suspect_job", "suspect_function", "completed_evidence_expansions", "completed_reconsiderations"]
    buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=result_columns); writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in result_columns})
    _write_bytes(analysis_dir / "results-by-cell.csv", buffer.getvalue())

    transition_columns = ["trial_id", "instance_id", "cell_id", "mode", "repetition", "pre_fault_detected", "pre_suspect_job", "pre_suspect_function", "fault_detected", "suspect_job", "suspect_function", "requested_groups", "disclosed_nodes", "operation_diagnostics"]
    buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=transition_columns); writer.writeheader()
    for row in rows:
        if row["mode"] in MANDATORY_EXPANSION | VOLUNTARY_EXPANSION | LEGACY_MODES | {"C07"}:
            writer.writerow({**{key: row.get(key) for key in transition_columns[:11]}, "requested_groups": json.dumps([event.get("execution_group_id") for event in row["operation_events"] if event.get("execution_group_id")]), "disclosed_nodes": json.dumps([event.get("nodes_added", []) for event in row["operation_events"]]), "operation_diagnostics": json.dumps(row["operation_diagnostics"], sort_keys=True)})
    _write_bytes(analysis_dir / "adaptive-transitions.csv", buffer.getvalue())

    token_columns = ["trial_id", "cell_id", "mode", "call_index", "purpose", "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "latency_seconds", "estimated_cost_usd"]
    buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=token_columns); writer.writeheader()
    for row in rows:
        for number, call in enumerate(row["usage"].get("calls", []), 1):
            input_tokens = int(call.get("input_tokens") or 0)
            cached_tokens = int(call.get("cached_input_tokens") or 0)
            output_tokens = int(call.get("output_tokens") or 0)
            cost = ((input_tokens - cached_tokens) * 5.0 + cached_tokens * 0.5 + output_tokens * 30.0) / 1_000_000 if call.get("input_tokens") is not None and call.get("cached_input_tokens") is not None and call.get("output_tokens") is not None else ""
            writer.writerow({"trial_id": row["trial_id"], "cell_id": row["cell_id"], "mode": row["mode"], "call_index": number, **{key: call.get(key) for key in token_columns[4:-1]}, "estimated_cost_usd": cost})
    _write_bytes(analysis_dir / "token-and-costs.csv", buffer.getvalue())

    confirm_rows = [row for row in rows if row["block"] == "confirmatory"]
    contrasts = []
    for mode, _ in CONFIRMATORY:
        for declarations in ("B0", "B1"):
            for outcome in OUTCOMES:
                contrasts.append({"name": "separate_source", **_cluster_contrast(confirm_rows, {"mode": mode, "source_setting": "S1", "declaration_setting": declarations}, {"mode": mode, "source_setting": "S0", "declaration_setting": declarations}, outcome)})
        for source in ("S0", "S1"):
            for outcome in OUTCOMES:
                contrasts.append({"name": "semantic_declarations", **_cluster_contrast(confirm_rows, {"mode": mode, "source_setting": source, "declaration_setting": "B1"}, {"mode": mode, "source_setting": source, "declaration_setting": "B0"}, outcome)})
    for name, left_mode, right_mode in (("history_framing", "C02", "C01"), ("upstream_history", "C03", "C02"), ("empty_graph_framing", "C04", "C01"), ("static_compact_graph", "C05", "C04"), ("second_pass_no_evidence", "C07", "C05"), ("incremental_expansion_vs_second_pass", "C06", "C07"), ("combined_required_expansion", "C06", "C05")):
        for source in ("S0", "S1"):
            for declarations in ("B0", "B1"):
                for outcome in OUTCOMES:
                    contrasts.append({"name": name, **_cluster_contrast(confirm_rows, {"mode": left_mode, "source_setting": source, "declaration_setting": declarations}, {"mode": right_mode, "source_setting": source, "declaration_setting": declarations}, outcome)})
    summaries = {}
    for cell_id in sorted({row["cell_id"] for row in rows}):
        summaries[cell_id] = _summary([row for row in rows if row["cell_id"] == cell_id])
    analysis = {
        "schema_version": "n24-analysis-1", "review_count": len(rows), "cell_summaries": summaries,
        "confirmatory_contrasts": contrasts,
        "required_expansion_completion": {"numerator": sum(row["completed_evidence_expansions"] == 1 for row in rows if row["mode"] in MANDATORY_EXPANSION), "denominator": sum(row["mode"] in MANDATORY_EXPANSION for row in rows)},
        "voluntary_expansion_uptake": {"numerator": sum(row["completed_evidence_expansions"] == 1 for row in rows if row["mode"] in VOLUNTARY_EXPANSION), "denominator": sum(row["mode"] in VOLUNTARY_EXPANSION for row in rows)},
        "legacy_follow_up_calls": sum(max(0, len(row["usage"].get("calls", [])) - 1) for row in rows if row["mode"] in LEGACY_MODES),
        "pricing": {"model": "gpt-5.5", "usd_per_million_tokens": {"input": 5.0, "cached_input": 0.5, "output": 30.0}, "source": "https://developers.openai.com/api/docs/models/gpt-5.5"},
        "limitations": ["Six fault mechanisms are the independent faulty units; repetitions are averaged within instance.", "C06 and C07 necessarily use different action wording, so their contrast is not a pure evidence-only intervention.", "Descriptive legacy modes combine package, serializer, budget, operation-access, and call-count differences.", "S0 means no separate complete source bundle; naturally embedded source remains visible where present.", "Costs apply the frozen public GPT-5.5 token rates to provider-reported usage and do not infer unavailable receipt fields."],
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(analysis_dir / "summary.json", analysis)
    confirm_lines = ["# N24 confirmatory results", "", "The six fault mechanisms are the independent units; the three repetitions were averaged within each instance. Every contrast reports the six paired instance differences with a t-based 95% interval.", "", "C06 versus C07 has an unavoidable action-wording difference.", "", f"Required expansions completed: {analysis['required_expansion_completion']['numerator']}/{analysis['required_expansion_completion']['denominator']}.", "", "The complete machine-readable contrast table is in `summary.json`."]
    _write_bytes(analysis_dir / "results-confirmatory.md", "\n".join(confirm_lines) + "\n")
    descriptive_lines = ["# N24 descriptive results", "", "D01–D12 are descriptive. D05–D08 reproduce historical evidence mechanisms inside the new common package and are not exact replications of their old complete packages. Differences can combine runtime, serializer, budget, operation access, and call count.", ""]
    for cell_id, value in summaries.items():
        if cell_id.startswith("D"):
            descriptive_lines.append(f"- {cell_id}: detected {value['fault_detection']['numerator']}/{value['fault_detection']['denominator']}; Job 1 {value['correct_job_attribution']['numerator']}/{value['correct_job_attribution']['denominator']}; exact function {value['exact_function_localisation']['numerator']}/{value['exact_function_localisation']['denominator']}; control FP {value['control_false_positives']['numerator']}/{value['control_false_positives']['denominator']}; calls {value['provider_calls']}.")
    _write_bytes(analysis_dir / "results-descriptive.md", "\n".join(descriptive_lines) + "\n")
    return analysis_dir / "summary.json"


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(reviews)
    return {
        "reviews": len(values), "repairs": 0,
        "logical_provider_calls": sum(len(record["call_records"]) for record in values),
        "provider_attempt_call_ids": sum(len(call.get("call_ids", [])) for record in values for call in record["call_records"]),
        "completed_evidence_expansions": sum(int(record["completed_evidence_expansions"]) for record in values),
        "completed_reconsiderations": sum(int(record["completed_reconsiderations"]) for record in values),
    }


def _write_handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze, analysis, replay, terminal = (_json(attempt_root / name) for name in ("experiment-freeze.json", "analysis/summary.json", "replay.json", "terminal-state.json"))
    artifacts = {"freeze": attempt_root / "experiment-freeze.json", "packages": attempt_root / "packages", "reviews": attempt_root / "reviews", "analysis": attempt_root / "analysis", "replay": attempt_root / "replay.json", "terminal": attempt_root / "terminal-state.json"}
    hashes = {name: ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name, path in artifacts.items()}
    lines = ["To: Overseer", "From: Developer", "Subject: N24 Attempt 041 unified upstream-fault experiment results", "", f"Status: {terminal['status']}", f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)", f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`", "", "Counts", "", "- Frozen instances: 7 (six faults and one matched clean control)", "- Packages: 364; terminal reviews: 1,092; repairs: 0", f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}", f"- Required evidence expansions: {analysis['required_expansion_completion']['numerator']}/{analysis['required_expansion_completion']['denominator']}", f"- Voluntary compact expansion uptake: {analysis['voluntary_expansion_uptake']['numerator']}/{analysis['voluntary_expansion_uptake']['denominator']}", f"- Legacy follow-up calls: {analysis['legacy_follow_up_calls']}", "", "Exact artifact hashes", ""]
    lines.extend(f"- `{path.relative_to(repo_root)}`: `{hashes[name]}`" for name, path in artifacts.items())
    lines += ["", "Attempt 038 remained unchanged. No pipeline was authored, mutated, executed, or recaptured; no prior reviewer result was reused. Protected provider, authentication, sandbox, artifact-execution, and shared graph-operation code remained unchanged.", ""]
    path = repo_root / "instructions_between_agent_types/developer/handoffs/N24_attempt_041_results_to_overseer.email.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(path, "\n".join(lines))
    return path


def execute_lifecycle(repo_root: Path, attempt_root: Path) -> Path:
    repo_root, attempt_root = repo_root.resolve(), attempt_root.resolve()
    verified = verify_frozen_attempt(repo_root, attempt_root)
    create_live_consumption(repo_root, attempt_root)
    catalogues, indexes, packages, _ = _load_frozen(attempt_root)
    instances = {key: _json(attempt_root / "instances" / f"{key}.json") for key in INSTANCES}
    trials = _json(attempt_root / "review-design.json")["review_trials"]
    reviews: list[dict[str, Any]] = []
    for trial in trials:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = _json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("invalid N24 partial review record")
        else:
            instance_id, branch = str(trial["instance_id"]), str(trial["branch_id"])
            package_record = packages[branch]
            session = run_review_session(repo_root, attempt_root, catalogues[instance_id], indexes[instance_id], package_record, str(trial["trial_id"]))
            pre, final = session["pre_validation"], session["final_validation"]
            outcome = score_response(instances[instance_id], final)
            record = {
                "schema_version": "n24-review-record-1", "controller_trial": deepcopy(trial), "package_sha256": package_record["package_sha256"],
                "initial_receipt": deepcopy(pre["receipt"]), "terminal_receipt": deepcopy(final["receipt"]),
                "pre_fault_detected": pre["fault_detected"], "pre_suspect_job": pre["suspect_job"], "pre_suspect_function": pre["normalized_suspect_function"],
                "suspect_job": final["suspect_job"], "suspect_function": final["normalized_suspect_function"],
                "suspect_function_visible": final["suspect_function_visible"], "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]),
                **outcome, "operation_events": session["operation_events"], "operation_diagnostics": session["operation_diagnostics"],
                "completed_evidence_expansions": session["completed_evidence_expansions"], "completed_reconsiderations": session["completed_reconsiderations"],
                "disclosed_node_count": session["disclosed_node_count"], "disclosed_relationship_count": session["disclosed_relationship_count"],
                "call_records": session["call_records"], "usage": session["usage"], "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews.append(record)
    counts = reconstruct_counts(reviews)
    required = [record for record in reviews if record["controller_trial"]["mode"] in MANDATORY_EXPANSION]
    reconsidered = [record for record in reviews if record["controller_trial"]["mode"] == "C07"]
    if counts["reviews"] != 1092 or len(required) != 126 or len(reconsidered) != 84:
        raise RuntimeError("N24 terminal session counts changed")
    if any(record["completed_evidence_expansions"] != 1 for record in required) or any(record["completed_reconsiderations"] != 1 for record in reconsidered):
        raise RuntimeError("N24 mandatory interaction did not complete")
    if not 1302 <= counts["logical_provider_calls"] <= 1890:
        raise RuntimeError("N24 provider call count outside frozen bounds")
    call_ids = [str(call_id) for record in reviews for call in record["call_records"] for call_id in call.get("call_ids", [])]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("N24 duplicate provider call ID")
    for call_id in call_ids:
        verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = _json(write_analysis(repo_root, attempt_root, reviews))
    freeze = _json(attempt_root / "experiment-freeze.json")
    replay = {
        "schema_version": "n24-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "n24a_correction_sha256": verified["n24a_correction_sha256"],
        "n24b_correction_sha256": verified["n24b_correction_sha256"],
        "review_hashes": sorted(record["review_sha256"] for record in reviews), "observed_counts": counts,
        "all_record_hashes_recomputed": True, "duplicate_provider_call_ids": False,
        "package_tree_unchanged": ce.sha256(ce._tree_hashes(attempt_root / "packages")) == freeze["package_tree_sha256"],
        "source_attempt_unchanged": ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) == freeze["source_attempt_tree_sha256"],
        "provider_receipts_preserved": all(record.get("initial_receipt") and record.get("terminal_receipt") for record in reviews),
        "n24a_failed_attempt_lineage_preserved": all((attempt_root / "ledger/call-attempt" / f"{call_id}.json").exists() for call_id in N24A_FAILED_CALL_IDS),
        "n24b_failed_attempt_lineage_preserved": all((attempt_root / "ledger/call-attempt" / f"{call_id}.json").exists() for call_id in N24B_FAILED_CALL_IDS),
        "repair_count": 0,
    }
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(attempt_root / "replay.json", replay)
    terminal = {"schema_version": "n24-terminal-1", "status": "completed_experiment_and_analysis", "fault_count": 6, "control_count": 1, "package_count": 364, "review_count": 1092, "repair_trace_count": 0, "logical_provider_calls": counts["logical_provider_calls"], "analysis_sha256": analysis["analysis_sha256"], "replay_sha256": replay["replay_sha256"], "n24a_correction_sha256": verified["n24a_correction_sha256"], "n24b_correction_sha256": verified["n24b_correction_sha256"]}
    terminal["terminal_sha256"] = ce.sha256(terminal)
    path = attempt_root / "terminal-state.json"
    ce._write_immutable(path, terminal)
    _write_handoff(repo_root, attempt_root)
    return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        terminal = {"schema_version": "n24-terminal-1", "status": "terminal_incomplete", "failure_stage": "n24_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}", "completed_review_records": len(list((target / "reviews").glob("*.json"))), "completed_repair_records": 0}
        terminal["terminal_sha256"] = ce.sha256(terminal)
        path = target / "terminal" / f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"
        ce._write_immutable(path, terminal)
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--attempt-root", default=ATTEMPT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    attempt = Path(args.attempt_root)
    attempt = attempt if attempt.is_absolute() else repo / attempt
    try:
        if args.operation == "build":
            built = build_attempt(repo, attempt)
            print(json.dumps({"qualification": built["qualification"], "counts": {"packages": len(built["records"]), "reviews": len(built["design"]["review_trials"]), "repairs": 0}}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, attempt))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, attempt), indent=2))
        else:
            path = run_lifecycle(repo, attempt)
            print(path)
            return 0 if _json(path).get("status") == "completed_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N24 experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
