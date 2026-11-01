"""Evidence packages for the seven reviewer arms and the rewired-edge test."""
from __future__ import annotations

import json
import re
import zlib

from rdr.graph import (build_graph, call_node, edge_counts, fake_writes, neighbourhood, random_subgraph, rec_node, render,
                       rewire_one, strip_ignored)
from rdr.trace import Trace

ARMS = ("A", "B", "C", "D", "E", "F", "G")
FORBIDDEN = re.compile(
    r"(?<![a-z0-9])(inject[a-z]*|fault[a-z]*|stale|repair[a-z]*|decoy[a-z]*|gold|truth)(?![a-z])", re.IGNORECASE)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class LeakageError(ValueError):
    pass


def seed_for(instance_id: str) -> int:
    return zlib.crc32(instance_id.encode("utf-8"))


def check_leakage(text: str, forbidden=FORBIDDEN, extra_forbidden: re.Pattern | None = None) -> None:
    """Raise on a forbidden word. With IGNORECASE the lookahead cannot see the end of `goldRun`, so the
    forbidden pattern is also tried on the text with camelCase boundaries split (`gold Run`)."""
    for candidate in (text, _CAMEL_BOUNDARY.sub(" ", text)):
        match = forbidden.search(candidate)
        if match:
            raise LeakageError(match.group(0))
    match = extra_forbidden.search(text) if extra_forbidden else None
    if match:
        raise LeakageError(match.group(0))


def _header(trace: Trace, symptom: str) -> list[str]:
    final = {record: strip_ignored(row) for record, row in trace.final_values().items()}
    lines = ["TASK", trace.instruction, "",
             "AGENT FINAL MESSAGE", trace.final_message, "",
             "USER REPORT", f"A user reports that record {symptom} looks wrong.", "",
             "FINAL STATE OF RECORDS THE AGENT CHANGED"]
    lines += [f"{record} = {json.dumps(final[record], sort_keys=True, default=str)}" for record in sorted(final)]
    lines += ["", "CALLS MADE (index and API only)"]
    lines += [f"{call.index} {call.name}" for call in trace.calls]
    return lines


def _action_log(trace: Trace) -> list[str]:
    lines = ["ACTION LOG"]
    for call in trace.calls:
        args = json.dumps(strip_ignored(call.args), sort_keys=True)
        response = json.dumps(strip_ignored(call.response), sort_keys=True, default=str)
        lines.append(f"[{call.index}] {call.name}({args}) -> {response}")
    return lines


def build_package(arm: str, trace: Trace, symptom: str, instance_id: str, avoid_calls=frozenset(),
                  d_hops: int = 2, extra_forbidden: re.Pattern | None = None) -> str:
    """`avoid_calls` (call indices) is never printed; arm F uses it to keep the fake graph off the origin."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    graph = build_graph(trace)
    seed = seed_for(instance_id)
    lines = _header(trace, symptom)
    if arm == "B":
        lines += ["", *_action_log(trace)]
    elif arm == "C":
        lines += ["", "PROVENANCE GRAPH", render(graph)]
    elif arm == "D":
        lines += ["", "PROVENANCE GRAPH", render(neighbourhood(graph, rec_node(symptom), d_hops))]
    elif arm == "E":
        counts = edge_counts(neighbourhood(graph, rec_node(symptom), d_hops))
        lines += ["", "PROVENANCE GRAPH", render(random_subgraph(graph, counts, seed))]
    elif arm == "F":
        fake, _ = fake_writes(graph, rec_node(symptom), {call_node(i) for i in avoid_calls}, seed)
        lines += ["", "PROVENANCE GRAPH", render(fake)]
    elif arm == "G":
        lines += ["", *_action_log(trace), "", "PROVENANCE GRAPH", render(graph)]
    text = "\n".join(lines)
    check_leakage(text, extra_forbidden=extra_forbidden)
    return text


def build_rewired_package(trace: Trace, symptom: str, decoy_index: int) -> str:
    graph = rewire_one(build_graph(trace), rec_node(symptom), call_node(decoy_index))
    text = "\n".join([*_header(trace, symptom), "", "PROVENANCE GRAPH", render(graph)])
    check_leakage(text)
    return text
