"""Attempt-053 Job 2: prioritize qualified commercial opportunities."""

import json
import sys
from decimal import Decimal, ROUND_HALF_EVEN

import pandas as pd


def join_priority_context(opportunities_df, coverage_df, commercial_df):
    joined_commercial_coverage_df = opportunities_df.merge(
        coverage_df, on="segment", how="left", validate="many_to_one"
    ).merge(
        commercial_df, on="opportunity_id", how="left", validate="one_to_one"
    )
    return joined_commercial_coverage_df


def calculate_single_count_priority(joined_commercial_coverage_df, attribution_df):
    attribution_identity_df = attribution_df.groupby("opportunity_id", as_index=False).agg(
        retained_weighted_total=("weighted_contribution", "sum"),
        attributed_source_count=("source_id", "nunique"),
    )
    scored_df = joined_commercial_coverage_df.merge(
        attribution_identity_df, on="opportunity_id", how="left", validate="one_to_one"
    )
    if not scored_df["full_precision_score"].round(12).eq(
        scored_df["retained_weighted_total"].round(12)
    ).all():
        raise ValueError("qualified score and retained contribution total differ")
    scored_df["priority_score"] = [
        float((
            Decimal(str(row["full_precision_score"]))
            * Decimal(str(row["coverage_multiplier"]))
            + Decimal(str(row["estimated_revenue"]))
            * Decimal(str(row["margin_rate"])) / Decimal("100000")
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))
        for row in scored_df.to_dict(orient="records")
    ]
    return scored_df


def rank_priority_portfolio(scored_df):
    ranked_portfolio_df = scored_df.sort_values(
        ["priority_score", "display_score", "opportunity_id"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    ranked_portfolio_df["portfolio_position"] = ranked_portfolio_df.index + 1
    return ranked_portfolio_df[[
        "opportunity_id", "segment", "campaign_id", "channel", "priority_score",
        "portfolio_position", "estimated_revenue", "coverage_tier", "attributed_source_count",
    ]]


def main():
    value = json.load(sys.stdin)
    opportunities_df = pd.DataFrame(value["opportunities"])
    attribution_df = pd.DataFrame(value["evidence_attribution"])
    coverage_df = pd.DataFrame(value["capability_coverage"])
    commercial_df = pd.DataFrame(value["commercial_context"])
    joined_commercial_coverage_df = join_priority_context(
        opportunities_df, coverage_df, commercial_df
    )
    scored_df = calculate_single_count_priority(
        joined_commercial_coverage_df, attribution_df
    )
    ranked_portfolio_df = rank_priority_portfolio(scored_df)
    result = {
        "priority_portfolio": ranked_portfolio_df.to_dict(orient="records"),
        "evidence_attribution": attribution_df.to_dict(orient="records"),
        "metadata": {
            "joined_count": int(len(joined_commercial_coverage_df)),
            "portfolio_count": int(len(ranked_portfolio_df)),
            "attribution_count": int(len(attribution_df)),
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

