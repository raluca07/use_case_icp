from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from use_case_icp.__main__ import build_parser
from use_case_icp.codex_runner import CodexResult, CodexRunner, extract_usage
from use_case_icp.dashboard import (
    _graph_svg,
    _lineage_interaction_script,
    experiment_page_body,
)
from use_case_icp.etiq_executor import EtiqExecutor
from use_case_icp.etiq_graph import value_preview
from use_case_icp.repair import (
    repair_diff,
    select_repair_target,
    source_scope,
    validate_repair_scope,
)
from use_case_icp.workflow import WorkflowRunner, repair_metrics
from use_case_icp.records import (
    AgentRequest,
    CodexContextManifest,
    CodexUsageRecord,
    ContextArtifact,
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    GeneratedFile,
    GeneratedPipeline,
    ReviewDecision,
    ReviewSection,
    RootJobState,
    TrustAnnotation,
    TrustLevel,
    jsonable,
    new_id,
    stable_hash,
)
from use_case_icp.review import (
    build_review_sections,
    build_review_units,
    retrace_node_refs,
    trusted_frontier,
    validate_expansion,
    validate_review,
    visible_evidence,
)
from use_case_icp.job_store import JobStore
from use_case_icp.review_experiment import (
    EXPERIMENT_MODES,
    history_artifacts,
    summarize_experiment,
)


class FakeCodeNode:
    def __init__(self, source: str) -> None:
        self.source = source

    def as_string(self) -> str:
        return self.source

    def scope(self) -> object:
        return self


class FakeFunctionMapping:
    def __init__(self, function_id: str, arguments: list[str], name: str) -> None:
        self.function_id = function_id
        self.function_arguments = set(arguments)
        self.function_name = name

    def metadata_json(self) -> dict[str, object]:
        return {
            "function_id": self.function_id,
            "dataset_function_arguments": sorted(self.function_arguments),
            "function_name": self.function_name,
        }


class FakeState:
    def __init__(
        self,
        state_id: str,
        name: str,
        stack: list[str],
        *,
        parents: list[str] | None = None,
        line: int = 1,
    ) -> None:
        self.state_id = state_id
        self.names = [name]
        self.func_stack = stack
        self.parent_ids = list(parents or [])
        self.parent: set[FakeState] = set()
        self.children: set[FakeState] = set()
        self.parent_func_mapping = FakeFunctionMapping(f"f-{state_id}", self.parent_ids, name)
        self.line_no = line
        self.value = {"name": name}
        self.node = FakeCodeNode(name)


class FakeResult:
    def __init__(self) -> None:
        self.states: list[FakeState] = [
            FakeState("s0", "source", ["main"], line=1),
            FakeState("s1", "collected", ["main", "collect,c1"], parents=["s0"], line=2),
            FakeState("s2", "raw", ["main"], parents=["s1"], line=3),
            FakeState("s3", "ranked", ["main", "rank,c1"], parents=["s2"], line=4),
            FakeState("s4", "result", ["main"], parents=["s3"], line=5),
        ]
        by_id = {state.state_id: state for state in self.states}
        for state in self.states:
            state.parent = {by_id[parent_id] for parent_id in state.parent_ids}
            for parent in state.parent:
                parent.children.add(state)
        self.scan_errors: list[str] = []

    def list_dataframes(self) -> list[str]:
        return ["source", "result"]

    def get_dataframes(self) -> list[FakeState]:
        return [self.states[0], self.states[4]]

    def list_models(self) -> list[str]:
        return []

    def get_models(self) -> list[FakeState]:
        return []

    def list_agents(self) -> list[str]:
        return []

    def get_agent_states(self) -> list[FakeState]:
        return []

    def get_unstructured_states(self) -> list[FakeState]:
        return self.states[1:4]


class FakeScanner:
    def scan_code(self, *, code_str: str) -> FakeResult:
        if not code_str:
            raise AssertionError("source required")
        exec(compile(code_str, "pipeline.py", "exec"), {"__name__": "__main__"})
        return FakeResult()


class FakeUnstructuredResult(FakeResult):
    def list_dataframes(self) -> list[str]:
        return []

    def get_dataframes(self) -> list[FakeState]:
        return []

    def get_unstructured_states(self) -> list[FakeState]:
        return self.states


class FakeUnstructuredScanner:
    def scan_code(self, *, code_str: str) -> FakeUnstructuredResult:
        if not code_str:
            raise AssertionError("source required")
        return FakeUnstructuredResult()


