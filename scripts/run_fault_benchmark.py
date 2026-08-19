#!/usr/bin/env python3
"""Run the fault corpus against every trust signal and write results as JSON.

Deterministic signals run locally and free. The judge arm calls an OpenAI-compatible
endpoint once per case per model per repeat, so repeats measure a judge's agreement
with itself as well as with the truth.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

from use_case_icp.fault_corpus import (
    BOUNDARIES,
    CONTRACTS,
    SCHEMAS,
    STAGE_INTENT,
    build_corpus,
    build_pipeline,
)
from use_case_icp.fault_scoring import (
    ContractDetector,
    SchemaDetector,
    capture_stage_outputs,
    score,
)

CRASHED = "crashed"


def run_case(pipeline):
    try:
        return capture_stage_outputs(pipeline, BOUNDARIES), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def deterministic(out_path: Path) -> dict:
    corpus = build_corpus()
    clean_outputs, clean_error = run_case(build_pipeline())
    assert clean_error is None, f"clean pipeline must run: {clean_error}"

    schema = SchemaDetector(SCHEMAS)
    contract = ContractDetector(CONTRACTS)
    rows = []
    for case in corpus:
        outputs, error = run_case(case.injected.pipeline)
        row = {
            "case_id": case.case_id,
            "fault": case.fault_name,
            "provenance": case.provenance,
            "boundary": case.boundary,
            "parameter": case.parameter,
            "contaminates": case.injected.ground_truth.contaminated_functions,
            "crashed": error is not None,
            "error": error,
            "signals": {},
        }
        if error is None:
            for name, detector in (("schema", schema), ("contract", contract)):
                labels = detector.label(BOUNDARIES, outputs)
                result = score(case.injected.ground_truth, BOUNDARIES, labels)
                row["signals"][name] = {
                    "labels": labels,
                    "false_trust": result.false_trust,
                    "false_suspects": result.false_suspects,
                    "localisation_error": result.localisation_error,
                    "shipped": result.shipped_contaminated_output,
                }
        rows.append(row)
    payload = {"boundaries": BOUNDARIES, "n_cases": len(rows), "rows": rows}
    out_path.write_text(json.dumps(payload, indent=2))
    return payload


JUDGE_PROMPT = """You are reviewing one stage of an automated market-research pipeline.

Stage name: {boundary}
What this stage is supposed to do: {intent}

This is the value the stage actually produced when it ran:
{output}

Decide whether this output is trustworthy for the stage's stated purpose, or whether
it shows a defect. Answer with JSON only, no other text, in exactly this form:
{{"verdict": "trusted", "reason": "<one short sentence>"}}
or
{{"verdict": "suspect", "reason": "<one short sentence>"}}"""


def ask(endpoint: str, model: str, prompt: str, timeout: int = 180) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 160,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    request = urllib.request.Request(
        f"{endpoint}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    return payload["choices"][0]["message"]["content"]


def parse_verdict(text: str) -> str | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        verdict = str(json.loads(text[start:end + 1]).get("verdict", "")).lower().strip()
    except json.JSONDecodeError:
        return None
    return verdict if verdict in {"trusted", "suspect"} else None


def judge(det: dict, out_path: Path, endpoint: str, models: list[str], repeats: int) -> None:
    existing = json.loads(out_path.read_text()) if out_path.exists() else {"verdicts": []}
    done = {(v["case_id"], v["model"], v["repeat"]) for v in existing["verdicts"]}
    clean_outputs, _ = run_case(build_pipeline())
    corpus = {case.case_id: case for case in build_corpus()}

    # Model is the OUTER loop on purpose. Interleaving models makes an MLX server
    # reload weights on every call, which dominated wall clock in a first attempt.
    prompts = {}
    for row in det["rows"]:
        if row["crashed"]:
            continue
        outputs, _ = run_case(corpus[row["case_id"]].injected.pipeline)
        prompts[row["case_id"]] = JUDGE_PROMPT.format(
            boundary=row["boundary"],
            intent=STAGE_INTENT[row["boundary"]],
            output=json.dumps(outputs.get(row["boundary"]), indent=2, default=str)[:2000],
        )

    live = [r for r in det["rows"] if not r["crashed"]]
    total = len(live) * len(models) * repeats
    count = 0
    started = time.time()
    for model in models:
        print(f"model {model}", flush=True)
        for repeat in range(repeats):
            for row in live:
                count += 1
                key = (row["case_id"], model, repeat)
                if key in done:
                    continue
                try:
                    verdict = parse_verdict(ask(endpoint, model, prompts[row["case_id"]]))
                except Exception as exc:
                    verdict = None
                    print(f"  error {type(exc).__name__} on {row['case_id']}", flush=True)
                existing["verdicts"].append({
                    "case_id": row["case_id"],
                    "boundary": row["boundary"],
                    "fault": row["fault"],
                    "model": model,
                    "repeat": repeat,
                    "verdict": verdict,
                })
                out_path.write_text(json.dumps(existing, indent=2))
                if count % 20 == 0:
                    rate = count / max(time.time() - started, 1e-9)
                    remaining = (total - count) / max(rate, 1e-9) / 60
                    print(f"  {count}/{total} ({rate:.2f}/s, ~{remaining:.0f} min left)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="benchmark-results")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--endpoint", default="http://localhost:8082")
    parser.add_argument("--models", nargs="*", default=[
        "mlx-community/Qwen3.8-27B-8bit",
        "mlx-community/Llama-3.2-3B-Instruct-4bit",
    ])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    det_path = outdir / "deterministic.json"
    det = deterministic(det_path)
    print(f"deterministic: {det['n_cases']} cases -> {det_path}")
    if args.judge:
        judge(det, outdir / "judge.json", args.endpoint, args.models, args.repeats)
        print("judge arm complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
