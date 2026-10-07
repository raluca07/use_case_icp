"""N27PD blinded-business-brief hard-fault pilot (Attempt 048)."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import csv
from decimal import Decimal, ROUND_HALF_EVEN
import inspect
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from . import n25_experiment as n25
from . import n26p_experiment as n26p
from . import n27p_experiment as n27p
from . import n27pa_experiment as n27pa
from . import n27pb_experiment as pb
from .fault_preflight_v2 import validate_strict_provider_schema
from .job_store import JobStore
from .n05_program import _load_snapshot, _parse_output, _pipeline_payload, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-048")
ATTEMPT_047 = Path("outputs/fault-experiments-v2-2-n10/attempt-047")
TASK = Path("instructions_between_agent_types/developer/current/N27PD_blinded_business_brief_hard_fault_pilot.email.md")
TASK_SHA256 = "sha256:0c51379384e787dbebcf11dde01f50f174b32579ecc59ac04108900172e5796c"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PD_blinded_business_brief_hard_fault_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:dfc91aca21896de27ad01c69727bbbc8fa4ee3d5ebc6be0638c8fe5312484b6f"
JOB1_SOURCE = Path("src/use_case_icp/n27pd_market_evidence.py")
JOB2_SOURCE = Path("src/use_case_icp/n27pd_opportunity_priority.py")
JOB3_SOURCE = Path("src/use_case_icp/n27pd_campaign_allocation.py")
JOB4_SOURCE = Path("src/use_case_icp/n27pd_activation_schedule.py")
PROMPT = Path("prompts/v2_2/n27pd_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n27pd_final.schema.json")
GROUP_SCHEMA = Path("schemas/v2_2/n27pd_choose_group.schema.json")
ARTIFACT_SCHEMA = Path("schemas/v2_2/n27pd_choose_artifact.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n27pd_reconsider.schema.json")
ORACLE_FREEZE = Path("qualification/hidden-oracle-freeze.json")
SANDBOX_GATE = pb.SANDBOX_GATE
SANDBOX_GATE_SHA256 = pb.SANDBOX_GATE_SHA256

JOB_ORDER = n25.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
INSTANCES = (
    "case-lilac-arch",
    "case-mint-quay",
    "case-ochre-glen",
    "case-pearl-vale",
    "case-russet-lake",
)
TRUTH = {
    "case-lilac-arch": None,
    "case-mint-quay": None,
    "case-ochre-glen": "filter_applicable_evidence",
    "case-pearl-vale": "normalize_source_observations",
    "case-russet-lake": "assemble_opportunity_evidence",
}
MATCHED_CLEAN = {instance: INSTANCES[0] for instance in INSTANCES[2:]}
MUTATIONS = {
    "case-ochre-glen": ('dated_df["_valid_until"] >= as_of', 'dated_df["_valid_until"] > as_of'),
    "case-pearl-vale": ('["opportunity_id", "source_id", "observed_at"]', '["opportunity_id", "source_id", "valid_until"]'),
    "case-russet-lake": ('left_on="evidence_opportunity_id"', 'left_on="partner_opportunity_id"'),
}
CELLS = ("P01", "P02", "P03", "P04", "P05", "P06")
MODE_NAMES = {
    "P01": "current_job4", "P02": "compact_end_to_end",
    "P03": "compact_end_to_end_semantic_boundaries",
    "P04": "adaptive_required_one", "P05": "adaptive_required_one_semantic_boundaries",
    "P06": "two_pass_reconsideration",
}
CALLS_BY_MODE = {"P01": 1, "P02": 1, "P03": 1, "P04": 3, "P05": 3, "P06": 3}
BUSINESS_BRIEF = (
    "Review a four-job marketing workflow that turns market evidence into a campaign activation schedule. "
    "Decide whether the observed execution contains a behaviorally significant processing fault. The workflow "
    "should base its plan on applicable market evidence, respect the supplied selection, budget and scheduling "
    "policies, and retain auditable attribution while evidence is aggregated into campaigns. Begin at Job 4 and "
    "identify the earliest responsible job and exact function only when the available evidence supports that conclusion."
)
ATTEMPT_047_HASHES = {
    "terminal-state.json": "sha256:280bb020fd89fd3ebbadc7648aab9c88fcc167134d36bd186d6f6cae229fa470",
    "experiment-freeze.json": "sha256:64883c31a8689eb5140adb8a33a41e59e5b2c3bda90bf6c800207d5bb9cf54b0",
    "replay.json": "sha256:e70e13d27f868b120e70c4ee24f5003b6b46f1da9685599c6075cfcd135b5671",
    "analysis/summary.json": "sha256:fe10dfedf6754500d47d06e2be769278f3eadbaef0df4ac029bdab03ed546a8c",
}
PROTECTED_HASHES = {
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
}


def _configure_reuse() -> None:
    pb.INSTANCES = INSTANCES
    pb.TRUTH = TRUTH
    pb.MATCHED_CLEAN = MATCHED_CLEAN
    pb.PROMPT = PROMPT
    pb.FINAL_SCHEMA = FINAL_SCHEMA
    pb.GROUP_SCHEMA = GROUP_SCHEMA
    pb.ARTIFACT_SCHEMA = ARTIFACT_SCHEMA
    pb.RECONSIDER_SCHEMA = RECONSIDER_SCHEMA
    functions = {
        JOB1: ("filter_applicable_evidence", "normalize_source_observations", "assemble_opportunity_evidence"),
        JOB2: ("join_commercial_context", "calculate_priority_inputs", "rank_opportunity_portfolio"),
        JOB3: ("aggregate_campaign_candidates", "join_campaign_economics", "allocate_campaign_budget"),
        JOB4: ("join_calendar_capacity", "assign_activation_windows", "aggregate_activation_forecast"),
    }
    n27p.FUNCTIONS = functions
    n27pa.FUNCTIONS = functions


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    create_bytes_exclusive(path, value.encode())


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PD authority changed: {relative}")
    for relative, expected in PROTECTED_HASHES.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"protected implementation changed: {relative}")
    for relative, expected in ATTEMPT_047_HASHES.items():
        if ce.sha256((repo_root / ATTEMPT_047 / relative).read_bytes()) != expected:
            raise ValueError(f"Attempt 047 preservation binding changed: {relative}")
    if ce.sha256((repo_root / SANDBOX_GATE).read_bytes()) != SANDBOX_GATE_SHA256:
        raise ValueError("signed artifact sandbox gate changed")
    sandbox = {
        "artifact_python_worker_sha256": ce.sha256(pb.operations._ARTIFACT_PYTHON_WORKER.encode()),
        "production_launcher_sha256": pb.operations.production_launcher_sha256(pb.operations.artifact_python_launcher),
        "launch_policy_sha256": pb.operations.ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
    }
    if sandbox != {
        "artifact_python_worker_sha256": "sha256:8e9307c764bb5e9f6511dc96fdc32a5adb3202df6bf0968c0b8522b6c74c98b5",
        "production_launcher_sha256": "sha256:fe8216b7c45091bffecfb1f304c3947548f7a1175fe03ad7c82d506bacc0ba83",
        "launch_policy_sha256": "sha256:ca9a3d0c25ce256c5e2d0ad7e9744d53803bfdc2028043c2839b25b2b8a094c9",
    }:
        raise ValueError("protected sandbox binding changed")
    if (ce.PROVIDER_MODEL, ce.PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise ValueError("model configuration changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "sandbox": sandbox}


SEGMENTS = ("enterprise", "growth", "public", "small_business")
CHANNEL_BY_SEGMENT = {"enterprise": "email", "growth": "social", "public": "search", "small_business": "email"}


def _fixture(prefix: str, value_offset: float) -> dict[str, Any]:
    opportunity_ids = [f"{prefix}-op-{index:02d}" for index in range(1, 14)]
    campaign_ids = {segment: f"{prefix}-campaign-{index:02d}" for index, segment in enumerate(SEGMENTS, 1)}
    sources = [f"{prefix}-source-{index:02d}" for index in range(1, 9)]
    observations = []
    for index, opportunity_id in enumerate(opportunity_ids):
        segment = SEGMENTS[index % len(SEGMENTS)]
        first = 5.05 + value_offset + (index % 3) * 0.31
        second = 5.35 + value_offset + (index % 4) * 0.27
        for part, contribution in enumerate((first, second), 1):
            observations.append({
                "contribution_id": f"{prefix}-contribution-{index + 1:02d}-{part}",
                "opportunity_id": opportunity_id,
                "partner_opportunity_id": opportunity_id,
                "segment": segment, "campaign_id": campaign_ids[segment],
                "channel_hint": CHANNEL_BY_SEGMENT[segment],
                "source_id": sources[(index * 2 + part - 1) % len(sources)],
                "observed_at": f"2026-08-{3 + ((index + part) % 20):02d}",
                "valid_until": "2026-10-15",
                "contribution_score": round(contribution, 3),
                "estimated_revenue": 82010 + index * 4300 + int(value_offset * 1000),
            })
    # A boundary observation controls one eligibility outcome without changing its threshold rule.
    observations[0]["contribution_score"] = 5.2 + value_offset
    observations[0]["valid_until"] = "2026-09-01"
    observations[1]["contribution_score"] = 5.1 + value_offset
    # One repeated source has a newer, stronger observation but a shorter validity horizon.
    repeat_base = observations[2]
    repeat_base.update({"contribution_score": 2.0 + value_offset, "observed_at": "2026-07-01", "valid_until": "2026-12-31"})
    observations.append({
        **repeat_base,
        "contribution_id": f"{prefix}-contribution-02-new",
        "observed_at": "2026-08-25", "valid_until": "2026-10-01",
        "contribution_score": 6.0 + value_offset,
    })
    observations[4]["partner_opportunity_id"] = opportunity_ids[3]
    coverage = [
        {"segment": segment, "coverage_tier": tier, "coverage_multiplier": multiplier}
        for segment, tier, multiplier in zip(SEGMENTS, ("strong", "strong", "moderate", "moderate"), (1.15, 1.1, 1.05, 1.0))
    ]
    commercial = [
        {"opportunity_id": opportunity_id, "margin_rate": round(0.31 + (index % 4) * 0.025, 3)}
        for index, opportunity_id in enumerate(opportunity_ids)
    ]
    audience = [
        {"segment": segment, "audience_size": size}
        for segment, size in zip(SEGMENTS, (52000, 46000, 41000, 36000))
    ]
    economics = [
        {"channel": "email", "conversion_rate": 0.032},
        {"channel": "social", "conversion_rate": 0.025},
        {"channel": "search", "conversion_rate": 0.029},
    ]
    calendar = [
        {"channel": channel, "window_id": f"{channel}-w{number}", "window_start": f"2026-10-{number * 7:02d}"}
        for channel in ("email", "social", "search") for number in (1, 2, 3)
    ]
    capacity = [
        {"channel": row["channel"], "window_id": row["window_id"], "available_slots": 2}
        for row in calendar
    ]
    return {
        "scenario_id": f"{prefix}-market-cycle",
        "market_observations": observations,
        "selection_policy": {
            "as_of_date": "2026-09-01", "segment_minimum_scores": {
                "enterprise": 10.0 + value_offset, "growth": 6.5 + value_offset,
                "public": 8.0 + value_offset, "small_business": 8.0 + value_offset,
            },
            "minimum_distinct_sources": 2, "reporting_precision": 2,
        },
        "capability_coverage": coverage, "commercial_context": commercial,
        "audience_economics": audience, "channel_economics": economics,
        "budget_policy": {
            "total_budget": 80000.0, "base_campaign_budget": 5000.0,
            "impact_budget_multiplier": 1000.0,
            "per_channel_caps": {"email": 42000.0, "social": 24000.0, "search": 24000.0},
        },
        "activation_calendar": calendar, "channel_capacity": capacity,
    }


def input_for(instance: str) -> dict[str, Any]:
    return deepcopy(_fixture("lumen", 0.0) if instance != INSTANCES[1] else _fixture("northstar", 0.43))


def _hidden_oracle(root: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Independent clean reference; deliberately does not import pipeline code."""
    policy = root["selection_policy"]
    applicable = [
        deepcopy(row) for row in root["market_observations"]
        if row["observed_at"] <= policy["as_of_date"] <= row["valid_until"]
    ]
    per_source = {}
    for row in sorted(applicable, key=lambda value: (value["opportunity_id"], value["source_id"], value["observed_at"]), reverse=False):
        key = (row["opportunity_id"], row["source_id"])
        if key not in per_source or row["observed_at"] > per_source[key]["observed_at"]:
            per_source[key] = row
    normalized = list(per_source.values())
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in normalized:
        key = (row["opportunity_id"], row["segment"], row["campaign_id"], row["channel_hint"])
        grouped.setdefault(key, []).append(row)
    opportunities = []
    for (opportunity, segment, campaign, channel), rows in sorted(grouped.items()):
        full = sum(float(row["contribution_score"]) for row in rows)
        if full >= float(policy["segment_minimum_scores"][segment]) and len({row["source_id"] for row in rows}) >= int(policy["minimum_distinct_sources"]):
            opportunities.append({
                "opportunity_id": opportunity, "segment": segment, "campaign_id": campaign,
                "channel_hint": channel, "full_precision_score": full,
                "reported_score": round(full, int(policy["reporting_precision"])),
                "evidence_source_count": len({row["source_id"] for row in rows}),
                "estimated_revenue": max(int(row["estimated_revenue"]) for row in rows),
            })
    opportunities.sort(key=lambda row: row["opportunity_id"])
    eligible = {row["opportunity_id"]: row for row in opportunities}
    attribution = [
        {
            "contribution_id": row["contribution_id"], "opportunity_id": row["opportunity_id"],
            "source_id": row["source_id"], "contribution_score": row["contribution_score"],
            "observed_at": row["observed_at"], "segment": row["segment"], "campaign_id": row["campaign_id"],
        }
        for row in normalized if row["opportunity_id"] in eligible
    ]
    attribution.sort(key=lambda row: (row["opportunity_id"], row["source_id"], row["contribution_id"]))
    job1 = {
        "opportunities": opportunities, "evidence_attribution": attribution,
        "metadata": {
            "applicable_observation_count": len(applicable), "per_source_observation_count": len(normalized),
            "qualified_opportunity_count": len(opportunities), "attribution_count": len(attribution),
            "scenario_id": root.get("scenario_id", ""),
        },
    }
    coverage = {row["segment"]: row for row in root["capability_coverage"]}
    commercial = {row["opportunity_id"]: row for row in root["commercial_context"]}
    support: dict[str, list[dict[str, Any]]] = {}
    for row in attribution:
        support.setdefault(row["opportunity_id"], []).append(row)
    portfolio = []
    for row in opportunities:
        rows = support[row["opportunity_id"]]
        priority = float((
            Decimal(str(row["full_precision_score"])) * Decimal(str(coverage[row["segment"]]["coverage_multiplier"]))
            + sum(Decimal(str(item["contribution_score"])) for item in rows) * Decimal("0.1")
            + Decimal(str(row["estimated_revenue"])) * Decimal(str(commercial[row["opportunity_id"]]["margin_rate"])) / Decimal("10000")
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
        portfolio.append({
            "opportunity_id": row["opportunity_id"], "segment": row["segment"],
            "campaign_id": row["campaign_id"], "channel_hint": row["channel_hint"],
            "priority_score": priority, "estimated_revenue": row["estimated_revenue"],
            "coverage_tier": coverage[row["segment"]]["coverage_tier"],
            "attributed_source_count": len({item["source_id"] for item in rows}),
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
        allocations.append({**row, "allocated_budget": amount})
    allocations = [{
        "campaign_id": row["campaign_id"], "segment": row["segment"], "channel": row["channel"],
        "allocated_budget": row["allocated_budget"], "expected_impact": row["expected_impact"],
        "opportunity_count": row["opportunity_count"],
    } for row in allocations]
    campaign_by_opportunity = {row["opportunity_id"]: row["campaign_id"] for row in portfolio}
    audit = sorted(
        ({"contribution_id": row["contribution_id"], "campaign_id": campaign_by_opportunity[row["opportunity_id"]]} for row in attribution),
        key=lambda row: (row["campaign_id"], row["contribution_id"]),
    )
    job3 = {
        "campaign_allocations": allocations, "contribution_audit": audit,
        "metadata": {
            "candidate_count": len(candidates), "allocation_count": len(allocations),
            "allocated_budget_total": sum(row["allocated_budget"] for row in allocations),
            "consumed_handoffs": ["priority_portfolio", "evidence_attribution", "metadata"],
        },
    }
    calendar: dict[str, list[dict[str, Any]]] = {}
    for row in root["activation_calendar"]:
        calendar.setdefault(row["channel"], []).append(row)
    capacity = {(row["channel"], row["window_id"]): int(row["available_slots"]) for row in root["channel_capacity"]}
    scheduled = []
    for allocation in sorted(allocations, key=lambda row: (-row["expected_impact"], row["campaign_id"])):
        count = 0
        for slot in sorted(calendar[allocation["channel"]], key=lambda row: row["window_start"]):
            key = (allocation["channel"], slot["window_id"])
            if count >= 2:
                break
            if capacity[key] <= 0:
                continue
            capacity[key] -= 1
            count += 1
            scheduled.append({
                "activation_id": f"activation-{len(scheduled) + 1:02d}",
                "campaign_id": allocation["campaign_id"], "segment": allocation["segment"],
                "channel": allocation["channel"], "window_id": slot["window_id"],
                "window_start": slot["window_start"],
                "scheduled_budget": round(allocation["allocated_budget"] / 2.0, 2),
                "expected_conversions": round(allocation["expected_impact"] / 2.0, 4),
            })
    grouped_forecast: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in scheduled:
        grouped_forecast.setdefault((row["window_id"], row["window_start"], row["channel"]), []).append(row)
    window_forecast = [{
        "window_id": key[0], "window_start": key[1], "channel": key[2],
        "scheduled_budget": sum(row["scheduled_budget"] for row in rows),
        "expected_conversions": sum(row["expected_conversions"] for row in rows),
        "activation_count": len(rows),
    } for key, rows in sorted(grouped_forecast.items())]
    job4 = {
        "activation_plan": {
            "activation_actions": scheduled, "window_forecast": window_forecast,
            "aggregate_forecast": {
                "scheduled_budget": round(sum(row["scheduled_budget"] for row in scheduled), 2),
                "expected_conversions": round(sum(row["expected_conversions"] for row in scheduled), 4),
                "activation_count": len(scheduled),
            },
        },
        "metadata": {
            "campaign_count": len({row["campaign_id"] for row in allocations}),
            "activation_count": len(scheduled), "window_count": len({row["window_id"] for row in scheduled}),
            "consumed_handoffs": ["campaign_allocations", "metadata"],
        },
    }
    return {JOB1: job1, JOB2: job2, JOB3: job3, JOB4: job4}


def _mutant_source(clean: str, instance: str) -> tuple[str, dict[str, Any] | None]:
    truth = TRUTH[instance]
    if truth is None:
        return clean, None
    old, new = MUTATIONS[instance]
    if clean.count(old) != 1:
        raise ValueError(f"mutation site is not unique: {instance}")
    mutated = clean.replace(old, new, 1)
    if ast.dump(ast.parse(clean)) == ast.dump(ast.parse(mutated)):
        raise ValueError("mutation did not alter the AST")
    statements = [
        node for node in ast.walk(ast.parse(clean))
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and old in (ast.get_source_segment(clean, node) or "")
    ]
    if len(statements) != 1:
        raise ValueError(f"mutation statement is not unique: {instance}")
    line = statements[0].lineno
    record = {
        "operator": "single_ast_site_substitution", "qualified_function_name": truth,
        "job_id": JOB1, "original_snippet": old, "mutant_snippet": new,
        "original_span": {"start_line": line, "end_line": line}, "candidate_count": 1,
        "exactly_one_source_site_changed": True, "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return mutated, record


def _pipeline(repo_root: Path, job_id: str, job1_source: str) -> GeneratedPipeline:
    paths = {
        JOB1: ("generated/protocol_2_2/n27pd_market_evidence.py", job1_source),
        JOB2: ("generated/protocol_2_2/n27pd_opportunity_priority.py", (repo_root / JOB2_SOURCE).read_text()),
        JOB3: ("generated/protocol_2_2/n27pd_campaign_allocation.py", (repo_root / JOB3_SOURCE).read_text()),
        JOB4: ("generated/protocol_2_2/n27pd_activation_schedule.py", (repo_root / JOB4_SOURCE).read_text()),
    }
    roles = {
        JOB1: (
            ("filter_applicable_evidence", "Transform market observations into applicable evidence.", ["market observations", "selection policy"], ["applicable evidence"]),
            ("normalize_source_observations", "Transform applicable evidence into per-source observations.", ["applicable evidence"], ["per-source observations"]),
            ("assemble_opportunity_evidence", "Transform per-source evidence into opportunity summaries and attribution.", ["per-source observations", "selection policy"], ["opportunities", "evidence attribution"]),
        ),
        JOB2: (
            ("join_commercial_context", "Transform opportunity and business context into enriched opportunities.", ["opportunities", "evidence attribution", "metadata", "capability coverage", "commercial context"], ["enriched opportunities"]),
            ("calculate_priority_inputs", "Transform enriched opportunities and attribution into priority inputs.", ["enriched opportunities", "evidence attribution"], ["priority inputs"]),
            ("rank_opportunity_portfolio", "Transform priority inputs into an opportunity portfolio.", ["priority inputs"], ["priority portfolio"]),
        ),
        JOB3: (
            ("aggregate_campaign_candidates", "Transform opportunities and attribution into campaign candidates and an audit mapping.", ["priority portfolio", "evidence attribution"], ["campaign candidates", "contribution audit"]),
            ("join_campaign_economics", "Transform campaign candidates and market economics into scored campaigns.", ["campaign candidates", "audience economics", "channel economics"], ["scored campaigns"]),
            ("allocate_campaign_budget", "Transform scored campaigns and a budget policy into campaign allocations.", ["scored campaigns", "budget policy"], ["campaign allocations"]),
        ),
        JOB4: (
            ("join_calendar_capacity", "Transform campaign allocations and scheduling context into feasible windows.", ["campaign allocations", "activation calendar", "channel capacity"], ["feasible windows"]),
            ("assign_activation_windows", "Transform feasible windows into scheduled activations.", ["feasible windows"], ["scheduled activations"]),
            ("aggregate_activation_forecast", "Transform scheduled activations into window and aggregate forecasts.", ["scheduled activations"], ["window forecast", "aggregate forecast"]),
        ),
    }
    path, source = paths[job_id]
    pipeline = GeneratedPipeline(
        entry_file=path,
        files=[GeneratedFile(path, source)],
        review_boundaries=[{
            "boundary_id": f"rb-blind-j{JOB_ORDER.index(job_id) + 1}-{index}",
            "function_name": name,
            "qualified_function_name": name,
            "source_path": path,
            "role": role,
            "expected_inputs": inputs,
            "expected_outputs": outputs,
            "semantic_stage": job_id,
        } for index, (name, role, inputs, outputs) in enumerate(roles[job_id], 1)],
    )
    pipeline.validate()
    return pipeline


def _job_input(job_id: str, prior: Mapping[str, Any] | None, root: Mapping[str, Any]) -> dict[str, Any]:
    if job_id == JOB1:
        return {key: deepcopy(root[key]) for key in ("scenario_id", "market_observations", "selection_policy")}
    if job_id == JOB2:
        return {
            "opportunities": deepcopy(prior["opportunities"]),
            "evidence_attribution": deepcopy(prior["evidence_attribution"]),
            "metadata": deepcopy(prior["metadata"]),
            "capability_coverage": deepcopy(root["capability_coverage"]),
            "commercial_context": deepcopy(root["commercial_context"]),
        }
    if job_id == JOB3:
        return {
            "priority_portfolio": deepcopy(prior["priority_portfolio"]),
            "evidence_attribution": deepcopy(prior["evidence_attribution"]),
            "metadata": deepcopy(prior["metadata"]),
            "audience_economics": deepcopy(root["audience_economics"]),
            "channel_economics": deepcopy(root["channel_economics"]),
            "budget_policy": deepcopy(root["budget_policy"]),
        }
    return {
        "campaign_allocations": deepcopy(prior["campaign_allocations"]),
        "metadata": deepcopy(prior["metadata"]),
        "activation_calendar": deepcopy(root["activation_calendar"]),
        "channel_capacity": deepcopy(root["channel_capacity"]),
    }


def _load_execution(branch: Path, job_id: str) -> Any | None:
    if not branch.exists():
        return None
    runs = sorted(branch.glob(f"jobstore/{job_id}/stages/n05/*/runs/*"))
    if len(runs) != 1:
        raise ValueError(f"partial Attempt-048 capture branch: {branch}")
    run_dir = runs[0]
    snapshot = _load_snapshot(JobStore(branch / "jobstore"), run_dir)
    if snapshot.scan_errors or not snapshot.nodes or not (run_dir / "etiq-native-lineage.json").is_file():
        raise ValueError(f"unreviewable Attempt-048 Etiq capture: {branch}")
    return n25.EtiqExecution(snapshot=snapshot, run_dir=run_dir)


def _validate_business_output(job_id: str, output: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    required = {
        JOB1: {"opportunities", "evidence_attribution", "metadata"},
        JOB2: {"priority_portfolio", "evidence_attribution", "metadata"},
        JOB3: {"campaign_allocations", "contribution_audit", "metadata"},
        JOB4: {"activation_plan", "metadata"},
    }[job_id]
    if set(output) != required:
        raise ValueError(f"unexpected output schema for {job_id}: {set(output)}")
    if job_id == JOB3:
        rows = output["campaign_allocations"]
        if not rows or len(rows) > 5 or len(runtime_input["priority_portfolio"]) < 12:
            raise ValueError("Job 3 did not perform the required many-to-few reduction")
    if job_id == JOB4:
        actions = output["activation_plan"]["activation_actions"]
        forbidden = {"opportunity_id", "source_id", "portfolio_position", "function_name"}
        if not actions or any(forbidden & set(row) for row in actions):
            raise ValueError("Job 4 output exposes an upstream identity or is empty")


def _capture_instance(repo_root: Path, target: Path, instance: str, job1_source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pipelines = {job: _pipeline(repo_root, job, job1_source) for job in JOB_ORDER}
    root = input_for(instance)
    jobs: dict[str, Any] = {}
    handoffs: list[dict[str, Any]] = []
    native_bindings: dict[str, Any] = {}
    prior = None
    names = {
        JOB2: ("opportunities", "evidence_attribution", "metadata"),
        JOB3: ("priority_portfolio", "evidence_attribution", "metadata"),
        JOB4: ("campaign_allocations", "metadata"),
    }
    for index, job_id in enumerate(JOB_ORDER):
        runtime_input = _job_input(job_id, prior, root)
        branch = target / "capture-branches" / instance / f"canonical-v2-job-{index + 1}"
        execution = _load_execution(branch, job_id)
        if execution is None:
            materialize_opaque_branch(branch, allowlist={}, manifest_identity={"purpose": "n27pd-fresh-native-capture", "case": instance, "job": job_id})
            copy_etiq_worker_runtime(branch, repo_root / "src")
            execution = execute_pipeline_in_branch(
                branch, repo_root=repo_root, job_id=job_id, pipeline=pipelines[job_id],
                runtime_input=runtime_input, run_index=INSTANCES.index(instance),
                stage=f"n27pd-{index + 1}",
            )
        output = _parse_output(execution)
        _validate_business_output(job_id, output, runtime_input)
        native_path = execution.run_dir / "etiq-native-lineage.json"
        native = _json(native_path)
        if not native.get("objects") or not native.get("edges"):
            raise ValueError(f"empty native Etiq structure: {instance}/{job_id}")
        realization = n25._realization(execution, pipelines[job_id], job_id)
        job = n25._job_record(execution, output, realization)
        job.update({
            "native_lineage": native,
            "native_lineage_file_sha256": ce.sha256(native_path.read_bytes()),
            "native_lineage_logical_sha256": ce.sha256(native),
            "native_lineage_export_status": execution.snapshot.inventories.get("json_lineage_export"),
        })
        jobs[job_id] = job
        native_bindings[job_id] = {
            "file_sha256": job["native_lineage_file_sha256"],
            "logical_sha256": job["native_lineage_logical_sha256"],
            "objects": len(native["objects"]), "edges": len(native["edges"]),
        }
        if index:
            producer = JOB_ORDER[index - 1]
            handoffs.extend(n25._handoff(name, producer, job_id, jobs[producer]["output"][name]) for name in names[job_id])
        prior = output
    capture = {
        "schema_version": "n27pd-four-job-native-capture-1",
        "capture_id": stable_id("rerun-capture", ["n27pd", instance], 0),
        "instance_id": instance, "job_ids": list(JOB_ORDER), "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": {job: ce.sha256(_pipeline_payload(pipelines[job])) for job in JOB_ORDER},
        "native_lineage_bindings": native_bindings, "canonical": True, "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    bundle = [{"job_id": job, "files": [{"path": pipelines[job].files[0].path, "content": pipelines[job].files[0].content}]} for job in JOB_ORDER]
    return capture, bundle


def _run_pipeline_sources(repo_root: Path, root: Mapping[str, Any], job1_source: str | None = None) -> dict[str, Any]:
    sources = [job1_source, None, None, None]
    paths = [JOB1_SOURCE, JOB2_SOURCE, JOB3_SOURCE, JOB4_SOURCE]
    outputs = {}
    prior = None
    with tempfile.TemporaryDirectory(prefix="n27pd-qualification-") as folder:
        for index, job_id in enumerate(JOB_ORDER):
            if sources[index] is None:
                executable = repo_root / paths[index]
            else:
                executable = Path(folder) / "job1.py"
                executable.write_text(str(sources[index]))
            runtime_input = _job_input(job_id, prior, root)
            result = subprocess.run(
                [sys.executable, str(executable)], input=json.dumps(runtime_input), text=True,
                capture_output=True, check=False, cwd=repo_root,
            )
            if result.returncode or result.stderr:
                raise ValueError(f"qualification execution failed for {job_id}: {result.stderr}")
            prior = json.loads(result.stdout)
            _validate_business_output(job_id, prior, runtime_input)
            outputs[job_id] = prior
    return outputs


def _interface_refs(catalogue: Mapping[str, Any], handoff: Mapping[str, Any]) -> dict[str, list[str]]:
    artifact = str(handoff["artifact_name"])
    aliases = {artifact, f"{artifact}_df"}
    refs = {}
    for side, job_key in (("producer_interface_refs", "upstream_job_id"), ("consumer_interface_refs", "downstream_job_id")):
        job = catalogue["jobs"][handoff[job_key]]
        native = [
            node["native_node_ref"] for node in job["native_graph"]["nodes"]
            if aliases & {str(name).strip("`") for name in node.get("names", [])}
        ]
        field = "expected_outputs" if side.startswith("producer") else "expected_inputs"
        boundaries = [boundary["boundary_id"] for boundary in job["realized_boundaries"] if artifact.replace("_", " ") in boundary.get(field, []) or artifact in boundary.get(field, [])]
        refs[side] = sorted(set(native + boundaries))
    return refs


def _connected_handoffs(catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = []
    for original in catalogue["handoffs"]:
        row = deepcopy(original)
        row.update(_interface_refs(catalogue, row))
        row["provenance_type"] = "controller_recorded_exact_hash_handoff"
        row["etiq_runtime_edge"] = False
        if row["producer_sha256"] != row["consumer_sha256"]:
            raise ValueError("producer/consumer handoff hash differs")
        values.append(row)
    if len(values) != 8 or len({row["handoff_id"] for row in values}) != 8:
        raise ValueError("Attempt 048 requires eight unique material handoffs")
    return values


def _capture_handoff_qualification(capture: Mapping[str, Any], catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = _connected_handoffs(catalogue)
    for row in values:
        producer = capture["jobs"][row["upstream_job_id"]]["output"][row["artifact_name"]]
        consumer = capture["jobs"][row["downstream_job_id"]]["input"][row["artifact_name"]]
        digest = ce.sha256(producer)
        if producer != consumer or digest != row["producer_sha256"] or digest != row["consumer_sha256"]:
            raise ValueError("cross-job handoff content/hash qualification failed")
    return values


def _replace_identifiers(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_identifiers(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_identifiers(item, replacements) for item in value]
    return replacements.get(value, value) if isinstance(value, str) else value


def _control_invariants(repo_root: Path, instance: str) -> dict[str, Any]:
    root = input_for(instance)
    clean = _run_pipeline_sources(repo_root, root)
    oracle = _hidden_oracle(root)
    if clean != oracle:
        raise ValueError(f"independent oracle mismatch: {instance}")
    permuted = deepcopy(root)
    permuted["market_observations"] = list(reversed(permuted["market_observations"]))
    if _run_pipeline_sources(repo_root, permuted) != clean:
        raise ValueError(f"permutation invariance failed: {instance}")
    inapplicable = deepcopy(root)
    inapplicable["market_observations"].append({
        **deepcopy(inapplicable["market_observations"][0]),
        "contribution_id": f"{instance}-inapplicable", "observed_at": "2027-01-01", "valid_until": "2027-02-01",
    })
    if _run_pipeline_sources(repo_root, inapplicable) != clean:
        raise ValueError(f"inapplicable-row invariance failed: {instance}")
    duplicate = deepcopy(root)
    duplicate["market_observations"].append(deepcopy(duplicate["market_observations"][5]))
    duplicate_output = _run_pipeline_sources(repo_root, duplicate)
    if (
        duplicate_output[JOB1]["opportunities"] != clean[JOB1]["opportunities"]
        or duplicate_output[JOB1]["evidence_attribution"] != clean[JOB1]["evidence_attribution"]
        or duplicate_output[JOB1]["metadata"]["per_source_observation_count"] != clean[JOB1]["metadata"]["per_source_observation_count"]
        or any(duplicate_output[job] != clean[job] for job in (JOB2, JOB3, JOB4))
    ):
        raise ValueError(f"duplicate-source invariance failed: {instance}")
    opportunity_ids = sorted({row["opportunity_id"] for row in root["market_observations"]})
    replacements = {value: f"renamed-op-{index:02d}" for index, value in enumerate(opportunity_ids, 1)}
    renamed = _replace_identifiers(root, replacements)
    if _run_pipeline_sources(repo_root, renamed) != _replace_identifiers(clean, replacements):
        raise ValueError(f"identifier-renaming invariance failed: {instance}")
    allocations = clean[JOB3]["campaign_allocations"]
    total = sum(row["allocated_budget"] for row in allocations)
    by_channel = {channel: sum(row["allocated_budget"] for row in allocations if row["channel"] == channel) for channel in root["budget_policy"]["per_channel_caps"]}
    if total > root["budget_policy"]["total_budget"] or any(by_channel[key] > root["budget_policy"]["per_channel_caps"][key] for key in by_channel):
        raise ValueError(f"budget conservation failed: {instance}")
    actions = clean[JOB4]["activation_plan"]["activation_actions"]
    used = {(channel, window): sum(row["channel"] == channel and row["window_id"] == window for row in actions) for channel, window in {(row["channel"], row["window_id"]) for row in root["channel_capacity"]}}
    allowed = {(row["channel"], row["window_id"]): row["available_slots"] for row in root["channel_capacity"]}
    if any(used[key] > allowed[key] for key in used):
        raise ValueError(f"schedule capacity failed: {instance}")
    source_contributions = {row["contribution_id"] for row in clean[JOB2]["evidence_attribution"]}
    audit_contributions = {row["contribution_id"] for row in clean[JOB3]["contribution_audit"]}
    if source_contributions != audit_contributions:
        raise ValueError(f"provenance conservation failed: {instance}")
    return {
        "oracle_exact_at_all_jobs": True, "permutation": True, "inapplicable_observation": True,
        "duplicate_observation": True, "opaque_identifier_renaming": True,
        "budget_and_channel_conservation": True, "schedule_capacity": True,
        "provenance_conservation": True,
    }


def _hard_fault_qualification(captures: Mapping[str, Mapping[str, Any]], instances: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    outputs = {instance: capture["jobs"][JOB4]["output"] for instance, capture in captures.items()}
    hashes = {instance: ce.sha256(output) for instance, output in outputs.items()}
    if len({hashes[instance] for instance in INSTANCES[2:]}) != 3:
        raise ValueError("fault Job-4 symptoms are not distinct")
    execution = {}
    deltas = {}
    for fault, clean in MATCHED_CLEAN.items():
        mutation = instances[fault]["mutation"]
        nodes = captures[fault]["jobs"][JOB1]["snapshot"]["nodes"]
        executed = [
            node["node_ref"] for node in nodes
            if mutation["qualified_function_name"] in ",".join(map(str, node.get("func_stack", [])))
            and int(node.get("line_no") or 0) >= mutation["original_span"]["start_line"]
        ]
        if not executed:
            raise ValueError(f"mutated statement did not execute: {fault}")
        fault_actions = outputs[fault]["activation_plan"]["activation_actions"]
        clean_actions = outputs[clean]["activation_plan"]["activation_actions"]
        if len(fault_actions) != len(clean_actions) or outputs[fault]["metadata"] != outputs[clean]["metadata"]:
            raise ValueError(f"fault changed Job-4 counts: {fault}")
        clean_campaigns = {row["campaign_id"]: row for row in clean_actions}
        fault_campaigns = {row["campaign_id"]: row for row in fault_actions}
        affected = sorted({campaign for campaign in clean_campaigns if clean_campaigns[campaign] != fault_campaigns.get(campaign)})
        if not 1 <= len(affected) <= 2:
            raise ValueError(f"fault symptom is not limited to one or two campaigns: {fault}/{affected}")
        execution[fault] = {"mutated_scope_executed": True, "captured_state_refs": executed[:8]}
        deltas[fault] = {
            "matched_clean_case": clean, "clean_job4_sha256": hashes[clean], "fault_job4_sha256": hashes[fault],
            "job4_campaign_action_counts_equal": True, "affected_campaign_count": len(affected),
            "affected_campaigns_controller_only": affected,
        }
    for instance, capture in captures.items():
        if any(capture["jobs"][job]["stderr"] for job in JOB_ORDER):
            raise ValueError(f"non-empty job error log: {instance}")
    return {
        "schema_version": "n27pd-hard-fault-qualification-1", "status": "passed",
        "clean_controls": 2, "one_site_faults": 3, "distinct_fault_job4_hashes": True,
        "one_site_executed_mutations": execution, "controller_only_deltas": deltas,
        "all_faults_preserve_schemas_and_job4_counts": True,
    }


def _load_prepared(target: Path) -> dict[str, Any]:
    folders = {
        "captures": "captures", "catalogues": "catalogues", "instances": "instances",
        "source_bundles": "source-bundles", "crosswalks": "native-crosswalks",
        "indexes": "native-subtree-index", "reviewer_nodes": "payload-lazy-nodes",
        "disclosures": "artifact-disclosures", "omissions": "omission-manifests",
    }
    values = {name: {path.stem: _json(path) for path in sorted((target / folder).glob("*.json"))} for name, folder in folders.items()}
    if any(set(collection) != set(INSTANCES) for collection in values.values()):
        raise ValueError("Attempt 048 prepared record set is partial")
    for instance in INSTANCES:
        values["source_bundles"][instance] = values["source_bundles"][instance]["source_bundle"]
    return values


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_reuse()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PD is authorized only for Attempt 048")
    authority = _verify_authority(repo_root)
    if len(list((target / "captures").glob("*.json"))) == len(INSTANCES):
        return _load_prepared(target) | {"authority": authority}
    clean_source = (repo_root / JOB1_SOURCE).read_text()
    clean_roots = {instance: input_for(instance) for instance in INSTANCES[:2]}
    oracle_record = {
        "schema_version": "n27pd-hidden-oracle-freeze-1",
        "status": "frozen_before_mutant_construction",
        "controller_only": True,
        "oracle_source": inspect.getsource(_hidden_oracle),
        "oracle_source_sha256": ce.sha256(inspect.getsource(_hidden_oracle).encode()),
        "clean_inputs_sha256": {instance: ce.sha256(value) for instance, value in clean_roots.items()},
        "clean_outputs": {instance: _hidden_oracle(value) for instance, value in clean_roots.items()},
        "mutation_records_existing_at_freeze": 0,
    }
    oracle_record["oracle_freeze_sha256"] = ce.sha256(oracle_record)
    ce._write_immutable(target / ORACLE_FREEZE, oracle_record)
    controls = {instance: _control_invariants(repo_root, instance) for instance in INSTANCES[:2]}
    control_record = {
        "schema_version": "n27pd-clean-control-qualification-1", "status": "passed",
        "independent_controls": controls, "oracle_frozen_before_mutants": True,
    }
    control_record["qualification_sha256"] = ce.sha256(control_record)
    ce._write_immutable(target / "qualification/clean-controls.json", control_record)
    prepared = {name: {} for name in (
        "captures", "catalogues", "instances", "source_bundles", "crosswalks",
        "indexes", "reviewer_nodes", "disclosures", "omissions",
    )}
    topology = {}
    handoff_records = {}
    for position, instance in enumerate(INSTANCES):
        source, mutation = _mutant_source(clean_source, instance)
        capture, source_bundle = _capture_instance(repo_root, target, instance, source)
        catalogue, crosswalk = n27p._catalogue(capture)
        catalogue["schema_version"] = "n27pd-four-job-native-catalogue-1"
        catalogue["handoffs"] = _connected_handoffs(catalogue)
        catalogue.pop("catalogue_sha256", None)
        catalogue["catalogue_sha256"] = ce.sha256(catalogue)
        compact, index = n27p.build_compact_graph(catalogue, crosswalk)
        topology[instance] = n27pa._topology_qualification(catalogue, index)
        if position == 1 and not all(value["passed"] for value in topology[instance].values()):
            raise ValueError("clean native topology failed before faulty captures")
        handoff_records[instance] = _capture_handoff_qualification(capture, catalogue)
        reviewer, disclosure, omission = pb._payload_lazy_catalogue(catalogue, instance)
        lazy_compact = pb._lazy_graph(compact, reviewer)
        pb._assert_payload_lazy(lazy_compact, disclosure)
        instance_record = {
            "schema_version": "n27pd-instance-1", "opaque_instance_id": instance,
            "designation": "matched_clean_control" if mutation is None else "upstream_fault",
            "truth_job": None if mutation is None else JOB1, "truth_function": TRUTH[instance],
            "mutation": mutation, "matched_clean_case": MATCHED_CLEAN.get(instance),
            "capture_sha256": capture["capture_sha256"], "catalogue_sha256": catalogue["catalogue_sha256"],
            "source_sha256": deepcopy(capture["source_sha256"]),
        }
        instance_record["instance_sha256"] = ce.sha256(instance_record)
        records = {
            "captures": capture, "catalogues": catalogue, "source_bundles": {"source_bundle": source_bundle},
            "crosswalks": crosswalk, "indexes": index, "reviewer_nodes": reviewer,
            "disclosures": disclosure, "omissions": omission, "instances": instance_record,
        }
        folders = {
            "captures": "captures", "catalogues": "catalogues", "source_bundles": "source-bundles",
            "crosswalks": "native-crosswalks", "indexes": "native-subtree-index",
            "reviewer_nodes": "payload-lazy-nodes", "disclosures": "artifact-disclosures",
            "omissions": "omission-manifests", "instances": "instances",
        }
        for name, record in records.items():
            ce._write_immutable(target / folders[name] / f"{instance}.json", record)
            prepared[name][instance] = source_bundle if name == "source_bundles" else record
        ce._write_immutable(target / "projections" / f"{instance}-compact.json", lazy_compact)
        for job in JOB_ORDER:
            raw = capture["jobs"][job]["native_lineage"]
            export = target / "native-exports" / instance / job / "etiq-native-lineage.json"
            ce._write_immutable(export, raw)
            record = {
                "schema_version": "n27pd-fresh-native-job-capture-1", "instance": instance,
                "job_id": job, "capture_status": "fresh_n27pd_execution",
                "required_api": 'create_full_lineage_graph(graph_format="json")',
                "native_export_file_sha256": ce.sha256(export.read_bytes()),
                "native_export_logical_sha256": ce.sha256(raw),
                "job_capture_sha256": ce.sha256(capture["jobs"][job]),
            }
            record["record_sha256"] = ce.sha256(record)
            ce._write_immutable(target / "job-captures" / instance / f"{job}.json", record)
    hard = _hard_fault_qualification(prepared["captures"], prepared["instances"])
    hard["qualification_sha256"] = ce.sha256(hard)
    ce._write_immutable(target / "qualification/hard-faults.json", hard)
    capture_qualification = {
        "schema_version": "n27pd-native-capture-qualification-1", "status": "passed",
        "instances": 5, "fresh_job_executions": 20, "etiq_version": "2.3.0",
        "required_api": 'create_full_lineage_graph(graph_format="json")',
        "clean_topology_validated_before_faulty_instances": True,
        "topology": topology, "handoffs": handoff_records, "handoff_count_per_instance": 8,
        "all_native_objects_edges_clusters_preserved": True,
        "all_handoffs_exact_hash_and_schema_valid": True,
    }
    capture_qualification["qualification_sha256"] = ce.sha256(capture_qualification)
    ce._write_immutable(target / "qualification/native-captures-and-handoffs.json", capture_qualification)
    return prepared | {"authority": authority}


def _with_handoffs(graph: Mapping[str, Any], handoffs: list[dict[str, Any]]) -> dict[str, Any]:
    value = deepcopy(dict(graph))
    value["handoffs"] = deepcopy(handoffs)
    value.pop("projection_sha256", None)
    value["projection_sha256"] = ce.sha256(value)
    return value


def _execution_record(catalogue: Mapping[str, Any], job_id: str) -> dict[str, Any]:
    position = JOB_ORDER.index(job_id) + 1
    return {
        "job": f"job_{position}", "captured_job_id": job_id,
        "input": deepcopy(catalogue["jobs"][job_id]["input"]),
        "output": deepcopy(catalogue["jobs"][job_id]["output"]),
        "stdout": str(catalogue["jobs"][job_id]["stdout"]),
        "stderr": str(catalogue["jobs"][job_id]["stderr"]),
    }


def _semantic_declarations(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    values = []
    for position, job_id in enumerate(JOB_ORDER, 1):
        for boundary in catalogue["jobs"][job_id]["realized_boundaries"]:
            values.append({
                "declaration_id": f"decl-{ce.sha256([job_id, boundary['boundary_id']])[7:23]}",
                "job_position": position,
                "qualified_function_identity": boundary["function_name"],
                "source_location": {
                    "path": boundary["static_identity"]["source_path"],
                    "function_source_sha256": boundary["static_identity"]["function_source_sha256"],
                },
                "declared_input_artifacts": deepcopy(boundary["expected_inputs"]),
                "declared_output_artifacts": deepcopy(boundary["expected_outputs"]),
                "neutral_transformation_responsibility": boundary["role"],
            })
    if len(values) != 12:
        raise ValueError("semantic declarations must cover all twelve functions")
    return {"semantic_declarations": values}


def _base_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    job1_input = catalogue["jobs"][JOB1]["input"]
    job2_input = catalogue["jobs"][JOB2]["input"]
    job3_input = catalogue["jobs"][JOB3]["input"]
    return {
        "schema_version": "n27pd-review-package-1",
        "business_brief": BUSINESS_BRIEF,
        "pipeline_topology": [
            {"job": f"job_{position}", "captured_job_id": job_id, "position": position, "observation_point": job_id == JOB4}
            for position, job_id in enumerate(JOB_ORDER, 1)
        ],
        "top_level_job_1_input": deepcopy(job1_input),
        "workflow_policy_inputs": {
            "capability_coverage": deepcopy(job2_input["capability_coverage"]),
            "commercial_context": deepcopy(job2_input["commercial_context"]),
            "audience_economics": deepcopy(job3_input["audience_economics"]),
            "channel_economics": deepcopy(job3_input["channel_economics"]),
            "budget_policy": deepcopy(job3_input["budget_policy"]),
        },
        "observed_job_4_execution": _execution_record(catalogue, JOB4),
        "separate_complete_source_bundle": deepcopy(source_bundle),
        "final_response_contract": {
            "fault_detected": "Boolean", "suspect_job": "job_1, job_2, job_3, job_4, or null",
            "suspect_function": "a function visible in supplied evidence, or null",
            "explanation": "concise evidence-grounded reasoning",
            "cited_evidence": "opaque references or short exact visible excerpts",
        },
    }


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], compact: Mapping[str, Any], mode: str) -> dict[str, Any]:
    package = _base_package(catalogue, source_bundle)
    if mode != "P01":
        package["graph_review"] = {
            "framing": "Captured native execution structure and separately labelled exact-hash handoffs may be used in the assessment.",
            "evidence": deepcopy(compact),
        }
    if mode in {"P03", "P05"}:
        package["semantic_declaration_bundle"] = _semantic_declarations(catalogue)
    if mode in {"P04", "P05"}:
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {
            "operation": "expand_execution_group_then_artifact_inspection",
            "model_selects_group_artifact_and_mode": True,
            "required_before_terminal": True, "maximum_completed_expansions": 1,
            "maximum_completed_inspections": 1,
        }
    elif mode == "P06":
        package["available_operations"] = ["reconsider_same_evidence"]
        package["interaction_contract"] = {
            "operation": "reconsider_same_evidence", "required_passes": 2,
            "evidence_bytes_added_each_pass": 0,
        }
    return package


def schedule() -> dict[str, Any]:
    cells = []
    for instance in INSTANCES:
        for mode in CELLS:
            cells.append({
                "opaque_instance_id": instance, "cell_id": mode, "mode": mode,
                "mode_name": MODE_NAMES[mode],
                "declaration_setting": "B1" if mode in {"P03", "P05"} else "B0",
                "branch_id": f"brn-{ce.sha256(['n27pd', instance, mode])[7:23]}",
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
                    "trial_id": f"trial-{ce.sha256(['n27pd', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if (len(cells), len(reviews), len({row["trial_id"] for row in reviews})) != (30, 60, 60):
        raise AssertionError("Attempt 048 schedule counts changed")
    if sum(CALLS_BY_MODE[row["mode"]] for row in reviews) != 120:
        raise AssertionError("Attempt 048 planned call count changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _package_records(target: Path) -> list[dict[str, Any]]:
    return pb._package_records(target)


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return pb._initial_evidence(package)


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by = {(row["controller_condition"]["opaque_instance_id"], row["controller_condition"]["cell_id"]): row["reviewer_package"] for row in records}
    rows = []
    for instance in INSTANCES:
        specs = (
            ("compact_graph_only", "P01", "P02", {"graph_review"}),
            ("semantic_only", "P02", "P03", {"semantic_declaration_bundle"}),
            ("adaptive_semantic_only", "P04", "P05", {"semantic_declaration_bundle"}),
        )
        for name, left_id, right_id, roots in specs:
            left = _initial_evidence(by[(instance, left_id)])
            right = _initial_evidence(by[(instance, right_id)])
            paths = n25._diff_paths(left, right)
            passed = bool(paths) and all(path.split(".")[1] in roots for path in paths)
            rows.append({"instance": instance, "invariant": name, "left": left_id, "right": right_id, "differing_paths": paths, "passed": passed})
        graph_hashes = [ce.sha256(by[(instance, cell)]["graph_review"]["evidence"]) for cell in ("P02", "P03", "P04", "P05", "P06")]
        rows.append({"instance": instance, "invariant": "byte_identical_initial_graph", "passed": len(set(graph_hashes)) == 1})
        b0_hashes = [ce.sha256(_initial_evidence(by[(instance, cell)])) for cell in ("P02", "P04", "P06")]
        rows.append({"instance": instance, "invariant": "b0_initial_evidence_equal", "passed": len(set(b0_hashes)) == 1})
        mechanics_left = {key: value for key, value in by[(instance, "P04")].items() if key != "semantic_declaration_bundle"}
        mechanics_right = {key: value for key, value in by[(instance, "P05")].items() if key != "semantic_declaration_bundle"}
        rows.append({"instance": instance, "invariant": "adaptive_mechanics_equal", "passed": mechanics_left == mechanics_right})
    if not all(row["passed"] for row in rows):
        raise ValueError(f"pairwise isolation failed: {[row for row in rows if not row['passed']][:3]}")
    return rows


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _configure_reuse()
    return pb.render_request(package, operation_response)


def _schema_for_stage(stage: str) -> Path:
    return {"final": FINAL_SCHEMA, "group": GROUP_SCHEMA, "artifact": ARTIFACT_SCHEMA, "reconsider": RECONSIDER_SCHEMA}[stage]


def validate_schemas(repo_root: Path) -> dict[str, str]:
    values = {}
    for path in (FINAL_SCHEMA, GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA):
        schema = _json(repo_root / path)
        Draft202012Validator.check_schema(schema)
        validate_strict_provider_schema(schema)
        values[path.as_posix()] = ce.sha256((repo_root / path).read_bytes())
    return values


def _leakage_audit(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    common_hashes = set()
    for record in records:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        common = {
            "business_brief": package["business_brief"],
            "pipeline_topology": package["pipeline_topology"],
            "final_response_contract": package["final_response_contract"],
        }
        common_hashes.add(ce.sha256(common))
        audited = {
            "common": common,
            "graph_framing": package.get("graph_review", {}).get("framing"),
            "operation": package.get("interaction_contract"),
            "semantic": package.get("semantic_declaration_bundle"),
        }
        visible = ce.canonical_json(audited).decode().lower()
        prohibited = [
            '"_valid_until"] >= as_of', '"_valid_until"] > as_of',
            '["opportunity_id", "source_id", "observed_at"]',
            '["opportunity_id", "source_id", "valid_until"]',
            'left_on="evidence_opportunity_id"', 'left_on="partner_opportunity_id"',
            "wrong survivor", "clean delta", "expected clean", "fault identity",
        ]
        hits = [term for term in prohibited if term in visible]
        if hits:
            raise ValueError(f"reviewer-visible non-source leakage: {condition['cell_id']}/{hits}")
        brief = package["business_brief"].lower()
        if any(name in brief for name in TRUTH.values() if name):
            raise ValueError("business brief names a Job-1 function")
        declarations = package.get("semantic_declaration_bundle", {}).get("semantic_declarations", [])
        if (condition["cell_id"] in {"P03", "P05"}) != bool(declarations):
            raise ValueError("semantic declaration treatment placement changed")
        rows.append({
            "opaque_instance_id": condition["opaque_instance_id"], "cell_id": condition["cell_id"],
            "common_text_sha256": ce.sha256(common), "audited_non_source_sha256": ce.sha256(audited),
            "prohibited_hits": hits, "passed": True,
        })
    if len(common_hashes) != 1:
        raise ValueError("reviewer-visible common text differs across instances")
    return {
        "schema_version": "n27pd-reviewer-leakage-audit-1", "status": "passed",
        "source_and_genuine_native_records_excluded_from_sanitization": True,
        "common_non_source_text_byte_identical": True, "rows": rows,
    }


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(records), len(design["review_trials"])) != (30, 60):
        raise ValueError("Attempt 048 package/review counts changed")
    schemas = validate_schemas(repo_root)
    pairwise = _pairwise_checks(records)
    leakage = _leakage_audit(records)
    maximum = 0
    artifact_maximum = 0
    for record in records:
        package = record["reviewer_package"]
        condition = record["controller_condition"]
        if package["business_brief"] != BUSINESS_BRIEF or "behavioural_criteria" in package:
            raise ValueError("reviewer brief was expanded or replaced")
        if len(package["separate_complete_source_bundle"]) != 4:
            raise ValueError("a package does not include all four complete actual sources")
        if condition["mode"] == "P01" and "graph_review" in package:
            raise ValueError("Current received graph evidence")
        if condition["mode"] != "P01":
            graph = package["graph_review"]["evidence"]
            if len(graph["handoffs"]) != 8:
                raise ValueError("connected graph lacks an exact handoff")
            pb._assert_payload_lazy(graph, prepared["disclosures"][condition["opaque_instance_id"]])
        maximum = max(maximum, n25._token_count(render_request(package)))
    for instance in INSTANCES:
        groups = _json(target / "qualification/adaptive-fault-relevance.json")["inspectable_artifacts_per_selectable_group"][instance]
        if len(groups) != 12 or any(count < 1 for count in groups.values()):
            raise ValueError("a native function group is missing an inspectable artifact")
        for artifact in prepared["disclosures"][instance]["artifacts"].values():
            artifact_maximum = max(artifact_maximum, n25._token_count(artifact["operation_node"]["artifact_content"]))
    expected_calls = sum(CALLS_BY_MODE[row["mode"]] for row in design["review_trials"])
    if expected_calls != 120 or max(maximum, artifact_maximum) >= 100_000:
        raise ValueError("call count or provider context qualification failed")
    return {
        "schema_version": "n27pd-no-model-verification-1", "status": "passed", "model_calls": 0,
        "instances": 5, "fresh_job_executions": 20, "packages": 30, "terminal_reviews": 60,
        "required_follow_up_calls": 60, "planned_provider_calls": 120, "repairs": 0,
        "strict_schema_hashes": schemas, "pairwise_checks": len(pairwise),
        "leakage_rows": len(leakage["rows"]),
        "maximum_initial_request_tokens": maximum,
        "maximum_complete_artifact_tokens": artifact_maximum,
        "provider_context_qualification_limit": 100_000,
        "fault_denominator_per_cell": 6, "control_denominator_per_cell": 4,
        "per_fault_denominator": 2, "per_control_denominator": 2,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_reuse()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if len(existing) == 30:
        qualification = qualify_packages(repo_root, target, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    relevance = pb.adaptive_relevance(prepared, target)
    relevance["schema_version"] = "n27pd-adaptive-relevance-1"
    relevance.pop("qualification_sha256", None)
    relevance["qualification_sha256"] = ce.sha256(relevance)
    ce._write_immutable(target / "qualification/adaptive-fault-relevance.json", relevance)
    graphs = {}
    for instance in INSTANCES:
        compact = _json(target / "projections" / f"{instance}-compact.json")
        graphs[instance] = _with_handoffs(compact, prepared["catalogues"][instance]["handoffs"])
        pb._assert_payload_lazy(graphs[instance], prepared["disclosures"][instance])
        ce._write_immutable(target / "projections" / f"{instance}-compact-end-to-end.json", graphs[instance])
    existing_by_branch = {record["controller_condition"]["branch_id"]: record for record in existing}
    records = []
    for condition in design["cells"]:
        if condition["branch_id"] in existing_by_branch:
            records.append(existing_by_branch[condition["branch_id"]])
            continue
        instance = condition["opaque_instance_id"]
        package = build_package(prepared["catalogues"][instance], prepared["source_bundles"][instance], graphs[instance], condition["mode"])
        record = {
            "schema_version": "n27pd-frozen-package-1", "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance]["catalogue_sha256"],
            "disclosure_catalogue_sha256": prepared["disclosures"][instance]["catalogue_sha256"],
            "omission_manifest_sha256": prepared["omissions"][instance]["manifest_sha256"],
            "business_brief_sha256": ce.sha256(BUSINESS_BRIEF.encode()),
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        path = target / "packages" / condition["branch_id"] / "reviewer-package.json"
        ce._write_immutable(path, record)
        manifest = {
            "schema_version": "n27pd-controller-manifest-1", "controller_condition": deepcopy(condition),
            "reviewer_package_path": path.relative_to(target).as_posix(),
            "reviewer_package_file_sha256": ce.sha256(path.read_bytes()), "package_sha256": record["package_sha256"],
        }
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{condition['branch_id']}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, target, records, prepared, design)
    leakage = _leakage_audit(records)
    leakage["audit_sha256"] = ce.sha256(leakage)
    ce._write_immutable(target / "qualification/reviewer-leakage-audit.json", leakage)
    pairwise = {"schema_version": "n27pd-pairwise-package-differences-1", "rows": _pairwise_checks(records), "all_passed": True}
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {"schema_version": "n27pd-review-design-1", "review_trials": design["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n27pd-repair-design-1", "repair_traces": []})
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27pd_experiment.py"), JOB1_SOURCE, JOB2_SOURCE, JOB3_SOURCE, JOB4_SOURCE,
        PROMPT, FINAL_SCHEMA, GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27pd_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 048 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after live reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("focused N27PD tests must pass before freeze")
    freeze = {
        "schema_version": "n27pd-experiment-freeze-1", "attempt": "048",
        "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "attempt_047_hashes": deepcopy(ATTEMPT_047_HASHES),
        "protected_hashes": deepcopy(PROTECTED_HASHES),
        "sandbox_gate_file_sha256": ce.sha256((repo_root / SANDBOX_GATE).read_bytes()),
        "sandbox_bindings": deepcopy(built["prepared"]["authority"]["sandbox"]),
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
        "expected_counts": {"instances": 5, "fresh_job_executions": 20, "packages": 30, "reviews": 60, "follow_up_calls": 60, "provider_calls": 120, "repairs": 0},
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
        "schema_version": "n27pd-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "one_use_live_authority": True,
        "authorized_calls": 120, "repairs": 0,
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], stage: str) -> dict[str, Any]:
    _configure_reuse()
    return pb.validate_response(repo_root, package, response, stage)


def score_response(instance: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    return pb.score_response(instance, validation)


def run_review_session(repo_root: Path, target: Path, catalogue: Mapping[str, Any], reviewer: Mapping[str, Any], disclosure: Mapping[str, Any], index: Mapping[str, Any], package_record: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    _configure_reuse()
    translated = deepcopy(dict(package_record))
    translated["controller_condition"] = deepcopy(dict(package_record["controller_condition"]))
    translated["controller_condition"]["mode"] = {"P04": "P10", "P05": "P10", "P06": "P12"}.get(package_record["controller_condition"]["mode"], "P01")
    return pb.run_review_session(repo_root, target, catalogue, reviewer, disclosure, index, translated, trial_id)


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return pb.reconstruct_counts(reviews)


def _actual_usage(usage: Mapping[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": int(usage.get("cumulative_actual_input_tokens") or usage.get("input_tokens") or 0),
        "cached_input_tokens": int(usage.get("cumulative_actual_cached_input_tokens") or usage.get("cached_input_tokens") or 0),
        "output_tokens": int(usage.get("cumulative_actual_output_tokens") or usage.get("output_tokens") or 0),
    }


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for review in reviews:
        trial = review["controller_trial"]
        usage = _actual_usage(review["usage"])
        group = review.get("selected_group") or {}
        artifact = review.get("selected_artifact") or {}
        rows.append({
            "trial_id": trial["trial_id"], "instance": trial["opaque_instance_id"],
            "cell_id": trial["cell_id"], "mode": trial["mode"], "repetition": trial["repetition"],
            "designation": review["designation"], "fault_detected": bool(review["fault_detected"]),
            "correct_job_attribution": bool(review["correct_job_attribution"]),
            "exact_function_localisation": bool(review["exact_function_localisation"]),
            "false_positive": bool(review["false_positive"]),
            "suspect_job": review["suspect_job"], "suspect_function": review["suspect_function"],
            "pre_fault_detected": bool(review["pre_fault_detected"]),
            "pre_suspect_job": review["pre_suspect_job"], "pre_suspect_function": review["pre_suspect_function"],
            "answer_changed": bool(review["answer_changed"]),
            "execution_group_id": group.get("execution_group_id"),
            "selected_group_contained_truth_state": bool(review["selected_group_contained_truth_state"]),
            "artifact_ref": artifact.get("artifact_ref"), "inspection": artifact.get("inspection"),
            "selected_artifact_was_truth_state": bool(review["selected_artifact_was_truth_state"]),
            "artifact_bytes_returned": int(artifact.get("artifact_bytes_returned") or 0),
            "provider_calls": len(review["call_records"]), **usage,
            "total_tokens": usage["input_tokens"] + usage["output_tokens"],
            "invalid_citation_ref_count": len(review["invalid_evidence_refs"]),
        })
    return rows


def _ratio(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    return {"numerator": sum(bool(row[key]) for row in rows), "denominator": len(rows)}


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    return {
        "reviews": len(rows), "provider_calls": sum(row["provider_calls"] for row in rows),
        "fault_detection": _ratio(faults, "fault_detected"),
        "correct_job_attribution": _ratio(faults, "correct_job_attribution"),
        "exact_function_localisation": _ratio(faults, "exact_function_localisation"),
        "control_false_positives": _ratio(controls, "false_positive"),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "cached_input_tokens": sum(row["cached_input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "total_tokens": sum(row["total_tokens"] for row in rows),
    }


def _contrast(rows: list[Mapping[str, Any]], name: str, left: str, right: str) -> list[dict[str, Any]]:
    values = []
    for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation"):
        differences = []
        for instance in MATCHED_CLEAN:
            left_values = [float(row[outcome]) for row in rows if row["instance"] == instance and row["cell_id"] == left]
            right_values = [float(row[outcome]) for row in rows if row["instance"] == instance and row["cell_id"] == right]
            differences.append(sum(left_values) / len(left_values) - sum(right_values) / len(right_values))
        values.append({
            "name": name, "left": left, "right": right, "population": "three_fault_instances",
            "outcome": outcome, "per_instance_differences_after_averaging_repetitions": differences,
            "mean_difference": sum(differences) / len(differences),
        })
    differences = []
    for instance in INSTANCES[:2]:
        left_values = [float(row["false_positive"]) for row in rows if row["instance"] == instance and row["cell_id"] == left]
        right_values = [float(row["false_positive"]) for row in rows if row["instance"] == instance and row["cell_id"] == right]
        differences.append(sum(left_values) / len(left_values) - sum(right_values) / len(right_values))
    values.append({
        "name": name, "left": left, "right": right, "population": "two_clean_controls",
        "outcome": "false_positive", "per_instance_differences_after_averaging_repetitions": differences,
        "mean_difference": sum(differences) / len(differences),
    })
    return values


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    aggregate = _summary(rows)
    cells = {cell: _summary([row for row in rows if row["cell_id"] == cell]) for cell in CELLS}
    for cell, value in cells.items():
        if value["fault_detection"]["denominator"] != 6 or value["control_false_positives"]["denominator"] != 4:
            raise RuntimeError(f"fault/control denominator changed: {cell}")
    if aggregate["provider_calls"] and not (aggregate["input_tokens"] and aggregate["output_tokens"]):
        raise RuntimeError("provider calls produced zero actual token usage")
    specs = (
        ("compact_graph_on_source", "P02", "P01"),
        ("semantic_on_fixed_graph", "P03", "P02"),
        ("nested_evidence_vs_equal_calls", "P04", "P06"),
        ("semantic_within_adaptive", "P05", "P04"),
        ("adaptive_vs_static_compact", "P04", "P02"),
    )
    contrasts = [row for name, left, right in specs for row in _contrast(rows, name, left, right)]
    for row in contrasts:
        if row["name"] == "adaptive_vs_static_compact":
            row["call_count_caveat"] = "P04 uses three calls and P02 one call"
    fault_cells = {f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell]) for instance in MATCHED_CLEAN for cell in CELLS}
    control_cells = {f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell]) for instance in INSTANCES[:2] for cell in CELLS}
    if any(value["fault_detection"]["denominator"] != 2 for value in fault_cells.values()):
        raise RuntimeError("per-fault denominator changed")
    if any(value["control_false_positives"]["denominator"] != 2 for value in control_cells.values()):
        raise RuntimeError("per-control denominator changed")
    analysis = {
        "schema_version": "n27pd-pilot-analysis-1", "exploratory_not_confirmatory": True,
        "population_level_significance_claimed": False, "full_replication_remains_deferred": True,
        "aggregate": aggregate, "cell_summaries": cells,
        "fault_summaries": {instance: _summary([row for row in rows if row["instance"] == instance]) for instance in MATCHED_CLEAN},
        "control_summaries": {instance: _summary([row for row in rows if row["instance"] == instance]) for instance in INSTANCES[:2]},
        "fault_cell_summaries": fault_cells, "control_cell_summaries": control_cells,
        "prespecified_descriptive_contrasts": contrasts,
        "operations": {
            "adaptive_sessions": sum(row["mode"] in {"P04", "P05"} for row in rows),
            "reconsideration_sessions": sum(row["mode"] == "P06" for row in rows),
            "answer_changes": sum(row["answer_changed"] for row in rows),
            "truth_group_selections": sum(row["selected_group_contained_truth_state"] for row in rows),
            "truth_artifact_selections": sum(row["selected_artifact_was_truth_state"] for row in rows),
            "artifact_bytes_returned": sum(row["artifact_bytes_returned"] for row in rows),
        },
        "actual_usage": {key: aggregate[key] for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")},
        "leakage_audit_sha256": _json(target / "qualification/reviewer-leakage-audit.json")["audit_sha256"],
        "limitations": [
            "This five-instance, two-repetition pilot is exploratory and is not a population-level significance test.",
            "The three distinct Job-1 faults, not repeated reviews, are the independent faulty units.",
            "The later full ICLR replication was not started.",
        ],
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(target / "analysis/summary.json", analysis)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    _write_text(target / "analysis/all-review-rows.csv", stream.getvalue())
    token_report = {
        "schema_version": "n27pd-actual-token-report-1", "provider_calls": aggregate["provider_calls"],
        **analysis["actual_usage"], "derived_total_rule": "input_tokens_plus_output_tokens",
        "all_values_from_immutable_provider_receipts": True,
    }
    token_report["report_sha256"] = ce.sha256(token_report)
    ce._write_immutable(target / "analysis/actual-token-report.json", token_report)
    return target / "analysis/summary.json"


def _rate(value: Mapping[str, int]) -> str:
    return "n/a" if not value["denominator"] else f"{value['numerator']}/{value['denominator']} ({100 * value['numerator'] / value['denominator']:.2f}%)"


def _write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PD-blinded-business-brief-hard-fault-pilot"
    findings = [
        "# N27PD blinded-business-brief hard-fault pilot", "",
        "Attempt 048 completed the authorized five-instance exploratory pilot. The full replication remains deferred.", "",
        "## Aggregate outcomes", "",
        f"- Fault detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Actual provider calls: {aggregate['provider_calls']}",
        f"- Actual tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; derived total {aggregate['total_tokens']}", "",
        "## Scope", "",
        "All 20 captures are fresh native Etiq executions. Complete actual source and one blinded business brief were held constant across treatments. Graph arms contain all eight separately labelled exact-hash handoffs. No repairs were run.", "",
        "The results are descriptive for three fault instances and two controls with two repetitions each; they do not support population-level significance claims.", "",
        "## Immutable records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-048/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-048/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-048/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-048/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    cell_lines = ["# Complete cell table", "", "| Cell | Reviews | Fault detection /6 | Job 1 /6 | Exact /6 | Control FP /4 | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in CELLS:
        value = analysis["cell_summaries"][cell]
        cell_lines.append(f"| {cell} | {value['reviews']} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} | {_rate(value['control_false_positives'])} | {value['provider_calls']} |")
    _write_text(report_dir / "cell-table.md", "\n".join(cell_lines))
    fault_lines = ["# Complete fault table", "", "| Fault instance | Cell | Detection /2 | Job 1 /2 | Exact /2 |", "|---|---|---:|---:|---:|"]
    for instance in MATCHED_CLEAN:
        for cell in CELLS:
            value = analysis["fault_cell_summaries"][f"{instance}/{cell}"]
            fault_lines.append(f"| {instance} | {cell} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} |")
    _write_text(report_dir / "fault-table.md", "\n".join(fault_lines))
    control_lines = ["# Complete control table", "", "| Control instance | Cell | False positives /2 |", "|---|---|---:|"]
    for instance in INSTANCES[:2]:
        for cell in CELLS:
            value = analysis["control_cell_summaries"][f"{instance}/{cell}"]
            control_lines.append(f"| {instance} | {cell} | {_rate(value['control_false_positives'])} |")
    _write_text(report_dir / "control-table.md", "\n".join(control_lines))
    operation_lines = ["# Complete operation table", "", "| Trial | Cell | Group | Artifact | Mode | Bytes | Truth group | Truth artifact | Answer changed | Valid request |", "|---|---|---|---|---|---:|---|---|---|---|"]
    token_lines = ["# Complete token table", "", "| Trial | Cell | Calls | Input | Cached input | Output | Derived total |", "|---|---|---:|---:|---:|---:|---:|"]
    trial_lines = ["# Complete review table", "", "| Position | Trial | Instance | Cell | Rep | Detected | Suspect job | Suspect function | Calls |", "|---:|---|---|---|---:|---|---|---|---:|"]
    for review in sorted(reviews, key=lambda value: value["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        group, artifact = review.get("selected_group") or {}, review.get("selected_artifact") or {}
        usage = _actual_usage(review["usage"])
        operation_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {artifact.get('inspection', '')} | {artifact.get('artifact_bytes_returned', 0)} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} | {review['answer_changed']} | {not review['operation_diagnostics']} |")
        token_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {len(review['call_records'])} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['input_tokens'] + usage['output_tokens']} |")
        trial_lines.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |")
    _write_text(report_dir / "operation-table.md", "\n".join(operation_lines))
    _write_text(report_dir / "token-table.md", "\n".join(token_lines))
    _write_text(report_dir / "review-table.md", "\n".join(trial_lines))
    leakage = _json(target / "qualification/reviewer-leakage-audit.json")
    leakage_lines = ["# Complete leakage table", "", "| Instance | Cell | Common text SHA-256 | Non-source audit SHA-256 | Hits | Passed |", "|---|---|---|---|---|---|"]
    for row in leakage["rows"]:
        leakage_lines.append(f"| {row['opaque_instance_id']} | {row['cell_id']} | {row['common_text_sha256']} | {row['audited_non_source_sha256']} | {len(row['prohibited_hits'])} | {row['passed']} |")
    _write_text(report_dir / "leakage-table.md", "\n".join(leakage_lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    aggregate = _json(target / "analysis/summary.json")["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PD Attempt 048 pilot results", "",
        "Status: `completed_pilot_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "",
        "- Five instances and 20 fresh native Etiq job captures",
        f"- 30 packages; 60 terminal reviews; {aggregate['provider_calls']} inference-bearing calls; zero repairs", "",
        "Exploratory outcomes", "",
        f"- Detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; derived total {aggregate['total_tokens']}", "",
        "Attempts 042-047 and all protected provider, Etiq-worker, sandbox and process-isolation surfaces remained unchanged. The full replication was not started.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PD_attempt_048_results_to_overseer.email.md", "\n".join(lines))


def execute_lifecycle(repo_root: Path, target: Path) -> Path:
    repo_root, target = repo_root.resolve(), target.resolve()
    verified = verify_frozen_attempt(repo_root, target)
    create_live_consumption(repo_root, target)
    prepared = prepare_attempt(repo_root, target)
    packages = {record["controller_condition"]["branch_id"]: record for record in _package_records(target)}
    trials = _json(target / "review-design.json")["review_trials"]
    relevance = _json(target / "qualification/adaptive-fault-relevance.json")["faults"]
    reviews = []
    for trial in trials:
        path = target / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = _json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record["controller_trial"] != trial or record["status"] != "complete":
                raise ValueError("invalid partial review record")
        else:
            instance = trial["opaque_instance_id"]
            package_record = packages[trial["branch_id"]]
            session = run_review_session(
                repo_root, target, prepared["catalogues"][instance], prepared["reviewer_nodes"][instance],
                prepared["disclosures"][instance], prepared["indexes"][instance], package_record, trial["trial_id"],
            )
            pre, final = session["pre_validation"], session["final_validation"]
            outcome = score_response(prepared["instances"][instance], final)
            truth = relevance.get(instance, {})
            group = session["selected_group"] or {}
            artifact = session["selected_artifact"] or {}
            record = {
                "schema_version": "n27pd-review-record-1", "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "initial_receipt": deepcopy(pre["receipt"]), "terminal_receipt": deepcopy(final["receipt"]),
                "pre_fault_detected": pre["fault_detected"], "pre_suspect_job": pre["suspect_job"],
                "pre_suspect_function": pre["normalized_suspect_function"],
                "suspect_job": final["suspect_job"], "suspect_function": final["normalized_suspect_function"],
                "suspect_function_visible": final["suspect_function_visible"],
                "parsed_evidence_refs": deepcopy(final["parsed_evidence_refs"]),
                "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]), **outcome,
                "operation_events": session["operation_events"], "operation_diagnostics": session["operation_diagnostics"],
                "selected_group": session["selected_group"], "selected_artifact": session["selected_artifact"],
                "selected_group_contained_truth_state": bool(group and group.get("execution_group_id") == truth.get("model_selectable_execution_group_id")),
                "selected_artifact_was_truth_state": bool(artifact and artifact.get("artifact_ref") == truth.get("artifact_ref")),
                "answer_changed": session["answer_changed"],
                "completed_expansions": session["completed_expansions"],
                "completed_artifact_inspections": session["completed_artifact_inspections"],
                "completed_reconsiderations": session["completed_reconsiderations"],
                "call_records": session["call_records"], "usage": session["usage"], "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews.append(record)
        print(f"N27PD review {len(reviews)}/60 complete: {trial['cell_id']}", flush=True)
    counts = reconstruct_counts(reviews)
    if counts["reviews"] != 60 or counts["repairs"] != 0 or counts["logical_provider_calls"] > 120:
        raise RuntimeError(f"terminal review/call counts invalid: {counts}")
    expected_actual = 120 - sum(2 if diagnostic["stage"] == "group" else 1 for review in reviews for diagnostic in review["operation_diagnostics"])
    if counts["logical_provider_calls"] != expected_actual:
        raise RuntimeError("invalid-operation no-extra-call reconciliation failed")
    call_ids = [call_id for review in reviews for call in review["call_records"] for call_id in call["call_ids"]]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("duplicate provider call ID")
    for call_id in call_ids:
        verify_record(target / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = _json(write_analysis(target, reviews))
    freeze = _json(target / "experiment-freeze.json")
    replay = {
        "schema_version": "n27pd-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(review["review_sha256"] for review in reviews),
        "observed_counts": counts, "planned_inference_calls": 120,
        "all_record_hashes_recomputed": True, "duplicate_provider_call_ids": False,
        "frozen_trees_unchanged": all(ce.sha256(ce._tree_hashes(target / folder)) == expected for folder, expected in freeze["tree_hashes"].items()),
        "provider_receipts_preserved": all(review["initial_receipt"] and review["terminal_receipt"] for review in reviews),
        "invalid_operations_received_no_extra_call": True, "repair_count": 0,
        "full_replication_started": False,
    }
    if not replay["frozen_trees_unchanged"] or not replay["provider_receipts_preserved"]:
        raise RuntimeError("replay reconciliation failed")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(target / "replay.json", replay)
    terminal = {
        "schema_version": "n27pd-terminal-1", "status": "completed_pilot_and_analysis",
        "instance_count": 5, "fresh_job_capture_count": 20, "package_count": 30,
        "review_count": 60, "planned_provider_calls": 120,
        "actual_provider_calls": counts["logical_provider_calls"],
        "rejected_operation_count": counts["rejected_operations"], "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"],
        "actual_token_report_sha256": _json(target / "analysis/actual-token-report.json")["report_sha256"],
        "replay_sha256": replay["replay_sha256"], "full_replication_started": False,
    }
    terminal["terminal_sha256"] = ce.sha256(terminal)
    path = target / "terminal-state.json"
    ce._write_immutable(path, terminal)
    _write_reports(repo_root, target, reviews)
    _write_handoff(repo_root, target)
    return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        record = {
            "schema_version": "n27pd-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27pd_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
            "completed_review_records": len(list((target / "reviews").glob("*.json"))),
            "completed_repair_records": 0,
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
        print(f"N27PD experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


_configure_reuse()


if __name__ == "__main__":
    raise SystemExit(main())
