"""Protocol 2.2 Gate-0 qualification built from the parameterized production path."""

from __future__ import annotations

from pathlib import Path
import importlib.metadata
import json
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from .fault_experiment import (
    EVIDENCE_MODES,
    graph_selection_for_mode,
    materialize_branch_package,
    verify_materialized_branch,
)
from .n05_program import (
    _file_contract,
    _fixture_allowlist,
    _tree_contract,
    build_n05_condition_package,
    copy_etiq_worker_runtime,
    derive_review_evidence,
    execute_two_job_chain,
    load_preflight_inputs,
    load_qualification_fixture,
    materialize_opaque_branch,
    run_deterministic_qualification,
)
from .n05_runner import (
    bubblewrap_version,
    canonical_json,
    create_json_exclusive,
    launch_policy_identity,
    sha256_bytes,
    sha256_file,
)
from .random_control import freeze_random_projections


PROTOCOL_ROOT = Path("docs/workshops/neurips-2026-v2-2")
FIXTURE_ROOT = Path(
    "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures"
)
MINIMUM_ROOT = FIXTURE_ROOT / "qualification-minimum"
PREFLIGHT_ROOT = FIXTURE_ROOT / "preflight"


def run_minimum_contract_qualification(
    repo_root: Path, output_root: Path
) -> dict[str, Any]:
    return run_deterministic_qualification(
        repo_root,
        output_root,
        qualification_root=MINIMUM_ROOT,
        preflight_root=PREFLIGHT_ROOT,
    )


def _minimum_execution(repo_root: Path, branch_root: Path) -> tuple[dict, dict, dict]:
    fixture, jobs = load_qualification_fixture(repo_root, MINIMUM_ROOT)
    scenario = load_preflight_inputs(repo_root, PREFLIGHT_ROOT)
    materialize_opaque_branch(
        branch_root,
        allowlist=_fixture_allowlist(repo_root, MINIMUM_ROOT, PREFLIGHT_ROOT),
        manifest_identity={"branch_id": "n06-minimum-package-capture", "purpose": "package_qualification"},
    )
    copy_etiq_worker_runtime(branch_root, repo_root / "src")
    execution = execute_two_job_chain(
        branch_root,
        repo_root=repo_root,
        jobs=jobs,
        scenario=scenario,
        run_index=0,
        stage="n06-package-qualification",
    )
    execution.update(derive_review_evidence(execution, jobs=jobs, scenario=scenario))
    return jobs, scenario, execution


def _package_inputs(
    jobs: Mapping[str, Any],
    scenario: Mapping[str, Any],
    execution: Mapping[str, Any],
    job_id: str,
    branch_index: int,
) -> dict[str, Any]:
    job_ids = list(jobs)
    opaque_jobs = {job_ids[0]: "job-n06up001", job_ids[1]: "job-n06down01"}
    realization = execution["realizations"][job_id]
    boundary_ids = [item["boundary_id"] for item in realization["realized_boundaries"]]
    return {
        "opaque_ids": {
            "instance_id": "ins-n06minimum",
            "condition_id": f"cfg-n06{branch_index:04d}",
            "branch_id": f"brn-n06{branch_index:04d}",
        },
        "review_task": "Detect and localize any behaviorally significant fault in the assigned job.",
        "behavioural_criteria": [
            "preserve the two exact handoffs",
            "produce the required deterministic recommendation",
        ],
        "top_level_input": {"corpus": scenario["corpus"], "capabilities": scenario["capabilities"]},
        "final_output": execution["outputs"][job_ids[1]],
        "assigned_job": {
            "job_id": opaque_jobs[job_id],
            "input": (
                {"corpus": scenario["corpus"]}
                if job_id == job_ids[0]
                else {
                    "needs": execution["outputs"][job_ids[0]]["needs"],
                    "evidence_sources": execution["outputs"][job_ids[0]]["evidence_sources"],
                    "capabilities": scenario["capabilities"],
                }
            ),
            "output": execution["outputs"][job_id],
            "stdout": "",
            "stderr": "",
        },
        "section": {
            "section_id": f"sec-n06{branch_index:04d}",
            "section_index": 0,
            "assigned_boundary_ids": boundary_ids,
            "context_boundary_ids": [],
            "organization": {"kind": "realized_semantic_boundaries"},
        },
        "full_chain_source": [
            {
                "job_id": opaque_jobs[value],
                "files": [
                    {"path": file.path, "content": file.content}
                    for file in jobs[value].files
                ],
            }
            for value in job_ids
        ],
        "history_chain_id": "chn-n06minimum",
        "history": [],
        "controller_job_id_map": opaque_jobs,
    }