class CoreTests(unittest.TestCase):
    def test_codex_schemas_require_every_declared_property(self) -> None:
        def check(value: object) -> None:
            if isinstance(value, dict):
                if value.get("type") == "object" and value.get("additionalProperties") is False:
                    self.assertEqual(
                        set(value.get("properties", {})),
                        set(value.get("required", [])),
                    )
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        schema_root = Path(__file__).resolve().parents[1] / "schemas"
        for schema_path in schema_root.glob("*.json"):
            check(json.loads(schema_path.read_text(encoding="utf-8")))

    def test_cli_defaults_to_gpt_5_5_and_rejects_newer_job_models(self) -> None:
        args = build_parser().parse_args(["run", "--product", "p", "--audience", "a"])
        self.assertEqual(args.model, "gpt-5.5")
        self.assertEqual(args.max_authoring_retries, 2)
        self.assertEqual(args.max_repairs, 6)
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["run", "--product", "p", "--audience", "a", "--model", "gpt-5.6-sol"]
            )
        compare = build_parser().parse_args(
            ["compare-review", "job-1", "--baseline-run", "run-1"]
        )
        self.assertEqual(compare.model, "gpt-5.5")
        self.assertEqual(compare.repetitions, 1)
        compare_with_history = build_parser().parse_args(
            [
                "compare-review",
                "job-2",
                "--baseline-run",
                "run-2",
                "--history-job",
                "job-1",
            ]
        )
        self.assertEqual(compare_with_history.history_jobs, ["job-1"])

    def test_generated_pipeline_rejects_escape(self) -> None:
        pipeline = GeneratedPipeline(entry_file="../pipeline.py", files=[GeneratedFile("../pipeline.py", "x=1")])
        with self.assertRaises(ValueError):
            pipeline.validate()

    def test_usage_parser_and_incomplete_rollup(self) -> None:
        usage = extract_usage(
            [{"type": "turn.completed", "usage": {"input_tokens": 17, "output_tokens": 4}}],
            "inv-1",
            "segment",
            "succeeded",
        )
        self.assertEqual(usage.total_tokens, 21)
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs")
            request = AgentRequest("product", "audience")
            store.initialize_job(request, RootJobState("job-1"))
            first = store.invocation_dir("job-1", "inv-1")
            store.write_json(first / "usage.json", usage)
            second = store.invocation_dir("job-1", "inv-2")
            store.write_json(
                second / "usage.json",
                CodexUsageRecord("inv-2", "review", "failed", "unavailable"),
            )
            summary = store.update_usage_summary("job-1")
            self.assertFalse(summary["complete"])
            self.assertEqual(summary["totals"]["input_tokens"], 17)
            self.assertEqual(summary["totals"]["unavailable"], 1)

    def test_etiq_capture_sections_and_trust(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs")
            request = AgentRequest("product", "audience")
            store.initialize_job(request, RootJobState("job-1"))
            executor = EtiqExecutor(store, scanner_factory=FakeScanner)
            pipeline = GeneratedPipeline("pipeline.py", [GeneratedFile("pipeline.py", "result = 1")])
            execution = executor.execute(
                job_id="job-1",
                segment_id="segment-1",
                stage="market_demand",
                run_id="run-1",
                pipeline=pipeline,
            )
            self.assertTrue(execution.reviewable)
            self.assertEqual(len(execution.snapshot.nodes), 10)
            self.assertEqual(len(execution.snapshot.relationships), 13)
            self.assertEqual(
                execution.snapshot.inventories["captured_state_counts"],
                {
                    "get_dataframes": 2,
                    "get_models": 0,
                    "get_agent_states": 0,
                    "get_unstructured_states": 3,
                },
            )
            self.assertEqual(
                {item.relationship_type for item in execution.snapshot.relationships},
                {"function_argument", "function_result", "state_parent"},
            )

            units = build_review_units(execution.snapshot)
            self.assertEqual([unit.function_name for unit in units], ["collect", "rank"])
            self.assertFalse(any(unit.boundary_health.degraded for unit in units))
            sections = build_review_sections(units, section_size=1, overlap=1)
            self.assertEqual(len(sections), 2)
            self.assertIn(units[0].unit_id, sections[1].context_unit_ids)

            for section in sections:
                unit = next(item for item in units if item.unit_id == section.assigned_unit_ids[0])
                decision = ReviewDecision(
                    unit_id=unit.unit_id,
                    decision="trusted",
                    decision_reason="Captured input and output boundaries satisfy the expected transformation.",
                    evidence_refs=["stages/segment-1/market_demand/runs/run-1/etiq-nodes.json"],
                    trust_level=TrustLevel.REUSE,
                    criteria_outcomes=[{"criterion": "output exists", "verdict": "met", "evidence_refs": ["etiq-nodes"]}],
                    boundary_health_acknowledged=True,
                )
                receipt, annotations = validate_review(
                    review_job_id="job-1",
                    section=section,
                    units=units,
                    decisions=[decision],
                    allowed_evidence_refs={
                        "stages/segment-1/market_demand/runs/run-1/etiq-nodes.json",
                        "etiq-nodes",
                    },
                    receipt_ref=f"receipts/run-1-{section.section_id}.json",
                )
                self.assertEqual(receipt.result, "passed")
                self.assertEqual([item.unit_id for item in annotations], [unit.unit_id])

    def test_nested_review_units_split_recursively_and_sections_obey_evidence_limits(self) -> None:
        def node(ref: str, stack: list[str]) -> EtiqNodeRecord:
            return EtiqNodeRecord(ref, ref, [ref], 1, "state", "dict", stack, None, None, {})

        nodes = [
            node("root", ["main"]),
            node("runner", ["main", "run_pipeline,r1"]),
            node("stage-a", ["main", "run_pipeline,r1", "stage_a,a1"]),
            node("helper-a1", ["main", "run_pipeline,r1", "stage_a,a1", "helper_a,h1"]),
            node("helper-a2", ["main", "run_pipeline,r1", "stage_a,a1", "helper_b,h1"]),
            node("stage-b", ["main", "run_pipeline,r1", "stage_b,b1"]),
        ]
        edges = [
            ("root", "runner"),
            ("runner", "stage-a"),
            ("stage-a", "helper-a1"),
            ("helper-a1", "stage-a"),
            ("stage-a", "helper-a2"),
            ("helper-a2", "stage-a"),
            ("stage-a", "stage-b"),
        ]
        relationships = [
            EtiqRelationshipRecord(f"rel-{index}", source, target, "state_parent", "source_to_target", {})
            for index, (source, target) in enumerate(edges)
        ]
        snapshot = EtiqEvidenceSnapshot(
            "snapshot-1",
            "job-1",
            "run-1",
            nodes,
            relationships,
            {},
            [],
        )
        units = build_review_units(snapshot, max_descendant_frames=1)
        self.assertEqual(
            {unit.function_name for unit in units},
            {"helper_a", "helper_b", "stage_b"},
        )
        self.assertTrue(
            any(
                "parent_exceeded_limits" in unit.nesting_summary["selection_reason"]
                for unit in units
            )
        )
        sections = build_review_sections(
            units,
            section_size=8,
            overlap=1,
            max_nodes=2,
            max_relationships=6,
            max_helpers=2,
        )
        self.assertGreaterEqual(len(sections), 2)
        unit_by_id = {unit.unit_id: unit for unit in units}
        for section in sections:
            assigned_nodes = {
                ref
                for unit_id in section.assigned_unit_ids
                for ref in unit_by_id[unit_id].node_refs
            }
            self.assertLessEqual(len(assigned_nodes), 2)

    def test_declared_review_boundary_stays_collapsed_until_expanded(self) -> None:
        def node(ref: str, stack: list[str]) -> EtiqNodeRecord:
            return EtiqNodeRecord(ref, ref, [ref], 1, "state", "dict", stack, None, None, {})

        nodes = [
            node("before", ["main"]),
            node("stage", ["main", "stage_a,a1"]),
            node("helper", ["main", "stage_a,a1", "helper,h1"]),
            node("after", ["main"]),
        ]
        relationships = [
            EtiqRelationshipRecord("r1", "before", "stage", "state_parent", "flow", {}),
            EtiqRelationshipRecord("r2", "stage", "helper", "state_parent", "flow", {}),
            EtiqRelationshipRecord("r3", "helper", "stage", "state_parent", "flow", {}),
            EtiqRelationshipRecord("r4", "stage", "after", "state_parent", "flow", {}),
        ]
        snapshot = EtiqEvidenceSnapshot(
            "snapshot", "job", "run", nodes, relationships, {}, []
        )
        units = build_review_units(
            snapshot,
            declared_boundaries=[{"function_name": "stage_a"}],
        )
        self.assertEqual([unit.function_name for unit in units], ["stage_a"])
        initial = visible_evidence(units[0], snapshot)
        self.assertNotIn("helper", initial["node_refs"])
        prefix = validate_expansion(
            units[0],
            ["main", "stage_a,a1", "helper,h1"],
            [],
        )
        expanded = visible_evidence(units[0], snapshot, [prefix])
        self.assertIn("helper", expanded["node_refs"])

    def test_repeated_capture_nodes_fit_the_declared_review_boundary(self) -> None:
        nodes = [
            EtiqNodeRecord(
                f"node-{index}",
                f"node-{index}",
                [f"value-{index}"],
                index,
                "state",
                "dict",
                ["main", "extract_evidence,e1", "for row in sources,#10"],
                None,
                None,
                {},
            )
            for index in range(120)
        ]
        relationships = [
            EtiqRelationshipRecord(
                f"rel-{index}",
                f"node-{index}",
                f"node-{index + 1}",
                "state_parent",
                "source_to_target",
                {},
            )
            for index in range(119)
        ]
        snapshot = EtiqEvidenceSnapshot(
            "snapshot-repeated",
            "job-1",
            "run-repeated",
            nodes,
            relationships,
            {},
            [],
        )
        units = build_review_units(
            snapshot,
            declared_boundaries=[{"function_name": "extract_evidence"}],
        )
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].function_name, "extract_evidence")
        self.assertEqual(len(units[0].node_refs), 120)
        sections = build_review_sections(units)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].construction_summary["context_node_count"], 120)

    def test_value_preview_redacts_and_bounds_values(self) -> None:
        preview, truncated = value_preview(
            {"api_token": "do-not-store", "items": list(range(100))}
        )
        self.assertEqual(preview["api_token"], "[REDACTED]")
        self.assertEqual(len(preview["items"]), 20)
        self.assertTrue(truncated)

    def test_lineage_svg_renders_captured_relationships(self) -> None:
        svg = _graph_svg(
            [
                {"node_ref": "a", "names": ["a"], "state_type": "state", "func_stack": ["main"]},
                {"node_ref": "b", "names": ["b"], "state_type": "state", "func_stack": ["main", "stage"]},
            ],
            [
                {
                    "source_ref": "a",
                    "target_ref": "b",
                    "relationship_type": "state_parent",
                }
            ],
            [],
            {},
        )
        self.assertIn("<line", svg)
        self.assertIn("state_parent", svg)
        self.assertIn("class='lineage-node", svg)
        self.assertIn("data-node-ref='a'", svg)
        self.assertIn("class='captured-edge'", svg)

    def test_lineage_details_are_scoped_to_clicked_node(self) -> None:
        script = _lineage_interaction_script(
            {
                "nodes": [
                    {
                        "node_ref": "node-a",
                        "names": ["artifact"],
                        "state_type": "DataframeState",
                        "value_preview": {"rows": 1},
                    }
                ],
                "relationships": [
                    {
                        "relationship_ref": "relationship-a",
                        "source_ref": "node-a",
                        "target_ref": "node-b",
                        "relationship_type": "function_result",
                    }
                ],
                "units": [{"unit_id": "unit-a", "node_refs": ["node-a"]}],
                "annotations": [
                    {
                        "annotation_id": "annotation-a",
                        "unit_id": "unit-a",
                        "evidence_refs": ["node-a"],
                    }
                ],
                "statuses": {"unit-a": "failed"},
            }
        )
        self.assertIn("showNodeDetails", script)
        self.assertIn("Captured relationships", script)
        self.assertIn("Derived annotations", script)
        self.assertIn("lineageData.relationships.filter", script)

    def test_trusted_frontier_and_retrace_use_existing_edges(self) -> None:
        execution_nodes = [
            EtiqNodeRecord(ref, ref, [ref], 1, "state", "dict", ["main", ref], None, None, {})
            for ref in ("a", "b", "c")
        ]
        snapshot = EtiqEvidenceSnapshot(
            "snapshot",
            "job",
            "run",
            execution_nodes,
            [
                EtiqRelationshipRecord("ab", "a", "b", "state_parent", "flow", {}),
                EtiqRelationshipRecord("bc", "b", "c", "state_parent", "flow", {}),
            ],
            {},
            [],
        )
        units = build_review_units(snapshot)
        unit_by_name = {unit.function_name: unit for unit in units}
        annotations = [
            TrustAnnotation("t-a", unit_by_name["a"].unit_id, str(TrustLevel.REUSE), "codex", "job", "run", "r", []),
            TrustAnnotation("t-b", unit_by_name["b"].unit_id, str(TrustLevel.REUSE), "codex", "job", "run", "r", []),
        ]
        frontier = trusted_frontier(units, annotations)
        self.assertEqual(frontier["frontier_unit_ids"], [unit_by_name["b"].unit_id])
        self.assertEqual(retrace_node_refs(snapshot, ["c"]), ["c", "b", "a"])

    def test_non_pipeline_unit_does_not_block_reusable_frontier(self) -> None:
        nodes = [
            EtiqNodeRecord("a", "a", ["a"], 1, "state", "dict", ["main", "helper,a"], None, None, {}),
            EtiqNodeRecord("b", "b", ["b"], 2, "state", "dict", ["main", "stage,b"], None, None, {}),
        ]
        snapshot = EtiqEvidenceSnapshot(
            "snapshot",
            "job",
            "run",
            nodes,
            [EtiqRelationshipRecord("ab", "a", "b", "state_parent", "flow", {})],
            {},
            [],
        )
        units = build_review_units(snapshot)
        unit_by_name = {unit.function_name: unit for unit in units}
        section = ReviewSection(
            "section-001",
            1,
            [unit_by_name["helper"].unit_id, unit_by_name["stage"].unit_id],
            [unit_by_name["helper"].unit_id, unit_by_name["stage"].unit_id],
            0,
            1,
            section_input_hash="hash",
        )
        receipt, annotations = validate_review(
            review_job_id="job",
            section=section,
            units=units,
            decisions=[
                ReviewDecision(
                    unit_by_name["helper"].unit_id,
                    "not_pipeline_step",
                    "plumbing",
                    [],
                ),
                ReviewDecision(
                    unit_by_name["stage"].unit_id,
                    "trusted",
                    "valid stage",
                    ["b"],
                    trust_level=TrustLevel.REUSE,
                    criteria_outcomes=[
                        {"criterion": "valid", "verdict": "met", "evidence_refs": ["b"]}
                    ],
                    boundary_health_acknowledged=True,
                ),
            ],
            allowed_evidence_refs={"a", "b"},
            receipt_ref="receipt.json",
        )
        self.assertEqual(receipt.result, "passed")
        self.assertEqual(
            receipt.non_pipeline_unit_ids,
            [unit_by_name["helper"].unit_id],
        )
        frontier = trusted_frontier(units, annotations)
        self.assertEqual(
            frontier["frontier_unit_ids"],
            [unit_by_name["stage"].unit_id],
        )
        self.assertEqual(
            frontier["non_pipeline_unit_ids"],
            [unit_by_name["helper"].unit_id],
        )

    def test_review_experiment_compares_issue_overlap_and_resolution(self) -> None:
        records = []
        for run_label, issues in (("baseline", ["stage"]), ("repaired", [])):
            for mode in EXPERIMENT_MODES:
                records.append(
                    {
                        "run_label": run_label,
                        "mode": mode,
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "package_chars": 100,
                        "issue_keys": issues,
                    }
                )
        summary = summarize_experiment(records)
        self.assertEqual(
            summary["arms"]["baseline:semantic_only"]["issue_recall_vs_selected"],
            1.0,
        )
        self.assertEqual(summary["resolved_issue_keys"]["etiq_selected"], ["stage"])

    def test_review_experiment_reports_consensus_and_verified_quality(self) -> None:
        records = []
        for mode in EXPERIMENT_MODES:
            issues = ["discover", "extract", "synthesize"]
            if mode in {"semantic_only", "etiq_selected"}:
                issues.append("retrieve")
            records.append(
                {
                    "run_label": "baseline",
                    "mode": mode,
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "package_chars": 100,
                    "issue_keys": issues,
                }
            )
        assessment = {
            "core_issue_keys": ["discover", "extract", "synthesize"],
            "arms": {
                "baseline:semantic_only": {
                    "misattributed_issue_keys": ["retrieve"],
                    "secondary_findings": ["source failure propagation"],
                },
                "baseline:etiq_selected": {
                    "misattributed_issue_keys": ["retrieve"],
                },
            },
        }
        summary = summarize_experiment(records, assessment)
        self.assertEqual(
            summary["consensus_by_run"]["baseline"]["consensus_core_issue_keys"],
            ["discover", "extract", "synthesize"],
        )
        self.assertEqual(
            summary["consensus_by_run"]["baseline"]["disputed_issue_keys"],
            ["retrieve"],
        )
        semantic = summary["arms"]["baseline:semantic_only"]
        self.assertEqual(semantic["verified_core_recall"], 1.0)
        self.assertEqual(semantic["verified_issue_precision"], 0.75)
        self.assertEqual(semantic["misattributed_issue_count"], 1)
        self.assertEqual(
            semantic["secondary_findings"],
            ["source failure propagation"],
        )

    def test_review_experiment_dashboard_shows_planned_arms(self) -> None:
        body = experiment_page_body(
            "job-1",
            "comparison-1",
            {
                "execute": False,
                "model": "gpt-5.5",
                "repetitions": 1,
                "summary": {
                    "arms": {
                        f"baseline:{mode}": {
                            "run_label": "baseline",
                            "mode": mode,
                            "average_package_chars": package_chars,
                            "average_input_tokens": 0,
                            "issue_count": 0,
                            "issue_recall_vs_selected": None,
                        }
                        for mode, package_chars in (
                            ("semantic_only", 100),
                            ("history_full", 500),
                            ("etiq_full", 300),
                            ("etiq_selected", 150),
                        )
                    },
                    "resolved_issue_keys": {},
                },
            },
        )
        self.assertIn("planned only", body)
        self.assertIn("semantic_only", body)
        self.assertIn("history_full", body)
        self.assertIn("etiq_full", body)
        self.assertIn("etiq_selected", body)
        self.assertIn("Verified core recall", body)
        self.assertIn("no source-verified assessment", body)
        self.assertIn("Node means an Etiq-captured runtime state", body)

    def test_full_history_includes_semantic_artifacts_but_not_etiq_or_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs")
            job_dir = store.job_dir("job-1")
            run_dir = job_dir / "stages" / "segment-1" / "market_demand" / "runs" / "run-1"
            pipeline_dir = run_dir / "pipeline"
            pipeline_dir.mkdir(parents=True)
            store.write_json(job_dir / "request.json", {"product": "product"})
            store.write_json(job_dir / "segments.json", {"segments": ["segment"]})
            store.write_json(run_dir / "pipeline-input.json", {"audience": "audience"})
            store.write_json(run_dir / "semantic-result.json", {"needs": ["need"]})
            store.write_json(run_dir / "repair-diff.json", {"diff": "future repair"})
            store.write_json(run_dir / "etiq-nodes.json", [{"node_ref": "secret"}])
            store.write_json(run_dir / "review-receipt.json", {"decision": "failed"})
            (pipeline_dir / "pipeline.py").write_text("result = 1\n", encoding="utf-8")
            future_pipeline = (
                job_dir
                / "stages"
                / "segment-1"
                / "market_demand"
                / "runs"
                / "run-2"
                / "pipeline"
                / "pipeline.py"
            )
            future_pipeline.parent.mkdir(parents=True)
            future_pipeline.write_text("result = 2\n", encoding="utf-8")

            artifacts = history_artifacts(store, ["job-1"])
            refs = {artifact["ref"] for artifact in artifacts}
            self.assertIn("history:job-1:request.json", refs)
            self.assertIn(
                "history:job-1:stages/segment-1/market_demand/runs/run-1/pipeline/pipeline.py",
                refs,
            )
            self.assertIn(
                "history:job-1:stages/segment-1/market_demand/runs/run-1/pipeline-input.json",
                refs,
            )
            self.assertFalse(any("etiq-" in ref for ref in refs))
            self.assertFalse(any("review-" in ref for ref in refs))

            visible = history_artifacts(
                store,
                ["job-1"],
                target_job_id="job-1",
                target_run_dir=run_dir,
            )
            visible_refs = {artifact["ref"] for artifact in visible}
            self.assertFalse(any("/run-2/" in ref for ref in visible_refs))
            self.assertFalse(any(ref.endswith("repair-diff.json") for ref in visible_refs))

    def test_repair_scope_accepts_only_selected_function(self) -> None:
        original = GeneratedPipeline(
            "pipeline.py",
            [
                GeneratedFile(
                    "pipeline.py",
                    "def stage():\n    value = 1\n    return value\n\nresult = stage()\n",
                )
            ],
            [{"function_name": "stage"}],
        )
        target = source_scope(original, function_name="stage", mode="boundary")
        replacement = GeneratedPipeline(
            "pipeline.py",
            [
                GeneratedFile(
                    "pipeline.py",
                    "def stage():\n    value = 2\n    return value\n\nresult = stage()\n",
                )
            ],
            [{"function_name": "stage"}],
        )
        validate_repair_scope(original, replacement, target)
        diff = repair_diff(original, replacement)
        self.assertIn("-    value = 1", diff)
        self.assertIn("+    value = 2", diff)
        outside = GeneratedPipeline(
            "pipeline.py",
            [
                GeneratedFile(
                    "pipeline.py",
                    "def stage():\n    value = 2\n    return value\n\nresult = stage() + 1\n",
                )
            ],
            [{"function_name": "stage"}],
        )
        with self.assertRaises(ValueError):
            validate_repair_scope(original, outside, target)

        node_target = source_scope(
            original,
            function_name="stage",
            mode="faulty_node",
            line_no=2,
        )
        self.assertEqual(node_target["effective_mode"], "faulty_node")
        validate_repair_scope(original, replacement, node_target)
        changed_return = GeneratedPipeline(
            "pipeline.py",
            [
                GeneratedFile(
                    "pipeline.py",
                    "def stage():\n    value = 1\n    return value + 1\n\nresult = stage()\n",
                )
            ],
            [{"function_name": "stage"}],
        )
        with self.assertRaises(ValueError):
            validate_repair_scope(original, changed_return, node_target)

    def test_repair_target_rotates_to_the_least_repaired_failed_function(self) -> None:
        pipeline = GeneratedPipeline(
            "pipeline.py",
            [
                GeneratedFile(
                    "pipeline.py",
                    "def collect():\n    return 1\n\ndef extract():\n    return 2\n",
                )
            ],
            [{"function_name": "collect"}, {"function_name": "extract"}],
        )
        nodes = [
            EtiqNodeRecord(
                node_ref="node-collect",
                raw_id="collect",
                names=["collect"],
                line_no=1,
                state_type="FunctionMapping",
                value_type=None,
                func_stack=["main", "collect,1"],
                source="def collect():",
                scope_type="function",
                raw_metadata={},
            ),
            EtiqNodeRecord(
                node_ref="node-extract",
                raw_id="extract",
                names=["extract"],
                line_no=4,
                state_type="FunctionMapping",
                value_type=None,
                func_stack=["main", "extract,1"],
                source="def extract():",
                scope_type="function",
                raw_metadata={},
            ),
        ]
        snapshot = EtiqEvidenceSnapshot(
            "snapshot-1",
            "job-1",
            "run-1",
            nodes,
            [],
            {},
            [],
        )
        context = {
            "units": [
                {
                    "unit_id": "unit-collect",
                    "function_name": "collect",
                    "node_refs": ["node-collect"],
                },
                {
                    "unit_id": "unit-extract",
                    "function_name": "extract",
                    "node_refs": ["node-extract"],
                },
            ],
            "receipts": [
                {
                    "failed_or_suspect_unit_ids": [
                        "unit-collect",
                        "unit-extract",
                    ],
                    "suspect_node_refs": ["node-collect", "node-extract"],
                }
            ],
        }
        target = select_repair_target(
            "boundary",
            pipeline=pipeline,
            snapshot=snapshot,
            review_context=context,
            previous_target_function_names=["collect"],
        )
        self.assertEqual(target["function_name"], "extract")
        self.assertEqual(target["suspect_node_ref"], "node-extract")

    def test_repair_metrics_separate_accepted_and_effective_repairs(self) -> None:
        metrics = repair_metrics(
            [
                {"target_function": "collect", "status": "target_still_flagged"},
                {"target_function": "extract", "status": "target_resolved"},
                {"target_function": "synthesize", "status": "pending"},
            ],
            repair_budget=6,
            initial_issue_functions=["collect", "extract", "synthesize"],
            current_issue_functions=["collect", "synthesize"],
            current_run_id="run-3",
        )
        self.assertEqual(metrics["accepted_repair_count"], 3)
        self.assertEqual(metrics["evaluated_repair_count"], 2)
        self.assertEqual(metrics["effective_repair_count"], 1)
        self.assertEqual(metrics["repair_effectiveness_rate"], 0.5)
        self.assertEqual(metrics["resolved_initial_issue_functions"], ["extract"])

    def test_etiq_unstructured_states_are_evidence_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs")
            request = AgentRequest("product", "audience")
            store.initialize_job(request, RootJobState("job-unstructured"))
            execution = EtiqExecutor(store, scanner_factory=FakeUnstructuredScanner).execute(
                job_id="job-unstructured",
                segment_id="segment-1",
                stage="market_demand",
                run_id="run-unstructured",
                pipeline=GeneratedPipeline(
                    "pipeline.py",
                    [GeneratedFile("pipeline.py", "result = {'captured': True}")],
                ),
            )

            self.assertTrue(execution.reviewable)
            self.assertEqual(
                execution.snapshot.inventories["captured_state_counts"],
                {
                    "get_dataframes": 0,
                    "get_models": 0,
                    "get_agent_states": 0,
                    "get_unstructured_states": 5,
                },
            )
            self.assertEqual(len(execution.snapshot.nodes), 10)

    def test_etiq_execution_persists_compilation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs")
            store.initialize_job(
                AgentRequest("product", "audience"),
                RootJobState("job-compile-failure"),
            )
            executor = EtiqExecutor(store, scanner_factory=FakeScanner)
            with self.assertRaises(SyntaxError):
                executor.execute(
                    job_id="job-compile-failure",
                    segment_id="segment-1",
                    stage="market_demand",
                    run_id="run-failed",
                    pipeline=GeneratedPipeline(
                        "pipeline.py",
                        [GeneratedFile("pipeline.py", "result =\n")],
                    ),
                )

            run_dir = store.stage_run_dir(
                "job-compile-failure",
                "segment-1",
                "market_demand",
                "run-failed",
            )
            failure = store.read_json(run_dir / "execution-error.json")
            self.assertEqual(failure["error_type"], "SyntaxError")
            self.assertTrue((run_dir / "pipeline" / "pipeline.py").exists())
            self.assertTrue((run_dir / "pipeline-stdout.log").exists())


