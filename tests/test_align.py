"""Alignment of created rows across runs (carry-over C1, I6, I7)."""
import pytest

from rdr.align import (Schema, align, check_aligned_clean_control, compare, is_side_effect, make_aligned_truth,
                       matched_symptom, resource_table)
from rdr.trace import Call, Trace, Write
from rdr.truth import Partial
from rdr.scorer import score

SCHEMA = Schema(
    foreign_keys={"splitwise.expenses": {"payment_ref": "venmo.transactions"},
                  "venmo.transactions": {}, "venmo.notifications": {},
                  "mail.threads": {}, "mail.emails": {}},
    json_columns={"venmo.notifications": ["data"], "mail.threads": ["email_ids"]})
INSTRUCTION = "Pay ann 5 on Venmo and settle Splitwise expense 77 with that payment."
EXP77 = {"id": 77, "settled": False, "payment_ref": None}


def _pay(index, receiver, txn, note):
    row = {"id": txn, "receiver": receiver, "amount": 5, "status": "completed"}
    return Call(index, "venmo", "send_money", {"receiver": receiver, "amount": 5}, {"transaction_id": txn}, [
        Write(f"venmo.transactions#{txn}", None, row),
        Write(f"venmo.notifications#{note}", None, {"id": note, "data": f'{{"transaction_id": {txn}}}'})])


def _settle(index, before, ref):
    return Call(index, "splitwise", "settle_expense", {"expense_id": 77, "payment_ref": ref}, {"ok": True},
                [Write("splitwise.expenses#77", before, {"id": 77, "settled": True, "payment_ref": ref})])


def _refund(index, txn, receiver):
    before = {"id": txn, "receiver": receiver, "amount": 5, "status": "completed"}
    return Call(index, "venmo", "refund", {"transaction_id": txn}, {"status": "refunded"},
                [Write(f"venmo.transactions#{txn}", before, {**before, "status": "refunded"})])


def gold():
    return Trace("t", INSTRUCTION, "done", [_pay(0, "ann", 201, 9), _settle(1, EXP77, 201)])


def persistent():
    """Pays bob (txn 201, the id ann's payment has in gold), settles with it, refunds it, pays ann (txn 202)."""
    return Trace("t", INSTRUCTION, "done", [_pay(0, "bob", 201, 9), _settle(1, EXP77, 201),
                                            _refund(2, 201, "bob"), _pay(3, "ann", 202, 10)])


def clean():
    trace = persistent()
    trace.calls.append(_settle(4, {"id": 77, "settled": True, "payment_ref": 201}, 202))
    return trace


REFUNDED = {"venmo.transactions#201": Partial({"status": "refunded"})}


def test_toy_expense_is_stale_and_anns_payment_is_not():
    comparison = compare(persistent(), gold(), SCHEMA, REFUNDED)
    assert comparison.stale == ["splitwise.expenses#77"]
    assert comparison.missing == []
    assert comparison.alignment.pairs == {"venmo.transactions#202": "venmo.transactions#201",
                                          "venmo.notifications#10": "venmo.notifications#9"}
    assert comparison.alignment.faulty_only == ["venmo.transactions#201", "venmo.notifications#9"]


def test_toy_clean_control_equals_gold():
    check_aligned_clean_control(clean(), gold(), SCHEMA, REFUNDED)


def test_toy_persistent_is_not_a_clean_control():
    with pytest.raises(ValueError, match="differs from gold"):
        check_aligned_clean_control(persistent(), gold(), SCHEMA, REFUNDED)


def test_side_effect_rows_are_set_aside_and_do_not_count_towards_min_stale():
    comparison = compare(persistent(), gold(), SCHEMA, REFUNDED)
    assert comparison.side_effect == ["venmo.notifications#9"]
    with pytest.raises(ValueError, match="min_stale"):
        make_aligned_truth("i1", persistent(), gold(), SCHEMA, 0, REFUNDED, min_stale=2, expect_faulty=True)
    truth = make_aligned_truth("i1", persistent(), gold(), SCHEMA, 0, REFUNDED, expect_faulty=True)
    assert truth.stale == ["splitwise.expenses#77"] and truth.side_effect == ["venmo.notifications#9"]
    assert truth.symptom == "splitwise.expenses#77" and truth.origin_index == 0


