"""Deterministic per-review scores. No LLM judge."""
from __future__ import annotations

from rdr.answer import normalise_record, validate_answer
from rdr.truth import Truth


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def score(answer: dict, truth: Truth, known_labels=None) -> dict:
    validate_answer(answer)
    symptom = normalise_record(truth.symptom)
    all_claims = {normalise_record(r) for r in answer["still_wrong_records"]}
    known = None if known_labels is None else {normalise_record(r) for r in known_labels}
    side_effect = {normalise_record(r) for r in truth.side_effect}
    claimed = all_claims - {symptom} - side_effect  # side-effect rows are neither hits nor false claims
    actual = {normalise_record(r) for r in truth.stale} - {symptom}
    hits = len(claimed & actual)
    origin = answer["origin_call"]
    return {
        "instance_id": truth.instance_id,
        "detection_correct": answer["anything_wrong"] == truth.is_faulty,
        "origin_hit": (origin == truth.origin_index) if truth.is_faulty else None,
        "stale_precision": _ratio(hits, len(claimed)) if truth.is_faulty else None,
        "stale_recall": _ratio(hits, len(actual)) if truth.is_faulty else None,
        "false_stale_count": None if truth.is_faulty else len(claimed),
        "followed_decoy": (origin == truth.decoy_index) if truth.decoy_index is not None else None,
        "named_symptom": symptom in all_claims,
        "unknown_labels": None if known is None else len(all_claims - known),
    }
