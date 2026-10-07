"""Attempt-049 Job 1: market-evidence qualification and attribution."""

import json
import sys

import pandas as pd


def filter_applicable_evidence(observations_df, policy):
    as_of = pd.Timestamp(policy["as_of_date"])
    dated_df = observations_df.assign(
        _effective_time=pd.to_datetime(observations_df["effective_date"]),
        _ingested_time=pd.to_datetime(observations_df["ingested_at"]),
        _valid_until=pd.to_datetime(observations_df["valid_until"]),
    )
    applicable_df = dated_df.loc[
        dated_df["_effective_time"].le(as_of) & dated_df["_valid_until"].ge(as_of)
    ].drop(columns=["_effective_time", "_ingested_time", "_valid_until"])
    return applicable_df.reset_index(drop=True)


def normalize_source_observations(applicable_df):
    ordered_df = applicable_df.sort_values(
        ["opportunity_id", "source_id", "effective_date"],
        ascending=[True, True, False],
        kind="stable",
    )
    per_source_df = ordered_df.drop_duplicates(
        ["opportunity_id", "source_id"], keep="first"
    )
    return per_source_df.reset_index(drop=True)


def assemble_opportunity_evidence(per_source_df, policy):
    scoped_df = per_source_df.drop_duplicates(
        ["opportunity_id", "source_id"], keep="first"
    )
    group_fields = ["opportunity_id", "segment", "campaign_id", "channel_hint"]
    full_precision_df = scoped_df.groupby(group_fields, as_index=False, sort=True).agg(
        full_precision_score=("contribution_score", "sum"),
        evidence_source_count=("source_id", "nunique"),
        estimated_revenue=("estimated_revenue", "max"),
    )
    reported_df = full_precision_df.assign(
        reported_score=full_precision_df["full_precision_score"].round(
            int(policy["reporting_precision"])
        )
    )
    thresholds_df = pd.DataFrame(
        [{"segment": segment, "minimum_score": score} for segment, score in policy["segment_minimum_scores"].items()]
    )
    eligibility_df = reported_df.merge(thresholds_df, on="segment", how="left", validate="many_to_one")
    eligibility_df["eligible"] = (
        eligibility_df["full_precision_score"].ge(eligibility_df["minimum_score"])
        & eligibility_df["evidence_source_count"].ge(int(policy["minimum_distinct_sources"]))
    )
    opportunities_df = eligibility_df.loc[eligibility_df["eligible"], [
        "opportunity_id", "segment", "campaign_id", "channel_hint",
        "full_precision_score", "reported_score", "evidence_source_count", "estimated_revenue",
    ]].sort_values("opportunity_id", kind="stable").reset_index(drop=True)
    attribution_df = scoped_df.merge(
        opportunities_df[["opportunity_id"]], on="opportunity_id", how="inner", validate="many_to_one"
    )
    attribution_df = attribution_df[[
        "contribution_id", "opportunity_id", "source_id", "contribution_score",
        "effective_date", "segment", "campaign_id",
    ]].sort_values(["opportunity_id", "source_id", "contribution_id"], kind="stable").reset_index(drop=True)
    return opportunities_df, attribution_df


def main():
    value = json.load(sys.stdin)
    observations_df = pd.DataFrame(value["market_observations"])
    policy = value["selection_policy"]
    applicable_df = filter_applicable_evidence(observations_df, policy)
    per_source_df = normalize_source_observations(applicable_df)
    opportunities_df, attribution_df = assemble_opportunity_evidence(per_source_df, policy)
    result = {
        "opportunities": opportunities_df.to_dict(orient="records"),
        "evidence_attribution": attribution_df.to_dict(orient="records"),
        "metadata": {
            "applicable_observation_count": int(len(applicable_df)),
            "per_source_observation_count": int(len(per_source_df)),
            "qualified_opportunity_count": int(len(opportunities_df)),
            "attribution_count": int(len(attribution_df)),
            "scenario_id": value.get("scenario_id", ""),
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
