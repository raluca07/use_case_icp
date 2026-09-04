"""N12 append-only execution entry point for protocol 2.2."""

from __future__ import annotations

from copy import deepcopy
import importlib.metadata
from pathlib import Path
import re
import sys
from typing import Any

from .n05_program import _file_contract, run_isolation_dry_run
from .n05_runner import (
    bubblewrap_version,
    canonical_json,
    create_json_exclusive,
    launch_policy_identity,
    sha256_bytes,
    sha256_file,
)
from .n07_program import (
    ACCEPTED_PHASE_A_SHA256,
    ACCEPTED_PHASE_A_TREE_SHA256,
    EXPECTED_COUNTS,
    N12_AUTHORIZATION_SHA256,
    PROTOCOL_CONTENT_SHA256,
    _live_provider,
    _load_json,
    _qualification_provider,
    _run_lifecycle,
    _tree_contract,
    verify_accepted_phase_a,
)


N12_TASK = Path(
    "instructions_between_agent_types/developer/current/"
    "N12_v2_2_phase_b_removal_and_experiment_execution.email.md"
)
N12_TASK_SHA256 = "sha256:0d2815bd1f9f3425fa99e6498e28acecc177cf9287d65c4675f615794062244a"
N12_AUTHORIZATION = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "N12_v2_2_phase_b_removal_and_experiment_execution_authorization.json"
)
PROTOCOL_JSON = Path("docs/workshops/neurips-2026-v2-2/experiment-protocol.json")
N10_OUTPUT_RELATIVE = Path("outputs/fault-experiments-v2-2-n10")
N12_QUALIFICATION_RELATIVE = Path("qualification-n12-002")
N12_READINESS_NAME = "n12-readiness-013.json"
N12_TEST_OUTPUT_DIR = "test-outputs-013"
N12_ATTEMPT = "attempt-023"
N13_TASK = Path(
    "instructions_between_agent_types/developer/current/"
    "N13_v2_2_fix_review_ledger_collision_and_resume_96_packages.email.md"
)
N13_TASK_SHA256 = "sha256:819a4aae80dd9c6532c706aeb2116ea5dd2d9aaf54fb32910a115aa573d57fa5"
N13_AUTHORIZATION = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "N13_v2_2_review_ledger_collision_correction_and_package_reuse_authorization.json"
)
N13_AUTHORIZATION_SHA256 = "sha256:f94952ae30f1045b74a199dd95bc502df1d5f08a26b205ecd09d7c9129828400"
N14_TASK = Path(
    "instructions_between_agent_types/developer/current/"
    "N14_corrected_four_instance_finish_gate_freeze_and_run.email.md"
)
N14_TASK_SHA256 = "sha256:45b28eb60a78523908cf94efc6de11ecdd8551ec1c4bb2debb25b7f41b083056"
N14_AUTHORIZATION = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "N14_corrected_four_instance_execution_authorization.json"
)
N14_AUTHORIZATION_SHA256 = "sha256:725b0e8f6d8b2f65cf568f56c279e7cb38145706787480dfcc5f369f5bc9ea7e"
N13_ORIGINAL_SOURCE_TREE_SHA256 = "sha256:3e0338d5a60c72f116b686ae3f644adc12935e0cfdefaacd23d8e1e2d78d4a4f"
N13_CORRECTION_RELATIVE = Path("post-freeze-controller-correction.json")
N13_TEST_OUTPUT_DIR = "post-freeze-verification"
N13_CHANGED_PATHS_BEFORE = {
    "src/use_case_icp/n07_program.py": "sha256:f56c077226109290903306e4fb53ea65dd88fe4a3ebcabba44f813efc2d53298",
    "src/use_case_icp/n10_program.py": "sha256:74813b3c84700bd550c10a4072f62e79e5de6f9ccb1cc64520d72435651471fd",
    "tests/test_n10_program.py": "sha256:f90370665fe44187d30816687f344c107778be242205eda814973671b1924ebe",
}
N13_FROZEN_HASHES = {
    "experiment_freeze_file_sha256": "sha256:18d1aa73f8b2a2694207fa91a7d8496bfe39339a775cbda0b992f895f124a7d9",
    "experiment_freeze_sha256": "sha256:00d5394afbd87cf6eba736ddd0ae4873a95dcff163d011297fd0c8ccab5860bb",
    "pre_review_state_sha256": "sha256:cbf7d79535dfdf618d7ea5b9acb9fc15d6b5d0815efdc9e7ef01371c272c995f",
    "instance_tree_sha256": "sha256:36ac6b91cbd4bb6446f12fff4048b1f51ac0d60c4c35ad1372b053b460fae63c",
    "capture_tree_sha256": "sha256:796259c3362c552ffa85cdde02ef58946136ed6f16d7ada05527215706d0aa5e",
    "package_record_tree_sha256": "sha256:d53a286bf169d6c30c26999ca91d2af52bb1619b7fc8471bc3c10b5c926f8bc6",
    "package_tree_sha256": "sha256:fd675d12a4e71ece339b8abc9d3c942ee2e174b8b293ca1c775aa4c63bd0237f",
    "review_design_sha256": "sha256:256038aaa414b650ba971ffbf06f4e410e111ee53ade6ed922b9c0721a672f20",
    "repair_design_sha256": "sha256:503f83d792c163a644f05ed9469240ded102c46e83a81dfa52a26e8e2126d910",
}
N13_FIRST_REVIEW = {
    "trial_id": "trial-000-639fb9a3fb1db2fb",
    "call_id": "call-000-9f79d4fc8bf4ac6b",
    "call_record_file_sha256": "sha256:95c767995bbcdea234fd17303b37095351b4b0e50c03acb9b3fd132a72c3bb65",
    "logical_request_sha256": "sha256:69f0463674dac6f0078fe9ccedc37c01095d07945eb27e68561941dd5dc76a70",
    "prompt_sha256": "sha256:1cdaf6bf4f088a5452790ba13bb3a652bb3e3f79239452c26795a896aaae4243",
    "response_sha256": "sha256:b5a6d6125ebc841a6f3cd1c3d9a315b2fd26941542ef26278ce01223903ced95",
}
N13_RESUME_EVENT_HASHES = {
    "ledger/resume-event/resume-000.json": "sha256:677619cb4202f34a75b74c4b73b9442a1a5532fb68763150bc9c1d87f1cea0b6",
    "ledger/resume-event/resume-001.json": "sha256:0ae87cac94202ad462aa217cc39b049a1859140687b753f746d462230c283b3c",
}
N12_TEST_COMMANDS = {
    "focused": "PYTHONPATH=src .venv/bin/python -m unittest tests.test_n10_program tests.test_n06_v22 -v",
    "full": "PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v",
}
N12_GOVERNED_PATHS = (
    "pyproject.toml",
    "src/use_case_icp/n10_program.py",
    "src/use_case_icp/n07_program.py",
    "src/use_case_icp/n05_runner.py",
    "src/use_case_icp/fault_v21.py",
    "src/use_case_icp/random_control.py",
    "src/use_case_icp/__main__.py",
    "tests/test_n10_program.py",
    "tests/test_n06_v22.py",
    "prompts/v2_2/fault_chain_authoring.md",
    "prompts/v2_2/fault_chain_stabilization.md",
    "schemas/v2_2/fault_chain_authoring.schema.json",
    "schemas/v2_2/fault_instance.schema.json",
)


