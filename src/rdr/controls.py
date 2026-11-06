"""Control arms H to M on the frozen Gate 2 pilot set (Raluca's review, 6 Nov 2026).

derive:  copy the frozen pilot instances, rebuild arms A to G and require them byte-identical to the frozen
         packages (this proves the anchor call and the id tables are the ones the build used), then add the six
         control packages and freeze the copy under its own manifest. The pilot set itself is never touched.
run:     one Haiku review per instance and control arm, same runner and settings as the pilot.
analyse: score H to M next to the pilot's main reviews of A to G and write docs/controls_results.md.

Usage (from the repo root): `PYTHONPATH=src .venv/bin/python -m rdr.controls derive|run|analyse`.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from rdr.freeze import build_manifest, verify_manifest, write_manifest
from rdr.packager import ARMS, CONTROL_ARMS, build_package
from rdr.pilot import _load_record, _mean, _pct, cluster_bootstrap, load_instances, review_path, run, sign_test_p
from rdr.scorer import score
from rdr.trace import Trace
from rdr.truth import Truth

REPO = Path(__file__).resolve().parents[2]
PILOT = REPO / "runs" / "pilot"
ROOT = REPO / "runs" / "controls"
# (X, Y, question). Each row is read as "what X has that Y lacks".
CONTRASTS = (
    ("J", "C", "structure only against the full graph: do the arguments in the labels carry C?"),
    ("J", "A", "structure only against nothing: does graph structure alone help?"),
    ("I", "B", "inputs only against the full log: do responses add anything?"),
    ("I", "A", "inputs only against nothing"),
    ("I", "C", "inputs only against the full graph"),
    ("G", "H", "log + real graph against log + fake graph: the graph's added value, controlled"),
    ("K", "D", "neighbourhood with the source forced in against the plain neighbourhood"),
    ("K", "L", "targeted against random slice, source present in both"),
    ("C", "M", "full graph against the same graph with the source removed"),
    ("M", "A", "graph without the source against nothing"),
)


def anchor_of(meta: dict, metas: dict[str, dict]) -> int:
    """The origin call, or for a clean twin the same write position as its persistent twin's origin."""
    if meta["origin_index"] is not None:
        return meta["origin_index"]
    twin = metas[meta["twin_of"]]["origin_index"]
    if twin is None:
        raise ValueError(f"{meta['instance_id']}: clean twin of an instance without an origin")
    return twin


def default_id_tables() -> dict:
    from rdr.appworld_adapter import load_schema
    from rdr.graph import id_key_tables

    schema = load_schema(REPO / "runs" / "schema.json")
    docs = {f.stem: json.loads(f.read_text()) for f in (REPO / "appworld_root/data/api_docs/standard").glob("*.json")}
    return id_key_tables(docs, schema.tables, schema.foreign_keys)


