from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .codex_runner import CodexRunner
from .etiq_executor import EtiqExecution, EtiqExecutor
from .job_store import JobStore
from .records import (
    ContextArtifact,
    GeneratedFile,
    GeneratedPipeline,
    jsonable,
    new_id,
    stable_hash,
)
from .repair import repair_diff, select_repair_target, source_scope, validate_repair_scope
from .review import build_review_sections, build_review_units
from .review import inspect_artifact, validate_expansion, validate_review
from .review_experiment import (
    EXPERIMENT_MODES,
    _issue_keys,
    build_experiment_package,
)
from .workflow import parse_pipeline_result, review_decisions


def load_pipeline(store: JobStore, run_dir: Path) -> GeneratedPipeline:
    manifest = store.read_json(run_dir / "pipeline-manifest.json")
    return GeneratedPipeline(
        entry_file=str(manifest["entry_file"]),
        files=[
            GeneratedFile(
                str(path),
                (run_dir / "pipeline" / str(path)).read_text(encoding="utf-8"),
            )
            for path in manifest["file_hashes"]
        ],
        review_boundaries=list(manifest.get("review_boundaries", [])),
    )


def save_review_layout(
    store: JobStore,
    execution: EtiqExecution,
    pipeline: GeneratedPipeline,
) -> tuple[list[Any], list[ReviewSection]]:
    units = build_review_units(
        execution.snapshot,
        declared_boundaries=pipeline.review_boundaries,
    )
    sections = build_review_sections(units)
    store.write_json(execution.run_dir / "review-boundaries.json", units)
    store.write_json(execution.run_dir / "review-sections.json", sections)
    return units, sections


