"""N20D two-job source, history, no-log, and graph comparison."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from . import n20_experiment as n20
from . import n20a_experiment as n20a
from .n05_program import _pipeline_payload
from .n05_runner import create_bytes_exclusive, verify_record


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-037")
SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-036")
TASK = Path("instructions_between_agent_types/developer/current/N20D_two_job_history_no_log_run.email.md")
TASK_SHA256 = "sha256:3db98306300ad0a77f5815b94ebf0161a2e74300a31783d6073093c7fe929572"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N20D_two_job_history_no_log_authorization.json")
AUTHORITY_SHA256 = "sha256:4b6f67fc3f527b8b023cb54bcd8363a1ac1c873145abbcc5f02a5dd034b05d71"
SOURCE_TREE_SHA256 = "sha256:7eb24a2b0a543f0b407dced36d1d4ab4a672836aaf7f60c3ecb7899c492cecf4"
SOURCE_FREEZE_SHA256 = "sha256:5ae960239dd89f2acdd77cb823bfb558b1d8d94cf9029839fde50f56424dc401"
SOURCE_FREEZE_FILE_SHA256 = "sha256:006ce5b91d57041eded896aea03ae5b9532f603ecb82db10dd7b3bcd3efbec04"
SOURCE_TERMINAL_SHA256 = "sha256:eae9e83acf332ee4da1ff9eb4313d8e3a871e7feaafdca28e92df2a234fd9225"
SOURCE_TERMINAL_FILE_SHA256 = "sha256:7daa6d6c8045bde6d1bc89242103d44d30b4e946a7d96e80685bc52107a4a9b2"
SOURCE_ANALYSIS_SHA256 = "sha256:284691d2143e4c51a3a17a863c6549b21e25ddd6faab9224025f35858d8c4ddd"
SOURCE_ANALYSIS_FILE_SHA256 = "sha256:0c3a97dcb5bcd84828487357470ea89565edec44752ec09c76158abfc00f63b0"

OPEN_PROMPT = n20a.OPEN_PROMPT
GUIDED_PROMPT = n20a.GUIDED_PROMPT
OPEN_FINAL_SCHEMA = n20a.OPEN_FINAL_SCHEMA
GUIDED_FINAL_SCHEMA = n20a.GUIDED_FINAL_SCHEMA
VOLUNTARY_SCHEMA = n20a.VOLUNTARY_SCHEMA
REQUIRED_SCHEMA = n20a.REQUIRED_SCHEMA

MODES = (
    "io_job2_open",
    "io_both_open",
    "current_open",
    "history_full_open",
    "etiq_empty_open",
    "compact_fixed_guided",
    "adaptive_voluntary_guided",
    "adaptive_required_one_guided",
)
OPEN_MODES = MODES[:5]
ADAPTIVE_MODES = MODES[-2:]
FAULTS = n20.FAULTS
INSTANCES = n20.INSTANCES
CLEAN_INSTANCE = n20.CLEAN_INSTANCE
FAULT_GROUP = n20.FAULT_GROUP
UPSTREAM = "job_upstream_demand_provenance"
DOWNSTREAM = "job_downstream_coverage_priority"
COMMON_KEYS = (
    "task",
    "behavioural_criteria",
    "pipeline_topology",
    "top_level_input",
    "final_output",
    "source_bundle",
)


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20D authority input changed: {relative}")
    source = repo_root / SOURCE_ATTEMPT
    if ce.sha256(ce._tree_hashes(source)) != SOURCE_TREE_SHA256:
        raise ValueError("Attempt 036 tree changed")
    fixed = (
        ("experiment-freeze.json", SOURCE_FREEZE_FILE_SHA256, "freeze_sha256", SOURCE_FREEZE_SHA256),
        ("terminal-state.json", SOURCE_TERMINAL_FILE_SHA256, "terminal_sha256", SOURCE_TERMINAL_SHA256),
        ("analysis/summary.json", SOURCE_ANALYSIS_FILE_SHA256, "analysis_sha256", SOURCE_ANALYSIS_SHA256),
    )
    for relative, file_hash, logical_key, logical_hash in fixed:
        path = source / relative
        record = ce._read_json(path)
        if ce.sha256(path.read_bytes()) != file_hash or ce._verified_self_hash(record, logical_key) != logical_hash:
            raise ValueError(f"Attempt 036 binding changed: {relative}")
    for relative, expected in ce.N15_PROTECTED_FILE_SHA256.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20D protected boundary changed: {relative}")
    return {
        "source_attempt_tree_sha256": SOURCE_TREE_SHA256,
        "source_freeze_sha256": SOURCE_FREEZE_SHA256,
        "source_terminal_sha256": SOURCE_TERMINAL_SHA256,
        "source_analysis_sha256": SOURCE_ANALYSIS_SHA256,
        "protected_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
    }


def _copy_exact(source: Path, target: Path) -> None:
    create_bytes_exclusive(target, source.read_bytes())


def _source_bundles(repo_root: Path, captures: Mapping[str, Mapping[str, Any]], instances: Mapping[str, Mapping[str, Any]], qualifications: Mapping[str, Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    clean_jobs, _ = ce._n16_clean_base(repo_root)
    clean_hashes = {job_id: ce.sha256(_pipeline_payload(pipeline)) for job_id, pipeline in clean_jobs.items()}
    if clean_hashes != n20.CLEAN_SOURCE_SHA256:
        raise ValueError("reconstructed clean source changed")
    bundles = {}
    for instance_id in INSTANCES:
        jobs = deepcopy(clean_jobs)
        if instance_id != CLEAN_INSTANCE:
            jobs, site = n20.mutate_upstream(clean_jobs, instance_id)
            qualification = qualifications[instance_id]
            frozen_site = instances[instance_id]["mutation"]
            for key in ("fault_id", "qualified_function_name", "source_path", "original_span", "original_snippet", "mutant_snippet", "mutation_sha256"):
                if site[key] != qualification[key] or site[key] != frozen_site[key]:
                    raise ValueError(f"reconstructed mutation binding changed: {instance_id}: {key}")
        observed = {job_id: ce.sha256(_pipeline_payload(pipeline)) for job_id, pipeline in jobs.items()}
        if observed != captures[instance_id]["source_sha256"] or observed != instances[instance_id]["source_sha256"]:
            raise ValueError(f"source bundle does not match frozen capture: {instance_id}")
        bundle = ce._n16_source_bundle(jobs)
        if [x["job_id"] for x in bundle] != [UPSTREAM, DOWNSTREAM] or any(not item["files"] for item in bundle):
            raise ValueError(f"source bundle order or contents changed: {instance_id}")
        bundles[instance_id] = bundle
    return bundles


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N20D is authorized only for Attempt 037")
    _verify_authority(repo_root)
    source = repo_root / SOURCE_ATTEMPT
    freeze = ce._read_json(source / "experiment-freeze.json")
    for directory in ("captures", "catalogues", "instances", "qualification/mutations"):
        for source_path in sorted((source / directory).glob("*.json")):
            _copy_exact(source_path, target / directory / source_path.name)
    _copy_exact(source / "qualification/mutation-summary.json", target / "qualification/mutation-summary.json")
    captures = {path.stem: ce._read_json(path) for path in sorted((target / "captures").glob("*.json"))}
    catalogues = {path.stem: ce._read_json(path) for path in sorted((target / "catalogues").glob("*.json"))}
    instances = {path.stem: ce._read_json(path) for path in sorted((target / "instances").glob("*.json"))}
    qualifications = {path.stem: ce._read_json(path) for path in sorted((target / "qualification/mutations").glob("*.json"))}
    if set(captures) != set(INSTANCES) or set(catalogues) != set(INSTANCES) or set(instances) != set(INSTANCES) or set(qualifications) != set(FAULTS):
        raise ValueError("N20D reused record set changed")
    for instance_id in INSTANCES:
        ce._verify_capture(captures[instance_id])
        ce.verify_catalogue(catalogues[instance_id])
        ce._verified_self_hash(instances[instance_id], "instance_sha256")
        if captures[instance_id]["capture_sha256"] != freeze["capture_hashes"][instance_id]:
            raise ValueError(f"reused capture hash changed: {instance_id}")
        if catalogues[instance_id]["catalogue_sha256"] != freeze["catalogue_hashes"][instance_id]:
            raise ValueError(f"reused catalogue hash changed: {instance_id}")
        if instances[instance_id]["instance_sha256"] != freeze["instance_hashes"][instance_id]:
            raise ValueError(f"reused instance hash changed: {instance_id}")
    for fault_id in FAULTS:
        if ce._verified_self_hash(qualifications[fault_id], "qualification_sha256") != freeze["mutation_qualification_hashes"][fault_id]:
            raise ValueError(f"reused qualification hash changed: {fault_id}")
    bundles = _source_bundles(repo_root, captures, instances, qualifications)
    for instance_id, bundle in bundles.items():
        ce._write_immutable(target / "source-bundles" / f"{instance_id}.json", {"source_bundle": bundle})
    return {"captures": captures, "catalogues": catalogues, "instances": instances, "qualifications": qualifications, "source_bundles": bundles}


def _common(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = n20._open_common(catalogue)
    return {
        "task": baseline["review_task"],
        "behavioural_criteria": deepcopy(baseline["behavioural_criteria"]),
        "pipeline_topology": [UPSTREAM, DOWNSTREAM],
        "top_level_input": deepcopy(catalogue["jobs"][UPSTREAM]["input"]),
        "final_output": deepcopy(catalogue["jobs"][DOWNSTREAM]["output"]),
        "source_bundle": deepcopy(source_bundle),
    }


def _job_record(catalogue: Mapping[str, Any], job_id: str, *, logs: bool) -> dict[str, Any]:
    record = {
        "job_id": job_id,
        "input": deepcopy(catalogue["jobs"][job_id]["input"]),
        "output": deepcopy(catalogue["jobs"][job_id]["output"]),
    }
    if logs:
        record["stdout"] = str(catalogue["jobs"][job_id]["stdout"])
        record["stderr"] = str(catalogue["jobs"][job_id]["stderr"])
    return record


def build_review_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError("unknown N20D mode")
    package: dict[str, Any] = {"schema_version": "n20d-review-package-1", **_common(catalogue, source_bundle)}
    if mode == "io_job2_open":
        package["job_execution_records"] = [_job_record(catalogue, DOWNSTREAM, logs=False)]
        return package
    if mode == "io_both_open":
        package["job_execution_records"] = [_job_record(catalogue, UPSTREAM, logs=False), _job_record(catalogue, DOWNSTREAM, logs=False)]
        return package
    package["job_execution_records"] = [_job_record(catalogue, DOWNSTREAM, logs=True)]
    if mode == "current_open":
        return package
    if mode == "history_full_open":
        history = _job_record(catalogue, UPSTREAM, logs=True)
        history["produced_handoffs"] = deepcopy(list(catalogue["handoffs"]))
        package["prior_task_records"] = [history]
        return package
    package["integrated_etiq_instructions"] = {
        "framing": "Use the supplied execution evidence when judging the run.",
        "semantic_boundaries_supplied": mode != "etiq_empty_open",
    }
    package["runtime_evidence"] = n20._empty_projection(catalogue) if mode == "etiq_empty_open" else n20._compact_projection(catalogue)
    if mode == "etiq_empty_open":
        return package
    package["boundary_guidance"] = n20._guided_declarations(catalogue)
    if mode in ADAPTIVE_MODES:
        package["available_operations"] = ["helper_expansion"]
        package["action_contract"] = {
            "permitted_actions": ["helper_expansion", "finalize"] if mode == "adaptive_voluntary_guided" else ["helper_expansion"],
            "first_action_must_expand_one_model_selected_child_group": mode == "adaptive_required_one_guided",
            "maximum_completed_expansions": 1,
            "finalize_after_completed_expansion": True,
        }
    return package


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    visible = ce.canonical_json(request).decode()
    forbidden = ("designation", "truth_job", "truth_function", "fault_id", "evidence_mode", "branch_id", "trial_id", "repetition", "seed", "qualification")
    if any(f'"{key}"' in visible for key in forbidden):
        raise ValueError("N20D rendered request leaks controller state")
    return request


def schedule() -> dict[str, Any]:
    packages = [
        {"instance_id": instance, "evidence_mode": mode, "branch_id": f"brn-{ce.sha256(['n20d', instance, mode])[7:23]}"}
        for instance in INSTANCES for mode in MODES
    ]
    by = {(x["instance_id"], x["evidence_mode"]): x for x in packages}
    reviews = []
    block = 0
    for repetition in range(1, 4):
        rotated_instances = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for instance in rotated_instances:
            rotation = block % len(MODES)
            for position, mode in enumerate(MODES[rotation:] + MODES[:rotation], 1):
                condition = by[(instance, mode)]
                reviews.append({
                    **condition,
                    "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n20d', condition['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                    "local_block": block + 1,
                    "mode_position": position,
                })
            block += 1
    if (len(packages), len(reviews), len({x["trial_id"] for x in reviews})) != (56, 168, 168):
        raise AssertionError("N20D schedule changed")
    return {"packages": packages, "review_trials": reviews, "repair_traces": []}


def _schema_for(mode: str, *, follow_up: bool = False) -> Path:
    if follow_up:
        return GUIDED_FINAL_SCHEMA
    if mode in OPEN_MODES:
        return OPEN_FINAL_SCHEMA
    if mode == "compact_fixed_guided":
        return GUIDED_FINAL_SCHEMA
    if mode == "adaptive_voluntary_guided":
        return VOLUNTARY_SCHEMA
    if mode == "adaptive_required_one_guided":
        return REQUIRED_SCHEMA
    raise ValueError("unknown N20D mode")


def _prompt_for(mode: str) -> Path:
    return OPEN_PROMPT if mode in OPEN_MODES else GUIDED_PROMPT


def _contains_key(value: Any, keys: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(str(key) in keys or _contains_key(child, keys) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_key(child, keys) for child in value)
    return False


def qualify_packages(repo_root: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(records), len(design["review_trials"]), len(design["repair_traces"])) != (56, 168, 0):
        raise ValueError("N20D package or schedule count changed")
    by = {(x["controller_condition"]["instance_id"], x["controller_condition"]["evidence_mode"]): x["reviewer_package"] for x in records}
    checks = 0
    for instance_id in INSTANCES:
        packages = {mode: by[(instance_id, mode)] for mode in MODES}
        expected_bundle = prepared["source_bundles"][instance_id]
        if any(package["source_bundle"] != expected_bundle for package in packages.values()):
            raise ValueError(f"N20D source bundle differs across arms: {instance_id}")
        if len({ce.canonical_json({key: package[key] for key in COMMON_KEYS}) for package in packages.values()}) != 1:
            raise ValueError(f"N20D common evidence differs across arms: {instance_id}")
        capture = prepared["captures"][instance_id]
        for job in expected_bundle:
            if not job["files"] or any(not isinstance(item["content"], str) or not item["content"] for item in job["files"]):
                raise ValueError("N20D source was truncated")
        no_log = (packages["io_job2_open"], packages["io_both_open"])
        for package in no_log:
            if _contains_key(package, {"stdout", "stderr", "prior_task_records", "boundary_guidance", "runtime_evidence", "integrated_etiq_instructions", "available_operations", "action_contract"}):
                raise ValueError("N20D no-log package contains prohibited treatment material")
        if [x["job_id"] for x in packages["io_job2_open"]["job_execution_records"]] != [DOWNSTREAM]:
            raise ValueError("I/O Job 2 record changed")
        if [x["job_id"] for x in packages["io_both_open"]["job_execution_records"]] != [UPSTREAM, DOWNSTREAM]:
            raise ValueError("I/O Both records changed")
        current = packages["current_open"]
        history = packages["history_full_open"]
        empty = packages["etiq_empty_open"]
        fixed = packages["compact_fixed_guided"]
        voluntary = packages["adaptive_voluntary_guided"]
        required = packages["adaptive_required_one_guided"]
        if "prior_task_records" in current or current["job_execution_records"] != [_job_record(prepared["catalogues"][instance_id], DOWNSTREAM, logs=True)]:
            raise ValueError("N20D Current evidence changed")
        expected_history = _job_record(prepared["catalogues"][instance_id], UPSTREAM, logs=True)
        expected_history["produced_handoffs"] = deepcopy(capture["handoffs"])
        if history.get("prior_task_records") != [expected_history] or "source_bundle" in expected_history:
            raise ValueError("N20D History record is not canonical")
        for mode in OPEN_MODES:
            package = packages[mode]
            if "boundary_guidance" in package or _schema_for(mode) != OPEN_FINAL_SCHEMA:
                raise ValueError("N20D open mode exposes boundary guidance")
        if any(key in current for key in ("runtime_evidence", "integrated_etiq_instructions", "available_operations", "action_contract")):
            raise ValueError("N20D Current exposes graph framing")
        if "boundary_guidance" in empty or any(empty["runtime_evidence"].get(key) for key in ("anchors", "nodes", "relationships", "handoffs", "collapsed_child_groups")):
            raise ValueError("N20D Empty contains boundary or graph evidence")
        for guided in (fixed, voluntary, required):
            if len(guided["boundary_guidance"]["semantic_declarations"]) != 6 or len(guided["runtime_evidence"]["anchors"]) != 6:
                raise ValueError("N20D guided package lacks six declarations and anchors")
        equal_keys = (*COMMON_KEYS, "job_execution_records", "integrated_etiq_instructions", "runtime_evidence", "boundary_guidance")
        if len({ce.canonical_json({key: package[key] for key in equal_keys}) for package in (fixed, voluntary, required)}) != 1:
            raise ValueError("N20D Fixed and Adaptive initial evidence differs")
        if any(key in fixed for key in ("available_operations", "action_contract")):
            raise ValueError("N20D Fixed exposes an operation")
        if voluntary.get("available_operations") != ["helper_expansion"] or required.get("available_operations") != ["helper_expansion"]:
            raise ValueError("N20D Adaptive routing changed")
        for package in packages.values():
            render_request(package)
        checks += 16
    if ce._read_json(repo_root / REQUIRED_SCHEMA)["properties"]["next_action"]["properties"]["action"].get("const") != "helper_expansion":
        raise ValueError("N20D Required-One schema routing changed")
    return {
        "status": "passed",
        "model_calls": 0,
        "fault_count": 6,
        "clean_control_count": 1,
        "capture_count": 7,
        "catalogue_count": 7,
        "source_bundle_count": 7,
        "package_count": 56,
        "review_count": 168,
        "required_one_follow_up_count": 21,
        "provider_call_minimum": 189,
        "provider_call_maximum": 210,
        "repair_count": 0,
        "comparison_count": checks,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    records = []
    for condition in design["packages"]:
        instance_id = str(condition["instance_id"])
        package = build_review_package(prepared["catalogues"][instance_id], prepared["source_bundles"][instance_id], str(condition["evidence_mode"]))
        record = {
            "schema_version": "n20d-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "source_capture_sha256": prepared["catalogues"][instance_id]["source_capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance_id]["catalogue_sha256"],
            "source_bundle_file_sha256": ce.sha256((target / "source-bundles" / f"{instance_id}.json").read_bytes()),
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        records.append(record)
    qualification = qualify_packages(repo_root, records, prepared, design)
    return {**prepared, "packages": records, "schedule": design, "qualification": qualification}


def _load_frozen(attempt_root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    catalogues = {path.stem: ce._read_json(path) for path in sorted((attempt_root / "catalogues").glob("*.json"))}
    packages = {}
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        package = ce._read_json(attempt_root / manifest["reviewer_package_path"])
        if ce.sha256(package) != manifest["reviewer_package_sha256"]:
            raise ValueError("N20D reviewer package hash mismatch")
        record = {**manifest, "reviewer_package": package}
        unsigned = deepcopy(record)
        observed = unsigned.pop("package_sha256")
        unsigned.pop("reviewer_package_path")
        unsigned.pop("reviewer_package_sha256")
        if ce.sha256(unsigned) != observed:
            raise ValueError("N20D package record hash mismatch")
        packages[str(manifest["controller_condition"]["branch_id"])] = record
        records.append(record)
    return catalogues, packages, records


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n20d_experiment.py"),
        Path("src/use_case_icp/n20a_experiment.py"),
        Path("src/use_case_icp/n20_experiment.py"),
        Path("tests/test_n20d_experiment.py"),
        OPEN_PROMPT,
        GUIDED_PROMPT,
        OPEN_FINAL_SCHEMA,
        GUIDED_FINAL_SCHEMA,
        VOLUNTARY_SCHEMA,
        REQUIRED_SCHEMA,
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if (target / "experiment-freeze.json").exists():
        raise ValueError("Attempt 037 is already frozen")
    if any((target / name).exists() for name in ("packages", "controller-manifests", "reviews")):
        raise ValueError("Attempt 037 contains pre-freeze scientific material")
    source_tree = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    built = build_attempt(repo_root, target)
    for record in built["packages"]:
        branch = record["controller_condition"]["branch_id"]
        ce._write_immutable(target / "packages" / branch / "reviewer-package.json", record["reviewer_package"])
        manifest = {key: deepcopy(value) for key, value in record.items() if key != "reviewer_package"}
        manifest.update({"reviewer_package_path": f"packages/{branch}/reviewer-package.json", "reviewer_package_sha256": ce.sha256(record["reviewer_package"])})
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
    ce._write_immutable(target / "review-design.json", {"review_trials": built["schedule"]["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"repair_traces": []})
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != source_tree:
        raise RuntimeError("Attempt 036 changed during N20D freeze")
    freeze = {
        "schema_version": "n20d-two-job-history-freeze-1",
        "status": "frozen_before_first_experimental_review",
        "attempt": "attempt-037",
        "source_attempt": "attempt-036",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority_bindings": _verify_authority(repo_root),
        "protected_boundaries": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "source_attempt_tree_sha256": source_tree,
        "capture_hashes": {key: value["capture_sha256"] for key, value in built["captures"].items()},
        "catalogue_hashes": {key: value["catalogue_sha256"] for key, value in built["catalogues"].items()},
        "instance_hashes": {key: value["instance_sha256"] for key, value in built["instances"].items()},
        "source_bundle_file_hashes": {key: ce.sha256((target / "source-bundles" / f"{key}.json").read_bytes()) for key in INSTANCES},
        "source_bundle_payload_hashes": {key: ce.sha256(value) for key, value in built["source_bundles"].items()},
        "package_hashes": sorted(x["package_sha256"] for x in built["packages"]),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "review_design_sha256": ce.sha256(built["schedule"]["review_trials"]),
        "repair_design_sha256": ce.sha256([]),
        "expected_counts": {"faults": 6, "controls": 1, "captures": 7, "catalogues": 7, "source_bundles": 7, "packages": 56, "reviews": 168, "required_one_follow_ups": 21, "provider_calls_min": 189, "provider_calls_max": 210, "repairs": 0},
        "qualification": built["qualification"],
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path = target / "experiment-freeze.json"
    ce._write_immutable(path, freeze)
    return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _verify_authority(repo_root)
    freeze = ce._read_json(target / "experiment-freeze.json")
    observed = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20D frozen code changed: {relative}")
    for relative, expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20D protected boundary changed: {relative}")
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != freeze["source_attempt_tree_sha256"]:
        raise ValueError("Attempt 036 changed after N20D freeze")
    prepared = prepare_attempt(repo_root, target)
    for instance_id, expected in freeze["source_bundle_file_hashes"].items():
        if ce.sha256((target / "source-bundles" / f"{instance_id}.json").read_bytes()) != expected:
            raise ValueError(f"N20D source bundle file changed: {instance_id}")
    catalogues, _, records = _load_frozen(target)
    if catalogues.keys() != prepared["catalogues"].keys():
        raise ValueError("N20D frozen catalogue set changed")
    design = {"packages": [deepcopy(x["controller_condition"]) for x in records], "review_trials": ce._read_json(target / "review-design.json")["review_trials"], "repair_traces": ce._read_json(target / "repair-design.json")["repair_traces"]}
    qualification = qualify_packages(repo_root, records, prepared, design)
    if sorted(x["package_sha256"] for x in records) != freeze["package_hashes"] or ce.sha256(design["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("N20D frozen package or schedule changed")
    return {"status": "verified", "freeze_sha256": observed, "qualification": qualification, "capture_count": 7, "catalogue_count": 7, "source_bundle_count": 7, "package_count": 56, "review_count": 168, "repair_count": 0}


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path = attempt_root / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(ce._read_json(path), "consumption_sha256")
        return path
    if list((attempt_root / "reviews").glob("*.json")):
        raise ValueError("N20D review exists before live consumption")
    verified = verify_frozen_attempt(repo_root, attempt_root)
    record = {
        "schema_version": "n20d-live-consumption-1",
        "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "controller-manifests")),
        "review_design_file_sha256": ce.sha256((attempt_root / "review-design.json").read_bytes()),
        "protected_file_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 56, "reviews": 168, "required_one_follow_ups": 21, "provider_calls_min": 189, "provider_calls_max": 210, "repairs": 0},
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
    schema = ce._read_json(repo_root / schema_path)
    scientific = {key: deepcopy(response.get(key)) for key in schema["required"]}
    Draft202012Validator(schema).validate(scientific)
    boundary = scientific.get("suspect_boundary_id")
    allowed_boundaries = set(package.get("boundary_guidance", {}).get("assigned_boundary_ids", []))
    boundary_valid = boundary is None or str(boundary) in allowed_boundaries
    visible = ce.canonical_json(package).decode()
    invalid_refs = [str(value) for value in scientific["evidence_refs"] if str(value) not in visible]
    return {
        "valid": True,
        "receipt": scientific,
        "fault_detected": bool(scientific["fault_detected"]),
        "suspect_job": scientific["suspect_job"],
        "normalized_suspect_function": _normalized_function(scientific["suspect_function"]),
        "suspect_boundary_id": str(boundary) if boundary is not None and boundary_valid else None,
        "raw_suspect_boundary_id": boundary,
        "boundary_reference_valid": boundary_valid,
        "invalid_evidence_refs": invalid_refs,
    }


score_response = n20a.score_response


def _provider_review(repo_root: Path, attempt_root: Path, request: Mapping[str, Any], parent_id: str, mode: str, *, follow_up: bool = False) -> dict[str, Any]:
    return ce._provider_call(repo_root, attempt_root, kind="review", model_request=request, controller_parent_id=parent_id, review_prompt=_prompt_for(mode), review_schema=_schema_for(mode, follow_up=follow_up))


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count") if response.get(key) is not None}


def _expand_child(catalogue: Mapping[str, Any], package: Mapping[str, Any], boundary_id: str, child_group_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    internal = {
        "schema_version": "corrected-four-instance-package-2",
        "common_base": n20._open_common(catalogue),
        "allowed_evidence_refs": [str(x["handoff_id"]) for x in catalogue["handoffs"]],
        "prior_task_records": [],
        "integrated_etiq_instructions": deepcopy(package["integrated_etiq_instructions"]),
        "runtime_evidence": deepcopy(package["runtime_evidence"]),
        "boundary_guidance": deepcopy(package["boundary_guidance"]),
        "available_operations": deepcopy(package["available_operations"]),
        "action_contract": deepcopy(package["action_contract"]),
    }
    graph = internal["runtime_evidence"]
    internal["allowed_evidence_refs"] = sorted(set(internal["allowed_evidence_refs"]) | {str(x["boundary_id"]) for x in graph["anchors"]} | {str(x["anchor_id"]) for x in graph["anchors"]} | {str(x["child_group_id"]) for x in graph["collapsed_child_groups"]})
    updated_internal, event = n20.expand_child(catalogue, internal, boundary_id, child_group_id)
    updated = deepcopy(dict(package))
    updated["runtime_evidence"] = updated_internal["runtime_evidence"]
    return updated, event


def run_review_session(repo_root: Path, attempt_root: Path, catalogue: Mapping[str, Any], package: Mapping[str, Any], trial_id: str, mode: str) -> dict[str, Any]:
    initial = _provider_review(repo_root, attempt_root, render_request(package), trial_id, mode)
    pre = validate_response(repo_root, package, initial, _schema_for(mode))
    usage = [ce.actual_usage_record(initial, purpose="initial_review", phase="n20d_review")]
    calls = [_call_record(initial)]
    current = deepcopy(dict(package))
    final = pre
    event = None
    diagnostic = None
    if mode in ADAPTIVE_MODES:
        action = pre["receipt"]["next_action"]
        if action["action"] == "helper_expansion":
            try:
                current, event = _expand_child(catalogue, current, str(action["boundary_id"]), str(action["child_group_id"]))
            except ValueError as exc:
                diagnostic = {"status": "invalid_operation_reference", "error": str(exc), "request": deepcopy(action)}
                if mode == "adaptive_required_one_guided":
                    raise RuntimeError("N20D Required-One could not complete its model-selected expansion") from exc
            if event is not None:
                current.pop("available_operations", None)
                current.pop("action_contract", None)
                response = _provider_review(repo_root, attempt_root, render_request(current, operation_response=event), f"{trial_id}-follow-up-01", mode, follow_up=True)
                final = validate_response(repo_root, current, response, GUIDED_FINAL_SCHEMA)
                usage.append(ce.actual_usage_record(response, purpose="helper_expansion_follow_up", phase="n20d_review"))
                calls.append(_call_record(response))
        elif action["action"] == "finalize":
            diagnostic = {"status": "finalized_without_expansion", "ignored_operation_target": {"boundary_id": action["boundary_id"], "child_group_id": action["child_group_id"]}}
            if mode == "adaptive_required_one_guided":
                raise RuntimeError("N20D Required-One finalized before expansion")
        else:
            raise ValueError("unknown N20D Adaptive action")
    runtime = current.get("runtime_evidence", {})
    nodes = runtime.get("nodes", [])
    return {
        "pre_validation": pre,
        "final_validation": final,
        "operation_event": event,
        "operation_diagnostic": diagnostic,
        "completed_expansion_count": 1 if event else 0,
        "disclosed_node_count": len(nodes),
        "disclosed_relationship_count": len(runtime.get("relationships", [])),
        "duplicated_graph_source_node_count": sum(node.get("source") is not None for node in nodes),
        "values_visible": any(node.get("artifact_content") is not None or node.get("value_preview") is not None for node in nodes),
        "call_records": calls,
        "usage": ce.aggregate_actual_usage_records(usage),
    }


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [x for x in rows if x["designation"] == "upstream_fault"]
    controls = [x for x in rows if x["designation"] == "matched_clean_control"]
    calls = [call for row in rows for call in row["raw_calls"]]
    return {
        "reviews": len(rows),
        "provider_calls": len(calls),
        "fault_detection": {"numerator": sum(x["fault_detected"] for x in faults), "denominator": len(faults)},
        "correct_job_attribution": {"numerator": sum(x["correct_job_attribution"] for x in faults), "denominator": len(faults)},
        "exact_function_localisation": {"numerator": sum(x["exact_function_localisation"] for x in faults), "denominator": len(faults)},
        "control_false_positives": {"numerator": sum(x["false_positive"] for x in controls), "denominator": len(controls)},
        "expansion_sessions": sum(x["completed_expansion_count"] for x in rows),
        "disclosed_nodes": sum(x["disclosed_node_count"] for x in rows),
        "disclosed_relationships": sum(x["disclosed_relationship_count"] for x in rows),
        "input_tokens": sum(int(x.get("input_tokens") or 0) for x in calls),
        "cached_input_tokens": sum(int(x.get("cached_input_tokens") or 0) for x in calls),
        "output_tokens": sum(int(x.get("output_tokens") or 0) for x in calls),
    }


def _rate(summary: Mapping[str, Any], key: str) -> float:
    value = summary[key]
    return value["numerator"] / value["denominator"] if value["denominator"] else 0.0


def write_analysis(repo_root: Path, attempt_root: Path, reviews: Mapping[tuple[str, int], Mapping[str, Any]]) -> Path:
    rows = []
    raw_calls = []
    for record in reviews.values():
        trial = record["controller_trial"]
        calls = []
        for index, call in enumerate(record["usage"].get("calls", []), 1):
            tagged = {"trial_id": trial["trial_id"], "call_index": index, **deepcopy(call)}
            calls.append(tagged)
            raw_calls.append(tagged)
        rows.append({
            **deepcopy(trial),
            "designation": record["designation"],
            "fault_group": record["fault_group"],
            "truth_function": record["truth_function"],
            "fault_detected": record["fault_detected"],
            "false_positive": record["false_positive"],
            "correct_job_attribution": record["correct_job_attribution"],
            "exact_function_localisation": record["exact_function_localisation"],
            "pre_fault_detected": record["pre_fault_detected"],
            "pre_suspect_job": record["pre_suspect_job"],
            "pre_suspect_function": record["pre_suspect_function"],
            "suspect_job": record["suspect_job"],
            "suspect_function": record["suspect_function"],
            "suspect_boundary_id": record["suspect_boundary_id"],
            "completed_expansion_count": record["completed_expansion_count"],
            "selected_expansion": deepcopy(record["selected_expansion"]),
            "disclosed_node_count": record["disclosed_node_count"],
            "disclosed_relationship_count": record["disclosed_relationship_count"],
            "duplicated_graph_source_node_count": record["duplicated_graph_source_node_count"],
            "diagnosis_changed_after_expansion": record["pre_suspect_job"] != record["suspect_job"] or record["pre_suspect_function"] != record["suspect_function"],
            "raw_calls": calls,
        })
    by_mode = {mode: _summary([x for x in rows if x["evidence_mode"] == mode]) for mode in MODES}
    by_fault = {fault: {mode: _summary([x for x in rows if x["instance_id"] == fault and x["evidence_mode"] == mode]) for mode in MODES} for fault in INSTANCES}
    pairs = (
        ("history_vs_current", "current_open", "history_full_open"),
        ("io_both_vs_io_job2", "io_job2_open", "io_both_open"),
        ("current_vs_io_job2", "io_job2_open", "current_open"),
        ("empty_vs_current", "current_open", "etiq_empty_open"),
        ("fixed_vs_current", "current_open", "compact_fixed_guided"),
        ("voluntary_vs_fixed", "compact_fixed_guided", "adaptive_voluntary_guided"),
        ("required_vs_fixed", "compact_fixed_guided", "adaptive_required_one_guided"),
    )
    contrasts = []
    for name, left, right in pairs:
        contrasts.append({"name": name, "left": left, "right": right, **{f"{key}_rate_difference_right_minus_left": _rate(by_mode[right], key) - _rate(by_mode[left], key) for key in ("fault_detection", "correct_job_attribution", "exact_function_localisation", "control_false_positives")}})
    source_analysis = ce._read_json(repo_root / SOURCE_ATTEMPT / "analysis/summary.json")
    shared = n20a.MODES
    descriptive = {}
    for instance_id in INSTANCES:
        descriptive[instance_id] = {}
        for mode in shared:
            present = by_fault[instance_id][mode]
            absent = source_analysis["fault_mode_summaries"][instance_id][mode]
            descriptive[instance_id][mode] = {
                key: {"attempt_037": deepcopy(present[key]), "attempt_036": deepcopy(absent[key]), "rate_difference_037_minus_036": _rate(present, key) - _rate(absent, key)}
                for key in ("fault_detection", "correct_job_attribution", "exact_function_localisation", "control_false_positives")
            }
    analysis = {
        "schema_version": "n20d-two-job-history-analysis-1",
        "source_contract": "Complete two-job source was constant across all arms and was not the History treatment.",
        "history_limit": "Job 2 input already contains Job 1's handed-off output, so incremental History evidence may be mainly Job 1 logs and chronology.",
        "claim_boundary": "Guided-versus-open estimates the combined boundary-plus-graph treatment.",
        "review_count": len(rows),
        "repair_trace_count": 0,
        "mode_summaries": by_mode,
        "fault_mode_summaries": by_fault,
        "prespecified_contrasts": contrasts,
        "attempt_036_descriptive_comparison": descriptive,
        "adaptive_pre_post": [deepcopy(x) for x in rows if x["evidence_mode"] in ADAPTIVE_MODES],
        "voluntary_expansion_uptake": {"numerator": sum(x["completed_expansion_count"] for x in rows if x["evidence_mode"] == "adaptive_voluntary_guided"), "denominator": sum(x["evidence_mode"] == "adaptive_voluntary_guided" for x in rows)},
        "required_one_completion": {"numerator": sum(x["completed_expansion_count"] for x in rows if x["evidence_mode"] == "adaptive_required_one_guided"), "denominator": sum(x["evidence_mode"] == "adaptive_required_one_guided" for x in rows)},
        "rows": sorted(rows, key=lambda x: x["schedule_position"]),
        "raw_per_call_tokens": raw_calls,
        "actual_usage": ce.aggregate_actual_usage_records(raw_calls),
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    path = attempt_root / "analysis/summary.json"
    ce._write_immutable(path, analysis)
    return path


def _write_report(repo_root: Path, attempt_root: Path) -> Path:
    analysis = ce._read_json(attempt_root / "analysis/summary.json")
    replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    lines = [
        "# Attempt 037 — two-job source, history, no-log, and graph comparison",
        "",
        f"Completed 168 reviews, {replay['observed_counts']['logical_provider_calls']} logical provider calls, and zero repairs.",
        "",
        "Complete two-job source was constant across all arms and was not History. With two jobs, Job 2 input already contains Job 1's handed-off output, so incremental History evidence may be mainly Job 1 logs and chronology. Guided-versus-open estimates the combined boundary-plus-graph treatment.",
        "",
        "## Overall results",
        "",
        "| Mode | Detection | Correct Job 1 | Exact function | Control FP | Expansions | Calls | Input | Cached | Output |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        x = analysis["mode_summaries"][mode]
        lines.append(f"| {mode} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']} | {x['expansion_sessions']} | {x['provider_calls']} | {x['input_tokens']} | {x['cached_input_tokens']} | {x['output_tokens']} |")
    lines += ["", "## Results by fault", "", "| Fault | Mode | Detected | Job 1 | Exact function | Calls | Input | Output |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for fault in INSTANCES:
        for mode in MODES:
            x = analysis["fault_mode_summaries"][fault][mode]
            lines.append(f"| {fault} | {mode} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['provider_calls']} | {x['input_tokens']} | {x['output_tokens']} |")
    lines += ["", "## Adaptive pre/post answers", "", "| Trial | Mode | Pre job/function | Final job/function | Selected child | Nodes | Relationships |", "|---|---|---|---|---|---:|---:|"]
    for row in analysis["adaptive_pre_post"]:
        selected = row["selected_expansion"] or {}
        child = f"{selected.get('boundary_id', 'none')}:{selected.get('child_group_id', 'none')}"
        lines.append(f"| {row['trial_id']} | {row['evidence_mode']} | {row['pre_suspect_job'] or 'none'}/{row['pre_suspect_function'] or 'none'} | {row['suspect_job'] or 'none'}/{row['suspect_function'] or 'none'} | {child} | {row['disclosed_node_count']} | {row['disclosed_relationship_count']} |")
    lines += ["", "## All 168 trial rows", "", "| Pos | Trial | Instance | Mode | Rep | Detected/FP | Job | Function | Exact | Expansion | Calls | Input | Cached | Output |", "|---:|---|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|"]
    for row in analysis["rows"]:
        calls = row["raw_calls"]
        outcome = "detected" if row["fault_detected"] else "FP" if row["false_positive"] else "clean/miss"
        lines.append(f"| {row['schedule_position']} | {row['trial_id']} | {row['instance_id']} | {row['evidence_mode']} | {row['repetition']} | {outcome} | {row['suspect_job'] or 'none'} | {row['suspect_function'] or 'none'} | {row['exact_function_localisation']} | {row['completed_expansion_count']} | {len(calls)} | {sum(int(x.get('input_tokens') or 0) for x in calls)} | {sum(int(x.get('cached_input_tokens') or 0) for x in calls)} | {sum(int(x.get('output_tokens') or 0) for x in calls)} |")
    lines += ["", "Attempt 036 remains a separate source-absent descriptive comparison; its repetitions are not paired deterministic outcomes and are not pooled with Attempt 037.", ""]
    path = repo_root / "docs/workshops/n20d-attempt-037-two-job-history-no-log-complete-findings.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_bytes_exclusive(path, "\n".join(lines).encode())
    return path


def _write_handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze = ce._read_json(attempt_root / "experiment-freeze.json")
    analysis = ce._read_json(attempt_root / "analysis/summary.json")
    replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    terminal = ce._read_json(attempt_root / "terminal-state.json")
    report = repo_root / "docs/workshops/n20d-attempt-037-two-job-history-no-log-complete-findings.md"
    artifacts = {"freeze": attempt_root / "experiment-freeze.json", "source_bundles": attempt_root / "source-bundles", "packages": attempt_root / "packages", "reviews": attempt_root / "reviews", "analysis": attempt_root / "analysis/summary.json", "replay": attempt_root / "replay/reconciliation.json", "terminal": attempt_root / "terminal-state.json", "report": report}
    hashes = {name: ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name, path in artifacts.items()}
    lines = ["To: Overseer", "From: Developer", "Subject: N20D Attempt 037 two-job History/no-log results", "", f"Status: {terminal['status']}", f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)", f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`", "", "Counts", "- Faults: 6; clean controls: 1", "- Source bundles: 7; packages: 56; reviews: 168; repairs: 0", f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}", f"- Required-One completion: {analysis['required_one_completion']['numerator']}/{analysis['required_one_completion']['denominator']}", f"- Voluntary uptake: {analysis['voluntary_expansion_uptake']['numerator']}/{analysis['voluntary_expansion_uptake']['denominator']}", "", "Mode results", ""]
    for mode in MODES:
        x = analysis["mode_summaries"][mode]
        lines.append(f"- {mode}: detected {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']}; Job 1 {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']}; exact function {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']}; control FP {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']}; calls {x['provider_calls']}; input/output {x['input_tokens']}/{x['output_tokens']}.")
    lines += ["", "Exact artifact hashes", ""] + [f"- `{artifacts[name].relative_to(repo_root)}`: `{digest}`" for name, digest in hashes.items()] + ["", "Attempt 036 remained unchanged. No mutation, pipeline, capture, catalogue, prior provider response, or call ID was regenerated or reused. Complete source was constant across all arms and was not History. Protected execution/security and graph-operation code was unchanged.", ""]
    path = repo_root / "instructions_between_agent_types/developer/handoffs/N20D_attempt_037_results_to_overseer.email.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_bytes_exclusive(path, "\n".join(lines).encode())
    return path


def execute_lifecycle(repo_root: Path, attempt_root: Path) -> Path:
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    verified = verify_frozen_attempt(repo_root, attempt_root)
    create_live_consumption(repo_root, attempt_root)
    catalogues, packages, records = _load_frozen(attempt_root)
    trials = ce._read_json(attempt_root / "review-design.json")["review_trials"]
    instances = {key: ce._read_json(attempt_root / "instances" / f"{key}.json") for key in INSTANCES}
    reviews: dict[tuple[str, int], Mapping[str, Any]] = {}
    for trial in trials:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = ce._read_json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("invalid N20D partial review")
        else:
            package_record = packages[str(trial["branch_id"])]
            package = package_record["reviewer_package"]
            mode = str(trial["evidence_mode"])
            session = run_review_session(repo_root, attempt_root, catalogues[str(trial["instance_id"])], package, str(trial["trial_id"]), mode)
            final, pre = session["final_validation"], session["pre_validation"]
            outcome = score_response(instances[str(trial["instance_id"])], final)
            event = session["operation_event"]
            record = {
                "schema_version": "n20d-review-record-1",
                "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "receipt": deepcopy(final["receipt"]),
                "pre_fault_detected": pre["fault_detected"],
                "pre_suspect_job": pre["suspect_job"],
                "pre_suspect_function": pre["normalized_suspect_function"],
                "suspect_job": final["suspect_job"],
                "suspect_function": final["normalized_suspect_function"],
                "suspect_boundary_id": final["suspect_boundary_id"],
                "raw_suspect_boundary_id": final["raw_suspect_boundary_id"],
                "boundary_reference_valid": final["boundary_reference_valid"],
                "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]),
                **outcome,
                "fault_group": instances[str(trial["instance_id"])]["fault_group"],
                "completed_expansion_count": session["completed_expansion_count"],
                "selected_expansion": ({key: deepcopy(event.get(key)) for key in ("resolved_job_id", "boundary_id", "child_group_id", "nodes_added", "relationships_added")} if event else None),
                "operation_diagnostic": deepcopy(session["operation_diagnostic"]),
                "disclosed_node_count": session["disclosed_node_count"],
                "disclosed_relationship_count": session["disclosed_relationship_count"],
                "duplicated_graph_source_node_count": session["duplicated_graph_source_node_count"],
                "values_visible": session["values_visible"],
                "call_records": session["call_records"],
                "usage": session["usage"],
                "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews[(str(trial["branch_id"]), int(trial["repetition"]))] = record
    required = [x for x in reviews.values() if x["controller_trial"]["evidence_mode"] == "adaptive_required_one_guided"]
    if len(reviews) != 168 or len(required) != 21 or any(x["completed_expansion_count"] != 1 for x in required):
        raise RuntimeError("N20D review or Required-One invariant failed")
    call_ids = [str(call_id) for record in reviews.values() for call in record["call_records"] for call_id in call.get("call_ids", [])]
    logical_calls = sum(len(x["call_records"]) for x in reviews.values())
    if not 189 <= logical_calls <= 210 or len(call_ids) != len(set(call_ids)):
        raise ValueError("N20D call count or lineage changed")
    for call_id in call_ids:
        verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = ce._read_json(write_analysis(repo_root, attempt_root, reviews))
    freeze = ce._read_json(attempt_root / "experiment-freeze.json")
    replay = {
        "schema_version": "n20d-replay-1",
        "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(x["review_sha256"] for x in reviews.values()),
        "observed_counts": {"faults": 6, "controls": 1, "captures": 7, "catalogues": 7, "source_bundles": 7, "packages": len(records), "reviews": len(reviews), "repairs": 0, "logical_provider_calls": logical_calls, "provider_attempt_call_ids": len(call_ids), "completed_helper_expansions": sum(x["completed_expansion_count"] for x in reviews.values()), "disclosed_nodes": sum(x["disclosed_node_count"] for x in reviews.values()), "disclosed_relationships": sum(x["disclosed_relationship_count"] for x in reviews.values())},
        "all_record_hashes_recomputed": True,
        "duplicate_logical_calls": False,
        "required_one_sessions_complete": True,
        "source_bundle_files_unchanged": all(ce.sha256((attempt_root / "source-bundles" / f"{key}.json").read_bytes()) == value for key, value in freeze["source_bundle_file_hashes"].items()),
        "source_attempt_unchanged": ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) == freeze["source_attempt_tree_sha256"],
    }
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(attempt_root / "replay/reconciliation.json", replay)
    terminal = {"schema_version": "n20d-terminal-1", "status": "completed_experiment_and_analysis", "fault_count": 6, "control_count": 1, "package_count": 56, "review_count": 168, "repair_trace_count": 0, "analysis_sha256": analysis["analysis_sha256"], "replay_sha256": replay["replay_sha256"]}
    terminal["terminal_sha256"] = ce.sha256(terminal)
    path = attempt_root / "terminal-state.json"
    ce._write_immutable(path, terminal)
    _write_report(repo_root, attempt_root)
    _write_handoff(repo_root, attempt_root)
    return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        terminal = {"schema_version": "n20d-terminal-1", "status": "terminal_incomplete", "failure_stage": "n20d_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}", "completed_review_records": len(list((target / "reviews").glob("*.json"))), "completed_repair_records": 0}
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
            print(json.dumps({"qualification": built["qualification"], "counts": {"captures": len(built["captures"]), "catalogues": len(built["catalogues"]), "source_bundles": len(built["source_bundles"]), "packages": len(built["packages"]), "reviews": len(built["schedule"]["review_trials"]), "repairs": 0}}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, attempt))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, attempt), indent=2))
        else:
            path = run_lifecycle(repo, attempt)
            print(path)
            return 0 if ce._read_json(path).get("status") == "completed_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N20D experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
