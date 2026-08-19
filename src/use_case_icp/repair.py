from __future__ import annotations

import ast
import difflib
from typing import Any

from .records import EtiqEvidenceSnapshot, GeneratedPipeline
from .review import retrace_node_refs


def _functions(source: str, name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(source)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]


def _statements(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.stmt]:
    return sorted(
        (
            node
            for node in ast.walk(function)
            if isinstance(node, ast.stmt)
            and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        key=lambda node: (
            int(node.lineno),
            int(node.col_offset),
            int(getattr(node, "end_lineno", node.lineno)),
        ),
    )


def source_scope(
    pipeline: GeneratedPipeline,
    *,
    function_name: str,
    mode: str,
    line_no: int | None = None,
) -> dict[str, Any]:
    matches: list[tuple[str, str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for generated_file in pipeline.files:
        for function in _functions(generated_file.content, function_name):
            matches.append((generated_file.path, generated_file.content, function))
    if not matches:
        entry = next(item for item in pipeline.files if item.path == pipeline.entry_file)
        return {
            "requested_mode": mode,
            "effective_mode": "boundary",
            "scope_kind": "module_fallback",
            "function_name": function_name,
            "file": entry.path,
            "start_line": 1,
            "end_line": max(1, len(entry.content.splitlines())),
        }
    if line_no is not None:
        containing = [
            item
            for item in matches
            if item[2].lineno <= line_no <= int(item[2].end_lineno or item[2].lineno)
        ]
        if containing:
            matches = containing
    if len(matches) != 1:
        raise ValueError(f"repair boundary function is ambiguous: {function_name}")
    path, _, function = matches[0]
    scope: dict[str, Any] = {
        "requested_mode": mode,
        "effective_mode": "boundary",
        "scope_kind": "function",
        "function_name": function_name,
        "file": path,
        "start_line": function.lineno,
        "end_line": int(function.end_lineno or function.lineno),
    }
    if mode != "faulty_node" or line_no is None:
        return scope
    candidates = [
        statement
        for statement in _statements(function)
        if statement.lineno <= line_no <= int(statement.end_lineno or statement.lineno)
    ]
    if not candidates:
        return scope
    statement = min(
        candidates,
        key=lambda item: (
            int(item.end_lineno or item.lineno) - item.lineno,
            item.col_offset,
        ),
    )
    statements = _statements(function)
    scope.update(
        {
            "effective_mode": "faulty_node",
            "start_line": statement.lineno,
            "end_line": int(statement.end_lineno or statement.lineno),
            "statement_index": statements.index(statement),
        }
    )
    return scope


def select_repair_target(
    mode: str,
    *,
    pipeline: GeneratedPipeline,
    snapshot: EtiqEvidenceSnapshot,
    review_context: dict[str, Any],
    previous_target_function_names: list[str] | None = None,
) -> dict[str, Any]:
    if mode not in {"boundary", "faulty_node"}:
        raise ValueError("repair_scope_mode must be 'boundary' or 'faulty_node'")
    all_receipts = review_context.get("receipts", [])
    receipts = [
        receipt
        for receipt in all_receipts
        if receipt.get("result") != "rejected"
    ]
    if all_receipts and not receipts:
        raise ValueError("rejected review receipts cannot select a repair target")
    failed_unit_ids = [
        str(unit_id)
        for receipt in receipts
        for unit_id in receipt.get("failed_or_suspect_unit_ids", [])
    ]
    if not failed_unit_ids:
        function_name = (
            str(pipeline.review_boundaries[0]["function_name"])
            if pipeline.review_boundaries
            else "__module__"
        )
        target = source_scope(
            pipeline,
            function_name=function_name,
            mode="boundary",
        )
        target.update(
            {
                "unit_id": None,
                "suspect_node_ref": None,
                "retrace_node_refs": [],
                "selection_reason": str(
                    review_context.get("reason") or "review did not identify a repair unit"
                ),
            }
        )
        return target
    unit_by_id = {
        str(item.get("unit_id")): item
        for item in review_context.get("units", [])
    }
    candidates = [
        unit_by_id[unit_id]
        for unit_id in dict.fromkeys(failed_unit_ids)
        if unit_id in unit_by_id
    ]
    if not candidates:
        raise ValueError("repair units are missing from review context")
    failed_ids = {str(item["unit_id"]) for item in candidates}
    causal_roots = [
        item
        for item in candidates
        if not failed_ids.intersection(
            str(unit_id) for unit_id in item.get("upstream_unit_ids", [])
        )
    ]
    candidate_pool = causal_roots or candidates
    attempt_counts: dict[str, int] = {}
    for function_name in previous_target_function_names or []:
        attempt_counts[function_name] = attempt_counts.get(function_name, 0) + 1
    unit = min(
        enumerate(candidate_pool),
        key=lambda item: (
            attempt_counts.get(str(item[1].get("function_name")), 0),
            item[0],
        ),
    )[1]
    unit_id = str(unit["unit_id"])
    suspect_refs = [
        str(ref)
        for receipt in receipts
        for ref in receipt.get("suspect_node_refs", [])
    ]
    unit_node_refs = set(unit.get("node_refs", []))
    suspect_ref = next(
        (ref for ref in suspect_refs if ref in unit_node_refs),
        None,
    )
    node = next(
        (item for item in snapshot.nodes if item.node_ref == suspect_ref),
        None,
    )
    target = source_scope(
        pipeline,
        function_name=str(unit["function_name"]),
        mode=mode,
        line_no=node.line_no if node is not None else None,
    )
    target.update(
        {
            "unit_id": unit_id,
            "suspect_node_ref": suspect_ref,
            "previous_attempts_for_boundary": attempt_counts.get(
                str(unit["function_name"]),
                0,
            ),
            "selection_reason": (
                "earliest graph-causal failed boundary; ties use the fewest previous repairs"
            ),
            "retrace_node_refs": retrace_node_refs(
                snapshot,
                [suspect_ref] if suspect_ref else unit.get("node_refs", []),
            ),
        }
    )
    return target


def _outside_scope(source: str, start_line: int, end_line: int) -> tuple[str, str]:
    lines = source.splitlines(keepends=True)
    return "".join(lines[: start_line - 1]), "".join(lines[end_line:])


def validate_repair_scope(
    original: GeneratedPipeline,
    replacement: GeneratedPipeline,
    target: dict[str, Any],
) -> None:
    if original.entry_file != replacement.entry_file:
        raise ValueError("repair cannot change entry_file")
    if original.review_boundaries != replacement.review_boundaries:
        raise ValueError("repair cannot change declared review boundaries")
    old_files = {item.path: item.content for item in original.files}
    new_files = {item.path: item.content for item in replacement.files}
    if old_files.keys() != new_files.keys():
        raise ValueError("repair cannot add or remove files")
    target_file = str(target["file"])
    for path in old_files:
        if path != target_file and old_files[path] != new_files[path]:
            raise ValueError(f"repair changed a file outside its scope: {path}")

    if target.get("scope_kind") == "module_fallback":
        raise ValueError(
            "repair target does not resolve to a single function, so the repair "
            "cannot be scoped: "
            f"{target.get('function_name')!r}"
        )
    old_functions = _functions(old_files[target_file], str(target["function_name"]))
    new_functions = _functions(new_files[target_file], str(target["function_name"]))
    if len(old_functions) != 1 or len(new_functions) != 1:
        raise ValueError("repair must preserve one unambiguous target function")
    old_function, new_function = old_functions[0], new_functions[0]
    if target["effective_mode"] == "faulty_node":
        index = int(target["statement_index"])
        old_statements = _statements(old_function)
        new_statements = _statements(new_function)
        if index >= len(old_statements) or index >= len(new_statements):
            raise ValueError("repair must preserve the target statement position")
        old_scope, new_scope = old_statements[index], new_statements[index]
    else:
        old_scope, new_scope = old_function, new_function
    old_outside = _outside_scope(
        old_files[target_file],
        int(old_scope.lineno),
        int(old_scope.end_lineno or old_scope.lineno),
    )
    new_outside = _outside_scope(
        new_files[target_file],
        int(new_scope.lineno),
        int(new_scope.end_lineno or new_scope.lineno),
    )
    if old_outside != new_outside:
        raise ValueError("repair changed source outside the selected scope")


def repair_diff(
    original: GeneratedPipeline,
    replacement: GeneratedPipeline,
) -> str:
    old_files = {item.path: item.content for item in original.files}
    new_files = {item.path: item.content for item in replacement.files}
    parts: list[str] = []
    for path in sorted(old_files.keys() | new_files.keys()):
        if old_files.get(path) == new_files.get(path):
            continue
        parts.extend(
            difflib.unified_diff(
                old_files.get(path, "").splitlines(),
                new_files.get(path, "").splitlines(),
                fromfile=f"before/{path}",
                tofile=f"after/{path}",
                lineterm="",
            )
        )
    return "\n".join(parts)
