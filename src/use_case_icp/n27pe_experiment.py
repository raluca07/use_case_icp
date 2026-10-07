"""N27PE control-validity-corrected pilot (Attempt 049)."""

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
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from . import n25_experiment as n25
from . import n27p_experiment as n27p
from . import n27pa_experiment as n27pa
from . import n27pb_experiment as pb
from . import n27pd_experiment as prior
from .fault_preflight_v2 import validate_strict_provider_schema
from .n05_program import _pipeline_payload
from .n05_runner import stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-049")
ATTEMPT_048 = Path("outputs/fault-experiments-v2-2-n10/attempt-048")
TASK = Path("instructions_between_agent_types/developer/current/N27PE_control_validity_correction_and_complete_pilot.email.md")
TASK_SHA256 = "sha256:18d34f605666544816da92abeadc39eecd682b1bd08055f992806fb9017fe2a5"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PE_control_validity_correction_and_complete_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:5d478fa2e6f99e8dd322788a23b28535594f88147ff7650f293aa8d584cdec95"
JOB1_SOURCE = Path("src/use_case_icp/n27pe_market_evidence.py")
JOB2_SOURCE = Path("src/use_case_icp/n27pd_opportunity_priority.py")
JOB3_SOURCE = Path("src/use_case_icp/n27pe_campaign_allocation.py")
JOB4_SOURCE = Path("src/use_case_icp/n27pe_activation_schedule.py")
PROMPT = Path("prompts/v2_2/n27pe_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n27pe_final.schema.json")
GROUP_SCHEMA = Path("schemas/v2_2/n27pe_choose_group.schema.json")
ARTIFACT_SCHEMA = Path("schemas/v2_2/n27pe_choose_artifact.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n27pe_reconsider.schema.json")
ORACLE_FREEZE = Path("qualification/hidden-oracle-freeze.json")
CALIBRATION = "calibration-clean-01"
SANDBOX_GATE = pb.SANDBOX_GATE
SANDBOX_GATE_SHA256 = pb.SANDBOX_GATE_SHA256

JOB_ORDER = n25.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
INSTANCES = (
    "case-cobalt-field",
    "case-ivory-ridge",
    "case-amber-ford",
    "case-sienna-gate",
    "case-teal-meadow",
)
TRUTH = {
    INSTANCES[0]: None,
    INSTANCES[1]: None,
    INSTANCES[2]: "filter_applicable_evidence",
    INSTANCES[3]: "normalize_source_observations",
    INSTANCES[4]: "assemble_opportunity_evidence",
}
MATCHED_CLEAN = {instance: INSTANCES[0] for instance in INSTANCES[2:]}
MUTATIONS = {
    INSTANCES[2]: ('dated_df["_effective_time"].le(as_of)', 'dated_df["_ingested_time"].le(as_of)'),
    INSTANCES[3]: ('["opportunity_id", "source_id", "effective_date"]', '["opportunity_id", "source_id", "valid_until"]'),
    INSTANCES[4]: (
        'scoped_df = per_source_df.drop_duplicates(\n        ["opportunity_id", "source_id"], keep="first"',
        'scoped_df = per_source_df.drop_duplicates(\n        ["source_id"], keep="first"',
    ),
}
CELLS = prior.CELLS
MODE_NAMES = prior.MODE_NAMES
CALLS_BY_MODE = prior.CALLS_BY_MODE
BUSINESS_BRIEF = (
    "Review a four-job marketing workflow that turns market evidence into a campaign activation schedule. "
    "Decide whether the observed execution contains a behaviorally significant processing fault. The workflow "
    "should base its plan on applicable market evidence, respect the supplied selection, budget and scheduling "
    "policies, and retain auditable attribution while evidence is aggregated into campaigns. Begin at Job 4 and "
    "identify the earliest responsible job and exact function only when the available evidence supports that conclusion."
)
INTERFACE_DESCRIPTION = {
    "market_observations": {
        "effective_date": "date on which the evidence becomes effective",
        "ingested_at": "date on which the workflow records the evidence",
        "valid_until": "last date in the evidence validity window",
        "contribution_score": "evidence contribution points",
        "estimated_revenue": "estimated revenue in currency units",
    },
    "priority_units": {
        "contribution_component": "priority points use one tenth of each contribution point",
        "margin_component": "one priority point represents 10,000 currency units of estimated margin",
    },
    "expected_impact": "expected conversions derived per 10,000 audience members using the supplied channel rate",
    "contribution_audit": "the workflow audit record passed from Job 3 to Job 4",
    "attribution_manifest": "binds the final activation plan to the exact logical contribution audit hash and record count",
    "activation_policy.max_windows_per_campaign": "supplied maximum number of activation windows for each campaign",
}
ATTEMPT_048_HASHES = {
    "terminal-state.json": "sha256:a1b47f149bdebdbfb29ae51af0b8b1c0fbd89af006edabb6f6e876b97f45893d",
    "experiment-freeze.json": "sha256:d4344df13a2b8ec119437e916f48f8f6b7d768baecf620b3b323ceb3b53b19fe",
    "replay.json": "sha256:78358694a72feee66f6bc514a5bca2f83a64e0dcdf359d0cceb64ada7a4a07a3",
    "analysis/summary.json": "sha256:6396e0d41f69f0a3b0a17141075a8a687d0deffe6d3584817372d2b7bd18805b",
}
PROTECTED_HASHES = {
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
    "src/use_case_icp/n27pd_opportunity_priority.py": "sha256:cd802d710cefab6083e68361508ef2efa35d52f878d354cd663a07c7fa4c0907",
}


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    prior._write_text(path, value)


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PE authority changed: {relative}")
    for relative, expected in PROTECTED_HASHES.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"protected implementation changed: {relative}")
    for relative, expected in ATTEMPT_048_HASHES.items():
        if ce.sha256((repo_root / ATTEMPT_048 / relative).read_bytes()) != expected:
            raise ValueError(f"Attempt 048 preservation binding changed: {relative}")
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


SEGMENTS = ("enterprise", "growth", "public", "small_business")
CHANNEL_BY_SEGMENT = {"enterprise": "email", "growth": "social", "public": "search", "small_business": "email"}


