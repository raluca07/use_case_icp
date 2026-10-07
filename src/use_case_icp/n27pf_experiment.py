"""N27PF priority-semantics-corrected native-Etiq pilot (Attempt 050)."""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping

from . import corrected_experiment as ce
from . import n25_experiment as n25
from . import n27p_experiment as n27p
from . import n27pa_experiment as n27pa
from . import n27pb_experiment as pb
from . import n27pe_experiment as pe


_PE_CONFIGURE = pe._configure_base
_PE_FIXTURE = pe._fixture
_PE_ORACLE = pe._hidden_oracle
_PE_MUTANT_SOURCE = pe._mutant_source
_PE_PIPELINE = pe._pipeline
_PE_JOB_INPUT = pe._job_input
_PE_VALIDATE_OUTPUT = pe._validate_business_output
_PE_RUN_PIPELINE = pe._run_pipeline_sources
_PE_CONTROL_INVARIANTS = pe._control_invariants
_PE_CAPTURE = pe._capture_instance
_PE_CATALOGUE = pe._catalogue
_PE_CONNECTED_HANDOFFS = pe._connected_handoffs
_PE_HANDOFF_QUALIFICATION = pe._capture_handoff_qualification
_PE_HARD_FAULT_QUALIFICATION = pe._hard_fault_qualification
_PE_LOAD_PREPARED = pe._load_prepared
_PE_BASE_PACKAGE = pe._base_package
_PE_BUILD_PACKAGE = pe.build_package
_PE_PACKAGE_RECORDS = pe._package_records
_PE_INITIAL_EVIDENCE = pe._initial_evidence
_PE_PAIRWISE_CHECKS = pe._pairwise_checks
_PE_RENDER_REQUEST = pe.render_request
_PE_VALIDATE_SCHEMAS = pe.validate_schemas
_PE_LEAKAGE_AUDIT = pe._leakage_audit
_PE_QUALIFY_PACKAGES = pe.qualify_packages
_PE_PREPARE = pe.prepare_attempt
_PE_BUILD_ATTEMPT = pe.build_attempt
_PE_VALIDATE_RESPONSE = pe.validate_response
_PE_SCORE_RESPONSE = pe.score_response
_PE_RUN_REVIEW = pe.run_review_session
_PE_RECONSTRUCT_COUNTS = pe.reconstruct_counts
_PE_ACTUAL_USAGE = pe._actual_usage
_PE_ANALYSIS_ROWS = pe._analysis_rows
_PE_SUMMARY = pe._summary
_PE_CONTRAST = pe._contrast
_PE_FALSE_POSITIVE_RATIONALE = pe._false_positive_rationale
_PE_WRITE_ANALYSIS = pe.write_analysis
_PE_EXECUTE_LIFECYCLE = pe.execute_lifecycle


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-050")
ATTEMPT_049 = Path("outputs/fault-experiments-v2-2-n10/attempt-049")
TASK = Path("instructions_between_agent_types/developer/current/N27PF_priority_semantics_correction_and_complete_pilot.email.md")
TASK_SHA256 = "sha256:8e3e3c58e6f962510486c073448f35692e4c12e314b603a595e28c532b0bfbc4"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PF_priority_semantics_correction_and_complete_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:bd6c29b8cdd804ce53be89754d772596b9c22f126892eb9927527878c3c1ccc8"
JOB1_SOURCE = Path("src/use_case_icp/n27pe_market_evidence.py")
JOB2_SOURCE = Path("src/use_case_icp/n27pf_opportunity_priority.py")
OLD_JOB2_SOURCE = Path("src/use_case_icp/n27pd_opportunity_priority.py")
JOB3_SOURCE = Path("src/use_case_icp/n27pe_campaign_allocation.py")
JOB4_SOURCE = Path("src/use_case_icp/n27pe_activation_schedule.py")
PROMPT = Path("prompts/v2_2/n27pe_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n27pe_final.schema.json")
GROUP_SCHEMA = Path("schemas/v2_2/n27pe_choose_group.schema.json")
ARTIFACT_SCHEMA = Path("schemas/v2_2/n27pe_choose_artifact.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n27pe_reconsider.schema.json")
ORACLE_FREEZE = Path("qualification/hidden-oracle-freeze.json")
CALIBRATION = "calibration-clean-02"
SANDBOX_GATE = pb.SANDBOX_GATE
SANDBOX_GATE_SHA256 = pb.SANDBOX_GATE_SHA256

JOB_ORDER = n25.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
INSTANCES = pe.INSTANCES
TRUTH = deepcopy(pe.TRUTH)
MATCHED_CLEAN = deepcopy(pe.MATCHED_CLEAN)
MUTATIONS = deepcopy(pe.MUTATIONS)
CELLS = pe.CELLS
MODE_NAMES = pe.MODE_NAMES
CALLS_BY_MODE = pe.CALLS_BY_MODE
BUSINESS_BRIEF = pe.BUSINESS_BRIEF
INTERFACE_DESCRIPTION = deepcopy(pe.INTERFACE_DESCRIPTION)
INTERFACE_DESCRIPTION["priority_units"] = {
    "evidence_component": "evidence priority points equal full_precision_score multiplied by the supplied coverage_multiplier and by 0.1",
    "margin_component": "margin priority points equal estimated_revenue multiplied by margin_rate and divided by 10000",
}
INTERFACE_DESCRIPTION["campaign_budget"] = "requested budget equals the supplied base plus expected impact times the supplied multiplier, rounded to the nearest 100 currency units; supplied total and channel caps constrain allocation"
INTERFACE_DESCRIPTION["activation_allocation"] = "each campaign's allocation and expected impact are divided across its selected available windows"

