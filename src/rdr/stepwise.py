"""Arm N, step by step (Raluca, 2 Nov 2026: does the reviewer take the full graph or walk it?).

Every other arm is one shot: the whole package in one prompt with no tools. Here the reviewer starts from the
reported record with that record's edges already shown, and each round asks for one visible node's edges (a call
or a record), for at most `max_expansions` rounds, or says it has enough. Each round is a fresh isolated
`claude -p` call that sees the common header, the explored part of the graph, its own notes and any request that
could not be done. The answer is then asked with the standard system prompt and schema over the explored part,
so arm N is scored exactly as the one-shot arms.

Arm O is the same walk with the stopping choice removed: the reviewer must use every expansion before it is asked
for the answer. N against O separates "walking helps" from "the reviewer chooses to stop early".

Every round is saved (`<arm>.step<k>.json`), so a stopped run resumes without new calls. `<arm>.path.json` keeps
the walk.

Usage (from the repo root): `PYTHONPATH=src .venv/bin/python -m rdr.stepwise check|run [N|O] [limit]|analyse`.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

from rdr.controls import (ARM_NAMES, REPO, anchor_of, contrast_lines, default_id_tables, groups_of, paired,
                          score_rows, summarise, table_lines)
from rdr.freeze import verify_manifest
from rdr.graph import Graph, build_graph, call_node, rec_node, render, with_node
from rdr.packager import ARMS, CONTROL_ARMS, _header, check_leakage
from rdr.pilot import EFFORT, MODEL, _pct, load_instances
from rdr.runner import RETRY_PATTERN, ReviewError, review_with_backoff
from rdr.trace import Trace
from rdr.truth import Truth

MAX_EXPANSIONS = 6
NOTE_CHARS = 600
ROOT = REPO / "runs" / "stepwise"
CONTROLS = REPO / "runs" / "controls"

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["expand", "answer"]},
        "node": {"type": ["string", "null"]},
        "note": {"type": "string"},
    },
    "required": ["action", "node", "note"],
    "additionalProperties": False,
}

STEP_SYSTEM_PROMPT = (
    "You review the record of an automated assistant's work in a user's apps. A user reports that one record "
    "looks wrong. You can see the task, the final state of the records the assistant changed and the list of "
    "calls it made. The provenance graph of the run is shown only where you have explored it, starting from the "
    "reported record. Each turn, either expand one node listed under NODES that you have not expanded yet (a call "
    "such as call:12 or a record such as rec:app.table#5) to see its edges and neighbours, or stop when you have "
    "enough evidence to say which call started the problem and which records are still wrong. "
    "action: \"expand\" or \"answer\". node: the node to expand, or null when you answer. "
    "note: one or two sentences on what you have learned and what you are looking for; your notes are shown back "
    "to you on the next turn. Use only the evidence in the message. Reply with JSON matching the schema and nothing "
    "else."
)


def validate_step(step) -> dict:
    if not isinstance(step, dict):
        raise ValueError(f"step must be an object, got {type(step).__name__}")
    if sorted(step) != ["action", "node", "note"]:
        raise ValueError(f"step has keys {sorted(step)}, expected action, node and note")
    if step["action"] not in ("expand", "answer"):
        raise ValueError(f"unknown action {step['action']!r}")
    if not isinstance(step["note"], str):
        raise ValueError("note must be a string")
    if step["action"] == "expand" and not (isinstance(step["node"], str) and step["node"].strip()):
        raise ValueError("an expand step needs a node")
    if step["node"] is not None and not isinstance(step["node"], str):
        raise ValueError("node must be a string or null")
    return step


FORCED_STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["expand"]},
        "node": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["action", "node", "note"],
    "additionalProperties": False,
}

FORCED_STEP_SYSTEM_PROMPT = (
    "You review the record of an automated assistant's work in a user's apps. A user reports that one record "
    "looks wrong. You can see the task, the final state of the records the assistant changed and the list of "
    "calls it made. The provenance graph of the run is shown only where you have explored it, starting from the "
    "reported record. Each turn, expand one node listed under NODES that you have not expanded yet (a call such as "
    "call:12 or a record such as rec:app.table#5) to see its edges and neighbours. You expand a fixed number of "
    "nodes, one per turn, and you are asked which call started the problem and which records are still wrong after "
    "the last one. action: \"expand\". node: the node to expand. note: one or two sentences on what you have "
    "learned and what you are looking for; your notes are shown back to you on the next turn. Use only the "
    "evidence in the message. Reply with JSON matching the schema and nothing else."
)


def validate_forced_step(step) -> dict:
    validate_step(step)
    if step["action"] != "expand":
        raise ValueError("this walk expands a fixed number of nodes; the answer is asked after the last one")
    return step


MODES = {"N": (STEP_SYSTEM_PROMPT, STEP_SCHEMA, validate_step),
         "O": (FORCED_STEP_SYSTEM_PROMPT, FORCED_STEP_SCHEMA, validate_forced_step)}


def normalise_node(text: str, graph: Graph) -> str:
    """`12`, `call 12` and `call:12` name call 12; a record label without `rec:` names that record."""
    text = text.strip()
    if text in graph.call_nodes or text in graph.record_nodes:
        return text
    if text.isdigit():
        return call_node(int(text))
    rest = text[len("call"):].strip(" :#") if text.lower().startswith("call") else ""
    if rest.isdigit():
        return call_node(int(rest))
    if rec_node(text) in graph.record_nodes:
        return rec_node(text)
    return text


def explored_graph(graph: Graph, expanded: list[str]) -> Graph:
    part = Graph({}, [], [])
    for node in expanded:
        part = with_node(graph, part, node)
    return part


def _view_lines(trace: Trace, symptom: str, graph: Graph, expanded: list[str]) -> list[str]:
    view = explored_graph(graph, expanded)
    return [*_header(trace, symptom), "", "PROVENANCE GRAPH, EXPLORED PART ONLY",
            "Expanded so far, in order: " + ", ".join(expanded), render(view)]


def _notes_lines(notes: list[str], events: list[str]) -> list[str]:
    lines: list[str] = []
    if events:
        lines += ["", "REQUESTS THAT COULD NOT BE DONE", *events]
    if notes:
        lines += ["", "YOUR NOTES SO FAR", *(f"round {k}: {note}" for k, note in enumerate(notes, 1))]
    return lines


def round_package(trace: Trace, symptom: str, graph: Graph, expanded: list[str], notes: list[str],
                  events: list[str], left: int, extra_forbidden=None) -> str:
    ours = _view_lines(trace, symptom, graph, expanded) + [
        "", "You can expand any node listed under NODES that you have not expanded yet.", f"EXPANSIONS LEFT: {left}"]
    text = "\n".join(ours)
    check_leakage(text, extra_forbidden=extra_forbidden)  # notes and echoed requests are the reviewer's own words
    return "\n".join([text, *_notes_lines(notes, events)])


def final_package(trace: Trace, symptom: str, graph: Graph, expanded: list[str], notes: list[str],
                  extra_forbidden=None) -> str:
    text = "\n".join(_view_lines(trace, symptom, graph, expanded))
    check_leakage(text, extra_forbidden=extra_forbidden)
    return "\n".join([text, *_notes_lines(notes, [])])


def explore(trace: Trace, symptom: str, instance_id: str, id_tables: dict | None, ask,
            max_expansions: int = MAX_EXPANSIONS, extra_forbidden=None) -> dict:
    """Walk the graph from the reported record. `ask(kind, package, round)` returns a validated step for kind
    "step" and the answer record for kind "answer"."""
    graph = build_graph(trace, id_tables)
    start = rec_node(symptom)
    if start not in graph.record_nodes:
        raise ValueError(f"{instance_id}: the reported record {symptom} is not in the graph")
    expanded, notes, events = [start], [], []
    stopped_by, rounds = "budget", 0
    for k in range(1, max_expansions + 1):
        package = round_package(trace, symptom, graph, expanded, notes, events, max_expansions - k + 1,
                                extra_forbidden)
        step = ask("step", package, k)
        rounds = k
        notes.append(step["note"].strip()[:NOTE_CHARS])
        if step["action"] == "answer":
            stopped_by = "answer"
            break
        node = normalise_node(step["node"], graph)
        view = explored_graph(graph, expanded)
        if node in expanded:
            events.append(f"round {k}: {node} is already expanded")
        elif node not in view.call_nodes and node not in view.record_nodes:
            events.append(f"round {k}: {node[:80]} is not a node you can see yet")
        else:
            expanded.append(node)
    record = ask("answer", final_package(trace, symptom, graph, expanded, notes, extra_forbidden), 0)
    return {"expanded": expanded, "notes": notes, "events": events, "rounds": rounds, "stopped_by": stopped_by,
            "max_expansions": max_expansions, "record": record}


def make_ask(reviews_dir: Path, instance_id: str, model: str, effort: str, claude_cmd, waits, sleep_fn,
             arm: str = "N"):
    system_prompt, schema, validate = MODES[arm]

    def ask(kind: str, package: str, k: int):
        with tempfile.TemporaryDirectory(prefix="rdr-review-") as workdir:  # fresh and empty per call
            if kind == "step":
                record = review_with_backoff(package, reviews_dir / instance_id / f"{arm}.step{k}.json", model,
                                             effort, Path(workdir), claude_cmd=claude_cmd, waits=waits,
                                             sleep_fn=sleep_fn, system_prompt=system_prompt, schema=schema,
                                             validate=validate)
                return record["answer"]
            return review_with_backoff(package, reviews_dir / instance_id / f"{arm}.json", model, effort,
                                       Path(workdir), claude_cmd=claude_cmd, waits=waits, sleep_fn=sleep_fn)
    return ask


def run(instances_dir: Path, reviews_dir: Path, log_path: Path, id_tables: dict | None, claude_cmd=("claude",),
        model: str = MODEL, effort: str = EFFORT, sleep_fn=time.sleep, waits=(60, 300, 1800),
        max_expansions: int = MAX_EXPANSIONS, limit: int | None = None, arm: str = "N") -> dict:
    problems = verify_manifest(instances_dir)
    if problems:
        raise RuntimeError(f"freeze check failed: {problems[:5]}")
    instances = load_instances(instances_dir)[:limit]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {"planned": len(instances), "done": 0, "failed": 0, "stopped": None}

    def log(row: dict) -> None:
        with log_path.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    log({"event": "session_start", "t": time.time(), "planned": len(instances)})
    for inst in instances:
        trace = Trace.load(inst["dir"] / "trace.json")
        truth = Truth.load(inst["dir"] / "truth.json")
        ask = make_ask(reviews_dir, inst["id"], model, effort, claude_cmd, waits, sleep_fn, arm)
        row = {"event": "instance", "arm": arm, "instance": inst["id"], "t_start": time.time()}
        try:
            out = explore(trace, truth.symptom, inst["id"], id_tables, ask, max_expansions)
        except ReviewError as err:
            row.update(t_end=time.time(), status="failed", reason=str(err)[-600:])
            log(row)
            summary["failed"] += 1
            if RETRY_PATTERN.search(str(err).lower()):
                summary["stopped"] = f"{inst['id']}: {str(err)[-600:]}"
                break
            continue
        path = {k: v for k, v in out.items() if k != "record"}
        (reviews_dir / inst["id"] / f"{arm}.path.json").write_text(json.dumps(path, indent=2, sort_keys=True))
        row.update(t_end=time.time(), status="done", rounds=out["rounds"], stopped_by=out["stopped_by"])
        log(row)
        summary["done"] += 1
    log({"event": "session_end", "t": time.time(), **summary})
    return summary


def distance(graph: Graph, source: str, target: str) -> int | None:
    adjacent: dict[str, set[str]] = {}
    for edge in graph.edges:
        adjacent.setdefault(edge.src, set()).add(edge.dst)
        adjacent.setdefault(edge.dst, set()).add(edge.src)
    seen = {source: 0}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for neighbour in adjacent.get(node, ()):
            if neighbour not in seen:
                seen[neighbour] = seen[node] + 1
                queue.append(neighbour)
    return seen.get(target)


def check(instances_dir: Path, id_tables: dict | None) -> dict:
    """The walk's graph must be arm C's graph, byte for byte, and the anchor's distance is recorded."""
    dirs = sorted(p for p in instances_dir.iterdir() if p.is_dir())
    metas = {d.name: json.loads((d / "meta.json").read_text()) for d in dirs}
    distances = {}
    for d in dirs:
        trace, truth = Trace.load(d / "trace.json"), Truth.load(d / "truth.json")
        graph = build_graph(trace, id_tables)
        c_graph = (d / "packages" / "C.txt").read_text().split("PROVENANCE GRAPH\n", 1)[1]
        if render(graph) != c_graph:
            raise RuntimeError(f"{d.name}: the walk's graph differs from arm C's")
        distances[d.name] = distance(graph, rec_node(truth.symptom), call_node(anchor_of(metas[d.name], metas)))
    return distances


