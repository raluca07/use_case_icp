#!/usr/bin/env python3
"""Figures for the paper. Reads benchmark results, writes PDFs for LaTeX."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Validated categorical palette (six checks pass, light surface, no warnings).
BLUE, RED, PURPLE, GREEN = "#3366CC", "#CC3311", "#AA4499", "#117733"
INK, MUTED, GRID = "#1a1a1a", "#5a5a5a", "#d8d8d4"

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "axes.linewidth": 0.6,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "text.color": INK,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
})


def recess(ax, axis="x"):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=axis, color=GRID, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)


def short(model: str) -> str:
    name = model.split("/")[-1]
    return name.replace("-Instruct", "").replace("-8bit", "").replace("-4bit", "")


def load(outdir: Path):
    det = json.loads((outdir / "deterministic.json").read_text())
    judge_path = outdir / "judge.json"
    judge = json.loads(judge_path.read_text())["verdicts"] if judge_path.exists() else []
    return det, judge


def judge_rates(det, judge):
    """Per model: false-trust rate by majority vote, and self-disagreement."""
    by_case = defaultdict(list)
    for v in judge:
        if v["verdict"] is not None:
            by_case[(v["model"], v["case_id"])].append(v["verdict"])
    models = sorted({m for m, _ in by_case})
    out = {}
    for model in models:
        cases = [(c, vs) for (m, c), vs in by_case.items() if m == model]
        complete = [(c, vs) for c, vs in cases if len(vs) >= 3]
        if not complete:
            continue
        false_trust = sum(
            1 for _, vs in complete if vs.count("suspect") <= len(vs) / 2
        )
        split = sum(1 for _, vs in complete if 0 < vs.count("suspect") < len(vs))
        out[model] = {
            "n": len(complete),
            "false_trust": false_trust,
            "rate": false_trust / len(complete),
            "split": split,
            "split_rate": split / len(complete),
            "cases": dict(complete),
        }
    return out


def fig_false_trust(det, judge, path: Path):
    live = [r for r in det["rows"] if not r["crashed"]]
    n = len(live)
    labels, values, colours = [], [], []
    for name, colour in (("schema", BLUE), ("contract", GREEN)):
        ft = sum(1 for r in live if r["signals"][name]["false_trust"])
        labels.append(f"{name}\n(deterministic)")
        values.append(ft / n)
        colours.append(colour)
    for i, (model, stats) in enumerate(judge_rates(det, judge).items()):
        labels.append(f"{short(model)}\n(judge, n={stats['n']})")
        values.append(stats["rate"])
        colours.append([RED, PURPLE][i % 2])

    fig, ax = plt.subplots(figsize=(5.4, 2.6))
    bars = ax.bar(labels, values, color=colours, width=0.55, zorder=3)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02,
                f"{value:.0%}", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylabel("false-trust rate")
    ax.set_ylim(0, min(1.0, max(values) + 0.18))
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    recess(ax, axis="y")
    ax.tick_params(axis="x", length=0)
    fig.savefig(path)
    plt.close(fig)
    return dict(zip(labels, values))


def fig_by_fault(det, path: Path):
    live = [r for r in det["rows"] if not r["crashed"]]
    faults = sorted({r["fault"] for r in live})
    totals = Counter(r["fault"] for r in live)
    series = {}
    for name in ("schema", "contract"):
        series[name] = [
            sum(1 for r in live if r["fault"] == f and not r["signals"][name]["false_trust"])
            / totals[f]
            for f in faults
        ]
    x = range(len(faults))
    width = 0.38
    fig, ax = plt.subplots(figsize=(5.6, 2.7))
    ax.bar([i - width / 2 for i in x], series["schema"], width, label="schema",
           color=BLUE, zorder=3)
    ax.bar([i + width / 2 for i in x], series["contract"], width, label="invariants",
           color=GREEN, zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f.replace("_", "\n") for f in faults], fontsize=8)
    ax.set_ylabel("detected")
    ax.set_ylim(0, 1.32)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center",
              bbox_to_anchor=(0.5, 1.22))
    recess(ax, axis="y")
    ax.tick_params(axis="x", length=0)
    for i, f in enumerate(faults):
        ax.text(i, 1.03, f"n={totals[f]}", ha="center", fontsize=7, color=MUTED)
    # A zero bar is a real result here, so mark it rather than leave a blank slot.
    for i, f in enumerate(faults):
        for j, name in enumerate(("schema", "contract")):
            if series[name][i] == 0:
                ax.text(i + (j - 0.5) * width, 0.015, "0",
                        ha="center", va="bottom", fontsize=7, color=MUTED)
    fig.savefig(path)
    plt.close(fig)


def fig_judge_split(det, judge, path: Path):
    rates = judge_rates(det, judge)
    if not rates:
        return None
    fig, ax = plt.subplots(figsize=(5.4, 2.5))
    width = 0.38
    models = list(rates)
    for i, model in enumerate(models):
        counts = Counter(
            vs.count("suspect") for vs in rates[model]["cases"].values()
        )
        total = rates[model]["n"]
        xs = [0, 1, 2, 3]
        ys = [counts.get(k, 0) / total for k in xs]
        offset = (i - (len(models) - 1) / 2) * width
        ax.bar([x + offset for x in xs], ys, width, label=short(model),
               color=[RED, PURPLE][i % 2], zorder=3)
    ax.set_xticks([0, 1, 2, 3])
    ax.set_xticklabels(["0 of 3", "1 of 3", "2 of 3", "3 of 3"])
    ax.set_xlabel("repeats calling the same poisoned boundary suspect")
    ax.set_ylabel("share of cases")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    recess(ax, axis="y")
    ax.tick_params(axis="x", length=0)
    fig.savefig(path)
    plt.close(fig)
    return {short(m): rates[m]["split_rate"] for m in models}


def fig_localisation(det, path: Path):
    live = [r for r in det["rows"] if not r["crashed"]]
    fig, ax = plt.subplots(figsize=(5.4, 2.4))
    width = 0.38
    buckets = ["upstream\n(work redone)", "exact", "downstream\n(output shipped)", "no resume\nproposed"]
    for i, (name, colour) in enumerate((("schema", BLUE), ("contract", GREEN))):
        counts = [0, 0, 0, 0]
        for r in live:
            e = r["signals"][name]["localisation_error"]
            if e is None:
                counts[3] += 1
            elif e < 0:
                counts[0] += 1
            elif e == 0:
                counts[1] += 1
            else:
                counts[2] += 1
        offset = (i - 0.5) * width
        ax.bar([x + offset for x in range(4)], [c / len(live) for c in counts],
               width, label=name if name == "schema" else "invariants",
               color=colour, zorder=3)
    ax.set_xticks(range(4))
    ax.set_xticklabels(buckets, fontsize=8)
    ax.set_ylabel("share of cases")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    recess(ax, axis="y")
    ax.tick_params(axis="x", length=0)
    fig.savefig(path)
    plt.close(fig)


def fig_selection(path: Path):
    sel = json.loads(Path("benchmark-results/selection.json").read_text())
    live = [r for r in sel["rows"] if not r["crashed"]]
    contested = [r for r in live if r["detectors"]["contract"]["n_flagged"] > 1]
    groups = [("all cases", live), ("more than one\nboundary flagged", contested)]
    names = [("source_order", "source order (no graph)", RED),
             ("causal_root", "causal root (graph)", GREEN)]
    fig, ax = plt.subplots(figsize=(5.4, 2.6))
    width = 0.36
    for i, (key, label, colour) in enumerate(names):
        ys = [sum(1 for r in g if r["detectors"]["contract"]["selectors"][key]["correct"]) / len(g)
              for _, g in groups]
        offset = (i - 0.5) * width
        bars = ax.bar([x + offset for x in range(len(groups))], ys, width,
                      label=label, color=colour, zorder=3)
        for bar, y in zip(bars, ys):
            ax.text(bar.get_x() + bar.get_width() / 2, y + 0.02, f"{y:.0%}",
                    ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[0] for g in groups])
    ax.set_ylabel("repair target correctly identified")
    ax.set_ylim(0, 1.25)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center",
              bbox_to_anchor=(0.5, 1.18))
    recess(ax, axis="y")
    ax.tick_params(axis="x", length=0)
    fig.savefig(path)
    plt.close(fig)
    n_c = len(contested)
    return {"n": len(live), "contested": n_c}


def main() -> int:
    outdir = Path("benchmark-results")
    figdir = Path("../../../../../Users/fabio/Desktop/etiq_trust_benchmark/paper/figures")
    figdir = Path.home() / "Desktop/etiq_trust_benchmark/paper/figures"
    figdir.mkdir(parents=True, exist_ok=True)
    det, judge = load(outdir)
    print("false trust:", fig_false_trust(det, judge, figdir / "false-trust.pdf"))
    fig_by_fault(det, figdir / "by-fault.pdf")
    print("judge split:", fig_judge_split(det, judge, figdir / "judge-split.pdf"))
    fig_localisation(det, figdir / "localisation.pdf")
    print("selection:", fig_selection(figdir / "selection.pdf"))
    print("figures ->", figdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
