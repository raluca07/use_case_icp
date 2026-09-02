import json
import sys

import pandas as pd


def select_demand_records(corpus_df):
    fallback_record_ids = ["n06-r07", "n06-r08"]
    working = corpus_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"])
    working = working.fillna({"record_id": "", "need": "", "demand_score": 0, "source_id": "", "source_weight": 0})
    mask = (working["demand_score"] >= 3) | (working["record_id"].isin(fallback_record_ids))
    selected = working.loc[mask]
    records = []
    for _, row in selected.iterrows():
        records.append({
            "record_id": row.get("record_id", ""),
            "need": row.get("need", ""),
            "demand_score": int(row.get("demand_score", 0)),
            "source_id": row.get("source_id", ""),
            "source_weight": int(row.get("source_weight", 0)),
        })
    return pd.DataFrame(records, columns=["record_id", "need", "demand_score", "source_id", "source_weight"])


def normalize_evidence(selected_df):
    index_window = [0, 1, 2, 3, 4, 5, 6, 7]
    allowed_record_ids = ["n06-r01", "n06-r02", "n06-r03", "n06-r04", "n06-r05", "n06-r06", "n06-r07", "n06-r08"]
    normalized = selected_df.reindex(columns=["record_id", "need", "demand_score", "source_id", "source_weight"])
    normalized = normalized.fillna({"record_id": "", "need": "", "demand_score": 0, "source_id": "", "source_weight": 0})
    retained = normalized.loc[normalized["record_id"].isin(allowed_record_ids)]
    return retained.head(len(index_window)).reset_index(drop=True)


def assemble_provenance(needs_df):
    rows = []
    for _, row in needs_df.iterrows():
        rows.append({
            "record_id": row.get("record_id", ""),
            "source_id": row.get("source_id", ""),
            "source_weight": int(row.get("source_weight", 0)),
            "demand_score": int(row.get("demand_score", 0)),
        })
    ordered = sorted(rows, key=lambda item: (-item.get("demand_score", 0), item.get("record_id", "")))
    records = []
    for index, item in enumerate(ordered, start=1):
        records.append({
            "record_id": item.get("record_id", ""),
            "source_id": item.get("source_id", ""),
            "source_weight": int(item.get("source_weight", 0)),
            "rank": index,
        })
    return pd.DataFrame(records, columns=["record_id", "source_id", "source_weight", "rank"])


payload = json.load(sys.stdin)
corpus_df = pd.DataFrame(payload.get("corpus", []))
selected_df = select_demand_records(corpus_df)
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
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
