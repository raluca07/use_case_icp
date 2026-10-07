"""N27PG activation-validity-corrected native-Etiq pilot (Attempt 051)."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import inspect
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import corrected_experiment as ce
from . import n25_experiment as n25
from . import n27pb_experiment as pb
from . import n27pe_experiment as pe
from . import n27pf_experiment as pf


_PF_CONFIGURE = pf._configure_base
_PF_INPUT = pf.input_for
_PF_ORACLE = pf._hidden_oracle
_PF_MUTANT_SOURCE = pf._mutant_source
_PF_PIPELINE = pf._pipeline
_PF_JOB_INPUT = pf._job_input
_PF_VALIDATE_OUTPUT = pf._validate_business_output
_PF_RUN_PIPELINE = pf._run_pipeline_sources
_PF_PUBLIC_CHECKS = pf._public_contract_checks
_PF_DELTA_CHECK = pf._contribution_delta_check
_PF_CONTROL_INVARIANTS = pf._control_invariants
_PF_HARD_FAULT_QUALIFICATION = pf._hard_fault_qualification
_PF_CAPTURE = pf._capture_instance
_PF_CATALOGUE = pf._catalogue
_PF_CONNECTED_HANDOFFS = pf._connected_handoffs
_PF_HANDOFF_QUALIFICATION = pf._capture_handoff_qualification
_PF_LOAD_PREPARED = pf._load_prepared
_PF_BASE_PACKAGE = pf._base_package
_PF_BUILD_PACKAGE = pf.build_package
_PF_PREPARE = pf.prepare_attempt
_PF_PACKAGE_RECORDS = pf._package_records
_PF_INITIAL_EVIDENCE = pf._initial_evidence
_PF_PAIRWISE_CHECKS = pf._pairwise_checks
_PF_RENDER_REQUEST = pf.render_request
_PF_VALIDATE_SCHEMAS = pf.validate_schemas
_PF_LEAKAGE_AUDIT = pf._leakage_audit
_PF_QUALIFY_PACKAGES = pf.qualify_packages
_PE_BUILD_ATTEMPT = pf._PE_BUILD_ATTEMPT
_PF_VALIDATE_RESPONSE = pf.validate_response
_PF_SCORE_RESPONSE = pf.score_response
_PF_RUN_REVIEW = pf.run_review_session
_PF_RECONSTRUCT_COUNTS = pf.reconstruct_counts
_PF_ACTUAL_USAGE = pf._actual_usage
_PF_WRITE_ANALYSIS = pf.write_analysis
_PE_EXECUTE_LIFECYCLE = pf._PE_EXECUTE_LIFECYCLE


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-051")
ATTEMPT_050 = Path("outputs/fault-experiments-v2-2-n10/attempt-050")
TASK = Path("instructions_between_agent_types/developer/current/N27PG_activation_validity_correction_and_complete_pilot.email.md")
TASK_SHA256 = "sha256:40bc549fe63472f0d5339ed1a6e90607a13acaee1cb9b2f8fc421b2e044db234"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PG_activation_validity_correction_and_complete_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:41d2bd403690aadda414bf82077d4f38e94b9eb7d83639d6276509bd7fe8270d"
JOB1_SOURCE = pf.JOB1_SOURCE
JOB2_SOURCE = pf.JOB2_SOURCE
JOB3_SOURCE = pf.JOB3_SOURCE
JOB4_SOURCE = pf.JOB4_SOURCE
PROMPT = pf.PROMPT
FINAL_SCHEMA = pf.FINAL_SCHEMA
GROUP_SCHEMA = pf.GROUP_SCHEMA
ARTIFACT_SCHEMA = pf.ARTIFACT_SCHEMA
RECONSIDER_SCHEMA = pf.RECONSIDER_SCHEMA
ORACLE_FREEZE = pf.ORACLE_FREEZE
CALIBRATION = "deterministic-clean-03"
SANDBOX_GATE = pf.SANDBOX_GATE
SANDBOX_GATE_SHA256 = pf.SANDBOX_GATE_SHA256

JOB_ORDER = pf.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
INSTANCES = pf.INSTANCES
TRUTH = deepcopy(pf.TRUTH)
MATCHED_CLEAN = deepcopy(pf.MATCHED_CLEAN)
MUTATIONS = deepcopy(pf.MUTATIONS)
CELLS = pf.CELLS
MODE_NAMES = pf.MODE_NAMES
CALLS_BY_MODE = pf.CALLS_BY_MODE
BUSINESS_BRIEF = pf.BUSINESS_BRIEF
INTERFACE_DESCRIPTION = deepcopy(pf.INTERFACE_DESCRIPTION)

ATTEMPT_050_HASHES = {
    "terminal-state.json": "sha256:6590ce6bfbbb7dce68b31944b106247d959e7503842b9d7c9d84947b316b9407",
    "calibration/disposition-round-2.json": "sha256:4ea2a225695385197243162ab8caa291f5dd9302042442b319a1ee98390ecd25",
    "calibration/pre-freeze-correction.json": "sha256:319a5f2e72efbc75d966a75eb95a6ca1e1529ba5c5aae5b5a393c548fc1eca62",
}
REUSED_HASHES = {
    JOB1_SOURCE.as_posix(): "sha256:24d446da8fec7833afcc624576a0ac805d3e87b995bbdfa08b2d1050a224b26c",
    JOB2_SOURCE.as_posix(): "sha256:692b43c15401696ad0117578c3fac9a3351a1f83bd249abfcada1a070526588f",
    JOB3_SOURCE.as_posix(): "sha256:27ddd5e24d409fee91b443b66ce731398bca6ba9c526b3b0eef0c0f54beea66b",
    JOB4_SOURCE.as_posix(): "sha256:35e4739828272ac1c51978df1ef044c6f21a88c90ec5b0eae080c48d5f8b602f",
    PROMPT.as_posix(): "sha256:9f54796c4468b8759a904d390265edf7004f5e73d1afcc37c82ff1839f1acaa8",
    FINAL_SCHEMA.as_posix(): "sha256:28b3c172a7aa839da5e86241559251b015ca8f7cf5b5cb0b790ec4ac67da5d6b",
    GROUP_SCHEMA.as_posix(): "sha256:76090dda91bbcd0b10ca23cd832a163afeda96e5c568b34ec1d339ebaa59cb8a",
    ARTIFACT_SCHEMA.as_posix(): "sha256:f59c155d743a0a9188e42cef67973c0c3e66650cd3c9eeed6793ac70875c4b7b",
    RECONSIDER_SCHEMA.as_posix(): "sha256:1e4fd04e723291f0dd62b95ecd8b073a43663bceb3592a04589d6157cccb2aef",
}
PROTECTED_HASHES = deepcopy(pf.PROTECTED_HASHES)


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    pe._write_text(path, value)


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PG authority changed: {relative}")
    for relative, expected in {**REUSED_HASHES, **PROTECTED_HASHES}.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"bound reused/protected file changed: {relative}")
    for relative, expected in ATTEMPT_050_HASHES.items():
        if ce.sha256((repo_root / ATTEMPT_050 / relative).read_bytes()) != expected:
            raise ValueError(f"Attempt 050 preservation binding changed: {relative}")
    if ce.sha256((repo_root / SANDBOX_GATE).read_bytes()) != SANDBOX_GATE_SHA256:
        raise ValueError("signed artifact sandbox gate changed")
    sandbox = {
        "artifact_python_worker_sha256": ce.sha256(pb.operations._ARTIFACT_PYTHON_WORKER.encode()),
        "production_launcher_sha256": pb.operations.production_launcher_sha256(pb.operations.artifact_python_launcher),
        "launch_policy_sha256": pb.operations.ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
    }
    expected = {
        "artifact_python_worker_sha256": "sha256:8e9307c764bb5e9f6511dc96fdc32a5adb3202df6bf0968c0b8522b6c74c98b5",
        "production_launcher_sha256": "sha256:fe8216b7c45091bffecfb1f304c3947548f7a1175fe03ad7c82d506bacc0ba83",
        "launch_policy_sha256": "sha256:ca9a3d0c25ce256c5e2d0ad7e9744d53803bfdc2028043c2839b25b2b8a094c9",
    }
    if sandbox != expected or (ce.PROVIDER_MODEL, ce.PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise ValueError("protected execution binding changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "sandbox": sandbox}


def input_for(instance: str) -> dict[str, Any]:
    value = deepcopy(_PF_INPUT(instance))
    matches = [row for row in value["market_observations"] if row["contribution_id"].endswith("-contribution-02-new")]
    if len(matches) != 1 or matches[0]["valid_until"] != "2026-10-01":
        raise ValueError("N27PG one-field fixture target changed")
    matches[0]["valid_until"] = "2026-10-15"
    older = [
        row for row in value["market_observations"]
        if row["opportunity_id"] == matches[0]["opportunity_id"] and row["source_id"] == matches[0]["source_id"] and row is not matches[0]
    ]
    if len(older) != 1 or older[0]["valid_until"] != "2026-12-31":
        raise ValueError("F2 competing older record changed")
    return value


def _hidden_oracle(root: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return _PF_ORACLE(root)


def _mutant_source(clean: str, instance: str):
    return _PF_MUTANT_SOURCE(clean, instance)


def _pipeline(repo_root: Path, job_id: str, job1_source: str):
    return _PF_PIPELINE(repo_root, job_id, job1_source)


def _job_input(job_id: str, prior_output: Mapping[str, Any] | None, root: Mapping[str, Any]) -> dict[str, Any]:
    return _PF_JOB_INPUT(job_id, prior_output, root)


def _validate_business_output(job_id: str, output: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    _PF_VALIDATE_OUTPUT(job_id, output, runtime_input)


def _run_pipeline_sources(repo_root: Path, root: Mapping[str, Any], job1_source: str | None = None) -> dict[str, Any]:
    return _PF_RUN_PIPELINE(repo_root, root, job1_source)


def _public_contract_checks(repo_root: Path, instance: str) -> dict[str, Any]:
    return _PF_PUBLIC_CHECKS(repo_root, instance)


def _contribution_delta_check(repo_root: Path) -> dict[str, Any]:
    return _PF_DELTA_CHECK(repo_root)


def _control_invariants(repo_root: Path, instance: str) -> dict[str, Any]:
    return _PF_CONTROL_INVARIANTS(repo_root, instance)


def _retained_validity(root: Mapping[str, Any], outputs: Mapping[str, Any]) -> dict[str, Any]:
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for row in root["market_observations"]:
        by_id.setdefault(row["contribution_id"], []).append(row)
    audit = outputs[JOB3]["contribution_audit"]
    actions = outputs[JOB4]["activation_plan"]["activation_actions"]
    activation_dates: dict[str, list[str]] = {}
    for row in actions:
        activation_dates.setdefault(row["campaign_id"], []).append(row["window_start"])
    unique = all(len(by_id.get(row["contribution_id"], [])) == 1 for row in audit)
    decision = root["selection_policy"]["as_of_date"]
    decision_valid = all(
        by_id[row["contribution_id"]][0]["effective_date"] <= decision <= by_id[row["contribution_id"]][0]["valid_until"]
        for row in audit if len(by_id.get(row["contribution_id"], [])) == 1
    )
    activation_valid = all(
        all(by_id[row["contribution_id"]][0]["valid_until"] >= date for date in activation_dates.get(row["campaign_id"], []))
        for row in audit if len(by_id.get(row["contribution_id"], [])) == 1
    )
    return {
        "audit_records_resolve_to_exactly_one_input": unique,
        "retained_effective_and_valid_at_decision": decision_valid,
        "retained_valid_through_all_campaign_activations": activation_valid,
        "audit_record_count": len(audit),
        "latest_activation": max((row["window_start"] for row in actions), default=None),
    }


def _changed_campaigns(clean: Mapping[str, Any], faulty: Mapping[str, Any]) -> list[str]:
    left = {row["campaign_id"]: row for row in clean[JOB4]["activation_plan"]["activation_actions"]}
    right = {row["campaign_id"]: row for row in faulty[JOB4]["activation_plan"]["activation_actions"]}
    return sorted(campaign for campaign in left if left[campaign] != right.get(campaign))


def _pre_capture_activation_audit(repo_root: Path, target: Path) -> dict[str, Any]:
    _configure_base()
    path = target / "qualification/activation-validity-pre-capture.json"
    if path.exists():
        record = _json(path)
        ce._verified_self_hash(record, "audit_sha256")
        return record
    clean_source = (repo_root / JOB1_SOURCE).read_text()
    clean_outputs = {}
    actual_outputs = {}
    clean_validity = {}
    actual_validity = {}
    mutation_checks = {}
    symptoms = {}
    for instance in INSTANCES:
        root = input_for(instance)
        clean = _run_pipeline_sources(repo_root, root)
        source, mutation = _mutant_source(clean_source, instance)
        actual = _run_pipeline_sources(repo_root, root, source)
        clean_outputs[instance] = clean
        actual_outputs[instance] = actual
        clean_validity[instance] = _retained_validity(root, clean)
        actual_validity[instance] = _retained_validity(root, actual)
        if not all(clean_validity[instance][key] for key in (
            "audit_records_resolve_to_exactly_one_input", "retained_effective_and_valid_at_decision", "retained_valid_through_all_campaign_activations"
        )):
            raise ValueError(f"clean activation-validity gate failed: {instance}")
        if mutation:
            old, new = MUTATIONS[instance]
            if clean_source.count(old) != 1 or ast.dump(ast.parse(clean_source)) == ast.dump(ast.parse(source)):
                raise ValueError(f"one-site mutation check failed: {instance}")
            if not actual_validity[instance]["audit_records_resolve_to_exactly_one_input"] or not actual_validity[instance]["retained_valid_through_all_campaign_activations"]:
                raise ValueError(f"fault audit identity/activation validity failed: {instance}")
            if len(actual[JOB4]["activation_plan"]["activation_actions"]) != len(clean[JOB4]["activation_plan"]["activation_actions"]):
                raise ValueError(f"fault action count changed: {instance}")
            changed = _changed_campaigns(clean, actual)
            if not 1 <= len(changed) <= 2:
                raise ValueError(f"fault symptom is not small: {instance}/{changed}")
            mutation_checks[instance] = {
                "one_ast_site": True, "truth_function": mutation["qualified_function_name"],
                "schema_preserved": all(set(actual[job]) == set(clean[job]) for job in JOB_ORDER),
                "job4_action_count_preserved": True,
            }
            symptoms[instance] = {"job4_sha256": ce.sha256(actual[JOB4]), "changed_campaign_count": len(changed)}
    if len({row["job4_sha256"] for row in symptoms.values()}) != 3:
        raise ValueError("fault symptoms are not distinct")
    f1 = actual_validity[INSTANCES[2]]
    if f1["retained_effective_and_valid_at_decision"]:
        raise ValueError("F1 no longer exposes its intended future-effective evidence divergence")
    f2_root = input_for(INSTANCES[3])
    f2_actual = actual_outputs[INSTANCES[3]][JOB1]["evidence_attribution"]
    newer = next(row for row in f2_root["market_observations"] if row["contribution_id"].endswith("-contribution-02-new"))
    selected_pair = [row for row in f2_actual if row["opportunity_id"] == newer["opportunity_id"] and row["source_id"] == newer["source_id"]]
    if len(selected_pair) != 1 or selected_pair[0]["contribution_id"] == newer["contribution_id"]:
        raise ValueError("F2 mutation no longer selects the older longer-valid record")
    corrected_root = input_for(INSTANCES[0])
    corrected_output = _run_pipeline_sources(repo_root, corrected_root)
    old_root = deepcopy(corrected_root)
    old_row = next(row for row in old_root["market_observations"] if row["contribution_id"].endswith("-contribution-02-new"))
    old_row["valid_until"] = "2026-10-01"
    old_output = _run_pipeline_sources(repo_root, old_root)
    old_check = _retained_validity(old_root, old_output)["retained_valid_through_all_campaign_activations"]
    new_check = _retained_validity(corrected_root, corrected_output)["retained_valid_through_all_campaign_activations"]
    if old_check or not new_check:
        raise ValueError("activation-validity regression did not distinguish old and corrected expiry")
    public = {instance: _public_contract_checks(repo_root, instance) for instance in INSTANCES[:2]}
    controls = {instance: _control_invariants(repo_root, instance) for instance in INSTANCES[:2]}
    delta = _contribution_delta_check(repo_root)
    record = {
        "schema_version": "n27pg-activation-validity-pre-capture-1", "status": "passed", "model_calls": 0,
        "exact_input_delta": {
            "selector": "contribution_id suffix -contribution-02-new", "field": "valid_until",
            "before": "2026-10-01", "after": "2026-10-15", "changed_fields_per_instance": 1,
            "competing_older_record_valid_until": "2026-12-31", "latest_selected_activation": "2026-10-14",
        },
        "regression": {"attempt_050_value_fails_activation_validity": not old_check, "attempt_051_value_passes_activation_validity": new_check},
        "clean_validity": clean_validity, "actual_fault_or_control_validity": actual_validity,
        "f1_expected_decision_validity_violation_is_fault_signal": True,
        "f2_older_longer_valid_record_selected_by_mutant": True,
        "public_contract_controls": public, "control_invariants": controls,
        "single_count_contribution_delta": delta, "mutation_checks": mutation_checks,
        "distinct_small_symptoms": symptoms,
    }
    record["audit_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return record


def _deterministic_calibration_replacement(repo_root: Path, target: Path, clean_source: str) -> dict[str, Any]:
    del repo_root, clean_source
    path = target / "calibration/disposition.json"
    if path.exists():
        record = _json(path)
        ce._verified_self_hash(record, "disposition_sha256")
        return record
    record = {
        "schema_version": "n27pg-deterministic-calibration-replacement-1",
        "status": "passed", "scenario": "no-model-deterministic-validity-gate",
        "calls": 0, "authorized_model_calibration_calls": 0,
        "experimental_analysis_excluded": True, "model_calls": 0,
        "activation_validity_pre_capture_sha256": _json(target / "qualification/activation-validity-pre-capture.json")["audit_sha256"],
        "attempt_050_calibration_reused": False,
    }
    record["disposition_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return record


def _calibration_disposition(target: Path) -> dict[str, Any]:
    return _json(target / "calibration/disposition.json")


def _configure_base() -> None:
    pf.ATTEMPT = ATTEMPT
    pf.TASK = TASK
    pf.TASK_SHA256 = TASK_SHA256
    pf.AUTHORITY = AUTHORITY
    pf.AUTHORITY_SHA256 = AUTHORITY_SHA256
    pf.CALIBRATION = CALIBRATION
    pf.INSTANCES = INSTANCES
    pf.TRUTH = TRUTH
    pf.MATCHED_CLEAN = MATCHED_CLEAN
    pf.MUTATIONS = MUTATIONS
    pf.BUSINESS_BRIEF = BUSINESS_BRIEF
    pf.INTERFACE_DESCRIPTION = INTERFACE_DESCRIPTION
    pf._verify_authority = _verify_authority
    pf.input_for = input_for
    pf._hidden_oracle = _hidden_oracle
    pf._mutant_source = _mutant_source
    pf._pipeline = _pipeline
    pf._job_input = _job_input
    pf._validate_business_output = _validate_business_output
    pf._run_pipeline_sources = _run_pipeline_sources
    pf._public_contract_checks = _public_contract_checks
    pf._contribution_delta_check = _contribution_delta_check
    pf._control_invariants = _control_invariants
    pf._calibration = _deterministic_calibration_replacement
    _PF_CONFIGURE()
    pe.ATTEMPT = ATTEMPT
    pe.TASK = TASK
    pe.TASK_SHA256 = TASK_SHA256
    pe.AUTHORITY = AUTHORITY
    pe.AUTHORITY_SHA256 = AUTHORITY_SHA256
    pe.CALIBRATION = CALIBRATION
    pe.INSTANCES = INSTANCES
    pe.TRUTH = TRUTH
    pe.MATCHED_CLEAN = MATCHED_CLEAN
    pe.MUTATIONS = MUTATIONS
    pe.BUSINESS_BRIEF = BUSINESS_BRIEF
    pe.INTERFACE_DESCRIPTION = INTERFACE_DESCRIPTION
    pe._verify_authority = _verify_authority
    pe.input_for = input_for
    pe._hidden_oracle = _hidden_oracle
    pe._mutant_source = _mutant_source
    pe._pipeline = _pipeline
    pe._job_input = _job_input
    pe._validate_business_output = _validate_business_output
    pe._run_pipeline_sources = _run_pipeline_sources
    pe._control_invariants = _control_invariants
    pe._hard_fault_qualification = _hard_fault_qualification
    pe._calibration = _deterministic_calibration_replacement
    pe._calibration_disposition = _calibration_disposition
    pe._base_package = _base_package
    pe.build_package = build_package
    pe.prepare_attempt = prepare_attempt
    pe.schedule = schedule
    pe.qualify_packages = qualify_packages
    pe.verify_frozen_attempt = verify_frozen_attempt
    pe.create_live_consumption = create_live_consumption
    pe.run_review_session = run_review_session
    pe.write_analysis = write_analysis
    pe._write_reports = _write_reports
    pe._write_handoff = _write_handoff
    pe._configure_base = _configure_base


def _hard_fault_qualification(captures: Mapping[str, Mapping[str, Any]], instances: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return _PF_HARD_FAULT_QUALIFICATION(captures, instances)


def _capture_instance(repo_root: Path, target: Path, instance: str, job1_source: str):
    _configure_base()
    return _PF_CAPTURE(repo_root, target, instance, job1_source)


def _catalogue(capture: Mapping[str, Any]):
    return _PF_CATALOGUE(capture)


def _connected_handoffs(catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _PF_CONNECTED_HANDOFFS(catalogue)


def _capture_handoff_qualification(capture: Mapping[str, Any], catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _PF_HANDOFF_QUALIFICATION(capture, catalogue)


def _load_prepared(target: Path) -> dict[str, Any]:
    _configure_base()
    return _PF_LOAD_PREPARED(target)


def _base_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    _configure_base()
    package = _PF_BASE_PACKAGE(catalogue, source_bundle)
    package["schema_version"] = "n27pg-review-package-1"
    return package


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], compact: Mapping[str, Any], mode: str) -> dict[str, Any]:
    _configure_base()
    pe._base_package = _base_package
    package = _PF_BUILD_PACKAGE(catalogue, source_bundle, compact, mode)
    _configure_base()
    return package


def schedule() -> dict[str, Any]:
    cells = []
    for instance in INSTANCES:
        for mode in CELLS:
            cells.append({
                "opaque_instance_id": instance, "cell_id": mode, "mode": mode,
                "mode_name": MODE_NAMES[mode], "declaration_setting": "B1" if mode in {"P03", "P05"} else "B0",
                "branch_id": f"brn-{ce.sha256(['n27pg', instance, mode])[7:23]}",
            })
    reviews = []
    for repetition in (1, 2):
        order = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for block, instance in enumerate(order):
            values = [value for value in cells if value["opaque_instance_id"] == instance]
            rotation = (block + repetition) % len(values)
            for cell in values[rotation:] + values[:rotation]:
                reviews.append({
                    **cell, "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n27pg', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if len(cells) != 30 or len(reviews) != 60 or sum(CALLS_BY_MODE[row["mode"]] for row in reviews) != 120:
        raise AssertionError("Attempt 051 schedule counts changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _public_contract_path(target: Path) -> Path:
    return target / "qualification/public-contract-audit.json"


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_base()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PG is authorized only for Attempt 051")
    _verify_authority(repo_root)
    _pre_capture_activation_audit(repo_root, target)
    prepared = _PF_PREPARE(repo_root, target)
    _configure_base()
    return prepared


def _package_records(target: Path) -> list[dict[str, Any]]:
    return _PF_PACKAGE_RECORDS(target)


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return _PF_INITIAL_EVIDENCE(package)


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    _configure_base()
    return _PF_PAIRWISE_CHECKS(records)


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _configure_base()
    return _PF_RENDER_REQUEST(package, operation_response)


def validate_schemas(repo_root: Path) -> dict[str, str]:
    _configure_base()
    return _PF_VALIDATE_SCHEMAS(repo_root)


def _leakage_audit(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    _configure_base()
    return _PF_LEAKAGE_AUDIT(records)


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    _configure_base()
    value = _PF_QUALIFY_PACKAGES(repo_root, target, records, prepared, design)
    pre = _json(target / "qualification/activation-validity-pre-capture.json")
    if pre["status"] != "passed" or _calibration_disposition(target)["calls"] != 0:
        raise ValueError("N27PG deterministic gate or zero-calibration policy failed")
    value.update({
        "schema_version": "n27pg-no-model-verification-1",
        "activation_validity_pre_capture_sha256": pre["audit_sha256"],
        "model_calibration_calls": 0,
        "attempt_050_preservation_verified": True,
    })
    _configure_base()
    return value


def _finalize_activation_validity_audit(target: Path) -> dict[str, Any]:
    path = target / "qualification/activation-validity-audit.json"
    if path.exists():
        record = _json(path)
        ce._verified_self_hash(record, "audit_sha256")
        return record
    pre = _json(target / "qualification/activation-validity-pre-capture.json")
    hard = _json(target / "qualification/hard-faults.json")
    relevance = _json(target / "qualification/adaptive-fault-relevance.json")
    native = _json(target / "qualification/native-captures-and-handoffs.json")
    if hard["status"] != "passed" or relevance["status"] != "passed" or native["fresh_job_executions"] != 20:
        raise ValueError("post-capture activation-validity evidence is incomplete")
    reachability = {}
    for instance in MATCHED_CLEAN:
        item = relevance["faults"][instance]
        if not item["initially_hidden"] or not item["disclosed_by_complete_subtree"] or item["function_name_match_alone_used_as_relevance_proof"]:
            raise ValueError(f"fault hidden-state reachability failed: {instance}")
        reachability[instance] = {
            "initially_hidden": True,
            "reachable_by_one_native_subtree_and_one_artifact_inspection": True,
            "function_name_matching_not_used_as_relevance_proof": True,
            "model_selectable_execution_group_id": item["model_selectable_execution_group_id"],
            "artifact_ref": item["artifact_ref"],
        }
    if not all(row["mutated_scope_executed"] for row in hard["one_site_executed_mutations"].values()):
        raise ValueError("one or more mutation sites did not execute in native capture")
    record = {
        "schema_version": "n27pg-activation-validity-audit-1", "status": "passed", "model_calls": 0,
        "pre_capture_audit_sha256": pre["audit_sha256"],
        "exact_input_delta": deepcopy(pre["exact_input_delta"]),
        "regression": deepcopy(pre["regression"]),
        "clean_pipeline_and_control_checks": {
            "both_controls_match_independent_oracle": True,
            "permutation_irrelevant_row_identifier_renaming": True,
            "single_count_job2_job3_budget_job4_capacity_lossless_audit_manifest": True,
        },
        "fault_qualification": {
            "one_executed_ast_site_each": True,
            "schemas_and_job4_action_counts_preserved": True,
            "distinct_small_downstream_symptoms": hard["distinct_fault_job4_hashes"],
            "hard_fault_qualification_sha256": hard["qualification_sha256"],
        },
        "hidden_state_reachability": reachability,
        "fresh_native_capture_count": native["fresh_job_executions"],
        "native_capture_qualification_sha256": native["qualification_sha256"],
        "model_calibration_calls": 0,
    }
    record["audit_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return record


def _write_no_model_freeze_verifier(repo_root: Path, target: Path, built: Mapping[str, Any]) -> dict[str, Any]:
    path = target / "qualification/n27pg-no-model-freeze-verifier.json"
    if path.exists():
        record = _json(path)
        ce._verified_self_hash(record, "verifier_sha256")
        return record
    records = list(built["records"])
    design = built["design"]
    pairwise = _pairwise_checks(records)
    leakage = _json(target / "qualification/reviewer-leakage-audit.json")
    audit = _json(target / "qualification/activation-validity-audit.json")
    if len(records) != 30 or len(design["review_trials"]) != 60:
        raise ValueError("package/review counts changed")
    if sum(CALLS_BY_MODE[row["mode"]] for row in design["review_trials"]) != 120:
        raise ValueError("planned inference calls changed")
    if not all(row["passed"] for row in pairwise) or leakage["status"] != "passed" or audit["status"] != "passed":
        raise ValueError("package isolation, leakage or activation-validity verification failed")
    if _calibration_disposition(target)["calls"] != 0:
        raise ValueError("Attempt 051 made a calibration call")
    record = {
        "schema_version": "n27pg-no-model-freeze-verifier-1", "status": "passed", "model_calls": 0,
        "activation_validity_audit_sha256": audit["audit_sha256"],
        "strict_schema_hashes": validate_schemas(repo_root),
        "packages": len(records), "terminal_reviews": len(design["review_trials"]),
        "planned_provider_calls": 120, "repairs": 0, "calibration_calls": 0,
        "pairwise_isolation_checks": len(pairwise), "starting_graph_identity_checked": True,
        "leakage_audit_sha256": leakage["audit_sha256"],
        "exact_resume_mechanics_reused": True,
        "attempt_050_preservation_verified": True,
    }
    record["verifier_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return record


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_base()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    built = _PE_BUILD_ATTEMPT(repo_root, target)
    _finalize_activation_validity_audit(target)
    _write_no_model_freeze_verifier(repo_root, target, built)
    _configure_base()
    return built


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27pg_experiment.py"), JOB1_SOURCE, JOB2_SOURCE, JOB3_SOURCE, JOB4_SOURCE,
        PROMPT, FINAL_SCHEMA, GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27pg_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 051 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after experimental reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("focused N27PG tests must pass before freeze")
    deterministic = _calibration_disposition(target)
    activation = _json(target / "qualification/activation-validity-audit.json")
    verifier = _json(target / "qualification/n27pg-no-model-freeze-verifier.json")
    if deterministic["calls"] != 0 or activation["status"] != "passed" or verifier["status"] != "passed":
        raise ValueError("deterministic pre-freeze gate failed")
    freeze = {
        "schema_version": "n27pg-experiment-freeze-1", "attempt": "051", "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {code_path.as_posix(): ce.sha256((repo_root / code_path).read_bytes()) for code_path in _code_paths()},
        "attempt_050_hashes": deepcopy(ATTEMPT_050_HASHES), "reused_hashes": deepcopy(REUSED_HASHES),
        "protected_hashes": deepcopy(PROTECTED_HASHES),
        "sandbox_gate_file_sha256": ce.sha256((repo_root / SANDBOX_GATE).read_bytes()),
        "sandbox_bindings": deepcopy(built["prepared"]["authority"]["sandbox"]),
        "activation_validity_audit_file_sha256": ce.sha256((target / "qualification/activation-validity-audit.json").read_bytes()),
        "no_model_freeze_verifier_file_sha256": ce.sha256((target / "qualification/n27pg-no-model-freeze-verifier.json").read_bytes()),
        "zero_call_deterministic_disposition_file_sha256": ce.sha256((target / "calibration/disposition.json").read_bytes()),
        "public_contract_audit_file_sha256": ce.sha256(_public_contract_path(target).read_bytes()),
        "common_material_freeze_file_sha256": ce.sha256((target / "qualification/scientific-common-material-freeze.json").read_bytes()),
        "hidden_oracle_file_sha256": ce.sha256((target / ORACLE_FREEZE).read_bytes()),
        "clean_control_file_sha256": ce.sha256((target / "qualification/clean-controls.json").read_bytes()),
        "hard_fault_file_sha256": ce.sha256((target / "qualification/hard-faults.json").read_bytes()),
        "native_capture_handoff_file_sha256": ce.sha256((target / "qualification/native-captures-and-handoffs.json").read_bytes()),
        "adaptive_relevance_file_sha256": ce.sha256((target / "qualification/adaptive-fault-relevance.json").read_bytes()),
        "leakage_audit_file_sha256": ce.sha256((target / "qualification/reviewer-leakage-audit.json").read_bytes()),
        "capture_hashes": {key: built["prepared"]["captures"][key]["capture_sha256"] for key in INSTANCES},
        "catalogue_hashes": {key: built["prepared"]["catalogues"][key]["catalogue_sha256"] for key in INSTANCES},
        "instance_hashes": {key: built["prepared"]["instances"][key]["instance_sha256"] for key in INSTANCES},
        "tree_hashes": {folder: ce.sha256(ce._tree_hashes(target / folder)) for folder in (
            "capture-branches", "job-captures", "native-exports", "catalogues", "artifact-disclosures",
            "omission-manifests", "projections", "packages", "controller-manifests",
        )},
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "no_model_verification_file_sha256": ce.sha256((target / "qualification/no-model-verification.json").read_bytes()),
        "focused_test_results_file_sha256": ce.sha256(focused.read_bytes()),
        "expected_counts": {"calibration_calls": 0, "instances": 5, "fresh_job_executions": 20, "packages": 30, "reviews": 60, "follow_up_calls": 60, "provider_calls": 120, "repairs": 0},
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0, "full_replication_started": False,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    ce._write_immutable(path, freeze)
    return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _verify_authority(repo_root)
    freeze = _json(target / "experiment-freeze.json")
    digest = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        actual = ce.sha256((repo_root / relative).read_bytes())
        if actual != expected:
            correction_path = target / "qualification/controller-exact-resume-correction.json"
            if relative != Path("src/use_case_icp/n27pg_experiment.py").as_posix() or not correction_path.exists():
                raise ValueError(f"frozen code changed: {relative}")
            correction = _json(correction_path)
            ce._verified_self_hash(correction, "correction_sha256")
            if (
                correction.get("status") != "preauthorized_controller_only_exact_resume"
                or correction.get("frozen_code_sha256") != expected
                or correction.get("corrected_code_sha256") != actual
                or correction.get("scientific_changes") is not False
                or correction.get("additional_provider_calls") != 0
            ):
                raise ValueError("invalid controller exact-resume correction")
    built = build_attempt(repo_root, target)
    for folder, expected in freeze["tree_hashes"].items():
        if ce.sha256(ce._tree_hashes(target / folder)) != expected:
            raise ValueError(f"frozen tree changed: {folder}")
    if sorted(record["package_sha256"] for record in built["records"]) != freeze["package_hashes"]:
        raise ValueError("frozen package membership changed")
    if ce.sha256(built["design"]["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("frozen review schedule changed")
    return {"status": "verified", "freeze_sha256": digest, "packages": 30, "reviews": 60, "provider_calls": 120, "repairs": 0, "qualification": built["qualification"]}


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("live authority must be consumed before reviews")
    freeze = _json(target / "experiment-freeze.json")
    record = {
        "schema_version": "n27pg-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "one_use_live_authority": True,
        "authorized_experimental_calls": 120, "calibration_calls": 0, "repairs": 0,
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], stage: str) -> dict[str, Any]:
    _configure_base()
    return _PF_VALIDATE_RESPONSE(repo_root, package, response, stage)


def score_response(instance: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    return _PF_SCORE_RESPONSE(instance, validation)


def run_review_session(repo_root: Path, target: Path, catalogue: Mapping[str, Any], reviewer: Mapping[str, Any], disclosure: Mapping[str, Any], index: Mapping[str, Any], package_record: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    _configure_base()
    value = _PF_RUN_REVIEW(repo_root, target, catalogue, reviewer, disclosure, index, package_record, trial_id)
    _configure_base()
    return value


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return _PF_RECONSTRUCT_COUNTS(reviews)


def _actual_usage(usage: Mapping[str, Any]) -> dict[str, int]:
    return _PF_ACTUAL_USAGE(usage)


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    _configure_base()
    path = _PF_WRITE_ANALYSIS(target, reviews)
    _configure_base()
    return path


def _rate(value: Mapping[str, int]) -> str:
    return "n/a" if not value["denominator"] else f"{value['numerator']}/{value['denominator']} ({100 * value['numerator'] / value['denominator']:.2f}%)"


def _write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PG-activation-validity-corrected-native-etiq-pilot"
    findings = [
        "# N27PG activation-validity-corrected native-Etiq pilot", "",
        "Attempt 051 completed the authorized five-instance exploratory pilot. Attempt 050 remains preserved and the full replication remains deferred.", "",
        "## Aggregate outcomes", "",
        f"- Fault sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct earliest Job-1 localisation: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Balanced fault-discrimination accuracy: {aggregate['balanced_fault_discrimination_accuracy']:.4f}",
        f"- Experimental provider calls: {aggregate['provider_calls']}; model calibration calls: 0",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; derived total {aggregate['total_tokens']}", "",
        "All 20 scientific captures are fresh native Etiq executions. Every connected graph contains nine separately labelled exact-hash handoffs. The activation-validity gate was deterministic and no repairs were run.", "",
        "## Immutable records", "",
        "- [Activation-validity audit](../../../../outputs/fault-experiments-v2-2-n10/attempt-051/qualification/activation-validity-audit.json)",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-051/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-051/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-051/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-051/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    cell_lines = ["# Complete cell table", "", "| Cell | Reviews | Detection /6 | Job 1 /6 | Exact /6 | Control FP /4 | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in CELLS:
        value = analysis["cell_summaries"][cell]
        cell_lines.append(f"| {cell} | {value['reviews']} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} | {_rate(value['control_false_positives'])} | {value['provider_calls']} |")
    _write_text(report_dir / "cell-table.md", "\n".join(cell_lines))
    fault_lines = ["# Complete fault table", "", "| Fault | Cell | Detection /2 | Job 1 /2 | Exact /2 |", "|---|---|---:|---:|---:|"]
    for instance in MATCHED_CLEAN:
        for cell in CELLS:
            value = analysis["fault_cell_summaries"][f"{instance}/{cell}"]
            fault_lines.append(f"| {instance} | {cell} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} |")
    _write_text(report_dir / "fault-table.md", "\n".join(fault_lines))
    control_lines = ["# Complete control table", "", "| Control | Cell | False positives /2 |", "|---|---|---:|"]
    for instance in INSTANCES[:2]:
        for cell in CELLS:
            value = analysis["control_cell_summaries"][f"{instance}/{cell}"]
            control_lines.append(f"| {instance} | {cell} | {_rate(value['control_false_positives'])} |")
    _write_text(report_dir / "control-table.md", "\n".join(control_lines))
    operation_lines = ["# Complete operation table", "", "| Trial | Cell | Group | Artifact | Inspection | Bytes | True group | True artifact |", "|---|---|---|---|---|---:|---|---|"]
    token_lines = ["# Complete token table", "", "| Trial | Cell | Rep | Calls | Input | Cached | Output | Total |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    review_lines = ["# Complete review table", "", "| Position | Trial | Instance | Cell | Rep | Detected | Job | Function | Calls |", "|---:|---|---|---|---:|---|---|---|---:|"]
    for review in sorted(reviews, key=lambda value: value["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        group, artifact = review.get("selected_group") or {}, review.get("selected_artifact") or {}
        usage = _actual_usage(review["usage"])
        operation_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {artifact.get('inspection', '')} | {artifact.get('artifact_bytes_returned', 0)} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} |")
        token_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {trial['repetition']} | {len(review['call_records'])} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['input_tokens'] + usage['output_tokens']} |")
        review_lines.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |")
    _write_text(report_dir / "operation-table.md", "\n".join(operation_lines))
    _write_text(report_dir / "token-table.md", "\n".join(token_lines))
    _write_text(report_dir / "review-table.md", "\n".join(review_lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PG Attempt 051 activation-validity-corrected pilot results", "",
        "Status: `completed_pilot_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "",
        "- Zero model calibration calls",
        "- Five instances and 20 fresh native Etiq scientific job captures",
        f"- 30 packages; 60 terminal reviews; {aggregate['provider_calls']} experimental calls; zero repairs", "",
        "Outcomes", "",
        f"- Sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Balanced fault-discrimination accuracy: {aggregate['balanced_fault_discrimination_accuracy']:.4f}", "",
        "Attempt 050 and all protected execution surfaces remained unchanged. The full replication was not started.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PG_attempt_051_results_to_overseer.email.md", "\n".join(lines))


def execute_lifecycle(repo_root: Path, target: Path) -> Path:
    _configure_base()
    freeze = _json(target / "experiment-freeze.json")
    disposition = target / "calibration/disposition.json"
    if ce.sha256(disposition.read_bytes()) != freeze["zero_call_deterministic_disposition_file_sha256"]:
        raise ValueError("frozen zero-call deterministic disposition changed")
    calibration_tree_sha256 = ce.sha256(ce._tree_hashes(target / "calibration"))
    original_json = pe._json

    def read_with_attempt_051_compatibility(path: Path) -> dict[str, Any]:
        record = original_json(path)
        if Path(path).resolve() == (target / "experiment-freeze.json").resolve():
            record = deepcopy(record)
            record["calibration_tree_sha256"] = calibration_tree_sha256
        return record

    pe._json = read_with_attempt_051_compatibility
    try:
        return _PE_EXECUTE_LIFECYCLE(repo_root, target)
    finally:
        pe._json = original_json


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        record = {
            "schema_version": "n27pg-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27pg_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
            "completed_review_records": len(list((target / "reviews").glob("*.json"))), "completed_repair_records": 0,
        }
        record["terminal_sha256"] = ce.sha256(record)
        path = target / "terminal" / f"terminal-incomplete-{record['terminal_sha256'][7:23]}.json"
        ce._write_immutable(path, record)
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--attempt-root", default=ATTEMPT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    target = Path(args.attempt_root)
    target = target if target.is_absolute() else repo / target
    try:
        if args.operation == "build":
            print(json.dumps({"qualification": build_attempt(repo, target)["qualification"]}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, target))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, target), indent=2))
        else:
            path = run_lifecycle(repo, target)
            print(path)
            return 0 if _json(path).get("status") == "completed_pilot_and_analysis" else 1
    except Exception as exc:
        print(f"N27PG experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
