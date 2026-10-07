"""Prespecified N05 reconciliation, analysis, and offline replay."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping

from .n05_runner import (
    canonical_json,
    create_bytes_exclusive,
    create_json_exclusive,
    sha256_bytes,
    stable_id,
)


EVIDENCE_MODES = (
    "current_run",
    "history_full",
    "etiq_full",
    "etiq_selected_fixed",
    "etiq_selected_adaptive",
    "etiq_random_matched",
)
PRIMARY = (
    ("current_run", "source_present"),
    ("history_full", "source_present"),
    ("etiq_full", "source_present"),
    ("etiq_selected_adaptive", "source_present"),
)
ABLATION_IDS = frozenset(
    {"instance-01", "instance-02", "instance-04", "instance-06", "instance-08", "instance-10"}
)
REPAIR_IDS = frozenset(
    {"instance-02", "instance-04", "instance-06", "instance-08", "instance-10"}
)
TRIAL_SEEDS = (104729, 130363, 155921)
CONTROL_IDS = frozenset({"instance-01", "instance-12"})


def expected_design() -> dict[str, Any]:
    branches: list[dict[str, Any]] = []
    conditions: dict[tuple[str, str], str] = {}
    for index, pair in enumerate(
        (mode, source)
        for mode in EVIDENCE_MODES
        for source in ("source_present", "source_absent")
    ):
        conditions[pair] = stable_id("condition", [pair[0], pair[1]], index)
    branch_index = 0
    for instance_number in range(1, 13):
        instance_id = f"instance-{instance_number:02d}"
        configurations = list(PRIMARY)
        if instance_id in ABLATION_IDS:
            configurations.extend(
                pair
                for pair in conditions
                if pair not in PRIMARY
            )
        for mode, source in configurations:
            condition_id = conditions[(mode, source)]
            branch_id = stable_id(
                "branch", [instance_id, condition_id, "frozen-package"], branch_index
            )
            branches.append(
                {
                    "branch_id": branch_id,
                    "instance_id": instance_id,
                    "condition_id": condition_id,
                    "evidence_mode": mode,
                    "source_setting": source,
                    "primary": (mode, source) in PRIMARY,
                    "ablation": instance_id in ABLATION_IDS,
                    "repair": instance_id in REPAIR_IDS,
                    "designation": (
                        "no_injection_control" if instance_id in CONTROL_IDS else "faulty"
                    ),
                    "branch_index": branch_index,
                }
            )
            branch_index += 1
    reviews: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    for branch in branches:
        for trial_index, seed in enumerate(TRIAL_SEEDS):
            trial_id = stable_id(
                "trial",
                [branch["instance_id"], branch["condition_id"], branch["branch_id"]],
                trial_index,
            )
            reviews.append(
                {
                    "trial_id": trial_id,
                    "branch_id": branch["branch_id"],
                    "instance_id": branch["instance_id"],
                    "condition_id": branch["condition_id"],
                    "trial_index": trial_index,
                    "seed": seed,
                }
            )
            if branch["repair"] and branch["ablation"]:
                repairs.append(
                    {
                        "repair_id": stable_id(
                            "repair", [trial_id, branch["branch_id"]], trial_index
                        ),
                        "trial_id": trial_id,
                        "branch_id": branch["branch_id"],
                        "instance_id": branch["instance_id"],
                        "condition_id": branch["condition_id"],
                    }
                )
    result = {
        "schema_version": "1",
        "instances": [f"instance-{index:02d}" for index in range(1, 13)],
        "ablation_instances": sorted(ABLATION_IDS),
        "repair_instances": sorted(REPAIR_IDS),
        "conditions": [
            {"condition_id": condition_id, "evidence_mode": pair[0], "source_setting": pair[1]}
            for pair, condition_id in conditions.items()
        ],
        "branches": branches,
        "review_trials": reviews,
        "repair_traces": repairs,
        "expected_counts": {
            "instances": 12,
            "ablation_instances": 6,
            "repair_instances": 5,
            "branches": 96,
            "primary_branches": 48,
            "additional_ablation_branches": 48,
            "review_trials": 288,
            "repair_traces": 180,
        },
    }
    result["design_sha256"] = sha256_bytes(canonical_json(result))
    return result


def reconcile_records(
    design: Mapping[str, Any],
    review_records: Iterable[Mapping[str, Any]],
    repair_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    reviews = list(review_records)
    repairs = list(repair_records)
    expected_reviews = {item["trial_id"] for item in design["review_trials"]}
    expected_repairs = {item["repair_id"] for item in design["repair_traces"]}
    observed_reviews = [str(item.get("trial_id") or "") for item in reviews]
    observed_repairs = [str(item.get("repair_id") or "") for item in repairs]
    if len(observed_reviews) != len(set(observed_reviews)):
        raise ValueError("N05 reconciliation found duplicate review trials")
    if len(observed_repairs) != len(set(observed_repairs)):
        raise ValueError("N05 reconciliation found duplicate repair traces")
    missing_reviews = sorted(expected_reviews - set(observed_reviews))
    extra_reviews = sorted(set(observed_reviews) - expected_reviews)
    missing_repairs = sorted(expected_repairs - set(observed_repairs))
    extra_repairs = sorted(set(observed_repairs) - expected_repairs)
    invalid_missing = [
        item
        for item in [*reviews, *repairs]
        if item.get("status") == "missing" and not item.get("failure_classification")
    ]
    report = {
        "expected_review_trials": len(expected_reviews),
        "observed_review_trials": len(reviews),
        "expected_repair_traces": len(expected_repairs),
        "observed_repair_traces": len(repairs),
        "missing_review_trial_ids": missing_reviews,
        "extra_review_trial_ids": extra_reviews,
        "missing_repair_ids": missing_repairs,
        "extra_repair_ids": extra_repairs,
        "unclassified_missing_records": len(invalid_missing),
    }
    report["passed"] = not any(
        (
            missing_reviews,
            extra_reviews,
            missing_repairs,
            extra_repairs,
            invalid_missing,
        )
    )
    report["reconciliation_sha256"] = sha256_bytes(canonical_json(report))
    return report


def _numeric_token(record: Mapping[str, Any]) -> int | None:
    value = record.get("input_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _complete_numeric_total(records: Iterable[Mapping[str, Any]], field: str) -> int | None:
    values = [record.get(field) for record in records]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return None
    return sum(values)


def analyze_frozen_results(
    branch_table: Iterable[Mapping[str, Any]],
    review_records: Iterable[Mapping[str, Any]],
    repair_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    branches = {str(item["branch_id"]): dict(item) for item in branch_table}
    reviews = [dict(item) for item in review_records]
    repairs = [dict(item) for item in repair_records]
    repair_by_trial = {str(item["trial_id"]): item for item in repairs}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for review in reviews:
        branch = branches[str(review["branch_id"])]
        review["evidence_mode"] = branch["evidence_mode"]
        review["source_setting"] = branch["source_setting"]
        key = (str(review["instance_id"]), str(review["condition_id"]))
        grouped.setdefault(key, []).append(review)
    instance_rows: list[dict[str, Any]] = []
    for (instance_id, condition_id), trials in sorted(grouped.items()):
        detected = [float(bool(item.get("fault_detected"))) for item in trials]
        localized = [float(bool(item.get("top_suspect_exact"))) for item in trials]
        paired_repairs = [
            repair_by_trial[str(item["trial_id"])]
            for item in trials
            if str(item["trial_id"]) in repair_by_trial
        ]
        repaired = [float(bool(item.get("repair_success"))) for item in paired_repairs]
        tokens = [_numeric_token(item) for item in trials]
        tokens.extend(_numeric_token(item) for item in paired_repairs)
        known_tokens = [value for value in tokens if value is not None]
        branch = branches[str(trials[0]["branch_id"])]
        instance_rows.append(
            {
                "instance_id": instance_id,
                "condition_id": condition_id,
                "evidence_mode": branch["evidence_mode"],
                "source_setting": branch["source_setting"],
                "designation": branch["designation"],
                "fault_detection_mean": mean(detected) if branch["designation"] == "faulty" else None,
                "false_positive_mean": mean(detected) if branch["designation"] == "no_injection_control" else None,
                "fault_localisation_mean": mean(localized) if branch["designation"] == "faulty" else None,
                "repair_success_mean": mean(repaired) if repaired else None,
                "input_tokens": sum(known_tokens) if len(known_tokens) == len(tokens) else None,
                "usage_unavailable_count": len(tokens) - len(known_tokens),
                "detection_trial_sd": pstdev(detected) if branch["designation"] == "faulty" else None,
                "false_positive_trial_sd": pstdev(detected) if branch["designation"] == "no_injection_control" else None,
                "localisation_trial_sd": pstdev(localized) if branch["designation"] == "faulty" else None,
                "repair_trial_sd": pstdev(repaired) if repaired else None,
                "trial_count": len(trials),
            }
        )
    summaries: list[dict[str, Any]] = []
    by_condition: dict[str, list[dict[str, Any]]] = {}
    for row in instance_rows:
        by_condition.setdefault(row["condition_id"], []).append(row)
    for condition_id, rows in sorted(by_condition.items()):
        first = rows[0]
        token_values = [row["input_tokens"] for row in rows]
        successes = [
            row["repair_success_mean"]
            for row in rows
            if row["repair_success_mean"] is not None
        ]
        complete_tokens = all(value is not None for value in token_values)
        token_total = sum(token_values) if complete_tokens else None
        success_total = sum(successes) if successes else 0.0
        detections = [row["fault_detection_mean"] for row in rows if row["fault_detection_mean"] is not None]
        false_positives = [row["false_positive_mean"] for row in rows if row["false_positive_mean"] is not None]
        localisations = [row["fault_localisation_mean"] for row in rows if row["fault_localisation_mean"] is not None]
        summaries.append(
            {
                "condition_id": condition_id,
                "evidence_mode": first["evidence_mode"],
                "source_setting": first["source_setting"],
                "instance_count": len(rows),
                "fault_detection": mean(detections) if detections else None,
                "false_positive_rate": mean(false_positives) if false_positives else None,
                "fault_localisation": mean(localisations) if localisations else None,
                "repair_success": mean(successes) if successes else None,
                "input_tokens": token_total,
                "tokens_per_successful_repair": (
                    token_total / success_total
                    if token_total is not None and success_total > 0
                    else None
                ),
                "successes_per_100k_input_tokens": (
                    success_total * 100_000 / token_total
                    if token_total not in {None, 0}
                    else None
                ),
            }
        )
    row_by_key = {
        (row["instance_id"], row["evidence_mode"], row["source_setting"]): row
        for row in instance_rows
    }
    contrasts = []
    contrast_specs = (
        ("fixed_vs_random_source_present", ("etiq_selected_fixed", "source_present"), ("etiq_random_matched", "source_present")),
        ("adaptive_vs_fixed_source_present", ("etiq_selected_adaptive", "source_present"), ("etiq_selected_fixed", "source_present")),
        ("adaptive_source_present_vs_absent", ("etiq_selected_adaptive", "source_present"), ("etiq_selected_adaptive", "source_absent")),
    )
    for name, left, right in contrast_specs:
        pairs = []
        for instance_id in sorted(ABLATION_IDS):
            left_row = row_by_key[(instance_id, *left)]
            right_row = row_by_key[(instance_id, *right)]
            left_value = left_row["fault_localisation_mean"]
            right_value = right_row["fault_localisation_mean"]
            if left_value is None or right_value is None:
                continue
            pairs.append({"instance_id": instance_id, "left": left_value, "right": right_value})
        contrasts.append(
            {
                "contrast": name,
                "left": {"evidence_mode": left[0], "source_setting": left[1]},
                "right": {"evidence_mode": right[0], "source_setting": right[1]},
                "paired_instance_values": pairs,
                "wins": sum(item["left"] > item["right"] for item in pairs),
                "ties": sum(item["left"] == item["right"] for item in pairs),
                "losses": sum(item["left"] < item["right"] for item in pairs),
            }
        )
    all_outcome_records = [*reviews, *repairs]
    diagnostics = {
        "review_retry_count": sum(max(0, int(item.get("attempt_count", 1)) - 1) for item in reviews),
        "repair_retry_count": sum(max(0, int(item.get("attempt_count", 1)) - 1) for item in repairs),
        "expansion_count": sum(int(item.get("expansion_count") or 0) for item in reviews),
        "citation_count": sum(int(item.get("citation_count") or 0) for item in reviews),
        "latency_seconds": sum(float(item.get("latency_seconds") or 0.0) for item in [*reviews, *repairs]),
        "cached_input_tokens": _complete_numeric_total(all_outcome_records, "cached_input_tokens"),
        "output_tokens": _complete_numeric_total(all_outcome_records, "output_tokens"),
        "reasoning_tokens": _complete_numeric_total(all_outcome_records, "reasoning_tokens"),
    }
    analysis = {
        "schema_version": "1",
        "unit_of_independence": "instance",
        "trial_handling": "average_within_instance_configuration_before_across_instance",
        "instance_rows": instance_rows,
        "condition_summaries": summaries,
        "paired_contrasts": contrasts,
        "diagnostics": diagnostics,
        "setup_usage_included": False,
    }
    analysis["analysis_sha256"] = sha256_bytes(canonical_json(analysis))
    return analysis


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_analysis_outputs(output_root: Path, analysis: Mapping[str, Any]) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "analysis.json"
    create_json_exclusive(json_path, analysis)
    instance_path = output_root / "instance-results.csv"
    condition_path = output_root / "headline-results.csv"
    _write_csv(instance_path, list(analysis["instance_rows"]))
    _write_csv(condition_path, list(analysis["condition_summaries"]))
    plot_path = output_root / "headline-results.svg"
    summaries = list(analysis["condition_summaries"])
    width = 960
    height = 80 + 28 * len(summaries)
    rows = []
    for index, row in enumerate(summaries):
        value = float(row["fault_localisation"])
        y = 48 + index * 28
        bar_width = round(value * 500, 3)
        label = f"{row['evidence_mode']} / {row['source_setting']}"
        rows.append(
            f'<text x="8" y="{y + 14}" font-size="12">{label}</text>'
            f'<rect x="390" y="{y}" width="{bar_width}" height="18" fill="#3569a8"/>'
            f'<text x="{398 + bar_width}" y="{y + 14}" font-size="12">{value:.3f}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        '<text x="8" y="24" font-size="16">Fault localisation by frozen condition</text>'
        + "".join(rows)
        + "</svg>\n"
    )
    create_bytes_exclusive(plot_path, svg.encode())
    return {
        path.name: sha256_bytes(path.read_bytes())
        for path in (json_path, instance_path, condition_path, plot_path)
    }


def build_anonymous_release(
    release_root: Path,
    *,
    public_files: Mapping[str, Path],
) -> dict[str, Any]:
    """Copy an explicit public allowlist and emit deterministic SHA-256 checksums."""
    forbidden = {
        "truth",
        "ground-truth",
        "setup",
        "auth",
        "controller",
        "invocation",
        "source-bundle",
    }
    copied: list[dict[str, str]] = []
    for relative, source in sorted(public_files.items()):
        path = Path(relative)
        normalized = path.as_posix().casefold()
        if path.is_absolute() or ".." in path.parts or any(term in normalized for term in forbidden):
            raise ValueError("N05 anonymous release allowlist contains a restricted path")
        data = Path(source).read_bytes()
        digest = create_bytes_exclusive(release_root / path, data)
        copied.append({"path": path.as_posix(), "sha256": digest})
    checksum_lines = "".join(
        f"{item['sha256'][7:]}  {item['path']}\n" for item in copied
    ).encode()
    checksum_hash = create_bytes_exclusive(release_root / "checksums.sha256", checksum_lines)
    manifest = {
        "schema_version": "1",
        "release_classification": "anonymous_public_results_only",
        "files": copied,
        "checksums_sha256": checksum_hash,
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(manifest))
    create_json_exclusive(release_root / "release-manifest.json", manifest)
    return manifest


def verify_anonymous_release(release_root: Path) -> dict[str, Any]:
    """Verify every published byte and both release checksum bindings."""
    manifest = json.loads((release_root / "release-manifest.json").read_text())
    supplied_manifest_hash = manifest.get("manifest_sha256")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    if supplied_manifest_hash != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("N05 anonymous release manifest checksum mismatch")
    checksum_bytes = (release_root / "checksums.sha256").read_bytes()
    if manifest.get("checksums_sha256") != sha256_bytes(checksum_bytes):
        raise ValueError("N05 anonymous release checksum-file binding mismatch")
    expected_lines = "".join(
        f"{item['sha256'][7:]}  {item['path']}\n"
        for item in manifest.get("files", [])
    ).encode()
    if checksum_bytes != expected_lines:
        raise ValueError("N05 anonymous release checksum listing mismatch")
    verified = []
    for item in manifest.get("files", []):
        path = Path(str(item.get("path") or ""))
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise ValueError("N05 anonymous release contains an unsafe path")
        artifact = release_root / path
        if not artifact.is_file() or sha256_bytes(artifact.read_bytes()) != item.get("sha256"):
            raise ValueError(f"N05 anonymous release artifact checksum mismatch: {path}")
        verified.append(path.as_posix())
    return {
        "passed": True,
        "manifest_sha256": supplied_manifest_hash,
        "checksums_sha256": manifest["checksums_sha256"],
        "verified_files": verified,
    }


def offline_replay(bundle_root: Path) -> dict[str, Any]:
    design = json.loads((bundle_root / "design.json").read_text())
    branches = json.loads((bundle_root / "branches.json").read_text())
    reviews = json.loads((bundle_root / "reviews.json").read_text())
    repairs = json.loads((bundle_root / "repairs.json").read_text())
    reconciliation = reconcile_records(design, reviews, repairs)
    if not reconciliation["passed"]:
        raise ValueError("N05 offline replay reconciliation failed")
    analysis = analyze_frozen_results(branches, reviews, repairs)
    expected = json.loads((bundle_root / "expected-analysis.json").read_text())
    if analysis != expected:
        raise ValueError("N05 offline replay analysis differs from frozen output")
    return {
        "passed": True,
        "reconciliation_sha256": reconciliation["reconciliation_sha256"],
        "analysis_sha256": analysis["analysis_sha256"],
        "primary_instance_count": 12,
        "ablation_instance_count": 6,
    }


def miniature_replay_fixture(output_root: Path) -> dict[str, Any]:
    design = expected_design()
    branches = design["branches"]
    reviews = [
        {
            **item,
            "status": "complete",
            "fault_detected": item["instance_id"] not in {"instance-01", "instance-12"},
            "top_suspect_exact": item["instance_id"] not in {"instance-01", "instance-12"},
            "input_tokens": 1000 + item["trial_index"],
        }
        for item in design["review_trials"]
    ]
    repairs = [
        {
            **item,
            "status": "complete",
            "repair_success": True,
            "input_tokens": 500,
        }
        for item in design["repair_traces"]
    ]
    analysis = analyze_frozen_results(branches, reviews, repairs)
    for name, value in (
        ("design.json", design),
        ("branches.json", branches),
        ("reviews.json", reviews),
        ("repairs.json", repairs),
        ("expected-analysis.json", analysis),
    ):
        create_json_exclusive(output_root / name, value)
    replay = offline_replay(output_root)
    return {"design": design, "analysis": analysis, "replay": replay}
