"""Import native ETIQ lineage and compose it with an AppWorld execution graph.

AppWorld execution graphs remain authoritative and are never converted to ETIQ.
The composite is a separate evidence condition built from two independently
observed layers.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from rdr.packager import check_leakage
from rdr.v2_packager import PackageV2, _initial_sections, package_metadata
from rdr.v2_schema import TraceV2


ETIQ_CONDITIONS = ("ETIQ_CODE_LINEAGE", "APPWORLD_ETIQ_COMPOSITE")
STATE_GRAPH_CONDITIONS = ("STATE_APPWORLD_GRAPH", "STATE_ETIQ_GRAPH")
ALL_ETIQ_CONDITIONS = ETIQ_CONDITIONS + STATE_GRAPH_CONDITIONS
SENSITIVE_NAME = re.compile(
    r"token|key|secret|password|credential|authorization|cookie", re.IGNORECASE
)
PRIVATE_EVIDENCE_TERMS = (
    "replay_bundle", "expected_transcript", "expected_actions", "qualification",
    "fault_plan", "gold", "scoring_label", "validation_outcome", "bundle_sha256",
)
PRIMITIVE_CAPTURE_TARGETS = {
    "builtins.bool", "builtins.bytes", "builtins.dict", "builtins.float",
    "builtins.int", "builtins.list", "builtins.set", "builtins.str", "builtins.tuple",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _manifest(value: dict[str, Any], builder: str) -> dict[str, Any]:
    payload = {key: item for key, item in value.items() if key != "manifest"}
    return {
        "builder": builder,
        "content_sha256": _canonical_hash(payload),
        "node_count": len(value.get("nodes", [])),
        "edge_count": len(value.get("edges", [])),
    }


def _write_json_create_only(path: Path, value: Any) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_etiq_unavailable(output_path: Path) -> dict:
    payload = {
        "schema_version": "2.3.0",
        "graph_kind": "etiq_native",
        "private": True,
        "status": "unavailable",
        "producer": None,
        "native_export": None,
        "reason": (
            "No eligible workflow with genuinely observed ETIQ lineage was imported; "
            "AppWorld execution graphs are intentionally not converted."
        ),
    }
    payload["manifest"] = _manifest(
        payload, "rdr.v2_etiq_export.record_etiq_unavailable@2.3.0"
    )
    _write_json_create_only(output_path, payload)
    return payload


def export_etiq_native(execution_path: Path, output_path: Path) -> dict:
    del execution_path, output_path
    raise ValueError(
        "AppWorld-to-ETIQ conversion is forbidden; import genuinely native ETIQ lineage or record it unavailable"
    )


def _capture_targets(scan_dir: Path) -> set[str]:
    config = (
        scan_dir.parent / f".{scan_dir.name}-isolation/data/etiq_copilot/capture_targets.yml"
    )
    if not config.is_file():
        candidates = list(scan_dir.parent.glob("**/etiq_copilot/capture_targets.yml"))
        if len(candidates) != 1:
            raise ValueError("native ETIQ scan has no unique isolated capture-target configuration")
        config = candidates[0]
    return {
        line.split(":", 1)[0].strip()
        for line in config.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "!")) and ":" in line
    }


def _lineage_feature_counts(nodes: list[dict[str, Any]]) -> dict[str, int]:
    intermediate_names = {"payload", "receipt_path", "matching_users", "result", "request_id"}
    return {
        "workflow_assignments": sum(node.get("kind") == "etiq_state" for node in nodes),
        "parsing_operations": sum("json.loads" in node.get("label", "") for node in nodes),
        "guard_outcomes": sum(
            (node.get("kind") == "etiq_operation" and " if " in node.get("label", ""))
            or "(payload, None)" in node.get("label", "")
            or "reason" in node.get("state_names", [])
            for node in nodes
        ),
        "intermediate_values": sum(
            bool(intermediate_names & set(node.get("state_names", []))) for node in nodes
        ),
    }


def _normalise_etiq_text(value: str) -> str:
    return re.sub(r"`+$", "", value)


def _normalise_public_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalise_etiq_text(value)
    if isinstance(value, list):
        return [_normalise_public_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalise_public_value(item) for key, item in sorted(value.items())}
    return value


def _argument_bundle_names(node: dict[str, Any]) -> set[str]:
    """Return names encoded by ETIQ's unlabeled function-argument bundle nodes."""
    if node.get("kind") != "etiq_operation":
        return set()
    parts = [part.strip() for part in node.get("label", "").split(",")]
    return set(parts) if len(parts) > 1 and all(part.isidentifier() for part in parts) else set()


