"""Attempt-048 Job 4: capacity-constrained activation scheduling."""

import json
import sys

import pandas as pd


def join_calendar_capacity(allocations_df, calendar_df, capacity_df):
    candidate_windows_df = allocations_df.merge(
        calendar_df, on="channel", how="inner", validate="many_to_many"
    )
    feasible_windows_df = candidate_windows_df.merge(
        capacity_df, on=["channel", "window_id"], how="inner", validate="many_to_one"
    )
    feasible_windows_df = feasible_windows_df.loc[
        feasible_windows_df["available_slots"].gt(0)
    ].copy()
    return feasible_windows_df


def assign_activation_windows(feasible_windows_df):
    ordered_df = feasible_windows_df.sort_values(
        ["expected_impact", "campaign_id", "window_start"],
        ascending=[False, True, True], kind="stable",
    )
    remaining = {
        (row["channel"], row["window_id"]): int(row["available_slots"])
        for row in ordered_df.to_dict(orient="records")
    }
    campaign_counts = {}
    scheduled = []
    for row in ordered_df.to_dict(orient="records"):
        campaign = row["campaign_id"]
        key = (row["channel"], row["window_id"])
        if campaign_counts.get(campaign, 0) >= 2 or remaining[key] <= 0:
            continue
        campaign_counts[campaign] = campaign_counts.get(campaign, 0) + 1
        remaining[key] -= 1
        scheduled.append({
            "activation_id": f"activation-{len(scheduled) + 1:02d}",
            "campaign_id": campaign, "segment": row["segment"], "channel": row["channel"],
            "window_id": row["window_id"], "window_start": row["window_start"],
            "scheduled_budget": round(float(row["allocated_budget"]) / 2.0, 2),
            "expected_conversions": round(float(row["expected_impact"]) / 2.0, 4),
        })
    return pd.DataFrame(scheduled)


def aggregate_activation_forecast(scheduled_df):
    forecast_df = scheduled_df.groupby(
        ["window_id", "window_start", "channel"], as_index=False, sort=True
    ).agg(
        scheduled_budget=("scheduled_budget", "sum"),
        expected_conversions=("expected_conversions", "sum"),
        activation_count=("activation_id", "count"),
    )
    return {
        "activation_actions": scheduled_df.to_dict(orient="records"),
        "window_forecast": forecast_df.to_dict(orient="records"),
        "aggregate_forecast": {
            "scheduled_budget": round(float(scheduled_df["scheduled_budget"].sum()), 2),
            "expected_conversions": round(float(scheduled_df["expected_conversions"].sum()), 4),
            "activation_count": int(len(scheduled_df)),
        },
    }


def main():
    value = json.load(sys.stdin)
    allocations_df = pd.DataFrame(value["campaign_allocations"])
    calendar_df = pd.DataFrame(value["activation_calendar"])
    capacity_df = pd.DataFrame(value["channel_capacity"])
    feasible_df = join_calendar_capacity(allocations_df, calendar_df, capacity_df)
    scheduled_df = assign_activation_windows(feasible_df)
    activation_plan = aggregate_activation_forecast(scheduled_df)
    result = {
        "activation_plan": activation_plan,
        "metadata": {
            "campaign_count": int(allocations_df["campaign_id"].nunique()),
            "activation_count": int(len(scheduled_df)),
            "window_count": int(scheduled_df["window_id"].nunique()),
            "consumed_handoffs": ["campaign_allocations", "metadata"],
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
