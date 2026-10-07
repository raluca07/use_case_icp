"""N27PB payload-lazy native-Etiq hard-fault pilot (Attempt 046)."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from copy import deepcopy
import csv
import io
import json
from itertools import product
from pathlib import Path
import random
import re
import time
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from . import fault_operations as operations
from . import n25_experiment as n25
from . import n26p_experiment as n26p
from . import n27p_experiment as n27p
from . import n27pa_experiment as n27pa
from .fault_preflight_v2 import validate_strict_provider_schema
from .job_store import JobStore
from .n05_program import _load_snapshot, _parse_output, _pipeline_payload, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-046")
ATTEMPT_045 = Path("outputs/fault-experiments-v2-2-n10/attempt-045")
TASK = Path("instructions_between_agent_types/developer/current/N27PB_payload_lazy_hard_fault_native_etiq_pilot.email.md")
TASK_SHA256 = "sha256:5afbeca8de4f155a4121b0c5f25c2bb708d8d3c5d18e4e3fb4426a4070e5cdff"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PB_payload_lazy_hard_fault_native_etiq_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:6d6ce2b31a5009872f9b6d4bfcd06d7144f1e168e2391dd0485c760ed0fb32b6"
N27PA_AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PA_dataframe_native_jobs_3_4_pilot_authorization.json")
N27PA_AUTHORITY_SHA256 = "sha256:54730443a57d17630dd69d0373f4ed2f8a7c758e958e46fbba61d5040aae05cb"
UPSTREAM_SOURCE = Path("src/use_case_icp/n26_upstream_demand_provenance.py")
DOWNSTREAM_SOURCE = Path("src/use_case_icp/n26_downstream_coverage_priority.py")
JOB3_SOURCE = Path("src/use_case_icp/n27pa_campaign_portfolio.py")
JOB4_SOURCE = Path("src/use_case_icp/n27pa_campaign_activation.py")
PROMPT = Path("prompts/v2_2/n27pb_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n27pb_final.schema.json")
GROUP_SCHEMA = Path("schemas/v2_2/n27pb_choose_group.schema.json")
ARTIFACT_SCHEMA = Path("schemas/v2_2/n27pb_choose_artifact.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n27pb_reconsider.schema.json")
COMMON_CONTRACT = Path("qualification/common-reviewer-contract.json")
SANDBOX_GATE = Path("outputs/fault-experiments-v2-2-n10/attempt-025/qualification/tester-n14a-delta-gate-b13d882b5af6a753.json")
SANDBOX_GATE_SHA256 = "sha256:07700a2826733de6a9b0de2a59d0b399a2bbfa8a27325bff00b2a567e8c22051"

JOB_ORDER = n25.JOB_ORDER
UPSTREAM, DOWNSTREAM, JOB3, JOB4 = JOB_ORDER
FUNCTIONS = n25.FUNCTIONS
DELIVERY_RULES = n25.DELIVERY_RULES
INSTANCES = (
    "case-amber-harbor",
    "case-cobalt-meadow",
    "case-ivory-ridge",
    "case-sable-orchard",
    "case-vermilion-brook",
)
TRUTH = {
    "case-amber-harbor": None,
    "case-cobalt-meadow": "select_demand",
    "case-ivory-ridge": "normalize",
    "case-sable-orchard": None,
    "case-vermilion-brook": "assemble_provenance",
}
MATCHED_CLEAN = {
    "case-cobalt-meadow": "case-amber-harbor",
    "case-ivory-ridge": "case-amber-harbor",
    "case-vermilion-brook": "case-sable-orchard",
}
MUTATIONS = {
    "case-cobalt-meadow": ("threshold_value >= threshold", "threshold_value > threshold"),
    "case-ivory-ridge": ('-row["aggregate_demand"]', 'row["aggregate_demand"]'),
    "case-vermilion-brook": ('-float(row["source_weight"])', 'float(row["source_weight"])'),
}
CELLS = (
    "P01-S0-B0", "P02-S1-B0", "P03-S1-B1", "P04-S1-B0",
    "P05-S1-B0", "P06-S0-B0", "P07-S1-B0", "P08-S1-B1",
    "P09-S1-B0", "P10-S0-B0", "P11-S1-B0", "P12-S1-B0",
    "P13-S1-B0", "P14-S1-B0",
)
MODE_NAMES = {
    "P01": "current_job4", "P02": "current_job4", "P03": "current_job4",
    "P04": "full_predecessor_history", "P05": "compact_native_nodes",
    "P06": "compact_fixed", "P07": "compact_fixed", "P08": "compact_fixed",
    "P09": "compact_inspect", "P10": "adaptive_required_one",
    "P11": "adaptive_required_one", "P12": "two_pass_reconsideration",
    "P13": "full_graph_inspect", "P14": "random_matched_inspect",
}
GRAPH_MODES = {f"P{number:02d}" for number in range(5, 15)}
TASK_TEXT = (
    "Starting from the observed Job-4 campaign-activation result, decide whether the four-job "
    "execution contains a behaviorally significant fault. If it does, identify the earliest "
    "responsible job and, when supplied evidence supports it, the exact responsible function."
)
CONTRACT_CRITERIA = [
    "Apply the supplied demand-selection policy consistently within the retained capacity.",
    "Retain the strongest traceable evidence for each retained need.",
    "Preserve demand and provenance ordering through downstream handoffs.",
    "Place evidence gaps before launch-ready work.",
    "Preserve record identity and traceability through the campaign portfolio and activation plan.",
]
SOURCE_HASHES = {
    UPSTREAM_SOURCE.as_posix(): "sha256:c0891f2e73be29504c648df8c41d225e1e8419256c96feb7e8eb177d0438e247",
    DOWNSTREAM_SOURCE.as_posix(): "sha256:df117801a274f44893bd5f0a5ffc82eb54b1870ee7fe17f2abd568fafb217e76",
    JOB3_SOURCE.as_posix(): "sha256:76753d5ba89b3955226dbaedb812e46c2c87e11b7a4c357698f7a1ecd267a8e8",
    JOB4_SOURCE.as_posix(): "sha256:1078f6c7ccac6f579aabbb4f82ad7761621d3a6ee77bb79007dba23c3fb9f8dc",
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
}
ATTEMPT_045_HASHES = {
    "terminal-state.json": "sha256:500783cb05409249f61a77b0dbbb6708b0a2909f503b9a6b01ac69ca4ee3c6d4",
    "experiment-freeze.json": "sha256:80296b7f0f09c465dc0716b6cb70b5affbff018d5cdfb8604f61d4a8ef94b1bd",
    "replay.json": "sha256:f99e2f96ef3f2c4d5e05a500ee92c69371768dc6ca243d978611e85969fe0995",
    "analysis/summary.json": "sha256:137e17fea3a1e35e2a649c40167ae42223d219b91aef26ec1e007e86ab85f830",
}


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    create_bytes_exclusive(path, value.encode())


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    bindings = ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256), (N27PA_AUTHORITY, N27PA_AUTHORITY_SHA256))
    for relative, expected in bindings:
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PB authority changed: {relative}")
    for relative, expected in SOURCE_HASHES.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PB protected source changed: {relative}")
    for relative, expected in ATTEMPT_045_HASHES.items():
        if ce.sha256((repo_root / ATTEMPT_045 / relative).read_bytes()) != expected:
            raise ValueError(f"Attempt 045 preservation binding changed: {relative}")
    for root, files in n27p.PRESERVED.items():
        for relative, expected in files.items():
            if ce.sha256((repo_root / root / relative).read_bytes()) != expected:
                raise ValueError(f"historical preservation binding changed: {root.name}/{relative}")
    if ce.sha256((repo_root / SANDBOX_GATE).read_bytes()) != SANDBOX_GATE_SHA256:
        raise ValueError("signed artifact sandbox gate changed")
    protected = {
        "artifact_python_worker_sha256": ce.sha256(operations._ARTIFACT_PYTHON_WORKER.encode()),
        "production_launcher_sha256": operations.production_launcher_sha256(operations.artifact_python_launcher),
        "launch_policy_sha256": operations.ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
    }
    expected = {
        "artifact_python_worker_sha256": "sha256:8e9307c764bb5e9f6511dc96fdc32a5adb3202df6bf0968c0b8522b6c74c98b5",
        "production_launcher_sha256": "sha256:fe8216b7c45091bffecfb1f304c3947548f7a1175fe03ad7c82d506bacc0ba83",
        "launch_policy_sha256": "sha256:ca9a3d0c25ce256c5e2d0ad7e9744d53803bfdc2028043c2839b25b2b8a094c9",
    }
    if protected != expected:
        raise ValueError("protected artifact sandbox binding changed")
    if (ce.PROVIDER_MODEL, ce.PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise ValueError("N27PB model configuration changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "sandbox": protected}


def _row(record_id: str, need: str, segment: str, demand: float, weight: float, source: str) -> dict[str, Any]:
    return {
        "observation_id": f"obs-{record_id}", "record_id": record_id, "need": need,
        "segment": segment, "demand_score": demand, "source_weight": weight,
        "source_id": source, "qualified": True,
    }


def _selection_input() -> dict[str, Any]:
    fallback_needs = (
        ("rec-horizon", "account intelligence", 8.9),
        ("rec-juniper", "regional reporting", 8.5),
        ("rec-lantern", "buyer journey analytics", 8.1),
        ("rec-marigold", "partner attribution", 7.8),
        ("rec-nimbus", "pipeline automation", 7.5),
        ("rec-oak", "territory planning", 7.2),
        ("rec-prairie", "conversion forecasting", 6.9),
    )
    rows = [_row(record, need, "established", demand, 5.4 + index / 10, f"source-{index:02d}") for index, (record, need, demand) in enumerate(fallback_needs, 1)]
    rows.extend([
        _row("rec-quartz", "content measurement", "strategic", 7.4, 6.35, "source-21"),
        _row("rec-river", "community nurture", "growth", 7.1, 6.25, "source-22"),
    ])
    return {
        "scenario_id": "portfolio-capacity-planning",
        "corpus": rows,
        "selection_policy": {
            "segment_thresholds": {"established": 5.0, "strategic": 7.4, "growth": 7.0},
            "default_threshold": 5.0, "minimum_qualifying_source_rate": 0.5,
            "fallback_record_ids": [value[0] for value in fallback_needs],
            "retained_capacity": 8, "aggregation_rule": "sum",
            "duplicate_survivor_rule": "highest_source_weight", "score_precision": 2,
            "ranking_tie_break": ["aggregate_demand_desc", "source_weight_desc", "record_id"],
        },
    }


def _provenance_input() -> dict[str, Any]:
    values = (
        ("rec-saffron", "account intelligence", 9.2, 7.3),
        ("rec-thicket", "regional reporting", 8.7, 7.1),
        ("rec-umber", "buyer journey analytics", 8.1, 6.9),
        ("rec-violet", "partner attribution", 7.55, 6.7),
        ("rec-willow", "pipeline automation", 7.55, 6.55),
        ("rec-xenia", "territory planning", 6.9, 6.4),
        ("rec-yarrow", "conversion forecasting", 6.3, 6.2),
        ("rec-zephyr", "content measurement", 5.8, 6.0),
    )
    return {
        "scenario_id": "provenance-order-planning",
        "corpus": [_row(record, need, "portfolio", demand, weight, f"evidence-{index:02d}") for index, (record, need, demand, weight) in enumerate(values, 1)],
        "selection_policy": {
            "segment_thresholds": {"portfolio": 5.0}, "default_threshold": 5.0,
            "minimum_qualifying_source_rate": 0.5, "fallback_record_ids": [],
            "retained_capacity": 8, "aggregation_rule": "sum",
            "duplicate_survivor_rule": "highest_source_weight", "score_precision": 2,
            "ranking_tie_break": ["aggregate_demand_desc", "source_weight_desc", "record_id"],
        },
    }


def input_for(instance_id: str) -> dict[str, Any]:
    return deepcopy(_selection_input() if instance_id in INSTANCES[:3] else _provenance_input())


CAPABILITIES = [
    {"capability_id": f"capability-{index:02d}", "need": need}
    for index, need in enumerate((
        "account intelligence", "regional reporting", "buyer journey analytics",
        "partner attribution", "pipeline automation", "territory planning",
        "conversion forecasting", "content measurement", "community nurture",
    ), 1)
]


def _mutant_source(clean: str, instance_id: str) -> tuple[str, dict[str, Any] | None]:
    truth = TRUTH[instance_id]
    if truth is None:
        return clean, None
    old, new = MUTATIONS[instance_id]
    if clean.count(old) != 1:
        raise ValueError(f"mutation site is not unique: {instance_id}")
    mutated = clean.replace(old, new, 1)
    clean_tree, mutant_tree = ast.parse(clean), ast.parse(mutated)
    if sum(ast.dump(a) != ast.dump(b) for a, b in zip(ast.walk(clean_tree), ast.walk(mutant_tree))) < 1:
        raise ValueError("mutation did not change the AST")
    start = clean.index(old)
    line = clean.count("\n", 0, start) + 1
    record = {
        "operator": "single_ast_expression_substitution",
        "qualified_function_name": truth, "job_id": UPSTREAM,
        "original_snippet": old, "mutant_snippet": new,
        "original_span": {"start_line": line, "end_line": line},
        "candidate_count": 1, "exactly_one_source_site_changed": True,
        "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return mutated, record


def _pipeline(repo_root: Path, job_id: str, upstream_source: str) -> GeneratedPipeline:
    paths = {
        UPSTREAM: ("generated/protocol_2_2/n26_upstream_demand_provenance.py", upstream_source),
        DOWNSTREAM: ("generated/protocol_2_2/n26_downstream_coverage_priority.py", (repo_root / DOWNSTREAM_SOURCE).read_text()),
        JOB3: ("generated/protocol_2_2/n27pa_campaign_portfolio.py", (repo_root / JOB3_SOURCE).read_text()),
        JOB4: ("generated/protocol_2_2/n27pa_campaign_activation.py", (repo_root / JOB4_SOURCE).read_text()),
    }
    roles = {
        UPSTREAM: (
            ("select_demand", "Transform corpus and policy into selected demand observations.", ["corpus", "selection_policy"], ["selected observations"]),
            ("normalize", "Transform selected observations into retained needs.", ["selected observations", "selection_policy"], ["needs"]),
            ("assemble_provenance", "Transform retained needs into provenance records.", ["needs", "selection_policy"], ["evidence_sources"]),
        ),
        DOWNSTREAM: (
            ("map_coverage", "Transform needs and capabilities into coverage records.", ["needs", "capabilities"], ["coverage"]),
            ("prioritize", "Transform coverage and provenance into priorities.", ["coverage", "evidence_sources"], ["priorities"]),
            ("synthesize", "Transform priorities into retained priorities and a recommendation.", ["priorities"], ["priorities", "recommendation"]),
        ),
        JOB3: (
            ("build_campaign_items", "Transform priorities into campaign items.", ["priorities"], ["campaign items"]),
            ("assign_message_strategy", "Transform campaign items and recommendation into assigned items.", ["campaign items", "recommendation"], ["assigned items"]),
            ("assemble_campaign_portfolio", "Transform assigned items and coverage into a campaign portfolio.", ["assigned items", "coverage", "recommendation"], ["campaign_portfolio"]),
        ),
        JOB4: (
            ("map_delivery_channels", "Transform campaign items and delivery rules into mapped items.", ["campaign items", "delivery_rules"], ["mapped items"]),
            ("schedule_campaign_actions", "Transform mapped items into scheduled actions.", ["mapped items"], ["scheduled actions"]),
            ("assemble_activation_plan", "Transform scheduled actions into an activation plan.", ["campaign_portfolio", "scheduled actions"], ["activation_plan"]),
        ),
    }
    path, source = paths[job_id]
    pipeline = GeneratedPipeline(
        entry_file=path,
        files=[GeneratedFile(path, source)],
        review_boundaries=[{
            "boundary_id": f"rb-opaque-j{JOB_ORDER.index(job_id) + 1}-{index}",
            "function_name": name, "qualified_function_name": name,
            "source_path": path, "role": role,
            "expected_inputs": inputs, "expected_outputs": outputs,
            "semantic_stage": job_id,
        } for index, (name, role, inputs, outputs) in enumerate(roles[job_id], 1)],
    )
    pipeline.validate()
    return pipeline


def _job_input(job_id: str, prior: Mapping[str, Any] | None, root: Mapping[str, Any]) -> dict[str, Any]:
    if job_id == UPSTREAM:
        return deepcopy(dict(root))
    if job_id == DOWNSTREAM:
        return {"needs": deepcopy(prior["needs"]), "evidence_sources": deepcopy(prior["evidence_sources"]), "capabilities": deepcopy(CAPABILITIES)}
    if job_id == JOB3:
        return {key: deepcopy(prior[key]) for key in ("coverage", "priorities", "recommendation", "metadata")}
    return {"campaign_portfolio": deepcopy(prior["campaign_portfolio"]), "metadata": deepcopy(prior["metadata"]), "delivery_rules": deepcopy(DELIVERY_RULES)}


def _load_execution(branch: Path, job_id: str) -> Any | None:
    if not branch.exists():
        return None
    runs = sorted(branch.glob(f"jobstore/{job_id}/stages/n05/*/runs/*"))
    if len(runs) != 1:
        raise ValueError(f"partial fresh capture branch: {branch}")
    run_dir = runs[0]
    snapshot = _load_snapshot(JobStore(branch / "jobstore"), run_dir)
    if snapshot.scan_errors or not snapshot.nodes or not (run_dir / "etiq-native-lineage.json").is_file():
        raise ValueError(f"unreviewable fresh Etiq capture: {branch}")
    return n25.EtiqExecution(snapshot=snapshot, run_dir=run_dir)


def _capture_instance(repo_root: Path, target: Path, instance_id: str, upstream_source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pipelines = {job: _pipeline(repo_root, job, upstream_source) for job in JOB_ORDER}
    jobs: dict[str, Any] = {}
    handoffs: list[dict[str, Any]] = []
    native_bindings: dict[str, Any] = {}
    prior = None
    for index, job_id in enumerate(JOB_ORDER):
        runtime_input = _job_input(job_id, prior, input_for(instance_id))
        branch = target / "capture-branches" / instance_id / f"canonical-v2-job-{index + 1}"
        execution = _load_execution(branch, job_id)
        if execution is None:
            materialize_opaque_branch(branch, allowlist={}, manifest_identity={"purpose": "n27pb-fresh-native-capture", "case": instance_id, "job": job_id})
            copy_etiq_worker_runtime(branch, repo_root / "src")
            execution = execute_pipeline_in_branch(
                branch, repo_root=repo_root, job_id=job_id, pipeline=pipelines[job_id],
                runtime_input=runtime_input, run_index=INSTANCES.index(instance_id),
                stage=f"n27pb-{index + 1}",
            )
        output = _parse_output(execution)
        n26p._check_output(repo_root, job_id, output, runtime_input)
        native_path = execution.run_dir / "etiq-native-lineage.json"
        native = _json(native_path)
        if not native.get("objects") or not native.get("edges"):
            raise ValueError(f"empty native export: {instance_id}/{job_id}")
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
            names = ("needs", "evidence_sources") if job_id == DOWNSTREAM else (("coverage", "priorities", "recommendation", "metadata") if job_id == JOB3 else ("campaign_portfolio", "metadata"))
            handoffs.extend(n25._handoff(name, producer, job_id, jobs[producer]["output"][name]) for name in names)
        prior = output
    capture = {
        "schema_version": "n27pb-four-job-native-capture-1",
        "capture_id": stable_id("rerun-capture", ["n27pb", instance_id], 0),
        "instance_id": instance_id, "job_ids": list(JOB_ORDER), "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": {job: ce.sha256(_pipeline_payload(pipelines[job])) for job in JOB_ORDER},
        "native_lineage_bindings": native_bindings, "canonical": True, "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    n25._verify_four_capture(capture)
    bundle = [{"job_id": job, "files": [{"path": pipelines[job].files[0].path, "content": pipelines[job].files[0].content}]} for job in JOB_ORDER]
    return capture, bundle


def _action_rows(output: Mapping[str, Any]) -> list[dict[str, Any]]:
    plan = output["activation_plan"]
    return [*plan["launch_actions"], *plan["evidence_review_actions"]]


def _hard_fault_qualification(captures: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    clean_selection = captures[INSTANCES[0]]["jobs"][JOB4]["output"]
    clean_provenance = captures[INSTANCES[3]]["jobs"][JOB4]["output"]
    outputs = {key: value["jobs"][JOB4]["output"] for key, value in captures.items()}
    selection_ids = [row["record_id"] for row in _action_rows(clean_selection)]
    if len(selection_ids) != 8 or "rec-quartz" not in selection_ids or "rec-river" in selection_ids:
        raise ValueError("selection clean oracle failed")
    for instance_id in INSTANCES[1:3]:
        ids = [row["record_id"] for row in _action_rows(outputs[instance_id])]
        if len(ids) != 8 or "rec-river" not in ids or "rec-quartz" in ids:
            raise ValueError(f"matched substitution oracle failed: {instance_id}")
    if ce.canonical_json(outputs[INSTANCES[1]]) != ce.canonical_json(outputs[INSTANCES[2]]):
        raise ValueError("F1/F2 logical Job-4 symptoms are not identical")
    clean_rows = _action_rows(clean_provenance)
    faulty_rows = _action_rows(outputs[INSTANCES[4]])
    clean_ids = [row["record_id"] for row in clean_rows]
    faulty_ids = [row["record_id"] for row in faulty_rows]
    differing = [index for index, pair in enumerate(zip(clean_ids, faulty_ids)) if pair[0] != pair[1]]
    if (
        len(clean_ids) != len(faulty_ids) or set(clean_ids) != set(faulty_ids)
        or differing != [3, 4] or faulty_ids[3:5] != list(reversed(clean_ids[3:5]))
    ):
        raise ValueError("F3 is not exactly one adjacent record-order inversion")
    for instance_id in INSTANCES:
        capture = captures[instance_id]
        output = outputs[instance_id]
        rows = _action_rows(output)
        if not rows or any(value is None for row in rows for value in row.values()):
            raise ValueError(f"implausible null/empty plan: {instance_id}")
        if any(float(row.get("source_weight", 1)) == 0 or int(row.get("upstream_rank", 1)) == 0 for row in rows):
            raise ValueError(f"zero rank/weight giveaway: {instance_id}")
        if any(capture["jobs"][job]["stderr"] for job in JOB_ORDER):
            raise ValueError(f"exception/log giveaway: {instance_id}")
        counts = output["metadata"]
        if counts["total_action_count"] != len(rows) or counts["scheduled_action_count"] + counts["review_action_count"] != len(rows):
            raise ValueError(f"final metadata count mismatch: {instance_id}")
    for fault, clean in MATCHED_CLEAN.items():
        fault_output, clean_output = outputs[fault], outputs[clean]
        if len(_action_rows(fault_output)) != len(_action_rows(clean_output)) or fault_output["metadata"] != clean_output["metadata"]:
            raise ValueError(f"fault changed final counts: {fault}")
    deltas = {}
    for fault, clean in MATCHED_CLEAN.items():
        deltas[fault] = {
            "matched_clean_case": clean,
            "clean_job4_sha256": ce.sha256(outputs[clean]),
            "fault_job4_sha256": ce.sha256(outputs[fault]),
            "clean_record_order": [row["record_id"] for row in _action_rows(outputs[clean])],
            "fault_record_order": [row["record_id"] for row in _action_rows(outputs[fault])],
            "row_count_equal": len(_action_rows(outputs[clean])) == len(_action_rows(outputs[fault])),
            "metadata_counts_equal": outputs[clean]["metadata"] == outputs[fault]["metadata"],
        }
    return {
        "schema_version": "n27pb-hard-fault-qualification-1", "status": "passed",
        "clean_controls": 2, "one_site_faults": 3,
        "f1_f2_exact_job4_match": ce.canonical_json(outputs[INSTANCES[1]]) == ce.canonical_json(outputs[INSTANCES[2]]),
        "f3_adjacent_inversion_positions": differing,
        "all_schemas_counts_and_plausibility_passed": True,
        "controller_only_deltas": deltas,
    }


def _artifact_descriptor(instance_id: str, node: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    content = node.get("artifact_content")
    digest = ce.sha256(content)
    artifact_ref = f"art-{ce.sha256([instance_id, node['job_id'], node['native_node_ref'], digest])[7:23]}"
    kind = str(node.get("artifact_kind") or "record")
    rows = len(content.get("rows", [])) if kind == "table" and isinstance(content, Mapping) else None
    columns = list(map(str, content.get("columns", []))) if kind == "table" and isinstance(content, Mapping) else []
    inspections = ["describe", "read", "full"] + (["python"] if kind == "table" else [])
    return {
        "artifact_ref": artifact_ref, "kind": kind, "rows": rows, "columns": columns,
        "captured_value_sha256": digest,
        "capture_truncated": bool(node.get("artifact_truncated")),
        "available_inspections": inspections,
    }, artifact_ref


def _payload_lazy_catalogue(catalogue: Mapping[str, Any], instance_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    reviewer_nodes: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, Any] = {}
    omissions = []
    body_keys = {"artifact_content", "value_preview", "raw_value", "value", "content", "rows", "text"}
    for job_id in JOB_ORDER:
        for original in catalogue["jobs"][job_id]["native_graph"]["nodes"]:
            node = deepcopy(original)
            paths = []
            payload_values = [original.get(key) for key in ("artifact_content", "value_preview") if original.get(key) is not None]
            for key in list(node):
                value = node[key]
                duplicate = key in body_keys or any(value == payload for payload in payload_values)
                if duplicate:
                    if value is not None:
                        paths.append(key)
                    node.pop(key)
            if original.get("artifact_content") is not None:
                descriptor, artifact_ref = _artifact_descriptor(instance_id, original)
                node["artifact_descriptor"] = descriptor
                operation_node = {
                    "node_ref": artifact_ref,
                    "artifact_kind": original.get("artifact_kind"),
                    "artifact_content": deepcopy(original["artifact_content"]),
                    "artifact_truncated": bool(original.get("artifact_truncated")),
                    "artifact_size": deepcopy(original.get("artifact_size")),
                    "artifact_value_sha256": descriptor["captured_value_sha256"],
                    "raw_metadata": {}, "raw_metadata_sha256": ce.sha256({}),
                }
                artifacts[artifact_ref] = {
                    "artifact_ref": artifact_ref, "job_id": job_id,
                    "native_node_ref": original["native_node_ref"],
                    "complete_native_node": deepcopy(original),
                    "operation_node": operation_node,
                    "descriptor": deepcopy(descriptor),
                }
            reviewer_nodes[original["native_node_ref"]] = node
            if paths:
                omissions.append({
                    "job_id": job_id, "native_node_ref": original["native_node_ref"],
                    "omitted_field_paths": sorted(paths),
                    "complete_node_sha256": ce.sha256(original),
                    "reviewer_node_sha256": ce.sha256(node),
                })
    reviewer = {"schema_version": "n27pb-payload-lazy-native-nodes-1", "nodes": reviewer_nodes}
    reviewer["reviewer_nodes_sha256"] = ce.sha256(reviewer)
    disclosure = {"schema_version": "n27pb-artifact-disclosure-catalogue-1", "artifacts": artifacts}
    disclosure["catalogue_sha256"] = ce.sha256(disclosure)
    manifest = {
        "schema_version": "n27pb-field-omission-manifest-1", "instance": instance_id,
        "omissions": omissions, "artifact_count": len(artifacts),
        "body_keys_withheld": sorted(body_keys),
        "direct_duplicate_scan_passed": True,
    }
    manifest["manifest_sha256"] = ce.sha256(manifest)
    return reviewer, disclosure, manifest


def _lazy_graph(graph: Mapping[str, Any], reviewer: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(graph))
    value["nodes"] = [deepcopy(reviewer["nodes"][node["native_node_ref"]]) for node in graph["nodes"]]
    value.pop("projection_sha256", None)
    value["projection_sha256"] = ce.sha256(value)
    return value


def _assert_payload_lazy(graph: Mapping[str, Any], disclosure: Mapping[str, Any]) -> None:
    encoded = ce.canonical_json(graph)
    for artifact in disclosure["artifacts"].values():
        body = ce.canonical_json(artifact["operation_node"]["artifact_content"])
        preview = artifact["complete_native_node"].get("value_preview")
        if len(body) > 2 and body in encoded:
            raise ValueError("initial graph contains a complete artifact-body duplicate")
        if preview is not None and ce.canonical_json(preview) in encoded:
            raise ValueError("initial graph contains a value-preview duplicate")
    forbidden = {"artifact_content", "value_preview", "raw_value"}
    if any(forbidden & set(node) for node in graph.get("nodes", [])):
        raise ValueError("payload-lazy graph retained a value field")


def _load_prepared(target: Path) -> dict[str, Any]:
    folders = {
        "captures": "captures", "catalogues": "catalogues", "instances": "instances",
        "source_bundles": "source-bundles", "crosswalks": "native-crosswalks",
        "indexes": "native-subtree-index", "reviewer_nodes": "payload-lazy-nodes",
        "disclosures": "artifact-disclosures", "omissions": "omission-manifests",
    }
    values = {name: {path.stem: _json(path) for path in sorted((target / folder).glob("*.json"))} for name, folder in folders.items()}
    if any(set(collection) != set(INSTANCES) for collection in values.values()):
        raise ValueError("Attempt 046 prepared record set is partial")
    for instance_id in INSTANCES:
        values["source_bundles"][instance_id] = values["source_bundles"][instance_id]["source_bundle"]
    return values


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PB is authorized only for Attempt 046")
    authority = _verify_authority(repo_root)
    if (target / "captures").exists():
        return _load_prepared(target) | {"authority": authority}
    contract = {
        "schema_version": "n27pb-common-reviewer-contract-1",
        "status": "frozen_before_mutant_construction",
        "review_task": TASK_TEXT, "behavioural_criteria": CONTRACT_CRITERIA,
        "fault_specific_terms_absent": True, "mutation_records_existing_at_freeze": 0,
    }
    contract["contract_sha256"] = ce.sha256(contract)
    ce._write_immutable(target / COMMON_CONTRACT, contract)
    clean_source = (repo_root / UPSTREAM_SOURCE).read_text()
    prepared = {name: {} for name in ("captures", "catalogues", "instances", "source_bundles", "crosswalks", "indexes", "reviewer_nodes", "disclosures", "omissions")}
    topology = {}
    for instance_id in INSTANCES:
        source, mutation = _mutant_source(clean_source, instance_id)
        capture, source_bundle = _capture_instance(repo_root, target, instance_id, source)
        catalogue, crosswalk = n27p._catalogue(capture)
        catalogue["schema_version"] = "n27pb-four-job-native-catalogue-1"
        catalogue.pop("catalogue_sha256", None)
        catalogue["catalogue_sha256"] = ce.sha256(catalogue)
        compact, index = n27p.build_compact_graph(catalogue, crosswalk)
        topology[instance_id] = n27pa._topology_qualification(catalogue, index)
        reviewer, disclosure, omission = _payload_lazy_catalogue(catalogue, instance_id)
        lazy_compact = _lazy_graph(compact, reviewer)
        _assert_payload_lazy(lazy_compact, disclosure)
        instance = {
            "schema_version": "n27pb-instance-1", "opaque_instance_id": instance_id,
            "designation": "matched_clean_control" if TRUTH[instance_id] is None else "upstream_fault",
            "truth_job": None if TRUTH[instance_id] is None else UPSTREAM,
            "truth_function": TRUTH[instance_id], "mutation": mutation,
            "matched_clean_case": MATCHED_CLEAN.get(instance_id),
            "capture_sha256": capture["capture_sha256"], "catalogue_sha256": catalogue["catalogue_sha256"],
            "source_sha256": deepcopy(capture["source_sha256"]),
        }
        instance["instance_sha256"] = ce.sha256(instance)
        records = {
            "captures": capture, "catalogues": catalogue, "source_bundles": {"source_bundle": source_bundle},
            "crosswalks": crosswalk, "indexes": index, "reviewer_nodes": reviewer,
            "disclosures": disclosure, "omissions": omission, "instances": instance,
        }
        folder = {
            "captures": "captures", "catalogues": "catalogues", "source_bundles": "source-bundles",
            "crosswalks": "native-crosswalks", "indexes": "native-subtree-index",
            "reviewer_nodes": "payload-lazy-nodes", "disclosures": "artifact-disclosures",
            "omissions": "omission-manifests", "instances": "instances",
        }
        for name, record in records.items():
            ce._write_immutable(target / folder[name] / f"{instance_id}.json", record)
            prepared[name][instance_id] = source_bundle if name == "source_bundles" else record
        ce._write_immutable(target / "projections" / f"{instance_id}-compact.json", lazy_compact)
        for job_id in JOB_ORDER:
            raw = capture["jobs"][job_id]["native_lineage"]
            export = target / "native-exports" / instance_id / job_id / "etiq-native-lineage.json"
            ce._write_immutable(export, raw)
            job_record = {
                "schema_version": "n27pb-fresh-native-job-capture-1", "instance": instance_id,
                "job_id": job_id, "capture_status": "fresh_n27pb_execution",
                "native_export_file_sha256": ce.sha256(export.read_bytes()),
                "native_export_logical_sha256": ce.sha256(raw),
                "job_capture_sha256": ce.sha256(capture["jobs"][job_id]),
            }
            job_record["record_sha256"] = ce.sha256(job_record)
            ce._write_immutable(target / "job-captures" / instance_id / f"{job_id}.json", job_record)
    hard = _hard_fault_qualification(prepared["captures"])
    hard["qualification_sha256"] = ce.sha256(hard)
    ce._write_immutable(target / "qualification/hard-faults.json", hard)
    capture_qualification = {
        "schema_version": "n27pb-native-capture-qualification-1", "status": "passed",
        "instances": 5, "fresh_job_executions": 20, "etiq_version": "2.3.0",
        "required_api": 'create_full_lineage_graph(graph_format="json")',
        "topology": topology, "all_native_objects_edges_preserved": True,
    }
    capture_qualification["qualification_sha256"] = ce.sha256(capture_qualification)
    ce._write_immutable(target / "qualification/native-captures.json", capture_qualification)
    return prepared | {"authority": authority}


def _node_signature(nodes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(nodes)
    return {
        "native_kind": dict(sorted(Counter(str(value["native_kind"]) for value in values).items())),
        "native_cluster_depth": dict(sorted(Counter(str(value.get("native_cluster_depth")) for value in values).items())),
        "inspectable_artifacts": sum("artifact_descriptor" in value for value in values),
    }


def _degree_multiset(nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> list[list[int]]:
    edge_list = list(edges)
    return sorted([
        [sum(edge["source_ref"] == ref for edge in edge_list), sum(edge["target_ref"] == ref for edge in edge_list)]
        for ref in (node["native_node_ref"] for node in nodes)
    ])


def random_structural_graph(
    catalogue: Mapping[str, Any], full_compact: Mapping[str, Any], lazy_compact: Mapping[str, Any],
    reviewer: Mapping[str, Any], index: Mapping[str, Any], seed: int,
) -> dict[str, Any]:
    pools: dict[str, list[dict[str, Any]]] = {}
    anchors: dict[str, set[str]] = {}
    targets: dict[str, set[str]] = {}
    for job_id in JOB_ORDER:
        candidates = n27pa._random_candidates(catalogue, full_compact, index, job_id)
        target = {node["native_node_ref"] for node in full_compact["nodes"] if node["job_id"] == job_id}
        candidate_sets = [{node["native_node_ref"] for node in candidate["nodes"]} for candidate in candidates]
        unavoidable = set.intersection(target, *candidate_sets) if candidate_sets else set()
        for candidate, refs in zip(candidates, candidate_sets):
            left, right = target - unavoidable, refs - unavoidable
            candidate["replaceable_jaccard"] = len(left & right) / max(1, len(left | right))
            candidate["lazy_nodes"] = [deepcopy(reviewer["nodes"][node["native_node_ref"]]) for node in candidate["nodes"]]
        candidates.sort(key=lambda value: (value["replaceable_jaccard"], ce.sha256(value["nodes"])))
        pools[job_id] = candidates[:12]
        anchors[job_id] = unavoidable
        targets[job_id] = target
    target_tokens = n25._token_count({key: lazy_compact[key] for key in ("nodes", "relationships", "native_clusters", "collapsed_execution_groups")})
    eligible = []
    for combination in product(*(pools[job] for job in JOB_ORDER)):
        structural = {
            "nodes": [node for candidate in combination for node in candidate["lazy_nodes"]],
            "relationships": [edge for candidate in combination for edge in candidate["relationships"]],
            "native_clusters": [cluster for candidate in combination for cluster in candidate["native_clusters"]],
            "collapsed_execution_groups": [group for candidate in combination for group in candidate["collapsed_execution_groups"]],
        }
        tokens = n25._token_count(structural)
        difference = abs(tokens - target_tokens) / max(1, target_tokens)
        if difference <= 0.05:
            selected_refs = {node["native_node_ref"] for node in structural["nodes"]}
            target_refs = set().union(*targets.values())
            unavoidable = set().union(*anchors.values())
            left, right = target_refs - unavoidable, selected_refs - unavoidable
            overlap = len(left & right) / max(1, len(left | right))
            eligible.append((overlap, difference, tokens, combination, structural))
    if not eligible:
        raise ValueError("Random Matched has no honest token-matched native draw")
    minimum = min(value[0] for value in eligible)
    best = [value for value in eligible if value[0] == minimum]
    generator = random.Random(seed)
    overlap, difference, tokens, combination, structural = best[generator.randrange(len(best))]
    if overlap > 0.50:
        raise ValueError(f"Random Matched replaceable overlap exceeds 0.50: {overlap}")
    diagnostics = {}
    for job_id, candidate in zip(JOB_ORDER, combination):
        target_nodes = [node for node in lazy_compact["nodes"] if node["job_id"] == job_id]
        target_edges = [edge for edge in lazy_compact["relationships"] if edge["job_id"] == job_id]
        if (
            len(candidate["lazy_nodes"]) != len(target_nodes)
            or len(candidate["relationships"]) != len(target_edges)
            or _node_signature(candidate["lazy_nodes"]) != _node_signature(target_nodes)
            or _degree_multiset(candidate["lazy_nodes"], candidate["relationships"]) != _degree_multiset(target_nodes, target_edges)
        ):
            raise ValueError(f"Random Matched structural stratum failed: {job_id}")
        target_classes = Counter(group["hidden_size_class"] for group in lazy_compact["collapsed_execution_groups"] if group["job_id"] == job_id)
        observed_classes = Counter(group["hidden_size_class"] for group in candidate["collapsed_execution_groups"])
        if len(candidate["collapsed_execution_groups"]) != 3 or target_classes != observed_classes:
            raise ValueError(f"Random Matched collapsed-group stratum failed: {job_id}")
        diagnostics[job_id] = {
            "draw_pool": len(pools[job_id]),
            "unavoidable_interface_anchor_refs": sorted(anchors[job_id]),
            "selected_node_refs": [node["native_node_ref"] for node in candidate["lazy_nodes"]],
            "node_count": len(candidate["lazy_nodes"]), "edge_count": len(candidate["relationships"]),
            "node_signature": _node_signature(candidate["lazy_nodes"]),
            "directed_degree_multiset": _degree_multiset(candidate["lazy_nodes"], candidate["relationships"]),
            "collapsed_group_count": len(candidate["collapsed_execution_groups"]),
            "hidden_size_classes": dict(sorted(observed_classes.items())),
        }
    value = {
        "job_evidence_order": deepcopy(lazy_compact["job_evidence_order"]),
        **structural, "disclosed_execution_groups": [], "handoffs": [],
        "random_structural_match": {
            "selection_rule": "minimum-overlap seeded draw from real native objects and edges",
            "seed_commitment": ce.sha256(["n27pb-random", seed]),
            "uses_truth_or_outcome": False, "eligible_composite_draws": len(eligible),
            "minimum_overlap_ties": len(best), "replaceable_node_jaccard": overlap,
            "target_tokens": target_tokens, "observed_tokens": tokens,
            "relative_token_difference": difference, "jobs": diagnostics,
        },
    }
    value["projection_sha256"] = ce.sha256(value)
    return value


def expand_native_subtree(
    catalogue: Mapping[str, Any], reviewer: Mapping[str, Any], index: Mapping[str, Any],
    package: Mapping[str, Any], group_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = index["groups"].get(group_id)
    graph = package.get("graph_review", {}).get("evidence", {})
    advertised = {group["execution_group_id"] for group in graph.get("collapsed_execution_groups", [])}
    if binding is None or group_id not in advertised:
        raise ValueError("native subtree identifier is not currently advertised")
    all_edges = [edge for job in JOB_ORDER for edge in catalogue["jobs"][job]["native_graph"]["edges"]]
    all_clusters = {cluster["native_cluster_ref"]: cluster for job in JOB_ORDER for cluster in catalogue["jobs"][job]["native_graph"]["clusters"]}
    updated = deepcopy(dict(package))
    evidence = updated["graph_review"]["evidence"]
    existing = {node["native_node_ref"] for node in evidence["nodes"]}
    added = [deepcopy(reviewer["nodes"][ref]) for ref in binding["node_refs"] if ref not in existing]
    evidence["nodes"].extend(added)
    visible = {node["native_node_ref"] for node in evidence["nodes"]}
    old_edges = {edge["native_edge_ref"] for edge in evidence["relationships"]}
    added_edges = [deepcopy(edge) for edge in all_edges if edge["source_ref"] in visible and edge["target_ref"] in visible and edge["native_edge_ref"] not in old_edges]
    evidence["relationships"].extend(added_edges)
    evidence["native_clusters"] = [cluster for cluster in evidence["native_clusters"] if cluster["native_cluster_ref"] != group_id]
    evidence["native_clusters"].extend(deepcopy(all_clusters[ref]) for ref in binding["cluster_refs"])
    descriptor = next(group for group in evidence["collapsed_execution_groups"] if group["execution_group_id"] == group_id)
    evidence["collapsed_execution_groups"] = [group for group in evidence["collapsed_execution_groups"] if group["execution_group_id"] != group_id]
    evidence["disclosed_execution_groups"].append(deepcopy(descriptor))
    evidence.pop("projection_sha256", None)
    evidence["projection_sha256"] = ce.sha256(evidence)
    artifact_refs = [node["artifact_descriptor"]["artifact_ref"] for node in added if "artifact_descriptor" in node]
    if not added or not added_edges or not artifact_refs:
        raise ValueError("native subtree does not disclose structure and an inspectable artifact")
    return updated, {
        "operation": "expand_execution_group", "status": "completed",
        "execution_group_id": group_id, "job_id": descriptor["job_id"],
        "captured_function_label": descriptor["captured_function_label"],
        "nodes_added": [node["native_node_ref"] for node in added],
        "relationships_added": [edge["native_edge_ref"] for edge in added_edges],
        "clusters_added": deepcopy(binding["cluster_refs"]),
        "newly_disclosed_artifact_refs": artifact_refs,
        "evidence_bytes_added": len(ce.canonical_json({"nodes": added, "relationships": added_edges})),
    }


def adaptive_relevance(prepared: Mapping[str, Any], target: Path) -> dict[str, Any]:
    results = {}
    for instance_id, truth in TRUTH.items():
        if truth is None:
            continue
        clean_id = MATCHED_CLEAN[instance_id]
        catalogue = prepared["catalogues"][instance_id]
        clean_nodes = prepared["catalogues"][clean_id]["jobs"][UPSTREAM]["nodes"]
        clean_hashes: dict[tuple[Any, ...], set[str]] = {}
        for node in clean_nodes:
            key = (node.get("line_no"), node.get("state_type"), tuple(node.get("names", [])))
            if node.get("artifact_value_sha256"):
                clean_hashes.setdefault(key, set()).add(str(node["artifact_value_sha256"]))
        mutation = prepared["instances"][instance_id]["mutation"]
        candidates = []
        for node in catalogue["jobs"][UPSTREAM]["nodes"]:
            key = (node.get("line_no"), node.get("state_type"), tuple(node.get("names", [])))
            stack = ",".join(map(str, node.get("func_stack", [])))
            if (
                node.get("artifact_value_sha256") and truth in stack
                and int(node.get("line_no") or 0) >= int(mutation["original_span"]["start_line"])
                and str(node["artifact_value_sha256"]) not in clean_hashes.get(key, set())
            ):
                candidates.append(node)
        candidates.sort(key=lambda node: (int(node.get("line_no") or 0), str(node["node_ref"])))
        if not candidates:
            raise ValueError(f"no exact directly affected captured state: {instance_id}")
        canonical = candidates[0]
        mappings = prepared["crosswalks"][instance_id]["jobs"][UPSTREAM]["crosswalk"]
        matches = [item for item in mappings if item["match_status"] == "exact" and canonical["node_ref"] in item["canonical_node_refs"]]
        if len(matches) > 1:
            native_by_ref = {node["native_node_ref"]: node for node in catalogue["jobs"][UPSTREAM]["native_graph"]["nodes"]}
            name = str(canonical.get("names", [""])[0])
            base = name.split("(", 1)[0].split("[", 1)[0]
            preferred = [
                item for item in matches
                if base and base in native_by_ref[item["native_node_ref"]]["native_label"]
                and not native_by_ref[item["native_node_ref"]]["native_label"].startswith("Anonymous")
            ]
            if len(preferred) == 1:
                matches = preferred
        if len(matches) != 1:
            raise ValueError(f"affected-state native crosswalk is ambiguous: {instance_id}")
        native_ref = matches[0]["native_node_ref"]
        compact = _json(target / "projections" / f"{instance_id}-compact.json")
        visible = {node["native_node_ref"] for node in compact["nodes"]}
        groups = [group_id for group_id, binding in prepared["indexes"][instance_id]["groups"].items() if native_ref in binding["node_refs"]]
        if len(groups) != 1 or native_ref in visible:
            raise ValueError(f"affected state is not uniquely hidden in one subtree: {instance_id}")
        group_id = groups[0]
        if prepared["indexes"][instance_id]["groups"][group_id]["descriptor"]["captured_function_label"] != truth:
            raise ValueError(f"affected state is outside truth subtree: {instance_id}")
        simulated, event = expand_native_subtree(catalogue, prepared["reviewer_nodes"][instance_id], prepared["indexes"][instance_id], {"graph_review": {"evidence": compact}}, group_id)
        affected = prepared["reviewer_nodes"][instance_id]["nodes"][native_ref]
        if native_ref not in event["nodes_added"] or "artifact_descriptor" not in affected:
            raise ValueError(f"affected state is not inspectable after disclosure: {instance_id}")
        results[instance_id] = {
            "truth_function": truth,
            "proof_basis": "first captured state in the mutated scope whose exact frozen artifact differs from the matched clean execution",
            "function_name_match_alone_used_as_relevance_proof": False,
            "canonical_state_ref": canonical["node_ref"], "native_node_ref": native_ref,
            "artifact_ref": affected["artifact_descriptor"]["artifact_ref"],
            "model_selectable_execution_group_id": group_id,
            "initially_hidden": True, "disclosed_by_complete_subtree": True,
            "expanded_projection_sha256": simulated["graph_review"]["evidence"]["projection_sha256"],
        }
    selectable = {}
    for instance_id in INSTANCES:
        compact = _json(target / "projections" / f"{instance_id}-compact.json")
        rows = {}
        for group in compact["collapsed_execution_groups"]:
            _, event = expand_native_subtree(
                prepared["catalogues"][instance_id], prepared["reviewer_nodes"][instance_id],
                prepared["indexes"][instance_id], {"graph_review": {"evidence": compact}}, group["execution_group_id"],
            )
            rows[group["execution_group_id"]] = len(event["newly_disclosed_artifact_refs"])
        if len(rows) != 12 or any(count < 1 for count in rows.values()):
            raise ValueError(f"not every selectable group has a newly disclosed artifact: {instance_id}")
        selectable[instance_id] = rows
    record = {
        "schema_version": "n27pb-adaptive-relevance-1", "status": "passed",
        "faults": results, "inspectable_artifacts_per_selectable_group": selectable,
    }
    record["qualification_sha256"] = ce.sha256(record)
    return record


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
                "boundary_id": boundary["boundary_id"], "job_id": job_id,
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
        raise ValueError("semantic declaration bundle does not cover all 12 functions")
    return {"semantic_declarations": values}


def _base_package(catalogue: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "n27pb-review-package-1",
        "review_task": contract["review_task"],
        "behavioural_criteria": deepcopy(contract["behavioural_criteria"]),
        "pipeline_topology": [
            {"job": f"job_{position}", "captured_job_id": job_id, "position": position, "observation_point": job_id == JOB4}
            for position, job_id in enumerate(JOB_ORDER, 1)
        ],
        "top_level_demand_input": deepcopy(catalogue["jobs"][UPSTREAM]["input"]),
        "capability_fixture": deepcopy(catalogue["jobs"][DOWNSTREAM]["input"]["capabilities"]),
        "delivery_rules_fixture": deepcopy(DELIVERY_RULES),
        "observed_job_4_execution": _execution_record(catalogue, JOB4),
        "final_response_contract": {
            "fault_detected": "Boolean", "suspect_job": "job_1, job_2, job_3, job_4, or null",
            "suspect_function": "a function visible in supplied evidence, or null",
            "explanation": "concise evidence-grounded reasoning",
            "cited_evidence": "structured opaque references or short exact visible excerpts",
        },
    }


def build_package(
    catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]],
    graphs: Mapping[str, Mapping[str, Any]], contract: Mapping[str, Any],
    mode: str, source_setting: str, declaration_setting: str,
) -> dict[str, Any]:
    package = _base_package(catalogue, contract)
    if mode == "P04":
        records = []
        for job_id in JOB_ORDER[:3]:
            record = _execution_record(catalogue, job_id)
            record["chronology"] = {"position": JOB_ORDER.index(job_id) + 1, "precedes": f"job_{JOB_ORDER.index(job_id) + 2}"}
            record["exact_outgoing_handoffs"] = [deepcopy(value) for value in catalogue["handoffs"] if value["upstream_job_id"] == job_id]
            records.append(record)
        package["history"] = {"prior_task_records": records}
    if mode in GRAPH_MODES:
        if mode == "P05":
            compact = graphs["compact"]
            evidence = {
                "job_evidence_order": deepcopy(compact["job_evidence_order"]),
                "nodes": deepcopy(compact["nodes"]), "relationships": [],
                "native_clusters": [], "collapsed_execution_groups": [],
                "disclosed_execution_groups": [], "handoffs": [],
            }
            evidence["projection_sha256"] = ce.sha256(evidence)
        elif mode == "P13":
            evidence = deepcopy(graphs["full"])
        elif mode == "P14":
            evidence = deepcopy(graphs["random"])
            evidence.pop("random_structural_match", None)
            evidence.pop("projection_sha256", None)
            evidence["projection_sha256"] = ce.sha256(evidence)
        else:
            evidence = deepcopy(graphs["compact"])
        package["graph_review"] = {"framing": "Captured native execution structure may be used in the assessment.", "evidence": evidence}
    if source_setting == "S1":
        package["separate_complete_source_bundle"] = deepcopy(source_bundle)
    if declaration_setting == "B1":
        package["semantic_declaration_bundle"] = _semantic_declarations(catalogue)
    if mode in {"P09", "P13", "P14"}:
        package["available_operations"] = ["artifact_inspection"]
        package["interaction_contract"] = {
            "operation": "artifact_inspection", "model_selects_artifact_and_mode": True,
            "required_before_terminal": True, "maximum_completed_inspections": 1,
        }
    elif mode in {"P10", "P11"}:
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {
            "operation": "expand_execution_group_then_artifact_inspection",
            "model_selects_group_artifact_and_mode": True,
            "required_before_terminal": True, "maximum_completed_expansions": 1,
            "maximum_completed_inspections": 1,
        }
    elif mode == "P12":
        package["available_operations"] = ["reconsider_same_evidence"]
        package["interaction_contract"] = {
            "operation": "reconsider_same_evidence", "required_passes": 2,
            "evidence_bytes_added_each_pass": 0,
        }
    return package


def schedule() -> dict[str, Any]:
    cells = []
    for instance_id in INSTANCES:
        for cell_id in CELLS:
            mode, source, declaration = cell_id.split("-")
            cells.append({
                "opaque_instance_id": instance_id, "cell_id": cell_id, "mode": mode,
                "mode_name": MODE_NAMES[mode], "source_setting": source,
                "declaration_setting": declaration,
                "branch_id": f"brn-{ce.sha256(['n27pb', instance_id, cell_id])[7:23]}",
            })
    reviews = []
    for repetition in (1, 2):
        order = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for block, instance_id in enumerate(order):
            values = [value for value in cells if value["opaque_instance_id"] == instance_id]
            rotation = (block + repetition) % len(values)
            for cell in values[rotation:] + values[:rotation]:
                reviews.append({
                    **cell, "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n27pb', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if (len(cells), len(reviews), len({row["trial_id"] for row in reviews})) != (70, 140, 140):
        raise AssertionError("N27PB schedule counts changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _package_records(target: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((target / "controller-manifests").glob("*.json")):
        manifest = _json(path)
        package_path = target / manifest["reviewer_package_path"]
        if ce.sha256(package_path.read_bytes()) != manifest["reviewer_package_file_sha256"]:
            raise ValueError("reviewer package file binding changed")
        record = _json(package_path)
        ce._verified_self_hash(record, "package_sha256")
        records.append(record)
    return records


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in package.items() if key not in {"available_operations", "interaction_contract"}}


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by = {(row["controller_condition"]["opaque_instance_id"], row["controller_condition"]["cell_id"]): row["reviewer_package"] for row in records}
    specs = (
        ("source", "P01-S0-B0", "P02-S1-B0", {"separate_complete_source_bundle"}, False),
        ("declarations", "P02-S1-B0", "P03-S1-B1", {"semantic_declaration_bundle"}, False),
        ("history", "P02-S1-B0", "P04-S1-B0", {"history"}, False),
        ("compact_structure", "P01-S0-B0", "P06-S0-B0", {"graph_review"}, False),
        ("compact_source", "P06-S0-B0", "P07-S1-B0", {"separate_complete_source_bundle"}, False),
        ("compact_declarations", "P07-S1-B0", "P08-S1-B1", {"semantic_declaration_bundle"}, False),
        ("compact_nodes", "P02-S1-B0", "P05-S1-B0", {"graph_review"}, False),
        ("connectivity_groups", "P05-S1-B0", "P07-S1-B0", {"graph_review"}, False),
        ("adaptive_source", "P10-S0-B0", "P11-S1-B0", {"separate_complete_source_bundle"}, False),
        ("compact_full", "P09-S1-B0", "P13-S1-B0", {"graph_review"}, False),
        ("selected_random", "P09-S1-B0", "P14-S1-B0", {"graph_review"}, False),
    )
    rows = []
    for instance_id in INSTANCES:
        for name, left_id, right_id, roots, initial in specs:
            left, right = by[(instance_id, left_id)], by[(instance_id, right_id)]
            if initial:
                left, right = _initial_evidence(left), _initial_evidence(right)
            paths = n25._diff_paths(left, right)
            passed = bool(paths) and all(path.split(".")[1] in roots for path in paths)
            rows.append({"instance": instance_id, "invariant": name, "left": left_id, "right": right_id, "differing_paths": paths, "passed": passed})
        compact_ids = ("P07-S1-B0", "P09-S1-B0", "P11-S1-B0", "P12-S1-B0")
        graph_hashes = [ce.sha256(by[(instance_id, cell)]["graph_review"]["evidence"]) for cell in compact_ids]
        rows.append({"instance": instance_id, "invariant": "identical_compact_initial_graph", "cells": compact_ids, "passed": len(set(graph_hashes)) == 1})
    if not all(row["passed"] for row in rows):
        raise ValueError(f"pairwise isolation failed: {[row for row in rows if not row['passed']][:2]}")
    return rows


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    visible = ce.canonical_json(request).decode()
    forbidden = ("opaque_instance_id", "cell_id", "source_setting", "declaration_setting", "branch_id", "trial_id", "repetition", "truth_job", "truth_function", "designation", "mutation", "oracle", "clean_job4_sha256", "random_structural_match")
    if any(f'"{key}"' in visible for key in forbidden) or any(instance in visible for instance in INSTANCES):
        raise ValueError("rendered request leaks controller-only state")
    return request


def _schema_for_stage(stage: str) -> Path:
    return {"final": FINAL_SCHEMA, "group": GROUP_SCHEMA, "artifact": ARTIFACT_SCHEMA, "reconsider": RECONSIDER_SCHEMA}[stage]


def validate_schemas(repo_root: Path) -> dict[str, str]:
    results = {}
    for path in (FINAL_SCHEMA, GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA):
        schema = _json(repo_root / path)
        Draft202012Validator.check_schema(schema)
        validate_strict_provider_schema(schema)
        results[path.as_posix()] = ce.sha256((repo_root / path).read_bytes())
    return results


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(records), len(design["review_trials"])) != (70, 140):
        raise ValueError("package/review counts changed")
    schemas = validate_schemas(repo_root)
    pairwise = _pairwise_checks(records)
    maximum = 0
    full_artifact_maximum = 0
    contract = _json(target / COMMON_CONTRACT)
    contract_bytes = ce.canonical_json(contract["behavioural_criteria"])
    for record in records:
        condition, package = record["controller_condition"], record["reviewer_package"]
        if ce.canonical_json(package["behavioural_criteria"]) != contract_bytes:
            raise ValueError("common reviewer contract differs across packages")
        maximum = max(maximum, n25._token_count(render_request(package)))
        if "graph_review" in package:
            _assert_payload_lazy(package["graph_review"]["evidence"], prepared["disclosures"][condition["opaque_instance_id"]])
        if condition["declaration_setting"] == "B1" and len(package["semantic_declaration_bundle"]["semantic_declarations"]) != 12:
            raise ValueError("B1 declaration coverage changed")
    for instance_id in INSTANCES:
        disclosure = prepared["disclosures"][instance_id]
        for artifact in disclosure["artifacts"].values():
            full_artifact_maximum = max(full_artifact_maximum, n25._token_count(artifact["operation_node"]["artifact_content"]))
    if max(maximum, full_artifact_maximum) >= 100_000:
        raise ValueError("complete graph or artifact does not fit the qualified provider context allowance")
    expected_calls = sum({"P01": 1, "P02": 1, "P03": 1, "P04": 1, "P05": 1, "P06": 1, "P07": 1, "P08": 1, "P09": 2, "P10": 3, "P11": 3, "P12": 3, "P13": 2, "P14": 2}[trial["mode"]] for trial in design["review_trials"])
    if expected_calls != 230:
        raise ValueError("planned call count changed")
    return {
        "schema_version": "n27pb-no-model-verification-1", "status": "passed", "model_calls": 0,
        "instances": 5, "fresh_job_executions": 20, "packages": 70, "terminal_reviews": 140,
        "required_follow_up_calls": 90, "planned_provider_calls": 230, "repairs": 0,
        "strict_schema_hashes": schemas, "pairwise_checks": len(pairwise),
        "maximum_initial_request_tokens": maximum,
        "maximum_complete_artifact_tokens": full_artifact_maximum,
        "provider_context_qualification_limit": 100_000,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if len(existing) == 70:
        qualification = qualify_packages(repo_root, target, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    relevance = adaptive_relevance(prepared, target)
    ce._write_immutable(target / "qualification/adaptive-fault-relevance.json", relevance)
    graphs = {}
    random_records = {}
    for instance_id in INSTANCES:
        catalogue = prepared["catalogues"][instance_id]
        compact = _json(target / "projections" / f"{instance_id}-compact.json")
        full_path = target / "projections" / f"{instance_id}-full.json"
        random_path = target / "projections" / f"{instance_id}-random.json"
        if full_path.exists() and random_path.exists():
            full, random_graph = _json(full_path), _json(random_path)
        else:
            full_compact, _ = n27p.build_compact_graph(catalogue, prepared["crosswalks"][instance_id])
            full = _lazy_graph(n27p.full_graph(catalogue), prepared["reviewer_nodes"][instance_id])
            seed = int(ce.sha256([prepared["captures"][instance_id]["capture_sha256"], "n27pb-random-structural"])[7:23], 16)
            random_graph = random_structural_graph(
                catalogue, full_compact, compact, prepared["reviewer_nodes"][instance_id],
                prepared["indexes"][instance_id], seed,
            )
        _assert_payload_lazy(full, prepared["disclosures"][instance_id])
        _assert_payload_lazy(random_graph, prepared["disclosures"][instance_id])
        graphs[instance_id] = {"compact": compact, "full": full, "random": random_graph}
        random_records[instance_id] = deepcopy(random_graph["random_structural_match"])
        ce._write_immutable(full_path, full)
        ce._write_immutable(random_path, random_graph)
    random_qualification = {
        "schema_version": "n27pb-random-structural-qualification-1", "status": "passed",
        "instances": random_records, "all_strata_matched": True,
        "replaceable_jaccard_maximum": max(value["replaceable_node_jaccard"] for value in random_records.values()),
        "required_maximum": 0.50, "token_tolerance": 0.05,
        "selection_uses_truth_or_outcome": False,
    }
    random_qualification["qualification_sha256"] = ce.sha256(random_qualification)
    ce._write_immutable(target / "qualification/random-structural-matches.json", random_qualification)
    contract = _json(target / COMMON_CONTRACT)
    existing_by_branch = {record["controller_condition"]["branch_id"]: record for record in existing}
    records = []
    for condition in design["cells"]:
        if condition["branch_id"] in existing_by_branch:
            records.append(existing_by_branch[condition["branch_id"]])
            continue
        instance_id = condition["opaque_instance_id"]
        package = build_package(
            prepared["catalogues"][instance_id], prepared["source_bundles"][instance_id],
            graphs[instance_id], contract, condition["mode"],
            condition["source_setting"], condition["declaration_setting"],
        )
        record = {
            "schema_version": "n27pb-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance_id]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance_id]["catalogue_sha256"],
            "disclosure_catalogue_sha256": prepared["disclosures"][instance_id]["catalogue_sha256"],
            "omission_manifest_sha256": prepared["omissions"][instance_id]["manifest_sha256"],
            "common_contract_sha256": contract["contract_sha256"],
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        path = target / "packages" / condition["branch_id"] / "reviewer-package.json"
        ce._write_immutable(path, record)
        manifest = {
            "schema_version": "n27pb-controller-manifest-1",
            "controller_condition": deepcopy(condition),
            "reviewer_package_path": path.relative_to(target).as_posix(),
            "reviewer_package_file_sha256": ce.sha256(path.read_bytes()),
            "package_sha256": record["package_sha256"],
        }
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{condition['branch_id']}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, target, records, prepared, design)
    pairwise = {"schema_version": "n27pb-pairwise-package-differences-1", "rows": _pairwise_checks(records), "all_passed": True}
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {"schema_version": "n27pb-review-design-1", "review_trials": design["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n27pb-repair-design-1", "repair_traces": []})
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27pb_experiment.py"), PROMPT, FINAL_SCHEMA,
        GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27pb_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 046 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after live reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("focused N27PB tests must pass before freeze")
    freeze = {
        "schema_version": "n27pb-experiment-freeze-1", "attempt": "046",
        "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "source_hashes": deepcopy(SOURCE_HASHES), "attempt_045_hashes": deepcopy(ATTEMPT_045_HASHES),
        "sandbox_gate_file_sha256": ce.sha256((repo_root / SANDBOX_GATE).read_bytes()),
        "sandbox_bindings": deepcopy(built["prepared"]["authority"]["sandbox"]),
        "common_contract_file_sha256": ce.sha256((target / COMMON_CONTRACT).read_bytes()),
        "hard_fault_file_sha256": ce.sha256((target / "qualification/hard-faults.json").read_bytes()),
        "native_capture_file_sha256": ce.sha256((target / "qualification/native-captures.json").read_bytes()),
        "adaptive_relevance_file_sha256": ce.sha256((target / "qualification/adaptive-fault-relevance.json").read_bytes()),
        "random_structural_file_sha256": ce.sha256((target / "qualification/random-structural-matches.json").read_bytes()),
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
        "expected_counts": {"instances": 5, "fresh_job_executions": 20, "packages": 70, "reviews": 140, "follow_up_calls": 90, "provider_calls": 230, "repairs": 0},
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
    return {"status": "verified", "freeze_sha256": digest, "packages": 70, "reviews": 140, "provider_calls": 230, "repairs": 0, "qualification": built["qualification"]}


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("live authority must be consumed before reviews")
    freeze = _json(target / "experiment-freeze.json")
    record = {
        "schema_version": "n27pb-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "one_use_live_authority": True,
        "authorized_calls": 230, "repairs": 0,
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], stage: str) -> dict[str, Any]:
    schema = _json(repo_root / _schema_for_stage(stage))
    scientific = {key: deepcopy(response.get(key)) for key in schema["required"]}
    Draft202012Validator(schema).validate(scientific)
    visible = ce.canonical_json(package).decode()
    function = n25._normalized_function(scientific["suspect_function"])
    opaque_pattern = re.compile(r"(?:native-(?:node|edge|cluster)-j\d+-\d+|art-[0-9a-f]{16}|rb-opaque-j\d+-\d+)")
    cited_refs = [ref for citation in scientific["cited_evidence"] for ref in opaque_pattern.findall(str(citation))]
    return {
        "valid": True, "receipt": scientific,
        "fault_detected": bool(scientific["fault_detected"]),
        "suspect_job": scientific["suspect_job"],
        "normalized_suspect_function": function,
        "suspect_function_visible": function is None or function in visible.lower(),
        "parsed_evidence_refs": cited_refs,
        "invalid_evidence_refs": [ref for ref in cited_refs if ref not in visible],
    }


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


def _provider_review(repo_root: Path, target: Path, request: Mapping[str, Any], parent_id: str, stage: str) -> dict[str, Any]:
    started = time.monotonic()
    response = ce._provider_call(
        repo_root, target, kind="review", model_request=request,
        controller_parent_id=parent_id, review_prompt=PROMPT,
        review_schema=_schema_for_stage(stage),
    )
    return {**response, "n27pb_latency_seconds": time.monotonic() - started}


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count", "n27pb_latency_seconds")}


def _usage(response: Mapping[str, Any], purpose: str) -> dict[str, Any]:
    return {
        **ce.actual_usage_record(response, purpose=purpose, phase="n27pb_pilot_review"),
        "latency_seconds": response.get("n27pb_latency_seconds"),
    }


def _visible_artifacts(package: Mapping[str, Any]) -> set[str]:
    return {
        node["artifact_descriptor"]["artifact_ref"]
        for node in package.get("graph_review", {}).get("evidence", {}).get("nodes", [])
        if "artifact_descriptor" in node
    }


def inspect_artifact(
    repo_root: Path, catalogue: Mapping[str, Any], package: Mapping[str, Any],
    request: Mapping[str, Any], allowed_refs: set[str] | None = None,
) -> dict[str, Any]:
    artifact_ref = str(request.get("artifact_ref") or "")
    visible = _visible_artifacts(package)
    if artifact_ref not in visible or (allowed_refs is not None and artifact_ref not in allowed_refs):
        raise ValueError("artifact inspection requires an eligible currently visible descriptor")
    artifact = catalogue["artifacts"].get(artifact_ref)
    if artifact is None:
        raise ValueError("artifact reference is absent from the frozen disclosure catalogue")
    mode = str(request.get("inspection") or "")
    if mode not in artifact["descriptor"]["available_inspections"]:
        raise ValueError("inspection mode is not available for this artifact descriptor")
    operation_request = {
        "node_ref": artifact_ref, "inspection": mode,
        "columns": deepcopy(request.get("columns", [])), "start": int(request.get("start", 0)),
        "count": int(request.get("count", 1)), "query": str(request.get("query", "")),
        "code": str(request.get("code", "")), "include_raw_metadata": False,
    }
    operation_package = {
        "available_operations": ["artifact_inspection"],
        "runtime_evidence": {"nodes": [{"node_ref": ref} for ref in sorted(visible)]},
    }
    operation_catalogue = {
        "assigned_job_id": artifact["job_id"],
        "jobs": {artifact["job_id"]: {"nodes": [artifact["operation_node"]]}},
    }
    python_executor = None
    if mode == "python":
        gate = _json(repo_root / SANDBOX_GATE)
        python_executor = operations.signed_catalogue_python_executor(
            gate=gate, expected_gate_sha256=ce.sha256(gate), repo_root=repo_root,
        )
    result = operations.inspect_catalogue_artifact(
        operation_catalogue, operation_package, operation_request,
        python_executor=python_executor,
    )
    return {
        "operation": "artifact_inspection", "status": "completed",
        "artifact_ref": artifact_ref, "native_node_ref": artifact["native_node_ref"],
        "inspection": mode, "request": deepcopy(dict(request)),
        "result": result, "artifact_bytes_returned": len(ce.canonical_json(result)),
        "native_operation_content_bytes": result["artifact_bytes_returned"],
        "returned_value_sha256": ce.sha256(result),
    }


def _diagnosis(validation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fault_detected": validation["fault_detected"], "suspect_job": validation["suspect_job"],
        "suspect_function": validation["normalized_suspect_function"],
    }


def run_review_session(
    repo_root: Path, target: Path, catalogue: Mapping[str, Any], reviewer: Mapping[str, Any],
    disclosure: Mapping[str, Any], index: Mapping[str, Any], package_record: Mapping[str, Any], trial_id: str,
) -> dict[str, Any]:
    mode = package_record["controller_condition"]["mode"]
    package = deepcopy(package_record["reviewer_package"])
    first_stage = "group" if mode in {"P10", "P11"} else ("artifact" if mode in {"P09", "P13", "P14"} else ("reconsider" if mode == "P12" else "final"))
    response = _provider_review(repo_root, target, render_request(package), trial_id, first_stage)
    pre = validate_response(repo_root, package, response, first_stage)
    latest, current = pre, package
    calls = [_call_record(response)]
    usage = [_usage(response, "initial_review")]
    events: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    selected_group = None
    selected_artifact = None

    if mode in {"P09", "P13", "P14"}:
        action = pre["receipt"]["next_action"]
        try:
            event = inspect_artifact(repo_root, disclosure, current, action)
        except (KeyError, TypeError, ValueError) as exc:
            diagnostics.append({"status": "rejected_without_model_call", "stage": "artifact", "reason": str(exc), "request": deepcopy(action), "evidence_bytes_added": 0})
        else:
            events.append(event)
            selected_artifact = deepcopy(event)
            current.pop("available_operations", None)
            current.pop("interaction_contract", None)
            response = _provider_review(repo_root, target, render_request(current, event), f"{trial_id}-follow-up-01", "final")
            latest = validate_response(repo_root, current, response, "final")
            calls.append(_call_record(response))
            usage.append(_usage(response, "model_selected_artifact_inspection"))
    elif mode in {"P10", "P11"}:
        action = pre["receipt"]["next_action"]
        try:
            current, expansion = expand_native_subtree(catalogue, reviewer, index, current, str(action["execution_group_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            diagnostics.append({"status": "rejected_without_model_call", "stage": "group", "reason": str(exc), "request": deepcopy(action), "evidence_bytes_added": 0})
        else:
            events.append(expansion)
            selected_group = deepcopy(expansion)
            current["available_operations"] = ["artifact_inspection"]
            current["interaction_contract"] = {
                "operation": "artifact_inspection", "required_before_terminal": True,
                "eligible_artifact_refs": deepcopy(expansion["newly_disclosed_artifact_refs"]),
                "model_selects_artifact_and_mode": True,
            }
            response = _provider_review(repo_root, target, render_request(current, expansion), f"{trial_id}-follow-up-01", "artifact")
            after_expansion = validate_response(repo_root, current, response, "artifact")
            latest = after_expansion
            calls.append(_call_record(response))
            usage.append(_usage(response, "model_selected_native_subtree"))
            inspection_action = after_expansion["receipt"]["next_action"]
            try:
                inspection = inspect_artifact(repo_root, disclosure, current, inspection_action, set(expansion["newly_disclosed_artifact_refs"]))
            except (KeyError, TypeError, ValueError) as exc:
                diagnostics.append({"status": "rejected_without_model_call", "stage": "artifact", "reason": str(exc), "request": deepcopy(inspection_action), "evidence_bytes_added": 0})
            else:
                events.append(inspection)
                selected_artifact = deepcopy(inspection)
                current.pop("available_operations", None)
                current.pop("interaction_contract", None)
                response = _provider_review(repo_root, target, render_request(current, inspection), f"{trial_id}-follow-up-02", "final")
                latest = validate_response(repo_root, current, response, "final")
                calls.append(_call_record(response))
                usage.append(_usage(response, "newly_disclosed_artifact_inspection"))
    elif mode == "P12":
        for pass_number in (1, 2):
            before = ce.sha256(_initial_evidence(current))
            event = {"operation": "reconsider_same_evidence", "status": "completed", "pass": pass_number, "evidence_bytes_added": 0}
            if pass_number == 2:
                current.pop("available_operations", None)
                current.pop("interaction_contract", None)
            stage = "reconsider" if pass_number == 1 else "final"
            response = _provider_review(repo_root, target, render_request(current, event), f"{trial_id}-follow-up-{pass_number:02d}", stage)
            if ce.sha256(_initial_evidence(current)) != before:
                raise RuntimeError("zero-evidence reconsideration changed evidence")
            latest = validate_response(repo_root, current, response, stage)
            events.append(event)
            calls.append(_call_record(response))
            usage.append(_usage(response, f"zero_evidence_reconsideration_{pass_number}"))

    return {
        "pre_validation": pre, "final_validation": latest,
        "operation_events": events, "operation_diagnostics": diagnostics,
        "selected_group": selected_group, "selected_artifact": selected_artifact,
        "answer_changed": _diagnosis(pre) != _diagnosis(latest),
        "completed_expansions": sum(event["operation"] == "expand_execution_group" for event in events),
        "completed_artifact_inspections": sum(event["operation"] == "artifact_inspection" for event in events),
        "completed_reconsiderations": sum(event["operation"] == "reconsider_same_evidence" for event in events),
        "call_records": calls, "usage": ce.aggregate_actual_usage_records(usage),
    }


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(reviews)
    return {
        "reviews": len(values), "repairs": 0,
        "logical_provider_calls": sum(len(value["call_records"]) for value in values),
        "provider_attempt_call_ids": sum(len(call["call_ids"]) for value in values for call in value["call_records"]),
        "completed_expansions": sum(value["completed_expansions"] for value in values),
        "completed_artifact_inspections": sum(value["completed_artifact_inspections"] for value in values),
        "completed_reconsiderations": sum(value["completed_reconsiderations"] for value in values),
        "rejected_operations": sum(len(value["operation_diagnostics"]) for value in values),
    }


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for review in reviews:
        trial, usage = review["controller_trial"], review["usage"]
        selected_artifact = review.get("selected_artifact") or {}
        rows.append({
            "trial_id": trial["trial_id"], "instance": trial["opaque_instance_id"],
            "cell_id": trial["cell_id"], "mode": trial["mode"],
            "source_setting": trial["source_setting"], "declaration_setting": trial["declaration_setting"],
            "repetition": trial["repetition"], "designation": review["designation"],
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
            "artifact_ref": selected_artifact.get("artifact_ref"), "inspection": selected_artifact.get("inspection"),
            "artifact_bytes_returned": int(selected_artifact.get("artifact_bytes_returned") or 0),
            "provider_calls": len(review["call_records"]),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "invalid_citation_ref_count": len(review["invalid_evidence_refs"]),
        })
    return rows


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    def ratio(values: list[Mapping[str, Any]], key: str) -> dict[str, int]:
        return {"numerator": sum(bool(value[key]) for value in values), "denominator": len(values)}
    return {
        "reviews": len(rows), "provider_calls": sum(row["provider_calls"] for row in rows),
        "fault_detection": ratio(faults, "fault_detected"),
        "correct_job_attribution": ratio(faults, "correct_job_attribution"),
        "exact_function_localisation": ratio(faults, "exact_function_localisation"),
        "control_false_positives": ratio(controls, "false_positive"),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "cached_input_tokens": sum(row["cached_input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "total_tokens": sum(row["total_tokens"] for row in rows),
    }


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    aggregate = _summary(rows)
    cell_summaries = {cell: _summary([row for row in rows if row["cell_id"] == cell]) for cell in CELLS}
    if aggregate["fault_detection"]["denominator"] != 84 or aggregate["control_false_positives"]["denominator"] != 56:
        raise RuntimeError("fault/control analysis denominators changed")
    contrasts = []
    specifications = (
        ("source", "P02-S1-B0", "P01-S0-B0"),
        ("declarations", "P03-S1-B1", "P02-S1-B0"),
        ("history", "P04-S1-B0", "P02-S1-B0"),
        ("nodes", "P05-S1-B0", "P02-S1-B0"),
        ("connectivity_and_groups", "P07-S1-B0", "P05-S1-B0"),
        ("visible_interface_inspection", "P09-S1-B0", "P07-S1-B0"),
        ("nested_disclosure", "P11-S1-B0", "P09-S1-B0"),
        ("new_evidence_vs_extra_calls", "P11-S1-B0", "P12-S1-B0"),
        ("full_vs_compact", "P13-S1-B0", "P09-S1-B0"),
        ("random_vs_selected", "P14-S1-B0", "P09-S1-B0"),
    )
    for name, left, right in specifications:
        for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation", "false_positive"):
            differences = []
            for instance_id in INSTANCES:
                left_values = [float(row[outcome]) for row in rows if row["instance"] == instance_id and row["cell_id"] == left]
                right_values = [float(row[outcome]) for row in rows if row["instance"] == instance_id and row["cell_id"] == right]
                differences.append(sum(left_values) / len(left_values) - sum(right_values) / len(right_values))
            contrasts.append({
                "name": name, "left": left, "right": right, "outcome": outcome,
                "unit": "two repetitions averaged within each of five instances",
                "per_instance_differences": differences,
                "mean_difference": sum(differences) / len(differences),
            })
    operations_summary = {
        "adaptive_sessions": sum(row["mode"] in {"P10", "P11"} for row in rows),
        "visible_inspection_sessions": sum(row["mode"] in {"P09", "P13", "P14"} for row in rows),
        "reconsideration_sessions": sum(row["mode"] == "P12" for row in rows),
        "answer_changes": sum(row["answer_changed"] for row in rows),
        "truth_group_selections": sum(row["selected_group_contained_truth_state"] for row in rows),
        "truth_artifact_selections": sum(row["selected_artifact_was_truth_state"] for row in rows),
        "artifact_bytes_returned": sum(row["artifact_bytes_returned"] for row in rows),
    }
    analysis = {
        "schema_version": "n27pb-pilot-analysis-1", "exploratory_not_confirmatory": True,
        "full_replication_remains_deferred": True, "aggregate": aggregate,
        "cell_summaries": cell_summaries,
        "instance_summaries": {instance: _summary([row for row in rows if row["instance"] == instance]) for instance in INSTANCES},
        "instance_cell_summaries": {f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell]) for instance in INSTANCES for cell in CELLS},
        "prespecified_descriptive_contrasts": contrasts, "operations": operations_summary,
        "actual_usage": {key: aggregate[key] for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")},
        "estimated_cost_usd": round((aggregate["input_tokens"] - aggregate["cached_input_tokens"]) * 5 / 1_000_000 + aggregate["cached_input_tokens"] * .5 / 1_000_000 + aggregate["output_tokens"] * 30 / 1_000_000, 6),
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
    writer.writeheader()
    writer.writerows(rows)
    _write_text(target / "analysis/all-review-rows.csv", stream.getvalue())
    return target / "analysis/summary.json"


def _rate(value: Mapping[str, int]) -> str:
    return "n/a" if not value["denominator"] else f"{value['numerator']}/{value['denominator']} ({100 * value['numerator'] / value['denominator']:.2f}%)"


def _write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PB-payload-lazy-hard-fault-pilot"
    findings = [
        "# N27PB payload-lazy native-Etiq hard-fault pilot", "",
        "Attempt 046 completed the authorized five-instance exploratory pilot. The full replication remains deferred.", "",
        "## Aggregate outcomes", "",
        f"- Fault detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Actual provider calls: {aggregate['provider_calls']}",
        f"- Actual tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; total {aggregate['total_tokens']}", "",
        "## Scope", "",
        "All 20 captures are fresh native Etiq executions. Artifact bodies stayed controller-side until a model-selected inspection. No repairs or full replication were run.", "",
        "## Immutable records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-046/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-046/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-046/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-046/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    cell_lines = ["# Complete cell table", "", "| Cell | Reviews | Detection | Job 1 | Exact function | Control FP | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cell in CELLS:
        value = analysis["cell_summaries"][cell]
        cell_lines.append(f"| {cell} | {value['reviews']} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} | {_rate(value['control_false_positives'])} | {value['provider_calls']} |")
    _write_text(report_dir / "cell-table.md", "\n".join(cell_lines))
    trial_lines = ["# Complete trial table", "", "| Position | Trial | Instance | Cell | Rep | Detected | Suspect job | Suspect function | Artifact/mode | Calls |", "|---:|---|---|---|---:|---|---|---|---|---:|"]
    for review in sorted(reviews, key=lambda value: value["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        artifact = review.get("selected_artifact") or {}
        trial_lines.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {artifact.get('artifact_ref', '')}/{artifact.get('inspection', '')} | {len(review['call_records'])} |")
    _write_text(report_dir / "trial-table.md", "\n".join(trial_lines))
    operation_lines = ["# Complete operation table", "", "| Trial | Cell | Group | Artifact | Mode | Bytes | Answer changed | Validations |", "|---|---|---|---|---|---:|---|---|"]
    for review in reviews:
        trial = review["controller_trial"]
        group, artifact = review.get("selected_group") or {}, review.get("selected_artifact") or {}
        operation_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {artifact.get('inspection', '')} | {artifact.get('artifact_bytes_returned', 0)} | {review['answer_changed']} | {len(review['operation_diagnostics']) == 0} |")
    _write_text(report_dir / "operation-table.md", "\n".join(operation_lines))
    native = _json(target / "qualification/native-captures.json")["topology"]
    topology_lines = ["# Native topology table", "", "| Instance | Job | Native nodes | Native edges | V0 | E0 | Groups | Passed |", "|---|---|---:|---:|---:|---:|---:|---|"]
    for instance in INSTANCES:
        index = prepared_index = _json(target / "native-subtree-index" / f"{instance}.json")
        for job in JOB_ORDER:
            count = prepared_index["job_counts"][job]
            topology_lines.append(f"| {instance} | {job} | {count['full_nodes']} | {count['full_edges']} | {count['visible_nodes']} | {count['visible_edges']} | {count['collapsed_clusters']} | {native[instance][job]['passed']} |")
    _write_text(report_dir / "native-topology-table.md", "\n".join(topology_lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PB Attempt 046 pilot results", "",
        "Status: `completed_pilot_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "",
        "- Five instances and 20 fresh native Etiq job captures",
        f"- 70 packages; 140 terminal reviews; {aggregate['provider_calls']} inference-bearing calls; zero repairs", "",
        "Exploratory outcomes", "",
        f"- Detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; total {aggregate['total_tokens']}", "",
        "Attempts 042–045 and all protected provider, Etiq-worker, sandbox and process-isolation surfaces remained unchanged. The full replication was not started.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PB_attempt_046_results_to_overseer.email.md", "\n".join(lines))


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
            instance_id = trial["opaque_instance_id"]
            package_record = packages[trial["branch_id"]]
            session = run_review_session(
                repo_root, target, prepared["catalogues"][instance_id],
                prepared["reviewer_nodes"][instance_id], prepared["disclosures"][instance_id],
                prepared["indexes"][instance_id], package_record, trial["trial_id"],
            )
            pre, final = session["pre_validation"], session["final_validation"]
            outcome = score_response(prepared["instances"][instance_id], final)
            truth = relevance.get(instance_id, {})
            group = session["selected_group"] or {}
            artifact = session["selected_artifact"] or {}
            record = {
                "schema_version": "n27pb-review-record-1", "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "initial_receipt": deepcopy(pre["receipt"]), "terminal_receipt": deepcopy(final["receipt"]),
                "pre_fault_detected": pre["fault_detected"], "pre_suspect_job": pre["suspect_job"],
                "pre_suspect_function": pre["normalized_suspect_function"],
                "suspect_job": final["suspect_job"], "suspect_function": final["normalized_suspect_function"],
                "suspect_function_visible": final["suspect_function_visible"],
                "parsed_evidence_refs": deepcopy(final["parsed_evidence_refs"]),
                "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]),
                **outcome,
                "operation_events": session["operation_events"],
                "operation_diagnostics": session["operation_diagnostics"],
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
    counts = reconstruct_counts(reviews)
    if counts["reviews"] != 140 or counts["repairs"] != 0 or counts["logical_provider_calls"] > 230:
        raise RuntimeError(f"terminal review/call counts invalid: {counts}")
    if counts["logical_provider_calls"] != 230 - sum(
        2 if diagnostic["stage"] == "group" else 1
        for review in reviews for diagnostic in review["operation_diagnostics"]
    ):
        raise RuntimeError("invalid-operation no-extra-call reconciliation failed")
    call_ids = [call_id for review in reviews for call in review["call_records"] for call_id in call["call_ids"]]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("duplicate provider call ID")
    for call_id in call_ids:
        verify_record(target / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = _json(write_analysis(target, reviews))
    freeze = _json(target / "experiment-freeze.json")
    replay = {
        "schema_version": "n27pb-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(review["review_sha256"] for review in reviews),
        "observed_counts": counts, "planned_inference_calls": 230,
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
        "schema_version": "n27pb-terminal-1", "status": "completed_pilot_and_analysis",
        "instance_count": 5, "fresh_job_capture_count": 20, "package_count": 70,
        "review_count": 140, "planned_provider_calls": 230,
        "actual_provider_calls": counts["logical_provider_calls"],
        "rejected_operation_count": counts["rejected_operations"], "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"], "replay_sha256": replay["replay_sha256"],
        "full_replication_started": False,
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
            "schema_version": "n27pb-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27pb_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
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
            result = build_attempt(repo, target)
            print(json.dumps({"qualification": result["qualification"]}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, target))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, target), indent=2))
        else:
            path = run_lifecycle(repo, target)
            print(path)
            return 0 if _json(path).get("status") == "completed_pilot_and_analysis" else 1
    except Exception as exc:
        print(f"N27PB experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
