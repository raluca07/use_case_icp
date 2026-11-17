import json
from pathlib import Path

import pytest

from rdr.v2_state_graph_smoke import (
    DEFAULT_ETIQ_PYTHON,
    REQUIRED_STATE_KEYS,
    build_state_graph_smoke,
    validate_task_state_snapshot,
)


def task_state():
    return {
        "gmail_threads": [{"summary": {"subject": "Invoice request: A"}, "detail": {}}],
        "venmo_users_by_email": {"a@example.com": [{"id": 1}]},
        "relevant_payment_requests": [],
        "receipt_files": {"~/Documents/payment_requests/A.txt": None},
    }


def test_task_state_snapshot_schema_is_fixed_and_nonempty():
    assert set(validate_task_state_snapshot(task_state())) == set(REQUIRED_STATE_KEYS)
    bad = task_state()
    bad["gmail_threads"] = []
    with pytest.raises(ValueError, match="qualified task inputs"):
        validate_task_state_snapshot(bad)
    with pytest.raises(ValueError, match="wrong fields"):
        validate_task_state_snapshot({**task_state(), "private_truth": "M02"})


def test_builder_refuses_overwrite_before_execution(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        build_state_graph_smoke(output, tmp_path / "provenance", "M02", "codex")


def test_builder_failure_is_durable_but_never_frozen(tmp_path, monkeypatch):
    output = tmp_path / "failed"
    monkeypatch.setattr("rdr.v2_state_graph_smoke.verify_current_code_snapshot", lambda root: [])
    monkeypatch.setattr(
        "rdr.v2_state_graph_smoke._run_three",
        lambda *args: (_ for _ in ()).throw(RuntimeError("initialization failed")),
    )
    with pytest.raises(RuntimeError, match="initialization failed"):
        build_state_graph_smoke(output, tmp_path / "provenance", "M02", "codex")
    failure = json.loads((output / "private/build_failure.json").read_text())
    assert failure["status"] == "blocked"
    assert failure["root_manifest_written"] is False
    assert not (output / "MANIFEST.sha256.json").exists()


def test_builder_rejects_fault_substitution(tmp_path):
    with pytest.raises(ValueError, match="no substitution"):
        build_state_graph_smoke(tmp_path / "out", tmp_path / "provenance", "S01", "codex")


def test_builder_pins_the_isolated_etiq_interpreter():
    assert DEFAULT_ETIQ_PYTHON == Path(".venv-etiq-pilot/bin/python")
    assert DEFAULT_ETIQ_PYTHON.is_file()
