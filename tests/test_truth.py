import pytest
from builders import clean_trace, gold_trace, nonpersistent_trace, persistent_trace

from rdr.trace import Call, Trace, Write
from rdr.truth import Truth, check_clean_control, choose_symptom, make_truth, stale_records

REFUNDED = {"venmo.transactions#101": {"receiver": "bob@x.com", "amount": 5, "status": "refunded"}}


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
    truth = make_truth("i1", persistent_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED,
                       expect_faulty=True)
    assert truth == Truth("i1", True, 1, ["splitwise.expenses#77"], [], "splitwise.expenses#77", None)


def test_make_truth_for_clean_control_has_no_origin_and_a_seeded_symptom():
    truth = make_truth("i2", clean_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED,
                       expect_faulty=False)
    assert truth.is_faulty is False and truth.origin_index is None and truth.stale == []
    assert truth.symptom in clean_trace().touched_records()
    assert truth.symptom == make_truth("i2", clean_trace(), gold_trace(), 1, REFUNDED,
                                         expect_faulty=False).symptom


def test_make_truth_requires_origin_for_faulty_runs():
    with pytest.raises(ValueError, match="origin"):
        make_truth("i3", persistent_trace(), gold_trace(), origin_index=None, neutralised=REFUNDED,
                   expect_faulty=True)


def test_choose_symptom_picks_a_deterministic_stale_record():
    stale = ["b#2", "a#1", "c#3"]
    assert choose_symptom("i4", stale, persistent_trace()) in stale
    assert choose_symptom("i4", stale, persistent_trace()) == choose_symptom("i4", stale, persistent_trace())
    picks = {choose_symptom(f"inst{n}", stale, persistent_trace()) for n in range(30)}
    assert len(picks) > 1


def test_choose_symptom_raises_when_nothing_was_touched():
    empty = Trace("t1", "x", "y", [])
    with pytest.raises(ValueError, match="touched"):
        choose_symptom("i5", [], empty)


def test_neutralised_record_with_an_unexpected_final_value_raises():
    wrong = {"venmo.transactions#101": {"receiver": "bob@x.com", "amount": 5, "status": "completed"}}
    with pytest.raises(ValueError, match="repair did not neutralise venmo.transactions#101"):
        stale_records(persistent_trace(), gold_trace(), wrong)


def test_neutralised_expected_value_ignores_volatile_fields():
    expected = {"venmo.transactions#101": {"receiver": "bob@x.com", "amount": 5, "status": "refunded",
                                           "updated_at": "later"}}
    assert stale_records(persistent_trace(), gold_trace(), expected, ignore_fields=("updated_at",)) == (
        ["splitwise.expenses#77"], [])


def test_min_stale_rejects_instances_with_too_few_stale_records():
    with pytest.raises(ValueError, match="stale"):
        make_truth("i6", persistent_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED, min_stale=2,
                   expect_faulty=True)
    truth = make_truth("i6", persistent_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED, min_stale=1,
                       expect_faulty=True)
    assert truth.stale == ["splitwise.expenses#77"]


def test_min_stale_does_not_apply_to_clean_controls():
    truth = make_truth("i7", clean_trace(), gold_trace(), origin_index=None, neutralised=REFUNDED, min_stale=2,
                       expect_faulty=False)
    assert truth.is_faulty is False


def test_truth_round_trip(tmp_path):
    truth = make_truth("i1", persistent_trace(), gold_trace(), 1, REFUNDED, decoy_index=4, expect_faulty=True)
    path = tmp_path / "truth.json"
    truth.save(path)
    assert Truth.load(path) == truth


def test_make_truth_requires_expect_faulty():
    with pytest.raises(TypeError):
        make_truth("i8", persistent_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED)


def test_make_truth_rejects_a_faulty_instance_that_was_meant_to_be_clean():
    with pytest.raises(ValueError, match="expect_faulty"):
        make_truth("i8", persistent_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED,
                   expect_faulty=False)


def test_make_truth_rejects_a_clean_instance_that_was_meant_to_be_faulty():
    with pytest.raises(ValueError, match="expect_faulty"):
        make_truth("i9", clean_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED, expect_faulty=True)


def test_min_stale_two_accepts_a_nonpersistent_fault_with_two_stale_records():
    truth = make_truth("i10", nonpersistent_trace(), gold_trace(), origin_index=1, min_stale=2, expect_faulty=True)
    assert truth.stale == ["splitwise.expenses#77", "venmo.transactions#101"]
    assert truth.missing == ["venmo.transactions#201"] and truth.is_faulty
