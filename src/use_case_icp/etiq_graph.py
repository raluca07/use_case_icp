from __future__ import annotations

import importlib.metadata
import json
import re
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from .records import (
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    new_id,
)


STATE_GETTERS = (
    "get_dataframes",
    "get_models",
    "get_agent_states",
    "get_unstructured_states",
)
SENSITIVE_NAME = re.compile(
    r"(api[_-]?key|authorization|cookie|credential|password|secret|session|token)",
    re.IGNORECASE,
)


def _safe_call(value: Any, method: str) -> Any:
    target = getattr(value, method, None)
    if not callable(target):
        return None
    try:
        return target()
    except Exception as exc:
        return {"error": type(exc).__name__}


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return repr(value)[:500]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth=depth + 1) for item in value]
    return repr(value)[:1000]


def _preview_value(value: Any, *, depth: int = 0) -> tuple[Any, bool]:
    if depth > 3:
        return repr(value)[:200], True
    if value is None or isinstance(value, (int, float, bool)):
        return value, False
    if isinstance(value, str):
        return value[:500], len(value) > 500
    if hasattr(value, "shape") and hasattr(value, "columns") and hasattr(value, "head"):
        try:
            rows = value.head(5).to_dict(orient="records")
            columns = [str(item) for item in list(value.columns)[:20]]
            return {
                "kind": type(value).__name__,
                "shape": list(value.shape),
                "columns": columns,
                "rows": _redact_mapping_rows(rows),
            }, len(value) > 5 or len(value.columns) > 20
        except Exception:
            pass
    if isinstance(value, Mapping):
        preview: dict[str, Any] = {}
        truncated = len(value) > 20
        for key, item in list(value.items())[:20]:
            name = str(key)
            if SENSITIVE_NAME.search(name):
                preview[name] = "[REDACTED]"
                continue
            preview[name], item_truncated = _preview_value(item, depth=depth + 1)
            truncated = truncated or item_truncated
        return preview, truncated
    if isinstance(value, (list, tuple, set)):
        preview_items: list[Any] = []
        truncated = len(value) > 20
        for item in list(value)[:20]:
            item_preview, item_truncated = _preview_value(item, depth=depth + 1)
            preview_items.append(item_preview)
            truncated = truncated or item_truncated
        return preview_items, truncated
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _preview_value(dump(), depth=depth + 1)
        except Exception:
            pass
    text = repr(value)
    return text[:500], len(text) > 500


def _redact_mapping_rows(rows: Any) -> list[Any]:
    preview, _ = _preview_value(rows)
    return preview if isinstance(preview, list) else []


