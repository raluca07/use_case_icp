from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from use_case_icp import n07_program, n10_program
from use_case_icp.fault_v21 import qualify_realized_chain


ROOT = Path(__file__).resolve().parents[1]


class N12BindingTests(unittest.TestCase):
    def test_latest_task_authority_protocol_and_phase_a_are_exact(self) -> None:
        bindings = n10_program.validate_n10_bindings(ROOT)
        self.assertEqual(bindings["task_sha256"], n10_program.N13_TASK_SHA256)
        self.assertEqual(bindings["authorization_sha256"], n10_program.N13_AUTHORIZATION_SHA256)
        self.assertEqual(bindings["current_task_sha256"], n10_program.N14_TASK_SHA256)
        self.assertEqual(
            bindings["current_authorization_sha256"],
            n10_program.N14_AUTHORIZATION_SHA256,
        )
        self.assertEqual(bindings["n12_task_sha256"], n10_program.N12_TASK_SHA256)
        self.assertEqual(bindings["n12_authorization_sha256"], n07_program.N12_AUTHORIZATION_SHA256)
        self.assertEqual(bindings["accepted_phase_a_sha256"], n07_program.ACCEPTED_PHASE_A_SHA256)
        self.assertEqual(bindings["accepted_phase_a_tree_sha256"], n07_program.ACCEPTED_PHASE_A_TREE_SHA256)

    def test_accepted_phase_a_is_verified_not_regenerated(self) -> None:
        verified = n07_program.verify_accepted_phase_a(ROOT)
        self.assertFalse(verified["nested_snapshot_hashes_independently_recomputed"])
        self.assertFalse(verified["model_visible"])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "attempt"
            terminal = n07_program._run_lifecycle(
                ROOT,
                output,
                provider=lambda *_: (_ for _ in ()).throw(AssertionError("model called")),
                qualification=True,
                stop_after="construction",
            )
            self.assertTrue((output / "checkpoints/00-phase_a.json").is_file())
            self.assertFalse((output / "phase-a").exists())
            self.assertEqual(json.loads(terminal.read_text())["failed_checkpoint"], "construction")

    def test_phase_b_has_no_lifecycle_or_cli_surface(self) -> None:
        self.assertEqual(
            n07_program.STAGES,
            ("phase_a", "construction", "capture", "package", "review", "repair", "closure", "analysis", "replay"),
        )
        self.assertFalse(hasattr(n07_program, "_phase_b"))
        source = inspect.getsource(n07_program._run_lifecycle)
        self.assertNotIn('stage == "phase_b"', source)


