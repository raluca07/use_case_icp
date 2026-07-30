from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .codex_runner import CodexResult, CodexRunner
from .etiq_executor import EtiqExecution, EtiqExecutor
from .records import (
    AgentRequest,
    ContextArtifact,
    GeneratedPipeline,
    ReviewDecision,
    RootJobState,
    Segment,
    jsonable,
    new_id,
    stable_hash,
)
from .repair import repair_diff, select_repair_target, validate_repair_scope
from .review import (
    build_review_sections,
    build_review_units,
    inspect_artifact,
    review_node_payload,
    review_relationship_payload,
    trusted_frontier,
    validate_review,
    validate_expansion,
    visible_evidence,
)
from .job_store import JobStore


@dataclass(slots=True)
class PipelineOutcome:
    trusted: bool
    semantic_result: dict[str, Any]
    run_id: str | None
    reason: str | None = None
    trust_context: dict[str, Any] | None = None


RUNTIME_RESULT_KEYS = {
    "market_demand": {"needs", "workflows", "demand_signals", "assumptions", "gaps"},
    "coverage": {"mappings", "use_cases", "icp_traits", "gaps", "sufficient"},
}


def parse_pipeline_result(execution: EtiqExecution, stage: str) -> dict[str, Any]:
    raw_output = (execution.run_dir / "pipeline-stdout.log").read_text(encoding="utf-8").strip()
    if not raw_output:
        raise RuntimeError(f"{stage} pipeline emitted no JSON result on stdout")
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{stage} pipeline stdout is not one valid JSON object: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{stage} pipeline result must be a JSON object")
    missing = sorted(RUNTIME_RESULT_KEYS.get(stage, set()) - payload.keys())
    if missing:
        raise RuntimeError(
            f"{stage} pipeline result is missing required keys: {', '.join(missing)}"
        )
    return payload


def pipeline_failure_details(
    run_dir: Path,
    *,
    phase: str,
    message: str,
    execution: EtiqExecution | None = None,
) -> dict[str, Any]:
    def read_text(name: str) -> str:
        path = run_dir / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_json(name: str) -> Any:
        path = run_dir / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    details: dict[str, Any] = {
        "phase": phase,
        "message": message,
        "execution_error": read_json("execution-error.json"),
        "stdout": read_text("pipeline-stdout.log"),
        "stderr": read_text("pipeline-stderr.log"),
        "etiq_scan_errors": read_json("etiq-scan-errors.json"),
    }
    if execution is not None:
        details["node_count"] = len(execution.snapshot.nodes)
        details["relationship_count"] = len(execution.snapshot.relationships)
    return details


def failed_function_names(review_context: dict[str, Any]) -> list[str]:
    unit_by_id = {
        str(unit.get("unit_id")): unit
        for unit in review_context.get("units", [])
    }
    failed_unit_ids = [
        str(unit_id)
        for receipt in review_context.get("receipts", [])
        for unit_id in receipt.get("failed_or_suspect_unit_ids", [])
    ]
    return list(
        dict.fromkeys(
            str(unit_by_id[unit_id].get("function_name"))
            for unit_id in failed_unit_ids
            if unit_id in unit_by_id
        )
    )


def reviewed_function_names(review_context: dict[str, Any]) -> list[str]:
    unit_by_id = {
        str(unit.get("unit_id")): unit
        for unit in review_context.get("units", [])
    }
    reviewed_unit_ids = [
        str(unit_id)
        for receipt in review_context.get("receipts", [])
        for unit_id in receipt.get("reviewed_unit_ids", [])
    ]
    return list(
        dict.fromkeys(
            str(unit_by_id[unit_id].get("function_name"))
            for unit_id in reviewed_unit_ids
            if unit_id in unit_by_id
        )
    )


def repair_metrics(
    attempts: list[dict[str, Any]],
    *,
    repair_budget: int,
    initial_issue_functions: list[str],
    current_issue_functions: list[str],
    current_run_id: str,
) -> dict[str, Any]:
    evaluated = [
        attempt
        for attempt in attempts
        if attempt["status"] in {"target_resolved", "target_still_flagged"}
    ]
    effective = [
        attempt for attempt in evaluated if attempt["status"] == "target_resolved"
    ]
    return {
        "repair_budget": repair_budget,
        "accepted_repair_count": len(attempts),
        "evaluated_repair_count": len(evaluated),
        "effective_repair_count": len(effective),
        "repair_effectiveness_rate": (
            round(len(effective) / len(evaluated), 4) if evaluated else None
        ),
        "unique_boundaries_repaired": sorted(
            {str(attempt["target_function"]) for attempt in attempts}
        ),
        "initial_issue_functions": initial_issue_functions,
        "current_issue_functions": current_issue_functions,
        "resolved_initial_issue_functions": sorted(
            set(initial_issue_functions) - set(current_issue_functions)
        ),
        "current_run_id": current_run_id,
        "attempts": attempts,
        "definitions": {
            "accepted_repair": "Codex returned an in-scope code change with a non-empty diff.",
            "evaluated_repair": "The accepted change was executed and reviewed in a later run.",
            "effective_repair": "The targeted function was no longer failed or suspect in that later review.",
        },
    }


