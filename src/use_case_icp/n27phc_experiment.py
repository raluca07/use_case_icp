"""N27PHC larger mixed-difficulty native-Etiq experiment (Attempt 054)."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import random
from typing import Any, Iterable, Mapping

from . import corrected_experiment as ce
from . import n27phb_experiment as base
from . import n27p_experiment as n27p
from . import n27pb_experiment as pb
from .n27phc_hidden_oracle import compute_clean_result


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-054")
ATTEMPT_053 = Path("outputs/fault-experiments-v2-2-n10/attempt-053")
TASK = Path("instructions_between_agent_types/developer/current/N27PHC_larger_hard_fault_native_etiq_experiment.email.md")
TASK_SHA256 = "sha256:832c27db0930d58a99c86677fd3891815cc946f5cbe3b29f722b6d9313f6fd2e"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PHC_larger_hard_fault_native_etiq_experiment_authorization.json")
AUTHORITY_SHA256 = "sha256:0b49007602fa6c51427dab173e697bacf08936fffd5b730119d225076fc9d10a"

JOB1_SOURCE = Path("src/use_case_icp/n27phc_market_evidence.py")
JOB2_SOURCE = base.JOB2_SOURCE
JOB3_SOURCE = base.JOB3_SOURCE
JOB4_SOURCE = base.JOB4_SOURCE
ORACLE_SOURCE = Path("src/use_case_icp/n27phc_hidden_oracle.py")
PROMPT = base.PROMPT
FINAL_SCHEMA = base.FINAL_SCHEMA
GROUP_SCHEMA = base.GROUP_SCHEMA
ARTIFACT_SCHEMA = base.ARTIFACT_SCHEMA
RECONSIDER_SCHEMA = base.RECONSIDER_SCHEMA
JOB_ORDER = base.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
JOB_SOURCES = {JOB1: JOB1_SOURCE, JOB2: JOB2_SOURCE, JOB3: JOB3_SOURCE, JOB4: JOB4_SOURCE}

CONTROLS = ("case-alder", "case-birch", "case-cedar", "case-dogwood")
H1 = ("case-ember", "case-flint", "case-garnet")
H2 = ("case-hazel", "case-iris", "case-juniper")
H3 = ("case-kestrel", "case-lilac", "case-mica")
H4 = ("case-nickel", "case-onyx", "case-poppy")
INSTANCES = CONTROLS + H1 + H2 + H3 + H4
TRUTH = {
    **{item: None for item in CONTROLS},
    **{item: "aggregate_opportunity_evidence" for item in H1 + H2},
    **{item: "select_snapshot_observations" for item in H3},
    **{item: "weight_source_reliability" for item in H4},
}
FAULT_MECHANISM = {
    **{item: "H1_rounded_eligibility_score" for item in H1},
    **{item: "H2_exclusive_minimum_source_boundary" for item in H2},
    **{item: "H3_exclusive_effective_snapshot_boundary" for item in H3},
    **{item: "H4_pre_aggregate_contribution_rounding" for item in H4},
}
DIFFICULTY = {
    **{item: "hard_data_dependent" for item in H1 + H4},
    **{item: "ordinary_boundary" for item in H2 + H3},
}
MATCHED_CLEAN = {item: CONTROLS[index % len(CONTROLS)] for index, item in enumerate(H1 + H2 + H3 + H4)}
MUTATIONS = {
    **{item: ('decision_score = eligibility_df["full_precision_score"]', 'decision_score = eligibility_df["display_score"]') for item in H1},
    **{item: ('source_qualifies = eligibility_df["source_count"].ge(int(planning_policy["minimum_sources"]))', 'source_qualifies = eligibility_df["source_count"].gt(int(planning_policy["minimum_sources"]))') for item in H2},
    **{item: ('effective_admitted = dated_df["_effective"].le(snapshot)', 'effective_admitted = dated_df["_effective"].lt(snapshot)') for item in H3},
    **{item: ('applied_contribution = raw_contribution', 'applied_contribution = raw_contribution.round(int(planning_policy["display_precision"]))') for item in H4},
}

CELLS = base.CELLS
CONTROLLER_MODE = base.CONTROLLER_MODE
CALLS_BY_CELL = base.CALLS_BY_CELL
SEMANTIC_CELLS = base.SEMANTIC_CELLS
GRAPH_CELLS = base.GRAPH_CELLS
SCHEDULE_SEED = 540916271
TOP_LEVEL_FUNCTIONS = base.TOP_LEVEL_FUNCTIONS

PRESERVED_HASHES = {
    "terminal-state.json": "sha256:b8e5d76e98eb27e4cb8fea46a5822971031ec956d301baa92348b563dd22dafb",
    "experiment-freeze.json": "sha256:5118bde19aa786f6f8c3fc7dc49a2ffacf39aa9d1999efe2898101fb03e629d5",
    "replay.json": "sha256:d86531d84e88b0c09f90bcc733746a2751f55e1049dd4c9e77657cdb1ff9e32f",
}
REUSED_HASHES = {
    "src/use_case_icp/n27phb_experiment.py": "sha256:b70767f31d637b781835f5cdd5aa8760ecc74fe19e636fb2a1a451d1ff60fb6e",
    "src/use_case_icp/n27phb_opportunity_priority.py": "sha256:831f432197695ebc7c5ba8c9b1d110ff9d4bf313c8be53a6f993cd5d7e21d33e",
    "src/use_case_icp/n27phb_campaign_allocation.py": "sha256:60106149c2f54847e90af26e9ab054d1a12407f0906e36990d5e5a4d07ce1085",
    "src/use_case_icp/n27phb_activation_schedule.py": "sha256:97aefa58a6a4ecf3afe7e7462e04e77f662d80e8c70413464cb4c636e7ebd345",
    "prompts/v2_2/n27phb_review.md": "sha256:21c4e57fa69676d4a20ff943f65d819786bcabc92a3d055faf15dd66da46b229",
    "schemas/v2_2/n27phb_choose_artifact.schema.json": "sha256:337f61a0461c1c0e6503b5476bd33d311d01e2040f0a0478f2177dc6a79bb5ca",
    "schemas/v2_2/n27phb_choose_group.schema.json": "sha256:91355d0f492ffe272e70396efdaf4948d9d8ddd354db7df3c15a8f7575b229a2",
    "schemas/v2_2/n27phb_final.schema.json": "sha256:f94c7658f69212994de5e1276d26e1871a689c16b5d509fc0fde72b0a6a19351",
    "schemas/v2_2/n27phb_reconsider.schema.json": "sha256:7e482027a5c34b770c55c38f5d94b2d3c728ee05d502c10256a5d7addb57766e",
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
}


def _install_base_bindings() -> None:
    bindings = {
        "ATTEMPT": ATTEMPT, "TASK": TASK, "TASK_SHA256": TASK_SHA256,
        "AUTHORITY": AUTHORITY, "AUTHORITY_SHA256": AUTHORITY_SHA256,
        "JOB1_SOURCE": JOB1_SOURCE, "JOB2_SOURCE": JOB2_SOURCE, "JOB3_SOURCE": JOB3_SOURCE,
        "JOB4_SOURCE": JOB4_SOURCE, "ORACLE_SOURCE": ORACLE_SOURCE, "JOB_SOURCES": JOB_SOURCES,
        "INSTANCES": INSTANCES, "TRUTH": TRUTH, "MATCHED_CLEAN": MATCHED_CLEAN,
        "MUTATIONS": MUTATIONS, "FAULT_MECHANISM": FAULT_MECHANISM, "SCHEDULE_SEED": SCHEDULE_SEED,
    }
    for name, value in bindings.items():
        setattr(base, name, value)
    base.input_for = input_for
    base._mutant_source = _mutant_source
    base._oracle_jobs = _oracle_jobs
    base.compute_clean_result = compute_clean_result
    n27p.FUNCTIONS = TOP_LEVEL_FUNCTIONS
    pb.FUNCTIONS = TOP_LEVEL_FUNCTIONS


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if base._file_sha(repo_root / relative) != expected:
            raise ValueError(f"N27PHC authority changed: {relative}")
    for relative, expected in PRESERVED_HASHES.items():
        if base._file_sha(repo_root / ATTEMPT_053 / relative) != expected:
            raise ValueError(f"Attempt 053 preservation binding changed: {relative}")
    for relative, expected in REUSED_HASHES.items():
        if base._file_sha(repo_root / relative) != expected:
            raise ValueError(f"reused or protected binding changed: {relative}")
    if (ce.PROVIDER_MODEL, ce.PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise ValueError("provider configuration changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "reused_hashes": deepcopy(REUSED_HASHES)}


def _edge_observation(prefix: str, suffix: str, opportunity: str, source: str, segment: str,
                      campaign: str, channel: str, effective: str, value: float, revenue: int) -> dict[str, Any]:
    return base._observation(prefix, suffix, opportunity, source, segment, campaign, channel,
                             effective, "2026-09-14T09:00:00", value, revenue)


def input_for(instance: str) -> dict[str, Any]:
    if instance not in INSTANCES:
        raise KeyError(instance)
    index = INSTANCES.index(instance)
    prefix = ("alder", "birch", "cedar", "dogwood", "ember", "flint", "garnet", "hazel",
              "iris", "juniper", "kestrel", "lilac", "mica", "nickel", "onyx", "poppy")[index]
    variant = ("a", "b", "c")[index % 3]
    root = base._fixture(prefix, variant, stressed=index % 2 == 1)
    policy = root["planning_policy"]
    policy.update({
        "effective_snapshot_boundary": "inclusive",
        "minimum_source_boundary": "inclusive",
        "eligibility_score_basis": "full_precision",
        "contribution_aggregation_basis": "full_precision",
    })
    delta = index * 0.0007
    additions = [
        _edge_observation(prefix, "stable-third", "opportunity-stable", "source-stable-third", "north", "campaign-alpha", "email", "2026-08-25", 0.181 + delta, 184000 + 1000 * index),
        _edge_observation(prefix, "temporal-third", "opportunity-temporal", "source-temporal-third", "south", "campaign-beta", "social", "2026-08-26", 0.205 + delta, 158000 + 900 * index),
        _edge_observation(prefix, "boundary-exact", "opportunity-boundary", "source-boundary-exact", "south", "campaign-beta", "social", policy["as_of_date"], 0.401 + delta, 88000 + 700 * index),
        _edge_observation(prefix, "boundary-earlier", "opportunity-boundary", "source-boundary-earlier", "south", "campaign-beta", "social", "2026-09-11", 0.397 + delta, 88000 + 700 * index),
    ]
    root["market_observations"].extend(additions)
    root["source_reliability"].extend([
        {"source_id": f"{prefix}-source-stable-third", "segment": "north", "reliability": 0.83},
        {"source_id": f"{prefix}-source-temporal-third", "segment": "south", "reliability": 0.88},
        {"source_id": f"{prefix}-source-boundary-exact", "segment": "south", "reliability": 0.82},
        {"source_id": f"{prefix}-source-boundary-earlier", "segment": "south", "reliability": 0.79},
    ])
    root["commercial_context"].append({
        "opportunity_id": f"{prefix}-opportunity-boundary", "margin_rate": 0.21 + 0.001 * index,
    })
    return deepcopy(root)


def _mutant_source(clean: str, instance: str) -> tuple[str, dict[str, Any] | None]:
    if TRUTH[instance] is None:
        return clean, None
    old, new = MUTATIONS[instance]
    if clean.count(old) != 1:
        raise ValueError(f"mutation site is not unique: {instance}")
    mutated = clean.replace(old, new, 1)
    before, after = ast.parse(clean), ast.parse(mutated)
    if ast.dump(before) == ast.dump(after):
        raise ValueError("mutation did not change the AST")
    record = {
        "operator": "single_executed_ast_site_substitution", "job_id": JOB1,
        "qualified_function_name": TRUTH[instance], "original_snippet": old,
        "mutant_snippet": new, "candidate_count": 1,
        "original_span": {"start_line": clean.count("\n", 0, clean.index(old)) + 1},
        "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return mutated, record


def _oracle_jobs(root: Mapping[str, Any]) -> dict[str, Any]:
    result = compute_clean_result(root)
    return {job: result[f"job_{index}"] for index, job in enumerate(JOB_ORDER, 1)}


def _run_pipeline_sources(repo_root: Path, root: Mapping[str, Any], job1_source: str | None = None) -> dict[str, Any]:
    _install_base_bindings()
    return base._run_pipeline_sources(repo_root, root, job1_source)


def _deterministic_private_qualification(repo_root: Path, target: Path) -> dict[str, Any]:
    path = target / "qualification-private/qualification-summary.json"
    if path.exists():
        record = base._json(path)
        ce._verified_self_hash(record, "qualification_sha256")
        return record
    clean_source = (repo_root / JOB1_SOURCE).read_text()
    controls: dict[str, str] = {}
    for instance in CONTROLS:
        root = input_for(instance)
        oracle = compute_clean_result(root)
        actual = _run_pipeline_sources(repo_root, root)["outputs"]
        if ce.canonical_json(actual) != ce.canonical_json(_oracle_jobs(root)):
            raise ValueError(f"control and independent oracle differ: {instance}")
        decisions = {row["opportunity_id"]: row for row in oracle["decisions"]}
        prefix = root["scenario_label"].removesuffix("-planning")
        boundary = decisions[f"{prefix}-opportunity-boundary"]
        threshold = decisions[f"{prefix}-opportunity-threshold"]
        if not boundary["eligible"] or boundary["source_count"] != root["planning_policy"]["minimum_sources"]:
            raise ValueError("control lacks valid minimum-source and snapshot-boundary edge")
        if threshold["display_score"] == threshold["full_precision_score"]:
            raise ValueError("control lacks rounded-score edge")
        weighted = oracle["job_1"]["evidence_attribution"]
        if not any(round(row["weighted_contribution"], 2) != row["weighted_contribution"] for row in weighted):
            raise ValueError("control lacks contribution-rounding edge")
        reversed_root = deepcopy(root)
        reversed_root["market_observations"] = list(reversed(reversed_root["market_observations"]))
        if ce.canonical_json(compute_clean_result(reversed_root)["job_4"]) != ce.canonical_json(oracle["job_4"]):
            raise ValueError("permutation invariance failed")
        irrelevant = deepcopy(root)
        irrelevant["market_observations"].append(base._observation(
            prefix, "irrelevant-expired", "irrelevant", "irrelevant", "north", "irrelevant",
            "email", "2025-01-01", "2025-01-02T00:00:00", 0.123, 12345, valid="2025-02-01",
        ))
        if ce.canonical_json(compute_clean_result(irrelevant)["job_4"]) != ce.canonical_json(oracle["job_4"]):
            raise ValueError("irrelevant-row invariance failed")
        private = {
            "schema_version": "n27phc-private-clean-control-1", "instance": instance,
            "oracle_output": oracle, "executed_outputs": actual, "all_four_edge_patterns": True,
            "permutation_invariant": True, "irrelevant_row_invariant": True,
        }
        private["record_sha256"] = ce.sha256(private)
        ce._write_immutable(target / "qualification-private/controls" / f"{instance}.json", private)
        controls[instance] = private["record_sha256"]
    faults: dict[str, str] = {}
    numerical_signatures: set[bytes] = set()
    for instance in INSTANCES[len(CONTROLS):]:
        root = input_for(instance)
        clean = _oracle_jobs(root)
        mutated, mutation = _mutant_source(clean_source, instance)
        actual = _run_pipeline_sources(repo_root, root, mutated)["outputs"]
        clean_job4, fault_job4 = clean[JOB4], actual[JOB4]
        clean_actions = clean_job4["activation_plan"]["activation_actions"]
        fault_actions = fault_job4["activation_plan"]["activation_actions"]
        if len(clean_actions) != len(fault_actions) or len(fault_actions) != 4:
            raise ValueError(f"fault changes Job-4 action count: {instance}")
        if ce.canonical_json(clean_job4) == ce.canonical_json(fault_job4):
            raise ValueError(f"fault has no downstream effect: {instance}")
        numeric = ce.canonical_json({
            "aggregate": fault_job4["activation_plan"]["aggregate_forecast"],
            "windows": fault_job4["activation_plan"]["window_forecast"],
        })
        if numeric in numerical_signatures:
            raise ValueError(f"fault numerical signature is not distinct: {instance}")
        numerical_signatures.add(numeric)
        clean_total = float(clean_job4["activation_plan"]["aggregate_forecast"]["scheduled_budget"])
        fault_total = float(fault_job4["activation_plan"]["aggregate_forecast"]["scheduled_budget"])
        if abs(clean_total - fault_total) <= 0 or abs(clean_total - fault_total) > 500:
            raise ValueError(f"Job-4 numerical change is not small and nonzero: {instance}")
        private = {
            "schema_version": "n27phc-private-fault-1", "instance": instance,
            "fault_mechanism": FAULT_MECHANISM[instance], "difficulty_tier": DIFFICULTY[instance],
            "truth_function": TRUTH[instance], "mutation": mutation,
            "matched_clean_instance": MATCHED_CLEAN[instance], "clean_outputs": clean,
            "fault_outputs": actual, "clean_job4_sha256": ce.sha256(clean_job4),
            "fault_job4_sha256": ce.sha256(fault_job4), "action_count_preserved": True,
            "schema_preserved": True, "small_nonzero_numerical_change": True,
        }
        private["record_sha256"] = ce.sha256(private)
        ce._write_immutable(target / "qualification-private/faults" / f"{instance}.json", private)
        faults[instance] = private["record_sha256"]
    summary = {
        "schema_version": "n27phc-private-deterministic-qualification-1", "status": "passed",
        "model_calls": 0, "controls": controls, "faults": faults,
        "oracle_source_sha256": base._file_sha(repo_root / ORACLE_SOURCE),
        "job_source_sha256": {path.as_posix(): base._file_sha(repo_root / path) for path in JOB_SOURCES.values()},
        "control_oracle_equality": True, "controls_with_all_four_edge_patterns": 4,
        "metamorphic_checks": 8, "one_site_faults": 12,
        "distinct_job4_numerical_signatures": 12, "job4_action_count_preserved": True,
    }
    summary["qualification_sha256"] = ce.sha256(summary)
    ce._write_immutable(path, summary)
    return summary


def _load_prepared(target: Path) -> dict[str, Any]:
    _install_base_bindings()
    return base._load_prepared(target)


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PHC is authorized only for Attempt 054")
    authority = _verify_authority(repo_root)
    _install_base_bindings()
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
        capture, source_bundle = base._capture_instance(repo_root, target, instance, source)
        capture["schema_version"] = "n27phc-four-job-native-capture-1"
        capture["capture_id"] = base.stable_id("rerun-capture", ["n27phc", instance], 0)
        capture.pop("capture_sha256", None)
        capture["capture_sha256"] = ce.sha256(capture)
        catalogue, crosswalk = n27p._catalogue(capture)
        catalogue["schema_version"] = "n27phc-four-job-native-catalogue-1"
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
            "schema_version": "n27phc-private-instance-1", "opaque_instance_id": instance,
            "designation": "matched_clean_control" if instance in CONTROLS else "upstream_fault",
            "truth_job": None if instance in CONTROLS else JOB1, "truth_function": TRUTH[instance],
            "fault_mechanism": FAULT_MECHANISM.get(instance), "difficulty_tier": DIFFICULTY.get(instance),
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
                "schema_version": "n27phc-fresh-native-job-capture-1", "instance": instance,
                "job_id": job, "capture_status": "fresh_n27phc_execution",
                "native_export_file_sha256": base._file_sha(export),
                "native_export_logical_sha256": ce.sha256(raw),
                "job_capture_sha256": ce.sha256(capture["jobs"][job]),
            }
            job_record["record_sha256"] = ce.sha256(job_record)
            ce._write_immutable(target / "job-captures" / instance / f"{job}.json", job_record)
    qualification = {
        "schema_version": "n27phc-native-capture-qualification-1", "status": "passed",
        "instances": 16, "fresh_job_executions": 64, "etiq_version": "2.3.0",
        "required_api": 'create_full_lineage_graph(graph_format="json")', "topology": topology,
        "exact_handoffs_per_capture": 8, "all_native_objects_edges_preserved": True,
    }
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/native-captures.json", qualification)
    return prepared | {"authority": authority}


def adaptive_relevance(prepared: Mapping[str, Any], target: Path) -> dict[str, Any]:
    _install_base_bindings()
    prepared_with_root = dict(prepared) | {"attempt_root": target}
    state_by_mechanism = {
        "H1_rounded_eligibility_score": "eligibility_decision_df",
        "H2_exclusive_minimum_source_boundary": "eligibility_decision_df",
        "H3_exclusive_effective_snapshot_boundary": "snapshot_decision_df",
        "H4_pre_aggregate_contribution_rounding": "contribution_precision_df",
    }
    faults = {}
    for instance in INSTANCES[len(CONTROLS):]:
        state_name = state_by_mechanism[FAULT_MECHANISM[instance]]
        binding = base._artifact_for_state(prepared_with_root, instance, JOB1, state_name)
        compact = base._json(target / "projections" / f"{instance}-compact.json")
        _, event = pb.expand_native_subtree(
            prepared["catalogues"][instance], prepared["reviewer_nodes"][instance],
            prepared["indexes"][instance], {"graph_review": {"evidence": compact}},
            binding["execution_group_id"],
        )
        if binding["artifact_ref"] not in event["newly_disclosed_artifact_refs"]:
            raise ValueError(f"decisive state is not reachable: {instance}")
        faults[instance] = {
            "truth_function": TRUTH[instance], "fault_mechanism": FAULT_MECHANISM[instance],
            "difficulty_tier": DIFFICULTY[instance], "decisive_state_name": state_name,
            **binding, "initially_hidden": True, "one_expansion_reachable": True,
            "one_inspection_reachable": True,
        }
    record = {
        "schema_version": "n27phc-adaptive-relevance-1", "status": "passed",
        "faults": faults, "row_level_runtime_witnesses": len(faults),
        "function_name_matching_alone_used": False,
    }
    record["qualification_sha256"] = ce.sha256(record)
    return record


def _job_executions(catalogue: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = []
    for position, job in enumerate(JOB_ORDER, 1):
        captured = catalogue["jobs"][job]
        record = {
            "job": f"job_{position}", "input": deepcopy(captured["input"]),
            "parsed_output": deepcopy(captured["output"]),
        }
        if job == JOB4:
            record.update({"stdout": str(captured["stdout"]), "stderr": str(captured["stderr"])})
        records.append(record)
    return records


def build_package(catalogue: Mapping[str, Any], source_bundle: list[dict[str, Any]],
                  compact: Mapping[str, Any], cell: str) -> dict[str, Any]:
    package = {
        "schema_version": "n27phc-review-package-1",
        "review_task": "Assess whether the observed execution is consistent with the stated marketing task. The execution may be correct or faulty. Report a behaviorally significant processing error and its earliest responsible job and function only when supported; otherwise report no fault.",
        "marketing_objective": "Qualify current market evidence, prioritize commercial opportunities, allocate campaign budgets, and schedule capacity-constrained activations.",
        "pipeline_topology": [
            {"job": f"job_{position}", "name": name, "position": position, "observation_point": position == 4}
            for position, name in enumerate(("market evidence", "opportunity priority", "campaign allocation", "activation scheduling"), 1)
        ],
        "complete_actual_source_bundle": deepcopy(source_bundle),
        "observed_job_executions": _job_executions(catalogue),
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
        package["semantic_declaration_bundle"] = base._semantic_declarations(catalogue)
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
    cells = [{
        "opaque_instance_id": instance, "cell_id": cell, "mode": CONTROLLER_MODE[cell],
        "declaration_setting": "B1" if cell in SEMANTIC_CELLS else "B0",
        "branch_id": f"brn-{ce.sha256(['n27phc', instance, cell])[7:23]}",
    } for instance in INSTANCES for cell in CELLS]
    trials = [{
        **condition, "repetition": repetition,
        "trial_id": f"trial-{ce.sha256(['n27phc', condition['branch_id'], repetition])[7:23]}",
    } for condition in cells for repetition in (1, 2, 3)]
    random.Random(SCHEDULE_SEED).shuffle(trials)
    for position, trial in enumerate(trials, 1):
        trial["schedule_position"] = position
    positions = {
        instance: [row["schedule_position"] for row in trials if row["opaque_instance_id"] == instance]
        for instance in INSTANCES
    }
    if (len(cells), len(trials), sum(CALLS_BY_CELL[row["cell_id"]] for row in trials)) != (96, 288, 576):
        raise AssertionError("N27PHC schedule counts changed")
    if all(row["opaque_instance_id"] in CONTROLS for row in trials[:12]) or any(max(value) - min(value) <= 31 for value in positions.values()):
        raise AssertionError("N27PHC schedule is not globally dispersed")
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
        manifest = base._json(path)
        package_path = target / manifest["reviewer_package_path"]
        if base._file_sha(package_path) != manifest["reviewer_package_file_sha256"]:
            raise ValueError("reviewer package file binding changed")
        record = base._json(package_path)
        ce._verified_self_hash(record, "package_sha256")
        records.append(record)
    order = {row["branch_id"]: position for position, row in enumerate(schedule()["cells"])}
    return sorted(records, key=lambda row: order[row["controller_condition"]["branch_id"]])


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    visible = ce.canonical_json(request).decode()
    forbidden = (
        "qualification-private", "oracle_output", "clean_outputs", "fault_outputs",
        "matched_clean_case", "truth_job", "truth_function", "mutant_snippet",
        "original_snippet", "mutation_sha256", "opaque_instance_id", "cell_id",
        "branch_id", "trial_id", "designation", "fault_mechanism", "difficulty_tier",
    )
    if any(token in visible for token in forbidden) or any(instance in visible for instance in INSTANCES):
        raise ValueError("rendered request leaks controller-only state")
    return request


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by = {(row["controller_condition"]["opaque_instance_id"], row["controller_condition"]["cell_id"]): row["reviewer_package"] for row in records}
    common_keys = {
        "schema_version", "review_task", "marketing_objective", "pipeline_topology",
        "complete_actual_source_bundle", "observed_job_executions", "final_response_contract",
    }
    checks = []
    for instance in INSTANCES:
        packages = {cell: by[(instance, cell)] for cell in CELLS}
        common_hashes = {cell: ce.sha256({key: package[key] for key in common_keys}) for cell, package in packages.items()}
        checks.extend([
            {"instance": instance, "invariant": "identical_source_and_all_job_io", "passed": len(set(common_hashes.values())) == 1},
            {"instance": instance, "invariant": "identical_starting_graph_bytes", "passed": len({ce.sha256(packages[cell]["graph_review"]["evidence"]) for cell in GRAPH_CELLS}) == 1},
            {"instance": instance, "invariant": "p02_minus_p01_is_graph_envelope", "passed": set(packages["P02"]) - set(packages["P01"]) == {"graph_review"} and set(packages["P01"]) == common_keys},
            {"instance": instance, "invariant": "p01_no_graph_or_semantics", "passed": "graph_review" not in packages["P01"] and "semantic_declaration_bundle" not in packages["P01"]},
            {"instance": instance, "invariant": "semantic_cells_only", "passed": all(("semantic_declaration_bundle" in packages[cell]) == (cell in SEMANTIC_CELLS) for cell in CELLS)},
            {"instance": instance, "invariant": "adaptive_mechanics_matched", "passed": packages["P04"]["interaction_contract"] == packages["P05"]["interaction_contract"]},
        ])
        for cell, package in packages.items():
            jobs = package["observed_job_executions"]
            checks.append({
                "instance": instance, "cell": cell, "invariant": "upstream_logs_excluded_job4_logs_included",
                "passed": len(jobs) == 4 and all("stdout" not in row and "stderr" not in row for row in jobs[:3]) and all(key in jobs[3] for key in ("stdout", "stderr")),
            })
    if not all(row["passed"] for row in checks):
        raise ValueError(f"pairwise treatment isolation failed: {[row for row in checks if not row['passed']]}")
    return checks


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]],
                     prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if len(records) != 96 or len(design["review_trials"]) != 288:
        raise ValueError("N27PHC package/review count changed")
    if sum(CALLS_BY_CELL[row["cell_id"]] for row in design["review_trials"]) != 576:
        raise ValueError("N27PHC planned call count changed")
    schemas = base.validate_schemas(repo_root)
    pairwise = _pairwise_checks(records)
    common = {
        "schema_version", "review_task", "marketing_objective", "pipeline_topology",
        "complete_actual_source_bundle", "observed_job_executions", "final_response_contract",
    }
    allowed = {
        "P01": common,
        "P02": common | {"graph_review"},
        "P03": common | {"graph_review", "semantic_declaration_bundle"},
        "P04": common | {"graph_review", "available_operations", "interaction_contract"},
        "P05": common | {"graph_review", "semantic_declaration_bundle", "available_operations", "interaction_contract"},
        "P06": common | {"graph_review", "available_operations", "interaction_contract"},
    }
    rows = []
    maximum_request = 0
    maximum_artifact = 0
    expected_paths = [f"generated/protocol_2_2/{JOB_SOURCES[job].name}" for job in JOB_ORDER]
    for record in records:
        condition, package = record["controller_condition"], record["reviewer_package"]
        cell, instance = condition["cell_id"], condition["opaque_instance_id"]
        if set(package) != allowed[cell]:
            raise ValueError(f"positive package allowlist failed: {cell}/{set(package)}")
        source_paths = [file["path"] for job in package["complete_actual_source_bundle"] for file in job["files"]]
        if source_paths != expected_paths or any("oracle" in path or "experiment" in path for path in source_paths):
            raise ValueError("source bundle contains a non-executed file")
        jobs = package["observed_job_executions"]
        if len(jobs) != 4 or any(set(row) != {"job", "input", "parsed_output"} for row in jobs[:3]):
            raise ValueError("Jobs 1-3 top-level records include forbidden logs or fields")
        if set(jobs[3]) != {"job", "input", "parsed_output", "stdout", "stderr"}:
            raise ValueError("Job 4 top-level record is incomplete")
        request = render_request(package)
        maximum_request = max(maximum_request, base.n25._token_count(request))
        if "graph_review" in package:
            pb._assert_payload_lazy(package["graph_review"]["evidence"], prepared["disclosures"][instance])
        if "semantic_declaration_bundle" in package:
            declaration = ce.canonical_json(package["semantic_declaration_bundle"]).decode().lower()
            forbidden_semantics = ("greater_than", "less_than", "eligibility_threshold", "minimum_sources", "expected result", "affected")
            if any(token in declaration for token in forbidden_semantics):
                raise ValueError("B1 semantic declaration contains policy detail")
        rows.append({
            "branch_id": condition["branch_id"], "cell": cell,
            "allowed_package_keys": sorted(allowed[cell]), "allowed_source_files": source_paths,
            "all_four_top_level_io_records": True, "rendered_request_sha256": ce.sha256(request),
            "passed": True,
        })
    for instance in INSTANCES:
        for artifact in prepared["disclosures"][instance]["artifacts"].values():
            maximum_artifact = max(maximum_artifact, base.n25._token_count(artifact["operation_node"]["artifact_content"]))
    if max(maximum_request, maximum_artifact) >= 100_000:
        raise ValueError("request or complete artifact exceeds provider context qualification")
    for path in (JOB1_SOURCE, ORACLE_SOURCE):
        imports = [
            alias.name for node in ast.walk(ast.parse((repo_root / path).read_text()))
            if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
        ]
        if any(name.startswith(("n25", "n26", "n27")) for name in imports):
            raise ValueError(f"fresh source imports historical job code: {path}")
    audit = {
        "schema_version": "n27phc-positive-package-allowlist-audit-1", "status": "passed",
        "rows": rows, "private_root_allowed": False, "executed_source_files_only": True,
        "source_and_all_job_io_identical_across_cells": True,
    }
    audit["audit_sha256"] = ce.sha256(audit)
    ce._write_immutable(target / "qualification/package-allowlist-and-leakage.json", audit)
    return {
        "schema_version": "n27phc-no-model-verification-1", "status": "passed", "model_calls": 0,
        "instances": 16, "fresh_job_executions": 64, "packages": 96,
        "terminal_reviews": 288, "planned_provider_calls": 576, "repairs": 0,
        "strict_schema_hashes": schemas, "pairwise_checks": len(pairwise),
        "maximum_initial_request_tokens": maximum_request,
        "maximum_complete_artifact_tokens": maximum_artifact,
        "fault_denominator_per_cell": 36, "control_denominator_per_cell": 12,
        "package_allowlist_audit_sha256": audit["audit_sha256"],
        "private_qualification_tree_sha256": ce.sha256(ce._tree_hashes(target / "qualification-private")),
        "attempt_053_preservation_verified": True,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if len(existing) == 96:
        qualification = qualify_packages(repo_root, target, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    relevance = adaptive_relevance(prepared, target)
    ce._write_immutable(target / "qualification-private/adaptive-relevance.json", relevance)
    lineage = {
        "schema_version": "n27phc-lineage-1", "attempt": "054", "attempt_053_preserved": True,
        "scientific_reuse_from_attempt_053": False,
        "mechanics_reused_from_attempt_053": ["provider", "ledger", "native_capture", "nesting", "disclosure", "artifact_operations", "resume", "replay", "analysis"],
        "fresh_job_source": JOB1_SOURCE.as_posix(), "reused_job_sources": [JOB2_SOURCE.as_posix(), JOB3_SOURCE.as_posix(), JOB4_SOURCE.as_posix()],
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
            base._json(target / "projections" / f"{instance}-compact.json"), condition["cell_id"],
        )
        record = {
            "schema_version": "n27phc-frozen-package-1", "controller_condition": deepcopy(condition),
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
            "schema_version": "n27phc-controller-manifest-1", "controller_condition": deepcopy(condition),
            "reviewer_package_path": path.relative_to(target).as_posix(),
            "reviewer_package_file_sha256": base._file_sha(path), "package_sha256": record["package_sha256"],
        }
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{condition['branch_id']}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, target, records, prepared, design)
    pairwise = {"schema_version": "n27phc-pairwise-package-differences-1", "rows": _pairwise_checks(records), "all_passed": True}
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {
        "schema_version": "n27phc-review-design-1", "review_trials": design["review_trials"],
        "controller_only_randomization": design["controller_only_randomization"],
    })
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n27phc-repair-design-1", "repair_traces": []})
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    resume = {
        "schema_version": "n27phc-no-model-resume-replay-1", "status": "passed", "model_calls": 0,
        "package_hashes_reconstruct": sorted(record["package_sha256"] for record in records) == sorted(row["package_sha256"] for row in _package_records(target)),
        "schedule_reconstructs": schedule()["review_trials"] == design["review_trials"],
        "partial_review_resume_supported": True, "replay_hash_verification_supported": True,
    }
    resume["qualification_sha256"] = ce.sha256(resume)
    ce._write_immutable(target / "qualification/no-model-resume-replay.json", resume)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (Path("src/use_case_icp/n27phc_experiment.py"), JOB1_SOURCE, ORACLE_SOURCE, Path("tests/test_n27phc_experiment.py"))


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("Attempt 054 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("cannot freeze after live reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or base._json(focused).get("status") != "passed":
        raise ValueError("focused N27PHC tests must pass before freeze")
    freeze = {
        "schema_version": "n27phc-experiment-freeze-1", "attempt": "054",
        "status": "frozen_before_live_experiment",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {relative.as_posix(): base._file_sha(repo_root / relative) for relative in _code_paths()},
        "attempt_053_hashes": deepcopy(PRESERVED_HASHES), "reused_hashes": deepcopy(REUSED_HASHES),
        "controller_only_schedule_seed": SCHEDULE_SEED,
        "private_qualification_tree_sha256": ce.sha256(ce._tree_hashes(target / "qualification-private")),
        "package_allowlist_file_sha256": base._file_sha(target / "qualification/package-allowlist-and-leakage.json"),
        "native_capture_file_sha256": base._file_sha(target / "qualification/native-captures.json"),
        "capture_hashes": {instance: built["prepared"]["captures"][instance]["capture_sha256"] for instance in INSTANCES},
        "catalogue_hashes": {instance: built["prepared"]["catalogues"][instance]["catalogue_sha256"] for instance in INSTANCES},
        "instance_hashes": {instance: built["prepared"]["instances"][instance]["instance_sha256"] for instance in INSTANCES},
        "tree_hashes": {folder: ce.sha256(ce._tree_hashes(target / folder)) for folder in (
            "capture-branches", "job-captures", "native-exports", "catalogues",
            "artifact-disclosures", "omission-manifests", "projections", "packages", "controller-manifests",
        )},
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "no_model_verification_file_sha256": base._file_sha(target / "qualification/no-model-verification.json"),
        "no_model_resume_replay_file_sha256": base._file_sha(target / "qualification/no-model-resume-replay.json"),
        "focused_test_results_file_sha256": base._file_sha(focused),
        "expected_counts": {"model_calibration_calls": 0, "instances": 16, "fresh_job_executions": 64, "packages": 96, "reviews": 288, "provider_calls": 576, "repairs": 0},
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0, "full_experiment_started": False,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    ce._write_immutable(path, freeze)
    return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _verify_authority(repo_root)
    freeze = base._json(target / "experiment-freeze.json")
    digest = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        if base._file_sha(repo_root / relative) != expected:
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
    return {"status": "verified", "freeze_sha256": digest, "packages": 96, "reviews": 288, "provider_calls": 576, "repairs": 0, "qualification": built["qualification"]}


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(base._json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("live authority must be consumed before reviews")
    record = {
        "schema_version": "n27phc-live-consumption-1", "authority": AUTHORITY_SHA256,
        "freeze_sha256": base._json(target / "experiment-freeze.json")["freeze_sha256"],
        "one_use_live_authority": True, "authorized_calls": 576,
        "model_calibration_calls": 0, "repairs": 0,
        "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _configure_review_controller() -> None:
    _install_base_bindings()
    base.render_request = render_request
    base.ATTEMPT = ATTEMPT
    pb.ATTEMPT = ATTEMPT


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    _install_base_bindings()
    rows = base._analysis_rows(reviews)
    for row in rows:
        row["difficulty_tier"] = DIFFICULTY.get(row["instance"])
    return rows


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    return base._summary(rows)


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    review_list = list(reviews)
    rows = _analysis_rows(review_list)
    aggregate = _summary(rows)
    if aggregate["fault_detection"]["denominator"] != 216 or aggregate["control_false_positives"]["denominator"] != 72:
        raise RuntimeError("fault/control analysis denominators changed")

    def mean(instance: str, cell: str, outcome: str) -> float:
        values = [float(row[outcome]) for row in rows if row["instance"] == instance and row["cell_id"] == cell]
        if len(values) != 3:
            raise RuntimeError("three within-instance repetitions are required")
        return sum(values) / 3

    contrasts = []
    for name, left, right in (
        ("graph", "P02", "P01"), ("adaptive_disclosure", "P04", "P02"),
        ("equal_call_reconsideration", "P06", "P02"), ("static_semantics", "P03", "P02"),
        ("adaptive_semantics", "P05", "P04"),
    ):
        for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation", "false_positive"):
            eligible = CONTROLS if outcome == "false_positive" else INSTANCES[len(CONTROLS):]
            differences = [mean(instance, left, outcome) - mean(instance, right, outcome) for instance in eligible]
            contrasts.append({
                "name": name, "left": left, "right": right, "outcome": outcome,
                "unit": "within_instance_mean_of_three_repetitions",
                "per_instance_differences": differences, "mean_difference": sum(differences) / len(differences),
            })
    mechanism_summaries = {
        mechanism: {
            "aggregate": _summary([row for row in rows if row["fault_mechanism"] == mechanism]),
            "by_cell": {cell: _summary([row for row in rows if row["fault_mechanism"] == mechanism and row["cell_id"] == cell]) for cell in CELLS},
        } for mechanism in sorted(set(FAULT_MECHANISM.values()))
    }
    tier_summaries = {
        tier: {
            "aggregate": _summary([row for row in rows if row["difficulty_tier"] == tier]),
            "by_cell": {cell: _summary([row for row in rows if row["difficulty_tier"] == tier and row["cell_id"] == cell]) for cell in CELLS},
        } for tier in ("ordinary_boundary", "hard_data_dependent")
    }
    per_call = {}
    for cell in CELLS:
        selected = [review for review in review_list if review["controller_trial"]["cell_id"] == cell]
        positions = []
        for position in range(1, CALLS_BY_CELL[cell] + 1):
            calls = [review["usage"]["calls"][position - 1] for review in selected]
            positions.append({
                "call_position": position, "calls": len(calls),
                "mean_input_tokens": sum(int(call.get("input_tokens") or 0) for call in calls) / len(calls),
                "mean_cached_input_tokens": sum(int(call.get("cached_input_tokens") or 0) for call in calls) / len(calls),
                "mean_output_tokens": sum(int(call.get("output_tokens") or 0) for call in calls) / len(calls),
                "mean_latency_seconds": sum(float(call.get("latency_seconds") or 0) for call in calls) / len(calls),
            })
        per_call[cell] = positions
    analysis = {
        "schema_version": "n27phc-full-experiment-analysis-1", "aggregate": aggregate,
        "cell_summaries": {cell: _summary([row for row in rows if row["cell_id"] == cell]) for cell in CELLS},
        "difficulty_tier_summaries": tier_summaries, "fault_mechanism_summaries": mechanism_summaries,
        "fault_instance_cell_summaries": {f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell]) for instance in INSTANCES[len(CONTROLS):] for cell in CELLS},
        "control_instance_cell_summaries": {f"{instance}/{cell}": _summary([row for row in rows if row["instance"] == instance and row["cell_id"] == cell]) for instance in CONTROLS for cell in CELLS},
        "prespecified_paired_contrasts": contrasts,
        "operations": {
            "adaptive_sessions": sum(row["cell_id"] in {"P04", "P05"} for row in rows),
            "reconsideration_sessions": sum(row["cell_id"] == "P06" for row in rows),
            "answer_changes": sum(row["answer_changed"] for row in rows),
            "truth_group_selections": sum(row["selected_group_contained_truth_state"] for row in rows),
            "truth_artifact_selections": sum(row["selected_artifact_was_truth_state"] for row in rows),
            "artifact_bytes_returned": sum(row["artifact_bytes_returned"] for row in rows),
        },
        "per_call_token_latency": per_call,
        "token_accounting": {"input_includes_cached_input": True, "input_plus_output_tokens": aggregate["input_tokens"] + aggregate["output_tokens"]},
        "analysis_unit": "three repetitions averaged within instance before cross-instance contrasts",
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(target / "analysis/summary.json", analysis)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    base._write_text(target / "analysis/all-review-rows.csv", stream.getvalue())
    return target / "analysis/summary.json"


def _write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = base._json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PHC-larger-hard-fault-native-etiq-experiment"
    findings = [
        "# N27PHC larger mixed-difficulty native-Etiq experiment", "",
        "Attempt 054 completed the authorized sixteen-instance experiment while preserving Attempt 053.", "",
        "## Aggregate outcomes", "",
        f"- Fault sensitivity: {base._rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {base._rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {base._rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {base._rate(aggregate['control_false_positives'])}",
        f"- Scientific calls: {aggregate['provider_calls']}; calibration calls: 0; repairs: 0",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; input plus output {aggregate['total_tokens']}",
        f"- Aggregate provider latency: {aggregate['latency_seconds']:.3f} seconds", "",
        "Every arm received byte-identical complete source and actual top-level inputs and parsed outputs for all four jobs. Only Job 4 supplied stdout and stderr.", "",
        "## Records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-054/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-054/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-054/replay.json)",
        "- [Terminal](../../../../outputs/fault-experiments-v2-2-n10/attempt-054/terminal-state.json)",
    ]
    base._write_text(report_dir / "findings.md", "\n".join(findings))
    cell = ["# Cell results", "", "| Cell | Reviews | Detection | Job 1 | Exact | Control FP | Calls |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name in CELLS:
        value = analysis["cell_summaries"][name]
        cell.append(f"| {name} | {value['reviews']} | {base._rate(value['fault_detection'])} | {base._rate(value['correct_job_attribution'])} | {base._rate(value['exact_function_localisation'])} | {base._rate(value['control_false_positives'])} | {value['provider_calls']} |")
    base._write_text(report_dir / "cell-table.md", "\n".join(cell))
    for key, filename in (("fault_mechanism_summaries", "fault-mechanism-table.md"), ("difficulty_tier_summaries", "difficulty-tier-table.md")):
        lines = [f"# {key.replace('_', ' ').title()}", "", "| Group | Cell | Detection | Job 1 | Exact |", "|---|---|---:|---:|---:|"]
        for group, values in analysis[key].items():
            for name in CELLS:
                value = values["by_cell"][name]
                lines.append(f"| {group} | {name} | {base._rate(value['fault_detection'])} | {base._rate(value['correct_job_attribution'])} | {base._rate(value['exact_function_localisation'])} |")
        base._write_text(report_dir / filename, "\n".join(lines))
    base._write_text(report_dir / "paired-contrasts.json", json.dumps(analysis["prespecified_paired_contrasts"], indent=2, sort_keys=True))
    base._write_text(report_dir / "per-call-token-latency.json", json.dumps(analysis["per_call_token_latency"], indent=2, sort_keys=True))
    operation = ["# Adaptive operations", "", "| Trial | Cell | Group | Artifact | True group | True artifact |", "|---|---|---|---|---|---|"]
    review_table = ["# Review results", "", "| Position | Trial | Instance | Cell | Rep | Detected | Job | Function | Calls |", "|---:|---|---|---|---:|---|---|---|---:|"]
    for review in sorted(reviews, key=lambda row: row["controller_trial"]["schedule_position"]):
        trial, group, artifact = review["controller_trial"], review.get("selected_group") or {}, review.get("selected_artifact") or {}
        operation.append(f"| {trial['trial_id']} | {trial['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} |")
        review_table.append(f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['opaque_instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |")
    base._write_text(report_dir / "operation-table.md", "\n".join(operation))
    base._write_text(report_dir / "review-table.md", "\n".join(review_table))


def _write_handoff(repo_root: Path, target: Path) -> None:
    aggregate = base._json(target / "analysis/summary.json")["aggregate"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PHC Attempt 054 larger mixed-difficulty experiment results", "",
        "Status: `completed_full_experiment_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{base._json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "Counts", "", "- Zero calibration calls", "- Sixteen fresh instances and 64 fresh native Etiq job captures",
        f"- 96 packages; 288 terminal reviews; {aggregate['provider_calls']} logical scientific calls; zero repairs", "",
        "Outcomes", "", f"- Sensitivity: {base._rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {base._rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {base._rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {base._rate(aggregate['control_false_positives'])}", "",
        "Attempt 053, Jobs 2-4, prompt, schemas and protected execution surfaces remained unchanged.",
    ]
    base._write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PHC_attempt_054_results_to_overseer.email.md", "\n".join(lines))


def execute_lifecycle(repo_root: Path, target: Path) -> Path:
    repo_root, target = repo_root.resolve(), target.resolve()
    _configure_review_controller()
    verified = verify_frozen_attempt(repo_root, target)
    create_live_consumption(repo_root, target)
    prepared = prepare_attempt(repo_root, target)
    packages = {record["controller_condition"]["branch_id"]: record for record in _package_records(target)}
    trials = base._json(target / "review-design.json")["review_trials"]
    relevance = base._json(target / "qualification-private/adaptive-relevance.json")["faults"]
    reviews = []
    for trial in trials:
        path = target / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = base._json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record["controller_trial"] != trial or record["status"] != "complete":
                raise ValueError("invalid partial review record")
        else:
            instance = trial["opaque_instance_id"]
            package_record = packages[trial["branch_id"]]
            session = base.run_review_session(
                repo_root, target, prepared["catalogues"][instance], prepared["reviewer_nodes"][instance],
                prepared["disclosures"][instance], prepared["indexes"][instance], package_record, trial["trial_id"],
            )
            pre, final = session["pre_validation"], session["final_validation"]
            outcome = base.score_response(prepared["instances"][instance], final)
            truth = relevance.get(instance, {})
            group, artifact = session["selected_group"] or {}, session["selected_artifact"] or {}
            record = {
                "schema_version": "n27phc-review-record-1", "controller_trial": deepcopy(trial),
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
                "answer_changed": session["answer_changed"], "completed_expansions": session["completed_expansions"],
                "completed_artifact_inspections": session["completed_artifact_inspections"],
                "completed_reconsiderations": session["completed_reconsiderations"],
                "call_records": session["call_records"], "usage": session["usage"], "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews.append(record)
        print(f"N27PHC review {len(reviews)}/288 complete: {trial['cell_id']}", flush=True)
    counts = pb.reconstruct_counts(reviews)
    if counts["reviews"] != 288 or counts["repairs"] != 0 or counts["logical_provider_calls"] != 576:
        raise RuntimeError(f"terminal review/call counts invalid: {counts}")
    call_ids = [call_id for review in reviews for call in review["call_records"] for call_id in call["call_ids"]]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("duplicate provider call ID")
    for call_id in call_ids:
        base.verify_record(target / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = base._json(write_analysis(target, reviews))
    freeze = base._json(target / "experiment-freeze.json")
    replay = {
        "schema_version": "n27phc-replay-1", "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(review["review_sha256"] for review in reviews),
        "observed_counts": counts, "planned_scientific_calls": 576, "model_calibration_calls": 0,
        "all_record_hashes_recomputed": True, "duplicate_provider_call_ids": False,
        "frozen_trees_unchanged": all(ce.sha256(ce._tree_hashes(target / folder)) == expected for folder, expected in freeze["tree_hashes"].items()),
        "frozen_private_qualification_unchanged": ce.sha256(ce._tree_hashes(target / "qualification-private")) == freeze["private_qualification_tree_sha256"],
        "provider_receipts_preserved": all(review["initial_receipt"] and review["terminal_receipt"] for review in reviews),
        "repair_count": 0,
        "attempt_053_preserved": all(base._file_sha(repo_root / ATTEMPT_053 / path) == expected for path, expected in PRESERVED_HASHES.items()),
        "reused_and_protected_files_preserved": all(base._file_sha(repo_root / path) == expected for path, expected in REUSED_HASHES.items()),
        "full_experiment_completed": True,
    }
    if not all(replay[key] for key in ("frozen_trees_unchanged", "frozen_private_qualification_unchanged", "provider_receipts_preserved", "attempt_053_preserved", "reused_and_protected_files_preserved")):
        raise RuntimeError("replay reconciliation failed")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(target / "replay.json", replay)
    terminal = {
        "schema_version": "n27phc-terminal-1", "status": "completed_full_experiment_and_analysis",
        "model_calibration_call_count": 0, "instance_count": 16, "fresh_job_capture_count": 64,
        "package_count": 96, "review_count": 288, "planned_scientific_provider_calls": 576,
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
            "schema_version": "n27phc-terminal-1", "status": "terminal_incomplete",
            "failure_stage": "n27phc_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}",
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
            return 0 if base._json(path).get("status") == "completed_full_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N27PHC experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
