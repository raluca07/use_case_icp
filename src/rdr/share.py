"""Shareable summary of the control arms (H to M), the step-by-step arm (N) and the runtime-error probe, 6 Nov 2026.

Writes results/controls-stepwise-2026-11-06/: README.md, scores.jsonl (metrics and ids only, no AppWorld data) and
figures/*.png. Every number in the README and the figures is computed here from the saved reviews and the probe's
counts, and each claim the prose makes is asserted, so the build fails if the data stop supporting it. Every figure
passes a text-overlap guard measured at the save resolution before it is written.

Usage (from the repo root): `PYTHONPATH=src .venv/bin/python -m rdr.share`.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402

from rdr.controls import REPO, default_id_tables, groups_of, paired, score_rows, summarise  # noqa: E402
from rdr.packager import ARMS, CONTROL_ARMS  # noqa: E402
from rdr.pilot import REPEATS, _load_record, choose_repeat_instances, load_instances, review_path  # noqa: E402
from rdr.scorer import score  # noqa: E402
from rdr.stepwise import MAX_EXPANSIONS, NOTE_CHARS, check, walk_rows  # noqa: E402

OUT = REPO / "results" / "controls-stepwise-2026-11-06"
PILOT_REVIEWS = REPO / "runs" / "pilot" / "reviews"
CONTROLS = REPO / "runs" / "controls"
STEPWISE_REVIEWS = REPO / "runs" / "stepwise" / "reviews"
ARM_ORDER = (*ARMS, *CONTROL_ARMS, "N")

TEAL, ORANGE = "#0B8F86", "#D07020"  # the dataviz validator passes this pair on a light surface
INK, BODY, MUTED, RULE = "#2F353D", "#4A515B", "#8A939E", "#E3E7EA"
TEAL_TINT, ORANGE_TINT = "#E6F2F1", "#F8E6D6"
SAVE_DPI = 200
FONT = 10.5

SHORT = {"A": "output only", "B": "action log", "C": "whole graph", "D": "neighbourhood", "E": "random slice",
         "F": "fake graph", "G": "log + graph", "H": "log + fake graph", "I": "inputs only",
         "J": "graph, no arguments", "K": "neighbourhood + origin", "L": "random slice + origin",
         "M": "graph minus origin", "N": "step-by-step walk"}

# Per arm: final state and call list, call arguments, call responses, graph edges, then what the graph shows.
# 2 = shown, 1 = only for the calls the slice shows, 0 = not shown, "fake" = writes edges rewired.
EVIDENCE = {
    "A": (2, 0, 0, 0, "nothing more"),
    "B": (2, 2, 2, 0, "the full action log, in order"),
    "C": (2, 2, 0, 2, "the whole graph"),
    "D": (2, 1, 0, 1, "2 hops around the reported record"),
    "E": (2, 1, 0, 1, "a random slice the size of D"),
    "F": (2, 2, 0, "fake", "the whole graph, writes edges rewired"),
    "G": (2, 2, 2, 2, "the log and the whole graph"),
    "H": (2, 2, 2, "fake", "the log and F's fake graph"),
    "I": (2, 2, 0, 0, "every call's arguments, nothing else"),
    "J": (2, 0, 0, 2, "the whole graph, arguments cut from labels"),
    "K": (2, 1, 0, 1, "D plus the origin call and its edges"),
    "L": (2, 1, 0, 1, "a random slice the size of K, origin in"),
    "M": (2, 1, 0, 1, "the whole graph minus the origin call"),
    "N": (2, 1, 0, 1, "walked from the reported record"),
}

KEY_CONTRASTS = (
    ("I", "C", "inputs only vs whole graph"),
    ("I", "A", "inputs only vs output only"),
    ("J", "C", "graph without arguments vs whole graph"),
    ("J", "A", "graph without arguments vs output only"),
    ("G", "H", "log + real graph vs log + fake graph"),
    ("K", "D", "neighbourhood + origin vs neighbourhood"),
    ("K", "L", "neighbourhood + origin vs random + origin"),
    ("C", "M", "whole graph vs whole graph minus origin"),
    ("N", "C", "step-by-step walk vs whole graph"),
    ("N", "D", "step-by-step walk vs neighbourhood"),
)


# ---------------------------------------------------------------- layout guard

def _texts(fig) -> list:
    texts = list(fig.texts)
    for ax in fig.axes:
        texts += list(ax.texts) + [ax.title, ax._left_title, ax._right_title, ax.xaxis.label, ax.yaxis.label]
        if ax.axison:
            texts += list(ax.get_xticklabels()) + list(ax.get_yticklabels())
        if ax.get_legend() is not None:
            texts += list(ax.get_legend().get_texts())
    for legend in fig.legends:
        texts += list(legend.get_texts())
    return [t for t in texts if t.get_visible() and t.get_text().strip()]


def text_problems(fig, dpi: int = SAVE_DPI, tol: float = 0.5) -> list[str]:
    """Texts whose boxes overlap each other or leave the canvas, measured at the dpi the figure is saved at."""
    fig.set_dpi(dpi)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, height = fig.bbox.width, fig.bbox.height
    boxes = [(t.get_text().strip().replace("\n", " ")[:40], t.get_window_extent(renderer)) for t in _texts(fig)]
    problems = [f"off canvas: {label!r}" for label, b in boxes
                if b.x0 < -tol or b.y0 < -tol or b.x1 > width + tol or b.y1 > height + tol]
    for a in range(len(boxes)):
        for c in range(a + 1, len(boxes)):
            (la, ba), (lc, bc) = boxes[a], boxes[c]
            if min(ba.x1, bc.x1) - max(ba.x0, bc.x0) > tol and min(ba.y1, bc.y1) - max(ba.y0, bc.y0) > tol:
                problems.append(f"overlap: {la!r} and {lc!r}")
    return problems


def save(fig, path: Path) -> None:
    problems = text_problems(fig)
    if problems:
        raise RuntimeError(f"{path.name}: {problems}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=SAVE_DPI, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- data

def collect() -> dict:
    id_tables = default_id_tables()
    instances = load_instances(CONTROLS / "instances")
    reviews_for = {a: PILOT_REVIEWS if a in ARMS else CONTROLS / "reviews" if a in CONTROL_ARMS else STEPWISE_REVIEWS
                   for a in ARM_ORDER}
    rows = score_rows(instances, reviews_for)
    groups = groups_of(instances)
    table = summarise(rows, instances, ARM_ORDER)
    contrasts = {(c["pair"], c["group"]): c for c in paired(rows, groups, KEY_CONTRASTS)}
    distances = check(CONTROLS / "instances", id_tables)
    walks = {w["id"]: w for w in walk_rows(instances, STEPWISE_REVIEWS, rows, "N", distances, id_tables)}
    records = {(i["id"], a): _load_record(review_path(reviews_for[a], i["id"], a, 0)) for i in instances
               for a in ARM_ORDER}
    models = {(r["model_requested"], r["effort"]) for r in records.values() if r is not None}
    if len(models) != 1:
        raise RuntimeError(f"reviews disagree on model or effort: {models}")
    new_calls = sum(1 for d in (CONTROLS / "reviews").iterdir() for f in d.glob("[H-M].json"))
    walk_calls = sum(1 for d in STEPWISE_REVIEWS.iterdir() for f in d.glob("N*.json") if not f.name.endswith(
        ("path.json", "failed.json")))
    probe = json.loads((OUT / "runtime_probe.json").read_text())
    return {"instances": instances, "rows": rows, "groups": groups, "table": table, "contrasts": contrasts,
            "walks": walks, "records": records, "model": models.pop(), "new_calls": new_calls,
            "walk_calls": walk_calls, "probe": probe,
            "generators": len({i["generator"] for i in instances})}


def write_scores(data: dict, path: Path) -> int:
    lines = []
    for inst in data["instances"]:
        for arm in ARM_ORDER:
            record = data["records"][(inst["id"], arm)]
            row = {"instance_id": inst["id"], "arm": arm, "variant": inst["variant"], "generator": inst["generator"],
                   "is_faulty": inst["truth"].is_faulty, "failed": record is None}
            if record is None:
                row.update(data["rows"][(inst["id"], arm)], origin_call="missing")
            else:
                row.update(score(record["answer"], inst["truth"], known_labels=inst["known"]),
                           origin_call=record["answer"]["origin_call"])
            if arm == "N":
                w = data["walks"][inst["id"]]
                row.update(walk_rounds=w["rounds"], walk_nodes_expanded=w["expanded"], walk_stopped_by=w["stopped_by"],
                           walk_origin_in_view=w["anchor_seen"], walk_origin_expanded=w["anchor_expanded"],
                           walk_distance=w["distance"])
            lines.append(json.dumps(row, sort_keys=True))
    path.write_text("\n".join(lines) + "\n")
    return len(lines)


# ---------------------------------------------------------------- figures

def _box(ax, x, y, w, h, text, edge, fill="white", lw=1.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.0", linewidth=lw,
                                edgecolor=edge, facecolor=fill))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=FONT, color=INK, linespacing=1.35)


def _arrow(ax, start, end, color, ls="-"):
    ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5, linestyle=ls,
                                                          shrinkA=0, shrinkB=0, mutation_scale=14))


def figure_fault(path: Path) -> None:
    fig = plt.figure(figsize=(10, 4.4))
    ax = fig.add_axes((0.01, 0.02, 0.98, 0.96))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 46)
    ax.axis("off")
    _box(ax, 2, 37, 78, 8, "W's row: wrong after call W, right again after the repair", TEAL, TEAL_TINT)
    _box(ax, 2, 19, 21, 11, "call W\nwrites a wrong value", ORANGE, lw=2.0)
    _box(ax, 29, 19, 26, 11, "later calls reuse\nthe same wrong value", BODY)
    _box(ax, 61, 19, 19, 11, "repair call,\njust before the end", TEAL, lw=2.0)
    _box(ax, 29, 2, 12, 9, "still wrong", ORANGE, ORANGE_TINT)
    _box(ax, 43, 2, 12, 9, "still wrong,\nreported", INK, ORANGE_TINT, lw=2.2)
    _box(ax, 66, 2, 32, 9, "the reviewer gets the reported\nrecord and must name call W", INK)
    _arrow(ax, (12.5, 30), (12.5, 37), ORANGE)
    ax.text(14, 33.5, "writes", fontsize=FONT - 1, color=BODY, va="center")
    _arrow(ax, (70.5, 30), (70.5, 37), TEAL)
    ax.text(72, 33.5, "fixes", fontsize=FONT - 1, color=BODY, va="center")
    _arrow(ax, (23, 24.5), (29, 24.5), ORANGE, ls="--")
    _arrow(ax, (35, 19), (35, 11), BODY)
    _arrow(ax, (49, 19), (49, 11), BODY)
    _arrow(ax, (55, 6.5), (66, 6.5), INK)
    save(fig, path)


def figure_arms(path: Path) -> None:
    arms = list(EVIDENCE)
    fig = plt.figure(figsize=(10.5, 6.6))
    ax = fig.add_axes((0.0, 0.08, 1.0, 0.9))
    ax.set_xlim(0, 10.5)
    ax.set_ylim(len(arms) - 0.4, -1.9)
    ax.axis("off")
    cols = (2.55, 3.55, 4.55, 5.55)
    for x, head in zip(cols, ("Final state\nand calls", "Call\narguments", "Call\nresponses", "Graph\nedges")):
        ax.text(x, -1.0, head, ha="center", va="center", fontsize=FONT, color=INK, weight="bold", linespacing=1.3)
    ax.text(6.15, -1.0, "In words", ha="left", va="center", fontsize=FONT, color=INK,
            weight="bold")
    for row, arm in enumerate(arms):
        ax.text(0.15, row, f"{arm}", ha="left", va="center", fontsize=FONT, color=INK, weight="bold")
        ax.text(0.45, row, SHORT[arm], ha="left", va="center", fontsize=FONT, color=INK)
        for x, value in zip(cols, EVIDENCE[arm][:4]):
            if value == 2:
                ax.scatter([x], [row], s=110, color=TEAL, zorder=3)
            elif value == 1:
                ax.scatter([x], [row], s=110, facecolor="white", edgecolor=TEAL, linewidth=2, zorder=3)
            elif value == "fake":
                ax.scatter([x], [row], s=100, marker="s", color=ORANGE, zorder=3)
            else:
                ax.scatter([x], [row], s=14, color=MUTED, zorder=3)
        ax.text(6.15, row, EVIDENCE[arm][4], ha="left", va="center", fontsize=FONT, color=BODY)
    for boundary in (1.5, 6.5, 12.5):
        ax.axhline(boundary, xmin=0.01, xmax=0.99, color=RULE, lw=1.0)
    handles = [Line2D([], [], marker="o", ls="", color=TEAL, markersize=9, label="shown"),
               Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=TEAL, markeredgewidth=2,
                      markersize=9, label="only for the calls the slice shows"),
               Line2D([], [], marker="s", ls="", color=ORANGE, markersize=8, label="edges rewired (fake)"),
               Line2D([], [], marker="o", ls="", color=MUTED, markersize=4, label="not shown")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=FONT - 0.5,
               bbox_to_anchor=(0.5, 0.005), handletextpad=0.4, columnspacing=1.6)
    save(fig, path)


def figure_origin(path: Path, data: dict) -> None:
    table, arms = data["table"], list(ARM_ORDER)
    n_f, n_p, n_n = (len(data["groups"][g]) for g in ("faulty", "persistent", "nonpersistent"))
    fig = plt.figure(figsize=(10, 6.8))
    ax = fig.add_axes((0.25, 0.08, 0.63, 0.82))
    for row, arm in enumerate(arms):
        t = table[arm]
        lo, hi = t["ci"]
        ax.plot([100 * lo, 100 * hi], [row, row], color=MUTED, lw=2.2, solid_capstyle="round", zorder=1)
        ax.scatter([100 * t["origin"][0] / t["origin"][1]], [row], s=70, color=INK, zorder=3)
        ax.scatter([100 * t["origin_p"][0] / t["origin_p"][1]], [row - 0.27], s=42, color=TEAL, zorder=3)
        ax.scatter([100 * t["origin_n"][0] / t["origin_n"][1]], [row + 0.27], s=46, marker="D", color=ORANGE,
                   zorder=3)
        ax.text(1.02, row, f"{t['origin'][0]}/{t['origin'][1]}", transform=ax.get_yaxis_transform(), ha="left",
                va="center", fontsize=FONT, color=INK)
    ax.text(1.02, -1.1, f"of {n_f}", transform=ax.get_yaxis_transform(), ha="left", va="center", fontsize=FONT - 1,
            color=BODY)
    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels([f"{a}   {SHORT[a]}" for a in arms], fontsize=FONT, color=INK)
    ax.set_ylim(len(arms) - 0.4, -1.6)
    ax.set_xlim(-2, 102)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=FONT - 0.5, color=BODY)
    ax.set_xlabel("reviewer named the call where the problem started", fontsize=FONT, color=BODY)
    ax.grid(axis="x", color=RULE, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", color=MUTED)
    handles = [Line2D([], [], marker="o", ls="-", color=INK, markersize=8, markeredgecolor=INK,
                      label=f"all {n_f} faulty, 95% interval in grey"),
               Line2D([], [], marker="o", ls="", color=TEAL, markersize=7, label=f"{n_p} persistent"),
               Line2D([], [], marker="D", ls="", color=ORANGE, markersize=6, label=f"{n_n} non-persistent")]
    for handle in handles[:1]:
        handle.set_color(INK)
    leg = fig.legend(handles=handles, loc="upper left", ncol=3, frameon=False, fontsize=FONT - 0.5,
                     bbox_to_anchor=(0.25, 0.995), handletextpad=0.4, columnspacing=1.8)
    leg.legend_handles[0].set_linestyle("")
    save(fig, path)


def figure_contrasts(path: Path, data: dict) -> None:
    rows = [data["contrasts"][(f"{x} vs {y}", "faulty")] for x, y, _ in KEY_CONTRASTS]
    labels = [f"{x} vs {y}   {text}" for x, y, text in KEY_CONTRASTS]
    top = max(max(c["x_only"], c["y_only"]) for c in rows)
    fig = plt.figure(figsize=(10.5, 5.6))
    ax = fig.add_axes((0.43, 0.1, 0.45, 0.78))
    for row, c in enumerate(rows):
        if c["x_only"]:
            ax.barh(row, c["x_only"], height=0.56, color=TEAL)
            ax.text(c["x_only"] + 0.25, row, str(c["x_only"]), va="center", ha="left", fontsize=FONT, color=INK)
        if c["y_only"]:
            ax.barh(row, -c["y_only"], height=0.56, color=ORANGE)
            ax.text(-c["y_only"] - 0.25, row, str(c["y_only"]), va="center", ha="right", fontsize=FONT, color=INK)
        if not c["x_only"] and not c["y_only"]:
            ax.text(0.35, row, "same answers", va="center", ha="left", fontsize=FONT - 0.5, color=BODY)
        ax.text(1.03, row, f"p = {c['p']:.3f}".replace("p = 1.000", "p = 1"), transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=FONT - 0.5, color=BODY)
    ax.axvline(0, color=INK, lw=1.0)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels, fontsize=FONT, color=INK)
    ax.set_ylim(len(rows) - 0.5, -0.6)
    span = top + 2
    ax.set_xlim(-span, span)
    ticks = [t for t in range(-top, top + 1) if t % 2 == 0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(abs(t)) for t in ticks], fontsize=FONT - 0.5, color=BODY)
    ax.set_xlabel(f"faulty instances (of {len(data['groups']['faulty'])}) that only one of the two arms got right",
                  fontsize=FONT, color=BODY)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", color=MUTED)
    handles = [Patch(color=TEAL, label="only the first arm right"), Patch(color=ORANGE, label="only the second arm right")]
    fig.legend(handles=handles, loc="upper left", ncol=2, frameon=False, fontsize=FONT - 0.5,
               bbox_to_anchor=(0.43, 0.995), handletextpad=0.5, columnspacing=1.8)
    save(fig, path)


def walk_funnel(data: dict) -> list[tuple[str, int]]:
    faulty = [w for w in data["walks"].values() if w["variant"] != "clean"]
    reachable = [w for w in faulty if w["distance"] is not None]
    seen = [w for w in reachable if w["anchor_seen"]]
    return [("faulty instances", len(faulty)),
            ("origin reachable from the reported record", len(reachable)),
            ("origin came into view during the walk", len(seen)),
            ("reviewer named the origin", sum(1 for w in faulty if w["hit"]))]


def figure_walks(path: Path, data: dict) -> None:
    steps = walk_funnel(data)
    fig = plt.figure(figsize=(10, 3.3))
    ax = fig.add_axes((0.36, 0.08, 0.58, 0.84))
    for row, (label, value) in enumerate(steps):
        ax.barh(row, value, height=0.56, color=TEAL)
        ax.text(value + 0.2, row, str(value), va="center", ha="left", fontsize=FONT, color=INK)
    ax.set_yticks(range(len(steps)))
    ax.set_yticklabels([label for label, _ in steps], fontsize=FONT, color=INK)
    ax.set_ylim(len(steps) - 0.5, -0.5)
    ax.set_xlim(0, steps[0][1] + 1.5)
    ax.set_xticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    save(fig, path)


# ---------------------------------------------------------------- README

def _k(t: tuple[int, int]) -> str:
    return f"{t[0]} of {t[1]}"


def readme(data: dict, n_scores: int) -> str:
    T, C, G = data["table"], data["contrasts"], data["groups"]
    n_f, n_p, n_n, n_c = (len(G[g]) for g in ("faulty", "persistent", "nonpersistent", "clean"))
    model, effort = data["model"]
    walks = list(data["walks"].values())
    faulty_walks = [w for w in walks if w["variant"] != "clean"]
    funnel = dict(walk_funnel(data))
    in_view = [w for w in faulty_walks if w["anchor_seen"]]
    missed_in_view = [w for w in in_view if not w["hit"]]
    named_in_missed = {"another call": 0, "no call": 0}
    for w in missed_in_view:
        named = data["records"][(w["id"], "N")]["answer"]["origin_call"]
        named_in_missed["no call" if named is None else "another call"] += 1
    stopped = sum(1 for w in walks if w["stopped_by"] == "answer")
    median_nodes = statistics.median(w["expanded"] for w in walks)
    same_ic = sum(1 for i in G["faulty"] if data["records"][(i, "I")]["answer"]["origin_call"]
                  == data["records"][(i, "C")]["answer"]["origin_call"])
    probe = data["probe"]
    failed_probe = probe["outcomes"].get("a later call failed", 0)
    pf = lambda x, y, g="faulty": C[(f"{x} vs {y}", g)]  # noqa: E731

    # the claims the prose makes, checked against the data
    assert T["I"]["origin"] == T["C"]["origin"] == T["B"]["origin"], "inputs, graph and log no longer tie"
    assert same_ic == n_f, "inputs and graph no longer name the same call on every faulty instance"
    assert T["A"]["origin"][0] < T["J"]["origin"][0] < T["C"]["origin"][0]
    assert pf("J", "C")["x_only"] == 0 and pf("J", "C")["y_only"] == pf("J", "C", "persistent")["y_only"]
    assert pf("K", "D")["y_only"] == 0 and T["K"]["origin"] == T["L"]["origin"] and T["M"]["origin"] == T["A"]["origin"]
    assert T["G"]["origin_p"][0] > T["H"]["origin_p"][0]
    assert T["N"]["origin"] == T["D"]["origin"] and T["N"]["origin_p"][0] == 0 and pf("N", "D")["x_only"] == 0
    alarms = {a: T[a]["false_stale_inst"] for a in ARM_ORDER}
    assert max(alarms, key=alarms.get) == "C" and sorted(alarms.values()).count(alarms["C"]) == 1
    assert sorted(a for a, v in alarms.items() if v == min(alarms.values())) == ["B", "D", "H", "L"]
    repeat_ids = choose_repeat_instances(load_instances(REPO / "runs" / "pilot" / "instances"))
    runs_c = [[_load_record(review_path(PILOT_REVIEWS, i, "C", k)) for k in (0, *REPEATS)] for i in repeat_ids]
    stable_c = sum(1 for runs in runs_c if all(runs) and len({r["answer"]["origin_call"] for r in runs}) == 1)

    def hits(arm: str, key: str = "origin") -> str:
        return _k(T[arm][key])

    def fa(arm: str) -> str:
        return f"{T[arm]['false_stale_inst']} of {n_c}"

    table_rows = "\n".join(
        f"| {a} | {SHORT[a]} | {hits(a)} | {hits(a, 'origin_p')} | {hits(a, 'origin_n')} | {fa(a)} |"
        for a in ARM_ORDER)
    p = lambda c: "1" if c["p"] == 1 else f"{c['p']:.3f}"  # noqa: E731
    return f"""# Control arms and a step-by-step reviewer, 6 Nov 2026