def derive(source: Path, target: Path, id_tables: dict | None) -> dict:
    problems = verify_manifest(source)
    if problems:
        raise RuntimeError(f"source freeze check failed: {problems[:5]}")
    dirs = sorted(p for p in source.iterdir() if p.is_dir())
    metas = {json.loads((d / "meta.json").read_text())["instance_id"]: json.loads((d / "meta.json").read_text())
             for d in dirs}
    staged: dict[str, dict[str, str]] = {}
    for d in dirs:
        meta = metas[d.name]
        trace, truth = Trace.load(d / "trace.json"), Truth.load(d / "truth.json")
        anchor = frozenset({anchor_of(meta, metas)})
        for arm in ARMS:
            rebuilt = build_package(arm, trace, truth.symptom, d.name, avoid_calls=anchor, id_tables=id_tables)
            if rebuilt != (d / "packages" / f"{arm}.txt").read_text():
                raise RuntimeError(f"{d.name}: rebuilt arm {arm} differs from the frozen package")
        staged[d.name] = {arm: build_package(arm, trace, truth.symptom, d.name, avoid_calls=anchor,
                                             id_tables=id_tables) for arm in CONTROL_ARMS}
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    (target / "MANIFEST.sha256.json").unlink()
    for instance_id, packages in staged.items():
        for arm, text in packages.items():
            (target / instance_id / "packages" / f"{arm}.txt").write_text(text)
    write_manifest(target)
    frozen = build_manifest(source)
    copied = build_manifest(target)
    if any(copied.get(k) != v for k, v in frozen.items()):
        raise RuntimeError("a frozen pilot file changed in the copy")
    sizes = {arm: sorted(len(p[arm]) for p in staged.values()) for arm in CONTROL_ARMS}
    return {"instances": len(staged), "new_packages": sum(len(p) for p in staged.values()),
            "chars_min_median_max": {a: (s[0], s[len(s) // 2], s[-1]) for a, s in sizes.items()}}


def control_jobs(instances: list[dict]) -> list[tuple[str, str, int]]:
    return [(i["id"], arm, 0) for i in instances for arm in CONTROL_ARMS]


def score_rows(instances: list[dict], reviews_for: dict[str, Path]) -> dict[tuple[str, str], dict]:
    """Main review of every arm in `reviews_for` (arm -> reviews directory), intention to treat (a missing or failed
    review is a miss)."""
    rows = {}
    for inst in instances:
        truth = inst["truth"]
        for arm, reviews in reviews_for.items():
            record = _load_record(review_path(reviews, inst["id"], arm, 0))
            if record is None:
                rows[(inst["id"], arm)] = {"failed": True, "detection_correct": False,
                                           "origin_hit": False if truth.is_faulty else None,
                                           "stale_precision": 0.0 if truth.is_faulty else None,
                                           "stale_recall": 0.0 if truth.is_faulty else None,
                                           "false_stale_count": None if truth.is_faulty else 0}
                continue
            s = score(record["answer"], truth, known_labels=inst["known"])
            rows[(inst["id"], arm)] = {**s, "failed": False}
    return rows


def groups_of(instances: list[dict]) -> dict[str, list[str]]:
    ids = [i["id"] for i in instances]
    variant = {i["id"]: i["variant"] for i in instances}
    return {"all": ids, "faulty": [i for i in ids if variant[i] != "clean"],
            "persistent": [i for i in ids if variant[i] == "persistent"],
            "nonpersistent": [i for i in ids if variant[i] == "nonpersistent"],
            "clean": [i for i in ids if variant[i] == "clean"]}


def summarise(rows: dict, instances: list[dict], arms) -> dict[str, dict]:
    groups = groups_of(instances)
    generator = {i["id"]: i["generator"] for i in instances}

    def hits(arm: str, group: list[str], field: str = "origin_hit") -> tuple[int, int]:
        return sum(1 for i in group if rows[(i, arm)][field]), len(group)

    table = {}
    for arm in arms:
        per: dict[str, list[int]] = {}
        for i in groups["faulty"]:
            cell = per.setdefault(generator[i], [0, 0])
            cell[0] += 1 if rows[(i, arm)]["origin_hit"] else 0
            cell[1] += 1
        table[arm] = {
            "origin": hits(arm, groups["faulty"]), "origin_p": hits(arm, groups["persistent"]),
            "origin_n": hits(arm, groups["nonpersistent"]), "detect": hits(arm, groups["all"], "detection_correct"),
            "false_stale_inst": sum(1 for i in groups["clean"] if (rows[(i, arm)]["false_stale_count"] or 0) > 0),
            "precision": [rows[(i, arm)]["stale_precision"] for i in groups["faulty"]
                          if rows[(i, arm)]["stale_precision"] is not None],
            "failed": sum(1 for i in groups["all"] if rows[(i, arm)]["failed"]),
            "ci": cluster_bootstrap({g: (a, b) for g, (a, b) in per.items()}),
        }
    return table


def paired(rows: dict, groups: dict, pairs) -> list[dict]:
    """Origin-hit contrasts for (X, Y, question) pairs on the faulty, persistent and non-persistent groups."""
    out = []
    for x, y, question in pairs:
        for name in ("faulty", "persistent", "nonpersistent"):
            xs = [bool(rows[(i, x)]["origin_hit"]) for i in groups[name]]
            ys = [bool(rows[(i, y)]["origin_hit"]) for i in groups[name]]
            b = sum(1 for a, c in zip(xs, ys) if a and not c)
            c = sum(1 for a, c_ in zip(xs, ys) if c_ and not a)
            out.append({"pair": f"{x} vs {y}", "group": name, "n": len(xs), "x": sum(xs), "y": sum(ys),
                        "x_only": b, "y_only": c, "p": sign_test_p(b, c), "question": question})
    return out


def analyse(instances_dir: Path, pilot_reviews: Path, control_reviews: Path, report_path: Path) -> dict:
    instances = load_instances(instances_dir)
    reviews_for = {**{a: pilot_reviews for a in ARMS}, **{a: control_reviews for a in CONTROL_ARMS}}
    rows = score_rows(instances, reviews_for)
    groups = groups_of(instances)
    table = summarise(rows, instances, ARMS + CONTROL_ARMS)
    contrasts = paired(rows, groups, CONTRASTS)
    report = render(table, contrasts, groups, len(groups["all"]))
    report_path.write_text(report)
    return {"table": table, "contrasts": contrasts, "report": report}


ARM_NAMES = {
    "A": "output only", "B": "full action log", "C": "full graph", "D": "symptom neighbourhood",
    "E": "random slice matched to D", "F": "fake graph", "G": "log + graph",
    "H": "log + fake graph", "I": "call inputs only", "J": "graph without arguments",
    "K": "neighbourhood + source", "L": "random slice + source, matched to K", "M": "graph without the source",
    "N": "step by step from the symptom, may stop early", "O": "step by step, all expansions used",
}


def table_lines(table: dict, groups: dict) -> list[str]:
    lines = ["| Arm | Evidence | Origin hit (faulty) | 95% CI (generator bootstrap) | Persistent | Non-persistent | "
             "Detection (all) | Stale precision | Clean twins with false-stale claims | Failed |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for arm, t in table.items():
        lo, hi = t["ci"]
        lines.append(f"| {arm} | {ARM_NAMES[arm]} | {_pct(*t['origin'])} | {100 * lo:.0f}% to {100 * hi:.0f}% | "
                     f"{_pct(*t['origin_p'])} | {_pct(*t['origin_n'])} | {_pct(*t['detect'])} | "
                     f"{_mean(t['precision'])} | {_pct(t['false_stale_inst'], len(groups['clean']))} | "
                     f"{t['failed']} |")
    return lines


def contrast_lines(contrasts: list[dict]) -> list[str]:
    lines = ["Exact two-sided sign test on the discordant pairs, paired by instance. Descriptive only: n is tiny, "
             "instances within a generator are not independent, and nothing is corrected for multiplicity.", "",
             "| Contrast | Question | Group | X rate | Y rate | X only right | Y only right | Sign test p |",
             "|---|---|---|---|---|---|---|---|"]
    for c in contrasts:
        lines.append(f"| {c['pair']} | {c['question'] if c['group'] == 'faulty' else ''} | {c['group']} | "
                     f"{_pct(c['x'], c['n'])} | {_pct(c['y'], c['n'])} | {c['x_only']} | {c['y_only']} | "
                     f"{c['p']:.3f} |")
    return lines


def render(table: dict, contrasts: list[dict], groups: dict, n_all: int) -> str:
    L: list[str] = []
    w = L.append
    w("# Control arms H to M on the Gate 2 pilot set")
    w("")
    w("Raluca's review of the pilot (6 Nov 2026) asked whether inputs alone are enough and asked for arms with "
      "the source present in both graph and non-graph evidence. Six control arms answer that on the same frozen "
      f"{n_all} instances ({len(groups['persistent'])} persistent, {len(groups['nonpersistent'])} non-persistent, "
      f"{len(groups['clean'])} clean), same model (`claude-haiku-5-5`, effort `medium`), one main review each. "
      "Arms A to G are the pilot's own main reviews, not re-run. The anchor call is the origin, or in a clean "
      "twin the same write position. Counts, names and mechanisms only. A failed or missing review is a miss "
      "(intention to treat).")
    w("")
    w("## 1. Origin hit by arm")
    w("")
    L.extend(table_lines(table, groups))
    w("")
    w("## 2. Paired contrasts on origin hit")
    w("")
    L.extend(contrast_lines(contrasts))
    w("")
    return "\n".join(L)


def main(argv: list[str]) -> int:
    instances_dir, reviews_dir = ROOT / "instances", ROOT / "reviews"
    if argv and argv[0] == "derive":
        print(json.dumps(derive(PILOT / "instances", instances_dir, default_id_tables()), indent=2))
        return 0
    if argv and argv[0] == "run":
        jobs = control_jobs(load_instances(instances_dir))
        summary = run(instances_dir, reviews_dir, ROOT / "run_log.jsonl", jobs=jobs)
        print(json.dumps(summary, indent=2))
        return 0 if summary["stopped"] is None else 2
    if argv and argv[0] == "analyse":
        result = analyse(instances_dir, PILOT / "reviews", reviews_dir, REPO / "docs" / "controls_results.md")
        print(result["report"])
        return 0
    print("usage: python -m rdr.controls derive|run|analyse", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
