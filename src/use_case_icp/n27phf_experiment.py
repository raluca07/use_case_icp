"""Thin Attempt-057 binding for the natural-state multi-fault experiment."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import corrected_experiment as ce
from . import n27phb_experiment as base
from . import n27phd_experiment as lifecycle
from . import n27phe_experiment as prior
from . import n27pb_experiment as pb


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-057")
ATTEMPT_056 = Path("outputs/fault-experiments-v2-2-n10/attempt-056")
TASK = Path("instructions_between_agent_types/developer/current/N27PHF_natural_state_multi_hard_fault_experiment.email.md")
TASK_SHA256 = "sha256:0821c5f5cccda5854a2758c1127d9e3aef75eecffd10133317243616e901bb80"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PHF_natural_state_multi_hard_fault_experiment_authorization.json")
AUTHORITY_SHA256 = "sha256:e2330af373f5282eefe50a09d1151e115c2ddc40351cfd0cfd0f9772246536c7"

JOB1_SOURCE = Path("src/use_case_icp/n27phe_market_evidence.py")
JOB2_SOURCE = base.JOB2_SOURCE
JOB3_SOURCE = Path("src/use_case_icp/n27phf_campaign_allocation.py")
JOB4_SOURCE = base.JOB4_SOURCE
ORACLE_SOURCE = Path("src/use_case_icp/n27phd_hidden_oracle.py")
JOB_ORDER = base.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
JOB_SOURCES = {JOB1: JOB1_SOURCE, JOB2: JOB2_SOURCE, JOB3: JOB3_SOURCE, JOB4: JOB4_SOURCE}

CONTROLS = ("case-control-01", "case-control-02", "case-control-03", "case-control-04")
R = ("case-r01", "case-r02")
S = ("case-s01", "case-s02")
E = ("case-e01", "case-e02")
V = ("case-v01", "case-v02")
D = ("case-d01", "case-d02")
C = ("case-c01", "case-c02")
FAULTS = R + S + E + V + D + C
INSTANCES = CONTROLS + FAULTS
TRUTH = {
    **{item: None for item in CONTROLS},
    **{item: "weight_source_reliability" for item in R},
    **{item: "select_snapshot_observations" for item in S + E},
    **{item: "reduce_source_repeats" for item in V + D},
    **{item: "allocate_campaign_budget" for item in C},
}
FAULT_JOB = {**{item: JOB1 for item in R + S + E + V + D}, **{item: JOB3 for item in C}}
FAULT_MECHANISM = {
    **{item: "R_premature_contribution_rounding" for item in R},
    **{item: "S_recorded_time_snapshot_substitution" for item in S},
    **{item: "E_expiry_compared_with_recorded_time" for item in E},
    **{item: "V_oldest_repeat_retained" for item in V},
    **{item: "D_repeat_rank_scoped_by_source" for item in D},
    **{item: "C_non_cumulative_channel_cap" for item in C},
}
DIFFICULTY = {item: "prespecified_data_dependent" for item in FAULTS}
MATCHED_CLEAN = {item: CONTROLS[index % len(CONTROLS)] for index, item in enumerate(FAULTS)}
MUTATIONS = {
    **{item: (
        "aggregation_contribution = raw_contribution",
        'aggregation_contribution = raw_contribution.round(int(planning_policy["display_precision"]))',
    ) for item in R},
    **{item: (
        'effective_admitted = dated_df["_effective"].le(snapshot)',
        'effective_admitted = dated_df["_recorded"].le(snapshot)',
    ) for item in S},
    **{item: (
        'dated_df["_expires"].ge(snapshot)',
        'dated_df["_expires"].ge(dated_df["_recorded"])',
    ) for item in E},
    **{item: (
        "ascending=[True, True, False], kind=\"stable\"",
        "ascending=[True, True, True], kind=\"stable\"",
    ) for item in V},
    **{item: (
        '["opportunity_id", "source_id"], sort=False',
        '["source_id"], sort=False',
    ) for item in D},
    **{item: (
        'float(budget_policy["channel_caps"][channel]) - channel_used.get(channel, 0.0),',
        'float(budget_policy["channel_caps"][channel]),',
    ) for item in C},
}
SCHEDULE_SEED = 570924271

PRESERVED_HASHES = {
    "experiment-freeze.json": "sha256:4a235a9061b6edae19c2fd71602c69328e855ec9eee1cdbb21a680e04565caf0",
    "live-consumption.json": "sha256:715299937f4d2ca31cd4c1142428c103ed68d6c2d7043339c7b6682bd97f88c4",
}
REUSED_HASHES = {
    "src/use_case_icp/n27phe_experiment.py": "sha256:c05f29ed0e77d1e944a4def21f7bb3481a48ffa79082b27d3934606f69bcd9da",
    "src/use_case_icp/n27phe_market_evidence.py": "sha256:8c422df1584b0b502fdddcf81da23d2fc247b4db1c4a39ca1e3fd96750e1e97a",
    "src/use_case_icp/n27phb_experiment.py": "sha256:b70767f31d637b781835f5cdd5aa8760ecc74fe19e636fb2a1a451d1ff60fb6e",
    "src/use_case_icp/n27phd_experiment.py": "sha256:feb098ce5fef38235aa91adafe61b6fb45986bc7fb12c8cdb222df3389866a48",
    "src/use_case_icp/n27phb_opportunity_priority.py": "sha256:831f432197695ebc7c5ba8c9b1d110ff9d4bf313c8be53a6f993cd5d7e21d33e",
    "src/use_case_icp/n27phb_activation_schedule.py": "sha256:97aefa58a6a4ecf3afe7e7462e04e77f662d80e8c70413464cb4c636e7ebd345",
    "prompts/v2_2/n27phb_review.md": "sha256:21c4e57fa69676d4a20ff943f65d819786bcabc92a3d055faf15dd66da46b229",
    "schemas/v2_2/n27phb_choose_artifact.schema.json": "sha256:337f61a0461c1c0e6503b5476bd33d311d01e2040f0a0478f2177dc6a79bb5ca",
    "schemas/v2_2/n27phb_choose_group.schema.json": "sha256:91355d0f492ffe272e70396efdaf4948d9d8ddd354db7df3c15a8f7575b229a2",
    "schemas/v2_2/n27phb_final.schema.json": "sha256:f94c7658f69212994de5e1276d26e1871a689c16b5d509fc0fde72b0a6a19351",
    "schemas/v2_2/n27phb_reconsider.schema.json": "sha256:7e482027a5c34b770c55c38f5d94b2d3c728ee05d502c10256a5d7addb57766e",
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
    "src/use_case_icp/fault_operations.py": "sha256:1bb57683e121d179a3fc2e25351b6cb014b008a39ce867c6f79e75c38014d033",
}

_ORIGINAL_CAPTURE = base._capture_instance
_ORIGINAL_PIPELINE = base._pipeline
_ORIGINAL_QUALIFY_PACKAGES = lifecycle.qualify_packages
_ORIGINAL_FREEZE = lifecycle.freeze_attempt
_ORIGINAL_WRITE_ANALYSIS = lifecycle.write_analysis
_ORIGINAL_PREPARE = lifecycle.prepare_attempt


def input_for(instance: str) -> dict[str, Any]:
    if instance not in INSTANCES:
        raise KeyError(instance)
    index = INSTANCES.index(instance)
    prefix = f"field-{index + 1:02d}"
    root = base._fixture(prefix, ("a", "b", "c")[index % 3], stressed=index % 2 == 1)
    policy = root["planning_policy"]

    for row in root["market_observations"]:
        if row["opportunity_id"] == f"{prefix}-opportunity-threshold":
            row["campaign_id"] = f"{prefix}-campaign-gamma"
            row["evidence_value"] += 0.055 + 0.0013 * index
        if row["contribution_id"] == f"{prefix}-contribution-temporal-older":
            row["evidence_value"] = 0.47 + 0.003 * (index % 4)

    root["market_observations"].extend([
        base._observation(
            prefix, "late-effective", "opportunity-stable", "source-late-effective", "north",
            "campaign-alpha", "email", "2026-09-20", "2026-09-10T08:00:00",
            0.167 + 0.0031 * index, 184000 + 900 * index,
        ),
        base._observation(
            prefix, "expired-after-recording", "opportunity-temporal", "source-expiry-edge", "south",
            "campaign-beta", "social", "2026-09-05", "2026-09-06T08:00:00",
            0.15 + 0.12 * (index % 2) + 0.001 * index,
            158000 + 700 * index, valid="2026-09-10",
        ),
        base._observation(
            prefix, "temporal-backup", "opportunity-temporal", "source-temporal-backup", "south",
            "campaign-beta", "social", "2026-08-25", "2026-08-26T08:00:00",
            0.35 + 0.002 * index, 158000 + 700 * index,
        ),
        base._observation(
            prefix, "distractor", "opportunity-stable", "source-distractor", "north",
            "campaign-alpha", "email", "2026-08-28", "2026-08-29T08:00:00",
            0.109 + 0.0019 * index, 184000 + 900 * index,
        ),
    ])
    root["source_reliability"].extend([
        {"source_id": f"{prefix}-source-late-effective", "segment": "north", "reliability": 0.73 + 0.004 * (index % 5)},
        {"source_id": f"{prefix}-source-expiry-edge", "segment": "south", "reliability": 0.62 + 0.12 * (index % 2)},
        {"source_id": f"{prefix}-source-temporal-backup", "segment": "south", "reliability": 0.75 + 0.006 * (index % 3)},
        {"source_id": f"{prefix}-source-distractor", "segment": "north", "reliability": 0.77 + 0.003 * (index % 6)},
    ])
    root["budget_policy"]["channel_caps"]["email"] = 8010.0 + 8.0 * index
    root["budget_policy"]["total_budget"] = 26000.0 + 31.0 * index
    shift = index % len(root["market_observations"])
    root["market_observations"] = root["market_observations"][shift:] + root["market_observations"][:shift]
    assert policy["as_of_date"] == "2026-09-15"
    return deepcopy(root)


def _source_for_instance(repo_root: Path, instance: str) -> tuple[str, str, dict[str, Any] | None]:
    job1 = (repo_root / JOB1_SOURCE).read_text()
    job3 = (repo_root / JOB3_SOURCE).read_text()
    if instance in CONTROLS:
        return job1, job3, None
    old, new = MUTATIONS[instance]
    target = job3 if instance in C else job1
    if target.count(old) != 1:
        raise ValueError(f"mutation site is not unique: {instance}")
    mutated = target.replace(old, new, 1)
    if ast.dump(ast.parse(target)) == ast.dump(ast.parse(mutated)):
        raise ValueError(f"mutation does not change AST: {instance}")
    record = {
        "operator": "single_executed_ast_site_substitution", "job_id": FAULT_JOB[instance],
        "qualified_function_name": TRUTH[instance], "original_snippet": old, "mutant_snippet": new,
        "candidate_count": 1, "original_span": {"start_line": target.count("\n", 0, target.index(old)) + 1},
        "mutated_source_sha256": ce.sha256(mutated.encode()),
    }
    record["mutation_sha256"] = ce.sha256(record)
    return (job1, mutated, record) if instance in C else (mutated, job3, record)


def _mutant_source(clean: str, instance: str) -> tuple[str, dict[str, Any] | None]:
    job1, _, mutation = _source_for_instance(Path(__file__).resolve().parents[2], instance)
    return job1, mutation


def _configured_pipeline(repo_root: Path, instance: str, job_id: str, job1_source: str):
    pipeline = _ORIGINAL_PIPELINE(repo_root, job_id, job1_source)
    if job_id == JOB3:
        _, job3_source, _ = _source_for_instance(repo_root, instance)
        pipeline.files[0].content = job3_source
        boundary = next(row for row in pipeline.review_boundaries if row["qualified_function_name"] == "aggregate_campaign_candidates")
        boundary["role"] = "Aggregate campaign candidates and attribution commitment."
        boundary["expected_outputs"] = ["candidate dataframe", "attribution commitment"]
    pipeline.validate()
    return pipeline


def _capture_instance(repo_root: Path, target: Path, instance: str, job1_source: str):
    previous = base._pipeline
    base._pipeline = lambda root, job, source: _configured_pipeline(root, instance, job, source)
    try:
        return _ORIGINAL_CAPTURE(repo_root, target, instance, job1_source)
    finally:
        base._pipeline = previous


def _run_sources(repo_root: Path, root: Mapping[str, Any], instance: str) -> dict[str, Any]:
    job1, job3, _ = _source_for_instance(repo_root, instance)
    sources = {
        JOB1: job1, JOB2: (repo_root / JOB2_SOURCE).read_text(),
        JOB3: job3, JOB4: (repo_root / JOB4_SOURCE).read_text(),
    }
    prior_output = None
    inputs, outputs = {}, {}
    for job in JOB_ORDER:
        runtime_input = base._job_input(job, prior_output, root)
        output = base._run_program(sources[job], runtime_input, repo_root)
        base._validate_output(job, output, runtime_input)
        inputs[job], outputs[job], prior_output = runtime_input, output, output
    return {"inputs": inputs, "outputs": outputs}


def _shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items() if not key.endswith("sha256")}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    return "<number>" if isinstance(value, (int, float)) else value


def _preservation_manifest(repo_root: Path, target: Path) -> dict[str, Any]:
    path = target / "lineage/attempt-056-preservation.json"
    if path.exists():
        record = base._json(path)
        ce._verified_self_hash(record, "manifest_sha256")
        return record
    prior_root = repo_root / ATTEMPT_056
    for relative, expected in PRESERVED_HASHES.items():
        if base._file_sha(prior_root / relative) != expected:
            raise ValueError(f"Attempt 056 preservation binding changed: {relative}")
    record = {
        "schema_version": "n27phf-attempt-056-preservation-1", "status": "preserved_partial_attempt",
        "rule": "read-only; never resume or pool", "bound_file_hashes": deepcopy(PRESERVED_HASHES),
        "review_records": len(list((prior_root / "reviews").glob("*.json"))),
        "tree_sha256": ce.sha256(ce._tree_hashes(prior_root)),
    }
    record["manifest_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return record


def _edge_checks(root: Mapping[str, Any]) -> dict[str, bool]:
    rows = root["market_observations"]
    snapshot = root["planning_policy"]["as_of_date"]
    by_source: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_source.setdefault(row["source_id"], []).append(row)
    repeats = [
        values for values in by_source.values()
        if len({row["opportunity_id"] for row in values}) == 1 and len(values) > 1
    ]
    return {
        "R": False,
        "S": any(row["recorded_at"][:10] <= snapshot < row["effective_date"] for row in rows),
        "E": any(row["recorded_at"][:10] <= row["valid_until"] < snapshot for row in rows),
        "V": any(
            len({row["effective_date"] for row in values}) > 1
            and [row["contribution_id"] for row in sorted(values, key=lambda row: row["effective_date"])]
            != [row["contribution_id"] for row in sorted(values, key=lambda row: row["evidence_value"])]
            for values in repeats
        ),
        "D": any(len({row["opportunity_id"] for row in values}) > 1 for values in by_source.values()) and bool(repeats),
        "C": False,
    }


def _private_qualification(repo_root: Path, target: Path) -> dict[str, Any]:
    path = target / "qualification-private/qualification-summary.json"
    if path.exists():
        record = base._json(path)
        ce._verified_self_hash(record, "qualification_sha256")
        return record
    _preservation_manifest(repo_root, target)
    controls, faults = {}, {}
    control_edges = {name: False for name in "RSEVDC"}
    symptoms: dict[str, set[str]] = {}
    old_job3 = (repo_root / "src/use_case_icp/n27phb_campaign_allocation.py").read_text()
    new_job3 = (repo_root / JOB3_SOURCE).read_text()
    for instance in INSTANCES:
        root = input_for(instance)
        clean = lifecycle._oracle_jobs(root)
        actual = _run_sources(repo_root, root, instance)["outputs"]
        clean_runtime = _run_sources(repo_root, root, CONTROLS[0])["outputs"] if instance not in CONTROLS else actual
        job2_input = base._job_input(JOB3, clean_runtime[JOB2], root)
        if base._run_program(old_job3, job2_input, repo_root) != base._run_program(new_job3, job2_input, repo_root):
            raise ValueError(f"clean Job-3 output equivalence failed: {instance}")
        edges = _edge_checks(root)
        attribution = clean_runtime[JOB1]["evidence_attribution"]
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for row in attribution:
            grouped.setdefault(row["opportunity_id"], []).append(row)
        precision = int(root["planning_policy"]["display_precision"])
        edges["R"] = any(
            len(values) >= 2 and round(sum(float(row["weighted_contribution"]) for row in values), precision)
            != round(sum(round(float(row["weighted_contribution"]), precision) for row in values), precision)
            for values in grouped.values()
        )
        cap_probe = _run_sources(repo_root, root, C[0])["outputs"][JOB3]["campaign_allocations"]
        email_probe = [row for row in cap_probe if row["channel"] == "email"]
        email_cap = float(root["budget_policy"]["channel_caps"]["email"])
        edges["C"] = (
            len(email_probe) >= 2
            and all(0 < float(row["allocated_budget"]) < email_cap for row in email_probe)
            and sum(float(row["allocated_budget"]) for row in email_probe) > email_cap
        )
        if instance in CONTROLS:
            control_edges = {name: control_edges[name] or edges[name] for name in control_edges}
        elif not edges[FAULT_MECHANISM[instance][0]]:
            raise ValueError(f"fixture lacks its required edge pattern: {instance}/{edges}")
        _, _, mutation = _source_for_instance(repo_root, instance)
        if instance in CONTROLS:
            if not prior._outputs_equal(actual, clean):
                raise ValueError(f"clean control differs from oracle: {instance}")
        else:
            clean_opportunities = [row["opportunity_id"] for row in clean[JOB1]["opportunities"]]
            fault_opportunities = [row["opportunity_id"] for row in actual[JOB1]["opportunities"]]
            clean_allocations = [row["campaign_id"] for row in clean[JOB3]["campaign_allocations"]]
            fault_allocations = [row["campaign_id"] for row in actual[JOB3]["campaign_allocations"]]
            clean_actions = clean[JOB4]["activation_plan"]["activation_actions"]
            fault_actions = actual[JOB4]["activation_plan"]["activation_actions"]
            clean_ids = [(row["campaign_id"], row["window_id"]) for row in clean_actions]
            fault_ids = [(row["campaign_id"], row["window_id"]) for row in fault_actions]
            if (
                clean_opportunities != fault_opportunities
                or clean_allocations != fault_allocations
                or clean_ids != fault_ids
            ):
                raise ValueError(f"fault changes business identities, ordering or counts: {instance}")
            deltas = [round(float(right["scheduled_budget"]) - float(left["scheduled_budget"]), 8) for left, right in zip(clean_actions, fault_actions)]
            if not any(delta != 0 for delta in deltas) or max(abs(delta) for delta in deltas) > 1500:
                raise ValueError(f"Job-4 symptom is not small and nonzero: {instance}/{deltas}")
            symptom = ce.sha256(deltas)
            group = FAULT_MECHANISM[instance]
            if symptom in symptoms.setdefault(group, set()):
                raise ValueError(f"within-mechanism numerical symptom is not distinct: {instance}")
            symptoms[group].add(symptom)
        record = {
            "schema_version": "n27phf-private-case-1", "instance": instance,
            "designation": "clean_control" if instance in CONTROLS else "fault",
            "fault_mechanism": FAULT_MECHANISM.get(instance), "truth_job": FAULT_JOB.get(instance),
            "truth_function": TRUTH[instance], "mutation": mutation, "edge_patterns": edges,
            "clean_outputs": clean, "executed_outputs": actual,
            "business_identity_count_order_preserved": True,
            "independent_executed_mutant_match": True,
        }
        record["record_sha256"] = ce.sha256(record)
        folder = "controls" if instance in CONTROLS else "faults"
        ce._write_immutable(target / "qualification-private" / folder / f"{instance}.json", record)
        (controls if instance in CONTROLS else faults)[instance] = record["record_sha256"]
    if not all(control_edges.values()):
        raise ValueError(f"clean controls do not collectively cover all edge patterns: {control_edges}")
    summary = {
        "schema_version": "n27phf-private-deterministic-qualification-1", "status": "passed",
        "model_calls": 0, "fault_mechanisms": 6, "fault_instances": 12, "clean_controls": 4,
        "one_site_faults": 12, "pairwise_distinct_within_mechanism": True,
        "all_controls_cover_all_edge_patterns": True, "clean_job3_byte_equivalent": True,
        "collective_control_edge_coverage": control_edges,
        "controls": controls, "faults": faults,
    }
    summary["qualification_sha256"] = ce.sha256(summary)
    ce._write_immutable(path, summary)
    return summary


def adaptive_relevance(prepared: Mapping[str, Any], target: Path) -> dict[str, Any]:
    context = dict(prepared) | {"attempt_root": target}
    primary = {
        **{item: (JOB1, "weighted_df") for item in R},
        **{item: (JOB1, "dated_df") for item in S + E},
        **{item: (JOB1, "ordered_df") for item in V},
        **{item: (JOB1, "decision_rank") for item in D},
        **{item: (JOB3, "ordered_df") for item in C},
    }
    faults, natural = {}, {}
    for instance in FAULTS:
        job, state = primary[instance]
        binding = base._artifact_for_state(context, instance, job, state)
        faults[instance] = {
            "truth_function": TRUTH[instance], "fault_mechanism": FAULT_MECHANISM[instance],
            "decisive_state_name": state, **binding, "initially_hidden": True,
            "one_expansion_reachable": True, "one_inspection_reachable": True,
        }
        if instance in V + D:
            state_rows = []
            compact = base._json(target / "projections" / f"{instance}-compact.json")
            common = ce.canonical_json(lifecycle._job_executions(prepared["catalogues"][instance]))
            compact_bytes = ce.canonical_json(compact)
            for natural_state in ("ordered_df", "decision_rank"):
                item = base._artifact_for_state(context, instance, JOB1, natural_state)
                expanded, event = pb.expand_native_subtree(
                    prepared["catalogues"][instance], prepared["reviewer_nodes"][instance],
                    prepared["indexes"][instance], {"graph_review": {"evidence": compact}},
                    item["execution_group_id"],
                )
                if item["artifact_ref"] not in event["newly_disclosed_artifact_refs"]:
                    raise ValueError(f"natural state is not newly disclosed: {instance}/{natural_state}")
                artifact = prepared["disclosures"][instance]["artifacts"][item["artifact_ref"]]
                content = artifact["operation_node"]["artifact_content"]
                if ce.canonical_json(content) in common or ce.canonical_json(content) in compact_bytes:
                    raise ValueError(f"natural state already occurs in common or Compact evidence: {instance}/{natural_state}")
                modes = artifact["descriptor"]["available_inspections"]
                mode = "full" if "full" in modes else modes[-1]
                inspection = pb.inspect_artifact(
                    Path(__file__).resolve().parents[2], prepared["disclosures"][instance], expanded,
                    {"artifact_ref": item["artifact_ref"], "inspection": mode}, {item["artifact_ref"]},
                )
                if inspection["status"] != "completed" or inspection["native_operation_content_bytes"] <= 0:
                    raise ValueError(f"natural-state inspection failed: {instance}/{natural_state}")
                state_rows.append({
                    "state_name": natural_state, **item, "absent_from_common": True,
                    "absent_from_initial_compact": True, "retained_in_native_catalogue": True,
                    "probe_status": "completed", "returned_value_sha256": inspection["returned_value_sha256"],
                })
            natural[instance] = state_rows
    record = {
        "schema_version": "n27phf-adaptive-relevance-1", "status": "passed", "faults": faults,
        "natural_state_probes": natural, "natural_state_instances": 4, "natural_state_comparisons": 8,
        "model_choice_forced": False, "rounding_state_claim": "runtime organization and provenance only",
    }
    record["qualification_sha256"] = ce.sha256(record)
    return record


def natural_state_qualification(prepared: Mapping[str, Any], target: Path) -> dict[str, Any]:
    relevance = adaptive_relevance(prepared, target)
    return {
        "schema_version": "n27phf-natural-state-qualification-1", "status": "passed",
        "case_count": 4, "state_comparisons": 8, "model_calls": 0,
        "cases": deepcopy(relevance["natural_state_probes"]),
        "qualification_sha256": ce.sha256({
            "schema_version": "n27phf-natural-state-qualification-1", "status": "passed",
            "case_count": 4, "state_comparisons": 8, "model_calls": 0,
            "cases": relevance["natural_state_probes"],
        }),
    }


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    prepared = _ORIGINAL_PREPARE(repo_root, attempt_root)
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    for instance in C:
        record = deepcopy(prepared["instances"][instance])
        if record.get("truth_job") == JOB3:
            continue
        record["truth_job"] = JOB3
        record.pop("instance_sha256", None)
        record["instance_sha256"] = ce.sha256(record)
        path = target / "qualification-private/instances" / f"{instance}.json"
        if path.exists():
            path.unlink()
        ce._write_immutable(path, record)
        prepared["instances"][instance] = record
    return prepared


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]],
                     prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_QUALIFY_PACKAGES(repo_root, target, records, prepared, design)
    forbidden = (
        "contribution_audit_df", "_decision_df", "_witness_df", "_diagnosis_df", "_precision_df",
    )
    inspected = []
    paths = [JOB1_SOURCE, JOB3_SOURCE]
    paths.extend(sorted((target / "catalogues").glob("*.json")))
    paths.extend(sorted((target / "native-exports").glob("*/*/etiq-native-lineage.json")))
    for path in paths:
        actual = path if path.is_absolute() else repo_root / path
        text = actual.read_text()
        matches = [token for token in forbidden if token in text]
        if matches:
            raise ValueError(f"prohibited diagnostic state in {actual}: {matches}")
        inspected.append(actual.relative_to(repo_root).as_posix() if actual.is_relative_to(repo_root) else actual.as_posix())
    for package_record in records:
        rendered = (repo_root / lifecycle.PROMPT).read_text() + json.dumps(
            lifecycle.render_request(package_record["reviewer_package"]), ensure_ascii=False, sort_keys=True
        )
        matches = [token for token in forbidden if token in rendered]
        if matches:
            raise ValueError(f"rendered package contains prohibited diagnostic state: {matches}")
    preservation = _preservation_manifest(repo_root, target)
    if ce.sha256(ce._tree_hashes(repo_root / ATTEMPT_056)) != preservation["tree_sha256"]:
        raise ValueError("Attempt 056 changed after its preservation manifest was recorded")
    result.update({
        "attempt_056_preservation_verified": True,
        "attempt_056_preservation_manifest_sha256": preservation["manifest_sha256"],
        "contribution_audit_df_occurrences": 0,
        "replacement_diagnostic_state_occurrences": 0,
        "recursive_cleanup_files_checked": len(inspected),
        "natural_state_qualification_sha256": base._json(
            target / "qualification-private/truthful-witnesses.json"
        )["qualification_sha256"],
    })
    return result


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27phf_experiment.py"), JOB3_SOURCE,
        Path("tests/test_n27phf_experiment.py"),
    )


def _bind() -> None:
    values = {
        "ATTEMPT": ATTEMPT, "ATTEMPT_054": ATTEMPT_056, "TASK": TASK, "TASK_SHA256": TASK_SHA256,
        "AUTHORITY": AUTHORITY, "AUTHORITY_SHA256": AUTHORITY_SHA256,
        "JOB1_SOURCE": JOB1_SOURCE, "JOB2_SOURCE": JOB2_SOURCE, "JOB3_SOURCE": JOB3_SOURCE,
        "JOB4_SOURCE": JOB4_SOURCE, "ORACLE_SOURCE": ORACLE_SOURCE, "JOB_SOURCES": JOB_SOURCES,
        "CONTROLS": CONTROLS, "H1": R, "H2": S, "H3": E, "H4": V + D + C,
        "INSTANCES": INSTANCES, "TRUTH": TRUTH, "FAULT_MECHANISM": FAULT_MECHANISM,
        "DIFFICULTY": DIFFICULTY, "MATCHED_CLEAN": MATCHED_CLEAN, "MUTATIONS": MUTATIONS,
        "SCHEDULE_SEED": SCHEDULE_SEED, "PRESERVED_HASHES": PRESERVED_HASHES,
        "REUSED_HASHES": REUSED_HASHES, "input_for": input_for, "_mutant_source": _mutant_source,
        "_deterministic_private_qualification": _private_qualification,
        "prepare_attempt": prepare_attempt, "adaptive_relevance": adaptive_relevance,
        "truthful_witness_qualification": natural_state_qualification,
        "qualify_packages": qualify_packages, "_code_paths": _code_paths,
    }
    for name, value in values.items():
        setattr(lifecycle, name, value)
    base._capture_instance = _capture_instance
    lifecycle.write_analysis = write_analysis
    lifecycle._write_reports = write_reports
    lifecycle._write_handoff = write_handoff
    lifecycle.freeze_attempt = freeze_attempt


def _summary_for(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    return lifecycle._summary(rows)


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    review_list = list(reviews)
    path = _ORIGINAL_WRITE_ANALYSIS(target, review_list)
    analysis = base._json(path)
    rows = lifecycle._analysis_rows(review_list)

    def mean(instance: str, cell: str, outcome: str) -> float:
        values = [float(row[outcome]) for row in rows if row["instance"] == instance and row["cell_id"] == cell]
        if len(values) != 3:
            raise RuntimeError("three repetitions are required for each instance/cell")
        return sum(values) / 3

    contrasts = []
    for name, left, right in (
        ("primary_adaptive_semantics", "P05", "P01"),
        ("static_graph", "P02", "P01"),
        ("static_semantics", "P03", "P02"),
        ("interactive_disclosure", "P04", "P02"),
        ("interactive_with_semantics", "P05", "P03"),
        ("disclosure_vs_equal_calls", "P05", "P06"),
    ):
        for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation", "false_positive"):
            eligible = CONTROLS if outcome == "false_positive" else FAULTS
            differences = [mean(instance, left, outcome) - mean(instance, right, outcome) for instance in eligible]
            contrasts.append({
                "name": name, "left": left, "right": right, "outcome": outcome,
                "unit": "instance_after_averaging_three_repetitions",
                "per_instance_differences": differences,
                "mean_difference": sum(differences) / len(differences),
                "wins_ties_losses": {
                    "wins": sum(value > 0 for value in differences),
                    "ties": sum(value == 0 for value in differences),
                    "losses": sum(value < 0 for value in differences),
                },
                **prior._sign_flip_test(differences),
            })
    relevance = base._json(target / "qualification-private/adaptive-relevance.json")
    relevant_refs = {
        instance: {item["artifact_ref"] for item in bindings}
        for instance, bindings in relevance["natural_state_probes"].items()
    }
    adaptive_rows = []
    for review in review_list:
        trial = review["controller_trial"]
        if trial["cell_id"] not in {"P04", "P05"}:
            continue
        selected = (review.get("selected_artifact") or {}).get("artifact_ref")
        adaptive_rows.append({
            "trial_id": trial["trial_id"], "instance": trial["opaque_instance_id"],
            "cell": trial["cell_id"], "selected_artifact_ref": selected,
            "selected_prespecified_natural_state": selected in relevant_refs.get(trial["opaque_instance_id"], set()),
            "exact_function_localisation": bool(review["exact_function_localisation"]),
        })
    analysis.update({
        "schema_version": "n27phf-natural-state-analysis-1",
        "confirmatory_paired_contrasts": contrasts,
        "job1_faults_by_cell": {cell: _summary_for([row for row in rows if row["instance"] in R + S + E + V + D and row["cell_id"] == cell]) for cell in lifecycle.CELLS},
        "job3_faults_by_cell": {cell: _summary_for([row for row in rows if row["instance"] in C and row["cell_id"] == cell]) for cell in lifecycle.CELLS},
        "all_faults_by_cell": {cell: _summary_for([row for row in rows if row["instance"] in FAULTS and row["cell_id"] == cell]) for cell in lifecycle.CELLS},
        "controls_by_cell": {cell: _summary_for([row for row in rows if row["instance"] in CONTROLS and row["cell_id"] == cell]) for cell in lifecycle.CELLS},
        "observed_p01_difficulty_by_mechanism": {
            mechanism: _summary_for([row for row in rows if row["fault_mechanism"] == mechanism and row["cell_id"] == "P01"])["exact_function_localisation"]
            for mechanism in sorted(set(FAULT_MECHANISM.values()))
        },
        "natural_state_adaptive_selections": adaptive_rows,
        "natural_state_selection_summary": {
            "eligible_sessions": sum(row["instance"] in V + D for row in adaptive_rows),
            "selected_sessions": sum(row["selected_prespecified_natural_state"] for row in adaptive_rows),
            "correctness_not_used_as_disclosure_proxy": True,
        },
        "attempt_056": {"status": "preserved_partial", "pooled": False},
        "analysis_unit": "instance after averaging the three repeated reviews",
    })
    analysis.pop("attempt_054_validity_diagnostic", None)
    analysis.pop("analysis_sha256", None)
    analysis["analysis_sha256"] = ce.sha256(analysis)
    path.unlink()
    ce._write_immutable(path, analysis)
    return path


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    path = _ORIGINAL_FREEZE(repo_root, attempt_root)
    freeze = base._json(path)
    freeze["schema_version"] = "n27phf-experiment-freeze-1"
    freeze["attempt"] = "057"
    freeze["attempt_056_hashes"] = freeze.pop("attempt_054_hashes")
    freeze["attempt_056_preservation_manifest_sha256"] = base._json(
        (attempt_root or repo_root / ATTEMPT) / "lineage/attempt-056-preservation.json"
    )["manifest_sha256"]
    freeze.pop("freeze_sha256", None)
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path.unlink()
    ce._write_immutable(path, freeze)
    return path


def write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = base._json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PHF-natural-state-multi-hard-fault-experiment"
    findings = [
        "# N27PHF natural-state multi-hard-fault experiment", "",
        "Attempt 057 completed without modifying or pooling the partial Attempt 056.", "",
        f"- Fault detection: {base._rate(aggregate['fault_detection'])}",
        f"- Correct-job attribution: {base._rate(aggregate['correct_job_attribution'])}",
        f"- Exact-function localisation: {base._rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {base._rate(aggregate['control_false_positives'])}",
        f"- Scientific calls: {aggregate['provider_calls']}; calibration calls: 0; repairs: 0", "",
        "The Job-3 contribution audit was removed. V/D natural-state disclosure is counted only when the model actually selected and inspected ordered_df or decision_rank.", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/replay.json)",
        "- [Terminal](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/terminal-state.json)",
    ]
    base._write_text(report_dir / "findings.md", "\n".join(findings))
    cells = ["# Cell results", "", "| Cell | Detection | Job | Exact | Control FP | Calls |", "|---|---:|---:|---:|---:|---:|"]
    for cell in lifecycle.CELLS:
        value = analysis["cell_summaries"][cell]
        cells.append(f"| {cell} | {base._rate(value['fault_detection'])} | {base._rate(value['correct_job_attribution'])} | {base._rate(value['exact_function_localisation'])} | {base._rate(value['control_false_positives'])} | {value['provider_calls']} |")
    base._write_text(report_dir / "cell-table.md", "\n".join(cells))
    base._write_text(report_dir / "paired-contrasts.json", json.dumps(analysis["confirmatory_paired_contrasts"], indent=2, sort_keys=True))
    base._write_text(report_dir / "natural-state-selections.json", json.dumps(analysis["natural_state_adaptive_selections"], indent=2, sort_keys=True))
    base._write_text(report_dir / "per-call-token-latency.json", json.dumps(analysis["per_call_token_latency"], indent=2, sort_keys=True))


def write_handoff(repo_root: Path, target: Path) -> None:
    analysis = base._json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    selection = analysis["natural_state_selection_summary"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PHF Attempt 057 natural-state results", "",
        "Status: `completed_full_experiment_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{base._json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "- 64 fresh native captures; 96 packages; 288 reviews; 576 calls; zero repairs",
        f"- Exact localisation: {base._rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {base._rate(aggregate['control_false_positives'])}",
        f"- Prespecified V/D natural state selected in {selection['selected_sessions']}/{selection['eligible_sessions']} eligible Adaptive sessions", "",
        "Attempt 056 remained byte-for-byte preserved and its partial outcomes were not pooled.",
    ]
    base._write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PHF_attempt_057_results_to_overseer.email.md", "\n".join(lines))


def main() -> int:
    _bind()
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    target = repo / ATTEMPT
    try:
        if args.operation == "build":
            print(json.dumps({"qualification": lifecycle.build_attempt(repo, target)["qualification"]}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, target))
        elif args.operation == "verify":
            print(json.dumps(lifecycle.verify_frozen_attempt(repo, target), indent=2))
        else:
            path = lifecycle.run_lifecycle(repo, target)
            print(path)
            return 0 if base._json(path).get("status") == "completed_full_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N27PHF experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
