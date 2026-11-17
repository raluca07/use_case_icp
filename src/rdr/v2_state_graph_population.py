"""Fresh, frozen 42-instance population for the two state-graph conditions."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from rdr.freeze import verify_manifest, write_manifest
from rdr.v2_dry_run import _clean_fixture_variants, _clean_truth, _truth
from rdr.v2_etiq_export import (
    STATE_GRAPH_CONDITIONS,
    audit_state_graph_conditions,
    build_state_graph_conditions,
)
from rdr.v2_faults import (
    FAULT_SPECS,
    _action_plan,
    _repair_plan_for,
    _runtime_plan,
    mutate_source,
    qualify_faults,
)
from rdr.v2_feasibility import normalize_trace_value
from rdr.v2_live import run_fresh_cell
from rdr.v2_pipeline import validate_execution_pair
from rdr.v2_provenance import verify_current_code_snapshot
from rdr.v2_schema import TraceV2, save_v2
from rdr.v2_state_graph_smoke import (
    DEFAULT_ETIQ_PYTHON,
    DEFAULT_SOURCE,
    _capture_etiq,
    _private_values,
    validate_task_state_snapshot,
)


ADMITTED_FAULTS = ("L01", "S01", "S04", "R11", "R15", "M02", "I06", "A01")
V8R11_ROOT = Path("runs/v2/build-v8r11-complete-etiq-20261114")
DATASET_SOURCE = Path("fixtures/v2/reference_solution.py")
SCHEDULE_SEED = 20261116
CONTEXT_BUDGET_TOKENS = 200_000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _validate_v8r11_population(v8r11_root: Path) -> dict[str, str]:
    problems = verify_manifest(v8r11_root)
    if problems:
        raise ValueError(f"V8R11 manifest failed: {problems[:5]}")
    mapping = json.loads((v8r11_root / "private/instance_map.json").read_text())
    expected = {
        *(f"live-{author}-{fault_id}-{repair}"
          for author in ("codex", "dataset")
          for fault_id in ADMITTED_FAULTS
          for repair in ("unrepaired", "repaired")),
        *(f"clean-{author}-{index:02d}"
          for author in ("codex", "dataset") for index in range(1, 6)),
    }
    if len(mapping) != 42 or set(mapping.values()) != expected:
        raise ValueError("V8R11 logical population is not the predeclared 42-instance population")
    return {logical: public for public, logical in mapping.items()}


def qualify_state_graph_population(
    output_root: Path,
    code_provenance: Path,
    source_path: Path = DEFAULT_SOURCE,
) -> dict[str, Any]:
    """Re-run qualification for the eight predeclared faults under the frozen code."""
    if output_root.exists():
        raise FileExistsError(output_root)
    problems = verify_current_code_snapshot(code_provenance)
    if problems:
        raise ValueError(f"current code differs from frozen provenance: {problems[:5]}")
    output_root.mkdir(parents=True)
    try:
        source = source_path.read_text()
        records = qualify_faults(source, output_root, "codex", set(ADMITTED_FAULTS))
        admitted = [record for record in records if record.get("admitted") == 1]
        if [record["fault_id"] for record in admitted] != list(ADMITTED_FAULTS):
            raise ValueError(
                "fresh qualification did not admit exactly the predeclared eight faults: "
                + repr([(record["fault_id"], record["status"], record["admitted"])
                        for record in records])
            )
        for record in records:
            if record.get("inferred_classification") != FAULT_SPECS[record["fault_id"]].fault_class:
                raise ValueError(f"{record['fault_id']}: measured class differs from executable fault spec")
        code_record = json.loads((code_provenance / "code_provenance.json").read_text())
        _write_json(output_root / "qualification.json", records)
        summary = {
            "schema_version": 1,
            "qualification_kind": "fresh_state_graph_population",
            "fault_ids": list(ADMITTED_FAULTS),
            "admitted": len(admitted),
            "blocked": sum(record["status"] == "blocked" for record in records),
            "reviewer_calls": 0,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "code_snapshot_id": code_record["snapshot_id"],
            "code_provenance": str(code_provenance),
            "code_provenance_manifest_sha256": _sha(code_provenance / "MANIFEST.sha256.json"),
            "fresh_appworld_cells": sum(
                sum(name != "pair_validation" for name in record.get("cells", {}))
                if record.get("cells") else record["attempted"]
                for record in records
            ),
        }
        _write_json(output_root / "qualification_summary.json", summary)
        _write_json(output_root / "qualification_provenance.json", {
            "schema_version": 1,
            "created_by": "rdr.v2_state_graph_population.qualify_state_graph_population",
            "fresh_execution": True,
            "copied_or_relabelled_qualification": False,
            "code_snapshot_id": code_record["snapshot_id"],
            "code_provenance": str(code_provenance),
            "code_provenance_manifest_sha256": _sha(code_provenance / "MANIFEST.sha256.json"),
            "qualification_sha256": _sha(output_root / "qualification.json"),
        })
        write_manifest(output_root)
        return summary
    except Exception as error:
        _write_json(output_root / "qualification_failure.json", {
            "status": "blocked", "error_type": type(error).__name__, "reason": str(error),
            "manifest_written": False,
        })
        raise


def verify_population_qualification(root: Path, code_provenance: Path) -> list[dict[str, Any]]:
    problems = verify_manifest(root)
    if problems:
        raise ValueError(f"qualification manifest failed: {problems[:5]}")
    provenance = json.loads((root / "qualification_provenance.json").read_text())
    code = json.loads((code_provenance / "code_provenance.json").read_text())
    if provenance.get("code_snapshot_id") != code.get("snapshot_id"):
        raise ValueError("qualification and executable provenance snapshots differ")
    if provenance.get("code_provenance_manifest_sha256") != _sha(
        code_provenance / "MANIFEST.sha256.json"
    ):
        raise ValueError("qualification is bound to a different provenance manifest")
    records = json.loads((root / "qualification.json").read_text())
    admitted = [record for record in records if record.get("admitted") == 1]
    if [record["fault_id"] for record in admitted] != list(ADMITTED_FAULTS):
        raise ValueError("qualification does not admit exactly the frozen fault population")
    return records


def _fresh_pair(
    source: str, author: str, fault_id: str, timeout_seconds: int,
) -> tuple[dict, dict, list[str], dict]:
    clean = run_fresh_cell(source, author, timeout_seconds=timeout_seconds)
    spec = FAULT_SPECS[fault_id]
    faulty_source, locations = source, []
    if spec.fault_class in {"source", "mixed", "interaction", "amplified"}:
        faulty_source, location = mutate_source(source, fault_id)
        locations.append(location)
    if spec.fault_class == "action":
        unrepaired_plan = _action_plan(fault_id, clean)
    elif spec.fault_class == "source":
        unrepaired_plan = None
    else:
        unrepaired_plan = _runtime_plan(fault_id, clean)
    unrepaired = run_fresh_cell(
        faulty_source, author, unrepaired_plan, timeout_seconds=timeout_seconds
    )
    repaired = run_fresh_cell(
        faulty_source, author, _repair_plan_for(fault_id, clean),
        timeout_seconds=timeout_seconds,
    )
    return unrepaired, repaired, locations, clean


def _fresh_pair_job(
    job: tuple[str, str, str], timeout_seconds: int,
) -> tuple[str, str, str, tuple[dict, dict, list[str], dict]]:
    author, source, fault_id = job
    return author, source, fault_id, _fresh_pair(source, author, fault_id, timeout_seconds)


def _normalized_trace(trace: dict[str, Any]) -> tuple[dict[str, Any], str]:
    normalized = normalize_trace_value(trace)
    return normalized, _json_sha(normalized)


def freeze_state_graph_schedule(
    inventory: list[dict[str, Any]], seed: int = SCHEDULE_SEED,
) -> dict[str, Any]:
    by_instance: dict[str, dict[str, dict[str, Any]]] = {}
    for row in inventory:
        by_instance.setdefault(row["instance_id"], {})[row["arm"]] = row
    if len(by_instance) != 42 or any(set(arms) != set(STATE_GRAPH_CONDITIONS)
                                     for arms in by_instance.values()):
        raise ValueError("schedule requires 42 instances with both state-graph arms")
    instances = sorted(by_instance)
    random.Random(seed).shuffle(instances)
    jobs = []
    first_arm_counts = {arm: 0 for arm in STATE_GRAPH_CONDITIONS}
    for pair_position, instance_id in enumerate(instances):
        arms = list(STATE_GRAPH_CONDITIONS)
        if pair_position % 2:
            arms.reverse()
        first_arm_counts[arms[0]] += 1
        for arm_position, arm in enumerate(arms):
            row = by_instance[instance_id][arm]
            jobs.append({
                "position": len(jobs),
                "pair_position": pair_position,
                "arm_position": arm_position,
                "instance_id": instance_id,
                "arm": arm,
                "package_sha256": row["package_sha256"],
            })
    return {
        "schema_version": 1,
        "seed": seed,
        "selected_before_reviewer_outputs": True,
        "population_instances": 42,
        "jobs": jobs,
        "first_arm_counts": first_arm_counts,
        "conditions": list(STATE_GRAPH_CONDITIONS),
    }


def _public_inventory(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    private = {
        "logical_instance", "status", "fault_id", "fault_class", "repair", "author",
        "fault_occurred", "residual_harm_present", "trace_sha256", "source_sha256",
    }
    return [{key: value for key, value in row.items() if key not in private} for row in inventory]


def _package_for_instance(
    output_root: Path,
    item: dict[str, Any],
    etiq_python: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    instance_id, result = item["instance_id"], item["result"]
    trace = TraceV2.from_dict(result["trace"])
    etiq, qualification = _capture_etiq(output_root, instance_id, result, etiq_python)
    graph_root = output_root / "private/graphs" / instance_id
    _write_json(graph_root / "etiq_native.json", etiq)
    packages = build_state_graph_conditions(
        trace,
        result["execution_graph"],
        etiq,
        item["initial_task_state"],
        item["final_task_state"],
    )
    audit = audit_state_graph_conditions(packages, _private_values(result["trace"]))
    if not audit["passed"]:
        raise ValueError(f"{instance_id}: state-graph package isolation failed")
    package_root = output_root / "public/instances" / instance_id / "packages"
    package_root.mkdir(parents=True)
    rows = []
    for package in packages:
        path = package_root / f"{package.arm}.txt"
        path.write_text(package.text)
        if package.metadata["tokens"] > CONTEXT_BUDGET_TOKENS:
            raise ValueError(f"{instance_id}/{package.arm}: package exceeds context budget")
        rows.append({
            "instance_id": instance_id,
            "logical_instance": item["logical_instance"],
            "status": item["status"],
            "fault_id": item["truth"].fault_id,
            "fault_class": item["truth"].fault_class,
            "repair": item["truth"].repair,
            "author": item["truth"].author,
            "fault_occurred": item["truth"].fault_occurred,
            "residual_harm_present": item["truth"].residual_harm_present,
            "trace_sha256": item["truth"].trace_sha256,
            "source_sha256": item["truth"].source_sha256,
            "arm": package.arm,
            **package.metadata,
        })
    return rows, {
        "instance_id": instance_id,
        "repeatability": f"private/etiq/{instance_id}/qualification/repeatability.json",
        "source_binding": f"private/etiq/{instance_id}/qualification/source-binding.json",
        "run_1_manifest": f"private/etiq/{instance_id}/run-1/MANIFEST.sha256.json",
        "run_2_manifest": f"private/etiq/{instance_id}/run-2/MANIFEST.sha256.json",
        "eligible": qualification["workflow_only_eligibility"]["status"] == "eligible",
        "package_isolation": audit,
    }


def build_state_graph_population(
    output_root: Path,
    code_provenance: Path,
    qualification_root: Path,
    v8r11_root: Path = V8R11_ROOT,
    codex_source_path: Path = DEFAULT_SOURCE,
    dataset_source_path: Path = DATASET_SOURCE,
    workers: int = 4,
    timeout_seconds: int = 180,
    etiq_python: Path = DEFAULT_ETIQ_PYTHON,
) -> dict[str, Any]:
    """Execute and freeze the V8R11 logical population with state snapshots and native Etiq."""
    if output_root.exists():
        raise FileExistsError(output_root)
    problems = verify_current_code_snapshot(code_provenance)
    if problems:
        raise ValueError(f"current code differs from frozen provenance: {problems[:5]}")
    qualification = verify_population_qualification(qualification_root, code_provenance)
    old_public_ids = _validate_v8r11_population(v8r11_root)
    class_by_fault = {
        record["fault_id"]: record["inferred_classification"]
        for record in qualification if record["admitted"] == 1
    }
    sources = {
        "codex": codex_source_path.read_text(),
        "dataset": dataset_source_path.read_text(),
    }
    output_root.mkdir(parents=True)
    try:
        pair_jobs = [
            (author, sources[author], fault_id)
            for author in ("codex", "dataset") for fault_id in ADMITTED_FAULTS
        ]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pair_results = list(pool.map(
                lambda job: _fresh_pair_job(job, timeout_seconds), pair_jobs
            ))
            clean_jobs = []
            counts = {"codex": 0, "dataset": 0}
            for index, fixture in enumerate(_clean_fixture_variants()):
                author = "codex" if index % 2 == 0 else "dataset"
                counts[author] += 1
                clean_jobs.append((author, counts[author], fixture))
            clean_results = list(pool.map(
                lambda job: (*job, run_fresh_cell(
                    sources[job[0]], job[0], fixture=job[2],
                    timeout_seconds=timeout_seconds,
                )),
                clean_jobs,
            ))

        items: list[dict[str, Any]] = []
        for author, _, fault_id, pair in pair_results:
            unrepaired, repaired, source_locations, clean = pair
            pair_validation = validate_execution_pair(unrepaired, repaired, clean)
            for status, result in (("unrepaired", unrepaired), ("repaired", repaired)):
                logical = f"live-{author}-{fault_id}-{status}"
                truth = _truth(
                    result, logical, fault_id, class_by_fault[fault_id], status,
                    author, source_locations, pair_validation,
                )
                items.append({
                    "instance_id": old_public_ids[logical], "logical_instance": logical,
                    "status": status, "result": result, "truth": truth,
                    "pair_validation": pair_validation,
                })
        for author, number, fixture, result in clean_results:
            logical = f"clean-{author}-{number:02d}"
            truth = _clean_truth(result, logical, author, fixture)
            items.append({
                "instance_id": old_public_ids[logical], "logical_instance": logical,
                "status": "clean", "result": result, "truth": truth,
                "pair_validation": {
                    "kind": "clean_control", "fault_intervention": False,
                    "repair_intervention": False,
                },
            })
        items.sort(key=lambda item: item["instance_id"])
        if len(items) != 42:
            raise ValueError("fresh population does not contain exactly 42 logical instances")

        comparability = []
        for item in items:
            old_trace = json.loads((
                v8r11_root / "private/traces" / f"{item['instance_id']}.json"
            ).read_text())
            old_normalized, old_sha = _normalized_trace(old_trace)
            new_normalized, new_sha = _normalized_trace(item["result"]["trace"])
            comparability.append({
                "instance_id": item["instance_id"],
                "logical_instance": item["logical_instance"],
                "v8r11_normalized_trace_sha256": old_sha,
                "fresh_normalized_trace_sha256": new_sha,
                "matched": old_normalized == new_normalized,
                "normalized_fields": ["access_token", "created_at", "registered_at", "updated_at"],
            })
        _write_json(output_root / "private/v8r11_trace_comparability_audit.json", {
            "schema_version": 1,
            "v8r11_root": str(v8r11_root),
            "v8r11_manifest_sha256": _sha(v8r11_root / "MANIFEST.sha256.json"),
            "matches": sum(row["matched"] for row in comparability),
            "mismatches": sum(not row["matched"] for row in comparability),
            "rows": comparability,
        })
        mismatches = [row for row in comparability if not row["matched"]]
        if mismatches:
            raise ValueError(
                "fresh population is not trace-comparable to V8R11: "
                + repr([row["logical_instance"] for row in mismatches])
            )

        mapping, replay_audit = [], []
        for item in items:
            instance_id, result = item["instance_id"], item["result"]
            initial = validate_task_state_snapshot(result["initial_task_state"])
            final = validate_task_state_snapshot(result["final_task_state"])
            item["initial_task_state"], item["final_task_state"] = initial, final
            private = output_root / "private"
            for directory in (
                private / "traces", private / "truth", private / "snapshots",
                private / "runs" / instance_id, private / "graphs" / instance_id,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            save_v2(TraceV2.from_dict(result["trace"]), private / "traces" / f"{instance_id}.json")
            save_v2(item["truth"], private / "truth" / f"{instance_id}.json")
            _write_json(private / "runs" / instance_id / "run.json", result)
            _write_json(
                private / "runs" / instance_id / "pair_validation.json",
                item["pair_validation"],
            )
            _write_json(private / "snapshots" / f"{instance_id}.json", {
                "schema_version": 1,
                "initial_task_state": initial,
                "final_task_state": final,
                "initial_sha256": _json_sha(initial),
                "final_sha256": _json_sha(final),
                "schema_valid": True,
            })
            _write_json(
                private / "graphs" / instance_id / "appworld_execution.json",
                result["execution_graph"],
            )
            mapping.append({
                "instance_id": instance_id,
                "logical_instance": item["logical_instance"],
                "status": item["status"],
                "fault_id": item["truth"].fault_id,
                "author": item["truth"].author,
            })
            replay_audit.append({
                "instance_id": instance_id,
                "logical_instance": item["logical_instance"],
                "status": item["status"],
                "fresh_root": result["process"]["fresh_root"],
                "process_group_owned": result["process"]["process_group_owned"],
                "returncode": result["process"]["returncode"],
                "snapshot": f"private/snapshots/{instance_id}.json",
                "snapshot_schema_valid": True,
            })
        _write_json(output_root / "private/instance_mapping.json", mapping)
        _write_json(output_root / "private/appworld_snapshot_audit.json", {
            "schema_version": 1,
            "fresh_packaged_replays": 42,
            "fresh_pair_reference_replays": 16,
            "all_snapshot_schemas_valid": True,
            "rows": replay_audit,
        })

        inventory, etiq_audit = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            packaged = list(pool.map(
                lambda item: _package_for_instance(output_root, item, etiq_python), items
            ))
        for rows, audit in packaged:
            inventory.extend(rows)
            etiq_audit.append(audit)
        inventory.sort(key=lambda row: (row["instance_id"], row["arm"]))
        etiq_audit.sort(key=lambda row: row["instance_id"])
        if len(inventory) != 84 or not all(row["eligible"] for row in etiq_audit):
            raise ValueError("full state-graph packaging or Etiq qualification is incomplete")
        _write_json(output_root / "private/package_size_inventory.json", inventory)
        _write_json(output_root / "private/etiq_qualification_audit.json", {
            "schema_version": 1,
            "instances": 42,
            "isolated_scans": 84,
            "eligible": sum(row["eligible"] for row in etiq_audit),
            "reused_capture_pairs": 0,
            "new_capture_pairs": 42,
            "rows": etiq_audit,
        })
        public_inventory = _public_inventory(inventory)
        (output_root / "public/package_manifest.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in public_inventory)
        )
        schedule = freeze_state_graph_schedule(public_inventory)
        _write_json(output_root / "public/state_graph_job_order.json", schedule)
        code = json.loads((code_provenance / "code_provenance.json").read_text())
        build_identity = {
            "schema_version": 1,
            "build_version": output_root.name,
            "code_snapshot_id": code["snapshot_id"],
            "code_provenance": str(code_provenance),
            "code_provenance_manifest_sha256": _sha(code_provenance / "MANIFEST.sha256.json"),
            "qualification_root": str(qualification_root),
            "qualification_manifest_sha256": _sha(qualification_root / "MANIFEST.sha256.json"),
            "v8r11_root": str(v8r11_root),
            "v8r11_manifest_sha256": _sha(v8r11_root / "MANIFEST.sha256.json"),
            "reviewer_model": "gpt-5.6-sol",
            "reasoning_effort": "medium",
            "reviewer_calls": 0,
        }
        _write_json(output_root / "public/build_identity.json", build_identity)
        _write_json(output_root / "private/provenance_binding.json", build_identity)
        summary = {
            "schema_version": 1,
            "instances": 42,
            "clean_controls": 10,
            "unrepaired_instances": 16,
            "repaired_instances": 16,
            "authors": {"codex": 21, "dataset": 21},
            "fault_ids": list(ADMITTED_FAULTS),
            "packages": 84,
            "conditions": list(STATE_GRAPH_CONDITIONS),
            "schedule_jobs": 84,
            "appworld_packaged_replays": 42,
            "appworld_pair_reference_replays": 16,
            "etiq_native_runs": 84,
            "v8r11_trace_matches": 42,
            "v8r11_trace_mismatches": 0,
            "all_package_isolation_passed": True,
            "all_etiq_repeatability_eligible": True,
            "reviewer_calls": 0,
        }
        _write_json(output_root / "summary.json", summary)
        write_manifest(output_root / "public")
        write_manifest(output_root / "private")
        write_manifest(output_root)
        verified = verify_state_graph_population(output_root)
        if verified["instances"] != 42 or verified["packages"] != 84:
            raise ValueError("final population verification differs from the frozen design")
        return summary
    except Exception as error:
        _write_json(output_root / "private/build_failure.json", {
            "status": "blocked", "error_type": type(error).__name__, "reason": str(error),
            "root_manifest_written": False,
        })
        raise


def _verify_schedule(root: Path, inventory: list[dict[str, Any]]) -> dict[str, Any]:
    frozen = json.loads((root / "public/state_graph_job_order.json").read_text())
    expected = freeze_state_graph_schedule(_public_inventory(inventory), frozen.get("seed"))
    if frozen != expected or len(frozen["jobs"]) != 84:
        raise ValueError("frozen state-graph schedule differs from deterministic 84-job schedule")
    if frozen["first_arm_counts"] != {arm: 21 for arm in STATE_GRAPH_CONDITIONS}:
        raise ValueError("state-graph schedule does not alternate the first arm 21/21")
    return frozen


def verify_state_graph_population(root: Path) -> dict[str, Any]:
    problems = verify_manifest(root)
    problems += [f"public: {problem}" for problem in verify_manifest(root / "public")]
    problems += [f"private: {problem}" for problem in verify_manifest(root / "private")]
    if problems:
        raise ValueError(f"state-graph population manifests failed: {problems[:5]}")
    mapping = json.loads((root / "private/instance_mapping.json").read_text())
    inventory = json.loads((root / "private/package_size_inventory.json").read_text())
    if len(mapping) != 42 or len(inventory) != 84:
        raise ValueError("state-graph population does not have 42 instances and 84 packages")
    statuses = {status: sum(row["status"] == status for row in mapping)
                for status in ("clean", "unrepaired", "repaired")}
    authors = {author: sum(row["author"] == author for row in mapping)
               for author in ("codex", "dataset")}
    if statuses != {"clean": 10, "unrepaired": 16, "repaired": 16}:
        raise ValueError("population status balance differs from the frozen design")
    if authors != {"codex": 21, "dataset": 21}:
        raise ValueError("population author balance differs from the frozen design")
    by_instance: dict[str, dict[str, str]] = {}
    for row in inventory:
        if row["arm"] not in STATE_GRAPH_CONDITIONS:
            raise ValueError("package inventory contains a non-state-graph arm")
        path = root / "public/instances" / row["instance_id"] / "packages" / f"{row['arm']}.txt"
        text = path.read_text()
        if _sha(path) != row["package_sha256"] or row["characters"] != len(text):
            raise ValueError(f"{row['instance_id']}/{row['arm']}: package inventory mismatch")
        if row["tokens"] <= 0 or row["tokens"] > CONTEXT_BUDGET_TOKENS:
            raise ValueError("package is empty, truncated, or over the context budget")
        if row.get("context_preflight_passed") is not True or row.get("truncated", False):
            raise ValueError("package did not pass no-truncation context preflight")
        kind = "appworld_execution" if row["arm"] == STATE_GRAPH_CONDITIONS[0] else "etiq_native"
        if text.count("PROVENANCE GRAPH kind=") != 1 or f"kind={kind}" not in text:
            raise ValueError("package does not contain exactly one correctly typed graph")
        forbidden = (
            "EXECUTED WORKFLOW SOURCE", "CALLS MADE", "COMPLETE INTERLEAVED ACTION LOG",
            "kind=appworld_etiq_composite", "unrepaired", "repaired", "fault_id",
            "private truth", "expected_affected_artifacts", "mutation_metadata",
        )
        if any(term in text for term in forbidden):
            raise ValueError("state-graph package contains forbidden or private evidence")
        common = text.split("\n\nPROVENANCE GRAPH kind=", 1)[0]
        by_instance.setdefault(row["instance_id"], {})[row["arm"]] = common
    if set(by_instance) != {row["instance_id"] for row in mapping}:
        raise ValueError("package and private instance populations differ")
    for instance_id, common in by_instance.items():
        if set(common) != set(STATE_GRAPH_CONDITIONS) or len(set(common.values())) != 1:
            raise ValueError(f"{instance_id}: paired common evidence is not byte-identical")
        snapshots = json.loads((root / "private/snapshots" / f"{instance_id}.json").read_text())
        validate_task_state_snapshot(snapshots["initial_task_state"])
        validate_task_state_snapshot(snapshots["final_task_state"])
    comparison = json.loads((root / "private/v8r11_trace_comparability_audit.json").read_text())
    if comparison["matches"] != 42 or comparison["mismatches"] != 0:
        raise ValueError("V8R11 trace-comparability gate failed")
    etiq = json.loads((root / "private/etiq_qualification_audit.json").read_text())
    if etiq["eligible"] != 42 or etiq["isolated_scans"] != 84:
        raise ValueError("native Etiq qualification is incomplete")
    schedule = _verify_schedule(root, inventory)
    return {
        "instances": 42,
        "packages": 84,
        "schedule_jobs": len(schedule["jobs"]),
        "paired_common_byte_identical": True,
        "single_graph_packages": True,
        "etiq_eligible": 42,
        "v8r11_trace_matches": 42,
        "manifests_verified": True,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    qualify = sub.add_parser("qualify")
    qualify.add_argument("--out", type=Path, required=True)
    qualify.add_argument("--code-provenance", type=Path, required=True)
    qualify.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    build = sub.add_parser("build")
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--code-provenance", type=Path, required=True)
    build.add_argument("--qualification", type=Path, required=True)
    build.add_argument("--v8r11", type=Path, default=V8R11_ROOT)
    build.add_argument("--codex-source", type=Path, default=DEFAULT_SOURCE)
    build.add_argument("--dataset-source", type=Path, default=DATASET_SOURCE)
    build.add_argument("--workers", type=int, default=4)
    build.add_argument("--timeout", type=int, default=180)
    build.add_argument("--etiq-python", type=Path, default=DEFAULT_ETIQ_PYTHON)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "qualify":
        result = qualify_state_graph_population(args.out, args.code_provenance, args.source)
    elif args.command == "build":
        result = build_state_graph_population(
            args.out, args.code_provenance, args.qualification, args.v8r11,
            args.codex_source, args.dataset_source, args.workers, args.timeout,
            args.etiq_python,
        )
    else:
        result = verify_state_graph_population(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
