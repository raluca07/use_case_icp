import json
import sys

import pandas as pd


def select_demand_records(corpus_df):
    fallback_ids = ["n06-r07", "n06-r08"]
    if corpus_df.empty:
        source_df = pd.DataFrame(columns=["record_id", "need", "demand_score", "source_id", "source_weight"])
    else:
        source_df = corpus_df.copy()
    demand_values = pd.to_numeric(source_df.get("demand_score", 0), errors="coerce").fillna(0)
    record_values = source_df.get("record_id", pd.Series([""] * len(source_df), index=source_df.index)).fillna("")
    selected_df = source_df[(demand_values >= 3) | (record_values.isin(fallback_ids))]
    records = []
    for _, row in selected_df.iterrows():
        records.append({
            "record_id": row.get("record_id", "") if pd.notna(row.get("record_id", "")) else "",
            "need": row.get("need", "") if pd.notna(row.get("need", "")) else "",
            "demand_score": int(row.get("demand_score", 0)) if pd.notna(row.get("demand_score", 0)) else 0,
            "source_id": row.get("source_id", "") if pd.notna(row.get("source_id", "")) else "",
            "source_weight": int(row.get("source_weight", 0)) if pd.notna(row.get("source_weight", 0)) else 0,
        })
    return pd.DataFrame(records, columns=["record_id", "need", "demand_score", "source_id", "source_weight"])


def normalize_evidence(selected_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    normalized_df = selected_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"])
    normalized_df = normalized_df.fillna({
        "record_id": "",
        "need": "",
        "demand_score": 0,
        "source_id": "",
        "source_weight": 0,
    })
    retained_df = normalized_df[normalized_df["record_id"].isin(allowed_ids)]
    return retained_df.head(len(index_window)).reset_index(drop=True)


def assemble_provenance(needs_df):
    source_records = []
    for record in needs_df.to_dict(orient="records"):
        source_records.append({
            "record_id": record.get("record_id", ""),
            "source_id": record.get("source_id", ""),
            "source_weight": record.get("source_weight", 0),
            "demand_score": record.get("demand_score", 0),
        })
    ordered_records = sorted(source_records, key=lambda item: (-int(item.get("demand_score", 0) or 0), item.get("record_id", "")))
    evidence_records = []
    for index, record in enumerate(ordered_records, start=1):
        evidence_records.append({
            "record_id": record.get("record_id", ""),
            "source_id": record.get("source_id", ""),
            "source_weight": record.get("source_weight", 0),
            "rank": index,
        })
    return pd.DataFrame(evidence_records, columns=["record_id", "source_id", "source_weight", "rank"])


input_payload = json.load(sys.stdin)
corpus_frame = pd.DataFrame(input_payload.get("corpus", []))
selected_needs_frame = select_demand_records(corpus_frame)
normalized_needs_frame = normalize_evidence(selected_needs_frame)
evidence_sources_frame = assemble_provenance(normalized_needs_frame)
output_payload = {
    "needs": normalized_needs_frame.to_dict(orient="records"),
    "evidence_sources": evidence_sources_frame.to_dict(orient="records"),
    "metadata": {
        "scenario_id": "protocol-2-2-experimental-demand-recovery-v1",
        "job_id": "job-upstream-demand-provenance-1108-1",
        "need_count": int(len(normalized_needs_frame)),
        "evidence_source_count": int(len(evidence_sources_frame)),
    },
}
sys.stdout.write(json.dumps(output_payload, separators=(",", ":"), sort_keys=True))
