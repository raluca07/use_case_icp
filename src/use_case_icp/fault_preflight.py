"""Unscored C07 Phase-A construction for the two-job workshop preflight."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping

from .codex_runner import CodexInvocationError, CodexRunner
from .etiq_executor import EtiqExecution, EtiqExecutor
from .fault_experiment import (
    PROTOCOL_CONTENT_HASH,
    PROTOCOL_VERSION,
    MAX_PACKAGE_BYTES,
    _digest,
    _encode,
    build_setup_record,
    build_stabilization_evidence,
    graph_selection_for_mode,
    materialize_realized_boundaries,
    persist_setup_record,
    validate_reference_attempt,
    validate_stabilization_replacement,
    validate_two_job_chain,
)
from .fault_injection import (
    FaultSelection,
    finalize_injection_after_captures,
    inject_after_clean_acceptance,
    persist_restricted_injection_records,
)
from .fault_operations import expand_direct_child
from .job_store import JobStore
from .records import (
    AgentRequest,
    ContextArtifact,
    GeneratedFile,
    GeneratedPipeline,
    RootJobState,
    jsonable,
    new_id,
    stable_hash,
)
from .review import frame_name


PREFLIGHT_JOB_IDS = (
    "market-demand-research",
    "coverage-prioritization-synthesis",
)

C07B_DECISION_RELATIVE_PATH = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "C07B_fault_blind_phase_a_retry_authorization.json"
)
C07B_DECISION_SHA256 = "2722a66f14a690e068ebd19f1f5a0a60a3d370e0b7b376c941c83a80965b062c"
C07B_MARKER_NAME = "protocol-1.3.1-c07b-phase-a-attempt.json"
C07B_CONSUMPTION_NAME = "c07b-authorization-consumption.json"
C07B_ENVIRONMENT_GATE_NAME = "c07b-environment-gate.json"
C07B_HISTORY_NAME = "c07b-phase-a-history.jsonl"
C07B_DIAGNOSTIC_NAME = "c07b-authorization-diagnostics.jsonl"
C07B_EXCLUDED_PREFLIGHTS = {
    "preflight-03420ef8721a4358": "4a1d6b02ef80a08b3ef8013096c91a8a8e00e89af7f537e7ec97a38a4dd2f8fb",
    "preflight-d06945d8ba2b4345": "af33dadd44d7aa53ed11ff8697281bdb92d6c1f2eb94c995bf0fecacc9960346",
}
C07D_DECISION_RELATIVE_PATH = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "C07D_fault_blind_phase_a_execution_authorization.json"
)
C07D_DECISION_SHA256 = "23df54d81dd176f24b1478177c81f4bfa8b6e49fb869785586817891498244ec"
C07D_MARKER_NAME = "protocol-1.3.1-c07d-phase-a-attempt.json"
C07D_CONSUMPTION_NAME = "c07d-authorization-consumption.json"
C07D_ENVIRONMENT_GATE_NAME = "c07d-environment-gate.json"
C07D_HISTORY_NAME = "c07d-phase-a-history.jsonl"
C07D_DIAGNOSTIC_NAME = "c07d-authorization-diagnostics.jsonl"
C07D_C07C_HANDOFF_RELATIVE_PATH = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "C07C_candidate_progression_to_overseer.email.md"
)
C07D_C07C_HANDOFF_SHA256 = "23bc3d9b55140d93dcab2f962122535cfa8827ffdfde999cf567fb3e1105bfd8"
C07D_BASELINE_CODE_SHA256 = "sha256:0dce68908e430d3ab3ddbfb56b5dcff41260ede7d8d7eb0ae2d1e60e5d54ddca"
C07D_EXCLUDED_PREFLIGHTS = {
    **C07B_EXCLUDED_PREFLIGHTS,
    "preflight-e8a6bd2f06fb4c58": "288704e7fe007f0fe56a7db6572efdd7bb9d0bde0b993473dfcdf37c91ad6d78",
}

AUTHORING_SCENARIO_KEYS = (
    "schema_version",
    "protocol_version",
    "protocol_content_hash",
    "scenario_id",
    "scored",
    "phase",
    "authoring_seed",
    "job_ids",
    "dependencies",
    "authoring_requirements",
    "limits",
    "redistribution",
    "corpus",
    "capabilities",
    "oracles",
)
CONTROLLER_MUTATION_FIELDS = frozenset(
    {"mutation", "fault_class", "function_name", "occurrence", "parameter", "seed"}
)


def load_preflight_scenario(
    repo_root: Path, *, include_controller_mutation: bool = True
) -> dict[str, Any]:
    root = (
        repo_root
        / "docs/experiments/2026-workshop-fault-localisation/fixtures/preflight"
    )
    scenario = json.loads((root / "scenario.json").read_text(encoding="utf-8"))
    corpus = json.loads((root / scenario["corpus_path"]).read_text(encoding="utf-8"))
    capabilities = json.loads(
        (root / scenario["capability_catalogue_path"]).read_text(encoding="utf-8")
    )
    oracles = json.loads((root / scenario["oracle_path"]).read_text(encoding="utf-8"))
    scenario["corpus"] = corpus
    scenario["capabilities"] = capabilities
    scenario["oracles"] = oracles
    if include_controller_mutation:
        scenario["controller_mutation"] = json.loads(
            (root / "restricted/mutation-plan.json").read_text(encoding="utf-8")
        )
    validate_preflight_scenario(scenario)
    return scenario


def validate_preflight_scenario(scenario: Mapping[str, Any]) -> None:
    if scenario.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("preflight scenario has a stale protocol version")
    if scenario.get("protocol_content_hash") != PROTOCOL_CONTENT_HASH:
        raise ValueError("preflight scenario has a stale protocol hash")
    if scenario.get("scored") is not False or scenario.get("phase") != "A":
        raise ValueError("C07 Phase A must be separately identified and unscored")
    jobs = tuple(str(value) for value in scenario.get("job_ids", []))
    if jobs != PREFLIGHT_JOB_IDS:
        raise ValueError("preflight scenario must use the frozen ordered two-job IDs")
    redistribution = scenario.get("redistribution", {})
    if (
        redistribution.get("status") != "approved_synthetic"
        or redistribution.get("live_http") is not False
        or any(
            redistribution.get(name) is not False
            for name in (
                "contains_secrets",
                "contains_identifying_metadata",
                "contains_copyrighted_full_pages",
            )
        )
    ):
        raise ValueError("preflight data does not satisfy the frozen redistribution policy")
    if not scenario.get("corpus", {}).get("records"):
        raise ValueError("preflight corpus is empty")
    if not scenario.get("capabilities", {}).get("capabilities"):
        raise ValueError("preflight capability catalogue is empty")
    if "controller_mutation" in scenario:
        mutation = scenario["controller_mutation"]
        if (
            mutation.get("storage_classification") != "restricted_controller_only"
            or mutation.get("protocol_version") != PROTOCOL_VERSION
            or mutation.get("protocol_content_hash") != PROTOCOL_CONTENT_HASH
        ):
            raise ValueError("preflight mutation plan is not bound controller-only data")


def author_visible_preflight_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Return the explicit author-visible allowlist, excluding future fault truth."""
    visible = {
        key: jsonable(scenario[key])
        for key in AUTHORING_SCENARIO_KEYS
        if key in scenario
    }
    leaked = CONTROLLER_MUTATION_FIELDS.intersection(visible)
    if leaked or "controller_mutation" in visible:
        raise ValueError(f"authoring context contains controller mutation fields: {sorted(leaked)}")
    encoded = json.dumps(visible, sort_keys=True, ensure_ascii=False)
    if "reverse_ordering" in encoded or '"occurrence"' in encoded:
        raise ValueError("authoring context discloses the future fault selection")
    return visible


def _artifact(ref: str, content: Any, purpose: str) -> ContextArtifact:
    return ContextArtifact(
        ref=ref,
        content_hash=stable_hash(content),
        delivery="embedded",
        purpose=purpose,
        content=content,
    )


def author_preflight_candidate(
    codex: CodexRunner,
    *,
    setup_job_id: str,
    repo_root: Path,
    scenario: Mapping[str, Any],
    candidate_number: int,
) -> tuple[dict[str, GeneratedPipeline], dict[str, Any], str, Mapping[str, Any]]:
    validate_reference_attempt(candidate_number, 0)
    prompt_template = (repo_root / "prompts/fault_chain_authoring.md").read_text(
        encoding="utf-8"
    )
    visible_scenario = author_visible_preflight_scenario(scenario)
    prompt = (
        prompt_template
        + "\n\nFrozen scenario and inputs:\n"
        + json.dumps(visible_scenario, sort_keys=True, ensure_ascii=False)
        + f"\n\nCandidate number: {candidate_number}. Authoring seed: {scenario['authoring_seed']}."
    )
    if "so the frozen preflight mutation can" in prompt or "reverse_ordering" in prompt:
        raise ValueError("authoring prompt discloses the future fault target")
    schema = json.loads(
        (repo_root / "schemas/fault_chain_authoring.schema.json").read_text(
            encoding="utf-8"
        )
    )
    result = None
    for infrastructure_attempt in range(1, 4):
        try:
            result = codex.run(
                job_id=setup_job_id,
                job_type="fault_preflight_authoring",
                purpose="c07_phase_a_authoring",
                prompt=prompt,
                output_schema=schema,
                artifacts=[
                    _artifact("prompt:fault_chain_authoring", prompt_template, "authoring rules"),
                    _artifact("scenario:preflight", visible_scenario, "frozen setup input"),
                ],
                excluded=[
                    {"ref": "repository-tree", "reason": "fresh-chain authoring boundary"},
                    {"ref": "pilot-source", "reason": "stored pipelines are ineligible"},
                    {
                        "ref": "controller:preflight-mutation-plan",
                        "reason": "future fault selection is controller-only until reference freeze",
                    },
                    {"ref": "reviewer-information", "reason": "Phase A makes no reviewer call"},
                ],
            )
            break
        except CodexInvocationError:
            if infrastructure_attempt == 3:
                raise
    assert result is not None
    jobs = {
        str(value["job_id"]): GeneratedPipeline.from_payload(value["pipeline"])
        for value in result.payload["jobs"]
    }
    if tuple(jobs) != PREFLIGHT_JOB_IDS:
        raise ValueError("authoring response did not return the exact ordered jobs")
    return jobs, dict(result.payload["complexity_claims"]), result.invocation_id, jsonable(result.usage)


