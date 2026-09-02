import json
import sys

import pandas as pd


def map_coverage(needs_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    capability_by_need = {
        "trace exact artifact handoffs between jobs": "cap-handoff",
        "inspect bounded intermediate table values": "cap-inspect",
        "resume from a verified trusted frontier": "cap-frontier",
        "localize a transformation to one function": "cap-localize",
        "compare selected and complete runtime evidence": "cap-compare",
        "preserve immutable review attempts": "cap-ledger",
    }
    rows = needs_df.to_dict(orient="records")
    records = []
    for row in rows:
        record_id = row.get("record_id", "")
        if record_id in allowed_record_ids:
            need = row.get("need", "")
            capability_id = capability_by_need.get(need, "")
            records.append({
                "record_id": record_id,
                "need": need,
                "capability_id": capability_id,
                "coverage": "direct" if capability_id else "none",
            })
    return pd.DataFrame(records)


def prioritize_needs(coverage_df, evidence_sources_df):
    rank_rows = evidence_sources_df.to_dict(orient="records")
    rank_by_record_id = {}
    for row in rank_rows:
        rank_by_record_id[row.get("record_id", "")] = row.get("rank", 0)
    records = []
    for row in coverage_df.to_dict(orient="records"):
        unsupported = row.get("coverage", "") != "direct"
        records.append({
            "record_id": row.get("record_id", ""),
            "need": row.get("need", ""),
            "capability_id": row.get("capability_id", ""),
            "coverage": row.get("coverage", "none"),
            "unsupported": bool(unsupported),
            "evidence_rank": rank_by_record_id.get(row.get("record_id", ""), 0),
        })
    ordered = sorted(records, key=lambda row: (0 if row.get("unsupported", False) else 1, row.get("evidence_rank", 0), row.get("record_id", "")))
    priorities = []
    for priority, row in enumerate(ordered, start=1):
        priorities.append({
            "priority": priority,
            "record_id": row.get("record_id", ""),
            "need": row.get("need", ""),
            "capability_id": row.get("capability_id", ""),
            "coverage": row.get("coverage", "none"),
            "unsupported": row.get("unsupported", False),
            "evidence_rank": row.get("evidence_rank", 0),
        })
    return pd.DataFrame(priorities)


def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained = priorities_df.head(len(index_window)).reset_index(drop=True)
    first_priority = retained.to_dict(orient="records")[0] if len(retained) else {"need": "", "unsupported": False}
    recommendation = {
        "top_need": first_priority.get("need", ""),
        "decision": "prioritize" if first_priority.get("unsupported", False) else "maintain",
    }
    return pd.DataFrame([recommendation])


payload = json.load(sys.stdin)
needs = pd.DataFrame(payload.get("needs", []))
evidence_sources = pd.DataFrame(payload.get("evidence_sources", []))
coverage = map_coverage(needs)
priorities = prioritize_needs(coverage, evidence_sources)
recommendation_frame = synthesize_recommendation(priorities)
result = {
    "coverage": coverage.to_dict(orient="records"),
    "priorities": priorities.to_dict(orient="records"),
    "recommendation": recommendation_frame.to_dict(orient="records")[0],
    "metadata": {
        "job": "downstream-coverage-priority",
        "priority_count": int(len(priorities)),
        "consumed_handoffs": ["needs", "evidence_sources"],
    },
}
json.dump(result, sys.stdout, separators=(",", ":"))
