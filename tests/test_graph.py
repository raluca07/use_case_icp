import pytest
from builders import persistent_trace

from rdr.graph import (Edge, build_graph, call_node, edge_counts, neighbourhood, random_subgraph, rec_node,
                       render, rewire_one, rewire_writes, strip_ignored)
from rdr.trace import Call, Trace, Write

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


def _trace(*calls):
    return Trace("t", "instruction", "done", list(calls))


def _kinds(graph, kind):
    return {e for e in graph.edges if e.kind == kind}


def test_call_labels_hide_tokens():
    trace = persistent_trace()
    trace.calls[1].args["access_token"] = "tok-abc"
    g = build_graph(trace)
    assert g.call_nodes["call:1"] == "1 venmo.send_money(amount=5, receiver='bob@x.com')"
    assert "tok-abc" not in render(g)


def test_ignored_keys_cover_every_credential_name():
    from rdr.graph import IGNORED_KEYS
    assert IGNORED_KEYS == frozenset({"access_token", "refresh_token", "password", "api_key", "otp", "secret"})


@pytest.mark.parametrize("key", ["access_token", "refresh_token", "api_key", "otp", "secret", "password"])
def test_credentials_never_create_feeds_edges(key):
    g = build_graph(_trace(
        Call(0, "venmo", "login", {"username": "me"}, {key: "credential-123"}),
        Call(1, "venmo", "show_profile", {key: "credential-123"}, {"name": "Me"})))
    assert not _kinds(g, "feeds")


def test_page_limit_equal_to_a_response_number_is_not_a_feed():
    g = build_graph(_trace(
        Call(0, "spotify", "count_songs", {}, {"count": 20}),
        Call(1, "spotify", "list_songs", {"page_limit": 20}, {"songs": []})))
    assert not _kinds(g, "feeds")


def test_single_digit_id_under_an_id_key_feeds_and_reads():
    row = {"title": "t"}
    g = build_graph(_trace(
        Call(0, "splitwise", "create_expense", {}, {"expense_id": 7},
             [Write("splitwise.expenses#7", None, row)]),
        Call(1, "splitwise", "show_expense", {"expense_id": 7}, row),
        Call(2, "splitwise", "settle_expense", {"expense_id": 7}, {"ok": True},
             [Write("splitwise.expenses#7", row, {"title": "t", "settled": True})])))
    assert Edge("call:0", "call:1", "feeds") in g.edges
    assert Edge(rec_node("splitwise.expenses#7"), "call:1", "reads") in g.edges
    assert Edge(rec_node("splitwise.expenses#7"), "call:2", "reads") not in g.edges


def test_ids_inside_lists_under_an_id_key_count():
    g = build_graph(_trace(
        Call(0, "splitwise", "create_expense", {}, {"expense_id": 7},
             [Write("splitwise.expenses#7", None, {"a": 1})]),
        Call(1, "splitwise", "bulk_show", {"expense_ids": [7, 8]}, [])))
    assert Edge(rec_node("splitwise.expenses#7"), "call:1", "reads") in g.edges
    assert Edge("call:0", "call:1", "feeds") in g.edges


def test_integral_floats_normalise_to_int_strings():
    g = build_graph(_trace(
        Call(0, "venmo", "send_money", {}, {"transaction_id": 101.0}),
        Call(1, "venmo", "refund", {"transaction_id": 101}, {})))
    assert Edge("call:0", "call:1", "feeds") in g.edges


def test_bools_never_match():
    g = build_graph(_trace(
        Call(0, "a", "x", {}, {"flag": True, "item_id": 1}),
        Call(1, "a", "y", {"is_ok_id": True, "item_id": 1}, {})))
    assert Edge("call:0", "call:1", "feeds") in g.edges
    g2 = build_graph(_trace(Call(0, "a", "x", {}, {"flag": True}), Call(1, "a", "y", {"is_ok_id": True}, {})))
    assert not _kinds(g2, "feeds")


def test_reads_edge_to_a_record_created_later_is_not_emitted():
    g = build_graph(_trace(
        Call(0, "splitwise", "show_expense", {"expense_id": 55}, {}),
        Call(1, "splitwise", "create_expense", {}, {"expense_id": 55},
             [Write("splitwise.expenses#55", None, {"a": 1})]),
        Call(2, "splitwise", "show_expense", {"expense_id": 55}, {"a": 1})))
    reads = _kinds(g, "reads")
    assert reads == {Edge(rec_node("splitwise.expenses#55"), "call:2", "reads")}


def test_reads_edge_to_a_preexisting_record_written_later_is_emitted_before_the_write():
    g = build_graph(_trace(
        Call(0, "splitwise", "show_expense", {"expense_id": 55}, {}),
        Call(1, "splitwise", "settle_expense", {"expense_id": 55}, {},
             [Write("splitwise.expenses#55", {"a": 1}, {"a": 2})])))
    assert Edge(rec_node("splitwise.expenses#55"), "call:0", "reads") in g.edges


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


def test_rewire_writes_raises_when_nothing_can_change():
    single = build_graph(_trace(Call(0, "a", "x", {}, {}, [Write("a.t#1", None, {"v": 1})])))
    with pytest.raises(ValueError, match="rewir"):
        rewire_writes(single, seed=1)


def test_rewire_one_rejects_unknown_decoy_and_existing_writer():
    g = build_graph(persistent_trace())
    with pytest.raises(ValueError, match="call node"):
        rewire_one(g, EXP77, "call:99")
    with pytest.raises(ValueError, match="already"):
        rewire_one(g, EXP77, "call:2")


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
