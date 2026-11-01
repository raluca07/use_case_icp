"""Deterministic per-review scores. No LLM judge."""
from __future__ import annotations

from rdr.truth import Truth


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def score(answer: dict, truth: Truth) -> dict:
    claimed = set(answer.get("still_wrong_records") or []) - {truth.symptom}
    actual = set(truth.stale) - {truth.symptom}
    hits = len(claimed & actual)
    origin = answer.get("origin_call")
    return {
        "instance_id": truth.instance_id,
        "detection_correct": bool(answer.get("anything_wrong")) == truth.is_faulty,
        "origin_hit": (origin == truth.origin_index) if truth.is_faulty else None,
        "stale_precision": _ratio(hits, len(claimed)) if truth.is_faulty else None,
        "stale_recall": _ratio(hits, len(actual)) if truth.is_faulty else None,
        "false_stale_count": None if truth.is_faulty else len(claimed),
        "followed_decoy": (origin == truth.decoy_index) if truth.decoy_index is not None else None,
    }
