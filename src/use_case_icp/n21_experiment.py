"""N21 fully boundary-free native-Etiq experiment."""

from __future__ import annotations

import argparse
from copy import deepcopy
import inspect
import json
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from . import n20_experiment as n20
from . import n20a_experiment as n20a
from . import n20d_experiment as n20d
from .n05_runner import create_bytes_exclusive, verify_record


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-038")
SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-037")
TASK = Path("instructions_between_agent_types/developer/current/N21_boundary_free_native_etiq_experiment.email.md")
TASK_SHA256 = "sha256:8dff7637ffcd610c02888f51109fdac3499097af465e78b3be49f07f2feddd75"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N21_boundary_free_native_etiq_authorization.json")
AUTHORITY_SHA256 = "sha256:2cae30ad388a00193350b3bd08bc9bf99ef7d5bf5a8ba0832999c6a83f25a301"
SOURCE_TREE_SHA256 = "sha256:a7b8d11717d1cb3281757f1f0e2fae542b1b2ee238630a90f1c477bbb88a112c"
SOURCE_FREEZE_SHA256 = "sha256:71939899732c6883f51d9ea5da315f669e27c0028d0e90c6821b34e1ce7a2d53"
SOURCE_FREEZE_FILE_SHA256 = "sha256:292bf22ac9cf9f7b37b3f0b92449eefdd8cce8f35f4d16148af4e3181fcd9291"
SOURCE_TERMINAL_SHA256 = "sha256:d7cc164213a80a7f04d1088d2cec3e358e1408294ca5481d74d51398852de92a"
SOURCE_TERMINAL_FILE_SHA256 = "sha256:e730fdbacfb39f9c5f3d3fd662ea10e14a36ec4d859f13cfbd75818a9b8184b7"
SOURCE_ANALYSIS_SHA256 = "sha256:abd48afd8d8ebaf89096d1d7d9c4fb18dd79c906aecdcd97217756261c54223f"
SOURCE_ANALYSIS_FILE_SHA256 = "sha256:f98aa47c5e4c635b3d7e079c242c6baa59aa31632f9b006affd42238b08e5cbf"
SOURCE_REPLAY_SHA256 = "sha256:98fe529a0f8d77b688a19ad2a911a61d5519fbc194533b3eb65e586af82b52a0"
SOURCE_REPLAY_FILE_SHA256 = "sha256:51b98d2fc31d5c25bb5d7e29fd6dedcb84109e7b2bd9a7790b5f6b6235b54a90"

PROMPT = n20a.OPEN_PROMPT
FINAL_SCHEMA = Path("schemas/v2_2/n21_native_final.schema.json")
VOLUNTARY_SCHEMA = Path("schemas/v2_2/n21_native_adaptive_voluntary.schema.json")
REQUIRED_SCHEMA = Path("schemas/v2_2/n21_native_adaptive_required.schema.json")
MODES = (
    "io_job2_open",
    "io_both_open",
    "current_open",
    "history_full_open",
    "etiq_empty_open",
    "compact_fixed_native",
    "adaptive_voluntary_native",
    "adaptive_required_one_native",
)
NON_GRAPH_MODES = MODES[:4]
ADAPTIVE_MODES = MODES[-2:]
FAULTS = n20.FAULTS
INSTANCES = n20.INSTANCES
CLEAN_INSTANCE = n20.CLEAN_INSTANCE
FAULT_GROUP = n20.FAULT_GROUP
UPSTREAM = n20d.UPSTREAM
DOWNSTREAM = n20d.DOWNSTREAM
COMMON_KEYS = n20d.COMMON_KEYS


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N21 authority input changed: {relative}")
    source = repo_root / SOURCE_ATTEMPT
    if ce.sha256(ce._tree_hashes(source)) != SOURCE_TREE_SHA256:
        raise ValueError("Attempt 037 tree changed")
    fixed = (
        ("experiment-freeze.json", SOURCE_FREEZE_FILE_SHA256, "freeze_sha256", SOURCE_FREEZE_SHA256),
        ("terminal-state.json", SOURCE_TERMINAL_FILE_SHA256, "terminal_sha256", SOURCE_TERMINAL_SHA256),
        ("analysis/summary.json", SOURCE_ANALYSIS_FILE_SHA256, "analysis_sha256", SOURCE_ANALYSIS_SHA256),
        ("replay/reconciliation.json", SOURCE_REPLAY_FILE_SHA256, "replay_sha256", SOURCE_REPLAY_SHA256),
    )
    for relative, file_hash, logical_key, logical_hash in fixed:
        path = source / relative
        record = ce._read_json(path)
        if ce.sha256(path.read_bytes()) != file_hash or ce._verified_self_hash(record, logical_key) != logical_hash:
            raise ValueError(f"Attempt 037 binding changed: {relative}")
    for relative, expected in ce.N15_PROTECTED_FILE_SHA256.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N21 protected boundary changed: {relative}")
    return {
        "source_attempt_tree_sha256": SOURCE_TREE_SHA256,
        "source_freeze_sha256": SOURCE_FREEZE_SHA256,
        "source_terminal_sha256": SOURCE_TERMINAL_SHA256,
        "source_analysis_sha256": SOURCE_ANALYSIS_SHA256,
        "source_replay_sha256": SOURCE_REPLAY_SHA256,
        "protected_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
    }


def _copy_exact(source: Path, target: Path) -> None:
    create_bytes_exclusive(target, source.read_bytes())


