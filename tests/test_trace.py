import pytest
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


def _with_indices(*indices):
    data = persistent_trace().to_dict()
    data["calls"] = [{**data["calls"][0], "index": i} for i in indices]
    return data


def test_from_dict_accepts_increasing_gappy_indices():
    assert [c.index for c in Trace.from_dict(_with_indices(0, 3, 7)).calls] == [0, 3, 7]


@pytest.mark.parametrize("indices", [(0, 0), (2, 1), (0, 1, 1), (3, 2, 4)])
def test_from_dict_rejects_duplicate_or_decreasing_indices(indices):
    with pytest.raises(ValueError, match="strictly increasing"):
        Trace.from_dict(_with_indices(*indices))