def value_preview(value: Any, *, max_chars: int = 2_000) -> tuple[Any, bool]:
    preview, truncated = _preview_value(value)
    encoded = json.dumps(preview, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return preview, truncated
    return {"summary": encoded[:max_chars]}, True


def _redact_artifact(value: Any, *, depth: int = 0) -> Any:
    if depth > 10:
        return repr(value)[:1_000]
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if SENSITIVE_NAME.search(str(key))
                else _redact_artifact(item, depth=depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_redact_artifact(item, depth=depth + 1) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _redact_artifact(dump(), depth=depth + 1)
        except Exception:
            pass
    return _json_safe(value, depth=depth)


def inspectable_artifact(
    value: Any,
    *,
    max_chars: int = 2_000_000,
) -> tuple[str | None, Any | None, bool, dict[str, int] | None]:
    if value is None:
        return None, None, False, None
    if hasattr(value, "shape") and hasattr(value, "columns") and hasattr(value, "to_dict"):
        try:
            columns = [str(item) for item in value.columns]
            rows = _redact_artifact(value.to_dict(orient="records"))
            content: Any = {"columns": columns, "rows": rows}
            size = {"rows": int(value.shape[0]), "columns": int(value.shape[1])}
            encoded = json.dumps(content, ensure_ascii=False, default=str)
            if len(encoded) <= max_chars:
                return "table", content, False, size
            kept = max(1, int(len(rows) * max_chars / max(len(encoded), 1)))
            content = {"columns": columns, "rows": rows[:kept]}
            while kept > 1 and len(json.dumps(content, ensure_ascii=False, default=str)) > max_chars:
                kept //= 2
                content["rows"] = rows[:kept]
            return "table", content, True, size
        except Exception:
            pass
    if isinstance(value, str):
        return "document", value[:max_chars], len(value) > max_chars, {"characters": len(value)}
    content = _redact_artifact(value)
    encoded = json.dumps(content, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        kind = "sequence" if isinstance(content, list) else "record"
        size = {"items": len(content)} if isinstance(content, (list, dict)) else {"characters": len(encoded)}
        return kind, content, False, size
    return "record", None, True, {"characters": len(encoded)}


def _redact_metadata_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[OMITTED; use value_preview]"
                if str(key).lower() in {"value", "values"} or SENSITIVE_NAME.search(str(key))
                else _redact_metadata_values(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_metadata_values(item) for item in value]
    return value


def _flatten_states(values: Any) -> list[Any]:
    states: list[Any] = []
    seen: set[int] = set()

    def visit(value: Any) -> None:
        if value is None or isinstance(value, (str, bytes, int, float, bool)):
            return
        if isinstance(value, Mapping):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        identifier = id(value)
        if identifier in seen:
            return
        seen.add(identifier)
        states.append(value)

    visit(values)
    return states


def _raw_id(state: Any) -> str | None:
    for name in ("state_id", "raw_state_id", "id", "_id"):
        value = getattr(state, name, None)
        if value is not None and not callable(value):
            return str(value)
    return None


def _captured_state_categories(result: Any) -> tuple[list[Any], dict[str, list[Any]]]:
    categories: dict[str, list[Any]] = {}
    combined: list[Any] = []
    seen: set[tuple[str, str | int]] = set()
    for getter_name in STATE_GETTERS:
        getter = getattr(result, getter_name, None)
        if not callable(getter):
            raise RuntimeError(
                f"Etiq scan result does not expose required state accessor {getter_name}()"
            )
        try:
            states = _flatten_states(getter())
        except Exception as exc:
            raise RuntimeError(
                f"Etiq state accessor {getter_name}() failed with {type(exc).__name__}"
            ) from exc
        categories[getter_name] = states
        for state in states:
            raw_id = _raw_id(state)
            key: tuple[str, str | int] = (
                ("state_id", raw_id) if raw_id is not None else ("object_id", id(state))
            )
            if key not in seen:
                seen.add(key)
                combined.append(state)
    return combined, categories


def _as_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _as_stack(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return []


def _function_mapping_key(state: Any, mapping: Any) -> tuple[Any, ...]:
    stack = tuple(
        frame.rsplit(",", 1)[0].strip()
        for frame in _as_stack(getattr(state, "func_stack", None))
    )
    node = getattr(state, "node", None)
    return (
        stack,
        str(getattr(mapping, "function_name", None) or "Anonymous"),
        getattr(state, "line_no", None),
        _safe_call(node, "as_string") if node is not None else None,
    )


def _relation_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [str(key) for key in value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _state_refs(value: Any, state_to_ref: Mapping[int, str]) -> list[tuple[str, Any]]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    return [
        (ref, item)
        for item in items
        if (ref := state_to_ref.get(id(item))) is not None
    ]


def _state_summaries(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    return [
        {
            "raw_id": _raw_id(item),
            "state_type": type(item).__name__,
        }
        for item in items
    ]


def _metadata(value: Any) -> Any:
    metadata = _safe_call(value, "metadata_json")
    if metadata is not None:
        return _json_safe(metadata)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _json_safe(dump(mode="json"))
        except Exception:
            pass
    return _json_safe(value)


def serialize_etiq_result(*, job_id: str, run_id: str, result: Any) -> EtiqEvidenceSnapshot:
    states, state_categories = _captured_state_categories(result)
    nodes: list[EtiqNodeRecord] = []
    state_id_to_ref: dict[str, str] = {}
    state_to_ref: dict[int, str] = {}
    for index, state in enumerate(states, start=1):
        node_ref = f"{run_id}:state:{index:06d}"
        raw_id = _raw_id(state)
        if raw_id:
            if raw_id in state_id_to_ref:
                raise RuntimeError(f"duplicate Etiq state id: {raw_id}")
            state_id_to_ref[raw_id] = node_ref
        state_to_ref[id(state)] = node_ref
        node = getattr(state, "node", None)
        value = getattr(state, "value", None)
        preview, preview_truncated = value_preview(value)
        artifact_kind, artifact_content, artifact_truncated, artifact_size = (
            inspectable_artifact(value)
        )
        metadata: dict[str, Any] = {}
        for name in ("parent", "children"):
            if hasattr(state, name):
                metadata[name] = _state_summaries(getattr(state, name))
        for name in (
            "parent_state_ids",
            "child_state_ids",
            "parent_func_mapping",
            "child_func_mapping",
        ):
            if hasattr(state, name):
                metadata[name] = _redact_metadata_values(
                    _metadata(getattr(state, name))
                )
        metadata["etiq_metadata"] = _redact_metadata_values(_metadata(state))
        metadata["source_node_type"] = type(node).__name__ if node is not None else None
        nodes.append(
            EtiqNodeRecord(
                node_ref=node_ref,
                raw_id=raw_id,
                names=_as_names(getattr(state, "names", None)),
                line_no=(
                    getattr(state, "line_no", None)
                    if isinstance(getattr(state, "line_no", None), int)
                    else None
                ),
                state_type=type(state).__name__,
                value_type=type(value).__name__ if value is not None else None,
                func_stack=_as_stack(getattr(state, "func_stack", None)),
                source=_safe_call(node, "as_string") if node is not None else None,
                scope_type=(
                    type(scope).__name__
                    if node is not None and (scope := _safe_call(node, "scope")) is not None
                    else None
                ),
                raw_metadata=metadata,
                value_preview=preview,
                preview_truncated=preview_truncated,
                artifact_kind=artifact_kind,
                artifact_content=artifact_content,
                artifact_truncated=artifact_truncated,
                artifact_size=artifact_size,
            )
        )

    mapping_to_ref: dict[tuple[Any, ...], str] = {}
    mapping_node_by_ref: dict[str, EtiqNodeRecord] = {}
    state_mapping_ref: dict[int, str] = {}
    for state in states:
        mapping = getattr(state, "parent_func_mapping", None)
        function_id = getattr(mapping, "function_id", None) if mapping is not None else None
        if mapping is None or function_id is None:
            continue
        mapping_id = str(function_id)
        mapping_key = _function_mapping_key(state, mapping)
        mapping_ref = mapping_to_ref.get(mapping_key)
        if mapping_ref is None:
            mapping_ref = f"{run_id}:function:{len(mapping_to_ref) + 1:06d}"
            mapping_to_ref[mapping_key] = mapping_ref
            state_node = getattr(state, "node", None)
            mapping_node = EtiqNodeRecord(
                node_ref=mapping_ref,
                raw_id=mapping_id,
                names=[str(getattr(mapping, "function_name", None) or "Anonymous")],
                line_no=(
                    getattr(state, "line_no", None)
                    if isinstance(getattr(state, "line_no", None), int)
                    else None
                ),
                state_type=type(mapping).__name__,
                value_type=None,
                func_stack=_as_stack(getattr(state, "func_stack", None)),
                source=_safe_call(state_node, "as_string") if state_node is not None else None,
                scope_type=(
                    type(scope).__name__
                    if state_node is not None
                    and (scope := _safe_call(state_node, "scope")) is not None
                    else None
                ),
                raw_metadata={
                    "etiq_metadata": _metadata(mapping),
                    "captured_invocation_count": 1,
                },
            )
            nodes.append(mapping_node)
            mapping_node_by_ref[mapping_ref] = mapping_node
        else:
            mapping_node_by_ref[mapping_ref].raw_metadata["captured_invocation_count"] += 1
        state_mapping_ref[id(state)] = mapping_ref

    relationships: list[EtiqRelationshipRecord] = []
    relationship_keys: set[tuple[str, str, str]] = set()
    unresolved_relationships: list[dict[str, Any]] = []

    def add(
        source_ref: str | None,
        target_ref: str | None,
        kind: str,
        direction: str,
        raw: Any,
    ) -> None:
        if source_ref is None or target_ref is None:
            unresolved_relationships.append(
                {
                    "source_ref": source_ref,
                    "target_ref": target_ref,
                    "relationship_type": kind,
                    "direction": direction,
                    "captured": _json_safe(raw),
                }
            )
            return
        key = (source_ref, target_ref, kind)
        if key in relationship_keys:
            return
        relationship_keys.add(key)
        relationships.append(
            EtiqRelationshipRecord(
                relationship_ref=f"{run_id}:relationship:{len(relationships) + 1:06d}",
                source_ref=source_ref,
                target_ref=target_ref,
                relationship_type=kind,
                direction=direction,
                raw_metadata={"captured": _json_safe(raw)},
            )
        )

    for state in states:
        raw_id = _raw_id(state)
        state_ref = state_to_ref[id(state)]
        mapping = getattr(state, "parent_func_mapping", None)
        mapping_ref = state_mapping_ref.get(id(state))
        if mapping_ref is not None:
            for argument_id in _relation_ids(getattr(mapping, "function_arguments", None)):
                add(
                    state_id_to_ref.get(argument_id),
                    mapping_ref,
                    "function_argument",
                    "captured_flow",
                    _redact_metadata_values(_metadata(mapping)),
                )
            add(
                mapping_ref,
                state_ref,
                "function_result",
                "captured_flow",
                _redact_metadata_values(_metadata(mapping)),
            )

        for parent_ref, parent in _state_refs(getattr(state, "parent", None), state_to_ref):
            add(
                parent_ref,
                state_ref,
                "state_parent",
                "parent_to_child",
                _state_summaries(parent)[0],
            )
        for child_ref, child in _state_refs(getattr(state, "children", None), state_to_ref):
            add(
                state_ref,
                child_ref,
                "state_parent",
                "parent_to_child",
                _state_summaries(child)[0],
            )

        if raw_id is None:
            continue
        for parent_id in _relation_ids(getattr(state, "parent_state_ids", None)):
            add(
                state_id_to_ref.get(parent_id),
                state_ref,
                "state_parent",
                "parent_to_child",
                getattr(state, "parent_state_ids", None),
            )
        for child_id in _relation_ids(getattr(state, "child_state_ids", None)):
            add(
                state_ref,
                state_id_to_ref.get(child_id),
                "state_parent",
                "parent_to_child",
                getattr(state, "child_state_ids", None),
            )
        for attribute in ("parent_func_mapping", "child_func_mapping"):
            relation_mapping = getattr(state, attribute, None)
            if not isinstance(relation_mapping, Mapping):
                continue
            for other_id, relation_kind in relation_mapping.items():
                if attribute.startswith("parent"):
                    add(
                        state_id_to_ref.get(str(other_id)),
                        state_ref,
                        str(relation_kind),
                        "parent_to_child",
                        relation_mapping,
                    )
                else:
                    add(
                        state_ref,
                        state_id_to_ref.get(str(other_id)),
                        str(relation_kind),
                        "parent_to_child",
                        relation_mapping,
                    )

    try:
        etiq_version = importlib.metadata.version("etiq-copilot")
    except importlib.metadata.PackageNotFoundError:
        etiq_version = "injected-scanner"
    inventories: dict[str, Any] = {
        "etiq_copilot_version": etiq_version,
        "scan_errors_exposed": hasattr(result, "scan_errors"),
        "json_lineage_export": "unsupported_not_called",
        "captured_state_counts": {
            name: len(category_states)
            for name, category_states in state_categories.items()
        },
        "unresolved_relationships": unresolved_relationships,
    }
    for name in ("list_dataframes", "list_models", "list_agents"):
        method = getattr(result, name, None)
        if callable(method):
            try:
                inventories[name] = _json_safe(method())
            except Exception as exc:
                inventories[name] = {"error": type(exc).__name__}
        else:
            inventories[name] = {"unsupported": True}
    for name, category_states in state_categories.items():
        inventories[name] = [
            {
                "raw_id": _raw_id(state),
                "state_type": type(state).__name__,
            }
            for state in category_states
        ]
    scan_errors = _json_safe(getattr(result, "scan_errors", []))
    if not isinstance(scan_errors, list):
        scan_errors = [scan_errors] if scan_errors else []
    return EtiqEvidenceSnapshot(
        snapshot_id=new_id("etiq"),
        job_id=job_id,
        run_id=run_id,
        nodes=nodes,
        relationships=relationships,
        inventories=inventories,
        scan_errors=scan_errors,
    )
