import pytest
from builders import persistent_trace, realistic_trace

from rdr.graph import (Edge, build_graph, call_node, edge_counts, fake_writes, neighbourhood, random_subgraph,
                       rec_node, render, rewire_one, strip_ignored)
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


def _ancestors(graph, writers):
    reverse = {}
    for e in graph.edges:
        reverse.setdefault(e.dst, set()).add(e.src)
    seen, stack = set(writers), list(writers)
    while stack:
        for parent in reverse.get(stack.pop(), ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def _symptom_writers(graph, symptom):
    return {e.src for e in graph.edges if e.kind == "writes" and e.dst == symptom}


def test_fake_writes_is_deterministic_and_only_touches_writes_edges():
    g = build_graph(persistent_trace())
    fake, fraction = fake_writes(g, EXP77, frozenset({call_node(1)}), seed=3)
    again, again_fraction = fake_writes(g, EXP77, frozenset({call_node(1)}), seed=3)
    assert fake.edges == again.edges and fraction == again_fraction
    assert {e for e in fake.edges if e.kind != "writes"} == {e for e in g.edges if e.kind != "writes"}
    assert fake.call_nodes == g.call_nodes and fake.record_nodes == g.record_nodes
    assert 0.5 <= fraction <= 1.0


def test_fake_writes_never_points_the_symptom_at_the_origin_or_its_ancestors():
    g = build_graph(persistent_trace())
    for seed in range(2000):
        fake, _ = fake_writes(g, EXP77, frozenset({call_node(1)}), seed)
        sources = _symptom_writers(fake, EXP77)
        assert sources and sources <= {call_node(0), call_node(4)}, (seed, sources)


def test_fake_writes_every_writes_edge_gets_a_different_source_when_unique():
    g = build_graph(realistic_trace())
    fake, fraction = fake_writes(g, EXP77, frozenset(), seed=5)
    assert fraction == 1.0
    old = {e.dst: e.src for e in g.edges if e.kind == "writes"}
    for e in fake.edges:
        if e.kind == "writes":
            assert e.src != old[e.dst]


def test_fake_writes_on_a_realistic_shape_never_fails_or_touches_the_origin():
    g = build_graph(realistic_trace())
    banned = _ancestors(g, _symptom_writers(g, EXP77)) | {call_node(1)}
    for seed in range(200):
        fake, fraction = fake_writes(g, EXP77, frozenset({call_node(1)}), seed)
        assert fraction >= 0.5
        sources = _symptom_writers(fake, EXP77)
        assert sources and not (sources & banned), (seed, sources)


def test_fake_writes_raises_when_a_symptom_edge_has_no_candidate():
    single = build_graph(_trace(Call(0, "a", "x", {}, {}, [Write("a.t#1", None, {"v": 1})])))
    with pytest.raises(ValueError, match="candidate"):
        fake_writes(single, rec_node("a.t#1"), frozenset(), seed=1)
    g = build_graph(persistent_trace())
    with pytest.raises(ValueError, match="candidate"):
        fake_writes(g, EXP77, frozenset({call_node(0), call_node(4)}), seed=1)


def test_fake_writes_raises_when_less_than_half_the_edges_change():
    two = build_graph(_trace(
        Call(0, "a", "x", {}, {}, [Write("a.t#1", None, {"v": 1})]),
        Call(1, "a", "y", {}, {}, [Write("a.t#1", {"v": 1}, {"v": 2})])))
    with pytest.raises(ValueError, match="fraction"):
        fake_writes(two, rec_node("a.t#none"), frozenset(), seed=1)


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


# ---- carry-over I2: argument keys map to tables, tighter value matching

from rdr.graph import MAX_PRODUCERS, id_key_tables, response_values  # noqa: E402

DOCS = {"venmo": {
    "show_transaction": {"path": "/venmo/transactions/{transaction_id}", "parameters": [{"name": "transaction_id"}]},
    "show_user": {"path": "/venmo/users", "parameters": [{"name": "user_id"}]},
    "update_comment": {"path": "/venmo/comments/{comment_id}", "parameters": [{"name": "comment_id"}]},
    "draft": {"path": "/venmo/drafts", "parameters": [{"name": "belongs_to_thread_id"}]},
    "show_message": {"path": "/venmo/messages/text/{text_message_id}", "parameters": [{"name": "text_message_id"}]},
    "mystery": {"path": "/venmo/mystery", "parameters": [{"name": "widget_id"}, {"name": "amount"}]},
}}
TABLES = {"venmo.transactions", "venmo.users", "venmo.transaction_comments", "venmo.user_threads",
          "venmo.drafts", "venmo.global_text_messages", "venmo.user_text_messages"}
FKS = {"venmo.drafts": {"belongs_to_thread_id": "venmo.user_threads"}}


def test_id_key_tables_resolves_by_path_suffix_foreign_key_name_and_user_view():
    m = id_key_tables(DOCS, TABLES, FKS)
    assert m["venmo.show_transaction"] == {"transaction_id": "venmo.transactions"}
    assert m["venmo.show_user"] == {"user_id": "venmo.users"}
    assert m["venmo.update_comment"] == {"comment_id": "venmo.transaction_comments"}
    assert m["venmo.draft"] == {"belongs_to_thread_id": "venmo.user_threads"}
    assert m["venmo.show_message"] == {"text_message_id": "venmo.user_text_messages"}
    assert m["venmo.mystery"] == {}


def test_with_id_tables_a_user_id_cannot_read_a_transaction_with_the_same_number():
    trace = _trace(
        Call(0, "venmo", "pay", {}, {"transaction_id": 3}, [Write("venmo.transactions#3", None, {"a": 1})]),
        Call(1, "venmo", "show_user", {"user_id": 3}, {}),
        Call(2, "venmo", "show_transaction", {"transaction_id": 3}, {}))
    tables = id_key_tables(DOCS, TABLES, FKS)
    assert _kinds(build_graph(trace, tables), "reads") == {Edge(rec_node("venmo.transactions#3"), "call:2", "reads")}
    assert Edge(rec_node("venmo.transactions#3"), "call:1", "reads") in build_graph(trace).edges


def test_numbers_in_responses_count_only_under_id_keys_except_bare_scalars():
    assert response_values({"count": 101, "transaction_id": 7}) == {"7"}
    assert response_values(101) == {"101"} and response_values("ab") == {"ab"}
    g = build_graph(_trace(Call(0, "a", "count", {}, {"count": 101}),
                           Call(1, "a", "show", {"transaction_id": 101}, {})))
    assert not _kinds(g, "feeds")
    g = build_graph(_trace(Call(0, "a", "make", {}, 101), Call(1, "a", "show", {"transaction_id": 101}, {})))
    assert Edge("call:0", "call:1", "feeds") in g.edges


def test_short_strings_under_id_keys_and_numeric_strings_match():
    g = build_graph(_trace(Call(0, "a", "make", {}, {"code_id": "7"}), Call(1, "a", "use", {"code_id": 7}, {})))
    assert Edge("call:0", "call:1", "feeds") in g.edges
    g = build_graph(_trace(Call(0, "a", "make", {}, {"name": "ab"}), Call(1, "a", "use", {"name": "ab"}, {})))
    assert not _kinds(g, "feeds")


def test_values_returned_by_too_many_calls_do_not_feed():
    common = [Call(i, "a", "list", {}, {"owner_id": 5}) for i in range(MAX_PRODUCERS + 1)]
    g = build_graph(_trace(*common, Call(MAX_PRODUCERS + 1, "a", "use", {"owner_id": 5}, {})))
    assert not _kinds(g, "feeds")
    few = common[:MAX_PRODUCERS]
    g = build_graph(_trace(*few, Call(MAX_PRODUCERS, "a", "use", {"owner_id": 5}, {})))
    assert len(_kinds(g, "feeds")) == MAX_PRODUCERS
