"""Parallel-isolated catalogue qualification and deterministic report writing."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rdr.freeze import write_manifest
from rdr.v2_faults import FAULT_SPECS, qualify_faults
from rdr.v2_provenance import verify_code_snapshot


QUALIFICATION_BUILDER_VERSION = "v8-reliability"
IMPLEMENTATION_PATHS = (
    Path("src/rdr/v2_faults.py"),
    Path("src/rdr/v2_live.py"),
    Path("src/rdr/v2_pipeline.py"),
    Path("src/rdr/appworld_adapter.py"),
    Path("src/rdr/v2_qualify.py"),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_reports(source: str, root: Path, author: str, workers: int, ordered: list[dict]) -> None:
    output = root / "qualification.json"
    output.write_text(json.dumps(ordered, indent=2, sort_keys=True))
    lines = ["# V2 real-execution qualification", "", "| Fault | Status | Attempts | Admitted | Inferred | Reason |",
             "|---|---:|---:|---:|---|---|"]
    for record in ordered:
        lines.append(f"| {record['fault_id']} | {record['status']} | {record['attempted']} | "
                     f"{record['admitted']} | {record.get('inferred_classification') or ''} | {record['reason']} |")
    (root / "qualification.md").write_text("\n".join(lines) + "\n")
    summary = {
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "author": author,
        "workers": workers, "parallel_isolation_precondition": "two concurrent clean worlds matched",
        "counts": {status: sum(record["status"] == status for record in ordered)
                   for status in ("qualified", "unqualified", "blocked")},
        "admitted": sum(record["admitted"] for record in ordered),
        "real_cell_attempts": sum(record["attempted"] for record in ordered),
    }
    (root / "qualification_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))


def qualify_catalogue(source: str, root: Path, author: str, workers: int = 4) -> list[dict]:
    if workers < 1:
        raise ValueError("workers must be positive")
    root.mkdir(parents=True, exist_ok=True)
    appworld_ids = list(FAULT_SPECS)
    records = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(qualify_faults, source, root, author, {fault_id}): fault_id
            for fault_id in appworld_ids
        }
        for future in as_completed(futures):
            [record] = future.result()
            records[record["fault_id"]] = record
    ordered = [records[fault_id] for fault_id in FAULT_SPECS]
    _write_reports(source, root, author, workers, ordered)
    return ordered


def write_provenance(root: Path, source_path: Path, records: list[dict], code_provenance: Path,
                     environment_manifest: Path) -> dict:
    code = json.loads((code_provenance / "code_provenance.json").read_text())
    problems = verify_code_snapshot(code_provenance)
    if problems:
        raise ValueError(f"code snapshot verification failed: {problems[:5]}")
    cells = [cell for record in records for name, cell in record.get("cells", {}).items()
             if name != "pair_validation"]
    record = {
        "qualification_builder_version": QUALIFICATION_BUILDER_VERSION,
        "code_snapshot_id": code["snapshot_id"],
        "source_sha256": _sha(source_path),
        "implementation_file_hashes": {path.as_posix(): _sha(path) for path in IMPLEMENTATION_PATHS},
        "environment_manifest": str(environment_manifest),
        "environment_manifest_sha256": _sha(environment_manifest),
        "components": {
            "appworld": {"execution": "rerun", "records": len(records), "cells": len(cells)},
        },
        "counts": {status: sum(item["status"] == status for item in records)
                   for status in ("qualified", "unqualified", "blocked")},
        "admitted_ids": [item["fault_id"] for item in records if item["admitted"]],
        "rows": len(records),
        "cell_evidence": {
            item["fault_id"]: item.get("cells", {}) for item in records
        },
    }
    (root / "qualification_provenance.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--author", choices=("codex", "dataset"), default="codex")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--code-provenance", type=Path)
    parser.add_argument("--environment-manifest", type=Path)
    args = parser.parse_args(argv)
    records = qualify_catalogue(args.source.read_text(), args.root, args.author, args.workers)
    if args.code_provenance or args.environment_manifest:
        if not args.code_provenance or not args.environment_manifest:
            parser.error("current-code provenance requires both --code-provenance and --environment-manifest")
        write_provenance(args.root, args.source, records, args.code_provenance,
                         args.environment_manifest)
    write_manifest(args.root)
    print(json.dumps({"records": len(records), "root": str(args.root)}, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
