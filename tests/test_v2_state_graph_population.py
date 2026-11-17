import json
from pathlib import Path

import pytest

from rdr.freeze import write_manifest
from rdr.v2_faults import FAULT_SPECS
from rdr.v2_state_graph_population import (
    ADMITTED_FAULTS,
    SCHEDULE_SEED,
    V8R11_ROOT,
    _normalized_trace,
    _fresh_pair_job,
    _validate_v8r11_population,
    build_state_graph_population,
    freeze_state_graph_schedule,
    qualify_state_graph_population,
)


def inventory():
    rows = []
    for index in range(42):
        for arm in ("STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH"):
            rows.append({
                "instance_id": f"i-{index:02d}",
                "arm": arm,
                "package_sha256": f"sha-{index}-{arm}",
            })
    return rows


def test_v8r11_logical_population_is_the_frozen_42():
    mapping = _validate_v8r11_population(V8R11_ROOT)
    assert len(mapping) == 42
    assert sum(name.startswith("clean-") for name in mapping) == 10
    for fault_id in ADMITTED_FAULTS:
        assert sum(f"-{fault_id}-" in name for name in mapping) == 4


def test_schedule_has_only_84_state_graph_jobs_and_alternates_first_arm():
    first = freeze_state_graph_schedule(inventory())
    second = freeze_state_graph_schedule(inventory())
    assert first == second
    assert first["seed"] == SCHEDULE_SEED
    assert len(first["jobs"]) == 84
    assert first["first_arm_counts"] == {
        "STATE_APPWORLD_GRAPH": 21,
        "STATE_ETIQ_GRAPH": 21,
    }
    assert {job["arm"] for job in first["jobs"]} == {
        "STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH",
    }
    pairs = [first["jobs"][index:index + 2] for index in range(0, 84, 2)]
    assert all(pair[0]["instance_id"] == pair[1]["instance_id"] for pair in pairs)
    assert [pair[0]["arm"] for pair in pairs[:4]] == [
        "STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH",
        "STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH",
    ]


def test_normalized_trace_ignores_only_established_dynamic_fields():
    left = {"access_token": "one", "created_at": 1, "nested": {"value": 3}}
    right = {"access_token": "two", "created_at": 2, "nested": {"value": 3}}
    assert _normalized_trace(left) == _normalized_trace(right)
    right["nested"]["value"] = 4
    assert _normalized_trace(left) != _normalized_trace(right)


def test_pair_job_passes_source_and_author_in_the_declared_order(monkeypatch):
    observed = []
    monkeypatch.setattr(
        "rdr.v2_state_graph_population._fresh_pair",
        lambda source, author, fault_id, timeout: observed.append(
            (source, author, fault_id, timeout)
        ) or ({}, {}, [], {}),
    )
    result = _fresh_pair_job(("codex", "source text", "M02"), 180)
    assert observed == [("source text", "codex", "M02", 180)]
    assert result[:3] == ("codex", "source text", "M02")


def test_qualification_is_fresh_and_bound_to_exact_snapshot(tmp_path, monkeypatch):
    provenance = tmp_path / "code"
    provenance.mkdir()
    (provenance / "code_provenance.json").write_text(json.dumps({"snapshot_id": "snap"}))
    write_manifest(provenance)
    source = tmp_path / "source.py"
    source.write_text("x = 1\n")
    records = [
        {
            "fault_id": fault_id,
            "status": "qualified",
            "admitted": 1,
            "attempted": 3,
            "inferred_classification": FAULT_SPECS[fault_id].fault_class,
        }
        for fault_id in ADMITTED_FAULTS
    ]
    monkeypatch.setattr(
        "rdr.v2_state_graph_population.verify_current_code_snapshot", lambda root: []
    )
    monkeypatch.setattr(
        "rdr.v2_state_graph_population.qualify_faults", lambda *args, **kwargs: records
    )
    output = tmp_path / "qualification"
    summary = qualify_state_graph_population(output, provenance, source)
    frozen = json.loads((output / "qualification_provenance.json").read_text())
    assert summary["admitted"] == 8
    assert frozen["fresh_execution"] is True
    assert frozen["copied_or_relabelled_qualification"] is False
    assert frozen["code_snapshot_id"] == "snap"
    assert not __import__("rdr.freeze", fromlist=["verify_manifest"]).verify_manifest(output)


def test_full_builder_refuses_overwrite_before_any_execution(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        build_state_graph_population(output, tmp_path / "code", tmp_path / "qualification")
