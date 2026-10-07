"""Deterministic Job 3 for N25: build a complete campaign portfolio."""

import json
import sys

import pandas as pd


def build_campaign_items(priorities):
    fields = (
        "record_id", "need", "priority_rank", "upstream_rank",
        "capability_id", "coverage", "unsupported",
    )
    items = []
    priorities_df = pd.DataFrame(priorities)
    for _, priority in priorities_df.iterrows():
        row = priority.to_dict()
        items.append({field: row.get(field) for field in fields})
    return items


def assign_message_strategy(campaign_items, recommendation):
    recommendation.get("top_need", "")
    assigned = []
    items_df = pd.DataFrame(campaign_items)
    for _, item in items_df.iterrows():
        row = item.to_dict()
        rank = row.get("upstream_rank")
        row.update({
            "campaign_role": "primary" if row.get("priority_rank") == 1 else "supporting",
            "message_strategy": "gap_education" if row.get("unsupported") else "capability_reinforcement",
            "evidence_status": "traceable" if isinstance(rank, int) and rank > 0 else "evidence_review_required",
        })
        assigned.append(row)
    return assigned


def assemble_campaign_portfolio(campaign_items, coverage, recommendation):
    coverage_totals = {"direct": 0, "none": 0, "other": 0}
    coverage_df = pd.DataFrame(coverage)
    for _, coverage_row in coverage_df.iterrows():
        row = coverage_row.to_dict()
        label = row.get("coverage")
        coverage_totals[label if label in coverage_totals else "other"] += 1
    review_count = sum(item["evidence_status"] != "traceable" for item in campaign_items)
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
            "input_coverage_count": len(coverage),
            "input_priority_count": len(campaign_items),
            "consumed_handoffs": ["coverage", "priorities", "recommendation", "metadata"],
        },
    }


def main():
    input_object = json.load(sys.stdin)
    items = build_campaign_items(input_object.get("priorities", []))
    assigned = assign_message_strategy(items, input_object.get("recommendation", {}))
    result = assemble_campaign_portfolio(
        assigned,
        input_object.get("coverage", []),
        input_object.get("recommendation", {}),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
