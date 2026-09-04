from __future__ import annotations

from copy import deepcopy
import json
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from use_case_icp.corrected_experiment import (
    EVIDENCE_MODES,
    N14B_AUTHORITY,
    N14B_AUTHORITY_SHA256,
    _normalized_review_response,
    _controller_key_paths,
    aggregate_actual_usage,
    build_corrected_attempt,
    build_n15_attempt,
    build_disclosure_catalogue,
    build_review_package,
    expand_n15_helper,
    canonical_json,
    dependency_suffix,
    execute_resumable_lifecycle,
    experiment_schedule,
    expand_helper,
    freeze_corrected_attempt,
    inspect_artifact,
    perform_operation,
    production_reviewer,
    record_attempt_024_incomplete,
    render_provider_request,
    run_corrected_lifecycle,
    run_follow_up_loop,
    sha256,
    score_n15_top_suspect,
    usage_record,
    validate_visible_reference,
    validate_n15_reviewer_response,
    verify_frozen_attempt,
    write_zero_model_orchestration_report,
)
from use_case_icp.fault_operations import (
    ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
    PROTOCOL_CONTENT_HASH,
    _validate_artifact_python_expression,
    artifact_python_launcher,
    production_launcher_sha256,
    signed_catalogue_python_executor,
)


ROOT = Path(__file__).resolve().parents[1]


def node(ref: str, stack: list[str], artifact_kind=None, artifact_content=None):
    value = {
        "node_ref": ref,
        "raw_id": ref,
        "names": [ref],
        "line_no": 1,
        "state_type": "DataframeState" if artifact_kind == "table" else "state",
        "value_type": "DataFrame" if artifact_kind == "table" else "str",
        "func_stack": stack,
        "source": f"{ref} = captured()",
        "scope_type": "FunctionDef",
        "raw_metadata": {"capture": ref},
        "value_preview": "preview",
        "preview_truncated": artifact_content is not None,
        "artifact_kind": artifact_kind,
        "artifact_content": artifact_content,
        "artifact_truncated": False,
        "artifact_size": (
            {"rows": len(artifact_content["rows"]), "columns": len(artifact_content["columns"])}
            if artifact_kind == "table"
            else {"characters": len(artifact_content)}
            if artifact_kind == "document"
            else None
        ),
    }
    return value


def relationship(ref: str, source: str, target: str):
    return {
        "relationship_ref": ref,
        "source_ref": source,
        "target_ref": target,
        "relationship_type": "captured",
        "direction": "captured_flow",
        "raw_metadata": {"edge": ref},
    }


def fixture_capture(instance_id="instance-01"):
    document = "0123456789" * 501
    table = {
        "columns": ["record_id", "demand_score", "nullable"],
        "rows": [
            {"record_id": "a", "demand_score": 1, "nullable": None},
            {"record_id": "b", "demand_score": 3, "nullable": "x"},
        ],
    }
    nodes = [
        node("outside-in", ["main"]),
        node("root-table", ["main", "target_function"], "table", table),
        node("root-doc", ["main", "target_function"], "document", document),
        node("helper-a", ["main", "target_function", "helper_a"], "document", "inside a"),
        node("nested", ["main", "target_function", "helper_a", "nested_helper"], "document", "nested"),
        node("helper-b", ["main", "target_function", "helper_b"], "document", "inside b"),
        node("outside-out", ["main"]),
    ]
    relationships = [
        relationship("edge-in", "outside-in", "root-table"),
        relationship("edge-root", "root-table", "root-doc"),
        relationship("edge-a", "root-doc", "helper-a"),
        relationship("edge-nested", "helper-a", "nested"),
        relationship("edge-b", "root-doc", "helper-b"),
        relationship("edge-out", "root-doc", "outside-out"),
    ]
    boundary = {
        "boundary_id": "captured-boundary",
        "function_name": "target_function",
        "matched_prefix": ["main", "target_function"],
        "matched_function_node_ref": "root-table",
        "node_refs": [value["node_ref"] for value in nodes[1:-1]],
        "relationship_refs": [value["relationship_ref"] for value in relationships],
        "input_relationship_refs": ["edge-in"],
        "output_relationship_refs": ["edge-out"],
        "helper_prefixes": [
            ["main", "target_function", "helper_a"],
            ["main", "target_function", "helper_a", "nested_helper"],
            ["main", "target_function", "helper_b"],
        ],
        "role": "target",
        "expected_inputs": ["captured input"],
        "expected_outputs": ["captured output"],
        "realized_boundary_sha256": "frozen-fixture-boundary",
        "static_identity": {
            "job_id": "fixture-job",
            "source_path": "generated/fixture.py",
            "qualified_function_name": "target_function",
            "function_source_sha256": sha256(b"target_function"),
        },
    }
    snapshots = {}
    for job_id in ("upstream", "downstream"):
        snapshots[job_id] = {
            "input": {"job": job_id},
            "output": {"job": job_id},
            "stdout": "",
            "stderr": "",
            "snapshot": {
                "snapshot_id": f"snapshot-{job_id}",
                "job_id": job_id,
                "run_id": f"run-{job_id}",
                "nodes": deepcopy(nodes),
                "relationships": deepcopy(relationships),
                "inventories": {},
                "scan_errors": [],
                "created_at": "2026-01-01T00:00:00Z",
                "schema_version": "1",
            },
            "realization": {"realized_boundaries": [deepcopy(boundary)]},
        }
    capture = {
        "schema_version": "1",
        "capture_id": "capture-fixture",
        "instance_id": instance_id,
        "job_ids": ["upstream", "downstream"],
        "jobs": snapshots,
        "handoffs": [
            {
                "handoff_id": "handoff-one",
                "upstream_job_id": "upstream",
                "downstream_job_id": "downstream",
                "producer_sha256": sha256({"handoff": 1}),
                "consumer_sha256": sha256({"handoff": 1}),
            }
        ],
        "source_sha256": {"upstream": sha256(b"up"), "downstream": sha256(b"down")},
        "canonical": True,
        "attempt_count": 1,
    }
    capture["capture_sha256"] = sha256(capture)
    return capture


