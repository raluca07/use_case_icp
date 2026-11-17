"""No-review v2 build from real, isolated AppWorld executions only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import sys
import shutil
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rdr.freeze import verify_manifest, write_manifest
from rdr.graph import rec_node
from rdr.stepwise import explored_graph, round_package
from rdr.v2_faults import (FAULT_SPECS, _action_plan, _repair_plan_for, _runtime_plan,
                           mutate_source, qualify_faults, root_cause_evidence)
from rdr.v2_live import run_fresh_cell
from rdr.v2_packager import (_common_with_calls, _flat_graph, ARMS_V2, audit_packages, build_package_v2,
                             package_metadata)
from rdr.v2_pipeline import validate_execution_pair
from rdr.v2_schema import TraceV2, TruthV2, save_v2


NON_INTERACTIVE_ARMS = tuple(arm for arm in ARMS_V2 if arm not in {"N", "O"})
JOB_ORDER_SEED = 20261108
PRIVATE_PACKAGE_FIELDS = frozenset({
    "fault_id", "fault_class", "repair", "fault_occurred", "residual_harm_present",
    "author", "generator_cluster", "trace_sha256", "task_input_sha256", "source_sha256",
})


def _public_id(private_id: str, prefix: str = "v6") -> str:
    return prefix + "-" + hashlib.sha256(private_id.encode()).hexdigest()[:16]


def _write_package_manifests(root: Path, rows: list[dict]) -> None:
    public_rows = [{key: value for key, value in row.items() if key not in PRIVATE_PACKAGE_FIELDS}
                   for row in rows]
    (root / "public" / "package_manifest.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in public_rows))
    (root / "private" / "package_truth_manifest.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    _write_schedules(root, public_rows)


def _write_instance_map(root: Path) -> None:
    mapping = {}
    for path in sorted((root / "private" / "truth").glob("*.json")):
        truth = TruthV2.from_dict(json.loads(path.read_text()))
        mapping[path.stem] = truth.instance_id
    (root / "private" / "instance_map.json").write_text(json.dumps(mapping, indent=2, sort_keys=True))


def _write_schedules(root: Path, rows: list[dict]) -> None:
    jobs = [{"instance_id": row["instance_id"], "arm": row["arm"],
             "package_sha256": row["package_sha256"]}
            for row in rows if row["arm"] not in {"N", "O"}]
    jobs.sort(key=lambda item: (item["instance_id"], item["arm"]))
    random.Random(JOB_ORDER_SEED).shuffle(jobs)
    (root / "public" / "one_shot_job_order.json").write_text(json.dumps({
        "seed": JOB_ORDER_SEED, "selected_before_reviewer_outputs": True,
        "jobs": [{"position": position, **job} for position, job in enumerate(jobs)],
    }, indent=2, sort_keys=True))
    instances = sorted({row["instance_id"] for row in rows})
    random.Random(JOB_ORDER_SEED).shuffle(instances)
    interactive = []
    for position, instance_id in enumerate(instances):
        base = root / "public" / "interactive" / instance_id
        interactive.append({
            "position": position,
            "instance_id": instance_id,
            "walk_sha256": _sha(base / "walk.json"),
            "N_initial_sha256": _sha(base / "N.initial.txt"),
            "O_initial_sha256": _sha(base / "O.initial.txt"),
        })
    (root / "public" / "interactive_job_order.json").write_text(json.dumps({
        "seed": JOB_ORDER_SEED, "selected_before_reviewer_outputs": True,
        "instances": interactive,
    }, indent=2, sort_keys=True))


def _copy_private_graphs(root: Path, authoring_graph: Path | None = None) -> None:
    graph_root = root / "private" / "graphs"
    codex_root, etiq_root = graph_root / "codex_authoring", graph_root / "etiq_native"
    codex_root.mkdir(parents=True, exist_ok=True)
    etiq_root.mkdir(parents=True, exist_ok=True)
    authoring_graph = authoring_graph or Path(
        "runs/v2/authoring/experiment-ready-20261109/codex_authoring.json")
    if authoring_graph.is_file():
        shutil.copy2(authoring_graph, codex_root / "codex_authoring.json")
    etiq = Path("runs/v2/etiq-experiment-ready-20261109/etiq_native_unavailable.json")
    if etiq.is_file():
        shutil.copy2(etiq, etiq_root / etiq.name)
    links = []
    for trace_path in sorted((root / "private" / "traces").glob("*.json")):
        trace = TraceV2.from_dict(json.loads(trace_path.read_text()))
        execution = json.loads((root / "appworld_execution" / trace_path.name).read_text())
        links.append({
            "instance_id": trace_path.stem, "appworld_run_id": execution["run_id"],
            "final_source_sha256": hashlib.sha256(trace.source["workflow.py"].encode()).hexdigest(),
        })
    (graph_root / "linkage.json").write_text(json.dumps({
        "schema_version": 1, "join_keys": ["final_source_sha256", "appworld_run_id"],
        "node_sets_merged": False, "links": links,
    }, indent=2, sort_keys=True))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_qualification(source: str, root: Path) -> list[dict]:
    qualification_root = root / "private" / "qualification"
    qualification_root.mkdir(parents=True, exist_ok=True)
    records = qualify_faults(source, qualification_root, "codex")
    path = qualification_root / "qualification.json"
    path.write_text(json.dumps(records, indent=2, sort_keys=True))
    lines = ["# Live v2 fault qualification", "", "All attempts below are fresh copied AppWorld worlds.", "",
             "| Fault | Status | Attempts | Admitted | Reason |", "|---|---:|---:|---:|---|"]
    for record in records:
        lines.append(f"| {record['fault_id']} | {record['status']} | {record['attempted']} | "
                     f"{record['admitted']} | {record['reason']} |")
    (qualification_root / "qualification.md").write_text("\n".join(lines) + "\n")
    return records


def _real_pair(source: str, author: str, fault_id: str) -> tuple[dict, dict, list[str], dict]:
    clean = run_fresh_cell(source, author)
    spec = FAULT_SPECS[fault_id]
    faulty_source, locations = source, []
    if spec.fault_class in {"source", "mixed", "interaction", "amplified"}:
        mutated, location = mutate_source(source, fault_id)
        faulty_source, locations = mutated, [location]
    if spec.fault_class == "action":
        unrepaired_plan = _action_plan(fault_id, clean)
    elif spec.fault_class == "source":
        unrepaired_plan = None
    else:
        unrepaired_plan = _runtime_plan(fault_id, clean)
    return (run_fresh_cell(faulty_source, author, unrepaired_plan),
            run_fresh_cell(faulty_source, author, _repair_plan_for(fault_id, clean)), locations, clean)


def _cached_pair(root: Path, source: str, author: str, fault_id: str) -> tuple[dict, dict, list[str], dict] | None:
    paths = {
        repair: root / "instances" / f"live-{author}-{fault_id}-{repair}" / "private" / "run.json"
        for repair in ("unrepaired", "repaired")
    }
    if not all(path.is_file() for path in paths.values()):
        return None
    for path in paths.values():
        problems = verify_manifest(path.parents[1])
        if problems:
            raise ValueError(f"cannot reuse changed execution at {path.parents[1]}: {problems[:3]}")
    locations = []
    if FAULT_SPECS[fault_id].fault_class in {"source", "mixed", "interaction", "amplified"}:
        _, location = mutate_source(source, fault_id)
        locations.append(location)
    return (json.loads(paths["unrepaired"].read_text()), json.loads(paths["repaired"].read_text()),
            locations, run_fresh_cell(source, author))


def _trace_sha(trace: TraceV2) -> str:
    return hashlib.sha256(json.dumps(trace.to_dict(), sort_keys=True).encode()).hexdigest()


def _clean_fixture_variants() -> list[dict]:
    base = json.loads(Path("fixtures/v2/invoice_v1.json").read_text())
    config = json.loads(Path("fixtures/v2/clean_controls.json").read_text())
    variants = []
    for selected in config["variants"]:
        fixture = copy.deepcopy(base)
        fixture["fixture_id"] = "invoice-v1-" + selected["id"]
        for position, invoice in enumerate([*fixture["invoices"], fixture["unmatched_invoice"]], 1):
            invoice["amount_usd"] = round(invoice["amount_usd"] + selected["amount_offset"], 2)
            invoice["memo"] += selected["memo_suffix"]
            invoice["invoice_id"] += "-" + selected["id"].upper()
            invoice["subject_suffix"] += " " + selected["id"]
        variants.append(fixture)
    return variants


def _truth(result: dict, instance_id: str, fault_id: str, fault_class: str, repair: str,
           author: str, source_locations: list[str], pair_validation: dict) -> TruthV2:
    if fault_id.startswith("P") or FAULT_SPECS[fault_id].injection_channel is not None:
        raise ValueError("out-of-scope security case cannot enter the reliability population")
    trace = TraceV2.from_dict(result["trace"])
    historical = list(pair_validation["historically_corrupted_artifacts"])
    restored = list(pair_validation["restored_artifacts"]) if repair == "repaired" else []
    residual = (list(pair_validation["residual_harmful_artifacts"])
                if repair == "repaired" else list(pair_validation["unrepaired_residual_harmful_artifacts"]))
    harmful_calls = list(pair_validation["harmful_runtime_indices"] if repair == "repaired"
                         else pair_validation["unrepaired_harmful_runtime_indices"])
    causal_sources, causal_events = root_cause_evidence(
        fault_id, source_locations, result.get("fault_plan") or result.get("plan")
    )
    historical = sorted(set(historical) | {write.record for call in trace.calls
                                           if call.index in harmful_calls for write in call.writes})
    changed = [write.record for call in trace.calls for write in call.writes]
    written = set(changed)
    symptom = next((item for item in historical if item in written), changed[0])
    residual_present = bool(residual or not result["evaluation"]["passed"])
    return TruthV2(instance_id, True, residual_present, fault_id, fault_class, repair,
                   causal_sources, causal_events, historical, sorted(set(restored)),
                   sorted(set(residual)), symptom, author,
                   injection_channel=FAULT_SPECS[fault_id].injection_channel,
                   task_cluster="invoice-v1",
                   generator_cluster=fault_id, trace_sha256=_trace_sha(trace),
                   task_input_sha256=hashlib.sha256(
                       Path("fixtures/v2/invoice_v1.json").read_bytes()).hexdigest(),
                   source_sha256=hashlib.sha256(trace.source["workflow.py"].encode()).hexdigest())


def _clean_truth(result: dict, instance_id: str, author: str, fixture: dict) -> TruthV2:
    trace = TraceV2.from_dict(result["trace"])
    anchor_call = next(call for call in trace.calls if call.name == "venmo.create_payment_request")
    symptom = next(write.record for write in anchor_call.writes
                   if write.record.startswith("venmo.payment_requests#"))
    return TruthV2(instance_id, False, False, None, None, None, [], [], [], [], [], symptom,
                   author, task_cluster="invoice-v1", generator_cluster=f"clean-{author}",
                   trace_sha256=_trace_sha(trace),
                   task_input_sha256=hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest(),
                   source_sha256=hashlib.sha256(trace.source["workflow.py"].encode()).hexdigest())


def _anchor_index(trace: TraceV2, truth: TruthV2) -> int:
    if truth.root_cause_event_indices:
        return min(truth.root_cause_event_indices)
    return next(call.index for call in trace.calls
                if any(write.record == truth.symptom for write in call.writes))


def _write_instance(root: Path, result: dict, truth: TruthV2, pair_validation: dict,
                    package_rows: list[dict], audits: list[dict], public_prefix: str = "v6") -> None:
    trace = TraceV2.from_dict(result["trace"])
    public_id = _public_id(truth.instance_id, public_prefix)
    instance = root / "public" / "instances" / public_id
    packages_dir = instance / "packages"
    packages_dir.mkdir(parents=True)
    private = root / "private"
    for directory in (private / "truth", private / "traces", private / "runs" / public_id,
                      root / "appworld_execution"):
        directory.mkdir(parents=True, exist_ok=True)
    save_v2(trace, private / "traces" / f"{public_id}.json")
    save_v2(truth, private / "truth" / f"{public_id}.json")
    execution_path = root / "appworld_execution" / f"{public_id}.json"
    execution_path.write_text(json.dumps(result["execution_graph"], indent=2, sort_keys=True))
    (private / "runs" / public_id / "run.json").write_text(
        json.dumps(result, indent=2, sort_keys=True))
    (private / "runs" / public_id / "pair_validation.json").write_text(
        json.dumps(pair_validation, indent=2, sort_keys=True))
    anchor = _anchor_index(trace, truth)
    packages = [build_package_v2(arm, trace, truth.symptom, public_id, anchor,
                                 execution_graph=result["execution_graph"],
                                 initial_task_state=result.get("initial_task_state"),
                                 final_task_state=result.get("final_task_state"))
                for arm in NON_INTERACTIVE_ARMS]
    for package in packages:
        (packages_dir / f"{package.arm}.txt").write_text(package.text)
        package_rows.append({"instance_id": public_id, "fault_id": truth.fault_id,
                             "fault_class": truth.fault_class, "repair": truth.repair,
                             "fault_occurred": truth.fault_occurred,
                             "residual_harm_present": truth.residual_harm_present,
                             "author": truth.author, "generator_cluster": truth.generator_cluster,
                             "trace_sha256": truth.trace_sha256,
                             "task_input_sha256": truth.task_input_sha256,
                             "source_sha256": truth.source_sha256,
                             "arm": package.arm, **package.metadata})
    flat = _flat_graph(result["execution_graph"])
    c_graph_hash = next(package.metadata["graph_projection_sha256"] for package in packages
                        if package.arm == "C")
    interactive_graph_hash = package_metadata("", {}, trace, flat)["graph_projection_sha256"]
    start = rec_node(truth.symptom)
    initial = round_package(trace.to_v1_observed(), truth.symptom, flat, [start], [], [], 6,
                            common_header=_common_with_calls(trace))
    initial_view = explored_graph(flat, [start])
    interactive_dir = root / "public" / "interactive" / public_id
    interactive_dir.mkdir(parents=True)
    interactive_common = initial.split("\n\nPROVENANCE GRAPH, EXPLORED PART ONLY", 1)[0]
    for arm in ("N", "O"):
        path = interactive_dir / f"{arm}.initial.txt"
        path.write_text(initial)
        package_rows.append({
            "instance_id": public_id, "fault_id": truth.fault_id,
            "fault_class": truth.fault_class, "repair": truth.repair,
            "fault_occurred": truth.fault_occurred,
            "residual_harm_present": truth.residual_harm_present,
            "author": truth.author, "generator_cluster": truth.generator_cluster,
            "trace_sha256": truth.trace_sha256, "task_input_sha256": truth.task_input_sha256,
            "source_sha256": truth.source_sha256, "arm": arm, "interactive": True,
            "package_kind": "initial_walk_view",
            **package_metadata(initial, {"interactive_initial": initial}, trace, initial_view),
        })
    public_trace = trace.to_dict()
    public_trace["source"] = {}
    (interactive_dir / "walk.json").write_text(json.dumps({
        "trace": public_trace, "reported_artifact": truth.symptom,
        "execution_graph": result["execution_graph"],
    }, indent=2, sort_keys=True))
    forbidden = ["mutation_metadata", "expected_affected_artifacts"]
    if truth.fault_id:
        forbidden.extend([truth.fault_id, truth.repair])
    audit = audit_packages(packages, forbidden, execution_graph=result["execution_graph"])
    audit.update({"instance_id": truth.instance_id, "public_id": public_id, "repair": truth.repair,
                  "interactive_common_matches": interactive_common == _common_with_calls(trace),
                  "interactive_flat_graph_matches_c": interactive_graph_hash == c_graph_hash,
                  "clean_metadata_empty": (truth.fault_occurred or
                                           not any((truth.fault_id, truth.fault_class, truth.repair,
                                                    truth.root_cause_source_locations,
                                                    truth.root_cause_event_indices,
                                                    truth.historically_affected_artifacts,
                                                    truth.restored_artifacts,
                                                    truth.residual_harmful_artifacts)))})
    audit["passed"] = (audit["passed"] and audit["interactive_common_matches"]
                       and audit["interactive_flat_graph_matches_c"] and audit["clean_metadata_empty"])
    audits.append(audit)


def dry_run(root: Path, source_path: Path, qualification_path: Path | None = None, workers: int = 4,
            reuse_runs: Path | None = None, code_provenance: Path | None = None,
            environment_root: Path | None = None, build_version: str = "V6") -> dict:
    if root.exists():
        raise FileExistsError(f"dry-run output already exists: {root}")
    root.mkdir(parents=True)
    public_prefix = build_version.lower().split("-", 1)[0]
    codex_source = source_path.read_text()
    if qualification_path:
        qualification = json.loads(qualification_path.read_text())
        qualification_root = root / "private" / "qualification"
        shutil.copytree(qualification_path.parent, qualification_root,
                        ignore=shutil.ignore_patterns("MANIFEST.sha256.json"))
    else:
        qualification = _write_qualification(codex_source, root)
    admitted_records = [record for record in qualification if record["admitted"]]
    admitted = [record["fault_id"] for record in admitted_records]
    class_by_fault = {record["fault_id"]: record["inferred_classification"] for record in admitted_records}
    sources = {"codex": codex_source, "dataset": Path("fixtures/v2/reference_solution.py").read_text()}
    package_rows, audits = [], []
    pair_jobs = [(author, source, fault_id) for author, source in sources.items() for fault_id in admitted]
    def build_pair(job):
        author, source, fault_id = job
        pair = _cached_pair(reuse_runs, source, author, fault_id) if reuse_runs else None
        return (*job, pair or _real_pair(source, author, fault_id), pair is not None)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pair_results = list(pool.map(build_pair, pair_jobs))
        variants = _clean_fixture_variants()
        clean_jobs = [("codex" if index % 2 == 0 else "dataset",
                       sources["codex" if index % 2 == 0 else "dataset"], fixture)
                      for index, fixture in enumerate(variants)]
        clean_results = list(pool.map(
            lambda item: (item[0], item[2], run_fresh_cell(item[1], item[0], fixture=item[2])), clean_jobs))
    for author, source, fault_id, pair, reused in pair_results:
        unrepaired, repaired, source_locations, clean = pair
        try:
            pair_validation = validate_execution_pair(unrepaired, repaired, clean)
        except ValueError as error:
            raise ValueError(f"{author}/{fault_id}: {error}") from error
        for repair, result in (("unrepaired", unrepaired), ("repaired", repaired)):
            instance_id = f"live-{author}-{fault_id}-{repair}"
            truth = _truth(result, instance_id, fault_id, class_by_fault[fault_id], repair,
                           author, source_locations, pair_validation)
            _write_instance(root, result, truth, pair_validation, package_rows, audits, public_prefix)
    clean_hashes = []
    clean_pairs = []
    clean_counts = {}
    for author, fixture, result in clean_results:
        clean_counts[author] = clean_counts.get(author, 0) + 1
        instance_id = f"clean-{author}-{clean_counts[author]:02d}"
        truth = _clean_truth(result, instance_id, author, fixture)
        clean_hashes.append(truth.trace_sha256)
        clean_pairs.append((truth.task_input_sha256, truth.trace_sha256))
        clean_validation = {
            "kind": "clean_control", "fault_intervention": False, "repair_intervention": False,
            "reported_record": truth.symptom, "anchor_index": _anchor_index(TraceV2.from_dict(result["trace"]), truth),
            "trace_sha256": truth.trace_sha256, "generator_cluster": truth.generator_cluster,
        }
        _write_instance(root, result, truth, clean_validation, package_rows, audits, public_prefix)
    if len(clean_pairs) < 9 or len(clean_pairs) != len(set(clean_pairs)):
        raise ValueError("clean controls require at least nine distinct input/trace pairs")
    (root / "interactive_arms.json").write_text(json.dumps({
        "N": {"status": "implemented", "max_expansions": 6, "adaptive_stop": True},
        "O": {"status": "implemented", "max_expansions": 6, "adaptive_stop": False},
        "reviewer_calls_in_preparation": 0,
    }, indent=2, sort_keys=True))
    _write_package_manifests(root, package_rows)
    _write_instance_map(root)
    (root / "private" / "isolation_audit.json").write_text(json.dumps(audits, indent=2, sort_keys=True))
    execution_provenance = [{"author": author, "fault_id": fault_id,
                             "decision": "reused" if reused else "rerun",
                             "compatibility": "verified cached pair" if reused else "not_applicable"}
                            for author, _, fault_id, _, reused in pair_results]
    (root / "private" / "execution_provenance.json").write_text(
        json.dumps(execution_provenance, indent=2, sort_keys=True))
    provenance_root = root / "private" / "provenance"
    provenance_root.mkdir()
    if not code_provenance:
        raise ValueError(f"{build_version} build requires --code-provenance")
    shutil.copytree(code_provenance, provenance_root / "code")
    if not environment_root:
        raise ValueError(f"{build_version} build requires --environment-root")
    shutil.copytree(environment_root, provenance_root / "environment")
    code_record = json.loads((provenance_root / "code" / "code_provenance.json").read_text())
    qualification_provenance = json.loads(
        (root / "private" / "qualification" / "qualification_provenance.json").read_text())
    if qualification_provenance["code_snapshot_id"] != code_record["snapshot_id"]:
        raise ValueError("qualification and package build use different code snapshots")
    (root / "public" / "build_identity.json").write_text(json.dumps({
        "build_version": build_version, "code_snapshot_id": code_record["snapshot_id"],
        "reviewer_model": "gpt-5.6-sol", "reasoning_effort": "medium",
    }, indent=2, sort_keys=True))
    sizes = [row["tokens"] for row in package_rows]
    summary = {
        "reviewer_calls": 0, "admitted_faults": admitted,
        "unavailable_classes": sorted({record["fault_class"] for record in qualification}
                                      - {record["fault_class"] for record in qualification if record["admitted"]}),
        "instances": len(admitted) * 4 + len(clean_results), "authors": sorted(sources),
        "clean_controls": len(clean_results), "clean_trace_hashes": clean_hashes,
        "clean_input_trace_pairs": clean_pairs, "clean_controls_by_author": clean_counts,
        "repaired_instances": len(admitted) * 2, "unrepaired_instances": len(admitted) * 2,
        "fully_restored_repaired": sum(
            not json.loads((root / "private" / "truth" /
                            f"{_public_id(f'live-{author}-{fault_id}-repaired', public_prefix)}.json").read_text())["residual_harm_present"]
            for author in sources for fault_id in admitted),
        "residual_harm_repaired": sum(
            json.loads((root / "private" / "truth" /
                        f"{_public_id(f'live-{author}-{fault_id}-repaired', public_prefix)}.json").read_text())["residual_harm_present"]
            for author in sources for fault_id in admitted),
        "packages": len(package_rows),
        "one_shot_package_files": sum(row["arm"] not in {"N", "O"} for row in package_rows),
        "interactive_initial_packages": sum(row["arm"] in {"N", "O"} for row in package_rows),
        "total_manifest_rows": len(package_rows),
        "expected_maximum_reviewer_calls": (
            sum(row["arm"] not in {"N", "O"} for row in package_rows)
            + 14 * (len(admitted) * 4 + len(clean_results))
        ),
        "one_shot_arms": list(NON_INTERACTIVE_ARMS), "interactive_arms": ["N", "O"],
        "qualification_counts": {status: sum(record["status"] == status for record in qualification)
                                 for status in ("qualified", "unqualified", "blocked")},
        "isolation_passed": bool(audits) and all(audit["passed"] for audit in audits),
        "package_size": {"min_tokens": min(sizes), "median_tokens": statistics.median(sizes),
                         "max_tokens": max(sizes)} if sizes else {},
        "qualification_sha256": _sha(root / "private" / "qualification" / "qualification.json"),
        "reused_real_execution_pairs": sum(reused for *_, reused in pair_results),
        "reuse_source": str(reuse_runs) if reuse_runs else None,
        "code_snapshot_id": code_record["snapshot_id"],
        "code_provenance_sha256": _sha(
            provenance_root / "code" / "code_provenance.json"),
        "environment_manifest_sha256": _sha(
            provenance_root / "environment" / "MANIFEST.sha256.json"),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    _copy_private_graphs(root, source_path.parent / "codex_authoring.json")
    for frozen_root in (root / "public", root / "private" / "qualification",
                        root / "private", root / "appworld_execution"):
        write_manifest(frozen_root)
    write_manifest(root)
    return summary


def refresh_v5_isolation(root: Path) -> dict:
    """Rebuild public packages/audits from frozen executions after packager-only corrections."""
    rows, audits = [], []
    for truth_path in sorted((root / "private" / "truth").glob("*.json")):
        instance_id = truth_path.stem
        truth = TruthV2.from_dict(json.loads(truth_path.read_text()))
        run = json.loads((root / "private" / "runs" / instance_id / "run.json").read_text())
        validation = json.loads(
            (root / "private" / "runs" / instance_id / "pair_validation.json").read_text())
        public_instance = root / "public" / "instances" / instance_id
        interactive = root / "public" / "interactive" / instance_id
        for path in [*public_instance.glob("**/*"), *interactive.glob("*")]:
            if path.is_file():
                path.unlink()
        for path in sorted([*public_instance.glob("**/*"), *interactive.glob("*")], reverse=True):
            if path.is_dir():
                path.rmdir()
        if public_instance.exists():
            public_instance.rmdir()
        if interactive.exists():
            interactive.rmdir()
        _write_instance(root, run, truth, validation, rows, audits)
    _write_package_manifests(root, rows)
    _write_instance_map(root)
    (root / "private" / "isolation_audit.json").write_text(json.dumps(audits, indent=2, sort_keys=True))
    summary_path = root / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["isolation_passed"] = bool(audits) and all(audit["passed"] for audit in audits)
    summary["packages"] = len(rows)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    _copy_private_graphs(root)
    for manifest in root.rglob("MANIFEST.sha256.json"):
        manifest.unlink()
    for frozen_root in (root / "public", root / "private" / "qualification",
                        root / "private", root / "appworld_execution"):
        write_manifest(frozen_root)
    write_manifest(root)
    return summary


def repackage_v5(source: Path, destination: Path) -> dict:
    """Create a new frozen V5 projection from measured runs without executing AppWorld."""
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    shutil.copytree(source / "private" / "qualification",
                    destination / "private" / "qualification")
    shutil.copy2(source / "interactive_arms.json", destination / "interactive_arms.json")
    rows, audits = [], []
    for truth_path in sorted((source / "private" / "truth").glob("*.json")):
        truth = TruthV2.from_dict(json.loads(truth_path.read_text()))
        run_root = source / "private" / "runs" / truth_path.stem
        run = json.loads((run_root / "run.json").read_text())
        validation = json.loads((run_root / "pair_validation.json").read_text())
        _write_instance(destination, run, truth, validation, rows, audits)
    _write_package_manifests(destination, rows)
    _write_instance_map(destination)
    (destination / "private" / "isolation_audit.json").write_text(
        json.dumps(audits, indent=2, sort_keys=True))
    summary = json.loads((source / "summary.json").read_text())
    summary.update(packages=len(rows), isolation_passed=bool(audits) and all(a["passed"] for a in audits),
                   public_ids_anonymized=True, causal_manifest_private=True,
                   repackage_source=str(source), reviewer_calls=0)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    _copy_private_graphs(destination)
    for frozen_root in (destination / "public", destination / "private" / "qualification",
                        destination / "private", destination / "appworld_execution"):
        write_manifest(frozen_root)
    write_manifest(destination)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-runs", type=Path)
    parser.add_argument("--code-provenance", type=Path)
    parser.add_argument("--environment-root", type=Path)
    parser.add_argument("--build-version", default="V6")
    parser.add_argument("--refresh-isolation", action="store_true")
    parser.add_argument("--repackage-from", type=Path)
    args = parser.parse_args(argv)
    result = (repackage_v5(args.repackage_from, args.root) if args.repackage_from else
              refresh_v5_isolation(args.root) if args.refresh_isolation else
              dry_run(args.root, args.source, args.qualification, args.workers, args.reuse_runs,
                      args.code_provenance, args.environment_root, args.build_version))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