This follows your notes on the pilot. Six control arms (H to M) answer your points 2 and 3, and arm N is a reviewer that walks the graph one node at a time, for your question of 2 Nov about whether the model takes the whole graph or parses it step by step.

Everything ran on the same {len(G['all'])} frozen instances as the [pilot](../pilot-2026-11-02/README.md): {n_p} persistent faults, {n_n} non-persistent faults and {n_c} clean twins from {data['generators']} AppWorld generators. The reviewer is the same, `{model}` at effort {effort} through an isolated `claude -p`, with one review per arm and instance. The controls took {data['new_calls']} calls and the walks {data['walk_calls']}, and none failed. Arms A to G are the pilot's own reviews, not re-run.

With {n_f} faulty instances from {data['generators']} generators, all of this is direction, not proof.

## In short

- **Inputs are enough in one shot.** Call inputs alone (arm I: each call's arguments, no responses, no graph) find the origin in {hits('I')}, the same as the whole graph (C) and the full log (B). I and C name the same call on all {n_f} faulty instances, so what the graph arm gets right comes from the arguments printed in its node labels.
- **Structure alone helps a little.** The whole graph with the arguments cut out (J) gets {hits('J')}, more than output only (A, {hits('A')}) and less than C. Every instance J loses against C is a persistent fault ({hits('J', 'origin_p')} against {hits('C', 'origin_p')}).
- **The slice arms depend on whether the origin is in the evidence.** Forcing the origin call into the 2-hop neighbourhood takes it from {hits('D')} to {hits('K')} (K against D). A random slice with the origin in does exactly as well (L, {hits('L')}). Taking the origin out of the whole graph drops it to {hits('M')}, the output-only level (M against C).
- **The graph adds to the log only when its edges are real, and only on persistent faults.** Log plus real graph (G) gets {hits('G', 'origin_p')} persistent faults, log plus fake graph (H) {hits('H', 'origin_p')}.
- **Walking does not help Haiku here.** The step-by-step reviewer (N) finds the origin in {hits('N')}, the same instances as the plain neighbourhood, and none of the {n_p} persistent faults. It stopped by its own choice in {stopped} of {len(walks)} walks, after a median of {median_nodes:g} expanded nodes.

## The fault

![A persistent fault](figures/fig1_persistent_fault.png)

**Figure 1.** In a persistent fault, call W writes a wrong value and later calls reuse the same wrong value, so the records they build are wrong too. A repair just before the end puts W's own row right, but the records built from the wrong value stay wrong. The reviewer is told that one of them looks wrong and must name W. A non-persistent fault has no repair. In a clean twin the repair comes straight after W, so nothing is built from the wrong value.

## What each arm sees

![What each arm sees](figures/fig2_arms.png)

**Figure 2.** Every arm gets the task, the agent's final message, the user's report, the final state of the records the agent changed and the list of calls by index and API. The columns show what else it gets. Arms A to M get everything in one prompt with no tools; arm N walks the graph (below).

## Results

![Origin hit by arm](figures/fig3_origin_hit.png)

**Figure 3.** How often each arm named the call where the problem started. The black dot is all {n_f} faulty instances with a 95% interval from a bootstrap over generators; the teal and orange marks split it into persistent and non-persistent faults.

| Arm | Evidence | Origin found, faulty ({n_f}) | Persistent ({n_p}) | Non-persistent ({n_n}) | False alarm on clean ({n_c}) |
|---|---|---|---|---|---|
{table_rows}

False alarms are clean twins where the reviewer claimed wrong records. They are highest for the whole graph (C, {fa('C')}) and lowest for the log (B), the neighbourhood (D), log plus fake graph (H) and the random slice with the origin (L), all {fa('B')}.

![Paired contrasts](figures/fig4_contrasts.png)

**Figure 4.** Each row pairs two arms on the same {n_f} faulty instances and counts the instances only one of them got right. The p value is an exact two-sided sign test on those counts. It is descriptive: instances within a generator are not independent, and nothing is corrected for multiplicity. Inputs only and the whole graph give the same answers (I vs C); removing the origin costs the whole graph {pf('C', 'M')['x_only']} instances (C vs M, p = {p(pf('C', 'M'))}); adding it to the neighbourhood gains {pf('K', 'D')['x_only']} (K vs D, p = {p(pf('K', 'D'))}).

## The step-by-step reviewer (arm N)

Arm N starts from the reported record with that record's edges shown. Each round it can expand one node it can see, a call or a record, to reveal that node's edges and neighbours, for up to {MAX_EXPANSIONS} rounds, and it can stop at any time. Each round is a fresh isolated call that sees the same header as every arm, the part of the graph explored so far, its own notes from earlier rounds (up to {NOTE_CHARS} characters each) and any request that could not be done. It then answers through the same prompt and schema as every other arm, over the explored part only, so it is scored the same way. The graph it walks is byte for byte the graph arm C shows.

![Where the walk loses the origin](figures/fig5_walk.png)

**Figure 5.** Where the walk loses the origin, over the {n_f} faulty instances. In {funnel['faulty instances'] - funnel['origin reachable from the reported record']} of them the reported record has no path to the origin in the graph, so no walk can get there. In the other {funnel['origin reachable from the reported record']} the origin call came into view in {funnel['origin came into view during the walk']}, and the reviewer named it in {sum(1 for w in in_view if w['hit'])} of those. When it was in view and missed, the reviewer named another call in {named_in_missed['another call']} and no call in {named_in_missed['no call']}.

So reaching the origin is only part of the problem: once it is on screen as a neighbour, Haiku often still does not pick it. Your nested-graph result may need a stronger model or a walk the reviewer cannot stop early. That second version is implemented as arm O (it must use all {MAX_EXPANSIONS} expansions) but has not been run.

## Runtime errors (your point 6): a first probe

All pilot faults are code errors in your sense: the agent passes a wrong argument. As a first runtime error, the probe changes what the code sees in one read call's response. A value is swapped for another value of the same field from the same list (another contact, another transaction), while every line of code stays right and writes the value on.

Of {probe['candidates']} candidate read calls from {probe['candidate_generators']} generators, {probe['outcomes'].get('two or more stale rows', 0)} runs finished and left two or more wrong rows, from {probe['usable_generators']} generators ({probe['usable_generators_outside_pilot']} of them not used by the pilot). In {failed_probe} runs the swapped value made a later API call fail. At two instances per generator that is about {probe['units_at_cap_2_outside_pilot']} more instances outside the pilot set, enough for a code-versus-runtime split but not enough on its own for the main run.

Four decisions are yours before it becomes a fault family:

1. Whether the origin is the read call that returned the wrong value or the first write that used it.
2. Whether the trace shows the wrong response, as if the service returned it. Today the probe changes only what the code sees, so the trace shows the right response and a write that does not match it.
3. What the repair is, for example fixing the first record built from the wrong value while the later ones stay wrong.
4. What the clean twin is, since there is no held value to cut off early.

## Caveats

- {n_f} faulty instances from {data['generators']} generators, at most 2 per generator.
- All persistent faults are held-value faults: the agent keeps a wrong value across calls, so the wrong value does not travel through an API edge.
- One model and one review per arm. In the pilot, Haiku named the same origin in all {1 + len(REPEATS)} runs of the whole-graph view for only {stable_c} of {len(repeat_ids)} instances.
- Arm N's design is one of several reasonable ones: separate rounds that share notes, at most {MAX_EXPANSIONS} expansions, and an answer over the explored part only.

## Next

- Run arm O, the walk that must use every expansion, to see whether walking helps when the reviewer cannot stop early.
- Your four decisions on runtime errors, then build that family next to the code-error one.
- More instances: these results rest on {n_f} faulty instances, and the main analysis needs several times that.

## Files

- `scores.jsonl`: {n_scores} rows, one per instance and arm (A to N), metrics and ids only, no AppWorld data. Arm N rows add the walk: rounds, nodes expanded, how it stopped, whether the origin came into view or was expanded, and its distance from the reported record.
- `runtime_probe.json`: the probe's counts.
- `figures/`: drawn by `src/rdr/share.py` from the saved reviews; every number in this README is computed there too.
- Full tables: [`docs/controls_results.md`](../../docs/controls_results.md) and [`docs/stepwise_results.md`](../../docs/stepwise_results.md).
- Rerun from the repo root with `PYTHONPATH=src .venv/bin/python -m` and `rdr.controls derive|run|analyse`, `rdr.stepwise run|analyse`, `rdr.runtime_probe` and `rdr.share`.
"""


def main(argv: list[str]) -> int:
    data = collect()
    figures = OUT / "figures"
    figure_fault(figures / "fig1_persistent_fault.png")
    figure_arms(figures / "fig2_arms.png")
    figure_origin(figures / "fig3_origin_hit.png", data)
    figure_contrasts(figures / "fig4_contrasts.png", data)
    figure_walks(figures / "fig5_walk.png", data)
    n_scores = write_scores(data, OUT / "scores.jsonl")
    (OUT / "README.md").write_text(readme(data, n_scores))
    print(f"wrote {OUT.relative_to(REPO)}: README.md, scores.jsonl ({n_scores} rows), 5 figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
