"""N26 Job 2, preserving the N25 business rules for richer record IDs."""

import json
import sys

import pandas as pd


def map_coverage(needs_df, capabilities_df):
    capability_by_need = {
        row["need"]: row["capability_id"]
        for row in capabilities_df.to_dict(orient="records")
    }
    records = []
    for _, row in needs_df.iterrows():
        need = row["need"]
        capability_id = capability_by_need.get(need, "")
        records.append({
            "record_id": row["record_id"],
            "need": need,
            "capability_id": capability_id,
            "coverage": "direct" if capability_id else "none",
        })
    return pd.DataFrame(records)


def prioritize(coverage_df, evidence_sources_df):
    rank_by_record = {
        row["record_id"]: row["rank"]
        for row in evidence_sources_df.to_dict(orient="records")
    }
    candidates = []
    for row in coverage_df.to_dict(orient="records"):
        candidates.append({
            **row,
            "unsupported": row["coverage"] != "direct",
            "upstream_rank": rank_by_record.get(row["record_id"], 0),
        })
    ordered = sorted(
        candidates,
        key=lambda row: (
            0 if row["unsupported"] else 1,
            row["upstream_rank"],
            row["record_id"],
        ),
    )
    return pd.DataFrame([
        {"priority_rank": rank, **row}
        for rank, row in enumerate(ordered, start=1)
    ])


def synthesize(priorities_df):
    rows = priorities_df.to_dict(orient="records")
    first = rows[0] if rows else {"need": "", "unsupported": False}
    return priorities_df, {
        "top_need": first["need"],
        "decision": "prioritize" if first["unsupported"] else "maintain",
    }


def main():
    input_object = json.load(sys.stdin)
    needs_df = pd.DataFrame(input_object["needs"])
    evidence_sources_df = pd.DataFrame(input_object["evidence_sources"])
    capabilities_df = pd.DataFrame(input_object["capabilities"])
    coverage_df = map_coverage(needs_df, capabilities_df)
    priorities_df = prioritize(coverage_df, evidence_sources_df)
    retained_df, recommendation = synthesize(priorities_df)
    result = {
        "coverage": coverage_df.to_dict(orient="records"),
        "priorities": retained_df.to_dict(orient="records"),
        "recommendation": recommendation,
        "metadata": {
            "coverage_count": int(len(coverage_df)),
            "priority_count": int(len(retained_df)),
            "consumed_handoffs": ["needs", "evidence_sources"],
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
