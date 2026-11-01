"""The reviewer's answer shape: schema, validation and record-label normalisation. Shared by runner and scorer."""
from __future__ import annotations

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "anything_wrong": {"type": "boolean"},
        "origin_call": {"type": ["integer", "null"]},
        "still_wrong_records": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["anything_wrong", "origin_call", "still_wrong_records"],
    "additionalProperties": False,
}

_KEYS = frozenset(ANSWER_SCHEMA["properties"])


def validate_answer(answer) -> dict:
    if not isinstance(answer, dict):
        raise ValueError(f"answer must be an object, got {type(answer).__name__}")
    missing = sorted(_KEYS - set(answer))
    if missing:
        raise ValueError(f"answer is missing keys {missing}")
    extra = sorted(set(answer) - _KEYS)
    if extra:
        raise ValueError(f"answer has unexpected keys {extra}")
    if not isinstance(answer["anything_wrong"], bool):
        raise ValueError("anything_wrong must be a boolean")
    origin = answer["origin_call"]
    if origin is not None and (isinstance(origin, bool) or not isinstance(origin, int)):
        raise ValueError("origin_call must be an integer or null")
    records = answer["still_wrong_records"]
    if not isinstance(records, list) or not all(isinstance(r, str) for r in records):
        raise ValueError("still_wrong_records must be a list of strings")
    return answer


def normalise_record(label: str) -> str:
    label = label.strip()
    if label.startswith("rec:"):
        label = label[len("rec:"):]
    return label.strip()
