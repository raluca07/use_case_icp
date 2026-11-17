import hashlib
import json

import pytest

from rdr.freeze import verify_manifest, write_manifest
from rdr.v2_schema import TruthV2, save_v2
from rdr.v2_state_graph_population import freeze_state_graph_schedule
from rdr.v2_state_graph_review import (
    _fake_review,
    analyse_state_graph_reviews,
    run_state_graph_reviews,
    verify_frozen_review_inputs,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_fixture(tmp_path):
    code = tmp_path / "code"
    code.mkdir()
    (code / "code_provenance.json").write_text(json.dumps({"snapshot_id": "snap"}))
    write_manifest(code)
    build = tmp_path / "build"
    public, private = build / "public", build / "private"
    rows = []
    inventory = []
    for index in range(42):
        instance = f"instance-{index:02d}"
        faulty = index >= 10
        truth = TruthV2(
            f"logical-{index:02d}", faulty, faulty,
            "S01" if faulty else None, "source" if faulty else None,
            "repaired" if faulty and index % 2 else "unrepaired" if faulty else None,
            ["workflow.py:1"] if faulty else [], [],
            ["artifact"] if faulty else [], [], ["artifact"] if faulty else [],
            "artifact", "codex" if index % 2 == 0 else "dataset",
        )
        (private / "truth").mkdir(parents=True, exist_ok=True)
        save_v2(truth, private / "truth" / f"{instance}.json")
        packages = public / "instances" / instance / "packages"
        packages.mkdir(parents=True)
        for arm in ("STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH"):
            path = packages / f"{arm}.txt"
            path.write_text(f"package {instance} {arm}\n")
            row = {
                "instance_id": instance, "arm": arm, "package_sha256": sha(path),
                "characters": len(path.read_text()), "utf8_bytes": len(path.read_bytes()),
                "tokens": len(path.read_text().split()), "context_preflight_passed": True,
                "truncated": False,
            }
            rows.append(row)
            inventory.append({
                **row, "logical_instance": truth.instance_id,
                "status": truth.repair or "clean", "fault_id": truth.fault_id,
                "fault_class": truth.fault_class, "repair": truth.repair,
                "author": truth.author, "fault_occurred": truth.fault_occurred,
                "residual_harm_present": truth.residual_harm_present,
                "trace_sha256": "trace", "source_sha256": "source",
            })
    public.mkdir(exist_ok=True)
    (public / "package_manifest.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (public / "state_graph_job_order.json").write_text(
        json.dumps(freeze_state_graph_schedule(rows), indent=2, sort_keys=True)
    )
    (private / "package_size_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True)
    )
    identity = {
        "code_snapshot_id": "snap",
        "code_provenance_manifest_sha256": sha(code / "MANIFEST.sha256.json"),
    }
    (public / "build_identity.json").write_text(json.dumps(identity))
    write_manifest(public)
    write_manifest(private)
    write_manifest(build)
    return build, code


def test_fake_runner_executes_exact_frozen_84_without_private_truth(tmp_path, monkeypatch):
    build, code = frozen_fixture(tmp_path)
    monkeypatch.setattr(
        "rdr.v2_state_graph_review.verify_current_code_snapshot", lambda root: []
    )
    monkeypatch.setattr(
        "rdr.v2_state_graph_review.load_truth",
        lambda *args: (_ for _ in ()).throw(AssertionError("private truth accessed")),
    )
    reviews = tmp_path / "reviews"
    result = run_state_graph_reviews(
        build, reviews, code, review_fn=_fake_review,
        preflight_fn=lambda: {"fake": True, "model_calls": 0},
    )
    assert result["planned"] == result["completed"] == 84
    assert result["private_truth_loaded_during_review"] is False
    assert len(list((reviews / "results").glob("*/*.json"))) == 84
    assert not verify_manifest(reviews)


def test_runner_rejects_schedule_tampering(tmp_path, monkeypatch):
    build, code = frozen_fixture(tmp_path)
    monkeypatch.setattr(
        "rdr.v2_state_graph_review.verify_current_code_snapshot", lambda root: []
    )
    schedule = json.loads((build / "public/state_graph_job_order.json").read_text())
    schedule["jobs"][0]["arm"] = "A"
    (build / "public/state_graph_job_order.json").write_text(json.dumps(schedule))
    write_manifest(build / "public")
    write_manifest(build)
    with pytest.raises(RuntimeError, match="84-job schedule"):
        verify_frozen_review_inputs(build, code)


def test_two_arm_analysis_reports_required_metrics_and_pairs(tmp_path, monkeypatch):
    build, code = frozen_fixture(tmp_path)
    monkeypatch.setattr(
        "rdr.v2_state_graph_review.verify_current_code_snapshot", lambda root: []
    )
    reviews = tmp_path / "reviews"
    run_state_graph_reviews(
        build, reviews, code, review_fn=_fake_review,
        preflight_fn=lambda: {"fake": True, "model_calls": 0},
    )
    monkeypatch.setattr(
        "rdr.v2_state_graph_review.verify_state_graph_population",
        lambda root: {"instances": 42, "packages": 84},
    )
    analysis = analyse_state_graph_reviews(build, reviews, tmp_path / "analysis", code)
    assert analysis["rows"] == 84 and analysis["instances"] == 42
    assert analysis["paired_appworld_versus_etiq"]["pairs"] == 42
    assert set(analysis["by_arm"]) == {"STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH"}
    assert set(analysis["overall"]) >= {
        "fault_occurrence_accuracy", "residual_harm_accuracy", "strict_joint_detection",
        "clean_false_positive_rate", "fault_class_accuracy",
        "root_cause_source_precision", "root_cause_event_recall",
        "historical_artifact_precision", "restored_artifact_recall",
        "residual_artifact_precision",
    }
    assert set(analysis["package_size"]) == {
        "characters_by_arm", "estimated_tokens_by_arm", "actual_input_tokens_by_arm",
    }
