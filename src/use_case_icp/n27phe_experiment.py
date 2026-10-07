"""Thin Attempt-056 binding for the hard-rounding confirmation."""

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
from . import n27pb_experiment as pb
from .n27phd_hidden_oracle import compute_clean_result


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-056")
ATTEMPT_055 = Path("outputs/fault-experiments-v2-2-n10/attempt-055")
TASK = Path("instructions_between_agent_types/developer/current/N27PHE_hard_rounding_confirmatory_replication.email.md")
TASK_SHA256 = "sha256:82e4b0df5db5afeb55b7f2d688e9772e56635db4aad74999280c07745abc4437"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PHE_hard_rounding_confirmatory_replication_authorization.json")
AUTHORITY_SHA256 = "sha256:cc3045b636d4ac79147441a61b640dbfa2323dcb10b5f32b96eb9603d3f42df9"

JOB1_SOURCE = Path("src/use_case_icp/n27phe_market_evidence.py")
JOB2_SOURCE = base.JOB2_SOURCE
JOB3_SOURCE = base.JOB3_SOURCE
JOB4_SOURCE = base.JOB4_SOURCE
ORACLE_SOURCE = Path("src/use_case_icp/n27phd_hidden_oracle.py")
JOB_ORDER = base.JOB_ORDER
JOB1, JOB2, JOB3, JOB4 = JOB_ORDER
JOB_SOURCES = {JOB1: JOB1_SOURCE, JOB2: JOB2_SOURCE, JOB3: JOB3_SOURCE, JOB4: JOB4_SOURCE}

CONTROLS = ("case-harbor", "case-juniper", "case-lantern", "case-meadow")
FAULTS = (
    "case-amber", "case-brook", "case-canvas", "case-drift", "case-finch", "case-grove",
    "case-heather", "case-ivory", "case-kestrel", "case-lilac", "case-mosaic", "case-nimbus",
)
INSTANCES = CONTROLS + FAULTS
TRUTH = {**{item: None for item in CONTROLS}, **{item: "weight_source_reliability" for item in FAULTS}}
FAULT_MECHANISM = {item: "premature_contribution_rounding" for item in FAULTS}
DIFFICULTY = {item: "hard_data_dependent" for item in FAULTS}
MATCHED_CLEAN = {item: CONTROLS[index % len(CONTROLS)] for index, item in enumerate(FAULTS)}
MUTATION = (
    "aggregation_contribution = raw_contribution",
    'aggregation_contribution = raw_contribution.round(int(planning_policy["display_precision"]))',
)
MUTATIONS = {item: MUTATION for item in FAULTS}
SCHEDULE_SEED = 560916271

