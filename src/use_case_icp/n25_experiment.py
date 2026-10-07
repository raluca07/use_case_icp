"""N25 append-only four-stage campaign-diagnosis experiment."""

from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import random
import re
import time
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator
import tiktoken

from . import corrected_experiment as ce
from .fault_preflight_v2 import validate_strict_provider_schema
from .n05_program import _load_snapshot, _parse_output, _pipeline_payload, derive_review_evidence, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, stable_id, verify_record
from .etiq_executor import EtiqExecution
from .job_store import JobStore
from .records import GeneratedFile, GeneratedPipeline, jsonable


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-042")
ATTEMPT_041 = Path("outputs/fault-experiments-v2-2-n10/attempt-041")
ATTEMPT_033 = Path("outputs/fault-experiments-v2-2-n10/attempt-033")
TASK = Path("instructions_between_agent_types/developer/current/N25_four_stage_campaign_diagnosis_experiment.email.md")
TASK_SHA256 = "sha256:b2b362957f22516d805e8727938c89f0490d761e3ee8314f5dddf84f121d1c03"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N25_four_stage_campaign_diagnosis_experiment_authorization.json")
AUTHORITY_SHA256 = "sha256:0e2ec34f414c7bf68e70730535147779b2a47b3eb9c4c41105a2c3778defab9f"
PROMPT = Path("prompts/v2_2/n25_four_stage_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n25_final.schema.json")
REQUIRED_SCHEMA = Path("schemas/v2_2/n25_expand_required.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n25_reconsider.schema.json")
JOB3_OUTPUT_SCHEMA = Path("schemas/v2_2/n25_campaign_portfolio_output.schema.json")
JOB4_OUTPUT_SCHEMA = Path("schemas/v2_2/n25_activation_plan_output.schema.json")
JOB3_SOURCE = Path("src/use_case_icp/n25_campaign_portfolio.py")
JOB4_SOURCE = Path("src/use_case_icp/n25_campaign_activation.py")

UPSTREAM = "job_upstream_demand_provenance"
DOWNSTREAM = "job_downstream_coverage_priority"
JOB3 = "job_campaign_portfolio_generation"
JOB4 = "job_campaign_activation_planning"
JOB_ORDER = (UPSTREAM, DOWNSTREAM, JOB3, JOB4)
FUNCTIONS = {
    UPSTREAM: ("select_demand", "normalize", "assemble_provenance"),
    DOWNSTREAM: ("map_coverage", "prioritize", "synthesize"),
    JOB3: ("build_campaign_items", "assign_message_strategy", "assemble_campaign_portfolio"),
    JOB4: ("map_delivery_channels", "schedule_campaign_actions", "assemble_activation_plan"),
}
INSTANCES = (
    "select_threshold_omission",
    "select_need_source_id_substitution",
    "normalize_top_record_omission",
    "normalize_middle_record_omission",
    "provenance_ranking_reversal",
    "provenance_join_identity",
    "four_stage_clean_control",
)
CLEAN_INSTANCE = "four_stage_clean_control"
SOURCE_INSTANCE = {
    "select_threshold_omission": (ATTEMPT_041, "select_threshold_omission"),
    "select_need_source_id_substitution": (ATTEMPT_033, "n19a-three-job-upstream-fault"),
    "normalize_top_record_omission": (ATTEMPT_041, "normalize_top_record_omission"),
    "normalize_middle_record_omission": (ATTEMPT_041, "normalize_middle_record_omission"),
    "provenance_ranking_reversal": (ATTEMPT_041, "provenance_ranking_reversal"),
    "provenance_join_identity": (ATTEMPT_041, "provenance_join_identity"),
    "four_stage_clean_control": (ATTEMPT_041, "n16-clean-control"),
}
TRUTH = {
    "select_threshold_omission": "select_demand",
    "select_need_source_id_substitution": "select_demand",
    "normalize_top_record_omission": "normalize",
    "normalize_middle_record_omission": "normalize",
    "provenance_ranking_reversal": "assemble_provenance",
    "provenance_join_identity": "assemble_provenance",
    "four_stage_clean_control": None,
}
MODES = (
    ("E01", "io_job4"),
    ("E02", "current_job4"),
    ("E03", "history_empty"),
    ("E04", "history_full"),
    ("E05", "etiq_empty"),
    ("E06", "compact_nodes_only"),
    ("E07", "compact_fixed"),
    ("E08", "compact_adaptive_required_one"),
    ("E09", "compact_reconsideration"),
    ("E10", "full_graph"),
    ("E11", "random_matched"),
)
MODE_NAMES = dict(MODES)
GRAPH_MODES = {f"E{number:02d}" for number in range(5, 12)}
DELIVERY_RULES = [
    {"message_strategy": "gap_education", "channel": "content_marketing", "action_type": "publish_educational_asset"},
    {"message_strategy": "capability_reinforcement", "channel": "product_marketing", "action_type": "publish_capability_demo"},
]
TASK_TEXT = (
    "Starting from the observed Job-4 campaign-activation result, decide whether the four-job execution "
    "contains a behaviorally significant fault. If it does, identify the earliest responsible job and, "
    "when the supplied evidence supports it, the exact responsible function."
)
PROTECTED = {
    "src/use_case_icp/n05_runner.py": "sha256:25ba9749a212aef9d8a23513e4e1014985291708a0517e6d20f1f4469ed85bee",
    "src/use_case_icp/n07_program.py": "sha256:d338cc22ce881b2c9bae46a105f227b9aae5f563fde17b177a3435286beec34f",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
    "prompts/v2_2/fault_review.md": "sha256:1a59763cce79f307b0b86501ee4d272726c6df793d7827a9c155b8b8fd22ea44",
    "schemas/v2_2/fault_review_receipt.schema.json": "sha256:3cebce8ef00c20f8316a4ed0998fd53ebff9e62a9471b7b635305ad7a5cbd075",
}
SOURCE_FIXED = {
    "attempt-041/experiment-freeze.json": "sha256:36b99333f33cd4346775a9526c6087c33e50d4c2f146adf69c584c36640d75a4",
    "attempt-041/terminal-state.json": "sha256:e7008ebcbe0a96b629138e0db156fe472541b2dbc75df0124890bb91f8e81217",
    "attempt-041/replay.json": "sha256:253d58982c3ce5c112fbdb4bee247479a59d1bff9f78746b5241c13019c5c501",
    "attempt-033/experiment-freeze.json": "sha256:b93b3dd1c7ca69f9d48c95d0011a48809f57898a9556a201106e38a0d9c1296a",
    "attempt-033/terminal-state.json": "sha256:e9283c552df88d6f5b331bec6ab18e7cfd8a5b1eca284b4a2572e9f80bdb5ab1",
    "attempt-033/replay/reconciliation.json": "sha256:50c540ab81c6d7b6f6aaee60c7bb9ef1a529a899d3b6a62aecf48f590a618ff4",
}


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_bytes(path: Path, text: str) -> None:
    create_bytes_exclusive(path, text.encode())


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N25 authority input changed: {relative}")
    for relative, expected in PROTECTED.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N25 protected boundary changed: {relative}")
    root = repo_root / "outputs/fault-experiments-v2-2-n10"
    for relative, expected in SOURCE_FIXED.items():
        if ce.sha256((root / relative).read_bytes()) != expected:
            raise ValueError(f"N25 source-attempt binding changed: {relative}")
    return {
        "task_sha256": TASK_SHA256,
        "authority_sha256": AUTHORITY_SHA256,
        "protected_hashes": deepcopy(PROTECTED),
        "source_fixed_file_hashes": deepcopy(SOURCE_FIXED),
    }


def _pipeline(repo_root: Path, job_id: str) -> GeneratedPipeline:
    if job_id == JOB3:
        source_path = JOB3_SOURCE
        generated = "generated/protocol_2_2/campaign_portfolio_generation.py"
        boundaries = [
            ("build_campaign_items", "Build one campaign item for every received priority without truncation.", ["complete ordered priorities"], ["complete copied campaign items"]),
            ("assign_message_strategy", "Assign an ordinary campaign role, message strategy and evidence status to every item.", ["campaign items", "recommendation"], ["strategy-assigned campaign items"]),
            ("assemble_campaign_portfolio", "Assemble the complete campaign portfolio and input-relative counts.", ["assigned items", "coverage", "recommendation"], ["campaign_portfolio", "metadata"]),
        ]
    elif job_id == JOB4:
        source_path = JOB4_SOURCE
        generated = "generated/protocol_2_2/campaign_activation_planning.py"
        boundaries = [
            ("map_delivery_channels", "Map every campaign item through the delivery rules without dropping an unmapped item.", ["campaign items", "delivery rules"], ["mapped campaign items"]),
            ("schedule_campaign_actions", "Place every mapped item exactly once into launch or evidence-review actions.", ["mapped campaign items"], ["launch actions", "evidence-review actions"]),
            ("assemble_activation_plan", "Assemble the final activation plan, channel mix and action counts.", ["campaign portfolio", "scheduled actions"], ["activation_plan", "metadata"]),
        ]
    else:
        raise ValueError(f"unsupported N25 new job: {job_id}")
    pipeline = GeneratedPipeline(
        entry_file=generated,
        files=[GeneratedFile(generated, (repo_root / source_path).read_text(encoding="utf-8"))],
        review_boundaries=[{
            "boundary_id": f"rb_n25_{job_id}_{name}",
            "function_name": name,
            "qualified_function_name": name,
            "source_path": generated,
            "role": role,
            "expected_inputs": inputs,
            "expected_outputs": outputs,
            "semantic_stage": job_id,
        } for name, role, inputs, outputs in boundaries],
    )
    pipeline.validate()
    return pipeline


def _job3_input(source_capture: Mapping[str, Any]) -> dict[str, Any]:
    output = source_capture["jobs"][DOWNSTREAM]["output"]
    return {key: deepcopy(output[key]) for key in ("coverage", "priorities", "recommendation", "metadata")}


def _job4_input(job3_output: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "campaign_portfolio": deepcopy(job3_output["campaign_portfolio"]),
        "metadata": deepcopy(job3_output["metadata"]),
        "delivery_rules": deepcopy(DELIVERY_RULES),
    }


