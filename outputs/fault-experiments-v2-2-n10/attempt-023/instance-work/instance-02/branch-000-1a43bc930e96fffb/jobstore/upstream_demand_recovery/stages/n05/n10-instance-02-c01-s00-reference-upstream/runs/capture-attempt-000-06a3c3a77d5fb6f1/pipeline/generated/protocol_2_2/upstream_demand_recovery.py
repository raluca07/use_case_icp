import json
import sys

import pandas as pd


def select_demand(corpus_df):
    fallback_ids = ["n06-r07", "n06-r08"]
    working = corpus_df.copy()
    if "demand_score" not in working.columns:
        working["demand_score"] = 0
    if "record_id" not in working.columns:
        working["record_id"] = ""
    selected = working[(working["demand_score"].fillna(0) >= 3) | (working["record_id"].isin(fallback_ids))]
    records = []
    for _, row in selected.iterrows():
        records.append({
            "record_id": row.get("record_id", "") if pd.notna(row.get("record_id", "")) else "",
            "need": row.get("need", "") if pd.notna(row.get("need", "")) else "",
            "demand_score": int(row.get("demand_score", 0)) if pd.notna(row.get("demand_score", 0)) else 0,
            "source_id": row.get("source_id", "") if pd.notna(row.get("source_id", "")) else "",
            "source_weight": int(row.get("source_weight", 0)) if pd.notna(row.get("source_weight", 0)) else 0,
        })
    return pd.DataFrame.from_records(records, columns=["record_id", "need", "demand_score", "source_id", "source_weight"])


def normalize_evidence(selected_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    required_columns = ["record_id", "need", "demand_score", "source_id", "source_weight"]
    working = selected_df.reindex(columns=required_columns)
    working["record_id"] = working["record_id"].fillna("")
    working["need"] = working["need"].fillna("")
    working["demand_score"] = working["demand_score"].fillna(0).astype(int)
    working["source_id"] = working["source_id"].fillna("")
    working["source_weight"] = working["source_weight"].fillna(0).astype(int)
    retained = working[working["record_id"].apply(lambda record_id: record_id in allowed_record_ids)]
    return retained.head(len(index_window)).reset_index(drop=True)


def assemble_provenance(needs_df):
    source_records = []
    input_records = needs_df.to_dict(orient="records")
    ordered_records = sorted(input_records, key=lambda record: (-(record.get("demand_score", 0) or 0), record.get("record_id", "") or ""))
    for rank, record in enumerate(ordered_records, start=1):
        source_records.append({
            "record_id": record.get("record_id", "") or "",
            "source_id": record.get("source_id", "") or "",
            "source_weight": int(record.get("source_weight", 0) or 0),
            "rank": rank,
        })
    return pd.DataFrame.from_records(source_records, columns=["record_id", "source_id", "source_weight", "rank"])


payload = json.load(sys.stdin)
corpus_df = pd.DataFrame(payload.get("corpus", []))
selected_df = select_demand(corpus_df)
needs_df = normalize_evidence(selected_df)
evidence_sources_df = assemble_provenance(needs_df)
result = {
    "needs": needs_df.to_dict(orient="records"),
    "evidence_sources": evidence_sources_df.to_dict(orient="records"),
    "metadata": {
        "job_id": "upstream_demand_recovery",
        "need_count": int(len(needs_df)),
        "evidence_source_count": int(len(evidence_sources_df)),
    },
}
json.dump(result, sys.stdout, separators=(",", ":"))
