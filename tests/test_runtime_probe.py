from rdr.runtime_probe import runtime_candidates, sibling_pairs
from rdr.trace import Call, Trace, Write


def test_sibling_pairs_take_the_first_other_value_of_the_same_key():
    response = {"items": [{"id": 3, "name": "a"}, {"id": 5, "name": "b"}, {"id": 4, "name": "a"}]}
    pairs = sibling_pairs(response)
    assert ("id", 3, 4) in pairs and ("id", 5, 3) in pairs and ("name", "a", "b") in pairs
    assert sibling_pairs({"id": 3}) == [] and sibling_pairs([{"id": 3}]) == []


def _trace(second_write_rows: int) -> Trace:
    listing = Call(0, "contacts", "search", {"query": "ann"}, [{"contact_id": 41}, {"contact_id": 42}])
    pay = Call(1, "venmo", "send_money", {"contact_id": 41, "amount": 5}, {"transaction_id": 9},
               [Write("venmo.transactions#9", None, {"contact_id": 41})])
    rows = [Write(f"venmo.notes#{n}", None, {"contact_id": 41}) for n in range(second_write_rows)]
    note = Call(2, "venmo", "add_note", {"contact_id": 41}, {"ok": True}, rows)
    return Trace("t_1", "Pay ann.", "Done.", [listing, pay, note])


def test_a_read_whose_value_reaches_two_written_rows_is_a_candidate():
    found = runtime_candidates("abc_1", _trace(1), None)
    assert found == [{"task": "abc_1", "generator": "abc", "read_index": 0, "key": "contact_id", "value": 41,
                      "alt": 42}]


def test_a_read_whose_value_reaches_one_row_is_not():
    trace = _trace(0)
    trace.calls = trace.calls[:2]
    assert runtime_candidates("abc_1", trace, None) == []
