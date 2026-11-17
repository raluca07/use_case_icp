"""Fresh-root subprocess execution for v2 qualification and variant construction."""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from rdr.appworld_adapter import Plan
from rdr.v2_feasibility import DEFAULT_FIXTURE_ROOT, REPO, _invoice_body, load_fixture, run_reference


PYTHON = REPO / ".venv" / "bin" / "python"


def _copy_fixture(source: Path, destination: Path) -> str:
    """Create an independent fixture tree, preferring filesystem copy-on-write."""
    command = ["cp", "--reflink=auto", "-a", str(source), str(destination)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        return "cp --reflink=auto -a"
    shutil.copytree(source, destination)
    return "shutil.copytree"


def run_fresh_cell(
    source: str,
    author: str,
    plan: dict | None = None,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    timeout_seconds: int = 180,
    fixture: dict | None = None,
) -> dict:
    """Run one cell in a copied fixture root and own the complete worker process group."""
    with tempfile.TemporaryDirectory(prefix="rdr-v2-world-") as temporary:
        temporary_path = Path(temporary)
        copied_root = temporary_path / "root"
        copy_method = _copy_fixture(fixture_root, copied_root)
        if fixture is not None:
            base = load_fixture()
            gmail = copied_root / "data" / "tasks" / "rdrinv01_1" / "dbs" / "gmail.jsonl"
            text = gmail.read_text()
            for old, new in zip([*base["invoices"], base["unmatched_invoice"]],
                                [*fixture["invoices"], fixture["unmatched_invoice"]]):
                text = text.replace(_invoice_body(old), _invoice_body(new))
                text = text.replace("Invoice request: " + old["subject_suffix"],
                                    "Invoice request: " + new["subject_suffix"])
            gmail.write_text(text)
        request_path = temporary_path / "request.json"
        output_path = temporary_path / "result.json"
        request_path.write_text(json.dumps({"source": source, "author": author, "plan": plan or {},
                                            "fixture": fixture}))
        command = [str(PYTHON), "-m", "rdr.v2_live", "worker", "--request", str(request_path),
                   "--out", str(output_path), "--fixture-root", str(copied_root)]
        environment = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(REPO / "src")}
        process = subprocess.Popen(
            command,
            cwd=REPO,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            raise TimeoutError(
                f"fresh AppWorld cell exceeded {timeout_seconds}s; process group terminated; "
                f"stderr={stderr[-8000:]}"
            )
        if process.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"fresh AppWorld worker failed ({process.returncode}): {stderr[-2000:]}")
        result = json.loads(output_path.read_text())
        result["fault_plan"] = plan or {}
        result["process"] = {
            "copy_method": copy_method,
            "fresh_root": True,
            "timeout_seconds": timeout_seconds,
            "returncode": process.returncode,
            "stdout_sha256": __import__("hashlib").sha256(stdout.encode()).hexdigest(),
            "stderr_sha256": __import__("hashlib").sha256(stderr.encode()).hexdigest(),
            "process_group_owned": True,
            "root_cleaned": True,
        }
        return result


def _worker(request_path: Path, output_path: Path, fixture_root: Path) -> None:
    debug_after = os.environ.get("RDR_DEBUG_STACK_SECONDS")
    if debug_after:
        faulthandler.dump_traceback_later(float(debug_after), file=sys.stderr)
    request = json.loads(request_path.read_text())
    result = run_reference(
        experiment="v2_cell_" + uuid.uuid4().hex[:16],
        artifact_state="clean",
        fixture_root=fixture_root,
        source_text=request["source"],
        plan=Plan.from_dict(request.get("plan")),
        author=request["author"],
        include_private=True,
        fixture_data=request.get("fixture"),
    )
    output_path.write_text(json.dumps(result, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--request", type=Path, required=True)
    worker.add_argument("--out", type=Path, required=True)
    worker.add_argument("--fixture-root", type=Path, required=True)
    args = parser.parse_args(argv)
    _worker(args.request, args.out, args.fixture_root)


if __name__ == "__main__":
    main(sys.argv[1:])
