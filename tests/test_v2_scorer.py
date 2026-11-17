import pytest
import re

from rdr.v2_review import SYSTEM_PROMPT_V2
from rdr.v2_schema import TruthV2
from rdr.v2_scorer import ANSWER_SCHEMA_V2, FAULT_CLASSES_V2, score_v2, validate_answer_v2


def _answer(fault_class):
    return {
        "fault_occurred": fault_class is not None,
        "residual_harm_present": False,
        "fault_class": fault_class,
        "root_cause_source_locations": [],
        "root_cause_event_indices": [],
        "historically_affected_artifacts": [],
        "restored_artifacts": [],
        "residual_harmful_artifacts": [],
    }


def test_fault_class_schema_enum_and_validator_have_exactly_the_same_contract():
    allowed = [None, "action", "source", "runtime", "mixed", "interaction", "amplified"]
    assert list(FAULT_CLASSES_V2) == allowed[1:]
    assert ANSWER_SCHEMA_V2["properties"]["fault_class"] == {
        "type": ["string", "null"], "enum": allowed,
    }
    assert [value for value in allowed if validate_answer_v2(_answer(value))] == allowed
    for value in ("wrong-recipient fault", "action fault", "", 0, False):
        with pytest.raises(ValueError, match="invalid fault_class"):
            validate_answer_v2(_answer(value))


def test_root_cause_contract_is_identical_across_prompt_schema_validator_truth_and_score():
    root_fields = {"root_cause_source_locations", "root_cause_event_indices"}
    legacy_fields = {"source_locations", "runtime_events", "first_harmful_event"}
    assert root_fields <= set(ANSWER_SCHEMA_V2["properties"])
    assert root_fields <= set(ANSWER_SCHEMA_V2["required"])
    assert not legacy_fields & set(ANSWER_SCHEMA_V2["properties"])
    assert all(field in SYSTEM_PROMPT_V2 for field in root_fields)
    assert not any(re.search(rf"(?<!root_cause_){field}\b", SYSTEM_PROMPT_V2)
                   for field in legacy_fields)
    answer = _answer("runtime")
    answer["root_cause_event_indices"] = [3]
    validate_answer_v2(answer)
    truth = TruthV2("i", True, True, "R01", "runtime", "unrepaired", [], [3],
                    ["x#1"], [], ["x#1"], "x#1", "codex")
    score = score_v2(answer, truth)
    assert score["root_cause_event_precision"] == 1
    assert score["root_cause_event_recall"] == 1
    assert not legacy_fields & set(score)


def test_multi_cause_scoring():
    truth = TruthV2("i", True, False, "I01", "interaction", "repaired", ["w.py:2"], [3],
                    ["x#1", "x#2"], ["x#1", "x#2"], [], "x#1", "codex")
    answer = {"fault_occurred": True, "residual_harm_present": False,
              "fault_class": "interaction", "root_cause_source_locations": ["w.py:2"],
              "root_cause_event_indices": [3],
              "historically_affected_artifacts": ["x#1"],
              "restored_artifacts": ["x#1", "x#2"], "residual_harmful_artifacts": []}
    score = score_v2(answer, truth)
    assert score["fault_class_hit"] and score["root_cause_source_recall"] == 1
    assert score["root_cause_event_recall"] == 1
    assert score["historical_artifact_precision"] == 1
    assert score["historical_artifact_recall"] == 0.5
    assert score["fault_occurred_correct"] and score["residual_harm_correct"]


def test_clean_truth_cannot_carry_fault_metadata():
    with pytest.raises(ValueError, match="clean truth"):
        TruthV2("clean", False, False, "L01", "action", None, [], [], [], [], [],
                "x#1", "codex")


def test_repaired_truth_distinguishes_restoration_from_residual_harm():
    restored = TruthV2("r1", True, False, "L01", "action", "repaired", [], [2],
                       ["x#1"], ["x#1"], [], "x#1", "codex")
    residual = TruthV2("r2", True, True, "L01", "action", "repaired", [], [2],
                       ["x#1", "y#1"], ["x#1"], ["y#1"], "y#1", "codex")
    assert restored.fault_occurred and not restored.residual_harm_present
    assert residual.fault_occurred and residual.residual_harm_present
