from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable

from .records import (
    AgentRequest,
    JobEvent,
    RootJobState,
    TrustAnnotation,
    jsonable,
    stable_hash,
    utc_now,
)


class JobStore:
    """Small atomic JSON/JSONL store rooted under outputs/jobs."""

    def __init__(self, output_root: Path | str = "outputs/jobs") -> None:
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def job_dir(self, job_id: str) -> Path:
        if not job_id or "/" in job_id or ".." in job_id:
            raise ValueError("invalid job_id")
        return self.output_root / job_id

    def stage_run_dir(self, job_id: str, segment_id: str, stage: str, run_id: str) -> Path:
        return self.job_dir(job_id) / "stages" / segment_id / stage / "runs" / run_id

    def receipt_path(self, job_id: str, run_id: str, section_id: str) -> Path:
        return self.job_dir(job_id) / "receipts" / f"{run_id}-{section_id}.json"

    def final_result_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "final" / "result.json"

    def initialize_job(self, request: AgentRequest, state: RootJobState) -> Path:
        request.validate()
        job_dir = self.job_dir(state.job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        self.write_json(job_dir / "request.json", request)
        self.write_json(job_dir / "state.json", state)
        (job_dir / "events.jsonl").touch(exist_ok=True)
        return job_dir

    def load_state(self, job_id: str) -> RootJobState:
        payload = self.read_json(self.job_dir(job_id) / "state.json")
        if not isinstance(payload, dict):
            raise FileNotFoundError(f"state not found for {job_id}")
        return RootJobState(**payload)

    def update_state(self, job_id: str, **changes: Any) -> RootJobState:
        state = self.load_state(job_id)
        for name, value in changes.items():
            if not hasattr(state, name):
                raise ValueError(f"unknown job state field: {name}")
            setattr(state, name, value)
        state.updated_at = utc_now()
        self.write_json(self.job_dir(job_id) / "state.json", state)
        return state

    def increment_repair(self, job_id: str) -> RootJobState:
        state = self.load_state(job_id)
        return self.update_state(job_id, repair_count=state.repair_count + 1)

    def record_repair_evaluation(self, job_id: str, *, effective: bool) -> RootJobState:
        state = self.load_state(job_id)
        return self.update_state(
            job_id,
            evaluated_repair_count=state.evaluated_repair_count + 1,
            effective_repair_count=state.effective_repair_count + int(effective),
        )

    def increment_authoring_retry(self, job_id: str) -> RootJobState:
        state = self.load_state(job_id)
        return self.update_state(
            job_id,
            authoring_retry_count=state.authoring_retry_count + 1,
        )

    def read_json(self, path: Path | str, default: Any = None) -> Any:
        candidate = Path(path)
        if not candidate.exists():
            return default
        with candidate.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_json(self, path: Path | str, value: Any) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(jsonable(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        with self._lock:
            descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def append_event(self, job_id: str, event_type: str, summary: str, **fields: Any) -> JobEvent:
        path = self.job_dir(job_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            sequence = 1
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    sequence += sum(1 for line in handle if line.strip())
            event = JobEvent(sequence=sequence, event_type=event_type, summary=summary, **fields)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(jsonable(event), sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return event

    def read_events(self, job_id: str) -> list[dict[str, Any]]:
        path = self.job_dir(job_id) / "events.jsonl"
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def write_segments(self, job_id: str, segments: Iterable[Any], input_fingerprint: str) -> None:
        self.write_json(
            self.job_dir(job_id) / "segments.json",
            {"segments": list(segments), "input_fingerprint": input_fingerprint},
        )

    def append_trust_annotation(self, job_id: str, annotation: TrustAnnotation) -> None:
        path = self.job_dir(job_id) / "trust-annotations.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(jsonable(annotation), sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read_trust_annotations(self, job_id: str) -> list[dict[str, Any]]:
        path = self.job_dir(job_id) / "trust-annotations.jsonl"
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def invocation_dir(self, job_id: str, invocation_id: str) -> Path:
        path = self.job_dir(job_id) / "invocations" / invocation_id
        path.mkdir(parents=True, exist_ok=False)
        return path

    def update_usage_summary(self, job_id: str) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        invocation_root = self.job_dir(job_id) / "invocations"
        if invocation_root.exists():
            for path in sorted(invocation_root.glob("*/usage.json")):
                record = self.read_json(path)
                if isinstance(record, dict):
                    records.append(record)
        by_purpose: dict[str, dict[str, int]] = {}
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reported": 0, "unavailable": 0}
        for record in records:
            purpose = str(record.get("purpose") or "unknown")
            bucket = by_purpose.setdefault(
                purpose,
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reported": 0, "unavailable": 0},
            )
            status = str(record.get("usage_status") or "unavailable")
            if status != "reported":
                bucket["unavailable"] += 1
                totals["unavailable"] += 1
                continue
            bucket["reported"] += 1
            totals["reported"] += 1
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                amount = int(record.get(key) or 0)
                bucket[key] += amount
                totals[key] += amount
        summary = {
            "schema_version": "1",
            "job_id": job_id,
            "complete": totals["unavailable"] == 0,
            "totals": totals,
            "by_purpose": by_purpose,
            "updated_at": utc_now(),
        }
        self.write_json(self.job_dir(job_id) / "usage-summary.json", summary)
        return summary

    def materialize_pipeline(self, run_dir: Path, pipeline: Any) -> dict[str, Any]:
        pipeline.validate()
        bundle_dir = run_dir / "pipeline"
        bundle_dir.mkdir(parents=True, exist_ok=False)
        hashes: dict[str, str] = {}
        for item in pipeline.files:
            target = (bundle_dir / item.path).resolve()
            if bundle_dir.resolve() not in target.parents:
                raise ValueError(f"generated path escapes bundle: {item.path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item.content, encoding="utf-8")
            hashes[item.path] = stable_hash(item.content)
        manifest = {
            "schema_version": "1",
            "entry_file": pipeline.entry_file,
            "review_boundaries": pipeline.review_boundaries,
            "file_hashes": hashes,
            "manifest_hash": stable_hash(
                {
                    "entry_file": pipeline.entry_file,
                    "review_boundaries": pipeline.review_boundaries,
                    "file_hashes": hashes,
                }
            ),
        }
        self.write_json(run_dir / "pipeline-manifest.json", manifest)
        return manifest
