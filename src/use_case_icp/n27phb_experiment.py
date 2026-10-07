"""N27PHB corrected full native-Etiq experiment (Attempt 053)."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import random
import subprocess
import sys
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from . import n25_experiment as n25
from . import n27p_experiment as n27p
from . import n27pb_experiment as pb
from .n27phb_hidden_oracle import compute_clean_result
from .fault_preflight_v2 import validate_strict_provider_schema
from .n05_program import _parse_output, _pipeline_payload, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, materialize_opaque_branch, stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline


_PB_RUN_REVIEW = pb.run_review_session
_PB_VALIDATE_RESPONSE = pb.validate_response


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-053")
ATTEMPT_052 = Path("outputs/fault-experiments-v2-2-n10/attempt-052")
TASK = Path("instructions_between_agent_types/developer/current/N27PHB_corrected_full_native_etiq_experiment.email.md")
TASK_SHA256 = "sha256:b9f4e113913dd230e1d693f8bde4c93a776eb6f5b296db1e23a61a9d6ca28c68"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PHB_corrected_full_native_etiq_experiment_authorization.json")
AUTHORITY_SHA256 = "sha256:a7ce3f7a2ab1a1e3a8e4c208b18bc497090569708518c2a247f29b3430520ea5"

JOB1_SOURCE = Path("src/use_case_icp/n27phb_market_evidence.py")
JOB2_SOURCE = Path("src/use_case_icp/n27phb_opportunity_priority.py")
JOB3_SOURCE = Path("src/use_case_icp/n27phb_campaign_allocation.py")
JOB4_SOURCE = Path("src/use_case_icp/n27phb_activation_schedule.py")
ORACLE_SOURCE = Path("src/use_case_icp/n27phb_hidden_oracle.py")
PROMPT = Path("prompts/v2_2/n27phb_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n27phb_final.schema.json")
GROUP_SCHEMA = Path("schemas/v2_2/n27phb_choose_group.schema.json")
ARTIFACT_SCHEMA = Path("schemas/v2_2/n27phb_choose_artifact.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n27phb_reconsider.schema.json")

JOB_ORDER = n25.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
JOB_SOURCES = {JOB1: JOB1_SOURCE, JOB2: JOB2_SOURCE, JOB3: JOB3_SOURCE, JOB4: JOB4_SOURCE}
INSTANCES = (
    "case-amber-fjord", "case-cobalt-meadow", "case-linen-ridge",
    "case-marigold-harbor", "case-pearl-orchard",
    "case-quartz-brook", "case-saffron-cliff",
    "case-teal-prairie", "case-umber-vale",
)
TRUTH = {
    INSTANCES[0]: None, INSTANCES[1]: None, INSTANCES[2]: None,
    INSTANCES[3]: "aggregate_opportunity_evidence", INSTANCES[4]: "aggregate_opportunity_evidence",
    INSTANCES[5]: "reduce_source_repeats", INSTANCES[6]: "reduce_source_repeats",
    INSTANCES[7]: "weight_source_reliability", INSTANCES[8]: "weight_source_reliability",
}
MATCHED_CLEAN = {
    INSTANCES[3]: INSTANCES[0], INSTANCES[5]: INSTANCES[0], INSTANCES[7]: INSTANCES[0],
    INSTANCES[4]: INSTANCES[1], INSTANCES[6]: INSTANCES[1], INSTANCES[8]: INSTANCES[1],
}
MUTATIONS = {
    INSTANCES[3]: ('decision_score = eligibility_df["full_precision_score"]', 'decision_score = eligibility_df["display_score"]'),
    INSTANCES[4]: ('decision_score = eligibility_df["full_precision_score"]', 'decision_score = eligibility_df["display_score"]'),
    INSTANCES[5]: ('applied_basis = configured_basis', 'applied_basis = "recorded_at"'),
    INSTANCES[6]: ('applied_basis = configured_basis', 'applied_basis = "recorded_at"'),
    INSTANCES[7]: ('join_columns = ["source_id", "segment"]', 'join_columns = ["source_id"]'),
    INSTANCES[8]: ('join_columns = ["source_id", "segment"]', 'join_columns = ["source_id"]'),
}
FAULT_MECHANISM = {
    INSTANCES[3]: "F1_rounded_threshold", INSTANCES[4]: "F1_rounded_threshold",
    INSTANCES[5]: "F2_temporal_survivor", INSTANCES[6]: "F2_temporal_survivor",
    INSTANCES[7]: "F3_source_only_join", INSTANCES[8]: "F3_source_only_join",
}
SCHEDULE_SEED = 530914271
CELLS = ("P01", "P02", "P03", "P04", "P05", "P06")
CONTROLLER_MODE = {"P01": "P01", "P02": "P07", "P03": "P08", "P04": "P10", "P05": "P11", "P06": "P12"}
CALLS_BY_CELL = {"P01": 1, "P02": 1, "P03": 1, "P04": 3, "P05": 3, "P06": 3}
SEMANTIC_CELLS = {"P03", "P05"}
GRAPH_CELLS = set(CELLS) - {"P01"}

# Etiq records the fourth Job-1 and Job-4 functions as genuine nested groups:
# each is called by the preceding function rather than by module-level code.
TOP_LEVEL_FUNCTIONS = {
    JOB1: ("select_snapshot_observations", "reduce_source_repeats", "weight_source_reliability"),
    JOB2: ("join_priority_context", "calculate_single_count_priority", "rank_priority_portfolio"),
    JOB3: ("aggregate_campaign_candidates", "score_campaign_candidates", "allocate_campaign_budget"),
    JOB4: ("join_available_windows", "choose_activation_windows", "aggregate_activation_schedule"),
}

ATTEMPT_052_HASHES = {
    "terminal-state.json": "sha256:acd92e43aa84415589661d93756a356cb5588818ab20b7c54e75a2ea098e811b",
    "experiment-freeze.json": "sha256:35864b200796bebf1380c4258bc7fe4b8c2ec9f420f42e8c9a09f4279c91357c",
    "replay.json": "sha256:78761d807b854fe78ecccb8d87c09045c5e1e74096f869d4fddb1b6630ad21f3",
}
PROTECTED_HASHES = {
    "src/use_case_icp/n27pg_experiment.py": "sha256:6c191ba12a50cde145a229fc1f18f700b5384db3a805ba649128f6993009d70e",
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
}
SANDBOX_GATE = pb.SANDBOX_GATE
SANDBOX_GATE_SHA256 = pb.SANDBOX_GATE_SHA256


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, text: str) -> None:
    pb.create_bytes_exclusive(path, text.encode())


def _file_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_token_correction(repo_root: Path) -> dict[str, str]:
    report_dir = repo_root / "docs/workshops/ICLR/N27PHA-fresh-jobs-clean-package-native-etiq-pilot"
    correction_path = report_dir / "token-accounting-correction.json"
    correction = _json(correction_path)
    ce._verified_self_hash(correction, "correction_sha256")
    reviews = [_json(path) for path in sorted((repo_root / ATTEMPT_052 / "reviews").glob("*.json"))]
    totals = {
        "input_tokens": sum(int(row["usage"]["cumulative_actual_input_tokens"]) for row in reviews),
        "cached_input_tokens": sum(int(row["usage"]["cumulative_actual_cached_input_tokens"]) for row in reviews),
        "output_tokens": sum(int(row["usage"]["cumulative_actual_output_tokens"]) for row in reviews),
    }
    totals["input_plus_output_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    expected = {"input_tokens": 3156968, "cached_input_tokens": 678784, "output_tokens": 66143, "input_plus_output_tokens": 3223111}
    if len(reviews) != 30 or totals != expected or correction["totals"] != expected:
        raise ValueError("Attempt 052 token correction does not reproduce authorized totals")
    return {
        "json_file_sha256": _file_sha(correction_path),
        "markdown_file_sha256": _file_sha(report_dir / "token-accounting-correction.md"),
        "logical_sha256": correction["correction_sha256"],
    }


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if _file_sha(repo_root / relative) != expected:
            raise ValueError(f"N27PHB authority changed: {relative}")
    for relative, expected in ATTEMPT_052_HASHES.items():
        if _file_sha(repo_root / ATTEMPT_052 / relative) != expected:
            raise ValueError(f"Attempt 052 preservation binding changed: {relative}")
    if _file_sha(repo_root / "src/use_case_icp/n27pha_experiment.py") != "sha256:2e5a6a724855b01582664c775ac26dce29ad2b156b8ec163e172315149cdafff":
        raise ValueError("Attempt 052 controller changed")
    for relative, expected in PROTECTED_HASHES.items():
        if _file_sha(repo_root / relative) != expected:
            raise ValueError(f"protected execution binding changed: {relative}")
    if _file_sha(repo_root / SANDBOX_GATE) != SANDBOX_GATE_SHA256:
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
        raise ValueError("protected provider or sandbox configuration changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "sandbox": sandbox, "token_correction": _verify_token_correction(repo_root)}


def _observation(prefix, suffix, opportunity, source, segment, campaign, channel, effective, recorded, value, revenue, valid="2026-12-31"):
    return {
        "contribution_id": f"{prefix}-contribution-{suffix}", "opportunity_id": f"{prefix}-{opportunity}",
        "source_id": f"{prefix}-{source}", "segment": segment, "campaign_id": f"{prefix}-{campaign}",
        "channel": channel, "effective_date": effective, "recorded_at": recorded,
        "valid_until": valid, "evidence_value": value, "estimated_revenue": revenue,
    }


def _fixture(prefix: str, variant: str, stressed: bool = False) -> dict[str, Any]:
    values = {
        "a": {"stable": (0.57, 0.39), "threshold": (0.3115, 0.2504), "temporal": (0.51, 0.405, 0.43), "reliability": (0.82, 0.56, 0.91, 0.80, 1.0, 0.86), "revenue": (184000, 97000, 158000)},
        "b": {"stable": (0.53, 0.43), "threshold": (0.301, 0.2647), "temporal": (0.48, 0.405, 0.44), "reliability": (0.84, 0.59, 0.89, 0.78, 1.0, 0.84), "revenue": (191000, 101000, 166000)},
        "c": {"stable": (0.59, 0.37), "threshold": (0.321, 0.2587), "temporal": (0.49, 0.39, 0.435), "reliability": (0.81, 0.58, 0.92, 0.75, 1.0, 0.87), "revenue": (188000, 99000, 162000)},
    }[variant]
    stable, threshold, temporal = values["stable"], values["threshold"], values["temporal"]
    north_shared, south_shared, north_only, threshold_one, threshold_two, repeat = values["reliability"]
    stable_revenue, threshold_revenue, temporal_revenue = values["revenue"]
    observations = [
        _observation(prefix, "stable-shared", "opportunity-stable", "source-shared", "north", "campaign-alpha", "email", "2026-08-20", "2026-08-22T10:00:00", stable[0], stable_revenue),
        _observation(prefix, "stable-north", "opportunity-stable", "source-north", "north", "campaign-alpha", "email", "2026-08-22", "2026-08-23T09:00:00", stable[1], stable_revenue),
        _observation(prefix, "threshold-one", "opportunity-threshold", "source-threshold-one", "north", "campaign-alpha", "email", "2026-09-01", "2026-09-02T08:00:00", threshold[0], threshold_revenue),
        _observation(prefix, "threshold-two", "opportunity-threshold", "source-threshold-two", "north", "campaign-alpha", "email", "2026-09-02", "2026-09-03T08:00:00", threshold[1], threshold_revenue),
        _observation(prefix, "temporal-shared", "opportunity-temporal", "source-shared", "south", "campaign-beta", "social", "2026-08-15", "2026-08-16T08:00:00", temporal[0], temporal_revenue),
        _observation(prefix, "temporal-older", "opportunity-temporal", "source-repeat", "south", "campaign-beta", "social", "2026-08-01", "2026-09-10T09:00:00", temporal[1], temporal_revenue),
        _observation(prefix, "temporal-newer", "opportunity-temporal", "source-repeat", "south", "campaign-beta", "social", "2026-09-01", "2026-09-05T09:00:00", temporal[2], temporal_revenue),
        _observation(prefix, "expired", "opportunity-noise", "source-noise", "north", "campaign-noise", "email", "2026-07-01", "2026-07-02T08:00:00", 0.99, 50000, valid="2026-08-31"),
        _observation(prefix, "future-recorded", "opportunity-noise", "source-noise-two", "south", "campaign-noise", "social", "2026-09-01", "2026-09-20T08:00:00", 0.99, 50000),
    ]
    reliability_values = {
        "source-shared": (north_shared, south_shared),
        "source-north": (north_only, None),
        "source-threshold-one": (threshold_one, None), "source-threshold-two": (threshold_two, None),
        "source-repeat": (None, repeat),
        "source-noise": (0.70, None), "source-noise-two": (None, 0.72),
    }
    source_reliability = []
    for source, values in reliability_values.items():
        for segment, value in zip(("north", "south"), values):
            if value is not None:
                source_reliability.append({"source_id": f"{prefix}-{source}", "segment": segment, "reliability": value})
    return {
        "scenario_label": f"{prefix}-planning",
        "market_observations": list(reversed(observations)) if stressed else observations,
        "source_reliability": source_reliability,
        "repeat_resolution_policy": {"basis": "effective_date"},
        "planning_policy": {
            "as_of_date": "2026-09-15", "display_precision": 2,
            "minimum_sources": 2, "eligibility_thresholds": {"north": 0.50, "south": 0.60},
        },
        "capability_coverage": [
            {"segment": "north", "coverage_multiplier": 1.17 + 0.02 * (variant == "b"), "coverage_tier": "established"},
            {"segment": "south", "coverage_multiplier": 1.06 + 0.03 * (variant == "c"), "coverage_tier": "growing"},
        ],
        "commercial_context": [
            {"opportunity_id": f"{prefix}-opportunity-stable", "margin_rate": 0.29 + 0.02 * (variant == "b")},
            {"opportunity_id": f"{prefix}-opportunity-threshold", "margin_rate": 0.24 + 0.02 * (variant == "c")},
            {"opportunity_id": f"{prefix}-opportunity-temporal", "margin_rate": 0.27 + 0.02 * (variant == "b")},
        ],
        "audience_economics": [
            {"segment": "north", "audience_size": {"a": 12300, "b": 13100, "c": 12700}[variant]},
            {"segment": "south", "audience_size": {"a": 9300, "b": 10100, "c": 9700}[variant]},
        ],
        "channel_economics": [
            {"channel": "email", "conversion_rate": {"a": 0.061, "b": 0.066, "c": 0.063}[variant]},
            {"channel": "social", "conversion_rate": {"a": 0.041, "b": 0.044, "c": 0.042}[variant]},
        ],
        "budget_policy": {
            "total_budget": 30000.0, "base_campaign_budget": 4000.0,
            "impact_budget_multiplier": 900.0,
            "channel_caps": {"email": 18000.0, "social": 15000.0},
        },
        "activation_calendar": [
            {"channel": "email", "window_id": "window-e1", "window_start": "2026-10-05"},
            {"channel": "email", "window_id": "window-e2", "window_start": "2026-10-12"},
            {"channel": "social", "window_id": "window-s1", "window_start": "2026-10-06"},
            {"channel": "social", "window_id": "window-s2", "window_start": "2026-10-13"},
        ],
        "channel_capacity": [
            {"channel": "email", "window_id": "window-e1", "available_slots": 2},
            {"channel": "email", "window_id": "window-e2", "available_slots": 2},
            {"channel": "social", "window_id": "window-s1", "available_slots": 2},
            {"channel": "social", "window_id": "window-s2", "available_slots": 2},
        ],
        "scheduling_policy": {"max_windows_per_campaign": 2, "budget_precision": 2, "impact_precision": 4},
    }


def input_for(instance: str) -> dict[str, Any]:
    if instance not in INSTANCES:
        raise KeyError(instance)
    variants = ("a", "b", "c", "a", "b", "a", "b", "a", "b")
    prefixes = ("amber", "cobalt", "linen", "marigold", "pearl", "quartz", "saffron", "teal", "umber")
    root = _fixture(prefixes[INSTANCES.index(instance)], variants[INSTANCES.index(instance)], instance == INSTANCES[2])
    if instance == INSTANCES[2]:
        root["market_observations"].extend([
            _observation("linen", "noise-expired-two", "opportunity-noise-two", "source-noise-three", "north", "campaign-noise", "email", "2025-02-01", "2025-02-02T00:00:00", 0.88, 61000, valid="2025-06-30"),
            _observation("linen", "noise-future-two", "opportunity-noise-three", "source-noise-four", "south", "campaign-noise", "social", "2026-10-01", "2026-09-01T00:00:00", 0.91, 62000),
        ])
    return deepcopy(root)


def _mutant_source(clean: str, instance: str) -> tuple[str, dict[str, Any] | None]:
    truth = TRUTH[instance]
    if truth is None:
        return clean, None
    old, new = MUTATIONS[instance]
    if clean.count(old) != 1:
        raise ValueError(f"mutation site is not unique: {instance}")
    mutated = clean.replace(old, new, 1)
    if ast.dump(ast.parse(clean)) == ast.dump(ast.parse(mutated)):
        raise ValueError("mutation did not change the AST")
    line = clean.count("\n", 0, clean.index(old)) + 1
    record = {
        "operator": "single_ast_site_substitution", "job_id": JOB1,
        "qualified_function_name": truth, "original_snippet": old, "mutant_snippet": new,
        "original_span": {"start_line": line, "end_line": line}, "candidate_count": 1,
        "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return mutated, record


def _pipeline(repo_root: Path, job_id: str, job1_source: str) -> GeneratedPipeline:
    source = job1_source if job_id == JOB1 else (repo_root / JOB_SOURCES[job_id]).read_text()
    generated_path = f"generated/protocol_2_2/{JOB_SOURCES[job_id].name}"
    roles = {
        JOB1: (
            ("select_snapshot_observations", "Select snapshot-usable observation rows.", ["observation table", "planning policy"], ["applicable dataframe"]),
            ("reduce_source_repeats", "Reduce repeated source observations.", ["applicable dataframe"], ["normalized dataframe"]),
            ("weight_source_reliability", "Combine observations and reliability context.", ["normalized dataframe", "reliability dataframe"], ["weighted dataframe"]),
            ("aggregate_opportunity_evidence", "Aggregate opportunity evidence and eligibility state.", ["weighted dataframe", "planning policy"], ["eligibility dataframe", "opportunities dataframe", "attribution dataframe"]),
        ),
        JOB2: (
            ("join_priority_context", "Combine opportunity and commercial context.", ["opportunities dataframe", "coverage dataframe", "commercial dataframe"], ["joined dataframe"]),
            ("calculate_single_count_priority", "Calculate opportunity priority state.", ["joined dataframe", "attribution dataframe"], ["scored dataframe"]),
            ("rank_priority_portfolio", "Rank opportunity portfolio state.", ["scored dataframe"], ["ranked dataframe"]),
        ),
        JOB3: (
            ("aggregate_campaign_candidates", "Aggregate campaign candidates and attribution state.", ["portfolio dataframe", "attribution dataframe"], ["candidate dataframe", "audit dataframe", "commitment"]),
            ("score_campaign_candidates", "Combine campaign and audience context.", ["candidate dataframe", "audience dataframe", "channel dataframe"], ["campaign scoring dataframe"]),
            ("allocate_campaign_budget", "Allocate campaign budget under constraints.", ["campaign scoring dataframe", "budget policy"], ["allocation dataframe"]),
        ),
        JOB4: (
            ("join_available_windows", "Combine campaign, calendar and capacity state.", ["allocation dataframe", "calendar dataframe", "capacity dataframe"], ["available windows dataframe"]),
            ("choose_activation_windows", "Choose campaign activation windows.", ["available windows dataframe", "scheduling policy"], ["activation actions dataframe"]),
            ("split_campaign_totals", "Split campaign totals across chosen windows.", ["selected windows", "campaign counts", "scheduling policy"], ["activation actions dataframe"]),
            ("aggregate_activation_schedule", "Aggregate the activation schedule.", ["activation actions dataframe", "attribution commitment", "scheduling policy"], ["activation plan"]),
        ),
    }
    pipeline = GeneratedPipeline(
        entry_file=generated_path,
        files=[GeneratedFile(generated_path, source)],
        review_boundaries=[{
            "boundary_id": f"rb-n27phb-j{JOB_ORDER.index(job_id) + 1}-{index}",
            "function_name": name, "qualified_function_name": name,
            "source_path": generated_path, "role": role,
            "expected_inputs": inputs, "expected_outputs": outputs, "semantic_stage": job_id,
        } for index, (name, role, inputs, outputs) in enumerate(roles[job_id], 1)],
    )
    pipeline.validate()
    return pipeline


def _contains_upstream_identifier(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            key in {"contribution_audit", "contribution_id", "source_id", "opportunity_id"}
            or _contains_upstream_identifier(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_upstream_identifier(item) for item in value)
    return False


def _job_input(job_id: str, prior: Mapping[str, Any] | None, root: Mapping[str, Any]) -> dict[str, Any]:
    if job_id == JOB1:
        return {key: deepcopy(root[key]) for key in ("scenario_label", "market_observations", "source_reliability", "repeat_resolution_policy", "planning_policy")}
    if job_id == JOB2:
        return {
            "opportunities": deepcopy(prior["opportunities"]),
            "evidence_attribution": deepcopy(prior["evidence_attribution"]),
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
    value = {
        "campaign_allocations": deepcopy(prior["campaign_allocations"]),
        "attribution_commitment": deepcopy(prior["attribution_commitment"]),
        "metadata": deepcopy(prior["metadata"]),
        "activation_calendar": deepcopy(root["activation_calendar"]),
        "channel_capacity": deepcopy(root["channel_capacity"]),
        "scheduling_policy": deepcopy(root["scheduling_policy"]),
    }
    if _contains_upstream_identifier(value):
        raise ValueError("Job-4 stdin contains row-level upstream identity")
    return value


def _validate_output(job_id: str, output: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    required = {
        JOB1: {"opportunities", "evidence_attribution", "metadata"},
        JOB2: {"priority_portfolio", "evidence_attribution", "metadata"},
        JOB3: {"campaign_allocations", "attribution_commitment", "metadata"},
        JOB4: {"activation_plan", "metadata"},
    }
    if set(output) != required[job_id]:
        raise ValueError(f"unexpected {job_id} output fields: {set(output)}")
    if job_id == JOB3 and _contains_upstream_identifier(output):
        raise ValueError("Job-3 public output exposes row-level identity")
    if job_id == JOB4:
        if _contains_upstream_identifier(runtime_input) or _contains_upstream_identifier(output):
            raise ValueError("Job-4 record exposes row-level upstream identity")
        plan = output["activation_plan"]
        allocations = {row["campaign_id"]: row for row in runtime_input["campaign_allocations"]}
        actions: dict[str, list[Mapping[str, Any]]] = {}
        for row in plan["activation_actions"]:
            actions.setdefault(row["campaign_id"], []).append(row)
        for campaign, allocation in allocations.items():
            rows = actions.get(campaign, [])
            if round(sum(row["scheduled_budget"] for row in rows), 2) != round(allocation["allocated_budget"], 2):
                raise ValueError("Job-4 campaign budget is not conserved")
            if round(sum(row["expected_impact"] for row in rows), 4) != round(allocation["expected_impact"], 4):
                raise ValueError("Job-4 campaign impact is not conserved")
        if plan["attribution_commitment"] != runtime_input["attribution_commitment"]:
            raise ValueError("Job-4 attribution commitment changed")


def _run_program(source: str, runtime_input: Mapping[str, Any], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-c", source], input=json.dumps(runtime_input), text=True,
        capture_output=True, cwd=cwd, check=False,
    )
    if completed.returncode or completed.stderr:
        raise RuntimeError(f"deterministic job execution failed: {completed.stderr}")
    return json.loads(completed.stdout)


def _run_pipeline_sources(repo_root: Path, root: Mapping[str, Any], job1_source: str | None = None) -> dict[str, Any]:
    sources = {job: (job1_source if job == JOB1 and job1_source is not None else (repo_root / JOB_SOURCES[job]).read_text()) for job in JOB_ORDER}
    prior = None
    outputs = {}
    inputs = {}
    for job in JOB_ORDER:
        runtime_input = _job_input(job, prior, root)
        output = _run_program(sources[job], runtime_input, repo_root)
        _validate_output(job, output, runtime_input)
        inputs[job] = runtime_input
        outputs[job] = output
        prior = output
    return {"inputs": inputs, "outputs": outputs}


def _capture_instance(repo_root: Path, target: Path, instance: str, job1_source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pipelines = {job: _pipeline(repo_root, job, job1_source) for job in JOB_ORDER}
    root = input_for(instance)
    jobs = {}
    handoffs = []
    native_bindings = {}
    prior = None
    handoff_names = {
        JOB2: ("opportunities", "evidence_attribution"),
        JOB3: ("priority_portfolio", "evidence_attribution", "metadata"),
        JOB4: ("campaign_allocations", "attribution_commitment", "metadata"),
    }
    for index, job in enumerate(JOB_ORDER):
        runtime_input = _job_input(job, prior, root)
        branch = target / "capture-branches" / instance / f"canonical-v2-job-{index + 1}"
        execution = pb._load_execution(branch, job)
        if execution is None:
            materialize_opaque_branch(branch, allowlist={}, manifest_identity={"purpose": "n27phb-fresh-native-capture", "case": instance, "job": job})
            copy_etiq_worker_runtime(branch, repo_root / "src")
            execution = execute_pipeline_in_branch(
                branch, repo_root=repo_root, job_id=job, pipeline=pipelines[job],
                runtime_input=runtime_input, run_index=INSTANCES.index(instance),
                stage=f"n27phb-{index + 1}",
            )
        output = _parse_output(execution)
        _validate_output(job, output, runtime_input)
        native_path = execution.run_dir / "etiq-native-lineage.json"
        native = _json(native_path)
        if not native.get("objects") or not native.get("edges"):
            raise ValueError(f"empty native Etiq export: {instance}/{job}")
        realization = n25._realization(execution, pipelines[job], job)
        captured = n25._job_record(execution, output, realization)
        captured.update({
            "native_lineage": native,
            "native_lineage_file_sha256": _file_sha(native_path),
            "native_lineage_logical_sha256": ce.sha256(native),
            "native_lineage_export_status": execution.snapshot.inventories.get("json_lineage_export"),
        })
        jobs[job] = captured
        native_bindings[job] = {
            "file_sha256": captured["native_lineage_file_sha256"],
            "logical_sha256": captured["native_lineage_logical_sha256"],
            "objects": len(native["objects"]), "edges": len(native["edges"]),
        }
        if index:
            producer = JOB_ORDER[index - 1]
            handoffs.extend(n25._handoff(name, producer, job, jobs[producer]["output"][name]) for name in handoff_names[job])
        prior = output
    capture = {
        "schema_version": "n27phb-four-job-native-capture-1",
        "capture_id": stable_id("rerun-capture", ["n27phb", instance], 0),
        "instance_id": instance, "job_ids": list(JOB_ORDER), "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": {job: ce.sha256(_pipeline_payload(pipelines[job])) for job in JOB_ORDER},
        "native_lineage_bindings": native_bindings, "canonical": True, "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    n25._verify_four_capture(capture)
    bundle = [{"job_id": job, "files": [{"path": pipelines[job].files[0].path, "content": pipelines[job].files[0].content}]} for job in JOB_ORDER]
    return capture, bundle


def _oracle_jobs(root: Mapping[str, Any]) -> dict[str, Any]:
    result = compute_clean_result(root)
    return {job: result[f"job_{index}"] for index, job in enumerate(JOB_ORDER, 1)}


def _changed_campaigns(clean: Mapping[str, Any], faulty: Mapping[str, Any]) -> list[str]:
    left = {row["campaign_id"]: row for row in clean["activation_plan"]["activation_actions"]}
    right = {row["campaign_id"]: row for row in faulty["activation_plan"]["activation_actions"]}
    return sorted(campaign for campaign in set(left) | set(right) if left.get(campaign) != right.get(campaign))


def _rename_tokens(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_rename_tokens(item, old, new) for item in value]
    if isinstance(value, Mapping):
        return {key: _rename_tokens(item, old, new) for key, item in value.items()}
    return value


def _survivor_witness(root: Mapping[str, Any], applied_basis: str) -> list[dict[str, Any]]:
    snapshot = root["planning_policy"]["as_of_date"]
    usable = [
        row for row in root["market_observations"]
        if row["effective_date"] <= snapshot
        and row["recorded_at"][:10] <= snapshot
        and row["valid_until"] >= snapshot
    ]
    ordered = sorted(
        usable,
        key=lambda row: (row["opportunity_id"], row["source_id"], row[applied_basis]),
        reverse=False,
    )
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in ordered:
        groups.setdefault((row["opportunity_id"], row["source_id"]), []).append(row)
    witness = []
    configured = root["repeat_resolution_policy"]["basis"]
    for rows in groups.values():
        survivor = max(rows, key=lambda row: row[applied_basis])["contribution_id"]
        for row in rows:
            witness.append({
                "contribution_id": row["contribution_id"],
                "opportunity_id": row["opportunity_id"],
                "source_id": row["source_id"],
                "effective_date": row["effective_date"],
                "recorded_at": row["recorded_at"],
                "configured_basis": configured,
                "applied_basis": applied_basis,
                "survivor_status": "survivor" if row["contribution_id"] == survivor else "discarded",
            })
    return sorted(witness, key=lambda row: (row["opportunity_id"], row["source_id"], row["effective_date"]))


def _deterministic_private_qualification(repo_root: Path, target: Path) -> dict[str, Any]:
    summary_path = target / "qualification-private/qualification-summary.json"
    if summary_path.exists():
        record = _json(summary_path)
        ce._verified_self_hash(record, "qualification_sha256")
        return record
    clean_source = (repo_root / JOB1_SOURCE).read_text()
    controls = {}
    for instance in INSTANCES[:3]:
        root = input_for(instance)
        oracle = compute_clean_result(root)
        executed = _run_pipeline_sources(repo_root, root)["outputs"]
        expected = _oracle_jobs(root)
        if ce.canonical_json(executed) != ce.canonical_json(expected):
            raise ValueError(f"control and independent oracle differ: {instance}")
        reversed_root = deepcopy(root)
        reversed_root["market_observations"] = list(reversed(reversed_root["market_observations"]))
        if ce.canonical_json(compute_clean_result(reversed_root)["job_4"]) != ce.canonical_json(oracle["job_4"]):
            raise ValueError("permutation invariance failed")
        irrelevant_root = deepcopy(root)
        irrelevant_root["market_observations"].append(_observation(
            "qualification", "expired-extra", "unused", "unused", "north", "unused", "email",
            "2025-01-01", "2025-01-02T00:00:00", 0.123, 12345, valid="2025-02-01",
        ))
        if ce.canonical_json(compute_clean_result(irrelevant_root)["job_4"]) != ce.canonical_json(oracle["job_4"]):
            raise ValueError("irrelevant-row invariance failed")
        old = root["scenario_label"].removesuffix("-planning")
        renamed_root = _rename_tokens(root, old, "qualification-renamed")
        renamed = compute_clean_result(renamed_root)["job_4"]
        normalized = _rename_tokens(renamed, "qualification-renamed", old)
        normalized["activation_plan"]["attribution_commitment"]["logical_sha256"] = oracle["job_4"]["activation_plan"]["attribution_commitment"]["logical_sha256"]
        if ce.canonical_json(normalized) != ce.canonical_json(oracle["job_4"]):
            raise ValueError("identifier-renaming invariance failed")
        private = {
            "schema_version": "n27phb-private-clean-control-1", "instance": instance,
            "oracle_output": oracle, "executed_outputs": executed,
            "permutation_invariant": True, "irrelevant_row_invariant": True,
            "identifier_renaming_invariant": True,
        }
        private["record_sha256"] = ce.sha256(private)
        ce._write_immutable(target / "qualification-private/controls" / f"{instance}.json", private)
        controls[instance] = private["record_sha256"]
    faults = {}
    signatures = set()
    f2_witnesses = {}
    for instance in INSTANCES[3:]:
        root = input_for(instance)
        clean_outputs = _oracle_jobs(root)
        mutated, mutation = _mutant_source(clean_source, instance)
        actual = _run_pipeline_sources(repo_root, root, mutated)["outputs"]
        clean_job4, job4 = clean_outputs[JOB4], actual[JOB4]
        if len(job4["activation_plan"]["activation_actions"]) != len(clean_job4["activation_plan"]["activation_actions"]):
            raise ValueError(f"fault changes Job-4 action count: {instance}")
        changed = _changed_campaigns(clean_job4, job4)
        if not changed or len(changed) > 2:
            raise ValueError(f"fault campaign delta is not small: {instance}")
        signature = ce.sha256(job4)
        if signature in signatures or signature == ce.sha256(clean_job4):
            raise ValueError(f"fault Job-4 numerical signature is not distinct: {instance}")
        signatures.add(signature)
        job1 = actual[JOB1]
        prefix = root["scenario_label"].removesuffix("-planning")
        mechanism = FAULT_MECHANISM[instance]
        if mechanism == "F1_rounded_threshold":
            threshold_id = f"{prefix}-opportunity-threshold"
            clean_decision = next(row for row in compute_clean_result(root)["decisions"] if row["opportunity_id"] == threshold_id)
            if clean_decision["eligible"] or threshold_id not in {row["opportunity_id"] for row in job1["opportunities"]}:
                raise ValueError("F1 does not reverse the precision-sensitive eligibility decision")
        elif mechanism == "F2_temporal_survivor":
            clean_witness = _survivor_witness(root, "effective_date")
            faulty_witness = _survivor_witness(root, "recorded_at")
            clean_survivor = [row for row in clean_witness if "temporal-" in row["contribution_id"] and "shared" not in row["contribution_id"] and row["survivor_status"] == "survivor"]
            faulty_survivor = [row for row in faulty_witness if "temporal-" in row["contribution_id"] and "shared" not in row["contribution_id"] and row["survivor_status"] == "survivor"]
            if len(clean_survivor) != 1 or len(faulty_survivor) != 1 or clean_survivor[0]["contribution_id"] == faulty_survivor[0]["contribution_id"]:
                raise ValueError("F2 witness does not resolve the applied temporal basis")
            f2_witnesses[instance] = {"clean": clean_witness, "faulty": faulty_witness}
        elif job1["metadata"]["weighted_count"] <= job1["metadata"]["normalized_count"]:
            raise ValueError("F3 does not create the reliability-scope collision")
        private = {
            "schema_version": "n27phb-private-hard-fault-1", "instance": instance,
            "fault_mechanism": mechanism, "truth_function": TRUTH[instance], "mutation": mutation,
            "matched_clean_instance": MATCHED_CLEAN[instance], "clean_outputs": clean_outputs,
            "fault_outputs": actual, "changed_campaigns": changed,
            "clean_job4_sha256": ce.sha256(clean_job4), "fault_job4_sha256": signature,
            "action_count_preserved": True, "schema_preserved": True,
        }
        private["record_sha256"] = ce.sha256(private)
        ce._write_immutable(target / "qualification-private/faults" / f"{instance}.json", private)
        faults[instance] = private["record_sha256"]
    witness = {
        "schema_version": "n27phb-f2-deterministic-witness-1", "status": "passed",
        "configured_basis": "effective_date", "fault_applied_basis": "recorded_at",
        "instances": f2_witnesses, "distinguishes_clean_and_faulty_survivors": True,
    }
    witness["witness_sha256"] = ce.sha256(witness)
    ce._write_immutable(target / "qualification-private/f2-survivor-witness.json", witness)
    summary = {
        "schema_version": "n27phb-private-deterministic-qualification-1", "status": "passed",
        "model_calls": 0, "controls": controls, "faults": faults,
        "oracle_source_sha256": _file_sha(repo_root / ORACLE_SOURCE),
        "fresh_job_source_sha256": {path.as_posix(): _file_sha(repo_root / path) for path in JOB_SOURCES.values()},
        "control_oracle_equality": True, "metamorphic_checks": 9,
        "one_site_faults": 6, "distinct_job4_signatures": 6,
        "f2_witnesses": 2, "job4_row_identity_absent": True, "job4_conservation_passed": True,
    }
    summary["qualification_sha256"] = ce.sha256(summary)
    ce._write_immutable(summary_path, summary)
    return summary
def _load_prepared(target: Path) -> dict[str, Any]:
    folders = {
        "captures": "captures", "catalogues": "catalogues", "source_bundles": "source-bundles",
        "crosswalks": "native-crosswalks", "indexes": "native-subtree-index",
        "reviewer_nodes": "payload-lazy-nodes", "disclosures": "artifact-disclosures",
        "omissions": "omission-manifests", "instances": "qualification-private/instances",
    }
    values = {name: {path.stem: _json(path) for path in sorted((target / folder).glob("*.json"))} for name, folder in folders.items()}
    if any(set(value) != set(INSTANCES) for value in values.values()):
        raise ValueError("Attempt 053 prepared record set is partial")
    for instance in INSTANCES:
        values["source_bundles"][instance] = values["source_bundles"][instance]["source_bundle"]
    return values


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PHB is authorized only for Attempt 053")
    authority = _verify_authority(repo_root)
    n27p.FUNCTIONS = TOP_LEVEL_FUNCTIONS
    pb.FUNCTIONS = TOP_LEVEL_FUNCTIONS
    _deterministic_private_qualification(repo_root, target)
    if (target / "captures").exists():
        return _load_prepared(target) | {"authority": authority}
    clean_source = (repo_root / JOB1_SOURCE).read_text()
    prepared = {name: {} for name in (
        "captures", "catalogues", "source_bundles", "crosswalks", "indexes",
        "reviewer_nodes", "disclosures", "omissions", "instances",
    )}
    topology = {}
    for instance in INSTANCES:
        source, mutation = _mutant_source(clean_source, instance)
        capture, source_bundle = _capture_instance(repo_root, target, instance, source)
        catalogue, crosswalk = n27p._catalogue(capture)
        catalogue["schema_version"] = "n27phb-four-job-native-catalogue-1"
        catalogue.pop("catalogue_sha256", None)
        catalogue["catalogue_sha256"] = ce.sha256(catalogue)
        compact, index = n27p.build_compact_graph(catalogue, crosswalk)
        compact["handoffs"] = deepcopy(catalogue["handoffs"])
        compact.pop("projection_sha256", None)
        compact["projection_sha256"] = ce.sha256(compact)
        reviewer, disclosure, omission = pb._payload_lazy_catalogue(catalogue, instance)
        lazy_compact = pb._lazy_graph(compact, reviewer)
        pb._assert_payload_lazy(lazy_compact, disclosure)
        topology[instance] = {
            job: {
                "objects": capture["native_lineage_bindings"][job]["objects"],
                "edges": capture["native_lineage_bindings"][job]["edges"],
                "visible_nodes": index["job_counts"][job]["visible_nodes"],
                "visible_edges": index["job_counts"][job]["visible_edges"],
                "collapsed_groups": index["job_counts"][job]["collapsed_clusters"],
            } for job in JOB_ORDER
        }
        instance_record = {
            "schema_version": "n27phb-private-instance-1", "opaque_instance_id": instance,
            "designation": "matched_clean_control" if TRUTH[instance] is None else "upstream_fault",
            "truth_job": None if TRUTH[instance] is None else JOB1,
            "truth_function": TRUTH[instance], "mutation": mutation,
            "matched_clean_case": MATCHED_CLEAN.get(instance),
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
            "omissions": "omission-manifests", "instances": "qualification-private/instances",
        }
        for name, record in records.items():
            ce._write_immutable(target / folders[name] / f"{instance}.json", record)
            prepared[name][instance] = source_bundle if name == "source_bundles" else record
        ce._write_immutable(target / "projections" / f"{instance}-compact.json", lazy_compact)
        for job in JOB_ORDER:
            raw = capture["jobs"][job]["native_lineage"]
            export = target / "native-exports" / instance / job / "etiq-native-lineage.json"
            ce._write_immutable(export, raw)
            job_record = {
                "schema_version": "n27phb-fresh-native-job-capture-1", "instance": instance,
                "job_id": job, "capture_status": "fresh_n27phb_execution",
                "native_export_file_sha256": _file_sha(export),
                "native_export_logical_sha256": ce.sha256(raw),
                "job_capture_sha256": ce.sha256(capture["jobs"][job]),
            }
            job_record["record_sha256"] = ce.sha256(job_record)
            ce._write_immutable(target / "job-captures" / instance / f"{job}.json", job_record)
    qualification = {
        "schema_version": "n27phb-native-capture-qualification-1", "status": "passed",
        "instances": 9, "fresh_job_executions": 36, "etiq_version": "2.3.0",
        "required_api": 'create_full_lineage_graph(graph_format="json")',
        "topology": topology, "exact_handoffs_per_capture": 8,
        "all_native_objects_edges_preserved": True,
    }
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/native-captures.json", qualification)
    return prepared | {"authority": authority}


def _artifact_for_state(prepared: Mapping[str, Any], instance: str, job: str, state_name: str) -> dict[str, Any]:
    catalogue = prepared["catalogues"][instance]
    canonical = [
        node for node in catalogue["jobs"][job]["nodes"]
        if any(state_name in str(name) for name in node.get("names", [])) and node.get("artifact_value_sha256")
    ]
    if not canonical:
        raise ValueError(f"captured state is absent: {instance}/{state_name}")
    crosswalk = prepared["crosswalks"][instance]["jobs"][job]["crosswalk"]
    matches = []
    for node in canonical:
        matches.extend(item for item in crosswalk if item["match_status"] == "exact" and node["node_ref"] in item["canonical_node_refs"])
    reviewer_nodes = prepared["reviewer_nodes"][instance]["nodes"]
    matches = [item for item in matches if "artifact_descriptor" in reviewer_nodes.get(item["native_node_ref"], {})]
    if not matches:
        raise ValueError(f"captured state lacks an exact native artifact: {instance}/{state_name}")
    compact = _json(Path(prepared["attempt_root"]) / "projections" / f"{instance}-compact.json") if "attempt_root" in prepared else None
    visible = set() if compact is None else {node["native_node_ref"] for node in compact["nodes"]}
    for item in matches:
        native_ref = item["native_node_ref"]
        groups = [group_id for group_id, binding in prepared["indexes"][instance]["groups"].items() if native_ref in binding["node_refs"]]
        if len(groups) == 1 and native_ref not in visible:
            descriptor = reviewer_nodes[native_ref]["artifact_descriptor"]
            return {"native_node_ref": native_ref, "execution_group_id": groups[0], "artifact_ref": descriptor["artifact_ref"]}
    raise ValueError(f"captured state is not uniquely hidden: {instance}/{state_name}")


def adaptive_relevance(prepared: Mapping[str, Any], target: Path) -> dict[str, Any]:
    prepared = dict(prepared)
    prepared["attempt_root"] = target
    state_by_mechanism = {
        "F1_rounded_threshold": "eligibility_df",
        "F2_temporal_survivor": "survivor_decision_df",
        "F3_source_only_join": "weighted_df",
    }
    faults = {}
    for instance in INSTANCES[3:]:
        state_name = state_by_mechanism[FAULT_MECHANISM[instance]]
        binding = _artifact_for_state(prepared, instance, JOB1, state_name)
        compact = _json(target / "projections" / f"{instance}-compact.json")
        expanded, event = pb.expand_native_subtree(
            prepared["catalogues"][instance], prepared["reviewer_nodes"][instance],
            prepared["indexes"][instance], {"graph_review": {"evidence": compact}},
            binding["execution_group_id"],
        )
        if binding["artifact_ref"] not in event["newly_disclosed_artifact_refs"]:
            raise ValueError("decisive artifact is not disclosed by its native subtree")
        faults[instance] = {
            "truth_function": TRUTH[instance], "fault_mechanism": FAULT_MECHANISM[instance],
            "decisive_state_name": state_name, **binding, "initially_hidden": True,
            "one_expansion_reachable": True, "one_inspection_reachable": True,
            "expanded_projection_sha256": expanded["graph_review"]["evidence"]["projection_sha256"],
        }
    audit_states = {}
    for instance in INSTANCES:
        binding = _artifact_for_state(prepared, instance, JOB3, "contribution_audit_df")
        compact = _json(target / "projections" / f"{instance}-compact.json")
        _, event = pb.expand_native_subtree(
            prepared["catalogues"][instance], prepared["reviewer_nodes"][instance],
            prepared["indexes"][instance], {"graph_review": {"evidence": compact}},
            binding["execution_group_id"],
        )
        if binding["artifact_ref"] not in event["newly_disclosed_artifact_refs"]:
            raise ValueError("Job-3 contribution audit is not legally inspectable")
        audit_states[instance] = {**binding, "initially_hidden": True, "output_field": False}
    f2 = {instance: faults[instance] for instance in INSTANCES[5:7]}
    if len(f2) != 2 or not all(row["decisive_state_name"] == "survivor_decision_df" for row in f2.values()):
        raise ValueError("F2 native witness reachability failed")
    record = {
        "schema_version": "n27phb-adaptive-relevance-1", "status": "passed",
        "faults": faults, "f2_survivor_witnesses": f2,
        "job3_private_audit_states": audit_states, "function_name_matching_alone_used": False,
    }
    record["qualification_sha256"] = ce.sha256(record)
    return record
def _semantic_declarations(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    declarations = []
    for position, job in enumerate(JOB_ORDER, 1):
        for boundary in catalogue["jobs"][job]["realized_boundaries"]:
            declarations.append({
                "boundary_id": boundary["boundary_id"], "job": f"job_{position}",
                "executed_function_name": boundary["function_name"],
                "coarse_purpose": boundary["role"],
                "input_type_names": deepcopy(boundary["expected_inputs"]),
                "output_type_names": deepcopy(boundary["expected_outputs"]),
            })
    return {"semantic_declarations": declarations}


def _job4_execution(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    captured = catalogue["jobs"][JOB4]
    record = {
        "job": "job_4", "input": deepcopy(captured["input"]),
        "parsed_output": deepcopy(captured["output"]),
        "stdout": str(captured["stdout"]), "stderr": str(captured["stderr"]),
    }
    if _contains_upstream_identifier(record):
        raise ValueError("review-visible Job-4 record contains upstream row identity")
    return record


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], compact: Mapping[str, Any], cell: str) -> dict[str, Any]:
    package = {
        "schema_version": "n27phb-review-package-1",
        "review_task": "Assess whether the observed execution is consistent with the stated marketing task. The execution may be correct or faulty. Report a behaviorally significant processing error and its earliest responsible job and function only when supported; otherwise report no fault.",
        "marketing_objective": "Qualify current market evidence, prioritize commercial opportunities, allocate campaign budgets, and schedule capacity-constrained activations.",
        "pipeline_topology": [
            {"job": f"job_{position}", "name": name, "position": position, "observation_point": position == 4}
            for position, name in enumerate(("market evidence", "opportunity priority", "campaign allocation", "activation scheduling"), 1)
        ],
        "complete_actual_source_bundle": deepcopy(source_bundle),
        "observed_job_4_execution": _job4_execution(catalogue),
        "final_response_contract": {
            "fault_detected": "Boolean", "suspect_job": "job_1, job_2, job_3, job_4, or null",
            "suspect_function": "visible executed function name or null",
            "explanation": "concise evidence-grounded reasoning",
            "cited_evidence": "opaque references or short visible excerpts",
        },
    }
    if cell in GRAPH_CELLS:
        package["graph_review"] = {
            "framing": "Captured native execution structure may be used in the assessment.",
            "evidence": deepcopy(compact),
        }
    if cell in SEMANTIC_CELLS:
        package["semantic_declaration_bundle"] = _semantic_declarations(catalogue)
    if cell in {"P04", "P05"}:
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {
            "operation": "expand_execution_group_then_artifact_inspection",
            "model_selects_group_artifact_and_mode": True, "required_before_terminal": True,
            "maximum_completed_expansions": 1, "maximum_completed_inspections": 1,
        }
    elif cell == "P06":
        package["available_operations"] = ["reconsider_same_evidence"]
        package["interaction_contract"] = {
            "operation": "reconsider_same_evidence", "required_passes": 2,
            "evidence_bytes_added_each_pass": 0,
        }
    return package


def schedule() -> dict[str, Any]:
    cells = []
    for instance in INSTANCES:
        for cell in CELLS:
            cells.append({
                "opaque_instance_id": instance, "cell_id": cell,
                "mode": CONTROLLER_MODE[cell],
                "declaration_setting": "B1" if cell in SEMANTIC_CELLS else "B0",
                "branch_id": f"brn-{ce.sha256(['n27phb', instance, cell])[7:23]}",
            })
    trials = []
    for condition in cells:
        for repetition in (1, 2, 3):
            trials.append({
                **condition, "repetition": repetition,
                "trial_id": f"trial-{ce.sha256(['n27phb', condition['branch_id'], repetition])[7:23]}",
            })
    random.Random(SCHEDULE_SEED).shuffle(trials)
    for position, trial in enumerate(trials, 1):
        trial["schedule_position"] = position
    positions = {
        instance: [row["schedule_position"] for row in trials if row["opaque_instance_id"] == instance]
        for instance in INSTANCES
    }
    if (
        len(cells) != 54 or len(trials) != 162
        or sum(CALLS_BY_CELL[row["cell_id"]] for row in trials) != 324
        or all(row["opaque_instance_id"] in INSTANCES[:3] for row in trials[:9])
        or any(max(values) - min(values) <= 17 for values in positions.values())
    ):
        raise AssertionError("N27PHB randomized schedule invariants changed")
    return {
        "cells": cells, "review_trials": trials, "repair_traces": [],
        "controller_only_randomization": {
            "algorithm": "python-random-mt19937-shuffle", "seed": SCHEDULE_SEED,
            "globally_randomized": True,
        },
    }
def _package_records(target: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((target / "controller-manifests").glob("*.json")):
        manifest = _json(path)
        package_path = target / manifest["reviewer_package_path"]
        if _file_sha(package_path) != manifest["reviewer_package_file_sha256"]:
            raise ValueError("reviewer package file binding changed")
        record = _json(package_path)
        ce._verified_self_hash(record, "package_sha256")
        records.append(record)
    order = {row["branch_id"]: position for position, row in enumerate(schedule()["cells"])}
    return sorted(records, key=lambda row: order[row["controller_condition"]["branch_id"]])


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in package.items() if key not in {"available_operations", "interaction_contract"}}


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    visible = ce.canonical_json(request).decode()
    forbidden = (
        "qualification-private", "oracle_output", "clean_outputs", "fault_outputs", "matched_clean_case",
        "truth_job", "truth_function", "mutant_snippet", "original_snippet", "mutation_sha256",
        "opaque_instance_id", "cell_id", "branch_id", "trial_id", "designation",
    )
    if any(token in visible for token in forbidden) or any(instance in visible for instance in INSTANCES):
        raise ValueError("rendered request leaks private or controller-only state")
    # Job-1 input field names legitimately occur inside the required complete
    # source listing.  Leakage is therefore enforced structurally by the
    # package allowlist, rather than by scanning source-code text.
    if any(key in package for key in ("market_observations", "source_reliability", "job_1_input")):
        raise ValueError("rendered request leaks Job-1 top-level input")
    return request


def _schema_for_stage(stage: str) -> Path:
    return {"final": FINAL_SCHEMA, "group": GROUP_SCHEMA, "artifact": ARTIFACT_SCHEMA, "reconsider": RECONSIDER_SCHEMA}[stage]


def validate_schemas(repo_root: Path) -> dict[str, str]:
    values = {}
    for path in (FINAL_SCHEMA, GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA):
        schema = _json(repo_root / path)
        Draft202012Validator.check_schema(schema)
        validate_strict_provider_schema(schema)
        values[path.as_posix()] = _file_sha(repo_root / path)
    return values


def _configure_controller() -> None:
    pb.ATTEMPT = ATTEMPT
    pb.TASK = TASK
    pb.TASK_SHA256 = TASK_SHA256
    pb.AUTHORITY = AUTHORITY
    pb.AUTHORITY_SHA256 = AUTHORITY_SHA256
    pb.PROMPT = PROMPT
    pb.FINAL_SCHEMA = FINAL_SCHEMA
    pb.GROUP_SCHEMA = GROUP_SCHEMA
    pb.ARTIFACT_SCHEMA = ARTIFACT_SCHEMA
    pb.RECONSIDER_SCHEMA = RECONSIDER_SCHEMA
    pb.INSTANCES = INSTANCES
    pb.TRUTH = TRUTH
    pb.MATCHED_CLEAN = MATCHED_CLEAN
    pb.render_request = render_request
    pb.validate_response = validate_response


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], stage: str) -> dict[str, Any]:
    _configure_controller()
    return _PB_VALIDATE_RESPONSE(repo_root, package, response, stage)


def score_response(instance: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    truth = instance["truth_function"]
    detected = bool(validation["fault_detected"])
    if truth is None:
        return {
            "designation": "matched_clean_control", "fault_detected": detected,
            "false_positive": detected, "correct_job_attribution": False,
            "exact_function_localisation": False, "truth_job": None, "truth_function": None,
        }
    correct_job = detected and validation["suspect_job"] == "job_1"
    exact = correct_job and validation["normalized_suspect_function"] == truth and validation["suspect_function_visible"]
    return {
        "designation": "upstream_fault", "fault_detected": detected,
        "false_positive": False, "correct_job_attribution": correct_job,
        "exact_function_localisation": exact, "truth_job": "job_1", "truth_function": truth,
    }


def run_review_session(repo_root: Path, target: Path, catalogue: Mapping[str, Any], reviewer: Mapping[str, Any], disclosure: Mapping[str, Any], index: Mapping[str, Any], package_record: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    _configure_controller()
    return _PB_RUN_REVIEW(repo_root, target, catalogue, reviewer, disclosure, index, package_record, trial_id)


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by = {(row["controller_condition"]["opaque_instance_id"], row["controller_condition"]["cell_id"]): row["reviewer_package"] for row in records}
    checks = []
    for instance in INSTANCES:
        packages = {cell: by[(instance, cell)] for cell in CELLS}
        common_keys = {
            "schema_version", "review_task", "marketing_objective", "pipeline_topology",
            "complete_actual_source_bundle", "observed_job_4_execution", "final_response_contract",
        }
        common_hashes = {cell: ce.sha256({key: packages[cell][key] for key in common_keys}) for cell in CELLS}
        checks.append({"instance": instance, "invariant": "identical_common_bytes", "passed": len(set(common_hashes.values())) == 1})
        graph_hashes = {cell: ce.sha256(packages[cell]["graph_review"]["evidence"]) for cell in GRAPH_CELLS}
        checks.append({"instance": instance, "invariant": "identical_starting_graph_bytes", "passed": len(set(graph_hashes.values())) == 1})
        checks.append({"instance": instance, "invariant": "p01_no_graph_or_semantics", "passed": "graph_review" not in packages["P01"] and "semantic_declaration_bundle" not in packages["P01"]})
        checks.append({"instance": instance, "invariant": "semantic_cells_only", "passed": all(("semantic_declaration_bundle" in packages[cell]) == (cell in SEMANTIC_CELLS) for cell in CELLS)})
        checks.append({"instance": instance, "invariant": "adaptive_mechanics_matched", "passed": packages["P04"]["interaction_contract"] == packages["P05"]["interaction_contract"]})
    if not all(row["passed"] for row in checks):
        raise ValueError(f"pairwise package isolation failed: {[row for row in checks if not row['passed']]}")
    return checks


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if len(records) != 54 or len(design["review_trials"]) != 162:
        raise ValueError("N27PHB package/review count changed")
    if sum(CALLS_BY_CELL[row["cell_id"]] for row in design["review_trials"]) != 324:
        raise ValueError("N27PHB planned call count changed")
    schemas = validate_schemas(repo_root)
    pairwise = _pairwise_checks(records)
    maximum_request = 0
    maximum_artifact = 0
    allowed_base = {
        "schema_version", "review_task", "marketing_objective", "pipeline_topology",
        "complete_actual_source_bundle", "observed_job_4_execution", "final_response_contract",
    }
    allowed_by_cell = {
        "P01": allowed_base,
        "P02": allowed_base | {"graph_review"},
        "P03": allowed_base | {"graph_review", "semantic_declaration_bundle"},
        "P04": allowed_base | {"graph_review", "available_operations", "interaction_contract"},
        "P05": allowed_base | {"graph_review", "semantic_declaration_bundle", "available_operations", "interaction_contract"},
        "P06": allowed_base | {"graph_review", "available_operations", "interaction_contract"},
    }
    allowlist_rows = []
    for record in records:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        cell = condition["cell_id"]
        if set(package) != allowed_by_cell[cell]:
            raise ValueError(f"positive package allowlist failed: {cell}/{set(package)}")
        source_paths = [file["path"] for job in package["complete_actual_source_bundle"] for file in job["files"]]
        expected_paths = [f"generated/protocol_2_2/{JOB_SOURCES[job].name}" for job in JOB_ORDER]
        if source_paths != expected_paths or any("oracle" in path or "experiment" in path for path in source_paths):
            raise ValueError("source bundle contains a non-executed file")
        if _contains_upstream_identifier(package["observed_job_4_execution"]):
            raise ValueError("Job-4 package record contains upstream identity")
        request = render_request(package)
        maximum_request = max(maximum_request, n25._token_count(request))
        if "graph_review" in package:
            pb._assert_payload_lazy(package["graph_review"]["evidence"], prepared["disclosures"][condition["opaque_instance_id"]])
        allowlist_rows.append({
            "branch_id": condition["branch_id"], "cell": cell,
            "allowed_package_keys": sorted(allowed_by_cell[cell]),
            "allowed_source_files": source_paths, "rendered_request_sha256": ce.sha256(request),
            "passed": True,
        })
    for instance in INSTANCES:
        for artifact in prepared["disclosures"][instance]["artifacts"].values():
            maximum_artifact = max(maximum_artifact, n25._token_count(artifact["operation_node"]["artifact_content"]))
    if max(maximum_request, maximum_artifact) >= 100_000:
        raise ValueError("request or complete artifact exceeds provider context qualification")
    source_independence = {}
    historical_names = {"n27pe", "n27pf", "n27pg", "n27pa", "n27pb", "n25", "n26"}
    for path in (*JOB_SOURCES.values(), ORACLE_SOURCE):
        tree = ast.parse((repo_root / path).read_text())
        imports = [
            alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        if any(any(name.startswith(prefix) for prefix in historical_names) for name in imports):
            raise ValueError(f"fresh source imports historical job code: {path}")
        source_independence[path.as_posix()] = {"sha256": _file_sha(repo_root / path), "historical_job_imports": 0}
    audit = {
        "schema_version": "n27phb-positive-package-allowlist-audit-1", "status": "passed",
        "rows": allowlist_rows, "private_root_allowed": False,
        "executed_source_files_only": True, "source_independence": source_independence,
    }
    audit["audit_sha256"] = ce.sha256(audit)
    ce._write_immutable(target / "qualification/package-allowlist-and-leakage.json", audit)
    return {
        "schema_version": "n27phb-no-model-verification-1", "status": "passed", "model_calls": 0,
        "instances": 9, "fresh_job_executions": 36, "packages": 54, "terminal_reviews": 162,
        "planned_provider_calls": 324, "required_follow_up_calls": 162, "repairs": 0,
        "strict_schema_hashes": schemas, "pairwise_checks": len(pairwise),
        "maximum_initial_request_tokens": maximum_request,
        "maximum_complete_artifact_tokens": maximum_artifact,
        "fault_denominator_per_cell": 18, "control_denominator_per_cell": 9,
        "package_allowlist_audit_sha256": audit["audit_sha256"],
        "private_qualification_tree_sha256": ce.sha256(ce._tree_hashes(target / "qualification-private")),
        "attempt_052_preservation_verified": True,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if len(existing) == 54:
        qualification = qualify_packages(repo_root, target, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    relevance = adaptive_relevance(prepared, target)
    ce._write_immutable(target / "qualification-private/adaptive-relevance.json", relevance)
    lineage = {
        "schema_version": "n27phb-lineage-1", "attempt": "053",
        "attempt_052_preserved": True, "scientific_reuse_from_attempt_052": False,
        "controller_mechanics_reused_from": ["N27PHA", "N27PB"],
        "fresh_job_sources": [path.as_posix() for path in JOB_SOURCES.values()],
    }
    lineage["lineage_sha256"] = ce.sha256(lineage)
    ce._write_immutable(target / "lineage/attempt-lineage.json", lineage)
    existing_by_branch = {record["controller_condition"]["branch_id"]: record for record in existing}
    records = []
    for condition in design["cells"]:
        if condition["branch_id"] in existing_by_branch:
            records.append(existing_by_branch[condition["branch_id"]])
            continue
        instance = condition["opaque_instance_id"]
        package = build_package(
            prepared["catalogues"][instance], prepared["source_bundles"][instance],
            _json(target / "projections" / f"{instance}-compact.json"), condition["cell_id"],
        )
        record = {
            "schema_version": "n27phb-frozen-package-1", "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance]["catalogue_sha256"],
            "disclosure_catalogue_sha256": prepared["disclosures"][instance]["catalogue_sha256"],
            "omission_manifest_sha256": prepared["omissions"][instance]["manifest_sha256"],
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        path = target / "packages" / condition["branch_id"] / "reviewer-package.json"
        ce._write_immutable(path, record)
        manifest = {
            "schema_version": "n27phb-controller-manifest-1", "controller_condition": deepcopy(condition),
            "reviewer_package_path": path.relative_to(target).as_posix(),
            "reviewer_package_file_sha256": _file_sha(path), "package_sha256": record["package_sha256"],
        }
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{condition['branch_id']}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, target, records, prepared, design)
    pairwise = {"schema_version": "n27phb-pairwise-package-differences-1", "rows": _pairwise_checks(records), "all_passed": True}
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {
        "schema_version": "n27phb-review-design-1", "review_trials": design["review_trials"],
        "controller_only_randomization": design["controller_only_randomization"],
    })
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n27phb-repair-design-1", "repair_traces": []})
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27phb_experiment.py"), JOB1_SOURCE, JOB2_SOURCE,
        JOB3_SOURCE, JOB4_SOURCE, ORACLE_SOURCE, PROMPT, FINAL_SCHEMA,
        GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27phb_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 053 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after live reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("focused N27PHB tests must pass before freeze")
    freeze = {
        "schema_version": "n27phb-experiment-freeze-1", "attempt": "053",
        "status": "frozen_before_live_experiment",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {relative.as_posix(): _file_sha(repo_root / relative) for relative in _code_paths()},
        "attempt_052_hashes": deepcopy(ATTEMPT_052_HASHES),
        "protected_hashes": deepcopy(PROTECTED_HASHES),
        "sandbox_gate_file_sha256": _file_sha(repo_root / SANDBOX_GATE),
        "sandbox_bindings": deepcopy(built["prepared"]["authority"]["sandbox"]),
        "attempt_052_token_correction": deepcopy(built["prepared"]["authority"]["token_correction"]),
        "controller_only_schedule_seed": SCHEDULE_SEED,
        "private_qualification_tree_sha256": ce.sha256(ce._tree_hashes(target / "qualification-private")),
        "package_allowlist_file_sha256": _file_sha(target / "qualification/package-allowlist-and-leakage.json"),
        "native_capture_file_sha256": _file_sha(target / "qualification/native-captures.json"),
        "capture_hashes": {instance: built["prepared"]["captures"][instance]["capture_sha256"] for instance in INSTANCES},
        "catalogue_hashes": {instance: built["prepared"]["catalogues"][instance]["catalogue_sha256"] for instance in INSTANCES},
        "instance_hashes": {instance: built["prepared"]["instances"][instance]["instance_sha256"] for instance in INSTANCES},
        "tree_hashes": {folder: ce.sha256(ce._tree_hashes(target / folder)) for folder in (
            "capture-branches", "job-captures", "native-exports", "catalogues",
            "artifact-disclosures", "omission-manifests", "projections", "packages", "controller-manifests",
        )},
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "no_model_verification_file_sha256": _file_sha(target / "qualification/no-model-verification.json"),
        "no_model_resume_replay_file_sha256": _file_sha(target / "qualification/no-model-resume-replay.json"),
        "focused_test_results_file_sha256": _file_sha(focused),
        "expected_counts": {"model_calibration_calls": 0, "instances": 9, "fresh_job_executions": 36, "packages": 54, "reviews": 162, "provider_calls": 324, "repairs": 0},
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
        if _file_sha(repo_root / relative) != expected:
            raise ValueError(f"frozen code changed: {relative}")
    built = build_attempt(repo_root, target)
    if ce.sha256(ce._tree_hashes(target / "qualification-private")) != freeze["private_qualification_tree_sha256"]:
        raise ValueError("frozen private qualification changed")
    for folder, expected in freeze["tree_hashes"].items():
        if ce.sha256(ce._tree_hashes(target / folder)) != expected:
            raise ValueError(f"frozen tree changed: {folder}")
    if sorted(record["package_sha256"] for record in built["records"]) != freeze["package_hashes"]:
        raise ValueError("frozen package membership changed")
    if ce.sha256(built["design"]["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("frozen review schedule changed")
    return {"status": "verified", "freeze_sha256": digest, "packages": 54, "reviews": 162, "provider_calls": 324, "repairs": 0, "qualification": built["qualification"]}


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("live authority must be consumed before reviews")
    freeze = _json(target / "experiment-freeze.json")
    record = {
        "schema_version": "n27phb-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "one_use_live_authority": True,
        "authorized_calls": 324, "model_calibration_calls": 0, "repairs": 0,
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _usage_values(usage: Mapping[str, Any]) -> dict[str, int]:
    input_tokens = int(usage.get("cumulative_actual_input_tokens") or 0)
    output_tokens = int(usage.get("cumulative_actual_output_tokens") or 0)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": int(usage.get("cumulative_actual_cached_input_tokens") or 0),
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for review in reviews:
        trial = review["controller_trial"]
        usage = _usage_values(review["usage"])
        artifact = review.get("selected_artifact") or {}
        rows.append({
            "trial_id": trial["trial_id"], "instance": trial["opaque_instance_id"],
            "cell_id": trial["cell_id"], "repetition": trial["repetition"], "designation": review["designation"],
            "fault_mechanism": FAULT_MECHANISM.get(trial["opaque_instance_id"]),
            "fault_detected": bool(review["fault_detected"]),
            "correct_job_attribution": bool(review["correct_job_attribution"]),
            "exact_function_localisation": bool(review["exact_function_localisation"]),
            "false_positive": bool(review["false_positive"]),
            "suspect_job": review["suspect_job"], "suspect_function": review["suspect_function"],
            "pre_fault_detected": bool(review["pre_fault_detected"]),
            "pre_suspect_job": review["pre_suspect_job"], "pre_suspect_function": review["pre_suspect_function"],
            "answer_changed": bool(review["answer_changed"]),
            "selected_group_contained_truth_state": bool(review["selected_group_contained_truth_state"]),
            "selected_artifact_was_truth_state": bool(review["selected_artifact_was_truth_state"]),
            "artifact_ref": artifact.get("artifact_ref"), "inspection": artifact.get("inspection"),
            "artifact_bytes_returned": int(artifact.get("artifact_bytes_returned") or 0),
            "provider_calls": len(review["call_records"]),
            "latency_seconds": sum(float(call.get("n27pb_latency_seconds") or 0) for call in review["call_records"]),
            **usage,
        })
    return rows


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    ratio = lambda values, key: {"numerator": sum(bool(row[key]) for row in values), "denominator": len(values)}
    return {
        "reviews": len(rows), "provider_calls": sum(row["provider_calls"] for row in rows),
        "fault_detection": ratio(faults, "fault_detected"),
        "correct_job_attribution": ratio(faults, "correct_job_attribution"),
        "exact_function_localisation": ratio(faults, "exact_function_localisation"),
        "control_false_positives": ratio(controls, "false_positive"),
        **{key: sum(row[key] for row in rows) for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "latency_seconds")},
    }


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    aggregate = _summary(rows)
    if aggregate["fault_detection"]["denominator"] != 108 or aggregate["control_false_positives"]["denominator"] != 54:
        raise RuntimeError("fault/control analysis denominators changed")

    def instance_cell_mean(instance: str, cell: str, outcome: str) -> float:
        values = [float(row[outcome]) for row in rows if row["instance"] == instance and row["cell_id"] == cell]
        if len(values) != 3:
            raise RuntimeError("three within-instance repetitions are required")
        return sum(values) / 3

    contrasts = []
    for name, left, right in (
        ("graph", "P02", "P01"), ("static_semantics", "P03", "P02"),
        ("adaptive_disclosure", "P04", "P02"), ("adaptive_semantics", "P05", "P04"),
        ("equal_call_reconsideration", "P06", "P02"),
    ):
        for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation", "false_positive"):
            eligible = INSTANCES[:3] if outcome == "false_positive" else INSTANCES[3:]
            differences = [
                instance_cell_mean(instance, left, outcome) - instance_cell_mean(instance, right, outcome)
                for instance in eligible
            ]
            contrasts.append({
                "name": name, "left": left, "right": right, "outcome": outcome,
                "unit": "within_instance_mean_of_three_repetitions",
                "per_instance_differences": differences,
                "mean_difference": sum(differences) / len(differences),
            })
    mechanism_summaries = {
        mechanism: {
            "aggregate": _summary([row for row in rows if row["fault_mechanism"] == mechanism]),
            "by_cell": {
                cell: _summary([row for row in rows if row["fault_mechanism"] == mechanism and row["cell_id"] == cell])
                for cell in CELLS
            },
        }
        for mechanism in sorted(set(FAULT_MECHANISM.values()))
    }
    analysis = {
        "schema_version": "n27phb-full-experiment-analysis-1",
        "aggregate": aggregate,
        "cell_summaries": {cell: _summary([row for row in rows if row["cell_id"] == cell]) for cell in CELLS},
        "fault_mechanism_summaries": mechanism_summaries,
        "fault_instance_cell_summaries": {
            f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell])
            for instance in INSTANCES[3:] for cell in CELLS
        },
        "control_instance_cell_summaries": {
            f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell])
            for instance in INSTANCES[:3] for cell in CELLS
        },
        "prespecified_paired_contrasts": contrasts,
        "operations": {
            "adaptive_sessions": sum(row["cell_id"] in {"P04", "P05"} for row in rows),
            "reconsideration_sessions": sum(row["cell_id"] == "P06" for row in rows),
            "answer_changes": sum(row["answer_changed"] for row in rows),
            "truth_group_selections": sum(row["selected_group_contained_truth_state"] for row in rows),
            "truth_artifact_selections": sum(row["selected_artifact_was_truth_state"] for row in rows),
            "artifact_bytes_returned": sum(row["artifact_bytes_returned"] for row in rows),
        },
        "token_accounting": {
            "input_includes_cached_input": True,
            "input_plus_output_tokens": aggregate["input_tokens"] + aggregate["output_tokens"],
        },
        "analysis_unit": "three repetitions averaged within instance before cross-instance contrasts",
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(target / "analysis/summary.json", analysis)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    _write_text(target / "analysis/all-review-rows.csv", stream.getvalue())
    return target / "analysis/summary.json"
def _rate(value: Mapping[str, int]) -> str:
    return "n/a" if not value["denominator"] else f"{value['numerator']}/{value['denominator']} ({100 * value['numerator'] / value['denominator']:.2f}%)"


def _write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PHB-corrected-full-native-etiq-experiment"
    findings = [
        "# N27PHB corrected full native-Etiq experiment", "",
        "Attempt 053 completed the authorized fresh nine-instance, three-repetition full experiment. Attempt 052 remains preserved.", "",
        "## Aggregate outcomes", "",
        f"- Fault sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 localisation: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Scientific provider calls: {aggregate['provider_calls']}; calibration calls: 0; repairs: 0",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; input plus output {aggregate['total_tokens']}",
        f"- Aggregate provider latency: {aggregate['latency_seconds']:.3f} seconds", "",
        "All 36 native Etiq captures, 54 packages and 162 model sessions were fresh. Repetitions were averaged within instance before cross-instance paired contrasts.", "",
        "## Records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-053/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-053/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-053/replay.json)",
        "- [Terminal](../../../../outputs/fault-experiments-v2-2-n10/attempt-053/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    cell_lines = ["# Cell results", "", "| Cell | Reviews | Detection | Job 1 | Exact | Control FP | Calls | Latency seconds |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cell in CELLS:
        value = analysis["cell_summaries"][cell]
        cell_lines.append(f"| {cell} | {value['reviews']} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} | {_rate(value['control_false_positives'])} | {value['provider_calls']} | {value['latency_seconds']:.3f} |")
    _write_text(report_dir / "cell-table.md", "\n".join(cell_lines))
    mechanism_lines = ["# Fault-mechanism results", "", "| Mechanism | Cell | Detection | Job 1 | Exact |", "|---|---|---:|---:|---:|"]
    for mechanism, value in analysis["fault_mechanism_summaries"].items():
        for cell in CELLS:
            summary = value["by_cell"][cell]
            mechanism_lines.append(f"| {mechanism} | {cell} | {_rate(summary['fault_detection'])} | {_rate(summary['correct_job_attribution'])} | {_rate(summary['exact_function_localisation'])} |")
    _write_text(report_dir / "fault-mechanism-table.md", "\n".join(mechanism_lines))
    review_lines = ["# Review results", "", "| Position | Trial | Rep | Instance | Cell | Detected | Job | Function | Calls |", "|---:|---|---:|---|---|---|---|---|---:|"]
    operation_lines = ["# Adaptive and reconsideration operations", "", "| Trial | Cell | Group | Artifact | Inspection | Bytes | True group | True artifact |", "|---|---|---|---|---|---:|---|---|"]
    token_lines = ["# Actual token and latency usage", "", "| Trial | Cell | Calls | Input | Cached | Output | Input + output | Latency seconds |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for review in sorted(reviews, key=lambda row: row["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        group = review.get("selected_group") or {}
        artifact = review.get("selected_artifact") or {}
        usage = _usage_values(review["usage"])
        latency = sum(float(call.get("n27pb_latency_seconds") or 0) for call in review["call_records"])
        review_lines.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['repetition']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |")
        operation_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {artifact.get('inspection', '')} | {artifact.get('artifact_bytes_returned', 0)} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} |")
        token_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {len(review['call_records'])} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['total_tokens']} | {latency:.3f} |")
    _write_text(report_dir / "review-table.md", "\n".join(review_lines))
    _write_text(report_dir / "operation-table.md", "\n".join(operation_lines))
    _write_text(report_dir / "token-latency-table.md", "\n".join(token_lines))
    _write_text(report_dir / "paired-contrasts.json", json.dumps(analysis["prespecified_paired_contrasts"], indent=2, sort_keys=True))


def _write_handoff(repo_root: Path, target: Path) -> None:
    aggregate = _json(target / "analysis/summary.json")["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PHB Attempt 053 corrected full experiment results", "",
        "Status: `completed_full_experiment_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "",
        "- Zero model calibration calls",
        "- Nine fresh instances and 36 fresh native Etiq job captures",
        f"- 54 packages; 162 terminal reviews; {aggregate['provider_calls']} scientific calls; zero repairs", "",
        "Outcomes", "",
        f"- Sensitivity: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {_rate(aggregate['control_false_positives'])}", "",
        "Attempt 052 and protected execution surfaces remained unchanged.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PHB_attempt_053_results_to_overseer.email.md", "\n".join(lines))
def execute_lifecycle(repo_root: Path, target: Path) -> Path:
    repo_root, target = repo_root.resolve(), target.resolve()
    verified = verify_frozen_attempt(repo_root, target)
    create_live_consumption(repo_root, target)
    prepared = prepare_attempt(repo_root, target)
    packages = {record["controller_condition"]["branch_id"]: record for record in _package_records(target)}
    trials = _json(target / "review-design.json")["review_trials"]
    relevance = _json(target / "qualification-private/adaptive-relevance.json")["faults"]
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
            group = session["selected_group"] or {}; artifact = session["selected_artifact"] or {}
            record = {
                "schema_version": "n27phb-review-record-1", "controller_trial": deepcopy(trial),
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
                "selected_group_contained_truth_state": bool(group and group.get("execution_group_id") == truth.get("execution_group_id")),
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
        print(f"N27PHB review {len(reviews)}/162 complete: {trial['cell_id']}", flush=True)
    counts = pb.reconstruct_counts(reviews)
    if counts["reviews"] != 162 or counts["repairs"] != 0 or counts["logical_provider_calls"] > 324:
        raise RuntimeError(f"terminal review/call counts invalid: {counts}")
    expected_actual = 324 - sum(2 if diagnostic["stage"] == "group" else 1 for review in reviews for diagnostic in review["operation_diagnostics"])
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
        "schema_version": "n27phb-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(review["review_sha256"] for review in reviews),
        "observed_counts": counts, "planned_scientific_calls": 324,
        "model_calibration_calls": 0, "all_record_hashes_recomputed": True,
        "duplicate_provider_call_ids": False,
        "frozen_trees_unchanged": all(ce.sha256(ce._tree_hashes(target / folder)) == expected for folder, expected in freeze["tree_hashes"].items()),
        "frozen_private_qualification_unchanged": ce.sha256(ce._tree_hashes(target / "qualification-private")) == freeze["private_qualification_tree_sha256"],
        "provider_receipts_preserved": all(review["initial_receipt"] and review["terminal_receipt"] for review in reviews),
        "invalid_operations_received_no_extra_call": True, "repair_count": 0,
        "attempt_052_preserved": all(_file_sha(repo_root / ATTEMPT_052 / path) == expected for path, expected in ATTEMPT_052_HASHES.items()),
        "full_experiment_completed": True,
    }
    if not all(replay[key] for key in ("frozen_trees_unchanged", "frozen_private_qualification_unchanged", "provider_receipts_preserved", "attempt_052_preserved")):
        raise RuntimeError("replay reconciliation failed")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(target / "replay.json", replay)
    terminal = {
        "schema_version": "n27phb-terminal-1", "status": "completed_full_experiment_and_analysis",
        "model_calibration_call_count": 0, "instance_count": 9,
        "fresh_job_capture_count": 36, "package_count": 54, "review_count": 162,
        "planned_scientific_provider_calls": 324,
        "actual_scientific_provider_calls": counts["logical_provider_calls"],
        "rejected_operation_count": counts["rejected_operations"], "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"], "replay_sha256": replay["replay_sha256"],
        "full_experiment_completed": True,
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
            "schema_version": "n27phb-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27phb_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
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
            return 0 if _json(path).get("status") == "completed_full_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N27PHB experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
