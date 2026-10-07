"""Clean N26 Job 1: policy-driven demand selection and provenance."""

import json
import sys

import pandas as pd


def select_demand(corpus_df, policy):
    selected = []
    precision = int(policy["score_precision"])
    for (record_id, segment), group in corpus_df.groupby(["record_id", "segment"], sort=True):
        aggregate_demand = round(float(group["demand_score"].sum()), precision)
        distinct_sources = set(group["source_id"].tolist())
        qualifying_sources = set(group.loc[group["qualified"], "source_id"].tolist())
        qualifying_rate = len(qualifying_sources) / len(distinct_sources)
        threshold = float(policy["segment_thresholds"].get(segment, policy["default_threshold"]))
        representative_source_id = str(group.iloc[0]["source_id"])
        representative_weight = float(group["source_weight"].max())
        threshold_value = aggregate_demand
        threshold_passed = threshold_value >= threshold
        is_fallback = record_id in policy["fallback_record_ids"]
        decision_df = pd.DataFrame([{
            "record_id": record_id,
            "aggregate_demand": aggregate_demand,
            "qualifying_source_rate": qualifying_rate,
            "threshold": threshold,
            "threshold_value": threshold_value,
            "threshold_passed": threshold_passed,
            "is_fallback": is_fallback,
        }])
        decision_df.get("record_id")
        if (threshold_passed and qualifying_rate >= policy["minimum_qualifying_source_rate"]) or is_fallback:
            for _, observation in group.iterrows():
                selected.append({
                    "record_id": record_id,
                    "need": observation["need"],
                    "segment": segment,
                    "aggregate_demand": aggregate_demand,
                    "qualifying_source_rate": qualifying_rate,
                    "source_id": observation["source_id"],
                    "source_weight": float(observation["source_weight"]),
                    "is_fallback": is_fallback,
                    "representative_source_id": representative_source_id,
                    "representative_weight": representative_weight,
                })
    return pd.DataFrame(selected)


def normalize(selected_df, policy):
    survivors = []
    for _, group in selected_df.groupby("record_id", sort=True):
        survivor = group.sort_values(
            ["source_weight", "source_id"], ascending=[False, True]
        ).iloc[0]
        survivors.append(survivor.to_dict())
    fallbacks = sorted(
        [row for row in survivors if row["is_fallback"]],
        key=lambda row: row["record_id"],
    )
    primaries = sorted(
        [row for row in survivors if not row["is_fallback"]],
        key=lambda row: (-row["aggregate_demand"], row["record_id"]),
    )
    retained = (fallbacks + primaries)[: int(policy["retained_capacity"])]
    return pd.DataFrame([
        {
            "record_id": row["record_id"],
            "need": row["need"],
            "demand_score": row["aggregate_demand"],
            "source_id": row["source_id"],
            "source_weight": row["source_weight"],
        }
        for row in retained
    ])


def assemble_provenance(needs_df, policy):
    precision = int(policy["score_precision"])
    ordered = sorted(
        needs_df.to_dict(orient="records"),
        key=lambda row: (
            -round(float(row["demand_score"]), precision),
            -float(row["source_weight"]),
            row["record_id"],
        ),
    )
    provenance = []
    for rank, row in enumerate(ordered, start=1):
        provenance.append({
            "record_id": row["record_id"],
            "source_id": row["source_id"],
            "source_weight": row["source_weight"],
            "rank": rank,
        })
    return pd.DataFrame(provenance)


def main():
    input_object = json.load(sys.stdin)
    corpus_df = pd.DataFrame(input_object["corpus"])
    policy = input_object["selection_policy"]
    selected_df = select_demand(corpus_df, policy)
    needs_df = normalize(selected_df, policy)
    evidence_sources_df = assemble_provenance(needs_df, policy)
    result = {
        "needs": needs_df.to_dict(orient="records"),
        "evidence_sources": evidence_sources_df.to_dict(orient="records"),
        "metadata": {
            "record_count": int(len(needs_df)),
            "evidence_source_count": int(len(evidence_sources_df)),
            "scenario_id": input_object.get("scenario_id", ""),
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
