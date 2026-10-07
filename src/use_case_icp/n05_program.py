"""N05-specific qualification and experiment orchestration functions."""

from __future__ import annotations

from copy import deepcopy
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Mapping

from .etiq_executor import EtiqExecution
from .fault_v2 import (
    freeze_reverse_ordering_order_v2,
    inject_reverse_ordering_v2,
)
from .fault_injection import normalize_pipeline
from .fault_v21 import (
    eligible_direct_child_helpers,
    enrich_snapshot_identities,
    graph_size_report,
    materialize_realized_boundaries,
    parse_generated_pipeline,
    qualify_realized_chain,
    resolve_static_identity,
    freeze_operator_site_order,
    inject_operator_exact,
)
from .job_store import JobStore
from .fault_operations import (
    append_operation_event,
    recalculate_exact_hash_handoffs,
    recompute_resume_outcome,
    two_job_suffix_rerun_job_ids,
    validate_boundary_sized_repair,
)
from .fault_experiment import (
    build_fault_review_package,
    graph_selection_for_mode,
    verify_canonical_graph_projection,
)
from .repair import source_scope
from .n05_runner import (
    append_record,
    canonical_json,
    copy_codex_auth,
    codex_permission_profile_probe_command,
    copy_etiq_worker_runtime,
    create_json_exclusive,
    create_bytes_exclusive,
    etiq_worker_bubblewrap_command,
    materialize_opaque_branch,
    sha256_bytes,
    stable_id,
    run_python_in_branch,
    codex_control_plane_bubblewrap_command,
    codex_bubblewrap_command,
    bubblewrap_version,
    launch_policy_identity,
    launch_codex_in_branch,
    run_with_identical_retries,
    sha256_file,
    validate_signed_tester_gate,
)
from .records import (
    AgentRequest,
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    GeneratedFile,
    GeneratedPipeline,
    RootJobState,
    jsonable,
)


