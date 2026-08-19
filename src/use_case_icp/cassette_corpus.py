"""Faults injected into recorded responses, leaving the pipeline source untouched.

Mutating source makes a static slice of the code close to a giveaway, because the fault
is literally written there. Real faults in this system arrive through fetched content:
a source returns fewer records than it claims, a stale copy, a mislabelled identifier.
Here the code is byte-identical across every case and only the recorded responses差, so
static inspection has nothing to find and captured values are the only place the fault
is visible.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import io
from dataclasses import dataclass
from typing import Any

from .fault_scoring import Contract, _DEFINITION_NODES
from .records import GeneratedFile, GeneratedPipeline

BOUNDARIES = [
    "define_research_plan",
    "retrieve_registries",
    "retrieve_trackers",
    "retrieve_vendor_docs",
    "merge_sources",
    "extract_evidence_records",
    "synthesize_market_demand",
]

# One source of truth for which stage first consumes which recorded response.
CLASS_OF_STAGE = {
    "retrieve_registries": "registries",
    "retrieve_trackers": "issue_trackers",
    "retrieve_vendor_docs": "vendor_docs",
}

PIPELINE_SOURCE = '''import json

def fetch(source_id):
    return CASSETTE[source_id]

def define_research_plan():
    return {
        "questions": ["what do agent builders lack", "what do they pay for"],
        "source_classes": ["registries", "issue_trackers", "vendor_docs"],
        "minimum_sources": 6,
    }

def retrieve_registries(plan):
    ids = ["registry_alpha", "registry_beta", "registry_gamma", "registry_delta", "registry_epsilon"]
    docs = [fetch(i) for i in ids]
    return {"source_class": "registries", "documents": docs,
            "source_ids": [d.get("id") for d in docs]}

def retrieve_trackers(plan):
    ids = ["tracker_delta", "tracker_epsilon", "tracker_theta", "tracker_iota"]
    docs = [fetch(i) for i in ids]
    return {"source_class": "issue_trackers", "documents": docs,
            "source_ids": [d.get("id") for d in docs]}

def retrieve_vendor_docs(plan):
    ids = ["docs_zeta", "docs_eta", "docs_kappa", "docs_lambda"]
    docs = [fetch(i) for i in ids]
    return {"source_class": "vendor_docs", "documents": docs,
            "source_ids": [d.get("id") for d in docs]}

def merge_sources(registries, trackers, vendor):
    documents = []
    for part in (registries, trackers, vendor):
        documents.extend(part.get("documents", []))
    return {"documents": documents, "classes_merged": 3,
            "source_ids": [d.get("id") for d in documents]}

def extract_evidence_records(merged):
    records = []
    for doc in merged.get("documents", []):
        for quote in doc.get("quotes", []):
            records.append({"source_id": doc.get("id"), "quote": quote,
                            "published": doc.get("published")})
    return {"records": records, "source_ids": merged.get("source_ids", [])}

def synthesize_market_demand(evidence):
    needs = []
    for record in evidence.get("records", []):
        needs.append({"need_id": record.get("source_id"), "support": record.get("quote")})
    ranked = sorted(needs, key=lambda item: str(item.get("need_id")))
    return {"needs": ranked, "record_count": len(evidence.get("records", []))}

plan = define_research_plan()
registries = retrieve_registries(plan)
trackers = retrieve_trackers(plan)
vendor = retrieve_vendor_docs(plan)
merged = merge_sources(registries, trackers, vendor)
evidence = extract_evidence_records(merged)
demand = synthesize_market_demand(evidence)
print(json.dumps(demand, sort_keys=True))
'''


def _doc(source_id: str, n_quotes: int = 2) -> dict[str, Any]:
    return {
        "id": source_id,
        "published": "2026-07-30",
        "quotes": [f"{source_id} practitioner statement {i}" for i in range(1, n_quotes + 1)],
    }


BASE_CASSETTE: dict[str, dict[str, Any]] = {
    sid: _doc(sid)
    for sid in ["registry_alpha", "registry_beta", "registry_gamma", "registry_delta",
                "registry_epsilon", "tracker_delta", "tracker_epsilon", "tracker_theta",
                "tracker_iota", "docs_zeta", "docs_eta", "docs_kappa", "docs_lambda"]
}

SOURCE_OWNER = {
    "registry_alpha": "retrieve_registries", "registry_beta": "retrieve_registries",
    "registry_gamma": "retrieve_registries", "registry_delta": "retrieve_registries",
    "registry_epsilon": "retrieve_registries",
    "tracker_delta": "retrieve_trackers", "tracker_epsilon": "retrieve_trackers",
    "tracker_theta": "retrieve_trackers", "tracker_iota": "retrieve_trackers",
    "docs_zeta": "retrieve_vendor_docs", "docs_eta": "retrieve_vendor_docs",
    "docs_kappa": "retrieve_vendor_docs", "docs_lambda": "retrieve_vendor_docs",
}

DOWNSTREAM = {
    "retrieve_registries": ["merge_sources", "extract_evidence_records", "synthesize_market_demand"],
    "retrieve_trackers": ["merge_sources", "extract_evidence_records", "synthesize_market_demand"],
    "retrieve_vendor_docs": ["merge_sources", "extract_evidence_records", "synthesize_market_demand"],
}


def build_pipeline() -> GeneratedPipeline:
    return GeneratedPipeline("pipeline.py", [GeneratedFile("pipeline.py", PIPELINE_SOURCE)],
                             [{"function_name": b} for b in BOUNDARIES])


# ---- cassette mutations: the fault lives here, never in the source ----

def _truncate_quotes(doc): doc["quotes"] = doc["quotes"][:1]
def _empty_quotes(doc): doc["quotes"] = []
def _drop_published(doc): doc.pop("published", None)
def _stale_published(doc): doc["published"] = "2019-01-01"
def _mislabel_id(doc): doc["id"] = "registry_alpha"
def _duplicate_quote(doc): doc["quotes"] = [doc["quotes"][0], doc["quotes"][0]]
def _blank_id(doc): doc["id"] = None

MUTATIONS = {
    "truncated_response": ("observed", _truncate_quotes),
    "empty_response": ("observed", _empty_quotes),
    "missing_date": ("observed", _drop_published),
    "stale_copy": ("observed", _stale_published),
    "mislabelled_id": ("observed", _mislabel_id),
    "duplicated_record": ("synthetic", _duplicate_quote),
    "null_identifier": ("synthetic", _blank_id),
}


@dataclass(frozen=True)
class CassetteCase:
    case_id: str
    mutation: str
    provenance: str
    source_id: str
    boundary: str
    contaminates: list[str]
    cassette: dict[str, Any]


def build_corpus() -> list[CassetteCase]:
    cases = []
    for name, (provenance, fn) in MUTATIONS.items():
        for source_id in BASE_CASSETTE:
            cassette = copy.deepcopy(BASE_CASSETTE)
            before = copy.deepcopy(cassette[source_id])
            fn(cassette[source_id])
            if cassette[source_id] == before:
                continue
            owner = SOURCE_OWNER[source_id]
            cases.append(CassetteCase(
                case_id=f"{name}|{source_id}", mutation=name, provenance=provenance,
                source_id=source_id, boundary=owner,
                contaminates=DOWNSTREAM[owner], cassette=cassette))
    return cases


def capture(cassette: dict[str, Any]) -> dict[str, Any]:
    """Run the untouched pipeline against a given cassette, recording each boundary."""
    tree = ast.parse(PIPELINE_SOURCE)
    defs = [n for n in tree.body if isinstance(n, _DEFINITION_NODES)]
    rest = [n for n in tree.body if not isinstance(n, _DEFINITION_NODES)]
    ns: dict[str, Any] = {"__name__": "__pipeline__", "CASSETTE": cassette}
    exec(compile(ast.Module(body=defs, type_ignores=[]), "pipeline.py", "exec"), ns)
    out: dict[str, Any] = {}

    def wrap(name, fn):
        def rec(*a, **k):
            v = fn(*a, **k); out[name] = v; return v
        return rec

    for b in BOUNDARIES:
        if callable(ns.get(b)):
            ns[b] = wrap(b, ns[b])
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(ast.Module(body=rest, type_ignores=[]), "pipeline.py", "exec"), ns)
    return out


INTENT = {
    "define_research_plan": "Declare the research questions, the source classes to consult, and the minimum sources a finding needs.",
    "retrieve_registries": "Fetch every registry source and return its documents and identifiers.",
    "retrieve_trackers": "Fetch every issue-tracker source and return its documents and identifiers.",
    "retrieve_vendor_docs": "Fetch every vendor-documentation source and return its documents and identifiers.",
    "merge_sources": "Combine documents from every retrieval branch into one list.",
    "extract_evidence_records": "Turn documents into evidence records, each carrying its source, a quote and a publication date.",
    "synthesize_market_demand": "Turn evidence records into ranked market needs, each traceable to supporting evidence.",
}

CONTRACTS = {
    "retrieve_registries": Contract("retrieve_registries", required_fields=["source_ids", "documents"], min_items={"source_ids": 5}),
    "retrieve_trackers": Contract("retrieve_trackers", required_fields=["source_ids", "documents"], min_items={"source_ids": 4}),
    "retrieve_vendor_docs": Contract("retrieve_vendor_docs", required_fields=["source_ids", "documents"], min_items={"source_ids": 4}),
    "merge_sources": Contract("merge_sources", required_fields=["documents"], min_items={"documents": 13}),
    "extract_evidence_records": Contract("extract_evidence_records", required_fields=["records"], min_items={"records": 26}),
    "synthesize_market_demand": Contract("synthesize_market_demand", required_fields=["needs"], min_items={"needs": 26}),
}
