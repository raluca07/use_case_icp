"""Gate 2 Haiku pilot: run every frozen instance through arms A to G, repeat arms B and C on 10 instances, score
every review intention-to-treat, and write the results table.

Usage (from the repo root, `PYTHONPATH=src .venv/bin/python -m rdr.pilot run|analyse`).
"""
from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
import tempfile
import time
import zlib
from pathlib import Path

from rdr.freeze import verify_manifest
from rdr.runner import RETRY_PATTERN, ReviewError, review_with_backoff
from rdr.scorer import score
from rdr.trace import Trace
from rdr.truth import Truth

MODEL = "claude-haiku-5-5"
EFFORT = "medium"
ARMS = "ABCDEFG"
REPEAT_ARMS = ("B", "C")
REPEATS = (1, 2, 3)
N_REPEAT_INSTANCES = 10
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = zlib.crc32(b"rdr-pilot-bootstrap-v1")
LONG_CALL_SECONDS = 600
CONTRASTS = (("G", "B"), ("C", "A"), ("G", "C"), ("F", "C"), ("D", "C"), ("E", "D"))


# ---------------------------------------------------------------- instances and plan

def load_instances(instances_dir: Path) -> list[dict]:
    """Instances sorted by id, each with meta, truth, the labels its trace touched and its packages."""
    out = []
    for path in sorted(p for p in instances_dir.iterdir() if p.is_dir()):
        meta = json.loads((path / "meta.json").read_text())
        out.append({
            "id": meta["instance_id"], "generator": meta["generator"], "variant": meta["variant"], "dir": path,
            "truth": Truth.load(path / "truth.json"),
            "known": set(Trace.load(path / "trace.json").touched_records()),
        })
    return sorted(out, key=lambda i: i["id"])


def _crc(instance_id: str) -> int:
    return zlib.crc32(instance_id.encode("utf-8"))


def choose_repeat_instances(instances: list[dict], n: int = N_REPEAT_INSTANCES) -> list[str]:
    """Variants share the n slots in proportion to their size (largest remainder, ties by variant name); inside a
    variant the instances with the smallest crc32 of the id are taken. Deterministic."""
    by_variant: dict[str, list[str]] = {}
    for inst in instances:
        by_variant.setdefault(inst["variant"], []).append(inst["id"])
    total = sum(len(v) for v in by_variant.values())
    quota = {v: n * len(ids) / total for v, ids in by_variant.items()}
    alloc = {v: min(len(by_variant[v]), math.floor(q)) for v, q in quota.items()}
    for v in sorted(quota, key=lambda v: (-(quota[v] - math.floor(quota[v])), v)):
        if sum(alloc.values()) >= n:
            break
        if alloc[v] < len(by_variant[v]):
            alloc[v] += 1
    chosen = []
    for v, ids in by_variant.items():
        chosen += sorted(ids, key=lambda i: (_crc(i), i))[:alloc[v]]
    return sorted(chosen)


def plan_jobs(instances: list[dict]) -> list[tuple[str, str, int]]:
    """(instance id, arm, rep). rep 0 is the main review. Mains first, then the repeats."""
    jobs = [(i["id"], arm, 0) for i in instances for arm in ARMS]
    repeat_ids = choose_repeat_instances(instances)
    jobs += [(iid, arm, k) for k in REPEATS for iid in repeat_ids for arm in REPEAT_ARMS]
    return jobs


def review_path(reviews_dir: Path, instance_id: str, arm: str, rep: int) -> Path:
    name = f"{arm}.json" if rep == 0 else f"{arm}.rep{rep}.json"
    return reviews_dir / instance_id / name


def failed_path(path: Path) -> Path:
    return path.with_name(path.stem + ".failed.json")


# ---------------------------------------------------------------- running

