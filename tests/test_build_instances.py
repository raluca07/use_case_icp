"""Instance builder: screen, validation, atomic writes and selection (synthetic traces, fake run results)."""
from types import SimpleNamespace

import pytest

from rdr.align import Schema
from rdr.build_instances import (Built, Excluded, evaluate_variant, nouns, packages_for, screen_guesses, screened,
                                 select, spread, write_instance)
from rdr.inject import Candidate
from rdr.trace import Call, Trace, Write
from rdr.truth import Truth

SCHEMA = Schema(foreign_keys={"music.song_reviews": {"song_id": "music.songs"}}, json_columns={})


def _review(index, song, review_id, rating):
    return Call(index, "music", "review_song", {"song_id": song, "rating": rating}, {"review_id": review_id},
                [Write(f"music.song_reviews#{review_id}", None, {"id": review_id, "song_id": song, "rating": rating})])


def _final(index):
    return Call(index, "supervisor", "complete_task", {"status": "success"}, {})


def _gold():
    return Trace("abc1234_1", "Rate songs 5", "Task completed.",
                 [Call(0, "music", "search_songs", {}, []), _review(1, 11, 101, 5), _review(2, 12, 102, 5),
                  _review(3, 13, 103, 5), _final(4)])


def _candidate(index=2):
    return Candidate("abc1234_1", index, "music", "review_song", "rating", 5, 4, "music.song_reviews", "rating",
                     {"app": "music", "api": "update_song_review", "args": {"rating": 5}, "id_param": "review_id",
                      "id_table": "music.song_reviews", "id_match": {"rating": 4}},
                     {"rating": 5}, {"api": "review_song", "arg": "rating", "value": 5, "wrong": 4, "mode": "equal"},
                     [3], [])


def _repair(index, review_id):
    return Call(index, "music", "update_song_review", {"review_id": review_id, "rating": 5}, {},
                [Write(f"music.song_reviews#{review_id}", {"id": review_id, "song_id": 12, "rating": 4},
                       {"id": review_id, "song_id": 12, "rating": 5})])


def _result(trace, failed=(), repair_index=None, substituted=(3,), succeeded=True, mismatch=None):
    return SimpleNamespace(trace=trace, succeeded=succeeded, failed_calls=list(failed), repair_index=repair_index,
                           substituted=list(substituted), plan_mismatch=mismatch)


def _persistent_trace():
    return Trace("abc1234_1", "Rate songs 5", "x",
                 [Call(0, "music", "search_songs", {}, []), _review(1, 11, 101, 5), _review(2, 12, 102, 4),
                  _review(3, 13, 103, 4), _repair(4, 102), _final(5)])


def test_nouns_drop_verbs_and_plurals():
    assert nouns("review_song") == {"review", "song"} and nouns("song_reviews") == {"song", "review"}
    assert nouns("update_song_review") == {"song", "review"}


def test_screen_names_the_earliest_matching_call_and_drops_only_when_it_is_the_origin():
    trace = _persistent_trace()
    guesses = screen_guesses(trace, "music.song_reviews#103")
    assert guesses == {"symptom_table": 1, "last_call": 1, "rewritten_row": 2}
    assert not screened(guesses, 2) and screened(guesses, 1) and not screened(guesses, None)


def test_persistent_variant_yields_derived_stale_records_with_the_repaired_row_neutralised():
    candidate = _candidate()
    gold = _gold()
    trace = _persistent_trace()
    trace.calls[3] = _review(3, 13, 103, 4)
    trace.calls.insert(4, Call(4, "music", "review_song", {"song_id": 14, "rating": 4}, {},
                               [Write("music.song_reviews#104", None, {"id": 104, "song_id": 14, "rating": 4})]))
    trace.calls[5:] = [_repair(5, 102), _final(6)]
    gold.calls.insert(4, Call(4, "music", "review_song", {"song_id": 14, "rating": 5}, {},
                              [Write("music.song_reviews#104", None, {"id": 104, "song_id": 14, "rating": 5})]))
    gold.calls[5] = _final(5)
    out, truth, _ = evaluate_variant(candidate, "persistent", _result(trace, repair_index=5), gold, SCHEMA)
    assert truth.is_faulty and truth.origin_index == 2
    assert truth.stale == ["music.song_reviews#103", "music.song_reviews#104"]
    assert out.final_message == "Task completed."


def test_persistent_variant_with_one_derived_record_is_excluded_by_min_stale():
    with pytest.raises(Excluded, match="fewer than 2"):
        evaluate_variant(_candidate(), "persistent", _result(_persistent_trace(), repair_index=4), _gold(), SCHEMA)


