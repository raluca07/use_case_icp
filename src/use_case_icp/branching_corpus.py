"""A branching pipeline, where source order and dataflow order disagree.

In a straight-line pipeline the causal root of a set of flagged boundaries is simply
the earliest of them, so a selector that consults the dataflow graph and one that
walks the source in order cannot disagree. Any measured advantage for the graph would
be an artifact of the shape of the pipeline rather than of the graph.

This pipeline branches, and its functions are defined in an order that does not match
the order they run in, which is what a model writing code actually produces. Here the
two selectors can and do disagree.
"""

from __future__ import annotations

from typing import Any

from .fault_scoring import Contract
from .records import GeneratedFile, GeneratedPipeline

# Declaration order deliberately differs from execution order.
BOUNDARIES = [
    "synthesize_market_demand",
    "retrieve_registries",
    "extract_evidence_records",
    "define_research_plan",
    "merge_sources",
    "retrieve_trackers",
    "retrieve_vendor_docs",
]

PIPELINE_SOURCE = '''import json

def synthesize_market_demand(evidence):
    needs = []
    for record in evidence.get("records", []):
        needs.append({
            "need_id": record.get("source_id", "unattributed"),
            "support": record.get("quote", "no quote recorded"),
        })
    ranked = sorted(needs, key=lambda item: item.get("need_id", ""))
    return {"needs": ranked, "record_count": len(evidence.get("records", []))}

def retrieve_registries(plan):
    known = ["registry_alpha", "registry_beta", "registry_gamma"]
    return {"source_ids": known, "source_class": "registries"}

def extract_evidence_records(merged):
    records = []
    for source_id in merged.get("source_ids", []):
        if len(source_id) > 3:
            records.append({"source_id": source_id, "quote": "observed practitioner statement"})
    return {"records": records, "source_ids": merged.get("source_ids", [])}

def define_research_plan():
    return {
        "questions": ["what do agent builders lack", "what do they pay for"],
        "source_classes": ["registries", "issue_trackers", "vendor_docs"],
        "minimum_sources": 6,
    }

def merge_sources(registries, trackers, vendor):
    combined = []
    for part in (registries, trackers, vendor):
        combined.extend(part.get("source_ids", []))
    return {"source_ids": combined, "classes_merged": 3}

def retrieve_trackers(plan):
    known = ["tracker_delta", "tracker_epsilon"]
    return {"source_ids": known, "source_class": "issue_trackers"}

def retrieve_vendor_docs(plan):
    known = ["docs_zeta", "docs_eta"]
    return {"source_ids": known, "source_class": "vendor_docs"}

plan = define_research_plan()
registries = retrieve_registries(plan)
trackers = retrieve_trackers(plan)
vendor = retrieve_vendor_docs(plan)
merged = merge_sources(registries, trackers, vendor)
evidence = extract_evidence_records(merged)
demand = synthesize_market_demand(evidence)
print(json.dumps(demand, sort_keys=True))
'''

SCHEMAS: dict[str, dict[str, Any]] = {
    "define_research_plan": {"type": "object", "required": ["questions", "source_classes", "minimum_sources"]},
    "retrieve_registries": {"type": "object", "required": ["source_ids", "source_class"]},
    "retrieve_trackers": {"type": "object", "required": ["source_ids", "source_class"]},
    "retrieve_vendor_docs": {"type": "object", "required": ["source_ids", "source_class"]},
    "merge_sources": {"type": "object", "required": ["source_ids", "classes_merged"]},
    "extract_evidence_records": {"type": "object", "required": ["records", "source_ids"]},
    "synthesize_market_demand": {"type": "object", "required": ["needs", "record_count"]},
}

CONTRACTS: dict[str, Contract] = {
    "define_research_plan": Contract(
        function="define_research_plan",
        required_fields=["questions", "source_classes", "minimum_sources"],
        min_items={"questions": 2, "source_classes": 3},
    ),
    "retrieve_registries": Contract(
        function="retrieve_registries",
        required_fields=["source_ids", "source_class"],
        min_items={"source_ids": 3},
        field_pattern={"source_ids": r"^[a-z]+_[a-z]+$"},
    ),
    "retrieve_trackers": Contract(
        function="retrieve_trackers",
        required_fields=["source_ids", "source_class"],
        min_items={"source_ids": 2},
        field_pattern={"source_ids": r"^[a-z]+_[a-z]+$"},
    ),
    "retrieve_vendor_docs": Contract(
        function="retrieve_vendor_docs",
        required_fields=["source_ids", "source_class"],
        min_items={"source_ids": 2},
        field_pattern={"source_ids": r"^[a-z]+_[a-z]+$"},
    ),
    "merge_sources": Contract(
        function="merge_sources",
        required_fields=["source_ids", "classes_merged"],
        min_items={"source_ids": 7},
    ),
    "extract_evidence_records": Contract(
        function="extract_evidence_records",
        required_fields=["records", "source_ids"],
        min_items={"records": 7},
    ),
    "synthesize_market_demand": Contract(
        function="synthesize_market_demand",
        required_fields=["needs", "record_count"],
        min_items={"needs": 7},
    ),
}


def build_pipeline() -> GeneratedPipeline:
    return GeneratedPipeline(
        "pipeline.py",
        [GeneratedFile("pipeline.py", PIPELINE_SOURCE)],
        [{"function_name": name} for name in BOUNDARIES],
    )
