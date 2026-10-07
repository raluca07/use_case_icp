"""N20A corrected boundary-free upstream-fault experiment."""

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
from .n05_runner import create_bytes_exclusive, verify_record


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-036")
SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-034")
PRESERVED_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-035")
PRESERVED_ATTEMPT_TREE_SHA256 = "sha256:926775b238b10d3b22535d50b04b939f17db2812e3dc12d50ccb52fe275a3b4e"
TASK = Path("instructions_between_agent_types/developer/current/N20B_provider_schema_compatibility_and_run.email.md")
TASK_SHA256 = "sha256:6d0b1ce84ab759c2f885fb05577b0e6061f1783c4e96c071700653979437facd"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N20B_provider_schema_compatibility_authorization.json")
AUTHORITY_SHA256 = "sha256:e2e32e17f2344d0618e322fbcb57b74a581df7778f21637772c934234ebde9b5"
SOURCE_FREEZE_SHA256 = "sha256:4f2273b9aa185ada16754a9d54a69884a037482a751dc3d1a52c89ef82ba4869"
SOURCE_FREEZE_FILE_SHA256 = "sha256:f5e2c2dc928b804a8d1ce5fee3d153c2fda1dde19ed3e4ed84cbbf415b5bdfb4"
SOURCE_TERMINAL_SHA256 = "sha256:4077b295862d0fe24f9ee6a5810a7dde71ea6551be1ccaea1bec28d6ede36586"
SOURCE_TERMINAL_FILE_SHA256 = "sha256:5254e6e90da3cf176b21d9bf0a7ca1a29f195ad58f16a6a5365897a10fc939d5"

OPEN_PROMPT = Path("prompts/v2_2/n20a_open_review.md")
GUIDED_PROMPT = Path("prompts/v2_2/n20a_guided_review.md")
OPEN_FINAL_SCHEMA = Path("schemas/v2_2/n20a_open_final.schema.json")
GUIDED_FINAL_SCHEMA = Path("schemas/v2_2/n20a_guided_final.schema.json")
VOLUNTARY_SCHEMA = Path("schemas/v2_2/n20a_adaptive_voluntary.schema.json")
REQUIRED_SCHEMA = Path("schemas/v2_2/n20a_adaptive_required.schema.json")
MODES = n20.MODES
FAULTS = n20.FAULTS
INSTANCES = n20.INSTANCES
CLEAN_INSTANCE = n20.CLEAN_INSTANCE
FAULT_GROUP = n20.FAULT_GROUP


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20A authority input changed: {relative}")
    source = repo_root / SOURCE_ATTEMPT
    freeze_path = source / "experiment-freeze.json"
    freeze = ce._read_json(freeze_path)
    if ce.sha256(freeze_path.read_bytes()) != SOURCE_FREEZE_FILE_SHA256:
        raise ValueError("Attempt-034 freeze file changed")
    if ce._verified_self_hash(freeze, "freeze_sha256") != SOURCE_FREEZE_SHA256:
        raise ValueError("Attempt-034 logical freeze changed")
    terminal_path = source / "terminal/terminal-incomplete-4077b295862d0fe2.json"
    terminal = ce._read_json(terminal_path)
    if ce.sha256(terminal_path.read_bytes()) != SOURCE_TERMINAL_FILE_SHA256:
        raise ValueError("Attempt-034 terminal file changed")
    if ce._verified_self_hash(terminal, "terminal_sha256") != SOURCE_TERMINAL_SHA256:
        raise ValueError("Attempt-034 terminal identity changed")
    if ce.sha256(ce._tree_hashes(repo_root / PRESERVED_ATTEMPT)) != PRESERVED_ATTEMPT_TREE_SHA256:
        raise ValueError("Attempt-035 changed after its terminal-incomplete record")
    for relative, expected in ce.N15_PROTECTED_FILE_SHA256.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20A protected boundary changed: {relative}")
    return {
        "source_freeze_sha256": SOURCE_FREEZE_SHA256,
        "source_freeze_file_sha256": SOURCE_FREEZE_FILE_SHA256,
        "source_terminal_sha256": SOURCE_TERMINAL_SHA256,
        "source_terminal_file_sha256": SOURCE_TERMINAL_FILE_SHA256,
        "protected_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
    }


