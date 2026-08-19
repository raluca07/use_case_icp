from __future__ import annotations

import importlib.metadata
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .etiq_worker import EXPECTED_ETIQ_VERSION, persist_result, scan_source
from .records import (
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    GeneratedPipeline,
)
from .job_store import JobStore

@dataclass(slots=True)
class EtiqExecution:
    snapshot: EtiqEvidenceSnapshot
    run_dir: Path

    @property
    def reviewable(self) -> bool:
        return not self.snapshot.scan_errors and bool(self.snapshot.nodes)


DEFAULT_MEMORY_LIMIT_MB = 2048
DEFAULT_CPU_LIMIT_SECONDS = 900


def worker_limits(runtime_input: Any | None) -> dict[str, int]:
    """Resource limits for the generated-pipeline worker.

    The caller may lower or raise these. They previously defaulted to 0, which
    `_apply_limits` reads as "apply no limit at all". See issue #1.
    """
    limits: dict[str, Any] = {}
    if isinstance(runtime_input, dict):
        request = runtime_input.get("request")
        if isinstance(request, dict) and isinstance(request.get("limits"), dict):
            limits = request["limits"]
    return {
        "memory_limit_mb": int(limits.get("etiq_memory_mb", DEFAULT_MEMORY_LIMIT_MB)),
        "cpu_limit_seconds": int(
            limits.get("etiq_cpu_seconds", DEFAULT_CPU_LIMIT_SECONDS)
        ),
    }


