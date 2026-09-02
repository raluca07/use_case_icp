#!/usr/bin/env python3
"""Create or verify the read-only Attempt 023 preservation record."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable


PRESERVATION_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PRESERVATION_ROOT.parents[2]
ATTEMPT_ROOT = PRESERVATION_ROOT.parent / "attempt-023"
HANDOFF_RELATIVE = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "N13_attempt_023_results_preservation_001_to_overseer.email.md"
)
HANDOFF_PATH = REPO_ROOT / HANDOFF_RELATIVE
EXPECTED_PRESERVATION_FILES = {
    "README.md",
    "checksums.sha256",
    "initial-review-results.csv",
    "preservation-manifest.json",
    "repair-validity.json",
    "token-usage.json",
    "verify_preservation.py",
}
PRIMARY_MODES = (
    "current_run",
    "history_full",
    "etiq_full",
    "etiq_selected_adaptive",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_contract(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.resolve().relative_to(REPO_ROOT).as_posix(),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def tree_contract(
    path: Path,
    include: Callable[[Path], bool] | None = None,
    include_files: bool = True,
) -> dict[str, Any]:
    paths = sorted(
        item
        for item in path.rglob("*")
        if item.is_file() and (include is None or include(item))
    )
    files = [file_contract(item) for item in paths]
    result: dict[str, Any] = {
        "root": path.resolve().relative_to(REPO_ROOT).as_posix(),
        "file_count": len(files),
        "tree_sha256": sha256_bytes(canonical_bytes(files)),
    }
    if include_files:
        result["files"] = files
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def aggregate_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "logical_call_count",
        "provider_attempt_count",
    )
    return {
        **{field: sum(int(record.get(field) or 0) for record in records) for field in fields},
        "record_count": len(records),
        "usage_unavailable_count": sum(bool(record.get("usage_unavailable")) for record in records),
    }


def source_file(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT / "src/use_case_icp")
    return "__pycache__" not in relative.parts and path.suffix != ".pyc"


def load_source_records() -> tuple[
    list[tuple[Path, dict[str, Any]]],
    list[tuple[Path, dict[str, Any]]],
    dict[str, dict[str, Any]],
]:
    reviews = [
        (path, load_json(path)) for path in sorted((ATTEMPT_ROOT / "reviews").glob("*.json"))
    ]
    repairs = [
        (path, load_json(path)) for path in sorted((ATTEMPT_ROOT / "repairs").glob("*.json"))
    ]
    packages = {
        record["branch_id"]: record
        for path in sorted((ATTEMPT_ROOT / "package-records").glob("*.json"))
        for record in [load_json(path)]
    }
    if len(reviews) != 288 or len(repairs) != 180 or len(packages) != 96:
        raise ValueError("Attempt 023 source counts changed")
    return reviews, repairs, packages


def build_initial_results(
    reviews: list[tuple[Path, dict[str, Any]]],
    packages: dict[str, dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    output = io.StringIO()
    fields = [
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
        "review_provider_attempts",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    summaries: list[dict[str, Any]] = []
    for mode in PRIMARY_MODES:
        selected = [
            record
            for _, record in reviews
            if packages[record["branch_id"]]["evidence_mode"] == mode
            and packages[record["branch_id"]]["source_setting"] == "source_present"
        ]
        faulty = [
            record
            for record in selected
            if packages[record["branch_id"]]["designation"] == "faulty"
        ]
        controls = [
            record
            for record in selected
            if packages[record["branch_id"]]["designation"] == "no_injection_control"
        ]
        summary = {
            "condition": mode,
            "source_setting": "source_present",
            "review_records": len(selected),
            "detection_numerator": sum(bool(record["fault_detected"]) for record in faulty),
            "detection_denominator": len(faulty),
            "localisation_numerator": sum(bool(record["top_suspect_exact"]) for record in faulty),
            "localisation_denominator": len(faulty),
            "false_positives_numerator": sum(bool(record["fault_detected"]) for record in controls),
            "false_positives_denominator": len(controls),
            **{
                f"review_{field}": sum(int(record.get(field) or 0) for record in selected)
                for field in (
                    "input_tokens",
                    "cached_input_tokens",
                    "output_tokens",
                    "reasoning_tokens",
                    "provider_attempt_count",
                )
            },
        }
        summaries.append(summary)
        writer.writerow(
            {
                "condition": mode,
                "source_setting": "source_present",
                "review_records": len(selected),
                "detection": f'{summary["detection_numerator"]}/{summary["detection_denominator"]}',
                "localisation": f'{summary["localisation_numerator"]}/{summary["localisation_denominator"]}',
                "false_positives": (
                    f'{summary["false_positives_numerator"]}/'
                    f'{summary["false_positives_denominator"]}'
                ),
                "review_input_tokens": summary["review_input_tokens"],
                "review_cached_input_tokens": summary["review_cached_input_tokens"],
                "review_output_tokens": summary["review_output_tokens"],
                "review_reasoning_tokens": summary["review_reasoning_tokens"],
                "review_provider_attempts": summary["review_provider_attempt_count"],
            }
        )
    expected = [
        ("current_run", 20, 30, 19, 30, 1, 6),
        ("history_full", 24, 30, 24, 30, 1, 6),
        ("etiq_full", 22, 30, 18, 30, 2, 6),
        ("etiq_selected_adaptive", 25, 30, 22, 30, 3, 6),
    ]
    observed = [
        (
            row["condition"],
            row["detection_numerator"],
            row["detection_denominator"],
            row["localisation_numerator"],
            row["localisation_denominator"],
            row["false_positives_numerator"],
            row["false_positives_denominator"],
        )
        for row in summaries
    ]
    if observed != expected:
        raise ValueError(f"primary review results changed: {observed!r}")
    return output.getvalue(), summaries


def response_contract(record_path: Path, record: dict[str, Any]) -> dict[str, Any]:
    result = record["retry_lineage"]["result"]
    response_path = ATTEMPT_ROOT / "provider-branches" / result["branch_id"] / "output/response.json"
    contract = file_contract(response_path)
    if contract["sha256"] != result["response_sha256"]:
        raise ValueError(f"provider response hash mismatch: {record_path}")
    return {
        "repair_id": record["repair_id"],
        "repair_record_path": record_path.relative_to(REPO_ROOT).as_posix(),
        "repair_record_sha256": file_contract(record_path)["sha256"],
        "call_ids": record["call_ids"],
        "request_sha256": record["request_sha256"],
        "response_path": contract["path"],
        "response_sha256": contract["sha256"],
        "response_bytes": contract["bytes"],
        "canonical_response_sha256": sha256_bytes(canonical_bytes(result["response"])),
    }


def build_repair_validity(
    repairs: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    no_call = [(path, record) for path, record in repairs if not record["repair_attempted"]]
    generated = [(path, record) for path, record in repairs if record["repair_attempted"]]
    classifications = Counter(record["failure_classification"] for _, record in repairs)
    if (
        len(no_call) != 57
        or len(generated) != 123
        or classifications
        != Counter(
            {
                "missed_or_wrong_localisation": 57,
                "re_review_failure": 114,
                "rerun_crash_schema_or_oracle_failure": 9,
            }
        )
        or any(record.get("call_records") for _, record in no_call)
        or any(record.get("provider_attempt_count") != 1 for _, record in generated)
        or any(record.get("re_review") is not None for _, record in generated)
    ):
        raise ValueError("repair validity source facts changed")
    responses = [response_contract(path, record) for path, record in generated]
    if len({item["response_sha256"] for item in responses}) != 123:
        raise ValueError("repair response hashes are not unique")
    return {
        "schema_version": "1",
        "source_attempt": "outputs/fault-experiments-v2-2-n10/attempt-023",
        "repair_trial_count": 180,
        "valid_no_repair_endpoint": {
            "count": 57,
            "classification": "missed_or_wrong_localisation",
            "repair_calls": 0,
            "scientific_status": "valid initial-review/localisation endpoint",
        },
        "generated_repair_responses": {
            "count": 123,
            "all_preserved_by_exact_file_hash": True,
            "responses": responses,
        },
        "post_response_outcomes": {
            "count": 123,
            "scientific_status": "invalid_censored",
            "controller_bugs": [
                "dependency-order controller bug",
                "re-review-package controller bug",
            ],
            "observed_controller_failure_classifications": {
                "re_review_failure": 114,
                "rerun_crash_schema_or_oracle_failure": 9,
            },
            "valid_repaired_run_re_reviews": 0,
            "may_be_used_for_repair_success_estimation": False,
        },
        "repair_success_reporting": {
            "headline_value_published": False,
            "legacy_controller_aggregate_scientific_status": "not_a_scientific_result",
            "prohibited_use": "must not be reported or used as a repair-success finding",
        },
        "future_recovery_requirement": (
            "Reuse the frozen 96 packages, 288 initial reviews, and 123 repair "
            "responses by exact hash; do not regenerate them."
        ),
    }


def review_contracts(reviews: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    contracts = []
    for path, record in reviews:
        result = record["retry_lineage"]["result"]
        response_path = ATTEMPT_ROOT / "provider-branches" / result["branch_id"] / "output/response.json"
        response = file_contract(response_path)
        if response["sha256"] != result["response_sha256"]:
            raise ValueError(f"review response hash mismatch: {path}")
        contracts.append(
            {
                "trial_id": record["trial_id"],
                "condition_id": record["condition_id"],
                "instance_id": record["instance_id"],
                "branch_id": record["branch_id"],
                "record": file_contract(path),
                "request_sha256": record["request_sha256"],
                "call_ids": record["call_ids"],
                "response": response,
            }
        )
    if len({item["trial_id"] for item in contracts}) != 288:
        raise ValueError("initial review IDs are not unique")
    return contracts


def package_contracts(packages: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_branch = {
        load_json(path)["branch_id"]: path
        for path in sorted((ATTEMPT_ROOT / "package-records").glob("*.json"))
    }
    contracts = []
    for branch_id, record in sorted(packages.items()):
        package_path = ATTEMPT_ROOT / record["path"]
        contracts.append(
            {
                "branch_id": branch_id,
                "condition_id": record["condition_id"],
                "instance_id": record["instance_id"],
                "record": file_contract(by_branch[branch_id]),
                "declared_package_sha256": record["package_sha256"],
                "verified": record["verified"],
                "package_tree": tree_contract(package_path),
            }
        )
    if len(contracts) != 96 or any(not item["verified"] for item in contracts):
        raise ValueError("package contracts changed")
    return contracts


def build_token_usage(
    reviews: list[tuple[Path, dict[str, Any]]],
    repairs: list[tuple[Path, dict[str, Any]]],
    primary_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    review_records = [record for _, record in reviews]
    generated_repairs = [record for _, record in repairs if record["repair_attempted"]]
    review_usage = aggregate_usage(review_records)
    repair_usage = aggregate_usage(generated_repairs)
    expected_review = {
        "input_tokens": 10295186,
        "cached_input_tokens": 3057664,
        "output_tokens": 420559,
        "reasoning_tokens": 0,
        "logical_call_count": 288,
        "provider_attempt_count": 288,
        "record_count": 288,
        "usage_unavailable_count": 0,
    }
    expected_repair = {
        "input_tokens": 4631682,
        "cached_input_tokens": 1066112,
        "output_tokens": 73978,
        "reasoning_tokens": 0,
        "logical_call_count": 123,
        "provider_attempt_count": 123,
        "record_count": 123,
        "usage_unavailable_count": 0,
    }
    if review_usage != expected_review or repair_usage != expected_repair:
        raise ValueError("review or repair token accounting changed")
    return {
        "schema_version": "1",
        "review_only": review_usage,
        "repair_response_generation_only": repair_usage,
        "repair_post_response_outcomes": "censored; no valid repaired-run re-review usage exists",
        "primary_source_present_review_only_by_condition": primary_summaries,
        "separation_assertion": "review-only usage excludes every repair call",
    }


def build_manifest() -> dict[str, Any]:
    reviews, repairs, packages = load_source_records()
    _, primary_summaries = build_initial_results(reviews, packages)
    repair_validity = build_repair_validity(repairs)
    attempt_tree = tree_contract(ATTEMPT_ROOT, include_files=False)
    return {
        "schema_version": "1",
        "preservation_id": "attempt-023-results-preservation-001",
        "source_attempt": ATTEMPT_ROOT.relative_to(REPO_ROOT).as_posix(),
        "source_attempt_policy": "immutable_read_only",
        "complete_attempt_tree": attempt_tree,
        "experiment_freeze_and_pre_review_state": {
            "experiment_freeze": file_contract(ATTEMPT_ROOT / "experiment-freeze.json"),
            "pre_review_state": file_contract(ATTEMPT_ROOT / "state/pre-review-state.json"),
        },
        "frozen_experimental_material": {
            "instances": tree_contract(ATTEMPT_ROOT / "instances"),
            "captures": tree_contract(ATTEMPT_ROOT / "captures"),
            "package_records": tree_contract(ATTEMPT_ROOT / "package-records"),
            "packages": package_contracts(packages),
            "packages_tree": tree_contract(ATTEMPT_ROOT / "packages"),
        },
        "initial_reviews": {
            "count": 288,
            "records_tree": tree_contract(ATTEMPT_ROOT / "reviews"),
            "records_and_responses": review_contracts(reviews),
        },
        "repair_records": {
            "count": 180,
            "records_tree": tree_contract(ATTEMPT_ROOT / "repairs"),
            "records": [file_contract(path) for path, _ in repairs],
            "generated_response_count": repair_validity["generated_repair_responses"]["count"],
        },
        "closure_terminal_analysis_release": {
            "ledger": tree_contract(ATTEMPT_ROOT / "ledger"),
            "ledger_closure": file_contract(ATTEMPT_ROOT / "ledger-closure.json"),
            "terminal": file_contract(ATTEMPT_ROOT / "terminal.json"),
            "analysis_json": file_contract(ATTEMPT_ROOT / "analysis/analysis.json"),
            "analysis_tree": tree_contract(ATTEMPT_ROOT / "analysis"),
            "anonymous_release_tree": tree_contract(ATTEMPT_ROOT / "anonymous-release"),
            "release_verification": file_contract(ATTEMPT_ROOT / "release-verification.json"),
        },
        "n13_post_freeze_correction": file_contract(
            ATTEMPT_ROOT / "post-freeze-controller-correction.json"
        ),
        "relevant_repository_trees": {
            "source": tree_contract(REPO_ROOT / "src/use_case_icp", include=source_file),
            "prompts_v2_2": tree_contract(REPO_ROOT / "prompts/v2_2"),
            "schemas_v2_2": tree_contract(REPO_ROOT / "schemas/v2_2"),
            "protocol": tree_contract(REPO_ROOT / "docs/workshops/neurips-2026-v2-2"),
            "experiment_fixture": tree_contract(
                REPO_ROOT
                / "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/experiment-v1"
            ),
        },
        "valid_primary_source_present_results": primary_summaries,
        "repair_scientific_status": {
            "valid_no_repair_endpoints": 57,
            "preserved_repair_responses": 123,
            "censored_post_response_outcomes": 123,
            "valid_repaired_run_re_reviews": 0,
            "headline_repair_success_value_published": False,
        },
    }


def readme_text() -> str:
    return """# Attempt 023 results preservation 001