def _copy_exact(source: Path, target: Path) -> None:
    create_bytes_exclusive(target, source.read_bytes())


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N20B is authorized only for Attempt 036")
    _verify_authority(repo_root)
    source = repo_root / SOURCE_ATTEMPT
    freeze = ce._read_json(source / "experiment-freeze.json")
    for instance_id in INSTANCES:
        capture_source = source / "captures" / f"{instance_id}.json"
        catalogue_source = source / "catalogues" / f"{instance_id}.json"
        instance_source = source / "instances" / f"{instance_id}.json"
        capture = ce._read_json(capture_source)
        catalogue = ce._read_json(catalogue_source)
        instance = ce._read_json(instance_source)
        ce._verify_capture(capture)
        ce.verify_catalogue(catalogue)
        ce._verified_self_hash(instance, "instance_sha256")
        if capture["capture_sha256"] != freeze["capture_hashes"][instance_id]:
            raise ValueError(f"Attempt-034 capture binding changed: {instance_id}")
        if catalogue["catalogue_sha256"] != freeze["catalogue_hashes"][instance_id]:
            raise ValueError(f"Attempt-034 catalogue binding changed: {instance_id}")
        if instance["capture_sha256"] != capture["capture_sha256"] or instance["catalogue_sha256"] != catalogue["catalogue_sha256"]:
            raise ValueError(f"Attempt-034 instance binding changed: {instance_id}")
        _copy_exact(capture_source, target / "captures" / capture_source.name)
        _copy_exact(catalogue_source, target / "catalogues" / catalogue_source.name)
        _copy_exact(instance_source, target / "instances" / instance_source.name)
    for fault_id in FAULTS:
        source_path = source / "qualification/mutations" / f"{fault_id}.json"
        qualification = ce._read_json(source_path)
        if ce._verified_self_hash(qualification, "qualification_sha256") != freeze["mutation_qualification_hashes"][fault_id]:
            raise ValueError(f"Attempt-034 mutation qualification changed: {fault_id}")
        _copy_exact(source_path, target / "qualification/mutations" / source_path.name)
    summary_source = source / "qualification/mutation-summary.json"
    summary = ce._read_json(summary_source)
    ce._verified_self_hash(summary, "summary_sha256")
    if summary["qualification_hashes"] != freeze["mutation_qualification_hashes"]:
        raise ValueError("Attempt-034 mutation summary changed")
    _copy_exact(summary_source, target / "qualification/mutation-summary.json")
    captures = {path.stem: ce._read_json(path) for path in sorted((target / "captures").glob("*.json"))}
    catalogues = {path.stem: ce._read_json(path) for path in sorted((target / "catalogues").glob("*.json"))}
    instances = {path.stem: ce._read_json(path) for path in sorted((target / "instances").glob("*.json"))}
    return {"captures": captures, "catalogues": catalogues, "instances": instances, "reused_from_attempt_034": True}


def _empty_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    return n20._empty_projection(catalogue)


def _compact_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    return n20._compact_projection(catalogue)


