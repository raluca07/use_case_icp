from __future__ import annotations

import contextlib
import base64
import hashlib
import importlib.metadata
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .etiq_graph import serialize_etiq_result
from .job_store import JobStore
from .records import jsonable, stable_hash

EXPECTED_ETIQ_VERSION = "2.3.0"


def scan_source(
    scanner: Any,
    *,
    bundle_dir: Path,
    entry_file: str,
    runtime_input: Any | None,
    network_mode: str | None = None,
    network_cassette_path: Path | None = None,
) -> tuple[Any, str, str]:
    entry_source = (bundle_dir / entry_file).read_text(encoding="utf-8")
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    old_cwd = Path.cwd()
    old_path = list(sys.path)
    old_argv = list(sys.argv)
    old_stdin = sys.stdin
    original_urlopen = urllib.request.urlopen
    cassette: list[dict[str, Any]] = []
    replay_uses: dict[tuple[str, str], int] = {}
    if network_mode == "replay":
        if network_cassette_path is None:
            raise ValueError("network replay requires a cassette path")
        cassette = json.loads(network_cassette_path.read_text(encoding="utf-8"))

    def buffered_response(body: bytes, item: dict[str, Any]) -> io.BytesIO:
        response = io.BytesIO(body)
        response.status = int(item.get("status") or 200)  # type: ignore[attr-defined]
        response.headers = dict(item.get("headers") or {})  # type: ignore[attr-defined]
        response.reason = str(item.get("reason") or "")  # type: ignore[attr-defined]
        response.url = str(item["url"])  # type: ignore[attr-defined]
        response.geturl = lambda: response.url  # type: ignore[attr-defined]
        response.getcode = lambda: response.status  # type: ignore[attr-defined]
        response.info = lambda: response.headers  # type: ignore[attr-defined]
        return response

    def urlopen(request: Any, *args: Any, **kwargs: Any) -> Any:
        url = str(getattr(request, "full_url", request))
        method = str(
            request.get_method() if hasattr(request, "get_method") else "GET"
        )
        if network_mode == "replay":
            matching = [
                item
                for item in cassette
                if item["method"] == method and item["url"] == url
            ]
            key = (method, url)
            used = replay_uses.get(key, 0)
            if not matching:
                raise RuntimeError(f"unrecorded network request: {method} {url}")
            if used >= len(matching):
                raise RuntimeError(f"recorded request count exhausted: {method} {url}")
            item = matching[used]
            replay_uses[key] = used + 1
            if item.get("error"):
                raise urllib.error.URLError(str(item["error"]))
            return buffered_response(
                base64.b64decode(str(item["body_base64"])),
                item,
            )
        try:
            response = original_urlopen(request, *args, **kwargs)
            body = response.read()
            item = {
                "method": method,
                "url": url,
                "status": int(getattr(response, "status", 200) or 200),
                "reason": str(getattr(response, "reason", "") or ""),
                "headers": {
                    str(name): str(value)
                    for name, value in dict(
                        getattr(response, "headers", {}) or {}
                    ).items()
                    if str(name).lower()
                    not in {"authorization", "proxy-authorization", "set-cookie"}
                },
                "body_base64": base64.b64encode(body).decode("ascii"),
            }
            cassette.append(item)
            return buffered_response(body, item)
        except Exception as exc:
            cassette.append(
                {
                    "method": method,
                    "url": url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            raise

    try:
        if network_mode in {"record", "replay"}:
            urllib.request.urlopen = urlopen
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
        urllib.request.urlopen = original_urlopen
        if network_mode == "record" and network_cassette_path is not None:
            network_cassette_path.write_text(
                json.dumps(cassette, indent=2, sort_keys=True),
                encoding="utf-8",
            )
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
    export = getattr(result, "create_full_lineage_graph", None)
    if not callable(export):
        raise RuntimeError("Etiq scan result does not expose create_full_lineage_graph()")
    native_text = export(graph_format="json")
    if not isinstance(native_text, str):
        raise TypeError("Etiq native JSON lineage export did not return text")
    native_lineage = json.loads(native_text)
    if not isinstance(native_lineage, dict):
        raise ValueError("Etiq native JSON lineage export is not an object")
    if not isinstance(native_lineage.get("objects"), list) or not isinstance(
        native_lineage.get("edges"), list
    ):
        raise ValueError("Etiq native JSON lineage export lacks objects or edges")
    native_path = run_dir / "etiq-native-lineage.json"
    store.write_json(native_path, native_lineage)
    native_file_sha256 = "sha256:" + hashlib.sha256(native_path.read_bytes()).hexdigest()
    native_logical_sha256 = "sha256:" + stable_hash(native_lineage)

    snapshot = serialize_etiq_result(job_id=job_id, run_id=run_id, result=result)
    snapshot.inventories["json_lineage_export"] = "captured"
    snapshot.inventories["native_lineage_file"] = native_path.name
    snapshot.inventories["native_lineage_file_sha256"] = native_file_sha256
    snapshot.inventories["native_lineage_logical_sha256"] = native_logical_sha256
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
            "native_lineage_export_status": "captured",
            "native_lineage_file": native_path.name,
            "native_lineage_file_sha256": native_file_sha256,
            "native_lineage_logical_sha256": native_logical_sha256,
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
            network_mode=request.get("network_mode"),
            network_cassette_path=(
                Path(request["network_cassette_path"])
                if request.get("network_cassette_path")
                else None
            ),
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
