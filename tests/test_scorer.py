import pytest

from rdr.scorer import score
from rdr.truth import Truth

FAULTY = Truth("i1", True, 1, ["splitwise.expenses#77", "todo.items#5"], [], "splitwise.expenses#77")
CLEAN = Truth("i2", False, None, [], [], "venmo.transactions#201")


def test_perfect_answer():
    s = score({"anything_wrong": True, "origin_call": 1,
               "still_wrong_records": ["splitwise.expenses#77", "todo.items#5"]}, FAULTY)
    assert s == {"instance_id": "i1", "detection_correct": True, "origin_hit": True, "stale_precision": 1.0,
                 "stale_recall": 1.0, "false_stale_count": None, "followed_decoy": None}


def test_wrong_origin_and_extra_record():
    s = score({"anything_wrong": True, "origin_call": 3,
               "still_wrong_records": ["todo.items#5", "venmo.transactions#201"]}, FAULTY)
    assert s["origin_hit"] is False and s["stale_precision"] == 0.5 and s["stale_recall"] == 1.0


def test_no_claims_gives_undefined_precision_and_zero_recall():
    s = score({"anything_wrong": True, "origin_call": 1, "still_wrong_records": []}, FAULTY)
    assert s["stale_precision"] is None and s["stale_recall"] == 0.0


def test_clean_control_correctly_passed():
    s = score({"anything_wrong": False, "origin_call": None, "still_wrong_records": []}, CLEAN)
    assert s["detection_correct"] is True and s["origin_hit"] is None and s["false_stale_count"] == 0


def test_clean_control_false_alarm_excludes_symptom():
    s = score({"anything_wrong": True, "origin_call": 2,
               "still_wrong_records": ["venmo.transactions#201", "splitwise.expenses#77"]}, CLEAN)
    assert s["detection_correct"] is False and s["false_stale_count"] == 1


def test_decoy_follow():
    truth = Truth("i3", True, 1, ["splitwise.expenses#77"], [], "splitwise.expenses#77", decoy_index=4)
    assert score({"anything_wrong": True, "origin_call": 4, "still_wrong_records": []}, truth)["followed_decoy"] is True
    assert score({"anything_wrong": True, "origin_call": 1, "still_wrong_records": []}, truth)["followed_decoy"] is False


def test_rec_prefixed_claims_score_like_bare_labels():
    bare = score({"anything_wrong": True, "origin_call": 1,
                  "still_wrong_records": ["splitwise.expenses#77", "todo.items#5"]}, FAULTY)
    prefixed = score({"anything_wrong": True, "origin_call": 1,
                      "still_wrong_records": ["rec:splitwise.expenses#77", " rec:todo.items#5 "]}, FAULTY)
    assert prefixed == bare
    assert prefixed["stale_precision"] == 1.0 and prefixed["stale_recall"] == 1.0


def test_rec_prefixed_symptom_is_excluded_on_clean_controls():
    s = score({"anything_wrong": True, "origin_call": 2,
               "still_wrong_records": ["rec:venmo.transactions#201", "rec:splitwise.expenses#77"]}, CLEAN)
    assert s["false_stale_count"] == 1


def test_truth_labels_are_normalised_too():
    truth = Truth("i4", True, 1, ["rec:splitwise.expenses#77", "todo.items#5"], [], "rec:splitwise.expenses#77")
    s = score({"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["todo.items#5"]}, truth)
    assert s["stale_precision"] == 1.0 and s["stale_recall"] == 1.0


def test_malformed_answer_raises():
    with pytest.raises(ValueError):
        score({"anything_wrong": "yes", "origin_call": 1, "still_wrong_records": []}, FAULTY)
    with pytest.raises(ValueError):
        score({"anything_wrong": True}, FAULTY)
