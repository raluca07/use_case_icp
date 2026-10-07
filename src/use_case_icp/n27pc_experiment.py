"""N27PC unambiguous-control connected-lineage pilot (Attempt 047)."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from . import n25_experiment as n25
from . import n27p_experiment as n27p
from . import n27pa_experiment as n27pa
from . import n27pb_experiment as pb
from .fault_preflight_v2 import validate_strict_provider_schema
from .n05_program import _pipeline_payload
from .n05_runner import create_bytes_exclusive, stable_id, verify_record


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-047")
ATTEMPT_046 = Path("outputs/fault-experiments-v2-2-n10/attempt-046")
TASK = Path("instructions_between_agent_types/developer/current/N27PC_unambiguous_controls_connected_lineage_pilot.email.md")
TASK_SHA256 = "sha256:82ef013ac3410b0fca7d73be83bae4594cac83586a8ef8016a422f5f2f80fa0c"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PC_unambiguous_controls_connected_lineage_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:1f8c78797748c053a5b8105dd03e11e27138b8897b2dbb791a9c6ce05852235c"
PROMPT = Path("prompts/v2_2/n27pc_review.md")
FINAL_SCHEMA = Path("schemas/v2_2/n27pc_final.schema.json")
GROUP_SCHEMA = Path("schemas/v2_2/n27pc_choose_group.schema.json")
ARTIFACT_SCHEMA = Path("schemas/v2_2/n27pc_choose_artifact.schema.json")
RECONSIDER_SCHEMA = Path("schemas/v2_2/n27pc_reconsider.schema.json")
COMMON_CONTRACT = Path("qualification/common-reviewer-contract.json")

UPSTREAM_SOURCE = pb.UPSTREAM_SOURCE
DOWNSTREAM_SOURCE = pb.DOWNSTREAM_SOURCE
JOB3_SOURCE = pb.JOB3_SOURCE
JOB4_SOURCE = pb.JOB4_SOURCE
SANDBOX_GATE = pb.SANDBOX_GATE
SANDBOX_GATE_SHA256 = pb.SANDBOX_GATE_SHA256
JOB_ORDER = pb.JOB_ORDER
UPSTREAM, DOWNSTREAM, JOB3, JOB4 = JOB_ORDER
DELIVERY_RULES = pb.DELIVERY_RULES
CAPABILITIES = pb.CAPABILITIES

INSTANCES = (
    "case-copper-cove",
    "case-elm-delta",
    "case-frost-basin",
    "case-garnet-field",
    "case-hazel-point",
)
TRUTH = {
    "case-copper-cove": None,
    "case-elm-delta": "select_demand",
    "case-frost-basin": "normalize",
    "case-garnet-field": None,
    "case-hazel-point": "assemble_provenance",
}
MATCHED_CLEAN = {
    "case-elm-delta": "case-copper-cove",
    "case-frost-basin": "case-copper-cove",
    "case-hazel-point": "case-garnet-field",
}
MUTATIONS = {
    "case-elm-delta": ("threshold_value >= threshold", "threshold_value > threshold"),
    "case-frost-basin": ('-row["aggregate_demand"]', '-row["source_weight"]'),
    "case-hazel-point": ('-float(row["source_weight"])', '-round(float(row["source_weight"]), 1)'),
}
CELLS = tuple(f"P{index:02d}" for index in range(1, 14))
MODE_NAMES = {
    "P01": "current_job4",
    "P02": "current_job4_semantic_declarations",
    "P03": "full_predecessor_history_and_handoffs",
    "P04": "handoffs_only",
    "P05": "compact_native_nodes",
    "P06": "compact_within_job",
    "P07": "compact_end_to_end",
    "P08": "compact_end_to_end_semantic_declarations",
    "P09": "compact_end_to_end_inspect",
    "P10": "adaptive_required_one",
    "P11": "two_pass_reconsideration",
    "P12": "full_end_to_end_inspect",
    "P13": "random_end_to_end_inspect",
}
CALLS_BY_MODE = {
    "P01": 1, "P02": 1, "P03": 1, "P04": 1, "P05": 1,
    "P06": 1, "P07": 1, "P08": 1, "P09": 2, "P10": 3,
    "P11": 3, "P12": 2, "P13": 2,
}
TASK_TEXT = (
    "Starting from the observed Job-4 campaign-activation result, decide whether the four-job "
    "execution contains a behaviorally significant fault. If it does, identify the earliest "
    "responsible job and, when supplied evidence supports it, the exact responsible function."
)
CONTRACT_CRITERIA = [
    "Aggregate observations by canonical record ID and segment using the supplied aggregation rule.",
    "Treat each segment threshold as an inclusive minimum: a value equal to its threshold passes.",
    "Calculate qualifying-source rate over distinct source IDs.",
    "Retain listed fallback records and protect them before filling remaining retained capacity.",
    "Fill remaining capacity among eligible non-fallback records by aggregate demand descending, then source weight descending, then stable record ID.",
    "For duplicate observations retain the representative with highest source weight, then stable source ID.",
    "Rank provenance by aggregate demand descending, then unrounded captured source weight descending, then stable record ID; apply supplied output precision only after ordering.",
    "In Job 2 map needs to capabilities, put unsupported records before supported records, and within that priority preserve upstream provenance rank then stable record ID.",
    "In Job 3 preserve the priority rows, assign the first priority the primary campaign role, map unsupported work to gap education and supported work to capability reinforcement, and preserve the recommendation in the portfolio.",
    "In Job 4 map message strategies with the supplied delivery rules, schedule by priority rank then stable record ID, launch only traceable fully mapped work, and otherwise require evidence review.",
    "Across Jobs 2 through 4 preserve record identity, upstream provenance rank, ordering, and stipulated campaign decisions through every handoff.",
    "For this pipeline downstream traceability means preservation of record ID and upstream provenance rank; later business artifacts need not repeat Job-1 source_id or source_weight fields.",
]
SOURCE_HASHES = deepcopy(pb.SOURCE_HASHES)
ATTEMPT_046_HASHES = {
    "terminal-state.json": "sha256:c6be6634a9faa8c934033aed8ce69f6c7ccb57a5c50d479105f1824a39479110",
    "experiment-freeze.json": "sha256:999b134c29573634df712a1a395434f5a062b210c78b8ecb773f142b32afae4a",
    "replay.json": "sha256:cca597d00cad732189f223dd593e9e5071f1e88386f5dba36128211b118290da",
    "analysis/summary.json": "sha256:f56f2cd2974b79d91a47daacc53ac6c88f0e4b57e67c124a9f4e5f482170ab50",
    "analysis/actual-token-report.json": "sha256:b4be2ab17e0194028a410cce6273e3ad1cfec60d0ab255b1166d2c7d066f55c9",
}


def _configure_reuse() -> None:
    """Point the frozen N27PB primitives at Attempt-047 data without editing them."""
    pb.INSTANCES = INSTANCES
    pb.TRUTH = TRUTH
    pb.MATCHED_CLEAN = MATCHED_CLEAN
    pb.MUTATIONS = MUTATIONS
    pb.PROMPT = PROMPT
    pb.FINAL_SCHEMA = FINAL_SCHEMA
    pb.GROUP_SCHEMA = GROUP_SCHEMA
    pb.ARTIFACT_SCHEMA = ARTIFACT_SCHEMA
    pb.RECONSIDER_SCHEMA = RECONSIDER_SCHEMA
    pb.input_for = input_for


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    create_bytes_exclusive(path, value.encode())


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PC authority changed: {relative}")
    for relative, expected in SOURCE_HASHES.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PC protected source changed: {relative}")
    if ce.sha256((repo_root / "src/use_case_icp/n27pb_experiment.py").read_bytes()) != "sha256:c727ee763ac728a25109509f8d18d0c1df1b97277d329404bd322ef899385180":
        raise ValueError("frozen N27PB controller changed")
    for relative, expected in ATTEMPT_046_HASHES.items():
        if ce.sha256((repo_root / ATTEMPT_046 / relative).read_bytes()) != expected:
            raise ValueError(f"Attempt 046 preservation binding changed: {relative}")
    if ce.sha256((repo_root / SANDBOX_GATE).read_bytes()) != SANDBOX_GATE_SHA256:
        raise ValueError("signed artifact sandbox gate changed")
    protected = {
        "artifact_python_worker_sha256": ce.sha256(pb.operations._ARTIFACT_PYTHON_WORKER.encode()),
        "production_launcher_sha256": pb.operations.production_launcher_sha256(pb.operations.artifact_python_launcher),
        "launch_policy_sha256": pb.operations.ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
    }
    expected = {
        "artifact_python_worker_sha256": "sha256:8e9307c764bb5e9f6511dc96fdc32a5adb3202df6bf0968c0b8522b6c74c98b5",
        "production_launcher_sha256": "sha256:fe8216b7c45091bffecfb1f304c3947548f7a1175fe03ad7c82d506bacc0ba83",
        "launch_policy_sha256": "sha256:ca9a3d0c25ce256c5e2d0ad7e9744d53803bfdc2028043c2839b25b2b8a094c9",
    }
    if protected != expected or (ce.PROVIDER_MODEL, ce.PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise ValueError("protected execution binding changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "sandbox": protected}


def _row(record_id: str, need: str, segment: str, demand: float, weight: float, source: str) -> dict[str, Any]:
    return pb._row(record_id, need, segment, demand, weight, source)


def _selection_input() -> dict[str, Any]:
    fallbacks = (
        ("rec-horizon", "account intelligence", 9.1),
        ("rec-juniper", "regional reporting", 8.9),
        ("rec-lantern", "buyer journey analytics", 8.7),
        ("rec-marigold", "partner attribution", 8.5),
        ("rec-nimbus", "pipeline automation", 8.3),
        ("rec-oak", "territory planning", 8.1),
        ("rec-prairie", "conversion forecasting", 7.8),
    )
    rows = [_row(record, need, "established", demand, 5.4 + index / 10, f"source-{index:02d}") for index, (record, need, demand) in enumerate(fallbacks, 1)]
    rows.extend([
        _row("rec-quartz", "content measurement", "strategic", 7.4, 6.25, "source-21"),
        _row("rec-river", "community nurture", "growth", 7.1, 6.35, "source-22"),
    ])
    return {
        "scenario_id": "connected-capacity-planning",
        "corpus": rows,
        "selection_policy": {
            "segment_thresholds": {"established": 5.0, "strategic": 7.4, "growth": 7.0},
            "default_threshold": 5.0,
            "minimum_qualifying_source_rate": 0.5,
            "fallback_record_ids": [value[0] for value in fallbacks],
            "retained_capacity": 8,
            "aggregation_rule": "sum",
            "duplicate_survivor_rule": "highest_source_weight",
            "score_precision": 2,
            "ranking_tie_break": ["aggregate_demand_desc", "source_weight_desc", "record_id"],
        },
    }


def _provenance_input() -> dict[str, Any]:
    values = (
        ("rec-saffron", "account intelligence", 9.2, 7.3),
        ("rec-thicket", "regional reporting", 8.7, 7.1),
        ("rec-umber", "buyer journey analytics", 8.1, 6.9),
        ("rec-violet", "partner attribution", 7.55, 6.61),
        ("rec-willow", "pipeline automation", 7.55, 6.64),
        ("rec-xenia", "territory planning", 6.9, 6.4),
        ("rec-yarrow", "conversion forecasting", 6.3, 6.2),
        ("rec-zephyr", "content measurement", 5.8, 6.0),
    )
    rows = [_row(record, need, "portfolio", demand, weight, f"evidence-{index:02d}") for index, (record, need, demand, weight) in enumerate(values, 1)]
    return {
        "scenario_id": "connected-precision-planning",
        "corpus": rows,
        "selection_policy": {
            "segment_thresholds": {"portfolio": 5.0},
            "default_threshold": 5.0,
            "minimum_qualifying_source_rate": 0.5,
            "fallback_record_ids": ["rec-violet", "rec-willow"],
            "retained_capacity": 8,
            "aggregation_rule": "sum",
            "duplicate_survivor_rule": "highest_source_weight",
            "score_precision": 2,
            "ranking_tie_break": ["aggregate_demand_desc", "source_weight_desc", "record_id"],
        },
    }


def input_for(instance_id: str) -> dict[str, Any]:
    return deepcopy(_selection_input() if instance_id in INSTANCES[:3] else _provenance_input())


def _mutant_source(clean: str, instance_id: str) -> tuple[str, dict[str, Any] | None]:
    truth = TRUTH[instance_id]
    if truth is None:
        return clean, None
    old, new = MUTATIONS[instance_id]
    if clean.count(old) != 1:
        raise ValueError(f"mutation site is not unique: {instance_id}")
    mutated = clean.replace(old, new, 1)
    old_tree, new_tree = ast.parse(clean), ast.parse(mutated)
    if ast.dump(old_tree) == ast.dump(new_tree):
        raise ValueError("mutation did not alter the AST")
    line = clean.count("\n", 0, clean.index(old)) + 1
    record = {
        "operator": "single_ast_expression_substitution",
        "qualified_function_name": truth,
        "job_id": UPSTREAM,
        "original_snippet": old,
        "mutant_snippet": new,
        "original_span": {"start_line": line, "end_line": line},
        "candidate_count": 1,
        "exactly_one_source_site_changed": True,
        "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return mutated, record


def _direct_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    policy = value["selection_policy"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in value["corpus"]:
        grouped.setdefault((row["record_id"], row["segment"]), []).append(row)
    survivors = []
    for (record_id, segment), rows in sorted(grouped.items()):
        aggregate = round(sum(float(row["demand_score"]) for row in rows), int(policy["score_precision"]))
        sources = {row["source_id"] for row in rows}
        qualifying = {row["source_id"] for row in rows if row["qualified"]}
        fallback = record_id in policy["fallback_record_ids"]
        threshold = float(policy["segment_thresholds"].get(segment, policy["default_threshold"]))
        if (aggregate >= threshold and len(qualifying) / len(sources) >= policy["minimum_qualifying_source_rate"]) or fallback:
            representative = sorted(rows, key=lambda row: (-float(row["source_weight"]), str(row["source_id"])))[0]
            survivors.append({
                "record_id": record_id, "need": representative["need"],
                "demand_score": aggregate, "source_id": representative["source_id"],
                "source_weight": float(representative["source_weight"]), "is_fallback": fallback,
            })
    fallbacks = sorted((row for row in survivors if row["is_fallback"]), key=lambda row: row["record_id"])
    primaries = sorted((row for row in survivors if not row["is_fallback"]), key=lambda row: (-row["demand_score"], -row["source_weight"], row["record_id"]))
    retained = (fallbacks + primaries)[: int(policy["retained_capacity"])]
    needs = [{key: row[key] for key in ("record_id", "need", "demand_score", "source_id", "source_weight")} for row in retained]
    ordered = sorted(needs, key=lambda row: (-row["demand_score"], -row["source_weight"], row["record_id"]))
    evidence = [{"record_id": row["record_id"], "source_id": row["source_id"], "source_weight": row["source_weight"], "rank": rank} for rank, row in enumerate(ordered, 1)]
    return {"needs": needs, "evidence_sources": evidence, "metadata": {"record_count": len(needs), "evidence_source_count": len(evidence), "scenario_id": value.get("scenario_id", "")}}


def _interface_refs(catalogue: Mapping[str, Any], handoff: Mapping[str, Any]) -> dict[str, list[str]]:
    artifact = str(handoff["artifact_name"])
    aliases = {artifact, f"{artifact}_df"}
    if artifact == "campaign_portfolio":
        aliases.add("campaign_items_df")
    refs: dict[str, list[str]] = {}
    for side, job_key in (("producer_interface_refs", "upstream_job_id"), ("consumer_interface_refs", "downstream_job_id")):
        job = catalogue["jobs"][handoff[job_key]]
        native = []
        for node in job["native_graph"]["nodes"]:
            names = {str(name).strip("`") for name in node.get("names", [])}
            if names & aliases:
                native.append(node["native_node_ref"])
        boundaries = []
        field = "expected_outputs" if side.startswith("producer") else "expected_inputs"
        for boundary in job["realized_boundaries"]:
            if artifact in boundary.get(field, []):
                boundaries.append(boundary["boundary_id"])
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
        raise ValueError("exactly eight unique cross-job handoffs are required")
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
    outputs = {key: value["jobs"][JOB4]["output"] for key, value in captures.items()}
    clean_job1 = {instance: captures[instance]["jobs"][UPSTREAM]["output"] for instance in (INSTANCES[0], INSTANCES[3])}
    references = {instance: _direct_reference(input_for(instance)) for instance in clean_job1}
    if clean_job1 != references:
        raise ValueError("independent common-contract calculation does not match both clean Job-1 outputs")
    c1_ids = [row["record_id"] for row in pb._action_rows(outputs[INSTANCES[0]])]
    if len(c1_ids) != 8 or "rec-quartz" not in c1_ids or "rec-river" in c1_ids:
        raise ValueError("C1 control capacity result failed")
    for fault in INSTANCES[1:3]:
        ids = [row["record_id"] for row in pb._action_rows(outputs[fault])]
        if len(ids) != 8 or "rec-river" not in ids or "rec-quartz" in ids:
            raise ValueError(f"matched capacity substitution failed: {fault}")
    if ce.canonical_json(outputs[INSTANCES[1]]) != ce.canonical_json(outputs[INSTANCES[2]]):
        raise ValueError("F1 and F2 do not have identical logical Job-4 output")
    clean_ids = [row["record_id"] for row in pb._action_rows(outputs[INSTANCES[3]])]
    faulty_ids = [row["record_id"] for row in pb._action_rows(outputs[INSTANCES[4]])]
    differing = [index for index, pair in enumerate(zip(clean_ids, faulty_ids)) if pair[0] != pair[1]]
    if set(clean_ids) != set(faulty_ids) or differing != [3, 4] or faulty_ids[3:5] != list(reversed(clean_ids[3:5])):
        raise ValueError("F3 is not exactly one adjacent provenance inversion")
    if clean_ids[3:5] != ["rec-willow", "rec-violet"]:
        raise ValueError("C2 does not order the close pair by unrounded weight")
    deltas = {}
    execution_proofs = {}
    for fault, clean in MATCHED_CLEAN.items():
        mutation = instances[fault]["mutation"]
        nodes = captures[fault]["jobs"][UPSTREAM]["snapshot"]["nodes"]
        executed = [
            node["node_ref"] for node in nodes
            if any(str(frame).split(",", 1)[0] == mutation["qualified_function_name"] for frame in node.get("func_stack", []))
            and int(node.get("line_no") or 0) >= mutation["original_span"]["start_line"]
        ]
        if not executed:
            raise ValueError(f"mutated statement scope did not execute: {fault}")
        fault_rows = pb._action_rows(outputs[fault])
        clean_rows = pb._action_rows(outputs[clean])
        if len(fault_rows) != len(clean_rows) or outputs[fault]["metadata"] != outputs[clean]["metadata"]:
            raise ValueError(f"fault changed final row/metadata counts: {fault}")
        deltas[fault] = {
            "matched_clean_case": clean,
            "clean_job4_sha256": ce.sha256(outputs[clean]),
            "fault_job4_sha256": ce.sha256(outputs[fault]),
            "clean_record_order": [row["record_id"] for row in clean_rows],
            "fault_record_order": [row["record_id"] for row in fault_rows],
            "row_count_equal": len(clean_rows) == len(fault_rows),
            "metadata_counts_equal": outputs[fault]["metadata"] == outputs[clean]["metadata"],
        }
        execution_proofs[fault] = {"mutated_scope_executed": True, "captured_state_refs": executed[:8]}
    for instance in INSTANCES:
        capture = captures[instance]
        rows = pb._action_rows(outputs[instance])
        if not rows or any(value is None for row in rows for value in row.values()):
            raise ValueError(f"implausible final plan: {instance}")
        if any(capture["jobs"][job]["stderr"] for job in JOB_ORDER):
            raise ValueError(f"non-empty execution error log: {instance}")
        for job in JOB_ORDER:
            if not capture["jobs"][job]["output"]:
                raise ValueError(f"empty job output: {instance}/{job}")
    return {
        "schema_version": "n27pc-hard-fault-qualification-1",
        "status": "passed",
        "independent_reference_clean_matches": {instance: True for instance in clean_job1},
        "clean_contract_control_agreement": True,
        "c1_no_higher_demand_eligible_omission": True,
        "c2_close_pair_unrounded_weight_order": True,
        "one_site_executed_mutations": execution_proofs,
        "f1_f2_exact_job4_match": True,
        "f3_adjacent_inversion_positions": differing,
        "controller_only_deltas": deltas,
        "all_schemas_counts_handoffs_and_plausibility_passed": True,
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
        raise ValueError("Attempt 047 prepared record set is partial")
    for instance in INSTANCES:
        values["source_bundles"][instance] = values["source_bundles"][instance]["source_bundle"]
    return values


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_reuse()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PC is authorized only for Attempt 047")
    authority = _verify_authority(repo_root)
    if (target / "captures").exists():
        prepared = _load_prepared(target)
        hard_path = target / "qualification/hard-faults.json"
        capture_path = target / "qualification/native-captures-and-handoffs.json"
        if not hard_path.exists():
            hard = _hard_fault_qualification(prepared["captures"], prepared["instances"])
            hard["qualification_sha256"] = ce.sha256(hard)
            ce._write_immutable(hard_path, hard)
        if not capture_path.exists():
            topology = {instance: n27pa._topology_qualification(prepared["catalogues"][instance], prepared["indexes"][instance]) for instance in INSTANCES}
            handoffs = {instance: _capture_handoff_qualification(prepared["captures"][instance], prepared["catalogues"][instance]) for instance in INSTANCES}
            capture_qualification = {
                "schema_version": "n27pc-native-capture-qualification-1", "status": "passed",
                "instances": 5, "fresh_job_executions": 20, "etiq_version": "2.3.0",
                "required_api": 'create_full_lineage_graph(graph_format="json")',
                "topology": topology, "handoffs": handoffs, "handoff_count_per_instance": 8,
                "all_native_objects_edges_clusters_preserved": True,
                "all_handoffs_exact_hash_and_schema_valid": True,
            }
            capture_qualification["qualification_sha256"] = ce.sha256(capture_qualification)
            ce._write_immutable(capture_path, capture_qualification)
        return prepared | {"authority": authority}
    contract = {
        "schema_version": "n27pc-common-reviewer-contract-1",
        "status": "frozen_before_mutant_construction",
        "review_task": TASK_TEXT,
        "behavioural_criteria": CONTRACT_CRITERIA,
        "fault_specific_terms_absent": True,
        "mutation_records_existing_at_freeze": 0,
    }
    contract["contract_sha256"] = ce.sha256(contract)
    ce._write_immutable(target / COMMON_CONTRACT, contract)
    clean_source = (repo_root / UPSTREAM_SOURCE).read_text()
    prepared = {name: {} for name in ("captures", "catalogues", "instances", "source_bundles", "crosswalks", "indexes", "reviewer_nodes", "disclosures", "omissions")}
    topology = {}
    handoff_records = {}
    for instance in INSTANCES:
        source, mutation = _mutant_source(clean_source, instance)
        capture, source_bundle = pb._capture_instance(repo_root, target, instance, source)
        capture["schema_version"] = "n27pc-four-job-native-capture-1"
        capture["capture_id"] = stable_id("rerun-capture", ["n27pc", instance], 0)
        capture.pop("capture_sha256", None)
        capture["capture_sha256"] = ce.sha256(capture)
        catalogue, crosswalk = n27p._catalogue(capture)
        catalogue["schema_version"] = "n27pc-four-job-native-catalogue-1"
        catalogue["handoffs"] = _connected_handoffs(catalogue)
        catalogue.pop("catalogue_sha256", None)
        catalogue["catalogue_sha256"] = ce.sha256(catalogue)
        compact, index = n27p.build_compact_graph(catalogue, crosswalk)
        topology[instance] = n27pa._topology_qualification(catalogue, index)
        handoff_records[instance] = _capture_handoff_qualification(capture, catalogue)
        reviewer, disclosure, omission = pb._payload_lazy_catalogue(catalogue, instance)
        lazy_compact = pb._lazy_graph(compact, reviewer)
        pb._assert_payload_lazy(lazy_compact, disclosure)
        instance_record = {
            "schema_version": "n27pc-instance-1",
            "opaque_instance_id": instance,
            "designation": "matched_clean_control" if TRUTH[instance] is None else "upstream_fault",
            "truth_job": None if TRUTH[instance] is None else UPSTREAM,
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
        ce._write_immutable(target / "projections" / f"{instance}-compact-within-job.json", lazy_compact)
        for job in JOB_ORDER:
            raw = capture["jobs"][job]["native_lineage"]
            export = target / "native-exports" / instance / job / "etiq-native-lineage.json"
            ce._write_immutable(export, raw)
            record = {
                "schema_version": "n27pc-fresh-native-job-capture-1",
                "instance": instance, "job_id": job,
                "capture_status": "fresh_n27pc_execution",
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
        "schema_version": "n27pc-native-capture-qualification-1", "status": "passed",
        "instances": 5, "fresh_job_executions": 20, "etiq_version": "2.3.0",
        "required_api": 'create_full_lineage_graph(graph_format="json")',
        "topology": topology, "handoffs": handoff_records,
        "handoff_count_per_instance": 8,
        "all_native_objects_edges_clusters_preserved": True,
        "all_handoffs_exact_hash_and_schema_valid": True,
    }
    capture_qualification["qualification_sha256"] = ce.sha256(capture_qualification)
    ce._write_immutable(target / "qualification/native-captures-and-handoffs.json", capture_qualification)
    return prepared | {"authority": authority}


def _graph_layer(compact: Mapping[str, Any], handoffs: list[dict[str, Any]], layer: str) -> dict[str, Any]:
    value = {
        "job_evidence_order": deepcopy(compact["job_evidence_order"]),
        "nodes": [], "relationships": [], "native_clusters": [],
        "collapsed_execution_groups": [], "disclosed_execution_groups": [], "handoffs": [],
    }
    if layer != "handoffs_only":
        value["nodes"] = deepcopy(compact["nodes"])
    if layer in {"within_job", "end_to_end"}:
        for key in ("relationships", "native_clusters", "collapsed_execution_groups"):
            value[key] = deepcopy(compact[key])
    if layer in {"handoffs_only", "end_to_end"}:
        value["handoffs"] = deepcopy(handoffs)
    value["projection_sha256"] = ce.sha256(value)
    return value


def _with_handoffs(graph: Mapping[str, Any], handoffs: list[dict[str, Any]]) -> dict[str, Any]:
    value = deepcopy(dict(graph))
    value["handoffs"] = deepcopy(handoffs)
    value.pop("projection_sha256", None)
    value["projection_sha256"] = ce.sha256(value)
    return value


def _random_end_to_end(catalogue: Mapping[str, Any], compact_full: Mapping[str, Any], compact_lazy: Mapping[str, Any], reviewer: Mapping[str, Any], index: Mapping[str, Any], handoffs: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    selected = pb.random_structural_graph(catalogue, compact_full, compact_lazy, reviewer, index, seed)
    target_structural = {key: compact_lazy[key] for key in ("nodes", "relationships", "native_clusters", "collapsed_execution_groups")}
    observed_structural = {key: selected[key] for key in target_structural}
    target_tokens = n25._token_count(target_structural | {"handoffs": handoffs})
    observed_tokens = n25._token_count(observed_structural | {"handoffs": handoffs})
    difference = abs(observed_tokens - target_tokens) / max(1, target_tokens)
    if difference > 0.05:
        raise ValueError("Random End-to-End exceeds 5% structural-token tolerance")
    selected["handoffs"] = deepcopy(handoffs)
    selected["random_structural_match"].update({
        "seed_commitment": ce.sha256(["n27pc-random", seed]),
        "fixed_handoff_anchor_count": 8,
        "target_tokens_including_handoffs": target_tokens,
        "observed_tokens_including_handoffs": observed_tokens,
        "relative_token_difference": difference,
    })
    selected.pop("projection_sha256", None)
    selected["projection_sha256"] = ce.sha256(selected)
    return selected


def _base_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], contract: Mapping[str, Any]) -> dict[str, Any]:
    package = pb._base_package(catalogue, contract)
    package["schema_version"] = "n27pc-review-package-1"
    package["separate_complete_source_bundle"] = deepcopy(source_bundle)
    return package


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]], graphs: Mapping[str, Mapping[str, Any]], contract: Mapping[str, Any], mode: str) -> dict[str, Any]:
    package = _base_package(catalogue, source_bundle, contract)
    handoffs = deepcopy(catalogue["handoffs"])
    if mode == "P03":
        records = []
        for job in JOB_ORDER[:3]:
            record = pb._execution_record(catalogue, job)
            record["chronology"] = {"position": JOB_ORDER.index(job) + 1, "precedes": f"job_{JOB_ORDER.index(job) + 2}"}
            records.append(record)
        package["history"] = {"prior_task_records": records, "exact_cross_job_handoffs": handoffs}
    graph_key = {
        "P04": "handoffs", "P05": "nodes", "P06": "within",
        "P07": "end_to_end", "P08": "end_to_end", "P09": "end_to_end",
        "P10": "end_to_end", "P11": "end_to_end", "P12": "full", "P13": "random",
    }.get(mode)
    if graph_key:
        evidence = deepcopy(graphs[graph_key])
        if graph_key == "random":
            evidence.pop("random_structural_match", None)
            evidence.pop("projection_sha256", None)
            evidence["projection_sha256"] = ce.sha256(evidence)
        package["graph_review"] = {
            "framing": "Captured native execution structure and explicitly labelled exact-hash handoffs may be used in the assessment.",
            "evidence": evidence,
        }
    if mode in {"P02", "P08"}:
        package["semantic_declaration_bundle"] = pb._semantic_declarations(catalogue)
    if mode in {"P09", "P12", "P13"}:
        package["available_operations"] = ["artifact_inspection"]
        package["interaction_contract"] = {
            "operation": "artifact_inspection", "model_selects_artifact_and_mode": True,
            "required_before_terminal": True, "maximum_completed_inspections": 1,
        }
    elif mode == "P10":
        package["available_operations"] = ["expand_execution_group"]
        package["interaction_contract"] = {
            "operation": "expand_execution_group_then_artifact_inspection",
            "model_selects_group_artifact_and_mode": True,
            "required_before_terminal": True,
            "maximum_completed_expansions": 1,
            "maximum_completed_inspections": 1,
        }
    elif mode == "P11":
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
                "declaration_setting": "B1" if mode in {"P02", "P08"} else "B0",
                "branch_id": f"brn-{ce.sha256(['n27pc', instance, mode])[7:23]}",
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
                    "trial_id": f"trial-{ce.sha256(['n27pc', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if (len(cells), len(reviews), len({row["trial_id"] for row in reviews})) != (65, 130, 130):
        raise AssertionError("N27PC schedule counts changed")
    if sum(CALLS_BY_MODE[row["mode"]] for row in reviews) != 200:
        raise AssertionError("N27PC planned call count changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _package_records(target: Path) -> list[dict[str, Any]]:
    return pb._package_records(target)


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return pb._initial_evidence(package)


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by = {(row["controller_condition"]["opaque_instance_id"], row["controller_condition"]["cell_id"]): row["reviewer_package"] for row in records}
    specs = (
        ("semantic_current", "P01", "P02", {"semantic_declaration_bundle"}),
        ("history_and_handoffs", "P01", "P03", {"history"}),
        ("handoffs_alone", "P01", "P04", {"graph_review"}),
        ("native_nodes", "P01", "P05", {"graph_review"}),
        ("within_job_topology", "P05", "P06", {"graph_review"}),
        ("cross_job_connectivity", "P06", "P07", {"graph_review"}),
        ("semantic_connected", "P07", "P08", {"semantic_declaration_bundle"}),
        ("compact_to_full", "P09", "P12", {"graph_review"}),
        ("selected_to_random", "P09", "P13", {"graph_review"}),
    )
    rows = []
    for instance in INSTANCES:
        for name, left_id, right_id, roots in specs:
            left = _initial_evidence(by[(instance, left_id)])
            right = _initial_evidence(by[(instance, right_id)])
            paths = n25._diff_paths(left, right)
            passed = bool(paths) and all(path.split(".")[1] in roots for path in paths)
            rows.append({"instance": instance, "invariant": name, "left": left_id, "right": right_id, "differing_paths": paths, "passed": passed})
        compact_ids = ("P07", "P09", "P10", "P11")
        graph_hashes = [ce.sha256(by[(instance, cell)]["graph_review"]["evidence"]) for cell in compact_ids]
        rows.append({"instance": instance, "invariant": "identical_compact_initial_graph", "cells": compact_ids, "passed": len(set(graph_hashes)) == 1})
    if not all(row["passed"] for row in rows):
        raise ValueError(f"pairwise isolation failed: {[row for row in rows if not row['passed']][:2]}")
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


def _validate_graph_layers(record: Mapping[str, Any]) -> None:
    mode = record["controller_condition"]["mode"]
    package = record["reviewer_package"]
    if "separate_complete_source_bundle" not in package or len(package["separate_complete_source_bundle"]) != 4:
        raise ValueError("all cells must contain all four complete sources")
    graph = package.get("graph_review", {}).get("evidence")
    if mode in {"P01", "P02", "P03"} and graph is not None:
        raise ValueError("current/history cell unexpectedly contains graph evidence")
    if graph is None:
        return
    expected = {
        "P04": (0, 0, 0, 0, 8),
        "P05": (None, 0, 0, 0, 0),
        "P06": (None, None, None, 12, 0),
        "P07": (None, None, None, 12, 8), "P08": (None, None, None, 12, 8),
        "P09": (None, None, None, 12, 8), "P10": (None, None, None, 12, 8),
        "P11": (None, None, None, 12, 8), "P12": (None, None, None, 0, 8),
        "P13": (None, None, None, 12, 8),
    }[mode]
    observed = (len(graph["nodes"]), len(graph["relationships"]), len(graph["native_clusters"]), len(graph["collapsed_execution_groups"]), len(graph["handoffs"]))
    if any(want is not None and got != want for got, want in zip(observed, expected)):
        raise ValueError(f"graph layer shape changed: {mode}/{observed}")
    if graph["handoffs"]:
        if len({row["handoff_id"] for row in graph["handoffs"]}) != 8 or any(row["provenance_type"] != "controller_recorded_exact_hash_handoff" or row["producer_sha256"] != row["consumer_sha256"] for row in graph["handoffs"]):
            raise ValueError("invalid connected handoff layer")


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(records), len(design["review_trials"])) != (65, 130):
        raise ValueError("package/review counts changed")
    schemas = validate_schemas(repo_root)
    pairwise = _pairwise_checks(records)
    contract = _json(target / COMMON_CONTRACT)
    contract_bytes = ce.canonical_json(contract["behavioural_criteria"])
    maximum = 0
    artifact_maximum = 0
    for record in records:
        package = record["reviewer_package"]
        condition = record["controller_condition"]
        if ce.canonical_json(package["behavioural_criteria"]) != contract_bytes:
            raise ValueError("common contract differs across packages")
        _validate_graph_layers(record)
        maximum = max(maximum, n25._token_count(render_request(package)))
        if "graph_review" in package:
            pb._assert_payload_lazy(package["graph_review"]["evidence"], prepared["disclosures"][condition["opaque_instance_id"]])
        if condition["mode"] in {"P02", "P08"} and len(package["semantic_declaration_bundle"]["semantic_declarations"]) != 12:
            raise ValueError("semantic declaration coverage changed")
    for instance in INSTANCES:
        for artifact in prepared["disclosures"][instance]["artifacts"].values():
            artifact_maximum = max(artifact_maximum, n25._token_count(artifact["operation_node"]["artifact_content"]))
    expected_calls = sum(CALLS_BY_MODE[row["mode"]] for row in design["review_trials"])
    if expected_calls != 200 or max(maximum, artifact_maximum) >= 100_000:
        raise ValueError("call or provider-context qualification failed")
    return {
        "schema_version": "n27pc-no-model-verification-1", "status": "passed", "model_calls": 0,
        "instances": 5, "fresh_job_executions": 20, "packages": 65, "terminal_reviews": 130,
        "required_follow_up_calls": 70, "planned_provider_calls": 200, "repairs": 0,
        "strict_schema_hashes": schemas, "pairwise_checks": len(pairwise),
        "maximum_initial_request_tokens": maximum,
        "maximum_complete_artifact_tokens": artifact_maximum,
        "provider_context_qualification_limit": 100_000,
        "fault_denominator_per_cell": 6, "control_denominator_per_cell": 4,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    _configure_reuse()
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if len(existing) == 65:
        qualification = qualify_packages(repo_root, target, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    # The reused, hash-bound relevance primitive reads this proven projection
    # name. Keep the attempt-specific descriptive filename as well.
    for instance in INSTANCES:
        compatibility = target / "projections" / f"{instance}-compact.json"
        if not compatibility.exists():
            ce._write_immutable(compatibility, _json(target / "projections" / f"{instance}-compact-within-job.json"))
    relevance = pb.adaptive_relevance(prepared, target)
    relevance["schema_version"] = "n27pc-adaptive-relevance-1"
    relevance.pop("qualification_sha256", None)
    relevance["qualification_sha256"] = ce.sha256(relevance)
    ce._write_immutable(target / "qualification/adaptive-fault-relevance.json", relevance)
    graphs = {}
    random_records = {}
    for instance in INSTANCES:
        catalogue = prepared["catalogues"][instance]
        handoffs = catalogue["handoffs"]
        compact_within = _json(target / "projections" / f"{instance}-compact-within-job.json")
        full_path = target / "projections" / f"{instance}-full-end-to-end.json"
        random_path = target / "projections" / f"{instance}-random-end-to-end.json"
        if full_path.exists() and random_path.exists():
            full, random_graph = _json(full_path), _json(random_path)
        else:
            full_compact, _ = n27p.build_compact_graph(catalogue, prepared["crosswalks"][instance])
            full = _with_handoffs(pb._lazy_graph(n27p.full_graph(catalogue), prepared["reviewer_nodes"][instance]), handoffs)
            seed = int(ce.sha256([prepared["captures"][instance]["capture_sha256"], "n27pc-random-structural"])[7:23], 16)
            random_graph = _random_end_to_end(
                catalogue, full_compact, compact_within, prepared["reviewer_nodes"][instance],
                prepared["indexes"][instance], handoffs, seed,
            )
        pb._assert_payload_lazy(full, prepared["disclosures"][instance])
        pb._assert_payload_lazy(random_graph, prepared["disclosures"][instance])
        graphs[instance] = {
            "handoffs": _graph_layer(compact_within, handoffs, "handoffs_only"),
            "nodes": _graph_layer(compact_within, handoffs, "nodes"),
            "within": _graph_layer(compact_within, handoffs, "within_job"),
            "end_to_end": _graph_layer(compact_within, handoffs, "end_to_end"),
            "full": full, "random": random_graph,
        }
        random_records[instance] = deepcopy(random_graph["random_structural_match"])
        for name in ("handoffs", "nodes", "within", "end_to_end"):
            ce._write_immutable(target / "projections" / f"{instance}-{name}.json", graphs[instance][name])
        ce._write_immutable(full_path, full)
        ce._write_immutable(random_path, random_graph)
    random_qualification = {
        "schema_version": "n27pc-random-structural-qualification-1", "status": "passed",
        "instances": random_records, "all_strata_matched": True,
        "replaceable_jaccard_maximum": max(value["replaceable_node_jaccard"] for value in random_records.values()),
        "required_maximum": 0.50, "token_tolerance": 0.05,
        "fixed_handoff_anchors_per_instance": 8, "selection_uses_truth_or_outcome": False,
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
        instance = condition["opaque_instance_id"]
        package = build_package(prepared["catalogues"][instance], prepared["source_bundles"][instance], graphs[instance], contract, condition["mode"])
        record = {
            "schema_version": "n27pc-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance]["catalogue_sha256"],
            "disclosure_catalogue_sha256": prepared["disclosures"][instance]["catalogue_sha256"],
            "omission_manifest_sha256": prepared["omissions"][instance]["manifest_sha256"],
            "common_contract_sha256": contract["contract_sha256"],
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        path = target / "packages" / condition["branch_id"] / "reviewer-package.json"
        ce._write_immutable(path, record)
        manifest = {
            "schema_version": "n27pc-controller-manifest-1",
            "controller_condition": deepcopy(condition),
            "reviewer_package_path": path.relative_to(target).as_posix(),
            "reviewer_package_file_sha256": ce.sha256(path.read_bytes()),
            "package_sha256": record["package_sha256"],
        }
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{condition['branch_id']}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, target, records, prepared, design)
    pairwise = {"schema_version": "n27pc-pairwise-package-differences-1", "rows": _pairwise_checks(records), "all_passed": True}
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {"schema_version": "n27pc-review-design-1", "review_trials": design["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n27pc-repair-design-1", "repair_traces": []})
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27pc_experiment.py"), PROMPT, FINAL_SCHEMA,
        GROUP_SCHEMA, ARTIFACT_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27pc_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 047 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after live reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("focused N27PC tests must pass before freeze")
    freeze = {
        "schema_version": "n27pc-experiment-freeze-1", "attempt": "047",
        "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "source_hashes": deepcopy(SOURCE_HASHES), "attempt_046_hashes": deepcopy(ATTEMPT_046_HASHES),
        "sandbox_gate_file_sha256": ce.sha256((repo_root / SANDBOX_GATE).read_bytes()),
        "sandbox_bindings": deepcopy(built["prepared"]["authority"]["sandbox"]),
        "common_contract_file_sha256": ce.sha256((target / COMMON_CONTRACT).read_bytes()),
        "hard_fault_file_sha256": ce.sha256((target / "qualification/hard-faults.json").read_bytes()),
        "native_capture_handoff_file_sha256": ce.sha256((target / "qualification/native-captures-and-handoffs.json").read_bytes()),
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
        "expected_counts": {"instances": 5, "fresh_job_executions": 20, "packages": 65, "reviews": 130, "follow_up_calls": 70, "provider_calls": 200, "repairs": 0},
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
    return {"status": "verified", "freeze_sha256": digest, "packages": 65, "reviews": 130, "provider_calls": 200, "repairs": 0, "qualification": built["qualification"]}


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("live authority must be consumed before reviews")
    freeze = _json(target / "experiment-freeze.json")
    record = {
        "schema_version": "n27pc-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": freeze["freeze_sha256"], "one_use_live_authority": True,
        "authorized_calls": 200, "repairs": 0,
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
    translated["controller_condition"]["mode"] = {
        "P09": "P09", "P10": "P10", "P11": "P12", "P12": "P13", "P13": "P14",
    }.get(package_record["controller_condition"]["mode"], "P01")
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
            "selected_group_contained_truth_state": bool(review["selected_group_contained_truth_state"]),
            "selected_artifact_was_truth_state": bool(review["selected_artifact_was_truth_state"]),
            "artifact_ref": artifact.get("artifact_ref"), "inspection": artifact.get("inspection"),
            "artifact_bytes_returned": int(artifact.get("artifact_bytes_returned") or 0),
            "provider_calls": len(review["call_records"]),
            **usage, "total_tokens": usage["input_tokens"] + usage["output_tokens"],
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
            l = [float(row[outcome]) for row in rows if row["instance"] == instance and row["cell_id"] == left]
            r = [float(row[outcome]) for row in rows if row["instance"] == instance and row["cell_id"] == right]
            differences.append(sum(l) / len(l) - sum(r) / len(r))
        values.append({"name": name, "left": left, "right": right, "population": "three_fault_instances", "outcome": outcome, "per_instance_differences": differences, "mean_difference": sum(differences) / 3})
    differences = []
    for instance in (INSTANCES[0], INSTANCES[3]):
        l = [float(row["false_positive"]) for row in rows if row["instance"] == instance and row["cell_id"] == left]
        r = [float(row["false_positive"]) for row in rows if row["instance"] == instance and row["cell_id"] == right]
        differences.append(sum(l) / len(l) - sum(r) / len(r))
    values.append({"name": name, "left": left, "right": right, "population": "two_clean_controls", "outcome": "false_positive", "per_instance_differences": differences, "mean_difference": sum(differences) / 2})
    return values


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    aggregate = _summary(rows)
    cells = {cell: _summary([row for row in rows if row["cell_id"] == cell]) for cell in CELLS}
    for cell, value in cells.items():
        if value["fault_detection"]["denominator"] != 6 or value["control_false_positives"]["denominator"] != 4:
            raise RuntimeError(f"fault/control denominator changed: {cell}")
    if aggregate["provider_calls"] and not (aggregate["input_tokens"] and aggregate["output_tokens"] and aggregate["total_tokens"]):
        raise RuntimeError("non-zero provider calls produced zero actual token usage")
    specifications = (
        ("semantic_current", "P02", "P01"), ("semantic_connected", "P08", "P07"),
        ("predecessor_history", "P03", "P01"), ("exact_handoffs_alone", "P04", "P01"),
        ("native_nodes", "P05", "P01"), ("within_job_connectivity_groups", "P06", "P05"),
        ("cross_job_connectivity", "P07", "P06"), ("visible_interface_inspection", "P09", "P07"),
        ("nested_evidence_vs_equal_calls", "P10", "P11"), ("adaptive_vs_direct_inspection", "P10", "P09"),
        ("full_vs_compact", "P12", "P09"), ("random_vs_selected", "P13", "P09"),
    )
    contrasts = [row for name, left, right in specifications for row in _contrast(rows, name, left, right)]
    for row in contrasts:
        if row["name"] == "adaptive_vs_direct_inspection":
            row["planned_call_count_difference_per_review"] = 1
    fault_tables = {instance: _summary([row for row in rows if row["instance"] == instance]) for instance in MATCHED_CLEAN}
    control_tables = {instance: _summary([row for row in rows if row["instance"] == instance]) for instance in (INSTANCES[0], INSTANCES[3])}
    if any(value["fault_detection"]["denominator"] != 26 for value in fault_tables.values()):
        raise RuntimeError("per-fault denominator changed")
    if any(value["control_false_positives"]["denominator"] != 26 for value in control_tables.values()):
        raise RuntimeError("per-control denominator changed")
    analysis = {
        "schema_version": "n27pc-pilot-analysis-1", "exploratory_not_confirmatory": True,
        "full_replication_remains_deferred": True, "aggregate": aggregate,
        "cell_summaries": cells,
        "fault_summaries": fault_tables, "control_summaries": control_tables,
        "fault_cell_summaries": {f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell]) for instance in MATCHED_CLEAN for cell in CELLS},
        "control_cell_summaries": {f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell]) for instance in (INSTANCES[0], INSTANCES[3]) for cell in CELLS},
        "prespecified_descriptive_contrasts": contrasts,
        "operations": {
            "adaptive_sessions": sum(row["mode"] == "P10" for row in rows),
            "visible_inspection_sessions": sum(row["mode"] in {"P09", "P12", "P13"} for row in rows),
            "reconsideration_sessions": sum(row["mode"] == "P11" for row in rows),
            "answer_changes": sum(row["answer_changed"] for row in rows),
            "truth_group_selections": sum(row["selected_group_contained_truth_state"] for row in rows),
            "truth_artifact_selections": sum(row["selected_artifact_was_truth_state"] for row in rows),
            "artifact_bytes_returned": sum(row["artifact_bytes_returned"] for row in rows),
        },
        "actual_usage": {key: aggregate[key] for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")},
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
    token_report = {
        "schema_version": "n27pc-actual-token-report-1", "provider_calls": aggregate["provider_calls"],
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
    report_dir = repo_root / "docs/workshops/ICLR/N27PC-connected-lineage-hard-fault-pilot"
    findings = [
        "# N27PC connected-lineage hard-fault pilot", "",
        "Attempt 047 completed the authorized five-instance exploratory pilot. The full replication remains deferred.", "",
        "## Aggregate outcomes", "",
        f"- Fault detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Actual provider calls: {aggregate['provider_calls']}",
        f"- Actual tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; derived total {aggregate['total_tokens']}", "",
        "## Scope", "",
        "All 20 captures are fresh native Etiq executions. Complete actual source was held constant across all cells; connected graph arms contain all eight labelled exact-hash handoffs. No repairs or full replication were run.", "",
        "## Immutable records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-047/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-047/analysis/summary.json)",
        "- [Token report](../../../../outputs/fault-experiments-v2-2-n10/attempt-047/analysis/actual-token-report.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-047/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-047/terminal-state.json)",
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
    for instance in (INSTANCES[0], INSTANCES[3]):
        for cell in CELLS:
            value = analysis["control_cell_summaries"][f"{instance}/{cell}"]
            control_lines.append(f"| {instance} | {cell} | {_rate(value['control_false_positives'])} |")
    _write_text(report_dir / "control-table.md", "\n".join(control_lines))
    trial_lines = ["# Complete trial table", "", "| Position | Trial | Instance | Cell | Rep | Detected | Suspect job | Suspect function | Calls |", "|---:|---|---|---|---:|---|---|---|---:|"]
    operation_lines = ["# Complete operation table", "", "| Trial | Cell | Group | Artifact | Mode | Bytes | Truth group | Truth artifact | Answer changed | Valid request |", "|---|---|---|---|---|---:|---|---|---|---|"]
    token_lines = ["# Complete token table", "", "| Trial | Cell | Calls | Input | Cached input | Output | Derived total |", "|---|---|---:|---:|---:|---:|---:|"]
    for review in sorted(reviews, key=lambda value: value["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        group, artifact = review.get("selected_group") or {}, review.get("selected_artifact") or {}
        usage = _actual_usage(review["usage"])
        trial_lines.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |")
        operation_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {artifact.get('inspection', '')} | {artifact.get('artifact_bytes_returned', 0)} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} | {review['answer_changed']} | {not review['operation_diagnostics']} |")
        token_lines.append(f"| {trial['trial_id']} | {trial['cell_id']} | {len(review['call_records'])} | {usage['input_tokens']} | {usage['cached_input_tokens']} | {usage['output_tokens']} | {usage['input_tokens'] + usage['output_tokens']} |")
    _write_text(report_dir / "trial-table.md", "\n".join(trial_lines))
    _write_text(report_dir / "operation-table.md", "\n".join(operation_lines))
    _write_text(report_dir / "token-table.md", "\n".join(token_lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PC Attempt 047 pilot results", "",
        "Status: `completed_pilot_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "",
        "- Five instances and 20 fresh native Etiq job captures",
        f"- 65 packages; 130 terminal reviews; {aggregate['provider_calls']} inference-bearing calls; zero repairs", "",
        "Exploratory outcomes", "",
        f"- Detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; derived total {aggregate['total_tokens']}", "",
        "Attempt 046 and all protected provider, Etiq-worker, sandbox and process-isolation surfaces remained unchanged. The full replication was not started.",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PC_attempt_047_results_to_overseer.email.md", "\n".join(lines))


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
                "schema_version": "n27pc-review-record-1", "controller_trial": deepcopy(trial),
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
    counts = reconstruct_counts(reviews)
    if counts["reviews"] != 130 or counts["repairs"] != 0 or counts["logical_provider_calls"] > 200:
        raise RuntimeError(f"terminal review/call counts invalid: {counts}")
    expected_actual = 200 - sum(2 if diagnostic["stage"] == "group" else 1 for review in reviews for diagnostic in review["operation_diagnostics"])
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
        "schema_version": "n27pc-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(review["review_sha256"] for review in reviews),
        "observed_counts": counts, "planned_inference_calls": 200,
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
        "schema_version": "n27pc-terminal-1", "status": "completed_pilot_and_analysis",
        "instance_count": 5, "fresh_job_capture_count": 20, "package_count": 65,
        "review_count": 130, "planned_provider_calls": 200,
        "actual_provider_calls": counts["logical_provider_calls"],
        "rejected_operation_count": counts["rejected_operations"], "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"], "actual_token_report_sha256": _json(target / "analysis/actual-token-report.json")["report_sha256"],
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
            "schema_version": "n27pc-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27pc_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
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
        print(f"N27PC experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


_configure_reuse()


if __name__ == "__main__":
    raise SystemExit(main())
