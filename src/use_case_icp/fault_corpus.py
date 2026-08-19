"""A corpus of injected faults over a pipeline shaped like the one under study.

The stage names mirror the run analysed in the paper: define_research_plan,
retrieve_public_sources, extract_evidence_records and synthesize_market_demand.
Every case in the corpus is one fault at one boundary with one parameter, and the
corpus is the cross product of those that actually change the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fault_injection import FAULT_CATALOGUE, InjectedPipeline, inject
from .fault_scoring import Contract
from .records import GeneratedFile, GeneratedPipeline

BOUNDARIES = [
    "define_research_plan",
    "retrieve_public_sources",
    "extract_evidence_records",
    "synthesize_market_demand",
]

PIPELINE_SOURCE = '''import json

def define_research_plan():
    return {
        "questions": ["what do agent builders lack", "what do they pay for"],
        "source_classes": ["registries", "issue_trackers", "vendor_docs"],
        "minimum_sources": 3,
    }

def retrieve_public_sources(plan):
    catalogue = {
        "registries": ["registry_alpha", "registry_beta"],
        "issue_trackers": ["tracker_gamma", "tracker_delta"],
        "vendor_docs": ["docs_epsilon"],
    }
    fetched = []
    for source_class in plan.get("source_classes", []):
        for source_id in catalogue.get(source_class, []):
            fetched.append(source_id)
    return {"source_ids": fetched, "attempted": len(fetched), "plan": plan}

def extract_evidence_records(sources):
    records = []
    for source_id in sources.get("source_ids", []):
        if len(source_id) > 3:
            records.append({"source_id": source_id, "quote": "observed practitioner statement"})
    return {"records": records, "source_ids": sources.get("source_ids", [])}

def synthesize_market_demand(evidence):
    needs = []
    for record in evidence.get("records", []):
        needs.append({
            "need_id": record.get("source_id", "unattributed"),
            "support": record.get("quote", "no quote recorded"),
        })
    ranked = sorted(needs, key=lambda item: item.get("need_id", ""))
    return {"needs": ranked, "record_count": len(evidence.get("records", []))}

plan = define_research_plan()
sources = retrieve_public_sources(plan)
evidence = extract_evidence_records(sources)
demand = synthesize_market_demand(evidence)
print(json.dumps(demand, sort_keys=True))
'''

SCHEMAS: dict[str, dict[str, Any]] = {
    "define_research_plan": {
        "type": "object",
        "required": ["questions", "source_classes", "minimum_sources"],
        "properties": {
            "questions": {"type": "array"},
            "source_classes": {"type": "array"},
            "minimum_sources": {"type": "integer"},
        },
    },
    "retrieve_public_sources": {
        "type": "object",
        "required": ["source_ids", "attempted"],
        "properties": {"source_ids": {"type": "array"}, "attempted": {"type": "integer"}},
    },
    "extract_evidence_records": {
        "type": "object",
        "required": ["records", "source_ids"],
        "properties": {"records": {"type": "array"}, "source_ids": {"type": "array"}},
    },
    "synthesize_market_demand": {
        "type": "object",
        "required": ["needs", "record_count"],
        "properties": {"needs": {"type": "array"}, "record_count": {"type": "integer"}},
    },
}

CONTRACTS: dict[str, Contract] = {
    "define_research_plan": Contract(
        function="define_research_plan",
        required_fields=["questions", "source_classes", "minimum_sources"],
        min_items={"questions": 2, "source_classes": 3},
    ),
    "retrieve_public_sources": Contract(
        function="retrieve_public_sources",
        required_fields=["source_ids", "attempted"],
        min_items={"source_ids": 5},
        field_pattern={"source_ids": r"^[a-z]+_[a-z]+$"},
    ),
    "extract_evidence_records": Contract(
        function="extract_evidence_records",
        required_fields=["records", "source_ids"],
        min_items={"records": 3},
    ),
    "synthesize_market_demand": Contract(
        function="synthesize_market_demand",
        required_fields=["needs", "record_count"],
        min_items={"needs": 3},
    ),
}

# What each stage is supposed to do, in the words a reviewer would be given.
STAGE_INTENT = {
    "define_research_plan": (
        "Declare the research questions and the classes of public source that will be "
        "consulted, plus the minimum number of sources required for a finding to count."
    ),
    "retrieve_public_sources": (
        "Fetch every source in every declared source class and report which source "
        "identifiers were retrieved and how many were attempted."
    ),
    "extract_evidence_records": (
        "Turn retrieved sources into evidence records, each carrying the source it came "
        "from and a supporting quote observed in that source."
    ),
    "synthesize_market_demand": (
        "Turn evidence records into ranked market needs, each traceable to the evidence "
        "that supports it, with the ranking in a stable declared order."
    ),
}

PARAMETERS: dict[str, list[str]] = {
    "drop_field": [
        "questions", "source_classes", "minimum_sources", "source_ids",
        "attempted", "records", "needs", "record_count", "need_id", "quote", "support",
    ],
    "fabricate_identifier": [
        "PLACEHOLDER-001", "registry_alpha", "tracker_gamma",
        "registries", "observed practitioner statement", "unverified vendor claim",
    ],
    "truncate_sequence": [""],
    "invert_comparison": [""],
    "reverse_ordering": [""],
}


@dataclass(frozen=True)
class Case:
    case_id: str
    fault_name: str
    provenance: str
    boundary: str
    parameter: str
    injected: InjectedPipeline


def build_pipeline() -> GeneratedPipeline:
    return GeneratedPipeline(
        "pipeline.py",
        [GeneratedFile("pipeline.py", PIPELINE_SOURCE)],
        [{"function_name": name} for name in BOUNDARIES],
    )


def build_corpus() -> list[Case]:
    """Every fault, boundary and parameter combination that changes the source."""
    cases: list[Case] = []
    for fault_name, fault in FAULT_CATALOGUE.items():
        for boundary in BOUNDARIES:
            for parameter in PARAMETERS.get(fault_name, [""]):
                try:
                    injected = inject(
                        build_pipeline(), fault, target=boundary, parameter=parameter
                    )
                except ValueError:
                    continue
                label = parameter or "default"
                cases.append(
                    Case(
                        case_id=f"{fault_name}|{boundary}|{label}",
                        fault_name=fault_name,
                        provenance=fault.provenance,
                        boundary=boundary,
                        parameter=parameter,
                        injected=injected,
                    )
                )
    return cases
