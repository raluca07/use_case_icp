"""Build the static, read-only presentation demo from recorded Attempt 053 data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_ROOT = ROOT / "outputs/fault-experiments-v2-2-n10/attempt-053"
TRIAL_ID = "trial-185576df477d708c"
OUTPUT = ROOT / "docs/presentation/demo/demo-data.js"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_demo_data() -> dict[str, Any]:
    terminal = read_json(ATTEMPT_ROOT / "terminal-state.json")
    analysis = read_json(ATTEMPT_ROOT / "analysis/summary.json")
    review = read_json(ATTEMPT_ROOT / "reviews" / f"{TRIAL_ID}.json")
    expansion, inspection = review["operation_events"]

    labels = {
        "P01": "Base",
        "P02": "Graph",
        "P03": "Graph + semantics",
        "P04": "Adaptive graph",
        "P05": "Adaptive + semantics",
        "P06": "Equal-call reconsideration",
    }
    conditions = []
    for cell_id, label in labels.items():
        summary = analysis["cell_summaries"][cell_id]
        conditions.append(
            {
                "cell_id": cell_id,
                "label": label,
                "fault_detection": summary["fault_detection"],
                "exact_localisation": summary["exact_function_localisation"],
                "false_positives": summary["control_false_positives"],
                "reviews": summary["reviews"],
                "provider_calls": summary["provider_calls"],
            }
        )

    return {
        "schema_version": "readonly-demo-1",
        "attempt": "053",
        "terminal": {
            "status": terminal["status"],
            "instances": terminal["instance_count"],
            "captures": terminal["fresh_job_capture_count"],
            "packages": terminal["package_count"],
            "reviews": terminal["review_count"],
            "provider_calls": terminal["actual_scientific_provider_calls"],
            "repairs": terminal["repair_trace_count"],
        },
        "conditions": conditions,
        "jobs": [
            {"id": "job_1", "name": "Market evidence", "summary": "Select, deduplicate, and reliability-weight observations."},
            {"id": "job_2", "name": "Opportunity priority", "summary": "Join commercial context, score, and rank opportunities."},
            {"id": "job_3", "name": "Campaign allocation", "summary": "Aggregate candidates, score campaigns, and allocate budget."},
            {"id": "job_4", "name": "Activation schedule", "summary": "Join capacity, choose windows, and produce the final schedule."},
        ],
        "walkthrough": {
            "trial": review["controller_trial"],
            "designation": review["designation"],
            "initial_receipt": review["initial_receipt"],
            "expansion": {
                "job_id": expansion["job_id"],
                "execution_group_id": expansion["execution_group_id"],
                "function": expansion["captured_function_label"],
                "nodes_added": len(expansion["nodes_added"]),
                "relationships_added": len(expansion["relationships_added"]),
                "artifacts_added": len(expansion["newly_disclosed_artifact_refs"]),
                "evidence_bytes_added": expansion["evidence_bytes_added"],
            },
            "inspection": {
                "artifact_ref": inspection["artifact_ref"],
                "native_node_ref": inspection["native_node_ref"],
                "columns": inspection["result"]["columns"],
                "rows": inspection["result"]["content"],
                "returned_rows": inspection["result"]["returned_rows"],
                "bytes": inspection["result"]["artifact_bytes_returned"],
            },
            "terminal_receipt": review["terminal_receipt"],
            "outcome": {
                "fault_detected": review["fault_detected"],
                "correct_job_attribution": review["correct_job_attribution"],
                "exact_function_localisation": review["exact_function_localisation"],
                "false_positive": review["false_positive"],
                "answer_changed": review["answer_changed"],
                "truth_job": review["truth_job"],
                "truth_function": review["truth_function"],
                "selected_group_contained_truth_state": review["selected_group_contained_truth_state"],
                "selected_artifact_was_truth_state": review["selected_artifact_was_truth_state"],
            },
            "usage": {
                "calls": len(review["call_records"]),
                "input_tokens": review["usage"]["cumulative_actual_input_tokens"],
                "cached_input_tokens": review["usage"]["cumulative_actual_cached_input_tokens"],
                "output_tokens": review["usage"]["cumulative_actual_output_tokens"],
            },
        },
        "sources": {
            "review": f"../../../outputs/fault-experiments-v2-2-n10/attempt-053/reviews/{TRIAL_ID}.json",
            "terminal": "../../../outputs/fault-experiments-v2-2-n10/attempt-053/terminal-state.json",
            "analysis": "../../../outputs/fault-experiments-v2-2-n10/attempt-053/analysis/summary.json",
            "experiment_diagram": "../diagrams/four_job_experiment_architecture.svg",
            "harness_diagram": "../diagrams/graph_harness_internals.svg",
        },
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(build_demo_data(), ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_text(f"window.READ_ONLY_DEMO_DATA={data};\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
