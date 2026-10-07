"""Attempt-045 DataFrame-native campaign activation planning."""

import json
import sys

import pandas as pd


def map_delivery_channels(campaign_items_df, delivery_rules_df):
    mapped_df = campaign_items_df.merge(
        delivery_rules_df.loc[:, ["message_strategy", "channel", "action_type"]],
        how="left",
        on="message_strategy",
        sort=False,
        validate="many_to_one",
    )
    mapped_df[["channel", "action_type"]] = mapped_df[["channel", "action_type"]].where(
        mapped_df[["channel", "action_type"]].notna(), None
    )
    return mapped_df


def schedule_campaign_actions(mapped_df):
    scheduled_df = mapped_df.sort_values(
        ["priority_rank", "record_id"], kind="stable"
    ).reset_index(drop=True)
    launchable = (
        scheduled_df["evidence_status"].eq("traceable")
        & scheduled_df["channel"].notna()
        & scheduled_df["action_type"].notna()
    )
    scheduled_df["action_status"] = launchable.map(
        {True: "launch", False: "evidence_review"}
    )
    return scheduled_df


def assemble_activation_plan(campaign_portfolio, scheduled_df):
    action_columns = [column for column in scheduled_df.columns if column != "action_status"]
    launch_actions = scheduled_df.loc[
        scheduled_df["action_status"].eq("launch"), action_columns
    ].to_dict(orient="records")
    evidence_review_actions = scheduled_df.loc[
        scheduled_df["action_status"].eq("evidence_review"), action_columns
    ].to_dict(orient="records")
    channel_counts = scheduled_df["channel"].fillna("unmapped").value_counts().to_dict()
    channel_mix = [
        {"channel": channel, "action_count": int(channel_counts[channel])}
        for channel in sorted(channel_counts)
    ]
    return {
        "activation_plan": {
            "recommended_focus": campaign_portfolio.get("recommended_focus"),
            "recommended_decision": campaign_portfolio.get("recommended_decision"),
            "launch_actions": launch_actions,
            "evidence_review_actions": evidence_review_actions,
            "channel_mix": channel_mix,
            "plan_summary": (
                f"Scheduled {len(launch_actions)} launch actions and "
                f"{len(evidence_review_actions)} evidence-review actions."
            ),
        },
        "metadata": {
            "scheduled_action_count": len(launch_actions),
            "review_action_count": len(evidence_review_actions),
            "total_action_count": len(scheduled_df),
            "rules_version": "n25-delivery-rules-1",
            "consumed_handoffs": ["campaign_portfolio", "metadata"],
        },
    }


def main():
    input_object = json.load(sys.stdin)
    campaign_portfolio = input_object.get("campaign_portfolio", {})
    campaign_items_df = pd.DataFrame(campaign_portfolio.get("items", []))
    delivery_rules_df = pd.DataFrame(input_object.get("delivery_rules", []))
    mapped_df = map_delivery_channels(campaign_items_df, delivery_rules_df)
    scheduled_df = schedule_campaign_actions(mapped_df)
    result = assemble_activation_plan(campaign_portfolio, scheduled_df)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