PRESERVED_HASHES = {
    "terminal-state.json": "sha256:721729661af1a335268cea7ed9caf60fba993f40dff27afb17f3759f3610d87f",
    "experiment-freeze.json": "sha256:b74b1678a69a1f48ab63852df154029156d9e8db7e66f0491a46e89752a36c2d",
    "replay.json": "sha256:f148331157356cfacb042e9294fa784f9a241fd6c3bf0a3272a66f803d91cceb",
    "analysis/summary.json": "sha256:e6ae4871759e6b4011f1e3615f0131a76f1a51b203d573843a7932975b98f50a",
}
REUSED_HASHES = {
    "src/use_case_icp/n27phb_experiment.py": "sha256:b70767f31d637b781835f5cdd5aa8760ecc74fe19e636fb2a1a451d1ff60fb6e",
    "src/use_case_icp/n27phd_experiment.py": "sha256:feb098ce5fef38235aa91adafe61b6fb45986bc7fb12c8cdb222df3389866a48",
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

_ORIGINAL_QUALIFY_PACKAGES = lifecycle.qualify_packages
_ORIGINAL_FREEZE = lifecycle.freeze_attempt
_ORIGINAL_WRITE_ANALYSIS = lifecycle.write_analysis


def input_for(instance: str) -> dict[str, Any]:
    if instance not in INSTANCES:
        raise KeyError(instance)
    index = INSTANCES.index(instance)
    prefix = f"market-{index + 1:02d}"
    desired_rows = (5, 8, 11, 14)[index] if instance in CONTROLS else 4 + FAULTS.index(instance)
    root = base._fixture(prefix, ("a", "b", "c")[index % 3], stressed=index % 2 == 1)

    threshold = f"{prefix}-opportunity-threshold"
    root["market_observations"] = [row for row in root["market_observations"] if row["opportunity_id"] != threshold]
    used_sources = {row["source_id"] for row in root["market_observations"]}
    root["source_reliability"] = [row for row in root["source_reliability"] if row["source_id"] in used_sources]
    root["commercial_context"] = [row for row in root["commercial_context"] if row["opportunity_id"] != threshold]

    for extra in range(desired_rows - 4):
        stable = (extra + index) % 2 == 0
        suffix = f"additional-{extra + 1:02d}"
        opportunity = "opportunity-stable" if stable else "opportunity-temporal"
        segment = "north" if stable else "south"
        campaign = "campaign-alpha" if stable else "campaign-beta"
        channel = "email" if stable else "social"
        evidence = 0.137 + 0.019 * ((extra * 3 + index) % 17) + 0.0007 * index
        reliability = 0.61 + 0.021 * ((extra * 5 + index) % 15)
        root["market_observations"].append(base._observation(
            prefix, suffix, opportunity, f"source-{suffix}", segment, campaign, channel,
            f"2026-08-{10 + (extra % 14):02d}", f"2026-08-{11 + (extra % 14):02d}T09:00:00",
            evidence, 184000 + 1100 * index if stable else 158000 + 900 * index,
        ))
        root["source_reliability"].append({
            "source_id": f"{prefix}-source-{suffix}", "segment": segment, "reliability": reliability,
        })
    shift = index % len(root["market_observations"])
    root["market_observations"] = root["market_observations"][shift:] + root["market_observations"][:shift]
    return deepcopy(root)


def _mutant_source(clean: str, instance: str) -> tuple[str, dict[str, Any] | None]:
    if instance in CONTROLS:
        return clean, None
    old, new = MUTATION
    if clean.count(old) != 1:
        raise ValueError(f"mutation site is not unique: {instance}")
    mutated = clean.replace(old, new, 1)
    if ast.dump(ast.parse(clean)) == ast.dump(ast.parse(mutated)):
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


def _nonnumeric(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _nonnumeric(item) for key, item in value.items() if not key.endswith("sha256")}
    if isinstance(value, list):
        return [_nonnumeric(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return "<number>"
    return value


def _outputs_equal(left: Any, right: Any) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_outputs_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_outputs_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-12
    return left == right


def _weighted_rows(root: Mapping[str, Any], rounded: bool) -> list[dict[str, Any]]:
    snapshot = root["planning_policy"]["as_of_date"]
    usable = [
        row for row in root["market_observations"]
        if row["effective_date"] <= snapshot and row["recorded_at"][:10] <= snapshot <= row["valid_until"]
    ]
    basis = root["repeat_resolution_policy"]["basis"]
    survivors: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in usable:
        key = (row["opportunity_id"], row["source_id"])
        if key not in survivors or row[basis] > survivors[key][basis]:
            survivors[key] = row
    reliability = {(row["source_id"], row["segment"]): float(row["reliability"]) for row in root["source_reliability"]}
    rows = []
    for row in survivors.values():
        raw = float(row["evidence_value"]) * reliability[(row["source_id"], row["segment"])]
        selected = round(raw, int(root["planning_policy"]["display_precision"])) if rounded else raw
        rows.append({
            **{key: row[key] for key in ("contribution_id", "opportunity_id", "source_id", "segment", "campaign_id", "effective_date", "recorded_at")},
            "evidence_value": float(row["evidence_value"]), "reliability": reliability[(row["source_id"], row["segment"])],
            "weighted_contribution": selected,
        })
    return rows


def _private_qualification(repo_root: Path, target: Path) -> dict[str, Any]:
    path = target / "qualification-private/qualification-summary.json"
    if path.exists():
        record = base._json(path)
        ce._verified_self_hash(record, "qualification_sha256")
        return record
    clean_source = (repo_root / JOB1_SOURCE).read_text()
    controls: dict[str, str] = {}
    faults: dict[str, str] = {}
    for instance in INSTANCES:
        root = input_for(instance)
        clean = lifecycle._oracle_jobs(root)
        source, mutation = _mutant_source(clean_source, instance)
        actual = lifecycle._run_pipeline_sources(repo_root, root, source)["outputs"]
        expected_rows = _weighted_rows(root, instance in FAULTS)
        if int(actual[JOB1]["metadata"]["weighted_count"]) != len(expected_rows):
            raise ValueError(f"retained contribution count differs: {instance}")
        if instance in CONTROLS:
            if not _outputs_equal(actual, clean):
                raise ValueError(f"control differs from independent oracle: {instance}")
        else:
            if ce.canonical_json(actual[JOB4]) == ce.canonical_json(clean[JOB4]):
                raise ValueError(f"fault has no Job-4 numerical effect: {instance}")
            if _nonnumeric(actual) != _nonnumeric(clean):
                raise ValueError(f"fault changed business identity, order or categorical output: {instance}")
            clean_budget = float(clean[JOB4]["activation_plan"]["aggregate_forecast"]["scheduled_budget"])
            fault_budget = float(actual[JOB4]["activation_plan"]["aggregate_forecast"]["scheduled_budget"])
            if not 0 < abs(clean_budget - fault_budget) < max(500.0, clean_budget * 0.01):
                raise ValueError(f"Job-4 effect is not small and nonzero: {instance}")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in expected_rows:
            grouped.setdefault(row["opportunity_id"], []).append(row)
        affected = []
        for opportunity, rows in grouped.items():
            raw = [float(row["evidence_value"]) * float(row["reliability"]) for row in rows]
            rounded = [round(value, int(root["planning_policy"]["display_precision"])) for value in raw]
            if len(rows) >= 2 and abs(sum(raw) - sum(rounded)) > 1e-12:
                affected.append({
                    "opportunity_id": opportunity, "row_count": len(rows),
                    "full_precision_sum": sum(raw), "sum_of_rounded": sum(rounded),
                })
        if not affected:
            raise ValueError(f"case lacks the prescribed numerical edge: {instance}")
        record = {
            "schema_version": "n27phe-private-case-1", "instance": instance,
            "designation": "clean_control" if instance in CONTROLS else "fault",
            "retained_contribution_rows": len(expected_rows), "affected_aggregates": affected,
            "mutation": mutation, "clean_outputs": clean, "executed_outputs": actual,
            "categorical_identity_order_shape_preserved": True,
            "small_nonzero_job4_numeric_effect": instance in FAULTS,
        }
        record["record_sha256"] = ce.sha256(record)
        folder = "controls" if instance in CONTROLS else "faults"
        ce._write_immutable(target / "qualification-private" / folder / f"{instance}.json", record)
        (controls if instance in CONTROLS else faults)[instance] = record["record_sha256"]
    summary = {
        "schema_version": "n27phe-private-deterministic-qualification-1", "status": "passed",
        "model_calls": 0, "fault_mechanisms": 1, "fault_data_instances": 12,
        "clean_controls": 4, "one_site_faults": 12, "controls": controls, "faults": faults,
        "retained_row_range": [4, 15], "categorical_outputs_preserved": True,
        "job_source_sha256": {path.as_posix(): base._file_sha(repo_root / path) for path in JOB_SOURCES.values()},
    }
    summary["qualification_sha256"] = ce.sha256(summary)
    ce._write_immutable(path, summary)
    return summary


def adaptive_relevance(prepared: Mapping[str, Any], target: Path) -> dict[str, Any]:
    context = dict(prepared) | {"attempt_root": target}
    cases = {}
    for instance in INSTANCES:
        binding = base._artifact_for_state(context, instance, JOB1, "weighted_df")
        compact = base._json(target / "projections" / f"{instance}-compact.json")
        _, event = pb.expand_native_subtree(
            prepared["catalogues"][instance], prepared["reviewer_nodes"][instance],
            prepared["indexes"][instance], {"graph_review": {"evidence": compact}},
            binding["execution_group_id"],
        )
        if binding["artifact_ref"] not in event["newly_disclosed_artifact_refs"]:
            raise ValueError(f"weighted_df is not reachable: {instance}")
        cases[instance] = {
            "truth_function": TRUTH[instance], "fault_mechanism": FAULT_MECHANISM.get(instance),
            "decisive_state_name": "weighted_df", **binding, "initially_hidden": True,
            "one_expansion_reachable": True, "one_inspection_reachable": True,
        }
    record = {
        "schema_version": "n27phe-adaptive-relevance-1", "status": "passed",
        "faults": {instance: cases[instance] for instance in FAULTS}, "controls": {instance: cases[instance] for instance in CONTROLS},
        "weighted_df_cases": 16, "function_name_matching_alone_used": False,
    }
    record["qualification_sha256"] = ce.sha256(record)
    return record


def weighted_df_qualification(prepared: Mapping[str, Any], target: Path) -> dict[str, Any]:
    context = dict(prepared) | {"attempt_root": target}
    cases = {}
    for instance in INSTANCES:
        binding = base._artifact_for_state(context, instance, JOB1, "weighted_df")
        content = prepared["disclosures"][instance]["artifacts"][binding["artifact_ref"]]["operation_node"]["artifact_content"]
        actual = content["rows"]
        expected = _weighted_rows(input_for(instance), instance in FAULTS)
        actual_by_id = {str(row["contribution_id"]): row for row in actual}
        if set(actual_by_id) != {row["contribution_id"] for row in expected}:
            raise ValueError(f"weighted_df row identities differ: {instance}")
        for row in expected:
            observed = actual_by_id[row["contribution_id"]]
            for key, value in row.items():
                if isinstance(value, float):
                    if abs(float(observed[key]) - value) > 1e-12:
                        raise ValueError(f"weighted_df numeric mismatch: {instance}/{row['contribution_id']}/{key}")
                elif observed[key] != value:
                    raise ValueError(f"weighted_df value mismatch: {instance}/{row['contribution_id']}/{key}")
        cases[instance] = {
            "artifact_ref": binding["artifact_ref"], "execution_group_id": binding["execution_group_id"],
            "rows": len(actual), "independent_exact_recomputation_match": True,
            "actual_downstream_column_only": True,
        }
    record = {
        "schema_version": "n27phe-weighted-df-qualification-1", "status": "passed",
        "cases": cases, "case_count": 16, "state_comparisons": 16, "model_calls": 0,
        "purpose_built_diagnostic_tables": [],
    }
    record["qualification_sha256"] = ce.sha256(record)
    return record


def qualify_packages(repo_root: Path, target: Path, records: list[Mapping[str, Any]],
                     prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_QUALIFY_PACKAGES(repo_root, target, records, prepared, design)
    prohibited = ("contribution_precision_df", "eligibility_decision_df", "snapshot_decision_df")
    for record in records:
        rendered = (repo_root / lifecycle.PROMPT).read_text() + json.dumps(
            lifecycle.render_request(record["reviewer_package"]), ensure_ascii=False, sort_keys=True
        )
        if any(name in rendered for name in prohibited):
            raise ValueError("rendered package contains a purpose-built diagnostic table")
        lowered = rendered.lower()
        if any(phrase in lowered for phrase in ("expected defect is rounding", "correct aggregation order", "rounding is the defect")):
            raise ValueError("rendered package names the expected defect")
    result["attempt_055_preservation_verified"] = True
    result["weighted_df_qualification_sha256"] = base._json(
        target / "qualification-private/truthful-witnesses.json"
    )["qualification_sha256"]
    result["purpose_built_diagnostic_table_count"] = 0
    return result


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27phe_experiment.py"), JOB1_SOURCE,
        Path("tests/test_n27phe_experiment.py"),
    )


def _bind() -> None:
    values = {
        "ATTEMPT": ATTEMPT, "ATTEMPT_054": ATTEMPT_055, "TASK": TASK, "TASK_SHA256": TASK_SHA256,
        "AUTHORITY": AUTHORITY, "AUTHORITY_SHA256": AUTHORITY_SHA256,
        "JOB1_SOURCE": JOB1_SOURCE, "JOB2_SOURCE": JOB2_SOURCE, "JOB3_SOURCE": JOB3_SOURCE,
        "JOB4_SOURCE": JOB4_SOURCE, "ORACLE_SOURCE": ORACLE_SOURCE, "JOB_SOURCES": JOB_SOURCES,
        "CONTROLS": CONTROLS, "H1": (), "H2": (), "H3": (), "H4": FAULTS,
        "INSTANCES": INSTANCES, "TRUTH": TRUTH, "FAULT_MECHANISM": FAULT_MECHANISM,
        "DIFFICULTY": DIFFICULTY, "MATCHED_CLEAN": MATCHED_CLEAN, "MUTATIONS": MUTATIONS,
        "SCHEDULE_SEED": SCHEDULE_SEED, "PRESERVED_HASHES": PRESERVED_HASHES,
        "REUSED_HASHES": REUSED_HASHES,
        "input_for": input_for, "_mutant_source": _mutant_source,
        "_deterministic_private_qualification": _private_qualification,
        "adaptive_relevance": adaptive_relevance, "truthful_witness_qualification": weighted_df_qualification,
        "qualify_packages": qualify_packages, "_code_paths": _code_paths,
    }
    for name, value in values.items():
        setattr(lifecycle, name, value)
    lifecycle.write_analysis = write_analysis
    lifecycle._write_reports = write_reports
    lifecycle._write_handoff = write_handoff
    lifecycle.freeze_attempt = freeze_attempt


def _sign_flip_test(differences: list[float]) -> dict[str, Any]:
    observed = abs(sum(differences) / len(differences))
    distribution = []
    for mask in range(1 << len(differences)):
        distribution.append(sum(value if mask & (1 << index) else -value for index, value in enumerate(differences)) / len(differences))
    ordered = sorted(distribution)
    p_value = sum(abs(value) >= observed - 1e-15 for value in distribution) / len(distribution)
    return {
        "method": "exact_paired_sign_flip_randomization", "assignments": len(distribution),
        "two_sided_p_value": p_value,
        "randomization_interval_95": [ordered[int(0.025 * (len(ordered) - 1))], ordered[int(0.975 * (len(ordered) - 1))]],
    }


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    review_list = list(reviews)
    path = _ORIGINAL_WRITE_ANALYSIS(target, review_list)
    analysis = base._json(path)
    contrasts = []
    for name, left, right in (
        ("primary_adaptive_semantics_vs_source", "P05", "P01"),
        ("adaptive_semantics_vs_equal_call", "P05", "P06"),
        ("adaptive_semantics_vs_static_graph", "P05", "P02"),
        ("adaptive_without_semantics_vs_static_graph", "P04", "P02"),
    ):
        for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation"):
            differences = []
            for instance in FAULTS:
                def mean(cell: str) -> float:
                    values = [
                        float(row[outcome]) for row in lifecycle._analysis_rows(review_list)
                        if row["instance"] == instance and row["cell_id"] == cell
                    ]
                    return sum(values) / len(values)
                differences.append(mean(left) - mean(right))
            contrasts.append({
                "name": name, "left": left, "right": right, "outcome": outcome,
                "unit": "fault_instance_after_averaging_three_repetitions",
                "per_instance_differences": differences,
                "mean_difference": sum(differences) / len(differences),
                "wins_ties_losses": {
                    "wins": sum(value > 0 for value in differences), "ties": sum(value == 0 for value in differences),
                    "losses": sum(value < 0 for value in differences),
                },
                **_sign_flip_test(differences),
            })
    adaptive = [review for review in review_list if review["controller_trial"]["cell_id"] in {"P04", "P05"}]
    analysis["confirmatory_paired_contrasts"] = contrasts
    analysis["weighted_df_adaptive_selection"] = {
        "adaptive_sessions": len(adaptive),
        "selected_weighted_df_group": sum(bool(review["selected_group_contained_truth_state"]) for review in adaptive),
        "inspected_weighted_df_artifact": sum(bool(review["selected_artifact_was_truth_state"]) for review in adaptive),
        "causal_claim_from_correctness_prohibited": True,
    }
    analysis["attempt_055_descriptive_comparison_only"] = {
        "pooled": False,
        "attempt_055_exact_by_cell": base._json(target.parent / "attempt-055/analysis/summary.json")["attempt_054_validity_diagnostic"]["attempt_055_exact_by_cell"],
        "attempt_056_exact_by_cell": {cell: analysis["cell_summaries"][cell]["exact_function_localisation"] for cell in lifecycle.CELLS},
    }
    analysis["schema_version"] = "n27phe-confirmatory-analysis-1"
    analysis.pop("analysis_sha256", None)
    analysis["analysis_sha256"] = ce.sha256(analysis)
    path.unlink()
    ce._write_immutable(path, analysis)
    return path


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    path = _ORIGINAL_FREEZE(repo_root, attempt_root)
    freeze = base._json(path)
    freeze["schema_version"] = "n27phe-experiment-freeze-1"
    freeze["attempt"] = "056"
    freeze["attempt_055_hashes"] = freeze.pop("attempt_054_hashes")
    freeze.pop("freeze_sha256", None)
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path.unlink()
    ce._write_immutable(path, freeze)
    return path


def write_reports(repo_root: Path, target: Path, reviews: list[Mapping[str, Any]]) -> None:
    analysis = base._json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    report_dir = repo_root / "docs/workshops/ICLR/N27PHE-hard-rounding-confirmatory-replication"
    findings = [
        "# N27PHE hard-rounding confirmatory replication", "",
        "Attempt 056 completed the reuse-first sixteen-instance confirmation without pooling Attempt 055.", "",
        f"- Fault detection: {base._rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {base._rate(aggregate['correct_job_attribution'])}",
        f"- Exact-function localisation: {base._rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {base._rate(aggregate['control_false_positives'])}",
        f"- Scientific calls: {aggregate['provider_calls']}; calibration calls: 0; repairs: 0", "",
        "Every arm received byte-identical complete source and top-level I/O for all four jobs. The naturally downstream-used weighted_df was the only decisive Job-1 runtime table.", "",
        "## Records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-056/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-056/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-056/replay.json)",
        "- [Terminal](../../../../outputs/fault-experiments-v2-2-n10/attempt-056/terminal-state.json)",
    ]
    base._write_text(report_dir / "findings.md", "\n".join(findings))
    rows = ["# Cell results", "", "| Cell | Detection | Job 1 | Exact | Control FP | Calls |", "|---|---:|---:|---:|---:|---:|"]
    for cell in lifecycle.CELLS:
        value = analysis["cell_summaries"][cell]
        rows.append(f"| {cell} | {base._rate(value['fault_detection'])} | {base._rate(value['correct_job_attribution'])} | {base._rate(value['exact_function_localisation'])} | {base._rate(value['control_false_positives'])} | {value['provider_calls']} |")
    base._write_text(report_dir / "cell-table.md", "\n".join(rows))
    base._write_text(report_dir / "confirmatory-paired-contrasts.json", json.dumps(analysis["confirmatory_paired_contrasts"], indent=2, sort_keys=True))
    base._write_text(report_dir / "per-call-token-latency.json", json.dumps(analysis["per_call_token_latency"], indent=2, sort_keys=True))
    operations = ["# Adaptive selections", "", "| Trial | Cell | Group | Artifact | weighted_df group | weighted_df artifact |", "|---|---|---|---|---|---|"]
    for review in sorted(reviews, key=lambda row: row["controller_trial"]["schedule_position"]):
        if review["controller_trial"]["cell_id"] not in {"P04", "P05"}:
            continue
        group, artifact = review.get("selected_group") or {}, review.get("selected_artifact") or {}
        operations.append(f"| {review['controller_trial']['trial_id']} | {review['controller_trial']['cell_id']} | {group.get('execution_group_id', '')} | {artifact.get('artifact_ref', '')} | {review['selected_group_contained_truth_state']} | {review['selected_artifact_was_truth_state']} |")
    base._write_text(report_dir / "adaptive-selections.md", "\n".join(operations))


def write_handoff(repo_root: Path, target: Path) -> None:
    analysis = base._json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    selected = analysis["weighted_df_adaptive_selection"]
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PHE Attempt 056 hard-rounding confirmation results", "",
        "Status: `completed_full_experiment_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{base._json(target / 'experiment-freeze.json')['freeze_sha256']}`", "",
        "- 64 fresh native Etiq captures; 96 packages; 288 reviews; 576 calls; zero repairs",
        f"- Exact localisation: {base._rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {base._rate(aggregate['control_false_positives'])}",
        f"- weighted_df selected and inspected in {selected['inspected_weighted_df_artifact']}/{selected['adaptive_sessions']} Adaptive sessions", "",
        "Attempt 055 and every protected/reused component remained unchanged; results were not pooled.",
    ]
    base._write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27PHE_attempt_056_results_to_overseer.email.md", "\n".join(lines))


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
        print(f"N27PHE experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