WALK_CONTRASTS = (
    ("N", "C", "walking against the whole graph in one prompt"),
    ("N", "D", "walking against the fixed 2-hop neighbourhood"),
    ("N", "K", "walking against the neighbourhood with the source forced in"),
    ("N", "B", "walking the graph against the full action log"),
    ("N", "A", "walking against no graph"),
    ("O", "N", "a full walk against a walk the reviewer may stop"),
    ("O", "C", "a full walk against the whole graph in one prompt"),
    ("O", "A", "a full walk against no graph"),
)


def walk_rows(instances: list[dict], reviews_dir: Path, rows: dict, arm: str, distances: dict,
              id_tables: dict | None) -> list[dict]:
    metas = {i["id"]: json.loads((i["dir"] / "meta.json").read_text()) for i in instances}
    walks = []
    for inst in instances:
        path_file = reviews_dir / inst["id"] / f"{arm}.path.json"
        if not path_file.exists():
            continue
        path = json.loads(path_file.read_text())
        anchor = call_node(anchor_of(metas[inst["id"]], metas))
        graph = build_graph(Trace.load(inst["dir"] / "trace.json"), id_tables)
        view = explored_graph(graph, path["expanded"])
        walks.append({"id": inst["id"], "variant": inst["variant"], "rounds": path["rounds"],
                      "stopped_by": path["stopped_by"], "events": len(path["events"]),
                      "expanded": len(path["expanded"]) - 1, "distance": distances[inst["id"]],
                      "anchor_seen": anchor in view.call_nodes, "anchor_expanded": anchor in path["expanded"],
                      "hit": rows[(inst["id"], arm)]["origin_hit"]})
    return walks


