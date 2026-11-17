"""V2 reviewer execution and deterministic grouped analysis; never used by the dry run."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from rdr.freeze import verify_manifest, write_manifest
from rdr.stepwise import MODES, explore, explored_graph
from rdr.v2_etiq_export import ALL_ETIQ_CONDITIONS
from rdr.v2_packager import ARMS_V2, _common_with_calls, _flat_graph
from rdr.v2_provenance import verify_current_code_snapshot
from rdr.v2_openai_runner import (REVIEWER_EFFORT, REVIEWER_MODEL, ReviewError,
                                  codex_login_preflight, review)
from rdr.v2_schema import TraceV2, TruthV2, load_trace, load_truth
from rdr.v2_scorer import ANSWER_SCHEMA_V2, score_v2, validate_answer_v2


SYSTEM_PROMPT_V2 = (
    "Use only the evidence included in this review package. Do not inspect or use information from outside the "
    "package.\n\n"
    "Make two independent decisions: whether a fault caused harmful behaviour at any point during execution, "
    "and whether any harmful state or artifact still exists at the end of the recorded execution.\n\n"
    "Identify the root cause of the harmful behaviour. A root cause is the source defect, incorrect action, or "
    "abnormal runtime condition without which the harmful outcome would not have occurred. Report all causal "
    "source locations as file:line values in root_cause_source_locations. Report all causal action or runtime "
    "events by their event indices in root_cause_event_indices.\n\n"
    "Include multiple source locations or event indices when the root cause has multiple necessary components. "
    "Do not select a later propagation, state-write, notification, or repair event merely because that is where "
    "the harm became visible. Include such an event as a root cause only when the event itself introduced a "
    "necessary harmful action or runtime condition. If the supplied evidence does not support a source location "
    "or causal event index, return an empty list for that field.\n\n"
    "Classify the fault using exactly one of the following definitions:\n"
    "- action: the executed source is unchanged, but an operation or API call is executed with an incorrect "
    "argument or action.\n"
    "- source: a defect in the executed source causes harm under otherwise normal runtime behaviour.\n"
    "- runtime: the source is unchanged, but an abnormal response, failure, ordering, concurrent update, "
    "filesystem result, clock, permission, or dependency behaviour causes harm.\n"
    "- mixed: source and runtime faults occur in the same execution, and each is independently harmful.\n"
    "- interaction: a source condition and runtime condition occur together; neither is harmful alone, but "
    "their combination is harmful.\n"
    "- amplified: at least one component is harmful alone, and combining it with another component creates "
    "additional harm or greater severity.\n\n"
    "Use null for fault_class when no harmful fault occurred. Otherwise, return only one of the defined category "
    "names, not a descriptive fault name.\n\n"
    "Report historically_affected_artifacts as artifacts that entered a harmful or incorrect state at any point "
    "during execution. Report restored_artifacts as the subset of those artifacts that were later returned to a "
    "correct state. Report residual_harmful_artifacts as artifacts that remain harmful or incorrect at the end "
    "of the recorded execution.\n\n"
    "Later corrective actions do not erase the historical fault. If all harmful state and artifacts are "
    "restored, return fault_occurred=true and residual_harm_present=false. If any harmful state or artifact "
    "remains, return fault_occurred=true and residual_harm_present=true.\n\n"
    "When no harmful fault occurred, return fault_occurred=false, residual_harm_present=false, fault_class=null, "
    "and empty root-cause and artifact lists.\n\n"
    "Base every claim on evidence visible in the package. Do not invent unseen events, private labels, source "
    "lines, or artifact identifiers. Reply only with JSON matching the schema."
)
JOB_ORDER_SEED = 20261108
REVIEWER_PROVENANCE = Path("runs/v2/reviewer-code-v6-codex-cli-final-20261111")
TRANSPORT_DISCLOSURE = {
    "reviewer_transport": "codex_cli",
    "reviewer_harness": "codex_agent",
    "tool_surface_available": True,
    "observed_tool_use": False,
    "fabio_evidence_arm_compatible": True,
    "fabio_transport_replication": False,
}
def _require_registered_reviewer(model: str, effort: str) -> None:
    if (model, effort) != (REVIEWER_MODEL, REVIEWER_EFFORT):
        raise ValueError(f"active V2 reviewer is fixed to {REVIEWER_MODEL}/{REVIEWER_EFFORT}")


def clean_control_metrics(rows: list[dict]) -> dict:
    def interval(successes: int, n: int) -> list[float] | None:
        if not n:
            return None
        z = 1.959963984540054
        center = (successes / n + z * z / (2 * n)) / (1 + z * z / n)
        proportion = successes / n
        half = z * (proportion * (1 - proportion) / n + z * z / (4 * n * n)) ** 0.5 / (1 + z * z / n)
        return [max(0.0, center - half), min(1.0, center + half)]
    clean = [row for row in rows if not row["truth_fault_occurred"]]
    by_arm = {}
    for arm in sorted({row["arm"] for row in clean}):
        cell = [row for row in clean if row["arm"] == arm]
        false_alarms = sum(row["false_alarm"] for row in cell)
        by_arm[arm] = {
            "n": len(cell), "false_positives": false_alarms,
            "false_positive_rate": false_alarms / len(cell),
            "false_positive_rate_wilson_95": interval(false_alarms, len(cell)),
            "specificity": 1 - false_alarms / len(cell),
            "inference": "descriptive_only" if len(cell) < 30 else "interval_reported",
            "false_fault_class_claims": sum(row["false_fault_class_claim"] for row in cell),
        }
    false_alarms = sum(row["false_alarm"] for row in clean)
    return {
        "n": len(clean), "false_positives": false_alarms,
        "false_positive_rate": false_alarms / len(clean) if clean else None,
        "false_positive_rate_wilson_95": interval(false_alarms, len(clean)),
        "specificity": 1 - false_alarms / len(clean) if clean else None,
        "false_fault_class_claims": sum(row["false_fault_class_claim"] for row in clean),
        "by_arm": by_arm,
    }


def plan_jobs(public_root: Path, seed: int = JOB_ORDER_SEED) -> list[tuple[str, str, Path]]:
    jobs = []
    for instance in sorted((public_root / "instances").iterdir()):
        if not instance.is_dir():
            continue
        for package in sorted((instance / "packages").glob("*.txt")):
            jobs.append((instance.name, package.stem, package))
    random.Random(seed).shuffle(jobs)
    return jobs


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_stage_ledger(reviews_dir: Path) -> dict:
    path = reviews_dir / "review_stages.json"
    if not path.is_file():
        return {"schema_version": 1, "stages": {}}
    ledger = json.loads(path.read_text())
    if ledger.get("schema_version") != 1 or not isinstance(ledger.get("stages"), dict):
        raise RuntimeError("invalid review stage ledger")
    return ledger


def _reviewer_snapshot_id(reviewer_provenance: Path,
                          repository_root: Path | None = None) -> str:
    problems = verify_current_code_snapshot(reviewer_provenance, repository_root)
    if problems:
        raise RuntimeError(f"current reviewer code differs from frozen snapshot: {problems[:5]}")
    record = json.loads((reviewer_provenance / "code_provenance.json").read_text())
    if not record.get("snapshot_id"):
        raise RuntimeError("reviewer code snapshot has no snapshot_id")
    return record["snapshot_id"]


def _bind_code_snapshot(public_root: Path, reviews_dir: Path,
                        reviewer_provenance: Path = REVIEWER_PROVENANCE) -> dict:
    identity = json.loads((public_root / "build_identity.json").read_text())
    build_snapshot_id = identity["code_snapshot_id"]
    reviewer_snapshot_id = _reviewer_snapshot_id(reviewer_provenance)
    ledger = _load_stage_ledger(reviews_dir)
    expected = {
        "build_code_snapshot_id": build_snapshot_id,
        "reviewer_code_snapshot_id": reviewer_snapshot_id,
        "reviewer_provenance": str(reviewer_provenance),
    }
    differing = [key for key, value in expected.items() if ledger.get(key) not in (None, value)]
    if differing:
        raise RuntimeError(f"review result root is bound to different provenance: {differing}")
    if any(key not in ledger for key in expected):
        ledger.update(expected)
        reviews_dir.mkdir(parents=True, exist_ok=True)
        (reviews_dir / "review_stages.json").write_text(json.dumps(ledger, indent=2, sort_keys=True))
    return expected


def _verify_stage(reviews_dir: Path, stage: str) -> None:
    ledger = _load_stage_ledger(reviews_dir)
    recorded = ledger["stages"].get(stage)
    if not recorded:
        raise RuntimeError(f"required review stage {stage} is not complete")
    stage_root = reviews_dir / stage
    problems = verify_manifest(stage_root)
    if problems:
        raise RuntimeError(f"review stage {stage} changed: {problems[:5]}")
    manifest = stage_root / "MANIFEST.sha256.json"
    if _sha(manifest) != recorded.get("manifest_sha256"):
        raise RuntimeError(f"review stage {stage} manifest differs from ledger")


def _record_stage(reviews_dir: Path, stage: str) -> None:
    stage_root = reviews_dir / stage
    manifest = write_manifest(stage_root)
    ledger = _load_stage_ledger(reviews_dir)
    existing = ledger["stages"].get(stage)
    record = {"manifest_sha256": _sha(manifest), "result_files": len(json.loads(manifest.read_text()))}
    if existing and existing != record:
        raise RuntimeError(f"refusing to overwrite changed {stage} stage ledger entry")
    ledger["stages"][stage] = record
    (reviews_dir / "review_stages.json").write_text(json.dumps(ledger, indent=2, sort_keys=True))


def _interactive_schedule(public_root: Path, seed: int) -> list[Path]:
    instances = sorted(path for path in (public_root / "instances").iterdir() if path.is_dir())
    random.Random(seed).shuffle(instances)
    computed = []
    for position, instance in enumerate(instances):
        base = public_root / "interactive" / instance.name
        computed.append({
            "position": position,
            "instance_id": instance.name,
            "walk_sha256": _sha(base / "walk.json"),
            "N_initial_sha256": _sha(base / "N.initial.txt"),
            "O_initial_sha256": _sha(base / "O.initial.txt"),
        })
    registered = json.loads((public_root / "interactive_job_order.json").read_text())
    if registered.get("seed") != seed or registered.get("instances") != computed:
        raise RuntimeError("computed interactive order differs from frozen public order")
    return instances


def run_reviews(public_root: Path, reviews_dir: Path, model: str, effort: str,
                seed: int = JOB_ORDER_SEED,
                reviewer_provenance: Path = REVIEWER_PROVENANCE) -> dict:
    _require_registered_reviewer(model, effort)
    problems = verify_manifest(public_root)
    if problems:
        raise RuntimeError(f"freeze check failed: {problems[:5]}")
    provenance = _bind_code_snapshot(public_root, reviews_dir, reviewer_provenance)
    jobs = plan_jobs(public_root, seed)
    preflight = codex_login_preflight()
    if "one_shot" in _load_stage_ledger(reviews_dir)["stages"]:
        _verify_stage(reviews_dir, "one_shot")
    stage_dir = reviews_dir / "one_shot"
    stage_dir.mkdir(parents=True, exist_ok=True)
    frozen_order = [{"position": i, "instance_id": item[0], "arm": item[1],
                     "package_sha256": __import__("hashlib").sha256(item[2].read_bytes()).hexdigest()}
                    for i, item in enumerate(jobs)]
    registered = json.loads((public_root / "one_shot_job_order.json").read_text())
    if registered["jobs"] != frozen_order:
        raise RuntimeError("computed reviewer job order differs from frozen public order")
    order_path = stage_dir / "frozen_job_order.json"
    if order_path.exists() and json.loads(order_path.read_text()) != registered:
        raise RuntimeError("frozen reviewer job order differs")
    order_path.write_text(json.dumps(registered, indent=2, sort_keys=True))
    done = resumed = 0
    response_ids = set()
    for instance_id, arm, package_path in jobs:
        output = stage_dir / instance_id / f"{arm}.json"
        existed = output.exists()
        record = review(package_path.read_text(), output, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                        validate_answer_v2, model, effort)
        response_id = record.get("response_id")
        if not response_id or response_id in response_ids:
            raise ReviewError("review responses require unique non-empty response IDs")
        response_ids.add(response_id)
        resumed += int(existed)
        done += int(not existed)
    _record_stage(reviews_dir, "one_shot")
    return {"planned": len(jobs), "done": done, "resumed": resumed, "model": model,
            "effort": effort, "preflight": preflight, "provenance": provenance,
            **TRANSPORT_DISCLOSURE}


def smoke_review(public_root: Path, output_dir: Path, instance_id: str, arm: str,
                 model: str, effort: str,
                 reviewer_provenance: Path = REVIEWER_PROVENANCE) -> dict:
    """Run one explicitly named one-shot package outside all experimental review directories."""
    if not output_dir.name.startswith("smoke-"):
        raise ValueError("smoke output directory name must start with smoke-")
    _require_registered_reviewer(model, effort)
    problems = verify_manifest(public_root)
    if problems:
        raise RuntimeError(f"freeze check failed: {problems[:5]}")
    package = public_root / "instances" / instance_id / "packages" / f"{arm}.txt"
    if not package.is_file():
        raise FileNotFoundError(f"named one-shot package does not exist: {package}")
    reviewer_snapshot_id = _reviewer_snapshot_id(reviewer_provenance)
    output_dir.mkdir(parents=True, exist_ok=True)
    record_path = output_dir / "review.json"
    text = package.read_text()
    try:
        preflight = codex_login_preflight()
        record = review(text, record_path, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                        validate_answer_v2, model, effort)
        if not record.get("usage"):
            raise ReviewError("smoke response has empty usage")
        if (record.get("observed_tool_use") is not False
                or record.get("previous_response_id") is not None
                or record.get("conversation") is not None or record.get("session") is not None):
            raise ReviewError("smoke response identity is not stateless and tool-free")
        summary = {
            "status": "passed", "excluded_from_experiment_analysis": True,
            "instance_id": instance_id, "arm": arm, "requested_model": model,
            "served_model": record.get("served_model"),
            "served_model_verification": record["served_model_verification"], "effort": effort,
            "actual_usage": record.get("usage", {}), "context_error": None,
            "response_id": record["response_id"], "event_types": record["event_types"],
            "item_types": record["item_types"], "preflight": preflight,
            "reviewer_code_snapshot_id": reviewer_snapshot_id,
            "reviewer_provenance": str(reviewer_provenance),
            "previous_response_id": record["previous_response_id"],
            "conversation": record["conversation"], "session": record["session"],
            "system_prompt_sha256": record["system_prompt_sha256"],
            "rendered_prompt_sha256": record["rendered_prompt_sha256"],
            "schema_sha256": record["schema_sha256"],
            "package_sha256": record["package_sha256"],
            "package_reviewer_tokens": record["package_reviewer_tokens"],
            "package_utf8_bytes": record["package_utf8_bytes"],
            **TRANSPORT_DISCLOSURE,
        }
    except ReviewError as error:
        summary = {
            "status": "failed", "excluded_from_experiment_analysis": True,
            "instance_id": instance_id, "arm": arm, "requested_model": model,
            "served_model": None, "effort": effort, "actual_usage": {},
            "context_error": str(error),
            "reviewer_code_snapshot_id": reviewer_snapshot_id,
            "reviewer_provenance": str(reviewer_provenance),
            **TRANSPORT_DISCLOSURE,
        }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    write_manifest(output_dir)
    return summary


def run_interactive_reviews(public_root: Path, reviews_dir: Path, arm: str,
                            model: str, effort: str, limit: int | None = None,
                            seed: int = JOB_ORDER_SEED,
                            reviewer_provenance: Path = REVIEWER_PROVENANCE) -> dict:
    if arm not in {"N", "O"}:
        raise ValueError("interactive arm must be N or O")
    _require_registered_reviewer(model, effort)
    problems = verify_manifest(public_root)
    if problems:
        raise RuntimeError(f"freeze check failed: {problems[:5]}")
    if limit is not None:
        raise ValueError("frozen interactive execution does not permit a partial instance schedule")
    provenance = _bind_code_snapshot(public_root, reviews_dir, reviewer_provenance)
    preflight = codex_login_preflight()
    _verify_stage(reviews_dir, "one_shot")
    if arm == "O":
        _verify_stage(reviews_dir, "N")
    elif "N" in _load_stage_ledger(reviews_dir)["stages"]:
        _verify_stage(reviews_dir, "N")
    stage_dir = reviews_dir / arm
    stage_dir.mkdir(parents=True, exist_ok=True)
    instances = _interactive_schedule(public_root, seed)
    done = 0
    response_ids = set()
    for instance in instances:
        walk = json.loads((public_root / "interactive" / instance.name / "walk.json").read_text())
        trace = TraceV2.from_dict(walk["trace"])
        symptom = walk["reported_artifact"]
        execution = walk["execution_graph"]
        flat = _flat_graph(execution)
        mode_prompt, mode_schema, mode_validate = MODES[arm]
        transcript = []

        def ask(kind: str, package: str, round_number: int):
            if kind == "step" and round_number == 1:
                frozen_initial = public_root / "interactive" / instance.name / f"{arm}.initial.txt"
                if package != frozen_initial.read_text():
                    raise RuntimeError(f"{instance.name} arm {arm}: initial walk package differs from frozen build")
            if kind == "step":
                output = stage_dir / instance.name / f"{arm}.step{round_number}.json"
                record = review(package, output, mode_prompt, mode_schema, mode_validate, model, effort)
            else:
                output = stage_dir / instance.name / f"{arm}.json"
                record = review(package, output, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                                validate_answer_v2, model, effort)
            response_id = record.get("response_id")
            if not response_id or response_id in response_ids:
                raise ReviewError("interactive review responses require unique non-empty response IDs")
            response_ids.add(response_id)
            transcript.append({
                "kind": kind, "round": round_number, "artifact": str(output),
                "answer": record["answer"], "usage": record.get("usage", {}),
                "wall_seconds": record.get("wall_seconds"),
                "response_id": record.get("response_id"),
                "served_model_verification": record.get("served_model_verification"),
            })
            return record["answer"]

        result = explore(trace.to_v1_observed(), symptom, instance.name, None, ask,
                         max_expansions=6, graph=flat, common_header=_common_with_calls(trace))
        view = explored_graph(flat, result["expanded"])
        total_nodes = len(flat.call_nodes) + len(flat.record_nodes)
        path = {key: value for key, value in result.items() if key != "record"}
        path["transcript"] = transcript
        path["total_wall_seconds"] = sum(item["wall_seconds"] or 0 for item in transcript)
        path["token_usage"] = {
            key: sum(item["usage"].get(key, 0) for item in transcript
                     if isinstance(item["usage"].get(key, 0), (int, float)))
            for key in sorted({key for item in transcript for key in item["usage"]})
        }
        path["revealed_graph_fraction"] = (
            (len(view.call_nodes) + len(view.record_nodes)) / total_nodes if total_nodes else 0
        )
        output = stage_dir / instance.name / f"{arm}.path.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(path, indent=2, sort_keys=True))
        done += 1
    _record_stage(reviews_dir, arm)
    if arm == "O":
        write_manifest(reviews_dir)
    return {"arm": arm, "planned": len(instances), "done": done, "model": model,
            "effort": effort, "preflight": preflight, "provenance": provenance,
            **TRANSPORT_DISCLOSURE}


def analyse(build_root: Path, reviews_dir: Path, output_dir: Path,
            reviewer_provenance: Path = REVIEWER_PROVENANCE) -> dict:
    reviewer_snapshot = _reviewer_snapshot_id(reviewer_provenance)
    public_root, private_root = build_root / "public", build_root / "private"
    for root in (build_root, reviews_dir):
        problems = verify_manifest(root)
        if problems:
            raise RuntimeError(f"freeze check failed for {root}: {problems[:5]}")
    for stage in ("one_shot", "N", "O"):
        _verify_stage(reviews_dir, stage)
    build_snapshot = json.loads((public_root / "build_identity.json").read_text())["code_snapshot_id"]
    ledger = _load_stage_ledger(reviews_dir)
    if ledger.get("build_code_snapshot_id") != build_snapshot:
        raise RuntimeError("analysis build snapshot differs from reviewer stage ledger")
    if ledger.get("reviewer_code_snapshot_id") != reviewer_snapshot:
        raise RuntimeError("analysis reviewer snapshot differs from reviewer stage ledger")
    rows = []
    package_rows = {
        (row["instance_id"], row["arm"]): row
        for row in (
            json.loads(line) for line in (public_root / "package_manifest.jsonl").read_text().splitlines()
        )
    }
    for instance_id, arm, _ in sorted(plan_jobs(public_root, seed=0)):
        truth = load_truth(private_root / "truth" / f"{instance_id}.json")
        if not isinstance(truth, TruthV2):
            raise ValueError(f"not v2 truth for instance {instance_id}")
        review = json.loads((reviews_dir / "one_shot" / instance_id / f"{arm}.json").read_text())
        manifest_row = package_rows[(instance_id, arm)]
        rows.append({
            "arm": arm,
            "experimental_condition": manifest_row.get("experimental_condition"),
            "actual_reviewer_input_tokens": review.get("input_tokens"),
            **score_v2(review["answer"], truth), **{
            key: package_rows[(instance_id, arm)][key]
            for key in ("tokens", "utf8_bytes", "characters", "lines")
        }})
    for instance in sorted(path for path in (public_root / "instances").iterdir() if path.is_dir()):
        truth = load_truth(private_root / "truth" / f"{instance.name}.json")
        if not isinstance(truth, TruthV2):
            raise ValueError(f"not v2 truth: {instance}")
        for arm in ("N", "O"):
            review_path = reviews_dir / arm / instance.name / f"{arm}.json"
            if not review_path.is_file():
                continue
            review = json.loads(review_path.read_text())
            rows.append({"arm": arm, **score_v2(review["answer"], truth),
                         "tokens": review["package_reviewer_tokens"],
                         "utf8_bytes": review["package_utf8_bytes"],
                         "characters": review["package_characters"],
                         "lines": review["package_lines"]})
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "scores.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    fields = ("fault_id", "fault_class", "repair", "author", "injection_channel", "arm",
              "experimental_condition",
              "task_cluster", "generator_cluster")
    grouped = {}
    for field in fields:
        cells = defaultdict(list)
        for row in rows:
            cells[str(row.get(field))].append(row)
        grouped[field] = {
            value: {
                "n": len(cell),
                "detection_accuracy": sum(bool(row["detection_correct"]) for row in cell) / len(cell),
                "median_tokens": sorted(row["tokens"] for row in cell)[len(cell) // 2],
            }
            for value, cell in sorted(cells.items())
        }
    summary = {
        "rows": len(rows), "grouped": grouped, "size_sensitivity_field": "tokens",
        "actual_reviewer_input_token_field": "actual_reviewer_input_tokens",
        "size_preregistered_as_covariate": True,
        "clean_controls": clean_control_metrics(rows),
        "build_code_snapshot_id": build_snapshot,
        "reviewer_code_snapshot_id": reviewer_snapshot,
        **TRANSPORT_DISCLOSURE,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    write_manifest(output_dir)
    return summary


def write_deterministic_fake_reviews(public_root: Path, reviews_dir: Path,
                                     reviewer_provenance: Path = REVIEWER_PROVENANCE) -> dict:
    """Create public-input-only records for the analysis join test; never an experiment arm."""
    if reviews_dir.exists():
        raise FileExistsError(reviews_dir)
    _bind_code_snapshot(public_root, reviews_dir, reviewer_provenance)
    answer = {
        "fault_occurred": False, "residual_harm_present": False, "fault_class": None,
        "root_cause_source_locations": [], "root_cause_event_indices": [],
        "historically_affected_artifacts": [], "restored_artifacts": [],
        "residual_harmful_artifacts": [],
    }
    one_shot = reviews_dir / "one_shot"
    for instance_id, arm, package in plan_jobs(public_root):
        text = package.read_text()
        output = one_shot / instance_id / f"{arm}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "answer": answer, "response_id": f"fake-{instance_id}-{arm}",
            "package_reviewer_tokens": len(text.split()), "package_utf8_bytes": len(text.encode()),
            "package_characters": len(text), "package_lines": len(text.splitlines()),
        }, indent=2, sort_keys=True))
    _record_stage(reviews_dir, "one_shot")
    for arm in ("N", "O"):
        for instance in _interactive_schedule(public_root, JOB_ORDER_SEED):
            text = (public_root / "interactive" / instance.name / f"{arm}.initial.txt").read_text()
            output = reviews_dir / arm / instance.name / f"{arm}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "answer": answer, "response_id": f"fake-{instance.name}-{arm}",
                "package_reviewer_tokens": len(text.split()), "package_utf8_bytes": len(text.encode()),
                "package_characters": len(text), "package_lines": len(text.splitlines()),
            }, indent=2, sort_keys=True))
        _record_stage(reviews_dir, arm)
    write_manifest(reviews_dir)
    return {"one_shot": len(plan_jobs(public_root)),
            "interactive": 2 * len(_interactive_schedule(public_root, JOB_ORDER_SEED)),
            "private_truth_accessed_during_review": False}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--instances", type=Path, required=True)
    run.add_argument("--reviews", type=Path, required=True)
    run.add_argument("--model", default=REVIEWER_MODEL)
    run.add_argument("--effort", default=REVIEWER_EFFORT)
    run.add_argument("--reviewer-provenance", type=Path, default=REVIEWER_PROVENANCE)
    analysis = sub.add_parser("analyse")
    analysis.add_argument("--instances", type=Path, required=True)
    analysis.add_argument("--reviews", type=Path, required=True)
    analysis.add_argument("--out", type=Path, required=True)
    analysis.add_argument("--reviewer-provenance", type=Path, default=REVIEWER_PROVENANCE)
    interactive = sub.add_parser("run-interactive")
    interactive.add_argument("--instances", type=Path, required=True)
    interactive.add_argument("--reviews", type=Path, required=True)
    interactive.add_argument("--arm", choices=("N", "O"), required=True)
    interactive.add_argument("--model", default=REVIEWER_MODEL)
    interactive.add_argument("--effort", default=REVIEWER_EFFORT)
    interactive.add_argument("--reviewer-provenance", type=Path, default=REVIEWER_PROVENANCE)
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--instances", type=Path, required=True)
    smoke.add_argument("--out", type=Path, required=True)
    smoke.add_argument("--instance", required=True)
    smoke.add_argument("--arm", choices=(
        *(arm for arm in ARMS_V2 if arm not in "NO"),
        *ALL_ETIQ_CONDITIONS,
    ),
                       required=True)
    smoke.add_argument("--model", default=REVIEWER_MODEL)
    smoke.add_argument("--effort", default=REVIEWER_EFFORT)
    smoke.add_argument("--reviewer-provenance", type=Path, default=REVIEWER_PROVENANCE)
    dry_analysis = sub.add_parser("dry-analysis")
    dry_analysis.add_argument("--instances", type=Path, required=True)
    dry_analysis.add_argument("--reviews", type=Path, required=True)
    dry_analysis.add_argument("--out", type=Path, required=True)
    dry_analysis.add_argument("--reviewer-provenance", type=Path, default=REVIEWER_PROVENANCE)
    interactive.add_argument("--limit", type=int)
    interactive.add_argument("--seed", type=int, default=20261108)
    args = parser.parse_args(argv)
    if args.command == "run":
        result = run_reviews(args.instances, args.reviews, args.model, args.effort,
                             reviewer_provenance=args.reviewer_provenance)
    elif args.command == "run-interactive":
        result = run_interactive_reviews(args.instances, args.reviews, args.arm, args.model, args.effort,
                                         args.limit, args.seed, args.reviewer_provenance)
    elif args.command == "smoke":
        result = smoke_review(args.instances, args.out, args.instance, args.arm, args.model, args.effort,
                              args.reviewer_provenance)
    elif args.command == "dry-analysis":
        fake = write_deterministic_fake_reviews(args.instances / "public", args.reviews,
                                                args.reviewer_provenance)
        result = {"fake_records": fake, "analysis": analyse(
            args.instances, args.reviews, args.out, args.reviewer_provenance)}
    else:
        result = analyse(args.instances, args.reviews, args.out, args.reviewer_provenance)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "smoke" and result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