def _fixture(prefix: str, value_offset: float) -> dict[str, Any]:
    opportunity_ids = [f"{prefix}-op-{index:02d}" for index in range(1, 14)]
    campaign_ids = {segment: f"{prefix}-campaign-{index:02d}" for index, segment in enumerate(SEGMENTS, 1)}
    observations = []
    for index, opportunity_id in enumerate(opportunity_ids):
        segment = SEGMENTS[index % len(SEGMENTS)]
        values = (4.35 + value_offset + (index % 3) * 0.13, 3.75 + value_offset, 2.55 + value_offset)
        for part, contribution in enumerate(values, 1):
            observations.append({
                "contribution_id": f"{prefix}-contribution-{index + 1:02d}-{part}",
                "opportunity_id": opportunity_id,
                "segment": segment,
                "campaign_id": campaign_ids[segment],
                "channel_hint": CHANNEL_BY_SEGMENT[segment],
                "source_id": f"{prefix}-source-{index + 1:02d}-{part}",
                "effective_date": f"2026-08-{3 + ((index + part) % 20):02d}",
                "ingested_at": f"2026-08-{5 + ((index + part) % 20):02d}",
                "valid_until": "2026-10-15",
                "contribution_score": round(contribution, 3),
                "estimated_revenue": 83000 + index * 4100 + int(value_offset * 1000),
            })
    # F1 stimulus: recorded before the decision but not yet effective; admitting it crosses one supplied threshold.
    observations[2].update({
        "effective_date": "2026-09-10", "ingested_at": "2026-08-20",
        "contribution_score": round(1.65 + value_offset, 3),
    })
    # F2 stimulus: the later effective observation is stronger although the older row has the longer validity horizon.
    observations[3].update({
        "effective_date": "2026-07-01", "ingested_at": "2026-07-03",
        "valid_until": "2026-12-31", "contribution_score": round(2.05 + value_offset, 3),
    })
    observations.append({
        **observations[3],
        "contribution_id": f"{prefix}-contribution-02-new",
        "effective_date": "2026-08-25", "ingested_at": "2026-08-27",
        "valid_until": "2026-10-01", "contribution_score": round(5.85 + value_offset, 3),
    })
    # F3 stimulus: one legitimate source is reused once at another opportunity; identifiers remain unambiguous.
    observations[8]["source_id"] = observations[4]["source_id"]
    coverage = [
        {"segment": segment, "coverage_tier": tier, "coverage_multiplier": multiplier}
        for segment, tier, multiplier in zip(SEGMENTS, ("strong", "strong", "moderate", "moderate"), (1.15, 1.1, 1.05, 1.0))
    ]
    commercial = [
        {"opportunity_id": opportunity_id, "margin_rate": round(0.31 + (index % 4) * 0.025, 3)}
        for index, opportunity_id in enumerate(opportunity_ids)
    ]
    audience = [{"segment": segment, "audience_size": size} for segment, size in zip(SEGMENTS, (52000, 65000, 55000, 36000))]
    economics = [
        {"channel": "email", "conversion_rate": 0.032},
        {"channel": "social", "conversion_rate": 0.025},
        {"channel": "search", "conversion_rate": 0.029},
    ]
    calendar = [
        {"channel": channel, "window_id": f"{channel}-w{number}", "window_start": f"2026-10-{number * 7:02d}"}
        for channel in ("email", "social", "search") for number in (1, 2, 3)
    ]
    capacity = [{"channel": row["channel"], "window_id": row["window_id"], "available_slots": 2} for row in calendar]
    return {
        "scenario_id": f"{prefix}-market-cycle",
        "market_observations": observations,
        "selection_policy": {
            "as_of_date": "2026-09-01",
            "segment_minimum_scores": {
                "enterprise": 9.2 + value_offset * 2,
                "growth": 8.0 + value_offset * 2,
                "public": 8.0 + value_offset * 2,
                "small_business": 8.8 + value_offset * 2,
            },
            "minimum_distinct_sources": 2,
            "reporting_precision": 2,
        },
        "capability_coverage": coverage,
        "commercial_context": commercial,
        "audience_economics": audience,
        "channel_economics": economics,
        "budget_policy": {
            "total_budget": 80000.0,
            "base_campaign_budget": 5000.0,
            "impact_budget_multiplier": 1000.0,
            "per_channel_caps": {"email": 42000.0, "social": 24000.0, "search": 24000.0},
        },
        "activation_calendar": calendar,
        "channel_capacity": capacity,
        "activation_policy": {"max_windows_per_campaign": 2},
    }


def input_for(instance: str) -> dict[str, Any]:
    if instance == INSTANCES[1]:
        return deepcopy(_fixture("northstar", 0.37))
    if instance == CALIBRATION:
        return deepcopy(_fixture("quartz", 0.71))
    return deepcopy(_fixture("lumen", 0.0))


