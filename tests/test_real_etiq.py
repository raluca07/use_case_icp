from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from use_case_icp.etiq_executor import EXPECTED_ETIQ_VERSION, EtiqExecutor
from use_case_icp.records import AgentRequest, GeneratedFile, GeneratedPipeline, RootJobState
from use_case_icp.review import build_review_units
from use_case_icp.job_store import JobStore


@unittest.skipUnless(importlib.util.find_spec("etiq_copilot"), "etiq-copilot is not installed")
class RealEtiqContractTests(unittest.TestCase):
    def test_pinned_nested_scan_preserves_captured_graph(self) -> None:
        source = """import pandas as pd

def collect(payload):
    gathered = pd.DataFrame([{"value": payload["value"] + 1}])
    return gathered

def rank(payload):
    ranked = payload.copy()
    ranked["ranked"] = ranked["value"] + 10
    return ranked

source = {"value": 1}
collected = collect(source)
result = rank(collected)
"""
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "jobs")
            store.initialize_job(AgentRequest("product", "audience"), RootJobState("job-real"))
            execution = EtiqExecutor(store).execute(
                job_id="job-real",
                segment_id="segment-real",
                stage="market_demand",
                run_id="run-real",
                pipeline=GeneratedPipeline("pipeline.py", [GeneratedFile("pipeline.py", source)]),
            )
            node_refs = {node.node_ref for node in execution.snapshot.nodes}
            self.assertTrue(execution.reviewable)
            self.assertTrue((execution.run_dir / "worker-request.json").exists())
            self.assertTrue((execution.run_dir / "worker-stdout.log").exists())
            self.assertEqual(execution.snapshot.inventories["etiq_copilot_version"], EXPECTED_ETIQ_VERSION)
            self.assertGreater(
                execution.snapshot.inventories["captured_state_counts"]["get_dataframes"],
                0,
            )
            self.assertIn("FunctionMapping", {node.state_type for node in execution.snapshot.nodes})
            self.assertEqual(
                {relationship.relationship_type for relationship in execution.snapshot.relationships},
                {"function_argument", "function_result", "state_parent"},
            )
            self.assertTrue(
                all(
                    relationship.source_ref in node_refs and relationship.target_ref in node_refs
                    for relationship in execution.snapshot.relationships
                )
            )
            units = build_review_units(execution.snapshot)
            unit_by_name = {unit.function_name: unit for unit in units}
            self.assertIn("collect", unit_by_name)
            self.assertIn("rank", unit_by_name)
            self.assertFalse(unit_by_name["collect"].boundary_health.degraded)
            self.assertFalse(unit_by_name["rank"].boundary_health.degraded)


if __name__ == "__main__":
    unittest.main()