class N12ConstructionTests(unittest.TestCase):
    def test_authoring_request_contains_only_approved_visible_context(self) -> None:
        captured = {}

        class StopConstruction(Exception):
            pass

        def stop(_output, _provider, kind, request, *, parent_id):
            captured.update({"kind": kind, "request": request, "parent_id": parent_id})
            raise StopConstruction

        one_slot = [{
            "instance_id": "instance-01",
            "designation": "faulty",
            "fault_class": "ordering_perturbation",
            "injection_operator": "reverse_ordering",
            "target_job": "upstream",
            "stage": "early",
            "authoring_seed": 101,
            "injection_seed": 202,
        }]
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            n07_program, "_protocol_instance_slots", return_value=one_slot
        ), mock.patch.object(n07_program, "_call_provider", side_effect=stop):
            with self.assertRaises(StopConstruction):
                n07_program._construct_instances(
                    ROOT,
                    Path(temporary),
                    {"phase_a_sha256": n07_program.ACCEPTED_PHASE_A_SHA256},
                    lambda *_: {},
                    qualification=True,
                )
        request = captured["request"]
        self.assertEqual(set(request), {"instance_id", "candidate_number", "authoring_seed", "task"})
        self.assertEqual(
            set(request["task"]),
            {"scenario_id", "corpus", "capabilities", "job_contract", "behavioural_requirements"},
        )
        serialized = json.dumps(request, sort_keys=True)
        for forbidden in (
            "designation", "fault_class", "injection_operator", "target_job",
            "target_stage", "nested_helper", "injection_seed", "ablation", "repair_membership",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_v22_ordinary_two_job_chain_has_no_padding_quotas(self) -> None:
        def realization(job_id: str) -> dict:
            return {
                "job_id": job_id,
                "realized_boundaries": [{"boundary_id": f"{job_id}-one", "semantic_stage": "ordinary"}],
                "boundary_realization_audit": {"unmatched_declaration_count": 0},
            }

        report = qualify_realized_chain(
            [realization("up"), realization("down")],
            handoffs=[
                {"producer_sha256": "same", "consumer_sha256": "same"},
                {"producer_sha256": "same-2", "consumer_sha256": "same-2"},
            ],
            helper_evidence=[],
            graph_size_reports=[],
            has_join_or_aggregation=False,
            protocol_version="2.2.0",
        )
        self.assertEqual(report["realized_boundary_count"], 2)
        self.assertEqual(report["eligible_helper_count"], 0)
        self.assertIsNone(report["selected_to_full_ratio"])

    def test_frozen_instance_schema_is_current_n12(self) -> None:
        schema = json.loads((ROOT / "schemas/v2_2/fault_instance.schema.json").read_text())
        self.assertEqual(
            schema["properties"]["protocol_content_hash"]["const"],
            n07_program.PROTOCOL_CONTENT_SHA256,
        )
        self.assertIn("execution_sha256", schema["required"])


class N12CaptureAndPackageTests(unittest.TestCase):
    def test_capture_reuses_execution_and_freezes_full_runtime_material(self) -> None:
        run_dir = None
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "pipeline-input.json").write_text('{"x":1}')
            (run_dir / "pipeline-stdout.log").write_text("actual stdout\n")
            (run_dir / "pipeline-stderr.log").write_text("actual stderr\n")
            snapshot = mock.Mock()
            snapshot.__class__ = dict
            snapshot = {"nodes": [{"node_ref": "n1"}], "relationships": []}
            execution_item = mock.Mock(run_dir=run_dir, snapshot=snapshot)
            instances = []
            for index in range(12):
                instances.append({
                    "instance_id": f"instance-{index + 1:02d}",
                    "evaluation_execution": {
                        "executions": {"job": execution_item},
                        "outputs": {"job": {"y": index}},
                        "realizations": {"job": {"realized_boundaries": []}},
                        "handoffs": [],
                    },
                    "frozen_record": {"source_sha256": {"job": f"sha256:{index:064x}"}},
                })
            with mock.patch.object(
                n07_program, "create_json_exclusive", return_value="sha256:" + "0" * 64
            ):
                captures = n07_program._capture_instances(root, instances)
        self.assertEqual(len(captures), 12)
        job = captures[0]["jobs"]["job"]
        self.assertEqual(job["input"], {"x": 1})
        self.assertEqual(job["stdout"], "actual stdout\n")
        self.assertEqual(job["stderr"], "actual stderr\n")
        self.assertIn("snapshot", job)
        self.assertNotIn("oracle", captures[0])

    def test_history_is_nonempty_only_for_downstream_ancestry_and_ids_are_instance_specific(self) -> None:
        source = inspect.getsource(n07_program._package_inputs)
        self.assertIn('if job_id == job_ids[1]', source)
        self.assertIn('"task_input"', source)
        self.assertIn('"task_output"', source)
        self.assertIn('"stdout"', source)
        self.assertIn('"stderr"', source)
        self.assertIn("instance_token", source)

    def test_package_neutralization_uses_the_current_execution_realization(self) -> None:
        source = inspect.getsource(n07_program._materialize_packages)
        self.assertIn('**execution["realizations"][job_id]', source)
        self.assertNotIn("**realization,", source)


