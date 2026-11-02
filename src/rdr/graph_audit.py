"""Edge-precision audit of the provenance graph on gold replays (carry-over I2).

feeds edges, counterfactual oracle: for a sampled edge i -> j matched on value v, the gold code is re-run with
v replaced by a sentinel in what call i's response shows the code (rdr.appworld_adapter Plan.patch). The edge
is confirmed if call j's arguments now carry the sentinel, changed if they differ from gold without it (the
value still steered j), refuted if call j is unchanged (j took v from elsewhere), and diverged if the run no
longer reaches a call j with the same API (excluded from precision). Precision is reported for several
MAX_PRODUCERS cut-offs from one sample drawn without any cut-off.

reads edges: a reads edge R -> j is confirmed by evidence when a row j writes holds a foreign key to R, or j's
response holds R's id beside another of R's field values; it is path-addressed when j's documented API path
addresses a row of R's table by that argument (`/<table>/{<key>}`), which the API contract makes a read of R;
otherwise it is unverified.
Output: runs/audit/graph_audit.json (counts only are printed).
"""
from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rdr.graph import argument_values, build_graph, response_values
from rdr.trace import Trace

CUTOFFS = (1, 2, 3, 5, 10, None)
REPO = Path(__file__).resolve().parents[2]


def sentinel_for(value: str):
    return str(int(value) + 7919) if value.lstrip("-").isdigit() else value + "q"


def classify(gold: Trace, run: Trace, j: int, sentinel: str) -> str:
    if run is None or len(run.calls) <= j or run.calls[j].name != gold.calls[j].name:
        return "diverged"
    if sentinel in argument_values(run.calls[j].args):
        return "confirmed"
    if run.calls[j].args == gold.calls[j].args:
        return "refuted"
    return "changed"


def feeds_candidates(trace: Trace) -> list[dict]:
    """Every feeds edge with no producer cut-off, each with its most specific matched value."""
    graph = build_graph(trace, max_producers=10**9)
    resp = [response_values(c.response) for c in trace.calls]
    returned_by: dict[str, int] = {}
    for values in resp:
        for v in values:
            returned_by[v] = returned_by.get(v, 0) + 1
    position = {c.index: p for p, c in enumerate(trace.calls)}
    out = []
    for edge in graph.edges:
        if edge.kind != "feeds":
            continue
        i, j = position[int(edge.src[5:])], position[int(edge.dst[5:])]
        shared = sorted(resp[i] & argument_values(trace.calls[j].args), key=lambda v: (returned_by[v], v))
        out.append({"task_id": trace.task_id, "i": i, "j": j, "value": shared[0],
                    "producers": returned_by[shared[0]]})
    return out


def precision(rows: list[dict], cutoff) -> dict:
    kept = [r for r in rows if cutoff is None or r["producers"] <= cutoff]
    counts = {k: sum(r["verdict"] == k for r in kept) for k in ("confirmed", "changed", "refuted", "diverged")}
    decided = counts["confirmed"] + counts["changed"] + counts["refuted"]
    true = counts["confirmed"] + counts["changed"]
    return {"cutoff": cutoff, **counts, "precision": round(true / decided, 3) if decided else None}


def _feeds_verdict(row: dict, gold_dir: Path) -> dict:
    from rdr.appworld_adapter import run_task

    gold = Trace.load(gold_dir / row["task_id"] / "trace.json")
    sentinel = sentinel_for(row["value"])
    result = run_task(row["task_id"], {"patch": {"index": row["i"], "value": row["value"], "replacement": sentinel}})
    return {**row, "verdict": classify(gold, result.trace, row["j"], sentinel)}


def _path_addresses(doc: dict | None, table: str, args: dict, rowid: str) -> bool:
    if not doc:
        return False
    segments = doc["path"].strip("/").split("/")
    short = table.split(".", 1)[1]
    for n, segment in enumerate(segments[1:], start=1):
        key = segment[1:-1] if segment.startswith("{") and segment.endswith("}") else None
        if key and str(args.get(key)) == rowid and (segments[n - 1] == short or short.endswith("_" + segments[n - 1])):
            return True
    return False


