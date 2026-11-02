"""Generic candidate discovery and plans (synthetic traces and API docs)."""
from rdr.inject import VARIANTS, Candidate, find_candidates, repaired_record, wrong_value
from rdr.trace import Call, Trace, Write

DOCS = {
    "music": {
        "update_album_review": {"method": "PATCH", "path": "/music/album_reviews/{review_id}",
                                "parameters": [{"name": "review_id", "required": True},
                                               {"name": "rating", "required": False}]},
        "review_song": {"method": "POST", "path": "/music/songs/{song_id}/reviews",
                        "parameters": [{"name": "song_id", "required": True}, {"name": "rating", "required": True},
                                       {"name": "access_token", "required": True}]},
        "update_song_review": {"method": "PATCH", "path": "/music/song_reviews/{review_id}",
                               "parameters": [{"name": "review_id", "required": True},
                                              {"name": "rating", "required": False},
                                              {"name": "access_token", "required": True}]},
        "like_song": {"method": "POST", "path": "/music/songs/{song_id}/like",
                      "parameters": [{"name": "song_id", "required": True}]},
    },
    "files": {
        "copy_file": {"method": "POST", "path": "/files/file/copy",
                      "parameters": [{"name": "source_file_path", "required": True},
                                     {"name": "destination_file_path", "required": True}]},
        "move_file": {"method": "POST", "path": "/files/file/move",
                      "parameters": [{"name": "source_file_path", "required": True},
                                     {"name": "destination_file_path", "required": True},
                                     {"name": "access_token", "required": True}]},
    },
}
ID_TABLES = {"music.update_song_review": {"review_id": "music.song_reviews"},
             "music.update_album_review": {"review_id": "music.album_reviews"},
             "music.review_song": {"song_id": "music.songs"}, "music.like_song": {"song_id": "music.songs"}}


def _review(index, song, review_id, rating=5):
    return Call(index, "music", "review_song", {"song_id": song, "rating": rating, "access_token": "t"},
                {"review_id": review_id},
                [Write(f"music.song_reviews#{review_id}", None, {"id": review_id, "song_id": song, "rating": rating}),
                 Write(f"music.songs#{song}", {"id": song, "avg": 0}, {"id": song, "avg": rating})])


def _gold():
    return Trace("abc1234_1", "Rate the songs 5", "done", [
        Call(0, "music", "search", {"q": "x"}, [{"song_id": 11}, {"song_id": 12}, {"song_id": 13}]),
        _review(1, 11, 101), _review(2, 12, 102), _review(3, 13, 103),
        Call(4, "music", "like_song", {"song_id": 11}, {}, [Write("music.likes#1", None, {"id": 1, "song_id": 11})]),
        Call(5, "supervisor", "complete_task", {"status": "success"}, {})])


def _by(cands, index, arg):
    return next(c for c in cands if c.index == index and c.arg == arg)


def test_rating_candidate_has_an_update_repair_and_held_consumers():
    cands = find_candidates(_gold(), DOCS, ID_TABLES)
    c = _by(cands, 2, "rating")
    assert (c.gold_value, c.wrong_value, c.table, c.column) == (5, 4, "music.song_reviews", "rating")
    assert c.repair == {"app": "music", "api": "update_song_review", "args": {"rating": 5, "access_token": "t"},
                        "id_param": "review_id", "id_table": "music.song_reviews", "id_match": {"rating": 4}}
    assert c.neutral == {"rating": 5}
    assert c.consumers == [3] and c.held["value"] == 5 and c.held["wrong"] == 4 and c.persistent_capable
    assert _by(cands, 3, "rating").consumers == [] and not _by(cands, 3, "rating").persistent_capable


def test_id_arguments_take_another_id_seen_in_responses_and_unrepairable_writes_are_skipped():
    gold = _gold()
    assert wrong_value(gold, gold.calls[1], "song_id", 11) == 12
    cands = find_candidates(gold, DOCS, ID_TABLES)
    assert not [c for c in cands if c.arg == "song_id"]  # no update API takes song_id
    assert not [c for c in cands if c.api == "like_song"]
    assert not [c for c in cands if c.arg == "access_token"]


