"""ETIQ 2.3.2 native-lineage pilot, isolated from the reviewer experiment."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import multiprocessing
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ETIQ_VERSION = "2.3.2"
OFFICIAL_DEMO_COMMIT = "5bba85283e5d45bb357054ce387bee86c58895ef"
QUALIFICATION_ROOT = Path("runs/v2/qualification-v6-20261111/cells")
OFFICIAL_ENTRY = Path("fixtures/etiq/agentic_unstructured.py")
REPLAY_ENTRY = Path("fixtures/v2/etiq_replay_entry.py")
MATRIX_CELLS = (
    "S01/S0R0", "S01/S1R0", "S01/repaired",
    "R01/S0R1", "R01/repaired",
    "I06/S0R0", "I06/S1R0", "I06/S0R1", "I06/S1R1", "I06/repaired",
)
WRITE_METHODS = {
    ("venmo", "create_payment_request"), ("venmo", "update_payment_request"),
    ("file_system", "create_file"), ("gmail", "reply_to_email"),
    ("gmail", "label_thread"), ("gmail", "mark_thread_read"),
    ("supervisor", "complete_task"),
}
LEAKAGE_DENYLIST = (
    "replay_bundle", "expected_transcript", "expected_actions", "args_sha256",
    "replay_result", "replay_fidelity", "qualification_passed", "position['value']",
    "bundle_sha256", "validation_outcome",
)
SENSITIVE_NAME = re.compile(
    r"token|key|secret|password|credential|authorization|cookie", re.IGNORECASE
)
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
FORBIDDEN_ENV = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
FORBIDDEN_PREFIXES = ("AWS_", "AZURE_", "GOOGLE_", "GCP_", "GITHUB_", "GH_")
DOT_PROJECTION_TIMEOUT_SECONDS = 30.0
REPLAY_API_QUALIFIED_TYPE = "fixtures.v2.etiq_replay_entry.ReplayApiCollection"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _expected_solution_output(source: str, final_response: Any) -> Any:
    """Infer the replay return contract from the frozen solution's final statement."""
    tree = ast.parse(source)
    solution = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "solution"
    )
    final = solution.body[-1]
    return final_response if isinstance(final, ast.Return) and final.value is not None else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_repository_file(path: str | Path, *, suffix: str | None = None) -> Path:
    requested = Path(path)
    if requested.is_absolute():
        raise ValueError("path must be relative to the repository")
    resolved = (REPOSITORY_ROOT / requested).resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("path must stay inside the repository") from exc
    if not resolved.is_file():
        raise ValueError(f"file does not exist: {path}")
    if suffix and resolved.suffix != suffix:
        raise ValueError(f"file must have suffix {suffix}")
    return resolved


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    write_json(temporary, value)
    temporary.replace(path)


def _replace_strings(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_replace_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_strings(item, replacements) for key, item in value.items()}
    return value


def _synthetic_replacements(calls: list[dict[str, Any]]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for call in calls:
        response = call.get("observed_response")
        if call["app"] == "supervisor" and call["api"] == "show_account_passwords":
            for account in response:
                replacements[account["password"]] = f"pilot-password-{account['account_name']}"
        if call["api"] == "login" and isinstance(response, dict):
            replacements[response["access_token"]] = f"pilot-token-{call['app']}"
    return replacements


def build_replay_bundle(cell_relative: Path, source_relative: Path) -> tuple[dict[str, Any], str]:
    cell_path = resolve_repository_file(QUALIFICATION_ROOT / cell_relative, suffix=".json")
    cell = json.loads(cell_path.read_text(encoding="utf-8"))
    if cell.get("artifact_state") != "clean":
        raise ValueError("qualification cell is not a cleanly captured artifact")
    source = cell["trace"]["source"]["workflow.py"]
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    if source_hash != cell["source_sha256"]:
        raise ValueError("qualification source hash differs from embedded source")
    raw_calls = cell["trace"]["calls"]
    replacements = _synthetic_replacements(raw_calls)
    fault_plan = cell.get("fault_plan", {})
    repair_index = cell.get("repair_index")
    calls: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_calls):
        args = _replace_strings(raw["args"], replacements)
        response = _replace_strings(raw["observed_response"], replacements)
        injected_hook = _is_injected_hook(
            fault_plan, repair_index, index, len(raw_calls), raw_calls[-1]["api"]
        )
        item = {
            "index": index, "app": raw["app"], "method": raw["api"],
            "args_sha256": canonical_hash(args), "response": response,
            "injected_hook": injected_hook,
        }
        if injected_hook:
            item["hook_args"] = args
        calls.append(item)
        observed = {key: item[key] for key in ("index", "app", "method", "args_sha256")}
        transcript.append(observed)
        if (raw["app"], raw["api"]) in WRITE_METHODS:
            actions.append(observed)
    bundle = {
        "schema_version": "2.0", "private": True,
        "qualification": {
            "cell": (QUALIFICATION_ROOT / cell_relative).as_posix(),
            "cell_sha256": file_sha256(cell_path),
            "expected_passed": cell["passed"],
            "artifact_state": cell["artifact_state"],
            "fixture_id": cell["fixture_id"],
            "fault_plan_sha256": canonical_hash(fault_plan),
        },
        "workflow_path": source_relative.as_posix(),
        "workflow_sha256": source_hash,
        "calls": calls,
        "expected_transcript": transcript,
        "expected_transcript_sha256": canonical_hash(transcript),
        "expected_actions": actions,
        "expected_actions_sha256": canonical_hash(actions),
        "argument_interventions": _argument_interventions(fault_plan),
        "expected_final_output": _expected_solution_output(source, calls[-1]["response"]),
        "expected_final_output_sha256": canonical_hash(
            _expected_solution_output(source, calls[-1]["response"])
        ),
        "sanitization": "Credentials were replaced with deterministic synthetic pilot values.",
    }
    bundle["bundle_sha256"] = canonical_hash(bundle)
    return bundle, source


def build_frozen_trace_replay_bundle(
    trace: dict[str, Any], source_relative: Path, instance_id: str,
    fault_plan: dict[str, Any] | None = None, repair_index: int | None = None,
) -> tuple[dict[str, Any], str]:
    """Build a private replay contract from one already-frozen experiment trace."""
    source = trace["source"]["workflow.py"]
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    raw_calls = trace["calls"]
    replacements = _synthetic_replacements(raw_calls)
    calls: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_calls):
        args = _replace_strings(raw["args"], replacements)
        response = _replace_strings(raw["observed_response"], replacements)
        injected_hook = _is_injected_hook(
            fault_plan or {}, repair_index, index, len(raw_calls), raw_calls[-1]["api"]
        )
        item = {
            "index": index, "app": raw["app"], "method": raw["api"],
            "args_sha256": canonical_hash(args), "response": response,
            "injected_hook": injected_hook,
        }
        if injected_hook:
            item["hook_args"] = args
        calls.append(item)
        observed = {key: item[key] for key in ("index", "app", "method", "args_sha256")}
        transcript.append(observed)
        if (raw["app"], raw["api"]) in WRITE_METHODS:
            actions.append(observed)
    bundle = {
        "schema_version": "2.1", "private": True,
        "qualification": {
            "cell": f"frozen-build:{instance_id}",
            "cell_sha256": canonical_hash(trace),
            "expected_passed": True,
            "artifact_state": "frozen_trace",
            "fixture_id": trace["task_id"],
            "fault_plan_sha256": canonical_hash(fault_plan or {}),
        },
        "workflow_path": source_relative.as_posix(), "workflow_sha256": source_hash,
        "calls": calls, "expected_transcript": transcript,
        "expected_transcript_sha256": canonical_hash(transcript),
        "expected_actions": actions, "expected_actions_sha256": canonical_hash(actions),
        "argument_interventions": _argument_interventions(fault_plan or {}),
        "expected_final_output": _expected_solution_output(source, calls[-1]["response"]),
        "expected_final_output_sha256": canonical_hash(
            _expected_solution_output(source, calls[-1]["response"])
        ),
        "sanitization": "Credentials were replaced with deterministic synthetic pilot values.",
    }
    bundle["bundle_sha256"] = canonical_hash(bundle)
    return bundle, source


