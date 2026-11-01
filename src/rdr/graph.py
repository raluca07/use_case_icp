"""Provenance graph built from a Trace: call nodes, record nodes, typed edges."""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from rdr.trace import Trace

IGNORED_KEYS = frozenset({"access_token", "refresh_token", "password", "api_key", "otp", "secret"})


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str


@dataclass
class Graph:
    call_nodes: dict[str, str]
    record_nodes: list[str]
    edges: list[Edge] = field(default_factory=list)


def call_node(index: int) -> str:
    return f"call:{index}"


def rec_node(record: str) -> str:
    return f"rec:{record}"


def strip_ignored(obj):
    if isinstance(obj, dict):
        return {k: strip_ignored(v) for k, v in obj.items() if k not in IGNORED_KEYS}
    if isinstance(obj, list):
        return [strip_ignored(v) for v in obj]
    return obj


def _is_id_key(key) -> bool:
    return isinstance(key, str) and (key == "id" or key.endswith(("_id", "_ids", "_ref")))


def _number_text(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _collect(obj, numbers_anywhere: bool, id_context: bool, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key not in IGNORED_KEYS:
                _collect(value, numbers_anywhere, _is_id_key(key), out)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _collect(value, numbers_anywhere, id_context, out)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, str):
        if len(obj) >= 3:
            out.add(obj)
    elif isinstance(obj, (int, float)):
        if numbers_anywhere or id_context:
            out.add(_number_text(obj))


def argument_values(args) -> set[str]:
    """Strings of length >= 3 anywhere, numbers only under ID-like keys (`id`, `*_id`, `*_ids`, `*_ref`)."""
    out: set[str] = set()
    _collect(args, False, False, out)
    return out


def response_values(response) -> set[str]:
    """Strings of length >= 3 and numbers of any length under any key."""
    out: set[str] = set()
    _collect(response, True, True, out)
    return out


def _row_id(record: str) -> str:
    return record.split("#", 1)[1]


def _fmt_args(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in sorted(args.items()) if k not in IGNORED_KEYS)


def _dedupe(edges: list[Edge]) -> list[Edge]:
    seen: set[Edge] = set()
    out: list[Edge] = []
    for edge in edges:
        if edge not in seen:
            seen.add(edge)
            out.append(edge)
    return out


def build_graph(trace: Trace) -> Graph:
    call_nodes = {call_node(c.index): f"{c.index} {c.name}({_fmt_args(c.args)})" for c in trace.calls}
    records = trace.touched_records()
    created_at: dict[str, int] = {}
    seen: set[str] = set()
    for position, call in enumerate(trace.calls):
        for write in call.writes:
            if write.record not in seen:
                seen.add(write.record)
                if write.before is None:
                    created_at[write.record] = position
    arg_values = [argument_values(c.args) for c in trace.calls]
    resp_values = [response_values(c.response) for c in trace.calls]
    edges: list[Edge] = []
    for call in trace.calls:
        for write in call.writes:
            edges.append(Edge(call_node(call.index), rec_node(write.record), "writes"))
    for position, call in enumerate(trace.calls):
        written = {w.record for w in call.writes}
        for record in records:
            if record in written or _row_id(record) not in arg_values[position]:
                continue
            if record in created_at and position <= created_at[record]:
                continue
            edges.append(Edge(rec_node(record), call_node(call.index), "reads"))
    producers: dict[str, list[int]] = {}
    for position, call in enumerate(trace.calls):
        for earlier in sorted({p for value in arg_values[position] for p in producers.get(value, ())}):
            edges.append(Edge(call_node(trace.calls[earlier].index), call_node(call.index), "feeds"))
        for value in resp_values[position]:
            producers.setdefault(value, []).append(position)
    return Graph(call_nodes, [rec_node(r) for r in records], _dedupe(edges))


def edge_counts(graph: Graph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in graph.edges:
        counts[edge.kind] = counts.get(edge.kind, 0) + 1
    return counts


def _restrict(graph: Graph, keep: set[str], edges: list[Edge] | None = None) -> Graph:
    chosen = edges if edges is not None else [e for e in graph.edges if e.src in keep and e.dst in keep]
    return Graph({k: v for k, v in graph.call_nodes.items() if k in keep},
                 [r for r in graph.record_nodes if r in keep], chosen)


def neighbourhood(graph: Graph, center: str, hops: int) -> Graph:
    adjacent: dict[str, set[str]] = {}
    for edge in graph.edges:
        adjacent.setdefault(edge.src, set()).add(edge.dst)
        adjacent.setdefault(edge.dst, set()).add(edge.src)
    keep = {center}
    frontier = deque([(center, 0)])
    while frontier:
        node, distance = frontier.popleft()
        if distance == hops:
            continue
        for neighbour in adjacent.get(node, ()):
            if neighbour not in keep:
                keep.add(neighbour)
                frontier.append((neighbour, distance + 1))
    return _restrict(graph, keep)


def random_subgraph(graph: Graph, counts: dict[str, int], seed: int) -> Graph:
    rng = random.Random(seed)
    chosen: set[Edge] = set()
    for kind in sorted(counts):
        pool = [e for e in graph.edges if e.kind == kind]
        chosen |= set(rng.sample(pool, min(counts[kind], len(pool))))
    keep = {e.src for e in chosen} | {e.dst for e in chosen}
    return _restrict(graph, keep, [e for e in graph.edges if e in chosen])


def rewire_writes(graph: Graph, seed: int) -> Graph:
    rng = random.Random(seed)
    writes = [e for e in graph.edges if e.kind == "writes"]
    sources = [e.src for e in writes]
    permuted = sources[:]
    for _ in range(100):
        rng.shuffle(permuted)
        if all(new != old for new, old in zip(permuted, sources)):
            break
    replacements = iter(Edge(src, e.dst, "writes") for src, e in zip(permuted, writes))
    edges = [next(replacements) if e.kind == "writes" else e for e in graph.edges]
    if {e for e in edges if e.kind == "writes"} == set(writes):
        raise ValueError("rewiring left the writes edges unchanged")
    return Graph(dict(graph.call_nodes), list(graph.record_nodes), _dedupe(edges))


def rewire_one(graph: Graph, record_node: str, decoy_node: str) -> Graph:
    if decoy_node not in graph.call_nodes:
        raise ValueError(f"decoy {decoy_node} is not a call node of the graph")
    if Edge(decoy_node, record_node, "writes") in graph.edges:
        raise ValueError(f"decoy {decoy_node} already writes {record_node}")
    edges = [Edge(decoy_node, e.dst, "writes") if e.kind == "writes" and e.dst == record_node else e
             for e in graph.edges]
    return Graph(dict(graph.call_nodes), list(graph.record_nodes), _dedupe(edges))


def _node_key(node: str) -> tuple:
    kind, _, rest = node.partition(":")
    return (0, int(rest), "") if kind == "call" else (1, 0, rest)


def render(graph: Graph) -> str:
    lines = ["NODES"]
    lines += [f"{n} = {graph.call_nodes[n]}" for n in sorted(graph.call_nodes, key=_node_key)]
    lines += sorted(graph.record_nodes)
    lines.append("EDGES")
    lines += [f"{e.src} -{e.kind}-> {e.dst}"
              for e in sorted(graph.edges, key=lambda e: (_node_key(e.src), e.kind, _node_key(e.dst)))]
    return "\n".join(lines)