This directory is a read-only preservation index over the unchanged `attempt-023` directory. It contains derived review-only results and exact SHA-256 bindings; it does not contain regenerated experimental evidence.

## Valid findings

The 288 initial review records are valid for fault detection and localisation. `initial-review-results.csv` derives the four primary, source-present condition results directly from those records. Its token columns contain review-only usage. `token-usage.json` keeps all 288 initial-review usage separate from the 123 repair-response calls.

The 57 trials classified as missed or wrong localisation also ended validly at that point. They made no repair call.

## Censored repair material

Exactly 123 repair responses were generated and are preserved by exact response-file hash in `repair-validity.json`. Every outcome after those responses is censored because dependency ordering and re-review package construction were affected by controller bugs. There are zero valid repaired-run re-reviews. The original controller's repair-success aggregate is not a scientific result and must not be reported or used.

## Preservation and recovery

All original Attempt 023 files remain in place and unchanged. `preservation-manifest.json` binds the complete Attempt 023 tree as well as the experiment freeze, pre-review state, 12 instances, 12 captures, 96 packages, 288 reviews, 180 repair records, closure, terminal, analysis, anonymous release, N13 correction, and the relevant repository trees.

Any future recovery must reuse the frozen 96 packages, 288 initial reviews, and 123 repair responses by exact hash. It must not regenerate or replace them.

