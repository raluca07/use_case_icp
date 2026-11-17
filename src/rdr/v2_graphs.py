"""Private authoring graph and public-execution graph summaries for v2."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from rdr.appworld_adapter import APPWORLD_ROOT, REPO, load_schema
from rdr.graph import build_graph, id_key_tables, strip_ignored
from rdr.v2_schema import TraceV2


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_authoring_graph(workspace: Path) -> dict:
    """Build private provenance from Codex JSONL without copying session or credential metadata."""
    metadata = json.loads((workspace / "authoring.json").read_text())
    run_id = "authoring:" + _sha_text(metadata.get("thread_id", metadata["solution_sha256"]))[:16]
    nodes = [
        {"id": "run", "kind": "authoring_run", "run_id": run_id,
         "requested_model": metadata.get("requested_model"), "served_model": metadata["served_model"],
         "requested_effort": metadata.get("requested_effort"), "served_effort": metadata["served_effort"],
         "cli_version": metadata.get("cli_version"), "elapsed_seconds": metadata.get("elapsed_seconds"),
         "usage": metadata.get("usage")},
        {"id": "task", "kind": "prompt", "sha256": metadata["task_sha256"]},
        {"id": "api_docs", "kind": "documentation", "sha256": metadata["api_inventory_sha256"]},
    ]
    edges = []
    for number, prompt_path in enumerate(sorted(workspace.glob("revision_feedback*.md")), 1):
        prompt_id = f"revision_prompt:{number}"
        nodes.append({"id": prompt_id, "kind": "prompt", "sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest()})
        edges.append({"src": "run", "kind": "contains", "dst": prompt_id})
    previous_source = None
    jsonl_paths = [workspace / "codex_stdout.jsonl", *sorted(workspace.glob("revision_*_stdout.jsonl"))]
    command_number = 0
    for turn, path in enumerate(jsonl_paths):
        for line in path.read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") or {}
            if event.get("type") != "item.completed":
                continue
            if item.get("type") == "command_execution":
                command_number += 1
                node_id = f"command:{command_number}"
                output = _sanitize(item.get("aggregated_output") or "", workspace)
                command = _sanitize(item.get("command") or "", workspace)
                is_test = any(token in command for token in ("pytest", "py_compile", "assert ", "ast.parse"))
                nodes.append({
                    "id": node_id,
                    "kind": "test_execution" if is_test else "command",
                    "command": command,
                    "exit_code": item.get("exit_code"),
                    "turn": turn,
                })
                edges.append({"src": "run", "kind": "contains", "dst": node_id})
                output_id = f"output:{command_number}"
                nodes.append({"id": output_id, "kind": "test_output" if is_test else "command_output", "text": output,
                              "sha256": _sha_text(output), "turn": turn})
                edges.append({"src": node_id, "kind": "observed", "dst": output_id})
                if previous_source:
                    edges.append({"src": node_id, "kind": "tested", "dst": previous_source})
            elif item.get("type") == "file_change":
                for change in item.get("changes") or []:
                    if Path(change.get("path", "")).name != "solution.py":
                        continue
                    source_hash = metadata["solution_sha256"] if turn == len(jsonl_paths) - 1 else None
                    if turn == 0:
                        source_hash = metadata.get("initial_solution_sha256", source_hash)
                    elif turn - 1 < len(metadata.get("revisions", [])):
                        source_hash = metadata["revisions"][turn - 1].get("solution_sha256")
                    if source_hash is None:
                        source_hash = f"unavailable-turn-{turn}"
                    node_id = f"source:{source_hash}"
                    if not any(node["id"] == node_id for node in nodes):
                        nodes.append({"id": node_id, "kind": "source", "sha256": source_hash, "turn": turn})
                    edit_id = f"edit:{turn}:{len([n for n in nodes if n['kind'] == 'edit']) + 1}"
                    nodes.append({"id": edit_id, "kind": "edit", "turn": turn,
                                  "change_kind": change.get("kind")})
                    edges.append({"src": "run", "kind": "contains", "dst": edit_id})
                    edges.append({"src": edit_id, "kind": "modified", "dst": node_id})
                    if previous_source and previous_source != node_id:
                        edges.append({"src": node_id, "kind": "revised_after", "dst": previous_source})
                    previous_source = node_id
    final_id = f"source:{metadata['solution_sha256']}"
    if not any(node["id"] == final_id for node in nodes):
        nodes.append({"id": final_id, "kind": "source", "sha256": metadata["solution_sha256"], "turn": len(jsonl_paths) - 1})
    final_workflow = "final_workflow"
    nodes.append({"id": final_workflow, "kind": "final_workflow", "sha256": metadata["solution_sha256"]})
    edges.extend([
        {"src": "run", "kind": "contains", "dst": "task"},
        {"src": "run", "kind": "contains", "dst": "api_docs"},
        {"src": "run", "kind": "produced", "dst": final_workflow},
        {"src": final_workflow, "kind": "contains", "dst": final_id},
    ])
    graph = {
        "schema_version": "2.1.0",
        "graph_kind": "codex_authoring",
        "private": True,
        "run_id": run_id,
        "requested_model": metadata.get("requested_model"),
        "served_model": metadata["served_model"],
        "requested_effort": metadata.get("requested_effort"),
        "served_effort": metadata["served_effort"],
        "cli_version": metadata.get("cli_version"),
        "task_sha256": metadata["task_sha256"],
        "api_inventory_sha256": metadata["api_inventory_sha256"],
        "elapsed_seconds": metadata.get("elapsed_seconds"),
        "usage": metadata.get("usage"),
        "final_source_sha256": metadata["solution_sha256"],
        "nodes": nodes,
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
    }
    graph["manifest"] = _manifest(graph, "rdr.v2_graphs.build_authoring_graph@2.1.0")
    return graph


def _sanitize(value: str, workspace: Path) -> str:
    value = value.replace(str(workspace), "<workspace>").replace(str(workspace.parent), "<workspace-parent>")
    value = re.sub(r"/tmp/rdr-v2-author-[A-Za-z0-9_.-]+", "<workspace>", value)
    value = re.sub(r"/home/[^/\s]+", "<home>", value)
    value = re.sub(
        r"(?i)(access[_-]?token|password|api[_-]?key)(['\"]?\s*[:=]\s*['\"]?)([^'\"\s,}\]]+)",
        r"\1\2<redacted>",
        value,
    )
    return value


def _manifest(graph: dict, builder: str) -> dict:
    payload = json.dumps({key: value for key, value in graph.items() if key != "manifest"},
                         sort_keys=True, separators=(",", ":"), default=str)
    return {"builder": builder, "content_sha256": _sha_text(payload),
            "node_count": len(graph.get("nodes", [])), "edge_count": len(graph.get("edges", [])),
            "source_sha256": graph.get("source_sha256") or graph.get("final_source_sha256"),
            "run_id": graph.get("run_id")}


def write_authoring_graph(workspace: Path) -> Path:
    output = workspace / "codex_authoring.json"
    output.write_text(json.dumps(build_authoring_graph(workspace), indent=2, sort_keys=True))
    return output


def execution_graph_summary(trace: TraceV2, source_sha256: str, run_id: str) -> dict:
    """Build the complete execution graph from the exact frozen TraceV2 artifact."""
    nodes = [{"id": "source:file:workflow.py", "kind": "source_file", "sha256": source_sha256}]
    edges = []
    seen = {nodes[0]["id"]}

    def add(node: dict) -> None:
        if node["id"] not in seen:
            nodes.append(node)
            seen.add(node["id"])

    for call in trace.calls:
        call_id = f"call:{call.index}"
        add({"id": call_id, "kind": "api_call", "index": call.index, "api": call.name,
             "args": strip_ignored(call.args)})
        span_id = "span:" + _sha_text(call.source_span or "unknown")[:16]
        add({"id": span_id, "kind": "source_span", "location": call.source_span})
        edges.extend([
            {"src": "source:file:workflow.py", "kind": "contains", "dst": span_id},
            {"src": call_id, "kind": "executed_by", "dst": span_id},
        ])
        parent_group = None
        for group in call.group_ids:
            group_id = "invocation:" + _sha_text(group)[:16]
            kind = "loop_iteration" if group.startswith("loop:") else "function_invocation"
            add({"id": group_id, "kind": kind, "identity": group,
                 "nesting_depth": group.count("/") + int(group.startswith("loop:"))})
            if parent_group:
                edges.append({"src": parent_group, "kind": "contains", "dst": group_id})
            parent_group = group_id
        if parent_group:
            edges.append({"src": parent_group, "kind": "contains", "dst": call_id})
        raw_id, observed_id = f"response:raw:{call.index}", f"response:observed:{call.index}"
        add({"id": raw_id, "kind": "raw_response", "value": strip_ignored(call.raw_response)})
        add({"id": observed_id, "kind": "observed_response", "value": strip_ignored(call.observed_response)})
        edges.extend([
            {"src": call_id, "kind": "contains", "dst": raw_id},
            {"src": raw_id, "kind": "observed_as", "dst": observed_id},
        ])
        for write in call.writes:
            before_id = "artifact:before:" + _sha_text(f"{call.index}:{write.record}")[:20]
            after_id = "artifact:after:" + _sha_text(f"{call.index}:{write.record}")[:20]
            add({"id": before_id, "kind": "artifact_before", "record": write.record,
                 "value": strip_ignored(write.before)})
            add({"id": after_id, "kind": "artifact_after", "record": write.record,
                 "value": strip_ignored(write.after)})
            edges.append({"src": call_id, "kind": "writes", "dst": after_id})
    schema = load_schema(REPO / "runs" / "schema.json")
    docs = {path.stem: json.loads(path.read_text())
            for path in (APPWORLD_ROOT / "data" / "api_docs" / "standard").glob("*.json")}
    legacy = build_graph(trace.to_v1_observed(), id_key_tables(docs, schema.tables, schema.foreign_keys))
    for edge in legacy.edges:
        if edge.kind == "feeds":
            earlier = int(edge.src.split(":", 1)[1])
            edges.append({"src": f"response:observed:{earlier}", "kind": "feeds", "dst": edge.dst})
        elif edge.kind == "reads":
            record = edge.src.removeprefix("rec:")
            reader = int(edge.dst.split(":", 1)[1])
            versions = []
            for call in trace.calls:
                for write in call.writes:
                    if write.record == record:
                        before_id = "artifact:before:" + _sha_text(f"{call.index}:{record}")[:20]
                        after_id = "artifact:after:" + _sha_text(f"{call.index}:{record}")[:20]
                        versions.append((call.index, before_id, after_id, write.before))
            prior = [version for version in versions if version[0] < reader]
            if prior:
                artifact = prior[-1][2]
            else:
                initial = next((version for version in versions if version[3] is not None), None)
                artifact = initial[1] if initial else None
            if artifact:
                edges.append({"src": artifact, "kind": "reads", "dst": edge.dst})
    graph = {
        "schema_version": "2.1.0",
        "graph_kind": "appworld_execution",
        "run_id": run_id,
        "source_sha256": source_sha256,
        "trace_sha256": _sha_text(json.dumps(trace.to_dict(), sort_keys=True, default=str)),
        "calls": [
            {"index": call.index, "api": call.name,
             "raw_response_sha256": _sha_text(json.dumps(call.raw_response, sort_keys=True, default=str)),
             "observed_response_sha256": _sha_text(json.dumps(call.observed_response, sort_keys=True, default=str))}
            for call in trace.calls
        ],
        "nodes": sorted(nodes, key=lambda node: node["id"]),
        "edges": sorted({(edge["src"], edge["kind"], edge["dst"]) for edge in edges}),
        "counts": {
            "calls": len(trace.calls),
            "writes": sum(len(call.writes) for call in trace.calls),
            "groups": len({group for call in trace.calls for group in call.group_ids}),
        },
    }
    graph["edges"] = [{"src": src, "kind": kind, "dst": dst} for src, kind, dst in graph["edges"]]
    graph["manifest"] = _manifest(graph, "rdr.v2_graphs.execution_graph_summary@2.1.0")
    return graph


def check_source_link(authoring: dict, execution: dict) -> bool:
    return authoring["final_source_sha256"] == execution["source_sha256"]
