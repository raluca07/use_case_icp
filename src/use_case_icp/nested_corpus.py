"""A pipeline with real nesting, so collapsed-helper selection has something to collapse.

Raluca's etiq_selected sends nodes at exactly the boundary's function-stack level, names
the nested helpers without their contents, and lets the reviewer request one direct child
at a time for at most three rounds. That protocol can only be evaluated on a pipeline
whose boundaries call helpers, which the flat corpora do not. Faults are planted at three
depths: visible at the boundary, inside a helper, and inside a sub-helper.
"""
from __future__ import annotations
import copy
from typing import Any

BOUNDARIES = ["define_research_plan", "retrieve_public_sources",
              "extract_evidence_records", "synthesize_market_demand"]

SOURCES = {
    f"src_{k}": {"id": f"src_{k}", "quotes": [f"practitioner note {k}.1", f"practitioner note {k}.2"],
                 "kind": "registry" if k < 3 else "tracker", "published": "2026-07-30"}
    for k in range(6)
}

# depth 0 = boundary body, 1 = helper, 2 = sub-helper
FAULTS: dict[str, dict[str, Any]] = {
    "plan_drops_class":      {"boundary": "define_research_plan",     "depth": 0, "helper": None},
    "fetch_skips_source":    {"boundary": "retrieve_public_sources",  "depth": 1, "helper": "_fetch_class"},
    "filter_wrong_pred":     {"boundary": "retrieve_public_sources",  "depth": 2, "helper": "_is_eligible"},
    "extract_drops_quote":   {"boundary": "extract_evidence_records", "depth": 1, "helper": "_quotes_of"},
    "extract_bad_attrib":    {"boundary": "extract_evidence_records", "depth": 2, "helper": "_attribute"},
    "rank_reverses":         {"boundary": "synthesize_market_demand", "depth": 1, "helper": "_rank"},
}


def run(fault: str | None = None) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Execute the pipeline, recording each function's output and its stack prefix."""
    trace: dict[str, Any] = {}
    stack: list[str] = []
    children: dict[str, list[str]] = {}

    def rec(name):
        def deco(fn):
            def wrapped(*a, **kw):
                parent = ".".join(stack) if stack else None
                stack.append(name)
                key = ".".join(stack)
                if parent is not None:
                    children.setdefault(parent, [])
                    if key not in children[parent]:
                        children[parent].append(key)
                try:
                    out = fn(*a, **kw)
                finally:
                    stack.pop()
                trace[key] = out
                return out
            return wrapped
        return deco

    @rec("_is_eligible")
    def _is_eligible(doc):
        if fault == "filter_wrong_pred":
            return doc["kind"] == "tracker"          # should accept both kinds
        return doc["kind"] in ("registry", "tracker")

    @rec("_fetch_class")
    def _fetch_class(kind, catalogue):
        docs = [d for d in catalogue.values() if d["kind"] == kind]
        if fault == "fetch_skips_source":
            docs = docs[:-1]                          # silently drops the last source
        return [d for d in docs if _is_eligible(d)]

    @rec("_quotes_of")
    def _quotes_of(doc):
        qs = list(doc["quotes"])
        if fault == "extract_drops_quote":
            qs = qs[:1]
        return qs

    @rec("_attribute")
    def _attribute(doc, quote):
        sid = doc["id"]
        if fault == "extract_bad_attrib":
            sid = "src_0"                             # every record attributed to one source
        return {"source_id": sid, "quote": quote}

    @rec("_rank")
    def _rank(needs):
        ordered = sorted(needs, key=lambda n: n["need_id"])
        if fault == "rank_reverses":
            ordered = list(reversed(ordered))
        return ordered

    @rec("define_research_plan")
    def define_research_plan():
        classes = ["registry", "tracker"]
        if fault == "plan_drops_class":
            classes = ["registry"]
        return {"source_classes": classes, "minimum_sources": 6}

    @rec("retrieve_public_sources")
    def retrieve_public_sources(plan):
        docs = []
        for kind in plan["source_classes"]:
            docs.extend(_fetch_class(kind, SOURCES))
        return {"documents": docs, "source_ids": [d["id"] for d in docs]}

    @rec("extract_evidence_records")
    def extract_evidence_records(fetched):
        records = []
        for doc in fetched["documents"]:
            for q in _quotes_of(doc):
                records.append(_attribute(doc, q))
        return {"records": records, "record_count": len(records)}

    @rec("synthesize_market_demand")
    def synthesize_market_demand(evidence):
        needs = [{"need_id": r["source_id"], "support": r["quote"]} for r in evidence["records"]]
        return {"needs": _rank(needs), "need_count": len(needs)}

    plan = define_research_plan()
    fetched = retrieve_public_sources(plan)
    evidence = extract_evidence_records(fetched)
    synthesize_market_demand(evidence)
    return trace, children


def package(trace, children, boundary, expanded: list[str]) -> dict[str, Any]:
    """Nodes at exactly the boundary's stack level, plus any helpers explicitly expanded.

    Unexpanded descendants are named but their contents withheld, which is the whole
    point of the protocol: the reviewer must ask, one direct child at a time.
    """
    visible = {boundary: trace[boundary]}
    for key in expanded:
        if key in trace:
            visible[key] = trace[key]
    frontier = []
    for parent in [boundary, *expanded]:
        for child in children.get(parent, []):
            if child not in visible:
                frontier.append(child)
    return {"visible": visible, "collapsed_helpers": sorted(set(frontier))}


def full_package(trace, boundary) -> dict[str, Any]:
    """Everything under the boundary, flattened, which is the arm to beat on cost."""
    return {"visible": {k: v for k, v in trace.items() if k == boundary or k.startswith(boundary + ".")},
            "collapsed_helpers": []}