## Verification

From the repository root, run:

```bash
python3 outputs/fault-experiments-v2-2-n10/attempt-023-results-preservation-001/verify_preservation.py
```

The command exits nonzero for a changed, missing, or unexpected preservation artifact; any changed, missing, or unexpected file in a bound source tree; any source-count or result mismatch; or any changed Attempt 023 file.
"""


def handoff_text(manifest_sha256: str) -> str:
    return f"""From: Developer
To: Overseer
Subject: Attempt 023 results preservation 001 handoff

Authorization boundary: preservation artifacts only; no Attempt 023 mutation, experiment rerun, provider call, or model call occurred.

Preservation directory:
`outputs/fault-experiments-v2-2-n10/attempt-023-results-preservation-001/`

Preservation manifest SHA-256:
`{manifest_sha256}`

Valid initial-review results (source-present primary conditions):

- current_run: detection 20/30; localisation 19/30; false positives 1/6
- history_full: detection 24/30; localisation 24/30; false positives 1/6
- etiq_full: detection 22/30; localisation 18/30; false positives 2/6
- etiq_selected_adaptive: detection 25/30; localisation 22/30; false positives 3/6

Repair validity:

- 57 valid missed/wrong-localisation endpoints with no repair call
- 123 repair responses preserved by exact hash
- 123 post-response outcomes censored
- zero valid repaired-run re-reviews
- no repair-success headline is scientifically reportable

