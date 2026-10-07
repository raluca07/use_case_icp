"""Attempt-053 Job 3: aggregate and allocate marketing campaigns."""

import hashlib
import json
import sys

import pandas as pd


def aggregate_campaign_candidates(portfolio_df, attribution_df):
    campaign_candidates_df = portfolio_df.groupby(
        ["campaign_id", "segment", "channel"], as_index=False, sort=True
    ).agg(
        opportunity_count=("opportunity_id", "nunique"),
        combined_priority=("priority_score", "sum"),
        campaign_revenue=("estimated_revenue", "sum"),
    )
    campaign_identity_df = portfolio_df[["opportunity_id", "campaign_id"]].drop_duplicates()
    contribution_audit_df = attribution_df.drop(columns=["campaign_id"]).merge(
        campaign_identity_df,
        on="opportunity_id",
        how="inner",
        validate="many_to_one",
    )[[
        "contribution_id", "opportunity_id", "source_id", "segment", "campaign_id",
        "effective_date", "recorded_at", "evidence_value", "reliability", "weighted_contribution",
    ]].sort_values(
        ["campaign_id", "opportunity_id", "source_id", "effective_date"], kind="stable"
    ).reset_index(drop=True)
    rows = contribution_audit_df.to_dict(orient="records")
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    attribution_commitment = {
        "logical_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "record_count": len(rows),
    }
    return campaign_candidates_df, attribution_commitment


def score_campaign_candidates(campaign_candidates_df, audience_df, channel_df):
    campaign_scoring_df = campaign_candidates_df.merge(
        audience_df, on="segment", how="left", validate="many_to_one"
    ).merge(
        channel_df, on="channel", how="left", validate="many_to_one"
    )
    campaign_scoring_df["expected_impact"] = (
        campaign_scoring_df["combined_priority"]
        * campaign_scoring_df["audience_size"] / 10000.0
        * campaign_scoring_df["conversion_rate"]
    ).round(4)
    return campaign_scoring_df


def allocate_campaign_budget(campaign_scoring_df, budget_policy):
    ordered_df = campaign_scoring_df.sort_values(
        ["expected_impact", "campaign_id"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    ordered_df["requested_budget"] = (
        float(budget_policy["base_campaign_budget"])
        + ordered_df["expected_impact"] * float(budget_policy["impact_budget_multiplier"])
    ).round(2)
    allocations = []
    total_used = 0.0
    channel_used = {}
    for row in ordered_df.to_dict(orient="records"):
        channel = row["channel"]
        amount = max(0.0, min(
            float(row["requested_budget"]),
            float(budget_policy["total_budget"]) - total_used,
            float(budget_policy["channel_caps"][channel]) - channel_used.get(channel, 0.0),
        ))
        amount = round(amount, 2)
        total_used = round(total_used + amount, 2)
        channel_used[channel] = round(channel_used.get(channel, 0.0) + amount, 2)
        allocations.append({
            "campaign_id": row["campaign_id"],
            "segment": row["segment"],
            "channel": channel,
            "allocated_budget": amount,
            "expected_impact": float(row["expected_impact"]),
            "opportunity_count": int(row["opportunity_count"]),
        })
    return pd.DataFrame(allocations)


def main():
    value = json.load(sys.stdin)
    portfolio_df = pd.DataFrame(value["priority_portfolio"])
    attribution_df = pd.DataFrame(value["evidence_attribution"])
    audience_df = pd.DataFrame(value["audience_economics"])
    channel_df = pd.DataFrame(value["channel_economics"])
    campaign_candidates_df, attribution_commitment = aggregate_campaign_candidates(
        portfolio_df, attribution_df
    )
    campaign_scoring_df = score_campaign_candidates(
        campaign_candidates_df, audience_df, channel_df
    )
    allocations_df = allocate_campaign_budget(
        campaign_scoring_df, value["budget_policy"]
    )
    result = {
        "campaign_allocations": allocations_df.to_dict(orient="records"),
        "attribution_commitment": attribution_commitment,
        "metadata": {
            "candidate_count": int(len(campaign_candidates_df)),
            "allocation_count": int(len(allocations_df)),
            "allocated_budget_total": round(float(allocations_df["allocated_budget"].sum()), 2),
            "expected_impact_total": round(float(allocations_df["expected_impact"].sum()), 4),
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

