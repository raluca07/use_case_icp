#!/usr/bin/env python3
"""Control arm: ask the judge about boundaries that are known to be clean.

The main judge arm only ever asks about the poisoned boundary, so a judge that
answers "suspect" indiscriminately scores a perfect false-trust rate while being
useless. This measures the other half: how often it calls a sound boundary suspect.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from use_case_icp.fault_corpus import BOUNDARIES, STAGE_INTENT, build_corpus, build_pipeline
from use_case_icp.fault_scoring import capture_stage_outputs
from scripts.run_fault_benchmark import JUDGE_PROMPT, ask, parse_verdict

ENDPOINT = "http://localhost:8091"
MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"
REPEATS = 3
OUT = Path("benchmark-results/judge_control.json")


def main() -> int:
    corpus = {c.case_id: c for c in build_corpus()}
    det = json.loads(Path("benchmark-results/deterministic.json").read_text())
    live = [r for r in det["rows"] if not r["crashed"]]

    targets = []
    # 1. Every boundary of the clean, unfaulted pipeline.
    clean_out = capture_stage_outputs(build_pipeline(), BOUNDARIES)
    for b in BOUNDARIES:
        targets.append(("CLEAN_PIPELINE", b, clean_out[b]))
    # 2. Per case, a boundary strictly upstream of the fault: cannot be contaminated.
    for r in live:
        idx = BOUNDARIES.index(r["boundary"])
        if idx == 0:
            continue
        upstream = BOUNDARIES[idx - 1]
        out = capture_stage_outputs(corpus[r["case_id"]].injected.pipeline, BOUNDARIES)
        targets.append((r["case_id"], upstream, out[upstream]))

    existing = json.loads(OUT.read_text()) if OUT.exists() else {"verdicts": []}
    done = {(v["case_id"], v["boundary"], v["repeat"]) for v in existing["verdicts"]}
    print(f"control targets: {len(targets)} x {REPEATS} repeats", flush=True)
    for i, (case_id, boundary, value) in enumerate(targets):
        prompt = JUDGE_PROMPT.format(
            boundary=boundary, intent=STAGE_INTENT[boundary],
            output=json.dumps(value, indent=2, default=str)[:2000])
        for repeat in range(REPEATS):
            if (case_id, boundary, repeat) in done:
                continue
            try:
                verdict = parse_verdict(ask(ENDPOINT, MODEL, prompt))
            except Exception as exc:
                print(f"  err {type(exc).__name__}", flush=True); verdict = None
            existing["verdicts"].append({"case_id": case_id, "boundary": boundary,
                                         "repeat": repeat, "verdict": verdict})
            OUT.write_text(json.dumps(existing, indent=2))
        if i % 5 == 0:
            print(f"  {i}/{len(targets)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
