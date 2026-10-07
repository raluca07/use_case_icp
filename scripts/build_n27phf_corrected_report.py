"""Build the corrected, receipt-backed reporting layer for Attempt 057."""

from __future__ import annotations

import csv
from collections import defaultdict
from hashlib import sha256
import itertools
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = ROOT / "outputs/fault-experiments-v2-2-n10/attempt-057"
REPORT = ROOT / "docs/workshops/ICLR/N27PHF-natural-state-multi-hard-fault-experiment"
SOURCE_ROWS = ATTEMPT / "analysis/all-review-rows.csv"
SOURCE_SUMMARY = ATTEMPT / "analysis/summary.json"

ARMS = {
    "P01": "Source + all-job top-level I/O; no graph or semantics; one call",
    "P02": "P01 + compact native Etiq graph; one call",
    "P03": "P02 + coarse semantic labels; one call",
    "P04": "P02 + required graph expansion and artifact inspection; three calls",
    "P05": "P04 + coarse semantic labels; three calls",
    "P06": "P02 + two no-new-evidence reconsiderations; three calls",
}

MECHANISMS = {
    "R_premature_contribution_rounding": "Premature contribution rounding",
    "S_recorded_time_snapshot_substitution": "Recorded-time snapshot substitution",
    "E_expiry_compared_with_recorded_time": "Expiry compared with recorded time",
    "V_oldest_repeat_retained": "Oldest repeated observation retained",
    "D_repeat_rank_scoped_by_source": "Repeat ranking scoped only by source",
    "C_non_cumulative_channel_cap": "Non-cumulative channel cap (Job 3)",
    "matched_clean_control": "Matched clean control",
}

INSTANCE_ORDER = (
    "case-control-01", "case-control-02", "case-control-03", "case-control-04",
    "case-r01", "case-r02", "case-s01", "case-s02", "case-e01", "case-e02",
    "case-v01", "case-v02", "case-d01", "case-d02", "case-c01", "case-c02",
)

CONFIRMATORY = (
    ("Primary: Adaptive + semantics vs no graph", "P05", "P01"),
    ("Static compact graph vs no graph", "P02", "P01"),
    ("Semantics on static graph", "P03", "P02"),
    ("Adaptive disclosure vs static graph", "P04", "P02"),
    ("Adaptive + semantics vs static + semantics", "P05", "P03"),
    ("Adaptive + semantics vs equal-call reconsideration", "P05", "P06"),
)

EXPLANATORY = (
    ("Adaptive vs equal-call reconsideration, both without semantics", "P04", "P06"),
    ("Semantics on Adaptive", "P05", "P04"),
    ("Equal-call reconsideration vs static graph", "P06", "P02"),
    ("Adaptive + semantics vs static graph", "P05", "P02"),
)

JOB_ALIASES = {
    "job_upstream_demand_provenance": "job_1",
    "job_downstream_coverage_priority": "job_2",
    "job_campaign_portfolio_generation": "job_3",
    "job_campaign_activation_planning": "job_4",
}