def _canonical_protocol_hash(protocol: dict[str, Any]) -> str:
    value = deepcopy(protocol)
    value["integrity"].pop("content_hash", None)
    for item in value["normative_artifacts"]:
        item.pop("sha256", None)
    for name in ("contract_arm_isolation", "contract_launch_policy"):
        value["namespace_registry"]["contracts"][name].pop("sha256", None)
    return sha256_bytes(canonical_json(value))


def _validate_n12_bindings(repo_root: Path) -> dict[str, Any]:
    if sha256_file(repo_root / N12_TASK) != N12_TASK_SHA256:
        raise ValueError("N12 controlling task hash mismatch")
    if sha256_file(repo_root / N12_AUTHORIZATION) != N12_AUTHORIZATION_SHA256:
        raise ValueError("N12 controlling authorization hash mismatch")
    protocol = _load_json(repo_root / PROTOCOL_JSON)
    if (
        protocol.get("integrity", {}).get("content_hash") != PROTOCOL_CONTENT_SHA256
        or _canonical_protocol_hash(protocol) != PROTOCOL_CONTENT_SHA256
    ):
        raise ValueError("N12 amended protocol content hash mismatch")
    phase_a = verify_accepted_phase_a(repo_root)
    return {
        "task_sha256": N12_TASK_SHA256,
        "authorization_sha256": N12_AUTHORIZATION_SHA256,
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "accepted_phase_a_sha256": phase_a["phase_a_sha256"],
        "accepted_phase_a_tree_sha256": phase_a["phase_a_tree_sha256"],
    }


