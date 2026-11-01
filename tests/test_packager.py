import pytest
from builders import persistent_trace

from rdr.packager import ARMS, LeakageError, build_package, build_rewired_package, check_leakage

SYMPTOM = "splitwise.expenses#77"


def _pkg(arm):
    return build_package(arm, persistent_trace(), SYMPTOM, "i1")


def test_every_arm_has_the_common_header():
    for arm in ARMS:
        text = _pkg(arm)
        assert "A user reports that record splitwise.expenses#77 looks wrong." in text
        assert "CALLS MADE (index and API only)" in text
        assert "\n1 venmo.send_money" in text


def test_arm_a_has_no_log_and_no_graph():
    text = _pkg("A")
    assert "ACTION LOG" not in text and "EDGES" not in text


def test_arm_b_has_the_log_without_tokens():
    text = _pkg("B")
    assert "ACTION LOG" in text and '"transaction_id": 101' in text
    assert "tok-abc" not in text and "EDGES" not in text


def test_arm_c_has_the_full_graph():
    assert _pkg("C").count("-writes->") == 4


def test_arm_d_is_the_symptom_neighbourhood():
    text = _pkg("D")
    assert text.count("-writes->") == 2 and text.count("-reads->") == 1 and text.count("-feeds->") == 1


def test_arm_e_matches_d_edge_counts():
    text = _pkg("E")
    assert text.count("-writes->") == 2 and text.count("-reads->") == 1 and text.count("-feeds->") == 1


def test_arm_f_differs_from_c():
    assert _pkg("F") != _pkg("C")


def test_arm_g_has_the_log_and_the_full_graph():
    text = _pkg("G")
    assert "ACTION LOG" in text and "EDGES" in text
    assert text.count("-writes->") == _pkg("C").count("-writes->")
    assert "tok-abc" not in text


def test_arm_list_includes_g():
    assert ARMS == ("A", "B", "C", "D", "E", "F", "G")


def test_packages_are_deterministic():
    assert [_pkg(a) for a in ARMS] == [_pkg(a) for a in ARMS]


def test_rewired_package_points_symptom_at_decoy():
    text = build_rewired_package(persistent_trace(), SYMPTOM, decoy_index=4)
    assert "call:4 -writes-> rec:splitwise.expenses#77" in text
    assert "call:2 -writes-> rec:splitwise.expenses#77" not in text


def test_leakage_is_rejected():
    trace = persistent_trace()
    trace.instruction = "This run has an injected fault."
    with pytest.raises(LeakageError):
        build_package("A", trace, SYMPTOM, "i1")


def test_check_leakage_is_case_insensitive():
    with pytest.raises(LeakageError):
        check_leakage("GOLD solution")


@pytest.mark.parametrize("text", ["the default setting", "Golden Hour", "a truthful note", "staleness-free",
                                  "unrepaired", "disinjected"])
def test_innocent_words_pass_the_leakage_check(text):
    check_leakage(text)


@pytest.mark.parametrize("text", ["a faulty run", "Repairs made", "GOLD solution", "stale data", "the decoy",
                                  "ground truth", "injected", "fault-free", "repaired."])
def test_forbidden_whole_words_raise(text):
    with pytest.raises(LeakageError):
        check_leakage(text)


def test_forbidden_word_inside_an_action_log_response_is_caught_for_arm_b():
    trace = persistent_trace()
    trace.calls[1].response = {"transaction_id": 101, "note": "faulty gateway"}
    build_package("A", trace, SYMPTOM, "i1")
    with pytest.raises(LeakageError):
        build_package("B", trace, SYMPTOM, "i1")


def test_unknown_arm_raises():
    with pytest.raises(ValueError):
        build_package("Z", persistent_trace(), SYMPTOM, "i1")
