"""Frozen reviewer runner and analysis for the two state-graph conditions only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from rdr.freeze import verify_manifest, write_manifest
from rdr.v2_etiq_export import STATE_GRAPH_CONDITIONS
from rdr.v2_openai_runner import (
    REVIEWER_EFFORT,
    REVIEWER_MODEL,
    ReviewError,
    codex_login_preflight,
    review,
)
from rdr.v2_provenance import verify_current_code_snapshot
from rdr.v2_review import SYSTEM_PROMPT_V2
from rdr.v2_schema import TruthV2, load_truth
from rdr.v2_scorer import ANSWER_SCHEMA_V2, score_v2, validate_answer_v2
from rdr.v2_state_graph_population import (
    freeze_state_graph_schedule,
    verify_state_graph_population,
)


BOOLEAN_METRICS = (
    "fault_occurred_correct",
    "residual_harm_correct",
    "detection_correct",
    "fault_class_hit",
)
LOCALIZATION_METRICS = (
    "root_cause_source_precision",
    "root_cause_source_recall",
    "root_cause_event_precision",
    "root_cause_event_recall",
    "historical_artifact_precision",
    "historical_artifact_recall",
    "restored_artifact_precision",
    "restored_artifact_recall",
    "residual_artifact_precision",
    "residual_artifact_recall",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value_sha(value: str | dict[str, Any]) -> str:
    text = value if isinstance(value, str) else json.dumps(
        value, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _public_rows(public_root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (public_root / "package_manifest.jsonl").read_text().splitlines()
        if line.strip()
    ]


def verify_frozen_review_inputs(
    build_root: Path, code_provenance: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify frozen bytes without loading or interpreting private truth."""
    build_problems = verify_manifest(build_root)
    public_problems = verify_manifest(build_root / "public")
    code_problems = verify_current_code_snapshot(code_provenance)
    if build_problems or public_problems or code_problems:
        raise RuntimeError(
            f"frozen input verification failed: build={build_problems[:3]}, "
            f"public={public_problems[:3]}, code={code_problems[:3]}"
        )
    public_root = build_root / "public"
    identity = json.loads((public_root / "build_identity.json").read_text())
    code = json.loads((code_provenance / "code_provenance.json").read_text())
    if identity.get("code_snapshot_id") != code.get("snapshot_id"):
        raise RuntimeError("build and reviewer executable provenance differ")
    if identity.get("code_provenance_manifest_sha256") != _sha(
        code_provenance / "MANIFEST.sha256.json"
    ):
        raise RuntimeError("build is bound to a different code provenance manifest")
    rows = _public_rows(public_root)
    if len(rows) != 84 or {row["arm"] for row in rows} != set(STATE_GRAPH_CONDITIONS):
        raise RuntimeError("public population is not exactly the 84 state-graph packages")
    frozen = json.loads((public_root / "state_graph_job_order.json").read_text())
    expected = freeze_state_graph_schedule(rows, frozen.get("seed"))
    if frozen != expected or len(frozen["jobs"]) != 84:
        raise RuntimeError("reviewer accepts only the frozen deterministic 84-job schedule")
    for job in frozen["jobs"]:
        package = public_root / "instances" / job["instance_id"] / "packages" / f"{job['arm']}.txt"
        if not package.is_file() or _sha(package) != job["package_sha256"]:
            raise RuntimeError("frozen schedule package hash differs")
    return frozen, rows


def _review_binding(
    build_root: Path, reviews_root: Path, code_provenance: Path,
) -> dict[str, Any]:
    identity = json.loads((build_root / "public/build_identity.json").read_text())
    code = json.loads((code_provenance / "code_provenance.json").read_text())
    binding = {
        "schema_version": 1,
        "build_root": str(build_root),
        "build_manifest_sha256": _sha(build_root / "MANIFEST.sha256.json"),
        "public_manifest_sha256": _sha(build_root / "public/MANIFEST.sha256.json"),
        "code_provenance": str(code_provenance),
        "code_snapshot_id": code["snapshot_id"],
        "code_provenance_manifest_sha256": _sha(code_provenance / "MANIFEST.sha256.json"),
        "build_code_snapshot_id": identity["code_snapshot_id"],
        "model": REVIEWER_MODEL,
        "effort": REVIEWER_EFFORT,
        "schedule_sha256": _sha(build_root / "public/state_graph_job_order.json"),
        "private_truth_loaded_during_review": False,
    }
    path = reviews_root / "review_binding.json"
    if path.is_file() and json.loads(path.read_text()) != binding:
        raise RuntimeError("review output root is bound to different frozen inputs")
    _write_json(path, binding)
    return binding


