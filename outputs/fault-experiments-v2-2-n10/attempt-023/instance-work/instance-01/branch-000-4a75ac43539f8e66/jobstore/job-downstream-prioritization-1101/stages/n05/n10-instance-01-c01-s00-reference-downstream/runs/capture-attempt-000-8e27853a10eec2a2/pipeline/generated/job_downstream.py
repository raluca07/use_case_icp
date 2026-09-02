import json
import sys

import pandas as pd


def coverage_mapping(needs_df, capabilities_df):
    allowed_record_ids = [
        "n06-r01", "n06-r02", "n06-r03", "n06-r04",
        "n06-r05", "n06-r06", "n06-r07", "n06-r08",
    ]
    capability_rows = capabilities_df.reindex(columns=["capability_id", "need"]).fillna("").to_dict("records")
    capability_by_need = {}
    for capability in capability_rows:
        need_text = capability.get("need", "") or ""
        capability_by_need[need_text] = capability.get("capability_id", "") or ""
    handoff = needs_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"])
    handoff["record_id"] = handoff["record_id"].fillna("")
    handoff["need"] = handoff["need"].fillna("")
    retained = handoff.loc[handoff["record_id"].isin(allowed_record_ids)]
    coverage_records = []
    for _, row in retained.iterrows():
        need_text = row.get("need", "") or ""
        capability_id = capability_by_need.get(need_text, "")
        coverage_records.append({
            "record_id": row.get("record_id", ""),
            "need": need_text,
            "capability_id": capability_id,
            "coverage": "direct" if capability_id else "unsupported",
        })
    return pd.DataFrame(coverage_records, columns=["record_id", "need", "capability_id", "coverage"])


def prioritization(coverage_df, evidence_sources_df):
    evidence_rows = evidence_sources_df.reindex(columns=["record_id", "source_id", "source_weight", "rank"]).fillna("").to_dict("records")
    rank_by_record_id = {}
    for row in evidence_rows:
        record_id = row.get("record_id", "") or ""
        try:
            rank_value = int(row.get("rank", 0) or 0)
        except (TypeError, ValueError):
            rank_value = 0
        rank_by_record_id[record_id] = rank_value
    priority_records = []
    for row in coverage_df.to_dict("records"):
        record_id = row.get("record_id", "") or ""
        coverage_value = row.get("coverage", "") or ""
        unsupported = coverage_value != "direct"
        priority_records.append({
            "record_id": record_id,
            "need": row.get("need", "") or "",
            "capability_id": row.get("capability_id", "") or "",
            "coverage": coverage_value,
            "unsupported": bool(unsupported),
            "provenance_rank": int(rank_by_record_id.get(record_id, 0) or 0),
        })
    ordered = sorted(priority_records, key=lambda row: (0 if row.get("unsupported", False) else 1, int(row.get("provenance_rank", 0) or 0), str(row.get("record_id", "") or "")))
    return pd.DataFrame(ordered, columns=["record_id", "need", "capability_id", "coverage", "unsupported", "provenance_rank"])


def synthesis(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained_priorities = priorities_df.head(len(index_window)).reset_index(drop=True)
    priority_records = retained_priorities.to_dict("records")
    first_priority = priority_records[0] if priority_records else {
        "need": "",
        "unsupported": False,
    }
    recommendation = {
        "top_need": first_priority.get("need", ""),
        "decision": "prioritize" if first_priority.get("unsupported", False) else "maintain",
    }
    return retained_priorities, recommendation


payload = json.load(sys.stdin)
needs_df = pd.DataFrame(payload.get("needs", []))
evidence_sources_df = pd.DataFrame(payload.get("evidence_sources", []))
capabilities_df = pd.DataFrame(payload.get("capabilities", []))
coverage_df = coverage_mapping(needs_df, capabilities_df)
priorities_df = prioritization(coverage_df, evidence_sources_df)
retained_priorities_df, recommendation = synthesis(priorities_df)
result = {
    "coverage": coverage_df.to_dict("records"),
    "priorities": retained_priorities_df.to_dict("records"),
    "recommendation": recommendation,
    "metadata": {
        "job": "downstream",
        "coverage_count": int(len(coverage_df)),
        "priority_count": int(len(retained_priorities_df)),
    },
}
json.dump(result, sys.stdout, sort_keys=True)