def run(instances_dir: Path, reviews_dir: Path, log_path: Path, claude_cmd=("claude",), model: str = MODEL,
        effort: str = EFFORT, sleep_fn=time.sleep, waits=(60, 300, 1800), jobs=None) -> dict:
    """Run every planned review (or the given `jobs`). Stops cleanly when the runner's backoff cannot outlast a
    usage limit."""
    problems = verify_manifest(instances_dir)
    if problems:
        raise RuntimeError(f"freeze check failed: {problems[:5]}")
    instances = load_instances(instances_dir)
    by_id = {i["id"]: i for i in instances}
    jobs = plan_jobs(instances) if jobs is None else jobs
    log_path.parent.mkdir(parents=True, exist_ok=True)
    session = {"event": "session_start", "t": time.time(), "planned": len(jobs)}
    summary = {"planned": len(jobs), "done": 0, "resumed": 0, "failed": 0, "stopped": None}

    def log(row: dict) -> None:
        with log_path.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    log(session)
    for instance_id, arm, rep in jobs:
        out_path = review_path(reviews_dir, instance_id, arm, rep)
        package = (by_id[instance_id]["dir"] / "packages" / f"{arm}.txt").read_text()
        row = {"event": "call", "instance": instance_id, "arm": arm, "rep": rep}
        existed = out_path.exists()
        row["t_start"] = time.time()
        try:
            with tempfile.TemporaryDirectory(prefix="rdr-review-") as workdir:  # fresh and empty per call
                record = review_with_backoff(package, out_path, model, effort, Path(workdir),
                                             waits=waits, sleep_fn=sleep_fn, claude_cmd=claude_cmd)
        except ReviewError as err:
            row.update(t_end=time.time(), status="failed", reason=str(err)[-600:])
            log(row)
            summary["failed"] += 1
            if RETRY_PATTERN.search(str(err).lower()):
                summary["stopped"] = f"{instance_id}/{arm}/rep{rep}: {str(err)[-600:]}"
                break
            continue
        failed_path(out_path).unlink(missing_ok=True)  # an earlier failed attempt is superseded by this record
        row.update(t_end=time.time(), status="resumed" if existed else "done",
                   wall_seconds=record.get("wall_seconds"))
        log(row)
        summary["resumed" if existed else "done"] += 1
    log({"event": "session_end", "t": time.time(), **summary})
    return summary


# ---------------------------------------------------------------- scoring