def _argument_interventions(fault_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    interventions: dict[str, dict[str, Any]] = {}
    index = fault_plan.get("index")
    if isinstance(index, int) and isinstance(fault_plan.get("arg"), str):
        interventions[str(index)] = {
            "operation": "set_arg", "arg": fault_plan["arg"], "value": fault_plan.get("value")
        }
    patch = fault_plan.get("patch")
    if isinstance(patch, dict) and isinstance(patch.get("index"), int):
        operation = patch.get("operation")
        if operation == "partial_file":
            interventions[str(patch["index"])] = {"operation": "partial_file", "arg": "content"}
        elif operation == "invalid_token":
            interventions[str(patch["index"])] = {
                "operation": "set_arg", "arg": patch.get("arg", "access_token"),
                "value": "invalid-local-token",
            }
    return interventions


def _is_injected_hook(
    fault_plan: dict[str, Any], repair_index: int | None, index: int,
    call_count: int, final_api: str,
) -> bool:
    repair_hook = bool(
        repair_index is not None and repair_index <= index < call_count - 1
        and final_api == "complete_task"
    )
    patch = fault_plan.get("patch")
    runtime_hook = bool(
        isinstance(patch, dict) and patch.get("operation") == "concurrent_update"
        and patch.get("index") == index
    )
    return repair_hook or runtime_hook


def export_replay_cell(cell_relative: Path, bundle_path: Path, source_path: Path) -> dict[str, Any]:
    if bundle_path.exists() or source_path.exists():
        raise ValueError("refusing to overwrite replay exchange files")
    source_relative = source_path.resolve().relative_to(REPOSITORY_ROOT.resolve())
    bundle, source = build_replay_bundle(cell_relative, source_relative)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source, encoding="utf-8")
    if file_sha256(source_path) != bundle["workflow_sha256"]:
        raise ValueError("exported source hash differs")
    write_json(bundle_path, bundle)
    source_path.chmod(0o400)
    bundle_path.chmod(0o400)
    return bundle


def validate_replay_bundle(path: Path) -> dict[str, Any]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    recorded = bundle.pop("bundle_sha256", None)
    if recorded != canonical_hash(bundle):
        raise ValueError("replay bundle hash does not match content")
    bundle["bundle_sha256"] = recorded
    if bundle.get("private") is not True:
        raise ValueError("replay bundle must be private")
    source = resolve_repository_file(bundle["workflow_path"], suffix=".py")
    if file_sha256(source) != bundle["workflow_sha256"]:
        raise ValueError("replay bundle source binding is stale")
    transcript = [
        {key: call[key] for key in ("index", "app", "method", "args_sha256")}
        for call in bundle["calls"]
    ]
    if transcript != bundle["expected_transcript"]:
        raise ValueError("replay transcript contract is inconsistent")
    return bundle


def _state_names(state: Any) -> list[str]:
    names = getattr(state, "names", None)
    if names is None:
        name = getattr(state, "state_name", None)
        return [str(name)] if name else []
    return [names] if isinstance(names, str) else sorted(str(name) for name in names)


def _node_source(node: Any) -> str | None:
    try:
        return str(node.as_string())
    except Exception:
        return None


def _node_scope(node: Any) -> str | None:
    try:
        scope = node.scope()
        return getattr(scope, "name", None) or type(scope).__name__
    except Exception:
        return None


def source_index(source_specs: list[dict[str, str]]) -> dict[str, Any]:
    import astroid

    by_line_source: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    by_expression: dict[str, list[dict[str, str]]] = defaultdict(list)
    for spec in source_specs:
        source = resolve_repository_file(spec["path"], suffix=".py").read_text(encoding="utf-8")
        module = astroid.parse(source, path=spec["path"])
        for node in module.nodes_of_class(astroid.nodes.NodeNG):
            try:
                expression = node.as_string()
            except Exception:
                continue
            record = {**spec, "scope": _node_scope(node) or ""}
            line = getattr(node, "lineno", None)
            if line:
                by_line_source[(line, expression)].append(record)
            by_expression[expression].append(record)
    return {"by_line_source": by_line_source, "by_expression": by_expression}


def classify_origin(line: int | None, expression: str | None, scope: str | None,
                    index: dict[str, Any], *, dependency: bool = False) -> dict[str, Any]:
    candidates = list(index["by_line_source"].get((line, expression), [])) if line and expression else []
    if not candidates and expression:
        candidates = list(index["by_expression"].get(expression, []))
        scoped = [item for item in candidates if scope and item["scope"] == scope]
        if scoped:
            candidates = scoped
    unique = {(item["role"], item["path"], item["sha256"]): item for item in candidates}
    if len(unique) == 1:
        item = next(iter(unique.values()))
        return {"classification": item["role"], "path": item["path"],
                "source_sha256": item["sha256"], "ambiguous": False}
    if dependency:
        return {"classification": "dependency", "path": None, "source_sha256": None,
                "ambiguous": False}
    return {"classification": "unknown", "path": None, "source_sha256": None,
            "ambiguous": len(unique) > 1}


def _safe_value(value: Any, names: list[str], depth: int = 0) -> Any:
    if any(SENSITIVE_NAME.search(name) for name in names):
        return "<redacted:sensitive-state>"
    if depth > 8:
        return {"__type__": type(value).__name__, "truncated": True}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return JWT.sub("<redacted:token>", value)
    if isinstance(value, dict):
        return {
            str(key): "<redacted:sensitive-key>" if SENSITIVE_NAME.search(str(key))
            else _safe_value(item, [str(key)], depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, names, depth + 1) for item in value]
    if isinstance(value, set):
        return sorted((_safe_value(item, names, depth + 1) for item in value), key=repr)
    if hasattr(value, "to_dict") and hasattr(value, "shape"):
        return {"__type__": type(value).__name__, "shape": list(value.shape),
                "columns": [str(item) for item in getattr(value, "columns", [])]}
    return {"__type__": f"{type(value).__module__}.{type(value).__qualname__}"}


def _structure(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"python_type": type(value).__name__}
    if isinstance(value, dict):
        result.update({"json_type": "object", "keys": sorted(str(key) for key in value), "length": len(value)})
    elif isinstance(value, (list, tuple, set, str)):
        result.update({"json_type": "string" if isinstance(value, str) else "array", "length": len(value)})
    elif value is None:
        result["json_type"] = "null"
    elif isinstance(value, bool):
        result["json_type"] = "boolean"
    elif isinstance(value, (int, float)):
        result["json_type"] = "number"
    if hasattr(value, "shape"):
        result["shape"] = list(value.shape)
    return result


