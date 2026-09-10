from __future__ import annotations

from pathlib import Path

import pytest

from use_case_icp import n24_experiment as n24


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = ROOT / n24.ATTEMPT


def correction_overlay():
    freeze = n24._json(ATTEMPT / "experiment-freeze.json")
    value = {
        "schema_version": "n24a-provider-schema-correction-1",
        "n24a_task_sha256": n24.N24A_TASK_SHA256,
        "n24a_authority_sha256": n24.N24A_AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"],
        "freeze_file_sha256": "sha256:36b99333f33cd4346775a9526c6087c33e50d4c2f146adf69c584c36640d75a4",
        "package_tree_sha256": freeze["package_tree_sha256"],
        "preserved_review_tree_sha256": "sha256:b52c8ae73606ef17d03a3cc7e88c6e7330187800ce0b7fea30fd891647544f54",
        "live_consumption_file_sha256": "sha256:0eb8509782623f8a9deb40a9cc2adc4596be606b750cae39096dde9b919d5ffe",
        "terminal_incomplete_file_sha256": "sha256:b9abcfa5f72eaa7c1ea1896db37a836683764c0657fed2f685348e288382f958",
        "schema_transitions": {path: {"before_sha256": before, "after_sha256": after} for path, (before, after) in n24.N24A_SCHEMA_TRANSITIONS.items()},
        "before_code_sha256": n24.N24A_BEFORE_CODE_SHA256,
        "after_code_sha256": n24.ce.sha256((ROOT / "src/use_case_icp/n24_experiment.py").read_bytes()),
        "blocked_trial_id": n24.N24A_BLOCKED_TRIAL,
        "failed_attempt_ids": list(n24.N24A_FAILED_CALL_IDS),
        "preserved_review_files": {path.relative_to(ATTEMPT).as_posix(): n24.ce.sha256(path.read_bytes()) for path in sorted((ATTEMPT / "reviews").glob("*.json"))},
    }
    value["correction_sha256"] = n24.ce.sha256(value)
    return value


def test_authorized_schema_hashes_and_const_types():
    hashes = n24.validate_n24_schemas(ROOT)
    for path, (_, after) in n24.N24A_SCHEMA_TRANSITIONS.items():
        assert hashes[path] == after


def test_correction_overlay_verifies_original_freeze_and_all_packages():
    freeze = n24._json(ATTEMPT / "experiment-freeze.json")
    overlay = n24.verify_n24a_correction(ROOT, ATTEMPT, freeze, correction_overlay())
    assert overlay["freeze_sha256"] == "sha256:578b287c860f5fcbfbc6be317d3d53c345bf85e6a0828b0a3f3899da1df06321"
    _, _, _, records = n24._load_frozen(ATTEMPT)
    assert len(records) == 364
    assert sorted(record["package_sha256"] for record in records) == freeze["package_hashes"]


def test_resume_skips_twenty_and_blocked_trial_has_no_response():
    trials = n24._json(ATTEMPT / "review-design.json")["review_trials"]
    completed = [trial for trial in trials if (ATTEMPT / "reviews" / f"{trial['trial_id']}.json").exists()]
    next_trial = next(trial for trial in trials if not (ATTEMPT / "reviews" / f"{trial['trial_id']}.json").exists())
    assert len(completed) == 20
    assert next_trial["trial_id"] == n24.N24A_BLOCKED_TRIAL
    for call_id in n24.N24A_FAILED_CALL_IDS:
        payload = n24.verify_record(ATTEMPT / "ledger", record_type="call-attempt", record_id=call_id)["payload"]
        assert payload["status"] == "failed"
        branch = ATTEMPT / "provider-branches" / payload["result"]["branch_id"]
        assert not (branch / "output/response.json").exists()


def test_existing_review_is_immutable():
    path = sorted((ATTEMPT / "reviews").glob("*.json"))[0]
    before = path.read_bytes()
    with pytest.raises(ValueError, match="append-only"):
        n24.ce._write_immutable(path, {"replacement": True})
    assert path.read_bytes() == before


def test_analysis_requires_complete_schedule(tmp_path):
    with pytest.raises(ValueError, match="1,092"):
        n24.write_analysis(ROOT, tmp_path, [])
