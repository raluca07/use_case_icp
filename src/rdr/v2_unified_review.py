"""Run and analyse only the final frozen unified V2 experiment."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path

from rdr.freeze import verify_manifest, write_manifest
from rdr.graph import Graph, rec_node
from rdr.stepwise import (
    FORCED_STEP_SYSTEM_PROMPT, NOTE_CHARS, MODES, explore, explored_graph, final_package,
    round_package,
)
from rdr.v2_openai_runner import (
    REVIEWER_EFFORT, REVIEWER_MODEL, codex_login_preflight, request_identity, review,
)
from rdr.v2_packager import _common_with_calls, _flat_graph
from rdr.v2_provenance import verify_current_code_snapshot
from rdr.v2_review import SYSTEM_PROMPT_V2
from rdr.v2_schema import TraceV2, TruthV2
from rdr.v2_scorer import ANSWER_SCHEMA_V2, score_v2, validate_answer_v2
from rdr.v2_unified_experiment import INTERACTIVE_ARMS, ONE_SHOT_ARMS, verify_unified


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _value_sha(value: str | dict) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _review_preflight(build: Path) -> tuple[Path, dict]:
    verify_unified(build)
    public = build / "public"
    identity = json.loads((public / "build_identity.json").read_text())
    provenance = Path(identity["code_provenance"])
    if _sha(provenance / "MANIFEST.sha256.json") != identity["code_provenance_manifest_sha256"]:
        raise ValueError("code-provenance manifest differs from frozen build binding")
    problems = verify_current_code_snapshot(provenance)
    if problems:
        raise ValueError(f"current reviewer code differs from frozen snapshot: {problems[:5]}")
    return public, identity


def _stage_manifest(reviews: Path, stage: str) -> None:
    write_manifest(reviews / stage)


def _verify_stage(reviews: Path, stage: str) -> None:
    problems = verify_manifest(reviews / stage)
    if problems:
        raise ValueError(f"{stage} review stage is incomplete or changed: {problems[:5]}")


def _run_identity(build: Path, public: Path, build_identity: dict) -> dict:
    return {
        "schema_version": 1,
        "build_manifest_sha256": _sha(build / "MANIFEST.sha256.json"),
        "public_manifest_sha256": _sha(public / "MANIFEST.sha256.json"),
        "code_snapshot_id": build_identity["code_snapshot_id"],
        "code_provenance_manifest_sha256": build_identity["code_provenance_manifest_sha256"],
        "one_shot_schedule_sha256": _sha(public / "one_shot_job_order.json"),
        "N_schedule_sha256": _sha(public / "interactive_N_job_order.json"),
        "O_schedule_sha256": _sha(public / "interactive_O_job_order.json"),
        "system_prompt_sha256": _value_sha(SYSTEM_PROMPT_V2),
        "answer_schema_sha256": _value_sha(ANSWER_SCHEMA_V2),
        "model": REVIEWER_MODEL, "effort": REVIEWER_EFFORT,
        "transport": "codex_cli", "pilot_outputs_included": False,
    }


def _corrected_o_run_identity(build: Path, public: Path, build_identity: dict) -> dict:
    identity = _run_identity(build, public, build_identity)
    identity.update({
        "review_scope": "corrected_O_only",
        "o_walk_contract": "visible_unexpanded_frontier_or_six_valid_expansions",
        "o_step_schema": "dynamic_eligible_node_enum",
    })
    return identity


def _bind_review_root(reviews: Path, expected: dict) -> None:
    path = reviews / "run_identity.json"
    if path.is_file():
        saved = json.loads(path.read_text())
        if saved != expected:
            differing = sorted(
                key for key in set(saved) | set(expected)
                if key not in saved or key not in expected or saved[key] != expected[key]
            )
            raise ValueError(f"review root identity differs: {differing}")
        return
    if reviews.exists() and any(reviews.iterdir()):
        raise ValueError("refusing to bind a non-empty review root without run_identity.json")
    reviews.mkdir(parents=True, exist_ok=True)
    _write_json(path, expected)


def validate_canonical_record(record: dict, package: str, system_prompt: str, schema: dict,
                              validator, response_ids: set[str]) -> str:
    """Validate one canonical call result; attempt sidecars never enter here."""
    cli_version = record.get("codex_cli_version")
    if not isinstance(cli_version, str) or not cli_version:
        raise ValueError("canonical record lacks Codex CLI version")
    expected = request_identity(
        package, REVIEWER_MODEL, REVIEWER_EFFORT, system_prompt, schema, cli_version=cli_version,
    )
    differing = sorted(key for key, value in expected.items() if record.get(key) != value)
    if differing:
        raise ValueError(f"canonical request identity differs in {differing}")
    if record.get("terminal_status") != "completed":
        raise ValueError("canonical record is not terminally completed")
    usage = record.get("usage")
    if (not isinstance(usage, dict) or not usage
            or not isinstance(usage.get("input_tokens"), (int, float))
            or isinstance(usage.get("input_tokens"), bool) or usage["input_tokens"] <= 0):
        raise ValueError("canonical record lacks non-empty input-token usage")
    if record.get("observed_tool_use") is not False:
        raise ValueError("canonical record observed reviewer tool use")
    for field in ("previous_response_id", "conversation", "session"):
        if record.get(field, "missing") is not None:
            raise ValueError(f"canonical record requires {field}=null")
    response_id = record.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        raise ValueError("canonical record lacks a response ID")
    if response_id in response_ids:
        raise ValueError("duplicate response ID across distinct canonical model calls")
    validator(record.get("answer"))
    response_ids.add(response_id)
    return response_id


def _one_shot_schedule(public: Path) -> dict:
    schedule = json.loads((public / "one_shot_job_order.json").read_text())
    if len(schedule.get("jobs", [])) != 1260:
        raise ValueError("runner accepts only the frozen 1,260-job schedule")
    return schedule


def _interactive_schedule(public: Path, arm: str) -> dict:
    schedule = json.loads((public / f"interactive_{arm}_job_order.json").read_text())
    if len(schedule.get("jobs", [])) != 42 or schedule.get("arm") != arm:
        raise ValueError("runner accepts only a complete frozen interactive schedule")
    return schedule


def corrected_o_eligible_nodes(graph: Graph, expanded: list[str]) -> list[str]:
    """Return the stable visible frontier, excluding every node already expanded."""
    view = explored_graph(graph, expanded)
    visible = set(view.call_nodes) | set(view.record_nodes)
    return sorted(visible - set(expanded))


def corrected_o_step_schema(eligible: list[str]) -> dict:
    if not eligible:
        raise ValueError("an O step schema requires at least one eligible node")
    return {
        "type": "object",
        "properties": {
            "action": {"enum": ["expand"]},
            "node": {"enum": list(eligible)},
            "note": {"type": "string"},
        },
        "required": ["action", "node", "note"],
        "additionalProperties": False,
    }


def validate_corrected_o_step(step: dict, eligible: list[str]) -> dict:
    if not isinstance(step, dict) or sorted(step) != ["action", "node", "note"]:
        raise ValueError("corrected O step must contain exactly action, node and note")
    if step["action"] != "expand":
        raise ValueError("corrected O accepts only expand steps")
    if not isinstance(step["note"], str):
        raise ValueError("corrected O note must be a string")
    node = step["node"]
    if not isinstance(node, str) or not node:
        raise ValueError("corrected O node must be a non-empty identifier")
    if node not in eligible:
        raise ValueError(f"corrected O node is not currently eligible: {node}")
    return step


def explore_corrected_o(trace, symptom: str, instance_id: str, ask, graph: Graph,
                        common_header: str, max_expansions: int = 6) -> dict:
    """Walk only the currently visible, unexpanded frontier, then request one diagnosis."""
    start = rec_node(symptom)
    if start not in graph.record_nodes:
        raise ValueError(f"{instance_id}: the reported record {symptom} is not in the graph")
    expanded, notes, requests = [start], [], []
    stopped_by = "budget"
    for round_number in range(1, max_expansions + 1):
        eligible = corrected_o_eligible_nodes(graph, expanded)
        if not eligible:
            stopped_by = "frontier_exhausted"
            break
        schema = corrected_o_step_schema(eligible)
        validator = lambda value, allowed=eligible: validate_corrected_o_step(value, allowed)
        package = round_package(
            trace, symptom, graph, expanded, notes, [], max_expansions - len(requests),
            common_header=common_header,
        )
        record = ask("step", package, round_number, schema, validator)
        step = validator(record["answer"])
        requests.append({
            "round": round_number,
            "eligible_nodes": eligible,
            "selected_node": step["node"],
        })
        expanded.append(step["node"])
        notes.append(step["note"].strip()[:NOTE_CHARS])
    final_record = ask(
        "answer", final_package(trace, symptom, graph, expanded, notes, common_header=common_header),
        0, ANSWER_SCHEMA_V2, validate_answer_v2,
    )
    return {
        "expanded": expanded,
        "expanded_nodes_in_order": expanded[1:],
        "eligible_nodes_before_requests": [
            {"round": item["round"], "nodes": item["eligible_nodes"]} for item in requests
        ],
        "selected_nodes": [item["selected_node"] for item in requests],
        "notes": notes,
        "requests": requests,
        "valid_expansions": len(requests),
        "rounds": len(requests),
        "stopped_by": stopped_by,
        "max_expansions": max_expansions,
        "final_call": {
            "response": final_record["answer"],
            "response_id": final_record["response_id"],
            "usage": final_record.get("usage", {}),
            "wall_seconds": final_record.get("wall_seconds", 0),
        },
    }


def _validate_one_shot_stage(public: Path, reviews: Path, response_ids: set[str] | None = None) -> set[str]:
    response_ids = response_ids if response_ids is not None else set()
    for job in _one_shot_schedule(public)["jobs"]:
        package_path = public / "instances" / job["instance_id"] / "packages" / f"{job['arm']}.txt"
        if _sha(package_path) != job["package_sha256"]:
            raise ValueError("scheduled package hash differs")
        path = reviews / "one_shot" / job["instance_id"] / f"{job['arm']}.json"
        if not path.is_file():
            raise ValueError(f"completed one-shot stage lacks canonical result {path}")
        validate_canonical_record(
            json.loads(path.read_text()), package_path.read_text(), SYSTEM_PROMPT_V2,
            ANSWER_SCHEMA_V2, validate_answer_v2, response_ids,
        )
    return response_ids


def _validate_interactive_stage(public: Path, reviews: Path, arm: str,
                                response_ids: set[str]) -> set[str]:
    schedule = _interactive_schedule(public, arm)
    mode_prompt, mode_schema, mode_validate = MODES[arm]
    for job in schedule["jobs"]:
        base = public / "interactive" / job["instance_id"]
        if _sha(base / "walk.json") != job["walk_sha256"]:
            raise ValueError("interactive walk hash differs")
        walk = json.loads((base / "walk.json").read_text())
        trace = TraceV2.from_dict(walk["trace"])
        flat = _flat_graph(walk["execution_graph"])

        def ask(kind: str, package: str, round_number: int):
            if kind == "step" and round_number == 1:
                if hashlib.sha256(package.encode()).hexdigest() != job["initial_package_sha256"]:
                    raise ValueError("first interactive package differs from frozen package")
            path = reviews / arm / job["instance_id"] / (
                f"{arm}.step{round_number}.json" if kind == "step" else f"{arm}.json"
            )
            if not path.is_file():
                raise ValueError(f"completed {arm} stage lacks canonical result {path}")
            prompt, schema, validator = ((mode_prompt, mode_schema, mode_validate) if kind == "step"
                                          else (SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2, validate_answer_v2))
            record = json.loads(path.read_text())
            validate_canonical_record(record, package, prompt, schema, validator, response_ids)
            return record["answer"]

        result = explore(
            trace.to_v1_observed(), walk["reported_artifact"], job["instance_id"], None, ask,
            max_expansions=6, graph=flat, common_header=_common_with_calls(trace),
        )
        path_file = reviews / arm / job["instance_id"] / f"{arm}.path.json"
        if not path_file.is_file():
            raise ValueError(f"completed {arm} stage lacks path record {path_file}")
        saved = json.loads(path_file.read_text())
        expected = {key: value for key, value in result.items() if key != "record"}
        if any(saved.get(key) != value for key, value in expected.items()):
            raise ValueError(f"{arm} interactive path differs from canonical model-call sequence")
    return response_ids


def _validate_corrected_o_stage(public: Path, reviews: Path,
                                response_ids: set[str] | None = None) -> set[str]:
    response_ids = response_ids if response_ids is not None else set()
    for job in _interactive_schedule(public, "O")["jobs"]:
        base = public / "interactive" / job["instance_id"]
        if _sha(base / "walk.json") != job["walk_sha256"]:
            raise ValueError("corrected O interactive walk hash differs")
        walk = json.loads((base / "walk.json").read_text())
        trace = TraceV2.from_dict(walk["trace"])
        flat = _flat_graph(walk["execution_graph"])
        transcript = []

        def ask(kind: str, package: str, round_number: int, schema: dict, validator):
            if kind == "step" and round_number == 1:
                if hashlib.sha256(package.encode()).hexdigest() != job["initial_package_sha256"]:
                    raise ValueError("corrected O first package differs from frozen initial package")
            path = reviews / "O" / job["instance_id"] / (
                f"O.step{round_number}.json" if kind == "step" else "O.json"
            )
            if not path.is_file():
                raise ValueError(f"completed corrected O stage lacks canonical result {path}")
            prompt = FORCED_STEP_SYSTEM_PROMPT if kind == "step" else SYSTEM_PROMPT_V2
            record = json.loads(path.read_text())
            response_id = validate_canonical_record(
                record, package, prompt, schema, validator, response_ids,
            )
            transcript.append({
                "kind": kind, "round": round_number, "response_id": response_id,
                "usage": record.get("usage", {}), "wall_seconds": record.get("wall_seconds", 0),
                "package_sha256": record.get("package_sha256"),
            })
            return record

        expected = explore_corrected_o(
            trace.to_v1_observed(), walk["reported_artifact"], job["instance_id"], ask, flat,
            _common_with_calls(trace),
        )
        expected["transcript"] = transcript
        path_file = reviews / "O" / job["instance_id"] / "O.path.json"
        if not path_file.is_file() or json.loads(path_file.read_text()) != expected:
            raise ValueError("corrected O path differs from its canonical model-call sequence")
    return response_ids


def _corrected_o_counts(public: Path, reviews: Path) -> dict:
    paths = [
        json.loads((reviews / "O" / job["instance_id"] / "O.path.json").read_text())
        for job in _interactive_schedule(public, "O")["jobs"]
    ]
    expansions = sum(path["valid_expansions"] for path in paths)
    return {
        "instances": len(paths),
        "valid_expansions": expansions,
        "final_calls": len(paths),
        "total_calls": expansions + len(paths),
        "frontier_exhausted": sum(path["stopped_by"] == "frontier_exhausted" for path in paths),
        "budget": sum(path["stopped_by"] == "budget" for path in paths),
        "repeated_or_invisible_or_empty": sum(
            int(not request["selected_node"]
                or request["selected_node"] not in request["eligible_nodes"]
                or request["selected_node"] in path["selected_nodes"][:index])
            for path in paths for index, request in enumerate(path["requests"])
        ),
    }


def _prior_response_ids(public: Path, reviews: Path, stages: tuple[str, ...]) -> set[str]:
    """Enumerate canonical model calls from frozen schedules, never recursive sidecar globs."""
    response_ids: set[str] = set()
    for stage in stages:
        if stage == "one_shot":
            _validate_one_shot_stage(public, reviews, response_ids)
        elif stage in INTERACTIVE_ARMS:
            _validate_interactive_stage(public, reviews, stage, response_ids)
        else:
            raise ValueError(f"unknown review stage {stage}")
    return response_ids


def _completed_stage(reviews: Path, stage: str) -> bool:
    return (reviews / stage / "MANIFEST.sha256.json").is_file()


def run_one_shot(build: Path, reviews: Path, review_fn=review, live: bool = True) -> dict:
    public, identity = _review_preflight(build)
    schedule = _one_shot_schedule(public)
    _bind_review_root(reviews, _run_identity(build, public, identity))
    if _completed_stage(reviews, "one_shot"):
        _verify_stage(reviews, "one_shot")
        _validate_one_shot_stage(public, reviews)
        return {"planned": 1260, "completed": 1260, "resumed": 1260,
                "immutable_completed_stage": True, "preflight": None}
    if live:
        preflight = codex_login_preflight()
    else:
        preflight = {"authenticated": False, "fake": True}
    stage = reviews / "one_shot"
    stage.mkdir(parents=True, exist_ok=True)
    response_ids, resumed = set(), 0
    for job in schedule["jobs"]:
        package_path = public / "instances" / job["instance_id"] / "packages" / f"{job['arm']}.txt"
        if _sha(package_path) != job["package_sha256"]:
            raise ValueError("scheduled package hash differs")
        output = stage / job["instance_id"] / f"{job['arm']}.json"
        existed = output.exists()
        package = package_path.read_text()
        record = review_fn(package, output, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                           validate_answer_v2, REVIEWER_MODEL, REVIEWER_EFFORT)
        validate_canonical_record(record, package, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                                  validate_answer_v2, response_ids)
        resumed += int(existed)
    _validate_one_shot_stage(public, reviews)
    _stage_manifest(reviews, "one_shot")
    return {"planned": 1260, "completed": 1260, "resumed": resumed, "preflight": preflight}


def run_interactive(build: Path, reviews: Path, arm: str, review_fn=review, live: bool = True) -> dict:
    if arm not in INTERACTIVE_ARMS:
        raise ValueError("interactive arm must be N or O")
    public, identity = _review_preflight(build)
    _bind_review_root(reviews, _run_identity(build, public, identity))
    _verify_stage(reviews, "one_shot")
    prior_stages = ("one_shot",)
    if arm == "O":
        _verify_stage(reviews, "N")
        prior_stages = ("one_shot", "N")
    response_ids = _prior_response_ids(public, reviews, prior_stages)
    schedule = _interactive_schedule(public, arm)
    if _completed_stage(reviews, arm):
        _verify_stage(reviews, arm)
        _validate_interactive_stage(public, reviews, arm, response_ids)
        if arm == "O":
            problems = verify_manifest(reviews)
            if problems:
                raise ValueError(f"completed review root changed: {problems[:5]}")
        return {"arm": arm, "instances": 42, "reviewer_calls": 0,
                "immutable_completed_stage": True,
                "expected": "84..294" if arm == "N" else 294}
    if live:
        codex_login_preflight()
    stage = reviews / arm
    stage.mkdir(parents=True, exist_ok=True)
    calls = 0
    for job in schedule["jobs"]:
        base = public / "interactive" / job["instance_id"]
        if _sha(base / "walk.json") != job["walk_sha256"]:
            raise ValueError("interactive walk hash differs")
        walk = json.loads((base / "walk.json").read_text())
        trace = TraceV2.from_dict(walk["trace"])
        flat = _flat_graph(walk["execution_graph"])
        transcript = []
        mode_prompt, mode_schema, mode_validate = MODES[arm]

        def ask(kind: str, package: str, round_number: int):
            nonlocal calls
            if kind == "step" and round_number == 1:
                if hashlib.sha256(package.encode()).hexdigest() != job["initial_package_sha256"]:
                    raise ValueError("first interactive package differs from frozen package")
            output = stage / job["instance_id"] / (
                f"{arm}.step{round_number}.json" if kind == "step" else f"{arm}.json"
            )
            prompt, schema, validator = ((mode_prompt, mode_schema, mode_validate) if kind == "step"
                                          else (SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2, validate_answer_v2))
            record = review_fn(package, output, prompt, schema, validator, REVIEWER_MODEL, REVIEWER_EFFORT)
            response_id = validate_canonical_record(
                record, package, prompt, schema, validator, response_ids,
            )
            transcript.append({"kind": kind, "round": round_number, "response_id": response_id,
                               "usage": record.get("usage", {}), "wall_seconds": record.get("wall_seconds", 0),
                               "package_sha256": record.get("package_sha256")})
            calls += 1
            return record["answer"]

        result = explore(trace.to_v1_observed(), walk["reported_artifact"], job["instance_id"], None, ask,
                         max_expansions=6, graph=flat, common_header=_common_with_calls(trace))
        path = {key: value for key, value in result.items() if key != "record"}
        path["transcript"] = transcript
        _write_json(stage / job["instance_id"] / f"{arm}.path.json", path)
    all_ids = _prior_response_ids(public, reviews, prior_stages)
    _validate_interactive_stage(public, reviews, arm, all_ids)
    _stage_manifest(reviews, arm)
    if arm == "O":
        write_manifest(reviews)
    return {"arm": arm, "instances": 42, "reviewer_calls": calls,
            "expected": "84..294" if arm == "N" else 294}


def run_corrected_o(build: Path, reviews: Path, review_fn=review, live: bool = True) -> dict:
    """Run corrected O alone in a new review root; completed one-shot and N roots are never touched."""
    public, identity = _review_preflight(build)
    _bind_review_root(reviews, _corrected_o_run_identity(build, public, identity))
    if _completed_stage(reviews, "O"):
        _verify_stage(reviews, "O")
        if verify_manifest(reviews):
            raise ValueError("completed corrected O review root changed")
        _validate_corrected_o_stage(public, reviews)
        counts = _corrected_o_counts(public, reviews)
        return {**counts, "new_reviewer_calls": 0, "resumed": counts["total_calls"],
                "immutable_completed_stage": True}
    if live:
        codex_login_preflight()
    stage = reviews / "O"
    stage.mkdir(parents=True, exist_ok=True)
    response_ids: set[str] = set()
    calls = resumed = 0
    for job in _interactive_schedule(public, "O")["jobs"]:
        base = public / "interactive" / job["instance_id"]
        if _sha(base / "walk.json") != job["walk_sha256"]:
            raise ValueError("corrected O interactive walk hash differs")
        walk = json.loads((base / "walk.json").read_text())
        trace = TraceV2.from_dict(walk["trace"])
        flat = _flat_graph(walk["execution_graph"])
        transcript = []

        def ask(kind: str, package: str, round_number: int, schema: dict, validator):
            nonlocal calls, resumed
            if kind == "step" and round_number == 1:
                if hashlib.sha256(package.encode()).hexdigest() != job["initial_package_sha256"]:
                    raise ValueError("corrected O first package differs from frozen initial package")
            output = stage / job["instance_id"] / (
                f"O.step{round_number}.json" if kind == "step" else "O.json"
            )
            existed = output.is_file()
            prompt = FORCED_STEP_SYSTEM_PROMPT if kind == "step" else SYSTEM_PROMPT_V2
            record = review_fn(
                package, output, prompt, schema, validator, REVIEWER_MODEL, REVIEWER_EFFORT,
            )
            response_id = validate_canonical_record(
                record, package, prompt, schema, validator, response_ids,
            )
            transcript.append({
                "kind": kind, "round": round_number, "response_id": response_id,
                "usage": record.get("usage", {}), "wall_seconds": record.get("wall_seconds", 0),
                "package_sha256": record.get("package_sha256"),
            })
            calls += 1
            resumed += int(existed)
            return record

        result = explore_corrected_o(
            trace.to_v1_observed(), walk["reported_artifact"], job["instance_id"], ask, flat,
            _common_with_calls(trace),
        )
        result["transcript"] = transcript
        _write_json(stage / job["instance_id"] / "O.path.json", result)
    _validate_corrected_o_stage(public, reviews)
    counts = _corrected_o_counts(public, reviews)
    if counts["valid_expansions"] != 122 or counts["final_calls"] != 42 or counts["total_calls"] != 164:
        raise ValueError(f"corrected O frozen-population call counts differ: {counts}")
    if counts["repeated_or_invisible_or_empty"]:
        raise ValueError("corrected O contains an invalid selected node")
    _stage_manifest(reviews, "O")
    write_manifest(reviews)
    return {**counts, "new_reviewer_calls": calls - resumed, "resumed": resumed,
            "preflight": "codex_cli" if live else "fake"}


def _ratio(rows: list[dict], key: str, applicable=lambda row: True) -> dict:
    cell = [row for row in rows if applicable(row)]
    numerator = sum(bool(row[key]) for row in cell)
    return {"numerator": numerator, "denominator": len(cell),
            "value": numerator / len(cell) if cell else None}


def _mean(rows: list[dict], key: str) -> dict:
    values = [row[key] for row in rows if row.get(key) is not None]
    return {"numerator": sum(values), "denominator": len(values),
            "value": sum(values) / len(values) if values else None}


def _summary(rows: list[dict]) -> dict:
    metrics = {
        "fault_occurrence_accuracy": _ratio(rows, "fault_occurred_correct"),
        "residual_harm_accuracy": _ratio(rows, "residual_harm_correct"),
        "strict_joint_detection": _ratio(rows, "detection_correct"),
        "clean_false_positive_rate": _ratio(rows, "false_alarm", lambda r: not r["truth_fault_occurred"]),
        "fault_class_accuracy_faulty_only": _ratio(rows, "fault_class_hit", lambda r: r["truth_fault_occurred"]),
        "false_fault_class_claims_clean": _ratio(rows, "false_fault_class_claim", lambda r: not r["truth_fault_occurred"]),
    }
    for key in (
        "root_cause_source_precision", "root_cause_source_recall", "root_cause_event_precision",
        "root_cause_event_recall", "historical_artifact_precision", "historical_artifact_recall",
        "restored_artifact_precision", "restored_artifact_recall", "residual_artifact_precision",
        "residual_artifact_recall",
    ):
        metrics[key] = _mean(rows, key)
    faulty = [row for row in rows if row["truth_fault_occurred"]]
    exact = sum(row["complete_root_cause_set_recovered"] for row in faulty)
    metrics["complete_gold_root_cause_set_recovered"] = {
        "numerator": exact, "denominator": len(faulty), "value": exact / len(faulty) if faulty else None,
    }
    return metrics


def _crossed_summaries(rows: list[dict]) -> dict:
    crossed = {}
    dimensions = {
        "arm_x_status": lambda row: (
            "clean" if not row["truth_fault_occurred"] else row["repair"]
        ),
        "arm_x_repair": lambda row: row["repair"] if row["truth_fault_occurred"] else None,
        "arm_x_fault_class": lambda row: row["fault_class"] if row["truth_fault_occurred"] else None,
        "arm_x_fault_id": lambda row: row["fault_id"] if row["truth_fault_occurred"] else None,
    }
    for name, dimension in dimensions.items():
        arm_cells: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for row in rows:
            value = dimension(row)
            if value is not None:
                arm_cells[row["arm"]][str(value)].append(row)
        crossed[name] = {
            arm: {
                value: {"evaluations": len(cell), "metrics": _summary(cell)}
                for value, cell in sorted(values.items())
            }
            for arm, values in sorted(arm_cells.items())
        }
    return crossed


def _equivalence_files(build: Path) -> dict[str, list[Path]]:
    public, private = build / "public", build / "private"
    return {
        "one_shot_packages": sorted((public / "instances").glob("*/packages/*.txt")),
        "N_inputs": sorted((public / "interactive").glob("*/N.initial.txt")),
        "O_inputs": sorted((public / "interactive").glob("*/O.initial.txt")),
        "interactive_walks": sorted((public / "interactive").glob("*/walk.json")),
        "truth": sorted((private / "truth").glob("*.json")),
        "instance_mapping": [private / "instance_mapping.json"],
        "one_shot_schedule": [public / "one_shot_job_order.json"],
        "N_schedule": [public / "interactive_N_job_order.json"],
        "O_schedule": [public / "interactive_O_job_order.json"],
    }


def audit_build_equivalence(base_build: Path, corrected_build: Path, output: Path | None = None) -> dict:
    verify_unified(base_build)
    verify_unified(corrected_build)
    base_groups, corrected_groups = _equivalence_files(base_build), _equivalence_files(corrected_build)
    groups, mismatches = {}, []
    for name in base_groups:
        base = {path.relative_to(base_build).as_posix(): _sha(path) for path in base_groups[name]}
        corrected = {
            path.relative_to(corrected_build).as_posix(): _sha(path) for path in corrected_groups[name]
        }
        missing = sorted(set(base) - set(corrected))
        added = sorted(set(corrected) - set(base))
        changed = sorted(path for path in set(base) & set(corrected) if base[path] != corrected[path])
        groups[name] = {
            "files": len(base), "byte_identical": not (missing or added or changed),
            "missing": missing, "added": added, "changed": changed,
        }
        mismatches.extend(f"{name}:{kind}:{path}" for kind, paths in (
            ("missing", missing), ("added", added), ("changed", changed)
        ) for path in paths)
    result = {
        "schema_version": 1, "base_build": str(base_build), "corrected_build": str(corrected_build),
        "base_manifest_sha256": _sha(base_build / "MANIFEST.sha256.json"),
        "corrected_manifest_sha256": _sha(corrected_build / "MANIFEST.sha256.json"),
        "passed": not mismatches, "groups": groups, "mismatches": mismatches,
    }
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        _write_json(output / "equivalence_audit.json", result)
        write_manifest(output)
    if mismatches:
        raise ValueError(f"corrected build is not equivalent: {mismatches[:5]}")
    return result


def _analysis_rows(build: Path, one_shot_reviews: Path, n_reviews: Path,
                   o_reviews: Path) -> list[dict]:
    public, private = build / "public", build / "private"
    package_rows = {(r["instance_id"], r["arm"]): r for r in (
        json.loads(line) for line in (public / "package_manifest.jsonl").read_text().splitlines()
    )}
    rows = []
    for instance_dir in sorted((public / "instances").iterdir()):
        instance_id = instance_dir.name
        truth = TruthV2.from_dict(json.loads((private / "truth" / f"{instance_id}.json").read_text()))
        for arm in ONE_SHOT_ARMS:
            record = json.loads((one_shot_reviews / "one_shot" / instance_id / f"{arm}.json").read_text())
            answer = record["answer"]
            scored = score_v2(answer, truth)
            scored["complete_root_cause_set_recovered"] = (
                set(answer["root_cause_source_locations"]) == set(truth.root_cause_source_locations)
                and set(answer["root_cause_event_indices"]) == set(truth.root_cause_event_indices)
            )
            size = package_rows[(instance_id, arm)]
            rows.append({"arm": arm, **scored, "package_tokens": size["tokens"],
                         "package_characters": size["characters"], "package_utf8_bytes": size["utf8_bytes"],
                         "actual_input_tokens": record.get("usage", {}).get("input_tokens")})
        for arm in INTERACTIVE_ARMS:
            root = n_reviews if arm == "N" else o_reviews
            record = json.loads((root / arm / instance_id / f"{arm}.json").read_text())
            path = json.loads((root / arm / instance_id / f"{arm}.path.json").read_text())
            answer = record["answer"]
            scored = score_v2(answer, truth)
            scored["complete_root_cause_set_recovered"] = (
                set(answer["root_cause_source_locations"]) == set(truth.root_cause_source_locations)
                and set(answer["root_cause_event_indices"]) == set(truth.root_cause_event_indices)
            )
            usage = sum(item.get("usage", {}).get("input_tokens", 0) or 0 for item in path["transcript"])
            rows.append({"arm": arm, **scored,
                         "package_tokens": record.get("package_reviewer_tokens"),
                         "package_characters": record.get("package_characters"),
                         "package_utf8_bytes": record.get("package_utf8_bytes"),
                         "actual_input_tokens": usage})
    return rows


def _write_analysis(rows: list[dict], output: Path, identity: dict) -> dict:
    grouped = {}
    for field in ("arm", "repair", "fault_class", "fault_id"):
        cells = defaultdict(list)
        for row in rows:
            cells[str(row.get(field))].append(row)
        grouped[field] = {key: {"evaluations": len(cell), "metrics": _summary(cell)}
                          for key, cell in sorted(cells.items())}
    crossed = _crossed_summaries(rows)
    paired = []
    by_key = {(row["instance_id"], row["arm"]): row for row in rows}
    arms = (*ONE_SHOT_ARMS, *INTERACTIVE_ARMS)
    instances = sorted({row["instance_id"] for row in rows})
    for left, right in itertools.combinations(arms, 2):
        left_wins = right_wins = ties = 0
        for instance in instances:
            a, b = by_key[(instance, left)]["detection_correct"], by_key[(instance, right)]["detection_correct"]
            left_wins += int(a and not b); right_wins += int(b and not a); ties += int(a == b)
        paired.append({"left": left, "right": right, "denominator": len(instances),
                       "left_wins": left_wins, "right_wins": right_wins, "ties": ties})
    size = {arm: {
        "package_tokens": _mean([{"x": r["package_tokens"]} for r in rows if r["arm"] == arm], "x"),
        "actual_input_tokens": _mean([{"x": r["actual_input_tokens"]} for r in rows if r["arm"] == arm], "x"),
    } for arm in arms}
    output.mkdir(parents=True, exist_ok=False)
    (output / "scores.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    _write_json(output / "analysis_identity.json", identity)
    _write_json(output / "summary.json", {"evaluations": len(rows), "overall": _summary(rows),
                                           "grouped": grouped, "crossed": crossed, "size": size,
                                           "pilot_outputs_included": False})
    _write_json(output / "paired_arm_comparisons.json", paired)
    write_manifest(output)
    return {"evaluations": len(rows), "arms": len(arms), "paired_comparisons": len(paired)}


def _verify_review_identity(reviews: Path, expected: dict) -> dict:
    path = reviews / "run_identity.json"
    if not path.is_file():
        raise ValueError(f"review root lacks run identity: {reviews}")
    saved = json.loads(path.read_text())
    if saved != expected:
        differing = sorted(
            key for key in set(saved) | set(expected)
            if key not in saved or key not in expected or saved[key] != expected[key]
        )
        raise ValueError(f"review root identity differs: {differing}")
    return saved


def analyse(build: Path, reviews: Path, output: Path) -> dict:
    public, build_identity = _review_preflight(build)
    for stage in ("one_shot", "N", "O"):
        _verify_stage(reviews, stage)
    if verify_manifest(reviews):
        raise ValueError("final review manifest is missing or changed")
    run_identity = _verify_review_identity(reviews, _run_identity(build, public, build_identity))
    response_ids = _validate_one_shot_stage(public, reviews)
    _validate_interactive_stage(public, reviews, "N", response_ids)
    _validate_interactive_stage(public, reviews, "O", response_ids)
    rows = _analysis_rows(build, reviews, reviews, reviews)
    return _write_analysis(rows, output, {
        "schema_version": 1, "mode": "single_root", "review_root": str(reviews),
        "run_identity_sha256": _value_sha(run_identity),
    })


def analyse_combined(base_build: Path, corrected_build: Path, base_reviews: Path,
                     corrected_o_reviews: Path, output: Path) -> dict:
    """Combine only base one-shot/N with corrected O; the base O tree is never read."""
    base_public = base_build / "public"
    corrected_public, corrected_identity = _review_preflight(corrected_build)
    verify_unified(base_build)
    equivalence = audit_build_equivalence(base_build, corrected_build)
    base_build_identity = json.loads((base_public / "build_identity.json").read_text())
    base_identity = _verify_review_identity(
        base_reviews, _run_identity(base_build, base_public, base_build_identity),
    )
    corrected_run_identity = _verify_review_identity(
        corrected_o_reviews,
        _corrected_o_run_identity(corrected_build, corrected_public, corrected_identity),
    )
    for field in ("system_prompt_sha256", "answer_schema_sha256", "model", "effort"):
        if base_identity[field] != corrected_run_identity[field]:
            raise ValueError(f"base and corrected O final-review contract differs: {field}")
    _verify_stage(base_reviews, "one_shot")
    _verify_stage(base_reviews, "N")
    _verify_stage(corrected_o_reviews, "O")
    if verify_manifest(corrected_o_reviews):
        raise ValueError("corrected O review root manifest is missing or changed")
    response_ids = _validate_one_shot_stage(base_public, base_reviews)
    _validate_interactive_stage(base_public, base_reviews, "N", response_ids)
    _validate_corrected_o_stage(corrected_public, corrected_o_reviews, response_ids)
    rows = _analysis_rows(corrected_build, base_reviews, base_reviews, corrected_o_reviews)
    if len(rows) != 1344:
        raise ValueError(f"combined analysis requires exactly 1,344 evaluations, found {len(rows)}")
    return _write_analysis(rows, output, {
        "schema_version": 1, "mode": "base_one_shot_N_plus_corrected_O",
        "base_review_root": str(base_reviews),
        "base_run_identity_sha256": _value_sha(base_identity),
        "base_one_shot_manifest_sha256": _sha(base_reviews / "one_shot/MANIFEST.sha256.json"),
        "base_N_manifest_sha256": _sha(base_reviews / "N/MANIFEST.sha256.json"),
        "base_O_excluded": True,
        "corrected_O_review_root": str(corrected_o_reviews),
        "corrected_O_run_identity_sha256": _value_sha(corrected_run_identity),
        "corrected_O_root_manifest_sha256": _sha(corrected_o_reviews / "MANIFEST.sha256.json"),
        "corrected_build_manifest_sha256": _sha(corrected_build / "MANIFEST.sha256.json"),
        "equivalence_audit": equivalence,
        "system_prompt_sha256": corrected_run_identity["system_prompt_sha256"],
        "answer_schema_sha256": corrected_run_identity["answer_schema_sha256"],
    })


def _empty_answer() -> dict:
    return {"fault_occurred": False, "residual_harm_present": False, "fault_class": None,
            "root_cause_source_locations": [], "root_cause_event_indices": [],
            "historically_affected_artifacts": [], "restored_artifacts": [],
            "residual_harmful_artifacts": []}


def fake_review(package, out_path, system_prompt, schema, validate, model, effort):
    identity = request_identity(package, model, effort, system_prompt, schema, cli_version="fake-codex-cli")
    if out_path.exists():
        saved = json.loads(out_path.read_text())
        if any(saved.get(key) != value for key, value in identity.items()):
            raise ValueError("fake review resume identity differs")
        return saved
    if schema is ANSWER_SCHEMA_V2:
        answer = _empty_answer()
    elif "answer" in schema["properties"]["action"].get("enum", []):
        answer = {"action": "answer", "node": None, "note": "deterministic fake early stop"}
    else:
        nodes = schema["properties"]["node"].get("enum", ["call:999999"])
        answer = {"action": "expand", "node": nodes[0], "note": "deterministic fake expansion"}
    validate(answer)
    response_id = "fake-" + hashlib.sha256((str(out_path) + identity["rendered_prompt_sha256"]).encode()).hexdigest()[:24]
    record = {**identity, "answer": answer, "response_id": response_id, "thread_id": response_id,
              "terminal_status": "completed", "status": "completed", "observed_tool_use": False,
              "usage": {"input_tokens": len(package.split()), "output_tokens": 8}, "wall_seconds": 0.0,
              "package_reviewer_tokens": len(package.split()), "package_characters": len(package),
              "package_utf8_bytes": len(package.encode()), "previous_response_id": None,
              "conversation": None, "session": None}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    attempt = {**identity, "attempt": 1, "response_id": response_id,
               "thread_id": response_id, "terminal_status": "completed",
               "status": "completed", "observed_tool_use": False,
               "usage": record["usage"], "wall_seconds": 0.0}
    _write_json(out_path.with_name(out_path.stem + ".attempt-1.json"), attempt)
    out_path.with_name(out_path.stem + ".attempt-1.codex.jsonl").write_text(
        json.dumps({"type": "thread.started", "thread_id": response_id}) + "\n"
    )
    _write_json(out_path, record)
    return record


def fake_run(build: Path, reviews: Path, analysis: Path) -> dict:
    one = run_one_shot(build, reviews, fake_review, live=False)
    n = run_interactive(build, reviews, "N", fake_review, live=False)
    o = run_interactive(build, reviews, "O", fake_review, live=False)
    result = analyse(build, reviews, analysis)
    return {"one_shot": one, "N": n, "O": o, "analysis": result, "real_reviewer_calls": 0}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("one-shot", "N"):
        command = sub.add_parser(name)
        command.add_argument("--build", type=Path, required=True)
        command.add_argument("--reviews", type=Path, required=True)
    corrected_o = sub.add_parser("corrected-O")
    corrected_o.add_argument("--build", type=Path, required=True)
    corrected_o.add_argument("--reviews", type=Path, required=True)
    analysis = sub.add_parser("analyse")
    analysis.add_argument("--build", type=Path, required=True)
    analysis.add_argument("--reviews", type=Path, required=True)
    analysis.add_argument("--out", type=Path, required=True)
    combined = sub.add_parser("analyse-combined")
    combined.add_argument("--base-build", type=Path, required=True)
    combined.add_argument("--corrected-build", type=Path, required=True)
    combined.add_argument("--base-reviews", type=Path, required=True)
    combined.add_argument("--corrected-o-reviews", type=Path, required=True)
    combined.add_argument("--out", type=Path, required=True)
    equivalence = sub.add_parser("audit-equivalence")
    equivalence.add_argument("--base-build", type=Path, required=True)
    equivalence.add_argument("--corrected-build", type=Path, required=True)
    equivalence.add_argument("--out", type=Path, required=True)
    fake = sub.add_parser("fake-run")
    fake.add_argument("--build", type=Path, required=True)
    fake.add_argument("--reviews", type=Path, required=True)
    fake.add_argument("--analysis", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "one-shot": result = run_one_shot(args.build, args.reviews)
    elif args.command == "N": result = run_interactive(args.build, args.reviews, "N")
    elif args.command == "corrected-O": result = run_corrected_o(args.build, args.reviews)
    elif args.command == "analyse": result = analyse(args.build, args.reviews, args.out)
    elif args.command == "analyse-combined":
        result = analyse_combined(
            args.base_build, args.corrected_build, args.base_reviews,
            args.corrected_o_reviews, args.out,
        )
    elif args.command == "audit-equivalence":
        result = audit_build_equivalence(args.base_build, args.corrected_build, args.out)
    else:
        result = fake_run(args.build, args.reviews, args.analysis)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
