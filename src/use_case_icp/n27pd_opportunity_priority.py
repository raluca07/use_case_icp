"""Attempt-048 Job 2: commercial opportunity prioritisation."""

import json
import sys

import pandas as pd


def join_commercial_context(opportunities_df, coverage_df, commercial_df):
    covered_df = opportunities_df.merge(
        coverage_df, on="segment", how="left", validate="many_to_one"
    )
    enriched_df = covered_df.merge(
        commercial_df, on="opportunity_id", how="left", validate="one_to_one"
    )
    return enriched_df


def calculate_priority_inputs(enriched_df, attribution_df):
    support_df = attribution_df.groupby("opportunity_id", as_index=False).agg(
        attributed_score=("contribution_score", "sum"),
        attributed_source_count=("source_id", "nunique"),
    )
    scored_df = enriched_df.merge(
        support_df, on="opportunity_id", how="left", validate="one_to_one"
    )
    scored_df["priority_score"] = (
        scored_df["full_precision_score"] * scored_df["coverage_multiplier"]
        + scored_df["attributed_score"] * 0.1
        + scored_df["estimated_revenue"] * scored_df["margin_rate"] / 10000.0
    ).round(4)
    return scored_df


def rank_opportunity_portfolio(scored_df):
    ranked_df = scored_df.sort_values(
        ["priority_score", "reported_score", "opportunity_id"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    ranked_df["portfolio_position"] = ranked_df.index + 1
    return ranked_df[[
        "opportunity_id", "segment", "campaign_id", "channel_hint", "priority_score",
        "portfolio_position", "estimated_revenue", "coverage_tier", "attributed_source_count",
    ]]


def main():
    value = json.load(sys.stdin)
    opportunities_df = pd.DataFrame(value["opportunities"])
    attribution_df = pd.DataFrame(value["evidence_attribution"])
    coverage_df = pd.DataFrame(value["capability_coverage"])
    commercial_df = pd.DataFrame(value["commercial_context"])
    enriched_df = join_commercial_context(opportunities_df, coverage_df, commercial_df)
    scored_df = calculate_priority_inputs(enriched_df, attribution_df)
    portfolio_df = rank_opportunity_portfolio(scored_df)
    result = {
        "priority_portfolio": portfolio_df.to_dict(orient="records"),
        "evidence_attribution": attribution_df.to_dict(orient="records"),
        "metadata": {
            "portfolio_count": int(len(portfolio_df)),
            "attribution_count": int(len(attribution_df)),
            "consumed_handoffs": ["opportunities", "evidence_attribution", "metadata"],
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