@pytest.mark.parametrize("kwargs,reason", [
    ({"mismatch": "x"}, "different call"), ({"succeeded": False}, "exception"),
    ({"failed": [2]}, "corrupted call failed"), ({"repair_index": None}, "repair call"),
    ({"failed": [3]}, "other calls fail"), ({"substituted": []}, "no consumer")])
def test_run_level_exclusions(kwargs, reason):
    args = {"repair_index": 4, **kwargs}
    with pytest.raises(Excluded, match=reason):
        evaluate_variant(_candidate(), "persistent", _result(_persistent_trace(), **args), _gold(), SCHEMA)


def test_clean_variant_must_equal_gold():
    clean = Trace("abc1234_1", "Rate songs 5", "x",
                  [Call(0, "music", "search_songs", {}, []), _review(1, 11, 101, 5), _review(2, 12, 102, 4),
                   _repair(3, 102), _review(4, 13, 103, 5), _final(5)])
    _, truth, comparison = evaluate_variant(_candidate(), "clean", _result(clean, repair_index=3, substituted=[]),
                                            _gold(), SCHEMA)
    assert not truth.is_faulty and comparison.stale == []
    with pytest.raises(Excluded, match="clean twin differs"):
        evaluate_variant(_candidate(), "clean", _result(_persistent_trace(), repair_index=4), _gold(), SCHEMA)


def _built(trace, truth, candidate, variant="persistent", iid="abc1234_1_x"):
    return Built(candidate, variant, iid, trace, truth, packages_for(trace, truth, iid, candidate.index, {}), {})


def test_write_instance_is_atomic_and_complete(tmp_path):
    truth = Truth("abc1234_1_x", True, 2, ["music.song_reviews#103"], [], "music.song_reviews#103")
    built = _built(_persistent_trace(), truth, _candidate())
    path = write_instance(tmp_path, built, _gold())
    assert sorted(p.name for p in path.iterdir()) == ["gold_trace.json", "meta.json", "packages", "trace.json",
                                                      "truth.json"]
    assert sorted(p.name for p in (path / "packages").iterdir()) == [f"{a}.txt" for a in "ABCDEFGHIJKLM"]
    assert not list(tmp_path.glob(".staging-*"))


def test_leakage_in_any_arm_excludes_the_instance():
    trace = _persistent_trace()
    trace.instruction = "Rate songs 5, the gold standard"
    truth = Truth("i", True, 2, ["music.song_reviews#103"], [], "music.song_reviews#103")
    with pytest.raises(Excluded, match="leakage"):
        packages_for(trace, truth, "i", 2, {})


def _fake(gen, task, variant="persistent", twin=False, n=0):
    c = Candidate(f"{gen}_{task}", n, "a", "b", "c", 1, 2, None, None, {}, None)
    b = Built(c, variant, f"{gen}_{task}_{variant}_{n}", None, None, {}, {})
    b.extra["has_twin"] = twin
    return b


def test_select_caps_generators_and_spreads():
    persistent = [_fake("g1", t, n=n) for t in (1, 2, 3) for n in range(2)] + [_fake("g2", 1, twin=True)]
    nonpersistent = [_fake("g1", 1, "nonpersistent"), _fake("g3", 1, "nonpersistent"),
                     _fake("g3", 2, "nonpersistent"), _fake("g3", 3, "nonpersistent")]
    chosen_p, chosen_n = select(persistent, nonpersistent, 20, 10)
    gens = [b.candidate.generator for b in chosen_p + chosen_n]
    assert gens.count("g1") == 2 and gens.count("g2") == 1 and gens.count("g3") == 2
    g1 = [b.candidate.task_id for b in chosen_p if b.candidate.generator == "g1"]
    assert len(set(g1)) == 2  # different tasks of the generator before repeating one


def test_spread_keeps_first_second_middle_and_last_positions():
    cands = [Candidate("t_1", i, "a", "b", "c", 1, 2, None, None, {}, None) for i in range(10)]
    assert [c.index for c in spread(cands, 4)] == [0, 1, 5, 9]
    assert [c.index for c in spread(cands, 2)] == [0, 1]


def test_select_approaches_the_requested_ratio_and_pairs_twins_of_the_same_wrong_action():
    persistent = [_fake(g, t, n=n) for g in ("g1", "g2", "g3") for t in (1, 2) for n in range(2)]
    twins = [_fake(g, 1, "nonpersistent", n=0) for g in ("g1", "g2", "g3")]
    for twin, p in zip(twins, [b for b in persistent if b.candidate.task_id.endswith("_1") and b.candidate.index == 0]):
        twin.candidate = p.candidate
    chosen_p, chosen_n = select(persistent, twins, 20, 10)
    assert len(chosen_p) + len(chosen_n) == 6 and len(chosen_n) == 2
    assert {b.candidate.key for b in chosen_n} <= {b.candidate.key for b in chosen_p}
