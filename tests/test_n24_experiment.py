from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from use_case_icp import n24_experiment as n24


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def built():
    return n24.build_attempt(ROOT)


def record_for(mode: str, source: str = "S0", declarations: str = "B0"):
    return next(
        record for record in built()["records"]
        if record["controller_condition"]["instance_id"] == "select_threshold_omission"
        and record["controller_condition"]["mode"] == mode
        and record["controller_condition"]["source_setting"] == source
        and record["controller_condition"]["declaration_setting"] == declarations
    )


def response(**extra):
    value = {
        "fault_detected": True,
        "suspect_job": "job_1",
        "suspect_function": "select_demand",
        "explanation": "visible evidence",
        "cited_evidence": [],
        "usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5, "reasoning_tokens": 2, "total_tokens": 15},
        "request_sha256": "sha256:test",
        "call_ids": [],
        "retry_lineage": [],
        "attempt_count": 1,
    }
    value.update(extra)
    return value


def test_exact_reuse_matrix_schedule_and_schemas():
    value = built()
    assert value["qualification"]["status"] == "passed"
    assert (len(value["records"]), len(value["design"]["review_trials"]), value["design"]["repair_traces"]) == (364, 1092, [])
    assert value["bindings"]["attempt_038_tree_sha256"] == n24.SOURCE_TREE_SHA256
    assert value["qualification"]["pairwise_checks"] == 476


def test_factor_byte_differences_and_initial_evidence_equivalence():
    c05, c06, c07 = (record_for(mode)["reviewer_package"] for mode in ("C05", "C06", "C07"))
    assert n24._initial_evidence(c05) == n24._initial_evidence(c06) == n24._initial_evidence(c07)
    s0, s1 = record_for("C05", "S0", "B0")["reviewer_package"], record_for("C05", "S1", "B0")["reviewer_package"]
    assert set(n24._diff_paths(s0, s1)) and all(path.startswith("$.separate_complete_source_bundle") for path in n24._diff_paths(s0, s1))
    b0, b1 = record_for("C05", "S0", "B0")["reviewer_package"], record_for("C05", "S0", "B1")["reviewer_package"]
    assert set(n24._diff_paths(b0, b1)) and all(path.startswith("$.semantic_declaration_bundle") for path in n24._diff_paths(b0, b1))


def test_required_group_validation_and_real_disclosure():
    value = built(); record = record_for("C06"); package = record["reviewer_package"]
    group = package["graph_review"]["evidence"]["collapsed_execution_groups"][0]["execution_group_id"]
    updated, event = n24._expand_native(value["catalogues"]["select_threshold_omission"], value["indexes"]["select_threshold_omission"], package, group)
    assert event["nodes_added"]
    assert len(updated["graph_review"]["evidence"]["nodes"]) > len(package["graph_review"]["evidence"]["nodes"])
    with pytest.raises(ValueError):
        n24._expand_native(value["catalogues"]["select_threshold_omission"], value["indexes"]["select_threshold_omission"], package, "unavailable")


def test_reconsideration_adds_zero_evidence(monkeypatch, tmp_path):
    calls = []
    def fake(*args, **kwargs):
        calls.append(args[2])
        return response(next_action={"action": "reconsider_same_evidence"}) if len(calls) == 1 else response()
    monkeypatch.setattr(n24, "_provider_review", fake)
    value = built(); record = record_for("C07")
    result = n24.run_review_session(ROOT, tmp_path, value["catalogues"]["select_threshold_omission"], value["indexes"]["select_threshold_omission"], record, "trial-test")
    assert len(calls) == 2
    assert result["operation_events"] == [{"operation": "reconsider_same_evidence", "status": "completed", "evidence_bytes_added": 0}]
    assert calls[0]["reviewer_package"] == calls[1]["reviewer_package"]


def test_scoring_retains_null_unavailable_and_partial_localisation():
    instance = built()["instances"]["select_threshold_omission"]
    package = record_for("C01")["reviewer_package"]
    partial = n24.validate_response(ROOT, package, response(suspect_function=None), n24.FINAL_SCHEMA)
    assert n24.score_response(instance, partial)["correct_job_attribution"]
    assert not n24.score_response(instance, partial)["exact_function_localisation"]
    invented = n24.validate_response(ROOT, package, response(suspect_function="invented_function", cited_evidence=["invented-ref"]), n24.FINAL_SCHEMA)
    assert invented["invalid_evidence_refs"] == ["invented-ref"]
    assert not n24.score_response(instance, invented)["exact_function_localisation"]
    null = n24.validate_response(ROOT, package, response(fault_detected=False, suspect_job=None, suspect_function=None), n24.FINAL_SCHEMA)
    assert not n24.score_response(instance, null)["fault_detected"]


def test_resume_receipt_and_aggregate_reconstruction():
    record = {"call_records": [{"call_ids": ["call-a"]}, {"call_ids": ["call-b"]}], "completed_evidence_expansions": 1, "completed_reconsiderations": 0}
    assert n24.reconstruct_counts([record]) == {"reviews": 1, "repairs": 0, "logical_provider_calls": 2, "provider_attempt_call_ids": 2, "completed_evidence_expansions": 1, "completed_reconsiderations": 0}
    signed = {"initial_receipt": response(), "terminal_receipt": response(), **record}
    before = n24.ce.sha256(signed)
    assert n24.ce.sha256(signed) == before
