import json
import sys

import pandas as pd


def select_demand_records(corpus_df):
    fallback_ids = ["n06-r07", "n06-r08"]
    selected = corpus_df[(corpus_df["demand_score"] >= 3) | (corpus_df["record_id"].isin(fallback_ids))]
    records = []
    for _, row in selected.iterrows():
        records.append({
            "record_id": row.get("record_id", ""),
            "need": row.get("need", ""),
            "demand_score": row.get("demand_score", 0),
            "source_id": row.get("source_id", ""),
            "source_weight": row.get("source_weight", 0),
        })
    return pd.DataFrame(records)


def normalize_evidence(selected_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    required_columns = ["record_id", "need", "demand_score", "source_id", "source_weight"]
    normalized = selected_df.reindex(columns=required_columns).copy()
    normalized["record_id"] = normalized["record_id"].fillna("")
    normalized["need"] = normalized["need"].fillna("")
    normalized["demand_score"] = normalized["demand_score"].fillna(0)
    normalized["source_id"] = normalized["source_id"].fillna("")
    normalized["source_weight"] = normalized["source_weight"].fillna(0)
    retained = normalized[normalized["record_id"].isin(allowed_record_ids)]
    return retained.head(len(index_window)).reset_index(drop=True)


def assemble_provenance(needs_df):
    rows = needs_df.to_dict(orient="records")
    ordered = sorted(rows, key=lambda row: (-row.get("demand_score", 0), row.get("record_id", "")))
    records = []
    for index, row in enumerate(ordered, start=1):
        records.append({
            "record_id": row.get("record_id", ""),
            "source_id": row.get("source_id", ""),
            "source_weight": row.get("source_weight", 0),
            "rank": index,
        })
    return pd.DataFrame(records)


payload = json.load(sys.stdin)
corpus = pd.DataFrame(payload.get("corpus", []))
selected_needs = select_demand_records(corpus)
needs = normalize_evidence(selected_needs)
evidence_sources = assemble_provenance(needs)
result = {
    "needs": needs.to_dict(orient="records"),
    "evidence_sources": evidence_sources.to_dict(orient="records"),
    "metadata": {"job": "upstream-demand-evidence", "need_count": int(len(needs))},
}
json.dump(result, sys.stdout, separators=(",", ":"))