def _parse_result(execution: EtiqExecution) -> dict[str, Any]:
    raw = (execution.run_dir / "pipeline-stdout.log").read_text(encoding="utf-8").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("job stdout is not exactly one JSON object") from exc
    if not isinstance(value, dict):
        raise RuntimeError("job output must be a JSON object")
    return value


def _validate_upstream(value: Mapping[str, Any], oracles: Mapping[str, Any]) -> None:
    if set(value) != {"normalized_demand", "provenance", "metadata"}:
        raise ValueError("upstream output schema is invalid")
    demand = value["normalized_demand"]
    provenance = value["provenance"]
    if not isinstance(demand, list) or not isinstance(provenance, list):
        raise ValueError("upstream artifacts must be arrays")
    required = set(oracles["required_need_ids"])
    if not required.issubset({str(item.get("need_id")) for item in demand}):
        raise ValueError("upstream stage oracle failed required needs")
    if len(demand) < int(oracles["minimum_demand_records"]):
        raise ValueError("upstream stage oracle failed demand count")
    if len(provenance) < int(oracles["minimum_provenance_records"]):
        raise ValueError("upstream stage oracle failed provenance count")


def _validate_downstream(value: Mapping[str, Any], oracles: Mapping[str, Any]) -> None:
    if set(value) != {"coverage", "priorities", "recommendation", "metadata"}:
        raise ValueError("downstream output schema is invalid")
    if len(value["priorities"]) < int(oracles["minimum_priorities"]):
        raise ValueError("downstream stage oracle failed priority count")
    statuses = {str(item.get("status")) for item in value["coverage"]}
    if not set(oracles["required_statuses"]).issubset(statuses):
        raise ValueError("downstream stage oracle failed coverage classes")
    if value["recommendation"].get("top_need_id") != oracles["expected_top_need_id"]:
        raise ValueError("downstream stage oracle failed top priority")


def oracle_report(
    upstream: Mapping[str, Any], downstream: Mapping[str, Any], oracles: Mapping[str, Any]
) -> dict[str, Any]:
    checks = {"upstream": False, "downstream": False, "end_to_end": False}
    errors: list[str] = []
    try:
        _validate_upstream(upstream, oracles["upstream"])
        checks["upstream"] = True
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    try:
        _validate_downstream(downstream, oracles["downstream"])
        checks["downstream"] = True
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    recommendation = downstream.get("recommendation", {})
    checks["end_to_end"] = (
        checks["upstream"]
        and checks["downstream"]
        and recommendation.get("decision") == oracles["end_to_end"]["expected_recommendation"]
        and recommendation.get("top_need_id") == oracles["end_to_end"]["expected_top_need_id"]
    )
    if not checks["end_to_end"] and not errors:
        errors.append("end-to-end oracle failed")
    return {"passed": all(checks.values()), "checks": checks, "errors": errors}


def execute_two_job_chain(
    etiq: EtiqExecutor,
    *,
    setup_job_id: str,
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    run_label: str,
) -> dict[str, Any]:
    upstream_id, downstream_id = PREFLIGHT_JOB_IDS
    for job_id in PREFLIGHT_JOB_IDS:
        try:
            for item in jobs[job_id].files:
                compile(item.content, item.path, "exec")
        except (SyntaxError, ValueError) as exc:
            raise RuntimeError(
                "candidate compilation/import validation failed",
                {
                    "failure_kind": "compile_import",
                    "failing_job_id": job_id,
                    "stderr": str(exc),
                },
            ) from exc
    try:
        upstream_execution = etiq.execute(
            job_id=upstream_id,
            segment_id="phase-a",
            stage=f"{run_label}-upstream",
            run_id=new_id("run"),
            pipeline=jobs[upstream_id],
            runtime_input={"corpus": scenario["corpus"]},
        )
        if not upstream_execution.reviewable:
            raise ValueError("Etiq produced no reviewable upstream capture")
        upstream_output = _parse_result(upstream_execution)
    except Exception as exc:
        raise RuntimeError(
            "upstream runtime validation failed",
            {
                "failure_kind": "runtime",
                "failing_job_id": upstream_id,
                "stderr": str(exc),
                "partial_capture": (
                    jsonable(upstream_execution.snapshot)
                    if "upstream_execution" in locals()
                    else None
                ),
            },
        ) from exc
    downstream_input = {
        "normalized_demand": upstream_output.get("normalized_demand"),
        "provenance": upstream_output.get("provenance"),
        "capabilities": scenario["capabilities"],
    }
    handoffs = []
    for name in ("normalized_demand", "provenance"):
        digest = _digest(_encode(upstream_output[name]))
        if _digest(_encode(downstream_input[name])) != digest:
            raise ValueError("downstream input did not preserve the exact upstream artifact")
        handoffs.append(
            {
                "handoff_ref": f"handoff-{name.replace('_', '-')}",
                "upstream_job_id": upstream_id,
                "downstream_job_id": downstream_id,
                "artifact_name": name,
                "artifact_sha256": digest,
                "provenance_type": "controller_recorded_exact_hash_handoff",
                "etiq_runtime_edge": False,
            }
        )
    try:
        downstream_execution = etiq.execute(
            job_id=downstream_id,
            segment_id="phase-a",
            stage=f"{run_label}-downstream",
            run_id=new_id("run"),
            pipeline=jobs[downstream_id],
            runtime_input=downstream_input,
        )
        if not downstream_execution.reviewable:
            raise ValueError("Etiq produced no reviewable downstream capture")
        downstream_output = _parse_result(downstream_execution)
    except Exception as exc:
        raise RuntimeError(
            "downstream runtime validation failed",
            {
                "failure_kind": "runtime",
                "failing_job_id": downstream_id,
                "stderr": str(exc),
                "completed_upstream_capture": jsonable(upstream_execution.snapshot),
                "completed_upstream_handoffs": handoffs,
                "partial_capture": (
                    jsonable(downstream_execution.snapshot)
                    if "downstream_execution" in locals()
                    else None
                ),
            },
        ) from exc
    validate_two_job_chain(
        PREFLIGHT_JOB_IDS, scenario["dependencies"], handoffs
    )
    return {
        "executions": {
            upstream_id: upstream_execution,
            downstream_id: downstream_execution,
        },
        "outputs": {upstream_id: upstream_output, downstream_id: downstream_output},
        "handoffs": handoffs,
        "oracle": oracle_report(
            upstream_output, downstream_output, scenario["oracles"]
        ),
    }


def stabilize_preflight_candidate(
    codex: CodexRunner,
    *,
    setup_job_id: str,
    repo_root: Path,
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    candidate_number: int,
    cycle: int,
    failure: Mapping[str, Any],
) -> tuple[dict[str, GeneratedPipeline], str, Mapping[str, Any], dict[str, Any]]:
    validate_reference_attempt(candidate_number, cycle)
    failing_job_id = str(failure["failing_job_id"])
    evidence = build_stabilization_evidence(
        failure_kind=str(failure["failure_kind"]),
        failing_job_id=failing_job_id,
        source=jsonable(jobs[failing_job_id].files),
        command=["etiq", "scan_code", jobs[failing_job_id].entry_file],
        exit_status=1,
        stdout=str(failure.get("stdout") or ""),
        stderr=str(failure.get("stderr") or ""),
        expected_interface={
            "entry_file": jobs[failing_job_id].entry_file,
            "review_boundaries": jobs[failing_job_id].review_boundaries,
            **(
                {
                    "required_output_keys": ["normalized_demand", "provenance", "metadata"],
                }
                if failing_job_id == PREFLIGHT_JOB_IDS[0]
                else {
                    "required_output_keys": ["coverage", "priorities", "recommendation", "metadata"],
                    "required_coverage_statuses": ["supported", "partial", "unsupported"],
                    "required_recommendation": {
                        "decision": "prioritize",
                        "top_need_id": "need-intermediate-state",
                    },
                }
            ),
        },
        frozen_schema_and_criteria=(
            {
                "scenario_id": scenario["scenario_id"],
                "failed_checks": list(failure.get("failed_checks", [])),
                "compact_diagnostics": dict(failure.get("compact_diagnostics", {})),
                "graph_evidence": "forbidden_for_validation_failure",
            }
            if failure["failure_kind"] == "validation"
            else {
                "scenario_id": scenario["scenario_id"],
                "expected_interface_only": True,
            }
        ),
        partial_capture=failure.get("partial_capture"),
        completed_upstream_capture=failure.get("completed_upstream_capture"),
        completed_upstream_handoffs=failure.get("completed_upstream_handoffs", []),
    )
    template = (repo_root / "prompts/fault_chain_stabilization.md").read_text(
        encoding="utf-8"
    )
    prompt = template + "\n\nFrozen stabilization evidence:\n" + json.dumps(
        evidence, sort_keys=True, ensure_ascii=False
    )
    schema = json.loads(
        (repo_root / "schemas/fault_chain_stabilization.schema.json").read_text(
            encoding="utf-8"
        )
    )
    result = codex.run(
        job_id=setup_job_id,
        job_type="fault_preflight_stabilization",
        purpose="c07_phase_a_stabilization",
        prompt=prompt,
        output_schema=schema,
        artifacts=[
            _artifact("prompt:fault_chain_stabilization", template, "setup repair rules"),
            _artifact("evidence:stabilization", evidence, "failing-job-only evidence"),
        ],
        excluded=[
            {"ref": "other-job-source", "reason": "job-scoped setup edit"},
            {"ref": "future-fault-target", "reason": "stabilization remains fault blind"},
            {"ref": "reviewer-information", "reason": "Phase A makes no reviewer call"},
        ],
    )
    if str(result.payload["failing_job_id"]) != failing_job_id:
        raise ValueError("stabilization response changed the failing job identity")
    replacements = dict(jobs)
    replacements[failing_job_id] = GeneratedPipeline.from_payload(
        result.payload["pipeline"]
    )
    validate_stabilization_replacement(
        jobs, replacements, failing_job_id=failing_job_id
    )
    return replacements, result.invocation_id, jsonable(result.usage), evidence


