"""Attempt-052 Job 1: qualify and aggregate market evidence."""

import json
import sys

import pandas as pd


def select_snapshot_observations(observations_df, planning_policy):
    snapshot = pd.Timestamp(planning_policy["as_of_date"])
    dated_df = observations_df.assign(
        _effective=pd.to_datetime(observations_df["effective_date"]),
        _recorded=pd.to_datetime(observations_df["recorded_at"]),
        _expires=pd.to_datetime(observations_df["valid_until"]),
    )
    applicable_df = dated_df.loc[
        dated_df["_effective"].le(snapshot)
        & dated_df["_recorded"].le(snapshot)
        & dated_df["_expires"].ge(snapshot)
    ].drop(columns=["_effective", "_recorded", "_expires"])
    return applicable_df.reset_index(drop=True)


def reduce_source_repeats(applicable_df):
    survivor_order = "effective_date"
    ordered_df = applicable_df.sort_values(
        ["opportunity_id", "source_id", survivor_order],
        ascending=[True, True, False],
        kind="stable",
    )
    normalized_df = ordered_df.drop_duplicates(
        ["opportunity_id", "source_id"], keep="first"
    )
    return normalized_df.reset_index(drop=True)


def weight_source_reliability(normalized_df, reliability_df, planning_policy):
    join_columns = ["source_id", "segment"]
    weighted_df = normalized_df.merge(
        reliability_df,
        on=join_columns,
        how="left",
        validate="many_to_many",
    )
    if "segment_x" in weighted_df.columns:
        weighted_df = weighted_df.drop(columns=["segment_y"]).rename(columns={"segment_x": "segment"})
    weighted_df["weighted_contribution"] = (
        weighted_df["evidence_value"] * weighted_df["reliability"]
    )
    eligibility_df, opportunities_df, attribution_df = aggregate_opportunity_evidence(
        weighted_df, planning_policy
    )
    return weighted_df, eligibility_df, opportunities_df, attribution_df


def aggregate_opportunity_evidence(weighted_df, planning_policy):
    keys = ["opportunity_id", "segment", "campaign_id", "channel"]
    aggregated_df = weighted_df.groupby(keys, as_index=False, sort=True).agg(
        full_precision_score=("weighted_contribution", "sum"),
        source_count=("source_id", "nunique"),
        estimated_revenue=("estimated_revenue", "max"),
    )
    aggregated_df["display_score"] = aggregated_df["full_precision_score"].round(
        int(planning_policy["display_precision"])
    )
    threshold_df = pd.DataFrame([
        {"segment": segment, "eligibility_threshold": threshold}
        for segment, threshold in planning_policy["eligibility_thresholds"].items()
    ])
    eligibility_df = aggregated_df.merge(
        threshold_df, on="segment", how="left", validate="many_to_one"
    )
    decision_score = eligibility_df["full_precision_score"]
    eligibility_df["eligible"] = (
        decision_score.ge(eligibility_df["eligibility_threshold"])
        & eligibility_df["source_count"].ge(int(planning_policy["minimum_sources"]))
    )
    opportunities_df = eligibility_df.loc[eligibility_df["eligible"], [
        "opportunity_id", "segment", "campaign_id", "channel",
        "full_precision_score", "display_score", "source_count", "estimated_revenue",
    ]].sort_values("opportunity_id", kind="stable").reset_index(drop=True)
    attribution_df = weighted_df.merge(
        opportunities_df[["opportunity_id"]],
        on="opportunity_id",
        how="inner",
        validate="many_to_one",
    )[[
        "contribution_id", "opportunity_id", "source_id", "segment", "campaign_id",
        "effective_date", "recorded_at", "evidence_value", "reliability", "weighted_contribution",
    ]].sort_values(
        ["opportunity_id", "source_id", "effective_date"], kind="stable"
    ).reset_index(drop=True)
    return eligibility_df, opportunities_df, attribution_df


def main():
    value = json.load(sys.stdin)
    observations_df = pd.DataFrame(value["market_observations"])
    reliability_df = pd.DataFrame(value["source_reliability"])
    applicable_df = select_snapshot_observations(observations_df, value["planning_policy"])
    normalized_df = reduce_source_repeats(applicable_df)
    weighted_df, eligibility_df, opportunities_df, attribution_df = weight_source_reliability(
        normalized_df, reliability_df, value["planning_policy"]
    )
    result = {
        "opportunities": opportunities_df.to_dict(orient="records"),
        "evidence_attribution": attribution_df.to_dict(orient="records"),
        "metadata": {
            "applicable_count": int(len(applicable_df)),
            "normalized_count": int(len(normalized_df)),
            "weighted_count": int(len(weighted_df)),
            "decision_count": int(len(eligibility_df)),
            "eligible_count": int(len(opportunities_df)),
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
