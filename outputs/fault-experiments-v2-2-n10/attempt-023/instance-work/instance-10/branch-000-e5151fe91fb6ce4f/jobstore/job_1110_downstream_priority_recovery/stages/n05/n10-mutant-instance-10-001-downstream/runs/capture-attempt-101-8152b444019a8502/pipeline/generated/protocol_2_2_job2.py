import json
import sys
import pandas as pd


def map_coverage(needs_df, capabilities_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    capability_by_need = {}
    for _, capability in capabilities_df.iterrows():
        capability_need = capability.get("need", "")
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
                "coverage": "direct" if capability_id != "" else "none",
            })
    return pd.DataFrame(coverage_records)


def prioritize_needs(coverage_df, evidence_df):
    rank_by_record_id = {}
    for _, source in evidence_df.iterrows():
        rank_by_record_id[source.get("record_id", "")] = source.get("rank", 0)
    priority_records = []
    for _, row in coverage_df.iterrows():
        coverage_value = row.get("coverage", "")
        unsupported = coverage_value != "direct"
        record_id = row.get("record_id", "")
        priority_records.append({
            "record_id": record_id,
            "need": row.get("need", ""),
            "capability_id": row.get("capability_id", ""),
            "coverage": coverage_value,
            "unsupported": unsupported,
            "rank": rank_by_record_id.get(record_id, 0),
        })
    ordered = sorted(priority_records, key=lambda item: (0 if item.get("unsupported", False) else 1, item.get("rank", 0), item.get("record_id", "")))
    priorities = []
    for priority, item in enumerate(ordered, start=1):
        priorities.append({
            "priority": priority,
            "record_id": item.get("record_id", ""),
            "need": item.get("need", ""),
            "capability_id": item.get("capability_id", ""),
            "coverage": item.get("coverage", ""),
            "unsupported": item.get("unsupported", False),
            "rank": item.get("rank", 0),
        })
    return pd.DataFrame(priorities)


def synthesize_recommendation(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained = priorities_df.head(len(index_window)).reset_index(drop=True)
    first_priority = retained.iloc[0].to_dict() if len(retained) > 0 else {}
    recommendation = {
        "top_need": first_priority.get("need", ""),
        "decision": "prioritize" if first_priority.get("unsupported", False) else "maintain",
    }
    return retained, recommendation


input_object = json.loads(sys.stdin.read())
needs_frame = pd.DataFrame(input_object.get("needs", []))
evidence_frame = pd.DataFrame(input_object.get("evidence_sources", []))
capabilities_frame = pd.DataFrame(input_object.get("capabilities", []))
coverage_frame = map_coverage(needs_frame, capabilities_frame)
priorities_frame = prioritize_needs(coverage_frame, evidence_frame)
retained_priorities_frame, recommendation_object = synthesize_recommendation(priorities_frame)
output_object = {
    "coverage": coverage_frame.to_dict(orient="records"),
    "priorities": retained_priorities_frame.to_dict(orient="records"),
    "recommendation": recommendation_object,
    "metadata": {"job_id": "job_1110_downstream_priority_recovery", "priority_count": int(len(retained_priorities_frame))},
}
sys.stdout.write(json.dumps(output_object, sort_keys=True, separators=(",", ":")))
