"""Disposable live AppWorld checks. Each CLI invocation owns and closes one fresh world."""
from __future__ import annotations

import json
import copy
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from rdr.v2_feasibility import DEFAULT_FIXTURE_ROOT
from rdr.v2_dry_run import _real_pair
from rdr.v2_pipeline import validate_execution_pair


def _run(tmp_path: Path, state: str, collateral: bool = False, capture: bool = True) -> dict:
    if not (DEFAULT_FIXTURE_ROOT / "data" / "tasks" / "rdrinv01_1").is_dir():
        pytest.skip("prepared synthetic AppWorld fixture is not installed")
    output = tmp_path / f"{state}-{uuid.uuid4().hex}.json"
    command = [
        sys.executable, "-m", "rdr.v2_feasibility", "--out", str(output),
        "--experiment", "v2-live-test-" + uuid.uuid4().hex,
        "--fixture-root", str(DEFAULT_FIXTURE_ROOT), "--artifact-state", state,
    ]
    if collateral:
        command.append("--inject-collateral")
    if not capture:
        command.append("--no-capture")
    env = dict(os.environ, PYTHONHASHSEED="0")
    subprocess.run(command, check=True, timeout=180, env=env, capture_output=True, text=True)
    return json.loads(output.read_text())


def test_live_all_idempotency_states_and_collateral_rejection(tmp_path):
    for state in ("both", "receipt_only", "request_only"):
        result = _run(tmp_path, state)
        assert result["passed"] and result["evaluation"]["request_count"] in {0, 2}
        assert not result["evaluation"]["delta_shape"]["created"]
    collateral = _run(tmp_path, "clean", collateral=True)
    assert not collateral["passed"]
    assert not collateral["evaluation"]["checks"]["exact_state_delta"]


def test_live_two_world_reference_determinism(tmp_path):
    first = _run(tmp_path, "clean")
    second = _run(tmp_path, "clean")
    assert first["passed"] and second["passed"]
    assert first["trace_sha256"] == second["trace_sha256"]
    assert first["evaluation"]["relevant_state_sha256"] == second["evaluation"]["relevant_state_sha256"]
    assert first["evaluation"]["checks"] == second["evaluation"]["checks"]
    assert first["evaluation"]["score"] == second["evaluation"]["score"]
    assert first["initial_task_state"] == second["initial_task_state"]
    assert first["final_task_state"] == second["final_task_state"]
    assert first["initial_task_state"]["gmail_threads"]
    assert first["final_task_state"]["relevant_payment_requests"]


def test_live_repair_truth_uses_measured_harm_and_complete_restoration():
    if not (DEFAULT_FIXTURE_ROOT / "data" / "tasks" / "rdrinv01_1").is_dir():
        pytest.skip("prepared synthetic AppWorld fixture is not installed")
    source_path = Path("runs/v2/authoring/experiment-ready-20261109/solution.py")
    if not source_path.is_file():
        pytest.skip("qualified Codex workflow source is absent")
    unrepaired, repaired, _, clean = _real_pair(source_path.read_text(), "codex", "L01")
    validation = validate_execution_pair(unrepaired, repaired, clean)
    assert set(validation["harmful_runtime_indices"]).isdisjoint(validation["corrective_call_indices"])
    assert validation["first_harmful_event"] == min(validation["harmful_runtime_indices"])
    assert not any(label.startswith("check:") for label in validation["residual_harmful_artifacts"])
    assert validation["primary_state_restored"]

    partial = copy.deepcopy(repaired)
    repair_index = partial["repair_index"]
    repair_call = next(call for call in partial["trace"]["calls"]
                       if call["index"] >= repair_index and call["writes"])
    repair_call["writes"][0]["after"] = {"deliberately": "partial"}
    partial_validation = validate_execution_pair(unrepaired, partial, clean)
    assert not partial_validation["primary_state_restored"]


def test_live_capture_does_not_change_clean_result(tmp_path):
    captured = _run(tmp_path, "clean")
    plain = _run(tmp_path, "clean", capture=False)
    assert captured["call_count"] > 0 and plain["call_count"] == 0
    assert captured["evaluation"] == plain["evaluation"]
