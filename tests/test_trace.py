from builders import persistent_trace

from rdr.trace import Trace


def test_touched_records_in_first_write_order():
    assert persistent_trace().touched_records() == [
        "venmo.transactions#101", "splitwise.expenses#77", "venmo.transactions#201"]


def test_base_values_take_first_before():
    assert persistent_trace().base_values() == {
        "venmo.transactions#101": None,
        "splitwise.expenses#77": {"settled": False, "payment_ref": None},
        "venmo.transactions#201": None,
    }


def test_final_values_take_last_after():
    final = persistent_trace().final_values()
    assert final["venmo.transactions#101"]["status"] == "refunded"
    assert final["splitwise.expenses#77"] == {"settled": True, "payment_ref": 101}


def test_call_name():
    assert persistent_trace().calls[1].name == "venmo.send_money"


def test_round_trip(tmp_path):
    trace = persistent_trace()
    path = tmp_path / "trace.json"
    trace.save(path)
    assert Trace.load(path) == trace
