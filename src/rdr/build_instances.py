"""Build frozen reviewer instances from AppWorld gold runs.

For each candidate (task, W, argument) from rdr.inject and each variant, the plan runs in a subprocess world,
the run is validated, ground truth is derived under the created-row alignment, and the seven arms are packaged.
An instance is written atomically to runs/pilot/instances/<instance_id>/ (all arms or none):
trace.json, truth.json, gold_trace.json, meta.json, packages/<A..G>.txt. Every exclusion is logged to
runs/pilot/exclusions.jsonl with its reason and template.

Screen (cheap, no LLM): an instance is dropped when a heuristic that sees only arm A's evidence (call names,
final state, the symptom label) names the origin: (1) the earliest call whose API nouns cover the symptom
table's nouns; (2) the earliest call whose API nouns cover those of the last call before the final call.
The brief's write-attribution heuristic (earliest call writing a row a later call changed) is computed and
reported but not used to drop, because every update repair rewrites W's row, so it names the origin of every
persistent instance by construction (see docs/pilot_build.md).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from rdr.align import (check_aligned_clean_control, compare, make_aligned_truth, matched_symptom)
from rdr.inject import Candidate, find_candidates, repaired_record
from rdr.packager import ARMS, LeakageError, build_package
from rdr.trace import Trace
from rdr.truth import Partial, Truth

REPO = Path(__file__).resolve().parents[2]
VERBS = frozenset({"create", "add", "update", "delete", "remove", "move", "show", "search", "set", "mark", "send",
                   "like", "unlike", "follow", "unfollow", "approve", "deny", "remind", "download", "play", "to",
                   "from", "in", "of", "complete", "login", "logout"})
READ_PREFIXES = ("show_", "search_", "login", "logout", "get_")


# ---------------------------------------------------------------- screen

def _singular(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def nouns(name: str) -> set[str]:
    return {_singular(t) for t in name.split("_") if t and t not in VERBS}


def screen_guesses(trace: Trace, symptom: str) -> dict[str, int | None]:
    """Origin guesses of the cheap heuristics (call indices; None when a heuristic makes no guess)."""
    acting = [c for c in trace.calls if c.app not in ("supervisor", "admin") and not c.api.startswith(READ_PREFIXES)]

    def earliest_covering(target: set[str], exclude=None):
        if not target:
            return None
        for call in acting:
            if call.index != exclude and target <= nouns(call.api):
                return call.index
        return None

    symptom_nouns = nouns(symptom.split("#", 1)[0].split(".", 1)[1])
    finals = [c for c in trace.calls if (c.app, c.api) == ("supervisor", "complete_task")]
    before_final = [c for c in acting if not finals or c.index < finals[-1].index]
    last = before_final[-1] if before_final else None
    rewritten: dict[str, list[int]] = defaultdict(list)
    for call in trace.calls:
        for write in call.writes:
            rewritten[write.record].append(call.index)
    writes_guess = min((idx[0] for idx in rewritten.values() if len(set(idx)) > 1), default=None)
    return {"symptom_table": earliest_covering(symptom_nouns),
            "last_call": earliest_covering(nouns(last.api), exclude=last.index) if last else None,
            "rewritten_row": writes_guess}


def screened(guesses: dict, origin: int | None) -> bool:
    return origin is not None and origin in (guesses["symptom_table"], guesses["last_call"])


# ---------------------------------------------------------------- validation

class Excluded(Exception):
    pass


@dataclass
class Built:
    candidate: Candidate
    variant: str
    instance_id: str
    trace: Trace
    truth: Truth
    packages: dict[str, str]
    guesses: dict
    twin_of: str | None = None
    comparison: object = None
    extra: dict = field(default_factory=dict)


def _check_run(result, candidate: Candidate, gold_failed: int, variant: str) -> Trace:
    if result.plan_mismatch:
        raise Excluded("control flow reached a different call at W")
    if getattr(result, "repair_error", None):
        raise Excluded("corrupted call changed no row the repair could address")
    if not result.succeeded:
        raise Excluded("run raised an exception")
    if candidate.index in result.failed_calls:
        raise Excluded("corrupted call failed")
    if variant != "nonpersistent" and (result.repair_index is None or result.repair_index in result.failed_calls):
        raise Excluded("repair call missing or failed")
    others = [i for i in result.failed_calls if i not in (candidate.index, result.repair_index)]
    if len(others) > gold_failed:
        raise Excluded("wrong value made other calls fail")
    if candidate.held and variant != "clean" and not result.substituted and not candidate.natural:
        raise Excluded("no consumer received the held value")
    return result.trace


def _neutralised(trace: Trace, candidate: Candidate) -> dict:
    if candidate.neutral is None:
        return {}
    record = repaired_record(trace, candidate)
    if record is None:
        raise Excluded("repaired row not found in the corrupted call's writes")
    return {record: Partial(candidate.neutral)}


def evaluate_variant(candidate: Candidate, variant: str, result, gold: Trace, schema,
                     gold_failed: int = 0) -> tuple[Trace, Truth, object]:
    trace = _check_run(result, candidate, gold_failed, variant)
    trace.final_message = gold.final_message  # twins share the final message; the agent reports success
    iid = candidate.instance_id(variant)
    try:
        if variant == "persistent":
            neutral = _neutralised(trace, candidate)
            truth = make_aligned_truth(iid, trace, gold, schema, candidate.index, neutral, min_stale=2,
                                       expect_faulty=True)
            comparison = compare(trace, gold, schema, neutral)
        elif variant == "nonpersistent":
            truth = make_aligned_truth(iid, trace, gold, schema, candidate.index, None, min_stale=1,
                                       expect_faulty=True)
            comparison = None
        else:
            neutral = _neutralised(trace, candidate)
            comparison = check_aligned_clean_control(trace, gold, schema, neutral)
            truth = make_aligned_truth(iid, trace, gold, schema, None, neutral, expect_faulty=False)
    except ValueError as error:
        message = str(error)
        if "min_stale" in message:
            raise Excluded("fewer than 2 non-side-effect stale records") from None
        if "expect_faulty" in message:
            raise Excluded("final state equals gold" if variant != "clean" else "clean twin differs from gold") \
                from None
        if "neutralise" in message:
            raise Excluded("repair did not restore the row") from None
        if "differs from gold" in message:
            raise Excluded("clean twin differs from gold") from None
        if "no stale record" in message:
            raise Excluded("faulty run has only missing records") from None
        raise
    return trace, truth, comparison


def packages_for(trace: Trace, truth: Truth, instance_id: str, avoid: int, id_tables: dict) -> dict[str, str]:
    out = {}
    for arm in ARMS:
        try:
            out[arm] = build_package(arm, trace, truth.symptom, instance_id, avoid_calls=frozenset({avoid}),
                                     id_tables=id_tables)
        except LeakageError as error:
            raise Excluded(f"leakage: {error}") from None
        except ValueError as error:
            raise Excluded(f"arm {arm} could not be built: {error}") from None
    return out


def write_instance(root: Path, built: Built, gold: Trace) -> Path:
    """All files or none: build under a staging name, then rename into place."""
    final = root / built.instance_id
    staging = root / f".staging-{built.instance_id}"
    shutil.rmtree(staging, ignore_errors=True)
    (staging / "packages").mkdir(parents=True)
    built.trace.save(staging / "trace.json")
    built.truth.save(staging / "truth.json")
    gold.save(staging / "gold_trace.json")
    meta = {"instance_id": built.instance_id, "variant": built.variant, "task_id": built.candidate.task_id,
            "generator": built.candidate.generator, "template": built.candidate.template,
            "origin_index": built.truth.origin_index, "twin_of": built.twin_of, "screen_guesses": built.guesses,
            "consumers": {"held": built.candidate.consumers, "natural": built.candidate.natural}, **built.extra}
    (staging / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    for arm, text in built.packages.items():
        (staging / "packages" / f"{arm}.txt").write_text(text)
    if final.exists():
        shutil.rmtree(final)
    os.rename(staging, final)
    return final


# ---------------------------------------------------------------- orchestration

def spread(cands: list[Candidate], per_template: int) -> list[Candidate]:
    """At most `per_template` candidates per (task, template): first, second, middle and last positions."""
    groups: dict[tuple, list[Candidate]] = defaultdict(list)
    for c in cands:
        groups[(c.task_id, c.template)].append(c)
    out = []
    for group in groups.values():
        group.sort(key=lambda c: c.index)
        picks = [0, 1, len(group) // 2, len(group) - 1]
        seen = []
        for p in picks:
            if 0 <= p < len(group) and group[p] not in seen:
                seen.append(group[p])
        out.extend(seen[:per_template])
    return out


@dataclass
class Builder:
    gold_dir: Path
    out_dir: Path
    schema: object
    api_docs: dict
    id_tables: dict
    workers: int = 10
    exclusions: list[dict] = field(default_factory=list)
    golds: dict[str, Trace] = field(default_factory=dict)

    def gold(self, task_id: str) -> Trace:
        if task_id not in self.golds:
            self.golds[task_id] = Trace.load(self.gold_dir / task_id / "trace.json")
        return self.golds[task_id]

    def exclude(self, candidate: Candidate, variant: str, reason: str) -> None:
        self.exclusions.append({"instance_id": candidate.instance_id(variant), "task_id": candidate.task_id,
                                "generator": candidate.generator, "template": candidate.template,
                                "variant": variant, "reason": reason})

    def run_variant(self, candidate: Candidate, variant: str, twin: Built | None = None) -> Built | None:
        from rdr.appworld_adapter import run_task

        gold = self.gold(candidate.task_id)
        try:
            result = run_task(candidate.task_id, candidate.plan(variant))
            failed_file = self.gold_dir / candidate.task_id / "failed_calls.json"
            gold_failed = len(json.loads(failed_file.read_text())) if failed_file.exists() else 0
            trace, truth, comparison = evaluate_variant(candidate, variant, result, gold, self.schema, gold_failed)
            if variant == "clean":
                if twin is None:
                    raise Excluded("no persistent twin")
                truth.symptom = matched_symptom(candidate.instance_id(variant), twin.comparison, comparison,
                                                trace, twin.trace)
            guesses = screen_guesses(trace, truth.symptom)
            if screened(guesses, truth.origin_index):
                raise Excluded("heuristic screen")
            packages = packages_for(trace, truth, candidate.instance_id(variant), candidate.index, self.id_tables)
        except Excluded as reason:
            self.exclude(candidate, variant, str(reason))
            return None
        except ValueError as error:
            self.exclude(candidate, variant, f"ground truth: {str(error)[:80]}")
            return None
        return Built(candidate, variant, candidate.instance_id(variant), trace, truth, packages, guesses,
                     twin.instance_id if twin else None, comparison)

    def run_many(self, jobs) -> list[Built]:
        with ThreadPoolExecutor(self.workers) as pool:
            return [b for b in pool.map(lambda job: self.run_variant(*job), jobs) if b is not None]


def select(persistent: list[Built], nonpersistent: list[Built], n_persistent: int, n_nonpersistent: int,
           cap: int = 2) -> tuple[list[Built], list[Built]]:
    """Fill as much generator capacity as possible (at most `cap` faulty instances per generator) while keeping
    the persistent : non-persistent ratio near the requested one. Order: non-persistent from generators with
    no persistent instance; one persistent per generator (instances with a clean twin first); a non-persistent
    twin of the same wrong action where the generator has room; a second persistent; then any remaining room.
    Within a generator, different tasks are used before a task repeats."""
    p_by: dict[str, list[Built]] = defaultdict(list)
    n_by: dict[str, list[Built]] = defaultdict(list)
    for b in sorted(persistent, key=lambda b: (not b.extra.get("has_twin"), b.instance_id)):
        p_by[b.candidate.generator].append(b)
    for b in sorted(nonpersistent, key=lambda b: b.instance_id):
        n_by[b.candidate.generator].append(b)
    gens = sorted(set(p_by) | set(n_by))
    total = sum(min(cap, len(p_by[g]) + len(n_by[g])) for g in gens)
    ratio = n_nonpersistent / (n_persistent + n_nonpersistent) if n_persistent + n_nonpersistent else 0
    want_n = min(n_nonpersistent, sum(min(cap, len(n_by[g])) for g in gens), round(total * ratio))
    want_p = min(n_persistent, total - want_n)
    load: Counter = Counter()
    chosen_p: list[Built] = []
    chosen_n: list[Built] = []

    def take(pool: list[Built], chosen: list[Built], prefer=None) -> None:
        gen = pool[0].candidate.generator
        tasks = {b.candidate.task_id for b in chosen_p + chosen_n if b.candidate.generator == gen}
        ranked = sorted(pool, key=lambda b: (prefer is not None and b.candidate.key != prefer,
                                             b.candidate.task_id in tasks))
        pick = ranked[0]
        pool.remove(pick)
        chosen.append(pick)
        load[gen] += 1

    for _ in range(cap):
        for g in gens:
            if not p_by[g] and n_by[g] and load[g] < cap and len(chosen_n) < want_n:
                take(n_by[g], chosen_n)
    for g in gens:
        if p_by[g] and load[g] < cap and len(chosen_p) < want_p:
            take(p_by[g], chosen_p)
    for b in list(chosen_p):
        g = b.candidate.generator
        if n_by[g] and load[g] < cap and len(chosen_n) < want_n:
            take(n_by[g], chosen_n, prefer=b.candidate.key)
    progress = True
    while progress:
        progress = False
        for g in gens:
            if p_by[g] and load[g] < cap and len(chosen_p) < want_p:
                take(p_by[g], chosen_p)
                progress = True
        for g in gens:
            if n_by[g] and load[g] < cap and len(chosen_n) < want_n:
                take(n_by[g], chosen_n)
                progress = True
    return chosen_p, chosen_n


def size_stats(instances: list[Built]) -> dict[str, dict[str, int]]:
    stats = {}
    for arm in ARMS:
        sizes = [len(b.packages[arm]) for b in instances]
        if sizes:
            stats[arm] = {"min": min(sizes), "median": int(statistics.median(sizes)), "max": max(sizes)}
    return stats


def main(argv=None) -> None:
    from rdr.appworld_adapter import load_schema
    from rdr.freeze import write_manifest
    from rdr.graph import id_key_tables

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=REPO / "runs" / "gold")
    parser.add_argument("--out", type=Path, default=REPO / "runs" / "pilot")
    parser.add_argument("--persistent", type=int, default=20)
    parser.add_argument("--nonpersistent", type=int, default=10)
    parser.add_argument("--clean", type=int, default=10)
    parser.add_argument("--per-template", type=int, default=4)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args(argv)

    schema = load_schema(REPO / "runs" / "schema.json")
    docs = {f.stem: json.loads(f.read_text()) for f in (REPO / "appworld_root/data/api_docs/standard").glob("*.json")}
    id_tables = id_key_tables(docs, schema.tables, schema.foreign_keys)
    gate = json.loads((args.gold / "determinism.json").read_text())
    tasks = sorted(t for t, v in gate.items() if v["passed"])
    builder = Builder(args.gold, args.out, schema, docs, id_tables, args.workers)
    candidates = [c for t in tasks for c in find_candidates(builder.gold(t), docs, id_tables)]
    pool = spread(candidates, args.per_template)
    capable = [c for c in pool if c.persistent_capable]

    persistent = builder.run_many([(c, "persistent") for c in capable])
    by_key = {b.candidate.key: b for b in persistent}
    cleans = builder.run_many([(b.candidate, "clean", b) for b in persistent])
    for clean in cleans:
        by_key[clean.candidate.key].extra["has_twin"] = True
    nonpersistent = builder.run_many([(c, "nonpersistent") for c in pool])

    chosen_p, chosen_n = select(persistent, nonpersistent, args.persistent, args.nonpersistent)
    twin_of = {b.instance_id: b for b in chosen_p}
    chosen_c: list[Built] = []
    gens_c: Counter = Counter()
    for clean in sorted(cleans, key=lambda c: c.instance_id):
        if clean.twin_of in twin_of:
            chosen_c.append(clean)
    chosen_c.sort(key=lambda c: (c.candidate.generator, c.instance_id))
    picked_c: list[Built] = []
    while len(picked_c) < args.clean and chosen_c:
        progress = False
        for clean in list(chosen_c):
            if gens_c[clean.candidate.generator] == min(gens_c[c.candidate.generator] for c in chosen_c):
                picked_c.append(clean)
                gens_c[clean.candidate.generator] += 1
                chosen_c.remove(clean)
                progress = True
                break
        if not progress:
            break
    for b in picked_c:
        twin_of[b.twin_of].extra["clean_twin"] = b.instance_id

    instances_dir = args.out / "instances"
    shutil.rmtree(instances_dir, ignore_errors=True)
    instances_dir.mkdir(parents=True)
    chosen = chosen_p + chosen_n + picked_c
    for built in chosen:
        write_instance(instances_dir, built, builder.gold(built.candidate.task_id))
    manifest = write_manifest(instances_dir)
    import hashlib
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()

    with (args.out / "exclusions.jsonl").open("w") as fh:
        for row in builder.exclusions:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    all_gens = sorted({t.split("_", 1)[0] for t in tasks})
    pilot_gens = sorted({b.candidate.generator for b in chosen})
    summary = {
        "candidates": len(candidates), "candidates_run": len(pool), "persistent_capable_run": len(capable),
        "valid": {"persistent": len(persistent), "clean": len(cleans), "nonpersistent": len(nonpersistent)},
        "chosen": {"persistent": len(chosen_p), "nonpersistent": len(chosen_n), "clean": len(picked_c)},
        "by_generator": {g: Counter(b.variant for b in chosen if b.candidate.generator == g) for g in pilot_gens},
        "by_template": dict(Counter(f"{b.variant} {b.candidate.template}" for b in chosen)),
        "pilot_generators": pilot_gens,
        "reserved_generators": [g for g in all_gens if g not in pilot_gens],
        "exclusions_by_reason": dict(Counter(r["reason"] for r in builder.exclusions).most_common()),
        "exclusions_by_reason_and_variant": dict(Counter(f"{r['variant']}: {r['reason']}"
                                                         for r in builder.exclusions).most_common()),
        "screen_drops": sum(r["reason"] == "heuristic screen" for r in builder.exclusions),
        "writes_heuristic_hits_among_chosen": sum(b.guesses["rewritten_row"] == b.truth.origin_index
                                                   for b in chosen if b.truth.origin_index is not None),
        "package_chars": size_stats(chosen),
        "manifest_sha256": digest,
    }
    (args.out / "build_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=dict))
    print(json.dumps(summary, indent=2, sort_keys=True, default=dict))


if __name__ == "__main__":
    main()
