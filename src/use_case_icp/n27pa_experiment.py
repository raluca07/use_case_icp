"""N27PA DataFrame-native Jobs 3-4 pilot (append-only Attempt 045)."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from copy import deepcopy
import json
from itertools import product
from pathlib import Path
import random
import re
import time
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator
import networkx as nx

from . import corrected_experiment as ce
from . import n25_experiment as n25
from . import n27p_experiment as n27p
from .fault_preflight_v2 import validate_strict_provider_schema
from .job_store import JobStore
from .n05_program import _load_snapshot, _parse_output, _pipeline_payload, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline, jsonable


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-045")
ATTEMPT_044 = Path("outputs/fault-experiments-v2-2-n10/attempt-044")
TASK = Path("instructions_between_agent_types/developer/current/N27PA_dataframe_native_jobs_3_4_pilot.email.md")
TASK_SHA256 = "sha256:ca929eea12aaf6f37e6f8da4f325d3e7edf5440e48ab2177c832e3df805241a8"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27PA_dataframe_native_jobs_3_4_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:54730443a57d17630dd69d0373f4ed2f8a7c758e958e46fbba61d5040aae05cb"
SOURCE_FREEZE = Path("qualification/corrected-source-freeze.json")
JOB3_SOURCE = Path("src/use_case_icp/n27pa_campaign_portfolio.py")
JOB4_SOURCE = Path("src/use_case_icp/n27pa_campaign_activation.py")
PROMPT = n25.PROMPT
FINAL_SCHEMA = n25.FINAL_SCHEMA
REQUIRED_SCHEMA = n25.REQUIRED_SCHEMA
RECONSIDER_SCHEMA = n25.RECONSIDER_SCHEMA

JOB_ORDER = n25.JOB_ORDER
UPSTREAM, DOWNSTREAM, JOB3, JOB4 = JOB_ORDER
FUNCTIONS = n25.FUNCTIONS
INSTANCES = n27p.INSTANCES
TRUTH = n27p.TRUTH
CELLS = n27p.CELLS
MODE_NAMES = n25.MODE_NAMES
GRAPH_MODES = n25.GRAPH_MODES
ATTEMPT_044_HASHES = {
    "terminal-state.json": "sha256:83daad0b6fd62b591d9dbc15a0e52c1939ee590e98418cdf54ba12195f2ad287",
    "qualification/pre-live-blocking-native-compact-details.json": "sha256:2a7d82f12d2dd202b046836be8ba33823f3f9357ca50acd4ea3358ffc9d80f83",
    "qualification/fresh-native-captures.json": "sha256:c44312144c09515f941819875f6000520bf5757559ea7e1f8be69a537045a491",
}
PROTECTED = {
    **n25.PROTECTED,
    "src/use_case_icp/etiq_worker.py": "sha256:ca874e495723eeb794ecd0d8fe3bbd1dec53a5a596f36ecb5c9720c59fd12434",
}


class _DeterministicDiGraphMatcher(nx.algorithms.isomorphism.DiGraphMatcher):
    """Make VF2 candidate traversal stable across Python hash seeds."""

    def candidate_pairs_iter(self):
        yield from sorted(
            super().candidate_pairs_iter(),
            key=lambda pair: (str(pair[1]), str(pair[0])),
            reverse=True,
        )


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, value: str) -> None:
    create_bytes_exclusive(path, value.encode())


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PA authority input changed: {relative}")
    for root, bindings in n27p.PRESERVED.items():
        for relative, expected in bindings.items():
            if ce.sha256((repo_root / root / relative).read_bytes()) != expected:
                raise ValueError(f"N27PA preserved attempt changed: {root.name}/{relative}")
    for relative, expected in ATTEMPT_044_HASHES.items():
        if ce.sha256((repo_root / ATTEMPT_044 / relative).read_bytes()) != expected:
            raise ValueError(f"N27PA Attempt-044 binding changed: {relative}")
    for relative, expected in PROTECTED.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27PA protected surface changed: {relative}")
    source_freeze = _json(repo_root / ATTEMPT / SOURCE_FREEZE)
    ce._verified_self_hash(source_freeze, "freeze_sha256")
    expected_sources = {JOB3: JOB3_SOURCE, JOB4: JOB4_SOURCE}
    for job_id, relative in expected_sources.items():
        if source_freeze["source_hashes"][job_id] != ce.sha256((repo_root / relative).read_bytes()):
            raise ValueError(f"N27PA corrected source changed after clean freeze: {job_id}")
    return {
        "task": TASK_SHA256,
        "authority": AUTHORITY_SHA256,
        "attempt_044": deepcopy(ATTEMPT_044_HASHES),
        "corrected_source_freeze": source_freeze["freeze_sha256"],
        "corrected_source_hashes": deepcopy(source_freeze["source_hashes"]),
    }


def _pipeline(repo_root: Path, source_capture: Mapping[str, Any], job_id: str) -> GeneratedPipeline:
    if job_id not in {JOB3, JOB4}:
        raise ValueError(f"N27PA only creates corrected Jobs 3-4: {job_id}")
    source_path = JOB3_SOURCE if job_id == JOB3 else JOB4_SOURCE
    generated = "generated/protocol_2_2/" + (
        "campaign_portfolio_generation.py" if job_id == JOB3 else "campaign_activation_planning.py"
    )
    boundaries = []
    for realized in source_capture["jobs"][job_id]["realization"]["realized_boundaries"]:
        boundaries.append({
            "boundary_id": str(realized["boundary_id"]),
            "function_name": str(realized["function_name"]),
            "qualified_function_name": str(realized["function_name"]),
            "source_path": generated,
            "role": str(realized["role"]),
            "expected_inputs": deepcopy(realized["expected_inputs"]),
            "expected_outputs": deepcopy(realized["expected_outputs"]),
            "semantic_stage": str(realized["semantic_stage"]),
        })
    pipeline = GeneratedPipeline(
        entry_file=generated,
        files=[GeneratedFile(generated, (repo_root / source_path).read_text(encoding="utf-8"))],
        review_boundaries=boundaries,
    )
    pipeline.validate()
    return pipeline


def _load_fresh_execution(branch: Path, job_id: str) -> Any | None:
    if not branch.exists():
        return None
    runs = sorted(branch.glob(f"jobstore/{job_id}/stages/n05/*/runs/*"))
    if len(runs) != 1:
        raise ValueError(f"N27PA existing fresh branch is incomplete: {branch}")
    run_dir = runs[0]
    snapshot = _load_snapshot(JobStore(branch / "jobstore"), run_dir)
    if snapshot.scan_errors or not snapshot.nodes or not (run_dir / "etiq-native-lineage.json").is_file():
        raise ValueError(f"N27PA fresh Etiq capture is not reviewable: {branch}")
    return n25.EtiqExecution(snapshot=snapshot, run_dir=run_dir)


def _fresh_job(
    repo_root: Path,
    target: Path,
    source_capture: Mapping[str, Any],
    instance_id: str,
    job_id: str,
) -> tuple[dict[str, Any], GeneratedPipeline]:
    index = JOB_ORDER.index(job_id)
    pipeline = _pipeline(repo_root, source_capture, job_id)
    source_freeze = _json(target / SOURCE_FREEZE)
    source_path = JOB3_SOURCE if job_id == JOB3 else JOB4_SOURCE
    if ce.sha256((repo_root / source_path).read_bytes()) != source_freeze["source_hashes"][job_id]:
        raise ValueError("N27PA fresh execution source differs from clean-frozen source")
    branch = target / "capture-branches" / instance_id / f"canonical-v2-job-{index + 1}"
    execution = _load_fresh_execution(branch, job_id)
    if execution is None:
        materialize_opaque_branch(
            branch,
            allowlist={},
            manifest_identity={
                "purpose": "n27pa-frozen-source-capture",
                "instance": instance_id,
                "job": job_id,
                "source_freeze": source_freeze["freeze_sha256"],
            },
        )
        copy_etiq_worker_runtime(branch, repo_root / "src")
        execution = execute_pipeline_in_branch(
            branch,
            repo_root=repo_root,
            job_id=job_id,
            pipeline=pipeline,
            runtime_input=source_capture["jobs"][job_id]["input"],
            run_index=INSTANCES.index(instance_id),
            stage=f"n27pa-frozen-{index + 1}",
        )
    output = _parse_output(execution)
    if output != source_capture["jobs"][job_id]["output"]:
        raise ValueError(f"N27PA corrected business output mismatch: {instance_id}/{job_id}")
    if _json(execution.run_dir / "pipeline-input.json") != source_capture["jobs"][job_id]["input"]:
        raise ValueError(f"N27PA corrected business input mismatch: {instance_id}/{job_id}")
    native_path = execution.run_dir / "etiq-native-lineage.json"
    native = _json(native_path)
    realization = n25._realization(execution, pipeline, job_id)
    job = n25._job_record(execution, output, realization)
    job.update({
        "native_lineage": native,
        "native_lineage_file_sha256": ce.sha256(native_path.read_bytes()),
        "native_lineage_logical_sha256": ce.sha256(native),
        "native_lineage_export_status": execution.snapshot.inventories.get("json_lineage_export"),
    })
    return job, pipeline


def _composite_capture(repo_root: Path, target: Path, instance_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    source_path = repo_root / ATTEMPT_044 / "captures" / f"{instance_id}.json"
    source_bundle_path = repo_root / ATTEMPT_044 / "source-bundles" / f"{instance_id}.json"
    instance_path = repo_root / ATTEMPT_044 / "instances" / f"{instance_id}.json"
    source = _json(source_path)
    n25._verify_four_capture(source)
    jobs = {job: deepcopy(source["jobs"][job]) for job in (UPSTREAM, DOWNSTREAM)}
    job3, pipeline3 = _fresh_job(repo_root, target, source, instance_id, JOB3)
    job4, pipeline4 = _fresh_job(repo_root, target, source, instance_id, JOB4)
    jobs.update({JOB3: job3, JOB4: job4})
    handoffs = [deepcopy(value) for value in source["handoffs"] if value["downstream_job_id"] == DOWNSTREAM]
    handoffs.extend(n25._handoff(name, DOWNSTREAM, JOB3, jobs[DOWNSTREAM]["output"][name]) for name in ("coverage", "priorities", "recommendation", "metadata"))
    handoffs.extend(n25._handoff(name, JOB3, JOB4, job3["output"][name]) for name in ("campaign_portfolio", "metadata"))
    source_hashes = {
        UPSTREAM: source["source_sha256"][UPSTREAM],
        DOWNSTREAM: source["source_sha256"][DOWNSTREAM],
        JOB3: ce.sha256(_pipeline_payload(pipeline3)),
        JOB4: ce.sha256(_pipeline_payload(pipeline4)),
    }
    capture = {
        "schema_version": "n27pa-four-job-native-capture-1",
        "capture_id": stable_id("rerun-capture", ["n27pa", instance_id], 0),
        "instance_id": instance_id,
        "job_ids": list(JOB_ORDER),
        "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": source_hashes,
        "attempt_044_reuse": {
            "capture_file_sha256": ce.sha256(source_path.read_bytes()),
            "source_bundle_file_sha256": ce.sha256(source_bundle_path.read_bytes()),
            "instance_file_sha256": ce.sha256(instance_path.read_bytes()),
            "job_capture_sha256": {job: ce.sha256(source["jobs"][job]) for job in (UPSTREAM, DOWNSTREAM)},
            "native_logical_sha256": {job: source["jobs"][job]["native_lineage_logical_sha256"] for job in (UPSTREAM, DOWNSTREAM)},
        },
        "corrected_source_freeze_sha256": _json(target / SOURCE_FREEZE)["freeze_sha256"],
        "canonical": True,
        "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    n25._verify_four_capture(capture)
    source_bundle = _json(source_bundle_path)["source_bundle"][:2]
    source_bundle.extend([
        {"job_id": JOB3, "files": [{"path": pipeline3.files[0].path, "content": pipeline3.files[0].content}]},
        {"job_id": JOB4, "files": [{"path": pipeline4.files[0].path, "content": pipeline4.files[0].content}]},
    ])
    return capture, source_bundle, _json(instance_path)


def _topology_qualification(catalogue: Mapping[str, Any], index: Mapping[str, Any]) -> dict[str, Any]:
    diagnostic = n27p.compact_topology_diagnostics(catalogue)
    jobs = {}
    for job_id in JOB_ORDER:
        native = catalogue["jobs"][job_id]["native_graph"]
        clusters = {value["native_cluster_ref"]: value for value in native["clusters"]}

        def descendants(cluster_ref: str) -> set[str]:
            found = set()
            for member in clusters[cluster_ref]["member_refs"]:
                if member in clusters:
                    found |= descendants(member)
                else:
                    found.add(member)
            return found

        crossings = {}
        handoff_edges = []
        for cluster_ref in native["top_level_cluster_refs"]:
            subtree = descendants(cluster_ref)
            relevant = [
                edge for edge in native["edges"]
                if (edge["source_ref"] in subtree) != (edge["target_ref"] in subtree)
            ]
            label = clusters[cluster_ref]["captured_function_label"]
            crossings[label] = len(relevant)
            handoff_edges.extend({
                "function": label,
                "edge_ref": edge["native_edge_ref"],
                "source_ref": edge["source_ref"],
                "target_ref": edge["target_ref"],
            } for edge in relevant)
        top_labels = set(crossings)
        counts = index["job_counts"][job_id]
        passed = (
            top_labels == set(FUNCTIONS[job_id])
            and diagnostic[job_id]["root_node_count"] > 0
            and all(value > 0 for value in crossings.values())
            and counts["visible_nodes"] > 0
            and counts["visible_edges"] > 0
            and counts["visible_nodes"] < counts["full_nodes"]
            and counts["collapsed_clusters"] == 3
        )
        jobs[job_id] = {
            **diagnostic[job_id],
            "crossing_edges_per_top_level_function": crossings,
            "dataframe_handoff_native_edges": handoff_edges,
            "three_disclosable_function_subtrees": counts["collapsed_clusters"] == 3,
            "passed": passed,
        }
    if not all(value["passed"] for value in jobs.values()):
        raise ValueError(f"N27PA native topology qualification failed: {jobs}")
    return jobs


def _load_prepared(target: Path) -> dict[str, Any]:
    values = {
        name: {path.stem: _json(path) for path in sorted((target / folder).glob("*.json"))}
        for name, folder in (
            ("captures", "captures"), ("catalogues", "catalogues"),
            ("instances", "instances"), ("source_bundles", "source-bundles"),
            ("crosswalks", "native-crosswalks"), ("indexes", "native-subtree-index"),
        )
    }
    if any(set(collection) != set(INSTANCES) for collection in values.values()):
        raise ValueError("N27PA prepared record set is partial")
    for instance_id in INSTANCES:
        n25._verify_four_capture(values["captures"][instance_id])
        ce.verify_catalogue(values["catalogues"][instance_id])
        ce._verified_self_hash(values["instances"][instance_id], "instance_sha256")
        ce._verified_self_hash(values["crosswalks"][instance_id], "bundle_sha256")
        ce._verified_self_hash(values["indexes"][instance_id], "index_sha256")
        values["source_bundles"][instance_id] = values["source_bundles"][instance_id]["source_bundle"]
    return values


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27PA is authorized only for Attempt 045")
    authority = _verify_authority(repo_root)
    if (target / "captures").exists():
        return _load_prepared(target) | {"authority": authority}
    prepared = {name: {} for name in ("captures", "catalogues", "instances", "source_bundles", "crosswalks", "indexes")}
    topology = {}
    for instance_id in INSTANCES:
        capture, source_bundle, old_instance = _composite_capture(repo_root, target, instance_id)
        catalogue, crosswalk = n27p._catalogue(capture)
        catalogue["schema_version"] = "n27pa-four-job-native-catalogue-1"
        catalogue.pop("catalogue_sha256", None)
        catalogue["catalogue_sha256"] = ce.sha256(catalogue)
        compact, index = n27p.build_compact_graph(catalogue, crosswalk)
        topology[instance_id] = _topology_qualification(catalogue, index)
        instance = {
            "schema_version": "n27pa-instance-1",
            "instance_id": instance_id,
            "designation": "matched_clean_control" if TRUTH[instance_id] is None else "upstream_fault",
            "truth_job": None if TRUTH[instance_id] is None else UPSTREAM,
            "truth_function": TRUTH[instance_id],
            "mutation": deepcopy(old_instance.get("mutation")),
            "attempt_044_instance_sha256": old_instance["instance_sha256"],
            "capture_sha256": capture["capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "source_sha256": deepcopy(capture["source_sha256"]),
        }
        instance["instance_sha256"] = ce.sha256(instance)
        ce._write_immutable(target / "captures" / f"{instance_id}.json", capture)
        ce._write_immutable(target / "catalogues" / f"{instance_id}.json", catalogue)
        ce._write_immutable(target / "source-bundles" / f"{instance_id}.json", {"source_bundle": source_bundle})
        ce._write_immutable(target / "native-crosswalks" / f"{instance_id}.json", crosswalk)
        ce._write_immutable(target / "native-subtree-index" / f"{instance_id}.json", index)
        ce._write_immutable(target / "instances" / f"{instance_id}.json", instance)
        ce._write_immutable(target / "projections" / f"{instance_id}-compact.json", compact)
        for job_id in JOB_ORDER:
            raw = capture["jobs"][job_id]["native_lineage"]
            export_path = target / "native-exports" / instance_id / job_id / "etiq-native-lineage.json"
            ce._write_immutable(export_path, raw)
            status = "reused_attempt_044_exact_hash" if job_id in {UPSTREAM, DOWNSTREAM} else "fresh_n27pa_execution"
            record = {
                "schema_version": "n27pa-per-job-native-capture-1",
                "instance_id": instance_id,
                "job_id": job_id,
                "capture_status": status,
                "job_capture_sha256": ce.sha256(capture["jobs"][job_id]),
                "native_export_file_sha256": ce.sha256(export_path.read_bytes()),
                "native_logical_sha256": capture["jobs"][job_id]["native_lineage_logical_sha256"],
                "source_sha256": capture["source_sha256"][job_id],
            }
            record["record_sha256"] = ce.sha256(record)
            ce._write_immutable(target / "job-captures" / instance_id / f"{job_id}.json", record)
        for key, value in (
            ("captures", capture), ("catalogues", catalogue), ("instances", instance),
            ("source_bundles", source_bundle), ("crosswalks", crosswalk), ("indexes", index),
        ):
            prepared[key][instance_id] = value
    source_hashes = {job: prepared["captures"][INSTANCES[0]]["source_sha256"][job] for job in (JOB3, JOB4)}
    if any(prepared["captures"][instance]["source_sha256"][job] != source_hashes[job] for instance in INSTANCES for job in (JOB3, JOB4)):
        raise ValueError("N27PA corrected sources differ across instances")
    qualification = {
        "schema_version": "n27pa-capture-topology-qualification-1",
        "status": "passed",
        "reused_job_1_2_captures": 8,
        "fresh_job_3_4_captures": 8,
        "composite_captures": 4,
        "source_hashes": source_hashes,
        "corrected_source_freeze_sha256": authority["corrected_source_freeze"],
        "topology": topology,
        "all_business_inputs_outputs_equal": True,
        "all_native_objects_edges_preserved": True,
    }
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification/capture-topology.json", qualification)
    return prepared | {"authority": authority}


def _random_signature(nodes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(nodes)
    return {
        "native_kind": dict(sorted(Counter(str(value["native_kind"]) for value in values).items())),
        "native_cluster_depth": dict(sorted(Counter(str(value.get("native_cluster_depth")) for value in values).items())),
        "source_bearing": sum(bool(value.get("source")) for value in values),
        "inspectable_artifact": sum(value.get("artifact_content") is not None for value in values),
    }


def _random_groups(
    catalogue: Mapping[str, Any],
    index: Mapping[str, Any],
    job_id: str,
    visible_refs: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    descriptors = []
    clusters = []
    native_clusters = {
        value["native_cluster_ref"]: value
        for value in catalogue["jobs"][job_id]["native_graph"]["clusters"]
    }
    for group_id, binding in sorted(index["groups"].items()):
        descriptor = binding["descriptor"]
        if descriptor["job_id"] != job_id:
            continue
        members = set(binding["node_refs"])
        hidden = members - visible_refs
        if not hidden:
            continue
        updated = {
            **deepcopy(descriptor),
            "visible_interface_node_refs": sorted(members & visible_refs),
            "hidden_node_count": len(hidden),
            "hidden_size_class": n27p._cluster_size_class(len(hidden)),
        }
        descriptors.append(updated)
        clusters.append({
            "native_cluster_ref": group_id,
            "job_id": job_id,
            "captured_function_label": native_clusters[group_id]["captured_function_label"],
            "cluster_depth": 0,
            "visible_member_refs": deepcopy(updated["visible_interface_node_refs"]),
            "hidden_node_count": len(hidden),
            "collapsed": True,
        })
    return descriptors, clusters


def _random_candidates(
    catalogue: Mapping[str, Any],
    compact: Mapping[str, Any],
    index: Mapping[str, Any],
    job_id: str,
) -> list[dict[str, Any]]:
    native = catalogue["jobs"][job_id]["native_graph"]
    nodes = {value["native_node_ref"]: value for value in native["nodes"]}
    target_nodes = {value["native_node_ref"]: value for value in compact["nodes"] if value["job_id"] == job_id}
    target_refs = frozenset(target_nodes)
    target_groups = [value for value in compact["collapsed_execution_groups"] if value["job_id"] == job_id]
    target_classes = Counter(value["hidden_size_class"] for value in target_groups)
    full_graph = nx.DiGraph()
    full_graph.add_nodes_from(nodes)
    full_graph.add_edges_from((edge["source_ref"], edge["target_ref"]) for edge in native["edges"])
    target_graph = full_graph.subgraph(list(target_nodes)).copy()
    matcher = _DeterministicDiGraphMatcher(full_graph, target_graph)
    expected_signature = _random_signature(target_nodes.values())
    seen: set[frozenset[str]] = set()
    candidates = []
    for mapping_number, mapping in enumerate(matcher.subgraph_isomorphisms_iter(), 1):
        if mapping_number > 100_000:
            break
        refs = frozenset(str(value) for value in mapping)
        if refs in seen:
            continue
        seen.add(refs)
        if refs == target_refs or _random_signature(nodes[ref] for ref in refs) != expected_signature:
            continue
        groups, clusters = _random_groups(catalogue, index, job_id, set(refs))
        if len(groups) != 3 or Counter(value["hidden_size_class"] for value in groups) != target_classes:
            continue
        relationships = [
            deepcopy(edge) for edge in native["edges"]
            if edge["source_ref"] in refs and edge["target_ref"] in refs
        ]
        if len(relationships) != len(target_graph.edges):
            continue
        candidate_nodes = [deepcopy(nodes[ref]) for ref in sorted(refs)]
        candidates.append({
            "nodes": candidate_nodes,
            "relationships": relationships,
            "collapsed_execution_groups": groups,
            "native_clusters": clusters,
            "tokens": n25._token_count({
                "nodes": candidate_nodes,
                "relationships": relationships,
                "collapsed_execution_groups": groups,
                "native_clusters": clusters,
            }),
        })
        if len(candidates) >= 32:
            break
    if not candidates:
        raise ValueError(f"N27PA Random has no real matched native subgraph: {job_id}")
    return candidates


def random_structural_graph(
    catalogue: Mapping[str, Any],
    compact: Mapping[str, Any],
    index: Mapping[str, Any],
    seed: int,
    selected_refs: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    generator = random.Random(seed)
    selections = {}
    diagnostics = {}
    for job_id in JOB_ORDER:
        target_nodes = [value for value in compact["nodes"] if value["job_id"] == job_id]
        target_edges = [value for value in compact["relationships"] if value["job_id"] == job_id]
        if selected_refs is None:
            candidates = _random_candidates(catalogue, compact, index, job_id)
            target_tokens = n25._token_count({
                "nodes": target_nodes,
                "relationships": target_edges,
                "collapsed_execution_groups": [value for value in compact["collapsed_execution_groups"] if value["job_id"] == job_id],
                "native_clusters": [value for value in compact["native_clusters"] if value["job_id"] == job_id],
            })
            candidates.sort(key=lambda value: (abs(value["tokens"] - target_tokens), ce.sha256(value["nodes"])))
            best_difference = abs(candidates[0]["tokens"] - target_tokens)
            tied = [value for value in candidates if abs(value["tokens"] - target_tokens) == best_difference]
            chosen = tied[generator.randrange(len(tied))]
            eligible = len(candidates)
        else:
            refs = set(selected_refs[job_id])
            native = catalogue["jobs"][job_id]["native_graph"]
            nodes = {value["native_node_ref"]: value for value in native["nodes"]}
            edges = [deepcopy(value) for value in native["edges"] if value["source_ref"] in refs and value["target_ref"] in refs]
            groups, clusters = _random_groups(catalogue, index, job_id, refs)
            chosen = {
                "nodes": [deepcopy(nodes[ref]) for ref in sorted(refs)],
                "relationships": edges,
                "collapsed_execution_groups": groups,
                "native_clusters": clusters,
            }
            eligible = None
        if len(chosen["nodes"]) != len(target_nodes) or len(chosen["relationships"]) != len(target_edges):
            raise ValueError(f"N27PA Random node/edge count mismatch: {job_id}")
        if _random_signature(chosen["nodes"]) != _random_signature(target_nodes):
            raise ValueError(f"N27PA Random visibility stratum mismatch: {job_id}")
        if not chosen["relationships"]:
            raise ValueError(f"N27PA Random has a zero-edge job: {job_id}")
        target_degrees = sorted(
            (sum(edge["source_ref"] == ref for edge in target_edges), sum(edge["target_ref"] == ref for edge in target_edges))
            for ref in {node["native_node_ref"] for node in target_nodes}
        )
        chosen_degrees = sorted(
            (sum(edge["source_ref"] == ref for edge in chosen["relationships"]), sum(edge["target_ref"] == ref for edge in chosen["relationships"]))
            for ref in {node["native_node_ref"] for node in chosen["nodes"]}
        )
        if chosen_degrees != target_degrees:
            raise ValueError(f"N27PA Random directed degree pattern mismatch: {job_id}")
        selections[job_id] = chosen
        diagnostics[job_id] = {
            "selected_node_refs": [value["native_node_ref"] for value in chosen["nodes"]],
            "eligible_alternatives": eligible,
            "node_count": len(chosen["nodes"]),
            "edge_count": len(chosen["relationships"]),
            "native_kind_distribution": _random_signature(chosen["nodes"])["native_kind"],
            "native_cluster_depth_distribution": _random_signature(chosen["nodes"])["native_cluster_depth"],
            "directed_degree_pattern": chosen_degrees,
            "source_bearing_count": _random_signature(chosen["nodes"])["source_bearing"],
            "inspectable_artifact_count": _random_signature(chosen["nodes"])["inspectable_artifact"],
            "collapsed_group_count": len(chosen["collapsed_execution_groups"]),
            "hidden_size_classes": dict(sorted(Counter(value["hidden_size_class"] for value in chosen["collapsed_execution_groups"]).items())),
            "endpoint_closure": True,
        }
    value = {
        "job_evidence_order": deepcopy(compact["job_evidence_order"]),
        "nodes": [node for job in JOB_ORDER for node in selections[job]["nodes"]],
        "relationships": [edge for job in JOB_ORDER for edge in selections[job]["relationships"]],
        "native_clusters": [cluster for job in JOB_ORDER for cluster in selections[job]["native_clusters"]],
        "collapsed_execution_groups": [group for job in JOB_ORDER for group in selections[job]["collapsed_execution_groups"]],
        "disclosed_execution_groups": [],
        "handoffs": [],
    }
    target_tokens = n25._token_count({key: compact[key] for key in ("nodes", "relationships", "native_clusters", "collapsed_execution_groups")})
    observed_tokens = n25._token_count({key: value[key] for key in ("nodes", "relationships", "native_clusters", "collapsed_execution_groups")})
    relative = abs(observed_tokens - target_tokens) / max(1, target_tokens)
    if relative > 0.03:
        raise ValueError(f"N27PA Random token match exceeds three percent: {relative}")
    value["random_structural_match"] = {
        "selection_rule": "seeded oracle-blind real-native subgraph draw matched to Compact Fixed",
        "seed_commitment": ce.sha256(["n27pa-random-structural", seed]),
        "uses_truth_or_outcome": False,
        "target_tokens": target_tokens,
        "observed_tokens": observed_tokens,
        "relative_token_difference": relative,
        "jobs": diagnostics,
    }
    value["projection_sha256"] = ce.sha256(value)
    return value


def adaptive_relevance(prepared: Mapping[str, Any], target: Path | None = None) -> dict[str, Any]:
    target = target or ATTEMPT
    clean_id = "four_stage_clean_control"
    clean_nodes = prepared["catalogues"][clean_id]["jobs"][UPSTREAM]["nodes"]
    results = {}
    for instance_id in INSTANCES:
        if TRUTH[instance_id] is None:
            continue
        instance = prepared["instances"][instance_id]
        mutation = instance["mutation"]
        canonical_nodes = prepared["catalogues"][instance_id]["jobs"][UPSTREAM]["nodes"]
        start_line = int(mutation["original_span"]["start_line"])
        if instance_id == "select_threshold_omission":
            candidates = [
                node for node in canonical_nodes
                if node.get("state_type") == "DataframeState"
                and node.get("line_no") == start_line
                and str(mutation["mutant_snippet"]) in str(node.get("source"))
                and node.get("artifact_value_sha256")
            ]
            basis = "executed DataFrame state on the exact mutated source span"
            clean_comparison = None
        else:
            clean_by_shape = {
                (node.get("line_no"), node.get("state_type"), node.get("source"), tuple(node.get("names", []))): node
                for node in clean_nodes if node.get("artifact_value_sha256")
            }
            candidates = []
            comparisons = {}
            for node in canonical_nodes:
                stack = ",".join(str(value) for value in node.get("func_stack", []))
                key = (node.get("line_no"), node.get("state_type"), node.get("source"), tuple(node.get("names", [])))
                clean = clean_by_shape.get(key)
                if (
                    node.get("line_no") is not None
                    and int(node["line_no"]) >= start_line
                    and mutation["qualified_function_name"] in stack
                    and node.get("artifact_value_sha256")
                    and clean is not None
                    and clean["artifact_value_sha256"] != node["artifact_value_sha256"]
                ):
                    candidates.append(node)
                    comparisons[node["node_ref"]] = {
                        "clean_artifact_value_sha256": clean["artifact_value_sha256"],
                        "faulty_artifact_value_sha256": node["artifact_value_sha256"],
                    }
            candidates.sort(key=lambda node: (int(node["line_no"]), str(node["node_ref"])))
            clean_comparison = comparisons.get(candidates[0]["node_ref"]) if candidates else None
            basis = "first executed DataFrame state after the mutation whose exact artifact differs from clean"
        if not candidates:
            raise ValueError(f"N27PA lacks exact mutation/direct-state evidence: {instance_id}")
        canonical = candidates[0]
        mappings = prepared["crosswalks"][instance_id]["jobs"][UPSTREAM]["crosswalk"]
        exact = [
            value for value in mappings
            if value["match_status"] == "exact" and canonical["node_ref"] in value["canonical_node_refs"]
        ]
        compact = _json(target / "projections" / f"{instance_id}-compact.json")
        visible = {value["native_node_ref"] for value in compact["nodes"]}
        hidden_exact = [value for value in exact if value["native_node_ref"] not in visible]
        if hidden_exact:
            exact = hidden_exact
        if len(exact) != 1:
            raise ValueError(f"N27PA exact native relevance crosswalk is ambiguous: {instance_id}")
        native_ref = exact[0]["native_node_ref"]
        index = prepared["indexes"][instance_id]
        groups = [
            group_id for group_id, binding in index["groups"].items()
            if binding["descriptor"]["job_id"] == UPSTREAM and native_ref in binding["node_refs"]
        ]
        if len(groups) != 1:
            raise ValueError(f"N27PA exact native relevance group is ambiguous: {instance_id}")
        group_id = groups[0]
        descriptor = index["groups"][group_id]["descriptor"]
        if descriptor["captured_function_label"] != TRUTH[instance_id]:
            raise ValueError(f"N27PA exact affected state is outside the truth subtree: {instance_id}")
        if native_ref in visible:
            raise ValueError(f"N27PA exact affected state is initially visible: {instance_id}")
        native_edges = prepared["catalogues"][instance_id]["jobs"][UPSTREAM]["native_graph"]["edges"]
        incident = [edge["native_edge_ref"] for edge in native_edges if native_ref in {edge["source_ref"], edge["target_ref"]}]
        if not incident:
            raise ValueError(f"N27PA exact affected state lacks native lineage: {instance_id}")
        package = {"available_operations": ["expand_execution_group"], "graph_review": {"evidence": deepcopy(compact)}}
        expanded, event = n27p.expand_native_subtree(
            prepared["catalogues"][instance_id], index, package, group_id
        )
        added = set(event["nodes_added"])
        if native_ref not in added or not set(incident) & set(event["relationships_added"]):
            raise ValueError(f"N27PA relevant Adaptive subtree does not disclose the affected lineage: {instance_id}")
        permitted = set(index["groups"][group_id]["node_refs"])
        if not added <= permitted or len(expanded["graph_review"]["evidence"]["disclosed_execution_groups"]) != 1:
            raise ValueError(f"N27PA Adaptive relevance simulation escaped one subtree: {instance_id}")
        results[instance_id] = {
            "truth_function": TRUTH[instance_id],
            "proof_basis": basis,
            "mutation_span": deepcopy(mutation["original_span"]),
            "canonical_state_ref": canonical["node_ref"],
            "canonical_state_line": canonical["line_no"],
            "canonical_state_source": canonical["source"],
            "clean_comparison": clean_comparison,
            "native_node_ref": native_ref,
            "native_incident_edge_refs": incident,
            "model_selectable_execution_group_id": group_id,
            "initially_hidden": True,
            "disclosed_by_complete_subtree": True,
            "function_name_match_alone_used_as_relevance_proof": False,
        }
    if set(results) != set(INSTANCES[:-1]):
        raise ValueError("N27PA did not qualify all three Job-1 faults")
    record = {"schema_version": "n27pa-adaptive-fault-relevance-1", "status": "passed", "instances": results}
    record["qualification_sha256"] = ce.sha256(record)
    return record


def build_package(
    catalogue: Mapping[str, Any],
    source_bundle: list[dict[str, Any]],
    graphs: Mapping[str, Mapping[str, Any]],
    mode: str,
    source_setting: str,
    declaration_setting: str,
) -> dict[str, Any]:
    package = n25._base_package(catalogue, include_job4_logs=mode != "E01")
    package["schema_version"] = "n27pa-four-stage-review-package-1"
    if mode in {"E03", "E04"}:
        package["history"] = {"prior_task_records": []}
        if mode == "E04":
            for job_id in JOB_ORDER[:3]:
                record = n25._execution_record(catalogue, job_id, True)
                record["chronology"] = {
                    "position": JOB_ORDER.index(job_id) + 1,
                    "precedes": f"job_{JOB_ORDER.index(job_id) + 2}",
                }
                record["exact_outgoing_handoffs"] = [
                    deepcopy(value) for value in catalogue["handoffs"]
                    if value["upstream_job_id"] == job_id
                ]
                package["history"]["prior_task_records"].append(record)
    if mode in GRAPH_MODES:
        if mode == "E05":
            evidence = n25.empty_graph()
        elif mode == "E06":
            evidence = {
                "job_evidence_order": deepcopy(graphs["compact"]["job_evidence_order"]),
                "nodes": deepcopy(graphs["compact"]["nodes"]),
                "relationships": [],
                "native_clusters": [],
                "collapsed_execution_groups": [],
                "disclosed_execution_groups": [],
                "handoffs": [],
            }
            evidence["projection_sha256"] = ce.sha256(evidence)
        elif mode in {"E07", "E08", "E09"}:
            evidence = deepcopy(graphs["compact"])
        elif mode == "E10":
            evidence = deepcopy(graphs["full"])
        else:
            evidence = deepcopy(graphs["random"])
            evidence.pop("random_structural_match", None)
            evidence.pop("projection_sha256", None)
            evidence["projection_sha256"] = ce.sha256(evidence)
        package["graph_review"] = {
            "framing": "Captured execution evidence may be used in the assessment.",
            "evidence": evidence,
        }
    if source_setting == "S1":
        package["separate_complete_source_bundle"] = deepcopy(source_bundle)
    if declaration_setting == "B1":
        package["semantic_declaration_bundle"] = n25._semantic_declarations(catalogue)
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
        for cell_id in CELLS:
            mode, source, declarations = cell_id.split("-")
            cells.append({
                "instance_id": instance_id,
                "cell_id": cell_id,
                "mode": mode,
                "mode_name": MODE_NAMES[mode],
                "source_setting": source,
                "declaration_setting": declarations,
                "branch_id": f"brn-{ce.sha256(['n27pa', instance_id, cell_id])[7:23]}",
            })
    reviews = []
    for repetition in (1, 2):
        order = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for block, instance_id in enumerate(order):
            values = [value for value in cells if value["instance_id"] == instance_id]
            rotation = (block + repetition) % len(values)
            for cell in values[rotation:] + values[:rotation]:
                reviews.append({
                    **cell,
                    "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n27pa', cell['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                })
    if (len(cells), len(reviews), len({value["trial_id"] for value in reviews})) != (64, 128, 128):
        raise AssertionError("N27PA pilot schedule changed")
    return {"cells": cells, "review_trials": reviews, "repair_traces": []}


def _schema_for(mode: str, follow_up: bool = False) -> Path:
    if follow_up or mode not in {"E08", "E09"}:
        return FINAL_SCHEMA
    return REQUIRED_SCHEMA if mode == "E08" else RECONSIDER_SCHEMA


def validate_schemas(repo_root: Path) -> dict[str, str]:
    return n25.validate_schemas(repo_root)


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    visible = ce.canonical_json(request).decode()
    forbidden_keys = (
        "instance_id", "cell_id", "source_setting", "declaration_setting", "branch_id",
        "trial_id", "repetition", "seed", "truth_job", "truth_function", "designation",
        "mutation", "oracle", "qualification", "clean_comparison", "random_structural_match",
    )
    if any(f'"{key}"' in visible for key in forbidden_keys):
        raise ValueError("N27PA rendered request leaks controller state")
    if any(value in visible for value in (*INSTANCES, "matched_clean_control", "upstream_fault")):
        raise ValueError("N27PA rendered request leaks instance or designation")
    return request


def _package_records(target: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((target / "controller-manifests").glob("*.json")):
        manifest = _json(path)
        package_path = target / manifest["reviewer_package_path"]
        if ce.sha256(package_path.read_bytes()) != manifest["reviewer_package_file_sha256"]:
            raise ValueError("N27PA package file binding changed")
        record = _json(package_path)
        if ce._verified_self_hash(record, "package_sha256") != manifest["package_sha256"]:
            raise ValueError("N27PA package logical binding changed")
        records.append(record)
    return records


def _initial_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value) for key, value in package.items()
        if key not in {"available_operations", "interaction_contract"}
    }


def _pairwise_checks(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by = {
        (value["controller_condition"]["instance_id"], value["controller_condition"]["cell_id"]): value["reviewer_package"]
        for value in records
    }
    specifications = (
        ("job4_logs", "E01-S1-B0", "E02-S1-B0", {"observed_job_4_execution"}, False),
        ("complete_source", "E02-S0-B0", "E02-S1-B0", {"separate_complete_source_bundle"}, False),
        ("boundaries", "E02-S1-B0", "E02-S1-B1", {"semantic_declaration_bundle"}, False),
        ("empty_history", "E02-S1-B0", "E03-S1-B0", {"history"}, False),
        ("actual_history", "E03-S1-B0", "E04-S1-B0", {"history"}, False),
        ("empty_graph", "E02-S1-B0", "E05-S1-B0", {"graph_review"}, False),
        ("compact_nodes", "E05-S1-B0", "E06-S1-B0", {"graph_review"}, False),
        ("compact_fixed", "E06-S1-B0", "E07-S1-B0", {"graph_review"}, False),
        ("adaptive_initial", "E07-S1-B0", "E08-S1-B0", set(), True),
        ("reconsider_initial", "E07-S1-B0", "E09-S1-B0", set(), True),
        ("full_graph", "E05-S1-B0", "E10-S1-B0", {"graph_review"}, False),
        ("random_structural", "E07-S1-B0", "E11-S1-B0", {"graph_review"}, False),
        ("compact_source", "E07-S0-B0", "E07-S1-B0", {"separate_complete_source_bundle"}, False),
        ("compact_boundaries", "E07-S1-B0", "E07-S1-B1", {"semantic_declaration_bundle"}, False),
    )
    rows = []
    for instance_id in INSTANCES:
        for name, left_id, right_id, roots, initial in specifications:
            left, right = by[(instance_id, left_id)], by[(instance_id, right_id)]
            if initial:
                left, right = _initial_evidence(left), _initial_evidence(right)
            paths = n25._diff_paths(left, right)
            passed = all(path.split(".")[1] in roots for path in paths) and bool(paths or not roots)
            rows.append({
                "instance_id": instance_id,
                "invariant": name,
                "left": left_id,
                "right": right_id,
                "differing_paths": paths,
                "allowed_roots": sorted(roots),
                "passed": passed,
            })
    if not all(row["passed"] for row in rows):
        raise ValueError(f"N27PA paired isolation failed: {[row for row in rows if not row['passed']][:2]}")
    return rows


def qualify_packages(
    repo_root: Path,
    records: list[Mapping[str, Any]],
    prepared: Mapping[str, Any],
    design: Mapping[str, Any],
) -> dict[str, Any]:
    schemas = validate_schemas(repo_root)
    if (len(records), len(design["review_trials"]), len(design["repair_traces"])) != (64, 128, 0):
        raise ValueError("N27PA package or schedule count changed")
    if sum(value["mode"] == "E08" for value in design["review_trials"]) != 16:
        raise ValueError("N27PA Adaptive follow-up count changed")
    if sum(value["mode"] == "E09" for value in design["review_trials"]) != 8:
        raise ValueError("N27PA Reconsideration count changed")
    maximum_tokens = 0
    simulations = 0
    modes = set()
    for record in records:
        condition = record["controller_condition"]
        package = record["reviewer_package"]
        request = render_request(package)
        maximum_tokens = max(maximum_tokens, n25._token_count(request))
        modes.add(condition["mode"])
        if condition["mode"] == "E08":
            groups = package["graph_review"]["evidence"]["collapsed_execution_groups"]
            expanded, event = n27p.expand_native_subtree(
                prepared["catalogues"][condition["instance_id"]],
                prepared["indexes"][condition["instance_id"]],
                package,
                groups[0]["execution_group_id"],
            )
            if event["status"] != "completed" or len(expanded["graph_review"]["evidence"]["disclosed_execution_groups"]) != 1:
                raise ValueError("N27PA Adaptive no-model simulation failed")
            simulations += 1
        if condition["mode"] == "E09" and package["interaction_contract"]["evidence_bytes_added"] != 0:
            raise ValueError("N27PA Reconsideration adds evidence")
        declarations = package.get("semantic_declaration_bundle", {}).get("semantic_declarations", [])
        if condition["declaration_setting"] == "B1" and len(declarations) != 12:
            raise ValueError("N27PA B1 does not contain all twelve declarations")
    if modes != set(MODE_NAMES):
        raise ValueError("N27PA does not represent every evidence mode")
    pairwise = _pairwise_checks(records)
    topology = _json(repo_root / ATTEMPT / "qualification/capture-topology.json")
    relevance = _json(repo_root / ATTEMPT / "qualification/adaptive-fault-relevance.json")
    random_match = _json(repo_root / ATTEMPT / "qualification/random-structural-matches.json")
    if topology["status"] != "passed" or relevance["status"] != "passed" or not random_match["all_strata_matched"]:
        raise ValueError("N27PA prerequisite qualification changed")
    return {
        "schema_version": "n27pa-no-model-verification-1",
        "status": "passed",
        "model_calls": 0,
        "instances": 4,
        "reused_job_1_2_captures": 8,
        "fresh_job_3_4_captures": 8,
        "cells_per_instance": 16,
        "packages": 64,
        "terminal_reviews": 128,
        "adaptive_followups": 16,
        "reconsideration_calls": 8,
        "planned_provider_calls": 152,
        "repairs": 0,
        "strict_schema_hashes": schemas,
        "pairwise_checks": len(pairwise),
        "no_model_adaptive_simulations": simulations,
        "maximum_estimated_input_tokens": maximum_tokens,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    existing = _package_records(target)
    if existing:
        qualification = qualify_packages(repo_root, existing, prepared, design)
        return {"prepared": prepared, "records": existing, "design": design, "qualification": qualification}
    relevance = adaptive_relevance(prepared, target)
    ce._write_immutable(target / "qualification/adaptive-fault-relevance.json", relevance)
    compact_graphs = {
        instance_id: _json(target / "projections" / f"{instance_id}-compact.json")
        for instance_id in INSTANCES
    }
    clean_id = "four_stage_clean_control"
    seed = int(ce.sha256([
        prepared["captures"][clean_id]["capture_sha256"],
        prepared["authority"]["corrected_source_freeze"],
        "n27pa-random-structural",
    ])[7:23], 16)
    clean_random = random_structural_graph(
        prepared["catalogues"][clean_id],
        compact_graphs[clean_id],
        prepared["indexes"][clean_id],
        seed,
    )
    graphs = {}
    structural = {}
    for instance_id in INSTANCES:
        random_graph = clean_random if instance_id == clean_id else random_structural_graph(
            prepared["catalogues"][instance_id],
            compact_graphs[instance_id],
            prepared["indexes"][instance_id],
            seed,
        )
        graphs[instance_id] = {
            "compact": compact_graphs[instance_id],
            "full": n27p.full_graph(prepared["catalogues"][instance_id]),
            "random": random_graph,
        }
        structural[instance_id] = deepcopy(random_graph["random_structural_match"])
        ce._write_immutable(target / "projections" / f"{instance_id}-full.json", graphs[instance_id]["full"])
        ce._write_immutable(target / "projections" / f"{instance_id}-random.json", random_graph)
    random_qualification = {
        "schema_version": "n27pa-random-structural-matches-1",
        "selection_source": "clean-seeded native structural and token strata only",
        "seed_commitment": ce.sha256(["n27pa-random-structural", seed]),
        "selected_refs_by_instance_job": {
            instance: {
                job: value["selected_node_refs"]
                for job, value in diagnostic["jobs"].items()
            }
            for instance, diagnostic in structural.items()
        },
        "instances": structural,
        "all_strata_matched": True,
        "every_job_has_native_relationship": True,
        "endpoint_closure": True,
        "token_tolerance": 0.03,
        "uses_truth_or_outcome": False,
    }
    random_qualification["qualification_sha256"] = ce.sha256(random_qualification)
    ce._write_immutable(target / "qualification/random-structural-matches.json", random_qualification)
    records = []
    for condition in design["cells"]:
        instance_id = condition["instance_id"]
        package = build_package(
            prepared["catalogues"][instance_id],
            prepared["source_bundles"][instance_id],
            graphs[instance_id],
            condition["mode"],
            condition["source_setting"],
            condition["declaration_setting"],
        )
        record = {
            "schema_version": "n27pa-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "capture_sha256": prepared["captures"][instance_id]["capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance_id]["catalogue_sha256"],
            "source_bundle_file_sha256": ce.sha256((target / "source-bundles" / f"{instance_id}.json").read_bytes()),
            "native_subtree_index_file_sha256": ce.sha256((target / "native-subtree-index" / f"{instance_id}.json").read_bytes()),
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        branch = condition["branch_id"]
        path = target / "packages" / branch / "reviewer-package.json"
        ce._write_immutable(path, record)
        manifest = {
            "schema_version": "n27pa-controller-manifest-1",
            "controller_condition": deepcopy(condition),
            "reviewer_package_path": path.relative_to(target).as_posix(),
            "reviewer_package_file_sha256": ce.sha256(path.read_bytes()),
            "package_sha256": record["package_sha256"],
        }
        manifest["manifest_sha256"] = ce.sha256(manifest)
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
        records.append(record)
    qualification = qualify_packages(repo_root, records, prepared, design)
    exposure = {record["controller_condition"]["branch_id"]: n25.exposure_manifest(record) for record in records}
    pairwise = {
        "schema_version": "n27pa-pairwise-package-differences-1",
        "rows": _pairwise_checks(records),
        "all_passed": True,
    }
    pairwise["report_sha256"] = ce.sha256(pairwise)
    ce._write_immutable(target / "package-exposure-manifest.json", {"schema_version": "n27pa-exposure-manifest-1", "packages": exposure})
    ce._write_immutable(target / "pairwise-package-differences.json", pairwise)
    ce._write_immutable(target / "review-design.json", {"schema_version": "n27pa-review-design-1", "review_trials": design["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"schema_version": "n27pa-repair-design-1", "repair_traces": []})
    ce._write_immutable(target / "qualification/no-model-verification.json", qualification)
    return {"prepared": prepared, "records": records, "design": design, "qualification": qualification}


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n27pa_experiment.py"), JOB3_SOURCE, JOB4_SOURCE,
        PROMPT, FINAL_SCHEMA, REQUIRED_SCHEMA, RECONSIDER_SCHEMA,
        Path("tests/test_n27pa_experiment.py"),
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    path = target / "experiment-freeze.json"
    if path.exists():
        raise FileExistsError("N27PA Attempt 045 is already frozen")
    if list((target / "reviews").glob("*.json")):
        raise ValueError("N27PA cannot freeze after reviews exist")
    built = build_attempt(repo_root, target)
    focused = target / "qualification/focused-test-results.json"
    if not focused.exists() or _json(focused).get("status") != "passed":
        raise ValueError("N27PA focused tests must pass before freeze")
    freeze = {
        "schema_version": "n27pa-experiment-freeze-1",
        "attempt": "045",
        "status": "frozen_before_live_pilot",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "protected_hashes": deepcopy(PROTECTED),
        "attempt_044_hashes": deepcopy(ATTEMPT_044_HASHES),
        "corrected_source_freeze_file_sha256": ce.sha256((target / SOURCE_FREEZE).read_bytes()),
        "capture_topology_file_sha256": ce.sha256((target / "qualification/capture-topology.json").read_bytes()),
        "adaptive_relevance_file_sha256": ce.sha256((target / "qualification/adaptive-fault-relevance.json").read_bytes()),
        "random_structural_file_sha256": ce.sha256((target / "qualification/random-structural-matches.json").read_bytes()),
        "capture_hashes": {key: built["prepared"]["captures"][key]["capture_sha256"] for key in INSTANCES},
        "catalogue_hashes": {key: built["prepared"]["catalogues"][key]["catalogue_sha256"] for key in INSTANCES},
        "instance_hashes": {key: built["prepared"]["instances"][key]["instance_sha256"] for key in INSTANCES},
        "capture_branch_tree_sha256": ce.sha256(ce._tree_hashes(target / "capture-branches")),
        "job_capture_tree_sha256": ce.sha256(ce._tree_hashes(target / "job-captures")),
        "native_export_tree_sha256": ce.sha256(ce._tree_hashes(target / "native-exports")),
        "projection_tree_sha256": ce.sha256(ce._tree_hashes(target / "projections")),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(target / "controller-manifests")),
        "package_hashes": sorted(record["package_sha256"] for record in built["records"]),
        "review_design_sha256": ce.sha256(built["design"]["review_trials"]),
        "no_model_verification_file_sha256": ce.sha256((target / "qualification/no-model-verification.json").read_bytes()),
        "focused_test_results_file_sha256": ce.sha256(focused.read_bytes()),
        "expected_counts": {
            "instances": 4, "reused_job_captures": 8, "fresh_job_executions": 8,
            "packages": 64, "reviews": 128, "adaptive_followups": 16,
            "reconsiderations": 8, "provider_calls": 152, "repairs": 0,
        },
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0,
        "full_replication_started": False,
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
            raise ValueError(f"N27PA frozen code changed: {relative}")
    built = build_attempt(repo_root, target)
    for folder, key in (
        ("capture-branches", "capture_branch_tree_sha256"),
        ("job-captures", "job_capture_tree_sha256"),
        ("native-exports", "native_export_tree_sha256"),
        ("projections", "projection_tree_sha256"),
        ("packages", "package_tree_sha256"),
        ("controller-manifests", "controller_manifest_tree_sha256"),
    ):
        if ce.sha256(ce._tree_hashes(target / folder)) != freeze[key]:
            raise ValueError(f"N27PA frozen tree changed: {folder}")
    if sorted(record["package_sha256"] for record in built["records"]) != freeze["package_hashes"]:
        raise ValueError("N27PA package hashes changed")
    if ce.sha256(built["design"]["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("N27PA review schedule changed")
    return {
        "status": "verified",
        "freeze_sha256": digest,
        "packages": 64,
        "reviews": 128,
        "provider_calls": 152,
        "repairs": 0,
        "qualification": built["qualification"],
    }


def create_live_consumption(repo_root: Path, target: Path) -> Path:
    path = target / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(_json(path), "consumption_sha256")
        return path
    if list((target / "reviews").glob("*.json")):
        raise ValueError("N27PA review exists before authority consumption")
    verified = verify_frozen_attempt(repo_root, target)
    record = {
        "schema_version": "n27pa-live-consumption-1",
        "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(target / "controller-manifests")),
        "protected_hashes": deepcopy(PROTECTED),
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 64, "reviews": 128, "provider_calls": 152, "repairs": 0},
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _provider_review(
    repo_root: Path,
    target: Path,
    request: Mapping[str, Any],
    parent_id: str,
    mode: str,
    follow_up: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    response = ce._provider_call(
        repo_root,
        target,
        kind="review",
        model_request=request,
        controller_parent_id=parent_id,
        review_prompt=PROMPT,
        review_schema=_schema_for(mode, follow_up),
    )
    return {**response, "n27pa_latency_seconds": time.monotonic() - started}


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(response.get(key))
        for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count", "n27pa_latency_seconds")
    }


def _usage(response: Mapping[str, Any], purpose: str) -> dict[str, Any]:
    return {
        **ce.actual_usage_record(response, purpose=purpose, phase="n27pa_pilot_review"),
        "latency_seconds": response.get("n27pa_latency_seconds"),
    }


def run_review_session(
    repo_root: Path,
    target: Path,
    catalogue: Mapping[str, Any],
    index: Mapping[str, Any],
    package_record: Mapping[str, Any],
    trial_id: str,
) -> dict[str, Any]:
    mode = package_record["controller_condition"]["mode"]
    package = deepcopy(package_record["reviewer_package"])
    initial = _provider_review(repo_root, target, render_request(package), trial_id, mode)
    pre = n25.validate_response(repo_root, package, initial, _schema_for(mode))
    final, current = pre, package
    calls = [_call_record(initial)]
    usage = [_usage(initial, "initial_pilot_review")]
    events = []
    if mode == "E08":
        group_id = str(pre["receipt"]["next_action"]["execution_group_id"])
        current, event = n27p.expand_native_subtree(catalogue, index, package, group_id)
        events.append(event)
        current.pop("available_operations", None)
        current.pop("interaction_contract", None)
        response = _provider_review(
            repo_root,
            target,
            render_request(current, event),
            f"{trial_id}-follow-up-01",
            mode,
            True,
        )
        final = n25.validate_response(repo_root, current, response, FINAL_SCHEMA)
        calls.append(_call_record(response))
        usage.append(_usage(response, "model_selected_native_subtree_disclosure"))
    elif mode == "E09":
        before = ce.sha256(_initial_evidence(current))
        event = {"operation": "reconsider_same_evidence", "status": "completed", "evidence_bytes_added": 0}
        response = _provider_review(
            repo_root,
            target,
            render_request(current, event),
            f"{trial_id}-follow-up-01",
            mode,
            True,
        )
        if ce.sha256(_initial_evidence(current)) != before:
            raise RuntimeError("N27PA Reconsideration changed evidence")
        final = n25.validate_response(repo_root, current, response, FINAL_SCHEMA)
        events.append(event)
        calls.append(_call_record(response))
        usage.append(_usage(response, "zero_evidence_reconsideration"))
    graph = current.get("graph_review", {}).get("evidence", {})
    return {
        "pre_validation": pre,
        "final_validation": final,
        "operation_events": events,
        "completed_evidence_expansions": sum(event["operation"] == "expand_execution_group" for event in events),
        "completed_reconsiderations": sum(event["operation"] == "reconsider_same_evidence" for event in events),
        "selected_group": next((deepcopy(event) for event in events if event["operation"] == "expand_execution_group"), None),
        "disclosed_node_count": len(graph.get("nodes", [])),
        "disclosed_relationship_count": len(graph.get("relationships", [])),
        "call_records": calls,
        "usage": ce.aggregate_actual_usage_records(usage),
    }


def _analysis_rows(reviews: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for review in reviews:
        trial = review["controller_trial"]
        usage = review["usage"]
        rows.append({
            "trial_id": trial["trial_id"],
            "instance_id": trial["instance_id"],
            "cell_id": trial["cell_id"],
            "mode": trial["mode"],
            "source_setting": trial["source_setting"],
            "declaration_setting": trial["declaration_setting"],
            "repetition": trial["repetition"],
            "designation": review["designation"],
            "fault_detected": bool(review["fault_detected"]),
            "correct_job_attribution": bool(review["correct_job_attribution"]),
            "exact_function_localisation": bool(review["exact_function_localisation"]),
            "false_positive": bool(review["false_positive"]),
            "suspect_job": review["suspect_job"],
            "suspect_function": review["suspect_function"],
            "provider_calls": len(review["call_records"]),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "selected_group_contained_mutation_state": bool(review["selected_group_contained_mutation_state"]),
            "pre_fault_detected": bool(review["pre_fault_detected"]),
            "pre_suspect_job": review["pre_suspect_job"],
            "pre_suspect_function": review["pre_suspect_function"],
        })
    return rows


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [row for row in rows if row["designation"] == "upstream_fault"]
    controls = [row for row in rows if row["designation"] == "matched_clean_control"]

    def ratio(values: list[Mapping[str, Any]], key: str) -> dict[str, int]:
        return {"numerator": sum(bool(value[key]) for value in values), "denominator": len(values)}

    return {
        "reviews": len(rows),
        "provider_calls": sum(row["provider_calls"] for row in rows),
        "fault_detection": ratio(faults, "fault_detected"),
        "correct_job_attribution": ratio(faults, "correct_job_attribution"),
        "exact_function_localisation": ratio(faults, "exact_function_localisation"),
        "control_false_positives": ratio(controls, "false_positive"),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "cached_input_tokens": sum(row["cached_input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "total_tokens": sum(row["total_tokens"] for row in rows),
        "selected_job_distribution": {
            str(key): sum(row["suspect_job"] == key for row in rows)
            for key in ("job_1", "job_2", "job_3", "job_4", None)
        },
        "selected_function_distribution": {
            str(key): sum(row["suspect_function"] == key for row in rows)
            for key in sorted({row["suspect_function"] for row in rows}, key=lambda value: str(value))
        },
    }


def write_analysis(target: Path, reviews: Iterable[Mapping[str, Any]]) -> Path:
    rows = _analysis_rows(reviews)
    aggregate = _summary(rows)
    cell_summaries = {cell: _summary([row for row in rows if row["cell_id"] == cell]) for cell in CELLS}
    if aggregate["fault_detection"]["denominator"] != 96 or aggregate["control_false_positives"]["denominator"] != 32:
        raise RuntimeError("N27PA aggregate fault/control accounting changed")
    if any(value["fault_detection"]["denominator"] != 6 or value["control_false_positives"]["denominator"] != 2 for value in cell_summaries.values()):
        raise RuntimeError("N27PA per-cell fault/control accounting changed")
    adaptive = [row for row in rows if row["mode"] == "E08"]
    reconsider = [row for row in rows if row["mode"] == "E09"]
    contrasts = []
    for name, left, right in (
        ("job4_logs", "E02-S1-B0", "E01-S1-B0"),
        ("complete_source", "E02-S1-B0", "E02-S0-B0"),
        ("semantic_boundaries", "E02-S1-B1", "E02-S1-B0"),
        ("empty_history", "E03-S1-B0", "E02-S1-B0"),
        ("actual_history", "E04-S1-B0", "E03-S1-B0"),
        ("empty_graph", "E05-S1-B0", "E02-S1-B0"),
        ("compact_nodes", "E06-S1-B0", "E05-S1-B0"),
        ("connectivity_nesting", "E07-S1-B0", "E06-S1-B0"),
        ("adaptive_disclosure", "E08-S1-B0", "E07-S1-B0"),
        ("new_evidence_vs_reconsideration", "E08-S1-B0", "E09-S1-B0"),
        ("full_graph", "E10-S1-B0", "E05-S1-B0"),
        ("structural_vs_random", "E07-S1-B0", "E11-S1-B0"),
    ):
        for outcome in ("fault_detected", "correct_job_attribution", "exact_function_localisation"):
            differences = []
            for instance in INSTANCES[:3]:
                a = [float(row[outcome]) for row in rows if row["instance_id"] == instance and row["cell_id"] == left]
                b = [float(row[outcome]) for row in rows if row["instance_id"] == instance and row["cell_id"] == right]
                differences.append(sum(a) / len(a) - sum(b) / len(b))
            contrasts.append({
                "name": name,
                "left": left,
                "right": right,
                "outcome": outcome,
                "independent_fault_units": 3,
                "mean_difference": sum(differences) / len(differences),
                "per_instance_differences": differences,
            })
    analysis = {
        "schema_version": "n27pa-pilot-analysis-1",
        "exploratory_not_confirmatory": True,
        "full_replication_remains_deferred": True,
        "aggregate": aggregate,
        "cell_summaries": cell_summaries,
        "instance_summaries": {instance: _summary([row for row in rows if row["instance_id"] == instance]) for instance in INSTANCES},
        "instance_cell_summaries": {
            f"{instance}/{cell}": _summary([row for row in rows if row["instance_id"] == instance and row["cell_id"] == cell])
            for instance in INSTANCES for cell in CELLS
        },
        "paired_pilot_contrasts": contrasts,
        "adaptive": {
            "sessions": len(adaptive),
            "mutation_state_containment": {
                "numerator": sum(row["selected_group_contained_mutation_state"] for row in adaptive if row["designation"] == "upstream_fault"),
                "denominator": sum(row["designation"] == "upstream_fault" for row in adaptive),
            },
            "detection_changed": sum(row["fault_detected"] != row["pre_fault_detected"] for row in adaptive),
            "job_changed": sum(row["suspect_job"] != row["pre_suspect_job"] for row in adaptive),
            "function_changed": sum(row["suspect_function"] != row["pre_suspect_function"] for row in adaptive),
        },
        "reconsideration": {
            "sessions": len(reconsider),
            "evidence_bytes_added": 0,
            "detection_changed": sum(row["fault_detected"] != row["pre_fault_detected"] for row in reconsider),
            "job_changed": sum(row["suspect_job"] != row["pre_suspect_job"] for row in reconsider),
            "function_changed": sum(row["suspect_function"] != row["pre_suspect_function"] for row in reconsider),
        },
        "estimated_cost_usd": round(
            (aggregate["input_tokens"] - aggregate["cached_input_tokens"]) * 5 / 1_000_000
            + aggregate["cached_input_tokens"] * .5 / 1_000_000
            + aggregate["output_tokens"] * 30 / 1_000_000,
            6,
        ),
        "limitations": [
            "This four-instance pilot is exploratory and must not be pooled into a later confirmatory replication.",
            "The three Job-1 faults, rather than repeated reviews, are the independent faulty units.",
            "Jobs 1 and 2 reuse Attempt-044 captures while Jobs 3 and 4 are fresh DataFrame-native executions.",
        ],
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    ce._write_immutable(target / "analysis/summary.json", analysis)
    import io
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
    report_dir = repo_root / "docs/workshops/ICLR/N27PA-dataframe-native-jobs-3-4-pilot"
    findings = [
        "# N27PA DataFrame-native Jobs 3–4 pilot", "",
        "Attempt 045 completed the authorized four-instance pilot with genuine DataFrame intermediates in Jobs 3 and 4. The results are exploratory; the seven-instance replication remains deferred.", "",
        "## Aggregate outcomes", "",
        f"- Fault detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job-1 attribution: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function localisation: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean-control false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Adaptive relevant-subtree selections: {_rate(analysis['adaptive']['mutation_state_containment'])}",
        f"- Required expansions: {analysis['adaptive']['sessions']}/16",
        f"- Reconsiderations: {analysis['reconsideration']['sessions']}/8 with zero added evidence", "",
        "## Operational result", "",
        "All native topology, exact relevance, Random matching, package-isolation, strict-schema, live-count and replay gates passed. No repair calls were made.", "",
        "## Immutable records", "",
        "- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-045/experiment-freeze.json)",
        "- [Analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-045/analysis/summary.json)",
        "- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-045/replay.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-045/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    cell_lines = [
        "# Complete cell table", "",
        "| Cell | Reviews | Detection | Job 1 | Exact function | Control FP | Calls |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in CELLS:
        value = analysis["cell_summaries"][cell]
        cell_lines.append(
            f"| {cell} | {value['reviews']} | {_rate(value['fault_detection'])} | {_rate(value['correct_job_attribution'])} | {_rate(value['exact_function_localisation'])} | {_rate(value['control_false_positives'])} | {value['provider_calls']} |"
        )
    _write_text(report_dir / "cell-table.md", "\n".join(cell_lines))
    trial_lines = [
        "# Complete trial table", "",
        "| Position | Trial | Instance | Cell | Rep | Detected | Suspect job | Suspect function | Calls |",
        "|---:|---|---|---|---:|---|---|---|---:|",
    ]
    for review in sorted(reviews, key=lambda value: value["controller_trial"]["schedule_position"]):
        trial = review["controller_trial"]
        trial_lines.append(
            f"| {trial['schedule_position']} | {trial['trial_id']} | {trial['instance_id']} | {trial['cell_id']} | {trial['repetition']} | {review['fault_detected']} | {review['suspect_job']} | {review['suspect_function']} | {len(review['call_records'])} |"
        )
    _write_text(report_dir / "trial-table.md", "\n".join(trial_lines))
    topology = _json(target / "qualification/capture-topology.json")["topology"]
    native_lines = [
        "# Complete native-topology table", "",
        "| Instance | Job | Native nodes | Native edges | V0 | E0 | Groups | Passed |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for instance in INSTANCES:
        index = _json(target / "native-subtree-index" / f"{instance}.json")
        for job in JOB_ORDER:
            value = index["job_counts"][job]
            native_lines.append(
                f"| {instance} | {job} | {value['full_nodes']} | {value['full_edges']} | {value['visible_nodes']} | {value['visible_edges']} | {value['collapsed_clusters']} | {topology[instance][job]['passed']} |"
            )
    _write_text(report_dir / "native-topology-table.md", "\n".join(native_lines))


def _write_handoff(repo_root: Path, target: Path) -> None:
    analysis = _json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    freeze_file = target / "experiment-freeze.json"
    lines = [
        "To: Overseer", "From: Developer", "Subject: N27PA Attempt 045 pilot results", "",
        "Status: `completed_pilot_and_analysis`",
        f"Authority: `{AUTHORITY.as_posix()}` (`{AUTHORITY_SHA256}`)",
        f"Freeze logical SHA-256: `{_json(freeze_file)['freeze_sha256']}`", "",
        "Counts", "",
        "- Four composite captures: eight exact reused Job-1/2 captures and eight fresh DataFrame-native Job-3/4 captures",
        "- 64 packages; 128 terminal reviews; 16 Adaptive disclosures; 8 zero-evidence reconsiderations",
        "- 152 logical provider calls; zero repairs", "",
        "Exploratory outcomes", "",
        f"- Detection: {_rate(aggregate['fault_detection'])}",
        f"- Correct Job 1: {_rate(aggregate['correct_job_attribution'])}",
        f"- Exact function: {_rate(aggregate['exact_function_localisation'])}",
        f"- Clean false positives: {_rate(aggregate['control_false_positives'])}",
        f"- Tokens: input {aggregate['input_tokens']}; cached input {aggregate['cached_input_tokens']}; output {aggregate['output_tokens']}; total {aggregate['total_tokens']}",
        f"- Frozen-rate estimated cost: USD {analysis['estimated_cost_usd']}", "",
        "Attempts 042, 043 and 044 and the protected Etiq/provider/execution surfaces remained unchanged. The full seven-instance replication was not started.",
    ]
    _write_text(
        repo_root / "instructions_between_agent_types/developer/handoffs/N27PA_attempt_045_results_to_overseer.email.md",
        "\n".join(lines),
    )


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


def execute_lifecycle(repo_root: Path, target: Path) -> Path:
    repo_root, target = repo_root.resolve(), target.resolve()
    verified = verify_frozen_attempt(repo_root, target)
    create_live_consumption(repo_root, target)
    prepared = prepare_attempt(repo_root, target)
    packages = {record["controller_condition"]["branch_id"]: record for record in _package_records(target)}
    trials = _json(target / "review-design.json")["review_trials"]
    relevance = _json(target / "qualification/adaptive-fault-relevance.json")["instances"]
    reviews = []
    for trial in trials:
        path = target / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = _json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record["controller_trial"] != trial or record["status"] != "complete":
                raise ValueError("invalid N27PA partial review record")
        else:
            instance_id = trial["instance_id"]
            package_record = packages[trial["branch_id"]]
            session = run_review_session(
                repo_root,
                target,
                prepared["catalogues"][instance_id],
                prepared["indexes"][instance_id],
                package_record,
                trial["trial_id"],
            )
            pre, final = session["pre_validation"], session["final_validation"]
            outcome = n25.score_response(prepared["instances"][instance_id], final)
            selected = session["selected_group"]
            relevant_group = relevance.get(instance_id, {}).get("model_selectable_execution_group_id")
            record = {
                "schema_version": "n27pa-review-record-1",
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
                "completed_evidence_expansions": session["completed_evidence_expansions"],
                "completed_reconsiderations": session["completed_reconsiderations"],
                "selected_group_contained_mutation_state": bool(
                    selected and selected["execution_group_id"] == relevant_group
                ),
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
    expected = {
        "reviews": 128,
        "repairs": 0,
        "logical_provider_calls": 152,
        "provider_attempt_call_ids": counts["provider_attempt_call_ids"],
        "completed_evidence_expansions": 16,
        "completed_reconsiderations": 8,
    }
    if counts != expected:
        raise RuntimeError(f"N27PA terminal counts changed: {counts}")
    call_ids = [call_id for record in reviews for call in record["call_records"] for call_id in call["call_ids"]]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("N27PA duplicate provider call ID")
    for call_id in call_ids:
        verify_record(target / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = _json(write_analysis(target, reviews))
    freeze = _json(target / "experiment-freeze.json")
    replay = {
        "schema_version": "n27pa-replay-1",
        "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(record["review_sha256"] for record in reviews),
        "observed_counts": counts,
        "all_record_hashes_recomputed": True,
        "duplicate_provider_call_ids": False,
        "package_tree_unchanged": ce.sha256(ce._tree_hashes(target / "packages")) == freeze["package_tree_sha256"],
        "controller_manifest_tree_unchanged": ce.sha256(ce._tree_hashes(target / "controller-manifests")) == freeze["controller_manifest_tree_sha256"],
        "capture_branch_tree_unchanged": ce.sha256(ce._tree_hashes(target / "capture-branches")) == freeze["capture_branch_tree_sha256"],
        "native_export_tree_unchanged": ce.sha256(ce._tree_hashes(target / "native-exports")) == freeze["native_export_tree_sha256"],
        "provider_receipts_preserved": all(record["initial_receipt"] and record["terminal_receipt"] for record in reviews),
        "required_expansions_complete": sum(record["completed_evidence_expansions"] for record in reviews) == 16,
        "reconsiderations_complete": sum(record["completed_reconsiderations"] for record in reviews) == 8,
        "repair_count": 0,
        "full_replication_started": False,
    }
    if not all(value for key, value in replay.items() if key.endswith(("unchanged", "preserved", "complete"))):
        raise RuntimeError("N27PA replay reconciliation failed")
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(target / "replay.json", replay)
    terminal = {
        "schema_version": "n27pa-terminal-1",
        "status": "completed_pilot_and_analysis",
        "instance_count": 4,
        "reused_job_capture_count": 8,
        "fresh_job_capture_count": 8,
        "package_count": 64,
        "review_count": 128,
        "mandatory_follow_up_count": 24,
        "logical_provider_calls": 152,
        "repair_trace_count": 0,
        "analysis_sha256": analysis["analysis_sha256"],
        "replay_sha256": replay["replay_sha256"],
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
            "schema_version": "n27pa-terminal-1",
            "status": "terminal_incomplete",
            "failure_stage": "n27pa_resumable_lifecycle",
            "error": f"{type(exc).__name__}: {exc}",
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
            built = build_attempt(repo, target)
            print(json.dumps({"qualification": built["qualification"]}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, target))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, target), indent=2))
        else:
            path = run_lifecycle(repo, target)
            print(path)
            return 0 if _json(path).get("status") == "completed_pilot_and_analysis" else 1
    except Exception as exc:
        print(f"N27PA experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
