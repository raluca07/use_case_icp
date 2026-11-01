from builders import persistent_trace

from rdr.graph import (Edge, build_graph, call_node, edge_counts, neighbourhood, random_subgraph, rec_node,
                       render, rewire_one, rewire_writes, strip_ignored)

EXP77 = rec_node("splitwise.expenses#77")
TXN101 = rec_node("venmo.transactions#101")


def test_edges_of_persistent_trace():
    g = build_graph(persistent_trace())
    assert set(g.edges) == {
        Edge("call:1", TXN101, "writes"),
        Edge("call:2", EXP77, "writes"),
        Edge("call:3", TXN101, "writes"),
        Edge("call:4", rec_node("venmo.transactions#201"), "writes"),
        Edge(TXN101, "call:2", "reads"),
        Edge("call:1", "call:2", "feeds"),
        Edge("call:1", "call:3", "feeds"),
    }


def test_call_labels_hide_tokens():
    g = build_graph(persistent_trace())
    assert g.call_nodes["call:1"] == "1 venmo.send_money(amount=5, receiver='bob@x.com')"
    assert "tok-abc" not in render(g)


def test_neighbourhood_two_hops_from_symptom():
    d = neighbourhood(build_graph(persistent_trace()), EXP77, 2)
    assert edge_counts(d) == {"writes": 2, "reads": 1, "feeds": 1}
    assert call_node(3) not in d.call_nodes


def test_random_subgraph_matches_counts_and_is_deterministic():
    g = build_graph(persistent_trace())
    counts = {"writes": 2, "reads": 1, "feeds": 1}
    first = random_subgraph(g, counts, seed=7)
    assert edge_counts(first) == counts
    assert set(first.edges) <= set(g.edges)
    assert first.edges == random_subgraph(g, counts, seed=7).edges


def test_rewire_writes_changes_structure_deterministically():
    g = build_graph(persistent_trace())
    fake = rewire_writes(g, seed=3)
    original_writes = {e for e in g.edges if e.kind == "writes"}
    fake_writes = {e for e in fake.edges if e.kind == "writes"}
    assert fake_writes != original_writes
    assert {e for e in fake.edges if e.kind != "writes"} == {e for e in g.edges if e.kind != "writes"}
    assert fake.edges == rewire_writes(g, seed=3).edges


def test_rewire_one_points_the_record_at_the_decoy():
    fake = rewire_one(build_graph(persistent_trace()), EXP77, call_node(4))
    assert Edge("call:4", EXP77, "writes") in fake.edges
    assert Edge("call:2", EXP77, "writes") not in fake.edges


def test_render_orders_calls_numerically():
    text = render(build_graph(persistent_trace()))
    assert text.index("call:2 =") < text.index("call:3 =")
    assert "call:1 -writes-> rec:venmo.transactions#101" in text


def test_strip_ignored_is_recursive():
    assert strip_ignored({"a": 1, "access_token": "x", "b": [{"password": "p", "c": 2}]}) == {"a": 1, "b": [{"c": 2}]}
