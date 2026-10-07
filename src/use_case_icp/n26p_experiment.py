"""N26P append-only implementation pilot for the reusable N26 foundation."""

from __future__ import annotations

import argparse
import ast
import csv
from copy import deepcopy
import json
from itertools import product
import math
from pathlib import Path
import random
import re
import time
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator
import tiktoken

from . import corrected_experiment as ce
from . import n25_experiment as n25
from .fault_preflight_v2 import validate_strict_provider_schema
from .n05_program import _parse_output, _pipeline_payload, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-043")
ATTEMPT_042 = Path("outputs/fault-experiments-v2-2-n10/attempt-042")
TASK = Path("instructions_between_agent_types/developer/current/N26P_small_implementation_pilot.email.md")
TASK_SHA256 = "sha256:4c7c5c2c8b4ca494a4dc064a4858d735afa11d64deef4eddbd26cb34334975fa"
FULL_TASK = Path("instructions_between_agent_types/developer/current/N26_corrected_data_dependent_four_stage_experiment.email.md")
FULL_TASK_SHA256 = "sha256:9412c7a0d26b53bbb741bf0b65c629f40d171d20971c3f5b707a7893759ec8d8"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N26P_small_implementation_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:92e916158ec2646d3f9d495f9f8181db7f2a2f4548e6f909a32d8e89bb3d3861"
CORRECTION_TASK = Path("instructions_between_agent_types/developer/current/N26PA_control_denominator_correction_and_resume.email.md")
CORRECTION_TASK_SHA256 = "sha256:63a1e391d17dbd08ef8e490bb469f33c4b31c2714792e6c0eb7a435e976a08c5"
CORRECTION_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N26PA_control_denominator_correction_and_resume_authorization.json")
CORRECTION_AUTHORITY_SHA256 = "sha256:f7017c01a98911aa4c80aed4f28eeaee51873ba6e6cf4045008a38e557cdd687"
CORRECTION_RECORD = Path("qualification/post-freeze-control-denominator-correction.json")
PROMPT = Path("prompts/v2_2/n26p_four_stage_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n26p_final.schema.json")
REQUIRED_SCHEMA = Path("schemas/v2_2/n26p_expand_required.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n26p_reconsider.schema.json")
UPSTREAM_SOURCE = Path("src/use_case_icp/n26_upstream_demand_provenance.py")
DOWNSTREAM_SOURCE = Path("src/use_case_icp/n26_downstream_coverage_priority.py")
JOB3_SOURCE = n25.JOB3_SOURCE
JOB4_SOURCE = n25.JOB4_SOURCE

UPSTREAM = n25.UPSTREAM
DOWNSTREAM = n25.DOWNSTREAM
JOB3 = n25.JOB3
JOB4 = n25.JOB4
JOB_ORDER = n25.JOB_ORDER
FUNCTIONS = n25.FUNCTIONS
DELIVERY_RULES = n25.DELIVERY_RULES
MODES = n25.MODES
MODE_NAMES = n25.MODE_NAMES
GRAPH_MODES = n25.GRAPH_MODES
ALL_INSTANCES = (
    "T1_threshold_inclusive_boundary", "T2_threshold_wrong_measure",
    "T3_threshold_aggregation_max", "T4_threshold_wrong_segment",
    "F1_fallback_identity_loss", "N1_capacity_precedence",
    "N2_duplicate_survivor", "P1_secondary_tie_break",
    "P2_premature_score_bucketing", "P3_qualifying_rate_denominator",
    "C0", "C1", "C2",
)
PILOT_INSTANCES = (
    "T1_threshold_inclusive_boundary", "N2_duplicate_survivor",
    "P1_secondary_tie_break", "C0", "C1",
)
PILOT_CELLS = (
    "E01-S1-B0", "E02-S0-B0", "E02-S1-B0", "E02-S1-B1",
    "E03-S1-B0", "E04-S1-B0", "E05-S1-B0", "E06-S1-B0",
    "E07-S0-B0", "E07-S1-B0", "E07-S1-B1", "E08-S0-B0",
    "E08-S1-B0", "E09-S1-B0", "E10-S1-B0", "E11-S1-B0",
)
TRUTH = {
    **{key: "select_demand" for key in (
        "T1_threshold_inclusive_boundary", "T2_threshold_wrong_measure",
        "T3_threshold_aggregation_max", "T4_threshold_wrong_segment",
        "F1_fallback_identity_loss", "P3_qualifying_rate_denominator",
    )},
    "N1_capacity_precedence": "normalize",
    "N2_duplicate_survivor": "normalize",
    "P1_secondary_tie_break": "assemble_provenance",
    "P2_premature_score_bucketing": "assemble_provenance",
    "C0": None, "C1": None, "C2": None,
}
MUTATIONS = {
    "T1_threshold_inclusive_boundary": ("threshold_value >= threshold", "threshold_value > threshold"),
    "T2_threshold_wrong_measure": ("threshold_value = aggregate_demand", "threshold_value = representative_weight"),
    "T3_threshold_aggregation_max": ('group["demand_score"].sum()', 'group["demand_score"].max()'),
    "T4_threshold_wrong_segment": ('policy["segment_thresholds"].get(segment, policy["default_threshold"])', 'policy["default_threshold"]'),
    "F1_fallback_identity_loss": ('record_id in policy["fallback_record_ids"]', 'representative_source_id in policy["fallback_record_ids"]'),
    "N1_capacity_precedence": ("(fallbacks + primaries)", "(primaries + fallbacks)"),
    "N2_duplicate_survivor": ("ascending=[False, True]", "ascending=[True, True]"),
    "P1_secondary_tie_break": ('-float(row["source_weight"])', 'float(row["source_weight"])'),
    "P2_premature_score_bucketing": ('round(float(row["demand_score"]), precision)', 'round(float(row["demand_score"]), 1)'),
    "P3_qualifying_rate_denominator": ("len(qualifying_sources) / len(distinct_sources)", "len(qualifying_sources) / len(group)"),
}
PROTECTED = {
    "src/use_case_icp/n05_runner.py": "sha256:25ba9749a212aef9d8a23513e4e1014985291708a0517e6d20f1f4469ed85bee",
    "src/use_case_icp/n07_program.py": "sha256:d338cc22ce881b2c9bae46a105f227b9aae5f563fde17b177a3435286beec34f",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
    "prompts/v2_2/fault_review.md": "sha256:1a59763cce79f307b0b86501ee4d272726c6df793d7827a9c155b8b8fd22ea44",
    "schemas/v2_2/fault_review_receipt.schema.json": "sha256:3cebce8ef00c20f8316a4ed0998fd53ebff9e62a9471b7b635305ad7a5cbd075",
}
ATTEMPT_042_HASHES = {
    "experiment-freeze.json": "sha256:03d61ee15f9f87ba3db318db585450ce4570a9ac5bfd17071c23f715f8572e71",
    "replay.json": "sha256:7796dd9fa0bde8153bab96f344ddaa5f9d24c15e869ed7c1f27202e7b6954614",
    "terminal-state.json": "sha256:9352cd69d341c1c81dc08e26a66d9f0b0ccb5b9654dda560948f9edac613061c",
}

BEHAVIOURAL_SPECIFICATION = """The supplied demand input and policy are stipulated. Job 1 groups observations by canonical record and segment, sums demand, computes the qualifying-source rate over distinct source IDs, applies segment thresholds inclusively, preserves listed fallbacks, chooses the highest-source-weight duplicate, protects fallbacks while filling retained capacity, and ranks provenance by aggregate demand descending, source weight descending, then record ID at configured precision. Job 2 maps capabilities, prioritizes unsupported needs before supported needs and then by upstream rank, and recommends its first priority. Job 3 preserves every priority, assigning primary only to priority rank 1, gap education to unsupported items, capability reinforcement otherwise, and evidence review only when upstream rank is non-positive. Job 4 maps the stipulated delivery rules, schedules every item exactly once, and preserves focus, decision, order and counts."""
TASK_TEXT = "Starting from the observed Job-4 campaign-activation result, decide whether the four-job execution contains a behaviorally significant fault. If it does, identify the earliest responsible job and, when the supplied evidence supports it, the exact responsible function."


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    create_bytes_exclusive(path, value.encode())


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for path, digest in ((TASK, TASK_SHA256), (FULL_TASK, FULL_TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / path).read_bytes()) != digest:
            raise ValueError(f"N26P authority input changed: {path}")
    for relative, digest in PROTECTED.items():
        if ce.sha256((repo_root / relative).read_bytes()) != digest:
            raise ValueError(f"N26P protected surface changed: {relative}")
    source = repo_root / ATTEMPT_042
    for relative, digest in ATTEMPT_042_HASHES.items():
        if ce.sha256((source / relative).read_bytes()) != digest:
            raise ValueError(f"Attempt 042 preservation binding changed: {relative}")
    return {"task": TASK_SHA256, "full_task": FULL_TASK_SHA256, "authority": AUTHORITY_SHA256}


def _observations() -> list[dict[str, Any]]:
    rows = []
    def add(record_id: str, need: str, segment: str, scores: list[float], weights: list[float], sources: list[str], qualified: list[bool], needs: list[str] | None = None) -> None:
        labels = needs or [need] * len(scores)
        for index, values in enumerate(zip(scores, weights, sources, qualified, labels), 1):
            score, weight, source, is_qualified, label = values
            rows.append({"observation_id": f"{record_id}-o{index}", "record_id": record_id, "need": label, "segment": segment, "demand_score": score, "source_weight": weight, "source_id": source, "qualified": is_qualified})
    add("n26-r01", "account intelligence", "enterprise", [6.0], [7.2], ["src-01"], [True])
    add("n26-r02", "regional reporting", "midmarket", [5.0], [5.4], ["src-02"], [True])
    add("n26-r03", "buyer journey analytics", "enterprise", [3.01, 3.03], [6.2, 5.8], ["src-03a", "src-03b"], [True, True])
    add("n26-r04", "partner attribution", "regulated", [6.2], [6.0], ["src-04"], [True])
    add("n26-r05", "pipeline automation", "midmarket", [2.0, 1.8, 1.74], [5.6, 4.9, 4.1], ["src-05a", "src-05a", "src-05b"], [True, True, False], ["pipeline automation", "pipeline automation", "manual pipeline tracking"])
    add("n26-r06", "territory planning", "enterprise", [7.0], [5.9], ["src-06"], [True])
    add("n26-r07", "conversion forecasting", "enterprise", [7.0], [7.5], ["src-07"], [True])
    add("n26-r08", "content measurement", "midmarket", [5.2], [5.2], ["src-08"], [True])
    add("n26-r09", "event follow-up", "smb", [1.0], [2.0], ["src-09"], [False])
    add("n26-r10", "community nurture", "smb", [1.2], [2.2], ["n26-r10"], [False])
    return rows


