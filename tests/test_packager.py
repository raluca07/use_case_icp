import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from builders import persistent_trace, realistic_trace

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


def _symptom_sources(text):
    return {int(m) for m in re.findall(r"^call:(\d+) -writes-> rec:splitwise\.expenses#77$", text, re.M)}


def test_arm_f_never_points_the_symptom_at_the_origin_or_its_ancestors():
    for n in range(200):
        text = build_package("F", persistent_trace(), SYMPTOM, f"inst{n}", avoid_calls=frozenset({1}))
        sources = _symptom_sources(text)
        assert sources and sources <= {0, 4}, (n, sources)


def test_arm_f_on_a_realistic_shape_never_fails_and_avoids_the_origin():
    for n in range(200):
        text = build_package("F", realistic_trace(), SYMPTOM, f"inst{n}", avoid_calls=frozenset({1}))
        assert _symptom_sources(text) == {0}, n


def test_avoid_calls_is_not_printed():
    with_avoid = build_package("F", realistic_trace(), SYMPTOM, "i1", avoid_calls=frozenset({1}))
    assert "avoid" not in with_avoid.lower()


def test_arm_d_and_e_use_d_hops():
    one = build_package("D", persistent_trace(), SYMPTOM, "i1", d_hops=1)
    assert one.count("-writes->") == 1 and "-reads->" not in one
    assert build_package("D", persistent_trace(), SYMPTOM, "i1") == build_package(
        "D", persistent_trace(), SYMPTOM, "i1", d_hops=2)
    e_one = build_package("E", persistent_trace(), SYMPTOM, "i1", d_hops=1)
    assert e_one.count("-writes->") == 1 and "-reads->" not in e_one


def test_extra_forbidden_is_checked_in_addition():
    trace = persistent_trace()
    trace.instruction = "Pay ann via the Mercury gateway."
    build_package("A", trace, SYMPTOM, "i1")
    with pytest.raises(LeakageError):
        build_package("A", trace, SYMPTOM, "i1", extra_forbidden=re.compile(r"mercury", re.IGNORECASE))


def test_packages_do_not_depend_on_the_hash_seed():
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys, hashlib\n"
        f"sys.path[:0] = [{str(root / 'src')!r}, {str(root / 'tests')!r}]\n"
        "from builders import persistent_trace\n"
        "from rdr.packager import ARMS, build_package\n"
        "text = ''.join(build_package(a, persistent_trace(), 'splitwise.expenses#77', 'i1', "
        "avoid_calls=frozenset({1})) for a in ARMS)\n"
        "print(hashlib.sha256(text.encode()).hexdigest())\n")
    digests = []
    for hash_seed in ("1", "2"):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": hash_seed}, check=True)
        digests.append(out.stdout.strip())
    assert digests[0] == digests[1] and len(digests[0]) == 64


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


def test_forbidden_pattern_is_exactly_the_agreed_one():
    from rdr.packager import FORBIDDEN
    assert FORBIDDEN.pattern == (r"(?<![a-z0-9])(inject[a-z]*|fault[a-z]*|stale|repair[a-z]*|decoy[a-z]*|gold|truth)"
                                 r"(?![a-z])")
    assert FORBIDDEN.flags & re.IGNORECASE


@pytest.mark.parametrize("text", ["gold_run", "is_faulty", "my_stale_rows", "truth_records", "goldRun",
                                  "x.gold", "faulty2", "fault-free", "_gold"])
def test_identifier_style_leaks_raise(text):
    with pytest.raises(LeakageError):
        check_leakage(text)


@pytest.mark.parametrize("text", ["default", "Golden Hour", "golden", "default_is_ok",
                                  "backfault", "overtruth", "9gold", "Stalemate"])
def test_identifier_style_innocents_pass(text):
    check_leakage(text)


def test_final_state_rows_drop_credentials_recursively():
    trace = persistent_trace()
    trace.calls[2].writes[0].after = {"settled": True, "payment_ref": 101,
                                      "owner": {"password": "pw-final-value", "name": "ann"},
                                      "tokens": [{"access_token": "tok-final-value"}]}
    for arm in ARMS:
        text = build_package(arm, trace, SYMPTOM, "i1")
        assert "pw-final-value" not in text and "tok-final-value" not in text
        assert '"name": "ann"' in text


def test_final_state_rows_with_non_json_values_do_not_crash():
    from decimal import Decimal
    trace = persistent_trace()
    trace.calls[2].writes[0].after = {"settled": True, "payment_ref": 101, "amount": Decimal("5.50")}
    assert "5.50" in build_package("A", trace, SYMPTOM, "i1")


def test_call_labels_in_the_graph_drop_nested_credentials():
    trace = persistent_trace()
    trace.calls[1].args["profile"] = {"password": "pw-arg-value", "city": "Leeds"}
    text = build_package("C", trace, SYMPTOM, "i1")
    assert "pw-arg-value" not in text and "Leeds" in text


def test_unknown_arm_raises():
    with pytest.raises(ValueError):
        build_package("Z", persistent_trace(), SYMPTOM, "i1")