def _load_record(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and isinstance(record.get("answer"), dict) else None


def score_all(instances: list[dict], reviews_dir: Path) -> list[dict]:
    """One row per planned review. A missing or failed review is a miss on every metric (intention to treat)."""
    rows = []
    for instance_id, arm, rep in plan_jobs(instances):
        inst = next(i for i in instances if i["id"] == instance_id)
        truth = inst["truth"]
        path = review_path(reviews_dir, instance_id, arm, rep)
        record = _load_record(path)
        base = {"instance_id": instance_id, "arm": arm, "rep": rep, "generator": inst["generator"],
                "variant": inst["variant"], "is_faulty": truth.is_faulty}
        if record is None:
            miss = {"failed": True, "detection_correct": False, "origin_hit": False if truth.is_faulty else None,
                    "stale_precision": 0.0 if truth.is_faulty else None,
                    "stale_recall": 0.0 if truth.is_faulty else None,
                    "false_stale_count": None if truth.is_faulty else 0, "named_symptom": False,
                    "unknown_labels": 0, "origin_call": "missing"}
            rows.append({**base, **miss})
            continue
        s = score(record["answer"], truth, known_labels=inst["known"])
        s.pop("instance_id", None)
        rows.append({**base, **s, "failed": False, "origin_call": record["answer"]["origin_call"]})
    return rows


# ---------------------------------------------------------------- statistics

def sign_test_p(b: int, c: int) -> float:
    """Exact two-sided sign test on b and c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def cluster_bootstrap(per_cluster: dict[str, tuple[int, int]], seed: int = BOOTSTRAP_SEED,
                      resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[float, float]:
    """95% percentile interval of the pooled rate when whole clusters (generators) are resampled."""
    rng = random.Random(seed)
    clusters = sorted(per_cluster)
    stats = []
    for _ in range(resamples):
        k = n = 0
        for _ in clusters:
            a, b = per_cluster[rng.choice(clusters)]
            k, n = k + a, n + b
        if n:
            stats.append(k / n)
    stats.sort()
    return stats[int(0.025 * (len(stats) - 1))], stats[int(math.ceil(0.975 * (len(stats) - 1)))]


def _pct(k: int, n: int) -> str:
    return "n/a" if n == 0 else f"{k}/{n} ({100 * k / n:.0f}%)"


def _mean(values: list[float]) -> str:
    return "n/a" if not values else f"{100 * statistics.mean(values):.0f}%"


def _tokens(record: dict) -> int:
    u = record.get("usage") or {}
    return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                             "cache_read_input_tokens"))


def _side_tokens(record: dict, model: str) -> int:
    usage = (record.get("envelope") or {}).get("modelUsage") or {}
    total = 0
    for name, u in usage.items():
        if name != model and isinstance(u, dict):
            total += sum(int(u.get(k) or 0) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                                                       "cacheCreationInputTokens"))
    return total


def _med_max(values: list[float]) -> str:
    return "n/a" if not values else f"{statistics.median(values):,.0f} / {max(values):,.0f}"


# ---------------------------------------------------------------- analysis and report

def analyse(instances_dir: Path, reviews_dir: Path, log_path: Path, scores_path: Path, report_path: Path) -> dict:
    instances = load_instances(instances_dir)
    rows = score_all(instances, reviews_dir)
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    scores_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    main = {(r["instance_id"], r["arm"]): r for r in rows if r["rep"] == 0}
    ids = [i["id"] for i in instances]
    variant = {i["id"]: i["variant"] for i in instances}
    generator = {i["id"]: i["generator"] for i in instances}
    faulty = [i for i in ids if variant[i] != "clean"]
    persistent = [i for i in ids if variant[i] == "persistent"]
    nonpers = [i for i in ids if variant[i] == "nonpersistent"]
    clean = [i for i in ids if variant[i] == "clean"]

    def count(arm: str, group: list[str], field: str) -> tuple[int, int]:
        return sum(1 for i in group if main[(i, arm)][field]), len(group)

    table: dict[str, dict] = {}
    for arm in ARMS:
        rs = {i: main[(i, arm)] for i in ids}
        prec = [rs[i]["stale_precision"] for i in faulty if rs[i]["stale_precision"] is not None]
        rec = [rs[i]["stale_recall"] for i in faulty if rs[i]["stale_recall"] is not None]
        table[arm] = {
            "detect": count(arm, ids, "detection_correct"), "origin": count(arm, faulty, "origin_hit"),
            "origin_p": count(arm, persistent, "origin_hit"), "origin_n": count(arm, nonpers, "origin_hit"),
            "precision": prec, "recall": rec,
            "false_stale_total": sum(rs[i]["false_stale_count"] or 0 for i in clean),
            "false_stale_inst": sum(1 for i in clean if (rs[i]["false_stale_count"] or 0) > 0),
            "named_symptom": count(arm, clean, "named_symptom"),
            "unknown": sum(rs[i]["unknown_labels"] or 0 for i in ids),
            "failed": sum(1 for i in ids if rs[i]["failed"]),
        }

    def ci(arm: str, metric: str) -> tuple[float, float]:
        group, field = (ids, "detection_correct") if metric == "detect" else (faulty, "origin_hit")
        per: dict[str, list[int]] = {}
        for i in group:
            cell = per.setdefault(generator[i], [0, 0])
            cell[0] += 1 if main[(i, arm)][field] else 0
            cell[1] += 1
        return cluster_bootstrap({g: (a, b) for g, (a, b) in per.items()})

    contrasts = []
    for x, y in CONTRASTS:
        for metric, group, field in (("origin hit", faulty, "origin_hit"), ("detection", ids, "detection_correct")):
            xs = [bool(main[(i, x)][field]) for i in group]
            ys = [bool(main[(i, y)][field]) for i in group]
            b = sum(1 for a, c in zip(xs, ys) if a and not c)
            c = sum(1 for a, c_ in zip(xs, ys) if c_ and not a)
            contrasts.append({"pair": f"{x} vs {y}", "metric": metric, "n": len(group), "x": sum(xs), "y": sum(ys),
                              "x_only": b, "y_only": c, "p": sign_test_p(b, c)})

    # repeat consistency
    repeat_ids = choose_repeat_instances(instances)
    consistency = {}
    by_key = {(r["instance_id"], r["arm"], r["rep"]): r for r in rows}
    for arm in REPEAT_ARMS:
        all_same = pairwise_num = pairwise_den = complete = 0
        hits_by_run = {k: 0 for k in (0, *REPEATS)}
        for i in repeat_ids:
            runs = [by_key[(i, arm, k)] for k in (0, *REPEATS)]
            for k, r in zip((0, *REPEATS), runs):
                hits_by_run[k] += 1 if r["origin_hit"] else 0
            if any(r["failed"] for r in runs):
                continue
            complete += 1
            origins = [r["origin_call"] for r in runs]
            all_same += 1 if len(set(origins)) == 1 else 0
            for a in range(4):
                for c in range(a + 1, 4):
                    pairwise_den += 1
                    pairwise_num += 1 if origins[a] == origins[c] else 0
        consistency[arm] = {"complete": complete, "all_same": all_same, "pair_num": pairwise_num,
                            "pair_den": pairwise_den, "hits_by_run": hits_by_run}

    facts = _run_facts(rows, reviews_dir, log_path, instances)
    gate2 = _gate2(table)
    report = render(table, ci, contrasts, consistency, facts, gate2, repeat_ids, instances, variant, ids, faulty,
                    persistent, nonpers, clean)
    report_path.write_text(report)
    return {"table": table, "contrasts": contrasts, "consistency": consistency, "facts": facts, "gate2": gate2,
            "report": report}


def _gate2(table: dict) -> dict:
    a = table["A"]["origin"]
    a_rate = a[0] / a[1]
    mid = {arm: t["origin"][0] / t["origin"][1] for arm, t in table.items()
           if 0.2 <= t["origin"][0] / t["origin"][1] <= 0.8}
    return {"a_rate": a_rate, "a_ok": a_rate < 0.8, "mid": mid, "mid_ok": bool(mid),
            "passed": a_rate < 0.8 and bool(mid)}


def _run_facts(rows: list[dict], reviews_dir: Path, log_path: Path, instances: list[dict]) -> dict:
    planned = len(rows)
    completed = sum(1 for r in rows if not r["failed"])
    failures = {arm: sum(1 for r in rows if r["arm"] == arm and r["failed"]) for arm in ARMS}
    tokens: dict[str, list[int]] = {a: [] for a in ARMS}
    side: dict[str, list[int]] = {a: [] for a in ARMS}
    wall: dict[str, list[float]] = {a: [] for a in ARMS}
    for r in rows:
        record = _load_record(review_path(reviews_dir, r["instance_id"], r["arm"], r["rep"]))
        if record is None:
            continue
        if r["rep"] == 0:
            tokens[r["arm"]].append(_tokens(record))
        side[r["arm"]].append(_side_tokens(record, MODEL))
        if record.get("wall_seconds") is not None:
            wall[r["arm"]].append(record["wall_seconds"])
    sessions, new_calls, active = [], 0, 0.0
    long_calls: list[tuple[float, str]] = []  # calls over 10 minutes: outages and backoff, not throughput
    normal_calls, normal_seconds = 0, 0.0
    first = last = None
    if log_path.exists():
        start = None
        for line in log_path.read_text().splitlines():
            row = json.loads(line)
            if row["event"] == "call":
                elapsed = row["t_end"] - row["t_start"]
                if elapsed > LONG_CALL_SECONDS:
                    long_calls.append((elapsed, f"{row['instance']}/{row['arm']}/rep{row['rep']} {row['status']}"))
                else:
                    normal_calls += 1 if row["status"] == "done" else 0
                    normal_seconds += elapsed
            if row["event"] == "session_start":
                start = row["t"]
                first = start if first is None else first
            elif row["event"] == "session_end" and start is not None:
                active += row["t"] - start
                last = row["t"]
                new_calls += row.get("done", 0)
                sessions.append((start, row["t"]))
                start = None
    return {"planned": planned, "completed": completed, "failures": failures, "tokens": tokens, "side": side,
            "wall": wall, "first": first, "last": last, "active_seconds": active, "new_calls": new_calls,
            "sessions": len(sessions), "long_calls": long_calls, "normal_calls": normal_calls,
            "normal_seconds": normal_seconds}


def _fmt_t(t: float | None) -> str:
    return "n/a" if t is None else time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(t))


def render(table, ci, contrasts, consistency, facts, gate2, repeat_ids, instances, variant, ids, faulty,
           persistent, nonpers, clean) -> str:
    L: list[str] = []
    w = L.append
    w("# Gate 2 Haiku pilot results")
    w("")
    w("Model `claude-haiku-5-5`, effort `medium`, one fresh empty working directory per call. Frozen set of "
      f"{len(ids)} instances ({len(persistent)} persistent, {len(nonpers)} non-persistent, {len(clean)} clean) over "
      "7 generators, manifest sha256 `ba9299df7bcfd796e416db0ac3f2c14fe1f66210145a34dce79673842def9675`. "
      "Counts, names and mechanisms only; no AppWorld data values. A failed or missing review counts as a miss "
      "on every metric (intention to treat) and is also counted separately below.")
    w("")
    w("## 1. Run facts")
    w("")
    hours = facts["active_seconds"] / 3600
    w(f"- Calls completed / planned: {facts['completed']} / {facts['planned']} "
      f"(main reviews {7 * len(ids)}, repeats {len(repeat_ids) * len(REPEAT_ARMS) * len(REPEATS)}).")
    w(f"- Wall-clock start {_fmt_t(facts['first'])}, end {_fmt_t(facts['last'])}, {facts['sessions']} session(s), "
      f"active time {hours:.2f} h.")
    if hours > 0:
        w(f"- Calls per hour sustained: {facts['new_calls'] / hours:.1f} "
          f"({facts['new_calls']} new calls logged over the active time).")
    if facts["normal_seconds"] > 0:
        w(f"- Calls per hour excluding calls longer than {LONG_CALL_SECONDS // 60} minutes: "
          f"{facts['normal_calls'] / (facts['normal_seconds'] / 3600):.1f} "
          f"({facts['normal_calls']} calls, {facts['normal_seconds'] / 3600:.2f} h). "
          "The sustained figure above is dragged down by the long calls; this one is the working rate.")
    if facts["long_calls"]:
        w("- Calls over 10 minutes (they overlap a network outage or machine sleep, cause not recorded): "
          + "; ".join(f"{name} took {sec:,.0f} s" for sec, name in facts["long_calls"]) + ".")
    w("- Failures per arm: " + ", ".join(f"{a} {facts['failures'][a]}" for a in ARMS) + ". "
      "A failed call is a miss on every metric (intention to treat). The one failure ended in an API connection error (DNS lookup failed), not a usage limit, and no usage limit was hit; it was not re-run.")
    w("")
    w("| Arm | main input tokens, median / max | side-call tokens, median / max | wall s per call, median / max |")
    w("|---|---|---|---|")
    for a in ARMS:
        w(f"| {a} | {_med_max(facts['tokens'][a])} | {_med_max(facts['side'][a])} | {_med_max(facts['wall'][a])} |")
    w("")
    w("Main-call input tokens are input plus cache creation plus cache read from the envelope usage. Side-call "
      "tokens are every non-requested model in the envelope's modelUsage, all token kinds summed. Wall seconds "
      "are over all completed calls of the arm, repeats included.")
    w("")
    w("## 2. Main table")
    w("")
    w(f"Detection over all {len(ids)}. Origin hit on the {len(faulty)} faulty instances, split into "
      f"{len(persistent)} persistent and {len(nonpers)} non-persistent. Precision and recall are means over faulty "
      "instances where defined (precision needs at least one claim after removing the symptom and side-effect rows; "
      "a failed review scores 0 on both). False-stale count is the total of wrong claimed records on the "
      f"{len(clean)} clean twins, with the number of clean instances that have any in brackets.")
    w("")
    w("| Arm | Detection | Origin hit (faulty) | Origin hit (persistent) | Origin hit (non-persistent) | "
      "Stale precision (n defined) | Stale recall (n defined) | False-stale on clean | Clean rate | "
      "Named symptom on clean | Unknown labels | Failed |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for a in ARMS:
        t = table[a]
        w(f"| {a} | {_pct(*t['detect'])} | {_pct(*t['origin'])} | {_pct(*t['origin_p'])} | {_pct(*t['origin_n'])} | "
          f"{_mean(t['precision'])} ({len(t['precision'])}) | {_mean(t['recall'])} ({len(t['recall'])}) | "
          f"{t['false_stale_total']} claims ({t['false_stale_inst']} inst) | "
          f"{_pct(t['false_stale_inst'], len(clean))} | {_pct(*t['named_symptom'])} | {t['unknown']} | "
          f"{t['failed']} |")
    w("")
    w("## 3. Uncertainty")
    w("")
    w("95% percentile intervals from a cluster bootstrap over generators: 7 clusters, 10,000 resamples, seed "
      f"{BOOTSTRAP_SEED} (zlib.crc32 of the constant `rdr-pilot-bootstrap-v1`). With only 7 clusters the intervals "
      "are wide and rough; read them as a range of what generator-level luck alone could produce, not as precise "
      "bounds.")
    w("")
    w("| Arm | Origin hit (faulty) | 95% CI | Detection (all) | 95% CI |")
    w("|---|---|---|---|---|")
    for a in ARMS:
        o, d = ci(a, "origin"), ci(a, "detect")
        t = table[a]
        w(f"| {a} | {_pct(*t['origin'])} | {100 * o[0]:.0f}% to {100 * o[1]:.0f}% | {_pct(*t['detect'])} | "
          f"{100 * d[0]:.0f}% to {100 * d[1]:.0f}% |")
    w("")
    w("## 4. Paired contrasts")
    w("")
    w("Paired by instance, main reviews only. The sign test is exact and two-sided on the discordant pairs. It is "
      "descriptive: n is tiny, instances within a generator are not independent, and no multiplicity correction "
      "is applied.")
    w("")
    w("| Contrast (X vs Y) | Metric | X rate | Y rate | X only right | Y only right | Sign test p |")
    w("|---|---|---|---|---|---|---|")
    for c in contrasts:
        w(f"| {c['pair']} | {c['metric']} | {_pct(c['x'], c['n'])} | {_pct(c['y'], c['n'])} | {c['x_only']} | "
          f"{c['y_only']} | {c['p']:.3f} |")
    w("")
    w("G vs B asks what the graph adds to the log. C vs A asks what a graph adds to nothing. G vs C asks what the "
      "log adds to the graph. F vs C is the fake-graph control. D vs C is the neighbourhood against the full "
      "graph. E vs D is the random slice against the targeted one.")
    w("")
    w("## 5. Repeat consistency")
    w("")
    w(f"{len(repeat_ids)} instances were repeated three more times on arms B and C: "
      + ", ".join(f"`{i}` ({variant[i]})" for i in repeat_ids) + ". Agreement is on the origin_call value across "
      "the 4 runs (main plus 3 repeats); an instance with any failed run is left out of the agreement counts.")
    w("")
    w("| Arm | Instances with 4 valid runs | All 4 runs name the same origin | Pairwise agreement | "
      "Origin hits in main / rep1 / rep2 / rep3 (of " + str(len(repeat_ids)) + ") |")
    w("|---|---|---|---|---|")
    for a in REPEAT_ARMS:
        c = consistency[a]
        hits = " / ".join(str(c["hits_by_run"][k]) for k in (0, *REPEATS))
        w(f"| {a} | {c['complete']} | {_pct(c['all_same'], c['complete'])} | "
          f"{_pct(c['pair_num'], c['pair_den'])} | {hits} |")
    w("")
    w("## 6. Gate 2 pass rule")
    w("")
    mid = ", ".join(f"{a} {100 * r:.0f}%" for a, r in gate2["mid"].items()) or "none"
    w(f"- Arm A origin hit {table['A']['origin'][0]}/{table['A']['origin'][1]} = {100 * gate2['a_rate']:.0f}%: "
      f"{'below' if gate2['a_ok'] else 'NOT below'} 80%.")
    w(f"- Arms with origin hit between 20% and 80% inclusive: {mid}.")
    w(f"- **Gate 2 origin-hit rule: {'PASS' if gate2['passed'] else 'FAIL'}.**")
    w("")
    w("## 7. Caveats")
    w("")
    w("- Held-value fault model. All 9 persistent instances use held-value consumers: the agent keeps using the "
      "wrong value it had when it made the write W, and the wrong value does not travel from W to the stale "
      "records through the API. W is linked to the stale records through the repair's writes edge on W's row and "
      "through shared feeds sources, not through a W-to-consumer data edge. This is a fault of the agent's belief "
      "carried across calls.")
    w("- Arm C contains the origin node in all 14 faulty instances, and the rewritten-row cue (the repair rewrites "
      "W's row) names the origin of 9 of 9 persistent instances. Arm D's 2-hop neighbourhood around the symptom "
      "contains an edge of the origin in 0 of 9 persistent instances (3 of 5 non-persistent). Expect C and G to be "
      "strong and D to be weak on persistent faults by construction, so C vs D differences here do not show that "
      "the graph in general beats a neighbourhood.")
    w("- Only 7 generators contribute (the pilot set is 9 persistent, 5 non-persistent and 9 clean, not 20 / 10 / "
      "10), at most 2 faulty instances per generator. Intervals and p-values are descriptive.")
    w("- The arm-A screen keeps only W positions that are not the first call of their API, a selection effect on "
      "instance shape. Package sizes are 10 to 100 times the Gate 0 smoke packages, so throughput here reflects "
      "long inputs.")
    w("")
    return "\n".join(L)


def main(argv: list[str]) -> int:
    root = Path("runs/pilot")
    instances_dir, reviews_dir, log_path = root / "instances", root / "reviews", root / "run_log.jsonl"
    if argv and argv[0] == "run":
        summary = run(instances_dir, reviews_dir, log_path)
        print(json.dumps(summary, indent=2))
        return 0 if summary["stopped"] is None else 2
    if argv and argv[0] == "analyse":
        result = analyse(instances_dir, reviews_dir, log_path, root / "scores.jsonl", Path("docs/pilot_results.md"))
        print(json.dumps({"facts_completed": result["facts"]["completed"], "gate2": result["gate2"]}, indent=2))
        return 0
    print("usage: python -m rdr.pilot run|analyse", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
