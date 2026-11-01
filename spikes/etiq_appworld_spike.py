"""Gate 0 spike: does Etiq capture data flow of AppWorld agent code?

Usage:
  .venv/bin/python spikes/etiq_appworld_spike.py TASK_ID GOLD_CODE_PATH OUT_JSON --mode exec
  .venv/bin/python spikes/etiq_appworld_spike.py TASK_ID GOLD_CODE_PATH OUT_JSON --mode inline --apis-expr "<Q11 expression>"

exec:   scanned source calls world.execute(gold_code); tests whether Etiq sees inside the shell.
inline: scanned source binds `apis` from the Q11 expression and runs gold_code as top-level statements.
"""
import argparse
import json
import textwrap
from pathlib import Path

from etiq_copilot.engine.implementations.scanner import DebuggerCodeScanner

ROOT = Path(__file__).resolve().parents[1] / "appworld_root"

parser = argparse.ArgumentParser()
parser.add_argument("task_id")
parser.add_argument("gold_code_path", type=Path)
parser.add_argument("out_json", type=Path)
parser.add_argument("--mode", choices=["exec", "inline"], required=True)
parser.add_argument("--apis-expr", default=None)
args = parser.parse_args()
gold_code = args.gold_code_path.read_text()

prelude = (
    "from appworld import AppWorld, update_root\n"
    f"update_root({str(ROOT)!r})\n"
    f"world = AppWorld(task_id={args.task_id!r}, experiment_name='rdr_etiq_spike')\n"
)
if args.mode == "exec":
    source = prelude + f"output = world.execute({gold_code!r})\nprint(output)\nworld.close()\n"
else:
    if not args.apis_expr:
        parser.error("--mode inline needs --apis-expr")
    # Adaptation: the gold file defines solution(apis, requester) and calls it, so `requester` must also be bound.
    source = prelude + f"apis = {args.apis_expr}\nrequester = world.requester\n" + textwrap.dedent(gold_code) + "\nworld.close()\n"

result = DebuggerCodeScanner().scan_code(code_str=source)
native = result.create_full_lineage_graph(graph_format="json")
args.out_json.parent.mkdir(parents=True, exist_ok=True)
args.out_json.write_text(native if isinstance(native, str) else json.dumps(native))
graph = json.loads(args.out_json.read_text())
labels = [str(o.get("label", "")) for o in graph.get("objects", [])]
# Adaptation: scan_code swallows exceptions of the scanned program into result.scan_errors; surface them.
scan_errors = result.scan_errors
print(json.dumps({
    "mode": args.mode,
    "scan_error_type": scan_errors.get("type") if isinstance(scan_errors, dict) else None,
    "objects": len(graph.get("objects", [])),
    "edges": len(graph.get("edges", [])),
    "objects_mentioning_apis": sum("apis." in label for label in labels),
}, indent=2))
