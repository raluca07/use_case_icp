"""Scars: caught faults become permanent deterministic checks on their boundary.

Accumulated history modulated every model judge we tested, in model-specific directions,
because it hands a model superseded evidence to reason over. A scar keeps the lesson and
throws away the transcript. It is minted from one clean and one faulty observation of the
same boundary, records only the differences that a check can express, and is attached to
that boundary's identity so it goes inert the moment the boundary legitimately changes.

The design constraint is the paper's own result: our deterministic signals raised zero
false suspicion, and scarring must not spend that. Every check therefore encodes a
specific observed difference, never a general suspicion, and a scar that cannot express
its difference as a check is refused rather than stored vague.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from typing import Any

from .records import GeneratedPipeline

TRUSTED = "trusted"
SUSPECT = "suspect"


def boundary_fingerprint(pipeline: GeneratedPipeline, boundary: str) -> str:
    """Identity of a boundary's implementation, so a scar can expire when it changes."""
    entry = next(f for f in pipeline.files if f.path == pipeline.entry_file)
    for node in ast.parse(entry.content).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == boundary:
            body = ast.dump(ast.parse(ast.unparse(node)))
            return hashlib.sha256(body.encode()).hexdigest()[:16]
    return ""


def _keys(value: Any) -> set[str]:
    return set(value) if isinstance(value, dict) else set()


def _len_of(value: Any, key: str) -> int | None:
    if isinstance(value, dict) and isinstance(value.get(key), (list, tuple)):
        return len(value[key])
    return None


def _sequence(value: Any, key: str) -> list[Any] | None:
    if isinstance(value, dict) and isinstance(value.get(key), (list, tuple)):
        return list(value[key])
    return None


def _sort_key(item: Any) -> str:
    if isinstance(item, dict):
        return "|".join(f"{k}={item[k]}" for k in sorted(item))
    return str(item)


def _vocab(value: Any, key: str) -> set[str] | None:
    if not isinstance(value, dict):
        return None
    items = value.get(key)
    if isinstance(items, (list, tuple)) and items and all(isinstance(i, str) for i in items):
        return set(items)
    return None


@dataclass(frozen=True)
class Scar:
    """One healed fault, expressed as checks over a boundary's captured output."""

    boundary: str
    fingerprint: str
    provenance: str
    checks: list[dict[str, Any]] = field(default_factory=list)

    def live(self, pipeline: GeneratedPipeline) -> bool:
        return bool(self.fingerprint) and boundary_fingerprint(pipeline, self.boundary) == self.fingerprint

    def violations(self, value: Any) -> list[str]:
        found: list[str] = []
        for check in self.checks:
            kind = check["kind"]
            if kind == "required_field" and check["field"] not in _keys(value):
                found.append(f"field {check['field']} absent, present when healthy")
            elif kind == "min_items":
                n = _len_of(value, check["field"])
                if n is not None and n < check["floor"]:
                    found.append(f"{check['field']} holds {n}, at least {check['floor']} when healthy")
            elif kind == "ordering":
                seq = _sequence(value, check["field"])
                if seq is not None and len(seq) > 1:
                    keys = [_sort_key(i) for i in seq]
                    if check["direction"] == "ascending" and keys != sorted(keys):
                        found.append(f"{check['field']} not in ascending order, was when healthy")
                    elif check["direction"] == "descending" and keys != sorted(keys, reverse=True):
                        found.append(f"{check['field']} not in descending order, was when healthy")
            elif kind == "known_vocabulary":
                seen = _vocab(value, check["field"])
                if seen is not None:
                    unknown = seen - set(check["allowed"])
                    if unknown:
                        found.append(f"{check['field']} carries unseen {sorted(unknown)[:2]}")
        return found


def mint_scar(*, boundary: str, pipeline: GeneratedPipeline, clean_value: Any,
              faulty_value: Any, provenance: str) -> Scar:
    """Distil one clean/faulty pair into checks. Refuses when nothing separable differs."""
    if clean_value == faulty_value:
        raise ValueError("cannot mint a scar from identical observations")

    checks: list[dict[str, Any]] = []
    for field_name in sorted(_keys(clean_value) - _keys(faulty_value)):
        checks.append({"kind": "required_field", "field": field_name})

    for field_name in sorted(_keys(clean_value) & _keys(faulty_value)):
        clean_n, faulty_n = _len_of(clean_value, field_name), _len_of(faulty_value, field_name)
        if clean_n is not None and faulty_n is not None and faulty_n < clean_n:
            checks.append({"kind": "min_items", "field": field_name, "floor": clean_n})
        clean_v, faulty_v = _vocab(clean_value, field_name), _vocab(faulty_value, field_name)
        if clean_v and faulty_v and (faulty_v - clean_v):
            checks.append({"kind": "known_vocabulary", "field": field_name,
                           "allowed": sorted(clean_v)})
        clean_seq, faulty_seq = _sequence(clean_value, field_name), _sequence(faulty_value, field_name)
        if clean_seq is not None and faulty_seq is not None and len(clean_seq) > 1:
            ck, fk = [_sort_key(i) for i in clean_seq], [_sort_key(i) for i in faulty_seq]
            # Only scar an ordering the healthy run actually held and the faulty one broke.
            if sorted(ck) == sorted(fk) and ck != fk:
                if ck == sorted(ck):
                    checks.append({"kind": "ordering", "field": field_name, "direction": "ascending"})
                elif ck == sorted(ck, reverse=True):
                    checks.append({"kind": "ordering", "field": field_name, "direction": "descending"})

    if not checks:
        raise ValueError(
            f"the difference at {boundary!r} is not expressible as a check; "
            "storing it as vague suspicion would spend the zero false-suspicion budget")
    return Scar(boundary=boundary, fingerprint=boundary_fingerprint(pipeline, boundary),
                provenance=provenance, checks=checks)


class ScarDetector:
    """Deterministic detector whose checks were learned rather than declared."""

    def __init__(self, scars: list[Scar]) -> None:
        self.scars = scars

    def label(self, boundaries: list[str], outputs: dict[str, Any],
              pipeline: GeneratedPipeline) -> dict[str, str]:
        labels = {b: TRUSTED for b in boundaries}
        for scar in self.scars:
            if scar.boundary not in outputs or not scar.live(pipeline):
                continue
            if scar.violations(outputs[scar.boundary]):
                labels[scar.boundary] = SUSPECT
        return labels