class FakeCodex:
    def __init__(
        self,
        store: JobStore,
        *,
        coverage_sufficient: bool = True,
        fail_first_review: bool = False,
        fail_first_pipeline: bool = False,
        invalid_first_bundle: bool = False,
    ) -> None:
        self.store = store
        self.coverage_sufficient = coverage_sufficient
        self.fail_first_review = fail_first_review
        self.fail_first_pipeline = fail_first_pipeline
        self.invalid_first_bundle = invalid_first_bundle
        self.review_count = 0
        self.invocations: list[str] = []
        self.purposes: list[str] = []

    def run(self, **kwargs: object) -> CodexResult:
        job_id = str(kwargs["job_id"])
        purpose = str(kwargs["purpose"])
        invocation_id = new_id("fake-inv")
        self.invocations.append(invocation_id)
        self.purposes.append(purpose)
        invocation_dir = self.store.invocation_dir(job_id, invocation_id)
        artifacts = kwargs.get("artifacts") or []
        self.store.write_json(
            invocation_dir / "context-manifest.json",
            {"invocation_id": invocation_id, "purpose": purpose, "fresh_session": True, "artifacts": artifacts},
        )
        usage = CodexUsageRecord(invocation_id, purpose, "succeeded", "reported", 10, 5, 15)
        self.store.write_json(invocation_dir / "usage.json", usage)
        self.store.update_usage_summary(job_id)
        context = artifacts[0].content if artifacts else {}
        if purpose == "segment":
            payload = {
                "segments": [
                    {
                        "id": "s1",
                        "name": "Segment One",
                        "definition": "A test segment",
                        "inclusion_criteria": ["test"],
                        "exclusion_criteria": [],
                        "fit_reason": "Test fit",
                    }
                ]
            }
        elif purpose in {"market_demand", "coverage"}:
            runtime_result = (
                {
                    "needs": ["runtime need"],
                    "workflows": ["runtime workflow"],
                    "demand_signals": [],
                    "assumptions": [],
                    "gaps": [],
                }
                if purpose == "market_demand"
                else {
                    "mappings": [],
                    "use_cases": ["runtime case"],
                    "icp_traits": ["runtime trait"],
                    "gaps": [],
                    "sufficient": self.coverage_sufficient,
                }
            )
            payload = {
                "needs": ["authoring need"] if purpose == "market_demand" else None,
                "workflows": ["authoring workflow"] if purpose == "market_demand" else None,
                "demand_signals": [] if purpose == "market_demand" else None,
                "assumptions": [] if purpose == "market_demand" else None,
                "mappings": [] if purpose == "coverage" else None,
                "use_cases": ["case"] if purpose == "coverage" else None,
                "icp_traits": ["trait"] if purpose == "coverage" else None,
                "gaps": [],
                "sufficient": self.coverage_sufficient if purpose == "coverage" else None,
                "pipeline": {
                    "entry_file": "pipeline.py",
                    "files": [
                        {
                            "path": "pipeline.py",
                            "content": (
                                (
                                    "raise RuntimeError('initial pipeline failed')\n"
                                    if self.fail_first_pipeline and purpose == "market_demand"
                                    else (
                                        "import json\n"
                                        f"result = {runtime_result!r}\n"
                                        "print(json.dumps(result, sort_keys=True))\n"
                                    )
                                )
                            ),
                        }
                    ],
                },
            }
            if self.invalid_first_bundle and purpose == "market_demand":
                payload["pipeline"]["files"].append(
                    {"path": "requirements.txt", "content": "etiq-copilot==2.3.0\n"}
                )
            payload = {key: value for key, value in payload.items() if value is not None}
        elif "_authoring_retry_" in purpose:
            retried_runtime_result = (
                {
                    "needs": ["retried runtime need"],
                    "workflows": ["retried runtime workflow"],
                    "demand_signals": [],
                    "assumptions": [],
                    "gaps": [],
                }
                if purpose.startswith("market_demand")
                else {
                    "mappings": [],
                    "use_cases": ["retried runtime case"],
                    "icp_traits": ["retried runtime trait"],
                    "gaps": [],
                    "sufficient": self.coverage_sufficient,
                }
            )
            payload = {
                "change_summary": "Rewrote the pipeline so it executes.",
                "pipeline": {
                    "entry_file": "pipeline.py",
                    "files": [
                        {
                            "path": "pipeline.py",
                            "content": (
                                "import json\n"
                                f"result = {retried_runtime_result!r}\n"
                                "print(json.dumps(result, sort_keys=True))\n"
                            ),
                        }
                    ],
                },
            }
        elif "_review_" in purpose:
            package = context["review_package"]
            fail_review = self.fail_first_review and self.review_count == 0
            self.review_count += 1
            reviews = []
            for index, unit in enumerate(package["assigned_units"]):
                failed = fail_review and index == 0
                reviews.append(
                    {
                        "unit_id": unit["unit_id"],
                        "decision": "failed" if failed else "trusted",
                        "decision_reason": (
                            "The captured transformation requires repair."
                            if failed
                            else "The captured transformation meets the expected result."
                        ),
                        "evidence_refs": package["evidence_refs"],
                        "trust_level": None if failed else "trusted_for_reuse",
                        "criteria_outcomes": (
                            []
                            if failed
                            else [
                                {
                                    "criterion": "captured output",
                                    "verdict": "met",
                                    "evidence_refs": package["evidence_refs"],
                                }
                            ]
                        ),
                        "boundary_health_acknowledged": True,
                    }
                )
            payload = {"reviews": reviews}
        elif purpose.endswith("_repair"):
            repaired_runtime_result = (
                {
                    "needs": ["repaired runtime need"],
                    "workflows": ["repaired runtime workflow"],
                    "demand_signals": [],
                    "assumptions": [],
                    "gaps": [],
                }
                if purpose.startswith("market_demand")
                else {
                    "mappings": [],
                    "use_cases": ["repaired runtime case"],
                    "icp_traits": ["repaired runtime trait"],
                    "gaps": [],
                    "sufficient": self.coverage_sufficient,
                }
            )
            payload = {
                "change_summary": "Repaired the failed stage.",
                "pipeline": {
                    "entry_file": "pipeline.py",
                    "files": [
                        {
                            "path": "pipeline.py",
                            "content": (
                                "import json\n"
                                f"result = {repaired_runtime_result!r}\n"
                                "print(json.dumps(result, sort_keys=True))\n"
                            ),
                        }
                    ],
                },
            }
        elif purpose.startswith("synthesis_"):
            mode = str(context["mode"])
            payload = {
                "mode": mode,
                "use_cases": ["case"],
                "icp": (
                    {"name": "ICP", "summary": "Test ICP", "traits": ["trait"]}
                    if mode == "supported"
                    else None
                ),
                "gaps": [],
                "limitations": [],
            }
        else:
            raise AssertionError(purpose)
        return CodexResult(invocation_id, payload, usage, [])