def _check_job3(repo_root: Path, output: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    Draft202012Validator(_json(repo_root / JOB3_OUTPUT_SCHEMA)).validate(dict(output))
    expected = runtime_input["priorities"]
    items = output["campaign_portfolio"]["items"]
    copied = ("record_id", "need", "priority_rank", "upstream_rank", "capability_id", "coverage", "unsupported")
    if len(items) != len(expected) or any({key: item.get(key) for key in copied} != {key: row.get(key) for key in copied} for item, row in zip(items, expected)):
        raise ValueError("N25 Job 3 did not preserve every priority and copied field")
    for item in items:
        rank = item.get("upstream_rank")
        wanted = "traceable" if isinstance(rank, int) and rank > 0 else "evidence_review_required"
        if item["evidence_status"] != wanted:
            raise ValueError("N25 Job 3 evidence-status rule changed")
    portfolio = output["campaign_portfolio"]
    if portfolio["recommended_focus"] != runtime_input["recommendation"]["top_need"] or portfolio["recommended_decision"] != runtime_input["recommendation"]["decision"]:
        raise ValueError("N25 Job 3 changed the recommendation")
    metadata = output["metadata"]
    if metadata["item_count"] != len(expected) or metadata["input_priority_count"] != len(expected) or metadata["input_coverage_count"] != len(runtime_input["coverage"]) or metadata["consumed_handoffs"] != ["coverage", "priorities", "recommendation", "metadata"]:
        raise ValueError("N25 Job 3 metadata contract changed")


def _check_job4(repo_root: Path, output: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    Draft202012Validator(_json(repo_root / JOB4_OUTPUT_SCHEMA)).validate(dict(output))
    plan = output["activation_plan"]
    source_items = runtime_input["campaign_portfolio"]["items"]
    actions = [*plan["launch_actions"], *plan["evidence_review_actions"]]
    if len(actions) != len(source_items) or sorted(ce.sha256(x) for x in actions) == []:
        raise ValueError("N25 Job 4 action set is empty or incomplete")
    action_by_record = {str(row["record_id"]): row for row in actions}
    if len(action_by_record) != len(source_items) or set(action_by_record) != {str(row["record_id"]) for row in source_items}:
        raise ValueError("N25 Job 4 did not represent every item exactly once")
    copied = ("record_id", "need", "priority_rank", "upstream_rank", "capability_id", "coverage", "unsupported", "campaign_role", "message_strategy", "evidence_status")
    for item in source_items:
        action = action_by_record[str(item["record_id"])]
        if {key: action.get(key) for key in copied} != {key: item.get(key) for key in copied}:
            raise ValueError("N25 Job 4 changed an inherited campaign item")
    metadata = output["metadata"]
    if metadata != {
        "scheduled_action_count": len(plan["launch_actions"]),
        "review_action_count": len(plan["evidence_review_actions"]),
        "total_action_count": len(actions),
        "rules_version": "n25-delivery-rules-1",
        "consumed_handoffs": ["campaign_portfolio", "metadata"],
    }:
        raise ValueError("N25 Job 4 metadata contract changed")


def _source_capture(repo_root: Path, instance_id: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    attempt, source_id = SOURCE_INSTANCE[instance_id]
    root = repo_root / attempt
    source_path = root / "captures" / f"{source_id}.json"
    source = _json(source_path)
    ce._verify_capture(source)
    jobs = {job: deepcopy(source["jobs"][job]) for job in (UPSTREAM, DOWNSTREAM)}
    handoffs = [deepcopy(value) for value in source["handoffs"] if value["upstream_job_id"] == UPSTREAM and value["downstream_job_id"] == DOWNSTREAM]
    if len(handoffs) != 2:
        raise ValueError(f"N25 source capture lacks two Job-1-to-Job-2 handoffs: {instance_id}")
    source_bundle_record = _json(root / "source-bundles" / f"{source_id}.json")
    source_bundle = [deepcopy(value) for value in source_bundle_record["source_bundle"] if value["job_id"] in (UPSTREAM, DOWNSTREAM)]
    instance = _json(root / "instances" / f"{source_id}.json")
    binding = {
        "source_attempt": attempt.name,
        "source_instance_id": source_id,
        "source_capture_file_sha256": ce.sha256(source_path.read_bytes()),
        "source_capture_sha256": source["capture_sha256"],
        "reused_job_sha256": {job: ce.sha256(jobs[job]) for job in (UPSTREAM, DOWNSTREAM)},
        "reused_handoffs_sha256": ce.sha256(handoffs),
        "source_bundle_file_sha256": ce.sha256((root / "source-bundles" / f"{source_id}.json").read_bytes()),
        "mutation": deepcopy(instance.get("mutation")),
    }
    return {
        "schema_version": "n25-two-job-reuse-1",
        "capture_id": str(source["capture_id"]),
        "instance_id": instance_id,
        "job_ids": [UPSTREAM, DOWNSTREAM],
        "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": {job: source["source_sha256"][job] for job in (UPSTREAM, DOWNSTREAM)},
        "canonical": True,
        "attempt_count": 1,
    }, binding, source_bundle


def _realization(execution: Any, pipeline: GeneratedPipeline, job_id: str) -> dict[str, Any]:
    evidence = derive_review_evidence(
        {"executions": {job_id: execution}},
        jobs={job_id: pipeline},
        scenario={"protocol_version": "2.2.0"},
        simple_boundary_matching=True,
    )
    realized = evidence["realizations"][job_id]
    for boundary in realized["realized_boundaries"]:
        root = ce.canonical_stack(boundary["matched_prefix"])
        boundary["helper_prefixes"] = [
            list(stack)
            for stack in sorted({ce.canonical_stack(node.func_stack) for node in execution.snapshot.nodes})
            if len(stack) > len(root) and stack[:len(root)] == root
        ]
    return realized


def _job_record(execution: Any, output: Mapping[str, Any], realization: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "input": _json(execution.run_dir / "pipeline-input.json"),
        "output": deepcopy(dict(output)),
        "stdout": (execution.run_dir / "pipeline-stdout.log").read_text(encoding="utf-8"),
        "stderr": (execution.run_dir / "pipeline-stderr.log").read_text(encoding="utf-8"),
        "snapshot": jsonable(execution.snapshot),
        "realization": deepcopy(dict(realization)),
    }


def _handoff(name: str, producer: str, consumer: str, value: Any) -> dict[str, Any]:
    digest = ce.sha256(value)
    return {
        "artifact_name": name,
        "consumer_sha256": digest,
        "downstream_job_id": consumer,
        "etiq_runtime_edge": False,
        "handoff_id": f"handoff-{producer}-{consumer}-{name}",
        "producer_sha256": digest,
        "provenance_type": "controller_recorded_exact_hash_handoff",
        "upstream_job_id": producer,
    }


def _new_capture(
    instance_id: str,
    source: Mapping[str, Any],
    job3_pipeline: GeneratedPipeline,
    job4_pipeline: GeneratedPipeline,
    job3_execution: Any,
    job4_execution: Any,
    job3_output: Mapping[str, Any],
    job4_output: Mapping[str, Any],
    job3_realization: Mapping[str, Any],
    job4_realization: Mapping[str, Any],
) -> dict[str, Any]:
    jobs = deepcopy(dict(source["jobs"]))
    jobs[JOB3] = _job_record(job3_execution, job3_output, job3_realization)
    jobs[JOB4] = _job_record(job4_execution, job4_output, job4_realization)
    handoffs = deepcopy(list(source["handoffs"]))
    handoffs.extend(_handoff(name, DOWNSTREAM, JOB3, jobs[DOWNSTREAM]["output"][name]) for name in ("coverage", "priorities", "recommendation", "metadata"))
    handoffs.extend(_handoff(name, JOB3, JOB4, job3_output[name]) for name in ("campaign_portfolio", "metadata"))
    capture = {
        "schema_version": "1",
        "capture_id": stable_id("rerun-capture", ["n25", instance_id], 0),
        "instance_id": instance_id,
        "job_ids": list(JOB_ORDER),
        "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": {
            **deepcopy(dict(source["source_sha256"])),
            JOB3: ce.sha256(_pipeline_payload(job3_pipeline)),
            JOB4: ce.sha256(_pipeline_payload(job4_pipeline)),
        },
        "canonical": True,
        "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    _verify_four_capture(capture)
    return capture


def _verify_four_capture(capture: Mapping[str, Any]) -> None:
    unsigned = dict(capture)
    observed = str(unsigned.pop("capture_sha256", ""))
    if not capture.get("canonical") or int(capture.get("attempt_count", 0)) != 1 or observed != ce.sha256(unsigned):
        raise ValueError("N25 canonical capture identity or hash mismatch")
    job_ids = list(map(str, capture.get("job_ids", [])))
    if job_ids != list(JOB_ORDER) or set(capture.get("jobs", {})) != set(JOB_ORDER):
        raise ValueError("N25 capture must contain the exact explicit four-job order")
    for job_id in JOB_ORDER:
        snapshot = capture["jobs"][job_id].get("snapshot")
        if not isinstance(snapshot, Mapping) or str(snapshot.get("job_id")) != job_id:
            raise ValueError(f"N25 snapshot identity mismatch: {job_id}")
    if len(capture.get("handoffs", [])) != 8:
        raise ValueError("N25 capture must contain eight exact-hash handoffs")
    for handoff in capture["handoffs"]:
        if handoff.get("producer_sha256") != handoff.get("consumer_sha256"):
            raise ValueError("N25 handoff producer and consumer hashes differ")


def _build_catalogue(capture: Mapping[str, Any]) -> dict[str, Any]:
    _verify_four_capture(capture)
    jobs = {}
    redactions = []
    for job_id in JOB_ORDER:
        captured = capture["jobs"][job_id]
        snapshot = captured["snapshot"]
        nodes = []
        for original in snapshot["nodes"]:
            node = deepcopy(dict(original))
            for path in ce._redaction_paths(node):
                redactions.append({"job_id": job_id, "node_ref": node["node_ref"], "path": path})
            node["node_sha256"] = ce.sha256(original)
            node["raw_metadata_sha256"] = ce.sha256(original.get("raw_metadata", {}))
            node["artifact_value_sha256"] = ce.sha256(original["artifact_content"]) if original.get("artifact_content") is not None else None
            nodes.append(node)
        relationships = []
        for original in snapshot["relationships"]:
            edge = deepcopy(dict(original))
            edge["relationship_sha256"] = ce.sha256(original)
            edge["raw_metadata_sha256"] = ce.sha256(original.get("raw_metadata", {}))
            relationships.append(edge)
        boundaries = deepcopy(captured["realization"]["realized_boundaries"])
        bindings = [ce._realized_boundary_binding(value) for value in boundaries]
        if len({value["reviewer_boundary_id"] for value in bindings}) != len(bindings):
            raise ValueError(f"N25 realized boundary identities are not unique: {job_id}")
        jobs[job_id] = {
            "job_id": job_id,
            "job_order_index": JOB_ORDER.index(job_id),
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_sha256": ce.sha256(snapshot),
            "nodes": nodes,
            "relationships": relationships,
            "inventories": deepcopy(snapshot.get("inventories", {})),
            "scan_errors": deepcopy(snapshot.get("scan_errors", [])),
            "realized_boundaries": boundaries,
            "boundary_bindings": bindings,
            "realized_boundary_prefixes": [{"boundary_id": str(value["boundary_id"]), "func_stack": list(ce.canonical_stack(value["matched_prefix"]))} for value in boundaries],
            "direct_child_function_prefixes": [entry for boundary in boundaries for entry in ce._direct_children(snapshot, boundary)],
            "input": deepcopy(captured["input"]),
            "output": deepcopy(captured["output"]),
            "stdout": str(captured["stdout"]),
            "stderr": str(captured["stderr"]),
        }
    catalogue = {
        "schema_version": "n25-four-job-catalogue-1",
        "storage_classification": "restricted_controller_only",
        "instance_id": capture["instance_id"],
        "source_capture_id": capture["capture_id"],
        "source_capture_sha256": capture["capture_sha256"],
        "job_order": list(JOB_ORDER),
        "assigned_job_id": JOB4,
        "source_sha256": deepcopy(capture["source_sha256"]),
        "handoffs": deepcopy(capture["handoffs"]),
        "jobs": jobs,
        "unavoidable_json_conversions": [{"scope": "entire_catalogue", "reason": "canonical capture is frozen as JSON; no additional object conversion was performed"}],
        "secret_redactions": redactions,
    }
    catalogue["catalogue_sha256"] = ce.sha256(catalogue)
    return catalogue


def _existing_execution(branch: Path, job_id: str) -> EtiqExecution | None:
    if not branch.exists():
        return None
    runs = sorted((branch / "jobstore" / job_id / "stages" / "n05").glob("*/runs/*"))
    if len(runs) != 1:
        raise ValueError(f"N25 existing capture branch is incomplete: {branch}")
    run_dir = runs[0]
    snapshot = _load_snapshot(JobStore(branch / "jobstore"), run_dir)
    if snapshot.scan_errors or not snapshot.nodes:
        raise ValueError(f"N25 existing Etiq capture is not reviewable: {branch}")
    return EtiqExecution(snapshot=snapshot, run_dir=run_dir)


def _load_prepared(target: Path) -> dict[str, Any]:
    captures = {path.stem: _json(path) for path in sorted((target / "captures").glob("*.json"))}
    catalogues = {path.stem: _json(path) for path in sorted((target / "catalogues").glob("*.json"))}
    instances = {path.stem: _json(path) for path in sorted((target / "instances").glob("*.json"))}
    sources = {path.stem: _json(path)["source_bundle"] for path in sorted((target / "source-bundles").glob("*.json"))}
    indexes = {path.stem: _json(path) for path in sorted((target / "group-index").glob("*.json"))}
    expected = set(INSTANCES)
    if any(set(values) != expected for values in (captures, catalogues, instances, sources, indexes)):
        raise ValueError("N25 prepared record set is partial")
    for instance_id in INSTANCES:
        _verify_four_capture(captures[instance_id])
        ce.verify_catalogue(catalogues[instance_id])
        ce._verified_self_hash(instances[instance_id], "instance_sha256")
        ce._verified_self_hash(indexes[instance_id], "index_sha256")
    return {"captures": captures, "catalogues": catalogues, "instances": instances, "source_bundles": sources, "indexes": indexes}


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N25 is authorized only for Attempt 042")
    authority = _verify_authority(repo_root)
    if (target / "captures").exists():
        prepared = _load_prepared(target)
        prepared["authority"] = authority
        return prepared

    ce._write_immutable(target / "delivery-rules.json", {"schema_version": "n25-delivery-rules-1", "rules": DELIVERY_RULES})
    job3_pipeline = _pipeline(repo_root, JOB3)
    job4_pipeline = _pipeline(repo_root, JOB4)
    captures: dict[str, Any] = {}
    catalogues: dict[str, Any] = {}
    instances: dict[str, Any] = {}
    source_bundles: dict[str, list[dict[str, Any]]] = {}
    reuse_bindings: dict[str, Any] = {}
    new_source_hashes = {
        JOB3: ce.sha256(_pipeline_payload(job3_pipeline)),
        JOB4: ce.sha256(_pipeline_payload(job4_pipeline)),
    }

    for run_index, instance_id in enumerate(INSTANCES):
        source, binding, source_bundle = _source_capture(repo_root, instance_id)
        reuse_bindings[instance_id] = binding
        branch3 = target / "capture-branches" / instance_id / "canonical-job-3"
        input3 = _job3_input(source)
        execution3 = _existing_execution(branch3, JOB3)
        if execution3 is None:
            materialize_opaque_branch(branch3, allowlist={}, manifest_identity={"purpose": "n25-job3-capture", "instance": instance_id})
            copy_etiq_worker_runtime(branch3, repo_root / "src")
            execution3 = execute_pipeline_in_branch(
                branch3,
                repo_root=repo_root,
                job_id=JOB3,
                pipeline=job3_pipeline,
                runtime_input=input3,
                run_index=run_index,
                stage=f"n25-{instance_id}-job3",
            )
        output3 = _parse_output(execution3)
        _check_job3(repo_root, output3, input3)
        realization3 = _realization(execution3, job3_pipeline, JOB3)

        branch4 = target / "capture-branches" / instance_id / "canonical-job-4"
        input4 = _job4_input(output3)
        execution4 = _existing_execution(branch4, JOB4)
        if execution4 is None:
            materialize_opaque_branch(branch4, allowlist={}, manifest_identity={"purpose": "n25-job4-capture", "instance": instance_id})
            copy_etiq_worker_runtime(branch4, repo_root / "src")
            execution4 = execute_pipeline_in_branch(
                branch4,
                repo_root=repo_root,
                job_id=JOB4,
                pipeline=job4_pipeline,
                runtime_input=input4,
                run_index=run_index,
                stage=f"n25-{instance_id}-job4",
            )
        output4 = _parse_output(execution4)
        _check_job4(repo_root, output4, input4)
        realization4 = _realization(execution4, job4_pipeline, JOB4)

        capture = _new_capture(
            instance_id, source, job3_pipeline, job4_pipeline,
            execution3, execution4, output3, output4, realization3, realization4,
        )
        catalogue = _build_catalogue(capture)
        ce.verify_catalogue(catalogue)
        boundaries = [
            boundary
            for job_id in JOB_ORDER
            for boundary in catalogue["jobs"][job_id]["realized_boundaries"]
        ]
        identities = {
            (job_id, boundary["static_identity"]["qualified_function_name"], tuple(boundary["matched_prefix"]))
            for job_id in JOB_ORDER
            for boundary in catalogue["jobs"][job_id]["realized_boundaries"]
        }
        if len(boundaries) != 12 or len(identities) != 12 or len(catalogue["handoffs"]) != 8:
            raise ValueError(f"N25 catalogue lacks twelve unique functions or eight handoffs: {instance_id}")
        for job_id in (JOB3, JOB4):
            if not any(boundary["helper_prefixes"] for boundary in catalogue["jobs"][job_id]["realized_boundaries"]):
                raise ValueError(f"N25 new job lacks a captured direct child scope: {job_id}")

        source_bundle = [
            *source_bundle,
            {"job_id": JOB3, "files": [{"path": job3_pipeline.files[0].path, "content": job3_pipeline.files[0].content}]},
            {"job_id": JOB4, "files": [{"path": job4_pipeline.files[0].path, "content": job4_pipeline.files[0].content}]},
        ]
        mutation = binding["mutation"]
        truth = TRUTH[instance_id]
        if truth is not None:
            source_text = source_bundle[0]["files"][0]["content"]
            realized_names = {boundary["function_name"] for boundary in catalogue["jobs"][UPSTREAM]["realized_boundaries"]}
            if truth not in realized_names or str(mutation.get("mutant_snippet")) not in source_text:
                raise ValueError(f"N25 mutation is not source-bound and realized: {instance_id}")
        instance = {
            "schema_version": "n25-four-stage-instance-1",
            "instance_id": instance_id,
            "designation": "matched_clean_control" if truth is None else "upstream_fault",
            "truth_job": None if truth is None else UPSTREAM,
            "truth_function": truth,
            "mutation": deepcopy(mutation),
            "reuse_binding": deepcopy(binding),
            "capture_sha256": capture["capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "source_sha256": deepcopy(capture["source_sha256"]),
            "job3_contract_passed": True,
            "job4_contract_passed": True,
        }
        instance["instance_sha256"] = ce.sha256(instance)
        graph, index = build_compact_graph(catalogue)
        ce._write_immutable(target / "captures" / f"{instance_id}.json", capture)
        ce._write_immutable(target / "catalogues" / f"{instance_id}.json", catalogue)
        ce._write_immutable(target / "source-bundles" / f"{instance_id}.json", {"source_bundle": source_bundle})
        ce._write_immutable(target / "instances" / f"{instance_id}.json", instance)
        ce._write_immutable(target / "group-index" / f"{instance_id}.json", index)
        for job_id in JOB_ORDER:
            per_job = {
                "schema_version": "n25-per-job-capture-1",
                "instance_id": instance_id,
                "job_id": job_id,
                "reuse_status": "exact_reuse" if job_id in (UPSTREAM, DOWNSTREAM) else "new_execution",
                "job_capture": deepcopy(capture["jobs"][job_id]),
                "job_capture_sha256": ce.sha256(capture["jobs"][job_id]),
                "source_sha256": capture["source_sha256"][job_id],
            }
            per_job["record_sha256"] = ce.sha256(per_job)
            ce._write_immutable(target / "job-captures" / instance_id / f"{job_id}.json", per_job)
        captures[instance_id] = capture
        catalogues[instance_id] = catalogue
        instances[instance_id] = instance
        source_bundles[instance_id] = source_bundle

    clean = captures[CLEAN_INSTANCE]["jobs"][JOB4]["output"]
    clean_plan = clean["activation_plan"]
    clean_actions = [*clean_plan["launch_actions"], *clean_plan["evidence_review_actions"]]
    if len(clean_actions) != 8 or clean["metadata"]["review_action_count"] != 0:
        raise ValueError("N25 clean end-to-end oracle failed")
    consequences = {}
    for instance_id in INSTANCES[:-1]:
        output = captures[instance_id]["jobs"][JOB4]["output"]
        plan = output["activation_plan"]
        actions = [*plan["launch_actions"], *plan["evidence_review_actions"]]
        records = [str(row["record_id"]) for row in actions]
        needs = [str(row["need"]) for row in actions]
        if ce.canonical_json(output) == ce.canonical_json(clean):
            raise ValueError(f"N25 fault did not propagate to Job 4: {instance_id}")
        checks = {
            "select_threshold_omission": "n06-r06" not in records and len(actions) < len(clean_actions),
            "select_need_source_id_substitution": all(re.fullmatch(r"s\d\d", value) for value in needs) and re.fullmatch(r"s\d\d", str(plan["recommended_focus"])) is not None,
            "normalize_top_record_omission": "n06-r01" not in records and plan["recommended_focus"] != clean_plan["recommended_focus"],
            "normalize_middle_record_omission": "n06-r06" not in records and len(actions) < len(clean_actions),
            "provenance_ranking_reversal": plan["recommended_focus"] != clean_plan["recommended_focus"] and records != [str(row["record_id"]) for row in clean_actions],
            "provenance_join_identity": output["metadata"]["review_action_count"] > 0 and any(int(row.get("upstream_rank") or 0) <= 0 for row in plan["evidence_review_actions"]),
        }
        if not checks[instance_id]:
            raise ValueError(f"N25 prespecified propagation consequence failed: {instance_id}")
        consequences[instance_id] = {
            "passed": True,
            "job4_output_sha256": ce.sha256(output),
            "clean_job4_output_sha256": ce.sha256(clean),
            "business_fields_differ": True,
        }
    ce._write_immutable(target / "qualification/reuse-bindings.json", {"schema_version": "n25-reuse-bindings-1", "authority": authority, "instances": reuse_bindings})
    ce._write_immutable(target / "qualification/propagation.json", {"schema_version": "n25-propagation-1", "clean_oracle_passed": True, "consequences": consequences})
    ce._write_immutable(target / "qualification/new-job-bindings.json", {
        "schema_version": "n25-new-job-bindings-1",
        "source_hashes": new_source_hashes,
        "delivery_rules_sha256": ce.sha256(DELIVERY_RULES),
        "job3_job4_hashes_identical_across_instances": all(
            captures[instance]["source_sha256"][job] == new_source_hashes[job]
            for instance in INSTANCES for job in (JOB3, JOB4)
        ),
        "new_capture_count": 14,
    })
    return _load_prepared(target) | {"authority": authority}


def _node_by_ref(catalogue: Mapping[str, Any]) -> dict[str, tuple[str, Mapping[str, Any]]]:
    return {
        str(node["node_ref"]): (job_id, node)
        for job_id in JOB_ORDER
        for node in catalogue["jobs"][job_id]["nodes"]
    }


def _edge_by_ref(catalogue: Mapping[str, Any]) -> dict[str, tuple[str, Mapping[str, Any]]]:
    return {
        str(edge["relationship_ref"]): (job_id, edge)
        for job_id in JOB_ORDER
        for edge in catalogue["jobs"][job_id]["relationships"]
    }


def _tag(value: Mapping[str, Any], job_id: str) -> dict[str, Any]:
    return {**deepcopy(dict(value)), "job_id": job_id}


def build_compact_graph(catalogue: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = _node_by_ref(catalogue)
    edges = _edge_by_ref(catalogue)
    anchors = []
    anchor_refs = set()
    groups = []
    group_index = {}
    for job_id in JOB_ORDER:
        realized = catalogue["jobs"][job_id]["realized_boundaries"]
        by_name = {str(value["function_name"]): value for value in realized}
        for name in FUNCTIONS[job_id]:
            boundary = by_name[name]
            ref = str(boundary["matched_function_node_ref"])
            if ref in anchor_refs or ref not in nodes:
                raise ValueError(f"N25 compact anchor identity is not unique: {job_id}/{name}")
            anchor_refs.add(ref)
            anchors.append(_tag(nodes[ref][1], job_id))
            root = tuple(map(str, boundary["matched_prefix"]))
            direct = sorted({
                tuple(map(str, prefix))
                for prefix in boundary["helper_prefixes"]
                if tuple(map(str, prefix))[:-1] == root
                and any(ce.canonical_stack(node.get("func_stack", [])) == tuple(map(str, prefix)) for node in catalogue["jobs"][job_id]["nodes"])
            })
            for prefix in direct:
                selected = [node for node in catalogue["jobs"][job_id]["nodes"] if ce.canonical_stack(node.get("func_stack", [])) == prefix]
                selected_refs = {str(node["node_ref"]) for node in selected}
                internal = [edge for edge in catalogue["jobs"][job_id]["relationships"] if str(edge["source_ref"]) in selected_refs and str(edge["target_ref"]) in selected_refs]
                group_id = f"grp-{ce.sha256([job_id, list(prefix)])[7:23]}"
                descriptor = {
                    "execution_group_id": group_id,
                    "job_id": job_id,
                    "parent_node_ref": ref,
                    "func_stack": list(prefix),
                    "node_count": len(selected),
                    "relationship_count": len(internal),
                    "has_deeper_stack": any(len(ce.canonical_stack(node.get("func_stack", []))) > len(prefix) and ce.canonical_stack(node.get("func_stack", []))[:len(prefix)] == prefix for node in catalogue["jobs"][job_id]["nodes"]),
                }
                groups.append(descriptor)
                group_index[group_id] = {"descriptor": deepcopy(descriptor), "node_refs": sorted(selected_refs)}
    compact_edges = [
        _tag(edge, job_id)
        for _, (job_id, edge) in sorted(edges.items())
        if str(edge["source_ref"]) in anchor_refs and str(edge["target_ref"]) in anchor_refs
    ]
    if len(anchors) != 12 or not groups:
        raise ValueError(f"N25 compact graph changed: {len(anchors)} anchors, {len(groups)} groups")
    projection = {
        "job_evidence_order": list(reversed(JOB_ORDER)),
        "nodes": anchors,
        "relationships": compact_edges,
        "collapsed_execution_groups": groups,
        "disclosed_execution_groups": [],
    }
    projection["projection_sha256"] = ce.sha256(projection)
    index = {"schema_version": "n25-group-index-1", "groups": group_index}
    index["index_sha256"] = ce.sha256(index)
    return projection, index


def empty_graph() -> dict[str, Any]:
    value = {"job_evidence_order": [], "nodes": [], "relationships": [], "handoffs": [], "collapsed_execution_groups": [], "disclosed_execution_groups": []}
    value["projection_sha256"] = ce.sha256(value)
    return value


def full_graph(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "job_evidence_order": list(reversed(JOB_ORDER)),
        "nodes": [_tag(node, job_id) for job_id in reversed(JOB_ORDER) for node in catalogue["jobs"][job_id]["nodes"]],
        "relationships": [_tag(edge, job_id) for job_id in reversed(JOB_ORDER) for edge in catalogue["jobs"][job_id]["relationships"]],
        "handoffs": deepcopy(list(catalogue["handoffs"])),
        "collapsed_execution_groups": [],
        "disclosed_execution_groups": [],
    }
    value["projection_sha256"] = ce.sha256(value)
    return value


def _token_count(value: Any) -> int:
    text = value if isinstance(value, str) else ce.canonical_json(value).decode()
    return len(tiktoken.get_encoding("o200k_base").encode(text))


def random_matched_graph(catalogue: Mapping[str, Any], compact: Mapping[str, Any]) -> dict[str, Any]:
    node_pool = [_tag(node, job_id) for job_id in JOB_ORDER for node in catalogue["jobs"][job_id]["nodes"]]
    edge_pool = [_tag(edge, job_id) for job_id in JOB_ORDER for edge in catalogue["jobs"][job_id]["relationships"]]
    target = _token_count({key: compact[key] for key in ("nodes", "relationships", "collapsed_execution_groups")})
    generator = random.Random(int(ce.sha256([catalogue["source_capture_sha256"], "n25-random-matched"])[7:23], 16))
    best: tuple[int, list[dict[str, Any]], list[dict[str, Any]]] | None = None
    for _ in range(3000):
        generator.shuffle(node_pool)
        count = generator.randint(8, min(30, len(node_pool)))
        selected = deepcopy(node_pool[:count])
        refs = {str(node["node_ref"]) for node in selected}
        eligible = [edge for edge in edge_pool if str(edge["source_ref"]) in refs and str(edge["target_ref"]) in refs]
        generator.shuffle(eligible)
        chosen_edges = deepcopy(eligible[:generator.randint(0, min(len(eligible), max(1, len(compact["relationships"]) + 4)))])
        observed = _token_count({"nodes": selected, "relationships": chosen_edges, "collapsed_execution_groups": []})
        candidate = (abs(target - observed), selected, chosen_edges)
        if best is None or candidate[0] < best[0]:
            best = candidate
    assert best is not None
    difference, selected, selected_edges = best
    value = {
        "job_evidence_order": list(reversed(JOB_ORDER)),
        "nodes": selected,
        "relationships": selected_edges,
        "handoffs": [],
        "collapsed_execution_groups": [],
        "disclosed_execution_groups": [],
        "random_match": {
            "selection_rule": "deterministic oracle-blind sample from the same four-job capture",
            "uses_fault_or_oracle_truth": False,
            "target_initial_evidence_tokens": target,
            "observed_initial_evidence_tokens": target - difference if _token_count({"nodes": selected, "relationships": selected_edges, "collapsed_execution_groups": []}) <= target else target + difference,
            "absolute_token_difference": difference,
        },
    }
    value["projection_sha256"] = ce.sha256(value)
    return value


def _semantic_declarations(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    declarations = []
    for position, job_id in enumerate(JOB_ORDER, 1):
        by_name = {str(value["function_name"]): value for value in catalogue["jobs"][job_id]["realized_boundaries"]}
        for name in FUNCTIONS[job_id]:
            boundary = by_name[name]
            declarations.append({
                "job": f"job_{position}",
                "captured_job_id": job_id,
                "qualified_function_name": boundary["static_identity"]["qualified_function_name"],
                "ordinary_responsibility": boundary["role"],
                "expected_interface": {
                    "inputs": deepcopy(boundary["expected_inputs"]),
                    "outputs": deepcopy(boundary["expected_outputs"]),
                },
                "handoff_role": "Produces or consumes only the ordinary artifacts shown in the ordered four-job workflow.",
            })
    if len(declarations) != 12:
        raise ValueError("N25 semantic declaration count changed")
    return {"semantic_declarations": declarations}


def _execution_record(catalogue: Mapping[str, Any], job_id: str, logs: bool = True) -> dict[str, Any]:
    position = JOB_ORDER.index(job_id) + 1
    value = {
        "job": f"job_{position}",
        "captured_job_id": job_id,
        "input": deepcopy(catalogue["jobs"][job_id]["input"]),
        "output": deepcopy(catalogue["jobs"][job_id]["output"]),
    }
    if logs:
        value.update({"stdout": str(catalogue["jobs"][job_id]["stdout"]), "stderr": str(catalogue["jobs"][job_id]["stderr"])})
    return value


def _base_package(catalogue: Mapping[str, Any], include_job4_logs: bool) -> dict[str, Any]:
    job2_input = catalogue["jobs"][DOWNSTREAM]["input"]
    job4 = _execution_record(catalogue, JOB4, include_job4_logs)
    return {
        "schema_version": "n25-four-stage-review-package-1",
        "review_task": TASK_TEXT,
        "behavioural_criteria": [
            "Treat the supplied demand, capability and delivery-rule fixtures as stipulated inputs.",
            "Every qualifying demand record should remain traceable through the ordered workflow without changing its identity or need text.",
            "The priority order and recommendation should follow the received demand evidence.",
            "Every received priority should become one campaign item and exactly one activation action.",
            "Items with a positive upstream rank and a delivery-rule match should be launchable; other items should remain represented for evidence review.",
            "The final focus, decision, action counts and action order should reflect the artifacts actually passed between jobs.",
        ],
        "pipeline_topology": [
            {"job": f"job_{position}", "captured_job_id": job_id, "position": position, "observation_point": job_id == JOB4}
            for position, job_id in enumerate(JOB_ORDER, 1)
        ],
        "top_level_demand_input": deepcopy(catalogue["jobs"][UPSTREAM]["input"]),
        "capability_fixture": deepcopy(job2_input.get("capabilities", [])),
        "delivery_rules_fixture": deepcopy(DELIVERY_RULES),
        "observed_job_4_execution": job4,
        "final_response_contract": {
            "fault_detected": "Boolean",
            "suspect_job": "job_1, job_2, job_3, job_4, or null",
            "suspect_function": "a function name visible in the supplied evidence, or null",
            "explanation": "concise evidence-grounded reasoning",
            "cited_evidence": "an array of exact evidence references or short exact visible excerpts",
        },
    }


def build_package(
    catalogue: Mapping[str, Any],
    source_bundle: list[dict[str, Any]],
    graphs: Mapping[str, Mapping[str, Any]],
    mode: str,
    source_setting: str,
    declaration_setting: str,
) -> dict[str, Any]:
    package = _base_package(catalogue, include_job4_logs=mode != "E01")
    if mode in {"E03", "E04"}:
        package["history"] = {"prior_task_records": []}
        if mode == "E04":
            records = []
            for job_id in JOB_ORDER[:3]:
                record = _execution_record(catalogue, job_id, True)
                record["chronology"] = {"position": JOB_ORDER.index(job_id) + 1, "precedes": f"job_{JOB_ORDER.index(job_id) + 2}"}
                record["exact_outgoing_handoffs"] = [deepcopy(value) for value in catalogue["handoffs"] if value["upstream_job_id"] == job_id]
                records.append(record)
            package["history"]["prior_task_records"] = records
    if mode in GRAPH_MODES:
        if mode == "E05":
            evidence = empty_graph()
        elif mode == "E06":
            compact = graphs["compact"]
            evidence = {
                "job_evidence_order": deepcopy(compact["job_evidence_order"]),
                "nodes": deepcopy(compact["nodes"]),
                "relationships": [],
                "collapsed_execution_groups": [],
                "disclosed_execution_groups": [],
            }
            evidence["projection_sha256"] = ce.sha256(evidence)
        elif mode in {"E07", "E08", "E09"}:
            evidence = deepcopy(graphs["compact"])
        elif mode == "E10":
            evidence = deepcopy(graphs["full"])
        else:
            evidence = deepcopy(graphs["random"])
        package["graph_review"] = {
            "framing": "Captured execution evidence may be used in the assessment.",
            "evidence": evidence,
        }
    if source_setting == "S1":
        package["separate_complete_source_bundle"] = deepcopy(source_bundle)
    if declaration_setting == "B1":
        package["semantic_declaration_bundle"] = _semantic_declarations(catalogue)
    if mode == "E08":
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {
            "operation": "expand_execution_group",
            "required_before_terminal": True,
            "maximum_completed_expansions": 1,
            "selection_must_be_model_selected": True,
        }
    elif mode == "E09":
        package["interaction_contract"] = {
            "operation": "reconsider_same_evidence",
            "required_second_pass": True,
            "evidence_bytes_added": 0,
        }
    return package


def schedule() -> dict[str, Any]:
    cells = []
    for instance_id in INSTANCES:
        for mode, name in MODES:
            for source in ("S0", "S1"):
                for declarations in ("B0", "B1"):
                    cell_id = f"{mode}-{source}-{declarations}"
                    cells.append({
                        "instance_id": instance_id,
                        "cell_id": cell_id,
                        "mode": mode,
                        "mode_name": name,
                        "source_setting": source,
                        "declaration_setting": declarations,
                        "branch_id": f"brn-{ce.sha256(['n25', instance_id, cell_id])[7:23]}",
                    })
    by_instance = {instance: [cell for cell in cells if cell["instance_id"] == instance] for instance in INSTANCES}
    reviews = []
    block = 0
    for repetition in range(1, 4):
        instance_order = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for instance in instance_order:
            values = by_instance[instance]
            rotation = block % len(values)
            for position, cell in enumerate(values[rotation:] + values[:rotation], 1):
                reviews.append({
                    **cell,
                    "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n25', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                    "local_block": block + 1,
                    "cell_position": position,
                })
            block += 1
    if (len(cells), len(reviews), len({value["trial_id"] for value in reviews})) != (308, 924, 924):
        raise AssertionError("N25 matrix changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _schema_for(mode: str, follow_up: bool = False) -> Path:
    if follow_up or mode not in {"E08", "E09"}:
        return FINAL_SCHEMA
    return REQUIRED_SCHEMA if mode == "E08" else RECONSIDER_SCHEMA


def _compatible_type(value: Any) -> set[str]:
    if value is None: return {"null"}
    if isinstance(value, bool): return {"boolean"}
    if isinstance(value, str): return {"string"}
    if isinstance(value, int): return {"integer", "number"}
    if isinstance(value, float): return {"number"}
    if isinstance(value, list): return {"array"}
    if isinstance(value, Mapping): return {"object"}
    return set()


def _validate_const_types(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        if "const" in value:
            declared = value.get("type")
            types = {declared} if isinstance(declared, str) else set(declared or [])
            if not types & _compatible_type(value["const"]):
                raise ValueError(f"N25 const lacks an explicit compatible type: {path}")
        for key, child in value.items():
            _validate_const_types(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_const_types(child, f"{path}[{index}]")


def validate_schemas(repo_root: Path) -> dict[str, str]:
    hashes = {}
    for relative in (FINAL_SCHEMA, REQUIRED_SCHEMA, RECONSIDER_SCHEMA):
        schema = _json(repo_root / relative)
        Draft202012Validator.check_schema(schema)
        validate_strict_provider_schema(schema, relative.as_posix())
        _validate_const_types(schema)
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
    forbidden = (
        "instance_id", "cell_id", "source_setting", "declaration_setting", "branch_id", "trial_id",
        "repetition", "seed", "truth_job", "truth_function", "designation", "mutation", "oracle",
        "qualification", "clean_comparison", "rejected_candidate",
    )
    if any(f'"{key}"' in visible for key in forbidden):
        raise ValueError("N25 rendered request leaks controller state")
    return request


def _diff_paths(left: Any, right: Any, prefix: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [prefix]
    if isinstance(left, Mapping):
        paths = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                paths.append(f"{prefix}.{key}")
            else:
                paths.extend(_diff_paths(left[key], right[key], f"{prefix}.{key}"))
        return paths
    if isinstance(left, list):
        if len(left) != len(right): return [prefix]
        return [path for index, values in enumerate(zip(left, right)) for path in _diff_paths(*values, f"{prefix}[{index}]")]
    return [] if left == right else [prefix]


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in package.items() if key not in {"available_operations", "interaction_contract"}}


def exposure_manifest(record: Mapping[str, Any]) -> dict[str, Any]:
    package = record["reviewer_package"]
    graph = package.get("graph_review", {}).get("evidence", {})
    separate = package.get("separate_complete_source_bundle", [])
    separate_sources = [str(file["content"]) for job in separate for file in job.get("files", [])]
    def sources(value: Any, context: bool = False) -> list[str]:
        found = []
        if isinstance(value, Mapping):
            for key, child in value.items(): found.extend(sources(child, context or str(key) in {"source", "source_text"}))
        elif isinstance(value, list):
            for child in value: found.extend(sources(child, context))
        elif context and isinstance(value, str): found.append(value)
        return found
    embedded = sources({key: value for key, value in package.items() if key != "separate_complete_source_bundle"})
    logs = [item[key] for item in [package.get("observed_job_4_execution", {}), *package.get("history", {}).get("prior_task_records", [])] for key in ("stdout", "stderr") if key in item]
    return {
        "branch_id": record["controller_condition"]["branch_id"],
        "model_visible_utf8_bytes": len(ce.canonical_json(render_request(package))),
        "estimated_model_visible_tokens": _token_count(render_request(package)),
        "source": {
            "separate_characters": sum(map(len, separate_sources)),
            "separate_tokens": sum(_token_count(value) for value in separate_sources),
            "naturally_embedded_characters": sum(map(len, embedded)),
            "naturally_embedded_tokens": sum(_token_count(value) for value in embedded),
            "total_reviewer_visible_source_characters": sum(map(len, [*separate_sources, *embedded])),
            "total_reviewer_visible_source_tokens": sum(_token_count(value) for value in [*separate_sources, *embedded]),
        },
        "history_records": len(package.get("history", {}).get("prior_task_records", [])),
        "log_characters": sum(map(len, logs)),
        "semantic_declarations": len(package.get("semantic_declaration_bundle", {}).get("semantic_declarations", [])),
        "graph_nodes": len(graph.get("nodes", [])),
        "graph_relationships": len(graph.get("relationships", [])),
        "collapsed_groups": len(graph.get("collapsed_execution_groups", [])),
    }


def _package_records(attempt_root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = _json(path)
        package_file = attempt_root / manifest["reviewer_package_path"]
        if ce.sha256(package_file.read_bytes()) != manifest["reviewer_package_file_sha256"]:
            raise ValueError("N25 package file binding changed")
        record = _json(package_file)
        if ce._verified_self_hash(record, "package_sha256") != manifest["package_sha256"]:
            raise ValueError("N25 package logical binding changed")
        records.append(record)
    return records


def _package_differences(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(records)
    by = {
        (value["controller_condition"]["instance_id"], value["controller_condition"]["cell_id"]): value["reviewer_package"]
        for value in values
    }
    rows = []
    for instance_id in INSTANCES:
        def check(name: str, left: str, right: str, roots: set[str], initial: bool = False) -> None:
            a, b = by[(instance_id, left)], by[(instance_id, right)]
            if initial:
                a, b = _initial_evidence(a), _initial_evidence(b)
            paths = _diff_paths(a, b)
            passed = all(path.split(".")[1] in roots for path in paths) and bool(paths or not roots)
            rows.append({"instance_id": instance_id, "invariant": name, "left": left, "right": right, "differing_paths": paths, "allowed_roots": sorted(roots), "passed": passed})
        for mode, _ in MODES:
            for declarations in ("B0", "B1"):
                check("S1_vs_S0", f"{mode}-S0-{declarations}", f"{mode}-S1-{declarations}", {"separate_complete_source_bundle"})
            for source in ("S0", "S1"):
                check("B1_vs_B0", f"{mode}-{source}-B0", f"{mode}-{source}-B1", {"semantic_declaration_bundle"})
        for source in ("S0", "S1"):
            for declarations in ("B0", "B1"):
                check("empty_history", f"E02-{source}-{declarations}", f"E03-{source}-{declarations}", {"history"})
                check("full_history", f"E03-{source}-{declarations}", f"E04-{source}-{declarations}", {"history"})
                check("empty_graph", f"E02-{source}-{declarations}", f"E05-{source}-{declarations}", {"graph_review"})
                check("compact_initial_E07_E08", f"E07-{source}-{declarations}", f"E08-{source}-{declarations}", set(), initial=True)
                check("compact_initial_E07_E09", f"E07-{source}-{declarations}", f"E09-{source}-{declarations}", set(), initial=True)
    if not all(row["passed"] for row in rows):
        raise ValueError(f"N25 paired-package isolation failed: {[row for row in rows if not row['passed']][:2]}")
    result = {"schema_version": "n25-package-differences-1", "rows": rows, "all_passed": True}
    result["report_sha256"] = ce.sha256(result)
    return result


def expand_execution_group(
    catalogue: Mapping[str, Any],
    index: Mapping[str, Any],
    package: Mapping[str, Any],
    group_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if "expand_execution_group" not in package.get("available_operations", []):
        raise ValueError("execution-group expansion is unavailable")
    binding = index["groups"].get(group_id)
    if binding is None:
        raise ValueError("execution group is not in the package's actual menu")
    evidence = package["graph_review"]["evidence"]
    advertised = {value["execution_group_id"] for value in evidence["collapsed_execution_groups"]}
    if group_id not in advertised:
        raise ValueError("execution group is not currently advertised")
    nodes = _node_by_ref(catalogue)
    selected = [_tag(nodes[ref][1], nodes[ref][0]) for ref in binding["node_refs"]]
    selected_refs = set(binding["node_refs"])
    selected_edges = [
        _tag(edge, job_id)
        for _, (job_id, edge) in sorted(_edge_by_ref(catalogue).items())
        if str(edge["source_ref"]) in selected_refs and str(edge["target_ref"]) in selected_refs
    ]
    updated = deepcopy(dict(package))
    graph = updated["graph_review"]["evidence"]
    existing_nodes = {str(node["node_ref"]) for node in graph["nodes"]}
    existing_edges = {str(edge["relationship_ref"]) for edge in graph["relationships"]}
    added_nodes = [node for node in selected if str(node["node_ref"]) not in existing_nodes]
    added_edges = [edge for edge in selected_edges if str(edge["relationship_ref"]) not in existing_edges]
    graph["nodes"].extend(added_nodes)
    graph["relationships"].extend(added_edges)
    descriptor = next(value for value in graph["collapsed_execution_groups"] if value["execution_group_id"] == group_id)
    graph["collapsed_execution_groups"] = [value for value in graph["collapsed_execution_groups"] if value["execution_group_id"] != group_id]
    graph["disclosed_execution_groups"].append(deepcopy(descriptor))
    graph.pop("projection_sha256", None)
    graph["projection_sha256"] = ce.sha256(graph)
    event = {
        "operation": "expand_execution_group",
        "status": "completed",
        "execution_group_id": group_id,
        "job_id": descriptor["job_id"],
        "func_stack": deepcopy(descriptor["func_stack"]),
        "nodes_added": [node["node_ref"] for node in added_nodes],
        "relationships_added": [edge["relationship_ref"] for edge in added_edges],
        "evidence_bytes_added": len(ce.canonical_json({"nodes": added_nodes, "relationships": added_edges})),
    }
    if not added_nodes:
        raise ValueError("execution-group expansion disclosed no new node")
    return updated, event


def qualify_packages(
    repo_root: Path,
    records: list[Mapping[str, Any]],
    prepared: Mapping[str, Any],
    design: Mapping[str, Any],
) -> dict[str, Any]:
    schema_hashes = validate_schemas(repo_root)
    if (len(records), len(design["review_trials"]), len(design["repair_traces"])) != (308, 924, 0):
        raise ValueError("N25 package or schedule count changed")
    if {value["instance_id"] for value in design["cells"]} != set(INSTANCES):
        raise ValueError("N25 schedule instance panel changed")
    cell_counts = {f"{mode}-{source}-{declarations}": 0 for mode, _ in MODES for source in ("S0", "S1") for declarations in ("B0", "B1")}
    for value in design["cells"]:
        cell_counts[value["cell_id"]] += 1
    if set(cell_counts.values()) != {7}:
        raise ValueError("N25 cells do not contain the same seven instances")
    if sum(value["mode"] == "E08" for value in design["review_trials"]) != 84 or sum(value["mode"] == "E09" for value in design["review_trials"]) != 84:
        raise ValueError("N25 mandatory follow-up schedule changed")
    if len(list((repo_root / ATTEMPT / "job-captures").glob("*/*.json"))) != 28:
        raise ValueError("N25 per-job capture record count changed")

    by = {
        (value["controller_condition"]["instance_id"], value["controller_condition"]["cell_id"]): value["reviewer_package"]
        for value in records
    }
    maximum_bytes = 0
    maximum_tokens = 0
    no_model_expansions = 0
    for record in records:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        request = render_request(package)
        size = len(ce.canonical_json(request))
        maximum_bytes = max(maximum_bytes, size)
        maximum_tokens = max(maximum_tokens, _token_count(request))
        if _token_count(request) > 1_000_000:
            raise ValueError(f"N25 complete package exceeds the provider context gate: {condition['cell_id']}")
        if condition["mode"] == "E08":
            catalogue = prepared["catalogues"][condition["instance_id"]]
            index = prepared["indexes"][condition["instance_id"]]
            groups = package["graph_review"]["evidence"]["collapsed_execution_groups"]
            if {value["execution_group_id"] for value in groups} != set(index["groups"]):
                raise ValueError("N25 Required-One menu differs from real currently available groups")
            expanded, event = expand_execution_group(catalogue, index, package, groups[0]["execution_group_id"])
            if event["status"] != "completed" or len(expanded["graph_review"]["evidence"]["disclosed_execution_groups"]) != 1:
                raise ValueError("N25 Required-One no-model simulation failed")
            no_model_expansions += 1

    for instance_id in INSTANCES:
        catalogue = prepared["catalogues"][instance_id]
        if list(catalogue["job_order"]) != list(JOB_ORDER) or len(catalogue["handoffs"]) != 8:
            raise ValueError("N25 four-job catalogue order or handoff count changed")
        if sum(len(catalogue["jobs"][job]["realized_boundaries"]) for job in JOB_ORDER) != 12:
            raise ValueError("N25 realized function count changed")
        for source in ("S0", "S1"):
            for declarations in ("B0", "B1"):
                e06 = by[(instance_id, f"E06-{source}-{declarations}")]
                e07 = by[(instance_id, f"E07-{source}-{declarations}")]
                if e06["graph_review"]["evidence"]["nodes"] != e07["graph_review"]["evidence"]["nodes"]:
                    raise ValueError("N25 E06 and E07 anchor nodes differ")
                if e06["graph_review"]["evidence"]["relationships"] or e06["graph_review"]["evidence"]["collapsed_execution_groups"] or "available_operations" in e06:
                    raise ValueError("N25 E06 exposes relationships, groups or operations")
                runtime = [by[(instance_id, f"{mode}-{source}-{declarations}")]["graph_review"]["evidence"] for mode in ("E07", "E08", "E09")]
                if len({ce.canonical_json(value) for value in runtime}) != 1:
                    raise ValueError("N25 E07-E09 initial runtime evidence differs")
                random_match = by[(instance_id, f"E11-{source}-{declarations}")]["graph_review"]["evidence"]["random_match"]
                tolerance = max(64, int(random_match["target_initial_evidence_tokens"] * 0.05))
                if random_match["uses_fault_or_oracle_truth"] or random_match["absolute_token_difference"] > tolerance:
                    raise ValueError(f"N25 random graph is not oracle-blind and budget-matched: {instance_id}")
                if by[(instance_id, f"E09-{source}-{declarations}")]["interaction_contract"]["evidence_bytes_added"] != 0:
                    raise ValueError("N25 reconsideration adds evidence")
    differences = _package_differences(records)
    exposures = [exposure_manifest(record) for record in records]
    return {
        "status": "passed",
        "model_calls": 0,
        "instances": 7,
        "new_job_captures": 14,
        "catalogues": 7,
        "functions_per_catalogue": 12,
        "handoffs_per_catalogue": 8,
        "packages": 308,
        "reviews": 924,
        "mandatory_evidence_follow_ups": 84,
        "mandatory_zero_evidence_follow_ups": 84,
        "planned_provider_calls": 1092,
        "repairs": 0,
        "strict_schema_hashes": schema_hashes,
        "pairwise_checks": len(differences["rows"]),
        "no_model_expansion_simulations": no_model_expansions,
        "maximum_model_visible_bytes": maximum_bytes,
        "maximum_estimated_input_tokens": maximum_tokens,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if existing:
        if len(existing) != 308:
            raise ValueError("N25 frozen package preparation is partial")
        qualification = qualify_packages(repo_root, existing, prepared, design)
        exposure = {record["controller_condition"]["branch_id"]: exposure_manifest(record) for record in existing}
        artifacts = {
            "package-exposure-manifest.json": {"schema_version": "n25-exposure-manifest-1", "packages": exposure},
            "pairwise-package-differences.json": _package_differences(existing),
            "review-design.json": {"schema_version": "n25-review-design-1", "review_trials": design["review_trials"]},
            "repair-design.json": {"schema_version": "n25-repair-design-1", "repair_traces": []},
            "qualification/no-model-verification.json": qualification,
        }
        for relative, value in artifacts.items():
            path = target / relative
            if path.exists():
                if _json(path) != value:
                    raise ValueError(f"N25 existing no-model artifact differs: {relative}")
            else:
                ce._write_immutable(path, value)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}

    graph_sets = {}
    for instance_id in INSTANCES:
        compact, index = build_compact_graph(prepared["catalogues"][instance_id])
        if index["index_sha256"] != prepared["indexes"][instance_id]["index_sha256"]:
            raise ValueError("N25 compact group index is not deterministic")
        graph_sets[instance_id] = {
            "compact": compact,
            "full": full_graph(prepared["catalogues"][instance_id]),
            "random": random_matched_graph(prepared["catalogues"][instance_id], compact),
        }
        for kind, graph in graph_sets[instance_id].items():
            ce._write_immutable(target / "projections" / f"{instance_id}-{kind}.json", graph)
    records = []
    for condition in design["cells"]:
        instance_id = condition["instance_id"]
        package = build_package(
            prepared["catalogues"][instance_id],
            prepared["source_bundles"][instance_id],
            graph_sets[instance_id],
            condition["mode"], condition["source_setting"], condition["declaration_setting"],
        )
        record = {
            "schema_version": "n25-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance_id]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance_id]["catalogue_sha256"],
            "source_bundle_file_sha256": ce.sha256((target / "source-bundles" / f"{instance_id}.json").read_bytes()),
            "group_index_file_sha256": ce.sha256((target / "group-index" / f"{instance_id}.json").read_bytes()),
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        branch = condition["branch_id"]
        package_path = target / "packages" / branch / "reviewer-package.json"
        ce._write_immutable(package_path, record)
        manifest = {
            "schema_version": "n25-controller-manifest-1",
            "controller_condition": deepcopy(condition),
            "reviewer_package_path": package_path.relative_to(target).as_posix(),
            "reviewer_package_file_sha256": ce.sha256(package_path.read_bytes()),
            "package_sha256": record["package_sha256"],
        }
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, records, prepared, design)
    exposure = {record["controller_condition"]["branch_id"]: exposure_manifest(record) for record in records}
    differences = _package_differences(records)
    ce._write_immutable(target / "package-exposure-manifest.json", {"schema_version": "n25-exposure-manifest-1", "packages": exposure})
    ce._write_immutable(target / "pairwise-package-differences.json", differences)
    ce._write_immutable(target / "review-design.json", {"schema_version": "n25-review-design-1", "review_trials": design["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n25-repair-design-1", "repair_traces": []})
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n25_experiment.py"), JOB3_SOURCE, JOB4_SOURCE, PROMPT,
        FINAL_SCHEMA, REQUIRED_SCHEMA, RECONSIDER_SCHEMA, JOB3_OUTPUT_SCHEMA, JOB4_OUTPUT_SCHEMA,
        Path("tests/test_n25_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if (target / "experiment-freeze.json").exists():
        raise FileExistsError("N25 Attempt 042 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("N25 cannot freeze after a review exists")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists():
        raise ValueError("N25 focused test result must be recorded before freeze")
    if _json(focused).get("status") != "passed":
        raise ValueError("N25 focused tests did not pass")
    prepared = built["prepared"]
    freeze = {
        "schema_version": "n25-experiment-freeze-1",
        "attempt": "042",
        "status": "frozen_before_live_review",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "protected_boundaries": deepcopy(PROTECTED),
        "source_fixed_file_hashes": deepcopy(SOURCE_FIXED),
        "reuse_bindings_file_sha256": ce.sha256((target / "qualification/reuse-bindings.json").read_bytes()),
        "new_job_bindings_file_sha256": ce.sha256((target / "qualification/new-job-bindings.json").read_bytes()),
        "propagation_file_sha256": ce.sha256((target / "qualification/propagation.json").read_bytes()),
        "precanonical_probe_file_sha256": ce.sha256((target / "qualification/precanonical-capture-implementation-probe.json").read_bytes()),
        "delivery_rules_file_sha256": ce.sha256((target / "delivery-rules.json").read_bytes()),
        "capture_hashes": {key: prepared["captures"][key]["capture_sha256"] for key in INSTANCES},
        "capture_file_hashes": {key: ce.sha256((target / "captures" / f"{key}.json").read_bytes()) for key in INSTANCES},
        "catalogue_hashes": {key: prepared["catalogues"][key]["catalogue_sha256"] for key in INSTANCES},
        "instance_hashes": {key: prepared["instances"][key]["instance_sha256"] for key in INSTANCES},
        "source_bundle_file_hashes": {key: ce.sha256((target / "source-bundles" / f"{key}.json").read_bytes()) for key in INSTANCES},
        "group_index_file_hashes": {key: ce.sha256((target / "group-index" / f"{key}.json").read_bytes()) for key in INSTANCES},
        "job_capture_tree_sha256": ce.sha256(ce._tree_hashes(target / "job-captures")),
        "capture_branch_tree_sha256": ce.sha256(ce._tree_hashes(target / "capture-branches")),
        "projection_tree_sha256": ce.sha256(ce._tree_hashes(target / "projections")),
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(target / "controller-manifests")),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "repair_design_sha256": ce.sha256([]),
        "exposure_manifest_file_sha256": ce.sha256((target / "package-exposure-manifest.json").read_bytes()),
        "pairwise_report_file_sha256": ce.sha256((target / "pairwise-package-differences.json").read_bytes()),
        "no_model_verification_file_sha256": ce.sha256((target / "qualification/no-model-verification.json").read_bytes()),
        "focused_test_results_file_sha256": ce.sha256(focused.read_bytes()),
        "expected_counts": {
            "faults": 6, "controls": 1, "jobs": 4, "new_job_captures": 14,
            "catalogues": 7, "packages": 308, "reviews": 924,
            "required_expansion_follow_ups": 84, "reconsideration_follow_ups": 84,
            "provider_calls": 1092, "repairs": 0,
        },
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0,
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
    observed = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N25 frozen implementation changed: {relative}")
    for relative, expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N25 protected boundary changed: {relative}")
    root = repo_root / "outputs/fault-experiments-v2-2-n10"
    for relative, expected in freeze["source_fixed_file_hashes"].items():
        if ce.sha256((root / relative).read_bytes()) != expected:
            raise ValueError(f"N25 reused source artifact changed after freeze: {relative}")
    prepared = prepare_attempt(repo_root, target)
    records = _package_records(target)
    design = {
        "cells": [deepcopy(record["controller_condition"]) for record in records],
        "review_trials": _json(target / "review-design.json")["review_trials"],
        "repair_traces": _json(target / "repair-design.json")["repair_traces"],
    }
    qualification = qualify_packages(repo_root, records, prepared, design)
    checks = {
        "qualification/reuse-bindings.json": "reuse_bindings_file_sha256",
        "qualification/new-job-bindings.json": "new_job_bindings_file_sha256",
        "qualification/propagation.json": "propagation_file_sha256",
        "qualification/precanonical-capture-implementation-probe.json": "precanonical_probe_file_sha256",
        "delivery-rules.json": "delivery_rules_file_sha256",
        "package-exposure-manifest.json": "exposure_manifest_file_sha256",
        "pairwise-package-differences.json": "pairwise_report_file_sha256",
        "qualification/no-model-verification.json": "no_model_verification_file_sha256",
        "qualification/focused-test-results.json": "focused_test_results_file_sha256",
    }
    for relative, key in checks.items():
        if ce.sha256((target / relative).read_bytes()) != freeze[key]:
            raise ValueError(f"N25 frozen artifact changed: {relative}")
    if ce.sha256(ce._tree_hashes(target / "packages")) != freeze["package_tree_sha256"] or sorted(record["package_sha256"] for record in records) != freeze["package_hashes"]:
        raise ValueError("N25 package tree changed after freeze")
    if ce.sha256(ce._tree_hashes(target / "controller-manifests")) != freeze["controller_manifest_tree_sha256"] or ce.sha256(design["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("N25 controller manifests or schedule changed")
    if ce.sha256(ce._tree_hashes(target / "job-captures")) != freeze["job_capture_tree_sha256"] or ce.sha256(ce._tree_hashes(target / "capture-branches")) != freeze["capture_branch_tree_sha256"] or ce.sha256(ce._tree_hashes(target / "projections")) != freeze["projection_tree_sha256"]:
        raise ValueError("N25 capture or projection bindings changed")
    return {
        "status": "verified",
        "freeze_sha256": observed,
        "qualification": qualification,
        "capture_count": 7,
        "new_job_capture_count": 14,
        "catalogue_count": 7,
        "package_count": 308,
        "review_count": 924,
        "repair_count": 0,
    }


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path = attempt_root / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((attempt_root / "reviews").glob("*.json")):
        raise ValueError("N25 review exists before live authority consumption")
    verified = verify_frozen_attempt(repo_root, attempt_root)
    record = {
        "schema_version": "n25-live-consumption-1",
        "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "controller-manifests")),
        "review_design_file_sha256": ce.sha256((attempt_root / "review-design.json").read_bytes()),
        "protected_file_hashes": deepcopy(PROTECTED),
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 308, "reviews": 924, "provider_calls": 1092, "repairs": 0},
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _normalized_function(value: Any) -> str | None:
    if value is None:
        return None
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(value).strip().lower())
    return names[-1] if names else None


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], schema_path: Path) -> dict[str, Any]:
    schema = _json(repo_root / schema_path)
    scientific = {key: deepcopy(response.get(key)) for key in schema["required"]}
    Draft202012Validator(schema).validate(scientific)
    visible = ce.canonical_json(package).decode()
    function = _normalized_function(scientific["suspect_function"])
    return {
        "valid": True,
        "receipt": scientific,
        "fault_detected": bool(scientific["fault_detected"]),
        "suspect_job": scientific["suspect_job"],
        "normalized_suspect_function": function,
        "suspect_function_visible": function is None or function in visible.lower(),
        "invalid_evidence_refs": [str(value) for value in scientific["cited_evidence"] if str(value) not in visible],
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


def _provider_review(
    repo_root: Path,
    attempt_root: Path,
    request: Mapping[str, Any],
    parent_id: str,
    mode: str,
    follow_up: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    response = ce._provider_call(
        repo_root,
        attempt_root,
        kind="review",
        model_request=request,
        controller_parent_id=parent_id,
        review_prompt=PROMPT,
        review_schema=_schema_for(mode, follow_up),
    )
    return {**response, "n25_latency_seconds": time.monotonic() - started}


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count", "n25_latency_seconds")}


def _usage(response: Mapping[str, Any], purpose: str) -> dict[str, Any]:
    return {**ce.actual_usage_record(response, purpose=purpose, phase="n25_review"), "latency_seconds": response.get("n25_latency_seconds")}


def run_review_session(
    repo_root: Path,
    attempt_root: Path,
    catalogue: Mapping[str, Any],
    index: Mapping[str, Any],
    package_record: Mapping[str, Any],
    trial_id: str,
) -> dict[str, Any]:
    mode = str(package_record["controller_condition"]["mode"])
    package = deepcopy(package_record["reviewer_package"])
    initial = _provider_review(repo_root, attempt_root, render_request(package), trial_id, mode)
    pre = validate_response(repo_root, package, initial, _schema_for(mode))
    final = pre
    current = package
    calls = [_call_record(initial)]
    usage = [_usage(initial, "initial_review")]
    events = []
    diagnostics = []
    if mode == "E08":
        action = pre["receipt"]["next_action"]
        try:
            current, event = expand_execution_group(catalogue, index, package, str(action["execution_group_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            diagnostics.append({"status": "rejected_without_model_call", "reason": str(exc), "request": deepcopy(action), "evidence_bytes_added": 0})
        else:
            events.append(event)
            current.pop("available_operations", None)
            current.pop("interaction_contract", None)
            response = _provider_review(repo_root, attempt_root, render_request(current, event), f"{trial_id}-follow-up-01", mode, True)
            final = validate_response(repo_root, current, response, FINAL_SCHEMA)
            calls.append(_call_record(response))
            usage.append(_usage(response, "model_selected_nested_disclosure"))
    elif mode == "E09":
        before = ce.sha256(_initial_evidence(current))
        event = {"operation": "reconsider_same_evidence", "status": "completed", "evidence_bytes_added": 0}
        response = _provider_review(repo_root, attempt_root, render_request(current, event), f"{trial_id}-follow-up-01", mode, True)
        if ce.sha256(_initial_evidence(current)) != before:
            raise RuntimeError("N25 reconsideration changed model-visible evidence")
        final = validate_response(repo_root, current, response, FINAL_SCHEMA)
        events.append(event)
        calls.append(_call_record(response))
        usage.append(_usage(response, "zero_evidence_reconsideration"))
    graph = current.get("graph_review", {}).get("evidence", {})
    selected_group = next((event for event in events if event["operation"] == "expand_execution_group"), None)
    return {
        "pre_validation": pre,
        "final_validation": final,
        "operation_events": events,
        "operation_diagnostics": diagnostics,
        "completed_evidence_expansions": sum(event["operation"] == "expand_execution_group" for event in events),
        "completed_reconsiderations": sum(event["operation"] == "reconsider_same_evidence" for event in events),
        "selected_group": deepcopy(selected_group),
        "disclosed_node_count": len(graph.get("nodes", [])),
        "disclosed_relationship_count": len(graph.get("relationships", [])),
        "call_records": calls,
        "usage": ce.aggregate_actual_usage_records(usage),
    }


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for review in reviews:
        trial = review["controller_trial"]
        rows.append({
            **deepcopy(trial),
            **{key: deepcopy(review[key]) for key in (
                "designation", "truth_function", "fault_detected", "false_positive",
                "correct_job_attribution", "exact_function_localisation", "suspect_job",
                "suspect_function", "pre_fault_detected", "pre_suspect_job",
                "pre_suspect_function", "completed_evidence_expansions",
                "completed_reconsiderations", "selected_group_contained_truth_function",
                "operation_events", "operation_diagnostics", "disclosed_node_count",
                "disclosed_relationship_count", "usage",
            )},
        })
    return rows


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]
    calls = [call for row in rows for call in row["usage"].get("calls", [])]
    return {
        "reviews": len(rows),
        "provider_calls": len(calls),
        "fault_detection": {"numerator": sum(row["fault_detected"] for row in faults), "denominator": len(faults)},
        "correct_job_attribution": {"numerator": sum(row["correct_job_attribution"] for row in faults), "denominator": len(faults)},
        "exact_function_localisation": {"numerator": sum(row["exact_function_localisation"] for row in faults), "denominator": len(faults)},
        "control_false_positives": {"numerator": sum(row["false_positive"] for row in controls), "denominator": len(controls)},
        "selected_job_distribution": {("null" if value is None else value): sum(row["suspect_job"] == value for row in rows) for value in ("job_1", "job_2", "job_3", "job_4", None)},
        "selected_function_distribution": {("null" if value is None else value): sum(row["suspect_function"] == value for row in rows) for value in sorted({row["suspect_function"] for row in rows}, key=lambda value: str(value))},
        "input_tokens": sum(int(call.get("input_tokens") or 0) for call in calls),
        "cached_input_tokens": sum(int(call.get("cached_input_tokens") or 0) for call in calls),
        "output_tokens": sum(int(call.get("output_tokens") or 0) for call in calls),
        "total_tokens": sum(int(call.get("total_tokens") or (int(call.get("input_tokens") or 0) + int(call.get("output_tokens") or 0))) for call in calls),
        "latency_seconds": sum(float(call.get("latency_seconds") or 0) for call in calls),
    }


def _paired_contrast(rows: list[Mapping[str, Any]], name: str, left: Mapping[str, str], right: Mapping[str, str], outcome: str) -> dict[str, Any]:
    differences = []
    for instance_id in INSTANCES[:-1]:
        def select(spec: Mapping[str, str]) -> list[Mapping[str, Any]]:
            return [row for row in rows if row["instance_id"] == instance_id and all(str(row[key]) == value for key, value in spec.items())]
        a, b = select(left), select(right)
        if not a or not b:
            raise ValueError(f"N25 contrast cell missing: {name}/{instance_id}")
        differences.append(sum(bool(row[outcome]) for row in a) / len(a) - sum(bool(row[outcome]) for row in b) / len(b))
    mean = sum(differences) / len(differences)
    se = math.sqrt(sum((value - mean) ** 2 for value in differences) / 5) / math.sqrt(6)
    margin = 2.571 * se
    return {
        "name": name, "outcome": outcome, "left": dict(left), "right": dict(right),
        "independent_fault_units": 6, "per_instance_differences": differences,
        "mean_difference": mean, "standard_error": se,
        "confidence_interval_95_t": [mean - margin, mean + margin],
    }


def write_analysis(repo_root: Path, attempt_root: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    if len(rows) != 924:
        raise ValueError("N25 analysis requires exactly 924 completed reviews")
    analysis_dir = attempt_root / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    result_columns = [
        "trial_id", "instance_id", "cell_id", "mode", "mode_name", "source_setting",
        "declaration_setting", "repetition", "designation", "truth_function", "fault_detected",
        "false_positive", "correct_job_attribution", "exact_function_localisation", "suspect_job",
        "suspect_function", "pre_fault_detected", "pre_suspect_job", "pre_suspect_function",
        "completed_evidence_expansions", "completed_reconsiderations",
        "selected_group_contained_truth_function", "disclosed_node_count", "disclosed_relationship_count",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=result_columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in result_columns})
    _write_bytes(analysis_dir / "all-review-rows.csv", buffer.getvalue())

    transition_columns = [
        "trial_id", "instance_id", "mode", "source_setting", "declaration_setting", "repetition",
        "pre_fault_detected", "pre_suspect_job", "pre_suspect_function", "fault_detected",
        "suspect_job", "suspect_function", "selected_group", "truth_contained", "evidence_bytes_added",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=transition_columns)
    writer.writeheader()
    for row in rows:
        if row["mode"] in {"E08", "E09"}:
            event = row["operation_events"][0] if row["operation_events"] else {}
            writer.writerow({
                **{key: row.get(key) for key in transition_columns[:12]},
                "selected_group": event.get("execution_group_id", ""),
                "truth_contained": row["selected_group_contained_truth_function"],
                "evidence_bytes_added": event.get("evidence_bytes_added", 0),
            })
    _write_bytes(analysis_dir / "adaptive-and-reconsideration-transitions.csv", buffer.getvalue())

    token_columns = ["trial_id", "mode", "call_index", "purpose", "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "latency_seconds", "estimated_cost_usd"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=token_columns)
    writer.writeheader()
    for row in rows:
        for call_index, call in enumerate(row["usage"].get("calls", []), 1):
            input_tokens = int(call.get("input_tokens") or 0)
            cached = int(call.get("cached_input_tokens") or 0)
            output = int(call.get("output_tokens") or 0)
            cost = ((input_tokens - cached) * 5.0 + cached * 0.5 + output * 30.0) / 1_000_000
            writer.writerow({"trial_id": row["trial_id"], "mode": row["mode"], "call_index": call_index, **{key: call.get(key) for key in token_columns[3:-1]}, "estimated_cost_usd": cost})
    _write_bytes(analysis_dir / "token-and-costs.csv", buffer.getvalue())

    cell_summaries = {
        cell: _summary([row for row in rows if row["cell_id"] == cell])
        for cell in sorted({row["cell_id"] for row in rows})
    }
    fault_summaries = {
        instance: _summary([row for row in rows if row["instance_id"] == instance])
        for instance in INSTANCES
    }
    condition_summaries = {
        f"{instance}/{cell}": _summary([row for row in rows if row["instance_id"] == instance and row["cell_id"] == cell])
        for instance in INSTANCES
        for cell in sorted({row["cell_id"] for row in rows})
    }
    mode_pairs = (
        ("job4_logs", "E02", "E01"),
        ("empty_history_framing", "E03", "E02"),
        ("actual_history", "E04", "E03"),
        ("empty_graph_framing", "E05", "E02"),
        ("compact_node_contents", "E06", "E05"),
        ("compact_relationships_and_nesting", "E07", "E06"),
        ("model_selected_disclosure", "E08", "E07"),
        ("new_evidence_vs_reconsideration", "E08", "E09"),
        ("complete_graph", "E10", "E05"),
        ("random_vs_structural_compact", "E11", "E07"),
    )
    contrasts = []
    outcomes = ("fault_detected", "correct_job_attribution", "exact_function_localisation")
    for name, left, right in mode_pairs:
        for source in ("S0", "S1"):
            for declarations in ("B0", "B1"):
                for outcome in outcomes:
                    contrasts.append(_paired_contrast(rows, name, {"mode": left, "source_setting": source, "declaration_setting": declarations}, {"mode": right, "source_setting": source, "declaration_setting": declarations}, outcome))
    for mode, _ in MODES:
        for declarations in ("B0", "B1"):
            for outcome in outcomes:
                contrasts.append(_paired_contrast(rows, "complete_source", {"mode": mode, "source_setting": "S1", "declaration_setting": declarations}, {"mode": mode, "source_setting": "S0", "declaration_setting": declarations}, outcome))
        for source in ("S0", "S1"):
            for outcome in outcomes:
                contrasts.append(_paired_contrast(rows, "semantic_declarations", {"mode": mode, "source_setting": source, "declaration_setting": "B1"}, {"mode": mode, "source_setting": source, "declaration_setting": "B0"}, outcome))
    aggregate = _summary(rows)
    agreement_rows = []
    for instance in INSTANCES:
        for cell in sorted({row["cell_id"] for row in rows}):
            selected = [row for row in rows if row["instance_id"] == instance and row["cell_id"] == cell]
            agreement_rows.append({
                "instance_id": instance,
                "cell_id": cell,
                **{outcome: len({bool(row[outcome]) for row in selected}) == 1 for outcome in outcomes},
            })
    exposure_values = list(_json(attempt_root / "package-exposure-manifest.json")["packages"].values())
    adaptive_rows = [row for row in rows if row["mode"] == "E08"]
    reconsider_rows = [row for row in rows if row["mode"] == "E09"]
    analysis = {
        "schema_version": "n25-analysis-1",
        "review_count": len(rows),
        "aggregate": aggregate,
        "cell_summaries": cell_summaries,
        "fault_summaries": fault_summaries,
        "instance_cell_summaries": condition_summaries,
        "paired_instance_level_contrasts": contrasts,
        "required_expansion_completion": {"numerator": sum(row["completed_evidence_expansions"] == 1 for row in rows if row["mode"] == "E08"), "denominator": sum(row["mode"] == "E08" for row in rows)},
        "reconsideration_completion": {"numerator": sum(row["completed_reconsiderations"] == 1 for row in rows if row["mode"] == "E09"), "denominator": sum(row["mode"] == "E09" for row in rows)},
        "adaptive_truth_group_selection": {"numerator": sum(row["selected_group_contained_truth_function"] for row in rows if row["mode"] == "E08" and row["designation"] == "upstream_fault"), "denominator": sum(row["mode"] == "E08" and row["designation"] == "upstream_fault" for row in rows)},
        "adaptive_diagnosis_transitions": {
            "sessions": len(adaptive_rows),
            "detection_changed": sum(row["pre_fault_detected"] != row["fault_detected"] for row in adaptive_rows),
            "job_changed": sum(row["pre_suspect_job"] != row["suspect_job"] for row in adaptive_rows),
            "function_changed": sum(row["pre_suspect_function"] != row["suspect_function"] for row in adaptive_rows),
            "selected_group_distribution": {
                group: sum(row["operation_events"] and row["operation_events"][0].get("execution_group_id") == group for row in adaptive_rows)
                for group in sorted({row["operation_events"][0].get("execution_group_id") for row in adaptive_rows if row["operation_events"]})
            },
        },
        "reconsideration_diagnosis_transitions": {
            "sessions": len(reconsider_rows),
            "evidence_bytes_added": sum((row["operation_events"][0].get("evidence_bytes_added", 0) if row["operation_events"] else 0) for row in reconsider_rows),
            "detection_changed": sum(row["pre_fault_detected"] != row["fault_detected"] for row in reconsider_rows),
            "job_changed": sum(row["pre_suspect_job"] != row["suspect_job"] for row in reconsider_rows),
            "function_changed": sum(row["pre_suspect_function"] != row["suspect_function"] for row in reconsider_rows),
        },
        "repetition_agreement": {
            "instance_cell_rows": agreement_rows,
            **{outcome: {"numerator": sum(row[outcome] for row in agreement_rows), "denominator": len(agreement_rows)} for outcome in outcomes},
        },
        "exposure_summary": {
            "packages": len(exposure_values),
            "visible_source_tokens_minimum": min(value["source"]["total_reviewer_visible_source_tokens"] for value in exposure_values),
            "visible_source_tokens_maximum": max(value["source"]["total_reviewer_visible_source_tokens"] for value in exposure_values),
            "graph_nodes_minimum": min(value["graph_nodes"] for value in exposure_values),
            "graph_nodes_maximum": max(value["graph_nodes"] for value in exposure_values),
            "graph_relationships_minimum": min(value["graph_relationships"] for value in exposure_values),
            "graph_relationships_maximum": max(value["graph_relationships"] for value in exposure_values),
            "collapsed_groups_minimum": min(value["collapsed_groups"] for value in exposure_values),
            "collapsed_groups_maximum": max(value["collapsed_groups"] for value in exposure_values),
        },
        "pricing": {"model": "gpt-5.5", "usd_per_million_tokens": {"input": 5.0, "cached_input": 0.5, "output": 30.0}},
        "estimated_cost_usd": ((aggregate["input_tokens"] - aggregate["cached_input_tokens"]) * 5.0 + aggregate["cached_input_tokens"] * 0.5 + aggregate["output_tokens"] * 30.0) / 1_000_000,
        "descriptive_prior_attempt_comparison": {
            "attempts": ["033", "041"],
            "pooled": False,
            "reason": "Observation point and packages differ; only genuinely common fault/arm constructs may be compared descriptively.",
        },
        "limitations": [
            "The six fault mechanisms are the independent faulty units; repetitions are averaged within instance.",
            "E07 versus E06 combines real relationships with nesting descriptors and is not a pure topology effect.",
            "S0 omits a separate complete source bundle but source naturally embedded in captured nodes can remain visible.",
            "Provider-reported usage fields are preserved; unavailable fields are not inferred.",
        ],
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(analysis_dir / "summary.json", analysis)
    return analysis_dir / "summary.json"


def _write_reports(repo_root: Path, attempt_root: Path) -> Path:
    analysis = _json(attempt_root / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N25-four-stage-campaign-diagnosis"
    report_dir.mkdir(parents=True, exist_ok=True)
    def rate(value: Mapping[str, Any]) -> str:
        denominator = int(value["denominator"])
        return f"{value['numerator']}/{denominator} ({100 * value['numerator'] / denominator:.2f}%)" if denominator else "0/0"
    findings = [
        "# N25 four-stage campaign-diagnosis findings",
        "",
        "N25 is a new four-stage downstream-first experiment. Earlier responses were not pooled into these results.",
        "",
        "## Aggregate outcomes",
        "",
        f"- Fault detection: {rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {rate(aggregate['correct_job_attribution'])}",
        f"- Exact Job-1 function localisation: {rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {rate(aggregate['control_false_positives'])}",
        f"- Required model-selected expansions: {analysis['required_expansion_completion']['numerator']}/{analysis['required_expansion_completion']['denominator']}",
        f"- Zero-evidence reconsiderations: {analysis['reconsideration_completion']['numerator']}/{analysis['reconsideration_completion']['denominator']}",
        "",
        "## Interpretation boundary",
        "",
        "The six fault mechanisms are the independent faulty units. Repetitions are averaged within each instance before cross-instance summaries. E07 versus E06 combines relationships and nesting descriptors, and prior attempts are descriptive comparisons only.",
        "",
        "## Immutable artifacts",
        "",
        f"- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-042/experiment-freeze.json)",
        f"- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-042/analysis/summary.json)",
        f"- [All review rows](../../../../outputs/fault-experiments-v2-2-n10/attempt-042/analysis/all-review-rows.csv)",
        f"- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-042/replay.json)",
        f"- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-042/terminal-state.json)",
        "",
    ]
    _write_bytes(report_dir / "findings.md", "\n".join(findings))
    tables = ["# N25 comprehensive cell table", "", "| Cell | Reviews | Detection | Job 1 | Exact function | Control FP | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cell, value in analysis["cell_summaries"].items():
        tables.append(f"| {cell} | {value['reviews']} | {rate(value['fault_detection'])} | {rate(value['correct_job_attribution'])} | {rate(value['exact_function_localisation'])} | {rate(value['control_false_positives'])} | {value['provider_calls']} |")
    tables += ["", "Machine-readable paired contrasts and distributions are in the immutable analysis summary.", ""]
    _write_bytes(report_dir / "tables.md", "\n".join(tables))
    return report_dir / "findings.md"


def _write_handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze = _json(attempt_root / "experiment-freeze.json")
    analysis = _json(attempt_root / "analysis/summary.json")
    replay = _json(attempt_root / "replay.json")
    terminal = _json(attempt_root / "terminal-state.json")
    artifacts = {
        "freeze": attempt_root / "experiment-freeze.json",
        "captures": attempt_root / "captures",
        "packages": attempt_root / "packages",
        "reviews": attempt_root / "reviews",
        "analysis": attempt_root / "analysis",
        "replay": attempt_root / "replay.json",
        "terminal": attempt_root / "terminal-state.json",
    }
    hashes = {name: ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name, path in artifacts.items()}
    aggregate = analysis["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N25 Attempt 042 four-stage campaign-diagnosis results", "",
        f"Status: `{terminal['status']}`", f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`", "", "Counts", "",
        "- Seven instances: six Job-1 faults and one clean control",
        "- Four jobs; fourteen new Job-3/Job-4 executions and captures",
        "- 308 packages; 924 reviews; 168 mandatory follow-ups; 0 repairs",
        f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}",
        f"- Required expansions: {analysis['required_expansion_completion']['numerator']}/{analysis['required_expansion_completion']['denominator']}",
        f"- Reconsiderations: {analysis['reconsideration_completion']['numerator']}/{analysis['reconsideration_completion']['denominator']}",
        "", "Outcomes", "",
        f"- Detection: {aggregate['fault_detection']['numerator']}/{aggregate['fault_detection']['denominator']}",
        f"- Correct Job 1: {aggregate['correct_job_attribution']['numerator']}/{aggregate['correct_job_attribution']['denominator']}",
        f"- Exact function: {aggregate['exact_function_localisation']['numerator']}/{aggregate['exact_function_localisation']['denominator']}",
        f"- Clean false positives: {aggregate['control_false_positives']['numerator']}/{aggregate['control_false_positives']['denominator']}",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; total {aggregate['total_tokens']}",
        f"- Frozen-rate estimated cost: USD {analysis['estimated_cost_usd']:.6f}",
        "", "Exact artifact hashes", "",
    ]
    lines.extend(f"- `{path.relative_to(repo_root)}`: `{hashes[name]}`" for name, path in artifacts.items())
    lines += ["", "Jobs 1 and 2 and Attempts 032, 033, 038 and 041 were not re-executed or modified. Protected provider, authentication, sandbox, isolation, artifact-execution and shared graph-operation code remained unchanged.", ""]
    path = repo_root / "instructions_between_agent_types/developer/handoffs/N25_attempt_042_results_to_overseer.email.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_bytes(path, "\n".join(lines))
    return path


def reconstruct_counts(reviews: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(reviews)
    return {
        "reviews": len(values),
        "repairs": 0,
        "logical_provider_calls": sum(len(value["call_records"]) for value in values),
        "provider_attempt_call_ids": sum(len(call["call_ids"]) for value in values for call in value["call_records"]),
        "completed_evidence_expansions": sum(value["completed_evidence_expansions"] for value in values),
        "completed_reconsiderations": sum(value["completed_reconsiderations"] for value in values),
    }


def execute_lifecycle(repo_root: Path, attempt_root: Path) -> Path:
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    verified = verify_frozen_attempt(repo_root, attempt_root)
    create_live_consumption(repo_root, attempt_root)
    prepared = prepare_attempt(repo_root, attempt_root)
    packages = {record["controller_condition"]["branch_id"]: record for record in _package_records(attempt_root)}
    trials = _json(attempt_root / "review-design.json")["review_trials"]
    reviews = []
    for trial in trials:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = _json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("invalid N25 partial review record")
        else:
            instance_id = trial["instance_id"]
            package_record = packages[trial["branch_id"]]
            session = run_review_session(
                repo_root, attempt_root, prepared["catalogues"][instance_id],
                prepared["indexes"][instance_id], package_record, trial["trial_id"],
            )
            pre = session["pre_validation"]
            final = session["final_validation"]
            outcome = score_response(prepared["instances"][instance_id], final)
            selected = session["selected_group"]
            truth = prepared["instances"][instance_id]["truth_function"]
            contained = bool(selected and truth and selected["job_id"] == UPSTREAM and truth in selected["func_stack"])
            record = {
                "schema_version": "n25-review-record-1",
                "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "initial_receipt": deepcopy(pre["receipt"]),
                "terminal_receipt": deepcopy(final["receipt"]),
                "pre_fault_detected": pre["fault_detected"],
                "pre_suspect_job": pre["suspect_job"],
                "pre_suspect_function": pre["normalized_suspect_function"],
                "suspect_job": final["suspect_job"],
                "suspect_function": final["normalized_suspect_function"],
                "suspect_function_visible": final["suspect_function_visible"],
                "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]),
                **outcome,
                "operation_events": session["operation_events"],
                "operation_diagnostics": session["operation_diagnostics"],
                "completed_evidence_expansions": session["completed_evidence_expansions"],
                "completed_reconsiderations": session["completed_reconsiderations"],
                "selected_group_contained_truth_function": contained,
                "disclosed_node_count": session["disclosed_node_count"],
                "disclosed_relationship_count": session["disclosed_relationship_count"],
                "call_records": session["call_records"],
                "usage": session["usage"],
                "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews.append(record)
    counts = reconstruct_counts(reviews)
    required = [record for record in reviews if record["controller_trial"]["mode"] == "E08"]
    reconsidered = [record for record in reviews if record["controller_trial"]["mode"] == "E09"]
    if counts != {"reviews": 924, "repairs": 0, "logical_provider_calls": 1092, "provider_attempt_call_ids": counts["provider_attempt_call_ids"], "completed_evidence_expansions": 84, "completed_reconsiderations": 84}:
        raise RuntimeError(f"N25 terminal session counts changed: {counts}")
    if any(record["completed_evidence_expansions"] != 1 for record in required) or any(record["completed_reconsiderations"] != 1 for record in reconsidered):
        raise RuntimeError("N25 mandatory interaction did not complete")
    call_ids = [call_id for record in reviews for call in record["call_records"] for call_id in call["call_ids"]]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("N25 duplicate provider call ID")
    for call_id in call_ids:
        verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = _json(write_analysis(repo_root, attempt_root, reviews))
    freeze = _json(attempt_root / "experiment-freeze.json")
    replay = {
        "schema_version": "n25-replay-1",
        "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(record["review_sha256"] for record in reviews),
        "observed_counts": counts,
        "all_record_hashes_recomputed": True,
        "duplicate_provider_call_ids": False,
        "package_tree_unchanged": ce.sha256(ce._tree_hashes(attempt_root / "packages")) == freeze["package_tree_sha256"],
        "controller_manifest_tree_unchanged": ce.sha256(ce._tree_hashes(attempt_root / "controller-manifests")) == freeze["controller_manifest_tree_sha256"],
        "source_artifacts_unchanged": all(ce.sha256((repo_root / "outputs/fault-experiments-v2-2-n10" / path).read_bytes()) == digest for path, digest in SOURCE_FIXED.items()),
        "provider_receipts_preserved": all(record.get("initial_receipt") and record.get("terminal_receipt") for record in reviews),
        "required_expansions_complete": len(required) == 84 and all(record["completed_evidence_expansions"] == 1 for record in required),
        "reconsiderations_complete": len(reconsidered) == 84 and all(record["completed_reconsiderations"] == 1 for record in reconsidered),
        "repair_count": 0,
    }
    if not all(value for key, value in replay.items() if key.endswith("unchanged") or key.endswith("preserved") or key.endswith("complete")):
        raise RuntimeError("N25 replay reconciliation failed")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(attempt_root / "replay.json", replay)
    terminal = {
        "schema_version": "n25-terminal-1",
        "status": "completed_experiment_and_analysis",
        "fault_count": 6,
        "control_count": 1,
        "job_count": 4,
        "new_job_capture_count": 14,
        "package_count": 308,
        "review_count": 924,
        "mandatory_follow_up_count": 168,
        "repair_trace_count": 0,
        "logical_provider_calls": counts["logical_provider_calls"],
        "analysis_sha256": analysis["analysis_sha256"],
        "replay_sha256": replay["replay_sha256"],
    }
    terminal["terminal_sha256"] = ce.sha256(terminal)
    path = attempt_root / "terminal-state.json"
    ce._write_immutable(path, terminal)
    _write_reports(repo_root, attempt_root)
    _write_handoff(repo_root, attempt_root)
    return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        terminal = {
            "schema_version": "n25-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n25_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
            "completed_review_records": len(list((target / "reviews").glob("*.json"))),
            "completed_repair_records": 0,
        }
        terminal["terminal_sha256"] = ce.sha256(terminal)
        path = target / "terminal" / f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"
        ce._write_immutable(path, terminal)
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--attempt-root", default=ATTEMPT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    attempt = Path(args.attempt_root)
    attempt = attempt if attempt.is_absolute() else repo / attempt
    try:
        if args.operation == "build":
            built = build_attempt(repo, attempt)
            print(json.dumps({"qualification": built["qualification"], "counts": {"packages": len(built["records"]), "reviews": len(built["design"]["review_trials"]), "repairs": 0}}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, attempt))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, attempt), indent=2))
        else:
            path = run_lifecycle(repo, attempt)
            print(path)
            return 0 if _json(path).get("status") == "completed_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N25 experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
