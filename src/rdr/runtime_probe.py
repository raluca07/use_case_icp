"""Feasibility probe for a runtime fault family (Raluca's point 6, 6 Nov 2026: code errors and runtime errors).

Every pilot fault is a wrong argument the agent passed (a code error). A runtime error here is a read call whose
response gives the code a wrong value while every line of code is right: the gold code then writes that value on.
The probe changes what the code sees of one read call R (Plan.patch, as the feeds-edge audit does), replacing a
value v with a sibling value of the same key from the same response list, and counts the runs that still finish
and leave two or more stale rows against gold.

Candidates: a read call R (no writes, not a system app) with a sibling pair (key, v, alt) where v appears in the
arguments of later writing calls that R feeds, and those calls write two or more rows. The first such pair per R
is taken. Output is counts only (no AppWorld values).

Usage (from the repo root): `PYTHONPATH=src .venv/bin/python -m rdr.runtime_probe <out.json>`.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rdr.graph import argument_values, build_graph, call_node
from rdr.inject import SYSTEM_APPS
from rdr.trace import Trace

REPO = Path(__file__).resolve().parents[2]


def sibling_pairs(response) -> list[tuple[str, object, object]]:
    """(key, value, alt) for every list of objects in the response: alt is the first other value of the same key in
    that list, ordered as text."""
    out: list[tuple[str, object, object]] = []

    def walk(obj) -> None:
        if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
            for key in sorted(set().union(*obj)):
                values = [x.get(key) for x in obj
                          if isinstance(x.get(key), (int, str)) and not isinstance(x.get(key), bool)]
                for value in values:
                    others = sorted({u for u in values if u != value}, key=str)
                    if others:
                        out.append((key, value, others[0]))
        for child in (obj.values() if isinstance(obj, dict) else obj if isinstance(obj, list) else []):
            walk(child)

    walk(response)
    return out


def runtime_candidates(task_id: str, gold: Trace, id_tables: dict | None) -> list[dict]:
    graph = build_graph(gold, id_tables)
    by_index = {c.index: c for c in gold.calls}
    feeds: dict[str, list[int]] = {}
    for edge in graph.edges:
        if edge.kind == "feeds":
            feeds.setdefault(edge.src, []).append(int(edge.dst.split(":")[1]))
    out = []
    for read in gold.calls:
        if read.app in SYSTEM_APPS or read.writes:
            continue
        for key, value, alt in sibling_pairs(read.response):
            consumers = [c for c in feeds.get(call_node(read.index), []) if by_index[c].writes
                         and by_index[c].app not in SYSTEM_APPS
                         and str(value) in {str(x) for x in argument_values(by_index[c].args)}]
            if len({w.record for c in consumers for w in by_index[c].writes}) >= 2:
                out.append({"task": task_id, "generator": task_id.split("_")[0], "read_index": read.index,
                            "key": key, "value": value, "alt": alt})
                break
    return out


def probe(candidate: dict, gold_dir: Path, schema) -> str:
    """Outcome of one patched run against gold."""
    from rdr.align import make_aligned_truth
    from rdr.appworld_adapter import run_task

    gold = Trace.load(gold_dir / candidate["task"] / "trace.json")
    failed_file = gold_dir / candidate["task"] / "failed_calls.json"
    gold_failed = len(json.loads(failed_file.read_text())) if failed_file.exists() else 0
    try:
        result = run_task(candidate["task"], {"patch": {"index": candidate["read_index"], "value": candidate["value"],
                                                        "replacement": candidate["alt"]}})
    except RuntimeError:
        return "worker error"
    if not result.succeeded:
        return "run raised an exception"
    if len(result.failed_calls) > gold_failed:
        return "a later call failed"
    try:
        truth = make_aligned_truth("probe", result.trace, gold, schema, candidate["read_index"], None, min_stale=1,
                                   expect_faulty=True)
    except ValueError as error:
        message = str(error)
        if "expect_faulty" in message:
            return "final state equals gold"
        if "no stale" in message:
            return "only missing records"
        return "ground truth error"
    return "two or more stale rows" if len(truth.stale) >= 2 else "one stale row"


def main(argv: list[str]) -> int:
    from rdr.appworld_adapter import load_schema
    from rdr.controls import default_id_tables

    out_path = Path(argv[0]) if argv else REPO / "runs" / "runtime_probe.json"
    gold_dir = REPO / "runs" / "gold"
    id_tables = default_id_tables()
    schema = load_schema(REPO / "runs" / "schema.json")
    gate = json.loads((gold_dir / "determinism.json").read_text())
    tasks = sorted(t for t, v in gate.items() if v["passed"])
    candidates = [c for t in tasks for c in runtime_candidates(t, Trace.load(gold_dir / t / "trace.json"), id_tables)]
    with ThreadPoolExecutor(8) as pool:
        outcomes = list(pool.map(lambda c: probe(c, gold_dir, schema), candidates))
    usable = Counter(c["generator"] for c, o in zip(candidates, outcomes) if o == "two or more stale rows")
    pilot = set(json.loads((REPO / "runs" / "pilot" / "build_summary.json").read_text())["pilot_generators"])
    summary = {
        "tasks": len(tasks), "candidates": len(candidates),
        "candidate_generators": len({c["generator"] for c in candidates}),
        "outcomes": dict(Counter(outcomes).most_common()),
        "usable_generators": len(usable), "usable_generators_outside_pilot": len(set(usable) - pilot),
        "usable_per_generator": sorted(usable.values(), reverse=True),
        "units_at_cap_2": sum(min(v, 2) for v in usable.values()),
        "units_at_cap_2_outside_pilot": sum(min(v, 2) for g, v in usable.items() if g not in pilot),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