class EtiqExecutor:
    """Runs one generated entry source through Etiq and persists captured evidence."""

    def __init__(
        self,
        store: JobStore,
        scanner_factory: Callable[[], Any] | None = None,
        *,
        timeout_seconds: int = 1800,
    ) -> None:
        self.store = store
        self._scanner_factory = scanner_factory
        self.timeout_seconds = timeout_seconds

    def _scanner(self) -> Any:
        if self._scanner_factory is not None:
            return self._scanner_factory()
        try:
            from etiq_copilot.engine.implementations.scanner import (  # type: ignore[import-not-found]
                DebuggerCodeScanner,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Etiq is not installed. Install the pinned PyPI release from requirements-etiq.txt."
            ) from exc
        installed_version = importlib.metadata.version("etiq-copilot")
        if installed_version != EXPECTED_ETIQ_VERSION:
            raise RuntimeError(
                f"Unsupported etiq-copilot version {installed_version}; expected {EXPECTED_ETIQ_VERSION} from PyPI."
            )
        return DebuggerCodeScanner()

    def _load_snapshot(self, run_dir: Path) -> EtiqEvidenceSnapshot:
        summary = self.store.read_json(run_dir / "etiq-snapshot.json")
        return EtiqEvidenceSnapshot(
            snapshot_id=str(summary["snapshot_id"]),
            job_id=str(summary["job_id"]),
            run_id=str(summary["run_id"]),
            nodes=[
                EtiqNodeRecord(**item)
                for item in self.store.read_json(run_dir / "etiq-nodes.json", [])
            ],
            relationships=[
                EtiqRelationshipRecord(**item)
                for item in self.store.read_json(run_dir / "etiq-relationships.json", [])
            ],
            inventories=self.store.read_json(run_dir / "etiq-inventory.json", {}),
            scan_errors=self.store.read_json(run_dir / "etiq-scan-errors.json", []),
            created_at=str(summary["created_at"]),
            schema_version=str(summary["schema_version"]),
        )

    def _worker_environment(
        self,
        runtime_input: Any | None,
        *,
        home: Path,
    ) -> dict[str, str]:
        allowed = {
            "LANG",
            "LC_ALL",
            "PATH",
            "REQUESTS_CA_BUNDLE",
            "SSL_CERT_FILE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
        }
        if isinstance(runtime_input, dict):
            request = runtime_input.get("request")
            if isinstance(request, dict):
                policy = request.get("source_policy")
                if isinstance(policy, dict):
                    allowed.update(str(name) for name in policy.get("environment_allowlist", []))
        environment = {name: os.environ[name] for name in allowed if name in os.environ}
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        # Set last so a source_policy allowlist cannot hand the generated pipeline the
        # real home directory, and with it ~/.codex/auth.json, ~/.ssh and ~/.aws.
        home.mkdir(parents=True, exist_ok=True)
        environment["HOME"] = str(home)
        return environment

    def _run_worker(self, request_path: Path, runtime_input: Any | None) -> None:
        process = subprocess.Popen(
            [sys.executable, "-m", "use_case_icp.etiq_worker", str(request_path)],
            cwd=request_path.parent,
            env=self._worker_environment(
                runtime_input,
                home=request_path.parent / "worker-home",
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            stdout, stderr = process.communicate()
        (request_path.parent / "worker-stdout.log").write_text(stdout, encoding="utf-8")
        (request_path.parent / "worker-stderr.log").write_text(stderr, encoding="utf-8")
        if timed_out:
            raise TimeoutError(f"Etiq worker exceeded {self.timeout_seconds} seconds")
        if process.returncode != 0:
            raise RuntimeError(f"Etiq worker failed with exit code {process.returncode}")

    def execute(
        self,
        *,
        job_id: str,
        segment_id: str,
        stage: str,
        run_id: str,
        pipeline: GeneratedPipeline,
        invocation_id: str | None = None,
        runtime_input: Any | None = None,
        network_mode: str | None = None,
        network_cassette_path: Path | None = None,
    ) -> EtiqExecution:
        pipeline.validate()
        run_dir = self.store.stage_run_dir(job_id, segment_id, stage, run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "pipeline-stdout.log").write_text("", encoding="utf-8")
        (run_dir / "pipeline-stderr.log").write_text("", encoding="utf-8")
        if invocation_id:
            self.store.write_json(run_dir / "codex-invocation-ref.json", {"invocation_id": invocation_id})
        try:
            manifest = self.store.materialize_pipeline(run_dir, pipeline)
            if runtime_input is not None:
                self.store.write_json(run_dir / "pipeline-input.json", runtime_input)
            bundle_dir = run_dir / "pipeline"
            for item in pipeline.files:
                compile(item.content, item.path, "exec")
            if self._scanner_factory is not None:
                result, stdout, stderr = scan_source(
                    self._scanner(),
                    bundle_dir=bundle_dir,
                    entry_file=pipeline.entry_file,
                    runtime_input=runtime_input,
                    network_mode=network_mode,
                    network_cassette_path=network_cassette_path,
                )
                (run_dir / "pipeline-stdout.log").write_text(stdout, encoding="utf-8")
                (run_dir / "pipeline-stderr.log").write_text(stderr, encoding="utf-8")
                persist_result(
                    self.store,
                    run_dir=run_dir,
                    job_id=job_id,
                    run_id=run_id,
                    manifest_hash=manifest["manifest_hash"],
                    result=result,
                )
            else:
                limits = worker_limits(runtime_input)
                worker_request = {
                    "output_root": str(self.store.output_root),
                    "run_dir": str(run_dir),
                    "job_id": job_id,
                    "run_id": run_id,
                    "entry_file": pipeline.entry_file,
                    "manifest_hash": manifest["manifest_hash"],
                    "memory_limit_mb": limits["memory_limit_mb"],
                    "cpu_limit_seconds": limits["cpu_limit_seconds"],
                    "network_mode": network_mode,
                    "network_cassette_path": (
                        str(network_cassette_path.resolve())
                        if network_cassette_path is not None
                        else None
                    ),
                }
                request_path = run_dir / "worker-request.json"
                self.store.write_json(request_path, worker_request)
                self._run_worker(request_path, runtime_input)
        except Exception as exc:
            if not (run_dir / "execution-error.json").exists():
                self.store.write_json(
                    run_dir / "execution-error.json",
                    {"error_type": type(exc).__name__, "message": str(exc)},
                )
            raise

        try:
            snapshot = self._load_snapshot(run_dir)
        except Exception as exc:
            self.store.write_json(
                run_dir / "execution-error.json",
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "phase": "etiq_result_serialization",
                },
            )
            raise
        return EtiqExecution(snapshot=snapshot, run_dir=run_dir)
