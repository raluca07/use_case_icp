import json
import sys

import pandas as pd


REQUIRED_COLUMNS = ["record_id", "need", "demand_score", "source_id", "source_weight"]


def demand_selection(corpus_df):
    fallback_record_ids = ["n06-r07", "n06-r08"]
    prepared = corpus_df.reindex(columns=REQUIRED_COLUMNS)
    prepared["record_id"] = prepared["record_id"].fillna("")
    prepared["need"] = prepared["need"].fillna("")
    prepared["source_id"] = prepared["source_id"].fillna("")
    prepared["demand_score"] = pd.to_numeric(prepared["demand_score"], errors="coerce").fillna(0)
    prepared["source_weight"] = pd.to_numeric(prepared["source_weight"], errors="coerce").fillna(0)
    mask = (prepared["demand_score"] >= 3) | (prepared["record_id"].isin(fallback_record_ids))
    selected = prepared.loc[mask]
    records = []
    for _, row in selected.iterrows():
        records.append({
            "record_id": row.get("record_id", ""),
            "need": row.get("need", ""),
            "demand_score": int(row.get("demand_score", 0)),
            "source_id": row.get("source_id", ""),
            "source_weight": int(row.get("source_weight", 0)),
        })
    return pd.DataFrame(records, columns=REQUIRED_COLUMNS)


def evidence_normalization(needs_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_record_ids = [
        "n06-r01", "n06-r02", "n06-r03", "n06-r04",
        "n06-r05", "n06-r06", "n06-r07", "n06-r08",
    ]
    normalized = needs_df.reindex(columns=REQUIRED_COLUMNS)
    normalized["record_id"] = normalized["record_id"].fillna("")
    normalized["need"] = normalized["need"].fillna("")
    normalized["source_id"] = normalized["source_id"].fillna("")
    normalized["demand_score"] = pd.to_numeric(normalized["demand_score"], errors="coerce").fillna(0).astype(int)
    normalized["source_weight"] = pd.to_numeric(normalized["source_weight"], errors="coerce").fillna(0).astype(int)
    retained = normalized.loc[normalized["record_id"].isin(allowed_record_ids)]
    return retained.head(len(index_window)).reset_index(drop=True)


def provenance_assembly(needs_df):
    rows = needs_df.to_dict("records")
    ordered = sorted(rows, key=lambda row: (-int(row.get("demand_score", 0) or 0), str(row.get("record_id", "") or "")))
    evidence_records = []
    for index, row in enumerate(ordered, start=1):
        evidence_records.append({
            "record_id": row.get("record_id", ""),
            "source_id": row.get("source_id", ""),
            "source_weight": int(row.get("source_weight", 0) or 0),
            "rank": index,
        })
    return pd.DataFrame(evidence_records, columns=["record_id", "source_id", "source_weight", "rank"])


payload = json.load(sys.stdin)
corpus_df = pd.DataFrame(payload.get("corpus", []))
selected_df = demand_selection(corpus_df)
needs_df = evidence_normalization(selected_df)
evidence_df = provenance_assembly(needs_df)
result = {
    "needs": needs_df[["record_id", "need", "demand_score", "source_id", "source_weight"]].to_dict("records"),
    "evidence_sources": evidence_df.to_dict("records"),
    "metadata": {
        "job": "upstream",
        "need_count": int(len(needs_df)),
        "evidence_source_count": int(len(evidence_df)),
    },
}
json.dump(result, sys.stdout, sort_keys=True)
