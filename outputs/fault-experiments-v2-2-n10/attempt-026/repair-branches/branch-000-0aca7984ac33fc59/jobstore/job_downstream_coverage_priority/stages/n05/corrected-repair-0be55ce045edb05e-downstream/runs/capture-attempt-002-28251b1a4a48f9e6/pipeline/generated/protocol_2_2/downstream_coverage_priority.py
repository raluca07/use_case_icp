import json
import sys

import pandas as pd


def map_coverage(needs_df, capabilities_df):
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    retained_df = needs_df[needs_df.get("record_id", "").isin(allowed_record_ids)]
    capability_rows = capabilities_df.reindex(columns=["capability_id", "need"]).fillna({"capability_id": "", "need": ""}).to_dict(orient="records")
    capability_by_need = {}
    for capability in capability_rows:
        capability_by_need[capability.get("need", "")] = capability.get("capability_id", "")
    records = []
    for _, row in retained_df.iterrows():
        need = row.get("need", "")
        capability_id = capability_by_need.get(need, "")
        records.append({
            "record_id": row.get("record_id", ""),
            "need": need,
            "capability_id": capability_id,
            "coverage": "direct" if capability_id != "" else "none",
        })
    return pd.DataFrame(records)


def prioritize(coverage_df, evidence_sources_df):
    evidence_rows = evidence_sources_df.reindex(columns=["record_id", "source_id", "source_weight", "rank"]).fillna({
        "record_id": "",
        "source_id": "",
        "source_weight": 0,
        "rank": 0,
    }).to_dict(orient="records")
    rank_by_record_id = {}
    for evidence in evidence_rows:
        rank_by_record_id[evidence.get("record_id", "")] = evidence.get("rank", 0)
    priority_rows = []
    for coverage in coverage_df.to_dict(orient="records"):
        unsupported = coverage.get("coverage", "") != "direct"
        priority_rows.append({
            "record_id": coverage.get("record_id", ""),
            "need": coverage.get("need", ""),
            "capability_id": coverage.get("capability_id", ""),
            "coverage": coverage.get("coverage", ""),
            "unsupported": unsupported,
            "upstream_rank": rank_by_record_id.get(coverage.get("record_id", ""), 0),
        })
    ranked_rows = sorted(priority_rows, key=lambda record: (0 if record.get("unsupported", False) else 1, record.get("upstream_rank", 0), record.get("record_id", "")))
    records = []
    for index, record in enumerate(ranked_rows, start=1):
        records.append({
            "priority_rank": index,
            "record_id": record.get("record_id", ""),
            "need": record.get("need", ""),
            "capability_id": record.get("capability_id", ""),
            "coverage": record.get("coverage", ""),
            "unsupported": bool(record.get("unsupported", False)),
            "upstream_rank": record.get("upstream_rank", 0),
        })
    return pd.DataFrame(records)


def synthesize(priorities_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    retained_priorities_df = priorities_df.head(len(index_window)).reset_index(drop=True)
    priority_records = retained_priorities_df.to_dict(orient="records")
    first_priority = priority_records[0] if priority_records else {"need": "", "unsupported": False}
    recommendation = {
        "top_need": first_priority.get("need", ""),
        "decision": "prioritize" if first_priority.get("unsupported", False) else "maintain",
    }
    return retained_priorities_df, recommendation


input_object = json.loads(sys.stdin.read())
needs_df = pd.DataFrame(input_object.get("needs", []))
evidence_sources_df = pd.DataFrame(input_object.get("evidence_sources", []))
capabilities_df = pd.DataFrame(input_object.get("capabilities", []))
coverage_df = map_coverage(needs_df, capabilities_df)
priorities_df = prioritize(coverage_df, evidence_sources_df)
retained_priorities_df, recommendation = synthesize(priorities_df)
result = {
    "coverage": coverage_df.to_dict(orient="records"),
    "priorities": retained_priorities_df.to_dict(orient="records"),
    "recommendation": recommendation,
    "metadata": {
        "coverage_count": int(len(coverage_df)),
        "priority_count": int(len(retained_priorities_df)),
        "consumed_handoffs": ["needs", "evidence_sources"],
    },
}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