def reads_verdicts(trace: Trace, id_tables: dict, schema, api_docs: dict | None = None) -> list[str]:
    graph = build_graph(trace, id_tables)
    position = {c.index: p for p, c in enumerate(trace.calls)}
    state: dict[str, dict | None] = {}
    seen_at: dict[int, dict[str, dict | None]] = {}
    for p, call in enumerate(trace.calls):
        seen_at[p] = dict(state)
        for write in call.writes:
            state[write.record] = write.after
    verdicts = []
    for edge in graph.edges:
        if edge.kind != "reads":
            continue
        record, j = edge.src[4:], position[int(edge.dst[5:])]
        table, rowid = record.split("#", 1)
        call = trace.calls[j]
        fk_hit = any(schema.foreign_keys.get(w.record.split("#")[0], {}).get(col) == table and str(val) == rowid
                     for w in call.writes if w.after for col, val in w.after.items())
        row = seen_at[j].get(record) or {}
        others = {str(v) for k, v in row.items() if k != "id" and v not in (None, "", 0, False)}
        resp_hit = False
        stack = [call.response]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                ids = {str(v) for k, v in item.items() if k == "id" or k.endswith("_id")}
                if rowid in ids and others & {str(v) for v in item.values()}:
                    resp_hit = True
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        if fk_hit or resp_hit:
            verdicts.append("evidence")
        elif _path_addresses((api_docs or {}).get(call.app, {}).get(call.api), table, call.args, rowid):
            verdicts.append("path")
        else:
            verdicts.append("unverified")
    return verdicts


def main(argv=None) -> None:
    from rdr.appworld_adapter import load_schema
    from rdr.graph import id_key_tables

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=REPO / "runs" / "gold")
    parser.add_argument("--out", type=Path, default=REPO / "runs" / "audit" / "graph_audit.json")
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--reads-only", action="store_true", help="reuse the feeds rows already in --out")
    args = parser.parse_args(argv)
    gate = json.loads((args.gold / "determinism.json").read_text())
    traces = [Trace.load(args.gold / t / "trace.json") for t in sorted(gate) if gate[t]["passed"]]
    candidates = [row for trace in traces for row in feeds_candidates(trace)]
    if args.reads_only:
        rows = json.loads(args.out.read_text())["feeds_rows"]
    else:
        sample = random.Random(args.seed).sample(candidates, min(args.sample, len(candidates)))
        with ThreadPoolExecutor(args.workers) as pool:
            rows = list(pool.map(lambda r: _feeds_verdict(r, args.gold), sample))
    schema = load_schema(REPO / "runs" / "schema.json")
    docs = {f.stem: json.loads(f.read_text()) for f in (REPO / "appworld_root/data/api_docs/standard").glob("*.json")}
    id_tables = id_key_tables(docs, schema.tables, schema.foreign_keys)
    reads = [v for trace in traces for v in reads_verdicts(trace, id_tables, schema, docs)]
    legacy_reads = sum(1 for trace in traces for e in build_graph(trace).edges if e.kind == "reads")
    summary = {
        "traces": len(traces), "feeds_edges_without_cutoff": len(candidates), "feeds_sample": len(rows),
        "feeds_edges_by_cutoff": {str(k): sum(1 for r in candidates if k is None or r["producers"] <= k)
                                  for k in CUTOFFS},
        "feeds_precision": [precision(rows, k) for k in CUTOFFS],
        "reads_edges": len(reads), "reads_by_evidence": reads.count("evidence"),
        "reads_path_addressed": reads.count("path"), "reads_unverified": reads.count("unverified"),
        "reads_edges_legacy": legacy_reads,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "feeds_rows": rows}, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
