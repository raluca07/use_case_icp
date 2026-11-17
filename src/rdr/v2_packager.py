"""V2 evidence arms, size manifests and private-evidence isolation audits."""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass

from rdr.graph import (Edge, Graph, build_graph, call_node, edge_counts, fake_writes, incident_edges, neighbourhood,
                       random_subgraph, rec_node, render, strip_ignored, with_node, without_arguments,
                       without_node)
from rdr.packager import check_leakage, seed_for
from rdr.v2_schema import TraceV2


ARMS_V2 = (
    *tuple(chr(code) for code in range(ord("A"), ord("Z") + 1)),
    "STATE_CALLS", "STATE_CALLS_SOURCE",
)
DEFAULT_CONTEXT_BUDGET_TOKENS = 200_000
SOURCE_ARMS = frozenset({"P", "Q", "R", "U", "V", "X", "Z", "STATE_CALLS_SOURCE"})
REAL_GRAPH_ARMS = frozenset({"C", "G", "Q", "T", "V"})
FAKE_GRAPH_ARMS = frozenset({"F", "H", "R"})
COLLAPSED_ARMS = frozenset({"S", "U"})
LOG_ARMS = frozenset({"B", "G", "H", "P", "Q", "R", "S", "T", "U", "V"})
STATE_ARMS = frozenset({"Y", "Z", "STATE_CALLS", "STATE_CALLS_SOURCE"})
NO_CALL_INDEX_ARMS = frozenset({"W", "X", "Y", "Z"})


@dataclass
class PackageV2:
    arm: str
    text: str
    common: str
    sections: dict[str, str]
    metadata: dict


def _common(trace: TraceV2) -> str:
    observed = trace.to_v1_observed()
    final = {record: strip_ignored(row) for record, row in observed.final_values().items()}
    lines = [
        "TASK", trace.instruction, "", "AGENT FINAL MESSAGE", trace.final_message, "",
        "FINAL STATE OF RECORDS THE AGENT CHANGED",
    ]
    lines.extend(f"{record} = {json.dumps(final[record], sort_keys=True, default=str)}" for record in sorted(final))
    return "\n".join(lines)


def _state_common(trace: TraceV2, initial_task_state: dict, final_task_state: dict) -> str:
    initial = json.dumps(strip_ignored(initial_task_state), indent=2, sort_keys=True, default=str)
    final = json.dumps(strip_ignored(final_task_state), indent=2, sort_keys=True, default=str)
    return "\n".join([
        "TASK", trace.instruction, "", "INITIAL TASK INPUTS", initial, "",
        "AGENT FINAL MESSAGE", trace.final_message, "", "FINAL TASK STATE", final,
    ])


def _call_index(trace: TraceV2) -> str:
    return "\n".join([
        "CALLS MADE (index and API only)",
        *(f"{call.index} {call.name}" for call in trace.calls),
    ])


def _common_with_calls(trace: TraceV2) -> str:
    return _common(trace) + "\n\n" + _call_index(trace)


def _initial_sections(
    arm: str,
    trace: TraceV2,
    initial_task_state: dict | None = None,
    final_task_state: dict | None = None,
) -> dict[str, str]:
    if arm in STATE_ARMS:
        if initial_task_state is None or final_task_state is None:
            raise ValueError(f"arm {arm} requires initial and final task state")
        sections = {"common": _state_common(trace, initial_task_state, final_task_state)}
    else:
        sections = {"common": _common(trace)}
    if arm not in NO_CALL_INDEX_ARMS:
        sections["call_index"] = _call_index(trace)
    return sections


def _inputs(trace: TraceV2) -> str:
    lines = ["CALL INPUTS"]
    for call in trace.calls:
        args = json.dumps(strip_ignored(call.args), sort_keys=True, default=str)
        lines.append(f"[{call.index}] {call.name}({args})")
    return "\n".join(lines)


def _responses(trace: TraceV2) -> str:
    lines = ["OBSERVED RESPONSES"]
    for call in trace.calls:
        response = json.dumps(strip_ignored(call.observed_response), sort_keys=True, default=str)
        lines.append(f"[{call.index}] {call.name} -> {response}")
    return "\n".join(lines)