def build_review_package(catalogue: Mapping[str, Any], mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError("unknown N20A mode")
    package: dict[str, Any] = {
        "schema_version": "corrected-four-instance-package-2",
        "common_base": n20._open_common(catalogue),
        "allowed_evidence_refs": [str(x["handoff_id"]) for x in catalogue["handoffs"]],
        "prior_task_records": [],
    }
    if mode == "current_open":
        return package
    package["integrated_etiq_instructions"] = {
        "framing": "Use the supplied execution evidence when judging the run.",
        "semantic_boundaries_supplied": mode != "etiq_empty_open",
    }
    package["runtime_evidence"] = _empty_projection(catalogue) if mode == "etiq_empty_open" else _compact_projection(catalogue)
    if mode == "etiq_empty_open":
        return package
    package["boundary_guidance"] = n20._guided_declarations(catalogue)
    graph = package["runtime_evidence"]
    package["allowed_evidence_refs"] = sorted(
        set(package["allowed_evidence_refs"])
        | {str(x["boundary_id"]) for x in graph["anchors"]}
        | {str(x["anchor_id"]) for x in graph["anchors"]}
        | {str(x["child_group_id"]) for x in graph["collapsed_child_groups"]}
    )
    if mode in {"adaptive_voluntary_guided", "adaptive_required_one_guided"}:
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
    forbidden = ("mutation", "oracle", "designation", "truth", "instance_id", "fault_id", "evidence_mode", "branch_id", "trial_id", "repetition", "seed", "source_bundle")
    visible = ce.canonical_json(request).decode()
    if any(f'"{key}"' in visible for key in forbidden):
        raise ValueError("N20A rendered request leaks controller state")
    return request


def schedule() -> dict[str, Any]:
    packages = [
        {"instance_id": instance, "evidence_mode": mode, "branch_id": f"brn-{ce.sha256(['n20a', instance, mode])[7:23]}"}
        for instance in INSTANCES for mode in MODES
    ]
    by = {(x["instance_id"], x["evidence_mode"]): x for x in packages}
    reviews = []
    block = 0
    for repetition in range(1, 4):
        instances = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for instance in instances:
            rotation = block % len(MODES)
            for position, mode in enumerate(MODES[rotation:] + MODES[:rotation], 1):
                condition = by[(instance, mode)]
                reviews.append({
                    **condition,
                    "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n20a', condition['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                    "local_block": block + 1,
                    "mode_position": position,
                })
            block += 1
    if len(packages) != 35 or len(reviews) != 105 or len({x["trial_id"] for x in reviews}) != 105:
        raise AssertionError("N20A schedule changed")
    return {"packages": packages, "review_trials": reviews, "repair_traces": []}


def _interface_text(repo_root: Path, package: Mapping[str, Any], prompt: Path, schema: Path) -> str:
    return "\n".join((
        (repo_root / prompt).read_text(encoding="utf-8"),
        ce.canonical_json(render_request(package)).decode(),
        ce.canonical_json(ce._read_json(repo_root / schema)).decode(),
    )).lower()


def qualify_packages(repo_root: Path, records: list[Mapping[str, Any]], catalogues: Mapping[str, Mapping[str, Any]], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(catalogues), len(records), len(design["review_trials"]), len(design["repair_traces"])) != (7, 35, 105, 0):
        raise ValueError("N20A package or schedule count changed")
    by = {(x["controller_condition"]["instance_id"], x["controller_condition"]["evidence_mode"]): x["reviewer_package"] for x in records}
    forbidden_open = ("boundary", "node", "child", "graph", "operation", "action", "helper", "expansion")
    checks = 0
    for instance in INSTANCES:
        pair = {mode: by[(instance, mode)] for mode in MODES}
        if len({ce.canonical_json(x["common_base"]) for x in pair.values()}) != 1:
            raise ValueError("N20A common runtime differs across arms")
        current, empty = pair["current_open"], pair["etiq_empty_open"]
        fixed, voluntary, required = pair["compact_fixed_guided"], pair["adaptive_voluntary_guided"], pair["adaptive_required_one_guided"]
        if any(word in _interface_text(repo_root, current, OPEN_PROMPT, OPEN_FINAL_SCHEMA) for word in forbidden_open):
            raise ValueError("Current Open model interface contains a prohibited concept")
        if any(key in current for key in ("runtime_evidence", "integrated_etiq_instructions", "boundary_guidance", "available_operations", "action_contract")):
            raise ValueError("Current Open contains treatment fields")
        if "boundary_guidance" in empty or "available_operations" in empty or "action_contract" in empty:
            raise ValueError("Etiq Empty is not boundary-free")
        if any(empty["runtime_evidence"].get(key) for key in ("anchors", "nodes", "relationships", "handoffs", "collapsed_child_groups")):
            raise ValueError("Etiq Empty contains execution evidence")
        for guided in (fixed, voluntary, required):
            if len(guided["boundary_guidance"]["semantic_declarations"]) != 6 or len(guided["runtime_evidence"]["anchors"]) != 6:
                raise ValueError("guided package lacks six declarations and anchors")
        if len({ce.canonical_json(x["boundary_guidance"]) for x in (fixed, voluntary, required)}) != 1:
            raise ValueError("Fixed and Adaptive guidance differs")
        if len({ce.canonical_json(x["runtime_evidence"]) for x in (fixed, voluntary, required)}) != 1:
            raise ValueError("Fixed and Adaptive initial graph differs")
        if any(key in fixed for key in ("available_operations", "action_contract")):
            raise ValueError("Fixed exposes an operation surface")
        if voluntary.get("available_operations") != ["helper_expansion"] or required.get("available_operations") != ["helper_expansion"]:
            raise ValueError("Adaptive expansion surface changed")
        checks += 10
    required_schema = ce._read_json(repo_root / REQUIRED_SCHEMA)
    if required_schema["properties"]["next_action"]["properties"]["action"].get("const") != "helper_expansion":
        raise ValueError("Required-One schema permits finalization before expansion")
    if "next_action" in ce._read_json(repo_root / GUIDED_FINAL_SCHEMA)["properties"]:
        raise ValueError("guided final schema exposes another operation")
    return {
        "status": "passed",
        "model_calls": 0,
        "fault_count": 6,
        "clean_control_count": 1,
        "capture_count": 7,
        "catalogue_count": 7,
        "package_count": 35,
        "review_count": 105,
        "required_one_follow_up_count": 21,
        "provider_call_minimum": 126,
        "provider_call_maximum": 147,
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
        catalogue = prepared["catalogues"][condition["instance_id"]]
        package = build_review_package(catalogue, condition["evidence_mode"])
        record = {
            "schema_version": "n20a-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "source_capture_sha256": catalogue["source_capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        records.append(record)
    qualification = qualify_packages(repo_root, records, prepared["catalogues"], design)
    return {**prepared, "packages": records, "schedule": design, "qualification": qualification}


def _load_frozen(attempt_root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    catalogues = {path.stem: ce._read_json(path) for path in sorted((attempt_root / "catalogues").glob("*.json"))}
    packages: dict[str, Any] = {}
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        package = ce._read_json(attempt_root / manifest["reviewer_package_path"])
        if ce.sha256(package) != manifest["reviewer_package_sha256"]:
            raise ValueError("N20A reviewer package hash mismatch")
        record = {**manifest, "reviewer_package": package}
        unsigned = deepcopy(record)
        observed = unsigned.pop("package_sha256")
        unsigned.pop("reviewer_package_path")
        unsigned.pop("reviewer_package_sha256")
        if ce.sha256(unsigned) != observed:
            raise ValueError("N20A package record hash mismatch")
        packages[str(manifest["controller_condition"]["branch_id"])] = record
        records.append(record)
    return catalogues, packages, records


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n20a_experiment.py"),
        Path("src/use_case_icp/n20_experiment.py"),
        Path("tests/test_n20a_experiment.py"),
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
        raise ValueError("Attempt 036 is already frozen")
    if any((target / name).exists() for name in ("packages", "controller-manifests", "reviews")):
        raise ValueError("Attempt 036 contains pre-freeze scientific material")
    source_tree = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    preserved_tree = ce.sha256(ce._tree_hashes(repo_root / PRESERVED_ATTEMPT))
    built = build_attempt(repo_root, target)
    for record in built["packages"]:
        branch = record["controller_condition"]["branch_id"]
        ce._write_immutable(target / "packages" / branch / "reviewer-package.json", record["reviewer_package"])
        manifest = {key: deepcopy(value) for key, value in record.items() if key != "reviewer_package"}
        manifest.update({
            "reviewer_package_path": f"packages/{branch}/reviewer-package.json",
            "reviewer_package_sha256": ce.sha256(record["reviewer_package"]),
        })
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
    ce._write_immutable(target / "review-design.json", {"review_trials": built["schedule"]["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"repair_traces": []})
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != source_tree:
        raise RuntimeError("Attempt 034 changed during N20A freeze")
    if ce.sha256(ce._tree_hashes(repo_root / PRESERVED_ATTEMPT)) != preserved_tree:
        raise RuntimeError("Attempt 035 changed during N20B freeze")
    freeze = {
        "schema_version": "n20a-boundary-free-freeze-1",
        "status": "frozen_before_first_experimental_review",
        "attempt": "attempt-036",
        "source_attempt": "attempt-034",
        "preserved_attempt": "attempt-035",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority_bindings": _verify_authority(repo_root),
        "protected_boundaries": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "source_attempt_tree_sha256": source_tree,
        "preserved_attempt_tree_sha256": preserved_tree,
        "capture_hashes": {key: value["capture_sha256"] for key, value in built["captures"].items()},
        "catalogue_hashes": {key: value["catalogue_sha256"] for key, value in built["catalogues"].items()},
        "instance_hashes": {key: value["instance_sha256"] for key, value in built["instances"].items()},
        "mutation_qualification_hashes": ce._read_json(target / "qualification/mutation-summary.json")["qualification_hashes"],
        "package_hashes": sorted(x["package_sha256"] for x in built["packages"]),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "common_runtime_hashes": {
            instance: ce.sha256(next(x for x in built["packages"] if x["controller_condition"]["instance_id"] == instance)["reviewer_package"]["common_base"])
            for instance in INSTANCES
        },
        "review_design_sha256": ce.sha256(built["schedule"]["review_trials"]),
        "repair_design_sha256": ce.sha256([]),
        "expected_counts": {"faults": 6, "controls": 1, "captures": 7, "catalogues": 7, "packages": 35, "reviews": 105, "required_one_follow_ups": 21, "provider_calls_max": 147, "repairs": 0},
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
            raise ValueError(f"N20A frozen code changed: {relative}")
    for relative, expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20A protected boundary changed: {relative}")
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != freeze["source_attempt_tree_sha256"]:
        raise ValueError("Attempt 034 changed after N20A freeze")
    if ce.sha256(ce._tree_hashes(repo_root / PRESERVED_ATTEMPT)) != freeze["preserved_attempt_tree_sha256"]:
        raise ValueError("Attempt 035 changed after N20B freeze")
    catalogues, _, records = _load_frozen(target)
    design = {"packages": [deepcopy(x["controller_condition"]) for x in records], "review_trials": ce._read_json(target / "review-design.json")["review_trials"], "repair_traces": ce._read_json(target / "repair-design.json")["repair_traces"]}
    qualification = qualify_packages(repo_root, records, catalogues, design)
    if sorted(x["package_sha256"] for x in records) != freeze["package_hashes"] or ce.sha256(design["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("N20A frozen package or schedule changed")
    return {"status": "verified", "freeze_sha256": observed, "qualification": qualification, "capture_count": 7, "catalogue_count": 7, "package_count": 35, "review_count": 105, "repair_count": 0}


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path = attempt_root / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(ce._read_json(path), "consumption_sha256")
        return path
    if list((attempt_root / "reviews").glob("*.json")):
        raise ValueError("N20A review exists before live consumption")
    verified = verify_frozen_attempt(repo_root, attempt_root)
    record = {
        "schema_version": "n20a-live-consumption-1",
        "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "controller-manifests")),
        "review_design_file_sha256": ce.sha256((attempt_root / "review-design.json").read_bytes()),
        "protected_file_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 35, "reviews": 105, "required_one_follow_ups": 21, "provider_calls_max": 147, "repairs": 0},
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _normalized_function(value: Any) -> str | None:
    if value is None:
        return None
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(value).strip().lower())
    return names[-1] if names else None


def _schema_for(mode: str, *, follow_up: bool = False) -> Path:
    if follow_up:
        return GUIDED_FINAL_SCHEMA
    if mode in {"current_open", "etiq_empty_open"}:
        return OPEN_FINAL_SCHEMA
    if mode == "compact_fixed_guided":
        return GUIDED_FINAL_SCHEMA
    if mode == "adaptive_voluntary_guided":
        return VOLUNTARY_SCHEMA
    if mode == "adaptive_required_one_guided":
        return REQUIRED_SCHEMA
    raise ValueError("unknown N20A mode")


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], schema_path: Path) -> dict[str, Any]:
    schema = ce._read_json(repo_root / schema_path)
    scientific = {key: deepcopy(response.get(key)) for key in schema["required"]}
    Draft202012Validator(schema).validate(scientific)
    boundary = scientific.get("suspect_boundary_id")
    allowed_boundaries = set(package.get("boundary_guidance", {}).get("assigned_boundary_ids", []))
    boundary_valid = boundary is None or str(boundary) in allowed_boundaries
    allowed_refs = set(map(str, package.get("allowed_evidence_refs", [])))
    invalid_refs = [str(value) for value in scientific["evidence_refs"] if str(value) not in allowed_refs]
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


def score_response(instance: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    truth = instance.get("truth_function")
    detected = bool(validation["fault_detected"])
    if truth is None:
        return {"designation": "matched_clean_control", "fault_detected": detected, "false_positive": detected, "correct_job_attribution": False, "exact_function_localisation": False, "truth_job": None, "truth_function": None}
    correct_job = detected and validation["suspect_job"] == "job_upstream_demand_provenance"
    return {
        "designation": "upstream_fault",
        "fault_detected": detected,
        "false_positive": False,
        "correct_job_attribution": correct_job,
        "exact_function_localisation": correct_job and validation["normalized_suspect_function"] == truth,
        "truth_job": "job_upstream_demand_provenance",
        "truth_function": truth,
    }


def _provider_review(repo_root: Path, attempt_root: Path, request: Mapping[str, Any], parent_id: str, mode: str, *, follow_up: bool = False) -> dict[str, Any]:
    prompt = OPEN_PROMPT if mode in {"current_open", "etiq_empty_open"} else GUIDED_PROMPT
    return ce._provider_call(repo_root, attempt_root, kind="review", model_request=request, controller_parent_id=parent_id, review_prompt=prompt, review_schema=_schema_for(mode, follow_up=follow_up))


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count") if response.get(key) is not None}


def run_review_session(repo_root: Path, attempt_root: Path, catalogue: Mapping[str, Any], package: Mapping[str, Any], trial_id: str, mode: str) -> dict[str, Any]:
    initial = _provider_review(repo_root, attempt_root, render_request(package), trial_id, mode)
    pre = validate_response(repo_root, package, initial, _schema_for(mode))
    usage = [ce.actual_usage_record(initial, purpose="initial_review", phase="n20a_review")]
    calls = [_call_record(initial)]
    current = deepcopy(dict(package))
    final = pre
    event = None
    diagnostic = None
    if mode in {"adaptive_voluntary_guided", "adaptive_required_one_guided"}:
        action = pre["receipt"]["next_action"]
        if action["action"] == "helper_expansion":
            try:
                current, event = n20.expand_child(catalogue, current, str(action["boundary_id"]), str(action["child_group_id"]))
            except ValueError as exc:
                diagnostic = {"status": "invalid_operation_reference", "error": str(exc), "request": deepcopy(action)}
                if mode == "adaptive_required_one_guided":
                    raise RuntimeError("N20A Required-One could not complete its model-selected expansion") from exc
            if event is not None:
                current.pop("available_operations", None)
                current.pop("action_contract", None)
                response = _provider_review(repo_root, attempt_root, render_request(current, operation_response=event), f"{trial_id}-follow-up-01", mode, follow_up=True)
                final = validate_response(repo_root, current, response, GUIDED_FINAL_SCHEMA)
                usage.append(ce.actual_usage_record(response, purpose="helper_expansion_follow_up", phase="n20a_review"))
                calls.append(_call_record(response))
        elif action["action"] == "finalize":
            diagnostic = {"status": "finalized_without_expansion", "ignored_operation_target": {"boundary_id": action["boundary_id"], "child_group_id": action["child_group_id"]}}
            if mode == "adaptive_required_one_guided":
                raise RuntimeError("N20A Required-One finalized before expansion")
        else:
            raise ValueError("unknown N20A adaptive action")
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
        "source_visible": any(node.get("source") is not None for node in nodes),
        "values_visible": any(node.get("artifact_content") is not None or node.get("value_preview") is not None for node in nodes),
        "call_records": calls,
        "usage": ce.aggregate_actual_usage_records(usage),
    }


def write_analysis(attempt_root: Path, reviews: Mapping[tuple[str, int], Mapping[str, Any]]) -> Path:
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
            "raw_suspect_boundary_id": record["raw_suspect_boundary_id"],
            "boundary_reference_valid": record["boundary_reference_valid"],
            "invalid_evidence_refs": deepcopy(record["invalid_evidence_refs"]),
            "completed_expansion_count": record["completed_expansion_count"],
            "selected_expansion": deepcopy(record["selected_expansion"]),
            "operation_diagnostic": deepcopy(record["operation_diagnostic"]),
            "disclosed_node_count": record["disclosed_node_count"],
            "disclosed_relationship_count": record["disclosed_relationship_count"],
            "source_visible": record["source_visible"],
            "values_visible": record["values_visible"],
            "diagnosis_changed_after_expansion": record["pre_suspect_job"] != record["suspect_job"] or record["pre_suspect_function"] != record["suspect_function"],
            "raw_calls": calls,
        })
    by_mode = {mode: n20._summary([x for x in rows if x["evidence_mode"] == mode]) for mode in MODES}
    by_fault = {fault: {mode: n20._summary([x for x in rows if x["instance_id"] == fault and x["evidence_mode"] == mode]) for mode in MODES} for fault in INSTANCES}
    by_group = {group: {mode: n20._summary([x for x in rows if x["fault_group"] == group and x["evidence_mode"] == mode]) for mode in MODES} for group in sorted(set(FAULT_GROUP.values()))}
    pairs = (("required_vs_current", "current_open", "adaptive_required_one_guided"), ("voluntary_vs_current", "current_open", "adaptive_voluntary_guided"), ("fixed_vs_current", "current_open", "compact_fixed_guided"), ("required_vs_fixed", "compact_fixed_guided", "adaptive_required_one_guided"), ("voluntary_vs_fixed", "compact_fixed_guided", "adaptive_voluntary_guided"), ("empty_vs_current", "current_open", "etiq_empty_open"))
    contrasts = []
    for name, left, right in pairs:
        contrasts.append({"name": name, "left": left, "right": right, **{f"{key}_rate_difference_right_minus_left": n20._rate(by_mode[right], key) - n20._rate(by_mode[left], key) for key in ("fault_detection", "correct_job_attribution", "exact_function_localisation", "control_false_positives")}})
    analysis = {
        "schema_version": "n20a-boundary-bundled-analysis-1",
        "scope_limitation": "Six prespecified mutants share one clean base pipeline; three repetitions are repeated model calls, not independent faults.",
        "claim_boundary": "Current-to-guided differences are the total effect of the integrated boundary-plus-graph treatment, not graph alone.",
        "review_count": len(rows),
        "repair_trace_count": 0,
        "mode_summaries": by_mode,
        "fault_mode_summaries": by_fault,
        "fault_group_mode_summaries": by_group,
        "primary_contrasts": contrasts,
        "adaptive_pre_post": [deepcopy(x) for x in rows if x["evidence_mode"] in {"adaptive_voluntary_guided", "adaptive_required_one_guided"}],
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
    labels = {"current_open": "Current Open", "etiq_empty_open": "Etiq Empty Open", "compact_fixed_guided": "Compact Fixed Guided", "adaptive_voluntary_guided": "Adaptive Voluntary Guided", "adaptive_required_one_guided": "Adaptive Required-One Guided"}
    lines = ["# Attempt 036 — corrected boundary-plus-graph upstream-fault comparison", "", f"Completed 105 reviews, {replay['observed_counts']['logical_provider_calls']} logical provider calls, and zero repairs.", "", "Current and Etiq Empty used genuinely boundary-free final-only interfaces. Fixed and Adaptive received the integrated boundary-plus-graph treatment. The six mutants share one clean base pipeline, so repetitions are repeated calls rather than independent fault instances.", "", "## Overall results", "", "| Arm | Detection | Correct Job 1 | Exact function | Control FP | Expansions | Calls | Input | Cached | Output |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        x = analysis["mode_summaries"][mode]
        lines.append(f"| {labels[mode]} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']} | {x['expansion_sessions']} | {x['provider_calls']} | {x['input_tokens']} | {x['cached_input_tokens']} | {x['output_tokens']} |")
    lines += ["", "## Results by fault", "", "| Fault | Group | Arm | Detected | Job 1 | Exact function | Calls | Input | Cached | Output |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for fault in FAULTS:
        for mode in MODES:
            x = analysis["fault_mode_summaries"][fault][mode]
            lines.append(f"| {fault} | {FAULT_GROUP[fault]} | {labels[mode]} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['provider_calls']} | {x['input_tokens']} | {x['cached_input_tokens']} | {x['output_tokens']} |")
    lines += ["", "## All 105 reviews", "", "| Pos | Trial | Instance | Arm | Rep | Detected/FP | Job | Function | Exact | Expansion | Calls | Input | Cached | Output |", "|---:|---|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|"]
    for row in analysis["rows"]:
        calls = row["raw_calls"]
        outcome = "detected" if row["fault_detected"] else "FP" if row["false_positive"] else "clean/miss"
        lines.append(f"| {row['schedule_position']} | {row['trial_id']} | {row['instance_id']} | {row['evidence_mode']} | {row['repetition']} | {outcome} | {row['suspect_job'] or 'none'} | {row['suspect_function'] or 'none'} | {row['exact_function_localisation']} | {row['completed_expansion_count']} | {len(calls)} | {sum(int(x.get('input_tokens') or 0) for x in calls)} | {sum(int(x.get('cached_input_tokens') or 0) for x in calls)} | {sum(int(x.get('output_tokens') or 0) for x in calls)} |")
    lines += ["", "## Limitations", "", "- Guided-versus-open contrasts estimate the integrated boundary-plus-graph treatment, not graph alone.", "- All six mutations share one clean base pipeline.", "- Three repetitions are repeated reviewer calls, not independent faults.", "- Cached input tokens are already included in input tokens.", ""]
    path = repo_root / "docs/workshops/n20b-attempt-036-boundary-free-upstream-faults-complete-findings.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_bytes_exclusive(path, "\n".join(lines).encode())
    return path


def _write_handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze = ce._read_json(attempt_root / "experiment-freeze.json")
    analysis = ce._read_json(attempt_root / "analysis/summary.json")
    replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    terminal = ce._read_json(attempt_root / "terminal-state.json")
    report = repo_root / "docs/workshops/n20b-attempt-036-boundary-free-upstream-faults-complete-findings.md"
    artifacts = {"freeze": attempt_root / "experiment-freeze.json", "mutation_qualification": attempt_root / "qualification/mutation-summary.json", "captures": attempt_root / "captures", "catalogues": attempt_root / "catalogues", "packages": attempt_root / "packages", "reviews": attempt_root / "reviews", "analysis": attempt_root / "analysis/summary.json", "replay": attempt_root / "replay/reconciliation.json", "terminal": attempt_root / "terminal-state.json", "report": report}
    hashes = {name: ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name, path in artifacts.items()}
    lines = ["To: Overseer", "From: Developer", "Subject: N20B Attempt 036 corrected boundary-free results", "", f"Status: {terminal['status']}", f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)", f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`", "", "Counts", "- Faults: 6; clean controls: 1", "- Packages: 35; reviews: 105; repairs: 0", f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}", f"- Required-One completion: {analysis['required_one_completion']['numerator']}/{analysis['required_one_completion']['denominator']}", f"- Voluntary uptake: {analysis['voluntary_expansion_uptake']['numerator']}/{analysis['voluntary_expansion_uptake']['denominator']}", "", "Mode results", ""]
    for mode in MODES:
        x = analysis["mode_summaries"][mode]
        lines.append(f"- {mode}: detected {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']}; Job 1 {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']}; exact function {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']}; control FP {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']}.")
    lines += ["", "Exact artifact hashes", ""] + [f"- `{artifacts[name].relative_to(repo_root)}`: `{digest}`" for name, digest in hashes.items()] + ["", "Attempts 034 and 035 remained unchanged and their provider responses were not reused. No pipeline, capture, catalogue, or mutation was rerun. No source bundle was supplied. Protected execution and security code was unchanged.", ""]
    path = repo_root / "instructions_between_agent_types/developer/handoffs/N20B_attempt_036_results_to_overseer.email.md"
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
                raise ValueError("invalid N20A partial review")
        else:
            package_record = packages[str(trial["branch_id"])]
            package = package_record["reviewer_package"]
            session = run_review_session(repo_root, attempt_root, catalogues[str(trial["instance_id"])], package, str(trial["trial_id"]), str(trial["evidence_mode"]))
            final, pre = session["final_validation"], session["pre_validation"]
            outcome = score_response(instances[str(trial["instance_id"])], final)
            event = session["operation_event"]
            record = {
                "schema_version": "n20a-review-record-1",
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
                "source_visible": session["source_visible"],
                "values_visible": session["values_visible"],
                "call_records": session["call_records"],
                "usage": session["usage"],
                "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews[(str(trial["branch_id"]), int(trial["repetition"]))] = record
    required = [x for x in reviews.values() if x["controller_trial"]["evidence_mode"] == "adaptive_required_one_guided"]
    if len(reviews) != 105 or len(required) != 21 or any(x["completed_expansion_count"] != 1 for x in required):
        raise RuntimeError("N20A review or Required-One invariant failed")
    call_ids = [str(call_id) for record in reviews.values() for call in record["call_records"] for call_id in call.get("call_ids", [])]
    logical_calls = sum(len(x["call_records"]) for x in reviews.values())
    if not 126 <= logical_calls <= 147 or len(call_ids) != len(set(call_ids)):
        raise ValueError("N20A call count or lineage changed")
    for call_id in call_ids:
        verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = ce._read_json(write_analysis(attempt_root, reviews))
    replay = {
        "schema_version": "n20a-replay-1",
        "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(x["review_sha256"] for x in reviews.values()),
        "observed_counts": {"faults": 6, "controls": 1, "captures": 7, "catalogues": 7, "packages": len(records), "reviews": len(reviews), "repairs": 0, "logical_provider_calls": logical_calls, "provider_attempt_call_ids": len(call_ids), "completed_helper_expansions": sum(x["completed_expansion_count"] for x in reviews.values()), "disclosed_nodes": sum(x["disclosed_node_count"] for x in reviews.values()), "disclosed_relationships": sum(x["disclosed_relationship_count"] for x in reviews.values())},
        "all_record_hashes_recomputed": True,
        "duplicate_logical_calls": False,
        "required_one_sessions_complete": True,
        "source_attempt_unchanged": ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) == ce._read_json(attempt_root / "experiment-freeze.json")["source_attempt_tree_sha256"],
        "preserved_attempt_unchanged": ce.sha256(ce._tree_hashes(repo_root / PRESERVED_ATTEMPT)) == ce._read_json(attempt_root / "experiment-freeze.json")["preserved_attempt_tree_sha256"],
    }
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(attempt_root / "replay/reconciliation.json", replay)
    terminal = {"schema_version": "n20a-terminal-1", "status": "completed_experiment_and_analysis", "fault_count": 6, "control_count": 1, "package_count": 35, "review_count": 105, "repair_trace_count": 0, "analysis_sha256": analysis["analysis_sha256"], "replay_sha256": replay["replay_sha256"]}
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
        terminal = {"schema_version": "n20a-terminal-1", "status": "terminal_incomplete", "failure_stage": "n20a_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}", "completed_review_records": len(list((target / "reviews").glob("*.json"))), "completed_repair_records": 0}
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
            print(json.dumps({"qualification": built["qualification"], "counts": {"captures": len(built["captures"]), "catalogues": len(built["catalogues"]), "packages": len(built["packages"]), "reviews": len(built["schedule"]["review_trials"]), "repairs": 0}}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, attempt))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, attempt), indent=2))
        else:
            path = run_lifecycle(repo, attempt)
            print(path)
            return 0 if ce._read_json(path).get("status") == "completed_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N20A experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
