"""Deterministic v2 answer validation and multi-cause scoring."""
from __future__ import annotations

from rdr.v2_schema import TruthV2


FAULT_CLASSES_V2 = ("action", "source", "runtime", "mixed", "interaction", "amplified")


ANSWER_SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "fault_occurred": {"type": "boolean"},
        "residual_harm_present": {"type": "boolean"},
        "fault_class": {"type": ["string", "null"], "enum": [None, *FAULT_CLASSES_V2]},
        "root_cause_source_locations": {"type": "array", "items": {"type": "string"}},
        "root_cause_event_indices": {"type": "array", "items": {"type": "integer"}},
        "historically_affected_artifacts": {"type": "array", "items": {"type": "string"}},
        "restored_artifacts": {"type": "array", "items": {"type": "string"}},
        "residual_harmful_artifacts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fault_occurred", "residual_harm_present", "fault_class",
                 "root_cause_source_locations", "root_cause_event_indices",
                 "historically_affected_artifacts",
                 "restored_artifacts", "residual_harmful_artifacts"],
    "additionalProperties": False,
}


def validate_answer_v2(answer: dict) -> dict:
    keys = set(ANSWER_SCHEMA_V2["properties"])
    if not isinstance(answer, dict) or set(answer) != keys:
        raise ValueError("v2 answer has wrong keys")
    for key in ("fault_occurred", "residual_harm_present"):
        if not isinstance(answer[key], bool):
            raise ValueError(f"{key} must be boolean")
    if answer["fault_class"] not in (None, *FAULT_CLASSES_V2):
        raise ValueError("invalid fault_class")
    for key, item_type in (
        ("root_cause_source_locations", str), ("root_cause_event_indices", int),
        ("historically_affected_artifacts", str), ("restored_artifacts", str),
        ("residual_harmful_artifacts", str),
    ):
        if not isinstance(answer[key], list) or not all(isinstance(item, item_type) and not isinstance(item, bool) for item in answer[key]):
            raise ValueError(f"invalid {key}")
    return answer


def _pr(claimed: set, actual: set) -> tuple[float | None, float | None]:
    precision = None if not claimed else len(claimed & actual) / len(claimed)
    recall = None if not actual else len(claimed & actual) / len(actual)
    return precision, recall


def score_v2(answer: dict, truth: TruthV2) -> dict:
    validate_answer_v2(answer)
    source_precision, source_recall = _pr(
        set(answer["root_cause_source_locations"]),
        set(truth.root_cause_source_locations),
    )
    event_precision, event_recall = _pr(
        set(answer["root_cause_event_indices"]),
        set(truth.root_cause_event_indices),
    )
    historical_precision, historical_recall = _pr(
        set(answer["historically_affected_artifacts"]), set(truth.historically_affected_artifacts))
    restored_precision, restored_recall = _pr(
        set(answer["restored_artifacts"]), set(truth.restored_artifacts))
    residual_precision, residual_recall = _pr(
        set(answer["residual_harmful_artifacts"]), set(truth.residual_harmful_artifacts))
    return {
        "instance_id": truth.instance_id,
        "fault_id": truth.fault_id,
        "repair": truth.repair,
        "author": truth.author,
        "injection_channel": truth.injection_channel,
        "fault_class": truth.fault_class,
        "task_cluster": truth.task_cluster,
        "generator_cluster": truth.generator_cluster,
        "truth_fault_occurred": truth.fault_occurred,
        "truth_residual_harm_present": truth.residual_harm_present,
        "fault_occurred_correct": answer["fault_occurred"] == truth.fault_occurred,
        "residual_harm_correct": answer["residual_harm_present"] == truth.residual_harm_present,
        "detection_correct": (answer["fault_occurred"] == truth.fault_occurred
                              and answer["residual_harm_present"] == truth.residual_harm_present),
        "false_alarm": not truth.fault_occurred and answer["fault_occurred"],
        "false_residual_harm_claim": not truth.residual_harm_present and answer["residual_harm_present"],
        "false_fault_class_claim": not truth.fault_occurred and answer["fault_class"] is not None,
        "fault_class_hit": answer["fault_class"] == truth.fault_class if truth.fault_occurred else answer["fault_class"] is None,
        "root_cause_source_precision": source_precision,
        "root_cause_source_recall": source_recall,
        "root_cause_event_precision": event_precision,
        "root_cause_event_recall": event_recall,
        "historical_artifact_precision": historical_precision,
        "historical_artifact_recall": historical_recall,
        "restored_artifact_precision": restored_precision,
        "restored_artifact_recall": restored_recall,
        "residual_artifact_precision": residual_precision,
        "residual_artifact_recall": residual_recall,
    }