def build_state_inventory(states: list[Any], index: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    records = []
    native_map: dict[str, dict[str, Any]] = {}
    for position, state in enumerate(states):
        node = getattr(state, "node", None)
        names = _state_names(state)
        expression = _node_source(node) if node is not None else None
        line = getattr(state, "line_no", None)
        scope = _node_scope(node) if node is not None else None
        origin = classify_origin(line, expression, scope, index,
                                 dependency=bool(getattr(state, "library_used", None)))
        safe = _safe_value(getattr(state, "value", None), names)
        native_id = str(getattr(state, "state_id", "")).replace("-", "")
        native_node = f"node_{native_id}" if native_id else None
        record = {
            "id": f"state-{position:05d}", "names": names, "state_type": type(state).__name__,
            "origin": origin, "source_line": line, "source_expression": expression,
            "scope": scope, "value_sha256": canonical_hash(safe),
            "hash_basis": "redacted_canonical_json", "structure": _structure(getattr(state, "value", None)),
            "sanitized_sample": None, "native_node": native_node,
        }
        records.append(record)
        if native_node:
            native_map[native_node] = record
    return {
        "schema_version": "1.0", "private": True, "raw_values_stored": False,
        "state_count": len(records), "states": records,
    }, native_map


def _dot_value(value: Any) -> str:
    text = str(value)
    if len(text) >= 2 and text[0] == text[-1] == '"':
        try:
            return ast.literal_eval(text)
        except Exception:
            return text[1:-1]
    return text


def _scope_label(value: str) -> str:
    value = value.removeprefix("cluster_")
    return re.sub(r",(?:[0-9a-f]{16}|[0-9a-f-]{36})$", "", value)


def parse_dot_projection(dot: str, native_state_map: dict[str, dict[str, Any]],
                         index: dict[str, Any], *, allow_empty: bool = False) -> dict[str, Any]:
    import pydot

    graphs = pydot.graph_from_dot_data(dot)
    if not graphs or len(graphs) != 1:
        raise ValueError("DOT must contain exactly one graph")
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def visit(graph: Any, scopes: list[str]) -> None:
        graph_label = _dot_value(graph.get_label()) if graph.get_label() else None
        current = scopes + ([graph_label] if graph_label else [])
        for node in graph.get_nodes():
            name = _dot_value(node.get_name())
            if name in {"node", "edge", "graph", "\n", ""}:
                continue
            attrs = {str(key): _dot_value(value) for key, value in node.get_attributes().items()}
            label = attrs.get("label", name)
            state_record = native_state_map.get(name)
            if state_record:
                origin = state_record["origin"]
                state_id = state_record["id"]
            else:
                origin = classify_origin(None, label, current[-1] if current else None, index)
                state_id = None
            nodes[name] = {
                "native_name": name, "label": label, "attributes": attrs,
                "clusters": [_scope_label(item) for item in current],
                "origin": origin, "state_id": state_id,
                "occurrence_ordinal": len(nodes),
            }
        for edge in graph.get_edges():
            edges.append({
                "source_native": _dot_value(edge.get_source()),
                "target_native": _dot_value(edge.get_destination()),
                "attributes": {str(key): _dot_value(value) for key, value in edge.get_attributes().items()},
                "occurrence_ordinal": len(edges),
            })
        for subgraph in graph.get_subgraphs():
            visit(subgraph, current)

    visit(graphs[0], [])
    if not nodes and not edges and allow_empty:
        return {
            "schema_version": "1.0", "artifact_kind": "etiq_dot_projection",
            "native_format": "dot", "nodes": [], "edges": [],
            "node_count": 0, "edge_count": 0,
            "semantic_sha256": canonical_hash({"node_colors": [], "edges": []}),
        }
    if not nodes or not edges:
        raise ValueError("DOT graph must contain non-zero nodes and edges")
    unresolved = sorted({endpoint for edge in edges for endpoint in (edge["source_native"], edge["target_native"])
                         if endpoint not in nodes})
    if unresolved:
        raise ValueError(f"DOT edge endpoints are unresolved: {unresolved[:5]}")

    base = {
        name: canonical_hash({key: value for key, value in node.items()
                              if key not in {"native_name", "state_id", "occurrence_ordinal"}})
        for name, node in nodes.items()
    }
    colors = base
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge["source_native"]].append(edge["target_native"])
        incoming[edge["target_native"]].append(edge["source_native"])
    for _ in range(8):
        colors = {
            name: canonical_hash({
                "self": base[name],
                "in": sorted(colors[item] for item in incoming[name]),
                "out": sorted(colors[item] for item in outgoing[name]),
            })
            for name in nodes
        }
    order = sorted(nodes, key=lambda name: (colors[name], base[name], name))
    stable = {name: f"node-{position:05d}" for position, name in enumerate(order)}
    projected_nodes = []
    for name in order:
        item = {key: value for key, value in nodes[name].items() if key != "native_name"}
        item["id"] = stable[name]
        item["semantic_color"] = colors[name]
        projected_nodes.append(item)
    projected_edges = sorted(
        ({"source": stable[edge["source_native"]], "target": stable[edge["target_native"]],
          "attributes": edge["attributes"],
          "occurrence_ordinal": edge["occurrence_ordinal"]} for edge in edges),
        key=lambda item: (item["source"], item["target"], canonical_json(item["attributes"])),
    )
    semantic = {
        "node_colors": sorted(Counter(colors.values()).items()),
        "edges": sorted(
            ((colors[e["source_native"]], colors[e["target_native"]], e["attributes"]) for e in edges),
            key=canonical_json,
        ),
    }
    return {
        "schema_version": "1.0", "artifact_kind": "etiq_dot_projection",
        "native_format": "dot", "nodes": projected_nodes, "edges": projected_edges,
        "node_count": len(projected_nodes), "edge_count": len(projected_edges),
        "semantic_sha256": canonical_hash(semantic),
    }


_DOT_ID = r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*'
_DOT_NODE = re.compile(rf"^\s*(?P<id>{_DOT_ID})\s+\[(?P<attrs>.*)\];\s*$")
_DOT_EDGE = re.compile(
    rf"^\s*(?P<src>{_DOT_ID})\s*->\s*(?P<dst>{_DOT_ID})"
    r"(?:\s+\[(?P<attrs>.*)\])?;\s*$"
)
_DOT_SUBGRAPH = re.compile(rf"^\s*subgraph\s+(?P<id>{_DOT_ID})\s*\{{\s*$")
_DOT_ATTR = re.compile(r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>"(?:\\.|[^"\\])*"|[^,\]]+)')


def _fast_dot_id(value: str) -> str:
    return _dot_value(value.strip())


def _fast_dot_attrs(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    return {
        match.group("key"): _dot_value(match.group("value").strip())
        for match in _DOT_ATTR.finditer(value)
    }


def _fast_dot_statements(dot: str) -> list[str]:
    """Split DOT outside quoted strings so compact and multiline exports agree."""
    statements: list[str] = []
    buffer: list[str] = []
    quoted = escaped = False
    for character in dot:
        buffer.append(character)
        if escaped:
            escaped = False
            continue
        if character == "\\" and quoted:
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if character in "{};":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return statements


def parse_etiq_dot_projection(dot: str, native_state_map: dict[str, dict[str, Any]],
                              index: dict[str, Any], *, allow_empty: bool = False) -> dict[str, Any]:
    """Parse the constrained DOT emitted by ETIQ without Graphviz or pydot."""
    if not dot.lstrip().startswith("digraph"):
        raise ValueError("ETIQ DOT must start with digraph")
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    scopes: list[dict[str, str]] = []
    root_open = False
    for line in _fast_dot_statements(dot):
        stripped = line.strip()
        if not stripped or stripped in {"compound=true;"}:
            continue
        if stripped.startswith("digraph") and stripped.endswith("{"):
            if root_open:
                raise ValueError("ETIQ DOT contains multiple root graphs")
            root_open = True
            continue
        subgraph = _DOT_SUBGRAPH.match(line)
        if subgraph:
            name = _fast_dot_id(subgraph.group("id"))
            scopes.append({"name": name, "label": _scope_label(name)})
            continue
        if stripped.startswith("label=") and stripped.endswith(";") and scopes:
            scopes[-1]["label"] = _fast_dot_attrs(stripped[:-1]).get("label", scopes[-1]["label"])
            continue
        if stripped == "}":
            if scopes:
                scopes.pop()
            elif root_open:
                root_open = False
            else:
                raise ValueError("ETIQ DOT contains an unmatched closing brace")
            continue
        edge = _DOT_EDGE.match(line)
        if edge:
            edges.append({
                "source_native": _fast_dot_id(edge.group("src")),
                "target_native": _fast_dot_id(edge.group("dst")),
                "attributes": _fast_dot_attrs(edge.group("attrs")),
                "occurrence_ordinal": len(edges),
            })
            continue
        node = _DOT_NODE.match(line)
        if node:
            name = _fast_dot_id(node.group("id"))
            if name in {"node", "edge", "graph"}:
                continue
            attrs = _fast_dot_attrs(node.group("attrs"))
            label = attrs.get("label", name)
            state_record = native_state_map.get(name)
            if state_record:
                origin = state_record["origin"]
                state_id = state_record["id"]
            else:
                origin = classify_origin(
                    None, label, scopes[-1]["label"] if scopes else None, index
                )
                state_id = None
            nodes[name] = {
                "native_name": name, "label": label, "attributes": attrs,
                "clusters": [scope["label"] for scope in scopes],
                "origin": origin, "state_id": state_id,
                "occurrence_ordinal": len(nodes),
            }
            continue
        if stripped not in {"bgcolor=\"#50E6FF\";"}:
            raise ValueError(f"unsupported ETIQ DOT statement: {stripped[:120]}")
    if scopes or root_open:
        raise ValueError("ETIQ DOT braces are unbalanced")
    if not nodes and not edges and allow_empty:
        return {
            "schema_version": "1.0", "artifact_kind": "etiq_dot_projection",
            "native_format": "dot", "nodes": [], "edges": [],
            "node_count": 0, "edge_count": 0,
            "semantic_sha256": canonical_hash({"node_colors": [], "edges": []}),
        }
    if not nodes or not edges:
        raise ValueError("ETIQ DOT graph must contain non-zero nodes and edges")
    unresolved = sorted({
        endpoint for edge in edges
        for endpoint in (edge["source_native"], edge["target_native"])
        if endpoint not in nodes
    })
    if unresolved:
        raise ValueError(f"ETIQ DOT edge endpoints are unresolved: {unresolved[:5]}")

    base = {
        name: canonical_hash({key: value for key, value in node.items()
                              if key not in {"native_name", "state_id", "occurrence_ordinal"}})
        for name, node in nodes.items()
    }
    colors = base
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge["source_native"]].append(edge["target_native"])
        incoming[edge["target_native"]].append(edge["source_native"])
    for _ in range(8):
        colors = {
            name: canonical_hash({
                "self": base[name],
                "in": sorted(colors[item] for item in incoming[name]),
                "out": sorted(colors[item] for item in outgoing[name]),
            })
            for name in nodes
        }
    order = sorted(nodes, key=lambda name: (colors[name], base[name], name))
    stable = {name: f"node-{position:05d}" for position, name in enumerate(order)}
    projected_nodes = []
    for name in order:
        item = {key: value for key, value in nodes[name].items() if key != "native_name"}
        item["id"] = stable[name]
        item["semantic_color"] = colors[name]
        projected_nodes.append(item)
    projected_edges = sorted(
        ({"source": stable[edge["source_native"]],
          "target": stable[edge["target_native"]],
          "attributes": edge["attributes"],
          "occurrence_ordinal": edge["occurrence_ordinal"]} for edge in edges),
        key=lambda item: (item["source"], item["target"], canonical_json(item["attributes"])),
    )
    semantic = {
        "node_colors": sorted(Counter(colors.values()).items()),
        "edges": sorted(
            ((colors[edge["source_native"]], colors[edge["target_native"]], edge["attributes"])
             for edge in edges),
            key=canonical_json,
        ),
    }
    return {
        "schema_version": "1.0", "artifact_kind": "etiq_dot_projection",
        "native_format": "dot", "nodes": projected_nodes, "edges": projected_edges,
        "node_count": len(projected_nodes), "edge_count": len(projected_edges),
        "semantic_sha256": canonical_hash(semantic),
    }


