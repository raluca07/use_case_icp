import json
import sys
from pathlib import Path

import pytest
from builders import persistent_trace, realistic_trace

from rdr.controls import derive
from rdr.freeze import write_manifest
from rdr.graph import build_graph
from rdr.packager import LeakageError, build_package
from rdr.stepwise import (FORCED_STEP_SCHEMA, MAX_EXPANSIONS, STEP_SCHEMA, analyse, explore, explored_graph,
                          normalise_node, run, validate_forced_step, validate_step)
from rdr.truth import Truth

SYMPTOM = "splitwise.expenses#77"
FAKE = (sys.executable, str(Path(__file__).with_name("fake_claude.py")))


def scripted(steps):
    """An `ask` that replays steps in order and records every package it was shown."""
    seen = {"step": [], "answer": []}
    queue = list(steps)

    def ask(kind, package, round_index):
        seen[kind].append(package)
        if kind == "answer":
            return {"answer": {"anything_wrong": True, "origin_call": 1, "still_wrong_records": [SYMPTOM]}}
        return queue.pop(0) if queue else {"action": "expand", "node": "call:0", "note": "more"}
    return ask, seen


def expand(node, note="next"):
    return {"action": "expand", "node": node, "note": note}


def test_the_start_is_the_reported_record_and_its_edges():
    graph = build_graph(persistent_trace())
    view = explored_graph(graph, ["rec:" + SYMPTOM])
    assert {(e.src, e.kind, e.dst) for e in view.edges} == {("call:2", "writes", "rec:" + SYMPTOM)}


def test_a_walk_expands_visible_nodes_and_ends_on_answer():
    ask, seen = scripted([expand("call:2"), expand("call:1"), {"action": "answer", "node": None, "note": "done"}])
    out = explore(persistent_trace(), SYMPTOM, "i1", None, ask)
    assert out["expanded"] == ["rec:" + SYMPTOM, "call:2", "call:1"]
    assert out["rounds"] == 3 and out["events"] == [] and out["stopped_by"] == "answer"
    assert len(seen["step"]) == 3 and len(seen["answer"]) == 1
    assert f"EXPANSIONS LEFT: {MAX_EXPANSIONS}" in seen["step"][0]
    assert "call:1 -writes-> rec:venmo.transactions#101" in seen["answer"][0]
    assert "next" in seen["answer"][0]  # the reviewer's own notes travel with it


def test_the_first_round_shows_only_the_start():
    ask, seen = scripted([{"action": "answer", "node": None, "note": "done"}])
    explore(persistent_trace(), SYMPTOM, "i1", None, ask)
    graph_part = seen["step"][0].split("PROVENANCE GRAPH", 1)[1]
    assert "call:2 -writes-> rec:" + SYMPTOM in graph_part
    assert "-reads->" not in graph_part and "call:1 =" not in graph_part and "call:4 =" not in graph_part


def test_a_node_that_is_not_visible_costs_a_round_and_is_reported():
    ask, seen = scripted([expand("call:4"), {"action": "answer", "node": None, "note": "done"}])
    out = explore(persistent_trace(), SYMPTOM, "i1", None, ask)
    assert out["expanded"] == ["rec:" + SYMPTOM] and out["rounds"] == 2
    assert out["events"] == ["round 1: call:4 is not a node you can see yet"]
    assert "call:4 is not a node you can see yet" in seen["step"][1]


def test_expanding_twice_is_reported():
    ask, _ = scripted([expand("call:2"), expand("call:2"), {"action": "answer", "node": None, "note": "done"}])
    out = explore(persistent_trace(), SYMPTOM, "i1", None, ask)
    assert out["events"] == ["round 2: call:2 is already expanded"]


def test_the_budget_ends_the_walk_and_the_answer_is_still_asked():
    ask, seen = scripted([])
    out = explore(realistic_trace(), SYMPTOM, "i1", None, ask, max_expansions=3)
    assert len(seen["step"]) == 3 and len(seen["answer"]) == 1 and out["stopped_by"] == "budget"


def test_node_names_are_normalised():
    graph = build_graph(persistent_trace())
    assert normalise_node("2", graph) == "call:2"
    assert normalise_node(" call 2 ", graph) == "call:2"
    assert normalise_node(SYMPTOM, graph) == "rec:" + SYMPTOM
    assert normalise_node("rec:" + SYMPTOM, graph) == "rec:" + SYMPTOM
    assert normalise_node("nonsense", graph) == "nonsense"


def test_notes_may_use_any_word_but_our_text_is_still_checked():
    ask, _ = scripted([expand("call:2", note="the stale repair looks faulty")])
    explore(persistent_trace(), SYMPTOM, "i1", None, ask, max_expansions=1)
    trace = persistent_trace()
    trace.instruction = "This run has an injected fault."
    with pytest.raises(LeakageError):
        explore(trace, SYMPTOM, "i1", None, scripted([])[0], max_expansions=1)


def _edge_lines(text):
    return {line for line in text.split("EDGES", 1)[1].splitlines() if " -" in line and "-> " in line}