class N12MechanicalReadinessTests(unittest.TestCase):
    def test_upstream_repair_reruns_the_complete_two_job_chain(self) -> None:
        execution = {"outputs": {}}
        with mock.patch.object(n07_program, "execute_two_job_chain", return_value=execution) as execute, mock.patch.object(
            n07_program, "derive_review_evidence", return_value={"derived": True}
        ):
            result = n07_program._rerun_dependency_suffix(
                Path("branch"),
                repo_root=ROOT,
                jobs={"up": object(), "down": object()},
                scenario={},
                repaired_job_id="up",
                canonical_execution={},
                run_index=1,
                stage="repair",
            )
        execute.assert_called_once()
        self.assertTrue(result["derived"])

    def test_downstream_repair_path_uses_canonical_upstream_hashes(self) -> None:
        source = inspect.getsource(n07_program._rerun_dependency_suffix)
        self.assertIn("deepcopy(canonical_execution", source)
        self.assertIn("producer_hash != consumer_hash", source)
        self.assertIn("reused_upstream_artifact_sha256", source)


class N13RetryLedgerTests(unittest.TestCase):
    def _live_provider(self, root: Path, launch: mock.Mock):
        codex = root / "codex-runtime/bin/codex"
        codex.parent.mkdir(parents=True)
        codex.write_text("")
        patches = (
            mock.patch.object(n07_program.shutil, "which", return_value=str(codex)),
            mock.patch.object(n07_program, "materialize_opaque_branch"),
            mock.patch.object(n07_program, "copy_codex_auth"),
            mock.patch.object(n07_program, "launch_codex_in_branch", launch),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return n07_program._live_provider(
            ROOT,
            root / "attempt",
            source_codex_home=root / "codex-home",
        )

    @staticmethod
    def _completed_result() -> dict:
        return {
            "status": "completed",
            "response": {"reviews": []},
            "usage": {
                "input_tokens": 101,
                "cached_input_tokens": 7,
                "output_tokens": 11,
            },
        }

    def test_live_review_has_one_owner_and_identical_resume_has_zero_launches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launch = mock.Mock(return_value=self._completed_result())
            provider = self._live_provider(root, launch)
            output = root / "attempt"
            request = {"trial_id": "trial-one", "seed": 1, "package": {"visible": True}}
            first = n07_program._call_provider(
                output, provider, "review", request, parent_id="trial-one"
            )
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(len(list((output / "ledger/call-attempt").glob("*.json"))), 1)
            self.assertEqual(first["attempt_count"], 1)
            self.assertEqual(first["call_ids"], first["retry_lineage"]["call_ids"])
            self.assertEqual(first["request_sha256"], first["retry_lineage"]["request_sha256"])
            self.assertEqual(first["retry_lineage"]["usage"]["input_tokens"], 101)

            resumed = n07_program._call_provider(
                output, provider, "review", request, parent_id="trial-one"
            )
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(resumed, first)
            self.assertEqual(n07_program._provider_usage_summary(output)["real_provider_attempts"], 1)

            changed = {**request, "seed": 2}
            with self.assertRaises(ValueError):
                n07_program._call_provider(
                    output, provider, "review", changed, parent_id="trial-one"
                )
            self.assertEqual(launch.call_count, 1)

    def test_live_request_kinds_and_review_rounds_have_distinct_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launch = mock.Mock(return_value=self._completed_result())
            provider = self._live_provider(root, launch)
            output = root / "attempt"
            base = {"trial_id": "trial-two", "seed": 2, "package": {"visible": True}}
            requests = [
                ("review", base, "trial-two"),
                ("review", {**base, "operation_evidence": {"node_refs": ["n1"]}}, "trial-two-follow-up-01"),
                ("review", {**base, "receipt_correction": {"correction_index": 1}}, "trial-two-receipt-correction-01"),
                ("review", {**base, "trial_id": "repair-two-re-review"}, "repair-two-re-review"),
            ]
            package_path = root / "repair-package.json"
            package_path.write_text('{"source_bundle":{"private":true}}')
            requests.append(
                (
                    "repair",
                    {
                        "repair_id": "repair-two",
                        "branch_id": "branch-two",
                        "package_path": str(package_path),
                        "selected_source": {"file": "pipeline.py"},
                        "review": {"trial_id": "trial-two"},
                    },
                    "repair-two",
                )
            )
            call_ids = []
            for kind, request, parent_id in requests:
                response = n07_program._call_provider(
                    output, provider, kind, request, parent_id=parent_id
                )
                call_ids.extend(response["call_ids"])
            self.assertEqual(launch.call_count, 5)
            self.assertEqual(len(call_ids), 5)
            self.assertEqual(len(set(call_ids)), 5)
            self.assertEqual(n07_program._provider_usage_summary(output)["real_provider_attempts"], 5)

    def test_qualification_provider_returns_the_same_zero_model_lineage_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)

            def qualification(_kind, _request):
                return {
                    "status": "complete",
                    "response": {"reviews": []},
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                    "real_model_call": False,
                }

            response = n07_program._call_provider(
                output,
                qualification,
                "review",
                {"trial_id": "qualification", "seed": 0},
                parent_id="qualification",
            )
            self.assertFalse(response["real_model_call"])
            self.assertEqual(response["call_ids"], response["retry_lineage"]["call_ids"])
            self.assertEqual(len(response["retry_lineage"]["attempts"]), 1)
            self.assertEqual(n07_program._provider_usage_summary(output)["real_provider_attempts"], 0)

    def test_attempt_023_frozen_base_and_first_review_match_n13(self) -> None:
        attempt = ROOT / n10_program.N10_OUTPUT_RELATIVE / n10_program.N12_ATTEMPT
        frozen = n10_program._verify_n13_frozen_state(ROOT, attempt)
        self.assertEqual(frozen["package_count"], 96)
        self.assertEqual(frozen["verified_package_count"], 96)
        self.assertEqual(frozen["unique_package_sha256_count"], 96)
        self.assertEqual(
            frozen["first_review"]["matching_call_ids"],
            [n10_program.N13_FIRST_REVIEW["call_id"]],
        )

    def test_package_checkpoint_reuses_preserved_first_call_and_writes_review(self) -> None:
        source = ROOT / "outputs/fault-experiments-v2-2-n10/attempt-023"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "attempt"
            (output / "checkpoints").mkdir(parents=True)
            for checkpoint in sorted((source / "checkpoints").glob("0[0-3]-*.json")):
                shutil.copy2(checkpoint, output / "checkpoints" / checkpoint.name)
            for relative in (
                "state",
                "provider-requests/trial-000-639fb9a3fb1db2fb",
                "packages/branch-000-79f5fe52dbf8839b",
            ):
                shutil.copytree(source / relative, output / relative)
            call_ledger = output / "ledger/call-attempt"
            call_ledger.mkdir(parents=True)
            required_call = source / "ledger/call-attempt" / f"{n10_program.N13_FIRST_REVIEW['call_id']}.json"
            call_records = [required_call]
            call_records.extend(
                path
                for path in sorted((source / "ledger/call-attempt").glob("*.json"))
                if path != required_call
            )
            for call_record in call_records[:25]:
                shutil.copy2(call_record, call_ledger / call_record.name)
            shutil.copy2(source / "experiment-freeze.json", output / "experiment-freeze.json")
            before = n07_program._tree_contract(
                root, output / "packages/branch-000-79f5fe52dbf8839b"
            )["tree_sha256"]
            launch = mock.Mock(side_effect=AssertionError("preserved review relaunched"))
            provider = self._live_provider(root, launch)
            first_trial = n07_program.expected_design()["review_trials"][0]
            with mock.patch.object(
                n07_program,
                "expected_design",
                return_value={"review_trials": [first_trial], "repair_traces": []},
            ):
                n07_program._run_lifecycle(
                    ROOT,
                    output,
                    provider=provider,
                    qualification=False,
                    stop_after="repair",
                )
            self.assertEqual(launch.call_count, 0)
            self.assertTrue((output / "reviews" / f"{first_trial['trial_id']}.json").is_file())
            self.assertEqual(len(list((output / "ledger/call-attempt").glob("*.json"))), 25)
            after = n07_program._tree_contract(
                root, output / "packages/branch-000-79f5fe52dbf8839b"
            )["tree_sha256"]
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