def _validate_review_record(
    record: dict[str, Any], package_sha256: str, response_ids: set[str],
) -> None:
    if record.get("package_sha256") != package_sha256:
        raise ReviewError("review record package hash differs from frozen schedule")
    if not record.get("system_prompt_sha256") or not record.get("schema_sha256"):
        raise ReviewError("review record lacks prompt/schema hashes")
    if not record.get("rendered_prompt_sha256"):
        raise ReviewError("review record lacks rendered prompt hash")
    response_id = record.get("response_id")
    if not response_id or response_id in response_ids:
        raise ReviewError("state-graph responses require unique non-empty response IDs")
    response_ids.add(response_id)
    if not record.get("usage") or record.get("input_tokens") is None:
        raise ReviewError("state-graph review record lacks usage")
    if record.get("observed_tool_use") is not False:
        raise ReviewError("state-graph review used a prohibited tool")
    if any(record.get(key) is not None for key in ("previous_response_id", "conversation", "session")):
        raise ReviewError("state-graph review was not a fresh stateless session")


def run_state_graph_reviews(
    build_root: Path,
    reviews_root: Path,
    code_provenance: Path,
    model: str = REVIEWER_MODEL,
    effort: str = REVIEWER_EFFORT,
    review_fn: Callable[..., dict[str, Any]] = review,
    preflight_fn: Callable[[], dict[str, Any]] = codex_login_preflight,
) -> dict[str, Any]:
    if (model, effort) != (REVIEWER_MODEL, REVIEWER_EFFORT):
        raise ValueError(f"state-graph reviewer is fixed to {REVIEWER_MODEL}/{REVIEWER_EFFORT}")
    schedule, _ = verify_frozen_review_inputs(build_root, code_provenance)
    if (reviews_root / "MANIFEST.sha256.json").is_file():
        problems = verify_manifest(reviews_root)
        if problems:
            raise RuntimeError(f"completed reviewer root changed: {problems[:5]}")
    reviews_root.mkdir(parents=True, exist_ok=True)
    binding = _review_binding(build_root, reviews_root, code_provenance)
    frozen_schedule = reviews_root / "frozen_state_graph_job_order.json"
    if frozen_schedule.is_file() and json.loads(frozen_schedule.read_text()) != schedule:
        raise RuntimeError("review output contains a different frozen schedule")
    _write_json(frozen_schedule, schedule)
    preflight = preflight_fn()
    public_root = build_root / "public"
    response_ids: set[str] = set()
    done = resumed = 0
    started = time.monotonic()
    for job in schedule["jobs"]:
        package = public_root / "instances" / job["instance_id"] / "packages" / f"{job['arm']}.txt"
        output = reviews_root / "results" / job["instance_id"] / f"{job['arm']}.json"
        existed = output.is_file()
        record = review_fn(
            package.read_text(), output, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
            validate_answer_v2, model, effort,
        )
        _validate_review_record(record, job["package_sha256"], response_ids)
        resumed += int(existed)
        done += int(not existed)
    summary = {
        "schema_version": 1,
        "planned": 84,
        "completed": 84,
        "done": done,
        "resumed": resumed,
        "model": model,
        "effort": effort,
        "wall_seconds": time.monotonic() - started,
        "preflight": preflight,
        "binding": binding,
        "private_truth_loaded_during_review": False,
        "fresh_stateless_sessions": 84,
        "observed_tool_calls": 0,
    }
    _write_json(reviews_root / "summary.json", summary)
    write_manifest(reviews_root)
    return summary


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"n": len(rows)}
    names = {
        "fault_occurrence_accuracy": "fault_occurred_correct",
        "residual_harm_accuracy": "residual_harm_correct",
        "strict_joint_detection": "detection_correct",
        "fault_class_accuracy": "fault_class_hit",
    }
    for output_name, field in names.items():
        result[output_name] = (
            sum(bool(row[field]) for row in rows) / len(rows) if rows else None
        )
    clean = [row for row in rows if not row["truth_fault_occurred"]]
    result["clean_false_positive_rate"] = (
        sum(bool(row["false_alarm"]) for row in clean) / len(clean) if clean else None
    )
    for field in LOCALIZATION_METRICS:
        values = [row[field] for row in rows if row[field] is not None]
        result[field] = sum(values) / len(values) if values else None
        result[field + "_n"] = len(values)
    return result