def validate_n10_bindings(repo_root: Path) -> dict[str, Any]:
    current = max(
        (repo_root / "instructions_between_agent_types/developer/current").glob("*.email.md"),
        key=lambda path: path.stat().st_mtime_ns,
    )
    if current.resolve() != (repo_root / N14_TASK).resolve():
        raise ValueError(f"N14 is no longer the latest developer task: {current.name}")
    if sha256_file(current) != N14_TASK_SHA256:
        raise ValueError("N14 current task hash mismatch")
    if sha256_file(repo_root / N14_AUTHORIZATION) != N14_AUTHORIZATION_SHA256:
        raise ValueError("N14 current authorization hash mismatch")
    if sha256_file(repo_root / N13_TASK) != N13_TASK_SHA256:
        raise ValueError("N13 retained task hash mismatch")
    if sha256_file(repo_root / N13_AUTHORIZATION) != N13_AUTHORIZATION_SHA256:
        raise ValueError("N13 controlling authorization hash mismatch")
    original = _validate_n12_bindings(repo_root)
    return {
        "task_sha256": N13_TASK_SHA256,
        "authorization_sha256": N13_AUTHORIZATION_SHA256,
        "current_task_sha256": N14_TASK_SHA256,
        "current_authorization_sha256": N14_AUTHORIZATION_SHA256,
        "n12_task_sha256": original["task_sha256"],
        "n12_authorization_sha256": original["authorization_sha256"],
        "protocol_content_sha256": original["protocol_content_sha256"],
        "accepted_phase_a_sha256": original["accepted_phase_a_sha256"],
        "accepted_phase_a_tree_sha256": original["accepted_phase_a_tree_sha256"],
    }


def _run_evidence_contract(repo_root: Path, run_root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(value for value in run_root.rglob("*") if value.is_file()):
        relative = path.relative_to(run_root).as_posix()
        if relative.startswith("readiness/n12-readiness") and relative.endswith(".json"):
            continue
        files.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "root": run_root.relative_to(repo_root).as_posix(),
        "files": files,
        "tree_sha256": sha256_bytes(canonical_json(files)),
    }


def _qualification_operation_audit(run_root: Path) -> dict[str, Any]:
    instances = [_load_json(path) for path in sorted((run_root / "instances").glob("*.json"))]
    captures = [_load_json(path) for path in sorted((run_root / "captures").glob("*.json"))]
    packages = [_load_json(path) for path in sorted((run_root / "package-records").glob("*.json"))]
    reviews = [_load_json(path) for path in sorted((run_root / "reviews").glob("*.json"))]
    repairs = [_load_json(path) for path in sorted((run_root / "repairs").glob("*.json"))]
    controls = [value for value in instances if value.get("designation") == "no_injection_control"]
    faults = [value for value in instances if value.get("designation") == "faulty"]
    if (
        (len(instances), len(captures), len(packages), len(reviews), len(repairs))
        != (12, 12, 96, 288, 180)
        or len(controls) != 2
        or len(faults) != 10
        or any(value.get("mutation") is not None for value in controls)
        or any(value.get("mutation") is None for value in faults)
    ):
        raise ValueError("N12 qualification operation audit has incorrect membership")
    capture_by_instance = {value["instance_id"]: value for value in captures}
    if len({canonical_json(value["source_sha256"]) for value in instances}) != 12:
        raise ValueError("N12 qualification reused an authored source bundle")
    if any(
        value.get("instance_capture_sha256")
        != capture_by_instance[value["instance_id"]]["capture_sha256"]
        or value.get("verified") is not True
        for value in packages
    ):
        raise ValueError("N12 package provenance is not owning-capture exact")
    if any(not value.get("jobs") or "oracle" in value for value in captures):
        raise ValueError("N12 capture is incomplete or contains restricted oracle truth")
    return {
        "status": "passed",
        "distinct_authored_sources": 12,
        "distinct_canonical_captures": 12,
        "controls": 2,
        "scheduled_faults": 10,
        "verified_owning_instance_packages": 96,
        "validated_reviews": 288,
        "operational_repairs": 180,
    }


