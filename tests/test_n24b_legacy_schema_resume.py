from __future__ import annotations

from pathlib import Path

import pytest

from use_case_icp import n24_experiment as n24


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = ROOT / n24.ATTEMPT
EXPECTED_SCHEMA_HASHES = {
    "schemas/v2_2/n24_final.schema.json": "sha256:1571131d617fe02287c0bee43a570738f69adc405b59c3dd914d7446e5852b89",
    "schemas/v2_2/n24_expand_required.schema.json": "sha256:76bb512c3848430fb972c9a0bab8cf2d8194c231ac0ec1d69feb1b6cd89cae9f",
    "schemas/v2_2/n24_expand_voluntary.schema.json": "sha256:706fcb6ffe456c8d66b6d876b4b15551fc358154d7d76640b2ccf732dc466c70",
    "schemas/v2_2/n24_reconsider.schema.json": "sha256:f4a81159e3302c7f43cd68b19fb8a70add131bbb500da10454cfe23955c40e8d",
    "schemas/v2_2/n24_legacy.schema.json": "sha256:f616c573284935b2ae0b3efcbfdf502669846f728b13cafcbde1aaf6dfccfe38",
}


def overlay():
    freeze = n24._json(ATTEMPT / "experiment-freeze.json")
    value = {
        "schema_version": "n24b-legacy-schema-correction-1",
        "n24b_task_sha256": n24.N24B_TASK_SHA256,
        "n24b_authority_sha256": n24.N24B_AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"],
        "freeze_file_sha256": "sha256:36b99333f33cd4346775a9526c6087c33e50d4c2f146adf69c584c36640d75a4",
        "package_tree_sha256": freeze["package_tree_sha256"],
        "live_consumption_file_sha256": "sha256:0eb8509782623f8a9deb40a9cc2adc4596be606b750cae39096dde9b919d5ffe",
        "n24a_correction_sha256": "sha256:504774861bd91419d640babfec53c12eed6053a7aa7717dae896f03ab29af7fd",
        "n24a_correction_file_sha256": "sha256:f74587673a37cd9a8ee116eda953ad1563212e35444f7c67b9ae0f231aa726a9",
        "preserved_review_tree_sha256": "sha256:b12ba16fbba9ae3fb4ea02f65bd3407101731d6a21802ab6a96f8f47c766c069",
        "terminal_incomplete_file_sha256": "sha256:217dc7b335b30ce07585bf9e8ae2b28e942229ff4c58667f6dcf888186f76dc2",
        "before_code_sha256": n24.N24B_BEFORE_CODE_SHA256,
        "after_code_sha256": n24.ce.sha256((ROOT / "src/use_case_icp/n24_experiment.py").read_bytes()),
        "blocked_trial_id": n24.N24B_BLOCKED_TRIAL,
        "legacy_schema_transition": {"before_sha256": n24.N24B_LEGACY_SCHEMA_TRANSITION[0], "after_sha256": n24.N24B_LEGACY_SCHEMA_TRANSITION[1]},
        "failed_attempt_ids": list(n24.N24B_FAILED_CALL_IDS),
        "preserved_review_files": {path.relative_to(ATTEMPT).as_posix(): n24.ce.sha256(path.read_bytes()) for path in sorted((ATTEMPT / "reviews").glob("*.json"))},
        "strict_schema_audit": {"hashes": n24.validate_n24_schemas(ROOT), "valid_witness_counts": n24.n24_schema_witnesses(ROOT), "status": "passed"},
    }
    value["correction_sha256"] = n24.ce.sha256(value)
    return value


def test_exact_schema_hashes_complete_strict_audit_and_witnesses():
    assert n24.validate_n24_schemas(ROOT) == EXPECTED_SCHEMA_HASHES
    assert n24.n24_schema_witnesses(ROOT) == {
        "schemas/v2_2/n24_final.schema.json": 1,
        "schemas/v2_2/n24_expand_required.schema.json": 1,
        "schemas/v2_2/n24_expand_voluntary.schema.json": 2,
        "schemas/v2_2/n24_reconsider.schema.json": 1,
        "schemas/v2_2/n24_legacy.schema.json": 3,
    }


def test_legacy_inspection_requires_exactly_all_declared_fields():
    schema = n24._json(ROOT / n24.LEGACY_SCHEMA)
    inspection = schema["properties"]["follow_up_requests"]["items"]["properties"]["requests"]["items"]
    assert set(inspection["required"]) == set(inspection["properties"]) == {"node_ref", "inspection", "start", "count", "columns", "query", "include_raw_metadata", "code"}


@pytest.mark.parametrize("kind", ["read", "describe", "full", "python"])
def test_each_inspection_kind_routes_to_existing_operation(monkeypatch, kind):
    seen = []
    def fake(catalogue, package, request, **kwargs):
        seen.append(request)
        return dict(package), {"operation": "artifact_inspection", "status": "completed", "evidence": []}
    monkeypatch.setattr(n24.ce, "perform_n15_operation", fake)
    package = {"available_operations": ["artifact_inspection"], "graph_review": {"evidence": {"nodes": []}}}
    request = {"operation": "artifact_inspection", "execution_group_id": "", "requests": [{"node_ref": "node", "inspection": kind, "start": 0, "count": 1, "columns": [], "query": "", "include_raw_metadata": False, "code": "len(df)" if kind == "python" else ""}]}
    n24._legacy_operation(ROOT, {}, package, {"nodes": []}, {}, request, None)
    assert seen == [request]


def test_ordered_overlays_and_all_frozen_packages_verify():
    freeze = n24._json(ATTEMPT / "experiment-freeze.json")
    n24a = n24.verify_n24a_correction(ROOT, ATTEMPT, freeze, expected_code_sha256=n24.N24B_BEFORE_CODE_SHA256)
    assert n24a["correction_sha256"] == "sha256:504774861bd91419d640babfec53c12eed6053a7aa7717dae896f03ab29af7fd"
    n24b = n24.verify_n24b_correction(ROOT, ATTEMPT, freeze, overlay())
    assert n24b["package_tree_sha256"] == freeze["package_tree_sha256"]
    _, _, _, records = n24._load_frozen(ATTEMPT)
    assert len(records) == 364
    assert sorted(record["package_sha256"] for record in records) == freeze["package_hashes"]


def test_resume_skips_36_immutable_reviews_and_preserves_failed_lineage():
    trials = n24._json(ATTEMPT / "review-design.json")["review_trials"]
    completed = [trial for trial in trials if (ATTEMPT / "reviews" / f"{trial['trial_id']}.json").exists()]
    next_trial = next(trial for trial in trials if not (ATTEMPT / "reviews" / f"{trial['trial_id']}.json").exists())
    assert len(completed) == 36
    assert next_trial["trial_id"] == n24.N24B_BLOCKED_TRIAL
    existing = ATTEMPT / "reviews" / f"{completed[0]['trial_id']}.json"
    before = existing.read_bytes()
    with pytest.raises(ValueError, match="append-only"):
        n24.ce._write_immutable(existing, {"replacement": True})
    assert existing.read_bytes() == before
    for call_id in n24.N24B_FAILED_CALL_IDS:
        payload = n24.verify_record(ATTEMPT / "ledger", record_type="call-attempt", record_id=call_id)["payload"]
        assert payload["status"] == "failed" and payload["parent_id"] == n24.N24B_BLOCKED_TRIAL
        assert not (ATTEMPT / "provider-branches" / payload["result"]["branch_id"] / "output/response.json").exists()
