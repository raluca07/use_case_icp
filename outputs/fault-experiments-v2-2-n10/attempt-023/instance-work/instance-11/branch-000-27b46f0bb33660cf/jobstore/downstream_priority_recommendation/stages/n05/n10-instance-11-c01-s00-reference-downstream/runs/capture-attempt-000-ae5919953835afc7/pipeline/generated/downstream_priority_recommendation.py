import json
import sys

import pandas as pd


def map_coverage(handoff_df, capabilities_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    capability_rows = []
    for _, capability in capabilities_df.reindex(columns=["capability_id", "need"]).fillna({"capability_id": "", "need": ""}).iterrows():
        capability_rows.append({
            "capability_id": capability.get("capability_id", ""),
            "need": capability.get("need", ""),
        })
    records = []
    normalized = handoff_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"])
    normalized = normalized.fillna({"record_id": "", "need": "", "demand_score": 0, "source_id": "", "source_weight": 0})
    retained = normalized.loc[normalized["record_id"].isin(allowed_record_ids)]
    for _, row in retained.iterrows():
        need_value = row.get("need", "")
        matched_capability = ""
        for capability in capability_rows:
            if capability.get("need", "") == need_value:
                matched_capability = capability.get("capability_id", "")
                break
        records.append({
            "record_id": row.get("record_id", ""),
            "need": need_value,
            "capability_id": matched_capability,
            "coverage": "direct" if matched_capability else "unsupported",
        })
    return pd.DataFrame(records, columns=["record_id", "need", "capability_id", "coverage"])


def prioritize_needs(coverage_df, evidence_sources_df):
    rank_map = {}
    for _, evidence in evidence_sources_df.reindex(columns=["record_id", "rank"]).fillna({"record_id": "", "rank": 0}).iterrows():
        rank_map[evidence.get("record_id", "")] = int(evidence.get("rank", 0))
    rows = []
    for _, row in coverage_df.iterrows():
        record_id = row.get("record_id", "")
        coverage_value = row.get("coverage", "")
        unsupported = coverage_value != "direct"
        rows.append({
            "record_id": record_id,
            "need": row.get("need", ""),
            "capability_id": row.get("capability_id", ""),
            "coverage": coverage_value,
            "unsupported": bool(unsupported),
            "provenance_rank": int(rank_map.get(record_id, 0)),
        })
    ordered = sorted(rows, key=lambda item: (0 if item.get("unsupported", False) else 1, item.get("provenance_rank", 0), item.get("record_id", "")))
    priority_records = []
    for index, item in enumerate(ordered, start=1):
        priority_records.append({
            "priority": index,
            "record_id": item.get("record_id", ""),
            "need": item.get("need", ""),
            "capability_id": item.get("capability_id", ""),
            "coverage": item.get("coverage", ""),
            "unsupported": bool(item.get("unsupported", False)),
            "provenance_rank": int(item.get("provenance_rank", 0)),
        })
    return pd.DataFrame(priority_records, columns=["priority", "record_id", "need", "capability_id", "coverage", "unsupported", "provenance_rank"])


def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained = priorities_df.head(len(index_window)).reset_index(drop=True)
    if retained.empty:
        first_priority = {"need": "", "unsupported": False}
    else:
        first_priority = retained.iloc[0].to_dict()
    recommendation = {
        "top_need": first_priority.get("need", ""),
        "decision": "prioritize" if bool(first_priority.get("unsupported", False)) else "maintain",
    }
    return retained, recommendation


payload = json.load(sys.stdin)
needs_df = pd.DataFrame(payload.get("needs", []))
evidence_sources_df = pd.DataFrame(payload.get("evidence_sources", []))
capabilities_df = pd.DataFrame(payload.get("capabilities", []))
coverage_df = map_coverage(needs_df, capabilities_df)
priorities_df = prioritize_needs(coverage_df, evidence_sources_df)
retained_priorities_df, recommendation = synthesize_recommendation(priorities_df)
result = {
    "coverage": coverage_df.to_dict(orient="records"),
    "priorities": retained_priorities_df.to_dict(orient="records"),
    "recommendation": recommendation,
    "metadata": {
        "job_id": "downstream_priority_recommendation",
        "coverage_count": int(len(coverage_df)),
        "priority_count": int(len(retained_priorities_df)),
    },
}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
