"""N27P native-Etiq replication pilot (append-only Attempt 044)."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Mapping

from . import corrected_experiment as ce
from . import n25_experiment as n25
from .job_store import JobStore
from .n05_program import _load_snapshot, _parse_output, _pipeline_payload, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline, jsonable


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-044")
ATTEMPT_042 = Path("outputs/fault-experiments-v2-2-n10/attempt-042")
ATTEMPT_043 = Path("outputs/fault-experiments-v2-2-n10/attempt-043")
TASK = Path("instructions_between_agent_types/developer/current/N27P_native_etiq_attempt_042_replication_pilot.email.md")
TASK_SHA256 = "sha256:c5b3a4c605315c4d131290c404091901784d4ff2d61f294d280b5f5698428f12"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N27P_native_etiq_attempt_042_replication_pilot_authorization.json")
AUTHORITY_SHA256 = "sha256:81d4e7149c31804eaa1003709658d935fc645adc340018aaa81ac5b7ae58081d"
PROMPT = n25.PROMPT
FINAL_SCHEMA = n25.FINAL_SCHEMA
REQUIRED_SCHEMA = n25.REQUIRED_SCHEMA
RECONSIDER_SCHEMA = n25.RECONSIDER_SCHEMA

JOB_ORDER = n25.JOB_ORDER
FUNCTIONS = n25.FUNCTIONS
UPSTREAM, DOWNSTREAM, JOB3, JOB4 = JOB_ORDER
MODES = n25.MODES
MODE_NAMES = n25.MODE_NAMES
GRAPH_MODES = n25.GRAPH_MODES
INSTANCES = (
    "select_threshold_omission",
    "normalize_middle_record_omission",
    "provenance_join_identity",
    "four_stage_clean_control",
)
TRUTH = {
    "select_threshold_omission": "select_demand",
    "normalize_middle_record_omission": "normalize",
    "provenance_join_identity": "assemble_provenance",
    "four_stage_clean_control": None,
}
CELLS = (
    "E01-S1-B0", "E02-S0-B0", "E02-S1-B0", "E02-S1-B1",
    "E03-S1-B0", "E04-S1-B0", "E05-S1-B0", "E06-S1-B0",
    "E07-S0-B0", "E07-S1-B0", "E07-S1-B1", "E08-S0-B0",
    "E08-S1-B0", "E09-S1-B0", "E10-S1-B0", "E11-S1-B0",
)
PRESERVED = {
    ATTEMPT_042: {
        "experiment-freeze.json": "sha256:03d61ee15f9f87ba3db318db585450ce4570a9ac5bfd17071c23f715f8572e71",
        "terminal-state.json": "sha256:9352cd69d341c1c81dc08e26a66d9f0b0ccb5b9654dda560948f9edac613061c",
        "replay.json": "sha256:7796dd9fa0bde8153bab96f344ddaa5f9d24c15e869ed7c1f27202e7b6954614",
    },
    ATTEMPT_043: {
        "experiment-freeze.json": "sha256:e23229855b55a2bab35d2b0eb8fcae5e6ebe889078d47485d45ffcb1500362b1",
        "terminal-state.json": "sha256:1532ae0e07e421c787a0ac44c2ddf48cfa255c2034b11b4e2121a09914b42d34",
        "replay.json": "sha256:057e5d4a5acb4e4731623ba03b6588b5fc6c80e391a4c8909b6ffcbca32fe73c",
    },
}
FORBIDDEN_VISIBLE_KEYS = (
    "instance_id", "cell_id", "source_setting", "declaration_setting", "branch_id",
    "trial_id", "repetition", "seed", "truth_job", "truth_function", "designation",
    "mutation", "oracle", "qualification", "clean_comparison", "boundary_id",
)


def _json(path: Path) -> dict[str, Any]:
    return ce._read_json(path)


def _write_text(path: Path, text: str) -> None:
    create_bytes_exclusive(path, text.encode())


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N27P authority input changed: {relative}")
    preserved = {}
    for root, bindings in PRESERVED.items():
        preserved[root.name] = {}
        for relative, expected in bindings.items():
            actual = ce.sha256((repo_root / root / relative).read_bytes())
            if actual != expected:
                raise ValueError(f"N27P preservation binding changed: {root.name}/{relative}")
            preserved[root.name][relative] = actual
    if (ce.PROVIDER_MODEL, ce.PROVIDER_REASONING_EFFORT) != ("gpt-5.5", "high"):
        raise ValueError("N27P model configuration changed")
    return {"task": TASK_SHA256, "authority": AUTHORITY_SHA256, "preserved": preserved}


def _source_attempt_record(repo_root: Path, instance_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    root = repo_root / ATTEMPT_042
    capture_path = root / "captures" / f"{instance_id}.json"
    source_path = root / "source-bundles" / f"{instance_id}.json"
    instance_path = root / "instances" / f"{instance_id}.json"
    capture = _json(capture_path)
    source_bundle = _json(source_path)["source_bundle"]
    instance = _json(instance_path)
    n25._verify_four_capture(capture)
    if instance.get("truth_function") != TRUTH[instance_id]:
        raise ValueError(f"N27P Attempt-042 truth binding changed: {instance_id}")
    binding = {
        "source_capture_file_sha256": ce.sha256(capture_path.read_bytes()),
        "source_bundle_file_sha256": ce.sha256(source_path.read_bytes()),
        "instance_file_sha256": ce.sha256(instance_path.read_bytes()),
        "source_sha256": deepcopy(capture["source_sha256"]),
        "input_sha256": {job: ce.sha256(capture["jobs"][job]["input"]) for job in JOB_ORDER},
        "expected_output_sha256": {job: ce.sha256(capture["jobs"][job]["output"]) for job in JOB_ORDER},
    }
    return capture, deepcopy(source_bundle), {"instance": instance, "binding": binding}


def _pipeline(source_capture: Mapping[str, Any], source_bundle: list[dict[str, Any]], job_id: str) -> GeneratedPipeline:
    bundle = next(value for value in source_bundle if value["job_id"] == job_id)
    entry_file = str(bundle["files"][0]["path"])
    boundaries = []
    for realized in source_capture["jobs"][job_id]["realization"]["realized_boundaries"]:
        boundaries.append({
            "boundary_id": str(realized["boundary_id"]),
            "function_name": str(realized["function_name"]),
            "qualified_function_name": str(realized["function_name"]),
            "source_path": entry_file,
            "role": str(realized["role"]),
            "expected_inputs": deepcopy(realized["expected_inputs"]),
            "expected_outputs": deepcopy(realized["expected_outputs"]),
            "semantic_stage": str(realized["semantic_stage"]),
        })
    pipeline = GeneratedPipeline(
        entry_file=entry_file,
        files=[GeneratedFile(str(value["path"]), str(value["content"])) for value in bundle["files"]],
        review_boundaries=boundaries,
    )
    pipeline.validate()
    return pipeline


def _native_path(run_dir: Path) -> Path:
    return run_dir / "etiq-native-lineage.json"


def _load_execution(branch: Path, job_id: str) -> Any | None:
    if not branch.exists():
        return None
    runs = sorted(branch.glob(f"jobstore/{job_id}/stages/n05/*/runs/*"))
    if len(runs) != 1:
        raise ValueError(f"N27P existing capture branch is incomplete: {branch}")
    run_dir = runs[0]
    snapshot = _load_snapshot(JobStore(branch / "jobstore"), run_dir)
    if snapshot.scan_errors or not snapshot.nodes or not _native_path(run_dir).is_file():
        raise ValueError(f"N27P existing Etiq capture is not reviewable: {branch}")
    return n25.EtiqExecution(snapshot=snapshot, run_dir=run_dir)


def _capture_instance(repo_root: Path, target: Path, instance_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    old, source_bundle, source = _source_attempt_record(repo_root, instance_id)
    jobs = {}
    handoffs = []
    native_bindings = {}
    for index, job_id in enumerate(JOB_ORDER):
        pipeline = _pipeline(old, source_bundle, job_id)
        branch = target / "capture-branches" / instance_id / f"canonical-v2-job-{index + 1}"
        execution = _load_execution(branch, job_id)
        if execution is None:
            materialize_opaque_branch(
                branch,
                allowlist={},
                manifest_identity={"purpose": "n27p-canonical-capture", "instance": instance_id, "job": job_id},
            )
            copy_etiq_worker_runtime(branch, repo_root / "src")
            execution = execute_pipeline_in_branch(
                branch,
                repo_root=repo_root,
                job_id=job_id,
                pipeline=pipeline,
                runtime_input=old["jobs"][job_id]["input"],
                run_index=INSTANCES.index(instance_id),
                stage=f"n27p-{instance_id}-{index + 1}",
            )
        output = _parse_output(execution)
        if output != old["jobs"][job_id]["output"]:
            raise ValueError(f"N27P business output differs from Attempt 042: {instance_id}/{job_id}")
        if _json(execution.run_dir / "pipeline-input.json") != old["jobs"][job_id]["input"]:
            raise ValueError(f"N27P input differs from Attempt 042: {instance_id}/{job_id}")
        native_path = _native_path(execution.run_dir)
        native = _json(native_path)
        if not isinstance(native.get("objects"), list) or not isinstance(native.get("edges"), list):
            raise ValueError(f"N27P native export is invalid: {instance_id}/{job_id}")
        realization = n25._realization(execution, pipeline, job_id)
        job = n25._job_record(execution, output, realization)
        job["native_lineage"] = native
        job["native_lineage_file_sha256"] = ce.sha256(native_path.read_bytes())
        job["native_lineage_logical_sha256"] = ce.sha256(native)
        job["native_lineage_export_status"] = execution.snapshot.inventories.get("json_lineage_export")
        jobs[job_id] = job
        native_bindings[job_id] = {
            "file_sha256": job["native_lineage_file_sha256"],
            "logical_sha256": job["native_lineage_logical_sha256"],
            "objects": len(native["objects"]),
            "edges": len(native["edges"]),
        }
        if index:
            producer = JOB_ORDER[index - 1]
            names = ("needs", "evidence_sources") if job_id == DOWNSTREAM else (("coverage", "priorities", "recommendation", "metadata") if job_id == JOB3 else ("campaign_portfolio", "metadata"))
            handoffs.extend(n25._handoff(name, producer, job_id, jobs[producer]["output"][name]) for name in names)
    capture = {
        "schema_version": "n27p-four-job-native-capture-1",
        "capture_id": stable_id("rerun-capture", ["n27p", instance_id], 0),
        "instance_id": instance_id,
        "job_ids": list(JOB_ORDER),
        "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": deepcopy(old["source_sha256"]),
        "native_lineage_bindings": native_bindings,
        "attempt_042_reuse_binding": source["binding"],
        "canonical": True,
        "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    n25._verify_four_capture(capture)
    return capture, source_bundle, source


def _raw_identifier(node: Mapping[str, Any], kind: str) -> str | None:
    metadata = node.get("raw_metadata", {}).get("etiq_metadata", {})
    value = metadata.get("id" if kind == "state" else "function_id")
    return re.sub(r"[^0-9a-f]", "", str(value).lower()) if value else None


def _native_identifier(obj: Mapping[str, Any]) -> str | None:
    name = str(obj.get("name") or "")
    value = name[5:] if name.startswith("node_") else name.rsplit(",", 1)[-1]
    normalized = re.sub(r"[^0-9a-f]", "", value.lower())
    return normalized if len(normalized) == 32 else None


def _native_graph(job_id: str, captured: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = captured["native_lineage"]
    objects = sorted(raw["objects"], key=lambda value: int(value["_gvid"]))
    by_gvid = {int(value["_gvid"]): value for value in objects}
    if len(by_gvid) != len(objects):
        raise ValueError(f"N27P duplicate native object ID: {job_id}")
    clusters = [value for value in objects if str(value.get("name", "")).startswith("cluster_")]
    ordinary = [value for value in objects if value not in clusters]
    cluster_gvids = {int(value["_gvid"]) for value in clusters}
    node_ref = {int(value["_gvid"]): f"native-node-j{JOB_ORDER.index(job_id) + 1}-{index:04d}" for index, value in enumerate(ordinary, 1)}
    cluster_ref = {int(value["_gvid"]): f"native-cluster-j{JOB_ORDER.index(job_id) + 1}-{index:03d}" for index, value in enumerate(clusters, 1)}
    ref_by_gvid = node_ref | cluster_ref
    if any(int(member) not in by_gvid for value in clusters for member in value.get("nodes", [])):
        raise ValueError(f"N27P unresolved native cluster membership: {job_id}")
    if any(int(edge[endpoint]) not in by_gvid for edge in raw["edges"] for endpoint in ("tail", "head")):
        raise ValueError(f"N27P unresolved native edge: {job_id}")

    canonical_by_id: dict[str, list[dict[str, Any]]] = {}
    for canonical in captured["snapshot"]["nodes"]:
        kind = "operation" if str(canonical["node_ref"]).split(":")[-2] == "function" else "state"
        identifier = _raw_identifier(canonical, kind)
        if identifier:
            canonical_by_id.setdefault(identifier, []).append(canonical)
    crosswalk = []
    reviewer_nodes = []
    safe_fields = (
        "state_type", "scope_type", "source", "line_no", "func_stack", "names",
        "value_type", "value_preview", "preview_truncated", "artifact_kind",
        "artifact_content", "artifact_truncated", "artifact_size",
    )
    for value in ordinary:
        gvid = int(value["_gvid"])
        identifier = _native_identifier(value)
        matches = canonical_by_id.get(identifier or "", [])
        kind = "operation" if value.get("shape") == "diamond" else "state"
        record = {
            "native_node_ref": node_ref[gvid],
            "job_id": job_id,
            "native_kind": kind,
            "native_label": str(value.get("label") or value.get("name") or "unlabelled"),
            "exact_canonical_match": len(matches) == 1,
        }
        if len(matches) == 1:
            record.update({key: deepcopy(matches[0].get(key)) for key in safe_fields if key in matches[0]})
        reviewer_nodes.append(record)
        crosswalk.append({
            "native_node_ref": node_ref[gvid],
            "native_gvid": gvid,
            "native_raw_identifier": identifier,
            "canonical_node_refs": [match["node_ref"] for match in matches],
            "match_status": "exact" if len(matches) == 1 else ("unmatched" if not matches else "multiple"),
            "match_basis": "exact normalized raw Etiq state/function UUID",
        })
    memberships = {int(value["_gvid"]): [int(member) for member in value.get("nodes", [])] for value in clusters}

    def descendants(cluster: int, trail: tuple[int, ...] = ()) -> set[int]:
        if cluster in trail:
            raise ValueError(f"N27P cyclic native cluster membership: {job_id}")
        found = set()
        for member in memberships[cluster]:
            if member in cluster_gvids:
                found |= descendants(member, (*trail, cluster))
            else:
                found.add(member)
        return found

    parent = {member: cluster for cluster, members in memberships.items() for member in members if member in cluster_gvids}
    if len(parent) != sum(member in cluster_gvids for members in memberships.values() for member in members):
        raise ValueError(f"N27P multiply parented native cluster: {job_id}")
    top = sorted(cluster_gvids - set(parent))
    top_labels = {str(by_gvid[value].get("label")) for value in top}
    if top_labels != set(FUNCTIONS[job_id]):
        raise ValueError(f"N27P expected top-level function clusters missing: {job_id}/{top_labels}")
    depth = {}
    for cluster in cluster_gvids:
        level, current = 0, cluster
        while current in parent:
            level += 1
            current = parent[current]
        depth[cluster] = level
    ordinary_parent: dict[int, int] = {}
    for cluster, members in memberships.items():
        for member in members:
            if member not in cluster_gvids:
                if member in ordinary_parent:
                    raise ValueError(f"N27P multiply parented native node: {job_id}")
                ordinary_parent[member] = cluster
    owner = {}
    for cluster in top:
        for member in descendants(cluster):
            owner[member] = cluster
    reviewer_by_ref = {value["native_node_ref"]: value for value in reviewer_nodes}
    for gvid, ref in node_ref.items():
        direct = ordinary_parent.get(gvid)
        reviewer_by_ref[ref]["native_cluster_depth"] = 0 if direct is None else depth[direct] + 1
        reviewer_by_ref[ref]["top_level_cluster_ref"] = cluster_ref[owner[gvid]] if gvid in owner else None
    edges = []
    raw_edges = sorted(raw["edges"], key=lambda value: int(value["_gvid"]))
    for index, edge in enumerate(raw_edges, 1):
        tail, head = int(edge["tail"]), int(edge["head"])
        if tail in cluster_gvids or head in cluster_gvids:
            raise ValueError(f"N27P native edge uses a cluster endpoint: {job_id}")
        edges.append({
            "native_edge_ref": f"native-edge-j{JOB_ORDER.index(job_id) + 1}-{index:04d}",
            "job_id": job_id,
            "source_ref": node_ref[tail],
            "target_ref": node_ref[head],
            "relationship_kind": "etiq_native_lineage",
            "direction": "tail_to_head",
        })
    reviewer_clusters = []
    for cluster in sorted(cluster_gvids):
        reviewer_clusters.append({
            "native_cluster_ref": cluster_ref[cluster],
            "job_id": job_id,
            "captured_function_label": str(by_gvid[cluster].get("label") or "unlabelled"),
            "cluster_depth": depth[cluster],
            "member_refs": [ref_by_gvid[member] for member in memberships[cluster]],
            "recursive_node_count": len(descendants(cluster)),
        })
    graph = {
        "job_id": job_id,
        "nodes": reviewer_nodes,
        "edges": edges,
        "clusters": reviewer_clusters,
        "top_level_cluster_refs": [cluster_ref[value] for value in top],
    }
    graph["native_graph_sha256"] = ce.sha256(graph)
    controller = {
        "schema_version": "n27p-native-crosswalk-1",
        "job_id": job_id,
        "crosswalk": crosswalk,
        "unmatched": [value for value in crosswalk if value["match_status"] == "unmatched"],
        "multiple": [value for value in crosswalk if value["match_status"] == "multiple"],
        "gvid_to_opaque_ref": {str(key): value for key, value in ref_by_gvid.items()},
        "cluster_descendant_gvids": {cluster_ref[key]: sorted(descendants(key)) for key in top},
        "top_level_cluster_gvids": top,
    }
    controller["crosswalk_sha256"] = ce.sha256(controller)
    return graph, controller


def _catalogue(capture: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    catalogue = n25._build_catalogue(capture)
    catalogue["schema_version"] = "n27p-four-job-native-catalogue-1"
    crosswalks = {}
    native_bindings = {}
    for job_id in JOB_ORDER:
        graph, crosswalk = _native_graph(job_id, capture["jobs"][job_id])
        catalogue["jobs"][job_id]["native_graph"] = graph
        catalogue["jobs"][job_id]["native_lineage_file_sha256"] = capture["jobs"][job_id]["native_lineage_file_sha256"]
        catalogue["jobs"][job_id]["native_lineage_logical_sha256"] = capture["jobs"][job_id]["native_lineage_logical_sha256"]
        crosswalks[job_id] = crosswalk
        native_bindings[job_id] = {
            "native_graph_sha256": graph["native_graph_sha256"],
            "crosswalk_sha256": crosswalk["crosswalk_sha256"],
            "native_lineage_file_sha256": capture["jobs"][job_id]["native_lineage_file_sha256"],
            "native_lineage_logical_sha256": capture["jobs"][job_id]["native_lineage_logical_sha256"],
        }
    catalogue["native_bindings"] = native_bindings
    catalogue.pop("catalogue_sha256", None)
    catalogue["catalogue_sha256"] = ce.sha256(catalogue)
    ce.verify_catalogue(catalogue)
    bundle = {"schema_version": "n27p-native-crosswalk-bundle-1", "jobs": crosswalks}
    bundle["bundle_sha256"] = ce.sha256(bundle)
    return catalogue, bundle


def _cluster_size_class(size: int) -> str:
    if size <= 8:
        return "small"
    if size <= 20:
        return "medium"
    return "large"


def build_compact_graph(catalogue: Mapping[str, Any], crosswalk_bundle: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    visible_nodes = []
    visible_edges = []
    collapsed = []
    collapsed_clusters = []
    groups = {}
    counts = {}
    for job_id in JOB_ORDER:
        native = catalogue["jobs"][job_id]["native_graph"]
        controller = crosswalk_bundle["jobs"][job_id]
        nodes = {value["native_node_ref"]: value for value in native["nodes"]}
        edges = native["edges"]
        clusters = {value["native_cluster_ref"]: value for value in native["clusters"]}
        top = native["top_level_cluster_refs"]
        descendants = {
            ref: {controller["gvid_to_opaque_ref"][str(gvid)] for gvid in controller["cluster_descendant_gvids"][ref]}
            for ref in top
        }
        owner = {node_ref: cluster_ref for cluster_ref, refs in descendants.items() for node_ref in refs}
        v0 = {ref for ref in nodes if ref not in owner}
        for edge in edges:
            source, target = edge["source_ref"], edge["target_ref"]
            if owner.get(source) != owner.get(target):
                v0.update((source, target))
        e0 = [edge for edge in edges if edge["source_ref"] in v0 and edge["target_ref"] in v0]
        if not e0:
            raise ValueError(f"N27P compact projection has no native edge: {job_id}")
        if len(v0) >= len(nodes):
            raise ValueError(f"N27P compact projection is not smaller than full graph: {job_id}")
        visible_nodes.extend(deepcopy(nodes[ref]) for ref in sorted(v0))
        visible_edges.extend(deepcopy(edge) for edge in e0)
        job_collapsed = 0
        for cluster_ref in top:
            hidden = descendants[cluster_ref] - v0
            if not hidden:
                continue
            cluster = clusters[cluster_ref]
            nested = [value for value in native["clusters"] if value["cluster_depth"] > 0 and value["native_cluster_ref"] in _recursive_cluster_refs(cluster_ref, clusters)]
            descriptor = {
                "execution_group_id": cluster_ref,
                "job_id": job_id,
                "captured_function_label": cluster["captured_function_label"],
                "visible_interface_node_refs": sorted(descendants[cluster_ref] & v0),
                "hidden_node_count": len(hidden),
                "hidden_size_class": _cluster_size_class(len(hidden)),
                "nested_cluster_count": len(nested),
            }
            collapsed.append(descriptor)
            collapsed_clusters.append({
                "native_cluster_ref": cluster_ref,
                "job_id": job_id,
                "captured_function_label": cluster["captured_function_label"],
                "cluster_depth": 0,
                "visible_member_refs": deepcopy(descriptor["visible_interface_node_refs"]),
                "hidden_node_count": len(hidden),
                "collapsed": True,
            })
            groups[cluster_ref] = {
                "descriptor": deepcopy(descriptor),
                "node_refs": sorted(descendants[cluster_ref]),
                "cluster_refs": sorted({cluster_ref, *_recursive_cluster_refs(cluster_ref, clusters)}),
            }
            job_collapsed += 1
        if job_collapsed != 3:
            raise ValueError(f"N27P compact projection lacks three top-level subtrees: {job_id}")
        counts[job_id] = {
            "full_nodes": len(nodes), "visible_nodes": len(v0), "full_edges": len(edges),
            "visible_edges": len(e0), "full_clusters": len(clusters), "collapsed_clusters": job_collapsed,
        }
    projection = {
        "job_evidence_order": list(reversed(JOB_ORDER)),
        "nodes": visible_nodes,
        "relationships": visible_edges,
        "native_clusters": collapsed_clusters,
        "collapsed_execution_groups": collapsed,
        "disclosed_execution_groups": [],
        "handoffs": [],
    }
    projection["projection_sha256"] = ce.sha256(projection)
    index = {"schema_version": "n27p-native-subtree-index-1", "groups": groups, "job_counts": counts}
    index["index_sha256"] = ce.sha256(index)
    return projection, index


def _recursive_cluster_refs(cluster_ref: str, clusters: Mapping[str, Mapping[str, Any]]) -> set[str]:
    found = set()
    for member in clusters[cluster_ref]["member_refs"]:
        if member in clusters:
            found.add(member)
            found |= _recursive_cluster_refs(member, clusters)
    return found


def full_graph(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "job_evidence_order": list(reversed(JOB_ORDER)),
        "nodes": [deepcopy(node) for job in reversed(JOB_ORDER) for node in catalogue["jobs"][job]["native_graph"]["nodes"]],
        "relationships": [deepcopy(edge) for job in reversed(JOB_ORDER) for edge in catalogue["jobs"][job]["native_graph"]["edges"]],
        "native_clusters": [deepcopy(cluster) for job in reversed(JOB_ORDER) for cluster in catalogue["jobs"][job]["native_graph"]["clusters"]],
        "collapsed_execution_groups": [],
        "disclosed_execution_groups": [],
        "handoffs": deepcopy(catalogue["handoffs"]),
    }
    value["projection_sha256"] = ce.sha256(value)
    return value


def expand_native_subtree(
    catalogue: Mapping[str, Any],
    index: Mapping[str, Any],
    package: Mapping[str, Any],
    group_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if "expand_execution_group" not in package.get("available_operations", []):
        raise ValueError("native subtree expansion is unavailable")
    binding = index["groups"].get(group_id)
    if binding is None:
        raise ValueError("native subtree is not in the frozen index")
    evidence = package["graph_review"]["evidence"]
    if group_id not in {value["execution_group_id"] for value in evidence["collapsed_execution_groups"]}:
        raise ValueError("native subtree is not advertised")
    all_nodes = {node["native_node_ref"]: node for job in JOB_ORDER for node in catalogue["jobs"][job]["native_graph"]["nodes"]}
    all_edges = [edge for job in JOB_ORDER for edge in catalogue["jobs"][job]["native_graph"]["edges"]]
    all_clusters = {cluster["native_cluster_ref"]: cluster for job in JOB_ORDER for cluster in catalogue["jobs"][job]["native_graph"]["clusters"]}
    updated = deepcopy(dict(package))
    graph = updated["graph_review"]["evidence"]
    existing_nodes = {value["native_node_ref"] for value in graph["nodes"]}
    added_nodes = [deepcopy(all_nodes[ref]) for ref in binding["node_refs"] if ref not in existing_nodes]
    graph["nodes"].extend(added_nodes)
    visible = {value["native_node_ref"] for value in graph["nodes"]}
    existing_edges = {value["native_edge_ref"] for value in graph["relationships"]}
    added_edges = [deepcopy(edge) for edge in all_edges if edge["source_ref"] in visible and edge["target_ref"] in visible and edge["native_edge_ref"] not in existing_edges]
    graph["relationships"].extend(added_edges)
    graph["native_clusters"] = [value for value in graph["native_clusters"] if value["native_cluster_ref"] != group_id]
    graph["native_clusters"].extend(deepcopy(all_clusters[ref]) for ref in binding["cluster_refs"])
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
        "captured_function_label": descriptor["captured_function_label"],
        "nodes_added": [value["native_node_ref"] for value in added_nodes],
        "relationships_added": [value["native_edge_ref"] for value in added_edges],
        "clusters_added": binding["cluster_refs"],
        "evidence_bytes_added": len(ce.canonical_json({"nodes": added_nodes, "relationships": added_edges, "clusters": binding["cluster_refs"]})),
    }
    if not added_nodes or not added_edges:
        raise ValueError("native subtree expansion lacks nodes or incident native lineage")
    return updated, event


def _load_prepared(target: Path) -> dict[str, Any]:
    values = {
        name: {path.stem: _json(path) for path in sorted((target / folder).glob("*.json"))}
        for name, folder in (
            ("captures", "captures"), ("catalogues", "catalogues"),
            ("instances", "instances"), ("source_bundles", "source-bundles"),
            ("crosswalks", "native-crosswalks"),
        )
    }
    if any(set(collection) != set(INSTANCES) for collection in values.values()):
        raise ValueError("N27P prepared record set is partial")
    values["indexes"] = {path.stem: _json(path) for path in sorted((target / "native-subtree-index").glob("*.json"))}
    for instance_id in INSTANCES:
        n25._verify_four_capture(values["captures"][instance_id])
        ce.verify_catalogue(values["catalogues"][instance_id])
        ce._verified_self_hash(values["instances"][instance_id], "instance_sha256")
        ce._verified_self_hash(values["crosswalks"][instance_id], "bundle_sha256")
        if instance_id in values["indexes"]:
            ce._verified_self_hash(values["indexes"][instance_id], "index_sha256")
        values["source_bundles"][instance_id] = values["source_bundles"][instance_id]["source_bundle"]
    return values


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N27P is authorized only for Attempt 044")
    authority = _verify_authority(repo_root)
    if (target / "captures").exists():
        prepared = _load_prepared(target) | {"authority": authority}
        blocking = target / "qualification" / "pre-live-blocking-native-compact.json"
        if blocking.exists():
            record = _json(blocking)
            ce._verified_self_hash(record, "blocking_sha256")
            raise RuntimeError(record["summary"])
        return prepared
    captures = {}
    catalogues = {}
    instances = {}
    source_bundles = {}
    crosswalks = {}
    indexes = {}
    compact_failures = []
    for instance_id in INSTANCES:
        capture, source_bundle, source = _capture_instance(repo_root, target, instance_id)
        catalogue, crosswalk = _catalogue(capture)
        old_instance = source["instance"]
        instance = {
            "schema_version": "n27p-instance-1",
            "instance_id": instance_id,
            "designation": "matched_clean_control" if TRUTH[instance_id] is None else "upstream_fault",
            "truth_job": None if TRUTH[instance_id] is None else UPSTREAM,
            "truth_function": TRUTH[instance_id],
            "mutation": deepcopy(old_instance.get("mutation")),
            "attempt_042_instance_file_sha256": source["binding"]["instance_file_sha256"],
            "capture_sha256": capture["capture_sha256"],
            "catalogue_sha256": catalogue["catalogue_sha256"],
            "source_sha256": deepcopy(capture["source_sha256"]),
            "input_sha256": deepcopy(source["binding"]["input_sha256"]),
        }
        instance["instance_sha256"] = ce.sha256(instance)
        ce._write_immutable(target / "captures" / f"{instance_id}.json", capture)
        ce._write_immutable(target / "catalogues" / f"{instance_id}.json", catalogue)
        ce._write_immutable(target / "source-bundles" / f"{instance_id}.json", {"source_bundle": source_bundle})
        ce._write_immutable(target / "instances" / f"{instance_id}.json", instance)
        ce._write_immutable(target / "native-crosswalks" / f"{instance_id}.json", crosswalk)
        for job_id in JOB_ORDER:
            raw = capture["jobs"][job_id]["native_lineage"]
            export_path = target / "native-exports" / instance_id / job_id / "etiq-native-lineage.json"
            ce._write_immutable(export_path, raw)
            record = {
                "schema_version": "n27p-per-job-native-capture-1",
                "instance_id": instance_id,
                "job_id": job_id,
                "job_capture_sha256": ce.sha256(capture["jobs"][job_id]),
                "native_run_file_sha256": capture["jobs"][job_id]["native_lineage_file_sha256"],
                "native_export_file_sha256": ce.sha256(export_path.read_bytes()),
                "native_logical_sha256": capture["jobs"][job_id]["native_lineage_logical_sha256"],
                "native_export_status": capture["jobs"][job_id]["native_lineage_export_status"],
                "source_sha256": capture["source_sha256"][job_id],
                "reuse_status": "fresh_execution",
            }
            record["record_sha256"] = ce.sha256(record)
            ce._write_immutable(target / "job-captures" / instance_id / f"{job_id}.json", record)
        captures[instance_id], catalogues[instance_id] = capture, catalogue
        instances[instance_id], source_bundles[instance_id] = instance, source_bundle
        crosswalks[instance_id] = crosswalk
        try:
            compact, index = build_compact_graph(catalogue, crosswalk)
        except ValueError as exc:
            compact_failures.append({
                "instance_id": instance_id,
                "error": str(exc),
                "per_job_native_counts": {
                    job: {
                        "nodes": len(catalogue["jobs"][job]["native_graph"]["nodes"]),
                        "edges": len(catalogue["jobs"][job]["native_graph"]["edges"]),
                        "clusters": len(catalogue["jobs"][job]["native_graph"]["clusters"]),
                    }
                    for job in JOB_ORDER
                },
            })
        else:
            indexes[instance_id] = index
            ce._write_immutable(target / "native-subtree-index" / f"{instance_id}.json", index)
            ce._write_immutable(target / "projections" / f"{instance_id}-compact.json", compact)
    prepared = {
        "captures": captures, "catalogues": catalogues, "instances": instances,
        "source_bundles": source_bundles, "crosswalks": crosswalks, "indexes": indexes,
    }
    qualification = {
        "schema_version": "n27p-fresh-capture-qualification-1",
        "status": "passed",
        "fresh_job_executions": 16,
        "native_export_count": 16,
        "business_outputs_match_attempt_042": True,
        "inputs_match_attempt_042": True,
        "etiq_version": "2.3.0",
        "native_api": 'create_full_lineage_graph(graph_format="json")',
        "capture_hashes": {key: value["capture_sha256"] for key, value in captures.items()},
        "native_lineage_hashes": {key: deepcopy(value["native_lineage_bindings"]) for key, value in captures.items()},
    }
    qualification["qualification_sha256"] = ce.sha256(qualification)
    ce._write_immutable(target / "qualification" / "fresh-native-captures.json", qualification)
    if compact_failures:
        blocking = {
            "schema_version": "n27p-pre-live-blocking-native-compact-1",
            "status": "failed_stop_before_packages",
            "failed_gate": "native_compact_projection_requires_non_zero_relationships_in_every_job",
            "summary": "Native Compact V0/E0 is empty for at least one job; N27P requires stopping before packages.",
            "algorithm": "V0 contains native non-cluster nodes outside all top-level clusters plus endpoints of native edges crossing a top-level subtree; E0 contains native edges with both endpoints in V0.",
            "failures": compact_failures,
            "fresh_job_captures_preserved": 16,
            "native_exports_preserved": 16,
            "packages_created": 0,
            "model_calls_made": 0,
            "live_authority_consumed": False,
            "substitution_or_pipeline_tuning_performed": False,
            "attempt_042_and_043_preserved": authority["preserved"],
        }
        blocking["blocking_sha256"] = ce.sha256(blocking)
        ce._write_immutable(target / "qualification" / "pre-live-blocking-native-compact.json", blocking)
        raise RuntimeError(blocking["summary"])
    return prepared | {"authority": authority}


def compact_topology_diagnostics(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    rows = {}
    for job_id in JOB_ORDER:
        native = catalogue["jobs"][job_id]["native_graph"]
        nodes = {value["native_node_ref"]: value for value in native["nodes"]}
        clusters = {value["native_cluster_ref"]: value for value in native["clusters"]}

        def members(cluster_ref: str, trail: tuple[str, ...] = ()) -> set[str]:
            if cluster_ref in trail:
                raise ValueError(f"N27P cyclic normalized cluster membership: {job_id}")
            found = set()
            for member in clusters[cluster_ref]["member_refs"]:
                if member in clusters:
                    found |= members(member, (*trail, cluster_ref))
                else:
                    found.add(member)
            return found

        top = native["top_level_cluster_refs"]
        descendants = {ref: members(ref) for ref in top}
        owner = {ref: cluster for cluster, values in descendants.items() for ref in values}
        root_nodes = set(nodes) - set(owner)
        crossing = [
            edge for edge in native["edges"]
            if owner.get(edge["source_ref"]) != owner.get(edge["target_ref"])
        ]
        v0 = set(root_nodes)
        for edge in crossing:
            v0.update((edge["source_ref"], edge["target_ref"]))
        e0 = [edge for edge in native["edges"] if edge["source_ref"] in v0 and edge["target_ref"] in v0]
        rows[job_id] = {
            "top_level_function_labels": sorted(clusters[ref]["captured_function_label"] for ref in top),
            "native_node_count": len(nodes),
            "native_cluster_count": len(clusters),
            "native_edge_count": len(native["edges"]),
            "root_node_count": len(root_nodes),
            "crossing_edge_count": len(crossing),
            "v0_node_count": len(v0),
            "e0_edge_count": len(e0),
            "compact_non_zero_relationship_gate": bool(e0),
        }
    return rows


def write_blocking_closure(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    authority = _verify_authority(repo_root)
    prepared = _load_prepared(target)
    original = _json(target / "qualification" / "pre-live-blocking-native-compact.json")
    ce._verified_self_hash(original, "blocking_sha256")
    topology = {instance: compact_topology_diagnostics(prepared["catalogues"][instance]) for instance in INSTANCES}
    failed = [
        {"instance_id": instance, "job_id": job, **values}
        for instance, jobs in topology.items()
        for job, values in jobs.items()
        if not values["compact_non_zero_relationship_gate"]
    ]
    if {(value["instance_id"], value["job_id"]) for value in failed} != {
        (instance, job) for instance in INSTANCES for job in (JOB3, JOB4)
    }:
        raise ValueError("N27P observed compact failure set changed")
    details = {
        "schema_version": "n27p-pre-live-blocking-native-compact-details-1",
        "status": "terminal_stop_before_packages",
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "original_blocking_record_sha256": original["blocking_sha256"],
        "topology_by_instance_and_job": topology,
        "failed_instance_job_pairs": failed,
        "failure_explanation": "For every fresh capture, Jobs 3 and 4 have no native non-cluster nodes outside their top-level function clusters and no native edge crossing a top-level subtree. The specified V0 and E0 are therefore empty for those jobs.",
        "required_action": "Stop before package construction; do not substitute isolated anchors, invent edges, tune the fixed pipeline, freeze, consume live authority or call the model.",
        "fresh_capture_count": len(list((target / "job-captures").glob("*/*.json"))),
        "native_export_count": len(list((target / "native-exports").glob("*/*/etiq-native-lineage.json"))),
        "capture_tree_sha256": ce.sha256(ce._tree_hashes(target / "captures")),
        "native_export_tree_sha256": ce.sha256(ce._tree_hashes(target / "native-exports")),
        "crosswalk_tree_sha256": ce.sha256(ce._tree_hashes(target / "native-crosswalks")),
        "package_count": len(list((target / "packages").glob("**/reviewer-package.json"))),
        "review_count": len(list((target / "reviews").glob("*.json"))),
        "provider_attempt_count": len(list((target / "ledger/call-attempt").glob("*.json"))),
        "live_authority_consumed": (target / "live-consumption.json").exists(),
        "experiment_frozen": (target / "experiment-freeze.json").exists(),
        "preservation_bindings": authority["preserved"],
    }
    if (details["fresh_capture_count"], details["native_export_count"], details["package_count"], details["review_count"], details["provider_attempt_count"]) != (16, 16, 0, 0, 0):
        raise ValueError("N27P stop-before-package counts changed")
    if details["live_authority_consumed"] or details["experiment_frozen"]:
        raise ValueError("N27P live authority or freeze exists despite the pre-live failure")
    details["details_sha256"] = ce.sha256(details)
    details_path = target / "qualification" / "pre-live-blocking-native-compact-details.json"
    ce._write_immutable(details_path, details)
    terminal = {
        "schema_version": "n27p-terminal-1",
        "status": "stopped_before_packages_native_compact_gate_failed",
        "attempt": "044",
        "fresh_job_capture_count": 16,
        "native_export_count": 16,
        "package_count": 0,
        "review_count": 0,
        "model_call_count": 0,
        "repair_count": 0,
        "live_authority_consumed": False,
        "experiment_frozen": False,
        "blocking_details_sha256": details["details_sha256"],
    }
    terminal["terminal_sha256"] = ce.sha256(terminal)
    terminal_path = target / "terminal-state.json"
    ce._write_immutable(terminal_path, terminal)
    report_dir = repo_root / "docs/workshops/ICLR/N27P-native-etiq-replication-pilot"
    findings = [
        "# N27P native-Etiq replication pilot", "",
        "Attempt 044 stopped at the mandatory pre-live native compact-projection gate. All 16 fresh `etiq-copilot==2.3.0` job captures and native JSON exports were preserved; no reviewer package was created and no model call was made.", "",
        "The blocker is structural and repeats in all four instances: Job 3 and Job 4 have no native non-cluster object outside their three top-level function clusters and no native edge crossing a top-level function subtree. The authorized V0 rule therefore selects zero nodes and the E0 rule selects zero relationships for those jobs. Compact Fixed cannot meet its required non-zero native relationships in every job.", "",
        "The controller did not insert anchors or edges, tune the fixed Attempt-042 pipeline, freeze the attempt, or consume live authority. Attempt 042 and Attempt 043 remain bound to their authorized hashes.", "",
        "## Records", "",
        "- [Detailed blocking qualification](../../../../outputs/fault-experiments-v2-2-n10/attempt-044/qualification/pre-live-blocking-native-compact-details.json)",
        "- [Fresh capture qualification](../../../../outputs/fault-experiments-v2-2-n10/attempt-044/qualification/fresh-native-captures.json)",
        "- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-044/terminal-state.json)",
    ]
    _write_text(report_dir / "findings.md", "\n".join(findings))
    lines = [
        "# Native topology and compact-gate table", "",
        "| Instance | Job | Native nodes | Clusters | Edges | Root nodes | Crossing edges | V0 | E0 | Pass |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for instance in INSTANCES:
        for job in JOB_ORDER:
            value = topology[instance][job]
            lines.append(f"| {instance} | {job} | {value['native_node_count']} | {value['native_cluster_count']} | {value['native_edge_count']} | {value['root_node_count']} | {value['crossing_edge_count']} | {value['v0_node_count']} | {value['e0_edge_count']} | {'yes' if value['compact_non_zero_relationship_gate'] else 'no'} |")
    _write_text(report_dir / "native-topology-tables.md", "\n".join(lines))
    handoff = [
        "To: Overseer", "From: Developer", "Subject: N27P Attempt 044 mandatory pre-live stop", "",
        "Status: `stopped_before_packages_native_compact_gate_failed`", "",
        "All 16 fresh native Etiq captures succeeded and reproduced Attempt 042 business outputs. In every instance, Jobs 3 and 4 yield V0=0 and E0=0 under the specified native compact algorithm because all native nodes and edges are internal to top-level function clusters.", "",
        "Per the N27P stop rule, no packages were built, the attempt was not frozen, live authority was not consumed, and no model calls or repairs occurred.", "",
        f"Detailed qualification logical hash: `{details['details_sha256']}`",
        f"Terminal logical hash: `{terminal['terminal_sha256']}`",
    ]
    _write_text(repo_root / "instructions_between_agent_types/developer/handoffs/N27P_attempt_044_pre_live_blocker_to_overseer.email.md", "\n".join(handoff))
    return terminal_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("capture", "close-blocked"))
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    try:
        if args.operation == "capture":
            prepare_attempt(repo_root)
            print("N27P native capture and compact qualification passed")
        else:
            print(write_blocking_closure(repo_root))
    except RuntimeError as exc:
        print(f"N27P stopped before packages: {exc}")
        return 2
    except Exception as exc:
        print(f"N27P failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