def _action_log(trace: TraceV2) -> str:
    """Fabio's legacy complete log: each call is immediately followed by its response."""
    lines = ["COMPLETE INTERLEAVED ACTION LOG"]
    for call in trace.calls:
        args = json.dumps(strip_ignored(call.args), sort_keys=True, default=str)
        response = json.dumps(strip_ignored(call.observed_response), sort_keys=True, default=str)
        lines.extend((f"[{call.index}] {call.name}({args})", f"[{call.index}] -> {response}"))
    return "\n".join(lines)


def _source(trace: TraceV2) -> str:
    parts = ["EXECUTED WORKFLOW SOURCE"]
    for path in sorted(trace.source):
        parts.extend([f"FILE {path}", trace.source[path]])
    return "\n".join(parts)


def derive_groups(trace: TraceV2) -> dict[str, list[int]]:
    """Use execution-provided group ids; fall back to contiguous app groups, never private truth."""
    groups: dict[str, list[int]] = {}
    for call in trace.calls:
        ids = call.group_ids or [f"app:{call.app}"]
        for group_id in ids:
            groups.setdefault(group_id, []).append(call.index)
    return groups


def _collapsed(trace: TraceV2, graph_text: str) -> str:
    groups = derive_groups(trace)
    graph = build_graph(trace.to_v1_observed())
    membership = {call_node(index): group for group, indices in groups.items() for index in indices}
    lines = ["COLLAPSED EXECUTION GROUPS"]
    for group, indices in sorted(groups.items()):
        members = {call_node(index) for index in indices}
        boundary = sorted({node for edge in graph.edges for node in (edge.src, edge.dst)
                           if node in members and (edge.src not in members or edge.dst not in members)})
        stable = hashlib.sha256((group + ":" + ",".join(map(str, indices))).encode()).hexdigest()[:12]
        lines.append(
            f"group:{stable} name={group} hidden_nodes={len(indices)} depth={group.count('/')} "
            f"boundary={json.dumps(boundary)}"
        )
    lines.append("TYPED EXTERNAL EDGES")
    for edge in graph.edges:
        src = membership.get(edge.src, edge.src)
        dst = membership.get(edge.dst, edge.dst)
        if src != dst:
            lines.append(f"{src} -{edge.kind}-> {dst}")
    return "\n".join(lines)


def _token_count(text: str) -> int:
    return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))