ATTEMPT_049_HASHES = {
    "terminal-state.json": "sha256:9ceb279befb51bb4da7979d25ad16d4517268f6f4f255e07229d950757d8e300",
    "calibration/disposition-round-2.json": "sha256:ce60b83c1ba61ec7e17742c8bd971955a375cbf6bcf307210b1bd54e365c1057",
    "calibration/round-2/results/calibration-current.json": "sha256:5895f7c9db5e2a72708887a889d34de302bbedea810d109c68ce8a1a41b1d119",
    "calibration/round-2/results/calibration-compact-semantic.json": "sha256:3747b371f26fa3b600f1e23ecec81f075b9d67cc6d572e7a79f4d7e2a70aa08e",
}
REUSED_HASHES = {
    JOB1_SOURCE.as_posix(): "sha256:24d446da8fec7833afcc624576a0ac805d3e87b995bbdfa08b2d1050a224b26c",
    JOB3_SOURCE.as_posix(): "sha256:27ddd5e24d409fee91b443b66ce731398bca6ba9c526b3b0eef0c0f54beea66b",
    JOB4_SOURCE.as_posix(): "sha256:35e4739828272ac1c51978df1ef044c6f21a88c90ec5b0eae080c48d5f8b602f",
    PROMPT.as_posix(): "sha256:9f54796c4468b8759a904d390265edf7004f5e73d1afcc37c82ff1839f1acaa8",
    FINAL_SCHEMA.as_posix(): "sha256:28b3c172a7aa839da5e86241559251b015ca8f7cf5b5cb0b790ec4ac67da5d6b",
    GROUP_SCHEMA.as_posix(): "sha256:76090dda91bbcd0b10ca23cd832a163afeda96e5c568b34ec1d339ebaa59cb8a",
    ARTIFACT_SCHEMA.as_posix(): "sha256:f59c155d743a0a9188e42cef67973c0c3e66650cd3c9eeed6793ac70875c4b7b",
    RECONSIDER_SCHEMA.as_posix(): "sha256:1e4fd04e723291f0dd62b95ecd8b073a43663bceb3592a04589d6157cccb2aef",
}
PROTECTED_HASHES = {
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
}


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    pe._write_text(path, value)


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PF authority changed: {relative}")
    for relative, expected in {**REUSED_HASHES, **PROTECTED_HASHES}.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"bound reused/protected file changed: {relative}")
    for relative, expected in ATTEMPT_049_HASHES.items():
        if ce.sha256((repo_root / ATTEMPT_049 / relative).read_bytes()) != expected:
            raise ValueError(f"Attempt 049 preservation binding changed: {relative}")
    if ce.sha256((repo_root / SANDBOX_GATE).read_bytes()) != SANDBOX_GATE_SHA256:
        raise ValueError("signed artifact sandbox gate changed")
    sandbox = {
        "artifact_python_worker_sha256": ce.sha256(pb.operations._ARTIFACT_PYTHON_WORKER.encode()),
        "production_launcher_sha256": pb.operations.production_launcher_sha256(pb.operations.artifact_python_launcher),
        "launch_policy_sha256": pb.operations.ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
    }
    expected = {
        "artifact_python_worker_sha256": "sha256:8e9307c764bb5e9f6511dc96fdc32a5adb3202df6bf0968c0b8522b6c74c98b5",
        "production_launcher_sha256": "sha256:fe8216b7c45091bffecfb1f304c3947548f7a1175fe03ad7c82d506bacc0ba83",
        "launch_policy_sha256": "sha256:ca9a3d0c25ce256c5e2d0ad7e9744d53803bfdc2028043c2839b25b2b8a094c9",
    }
    if sandbox != expected or (ce.PROVIDER_MODEL, ce.PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise ValueError("protected execution binding changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "sandbox": sandbox}


def input_for(instance: str) -> dict[str, Any]:
    if instance == CALIBRATION:
        value = deepcopy(_PE_FIXTURE("verdant", 1.13))
        for row in value["market_observations"]:
            row["ingested_at"] = row["effective_date"]
        return value
    return deepcopy(_PE_FIXTURE("northstar", 0.37) if instance == INSTANCES[1] else _PE_FIXTURE("lumen", 0.0))


def _hidden_oracle(root: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Extend the independent oracle with the corrected single-count downstream formula."""
    job1 = deepcopy(_PE_ORACLE(root)[JOB1])
    opportunities = job1["opportunities"]
    attribution = job1["evidence_attribution"]
    coverage = {row["segment"]: row for row in root["capability_coverage"]}
    commercial = {row["opportunity_id"]: row for row in root["commercial_context"]}
    support: dict[str, list[dict[str, Any]]] = {}
    for row in attribution:
        support.setdefault(row["opportunity_id"], []).append(row)
    portfolio = []
    for row in opportunities:
        retained = support[row["opportunity_id"]]
        total = sum(Decimal(str(item["contribution_score"])) for item in retained)
        if abs(Decimal(str(row["full_precision_score"])) - total) > Decimal("0.000000001"):
            raise ValueError("oracle attribution identity mismatch")
        priority = float((
            Decimal(str(row["full_precision_score"])) * Decimal(str(coverage[row["segment"]]["coverage_multiplier"])) * Decimal("0.1")
            + Decimal(str(row["estimated_revenue"])) * Decimal(str(commercial[row["opportunity_id"]]["margin_rate"])) / Decimal("10000")
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
        portfolio.append({
            "opportunity_id": row["opportunity_id"], "segment": row["segment"],
            "campaign_id": row["campaign_id"], "channel_hint": row["channel_hint"],
            "priority_score": priority, "estimated_revenue": row["estimated_revenue"],
            "coverage_tier": coverage[row["segment"]]["coverage_tier"],
            "attributed_source_count": len({item["source_id"] for item in retained}),
        })
    portfolio.sort(key=lambda row: (-row["priority_score"], -next(item["reported_score"] for item in opportunities if item["opportunity_id"] == row["opportunity_id"]), row["opportunity_id"]))
    for index, row in enumerate(portfolio, 1):
        row["portfolio_position"] = index
    job2 = {
        "priority_portfolio": portfolio, "evidence_attribution": attribution,
        "metadata": {"portfolio_count": len(portfolio), "attribution_count": len(attribution), "consumed_handoffs": ["opportunities", "evidence_attribution", "metadata"]},
    }
    campaigns: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in portfolio:
        campaigns.setdefault((row["campaign_id"], row["segment"], row["channel_hint"]), []).append(row)
    audience = {row["segment"]: row["audience_size"] for row in root["audience_economics"]}
    economics = {row["channel"]: row["conversion_rate"] for row in root["channel_economics"]}
    candidates = []
    for (campaign, segment, channel), rows in sorted(campaigns.items()):
        combined = sum(row["priority_score"] for row in rows)
        candidates.append({
            "campaign_id": campaign, "segment": segment, "channel": channel,
            "opportunity_count": len({row["opportunity_id"] for row in rows}),
            "expected_impact": round(combined * audience[segment] / 10000.0 * economics[channel], 4),
        })
    candidates.sort(key=lambda row: (-row["expected_impact"], row["campaign_id"]))
    budget = root["budget_policy"]
    total_used = 0.0
    channel_used: dict[str, float] = {}
    allocations = []
    for row in candidates:
        requested = round(float(budget["base_campaign_budget"]) + row["expected_impact"] * float(budget["impact_budget_multiplier"]), -2)
        channel = row["channel"]
        amount = max(0.0, min(requested, float(budget["per_channel_caps"][channel]) - channel_used.get(channel, 0.0), float(budget["total_budget"]) - total_used))
        channel_used[channel] = channel_used.get(channel, 0.0) + amount
        total_used += amount
        allocations.append({
            "campaign_id": row["campaign_id"], "segment": row["segment"], "channel": channel,
            "allocated_budget": amount, "expected_impact": row["expected_impact"], "opportunity_count": row["opportunity_count"],
        })
    campaign_by_opportunity = {row["opportunity_id"]: row["campaign_id"] for row in portfolio}
    audit = sorted(({
        "contribution_id": row["contribution_id"], "opportunity_id": row["opportunity_id"],
        "source_id": row["source_id"], "contribution_score": row["contribution_score"],
        "effective_date": row["effective_date"], "segment": row["segment"],
        "campaign_id": campaign_by_opportunity[row["opportunity_id"]],
    } for row in attribution), key=lambda row: (row["campaign_id"], row["opportunity_id"], row["source_id"], row["contribution_id"]))
    job3 = {
        "campaign_allocations": allocations, "contribution_audit": audit,
        "metadata": {"candidate_count": len(candidates), "allocation_count": len(allocations), "allocated_budget_total": sum(row["allocated_budget"] for row in allocations), "consumed_handoffs": ["priority_portfolio", "evidence_attribution", "metadata"]},
    }
    calendar: dict[str, list[dict[str, Any]]] = {}
    for row in root["activation_calendar"]:
        calendar.setdefault(row["channel"], []).append(row)
    capacity = {(row["channel"], row["window_id"]): int(row["available_slots"]) for row in root["channel_capacity"]}
    maximum = int(root["activation_policy"]["max_windows_per_campaign"])
    selected = []
    counts: dict[str, int] = {}
    for allocation in sorted(allocations, key=lambda row: (-row["expected_impact"], row["campaign_id"])):
        for slot in sorted(calendar[allocation["channel"]], key=lambda row: row["window_start"]):
            key = (allocation["channel"], slot["window_id"])
            if counts.get(allocation["campaign_id"], 0) >= maximum:
                break
            if capacity[key] <= 0:
                continue
            capacity[key] -= 1
            counts[allocation["campaign_id"]] = counts.get(allocation["campaign_id"], 0) + 1
            selected.append((allocation, slot))
    scheduled = []
    for allocation, slot in selected:
        count = counts[allocation["campaign_id"]]
        scheduled.append({
            "activation_id": f"activation-{len(scheduled) + 1:02d}", "campaign_id": allocation["campaign_id"],
            "segment": allocation["segment"], "channel": allocation["channel"], "window_id": slot["window_id"],
            "window_start": slot["window_start"], "scheduled_budget": round(allocation["allocated_budget"] / count, 2),
            "expected_conversions": round(allocation["expected_impact"] / count, 4),
        })
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in scheduled:
        grouped.setdefault((row["window_id"], row["window_start"], row["channel"]), []).append(row)
    forecast = [{
        "window_id": key[0], "window_start": key[1], "channel": key[2],
        "scheduled_budget": sum(row["scheduled_budget"] for row in rows),
        "expected_conversions": sum(row["expected_conversions"] for row in rows), "activation_count": len(rows),
    } for key, rows in sorted(grouped.items())]
    job4 = {
        "activation_plan": {
            "activation_actions": scheduled, "window_forecast": forecast,
            "aggregate_forecast": {"scheduled_budget": round(sum(row["scheduled_budget"] for row in scheduled), 2), "expected_conversions": round(sum(row["expected_conversions"] for row in scheduled), 4), "activation_count": len(scheduled)},
            "attribution_manifest": {"logical_sha256": ce.sha256(audit), "record_count": len(audit)},
        },
        "metadata": {"campaign_count": len({row["campaign_id"] for row in allocations}), "activation_count": len(scheduled), "window_count": len({row["window_id"] for row in scheduled}), "consumed_handoffs": ["campaign_allocations", "contribution_audit", "metadata"]},
    }
    return {JOB1: job1, JOB2: job2, JOB3: job3, JOB4: job4}


def _configure_base() -> None:
    pe.ATTEMPT = ATTEMPT
    pe.TASK = TASK
    pe.TASK_SHA256 = TASK_SHA256
    pe.AUTHORITY = AUTHORITY
    pe.AUTHORITY_SHA256 = AUTHORITY_SHA256
    pe.JOB1_SOURCE = JOB1_SOURCE
    pe.JOB2_SOURCE = JOB2_SOURCE
    pe.JOB3_SOURCE = JOB3_SOURCE
    pe.JOB4_SOURCE = JOB4_SOURCE
    pe.PROMPT = PROMPT
    pe.FINAL_SCHEMA = FINAL_SCHEMA
    pe.GROUP_SCHEMA = GROUP_SCHEMA
    pe.ARTIFACT_SCHEMA = ARTIFACT_SCHEMA
    pe.RECONSIDER_SCHEMA = RECONSIDER_SCHEMA
    pe.ORACLE_FREEZE = ORACLE_FREEZE
    pe.CALIBRATION = CALIBRATION
    pe.INSTANCES = INSTANCES
    pe.TRUTH = TRUTH
    pe.MATCHED_CLEAN = MATCHED_CLEAN
    pe.MUTATIONS = MUTATIONS
    pe.BUSINESS_BRIEF = BUSINESS_BRIEF
    pe.INTERFACE_DESCRIPTION = INTERFACE_DESCRIPTION
    pe._verify_authority = _verify_authority
    pe.input_for = input_for
    pe._hidden_oracle = _hidden_oracle
    pe._pipeline = _pipeline
    pe._job_input = _job_input
    pe._validate_business_output = _validate_business_output
    pe._run_pipeline_sources = _run_pipeline_sources
    pe._control_invariants = _control_invariants
    pe._hard_fault_qualification = _hard_fault_qualification
    pe._calibration = _calibration
    pe._base_package = _base_package
    pe.build_package = build_package
    pe._configure_base = _configure_base
    pe.prepare_attempt = prepare_attempt
    pe.schedule = schedule
    pe.qualify_packages = qualify_packages
    pe.verify_frozen_attempt = verify_frozen_attempt
    pe.create_live_consumption = create_live_consumption
    pe.run_review_session = run_review_session
    pe.write_analysis = write_analysis
    pe._write_reports = _write_reports
    pe._write_handoff = _write_handoff
    _PE_CONFIGURE()


def _mutant_source(clean: str, instance: str) -> tuple[str, dict[str, Any] | None]:
    return _PE_MUTANT_SOURCE(clean, instance)


def _pipeline(repo_root: Path, job_id: str, job1_source: str):
    return _PE_PIPELINE(repo_root, job_id, job1_source)


def _job_input(job_id: str, prior_output: Mapping[str, Any] | None, root: Mapping[str, Any]) -> dict[str, Any]:
    return _PE_JOB_INPUT(job_id, prior_output, root)


def _validate_business_output(job_id: str, output: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    _PE_VALIDATE_OUTPUT(job_id, output, runtime_input)
    if job_id == JOB2:
        support: dict[str, float] = {}
        for row in runtime_input["evidence_attribution"]:
            support[row["opportunity_id"]] = support.get(row["opportunity_id"], 0.0) + float(row["contribution_score"])
        if any(abs(float(row["full_precision_score"]) - float(support.get(row["opportunity_id"], 0.0))) > 1e-9 for row in runtime_input["opportunities"]):
            raise ValueError("Job-2 input attribution identity is inconsistent")


def _run_pipeline_sources(repo_root: Path, root: Mapping[str, Any], job1_source: str | None = None) -> dict[str, Any]:
    return _PE_RUN_PIPELINE(repo_root, root, job1_source)


def _priority_formula(root: Mapping[str, Any], opportunity: Mapping[str, Any]) -> float:
    coverage = next(row for row in root["capability_coverage"] if row["segment"] == opportunity["segment"])
    commercial = next(row for row in root["commercial_context"] if row["opportunity_id"] == opportunity["opportunity_id"])
    return float((
        Decimal(str(opportunity["full_precision_score"])) * Decimal(str(coverage["coverage_multiplier"])) * Decimal("0.1")
        + Decimal(str(opportunity["estimated_revenue"])) * Decimal(str(commercial["margin_rate"])) / Decimal("10000")
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))


def _public_contract_checks(repo_root: Path, instance: str) -> dict[str, Any]:
    root = input_for(instance)
    outputs = _run_pipeline_sources(repo_root, root)
    job1, job2, job3, job4 = (outputs[job] for job in JOB_ORDER)
    support: dict[str, list[dict[str, Any]]] = {}
    for row in job1["evidence_attribution"]:
        support.setdefault(row["opportunity_id"], []).append(row)
    opportunities = {row["opportunity_id"]: row for row in job1["opportunities"]}
    if any(abs(Decimal(str(row["full_precision_score"])) - sum(Decimal(str(item["contribution_score"])) for item in support[row_id])) > Decimal("0.000000001") for row_id, row in opportunities.items()):
        raise ValueError(f"full-precision attribution identity failed: {instance}")
    if any(row["priority_score"] != _priority_formula(root, opportunities[row["opportunity_id"]]) for row in job2["priority_portfolio"]):
        raise ValueError(f"single-count priority formula failed: {instance}")
    campaign_priority: dict[str, float] = {}
    for row in job2["priority_portfolio"]:
        campaign_priority[row["campaign_id"]] = campaign_priority.get(row["campaign_id"], 0.0) + row["priority_score"]
    audience = {row["segment"]: row["audience_size"] for row in root["audience_economics"]}
    conversion = {row["channel"]: row["conversion_rate"] for row in root["channel_economics"]}
    for row in job3["campaign_allocations"]:
        expected = round(campaign_priority[row["campaign_id"]] * audience[row["segment"]] / 10000.0 * conversion[row["channel"]], 4)
        if row["expected_impact"] != expected:
            raise ValueError(f"expected impact formula failed: {instance}")
    policy = root["budget_policy"]
    total_used = 0.0
    channel_used: dict[str, float] = {}
    for row in sorted(job3["campaign_allocations"], key=lambda value: (-value["expected_impact"], value["campaign_id"])):
        requested = round(float(policy["base_campaign_budget"]) + row["expected_impact"] * float(policy["impact_budget_multiplier"]), -2)
        channel = row["channel"]
        expected = max(0.0, min(requested, float(policy["per_channel_caps"][channel]) - channel_used.get(channel, 0.0), float(policy["total_budget"]) - total_used))
        if row["allocated_budget"] != expected:
            raise ValueError(f"budget allocation formula failed: {instance}")
        channel_used[channel] = channel_used.get(channel, 0.0) + expected
        total_used += expected
    actions = job4["activation_plan"]["activation_actions"]
    allocations = {row["campaign_id"]: row for row in job3["campaign_allocations"]}
    maximum = int(root["activation_policy"]["max_windows_per_campaign"])
    capacity = {(row["channel"], row["window_id"]): int(row["available_slots"]) for row in root["channel_capacity"]}
    for campaign, allocation in allocations.items():
        rows = [row for row in actions if row["campaign_id"] == campaign]
        if not rows or len(rows) > maximum:
            raise ValueError(f"activation window policy failed: {instance}/{campaign}")
        if round(sum(row["scheduled_budget"] for row in rows), 2) != round(allocation["allocated_budget"], 2):
            raise ValueError(f"activation budget split lost value: {instance}/{campaign}")
        if abs(sum(row["expected_conversions"] for row in rows) - allocation["expected_impact"]) > 0.0001:
            raise ValueError(f"activation impact split lost value: {instance}/{campaign}")
    if any(sum(row["channel"] == key[0] and row["window_id"] == key[1] for row in actions) > available for key, available in capacity.items()):
        raise ValueError(f"activation capacity failed: {instance}")
    audit = job3["contribution_audit"]
    expected_audit = sorted(deepcopy(job1["evidence_attribution"]), key=lambda row: (row["campaign_id"], row["opportunity_id"], row["source_id"], row["contribution_id"]))
    if audit != expected_audit or len({row["contribution_id"] for row in audit}) != len(audit):
        raise ValueError(f"contribution audit completeness failed: {instance}")
    if job4["activation_plan"]["attribution_manifest"] != {"logical_sha256": ce.sha256(audit), "record_count": len(audit)}:
        raise ValueError(f"attribution manifest failed: {instance}")
    return {
        "full_precision_matches_retained_contributions": True,
        "single_count_priority_formula": True,
        "expected_impact_formula": True,
        "budget_request_allocation_and_caps": True,
        "calendar_capacity_policy_and_lossless_split": True,
        "complete_contribution_audit": True,
        "exact_attribution_manifest": True,
    }


def _contribution_delta_check(repo_root: Path) -> dict[str, Any]:
    root = input_for(INSTANCES[0])
    baseline = _run_pipeline_sources(repo_root, root)
    changed = deepcopy(root)
    target = changed["market_observations"][4]
    opportunity_id = target["opportunity_id"]
    delta = Decimal("0.2")
    target["contribution_score"] = float(Decimal(str(target["contribution_score"])) + delta)
    updated = _run_pipeline_sources(repo_root, changed)
    before = next(row for row in baseline[JOB2]["priority_portfolio"] if row["opportunity_id"] == opportunity_id)["priority_score"]
    after = next(row for row in updated[JOB2]["priority_portfolio"] if row["opportunity_id"] == opportunity_id)["priority_score"]
    opportunity = next(row for row in baseline[JOB1]["opportunities"] if row["opportunity_id"] == opportunity_id)
    changed_opportunity = next(row for row in updated[JOB1]["opportunities"] if row["opportunity_id"] == opportunity_id)
    coverage = next(row for row in root["capability_coverage"] if row["segment"] == opportunity["segment"])["coverage_multiplier"]
    expected = round(_priority_formula(changed, changed_opportunity) - _priority_formula(root, opportunity), 4)
    observed = round(after - before, 4)
    if observed != expected or len(baseline[JOB1]["opportunities"]) != len(updated[JOB1]["opportunities"]):
        raise ValueError("contribution delta metamorphic check failed against corrected implementation")
    job2_input = _job_input(JOB2, baseline[JOB1], root)
    result = subprocess.run([sys.executable, str(repo_root / OLD_JOB2_SOURCE)], input=json.dumps(job2_input), text=True, capture_output=True, check=False, cwd=repo_root)
    if result.returncode or result.stderr:
        raise ValueError("historical Job-2 comparison execution failed")
    old_output = json.loads(result.stdout)
    old_score = next(row for row in old_output["priority_portfolio"] if row["opportunity_id"] == opportunity_id)["priority_score"]
    if old_score == before:
        raise ValueError("historical double-counting implementation unexpectedly passed public contract")
    return {
        "status": "passed", "opportunity_id_controller_only": opportunity_id,
        "contribution_delta": float(delta), "coverage_multiplier": coverage,
        "expected_priority_delta": expected, "observed_priority_delta": observed,
        "eligibility_set_unchanged": True, "old_double_counting_implementation_rejected": True,
        "old_priority_score": old_score, "corrected_priority_score": before,
    }


def _control_invariants(repo_root: Path, instance: str) -> dict[str, Any]:
    values = _PE_CONTROL_INVARIANTS(repo_root, instance)
    values.update(_public_contract_checks(repo_root, instance))
    return values


def _hard_fault_qualification(captures: Mapping[str, Mapping[str, Any]], instances: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    value = _PE_HARD_FAULT_QUALIFICATION(captures, instances)
    for instance, capture in captures.items():
        job1 = capture["jobs"][JOB1]["output"]
        job2 = capture["jobs"][JOB2]["output"]
        support: dict[str, float] = {}
        for row in job1["evidence_attribution"]:
            support[row["opportunity_id"]] = support.get(row["opportunity_id"], 0.0) + float(row["contribution_score"])
        if any(abs(float(row["full_precision_score"]) - support[row["opportunity_id"]]) > 1e-9 for row in job1["opportunities"]):
            raise ValueError(f"captured fault/control attribution identity failed: {instance}")
        root = input_for(instance)
        opportunities = {row["opportunity_id"]: row for row in job1["opportunities"]}
        if any(row["priority_score"] != _priority_formula(root, opportunities[row["opportunity_id"]]) for row in job2["priority_portfolio"]):
            raise ValueError(f"captured fault/control priority formula failed: {instance}")
    value["all_clean_and_faulty_attribution_identities_recomputed"] = True
    value["all_clean_and_faulty_priorities_single_count"] = True
    return value


def _capture_instance(repo_root: Path, target: Path, instance: str, job1_source: str):
    _configure_base()
    return _PE_CAPTURE(repo_root, target, instance, job1_source)


def _catalogue(capture: Mapping[str, Any]):
    return _PE_CATALOGUE(capture)


def _connected_handoffs(catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _PE_CONNECTED_HANDOFFS(catalogue)


def _capture_handoff_qualification(capture: Mapping[str, Any], catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _PE_HANDOFF_QUALIFICATION(capture, catalogue)


def _load_prepared(target: Path) -> dict[str, Any]:
    _configure_base()
    return _PE_LOAD_PREPARED(target)


def _base_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    _configure_base()
    package = _PE_BASE_PACKAGE(catalogue, source_bundle)
    package["schema_version"] = "n27pf-review-package-1"
    return package


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], compact: Mapping[str, Any], mode: str) -> dict[str, Any]:
    _configure_base()
    pe._base_package = _base_package
    return _PE_BUILD_PACKAGE(catalogue, source_bundle, compact, mode)


def schedule() -> dict[str, Any]:
    cells = []
    for instance in INSTANCES:
        for mode in CELLS:
            cells.append({
                "opaque_instance_id": instance, "cell_id": mode, "mode": mode,
                "mode_name": MODE_NAMES[mode], "declaration_setting": "B1" if mode in {"P03", "P05"} else "B0",
                "branch_id": f"brn-{ce.sha256(['n27pf', instance, mode])[7:23]}",
            })
    reviews = []
    for repetition in (1, 2):
        order = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for block, instance in enumerate(order):
            values = [value for value in cells if value["opaque_instance_id"] == instance]
            rotation = (block + repetition) % len(values)
            for cell in values[rotation:] + values[:rotation]:
                reviews.append({
                    **cell, "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n27pf', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if len(cells) != 30 or len(reviews) != 60 or sum(CALLS_BY_MODE[row["mode"]] for row in reviews) != 120:
        raise AssertionError("Attempt 050 schedule counts changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _calibration(repo_root: Path, target: Path, clean_source: str) -> dict[str, Any]:
    first_path = target / "calibration/disposition.json"
    first = _json(first_path) if first_path.exists() else None
    if first and first["status"] == "passed":
        ce._verified_self_hash(first, "disposition_sha256")
        return first
    round_number = 2 if first else 1
    disposition_path = target / ("calibration/disposition-round-2.json" if round_number == 2 else "calibration/disposition.json")
    if disposition_path.exists():
        disposition = _json(disposition_path)
        ce._verified_self_hash(disposition, "disposition_sha256")
        if disposition["status"] != "passed":
            raise RuntimeError("Attempt 050 clean calibration did not pass")
        return disposition
    calibration_root = target / "calibration" / ("round-2" if round_number == 2 else "round-1")
    correction = None
    if round_number == 2:
        correction = {
            "schema_version": "n27pf-pre-freeze-correction-1",
            "authority": "single authorized calibration correction round",
            "first_pass_disposition_sha256": first["disposition_sha256"],
            "issues": [
                "The common contract omitted Job-3 nearest-100 requested-budget rounding.",
                "The sacrificial input used differing effective and ingestion dates that invited an unsupported applicability concern.",
            ],
            "exact_delta": {
                "common_interface": "document nearest-100 requested-budget rounding",
                "calibration_input_only": "set each ingested_at value equal to its effective_date",
                "scientific_instances_or_faults_changed": False,
            },
            "fault_difficulty_or_treatment_selected_from_responses": False,
        }
        correction["correction_sha256"] = ce.sha256(correction)
        ce._write_immutable(target / "calibration/pre-freeze-correction.json", correction)
    capture, source_bundle = _capture_instance(repo_root, calibration_root, CALIBRATION, clean_source)
    catalogue, crosswalk = _catalogue(capture)
    catalogue["schema_version"] = "n27pf-calibration-native-catalogue-1"
    catalogue["handoffs"] = _connected_handoffs(catalogue)
    catalogue.pop("catalogue_sha256", None)
    catalogue["catalogue_sha256"] = ce.sha256(catalogue)
    compact, index = n27p.build_compact_graph(catalogue, crosswalk)
    reviewer, disclosure, omission = pb._payload_lazy_catalogue(catalogue, CALIBRATION)
    lazy = pe.prior._with_handoffs(pb._lazy_graph(compact, reviewer), catalogue["handoffs"])
    pb._assert_payload_lazy(lazy, disclosure)
    for name, record in {
        "capture": capture, "catalogue": catalogue, "native-crosswalk": crosswalk,
        "subtree-index": index, "artifact-disclosure": disclosure, "omission-manifest": omission,
    }.items():
        ce._write_immutable(calibration_root / f"{name}.json", record)
    results = []
    for position, (name, mode) in enumerate((("calibration-current", "P01"), ("calibration-compact-semantic", "P03")), 1):
        package = build_package(catalogue, source_bundle, lazy, mode)
        condition = {
            "opaque_instance_id": CALIBRATION, "cell_id": name, "mode": mode, "mode_name": name,
            "declaration_setting": "B1" if mode == "P03" else "B0", "branch_id": f"cal-{ce.sha256(['n27pf', name])[7:23]}",
        }
        package_record = {
            "schema_version": "n27pf-calibration-package-1", "controller_condition": condition,
            "capture_sha256": capture["capture_sha256"], "catalogue_sha256": catalogue["catalogue_sha256"],
            "reviewer_package": package,
        }
        package_record["package_sha256"] = ce.sha256(package_record)
        ce._write_immutable(calibration_root / "packages" / f"{name}.json", package_record)
        session = run_review_session(repo_root, calibration_root, catalogue, reviewer, disclosure, index, package_record, f"calibration-r{round_number}-{position:02d}")
        validation = session["final_validation"]
        result = {
            "schema_version": "n27pf-calibration-result-1", "scenario": CALIBRATION, "cell": name,
            "unscored": True, "excluded_from_scientific_analysis": True,
            "fault_detected": validation["fault_detected"], "receipt": deepcopy(validation["receipt"]),
            "call_records": deepcopy(session["call_records"]), "usage": deepcopy(session["usage"]),
        }
        result["result_sha256"] = ce.sha256(result)
        ce._write_immutable(calibration_root / "results" / f"{name}.json", result)
        results.append(result)
    passed = all(not result["fault_detected"] for result in results)
    disposition = {
        "schema_version": "n27pf-calibration-disposition-1", "status": "passed" if passed else ("failed_first_pass" if round_number == 1 else "failed_second_pass"),
        "scenario": CALIBRATION, "calls": (int(first["calls"]) if first else 0) + sum(len(result["call_records"]) for result in results),
        "authorized_maximum_calls": 4, "experimental_analysis_excluded": True,
        "correction_round_used": round_number == 2, "pre_freeze_delta": correction,
        "first_pass_disposition_sha256": first["disposition_sha256"] if first else None,
        "results": [{"cell": result["cell"], "fault_detected": result["fault_detected"], "result_sha256": result["result_sha256"]} for result in results],
    }
    disposition["disposition_sha256"] = ce.sha256(disposition)
    ce._write_immutable(disposition_path, disposition)
    if not passed:
        raise RuntimeError("first-pass calibration false positive requires authorized contradiction review" if round_number == 1 else "second-pass calibration remained false positive")
    return disposition


def _calibration_disposition(target: Path) -> dict[str, Any]:
    corrected = target / "calibration/disposition-round-2.json"
    return _json(corrected if corrected.exists() else target / "calibration/disposition.json")


def _public_contract_path(target: Path) -> Path:
    corrected = target / "qualification/public-contract-audit-round-2.json"
    return corrected if corrected.exists() else target / "qualification/public-contract-audit.json"


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_base()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PF is authorized only for Attempt 050")
    _verify_authority(repo_root)
    first = target / "calibration/disposition.json"
    corrected_round = first.exists() and _json(first)["status"] == "failed_first_pass"
    audit_path = target / ("qualification/public-contract-audit-round-2.json" if corrected_round else "qualification/public-contract-audit.json")
    if not audit_path.exists():
        checks = {instance: _public_contract_checks(repo_root, instance) for instance in (*INSTANCES[:2], CALIBRATION)}
        delta = _contribution_delta_check(repo_root)
        record = {
            "schema_version": "n27pf-public-contract-audit-1", "status": "passed",
            "independent_oracle_source_sha256": ce.sha256(inspect.getsource(_hidden_oracle).encode()),
            "recomputed_scenarios": checks, "contribution_delta_metamorphic": delta,
            "historical_double_counting_implementation_fails": delta["old_double_counting_implementation_rejected"],
            "model_calls": 0,
        }
        record["audit_sha256"] = ce.sha256(record)
        ce._write_immutable(audit_path, record)
    return _PE_PREPARE(repo_root, target)


def _package_records(target: Path) -> list[dict[str, Any]]:
    return _PE_PACKAGE_RECORDS(target)


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return _PE_INITIAL_EVIDENCE(package)


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    _configure_base()
    return _PE_PAIRWISE_CHECKS(records)


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _configure_base()
    return _PE_RENDER_REQUEST(package, operation_response)


def validate_schemas(repo_root: Path) -> dict[str, str]:
    _configure_base()
    return _PE_VALIDATE_SCHEMAS(repo_root)


def _leakage_audit(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    _configure_base()
    return _PE_LEAKAGE_AUDIT(records)


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    _configure_base()
    value = _PE_QUALIFY_PACKAGES(repo_root, target, records, prepared, design)
    public = _json(_public_contract_path(target))
    if public["status"] != "passed" or not public["historical_double_counting_implementation_fails"]:
        raise ValueError("public-contract audit is not qualified")
    value["public_contract_audit_sha256"] = public["audit_sha256"]
    value["historical_double_counting_formula_rejected"] = True
    value["schema_version"] = "n27pf-no-model-verification-1"
    return value


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_base()
    return _PE_BUILD_ATTEMPT(repo_root, attempt_root or repo_root / ATTEMPT)


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27pf_experiment.py"), JOB1_SOURCE, JOB2_SOURCE, JOB3_SOURCE, JOB4_SOURCE,
        PROMPT, FINAL_SCHEMA, GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27pf_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 050 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after experimental reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("focused N27PF tests must pass before freeze")
    calibration = _calibration_disposition(target)
    if calibration["status"] != "passed" or calibration["calls"] not in {2, 4}:
        raise ValueError("bounded clean calibration did not pass")
    freeze = {
        "schema_version": "n27pf-experiment-freeze-1", "attempt": "050", "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "attempt_049_hashes": deepcopy(ATTEMPT_049_HASHES), "reused_hashes": deepcopy(REUSED_HASHES),
        "protected_hashes": deepcopy(PROTECTED_HASHES),
        "sandbox_gate_file_sha256": ce.sha256((repo_root / SANDBOX_GATE).read_bytes()),
        "sandbox_bindings": deepcopy(built["prepared"]["authority"]["sandbox"]),
        "public_contract_audit_file_sha256": ce.sha256(_public_contract_path(target).read_bytes()),
        "calibration_disposition_file_sha256": ce.sha256((target / ("calibration/disposition-round-2.json" if (target / "calibration/disposition-round-2.json").exists() else "calibration/disposition.json")).read_bytes()),
        "calibration_tree_sha256": ce.sha256(ce._tree_hashes(target / "calibration")),
        "common_material_freeze_file_sha256": ce.sha256((target / "qualification/scientific-common-material-freeze.json").read_bytes()),
        "hidden_oracle_file_sha256": ce.sha256((target / ORACLE_FREEZE).read_bytes()),
        "clean_control_file_sha256": ce.sha256((target / "qualification/clean-controls.json").read_bytes()),
        "hard_fault_file_sha256": ce.sha256((target / "qualification/hard-faults.json").read_bytes()),
        "native_capture_handoff_file_sha256": ce.sha256((target / "qualification/native-captures-and-handoffs.json").read_bytes()),
        "adaptive_relevance_file_sha256": ce.sha256((target / "qualification/adaptive-fault-relevance.json").read_bytes()),
        "leakage_audit_file_sha256": ce.sha256((target / "qualification/reviewer-leakage-audit.json").read_bytes()),
        "capture_hashes": {key: built["prepared"]["captures"][key]["capture_sha256"] for key in INSTANCES},
        "catalogue_hashes": {key: built["prepared"]["catalogues"][key]["catalogue_sha256"] for key in INSTANCES},
        "instance_hashes": {key: built["prepared"]["instances"][key]["instance_sha256"] for key in INSTANCES},
        "tree_hashes": {folder: ce.sha256(ce._tree_hashes(target / folder)) for folder in (
            "capture-branches", "job-captures", "native-exports", "catalogues", "artifact-disclosures",
            "omission-manifests", "projections", "packages", "controller-manifests",
        )},
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "no_model_verification_file_sha256": ce.sha256((target / "qualification/no-model-verification.json").read_bytes()),
        "focused_test_results_file_sha256": ce.sha256(focused.read_bytes()),
        "expected_counts": {"calibration_calls": calibration["calls"], "instances": 5, "fresh_job_executions": 20, "packages": 30, "reviews": 60, "follow_up_calls": 60, "provider_calls": 120, "repairs": 0},
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0, "full_replication_started": False,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    ce._write_immutable(path, freeze)
    return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _verify_authority(repo_root)
    freeze = _json(target / "experiment-freeze.json")
    digest = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"frozen code changed: {relative}")
    built = build_attempt(repo_root, target)
    if ce.sha256(ce._tree_hashes(target / "calibration")) != freeze["calibration_tree_sha256"]:
        raise ValueError("frozen calibration records changed")
    for folder, expected in freeze["tree_hashes"].items():
        if ce.sha256(ce._tree_hashes(target / folder)) != expected:
            raise ValueError(f"frozen tree changed: {folder}")
    if sorted(record["package_sha256"] for record in built["records"]) != freeze["package_hashes"]:
        raise ValueError("frozen package membership changed")
    if ce.sha256(built["design"]["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("frozen review schedule changed")
    return {"status": "verified", "freeze_sha256": digest, "packages": 30, "reviews": 60, "provider_calls": 120, "repairs": 0, "qualification": built["qualification"]}


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("live authority must be consumed before reviews")
    freeze = _json(target / "experiment-freeze.json")
    record = {
        "schema_version": "n27pf-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "one_use_live_authority": True,
        "authorized_experimental_calls": 120, "completed_calibration_calls": _calibration_disposition(target)["calls"], "repairs": 0,
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], stage: str) -> dict[str, Any]:
    _configure_base()
    return _PE_VALIDATE_RESPONSE(repo_root, package, response, stage)


def score_response(instance: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    return _PE_SCORE_RESPONSE(instance, validation)


def run_review_session(repo_root: Path, target: Path, catalogue: Mapping[str, Any], reviewer: Mapping[str, Any], disclosure: Mapping[str, Any], index: Mapping[str, Any], package_record: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    _configure_base()
    return _PE_RUN_REVIEW(repo_root, target, catalogue, reviewer, disclosure, index, package_record, trial_id)


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return _PE_RECONSTRUCT_COUNTS(reviews)


def _actual_usage(usage: Mapping[str, Any]) -> dict[str, int]:
    return _PE_ACTUAL_USAGE(usage)


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    _configure_base()
    return _PE_WRITE_ANALYSIS(target, reviews)


def _rate(value: Mapping[str, int]) -> str:
    return "n/a" if not value["denominator"] else f"{value['numerator']}/{value['denominator']} ({100 * value['numerator'] / value['denominator']:.2f}%)"


def _write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PF-priority-corrected-native-etiq-pilot"
    findings = [
        "# N27PF priority-corrected native-Etiq pilot", "",
        "Attempt 050 completed the authorized five-instance exploratory pilot. The full replication remains deferred.", "",
        "## Aggregate outcomes", "",
        f"- Fault sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct earliest Job-1 localisation: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Balanced fault-discrimination accuracy: {aggregate['balanced_fault_discrimination_accuracy']:.4f}",
        f"- Experimental provider calls: {aggregate['provider_calls']}; calibration calls: {analysis['calibration']['calls']} (unscored and excluded)",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; derived total {aggregate['total_tokens']}", "",
        "All 20 scientific captures are fresh native Etiq executions. Every connected graph contains nine separately labelled exact-hash handoffs. No repairs were run.", "",
        "## Immutable records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-050/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-050/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-050/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-050/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    cell_lines = ["# Complete cell table", "", "| Cell | Reviews | Detection /6 | Job 1 /6 | Exact /6 | Control FP /4 | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in CELLS:
        value = analysis["cell_summaries"][cell]
        cell_lines.append(f"| {cell} | {value['reviews']} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} | {_rate(value['control_false_positives'])} | {value['provider_calls']} |")
    _write_text(report_dir / "cell-table.md", "\n".join(cell_lines))
    fault_lines = ["# Complete fault table", "", "| Fault | Cell | Detection /2 | Job 1 /2 | Exact /2 |", "|---|---|---:|---:|---:|"]
    for instance in MATCHED_CLEAN:
        for cell in CELLS:
            value = analysis["fault_cell_summaries"][f"{instance}/{cell}"]
            fault_lines.append(f"| {instance} | {cell} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} |")
    _write_text(report_dir / "fault-table.md", "\n".join(fault_lines))
    control_lines = ["# Complete control table", "", "| Control | Cell | False positives /2 |", "|---|---|---:|"]
    for instance in INSTANCES[:2]:
        for cell in CELLS:
            value = analysis["control_cell_summaries"][f"{instance}/{cell}"]
            control_lines.append(f"| {instance} | {cell} | {_rate(value['control_false_positives'])} |")
    _write_text(report_dir / "control-table.md", "\n".join(control_lines))
    operation_lines = ["# Complete operation table", "", "| Trial | Cell | Group | Artifact | Inspection | Bytes | True group | True artifact |", "|---|---|---|---|---|---:|---|---|"]
    token_lines = ["# Complete token table", "", "| Trial | Cell | Rep | Calls | Input | Cached | Output | Total |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    review_lines = ["# Complete review table", "", "| Position | Trial | Instance | Cell | Rep | Detected | Job | Function | Calls |", "|---:|---|---|---|---:|---|---|---|---:|"]
    for review in sorted(reviews, key=lambda value: value["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        group, artifact = review.get("selected_group") or {}, review.get("selected_artifact") or {}
        usage = _actual_usage(review["usage"])
        operation_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {artifact.get('inspection', '')} | {artifact.get('artifact_bytes_returned', 0)} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} |")
        token_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {trial['repetition']} | {len(review['call_records'])} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['input_tokens'] + usage['output_tokens']} |")
        review_lines.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |")
    _write_text(report_dir / "operation-table.md", "\n".join(operation_lines))
    _write_text(report_dir / "token-table.md", "\n".join(token_lines))
    _write_text(report_dir / "review-table.md", "\n".join(review_lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PF Attempt 050 priority-corrected pilot results", "",
        "Status: `completed_pilot_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "",
        f"- {_calibration_disposition(target)['calls']} unscored calibration calls, excluded from scientific results",
        "- Five instances and 20 fresh native Etiq scientific job captures",
        f"- 30 packages; 60 terminal reviews; {aggregate['provider_calls']} experimental calls; zero repairs", "",
        "Outcomes", "",
        f"- Sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Balanced fault-discrimination accuracy: {aggregate['balanced_fault_discrimination_accuracy']:.4f}", "",
        "Attempts 042-049 and all protected execution surfaces remained unchanged. The full replication was not started.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PF_attempt_050_results_to_overseer.email.md", "\n".join(lines))


def execute_lifecycle(repo_root: Path, target: Path) -> Path:
    _configure_base()
    return _PE_EXECUTE_LIFECYCLE(repo_root, target)


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        record = {
            "schema_version": "n27pf-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27pf_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
            "completed_review_records": len(list((target / "reviews").glob("*.json"))), "completed_repair_records": 0,
        }
        record["terminal_sha256"] = ce.sha256(record)
        path = target / "terminal" / f"terminal-incomplete-{record['terminal_sha256'][7:23]}.json"
        ce._write_immutable(path, record)
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--attempt-root", default=ATTEMPT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    target = Path(args.attempt_root)
    target = target if target.is_absolute() else repo / target
    try:
        if args.operation == "build":
            print(json.dumps({"qualification": build_attempt(repo, target)["qualification"]}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, target))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, target), indent=2))
        else:
            path = run_lifecycle(repo, target)
            print(path)
            return 0 if _json(path).get("status") == "completed_pilot_and_analysis" else 1
    except Exception as exc:
        print(f"N27PF experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
