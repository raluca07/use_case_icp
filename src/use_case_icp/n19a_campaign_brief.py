import json
import sys

import pandas as pd


def build_campaign_brief(priorities, recommendation):
    top_need = recommendation.get("top_need", "")
    decision = recommendation.get("decision", "")
    supporting_points = []
    priorities_df = pd.DataFrame(priorities).head(3)
    for _, priority in priorities_df.iterrows():
        priority = priority.to_dict()
        supporting_points.append({
            "priority_rank": priority.get("priority_rank"),
            "record_id": priority.get("record_id"),
            "need": priority.get("need"),
            "capability_id": priority.get("capability_id"),
            "coverage": priority.get("coverage"),
            "unsupported": priority.get("unsupported"),
        })
    return {
        "campaign_brief": {
            "audience_need": top_need,
            "recommended_action": decision,
            "message_strategy": (
                "lead_with_unmet_need"
                if decision == "prioritize"
                else "reinforce_supported_need"
            ),
            "primary_message": f"Focus campaign on: {top_need}",
            "supporting_points": supporting_points,
        },
        "metadata": {
            "supporting_point_count": len(supporting_points),
            "consumed_handoffs": ["priorities", "recommendation"],
        },
    }


def main():
    input_object = json.load(sys.stdin)
    result = build_campaign_brief(
        input_object.get("priorities", []),
        input_object.get("recommendation", {}),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