def _declarations(job_id: str, pipeline: GeneratedPipeline) -> list[dict[str, Any]]:
    return [
        {**value, "boundary_id": f"bnd-{stable_hash([job_id, value['function_name']])[:16]}"}
        for value in pipeline.review_boundaries
    ]


def complexity_report(
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    execution: Mapping[str, Any],
    claims: Mapping[str, Any],
) -> dict[str, Any]:
    required = scenario["authoring_requirements"]
    all_realized: dict[str, list[dict[str, Any]]] = {}
    full_bytes = 0
    selected_bytes = 0
    helper_names: set[str] = set()
    expandable_helpers: list[dict[str, Any]] = []
    expandable_helpers_by_job: dict[str, list[dict[str, Any]]] = {}
    helper_audit_by_job: dict[str, list[dict[str, Any]]] = {}
    for job_id in PREFLIGHT_JOB_IDS:
        snapshot = execution["executions"][job_id].snapshot
        declarations = _declarations(job_id, jobs[job_id])
        realized = materialize_realized_boundaries(snapshot, declarations)
        all_realized[job_id] = realized
        selected = graph_selection_for_mode(
            "etiq_selected_fixed", snapshot, realized, handoffs=execution["handoffs"]
        )
        full_bytes += len(_encode(jsonable(snapshot)))
        selected_bytes += len(_encode(selected))
        helper_names.update(
            prefix[-1]
            for boundary in realized
            for prefix in boundary["helper_prefixes"]
            if prefix
        )
        helper_audit = helper_eligibility_audit(
            snapshot,
            realized,
            handoffs=execution["handoffs"],
            max_expanded_bytes=min(
                int(scenario["limits"]["full_graph_max_bytes"]), MAX_PACKAGE_BYTES
            ),
        )
        helper_audit_by_job[job_id] = helper_audit
        eligible = [value for value in helper_audit if value["eligible"]]
        expandable_helpers_by_job[job_id] = eligible
        expandable_helpers.extend({**value, "job_id": job_id} for value in eligible)
    boundary_count = sum(len(value) for value in all_realized.values())
    ratio = selected_bytes / full_bytes if full_bytes else 1.0
    checks = {
        "exactly_two_jobs": tuple(jobs) == PREFLIGHT_JOB_IDS,
        "twelve_declarations": boundary_count == int(required["declared_boundaries"]),
        "two_exact_handoffs": len(execution["handoffs"]) >= 2,
        "join_or_aggregation": "join_demand_coverage" in {
            item["function_name"] for values in all_realized.values() for item in values
        },
        "two_expandable_nested_helpers": len(expandable_helpers)
        >= int(required["nested_helpers"]),
        "selected_materially_smaller": ratio
        <= float(scenario["limits"]["selected_to_full_max_ratio"]),
        "full_graph_fits": full_bytes <= int(scenario["limits"]["full_graph_max_bytes"]),
        "stage_and_end_to_end_oracles": execution["oracle"]["passed"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "declared_boundary_count": boundary_count,
        "observed_nested_helpers": sorted(helper_names),
        "operationally_expandable_helpers": expandable_helpers,
        "operationally_expandable_helpers_by_job": expandable_helpers_by_job,
        "helper_eligibility_audit_by_job": helper_audit_by_job,
        "author_helper_claims_used_for_eligibility": False,
        "full_graph_bytes": full_bytes,
        "selected_graph_bytes": selected_bytes,
        "selected_to_full_ratio": ratio,
        "realized_boundaries": all_realized,
    }


def operationally_expandable_helpers(
    snapshot: Any,
    realized_boundaries: list[dict[str, Any]],
    *,
    handoffs: list[dict[str, Any]],
    max_expanded_bytes: int = MAX_PACKAGE_BYTES,
) -> list[dict[str, Any]]:
    """Return eligible records from the complete captured-prefix audit."""
    return [
        value
        for value in helper_eligibility_audit(
            snapshot,
            realized_boundaries,
            handoffs=handoffs,
            max_expanded_bytes=max_expanded_bytes,
        )
        if value["eligible"]
    ]


def helper_eligibility_audit(
    snapshot: Any,
    realized_boundaries: list[dict[str, Any]],
    *,
    handoffs: list[dict[str, Any]],
    max_expanded_bytes: int = MAX_PACKAGE_BYTES,
) -> list[dict[str, Any]]:
    """Audit every collapsed prefix against all C07A helper predicates."""
    declared_prefixes = {
        tuple(str(item) for item in boundary["matched_prefix"])
        for boundary in realized_boundaries
    }
    audit: list[dict[str, Any]] = []
    for boundary in realized_boundaries:
        boundary_id = str(boundary["boundary_id"])
        parent_prefix = tuple(str(item) for item in boundary["matched_prefix"])
        fixed = graph_selection_for_mode(
            "etiq_selected_fixed", snapshot, [boundary], handoffs=handoffs
        )
        assert fixed is not None
        initial_nodes = set(fixed["node_refs"])
        initial_relationships = set(fixed["relationship_refs"])
        for collapsed in fixed["collapsed_helpers"]:
            prefix = tuple(str(item) for item in collapsed["func_stack"])
            exact_nodes = [
                node
                for node in snapshot.nodes
                if tuple(frame_name(str(item)) for item in node.func_stack)
                == prefix
            ]
            genuine_function_frame = bool(prefix) and ",#" not in prefix[-1]
            functiondef_nodes = [
                node for node in exact_nodes if node.scope_type == "FunctionDef"
            ]
            supporting_nodes = [
                node
                for node in functiondef_nodes
                if (
                    node.state_type.casefold().replace("_", "")
                    == "functionmapping"
                    or node.state_type.casefold().replace("_", "").endswith("state")
                )
            ]
            predicates = {
                "strict_descendant": len(prefix) > len(parent_prefix)
                and prefix[: len(parent_prefix)] == parent_prefix,
                "direct_child": prefix[:-1] == parent_prefix,
                "not_declared_prefix": prefix not in declared_prefixes,
                "genuine_function_frame": genuine_function_frame,
                "functiondef_scope": bool(functiondef_nodes),
                "captured_state_or_function_mapping": bool(supporting_nodes),
                "production_expansion_accepted": False,
                "within_frozen_budget": False,
                "adds_non_anchor_evidence": False,
            }
            expanded: dict[str, Any] | None = None
            expansion_error: str | None = None
            if all(
                predicates[name]
                for name in (
                    "strict_descendant",
                    "direct_child",
                    "not_declared_prefix",
                    "genuine_function_frame",
                    "functiondef_scope",
                    "captured_state_or_function_mapping",
                )
            ):
                package = {
                    "common_base": {
                        "section": {"assigned_boundary_ids": [boundary_id]}
                    },
                    "runtime_evidence": {
                        "collapsed_helpers": fixed["collapsed_helpers"]
                    },
                }
                binding = {
                    "protocol_content_hash": PROTOCOL_CONTENT_HASH,
                    "package_sha256": _digest(_encode(package)),
                    "snapshot_sha256": _digest(_encode(jsonable(snapshot))),
                    "realized_boundaries_sha256": _digest(_encode([boundary])),
                }
                binding["binding_sha256"] = _digest(_encode(binding))
                try:
                    expanded = expand_direct_child(
                        "etiq_selected_adaptive",
                        snapshot,
                        [boundary],
                        binding=binding,
                        package=package,
                        boundary_id=boundary_id,
                        requested_prefix=prefix,
                        handoffs=handoffs,
                    )
                    predicates["production_expansion_accepted"] = True
                except ValueError as exc:
                    expansion_error = str(exc)
            expanded = expanded or {"node_refs": [], "relationship_refs": []}
            added_nodes = sorted(set(expanded["node_refs"]) - initial_nodes)
            added_relationships = sorted(
                set(expanded["relationship_refs"]) - initial_relationships
            )
            expanded_bytes = len(_encode(expanded)) if predicates["production_expansion_accepted"] else None
            predicates["within_frozen_budget"] = bool(
                expanded_bytes is not None and expanded_bytes <= int(max_expanded_bytes)
            )
            predicates["adds_non_anchor_evidence"] = bool(
                added_nodes or added_relationships
            )
            rejection_reasons = [
                name for name, passed in predicates.items() if not passed
            ]
            if expansion_error:
                rejection_reasons.append("production_expansion_error")
            audit.append(
                {
                    "boundary_id": boundary_id,
                    "parent_boundary_prefix": list(parent_prefix),
                    "func_stack": list(prefix),
                    "supporting_node_refs": sorted(
                        node.node_ref for node in supporting_nodes
                    ),
                    "exact_prefix_node_refs": sorted(node.node_ref for node in exact_nodes),
                    "added_node_refs": added_nodes,
                    "added_relationship_refs": added_relationships,
                    "added_node_count": len(added_nodes),
                    "added_relationship_count": len(added_relationships),
                    "expanded_selection_bytes": expanded_bytes,
                    "max_expanded_bytes": int(max_expanded_bytes),
                    "predicates": predicates,
                    "eligible": not rejection_reasons,
                    "rejection_reasons": rejection_reasons,
                    "expansion_error": expansion_error,
                }
            )
    unique: dict[tuple[str, ...], dict[str, Any]] = {}
    for value in audit:
        prefix = tuple(value["func_stack"])
        if prefix not in unique or (value["eligible"] and not unique[prefix]["eligible"]):
            unique[prefix] = value
    return [unique[prefix] for prefix in sorted(unique)]


def _persist_record(
    restricted: Path,
    kind: str,
    setup_id: str,
    payload: Mapping[str, Any],
    usage: Mapping[str, Any] | None = None,
) -> Path:
    return persist_setup_record(
        build_setup_record(
            kind,
            setup_id=setup_id,
            job_ids=PREFLIGHT_JOB_IDS,
            payload=payload,
            usage=usage,
        ),
        restricted,
    )


def replay_failed_candidate_one_detector(failed_root: Path) -> dict[str, Any]:
    """Replay only the corrected detector over old Candidate 1 stored captures."""
    setup_store = failed_root / "restricted/setup-store"
    store = JobStore(setup_store)
    etiq = EtiqExecutor(store)
    stage_names = {
        PREFLIGHT_JOB_IDS[0]: "reference-c1-s3-upstream",
        PREFLIGHT_JOB_IDS[1]: "reference-c1-s3-downstream",
    }
    pipelines: dict[str, GeneratedPipeline] = {}
    snapshots: dict[str, Any] = {}
    upstream_output: dict[str, Any] | None = None
    for job_id, stage in stage_names.items():
        runs = list(
            (setup_store / job_id / "stages/phase-a" / stage / "runs").glob("*")
        )
        if len(runs) != 1:
            raise ValueError("preserved Candidate 1 replay requires one frozen run per job")
        run_dir = runs[0]
        manifest = json.loads(
            (run_dir / "pipeline-manifest.json").read_text(encoding="utf-8")
        )
        files = [
            GeneratedFile(
                str(path.relative_to(run_dir / "pipeline")),
                path.read_text(encoding="utf-8"),
            )
            for path in sorted((run_dir / "pipeline").rglob("*.py"))
        ]
        pipelines[job_id] = GeneratedPipeline(
            manifest["entry_file"], files, manifest["review_boundaries"]
        )
        snapshots[job_id] = etiq._load_snapshot(run_dir)
        if job_id == PREFLIGHT_JOB_IDS[0]:
            upstream_output = json.loads(
                (run_dir / "pipeline-stdout.log").read_text(encoding="utf-8")
            )
    assert upstream_output is not None
    handoffs = [
        {
            "handoff_ref": f"handoff-{name.replace('_', '-')}",
            "upstream_job_id": PREFLIGHT_JOB_IDS[0],
            "downstream_job_id": PREFLIGHT_JOB_IDS[1],
            "artifact_sha256": _digest(_encode(upstream_output[name])),
        }
        for name in ("normalized_demand", "provenance")
    ]
    eligible: list[dict[str, Any]] = []
    audit_by_job: dict[str, list[dict[str, Any]]] = {}
    for job_id in PREFLIGHT_JOB_IDS:
        realized = materialize_realized_boundaries(
            snapshots[job_id], _declarations(job_id, pipelines[job_id])
        )
        audit = helper_eligibility_audit(
            snapshots[job_id], realized, handoffs=handoffs
        )
        audit_by_job[job_id] = audit
        eligible.extend(
            {**value, "job_id": job_id}
            for value in audit
            if value["eligible"]
        )
    return {
        "source_preflight_id": failed_root.name,
        "source_candidate": 1,
        "purpose": "protocol_1_3_1_detector_regression_only",
        "retroactive_acceptance_permitted": False,
        "author_claims_consulted": False,
        "helper_eligibility_audit_by_job": audit_by_job,
        "operationally_expandable_helpers": eligible,
        "eligible_helper_count": len(eligible),
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_tree(root: Path, manifest_root: Path) -> str:
    """Match the archived GNU find/sort/sha256sum tree-hash convention."""
    found = subprocess.run(
        ["find", str(root), "-type", "f", "-printf", "%P\\0"],
        check=True,
        capture_output=True,
    ).stdout
    ordered = subprocess.run(
        ["sort", "-z"], check=True, input=found, capture_output=True
    ).stdout.split(b"\0")
    entries = bytearray()
    for encoded in ordered:
        if not encoded:
            continue
        relative = encoded.decode("utf-8")
        manifest_path = (root / relative).relative_to(manifest_root).as_posix()
        entries.extend(
            f"{_sha256_file(root / relative)}  {manifest_path}\n".encode("utf-8")
        )
    return hashlib.sha256(entries).hexdigest()


def _c07b_code_identity(repo_root: Path) -> dict[str, Any]:
    roots = [
        repo_root / "src",
        repo_root / "tests",
        repo_root / "prompts",
        repo_root / "schemas",
        repo_root / "docs/experiments/2026-workshop-fault-localisation/protocol",
        repo_root / "docs/experiments/2026-workshop-fault-localisation/fixtures/preflight",
    ]
    files = sorted(
        path
        for root in roots
        if root.exists()
        for path in root.rglob("*")
        if path.is_file()
    )
    manifest = [
        {
            "path": str(path.relative_to(repo_root)),
            "sha256": _sha256_file(path),
        }
        for path in files
    ]
    identity = {
        "files": manifest,
        "file_count": len(manifest),
        "code_and_dirty_tree_sha256": _digest(_encode(manifest)),
    }
    return identity


def _c07b_environment_identity() -> dict[str, Any]:
    try:
        etiq_version = importlib.metadata.version("etiq-copilot")
    except importlib.metadata.PackageNotFoundError:
        etiq_version = None
    details = {
        "interpreter": str(Path(sys.executable).absolute()),
        "python_version": sys.version,
        "platform": sys.platform,
        "etiq_copilot_version": etiq_version,
    }
    details["environment_sha256"] = _digest(_encode(details))
    return details


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(jsonable(payload), sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _create_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if path.exists():
            path.unlink()
        raise


def c07b_authorization_bindings(repo_root: Path, output_root: Path) -> dict[str, Any]:
    decision_path = repo_root / C07B_DECISION_RELATIVE_PATH
    decision_hash = _sha256_file(decision_path)
    if decision_hash != C07B_DECISION_SHA256:
        raise ValueError("C07B decision-file hash mismatch")
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if (
        decision.get("protocol", {}).get("protocol_version") != PROTOCOL_VERSION
        or decision.get("protocol", {}).get("protocol_content_hash")
        != PROTOCOL_CONTENT_HASH
        or decision.get("authorization", {}).get("additional_candidate_sets") != 1
    ):
        raise ValueError("C07B decision does not authorize this protocol and one set")

    scenario = load_preflight_scenario(repo_root, include_controller_mutation=False)
    fixture_root = repo_root / "docs/experiments/2026-workshop-fault-localisation/fixtures/preflight"
    actual_inputs = {
        "author_visible_scenario_sha256": _digest(
            _encode(author_visible_preflight_scenario(scenario))
        ),
        "authoring_prompt_sha256": "sha256:" + _sha256_file(
            repo_root / "prompts/fault_chain_authoring.md"
        ),
        "stabilization_prompt_sha256": "sha256:" + _sha256_file(
            repo_root / "prompts/fault_chain_stabilization.md"
        ),
        "controller_mutation_plan_sha256": "sha256:" + _sha256_file(
            fixture_root / "restricted/mutation-plan.json"
        ),
    }
    expected_inputs = {
        name: str(value)
        for name, value in decision["authorized_inputs"].items()
        if name.endswith("_sha256")
    }
    if actual_inputs != expected_inputs:
        raise ValueError("C07B authorized input hash mismatch")

    excluded_hashes: dict[str, str] = {}
    for preflight_id, expected_hash in C07B_EXCLUDED_PREFLIGHTS.items():
        excluded_root = output_root / preflight_id
        if not excluded_root.is_dir():
            raise ValueError(f"excluded preflight is absent: {preflight_id}")
        actual_hash = _sha256_tree(excluded_root, repo_root)
        if actual_hash != expected_hash:
            raise ValueError(f"excluded preflight tree changed: {preflight_id}")
        excluded_hashes[preflight_id] = actual_hash
    return {
        "decision_path": str(decision_path.relative_to(repo_root)),
        "decision_sha256": decision_hash,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "authorized_inputs": actual_inputs,
        "excluded_preflight_tree_sha256": excluded_hashes,
        "code_identity": _c07b_code_identity(repo_root),
        "environment_identity": _c07b_environment_identity(),
    }


def validate_c07b_environment_gate(
    output_root: Path,
    bindings: Mapping[str, Any],
    detector_replay: Mapping[str, Any],
) -> dict[str, Any]:
    gate_path = output_root / C07B_ENVIRONMENT_GATE_NAME
    if not gate_path.is_file():
        raise ValueError("C07B environment gate is absent")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    eligible = detector_replay["operationally_expandable_helpers"]
    replay_summary = sorted(
        (
            value["func_stack"][-1],
            value["added_node_count"],
            value["added_relationship_count"],
        )
        for value in eligible
    )
    required_replay = [
        ("demand_input_frame", 4, 6),
        ("provenance_input_frame", 4, 6),
    ]
    suite = gate.get("suite", {})
    if (
        gate.get("decision_sha256") != bindings["decision_sha256"]
        or gate.get("code_and_dirty_tree_sha256")
        != bindings["code_identity"]["code_and_dirty_tree_sha256"]
        or gate.get("environment_sha256")
        != bindings["environment_identity"]["environment_sha256"]
        or bindings["environment_identity"]["etiq_copilot_version"] != "2.3.0"
        or suite.get("returncode") != 0
        or suite.get("skipped") != 0
        or suite.get("real_etiq_contract_tests_passed") != 2
        or replay_summary != required_replay
        or gate.get("detector_replay_sha256") != _digest(_encode(detector_replay))
    ):
        raise ValueError("C07B environment gate does not match the current execution")
    return gate


def write_c07b_environment_gate(
    *,
    repo_root: Path,
    output_root: Path,
    suite_test_count: int,
    detector_replay: Mapping[str, Any],
) -> Path:
    """Record a successful zero-skip suite run for the current exact bindings."""
    bindings = c07b_authorization_bindings(repo_root, output_root)
    environment = bindings["environment_identity"]
    if environment["etiq_copilot_version"] != "2.3.0":
        raise ValueError("environment gate requires etiq-copilot==2.3.0")
    path = output_root / C07B_ENVIRONMENT_GATE_NAME
    _write_json(
        path,
        {
            "schema_version": "1",
            "decision_sha256": bindings["decision_sha256"],
            "code_and_dirty_tree_sha256": bindings["code_identity"]["code_and_dirty_tree_sha256"],
            "environment_sha256": environment["environment_sha256"],
            "environment_identity": environment,
            "suite": {
                "command": [str(Path(sys.executable).absolute()), "-m", "unittest", "discover", "-s", "tests", "-v"],
                "returncode": 0,
                "tests_run": int(suite_test_count),
                "skipped": 0,
                "real_etiq_contract_tests_passed": 2,
            },
            "detector_replay_sha256": _digest(_encode(detector_replay)),
        },
    )
    return path


def c07d_authorization_bindings(repo_root: Path, output_root: Path) -> dict[str, Any]:
    decision_path = repo_root / C07D_DECISION_RELATIVE_PATH
    decision_hash = _sha256_file(decision_path)
    if decision_hash != C07D_DECISION_SHA256:
        raise ValueError("C07D decision-file hash mismatch")
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    protocol = decision.get("protocol", {})
    authorization = decision.get("authorization", {})
    baseline = decision.get("verified_c07c_baseline", {})
    if (
        decision.get("decision_id")
        != "C07D-fault-blind-phase-a-execution-2026-08-28"
        or decision.get("decision_type")
        != "pre_results_phase_a_candidate_set_authorization"
        or decision.get("issued_by") != "Overseer"
        or protocol.get("protocol_version") != PROTOCOL_VERSION
        or protocol.get("protocol_content_hash") != PROTOCOL_CONTENT_HASH
        or protocol.get("protocol_change") is not False
        or authorization.get("additional_candidate_sets") != 1
        or authorization.get("maximum_candidates") != 3
        or authorization.get("maximum_stabilization_cycles_per_candidate") != 3
        or authorization.get("reviewer_model_calls_before_phase_a_acceptance") != 0
        or baseline.get("code_and_dirty_tree_sha256") != C07D_BASELINE_CODE_SHA256
        or str(baseline.get("c07c_handoff_sha256", "")).removeprefix("sha256:")
        != C07D_C07C_HANDOFF_SHA256
    ):
        raise ValueError("C07D decision fields do not authorize this execution")

    handoff_path = repo_root / C07D_C07C_HANDOFF_RELATIVE_PATH
    if _sha256_file(handoff_path) != C07D_C07C_HANDOFF_SHA256:
        raise ValueError("accepted C07C handoff hash mismatch")

    scenario = load_preflight_scenario(repo_root, include_controller_mutation=False)
    fixture_root = repo_root / "docs/experiments/2026-workshop-fault-localisation/fixtures/preflight"
    actual_inputs = {
        "author_visible_scenario_sha256": _digest(
            _encode(author_visible_preflight_scenario(scenario))
        ),
        "authoring_prompt_sha256": "sha256:" + _sha256_file(
            repo_root / "prompts/fault_chain_authoring.md"
        ),
        "stabilization_prompt_sha256": "sha256:" + _sha256_file(
            repo_root / "prompts/fault_chain_stabilization.md"
        ),
        "controller_mutation_plan_sha256": "sha256:" + _sha256_file(
            fixture_root / "restricted/mutation-plan.json"
        ),
    }
    expected_inputs = {
        name: str(value)
        for name, value in decision["authorized_inputs"].items()
        if name.endswith("_sha256")
    }
    if actual_inputs != expected_inputs:
        raise ValueError("C07D authorized input hash mismatch")

    expected_decision_trees = {
        value["preflight_id"]: str(value["tree_sha256"]).removeprefix("sha256:")
        for value in decision.get("preserved_preflights", [])
    }
    if expected_decision_trees != C07D_EXCLUDED_PREFLIGHTS:
        raise ValueError("C07D decision preserved-tree fields mismatch")
    excluded_hashes: dict[str, str] = {}
    for preflight_id, expected_hash in C07D_EXCLUDED_PREFLIGHTS.items():
        excluded_root = output_root / preflight_id
        if not excluded_root.is_dir():
            raise ValueError(f"excluded preflight is absent: {preflight_id}")
        actual_hash = _sha256_tree(excluded_root, repo_root)
        if actual_hash != expected_hash:
            raise ValueError(f"excluded preflight tree changed: {preflight_id}")
        excluded_hashes[preflight_id] = actual_hash
    return {
        "decision_path": str(decision_path.relative_to(repo_root)),
        "decision_sha256": decision_hash,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "c07c_handoff_sha256": C07D_C07C_HANDOFF_SHA256,
        "verified_c07c_baseline_code_sha256": C07D_BASELINE_CODE_SHA256,
        "authorized_inputs": actual_inputs,
        "excluded_preflight_tree_sha256": excluded_hashes,
        "code_identity": _c07b_code_identity(repo_root),
        "environment_identity": _c07b_environment_identity(),
    }


def validate_c07d_environment_gate(
    output_root: Path,
    bindings: Mapping[str, Any],
    detector_replay: Mapping[str, Any],
) -> dict[str, Any]:
    gate_path = output_root / C07D_ENVIRONMENT_GATE_NAME
    if not gate_path.is_file():
        raise ValueError("C07D environment gate is absent")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    replay_summary = sorted(
        (
            value["func_stack"][-1],
            value["added_node_count"],
            value["added_relationship_count"],
        )
        for value in detector_replay["operationally_expandable_helpers"]
    )
    suite = gate.get("suite", {})
    if (
        gate.get("decision_sha256") != bindings["decision_sha256"]
        or gate.get("code_and_dirty_tree_sha256")
        != bindings["code_identity"]["code_and_dirty_tree_sha256"]
        or gate.get("environment_sha256")
        != bindings["environment_identity"]["environment_sha256"]
        or gate.get("c07c_handoff_sha256") != bindings["c07c_handoff_sha256"]
        or gate.get("authorized_inputs") != bindings["authorized_inputs"]
        or gate.get("excluded_preflight_tree_sha256")
        != bindings["excluded_preflight_tree_sha256"]
        or bindings["environment_identity"]["etiq_copilot_version"] != "2.3.0"
        or suite.get("returncode") != 0
        or suite.get("skipped") != 0
        or suite.get("real_etiq_contract_tests_passed") != 2
        or replay_summary
        != [("demand_input_frame", 4, 6), ("provenance_input_frame", 4, 6)]
        or gate.get("detector_replay_sha256") != _digest(_encode(detector_replay))
    ):
        raise ValueError("C07D environment gate does not match the current execution")
    return gate


def write_c07d_environment_gate(
    *,
    repo_root: Path,
    output_root: Path,
    suite_test_count: int,
    detector_replay: Mapping[str, Any],
) -> Path:
    bindings = c07d_authorization_bindings(repo_root, output_root)
    environment = bindings["environment_identity"]
    if environment["etiq_copilot_version"] != "2.3.0":
        raise ValueError("environment gate requires etiq-copilot==2.3.0")
    path = output_root / C07D_ENVIRONMENT_GATE_NAME
    _write_json(
        path,
        {
            "schema_version": "1",
            "decision_sha256": bindings["decision_sha256"],
            "c07c_handoff_sha256": bindings["c07c_handoff_sha256"],
            "verified_c07c_baseline_code_sha256": bindings[
                "verified_c07c_baseline_code_sha256"
            ],
            "code_and_dirty_tree_sha256": bindings["code_identity"][
                "code_and_dirty_tree_sha256"
            ],
            "environment_sha256": environment["environment_sha256"],
            "environment_identity": environment,
            "authorized_inputs": bindings["authorized_inputs"],
            "excluded_preflight_tree_sha256": bindings[
                "excluded_preflight_tree_sha256"
            ],
            "suite": {
                "command": [
                    str(Path(sys.executable).absolute()),
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-v",
                ],
                "returncode": 0,
                "tests_run": int(suite_test_count),
                "skipped": 0,
                "real_etiq_contract_tests_passed": 2,
            },
            "detector_replay_sha256": _digest(_encode(detector_replay)),
        },
    )
    return path


def _inject_preflight_mutant(
    *,
    repo_root: Path,
    etiq: EtiqExecutor,
    setup_job_id: str,
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    execution: Mapping[str, Any],
    run_label: str,
) -> tuple[Any, Mapping[str, Any], Mapping[str, Any]]:
    """Load controller truth only after reference acceptance and run its gate."""
    mutation = json.loads(
        (
            repo_root
            / "docs/experiments/2026-workshop-fault-localisation/fixtures/preflight"
            / "restricted/mutation-plan.json"
        ).read_text(encoding="utf-8")
    )
    selection = FaultSelection(
        fault_class=mutation["fault_class"],
        function_name=mutation["function_name"],
        occurrence=int(mutation["occurrence"]),
        parameter=mutation["parameter"],
        seed=int(mutation["seed"]),
        job_id=mutation["job_id"],
    )
    validator_state: dict[str, Any] = {}
    validation_attempt = 0

    def validate_mutant(pipeline: GeneratedPipeline, truth: Any) -> Mapping[str, Any]:
        nonlocal validation_attempt
        validation_attempt += 1
        mutant_jobs = dict(jobs)
        mutant_jobs[selection.job_id] = pipeline
        result = execute_two_job_chain(
            etiq,
            setup_job_id=setup_job_id,
            scenario=scenario,
            jobs=mutant_jobs,
            run_label=f"{run_label}-{validation_attempt}",
        )
        selected_snapshot = result["executions"][selection.job_id].snapshot
        span = truth.site.mutant_span
        captured = any(
            selection.function_name
            in {frame_name(str(frame)) for frame in node.func_stack}
            and (
                node.line_no is None
                or int(span["start_line"])
                <= node.line_no
                <= int(span["end_line"]) + 1
            )
            for node in selected_snapshot.nodes
        )
        schema_valid = bool(result["outputs"][PREFLIGHT_JOB_IDS[1]].get("priorities"))
        flags = {
            "compile_success": True,
            "execution_success": True,
            "schema_valid": schema_valid,
            "mutated_statement_executed": captured,
            "plausible_final_result": schema_valid,
            "semantic_oracle_failed": not result["oracle"]["passed"],
            "executed_job_ids": list(PREFLIGHT_JOB_IDS),
            "oracle_report": result["oracle"],
            "mutation_execution_evidence": (
                "captured state in mutated span or immediate result-assignment line"
            ),
        }
        if all(
            flags[name] is True
            for name in (
                "compile_success",
                "execution_success",
                "schema_valid",
                "mutated_statement_executed",
                "plausible_final_result",
                "semantic_oracle_failed",
            )
        ):
            validator_state["result"] = result
        return flags

    outcome = inject_after_clean_acceptance(
        jobs[selection.job_id],
        reference_chain_accepted=True,
        fresh_chain=True,
        clean_control=False,
        clean_execution={
            "job_ids": list(PREFLIGHT_JOB_IDS),
            "oracle": execution["oracle"],
            "handoffs": execution["handoffs"],
        },
        expected_job_ids=PREFLIGHT_JOB_IDS,
        selection=selection,
        validator=validate_mutant,
    )
    mutant_execution = validator_state["result"]
    outcome = finalize_injection_after_captures(
        outcome,
        [mutant_execution["executions"][job_id].snapshot for job_id in PREFLIGHT_JOB_IDS],
    )
    return outcome, mutant_execution, mutation


def run_phase_a_preflight(
    *,
    repo_root: Path,
    output_root: Path,
    model: str,
    timeout_seconds: int = 1800,
    codex_factory: Callable[[JobStore], CodexRunner] | None = None,
    etiq_factory: Callable[[JobStore], EtiqExecutor] | None = None,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    attempt_marker = output_root / C07D_MARKER_NAME
    consumption_path = output_root / C07D_CONSUMPTION_NAME
    try:
        bindings = c07d_authorization_bindings(repo_root, output_root)
        failed_root = output_root / "preflight-03420ef8721a4358"
        detector_replay = replay_failed_candidate_one_detector(failed_root)
        environment_gate = validate_c07d_environment_gate(
            output_root, bindings, detector_replay
        )
    except Exception as exc:
        _append_jsonl(
            output_root / C07D_DIAGNOSTIC_NAME,
            {
                "status": "invalid_binding",
                "reason_type": type(exc).__name__,
                "reason": str(exc),
                "model_runner_constructed": False,
                "authorization_consumed": consumption_path.exists(),
            },
        )
        raise

    if attempt_marker.exists():
        marker = json.loads(attempt_marker.read_text(encoding="utf-8"))
        if not consumption_path.is_file():
            raise RuntimeError("C07D attempt marker exists without its consumption record")
        if (
            marker.get("decision_sha256") != bindings["decision_sha256"]
            or marker.get("consumption_record_sha256") != _sha256_file(consumption_path)
            or marker.get("code_and_dirty_tree_sha256")
            != bindings["code_identity"]["code_and_dirty_tree_sha256"]
            or marker.get("environment_sha256")
            != bindings["environment_identity"]["environment_sha256"]
        ):
            raise RuntimeError("C07D in-progress binding mismatch; refusing restart")
        existing_root = output_root / str(marker.get("preflight_id") or "")
        if (
            marker.get("status") == "consumed_in_progress"
            and (existing_root / "restricted/ledger/reference-execution-reference_execution.json").is_file()
        ):
            return resume_phase_a_mutation(
                repo_root=repo_root,
                output_root=output_root,
                marker=marker,
                timeout_seconds=timeout_seconds,
                etiq_factory=etiq_factory,
                attempt_marker=attempt_marker,
            )
        raise RuntimeError(
            f"C07D authorization already {marker.get('status', 'consumed')}; no new set permitted"
        )
    if consumption_path.exists():
        raise RuntimeError("C07D authorization was consumed without resumable attempt state")

    scenario = load_preflight_scenario(repo_root, include_controller_mutation=False)
    preflight_id = new_id("preflight")
    setup_job_id = new_id("setup")
    root = output_root / preflight_id
    consumption = {
        "schema_version": "1",
        "status": "consumed_in_progress",
        "decision_sha256": bindings["decision_sha256"],
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "preflight_id": preflight_id,
        "setup_id": setup_job_id,
        "authorized_candidate_sets_consumed": 1,
        "code_and_dirty_tree_sha256": bindings["code_identity"]["code_and_dirty_tree_sha256"],
        "environment_sha256": bindings["environment_identity"]["environment_sha256"],
        "authorized_inputs": bindings["authorized_inputs"],
        "excluded_preflight_tree_sha256": bindings["excluded_preflight_tree_sha256"],
        "c07c_handoff_sha256": bindings["c07c_handoff_sha256"],
        "verified_c07c_baseline_code_sha256": bindings[
            "verified_c07c_baseline_code_sha256"
        ],
    }
    _create_json_exclusive(consumption_path, consumption)
    consumption_hash = _sha256_file(consumption_path)
    marker = {
        **consumption,
        "consumption_record_sha256": consumption_hash,
    }
    _write_json(attempt_marker, marker)
    _append_jsonl(output_root / C07D_HISTORY_NAME, marker)
    restricted = root / "restricted"
    store = JobStore(restricted / "setup-store")
    store.initialize_job(
        AgentRequest(product="unscored C07 preflight", audience="workshop engineering"),
        RootJobState(job_id=setup_job_id, status="setup"),
    )
    codex = (
        codex_factory(store)
        if codex_factory
        else CodexRunner(store, model=model, timeout_seconds=timeout_seconds)
    )
    etiq = (
        etiq_factory(store)
        if etiq_factory
        else EtiqExecutor(store, timeout_seconds=timeout_seconds)
    )
    _persist_record(
        restricted / "ledger",
        "preflight",
        "setup-phase-a",
        {
            "preflight_id": preflight_id,
            "setup_id": setup_job_id,
            "phase": "A",
            "scored": False,
            "reviewer_model_calls": 0,
            "scenario_sha256": _digest(_encode(scenario)),
            "phase_b_status": "blocked_pending_c08_and_t02",
            "c07d_authorization": {
                "decision_sha256": bindings["decision_sha256"],
                "consumption_record_sha256": consumption_hash,
                "c07c_handoff_sha256": bindings["c07c_handoff_sha256"],
                "verified_c07c_baseline_code_sha256": bindings[
                    "verified_c07c_baseline_code_sha256"
                ],
                "code_identity": bindings["code_identity"],
                "environment_identity": bindings["environment_identity"],
                "environment_gate_sha256": _digest(_encode(environment_gate)),
                "authorized_inputs": bindings["authorized_inputs"],
                "excluded_preflight_tree_sha256": bindings["excluded_preflight_tree_sha256"],
            },
        },
    )
    _persist_record(
        restricted / "ledger",
        "complexity_gate",
        "old-candidate-one-detector",
        detector_replay,
    )

    accepted: dict[str, Any] | None = None
    rejection_log: list[dict[str, Any]] = []
    for candidate_number in range(1, 4):
        validate_reference_attempt(candidate_number, 0)
        try:
            jobs, claims, invocation_id, usage = author_preflight_candidate(
                codex,
                setup_job_id=setup_job_id,
                repo_root=repo_root,
                scenario=scenario,
                candidate_number=candidate_number,
            )
            _persist_record(
                restricted / "ledger",
                "authoring",
                f"author-{candidate_number:02d}",
                {
                    "candidate_number": candidate_number,
                    "invocation_id": invocation_id,
                    "job_bundle_sha256": {
                        job_id: _digest(_encode(jsonable(pipeline)))
                        for job_id, pipeline in jobs.items()
                    },
                    "fault_target_visible_to_author": False,
                    "author_visible_scenario_sha256": _digest(
                        _encode(author_visible_preflight_scenario(scenario))
                    ),
                },
                usage,
            )
            for cycle in range(0, 4):
                validate_reference_attempt(candidate_number, cycle)
                failure: dict[str, Any] | None = None
                helper_audit_recorded = False
                try:
                    execution = execute_two_job_chain(
                        etiq,
                        setup_job_id=setup_job_id,
                        scenario=scenario,
                        jobs=jobs,
                        run_label=f"reference-c{candidate_number}-s{cycle}",
                    )
                    report = complexity_report(scenario, jobs, execution, claims)
                    _persist_record(
                        restricted / "ledger",
                        "complexity_gate",
                        f"helper-audit-{candidate_number:02d}-{cycle:02d}",
                        {
                            "candidate_number": candidate_number,
                            "cycle": cycle,
                            "capture_status": "complete",
                            "author_claims_consulted": False,
                            "audit_by_job": report["helper_eligibility_audit_by_job"],
                        },
                    )
                    helper_audit_recorded = True
                    if execution["oracle"]["passed"] and report["passed"]:
                        try:
                            outcome, mutant_execution, mutation = _inject_preflight_mutant(
                                repo_root=repo_root,
                                etiq=etiq,
                                setup_job_id=setup_job_id,
                                scenario=scenario,
                                jobs=jobs,
                                execution=execution,
                                run_label=f"mutant-c{candidate_number}-s{cycle}-site",
                            )
                        except ValueError as exc:
                            mutation_rejection = {
                                "candidate_number": candidate_number,
                                "cycle": cycle,
                                "reason_type": type(exc).__name__,
                                "reason": str(exc),
                                "gate": "controller_only_mutation_gate",
                                "author_fault_target_visible": False,
                            }
                            rejection_log.append(mutation_rejection)
                            _persist_record(
                                restricted / "ledger",
                                "rejected_candidate",
                                f"mutation-reject-{candidate_number:02d}",
                                mutation_rejection,
                            )
                            break
                        accepted = {
                            "candidate_number": candidate_number,
                            "stabilization_cycles": cycle,
                            "jobs": jobs,
                            "claims": claims,
                            "execution": execution,
                            "complexity": report,
                            "outcome": outcome,
                            "mutant_execution": mutant_execution,
                            "mutation": mutation,
                        }
                        break
                    upstream_failed = not execution["oracle"]["checks"]["upstream"]
                    downstream_failed = not execution["oracle"]["checks"]["downstream"]
                    helper_counts = {
                        job_id: len(
                            report["operationally_expandable_helpers_by_job"].get(job_id, [])
                        )
                        for job_id in PREFLIGHT_JOB_IDS
                    }
                    if upstream_failed:
                        failing_job_id = PREFLIGHT_JOB_IDS[0]
                    elif downstream_failed:
                        failing_job_id = PREFLIGHT_JOB_IDS[1]
                    else:
                        failing_job_id = min(
                            PREFLIGHT_JOB_IDS,
                            key=lambda job_id: (helper_counts[job_id], job_id),
                        )
                    failure = {
                        "failure_kind": "validation",
                        "failing_job_id": failing_job_id,
                        "stderr": "reference oracle or complexity validation failed",
                        "failed_checks": [
                            name
                            for name, passed in {
                                **{
                                    f"oracle_{name}": passed
                                    for name, passed in execution["oracle"]["checks"].items()
                                },
                                **report["checks"],
                            }.items()
                            if not passed
                        ],
                        "compact_diagnostics": {
                            "oracle_errors": execution["oracle"]["errors"],
                            "expandable_helper_counts_by_job": helper_counts,
                            "selected_to_full_ratio": report["selected_to_full_ratio"],
                            "full_graph_bytes": report["full_graph_bytes"],
                            "selected_graph_bytes": report["selected_graph_bytes"],
                        },
                    }
                except RuntimeError as exc:
                    if len(exc.args) > 1 and isinstance(exc.args[1], Mapping):
                        failure = dict(exc.args[1])
                    else:
                        raise
                if not helper_audit_recorded:
                    _persist_record(
                        restricted / "ledger",
                        "complexity_gate",
                        f"helper-audit-{candidate_number:02d}-{cycle:02d}",
                        {
                            "candidate_number": candidate_number,
                            "cycle": cycle,
                            "capture_status": "unavailable_incomplete_execution",
                            "author_claims_consulted": False,
                            "audit_by_job": {},
                            "rejection_reasons": [
                                "complete_capture_required_for_helper_eligibility"
                            ],
                        },
                    )
                if cycle == 3:
                    raise ValueError("candidate exhausted three stabilization cycles")
                jobs, repair_invocation, repair_usage, evidence = stabilize_preflight_candidate(
                    codex,
                    setup_job_id=setup_job_id,
                    repo_root=repo_root,
                    scenario=scenario,
                    jobs=jobs,
                    candidate_number=candidate_number,
                    cycle=cycle + 1,
                    failure=failure,
                )
                _persist_record(
                    restricted / "ledger",
                    "stabilization_repair",
                    f"stabilize-{candidate_number:02d}-{cycle + 1:02d}",
                    {
                        "candidate_number": candidate_number,
                        "cycle": cycle + 1,
                        "invocation_id": repair_invocation,
                        "failing_job_id": failure["failing_job_id"],
                        "evidence": evidence,
                        "complete_two_job_rerun_required": True,
                    },
                    repair_usage,
                )
            if accepted is not None:
                break
        except Exception as exc:
            rejection_log.append(
                {
                    "candidate_number": candidate_number,
                    "reason_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
            _persist_record(
                restricted / "ledger",
                "rejected_candidate",
                f"reject-{candidate_number:02d}",
                rejection_log[-1],
            )
    if accepted is None:
        incomplete = {
            "schema_version": "1",
            "protocol_version": PROTOCOL_VERSION,
            "protocol_content_hash": PROTOCOL_CONTENT_HASH,
            "preflight_id": preflight_id,
            "status": "experiment_incomplete",
            "reason": "authorized Phase-A candidate set exhausted",
            "candidate_limit": 3,
            "stabilization_cycle_limit": 3,
            "reviewer_model_calls": 0,
            "requirements_weakened": False,
            "rejections": rejection_log,
            "preserved_failed_preflight": failed_root.name,
            "detector_replay": detector_replay,
            "setup_usage": store.update_usage_summary(setup_job_id),
        }
        root.mkdir(parents=True, exist_ok=True)
        (root / "phase-a-incomplete.json").write_text(
            json.dumps(incomplete, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        marker = {
            **json.loads(attempt_marker.read_text(encoding="utf-8")),
            "status": "experiment_incomplete",
            "outcome_ref": str(root / "phase-a-incomplete.json"),
        }
        _write_json(attempt_marker, marker)
        _append_jsonl(output_root / C07D_HISTORY_NAME, marker)
        raise RuntimeError(
            f"authorized Phase-A candidate set exhausted; experiment frozen incomplete at {root}"
        )

    jobs = accepted["jobs"]
    execution = accepted["execution"]
    _persist_record(
        restricted / "ledger",
        "reference_execution",
        "reference-execution",
        {
            "candidate_number": accepted["candidate_number"],
            "sources": {job_id: jsonable(value) for job_id, value in jobs.items()},
            "outputs": execution["outputs"],
            "snapshots": {
                job_id: jsonable(value.snapshot)
                for job_id, value in execution["executions"].items()
            },
            "handoffs": execution["handoffs"],
        },
    )
    _persist_record(
        restricted / "ledger",
        "reference_oracle",
        "reference-oracle",
        execution["oracle"],
    )
    _persist_record(
        restricted / "ledger",
        "complexity_gate",
        "complexity-gate",
        accepted["complexity"],
    )

    mutation = accepted["mutation"]
    outcome = accepted["outcome"]
    mutant_execution = accepted["mutant_execution"]
    selection = FaultSelection(
        fault_class=mutation["fault_class"],
        function_name=mutation["function_name"],
        occurrence=int(mutation["occurrence"]),
        parameter=mutation["parameter"],
        seed=int(mutation["seed"]),
        job_id=mutation["job_id"],
    )
    persist_restricted_injection_records(
        outcome, restricted / "injection", require_final=True
    )
    fixture = {
        "schema_version": "1",
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "preflight_id": preflight_id,
        "phase": "A",
        "scored": False,
        "reviewer_model_calls": 0,
        "phase_b_status": "blocked_pending_c08_runner_and_t02_signature",
        "scenario": {**scenario, "controller_mutation": mutation},
        "reference": {
            "jobs": {job_id: jsonable(value) for job_id, value in jobs.items()},
            "oracle": execution["oracle"],
            "handoffs": execution["handoffs"],
            "complexity": accepted["complexity"],
            "snapshots": {
                job_id: jsonable(execution["executions"][job_id].snapshot)
                for job_id in PREFLIGHT_JOB_IDS
            },
        },
        "mutant": {
            "jobs": {
                job_id: jsonable(
                    outcome.evaluation_pipeline if job_id == selection.job_id else jobs[job_id]
                )
                for job_id in PREFLIGHT_JOB_IDS
            },
            "outputs": mutant_execution["outputs"],
            "handoffs": mutant_execution["handoffs"],
            "snapshots": {
                job_id: jsonable(mutant_execution["executions"][job_id].snapshot)
                for job_id in PREFLIGHT_JOB_IDS
            },
            "ground_truth_ref": "restricted/injection/ground-truth.json",
        },
        "restricted_sentinels": {
            "repository": str(repo_root.resolve()),
            "controller": str(restricted.resolve()),
            "common_capture": str((restricted / "setup-store").resolve()),
            "ground_truth": str((restricted / "injection/ground-truth.json").resolve()),
        },
        "rejections": rejection_log,
        "protocol_1_3_0_candidate_1_detector_replay": detector_replay,
    }
    fixture["fixture_sha256"] = _digest(_encode(fixture))
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase-a-fixture.json").write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    marker = {
        **json.loads(attempt_marker.read_text(encoding="utf-8")),
        "status": "phase_a_passed",
        "outcome_ref": str(root / "phase-a-fixture.json"),
        "fixture_sha256": fixture["fixture_sha256"],
    }
    _write_json(attempt_marker, marker)
    _append_jsonl(output_root / C07D_HISTORY_NAME, marker)
    return root


def resume_phase_a_mutation(
    *,
    repo_root: Path,
    output_root: Path,
    marker: Mapping[str, Any],
    timeout_seconds: int,
    etiq_factory: Callable[[JobStore], EtiqExecutor] | None = None,
    attempt_marker: Path | None = None,
) -> Path:
    """Resume the same accepted reference after controller-only finalization failure."""
    preflight_id = str(marker["preflight_id"])
    root = output_root / preflight_id
    restricted = root / "restricted"
    store = JobStore(restricted / "setup-store")
    etiq = (
        etiq_factory(store)
        if etiq_factory
        else EtiqExecutor(store, timeout_seconds=timeout_seconds)
    )
    setup_jobs = list((restricted / "setup-store").glob("setup-*"))
    if len(setup_jobs) != 1:
        raise RuntimeError("mutation resume requires one existing setup job")
    setup_job_id = setup_jobs[0].name
    reference_record = json.loads(
        (restricted / "ledger/reference-execution-reference_execution.json").read_text(
            encoding="utf-8"
        )
    )["payload"]
    oracle = json.loads(
        (restricted / "ledger/reference-oracle-reference_oracle.json").read_text(
            encoding="utf-8"
        )
    )["payload"]
    complexity = json.loads(
        (restricted / "ledger/complexity-gate-complexity_gate.json").read_text(
            encoding="utf-8"
        )
    )["payload"]
    detector_replay = json.loads(
        (
            restricted
            / "ledger/old-candidate-one-detector-complexity_gate.json"
        ).read_text(encoding="utf-8")
    )["payload"]
    scenario = load_preflight_scenario(repo_root)
    jobs = {
        job_id: GeneratedPipeline.from_payload(reference_record["sources"][job_id])
        for job_id in PREFLIGHT_JOB_IDS
    }
    mutation = scenario["controller_mutation"]
    selection = FaultSelection(
        fault_class=mutation["fault_class"],
        function_name=mutation["function_name"],
        occurrence=int(mutation["occurrence"]),
        parameter=mutation["parameter"],
        seed=int(mutation["seed"]),
        job_id=mutation["job_id"],
    )
    validator_state: dict[str, Any] = {}
    validation_attempt = 0

    def validate_mutant(pipeline: GeneratedPipeline, truth: Any) -> Mapping[str, Any]:
        nonlocal validation_attempt
        validation_attempt += 1
        mutant_jobs = dict(jobs)
        mutant_jobs[selection.job_id] = pipeline
        result = execute_two_job_chain(
            etiq,
            setup_job_id=setup_job_id,
            scenario=scenario,
            jobs=mutant_jobs,
            run_label=f"mutant-resume-site-{validation_attempt}",
        )
        selected_snapshot = result["executions"][selection.job_id].snapshot
        span = truth.site.mutant_span
        captured = any(
            selection.function_name
            in {frame_name(str(frame)) for frame in node.func_stack}
            and (
                node.line_no is None
                or int(span["start_line"])
                <= node.line_no
                <= int(span["end_line"]) + 1
            )
            for node in selected_snapshot.nodes
        )
        schema_valid = bool(result["outputs"][PREFLIGHT_JOB_IDS[1]].get("priorities"))
        flags = {
            "compile_success": True,
            "execution_success": True,
            "schema_valid": schema_valid,
            "mutated_statement_executed": captured,
            "plausible_final_result": schema_valid,
            "semantic_oracle_failed": not result["oracle"]["passed"],
            "executed_job_ids": list(PREFLIGHT_JOB_IDS),
            "oracle_report": result["oracle"],
            "mutation_execution_evidence": (
                "captured state in mutated span or immediate result-assignment line"
            ),
        }
        if all(
            flags[name] is True
            for name in (
                "compile_success",
                "execution_success",
                "schema_valid",
                "mutated_statement_executed",
                "plausible_final_result",
                "semantic_oracle_failed",
            )
        ):
            validator_state["result"] = result
        return flags

    _persist_record(
        restricted / "ledger",
        "preflight",
        "mutation-finalization-resume",
        {
            "resume_scope": "same_authorized_candidate_set_and_accepted_reference",
            "reason": "canonical frame suffix and immediate result-line resolution correction",
            "new_authoring_candidate": False,
            "reviewer_model_calls": 0,
        },
    )
    outcome = inject_after_clean_acceptance(
        jobs[selection.job_id],
        reference_chain_accepted=True,
        fresh_chain=True,
        clean_control=False,
        clean_execution={
            "job_ids": list(PREFLIGHT_JOB_IDS),
            "oracle": oracle,
            "handoffs": reference_record["handoffs"],
        },
        expected_job_ids=PREFLIGHT_JOB_IDS,
        selection=selection,
        validator=validate_mutant,
    )
    mutant_execution = validator_state["result"]
    outcome = finalize_injection_after_captures(
        outcome,
        [
            mutant_execution["executions"][job_id].snapshot
            for job_id in PREFLIGHT_JOB_IDS
        ],
    )
    persist_restricted_injection_records(
        outcome, restricted / "injection", require_final=True
    )
    rejection_records = [
        json.loads(path.read_text(encoding="utf-8"))["payload"]
        for path in sorted((restricted / "ledger").glob("reject-*-rejected_candidate.json"))
    ]
    fixture = {
        "schema_version": "1",
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "preflight_id": preflight_id,
        "phase": "A",
        "scored": False,
        "reviewer_model_calls": 0,
        "phase_b_status": "blocked_pending_c08_runner_and_t02_signature",
        "scenario": scenario,
        "reference": {
            "jobs": reference_record["sources"],
            "oracle": oracle,
            "handoffs": reference_record["handoffs"],
            "complexity": complexity,
            "snapshots": reference_record["snapshots"],
        },
        "mutant": {
            "jobs": {
                job_id: jsonable(
                    outcome.evaluation_pipeline if job_id == selection.job_id else jobs[job_id]
                )
                for job_id in PREFLIGHT_JOB_IDS
            },
            "outputs": mutant_execution["outputs"],
            "handoffs": mutant_execution["handoffs"],
            "snapshots": {
                job_id: jsonable(mutant_execution["executions"][job_id].snapshot)
                for job_id in PREFLIGHT_JOB_IDS
            },
            "ground_truth_ref": "restricted/injection/ground-truth.json",
        },
        "restricted_sentinels": {
            "repository": str(repo_root.resolve()),
            "controller": str(restricted.resolve()),
            "common_capture": str((restricted / "setup-store").resolve()),
            "ground_truth": str((restricted / "injection/ground-truth.json").resolve()),
        },
        "rejections": rejection_records,
        "protocol_1_3_0_candidate_1_detector_replay": detector_replay,
        "controller_resume": {
            "new_candidate_set": False,
            "new_reference_candidate": False,
            "reviewer_model_calls": 0,
        },
    }
    fixture["fixture_sha256"] = _digest(_encode(fixture))
    (root / "phase-a-fixture.json").write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    attempt_marker = attempt_marker or output_root / "protocol-1.3.1-phase-a-attempt.json"
    terminal = {
        **dict(marker),
        "status": "phase_a_passed",
        "outcome_ref": str(root / "phase-a-fixture.json"),
        "fixture_sha256": fixture["fixture_sha256"],
        "controller_resume_count": 1,
    }
    _write_json(attempt_marker, terminal)
    if attempt_marker.name == C07D_MARKER_NAME:
        _append_jsonl(output_root / C07D_HISTORY_NAME, terminal)
    return root