def review_decisions(payload: Mapping[str, Any]) -> list[ReviewDecision]:
    return [
        ReviewDecision(
            unit_id=str(item["unit_id"]),
            decision=str(item["decision"]),
            decision_reason=str(item["decision_reason"]),
            evidence_refs=[str(value) for value in item.get("evidence_refs", [])],
            trust_level=item.get("trust_level"),
            criteria_outcomes=list(item.get("criteria_outcomes", [])),
            boundary_health_acknowledged=bool(item.get("boundary_health_acknowledged")),
            expand_helper_prefixes=[
                [str(value) for value in prefix]
                for prefix in item.get("expand_helper_prefixes", [])
            ],
            inspect_artifacts=[
                dict(value) for value in item.get("inspect_artifacts", [])
            ],
            suspect_node_refs=[
                str(value) for value in item.get("suspect_node_refs", [])
            ],
        )
        for item in payload["reviews"]
    ]


class WorkflowRunner:
    """Synchronous, fail-closed MVP workflow."""

    def __init__(
        self,
        *,
        repo_root: Path | str,
        store: JobStore,
        codex: CodexRunner,
        etiq: EtiqExecutor,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.store = store
        self.codex = codex
        self.etiq = etiq

    def run(self, request: AgentRequest, *, job_id: str | None = None) -> str:
        request.validate()
        job_id = job_id or new_id("job")
        state = RootJobState(job_id=job_id, status="running")
        self.store.initialize_job(request, state)
        self.store.append_event(job_id, "started", "Workflow started")
        try:
            segments, segment_fingerprint = self._segments(job_id, request)
            retained_gaps: list[str] = []
            processed_evidence: list[dict[str, Any]] = []
            for index, segment in enumerate(segments):
                segment.status = "active"
                self.store.write_segments(job_id, segments, segment_fingerprint)
                self.store.update_state(
                    job_id,
                    active_segment_id=segment.segment_id,
                    segment_cursor=index,
                )
                market_demand = self._pipeline_stage(
                    job_id=job_id,
                    request=request,
                    segment=segment,
                    stage="market_demand",
                    context={"retained_gaps": retained_gaps},
                )
                if not market_demand.trusted:
                    raise RuntimeError(
                        market_demand.reason
                        or "market-demand discovery did not reach reusable trust"
                    )
                coverage = self._pipeline_stage(
                    job_id=job_id,
                    request=request,
                    segment=segment,
                    stage="coverage",
                    context={
                        "market_demand": market_demand.semantic_result,
                        "market_demand_run_id": market_demand.run_id,
                        "market_demand_trust": market_demand.trust_context,
                    },
                )
                if not coverage.trusted:
                    raise RuntimeError(coverage.reason or "coverage did not reach reusable trust")
                if bool(coverage.semantic_result.get("sufficient")):
                    segment.status = "selected"
                    self.store.write_segments(job_id, segments, segment_fingerprint)
                    final = self._synthesis(
                        job_id,
                        request,
                        mode="supported",
                        context={
                            "segment": jsonable(segment),
                            "market_demand": market_demand.semantic_result,
                            "market_demand_trust": market_demand.trust_context,
                            "coverage": coverage.semantic_result,
                            "coverage_trust": coverage.trust_context,
                        },
                    )
                    self._complete(job_id, final)
                    return job_id
                segment.status = "processed_insufficient"
                retained_gaps.extend(str(item) for item in coverage.semantic_result.get("gaps", []))
                processed_evidence.append(
                    {
                        "segment": jsonable(segment),
                        "market_demand_trust": market_demand.trust_context,
                        "coverage_trust": coverage.trust_context,
                        "coverage_gaps": coverage.semantic_result.get("gaps", []),
                    }
                )
                self.store.append_event(
                    job_id,
                    "coverage_insufficient",
                    f"Coverage was trusted but insufficient for {segment.name}",
                    stage="coverage",
                    segment_id=segment.segment_id,
                    run_id=coverage.run_id,
                )
            final = self._synthesis(
                job_id,
                request,
                mode="no_sufficient_segment",
                context={
                    "segments": jsonable(segments),
                    "retained_gaps": retained_gaps,
                    "processed_evidence": processed_evidence,
                },
            )
            self._complete(job_id, final)
        except Exception as exc:
            self.store.update_state(job_id, status="failed", last_error=f"{type(exc).__name__}: {exc}")
            self.store.append_event(job_id, "failed", str(exc), severity="error")
            raise
        return job_id

    def _segments(self, job_id: str, request: AgentRequest) -> tuple[list[Segment], str]:
        payload = self._invoke(
            job_id=job_id,
            job_type="segment",
            purpose="segment",
            prompt_name="segment",
            schema_name="segment",
            context={"request": jsonable(request)},
        ).payload
        segments = [
            Segment(
                segment_id=str(item["id"]),
                name=str(item["name"]),
                definition=str(item["definition"]),
                rank=index,
                inclusion_criteria=[str(value) for value in item.get("inclusion_criteria", [])],
                exclusion_criteria=[str(value) for value in item.get("exclusion_criteria", [])],
                initial_fit_reason=str(item.get("fit_reason") or ""),
            )
            for index, item in enumerate(payload["segments"][: request.max_segments], start=1)
        ]
        if not segments or len(segments) > request.max_segments:
            raise ValueError("segment count is outside the configured range")
        ids = [segment.segment_id for segment in segments]
        if len(ids) != len(set(ids)):
            raise ValueError("segment IDs must be unique")
        fingerprint = stable_hash(
            {
                "product": request.product,
                "audience": request.audience,
                "criteria": request.segmentation_criteria,
            }
        )
        self.store.write_segments(job_id, segments, fingerprint)
        self.store.append_event(job_id, "segments_created", f"Created {len(segments)} candidate segments", stage="segment")
        return segments, fingerprint

    def _pipeline_stage(
        self,
        *,
        job_id: str,
        request: AgentRequest,
        segment: Segment,
        stage: str,
        context: dict[str, Any],
    ) -> PipelineOutcome:
        stage_input = {"request": jsonable(request), "segment": jsonable(segment), **context}
        initial = self._invoke(
            job_id=job_id,
            job_type=stage,
            purpose=stage,
            prompt_name=stage,
            schema_name=stage,
            context=stage_input,
            include_pipeline_instruction=True,
        )
        authoring_semantic = {key: value for key, value in initial.payload.items() if key != "pipeline"}
        max_authoring_retries = int(request.limits.get("authoring_retries", 2))
        max_repairs = int(request.limits.get("repairs", 6))
        authoring_retry_index = 0
        repair_index = 0
        repair_attempts: list[dict[str, Any]] = []
        initial_issue_functions: list[str] | None = None
        parent_run_id: str | None = None
        authoring_retry_link: dict[str, Any] | None = None
        repair_link: dict[str, Any] | None = None
        producing_invocation = initial.invocation_id
        pipeline_payload = initial.payload.get("pipeline", {})
        while True:
            try:
                pipeline = GeneratedPipeline.from_payload(pipeline_payload)
                break
            except (KeyError, TypeError, ValueError) as exc:
                failure = {
                    "phase": "bundle_validation",
                    "message": f"{type(exc).__name__}: {exc}",
                }
                self.store.append_event(
                    job_id,
                    "pipeline_attempt_failed",
                    f"{stage} pipeline failed before execution: {failure['message']}",
                    stage=stage,
                    segment_id=segment.segment_id,
                    severity="error",
                )
                if authoring_retry_index >= max_authoring_retries:
                    return PipelineOutcome(
                        False,
                        {},
                        None,
                        "pipeline authoring retry budget was exhausted before execution",
                    )
                previous_invocation = producing_invocation
                authoring_retry_index += 1
                retry = self._invoke(
                    job_id=job_id,
                    job_type=stage,
                    purpose=f"{stage}_authoring_retry_{authoring_retry_index}",
                    prompt_name="pipeline_retry",
                    schema_name="pipeline_retry",
                    context={
                        "stage": stage,
                        "request": jsonable(request),
                        "segment": jsonable(segment),
                        "runtime_input": stage_input,
                        "required_runtime_keys": sorted(RUNTIME_RESULT_KEYS.get(stage, set())),
                        "pipeline": pipeline_payload,
                        "failed_run_id": None,
                        "failure": failure,
                    },
                    include_pipeline_instruction=True,
                    caused_by_invocation_id=previous_invocation,
                )
                pipeline_payload = retry.payload.get("pipeline", {})
                producing_invocation = retry.invocation_id
                authoring_retry_link = {
                    "attempt": authoring_retry_index,
                    "previous_run_id": None,
                    "caused_by_invocation_id": previous_invocation,
                    "replacement_invocation_id": producing_invocation,
                    "change_summary": str(retry.payload["change_summary"]),
                }
                self.store.increment_authoring_retry(job_id)
                self.store.append_event(
                    job_id,
                    "pipeline_authoring_retried",
                    f"Codex rewrote the invalid {stage} pipeline bundle",
                    stage=stage,
                    segment_id=segment.segment_id,
                    artifact_refs=[f"invocations/{producing_invocation}"],
                )
        while True:
            while True:
                run_id = new_id(f"{stage}-run")
                run_dir = self.store.stage_run_dir(
                    job_id,
                    segment.segment_id,
                    stage,
                    run_id,
                )
                execution: EtiqExecution | None = None
                failure: dict[str, Any] | None = None
                try:
                    execution = self.etiq.execute(
                        job_id=job_id,
                        segment_id=segment.segment_id,
                        stage=stage,
                        run_id=run_id,
                        pipeline=pipeline,
                        invocation_id=producing_invocation,
                        runtime_input=stage_input,
                    )
                    semantic = parse_pipeline_result(execution, stage)
                    if not execution.reviewable:
                        failure = pipeline_failure_details(
                            run_dir,
                            phase="etiq_scan",
                            message="Etiq scan was not reviewable",
                            execution=execution,
                        )
                except Exception as exc:
                    failure = pipeline_failure_details(
                        run_dir,
                        phase=(
                            "runtime_output"
                            if execution is not None
                            else ("compilation" if isinstance(exc, SyntaxError) else "execution")
                        ),
                        message=f"{type(exc).__name__}: {exc}",
                        execution=execution,
                    )

                if run_dir.exists():
                    if parent_run_id:
                        self.store.write_json(
                            run_dir / "parent-run.json",
                            {"parent_run_id": parent_run_id},
                        )
                    if authoring_retry_link:
                        self.store.write_json(
                            run_dir / "authoring-retry.json",
                            authoring_retry_link,
                        )
                    if repair_link:
                        self.store.write_json(run_dir / "applied-repair.json", repair_link)

                if failure is None:
                    break

                self.store.append_event(
                    job_id,
                    "pipeline_attempt_failed",
                    f"{stage} pipeline failed before review during {failure['phase']}: {failure['message']}",
                    stage=stage,
                    segment_id=segment.segment_id,
                    run_id=run_id,
                    severity="error",
                    artifact_refs=(
                        [str(run_dir.relative_to(self.store.job_dir(job_id)))]
                        if run_dir.exists()
                        else []
                    ),
                )
                if authoring_retry_index >= max_authoring_retries:
                    return PipelineOutcome(
                        False,
                        {},
                        run_id,
                        "pipeline authoring retry budget was exhausted before review",
                    )

                previous_invocation = producing_invocation
                authoring_retry_index += 1
                retry = self._invoke(
                    job_id=job_id,
                    job_type=stage,
                    purpose=f"{stage}_authoring_retry_{authoring_retry_index}",
                    prompt_name="pipeline_retry",
                    schema_name="pipeline_retry",
                    context={
                        "stage": stage,
                        "request": jsonable(request),
                        "segment": jsonable(segment),
                        "runtime_input": stage_input,
                        "required_runtime_keys": sorted(RUNTIME_RESULT_KEYS.get(stage, set())),
                        "pipeline": jsonable(pipeline),
                        "failed_run_id": run_id,
                        "failure": failure,
                    },
                    include_pipeline_instruction=True,
                    caused_by_invocation_id=previous_invocation,
                )
                pipeline = GeneratedPipeline.from_payload(retry.payload["pipeline"])
                producing_invocation = retry.invocation_id
                authoring_retry_link = {
                    "attempt": authoring_retry_index,
                    "previous_run_id": run_id,
                    "caused_by_invocation_id": previous_invocation,
                    "replacement_invocation_id": producing_invocation,
                    "change_summary": str(retry.payload["change_summary"]),
                }
                self.store.increment_authoring_retry(job_id)
                self.store.append_event(
                    job_id,
                    "pipeline_authoring_retried",
                    f"Codex rewrote the {stage} pipeline after a pre-review failure",
                    stage=stage,
                    segment_id=segment.segment_id,
                    run_id=run_id,
                    artifact_refs=[f"invocations/{producing_invocation}"],
                )

            assert execution is not None
            self.store.write_json(execution.run_dir / "authoring-semantic.json", authoring_semantic)
            self.store.write_json(execution.run_dir / "semantic-result.json", semantic)
            self.store.append_event(
                job_id,
                "pipeline_result_captured",
                f"Captured {stage} semantic result from Etiq-executed pipeline stdout",
                stage=stage,
                segment_id=segment.segment_id,
                run_id=run_id,
            )
            self.store.append_event(
                job_id,
                "etiq_scan_completed",
                f"Etiq captured {len(execution.snapshot.nodes)} nodes for {stage}",
                stage=stage,
                segment_id=segment.segment_id,
                run_id=run_id,
            )
            trusted, review_context = self._review_execution(
                job_id=job_id,
                request=request,
                segment=segment,
                stage=stage,
                execution=execution,
                semantic=semantic,
                pipeline=pipeline,
            )
            issue_functions = failed_function_names(review_context)
            reviewed_functions = reviewed_function_names(review_context)
            if initial_issue_functions is None:
                initial_issue_functions = issue_functions
            if repair_attempts and repair_attempts[-1]["status"] == "pending":
                latest_attempt = repair_attempts[-1]
                target_function = str(latest_attempt["target_function"])
                if target_function in reviewed_functions:
                    effective = target_function not in issue_functions
                    latest_attempt.update(
                        {
                            "result_run_id": run_id,
                            "status": (
                                "target_resolved"
                                if effective
                                else "target_still_flagged"
                            ),
                            "issue_functions_after": issue_functions,
                        }
                    )
                    self.store.record_repair_evaluation(job_id, effective=effective)
                    self.store.append_event(
                        job_id,
                        "repair_evaluated",
                        (
                            f"Repair {latest_attempt['attempt']} resolved "
                            f"{target_function}"
                            if effective
                            else (
                                f"Repair {latest_attempt['attempt']} left "
                                f"{target_function} flagged"
                            )
                        ),
                        stage=stage,
                        segment_id=segment.segment_id,
                        run_id=run_id,
                    )
                else:
                    latest_attempt.update(
                        {
                            "result_run_id": run_id,
                            "status": "target_not_reviewed",
                            "issue_functions_after": issue_functions,
                        }
                    )
            metrics_path = execution.run_dir.parent.parent / "repair-metrics.json"
            self.store.write_json(
                metrics_path,
                repair_metrics(
                    repair_attempts,
                    repair_budget=max_repairs,
                    initial_issue_functions=initial_issue_functions or [],
                    current_issue_functions=issue_functions,
                    current_run_id=run_id,
                ),
            )
            if trusted:
                self.store.append_event(
                    job_id,
                    "stage_trusted",
                    f"{stage} reached trusted_for_reuse",
                    stage=stage,
                    segment_id=segment.segment_id,
                    run_id=run_id,
                )
                return PipelineOutcome(True, semantic, run_id, trust_context=review_context)
            if not review_context.get("repairable", True):
                return PipelineOutcome(
                    False,
                    semantic,
                    run_id,
                    str(review_context.get("reason") or "review could not produce a valid repair request"),
                    trust_context=review_context,
                )
            if repair_index >= max_repairs:
                return PipelineOutcome(False, semantic, run_id, "review requested repair but repair budget was exhausted")
            repair_mode = str(request.limits.get("repair_scope_mode", "boundary"))
            repair_target = select_repair_target(
                repair_mode,
                pipeline=pipeline,
                snapshot=execution.snapshot,
                review_context=review_context,
                previous_target_function_names=[
                    str(attempt["target_function"])
                    for attempt in repair_attempts
                ],
            )
            self.store.write_json(execution.run_dir / "repair-target.json", repair_target)
            repair = self._invoke(
                job_id=job_id,
                job_type=stage,
                purpose=f"{stage}_repair",
                prompt_name="repair",
                schema_name="repair",
                context={
                    "stage": stage,
                    "request": jsonable(request),
                    "segment": jsonable(segment),
                    "pipeline": jsonable(pipeline),
                    "review": review_context,
                    "repair_target": repair_target,
                },
                include_pipeline_instruction=True,
                caused_by_invocation_id=producing_invocation,
            )
            replacement = GeneratedPipeline.from_payload(repair.payload["pipeline"])
            validate_repair_scope(pipeline, replacement, repair_target)
            diff = repair_diff(pipeline, replacement)
            if not diff:
                raise ValueError("repair did not change the selected source scope")
            self.store.write_json(
                execution.run_dir / "repair-diff.json",
                {
                    "target": repair_target,
                    "change_summary": str(repair.payload["change_summary"]),
                    "unified_diff": diff,
                },
            )
            pipeline = replacement
            producing_invocation = repair.invocation_id
            parent_run_id = run_id
            authoring_retry_link = None
            repair_link = {
                "previous_run_id": run_id,
                "repair_invocation_id": producing_invocation,
                "change_summary": str(repair.payload["change_summary"]),
                "target": repair_target,
                "diff_ref": str(
                    (execution.run_dir / "repair-diff.json").relative_to(
                        self.store.job_dir(job_id)
                    )
                ),
            }
            repair_index += 1
            repair_attempts.append(
                {
                    "attempt": repair_index,
                    "source_run_id": run_id,
                    "result_run_id": None,
                    "target_function": repair_target["function_name"],
                    "target_unit_id": repair_target["unit_id"],
                    "previous_attempts_for_boundary": repair_target.get(
                        "previous_attempts_for_boundary",
                        0,
                    ),
                    "issue_functions_before": issue_functions,
                    "status": "pending",
                    "diff_ref": repair_link["diff_ref"],
                }
            )
            self.store.write_json(
                metrics_path,
                repair_metrics(
                    repair_attempts,
                    repair_budget=max_repairs,
                    initial_issue_functions=initial_issue_functions or [],
                    current_issue_functions=issue_functions,
                    current_run_id=run_id,
                ),
            )
            self.store.increment_repair(job_id)
        return PipelineOutcome(False, semantic, parent_run_id, "unreachable repair state")

    def _review_execution(
        self,
        *,
        job_id: str,
        request: AgentRequest,
        segment: Segment,
        stage: str,
        execution: EtiqExecution,
        semantic: dict[str, Any],
        pipeline: GeneratedPipeline,
    ) -> tuple[bool, dict[str, Any]]:
        units = build_review_units(
            execution.snapshot,
            declared_boundaries=pipeline.review_boundaries,
            max_descendant_frames=int(request.limits.get("review_unit_max_frames", 128)),
            max_nodes=int(request.limits.get("review_unit_max_nodes", 256)),
            max_relationships=int(request.limits.get("review_unit_max_relationships", 512)),
            max_nesting_depth=int(request.limits.get("review_unit_max_depth", 8)),
        )
        if not units:
            return False, {
                "reason": "no observed review units matched the declared or captured boundaries",
                "units": [],
                "receipts": [],
            }
        sections = build_review_sections(
            units,
            section_size=int(request.limits.get("section_size", 8)),
            overlap=int(request.limits.get("section_overlap", 1)),
            max_nodes=int(request.limits.get("section_max_nodes", 300)),
            max_relationships=int(request.limits.get("section_max_relationships", 512)),
            max_helpers=int(request.limits.get("section_max_helpers", 128)),
        )
        self.store.write_json(execution.run_dir / "review-boundaries.json", units)
        reusable: set[str] = set()
        non_pipeline: set[str] = set()
        receipt_summaries: list[dict[str, Any]] = []
        context_accounting: list[dict[str, Any]] = []
        node_by_ref = {node.node_ref: node for node in execution.snapshot.nodes}
        relationship_by_ref = {
            relationship.relationship_ref: relationship for relationship in execution.snapshot.relationships
        }
        job_root = self.store.job_dir(job_id)
        evidence_refs = [
            str((execution.run_dir / "etiq-nodes.json").relative_to(job_root)),
            str((execution.run_dir / "etiq-relationships.json").relative_to(job_root)),
        ]
        full_review_nodes = [
            review_node_payload(node) for node in execution.snapshot.nodes
        ]
        full_review_relationships = [
            review_relationship_payload(relationship)
            for relationship in execution.snapshot.relationships
        ]
        for section in sections:
            assigned = [unit for unit in units if unit.unit_id in section.assigned_unit_ids]
            context_units = [unit for unit in units if unit.unit_id in section.context_unit_ids]
            expanded: dict[str, list[list[str]]] = {
                unit.unit_id: [] for unit in context_units
            }
            artifact_inspections: dict[str, list[dict[str, Any]]] = {
                unit.unit_id: [] for unit in context_units
            }
            max_expansions = int(request.limits.get("review_expansions", 3))
            expansion_round = 0
            while True:
                visible_by_unit = {
                    unit.unit_id: visible_evidence(
                        unit,
                        execution.snapshot,
                        expanded[unit.unit_id],
                    )
                    for unit in context_units
                }
                node_refs = {
                    ref
                    for evidence in visible_by_unit.values()
                    for ref in evidence["node_refs"]
                }
                relationship_refs = {
                    ref
                    for evidence in visible_by_unit.values()
                    for ref in evidence["relationship_refs"]
                }
                package = {
                    "section": jsonable(section),
                    "assigned_units": jsonable(assigned),
                    "context_units": jsonable(context_units),
                    "visible_evidence_by_unit": visible_by_unit,
                    "artifact_inspections_by_unit": artifact_inspections,
                    "captured_nodes": [
                        review_node_payload(node_by_ref[ref])
                        for ref in sorted(node_refs)
                        if ref in node_by_ref
                    ],
                    "captured_relationships": [
                        review_relationship_payload(relationship_by_ref[ref])
                        for ref in sorted(relationship_refs)
                        if ref in relationship_by_ref
                    ],
                    "semantic_result": semantic,
                    "evidence_refs": evidence_refs,
                }
                section.section_input_hash = stable_hash(package)
                package["section"] = jsonable(section)
                self.store.write_json(execution.run_dir / "review-sections.json", sections)
                package_chars = len(json.dumps(package, sort_keys=True, ensure_ascii=False))
                available_package_chars = len(
                    json.dumps(
                        {
                            **package,
                            "captured_nodes": full_review_nodes,
                            "captured_relationships": full_review_relationships,
                        },
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                )
                max_package_chars = int(request.limits.get("review_package_max_chars", 400_000))
                if package_chars > max_package_chars:
                    raise ValueError(
                        f"review package {section.section_id} exceeds character budget: "
                        f"{package_chars} > {max_package_chars}"
                    )
                suffix = "" if expansion_round == 0 else f"_expand_{expansion_round}"
                review_result = self._invoke(
                    job_id=job_id,
                    job_type="review",
                    purpose=f"{stage}_review_{section.section_id}{suffix}",
                    prompt_name="review",
                    schema_name="review",
                    context={
                        "stage": stage,
                        "request": jsonable(request),
                        "segment": jsonable(segment),
                        "review_package": package,
                    },
                )
                context_accounting.append(
                    {
                        "section_id": section.section_id,
                        "expansion_round": expansion_round,
                        "available_package_chars": available_package_chars,
                        "selected_package_chars": package_chars,
                        "selected_to_available_ratio": (
                            round(package_chars / available_package_chars, 4)
                            if available_package_chars
                            else None
                        ),
                        "character_reduction": max(0, available_package_chars - package_chars),
                        "estimated_available_tokens": (available_package_chars + 3) // 4,
                        "estimated_selected_tokens": (package_chars + 3) // 4,
                        "reported_input_tokens": review_result.usage.input_tokens,
                        "selected_node_count": len(node_refs),
                        "available_node_count": len(execution.snapshot.nodes),
                        "selected_relationship_count": len(relationship_refs),
                        "available_relationship_count": len(execution.snapshot.relationships),
                    }
                )
                self.store.write_json(
                    execution.run_dir / "context-accounting.json",
                    context_accounting,
                )
                decisions = review_decisions(review_result.payload)
                requested = False
                unit_by_id = {unit.unit_id: unit for unit in assigned}
                for decision in decisions:
                    if decision.unit_id not in unit_by_id:
                        continue
                    for prefix in decision.expand_helper_prefixes:
                        validated = validate_expansion(
                            unit_by_id[decision.unit_id],
                            prefix,
                            expanded[decision.unit_id],
                        )
                        if validated not in expanded[decision.unit_id]:
                            expanded[decision.unit_id].append(validated)
                            requested = True
                    for inspection_request in decision.inspect_artifacts:
                        node_ref = str(inspection_request.get("node_ref") or "")
                        if node_ref not in node_refs or node_ref not in node_by_ref:
                            raise ValueError(
                                f"artifact inspection must target visible evidence: {node_ref}"
                            )
                        inspection = inspect_artifact(
                            node_by_ref[node_ref],
                            inspection_request,
                        )
                        if inspection not in artifact_inspections[decision.unit_id]:
                            artifact_inspections[decision.unit_id].append(inspection)
                            requested = True
                if not requested:
                    break
                expansion_round += 1
                if expansion_round > max_expansions:
                    raise ValueError(
                        f"review expansion budget exhausted for {section.section_id}"
                    )
            receipt_path = self.store.receipt_path(
                job_id,
                execution.snapshot.run_id,
                section.section_id,
            )
            receipt_ref = str(receipt_path.relative_to(job_root))
            receipt_attempts: list[dict[str, Any]] = []
            max_receipt_retries = int(request.limits.get("review_receipt_retries", 2))
            receipt_retry = 0
            while True:
                receipt, annotations = validate_review(
                    review_job_id=job_id,
                    section=section,
                    units=units,
                    decisions=decisions,
                    allowed_evidence_refs=(
                        set(package["evidence_refs"])
                        | {unit.unit_id for unit in context_units}
                        | set(node_refs)
                        | set(relationship_refs)
                    ),
                    receipt_ref=receipt_ref,
                    visible_node_refs_by_unit={
                        unit_id: set(evidence["node_refs"])
                        for unit_id, evidence in visible_by_unit.items()
                    },
                )
                receipt_attempts.append(jsonable(receipt))
                if receipt.result != "rejected":
                    break
                if receipt_retry >= max_receipt_retries:
                    self.store.write_json(
                        execution.run_dir / f"{section.section_id}-receipt-attempts.json",
                        receipt_attempts,
                    )
                    self.store.write_json(receipt_path, receipt)
                    return False, {
                        "run_id": execution.snapshot.run_id,
                        "reason": "review receipt validation failed after correction retries",
                        "repairable": False,
                        "units": jsonable(units),
                        "receipts": [jsonable(receipt)],
                    }
                receipt_retry += 1
                package["review_validation_errors"] = receipt.errors
                section.section_input_hash = stable_hash(package)
                package["section"] = jsonable(section)
                correction = self._invoke(
                    job_id=job_id,
                    job_type="review",
                    purpose=(
                        f"{stage}_review_{section.section_id}_"
                        f"receipt_retry_{receipt_retry}"
                    ),
                    prompt_name="review",
                    schema_name="review",
                    context={
                        "stage": stage,
                        "request": jsonable(request),
                        "segment": jsonable(segment),
                        "review_package": package,
                    },
                    caused_by_invocation_id=review_result.invocation_id,
                )
                review_result = correction
                decisions = review_decisions(correction.payload)
            self.store.write_json(
                execution.run_dir / f"{section.section_id}-receipt-attempts.json",
                receipt_attempts,
            )
            self.store.write_json(receipt_path, receipt)
            for annotation in annotations:
                self.store.append_trust_annotation(job_id, annotation)
            receipt_summaries.append(jsonable(receipt))
            reusable.update(receipt.reusable_trusted_unit_ids)
            non_pipeline.update(receipt.non_pipeline_unit_ids)
            frontier = trusted_frontier(
                units,
                self.store.read_trust_annotations(job_id),
            )
            self.store.write_json(execution.run_dir / "trusted-frontier.json", frontier)
            if receipt.result != "passed":
                return False, {
                    "run_id": execution.snapshot.run_id,
                    "repairable": receipt.result == "blocked_for_repair",
                    "units": jsonable(units),
                    "receipts": receipt_summaries,
                    "trusted_frontier": frontier,
                }
        required_unit_ids = {unit.unit_id for unit in units} - non_pipeline
        frontier = trusted_frontier(
            units,
            self.store.read_trust_annotations(job_id),
        )
        return reusable == required_unit_ids, {
            "run_id": execution.snapshot.run_id,
            "snapshot_id": execution.snapshot.snapshot_id,
            "snapshot_hash": stable_hash(execution.snapshot),
            "evidence_refs": evidence_refs,
            "units": jsonable(units),
            "receipts": receipt_summaries,
            "trusted_frontier": frontier,
            "required_unit_ids": sorted(required_unit_ids),
            "non_pipeline_unit_ids": sorted(non_pipeline),
        }

    def _synthesis(
        self,
        job_id: str,
        request: AgentRequest,
        *,
        mode: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        result = self._invoke(
            job_id=job_id,
            job_type="synthesis",
            purpose=f"synthesis_{mode}",
            prompt_name="synthesis",
            schema_name="synthesis",
            context={"request": jsonable(request), "mode": mode, **context},
        )
        return result.payload

    def _invoke(
        self,
        *,
        job_id: str,
        job_type: str,
        purpose: str,
        prompt_name: str,
        schema_name: str,
        context: dict[str, Any],
        include_pipeline_instruction: bool = False,
        caused_by_invocation_id: str | None = None,
    ) -> CodexResult:
        template_path = self.repo_root / "prompts" / f"{prompt_name}.md"
        template = template_path.read_text(encoding="utf-8")
        repository_instructions = (self.repo_root / "AGENTS.md").read_text(encoding="utf-8")
        template = (
            "## Repository instructions\n\n"
            f"{repository_instructions.strip()}\n\n"
            f"{template.strip()}"
        )
        prompt_artifacts = [
            ContextArtifact(
                ref=f"prompt:{prompt_name}",
                content_hash=stable_hash(template),
                delivery="embedded",
                purpose="prompt_template",
                content=template,
            ),
            ContextArtifact(
                ref="repo:AGENTS.md",
                content_hash=stable_hash(repository_instructions),
                delivery="embedded",
                purpose="repository_instructions",
                content=repository_instructions,
            ),
        ]
        if include_pipeline_instruction:
            instruction_path = self.repo_root / "prompts" / "pipeline_instruction.md"
            instruction = instruction_path.read_text(encoding="utf-8")
            template = f"{instruction.strip()}\n\n{template.strip()}"
            prompt_artifacts.append(
                ContextArtifact(
                    ref="prompt:pipeline_instruction",
                    content_hash=stable_hash(instruction),
                    delivery="embedded",
                    purpose="shared_pipeline_instruction",
                    content=instruction,
                )
            )
        schema = json.loads((self.repo_root / "schemas" / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
        context_json = json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False)
        prompt = f"{template.strip()}\n\n## Context\n\n{context_json}\n"
        artifact = ContextArtifact(
            ref=f"embedded:{purpose}",
            content_hash=stable_hash(context),
            delivery="embedded",
            purpose=purpose,
            content=context,
        )
        self.store.append_event(job_id, "codex_started", f"Starting fresh Codex session for {purpose}", stage=job_type)
        result = self.codex.run(
            job_id=job_id,
            job_type=job_type,
            purpose=purpose,
            prompt=prompt,
            output_schema=schema,
            artifacts=[artifact, *prompt_artifacts],
            caused_by_invocation_id=caused_by_invocation_id,
            context_budget=None,
        )
        self.store.append_event(
            job_id,
            "codex_completed",
            f"Codex session completed for {purpose}",
            stage=job_type,
            artifact_refs=[f"invocations/{result.invocation_id}"],
        )
        return result

    def _complete(self, job_id: str, final: dict[str, Any]) -> None:
        final_path = self.store.final_result_path(job_id)
        self.store.write_json(final_path, final)
        self.store.update_state(job_id, status="completed", final_artifact_ref="final/result.json")
        self.store.append_event(job_id, "completed", "Workflow completed", artifact_refs=["final/result.json"])
