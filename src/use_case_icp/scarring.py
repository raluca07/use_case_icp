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
    support: int = 1

    def clears(self, value: Any) -> tuple[bool, list[str]]:
        """Gate: a repair must clear the exact check that caught it to be re-trusted."""
        reasons = self.violations(value)
        return (not reasons), reasons

    def live(self, pipeline: GeneratedPipeline) -> bool:
        return bool(self.fingerprint) and boundary_fingerprint(pipeline, self.boundary) == self.fingerprint

    def violations(self, value: Any) -> list[str]:
        found: list[str] = []
        observed = features(value)
        for check in self.checks:
            kind = check["kind"]
            if "path" in check:
                path = check["path"]
                if kind == "required_field" and ("presence", path) not in observed:
                    found.append(f"{path} absent, present across {self.support} healthy runs")
                elif kind == "min_items":
                    n = observed.get(("count", path))
                    if n is not None and n < check["floor"]:
                        found.append(f"{path} holds {n}, at least {check['floor']} when healthy")
                elif kind == "min_each":
                    n = observed.get(("mincount", path))
                    if n is not None and n < check["floor"]:
                        found.append(f"an entry of {path} holds {n}, at least {check['floor']} when healthy")
                elif kind == "homogeneous":
                    if ("vocab", path) not in observed and ("count", path) in observed:
                        found.append(f"{path} is no longer a homogeneous list of identifiers")
                elif kind == "known_vocabulary":
                    seen = observed.get(("vocab", path))
                    if seen is not None and (set(seen) - set(check["allowed"])):
                        found.append(f"{path} carries values unseen in {self.support} healthy runs")
                elif kind == "ordering":
                    if observed.get(("order", path)) != check["direction"]:
                        found.append(f"{path} not {check['direction']}, was across healthy runs")
                continue
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

# ---------------------------------------------------------------------------
# Population-mined scars, trust propagation, and repair gating.
#
# Minting from a single healthy observation only works when the pipeline is
# deterministic. On real data every honest run differs, so a one-pair diff cannot
# separate "this property is invariant" from "this was today's value", and the scar
# fires on legitimate variation. Features are therefore extracted structurally and
# mined across a population of healthy runs; only properties that hold throughout it
# and break in the faulty one become checks.
# ---------------------------------------------------------------------------

CONTAMINATED = "contaminated"


def _order_of(items: list) -> str | None:
    if len(items) < 2:
        return None
    keys = [_sort_key(i) for i in items]
    if keys == sorted(keys):
        return "ascending"
    if keys == sorted(keys, reverse=True):
        return "descending"
    return None


def features(value: Any, prefix: str = "") -> dict[tuple[str, str], Any]:
    """Structural features of a captured value, descending into records inside lists."""
    found: dict[tuple[str, str], Any] = {}
    if not isinstance(value, dict):
        return found
    for key in value:
        path = f"{prefix}{key}"
        item = value[key]
        found[("presence", path)] = True
        if isinstance(item, (list, tuple)):
            items = list(item)
            found[("count", path)] = len(items)
            if items and all(isinstance(i, str) for i in items):
                found[("vocab", path)] = frozenset(items)
                order = _order_of(items)
                if order:
                    found[("order", path)] = order
            elif items and all(isinstance(i, dict) for i in items):
                order = _order_of(items)
                if order:
                    found[("order", path)] = order
                shared = set(items[0])
                for i in items[1:]:
                    shared &= set(i)
                for sub in sorted(shared):
                    subpath = f"{path}[].{sub}"
                    found[("presence", subpath)] = True
                    values = [i[sub] for i in items]
                    if all(isinstance(v, str) for v in values):
                        found[("vocab", subpath)] = frozenset(values)
                    elif all(isinstance(v, (list, tuple)) for v in values):
                        # A list nested inside a record: one shortened entry is only
                        # visible in the aggregate, so both totals and the floor matter.
                        found[("count", subpath)] = sum(len(v) for v in values)
                        found[("mincount", subpath)] = min(len(v) for v in values)
        elif isinstance(item, dict):
            found.update(features(item, prefix=f"{path}."))
    return found