def neutral_base():
    return {
        "common_base": {
            "schema_version": "1",
            "review_task": "Review one assigned boundary.",
            "behavioural_criteria": ["preserve behavior"],
            "top_level": {"input": {}, "final_output": {}},
            "assigned_job": {"job_id": "opaque-job", "input": {}, "output": {}},
            "semantic_declarations": [
                {
                    "boundary_id": "bnd-reviewer",
                    "function_name": "target_function",
                    "role": "target",
                    "expected_inputs": [],
                    "expected_outputs": [],
                }
            ],
            "section": {
                "section_id": "section-one",
                "assigned_boundary_ids": ["bnd-reviewer"],
                "context_boundary_ids": [],
            },
        },
        "source_bundle": [{"job_id": "opaque-job", "files": []}],
        "prior_task_records": [{"ref": "history-one", "content": "prior"}],
    }


class CorrectedProjectionTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = build_disclosure_catalogue(fixture_capture())
        self.fixed = build_review_package(
            self.catalogue,
            evidence_mode="etiq_selected_fixed",
            source_setting="source_present",
            neutral_base=neutral_base(),
        )
        self.adaptive = build_review_package(
            self.catalogue,
            evidence_mode="etiq_selected_adaptive",
            source_setting="source_present",
            neutral_base=neutral_base(),
        )
        self.boundary_id = self.adaptive["common_base"]["semantic_declarations"][0]["boundary_id"]

    def test_exact_prefix_is_visible_but_descendants_are_collapsed(self):
        refs = {value["node_ref"] for value in self.fixed["runtime_evidence"]["nodes"]}
        self.assertEqual(refs, {"outside-in", "root-table", "root-doc", "outside-out"})
        collapsed = self.fixed["runtime_evidence"]["collapsed_children"]
        self.assertEqual({tuple(value["func_stack"]) for value in collapsed}, {
            ("main", "target_function", "helper_a"),
            ("main", "target_function", "helper_b"),
        })
        self.assertEqual(
            set(collapsed[0]),
            {"boundary_id", "func_stack", "parent_func_stack", "direct_child", "captured_node_count", "has_nested_children"},
        )

    def test_fixed_and_adaptive_initial_graph_bytes_are_identical(self):
        self.assertEqual(
            canonical_json(self.fixed["runtime_evidence"]),
            canonical_json(self.adaptive["runtime_evidence"]),
        )

    def test_provider_package_has_no_controller_identifiers(self):
        rendered = render_provider_request(self.adaptive)
        serialized = canonical_json(rendered).decode()
        for forbidden in (
            "condition_id", "branch_id", "evidence_mode", "source_setting",
            "trial_id", "repair_id", "repetition",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(set(rendered), {"reviewer_package"})

    def test_history_pairs_use_exact_canonical_upstream_execution(self):
        downstream_catalogue = build_disclosure_catalogue(fixture_capture("instance-03"))
        full = build_review_package(
            downstream_catalogue,
            evidence_mode="history_full",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )
        empty = build_review_package(
            downstream_catalogue,
            evidence_mode="history_empty",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )
        left = deepcopy(full)
        right = deepcopy(empty)
        history = left.pop("prior_task_records")
        self.assertEqual(right.pop("prior_task_records"), [])
        self.assertEqual(left, right)
        upstream = downstream_catalogue["jobs"][downstream_catalogue["job_order"][0]]
        self.assertEqual(
            history,
            [{key: upstream[key] for key in ("input", "output", "stdout", "stderr")}],
        )

        upstream_catalogue = build_disclosure_catalogue(fixture_capture("instance-01"))
        upstream_full = build_review_package(
            upstream_catalogue,
            evidence_mode="history_full",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )
        upstream_empty = build_review_package(
            upstream_catalogue,
            evidence_mode="history_empty",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )
        self.assertEqual(upstream_full, upstream_empty)

    def test_random_is_rebuilt_against_corrected_fixed_and_cannot_expand(self):
        random_package = build_review_package(
            self.catalogue,
            evidence_mode="etiq_random_matched",
            source_setting="source_present",
            neutral_base=neutral_base(),
        )
        runtime = random_package["runtime_evidence"]
        self.assertEqual(
            runtime["random_match"]["corrected_fixed_projection_sha256"],
            self.fixed["runtime_evidence"]["projection_sha256"],
        )
        self.assertEqual(runtime["collapsed_children"], [])

    def test_nested_expansion_requires_parent_then_reveals_one_exact_level(self):
        nested_request = {
            "operation": "helper_expansion",
            "boundary_id": self.boundary_id,
            "prefixes": [["main", "target_function", "helper_a", "nested_helper"]],
        }
        unchanged, rejected = perform_operation(self.catalogue, self.adaptive, nested_request)
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(unchanged, self.adaptive)

        opened, event = expand_helper(
            self.catalogue,
            self.adaptive,
            {
                "operation": "helper_expansion",
                "boundary_id": self.boundary_id,
                "prefixes": [["main", "target_function", "helper_a"]],
            },
        )
        self.assertEqual(event["nodes_added"], ["helper-a"])
        refs = {value["node_ref"] for value in opened["runtime_evidence"]["nodes"]}
        self.assertIn("helper-a", refs)
        self.assertNotIn("nested", refs)
        self.assertNotIn("helper-b", refs)
        self.assertEqual(
            {tuple(value["func_stack"]) for value in opened["runtime_evidence"]["collapsed_children"]},
            {
                ("main", "target_function", "helper_a", "nested_helper"),
                ("main", "target_function", "helper_b"),
            },
        )

        opened_twice, second = expand_helper(self.catalogue, opened, nested_request)
        self.assertEqual(second["nodes_added"], ["nested"])
        refs = {value["node_ref"] for value in opened_twice["runtime_evidence"]["nodes"]}
        self.assertNotIn("helper-b", refs)

    def test_non_adaptive_conditions_reject_helper_expansion(self):
        request = {
            "operation": "helper_expansion",
            "boundary_id": self.boundary_id,
            "prefixes": [["main", "target_function", "helper_a"]],
        }
        for mode in EVIDENCE_MODES:
            if mode == "etiq_selected_adaptive":
                continue
            package = build_review_package(
                self.catalogue,
                evidence_mode=mode,
                source_setting="source_absent",
                neutral_base=neutral_base(),
            )
            _, event = perform_operation(self.catalogue, package, request)
            self.assertEqual(event["status"], "rejected", mode)

    def test_hidden_node_becomes_citable_and_inspectable_after_expansion(self):
        with self.assertRaisesRegex(ValueError, "not visible"):
            validate_visible_reference(self.adaptive, "helper-a")
        with self.assertRaisesRegex(ValueError, "currently visible"):
            inspect_artifact(
                self.catalogue,
                self.adaptive,
                {"node_ref": "helper-a", "inspection": "full"},
            )
        opened, _ = expand_helper(
            self.catalogue,
            self.adaptive,
            {
                "operation": "helper_expansion",
                "boundary_id": self.boundary_id,
                "prefixes": [["main", "target_function", "helper_a"]],
            },
        )
        self.assertEqual(validate_visible_reference(opened, "helper-a"), "helper-a")
        self.assertEqual(
            inspect_artifact(
                self.catalogue, opened, {"node_ref": "helper-a", "inspection": "full"}
            )["content"],
            "inside a",
        )


class CorrectedInspectionTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = build_disclosure_catalogue(fixture_capture())
        self.package = build_review_package(
            self.catalogue,
            evidence_mode="etiq_selected_fixed",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )

    def test_read_describe_full_and_python(self):
        read = inspect_artifact(
            self.catalogue,
            self.package,
            {"node_ref": "root-table", "inspection": "read", "start": 1, "count": 1, "columns": ["record_id", "demand_score"]},
        )
        self.assertEqual(read["content"], [{"record_id": "b", "demand_score": 3}])

        describe = inspect_artifact(
            self.catalogue,
            self.package,
            {"node_ref": "root-table", "inspection": "describe", "columns": ["demand_score"], "include_raw_metadata": True},
        )
        self.assertEqual(describe["row_count"], 2)
        self.assertEqual(describe["null_counts"]["nullable"], 1)
        self.assertEqual(describe["numeric_statistics"]["demand_score"]["median"], 2)
        self.assertEqual(describe["raw_metadata"], {"capture": "root-table"})

        full = inspect_artifact(
            self.catalogue, self.package, {"node_ref": "root-doc", "inspection": "full"}
        )
        self.assertGreater(len(full["content"]), 4_000)
        self.assertEqual(full["artifact_value_sha256"], sha256(full["content"]))

        python = inspect_artifact(
            self.catalogue,
            self.package,
            {"node_ref": "root-table", "inspection": "python", "code": "df.groupby('nullable', dropna=False).size().to_dict()"},
            python_executor=lambda _node, _code: {
                "result": {"nan": 1, "x": 1},
                "result_sha256": sha256({"nan": 1, "x": 1}),
            },
        )
        self.assertEqual(python["result"], {"nan": 1, "x": 1})
        self.assertEqual(python["result_sha256"], sha256(python["result"]))

    def test_document_read_uses_exact_character_count(self):
        result = inspect_artifact(
            self.catalogue,
            self.package,
            {"node_ref": "root-doc", "inspection": "read", "start": 5, "count": 20},
        )
        self.assertEqual(len(result["content"]), 20)
        self.assertTrue(result["more_available"])

    def test_python_fails_closed_without_signed_sandbox(self):
        with self.assertRaisesRegex(ValueError, "signed production sandbox unavailable"):
            inspect_artifact(
                self.catalogue,
                self.package,
                {"node_ref": "root-table", "inspection": "python", "code": "len(df)"},
            )

    def test_real_bubblewrap_cpu_allowance_and_other_limits(self):
        unsigned_gate = {
            "status": "passed",
            "protocol_content_hash": PROTOCOL_CONTENT_HASH,
            "production_launcher_sha256": production_launcher_sha256(
                artifact_python_launcher
            ),
            "launch_policy_sha256": ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
            "sandbox_backend": "bubblewrap",
            "sandbox_backend_version": "bubblewrap 0.9.0",
            "tester_identity": "unit-test",
            "signed_at": "2026-09-03T00:00:00Z",
            "probe_results": [{"status": "passed", "skipped": False}],
        }
        gate = {**unsigned_gate, "tester_signature": sha256(unsigned_gate)}
        executor = signed_catalogue_python_executor(
            gate=gate,
            expected_gate_sha256=sha256(gate),
            repo_root=ROOT,
        )
        table = {
            "artifact_kind": "table",
            "artifact_content": {
                "columns": ["group", "value"],
                "rows": [["a", 1], ["a", 2], ["b", 4]],
            },
        }
        self.assertEqual(
            [executor(table, "len(df)")["result"] for _ in range(3)],
            [3, 3, 3],
        )
        with self.assertRaisesRegex(ValueError, "signed production sandbox"):
            executor(table, "sum(range(10 ** 9))")
        with self.assertRaisesRegex(ValueError, "signed production sandbox"):
            executor(table, "[0] * (10 ** 8)")
        with self.assertRaisesRegex(ValueError, "signed production sandbox|output limit"):
            executor(table, "list(range(300000))")
        for expression in (
            "open('/tmp/escape', 'w')",
            "__import__('socket')",
            "__import__('subprocess')",
            "__import__('os').environ",
            "df.to_csv('/tmp/escape')",
            "getattr(df, 'to_pickle')('/tmp/escape')",
        ):
            with self.assertRaises(ValueError):
                _validate_artifact_python_expression(expression)
        with mock.patch(
            "use_case_icp.fault_operations.run_python_in_branch",
            side_effect=RuntimeError("Bubblewrap unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Bubblewrap unavailable"):
                executor(table, "len(df)")


class CorrectedLifecycleTests(unittest.TestCase):
    def test_attempt_026_same_gate_freezes_verifies_and_enters_guarded_live(self):
        source_handoff = json.loads(
            (
                ROOT
                / "outputs/fault-experiments-v2-2-n10/attempt-025/qualification/developer-to-tester-b13d882b5af6a753.json"
            ).read_text()
        )
        authorities = deepcopy(source_handoff["authorities"])
        authorities["N14B"] = {
            "path": N14B_AUTHORITY.as_posix(),
            "sha256": N14B_AUTHORITY_SHA256,
        }
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temporary:
            attempt = Path(temporary) / "attempt-026"
            handoff = {
                "status": "test-only-guarded-live",
                "authorities": authorities,
                "governed_files": {},
            }
            handoff["handoff_sha256"] = sha256(handoff)
            handoff_path = attempt / "qualification/developer-to-tester-test.json"
            handoff_path.parent.mkdir(parents=True)
            handoff_path.write_bytes(canonical_json(handoff))
            unsigned_gate = {
                "status": "passed",
                "protocol_content_hash": PROTOCOL_CONTENT_HASH,
                "production_launcher_sha256": production_launcher_sha256(
                    artifact_python_launcher
                ),
                "launch_policy_sha256": ARTIFACT_PYTHON_LAUNCH_POLICY_SHA256,
                "sandbox_backend": "bubblewrap",
                "sandbox_backend_version": "bubblewrap 0.9.0",
                "tester_identity": "unit-test",
                "signed_at": "2026-09-03T00:00:00Z",
                "probe_results": [{"status": "passed", "skipped": False}],
                "authorities": authorities,
                "latest_developer_handoff_path": handoff_path.relative_to(ROOT).as_posix(),
                "latest_developer_handoff_file_sha256": sha256(
                    handoff_path.read_bytes()
                ),
            }
            gate = {**unsigned_gate, "tester_signature": sha256(unsigned_gate)}
            observed = {}

            def qualify(packages, _catalogues, schedule, **_kwargs):
                observed["conditions"] = schedule["packages"]
                return {"status": "passed"}

            with mock.patch(
                "use_case_icp.corrected_experiment.ATTEMPT_026",
                attempt.relative_to(ROOT),
            ):
                freeze_path = freeze_corrected_attempt(
                    ROOT, attempt, tester_gate=gate
                )
                with mock.patch(
                    "use_case_icp.corrected_experiment.qualify_zero_model_lifecycle",
                    side_effect=qualify,
                ):
                    verified = verify_frozen_attempt(
                        ROOT, attempt, tester_gate=gate
                    )
            self.assertEqual(verified["status"], "verified")
            self.assertEqual(len(observed["conditions"]), 64)
            self.assertEqual(
                sha256(
                    {
                        path.relative_to(attempt / "packages").as_posix(): sha256(
                            path.read_bytes()
                        )
                        for path in sorted((attempt / "packages").rglob("*"))
                        if path.is_file()
                    }
                ),
                "sha256:95437dc67a2d77c4ef3469c7fc31b2743323ff0fa6fdb32965ebfcaec85df7e8",
            )

            def guarded(_request, **_kwargs):
                raise RuntimeError("guarded live entry reached")

            with mock.patch(
                "use_case_icp.corrected_experiment.ATTEMPT_026",
                attempt.relative_to(ROOT),
            ), mock.patch(
                "use_case_icp.corrected_experiment.verify_frozen_attempt",
                return_value={"zero_model_lifecycle": {"status": "passed"}},
            ):
                terminal_path = run_corrected_lifecycle(
                    ROOT,
                    attempt,
                    reviewer=guarded,
                    repairer=guarded,
                    rerunner=guarded,
                    tester_gate=gate,
                )
            self.assertIn(
                "guarded live entry reached",
                json.loads(terminal_path.read_text())["error"],
            )
            self.assertTrue((attempt / "live-consumption.json").is_file())

            other_unsigned = {**unsigned_gate, "signed_at": "2026-09-03T00:00:01Z"}
            other_gate = {
                **other_unsigned,
                "tester_signature": sha256(other_unsigned),
            }
            with mock.patch(
                "use_case_icp.corrected_experiment.ATTEMPT_026",
                attempt.relative_to(ROOT),
            ), self.assertRaisesRegex(ValueError, "differs from the gate"):
                verify_frozen_attempt(ROOT, attempt, tester_gate=other_gate)
            self.assertTrue(freeze_path.is_file())

    def test_frozen_verifier_reconstructs_all_package_conditions(self):
        attempt = ROOT / "outputs/fault-experiments-v2-2-n10/attempt-025"
        gate = json.loads(
            (
                attempt
                / "qualification/tester-n14a-delta-gate-b13d882b5af6a753.json"
            ).read_text()
        )
        observed = {}

        def qualify(packages, _catalogues, schedule, **_kwargs):
            observed["package_conditions"] = schedule["packages"]
            self.assertEqual(len(packages), 64)
            return {"status": "passed"}

        with mock.patch(
            "use_case_icp.corrected_experiment.qualify_zero_model_lifecycle",
            side_effect=qualify,
        ):
            verified = verify_frozen_attempt(
                ROOT,
                attempt,
                tester_gate=gate,
            )
        expected = [
            json.loads(path.read_text())["controller_condition"]
            for path in sorted((attempt / "controller-manifests").glob("*.json"))
        ]
        self.assertEqual(verified["status"], "verified")
        self.assertEqual(len(observed["package_conditions"]), 64)
        self.assertEqual(observed["package_conditions"], expected)

    def test_live_cli_enters_production_path_without_making_a_provider_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt = root / "attempt-025"
            gate = root / "candidate-gate.json"
            gate.write_text("{}", encoding="utf-8")
            completed = subprocess.run(
                [
                    str(ROOT / ".venv/bin/python"),
                    "-m",
                    "use_case_icp",
                    "--repo-root",
                    str(ROOT),
                    "fault-experiment-corrected-four",
                    "live",
                    "--attempt-root",
                    str(attempt),
                    "--tester-gate",
                    str(gate),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1)
            terminal_path = Path(completed.stdout.strip())
            self.assertTrue(terminal_path.is_file())
            self.assertEqual(json.loads(terminal_path.read_text())["status"], "terminal_incomplete")
            self.assertFalse((attempt / "live-consumption.json").exists())
            self.assertFalse((attempt / "ledger/call-attempt").exists())

    def test_production_reviewer_branch_contains_only_rendered_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_codex = root / "runtime/bin/codex"
            fake_codex.parent.mkdir(parents=True)
            fake_codex.write_text("", encoding="utf-8")
            codex_home = root / "codex-home"
            codex_home.mkdir()
            (codex_home / "auth.json").write_text("{}", encoding="utf-8")
            model_request = {"reviewer_package": self._plain_package()}
            observed = {}

            def launch(branch, **_kwargs):
                observed["prompt"] = (branch / "evidence/prompt.md").read_text()
                observed["evidence"] = sorted(
                    path.name for path in (branch / "evidence").iterdir()
                )
                return {
                    "status": "completed",
                    "response": {"reviews": []},
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                }

            with (
                mock.patch(
                    "use_case_icp.corrected_experiment.shutil.which",
                    return_value=str(fake_codex),
                ),
                mock.patch(
                    "use_case_icp.corrected_experiment.launch_codex_in_branch",
                    side_effect=launch,
                ),
            ):
                response = production_reviewer(
                    model_request,
                    controller_parent_id="controller-secret-trial",
                    repo_root=ROOT,
                    attempt_root=root / "attempt",
                    source_codex_home=codex_home,
                )
            self.assertEqual(observed["evidence"], ["prompt.md", "schema.json"])
            self.assertNotIn("controller-secret-trial", observed["prompt"])
            self.assertEqual(response["usage"], {"input_tokens": 2, "output_tokens": 1})
            self.assertEqual(len(response["call_ids"]), 1)

    @staticmethod
    def _plain_package():
        catalogue = build_disclosure_catalogue(fixture_capture())
        return build_review_package(
            catalogue,
            evidence_mode="current_run",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )

    def test_complete_zero_model_orchestration_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            report_path = write_zero_model_orchestration_report(
                ROOT, Path(temporary) / "attempt-025"
            )
            report = json.loads(report_path.read_text())
            self.assertEqual(report["status"], "completed_experiment_and_analysis")
            self.assertEqual(report["real_provider_calls"], 0)
            self.assertEqual(report["packages"], 64)
            self.assertEqual(report["synthetic_initial_reviews"], 192)
            self.assertEqual(report["synthetic_repair_traces"], 96)
            self.assertEqual(report["synthetic_repaired_recaptures"], 96)
            self.assertEqual(report["exact_resume_relaunched_calls"], 0)

    def test_actual_usage_is_per_call_and_missing_values_are_not_zero(self):
        initial = usage_record(
            {"usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_tokens": 1, "total_tokens": 14}},
            purpose="initial_review",
            phase="faulty_run",
        )
        missing = usage_record({}, purpose="artifact_inspection_follow_up", phase="faulty_run")
        self.assertEqual(initial["total_tokens"], 14)
        self.assertIsNone(missing["input_tokens"])
        aggregate = aggregate_actual_usage([initial, missing])
        self.assertIsNone(aggregate["cumulative_actual_input_tokens"])
        self.assertFalse(aggregate["usage_complete"])

    def test_follow_up_loop_uses_fresh_calls_and_accumulated_package(self):
        catalogue = build_disclosure_catalogue(fixture_capture())
        package = build_review_package(
            catalogue,
            evidence_mode="etiq_selected_adaptive",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )
        boundary_id = package["common_base"]["semantic_declarations"][0]["boundary_id"]
        seen = []

        def reviewer(request):
            seen.append(request)
            return {
                "usage": {"input_tokens": 2, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_tokens": 0, "total_tokens": 3},
                "follow_up_requests": [],
                "final": True,
            }

        result = run_follow_up_loop(
            catalogue=catalogue,
            package=package,
            initial_response={
                "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_tokens": 0, "total_tokens": 2},
                "follow_up_requests": [{
                    "operation": "helper_expansion",
                    "boundary_id": boundary_id,
                    "prefixes": [["main", "target_function", "helper_a"]],
                }],
            },
            reviewer=reviewer,
        )
        self.assertEqual(result["operation_follow_up_count"], 1)
        self.assertEqual(result["usage"]["cumulative_actual_input_tokens"], 3)
        self.assertIn(
            "helper-a",
            {value["node_ref"] for value in seen[0]["reviewer_package"]["runtime_evidence"]["nodes"]},
        )

    def test_follow_up_loop_processes_every_queued_request(self):
        catalogue = build_disclosure_catalogue(fixture_capture())
        package = build_review_package(
            catalogue,
            evidence_mode="etiq_selected_fixed",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )
        calls = []

        def reviewer(request):
            calls.append(request)
            return {
                "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_tokens": 0, "total_tokens": 2},
                "follow_up_requests": [],
            }

        result = run_follow_up_loop(
            catalogue=catalogue,
            package=package,
            initial_response={
                "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_tokens": 0, "total_tokens": 2},
                "follow_up_requests": [
                    {"operation": "artifact_inspection", "requests": [{"node_ref": "root-table", "inspection": "describe"}]},
                    {"operation": "artifact_inspection", "requests": [{"node_ref": "root-doc", "inspection": "read", "start": 0, "count": 5}]},
                ],
            },
            reviewer=reviewer,
        )
        self.assertEqual(result["operation_follow_up_count"], 2)
        self.assertEqual(len(calls), 2)

    def test_n14c_rejects_unavailable_duplicate_and_over_limit_requests(self):
        catalogue = build_disclosure_catalogue(fixture_capture())
        package = build_review_package(
            catalogue,
            evidence_mode="etiq_selected_fixed",
            source_setting="source_absent",
            neutral_base=neutral_base(),
        )
        first = {
            "operation": "artifact_inspection",
            "requests": [{"node_ref": "root-table", "inspection": "describe"}],
        }
        requests = [
            {
                "operation": "helper_expansion",
                "boundary_id": package["common_base"]["section"]["assigned_boundary_ids"][0],
                "prefixes": [["main", "target_function", "helper_a"]],
            },
            first,
            deepcopy(first),
            {
                "operation": "artifact_inspection",
                "requests": [{"node_ref": "root-doc", "inspection": "describe"}],
            },
            {
                "operation": "artifact_inspection",
                "requests": [{"node_ref": "root-table", "inspection": "full"}],
            },
            {
                "operation": "artifact_inspection",
                "requests": [
                    {
                        "node_ref": "root-doc",
                        "inspection": "read",
                        "start": 0,
                        "count": 5,
                    }
                ],
            },
        ]
        calls = []

        def reviewer(_request):
            calls.append(len(calls) + 1)
            return {
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "follow_up_requests": [],
                "latest_receipt": calls[-1],
            }

        with mock.patch(
            "use_case_icp.corrected_experiment.perform_operation",
            wraps=perform_operation,
        ) as operation:
            result = run_follow_up_loop(
                catalogue=catalogue,
                package=package,
                initial_response={
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "follow_up_requests": requests,
                },
                reviewer=reviewer,
            )
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(operation.call_count, 3)
        self.assertEqual(result["response"]["latest_receipt"], 3)
        self.assertEqual(result["operation_follow_up_count"], 3)
        statuses = [value["status"] for value in result["operation_events"]]
        self.assertEqual(
            statuses,
            [
                "rejected_unavailable_operation",
                "completed",
                "rejected_duplicate_request",
                "completed",
                "completed",
                "rejected_limit_exhausted",
            ],
        )
        for event in result["operation_events"]:
            if event["status"].startswith("rejected_"):
                self.assertEqual(event["evidence"], [])

    def test_n14c_blocked_trial_reuses_four_calls_and_scores_third_follow_up(self):
        attempt = ROOT / "outputs/fault-experiments-v2-2-n10/attempt-026"
        trial_id = "trial-f9d31e3979fc2bd1"
        branch_id = "brn-88c93e27dddf60a1"
        manifest = json.loads(
            (attempt / f"controller-manifests/{branch_id}.json").read_text()
        )
        package = json.loads(
            (attempt / manifest["reviewer_package_path"]).read_text()
        )
        catalogue = json.loads(
            (attempt / "catalogues/instance-04.json").read_text()
        )
        call_root = attempt / "ledger/call-attempt"
        before = sha256(
            {
                path.name: sha256(path.read_bytes())
                for path in sorted(call_root.glob("*.json"))
            }
        )

        def reviewer(request, *, controller_parent_id):
            return _normalized_review_response(
                production_reviewer(
                    render_provider_request(
                        request["reviewer_package"],
                        operation_response=request["operation_response"],
                    ),
                    controller_parent_id=controller_parent_id,
                    repo_root=ROOT,
                    attempt_root=attempt,
                )
            )

        with mock.patch(
            "use_case_icp.corrected_experiment.launch_codex_in_branch",
            side_effect=AssertionError("blocked trial must reuse recorded calls"),
        ):
            initial = _normalized_review_response(
                production_reviewer(
                    render_provider_request(package),
                    controller_parent_id=trial_id,
                    repo_root=ROOT,
                    attempt_root=attempt,
                )
            )
            result = run_follow_up_loop(
                catalogue=catalogue,
                package=package,
                initial_response=initial,
                reviewer=reviewer,
                controller_parent_id=trial_id,
            )
        call_ids = [
            call_id
            for record in result["call_records"]
            for call_id in record["call_ids"]
        ]
        self.assertEqual(
            call_ids,
            [
                "call-000-afad315e78a7a2cf",
                "call-000-686fb60cfca8be1c",
                "call-000-4f935b612612788c",
                "call-000-a0b48250d75037e0",
            ],
        )
        third = json.loads(
            (call_root / "call-000-a0b48250d75037e0.json").read_text()
        )["payload"]["result"]["response"]
        self.assertEqual(result["response"]["reviews"], third["reviews"])
        self.assertEqual(result["operation_follow_up_count"], 3)
        self.assertIn(
            "rejected_limit_exhausted",
            {value["status"] for value in result["operation_events"]},
        )
        self.assertEqual(
            before,
            sha256(
                {
                    path.name: sha256(path.read_bytes())
                    for path in sorted(call_root.glob("*.json"))
                }
            ),
        )

    def test_repair_directions_use_explicit_suffix(self):
        self.assertEqual(dependency_suffix(["upstream", "downstream"], "upstream"), ["upstream", "downstream"])
        self.assertEqual(dependency_suffix(["upstream", "downstream"], "downstream"), ["downstream"])

    def test_exact_four_instance_matrix(self):
        catalogues = [
            build_disclosure_catalogue(fixture_capture(instance_id))
            for instance_id in ("instance-01", "instance-04", "instance-03", "instance-12")
        ]
        schedule = experiment_schedule(catalogues)
        self.assertEqual(len(schedule["packages"]), 64)
        self.assertEqual(len(schedule["review_trials"]), 192)
        self.assertEqual(len(schedule["repair_traces"]), 96)

    def test_zero_model_resumable_controller_executes_and_resumes_full_matrix(self):
        captures = {
            instance_id: fixture_capture(instance_id)
            for instance_id in ("instance-01", "instance-04", "instance-03", "instance-12")
        }
        catalogues = {
            instance_id: build_disclosure_catalogue(capture)
            for instance_id, capture in captures.items()
        }
        schedule = experiment_schedule(catalogues.values())
        package_records = []
        for condition in schedule["packages"]:
            reviewer_package = build_review_package(
                catalogues[condition["instance_id"]],
                evidence_mode=condition["evidence_mode"],
                source_setting=condition["source_setting"],
                neutral_base=neutral_base(),
            )
            record = {
                "schema_version": "corrected-four-instance-frozen-package-1",
                "controller_condition": condition,
                "source_capture_sha256": catalogues[condition["instance_id"]]["source_capture_sha256"],
                "catalogue_sha256": catalogues[condition["instance_id"]]["catalogue_sha256"],
                "reviewer_package": reviewer_package,
            }
            record["package_sha256"] = sha256(record)
            package_records.append(record)

        with tempfile.TemporaryDirectory() as temporary:
            attempt = Path(temporary) / "attempt-025"
            for instance_id, catalogue in catalogues.items():
                path = attempt / "catalogues" / f"{instance_id}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(canonical_json(catalogue))
            for record in package_records:
                branch_id = record["controller_condition"]["branch_id"]
                package_path = attempt / "packages" / branch_id / "reviewer-package.json"
                package_path.parent.mkdir(parents=True, exist_ok=True)
                package_path.write_bytes(canonical_json(record["reviewer_package"]))
                manifest = {key: value for key, value in record.items() if key != "reviewer_package"}
                manifest["reviewer_package_path"] = f"packages/{branch_id}/reviewer-package.json"
                manifest["reviewer_package_sha256"] = sha256(record["reviewer_package"])
                manifest_path = attempt / "controller-manifests" / f"{branch_id}.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_bytes(canonical_json(manifest))
            (attempt / "review-design.json").write_bytes(
                canonical_json({"review_trials": schedule["review_trials"]})
            )
            (attempt / "repair-design.json").write_bytes(
                canonical_json({"repair_traces": schedule["repair_traces"]})
            )
            review_calls = 0

            def reviewer(request):
                nonlocal review_calls
                review_calls += 1
                package = request["reviewer_package"]
                decision = "suspect" if review_calls <= 192 else "trusted"
                return {
                    "usage": {"input_tokens": 2, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_tokens": 0, "total_tokens": 3},
                    "reviews": [
                        {
                            "unit_id": boundary_id,
                            "decision": decision,
                            "decision_reason": "deterministic controller qualification",
                            "evidence_refs": [boundary_id],
                            "trust_level": "provisionally_trusted",
                            "criteria_outcomes": [],
                            "boundary_health_acknowledged": True,
                            "expand_helper_prefixes": [],
                            "inspect_artifacts": [],
                            "suspect_node_refs": [],
                        }
                        for boundary_id in package["common_base"]["section"]["assigned_boundary_ids"]
                    ],
                }

            repairer = mock.Mock(
                return_value={
                    "usage": {"input_tokens": 2, "cached_input_tokens": 0, "output_tokens": 1, "reasoning_tokens": 0, "total_tokens": 3},
                    "neutral_base": neutral_base(),
                }
            )
            rerunner = mock.Mock(
                side_effect=lambda catalogue, _repair, _suffix: captures[catalogue["instance_id"]]
            )
            with mock.patch(
                "use_case_icp.corrected_experiment.verify_frozen_attempt",
                return_value={"zero_model_lifecycle": {"status": "passed"}},
            ):
                terminal = execute_resumable_lifecycle(
                    ROOT,
                    attempt,
                    reviewer=reviewer,
                    repairer=repairer,
                    rerunner=rerunner,
                    tester_gate={"qualification_fixture": True},
                )
                self.assertEqual(__import__("json").loads(terminal.read_text())["status"], "completed_experiment_and_analysis")
                self.assertEqual(review_calls, 288)
                self.assertEqual(repairer.call_count, 96)
                self.assertEqual(rerunner.call_count, 96)
                suffix_lengths = {
                    call.args[0]["instance_id"]: len(call.args[2])
                    for call in rerunner.call_args_list
                }
                self.assertEqual(suffix_lengths["instance-04"], 2)
                self.assertEqual(suffix_lengths["instance-03"], 1)
                review_calls_before_resume = review_calls
                repairer.reset_mock()
                rerunner.reset_mock()
                execute_resumable_lifecycle(
                    ROOT,
                    attempt,
                    reviewer=reviewer,
                    repairer=repairer,
                    rerunner=rerunner,
                    tester_gate={"qualification_fixture": True},
                )
                self.assertEqual(review_calls, review_calls_before_resume)
                repairer.assert_not_called()
                rerunner.assert_not_called()

    def test_attempt_024_closes_externally_and_freeze_fails_without_signed_sandbox(self):
        source_freeze = ROOT / "outputs/fault-experiments-v2-2-n10/attempt-023/experiment-freeze.json"
        before = sha256(source_freeze.read_bytes())
        abandoned = ROOT / "outputs/fault-experiments-v2-2-n10/attempt-024"
        abandoned_before = sha256(
            {
                path.relative_to(abandoned).as_posix(): sha256(path.read_bytes())
                for path in sorted(abandoned.rglob("*"))
                if path.is_file()
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            next_attempt = Path(temporary) / "attempt-025"
            closure_path = record_attempt_024_incomplete(ROOT, next_attempt)
            closure = __import__("json").loads(closure_path.read_text())
            self.assertEqual(closure["status"], "terminal_incomplete")
            self.assertEqual(closure["experimental_reviews"], 0)
            self.assertEqual(closure["experimental_repairs"], 0)
            self.assertEqual(closure["experimental_results"], 0)
            with self.assertRaisesRegex(RuntimeError, "zero-model lifecycle"):
                freeze_corrected_attempt(ROOT, next_attempt)
        built = build_corrected_attempt(ROOT)
        self.assertEqual(built["zero_model_lifecycle"]["status"], "terminal_incomplete")
        self.assertEqual(len(built["packages"]), 64)
        self.assertEqual(before, sha256(source_freeze.read_bytes()))
        abandoned_after = sha256(
            {
                path.relative_to(abandoned).as_posix(): sha256(path.read_bytes())
                for path in sorted(abandoned.rglob("*"))
                if path.is_file()
            }
        )
        self.assertEqual(abandoned_before, abandoned_after)


class N15DownstreamFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = build_n15_attempt(ROOT)
        cls.by_condition = {
            (
                value["controller_condition"]["instance_id"],
                value["controller_condition"]["evidence_mode"],
                value["controller_condition"]["source_setting"],
            ): value["reviewer_package"]
            for value in cls.built["packages"]
        }

    def test_n15_build_counts_downstream_scope_and_two_job_graphs(self):
        self.assertEqual(len(self.built["catalogues"]), 4)
        self.assertEqual(len(self.built["packages"]), 64)
        self.assertEqual(len(self.built["schedule"]["review_trials"]), 192)
        self.assertEqual(self.built["schedule"]["repair_traces"], [])
        for record in self.built["packages"]:
            condition = record["controller_condition"]
            package = record["reviewer_package"]
            catalogue = self.built["catalogues"][condition["instance_id"]]
            ids = package["common_base"]["section"]["assigned_boundary_ids"]
            self.assertEqual(len(ids), 6)
            self.assertEqual(len(set(ids)), 6)
            self.assertEqual(
                package["common_base"]["assigned_job"]["job_id"],
                catalogue["job_order"][-1],
            )
            runtime = package.get("runtime_evidence")
            if runtime and runtime["nodes"]:
                self.assertEqual({value["job_id"] for value in runtime["nodes"]}, set(catalogue["job_order"]))
                self.assertEqual(runtime["handoffs"], catalogue["handoffs"])

    def test_n15_treatments_are_isolated_and_combined_random_is_matched(self):
        for instance_id in self.built["catalogues"]:
            for source in ("source_present", "source_absent"):
                fixed = self.by_condition[(instance_id, "etiq_selected_fixed", source)]
                adaptive = self.by_condition[(instance_id, "etiq_selected_adaptive", source)]
                self.assertEqual(canonical_json(fixed["runtime_evidence"]), canonical_json(adaptive["runtime_evidence"]))
                random_package = self.by_condition[(instance_id, "etiq_random_matched", source)]
                match = random_package["runtime_evidence"]["random_match"]
                self.assertEqual(match["scope"], "combined_two_job_pool")
                self.assertTrue(match["node_count_matched"])
                self.assertTrue(match["relationship_count_matched"])
                self.assertEqual(len(self.by_condition[(instance_id, "history_full", source)]["prior_task_records"]), 1)
                self.assertEqual(self.by_condition[(instance_id, "history_empty", source)]["prior_task_records"], [])
            for mode in EVIDENCE_MODES:
                present = self.by_condition[(instance_id, mode, "source_present")]
                absent = self.by_condition[(instance_id, mode, "source_absent")]
                self.assertEqual(
                    {key for key in set(present) | set(absent) if canonical_json(present.get(key)) != canonical_json(absent.get(key))},
                    {"source_bundle"},
                )
                self.assertEqual(_controller_key_paths(render_provider_request(present)), [])
                visible = canonical_json(render_provider_request(present)).decode()
                self.assertNotIn('"mutation"', visible)
                self.assertNotIn('"oracle"', visible)

    def test_n15_helper_expands_each_bound_job_and_suspect_scoring_uses_job_and_id(self):
        catalogue = self.built["catalogues"]["instance-04"]
        package = self.by_condition[("instance-04", "etiq_selected_adaptive", "source_absent")]
        children = package["runtime_evidence"]["collapsed_children"]
        self.assertEqual({value["job_id"] for value in children}, set(catalogue["job_order"]))
        for job_id in catalogue["job_order"]:
            child = next(value for value in children if value["job_id"] == job_id)
            _, event = expand_n15_helper(
                catalogue,
                package,
                {
                    "operation": "helper_expansion",
                    "boundary_id": child["boundary_id"],
                    "prefixes": [child["func_stack"]],
                },
            )
            self.assertEqual(event["resolved_job_id"], job_id)
            self.assertEqual(event["status"], "completed")

        instance = json.loads((ROOT / "outputs/fault-experiments-v2-2-n10/attempt-023/instances/instance-04.json").read_text())
        truth_job = instance["mutation"]["target_job_id"]
        truth_qualified = instance["mutation"]["site"]["qualified_function_name"]
        truth = next(
            binding
            for binding in catalogue["jobs"][truth_job]["boundary_bindings"]
            if binding["frozen_realized_identity"]["qualified_function_name"] == truth_qualified
        )["reviewer_boundary_id"]
        reviews = []
        for boundary_id in package["common_base"]["section"]["assigned_boundary_ids"]:
            reviews.append(
                {
                    "unit_id": boundary_id,
                    "decision": "failed" if boundary_id == truth else "trusted",
                    "decision_reason": "focused N15 validator test",
                    "evidence_refs": [boundary_id],
                    "trust_level": "provisionally_trusted",
                    "criteria_outcomes": [],
                    "boundary_health_acknowledged": True,
                    "expand_helper_prefixes": [],
                    "inspect_artifacts": [],
                    "suspect_node_refs": [],
                }
            )
        validation = validate_n15_reviewer_response(catalogue, package, {"reviews": reviews})
        score = score_n15_top_suspect(catalogue, instance, validation)
        self.assertEqual(validation["selected_job_id"], truth_job)
        self.assertTrue(score["correct_job_localisation"])
        self.assertTrue(score["exact_boundary_localisation"])
        self.assertEqual(score["truth_function_name"], "normalize")


if __name__ == "__main__":
    unittest.main()