def run_minimum_package_qualification(
    repo_root: Path,
    output_root: Path,
    *,
    protocol_content_hash: str,
) -> dict[str, Any]:
    """Materialize every arm/source pair and one legally expanded adaptive pair."""
    output_root.mkdir(parents=True, exist_ok=True)
    jobs, scenario, execution = _minimum_execution(
        repo_root, output_root / "capture-branch"
    )
    handoffs = [
        {
            "handoff_ref": item["handoff_id"],
            "upstream_job_id": item["upstream_job_id"],
            "downstream_job_id": item["downstream_job_id"],
            "artifact_sha256": item["producer_sha256"],
        }
        for item in execution["handoffs"]
    ]
    instance_id = "ins-n06minimum"
    projections: dict[str, dict[str, dict[str, Any]]] = {}
    random_roots = output_root / "random-projections"
    for job_id, realization in execution["realizations"].items():
        snapshot = execution["executions"][job_id].snapshot
        boundaries = realization["realized_boundaries"]
        job_projections: dict[str, dict[str, Any]] = {}
        for mode in ("etiq_full", "etiq_selected_fixed", "etiq_selected_adaptive"):
            value = graph_selection_for_mode(
                mode,
                snapshot,
                boundaries,
                handoffs=handoffs,
                include_projection_binding=True,
            )
            assert value is not None
            job_projections[mode] = value
        frozen_random = freeze_random_projections(
            random_roots / job_id,
            snapshot,
            boundaries,
            job_projections["etiq_selected_fixed"],
            instance_id=instance_id,
            handoffs=handoffs,
            protocol_content_hash=protocol_content_hash,
        )
        random_projection = graph_selection_for_mode(
            "etiq_random_matched",
            snapshot,
            boundaries,
            handoffs=handoffs,
            frozen_random_by_boundary=frozen_random,
            random_instance_id=instance_id,
            random_protocol_content_hash=protocol_content_hash,
            include_projection_binding=True,
        )
        assert random_projection is not None
        job_projections["etiq_random_matched"] = random_projection
        owned_helpers = [
            item for item in execution["helpers"] if item["job_id"] == job_id
        ]
        if owned_helpers:
            expanded = {
                item["boundary_id"]: [
                    helper["helper_prefix"]
                    for helper in owned_helpers
                    if helper["boundary_id"] == item["boundary_id"]
                ]
                for item in owned_helpers
            }
            value = graph_selection_for_mode(
                "etiq_selected_adaptive",
                snapshot,
                boundaries,
                handoffs=handoffs,
                expanded_prefixes_by_boundary=expanded,
                include_projection_binding=True,
            )
            assert value is not None
            job_projections["etiq_selected_adaptive_expanded"] = value
        projections[job_id] = job_projections

    materialized: list[dict[str, Any]] = []
    branch_index = 0
    for job_id, realization in execution["realizations"].items():
        snapshot = execution["executions"][job_id].snapshot
        for mode in EVIDENCE_MODES:
            for source_setting in ("source_present", "source_absent"):
                branch_index += 1
                package_inputs = _package_inputs(
                    jobs, scenario, execution, job_id, branch_index
                )
                controller_job_id_map = package_inputs.pop("controller_job_id_map")
                package, manifest = build_n05_condition_package(
                    protocol_content_hash=protocol_content_hash,
                    protocol_version="2.2.0",
                    evidence_mode=mode,
                    source_setting=source_setting,
                    snapshot=snapshot,
                    realization=realization,
                    handoffs=execution["handoffs"],
                    frozen_projection=projections[job_id].get(mode),
                    controller_job_id_map=controller_job_id_map,
                    **package_inputs,
                )
                branch = output_root / "packages" / f"branch-{branch_index:03d}"
                materialize_branch_package(branch, package, manifest)
                verified = verify_materialized_branch(branch)
                materialized.append(
                    {
                        "job_id": job_id,
                        "evidence_mode": mode,
                        "source_setting": source_setting,
                        "package_sha256": manifest["package_sha256"],
                        "manifest_content_sha256": manifest["manifest_content_sha256"],
                        "projection_sha256": manifest.get("canonical_projection", {}).get("projection_sha256"),
                        "runtime_graph_sha256": manifest.get("runtime_graph_sha256"),
                        "verified": verified["verified"],
                    }
                )
        if "etiq_selected_adaptive_expanded" in projections[job_id]:
            for source_setting in ("source_present", "source_absent"):
                branch_index += 1
                package_inputs = _package_inputs(jobs, scenario, execution, job_id, branch_index)
                controller_job_id_map = package_inputs.pop("controller_job_id_map")
                package, manifest = build_n05_condition_package(
                    protocol_content_hash=protocol_content_hash,
                    protocol_version="2.2.0",
                    evidence_mode="etiq_selected_adaptive",
                    source_setting=source_setting,
                    snapshot=snapshot,
                    realization=realization,
                    handoffs=execution["handoffs"],
                    frozen_projection=projections[job_id]["etiq_selected_adaptive_expanded"],
                    controller_job_id_map=controller_job_id_map,
                    **package_inputs,
                )
                branch = output_root / "packages" / f"branch-{branch_index:03d}"
                materialize_branch_package(branch, package, manifest)
                verify_materialized_branch(branch)
                materialized.append(
                    {
                        "job_id": job_id,
                        "evidence_mode": "etiq_selected_adaptive_expanded",
                        "source_setting": source_setting,
                        "package_sha256": manifest["package_sha256"],
                        "manifest_content_sha256": manifest["manifest_content_sha256"],
                        "projection_sha256": manifest["canonical_projection"]["projection_sha256"],
                        "runtime_graph_sha256": manifest["runtime_graph_sha256"],
                        "verified": True,
                    }
                )
    report = {
        "schema_version": "1",
        "protocol_version": "2.2.0",
        "package_count": len(materialized),
        "all_modes": sorted({item["evidence_mode"] for item in materialized}),
        "all_source_settings": sorted({item["source_setting"] for item in materialized}),
        "packages": materialized,
    }
    create_json_exclusive(output_root / "minimum-package-qualification.json", report)
    return report