def test_plans_share_the_wrong_action_and_differ_in_repair_timing():
    c = _by(find_candidates(_gold(), DOCS, ID_TABLES), 2, "rating")
    plans = {v: c.plan(v) for v in VARIANTS}
    assert {p["value"] for p in plans.values()} == {4} and {p["index"] for p in plans.values()} == {2}
    assert plans["persistent"]["repair"]["timing"] == "before_final" and "held" in plans["persistent"]
    assert plans["clean"]["repair"]["timing"] == "immediate" and "held" not in plans["clean"]
    assert "repair" not in plans["nonpersistent"] and "held" in plans["nonpersistent"]
    assert len({c.instance_id(v) for v in VARIANTS}) == 3 and all(
        "persist" not in c.instance_id(v) and "clean" not in c.instance_id(v) for v in VARIANTS)


def test_repaired_record_is_found_by_the_wrong_value():
    c = _by(find_candidates(_gold(), DOCS, ID_TABLES), 2, "rating")
    faulty = _gold()
    faulty.calls[2] = _review(2, 12, 102, rating=4)
    assert repaired_record(faulty, c) == "music.song_reviews#102"


def _move(index, src, dst, file_id):
    return Call(index, "files", "move_file", {"source_file_path": src, "destination_file_path": dst,
                                              "access_token": "t"}, {"message": "ok"},
                [Write(f"files.files#{file_id}", None, {"id": file_id, "path": dst}),
                 Write(f"files.files#{file_id - 100}", {"id": file_id - 100, "path": src}, None)])


def test_destination_paths_get_a_sibling_directory_a_relocation_repair_and_prefix_consumers():
    gold = Trace("def5678_2", "Move files", "done", [
        Call(0, "files", "list", {"directory_path": "~/inbox/"}, ["~/inbox/a.txt", "~/inbox/b.txt", "~/old/c.txt"]),
        _move(1, "~/inbox/a.txt", "~/archive/a.txt", 201), _move(2, "~/inbox/b.txt", "~/archive/b.txt", 202),
        Call(3, "supervisor", "complete_task", {}, {})])
    c = _by(find_candidates(gold, DOCS, {}), 1, "destination_file_path")
    assert c.wrong_value in ("~/inbox/a.txt", "~/old/a.txt")
    assert c.repair == {"app": "files", "api": "move_file", "args": {
        "source_file_path": c.wrong_value, "destination_file_path": "~/archive/a.txt", "access_token": "t"}}
    assert c.neutral is None and c.consumers == [2] and c.held["mode"] == "prefix"
    assert c.held["value"] == "~/archive/"
    assert not [x for x in find_candidates(gold, DOCS, {}) if x.arg == "source_file_path"]


def test_wrong_value_by_type():
    gold = _gold()
    call = gold.calls[1]
    assert wrong_value(gold, call, "flag", True) is False
    assert wrong_value(gold, call, "amount", 12.5) == 22.5 and wrong_value(gold, call, "amount", 2.0) == 3.0
    assert wrong_value(gold, call, "note", "pay 30 now") == "pay 31 now"
    assert wrong_value(gold, call, "note", "hello") is None
    assert wrong_value(gold, call, "note", "see you soon") == "see you"
    assert wrong_value(gold, call, "file_path", "~/docs/work/a.txt") == "~/docs/a.txt"
    assert wrong_value(gold, call, "count", 1) == 2


def test_candidate_round_trips_to_a_dict():
    c = _by(find_candidates(_gold(), DOCS, ID_TABLES), 2, "rating")
    assert Candidate(**c.to_dict()) == c and c.template == "music.review_song:rating" and c.generator == "abc1234"


def test_update_of_an_existing_review_skips_apis_that_address_another_table():
    gold = _gold()
    gold.calls.insert(4, Call(4, "music", "update_song_review", {"review_id": 101, "rating": 3, "access_token": "t"},
                              {}, [Write("music.song_reviews#101", {"id": 101, "song_id": 11, "rating": 5},
                                         {"id": 101, "song_id": 11, "rating": 3})]))
    c = _by(find_candidates(gold, DOCS, ID_TABLES), 4, "rating")
    assert c.repair["api"] == "update_song_review" and c.repair["id_param"] == "review_id"