QUALIFICATION_ROOT = Path(
    "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/qualification"
)
PREFLIGHT_ROOT = Path(
    "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight"
)
N05_AUTHORITY_SHA256 = (
    "sha256:2928e57ecd8423365a53758424282b07928727bade71f8ff4fb1ce205df43a95"
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_qualification_fixture(
    repo_root: Path,
    qualification_root: Path = QUALIFICATION_ROOT,
) -> tuple[dict[str, Any], dict[str, GeneratedPipeline]]:
    fixture_root = repo_root / qualification_root
    fixture = _load_json(fixture_root / "fixture.json")
    jobs: dict[str, GeneratedPipeline] = {}
    for job_id in fixture["job_ids"]:
        specification = fixture["jobs"][job_id]
        source_path = fixture_root / specification["source_file"]
        payload = {
            "entry_file": specification["entry_file"],
            "files": [
                {"path": specification["entry_file"], "content": source_path.read_text()}
            ],
            "review_boundaries": specification["review_boundaries"],
        }
        parsed = parse_generated_pipeline(job_id, payload)
        jobs[job_id] = parse_generated_pipeline(
            job_id, _pipeline_payload(normalize_pipeline(parsed))
        )
    if tuple(jobs) != tuple(fixture["job_ids"]):
        raise ValueError("qualification fixture job order changed")
    return fixture, jobs


def load_preflight_inputs(
    repo_root: Path, preflight_root: Path = PREFLIGHT_ROOT
) -> dict[str, Any]:
    root = repo_root / preflight_root
    scenario = _load_json(root / "scenario.json")
    corpus = _load_json(root / scenario["corpus_path"])
    capabilities = _load_json(root / scenario["capability_catalogue_path"])
    oracles = _load_json(root / scenario["oracle_path"])
    scenario["corpus"] = corpus["records"]
    scenario["capabilities"] = capabilities["capabilities"]
    scenario["oracles"] = oracles
    return scenario


def validate_n05_model_response_schemas(repo_root: Path) -> dict[str, str]:
    from .fault_preflight_v2 import validate_strict_provider_schema

    names = (
        "fault_chain_authoring.schema.json",
        "fault_chain_stabilization.schema.json",
        "fault_review_receipt.schema.json",
        "fault_repair_response.schema.json",
    )
    result = {}
    for name in names:
        path = repo_root / "schemas/v2_1" / name
        validate_strict_provider_schema(_load_json(path), path.relative_to(repo_root).as_posix())
        result[name] = sha256_file(path)
    return result


def consume_gate_2_phase_a_authority(
    repo_root: Path,
    output_root: Path,
    *,
    tester_gate_path: Path,
    design_freeze_name: str = "n05-design-freeze.json",
) -> dict[str, Any]:
    """Atomically consume the one fresh N05 Phase-A candidate set before its first call."""
    if Path(design_freeze_name).name != design_freeze_name:
        raise ValueError("N05 design freeze name must be one file name")
    freeze_path = output_root / design_freeze_name
    gate = validate_signed_tester_gate(freeze_path, tester_gate_path)
    authority = repo_root / (
        "instructions_between_agent_types/overseer/decisions/"
        "N05_v2_1_end_to_end_completion_program_authorization.json"
    )
    if sha256_file(authority) != N05_AUTHORITY_SHA256:
        raise ValueError("N05 authority changed before Phase A")
    consumption = {
        "schema_version": "1",
        "status": "consumed_in_progress",
        "gate": "G2_one_use_model_phase_a",
        "candidate_sets_consumed": 1,
        "maximum_candidates": 3,
        "maximum_stabilization_cycles_per_candidate": 3,
        "provider_attempts_per_logical_request": 3,
        "reviewer_model_calls_authorized": 0,
        "authoring_seed": 26082941,
        "mutation_seed": 26082997,
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "authority_sha256": N05_AUTHORITY_SHA256,
        "design_freeze_sha256": sha256_file(freeze_path),
        "tester_gate_sha256": sha256_file(tester_gate_path),
        "tester_signature": gate["tester_signature"],
    }
    path = output_root / "gate-2/phase-a-authority-consumption.json"
    digest = create_json_exclusive(path, consumption)
    return {**consumption, "record_sha256": digest}


def run_isolated_codex_request(
    repo_root: Path,
    output_root: Path,
    *,
    parent_id: str,
    call_class: str,
    prompt: str,
    schema_name: str,
    source_codex_home: Path | None = None,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Execute a fresh isolated Codex request with exact-byte infrastructure retries."""
    if not (output_root / "gate-2/phase-a-authority-consumption.json").is_file():
        raise RuntimeError("N05 model request requires consumed Gate-2 authority")
    validate_n05_model_response_schemas(repo_root)
    request_root = output_root / "gate-2/requests" / parent_id / call_class
    prompt_path = request_root / "prompt.md"
    create_bytes_exclusive(prompt_path, prompt.encode())
    schema_path = repo_root / "schemas/v2_1" / schema_name
    codex_path = Path(shutil.which("codex") or "").resolve(strict=True)
    codex_runtime = codex_path.parent.parent
    codex_home = source_codex_home or Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    )
    attempt_index = 0

    def launch(call_id: str, _request_bytes: bytes) -> Mapping[str, Any]:
        nonlocal attempt_index
        branch_id = stable_id("branch", [parent_id, call_class, call_id], attempt_index)
        branch = output_root / "gate-2/model-branches" / branch_id
        materialize_opaque_branch(
            branch,
            allowlist={"prompt.md": prompt_path, "schema.json": schema_path},
            manifest_identity={"branch_id": branch_id, "call_id": call_id},
        )
        copy_codex_auth(branch, source_codex_home=codex_home)
        result = launch_codex_in_branch(
            branch,
            codex_runtime_root=codex_runtime,
            prompt_file="prompt.md",
            schema_file="schema.json",
            output_file="response.json",
            timeout_seconds=timeout_seconds,
        )
        attempt_index += 1
        return {**result, "branch_id": branch_id}

    return run_with_identical_retries(
        output_root / "ledger",
        parent_id=parent_id,
        call_class=call_class,
        logical_request={
            "prompt": prompt,
            "schema_sha256": sha256_file(schema_path),
            "model": "gpt-5.5",
            "reasoning_effort": "high",
        },
        launch=launch,
    )


def _load_snapshot(store: JobStore, run_dir: Path) -> EtiqEvidenceSnapshot:
    summary = store.read_json(run_dir / "etiq-snapshot.json")
    return EtiqEvidenceSnapshot(
        snapshot_id=str(summary["snapshot_id"]),
        job_id=str(summary["job_id"]),
        run_id=str(summary["run_id"]),
        nodes=[
            EtiqNodeRecord(**item)
            for item in store.read_json(run_dir / "etiq-nodes.json", [])
        ],
        relationships=[
            EtiqRelationshipRecord(**item)
            for item in store.read_json(run_dir / "etiq-relationships.json", [])
        ],
        inventories=store.read_json(run_dir / "etiq-inventory.json", {}),
        scan_errors=store.read_json(run_dir / "etiq-scan-errors.json", []),
        created_at=str(summary["created_at"]),
        schema_version=str(summary["schema_version"]),
    )


def execute_pipeline_in_branch(
    branch_root: Path,
    *,
    repo_root: Path,
    job_id: str,
    pipeline: GeneratedPipeline,
    runtime_input: Mapping[str, Any],
    run_index: int,
    stage: str,
) -> EtiqExecution:
    """Execute real Etiq through the production network-unshared worker path."""
    if importlib.metadata.version("etiq-copilot") != "2.3.0":
        raise RuntimeError("N05 requires etiq-copilot==2.3.0")
    store = JobStore(branch_root / "jobstore")
    if not store.job_dir(job_id).exists():
        store.initialize_job(
            AgentRequest("N05 qualification", "controlled engineering fixture"),
            RootJobState(job_id),
        )
    run_id = stable_id("capture-attempt", [job_id, stage], run_index)
    run_dir = store.stage_run_dir(job_id, "n05", stage, run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "pipeline-stdout.log").write_text("")
    (run_dir / "pipeline-stderr.log").write_text("")
    manifest = store.materialize_pipeline(run_dir, pipeline)
    store.write_json(run_dir / "pipeline-input.json", runtime_input)
    relative_run = run_dir.relative_to(store.output_root)
    worker_request = {
        "output_root": "/jobstore",
        "run_dir": f"/jobstore/{relative_run.as_posix()}",
        "job_id": job_id,
        "run_id": run_id,
        "entry_file": pipeline.entry_file,
        "manifest_hash": manifest["manifest_hash"],
        "memory_limit_mb": 0,
        "cpu_limit_seconds": 0,
        "network_mode": None,
        "network_cassette_path": None,
    }
    request_path = run_dir / "worker-request.json"
    store.write_json(request_path, worker_request)
    request_relative = request_path.relative_to(store.output_root).as_posix()
    command = etiq_worker_bubblewrap_command(
        branch_root,
        venv_root=repo_root / ".venv",
        request_relative_path=request_relative,
    )
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=1800,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        close_fds=True,
    )
    (run_dir / "worker-launch-stdout.log").write_text(completed.stdout)
    (run_dir / "worker-launch-stderr.log").write_text(completed.stderr)
    if completed.returncode != 0:
        detail = store.read_json(run_dir / "execution-error.json", {})
        raise RuntimeError(
            "N05 Bubblewrap Etiq worker failed: "
            + str(detail.get("message") or completed.stderr.strip())
        )
    snapshot = _load_snapshot(store, run_dir)
    if snapshot.scan_errors or not snapshot.nodes:
        raise ValueError("N05 real-Etiq capture is not reviewable")
    return EtiqExecution(snapshot=snapshot, run_dir=run_dir)


def _parse_output(execution: EtiqExecution) -> dict[str, Any]:
    raw = (execution.run_dir / "pipeline-stdout.log").read_text().strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("N05 job stdout is not exactly one JSON object") from error
    if not isinstance(value, dict):
        raise ValueError("N05 job result must be one JSON object")
    return value


def oracle_report(
    upstream: Mapping[str, Any], downstream: Mapping[str, Any], oracles: Mapping[str, Any]
) -> dict[str, Any]:
    checks = {
        "upstream_schema": set(upstream) == set(oracles["upstream"]["required_output_fields"]),
        "upstream_count": len(upstream.get("needs", []))
        >= int(oracles["upstream"]["required_need_count"]),
        "upstream_records": set(oracles["upstream"]["required_record_ids"])
        <= {str(item.get("record_id")) for item in upstream.get("needs", [])},
        "downstream_schema": set(downstream)
        == set(oracles["downstream"]["required_output_fields"]),
        "downstream_count": len(downstream.get("priorities", []))
        >= int(oracles["downstream"]["required_priority_count"]),
        "top_need": downstream.get("recommendation", {}).get("top_need")
        == oracles["downstream"]["required_top_need"],
        "decision": downstream.get("recommendation", {}).get("decision")
        == oracles["end_to_end"]["recommendation_decision"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failed_check_names": sorted(name for name, passed in checks.items() if not passed),
    }


def execute_two_job_chain(
    branch_root: Path,
    *,
    repo_root: Path,
    jobs: Mapping[str, GeneratedPipeline],
    scenario: Mapping[str, Any],
    run_index: int,
    stage: str,
) -> dict[str, Any]:
    """Execute both jobs and return only runtime outputs, captures, handoffs, and oracle."""
    job_ids = tuple(jobs)
    if len(job_ids) != 2:
        raise ValueError("N05 execution requires exactly two ordered jobs")
    upstream_id, downstream_id = job_ids
    upstream_execution = execute_pipeline_in_branch(
        branch_root,
        repo_root=repo_root,
        job_id=upstream_id,
        pipeline=jobs[upstream_id],
        runtime_input={"corpus": scenario["corpus"]},
        run_index=run_index,
        stage=f"{stage}-upstream",
    )
    upstream_output = _parse_output(upstream_execution)
    required_upstream_keys = set(scenario["oracles"]["upstream"]["required_output_fields"])
    if set(upstream_output) != required_upstream_keys:
        raise ValueError("N05 upstream output keys do not exactly match the runtime contract")
    downstream_input = {
        "needs": upstream_output.get("needs"),
        "evidence_sources": upstream_output.get("evidence_sources"),
        "capabilities": scenario["capabilities"],
    }
    handoffs: list[dict[str, Any]] = []
    for artifact in ("needs", "evidence_sources"):
        producer_hash = sha256_bytes(canonical_json(upstream_output.get(artifact)))
        consumer_hash = sha256_bytes(canonical_json(downstream_input.get(artifact)))
        handoffs.append(
            {
                "handoff_id": f"handoff-{artifact.replace('_', '-')}",
                "upstream_job_id": upstream_id,
                "downstream_job_id": downstream_id,
                "artifact_name": artifact,
                "producer_sha256": producer_hash,
                "consumer_sha256": consumer_hash,
                "provenance_type": "controller_recorded_exact_hash_handoff",
                "etiq_runtime_edge": False,
            }
        )
    downstream_execution = execute_pipeline_in_branch(
        branch_root,
        repo_root=repo_root,
        job_id=downstream_id,
        pipeline=jobs[downstream_id],
        runtime_input=downstream_input,
        run_index=run_index,
        stage=f"{stage}-downstream",
    )
    downstream_output = _parse_output(downstream_execution)
    required_downstream_keys = set(
        scenario["oracles"]["downstream"]["required_output_fields"]
    )
    if set(downstream_output) != required_downstream_keys:
        raise ValueError("N05 downstream output keys do not exactly match the runtime contract")
    executions = {
        upstream_id: upstream_execution,
        downstream_id: downstream_execution,
    }
    if any(item["producer_sha256"] != item["consumer_sha256"] for item in handoffs):
        raise ValueError("N05 exact-hash handoff validation failed")
    oracle = oracle_report(upstream_output, downstream_output, scenario["oracles"])
    return {
        "executions": executions,
        "outputs": {upstream_id: upstream_output, downstream_id: downstream_output},
        "handoffs": handoffs,
        "oracle": oracle,
    }


def derive_review_evidence(
    execution: Mapping[str, Any],
    *,
    jobs: Mapping[str, GeneratedPipeline],
    scenario: Mapping[str, Any],
    simple_boundary_matching: bool = False,
) -> dict[str, Any]:
    """Derive realized boundaries, helpers, and graph projections from captures."""
    realizations: dict[str, Any] = {}
    helpers: list[dict[str, Any]] = []
    size_reports: list[dict[str, Any]] = []
    for job_id, pipeline in jobs.items():
        snapshot = execution["executions"][job_id].snapshot
        if simple_boundary_matching:
            realization = _materialize_simple_realized_boundaries(
                snapshot,
                pipeline.review_boundaries,
                job_id=job_id,
                pipeline=pipeline,
            )
        else:
            snapshot = enrich_snapshot_identities(
                snapshot, job_id=job_id, pipeline=pipeline
            )
            execution["executions"][job_id].snapshot = snapshot
            realization = materialize_realized_boundaries(
                snapshot,
                pipeline.review_boundaries,
                job_id=job_id,
                pipeline=pipeline,
            )
        realizations[job_id] = realization
        helpers.extend(
            {**item, "job_id": job_id}
            for item in eligible_direct_child_helpers(
                snapshot, realization["realized_boundaries"]
            )
        )
        size_reports.append(
            graph_size_report(
                snapshot,
                realization["realized_boundaries"],
                protocol_version=str(scenario.get("protocol_version") or "2.1.0"),
            )
        )
    return {
        "realizations": realizations,
        "helpers": helpers,
        "graph_size_reports": size_reports,
    }


def _stack_names(stack: list[str]) -> tuple[str, ...]:
    return tuple(str(value).split(",", 1)[0] for value in stack)


def _materialize_simple_realized_boundaries(
    snapshot: EtiqEvidenceSnapshot,
    declarations: list[Mapping[str, Any]],
    *,
    job_id: str,
    pipeline: GeneratedPipeline,
) -> dict[str, Any]:
    """Match Phase-A declarations directly to observed function stacks."""
    if snapshot.job_id != job_id:
        raise ValueError("Phase-A boundary capture belongs to the wrong job")
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    if len(node_by_ref) != len(snapshot.nodes):
        raise ValueError("Phase-A capture contains duplicate node references")
    realized = []
    unmatched = []
    seen_ids: set[str] = set()
    for declaration in declarations:
        boundary_id = str(declaration["boundary_id"])
        if boundary_id in seen_ids:
            raise ValueError("Phase-A boundary IDs must be unique")
        seen_ids.add(boundary_id)
        identity = resolve_static_identity(
            job_id,
            pipeline,
            source_path=str(declaration["source_path"]),
            qualified_function_name=str(declaration["qualified_function_name"]),
        )
        expected_suffix = tuple(identity["qualified_function_name"].split("."))
        matched_prefixes = sorted(
            {
                _stack_names(node.func_stack)
                for node in snapshot.nodes
                if _stack_names(node.func_stack)[-len(expected_suffix) :] == expected_suffix
            }
        )
        if not matched_prefixes:
            unmatched.append(
                {
                    "boundary_id": boundary_id,
                    "static_identity": identity,
                    "semantic_stage": declaration["semantic_stage"],
                    "reason": "no_observed_function_stack",
                }
            )
            continue
        inside_refs = {
            node.node_ref
            for node in snapshot.nodes
            if any(
                _stack_names(node.func_stack)[: len(prefix)] == prefix
                for prefix in matched_prefixes
            )
        }
        relationships = {
            edge.relationship_ref
            for edge in snapshot.relationships
            if edge.source_ref in inside_refs or edge.target_ref in inside_refs
        }
        input_refs = {
            edge.relationship_ref
            for edge in snapshot.relationships
            if edge.source_ref not in inside_refs and edge.target_ref in inside_refs
        }
        output_refs = {
            edge.relationship_ref
            for edge in snapshot.relationships
            if edge.source_ref in inside_refs and edge.target_ref not in inside_refs
        }
        helper_prefixes = sorted(
            {
                stack[:depth]
                for node in snapshot.nodes
                for stack in [_stack_names(node.func_stack)]
                for prefix in matched_prefixes
                if stack[: len(prefix)] == prefix
                for depth in range(len(prefix) + 1, len(stack) + 1)
            },
            key=lambda value: (len(value), value),
        )
        function_refs = sorted(
            node.node_ref
            for node in snapshot.nodes
            if _stack_names(node.func_stack) in matched_prefixes
        )
        boundary = {
            "boundary_id": boundary_id,
            "semantic_stage": str(declaration["semantic_stage"]),
            "role": str(declaration.get("role") or ""),
            "expected_inputs": list(declaration.get("expected_inputs", [])),
            "expected_outputs": list(declaration.get("expected_outputs", [])),
            "static_identity": identity,
            "function_name": identity["qualified_function_name"].split(".")[-1],
            "matched_prefix": list(matched_prefixes[0]),
            "matched_prefixes": [list(prefix) for prefix in matched_prefixes],
            "prefix_multiplicity": len(matched_prefixes),
            "matched_function_node_refs": function_refs,
            "matched_function_node_ref": function_refs[0],
            "node_refs": sorted(inside_refs),
            "relationship_refs": sorted(relationships),
            "input_relationship_refs": sorted(input_refs),
            "output_relationship_refs": sorted(output_refs),
            "helper_prefixes": [list(prefix) for prefix in helper_prefixes],
        }
        boundary["realized_boundary_sha256"] = sha256_bytes(canonical_json(boundary))
        realized.append(boundary)
    audit = {
        "job_id": job_id,
        "realized_boundary_count": len(realized),
        "unmatched_declaration_count": len(unmatched),
        "unmatched_declarations": unmatched,
    }
    audit["audit_sha256"] = sha256_bytes(canonical_json(audit))
    return {
        "realized_boundaries": sorted(realized, key=lambda value: value["boundary_id"]),
        "boundary_realization_audit": audit,
    }


def _pipeline_payload(pipeline: GeneratedPipeline) -> dict[str, Any]:
    return {
        "entry_file": pipeline.entry_file,
        "files": [jsonable(item) for item in pipeline.files],
        "review_boundaries": [
            {
                key: value
                for key, value in boundary.items()
                if key
                in {
                    "boundary_id",
                    "source_path",
                    "qualified_function_name",
                    "semantic_stage",
                    "role",
                    "expected_inputs",
                    "expected_outputs",
                }
            }
            for boundary in pipeline.review_boundaries
        ],
    }


def build_n05_condition_package(
    *,
    protocol_content_hash: str,
    evidence_mode: str,
    source_setting: str,
    snapshot: EtiqEvidenceSnapshot,
    realization: Mapping[str, Any],
    handoffs: list[Mapping[str, Any]],
    random_selection: Mapping[str, Any] | None = None,
    frozen_projection: Mapping[str, Any] | None = None,
    expanded_prefixes_by_boundary: Mapping[
        str, list[list[str]]
    ] | None = None,
    controller_job_id_map: Mapping[str, str] | None = None,
    protocol_version: str = "2.1.0",
    **package_inputs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one package from a frozen canonical endpoint-complete projection."""
    if source_setting not in {"source_present", "source_absent"}:
        raise ValueError("N05 source setting is invalid")
    boundaries = [dict(item) for item in realization["realized_boundaries"]]
    if not boundaries:
        raise ValueError("N05 package requires realized boundaries")
    boundary_ids = {
        str(item["boundary_id"]): "bnd-"
        + sha256_bytes(canonical_json(item["static_identity"]))[7:23]
        for item in boundaries
    }
    if evidence_mode not in {
        "current_run",
        "history_full",
        "etiq_full",
        "etiq_selected_fixed",
        "etiq_selected_adaptive",
        "etiq_random_matched",
    }:
        raise ValueError("N05 evidence mode is invalid")
    graph_selection = None
    if evidence_mode.startswith("etiq_"):
        job_ids = dict(controller_job_id_map or {})
        clean_handoffs = [
            {
                "handoff_ref": str(item.get("handoff_ref") or item.get("handoff_id")),
                "upstream_job_id": job_ids.get(
                    str(item["upstream_job_id"]), str(item["upstream_job_id"])
                ),
                "downstream_job_id": job_ids.get(
                    str(item["downstream_job_id"]), str(item["downstream_job_id"])
                ),
                "artifact_sha256": str(
                    item.get("artifact_sha256") or item.get("producer_sha256")
                ),
            }
            for item in handoffs
        ]
        projection = dict(frozen_projection or {})
        if not projection:
            if evidence_mode == "etiq_random_matched":
                projection = dict(random_selection or {})
                if not projection.get("projection_sha256"):
                    raise ValueError(
                        "N05 random-matched package requires a canonical frozen projection"
                    )
            else:
                value = graph_selection_for_mode(
                    evidence_mode,
                    snapshot,
                    boundaries,
                    handoffs=clean_handoffs,
                    expanded_prefixes_by_boundary=expanded_prefixes_by_boundary,
                    include_projection_binding=True,
                )
                assert value is not None
                projection = value
        if projection.get("evidence_mode") != evidence_mode:
            raise ValueError("N05 frozen projection evidence mode changed")
        projection = verify_canonical_graph_projection(snapshot, projection)
        visible = {
            boundary_ids[str(boundary_id)]: deepcopy(value)
            for boundary_id, value in projection.get(
                "visible_evidence_by_boundary", {}
            ).items()
        }
        collapsed = [
            {
                "boundary_id": boundary_ids[str(item["boundary_id"])],
                "func_stack": list(item["func_stack"]),
            }
            for item in projection.get("collapsed_helpers", [])
        ]
        graph_selection = {
            "node_refs": list(projection["node_refs"]),
            "relationship_refs": list(projection["relationship_refs"]),
            "visible_evidence_by_boundary": visible,
            "collapsed_helpers": collapsed,
            "handoffs": clean_handoffs,
        }
    declarations = [
        {
            "boundary_id": boundary_ids[item["boundary_id"]],
            "function_name": item["static_identity"]["qualified_function_name"],
            "role": item["role"],
            "expected_inputs": item["expected_inputs"],
            "expected_outputs": item["expected_outputs"],
        }
        for item in boundaries
    ]
    inputs = deepcopy(package_inputs)
    section = dict(inputs["section"])
    for field in ("assigned_boundary_ids", "context_boundary_ids"):
        section[field] = [boundary_ids[str(value)] for value in section.get(field, [])]
    inputs["section"] = section
    package, manifest = build_fault_review_package(
        evidence_mode=evidence_mode,
        include_source_bundle=source_setting == "source_present",
        declarations=declarations,
        snapshot=snapshot if graph_selection is not None else None,
        graph_selection=graph_selection,
        **inputs,
    )
    manifest["protocol"] = {
        "protocol_id": "neurips-2026-workshop-fault-localisation-v2",
        "protocol_version": protocol_version,
        "protocol_content_hash": protocol_content_hash,
    }
    manifest["source_setting"] = source_setting
    manifest["controller_boundary_id_map"] = boundary_ids
    manifest["package_sha256"] = sha256_bytes(canonical_json(package))
    if graph_selection is not None:
        runtime = package["runtime_evidence"]
        runtime_graph = {
            "nodes": runtime["nodes"],
            "relationships": runtime["relationships"],
        }
        runtime_graph_bytes = canonical_json(runtime_graph)
        runtime_graph_sha256 = sha256_bytes(runtime_graph_bytes)
        if runtime_graph_sha256 != projection["graph_evidence_sha256"] or len(
            runtime_graph_bytes
        ) != projection["graph_evidence_utf8_bytes"]:
            raise ValueError(
                "N05 packaged runtime graph differs from the measured projection"
            )
        manifest["canonical_projection"] = {
            key: projection[key]
            for key in (
                "projection_inputs_sha256",
                "node_refs_sha256",
                "relationship_refs_sha256",
                "graph_evidence_sha256",
                "graph_evidence_utf8_bytes",
                "evidence_mode",
                "projection_sha256",
            )
        }
        manifest["runtime_graph_sha256"] = runtime_graph_sha256
        manifest["runtime_graph_utf8_bytes"] = len(runtime_graph_bytes)
        manifest["projection_package_equivalence_sha256"] = sha256_bytes(
            canonical_json(
                {
                    "projection_sha256": projection["projection_sha256"],
                    "projection_graph_sha256": projection[
                        "graph_evidence_sha256"
                    ],
                    "packaged_graph_sha256": runtime_graph_sha256,
                    "package_sha256": manifest["package_sha256"],
                }
            )
        )
    manifest["manifest_content_sha256"] = sha256_bytes(canonical_json(manifest))
    serialized_package = json.dumps(package)
    if "unmatched_declaration" in serialized_package:
        raise ValueError("N05 unmatched declaration audit leaked into reviewer package")
    if protocol_version == "2.2.0" and any(
        marker in serialized_package
        for marker in (
            "outputs/fault-experiments-v2-1",
            "N05 Candidate",
            "n05-candidate",
            "candidate-3",
        )
    ):
        raise ValueError("N06 excluded N05 evidence leaked into reviewer package")
    return package, manifest


def _accepted_mutant(
    branch_root: Path,
    *,
    repo_root: Path,
    fixture: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    plan = fixture["mutation"]
    job_id = str(plan["job_id"])
    target_identity = resolve_static_identity(
        job_id,
        jobs[job_id],
        source_path=str(plan["source_path"]),
        qualified_function_name=str(plan["qualified_function_name"]),
    )
    schedule = freeze_reverse_ordering_order_v2(
        jobs[job_id],
        target_identity=target_identity,
        seed=int(plan["seed"]),
        preferred_occurrence=None,
    )
    clean_bytes = canonical_json(_pipeline_payload(jobs[job_id]))
    rejections: list[dict[str, Any]] = []
    for attempt, candidate in enumerate(schedule["frozen_candidates"], 1):
        injected = inject_reverse_ordering_v2(
            jobs[job_id],
            target_identity=target_identity,
            occurrence=int(candidate["occurrence"]),
        )
        mutant_jobs = dict(jobs)
        mutant_jobs[job_id] = parse_generated_pipeline(
            job_id, _pipeline_payload(injected["pipeline"])
        )
        execution = execute_two_job_chain(
            branch_root,
            repo_root=repo_root,
            jobs=mutant_jobs,
            scenario=scenario,
            run_index=attempt + 10,
            stage=f"qualification-mutant-{attempt:02d}",
        )
        execution.update(
            derive_review_evidence(execution, jobs=mutant_jobs, scenario=scenario)
        )
        proof = any(
            str(plan["qualified_function_name"]).split(".")[-1]
            in {frame.split(",", 1)[0] for frame in node.func_stack}
            for node in execution["executions"][job_id].snapshot.nodes
        )
        flags = {
            "compile_success": True,
            "execution_success": True,
            "schema_valid": execution["oracle"]["checks"]["downstream_schema"],
            "mutated_statement_executed": proof,
            "plausible_final_result": bool(
                execution["outputs"][tuple(jobs)[1]].get("priorities")
            ),
            "semantic_oracle_failed": not execution["oracle"]["passed"],
        }
        if all(flags.values()):
            restored = canonical_json(_pipeline_payload(injected["clean_pipeline"]))
            validate_source_restoration(jobs[job_id], injected["clean_pipeline"])
            return {
                "target_identity": target_identity,
                "schedule": schedule,
                "selected_occurrence": int(candidate["occurrence"]),
                "site": injected["site"],
                "validation": flags,
                "execution": execution,
                "rejections": rejections,
                "restoration_sha256": sha256_bytes(restored),
            }
        rejections.append(
            {
                "occurrence": int(candidate["occurrence"]),
                "order_key": candidate["order_key"],
                "failed_flags": sorted(name for name, passed in flags.items() if not passed),
            }
        )
        if canonical_json(_pipeline_payload(injected["clean_pipeline"])) != clean_bytes:
            raise ValueError("N05 source restoration mismatch")
    raise ValueError("N05 deterministic mutation sites exhausted")


def validate_exact_mutation(
    clean: GeneratedPipeline, mutant: GeneratedPipeline, site: Mapping[str, Any]
) -> None:
    clean_payload = _pipeline_payload(normalize_pipeline(clean))
    mutant_payload = _pipeline_payload(normalize_pipeline(mutant))
    if canonical_json(clean_payload) == canonical_json(mutant_payload):
        raise ValueError("N05 mutation changed nothing")
    changed_files = [
        before["path"]
        for before, after in zip(clean_payload["files"], mutant_payload["files"], strict=True)
        if before != after
    ]
    if changed_files != [str(site.get("file") or "")]:
        raise ValueError("N05 mutation did not change exactly one selected source file")
    if not site.get("original_span") or not site.get("mutant_span"):
        raise ValueError("N05 mutation lacks one contiguous normalized source change")


def validate_source_restoration(
    expected_clean: GeneratedPipeline, restored: GeneratedPipeline
) -> None:
    if canonical_json(_pipeline_payload(normalize_pipeline(expected_clean))) != canonical_json(
        _pipeline_payload(normalize_pipeline(restored))
    ):
        raise ValueError("N05 source restoration mismatch")


def _fixture_allowlist(
    repo_root: Path,
    qualification_root: Path = QUALIFICATION_ROOT,
    preflight_root: Path = PREFLIGHT_ROOT,
) -> dict[str, Path]:
    qualification = repo_root / qualification_root
    preflight = repo_root / preflight_root
    return {
        "qualification/fixture.json": qualification / "fixture.json",
        "qualification/upstream.py": qualification / "upstream.py",
        "qualification/downstream.py": qualification / "downstream.py",
        "scenario.json": preflight / "scenario.json",
        "corpus.json": preflight / "corpus.json",
        "capabilities.json": preflight / "capabilities.json",
        "oracles.json": preflight / "oracles.json",
    }


def run_deterministic_qualification(
    repo_root: Path,
    output_root: Path,
    *,
    qualification_root: Path = QUALIFICATION_ROOT,
    preflight_root: Path = PREFLIGHT_ROOT,
) -> dict[str, Any]:
    """Run the positive fixture through real Etiq, mutation, and append-only recording."""
    fixture, jobs = load_qualification_fixture(repo_root, qualification_root)
    scenario = load_preflight_inputs(repo_root, preflight_root)
    branch_id = stable_id("branch", [fixture["fixture_id"], "positive"], 0)
    branch_root = output_root / "branches" / branch_id
    materialize_opaque_branch(
        branch_root,
        allowlist=_fixture_allowlist(
            repo_root, qualification_root, preflight_root
        ),
        manifest_identity={"branch_id": branch_id, "purpose": "deterministic_qualification"},
    )
    copy_etiq_worker_runtime(branch_root, repo_root / "src")
    reference = execute_two_job_chain(
        branch_root,
        repo_root=repo_root,
        jobs=jobs,
        scenario=scenario,
        run_index=0,
        stage="qualification-reference",
    )
    reference.update(derive_review_evidence(reference, jobs=jobs, scenario=scenario))
    if not reference["oracle"]["passed"]:
        raise ValueError("N05 deterministic reference oracle failed")
    qualification = qualify_realized_chain(
        reference["realizations"].values(),
        handoffs=reference["handoffs"],
        helper_evidence=reference["helpers"],
        graph_size_reports=reference["graph_size_reports"],
        has_join_or_aggregation=True,
    )
    expected = fixture["expected"]
    observed = {
        "declarations": sum(len(job.review_boundaries) for job in jobs.values()),
        "realized_boundaries": qualification["realized_boundary_count"],
        "unmatched_declarations": qualification["unmatched_declaration_count"],
        "exact_handoffs": qualification["handoff_count"],
    }
    if observed != {
        key: expected[key]
        for key in (
            "declarations",
            "realized_boundaries",
            "unmatched_declarations",
            "exact_handoffs",
        )
    }:
        raise ValueError(f"N05 deterministic fixture counts differ: {observed}")
    mutant = _accepted_mutant(
        branch_root,
        repo_root=repo_root,
        fixture=fixture,
        jobs=jobs,
        scenario=scenario,
    )
    serializable = {
        "schema_version": "1",
        "fixture_id": fixture["fixture_id"],
        "branch_id": branch_id,
        "etiq_version": importlib.metadata.version("etiq-copilot"),
        "reference_oracle": reference["oracle"],
        "qualification": qualification,
        "observed_counts": observed,
        "helpers": reference["helpers"],
        "realizations": reference["realizations"],
        "handoffs": reference["handoffs"],
        "mutation": {
            key: value
            for key, value in mutant.items()
            if key != "execution"
        },
        "mutant_oracle": mutant["execution"]["oracle"],
    }
    serializable["result_sha256"] = sha256_bytes(canonical_json(serializable))
    ledger = output_root / "ledger"
    record_id = stable_id("setup", [fixture["fixture_id"], "gate-0"], 0)
    record = append_record(
        ledger,
        record_type="deterministic-qualification",
        record_id=record_id,
        payload=serializable,
    )
    create_json_exclusive(
        output_root / "deterministic-qualification.json",
        {**serializable, "ledger_record": record},
    )
    return {**serializable, "ledger_record": record, "branch_root": branch_root}


def run_operator_qualification(repo_root: Path, output_root: Path) -> dict[str, Any]:
    """Qualify all five operators at top-level and nested exact identities."""
    source_path = repo_root / QUALIFICATION_ROOT / "operators.py"
    source = source_path.read_text()
    operator_targets = {
        "invert_comparison": ("top_invert", "outer_invert.invert_inner", ""),
        "truncate_sequence": ("top_truncate", "outer_truncate.truncate_inner", ""),
        "drop_field": ("top_drop", "outer_drop.drop_inner", "drop"),
        "fabricate_identifier": (
            "top_fabricate",
            "outer_fabricate.fabricate_inner",
            "mutated-id",
        ),
        "reverse_ordering": ("top_reverse", "outer_reverse.reverse_inner", ""),
    }
    rows: list[dict[str, Any]] = []
    case_index = 0
    for operator, targets in operator_targets.items():
        for target in targets[:2]:
            pipeline = GeneratedPipeline(
                "operators.py", [GeneratedFile("operators.py", source)]
            )
            pipeline = normalize_pipeline(pipeline)
            identity = resolve_static_identity(
                "n05-operator-job",
                pipeline,
                source_path="operators.py",
                qualified_function_name=target,
            )
            parameter = targets[2]
            schedule = freeze_operator_site_order(
                pipeline,
                target_identity=identity,
                operator=operator,
                seed=26082997 + case_index,
                parameter=parameter,
            )
            if not schedule["frozen_candidates"]:
                raise ValueError(f"N05 operator fixture has no site for {operator}/{target}")
            selected = schedule["frozen_candidates"][0]
            injected = inject_operator_exact(
                pipeline,
                target_identity=identity,
                operator=operator,
                occurrence=int(selected["occurrence"]),
                parameter=parameter,
            )
            branch_id = stable_id(
                "branch", ["operator-qualification", operator, target], case_index
            )
            branch_root = output_root / "operator-branches" / branch_id
            materialize_opaque_branch(
                branch_root,
                allowlist={"operators-reference.py": source_path},
                manifest_identity={"branch_id": branch_id, "purpose": "operator_qualification"},
            )
            clean_source = injected["clean_pipeline"].files[0].content.encode()
            mutant_source = injected["pipeline"].files[0].content.encode()
            create_bytes_exclusive(branch_root / "workspace" / "clean.py", clean_source)
            create_bytes_exclusive(branch_root / "workspace" / "mutant.py", mutant_source)
            clean_run = run_python_in_branch(
                branch_root,
                ["/venv/bin/python", "/workspace/clean.py", target],
                role="authored_python",
                venv_root=repo_root / ".venv",
            )
            mutant_run = run_python_in_branch(
                branch_root,
                ["/venv/bin/python", "/workspace/mutant.py", target],
                role="authored_python",
                venv_root=repo_root / ".venv",
            )
            if clean_run.returncode or mutant_run.returncode:
                raise ValueError(f"N05 operator execution failed for {operator}/{target}")
            if clean_run.stdout == mutant_run.stdout:
                raise ValueError(f"N05 operator mutation was a no-op for {operator}/{target}")
            if canonical_json(_pipeline_payload(injected["clean_pipeline"])) != canonical_json(
                _pipeline_payload(pipeline)
            ):
                raise ValueError("N05 operator source restoration mismatch")
            rows.append(
                {
                    "operator": operator,
                    "target_identity": identity,
                    "nested": "." in target,
                    "schedule_sha256": schedule["frozen_schedule_sha256"],
                    "selected_site": injected["site"],
                    "clean_output_sha256": sha256_bytes(clean_run.stdout.encode()),
                    "mutant_output_sha256": sha256_bytes(mutant_run.stdout.encode()),
                    "execution_proof": True,
                    "restoration_proof": True,
                }
            )
            case_index += 1
    report = {
        "schema_version": "1",
        "operator_count": 5,
        "case_count": len(rows),
        "top_level_cases": sum(not row["nested"] for row in rows),
        "nested_cases": sum(row["nested"] for row in rows),
        "cases": rows,
    }
    report["report_sha256"] = sha256_bytes(canonical_json(report))
    create_json_exclusive(output_root / "operator-qualification.json", report)
    return report


def _replace_pipeline_source(
    job_id: str, pipeline: GeneratedPipeline, replacements: Mapping[str, str]
) -> GeneratedPipeline:
    payload = _pipeline_payload(pipeline)
    source = payload["files"][0]["content"]
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError(f"N05 negative fixture replacement is not exact: {old}")
        source = source.replace(old, new)
    payload["files"][0]["content"] = source
    return parse_generated_pipeline(job_id, payload)


def _qualification_branch(
    repo_root: Path, output_root: Path, name: str, index: int
) -> Path:
    branch_id = stable_id("branch", ["negative-qualification", name], index)
    branch_root = output_root / "negative-branches" / branch_id
    materialize_opaque_branch(
        branch_root,
        allowlist=_fixture_allowlist(repo_root),
        manifest_identity={"branch_id": branch_id, "purpose": name},
    )
    copy_etiq_worker_runtime(branch_root, repo_root / "src")
    return branch_root


def _qualify_execution(execution: Mapping[str, Any]) -> dict[str, Any]:
    return qualify_realized_chain(
        execution["realizations"].values(),
        handoffs=execution["handoffs"],
        helper_evidence=execution["helpers"],
        graph_size_reports=execution["graph_size_reports"],
        has_join_or_aggregation=True,
    )


def run_negative_qualifications(repo_root: Path, output_root: Path) -> dict[str, Any]:
    """Exercise every named negative fixture at its intended production gate."""
    manifest = _load_json(repo_root / QUALIFICATION_ROOT / "negative-variants.json")
    fixture, base_jobs = load_qualification_fixture(repo_root)
    scenario = load_preflight_inputs(repo_root)
    outcomes: list[dict[str, str]] = []

    def expect_failure(name: str, gate: str, action: Any) -> None:
        try:
            action()
        except Exception as error:
            outcomes.append(
                {
                    "variant": name,
                    "expected_gate": gate,
                    "status": "failed_closed_as_expected",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            return
        raise AssertionError(f"N05 negative variant unexpectedly passed: {name}")

    upstream_id, downstream_id = tuple(base_jobs)
    eleven_jobs = dict(base_jobs)
    eleven_jobs[upstream_id] = _replace_pipeline_source(
        upstream_id,
        base_jobs[upstream_id],
        {
            "ranked = rank_demands(scored)": "ranked = scored.sort_values(by=['priority_score', 'record_id'], ascending=[False, True]).reset_index(drop=True)",
            "'needs': serialize_needs(ranked)": "'needs': ranked[['record_id', 'need', 'priority_score', 'evidence_ref']].to_dict(orient='records')",
            "'metadata': upstream_metadata(ranked)": "'metadata': {'selected_count': int(len(ranked)), 'pipeline': 'qualification-upstream'}",
        },
    )
    branch = _qualification_branch(repo_root, output_root, "eleven-realized", 0)
    eleven_execution = execute_two_job_chain(
        branch,
        repo_root=repo_root,
        jobs=eleven_jobs,
        scenario=scenario,
        run_index=0,
        stage="negative-eleven-realized",
    )
    eleven_execution.update(
        derive_review_evidence(eleven_execution, jobs=eleven_jobs, scenario=scenario)
    )
    expect_failure(
        "eleven_realized_boundaries",
        "minimum_realized_boundaries",
        lambda: _qualify_execution(eleven_execution),
    )

    mandatory_jobs = dict(base_jobs)
    mandatory_jobs[downstream_id] = _replace_pipeline_source(
        downstream_id,
        base_jobs[downstream_id],
        {
            "'recommendation': synthesize_recommendation(prioritized)": "'recommendation': {'top_need': str(prioritized.iloc[0]['need']), 'decision': 'prioritize' if prioritized.iloc[0]['coverage'] != 'supported' else 'maintain'}"
        },
    )
    branch = _qualification_branch(repo_root, output_root, "unmatched-stage", 1)
    mandatory_execution = execute_two_job_chain(
        branch,
        repo_root=repo_root,
        jobs=mandatory_jobs,
        scenario=scenario,
        run_index=0,
        stage="negative-unmatched-stage",
    )
    mandatory_execution.update(
        derive_review_evidence(
            mandatory_execution, jobs=mandatory_jobs, scenario=scenario
        )
    )
    expect_failure(
        "unmatched_mandatory_stage",
        "mandatory_semantic_stages",
        lambda: _qualify_execution(mandatory_execution),
    )

    def ambiguous() -> None:
        payload = _pipeline_payload(base_jobs[upstream_id])
        payload["files"][0]["content"] += "\n\ndef normalize_evidence(frame):\n    return frame.copy()\n"
        parse_generated_pipeline(upstream_id, payload)

    expect_failure("ambiguous_identity", "exact_static_identity", ambiguous)

    branch = _qualification_branch(repo_root, output_root, "conflicting-capture", 2)
    base_execution = execute_two_job_chain(
        branch,
        repo_root=repo_root,
        jobs=base_jobs,
        scenario=scenario,
        run_index=0,
        stage="negative-conflicting-capture",
    )
    base_execution.update(
        derive_review_evidence(base_execution, jobs=base_jobs, scenario=scenario)
    )

    def conflicting_capture() -> None:
        snapshot = deepcopy(base_execution["executions"][upstream_id].snapshot)
        node = next(
            item
            for item in snapshot.nodes
            if item.raw_metadata.get("v21_job_id") == upstream_id
        )
        node.raw_metadata["v21_source_path"] = "forged.py"
        materialize_realized_boundaries(
            snapshot,
            base_jobs[upstream_id].review_boundaries,
            job_id=upstream_id,
            pipeline=base_jobs[upstream_id],
        )

    expect_failure(
        "conflicting_capture_evidence",
        "capture_identity_enrichment",
        conflicting_capture,
    )

    helper_jobs = deepcopy(base_jobs)
    helper_declarations = {
        upstream_id: [
            ("uh01", "validate_selected_records.valid_record_ids"),
            ("uh02", "normalize_evidence.normalize_need"),
            ("uh03", "assemble_provenance.evidence_reference"),
            ("uh04", "score_demands.weighted_score"),
        ],
        downstream_id: [
            ("dh01", "map_coverage.coverage_input_frame"),
            ("dh02", "aggregate_coverage.summarize_coverage"),
            ("dh03", "prioritize_needs.gap_bonus"),
        ],
    }
    for job_id, declarations in helper_declarations.items():
        payload = _pipeline_payload(helper_jobs[job_id])
        for boundary_id, name in declarations:
            payload["review_boundaries"].append(
                {
                    "boundary_id": boundary_id,
                    "source_path": payload["entry_file"],
                    "qualified_function_name": name,
                    "semantic_stage": "supporting",
                    "role": "declared helper negative control",
                    "expected_inputs": ["captured value"],
                    "expected_outputs": ["captured value"],
                }
            )
        helper_jobs[job_id] = parse_generated_pipeline(job_id, payload)
    branch = _qualification_branch(repo_root, output_root, "ineligible-helper", 3)
    helper_execution = execute_two_job_chain(
        branch,
        repo_root=repo_root,
        jobs=helper_jobs,
        scenario=scenario,
        run_index=0,
        stage="negative-ineligible-helper",
    )
    helper_execution.update(
        derive_review_evidence(helper_execution, jobs=helper_jobs, scenario=scenario)
    )
    expect_failure(
        "ineligible_helper",
        "operational_helper_eligibility",
        lambda: _qualify_execution(helper_execution),
    )

    expect_failure(
        "no_op_mutation",
        "exact_one_site_mutation",
        lambda: validate_exact_mutation(
            base_jobs[upstream_id],
            deepcopy(base_jobs[upstream_id]),
            {"file": "upstream.py", "original_span": {}, "mutant_span": {}},
        ),
    )

    def restoration_mismatch() -> None:
        restored = deepcopy(base_jobs[upstream_id])
        restored.files[0].content = restored.files[0].content.replace(
            "qualification-upstream", "qualification-upstream-mismatch", 1
        )
        validate_source_restoration(base_jobs[upstream_id], restored)

    expect_failure(
        "restoration_mismatch",
        "byte_exact_source_restoration",
        restoration_mismatch,
    )
    expected = {(item["variant"], item["expected_gate"]) for item in manifest["variants"]}
    observed = {(item["variant"], item["expected_gate"]) for item in outcomes}
    if observed != expected:
        raise ValueError("N05 negative qualification coverage differs from manifest")
    report = {"schema_version": "1", "fixture_id": manifest["fixture_id"], "outcomes": outcomes}
    report["report_sha256"] = sha256_bytes(canonical_json(report))
    create_json_exclusive(output_root / "negative-qualifications.json", report)
    return report


def run_isolation_dry_run(repo_root: Path, output_root: Path) -> dict[str, Any]:
    """Run exact-path hostile probes in all three production launch positions."""
    controller_root = output_root / "controller-only"
    controller_root.mkdir(parents=True, exist_ok=True)
    sentinels = {
        "repository": repo_root / "README.md",
        "controller": controller_root / "truth.txt",
        "common_capture": controller_root / "common-capture.json",
        "aggregate_ledger": controller_root / "aggregate-ledger.json",
    }
    create_bytes_exclusive(sentinels["controller"], b"n05-controller-secret\n")
    create_bytes_exclusive(sentinels["common_capture"], b"n05-common-secret\n")
    create_bytes_exclusive(sentinels["aggregate_ledger"], b"n05-ledger-secret\n")
    own_source = controller_root / "own.txt"
    sibling_source = controller_root / "sibling.txt"
    create_bytes_exclusive(own_source, b"own-branch-visible\n")
    create_bytes_exclusive(sibling_source, b"sibling-secret\n")
    branch_ids = [
        stable_id("branch", ["isolation-dry-run", "opaque"], index)
        for index in range(2)
    ]
    branches: list[Path] = []
    for index, branch_id in enumerate(branch_ids):
        branch = output_root / "isolation-branches" / branch_id
        materialize_opaque_branch(
            branch,
            allowlist={"own.txt": own_source if index == 0 else sibling_source},
            manifest_identity={"branch_id": branch_id},
        )
        branches.append(branch)
    sibling_sentinel = branches[1] / "evidence" / "own.txt"
    forbidden = [*sentinels.values(), sibling_sentinel, Path.home() / ".codex"]
    probe_source = """import json, os, pathlib, socket, sys
paths = [pathlib.Path(value) for value in sys.argv[1:-1]]
fd = sys.argv[-1]
reads = {}
writes = {}
for path in paths:
    try:
        reads[str(path)] = path.read_text()
    except Exception as error:
        reads[str(path)] = type(error).__name__
    try:
        path.write_text('host-write')
        writes[str(path)] = 'unexpected-success'
    except Exception as error:
        writes[str(path)] = type(error).__name__
allowed_read = pathlib.Path('/evidence/own.txt').read_text().strip()
pathlib.Path('/workspace/allowed.txt').write_text('workspace-write')
pathlib.Path('/output/allowed.txt').write_text('output-write')
try:
    inherited_fd = pathlib.Path('/proc/self/fd/' + fd).read_text()
except Exception as error:
    inherited_fd = type(error).__name__
try:
    socket.create_connection(('1.1.1.1', 53), timeout=0.25)
    network = 'reachable'
except Exception as error:
    network = type(error).__name__
print(json.dumps({'reads': reads, 'writes': writes, 'allowed_read': allowed_read, 'inherited_fd': inherited_fd, 'network': network, 'environment': dict(os.environ)}, sort_keys=True))
"""
    create_bytes_exclusive(branches[0] / "workspace" / "probe.py", probe_source.encode())
    fake_auth = branches[0] / "home" / ".codex" / "auth.json"
    create_bytes_exclusive(fake_auth, b"{}\n")
    runtime_executable = Path(shutil.which("codex") or "").resolve(strict=True)
    codex_runtime = runtime_executable.parent.parent
    inherited = (controller_root / "inherited.txt").open("x+")
    inherited.write("inherited-secret")
    inherited.flush()
    arguments = [str(path.resolve()) for path in forbidden] + [str(inherited.fileno())]
    results: list[dict[str, Any]] = []
    try:
        codex_command = codex_control_plane_bubblewrap_command(
            branches[0],
            codex_runtime_root=codex_runtime,
            child_command=["/usr/bin/python3", "/workspace/probe.py", *arguments],
        )
        codex_probe = subprocess.run(
            codex_command,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            close_fds=True,
        )
        for role in ("authored_python", "repaired_python"):
            completed = run_python_in_branch(
                branches[0],
                ["/venv/bin/python", "/workspace/probe.py", *arguments],
                role=role,
                venv_root=repo_root / ".venv",
                timeout_seconds=60,
            )
            results.append(
                {
                    "role": role,
                    "returncode": completed.returncode,
                    "probe": json.loads(completed.stdout),
                }
            )
        results.insert(
            0,
            {
                "role": "codex_control_plane_launch_position",
                "returncode": codex_probe.returncode,
                "probe": json.loads(codex_probe.stdout),
            },
        )
    finally:
        inherited.close()
    forbidden_strings = {str(path.resolve()) for path in forbidden}
    for result in results:
        probe = result["probe"]
        if result["returncode"] != 0 or probe["allowed_read"] != "own-branch-visible":
            raise ValueError(f"N05 allowed-access isolation probe failed: {result['role']}")
        if set(probe["reads"]) != forbidden_strings or any(
            value not in {"FileNotFoundError", "PermissionError", "NotADirectoryError"}
            for value in probe["reads"].values()
        ):
            raise ValueError(f"N05 forbidden read succeeded: {result['role']}")
        if any(value == "unexpected-success" for value in probe["writes"].values()):
            raise ValueError(f"N05 forbidden write succeeded: {result['role']}")
        if "secret" in str(probe["inherited_fd"]):
            raise ValueError(f"N05 inherited descriptor leaked: {result['role']}")
        allowed_environment = {"PATH", "HOME", "TMPDIR", "LANG", "CODEX_HOME", "PWD"}
        if set(probe["environment"]) - allowed_environment:
            raise ValueError(
                f"N05 sandbox environment leaked: {result['role']}: "
                f"{sorted(set(probe['environment']) - allowed_environment)}"
            )
        if probe["environment"].get("PWD") not in {None, "/workspace"}:
            raise ValueError(f"N05 sandbox PWD leaked a host path: {result['role']}")
        if result["role"] != "codex_control_plane_launch_position" and probe["network"] == "reachable":
            raise ValueError(f"N05 Python network isolation failed: {result['role']}")
    try:
        run_python_in_branch(
            branches[0],
            ["/usr/bin/true"],
            role="authored_python",
            timeout_seconds=5,
        )
    except Exception:
        pass
    try:
        from .n05_runner import python_bubblewrap_command

        python_bubblewrap_command(
            branches[0], ["/usr/bin/true"], role="authored_python", bwrap_bin="n05-missing-bwrap"
        )
    except RuntimeError:
        fail_closed = True
    else:
        fail_closed = False
    if not fail_closed:
        raise ValueError("N05 missing sandbox did not fail closed")
    actual_codex_command = codex_bubblewrap_command(
        branches[0],
        codex_runtime_root=codex_runtime,
        prompt_file="own.txt",
        schema_file="own.txt",
        output_file="probe-output.json",
    )
    command_text = " ".join(actual_codex_command)
    if "permissions.n05-branch-command.network.enabled=false" not in command_text:
        raise ValueError("N05 Codex command-network denial profile is absent")
    profile_probe = subprocess.run(
        codex_permission_profile_probe_command(
            branches[0], codex_runtime_root=codex_runtime
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        close_fds=True,
    )
    if profile_probe.returncode != 0:
        raise ValueError(
            "N05 Codex permission profile failed local parsing: "
            + profile_probe.stderr.strip()
        )
    report = {
        "schema_version": "1",
        "sandbox_backend_version": bubblewrap_version(),
        "branch_ids": branch_ids,
        "probe_results": results,
        "sandbox_missing_fails_closed": fail_closed,
        "codex_control_plane_network_unshared": "--unshare-net" in actual_codex_command,
        "codex_command_network_permission_disabled": True,
        "codex_permission_profile_parsed_without_inference": True,
        "authored_python_network_unshared": True,
        "repaired_python_network_unshared": True,
        "tester_provider_transport_probe_pending_gate_1": True,
    }
    if report["codex_control_plane_network_unshared"]:
        raise ValueError("N05 Codex control plane incorrectly unshares provider network")
    report["report_sha256"] = sha256_bytes(canonical_json(report))
    create_json_exclusive(output_root / "isolation-dry-run.json", report)
    return report


def run_review_repair_dry_run(repo_root: Path, output_root: Path) -> dict[str, Any]:
    """Exercise the approved upstream and downstream Phase-B subtrace semantics."""
    upstream_id = "n05-dry-upstream"
    downstream_id = "n05-dry-downstream"
    dependencies = {upstream_id: [], downstream_id: [upstream_id]}
    source = (
        "import json\n"
        "def selected(rows):\n"
        "    return list(rows)\n"
        "if __name__ == '__main__':\n"
        "    print(json.dumps({'rows': selected([1, 2])}))\n"
    )
    repaired_source = source.replace("return list(rows)", "return sorted(rows)")
    declaration = {
        "source_path": "pipeline.py",
        "qualified_function_name": "selected",
        "semantic_stage": "supporting",
        "role": "dry-run selected repair boundary",
        "expected_inputs": ["rows"],
        "expected_outputs": ["rows"],
    }
    original = GeneratedPipeline(
        "pipeline.py", [GeneratedFile("pipeline.py", source)], [declaration]
    )
    replacement = GeneratedPipeline(
        "pipeline.py", [GeneratedFile("pipeline.py", repaired_source)], [declaration]
    )
    target = source_scope(original, function_name="selected", mode="boundary")
    validate_boundary_sized_repair(original, replacement, target)
    common_upstream = {"rows": [1, 2]}
    common_hash = sha256_bytes(canonical_json(common_upstream))
    initial_handoff = {
        "upstream_job_id": upstream_id,
        "downstream_job_id": downstream_id,
        "artifact_sha256": common_hash,
    }
    traces: list[dict[str, Any]] = []
    for index, repaired_job_id in enumerate((upstream_id, downstream_id)):
        branch_id = stable_id(
            "branch", ["gate-0-operational-dry-run", repaired_job_id], index
        )
        branch = output_root / "operational-branches" / branch_id
        materialize_opaque_branch(
            branch,
            allowlist={"pipeline.py": repo_root / QUALIFICATION_ROOT / "operators.py"},
            manifest_identity={"branch_id": branch_id, "purpose": "operational_dry_run"},
        )
        create_bytes_exclusive(
            branch / "workspace" / "repaired.py", repaired_source.encode()
        )
        execution = run_python_in_branch(
            branch,
            ["/venv/bin/python", "/workspace/repaired.py"],
            role="repaired_python",
            venv_root=repo_root / ".venv",
        )
        if execution.returncode != 0 or json.loads(execution.stdout) != common_upstream:
            raise ValueError("N05 operational repaired-Python execution failed")
        rerun_ids = two_job_suffix_rerun_job_ids(
            repaired_job_id,
            upstream_job_id=upstream_id,
            downstream_job_id=downstream_id,
            dependencies=dependencies,
        )
        job_artifacts = {
            upstream_id: {"output": common_upstream, "inputs_by_upstream": {}},
            downstream_id: {
                "output": {"decision": "resume"},
                "inputs_by_upstream": {upstream_id: common_upstream},
            },
        }
        handoffs = recalculate_exact_hash_handoffs(
            job_artifacts,
            dependencies,
            rerun_ids,
            immutable_upstream_artifact_hashes=(
                {upstream_id: common_hash} if repaired_job_id == downstream_id else {}
            ),
        )
        log = branch / "workspace" / "operation-events.jsonl"
        events = [
            ("capture", {}),
            ("package_created", {}),
            ("review", {}),
            ("citation", {}),
            ("artifact_inspection", {"request_count": 1}),
            ("helper_expansion", {"expansion_count": 1}),
            ("boundary_judgment", {}),
            ("suspect_identification", {}),
            ("receipt_validation", {"valid": True}),
            ("localisation_frozen", {}),
            ("retrace", {}),
            ("repair_target_selection", {}),
            ("scoped_repair", {}),
            ("rerun_recapture", {"rerun_job_ids": rerun_ids}),
            ("re_review", {}),
            ("citation", {"phase": "repaired_run"}),
            ("boundary_judgment", {"phase": "repaired_run"}),
            ("suspect_identification", {"phase": "repaired_run"}),
            ("receipt_validation", {"valid": True, "phase": "re_review"}),
            ("trusted_frontier_recomputed", {}),
            ("resume", {}),
        ]
        for operation, details in events:
            append_operation_event(
                branch,
                log,
                operation=operation,
                status="completed",
                details=details,
            )
        outcome = recompute_resume_outcome(
            [SimpleNamespace(unit_id="unit-1", upstream_unit_ids=[], downstream_unit_ids=[])],
            [{"unit_id": "unit-1", "status": "trusted_for_reuse", "authority": "codex"}],
        )
        if outcome["outcome"] != "resume":
            raise ValueError("N05 operational frontier did not resume")
        traces.append(
            {
                "branch_id": branch_id,
                "repaired_job_id": repaired_job_id,
                "rerun_job_ids": rerun_ids,
                "handoffs": handoffs,
                "repair_call_count": 1,
                "operation_count": len(events),
                "operation_event_log_sha256": sha256_file(log),
                "outcome": outcome["outcome"],
            }
        )
    expected_suffixes = [[upstream_id, downstream_id], [downstream_id]]
    if [trace["rerun_job_ids"] for trace in traces] != expected_suffixes:
        raise ValueError("N05 two-subtrace dependency suffix semantics changed")
    report = {
        "schema_version": "1",
        "phase_b_interpretation": "two independent unscored subtraces",
        "subtrace_count": 2,
        "traces": traces,
    }
    report["report_sha256"] = sha256_bytes(canonical_json(report))
    create_json_exclusive(output_root / "operational-dry-run.json", report)
    return report


def _file_contract(repo_root: Path, path: Path) -> dict[str, Any]:
    relative = path.relative_to(repo_root).as_posix()
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _tree_contract(repo_root: Path, root: Path) -> dict[str, Any]:
    files = [
        _file_contract(repo_root, path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    ]
    return {
        "root": root.relative_to(repo_root).as_posix(),
        "files": files,
        "tree_sha256": sha256_bytes(canonical_json(files)),
    }


def build_n05_design_freeze(
    repo_root: Path,
    output_root: Path,
    *,
    qualification_report: Mapping[str, Any],
    operator_report: Mapping[str, Any],
    negative_report: Mapping[str, Any],
    isolation_report: Mapping[str, Any],
    operational_report: Mapping[str, Any],
    replay_report: Mapping[str, Any],
    test_outputs: Mapping[str, Path],
    freeze_name: str = "n05-design-freeze.json",
    supersedes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind every pre-results N05 byte into one exclusive Gate-0 design freeze."""
    authority_path = repo_root / (
        "instructions_between_agent_types/overseer/decisions/"
        "N05_v2_1_end_to_end_completion_program_authorization.json"
    )
    expected_authority = (
        "sha256:2928e57ecd8423365a53758424282b07928727bade71f8ff4fb1ce205df43a95"
    )
    if sha256_file(authority_path) != expected_authority:
        raise ValueError("N05 controlling authorization hash mismatch")
    protocol_root = repo_root / "docs/workshops/neurips-2026-v2-1"
    protocol_json_path = protocol_root / "experiment-protocol.json"
    protocol_md_path = protocol_root / "EXPERIMENT_PROTOCOL.md"
    protocol = _load_json(protocol_json_path)
    if protocol.get("protocol_version") != "2.1.0" or protocol.get("status") != "pre_results_frozen":
        raise ValueError("N05 protocol is not the frozen 2.1.0 design")
    embedded = protocol_md_path.read_text().split("```json\n", 1)[1].rsplit("```", 1)[0]
    if embedded.encode() != protocol_json_path.read_bytes():
        raise ValueError("N05 Markdown and JSON protocol bytes differ")
    source_paths = [
        repo_root / "src/use_case_icp/fault_v21.py",
        repo_root / "src/use_case_icp/n05_runner.py",
        repo_root / "src/use_case_icp/n05_program.py",
        repo_root / "src/use_case_icp/n05_analysis.py",
        repo_root / "src/use_case_icp/fault_operations.py",
        repo_root / "src/use_case_icp/fault_experiment.py",
        repo_root / "src/use_case_icp/fault_injection.py",
        repo_root / "src/use_case_icp/fault_v2.py",
        repo_root / "src/use_case_icp/fault_preflight_v2.py",
        repo_root / "src/use_case_icp/records.py",
    ]
    test_paths = sorted((repo_root / "tests").glob("test_n05*.py"))
    test_contracts = {
        name: _file_contract(repo_root, path)
        for name, path in sorted(test_outputs.items())
    }
    if not test_contracts or any(path.stat().st_size == 0 for path in test_outputs.values()):
        raise ValueError("N05 freeze requires non-empty Gate-0 test outputs")
    from .n05_analysis import expected_design

    design = expected_design()
    if Path(freeze_name).name != freeze_name:
        raise ValueError("N05 design freeze name must be one file name")
    freeze = {
        "schema_version": "1",
        "gate": "G0_engineering_and_design",
        "status": "pre_results_frozen",
        "scientific_model_calls": 0,
        "reviewer_calls_observed": 0,
        "experimental_outcomes_observed": 0,
        "controlling_authority": {
            "path": authority_path.relative_to(repo_root).as_posix(),
            "sha256": expected_authority,
        },
        "protocol": {
            "id": protocol["protocol_id"],
            "version": protocol["protocol_version"],
            "content_hash": protocol["integrity"]["content_hash"],
            "json": _file_contract(repo_root, protocol_json_path),
            "markdown": _file_contract(repo_root, protocol_md_path),
        },
        "protocol_archive": _tree_contract(
            repo_root, protocol_root / "archive/protocol-2.0.3"
        ),
        "prompt_namespace": _tree_contract(repo_root, repo_root / "prompts/v2_1"),
        "schema_namespace": _tree_contract(repo_root, repo_root / "schemas/v2_1"),
        "fresh_inputs": _tree_contract(
            repo_root,
            repo_root
            / "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures",
        ),
        "source": [_file_contract(repo_root, path) for path in source_paths],
        "tests": [_file_contract(repo_root, path) for path in test_paths],
        "environment": {
            "python": sys.version.split()[0],
            "python_executable": str(Path(sys.executable).resolve()),
            "etiq_copilot": importlib.metadata.version("etiq-copilot"),
            "bubblewrap": bubblewrap_version(),
        },
        "production_launch_policy": launch_policy_identity(),
        "expected_design": {
            "design_sha256": design["design_sha256"],
            "counts": design["expected_counts"],
            "trial_seeds": [104729, 130363, 155921],
        },
        "qualification": {
            "positive_sha256": qualification_report["result_sha256"],
            "operators_sha256": operator_report["report_sha256"],
            "negative_sha256": negative_report["report_sha256"],
            "isolation_sha256": isolation_report["report_sha256"],
            "operational_sha256": operational_report["report_sha256"],
            "offline_replay_sha256": replay_report["reconciliation_sha256"],
        },
        "test_outputs": test_contracts,
        "excluded_old_evidence_projection": _tree_contract(
            repo_root, repo_root / "outputs/fault-experiments-v2"
        ),
        "future_materialization_contract": {
            "phase_a_calls": 1,
            "phase_b_subtraces": 2,
            "instances": 12,
            "capture_sets": 12,
            "branches": 96,
            "review_trials": 288,
            "repair_traces": 180,
            "append_only": True,
            "post_gate_1_design_changes": "experiment_incomplete",
        },
        "supersession": dict(supersedes or {}),
    }
    freeze["freeze_sha256"] = sha256_bytes(canonical_json(freeze))
    create_json_exclusive(output_root / freeze_name, freeze)
    return freeze
