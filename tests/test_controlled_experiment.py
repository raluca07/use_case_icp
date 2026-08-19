"""Tests for the controlled-experiment instrument.

`controlled_experiment` produces the published comparison numbers. A defect here
does not crash, it emits a plausible number that reaches the results table, so the
target-selection and scope-splicing behaviour is pinned deliberately. See issue #5.
"""

from __future__ import annotations

import unittest

from use_case_icp.controlled_experiment import choose_target, replace_scope
from use_case_icp.etiq_executor import EtiqExecution
from use_case_icp.records import (
    BoundaryHealth,
    EtiqEvidenceSnapshot,
    EvidenceReviewUnit,
    GeneratedFile,
    GeneratedPipeline,
)

PIPELINE_SOURCE = (
    "import json\n"
    "def collect():\n"
    "    return [1]\n"
    "def rank(values):\n"
    "    return sorted(values)\n"
    "result = rank(collect())\n"
    "print(json.dumps(result))\n"
)


def build_pipeline(source: str = PIPELINE_SOURCE) -> GeneratedPipeline:
    return GeneratedPipeline(
        "pipeline.py",
        [GeneratedFile("pipeline.py", source)],
        [{"function_name": "collect"}, {"function_name": "rank"}],
    )


def build_unit(
    unit_id: str,
    function_name: str,
    *,
    upstream: list[str] | None = None,
) -> EvidenceReviewUnit:
    return EvidenceReviewUnit(
        unit_id=unit_id,
        run_id="run-1",
        function_name=function_name,
        func_stack_prefix=["main", function_name],
        node_refs=[f"node-{function_name}"],
        relationship_refs=[],
        input_relationship_refs=[],
        output_relationship_refs=[],
        helper_prefixes=[],
        boundary_health=BoundaryHealth(
            grouping_mode="function",
            input_count=1,
            output_count=1,
            invocation_count=1,
        ),
        upstream_unit_ids=list(upstream or []),
    )


def build_execution() -> EtiqExecution:
    snapshot = EtiqEvidenceSnapshot(
        snapshot_id="snap-1",
        job_id="job-1",
        run_id="run-1",
        nodes=[],
        relationships=[],
        inventories={},
        scan_errors=[],
    )
    return EtiqExecution(snapshot=snapshot, run_dir=None)  # type: ignore[arg-type]


class ReplaceScopeTests(unittest.TestCase):
    def test_replace_scope_rewrites_only_the_target_function(self) -> None:
        from use_case_icp.repair import source_scope

        pipeline = build_pipeline()
        target = source_scope(pipeline, function_name="collect", mode="boundary")
        changed = replace_scope(
            pipeline,
            target,
            "def collect():\n    return [1, 2]\n",
        )
        content = changed.files[0].content
        self.assertIn("return [1, 2]", content)
        for untouched in (
            "import json\n",
            "def rank(values):\n",
            "    return sorted(values)\n",
            "result = rank(collect())\n",
        ):
            self.assertIn(untouched, content)

    def test_replace_scope_refuses_an_unresolvable_target(self) -> None:
        from use_case_icp.repair import source_scope

        pipeline = build_pipeline()
        target = source_scope(pipeline, function_name="missing_stage", mode="boundary")
        self.assertEqual(target["scope_kind"], "module_fallback")
        # start_line/end_line span the whole file, so the splice would rewrite every
        # line. The scope validator must refuse it rather than accept a whole-file edit.
        with self.assertRaises(ValueError):
            replace_scope(pipeline, target, "print('anything')\n")


class ChooseTargetTests(unittest.TestCase):
    def test_raises_without_a_failed_or_suspect_unit(self) -> None:
        units = [build_unit("unit-collect", "collect")]
        with self.assertRaises(ValueError):
            choose_target(
                mode="semantic_only",
                pipeline=build_pipeline(),
                execution=build_execution(),
                units=units,
                reviews=[{"unit_id": "unit-collect", "decision": "trusted"}],
                previous_targets=[],
            )

    def test_falls_back_to_suspect_units_when_none_failed(self) -> None:
        units = [build_unit("unit-collect", "collect")]
        target = choose_target(
            mode="semantic_only",
            pipeline=build_pipeline(),
            execution=build_execution(),
            units=units,
            reviews=[{"unit_id": "unit-collect", "decision": "suspect"}],
            previous_targets=[],
        )
        self.assertEqual(target["function_name"], "collect")

    def test_baseline_modes_rotate_away_from_a_previously_repaired_function(self) -> None:
        units = [
            build_unit("unit-collect", "collect"),
            build_unit("unit-rank", "rank"),
        ]
        reviews = [
            {"unit_id": "unit-collect", "decision": "failed"},
            {"unit_id": "unit-rank", "decision": "failed"},
        ]
        target = choose_target(
            mode="semantic_only",
            pipeline=build_pipeline(),
            execution=build_execution(),
            units=units,
            reviews=reviews,
            previous_targets=["collect"],
        )
        self.assertEqual(target["function_name"], "rank")

    def test_etiq_modes_pick_the_causal_root_and_baseline_modes_do_not(self) -> None:
        # rank is downstream of collect. The etiq arms filter to causal roots via
        # upstream_unit_ids; the baseline arms have no such step and rotate instead.
        # The arms therefore differ in target selection, not only in review context.
        units = [
            build_unit("unit-collect", "collect"),
            build_unit("unit-rank", "rank", upstream=["unit-collect"]),
        ]
        reviews = [
            {"unit_id": "unit-collect", "decision": "failed"},
            {"unit_id": "unit-rank", "decision": "failed"},
        ]
        kwargs = {
            "pipeline": build_pipeline(),
            "execution": build_execution(),
            "units": units,
            "reviews": reviews,
            "previous_targets": ["collect"],
        }
        etiq = choose_target(mode="etiq_selected", **kwargs)
        baseline = choose_target(mode="semantic_only", **kwargs)
        self.assertEqual(etiq["function_name"], "collect")
        self.assertEqual(baseline["function_name"], "rank")


if __name__ == "__main__":
    unittest.main()