def _test_contracts(repo_root: Path, run_root: Path) -> list[dict[str, Any]]:
    contracts = []
    for name, command in N12_TEST_COMMANDS.items():
        path = run_root / "readiness" / N12_TEST_OUTPUT_DIR / f"{name}.txt"
        text = path.read_text(errors="replace")
        match = re.search(r"Ran (\d+) tests? in ", text)
        if not match or not text.rstrip().endswith("OK") or "FAILED" in text or "skipped=" in text:
            raise ValueError(f"N12 {name} test output is not a zero-skip pass")
        contracts.append(
            {
                "name": name,
                "command": command,
                "tests_run": int(match.group(1)),
                "failures": 0,
                "errors": 0,
                "skips": 0,
                "output_path": path.relative_to(repo_root).as_posix(),
                "output_sha256": sha256_file(path),
            }
        )
    return contracts


def _readiness_path(root: Path) -> Path:
    return root / N12_QUALIFICATION_RELATIVE / "readiness" / N12_READINESS_NAME


def _validate_n10_readiness(repo_root: Path, path: Path) -> dict[str, Any]:
    record = _load_json(path)
    unsigned = dict(record)
    observed = unsigned.pop("readiness_sha256", None)
    if observed != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("N12 readiness content hash mismatch")
    if (
        record.get("status") != "ready"
        or record.get("bindings") != _validate_n12_bindings(repo_root)
        or record.get("observed_counts") != EXPECTED_COUNTS
        or record.get("real_model_calls") != 0
        or record.get("run_evidence") != _run_evidence_contract(repo_root, path.parent.parent)
        or record.get("source_tree", {}).get("tree_sha256")
        != N13_ORIGINAL_SOURCE_TREE_SHA256
    ):
        raise ValueError("N12 readiness binding changed")
    for item in record["governed_files"]:
        expected_before = N13_CHANGED_PATHS_BEFORE.get(item["path"])
        if expected_before is not None:
            if item["sha256"] != expected_before:
                raise ValueError("N13 pre-correction governed source hash changed")
            continue
        if sha256_file(repo_root / item["path"]) != item["sha256"]:
            raise ValueError("N12 governed source changed after readiness")
    for item in record["tests"]:
        if sha256_file(repo_root / item["output_path"]) != item["output_sha256"]:
            raise ValueError("N12 test evidence changed after readiness")
    return record


def _n13_test_contracts(repo_root: Path, run_root: Path) -> list[dict[str, Any]]:
    contracts = []
    for name, command in N12_TEST_COMMANDS.items():
        path = run_root / N13_TEST_OUTPUT_DIR / f"{name}.txt"
        text = path.read_text(errors="replace")
        match = re.search(r"Ran (\d+) tests? in ", text)
        if not match or not text.rstrip().endswith("OK") or "FAILED" in text or "skipped=" in text:
            raise ValueError(f"N13 {name} test output is not a zero-skip pass")
        contracts.append(
            {
                "name": name,
                "command": command,
                "tests_run": int(match.group(1)),
                "failures": 0,
                "errors": 0,
                "skips": 0,
                "output_path": path.relative_to(repo_root).as_posix(),
                "output_sha256": sha256_file(path),
            }
        )
    return contracts


