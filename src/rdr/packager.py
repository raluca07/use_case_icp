"""Evidence packages for the seven reviewer arms and the rewired-edge test."""
from __future__ import annotations

import json
import re
import zlib

from rdr.graph import (build_graph, call_node, edge_counts, neighbourhood, random_subgraph, rec_node, render,
                       rewire_one, rewire_writes, strip_ignored)
from rdr.trace import Trace

ARMS = ("A", "B", "C", "D", "E", "F", "G")
FORBIDDEN = re.compile(r"\b(inject\w*|fault\w*|stale|repair\w*|decoy\w*|gold|truth)\b", re.IGNORECASE)
D_HOPS = 2


class LeakageError(ValueError):
    pass


def seed_for(instance_id: str) -> int:
    return zlib.crc32(instance_id.encode("utf-8"))


def check_leakage(text: str, forbidden=FORBIDDEN) -> None:
    match = forbidden.search(text)
    if match:
        raise LeakageError(match.group(0))


def _header(trace: Trace, symptom: str) -> list[str]:
    final = trace.final_values()
    lines = ["TASK", trace.instruction, "",
             "AGENT FINAL MESSAGE", trace.final_message, "",
             "USER REPORT", f"A user reports that record {symptom} looks wrong.", "",
             "FINAL STATE OF RECORDS THE AGENT CHANGED"]
    lines += [f"{record} = {json.dumps(final[record], sort_keys=True)}" for record in sorted(final)]
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


def build_package(arm: str, trace: Trace, symptom: str, instance_id: str) -> str:
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
        lines += ["", "PROVENANCE GRAPH", render(neighbourhood(graph, rec_node(symptom), D_HOPS))]
    elif arm == "E":
        counts = edge_counts(neighbourhood(graph, rec_node(symptom), D_HOPS))
        lines += ["", "PROVENANCE GRAPH", render(random_subgraph(graph, counts, seed))]
    elif arm == "F":
        lines += ["", "PROVENANCE GRAPH", render(rewire_writes(graph, seed))]
    elif arm == "G":
        lines += ["", *_action_log(trace), "", "PROVENANCE GRAPH", render(graph)]
    text = "\n".join(lines)
    check_leakage(text)
    return text


def build_rewired_package(trace: Trace, symptom: str, decoy_index: int) -> str:
    graph = rewire_one(build_graph(trace), rec_node(symptom), call_node(decoy_index))
    text = "\n".join([*_header(trace, symptom), "", "PROVENANCE GRAPH", render(graph)])
    check_leakage(text)
    return text