def _grouped(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    cells: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cells[str(row.get(field))].append(row)
    return {key: _aggregate(cell) for key, cell in sorted(cells.items())}


def _paired_outcomes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_instance: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_instance[row["instance_id"]][row["arm"]] = row
    pairs = []
    app_wins = etiq_wins = ties = 0
    for instance_id in sorted(by_instance):
        cell = by_instance[instance_id]
        if set(cell) != set(STATE_GRAPH_CONDITIONS):
            raise ValueError(f"{instance_id}: analysis lacks a paired state-graph outcome")
        app, etiq = (cell[arm] for arm in STATE_GRAPH_CONDITIONS)
        app_score, etiq_score = int(app["detection_correct"]), int(etiq["detection_correct"])
        app_wins += app_score > etiq_score
        etiq_wins += etiq_score > app_score
        ties += app_score == etiq_score
        pairs.append({
            "instance_id": instance_id,
            "fault_id": app["fault_id"],
            "repair": app["repair"],
            "appworld_strict_joint_detection": bool(app_score),
            "etiq_strict_joint_detection": bool(etiq_score),
            "fault_occurrence_answers_equal": app["answer_fault_occurred"] == etiq["answer_fault_occurred"],
            "residual_harm_answers_equal": app["answer_residual_harm_present"] == etiq["answer_residual_harm_present"],
            "package_token_difference_etiq_minus_appworld": etiq["tokens"] - app["tokens"],
            "actual_input_token_difference_etiq_minus_appworld": (
                etiq["actual_reviewer_input_tokens"] - app["actual_reviewer_input_tokens"]
            ),
        })
    return {
        "pairs": len(pairs),
        "appworld_wins": app_wins,
        "etiq_wins": etiq_wins,
        "ties": ties,
        "rows": pairs,
    }


def analyse_state_graph_reviews(
    build_root: Path,
    reviews_root: Path,
    output_root: Path,
    code_provenance: Path,
) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    verify_state_graph_population(build_root)
    verify_frozen_review_inputs(build_root, code_provenance)
    review_problems = verify_manifest(reviews_root)
    if review_problems:
        raise RuntimeError(f"review manifest failed: {review_problems[:5]}")
    binding = json.loads((reviews_root / "review_binding.json").read_text())
    if binding["build_manifest_sha256"] != _sha(build_root / "MANIFEST.sha256.json"):
        raise RuntimeError("reviews are bound to a different build")
    schedule = json.loads((build_root / "public/state_graph_job_order.json").read_text())
    inventory = {
        (row["instance_id"], row["arm"]): row
        for row in json.loads((build_root / "private/package_size_inventory.json").read_text())
    }
    rows = []
    for job in schedule["jobs"]:
        instance_id, arm = job["instance_id"], job["arm"]
        truth = load_truth(build_root / "private/truth" / f"{instance_id}.json")
        if not isinstance(truth, TruthV2):
            raise ValueError(f"{instance_id}: state-graph analysis requires TruthV2")
        review_record = json.loads((
            reviews_root / "results" / instance_id / f"{arm}.json"
        ).read_text())
        if review_record.get("package_sha256") != job["package_sha256"]:
            raise ValueError("analysis review/package binding differs")
        sizes = inventory[(instance_id, arm)]
        score = score_v2(review_record["answer"], truth)
        score["truth_instance_id"] = score.pop("instance_id")
        rows.append({
            "instance_id": instance_id,
            "arm": arm,
            "answer_fault_occurred": review_record["answer"]["fault_occurred"],
            "answer_residual_harm_present": review_record["answer"]["residual_harm_present"],
            "actual_reviewer_input_tokens": review_record["input_tokens"],
            "package_sha256": job["package_sha256"],
            "tokens": sizes["tokens"],
            "characters": sizes["characters"],
            "utf8_bytes": sizes["utf8_bytes"],
            **score,
        })
    output_root.mkdir(parents=True)
    (output_root / "scores.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    summary = {
        "schema_version": 1,
        "rows": len(rows),
        "instances": len({row["instance_id"] for row in rows}),
        "conditions": list(STATE_GRAPH_CONDITIONS),
        "overall": _aggregate(rows),
        "by_arm": _grouped(rows, "arm"),
        "by_repair": _grouped(rows, "repair"),
        "by_fault_class": _grouped(rows, "fault_class"),
        "by_fault_id": _grouped(rows, "fault_id"),
        "paired_appworld_versus_etiq": _paired_outcomes(rows),
        "package_size": {
            "characters_by_arm": {
                arm: sum(row["characters"] for row in rows if row["arm"] == arm)
                for arm in STATE_GRAPH_CONDITIONS
            },
            "estimated_tokens_by_arm": {
                arm: sum(row["tokens"] for row in rows if row["arm"] == arm)
                for arm in STATE_GRAPH_CONDITIONS
            },
            "actual_input_tokens_by_arm": {
                arm: sum(row["actual_reviewer_input_tokens"] for row in rows if row["arm"] == arm)
                for arm in STATE_GRAPH_CONDITIONS
            },
        },
        "build_manifest_sha256": _sha(build_root / "MANIFEST.sha256.json"),
        "review_manifest_sha256": _sha(reviews_root / "MANIFEST.sha256.json"),
        "code_provenance_manifest_sha256": _sha(code_provenance / "MANIFEST.sha256.json"),
    }
    _write_json(output_root / "summary.json", summary)
    write_manifest(output_root)
    return summary


def _fake_review(
    package: str, output: Path, system_prompt: str, schema: dict[str, Any], validate,
    model: str, effort: str,
) -> dict[str, Any]:
    answer = {
        "fault_occurred": False,
        "residual_harm_present": False,
        "fault_class": None,
        "root_cause_source_locations": [],
        "root_cause_event_indices": [],
        "historically_affected_artifacts": [],
        "restored_artifacts": [],
        "residual_harmful_artifacts": [],
    }
    validate(answer)
    record = {
        "answer": answer,
        "response_id": "fake-" + hashlib.sha256(str(output).encode()).hexdigest()[:24],
        "usage": {"input_tokens": len(package.split()), "output_tokens": 1},
        "input_tokens": len(package.split()),
        "output_tokens": 1,
        "package_sha256": _value_sha(package),
        "system_prompt_sha256": _value_sha(system_prompt),
        "rendered_prompt_sha256": _value_sha(system_prompt + package),
        "schema_sha256": _value_sha(schema),
        "observed_tool_use": False,
        "previous_response_id": None,
        "conversation": None,
        "session": None,
        "wall_seconds": 0.0,
        "model_requested": model,
        "reasoning_effort": effort,
    }
    _write_json(output, record)
    return record


def write_fake_reviews_and_analyse(
    build_root: Path,
    reviews_root: Path,
    analysis_root: Path,
    code_provenance: Path,
) -> dict[str, Any]:
    run = run_state_graph_reviews(
        build_root, reviews_root, code_provenance,
        review_fn=_fake_review,
        preflight_fn=lambda: {"fake": True, "model_calls": 0},
    )
    analysis = analyse_state_graph_reviews(
        build_root, reviews_root, analysis_root, code_provenance
    )
    return {"fake_reviewer_calls": 0, "records": run["completed"], "analysis": analysis}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--build", type=Path, required=True)
    run.add_argument("--reviews", type=Path, required=True)
    run.add_argument("--code-provenance", type=Path, required=True)
    run.add_argument("--model", default=REVIEWER_MODEL)
    run.add_argument("--effort", default=REVIEWER_EFFORT)
    analyse = sub.add_parser("analyse")
    analyse.add_argument("--build", type=Path, required=True)
    analyse.add_argument("--reviews", type=Path, required=True)
    analyse.add_argument("--out", type=Path, required=True)
    analyse.add_argument("--code-provenance", type=Path, required=True)
    dry = sub.add_parser("dry-analysis")
    dry.add_argument("--build", type=Path, required=True)
    dry.add_argument("--reviews", type=Path, required=True)
    dry.add_argument("--out", type=Path, required=True)
    dry.add_argument("--code-provenance", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        result = run_state_graph_reviews(
            args.build, args.reviews, args.code_provenance, args.model, args.effort
        )
    elif args.command == "analyse":
        result = analyse_state_graph_reviews(
            args.build, args.reviews, args.out, args.code_provenance
        )
    else:
        result = write_fake_reviews_and_analyse(
            args.build, args.reviews, args.out, args.code_provenance
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