def _canonical_lineage(
    raw_nodes: dict[str, dict[str, Any]], projection_edges: list[dict[str, Any]],
) -> tuple[dict[str, str], list[tuple[str, str]], list[dict[str, Any]], dict[str, str]]:
    """Canonically label attributed lineage without consulting native traversal order.

    ETIQ function-call nodes encode the complete argument bundle in their label but emit one
    unlabeled incoming edge from an arbitrary bundle member. Those occurrences are retained as
    unattributed argument-binding evidence instead of guessing which state was intended.
    """
    descriptors = {native_id: _canonical_hash(public) for native_id, public in raw_nodes.items()}
    stable_edges: list[tuple[str, str]] = []
    unattributed_targets: list[str] = []
    for edge in projection_edges:
        source, target = edge["source"], edge["target"]
        if source not in raw_nodes or target not in raw_nodes:
            continue
        bundle_names = _argument_bundle_names(raw_nodes[target])
        source_names = set(raw_nodes[source].get("state_names", []))
        if bundle_names and source_names & bundle_names:
            unattributed_targets.append(target)
        else:
            stable_edges.append((source, target))

    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for source, target in stable_edges:
        outgoing[source].append(target)
        incoming[target].append(source)

    # Partition refinement uses canonical integer ranks and runs to convergence. Unlike repeated
    # hashing with a fixed round count, the result depends only on semantic attributes and directed
    # neighbour roles, never native names or parser order.
    colors = descriptors.copy()
    for _ in range(max(1, len(raw_nodes))):
        keys = {
            native_id: (
                descriptors[native_id],
                tuple(sorted(colors[item] for item in incoming[native_id])),
                tuple(sorted(colors[item] for item in outgoing[native_id])),
            )
            for native_id in raw_nodes
        }
        unique = {key: f"{index:08d}" for index, key in enumerate(sorted(set(keys.values())))}
        refined = {native_id: unique[key] for native_id, key in keys.items()}
        old_groups = sorted(sorted(group) for group in _partition_groups(colors).values())
        new_groups = sorted(sorted(group) for group in _partition_groups(refined).values())
        colors = refined
        if old_groups == new_groups:
            break

    # Convert ranks to content hashes so identifiers remain stable if unrelated rank classes are
    # added. Equal final colors are automorphic for the emitted DAG; assigning their occurrence
    # indices is representation-invariant because their public attributes and incident color roles
    # are identical.
    structural = {
        native_id: _canonical_hash({
            "semantic": descriptors[native_id],
            "in": sorted(colors[item] for item in incoming[native_id]),
            "out": sorted(colors[item] for item in outgoing[native_id]),
        })
        for native_id in raw_nodes
    }
    undirected: dict[str, set[str]] = defaultdict(set)
    for source, target in stable_edges:
        undirected[source].add(target)
        undirected[target].add(source)
    components: list[tuple[str, list[str], dict[str, int]]] = []
    unseen = set(raw_nodes)
    while unseen:
        start = next(iter(unseen))
        stack, component = [start], []
        unseen.remove(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in undirected[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        ordered = sorted(component, key=lambda item: (structural[item], descriptors[item]))
        local = {native_id: index for index, native_id in enumerate(ordered)}
        payload = {
            "nodes": [descriptors[native_id] for native_id in ordered],
            "edges": sorted(
                (local[source], local[target]) for source, target in stable_edges
                if source in local and target in local
            ),
        }
        components.append((_canonical_hash(payload), ordered, local))

    # Equal component hashes have identical canonical payloads. Their occurrence order can be
    # exchanged without changing the emitted node rows or edge set.
    component_indices: Counter[str] = Counter()
    node_ids: dict[str, str] = {}
    for component_hash, ordered, local in sorted(components, key=lambda item: item[0]):
        component_index = component_indices[component_hash]
        component_indices[component_hash] += 1
        for native_id in ordered:
            node_ids[native_id] = (
                f"node:{component_hash[:12]}:{component_index:05d}:{local[native_id]:05d}"
            )

    unattributed_counts = Counter(descriptors[target] for target in unattributed_targets)
    unattributed = [
        {
            "role": "function_argument_binding",
            "operation_semantic_sha256": descriptor,
            "occurrence_index": index,
            "multiplicity": 1,
        }
        for descriptor, count in sorted(unattributed_counts.items())
        for index in range(count)
    ]
    return node_ids, stable_edges, unattributed, descriptors


def _partition_groups(colors: dict[str, str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for native_id, color in colors.items():
        groups[color].append(native_id)
    return groups


def _scan_inputs(scan_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], set[str]]:
    result_path = scan_dir / "scan-result.json"
    projection_path = scan_dir / "workflow-lineage-projection.json"
    inventory_path = scan_dir / "state-inventory.json"
    if not all(path.is_file() for path in (result_path, projection_path, inventory_path)):
        raise ValueError("native ETIQ scan is missing result, workflow projection, or state inventory")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if result.get("capture_status") != "completed_with_states":
        raise ValueError("native ETIQ capture did not complete with states")
    if result.get("native_export_status") not in {"dot", "json"}:
        raise ValueError("native ETIQ export is unavailable")
    if result.get("projection_status") != "completed":
        raise ValueError("native ETIQ workflow projection did not complete")
    if result.get("replay_fidelity", {}).get("passed") is not True:
        raise ValueError("native ETIQ replay did not match the frozen trace")
    targets = _capture_targets(scan_dir)
    primitives = sorted(targets & PRIMITIVE_CAPTURE_TARGETS)
    if primitives:
        raise ValueError(f"primitive ETIQ capture targets are forbidden: {primitives}")
    if targets != {"fixtures.v2.etiq_replay_entry.ReplayApiCollection"}:
        raise ValueError("ReplayApiCollection must be the only ETIQ capture target")
    isolation = result.get("isolation", {})
    if (isolation.get("environment") != "allowlist"
            or isolation.get("network") != "python_socket_denial"
            or isolation.get("network_probe_passed") is not True):
        raise ValueError("native ETIQ capture was not produced in the required isolated configuration")
    return result, projection, inventory, targets


def _project_native_etiq(scan_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a deterministic public graph and retain native provenance privately."""
    result, projection, inventory, targets = _scan_inputs(scan_dir)

    states = {state["id"]: state for state in inventory["states"]}
    raw_nodes: dict[str, dict[str, Any]] = {}
    excluded = set()
    for node in projection["nodes"]:
        state = states.get(node.get("state_id"))
        names = [] if state is None else sorted(
            name for name in state.get("names", [])
            if name not in {"apis", "self", "__etiq_replay_apis__"}
            and not name.startswith("__etiq_")
        )
        if any(SENSITIVE_NAME.search(name) for name in names):
            excluded.add(node["id"])
            continue
        public = {
            "kind": "etiq_state" if state else "etiq_operation",
            "label": _normalise_etiq_text(node.get("label", "")),
            "clusters": sorted({_normalise_etiq_text(item) for item in node.get("clusters", [])}),
            "origin": {
                "classification": node["origin"]["classification"],
                "path": Path(node["origin"].get("path") or "workflow.py").name,
                "source_sha256": node["origin"].get("source_sha256"),
            },
        }
        if state:
            public.update({
                "state_sha256": state["value_sha256"],
                "state_names": names,
                "source_line": state.get("source_line"),
                "structure": _normalise_public_value(state.get("structure", {})),
            })
        if not names and state and public["structure"].get("python_type") == "ReplayApiCollection":
            excluded.add(node["id"])
            continue
        raw_nodes[node["id"]] = public
    node_ids, stable_edges, unattributed_edges, descriptors = _canonical_lineage(
        raw_nodes, projection["edges"]
    )
    descriptor_counts = Counter(descriptors.values())
    nodes = []
    occurrence_indices: Counter[str] = Counter()
    for native_id in sorted(raw_nodes, key=lambda item: node_ids[item]):
        descriptor = descriptors[native_id]
        public_id = node_ids[native_id]
        occurrence_index = occurrence_indices[descriptor]
        occurrence_indices[descriptor] += 1
        nodes.append({
            **raw_nodes[native_id],
            "id": public_id,
            "occurrence_index": occurrence_index,
            "equivalent_occurrence_count": descriptor_counts[descriptor],
            "multiplicity": 1,
        })
    nodes.sort(key=lambda item: item["id"])

    edge_indices: Counter[tuple[str, str]] = Counter()
    edges = []
    for native_source, native_target in stable_edges:
        source = node_ids[native_source]
        target = node_ids[native_target]
        pair = (source, target)
        occurrence_index = edge_indices[pair]
        edge_indices[pair] += 1
        edges.append({
            "src": source,
            "kind": "etiq_lineage",
            "dst": target,
            "occurrence_index": occurrence_index,
            "multiplicity": 1,
        })
    edges.sort(key=lambda item: (item["src"], item["kind"], item["dst"], item["occurrence_index"]))
    if not any(node["kind"] == "etiq_state" for node in nodes) or not edges:
        raise ValueError("native ETIQ workflow lineage has no public states or edges")
    features = _lineage_feature_counts(nodes)
    if not all(features.values()):
        raise ValueError(f"native ETIQ lineage is missing required workflow features: {features}")
    graph = {
        "schema_version": "2.3.0",
        "graph_kind": "etiq_native",
        "private": False,
        "status": "available",
        "producer": "etiq-copilot==2.3.2",
        "source_sha256": result["scan_source"]["sha256"],
        "native_export": {
            "format": result["native_export_status"],
            "excluded_sensitive_state_count": len(excluded),
            "capture_targets_sha256": _canonical_hash(sorted(targets)),
            "canonicalisation": "occurrence-preserving-order-independent-v3",
            "unattributed_edge_occurrences": unattributed_edges,
        },
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "states": sum(node["kind"] == "etiq_state" for node in nodes),
            "operations": sum(node["kind"] == "etiq_operation" for node in nodes),
            "edges": len(edges),
            "state_instances": sum(node["kind"] == "etiq_state" for node in nodes),
            "operation_instances": sum(node["kind"] == "etiq_operation" for node in nodes),
            "edge_instances": len(edges) + len(unattributed_edges),
            "unattributed_edge_instances": len(unattributed_edges),
            **features,
        },
    }
    encoded = _canonical_json(graph).lower()
    leaks = [term for term in PRIVATE_EVIDENCE_TERMS if term in encoded]
    if leaks:
        raise ValueError(f"native ETIQ public projection leaks private evidence: {leaks}")
    graph["manifest"] = _manifest(graph, "rdr.v2_etiq_export.import_native_etiq@2.3.1")
    private = {
        "scan_dir": str(scan_dir),
        "native_sha256": result["native_graph"]["sha256"],
        "occurrence_aware": (
            all("occurrence_ordinal" in node for node in projection["nodes"])
            and all("occurrence_ordinal" in edge for edge in projection["edges"])
        ),
        "projection_sha256": hashlib.sha256(
            (scan_dir / "workflow-lineage-projection.json").read_bytes()
        ).hexdigest(),
        "public_graph_sha256": _canonical_hash(graph),
    }
    return graph, private


def qualify_etiq_repeatability(first_scan: Path, second_scan: Path) -> dict[str, Any]:
    """Fail closed unless two isolated captures yield the same public graph."""
    first, first_private = _project_native_etiq(first_scan)
    second, second_private = _project_native_etiq(second_scan)
    occurrence_aware = first_private["occurrence_aware"] and second_private["occurrence_aware"]
    graph_identical = occurrence_aware and _canonical_json(first) == _canonical_json(second)
    result = {
        "schema_version": "1.0",
        "private": True,
        "deterministic_repeatability": graph_identical,
        "public_graph_sha256": (
            first["manifest"]["content_sha256"] if graph_identical else None
        ),
        "captures": [first_private, second_private],
        "workflow_only_eligibility": {
            "status": "eligible" if graph_identical else "blocked",
            "public_projection": True,
            "replay_fidelity": True,
            "isolated_capture_configuration": True,
            "private_data_leakage": False,
            "fault_to_action_complete": False,
            "claim": "workflow code-lineage evidence only",
        },
        "composite_eligibility": {"status": "not_assessed"},
    }
    if not graph_identical:
        result["reason"] = (
            "capture lacks occurrence-level projection metadata" if not occurrence_aware else
            "canonical public ETIQ graphs differ across identical captures"
        )
    return result


def import_native_etiq(scan_dir: Path, eligibility: dict[str, Any]) -> dict[str, Any]:
    """Import lineage only after explicit workflow evidence eligibility passes."""
    workflow = eligibility.get("workflow_only_eligibility", {})
    if (workflow.get("status") != "eligible"
            or eligibility.get("deterministic_repeatability") is not True):
        raise ValueError("native ETIQ workflow-only eligibility did not pass")
    graph, _ = _project_native_etiq(scan_dir)
    if graph["manifest"]["content_sha256"] != eligibility.get("public_graph_sha256"):
        raise ValueError("native ETIQ graph differs from the repeatability-qualified projection")
    return graph


def _public_appworld_node(node: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in node.items() if key != "value"}
    if "value" in node:
        public["value_sha256"] = _canonical_hash(node["value"])
        public["value_type"] = type(node["value"]).__name__
    public["id"] = "aw:" + node["id"]
    public["provenance_layer"] = "appworld"
    return public


def _argument_candidates(value: Any, path: str = "$") -> list[tuple[str, str, str]]:
    """Return (path, match kind, hash) without retaining argument values."""
    candidates = [(path, "exact", _canonical_hash(value))]
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            if not SENSITIVE_NAME.search(str(key)):
                candidates.extend(_argument_candidates(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            candidates.extend(_argument_candidates(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        for token in sorted(set(re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", value))):
            scalar: int | float = float(token) if "." in token else int(token)
            candidates.append((path, "formatted_scalar", _canonical_hash(scalar)))
    return candidates


def _reachable(adjacency: dict[str, list[str]], start: str) -> set[str]:
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for target in adjacency.get(node, []):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _source_literal_hashes(trace: TraceV2) -> set[str]:
    hashes: set[str] = set()
    for source in trace.source.values():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
                hashes.add(_canonical_hash(node.value))
    return hashes


def _prompt_content_hashes(trace: TraceV2) -> set[str]:
    suspicious = re.compile(r"ignore\s+(?:all\s+)?previous|system prompt|follow these instructions", re.I)
    hashes: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str) and suspicious.search(value):
            hashes.add(_canonical_hash(value))
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for call in trace.calls:
        visit(call.observed_response)
    return hashes


def _effect_artifact(
    appworld_graph: dict[str, Any], call_index: int, app: str, api: str, state_hash: str,
) -> tuple[str | None, str]:
    nodes = {node["id"]: node for node in appworld_graph["nodes"]}
    targets = [
        nodes[edge["dst"]] for edge in appworld_graph["edges"]
        if edge["src"] == f"call:{call_index}" and edge["kind"] == "writes"
    ]
    if app == "file_system" and api == "create_file":
        targets = [node for node in targets if node.get("record", "").startswith("file_system.files#")]
        reason = "unique file record written by file_system.create_file"
    else:
        targets = [
            node for node in targets
            if any(candidate_hash == state_hash
                   for _, _, candidate_hash in _argument_candidates(node.get("value")))
        ]
        reason = "unique written artifact privately matched to the bridged argument"
    if len(targets) != 1:
        return None, f"expected one specific written artifact; found {len(targets)}"
    return "aw:" + targets[0]["id"], reason


def build_appworld_etiq_composite(
    appworld_graph: dict[str, Any], trace: TraceV2, etiq_graph: dict[str, Any],
    eligibility: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a namespaced two-layer graph and a private ambiguity report."""
    if appworld_graph.get("graph_kind") != "appworld_execution":
        raise ValueError("composite requires the frozen appworld_execution graph")
    if etiq_graph.get("graph_kind") != "etiq_native" or etiq_graph.get("status") != "available":
        raise ValueError("composite requires imported native ETIQ lineage")
    if appworld_graph.get("source_sha256") != etiq_graph.get("source_sha256"):
        raise ValueError("AppWorld and ETIQ layers do not bind the same frozen source")
    if len(trace.calls) != len(appworld_graph.get("calls", [])):
        raise ValueError("trace call count differs from frozen AppWorld graph")
    if eligibility.get("deterministic_repeatability") is not True:
        raise ValueError("composite requires a passed deterministic ETIQ repeatability gate")
    if eligibility.get("workflow_only_eligibility", {}).get("status") != "eligible":
        raise ValueError("composite requires an eligible ETIQ public lineage projection")

    aw_nodes = [_public_appworld_node(node) for node in appworld_graph["nodes"]]
    aw_edges = [
        {"src": "aw:" + edge["src"], "kind": edge["kind"], "dst": "aw:" + edge["dst"]}
        for edge in appworld_graph["edges"]
    ]
    etiq_nodes = [
        {**node, "id": "etiq:" + node["id"], "provenance_layer": "etiq"}
        for node in etiq_graph["nodes"]
    ]
    etiq_edges = [
        {"src": "etiq:" + edge["src"], "kind": edge["kind"], "dst": "etiq:" + edge["dst"]}
        for edge in etiq_graph["edges"]
    ]
    state_nodes: dict[str, list[str]] = defaultdict(list)
    for node in etiq_nodes:
        hashes = node.get("state_sha256s", [])
        if node.get("state_sha256"):
            hashes = [*hashes, node["state_sha256"]]
        for state_hash in hashes:
            state_nodes[state_hash].append(node["id"])
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in etiq_edges:
        adjacency[edge["src"]].append(edge["dst"])
    calls_by_index = {call.index: call for call in trace.calls}

    bridges = []
    ambiguities = []
    unlinked = []
    response_starts: list[tuple[int, str, set[str]]] = []
    for call in trace.calls:
        response_hash = _canonical_hash(call.observed_response)
        matches = sorted(state_nodes.get(response_hash, []))
        join = {
            "call_index": call.index,
            "app": call.app,
            "api": call.api,
            "argument_sha256": _canonical_hash(call.args),
            "response_sha256": response_hash,
            "etiq_state_sha256": response_hash,
        }
        if len(matches) == 1:
            join["provenance_category"] = "API-response-derived"
            bridges.append({
                "src": f"aw:response:observed:{call.index}",
                "kind": "bridge_response_to_code", "dst": matches[0], "join": join,
            })
            response_starts.append((call.index, matches[0], _reachable(adjacency, matches[0])))
        elif len(matches) > 1:
            ambiguities.append({"bridge": "response_to_code", **join, "candidate_count": len(matches)})
        else:
            unlinked.append({"bridge": "response_to_code", **join,
                             "reason": "no ETIQ state uniquely represents the complete API response"})

    literal_hashes = _source_literal_hashes(trace)
    task_hashes = {candidate_hash for _, _, candidate_hash in _argument_candidates(trace.instruction)}
    prompt_hashes = _prompt_content_hashes(trace)
    for call in trace.calls:
        args_hash = _canonical_hash(call.args)
        by_state: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for path, match_kind, value_hash in _argument_candidates(call.args):
            if value_hash in state_nodes:
                by_state[value_hash].append((path, match_kind))
        for state_hash, argument_matches in sorted(by_state.items()):
            upstream = [
                (index, node, reachable)
                for index, node, reachable in response_starts
                if index < call.index
            ]
            candidates = sorted({
                node
                for node in state_nodes[state_hash]
                if any(node in reachable for _, _, reachable in upstream)
            })
            join = {
                "call_index": call.index,
                "app": call.app,
                "api": call.api,
                "argument_sha256": args_hash,
                "response_sha256": _canonical_hash(call.observed_response),
                "argument_value_sha256": state_hash,
                "etiq_state_sha256": state_hash,
                "argument_paths": sorted({path for path, _ in argument_matches}),
                "match_kinds": sorted({kind for _, kind in argument_matches}),
            }
            sources_by_candidate = {
                candidate: sorted(
                    index for index, _, reachable in upstream if candidate in reachable
                )
                for candidate in candidates
            }
            if len(candidates) == 1 and len(sources_by_candidate[candidates[0]]) == 1:
                sources = sources_by_candidate[candidates[0]]
                join["upstream_response_call_indices"] = sources
                join["upstream_response_sha256"] = [
                    _canonical_hash(calls_by_index[index].observed_response) for index in sources
                ]
                artifact_id, artifact_reason = _effect_artifact(
                    appworld_graph, call.index, call.app, call.api, state_hash
                )
                if artifact_id:
                    join.update({
                        "provenance_category": "API-response-derived",
                        "effect_artifact_id": artifact_id,
                    })
                    bridges.append({
                        "src": candidates[0], "kind": "bridge_code_to_argument",
                        "dst": f"aw:call:{call.index}", "join": join,
                    })
                else:
                    unlinked.append({"bridge": "code_to_argument", **join,
                                     "provenance_category": "API-response-derived",
                                     "reason": artifact_reason})
            elif candidates:
                ambiguities.append({
                    "bridge": "code_to_argument", **join,
                    "candidate_count": len(candidates),
                    "unreachable_candidate_count": len(state_nodes[state_hash]) - len(candidates),
                    "candidate_upstream_response_call_indices": sources_by_candidate,
                    "reason": (
                        "candidate has multiple upstream response occurrences"
                        if len(candidates) == 1 else
                        "multiple occurrence-level ETIQ states match the argument"
                    ),
                })
            else:
                category = (
                    "prompt-content-derived" if state_hash in prompt_hashes else
                    "source-generated" if state_hash in literal_hashes else
                    "task-input-derived" if state_hash in task_hashes else None
                )
                unlinked.append({
                    "bridge": "code_to_argument", **join,
                    "candidate_count": 0,
                    "unreachable_candidate_count": len(state_nodes[state_hash]),
                    "provenance_category": category,
                    "reason": (
                        "value is source-generated and has no verified API-response provenance"
                        if category == "source-generated" else
                        "value is task-input-derived and has no verified API-response provenance"
                        if category == "task-input-derived" else
                        "value is prompt-content-derived but lacks a unique lineage path from the full response"
                        if category == "prompt-content-derived" else
                        "matching lineage states are not reachable from a uniquely verified earlier API response"
                    ),
                })

    graph = {
        "schema_version": "2.3.0",
        "graph_kind": "appworld_etiq_composite",
        "source_sha256": appworld_graph["source_sha256"],
        "layers": {
            "appworld": {
                "graph_kind": "appworld_execution",
                "content_sha256": appworld_graph["manifest"]["content_sha256"],
                "node_count": len(appworld_graph["nodes"]),
                "edge_count": len(appworld_graph["edges"]),
            },
            "etiq": {
                "graph_kind": "etiq_native",
                "content_sha256": etiq_graph["manifest"]["content_sha256"],
                "node_count": len(etiq_graph["nodes"]),
                "edge_count": len(etiq_graph["edges"]),
            },
        },
        "nodes": sorted(aw_nodes + etiq_nodes, key=lambda item: item["id"]),
        "edges": sorted(
            aw_edges + etiq_edges + bridges,
            key=lambda item: (item["src"], item["kind"], item["dst"]),
        ),
        "counts": {
            "appworld_nodes": len(aw_nodes), "appworld_edges": len(aw_edges),
            "etiq_nodes": len(etiq_nodes), "etiq_edges": len(etiq_edges),
            "bridge_response_to_code": sum(edge["kind"] == "bridge_response_to_code" for edge in bridges),
            "bridge_code_to_argument": sum(edge["kind"] == "bridge_code_to_argument" for edge in bridges),
        },
    }
    graph["manifest"] = _manifest(
        graph, "rdr.v2_etiq_export.build_appworld_etiq_composite@2.3.1"
    )
    report = {
        "private": True,
        "ambiguous_joins": ambiguities,
        "ambiguous_join_count": len(ambiguities),
        "unlinked_joins": unlinked,
        "unlinked_join_count": len(unlinked),
        "accepted_bridge_count": len(bridges),
    }
    validation = validate_composite(graph, appworld_graph, etiq_graph)
    report.update(validation)
    checks = {
        "replay_fidelity": eligibility["workflow_only_eligibility"]["replay_fidelity"],
        "deterministic_repeatability": eligibility["deterministic_repeatability"],
        "isolated_capture_configuration": eligibility["workflow_only_eligibility"][
            "isolated_capture_configuration"
        ],
        "public_projection": eligibility["workflow_only_eligibility"]["public_projection"],
        "unique_cross_layer_path": bool(validation["verified_effect_path"]),
        "private_data_leakage": not _public_evidence_check(_canonical_json(graph)),
    }
    report["composite_eligibility"] = {
        "status": "eligible" if all(checks.values()) else "blocked", "checks": checks,
    }
    return graph, report


def validate_composite(
    graph: dict[str, Any], appworld_graph: dict[str, Any], etiq_graph: dict[str, Any]
) -> dict[str, Any]:
    if graph.get("graph_kind") != "appworld_etiq_composite":
        raise ValueError("wrong composite graph kind")
    nodes = {node["id"]: node for node in graph["nodes"]}
    if not nodes or any(not node_id.startswith(("aw:", "etiq:")) for node_id in nodes):
        raise ValueError("composite nodes are not fully namespaced")
    expected_aw_nodes = {"aw:" + node["id"] for node in appworld_graph["nodes"]}
    expected_etiq_nodes = {"etiq:" + node["id"] for node in etiq_graph["nodes"]}
    actual_aw_nodes = {node_id for node_id in nodes if node_id.startswith("aw:")}
    actual_etiq_nodes = {node_id for node_id in nodes if node_id.startswith("etiq:")}
    if actual_aw_nodes != expected_aw_nodes or actual_etiq_nodes != expected_etiq_nodes:
        raise ValueError("composite changed an AppWorld or ETIQ node set")
    unresolved = {
        endpoint for edge in graph["edges"] for endpoint in (edge["src"], edge["dst"])
        if endpoint not in nodes
    }
    if unresolved:
        raise ValueError(f"composite has unresolved edge endpoints: {sorted(unresolved)[:5]}")
    expected_aw_edges = {
        ("aw:" + edge["src"], edge["kind"], "aw:" + edge["dst"])
        for edge in appworld_graph["edges"]
    }
    actual_aw_edges = {
        (edge["src"], edge["kind"], edge["dst"])
        for edge in graph["edges"]
        if edge["src"].startswith("aw:") and edge["dst"].startswith("aw:")
    }
    expected_etiq_edges = {
        ("etiq:" + edge["src"], edge["kind"], "etiq:" + edge["dst"])
        for edge in etiq_graph["edges"]
    }
    actual_etiq_edges = {
        (edge["src"], edge["kind"], edge["dst"])
        for edge in graph["edges"]
        if edge["src"].startswith("etiq:") and edge["dst"].startswith("etiq:")
    }
    if actual_aw_edges != expected_aw_edges or actual_etiq_edges != expected_etiq_edges:
        raise ValueError("composite changed an AppWorld or ETIQ provenance layer")

    response_calls = {
        edge["join"]["call_index"]
        for edge in graph["edges"]
        if edge["kind"] == "bridge_response_to_code"
    }
    for bridge in (edge for edge in graph["edges"]
                   if edge["kind"] == "bridge_code_to_argument"):
        join = bridge.get("join", {})
        upstream = join.get("upstream_response_call_indices", [])
        if len(upstream) != 1 or upstream[0] not in response_calls:
            raise ValueError("code-to-argument bridge does not have exactly one upstream response")
        effect = join.get("effect_artifact_id")
        effect_edges = [
            edge for edge in graph["edges"]
            if edge["src"] == bridge["dst"] and edge["kind"] == "writes"
            and edge["dst"] == effect
        ]
        if not effect or len(effect_edges) != 1:
            raise ValueError("code-to-argument bridge does not have exactly one effect artifact")

    adjacency: dict[str, list[tuple[str, str, dict[str, Any] | None]]] = defaultdict(list)
    for edge in graph["edges"]:
        adjacency[edge["src"]].append((edge["dst"], edge["kind"], edge.get("join")))
    verified = None
    starts = [edge for edge in graph["edges"] if edge["kind"] == "bridge_response_to_code"]
    for start in starts:
        queue = deque([(start["dst"], [start["src"], start["dst"]], [start["kind"]], None)])
        seen = {(start["dst"], None)}
        while queue:
            current, path, kinds, effect_artifact = queue.popleft()
            if (kinds[-2:] == ["bridge_code_to_argument", "writes"]
                    and "etiq_lineage" in kinds and current == effect_artifact):
                verified = {"nodes": path, "edge_kinds": kinds}
                break
            for target, kind, join in adjacency.get(current, []):
                next_effect = (
                    join.get("effect_artifact_id")
                    if kind == "bridge_code_to_argument" and join else effect_artifact
                )
                marker = (target, next_effect)
                if marker not in seen and (
                    kind == "etiq_lineage" or kind == "bridge_code_to_argument" or kind == "writes"
                ):
                    seen.add(marker)
                    queue.append((target, path + [target], kinds + [kind], next_effect))
        if verified:
            break
    if not verified:
        raise ValueError(
            "no response -> ETIQ transformation -> later argument -> AppWorld database effect path"
        )
    return {
        "appworld_layer_preserved": True,
        "etiq_layer_preserved": True,
        "verified_effect_path": verified,
    }


def _render_public_graph(graph: dict[str, Any]) -> str:
    lines = [f"PROVENANCE GRAPH kind={graph['graph_kind']}"]
    if graph.get("bounded_projection"):
        lines.append("BOUNDED PUBLIC PROJECTION " + _canonical_json(graph["bounded_projection"]))
    for edge in graph.get("native_export", {}).get("unattributed_edge_occurrences", []):
        lines.append("UNATTRIBUTED ETIQ EDGE " + _canonical_json(edge))
    for node in sorted(graph["nodes"], key=lambda item: item["id"]):
        visible_keys = (
            "kind", "label", "state_names", "source_line", "provenance_layer",
            "index", "api", "args", "record", "location", "identity",
            "nesting_depth", "sha256", "value_sha256", "value_type",
            "occurrence_index", "equivalent_occurrence_count", "multiplicity",
        )
        detail = {key: node[key] for key in visible_keys if key in node}
        lines.append(f"NODE {node['id']} {_canonical_json(detail)}")
    for edge in sorted(graph["edges"], key=lambda item: (item["src"], item["kind"], item["dst"])):
        edge_detail = {
            key: edge[key] for key in ("occurrence_index", "multiplicity", "join")
            if key in edge
        }
        suffix = "" if not edge_detail else " " + _canonical_json(edge_detail)
        lines.append(f"EDGE {edge['src']} -{edge['kind']}-> {edge['dst']}{suffix}")
    return "\n".join(lines)


def _regex_tokens(text: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))


def _verified_causal_nodes(composite: dict[str, Any]) -> set[str]:
    """Return every node on an accepted response-to-effect causal path."""
    etiq_adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in composite["edges"]:
        if edge["kind"] == "etiq_lineage":
            etiq_adjacency[edge["src"]].append(edge["dst"])
    responses = {
        edge["join"]["call_index"]: edge
        for edge in composite["edges"]
        if edge["kind"] == "bridge_response_to_code"
    }
    required: set[str] = set()
    for bridge in (edge for edge in composite["edges"]
                   if edge["kind"] == "bridge_code_to_argument"):
        upstream = bridge["join"].get("upstream_response_call_indices", [])
        if len(upstream) != 1 or upstream[0] not in responses:
            raise ValueError("accepted bridge lacks exactly one upstream response occurrence")
        response = responses[upstream[0]]
        queue = deque([(response["dst"], [response["dst"]])])
        seen = {response["dst"]}
        path = None
        while queue:
            current, current_path = queue.popleft()
            if current == bridge["src"]:
                path = current_path
                break
            for target in etiq_adjacency.get(current, []):
                if target not in seen:
                    seen.add(target)
                    queue.append((target, current_path + [target]))
        if path is None:
            raise ValueError("accepted bridge has no occurrence-level ETIQ lineage path")
        required.update((response["src"], bridge["dst"], bridge["join"]["effect_artifact_id"]))
        required.update(path)
    if not required:
        raise ValueError("no accepted causal path is available for bounded evidence")
    return required


def _bounded_graph_view(
    graph: dict[str, Any], token_budget: int, required_ids: set[str],
) -> dict[str, Any]:
    """Bound by complete causal paths plus whole local-neighbourhood layers."""
    nodes = {node["id"]: node for node in graph["nodes"]}
    selected = required_ids & nodes.keys()
    if not selected:
        raise ValueError("bounded graph has no required causal-path nodes")

    def view(node_ids: set[str]) -> dict[str, Any]:
        return {
            **graph,
            "nodes": [nodes[item] for item in sorted(node_ids)],
            "edges": [edge for edge in graph["edges"]
                      if edge["src"] in node_ids and edge["dst"] in node_ids],
        }

    if _regex_tokens(_render_public_graph(view(selected))) > token_budget:
        raise ValueError("complete verified causal paths exceed the package token budget")

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        adjacency[edge["src"]].add(edge["dst"])
        adjacency[edge["dst"]].add(edge["src"])
    frontier = set(selected)
    remaining = set(nodes) - selected
    while frontier:
        neighbourhood = {
            neighbour for node_id in frontier for neighbour in adjacency[node_id]
            if neighbour in remaining
        }
        if not neighbourhood:
            break
        trial_ids = selected | neighbourhood
        trial = {
            **view(trial_ids),
        }
        if _regex_tokens(_render_public_graph(trial)) > token_budget:
            break
        selected = trial_ids
        remaining -= neighbourhood
        frontier = neighbourhood
    bounded = view(selected)
    return {
        **bounded,
        "bounded_projection": {
            "full_node_count": len(graph["nodes"]), "shown_node_count": len(selected),
            "full_edge_count": len(graph["edges"]), "shown_edge_count": len(bounded["edges"]),
            "selection": "complete_verified_paths_plus_whole_neighbourhood_layers",
            "required_path_node_count": len(required_ids & nodes.keys()),
        },
    }


def _public_evidence_check(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(term for term in PRIVATE_EVIDENCE_TERMS if term in lowered)


def build_etiq_conditions(
    trace: TraceV2, symptom: str, etiq_graph: dict[str, Any], composite_graph: dict[str, Any],
    max_tokens: int | None = None,
) -> list[PackageV2]:
    """Build two additive conditions; never modifies the registered non-Etiq arms."""
    validate_composite(
        composite_graph,
        _extract_layer(composite_graph, "aw:"),
        _extract_layer(composite_graph, "etiq:"),
    )
    composite_required = _verified_causal_nodes(composite_graph)
    packages = []
    for condition, graph in zip(ETIQ_CONDITIONS, (etiq_graph, composite_graph), strict=True):
        sections = _initial_sections(condition, trace)
        common = "\n\n".join(sections.values())
        visible_graph = graph
        rendered = _render_public_graph(visible_graph)
        if max_tokens and _regex_tokens(common + "\n\n" + rendered) > max_tokens:
            required = (
                {item.removeprefix("etiq:") for item in composite_required
                 if item.startswith("etiq:")}
                if graph["graph_kind"] == "etiq_native" else composite_required
            )
            visible_graph = _bounded_graph_view(
                graph, max(1, max_tokens - _regex_tokens(common) - 2), required
            )
            rendered = _render_public_graph(visible_graph)
        sections["graph"] = rendered
        text = "\n\n".join(sections.values())
        check_leakage(text)
        leaks = _public_evidence_check(text)
        if leaks:
            raise ValueError(f"ETIQ reviewer condition leaks private evidence: {leaks}")
        metadata = package_metadata(text, sections, trace, visible_graph)
        metadata["experimental_condition"] = condition
        metadata["actual_reviewer_input_tokens"] = None
        metadata["size_covariate"] = "tokens"
        metadata["bounded_projection"] = visible_graph.get("bounded_projection")
        if max_tokens and metadata["tokens"] > max_tokens:
            raise ValueError(f"condition {condition} cannot be bounded to {max_tokens} tokens")
        if not metadata["context_preflight_passed"]:
            raise ValueError(f"condition {condition} exceeds reviewer context budget")
        packages.append(PackageV2(condition, text, sections["common"], sections, metadata))
    return packages


def _public_appworld_graph(appworld_graph: dict[str, Any]) -> dict[str, Any]:
    """Expose one value-hashed AppWorld graph without adding an ETIQ layer."""
    if appworld_graph.get("graph_kind") != "appworld_execution":
        raise ValueError("state AppWorld condition requires an appworld_execution graph")
    graph = {
        "schema_version": appworld_graph.get("schema_version"),
        "graph_kind": "appworld_execution",
        "source_sha256": appworld_graph.get("source_sha256"),
        "nodes": [_public_appworld_node(node) for node in appworld_graph["nodes"]],
        "edges": [
            {"src": "aw:" + edge["src"], "kind": edge["kind"], "dst": "aw:" + edge["dst"]}
            for edge in appworld_graph["edges"]
        ],
    }
    graph["manifest"] = _manifest(
        graph, "rdr.v2_etiq_export._public_appworld_graph@2.3.0"
    )
    return graph


def build_state_graph_conditions(
    trace: TraceV2,
    appworld_graph: dict[str, Any],
    etiq_graph: dict[str, Any],
    initial_task_state: dict[str, Any],
    final_task_state: dict[str, Any],
    max_tokens: int | None = None,
) -> list[PackageV2]:
    """Build matched initial/final-state arms with exactly one graph type each."""
    if etiq_graph.get("graph_kind") != "etiq_native" or etiq_graph.get("status") != "available":
        raise ValueError("state ETIQ condition requires available native ETIQ lineage")
    if appworld_graph.get("source_sha256") != etiq_graph.get("source_sha256"):
        raise ValueError("state graph conditions require graphs bound to the same source")
    common_sections = _initial_sections(
        "Y", trace, initial_task_state=initial_task_state, final_task_state=final_task_state
    )
    public_appworld = _public_appworld_graph(appworld_graph)
    packages = []
    for condition, graph in zip(
        STATE_GRAPH_CONDITIONS, (public_appworld, etiq_graph), strict=True
    ):
        sections = dict(common_sections)
        sections["graph"] = _render_public_graph(graph)
        text = "\n\n".join(sections.values())
        check_leakage(text)
        leaks = _public_evidence_check(text)
        if leaks:
            raise ValueError(f"state graph condition leaks private evidence: {leaks}")
        metadata = package_metadata(text, sections, trace, graph)
        metadata["experimental_condition"] = condition
        metadata["actual_reviewer_input_tokens"] = None
        metadata["size_covariate"] = "tokens"
        if max_tokens and metadata["tokens"] > max_tokens:
            raise ValueError(
                f"condition {condition} exceeds the single-graph token budget of {max_tokens}"
            )
        if not metadata["context_preflight_passed"]:
            raise ValueError(f"condition {condition} exceeds reviewer context budget")
        packages.append(PackageV2(condition, text, sections["common"], sections, metadata))
    return packages


def audit_state_graph_conditions(
    packages: list[PackageV2], private_values: list[str]
) -> dict[str, Any]:
    by_condition = {package.arm: package for package in packages}
    leaks = {
        package.arm: sorted(value for value in private_values if value and value in package.text)
        for package in packages
    }
    graph_kinds = {
        condition: package.sections["graph"].splitlines()[0]
        for condition, package in by_condition.items()
    }
    common_hashes = {_canonical_hash(package.common) for package in packages}
    passed = (
        set(by_condition) == set(STATE_GRAPH_CONDITIONS)
        and len(common_hashes) == 1
        and not any(leaks.values())
        and "kind=appworld_execution" in graph_kinds.get("STATE_APPWORLD_GRAPH", "")
        and "kind=etiq_native" in graph_kinds.get("STATE_ETIQ_GRAPH", "")
        and all(not _public_evidence_check(package.text) for package in packages)
    )
    return {
        "conditions": list(STATE_GRAPH_CONDITIONS),
        "common_sha256": next(iter(common_hashes)) if len(common_hashes) == 1 else None,
        "private_value_leaks": {key: value for key, value in leaks.items() if value},
        "graph_kinds": graph_kinds,
        "package_sizes": {package.arm: package.metadata for package in packages},
        "passed": passed,
    }


def _extract_layer(composite: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Reconstruct topology only for validation of already-built reviewer evidence."""
    graph_kind = "appworld_execution" if prefix == "aw:" else "etiq_native"
    nodes = [{**node, "id": node["id"].removeprefix(prefix)}
             for node in composite["nodes"] if node["id"].startswith(prefix)]
    edges = [
        {"src": edge["src"].removeprefix(prefix), "kind": edge["kind"],
         "dst": edge["dst"].removeprefix(prefix)}
        for edge in composite["edges"]
        if edge["src"].startswith(prefix) and edge["dst"].startswith(prefix)
    ]
    return {"graph_kind": graph_kind, "nodes": nodes, "edges": edges}


def audit_etiq_conditions(packages: list[PackageV2], private_values: list[str]) -> dict[str, Any]:
    by_condition = {package.arm: package for package in packages}
    leaks = {
        package.arm: sorted(value for value in private_values if value and value in package.text)
        for package in packages
    }
    graph_kinds = {
        condition: package.sections["graph"].splitlines()[0]
        for condition, package in by_condition.items()
    }
    common_hashes = {_canonical_hash(package.common) for package in packages}
    passed = (
        set(by_condition) == set(ETIQ_CONDITIONS)
        and len(common_hashes) == 1
        and not any(leaks.values())
        and "kind=etiq_native" in graph_kinds.get("ETIQ_CODE_LINEAGE", "")
        and "kind=appworld_etiq_composite" in graph_kinds.get("APPWORLD_ETIQ_COMPOSITE", "")
        and all(not _public_evidence_check(package.text) for package in packages)
    )
    return {
        "conditions": list(ETIQ_CONDITIONS),
        "common_sha256": next(iter(common_hashes)) if len(common_hashes) == 1 else None,
        "private_value_leaks": {key: value for key, value in leaks.items() if value},
        "graph_kinds": graph_kinds,
        "package_sizes": {package.arm: package.metadata for package in packages},
        "passed": passed,
    }


def build_versioned_smoke(
    scan_dir: Path, repeat_scan_dir: Path, cell_path: Path, output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ValueError("refusing to overwrite versioned ETIQ smoke")
    cell = json.loads(cell_path.read_text(encoding="utf-8"))
    trace = TraceV2.from_dict(cell["trace"])
    appworld = cell["execution_graph"]
    appworld_before = hashlib.sha256(_canonical_json(appworld).encode()).hexdigest()
    eligibility = qualify_etiq_repeatability(scan_dir, repeat_scan_dir)
    etiq = import_native_etiq(scan_dir, eligibility)
    composite, joins = build_appworld_etiq_composite(appworld, trace, etiq, eligibility)
    appworld_after = hashlib.sha256(_canonical_json(appworld).encode()).hexdigest()
    if appworld_before != appworld_after:
        raise ValueError("composite construction mutated the frozen AppWorld graph")
    symptom = next(
        write.record for call in trace.calls for write in call.writes
        if write.record.startswith("file_system.files#")
    )
    packages = build_etiq_conditions(trace, symptom, etiq, composite)
    private_values = [
        value for call in cell["trace"]["calls"]
        for key, value in call["args"].items()
        if SENSITIVE_NAME.search(key) and isinstance(value, str)
    ]
    audit = audit_etiq_conditions(packages, private_values)
    if not audit["passed"]:
        raise ValueError("ETIQ condition isolation audit failed")
    output_dir.mkdir(parents=True)
    _write_json_create_only(output_dir / "graphs/etiq_native.json", etiq)
    _write_json_create_only(output_dir / "graphs/appworld_etiq_composite.json", composite)
    _write_json_create_only(output_dir / "private/join-assessment.json", joins)
    _write_json_create_only(output_dir / "private/repeatability-qualification.json", eligibility)
    _write_json_create_only(output_dir / "isolation-audit.json", audit)
    for package in packages:
        path = output_dir / "packages" / f"{package.arm}.txt"
        if path.exists():
            raise ValueError(f"refusing to overwrite {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(package.text, encoding="utf-8")
    summary = {
        "schema_version": "2.3.0",
        "excluded_from_experiment_analysis": True,
        "source_sha256": appworld["source_sha256"],
        "frozen_appworld_graph_unchanged": appworld_before == appworld_after,
        "counts": {
            "appworld": {"nodes": len(appworld["nodes"]), "edges": len(appworld["edges"])},
            "etiq": {"nodes": len(etiq["nodes"]), "edges": len(etiq["edges"])},
            "composite": {"nodes": len(composite["nodes"]), "edges": len(composite["edges"])},
        },
        "bridge_counts": {
            key: value for key, value in composite["counts"].items() if key.startswith("bridge_")
        },
        "verified_effect_path": joins["verified_effect_path"],
        "ambiguous_join_count": joins["ambiguous_join_count"],
        "unlinked_join_count": joins["unlinked_join_count"],
        "workflow_only_eligibility": eligibility["workflow_only_eligibility"],
        "composite_eligibility": joins["composite_eligibility"],
        "condition_package_sha256": {
            package.arm: package.metadata["package_sha256"] for package in packages
        },
        "package_sizes": {
            package.arm: {
                "characters": package.metadata["characters"],
                "utf8_bytes": package.metadata["utf8_bytes"],
                "regex_tokens": package.metadata["tokens"],
                "actual_reviewer_input_tokens": None,
                "bounded_projection": package.metadata["bounded_projection"],
            }
            for package in packages
        },
        "isolation_audit_passed": True,
    }
    _write_json_create_only(output_dir / "smoke-summary.json", summary)
    artifacts = {
        path.relative_to(output_dir).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output_dir.rglob("*")) if path.is_file()
    }
    _write_json_create_only(output_dir / "manifest.json", {
        "schema_version": "2.2.0", "create_only": True, "artifacts": artifacts,
        "artifact_count": len(artifacts),
    })
    return summary


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _link_or_copy(source: str, destination: str) -> str:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return destination


def _copy_verified_native_pair(
    reuse_build: Path, destination: Path, instance_id: str,
    trace_data: dict[str, Any], run_data: dict[str, Any], entry: Path,
) -> dict[str, Any]:
    from rdr.etiq_pilot import (
        build_frozen_trace_replay_bundle, validate_replay_bundle,
        validate_scan_result, verify_manifest as verify_scan_manifest,
    )

    source = reuse_build / "private/etiq" / instance_id
    bundle_path = source / "exchange/bundle.json"
    bundle = validate_replay_bundle(bundle_path)
    expected, expected_source = build_frozen_trace_replay_bundle(
        trace_data, Path(bundle["workflow_path"]), instance_id,
        run_data.get("fault_plan"), run_data.get("repair_index"),
    )
    if expected != bundle:
        raise ValueError(f"{instance_id}: reused replay bundle differs from frozen trace")
    if (source / "exchange/workflow.py").read_text(encoding="utf-8") != expected_source:
        raise ValueError(f"{instance_id}: reused workflow differs from frozen trace")
    runs = []
    for name in ("run-1", "run-2"):
        run = source / name
        manifest = verify_scan_manifest(run)
        validate_scan_result(run, entry, bundle_path=bundle_path)
        runs.append({
            "run": name,
            "scan_manifest_sha256": _sha256_file(run / "manifest.json"),
            "native_graph_sha256": json.loads(
                (run / "scan-result.json").read_text(encoding="utf-8")
            )["native_graph"]["sha256"],
            "replay_bundle_sha256": manifest["replay_bundle_sha256"],
        })
    destination.mkdir(parents=True)
    for name in (
        "exchange", "run-1", "run-2", ".run-1-isolation", ".run-2-isolation",
    ):
        shutil.copytree(source / name, destination / name, copy_function=_link_or_copy)
    for name in (".run-1-private-replay-result.json", ".run-2-private-replay-result.json"):
        _link_or_copy(str(source / name), str(destination / name))
    return {
        "instance_id": instance_id, "capture_origin": "reused_verified_native_pair",
        "source_build": str(reuse_build), "source_instance": str(source), "runs": runs,
    }


def _verify_complete_etiq_coverage(
    truths: list[dict[str, Any]], rows: list[dict[str, Any]], audits: list[dict[str, Any]],
    blocked_captures: list[dict[str, Any]],
    conditions: tuple[str, ...] = ETIQ_CONDITIONS,
) -> dict[str, Any]:
    expected_ids = {truth["instance_id"] for truth in truths}
    if blocked_captures:
        raise ValueError(f"ETIQ coverage blocked for {len(blocked_captures)} instances")
    if {audit["instance_id"] for audit in audits} != expected_ids:
        raise ValueError("ETIQ isolation audit does not cover the complete frozen population")
    condition_rows = [row for row in rows if row["arm"] in conditions]
    by_condition = {
        arm: [row for row in condition_rows if row["arm"] == arm]
        for arm in conditions
    }
    for arm, arm_rows in by_condition.items():
        ids = [row["instance_id"] for row in arm_rows]
        if len(ids) != len(expected_ids) or len(set(ids)) != len(ids) or set(ids) != expected_ids:
            raise ValueError(f"{arm} does not contain exactly the frozen 42-instance population")
        authors = Counter(row.get("author") for row in arm_rows)
        if authors != Counter({"codex": 21, "dataset": 21}):
            raise ValueError(f"{arm} author balance differs: {dict(authors)}")
    expected_packages = len(expected_ids) * len(conditions)
    if len(condition_rows) != expected_packages:
        raise ValueError(
            f"expected exactly {expected_packages} additive graph packages, "
            f"found {len(condition_rows)}"
        )
    return {
        "instances": len(expected_ids), "condition_packages": len(condition_rows),
        "condition_instance_ids_identical": True,
        "authors_by_condition": {
            arm: dict(sorted(Counter(row["author"] for row in arm_rows).items()))
            for arm, arm_rows in by_condition.items()
        },
    }


def _relative_file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256_file(path)
        for path in sorted(paths)
    }


def extend_frozen_build_with_etiq(
    source_build: Path, output_dir: Path, code_provenance: Path,
    reuse_native_build: Path | None = None,
) -> dict[str, Any]:
    """Create a new freeze with additive ETIQ conditions from frozen executions."""
    from rdr.etiq_pilot import (
        build_frozen_trace_replay_bundle, run_isolated_scan, validate_scan_result,
    )
    from rdr.freeze import verify_manifest, write_manifest
    from rdr.v2_dry_run import _write_package_manifests
    from rdr.v2_provenance import verify_current_code_snapshot

    problems = verify_manifest(source_build)
    if problems:
        raise ValueError(f"source build manifest failed: {problems[:5]}")
    code_problems = verify_current_code_snapshot(code_provenance)
    if code_problems:
        raise ValueError(f"current executable code differs from ETIQ build provenance: {code_problems[:5]}")
    if reuse_native_build:
        reuse_problems = verify_manifest(reuse_native_build)
        if reuse_problems:
            raise ValueError(f"native reuse build manifest failed: {reuse_problems[:5]}")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    truths = [json.loads(path.read_text()) for path in sorted(
        (source_build / "private/truth").glob("*.json")
    )]
    classes = {truth.get("fault_class") for truth in truths if truth.get("fault_class")}
    required_classes = {"source", "runtime", "mixed", "interaction", "amplified"}
    if not required_classes <= classes:
        raise ValueError(f"frozen build lacks required fault classes: {sorted(required_classes - classes)}")
    if any(truth.get("injection_channel") is not None for truth in truths):
        raise ValueError("active reliability build contains out-of-scope injection metadata")

    shutil.copytree(source_build, output_dir, copy_function=os.link)
    for manifest in output_dir.rglob("MANIFEST.sha256.json"):
        manifest.unlink()
    for relative in (
        "public/package_manifest.jsonl", "private/package_truth_manifest.jsonl",
        "public/one_shot_job_order.json", "public/interactive_job_order.json",
        "public/build_identity.json", "summary.json",
    ):
        (output_dir / relative).unlink()

    rows = [json.loads(line) for line in (
        source_build / "private/package_truth_manifest.jsonl"
    ).read_text().splitlines()]
    existing_max = defaultdict(int)
    for row in rows:
        if row["arm"] not in ALL_ETIQ_CONDITIONS:
            existing_max[row["instance_id"]] = max(existing_max[row["instance_id"]], row["tokens"])
    capture_root = output_dir / "private/etiq"
    audits = []
    blocked_captures = []
    capture_provenance = []
    for truth in truths:
        instance_id = next(path.stem for path in (source_build / "private/truth").glob("*.json")
                           if json.loads(path.read_text())["instance_id"] == truth["instance_id"])
        trace_data = json.loads((source_build / "private/traces" / f"{instance_id}.json").read_text())
        run_data = json.loads(
            (source_build / "private/runs" / instance_id / "run.json").read_text()
        )
        instance_capture = capture_root / instance_id
        entry = Path("fixtures/v2/etiq_replay_entry.py")
        try:
            if reuse_native_build and (reuse_native_build / "private/etiq" / instance_id).is_dir():
                capture_provenance.append(_copy_verified_native_pair(
                    reuse_native_build, instance_capture, instance_id,
                    trace_data, run_data, entry,
                ))
            else:
                exchange = instance_capture / "exchange"
                exchange.mkdir(parents=True)
                source_path = exchange / "workflow.py"
                bundle_path = exchange / "bundle.json"
                source_relative = source_path.resolve().relative_to(Path.cwd().resolve())
                bundle, source = build_frozen_trace_replay_bundle(
                    trace_data, source_relative, instance_id, run_data.get("fault_plan"),
                    run_data.get("repair_index"),
                )
                source_path.write_text(source, encoding="utf-8")
                bundle_path.write_text(
                    json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                first = instance_capture / "run-1"
                second = instance_capture / "run-2"
                run_isolated_scan(entry, first, bundle_path=bundle_path)
                run_isolated_scan(entry, second, bundle_path=bundle_path)
                validate_scan_result(first, entry, bundle_path=bundle_path)
                validate_scan_result(second, entry, bundle_path=bundle_path)
                capture_provenance.append({
                    "instance_id": instance_id, "capture_origin": "new_native_pair",
                    "source_build": None,
                })
            first = instance_capture / "run-1"
            second = instance_capture / "run-2"
            eligibility = qualify_etiq_repeatability(first, second)
        except Exception as error:
            blocked_captures.append({
                "instance_id": instance_id, "status": "blocked",
                "reason": f"{type(error).__name__}: {error}",
            })
            continue
        if eligibility["workflow_only_eligibility"]["status"] != "eligible":
            blocked_captures.append({
                "instance_id": instance_id, "status": "blocked",
                "reason": eligibility.get("reason", "occurrence-level captures differ"),
            })
            continue
        etiq = import_native_etiq(first, eligibility)
        appworld = json.loads(
            (source_build / "appworld_execution" / f"{instance_id}.json").read_text()
        )
        trace = TraceV2.from_dict(trace_data)
        composite, join_report = build_appworld_etiq_composite(
            appworld, trace, etiq, eligibility
        )
        packages = build_etiq_conditions(
            trace, truth["symptom"], etiq, composite,
            max_tokens=existing_max[instance_id],
        )
        initial_task_state = run_data.get("initial_task_state")
        final_task_state = run_data.get("final_task_state")
        if initial_task_state is None or final_task_state is None:
            raise ValueError(
                f"{instance_id}: state graph arms require pre- and post-execution task snapshots"
            )
        state_packages = build_state_graph_conditions(
            trace, appworld, etiq, initial_task_state, final_task_state,
            max_tokens=existing_max[instance_id],
        )
        packages.extend(state_packages)
        graph_root = output_dir / "public/instances" / instance_id / "etiq_graphs"
        _write_json_create_only(graph_root / "etiq_native.json", etiq)
        _write_json_create_only(graph_root / "appworld_etiq_composite.json", composite)
        private_root = capture_root / instance_id / "qualification"
        _write_json_create_only(private_root / "repeatability.json", eligibility)
        _write_json_create_only(private_root / "joins.json", join_report)
        private_values = [
            value for call in trace_data["calls"] for key, value in call["args"].items()
            if SENSITIVE_NAME.search(key) and isinstance(value, str)
        ]
        audit = audit_etiq_conditions(
            [package for package in packages if package.arm in ETIQ_CONDITIONS], private_values
        )
        state_audit = audit_state_graph_conditions(state_packages, private_values)
        audit["state_graph_conditions"] = state_audit
        audit["passed"] = audit["passed"] and state_audit["passed"]
        if not audit["passed"]:
            raise ValueError(f"{instance_id}: ETIQ isolation/leakage audit failed")
        audits.append({"instance_id": instance_id, **audit})
        for package in packages:
            package_path = output_dir / "public/instances" / instance_id / "packages" / f"{package.arm}.txt"
            if package_path.exists():
                raise ValueError(f"refusing to replace condition package {package_path}")
            package_path.write_text(package.text, encoding="utf-8")
            rows.append({
                "instance_id": instance_id,
                **{key: truth.get(key) for key in (
                    "fault_id", "fault_class", "repair", "fault_occurred",
                    "residual_harm_present", "author", "generator_cluster",
                    "trace_sha256", "task_input_sha256", "source_sha256",
                )},
                "arm": package.arm,
                **package.metadata,
            })
    (capture_root / "isolation-audit.json").write_text(
        json.dumps(audits, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (capture_root / "qualification-summary.json").write_text(json.dumps({
        "eligible": len(audits), "blocked": len(blocked_captures),
        "blocked_captures": blocked_captures,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (capture_root / "native-capture-provenance.json").write_text(json.dumps({
        "schema_version": "1.0", "pairs": capture_provenance,
        "reused_pairs": sum(item["capture_origin"] == "reused_verified_native_pair"
                            for item in capture_provenance),
        "new_pairs": sum(item["capture_origin"] == "new_native_pair"
                         for item in capture_provenance),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    public_truths = [
        {"instance_id": path.stem}
        for path in sorted((source_build / "private/truth").glob("*.json"))
    ]
    coverage = _verify_complete_etiq_coverage(
        public_truths, rows, audits, blocked_captures, ALL_ETIQ_CONDITIONS
    )
    _write_package_manifests(output_dir, rows)
    provenance_destination = output_dir / "private/provenance/etiq_reviewer_code"
    shutil.copytree(code_provenance, provenance_destination)
    code_record = json.loads((code_provenance / "code_provenance.json").read_text())
    base_identity = json.loads((source_build / "public/build_identity.json").read_text())
    (output_dir / "public/build_identity.json").write_text(json.dumps({
        "build_version": output_dir.name, "base_build": str(source_build),
        "code_snapshot_id": code_record["snapshot_id"],
        "base_build_identity": {
            "build_version": base_identity.get("build_version", source_build.name),
            "code_snapshot_id": base_identity["code_snapshot_id"],
            "manifest_sha256": _sha256_file(source_build / "MANIFEST.sha256.json"),
        },
        "additive_build_identity": {
            "build_version": output_dir.name,
            "code_snapshot_id": code_record["snapshot_id"],
            "code_provenance_sha256": _sha256_file(code_provenance / "code_provenance.json"),
            "code_provenance_manifest_sha256": _sha256_file(
                code_provenance / "MANIFEST.sha256.json"
            ),
        },
        "reviewer_model": "gpt-5.6-sol", "reasoning_effort": "medium",
    }, indent=2, sort_keys=True) + "\n")
    original_hashes = _relative_file_hashes(source_build / "public", [
        path for path in (source_build / "public/instances").glob("*/packages/*.txt")
        if path.stem not in ALL_ETIQ_CONDITIONS
    ])
    interactive_hashes = _relative_file_hashes(
        source_build / "public", [
            path for path in (source_build / "public/interactive").rglob("*")
            if path.is_file()
        ] if (source_build / "public/interactive").is_dir() else [],
    )
    unchanged = all(
        hashlib.sha256((output_dir / "public" / relative).read_bytes()).hexdigest() == digest
        for relative, digest in original_hashes.items()
    )
    interactive_unchanged = all(
        (output_dir / "public" / relative).is_file()
        and _sha256_file(output_dir / "public" / relative) == digest
        for relative, digest in interactive_hashes.items()
    )
    if not unchanged or not interactive_unchanged:
        raise ValueError("an existing non-Etiq reviewer input changed during ETIQ extension")
    summary = {
        "schema_version": "1.0", "base_build": str(source_build),
        "instances": len(truths), "conditions": list(ALL_ETIQ_CONDITIONS),
        "condition_packages": coverage["condition_packages"],
        "etiq_qualification": {"eligible": len(audits), "blocked": len(blocked_captures)},
        "existing_appworld_packages_byte_identical": True,
        "existing_interactive_inputs_byte_identical": True,
        "existing_package_files_verified": len(original_hashes),
        "existing_interactive_files_verified": len(interactive_hashes),
        "complete_coverage": coverage,
        "native_capture_reuse": {
            "reused_pairs": sum(item["capture_origin"] == "reused_verified_native_pair"
                                for item in capture_provenance),
            "new_pairs": sum(item["capture_origin"] == "new_native_pair"
                             for item in capture_provenance),
        },
        "isolation_passed": all(audit["passed"] for audit in audits),
        "size_covariate": "tokens", "reviewer_calls": 0,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    for root in (output_dir / "public", output_dir / "private", output_dir / "appworld_execution"):
        write_manifest(root)
    write_manifest(output_dir)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--instances", type=Path)
    parser.add_argument("--native-scan", type=Path)
    parser.add_argument("--repeat-native-scan", type=Path)
    parser.add_argument("--cell", type=Path)
    parser.add_argument("--smoke-root", type=Path)
    parser.add_argument("--source-build", type=Path)
    parser.add_argument("--extend-build", type=Path)
    parser.add_argument("--code-provenance", type=Path)
    parser.add_argument("--reuse-native-build", type=Path)
    args = parser.parse_args()
    if args.source_build and args.extend_build and args.code_provenance:
        print(json.dumps(extend_frozen_build_with_etiq(
            args.source_build, args.extend_build, args.code_provenance,
            args.reuse_native_build,
        ), sort_keys=True))
    elif args.native_scan and args.repeat_native_scan and args.cell and args.smoke_root:
        print(json.dumps(build_versioned_smoke(
            args.native_scan, args.repeat_native_scan, args.cell, args.smoke_root
        ), sort_keys=True))
    elif args.instances:
        output = args.instances / "etiq_native_unavailable.json"
        record_etiq_unavailable(output)
        print(json.dumps({"status": "unavailable", "artifact": str(output)}, sort_keys=True))
    elif args.execution and args.out:
        export_etiq_native(args.execution, args.out)
    else:
        parser.error(
            "provide --instances; --execution and --out; or --native-scan, "
            "--repeat-native-scan, --cell, and --smoke-root; or --source-build, "
            "--extend-build, and --code-provenance"
        )


if __name__ == "__main__":
    main()