def _verify_n13_frozen_state(repo_root: Path, run_root: Path) -> dict[str, Any]:
    freeze_path = run_root / "experiment-freeze.json"
    freeze = _load_json(freeze_path)
    observed = {
        "experiment_freeze_file_sha256": sha256_file(freeze_path),
        "experiment_freeze_sha256": freeze.get("freeze_sha256"),
        "pre_review_state_sha256": sha256_file(run_root / "state/pre-review-state.json"),
        "instance_tree_sha256": _tree_contract(repo_root, run_root / "instances")["tree_sha256"],
        "capture_tree_sha256": _tree_contract(repo_root, run_root / "captures")["tree_sha256"],
        "package_record_tree_sha256": _tree_contract(repo_root, run_root / "package-records")["tree_sha256"],
        "package_tree_sha256": _tree_contract(repo_root, run_root / "packages")["tree_sha256"],
        "review_design_sha256": freeze.get("review_design_sha256"),
        "repair_design_sha256": freeze.get("repair_design_sha256"),
    }
    if observed != N13_FROZEN_HASHES:
        raise ValueError("N13 frozen attempt-023 hashes changed")
    unsigned_freeze = dict(freeze)
    unsigned_freeze.pop("freeze_sha256", None)
    if sha256_bytes(canonical_json(unsigned_freeze)) != freeze["freeze_sha256"]:
        raise ValueError("N13 original experiment-freeze logical hash changed")
    package_records = [
        _load_json(path)
        for path in sorted((run_root / "package-records").glob("*.json"))
    ]
    package_hashes = [item.get("package_sha256") for item in package_records]
    if (
        len(package_records) != 96
        or sum(item.get("verified") is True for item in package_records) != 96
        or len(set(package_hashes)) != 96
    ):
        raise ValueError("N13 frozen package membership is not 96 verified unique hashes")
    call_path = run_root / "ledger/call-attempt" / f"{N13_FIRST_REVIEW['call_id']}.json"
    call = _load_json(call_path)
    payload = call.get("payload", {})
    branch_id = payload.get("result", {}).get("branch_id")
    prompt_path = run_root / "provider-requests" / N13_FIRST_REVIEW["trial_id"] / "review/prompt.md"
    response_path = run_root / "provider-branches" / str(branch_id) / "output/response.json"
    if (
        sha256_file(call_path) != N13_FIRST_REVIEW["call_record_file_sha256"]
        or payload.get("request_sha256") != N13_FIRST_REVIEW["logical_request_sha256"]
        or sha256_file(prompt_path) != N13_FIRST_REVIEW["prompt_sha256"]
        or sha256_file(response_path) != N13_FIRST_REVIEW["response_sha256"]
    ):
        raise ValueError("N13 preserved first review evidence changed")
    matching_calls = []
    for path in sorted((run_root / "ledger/call-attempt").glob("*.json")):
        candidate = _load_json(path).get("payload", {})
        if (
            candidate.get("parent_id") == N13_FIRST_REVIEW["trial_id"]
            and candidate.get("call_class") == "review"
        ):
            matching_calls.append(candidate.get("call_id"))
    if matching_calls != [N13_FIRST_REVIEW["call_id"]]:
        raise ValueError("N13 first logical review has a replacement or duplicate call")
    for relative, expected in N13_RESUME_EVENT_HASHES.items():
        if sha256_file(run_root / relative) != expected:
            raise ValueError("N13 preserved resume event changed")
    return {
        **observed,
        "package_count": 96,
        "verified_package_count": 96,
        "unique_package_sha256_count": 96,
        "instance_schedule_sha256": sha256_bytes(canonical_json(freeze["instance_schedule"])),
        "first_review": {
            **N13_FIRST_REVIEW,
            "branch_id": branch_id,
            "matching_call_ids": matching_calls,
        },
        "resume_event_hashes": dict(N13_RESUME_EVENT_HASHES),
    }


def _write_or_validate_n13_correction(repo_root: Path, run_root: Path) -> Path:
    path = run_root / N13_CORRECTION_RELATIVE
    frozen = _verify_n13_frozen_state(repo_root, run_root)
    source_tree = _tree_contract(repo_root, repo_root / "src/use_case_icp")
    changes = [
        {
            "path": relative,
            "before_sha256": before,
            "after_sha256": sha256_file(repo_root / relative),
        }
        for relative, before in sorted(N13_CHANGED_PATHS_BEFORE.items())
    ]
    patch_contract = {
        "algorithm": "sha256_of_canonical_changed_path_before_after_contract",
        "changes": changes,
    }
    tests = _n13_test_contracts(repo_root, run_root)
    if path.is_file():
        record = _load_json(path)
        unsigned = dict(record)
        logical_hash = unsigned.pop("correction_sha256", None)
        if (
            logical_hash != sha256_bytes(canonical_json(unsigned))
            or record.get("new_source_tree_sha256") != source_tree["tree_sha256"]
            or record.get("changes") != changes
            or record.get("tests") != tests
        ):
            raise ValueError("N13 post-freeze correction record changed")
        return path
    if list((run_root / "reviews").glob("*.json")) or list((run_root / "repairs").glob("*.json")):
        raise ValueError("N13 correction record must precede resumed review records")
    record = {
        "schema_version": "1",
        "status": "verified_post_freeze_controller_correction",
        "authorization_sha256": N13_AUTHORIZATION_SHA256,
        "task_sha256": N13_TASK_SHA256,
        "original_experiment_freeze_file_sha256": frozen["experiment_freeze_file_sha256"],
        "original_experiment_freeze_sha256": frozen["experiment_freeze_sha256"],
        "original_source_tree_sha256": N13_ORIGINAL_SOURCE_TREE_SHA256,
        "new_source_tree_sha256": source_tree["tree_sha256"],
        "changes": changes,
        "patch_contract": patch_contract,
        "patch_sha256": sha256_bytes(canonical_json(patch_contract)),
        "tests": tests,
        "frozen_state": frozen,
        "zero_package_changes": True,
        "zero_replacement_first_review_calls": True,
        "experimental_review_records_at_correction": 0,
        "experimental_repair_records_at_correction": 0,
    }
    record["correction_sha256"] = sha256_bytes(canonical_json(record))
    create_json_exclusive(path, record)
    return path


