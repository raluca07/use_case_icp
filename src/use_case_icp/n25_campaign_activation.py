"""Deterministic Job 4 for N25: plan activation for every campaign item."""

import json
import sys

import pandas as pd


def map_delivery_channels(campaign_items, delivery_rules):
    rules_df = pd.DataFrame(delivery_rules)
    rules = {
        row["message_strategy"]: {
            "channel": row["channel"],
            "action_type": row["action_type"],
        }
        for _, row in rules_df.iterrows()
    }
    mapped = []
    for item in campaign_items:
        row = dict(item)
        mapping = rules.get(row.get("message_strategy"), {})
        row["channel"] = mapping.get("channel")
        row["action_type"] = mapping.get("action_type")
        mapped.append(row)
    return mapped


def schedule_campaign_actions(mapped_items):
    launch_actions = []
    evidence_review_actions = []
    ordered = sorted(mapped_items, key=lambda row: (row.get("priority_rank", 0), row.get("record_id", "")))
    ordered_df = pd.DataFrame(ordered)
    for _, action in ordered_df.iterrows():
        item = action.to_dict()
        destination = (
            launch_actions
            if item.get("evidence_status") == "traceable" and item.get("channel") and item.get("action_type")
            else evidence_review_actions
        )
        destination.append(dict(item))
    return {"launch_actions": launch_actions, "evidence_review_actions": evidence_review_actions}


def assemble_activation_plan(campaign_portfolio, scheduled_actions):
    launch = scheduled_actions["launch_actions"]
    review = scheduled_actions["evidence_review_actions"]
    channel_counts = {}
    actions_df = pd.DataFrame([*launch, *review])
    for _, action in actions_df.iterrows():
        item = action.to_dict()
        channel = item.get("channel") or "unmapped"
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
    channel_mix = [
        {"channel": channel, "action_count": channel_counts[channel]}
        for channel in sorted(channel_counts)
    ]
    return {
        "activation_plan": {
            "recommended_focus": campaign_portfolio.get("recommended_focus"),
            "recommended_decision": campaign_portfolio.get("recommended_decision"),
            "launch_actions": launch,
            "evidence_review_actions": review,
            "channel_mix": channel_mix,
            "plan_summary": f"Scheduled {len(launch)} launch actions and {len(review)} evidence-review actions.",
        },
        "metadata": {
            "scheduled_action_count": len(launch),
            "review_action_count": len(review),
            "total_action_count": len(launch) + len(review),
            "rules_version": "n25-delivery-rules-1",
            "consumed_handoffs": ["campaign_portfolio", "metadata"],
        },
    }


def main():
    input_object = json.load(sys.stdin)
    portfolio = input_object.get("campaign_portfolio", {})
    mapped = map_delivery_channels(portfolio.get("items", []), input_object.get("delivery_rules", []))
    scheduled = schedule_campaign_actions(mapped)
    result = assemble_activation_plan(portfolio, scheduled)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