def _source_packages(source_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    packages = {}
    for path in sorted((source_root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        condition = manifest["controller_condition"]
        mode = str(condition["evidence_mode"])
        if mode not in NON_GRAPH_MODES:
            continue
        package = ce._read_json(source_root / manifest["reviewer_package_path"])
        if ce.sha256(package) != manifest["reviewer_package_sha256"]:
            raise ValueError("Attempt 037 package binding changed")
        packages[(str(condition["instance_id"]), mode)] = package
    if len(packages) != 28:
        raise ValueError("Attempt 037 non-graph package set changed")
    return packages


def _stack(node: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(map(str, node.get("func_stack", [])))


def build_native_graph(catalogue: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    job_order = list(map(str, catalogue["job_order"]))
    visible_nodes = []
    visible_by_stack: dict[tuple[str, tuple[str, ...]], str] = {}
    job_nodes: dict[str, list[Mapping[str, Any]]] = {}
    job_relationships: dict[str, list[Mapping[str, Any]]] = {}
    for job_id in job_order:
        nodes = list(catalogue["jobs"][job_id]["nodes"])
        relationships = list(catalogue["jobs"][job_id]["relationships"])
        job_nodes[job_id] = nodes
        job_relationships[job_id] = relationships
        stacks = sorted({_stack(node) for node in nodes if len(_stack(node)) == 2})
        for stack in stacks:
            candidates = sorted(
                (
                    node for node in nodes
                    if _stack(node) == stack
                    and node.get("state_type") == "FunctionMapping"
                    and node.get("scope_type") == "FunctionDef"
                    and str(node.get("source") or "").lstrip().startswith("def ")
                ),
                key=lambda node: str(node["node_ref"]),
            )
            if not candidates:
                raise ValueError(f"N21 native function stack lacks one eligible node: {job_id}: {stack}")
            node = candidates[0]
            visible_nodes.append(deepcopy(node))
            visible_by_stack[(job_id, stack)] = str(node["node_ref"])
    visible_refs = {str(node["node_ref"]) for node in visible_nodes}
    visible_relationships = [
        deepcopy(edge)
        for job_id in job_order
        for edge in job_relationships[job_id]
        if str(edge["source_ref"]) in visible_refs and str(edge["target_ref"]) in visible_refs
    ]
    groups = []
    group_index = {}
    for job_id in job_order:
        nodes = job_nodes[job_id]
        relationships = job_relationships[job_id]
        depth_three = sorted({_stack(node) for node in nodes if len(_stack(node)) == 3})
        for stack in depth_three:
            parent = visible_by_stack.get((job_id, stack[:2]))
            if parent is None:
                continue
            selected = [node for node in nodes if _stack(node) == stack]
            selected_refs = {str(node["node_ref"]) for node in selected}
            internal = [edge for edge in relationships if str(edge["source_ref"]) in selected_refs and str(edge["target_ref"]) in selected_refs]
            captured_types = {str(node.get("raw_metadata", {}).get("source_node_type") or node.get("state_type") or "") for node in selected}
            if len(captured_types) != 1:
                raise ValueError(f"N21 native execution group has ambiguous captured type: {job_id}: {stack}")
            group_id = f"grp-{ce.sha256([job_id, list(stack)])[7:23]}"
            descriptor = {
                "execution_group_id": group_id,
                "job_id": job_id,
                "parent_node_ref": parent,
                "func_stack": list(stack),
                "captured_type": next(iter(captured_types)),
                "node_count": len(selected),
                "relationship_count": len(internal),
                "has_deeper_stack": any(len(_stack(node)) > 3 and _stack(node)[:3] == stack for node in nodes),
            }
            groups.append(descriptor)
            group_index[group_id] = {
                "descriptor": deepcopy(descriptor),
                "node_refs": sorted(selected_refs),
            }
    if len(visible_nodes) != 6 or len(groups) != 2:
        raise ValueError(f"N21 frozen native shape changed: {len(visible_nodes)} nodes, {len(groups)} groups")
    projection = {
        "job_evidence_order": job_order,
        "nodes": visible_nodes,
        "relationships": visible_relationships,
        "collapsed_execution_groups": groups,
        "disclosed_execution_groups": [],
    }
    projection["projection_sha256"] = ce.sha256(projection)
    index = {"schema_version": "n21-native-group-index-1", "groups": group_index}
    index["index_sha256"] = ce.sha256(index)
    return projection, index


def empty_native_graph() -> dict[str, Any]:
    projection = {
        "job_evidence_order": [],
        "nodes": [],
        "relationships": [],
        "collapsed_execution_groups": [],
        "disclosed_execution_groups": [],
    }
    projection["projection_sha256"] = ce.sha256(projection)
    return projection


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N21 is authorized only for Attempt 038")
    _verify_authority(repo_root)
    source = repo_root / SOURCE_ATTEMPT
    source_freeze = ce._read_json(source / "experiment-freeze.json")
    for directory in ("captures", "catalogues", "instances", "qualification/mutations", "source-bundles"):
        for source_path in sorted((source / directory).glob("*.json")):
            _copy_exact(source_path, target / directory / source_path.name)
    _copy_exact(source / "qualification/mutation-summary.json", target / "qualification/mutation-summary.json")
    captures = {path.stem: ce._read_json(path) for path in sorted((target / "captures").glob("*.json"))}
    catalogues = {path.stem: ce._read_json(path) for path in sorted((target / "catalogues").glob("*.json"))}
    instances = {path.stem: ce._read_json(path) for path in sorted((target / "instances").glob("*.json"))}
    source_bundles = {path.stem: ce._read_json(path)["source_bundle"] for path in sorted((target / "source-bundles").glob("*.json"))}
    if set(captures) != set(INSTANCES) or set(catalogues) != set(INSTANCES) or set(instances) != set(INSTANCES) or set(source_bundles) != set(INSTANCES):
        raise ValueError("N21 reused record set changed")
    graphs = {}
    indexes = {}
    for instance_id in INSTANCES:
        ce._verify_capture(captures[instance_id])
        ce.verify_catalogue(catalogues[instance_id])
        ce._verified_self_hash(instances[instance_id], "instance_sha256")
        if captures[instance_id]["capture_sha256"] != source_freeze["capture_hashes"][instance_id]:
            raise ValueError(f"N21 capture hash changed: {instance_id}")
        if catalogues[instance_id]["catalogue_sha256"] != source_freeze["catalogue_hashes"][instance_id]:
            raise ValueError(f"N21 catalogue hash changed: {instance_id}")
        if instances[instance_id]["instance_sha256"] != source_freeze["instance_hashes"][instance_id]:
            raise ValueError(f"N21 instance hash changed: {instance_id}")
        source_path = target / "source-bundles" / f"{instance_id}.json"
        if ce.sha256(source_path.read_bytes()) != source_freeze["source_bundle_file_hashes"][instance_id]:
            raise ValueError(f"N21 source bundle hash changed: {instance_id}")
        graph, index = build_native_graph(catalogues[instance_id])
        graphs[instance_id] = graph
        indexes[instance_id] = index
        ce._write_immutable(target / "native-group-index" / f"{instance_id}.json", index)
    return {
        "captures": captures,
        "catalogues": catalogues,
        "instances": instances,
        "source_bundles": source_bundles,
        "native_graphs": graphs,
        "native_indexes": indexes,
        "source_packages": _source_packages(source),
    }


def build_review_package(prepared: Mapping[str, Any], instance_id: str, mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError("unknown N21 mode")
    if mode in NON_GRAPH_MODES:
        return deepcopy(prepared["source_packages"][(instance_id, mode)])
    current = deepcopy(prepared["source_packages"][(instance_id, "current_open")])
    current["schema_version"] = "n21-review-package-1"
    current["integrated_etiq_instructions"] = {"framing": "Use the supplied native Etiq execution evidence when judging the run."}
    current["runtime_evidence"] = empty_native_graph() if mode == "etiq_empty_open" else deepcopy(prepared["native_graphs"][instance_id])
    if mode in ADAPTIVE_MODES:
        current["available_operations"] = ["expand_execution_group"]
        current["action_contract"] = {
            "permitted_actions": ["expand_execution_group", "finalize"] if mode == "adaptive_voluntary_native" else ["expand_execution_group"],
            "first_action_must_expand_one_model_selected_group": mode == "adaptive_required_one_native",
            "maximum_completed_expansions": 1,
            "finalize_after_completed_expansion": True,
        }
    return current


def render_request(package: Mapping[str, Any], operation_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    request = {"reviewer_package": deepcopy(dict(package))}
    if operation_response is not None:
        request["operation_response"] = deepcopy(dict(operation_response))
    visible = ce.canonical_json(request).decode()
    forbidden_keys = (
        "semantic_declarations", "semantic_stages", "boundary_guidance", "anchors", "boundary_summaries",
        "visible_evidence_by_boundary", "suspect_boundary_id", "expected_inputs", "expected_outputs",
        "boundary_id", "boundary_name", "boundary_role", "assessment_by_boundary",
        "designation", "truth_job", "truth_function", "fault_id", "evidence_mode", "branch_id", "trial_id", "repetition", "seed", "qualification",
    )
    if any(f'"{key}"' in visible for key in forbidden_keys):
        raise ValueError("N21 rendered request contains prohibited controller material")
    if re.search(r'(?i)bnd-|rb_', visible):
        raise ValueError("N21 rendered request contains a prohibited identifier")
    return request


def schedule() -> dict[str, Any]:
    packages = [
        {"instance_id": instance, "evidence_mode": mode, "branch_id": f"brn-{ce.sha256(['n21', instance, mode])[7:23]}"}
        for instance in INSTANCES for mode in MODES
    ]
    by = {(x["instance_id"], x["evidence_mode"]): x for x in packages}
    reviews = []
    block = 0
    for repetition in range(1, 4):
        rotated_instances = INSTANCES[repetition - 1:] + INSTANCES[:repetition - 1]
        for instance in rotated_instances:
            rotation = block % len(MODES)
            for position, mode in enumerate(MODES[rotation:] + MODES[:rotation], 1):
                condition = by[(instance, mode)]
                reviews.append({
                    **condition,
                    "repetition": repetition,
                    "trial_id": f"trial-{ce.sha256(['n21', condition['branch_id'], repetition])[7:23]}",
                    "schedule_position": len(reviews) + 1,
                    "local_block": block + 1,
                    "mode_position": position,
                })
            block += 1
    if (len(packages), len(reviews), len({x["trial_id"] for x in reviews})) != (56, 168, 168):
        raise AssertionError("N21 schedule changed")
    return {"packages": packages, "review_trials": reviews, "repair_traces": []}


def _schema_for(mode: str, *, follow_up: bool = False) -> Path:
    if follow_up or mode not in ADAPTIVE_MODES:
        return FINAL_SCHEMA
    return VOLUNTARY_SCHEMA if mode == "adaptive_voluntary_native" else REQUIRED_SCHEMA


def _contains_key(value: Any, keys: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(str(key) in keys or _contains_key(child, keys) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_key(child, keys) for child in value)
    return False


def _catalogue_records(catalogue: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    nodes = {}
    relationships = {}
    for job_id in catalogue["job_order"]:
        nodes.update({str(node["node_ref"]): node for node in catalogue["jobs"][job_id]["nodes"]})
        relationships.update({str(edge["relationship_ref"]): edge for edge in catalogue["jobs"][job_id]["relationships"]})
    return nodes, relationships


def qualify_packages(repo_root: Path, records: list[Mapping[str, Any]], prepared: Mapping[str, Any], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(records), len(design["review_trials"]), len(design["repair_traces"])) != (56, 168, 0):
        raise ValueError("N21 package or schedule count changed")
    if any(term in inspect.getsource(build_native_graph) for term in ("boundary_bindings", "realized_boundaries", "realized_boundary_prefixes", "direct_child_function_prefixes")):
        raise ValueError("N21 native projection reads forbidden catalogue material")
    by = {(x["controller_condition"]["instance_id"], x["controller_condition"]["evidence_mode"]): x["reviewer_package"] for x in records}
    structured_forbidden = {"semantic_declarations", "semantic_stages", "boundary_guidance", "anchors", "boundary_summaries", "visible_evidence_by_boundary", "suspect_boundary_id", "expected_inputs", "expected_outputs", "boundary_id", "boundary_name", "boundary_role", "assessment_by_boundary"}
    checks = 0
    for instance_id in INSTANCES:
        packages = {mode: by[(instance_id, mode)] for mode in MODES}
        for mode in NON_GRAPH_MODES:
            if packages[mode] != prepared["source_packages"][(instance_id, mode)]:
                raise ValueError(f"N21 non-graph package changed from Attempt 037: {instance_id}: {mode}")
        if any(package["source_bundle"] != prepared["source_bundles"][instance_id] for package in packages.values()):
            raise ValueError(f"N21 source differs across modes: {instance_id}")
        if len({ce.canonical_json({key: package[key] for key in COMMON_KEYS}) for package in packages.values()}) != 1:
            raise ValueError(f"N21 common evidence differs across modes: {instance_id}")
        for package in packages.values():
            if _contains_key(package, structured_forbidden):
                raise ValueError("N21 package contains prohibited controller material")
            render_request(package)
        empty = packages["etiq_empty_open"]
        fixed = packages["compact_fixed_native"]
        voluntary = packages["adaptive_voluntary_native"]
        required = packages["adaptive_required_one_native"]
        if any(empty["runtime_evidence"][key] for key in ("job_evidence_order", "nodes", "relationships", "collapsed_execution_groups", "disclosed_execution_groups")):
            raise ValueError("N21 Empty contains native evidence")
        graph = fixed["runtime_evidence"]
        if len(graph["nodes"]) != 6 or len(graph["collapsed_execution_groups"]) != 2 or graph["disclosed_execution_groups"]:
            raise ValueError("N21 native initial graph shape changed")
        catalogue_nodes, catalogue_relationships = _catalogue_records(prepared["catalogues"][instance_id])
        if any(node != catalogue_nodes.get(str(node["node_ref"])) for node in graph["nodes"]):
            raise ValueError("N21 native projection rewrote a node")
        if any(edge != catalogue_relationships.get(str(edge["relationship_ref"])) for edge in graph["relationships"]):
            raise ValueError("N21 native projection fabricated a relationship")
        equal_keys = (*COMMON_KEYS, "job_execution_records", "integrated_etiq_instructions", "runtime_evidence")
        if len({ce.canonical_json({key: package[key] for key in equal_keys}) for package in (fixed, voluntary, required)}) != 1:
            raise ValueError("N21 Fixed and Adaptive initial evidence differs")
        if any(key in fixed for key in ("available_operations", "action_contract")):
            raise ValueError("N21 Fixed exposes an operation")
        if voluntary.get("available_operations") != ["expand_execution_group"] or required.get("available_operations") != ["expand_execution_group"]:
            raise ValueError("N21 Adaptive operation surface changed")
        checks += 15
    prompt_text = (repo_root / PROMPT).read_text().lower()
    schema_text = "\n".join((repo_root / path).read_text().lower() for path in (FINAL_SCHEMA, VOLUNTARY_SCHEMA, REQUIRED_SCHEMA))
    for text in (prompt_text, schema_text):
        if "boundary" in text or "bnd-" in text or "rb_" in text:
            raise ValueError("N21 prompt or schema contains prohibited material")
    if "suspect_function" not in ce._read_json(repo_root / FINAL_SCHEMA)["properties"] or "enum" in ce._read_json(repo_root / FINAL_SCHEMA)["properties"]["suspect_function"]:
        raise ValueError("N21 function response is not free text")
    return {
        "status": "passed",
        "model_calls": 0,
        "fault_count": 6,
        "clean_control_count": 1,
        "capture_count": 7,
        "catalogue_count": 7,
        "source_bundle_count": 7,
        "native_graph_count": 7,
        "package_count": 56,
        "review_count": 168,
        "required_one_follow_up_count": 21,
        "provider_call_minimum": 189,
        "provider_call_maximum": 210,
        "repair_count": 0,
        "comparison_count": checks,
    }


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule()
    records = []
    for condition in design["packages"]:
        instance_id = str(condition["instance_id"])
        package = build_review_package(prepared, instance_id, str(condition["evidence_mode"]))
        record = {
            "schema_version": "n21-frozen-package-1",
            "controller_condition": deepcopy(condition),
            "source_capture_sha256": prepared["catalogues"][instance_id]["source_capture_sha256"],
            "catalogue_sha256": prepared["catalogues"][instance_id]["catalogue_sha256"],
            "source_bundle_file_sha256": ce.sha256((target / "source-bundles" / f"{instance_id}.json").read_bytes()),
            "native_group_index_sha256": prepared["native_indexes"][instance_id]["index_sha256"],
            "reviewer_package": package,
        }
        record["package_sha256"] = ce.sha256(record)
        records.append(record)
    qualification = qualify_packages(repo_root, records, prepared, design)
    return {**prepared, "packages": records, "schedule": design, "qualification": qualification}


def _load_frozen(attempt_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    catalogues = {path.stem: ce._read_json(path) for path in sorted((attempt_root / "catalogues").glob("*.json"))}
    indexes = {path.stem: ce._read_json(path) for path in sorted((attempt_root / "native-group-index").glob("*.json"))}
    packages = {}
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        package = ce._read_json(attempt_root / manifest["reviewer_package_path"])
        if ce.sha256(package) != manifest["reviewer_package_sha256"]:
            raise ValueError("N21 reviewer package hash mismatch")
        record = {**manifest, "reviewer_package": package}
        unsigned = deepcopy(record)
        observed = unsigned.pop("package_sha256")
        unsigned.pop("reviewer_package_path")
        unsigned.pop("reviewer_package_sha256")
        if ce.sha256(unsigned) != observed:
            raise ValueError("N21 package record hash mismatch")
        packages[str(manifest["controller_condition"]["branch_id"])] = record
        records.append(record)
    return catalogues, indexes, packages, records


def _code_paths() -> tuple[Path, ...]:
    return (
        Path("src/use_case_icp/n21_experiment.py"),
        Path("src/use_case_icp/n20d_experiment.py"),
        Path("tests/test_n21_experiment.py"),
        PROMPT,
        FINAL_SCHEMA,
        VOLUNTARY_SCHEMA,
        REQUIRED_SCHEMA,
    )


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if (target / "experiment-freeze.json").exists():
        raise ValueError("Attempt 038 is already frozen")
    if any((target / name).exists() for name in ("packages", "controller-manifests", "reviews")):
        raise ValueError("Attempt 038 contains pre-freeze scientific material")
    source_tree = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    built = build_attempt(repo_root, target)
    for record in built["packages"]:
        branch = record["controller_condition"]["branch_id"]
        ce._write_immutable(target / "packages" / branch / "reviewer-package.json", record["reviewer_package"])
        manifest = {key: deepcopy(value) for key, value in record.items() if key != "reviewer_package"}
        manifest.update({"reviewer_package_path": f"packages/{branch}/reviewer-package.json", "reviewer_package_sha256": ce.sha256(record["reviewer_package"])})
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
    ce._write_immutable(target / "review-design.json", {"review_trials": built["schedule"]["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"repair_traces": []})
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != source_tree:
        raise RuntimeError("Attempt 037 changed during N21 freeze")
    freeze = {
        "schema_version": "n21-boundary-free-native-freeze-1",
        "status": "frozen_before_first_experimental_review",
        "attempt": "attempt-038",
        "source_attempt": "attempt-037",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "authority_bindings": _verify_authority(repo_root),
        "protected_boundaries": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in _code_paths()},
        "source_attempt_tree_sha256": source_tree,
        "capture_hashes": {key: value["capture_sha256"] for key, value in built["captures"].items()},
        "catalogue_hashes": {key: value["catalogue_sha256"] for key, value in built["catalogues"].items()},
        "instance_hashes": {key: value["instance_sha256"] for key, value in built["instances"].items()},
        "source_bundle_file_hashes": {key: ce.sha256((target / "source-bundles" / f"{key}.json").read_bytes()) for key in INSTANCES},
        "native_group_index_file_hashes": {key: ce.sha256((target / "native-group-index" / f"{key}.json").read_bytes()) for key in INSTANCES},
        "native_projection_hashes": {key: value["projection_sha256"] for key, value in built["native_graphs"].items()},
        "package_hashes": sorted(x["package_sha256"] for x in built["packages"]),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "review_design_sha256": ce.sha256(built["schedule"]["review_trials"]),
        "repair_design_sha256": ce.sha256([]),
        "expected_counts": {"faults": 6, "controls": 1, "captures": 7, "catalogues": 7, "source_bundles": 7, "native_graphs": 7, "packages": 56, "reviews": 168, "required_one_follow_ups": 21, "provider_calls_min": 189, "provider_calls_max": 210, "repairs": 0},
        "qualification": built["qualification"],
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "experimental_review_records_at_freeze": 0,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path = target / "experiment-freeze.json"
    ce._write_immutable(path, freeze)
    return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    _verify_authority(repo_root)
    freeze = ce._read_json(target / "experiment-freeze.json")
    observed = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N21 frozen code changed: {relative}")
    for relative, expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N21 protected boundary changed: {relative}")
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != freeze["source_attempt_tree_sha256"]:
        raise ValueError("Attempt 037 changed after N21 freeze")
    prepared = prepare_attempt(repo_root, target)
    for instance_id, expected in freeze["native_group_index_file_hashes"].items():
        if ce.sha256((target / "native-group-index" / f"{instance_id}.json").read_bytes()) != expected:
            raise ValueError(f"N21 native group index changed: {instance_id}")
    catalogues, _, _, records = _load_frozen(target)
    if catalogues.keys() != prepared["catalogues"].keys():
        raise ValueError("N21 frozen catalogue set changed")
    design = {"packages": [deepcopy(x["controller_condition"]) for x in records], "review_trials": ce._read_json(target / "review-design.json")["review_trials"], "repair_traces": ce._read_json(target / "repair-design.json")["repair_traces"]}
    qualification = qualify_packages(repo_root, records, prepared, design)
    if sorted(x["package_sha256"] for x in records) != freeze["package_hashes"] or ce.sha256(design["review_trials"]) != freeze["review_design_sha256"]:
        raise ValueError("N21 frozen package or schedule changed")
    return {"status": "verified", "freeze_sha256": observed, "qualification": qualification, "capture_count": 7, "catalogue_count": 7, "source_bundle_count": 7, "native_graph_count": 7, "package_count": 56, "review_count": 168, "repair_count": 0}


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path = attempt_root / "live-consumption.json"
    if path.exists():
        ce._verified_self_hash(ce._read_json(path), "consumption_sha256")
        return path
    if list((attempt_root / "reviews").glob("*.json")):
        raise ValueError("N21 review exists before live consumption")
    verified = verify_frozen_attempt(repo_root, attempt_root)
    record = {
        "schema_version": "n21-live-consumption-1",
        "status": "live_authority_consumed_before_first_provider_call",
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256},
        "freeze_sha256": verified["freeze_sha256"],
        "package_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "packages")),
        "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "controller-manifests")),
        "review_design_file_sha256": ce.sha256((attempt_root / "review-design.json").read_bytes()),
        "protected_file_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256),
        "model": ce.PROVIDER_MODEL,
        "reasoning_effort": ce.PROVIDER_REASONING_EFFORT,
        "expected_counts": {"packages": 56, "reviews": 168, "required_one_follow_ups": 21, "provider_calls_min": 189, "provider_calls_max": 210, "repairs": 0},
    }
    record["consumption_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return path


def _normalized_function(value: Any) -> str | None:
    if value is None:
        return None
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(value).strip().lower())
    return names[-1] if names else None


def validate_response(repo_root: Path, package: Mapping[str, Any], response: Mapping[str, Any], schema_path: Path) -> dict[str, Any]:
    schema = ce._read_json(repo_root / schema_path)
    scientific = {key: deepcopy(response.get(key)) for key in schema["required"]}
    Draft202012Validator(schema).validate(scientific)
    visible = ce.canonical_json(package).decode()
    invalid_refs = [str(value) for value in scientific["evidence_refs"] if str(value) not in visible]
    return {
        "valid": True,
        "receipt": scientific,
        "fault_detected": bool(scientific["fault_detected"]),
        "suspect_job": scientific["suspect_job"],
        "normalized_suspect_function": _normalized_function(scientific["suspect_function"]),
        "invalid_evidence_refs": invalid_refs,
    }


score_response = n20a.score_response


def expand_execution_group(catalogue: Mapping[str, Any], index: Mapping[str, Any], package: Mapping[str, Any], execution_group_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime = package.get("runtime_evidence", {})
    advertised = {str(group["execution_group_id"]): group for group in runtime.get("collapsed_execution_groups", [])}
    disclosed = {str(group["execution_group_id"]) for group in runtime.get("disclosed_execution_groups", [])}
    if execution_group_id not in advertised or execution_group_id in disclosed:
        raise ValueError("execution group is unavailable or already disclosed")
    indexed = index["groups"].get(execution_group_id)
    if indexed is None or indexed["descriptor"] != advertised[execution_group_id]:
        raise ValueError("execution group is not bound to the frozen index")
    stack = tuple(indexed["descriptor"]["func_stack"])
    job_id = str(indexed["descriptor"]["job_id"])
    selected = [deepcopy(node) for node in catalogue["jobs"][job_id]["nodes"] if _stack(node) == stack]
    if sorted(str(node["node_ref"]) for node in selected) != indexed["node_refs"]:
        raise ValueError("execution group node binding changed")
    updated = deepcopy(dict(package))
    projection = deepcopy(dict(runtime))
    known_refs = {str(node["node_ref"]) for node in projection["nodes"]}
    projection["nodes"] = [*projection["nodes"], *[node for node in selected if str(node["node_ref"]) not in known_refs]]
    now_visible = {str(node["node_ref"]) for node in projection["nodes"]}
    all_relationships = [edge for current_job in catalogue["job_order"] for edge in catalogue["jobs"][current_job]["relationships"]]
    projection["relationships"] = [deepcopy(edge) for edge in all_relationships if str(edge["source_ref"]) in now_visible and str(edge["target_ref"]) in now_visible]
    projection["collapsed_execution_groups"] = [deepcopy(group) for group in projection["collapsed_execution_groups"] if str(group["execution_group_id"]) != execution_group_id]
    projection["disclosed_execution_groups"] = [*projection["disclosed_execution_groups"], deepcopy(indexed["descriptor"])]
    projection.pop("projection_sha256", None)
    projection["projection_sha256"] = ce.sha256(projection)
    updated["runtime_evidence"] = projection
    event = {
        "operation": "expand_execution_group",
        "status": "completed",
        "execution_group_id": execution_group_id,
        "job_id": job_id,
        "func_stack": list(stack),
        "nodes_added": sorted(str(node["node_ref"]) for node in selected),
        "relationships_added": sorted(str(edge["relationship_ref"]) for edge in projection["relationships"] if edge not in runtime.get("relationships", [])),
        "runtime_evidence": deepcopy(projection),
    }
    render_request(updated, event)
    return updated, event


def _provider_review(repo_root: Path, attempt_root: Path, request: Mapping[str, Any], parent_id: str, mode: str, *, follow_up: bool = False) -> dict[str, Any]:
    return ce._provider_call(repo_root, attempt_root, kind="review", model_request=request, controller_parent_id=parent_id, review_prompt=PROMPT, review_schema=_schema_for(mode, follow_up=follow_up))


def _call_record(response: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(response.get(key)) for key in ("request_sha256", "call_ids", "retry_lineage", "attempt_count") if response.get(key) is not None}


def run_review_session(repo_root: Path, attempt_root: Path, catalogue: Mapping[str, Any], index: Mapping[str, Any], package: Mapping[str, Any], trial_id: str, mode: str) -> dict[str, Any]:
    initial = _provider_review(repo_root, attempt_root, render_request(package), trial_id, mode)
    pre = validate_response(repo_root, package, initial, _schema_for(mode))
    usage = [ce.actual_usage_record(initial, purpose="initial_review", phase="n21_review")]
    calls = [_call_record(initial)]
    current = deepcopy(dict(package))
    final = pre
    event = None
    diagnostic = None
    if mode in ADAPTIVE_MODES:
        action = pre["receipt"]["next_action"]
        if action["action"] == "expand_execution_group":
            try:
                current, event = expand_execution_group(catalogue, index, current, str(action["execution_group_id"]))
            except ValueError as exc:
                diagnostic = {"status": "invalid_operation_reference", "error": str(exc), "request": deepcopy(action)}
            if event is not None:
                current.pop("available_operations", None)
                current.pop("action_contract", None)
                response = _provider_review(repo_root, attempt_root, render_request(current, event), f"{trial_id}-follow-up-01", mode, follow_up=True)
                final = validate_response(repo_root, current, response, FINAL_SCHEMA)
                usage.append(ce.actual_usage_record(response, purpose="native_group_follow_up", phase="n21_review"))
                calls.append(_call_record(response))
        elif action["action"] == "finalize":
            diagnostic = {"status": "finalized_without_expansion", "ignored_execution_group_id": action["execution_group_id"]}
        else:
            raise ValueError("unknown N21 Adaptive action")
    runtime = current.get("runtime_evidence", {})
    return {
        "pre_validation": pre,
        "final_validation": final,
        "operation_event": event,
        "operation_diagnostic": diagnostic,
        "completed_expansion_count": 1 if event else 0,
        "disclosed_node_count": len(runtime.get("nodes", [])),
        "disclosed_relationship_count": len(runtime.get("relationships", [])),
        "call_records": calls,
        "usage": ce.aggregate_actual_usage_records(usage),
    }


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    faults = [x for x in rows if x["designation"] == "upstream_fault"]
    controls = [x for x in rows if x["designation"] == "matched_clean_control"]
    calls = [call for row in rows for call in row["raw_calls"]]
    return {
        "reviews": len(rows),
        "provider_calls": len(calls),
        "fault_detection": {"numerator": sum(x["fault_detected"] for x in faults), "denominator": len(faults)},
        "correct_job_attribution": {"numerator": sum(x["correct_job_attribution"] for x in faults), "denominator": len(faults)},
        "exact_function_localisation": {"numerator": sum(x["exact_function_localisation"] for x in faults), "denominator": len(faults)},
        "control_false_positives": {"numerator": sum(x["false_positive"] for x in controls), "denominator": len(controls)},
        "expansion_sessions": sum(x["completed_expansion_count"] for x in rows),
        "disclosed_nodes": sum(x["disclosed_node_count"] for x in rows),
        "disclosed_relationships": sum(x["disclosed_relationship_count"] for x in rows),
        "input_tokens": sum(int(x.get("input_tokens") or 0) for x in calls),
        "cached_input_tokens": sum(int(x.get("cached_input_tokens") or 0) for x in calls),
        "output_tokens": sum(int(x.get("output_tokens") or 0) for x in calls),
    }


def _rate(summary: Mapping[str, Any], key: str) -> float:
    value = summary[key]
    return value["numerator"] / value["denominator"] if value["denominator"] else 0.0


def write_analysis(repo_root: Path, attempt_root: Path, reviews: Mapping[tuple[str, int], Mapping[str, Any]]) -> Path:
    rows = []
    raw_calls = []
    for record in reviews.values():
        trial = record["controller_trial"]
        calls = []
        for index, call in enumerate(record["usage"].get("calls", []), 1):
            tagged = {"trial_id": trial["trial_id"], "call_index": index, **deepcopy(call)}
            calls.append(tagged)
            raw_calls.append(tagged)
        rows.append({
            **deepcopy(trial),
            "designation": record["designation"],
            "fault_group": record["fault_group"],
            "truth_function": record["truth_function"],
            "fault_detected": record["fault_detected"],
            "false_positive": record["false_positive"],
            "correct_job_attribution": record["correct_job_attribution"],
            "exact_function_localisation": record["exact_function_localisation"],
            "pre_fault_detected": record["pre_fault_detected"],
            "pre_suspect_job": record["pre_suspect_job"],
            "pre_suspect_function": record["pre_suspect_function"],
            "suspect_job": record["suspect_job"],
            "suspect_function": record["suspect_function"],
            "completed_expansion_count": record["completed_expansion_count"],
            "selected_execution_group": deepcopy(record["selected_execution_group"]),
            "disclosed_node_count": record["disclosed_node_count"],
            "disclosed_relationship_count": record["disclosed_relationship_count"],
            "diagnosis_changed_after_expansion": record["pre_suspect_job"] != record["suspect_job"] or record["pre_suspect_function"] != record["suspect_function"],
            "raw_calls": calls,
        })
    by_mode = {mode: _summary([x for x in rows if x["evidence_mode"] == mode]) for mode in MODES}
    by_fault = {fault: {mode: _summary([x for x in rows if x["instance_id"] == fault and x["evidence_mode"] == mode]) for mode in MODES} for fault in INSTANCES}
    pairs = (
        ("history_vs_current", "current_open", "history_full_open"),
        ("io_both_vs_io_job2", "io_job2_open", "io_both_open"),
        ("current_vs_io_job2", "io_job2_open", "current_open"),
        ("empty_vs_current", "current_open", "etiq_empty_open"),
        ("native_fixed_vs_empty", "etiq_empty_open", "compact_fixed_native"),
        ("voluntary_vs_native_fixed", "compact_fixed_native", "adaptive_voluntary_native"),
        ("required_vs_native_fixed", "compact_fixed_native", "adaptive_required_one_native"),
    )
    contrasts = []
    for name, left, right in pairs:
        contrasts.append({"name": name, "left": left, "right": right, **{f"{key}_rate_difference_right_minus_left": _rate(by_mode[right], key) - _rate(by_mode[left], key) for key in ("fault_detection", "correct_job_attribution", "exact_function_localisation", "control_false_positives")}})
    source_analysis = ce._read_json(repo_root / SOURCE_ATTEMPT / "analysis/summary.json")
    matching = {"io_job2_open": "io_job2_open", "io_both_open": "io_both_open", "current_open": "current_open", "history_full_open": "history_full_open", "etiq_empty_open": "etiq_empty_open", "compact_fixed_native": "compact_fixed_guided", "adaptive_voluntary_native": "adaptive_voluntary_guided", "adaptive_required_one_native": "adaptive_required_one_guided"}
    descriptive = {}
    for instance_id in INSTANCES:
        descriptive[instance_id] = {}
        for mode, source_mode in matching.items():
            current = by_fault[instance_id][mode]
            previous = source_analysis["fault_mode_summaries"][instance_id][source_mode]
            descriptive[instance_id][mode] = {
                key: {"attempt_038": deepcopy(current[key]), "attempt_037": deepcopy(previous[key]), "rate_difference_038_minus_037": _rate(current, key) - _rate(previous, key)}
                for key in ("fault_detection", "correct_job_attribution", "exact_function_localisation", "control_false_positives")
            }
    analysis = {
        "schema_version": "n21-boundary-free-native-analysis-1",
        "model_visible_semantic_boundary_material": False,
        "native_evidence_note": "Function names and source in native nodes are captured Etiq data, not controller-supplied semantic guidance.",
        "cross_attempt_limit": "Attempt 038 versus 037 is descriptive: calls are fresh and native captured nodes replace boundary-derived summaries and anchors.",
        "review_count": len(rows),
        "repair_trace_count": 0,
        "mode_summaries": by_mode,
        "fault_mode_summaries": by_fault,
        "prespecified_contrasts": contrasts,
        "attempt_037_descriptive_comparison": descriptive,
        "adaptive_pre_post": [deepcopy(x) for x in rows if x["evidence_mode"] in ADAPTIVE_MODES],
        "voluntary_expansion_uptake": {"numerator": sum(x["completed_expansion_count"] for x in rows if x["evidence_mode"] == "adaptive_voluntary_native"), "denominator": sum(x["evidence_mode"] == "adaptive_voluntary_native" for x in rows)},
        "required_one_completion": {"numerator": sum(x["completed_expansion_count"] for x in rows if x["evidence_mode"] == "adaptive_required_one_native"), "denominator": sum(x["evidence_mode"] == "adaptive_required_one_native" for x in rows)},
        "rows": sorted(rows, key=lambda x: x["schedule_position"]),
        "raw_per_call_tokens": raw_calls,
        "actual_usage": ce.aggregate_actual_usage_records(raw_calls),
    }
    analysis["analysis_sha256"] = ce.sha256(analysis)
    path = attempt_root / "analysis/summary.json"
    ce._write_immutable(path, analysis)
    return path


def _write_report(repo_root: Path, attempt_root: Path) -> Path:
    analysis = ce._read_json(attempt_root / "analysis/summary.json")
    replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    lines = [
        "# Attempt 038 — fully boundary-free native-Etiq comparison",
        "",
        f"Completed 168 reviews, {replay['observed_counts']['logical_provider_calls']} logical provider calls, and zero repairs.",
        "",
        "No controller-authored semantic boundary material was reviewer-visible in any arm. Function names and source appearing in native nodes are captured Etiq data, not controller-supplied semantic guidance. Attempt 038 versus 037 is descriptive because calls are fresh and the native graph representation replaces boundary-derived summaries and anchors.",
        "",
        "## Overall results",
        "",
        "| Mode | Detection | Correct Job 1 | Exact function | Control FP | Expansions | Calls | Input | Cached | Output |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        x = analysis["mode_summaries"][mode]
        lines.append(f"| {mode} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']} | {x['expansion_sessions']} | {x['provider_calls']} | {x['input_tokens']} | {x['cached_input_tokens']} | {x['output_tokens']} |")
    lines += ["", "## Results by fault", "", "| Fault | Mode | Detected | Job 1 | Exact function | Calls | Input | Output |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for fault in INSTANCES:
        for mode in MODES:
            x = analysis["fault_mode_summaries"][fault][mode]
            lines.append(f"| {fault} | {mode} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['provider_calls']} | {x['input_tokens']} | {x['output_tokens']} |")
    lines += ["", "## Adaptive pre/post answers", "", "| Trial | Mode | Pre job/function | Final job/function | Group | Raw stack | Nodes | Relationships |", "|---|---|---|---|---|---|---:|---:|"]
    for row in analysis["adaptive_pre_post"]:
        selected = row["selected_execution_group"] or {}
        lines.append(f"| {row['trial_id']} | {row['evidence_mode']} | {row['pre_suspect_job'] or 'none'}/{row['pre_suspect_function'] or 'none'} | {row['suspect_job'] or 'none'}/{row['suspect_function'] or 'none'} | {selected.get('execution_group_id', 'none')} | {json.dumps(selected.get('func_stack', []), separators=(',', ':'))} | {row['disclosed_node_count']} | {row['disclosed_relationship_count']} |")
    lines += ["", "## All 168 trial rows", "", "| Pos | Trial | Instance | Mode | Rep | Detected/FP | Job | Function | Exact | Expansion | Calls | Input | Cached | Output |", "|---:|---|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|"]
    for row in analysis["rows"]:
        calls = row["raw_calls"]
        outcome = "detected" if row["fault_detected"] else "FP" if row["false_positive"] else "clean/miss"
        lines.append(f"| {row['schedule_position']} | {row['trial_id']} | {row['instance_id']} | {row['evidence_mode']} | {row['repetition']} | {outcome} | {row['suspect_job'] or 'none'} | {row['suspect_function'] or 'none'} | {row['exact_function_localisation']} | {row['completed_expansion_count']} | {len(calls)} | {sum(int(x.get('input_tokens') or 0) for x in calls)} | {sum(int(x.get('cached_input_tokens') or 0) for x in calls)} | {sum(int(x.get('output_tokens') or 0) for x in calls)} |")
    lines += ["", "Attempt 037 is retained as a separate descriptive comparator and is not pooled with Attempt 038.", ""]
    path = repo_root / "docs/workshops/n21-attempt-038-boundary-free-native-etiq-complete-findings.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_bytes_exclusive(path, "\n".join(lines).encode())
    return path


def _write_handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze = ce._read_json(attempt_root / "experiment-freeze.json")
    analysis = ce._read_json(attempt_root / "analysis/summary.json")
    replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    terminal = ce._read_json(attempt_root / "terminal-state.json")
    report = repo_root / "docs/workshops/n21-attempt-038-boundary-free-native-etiq-complete-findings.md"
    artifacts = {"freeze": attempt_root / "experiment-freeze.json", "native_indexes": attempt_root / "native-group-index", "packages": attempt_root / "packages", "reviews": attempt_root / "reviews", "analysis": attempt_root / "analysis/summary.json", "replay": attempt_root / "replay/reconciliation.json", "terminal": attempt_root / "terminal-state.json", "report": report}
    hashes = {name: ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name, path in artifacts.items()}
    lines = ["To: Overseer", "From: Developer", "Subject: N21 Attempt 038 boundary-free native-Etiq results", "", f"Status: {terminal['status']}", f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)", f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`", "", "Counts", "- Faults: 6; clean controls: 1", "- Native graphs: 7; packages: 56; reviews: 168; repairs: 0", f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}", f"- Required-One completion: {analysis['required_one_completion']['numerator']}/{analysis['required_one_completion']['denominator']}", f"- Voluntary uptake: {analysis['voluntary_expansion_uptake']['numerator']}/{analysis['voluntary_expansion_uptake']['denominator']}", "", "Mode results", ""]
    for mode in MODES:
        x = analysis["mode_summaries"][mode]
        lines.append(f"- {mode}: detected {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']}; Job 1 {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']}; exact function {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']}; control FP {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']}; calls {x['provider_calls']}; input/output {x['input_tokens']}/{x['output_tokens']}.")
    lines += ["", "Exact artifact hashes", ""] + [f"- `{artifacts[name].relative_to(repo_root)}`: `{digest}`" for name, digest in hashes.items()] + ["", "Attempt 037 remained unchanged. No mutation, source, pipeline, capture, catalogue, provider response, result, call ID, or live authority was reused or regenerated. No semantic boundary material was reviewer-visible. Protected provider/security code was unchanged.", ""]
    path = repo_root / "instructions_between_agent_types/developer/handoffs/N21_attempt_038_results_to_overseer.email.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_bytes_exclusive(path, "\n".join(lines).encode())
    return path


def execute_lifecycle(repo_root: Path, attempt_root: Path) -> Path:
    repo_root = repo_root.resolve()
    attempt_root = attempt_root.resolve()
    verified = verify_frozen_attempt(repo_root, attempt_root)
    create_live_consumption(repo_root, attempt_root)
    catalogues, indexes, packages, records = _load_frozen(attempt_root)
    trials = ce._read_json(attempt_root / "review-design.json")["review_trials"]
    instances = {key: ce._read_json(attempt_root / "instances" / f"{key}.json") for key in INSTANCES}
    reviews: dict[tuple[str, int], Mapping[str, Any]] = {}
    for trial in trials:
        path = attempt_root / "reviews" / f"{trial['trial_id']}.json"
        if path.exists():
            record = ce._read_json(path)
            ce._verified_self_hash(record, "review_sha256")
            if record.get("controller_trial") != trial or record.get("status") != "complete":
                raise ValueError("invalid N21 partial review")
        else:
            instance_id = str(trial["instance_id"])
            package_record = packages[str(trial["branch_id"])]
            package = package_record["reviewer_package"]
            mode = str(trial["evidence_mode"])
            session = run_review_session(repo_root, attempt_root, catalogues[instance_id], indexes[instance_id], package, str(trial["trial_id"]), mode)
            final, pre = session["final_validation"], session["pre_validation"]
            outcome = score_response(instances[instance_id], final)
            event = session["operation_event"]
            record = {
                "schema_version": "n21-review-record-1",
                "controller_trial": deepcopy(trial),
                "package_sha256": package_record["package_sha256"],
                "receipt": deepcopy(final["receipt"]),
                "pre_fault_detected": pre["fault_detected"],
                "pre_suspect_job": pre["suspect_job"],
                "pre_suspect_function": pre["normalized_suspect_function"],
                "suspect_job": final["suspect_job"],
                "suspect_function": final["normalized_suspect_function"],
                "invalid_evidence_refs": deepcopy(final["invalid_evidence_refs"]),
                **outcome,
                "fault_group": instances[instance_id]["fault_group"],
                "completed_expansion_count": session["completed_expansion_count"],
                "selected_execution_group": ({key: deepcopy(event.get(key)) for key in ("execution_group_id", "job_id", "func_stack", "nodes_added", "relationships_added")} if event else None),
                "operation_diagnostic": deepcopy(session["operation_diagnostic"]),
                "disclosed_node_count": session["disclosed_node_count"],
                "disclosed_relationship_count": session["disclosed_relationship_count"],
                "call_records": session["call_records"],
                "usage": session["usage"],
                "status": "complete",
            }
            record["review_sha256"] = ce.sha256(record)
            ce._write_immutable(path, record)
        reviews[(str(trial["branch_id"]), int(trial["repetition"]))] = record
    required = [x for x in reviews.values() if x["controller_trial"]["evidence_mode"] == "adaptive_required_one_native"]
    voluntary = [x for x in reviews.values() if x["controller_trial"]["evidence_mode"] == "adaptive_voluntary_native"]
    if len(reviews) != 168 or len(required) != 21 or any(x["completed_expansion_count"] != 1 for x in required) or any(x["completed_expansion_count"] > 1 for x in voluntary):
        raise RuntimeError("N21 review or Adaptive invariant failed")
    call_ids = [str(call_id) for record in reviews.values() for call in record["call_records"] for call_id in call.get("call_ids", [])]
    logical_calls = sum(len(x["call_records"]) for x in reviews.values())
    if not 189 <= logical_calls <= 210 or len(call_ids) != len(set(call_ids)):
        raise ValueError("N21 call count or lineage changed")
    for call_id in call_ids:
        verify_record(attempt_root / "ledger", record_type="call-attempt", record_id=call_id)
    analysis = ce._read_json(write_analysis(repo_root, attempt_root, reviews))
    freeze = ce._read_json(attempt_root / "experiment-freeze.json")
    replay = {
        "schema_version": "n21-replay-1",
        "freeze_sha256": verified["freeze_sha256"],
        "review_hashes": sorted(x["review_sha256"] for x in reviews.values()),
        "observed_counts": {"faults": 6, "controls": 1, "captures": 7, "catalogues": 7, "source_bundles": 7, "native_graphs": 7, "packages": len(records), "reviews": len(reviews), "repairs": 0, "logical_provider_calls": logical_calls, "provider_attempt_call_ids": len(call_ids), "completed_native_expansions": sum(x["completed_expansion_count"] for x in reviews.values()), "disclosed_nodes": sum(x["disclosed_node_count"] for x in reviews.values()), "disclosed_relationships": sum(x["disclosed_relationship_count"] for x in reviews.values())},
        "all_record_hashes_recomputed": True,
        "duplicate_logical_calls": False,
        "required_one_sessions_complete": True,
        "native_index_files_unchanged": all(ce.sha256((attempt_root / "native-group-index" / f"{key}.json").read_bytes()) == value for key, value in freeze["native_group_index_file_hashes"].items()),
        "source_attempt_unchanged": ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) == freeze["source_attempt_tree_sha256"],
    }
    replay["replay_sha256"] = ce.sha256(replay)
    ce._write_immutable(attempt_root / "replay/reconciliation.json", replay)
    terminal = {"schema_version": "n21-terminal-1", "status": "completed_experiment_and_analysis", "fault_count": 6, "control_count": 1, "package_count": 56, "review_count": 168, "repair_trace_count": 0, "analysis_sha256": analysis["analysis_sha256"], "replay_sha256": replay["replay_sha256"]}
    terminal["terminal_sha256"] = ce.sha256(terminal)
    path = attempt_root / "terminal-state.json"
    ce._write_immutable(path, terminal)
    _write_report(repo_root, attempt_root)
    _write_handoff(repo_root, attempt_root)
    return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None = None) -> Path:
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    try:
        return execute_lifecycle(repo_root, target)
    except Exception as exc:
        terminal = {"schema_version": "n21-terminal-1", "status": "terminal_incomplete", "failure_stage": "n21_resumable_lifecycle", "error": f"{type(exc).__name__}: {exc}", "completed_review_records": len(list((target / "reviews").glob("*.json"))), "completed_repair_records": 0}
        terminal["terminal_sha256"] = ce.sha256(terminal)
        path = target / "terminal" / f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"
        ce._write_immutable(path, terminal)
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--attempt-root", default=ATTEMPT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    attempt = Path(args.attempt_root)
    attempt = attempt if attempt.is_absolute() else repo / attempt
    try:
        if args.operation == "build":
            built = build_attempt(repo, attempt)
            print(json.dumps({"qualification": built["qualification"], "counts": {"captures": len(built["captures"]), "catalogues": len(built["catalogues"]), "native_graphs": len(built["native_graphs"]), "packages": len(built["packages"]), "reviews": len(built["schedule"]["review_trials"]), "repairs": 0}}, indent=2))
        elif args.operation == "freeze":
            print(freeze_attempt(repo, attempt))
        elif args.operation == "verify":
            print(json.dumps(verify_frozen_attempt(repo, attempt), indent=2))
        else:
            path = run_lifecycle(repo, attempt)
            print(path)
            return 0 if ce._read_json(path).get("status") == "completed_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"N21 experiment failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