def write_n10_readiness(repo_root: Path, run_root: Path, terminal_path: Path) -> Path:
    terminal = _load_json(terminal_path)
    if (
        terminal.get("status") != "completed_experiment_and_analysis"
        or terminal.get("observed_counts") != EXPECTED_COUNTS
        or terminal.get("real_model_calls") != 0
        or terminal.get("accepted_phase_a_sha256") != ACCEPTED_PHASE_A_SHA256
        or terminal.get("accepted_phase_a_tree_sha256") != ACCEPTED_PHASE_A_TREE_SHA256
    ):
        raise ValueError("N12 zero-model lifecycle is not a complete exact-count pass")
    isolation_root = run_root / "readiness/isolation"
    isolation_path = isolation_root / "isolation-dry-run.json"
    isolation = _load_json(isolation_path) if isolation_path.is_file() else run_isolation_dry_run(repo_root, isolation_root)
    record = {
        "schema_version": "1",
        "status": "ready",
        "purpose": "n12_zero_model_production_equivalence_readiness",
        "bindings": validate_n10_bindings(repo_root),
        "qualification_terminal_sha256": sha256_file(terminal_path),
        "governed_files": [_file_contract(repo_root, repo_root / path) for path in N12_GOVERNED_PATHS],
        "source_tree": _tree_contract(repo_root, repo_root / "src/use_case_icp"),
        "experimental_fixture": _tree_contract(
            repo_root,
            repo_root
            / "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/experiment-v1",
        ),
        "tests": _test_contracts(repo_root, run_root),
        "production_isolation": {
            "status": "passed",
            "report_sha256": isolation["report_sha256"],
            "launcher": launch_policy_identity(),
            "sandbox_backend_version": bubblewrap_version(),
        },
        "operation_audit": _qualification_operation_audit(run_root),
        "observed_counts": terminal["observed_counts"],
        "real_model_calls": 0,
        "environment": {
            "python": sys.version.split()[0],
            "etiq_copilot": importlib.metadata.version("etiq-copilot"),
        },
    }
    record["run_evidence"] = _run_evidence_contract(repo_root, run_root)
    record["readiness_sha256"] = sha256_bytes(canonical_json(record))
    path = run_root / "readiness" / N12_READINESS_NAME
    create_json_exclusive(path, record)
    return path


def _create_attempt_record(repo_root: Path, run_root: Path, readiness: dict[str, Any]) -> None:
    previous = repo_root / N10_OUTPUT_RELATIVE / "attempt-022"
    preserved = [f"attempt-{index:03d}" for index in range(1, 23)]
    if any(not (repo_root / N10_OUTPUT_RELATIVE / name).is_dir() for name in preserved):
        raise ValueError("N12 cannot prove preservation of attempts 001 through 010")
    record = {
        "schema_version": "1",
        "status": "authorized_continuous_experiment_attempt",
        "attempt": N12_ATTEMPT,
        "previous_attempt": "attempt-022",
        "previous_terminal_sha256": sha256_file(previous / "terminal.json"),
        "preserved_attempts": preserved,
        "bindings": validate_n10_bindings(repo_root),
        "readiness_sha256": readiness["readiness_sha256"],
        "experimental_reviews_at_creation": 0,
        "experimental_repairs_at_creation": 0,
    }
    record["attempt_record_sha256"] = sha256_bytes(canonical_json(record))
    create_json_exclusive(run_root / "attempt-record.json", record)
    consumption = {
        "schema_version": "1",
        "status": "n12_authority_consumed_for_attempt_023",
        "authorization_sha256": N12_AUTHORIZATION_SHA256,
        "attempt_record_sha256": record["attempt_record_sha256"],
        "readiness_sha256": readiness["readiness_sha256"],
    }
    create_json_exclusive(run_root / "authority-consumption.json", consumption)


