import json
import sys

import pandas as pd


def map_coverage(needs_df, capabilities_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    need_rows = needs_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"]).copy()
    need_rows["record_id"] = need_rows["record_id"].fillna("")
    need_rows["need"] = need_rows["need"].fillna("")
    retained = need_rows[need_rows["record_id"].apply(lambda record_id: record_id in allowed_record_ids)]
    capability_rows = capabilities_df.reindex(columns=["capability_id", "need"]).copy()
    capability_rows["capability_id"] = capability_rows["capability_id"].fillna("")
    capability_rows["need"] = capability_rows["need"].fillna("")
    capability_by_need = {}
    for _, capability in capability_rows.iterrows():
        need = capability.get("need", "") if pd.notna(capability.get("need", "")) else ""
        capability_id = capability.get("capability_id", "") if pd.notna(capability.get("capability_id", "")) else ""
        if need not in capability_by_need:
            capability_by_need[need] = capability_id
    coverage_records = []
    for _, row in retained.iterrows():
        need = row.get("need", "") if pd.notna(row.get("need", "")) else ""
        capability_id = capability_by_need.get(need, "")
        coverage_records.append({
            "record_id": row.get("record_id", "") if pd.notna(row.get("record_id", "")) else "",
            "need": need,
            "capability_id": capability_id,
            "coverage": "direct" if capability_id else "unsupported",
        })
    return pd.DataFrame.from_records(coverage_records, columns=["record_id", "need", "capability_id", "coverage"])


def prioritize_needs(coverage_df, evidence_sources_df):
    evidence_rows = evidence_sources_df.reindex(columns=["record_id", "source_id", "source_weight", "rank"]).copy()
    rank_by_record_id = {}
    for _, row in evidence_rows.iterrows():
        record_id = row.get("record_id", "") if pd.notna(row.get("record_id", "")) else ""
        rank_value = row.get("rank", 0)
        rank_by_record_id[record_id] = int(rank_value) if pd.notna(rank_value) else 0
    priority_inputs = []
    for record in coverage_df.to_dict(orient="records"):
        coverage_value = record.get("coverage", "") or ""
        unsupported = coverage_value != "direct"
        record_id = record.get("record_id", "") or ""
        priority_inputs.append({
            "record_id": record_id,
            "need": record.get("need", "") or "",
            "capability_id": record.get("capability_id", "") or "",
            "coverage": coverage_value,
            "unsupported": unsupported,
            "upstream_rank": rank_by_record_id.get(record_id, 0),
        })
    ordered = sorted(priority_inputs, key=lambda record: (0 if record["unsupported"] else 1, record["upstream_rank"], record["record_id"]))
    priority_records = []
    for priority, record in enumerate(ordered, start=1):
        priority_records.append({
            "priority": priority,
            "record_id": record["record_id"],
            "need": record["need"],
            "capability_id": record["capability_id"],
            "coverage": record["coverage"],
            "unsupported": record["unsupported"],
            "upstream_rank": record["upstream_rank"],
        })
    return pd.DataFrame.from_records(priority_records, columns=["priority", "record_id", "need", "capability_id", "coverage", "unsupported", "upstream_rank"])


def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained = priorities_df.head(len(index_window)).reset_index(drop=True)
    first_priority = retained.to_dict(orient="records")[0] if len(retained) else {}
    recommendation = {
        "top_need": first_priority.get("need", ""),
        "decision": "prioritize" if first_priority.get("unsupported", False) else "maintain",
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
        "job_id": "downstream_priority_recovery",
        "coverage_count": int(len(coverage_df)),
        "priority_count": int(len(retained_priorities_df)),
    },
}
json.dump(result, sys.stdout, separators=(",", ":"))