def workflow_projection(dot_projection: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    workflow_nodes = [node for node in dot_projection["nodes"]
                      if node["origin"]["classification"] == "frozen_workflow"]
    included = {node["id"] for node in workflow_nodes}
    edges = [edge for edge in dot_projection["edges"]
             if edge["source"] in included and edge["target"] in included]
    projection = {
        "schema_version": "1.0", "artifact_kind": "workflow_lineage_projection",
        "derived_from": "native_etiq_dot", "private": True,
        "boundary_policy": "Only nodes unambiguously attributable to frozen_workflow are retained.",
        "nodes": workflow_nodes, "edges": edges,
    }
    encoded = canonical_json(projection).lower()
    leaks = sorted(item for item in LEAKAGE_DENYLIST if item.lower() in encoded)
    by_id = {node["id"]: node for node in workflow_nodes}
    action_ids = {node["id"] for node in workflow_nodes if any(
        method in node["label"] for _, method in WRITE_METHODS
    )}
    relevant_ids = {node["id"] for node in workflow_nodes if any(
        name in node["label"] for name in ("payload", "matching_users", "result", "request_id", "receipt_path")
    )}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
    paths = []
    for start in sorted(relevant_ids):
        queue = [(start, [start])]
        seen = {start}
        while queue:
            current, path = queue.pop(0)
            if current in action_ids and current != start:
                paths.append([{"id": item, "label": by_id[item]["label"],
                               "origin": by_id[item]["origin"]["classification"]} for item in path])
                break
            for target in adjacency[current]:
                if target not in seen:
                    seen.add(target)
                    queue.append((target, path + [target]))
    adjacent_unknown = 0
    all_origins = {node["id"]: node["origin"]["classification"] for node in dot_projection["nodes"]}
    for edge in dot_projection["edges"]:
        pair = {all_origins[edge["source"]], all_origins[edge["target"]]}
        if "frozen_workflow" in pair and "unknown" in pair:
            adjacent_unknown += 1
    assessment = {
        "leakage_matches": leaks, "action_node_count": len(action_ids),
        "fault_relevant_node_count": len(relevant_ids), "fault_to_action_paths": paths,
        "ambiguous_boundary_edge_count": adjacent_unknown,
        "eligible": not leaks and bool(paths) and adjacent_unknown == 0,
    }
    return projection, assessment


def _dot_projection_worker(dot_path: Path, output_dir: Path,
                           native_state_map: dict[str, dict[str, Any]], index: dict[str, Any],
                           parser: Any) -> None:
    try:
        projection = parser(dot_path.read_text(encoding="utf-8"), native_state_map, index,
                            allow_empty=True)
        if projection["node_count"] == 0 and projection["edge_count"] == 0:
            (output_dir / ".dot-projection-empty").write_text("empty\n", encoding="utf-8")
            return
        workflow, assessment = workflow_projection(projection)
        projection_tmp = output_dir / ".etiq_dot_projection.json.tmp"
        workflow_tmp = output_dir / ".workflow-lineage-projection.json.tmp"
        write_json(projection_tmp, projection)
        write_json(workflow_tmp, workflow)
        projection_tmp.replace(output_dir / "etiq_dot_projection.json")
        workflow_tmp.replace(output_dir / "workflow-lineage-projection.json")
        write_json_atomic(output_dir / ".dot-projection-assessment.json", assessment)
    except Exception as exc:
        error = _export_error(exc, "dot_projection")
        error["status"] = "failed"
        write_json_atomic(output_dir / "dot-projection-error.json", error)


def project_dot_bounded(dot_path: Path, output_dir: Path,
                        native_state_map: dict[str, dict[str, Any]], index: dict[str, Any], *,
                        timeout_seconds: float = DOT_PROJECTION_TIMEOUT_SECONDS,
                        parser: Any = parse_etiq_dot_projection) -> dict[str, Any]:
    context = multiprocessing.get_context("fork")
    process = context.Process(
        target=_dot_projection_worker,
        args=(dot_path, output_dir, native_state_map, index, parser),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        for name in (
            ".etiq_dot_projection.json.tmp", ".workflow-lineage-projection.json.tmp",
            "etiq_dot_projection.json", "workflow-lineage-projection.json",
            ".dot-projection-assessment.json", ".dot-projection-empty",
        ):
            (output_dir / name).unlink(missing_ok=True)
        error = {
            "schema_version": "1.0", "stage": "dot_projection", "status": "timed_out",
            "timeout_seconds": timeout_seconds, "etiq_copilot_version": ETIQ_VERSION,
            "exception_type": "TimeoutExpired",
            "message": f"DOT projection exceeded {timeout_seconds:g} seconds",
            "etiq_stack_frames": [],
        }
        write_json(output_dir / "dot-projection-error.json", error)
        return {"status": "timed_out", "dot_projection": None,
                "projection_assessment": None}
    if process.exitcode != 0 and not (output_dir / "dot-projection-error.json").exists():
        error = {
            "schema_version": "1.0", "stage": "dot_projection", "status": "failed",
            "etiq_copilot_version": ETIQ_VERSION, "exception_type": "ChildProcessError",
            "message": f"DOT projection process exited {process.exitcode}",
            "etiq_stack_frames": [],
        }
        write_json(output_dir / "dot-projection-error.json", error)
    if (output_dir / ".dot-projection-empty").exists():
        (output_dir / ".dot-projection-empty").unlink()
        return {"status": "empty", "dot_projection": None,
                "projection_assessment": None}
    if (output_dir / "dot-projection-error.json").exists():
        return {"status": "failed", "dot_projection": None,
                "projection_assessment": None}
    projection = json.loads((output_dir / "etiq_dot_projection.json").read_text(encoding="utf-8"))
    assessment_path = output_dir / ".dot-projection-assessment.json"
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    assessment_path.unlink()
    return {"status": "completed", "dot_projection": projection,
            "projection_assessment": assessment}


def _export_error(exc: Exception, stage: str) -> dict[str, Any]:
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__):
        if "etiq_copilot" in frame.filename:
            marker = frame.filename.split("site-packages/", 1)[-1]
            frames.append({"file": marker, "line": frame.lineno, "function": frame.name})
    return {"schema_version": "1.0", "stage": stage, "exception_type": type(exc).__name__,
            "message": str(exc), "etiq_copilot_version": ETIQ_VERSION, "etiq_stack_frames": frames}


def export_native_graph(scan: Any, output_dir: Path, native_state_map: dict[str, dict[str, Any]],
                        index: dict[str, Any], *,
                        projection_timeout_seconds: float = DOT_PROJECTION_TIMEOUT_SECONDS,
                        projection_parser: Any = parse_etiq_dot_projection) -> dict[str, Any]:
    warnings = []
    empty_json_path = None
    try:
        graph = scan.create_full_lineage_graph(graph_format="json")
        parsed = json.loads(graph) if isinstance(graph, str) else graph
        if not isinstance(parsed, dict):
            raise ValueError("ETIQ JSON lineage must be an object")
        native_path = output_dir / "lineage.json"
        write_json(native_path, parsed)
        native_hash = file_sha256(native_path)
        if parsed.get("objects") and parsed.get("edges"):
            return {
                "native_export_status": "json", "native_path": native_path,
                "native_sha256": native_hash, "projection_status": "not_applicable",
                "dot_projection": None, "projection_assessment": None,
                "projection_error": None, "warnings": warnings,
            }
        empty_json_path = native_path
    except Exception as json_exc:
        error_path = output_dir / "json-export-error.json"
        write_json(error_path, _export_error(json_exc, "json_export"))
        warnings.append({"stage": "json_export", "artifact": error_path.name,
                         "exception_type": type(json_exc).__name__})
    try:
        dot = scan.create_full_lineage_graph(graph_format="dot")
        if not isinstance(dot, str):
            raise ValueError("ETIQ DOT lineage must be text")
        native_path = output_dir / "lineage.dot"
        native_path.write_text(dot, encoding="utf-8")
        native_hash = file_sha256(native_path)
        projected = project_dot_bounded(
            native_path, output_dir, native_state_map, index,
            timeout_seconds=projection_timeout_seconds, parser=projection_parser,
        )
        if projected["status"] == "empty":
            return {
                "native_export_status": "empty", "native_path": native_path,
                "native_sha256": native_hash, "projection_status": "not_applicable",
                "dot_projection": None, "projection_assessment": None,
                "projection_error": None, "warnings": warnings,
            }
        projection_error = None
        if projected["status"] in {"failed", "timed_out"}:
            projection_error = {
                "path": "dot-projection-error.json",
                "sha256": file_sha256(output_dir / "dot-projection-error.json"),
            }
        return {
            "native_export_status": "dot", "native_path": native_path,
            "native_sha256": native_hash, "projection_status": projected["status"],
            "dot_projection": projected["dot_projection"],
            "projection_assessment": projected["projection_assessment"],
            "projection_error": projection_error, "warnings": warnings,
        }
    except Exception as dot_exc:
        dot_error_path = output_dir / "dot-export-error.json"
        write_json(dot_error_path, _export_error(dot_exc, "dot_export"))
        warnings.append({"stage": "dot_export", "artifact": dot_error_path.name,
                         "exception_type": type(dot_exc).__name__})
        if empty_json_path:
            return {
                "native_export_status": "empty", "native_path": empty_json_path,
                "native_sha256": file_sha256(empty_json_path),
                "projection_status": "not_applicable", "dot_projection": None,
                "projection_assessment": None, "projection_error": None,
                "warnings": warnings,
            }
        return {
            "native_export_status": "failed", "native_path": None,
            "native_sha256": None, "projection_status": "not_applicable",
            "dot_projection": None, "projection_assessment": None,
            "projection_error": None, "warnings": warnings,
        }


def _source_specs(entry_relative: Path, bundle_path: Path | None) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    entry = resolve_repository_file(entry_relative, suffix=".py")
    specs = [{"role": "replay_harness" if bundle_path else "frozen_workflow",
              "path": entry_relative.as_posix(), "sha256": file_sha256(entry)}]
    bundle = None
    if bundle_path:
        bundle = validate_replay_bundle(bundle_path)
        specs.append({"role": "frozen_workflow", "path": bundle["workflow_path"],
                      "sha256": bundle["workflow_sha256"]})
    return specs, bundle


def build_replay_scan(bundle: dict[str, Any], replay_result_path: Path) -> tuple[
    str, dict[str, Any], Any, dict[str, Any]
]:
    from fixtures.v2.etiq_replay_entry import write_replay_result

    workflow = resolve_repository_file(bundle["workflow_path"], suffix=".py")
    source = workflow.read_text(encoding="utf-8")
    if hashlib.sha256(source.encode()).hexdigest() != bundle["workflow_sha256"]:
        raise ValueError("replay workflow source binding is stale")
    transcript: list[dict[str, Any]] = []
    scan_globals = {
        "__etiq_replay_bundle__": bundle,
        "__etiq_replay_transcript__": transcript,
    }

    invocation = (
        "\n# ETIQ_REPLAY_INVOCATION: harness-only; frozen workflow ends above.\n"
        "from fixtures.v2.etiq_replay_entry import ReplayApiCollection\n"
        "__etiq_replay_apis__ = ReplayApiCollection(\n"
        "    __etiq_replay_bundle__, __etiq_replay_transcript__\n"
        ")\n"
        "__etiq_final_output__ = solution(__etiq_replay_apis__, None)\n"
        "__etiq_replay_apis__.assert_complete()\n"
    )
    program = source + ("" if source.endswith("\n") else "\n") + invocation

    def finalize() -> None:
        if "__etiq_final_output__" not in scan_globals:
            raise RuntimeError("ETIQ did not complete the replay invocation")
        write_replay_result(
            replay_result_path, bundle, transcript, scan_globals["__etiq_final_output__"]
        )

    metadata = {
        "path": bundle["workflow_path"], "sha256": bundle["workflow_sha256"],
        "frozen_source_bytes": len(source.encode()),
        "frozen_source_lines": len(source.splitlines()),
        "invocation_start_line": len(source.splitlines()) + 2,
        "invocation_role": "replay_harness",
    }
    return program, scan_globals, finalize, metadata


def _replay_fidelity(bundle: dict[str, Any], replay_result_path: Path) -> dict[str, Any]:
    replay = json.loads(replay_result_path.read_text(encoding="utf-8"))
    actions = [item for item in replay["transcript"] if (item["app"], item["method"]) in WRITE_METHODS]
    checks = {
        "workflow_source": replay["workflow_sha256"] == bundle["workflow_sha256"],
        "transcript": replay["transcript"] == bundle["expected_transcript"],
        "outgoing_actions": actions == bundle["expected_actions"],
        "final_output": replay["final_output"] == bundle["expected_final_output"],
        "qualification_label_bound": isinstance(bundle["qualification"]["expected_passed"], bool),
    }
    return {
        "checks": checks, "passed": all(checks.values()),
        "expected_qualification_passed": bundle["qualification"]["expected_passed"],
        "call_count": len(replay["transcript"]),
        "transcript_sha256": replay["transcript_sha256"],
        "actions_sha256": canonical_hash(actions),
        "final_output_sha256": replay["final_output_sha256"],
    }


def install_network_denial() -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise PermissionError("ETIQ pilot worker network access is disabled")

    socket.create_connection = denied  # type: ignore[assignment]
    original_socket = socket.socket

    class DeniedSocket(original_socket):
        def connect(self, address: Any) -> None:
            del address
            raise PermissionError("ETIQ pilot worker network access is disabled")

        def connect_ex(self, address: Any) -> int:
            del address
            raise PermissionError("ETIQ pilot worker network access is disabled")

    socket.socket = DeniedSocket  # type: ignore[assignment,misc]


def network_denial_probe() -> bool:
    try:
        socket.create_connection(("192.0.2.1", 9), timeout=0.01)
    except PermissionError:
        return True
    return False


def load_debugger_scanner() -> Any:
    from etiq_copilot.engine.implementations.scanner import DebuggerCodeScanner

    return DebuggerCodeScanner


def assess_workflow_only_eligibility(
    has_bundle: bool, native_status: str, projection_status: str,
    fidelity: dict[str, Any] | None, projection_assessment: dict[str, Any] | None,
) -> tuple[str, str]:
    if not has_bundle:
        return "not_assessed", "official control is not an experimental arm"
    if native_status == "json":
        return "not_assessed", "native JSON projection and origin assessment are not implemented"
    if native_status == "empty":
        return "not_eligible", "scanner completed but native lineage contains no fault-relevant states or edges"
    if (native_status == "dot" and projection_status == "completed" and fidelity
            and fidelity["passed"] and projection_assessment and projection_assessment["eligible"]):
        return "eligible", "native DOT and workflow projection satisfy pilot eligibility checks"
    return "not_eligible", "native lineage could not be projected into an eligible workflow-only arm"


def scan_entry(entry_relative: Path, output_dir: Path, *, bundle_path: Path | None = None,
               replay_result_path: Path | None = None) -> dict[str, Any]:
    if os.environ.get("ETIQ_NETWORK_DISABLED") != "1":
        raise RuntimeError("worker network denial was not requested")
    install_network_denial()
    if not network_denial_probe():
        raise RuntimeError("worker network denial probe failed")
    if importlib.metadata.version("etiq-copilot") != ETIQ_VERSION:
        raise RuntimeError("wrong etiq-copilot version")
    DebuggerCodeScanner = load_debugger_scanner()
    specs, bundle = _source_specs(entry_relative, bundle_path)
    index_specs = [spec for spec in specs if spec["role"] == "frozen_workflow"]
    index = source_index(index_specs)
    entry = resolve_repository_file(entry_relative, suffix=".py")
    if bundle:
        if replay_result_path is None:
            raise ValueError("replay result path is required with a replay bundle")
        program, scan_globals, finalize_replay, scan_source = build_replay_scan(
            bundle, replay_result_path
        )
        scan = DebuggerCodeScanner().scan_code(code_str=program, scan_globals=scan_globals)
        if not scan.scan_errors:
            finalize_replay()
    else:
        scan = DebuggerCodeScanner().scan_code(code_str=entry.read_text(encoding="utf-8"))
        scan_source = {
            "path": entry_relative.as_posix(), "sha256": file_sha256(entry),
            "frozen_source_bytes": entry.stat().st_size,
            "frozen_source_lines": len(entry.read_text(encoding="utf-8").splitlines()),
            "invocation_start_line": None, "invocation_role": None,
        }
    scan_errors = [] if not scan.scan_errors else [{"type": type(scan.scan_errors).__name__,
                                                     "message": str(scan.scan_errors)}]
    groups = {
        "dataframes": list(scan.get_dataframes() or []), "models": list(scan.get_models() or []),
        "agents": list(scan.get_agent_states() or []),
        "unstructured": list(scan.get_unstructured_states() or []),
    }
    states = groups["dataframes"] + groups["models"] + groups["agents"] + groups["unstructured"]
    inventory, native_state_map = build_state_inventory(states, index)
    output_dir.mkdir(parents=True, exist_ok=False)
    inventory_path = output_dir / "state-inventory.json"
    write_json(inventory_path, inventory)

    exported = export_native_graph(scan, output_dir, native_state_map, index)
    export_warnings = exported["warnings"]
    native_status = exported["native_export_status"]
    projection_status = exported["projection_status"]
    native_path = exported["native_path"]
    dot_projection = exported["dot_projection"]
    projection_assessment = exported["projection_assessment"]
    native_hash = exported["native_sha256"]
    fidelity = (
        _replay_fidelity(bundle, replay_result_path)
        if bundle and replay_result_path and replay_result_path.is_file() else None
    )
    state_count = sum(len(group) for group in groups.values())
    if scan_errors:
        capture_status = "failed"
    elif state_count:
        capture_status = "completed_with_states"
    else:
        capture_status = "completed_empty"
    capture_warnings = [] if state_count else [
        "The scanner completed normally but found no objects matching permitted capture types."
    ]
    workflow_eligibility, workflow_reason = assess_workflow_only_eligibility(
        bundle is not None, native_status, projection_status, fidelity, projection_assessment
    )
    completed = capture_status != "failed" and native_status != "failed"
    result = {
        "schema_version": "3.0", "status": "completed" if completed else "failed",
        "capture_status": capture_status, "native_export_status": native_status,
        "projection_status": projection_status,
        "workflow_only_eligibility": workflow_eligibility,
        "workflow_only_eligibility_reason": workflow_reason,
        "composite_eligibility": "not_assessed",
        "composite_eligibility_reason": "requires deterministic repeatability and a verified cross-layer path",
        "scan_errors": scan_errors,
        "capture_warnings": capture_warnings,
        "export_warnings": export_warnings, "etiq_copilot_version": ETIQ_VERSION,
        "producer": {"name": "etiq-copilot", "version": ETIQ_VERSION},
        "entry_file": {"path": entry_relative.as_posix(), "sha256": file_sha256(entry)},
        "scan_source": scan_source,
        "source_files": specs, "source_workflow_sha256": bundle["workflow_sha256"] if bundle else file_sha256(entry),
        "native_graph": {"format": native_path.suffix.removeprefix(".") if native_path else None,
                         "path": native_path.name if native_path else None, "sha256": native_hash},
        "dot_projection": {"path": "etiq_dot_projection.json", "sha256": file_sha256(output_dir / "etiq_dot_projection.json"),
                           "semantic_sha256": dot_projection["semantic_sha256"]} if dot_projection else None,
        "workflow_projection": {"path": "workflow-lineage-projection.json",
                                "sha256": file_sha256(output_dir / "workflow-lineage-projection.json"),
                                "assessment": projection_assessment} if dot_projection else None,
        "projection_error": exported["projection_error"],
        "state_inventory": {"path": inventory_path.name, "sha256": file_sha256(inventory_path)},
        "captured_objects": {
            "dataframes": sorted(str(name) for name in scan.list_dataframes()),
            "models": sorted(str(name) for name in scan.list_models()),
            "agents": sorted(str(name) for name in scan.list_agents()),
            "unstructured": sorted({name for state in groups["unstructured"] for name in _state_names(state)}),
        },
        "counts": {key: len(value) for key, value in groups.items()},
        "replay_fidelity": fidelity,
        "isolation": {"environment": "allowlist", "network": "python_socket_denial",
                      "network_probe_passed": True},
        "limitations": [
            "Raw state values are not stored.",
            "DOT projection is derived; lineage.dot remains the authoritative native artifact.",
            "Python socket denial is not an OS firewall for arbitrary child executables.",
        ],
    }
    write_json(output_dir / "scan-result.json", result)
    return result


def validate_scan_result(output_dir: Path, entry_relative: Path, *, bundle_path: Path | None = None) -> dict[str, Any]:
    result = json.loads((output_dir / "scan-result.json").read_text(encoding="utf-8"))
    if result["capture_status"] not in {"completed_with_states", "completed_empty"} or result["scan_errors"]:
        raise ValueError("state capture did not complete")
    if result["native_export_status"] not in {"json", "dot", "empty"}:
        raise ValueError("native ETIQ export failed")
    entry = resolve_repository_file(entry_relative, suffix=".py")
    if result["entry_file"] != {"path": entry_relative.as_posix(), "sha256": file_sha256(entry)}:
        raise ValueError("scan entry binding is stale")
    native = output_dir / result["native_graph"]["path"]
    if file_sha256(native) != result["native_graph"]["sha256"]:
        raise ValueError("native graph hash differs")
    if result["native_export_status"] == "dot" and result["projection_status"] == "completed":
        projection = json.loads((output_dir / "etiq_dot_projection.json").read_text(encoding="utf-8"))
        if projection["node_count"] <= 0 or projection["edge_count"] <= 0:
            raise ValueError("DOT projection is empty")
    if result["projection_status"] in {"failed", "timed_out"}:
        error_path = output_dir / "dot-projection-error.json"
        if not error_path.is_file() or file_sha256(error_path) != result["projection_error"]["sha256"]:
            raise ValueError("DOT projection error evidence differs")
    if result["native_export_status"] == "json" and bundle_path:
        if result["workflow_only_eligibility"] != "not_assessed":
            raise ValueError("native JSON workflow-only eligibility must remain unassessed")
    if bundle_path:
        bundle = validate_replay_bundle(bundle_path)
        if result["source_workflow_sha256"] != bundle["workflow_sha256"]:
            raise ValueError("workflow binding is stale")
        if result["scan_source"]["sha256"] != bundle["workflow_sha256"]:
            raise ValueError("ETIQ scanned source binding is stale")
        if result["scan_source"]["path"] != bundle["workflow_path"]:
            raise ValueError("ETIQ scanned the wrong workflow path")
        if not result["replay_fidelity"]["passed"]:
            raise ValueError("replay fidelity failed")
    return result


def build_worker_environment(output_dir: Path, bundle_path: Path | None,
                             replay_result: Path | None) -> dict[str, str]:
    isolation = output_dir.parent / f".{output_dir.name}-isolation"
    home = isolation / "home"
    cache = isolation / "cache"
    data = isolation / "data"
    temp = isolation / "tmp"
    for path in (home, cache, data, temp):
        path.mkdir(parents=True, exist_ok=False)
    if bundle_path:
        config = data / "etiq_copilot" / "capture_targets.yml"
        config.parent.mkdir(parents=True)
        config.write_text(
            f"!!set\n{REPLAY_API_QUALIFIED_TYPE}: null\n",
            encoding="utf-8",
        )
    environment = {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "HOME": str(home.resolve()), "XDG_CACHE_HOME": str(cache.resolve()),
        "XDG_DATA_HOME": str(data.resolve()),
        "TMPDIR": str(temp.resolve()), "PYTHONPATH": str((REPOSITORY_ROOT / "src").resolve()),
        "PYDANTIC_AI_NO_BANNER": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "ETIQ_NETWORK_DISABLED": "1",
    }
    if bundle_path and replay_result:
        environment["ETIQ_REPLAY_BUNDLE"] = str(bundle_path.resolve())
        environment["ETIQ_REPLAY_RESULT"] = str(replay_result.resolve())
    forbidden = [name for name in environment if FORBIDDEN_ENV.search(name)
                 or name.startswith(FORBIDDEN_PREFIXES)]
    if forbidden:
        raise ValueError(f"worker environment includes forbidden names: {forbidden}")
    return environment


def sanitize_process_text(text: str) -> str:
    return JWT.sub("<redacted:token>", text)


def environment_freeze(python_executable: Path | None = None) -> list[str]:
    environment = {"PATH": "/usr/bin:/bin", "UV_CACHE_DIR": "/tmp/rdr-v2-etiq-uv",
                   "HOME": "/tmp/rdr-v2-etiq-freeze-home", "LANG": "C.UTF-8"}
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to record the pilot environment freeze")
    python = str(python_executable or Path(sys.executable))
    completed = subprocess.run([uv, "pip", "freeze", "--python", python],
                               check=True, capture_output=True, text=True, env=environment)
    return [line for line in completed.stdout.splitlines() if line]


def _git_metadata() -> dict[str, Any]:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT,
                         check=True, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPOSITORY_ROOT,
                                check=True, capture_output=True, text=True).stdout.strip())
    return {"commit": sha, "dirty_worktree": dirty}