def invoke_json(
    codex: CodexRunner,
    *,
    job_id: str,
    purpose: str,
    prompt: str,
    schema: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    result = codex.run(
        job_id=job_id,
        job_type="controlled_experiment",
        purpose=purpose,
        prompt=prompt,
        output_schema=schema,
        artifacts=[
            ContextArtifact(
                ref=f"controlled:{purpose}",
                content_hash=stable_hash(context),
                delivery="embedded",
                purpose="isolated_controlled_experiment",
                content=context,
            )
        ],
    )
    return result.payload, {
        "invocation_id": result.invocation_id,
        "input_tokens": int(result.usage.input_tokens or 0),
        "cached_input_tokens": int(result.usage.extra.get("cached_input_tokens") or 0),
        "output_tokens": int(result.usage.output_tokens or 0),
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def review_execution(
    *,
    repo_root: Path,
    store: JobStore,
    codex: CodexRunner,
    job_id: str,
    mode: str,
    execution: EtiqExecution,
    pipeline: GeneratedPipeline,
    history_job_ids: list[str],
    blind: bool = False,
) -> tuple[
    list[dict[str, Any]],
    list[Any],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    units, sections = save_review_layout(store, execution, pipeline)
    schema = json.loads((repo_root / "schemas" / "review.schema.json").read_text())
    instructions = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    template = (repo_root / "prompts" / "review_experiment.md").read_text(
        encoding="utf-8"
    )
    reviews: list[dict[str, Any]] = []
    usage: list[dict[str, Any]] = []
    package_by_unit: dict[str, dict[str, Any]] = {}
    for section in sections:
        assigned = {
            unit.unit_id: unit
            for unit in units
            if unit.unit_id in section.assigned_unit_ids
        }
        expanded = {unit_id: [] for unit_id in section.context_unit_ids}
        inspections = {unit_id: [] for unit_id in section.context_unit_ids}
        expansion_round = 0
        receipt_retries = 0
        validation_errors: list[str] = []
        while True:
            package = build_experiment_package(
                mode,
                store=store,
                run_dir=execution.run_dir,
                snapshot=execution.snapshot,
                units=units,
                section=section,
                history_job_ids=history_job_ids,
                expanded_prefixes_by_unit=expanded,
                artifact_inspections_by_unit=inspections,
            )
            if validation_errors:
                package["review_validation_errors"] = validation_errors
            context = {
                "review_package": package,
                "reviewer_role": (
                    "blind_final_judge" if blind else "isolated_branch_reviewer"
                ),
            }
            prompt = (
                f"## Repository instructions\n\n{instructions.strip()}\n\n"
                f"{template.strip()}\n\n## Context\n\n"
                f"{json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False)}\n"
            )
            payload, measured = invoke_json(
                codex,
                job_id=job_id,
                purpose=f"controlled_{'judge' if blind else mode}_{new_id('review')}",
                prompt=prompt,
                schema=schema,
                context=context,
            )
            usage.append(measured)
            requested = False
            visible_refs = {
                str(item["node_ref"]) for item in package["captured_nodes"]
            }
            node_by_ref = {
                node.node_ref: node for node in execution.snapshot.nodes
            }
            if mode not in {"etiq_full", "etiq_selected"}:
                for review in payload["reviews"]:
                    if review.get("expand_helper_prefixes") or review.get(
                        "inspect_artifacts"
                    ):
                        raise ValueError(
                            f"{mode} requested Etiq evidence it was not supplied"
                        )
            if mode == "etiq_selected":
                for review in payload["reviews"]:
                    unit_id = str(review["unit_id"])
                    if unit_id not in assigned:
                        continue
                    for prefix in review.get("expand_helper_prefixes", []):
                        validated = validate_expansion(
                            assigned[unit_id], prefix, expanded[unit_id]
                        )
                        if validated not in expanded[unit_id]:
                            expanded[unit_id].append(validated)
                            requested = True
            if mode in {"etiq_full", "etiq_selected"}:
                for review in payload["reviews"]:
                    unit_id = str(review["unit_id"])
                    if unit_id not in assigned:
                        continue
                    for request in review.get("inspect_artifacts", []):
                        node_ref = str(request.get("node_ref") or "")
                        if node_ref not in visible_refs or node_ref not in node_by_ref:
                            raise ValueError(
                                f"artifact inspection must target visible evidence: {node_ref}"
                            )
                        result = inspect_artifact(node_by_ref[node_ref], request)
                        if result not in inspections[unit_id]:
                            inspections[unit_id].append(result)
                            requested = True
            if not requested:
                visible_for_validation = None
                if mode == "etiq_full":
                    all_node_refs = {
                        str(item["node_ref"]) for item in package["captured_nodes"]
                    }
                    visible_for_validation = {
                        unit_id: all_node_refs for unit_id in assigned
                    }
                elif mode == "etiq_selected":
                    visible_for_validation = {
                        unit_id: set(evidence["node_refs"])
                        for unit_id, evidence in package[
                            "visible_evidence_by_unit"
                        ].items()
                    }
                receipt, _ = validate_review(
                    review_job_id=job_id,
                    section=section,
                    units=units,
                    decisions=review_decisions(payload),
                    allowed_evidence_refs=set(package["allowed_evidence_refs"]),
                    receipt_ref=f"controlled:{execution.snapshot.run_id}:{section.section_id}",
                    visible_node_refs_by_unit=visible_for_validation,
                )
                if receipt.result == "rejected":
                    receipt_retries += 1
                    if receipt_retries > 2:
                        raise ValueError(
                            "review receipt validation failed after correction "
                            f"retries: {receipt.errors}"
                        )
                    validation_errors = receipt.errors
                    continue
                reviews.extend(payload["reviews"])
                for unit_id in assigned:
                    package_by_unit[unit_id] = package
                break
            expansion_round += 1
            if expansion_round > 3:
                raise ValueError(
                    f"review expansion budget exhausted for {section.section_id}"
                )
    return reviews, units, usage, package_by_unit


def choose_target(
    *,
    mode: str,
    pipeline: GeneratedPipeline,
    execution: EtiqExecution,
    units: list[Any],
    reviews: list[dict[str, Any]],
    previous_targets: list[str],
) -> dict[str, Any]:
    unit_by_id = {unit.unit_id: unit for unit in units}
    failed = [
        unit_by_id[str(review["unit_id"])]
        for review in reviews
        if review.get("decision") == "failed"
        and str(review.get("unit_id")) in unit_by_id
    ]
    if not failed:
        failed = [
            unit_by_id[str(review["unit_id"])]
            for review in reviews
            if review.get("decision") == "suspect"
            and str(review.get("unit_id")) in unit_by_id
        ]
    if not failed:
        raise ValueError("repair requested without a failed or suspect unit")
    if mode not in {"etiq_full", "etiq_selected"}:
        unit = min(
            enumerate(failed),
            key=lambda item: (previous_targets.count(item[1].function_name), item[0]),
        )[1]
        target = source_scope(
            pipeline,
            function_name=unit.function_name,
            mode="boundary",
        )
        target.update(
            {
                "unit_id": unit.unit_id,
                "suspect_node_ref": None,
                "selection_reason": "reviewer-selected failed function without Etiq graph",
                "retrace_node_refs": [],
            }
        )
        return target
    receipt = {
        "result": "blocked_for_repair",
        "failed_or_suspect_unit_ids": [unit.unit_id for unit in failed],
        "suspect_node_refs": [
            str(ref)
            for review in reviews
            for ref in review.get("suspect_node_refs", [])
        ],
    }
    return select_repair_target(
        "boundary",
        pipeline=pipeline,
        snapshot=execution.snapshot,
        review_context={
            "units": jsonable(units),
            "receipts": [receipt],
        },
        previous_target_function_names=previous_targets,
    )


def replace_scope(
    pipeline: GeneratedPipeline,
    target: dict[str, Any],
    replacement_source: str,
) -> GeneratedPipeline:
    files: list[GeneratedFile] = []
    for item in pipeline.files:
        if item.path != target["file"]:
            files.append(item)
            continue
        lines = item.content.splitlines(keepends=True)
        replacement = replacement_source.rstrip() + "\n"
        content = (
            "".join(lines[: int(target["start_line"]) - 1])
            + replacement
            + "".join(lines[int(target["end_line"]) :])
        )
        files.append(GeneratedFile(item.path, content))
    changed = GeneratedPipeline(
        pipeline.entry_file,
        files,
        pipeline.review_boundaries,
    )
    changed.validate()
    validate_repair_scope(pipeline, changed, target)
    return changed


def repair_pipeline(
    *,
    repo_root: Path,
    codex: CodexRunner,
    job_id: str,
    mode: str,
    pipeline: GeneratedPipeline,
    package: dict[str, Any],
    reviews: list[dict[str, Any]],
    target: dict[str, Any],
    repair_feedback: list[str] | None = None,
) -> tuple[GeneratedPipeline, dict[str, Any]]:
    schema = json.loads(
        (repo_root / "schemas" / "repair_scope.schema.json").read_text()
    )
    prompt_template = (repo_root / "prompts" / "controlled_repair.md").read_text(
        encoding="utf-8"
    )
    source_file = next(item for item in pipeline.files if item.path == target["file"])
    lines = source_file.content.splitlines()
    selected_source = "\n".join(
        lines[int(target["start_line"]) - 1 : int(target["end_line"])]
    )
    context = {
        "mode": mode,
        "review_package": package,
        "reviews": reviews,
        "repair_target": target,
        "selected_source": selected_source,
        "instruction": (
            "Return only the complete replacement source for the selected scope. "
            "Do not return or change any other source."
        ),
        "repair_feedback": repair_feedback or [],
    }
    prompt = (
        f"{prompt_template.strip()}\n\n## Context\n\n"
        f"{json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False)}\n"
    )
    payload, usage = invoke_json(
        codex,
        job_id=job_id,
        purpose=f"controlled_{mode}_{new_id('repair')}",
        prompt=prompt,
        schema=schema,
        context=context,
    )
    changed = replace_scope(pipeline, target, str(payload["replacement_source"]))
    usage["change_summary"] = str(payload["change_summary"])
    usage["diff"] = repair_diff(pipeline, changed)
    return changed, usage


def run_arm(
    *,
    repo_root: Path,
    store: JobStore,
    codex: CodexRunner,
    etiq: EtiqExecutor,
    job_id: str,
    experiment_id: str,
    mode: str,
    pipeline: GeneratedPipeline,
    frozen: EtiqExecution,
    runtime_input: dict[str, Any],
    cassette_path: Path,
    max_repairs: int,
) -> dict[str, Any]:
    current_pipeline = pipeline
    current_execution = frozen
    previous_targets: list[str] = []
    usage: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    issues: list[str] = []
    for attempt in range(max_repairs + 1):
        reviews, units, review_usage, packages = review_execution(
            repo_root=repo_root,
            store=store,
            codex=codex,
            job_id=job_id,
            mode=mode,
            execution=current_execution,
            pipeline=current_pipeline,
            history_job_ids=[job_id],
        )
        usage.extend(review_usage)
        issues = _issue_keys(reviews, units)
        if attempts and attempts[-1]["status"] == "pending":
            function_by_unit = {
                unit.unit_id: unit.function_name for unit in units
            }
            target_name = attempts[-1]["target_function"]
            target_still_issued = any(
                function_by_unit.get(str(review.get("unit_id"))) == target_name
                and review.get("decision") in {"failed", "suspect"}
                for review in reviews
            )
            attempts[-1]["status"] = (
                "target_still_issued"
                if target_still_issued
                else "target_resolved"
            )
        if not issues or attempt == max_repairs:
            break
        target = choose_target(
            mode=mode,
            pipeline=current_pipeline,
            execution=current_execution,
            units=units,
            reviews=reviews,
            previous_targets=previous_targets,
        )
        repair_feedback: list[str] = []
        for repair_retry in range(3):
            replacement, repair_usage = repair_pipeline(
                repo_root=repo_root,
                codex=codex,
                job_id=job_id,
                mode=mode,
                pipeline=current_pipeline,
                package=packages[str(target["unit_id"])],
                reviews=reviews,
                target=target,
                repair_feedback=repair_feedback,
            )
            usage.append(repair_usage)
            replay_run_id = new_id("controlled-run")
            execution_started = time.monotonic()
            try:
                replay = etiq.execute(
                    job_id=job_id,
                    segment_id=f"{experiment_id}-{mode}",
                    stage="market_demand",
                    run_id=replay_run_id,
                    pipeline=replacement,
                    runtime_input=runtime_input,
                    network_mode="replay",
                    network_cassette_path=cassette_path,
                )
                replay_semantic = parse_pipeline_result(
                    replay, "market_demand"
                )
                store.write_json(
                    replay.run_dir / "semantic-result.json", replay_semantic
                )
                break
            except RuntimeError:
                failed_dir = store.stage_run_dir(
                    job_id,
                    f"{experiment_id}-{mode}",
                    "market_demand",
                    replay_run_id,
                )
                error = store.read_json(failed_dir / "execution-error.json", {})
                message = str(error.get("message") or "")
                scan_errors = store.read_json(
                    failed_dir / "etiq-scan-errors.json", []
                )
                details = f"{message} {json.dumps(scan_errors, default=str)}"
                if (
                    "unrecorded network request" not in details
                    and "recorded request count exhausted" not in details
                ) or repair_retry == 2:
                    raise
                repair_feedback = [
                    "The previous replacement violated the frozen-corpus "
                    f"contract: {details}. Keep all network request identities "
                    "and counts unchanged."
                ]
        store.write_json(
            replay.run_dir / "parent-run.json",
            {"parent_run_id": current_execution.snapshot.run_id},
        )
        attempts.append(
            {
                "attempt": attempt + 1,
                "target_function": target["function_name"],
                "run_id": replay_run_id,
                "execution_seconds": round(
                    time.monotonic() - execution_started, 3
                ),
                "output_hash": stable_hash(replay_semantic),
                "status": "pending",
            }
        )
        previous_targets.append(str(target["function_name"]))
        current_pipeline = replacement
        current_execution = replay

    try:
        judge_reviews, judge_units, judge_usage, _ = review_execution(
            repo_root=repo_root,
            store=store,
            codex=codex,
            job_id=job_id,
            mode="etiq_selected",
            execution=current_execution,
            pipeline=current_pipeline,
            history_job_ids=[job_id],
            blind=True,
        )
        usage.extend(judge_usage)
        judge_issues = _issue_keys(judge_reviews, judge_units)
        judge_error = None
    except Exception as exc:
        judge_issues = []
        judge_error = f"{type(exc).__name__}: {exc}"
    return {
        "mode": mode,
        "status": "completed" if judge_error is None else "judge_failed",
        "final_run_id": current_execution.snapshot.run_id,
        "repairs": attempts,
        "evaluated_repair_count": sum(
            attempt["status"] != "pending" for attempt in attempts
        ),
        "effective_repair_count": sum(
            attempt["status"] == "target_resolved" for attempt in attempts
        ),
        "branch_issue_keys": issues,
        "judge_issue_keys": judge_issues,
        "judge_trusted": not judge_issues if judge_error is None else None,
        "judge_error": judge_error,
        "input_tokens": sum(item["input_tokens"] for item in usage),
        "cached_input_tokens": sum(
            item["cached_input_tokens"] for item in usage
        ),
        "output_tokens": sum(item["output_tokens"] for item in usage),
        "duration_seconds": round(
            sum(item["duration_seconds"] for item in usage)
            + sum(item["execution_seconds"] for item in attempts),
            3,
        ),
        "invocations": usage,
    }


def experiment_result(
    *,
    experiment_id: str,
    job_id: str,
    baseline_run_id: str,
    frozen_run_id: str,
    cassette_path: Path,
    max_repairs: int,
    arms: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "job_id": job_id,
        "status": status,
        "baseline_source_run_id": baseline_run_id,
        "frozen_run_id": frozen_run_id,
        "cassette_hash": stable_hash(
            json.loads(cassette_path.read_text(encoding="utf-8"))
        ),
        "max_repairs": max_repairs,
        "isolation": {
            "fresh_ephemeral_codex_session_per_invocation": True,
            "cross_arm_history_visible": False,
            "network": "record_once_then_replay_recorded_requests_only",
            "final_judge": "fresh blind etiq_selected review with expansion",
            "branch_order_visible_to_agents": False,
        },
        "arms": arms,
    }


def run_controlled_experiment(
    *,
    repo_root: Path,
    store: JobStore,
    codex: CodexRunner,
    etiq: EtiqExecutor,
    job_id: str,
    baseline_run_id: str,
    max_repairs: int = 3,
) -> str:
    matches = list(
        store.job_dir(job_id).glob(f"stages/*/*/runs/{baseline_run_id}")
    )
    if len(matches) != 1:
        raise FileNotFoundError(f"baseline run not found: {baseline_run_id}")
    source_run = matches[0]
    pipeline = load_pipeline(store, source_run)
    runtime_input = store.read_json(source_run / "pipeline-input.json")
    experiment_id = new_id("controlled-comparison")
    experiment_dir = store.job_dir(job_id) / "controlled-experiments" / experiment_id
    experiment_dir.mkdir(parents=True)
    cassette_path = experiment_dir / "network-cassette.json"
    frozen_run_id = new_id("controlled-run")
    frozen = etiq.execute(
        job_id=job_id,
        segment_id=f"{experiment_id}-frozen",
        stage="market_demand",
        run_id=frozen_run_id,
        pipeline=pipeline,
        runtime_input=runtime_input,
        network_mode="record",
        network_cassette_path=cassette_path,
    )
    semantic = parse_pipeline_result(frozen, "market_demand")
    store.write_json(frozen.run_dir / "semantic-result.json", semantic)
    arms: list[dict[str, Any]] = []
    store.write_json(
        experiment_dir / "result.json",
        experiment_result(
            experiment_id=experiment_id,
            job_id=job_id,
            baseline_run_id=baseline_run_id,
            frozen_run_id=frozen_run_id,
            cassette_path=cassette_path,
            max_repairs=max_repairs,
            arms=arms,
            status="running",
        ),
    )
    for mode in EXPERIMENT_MODES:
        try:
            arm = run_arm(
                repo_root=repo_root,
                store=store,
                codex=codex,
                etiq=etiq,
                job_id=job_id,
                experiment_id=experiment_id,
                mode=mode,
                pipeline=pipeline,
                frozen=frozen,
                runtime_input=runtime_input,
                cassette_path=cassette_path,
                max_repairs=max_repairs,
            )
        except Exception as exc:
            arm = {
                "mode": mode,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "repairs": [],
                "judge_trusted": None,
                "judge_issue_keys": [],
            }
        arms.append(arm)
        store.write_json(
            experiment_dir / "result.json",
            experiment_result(
                experiment_id=experiment_id,
                job_id=job_id,
                baseline_run_id=baseline_run_id,
                frozen_run_id=frozen_run_id,
                cassette_path=cassette_path,
                max_repairs=max_repairs,
                arms=arms,
                status="running",
            ),
        )
    store.write_json(
        experiment_dir / "result.json",
        experiment_result(
            experiment_id=experiment_id,
            job_id=job_id,
            baseline_run_id=baseline_run_id,
            frozen_run_id=frozen_run_id,
            cassette_path=cassette_path,
            max_repairs=max_repairs,
            arms=arms,
            status="completed",
        ),
    )
    return experiment_id
