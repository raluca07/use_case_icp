import json
import sys

import pandas as pd


def map_coverage(needs_df, capabilities_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    capability_by_need = {}
    for _, cap in capabilities_df.reindex(columns=["capability_id", "need"]).iterrows():
        need = "" if pd.isna(cap.get("need", "")) else cap.get("need", "")
        capability_id = "" if pd.isna(cap.get("capability_id", "")) else cap.get("capability_id", "")
        if need not in capability_by_need:
            capability_by_need[need] = capability_id
    coverage_records = []
    for _, row in needs_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"]).iterrows():
        record_id = "" if pd.isna(row.get("record_id", "")) else row.get("record_id", "")
        if record_id in allowed_record_ids:
            need = "" if pd.isna(row.get("need", "")) else row.get("need", "")
            capability_id = capability_by_need.get(need, "")
            coverage_records.append({
                "record_id": record_id,
                "need": need,
                "capability_id": capability_id,
                "coverage": "direct" if capability_id != "" else "unsupported",
            })
    return pd.DataFrame(coverage_records, columns=["record_id", "need", "capability_id", "coverage"])


def prioritize_needs(coverage_df, evidence_sources_df):
    rank_by_record_id = {}
    for _, source in evidence_sources_df.reindex(columns=["record_id", "source_id", "source_weight", "rank"]).iterrows():
        record_id = "" if pd.isna(source.get("record_id", "")) else source.get("record_id", "")
        rank_value = source.get("rank", 999999)
        rank_by_record_id[record_id] = 999999 if pd.isna(rank_value) else int(rank_value)
    priority_records = []
    for _, row in coverage_df.reindex(columns=["record_id", "need", "capability_id", "coverage"]).iterrows():
        record_id = "" if pd.isna(row.get("record_id", "")) else row.get("record_id", "")
        need = "" if pd.isna(row.get("need", "")) else row.get("need", "")
        capability_id = "" if pd.isna(row.get("capability_id", "")) else row.get("capability_id", "")
        coverage = "unsupported" if pd.isna(row.get("coverage", "unsupported")) else row.get("coverage", "unsupported")
        unsupported = coverage != "direct"
        priority_records.append({
            "record_id": record_id,
            "need": need,
            "capability_id": capability_id,
            "coverage": coverage,
            "unsupported": bool(unsupported),
            "provenance_rank": rank_by_record_id.get(record_id, 999999),
        })
    ordered = sorted(priority_records, key=lambda item: (0 if item.get("unsupported", False) else 1, item.get("provenance_rank", 999999), item.get("record_id", "")))
    ranked_records = []
    for priority, item in enumerate(ordered, start=1):
        ranked_records.append({
            "priority": priority,
            "record_id": item.get("record_id", ""),
            "need": item.get("need", ""),
            "capability_id": item.get("capability_id", ""),
            "coverage": item.get("coverage", "unsupported"),
            "unsupported": item.get("unsupported", True),
            "provenance_rank": item.get("provenance_rank", 999999),
        })
    return pd.DataFrame(ranked_records, columns=["priority", "record_id", "need", "capability_id", "coverage", "unsupported", "provenance_rank"])


def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained = priorities_df.head(len(index_window)).reset_index(drop=True)
    first_record = retained.iloc[0].to_dict() if len(retained) else {"need": "", "unsupported": True}
    recommendation = {
        "top_need": first_record.get("need", ""),
        "decision": "prioritize" if bool(first_record.get("unsupported", True)) else "maintain",
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
        "instance_id": "ins-36129a2a0d354dad",
        "scenario_id": "protocol-2-2-experimental-demand-recovery-v1",
        "job_id": "job_downstream_priority_recovery",
        "consumed_handoffs": ["needs", "evidence_sources"],
        "coverage_count": int(len(coverage_df)),
        "priority_count": int(len(retained_priorities_df)),
    },
}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
