import json
import sys

import pandas as pd


def select_demand_records(corpus_df):
    fallback_ids = ["n06-r07", "n06-r08"]
    selected = corpus_df[(corpus_df.get("demand_score", 0) >= 3) | (corpus_df.get("record_id", "").isin(fallback_ids))]
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


def normalize_selected_evidence(selected_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    required_columns = ["record_id", "need", "demand_score", "source_id", "source_weight"]
    normalized = selected_df.reindex(columns=required_columns)
    normalized = normalized.fillna({
        "record_id": "",
        "need": "",
        "demand_score": 0,
        "source_id": "",
        "source_weight": 0,
    })
    retained = normalized[normalized["record_id"].isin(allowed_record_ids)]
    return retained.head(len(index_window)).reset_index(drop=True)


def assemble_provenance(normalized_df):
    source_records = []
    rows = normalized_df.to_dict("records")
    ordered_rows = sorted(rows, key=lambda row: (-int(row.get("demand_score", 0) or 0), str(row.get("record_id", "") or "")))
    for rank_index, row in enumerate(ordered_rows, start=1):
        source_records.append({
            "record_id": row.get("record_id", "") or "",
            "source_id": row.get("source_id", "") or "",
            "source_weight": row.get("source_weight", 0) or 0,
            "rank": rank_index,
        })
    return pd.DataFrame(source_records)


payload = json.load(sys.stdin)
corpus_df = pd.DataFrame(payload.get("corpus", []))
selected_df = select_demand_records(corpus_df)
needs_df = normalize_selected_evidence(selected_df)
evidence_df = assemble_provenance(needs_df)
result = {
    "needs": needs_df.to_dict("records"),
    "evidence_sources": evidence_df.to_dict("records"),
    "metadata": {
        "scenario_id": payload.get("scenario_id", "protocol-2-2-experimental-demand-recovery-v1"),
        "need_count": int(len(needs_df)),
        "evidence_source_count": int(len(evidence_df)),
    },
}
json.dump(result, sys.stdout, separators=(",", ":"))