def _base_input() -> dict[str, Any]:
    return {
        "scenario_id": "four-stage-campaign",
        "corpus": _observations(),
        "selection_policy": {
            "segment_thresholds": {"enterprise": 6.0, "midmarket": 5.0, "regulated": 6.5, "smb": 4.0},
            "default_threshold": 5.0,
            "minimum_qualifying_source_rate": 0.5,
            "fallback_record_ids": ["n26-r09", "n26-r10"],
            "retained_capacity": 7,
            "aggregation_rule": "sum",
            "duplicate_survivor_rule": "highest_source_weight",
            "score_precision": 2,
            "ranking_tie_break": ["aggregate_demand_desc", "source_weight_desc", "record_id"],
        },
    }


def input_for(instance_id: str) -> dict[str, Any]:
    value = _base_input()
    if instance_id == "C1":
        value["scenario_id"] = "regional-demand-a"
        value["selection_policy"]["segment_thresholds"] = {"enterprise": 5.8, "midmarket": 5.1, "regulated": 6.0, "smb": 4.2}
        value["selection_policy"]["fallback_record_ids"] = ["n26-r08", "n26-r10"]
    elif instance_id == "C2":
        value["scenario_id"] = "regional-demand-b"
        value["selection_policy"]["score_precision"] = 3
        for row in value["corpus"]:
            if row["record_id"] == "n26-r03" and row["observation_id"].endswith("o2"):
                row["demand_score"] = 3.04
            if row["record_id"] == "n26-r05" and row["observation_id"].endswith("o1"):
                row["source_weight"] = 5.75
            if row["record_id"] == "n26-r06":
                row["source_weight"] = 7.8
    return value


CAPABILITIES = [
    {"capability_id": f"cap-{index:02d}", "need": need}
    for index, need in enumerate((
        "account intelligence", "regional reporting", "buyer journey analytics",
        "partner attribution", "pipeline automation", "territory planning",
        "conversion forecasting", "content measurement", "community nurture",
    ), 1)
]


