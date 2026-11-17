"""Build the three fresh executions used by the state-graph reviewer smoke."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from rdr.etiq_pilot import (
    build_frozen_trace_replay_bundle,
    run_isolated_scan,
    validate_scan_result,
)
from rdr.freeze import verify_manifest, write_manifest
from rdr.v2_dry_run import _clean_truth, _truth
from rdr.v2_etiq_export import (
    STATE_GRAPH_CONDITIONS,
    SENSITIVE_NAME,
    audit_state_graph_conditions,
    build_state_graph_conditions,
    import_native_etiq,
    qualify_etiq_repeatability,
)
from rdr.v2_faults import FAULT_SPECS, _repair_plan_for, _runtime_plan, mutate_source
from rdr.v2_feasibility import DEFAULT_FIXTURE_ROOT, load_fixture
from rdr.v2_live import run_fresh_cell
from rdr.v2_pipeline import validate_execution_pair
from rdr.v2_provenance import verify_current_code_snapshot
from rdr.v2_schema import TraceV2, save_v2


DEFAULT_SOURCE = Path("runs/v2/authoring/experiment-ready-20261109/solution.py")
DEFAULT_QUALIFICATION = Path("runs/v2/qualification-v8r2-reliability-20261114/qualification.json")
REPLAY_ENTRY = Path("fixtures/v2/etiq_replay_entry.py")
DEFAULT_ETIQ_PYTHON = Path(".venv-etiq-pilot/bin/python")
REQUIRED_STATE_KEYS = {
    "gmail_threads": list,
    "venmo_users_by_email": dict,
    "relevant_payment_requests": list,
    "receipt_files": dict,
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def validate_task_state_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or set(snapshot) != set(REQUIRED_STATE_KEYS):
        raise ValueError("task-state snapshot has the wrong fields")
    for key, expected_type in REQUIRED_STATE_KEYS.items():
        if not isinstance(snapshot[key], expected_type):
            raise ValueError(f"task-state snapshot field {key} has the wrong type")
    if not snapshot["gmail_threads"] or not snapshot["venmo_users_by_email"]:
        raise ValueError("task-state snapshot lacks the qualified task inputs")
    if not snapshot["receipt_files"]:
        raise ValueError("task-state snapshot lacks the task-scoped receipt paths")
    return snapshot


def _admitted_record(path: Path, fault_id: str) -> dict[str, Any]:
    records = json.loads(path.read_text())
    matches = [record for record in records if record["fault_id"] == fault_id]
    if len(matches) != 1 or matches[0].get("admitted") != 1:
        raise ValueError(f"{fault_id} is not an admitted fault with repaired/unrepaired variants")
    return matches[0]


def _run_three(source: str, author: str, fault_id: str, timeout_seconds: int) -> dict[str, dict]:
    clean = run_fresh_cell(source, author, timeout_seconds=timeout_seconds)
    mutated, source_location = mutate_source(source, fault_id)
    unrepaired_plan = _runtime_plan(fault_id, clean)
    repaired_plan = _repair_plan_for(fault_id, clean)
    unrepaired = run_fresh_cell(
        mutated, author, unrepaired_plan, timeout_seconds=timeout_seconds
    )
    repaired = run_fresh_cell(
        mutated, author, repaired_plan, timeout_seconds=timeout_seconds
    )
    return {
        "clean": clean,
        "unrepaired": unrepaired,
        "repaired": repaired,
        "source_locations": [source_location],
    }


def _instance_id(status: str, result: dict[str, Any]) -> str:
    identity = {
        "status": status,
        "trace_sha256": result["trace_sha256"],
        "source_sha256": result["source_sha256"],
        "fault_plan": result.get("fault_plan", {}),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return "state-smoke-" + digest[:16]


def _capture_etiq(
    root: Path, instance_id: str, result: dict[str, Any], etiq_python: Path,
) -> tuple[dict, dict]:
    capture = root / "private/etiq" / instance_id
    exchange = capture / "exchange"
    exchange.mkdir(parents=True)
    source_path = exchange / "workflow.py"
    bundle_path = exchange / "bundle.json"
    source_relative = source_path.resolve().relative_to(Path.cwd().resolve())
    bundle, replay_source = build_frozen_trace_replay_bundle(
        result["trace"], source_relative, instance_id,
        result.get("fault_plan"), result.get("repair_index"),
    )
    source_path.write_text(replay_source)
    _write_json(bundle_path, bundle)
    first, second = capture / "run-1", capture / "run-2"
    run_isolated_scan(
        REPLAY_ENTRY, first, bundle_path=bundle_path, python_executable=etiq_python
    )
    run_isolated_scan(
        REPLAY_ENTRY, second, bundle_path=bundle_path, python_executable=etiq_python
    )
    validate_scan_result(first, REPLAY_ENTRY, bundle_path=bundle_path)
    validate_scan_result(second, REPLAY_ENTRY, bundle_path=bundle_path)
    qualification = qualify_etiq_repeatability(first, second)
    if qualification["workflow_only_eligibility"]["status"] != "eligible":
        raise ValueError(f"{instance_id}: native Etiq repeatability did not qualify")
    graph = import_native_etiq(first, qualification)
    qualification_root = capture / "qualification"
    _write_json(qualification_root / "repeatability.json", qualification)
    _write_json(qualification_root / "source-binding.json", {
        "instance_id": instance_id,
        "workflow_sha256": bundle["workflow_sha256"],
        "run_1_source_sha256": json.loads((first / "scan-result.json").read_text())[
            "source_workflow_sha256"
        ],
        "run_2_source_sha256": json.loads((second / "scan-result.json").read_text())[
            "source_workflow_sha256"
        ],
        "passed": True,
    })
    return graph, qualification


def _private_values(trace_data: dict[str, Any]) -> list[str]:
    return [
        value
        for call in trace_data["calls"]
        for key, value in call["args"].items()
        if SENSITIVE_NAME.search(key) and isinstance(value, str)
    ]


def verify_state_graph_smoke(root: Path) -> dict[str, Any]:
    problems = verify_manifest(root)
    problems += [f"public: {item}" for item in verify_manifest(root / "public")]
    problems += [f"private: {item}" for item in verify_manifest(root / "private")]
    if problems:
        raise ValueError(f"state-graph smoke manifests failed: {problems[:5]}")
    mapping = json.loads((root / "private/instance_mapping.json").read_text())
    inventory = json.loads((root / "private/package_inventory.json").read_text())
    if len(mapping) != 3 or {row["status"] for row in mapping} != {
        "clean", "unrepaired", "repaired",
    }:
        raise ValueError("private mapping is not the predeclared three-instance design")
    if len(inventory) != 6:
        raise ValueError("package inventory does not contain exactly six rows")
    by_instance: dict[str, dict[str, str]] = {}
    for row in inventory:
        if row["arm"] not in STATE_GRAPH_CONDITIONS:
            raise ValueError("package inventory contains an unregistered condition")
        path = root / "public/instances" / row["instance_id"] / "packages" / f"{row['arm']}.txt"
        text = path.read_text()
        if _sha(path) != row["package_sha256"] or row["characters"] <= 0 or row["tokens"] <= 0:
            raise ValueError("package inventory differs from public evidence")
        expected_kind = (
            "appworld_execution" if row["arm"] == "STATE_APPWORLD_GRAPH" else "etiq_native"
        )
        if text.count("PROVENANCE GRAPH kind=") != 1 or f"kind={expected_kind}" not in text:
            raise ValueError("state package does not contain exactly one correctly typed graph")
        forbidden = (
            "EXECUTED WORKFLOW SOURCE", "CALLS MADE", "COMPLETE INTERLEAVED ACTION LOG",
            "kind=appworld_etiq_composite", "unrepaired", "repaired", "fault_id",
        )
        if any(term in text for term in forbidden):
            raise ValueError("state package contains forbidden evidence or private labels")
        common = text.split("\n\nPROVENANCE GRAPH kind=", 1)[0]
        by_instance.setdefault(row["instance_id"], {})[row["arm"]] = common
    for instance_id, common in by_instance.items():
        if set(common) != set(STATE_GRAPH_CONDITIONS) or len(set(common.values())) != 1:
            raise ValueError(f"{instance_id}: paired state conditions do not share byte-identical common evidence")
        snapshots = json.loads((root / "private/snapshots" / f"{instance_id}.json").read_text())
        validate_task_state_snapshot(snapshots["initial_task_state"])
        validate_task_state_snapshot(snapshots["final_task_state"])
        qualification = json.loads((
            root / "private/etiq" / instance_id / "qualification/repeatability.json"
        ).read_text())
        if qualification["workflow_only_eligibility"]["status"] != "eligible":
            raise ValueError(f"{instance_id}: Etiq qualification is not eligible")
    return {
        "instances": len(by_instance), "packages": len(inventory),
        "paired_common_byte_identical": True,
        "single_graph_packages": True,
        "manifests_verified": True,
    }


def build_state_graph_smoke(
    output_root: Path,
    code_provenance: Path,
    fault_id: str,
    author: str,
    source_path: Path = DEFAULT_SOURCE,
    qualification_path: Path = DEFAULT_QUALIFICATION,
    timeout_seconds: int = 180,
    etiq_python: Path = DEFAULT_ETIQ_PYTHON,
) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    if author not in {"codex", "dataset"}:
        raise ValueError("author must be codex or dataset")
    if fault_id != "M02":
        raise ValueError("the state-graph smoke is predeclared for admitted M02; no substitution is allowed")
    record = _admitted_record(qualification_path, fault_id)
    if record.get("fault_class") != "mixed" or FAULT_SPECS[fault_id].fault_class != "mixed":
        raise ValueError("M02 admission no longer matches the mixed-fault smoke design")
    problems = verify_current_code_snapshot(code_provenance)
    if problems:
        raise ValueError(f"current code differs from smoke provenance: {problems[:5]}")
    output_root.mkdir(parents=True)
    try:
        source = source_path.read_text()
        runs = _run_three(source, author, fault_id, timeout_seconds)
        pair_validation = validate_execution_pair(
            runs["unrepaired"], runs["repaired"], runs["clean"]
        )
        code_record = json.loads((code_provenance / "code_provenance.json").read_text())
        mapping = []
        inventory = []
        replay_audit = []
        etiq_audit = []
        fixture = load_fixture()
        for status in ("clean", "unrepaired", "repaired"):
            result = runs[status]
            initial = validate_task_state_snapshot(result["initial_task_state"])
            final = validate_task_state_snapshot(result["final_task_state"])
            instance_id = _instance_id(status, result)
            trace = TraceV2.from_dict(result["trace"])
            if status == "clean":
                truth = _clean_truth(result, f"state-smoke-{author}-clean", author, fixture)
            else:
                truth = _truth(
                    result, f"state-smoke-{author}-{fault_id}-{status}", fault_id,
                    record["fault_class"], status, author,
                    runs["source_locations"], pair_validation,
                )
            private = output_root / "private"
            for directory in (
                private / "traces", private / "truth", private / "runs" / instance_id,
                private / "snapshots", private / "graphs" / instance_id,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            save_v2(trace, private / "traces" / f"{instance_id}.json")
            save_v2(truth, private / "truth" / f"{instance_id}.json")
            _write_json(private / "runs" / instance_id / "run.json", result)
            _write_json(private / "runs" / instance_id / "pair_validation.json", (
                {"kind": "clean_control", "fault_intervention": False}
                if status == "clean" else pair_validation
            ))
            _write_json(private / "snapshots" / f"{instance_id}.json", {
                "schema_version": 1,
                "initial_task_state": initial,
                "final_task_state": final,
                "initial_sha256": hashlib.sha256(
                    json.dumps(initial, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "final_sha256": hashlib.sha256(
                    json.dumps(final, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "schema_valid": True,
            })
            appworld = result["execution_graph"]
            _write_json(private / "graphs" / instance_id / "appworld_execution.json", appworld)
            etiq, qualification = _capture_etiq(
                output_root, instance_id, result, etiq_python
            )
            _write_json(private / "graphs" / instance_id / "etiq_native.json", etiq)
            packages = build_state_graph_conditions(
                trace, appworld, etiq, initial, final
            )
            audit = audit_state_graph_conditions(packages, _private_values(result["trace"]))
            if not audit["passed"]:
                raise ValueError(f"{instance_id}: state-graph package isolation failed")
            package_root = output_root / "public/instances" / instance_id / "packages"
            package_root.mkdir(parents=True)
            for package in packages:
                path = package_root / f"{package.arm}.txt"
                path.write_text(package.text)
                row = {
                    "instance_id": instance_id, "arm": package.arm,
                    **package.metadata,
                }
                inventory.append(row)
            mapping.append({
                "instance_id": instance_id, "status": status,
                "fault_id": None if status == "clean" else fault_id,
                "author": author,
            })
            replay_audit.append({
                "instance_id": instance_id, "status": status,
                "fresh_root": result["process"]["fresh_root"],
                "process_group_owned": result["process"]["process_group_owned"],
                "returncode": result["process"]["returncode"],
                "initial_snapshot": f"private/snapshots/{instance_id}.json",
                "final_snapshot": f"private/snapshots/{instance_id}.json",
                "snapshot_schema_valid": True,
                "appworld_initialization": "completed_with_local_loopback_available",
            })
            etiq_audit.append({
                "instance_id": instance_id,
                "repeatability": f"private/etiq/{instance_id}/qualification/repeatability.json",
                "source_binding": f"private/etiq/{instance_id}/qualification/source-binding.json",
                "eligible": qualification["workflow_only_eligibility"]["status"] == "eligible",
                "package_isolation": audit,
            })
        if len(mapping) != 3 or len(inventory) != 6:
            raise ValueError("state-graph smoke must contain exactly three instances and six packages")
        private = output_root / "private"
        _write_json(private / "instance_mapping.json", mapping)
        _write_json(private / "package_inventory.json", inventory)
        _write_json(private / "appworld_replay_audit.json", {
            "schema_version": 1,
            "initialization_diagnosis": (
                "AppWorld Starlette TestClient initialization requires local loopback; the network-isolated "
                "sandbox blocks before snapshot_task_state, while the same bounded worker completes when "
                "local loopback is available."
            ),
            "rows": replay_audit,
        })
        _write_json(private / "etiq_qualification_audit.json", etiq_audit)
        _write_json(private / "smoke_design.json", {
            "schema_version": 1, "fault_id": fault_id, "author": author,
            "statuses": ["clean", "unrepaired", "repaired"],
            "selection": "predeclared functional smoke design; never used to alter package evidence",
            "qualification_record_sha256": _sha(qualification_path),
            "reviewer_calls": 0,
        })
        public_rows = [
            {key: value for key, value in row.items() if key not in {"actual_reviewer_input_tokens"}}
            for row in inventory
        ]
        (output_root / "public/package_manifest.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in public_rows)
        )
        _write_json(output_root / "public/one_shot_job_order.json", {
            "schema_version": 1,
            "selected_before_reviewer_outputs": True,
            "jobs": [
                {"position": position, "instance_id": row["instance_id"],
                 "arm": row["arm"], "package_sha256": row["package_sha256"]}
                for position, row in enumerate(sorted(
                    public_rows, key=lambda item: (item["instance_id"], item["arm"])
                ))
            ],
        })
        _write_json(output_root / "public/build_identity.json", {
            "build_version": output_root.name,
            "code_snapshot_id": code_record["snapshot_id"],
            "code_provenance": str(code_provenance),
            "code_provenance_manifest_sha256": _sha(
                code_provenance / "MANIFEST.sha256.json"
            ),
            "reviewer_model": "gpt-5.6-sol",
            "reasoning_effort": "medium",
        })
        _write_json(private / "code_provenance_binding.json", {
            "path": str(code_provenance),
            "snapshot_id": code_record["snapshot_id"],
            "manifest_sha256": _sha(code_provenance / "MANIFEST.sha256.json"),
        })
        summary = {
            "schema_version": 1,
            "instances": 3,
            "packages": 6,
            "conditions": list(STATE_GRAPH_CONDITIONS),
            "fault_id": fault_id,
            "author": author,
            "reviewer_calls": 0,
            "appworld_replays": 3,
            "etiq_native_runs": 6,
            "all_snapshots_schema_valid": True,
            "all_etiq_repeatability_eligible": True,
            "all_package_isolation_passed": True,
        }
        _write_json(output_root / "summary.json", summary)
        for manifest_root in (output_root / "public", output_root / "private"):
            write_manifest(manifest_root)
        write_manifest(output_root)
        verification = verify_state_graph_smoke(output_root)
        if verification != {
            "instances": 3, "packages": 6, "paired_common_byte_identical": True,
            "single_graph_packages": True, "manifests_verified": True,
        }:
            raise ValueError("final state-graph smoke verification differs")
        return summary
    except Exception as error:
        _write_json(output_root / "private/build_failure.json", {
            "status": "blocked", "error_type": type(error).__name__, "reason": str(error),
            "root_manifest_written": False,
        })
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--code-provenance", type=Path, required=True)
    parser.add_argument("--fault-id", required=True)
    parser.add_argument("--author", choices=("codex", "dataset"), required=True)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--qualification", type=Path, default=DEFAULT_QUALIFICATION)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--etiq-python", type=Path, default=DEFAULT_ETIQ_PYTHON)
    args = parser.parse_args(argv)
    result = build_state_graph_smoke(
        args.out, args.code_provenance, args.fault_id, args.author,
        args.source, args.qualification, args.timeout, args.etiq_python,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
