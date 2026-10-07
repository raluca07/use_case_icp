"""Attempt-048 Job 3: campaign aggregation and constrained allocation."""

import json
import sys

import pandas as pd


def aggregate_campaign_candidates(portfolio_df, attribution_df):
    candidates_df = portfolio_df.groupby(
        ["campaign_id", "segment", "channel_hint"], as_index=False, sort=True
    ).agg(
        opportunity_count=("opportunity_id", "nunique"),
        combined_priority=("priority_score", "sum"),
        campaign_revenue=("estimated_revenue", "sum"),
    )
    contribution_audit_df = attribution_df[["contribution_id", "campaign_id"]].sort_values(
        ["campaign_id", "contribution_id"], kind="stable"
    ).reset_index(drop=True)
    return candidates_df, contribution_audit_df


def join_campaign_economics(candidates_df, audience_df, economics_df):
    audience_joined_df = candidates_df.merge(
        audience_df, on="segment", how="left", validate="many_to_one"
    )
    economics_joined_df = audience_joined_df.merge(
        economics_df, left_on="channel_hint", right_on="channel", how="left", validate="many_to_one"
    )
    economics_joined_df["expected_impact"] = (
        economics_joined_df["combined_priority"]
        * economics_joined_df["audience_size"] / 10000.0
        * economics_joined_df["conversion_rate"]
    ).round(4)
    return economics_joined_df


def allocate_campaign_budget(scored_df, budget_policy):
    allocated_df = scored_df.sort_values(
        ["expected_impact", "campaign_id"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    allocated_df["requested_budget"] = (
        float(budget_policy["base_campaign_budget"])
        + allocated_df["expected_impact"] * float(budget_policy["impact_budget_multiplier"])
    ).round(-2)
    allocations = []
    total_used = 0.0
    channel_used = {}
    for row in allocated_df.to_dict(orient="records"):
        channel = row["channel"]
        channel_remaining = float(budget_policy["per_channel_caps"][channel]) - channel_used.get(channel, 0.0)
        total_remaining = float(budget_policy["total_budget"]) - total_used
        amount = max(0.0, min(float(row["requested_budget"]), channel_remaining, total_remaining))
        channel_used[channel] = channel_used.get(channel, 0.0) + amount
        total_used += amount
        allocations.append({
            "campaign_id": row["campaign_id"], "segment": row["segment"],
            "channel": channel, "allocated_budget": amount,
            "expected_impact": row["expected_impact"],
            "opportunity_count": int(row["opportunity_count"]),
        })
    return pd.DataFrame(allocations)


def main():
    value = json.load(sys.stdin)
    portfolio_df = pd.DataFrame(value["priority_portfolio"])
    attribution_df = pd.DataFrame(value["evidence_attribution"])
    audience_df = pd.DataFrame(value["audience_economics"])
    economics_df = pd.DataFrame(value["channel_economics"])
    candidates_df, contribution_audit_df = aggregate_campaign_candidates(portfolio_df, attribution_df)
    scored_df = join_campaign_economics(candidates_df, audience_df, economics_df)
    allocations_df = allocate_campaign_budget(scored_df, value["budget_policy"])
    result = {
        "campaign_allocations": allocations_df.to_dict(orient="records"),
        "contribution_audit": contribution_audit_df.to_dict(orient="records"),
        "metadata": {
            "candidate_count": int(len(candidates_df)),
            "allocation_count": int(len(allocations_df)),
            "allocated_budget_total": float(allocations_df["allocated_budget"].sum()),
            "consumed_handoffs": ["priority_portfolio", "evidence_attribution", "metadata"],
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
