from __future__ import annotations

import contextlib
import importlib.metadata
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from .etiq_graph import serialize_etiq_result
from .job_store import JobStore
from .records import jsonable

EXPECTED_ETIQ_VERSION = "2.3.0"


def scan_source(
    scanner: Any,
    *,
    bundle_dir: Path,
    entry_file: str,
    runtime_input: Any | None,
) -> tuple[Any, str, str]:
    entry_source = (bundle_dir / entry_file).read_text(encoding="utf-8")
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    old_cwd = Path.cwd()
    old_path = list(sys.path)
    old_argv = list(sys.argv)
    old_stdin = sys.stdin
    try:
        os.chdir(bundle_dir)
        sys.path.insert(0, str(bundle_dir))
        sys.argv = [entry_file]
        if runtime_input is not None:
            sys.stdin = io.StringIO(json.dumps(jsonable(runtime_input), ensure_ascii=False))
        try:
            with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
                result = scanner.scan_code(code_str=entry_source)
        except SystemExit as exc:
            raise RuntimeError(f"generated pipeline exited during Etiq execution with code {exc.code}") from exc
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path
        sys.argv = old_argv
        sys.stdin = old_stdin
    return result, captured_stdout.getvalue(), captured_stderr.getvalue()


def persist_result(
    store: JobStore,
    *,
    run_dir: Path,
    job_id: str,
    run_id: str,
    manifest_hash: str,
    result: Any,
) -> None:
    snapshot = serialize_etiq_result(job_id=job_id, run_id=run_id, result=result)
    store.write_json(run_dir / "etiq-nodes.json", snapshot.nodes)
    store.write_json(run_dir / "etiq-relationships.json", snapshot.relationships)
    store.write_json(run_dir / "etiq-inventory.json", snapshot.inventories)
    store.write_json(run_dir / "etiq-scan-errors.json", snapshot.scan_errors)
    store.write_json(
        run_dir / "etiq-snapshot.json",
        {
            "snapshot_id": snapshot.snapshot_id,
            "job_id": job_id,
            "run_id": run_id,
            "manifest_hash": manifest_hash,
            "node_count": len(snapshot.nodes),
            "relationship_count": len(snapshot.relationships),
            "reviewable": not snapshot.scan_errors and bool(snapshot.nodes),
            "created_at": snapshot.created_at,
            "schema_version": snapshot.schema_version,
        },
    )


def _apply_limits(request: dict[str, Any]) -> None:
    try:
        import resource
    except ImportError:
        return
    memory_mb = int(request.get("memory_limit_mb") or 0)
    cpu_seconds = int(request.get("cpu_limit_seconds") or 0)
    if memory_mb > 0:
        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    if cpu_seconds > 0:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv or sys.argv[1:])
    if len(arguments) != 1:
        print("usage: python -m use_case_icp.etiq_worker <request.json>", file=sys.stderr)
        return 2
    request_path = Path(arguments[0]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    run_dir = Path(request["run_dir"]).resolve()
    store = JobStore(request["output_root"])
    _apply_limits(request)
    try:
        installed_version = importlib.metadata.version("etiq-copilot")
        if installed_version != EXPECTED_ETIQ_VERSION:
            raise RuntimeError(
                f"Unsupported etiq-copilot version {installed_version}; "
                f"expected {EXPECTED_ETIQ_VERSION} from PyPI."
            )
        from etiq_copilot.engine.implementations.scanner import DebuggerCodeScanner

        runtime_input = store.read_json(run_dir / "pipeline-input.json")
        result, stdout, stderr = scan_source(
            DebuggerCodeScanner(),
            bundle_dir=run_dir / "pipeline",
            entry_file=str(request["entry_file"]),
            runtime_input=runtime_input,
        )
        (run_dir / "pipeline-stdout.log").write_text(stdout, encoding="utf-8")
        (run_dir / "pipeline-stderr.log").write_text(stderr, encoding="utf-8")
        persist_result(
            store,
            run_dir=run_dir,
            job_id=str(request["job_id"]),
            run_id=str(request["run_id"]),
            manifest_hash=str(request["manifest_hash"]),
            result=result,
        )
    except Exception as exc:
        store.write_json(
            run_dir / "execution-error.json",
            {"error_type": type(exc).__name__, "message": str(exc), "phase": "etiq_worker"},
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