def test_partial_expectation_is_checked():
    wrong = {"venmo.transactions#201": Partial({"status": "completed"})}
    with pytest.raises(ValueError, match="neutralise"):
        compare(persistent(), gold(), SCHEMA, wrong)


def test_without_neutralisation_the_refunded_payment_is_stale():
    assert compare(persistent(), gold(), SCHEMA).stale == ["splitwise.expenses#77", "venmo.transactions#201"]


def test_a_created_row_with_different_content_is_paired_and_stale_under_its_faulty_label():
    nonpersistent = Trace("t", INSTRUCTION, "done", [_pay(0, "bob", 201, 9), _settle(1, EXP77, 201)])
    comparison = compare(nonpersistent, gold(), SCHEMA)
    assert comparison.alignment.pairs["venmo.transactions#201"] == "venmo.transactions#201"
    assert "venmo.transactions#201" not in comparison.alignment.exact
    assert comparison.stale == ["venmo.transactions#201"] and comparison.missing == []


def test_pure_id_shift_is_not_stale():
    shifted = Trace("t", INSTRUCTION, "done", [_pay(0, "ann", 205, 15), _settle(1, EXP77, 205)])
    assert compare(shifted, gold(), SCHEMA).stale == []


def test_ids_inside_json_payload_columns_are_canonicalised():
    def run(email_id):
        return Trace("t", "x", "y", [
            Call(0, "mail", "send", {}, {}, [Write(f"mail.emails#{email_id}", None, {"id": email_id, "body": "hi"})]),
            Call(1, "mail", "thread", {}, {}, [Write("mail.threads#3", {"id": 3, "email_ids": "[1]"},
                                                     {"id": 3, "email_ids": f"[1, {email_id}]"})])])
    assert compare(run(50), run(40), SCHEMA).stale == []
    other = run(50)
    other.calls[1].writes[0].after["email_ids"] = "[1, 2]"
    assert compare(other, run(40), SCHEMA).stale == ["mail.threads#3"]


def test_gold_rows_the_faulty_run_never_created_are_missing():
    only_settle = Trace("t", INSTRUCTION, "done", [_settle(0, EXP77, 7)])
    comparison = compare(only_settle, gold(), SCHEMA)
    assert comparison.missing == ["absent:venmo.transactions#201"]
    assert comparison.stale == ["splitwise.expenses#77"]


def test_matched_symptom_maps_persistent_stale_records_onto_the_clean_twin():
    p, c = persistent(), clean()
    p_cmp = compare(p, gold(), SCHEMA, REFUNDED)
    c_cmp = check_aligned_clean_control(c, gold(), SCHEMA, REFUNDED)
    assert matched_symptom("twin", p_cmp, c_cmp, c, p) == "splitwise.expenses#77"


def test_resource_table_resolves_id_keys_within_the_app():
    tables = {"venmo.transactions", "venmo.users", "spotify.playlists", "todoist.categories"}
    assert resource_table("venmo", "transaction_id", tables) == "venmo.transactions"
    assert resource_table("spotify", "playlist_ids", tables) == "spotify.playlists"
    assert resource_table("todoist", "category_id", tables) == "todoist.categories"
    assert resource_table("venmo", "playlist_id", tables) is None
    assert resource_table("venmo", "id", tables) is None


def test_side_effect_classes():
    pay = Call(0, "venmo", "create_transaction", {}, {})
    assert is_side_effect("venmo.notifications#1", pay)
    assert is_side_effect("venmo.bank_transfers#1", pay)
    assert is_side_effect("gmail.emails#1", pay)
    assert not is_side_effect("venmo.transactions#1", pay)
    assert not is_side_effect("venmo.notifications#1", Call(0, "venmo", "mark_notification", {}, {}))


def test_scorer_neither_rewards_nor_penalises_side_effect_claims():
    truth = make_aligned_truth("i1", persistent(), gold(), SCHEMA, 0, REFUNDED, expect_faulty=True)
    answer = {"anything_wrong": True, "origin_call": 0,
              "still_wrong_records": ["splitwise.expenses#77", "venmo.notifications#9"]}
    result = score(answer, truth)
    assert result["stale_precision"] is None and result["stale_recall"] is None  # only the symptom is stale
    answer["still_wrong_records"].append("venmo.transactions#202")
    assert score(answer, truth)["stale_precision"] == 0.0
