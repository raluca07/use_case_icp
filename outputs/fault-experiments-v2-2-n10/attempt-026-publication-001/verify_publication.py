#!/usr/bin/env python3
"""Build or verify the curated Attempt 026 terminal-incomplete publication."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


PUBLICATION_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PUBLICATION_ROOT.parents[2]
ATTEMPT_ROOT = PUBLICATION_ROOT.parent / "attempt-026"
SOURCE_ATTEMPT_ROOT = PUBLICATION_ROOT.parent / "attempt-023"
MANIFEST_PATH = PUBLICATION_ROOT / "publication-manifest.json"
SUMMARY_PATH = PUBLICATION_ROOT / "observed-summary.json"
CSV_PATH = PUBLICATION_ROOT / "initial-review-results.csv"
RESPONSE_INDEX_PATH = PUBLICATION_ROOT / "response-index.json"
CHECKSUMS_PATH = PUBLICATION_ROOT / "checksums.sha256"

PUBLICATION_FILES = {
    "README.md",
    "checksums.sha256",
    "initial-review-results.csv",
    "observed-summary.json",
    "publication-manifest.json",
    "response-index.json",
    "verify_publication.py",
}
SAFE_ATTEMPT_DIRS = (
    "catalogues",
    "controller-manifests",
    "packages",
    "post-live",
    "qualification",
    "repairs",
    "reviews",
    "terminal",
)
TOP_LEVEL_ATTEMPT_FILES = (
    "experiment-freeze.json",
    "live-consumption.json",
    "repair-design.json",
    "review-design.json",
)
SELECTED_INSTANCES = {
    "instance-01": "upstream",
    "instance-04": "upstream",
    "instance-03": "downstream",
    "instance-12": "downstream",
}
FAULTY_INSTANCES = {"instance-03", "instance-04"}
EXPECTED_COUNTS = {
    "catalogues": 4,
    "controller-manifests": 64,
    "packages": 64,
    "post-live": 1,
    "qualification": 2,
    "repairs": 43,
    "reviews": 192,
    "terminal": 2,
    "provider_responses": 278,
    "repaired_pipelines": 210,
    "experiment-freeze.json": 1,
    "live-consumption.json": 1,
    "repair-design.json": 1,
    "review-design.json": 1,
}
SECRET_PATTERNS = {
    "private_key": re.compile(
        rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    ),
    "aws_access_key": re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "google_api_key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "github_token": re.compile(
        rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"
    ),
    "openai_or_anthropic_key": re.compile(
        rb"(?:sk-ant-[A-Za-z0-9_-]{20,}|"
        rb"(?:^|[^A-Za-z0-9_-])sk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{20,})"
    ),
    "slack_token": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "bearer_token": re.compile(rb"Bearer\s+[A-Za-z0-9._~+/-]{20,}"),
    "credentialed_url": re.compile(rb"https?://[^/@\s]+:[^/@\s]+@"),
    "jwt": re.compile(
        rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    "absolute_home_path": re.compile(
        rb"(?:/home/(?!codex(?:/|\b)|runner(?:/|\b))[^/\s]+|"
        rb"/Users/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)",
        re.IGNORECASE,
    ),
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": relative(path), "bytes": len(data), "sha256": sha256_bytes(data)}


def files_below(root: Path) -> Iterable[Path]:
    if root.is_dir():
        yield from (path for path in sorted(root.rglob("*")) if path.is_file())


def is_repaired_pipeline_file(path: Path) -> bool:
    if path.name in {"pipeline-input.json", "pipeline-manifest.json"}:
        return True
    return path.suffix == ".py" and "/pipeline/generated/" in path.as_posix()


def source_attempt_files() -> set[Path]:
    selected = set()
    for instance_id in SELECTED_INSTANCES:
        selected.add(SOURCE_ATTEMPT_ROOT / "instances" / f"{instance_id}.json")
        captures = [
            path
            for path in (SOURCE_ATTEMPT_ROOT / "captures").glob("*.json")
            if load_json(path).get("instance_id") == instance_id
        ]
        if len(captures) != 1:
            raise ValueError(f"expected one source capture for {instance_id}")
        selected.add(captures[0])
        instance_work = SOURCE_ATTEMPT_ROOT / "instance-work" / instance_id
        selected.update(
            path for path in files_below(instance_work) if is_repaired_pipeline_file(path)
        )
    return selected


def repository_files() -> set[Path]:
    selected = {
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "requirements-etiq.txt",
        REPO_ROOT / "schemas/corrected_four_instance_operation.schema.json",
        REPO_ROOT / "schemas/corrected_four_instance_package.schema.json",
    }
    selected.update(
        path
        for path in files_below(REPO_ROOT / "src/use_case_icp")
        if path.suffix == ".py"
    )
    for name in (
        "prompts/v2_2",
        "schemas/v2_2",
        "docs/workshops/neurips-2026-v2-2",
        "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/experiment-v1",
    ):
        selected.update(files_below(REPO_ROOT / name))
    return selected


def completed_record_files() -> list[Path]:
    return sorted(
        [*(ATTEMPT_ROOT / "reviews").glob("*.json"), *(ATTEMPT_ROOT / "repairs").glob("*.json")]
    )


def verify_self_hash(record: dict[str, Any], field: str, path: Path) -> None:
    unsigned = deepcopy(record)
    observed = str(unsigned.pop(field, ""))
    if observed != sha256_bytes(canonical_bytes(unsigned)):
        raise ValueError(f"invalid {field}: {relative(path)}")


def build_response_index() -> dict[str, Any]:
    parent_records = {}
    for record_path in completed_record_files():
        record = load_json(record_path)
        for call in record.get("call_records", []):
            for lineage in call.get("retry_lineage", []):
                parent_records[str(lineage["call_id"])] = relative(record_path)
    attempts = []
    responses = []
    for ledger_path in sorted((ATTEMPT_ROOT / "ledger/call-attempt").glob("*.json")):
        ledger = load_json(ledger_path)
        call_id = str(ledger["record_id"])
        payload = ledger.get("payload", {})
        result = payload.get("result", {})
        if sha256_bytes(canonical_bytes(payload)) != ledger.get("payload_sha256"):
            raise ValueError(f"invalid ledger payload hash: {call_id}")
        status = str(payload.get("status"))
        attempt = {
            "call_id": call_id,
            "status": status,
            "failure_classification": payload.get("failure_classification"),
            "parent_id": payload.get("parent_id"),
            "parent_record_path": parent_records.get(call_id),
            "ledger_record_sha256": sha256_bytes(ledger_path.read_bytes()),
        }
        attempts.append(attempt)
        if status == "completed":
            if result.get("status") != "completed":
                raise ValueError(f"completed call has no completed result: {call_id}")
            response_path = (
                ATTEMPT_ROOT
                / "provider-branches"
                / str(result["branch_id"])
                / "output/response.json"
            )
            response_sha256 = sha256_bytes(response_path.read_bytes())
            if response_sha256 != result.get("response_sha256"):
                raise ValueError(f"response binding changed for {call_id}")
            responses.append({
                "call_id": call_id,
                "response_path": relative(response_path),
                "response_bytes": response_path.stat().st_size,
                "response_sha256": response_sha256,
            })
        elif status != "failed":
            raise ValueError(f"unknown call-attempt status: {call_id}")
    status_counts = Counter(value["status"] for value in attempts)
    if len(attempts) != 279 or status_counts != {"completed": 278, "failed": 1}:
        raise ValueError(f"call-attempt accounting changed: {status_counts!r}")
    return {
        "schema_version": "1",
        "excluded_ledger_note": "Ledger files are excluded; their exact file hashes remain bound here.",
        "call_attempt_count": len(attempts),
        "call_attempt_status_counts": dict(sorted(status_counts.items())),
        "attempts": attempts,
        "response_count": len(responses),
        "responses": responses,
    }


def truth_by_instance() -> dict[str, str | None]:
    result: dict[str, str | None] = {instance_id: None for instance_id in SELECTED_INSTANCES}
    for instance_id in FAULTY_INSTANCES:
        instance = load_json(SOURCE_ATTEMPT_ROOT / "instances" / f"{instance_id}.json")
        mutation = instance["mutation"]
        catalogue = load_json(ATTEMPT_ROOT / "catalogues" / f"{instance_id}.json")
        bindings = catalogue["jobs"][mutation["target_job_id"]]["boundary_bindings"]
        matches = [
            str(value["reviewer_boundary_id"])
            for value in bindings
            if str(value["frozen_realized_identity"]["qualified_function_name"])
            == str(mutation["site"]["qualified_function_name"])
        ]
        if len(matches) != 1:
            raise ValueError(f"cannot resolve localisation truth for {instance_id}")
        result[instance_id] = matches[0]
    return result


def usage_totals(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    calls = [call for record in records for call in record.get("usage", {}).get("calls", [])]
    result: dict[str, Any] = {"logical_call_count": len(calls)}
    for field in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        values = [call.get(field) for call in calls]
        result[field] = (
            sum(values)
            if values and all(isinstance(value, int) and not isinstance(value, bool) for value in values)
            else None
        )
    return result


def build_observed_summary() -> tuple[dict[str, Any], str]:
    reviews = []
    for path in sorted((ATTEMPT_ROOT / "reviews").glob("*.json")):
        record = load_json(path)
        verify_self_hash(record, "review_sha256", path)
        if record.get("status") != "complete":
            raise ValueError(f"incomplete review record: {relative(path)}")
        reviews.append(record)
    repairs = []
    for path in sorted((ATTEMPT_ROOT / "repairs").glob("*.json")):
        record = load_json(path)
        verify_self_hash(record, "repair_sha256", path)
        if record.get("status") != "complete":
            raise ValueError(f"incomplete repair record: {relative(path)}")
        repairs.append(record)
    if len(reviews) != 192 or len(repairs) != 43:
        raise ValueError("Attempt 026 completed-record counts changed")

    truth = truth_by_instance()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    rows = []
    for record in reviews:
        condition = record["controller_trial"]
        instance_id = str(condition["instance_id"])
        faulty = instance_id in FAULTY_INSTANCES
        detected = bool(record["fault_detected"])
        row = {
            **condition,
            "assignment": SELECTED_INSTANCES[instance_id],
            "designation": "fault" if faulty else "control",
            "detected": detected,
            "false_positive": detected and not faulty,
            "exact_boundary_localisation": faulty
            and record.get("selected_suspect_boundary_id") == truth[instance_id],
            "record": record,
        }
        rows.append(row)
        groups[(str(condition["evidence_mode"]), str(condition["source_setting"]))].append(row)

    fieldnames = (
        "condition",
        "source_setting",
        "review_records",
        "detection",
        "localisation",
        "false_positives",
        "review_input_tokens",
        "review_cached_input_tokens",
        "review_output_tokens",
        "review_reasoning_tokens",
        "review_logical_calls",
    )
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    cell_summaries = []
    for (mode, source_setting), values in sorted(groups.items()):
        faulty = [value for value in values if value["designation"] == "fault"]
        controls = [value for value in values if value["designation"] == "control"]
        usage = usage_totals(value["record"] for value in values)
        cell = {
            "condition": mode,
            "source_setting": source_setting,
            "review_records": len(values),
            "detection_numerator": sum(value["detected"] for value in faulty),
            "detection_denominator": len(faulty),
            "localisation_numerator": sum(value["exact_boundary_localisation"] for value in faulty),
            "localisation_denominator": len(faulty),
            "false_positives_numerator": sum(value["false_positive"] for value in controls),
            "false_positives_denominator": len(controls),
            "review_usage": usage,
        }
        cell_summaries.append(cell)
        writer.writerow(
            {
                "condition": mode,
                "source_setting": source_setting,
                "review_records": len(values),
                "detection": f"{cell['detection_numerator']}/{cell['detection_denominator']}",
                "localisation": f"{cell['localisation_numerator']}/{cell['localisation_denominator']}",
                "false_positives": f"{cell['false_positives_numerator']}/{cell['false_positives_denominator']}",
                "review_input_tokens": usage["input_tokens"],
                "review_cached_input_tokens": usage["cached_input_tokens"],
                "review_output_tokens": usage["output_tokens"],
                "review_reasoning_tokens": usage["reasoning_tokens"],
                "review_logical_calls": usage["logical_call_count"],
            }
        )

    terminal_records = [load_json(path) for path in sorted((ATTEMPT_ROOT / "terminal").glob("*.json"))]
    summary = {
        "schema_version": "1",
        "attempt": "attempt-026",
        "status": "terminal_incomplete",
        "sample_size_limitation": "Four instances are descriptive and not population-powered.",
        "analysis_status": "The prespecified complete analysis was not generated because only 43 of 96 repair traces completed.",
        "completed_counts": {
            "frozen_packages": len(list((ATTEMPT_ROOT / "packages").glob("*/*.json"))),
            "initial_reviews": len(reviews),
            "repair_records": len(repairs),
            "planned_repair_records": 96,
            "missing_repair_records": 96 - len(repairs),
        },
        "initial_review_outcomes": {
            "fault_detection": {
                "numerator": sum(value["detected"] for value in rows if value["designation"] == "fault"),
                "denominator": sum(value["designation"] == "fault" for value in rows),
            },
            "control_false_positives": {
                "numerator": sum(value["false_positive"] for value in rows),
                "denominator": sum(value["designation"] == "control" for value in rows),
            },
            "exact_boundary_localisation": {
                "numerator": sum(value["exact_boundary_localisation"] for value in rows),
                "denominator": sum(value["designation"] == "fault" for value in rows),
            },
            "cells": cell_summaries,
        },
        "partial_repair_accounting": {
            "interpretation": "Interrupted prefix only; not a complete repair comparison.",
            "records": len(repairs),
            "attempted": sum(bool(value.get("repair_attempted")) for value in repairs),
            "success_without_regression": sum(bool(value.get("repair_success_without_regression")) for value in repairs),
        },
        "usage": {
            "initial_reviews": usage_totals(reviews),
            "partial_repairs": usage_totals(repairs),
        },
        "terminal_records": terminal_records,
    }
    return summary, stream.getvalue()


def select_publication_files(response_index: dict[str, Any]) -> list[Path]:
    selected = set()
    for name in SAFE_ATTEMPT_DIRS:
        selected.update(files_below(ATTEMPT_ROOT / name))
    selected.update(ATTEMPT_ROOT / name for name in TOP_LEVEL_ATTEMPT_FILES)
    selected.update(
        path
        for path in files_below(ATTEMPT_ROOT / "repair-branches")
        if is_repaired_pipeline_file(path)
    )
    selected.update(REPO_ROOT / record["response_path"] for record in response_index["responses"])
    selected.update(source_attempt_files())
    selected.update(repository_files())
    missing = [relative(path) for path in selected if not path.is_file()]
    if missing:
        raise ValueError(f"selected publication files are missing: {missing!r}")
    return sorted(path.resolve() for path in selected)


def group(path: Path) -> str:
    try:
        parts = path.relative_to(ATTEMPT_ROOT).parts
    except ValueError:
        parts = ()
    if parts:
        if parts[0] == "provider-branches":
            return "provider_responses"
        if parts[0] == "repair-branches":
            return "repaired_pipelines"
        return parts[0]
    try:
        path.relative_to(SOURCE_ATTEMPT_ROOT)
        return "source_attempt"
    except ValueError:
        return "repository_" + path.relative_to(REPO_ROOT).parts[0]


def check_paths(paths: list[Path]) -> None:
    for path in paths:
        rel = relative(path)
        parts = path.parts
        if ".codex" in parts or path.name in {"auth.json", ".git-credentials"}:
            raise ValueError(f"forbidden authentication path: {rel}")
        if path.suffix in {".log", ".pyc"} or "__pycache__" in parts:
            raise ValueError(f"forbidden transient path: {rel}")
        if path.stat().st_size >= 100_000_000:
            raise ValueError(f"file exceeds GitHub's individual-file limit: {rel}")
        try:
            attempt_parts = path.relative_to(ATTEMPT_ROOT).parts
        except ValueError:
            attempt_parts = ()
        if attempt_parts and attempt_parts[0] == "provider-branches":
            if attempt_parts[-2:] != ("output", "response.json"):
                raise ValueError(f"unexpected provider-branch file: {rel}")
        if attempt_parts and attempt_parts[0] == "repair-branches":
            if not is_repaired_pipeline_file(path):
                raise ValueError(f"unexpected repair-branch file: {rel}")


def scan_secrets(paths: list[Path]) -> None:
    matches = []
    for path in paths:
        data = path.read_bytes()
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                matches.append(f"{name}: {relative(path)}")
    if matches:
        raise ValueError("credential or local-path material found:\n" + "\n".join(matches))


def validate_counts(counts: Counter[str]) -> None:
    observed = {name: counts[name] for name in EXPECTED_COUNTS}
    if observed != EXPECTED_COUNTS:
        raise ValueError(f"publication counts changed: {observed!r}")


def raw_inventory() -> dict[str, Any]:
    files = [path for path in ATTEMPT_ROOT.rglob("*") if path.is_file()]
    return {
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "cryptographic_scope": "informational only; excluded raw files are not individually bound",
    }


def write_checksums() -> None:
    names = sorted(PUBLICATION_FILES - {"checksums.sha256"})
    CHECKSUMS_PATH.write_text(
        "".join(
            f"{hashlib.sha256((PUBLICATION_ROOT / name).read_bytes()).hexdigest()}  {name}\n"
            for name in names
        ),
        encoding="utf-8",
    )


def build() -> None:
    response_index = build_response_index()
    summary, csv_text = build_observed_summary()
    RESPONSE_INDEX_PATH.write_text(
        json.dumps(response_index, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    CSV_PATH.write_text(csv_text, encoding="utf-8")
    paths = select_publication_files(response_index)
    check_paths(paths)
    scan_secrets(paths)
    counts = Counter(group(path) for path in paths)
    validate_counts(counts)
    records = [file_record(path) for path in paths]
    manifest = {
        "schema_version": "1",
        "publication_id": "attempt-026-publication-001",
        "source_attempt": "attempt-026",
        "experiment_status": "terminal_incomplete",
        "selection_policy": {
            "included": [
                "frozen package/catalogue records and all completed review and repair records",
                "exact provider responses referenced by completed records",
                "generated repaired pipeline source, input, and manifest files",
                "qualification, correction, freeze, live-consumption, and terminal records",
                "source-attempt dependencies and relevant repository implementation assets",
            ],
            "excluded": [
                "raw provider requests and ledger files",
                "Codex homes, authentication, caches, runtime installations, and logs",
                "provider branch content other than exact response.json files",
                "repair branch content other than generated pipeline source, input, and manifests",
                "unreferenced work directories and transient controller state",
            ],
        },
        "raw_local_attempt_inventory": raw_inventory(),
        "file_count": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "category_counts": dict(sorted(counts.items())),
        "files": records,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_checksums()


def verify_checksums() -> None:
    expected_names = PUBLICATION_FILES - {"checksums.sha256"}
    observed_names = set()
    for line in CHECKSUMS_PATH.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        observed_names.add(name)
        observed = hashlib.sha256((PUBLICATION_ROOT / name).read_bytes()).hexdigest()
        if observed != digest:
            raise ValueError(f"publication metadata checksum mismatch: {name}")
    if observed_names != expected_names:
        raise ValueError("publication metadata checksum names changed")


def verify_response_index(index: dict[str, Any], selected: set[str]) -> None:
    records = index.get("responses")
    if not isinstance(records, list) or len(records) != 278:
        raise ValueError("response index count changed")
    attempts = index.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 279:
        raise ValueError("call-attempt index count changed")
    completed_call_ids = {
        str(call_id)
        for path in completed_record_files()
        for call in load_json(path).get("call_records", [])
        for call_id in call.get("call_ids", [])
    }
    indexed_call_ids = {str(record["call_id"]) for record in attempts}
    if not completed_call_ids <= indexed_call_ids:
        raise ValueError("call-attempt index no longer covers completed records")
    status_counts = Counter(str(record["status"]) for record in attempts)
    if status_counts != {"completed": 278, "failed": 1}:
        raise ValueError("call-attempt status counts changed")
    response_call_ids = {str(record["call_id"]) for record in records}
    indexed_completed = {
        str(record["call_id"]) for record in attempts if record["status"] == "completed"
    }
    if response_call_ids != indexed_completed:
        raise ValueError("response index no longer matches completed call attempts")
    for record in records:
        path = REPO_ROOT / str(record["response_path"])
        if str(record["response_path"]) not in selected:
            raise ValueError(f"response omitted from manifest: {relative(path)}")
        if file_record(path) != {
            "path": str(record["response_path"]),
            "bytes": record["response_bytes"],
            "sha256": record["response_sha256"],
        }:
            raise ValueError(f"response index binding changed: {relative(path)}")


def verify() -> None:
    unexpected = {
        path.name for path in PUBLICATION_ROOT.iterdir() if path.is_file()
    } - PUBLICATION_FILES
    if unexpected:
        raise ValueError(f"unexpected publication metadata files: {sorted(unexpected)!r}")
    verify_checksums()
    manifest = load_json(MANIFEST_PATH)
    if manifest.get("experiment_status") != "terminal_incomplete":
        raise ValueError("Attempt 026 must remain terminal-incomplete")
    records = manifest.get("files")
    if not isinstance(records, list):
        raise ValueError("publication manifest lacks file records")
    paths = []
    seen = set()
    for record in records:
        rel = str(record["path"])
        if rel in seen:
            raise ValueError(f"duplicate publication path: {rel}")
        seen.add(rel)
        path = REPO_ROOT / rel
        if not path.is_file() or file_record(path) != record:
            raise ValueError(f"publication file missing or changed: {rel}")
        paths.append(path.resolve())
    counts = Counter(group(path) for path in paths)
    validate_counts(counts)
    if manifest.get("category_counts") != dict(sorted(counts.items())):
        raise ValueError("publication category counts changed")
    if manifest.get("file_count") != len(paths):
        raise ValueError("publication file count changed")
    if manifest.get("total_bytes") != sum(path.stat().st_size for path in paths):
        raise ValueError("publication byte count changed")
    summary, csv_text = build_observed_summary()
    if load_json(SUMMARY_PATH) != summary or CSV_PATH.read_text(encoding="utf-8") != csv_text:
        raise ValueError("derived Attempt 026 summary changed")
    verify_response_index(load_json(RESPONSE_INDEX_PATH), seen)
    check_paths(paths)
    scan_secrets(paths)
    print(f"PASS: {len(paths)} curated files and every Attempt 026 binding verify exactly")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        build()
    verify()


if __name__ == "__main__":
    main()