def analyse(instances_dir: Path, reviews_dir: Path, report_path: Path, id_tables: dict | None) -> dict:
    instances = load_instances(instances_dir)
    walk_arms = [a for a in MODES if any((reviews_dir / i["id"] / f"{a}.path.json").exists() for i in instances)]
    arms = ("A", "B", "C", "D", "G", "J", "K", *walk_arms)
    reviews_for = {a: (REPO / "runs" / "pilot" / "reviews" if a in ARMS else
                       CONTROLS / "reviews" if a in CONTROL_ARMS else reviews_dir) for a in arms}
    rows = score_rows(instances, reviews_for)
    groups = groups_of(instances)
    table = summarise(rows, instances, arms)
    contrasts = paired(rows, groups, [c for c in WALK_CONTRASTS if c[0] in arms and c[1] in arms])
    distances = check(instances_dir, id_tables)
    walks = {a: walk_rows(instances, reviews_dir, rows, a, distances, id_tables) for a in walk_arms}
    report = render_report(table, contrasts, groups, walks)
    report_path.write_text(report)
    return {"table": table, "contrasts": contrasts, "walks": walks, "report": report}


def _walk_section(arm: str, walks: list[dict], n_all: int) -> list[str]:
    L: list[str] = []
    w = L.append
    faulty = [x for x in walks if x["variant"] != "clean"]
    unreachable = [x for x in faulty if x["distance"] is None]
    reachable = [x for x in faulty if x["distance"] is not None]
    seen = [x for x in reachable if x["anchor_seen"]]
    w(f"Arm {arm}: walks recorded {len(walks)} of {n_all}.")
    w("")
    w(f"- Faulty instances where no walk can reach the origin (no path in the graph): {len(unreachable)} of "
      f"{len(faulty)}. Origin hit there anyway: {sum(1 for x in unreachable if x['hit'])}.")
    w(f"- Reachable faulty instances where the walk brought the origin into view: {_pct(len(seen), len(reachable))}"
      f". Origin hit when it was in view: {_pct(sum(1 for x in seen if x['hit']), len(seen))}; when it was not: "
      f"{_pct(sum(1 for x in reachable if not x['anchor_seen'] and x['hit']), len(reachable) - len(seen))}.")
    w(f"- Walks that stopped by choice: {sum(1 for x in walks if x['stopped_by'] == 'answer')} of {len(walks)}; "
      f"by the budget: {sum(1 for x in walks if x['stopped_by'] == 'budget')}. Nodes expanded per walk, median: "
      f"{sorted(x['expanded'] for x in walks)[len(walks) // 2] if walks else 'n/a'}. Requests that could not be "
      f"done (not visible or already expanded): {sum(x['events'] for x in walks)} in all.")
    w("")
    w("| Instance | Variant | Distance | Rounds | Nodes expanded | Stopped by | Origin in view | Origin expanded | "
      "Origin hit |")
    w("|---|---|---|---|---|---|---|---|---|")
    for x in walks:
        w(f"| `{x['id']}` | {x['variant']} | {x['distance'] if x['distance'] is not None else 'no path'} | "
          f"{x['rounds']} | {x['expanded']} | {x['stopped_by']} | {'yes' if x['anchor_seen'] else 'no'} | "
          f"{'yes' if x['anchor_expanded'] else 'no'} | "
          f"{'' if x['hit'] is None else 'yes' if x['hit'] else 'no'} |")
    w("")
    return L


