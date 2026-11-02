from rdr.graph_audit import _path_addresses, classify, feeds_candidates, precision, sentinel_for
from rdr.trace import Call, Trace


def _t(*calls):
    return Trace("t", "i", "m", list(calls))


GOLD = _t(Call(0, "a", "make", {}, {"item_id": 7}), Call(1, "a", "use", {"item_id": 7}, {}))


def test_sentinel_keeps_numbers_numeric():
    assert sentinel_for("7") == "7926" and sentinel_for("ab@c.d") == "ab@c.dq"


def test_classify_verdicts():
    picked = _t(GOLD.calls[0], Call(1, "a", "use", {"item_id": 7926}, {}))
    assert classify(GOLD, picked, 1, "7926") == "confirmed"
    assert classify(GOLD, GOLD, 1, "7926") == "refuted"
    assert classify(GOLD, _t(GOLD.calls[0], Call(1, "a", "use", {"item_id": 8}, {})), 1, "7926") == "changed"
    assert classify(GOLD, _t(GOLD.calls[0], Call(1, "a", "other", {}, {})), 1, "7926") == "diverged"
    assert classify(GOLD, None, 1, "7926") == "diverged"


def test_feeds_candidates_pick_the_most_specific_value():
    trace = _t(Call(0, "a", "list", {}, {"owner_id": 5, "item_id": 7}), Call(1, "a", "list2", {}, {"owner_id": 5}),
               Call(2, "a", "use", {"owner_id": 5, "item_id": 7}, {}))
    rows = feeds_candidates(trace)
    assert {(r["i"], r["j"], r["value"], r["producers"]) for r in rows} == {(0, 2, "7", 1), (1, 2, "5", 2)}


def test_precision_by_cutoff_excludes_diverged():
    rows = [{"producers": 1, "verdict": "confirmed"}, {"producers": 3, "verdict": "refuted"},
            {"producers": 1, "verdict": "diverged"}]
    assert precision(rows, 1)["precision"] == 1.0 and precision(rows, None)["precision"] == 0.5


def test_path_addressed_reads():
    doc = {"path": "/spotify/songs/{song_id}/reviews"}
    assert _path_addresses(doc, "spotify.songs", {"song_id": 4}, "4")
    assert not _path_addresses(doc, "spotify.albums", {"song_id": 4}, "4")
    assert _path_addresses({"path": "/venmo/comments/{comment_id}"}, "venmo.transaction_comments",
                           {"comment_id": 2}, "2")