def _write_factual_handoff(
    run_root: Path,
    terminal_path: Path,
    governance_bindings: dict[str, Any],
) -> Path:
    path = run_root / "factual-handoff.json"
    if path.is_file():
        return path
    terminal = _load_json(terminal_path)
    if terminal.get("status") != "completed_experiment_and_analysis":
        return terminal_path
    value = {
        "schema_version": "1",
        "status": "completed_experiment_handoff",
        "attempt": N12_ATTEMPT,
        "terminal_sha256": sha256_file(terminal_path),
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "accepted_phase_a_sha256": ACCEPTED_PHASE_A_SHA256,
        "accepted_phase_a_tree_sha256": ACCEPTED_PHASE_A_TREE_SHA256,
        "observed_counts": terminal["observed_counts"],
        "replay_passed": terminal["replay_passed"],
        "release_checksums_verified": terminal["release_checksums_verified"],
        "provider_usage": terminal["provider_usage"],
        "governance_bindings": governance_bindings,
        "interpretation": "none; factual execution handoff only",
    }
    value["handoff_sha256"] = sha256_bytes(canonical_json(value))
    create_json_exclusive(path, value)
    return path


def run_n10_study(repo_root: Path, output_root: Path, *, mode: str) -> Path:
    if mode not in {"check_ready", "qualify_lifecycle", "finalize_readiness", "live"}:
        raise ValueError("unknown N12 controller mode")
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    if output_root != (repo_root / N10_OUTPUT_RELATIVE).resolve():
        raise ValueError("N12 requires the exact append-only output root")
    bindings = validate_n10_bindings(repo_root)
    readiness_path = _readiness_path(output_root)
    readiness = None
    if readiness_path.is_file():
        readiness = _validate_n10_readiness(repo_root, readiness_path)
    if mode == "check_ready":
        if readiness is not None:
            return readiness_path
        path = output_root / "readiness/n12-check-ready.json"
        if not path.is_file():
            create_json_exclusive(path, {"schema_version": "1", "status": "not_ready", "bindings": bindings})
        return path
    qualification_root = output_root / N12_QUALIFICATION_RELATIVE
    if mode == "qualify_lifecycle":
        terminal = qualification_root / "terminal.json"
        if terminal.is_file():
            return terminal
        return _run_lifecycle(
            repo_root,
            qualification_root,
            provider=_qualification_provider(repo_root),
            qualification=True,
            governance_bindings=bindings,
        )
    if mode == "finalize_readiness":
        terminal = qualification_root / "terminal.json"
        if not terminal.is_file():
            raise ValueError("N12 has no complete zero-model lifecycle to finalize")
        return readiness_path if readiness_path.is_file() else write_n10_readiness(repo_root, qualification_root, terminal)
    if readiness is None:
        raise ValueError("N12 live execution requires current zero-model readiness")
    run_root = output_root / N12_ATTEMPT
    terminal = run_root / "terminal.json"
    correction_path = _write_or_validate_n13_correction(repo_root, run_root)
    correction = _load_json(correction_path)
    governance_bindings = {
        **bindings,
        "readiness_sha256": readiness["readiness_sha256"],
        "original_experiment_freeze_file_sha256": N13_FROZEN_HASHES[
            "experiment_freeze_file_sha256"
        ],
        "original_experiment_freeze_sha256": N13_FROZEN_HASHES[
            "experiment_freeze_sha256"
        ],
        "post_freeze_controller_correction_file_sha256": sha256_file(
            correction_path
        ),
        "post_freeze_controller_correction_sha256": correction[
            "correction_sha256"
        ],
    }
    if terminal.is_file():
        _write_factual_handoff(run_root, terminal, governance_bindings)
        return terminal
    if not (run_root / "attempt-record.json").is_file():
        _create_attempt_record(repo_root, run_root, readiness)
    terminal = _run_lifecycle(
        repo_root,
        run_root,
        provider=_live_provider(repo_root, run_root),
        qualification=False,
        governance_bindings=governance_bindings,
    )
    _write_factual_handoff(run_root, terminal, governance_bindings)
    return terminal