class WorkflowTests(unittest.TestCase):
    def test_happy_path_uses_fresh_invocations_and_records_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JobStore(root / "outputs" / "jobs")
            fake_codex = FakeCodex(store)
            etiq = EtiqExecutor(store, scanner_factory=FakeScanner)
            repo_root = Path(__file__).resolve().parents[1]
            workflow = WorkflowRunner(repo_root=repo_root, store=store, codex=fake_codex, etiq=etiq)  # type: ignore[arg-type]
            job_id = workflow.run(AgentRequest("product", "audience", max_segments=1))
            state = store.read_json(store.job_dir(job_id) / "state.json")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(len(fake_codex.invocations), len(set(fake_codex.invocations)))
            self.assertGreaterEqual(len(fake_codex.invocations), 6)
            usage = store.read_json(store.job_dir(job_id) / "usage-summary.json")
            self.assertTrue(usage["complete"])
            self.assertEqual(usage["totals"]["reported"], len(fake_codex.invocations))
            for invocation in (store.job_dir(job_id) / "invocations").iterdir():
                manifest = store.read_json(invocation / "context-manifest.json")
                self.assertIn("repo:AGENTS.md", {item["ref"] for item in manifest["artifacts"]})
            market_demand_result_path = next(
                (store.job_dir(job_id) / "stages" / "s1" / "market_demand" / "runs").glob(
                    "*/semantic-result.json"
                )
            )
            authoring_result_path = market_demand_result_path.with_name("authoring-semantic.json")
            self.assertEqual(
                store.read_json(market_demand_result_path)["needs"],
                ["runtime need"],
            )
            self.assertEqual(
                store.read_json(authoring_result_path)["needs"],
                ["authoring need"],
            )
            for run_dir in (store.job_dir(job_id) / "stages" / "s1").glob("*/runs/*"):
                self.assertTrue((run_dir / "context-accounting.json").exists())
                self.assertTrue((run_dir / "trusted-frontier.json").exists())

    def test_trusted_but_insufficient_coverage_reaches_negative_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JobStore(root / "outputs" / "jobs")
            fake_codex = FakeCodex(store, coverage_sufficient=False)
            workflow = WorkflowRunner(
                repo_root=Path(__file__).resolve().parents[1],
                store=store,
                codex=fake_codex,  # type: ignore[arg-type]
                etiq=EtiqExecutor(store, scanner_factory=FakeScanner),
            )
            job_id = workflow.run(AgentRequest("product", "audience", max_segments=1))
            result = store.read_json(store.job_dir(job_id) / "final" / "result.json")
            self.assertEqual(result["mode"], "no_sufficient_segment")
            self.assertIsNone(result["icp"])
            events = store.read_events(job_id)
            self.assertIn("coverage_insufficient", {event["event_type"] for event in events})

    def test_failed_review_repairs_into_a_new_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JobStore(root / "outputs" / "jobs")
            fake_codex = FakeCodex(store, fail_first_review=True)
            workflow = WorkflowRunner(
                repo_root=Path(__file__).resolve().parents[1],
                store=store,
                codex=fake_codex,  # type: ignore[arg-type]
                etiq=EtiqExecutor(store, scanner_factory=FakeScanner),
            )
            job_id = workflow.run(
                AgentRequest("product", "audience", max_segments=1, limits={"repairs": 1})
            )
            state = store.read_json(store.job_dir(job_id) / "state.json")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["repair_count"], 1)
            self.assertEqual(state["evaluated_repair_count"], 1)
            self.assertEqual(state["effective_repair_count"], 1)
            metrics = store.read_json(
                store.job_dir(job_id)
                / "stages"
                / "s1"
                / "market_demand"
                / "repair-metrics.json"
            )
            self.assertEqual(metrics["repair_effectiveness_rate"], 1.0)
            self.assertEqual(metrics["attempts"][0]["status"], "target_resolved")
            market_demand_runs = list(
                (
                    store.job_dir(job_id)
                    / "stages"
                    / "s1"
                    / "market_demand"
                    / "runs"
                ).iterdir()
            )
            self.assertEqual(len(market_demand_runs), 2)
            self.assertTrue(
                any((run / "parent-run.json").exists() for run in market_demand_runs)
            )
            self.assertTrue(
                any((run / "repair-target.json").exists() for run in market_demand_runs)
            )
            self.assertTrue(
                any((run / "applied-repair.json").exists() for run in market_demand_runs)
            )

    def test_execution_failure_gets_a_fresh_authoring_retry_before_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JobStore(root / "outputs" / "jobs")
            fake_codex = FakeCodex(store, fail_first_pipeline=True)
            workflow = WorkflowRunner(
                repo_root=Path(__file__).resolve().parents[1],
                store=store,
                codex=fake_codex,  # type: ignore[arg-type]
                etiq=EtiqExecutor(store, scanner_factory=FakeScanner),
            )
            job_id = workflow.run(
                AgentRequest(
                    "product",
                    "audience",
                    max_segments=1,
                    limits={"authoring_retries": 2, "repairs": 1},
                )
            )

            state = store.read_json(store.job_dir(job_id) / "state.json")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["authoring_retry_count"], 1)
            self.assertEqual(state["repair_count"], 0)
            self.assertIn("market_demand_authoring_retry_1", fake_codex.purposes)

            market_demand_runs = list(
                (
                    store.job_dir(job_id)
                    / "stages"
                    / "s1"
                    / "market_demand"
                    / "runs"
                ).iterdir()
            )
            self.assertEqual(len(market_demand_runs), 2)
            failed_run = next(
                run for run in market_demand_runs if (run / "execution-error.json").exists()
            )
            retried_run = next(
                run for run in market_demand_runs if (run / "authoring-retry.json").exists()
            )
            retry_link = store.read_json(retried_run / "authoring-retry.json")
            self.assertEqual(retry_link["previous_run_id"], failed_run.name)
            self.assertEqual(
                store.read_json(retried_run / "semantic-result.json")["needs"],
                ["retried runtime need"],
            )

    def test_invalid_bundle_gets_a_fresh_authoring_retry_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JobStore(root / "outputs" / "jobs")
            fake_codex = FakeCodex(store, invalid_first_bundle=True)
            workflow = WorkflowRunner(
                repo_root=Path(__file__).resolve().parents[1],
                store=store,
                codex=fake_codex,  # type: ignore[arg-type]
                etiq=EtiqExecutor(store, scanner_factory=FakeScanner),
            )
            job_id = workflow.run(
                AgentRequest(
                    "product",
                    "audience",
                    max_segments=1,
                    limits={"authoring_retries": 2, "repairs": 1},
                )
            )

            state = store.read_json(store.job_dir(job_id) / "state.json")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["authoring_retry_count"], 1)
            self.assertIn("market_demand_authoring_retry_1", fake_codex.purposes)
            events = store.read_events(job_id)
            self.assertTrue(
                any(
                    event["event_type"] == "pipeline_attempt_failed"
                    and "requirements.txt" in event["summary"]
                    for event in events
                )
            )
            self.assertIn(
                "pipeline_attempt_failed",
                {event["event_type"] for event in store.read_events(job_id)},
            )


if __name__ == "__main__":
    unittest.main()