def file_sha(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def load_rows() -> list[dict[str, Any]]:
    frozen_summary = json.loads(SOURCE_SUMMARY.read_text())
    natural_state_by_trial = {
        item["trial_id"]: item
        for item in frozen_summary["natural_state_adaptive_selections"]
    }
    with SOURCE_ROWS.open(newline="") as handle:
        source = list(csv.DictReader(handle))
    rows = []
    for item in source:
        review_path = ATTEMPT / "reviews" / f"{item['trial_id']}.json"
        review = json.loads(review_path.read_text())
        truth_path = ATTEMPT / "qualification-private/instances" / f"{item['instance']}.json"
        truth = json.loads(truth_path.read_text())
        detected = as_bool(review["fault_detected"])
        truth_job = truth.get("truth_job")
        expected_job = JOB_ALIASES.get(truth_job)
        correct_job = bool(detected and expected_job and review.get("suspect_job") == expected_job)
        exact = bool(
            correct_job
            and review.get("suspect_function") == truth.get("truth_function")
            and review.get("suspect_function_visible")
        )
        is_control = truth.get("designation") == "matched_clean_control"
        rows.append({
            **item,
            "repetition": int(item["repetition"]),
            "provider_calls": int(item["provider_calls"]),
            "input_tokens": int(item["input_tokens"]),
            "cached_input_tokens": int(item["cached_input_tokens"]),
            "output_tokens": int(item["output_tokens"]),
            "total_tokens": int(item["total_tokens"]),
            "latency_seconds": float(item["latency_seconds"]),
            "recorded_correct_job": as_bool(item["correct_job_attribution"]),
            "recorded_exact": as_bool(item["exact_function_localisation"]),
            "detected": detected,
            "correct_job": False if is_control else correct_job,
            "exact": False if is_control else exact,
            "false_positive": bool(is_control and detected),
            "truth_job": truth_job,
            "truth_job_alias": expected_job,
            "truth_function": truth.get("truth_function"),
            "suspect_job": review.get("suspect_job"),
            "suspect_function": review.get("suspect_function"),
            "suspect_function_visible": bool(review.get("suspect_function_visible")),
            "package_sha256": review["package_sha256"],
            "review_sha256": review["review_sha256"],
            "raw_review_path": str(review_path.relative_to(ROOT)),
            "raw_review_file_sha256": file_sha(review_path),
            "correction_applied": bool(
                correct_job != as_bool(item["correct_job_attribution"])
                or exact != as_bool(item["exact_function_localisation"])
            ),
            "natural_state_selected": bool(
                natural_state_by_trial.get(item["trial_id"], {}).get("selected_prespecified_natural_state", False)
            ),
            "selected_artifact_ref": natural_state_by_trial.get(item["trial_id"], {}).get("selected_artifact_ref"),
        })
    return rows


def grouped(rows: Iterable[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    result: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[tuple(row[key] for key in keys)].append(row)
    return result


def exact_sign_flip(differences: list[float]) -> dict[str, Any]:
    observed = abs(sum(differences) / len(differences))
    distribution = [
        sum(sign * value for sign, value in zip(signs, differences)) / len(differences)
        for signs in itertools.product((-1, 1), repeat=len(differences))
    ]
    p_value = sum(abs(value) >= observed - 1e-15 for value in distribution) / len(distribution)
    wins = sum(value > 1e-15 for value in differences)
    losses = sum(value < -1e-15 for value in differences)
    return {
        "mean_difference": sum(differences) / len(differences),
        "two_sided_p_value": p_value,
        "wins": wins,
        "ties": len(differences) - wins - losses,
        "losses": losses,
        "assignments": len(distribution),
        "per_instance_differences": differences,
    }


def holm_adjust(p_values: list[float]) -> list[float]:
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    total = len(p_values)
    for rank, (index, value) in enumerate(ordered):
        running = max(running, min(1.0, value * (total - rank)))
        adjusted[index] = running
    return adjusted


def instance_means(rows: list[dict[str, Any]], outcome: str, instances: list[str]) -> dict[tuple[str, str], float]:
    cells = grouped(rows, "instance", "cell_id")
    result = {}
    for instance in instances:
        for arm in ARMS:
            values = [float(row[outcome]) for row in cells[(instance, arm)]]
            result[(instance, arm)] = sum(values) / len(values)
    return result


def contrasts(rows: list[dict[str, Any]], definitions: tuple[tuple[str, str, str], ...], outcome: str, instances: list[str]) -> list[dict[str, Any]]:
    means = instance_means(rows, outcome, instances)
    records = []
    for name, left, right in definitions:
        differences = [means[(instance, left)] - means[(instance, right)] for instance in instances]
        test = exact_sign_flip(differences)
        left_hits = sum(int(row[outcome]) for row in rows if row["instance"] in instances and row["cell_id"] == left)
        right_hits = sum(int(row[outcome]) for row in rows if row["instance"] in instances and row["cell_id"] == right)
        records.append({
            "name": name,
            "left": left,
            "right": right,
            "outcome": outcome,
            "instances": len(instances),
            "reviews_per_arm": len(instances) * 3,
            "left_hits": left_hits,
            "right_hits": right_hits,
            **test,
        })
    adjusted = holm_adjust([record["two_sided_p_value"] for record in records])
    for record, value in zip(records, adjusted):
        record["holm_p_value"] = value
        record["significant_raw_0_05"] = record["two_sided_p_value"] < 0.05
        record["significant_holm_0_05"] = value < 0.05
    return records


def fraction(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "—"
    return f"{numerator}/{denominator} ({100 * numerator / denominator:.2f}%)"


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_all_review_rows(rows: list[dict[str, Any]]) -> None:
    fields = [
        "trial_id", "instance", "cell_id", "repetition", "designation", "fault_mechanism",
        "truth_job", "truth_job_alias", "truth_function", "detected", "correct_job", "exact",
        "false_positive", "suspect_job", "suspect_function", "suspect_function_visible",
        "recorded_correct_job", "recorded_exact", "correction_applied", "natural_state_selected",
        "selected_artifact_ref",
        "provider_calls", "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens",
        "latency_seconds", "package_sha256", "review_sha256", "raw_review_file_sha256", "raw_review_path",
    ]
    ordered = sorted(rows, key=lambda row: (INSTANCE_ORDER.index(row["instance"]), row["cell_id"], row["repetition"]))
    write_csv(REPORT / "all-review-results-corrected.csv", fields, ordered)


def cell_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells = grouped(rows, "instance", "cell_id")
    records = []
    for instance in INSTANCE_ORDER:
        for arm in ARMS:
            values = cells[(instance, arm)]
            exemplar = values[0]
            records.append({
                "instance": instance,
                "designation": exemplar["designation"],
                "mechanism": exemplar["fault_mechanism"] or "matched_clean_control",
                "truth_job": exemplar["truth_job"] or "",
                "truth_function": exemplar["truth_function"] or "",
                "arm": arm,
                "detections_of_3": sum(row["detected"] for row in values),
                "correct_job_of_3": "" if exemplar["designation"] == "matched_clean_control" else sum(row["correct_job"] for row in values),
                "exact_of_3": "" if exemplar["designation"] == "matched_clean_control" else sum(row["exact"] for row in values),
                "false_positives_of_3": sum(row["false_positive"] for row in values),
                "natural_state_selected_of_3": sum(row["natural_state_selected"] for row in values),
                "provider_calls": sum(row["provider_calls"] for row in values),
                "input_tokens": sum(row["input_tokens"] for row in values),
                "cached_input_tokens": sum(row["cached_input_tokens"] for row in values),
                "output_tokens": sum(row["output_tokens"] for row in values),
                "total_tokens": sum(row["total_tokens"] for row in values),
                "latency_seconds": sum(row["latency_seconds"] for row in values),
                "trial_ids": ";".join(sorted(row["trial_id"] for row in values)),
                "raw_review_paths": ";".join(sorted(row["raw_review_path"] for row in values)),
            })
    return records


def write_complete_cells(records: list[dict[str, Any]]) -> None:
    fields = list(records[0])
    write_csv(REPORT / "complete-result-cells.csv", fields, records)
    lines = [
        "# Complete 96-cell results", "",
        "One cell is one frozen instance × evidence arm, aggregating its three repeated reviews. "
        "The 288 individual reviews, response fields, tokens, hashes and raw paths are in "
        "[all-review-results-corrected.csv](all-review-results-corrected.csv).", "",
        "`D`, `J`, `E` and `FP` mean detected fault, correct job, exact function and false positive. "
        "Job and exact are not applicable to controls. `Natural` counts reviews that selected the "
        "prespecified natural state. All Job-3 cells use the deterministic correction documented in "
        "[scoring-correction.md](scoring-correction.md).", "",
        "| Instance | Mechanism | Truth | Arm | D/3 | J/3 | E/3 | FP/3 | Natural/3 | Calls | Tokens |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        mechanism = MECHANISMS[record["mechanism"]]
        truth = "Control" if not record["truth_job"] else f"{record['truth_job']} / {record['truth_function']}"
        correct = "—" if record["correct_job_of_3"] == "" else str(record["correct_job_of_3"])
        exact = "—" if record["exact_of_3"] == "" else str(record["exact_of_3"])
        lines.append(
            f"| {record['instance']} | {mechanism} | {truth} | {record['arm']} | "
            f"{record['detections_of_3']} | {correct} | {exact} | {record['false_positives_of_3']} | "
            f"{record['natural_state_selected_of_3']} | {record['provider_calls']} | {record['total_tokens']:,} |"
        )
    (REPORT / "complete-result-cells.md").write_text("\n".join(lines) + "\n")


def arm_and_mechanism_tables(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    faults = [row for row in rows if row["designation"] != "matched_clean_control"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    lines = [
        "# Corrected aggregate and mechanism tables", "",
        "The original frozen analysis mis-scored all Job-3 channel-cap reviews. The tables below "
        "recompute correct-job and exact-function outcomes from the preserved responses and the "
        "private instance truth. Detection, false positives, calls and tokens are unchanged. See "
        "[the correction note](scoring-correction.md).", "",
        "## Arm-level results", "",
        "| Arm | Treatment | Detection | Correct job | Exact function | Control FP | Calls | Total tokens |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    arm_summary = {}
    for arm, description in ARMS.items():
        fault_rows = [row for row in faults if row["cell_id"] == arm]
        control_rows = [row for row in controls if row["cell_id"] == arm]
        all_rows = fault_rows + control_rows
        record = {
            "detection": sum(row["detected"] for row in fault_rows),
            "correct_job": sum(row["correct_job"] for row in fault_rows),
            "exact": sum(row["exact"] for row in fault_rows),
            "false_positive": sum(row["false_positive"] for row in control_rows),
            "provider_calls": sum(row["provider_calls"] for row in all_rows),
            "input_tokens": sum(row["input_tokens"] for row in all_rows),
            "cached_input_tokens": sum(row["cached_input_tokens"] for row in all_rows),
            "output_tokens": sum(row["output_tokens"] for row in all_rows),
            "total_tokens": sum(row["total_tokens"] for row in all_rows),
            "latency_seconds": sum(row["latency_seconds"] for row in all_rows),
        }
        arm_summary[arm] = record
        lines.append(
            f"| {arm} | {description} | {fraction(record['detection'], 36)} | "
            f"{fraction(record['correct_job'], 36)} | {fraction(record['exact'], 36)} | "
            f"{fraction(record['false_positive'], 12)} | {record['provider_calls']} | {record['total_tokens']:,} |"
        )

    lines += [
        "", "## Results by faulted job", "",
        "The Job-3 row incorporates the deterministic truth-binding correction.", "",
        "| Faulted job | Outcome | P01 | P02 | P03 | P04 | P05 | P06 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    job_splits = (
        ("Job 1", {"job_upstream_demand_provenance"}, 30),
        ("Job 3", {"job_campaign_portfolio_generation"}, 6),
    )
    for label, truth_jobs, denominator in job_splits:
        for outcome, outcome_label in (("detected", "Detection"), ("correct_job", "Correct job"), ("exact", "Exact function")):
            values = []
            for arm in ARMS:
                subset = [row for row in faults if row["truth_job"] in truth_jobs and row["cell_id"] == arm]
                values.append(f"{sum(row[outcome] for row in subset)}/{denominator}")
            lines.append(f"| {label} | {outcome_label} | " + " | ".join(values) + " |")

    lines += [
        "", "## Exact localisation by fault mechanism", "",
        "Each mechanism has two independent instances and three repeated reviews per instance.", "",
        "| Mechanism | P01 | P02 | P03 | P04 | P05 | P06 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mechanism in MECHANISMS:
        if mechanism == "matched_clean_control":
            continue
        values = []
        for arm in ARMS:
            cell = [row for row in faults if row["fault_mechanism"] == mechanism and row["cell_id"] == arm]
            values.append(f"{sum(row['exact'] for row in cell)}/6")
        lines.append(f"| {MECHANISMS[mechanism]} | " + " | ".join(values) + " |")

    lines += [
        "", "## Control false positives", "",
        "| Arm | P01 | P02 | P03 | P04 | P05 | P06 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| False positives | " + " | ".join(
            f"{sum(row['false_positive'] for row in controls if row['cell_id'] == arm)}/12" for arm in ARMS
        ) + " |",
        "", "## Completeness", "",
        "- [All 96 instance × arm result cells](complete-result-cells.md)",
        "- [Machine-readable 96-cell table](complete-result-cells.csv)",
        "- [All 288 corrected individual review rows](all-review-results-corrected.csv)",
        "- [Detailed significance table](significance-table.md)",
    ]
    return "\n".join(lines) + "\n", arm_summary


def significance_tables(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    fault_instances = [instance for instance in INSTANCE_ORDER if "control" not in instance]
    control_instances = [instance for instance in INSTANCE_ORDER if "control" in instance]
    confirmatory = []
    for outcome in ("detected", "correct_job", "exact"):
        confirmatory.extend(contrasts(rows, CONFIRMATORY, outcome, fault_instances))
    confirmatory.extend(contrasts(rows, CONFIRMATORY, "false_positive", control_instances))
    explanatory = contrasts(rows, EXPLANATORY, "exact", fault_instances)

    mechanism_records = []
    for mechanism in MECHANISMS:
        if mechanism == "matched_clean_control":
            continue
        instances = sorted({row["instance"] for row in rows if row["fault_mechanism"] == mechanism})
        records = contrasts(rows, CONFIRMATORY, "exact", instances)
        for record in records:
            record["mechanism"] = mechanism
        mechanism_records.extend(records)

    lines = [
        "# Detailed significance tables", "",
        "## Method", "",
        "The independent unit is the frozen data instance, not the model repetition. Each instance's "
        "three binary review results are averaged, and each arm contrast uses a two-sided exact paired "
        "sign-flip randomization test. `W/T/L` counts instances on which the left arm won, tied or lost. "
        "`Holm p` adjusts the six confirmatory comparisons within each outcome. Significance is "
        "two-sided `Holm p < 0.05`. Mechanism-level tests have only two independent instances and are "
        "therefore severely underpowered; their raw p-values are supplied for transparency and Holm "
        "adjusted within each mechanism. These are tests of arm differences, not tests that an arm's "
        "accuracy differs from zero.", "",
        "## Confirmatory arm contrasts", "",
        "| Outcome | Contrast (left − right) | Left | Right | Difference | W/T/L | Raw p | Holm p | Significant? |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    outcome_labels = {
        "detected": "Detection", "correct_job": "Correct job", "exact": "Exact function",
        "false_positive": "Control FP",
    }
    for record in confirmatory:
        denominator = record["reviews_per_arm"]
        lines.append(
            f"| {outcome_labels[record['outcome']]} | {record['name']} ({record['left']}−{record['right']}) | "
            f"{record['left_hits']}/{denominator} | {record['right_hits']}/{denominator} | "
            f"{100 * record['mean_difference']:+.2f} pp | {record['wins']}/{record['ties']}/{record['losses']} | "
            f"{record['two_sided_p_value']:.3f} | {record['holm_p_value']:.3f} | "
            f"{'Yes' if record['significant_holm_0_05'] else 'No'} |"
        )

    lines += [
        "", "## Explanatory exact-localisation contrasts", "",
        "These were added to explain the observed pattern and are not substitutes for the confirmatory comparisons.", "",
        "| Contrast (left − right) | Left | Right | Difference | W/T/L | Raw p | Holm p | Significant? |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for record in explanatory:
        lines.append(
            f"| {record['name']} ({record['left']}−{record['right']}) | {record['left_hits']}/36 | "
            f"{record['right_hits']}/36 | {100 * record['mean_difference']:+.2f} pp | "
            f"{record['wins']}/{record['ties']}/{record['losses']} | {record['two_sided_p_value']:.3f} | "
            f"{record['holm_p_value']:.3f} | {'Yes' if record['significant_holm_0_05'] else 'No'} |"
        )

    lines += [
        "", "## Exact localisation by mechanism", "",
        "Each row compares only two independent instances (six repeated reviews per arm). No result in this table is significant.", "",
        "| Mechanism | Contrast | Left | Right | Difference | W/T/L | Raw p | Holm p | Significant? |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for mechanism in MECHANISMS:
        if mechanism == "matched_clean_control":
            continue
        for record in (item for item in mechanism_records if item["mechanism"] == mechanism):
            lines.append(
                f"| {MECHANISMS[mechanism]} | {record['left']}−{record['right']} | "
                f"{record['left_hits']}/6 | {record['right_hits']}/6 | {100 * record['mean_difference']:+.2f} pp | "
                f"{record['wins']}/{record['ties']}/{record['losses']} | {record['two_sided_p_value']:.3f} | "
                f"{record['holm_p_value']:.3f} | {'Yes' if record['significant_holm_0_05'] else 'No'} |"
            )

    lines += [
        "", "## Interpretation", "",
        "No confirmatory, explanatory or mechanism-level contrast reaches the prespecified two-sided "
        "0.05 threshold. The observed graph gains are therefore descriptive estimates from this small "
        "experiment, not statistically established effects. Zero false positives in all arms means there "
        "is no observed specificity trade-off, but it also leaves no between-arm false-positive difference to test.",
    ]
    payload = {
        "schema_version": "n27phf-corrected-significance-1",
        "method": "two-sided exact paired sign-flip after averaging three repetitions within instance",
        "alpha": 0.05,
        "multiplicity": "Holm adjustment across six confirmatory comparisons within outcome; separately within mechanism",
        "confirmatory": confirmatory,
        "explanatory": explanatory,
        "by_mechanism": mechanism_records,
    }
    write_csv(
        REPORT / "significance-table.csv",
        [
            "mechanism", "outcome", "name", "left", "right", "instances", "reviews_per_arm", "left_hits",
            "right_hits", "mean_difference", "wins", "ties", "losses", "two_sided_p_value",
            "holm_p_value", "significant_raw_0_05", "significant_holm_0_05",
        ],
        confirmatory + explanatory + mechanism_records,
    )
    return "\n".join(lines) + "\n", payload


def scoring_note(rows: list[dict[str, Any]]) -> str:
    corrected = [row for row in rows if row["correction_applied"]]
    by_arm = {arm: sum(row["correction_applied"] for row in corrected if row["cell_id"] == arm) for arm in ARMS}
    return f"""# Attempt 057 Job-3 scoring correction

## What was wrong

Attempt 057 contains two Job-3 channel-cap fault instances (`case-c01` and
`case-c02`). Their private truth records identify
`job_campaign_portfolio_generation / allocate_campaign_budget`, which is
reviewer-facing `job_3 / allocate_campaign_budget`. All 36 associated model
responses detected the fault and returned that exact job and function.

The inherited scorer nevertheless compared every faulty response with the
literal `job_1` and wrote `truth_job: job_1`. This is visible in
[`n27phb_experiment.py`](../../../../src/use_case_icp/n27phb_experiment.py),
while a representative private truth record is
[`case-c01.json`](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/qualification-private/instances/case-c01.json)
and a representative raw review is
[`trial-3ad7ba2881c8a417.json`](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/reviews/trial-3ad7ba2881c8a417.json).

## Deterministic correction

The reporting correction reads each frozen private instance truth and each
frozen review response, maps the canonical job IDs to the reviewer-facing
`job_1`–`job_4` aliases, and recomputes correct-job and exact-function scores.
It makes no model call and changes no package, response, capture or frozen
Attempt 057 file.

- Corrected review rows: {len(corrected)}/288, all from the two Job-3 faults.
- Corrections per arm: {', '.join(f'{arm}={count}' for arm, count in by_arm.items())}.
- Correct-job attribution: 152/216 → 188/216.
- Exact-function localisation: 152/216 → 188/216.
- Detection remains 188/216; control false positives remain 0/72.
- Every arm gains exactly 6/36 correct-job and exact-function outcomes, so all
  paired between-arm differences and p-values remain unchanged.

## Preservation and audit trail

- Frozen source table SHA-256: `{file_sha(SOURCE_ROWS)}`
- Frozen source summary SHA-256: `{file_sha(SOURCE_SUMMARY)}`
- [Corrected 288-review ledger](all-review-results-corrected.csv)
- [Corrected 96-cell table](complete-result-cells.md)
- [Correction manifest](corrected-rescore.json)

The original frozen [`summary.json`](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/analysis/summary.json)
is preserved as the historical controller output and must not be quoted for
absolute correct-job or exact-function totals without this correction.
"""


def findings(arm_summary: dict[str, Any]) -> str:
    return f"""# Attempt 057 corrected findings

Attempt 057 tested six evidence treatments on 12 faulty instances and four
matched clean controls. Every arm received the complete source of all four
jobs, all four jobs' top-level inputs and parsed outputs, and only Job 4's
stdout/stderr. The graph arms added native Etiq execution structure; Adaptive
arms could disclose nested execution state.

The frozen controller analysis contains a Job-3 truth-binding error. This
report applies the deterministic reporting correction documented in
[scoring-correction.md](scoring-correction.md). No experiment artifact or model
response was changed.

## Corrected headline results

- Fault detection: **188/216 (87.04%)**.
- Correct-job attribution: **188/216 (87.04%)**, not the frozen report's 152/216.
- Exact-function localisation: **188/216 (87.04%)**, not 152/216.
- Clean-control false positives: **0/72**.
- Scientific calls: **576**; repairs and calibration calls: **0**.

## Findings

1. **The compact graph produced a small descriptive gain over source and
   top-level I/O alone.** P02 exactly localised 33/36 faults versus 30/36 for
   P01. All three additional successes were premature-rounding reviews. The
   paired test was not significant (difference +8.33 percentage points,
   two-sided p=0.500; Holm p=1.000). [Arm and mechanism results](cell-table.md)
   · [significance](significance-table.md#confirmatory-arm-contrasts)

2. **Adaptive disclosure did not improve on the static compact graph in the
   matched no-semantics comparison.** P04 and P02 both finished at 33/36 exact;
   P04 won one instance and lost one (p=1.000). Thus this run does not establish
   an incremental accuracy benefit from nested disclosure. [Cell results](cell-table.md#arm-level-results)
   · [significance](significance-table.md#confirmatory-arm-contrasts)

3. **Only premature rounding remained genuinely difficult.** Across all arms,
   rounding was localised 10/36 times. P01 scored 0/6, P02 3/6, P03 0/6, P04
   3/6, P05 4/6 and P06 0/6. The other five mechanisms were at ceiling except
   for two P06 misses on oldest-repeat retention. [Mechanism table](cell-table.md#exact-localisation-by-fault-mechanism)
   · [all 96 cells](complete-result-cells.md)

4. **The semantic labels showed no reliable benefit.** On the static graph,
   adding labels reduced exact localisation from 33/36 (P02) to 30/36 (P03).
   On Adaptive, labels increased it from 33/36 (P04) to 34/36 (P05). Neither
   contrast was significant. [Arm table](cell-table.md#arm-level-results) ·
   [confirmatory tests](significance-table.md#confirmatory-arm-contrasts)

5. **Extra calls alone did not explain the best observed score.** P06 received
   the same compact graph as P02 and two additional reconsideration calls but
   no new evidence; it fell from 33/36 to 28/36. P05 scored 34/36 versus P06's
   28/36, but that contrast combines disclosure and semantics and remained
   non-significant after correction (raw p=0.125; Holm p=0.750). [Arm table](cell-table.md#arm-level-results)
   · [significance](significance-table.md#confirmatory-arm-contrasts)

6. **The experiment did not demonstrate that selecting the designated hidden
   natural state caused success.** In the 24 eligible Adaptive reviews for the
   repeat-order and cross-opportunity mechanisms, the model selected
   `ordered_df` or `decision_rank` in 19. It was exact in all 19 selected and
   all five non-selected reviews; P01 already scored 12/12 on those mechanisms.
   [Per-cell selections](complete-result-cells.md) ·
   [frozen selection record](natural-state-selections.json)

7. **All arms avoided false positives on the clean controls.** Each arm scored
   0/12, giving 0/72 overall. This supports specificity in these four controls,
   but it cannot distinguish the arms statistically. [Control table](cell-table.md#control-false-positives)
   · [false-positive tests](significance-table.md#confirmatory-arm-contrasts)

8. **Interactive review was much more expensive without a demonstrated
   accuracy gain over static graph evidence.** P02 used {arm_summary['P02']['total_tokens']:,}
   input-plus-output tokens and 48 calls. P04 used {arm_summary['P04']['total_tokens']:,}
   tokens and 144 calls for the same 33/36 exact result; P05 used
   {arm_summary['P05']['total_tokens']:,} tokens and 144 calls for 34/36.
   [Arm-level token totals](cell-table.md#arm-level-results) ·
   [per-call accounting](per-call-token-latency.json)

## Statistical conclusion

No prespecified arm contrast was significant at two-sided 0.05, either before
or after Holm correction. The graph differences above must therefore be
reported as descriptive estimates from 12 independent faulty instances, not as
established effects. The three model repetitions per instance are repeated
measurements, not additional independent fault cases. [Full significance table](significance-table.md)

## Complete audit trail

- [Corrected aggregate and mechanism tables](cell-table.md)
- [Every one of the 96 instance × arm cells](complete-result-cells.md)
- [Every one of the 288 individual review results](all-review-results-corrected.csv)
- [Detailed significance tables](significance-table.md)
- [Scoring correction and frozen hashes](scoring-correction.md)
- [Frozen analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/analysis/summary.json)
- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/experiment-freeze.json)
- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/replay.json)
- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/terminal-state.json)
"""


def paper_writer_handover() -> str:
    return """# Paper Writer handover — Attempt 057 corrected results

Use this handover for the ICLR paper's Attempt 057 results. Do not quote the
frozen controller's 152/216 correct-job or exact-localisation totals: those
totals contain the documented Job-3 scorer error. Use the corrected reporting
layer linked below. Attempt 057's packages, receipts and frozen outputs remain
unchanged.

## Treatment definitions

Common to every arm: complete actual source for Jobs 1–4; actual top-level
inputs and parsed outputs for Jobs 1–4; Job-4 stdout/stderr only; the same
pipeline topology, marketing objective, review task and response contract.
Jobs 1–3 supplied no logs. The differences below are additions to that common
evidence.

- **P01:** complete source and top-level I/O for all four jobs, without graph or
  semantic labels.
- **P02:** P01 plus a compact native Etiq graph.
- **P03:** P02 plus coarse function-purpose semantics.
- **P04:** P02 plus required nested expansion and artifact inspection.
- **P05:** P04 plus coarse function-purpose semantics.
- **P06:** P02 plus two reconsideration calls that reveal no new evidence.

Reference: [arm table with full treatment text](cell-table.md#arm-level-results).

Representative frozen packages for the same `case-r01` instance:
[P01](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-4e61a93b3929e9c3/reviewer-package.json),
[P02](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-6469f8990209e542/reviewer-package.json),
[P03](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-f481d67028e2ec4b/reviewer-package.json),
[P04](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-45ccb4c59b9e4491/reviewer-package.json),
[P05](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-66de7ba695ecb0d8/reviewer-package.json), and
[P06](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-2d7ac66eb9cf24d6/reviewer-package.json).

## Claims that may be made

1. **Corrected overall performance was 188/216 for detection, correct-job
   attribution and exact-function localisation, with 0/72 clean-control false
   positives.** The equality of the three fault outcomes follows from the fact
   that every detected fault was also assigned to the correct job and exact
   function after the Job-3 correction. References: [correction evidence](scoring-correction.md)
   and [arm totals](cell-table.md#arm-level-results).

2. **The static compact graph had a small descriptive advantage over the
   no-graph arm:** P02 33/36 versus P01 30/36 exact. The gain was confined to
   the rounding mechanism and was not statistically significant (paired
   p=0.500; Holm p=1.000). References: [mechanism table](cell-table.md#exact-localisation-by-fault-mechanism)
   and [confirmatory significance row](significance-table.md#confirmatory-arm-contrasts).

3. **Required Adaptive disclosure did not improve on static compact graph
   evidence when semantics were held absent:** P04 and P02 were both 33/36,
   paired p=1.000. Reference: [confirmatory significance table](significance-table.md#confirmatory-arm-contrasts).

4. **Premature contribution rounding was the only consistently hard fault:**
   10/36 exact across arms, including P01 0/6 and a best arm result of P05 4/6.
   Five other mechanisms were at or near ceiling. References: [mechanism table](cell-table.md#exact-localisation-by-fault-mechanism)
   and [all instance cells](complete-result-cells.md).

5. **Semantic labels had no demonstrated benefit:** P03 was 30/36 versus P02
   33/36; P05 was 34/36 versus P04 33/36. Neither paired comparison was
   significant. References: [arm totals](cell-table.md#arm-level-results) and
   [significance table](significance-table.md#confirmatory-arm-contrasts).

6. **Additional calls without new evidence did not reproduce the best score:**
   P06 was 28/36 versus P02 33/36 and P05 34/36. The P05–P06 comparison was
   descriptive rather than significant (raw p=0.125; Holm p=0.750), and it is
   not a pure disclosure contrast because P05 also contains semantics.
   References: [arm totals](cell-table.md#arm-level-results), [confirmatory tests](significance-table.md#confirmatory-arm-contrasts)
   and [explanatory tests](significance-table.md#explanatory-exact-localisation-contrasts).

7. **Selection of the designated natural state was not shown to cause the
   result.** It occurred in 19/24 eligible Adaptive repeat-order/dedup reviews,
   but exact localisation was 19/19 when selected and 5/5 when not selected;
   the no-graph arm already scored 12/12 on those mechanisms. References:
   [complete cells](complete-result-cells.md) and [frozen selection details](natural-state-selections.json).

8. **Interactive evidence was substantially more expensive.** P02 used
   2,904,514 total tokens and 48 calls; P04 used 9,150,328 and 144 calls for the
   same 33/36 score; P05 used 9,218,638 and 144 calls for 34/36. References:
   [arm table](cell-table.md#arm-level-results) and [per-call accounting](per-call-token-latency.json).

9. **None of the prespecified between-arm effects was statistically
   significant.** Use descriptive language such as “observed,” “in this
   experiment,” and “did not establish”; do not write that graph or Adaptive
   evidence was proven superior. Reference: [complete significance report](significance-table.md).

## Required validity language

- The independent sample is 12 faulty instances plus four clean controls; the
  three model repetitions are repeated measurements.
- Mechanism-specific results have only two independent instances each and are
  underpowered. [Mechanism-level significance](significance-table.md#exact-localisation-by-mechanism)
- All arms received the same complete four-job source and top-level I/O. The
  experiment estimates what graph organization and interaction add on top of
  that common evidence; it is not a source-versus-graph test.
- The Job-3 scorer defect affected absolute correct-job and exact totals but not
  detection, false positives or any between-arm difference, because every arm
  gained six corrected Job-3 successes. [Correction note](scoring-correction.md)
- Do not pool Attempt 056. It remains a preserved partial run.

## Tables and raw references

- [Short corrected findings](findings.md)
- [Corrected aggregate and mechanism tables](cell-table.md)
- [All 96 result cells](complete-result-cells.md)
- [All 288 review rows with raw receipt paths and hashes](all-review-results-corrected.csv)
- [Significance table, including mechanism splits](significance-table.md)
- [Machine-readable correction manifest](corrected-rescore.json)
"""


def main() -> None:
    REPORT.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    if len(rows) != 288:
        raise ValueError(f"expected 288 reviews, found {len(rows)}")
    if sum(row["correction_applied"] for row in rows) != 36:
        raise ValueError("expected exactly 36 Job-3 scoring corrections")
    if any(not row["detected"] or not row["correct_job"] or not row["exact"] for row in rows if row["fault_mechanism"] == "C_non_cumulative_channel_cap"):
        raise ValueError("a Job-3 channel-cap receipt does not match its frozen truth")

    write_all_review_rows(rows)
    cells = cell_records(rows)
    if len(cells) != 96:
        raise ValueError(f"expected 96 result cells, found {len(cells)}")
    write_complete_cells(cells)
    table_text, arm_summary = arm_and_mechanism_tables(rows)
    (REPORT / "cell-table.md").write_text(table_text)
    significance_text, significance = significance_tables(rows)
    (REPORT / "significance-table.md").write_text(significance_text)
    (REPORT / "scoring-correction.md").write_text(scoring_note(rows))
    (REPORT / "findings.md").write_text(findings(arm_summary))
    (REPORT / "paper-writer-handover.md").write_text(paper_writer_handover())

    faults = [row for row in rows if row["designation"] != "matched_clean_control"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    manifest = {
        "schema_version": "n27phf-corrected-reporting-1",
        "attempt": "057",
        "preservation": "No frozen Attempt 057 artifact was modified.",
        "source_hashes": {
            "analysis/all-review-rows.csv": file_sha(SOURCE_ROWS),
            "analysis/summary.json": file_sha(SOURCE_SUMMARY),
            "experiment-freeze.json": file_sha(ATTEMPT / "experiment-freeze.json"),
            "replay.json": file_sha(ATTEMPT / "replay.json"),
            "terminal-state.json": file_sha(ATTEMPT / "terminal-state.json"),
        },
        "counts": {
            "reviews": len(rows), "result_cells": len(cells), "fault_reviews": len(faults),
            "control_reviews": len(controls), "corrected_job3_reviews": sum(row["correction_applied"] for row in rows),
        },
        "original_scores": {"detection": 188, "correct_job": 152, "exact": 152, "false_positive": 0},
        "corrected_scores": {
            "detection": sum(row["detected"] for row in faults),
            "correct_job": sum(row["correct_job"] for row in faults),
            "exact": sum(row["exact"] for row in faults),
            "false_positive": sum(row["false_positive"] for row in controls),
        },
        "arm_summaries": arm_summary,
        "significance": significance,
    }
    (REPORT / "corrected-rescore.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (REPORT / "paired-contrasts.json").write_text(
        json.dumps(significance["confirmatory"], indent=2, sort_keys=True) + "\n"
    )
    selections = [
        {
            "trial_id": row["trial_id"],
            "instance": row["instance"],
            "cell": row["cell_id"],
            "selected_artifact_ref": row["selected_artifact_ref"],
            "selected_prespecified_natural_state": row["natural_state_selected"],
            "recorded_exact_function_localisation": row["recorded_exact"],
            "corrected_exact_function_localisation": row["exact"],
        }
        for row in rows if row["cell_id"] in {"P04", "P05"}
    ]
    (REPORT / "natural-state-selections.json").write_text(
        json.dumps(selections, indent=2, sort_keys=True) + "\n"
    )

    readme = """# Attempt 057 corrected report pack

Start with [findings.md](findings.md). The paper-facing handover is
[paper-writer-handover.md](paper-writer-handover.md).

- [Scoring correction](scoring-correction.md)
- [Aggregate and mechanism tables](cell-table.md)
- [All 96 instance × arm cells](complete-result-cells.md)
- [All 288 individual reviews](all-review-results-corrected.csv)
- [Detailed significance results](significance-table.md)
- [Machine-readable correction manifest](corrected-rescore.json)

The files under the frozen Attempt 057 output directory were not changed.
"""
    (REPORT / "README.md").write_text(readme)


if __name__ == "__main__":
    main()