def reject_bytecode_artifacts(root: Path) -> None:
    forbidden = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and (path.suffix == ".pyc" or "__pycache__" in path.parts)
    )
    if forbidden:
        raise ValueError(f"bytecode artifacts are forbidden: {forbidden[:5]}")


def write_manifest(
    output_dir: Path, command: list[str], *, bundle_path: Path | None = None,
    python_executable: Path | None = None,
) -> dict[str, Any]:
    reject_bytecode_artifacts(output_dir)
    freeze = environment_freeze(python_executable)
    artifacts = {}
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            artifacts[path.name] = file_sha256(path)
    manifest = {
        "schema_version": "2.0", "environment_freeze": freeze,
        "environment_freeze_sha256": canonical_hash(freeze),
        "python_version": platform.python_version(), "platform": platform.platform(),
        "repository": _git_metadata(), "official_demo_commit": OFFICIAL_DEMO_COMMIT,
        "replay_bundle_sha256": file_sha256(bundle_path) if bundle_path else None,
        "command": command, "artifacts": artifacts,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def verify_manifest(output_dir: Path) -> dict[str, Any]:
    reject_bytecode_artifacts(output_dir)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if canonical_hash(manifest["environment_freeze"]) != manifest["environment_freeze_sha256"]:
        raise ValueError("environment freeze hash differs")
    for name, digest in manifest["artifacts"].items():
        if file_sha256(output_dir / name) != digest:
            raise ValueError(f"manifest hash differs for {name}")
    required = {"scan-result.json", "state-inventory.json", "stdout.txt", "stderr.txt"}
    result = json.loads((output_dir / "scan-result.json").read_text(encoding="utf-8"))
    native_path = result["native_graph"]["path"]
    if native_path:
        required.add(native_path)
    if result["native_export_status"] == "dot" and result["projection_status"] == "completed":
        required |= {"lineage.dot", "etiq_dot_projection.json", "workflow-lineage-projection.json"}
    if result["projection_status"] in {"failed", "timed_out"}:
        required.add("dot-projection-error.json")
    elif result["native_export_status"] == "failed":
        required |= {"json-export-error.json", "dot-export-error.json"}
    if not required <= set(manifest["artifacts"]):
        raise ValueError(f"manifest omits artifacts: {sorted(required - set(manifest['artifacts']))}")
    return manifest


def run_isolated_scan(
    entry_relative: Path, output_dir: Path, *, bundle_path: Path | None = None,
    python_executable: Path | None = None,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ValueError(f"refusing to overwrite pilot run: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    replay_result = (output_dir.parent / f".{output_dir.name}-private-replay-result.json").resolve() if bundle_path else None
    python = python_executable or Path(sys.executable)
    if not python.is_file():
        raise FileNotFoundError(f"Etiq Python interpreter does not exist: {python}")
    command = [str(python), "-m", "rdr.etiq_pilot", "scan-worker", "--entry",
               entry_relative.as_posix(), "--output", str(output_dir)]
    if bundle_path and replay_result:
        command += ["--bundle", str(bundle_path), "--replay-result", str(replay_result)]
    environment = build_worker_environment(output_dir, bundle_path, replay_result)
    completed = subprocess.run(command, cwd=REPOSITORY_ROOT, env=environment,
                               capture_output=True, text=True, timeout=300)
    if not output_dir.exists():
        raise RuntimeError(f"scan worker failed before producing artifacts: {completed.stderr}")
    (output_dir / "stdout.txt").write_text(sanitize_process_text(completed.stdout), encoding="utf-8")
    (output_dir / "stderr.txt").write_text(sanitize_process_text(completed.stderr), encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"scan worker exited {completed.returncode}")
    result = json.loads((output_dir / "scan-result.json").read_text(encoding="utf-8"))
    if result["status"] == "completed":
        validate_scan_result(output_dir, entry_relative, bundle_path=bundle_path)
    elif result["status"] != "failed":
        raise RuntimeError("worker produced neither a completed nor a failed result")
    write_manifest(
        output_dir, command, bundle_path=bundle_path,
        python_executable=python,
    )
    verify_manifest(output_dir)
    return result


def compare_runs(first: Path, second: Path) -> dict[str, Any]:
    a = json.loads((first / "scan-result.json").read_text(encoding="utf-8"))
    b = json.loads((second / "scan-result.json").read_text(encoding="utf-8"))
    checks = {
        "native_export_status": a["native_export_status"] == b["native_export_status"],
        "dot_semantics": (
            a["dot_projection"] is not None and b["dot_projection"] is not None
            and a["dot_projection"]["semantic_sha256"] == b["dot_projection"]["semantic_sha256"]
        ),
        "captured_names": a["captured_objects"] == b["captured_objects"],
        "transcript": a["replay_fidelity"]["transcript_sha256"] == b["replay_fidelity"]["transcript_sha256"],
        "final_output": a["replay_fidelity"]["final_output_sha256"] == b["replay_fidelity"]["final_output_sha256"],
    }
    return {"checks": checks, "passed": all(checks.values())}


def _state_hashes(inventory_path: Path, names: set[str]) -> dict[str, set[str]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = defaultdict(set)
    for state in inventory["states"]:
        for name in names & set(state["names"]):
            if state["origin"]["classification"] == "frozen_workflow":
                result[name].add(state["value_sha256"])
    return result


def build_summary(root: Path) -> dict[str, Any]:
    if (root / "pilot-summary.json").exists():
        raise ValueError("refusing to overwrite pilot summary")
    run = lambda cell, repeat=1: root / "cells" / cell / f"run-{repeat}"
    clean_repeat = compare_runs(run("S01/S0R0"), run("S01/S0R0", 2))
    fault_repeat = compare_runs(run("S01/S1R0"), run("S01/S1R0", 2))
    cases = {}
    for cell in MATRIX_CELLS:
        path = run(cell)
        scan = json.loads((path / "scan-result.json").read_text(encoding="utf-8"))
        cases[cell] = {
            "capture_status": scan["capture_status"], "native_export_status": scan["native_export_status"],
            "workflow_only_eligibility": scan["workflow_only_eligibility"],
            "composite_eligibility": scan["composite_eligibility"],
            "qualification_passed": scan["replay_fidelity"]["expected_qualification_passed"],
            "fidelity_passed": scan["replay_fidelity"]["passed"],
            "state_count": sum(scan["counts"].values()),
            "projection_assessment": scan["workflow_projection"]["assessment"] if scan["workflow_projection"] else None,
        }
    comparisons = {}
    relevant = {"payload", "matching_users", "result", "request_id", "receipt_path"}
    for label, left, right in (
        ("source", "S01/S0R0", "S01/S1R0"),
        ("source_repaired", "S01/S1R0", "S01/repaired"),
        ("runtime", "S01/S0R0", "R01/S0R1"),
        ("runtime_repaired", "R01/S0R1", "R01/repaired"),
        ("interaction", "I06/S1R0", "I06/S1R1"),
        ("interaction_repaired", "I06/S1R1", "I06/repaired"),
    ):
        a = _state_hashes(run(left) / "state-inventory.json", relevant)
        b = _state_hashes(run(right) / "state-inventory.json", relevant)
        comparisons[label] = {name: sorted(a.get(name, set()) ^ b.get(name, set())) for name in sorted(relevant)}
        comparisons[label]["changed_value_observed"] = any(comparisons[label][name] for name in relevant)
    native_valid = all(item["native_export_status"] in {"json", "dot"} for item in cases.values())
    native_empty = all(item["native_export_status"] == "empty" for item in cases.values())
    workflow_eligible = all(
        item["workflow_only_eligibility"] == "eligible" for item in cases.values()
    )
    if workflow_eligible:
        outcome = "eligible"
    elif native_valid:
        outcome = "native_dot_available_but_not_arm_eligible"
    elif native_empty:
        outcome = "not_eligible_empty_native_graph"
    else:
        outcome = "not_assessable_no_native_graph"
    summary = {
        "schema_version": "2.0", "etiq_copilot_version": ETIQ_VERSION,
        "decisions": {
            "scanner_execution": "completed" if all(
                item["capture_status"] in {"completed_with_states", "completed_empty"}
                for item in cases.values()
            ) else "failed",
            "eligible_appworld_states_captured": sum(item["state_count"] for item in cases.values()),
            "native_appworld_graph": "available" if native_valid else ("empty" if native_empty else "failed"),
            "experimental_arm": outcome,
        },
        "official_control": json.loads((root / "official-agentic/scan-result.json").read_text(encoding="utf-8")),
        "cases": cases, "repeatability": {"clean": clean_repeat, "source_fault": fault_repeat},
        "fault_value_comparisons": comparisons,
        "limitations": [
            "With isolated HOME/XDG data, replay scans capture zero states and both native exports are empty.",
            "The persistent user capture configuration is excluded because it registers builtins.dict.",
            "Fault-value and fault-to-action lineage cannot be assessed without a native graph.",
        ],
    }
    write_json(root / "pilot-summary.json", summary)
    return summary


def build_smoke_summary(root: Path) -> dict[str, Any]:
    output = root / "smoke-summary.json"
    if output.exists():
        raise ValueError("refusing to overwrite smoke summary")
    official = json.loads((root / "official-agentic/scan-result.json").read_text(encoding="utf-8"))
    clean = json.loads((root / "cells/S01/S0R0/run-1/scan-result.json").read_text(encoding="utf-8"))
    summary = {
        "schema_version": "1.0", "etiq_copilot_version": ETIQ_VERSION,
        "runs": {
            "official_agentic": {
                key: official[key] for key in (
                    "capture_status", "native_export_status", "projection_status",
                    "workflow_only_eligibility", "composite_eligibility",
                )
            },
            "S01/S0R0": {
                key: clean[key] for key in (
                    "capture_status", "native_export_status", "projection_status",
                    "workflow_only_eligibility", "composite_eligibility",
                )
            },
        },
        "decisions": {
            "scanner_execution": "completed" if clean["capture_status"] == "completed_empty" else "review_required",
            "eligible_appworld_states_captured": sum(clean["counts"].values()),
            "native_appworld_graph": "empty" if clean["native_export_status"] == "empty" else "review_required",
            "experimental_arm": (
                "not_eligible" if clean["workflow_only_eligibility"] == "not_eligible"
                else "review_required"
            ),
        },
        "stopped_after_clean_control": True,
    }
    write_json(output, summary)
    return summary


def write_isolation_assessment(root: Path) -> dict[str, Any]:
    output = root / "isolation-assessment.json"
    if output.exists():
        raise ValueError("refusing to overwrite isolation assessment")
    persistent = Path.home() / ".local/share/etiq_copilot/capture_targets.yml"
    targets = []
    if persistent.exists():
        targets = sorted(
            line.split(":", 1)[0].strip()
            for line in persistent.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("!") and ":" in line
        )
    assessment = {
        "schema_version": "1.0",
        "persistent_capture_config": {
            "path": persistent.as_posix(), "exists": persistent.exists(),
            "sha256": file_sha256(persistent) if persistent.exists() else None,
            "registered_targets": targets, "inherited_by_worker": False,
        },
        "disallowed_primitive_registration_present": "builtins.dict" in targets,
        "worker_policy": "Isolated HOME/XDG data directories; no capture target configuration copied.",
        "conclusion": (
            "The prior 1,381-state result is not reproducible without inheriting a persistent "
            "builtins.dict capture registration, which this pilot forbids."
        ),
    }
    write_json(output, assessment)
    return assessment


def write_root_manifest(root: Path) -> dict[str, Any]:
    output = root / "manifest.json"
    if output.exists():
        raise ValueError("refusing to overwrite root manifest")
    reject_bytecode_artifacts(root)
    artifacts = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != output
    }
    freeze = environment_freeze()
    manifest = {
        "schema_version": "2.0", "create_only": True,
        "environment_freeze": freeze, "environment_freeze_sha256": canonical_hash(freeze),
        "artifacts": artifacts, "artifact_count": len(artifacts),
        "repository": _git_metadata(), "official_demo_commit": OFFICIAL_DEMO_COMMIT,
    }
    write_json(output, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export-cell")
    export.add_argument("--cell", type=Path, required=True)
    export.add_argument("--bundle", type=Path, required=True)
    export.add_argument("--source", type=Path, required=True)
    worker = sub.add_parser("scan-worker")
    worker.add_argument("--entry", type=Path, required=True)
    worker.add_argument("--output", type=Path, required=True)
    worker.add_argument("--bundle", type=Path)
    worker.add_argument("--replay-result", type=Path)
    run = sub.add_parser("run")
    run.add_argument("--entry", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--bundle", type=Path)
    validate = sub.add_parser("validate")
    validate.add_argument("--entry", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    validate.add_argument("--bundle", type=Path)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--root", type=Path, required=True)
    summarize_smoke = sub.add_parser("summarize-smoke")
    summarize_smoke.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export-cell":
        result = export_replay_cell(args.cell, args.bundle, args.source)
        print(json.dumps({"status": "completed", "bundle_sha256": result["bundle_sha256"]}))
    elif args.command == "scan-worker":
        result = scan_entry(args.entry, args.output, bundle_path=args.bundle,
                            replay_result_path=args.replay_result)
        print(json.dumps({"status": result["status"], "native_export_status": result["native_export_status"]}))
    elif args.command == "run":
        result = run_isolated_scan(args.entry, args.output, bundle_path=args.bundle)
        print(json.dumps({"status": result["status"], "output": str(args.output)}))
    elif args.command == "validate":
        result = validate_scan_result(args.output, args.entry, bundle_path=args.bundle)
        verify_manifest(args.output)
        print(json.dumps({"status": result["status"], "output": str(args.output)}))
    elif args.command == "summarize":
        write_isolation_assessment(args.root)
        result = build_summary(args.root)
        write_root_manifest(args.root)
        print(json.dumps(result["decisions"], sort_keys=True))
    else:
        write_isolation_assessment(args.root)
        result = build_smoke_summary(args.root)
        write_root_manifest(args.root)
        print(json.dumps(result["decisions"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