def test_expanding_the_whole_connected_part_shows_all_of_arm_c_edges_there():
    trace = persistent_trace()
    order = ["call:2", "call:1", "call:3", "rec:venmo.transactions#101"]
    ask, seen = scripted([expand(n) for n in order] + [{"action": "answer", "node": None, "note": "done"}])
    out = explore(trace, SYMPTOM, "i1", None, ask, max_expansions=len(order) + 1)
    assert out["events"] == [] and out["stopped_by"] == "answer"
    c_edges = _edge_lines(build_package("C", trace, SYMPTOM, "i1"))
    # call 4 (the second payment) shares no edge with the reported record's part of the graph
    assert _edge_lines(seen["answer"][0]) == {line for line in c_edges if "call:4" not in line}


@pytest.mark.parametrize("step", [
    {"action": "expand", "node": None, "note": "x"}, {"action": "jump", "node": "call:1", "note": "x"},
    {"action": "answer", "node": None}, {"action": "answer", "node": None, "note": "x", "extra": 1}, "expand"])
def test_malformed_steps_are_rejected(step):
    with pytest.raises(ValueError):
        validate_step(step)


def test_step_schema_requires_every_field():
    assert sorted(STEP_SCHEMA["required"]) == ["action", "node", "note"]


def _frozen(tmp_path):
    src = tmp_path / "pilot"
    d = src / "p1"
    (d / "packages").mkdir(parents=True)
    persistent_trace().save(d / "trace.json")
    Truth("p1", True, 1, [SYMPTOM], [], SYMPTOM).save(d / "truth.json")
    (d / "meta.json").write_text(json.dumps({"instance_id": "p1", "variant": "persistent", "generator": "g1",
                                             "origin_index": 1, "twin_of": None}))
    for arm in "ABCDEFG":
        (d / "packages" / f"{arm}.txt").write_text(
            build_package(arm, persistent_trace(), SYMPTOM, "p1", avoid_calls=frozenset({1})))
    write_manifest(src)
    derive(src, tmp_path / "controls", None)
    return tmp_path / "controls"


def test_run_with_the_fake_cli_saves_every_round_and_resumes(tmp_path, monkeypatch):
    instances = _frozen(tmp_path)
    count = tmp_path / "count"
    monkeypatch.setenv("FAKE_COUNT_FILE", str(count))
    monkeypatch.setenv("FAKE_STEP_NODE", "call:2")
    reviews = tmp_path / "reviews"
    summary = run(instances, reviews, tmp_path / "log.jsonl", None, claude_cmd=FAKE, max_expansions=2)
    assert summary["done"] == 1 and summary["failed"] == 0
    files = sorted(p.name for p in (reviews / "p1").iterdir())
    assert files == ["N.json", "N.path.json", "N.step1.json", "N.step2.json"]
    path = json.loads((reviews / "p1" / "N.path.json").read_text())
    assert path["expanded"] == ["rec:" + SYMPTOM, "call:2"] and path["events"] == ["round 2: call:2 is already expanded"]
    assert json.loads((reviews / "p1" / "N.json").read_text())["answer"]["origin_call"] == 1
    calls = len(count.read_text().splitlines())
    assert calls == 3
    run(instances, reviews, tmp_path / "log.jsonl", None, claude_cmd=FAKE, max_expansions=2)
    assert len(count.read_text().splitlines()) == calls  # everything resumed from disk


def test_the_forced_walk_cannot_stop_early():
    with pytest.raises(ValueError):
        validate_forced_step({"action": "answer", "node": None, "note": "done"})
    assert validate_forced_step({"action": "expand", "node": "call:2", "note": "x"})
    assert FORCED_STEP_SCHEMA["properties"]["action"]["enum"] == ["expand"]


def test_forced_run_uses_its_own_files_and_the_report_covers_both_walks(tmp_path, monkeypatch):
    instances = _frozen(tmp_path)
    monkeypatch.setenv("FAKE_STEP_NODE", "call:2")
    reviews = tmp_path / "reviews"
    run(instances, reviews, tmp_path / "log.jsonl", None, claude_cmd=FAKE, max_expansions=2, arm="N")
    summary = run(instances, reviews, tmp_path / "log_o.jsonl", None, claude_cmd=FAKE, max_expansions=3, arm="O")
    assert summary["done"] == 1
    names = sorted(p.name for p in (reviews / "p1").iterdir())
    assert [n for n in names if n.startswith("O")] == ["O.json", "O.path.json", "O.step1.json", "O.step2.json",
                                                      "O.step3.json"]
    assert json.loads((reviews / "p1" / "O.path.json").read_text())["stopped_by"] == "budget"
    result = analyse(instances, reviews, tmp_path / "report.md", None)
    assert set(result["walks"]) == {"N", "O"}
    report = (tmp_path / "report.md").read_text()
    assert "| O vs N |" in report and "Arm O: walks recorded 1 of 1." in report
    assert result["walks"]["N"][0]["anchor_seen"] is True and result["walks"]["N"][0]["hit"] is True