Future recovery must reuse the exact frozen 96 packages, 288 initial reviews, and 123 repair responses bound by the manifest.
"""


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def create_preservation() -> None:
    reviews, repairs, packages = load_source_records()
    csv_text, summaries = build_initial_results(reviews, packages)
    repair_validity = build_repair_validity(repairs)
    token_usage = build_token_usage(reviews, repairs, summaries)
    manifest = build_manifest()
    generated = {
        "README.md": readme_text().encode("utf-8"),
        "initial-review-results.csv": csv_text.encode("utf-8"),
        "preservation-manifest.json": canonical_bytes(manifest) + b"\n",
        "repair-validity.json": canonical_bytes(repair_validity) + b"\n",
        "token-usage.json": canonical_bytes(token_usage) + b"\n",
    }
    for name, data in generated.items():
        write_new(PRESERVATION_ROOT / name, data)
    manifest_sha256 = sha256_bytes(generated["preservation-manifest.json"])
    write_new(HANDOFF_PATH, handoff_text(manifest_sha256).encode("utf-8"))
    checksum_paths = [
        "README.md",
        "initial-review-results.csv",
        "preservation-manifest.json",
        "repair-validity.json",
        "token-usage.json",
        "verify_preservation.py",
        "../../../" + HANDOFF_RELATIVE.as_posix(),
    ]
    lines = []
    for relative in checksum_paths:
        path = (PRESERVATION_ROOT / relative).resolve()
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}\n")
    write_new(PRESERVATION_ROOT / "checksums.sha256", "".join(lines).encode("utf-8"))


def verify_checksums() -> None:
    actual_files = {path.name for path in PRESERVATION_ROOT.iterdir() if path.is_file()}
    if actual_files != EXPECTED_PRESERVATION_FILES:
        raise ValueError(
            f"unexpected or missing preservation files: expected {sorted(EXPECTED_PRESERVATION_FILES)}, "
            f"observed {sorted(actual_files)}"
        )
    expected_paths = {
        "README.md",
        "initial-review-results.csv",
        "preservation-manifest.json",
        "repair-validity.json",
        "token-usage.json",
        "verify_preservation.py",
        "../../../" + HANDOFF_RELATIVE.as_posix(),
    }
    observed_paths = set()
    for line in (PRESERVATION_ROOT / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        observed_paths.add(relative)
        path = (PRESERVATION_ROOT / relative).resolve()
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"checksum mismatch: {relative}")
    if observed_paths != expected_paths:
        raise ValueError("checksums.sha256 has missing or unexpected entries")


def verify_preservation() -> None:
    verify_checksums()
    reviews, repairs, packages = load_source_records()
    expected_csv, summaries = build_initial_results(reviews, packages)
    if (PRESERVATION_ROOT / "initial-review-results.csv").read_text(encoding="utf-8") != expected_csv:
        raise ValueError("initial-review-results.csv is not the direct source-record derivation")
    expected_repair = build_repair_validity(repairs)
    if load_json(PRESERVATION_ROOT / "repair-validity.json") != expected_repair:
        raise ValueError("repair-validity.json does not match source records")
    expected_usage = build_token_usage(reviews, repairs, summaries)
    if load_json(PRESERVATION_ROOT / "token-usage.json") != expected_usage:
        raise ValueError("token-usage.json does not match source records")
    expected_manifest = build_manifest()
    if load_json(PRESERVATION_ROOT / "preservation-manifest.json") != expected_manifest:
        raise ValueError("preservation-manifest.json does not match bound artifacts")
    manifest_sha256 = sha256_bytes((PRESERVATION_ROOT / "preservation-manifest.json").read_bytes())
    if HANDOFF_PATH.read_text(encoding="utf-8") != handoff_text(manifest_sha256):
        raise ValueError("Developer-to-Overseer handoff does not match the manifest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true", help="create the preservation artifacts once")
    args = parser.parse_args()
    if args.create:
        create_preservation()
    verify_preservation()
    print("PASS: Attempt 023 and every preservation binding verify exactly")


if __name__ == "__main__":
    main()
