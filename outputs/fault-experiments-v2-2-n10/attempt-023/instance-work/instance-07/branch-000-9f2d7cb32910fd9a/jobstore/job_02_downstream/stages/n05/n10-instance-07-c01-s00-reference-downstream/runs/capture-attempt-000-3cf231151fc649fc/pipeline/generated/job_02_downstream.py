import json
import sys

import pandas as pd


def map_capability_coverage(needs_df, capabilities_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    capability_by_need = {}
    for _, capability in capabilities_df.iterrows():
        capability_need = capability.get("need", "")
        if capability_need not in capability_by_need:
            capability_by_need[capability_need] = capability.get("capability_id", "")
    coverage_records = []
    for _, row in needs_df.iterrows():
        record_id = row.get("record_id", "")
        if record_id in allowed_record_ids:
            need = row.get("need", "")
            capability_id = capability_by_need.get(need, "")
            coverage_records.append({
                "record_id": record_id,
                "need": need,
                "capability_id": capability_id,
                "coverage": "direct" if capability_id != "" else "unsupported",
            })
    return pd.DataFrame(coverage_records)


def prioritize_needs(coverage_df, evidence_sources_df):
    rank_by_record_id = {}
    for _, source in evidence_sources_df.iterrows():
        record_id = source.get("record_id", "")
        rank_by_record_id[record_id] = source.get("rank", 0)
    priority_records = []
    for _, row in coverage_df.iterrows():
        record_id = row.get("record_id", "")
        coverage = row.get("coverage", "")
        unsupported = coverage != "direct"
        priority_records.append({
            "record_id": record_id,
            "need": row.get("need", ""),
            "capability_id": row.get("capability_id", ""),
            "coverage": coverage,
            "unsupported": unsupported,
            "rank": rank_by_record_id.get(record_id, 0),
        })
    ordered_records = sorted(priority_records, key=lambda record: (0 if record.get("unsupported", False) else 1, record.get("rank", 0), record.get("record_id", "")))
    priorities = []
    for priority, record in enumerate(ordered_records, start=1):
        priorities.append({
            "priority": priority,
            "record_id": record.get("record_id", ""),
            "need": record.get("need", ""),
            "capability_id": record.get("capability_id", ""),
            "coverage": record.get("coverage", ""),
            "unsupported": record.get("unsupported", False),
            "rank": record.get("rank", 0),
        })
    return pd.DataFrame(priorities)


def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained_df = priorities_df.head(len(index_window)).reset_index(drop=True)
    if len(retained_df) == 0:
        recommendation = {"top_need": "", "decision": "maintain"}
    else:
        top_record = retained_df.iloc[0].to_dict()
        recommendation = {
            "top_need": top_record.get("need", ""),
            "decision": "prioritize" if top_record.get("unsupported", False) else "maintain",
        }
    return retained_df, recommendation


payload = json.load(sys.stdin)
needs = payload.get("needs", [])
evidence_sources = payload.get("evidence_sources", [])
capabilities = payload.get("capabilities", [])
needs_df = pd.DataFrame(needs)
evidence_sources_df = pd.DataFrame(evidence_sources)
capabilities_df = pd.DataFrame(capabilities)
coverage_df = map_capability_coverage(needs_df, capabilities_df)
priorities_df = prioritize_needs(coverage_df, evidence_sources_df)
retained_priorities_df, recommendation = synthesize_recommendation(priorities_df)
result = {
    "coverage": coverage_df.to_dict(orient="records"),
    "priorities": retained_priorities_df.to_dict(orient="records"),
    "recommendation": recommendation,
    "metadata": {
        "job_id": "job_02_downstream",
        "coverage_count": int(len(coverage_df)),
        "priorities_count": int(len(retained_priorities_df)),
    },
}
json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