def package_metadata(text: str, sections: dict[str, str], trace: TraceV2, graph=None) -> dict:
    source_files = sorted(trace.source) if "source" in sections else []
    tokens = _token_count(text)
    section_sizes = {
        name: {"characters": len(value), "utf8_bytes": len(value.encode()),
               "lines": len(value.splitlines()), "tokens": _token_count(value)}
        for name, value in sections.items()
    }
    graph_payload = None
    if isinstance(graph, dict):
        graph_payload = json.dumps(graph, sort_keys=True, separators=(",", ":"), default=str)
    elif graph is not None:
        graph_payload = render(graph)
    return {
        "characters": len(text),
        "utf8_bytes": len(text.encode()),
        "lines": len(text.splitlines()),
        "tokens": tokens,
        "tokenizer": "regex-v1",
        "tokens_by_section": {name: _token_count(value) for name, value in sections.items()},
        "section_sizes": section_sizes,
        "context_budget_tokens": DEFAULT_CONTEXT_BUDGET_TOKENS,
        "context_preflight_passed": tokens <= DEFAULT_CONTEXT_BUDGET_TOKENS,
        "graph_nodes": None if graph is None else (
            len(graph.get("nodes", [])) if isinstance(graph, dict) else len(graph.call_nodes) + len(graph.record_nodes)),
        "graph_edges_by_type": {} if graph is None else (
            _json_edge_counts(graph) if isinstance(graph, dict) else edge_counts(graph)),
        "graph_projection_sha256": hashlib.sha256(graph_payload.encode()).hexdigest() if graph_payload else None,
        "source_files": source_files,
        "source_lines": sum(len(trace.source[path].splitlines()) for path in source_files),
        "truncated": False,
        "truncation_rule": None,
        "package_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _matched_fake(real, symptom: str, seed: int):
    """Find the first deterministic rewire that preserves the registered graph margins."""
    for offset in range(1000):
        try:
            fake, _ = fake_writes(real, rec_node(symptom), set(), seed + offset)
        except ValueError:
            continue
        if (set(fake.call_nodes) == set(real.call_nodes)
                and set(fake.record_nodes) == set(real.record_nodes)
                and edge_counts(fake) == edge_counts(real)):
            return fake
    raise ValueError("could not construct a margin-matched fake graph")


def build_package_v2(
    arm: str,
    trace: TraceV2,
    symptom: str,
    instance_id: str,
    anchor_index: int | None = None,
    execution_graph: dict | None = None,
    initial_task_state: dict | None = None,
    final_task_state: dict | None = None,
) -> PackageV2:
    if arm not in ARMS_V2:
        raise ValueError(f"unknown arm {arm}")
    if arm in {"N", "O"}:
        raise ValueError(f"arm {arm} requires an interactive reviewer protocol and cannot be serialized")
    if execution_graph is not None:
        return _build_from_execution_graph(
            arm, trace, symptom, instance_id, anchor_index, execution_graph,
            initial_task_state, final_task_state,
        )
    observed = trace.to_v1_observed()
    real = build_graph(observed)
    fake = None
    if arm in FAKE_GRAPH_ARMS:
        fake = _matched_fake(real, symptom, seed_for(instance_id))
        if set(fake.call_nodes) != set(real.call_nodes) or set(fake.record_nodes) != set(real.record_nodes):
            raise ValueError("fake graph node set differs from real graph")
        if edge_counts(fake) != edge_counts(real):
            raise ValueError("fake graph edge-type counts differ from real graph")
    sections = _initial_sections(arm, trace, initial_task_state, final_task_state)
    graph = None
    if arm in LOG_ARMS:
        sections["action_log"] = _action_log(trace)
    elif arm == "I":
        sections["inputs"] = _inputs(trace)
    if arm in SOURCE_ARMS:
        sections["source"] = _source(trace)
    if arm in REAL_GRAPH_ARMS:
        graph = real
        sections["graph"] = "PROVENANCE GRAPH\n" + render(real)
    elif arm in FAKE_GRAPH_ARMS:
        graph = fake
        sections["graph"] = "PROVENANCE GRAPH\n" + render(fake)
    elif arm == "J":
        graph = without_arguments(real)
        sections["graph"] = "PROVENANCE GRAPH\n" + render(graph)
    elif arm in {"D", "E", "K", "L", "M"}:
        part = neighbourhood(real, rec_node(symptom), 2)
        if arm == "E":
            part = random_subgraph(real, edge_counts(part), seed_for(instance_id))
        if arm in {"K", "L", "M"}:
            if anchor_index is None:
                raise ValueError(f"arm {arm} requires private anchor_index")
            anchor = call_node(anchor_index)
            if arm == "M":
                part = without_node(real, anchor)
            else:
                part = with_node(real, part, anchor)
                if arm == "L":
                    part = random_subgraph(real, edge_counts(part), seed_for(instance_id), incident_edges(real, anchor))
        graph = part
        sections["graph"] = "PROVENANCE GRAPH\n" + render(part)
    elif arm in COLLAPSED_ARMS:
        sections["graph"] = _collapsed(trace, render(real))
        graph = real
    text = "\n\n".join(sections.values())
    check_leakage(text)
    return PackageV2(arm, text, sections["common"], sections, package_metadata(text, sections, trace, graph))


def audit_packages(packages: list[PackageV2], private_values: list[str], execution_graph: dict | None = None) -> dict:
    by_arm = {package.arm: package for package in packages}
    common_hashes = {
        family: {
            hashlib.sha256(package.common.encode()).hexdigest()
            for package in packages
            if ("state" if package.arm in STATE_ARMS else "standard") == family
        }
        for family in ("standard", "state")
    }
    common_sections_valid = all(len(hashes) <= 1 for hashes in common_hashes.values())
    leaks = {
        package.arm: [value for value in private_values if value and value in package.text]
        for package in packages
    }
    source_violations = [package.arm for package in packages
                         if ("source" in package.sections) != (package.arm in SOURCE_ARMS)]
    forbidden_graph_kinds = [package.arm for package in packages
                             if any(value in package.text for value in ("codex_authoring", "etiq_native"))]
    graph_node_leaks = []
    if execution_graph:
        allowed = {node["id"] for node in execution_graph["nodes"]}
        for package in packages:
            graph_text = package.sections.get("graph", "")
            mentioned = set(re.findall(
                r"(?:call|span|invocation|response|artifact|source):[A-Za-z0-9_.:#/-]+", graph_text
            ))
            if any(node.startswith(("call:", "span:", "invocation:", "response:", "artifact:", "source:"))
                   and node not in allowed for node in mentioned):
                graph_node_leaks.append(package.arm)
    extension_equivalence = {}
    for base, extension in (("B", "P"), ("G", "Q"), ("H", "R"), ("S", "U"), ("T", "V")):
        if base in by_arm and extension in by_arm:
            base_sections = by_arm[base].sections
            extended = {key: value for key, value in by_arm[extension].sections.items() if key != "source"}
            extension_equivalence[f"{extension}={base}+source"] = base_sections == extended
    nested_identity = {}
    for left, right in (("S", "T"), ("U", "V")):
        if left in by_arm and right in by_arm:
            nested_identity[f"{left}/{right}"] = (
                by_arm[left].metadata.get("underlying_graph_sha256")
                == by_arm[right].metadata.get("underlying_graph_sha256")
            )
    return {
        "common_sections_byte_identical_within_family": common_sections_valid,
        "common_section_families": {
            family: sorted(hashes) for family, hashes in common_hashes.items() if hashes
        },
        "private_value_leaks": {arm: values for arm, values in leaks.items() if values},
        "package_hashes_unique": len({package.metadata["package_sha256"] for package in packages}),
        "source_arm_violations": source_violations,
        "forbidden_graph_kind_leaks": forbidden_graph_kinds,
        "graph_node_leaks": graph_node_leaks,
        "extension_equivalence": extension_equivalence,
        "nested_underlying_graph_identity": nested_identity,
        "passed": common_sections_valid and not any(leaks.values()) and not source_violations
                  and not forbidden_graph_kinds and not graph_node_leaks
                  and all(extension_equivalence.values()) and all(nested_identity.values()),
    }


def _json_edge_counts(graph: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in graph.get("edges", []):
        counts[edge["kind"]] = counts.get(edge["kind"], 0) + 1
    return counts


def _graph_structure_sha256(graph: dict) -> str:
    payload = {"nodes": graph.get("nodes", []), "edges": graph.get("edges", [])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _render_json_graph(graph: dict) -> str:
    nodes = {node["id"]: node for node in graph["nodes"]}
    lines = ["PROVENANCE GRAPH"]
    for node_id in sorted(nodes):
        node = nodes[node_id]
        detail = {key: value for key, value in node.items() if key != "id"}
        if "value" in detail:
            value = detail.pop("value")
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
            detail["value_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
            detail["value_type"] = type(value).__name__
        lines.append(f"NODE {node_id} {json.dumps(detail, sort_keys=True, default=str)}")
    for edge in sorted(graph["edges"], key=lambda item: (item["src"], item["kind"], item["dst"])):
        lines.append(f"EDGE {edge['src']} -{edge['kind']}-> {edge['dst']}")
    return "\n".join(lines)


def _subgraph(graph: dict, node_ids: set[str], edges: list[dict] | None = None) -> dict:
    chosen = edges if edges is not None else [edge for edge in graph["edges"]
                                               if edge["src"] in node_ids and edge["dst"] in node_ids]
    present = {endpoint for edge in chosen for endpoint in (edge["src"], edge["dst"])} | node_ids
    return {"nodes": [node for node in graph["nodes"] if node["id"] in present], "edges": chosen}


def _json_neighbourhood(graph: dict, centers: set[str], hops: int) -> dict:
    adjacent: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        adjacent.setdefault(edge["src"], set()).add(edge["dst"])
        adjacent.setdefault(edge["dst"], set()).add(edge["src"])
    keep, frontier = set(centers), [(center, 0) for center in centers]
    while frontier:
        node, distance = frontier.pop(0)
        if distance == hops:
            continue
        for neighbour in adjacent.get(node, set()):
            if neighbour not in keep:
                keep.add(neighbour)
                frontier.append((neighbour, distance + 1))
    return _subgraph(graph, keep)


def _random_matched(graph: dict, counts: dict[str, int], seed: int) -> dict:
    rng, edges = random.Random(seed), []
    for kind, count in sorted(counts.items()):
        pool = [edge for edge in graph["edges"] if edge["kind"] == kind]
        edges.extend(rng.sample(pool, min(count, len(pool))))
    return _subgraph(graph, set(), edges)


def _fake_json_graph(graph: dict, seed: int) -> dict:
    edges = [dict(edge) for edge in graph["edges"]]
    rng = random.Random(seed)
    original = {(edge["src"], edge["kind"], edge["dst"]) for edge in edges}
    for kind in sorted({edge["kind"] for edge in edges}):
        positions = [index for index, edge in enumerate(edges) if edge["kind"] == kind]
        rng.shuffle(positions)
        for offset, first in enumerate(positions):
            for second in positions[offset + 1:]:
                left, right = edges[first], edges[second]
                swapped = {(left["src"], kind, right["dst"]), (right["src"], kind, left["dst"])}
                if (left["src"] != right["src"] and left["dst"] != right["dst"]
                        and not swapped & original):
                    left["dst"], right["dst"] = right["dst"], left["dst"]
                    return {"nodes": [dict(node) for node in graph["nodes"]], "edges": edges}
    raise ValueError("could not construct a degree-preserving fake execution graph")


def _collapsed_json(graph: dict) -> str:
    groups = {node["id"] for node in graph["nodes"]
              if node["kind"] in {"invocation", "function_invocation", "loop_iteration"}}
    members = {edge["dst"]: edge["src"] for edge in graph["edges"]
               if edge["kind"] == "contains" and edge["src"] in groups}
    lines = ["COLLAPSED EXECUTION GROUPS"]
    for group in sorted(groups):
        node = next(item for item in graph["nodes"] if item["id"] == group)
        direct = {member for member, owner in members.items() if owner == group}
        boundary = sorted({endpoint for edge in graph["edges"] for endpoint in (edge["src"], edge["dst"])
                           if endpoint in direct and (edge["src"] not in direct or edge["dst"] not in direct)})
        lines.append(f"GROUP {group} type={node['kind']} depth={node.get('nesting_depth', 0)} "
                     f"hidden_nodes={len(direct)} boundary={json.dumps(boundary)}")
    lines.append("TYPED EXTERNAL EDGES")
    for edge in graph["edges"]:
        src, dst = members.get(edge["src"], edge["src"]), members.get(edge["dst"], edge["dst"])
        if src != dst:
            lines.append(f"EDGE {src} -{edge['kind']}-> {dst}")
    return "\n".join(lines)


def _build_from_execution_graph(
    arm: str,
    trace: TraceV2,
    symptom: str,
    instance_id: str,
    anchor_index: int | None,
    execution_graph: dict,
    initial_task_state: dict | None,
    final_task_state: dict | None,
) -> PackageV2:
    if execution_graph.get("graph_kind") != "appworld_execution":
        raise ValueError("packages require the frozen appworld_execution graph")
    if arm in {"N", "O"}:
        raise ValueError(f"arm {arm} requires an interactive reviewer protocol and cannot be serialized")
    if arm in {*"ABCDEFGHIJKLMPQRWXYZ", "STATE_CALLS", "STATE_CALLS_SOURCE"}:
        return _build_flat_projection(
            arm, trace, symptom, instance_id, anchor_index, execution_graph,
            initial_task_state, final_task_state,
        )
    sections = _initial_sections(arm, trace, initial_task_state, final_task_state)
    if arm in LOG_ARMS:
        sections["action_log"] = _action_log(trace)
    elif arm == "I":
        sections["inputs"] = _inputs(trace)
    if arm in SOURCE_ARMS:
        sections["source"] = _source(trace)
    graph = None
    centers = {node["id"] for node in execution_graph["nodes"] if node.get("record") == symptom}
    if not centers:
        centers = {f"call:{anchor_index}"} if anchor_index is not None else set()
    if arm in REAL_GRAPH_ARMS:
        graph = _subgraph(execution_graph, {node["id"] for node in execution_graph["nodes"]})
    elif arm in FAKE_GRAPH_ARMS:
        graph = _fake_json_graph(execution_graph, seed_for(instance_id))
    elif arm == "J":
        graph = json.loads(json.dumps(execution_graph))
        for node in graph["nodes"]:
            node.pop("args", None)
    elif arm in {"D", "E", "K", "L", "M"}:
        part = _json_neighbourhood(execution_graph, centers, 2)
        if arm == "E":
            part = _random_matched(execution_graph, _json_edge_counts(part), seed_for(instance_id))
        if arm in {"K", "L", "M"}:
            anchor = f"call:{anchor_index}"
            if arm == "M":
                keep = {node["id"] for node in execution_graph["nodes"]} - {anchor}
                part = _subgraph(execution_graph, keep)
            else:
                keep = {node["id"] for node in part["nodes"]} | {anchor}
                part = _subgraph(execution_graph, keep)
                if arm == "L":
                    counts = _json_edge_counts(part)
                    part = _random_matched(execution_graph, counts, seed_for(instance_id))
        graph = part
    elif arm in COLLAPSED_ARMS:
        sections["graph"] = _collapsed_json(execution_graph)
        graph = execution_graph
    if graph is not None and "graph" not in sections:
        sections["graph"] = _render_json_graph(graph)
    text = "\n\n".join(sections.values())
    check_leakage(text)
    metadata = package_metadata(text, sections, trace, graph)
    if arm in {"S", "T", "U", "V"}:
        metadata["underlying_graph_sha256"] = _graph_structure_sha256(execution_graph)
    if not metadata["context_preflight_passed"]:
        raise ValueError(f"arm {arm} exceeds reviewer context budget without truncation")
    return PackageV2(arm, text, sections["common"], sections, metadata)


def _flat_graph(execution_graph: dict) -> Graph:
    nodes = {node["id"]: node for node in execution_graph["nodes"]}
    calls = {}
    records = {}
    for node_id, node in nodes.items():
        if node.get("kind") == "api_call":
            args = ", ".join(f"{key}={value!r}" for key, value in sorted(node.get("args", {}).items()))
            calls[node_id] = f"{node['index']} {node['api']}({args})"
        if node.get("kind") in {"artifact_before", "artifact_after"} and node.get("record"):
            records[node_id] = "rec:" + node["record"]
    edges = []
    for edge in execution_graph["edges"]:
        src, dst, kind = edge["src"], edge["dst"], edge["kind"]
        if kind == "writes" and src in calls and dst in records:
            edges.append(Edge(src, records[dst], kind))
        elif kind == "reads" and src in records and dst in calls:
            edges.append(Edge(records[src], dst, kind))
        elif kind == "feeds" and src.startswith("response:observed:") and dst in calls:
            edges.append(Edge("call:" + src.rsplit(":", 1)[1], dst, kind))
    unique = list(dict.fromkeys(edges))
    return Graph(calls, sorted(set(records.values())), unique)


def _build_flat_projection(
    arm: str,
    trace: TraceV2,
    symptom: str,
    instance_id: str,
    anchor_index: int | None,
    execution_graph: dict,
    initial_task_state: dict | None,
    final_task_state: dict | None,
) -> PackageV2:
    real = _flat_graph(execution_graph)
    fake = _matched_fake(real, symptom, seed_for(instance_id)) if arm in FAKE_GRAPH_ARMS else None
    sections = _initial_sections(arm, trace, initial_task_state, final_task_state)
    graph = None
    if arm in LOG_ARMS:
        sections["action_log"] = _action_log(trace)
    elif arm == "I":
        sections["inputs"] = _inputs(trace)
    if arm in SOURCE_ARMS:
        sections["source"] = _source(trace)
    if arm in {"C", "G", "Q"}:
        graph = real
    elif arm in {"F", "H", "R"}:
        graph = fake
    elif arm == "J":
        graph = without_arguments(real)
    elif arm in {"D", "E", "K", "L", "M"}:
        graph = neighbourhood(real, rec_node(symptom), 2)
        if arm == "E":
            graph = random_subgraph(real, edge_counts(graph), seed_for(instance_id))
        if arm in {"K", "L", "M"}:
            if anchor_index is None:
                raise ValueError(f"arm {arm} requires private anchor_index")
            anchor = call_node(anchor_index)
            if arm == "M":
                graph = without_node(real, anchor)
            else:
                graph = with_node(real, graph, anchor)
                if arm == "L":
                    graph = random_subgraph(real, edge_counts(graph), seed_for(instance_id),
                                            incident_edges(real, anchor))
    if graph is not None:
        sections["graph"] = "PROVENANCE GRAPH\n" + render(graph)
    text = "\n\n".join(sections.values())
    check_leakage(text)
    metadata = package_metadata(text, sections, trace, graph)
    if not metadata["context_preflight_passed"]:
        raise ValueError(f"arm {arm} exceeds reviewer context budget without truncation")
    return PackageV2(arm, text, sections["common"], sections, metadata)
