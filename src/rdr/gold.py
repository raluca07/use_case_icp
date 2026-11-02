"""Gold runs and the per-task determinism gate (spec section 4, carry-over decision 5).

Every eligible train/dev task's gold code runs twice, each time in its own subprocess world with
PYTHONHASHSEED=0. The task passes the gate when both runs succeed, pass `world.evaluate()`, and reach the same
end state (same digest of every changed row, system rows included) with identical traces.
Output (gitignored): runs/gold/<task_id>/{trace.json, evaluation.json} and runs/gold/determinism.json.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXCLUDED_GENERATORS = frozenset({"3c13f5a", "df61dc5"})
GOLD_DIR = Path(__file__).resolve().parents[2] / "runs" / "gold"


def generator_of(task_id: str) -> str:
    return task_id.split("_", 1)[0]


def eligible(task_ids) -> list[str]:
    return sorted(t for t in task_ids if generator_of(t) not in EXCLUDED_GENERATORS)


def gate_verdict(first, second) -> dict:
    """Compare two RunResults of the same gold code."""
    reasons = []
    for name, run in (("first", first), ("second", second)):
        if not run.succeeded:
            reasons.append(f"{name} run did not execute cleanly")
        elif not run.evaluation.get("success"):
            reasons.append(f"{name} run failed evaluation")
    if first.digest != second.digest:
        reasons.append("end states differ")
    elif first.trace is not None and second.trace is not None and first.trace.to_dict() != second.trace.to_dict():
        reasons.append("traces differ")
    return {"passed": not reasons, "reasons": reasons, "digest": first.digest}


def gate_task(task_id: str, out_dir: Path) -> dict:
    from rdr.appworld_adapter import run_task

    first, second = run_task(task_id), run_task(task_id)
    verdict = gate_verdict(first, second)
    task_dir = out_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    if first.trace is not None:
        first.trace.save(task_dir / "trace.json")
        (task_dir / "evaluation.json").write_text(json.dumps(first.evaluation, indent=2, sort_keys=True))
    return {"task_id": task_id, **verdict}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=GOLD_DIR)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--tasks", nargs="*")
    args = parser.parse_args(argv)
    if args.tasks:
        tasks = eligible(args.tasks)
    else:
        from appworld import load_task_ids, update_root

        from rdr.appworld_adapter import APPWORLD_ROOT
        update_root(str(APPWORLD_ROOT))
        tasks = eligible(load_task_ids("train") + load_task_ids("dev"))
    args.out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(args.workers) as pool:
        verdicts = list(pool.map(lambda t: gate_task(t, args.out), tasks))
    gate_file = args.out / "determinism.json"
    previous = json.loads(gate_file.read_text()) if gate_file.exists() and args.tasks else {}
    previous.update({v["task_id"]: v for v in verdicts})
    gate_file.write_text(json.dumps(previous, indent=2, sort_keys=True))
    passed = sum(v["passed"] for v in previous.values())
    print(f"determinism gate: {passed} of {len(previous)} tasks pass")


if __name__ == "__main__":
    main()
