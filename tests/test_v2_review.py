import inspect
import json

import pytest

from rdr.freeze import write_manifest
from rdr.v2_review import (REVIEWER_MODEL, SYSTEM_PROMPT_V2, clean_control_metrics, main, plan_jobs,
                           _record_stage, run_interactive_reviews, run_reviews, smoke_review)


def test_review_plan_is_complete_randomised_and_read_only(tmp_path):
    root = tmp_path / "dry"
    for instance in ("one", "two"):
        packages = root / "instances" / instance / "packages"
        packages.mkdir(parents=True)
        for arm in ("A", "B", "V"):
            (packages / f"{arm}.txt").write_text(f"{instance}-{arm}")
    first = plan_jobs(root, 1)
    second = plan_jobs(root, 2)
    assert len(first) == 6
    assert {(i, a) for i, a, _ in first} == {(i, a) for i, a, _ in second}
    assert [(i, a) for i, a, _ in first] != [(i, a) for i, a, _ in second]
    assert not {"N", "O"} & {arm for _, arm, _ in first}


def test_false_positive_metrics():
    rows = [
        {"arm": "A", "truth_fault_occurred": False, "false_alarm": False,
         "false_fault_class_claim": False},
        {"arm": "A", "truth_fault_occurred": False, "false_alarm": True,
         "false_fault_class_claim": True},
        {"arm": "A", "truth_fault_occurred": True, "false_alarm": False,
         "false_fault_class_claim": False},
    ]
    metrics = clean_control_metrics(rows)
    assert metrics["false_positive_rate"] == 0.5
    assert metrics["specificity"] == 0.5
    assert metrics["false_fault_class_claims"] == 1


def test_smoke_requires_separate_named_directory(tmp_path):
    with pytest.raises(ValueError, match="smoke-"):
        smoke_review(tmp_path, tmp_path / "reviews", "i", "A", REVIEWER_MODEL, "medium")


@pytest.mark.parametrize("condition", [
    "ETIQ_CODE_LINEAGE", "APPWORLD_ETIQ_COMPOSITE",
    "STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH",
])
def test_smoke_cli_accepts_additive_etiq_conditions(condition, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", [
        "v2_review", "smoke", "--instances", "public", "--out", "smoke-v7",
        "--instance", "example", "--arm", condition,
    ])
    monkeypatch.setattr("rdr.v2_review.smoke_review", lambda *args: {"status": "passed"})
    main()
    assert '"status": "passed"' in capsys.readouterr().out


def test_one_shot_and_interactive_transports_are_separate():
    assert REVIEWER_MODEL == "gpt-5.6-sol"
    assert "blocked_arms" not in inspect.getsource(run_reviews)
    source = inspect.getsource(run_interactive_reviews)
    assert "max_expansions=6" in source and "review(" in source


def test_reviewer_prompt_states_the_fault_class_contract():
    for fault_class in ("action", "source", "runtime", "mixed", "interaction", "amplified"):
        assert f"- {fault_class}:" in SYSTEM_PROMPT_V2
    assert "Use null for fault_class when no harmful fault occurred" in SYSTEM_PROMPT_V2
    assert "not a descriptive fault name" in SYSTEM_PROMPT_V2
    assert "root_cause_source_locations" in SYSTEM_PROMPT_V2
    assert "root_cause_event_indices" in SYSTEM_PROMPT_V2


def _staged_roots(tmp_path):
    public = tmp_path / "public"
    (public / "instances" / "v6-a" / "packages").mkdir(parents=True)
    (public / "build_identity.json").write_text(json.dumps({"code_snapshot_id": "test-snapshot"}))
    interactive = public / "interactive" / "v6-a"
    interactive.mkdir(parents=True)
    (interactive / "walk.json").write_text("{}")
    (interactive / "N.initial.txt").write_text("initial")
    (interactive / "O.initial.txt").write_text("initial")
    import hashlib
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    (public / "interactive_job_order.json").write_text(json.dumps({
        "seed": 20261108, "selected_before_reviewer_outputs": True,
        "instances": [{"position": 0, "instance_id": "v6-a",
                       "walk_sha256": sha(interactive / "walk.json"),
                       "N_initial_sha256": sha(interactive / "N.initial.txt"),
                       "O_initial_sha256": sha(interactive / "O.initial.txt")}],
    }))
    (public / "build_identity.json").write_text(json.dumps({"code_snapshot_id": "test-snapshot"}))
    write_manifest(public)
    reviews = tmp_path / "reviews"
    one_shot = reviews / "one_shot"
    one_shot.mkdir(parents=True)
    (one_shot / "result.json").write_text("{}")
    _record_stage(reviews, "one_shot")
    provenance = tmp_path / "reviewer-provenance"
    provenance.mkdir()
    (provenance / "code_provenance.json").write_text(json.dumps({"snapshot_id": "reviewer-test"}))
    write_manifest(provenance)
    return public, reviews, provenance


def test_tampered_one_shot_prevents_n(tmp_path, monkeypatch):
    public, reviews, provenance = _staged_roots(tmp_path)
    monkeypatch.setattr("rdr.v2_review.verify_current_code_snapshot", lambda *args: [])
    monkeypatch.setattr("rdr.v2_review.codex_login_preflight", lambda: {"authenticated": True})
    (reviews / "one_shot" / "result.json").write_text("tampered")
    with pytest.raises(RuntimeError, match="one_shot changed"):
        run_interactive_reviews(public, reviews, "N", REVIEWER_MODEL, "medium",
                                reviewer_provenance=provenance)


def test_tampered_n_prevents_o(tmp_path, monkeypatch):
    public, reviews, provenance = _staged_roots(tmp_path)
    monkeypatch.setattr("rdr.v2_review.verify_current_code_snapshot", lambda *args: [])
    monkeypatch.setattr("rdr.v2_review.codex_login_preflight", lambda: {"authenticated": True})
    n_root = reviews / "N"
    n_root.mkdir()
    (n_root / "result.json").write_text("{}")
    _record_stage(reviews, "N")
    (n_root / "result.json").write_text("tampered")
    with pytest.raises(RuntimeError, match="N changed"):
        run_interactive_reviews(public, reviews, "O", REVIEWER_MODEL, "medium",
                                reviewer_provenance=provenance)


def test_changed_interactive_order_prevents_run(tmp_path, monkeypatch):
    public, reviews, provenance = _staged_roots(tmp_path)
    monkeypatch.setattr("rdr.v2_review.verify_current_code_snapshot", lambda *args: [])
    monkeypatch.setattr("rdr.v2_review.codex_login_preflight", lambda: {"authenticated": True})
    schedule = json.loads((public / "interactive_job_order.json").read_text())
    schedule["instances"][0]["position"] = 1
    (public / "interactive_job_order.json").write_text(json.dumps(schedule))
    write_manifest(public)
    with pytest.raises(RuntimeError, match="interactive order"):
        run_interactive_reviews(public, reviews, "N", REVIEWER_MODEL, "medium",
                                reviewer_provenance=provenance)
