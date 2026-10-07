"""Attempt-045 DataFrame-native campaign portfolio generation."""

import json
import sys

import pandas as pd


ITEM_FIELDS = [
    "record_id",
    "need",
    "priority_rank",
    "upstream_rank",
    "capability_id",
    "coverage",
    "unsupported",
]


def build_campaign_items(priorities_df):
    return priorities_df.loc[:, ITEM_FIELDS].copy()


def assign_message_strategy(items_df, recommendation):
    recommendation.get("top_need", "")
    assigned_df = items_df.copy()
    assigned_df["campaign_role"] = assigned_df["priority_rank"].eq(1).map(
        {True: "primary", False: "supporting"}
    )
    assigned_df["message_strategy"] = assigned_df["unsupported"].map(
        {True: "gap_education", False: "capability_reinforcement"}
    )
    assigned_df["evidence_status"] = assigned_df["upstream_rank"].gt(0).map(
        {True: "traceable", False: "evidence_review_required"}
    )
    return assigned_df


def assemble_campaign_portfolio(assigned_df, coverage_df, recommendation):
    coverage_counts = coverage_df["coverage"].value_counts().to_dict()
    coverage_totals = {
        "direct": int(coverage_counts.get("direct", 0)),
        "none": int(coverage_counts.get("none", 0)),
        "other": int(
            sum(count for label, count in coverage_counts.items() if label not in {"direct", "none"})
        ),
    }
    campaign_items = assigned_df.to_dict(orient="records")
    review_count = int(assigned_df["evidence_status"].ne("traceable").sum())
    return {
        "campaign_portfolio": {
            "recommended_focus": recommendation.get("top_need"),
            "recommended_decision": recommendation.get("decision"),
            "items": campaign_items,
            "coverage_totals": coverage_totals,
        },
        "metadata": {
            "item_count": len(campaign_items),
            "traceable_item_count": len(campaign_items) - review_count,
            "evidence_review_item_count": review_count,
            "input_coverage_count": len(coverage_df),
            "input_priority_count": len(campaign_items),
            "consumed_handoffs": ["coverage", "priorities", "recommendation", "metadata"],
        },
    }


def main():
    input_object = json.load(sys.stdin)
    priorities_df = pd.DataFrame(input_object.get("priorities", []))
    coverage_df = pd.DataFrame(input_object.get("coverage", []))
    recommendation = input_object.get("recommendation", {})
    items_df = build_campaign_items(priorities_df)
    assigned_df = assign_message_strategy(items_df, recommendation)
    result = assemble_campaign_portfolio(assigned_df, coverage_df, recommendation)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
