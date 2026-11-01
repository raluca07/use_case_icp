"""Gate 0 discovery: print the AppWorld facts Plan 2 depends on.

Prints field NAMES and TYPES only. AppWorld data must not leave this machine in plain text.
"""
import json
from pathlib import Path

from appworld import AppWorld, load_task_ids, update_root

ROOT = Path(__file__).resolve().parents[1] / "appworld_root"
update_root(str(ROOT))


def shape(obj, depth=0):
    if depth > 3:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {k: shape(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shape(obj[0], depth + 1)] if obj else []
    return type(obj).__name__


train, dev = load_task_ids("train"), load_task_ids("dev")
print("Q1 train/dev task counts:", len(train), len(dev))
task_id = train[0]
print("task:", task_id)
gt_dir = ROOT / "data" / "tasks" / task_id / "ground_truth"
print("Q2 ground_truth files:", sorted(p.name for p in gt_dir.iterdir()) if gt_dir.exists() else "MISSING")
with AppWorld(task_id=task_id, experiment_name="rdr_discovery", ground_truth_mode="full") as world:
    gt = world.task.ground_truth
    print("Q2 ground_truth attributes:", [a for a in dir(gt) if not a.startswith("_")])
    calls = gt.api_calls
    print("Q2 api_calls container:", type(calls).__name__, "length", len(calls))
    first = calls[0]
    print("Q2 api_calls[0] shape:", json.dumps(shape(first)) if isinstance(first, (dict, list)) else type(first).__name__)
    print("Q2 compiled_solution_module type:", type(gt.compiled_solution_module).__name__)
    print("Q2 compiled_solution_module attributes:", [a for a in dir(gt.compiled_solution_module) if not a.startswith("_")])
    print("Q11 world attributes:", [a for a in dir(world) if not a.startswith("_")])
    print("Q11 shell namespace probe:", world.execute("print(sorted(k for k in globals() if not k.startswith('_')))"))
out = ROOT / "experiments" / "outputs" / "rdr_discovery" / "tasks" / task_id
print("output dir exists:", out.exists())
if out.exists():
    print("output files:", sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()))