def _hidden_oracle(root: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Independent exact oracle; never included in reviewer material."""
    policy = root["selection_policy"]
    applicable = [
        deepcopy(row) for row in root["market_observations"]
        if row["effective_date"] <= policy["as_of_date"] <= row["valid_until"]
    ]
    per_source: dict[tuple[str, str], dict[str, Any]] = {}
    for row in applicable:
        key = (row["opportunity_id"], row["source_id"])
        if key not in per_source or row["effective_date"] > per_source[key]["effective_date"]:
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
                "opportunity_id": opportunity,
                "segment": segment,
                "campaign_id": campaign,
                "channel_hint": channel,
                "full_precision_score": full,
                "reported_score": round(full, int(policy["reporting_precision"])),
                "evidence_source_count": len({row["source_id"] for row in rows}),
                "estimated_revenue": max(int(row["estimated_revenue"]) for row in rows),
            })
    opportunities.sort(key=lambda row: row["opportunity_id"])
    eligible = {row["opportunity_id"] for row in opportunities}
    attribution = [{
        "contribution_id": row["contribution_id"],
        "opportunity_id": row["opportunity_id"],
        "source_id": row["source_id"],
        "contribution_score": row["contribution_score"],
        "effective_date": row["effective_date"],
        "segment": row["segment"],
        "campaign_id": row["campaign_id"],
    } for row in normalized if row["opportunity_id"] in eligible]
    attribution.sort(key=lambda row: (row["opportunity_id"], row["source_id"], row["contribution_id"]))
    job1 = {
        "opportunities": opportunities,
        "evidence_attribution": attribution,
        "metadata": {
            "applicable_observation_count": len(applicable),
            "per_source_observation_count": len(normalized),
            "qualified_opportunity_count": len(opportunities),
            "attribution_count": len(attribution),
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
        "priority_portfolio": portfolio,
        "evidence_attribution": attribution,
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
    audit = sorted(({
        "contribution_id": row["contribution_id"], "opportunity_id": row["opportunity_id"],
        "source_id": row["source_id"], "contribution_score": row["contribution_score"],
        "effective_date": row["effective_date"], "segment": row["segment"],
        "campaign_id": campaign_by_opportunity[row["opportunity_id"]],
    } for row in attribution), key=lambda row: (row["campaign_id"], row["opportunity_id"], row["source_id"], row["contribution_id"]))
    job3 = {
        "campaign_allocations": allocations,
        "contribution_audit": audit,
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
            "activation_id": f"activation-{len(scheduled) + 1:02d}",
            "campaign_id": allocation["campaign_id"], "segment": allocation["segment"],
            "channel": allocation["channel"], "window_id": slot["window_id"], "window_start": slot["window_start"],
            "scheduled_budget": round(allocation["allocated_budget"] / count, 2),
            "expected_conversions": round(allocation["expected_impact"] / count, 4),
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
            "activation_actions": scheduled,
            "window_forecast": window_forecast,
            "aggregate_forecast": {
                "scheduled_budget": round(sum(row["scheduled_budget"] for row in scheduled), 2),
                "expected_conversions": round(sum(row["expected_conversions"] for row in scheduled), 4),
                "activation_count": len(scheduled),
            },
            "attribution_manifest": {"logical_sha256": ce.sha256(audit), "record_count": len(audit)},
        },
        "metadata": {
            "campaign_count": len({row["campaign_id"] for row in allocations}),
            "activation_count": len(scheduled), "window_count": len({row["window_id"] for row in scheduled}),
            "consumed_handoffs": ["campaign_allocations", "contribution_audit", "metadata"],
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
        "operator": "single_ast_site_substitution",
        "qualified_function_name": truth,
        "job_id": JOB1,
        "original_snippet": old,
        "mutant_snippet": new,
        "original_span": {"start_line": line, "end_line": line},
        "candidate_count": 1,
        "exactly_one_source_site_changed": True,
        "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return mutated, record


def _pipeline(repo_root: Path, job_id: str, job1_source: str) -> GeneratedPipeline:
    paths = {
        JOB1: ("generated/protocol_2_2/n27pe_market_evidence.py", job1_source),
        JOB2: ("generated/protocol_2_2/n27pd_opportunity_priority.py", (repo_root / JOB2_SOURCE).read_text()),
        JOB3: ("generated/protocol_2_2/n27pe_campaign_allocation.py", (repo_root / JOB3_SOURCE).read_text()),
        JOB4: ("generated/protocol_2_2/n27pe_activation_schedule.py", (repo_root / JOB4_SOURCE).read_text()),
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
            ("aggregate_campaign_candidates", "Transform opportunities and attribution into campaign candidates and a complete contribution audit.", ["priority portfolio", "evidence attribution"], ["campaign candidates", "contribution audit"]),
            ("join_campaign_economics", "Transform campaign candidates and market economics into scored campaigns.", ["campaign candidates", "audience economics", "channel economics"], ["scored campaigns"]),
            ("allocate_campaign_budget", "Transform scored campaigns and a budget policy into campaign allocations.", ["scored campaigns", "budget policy"], ["campaign allocations"]),
        ),
        JOB4: (
            ("join_calendar_capacity", "Transform campaign allocations and scheduling context into feasible windows.", ["campaign allocations", "activation calendar", "channel capacity"], ["feasible windows"]),
            ("assign_activation_windows", "Transform feasible windows under the supplied activation policy into scheduled activations.", ["feasible windows", "activation policy"], ["scheduled activations"]),
            ("aggregate_activation_forecast", "Transform scheduled activations and the contribution audit into forecasts and an attribution manifest.", ["scheduled activations", "contribution audit"], ["window forecast", "aggregate forecast", "attribution manifest"]),
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


def _job_input(job_id: str, prior_output: Mapping[str, Any] | None, root: Mapping[str, Any]) -> dict[str, Any]:
    if job_id == JOB1:
        return {key: deepcopy(root[key]) for key in ("scenario_id", "market_observations", "selection_policy")}
    if job_id == JOB2:
        return {
            "opportunities": deepcopy(prior_output["opportunities"]),
            "evidence_attribution": deepcopy(prior_output["evidence_attribution"]),
            "metadata": deepcopy(prior_output["metadata"]),
            "capability_coverage": deepcopy(root["capability_coverage"]),
            "commercial_context": deepcopy(root["commercial_context"]),
        }
    if job_id == JOB3:
        return {
            "priority_portfolio": deepcopy(prior_output["priority_portfolio"]),
            "evidence_attribution": deepcopy(prior_output["evidence_attribution"]),
            "metadata": deepcopy(prior_output["metadata"]),
            "audience_economics": deepcopy(root["audience_economics"]),
            "channel_economics": deepcopy(root["channel_economics"]),
            "budget_policy": deepcopy(root["budget_policy"]),
        }
    return {
        "campaign_allocations": deepcopy(prior_output["campaign_allocations"]),
        "contribution_audit": deepcopy(prior_output["contribution_audit"]),
        "metadata": deepcopy(prior_output["metadata"]),
        "activation_calendar": deepcopy(root["activation_calendar"]),
        "channel_capacity": deepcopy(root["channel_capacity"]),
        "activation_policy": deepcopy(root["activation_policy"]),
    }


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
        fields = {"contribution_id", "opportunity_id", "source_id", "contribution_score", "effective_date", "segment", "campaign_id"}
        if not output["campaign_allocations"] or len(output["campaign_allocations"]) > 5:
            raise ValueError("Job 3 did not perform the required many-to-few reduction")
        if any(set(row) != fields for row in output["contribution_audit"]):
            raise ValueError("Job 3 contribution audit is incomplete")
    if job_id == JOB4:
        actions = output["activation_plan"]["activation_actions"]
        manifest = output["activation_plan"]["attribution_manifest"]
        if not actions or manifest != {"logical_sha256": ce.sha256(runtime_input["contribution_audit"]), "record_count": len(runtime_input["contribution_audit"])}:
            raise ValueError("Job 4 audit manifest is invalid")
        maximum = int(runtime_input["activation_policy"]["max_windows_per_campaign"])
        if any(sum(item["campaign_id"] == row["campaign_id"] for item in actions) > maximum for row in actions):
            raise ValueError("Job 4 ignored activation policy")


def _run_pipeline_sources(repo_root: Path, root: Mapping[str, Any], job1_source: str | None = None) -> dict[str, Any]:
    outputs = {}
    prior_output = None
    sources = (job1_source, None, None, None)
    paths = (JOB1_SOURCE, JOB2_SOURCE, JOB3_SOURCE, JOB4_SOURCE)
    with tempfile.TemporaryDirectory(prefix="n27pe-qualification-") as folder:
        for index, job_id in enumerate(JOB_ORDER):
            executable = repo_root / paths[index]
            if sources[index] is not None:
                executable = Path(folder) / "job1.py"
                executable.write_text(str(sources[index]))
            runtime_input = _job_input(job_id, prior_output, root)
            result = subprocess.run(
                [sys.executable, str(executable)], input=json.dumps(runtime_input), text=True,
                capture_output=True, check=False, cwd=repo_root,
            )
            if result.returncode or result.stderr:
                raise ValueError(f"qualification execution failed for {job_id}: {result.stderr}")
            prior_output = json.loads(result.stdout)
            _validate_business_output(job_id, prior_output, runtime_input)
            outputs[job_id] = prior_output
    return outputs


def _replace_identifiers(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_identifiers(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_identifiers(item, replacements) for item in value]
    return replacements.get(value, value) if isinstance(value, str) else value


def _control_invariants(repo_root: Path, instance: str) -> dict[str, Any]:
    root = input_for(instance)
    serialized = ce.canonical_json(root).decode()
    if "partner_opportunity_id" in serialized:
        raise ValueError("removed partner identifier remains in input")
    as_of = root["selection_policy"]["as_of_date"]
    if any(row["effective_date"] == as_of or row["valid_until"] == as_of for row in root["market_observations"]):
        raise ValueError("control contains an ambiguous validity boundary")
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
        "contribution_id": f"{instance}-inapplicable", "effective_date": "2027-01-01",
        "ingested_at": "2027-01-02", "valid_until": "2027-02-01",
    })
    if _run_pipeline_sources(repo_root, inapplicable) != clean:
        raise ValueError(f"inapplicable-row invariance failed: {instance}")
    duplicate = deepcopy(root)
    duplicate["market_observations"].append(deepcopy(duplicate["market_observations"][5]))
    duplicate_output = _run_pipeline_sources(repo_root, duplicate)
    duplicate_job1 = deepcopy(duplicate_output[JOB1])
    duplicate_job1["metadata"]["applicable_observation_count"] = clean[JOB1]["metadata"]["applicable_observation_count"]
    if duplicate_job1 != clean[JOB1] or any(duplicate_output[job] != clean[job] for job in (JOB2, JOB3, JOB4)):
        raise ValueError(f"identical-repeat invariance failed: {instance}")
    opportunity_ids = sorted({row["opportunity_id"] for row in root["market_observations"]})
    replacements = {value: f"renamed-op-{index:02d}" for index, value in enumerate(opportunity_ids, 1)}
    renamed = _replace_identifiers(root, replacements)
    renamed_output = _run_pipeline_sources(repo_root, renamed)
    expected_renamed = _replace_identifiers(clean, replacements)
    renamed_audit = renamed_output[JOB3]["contribution_audit"]
    expected_renamed[JOB4]["activation_plan"]["attribution_manifest"] = {
        "logical_sha256": ce.sha256(renamed_audit), "record_count": len(renamed_audit)
    }
    if renamed_output != expected_renamed:
        raise ValueError(f"opaque-renaming invariance failed: {instance}")
    allocations = clean[JOB3]["campaign_allocations"]
    total = sum(row["allocated_budget"] for row in allocations)
    per_channel = root["budget_policy"]["per_channel_caps"]
    if total > root["budget_policy"]["total_budget"] or any(sum(row["allocated_budget"] for row in allocations if row["channel"] == channel) > cap for channel, cap in per_channel.items()):
        raise ValueError(f"budget or channel invariant failed: {instance}")
    actions = clean[JOB4]["activation_plan"]["activation_actions"]
    allowed = {(row["channel"], row["window_id"]): row["available_slots"] for row in root["channel_capacity"]}
    if any(sum(item["channel"] == key[0] and item["window_id"] == key[1] for item in actions) > cap for key, cap in allowed.items()):
        raise ValueError(f"schedule capacity failed: {instance}")
    maximum = root["activation_policy"]["max_windows_per_campaign"]
    if any(sum(item["campaign_id"] == row["campaign_id"] for item in actions) > maximum for row in actions):
        raise ValueError(f"activation policy failed: {instance}")
    audit = clean[JOB3]["contribution_audit"]
    expected = [{**row} for row in clean[JOB2]["evidence_attribution"]]
    expected.sort(key=lambda row: (row["campaign_id"], row["opportunity_id"], row["source_id"], row["contribution_id"]))
    if audit != expected or len({row["contribution_id"] for row in audit}) != len(audit):
        raise ValueError(f"complete contribution audit failed: {instance}")
    if clean[JOB4]["activation_plan"]["attribution_manifest"] != {"logical_sha256": ce.sha256(audit), "record_count": len(audit)}:
        raise ValueError(f"audit manifest failed: {instance}")
    return {
        "recomputed_from_source_and_input": True,
        "oracle_exact_at_all_jobs": True,
        "no_conflicting_identifier": True,
        "no_expiry_boundary_case": True,
        "permutation": True,
        "inapplicable_observation": True,
        "identical_repeat": True,
        "opaque_identifier_renaming": True,
        "budget_and_channel_conservation": True,
        "schedule_capacity_and_policy": True,
        "complete_audit_identity": True,
        "job4_manifest_binding": True,
    }


def _configure_base() -> None:
    prior.ATTEMPT = ATTEMPT
    prior.TASK = TASK
    prior.TASK_SHA256 = TASK_SHA256
    prior.AUTHORITY = AUTHORITY
    prior.AUTHORITY_SHA256 = AUTHORITY_SHA256
    prior.JOB1_SOURCE = JOB1_SOURCE
    prior.JOB2_SOURCE = JOB2_SOURCE
    prior.JOB3_SOURCE = JOB3_SOURCE
    prior.JOB4_SOURCE = JOB4_SOURCE
    prior.PROMPT = PROMPT
    prior.FINAL_SCHEMA = FINAL_SCHEMA
    prior.GROUP_SCHEMA = GROUP_SCHEMA
    prior.ARTIFACT_SCHEMA = ARTIFACT_SCHEMA
    prior.RECONSIDER_SCHEMA = RECONSIDER_SCHEMA
    prior.ORACLE_FREEZE = ORACLE_FREEZE
    prior.INSTANCES = INSTANCES
    prior.TRUTH = TRUTH
    prior.MATCHED_CLEAN = MATCHED_CLEAN
    prior.MUTATIONS = MUTATIONS
    prior.BUSINESS_BRIEF = BUSINESS_BRIEF
    prior._verify_authority = _verify_authority
    prior.input_for = input_for
    prior._hidden_oracle = _hidden_oracle
    prior._mutant_source = _mutant_source
    prior._pipeline = _pipeline
    prior._job_input = _job_input
    prior._validate_business_output = _validate_business_output
    prior._run_pipeline_sources = _run_pipeline_sources
    prior._control_invariants = _control_invariants
    functions = {
        JOB1: ("filter_applicable_evidence", "normalize_source_observations", "assemble_opportunity_evidence"),
        JOB2: ("join_commercial_context", "calculate_priority_inputs", "rank_opportunity_portfolio"),
        JOB3: ("aggregate_campaign_candidates", "join_campaign_economics", "allocate_campaign_budget"),
        JOB4: ("join_calendar_capacity", "assign_activation_windows", "aggregate_activation_forecast"),
    }
    n27p.FUNCTIONS = functions
    n27pa.FUNCTIONS = functions
    prior._configure_reuse()


def _capture_instance(repo_root: Path, target: Path, instance: str, job1_source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _configure_base()
    original_instances = prior.INSTANCES
    if instance == CALIBRATION:
        prior.INSTANCES = (CALIBRATION,) + INSTANCES
    try:
        capture, source_bundle = prior._capture_instance(repo_root, target, instance, job1_source)
    finally:
        prior.INSTANCES = original_instances
    job3 = capture["jobs"][JOB3]["output"]["contribution_audit"]
    job4 = capture["jobs"][JOB4]["input"]["contribution_audit"]
    if job3 != job4:
        raise ValueError("Job 3 audit was not passed exactly to Job 4")
    capture["handoffs"].append(n25._handoff("contribution_audit", JOB3, JOB4, job3))
    capture["capture_sha256"] = ce.sha256({key: value for key, value in capture.items() if key != "capture_sha256"})
    return capture, source_bundle


def _catalogue(capture: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    legacy = deepcopy(dict(capture))
    legacy["handoffs"] = [row for row in legacy["handoffs"] if row["artifact_name"] != "contribution_audit"]
    legacy["capture_sha256"] = ce.sha256({key: value for key, value in legacy.items() if key != "capture_sha256"})
    catalogue, crosswalk = n27p._catalogue(legacy)
    catalogue["source_capture_sha256"] = capture["capture_sha256"]
    catalogue["handoffs"] = deepcopy(capture["handoffs"])
    catalogue.pop("catalogue_sha256", None)
    catalogue["catalogue_sha256"] = ce.sha256(catalogue)
    ce.verify_catalogue(catalogue)
    return catalogue, crosswalk


def _connected_handoffs(catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = []
    for original in catalogue["handoffs"]:
        row = deepcopy(original)
        row.update(prior._interface_refs(catalogue, row))
        row["provenance_type"] = "controller_recorded_exact_hash_handoff"
        row["etiq_runtime_edge"] = False
        if row["producer_sha256"] != row["consumer_sha256"]:
            raise ValueError("producer/consumer handoff hash differs")
        values.append(row)
    if len(values) != 9 or len({row["handoff_id"] for row in values}) != 9:
        raise ValueError("Attempt 049 requires nine unique material handoffs")
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


def _hard_fault_qualification(captures: Mapping[str, Mapping[str, Any]], instances: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    outputs = {instance: capture["jobs"][JOB4]["output"] for instance, capture in captures.items()}
    hashes = {instance: ce.sha256(output) for instance, output in outputs.items()}
    if len({hashes[instance] for instance in INSTANCES[2:]}) != 3:
        raise ValueError("fault Job-4 symptoms are not distinct")
    execution = {}
    deltas = {}
    clean_capture = captures[INSTANCES[0]]
    clean_job1 = clean_capture["jobs"][JOB1]["output"]
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
        fault_job1 = captures[fault]["jobs"][JOB1]["output"]
        fault_actions = outputs[fault]["activation_plan"]["activation_actions"]
        clean_actions = outputs[clean]["activation_plan"]["activation_actions"]
        if len(fault_actions) != len(clean_actions) or outputs[fault]["metadata"] != outputs[clean]["metadata"]:
            raise ValueError(f"fault changed Job-4 counts: {fault}")
        clean_campaigns = {row["campaign_id"]: row for row in clean_actions}
        fault_campaigns = {row["campaign_id"]: row for row in fault_actions}
        affected = sorted({campaign for campaign in clean_campaigns if clean_campaigns[campaign] != fault_campaigns.get(campaign)})
        if not 1 <= len(affected) <= 2:
            raise ValueError(f"fault symptom is not limited to one or two campaigns: {fault}/{affected}")
        if fault == INSTANCES[2] and len(fault_job1["opportunities"]) - len(clean_job1["opportunities"]) != 1:
            raise ValueError("F1 did not move exactly one opportunity across its threshold")
        if fault in {INSTANCES[3], INSTANCES[4]} and [row["opportunity_id"] for row in fault_job1["opportunities"]] != [row["opportunity_id"] for row in clean_job1["opportunities"]]:
            raise ValueError(f"{fault} changed the qualified opportunity set")
        if fault == INSTANCES[4] and len(clean_job1["evidence_attribution"]) - len(fault_job1["evidence_attribution"]) != 1:
            raise ValueError("F3 did not change exactly one legitimately shared-source contribution")
        execution[fault] = {"mutated_scope_executed": True, "captured_state_refs": executed[:8]}
        deltas[fault] = {
            "matched_clean_case": clean,
            "clean_job4_sha256": hashes[clean],
            "fault_job4_sha256": hashes[fault],
            "job4_campaign_action_counts_equal": True,
            "affected_campaign_count": len(affected),
            "affected_campaigns_controller_only": affected,
        }
    return {
        "schema_version": "n27pe-hard-fault-qualification-1",
        "status": "passed",
        "clean_controls": 2,
        "one_site_faults": 3,
        "distinct_fault_job4_hashes": True,
        "one_site_executed_mutations": execution,
        "controller_only_deltas": deltas,
        "f1_threshold_crossing_from_timestamp_key_only": True,
        "f2_wrong_temporal_survivor": True,
        "f3_shared_source_scope_only": True,
        "all_faults_preserve_schemas_and_job4_counts": True,
    }


def _load_prepared(target: Path) -> dict[str, Any]:
    _configure_base()
    return prior._load_prepared(target)


def _base_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    _configure_base()
    package = prior._base_package(catalogue, source_bundle)
    package["schema_version"] = "n27pe-review-package-1"
    package["common_interface_description"] = deepcopy(INTERFACE_DESCRIPTION)
    package["workflow_policy_inputs"]["activation_policy"] = deepcopy(catalogue["jobs"][JOB4]["input"]["activation_policy"])
    return package


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], compact: Mapping[str, Any], mode: str) -> dict[str, Any]:
    package = _base_package(catalogue, source_bundle)
    if mode != "P01":
        package["graph_review"] = {
            "framing": "Captured native execution structure and separately labelled exact-hash handoffs may be used in the assessment.",
            "evidence": deepcopy(compact),
        }
    if mode in {"P03", "P05"}:
        package["semantic_declaration_bundle"] = prior._semantic_declarations(catalogue)
    if mode in {"P04", "P05"}:
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {
            "operation": "expand_execution_group_then_artifact_inspection",
            "model_selects_group_artifact_and_mode": True,
            "required_before_terminal": True,
            "maximum_completed_expansions": 1,
            "maximum_completed_inspections": 1,
        }
    elif mode == "P06":
        package["available_operations"] = ["reconsider_same_evidence"]
        package["interaction_contract"] = {"operation": "reconsider_same_evidence", "required_passes": 2, "evidence_bytes_added_each_pass": 0}
    return package


def schedule() -> dict[str, Any]:
    cells = []
    for instance in INSTANCES:
        for mode in CELLS:
            cells.append({
                "opaque_instance_id": instance,
                "cell_id": mode,
                "mode": mode,
                "mode_name": MODE_NAMES[mode],
                "declaration_setting": "B1" if mode in {"P03", "P05"} else "B0",
                "branch_id": f"brn-{ce.sha256(['n27pe', instance, mode])[7:23]}",
            })
    reviews = []
    for repetition in (1, 2):
        order = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for block, instance in enumerate(order):
            values = [value for value in cells if value["opaque_instance_id"] == instance]
            rotation = (block + repetition) % len(values)
            for cell in values[rotation:] + values[:rotation]:
                reviews.append({
                    **cell,
                    "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n27pe', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if len(cells) != 30 or len(reviews) != 60 or sum(CALLS_BY_MODE[row["mode"]] for row in reviews) != 120:
        raise AssertionError("Attempt 049 schedule counts changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _calibration_disposition(target: Path) -> dict[str, Any]:
    corrected = target / "calibration/disposition-round-2.json"
    return _json(corrected if corrected.exists() else target / "calibration/disposition.json")


def _corrected_round_required(target: Path) -> bool:
    path = target / "calibration/disposition.json"
    return path.exists() and _json(path)["status"] == "failed_first_pass"


def _oracle_freeze_path(target: Path) -> Path:
    corrected = target / "qualification/hidden-oracle-freeze-round-2.json"
    return corrected if corrected.exists() else target / ORACLE_FREEZE


def _control_qualification_path(target: Path) -> Path:
    corrected = target / "qualification/clean-controls-round-2.json"
    return corrected if corrected.exists() else target / "qualification/clean-controls.json"


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
            raise RuntimeError("bounded clean calibration did not pass")
        return disposition
    calibration_root = target / "calibration" / ("round-2" if round_number == 2 else "round-1")
    correction = None
    if round_number == 2:
        correction = {
            "schema_version": "n27pe-pre-freeze-correction-1",
            "authority": "single authorized calibration correction round",
            "first_pass_disposition_sha256": first["disposition_sha256"],
            "rationale": "Both clean reviewers reasonably treated post-decision ingestion as unavailable evidence.",
            "scope": "clean/calibration/experimental input fixture ambiguity only",
            "exact_delta": {
                "field": "the F1 stimulus dates",
                "before": {"effective_date": "2026-08-20", "ingested_at": "2026-09-10"},
                "after": {"effective_date": "2026-09-10", "ingested_at": "2026-08-20"},
                "effect": "clean execution excludes clearly future-effective evidence; the one-key F1 mutant admits it",
            },
            "experimental_fault_difficulty_selected_from_responses": False,
            "controller_file_sha256_after_delta": ce.sha256((repo_root / "src/use_case_icp/n27pe_experiment.py").read_bytes()),
        }
        correction["correction_sha256"] = ce.sha256(correction)
        ce._write_immutable(target / "calibration/pre-freeze-correction.json", correction)
    capture, source_bundle = _capture_instance(repo_root, calibration_root, CALIBRATION, clean_source)
    catalogue, crosswalk = _catalogue(capture)
    catalogue["schema_version"] = "n27pe-calibration-native-catalogue-1"
    catalogue["handoffs"] = _connected_handoffs(catalogue)
    catalogue.pop("catalogue_sha256", None)
    catalogue["catalogue_sha256"] = ce.sha256(catalogue)
    compact, index = n27p.build_compact_graph(catalogue, crosswalk)
    reviewer, disclosure, omission = pb._payload_lazy_catalogue(catalogue, CALIBRATION)
    lazy = prior._with_handoffs(pb._lazy_graph(compact, reviewer), catalogue["handoffs"])
    pb._assert_payload_lazy(lazy, disclosure)
    ce._write_immutable(calibration_root / "capture.json", capture)
    ce._write_immutable(calibration_root / "catalogue.json", catalogue)
    ce._write_immutable(calibration_root / "native-crosswalk.json", crosswalk)
    ce._write_immutable(calibration_root / "subtree-index.json", index)
    ce._write_immutable(calibration_root / "artifact-disclosure.json", disclosure)
    ce._write_immutable(calibration_root / "omission-manifest.json", omission)
    results = []
    modes = (("calibration-current", "P01"), ("calibration-compact-semantic", "P03"))
    for position, (name, mode) in enumerate(modes, 1):
        package = build_package(catalogue, source_bundle, lazy, mode)
        condition = {
            "opaque_instance_id": CALIBRATION,
            "cell_id": name,
            "mode": mode,
            "mode_name": name,
            "declaration_setting": "B1" if mode == "P03" else "B0",
            "branch_id": f"cal-{ce.sha256(['n27pe', name])[7:23]}",
        }
        package_record = {
            "schema_version": "n27pe-calibration-package-1",
            "controller_condition": condition,
            "capture_sha256": capture["capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "reviewer_package": package,
        }
        package_record["package_sha256"] = ce.sha256(package_record)
        ce._write_immutable(calibration_root / "packages" / f"{name}.json", package_record)
        session = prior.run_review_session(
            repo_root, calibration_root, catalogue, reviewer, disclosure, index,
            package_record, f"calibration-r{round_number}-{position:02d}",
        )
        validation = session["final_validation"]
        result = {
            "schema_version": "n27pe-calibration-result-1",
            "scenario": CALIBRATION,
            "cell": name,
            "unscored": True,
            "excluded_from_scientific_analysis": True,
            "fault_detected": validation["fault_detected"],
            "receipt": deepcopy(validation["receipt"]),
            "call_records": deepcopy(session["call_records"]),
            "usage": deepcopy(session["usage"]),
        }
        result["result_sha256"] = ce.sha256(result)
        ce._write_immutable(calibration_root / "results" / f"{name}.json", result)
        results.append(result)
    passed = all(not result["fault_detected"] for result in results)
    disposition = {
        "schema_version": "n27pe-calibration-disposition-1",
        "status": "passed" if passed else ("failed_first_pass" if round_number == 1 else "failed_second_pass"),
        "scenario": CALIBRATION,
        "calls": (int(first["calls"]) if first else 0) + sum(len(result["call_records"]) for result in results),
        "authorized_maximum_calls": 4,
        "experimental_analysis_excluded": True,
        "correction_round_used": round_number == 2,
        "pre_freeze_delta": correction,
        "first_pass_disposition_sha256": first["disposition_sha256"] if first else None,
        "results": [{"cell": result["cell"], "fault_detected": result["fault_detected"], "result_sha256": result["result_sha256"]} for result in results],
    }
    disposition["disposition_sha256"] = ce.sha256(disposition)
    ce._write_immutable(disposition_path, disposition)
    if not passed:
        raise RuntimeError("calibration false positive requires a genuine pre-freeze ambiguity review" if round_number == 1 else "second-pass calibration remained false positive")
    return disposition


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_base()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PE is authorized only for Attempt 049")
    authority = _verify_authority(repo_root)
    if len(list((target / "captures").glob("*.json"))) == len(INSTANCES):
        return _load_prepared(target) | {"authority": authority}
    clean_source = (repo_root / JOB1_SOURCE).read_text()
    clean_roots = {instance: input_for(instance) for instance in INSTANCES[:2]}
    corrected_round = _corrected_round_required(target)
    oracle_path = target / ("qualification/hidden-oracle-freeze-round-2.json" if corrected_round else ORACLE_FREEZE.as_posix())
    if not oracle_path.exists():
        oracle_record = {
            "schema_version": "n27pe-hidden-oracle-freeze-1",
            "status": "frozen_before_mutant_construction",
            "controller_only": True,
            "oracle_source": inspect.getsource(_hidden_oracle),
            "oracle_source_sha256": ce.sha256(inspect.getsource(_hidden_oracle).encode()),
            "clean_inputs_sha256": {instance: ce.sha256(value) for instance, value in clean_roots.items()},
            "clean_outputs": {instance: _hidden_oracle(value) for instance, value in clean_roots.items()},
            "mutation_records_existing_at_freeze": 0,
            "authorized_calibration_correction_round": corrected_round,
        }
        oracle_record["oracle_freeze_sha256"] = ce.sha256(oracle_record)
        ce._write_immutable(oracle_path, oracle_record)
    control_path = target / ("qualification/clean-controls-round-2.json" if corrected_round else "qualification/clean-controls.json")
    if not control_path.exists():
        controls = {instance: _control_invariants(repo_root, instance) for instance in (*INSTANCES[:2], CALIBRATION)}
        control_record = {
            "schema_version": "n27pe-clean-control-qualification-1",
            "status": "passed",
            "independent_controls": controls,
            "stored_qualification_booleans_trusted_without_recomputation": False,
            "oracle_frozen_before_mutants": True,
        }
        control_record["qualification_sha256"] = ce.sha256(control_record)
        ce._write_immutable(control_path, control_record)
    _calibration(repo_root, target, clean_source)
    common_path = target / "qualification/scientific-common-material-freeze.json"
    if not common_path.exists():
        common = {
            "schema_version": "n27pe-common-material-freeze-1",
            "status": "frozen_after_calibration_before_experimental_instances",
            "source_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in (JOB1_SOURCE, JOB2_SOURCE, JOB3_SOURCE, JOB4_SOURCE)},
            "business_brief_sha256": ce.sha256(BUSINESS_BRIEF.encode()),
            "interface_description_sha256": ce.sha256(INTERFACE_DESCRIPTION),
            "calibration_disposition_sha256": _calibration_disposition(target)["disposition_sha256"],
        }
        common["freeze_sha256"] = ce.sha256(common)
        ce._write_immutable(common_path, common)
    prepared = {name: {} for name in ("captures", "catalogues", "instances", "source_bundles", "crosswalks", "indexes", "reviewer_nodes", "disclosures", "omissions")}
    topology = {}
    handoff_records = {}
    for position, instance in enumerate(INSTANCES):
        source, mutation = _mutant_source(clean_source, instance)
        capture, source_bundle = _capture_instance(repo_root, target, instance, source)
        catalogue, crosswalk = _catalogue(capture)
        catalogue["schema_version"] = "n27pe-four-job-native-catalogue-1"
        catalogue["handoffs"] = _connected_handoffs(catalogue)
        catalogue.pop("catalogue_sha256", None)
        catalogue["catalogue_sha256"] = ce.sha256(catalogue)
        compact, index = n27p.build_compact_graph(catalogue, crosswalk)
        topology[instance] = n27pa._topology_qualification(catalogue, index)
        if position < 2 and not all(value["passed"] for value in topology[instance].values()):
            raise ValueError("clean native topology failed before faulty captures")
        handoff_records[instance] = _capture_handoff_qualification(capture, catalogue)
        reviewer, disclosure, omission = pb._payload_lazy_catalogue(catalogue, instance)
        lazy_compact = pb._lazy_graph(compact, reviewer)
        pb._assert_payload_lazy(lazy_compact, disclosure)
        instance_record = {
            "schema_version": "n27pe-instance-1",
            "opaque_instance_id": instance,
            "designation": "matched_clean_control" if mutation is None else "upstream_fault",
            "truth_job": None if mutation is None else JOB1,
            "truth_function": TRUTH[instance],
            "mutation": mutation,
            "matched_clean_case": MATCHED_CLEAN.get(instance),
            "capture_sha256": capture["capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "source_sha256": deepcopy(capture["source_sha256"]),
        }
        instance_record["instance_sha256"] = ce.sha256(instance_record)
        records = {
            "captures": capture, "catalogues": catalogue,
            "source_bundles": {"source_bundle": source_bundle}, "crosswalks": crosswalk,
            "indexes": index, "reviewer_nodes": reviewer, "disclosures": disclosure,
            "omissions": omission, "instances": instance_record,
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
                "schema_version": "n27pe-fresh-native-job-capture-1", "instance": instance,
                "job_id": job, "capture_status": "fresh_n27pe_execution",
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
        "schema_version": "n27pe-native-capture-qualification-1", "status": "passed",
        "instances": 5, "fresh_job_executions": 20, "etiq_version": "2.3.0",
        "required_api": 'create_full_lineage_graph(graph_format="json")',
        "clean_topology_validated_before_faulty_instances": True,
        "topology": topology, "handoffs": handoff_records, "handoff_count_per_instance": 9,
        "all_native_objects_edges_clusters_preserved": True,
        "all_handoffs_exact_hash_and_schema_valid": True,
    }
    capture_qualification["qualification_sha256"] = ce.sha256(capture_qualification)
    ce._write_immutable(target / "qualification/native-captures-and-handoffs.json", capture_qualification)
    return prepared | {"authority": authority}


def _package_records(target: Path) -> list[dict[str, Any]]:
    return pb._package_records(target)


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return pb._initial_evidence(package)


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    _configure_base()
    return prior._pairwise_checks(records)


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _configure_base()
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
    prohibited = [
        'dated_df["_effective_time"].le(as_of)', 'dated_df["_ingested_time"].le(as_of)',
        '["opportunity_id", "source_id", "effective_date"]',
        '["opportunity_id", "source_id", "valid_until"]',
        '["source_id"], keep="first"', "wrong survivor", "clean delta", "expected clean", "fault identity",
    ]
    for record in records:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        common = {
            "business_brief": package["business_brief"],
            "common_interface_description": package["common_interface_description"],
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
        hits = [term for term in prohibited if term.lower() in visible]
        if hits or "partner_opportunity_id" in ce.canonical_json(package).decode():
            raise ValueError(f"reviewer-visible non-source leakage or removed identifier: {condition['cell_id']}/{hits}")
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
        "schema_version": "n27pe-reviewer-leakage-audit-1", "status": "passed",
        "source_and_genuine_native_records_excluded_from_sanitization": True,
        "common_non_source_text_byte_identical": True, "rows": rows,
    }


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if len(records) != 30 or len(design["review_trials"]) != 60:
        raise ValueError("Attempt 049 package/review counts changed")
    schemas = validate_schemas(repo_root)
    pairwise = _pairwise_checks(records)
    leakage = _leakage_audit(records)
    maximum = 0
    artifact_maximum = 0
    for record in records:
        package = record["reviewer_package"]
        condition = record["controller_condition"]
        if package["business_brief"] != BUSINESS_BRIEF or package["common_interface_description"] != INTERFACE_DESCRIPTION:
            raise ValueError("common reviewer material changed")
        if len(package["separate_complete_source_bundle"]) != 4:
            raise ValueError("a package does not include all four complete actual sources")
        if condition["mode"] == "P01" and "graph_review" in package:
            raise ValueError("Current received graph evidence")
        if condition["mode"] != "P01":
            graph = package["graph_review"]["evidence"]
            if len(graph["handoffs"]) != 9:
                raise ValueError("connected graph lacks one of nine exact handoffs")
            pb._assert_payload_lazy(graph, prepared["disclosures"][condition["opaque_instance_id"]])
        maximum = max(maximum, n25._token_count(render_request(package)))
    relevance = _json(target / "qualification/adaptive-fault-relevance.json")
    for instance in INSTANCES:
        groups = relevance["inspectable_artifacts_per_selectable_group"][instance]
        if len(groups) != 12 or any(count < 1 for count in groups.values()):
            raise ValueError("a native function group is missing an inspectable artifact")
        for artifact in prepared["disclosures"][instance]["artifacts"].values():
            artifact_maximum = max(artifact_maximum, n25._token_count(artifact["operation_node"]["artifact_content"]))
    if sum(CALLS_BY_MODE[row["mode"]] for row in design["review_trials"]) != 120 or max(maximum, artifact_maximum) >= 100_000:
        raise ValueError("call count or provider context qualification failed")
    return {
        "schema_version": "n27pe-no-model-verification-1", "status": "passed", "model_calls": 0,
        "instances": 5, "fresh_job_executions": 20, "packages": 30, "terminal_reviews": 60,
        "required_follow_up_calls": 60, "planned_provider_calls": 120, "repairs": 0,
        "strict_schema_hashes": schemas, "pairwise_checks": len(pairwise), "leakage_rows": len(leakage["rows"]),
        "maximum_initial_request_tokens": maximum, "maximum_complete_artifact_tokens": artifact_maximum,
        "provider_context_qualification_limit": 100_000,
        "fault_denominator_per_cell": 6, "control_denominator_per_cell": 4,
        "per_fault_denominator": 2, "per_control_denominator": 2,
        "calibration_calls_excluded": _calibration_disposition(target)["calls"],
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_base()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if len(existing) == 30:
        qualification = qualify_packages(repo_root, target, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    relevance = pb.adaptive_relevance(prepared, target)
    relevance["schema_version"] = "n27pe-adaptive-relevance-1"
    relevance.pop("qualification_sha256", None)
    relevance["qualification_sha256"] = ce.sha256(relevance)
    ce._write_immutable(target / "qualification/adaptive-fault-relevance.json", relevance)
    graphs = {}
    for instance in INSTANCES:
        compact = _json(target / "projections" / f"{instance}-compact.json")
        graphs[instance] = prior._with_handoffs(compact, prepared["catalogues"][instance]["handoffs"])
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
            "schema_version": "n27pe-frozen-package-1", "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance]["catalogue_sha256"],
            "disclosure_catalogue_sha256": prepared["disclosures"][instance]["catalogue_sha256"],
            "omission_manifest_sha256": prepared["omissions"][instance]["manifest_sha256"],
            "business_brief_sha256": ce.sha256(BUSINESS_BRIEF.encode()),
            "interface_description_sha256": ce.sha256(INTERFACE_DESCRIPTION),
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        path = target / "packages" / condition["branch_id"] / "reviewer-package.json"
        ce._write_immutable(path, record)
        manifest = {
            "schema_version": "n27pe-controller-manifest-1", "controller_condition": deepcopy(condition),
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
    pairwise = {"schema_version": "n27pe-pairwise-package-differences-1", "rows": _pairwise_checks(records), "all_passed": True}
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {"schema_version": "n27pe-review-design-1", "review_trials": design["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n27pe-repair-design-1", "repair_traces": []})
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27pe_experiment.py"), JOB1_SOURCE, JOB2_SOURCE, JOB3_SOURCE, JOB4_SOURCE,
        PROMPT, FINAL_SCHEMA, GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27pe_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 049 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after experimental reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("focused N27PE tests must pass before freeze")
    calibration = _calibration_disposition(target)
    if calibration["status"] != "passed" or calibration["calls"] not in {2, 4}:
        raise ValueError("bounded clean calibration did not pass")
    freeze = {
        "schema_version": "n27pe-experiment-freeze-1", "attempt": "049",
        "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "attempt_048_hashes": deepcopy(ATTEMPT_048_HASHES),
        "protected_hashes": deepcopy(PROTECTED_HASHES),
        "sandbox_gate_file_sha256": ce.sha256((repo_root / SANDBOX_GATE).read_bytes()),
        "sandbox_bindings": deepcopy(built["prepared"]["authority"]["sandbox"]),
        "calibration_disposition_file_sha256": ce.sha256((target / ("calibration/disposition-round-2.json" if (target / "calibration/disposition-round-2.json").exists() else "calibration/disposition.json")).read_bytes()),
        "calibration_tree_sha256": ce.sha256(ce._tree_hashes(target / "calibration")),
        "common_material_freeze_file_sha256": ce.sha256((target / "qualification/scientific-common-material-freeze.json").read_bytes()),
        "hidden_oracle_file_sha256": ce.sha256(_oracle_freeze_path(target).read_bytes()),
        "clean_control_file_sha256": ce.sha256(_control_qualification_path(target).read_bytes()),
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
        "schema_version": "n27pe-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "one_use_live_authority": True,
        "authorized_experimental_calls": 120, "completed_calibration_calls": _calibration_disposition(target)["calls"], "repairs": 0,
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], stage: str) -> dict[str, Any]:
    _configure_base()
    return pb.validate_response(repo_root, package, response, stage)


def score_response(instance: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    return pb.score_response(instance, validation)


def run_review_session(repo_root: Path, target: Path, catalogue: Mapping[str, Any], reviewer: Mapping[str, Any], disclosure: Mapping[str, Any], index: Mapping[str, Any], package_record: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    _configure_base()
    return prior.run_review_session(repo_root, target, catalogue, reviewer, disclosure, index, package_record, trial_id)


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return pb.reconstruct_counts(reviews)


def _actual_usage(usage: Mapping[str, Any]) -> dict[str, int]:
    return prior._actual_usage(usage)


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    _configure_base()
    return prior._analysis_rows(reviews)


def _ratio(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    return {"numerator": sum(bool(row[key]) for row in rows), "denominator": len(rows)}


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    sensitivity = _ratio(faults, "fault_detected")
    false_positives = _ratio(controls, "false_positive")
    specificity = 1.0 - (false_positives["numerator"] / false_positives["denominator"] if false_positives["denominator"] else 0.0)
    sensitivity_rate = sensitivity["numerator"] / sensitivity["denominator"] if sensitivity["denominator"] else 0.0
    return {
        "reviews": len(rows), "provider_calls": sum(row["provider_calls"] for row in rows),
        "fault_detection": sensitivity,
        "correct_job_attribution": _ratio(faults, "correct_job_attribution"),
        "exact_function_localisation": _ratio(faults, "exact_function_localisation"),
        "control_false_positives": false_positives,
        "balanced_fault_discrimination_accuracy": (sensitivity_rate + specificity) / 2 if faults and controls else None,
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "cached_input_tokens": sum(row["cached_input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "total_tokens": sum(row["total_tokens"] for row in rows),
    }


def _contrast(rows: list[Mapping[str, Any]], name: str, left: str, right: str) -> list[dict[str, Any]]:
    _configure_base()
    return prior._contrast(rows, name, left, right)


def _false_positive_rationale(review: Mapping[str, Any]) -> str:
    if not review["false_positive"]:
        return "not_false_positive"
    job = review.get("suspect_job")
    if job == "job_1":
        return "claimed_upstream_evidence_processing_issue"
    if job == "job_4":
        return "claimed_activation_schedule_issue"
    if job in {"job_2", "job_3"}:
        return "claimed_intermediate_workflow_issue"
    return "fault_claim_without_localisation"


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    reviews = list(reviews)
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
    rationale_rows = [{
        "trial_id": review["controller_trial"]["trial_id"],
        "instance": review["controller_trial"]["opaque_instance_id"],
        "cell_id": review["controller_trial"]["cell_id"],
        "category": _false_positive_rationale(review),
        "explanation": review["terminal_receipt"].get("explanation", ""),
    } for review in reviews if review["false_positive"]]
    rationale_counts = {category: sum(row["category"] == category for row in rationale_rows) for category in sorted({row["category"] for row in rationale_rows})}
    adaptive_fault_trials = [{
        "trial_id": row["trial_id"], "instance": row["instance"], "cell_id": row["cell_id"],
        "selected_true_group": row["selected_group_contained_truth_state"],
        "selected_true_artifact": row["selected_artifact_was_truth_state"],
        "execution_group_id": row["execution_group_id"], "artifact_ref": row["artifact_ref"],
    } for row in rows if row["designation"] == "upstream_fault" and row["cell_id"] in {"P04", "P05"}]
    calibration = _calibration_disposition(target)
    analysis = {
        "schema_version": "n27pe-pilot-analysis-1", "exploratory_not_confirmatory": True,
        "population_level_significance_claimed": False, "full_replication_remains_deferred": True,
        "calibration": {
            "disposition_sha256": calibration["disposition_sha256"], "calls": calibration["calls"],
            "status": calibration["status"], "excluded_from_scientific_results": True,
        },
        "aggregate": aggregate, "cell_summaries": cells,
        "fault_summaries": {instance: _summary([row for row in rows if row["instance"] == instance]) for instance in MATCHED_CLEAN},
        "control_summaries": {instance: _summary([row for row in rows if row["instance"] == instance]) for instance in INSTANCES[:2]},
        "fault_cell_summaries": fault_cells, "control_cell_summaries": control_cells,
        "prespecified_descriptive_contrasts": contrasts,
        "false_positive_rationale_categories": {"counts": rationale_counts, "rows": rationale_rows},
        "adaptive_fault_trial_selection": adaptive_fault_trials,
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
            "The sacrificial calibration is excluded from every scientific denominator and contrast.",
            "The later full ICLR replication was not started.",
        ],
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(target / "analysis/summary.json", analysis)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    _write_text(target / "analysis/all-review-rows.csv", stream.getvalue())
    token_report = {
        "schema_version": "n27pe-actual-token-report-1", "provider_calls": aggregate["provider_calls"],
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
    report_dir = repo_root / "docs/workshops/ICLR/N27PE-control-validity-corrected-pilot"
    findings = [
        "# N27PE control-validity-corrected pilot", "",
        "Attempt 049 completed the authorized corrected five-instance pilot. Attempt 048 remains unchanged and the full replication remains deferred.", "",
        "## Aggregate outcomes", "",
        f"- Fault sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Balanced fault-discrimination accuracy: {aggregate['balanced_fault_discrimination_accuracy']:.4f}",
        f"- Experimental provider calls: {aggregate['provider_calls']}; calibration calls: {analysis['calibration']['calls']} (excluded)",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; derived total {aggregate['total_tokens']}", "",
        "All 20 scientific captures are fresh native Etiq executions. Every connected graph contains nine separately labelled exact-hash handoffs. No repairs were run.", "",
        "## Immutable records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-049/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-049/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-049/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-049/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    cell_lines = ["# Complete cell table", "", "| Cell | Reviews | Fault detection /6 | Job 1 /6 | Exact /6 | Control FP /4 | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
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
    token_lines = ["# Complete token table", "", "| Trial | Cell | Calls | Input | Cached | Output | Total |", "|---|---|---:|---:|---:|---:|---:|"]
    review_lines = ["# Complete review table", "", "| Position | Trial | Instance | Cell | Rep | Detected | Job | Function | Calls |", "|---:|---|---|---|---:|---|---|---|---:|"]
    for review in sorted(reviews, key=lambda value: value["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        group, artifact = review.get("selected_group") or {}, review.get("selected_artifact") or {}
        usage = _actual_usage(review["usage"])
        operation_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {artifact.get('inspection', '')} | {artifact.get('artifact_bytes_returned', 0)} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} |")
        token_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {len(review['call_records'])} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['input_tokens'] + usage['output_tokens']} |")
        review_lines.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |")
    _write_text(report_dir / "operation-table.md", "\n".join(operation_lines))
    _write_text(report_dir / "token-table.md", "\n".join(token_lines))
    _write_text(report_dir / "review-table.md", "\n".join(review_lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PE Attempt 049 corrected pilot results", "",
        "Status: `completed_pilot_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "",
        "- Two unscored calibration calls, excluded from scientific results",
        "- Five instances and 20 fresh native Etiq scientific job captures",
        f"- 30 packages; 60 terminal reviews; {aggregate['provider_calls']} experimental calls; zero repairs", "",
        "Outcomes", "",
        f"- Sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Balanced fault-discrimination accuracy: {aggregate['balanced_fault_discrimination_accuracy']:.4f}", "",
        "Attempt 048 and all protected execution surfaces remained unchanged. The full replication was not started.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PE_attempt_049_results_to_overseer.email.md", "\n".join(lines))


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
                "schema_version": "n27pe-review-record-1", "controller_trial": deepcopy(trial),
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
        print(f"N27PE review {len(reviews)}/60 complete: {trial['cell_id']}", flush=True)
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
        "schema_version": "n27pe-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(review["review_sha256"] for review in reviews),
        "observed_counts": counts, "planned_experimental_inference_calls": 120,
        "calibration_disposition_sha256": _calibration_disposition(target)["disposition_sha256"],
        "calibration_excluded_from_experimental_counts": True,
        "all_record_hashes_recomputed": True, "duplicate_provider_call_ids": False,
        "frozen_trees_unchanged": all(ce.sha256(ce._tree_hashes(target / folder)) == expected for folder, expected in freeze["tree_hashes"].items()),
        "frozen_calibration_unchanged": ce.sha256(ce._tree_hashes(target / "calibration")) == freeze["calibration_tree_sha256"],
        "provider_receipts_preserved": all(review["initial_receipt"] and review["terminal_receipt"] for review in reviews),
        "invalid_operations_received_no_extra_call": True, "repair_count": 0,
        "full_replication_started": False,
    }
    if not replay["frozen_trees_unchanged"] or not replay["frozen_calibration_unchanged"] or not replay["provider_receipts_preserved"]:
        raise RuntimeError("replay reconciliation failed")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(target / "replay.json", replay)
    terminal = {
        "schema_version": "n27pe-terminal-1", "status": "completed_pilot_and_analysis",
        "calibration_call_count": _calibration_disposition(target)["calls"], "calibration_excluded": True,
        "instance_count": 5, "fresh_job_capture_count": 20, "package_count": 30,
        "review_count": 60, "planned_experimental_provider_calls": 120,
        "actual_experimental_provider_calls": counts["logical_provider_calls"],
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
            "schema_version": "n27pe-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27pe_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
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
        print(f"N27PE experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
