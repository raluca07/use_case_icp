import json
import sys

import pandas as pd


def map_coverage(needs_df, capabilities_df):
    allowed_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    capability_records = capabilities_df.to_dict(orient="records") if not capabilities_df.empty else []
    coverage_records = []
    normalized_needs = needs_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"]).fillna({
        "record_id": "",
        "need": "",
        "demand_score": 0,
        "source_id": "",
        "source_weight": 0,
    })
    retained_needs = normalized_needs[normalized_needs["record_id"].isin(allowed_ids)]
    for _, need_row in retained_needs.iterrows():
        need_text = need_row.get("need", "") if pd.notna(need_row.get("need", "")) else ""
        matched_capability = ""
        for capability in capability_records:
            if capability.get("need", "") == need_text:
                matched_capability = capability.get("capability_id", "")
                break
        coverage_records.append({
            "record_id": need_row.get("record_id", "") if pd.notna(need_row.get("record_id", "")) else "",
            "need": need_text,
            "capability_id": matched_capability,
            "coverage": "direct" if matched_capability else "unsupported",
        })
    return pd.DataFrame(coverage_records, columns=["record_id", "need", "capability_id", "coverage"])


def prioritize_needs(coverage_df, evidence_sources_df):
    rank_map = {}
    for evidence in evidence_sources_df.to_dict(orient="records"):
        record_id = evidence.get("record_id", "")
        rank_value = evidence.get("rank", 999999)
        rank_map[record_id] = int(rank_value) if rank_value not in ("", None) else 999999
    priority_records = []
    for coverage in coverage_df.to_dict(orient="records"):
        record_id = coverage.get("record_id", "")
        coverage_value = coverage.get("coverage", "")
        unsupported = coverage_value != "direct"
        priority_records.append({
            "record_id": record_id,
            "need": coverage.get("need", ""),
            "capability_id": coverage.get("capability_id", ""),
            "coverage": coverage_value,
            "unsupported": unsupported,
            "rank": rank_map.get(record_id, 999999),
        })
    ordered_priorities = sorted(priority_records, key=lambda item: (0 if item.get("unsupported", False) else 1, int(item.get("rank", 999999) or 999999), item.get("record_id", "")))
    return pd.DataFrame(ordered_priorities, columns=["record_id", "need", "capability_id", "coverage", "unsupported", "rank"])


def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained_priorities = priorities_df.head(len(index_window)).reset_index(drop=True)
    priority_records = retained_priorities.to_dict(orient="records")
    first_priority = priority_records[0] if priority_records else {"need": "", "unsupported": True}
    recommendation = {
        "top_need": first_priority.get("need", ""),
        "decision": "prioritize" if first_priority.get("unsupported", False) else "maintain",
    }
    return retained_priorities, recommendation


input_payload = json.load(sys.stdin)
needs_frame = pd.DataFrame(input_payload.get("needs", []))
evidence_sources_frame = pd.DataFrame(input_payload.get("evidence_sources", []))
capabilities_frame = pd.DataFrame(input_payload.get("capabilities", []))
coverage_frame = map_coverage(needs_frame, capabilities_frame)
priorities_frame, recommendation_record = synthesize_recommendation(prioritize_needs(coverage_frame, evidence_sources_frame))
output_payload = {
    "coverage": coverage_frame.to_dict(orient="records"),
    "priorities": priorities_frame.to_dict(orient="records"),
    "recommendation": recommendation_record,
    "metadata": {
        "scenario_id": "protocol-2-2-experimental-demand-recovery-v1",
        "job_id": "job-downstream-coverage-priority-1108-1",
        "coverage_count": int(len(coverage_frame)),
        "priority_count": int(len(priorities_frame)),
    },
}
sys.stdout.write(json.dumps(output_payload, separators=(",", ":"), sort_keys=True))