def _mutant_source(clean: str, instance_id: str) -> tuple[str, dict[str, Any] | None]:
    if instance_id.startswith("C"):
        return clean, None
    old, new = MUTATIONS[instance_id]
    if clean.count(old) != 1:
        raise ValueError(f"N26 mutation site is not unique: {instance_id}")
    mutated = clean.replace(old, new, 1)
    ast.parse(mutated)
    start = clean.index(old)
    line = clean.count("\n", 0, start) + 1
    column = start - clean.rfind("\n", 0, start) - 1
    record = {
        "fault_id": instance_id,
        "job_id": UPSTREAM,
        "qualified_function_name": TRUTH[instance_id],
        "operator": instance_id.split("_", 1)[1],
        "original_snippet": old,
        "mutant_snippet": new,
        "original_span": {"start_line": line, "end_line": line, "start_column": column, "end_column": column + len(old)},
        "candidate_count": 1,
        "exactly_one_source_site_changed": True,
        "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return mutated, record


def _pipeline(repo_root: Path, job_id: str, upstream_source: str) -> GeneratedPipeline:
    if job_id == UPSTREAM:
        source = upstream_source
        generated = "generated/protocol_2_2/n26_upstream_demand_provenance.py"
    elif job_id == DOWNSTREAM:
        source = (repo_root / DOWNSTREAM_SOURCE).read_text()
        generated = "generated/protocol_2_2/n26_downstream_coverage_priority.py"
    else:
        return n25._pipeline(repo_root, job_id)
    roles = {
        UPSTREAM: (
            ("select_demand", "Select policy-qualified and fallback demand observations.", ["corpus", "selection_policy"], ["selected observations"]),
            ("normalize", "Choose duplicate survivors and enforce fallback-protected capacity.", ["selected observations", "selection_policy"], ["needs"]),
            ("assemble_provenance", "Rank coherent provenance using configured precision and tie-breaks.", ["needs", "selection_policy"], ["evidence_sources"]),
        ),
        DOWNSTREAM: (
            ("map_coverage", "Map each received need to capability coverage.", ["needs", "capabilities"], ["coverage"]),
            ("prioritize", "Prioritize unsupported needs before supported needs and then by upstream rank.", ["coverage", "evidence_sources"], ["priorities"]),
            ("synthesize", "Preserve priorities and recommend the first priority.", ["priorities"], ["priorities", "recommendation"]),
        ),
    }
    pipeline = GeneratedPipeline(
        entry_file=generated,
        files=[GeneratedFile(generated, source)],
        review_boundaries=[{
            "boundary_id": f"rb_n26_{job_id}_{name}", "function_name": name,
            "qualified_function_name": name, "source_path": generated,
            "role": role, "expected_inputs": inputs, "expected_outputs": outputs,
            "semantic_stage": job_id,
        } for name, role, inputs, outputs in roles[job_id]],
    )
    pipeline.validate()
    return pipeline


def _job_input(job_id: str, prior: Mapping[str, Any] | None, root_input: Mapping[str, Any]) -> dict[str, Any]:
    if job_id == UPSTREAM:
        return deepcopy(dict(root_input))
    if job_id == DOWNSTREAM:
        return {"needs": deepcopy(prior["needs"]), "evidence_sources": deepcopy(prior["evidence_sources"]), "capabilities": deepcopy(CAPABILITIES)}
    if job_id == JOB3:
        return {key: deepcopy(prior[key]) for key in ("coverage", "priorities", "recommendation", "metadata")}
    return {"campaign_portfolio": deepcopy(prior["campaign_portfolio"]), "metadata": deepcopy(prior["metadata"]), "delivery_rules": deepcopy(DELIVERY_RULES)}


def _check_output(repo_root: Path, job_id: str, output: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    if job_id == UPSTREAM:
        if set(output) != {"needs", "evidence_sources", "metadata"} or not output["needs"] or len(output["needs"]) != len(output["evidence_sources"]):
            raise ValueError("N26 Job 1 output contract failed")
        if len({row["record_id"] for row in output["needs"]}) != len(output["needs"]):
            raise ValueError("N26 Job 1 retained duplicate canonical records")
    elif job_id == DOWNSTREAM:
        if len(output["coverage"]) != len(runtime_input["needs"]) or len(output["priorities"]) != len(runtime_input["needs"]):
            raise ValueError("N26 Job 2 did not preserve every need")
        ordered = output["priorities"]
        if ordered != sorted(ordered, key=lambda row: row["priority_rank"]):
            raise ValueError("N26 Job 2 priority ranks are not ordered")
    elif job_id == JOB3:
        n25._check_job3(repo_root, output, runtime_input)
    else:
        n25._check_job4(repo_root, output, runtime_input)


def _capture_instance(repo_root: Path, target: Path, instance_id: str, source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pipelines = {job: _pipeline(repo_root, job, source) for job in JOB_ORDER}
    jobs = {}
    handoffs = []
    prior = None
    root_input = input_for(instance_id)
    for job_index, job_id in enumerate(JOB_ORDER):
        runtime_input = _job_input(job_id, prior, root_input)
        branch = target / "capture-branches" / instance_id / f"canonical-v2-job-{job_index + 1}"
        execution = n25._existing_execution(branch, job_id)
        if execution is None:
            materialize_opaque_branch(branch, allowlist={}, manifest_identity={"purpose": "n26p-canonical-capture", "instance": instance_id, "job": job_id})
            copy_etiq_worker_runtime(branch, repo_root / "src")
            execution = execute_pipeline_in_branch(branch, repo_root=repo_root, job_id=job_id, pipeline=pipelines[job_id], runtime_input=runtime_input, run_index=ALL_INSTANCES.index(instance_id), stage=f"n26p-{instance_id}-{job_index + 1}")
        output = _parse_output(execution)
        _check_output(repo_root, job_id, output, runtime_input)
        realization = n25._realization(execution, pipelines[job_id], job_id)
        jobs[job_id] = n25._job_record(execution, output, realization)
        if prior is not None:
            names = ("needs", "evidence_sources") if job_id == DOWNSTREAM else (("coverage", "priorities", "recommendation", "metadata") if job_id == JOB3 else ("campaign_portfolio", "metadata"))
            producer = JOB_ORDER[job_index - 1]
            handoffs.extend(n25._handoff(name, producer, job_id, prior[name]) for name in names)
        prior = output
    capture = {
        "schema_version": "n26-four-job-capture-1",
        "capture_id": stable_id("rerun-capture", ["n26p", instance_id], 0),
        "instance_id": instance_id, "job_ids": list(JOB_ORDER), "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": {job: ce.sha256(_pipeline_payload(pipelines[job])) for job in JOB_ORDER},
        "canonical": True, "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    n25._verify_four_capture(capture)
    source_bundle = [{"job_id": job, "files": [{"path": pipelines[job].files[0].path, "content": pipelines[job].files[0].content}]} for job in JOB_ORDER]
    return capture, source_bundle


def _catalogue(capture: Mapping[str, Any]) -> dict[str, Any]:
    value = n25._build_catalogue(capture)
    value["schema_version"] = "n26-four-job-catalogue-1"
    value.pop("catalogue_sha256", None)
    value["catalogue_sha256"] = ce.sha256(value)
    ce.verify_catalogue(value)
    return value


def _load_prepared(target: Path) -> dict[str, Any]:
    collections = {
        name: {path.stem: _json(path) for path in sorted((target / folder).glob("*.json"))}
        for name, folder in (("captures", "captures"), ("catalogues", "catalogues"), ("instances", "instances"))
    }
    indexes = {path.stem: _json(path) for path in sorted((target / "group-index-final").glob("*.json"))}
    if not indexes and set(collections["catalogues"]) == set(ALL_INSTANCES):
        for instance_id, catalogue in collections["catalogues"].items():
            _, index = build_compact_graph(catalogue)
            ce._write_immutable(target / "group-index-final" / f"{instance_id}.json", index)
            indexes[instance_id] = index
    collections["indexes"] = indexes
    collections["source_bundles"] = {path.stem: _json(path)["source_bundle"] for path in sorted((target / "source-bundles").glob("*.json"))}
    if any(set(values) != set(ALL_INSTANCES) for values in collections.values()):
        raise ValueError("N26 reusable foundation is partial")
    for instance_id in ALL_INSTANCES:
        n25._verify_four_capture(collections["captures"][instance_id])
        ce.verify_catalogue(collections["catalogues"][instance_id])
        ce._verified_self_hash(collections["instances"][instance_id], "instance_sha256")
        ce._verified_self_hash(collections["indexes"][instance_id], "index_sha256")
    return collections


def _business_signature(output: Mapping[str, Any]) -> dict[str, Any]:
    plan = output["activation_plan"]
    actions = [*plan["launch_actions"], *plan["evidence_review_actions"]]
    return {
        "recommended_focus": plan["recommended_focus"],
        "recommended_decision": plan["recommended_decision"],
        "action_order": [row["record_id"] for row in actions],
        "action_membership": sorted(row["record_id"] for row in actions),
        "action_values": [{key: row.get(key) for key in ("record_id", "need", "upstream_rank", "evidence_status")} for row in actions],
        "counts": deepcopy(output["metadata"]),
    }


def _group_size_class(size: int) -> str:
    if size <= 4:
        return "small"
    if size <= 12:
        return "medium"
    return "large"


def _top_level_function_nodes(catalogue: Mapping[str, Any], job_id: str) -> dict[str, dict[str, Any]]:
    found = {}
    for node in catalogue["jobs"][job_id]["nodes"]:
        stack = ce.canonical_stack(node.get("func_stack", []))
        if len(stack) == 2 and stack[0] == "main":
            found.setdefault(stack[1].split(",", 1)[0], node)
    return found


def _direct_groups(catalogue: Mapping[str, Any], job_id: str, anchor: Mapping[str, Any]) -> list[tuple[dict[str, Any], list[str]]]:
    root = ce.canonical_stack(anchor.get("func_stack", []))
    prefixes = sorted({
        ce.canonical_stack(node.get("func_stack", []))
        for node in catalogue["jobs"][job_id]["nodes"]
        if len(ce.canonical_stack(node.get("func_stack", []))) == len(root) + 1
        and ce.canonical_stack(node.get("func_stack", []))[:len(root)] == root
    })
    groups = []
    for prefix in prefixes:
        nodes = [node for node in catalogue["jobs"][job_id]["nodes"] if ce.canonical_stack(node.get("func_stack", [])) == prefix]
        refs = {str(node["node_ref"]) for node in nodes}
        edges = [edge for edge in catalogue["jobs"][job_id]["relationships"] if str(edge["source_ref"]) in refs and str(edge["target_ref"]) in refs]
        descriptor = {
            "execution_group_id": f"grp-{ce.sha256([job_id, list(prefix)])[7:23]}",
            "job_id": job_id, "parent_node_ref": anchor["node_ref"],
            "func_stack": list(prefix), "node_count": len(nodes),
            "relationship_count": len(edges),
            "size_class": _group_size_class(len(nodes)),
            "has_deeper_stack": any(
                len(ce.canonical_stack(node.get("func_stack", []))) > len(prefix)
                and ce.canonical_stack(node.get("func_stack", []))[:len(prefix)] == prefix
                for node in catalogue["jobs"][job_id]["nodes"]
            ),
        }
        groups.append((descriptor, sorted(refs)))
    return groups


def build_compact_graph(catalogue: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    requested = {UPSTREAM: "select_demand", DOWNSTREAM: "prioritize", JOB3: "build_campaign_items", JOB4: "schedule_campaign_actions"}
    anchors = []
    descriptors = []
    index = {}
    for job_id in JOB_ORDER:
        available = _top_level_function_nodes(catalogue, job_id)
        anchor = available.get(requested[job_id])
        if anchor is None:
            raise ValueError(f"N26 compact raw-stack anchor missing: {job_id}")
        anchors.append(n25._tag(anchor, job_id))
        for descriptor, refs in _direct_groups(catalogue, job_id, anchor):
            descriptors.append(descriptor)
            index[descriptor["execution_group_id"]] = {"descriptor": deepcopy(descriptor), "node_refs": refs}
    anchor_refs = {str(node["node_ref"]) for node in anchors}
    relationships = [
        n25._tag(edge, job_id)
        for job_id in JOB_ORDER for edge in catalogue["jobs"][job_id]["relationships"]
        if str(edge["source_ref"]) in anchor_refs and str(edge["target_ref"]) in anchor_refs
    ]
    if len(anchors) != 4 or not descriptors:
        raise ValueError("N26 compact projection lacks four structural anchors or nested groups")
    projection = {
        "job_evidence_order": list(reversed(JOB_ORDER)), "nodes": anchors,
        "relationships": relationships, "collapsed_execution_groups": descriptors,
        "disclosed_execution_groups": [],
        "selection_rule": "first raw top-level function execution in each ordered job; semantic boundaries unused",
    }
    projection["projection_sha256"] = ce.sha256(projection)
    group_index = {"schema_version": "n26-group-index-1", "groups": index}
    group_index["index_sha256"] = ce.sha256(group_index)
    return projection, group_index


def _node_stratum(node: Mapping[str, Any], group_descriptors: list[Mapping[str, Any]]) -> dict[str, Any]:
    source_chars = sum(len(str(node.get(key, ""))) for key in ("source", "source_text"))
    artifact = node.get("artifact_content")
    return {
        "job_id": node["job_id"], "node_type": node.get("state_type", node.get("node_type")),
        "stack_depth": len(ce.canonical_stack(node.get("func_stack", []))),
        "source_size_class": "none" if source_chars == 0 else ("small" if source_chars < 4000 else "large"),
        "artifact_kind": type(artifact).__name__,
        "group_count": len(group_descriptors),
        "group_size_classes": sorted(value["size_class"] for value in group_descriptors),
    }


def random_structural_graph(catalogue: Mapping[str, Any], compact: Mapping[str, Any], seed: int) -> dict[str, Any]:
    generator = random.Random(seed)
    compact_by_job = {node["job_id"]: node for node in compact["nodes"]}
    options = []
    for job_id in JOB_ORDER:
        target = compact_by_job[job_id]
        target_groups = [value for value in compact["collapsed_execution_groups"] if value["parent_node_ref"] == target["node_ref"]]
        target_stratum = _node_stratum(target, target_groups)
        candidates = []
        for candidate in _top_level_function_nodes(catalogue, job_id).values():
            if candidate["node_ref"] == target["node_ref"]:
                continue
            candidate_tagged = n25._tag(candidate, job_id)
            candidate_groups = [value[0] for value in _direct_groups(catalogue, job_id, candidate)]
            if _node_stratum(candidate_tagged, candidate_groups) == target_stratum:
                candidates.append((candidate_tagged, candidate_groups))
        if not candidates:
            raise ValueError(f"N26 Random Structural Matched has unmatched stratum: {job_id}/{target_stratum}")
        options.append((job_id, target, target_stratum, candidates))
    target_tokens = n25._token_count({key: compact[key] for key in ("nodes", "relationships", "collapsed_execution_groups")})
    qualifying = []
    for combination in product(*(entry[3] for entry in options)):
        candidate_nodes = [value[0] for value in combination]
        candidate_groups = [group for value in combination for group in value[1]]
        refs = {str(node["node_ref"]) for node in candidate_nodes}
        candidate_edges = [n25._tag(edge, job_id) for job_id in JOB_ORDER for edge in catalogue["jobs"][job_id]["relationships"] if str(edge["source_ref"]) in refs and str(edge["target_ref"]) in refs]
        observed = n25._token_count({"nodes": candidate_nodes, "relationships": candidate_edges, "collapsed_execution_groups": candidate_groups})
        if len(candidate_edges) == len(compact["relationships"]) and abs(observed - target_tokens) / max(1, target_tokens) <= 0.03:
            qualifying.append((candidate_nodes, candidate_edges, candidate_groups, observed, combination))
    if not qualifying:
        raise ValueError("N26 Random Structural Matched has no complete structural/token match")
    selected, relationships, descriptors, observed_tokens, selected_combination = qualifying[generator.randrange(len(qualifying))]
    diagnostics = [
        {"job_id": job_id, "target_node_ref": target["node_ref"], "selected_node_ref": chosen[0]["node_ref"], "stratum": stratum, "eligible_candidates": len(candidates)}
        for (job_id, target, stratum, candidates), chosen in zip(options, selected_combination)
    ]
    tolerance = abs(observed_tokens - target_tokens) / max(1, target_tokens)
    value = {
        "job_evidence_order": list(reversed(JOB_ORDER)), "nodes": selected,
        "relationships": relationships, "collapsed_execution_groups": descriptors,
        "disclosed_execution_groups": [],
        "random_structural_match": {
            "selection_rule": "seeded oracle-blind draw within the precommitted clean structural strata",
            "seed_commitment": ce.sha256(["n26-random-structural", seed]),
            "uses_truth_or_outcome": False, "diagnostics": diagnostics,
            "target_tokens": target_tokens, "observed_tokens": observed_tokens,
            "relative_token_difference": tolerance,
        },
    }
    value["projection_sha256"] = ce.sha256(value)
    return value


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N26P is authorized only for Attempt 043")
    authority = _verify_authority(repo_root)
    if (target / "captures").exists():
        return _load_prepared(target) | {"authority": authority}
    clean_source = (repo_root / UPSTREAM_SOURCE).read_text()
    captures = {}
    catalogues = {}
    instances = {}
    sources = {}
    indexes = {}
    for instance_id in ALL_INSTANCES:
        source, mutation = _mutant_source(clean_source, instance_id)
        capture, source_bundle = _capture_instance(repo_root, target, instance_id, source)
        catalogue = _catalogue(capture)
        compact, index = build_compact_graph(catalogue)
        instance = {
            "schema_version": "n26-instance-1", "instance_id": instance_id,
            "designation": "clean_control" if instance_id.startswith("C") else "upstream_fault",
            "truth_job": None if instance_id.startswith("C") else UPSTREAM,
            "truth_function": TRUTH[instance_id], "mutation": mutation,
            "input_sha256": ce.sha256(input_for(instance_id)),
            "capture_sha256": capture["capture_sha256"], "catalogue_sha256": catalogue["catalogue_sha256"],
            "source_sha256": deepcopy(capture["source_sha256"]),
        }
        instance["instance_sha256"] = ce.sha256(instance)
        ce._write_immutable(target / "captures" / f"{instance_id}.json", capture)
        ce._write_immutable(target / "catalogues" / f"{instance_id}.json", catalogue)
        ce._write_immutable(target / "source-bundles" / f"{instance_id}.json", {"source_bundle": source_bundle})
        ce._write_immutable(target / "instances" / f"{instance_id}.json", instance)
        ce._write_immutable(target / "group-index-final" / f"{instance_id}.json", index)
        for job_id in JOB_ORDER:
            record = {"schema_version": "n26-per-job-capture-1", "instance_id": instance_id, "job_id": job_id, "job_capture": deepcopy(capture["jobs"][job_id]), "job_capture_sha256": ce.sha256(capture["jobs"][job_id]), "source_sha256": capture["source_sha256"][job_id], "reuse_status": "fresh_execution"}
            record["record_sha256"] = ce.sha256(record)
            ce._write_immutable(target / "job-captures" / instance_id / f"{job_id}.json", record)
        captures[instance_id], catalogues[instance_id], instances[instance_id], sources[instance_id], indexes[instance_id] = capture, catalogue, instance, source_bundle, index
    clean_signature = _business_signature(captures["C0"]["jobs"][JOB4]["output"])
    mutant_signatures = {key: _business_signature(captures[key]["jobs"][JOB4]["output"]) for key in ALL_INSTANCES if not key.startswith("C")}
    hashes = {key: ce.sha256(value) for key, value in mutant_signatures.items()}
    if any(value == clean_signature for value in mutant_signatures.values()) or len(set(hashes.values())) != 10:
        raise ValueError("N26 mutant Job-4 outcomes are clean-equivalent or not pairwise distinct")
    nested = {}
    for instance_id in ALL_INSTANCES[:10]:
        truth = TRUTH[instance_id]
        legal = [value for value in indexes[instance_id]["groups"].values() if value["descriptor"]["job_id"] == UPSTREAM and truth in value["descriptor"]["func_stack"]]
        nested[instance_id] = {"legal_relevant_group_ids": [value["descriptor"]["execution_group_id"] for value in legal], "exact_mutation_or_immediate_state_hidden": bool(legal)}
    if sum(value["exact_mutation_or_immediate_state_hidden"] for value in nested.values()) < 6 or not nested["T1_threshold_inclusive_boundary"]["exact_mutation_or_immediate_state_hidden"]:
        raise ValueError("N26 exact nested-relevance qualification failed")
    ce._write_immutable(target / "foundation-qualification.json", {
        "schema_version": "n26-foundation-qualification-1", "status": "passed",
        "authority": authority, "all_instances": list(ALL_INSTANCES),
        "mutant_job4_hashes": hashes, "clean_job4_hash": ce.sha256(clean_signature),
        "pairwise_distinct_mutants": True, "clean_controls": ["C0", "C1", "C2"],
        "nested_relevance": nested, "nested_relevant_fault_count": sum(value["exact_mutation_or_immediate_state_hidden"] for value in nested.values()),
        "fresh_job_executions": 52, "capture_count": 13, "catalogue_count": 13,
    })
    return _load_prepared(target) | {"authority": authority}


def _base_package(catalogue: Mapping[str, Any], include_logs: bool) -> dict[str, Any]:
    return {
        "schema_version": "n26p-four-stage-review-package-1",
        "review_task": TASK_TEXT,
        "shared_behavioural_specification": BEHAVIOURAL_SPECIFICATION,
        "pipeline_topology": [
            {"job": f"job_{position}", "captured_job_id": job_id, "position": position, "observation_point": job_id == JOB4}
            for position, job_id in enumerate(JOB_ORDER, 1)
        ],
        "top_level_demand_input": deepcopy(catalogue["jobs"][UPSTREAM]["input"]),
        "capability_fixture": deepcopy(catalogue["jobs"][DOWNSTREAM]["input"]["capabilities"]),
        "delivery_rules_fixture": deepcopy(DELIVERY_RULES),
        "observed_job_4_execution": n25._execution_record(catalogue, JOB4, include_logs),
        "final_response_contract": {
            "fault_detected": "Boolean", "suspect_job": "job_1, job_2, job_3, job_4, or null",
            "suspect_function": "a function name visible in supplied evidence, or null",
            "explanation": "concise evidence-grounded reasoning",
            "cited_evidence": "exact evidence references or short visible excerpts",
        },
    }


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], graphs: Mapping[str, Mapping[str, Any]], mode: str, source: str, boundaries: str) -> dict[str, Any]:
    package = _base_package(catalogue, mode != "E01")
    if mode in {"E03", "E04"}:
        package["history"] = {"prior_task_records": []}
        if mode == "E04":
            for job_id in JOB_ORDER[:3]:
                record = n25._execution_record(catalogue, job_id, True)
                record["chronology"] = {"position": JOB_ORDER.index(job_id) + 1, "precedes": f"job_{JOB_ORDER.index(job_id) + 2}"}
                record["exact_outgoing_handoffs"] = [deepcopy(value) for value in catalogue["handoffs"] if value["upstream_job_id"] == job_id]
                package["history"]["prior_task_records"].append(record)
    if mode in GRAPH_MODES:
        if mode == "E05":
            evidence = n25.empty_graph()
        elif mode == "E06":
            evidence = {"job_evidence_order": deepcopy(graphs["compact"]["job_evidence_order"]), "nodes": deepcopy(graphs["compact"]["nodes"]), "relationships": [], "collapsed_execution_groups": [], "disclosed_execution_groups": []}
            evidence["projection_sha256"] = ce.sha256(evidence)
        elif mode in {"E07", "E08", "E09"}:
            evidence = deepcopy(graphs["compact"])
        elif mode == "E10":
            evidence = deepcopy(graphs["full"])
        else:
            evidence = deepcopy(graphs["random"])
            evidence.pop("random_structural_match", None)
            evidence.pop("projection_sha256", None)
            evidence["projection_sha256"] = ce.sha256(evidence)
        package["graph_review"] = {"framing": "Captured execution evidence may be used in the assessment.", "evidence": evidence}
    if source == "S1":
        package["separate_complete_source_bundle"] = deepcopy(source_bundle)
    if boundaries == "B1":
        package["semantic_declaration_bundle"] = n25._semantic_declarations(catalogue)
    if mode == "E08":
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {"operation": "expand_execution_group", "required_before_terminal": True, "maximum_completed_expansions": 1, "selection_must_be_model_selected": True}
    elif mode == "E09":
        package["interaction_contract"] = {"operation": "reconsider_same_evidence", "required_second_pass": True, "evidence_bytes_added": 0}
    return package


def schedule() -> dict[str, Any]:
    cells = []
    for instance_id in PILOT_INSTANCES:
        for cell_id in PILOT_CELLS:
            mode, source, boundaries = cell_id.split("-")
            cells.append({
                "instance_id": instance_id, "cell_id": cell_id, "mode": mode,
                "mode_name": MODE_NAMES[mode], "source_setting": source,
                "declaration_setting": boundaries,
                "branch_id": f"brn-{ce.sha256(['n26p', instance_id, cell_id])[7:23]}",
            })
    reviews = []
    for repetition in (1, 2):
        order = PILOT_INSTANCES[repetition - 1:] + PILOT_INSTANCES[:repetition - 1]
        for block, instance_id in enumerate(order):
            values = [value for value in cells if value["instance_id"] == instance_id]
            rotation = (block + repetition) % len(values)
            for cell in values[rotation:] + values[:rotation]:
                reviews.append({
                    **cell, "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n26p', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if (len(cells), len(reviews), len({value["trial_id"] for value in reviews})) != (80, 160, 160):
        raise AssertionError("N26P pilot schedule changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _schema_for(mode: str, follow_up: bool = False) -> Path:
    if follow_up or mode not in {"E08", "E09"}:
        return FINAL_SCHEMA
    return REQUIRED_SCHEMA if mode == "E08" else RECONSIDER_SCHEMA


def validate_schemas(repo_root: Path) -> dict[str, str]:
    hashes = {}
    for relative in (FINAL_SCHEMA, REQUIRED_SCHEMA, RECONSIDER_SCHEMA):
        schema = _json(repo_root / relative)
        Draft202012Validator.check_schema(schema)
        validate_strict_provider_schema(schema, relative.as_posix())
        n25._validate_const_types(schema)
        hashes[relative.as_posix()] = ce.sha256((repo_root / relative).read_bytes())
    terminal = {"fault_detected": True, "suspect_job": "job_1", "suspect_function": "select_demand", "explanation": "evidence", "cited_evidence": []}
    witnesses = {
        FINAL_SCHEMA: terminal,
        REQUIRED_SCHEMA: {**terminal, "next_action": {"action": "expand_execution_group", "execution_group_id": "grp-example"}},
        RECONSIDER_SCHEMA: {**terminal, "next_action": {"action": "reconsider_same_evidence"}},
    }
    for relative, witness in witnesses.items():
        Draft202012Validator(_json(repo_root / relative)).validate(witness)
    return hashes


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    visible = ce.canonical_json(request).decode()
    forbidden_keys = ("instance_id", "cell_id", "source_setting", "declaration_setting", "branch_id", "trial_id", "repetition", "seed", "truth_job", "truth_function", "designation", "mutation", "oracle", "qualification", "clean_comparison")
    if any(f'"{key}"' in visible for key in forbidden_keys):
        raise ValueError("N26P rendered request leaks controller state")
    forbidden_values = tuple(ALL_INSTANCES) + ("clean_control", "upstream_fault")
    if any(value in visible for value in forbidden_values):
        raise ValueError("N26P rendered request leaks instance or designation")
    return request


def _package_records(attempt_root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = _json(path)
        package_path = attempt_root / manifest["reviewer_package_path"]
        if ce.sha256(package_path.read_bytes()) != manifest["reviewer_package_file_sha256"]:
            raise ValueError("N26P package file binding changed")
        record = _json(package_path)
        if ce._verified_self_hash(record, "package_sha256") != manifest["package_sha256"]:
            raise ValueError("N26P package logical binding changed")
        records.append(record)
    return records


def _diff_paths(left: Any, right: Any, prefix: str = "$") -> list[str]:
    return n25._diff_paths(left, right, prefix)


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in package.items() if key not in {"available_operations", "interaction_contract"}}


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by = {(value["controller_condition"]["instance_id"], value["controller_condition"]["cell_id"]): value["reviewer_package"] for value in records}
    specifications = (
        ("job4_logs", "E01-S1-B0", "E02-S1-B0", {"observed_job_4_execution"}, False),
        ("complete_source", "E02-S0-B0", "E02-S1-B0", {"separate_complete_source_bundle"}, False),
        ("boundaries", "E02-S1-B0", "E02-S1-B1", {"semantic_declaration_bundle"}, False),
        ("empty_history", "E02-S1-B0", "E03-S1-B0", {"history"}, False),
        ("full_history", "E03-S1-B0", "E04-S1-B0", {"history"}, False),
        ("empty_graph", "E02-S1-B0", "E05-S1-B0", {"graph_review"}, False),
        ("compact_nodes", "E05-S1-B0", "E06-S1-B0", {"graph_review"}, False),
        ("compact_structure", "E06-S1-B0", "E07-S1-B0", {"graph_review"}, False),
        ("adaptive_initial", "E07-S1-B0", "E08-S1-B0", set(), True),
        ("reconsider_initial", "E07-S1-B0", "E09-S1-B0", set(), True),
        ("full_graph", "E05-S1-B0", "E10-S1-B0", {"graph_review"}, False),
        ("random_structural", "E07-S1-B0", "E11-S1-B0", {"graph_review"}, False),
        ("compact_source", "E07-S0-B0", "E07-S1-B0", {"separate_complete_source_bundle"}, False),
        ("compact_boundaries", "E07-S1-B0", "E07-S1-B1", {"semantic_declaration_bundle"}, False),
    )
    rows = []
    for instance_id in PILOT_INSTANCES:
        for name, left_id, right_id, roots, initial in specifications:
            left, right = by[(instance_id, left_id)], by[(instance_id, right_id)]
            if initial:
                left, right = _initial_evidence(left), _initial_evidence(right)
            paths = _diff_paths(left, right)
            passed = all(path.split(".")[1] in roots for path in paths) and (bool(paths) or not roots)
            rows.append({"instance_id": instance_id, "invariant": name, "left": left_id, "right": right_id, "differing_paths": paths, "allowed_roots": sorted(roots), "passed": passed})
    if not all(row["passed"] for row in rows):
        raise ValueError(f"N26P paired isolation failed: {[row for row in rows if not row['passed']][:2]}")
    return rows


def qualify_packages(repo_root: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    schemas = validate_schemas(repo_root)
    if (len(records), len(design["review_trials"]), len(design["repair_traces"])) != (80, 160, 0):
        raise ValueError("N26P package or schedule count changed")
    if {value["instance_id"] for value in design["cells"]} != set(PILOT_INSTANCES):
        raise ValueError("N26P live instance subset changed")
    if any({value["cell_id"] for value in design["cells"] if value["instance_id"] == instance} != set(PILOT_CELLS) for instance in PILOT_INSTANCES):
        raise ValueError("N26P sixteen-cell panel changed")
    if sum(value["mode"] == "E08" for value in design["review_trials"]) != 20 or sum(value["mode"] == "E09" for value in design["review_trials"]) != 10:
        raise ValueError("N26P follow-up schedule changed")
    maximum_tokens = 0
    simulated = 0
    represented = set()
    for record in records:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        request = render_request(package)
        maximum_tokens = max(maximum_tokens, n25._token_count(request))
        represented.add(condition["mode"])
        Draft202012Validator(_json(repo_root / _schema_for(condition["mode"]))).validate(
            {"fault_detected": True, "suspect_job": "job_1", "suspect_function": "select_demand", "explanation": "visible evidence", "cited_evidence": [], **({"next_action": {"action": "expand_execution_group", "execution_group_id": package["graph_review"]["evidence"]["collapsed_execution_groups"][0]["execution_group_id"]}} if condition["mode"] == "E08" else ({"next_action": {"action": "reconsider_same_evidence"}} if condition["mode"] == "E09" else {}))}
        )
        if condition["mode"] == "E08":
            groups = package["graph_review"]["evidence"]["collapsed_execution_groups"]
            if not groups:
                raise ValueError("N26P Adaptive package has no legal group")
            expanded, event = n25.expand_execution_group(prepared["catalogues"][condition["instance_id"]], prepared["indexes"][condition["instance_id"]], package, groups[0]["execution_group_id"])
            if event["status"] != "completed" or len(expanded["graph_review"]["evidence"]["disclosed_execution_groups"]) != 1:
                raise ValueError("N26P Adaptive no-model disclosure failed")
            simulated += 1
        if condition["mode"] == "E09" and package["interaction_contract"]["evidence_bytes_added"] != 0:
            raise ValueError("N26P Reconsideration advertises added evidence")
    if represented != {mode for mode, _ in MODES}:
        raise ValueError("N26P does not exercise every evidence mode")
    pairwise = _pairwise_checks(records)
    foundation = _json(repo_root / ATTEMPT / "foundation-qualification.json")
    if foundation["status"] != "passed" or foundation["nested_relevant_fault_count"] < 6:
        raise ValueError("N26 reusable foundation qualification changed")
    return {
        "schema_version": "n26p-no-model-verification-1", "status": "passed", "model_calls": 0,
        "foundation_instances": 13, "qualified_faults": 10, "qualified_controls": 3,
        "fresh_job_executions": 52, "captures": 13, "catalogues": 13,
        "live_instances": 5, "cells_per_live_instance": 16, "packages": 80,
        "terminal_reviews": 160, "adaptive_followups": 20, "reconsideration_calls": 10,
        "planned_provider_calls": 190, "repairs": 0, "strict_schema_hashes": schemas,
        "pairwise_checks": len(pairwise), "no_model_adaptive_simulations": simulated,
        "maximum_estimated_input_tokens": maximum_tokens,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if existing:
        qualification = qualify_packages(repo_root, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    compact_graphs = {}
    for instance_id in ALL_INSTANCES:
        compact, index = build_compact_graph(prepared["catalogues"][instance_id])
        if index["index_sha256"] != prepared["indexes"][instance_id]["index_sha256"]:
            raise ValueError("N26 compact graph is not deterministic")
        compact_graphs[instance_id] = compact
    seed_by_template = {
        "C0": int(ce.sha256([prepared["captures"]["C0"]["capture_sha256"], "n26-random-structural"])[7:23], 16),
        "C1": int(ce.sha256([prepared["captures"]["C1"]["capture_sha256"], "n26-random-structural"])[7:23], 16),
        "C2": int(ce.sha256([prepared["captures"]["C2"]["capture_sha256"], "n26-random-structural"])[7:23], 16),
    }
    graphs = {}
    structural = {}
    for instance_id in ALL_INSTANCES:
        template = instance_id if instance_id in {"C1", "C2"} else "C0"
        random_graph = random_structural_graph(prepared["catalogues"][instance_id], compact_graphs[instance_id], seed_by_template[template])
        graphs[instance_id] = {"compact": compact_graphs[instance_id], "full": n25.full_graph(prepared["catalogues"][instance_id]), "random": random_graph}
        structural[instance_id] = deepcopy(random_graph["random_structural_match"])
        for kind, graph in graphs[instance_id].items():
            ce._write_immutable(target / "projections" / f"{instance_id}-{kind}.json", graph)
    ce._write_immutable(target / "qualification/random-structural-matches.json", {"schema_version": "n26-random-structural-1", "templates": {key: {"seed_commitment": ce.sha256(["n26-random-structural", value])} for key, value in seed_by_template.items()}, "instances": structural, "all_strata_matched": True, "token_tolerance": 0.03})
    records = []
    for condition in design["cells"]:
        instance_id = condition["instance_id"]
        package = build_package(prepared["catalogues"][instance_id], prepared["source_bundles"][instance_id], graphs[instance_id], condition["mode"], condition["source_setting"], condition["declaration_setting"])
        record = {
            "schema_version": "n26p-frozen-package-1", "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance_id]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance_id]["catalogue_sha256"],
            "source_bundle_file_sha256": ce.sha256((target / "source-bundles" / f"{instance_id}.json").read_bytes()),
            "group_index_file_sha256": ce.sha256((target / "group-index-final" / f"{instance_id}.json").read_bytes()),
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        branch = condition["branch_id"]
        path = target / "packages" / branch / "reviewer-package.json"
        ce._write_immutable(path, record)
        manifest = {"schema_version": "n26p-controller-manifest-1", "controller_condition": deepcopy(condition), "reviewer_package_path": path.relative_to(target).as_posix(), "reviewer_package_file_sha256": ce.sha256(path.read_bytes()), "package_sha256": record["package_sha256"]}
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, records, prepared, design)
    exposure = {record["controller_condition"]["branch_id"]: n25.exposure_manifest(record) for record in records}
    pairwise = {"schema_version": "n26p-pairwise-package-differences-1", "rows": _pairwise_checks(records), "all_passed": True}
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "package-exposure-manifest.json", {"schema_version": "n26p-exposure-manifest-1", "packages": exposure})
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {"schema_version": "n26p-review-design-1", "review_trials": design["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n26p-repair-design-1", "repair_traces": []})
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (Path("src/use_case_icp/n26p_experiment.py"), UPSTREAM_SOURCE, DOWNSTREAM_SOURCE, JOB3_SOURCE, JOB4_SOURCE, PROMPT, FINAL_SCHEMA, REQUIRED_SCHEMA, RECONSIDER_SCHEMA, Path("tests/test_n26p_experiment.py"))


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if (target / "experiment-freeze.json").exists():
        raise FileExistsError("N26P Attempt 043 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("N26P cannot freeze after reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("N26P focused tests must pass before freeze")
    freeze = {
        "schema_version": "n26p-experiment-freeze-1", "attempt": "043", "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "full_task": {"path": FULL_TASK.as_posix(), "sha256": FULL_TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "protected_hashes": deepcopy(PROTECTED), "attempt_042_hashes": deepcopy(ATTEMPT_042_HASHES),
        "foundation_qualification_file_sha256": ce.sha256((target / "foundation-qualification.json").read_bytes()),
        "random_structural_file_sha256": ce.sha256((target / "qualification/random-structural-matches.json").read_bytes()),
        "capture_hashes": {key: built["prepared"]["captures"][key]["capture_sha256"] for key in ALL_INSTANCES},
        "catalogue_hashes": {key: built["prepared"]["catalogues"][key]["catalogue_sha256"] for key in ALL_INSTANCES},
        "instance_hashes": {key: built["prepared"]["instances"][key]["instance_sha256"] for key in ALL_INSTANCES},
        "capture_branch_tree_sha256": ce.sha256(ce._tree_hashes(target / "capture-branches")),
        "job_capture_tree_sha256": ce.sha256(ce._tree_hashes(target / "job-captures")),
        "projection_tree_sha256": ce.sha256(ce._tree_hashes(target / "projections")),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(target / "controller-manifests")),
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "no_model_verification_file_sha256": ce.sha256((target / "qualification/no-model-verification.json").read_bytes()),
        "focused_test_results_file_sha256": ce.sha256(focused.read_bytes()),
        "expected_counts": {"foundation_faults": 10, "foundation_controls": 3, "fresh_job_executions": 52, "live_instances": 5, "packages": 80, "reviews": 160, "adaptive_followups": 20, "reconsiderations": 10, "provider_calls": 190, "repairs": 0},
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "pilot_results_confirmatory_reuse_permitted": False, "experimental_review_records_at_freeze": 0,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path = target / "experiment-freeze.json"
    ce._write_immutable(path, freeze)
    return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _verify_authority(repo_root)
    freeze = _json(target / "experiment-freeze.json")
    digest = ce._verified_self_hash(freeze, "freeze_sha256")
    correction = _verify_post_freeze_correction(repo_root, target, freeze)
    for relative, expected in freeze["code_hashes"].items():
        actual = ce.sha256((repo_root / relative).read_bytes())
        if actual != expected and correction["new_code_hashes"].get(relative) != actual:
            raise ValueError(f"N26P frozen code changed: {relative}")
    built = build_attempt(repo_root, target)
    checks = {
        "capture-branches": "capture_branch_tree_sha256", "job-captures": "job_capture_tree_sha256",
        "projections": "projection_tree_sha256", "packages": "package_tree_sha256",
        "controller-manifests": "controller_manifest_tree_sha256",
    }
    for folder, key in checks.items():
        if ce.sha256(ce._tree_hashes(target / folder)) != freeze[key]:
            raise ValueError(f"N26P frozen tree changed: {folder}")
    if sorted(record["package_sha256"] for record in built["records"]) != freeze["package_hashes"] or ce.sha256(built["design"]["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("N26P package or schedule hashes changed")
    return {"status": "verified", "freeze_sha256": digest, "correction_sha256": correction["record_sha256"], "foundation_instances": 13, "packages": 80, "reviews": 160, "repairs": 0, "qualification": built["qualification"], "synthetic_control_denominator": correction["synthetic_control_denominator"]}


def _verify_post_freeze_correction(repo_root: Path, target: Path, freeze: Mapping[str, Any]) -> dict[str, Any]:
    record = _json(target / CORRECTION_RECORD)
    ce._verified_self_hash(record, "record_sha256")
    if record.get("schema_version") != "n26pa-post-freeze-correction-1" or record.get("status") != "authorized_correction_applied_before_live":
        raise ValueError("N26PA correction record status changed")
    expected_old = 'controls = [row for row in rows if row["designation"] == "' + 'clean_control"]'
    expected_new = 'controls = [row for row in rows if row["designation"] == "' + 'matched_clean_control"]'
    if record["task"] != {"path": CORRECTION_TASK.as_posix(), "sha256": CORRECTION_TASK_SHA256}:
        raise ValueError("N26PA correction task binding changed")
    if record["authority"] != {"path": CORRECTION_AUTHORITY.as_posix(), "sha256": CORRECTION_AUTHORITY_SHA256}:
        raise ValueError("N26PA correction authority binding changed")
    for path, expected in ((CORRECTION_TASK, CORRECTION_TASK_SHA256), (CORRECTION_AUTHORITY, CORRECTION_AUTHORITY_SHA256)):
        if ce.sha256((repo_root / path).read_bytes()) != expected:
            raise ValueError(f"N26PA authority input changed: {path}")
    if record["original_freeze"] != {
        "file_sha256": ce.sha256((target / "experiment-freeze.json").read_bytes()),
        "logical_sha256": freeze["freeze_sha256"],
    }:
        raise ValueError("N26PA original freeze binding changed")
    allowed = {"src/use_case_icp/n26p_experiment.py", "tests/test_n26p_experiment.py"}
    if set(record["old_code_hashes"]) != allowed or set(record["new_code_hashes"]) != allowed:
        raise ValueError("N26PA changed-file allowlist changed")
    for relative in allowed:
        if record["old_code_hashes"][relative] != freeze["code_hashes"][relative]:
            raise ValueError(f"N26PA old code hash changed: {relative}")
        if record["new_code_hashes"][relative] != ce.sha256((repo_root / relative).read_bytes()):
            raise ValueError(f"N26PA new code hash changed: {relative}")
    unchanged_code = {key: value for key, value in freeze["code_hashes"].items() if key not in allowed}
    if record["unchanged_code_hashes"] != unchanged_code:
        raise ValueError("N26PA unchanged frozen code bindings changed")
    for relative, expected in unchanged_code.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N26PA unauthorized frozen code change: {relative}")
    if record["protected_hashes"] != PROTECTED:
        raise ValueError("N26PA protected bindings changed")
    for relative, expected in PROTECTED.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N26PA protected surface changed: {relative}")
    predicate = record["predicate_correction"]
    source = (repo_root / "src/use_case_icp/n26p_experiment.py").read_text()
    if predicate != {"old": expected_old, "new": expected_new, "old_occurrences_after": 0, "new_occurrences_after": 1}:
        raise ValueError("N26PA predicate declaration changed")
    if source.count(expected_old) != 0 or source.count(expected_new) != 1:
        raise ValueError("N26PA predicate occurrence check failed")
    tree_bindings = {
        "package_tree_sha256": freeze["package_tree_sha256"],
        "controller_manifest_tree_sha256": freeze["controller_manifest_tree_sha256"],
        "projection_tree_sha256": freeze["projection_tree_sha256"],
        "capture_branch_tree_sha256": freeze["capture_branch_tree_sha256"],
        "job_capture_tree_sha256": freeze["job_capture_tree_sha256"],
    }
    if record["unchanged_tree_hashes"] != tree_bindings:
        raise ValueError("N26PA frozen tree bindings changed")
    if record["frozen_auxiliary_hashes"] != {
        "no_model_verification_file_sha256": freeze["no_model_verification_file_sha256"],
        "developer_blocking_record_file_sha256": ce.sha256((target / "qualification/developer-blocking-pre-live-control-denominator.json").read_bytes()),
    }:
        raise ValueError("N26PA frozen auxiliary bindings changed")
    if record["package_and_schedule"] != {
        "package_count": 80,
        "package_hashes_sha256": ce.sha256(freeze["package_hashes"]),
        "review_count": 160,
        "review_design_sha256": freeze["review_design_sha256"],
        "adaptive_followups": 20,
        "reconsiderations": 10,
    }:
        raise ValueError("N26PA package or schedule declaration changed")
    if record["verifier_delta"] != {
        "allowed_changed_files": sorted(allowed),
        "all_other_frozen_code_requires_original_hash": True,
        "correction_record_self_hash_required": True,
        "synthetic_control_denominator_required": True,
    }:
        raise ValueError("N26PA verifier-delta declaration changed")
    if record["focused_tests"] != {
        "command": ".venv/bin/pytest -q tests/test_n26p_experiment.py",
        "result": "12 passed",
        "status": "passed",
    }:
        raise ValueError("N26PA focused-test result changed")
    if record["pre_live_state"] != {
        "completed_reviews": 0,
        "provider_attempt_records": 0,
        "live_consumption_present": False,
    }:
        raise ValueError("N26PA pre-live state declaration changed")
    if record["scientific_material_unchanged"] is not True or record["model_requests_treatments_scoring_and_data_unchanged"] is not True:
        raise ValueError("N26PA scientific preservation declaration missing")
    detected = n25.score_response({"truth_function": None}, {"fault_detected": True})
    not_detected = n25.score_response({"truth_function": None}, {"fault_detected": False})
    base = {"provider_calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "suspect_job": None, "suspect_function": None}
    synthetic = _summary([{**base, **detected}, {**base, **not_detected}])["control_false_positives"]
    if synthetic != {"numerator": 1, "denominator": 2}:
        raise ValueError("N26PA corrected synthetic control denominator failed")
    record["synthetic_control_denominator"] = synthetic
    return record


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("N26P review exists before authority consumption")
    verified = verify_frozen_attempt(repo_root, target)
    record = {
        "schema_version": "n26p-live-consumption-1", "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"], "post_freeze_correction_sha256": verified["correction_sha256"], "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(target / "controller-manifests")),
        "protected_hashes": deepcopy(PROTECTED), "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 80, "reviews": 160, "provider_calls": 190, "repairs": 0},
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _provider_review(repo_root: Path, target: Path, request: Mapping[str, Any], parent_id: str, mode: str, follow_up: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    response = ce._provider_call(repo_root, target, kind="review", model_request=request, controller_parent_id=parent_id, review_prompt=PROMPT, review_schema=_schema_for(mode, follow_up))
    return {**response, "n26p_latency_seconds": time.monotonic() - started}


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count", "n26p_latency_seconds")}


def _usage(response: Mapping[str, Any], purpose: str) -> dict[str, Any]:
    return {**ce.actual_usage_record(response, purpose=purpose, phase="n26p_pilot_review"), "latency_seconds": response.get("n26p_latency_seconds")}


def run_review_session(repo_root: Path, target: Path, catalogue: Mapping[str, Any], index: Mapping[str, Any], package_record: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    mode = package_record["controller_condition"]["mode"]
    package = deepcopy(package_record["reviewer_package"])
    initial = _provider_review(repo_root, target, render_request(package), trial_id, mode)
    pre = n25.validate_response(repo_root, package, initial, _schema_for(mode))
    final, current = pre, package
    calls = [_call_record(initial)]
    usage = [_usage(initial, "initial_pilot_review")]
    events = []
    if mode == "E08":
        group_id = str(pre["receipt"]["next_action"]["execution_group_id"])
        current, event = n25.expand_execution_group(catalogue, index, package, group_id)
        events.append(event)
        current.pop("available_operations", None)
        current.pop("interaction_contract", None)
        response = _provider_review(repo_root, target, render_request(current, event), f"{trial_id}-follow-up-01", mode, True)
        final = n25.validate_response(repo_root, current, response, FINAL_SCHEMA)
        calls.append(_call_record(response))
        usage.append(_usage(response, "model_selected_nested_disclosure"))
    elif mode == "E09":
        before = ce.sha256(_initial_evidence(current))
        event = {"operation": "reconsider_same_evidence", "status": "completed", "evidence_bytes_added": 0}
        response = _provider_review(repo_root, target, render_request(current, event), f"{trial_id}-follow-up-01", mode, True)
        if ce.sha256(_initial_evidence(current)) != before:
            raise RuntimeError("N26P Reconsideration changed evidence")
        final = n25.validate_response(repo_root, current, response, FINAL_SCHEMA)
        events.append(event)
        calls.append(_call_record(response))
        usage.append(_usage(response, "zero_evidence_reconsideration"))
    graph = current.get("graph_review", {}).get("evidence", {})
    return {
        "pre_validation": pre, "final_validation": final, "operation_events": events,
        "completed_evidence_expansions": sum(event["operation"] == "expand_execution_group" for event in events),
        "completed_reconsiderations": sum(event["operation"] == "reconsider_same_evidence" for event in events),
        "selected_group": next((deepcopy(event) for event in events if event["operation"] == "expand_execution_group"), None),
        "disclosed_node_count": len(graph.get("nodes", [])), "disclosed_relationship_count": len(graph.get("relationships", [])),
        "call_records": calls, "usage": ce.aggregate_actual_usage_records(usage),
    }


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for review in reviews:
        trial = review["controller_trial"]
        usage = review["usage"]
        rows.append({
            "trial_id": trial["trial_id"], "instance_id": trial["instance_id"], "cell_id": trial["cell_id"],
            "mode": trial["mode"], "source_setting": trial["source_setting"], "declaration_setting": trial["declaration_setting"],
            "repetition": trial["repetition"], "designation": review["designation"],
            "fault_detected": bool(review["fault_detected"]), "correct_job_attribution": bool(review["correct_job_attribution"]),
            "exact_function_localisation": bool(review["exact_function_localisation"]), "false_positive": bool(review["false_positive"]),
            "suspect_job": review["suspect_job"], "suspect_function": review["suspect_function"],
            "provider_calls": len(review["call_records"]), "input_tokens": int(usage.get("input_tokens") or 0),
            "cached_input_tokens": int(usage.get("cached_input_tokens") or 0), "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "selected_group_contained_mutation_state": bool(review["selected_group_contained_mutation_state"]),
            "pre_fault_detected": bool(review["pre_fault_detected"]), "pre_suspect_job": review["pre_suspect_job"], "pre_suspect_function": review["pre_suspect_function"],
        })
    return rows


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    def ratio(values: list[Mapping[str, Any]], key: str) -> dict[str, int]:
        return {"numerator": sum(bool(value[key]) for value in values), "denominator": len(values)}
    return {
        "reviews": len(rows), "provider_calls": sum(row["provider_calls"] for row in rows),
        "fault_detection": ratio(faults, "fault_detected"), "correct_job_attribution": ratio(faults, "correct_job_attribution"),
        "exact_function_localisation": ratio(faults, "exact_function_localisation"), "control_false_positives": ratio(controls, "false_positive"),
        "input_tokens": sum(row["input_tokens"] for row in rows), "cached_input_tokens": sum(row["cached_input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows), "total_tokens": sum(row["total_tokens"] for row in rows),
        "selected_job_distribution": {str(key): sum(row["suspect_job"] == key for row in rows) for key in ("job_1", "job_2", "job_3", "job_4", None)},
        "selected_function_distribution": {str(key): sum(row["suspect_function"] == key for row in rows) for key in sorted({row["suspect_function"] for row in rows}, key=lambda value: str(value))},
    }


def write_analysis(repo_root: Path, target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    aggregate = _summary(rows)
    cell_summaries = {cell: _summary([row for row in rows if row["cell_id"] == cell]) for cell in PILOT_CELLS}
    if aggregate["fault_detection"]["denominator"] != 96 or aggregate["control_false_positives"]["denominator"] != 64:
        raise RuntimeError("N26PA aggregate fault/control accounting changed")
    if any(value["fault_detection"]["denominator"] != 6 or value["control_false_positives"]["denominator"] != 4 for value in cell_summaries.values()):
        raise RuntimeError("N26PA per-cell fault/control accounting changed")
    instance_summaries = {instance: _summary([row for row in rows if row["instance_id"] == instance]) for instance in PILOT_INSTANCES}
    instance_cell = {f"{instance}/{cell}": _summary([row for row in rows if row["instance_id"] == instance and row["cell_id"] == cell]) for instance in PILOT_INSTANCES for cell in PILOT_CELLS}
    adaptive = [row for row in rows if row["mode"] == "E08"]
    reconsider = [row for row in rows if row["mode"] == "E09"]
    contrasts = []
    for name, left, right, _, _ in (
        ("job4_logs", "E02-S1-B0", "E01-S1-B0", set(), False),
        ("complete_source", "E02-S1-B0", "E02-S0-B0", set(), False),
        ("semantic_boundaries", "E02-S1-B1", "E02-S1-B0", set(), False),
        ("empty_history", "E03-S1-B0", "E02-S1-B0", set(), False),
        ("actual_history", "E04-S1-B0", "E03-S1-B0", set(), False),
        ("empty_graph", "E05-S1-B0", "E02-S1-B0", set(), False),
        ("compact_nodes", "E06-S1-B0", "E05-S1-B0", set(), False),
        ("connectivity_nesting", "E07-S1-B0", "E06-S1-B0", set(), False),
        ("adaptive_disclosure", "E08-S1-B0", "E07-S1-B0", set(), False),
        ("new_evidence_vs_reconsideration", "E08-S1-B0", "E09-S1-B0", set(), False),
        ("full_graph", "E10-S1-B0", "E05-S1-B0", set(), False),
        ("structural_vs_random", "E07-S1-B0", "E11-S1-B0", set(), False),
    ):
        for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation"):
            differences = []
            for instance in PILOT_INSTANCES[:3]:
                a = [float(row[outcome]) for row in rows if row["instance_id"] == instance and row["cell_id"] == left]
                b = [float(row[outcome]) for row in rows if row["instance_id"] == instance and row["cell_id"] == right]
                differences.append(sum(a) / len(a) - sum(b) / len(b))
            contrasts.append({"name": name, "left": left, "right": right, "outcome": outcome, "independent_fault_units": 3, "mean_difference": sum(differences) / len(differences), "per_instance_differences": differences})
    analysis = {
        "schema_version": "n26p-pilot-analysis-1", "exploratory_not_confirmatory": True,
        "pilot_results_must_not_be_pooled_into_attempt_044": True, "aggregate": aggregate,
        "cell_summaries": cell_summaries, "instance_summaries": instance_summaries, "instance_cell_summaries": instance_cell,
        "paired_pilot_contrasts": contrasts,
        "adaptive": {"sessions": len(adaptive), "mutation_state_containment": {"numerator": sum(row["selected_group_contained_mutation_state"] for row in adaptive if row["designation"] == "upstream_fault"), "denominator": sum(row["designation"] == "upstream_fault" for row in adaptive)}, "detection_changed": sum(row["fault_detected"] != row["pre_fault_detected"] for row in adaptive), "job_changed": sum(row["suspect_job"] != row["pre_suspect_job"] for row in adaptive), "function_changed": sum(row["suspect_function"] != row["pre_suspect_function"] for row in adaptive)},
        "reconsideration": {"sessions": len(reconsider), "evidence_bytes_added": 0, "detection_changed": sum(row["fault_detected"] != row["pre_fault_detected"] for row in reconsider), "job_changed": sum(row["suspect_job"] != row["pre_suspect_job"] for row in reconsider), "function_changed": sum(row["suspect_function"] != row["pre_suspect_function"] for row in reconsider)},
        "estimated_cost_usd": round((aggregate["input_tokens"] - aggregate["cached_input_tokens"]) * 5 / 1_000_000 + aggregate["cached_input_tokens"] * .5 / 1_000_000 + aggregate["output_tokens"] * 30 / 1_000_000, 6),
        "limitations": ["This five-instance pilot is exploratory and must not be pooled into the later confirmatory experiment.", "Only three of ten faults and two of three independent controls received model calls.", "The three pilot faults, not repeated calls, are the independent faulty units."],
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(target / "analysis/summary.json", analysis)
    csv_path = target / "analysis/all-review-rows.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    output = []
    if rows:
        import io
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows); output = stream.getvalue()
    _write_text(csv_path, str(output))
    return target / "analysis/summary.json"


def _rate(value: Mapping[str, int]) -> str:
    return "n/a" if not value["denominator"] else f"{value['numerator']}/{value['denominator']} ({100 * value['numerator'] / value['denominator']:.2f}%)"


def _write_reports(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N26P-small-implementation-pilot"
    findings = [
        "# N26P small implementation pilot", "",
        "Attempt 043 completed the bounded implementation pilot. These exploratory outcomes must not be pooled into the later confirmatory N26 dataset.", "",
        "## Aggregate exploratory outcomes", "",
        f"- Fault detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Required expansions: {analysis['adaptive']['sessions']}/20",
        f"- Reconsiderations: {analysis['reconsideration']['sessions']}/10 with zero added evidence", "",
        "## Operational assessment", "",
        "The reusable thirteen-instance foundation qualified, every frozen pilot trial completed, Adaptive disclosed exactly one genuine model-selected group per applicable review, Random Structural Matched passed its frozen strata, and replay reconciled. Readiness is operational rather than performance-based.", "",
        "## Immutable records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-043/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-043/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-043/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-043/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    lines = ["# N26P complete pilot cell table", "", "| Cell | Reviews | Detection | Job 1 | Exact function | Control FP | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in PILOT_CELLS:
        value = analysis["cell_summaries"][cell]
        lines.append(f"| {cell} | {value['reviews']} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} | {_rate(value['control_false_positives'])} | {value['provider_calls']} |")
    _write_text(report_dir / "tables.md", "\n".join(lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    freeze_file = target / "experiment-freeze.json"
    lines = [
        "To: Overseer", "From: Developer", "Subject: N26P Attempt 043 implementation-pilot results", "",
        "Status: `completed_pilot_and_analysis`", f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(freeze_file)['freeze_sha256']}`", "", "Counts", "",
        "- Complete reusable foundation: ten faults, three controls, thirteen four-job captures and catalogues",
        "- Live pilot: five instances, sixteen cells each, 80 packages and 160 terminal reviews",
        "- 20 Required-One expansions; 10 zero-evidence reconsiderations; 190 logical calls; zero repairs", "",
        "Exploratory outcomes", "",
        f"- Detection: {_rate(aggregate['fault_detection'])}", f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}", f"- Clean false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; total {aggregate['total_tokens']}",
        f"- Frozen-rate estimated cost: USD {analysis['estimated_cost_usd']}", "", "Exact artifact hashes", "",
        f"- `{freeze_file.relative_to(repo_root).as_posix()}`: `{ce.sha256(freeze_file.read_bytes())}`",
        f"- `{target.relative_to(repo_root).as_posix()}/captures`: `{ce.sha256(ce._tree_hashes(target / 'captures'))}`",
        f"- `{target.relative_to(repo_root).as_posix()}/packages`: `{ce.sha256(ce._tree_hashes(target / 'packages'))}`",
        f"- `{target.relative_to(repo_root).as_posix()}/reviews`: `{ce.sha256(ce._tree_hashes(target / 'reviews'))}`",
        f"- `{target.relative_to(repo_root).as_posix()}/analysis`: `{ce.sha256(ce._tree_hashes(target / 'analysis'))}`",
        f"- `{target.relative_to(repo_root).as_posix()}/replay.json`: `{ce.sha256((target / 'replay.json').read_bytes())}`",
        f"- `{target.relative_to(repo_root).as_posix()}/terminal-state.json`: `{ce.sha256((target / 'terminal-state.json').read_bytes())}`", "",
        "Attempt 042 and all protected execution/security surfaces remained unchanged. Attempt 044 was not created or run. Pilot outcomes are exploratory and are not confirmatory-reusable.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N26P_attempt_043_results_to_overseer.email.md", "\n".join(lines))


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(reviews)
    return {
        "reviews": len(values), "repairs": 0,
        "logical_provider_calls": sum(len(value["call_records"]) for value in values),
        "provider_attempt_call_ids": sum(len(call["call_ids"]) for value in values for call in value["call_records"]),
        "completed_evidence_expansions": sum(value["completed_evidence_expansions"] for value in values),
        "completed_reconsiderations": sum(value["completed_reconsiderations"] for value in values),
    }


def execute_lifecycle(repo_root: Path, target: Path) -> Path:
    repo_root, target = repo_root.resolve(), target.resolve()
    verified = verify_frozen_attempt(repo_root, target)
    create_live_consumption(repo_root, target)
    prepared = prepare_attempt(repo_root, target)
    packages = {record["controller_condition"]["branch_id"]: record for record in _package_records(target)}
    trials = _json(target / "review-design.json")["review_trials"]
    foundation = _json(target / "foundation-qualification.json")
    reviews = []
    for trial in trials:
        path = target / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = _json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record["controller_trial"] != trial or record["status"] != "complete":
                raise ValueError("invalid N26P partial review record")
        else:
            instance_id = trial["instance_id"]
            package_record = packages[trial["branch_id"]]
            session = run_review_session(repo_root, target, prepared["catalogues"][instance_id], prepared["indexes"][instance_id], package_record, trial["trial_id"])
            pre, final = session["pre_validation"], session["final_validation"]
            outcome = n25.score_response(prepared["instances"][instance_id], final)
            selected = session["selected_group"]
            legal = foundation["nested_relevance"].get(instance_id, {}).get("legal_relevant_group_ids", [])
            record = {
                "schema_version": "n26p-review-record-1", "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"], "initial_receipt": deepcopy(pre["receipt"]),
                "terminal_receipt": deepcopy(final["receipt"]), "pre_fault_detected": pre["fault_detected"],
                "pre_suspect_job": pre["suspect_job"], "pre_suspect_function": pre["normalized_suspect_function"],
                "suspect_job": final["suspect_job"], "suspect_function": final["normalized_suspect_function"],
                "suspect_function_visible": final["suspect_function_visible"], "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]),
                **outcome, "operation_events": session["operation_events"],
                "completed_evidence_expansions": session["completed_evidence_expansions"],
                "completed_reconsiderations": session["completed_reconsiderations"],
                "selected_group_contained_mutation_state": bool(selected and selected["execution_group_id"] in legal),
                "disclosed_node_count": session["disclosed_node_count"], "disclosed_relationship_count": session["disclosed_relationship_count"],
                "call_records": session["call_records"], "usage": session["usage"], "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews.append(record)
    counts = reconstruct_counts(reviews)
    expected = {"reviews": 160, "repairs": 0, "logical_provider_calls": 190, "provider_attempt_call_ids": counts["provider_attempt_call_ids"], "completed_evidence_expansions": 20, "completed_reconsiderations": 10}
    if counts != expected:
        raise RuntimeError(f"N26P terminal counts changed: {counts}")
    call_ids = [call_id for record in reviews for call in record["call_records"] for call_id in call["call_ids"]]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("N26P duplicate provider call ID")
    for call_id in call_ids:
        verify_record(target / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = _json(write_analysis(repo_root, target, reviews))
    freeze = _json(target / "experiment-freeze.json")
    replay = {
        "schema_version": "n26p-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(record["review_sha256"] for record in reviews), "observed_counts": counts,
        "all_record_hashes_recomputed": True, "duplicate_provider_call_ids": False,
        "package_tree_unchanged": ce.sha256(ce._tree_hashes(target / "packages")) == freeze["package_tree_sha256"],
        "controller_manifest_tree_unchanged": ce.sha256(ce._tree_hashes(target / "controller-manifests")) == freeze["controller_manifest_tree_sha256"],
        "foundation_capture_tree_unchanged": ce.sha256(ce._tree_hashes(target / "capture-branches")) == freeze["capture_branch_tree_sha256"],
        "provider_receipts_preserved": all(record["initial_receipt"] and record["terminal_receipt"] for record in reviews),
        "required_expansions_complete": sum(record["completed_evidence_expansions"] for record in reviews) == 20,
        "reconsiderations_complete": sum(record["completed_reconsiderations"] for record in reviews) == 10,
        "repair_count": 0, "attempt_044_created": False, "pilot_results_confirmatory_reuse_permitted": False,
    }
    if not all(value for key, value in replay.items() if key.endswith("unchanged") or key.endswith("preserved") or key.endswith("complete")):
        raise RuntimeError("N26P replay reconciliation failed")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(target / "replay.json", replay)
    terminal = {
        "schema_version": "n26p-terminal-1", "status": "completed_pilot_and_analysis",
        "foundation_fault_count": 10, "foundation_control_count": 3, "foundation_capture_count": 13,
        "live_instance_count": 5, "package_count": 80, "review_count": 160,
        "mandatory_follow_up_count": 30, "logical_provider_calls": 190, "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"], "replay_sha256": replay["replay_sha256"],
        "attempt_044_created": False,
    }
    terminal["terminal_sha256"] = ce.sha256(terminal)
    path = target / "terminal-state.json"
    ce._write_immutable(path, terminal)
    _write_reports(repo_root, target)
    _write_handoff(repo_root, target)
    return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        record = {"schema_version": "n26p-terminal-1", "status": "terminal_incomplete", "failure_stage": "n26p_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}", "completed_review_records": len(list((target / 'reviews').glob('*.json'))), "completed_repair_records": 0}
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
            built = build_attempt(repo, target)
            print(json.dumps({"qualification": built["qualification"], "counts": {"packages": len(built["records"]), "reviews": len(built["design"]["review_trials"]), "repairs": 0}}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, target))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, target), indent=2))
        else:
            path = run_lifecycle(repo, target)
            print(path)
            return 0 if _json(path).get("status") == "completed_pilot_and_analysis" else 1
    except Exception as exc:
        print(f"N26P experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
