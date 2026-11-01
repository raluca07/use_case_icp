"""Two real reviews (arms A and C) of the hand-built persistent fixture with claude-haiku-5-5.

Writes to runs/smoke2/ (the first smoke run in runs/smoke/ used the pre-fix runner). The assertions run after
the loop so that both reviews are always saved and printed first.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

from builders import persistent_trace  # noqa: E402

from rdr.packager import build_package  # noqa: E402
from rdr.runner import review  # noqa: E402

MODEL = "claude-haiku-5-5"
OUT = REPO / "runs" / "smoke2"
rows = []
for arm in ("A", "C"):
    package = build_package(arm, persistent_trace(), "splitwise.expenses#77", "smoke-1")
    with tempfile.TemporaryDirectory() as empty:
        record = review(package, OUT / f"{arm}.json", MODEL, "medium", Path(empty))
    usage = record["usage"]
    total_in = sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    rows.append((arm, record, total_in, len(package)))
    print(json.dumps({"arm": arm, "answer": record["answer"], "served": record["served_models"],
                      "input_tokens_total": total_in, "package_chars": len(package),
                      "wall_seconds": round(record["wall_seconds"], 1)}, indent=2))

for arm, record, total_in, _ in rows:
    assert total_in < 5000, f"arm {arm}: context larger than expected ({total_in}); isolation may have failed"
    assert MODEL in record["served_models"], f"arm {arm}: served {record['served_models']}"
    assert record["envelope"]["is_error"] is False, f"arm {arm}: error envelope"
    assert len(record["stdout_sha256"]) == 64 and len(record["command_sha256"]) == 64
print("smoke OK")