def render_report(table: dict, contrasts: list[dict], groups: dict, walks: dict[str, list[dict]]) -> str:
    L: list[str] = []
    w = L.append
    w("# Step-by-step arms on the Gate 2 pilot set")
    w("")
    w("Raluca asked (2 Nov 2026) whether the reviewer takes the whole graph or walks it step by step. Every arm "
      "A to M is one shot. Arm N starts from the reported record and expands one visible node per round, for at "
      f"most {MAX_EXPANSIONS} rounds, and may stop early. Arm O is the same walk but must use all {MAX_EXPANSIONS} "
      "expansions. Both then answer with the standard prompt and schema over the explored part. Same frozen "
      f"{len(groups['all'])} instances ({len(groups['persistent'])} persistent, {len(groups['nonpersistent'])} "
      f"non-persistent, {len(groups['clean'])} clean), same model (`claude-haiku-5-5`, effort `medium`). Other arms "
      "are their existing main reviews, not re-run. A failed or missing review is a miss (intention to treat). "
      "Distance is the number of graph edges from the reported record to the origin (for a clean twin, to the same "
      "write), ignoring edge direction.")
    w("")
    w("## 1. Origin hit")
    w("")
    L.extend(table_lines(table, groups))
    w("")
    w("## 2. Paired contrasts on origin hit")
    w("")
    L.extend(contrast_lines(contrasts))
    w("")
    w("## 3. The walks")
    w("")
    for arm, rows in walks.items():
        L.extend(_walk_section(arm, rows, len(groups["all"])))
    return "\n".join(L)


def main(argv: list[str]) -> int:
    instances_dir, reviews_dir = CONTROLS / "instances", ROOT / "reviews"
    if argv and argv[0] == "check":
        distances = check(instances_dir, default_id_tables())
        print(json.dumps(distances, indent=2, sort_keys=True))
        return 0
    if argv and argv[0] == "run":
        arm = argv[1] if len(argv) > 1 and argv[1] in MODES else "N"
        rest = argv[2:] if len(argv) > 1 and argv[1] in MODES else argv[1:]
        limit = int(rest[0]) if rest else None
        log_name = "run_log.jsonl" if arm == "N" else f"run_log_{arm}.jsonl"
        summary = run(instances_dir, reviews_dir, ROOT / log_name, default_id_tables(), limit=limit, arm=arm)
        print(json.dumps(summary, indent=2))
        return 0 if summary["stopped"] is None else 2
    if argv and argv[0] == "analyse":
        result = analyse(instances_dir, reviews_dir, REPO / "docs" / "stepwise_results.md", default_id_tables())
        print(result["report"])
        return 0
    print("usage: python -m rdr.stepwise check|run [N|O] [limit]|analyse", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
