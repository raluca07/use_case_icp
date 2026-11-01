import pytest
from builders import clean_trace, gold_trace, nonpersistent_trace, persistent_trace

from rdr.trace import Call, Trace, Write
from rdr.truth import Truth, check_clean_control, choose_symptom, make_truth, stale_records

REFUNDED = frozenset({"venmo.transactions#101"})


def test_persistent_fault_leaves_only_the_derived_record_stale():
    assert stale_records(persistent_trace(), gold_trace(), REFUNDED) == (["splitwise.expenses#77"], [])


def test_nonpersistent_fault_marks_wrong_record_and_missing_payment():
    stale, missing = stale_records(nonpersistent_trace(), gold_trace())
    assert stale == ["splitwise.expenses#77", "venmo.transactions#101"]
    assert missing == ["venmo.transactions#201"]


def test_clean_control_matches_gold():
    assert stale_records(clean_trace(), gold_trace(), REFUNDED) == ([], [])
    check_clean_control(clean_trace(), gold_trace(), REFUNDED)


def test_check_clean_control_rejects_a_faulty_run():
    with pytest.raises(ValueError, match="differs from gold"):
        check_clean_control(persistent_trace(), gold_trace(), REFUNDED)


def test_ignore_fields_hides_volatile_values():
    gold = gold_trace()
    faulty = gold_trace()
    gold.calls[2].writes[0].after = {**gold.calls[2].writes[0].after, "updated_at": "t1"}
    faulty.calls[2].writes[0].after = {**faulty.calls[2].writes[0].after, "updated_at": "t2"}
    assert stale_records(faulty, gold, ignore_fields=("updated_at",)) == ([], [])


def test_conflicting_base_values_raise():
    gold = gold_trace()
    faulty = Trace("t1", "x", "y", [Call(0, "splitwise", "settle_expense", {}, {}, [
        Write("splitwise.expenses#77", {"settled": True, "payment_ref": 9}, {"settled": True, "payment_ref": 201})])])
    with pytest.raises(ValueError, match="starting value"):
        stale_records(faulty, gold)


def test_make_truth_for_persistent_fault():
    truth = make_truth("i1", persistent_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED)
    assert truth == Truth("i1", True, 1, ["splitwise.expenses#77"], [], "splitwise.expenses#77", None)


def test_make_truth_for_clean_control_has_no_origin_and_a_seeded_symptom():
    truth = make_truth("i2", clean_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED)
    assert truth.is_faulty is False and truth.origin_index is None and truth.stale == []
    assert truth.symptom in clean_trace().touched_records()
    assert truth.symptom == make_truth("i2", clean_trace(), gold_trace(), 1, REFUNDED).symptom


def test_make_truth_requires_origin_for_faulty_runs():
    with pytest.raises(ValueError, match="origin"):
        make_truth("i3", persistent_trace(), gold_trace(), origin_index=None, neutralised=REFUNDED)


def test_choose_symptom_prefers_first_stale_record():
    assert choose_symptom("i4", ["b#2", "a#1"], persistent_trace()) == "a#1"


def test_truth_round_trip(tmp_path):
    truth = make_truth("i1", persistent_trace(), gold_trace(), 1, REFUNDED, decoy_index=4)
    path = tmp_path / "truth.json"
    truth.save(path)
    assert Truth.load(path) == truth
