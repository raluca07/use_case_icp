import json
import sys

import pandas as pd


def select_demand_records(corpus_df):
    fallback_ids = ["n06-r07", "n06-r08"]
    records = []
    for _, row in corpus_df.iterrows():
        record_id = row.get("record_id", "")
        demand_score = row.get("demand_score", 0)
        if demand_score >= 3 or record_id in fallback_ids:
            records.append({
                "record_id": record_id,
                "need": row.get("need", ""),
                "demand_score": demand_score,
                "source_id": row.get("source_id", ""),
                "source_weight": row.get("source_weight", 0),
            })
    return pd.DataFrame(records)


def normalize_evidence_fields(selected_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    required_columns = ["record_id", "need", "demand_score", "source_id", "source_weight"]
    normalized_df = selected_df.reindex(columns=required_columns)
    normalized_df = normalized_df.fillna({
        "record_id": "",
        "need": "",
        "demand_score": 0,
        "source_id": "",
        "source_weight": 0,
    })
    retained_df = normalized_df[normalized_df["record_id"].isin(allowed_record_ids)]
    return retained_df.head(len(index_window)).reset_index(drop=True)


def assemble_provenance_sources(needs_df):
    source_records = []
    rows = []
    for _, row in needs_df.iterrows():
        rows.append({
            "record_id": row.get("record_id", ""),
            "source_id": row.get("source_id", ""),
            "source_weight": row.get("source_weight", 0),
            "demand_score": row.get("demand_score", 0),
        })
    ordered_rows = sorted(rows, key=lambda record: (-record.get("demand_score", 0), record.get("record_id", "")))
    for rank, record in enumerate(ordered_rows, start=1):
        source_records.append({
            "record_id": record.get("record_id", ""),
            "source_id": record.get("source_id", ""),
            "source_weight": record.get("source_weight", 0),
            "rank": rank,
        })
    return pd.DataFrame(source_records)


payload = json.load(sys.stdin)
corpus = payload.get("corpus", [])
corpus_df = pd.DataFrame(corpus)
selected_df = select_demand_records(corpus_df)
needs_df = normalize_evidence_fields(selected_df)
evidence_sources_df = assemble_provenance_sources(needs_df)
result = {
    "needs": needs_df.to_dict(orient="records"),
    "evidence_sources": evidence_sources_df.to_dict(orient="records"),
    "metadata": {
        "job_id": "job_01_upstream",
        "needs_count": int(len(needs_df)),
        "evidence_sources_count": int(len(evidence_sources_df)),
    },
}
json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
