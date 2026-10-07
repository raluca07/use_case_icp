"""Attempt-052 Job 4: schedule aggregate campaign activations."""

import json
import sys
from decimal import Decimal, ROUND_HALF_EVEN

import pandas as pd


def join_available_windows(allocations_df, calendar_df, capacity_df):
    candidate_windows_df = allocations_df.merge(
        calendar_df, on="channel", how="inner", validate="many_to_many"
    )
    available_windows_df = candidate_windows_df.merge(
        capacity_df, on=["channel", "window_id"], how="inner", validate="many_to_one"
    )
    return available_windows_df.loc[
        available_windows_df["available_slots"].gt(0)
    ].copy()


def choose_activation_windows(available_windows_df, scheduling_policy):
    limit = int(scheduling_policy["max_windows_per_campaign"])
    ordered_df = available_windows_df.sort_values(
        ["expected_impact", "campaign_id", "window_start"],
        ascending=[False, True, True],
        kind="stable",
    )
    remaining = {
        (row["channel"], row["window_id"]): int(row["available_slots"])
        for row in ordered_df.to_dict(orient="records")
    }
    counts = {}
    selected = []
    for row in ordered_df.to_dict(orient="records"):
        campaign = row["campaign_id"]
        key = (row["channel"], row["window_id"])
        if counts.get(campaign, 0) >= limit or remaining[key] <= 0:
            continue
        counts[campaign] = counts.get(campaign, 0) + 1
        remaining[key] -= 1
        selected.append(row)
    return split_campaign_totals(selected, counts, scheduling_policy)


def split_campaign_totals(selected, counts, scheduling_policy):
    budget_unit = Decimal("1").scaleb(-int(scheduling_policy["budget_precision"]))
    impact_unit = Decimal("1").scaleb(-int(scheduling_policy["impact_precision"]))
    actions = []
    seen = {}
    budget_assigned = {}
    impact_assigned = {}
    for row in selected:
        campaign = row["campaign_id"]
        seen[campaign] = seen.get(campaign, 0) + 1
        final = seen[campaign] == counts[campaign]
        total_budget = Decimal(str(row["allocated_budget"]))
        total_impact = Decimal(str(row["expected_impact"]))
        if final:
            budget = total_budget - budget_assigned.get(campaign, Decimal("0"))
            impact = total_impact - impact_assigned.get(campaign, Decimal("0"))
        else:
            budget = (total_budget / counts[campaign]).quantize(budget_unit, rounding=ROUND_HALF_EVEN)
            impact = (total_impact / counts[campaign]).quantize(impact_unit, rounding=ROUND_HALF_EVEN)
        budget_assigned[campaign] = budget_assigned.get(campaign, Decimal("0")) + budget
        impact_assigned[campaign] = impact_assigned.get(campaign, Decimal("0")) + impact
        actions.append({
            "activation_id": f"activation-{len(actions) + 1:02d}",
            "campaign_id": campaign,
            "segment": row["segment"],
            "channel": row["channel"],
            "window_id": row["window_id"],
            "window_start": row["window_start"],
            "scheduled_budget": float(budget),
            "expected_impact": float(impact),
        })
    return pd.DataFrame(actions)


def aggregate_activation_schedule(actions_df, attribution_commitment, scheduling_policy):
    window_forecast_df = actions_df.groupby(
        ["window_id", "window_start", "channel"], as_index=False, sort=True
    ).agg(
        scheduled_budget=("scheduled_budget", "sum"),
        expected_impact=("expected_impact", "sum"),
        activation_count=("activation_id", "count"),
    )
    return {
        "activation_actions": actions_df.to_dict(orient="records"),
        "window_forecast": window_forecast_df.to_dict(orient="records"),
        "aggregate_forecast": {
            "scheduled_budget": round(float(actions_df["scheduled_budget"].sum()), int(scheduling_policy["budget_precision"])),
            "expected_impact": round(float(actions_df["expected_impact"].sum()), int(scheduling_policy["impact_precision"])),
            "activation_count": int(len(actions_df)),
        },
        "attribution_commitment": dict(attribution_commitment),
    }


def main():
    value = json.load(sys.stdin)
    allocations_df = pd.DataFrame(value["campaign_allocations"])
    calendar_df = pd.DataFrame(value["activation_calendar"])
    capacity_df = pd.DataFrame(value["channel_capacity"])
    available_windows_df = join_available_windows(allocations_df, calendar_df, capacity_df)
    activation_actions_df = choose_activation_windows(available_windows_df, value["scheduling_policy"])
    activation_plan = aggregate_activation_schedule(
        activation_actions_df, value["attribution_commitment"], value["scheduling_policy"]
    )
    result = {
        "activation_plan": activation_plan,
        "metadata": {
            "campaign_count": int(allocations_df["campaign_id"].nunique()),
            "activation_count": int(len(activation_actions_df)),
            "window_count": int(activation_actions_df["window_id"].nunique()),
        },
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