def build_n06_design_freeze(
    repo_root: Path,
    output_root: Path,
    *,
    freeze_name: str = "n06-design-freeze.json",
    supersedes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Exclusive-create the exact N06 Gate-0 binding after every check passes."""
    authority = repo_root / (
        "instructions_between_agent_types/overseer/decisions/"
        "N06_v2_2_projection_correction_and_experiment_completion_authorization.json"
    )
    expected_authority = "sha256:71e769ea20900179cebbb1dd4909d6e1d6e0512cb86d7f424609baa413c2b6a2"
    if sha256_file(authority) != expected_authority:
        raise ValueError("N06 controlling authorization hash mismatch")
    protocol_path = repo_root / PROTOCOL_ROOT / "experiment-protocol.json"
    markdown_path = repo_root / PROTOCOL_ROOT / "EXPERIMENT_PROTOCOL.md"
    protocol = json.loads(protocol_path.read_text())
    embedded = markdown_path.read_text().split("```json\n", 1)[1].rsplit("```", 1)[0]
    if protocol_path.read_text() != embedded or protocol["protocol_version"] != "2.2.0":
        raise ValueError("N06 protocol pair is not the exact frozen 2.2.0 design")
    test_outputs = {
        name: output_root / "test-outputs" / name
        for name in (
            "focused-v2-2.txt",
            "all-v2-v2-1-v2-2.txt",
            "all-real-etiq.txt",
            "complete-discovery.txt",
        )
    }
    for path in test_outputs.values():
        text = path.read_text()
        if "FAILED" in text or "skipped=" in text or "NO TESTS RAN" in text or not text.rstrip().endswith("OK"):
            raise ValueError(f"N06 test output is not a zero-skip pass: {path.name}")
    complete_text = test_outputs["complete-discovery.txt"].read_text()
    if "Ran 295 tests" not in complete_text:
        raise ValueError("N06 complete discovery count changed")
    qualification_root = output_root / "qualification"
    minimum = json.loads(
        (qualification_root / "minimum-contract/deterministic-qualification.json").read_text()
    )
    packages = json.loads(
        (qualification_root / "packages/minimum-package-qualification.json").read_text()
    )
    if (
        minimum["observed_counts"]["realized_boundaries"] != 12
        or len(minimum["helpers"]) != 2
        or minimum["qualification"]["selected_to_full_ratio"] > 0.90
        or packages["package_count"] != 26
    ):
        raise ValueError("N06 minimum qualification result changed")
    from .n05_analysis import expected_design

    design = expected_design()
    governed_source = [
        "src/use_case_icp/fault_experiment.py",
        "src/use_case_icp/fault_v21.py",
        "src/use_case_icp/random_control.py",
        "src/use_case_icp/n05_program.py",
        "src/use_case_icp/n06_program.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/fault_operations.py",
        "src/use_case_icp/fault_injection.py",
        "src/use_case_icp/fault_v2.py",
        "src/use_case_icp/fault_preflight_v2.py",
        "src/use_case_icp/records.py",
        "src/use_case_icp/workflow.py",
        "src/use_case_icp/n05_analysis.py",
        "scripts/build_n06_protocol.py",
    ]
    freeze = {
        "schema_version": "1",
        "gate": "G0-protocol-projection-package-correction-and-design-freeze",
        "status": "pre_results_frozen",
        "protocol_id": protocol["protocol_id"],
        "protocol_version": "2.2.0",
        "scientific_model_calls": 0,
        "reviewer_calls": 0,
        "repair_calls": 0,
        "experimental_instances": 0,
        "experimental_packages": 0,
        "experimental_outcomes": 0,
        "controlling_authority": _file_contract(repo_root, authority),
        "protocol": {
            "content_hash": protocol["integrity"]["content_hash"],
            "json": _file_contract(repo_root, protocol_path),
            "markdown": _file_contract(repo_root, markdown_path),
            "archive_2_1_0": _tree_contract(repo_root, repo_root / PROTOCOL_ROOT / "archive/protocol-2.1.0"),
        },
        "preservation": {
            "baseline": _file_contract(repo_root, output_root / "n05-preservation-baseline.json"),
            "candidate_3_controller_audit": _file_contract(repo_root, output_root / "n05-candidate-3-controller-regression-audit.json"),
            "immutable_n05_file_count": 4235,
            "immutable_n05_total_bytes": 584548303,
        },
        "prompt_namespace": _tree_contract(repo_root, repo_root / "prompts/v2_2"),
        "schema_namespace": _tree_contract(repo_root, repo_root / "schemas/v2_2"),
        "fresh_inputs_and_fixtures": _tree_contract(repo_root, repo_root / FIXTURE_ROOT),
        "seeds": {"authoring": 26082951, "mutation": 260829107},
        "canonical_projection": {
            "selected_graph_evidence_bytes": minimum["qualification"]["selected_graph_evidence_bytes"],
            "full_graph_evidence_bytes": minimum["qualification"]["full_graph_evidence_bytes"],
            "selected_to_full_ratio": minimum["qualification"]["selected_to_full_ratio"],
            "projection_hashes": minimum["qualification"]["projection_hashes"],
            "helper_ownership": [
                {
                    "job_id": item["job_id"],
                    "boundary_id": item["boundary_id"],
                    "helper_prefix": item["helper_prefix"],
                    "incremental_node_count": len(item["incremental_node_refs"]),
                    "incremental_relationship_count": len(item["incremental_relationship_refs"]),
                }
                for item in minimum["helpers"]
            ],
        },
        "package_qualification": {
            "report": _file_contract(repo_root, qualification_root / "packages/minimum-package-qualification.json"),
            "package_count": packages["package_count"],
            "modes": packages["all_modes"],
            "source_settings": packages["all_source_settings"],
            "package_bindings": packages["packages"],
        },
        "qualification_records": {
            "minimum": _file_contract(repo_root, qualification_root / "minimum-contract/deterministic-qualification.json"),
            "operators": _file_contract(repo_root, qualification_root / "operators/operator-qualification.json"),
            "legacy_negatives": _file_contract(repo_root, qualification_root / "legacy-negatives/negative-qualifications.json"),
            "isolation": _file_contract(repo_root, qualification_root / "isolation/isolation-dry-run.json"),
            "recorder_and_two_subtraces": _file_contract(repo_root, qualification_root / "operational/operational-dry-run.json"),
            "analysis_and_replay": _tree_contract(repo_root, qualification_root / "replay"),
        },
        "source": [_file_contract(repo_root, repo_root / path) for path in governed_source],
        "tests": _tree_contract(repo_root, repo_root / "tests"),
        "test_outputs": {name: _file_contract(repo_root, path) for name, path in test_outputs.items()},
        "environment": {
            "python": sys.version.split()[0],
            "python_executable": str(Path(sys.executable).resolve()),
            "etiq_copilot": importlib.metadata.version("etiq-copilot"),
            "bubblewrap": bubblewrap_version(),
        },
        "runner_launcher_sandbox": launch_policy_identity(),
        "expected_design": {
            "design_sha256": design["design_sha256"],
            "counts": design["expected_counts"],
            "trial_seeds": [104729, 130363, 155921],
        },
        "future_materialization_contract": {
            "phase_a_candidate_limit": 3,
            "phase_a_stabilization_cycles_per_candidate": 3,
            "phase_b_subtraces": 2,
            "instances": 12,
            "captures": 12,
            "packages": 96,
            "review_trials": 288,
            "repair_traces": 180,
            "post_signature_change": "experiment_incomplete",
        },
        "supersession": dict(supersedes or {}),
    }
    if freeze["environment"]["python"] != "3.12.3" or freeze["environment"]["etiq_copilot"] != "2.3.0":
        raise ValueError("N06 frozen environment version changed")
    freeze["freeze_sha256"] = sha256_bytes(canonical_json(freeze))
    if Path(freeze_name).name != freeze_name:
        raise ValueError("N06 design freeze name must be one file name")
    create_json_exclusive(output_root / freeze_name, freeze)
    return freeze
