"""Control arms H to M (Raluca's review, 6 Nov 2026): inputs-only, structure-only and source present/absent."""
import re

import pytest
from builders import persistent_trace, realistic_trace

from rdr.graph import Edge, build_graph, call_node, edge_counts, random_subgraph
from rdr.packager import ALL_ARMS, ARMS, CONTROL_ARMS, build_package

SYMPTOM = "splitwise.expenses#77"
ORIGIN = frozenset({1})


def _pkg(arm, trace=None, instance="i1"):
    return build_package(arm, trace or persistent_trace(), SYMPTOM, instance, avoid_calls=ORIGIN)


def _graph_part(text):
    return text.split("PROVENANCE GRAPH", 1)[1] if "PROVENANCE GRAPH" in text else ""


def test_arm_sets():
    assert CONTROL_ARMS == ("H", "I", "J", "K", "L", "M")
    assert ALL_ARMS == ARMS + CONTROL_ARMS


def test_h_is_the_log_plus_the_fake_graph_of_f():
    h, f = _pkg("H"), _pkg("F")
    assert "ACTION LOG" in h
    assert _graph_part(h) == _graph_part(f)


def test_i_has_arguments_but_no_responses_and_no_graph():
    text = _pkg("I")
    assert "CALL INPUTS" in text and '[1] venmo.send_money({"amount": 5, "receiver": "bob@x.com"})' in text
    inputs = text.split("CALL INPUTS", 1)[1]
    assert " -> " not in inputs and '"status"' not in inputs
    assert "EDGES" not in text and "ACTION LOG" not in text and "tok-abc" not in text


def test_j_has_the_full_graph_without_any_argument():
    j, c = _graph_part(_pkg("J")), _graph_part(_pkg("C"))
    assert j.split("EDGES", 1)[1] == c.split("EDGES", 1)[1]
    assert "call:1 = 1 venmo.send_money\n" in j
    assert "bob@x.com" not in j and "(" not in j


def test_k_is_d_plus_the_origin_and_its_edges():
    k, d = _graph_part(_pkg("K", realistic_trace())), _graph_part(_pkg("D", realistic_trace()))
    assert "call:1 =" in k
    for edge in re.findall(r"^\S+ -\w+-> \S+$", d, re.M):
        assert edge in k
    origin_edges = [e for e in build_graph(realistic_trace()).edges if call_node(1) in (e.src, e.dst)]
    for e in origin_edges:
        assert f"{e.src} -{e.kind}-> {e.dst}" in k


def test_l_contains_the_origin_and_matches_k_edge_counts():
    for n in range(50):
        k = _pkg("K", realistic_trace(), f"i{n}")
        l_text = _pkg("L", realistic_trace(), f"i{n}")
        assert "call:1 =" in _graph_part(l_text), n
        for kind in ("writes", "reads", "feeds"):
            assert k.count(f"-{kind}->") == l_text.count(f"-{kind}->"), (n, kind)


def test_m_is_c_without_the_origin_node_or_any_edge_touching_it():
    m, c = _graph_part(_pkg("M")), _graph_part(_pkg("C"))
    assert "call:1 =" not in m and "call:1 -" not in m and "-> call:1\n" not in m + "\n"
    assert "call:1 =" in c
    kept = [e for e in re.findall(r"^\S+ -\w+-> \S+$", c, re.M) if "call:1 " not in e + " "]
    assert re.findall(r"^\S+ -\w+-> \S+$", m, re.M) == kept
    assert "\n1 venmo.send_money" in _pkg("M")  # the call list in the header is unchanged


@pytest.mark.parametrize("arm", ["K", "L", "M"])
def test_source_arms_need_exactly_one_anchor_call(arm):
    with pytest.raises(ValueError):
        build_package(arm, persistent_trace(), SYMPTOM, "i1")
    with pytest.raises(ValueError):
        build_package(arm, persistent_trace(), SYMPTOM, "i1", avoid_calls=frozenset({1, 2}))


def test_random_subgraph_with_no_required_edges_is_unchanged():
    graph = build_graph(realistic_trace())
    counts = {"writes": 2, "feeds": 1}
    assert random_subgraph(graph, counts, 7).edges == random_subgraph(graph, counts, 7, required=()).edges


def test_random_subgraph_keeps_required_edges_and_counts():
    graph = build_graph(realistic_trace())
    required = [e for e in graph.edges if e.src == call_node(1) and e.kind == "writes"]
    out = random_subgraph(graph, {"writes": len(required) + 1}, 3, required=required)
    assert set(required) <= set(out.edges)
    assert edge_counts(out) == {"writes": len(required) + 1}


def test_random_subgraph_rejects_required_edges_beyond_the_counts():
    graph = build_graph(realistic_trace())
    required = [e for e in graph.edges if e.kind == "writes"][:2]
    with pytest.raises(ValueError):
        random_subgraph(graph, {"writes": 1}, 3, required=required)


def test_required_edge_must_be_in_the_graph():
    graph = build_graph(realistic_trace())
    with pytest.raises(ValueError):
        random_subgraph(graph, {"writes": 1}, 3, required=[Edge("call:9", "rec:x#1", "writes")])


@pytest.mark.parametrize("arm", CONTROL_ARMS)
def test_control_arms_are_deterministic(arm):
    assert _pkg(arm, realistic_trace()) == _pkg(arm, realistic_trace())
