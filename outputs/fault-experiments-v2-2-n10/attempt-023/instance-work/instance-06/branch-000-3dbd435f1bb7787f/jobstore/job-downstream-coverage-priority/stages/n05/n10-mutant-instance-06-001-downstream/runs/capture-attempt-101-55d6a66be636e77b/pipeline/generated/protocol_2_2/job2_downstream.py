import json
import sys

import pandas as pd


def map_coverage(needs_df, capabilities_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    needs_records = needs_df.to_dict(orient="records")
    capability_records = capabilities_df.to_dict(orient="records")
    capability_by_need = {}
    for capability in capability_records:
        capability_need = capability.get("need", "")
        if capability_need not in capability_by_need:
            capability_by_need[capability_need] = capability.get("capability_id", "")
    coverage_records = []
    for record in needs_records:
        record_id = record.get("record_id", "")
        if record_id in allowed_record_ids:
            need = record.get("need", "")
            capability_id = capability_by_need.get(need, "")
            coverage_records.append({
                "record_id": record_id,
                "need": need,
                "capability_id": capability_id,
                "coverage": "direct" if capability_id else "unsupported",
            })
    return pd.DataFrame(coverage_records, columns=["record_id", "need", "capability_id", "coverage"])


def prioritize(coverage_df, evidence_sources_df):
    rank_map = {}
    for record in evidence_sources_df.to_dict(orient="records"):
        rank_map[record.get("record_id", "")] = record.get("rank", 0)
    priority_records = []
    for record in coverage_df.to_dict(orient="records"):
        record_id = record.get("record_id", "")
        coverage = record.get("coverage", "")
        unsupported = coverage != "direct"
        priority_records.append({
            "record_id": record_id,
            "need": record.get("need", ""),
            "capability_id": record.get("capability_id", ""),
            "coverage": coverage,
            "unsupported": unsupported,
            "upstream_rank": rank_map.get(record_id, 0),
        })
    ordered = sorted(priority_records, key=lambda record: (0 if record.get("unsupported", False) else 1, record.get("upstream_rank", 0), record.get("record_id", "")))
    for priority_index, record in enumerate(ordered, start=1):
        record["priority_rank"] = priority_index
    return pd.DataFrame(ordered, columns=["priority_rank", "record_id", "need", "capability_id", "coverage", "unsupported", "upstream_rank"])


def synthesize(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained = priorities_df.head(len(index_window)).reset_index(drop=True)
    priority_records = retained.to_dict(orient="records")
    top_record = priority_records[0] if priority_records else {"need": "", "unsupported": False}
    recommendation = {
        "top_need": top_record.get("need", ""),
        "decision": "prioritize" if top_record.get("unsupported", False) else "maintain",
    }
    return retained, recommendation


_input = json.load(sys.stdin)
_needs_df = pd.DataFrame(_input.get("needs", []))
_evidence_sources_df = pd.DataFrame(_input.get("evidence_sources", []))
_capabilities_df = pd.DataFrame(_input.get("capabilities", []))
_coverage_df = map_coverage(_needs_df, _capabilities_df)
_priorities_df = prioritize(_coverage_df, _evidence_sources_df)
_retained_priorities_df, _recommendation = synthesize(_priorities_df)
_result = {
    "coverage": _coverage_df.to_dict(orient="records"),
    "priorities": _retained_priorities_df.to_dict(orient="records"),
    "recommendation": _recommendation,
    "metadata": {
        "job": "downstream",
        "needs_handoff_count": int(len(_needs_df)),
        "evidence_sources_handoff_count": int(len(_evidence_sources_df)),
        "priority_count": int(len(_retained_priorities_df)),
    },
}
json.dump(_result, sys.stdout, separators=(",", ":"))