def mint_from_population(*, boundary: str, pipeline: GeneratedPipeline,
                         healthy_values: list[Any], faulty_value: Any,
                         provenance: str) -> Scar:
    """Scar only what held across every healthy observation and broke in the faulty one.

    Protocol constraint: the faulty observation must be one of the healthy ones plus the
    fault. Drawing it from a different generative process mines the difference between
    the processes, not the fault, and produces checks that fire on every honest run.
    """
    if not healthy_values:
        raise ValueError("population minting needs at least one healthy observation")
    pop = [features(v) for v in healthy_values]
    bad = features(faulty_value)
    checks: list[dict[str, Any]] = []

    presences = {k for k in pop[0] if k[0] == "presence"}
    for obs in pop[1:]:
        presences &= {k for k in obs if k[0] == "presence"}
    for _, path in sorted(presences):
        if ("presence", path) not in bad:
            checks.append({"kind": "required_field", "path": path})

    counts = {k[1] for k in pop[0] if k[0] == "count"}
    for obs in pop[1:]:
        counts &= {k[1] for k in obs if k[0] == "count"}
    for path in sorted(counts):
        floor = min(obs[("count", path)] for obs in pop)
        seen = bad.get(("count", path))
        if seen is not None and seen < floor:
            checks.append({"kind": "min_items", "path": path, "floor": floor})

    mins = {k[1] for k in pop[0] if k[0] == "mincount"}
    for obs in pop[1:]:
        mins &= {k[1] for k in obs if k[0] == "mincount"}
    for path in sorted(mins):
        floor = min(obs[("mincount", path)] for obs in pop)
        seen = bad.get(("mincount", path))
        if seen is not None and seen < floor:
            checks.append({"kind": "min_each", "path": path, "floor": floor})

    vocabs = {k[1] for k in pop[0] if k[0] == "vocab"}
    for obs in pop[1:]:
        vocabs &= {k[1] for k in obs if k[0] == "vocab"}
    for path in sorted(vocabs):
        allowed: set[str] = set()
        saturated = len(pop) >= 3
        for index, obs in enumerate(pop):
            values = set(obs[("vocab", path)])
            # A domain still admitting new values late in the population is open, and a
            # vocabulary check over it will fire on an honest run sooner or later.
            if index >= max(2, len(pop) // 2) and (values - allowed):
                saturated = False
            allowed |= values
        seen = bad.get(("vocab", path))
        if not saturated and seen is not None and (set(seen) - allowed):
            continue  # open domain: an unseen value here is not evidence of a fault
        if seen is None and ("count", path) in bad:
            # The list survives but stopped being homogeneous strings, so the vocabulary
            # feature vanished rather than changed. A null identifier looks like this.
            checks.append({"kind": "homogeneous", "path": path})
        elif seen is not None and (set(seen) - allowed):
            checks.append({"kind": "known_vocabulary", "path": path, "allowed": sorted(allowed)})

    orders = {k[1] for k in pop[0] if k[0] == "order"}
    for obs in pop[1:]:
        orders &= {k[1] for k in obs if k[0] == "order"}
    for path in sorted(orders):
        held = {obs[("order", path)] for obs in pop}
        if len(held) == 1 and bad.get(("order", path)) != next(iter(held)):
            checks.append({"kind": "ordering", "path": path, "direction": next(iter(held))})

    if not checks:
        raise ValueError(
            f"the difference at {boundary!r} is not expressible as a check that held "
            "across the healthy population; storing it as vague suspicion would spend "
            "the zero false-suspicion budget")
    return Scar(boundary=boundary, fingerprint=boundary_fingerprint(pipeline, boundary),
                provenance=provenance, checks=checks, support=len(healthy_values))


def healthy_variants(n: int) -> list[dict[str, Any]]:
    """Legitimately varying healthy cassettes: same sources and counts, different text.

    This is the variation a real corpus has and a deterministic fixture does not, and it
    is what a single-pair scar mistakes for a fault.
    """
    from . import cassette_corpus as _cc
    out = []
    for seed in range(n):
        cassette = {sid: dict(doc) for sid, doc in _cc.BASE_CASSETTE.items()}
        for sid, doc in cassette.items():
            doc["quotes"] = [f"{sid} practitioner statement {seed}-{i}"
                             for i in range(1, len(doc["quotes"]) + 1)]
            doc["published"] = f"2026-0{(seed % 9) + 1}-15"
        out.append(cassette)
    return out


def propagate_trust(pipeline: GeneratedPipeline, boundaries: list[str],
                    labels: dict[str, str]) -> dict[str, str]:
    """Trust as a property of the graph rather than of each node in isolation.

    A boundary whose own checks pass but whose inputs are untrusted is not trusted; it
    is contaminated, which is a different state and a different remedy. Distinguishing
    them is what makes a downstream blame arithmetically inconsistent rather than merely
    unlikely.
    """
    from .fault_injection import _dataflow_edges, _entry_source

    edges = _dataflow_edges(_entry_source(pipeline))
    upstream: dict[str, set[str]] = {b: set() for b in boundaries}
    changed = True
    while changed:
        changed = False
        for producer, consumer in edges:
            if consumer not in upstream:
                continue
            grown = {producer} | upstream.get(producer, set())
            if not grown <= upstream[consumer]:
                upstream[consumer] |= grown
                changed = True

    resolved: dict[str, str] = {}
    for b in boundaries:
        own = labels.get(b, TRUSTED)
        if own == SUSPECT:
            resolved[b] = SUSPECT
        elif any(labels.get(u) == SUSPECT for u in upstream[b] if u in labels):
            resolved[b] = CONTAMINATED
        else:
            resolved[b] = TRUSTED
    return resolved


IMPLICATED = "implicated"


def attribute_upstream(pipeline: GeneratedPipeline, boundaries: list[str],
                       labels: dict[str, str]) -> dict[str, str]:
    """Backward attribution: narrow to the boundaries that could explain a suspect one.

    Forward propagation marks what a known-bad boundary spoiled. It cannot help when the
    declared checks fire only downstream of the fault, which is the common case: a stage
    that faithfully passes on a bad input satisfies every criterion about its own
    behaviour, so the suspect set sits entirely downstream of the cause. This is the
    deterministic twin of the downstream-blame bias the model judges showed.

    The honest output is a candidate set rather than a culprit. Every unflagged ancestor
    of the earliest suspect boundary could explain it, and nothing declared enough to
    separate them; naming one would be a guess dressed as a computation. The set is what
    a bisection or a model should be handed.
    """
    from .fault_injection import _dataflow_edges, _entry_source

    edges = {(p, c) for p, c in _dataflow_edges(_entry_source(pipeline))
             if p in boundaries and c in boundaries}
    ancestors: dict[str, set[str]] = {b: set() for b in boundaries}
    changed = True
    while changed:
        changed = False
        for producer, consumer in edges:
            grown = {producer} | ancestors[producer]
            if not grown <= ancestors[consumer]:
                ancestors[consumer] |= grown
                changed = True

    resolved = dict(labels)
    suspects = [b for b in boundaries if labels.get(b) == SUSPECT]
    if not suspects:
        return resolved
    earliest = min(suspects, key=boundaries.index)
    for parent in ancestors[earliest]:
        if resolved.get(parent, TRUSTED) == TRUSTED:
            resolved[parent] = IMPLICATED
    return resolved
