"""Freeze the final 42-instance, all-arm V2 experiment without reviewer calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from collections import Counter
from pathlib import Path

from rdr.freeze import verify_manifest, write_manifest
from rdr.graph import rec_node
from rdr.stepwise import round_package
from rdr.v2_dry_run import _anchor_index
from rdr.v2_etiq_export import (
    ETIQ_CONDITIONS, STATE_GRAPH_CONDITIONS, build_appworld_etiq_composite,
    build_etiq_conditions, build_state_graph_conditions,
)
from rdr.v2_packager import (
    LOG_ARMS, SOURCE_ARMS, _common_with_calls, _flat_graph, build_package_v2,
)
from rdr.v2_provenance import verify_current_code_snapshot
from rdr.v2_schema import TraceV2, TruthV2
from rdr.v2_state_graph_population import verify_state_graph_population


SOURCE_POPULATION = Path("runs/v2/build-state-graph-population-v2-20261116")
ONE_SHOT_ARMS = (
    *tuple(chr(n) for n in range(ord("A"), ord("M") + 1)),
    *tuple(chr(n) for n in range(ord("P"), ord("Z") + 1)),
    "STATE_CALLS", "STATE_CALLS_SOURCE", *ETIQ_CONDITIONS, *STATE_GRAPH_CONDITIONS,
)
INTERACTIVE_ARMS = ("N", "O")
SCHEDULE_SEED = 20261117
PRIVATE_TERMS = (
    "expected_affected_artifacts", "mutation_metadata", "private truth", "injection_channel",
    "fault_id", "fault_class", "repair_label", "qualification_status",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _copy_population_private(source: Path, target: Path) -> None:
    for name in ("truth", "traces", "snapshots", "graphs"):
        shutil.copytree(source / "private" / name, target / name)
    for name in (
        "instance_mapping.json", "appworld_snapshot_audit.json",
        "etiq_qualification_audit.json", "v8r11_trace_comparability_audit.json",
    ):
        shutil.copy2(source / "private" / name, target / name)


def freeze_one_shot_schedule(rows: list[dict], seed: int = SCHEDULE_SEED) -> dict:
    by_instance: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_instance.setdefault(row["instance_id"], {})[row["arm"]] = row
    if len(by_instance) != 42 or any(set(cell) != set(ONE_SHOT_ARMS) for cell in by_instance.values()):
        raise ValueError("one-shot schedule requires all 30 arms for all 42 instances")
    instances = sorted(by_instance)
    random.Random(seed).shuffle(instances)
    jobs = []
    first = Counter()
    for instance_position, instance_id in enumerate(instances):
        offset = instance_position % len(ONE_SHOT_ARMS)
        arms = list(ONE_SHOT_ARMS[offset:] + ONE_SHOT_ARMS[:offset])
        if (instance_position // len(ONE_SHOT_ARMS)) % 2:
            arms.reverse()
        first[arms[0]] += 1
        for arm_position, arm in enumerate(arms):
            row = by_instance[instance_id][arm]
            jobs.append({
                "position": len(jobs), "instance_position": instance_position,
                "arm_position": arm_position, "instance_id": instance_id, "arm": arm,
                "package_sha256": row["package_sha256"],
            })
    return {
        "schema_version": 1, "seed": seed, "selected_before_reviewer_outputs": True,
        "instances": 42, "arms": list(ONE_SHOT_ARMS), "jobs": jobs,
        "first_arm_counts": dict(sorted(first.items())),
    }


def freeze_interactive_schedule(public: Path, arm: str, seed: int = SCHEDULE_SEED) -> dict:
    if arm not in INTERACTIVE_ARMS:
        raise ValueError("interactive arm must be N or O")
    instances = sorted(path.name for path in (public / "interactive").iterdir() if path.is_dir())
    random.Random(seed + INTERACTIVE_ARMS.index(arm) + 1).shuffle(instances)
    jobs = []
    for position, instance_id in enumerate(instances):
        base = public / "interactive" / instance_id
        jobs.append({
            "position": position, "instance_id": instance_id, "arm": arm,
            "walk_sha256": _sha(base / "walk.json"),
            "initial_package_sha256": _sha(base / f"{arm}.initial.txt"),
        })
    return {
        "schema_version": 1, "seed": seed + INTERACTIVE_ARMS.index(arm) + 1,
        "selected_before_reviewer_outputs": True, "arm": arm, "max_expansions": 6,
        "adaptive_stop": arm == "N", "jobs": jobs,
    }


def _package_audit(instance_id: str, packages, truth: TruthV2) -> dict:
    by_arm = {package.arm: package for package in packages}
    violations = []
    for package in packages:
        text, sections = package.text, package.sections
        if "USER REPORT" in text:
            violations.append(f"{package.arm}: user report")
        if any(term in text.lower() for term in PRIVATE_TERMS):
            violations.append(f"{package.arm}: private term")
        if ("source" in sections) != (package.arm in SOURCE_ARMS):
            violations.append(f"{package.arm}: source isolation")
        expected_calls = (
            package.arm in {*tuple(chr(n) for n in range(ord("A"), ord("V") + 1)),
                            *ETIQ_CONDITIONS, "STATE_CALLS", "STATE_CALLS_SOURCE"}
        )
        if ("call_index" in sections) != expected_calls:
            violations.append(f"{package.arm}: call-index isolation")
        if ("action_log" in sections) != (package.arm in LOG_ARMS):
            violations.append(f"{package.arm}: action-log isolation")
        if ("inputs" in sections) != (package.arm == "I"):
            violations.append(f"{package.arm}: call-input isolation")
        if package.metadata.get("truncated") or not package.metadata.get("context_preflight_passed"):
            violations.append(f"{package.arm}: context/truncation")
    standard = [p.common for p in packages if p.arm not in {"Y", "Z", "STATE_CALLS", "STATE_CALLS_SOURCE", *STATE_GRAPH_CONDITIONS}]
    state = [p.common for p in packages if p.arm in {"Y", "Z", "STATE_CALLS", "STATE_CALLS_SOURCE", *STATE_GRAPH_CONDITIONS}]
    if len(set(standard)) != 1 or len(set(state)) != 1:
        violations.append("common family mismatch")
    left, right = (by_arm[arm] for arm in STATE_GRAPH_CONDITIONS)
    if left.common != right.common or set(left.sections) != {"common", "graph"} or set(right.sections) != {"common", "graph"}:
        violations.append("state graph isolation")
    for fake, real in (("F", "C"), ("H", "G"), ("R", "Q")):
        fake_meta, real_meta = by_arm[fake].metadata, by_arm[real].metadata
        if (fake_meta["graph_nodes"] != real_meta["graph_nodes"]
                or fake_meta["graph_edges_by_type"] != real_meta["graph_edges_by_type"]):
            violations.append(f"{fake}: fake graph margins")
    return {"instance_id": instance_id, "passed": not violations, "violations": violations,
            "truth_loaded_only_during_build": truth.instance_id is not None}


def build_unified(root: Path, code_provenance: Path, source: Path = SOURCE_POPULATION) -> dict:
    if root.exists():
        raise FileExistsError(root)
    source_check = verify_state_graph_population(source)
    code_problems = verify_current_code_snapshot(code_provenance)
    if code_problems:
        raise ValueError(f"current code differs from provenance snapshot: {code_problems[:5]}")
    root.mkdir(parents=True)
    public, private = root / "public", root / "private"
    _copy_population_private(source, private)
    mapping = json.loads((private / "instance_mapping.json").read_text())
    rows, private_rows, audits = [], [], []
    for mapped in mapping:
        instance_id = mapped["instance_id"]
        trace = TraceV2.from_dict(json.loads((private / "traces" / f"{instance_id}.json").read_text()))
        truth = TruthV2.from_dict(json.loads((private / "truth" / f"{instance_id}.json").read_text()))
        snapshot = json.loads((private / "snapshots" / f"{instance_id}.json").read_text())
        graphs = private / "graphs" / instance_id
        appworld = json.loads((graphs / "appworld_execution.json").read_text())
        etiq = json.loads((graphs / "etiq_native.json").read_text())
        eligibility = json.loads((source / "private" / "etiq" / instance_id / "qualification" / "repeatability.json").read_text())
        composite, joins = build_appworld_etiq_composite(appworld, trace, etiq, eligibility)
        _write_json(private / "composite" / f"{instance_id}.json", composite)
        _write_json(private / "joins" / f"{instance_id}.json", joins)
        packages = [
            build_package_v2(
                arm, trace, truth.symptom, instance_id, _anchor_index(trace, truth), appworld,
                snapshot["initial_task_state"], snapshot["final_task_state"],
            )
            for arm in ONE_SHOT_ARMS
            if arm not in {*ETIQ_CONDITIONS, *STATE_GRAPH_CONDITIONS}
        ]
        packages += build_etiq_conditions(trace, truth.symptom, etiq, composite, max_tokens=200_000)
        packages += build_state_graph_conditions(
            trace, appworld, etiq, snapshot["initial_task_state"], snapshot["final_task_state"],
            max_tokens=200_000,
        )
        packages.sort(key=lambda package: ONE_SHOT_ARMS.index(package.arm))
        audit = _package_audit(instance_id, packages, truth)
        if not audit["passed"]:
            raise ValueError(f"{instance_id}: package isolation failed: {audit['violations']}")
        audits.append(audit)
        package_dir = public / "instances" / instance_id / "packages"
        package_dir.mkdir(parents=True)
        for package in packages:
            path = package_dir / f"{package.arm}.txt"
            path.write_text(package.text)
            row = {"instance_id": instance_id, "arm": package.arm, **package.metadata}
            rows.append(row)
            private_rows.append({**row, **mapped, "fault_class": truth.fault_class,
                                 "repair": truth.repair, "fault_occurred": truth.fault_occurred})
        flat = _flat_graph(appworld)
        public_trace = trace.to_dict()
        public_trace["source"] = {}
        walk = {"schema_version": 1, "instance_id": instance_id, "reported_artifact": truth.symptom,
                "trace": public_trace, "execution_graph": appworld}
        interactive = public / "interactive" / instance_id
        _write_json(interactive / "walk.json", walk)
        common_header = _common_with_calls(trace)
        for arm in INTERACTIVE_ARMS:
            text = round_package(trace.to_v1_observed(), truth.symptom, flat, [rec_node(truth.symptom)],
                                 [], [], 6, common_header=common_header)
            (interactive / f"{arm}.initial.txt").write_text(text)
    public_rows = [{key: value for key, value in row.items()} for row in rows]
    (public / "package_manifest.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in public_rows))
    (private / "package_truth_manifest.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in private_rows))
    _write_json(private / "package_size_inventory.json", rows)
    _write_json(private / "package_isolation_audit.json", {"passed": True, "instances": audits})
    _write_json(public / "one_shot_job_order.json", freeze_one_shot_schedule(rows))
    for arm in INTERACTIVE_ARMS:
        _write_json(public / f"interactive_{arm}_job_order.json", freeze_interactive_schedule(public, arm))
    code = json.loads((code_provenance / "code_provenance.json").read_text())
    identity = {
        "schema_version": 1, "code_snapshot_id": code["snapshot_id"],
        "code_provenance": str(code_provenance),
        "code_provenance_manifest_sha256": _sha(code_provenance / "MANIFEST.sha256.json"),
        "source_population": str(source), "source_population_manifest_sha256": _sha(source / "MANIFEST.sha256.json"),
        "reviewer_calls": 0,
    }
    _write_json(public / "build_identity.json", identity)
    _write_json(private / "source_population_binding.json", {**identity, "source_verification": source_check})
    summary = {"schema_version": 1, "instances": 42, "one_shot_arms": 30,
               "one_shot_packages": len(rows), "one_shot_jobs": len(rows),
               "interactive_arms": list(INTERACTIVE_ARMS), "reviewer_calls": 0,
               "isolation_passed": True}
    _write_json(root / "summary.json", summary)
    write_manifest(public)
    write_manifest(private)
    write_manifest(root)
    verify_unified(root)
    return summary


def verify_unified(root: Path) -> dict:
    problems = verify_manifest(root)
    problems += [f"public: {x}" for x in verify_manifest(root / "public")]
    problems += [f"private: {x}" for x in verify_manifest(root / "private")]
    if problems:
        raise ValueError(f"manifest verification failed: {problems[:5]}")
    rows = [json.loads(line) for line in (root / "public/package_manifest.jsonl").read_text().splitlines()]
    schedule = json.loads((root / "public/one_shot_job_order.json").read_text())
    if len(rows) != 1260 or len(schedule["jobs"]) != 1260:
        raise ValueError("unified build requires exactly 1,260 one-shot packages/jobs")
    if Counter(row["arm"] for row in rows) != Counter({arm: 42 for arm in ONE_SHOT_ARMS}):
        raise ValueError("one-shot arm counts differ")
    if schedule != freeze_one_shot_schedule(rows, schedule["seed"]):
        raise ValueError("one-shot schedule is not reproducible")
    for arm in INTERACTIVE_ARMS:
        frozen = json.loads((root / "public" / f"interactive_{arm}_job_order.json").read_text())
        if len(frozen["jobs"]) != 42 or frozen != freeze_interactive_schedule(root / "public", arm, SCHEDULE_SEED):
            raise ValueError(f"interactive {arm} schedule differs")
    return {"instances": 42, "one_shot_packages": 1260, "one_shot_jobs": 1260,
            "interactive_jobs": {"N": 42, "O": 42}, "manifests_verified": True}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--code-provenance", type=Path, required=True)
    build.add_argument("--source", type=Path, default=SOURCE_POPULATION)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build_unified(args.out, args.code_provenance, args.source) if args.command == "build" else verify_unified(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
