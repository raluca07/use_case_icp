"""N07 function-based execution controller for the frozen protocol-2.2 study."""

from __future__ import annotations

import importlib.metadata
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping

import jsonschema

from .fault_experiment import (
    build_stabilization_evidence,
    graph_selection_for_mode,
    materialize_branch_package,
    validate_stabilization_replacement,
    verify_materialized_branch,
)
from .fault_v21 import (
    eligible_direct_child_helpers,
    enrich_snapshot_identities,
    enumerate_operator_sites,
    freeze_operator_site_order,
    graph_size_report,
    inject_operator_exact,
    materialize_realized_boundaries,
    parse_generated_pipeline,
    qualify_realized_chain,
    resolve_static_identity,
)
from .n05_analysis import (
    analyze_frozen_results,
    build_anonymous_release,
    expected_design,
    offline_replay,
    reconcile_records,
    verify_anonymous_release,
    write_analysis_outputs,
)
from .n05_program import (
    _accepted_mutant,
    _file_contract,
    _parse_output,
    _pipeline_payload,
    _tree_contract,
    build_n05_condition_package,
    derive_review_evidence,
    execute_two_job_chain,
    execute_pipeline_in_branch,
    load_preflight_inputs,
    load_qualification_fixture,
    oracle_report,
    run_review_repair_dry_run,
    validate_exact_mutation,
    validate_source_restoration,
)
from .repair import repair_diff, source_scope, validate_repair_scope
from .review import inspect_artifact
from .etiq_executor import EtiqExecution
from .fault_operations import _package_with_graph_selection
from .n05_runner import (
    append_record,
    bubblewrap_version,
    canonical_json,
    copy_etiq_worker_runtime,
    copy_codex_auth,
    create_bytes_exclusive,
    create_json_exclusive,
    launch_policy_identity,
    launch_codex_in_branch,
    materialize_opaque_branch,
    run_with_identical_retries,
    sha256_bytes,
    sha256_file,
    stable_id,
)
from .random_control import freeze_random_projections
from .records import (
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    jsonable,
)


N07_AUTHORITY_SHA256 = "sha256:3f190125c7870fddd24f7778a6dbab3209901f88da9c7b011aa2af564c6549c7"
N07_OUTPUT_RELATIVE = Path("outputs/fault-experiments-v2-2-n07")
N08_AUTHORITY_SHA256 = "sha256:35ece65fd278c899312defb250d7fe2186957a1dd4a489d3dfb56b049e12cec3"
N08_OUTPUT_RELATIVE = Path("outputs/fault-experiments-v2-2-n08")
N09_AUTHORITY_SHA256 = "sha256:d7f4f8ff5d0b171868ff3664b450150fe9dda6cf06064b9e0ed8ce78158d1ee7"
N09_OUTPUT_RELATIVE = Path("outputs/fault-experiments-v2-2-n09")
N07_OUTPUT_TREE_SHA256 = "sha256:0f22ad348cc53e91b6e9322c72d70029f1ea8aded00ccaa9e6ca38e95a3bdd68"
N08_OUTPUT_TREE_SHA256 = "sha256:350979d852eebb5b0ef314ea240208a94fca8775468d120478b52cf4a81cf4c9"
N06_OUTPUT_RELATIVE = Path("outputs/fault-experiments-v2-2")
PROTOCOL_ROOT = Path("docs/workshops/neurips-2026-v2-2")
FIXTURE_ROOT = Path("docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures")
MINIMUM_ROOT = FIXTURE_ROOT / "qualification-minimum"
PHASE_A_FIXTURE_ROOT = FIXTURE_ROOT / "preflight-base-v1"
PREFLIGHT_ROOT = FIXTURE_ROOT / "preflight"
EXPERIMENT_ROOT = FIXTURE_ROOT / "experiment-v1"
ACCEPTED_PHASE_A_ROOT = Path("outputs/fault-experiments-v2-2-phase-a-001/phase-a")
ACCEPTED_PHASE_A_SHA256 = "sha256:f4c04cdbb841a4749053a0d38cae2dba84fda17ee7102e5d96b8ec89d0b0cf10"
ACCEPTED_PHASE_A_FILE_SHA256 = "sha256:bad8742936c1c102e29c9470beb125374b095bec2c95329de98cc7615933fbdb"
ACCEPTED_PHASE_A_TREE_SHA256 = "sha256:20a44c62c120afed1f9dba82cdd87817fc0cc38b1c979023b0a36e5ea7a2b736"
N12_AUTHORIZATION_SHA256 = "sha256:9549b6ff9d38ab138270b9a420277c9b7857d6f7efbae1bd1b8f6d1c0c3f40f0"
PROTOCOL_CONTENT_SHA256 = "sha256:bcfcd1afc192a37b2619934ac62a85c17ee80b2dfd45157d92185be03c4145c1"
AUTHORING_SEED = 26082951
MUTATION_SEED = 260829107
EXPECTED_COUNTS = {
    "instances": 12,
    "captures": 12,
    "packages": 96,
    "reviews": 288,
    "repairs": 180,
}
N06_BINDINGS = {
    "authorization": (
        Path("instructions_between_agent_types/overseer/decisions/N06_v2_2_projection_correction_and_experiment_completion_authorization.json"),
        "sha256:71e769ea20900179cebbb1dd4909d6e1d6e0512cb86d7f424609baa413c2b6a2",
    ),
    "design_freeze": (
        Path("outputs/fault-experiments-v2-2/gate-0/n06-design-freeze-v2.json"),
        "sha256:cac6afe41c184f22c4c6571e7d90df90305c94ffcf199890a7afd3aeaefb660b",
    ),
    "tester_gate": (
        Path("outputs/fault-experiments-v2-2/gate-1/tester-isolation-gate.json"),
        "sha256:68d5755e37c10d4a0764ae4e4d94bc2f260cbd0e3cbc3e5f9eaa83593b10b000",
    ),
    "terminal": (
        Path("outputs/fault-experiments-v2-2/gate-2/experiment-incomplete.json"),
        "sha256:6319e23c63abab65f0c203ce7b9d3547082eed78cf3b591848b057a51560f572",
    ),
}
N07_BINDINGS = {
    "authorization": (
        Path("instructions_between_agent_types/overseer/decisions/N07_v2_2_execution_readiness_and_continuous_experiment_authorization.json"),
        N07_AUTHORITY_SHA256,
    ),
    "e0_freeze": (
        N07_OUTPUT_RELATIVE / "e0/n07-execution-readiness-freeze-v2.json",
        "sha256:ce0749d8e093035fd5e35cde0b5c161822c9502180e5be78a3f1239dd3839337",
    ),
    "e1_gate": (
        N07_OUTPUT_RELATIVE / "e1/tester-execution-readiness-gate.json",
        "sha256:4dcc261275f679b7a31dbde6e52aac81d8e06e3c85cccc62cec9dc5d2ea8972e",
    ),
    "authority_consumption": (
        N07_OUTPUT_RELATIVE / "authority-consumption.json",
        "sha256:6814bdbb256320e80a43a8eba999095bfbb283feaedfabd6436719ccf9f1e45f",
    ),
    "terminal": (
        N07_OUTPUT_RELATIVE / "terminal.json",
        "sha256:32117d2d0b91ef8a65784bd3302cf069ffd8649be9e4ac9edcc540ae234994e9",
    ),
}
N08_BINDINGS = {
    "authorization": (
        Path("instructions_between_agent_types/overseer/decisions/N08_v2_2_auth_boundary_correction_and_immediate_execution_authorization.json"),
        N08_AUTHORITY_SHA256,
    ),
    "correction_readiness": (
        N08_OUTPUT_RELATIVE / "readiness/correction-readiness.json",
        "sha256:a76ed9fd79fbb399209c0a1522a1ce3e95a3f6b84a5b74a3709851dc9581136b",
    ),
    "live_readiness": (
        N08_OUTPUT_RELATIVE / "readiness/live.json",
        "sha256:94aeb312e1bffa82a4552027a718bc9e9793693e8741619181ad1bc52fc34bd8",
    ),
    "authority_consumption": (
        N08_OUTPUT_RELATIVE / "authority-consumption.json",
        "sha256:7f8a0960a492fb82e6a10c544d688f0de9f46f6423658eef31eaf949a634a02d",
    ),
    "terminal": (
        N08_OUTPUT_RELATIVE / "terminal.json",
        "sha256:8b880f71c3056a1832875d7555f51fce66a52fa0285daebbb0765ede87c97ed5",
    ),
}
N08_CANDIDATE_BINDINGS = {
    "response": (
        N08_OUTPUT_RELATIVE / "provider-branches/branch-000-1697f120f2f92b0a/output/response.json",
        "sha256:4b480a4441a3fc1d33f985f54e22cf7e28412ae89c791720fa042f02d596db5a",
    ),
    "prompt": (
        N08_OUTPUT_RELATIVE / "provider-branches/branch-000-1697f120f2f92b0a/evidence/prompt.md",
        "sha256:47ba1ed03f897ca1378c8f0751bc3a9a5f542fc158d62abebe2c668493e5554f",
    ),
    "schema": (
        N08_OUTPUT_RELATIVE / "provider-branches/branch-000-1697f120f2f92b0a/evidence/schema.json",
        "sha256:73638606663573f870b0869359de5acdb096edea61d2a24899ca2f2dc7578290",
    ),
    "branch_manifest": (
        N08_OUTPUT_RELATIVE / "provider-branches/branch-000-1697f120f2f92b0a/branch-manifest.json",
        "sha256:ab9416fb7509f08b676b8bf45f745e1158cbd82e39028346e262ffd04c9be6f8",
    ),
    "event_stream": (
        N08_OUTPUT_RELATIVE / "provider-branches/branch-000-1697f120f2f92b0a/output/codex-events.jsonl",
        "sha256:dc92806b2cb750bf2111d2730f1c5a03fc7739a73a9050b1a3a13769c89f7308",
    ),
    "transport_call_record": (
        N08_OUTPUT_RELATIVE / "ledger/call-attempt/call-000-4fb6f9466c8f180a.json",
        "sha256:2e6bb664fa84f1d6d83e8c2250283fb6cdd2d9ea339a46ca92682c5405dd66d7",
    ),
    "controller_call_record": (
        N08_OUTPUT_RELATIVE / "ledger/call-attempt/call-000-7f0cbe002dd71ffe.json",
        "sha256:867aee1847243d7b9d0ba9b870fc01b8500744387a59c55e7479d450d68df4b9",
    ),
}
N08_CANDIDATE_USAGE = {
    "input_tokens": 14534,
    "cached_input_tokens": 1408,
    "output_tokens": 6050,
}
N08_TEST_COMMANDS = (
    "PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_n05_runner.py' -v",
    "PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_n10_program.py' -v",
)
N09_TEST_COMMANDS = N08_TEST_COMMANDS
STAGES = (
    "phase_a",
    "construction",
    "capture",
    "package",
    "review",
    "repair",
    "closure",
    "analysis",
    "replay",
)
Provider = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"N07 expected one JSON object: {path}")
    return value


def _verify_self_hash(path: Path, field: str) -> str:
    value = _load_json(path)
    expected = value.pop(field, None)
    observed = sha256_bytes(canonical_json(value))
    if expected != observed:
        raise ValueError(f"accepted Phase-A self-hash mismatch: {path.name}")
    return observed


def verify_accepted_phase_a(repo_root: Path) -> dict[str, Any]:
    """Verify the exact accepted checkpoint without executing or copying it."""
    root = (repo_root / ACCEPTED_PHASE_A_ROOT).resolve()
    summary_path = root / "fixture.json"
    if sha256_file(summary_path) != ACCEPTED_PHASE_A_FILE_SHA256:
        raise ValueError("accepted Phase-A summary byte hash mismatch")
    summary = _load_json(summary_path)
    expected = summary.pop("phase_a_sha256", None)
    observed = sha256_bytes(canonical_json(summary))
    if expected != ACCEPTED_PHASE_A_SHA256 or observed != ACCEPTED_PHASE_A_SHA256:
        raise ValueError("accepted Phase-A canonical hash mismatch")

    files = [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    tree_sha256 = sha256_bytes(canonical_json(files))
    if len(files) != 11 or tree_sha256 != ACCEPTED_PHASE_A_TREE_SHA256:
        raise ValueError("accepted Phase-A 11-file tree mismatch")

    full_summary = _load_json(summary_path)
    for job_id, sources in full_summary["source_hashes"].items():
        if len(sources) != 1:
            raise ValueError("accepted Phase-A source manifest is not exact")
        for relative, source_sha256 in sources.items():
            if sha256_file(root / "frozen" / relative) != source_sha256:
                raise ValueError(f"accepted Phase-A source hash mismatch: {job_id}")
    self_hashes = {
        "boundaries": _verify_self_hash(root / "frozen/boundaries.json", "boundary_manifest_sha256"),
        "reference_capture": _verify_self_hash(root / "reference/capture-manifest.json", "capture_sha256"),
        "mutant_capture": _verify_self_hash(root / "mutant/capture-manifest.json", "capture_sha256"),
        "mutation": _verify_self_hash(root / "mutant/mutation.json", "mutation_sha256"),
    }
    if self_hashes != {
        "boundaries": full_summary["boundary_manifest_sha256"],
        "reference_capture": full_summary["reference_capture_sha256"],
        "mutant_capture": full_summary["mutant_capture_sha256"],
        "mutation": _load_json(root / "mutant/mutation.json")["mutation_sha256"],
    }:
        raise ValueError("accepted Phase-A summary references changed")
    if full_summary["mutation_diff_sha256"] != _load_json(root / "mutant/mutation.json")["diff_sha256"]:
        raise ValueError("accepted Phase-A mutation diff binding changed")
    return {
        "status": "verified_accepted_checkpoint",
        "artifact_root": ACCEPTED_PHASE_A_ROOT.as_posix(),
        "phase_a_sha256": ACCEPTED_PHASE_A_SHA256,
        "phase_a_summary_file_sha256": ACCEPTED_PHASE_A_FILE_SHA256,
        "phase_a_tree_sha256": tree_sha256,
        "file_count": len(files),
        "self_hashes": self_hashes,
        "nested_snapshot_hashes_independently_recomputed": False,
        "model_visible": False,
    }


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _qualification_authority(path: Path, output_root: Path) -> dict[str, Any]:
    authority = _load_json(path)
    required = {
        "schema_version": "1",
        "purpose": "n07_no_model_lifecycle_qualification",
        "real_scientific_authority": False,
        "model_calls_authorized": 0,
        "allowed_output_root": str(output_root.resolve()),
    }
    if any(authority.get(key) != value for key, value in required.items()):
        raise ValueError("N07 qualification authority is invalid for this output root")
    if not str(authority.get("authority_id") or "").strip():
        raise ValueError("N07 qualification authority lacks a stable authority_id")
    return authority


def _validate_assets(repo_root: Path) -> dict[str, Any]:
    authority = repo_root / (
        "instructions_between_agent_types/overseer/decisions/"
        "N07_v2_2_execution_readiness_and_continuous_experiment_authorization.json"
    )
    if sha256_file(authority) != N07_AUTHORITY_SHA256:
        raise ValueError("N07 controlling authorization hash mismatch")
    protocol_json = repo_root / PROTOCOL_ROOT / "experiment-protocol.json"
    protocol_markdown = repo_root / PROTOCOL_ROOT / "EXPERIMENT_PROTOCOL.md"
    if sha256_file(protocol_json) != "sha256:f30e3a38c4bfaf238dd313978fb02c2a651d85a024b9c0d539c72ecc5605fc4a":
        raise ValueError("N07 protocol JSON changed")
    if sha256_file(protocol_markdown) != "sha256:7e8fa19b674d7cbb378af428e3ffd97b8362a4ef44170631bf97a79faf7d8062":
        raise ValueError("N07 protocol Markdown changed")
    protocol = _load_json(protocol_json)
    if protocol.get("integrity", {}).get("content_hash") != PROTOCOL_CONTENT_SHA256:
        raise ValueError("N07 protocol content hash changed")
    trees = {
        "prompts": _tree_contract(repo_root, repo_root / "prompts/v2_2"),
        "schemas": _tree_contract(repo_root, repo_root / "schemas/v2_2"),
        "inputs": _tree_contract(repo_root, repo_root / FIXTURE_ROOT),
    }
    expected_trees = {
        "prompts": "sha256:e3cb1546b426c2411c51202dc494e10fb9ce2db683330671703d6ed1decab428",
        "schemas": "sha256:5def4a20cfbd18a6465e5425e1c8aee0ea8b47842c9c370e0d5268c11c41a168",
        "inputs": "sha256:59b4ad6d66ef3b80d1acad50bbf1f1896da83c4097da0b8274f57030d02dc907",
    }
    if any(trees[name]["tree_sha256"] != digest for name, digest in expected_trees.items()):
        raise ValueError("N07 frozen prompt, schema, or input tree changed")
    scenario = _load_json(repo_root / PREFLIGHT_ROOT / "scenario.json")
    if scenario.get("authoring_seed") != AUTHORING_SEED or scenario.get("mutation_seed") != MUTATION_SEED:
        raise ValueError("N07 frozen seeds changed")
    preservation = {}
    for name, (relative, expected) in N06_BINDINGS.items():
        path = repo_root / relative
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"N07 N06 preservation mismatch: {name}")
        preservation[name] = {"path": relative.as_posix(), "sha256": actual}
    if sys.version.split()[0] != "3.12.3":
        raise ValueError("N07 requires Python 3.12.3")
    if importlib.metadata.version("etiq-copilot") != "2.3.0":
        raise ValueError("N07 requires etiq-copilot==2.3.0")
    launcher = launch_policy_identity()
    if launcher["sandbox_backend_version"] != "bubblewrap 0.9.0":
        raise ValueError("N07 Bubblewrap identity changed")
    if shutil.which("codex") is None or not (Path.home() / ".codex/auth.json").is_file():
        raise ValueError("N07 Codex runtime or auth boundary is unavailable")
    required_functions = {
        "execute_two_job_chain": execute_two_job_chain,
        "derive_review_evidence": derive_review_evidence,
        "build_phase_a_base": build_phase_a_base,
        "qualify_realized_chain": qualify_realized_chain,
        "build_n05_condition_package": build_n05_condition_package,
        "materialize_branch_package": materialize_branch_package,
        "run_review_repair_dry_run": run_review_repair_dry_run,
        "reconcile_records": reconcile_records,
        "analyze_frozen_results": analyze_frozen_results,
        "offline_replay": offline_replay,
    }
    if any(not callable(value) for value in required_functions.values()):
        raise ValueError("N07 lifecycle function inventory is incomplete")
    return {
        "authority_sha256": sha256_file(authority),
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "protocol_json_sha256": sha256_file(protocol_json),
        "protocol_markdown_sha256": sha256_file(protocol_markdown),
        "trees": trees,
        "seeds": {"authoring": AUTHORING_SEED, "mutation": MUTATION_SEED},
        "preservation": preservation,
        "environment": {
            "python": sys.version.split()[0],
            "etiq_copilot": importlib.metadata.version("etiq-copilot"),
            "bubblewrap": bubblewrap_version(),
        },
        "launcher": launcher,
        "required_functions": sorted(required_functions),
    }


def _validate_tester_gate(output_root: Path, tester_gate_path: Path) -> dict[str, Any]:
    gate = _load_json(tester_gate_path)
    relative = Path(str(gate.get("design_freeze_path") or ""))
    if relative.is_absolute() or ".." in relative.parts or relative.parent != Path("e0"):
        raise ValueError("N07 Tester result has an invalid E0 freeze path")
    freeze_path = output_root / relative
    freeze = _load_json(freeze_path)
    required = {
        "status": "passed",
        "gate": "E1_single_execution_readiness",
        "n07_authorization_sha256": N07_AUTHORITY_SHA256,
        "design_freeze_sha256": sha256_file(freeze_path),
        "freeze_content_sha256": freeze.get("freeze_sha256"),
        "observed_counts": EXPECTED_COUNTS,
        "real_model_calls": 0,
    }
    if any(gate.get(key) != value for key, value in required.items()):
        raise ValueError("N07 Tester result does not bind the exact E0 freeze")
    signature = str(gate.get("tester_signature") or "")
    unsigned = dict(gate)
    unsigned.pop("tester_signature", None)
    if signature != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("N07 Tester signature is invalid")
    return {**gate, "validated_design_freeze_path": str(relative)}


def _validate_output_state(output_root: Path, *, live: bool) -> dict[str, Any]:
    if _inside(output_root, output_root.parent / N06_OUTPUT_RELATIVE.name):
        raise ValueError("N07 must not use the immutable N06 output root")
    files = sorted(path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file()) if output_root.exists() else []
    if not files:
        return {"state": "empty", "files": 0}
    terminal = output_root / "terminal.json"
    if terminal.is_file():
        return {"state": "terminal", "files": len(files), "terminal_sha256": sha256_file(terminal)}
    allowed_prefixes = ("readiness/", "e0/", "e1/", "test-outputs/")
    if not live and all(path.startswith(allowed_prefixes) for path in files):
        return {"state": "engineering", "files": len(files)}
    consumption = output_root / "authority-consumption.json"
    checkpoints = output_root / "checkpoints"
    if consumption.is_file() and checkpoints.is_dir():
        return {"state": "resumable", "files": len(files), "checkpoint_count": len(list(checkpoints.glob("*.json")))}
    if live and all(path.startswith(allowed_prefixes) for path in files):
        return {"state": "engineering", "files": len(files)}
    raise ValueError("N07 output root contains a non-resumable partial state")


def validate_n07_readiness(
    repo_root: Path,
    output_root: Path,
    *,
    qualification_authority: Path | None = None,
    tester_gate_path: Path | None = None,
    live: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    old_root = (repo_root / N06_OUTPUT_RELATIVE).resolve()
    if output_root == old_root or _inside(old_root, output_root):
        raise ValueError("N07 output root overlaps immutable N06")
    if live and output_root != (repo_root / N07_OUTPUT_RELATIVE).resolve():
        raise ValueError("N07 live execution requires the exact fresh N07 output root")
    authority = None
    if qualification_authority is not None:
        authority = _qualification_authority(qualification_authority.resolve(), output_root)
    elif not live:
        raise ValueError("N07 engineering modes require a qualification authority")
    bindings = _validate_assets(repo_root)
    state = _validate_output_state(output_root, live=live)
    gate = None
    if live:
        if tester_gate_path is None:
            raise ValueError("N07 live execution requires the signed E1 Tester result")
        gate = _validate_tester_gate(output_root, tester_gate_path.resolve())
    return {
        "schema_version": "1",
        "status": "ready",
        "mode": "live" if live else "qualification",
        "output_root": str(output_root),
        "output_state": state,
        "qualification_authority_sha256": sha256_file(qualification_authority.resolve()) if qualification_authority else None,
        "qualification_authority_id": authority.get("authority_id") if authority else None,
        "tester_gate_sha256": sha256_file(tester_gate_path.resolve()) if gate and tester_gate_path else None,
        "tester_signature": gate.get("tester_signature") if gate else None,
        "design_freeze_path": gate.get("validated_design_freeze_path") if gate else None,
        "design_freeze_sha256": (
            sha256_file(output_root / str(gate["validated_design_freeze_path"]))
            if gate
            else None
        ),
        "bindings": bindings,
        "expected_counts": EXPECTED_COUNTS,
        "real_model_calls": 0,
        "consumption_created": False,
    }


def _validate_n07_preservation(repo_root: Path) -> dict[str, Any]:
    files = {}
    for name, (relative, expected) in N07_BINDINGS.items():
        actual = sha256_file(repo_root / relative)
        if actual != expected:
            raise ValueError(f"N08 N07 preservation mismatch: {name}")
        files[name] = {"path": relative.as_posix(), "sha256": actual}
    tree = _tree_contract(repo_root, repo_root / N07_OUTPUT_RELATIVE)
    if tree["tree_sha256"] != N07_OUTPUT_TREE_SHA256:
        raise ValueError("N08 immutable N07 output tree changed")
    return {
        "files": files,
        "output_tree": {
            "root": N07_OUTPUT_RELATIVE.as_posix(),
            "tree_sha256": tree["tree_sha256"],
            "file_count": len(tree["files"]),
            "total_bytes": sum(item["bytes"] for item in tree["files"]),
        },
    }


def _validate_n08_assets(
    repo_root: Path,
    *,
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    authority = repo_root / (
        "instructions_between_agent_types/overseer/decisions/"
        "N08_v2_2_auth_boundary_correction_and_immediate_execution_authorization.json"
    )
    if sha256_file(authority) != N08_AUTHORITY_SHA256:
        raise ValueError("N08 controlling authorization hash mismatch")
    bindings = _validate_assets(repo_root)
    preservation = _validate_n07_preservation(repo_root)
    codex_home = source_codex_home or Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    )
    auth_path = codex_home / "auth.json"
    if auth_path.is_symlink() or not auth_path.is_file():
        raise ValueError("N08 Codex auth source is missing or is not a regular file")
    codex_bin = Path(shutil.which("codex") or "").resolve(strict=True)
    return {
        **bindings,
        "n08_authority_sha256": sha256_file(authority),
        "n07_preservation": preservation,
        "codex": {
            "executable": str(codex_bin),
            "executable_sha256": sha256_file(codex_bin),
            "auth_source": str(auth_path.resolve()),
            "auth_source_sha256": sha256_file(auth_path),
        },
    }


def _validate_n08_output_state(output_root: Path) -> dict[str, Any]:
    files = (
        sorted(path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file())
        if output_root.exists()
        else []
    )
    if not files:
        return {"state": "empty", "files": 0}
    if (output_root / "terminal.json").is_file():
        return {
            "state": "terminal",
            "files": len(files),
            "terminal_sha256": sha256_file(output_root / "terminal.json"),
        }
    if all(path.startswith("readiness/") for path in files):
        return {"state": "readiness", "files": len(files)}
    raise ValueError("N08 output root contains a partial or consumed execution")


def _validate_correction_readiness(repo_root: Path, output_root: Path) -> dict[str, Any]:
    path = output_root / "readiness/correction-readiness.json"
    record = _load_json(path)
    recorded_hash = record.get("correction_readiness_sha256")
    unsigned = dict(record)
    unsigned.pop("correction_readiness_sha256", None)
    if recorded_hash != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("N08 correction-readiness record hash mismatch")
    required = {
        "status": "passed",
        "n08_authority_sha256": N08_AUTHORITY_SHA256,
        "real_model_calls": 0,
    }
    if any(record.get(key) != value for key, value in required.items()):
        raise ValueError("N08 correction-readiness record is not a zero-model pass")
    if record.get("n07_preservation") != _validate_n07_preservation(repo_root):
        raise ValueError("N08 correction-readiness N07 preservation changed")
    tests = record.get("tests")
    if not isinstance(tests, list) or [item.get("command") for item in tests] != list(N08_TEST_COMMANDS):
        raise ValueError("N08 correction-readiness commands are incomplete")
    for item in tests:
        result_path = repo_root / str(item.get("output_path") or "")
        if (
            item.get("status") != "passed"
            or item.get("failures") != 0
            or item.get("errors") != 0
            or item.get("skips") != 0
            or sha256_file(result_path) != item.get("output_sha256")
        ):
            raise ValueError("N08 correction-readiness test output changed or failed")
    governed_files = record.get("governed_files")
    required_governed_paths = {
        "src/use_case_icp/n07_program.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/__main__.py",
        "tests/test_n05_runner.py",
        "tests/test_n10_program.py",
    }
    if not isinstance(governed_files, list) or {
        item.get("path") for item in governed_files
    } != required_governed_paths:
        raise ValueError("N08 correction-readiness governed file set is incomplete")
    for item in governed_files:
        if sha256_file(repo_root / str(item["path"])) != item.get("sha256"):
            raise ValueError("N08 governed source or test changed after readiness")
    regression = record.get("production_auth_boundary_regression", {})
    if regression.get("status") != "passed" or regression.get("real_model_calls") != 0:
        raise ValueError("N08 production authentication regression did not pass")
    return {**record, "file_sha256": sha256_file(path), "path": str(path)}


def validate_n08_readiness(
    repo_root: Path,
    output_root: Path,
    *,
    source_codex_home: Path | None = None,
    require_correction_readiness: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    if output_root != (repo_root / N08_OUTPUT_RELATIVE).resolve():
        raise ValueError("N08 live execution requires the exact fresh N08 output root")
    bindings = _validate_n08_assets(repo_root, source_codex_home=source_codex_home)
    state = _validate_n08_output_state(output_root)
    correction = (
        _validate_correction_readiness(repo_root, output_root)
        if require_correction_readiness
        else None
    )
    return {
        "schema_version": "1",
        "status": "ready",
        "mode": "live" if require_correction_readiness else "check_ready",
        "output_root": str(output_root),
        "output_state": state,
        "bindings": bindings,
        "correction_readiness_sha256": correction.get("file_sha256") if correction else None,
        "correction_readiness_content_sha256": correction.get("correction_readiness_sha256") if correction else None,
        "expected_counts": EXPECTED_COUNTS,
        "real_model_calls": 0,
        "consumption_created": False,
    }


def write_n08_correction_readiness(
    repo_root: Path,
    output_root: Path,
    *,
    test_runs: list[Mapping[str, Any]],
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    readiness = validate_n08_readiness(
        repo_root,
        output_root,
        source_codex_home=source_codex_home,
    )
    if [item.get("command") for item in test_runs] != list(N08_TEST_COMMANDS):
        raise ValueError("N08 correction-readiness requires the three exact focused commands")
    tests = []
    regression_passed = False
    test_output_root = (output_root / "readiness/test-outputs").resolve()
    for item in test_runs:
        output_path = Path(str(item.get("output_path") or "")).resolve()
        if not _inside(test_output_root, output_path):
            raise ValueError("N08 test output is outside the readiness test-output root")
        text = output_path.read_text(errors="replace")
        match = re.search(r"Ran (\d+) tests? in ", text)
        if not match or not text.rstrip().endswith("OK") or "FAILED" in text or "skipped=" in text:
            raise ValueError("N08 focused test output is not a zero-skip pass")
        if "test_live_provider_copies_only_auth_before_transport" in text:
            regression_passed = True
        tests.append(
            {
                "command": item["command"],
                "status": "passed",
                "tests_run": int(match.group(1)),
                "failures": 0,
                "errors": 0,
                "skips": 0,
                "output_path": output_path.relative_to(repo_root).as_posix(),
                "output_sha256": sha256_file(output_path),
            }
        )
    if not regression_passed:
        raise ValueError("N08 production authentication boundary regression is absent")
    governed_paths = (
        "src/use_case_icp/n07_program.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/__main__.py",
        "tests/test_n05_runner.py",
        "tests/test_n10_program.py",
    )
    record = {
        "schema_version": "1",
        "status": "passed",
        "purpose": "n08_localized_auth_boundary_correction_readiness",
        "n08_authority_sha256": N08_AUTHORITY_SHA256,
        "n07_preservation": readiness["bindings"]["n07_preservation"],
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "environment": readiness["bindings"]["environment"],
        "launcher": readiness["bindings"]["launcher"],
        "codex": readiness["bindings"]["codex"],
        "governed_files": [_file_contract(repo_root, repo_root / path) for path in governed_paths],
        "tests": tests,
        "production_auth_boundary_regression": {
            "status": "passed",
            "adapter": "n07_program._live_provider",
            "real_branch_materialization": True,
            "real_auth_copy": True,
            "transport_substitution_only": True,
            "transport_calls": 1,
            "real_model_calls": 0,
        },
        "real_model_calls": 0,
    }
    record["correction_readiness_sha256"] = sha256_bytes(canonical_json(record))
    path = output_root / "readiness/correction-readiness.json"
    digest = create_json_exclusive(path, record)
    return {**record, "file_sha256": digest, "path": str(path)}


def _validate_n08_preservation(repo_root: Path) -> dict[str, Any]:
    files = {}
    for name, (relative, expected) in {**N08_BINDINGS, **N08_CANDIDATE_BINDINGS}.items():
        actual = sha256_file(repo_root / relative)
        if actual != expected:
            raise ValueError(f"N09 N08 preservation mismatch: {name}")
        files[name] = {"path": relative.as_posix(), "sha256": actual}
    tree = _tree_contract(repo_root, repo_root / N08_OUTPUT_RELATIVE)
    if tree["tree_sha256"] != N08_OUTPUT_TREE_SHA256:
        raise ValueError("N09 immutable N08 output tree changed")
    transport = _load_json(repo_root / N08_CANDIDATE_BINDINGS["transport_call_record"][0])
    controller = _load_json(repo_root / N08_CANDIDATE_BINDINGS["controller_call_record"][0])
    transport_usage = transport.get("payload", {}).get("result", {}).get("usage")
    controller_result = controller.get("payload", {}).get("result", {}).get("response", {})
    if transport_usage != N08_CANDIDATE_USAGE or controller_result.get("usage") != N08_CANDIDATE_USAGE:
        raise ValueError("N09 N08 imported-candidate usage mismatch")
    if controller_result.get("real_model_call") is not True:
        raise ValueError("N09 N08 imported candidate lacks real-call provenance")
    return {
        "files": files,
        "output_tree": {
            "root": N08_OUTPUT_RELATIVE.as_posix(),
            "tree_sha256": tree["tree_sha256"],
            "file_count": len(tree["files"]),
            "total_bytes": sum(item["bytes"] for item in tree["files"]),
        },
        "candidate_usage": N08_CANDIDATE_USAGE,
    }


def _validate_n09_assets(
    repo_root: Path,
    *,
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    authority = repo_root / (
        "instructions_between_agent_types/overseer/decisions/"
        "N09_v2_2_live_mode_guard_correction_and_phase_a_continuation_authorization.json"
    )
    if sha256_file(authority) != N09_AUTHORITY_SHA256:
        raise ValueError("N09 controlling authorization hash mismatch")
    bindings = _validate_n08_assets(repo_root, source_codex_home=source_codex_home)
    return {
        **bindings,
        "n09_authority_sha256": sha256_file(authority),
        "n08_preservation": _validate_n08_preservation(repo_root),
    }


def _validate_n09_output_state(output_root: Path) -> dict[str, Any]:
    files = (
        sorted(path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file())
        if output_root.exists()
        else []
    )
    if not files:
        return {"state": "empty", "files": 0}
    if (output_root / "terminal.json").is_file():
        return {
            "state": "terminal",
            "files": len(files),
            "terminal_sha256": sha256_file(output_root / "terminal.json"),
        }
    if all(path.startswith("readiness/") for path in files):
        return {"state": "readiness", "files": len(files)}
    raise ValueError("N09 output root contains a partial or consumed execution")


def _validate_n09_correction_readiness(repo_root: Path, output_root: Path) -> dict[str, Any]:
    path = output_root / "readiness/correction-readiness.json"
    record = _load_json(path)
    content_hash = record.get("correction_readiness_sha256")
    unsigned = dict(record)
    unsigned.pop("correction_readiness_sha256", None)
    if content_hash != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("N09 correction-readiness record hash mismatch")
    if (
        record.get("status") != "passed"
        or record.get("n09_authority_sha256") != N09_AUTHORITY_SHA256
        or record.get("real_model_calls") != 0
        or record.get("n08_preservation") != _validate_n08_preservation(repo_root)
    ):
        raise ValueError("N09 correction-readiness bindings changed or did not pass")
    tests = record.get("tests")
    if not isinstance(tests, list) or [item.get("command") for item in tests] != list(N09_TEST_COMMANDS):
        raise ValueError("N09 correction-readiness commands are incomplete")
    for item in tests:
        result_path = repo_root / str(item.get("output_path") or "")
        if (
            item.get("status") != "passed"
            or item.get("failures") != 0
            or item.get("errors") != 0
            or item.get("skips") != 0
            or sha256_file(result_path) != item.get("output_sha256")
        ):
            raise ValueError("N09 correction-readiness test output changed or failed")
    required_paths = {
        "src/use_case_icp/n07_program.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/__main__.py",
        "tests/test_n05_runner.py",
        "tests/test_n10_program.py",
    }
    governed = record.get("governed_files")
    if not isinstance(governed, list) or {item.get("path") for item in governed} != required_paths:
        raise ValueError("N09 correction-readiness governed file set is incomplete")
    for item in governed:
        if sha256_file(repo_root / str(item["path"])) != item.get("sha256"):
            raise ValueError("N09 governed source or test changed after readiness")
    return {**record, "file_sha256": sha256_file(path), "path": str(path)}


def validate_n09_readiness(
    repo_root: Path,
    output_root: Path,
    *,
    source_codex_home: Path | None = None,
    require_correction_readiness: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    if output_root != (repo_root / N09_OUTPUT_RELATIVE).resolve():
        raise ValueError("N09 live execution requires the exact fresh N09 output root")
    bindings = _validate_n09_assets(repo_root, source_codex_home=source_codex_home)
    correction = (
        _validate_n09_correction_readiness(repo_root, output_root)
        if require_correction_readiness
        else None
    )
    return {
        "schema_version": "1",
        "status": "ready",
        "mode": "live" if require_correction_readiness else "check_ready",
        "output_root": str(output_root),
        "output_state": _validate_n09_output_state(output_root),
        "bindings": bindings,
        "correction_readiness_sha256": correction.get("file_sha256") if correction else None,
        "correction_readiness_content_sha256": correction.get("correction_readiness_sha256") if correction else None,
        "candidate_set": {
            "continued": 1,
            "additional_sets": 0,
            "imported_candidate": 1,
            "remaining_authoring_candidates": [2, 3],
            "maximum_stabilizations_per_candidate": 3,
        },
        "expected_counts": EXPECTED_COUNTS,
        "real_model_calls": 0,
        "consumption_created": False,
    }


def write_n09_correction_readiness(
    repo_root: Path,
    output_root: Path,
    *,
    test_runs: list[Mapping[str, Any]],
    source_codex_home: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    readiness = validate_n09_readiness(
        repo_root,
        output_root,
        source_codex_home=source_codex_home,
    )
    if [item.get("command") for item in test_runs] != list(N09_TEST_COMMANDS):
        raise ValueError("N09 correction-readiness requires the exact focused commands")
    tests = []
    test_output_root = (output_root / "readiness/test-outputs").resolve()
    for item in test_runs:
        output_path = Path(str(item.get("output_path") or "")).resolve()
        if not _inside(test_output_root, output_path):
            raise ValueError("N09 test output is outside the readiness test-output root")
        text = output_path.read_text(errors="replace")
        match = re.search(r"Ran (\d+) tests? in ", text)
        if not match or not text.rstrip().endswith("OK") or "FAILED" in text or "skipped=" in text:
            raise ValueError("N09 focused test output is not a zero-skip pass")
        tests.append(
            {
                "command": item["command"],
                "status": "passed",
                "tests_run": int(match.group(1)),
                "failures": 0,
                "errors": 0,
                "skips": 0,
                "output_path": output_path.relative_to(repo_root).as_posix(),
                "output_sha256": sha256_file(output_path),
            }
        )
    governed_paths = (
        "src/use_case_icp/n07_program.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/__main__.py",
        "tests/test_n05_runner.py",
        "tests/test_n10_program.py",
    )
    record = {
        "schema_version": "1",
        "status": "passed",
        "purpose": "n09_live_mode_guard_and_existing_candidate_continuation_readiness",
        "n09_authority_sha256": N09_AUTHORITY_SHA256,
        "n08_preservation": readiness["bindings"]["n08_preservation"],
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "environment": readiness["bindings"]["environment"],
        "launcher": readiness["bindings"]["launcher"],
        "codex": readiness["bindings"]["codex"],
        "governed_files": [_file_contract(repo_root, repo_root / path) for path in governed_paths],
        "tests": tests,
        "candidate_budget": readiness["candidate_set"],
        "real_model_calls": 0,
    }
    record["correction_readiness_sha256"] = sha256_bytes(canonical_json(record))
    path = output_root / "readiness/correction-readiness.json"
    digest = create_json_exclusive(path, record)
    return {**record, "file_sha256": digest, "path": str(path)}


def _write_readiness(output_root: Path, readiness: Mapping[str, Any], name: str) -> Path:
    path = output_root / "readiness" / f"{name}.json"
    create_json_exclusive(path, readiness)
    return path


def _consume_authority(
    output_root: Path,
    readiness: Mapping[str, Any],
    *,
    qualification: bool,
) -> dict[str, Any]:
    if (output_root / "terminal.json").exists():
        raise RuntimeError("N07 is terminal and cannot consume another authority")
    if (output_root / "authority-consumption.json").exists():
        raise RuntimeError("N07 one-use authority is already consumed")
    consumption = {
        "schema_version": "1",
        "status": "consumed_in_progress",
        "authority_kind": "temporary_no_model_qualification" if qualification else "n07_live_scientific",
        "candidate_sets_consumed": 1,
        "maximum_candidates": 3,
        "maximum_stabilizations_per_candidate": 3,
        "provider_attempts_per_logical_request": 3,
        "authoring_seed": AUTHORING_SEED,
        "mutation_seed": MUTATION_SEED,
        "expected_counts": EXPECTED_COUNTS,
        "output_root": str(output_root.resolve()),
        "n07_authorization_sha256": N07_AUTHORITY_SHA256,
        "readiness_sha256": sha256_bytes(canonical_json(readiness)),
        "qualification_authority_sha256": readiness.get("qualification_authority_sha256"),
        "design_freeze_sha256": readiness.get("design_freeze_sha256"),
        "tester_gate_sha256": readiness.get("tester_gate_sha256"),
        "tester_signature": readiness.get("tester_signature"),
        "real_model_calls_authorized": 0 if qualification else None,
    }
    digest = create_json_exclusive(output_root / "authority-consumption.json", consumption)
    return {**consumption, "record_sha256": digest}


def _consume_n08_authority(
    output_root: Path,
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    if (output_root / "terminal.json").exists():
        raise RuntimeError("N08 is terminal and cannot consume another authority")
    if (output_root / "authority-consumption.json").exists():
        raise RuntimeError("N08 one-use authority is already consumed")
    consumption = {
        "schema_version": "1",
        "status": "consumed_in_progress",
        "authority_kind": "n08_live_scientific",
        "candidate_sets_consumed": 1,
        "maximum_candidates": 3,
        "maximum_stabilizations_per_candidate": 3,
        "provider_attempts_per_logical_request": 3,
        "authoring_seed": AUTHORING_SEED,
        "mutation_seed": MUTATION_SEED,
        "expected_counts": EXPECTED_COUNTS,
        "output_root": str(output_root.resolve()),
        "n08_authorization_sha256": N08_AUTHORITY_SHA256,
        "n07_preservation": readiness["bindings"]["n07_preservation"],
        "readiness_sha256": sha256_bytes(canonical_json(readiness)),
        "correction_readiness_sha256": readiness["correction_readiness_sha256"],
        "correction_readiness_content_sha256": readiness[
            "correction_readiness_content_sha256"
        ],
    }
    digest = create_json_exclusive(output_root / "authority-consumption.json", consumption)
    return {**consumption, "record_sha256": digest}


def _consume_n09_authority(
    output_root: Path,
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    if (output_root / "terminal.json").exists():
        raise RuntimeError("N09 is terminal and cannot consume another authority")
    if (output_root / "authority-consumption.json").exists():
        raise RuntimeError("N09 one-use continuation authority is already consumed")
    consumption = {
        "schema_version": "1",
        "status": "consumed_in_progress",
        "authority_kind": "n09_existing_candidate_set_continuation",
        "candidate_sets_continued": 1,
        "additional_candidate_sets": 0,
        "imported_candidate": 1,
        "remaining_authoring_candidates": [2, 3],
        "maximum_stabilizations_per_candidate": 3,
        "provider_attempts_per_logical_request": 3,
        "authoring_seed": AUTHORING_SEED,
        "mutation_seed": MUTATION_SEED,
        "expected_counts": EXPECTED_COUNTS,
        "output_root": str(output_root.resolve()),
        "n09_authorization_sha256": N09_AUTHORITY_SHA256,
        "n08_preservation": readiness["bindings"]["n08_preservation"],
        "readiness_sha256": sha256_bytes(canonical_json(readiness)),
        "correction_readiness_sha256": readiness["correction_readiness_sha256"],
        "correction_readiness_content_sha256": readiness[
            "correction_readiness_content_sha256"
        ],
    }
    digest = create_json_exclusive(output_root / "authority-consumption.json", consumption)
    return {**consumption, "record_sha256": digest}


def _qualification_provider(repo_root: Path) -> Provider:
    fixture, jobs = load_qualification_fixture(repo_root, MINIMUM_ROOT)
    slots_by_id = {
        "ins-" + sha256_bytes(str(item["instance_id"]).encode())[7:23]: item
        for item in _protocol_instance_slots(repo_root)
    }
    authored = {
        "jobs": [
            {"job_id": job_id, "pipeline": _pipeline_payload(pipeline)}
            for job_id, pipeline in jobs.items()
        ],
        "complexity_claims": {
            "declared_boundary_count": 16,
            "exact_handoff_count": 2,
            "directly_executed_nested_helper_count": 2,
            "has_join_or_aggregation": True,
        },
        "qualification_fixture": fixture,
    }

    def authored_for_slot(request: Mapping[str, Any]) -> dict[str, Any]:
        response = json.loads(json.dumps(authored))
        opaque_instance_id = str(request["instance_id"])
        slot = slots_by_id[opaque_instance_id]
        instance_id = str(slot["instance_id"])
        slot_number = int(instance_id.split("-")[-1])
        by_job = {item["job_id"]: item["pipeline"] for item in response["jobs"]}
        if slot["designation"] == "no_injection_control":
            for pipeline in by_job.values():
                pipeline["files"][0]["content"] += f"\n# independent N10 slot {instance_id}\n"
            return response
        upstream_id, downstream_id = list(by_job)
        target_job_id = upstream_id if slot["target_job"] == "upstream" else downstream_id
        pipeline = by_job[target_job_id]
        source = pipeline["files"][0]["content"]
        if target_job_id == downstream_id:
            source = source.replace(
                "A matching capability identifier supplies direct evidence for this demand.",
                "m",
            ).replace(
                "No matching capability identifier exists, so this demand remains an evidenced gap.",
                "g",
            )
        qualified_name = "n10_slot_boundary"
        stage = {
            ("upstream", "early"): "upstream_demand_selection",
            ("upstream", "middle"): "upstream_evidence_normalization",
            ("upstream", "late"): "upstream_provenance_assembly",
            ("downstream", "early"): "downstream_coverage_mapping",
            ("downstream", "middle"): "downstream_prioritization",
            ("downstream", "late"): "downstream_synthesis",
        }[(slot["target_job"], slot["stage"])]
        snippets = {
            2: (
                "\ndef n10_slot_boundary(frame):\n"
                "    def apply(value):\n"
                "        sentinel = pd.DataFrame([{'record_id': 'n10-sentinel', 'source_id': 'n10', 'need': 'sentinel', 'demand_score': -1, 'source_weight': 1}])\n"
                "        combined = pd.concat([value, sentinel], ignore_index=True)\n"
                "        return combined[combined['demand_score'] >= 0].copy()\n"
                "    return apply(frame)\n\n"
            ),
            4: (
                "\ndef n10_slot_boundary(frame):\n"
                "    def apply(value):\n"
                "        keep = [0, 1, 2, 3, 4, 5, 6, 7]\n"
                "        return value.iloc[:len(keep)].copy()\n"
                "    return apply(frame)\n\n"
            ),
            6: (
                "\ndef n10_slot_boundary(frame):\n"
                "    def apply(value):\n"
                "        settings = {'count': len(value), 'fallback': 1}\n"
                "        return value.iloc[:settings.get('count', settings.get('fallback', 1))].copy()\n"
                "    return apply(frame)\n\n"
            ),
            8: (
                "\ndef n10_slot_boundary(frame):\n"
                "    def apply(value):\n"
                "        sentinel = pd.DataFrame([{'record_id': 'n10-fabricated-identifier-record', 'source_id': 'n10', 'need': 'sentinel', 'demand_score': 1, 'source_weight': 1}])\n"
                "        combined = pd.concat([value, sentinel], ignore_index=True)\n"
                "        return combined[combined['record_id'].str.startswith('n06-')].copy()\n"
                "    return apply(frame)\n\n"
            ),
            10: (
                "\ndef n10_slot_boundary(frame):\n"
                "    def apply(value):\n"
                "        records = value.to_dict(orient='records')\n"
                "        ordered = sorted(records, key=lambda row: row['priority_score'], reverse=True)\n"
                "        for index, row in enumerate(ordered):\n"
                "            row['priority_score'] = (len(ordered) - index) * 100\n"
                "        return pd.DataFrame(ordered)\n"
                "    return apply(frame)\n\n"
            ),
        }
        if slot_number == 3:
            marker = "ranked['final_score'] = ranked['priority_score'] + ranked['is_gap'].astype(int) * 10"
            if marker not in source:
                raise AssertionError("qualification prioritize marker is absent")
            source = source.replace(marker, marker[:-2] + "100", 1)
            pipeline["files"][0]["content"] = (
                source
                + f"\n# independent N10 slot {instance_id} candidate {int(request.get('candidate_number', 1))}\n"
            )
            return response
        if slot_number == 5:
            marker = "    return {'top_need': str(top['need']), 'decision': 'prioritize' if top['coverage'] != 'supported' else 'maintain'}"
            replacement = (
                "    c = ['maintain', 'prioritize']\n"
                "    return {'top_need': str(top['need']), 'decision': c[-1]}"
            )
            if marker not in source:
                raise AssertionError("qualification synthesis marker is absent")
            source = source.replace(marker, replacement, 1)
            pipeline["files"][0]["content"] = (
                source
                + f"\n# independent N10 slot {instance_id} candidate {int(request.get('candidate_number', 1))}\n"
            )
            return response
        if slot_number == 9:
            marker = "    return bind_coverage_evidence(assign_coverage(frame))"
            replacement = (
                "    prepared = bind_coverage_evidence(assign_coverage(frame))\n"
                "    prepared['priority_score'] = range(1, len(prepared) + 1)\n"
                "    prepared.loc[prepared['record_id'] == 'n06-r01', 'priority_score'] = 100\n"
                "    return prepared"
            )
            if marker not in source:
                raise AssertionError("qualification coverage marker is absent")
            source = source.replace(marker, replacement, 1)
            pipeline["files"][0]["content"] = (
                source
                + f"\n# independent N10 slot {instance_id} candidate {int(request.get('candidate_number', 1))}\n"
            )
            return response
        if slot_number == 11:
            marker = "    return ranked.sort_values(by=['final_score', 'record_id'], ascending=[False, True]).reset_index(drop=True)"
            replacement = (
                "    records = ranked.to_dict(orient='records')\n"
                "    ordered = sorted(records, key=lambda row: row['final_score'], reverse=True)\n"
                "    return pd.DataFrame(ordered)"
            )
            if marker not in source:
                raise AssertionError("qualification prioritization marker is absent")
            source = source.replace(marker, replacement, 1)
            pipeline["files"][0]["content"] = (
                source
                + f"\n# independent N10 slot {instance_id} candidate {int(request.get('candidate_number', 1))}\n"
            )
            return response
        if slot_number in snippets:
            source = source.replace("\nrequest = json.load(sys.stdin)\n", snippets[slot_number] + "request = json.load(sys.stdin)\n")
            replacements = {
                2: ("eligible = validate_demand_records(choose_demand_records(request['corpus']))", "chosen = validate_demand_records(choose_demand_records(request['corpus']))\neligible = n10_slot_boundary(chosen)"),
                4: ("normalized = normalize_evidence(eligible)", "normalized = n10_slot_boundary(normalize_evidence(eligible))"),
                6: ("eligible = validate_demand_records(choose_demand_records(request['corpus']))", "chosen = validate_demand_records(choose_demand_records(request['corpus']))\neligible = n10_slot_boundary(chosen)"),
                8: ("normalized = normalize_evidence(eligible)", "normalized = n10_slot_boundary(normalize_evidence(eligible))"),
                10: ("ranked = rank_demands(scored)", "ranked = n10_slot_boundary(rank_demands(scored))"),
            }
            old, new = replacements[slot_number]
            if old not in source:
                raise AssertionError(f"qualification source marker missing for {instance_id}")
            source = source.replace(old, new, 1)
            pipeline["review_boundaries"].append(
                {
                    "boundary_id": f"n10-{instance_id}-mutation-boundary",
                    "source_path": pipeline["files"][0]["path"],
                    "qualified_function_name": qualified_name,
                    "semantic_stage": stage,
                    "role": "deterministic qualification mutation boundary",
                    "expected_inputs": ["records"],
                    "expected_outputs": ["records"],
                }
            )
            candidate_number = int(request.get("candidate_number", 1))
            variant = "v" * (candidate_number * 257)
            probes = "".join(
                f"qualification_probe_{index:02d} = {index}\n"
                for index in range(1, 25)
            )
            indented_probes = "".join(f"    {line}\n" for line in probes.splitlines())
            source = source.replace(
                "def n10_slot_boundary(frame):\n",
                f"def n10_slot_boundary(frame):\n    qualification_variant = {variant!r}\n{indented_probes}",
                1,
            )
        pipeline["files"][0]["content"] = source + f"\n# independent N10 slot {instance_id}\n"
        return response

    def call(kind: str, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if kind == "instance_authoring":
            response = authored_for_slot(request)
            return {**response, "usage": {"input_tokens": 0, "output_tokens": 0}, "real_model_call": False}
        if kind == "instance_stabilization":
            raise AssertionError("passing qualification must not stabilize")
        if kind == "review":
            package = dict(request["package"])
            truth = request.get("ground_truth_boundary_id")
            reviews = []
            for declaration in package["common_base"]["semantic_declarations"]:
                boundary_id = str(declaration["boundary_id"])
                faulty_boundary = truth is not None and boundary_id == truth
                reviews.append(
                    {
                        "unit_id": boundary_id,
                        "decision": "suspect" if faulty_boundary else "trusted",
                        "decision_reason": "deterministic transport-boundary qualification response",
                        "evidence_refs": [boundary_id],
                        "trust_level": None if faulty_boundary else "trusted_for_reuse",
                        "criteria_outcomes": [
                            {
                                "criterion": "required deterministic behavior",
                                "verdict": "not_met" if faulty_boundary else "met",
                                "evidence_refs": [boundary_id],
                            }
                        ],
                        "boundary_health_acknowledged": True,
                        "expand_helper_prefixes": [],
                        "inspect_artifacts": [],
                        "suspect_node_refs": [],
                    }
                )
            return {
                "status": "complete",
                "response": {"reviews": reviews},
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 10,
                "reasoning_tokens": 0,
                "latency_seconds": 0.0,
                "expansion_count": int(request.get("evidence_mode") == "etiq_selected_adaptive"),
                "citation_count": 1,
                "attempt_count": 1,
                "real_model_call": False,
            }
        if kind == "repair":
            return {
                "status": "complete",
                "response": {
                    "change_summary": "restore the deterministic clean function body",
                    "pipeline": {
                        "entry_file": str(request["selected_source"]["file"]),
                        "files": [
                            {
                                "path": str(request["selected_source"]["file"]),
                                "content": str(request["clean_selected_source"]),
                            }
                        ],
                        "review_boundaries": [],
                    },
                },
                "input_tokens": 80,
                "cached_input_tokens": 0,
                "output_tokens": 8,
                "reasoning_tokens": 0,
                "latency_seconds": 0.0,
                "attempt_count": 1,
                "real_model_call": False,
            }
        raise ValueError(f"unknown N07 provider boundary: {kind}")

    return call


def _call_provider(
    output_root: Path,
    call_provider: Provider,
    kind: str,
    request: Mapping[str, Any],
    *,
    parent_id: str,
) -> dict[str, Any]:
    """Return one stable request/attempt lineage without wrapping live calls twice."""

    if getattr(call_provider, "_owns_retry_ledger", False):
        response = dict(call_provider(kind, request, parent_id=parent_id))
        lineage = response.get("retry_lineage")
        if not isinstance(lineage, Mapping):
            raise ValueError("N13 live provider omitted canonical retry lineage")
        call_ids = list(map(str, response.get("call_ids", [])))
        attempts = lineage.get("attempts")
        if (
            response.get("request_sha256") != lineage.get("request_sha256")
            or call_ids != list(map(str, lineage.get("call_ids", [])))
            or not isinstance(attempts, list)
            or call_ids != [str(item.get("call_id")) for item in attempts]
            or int(response.get("attempt_count") or 0) != len(attempts)
        ):
            raise ValueError("N13 live provider returned inconsistent retry lineage")
        return response

    def launch(_call_id: str, _request_bytes: bytes) -> Mapping[str, Any]:
        return {
            "status": "completed",
            "response": dict(call_provider(kind, request)),
        }

    outcome = run_with_identical_retries(
        output_root / "ledger",
        parent_id=parent_id,
        call_class=kind,
        logical_request={
            "kind": kind,
            "request": dict(request),
            "model": "gpt-5.5",
            "reasoning_effort": "high",
        },
        launch=launch,
    )
    if outcome["status"] != "completed":
        raise RuntimeError(f"N07 provider boundary failed: {kind}")
    response = dict(outcome["result"]["response"])
    response["attempt_count"] = len(outcome["attempts"])
    response["request_sha256"] = outcome["request_sha256"]
    response["call_ids"] = [item["call_id"] for item in outcome["attempts"]]
    response["retry_lineage"] = _retry_lineage(outcome)
    return response


def _retry_lineage(outcome: Mapping[str, Any]) -> dict[str, Any]:
    attempts = [
        {
            key: item.get(key)
            for key in (
                "call_id",
                "parent_id",
                "call_class",
                "attempt_index",
                "request_sha256",
                "status",
                "failure_classification",
                "record",
            )
        }
        for item in outcome["attempts"]
    ]
    result = dict(outcome["result"])
    usage = result.get("usage")
    if not isinstance(usage, Mapping):
        response = result.get("response")
        usage = response.get("usage") if isinstance(response, Mapping) else None
    return {
        "status": outcome["status"],
        "request_sha256": outcome["request_sha256"],
        "call_ids": [item["call_id"] for item in attempts],
        "attempts": attempts,
        "result": result,
        "usage": dict(usage) if isinstance(usage, Mapping) else {},
        "maximum_infrastructure_retries": 2,
    }


def _live_provider(
    repo_root: Path,
    output_root: Path,
    *,
    source_codex_home: Path | None = None,
) -> Provider:
    """Launch each live external call in a fresh signed production branch."""
    codex_bin = Path(shutil.which("codex") or "").resolve(strict=True)
    codex_runtime = codex_bin.parent.parent
    codex_home = source_codex_home or Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    )
    def call(
        kind: str,
        request: Mapping[str, Any],
        *,
        parent_id: str | None = None,
    ) -> Mapping[str, Any]:
        schemas = {
            "instance_authoring": "fault_chain_authoring.schema.json",
            "instance_stabilization": "fault_chain_stabilization.schema.json",
            "review": "fault_review_receipt.schema.json",
            "repair": "fault_repair_response.schema.json",
        }
        prompts = {
            "instance_authoring": "fault_chain_authoring.md",
            "instance_stabilization": "fault_chain_stabilization.md",
            "review": "fault_review.md",
            "repair": "fault_repair.md",
        }
        if kind not in schemas:
            raise ValueError(f"unknown N07 live provider boundary: {kind}")
        if kind == "instance_authoring":
            safe_request = {
                "instance_id": request["instance_id"],
                "candidate_number": request["candidate_number"],
                "authoring_seed": request["authoring_seed"],
                "task": request["task"],
            }
        elif kind == "instance_stabilization":
            safe_request = {
                key: request[key]
                for key in (
                    "candidate_number",
                    "cycle",
                    "failing_job_id",
                    "pipeline",
                    "expected_interface",
                    "fault_blind_diagnostics",
                    "stabilization_evidence",
                    "prompt_sha256",
                    "schema_sha256",
                )
            }
        elif kind == "review":
            package = request.get("package")
            if not isinstance(package, Mapping):
                package_path = Path(str(request.get("package_path") or (output_root / "packages" / str(request["branch_id"]) / "evidence/review-package.json")))
                package = json.loads(package_path.read_text())
            safe_request = {
                "trial_id": request["trial_id"],
                "seed": request["seed"],
                "package": dict(package),
                "operation_evidence": request.get("operation_evidence"),
                "receipt_correction": request.get("receipt_correction"),
            }
        elif kind == "repair":
            package_path = Path(str(request.get("package_path") or (output_root / "packages" / str(request["branch_id"]) / "evidence/review-package.json")))
            repair_package = json.loads(package_path.read_text())
            repair_package.pop("source_bundle", None)
            safe_request = {
                "repair_id": request["repair_id"],
                "selected_source": request["selected_source"],
                "review": request["review"],
                "package_without_source_bundle": repair_package,
                "response_contract": {
                    "pipeline.files": "exactly one item",
                    "pipeline.files[0].path": request["selected_source"]["file"],
                    "pipeline.files[0].content": "complete replacement text for selected_source only",
                    "pipeline.review_boundaries": "empty",
                },
            }
        template = (repo_root / "prompts/v2_2" / prompts[kind]).read_text()
        prompt = template + "\n\nFrozen request:\n" + json.dumps(safe_request, sort_keys=True)
        if parent_id is not None:
            parent = parent_id
        elif kind == "instance_authoring":
            parent = f"{request['instance_id']}-candidate-{int(request['candidate_number']):02d}"
        else:
            parent = str(
                request.get("trial_id")
                or request.get("repair_id")
                or request.get("instance_id")
                or stable_id(
                    "call",
                    [kind, sha256_bytes(canonical_json(safe_request))],
                    0,
                )
            )
        request_root = output_root / "provider-requests" / parent / kind
        prompt_path = request_root / "prompt.md"
        create_bytes_exclusive(prompt_path, prompt.encode())
        schema_path = repo_root / "schemas/v2_2" / schemas[kind]
        attempt_number = 0

        def launch(call_id: str, _request_bytes: bytes) -> Mapping[str, Any]:
            nonlocal attempt_number
            branch_id = stable_id("branch", [parent, kind, call_id], attempt_number)
            attempt_number += 1
            branch = output_root / "provider-branches" / branch_id
            materialize_opaque_branch(
                branch,
                allowlist={"prompt.md": prompt_path, "schema.json": schema_path},
                manifest_identity={"branch_id": branch_id, "call_id": call_id, "call_class": kind},
            )
            copy_codex_auth(branch, source_codex_home=codex_home)
            result = launch_codex_in_branch(
                branch,
                codex_runtime_root=codex_runtime,
                prompt_file="prompt.md",
                schema_file="schema.json",
                output_file="response.json",
            )
            return {**result, "branch_id": branch_id}

        outcome = run_with_identical_retries(
            output_root / "ledger",
            parent_id=parent,
            call_class=kind,
            logical_request={
                "prompt_sha256": sha256_bytes(prompt.encode()),
                "schema_sha256": sha256_file(schema_path),
                "model": "gpt-5.5",
                "reasoning_effort": "high",
            },
            launch=launch,
        )
        if outcome["status"] != "completed":
            raise RuntimeError(f"N07 {kind} provider request failed: {outcome['status']}")
        result = dict(outcome["result"])
        response = dict(result["response"])
        usage = dict(result.get("usage", {}))
        lineage = _retry_lineage(outcome)
        common = {
            "attempt_count": len(outcome["attempts"]),
            "request_sha256": outcome["request_sha256"],
            "call_ids": [item["call_id"] for item in outcome["attempts"]],
            "retry_lineage": lineage,
        }
        if kind in {"instance_authoring", "instance_stabilization"}:
            return {
                **response,
                **common,
                "usage": usage,
                "real_model_call": True,
            }
        if kind == "review":
            reviews = list(response.get("reviews", []))
            detected = any(item.get("decision") in {"suspect", "failed"} for item in reviews)
            return {
                "status": "complete",
                "fault_detected": detected,
                "input_tokens": usage.get("input_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens", 0),
                "output_tokens": usage.get("output_tokens"),
                "reasoning_tokens": 0,
                "latency_seconds": 0.0,
                "expansion_count": sum(bool(item.get("expand_helper_prefixes")) for item in reviews),
                "citation_count": sum(len(item.get("evidence_refs", [])) for item in reviews),
                **common,
                "response": response,
                "real_model_call": True,
            }
        return {
            "status": "complete",
            "input_tokens": usage.get("input_tokens"),
            "cached_input_tokens": usage.get("cached_input_tokens", 0),
            "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": 0,
            "latency_seconds": 0.0,
            **common,
            "response": response,
            "real_model_call": True,
        }

    setattr(call, "_owns_retry_ledger", True)
    return call


def _jobs_from_response(response: Mapping[str, Any]) -> dict[str, Any]:
    values = response.get("jobs")
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("N07 authoring response must contain exactly two jobs")
    jobs = {}
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError("N07 authoring job is not an object")
        job_id = str(item.get("job_id") or "")
        if not job_id or job_id in jobs:
            raise ValueError("N07 authoring job IDs are missing or duplicated")
        jobs[job_id] = parse_generated_pipeline(job_id, dict(item["pipeline"]))
    return jobs


def _validate_instance_model_marker(
    response: Mapping[str, Any],
    *,
    qualification: bool,
    call_kind: str,
) -> None:
    marker = response.get("real_model_call")
    expected = not qualification
    if type(marker) is not bool or marker is not expected:
        mode = "qualification" if qualification else "live"
        raise ValueError(
            f"N07 {mode} {call_kind} response has an invalid real_model_call marker"
        )


def _instance_stabilization_failure(
    error: Exception,
    jobs: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    message = str(error)
    job_ids = list(jobs)
    if not job_ids:
        raise ValueError("stabilization cannot attribute a failure without jobs")
    upstream_markers = {
        job_ids[0],
        "upstream",
        "upstream_demand_selection",
        "upstream_evidence_normalization",
        "upstream_provenance_assembly",
        "upstream_schema",
        "upstream_count",
        "upstream_records",
    }
    downstream_markers = {
        job_ids[-1],
        "downstream",
        "downstream_schema",
        "downstream_count",
        "top_need",
        "decision",
    }
    upstream = any(marker in message for marker in upstream_markers)
    downstream = any(marker in message for marker in downstream_markers)
    if upstream == downstream:
        raise ValueError("source failure is not attributable to exactly one job") from error
    failing_job_id = job_ids[0] if upstream else job_ids[-1]
    failed_checks = [message]
    return {
        "failure_kind": "validation",
        "failing_job_id": failing_job_id,
        "failed_checks": failed_checks,
        "compact_diagnostics": {
            "failed_check_count": len(failed_checks),
            "error_type": type(error).__name__,
        },
        "scenario_id": scenario["scenario_id"],
    }


def _instance_stabilization_request(
    repo_root: Path,
    *,
    candidate_number: int,
    cycle: int,
    jobs: Mapping[str, Any],
    scenario: Mapping[str, Any],
    failure: Mapping[str, Any],
    previous_rejection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    failing_job_id = str(failure["failing_job_id"])
    pipeline = jobs[failing_job_id]
    upstream = failing_job_id == list(jobs)[0]
    required_output_keys = (
        ["needs", "evidence_sources", "metadata"]
        if upstream
        else ["coverage", "priorities", "recommendation", "metadata"]
    )
    evidence = build_stabilization_evidence(
        failure_kind=str(failure["failure_kind"]),
        failing_job_id=failing_job_id,
        source=jsonable(pipeline.files),
        command=["etiq", "scan_code", pipeline.entry_file],
        exit_status=1,
        stdout="",
        stderr="; ".join(map(str, failure.get("failed_checks", []))),
        expected_interface={
            "entry_file": pipeline.entry_file,
            "source_paths": [item.path for item in pipeline.files],
            "review_boundaries": [dict(item) for item in pipeline.review_boundaries],
            "required_output_keys": required_output_keys,
        },
        frozen_schema_and_criteria={
            "scenario_id": scenario["scenario_id"],
            "behavioural_requirements": scenario["behavioural_requirements"],
            "failed_checks": list(failure.get("failed_checks", [])),
            "compact_diagnostics": dict(failure.get("compact_diagnostics", {})),
            "previous_response_rejection": (
                dict(previous_rejection) if previous_rejection is not None else None
            ),
            "graph_evidence": "forbidden_for_validation_failure",
        },
    )
    return {
        "candidate_number": candidate_number,
        "cycle": cycle,
        "failing_job_id": failing_job_id,
        "pipeline": _pipeline_payload(pipeline),
        "expected_interface": evidence["expected_interface"],
        "fault_blind_diagnostics": evidence["frozen_schema_and_criteria"],
        "stabilization_evidence": evidence,
        "prompt_sha256": sha256_file(repo_root / "prompts/v2_2/fault_chain_stabilization.md"),
        "schema_sha256": sha256_file(repo_root / "schemas/v2_2/fault_chain_stabilization.schema.json"),
    }


def _validate_instance_stabilization_scope(
    jobs: Mapping[str, Any],
    *,
    failing_job_id: str,
    response: Mapping[str, Any],
) -> dict[str, Any]:
    if str(response.get("job_id") or "") != failing_job_id:
        raise ValueError("stabilization response changed the failing job identity")
    original = jobs[failing_job_id]
    source = response.get("replacement_source")
    if not isinstance(source, list) or not source:
        raise ValueError("stabilization response has no complete replacement source")
    source_paths = [str(item.get("path") or "") for item in source if isinstance(item, Mapping)]
    if len(source_paths) != len(source) or source_paths != [item.path for item in original.files]:
        raise ValueError("stabilization response changed the source paths")

    declarations = _pipeline_payload(original)["review_boundaries"]
    if response.get("boundary_relinks"):
        raise ValueError("instance stabilization cannot change controller-owned boundaries")

    replacement = parse_generated_pipeline(
        failing_job_id,
        {
            "entry_file": original.entry_file,
            "files": source,
            "review_boundaries": declarations,
        },
    )
    replacements = dict(jobs)
    replacements[failing_job_id] = replacement
    validate_stabilization_replacement(jobs, replacements, failing_job_id=failing_job_id)
    return replacements


def build_phase_a_base(repo_root: Path, output_root: Path) -> dict[str, Any]:
    """Build and freeze the deterministic controller-owned Phase-A base."""
    fixture, jobs = load_qualification_fixture(repo_root, PHASE_A_FIXTURE_ROOT)
    scenario = load_preflight_inputs(repo_root, PREFLIGHT_ROOT)
    job_ids = list(jobs)
    if job_ids != ["preflight-upstream", "preflight-downstream"]:
        raise ValueError("Phase-A fixture must contain the fixed ordered two-job chain")
    if set(fixture["runtime_contract"]["upstream_output_keys"]) != set(
        scenario["oracles"]["upstream"]["required_output_fields"]
    ) or set(fixture["runtime_contract"]["downstream_output_keys"]) != set(
        scenario["oracles"]["downstream"]["required_output_fields"]
    ):
        raise ValueError("Phase-A fixture and oracle output contracts differ")

    output_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="phase-a-", dir=output_root.parent) as temporary:
        branch = Path(temporary) / "branch"
        materialize_opaque_branch(
            branch,
            allowlist={
                "fixture.json": repo_root / PHASE_A_FIXTURE_ROOT / "fixture.json",
                "scenario.json": repo_root / PREFLIGHT_ROOT / "scenario.json",
                "corpus.json": repo_root / PREFLIGHT_ROOT / "corpus.json",
                "capabilities.json": repo_root / PREFLIGHT_ROOT / "capabilities.json",
                "oracles.json": repo_root / PREFLIGHT_ROOT / "oracles.json",
            },
            manifest_identity={"purpose": "deterministic-phase-a-base", "fixture": "preflight-base-v1"},
        )
        copy_etiq_worker_runtime(branch, repo_root / "src")
        reference = execute_two_job_chain(
            branch,
            repo_root=repo_root,
            jobs=jobs,
            scenario=scenario,
            run_index=0,
            stage="phase-a-reference",
        )
        try:
            reference.update(
                derive_review_evidence(
                    reference,
                    jobs=jobs,
                    scenario=scenario,
                    simple_boundary_matching=True,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Phase-A controller review-evidence derivation failed: {error}"
            ) from error
        if not reference["oracle"]["passed"]:
            raise ValueError(
                "Phase-A clean oracle failed: "
                + ",".join(reference["oracle"]["failed_check_names"])
            )

        for job_id, pipeline in jobs.items():
            realization = reference["realizations"][job_id]
            if (
                not reference["executions"][job_id].snapshot.nodes
                or realization["boundary_realization_audit"]["unmatched_declaration_count"]
                or len(realization["realized_boundaries"])
                != len(pipeline.review_boundaries)
            ):
                raise ValueError(
                    f"Phase-A declared boundary did not execute for {job_id}"
                )
        if not any(
            item["incremental_node_refs"] or item["incremental_relationship_refs"]
            for item in reference["helpers"]
        ):
            raise ValueError("Phase-A nested helper expansion adds no evidence")

        mutation_target = dict(fixture["mutation"])
        target_job_id = mutation_target["job_id"]
        target_identity = resolve_static_identity(
            target_job_id,
            jobs[target_job_id],
            source_path=mutation_target["source_path"],
            qualified_function_name=mutation_target["qualified_function_name"],
        )
        injected = inject_operator_exact(
            jobs[target_job_id],
            target_identity=target_identity,
            operator=mutation_target["operator"],
            occurrence=0,
            parameter="",
        )
        mutant_jobs = dict(jobs)
        mutant_jobs[target_job_id] = parse_generated_pipeline(
            target_job_id, _pipeline_payload(injected["pipeline"])
        )
        validate_exact_mutation(
            jobs[target_job_id], mutant_jobs[target_job_id], injected["site"]
        )
        validate_source_restoration(
            jobs[target_job_id], injected["clean_pipeline"]
        )
        mutant = execute_two_job_chain(
            branch,
            repo_root=repo_root,
            jobs=mutant_jobs,
            scenario=scenario,
            run_index=1,
            stage="phase-a-mutant",
        )
        try:
            mutant.update(
                derive_review_evidence(
                    mutant,
                    jobs=mutant_jobs,
                    scenario=scenario,
                    simple_boundary_matching=True,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Phase-A controller mutant review-evidence derivation failed: {error}"
            ) from error

    function_name = mutation_target["qualified_function_name"].split(".")[-1]
    mutated_statement_executed = any(
        node.line_no == injected["site"]["mutant_span"]["start_line"]
        and function_name
        in {str(frame).split(",", 1)[0] for frame in node.func_stack}
        for node in mutant["executions"][target_job_id].snapshot.nodes
    )
    captured_fault_boundary = any(
        boundary["static_identity"]["qualified_function_name"]
        == mutation_target["qualified_function_name"]
        for boundary in mutant["realizations"][target_job_id]["realized_boundaries"]
    )
    validation = {
        "exactly_one_source_mutation": True,
        "mutated_statement_executed": mutated_statement_executed,
        "both_jobs_complete": len(mutant["outputs"]) == 2,
        "schema_valid": (
            mutant["oracle"]["checks"]["upstream_schema"]
            and mutant["oracle"]["checks"]["downstream_schema"]
        ),
        "clean_oracle_passed": reference["oracle"]["passed"],
        "mutant_oracle_failed": not mutant["oracle"]["passed"],
        "fault_in_captured_boundary": captured_fault_boundary,
    }
    if not all(validation.values()):
        raise ValueError(
            "Phase-A fixed mutation failed: "
            + ",".join(sorted(key for key, passed in validation.items() if not passed))
        )
    if any(
        path.exists() and any(path.glob("*.json"))
        for path in (output_root / "reviews", output_root / "repairs")
    ):
        raise ValueError("Phase-A created reviewer or repair records")

    source_hashes = {
        job_id: {
            item.path: sha256_bytes(item.content.encode())
            for item in pipeline.files
        }
        for job_id, pipeline in jobs.items()
    }
    boundaries = {
        "schema_version": "1",
        "realizations": reference["realizations"],
        "helpers": reference["helpers"],
    }
    boundaries["boundary_manifest_sha256"] = sha256_bytes(canonical_json(boundaries))

    def capture_manifest(execution: Mapping[str, Any]) -> dict[str, Any]:
        record = {
            "schema_version": "1",
            "jobs": {
                job_id: {
                    "snapshot_sha256": sha256_bytes(
                        canonical_json(jsonable(run.snapshot))
                    ),
                    "node_count": len(run.snapshot.nodes),
                    "relationship_count": len(run.snapshot.relationships),
                }
                for job_id, run in execution["executions"].items()
            },
        }
        record["capture_sha256"] = sha256_bytes(canonical_json(record))
        return record

    reference_capture = capture_manifest(reference)
    mutant_capture = capture_manifest(mutant)
    diff_hash = sha256_bytes(
        canonical_json(
            {
                "original_span": injected["site"]["original_span"],
                "mutant_span": injected["site"]["mutant_span"],
            }
        )
    )
    mutation_record = {
        "schema_version": "1",
        "target": mutation_target,
        "site": injected["site"],
        "diff_sha256": diff_hash,
        "validation": validation,
    }
    mutation_record["mutation_sha256"] = sha256_bytes(
        canonical_json(mutation_record)
    )

    for job_id, pipeline in jobs.items():
        source_file = pipeline.files[0]
        create_bytes_exclusive(
            output_root / "phase-a/frozen" / source_file.path,
            source_file.content.encode(),
        )
    create_json_exclusive(output_root / "phase-a/frozen/boundaries.json", boundaries)
    create_json_exclusive(
        output_root / "phase-a/reference/outputs.json", reference["outputs"]
    )
    create_json_exclusive(
        output_root / "phase-a/reference/handoffs.json",
        {"handoffs": reference["handoffs"]},
    )
    create_json_exclusive(
        output_root / "phase-a/reference/capture-manifest.json", reference_capture
    )
    create_json_exclusive(
        output_root / "phase-a/mutant/mutation.json", mutation_record
    )
    create_json_exclusive(
        output_root / "phase-a/mutant/outputs.json", mutant["outputs"]
    )
    create_json_exclusive(
        output_root / "phase-a/mutant/oracle-report.json", mutant["oracle"]
    )
    create_json_exclusive(
        output_root / "phase-a/mutant/capture-manifest.json", mutant_capture
    )

    handoff_hashes = {
        item["artifact_name"]: item["producer_sha256"]
        for item in reference["handoffs"]
    }
    frozen_fixture = {
        "schema_version": "1",
        "status": "phase_a_passed",
        "fixture_id": fixture["fixture_id"],
        "fixture_sha256": sha256_file(
            repo_root / PHASE_A_FIXTURE_ROOT / "fixture.json"
        ),
        "source_hashes": source_hashes,
        "boundary_manifest_sha256": boundaries["boundary_manifest_sha256"],
        "reference_capture_sha256": reference_capture["capture_sha256"],
        "handoff_hashes": handoff_hashes,
        "mutation_target": mutation_target,
        "mutation_diff_sha256": diff_hash,
        "mutant_capture_sha256": mutant_capture["capture_sha256"],
        "clean_oracle": reference["oracle"],
        "mutant_oracle": mutant["oracle"],
        "model_calls": 0,
        "review_calls": 0,
        "repair_calls": 0,
    }
    frozen_fixture["phase_a_sha256"] = sha256_bytes(
        canonical_json(frozen_fixture)
    )
    create_json_exclusive(output_root / "phase-a/fixture.json", frozen_fixture)
    return {
        "fixture": fixture,
        "jobs": jobs,
        "scenario": scenario,
        "execution": reference,
        "qualification": {
            "status": "passed",
            "declared_boundaries": sum(
                len(pipeline.review_boundaries) for pipeline in jobs.values()
            ),
            "realized_boundaries": sum(
                len(value["realized_boundaries"])
                for value in reference["realizations"].values()
            ),
            "exact_handoffs": len(reference["handoffs"]),
            "expandable_helpers": len(reference["helpers"]),
        },
        "mutation": {
            "jobs": mutant_jobs,
            "execution": mutant,
            "target_job_id": target_job_id,
            "operator": mutation_target["operator"],
            "schedule_sha256": mutation_record["mutation_sha256"],
            "site": injected["site"],
            "validation": validation,
            "rejections": [],
        },
        "authoring_calls": 0,
        "stabilization_calls": 0,
        "model_calls": 0,
        "review_calls": 0,
        "repair_calls": 0,
    }

def _checkpoint(output_root: Path, stage_index: int, stage: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    previous = None
    if stage_index:
        previous_path = output_root / "checkpoints" / f"{stage_index - 1:02d}-{STAGES[stage_index - 1]}.json"
        if not previous_path.is_file():
            raise ValueError("N07 checkpoint lineage is incomplete")
        previous = sha256_file(previous_path)
    value = {
        "schema_version": "1",
        "stage_index": stage_index,
        "stage": stage,
        "status": "passed",
        "previous_checkpoint_sha256": previous,
        "payload": dict(payload),
        "payload_sha256": sha256_bytes(canonical_json(payload)),
    }
    path = output_root / "checkpoints" / f"{stage_index:02d}-{stage}.json"
    digest = create_json_exclusive(path, value)
    return {**value, "record_sha256": digest}


def _terminal_incomplete(
    output_root: Path,
    stage: str,
    reason: str,
    *,
    experimental: bool = False,
    governance_bindings: Mapping[str, Any] | None = None,
) -> Path:
    completed = [path.stem.split("-", 1)[1] for path in sorted((output_root / "checkpoints").glob("*.json"))]
    review_records = list((output_root / "reviews").glob("*.json"))
    repair_records = list((output_root / "repairs").glob("*.json"))
    value = {
        "schema_version": "1",
        "status": "experiment_incomplete",
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "accepted_phase_a_sha256": ACCEPTED_PHASE_A_SHA256,
        "accepted_phase_a_tree_sha256": ACCEPTED_PHASE_A_TREE_SHA256,
        "governance_bindings": dict(governance_bindings or {}),
        "failed_checkpoint": stage,
        "reason": reason,
        "completed_checkpoints": completed,
        "downstream_activated": bool(review_records) if experimental else False,
        "observed_experimental_reviews": len(review_records) if experimental else 0,
        "observed_experimental_repairs": len(repair_records) if experimental else 0,
        "candidate_sets_consumed": 1 if (output_root / "authority-consumption.json").is_file() else 0,
    }
    create_json_exclusive(output_root / "terminal.json", value)
    return output_root / "terminal.json"


def _receipt_suspects(package: Mapping[str, Any], response: Mapping[str, Any]) -> list[str]:
    receipt = dict(response.get("response") or {})
    decisions = list(receipt.get("reviews", []))
    assigned = list(package["common_base"]["section"]["assigned_boundary_ids"])
    observed = [str(value.get("unit_id") or "") for value in decisions if isinstance(value, Mapping)]
    if len(observed) != len(set(observed)) or set(observed) != set(assigned):
        raise ValueError("review receipt does not cover every assigned boundary exactly once")
    allowed_refs = set(map(str, package["allowed_evidence_refs"]))
    for decision in decisions:
        refs = list(decision.get("evidence_refs", []))
        refs.extend(
            ref
            for criterion in decision.get("criteria_outcomes", [])
            for ref in criterion.get("evidence_refs", [])
        )
        if not refs or not set(map(str, refs)) <= allowed_refs:
            raise ValueError("review receipt contains missing or non-visible citations")
        if decision.get("inspect_artifacts") and not package["capabilities"]["inspect_visible_artifact"]:
            raise ValueError("review requested unavailable artifact inspection")
        if decision.get("expand_helper_prefixes") and not package["capabilities"]["reveal_direct_child"]:
            raise ValueError("review requested unavailable helper expansion")
    return [
        str(value["unit_id"])
        for value in decisions
        if value.get("decision") in {"failed", "suspect"}
    ]


def _rerun_dependency_suffix(
    branch: Path,
    *,
    repo_root: Path,
    jobs: Mapping[str, Any],
    scenario: Mapping[str, Any],
    repaired_job_id: str,
    canonical_execution: Mapping[str, Any],
    run_index: int,
    stage: str,
) -> dict[str, Any]:
    job_ids = list(jobs)
    if repaired_job_id == job_ids[0]:
        execution = execute_two_job_chain(
            branch,
            repo_root=repo_root,
            jobs=jobs,
            scenario=scenario,
            run_index=run_index,
            stage=stage,
        )
        execution.update(
            derive_review_evidence(execution, jobs=jobs, scenario=scenario)
        )
        return execution
    if repaired_job_id != job_ids[1]:
        raise ValueError("repaired job is outside the exact two-job dependency chain")
    upstream_id, downstream_id = job_ids
    upstream_output = deepcopy(canonical_execution["outputs"][upstream_id])
    downstream_input = {
        "needs": upstream_output.get("needs"),
        "evidence_sources": upstream_output.get("evidence_sources"),
        "capabilities": scenario["capabilities"],
    }
    downstream_execution = execute_pipeline_in_branch(
        branch,
        repo_root=repo_root,
        job_id=downstream_id,
        pipeline=jobs[downstream_id],
        runtime_input=downstream_input,
        run_index=run_index,
        stage=f"{stage}-downstream",
    )
    downstream_output = _parse_output(downstream_execution)
    downstream_execution.snapshot = enrich_snapshot_identities(
        downstream_execution.snapshot,
        job_id=downstream_id,
        pipeline=jobs[downstream_id],
    )
    downstream_realization = materialize_realized_boundaries(
        downstream_execution.snapshot,
        jobs[downstream_id].review_boundaries,
        job_id=downstream_id,
        pipeline=jobs[downstream_id],
    )
    handoffs = []
    for artifact in ("needs", "evidence_sources"):
        producer_hash = sha256_bytes(canonical_json(upstream_output.get(artifact)))
        consumer_hash = sha256_bytes(canonical_json(downstream_input.get(artifact)))
        if producer_hash != consumer_hash:
            raise ValueError("downstream-only rerun changed a reused upstream artifact")
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
    return {
        "executions": {
            upstream_id: canonical_execution["executions"][upstream_id],
            downstream_id: downstream_execution,
        },
        "outputs": {upstream_id: upstream_output, downstream_id: downstream_output},
        "handoffs": handoffs,
        "realizations": {
            upstream_id: canonical_execution["realizations"][upstream_id],
            downstream_id: downstream_realization,
        },
        "helpers": [
            *[
                item for item in canonical_execution["helpers"]
                if item.get("job_id") == upstream_id
            ],
            *[
                {**item, "job_id": downstream_id}
                for item in eligible_direct_child_helpers(
                    downstream_execution.snapshot,
                    downstream_realization["realized_boundaries"],
                )
            ],
        ],
        "graph_size_reports": [
            *[
                item for item in canonical_execution["graph_size_reports"]
                if item.get("job_id") == upstream_id
            ],
            graph_size_report(
                downstream_execution.snapshot,
                downstream_realization["realized_boundaries"],
                protocol_version="2.2.0",
            ),
        ],
        "oracle": oracle_report(upstream_output, downstream_output, scenario["oracles"]),
        "reused_upstream_artifact_sha256": {
            artifact: sha256_bytes(canonical_json(upstream_output.get(artifact)))
            for artifact in ("needs", "evidence_sources")
        },
    }


def _protocol_instance_slots(repo_root: Path) -> list[dict[str, Any]]:
    protocol = _load_json(repo_root / PROTOCOL_ROOT / "experiment-protocol.json")
    slots = [dict(item) for item in protocol["instance_design"]["instance_slots"]]
    if [item["instance_id"] for item in slots] != [f"instance-{index:02d}" for index in range(1, 13)]:
        raise ValueError("N10 instance schedule does not contain the exact ordered slots")
    return slots


def _validate_frozen_instance(repo_root: Path, record: Mapping[str, Any]) -> None:
    schema = _load_json(repo_root / "schemas/v2_2/fault_instance.schema.json")
    jsonschema.Draft202012Validator(schema).validate(dict(record))
    unsigned = dict(record)
    observed = unsigned.pop("instance_sha256", None)
    if observed != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("v2.2 frozen instance self-hash mismatch")


def _scheduled_mutant(
    branch: Path,
    *,
    repo_root: Path,
    slot: Mapping[str, Any],
    jobs: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    job_ids = list(jobs)
    target_job_id = job_ids[0] if slot["target_job"] == "upstream" else job_ids[1]
    operator = str(slot["injection_operator"])
    parameter = "n10-fabricated-identifier" if operator == "fabricate_identifier" else ""
    semantic_stage = {
        ("upstream", "early"): "upstream_demand_selection",
        ("upstream", "middle"): "upstream_evidence_normalization",
        ("upstream", "late"): "upstream_provenance_assembly",
        ("downstream", "early"): "downstream_coverage_mapping",
        ("downstream", "middle"): "downstream_prioritization",
        ("downstream", "late"): "downstream_synthesis",
    }[(str(slot["target_job"]), str(slot["stage"]))]
    schedules = []
    for declaration in jobs[target_job_id].review_boundaries:
        qualified_name = str(declaration["qualified_function_name"])
        if declaration["semantic_stage"] != semantic_stage:
            continue
        identity = resolve_static_identity(
            target_job_id,
            jobs[target_job_id],
            source_path=str(declaration["source_path"]),
            qualified_function_name=qualified_name,
        )
        if not enumerate_operator_sites(
            jobs[target_job_id],
            target_identity=identity,
            operator=operator,
            parameter=parameter,
        ):
            continue
        schedules.append(
            freeze_operator_site_order(
                jobs[target_job_id],
                target_identity=identity,
                operator=operator,
                seed=int(slot["injection_seed"]),
                parameter=parameter,
            )
        )
    candidates = sorted(
        (
            (str(site["order_key"]), schedule, site)
            for schedule in schedules
            for site in schedule["frozen_candidates"]
        ),
        key=lambda item: (item[0], item[2]["qualified_function_name"], item[2]["occurrence"]),
    )
    if not candidates:
        raise ValueError("frozen mutation schedule has no eligible exact site")
    rejections = []
    for attempt, (_order_key, schedule, site) in enumerate(candidates, 1):
        injected = inject_operator_exact(
            jobs[target_job_id],
            target_identity=schedule["target_identity"],
            operator=operator,
            occurrence=int(site["occurrence"]),
            parameter=parameter,
        )
        mutant_jobs = dict(jobs)
        mutant_jobs[target_job_id] = parse_generated_pipeline(
            target_job_id, _pipeline_payload(injected["pipeline"])
        )
        try:
            execution = execute_two_job_chain(
                branch,
                repo_root=repo_root,
                jobs=mutant_jobs,
                scenario=scenario,
                run_index=100 + attempt,
                stage=f"n10-mutant-{slot['instance_id']}-{attempt:03d}",
            )
            execution.update(
                derive_review_evidence(
                    execution, jobs=mutant_jobs, scenario=scenario
                )
            )
            function_name = str(site["qualified_function_name"]).split(".")[-1]
            proof = any(
                function_name in {str(frame).split(",", 1)[0] for frame in node.func_stack}
                for node in execution["executions"][target_job_id].snapshot.nodes
            )
            flags = {
                "compile_success": True,
                "execution_success": True,
                "schema_valid": bool(
                    execution["oracle"]["checks"]["upstream_schema"]
                    and execution["oracle"]["checks"]["downstream_schema"]
                ),
                "mutated_statement_executed": proof,
                "plausible_final_result": bool(execution["outputs"][job_ids[1]].get("priorities")),
                "semantic_oracle_failed": not execution["oracle"]["passed"],
            }
            validate_exact_mutation(jobs[target_job_id], mutant_jobs[target_job_id], injected["site"])
            validate_source_restoration(jobs[target_job_id], injected["clean_pipeline"])
            if all(flags.values()):
                return {
                    "jobs": mutant_jobs,
                    "execution": execution,
                    "target_job_id": target_job_id,
                    "operator": operator,
                    "schedule_sha256": schedule["frozen_schedule_sha256"],
                    "site": injected["site"],
                    "validation": flags,
                    "rejections": rejections,
                }
            rejections.append({"site": site, "failed_flags": sorted(k for k, value in flags.items() if not value)})
        except (KeyError, RuntimeError, TypeError, ValueError) as error:
            rejections.append({"site": site, "reason": f"{type(error).__name__}: {error}"})
    raise ValueError(
        "frozen mutation-site order exhausted: "
        + json.dumps(rejections, sort_keys=True, default=str)
    )


def _construct_instances(
    repo_root: Path,
    output_root: Path,
    phase_a: Mapping[str, Any],
    call_provider: Provider,
    *,
    qualification: bool,
) -> list[dict[str, Any]]:
    if phase_a.get("phase_a_sha256") != ACCEPTED_PHASE_A_SHA256:
        raise ValueError("instance construction is not bound to the accepted Phase-A checkpoint")
    scenario = load_preflight_inputs(repo_root, EXPERIMENT_ROOT)
    instances = []
    for slot_index, slot in enumerate(_protocol_instance_slots(repo_root)):
        instance_id = str(slot["instance_id"])
        rejection_log = []
        accepted = None
        authoring_usage_records: list[dict[str, Any]] = []
        stabilization_usage_records: list[dict[str, Any]] = []
        for candidate in range(1, 3):
            opaque_instance_id = "ins-" + sha256_bytes(instance_id.encode())[7:23]
            authoring_request = {
                "instance_id": opaque_instance_id,
                "candidate_number": candidate,
                "authoring_seed": int(slot["authoring_seed"]),
                "task": {
                    "scenario_id": scenario["scenario_id"],
                    "corpus": scenario["corpus"],
                    "capabilities": scenario["capabilities"],
                    "job_contract": scenario["job_contract"],
                    "behavioural_requirements": scenario["behavioural_requirements"],
                },
            }
            response = _call_provider(
                output_root,
                call_provider,
                "instance_authoring",
                authoring_request,
                parent_id=f"n10-{instance_id}-candidate-{candidate:02d}",
            )
            _validate_instance_model_marker(
                response,
                qualification=qualification,
                call_kind="instance authoring",
            )
            authoring_usage_records.append(
                {"candidate_number": candidate, **_call_usage(response)}
            )
            jobs = _jobs_from_response(response)
            branch_id = stable_id("branch", [instance_id, "construction", candidate], candidate - 1)
            branch = output_root / "instance-work" / instance_id / branch_id
            materialize_opaque_branch(
                branch,
                allowlist={
                    "scenario.json": repo_root / EXPERIMENT_ROOT / "scenario.json",
                    "corpus.json": repo_root / EXPERIMENT_ROOT / "corpus.json",
                    "capabilities.json": repo_root / EXPERIMENT_ROOT / "capabilities.json",
                    "oracles.json": repo_root / EXPERIMENT_ROOT / "oracles.json",
                },
                manifest_identity={"instance_id": instance_id, "candidate": str(candidate)},
            )
            copy_etiq_worker_runtime(branch, repo_root / "src")
            clean_execution = None
            qualification_report = None
            stabilization_call_ids = []
            previous_rejection = None
            for cycle in range(2):
                source_failure: Exception | None = None
                try:
                    clean_execution = execute_two_job_chain(
                        branch,
                        repo_root=repo_root,
                        jobs=jobs,
                        scenario=scenario,
                        run_index=cycle,
                        stage=f"n10-{instance_id}-c{candidate:02d}-s{cycle:02d}-reference",
                    )
                except (RuntimeError, ValueError) as error:
                    source_failure = error
                if clean_execution is not None and not clean_execution["oracle"]["passed"]:
                    source_failure = ValueError(
                        "instance reference oracle failed: "
                        + ",".join(clean_execution["oracle"]["failed_check_names"])
                    )
                if source_failure is None:
                    clean_execution.update(
                        derive_review_evidence(
                            clean_execution, jobs=jobs, scenario=scenario
                        )
                    )
                    qualification_report = qualify_realized_chain(
                        clean_execution["realizations"].values(),
                        handoffs=clean_execution["handoffs"],
                        helper_evidence=clean_execution["helpers"],
                        graph_size_reports=[],
                        has_join_or_aggregation=False,
                        protocol_version="2.2.0",
                    )
                    break
                if cycle == 1:
                    rejection_log.append(
                        {
                            "candidate": candidate,
                            "cycle": cycle,
                            "reason": f"{type(source_failure).__name__}: {source_failure}",
                        }
                    )
                    clean_execution = None
                    break
                failure = _instance_stabilization_failure(source_failure, jobs, scenario)
                request = _instance_stabilization_request(
                    repo_root,
                    candidate_number=candidate,
                    cycle=cycle + 1,
                    jobs=jobs,
                    scenario=scenario,
                    failure=failure,
                    previous_rejection=previous_rejection,
                )
                stabilization = _call_provider(
                    output_root,
                    call_provider,
                    "instance_stabilization",
                    request,
                    parent_id=f"n10-{instance_id}-c{candidate:02d}-stabilization-{cycle + 1:02d}",
                )
                _validate_instance_model_marker(
                    stabilization,
                    qualification=qualification,
                    call_kind="instance stabilization",
                )
                stabilization_call_ids.extend(stabilization["call_ids"])
                stabilization_usage_records.append(
                    {
                        "candidate_number": candidate,
                        "cycle": cycle + 1,
                        **_call_usage(stabilization),
                    }
                )
                try:
                    jobs = _validate_instance_stabilization_scope(
                        jobs,
                        failing_job_id=str(failure["failing_job_id"]),
                        response=stabilization,
                    )
                    previous_rejection = None
                except (KeyError, TypeError, ValueError) as response_error:
                    previous_rejection = {
                        "candidate": candidate,
                        "cycle": cycle + 1,
                        "gate": "stabilization_response",
                        "reason": str(response_error),
                    }
                    rejection_log.append(previous_rejection)
            if clean_execution is None or qualification_report is None:
                continue
            if slot["designation"] == "no_injection_control":
                evaluation_jobs = jobs
                evaluation_execution = clean_execution
                mutation = None
            else:
                mutation = _scheduled_mutant(
                    branch,
                    repo_root=repo_root,
                    slot=slot,
                    jobs=jobs,
                    scenario=scenario,
                )
                evaluation_jobs = mutation["jobs"]
                evaluation_execution = mutation["execution"]
            accepted = {
                "schema_version": "1",
                **slot,
                "slot_index": slot_index,
                "candidate_number": candidate,
                "stabilization_cycles": len(stabilization_call_ids),
                "fresh_chain": True,
                "jobs": evaluation_jobs,
                "clean_jobs": jobs,
                "clean_execution": clean_execution,
                "evaluation_execution": evaluation_execution,
                "qualification": qualification_report,
                "mutation": mutation,
                "authoring_request_sha256": response["request_sha256"],
                "authoring_call_ids": response["call_ids"],
                "stabilization_call_ids": stabilization_call_ids,
                "authoring_usage": _aggregate_usage(authoring_usage_records),
                "stabilization_usage": _aggregate_usage(stabilization_usage_records),
                "authoring_call_records": authoring_usage_records,
                "stabilization_call_records": stabilization_usage_records,
                "rejections": rejection_log,
            }
            break
        if accepted is None:
            raise ValueError(f"N10 instance slot exhausted: {instance_id}")
        frozen = {
            key: jsonable(value)
            for key, value in accepted.items()
            if key not in {"jobs", "clean_jobs", "clean_execution", "evaluation_execution", "mutation"}
        }
        frozen.update(
            {
                "protocol_id": "neurips-2026-workshop-fault-localisation-v2",
                "protocol_version": "2.2.0",
                "protocol_content_hash": PROTOCOL_CONTENT_SHA256,
                "source_sha256": {
                    job_id: sha256_bytes(canonical_json(_pipeline_payload(pipeline)))
                    for job_id, pipeline in accepted["jobs"].items()
                },
                "execution_sha256": sha256_bytes(
                    canonical_json(
                        {
                            "outputs": accepted["evaluation_execution"]["outputs"],
                            "handoffs": accepted["evaluation_execution"]["handoffs"],
                            "snapshots": {
                                job_id: jsonable(execution.snapshot)
                                for job_id, execution in accepted["evaluation_execution"]["executions"].items()
                            },
                            "realizations": accepted["evaluation_execution"]["realizations"],
                            "oracle": accepted["evaluation_execution"]["oracle"],
                        }
                    )
                ),
                "reference_bundle_sha256": sha256_bytes(
                    canonical_json(
                        {
                            job_id: _pipeline_payload(pipeline)
                            for job_id, pipeline in accepted["clean_jobs"].items()
                        }
                    )
                ),
                "mutant_bundle_sha256": (
                    sha256_bytes(
                        canonical_json(
                            {
                                job_id: _pipeline_payload(pipeline)
                                for job_id, pipeline in accepted["jobs"].items()
                            }
                        )
                    )
                    if accepted["mutation"] is not None
                    else None
                ),
                "mutation": (
                    {
                        key: jsonable(accepted["mutation"][key])
                        for key in (
                            "target_job_id",
                            "operator",
                            "schedule_sha256",
                            "site",
                            "validation",
                            "rejections",
                        )
                    }
                    if accepted["mutation"] is not None
                    else None
                ),
            }
        )
        frozen["instance_sha256"] = sha256_bytes(canonical_json(frozen))
        _validate_frozen_instance(repo_root, frozen)
        create_json_exclusive(output_root / "instances" / f"{instance_id}.json", frozen)
        accepted["frozen_record"] = frozen
        instances.append(accepted)
    if len({tuple(item["frozen_record"]["source_sha256"].values()) for item in instances}) != 12:
        raise ValueError("N10 independently authored instance sources are not distinct")
    return instances


def _capture_instances(output_root: Path, instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    captures = []
    for index, instance in enumerate(instances):
        execution = instance["evaluation_execution"]
        capture_id = stable_id("capture-set", [instance["instance_id"], "canonical"], index)
        jobs = {}
        for job_id, item in execution["executions"].items():
            jobs[job_id] = {
                "input": _load_json(item.run_dir / "pipeline-input.json"),
                "output": execution["outputs"][job_id],
                "stdout": (item.run_dir / "pipeline-stdout.log").read_text(),
                "stderr": (item.run_dir / "pipeline-stderr.log").read_text(),
                "snapshot": jsonable(item.snapshot),
                "realization": execution["realizations"][job_id],
            }
        value = {
            "schema_version": "1",
            "capture_id": capture_id,
            "instance_id": instance["instance_id"],
            "job_ids": list(execution["executions"]),
            "jobs": jobs,
            "handoffs": execution["handoffs"],
            "source_sha256": instance["frozen_record"]["source_sha256"],
            "canonical": True,
            "attempt_count": 1,
        }
        value["capture_sha256"] = sha256_bytes(canonical_json(value))
        create_json_exclusive(output_root / "captures" / f"{capture_id}.json", value)
        instance["capture"] = value
        captures.append(value)
    if len({item["capture_sha256"] for item in captures}) != 12:
        raise ValueError("N10 canonical instance captures are not distinct")
    return captures


def _package_inputs(
    jobs: Mapping[str, Any],
    scenario: Mapping[str, Any],
    execution: Mapping[str, Any],
    job_id: str,
    branch: Mapping[str, Any],
    capture: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    job_ids = list(jobs)
    instance_token = sha256_bytes(str(branch["instance_id"]).encode())[7:17]
    opaque_jobs = {
        job_ids[0]: f"job-{instance_token}-up",
        job_ids[1]: f"job-{instance_token}-dn",
    }
    realization = execution["realizations"][job_id]
    boundary_ids = [item["boundary_id"] for item in realization["realized_boundaries"]]
    assigned_execution = execution["executions"][job_id]
    captured_job = capture["jobs"][job_id] if capture is not None else None
    runtime_input = (
        captured_job["input"]
        if captured_job is not None
        else _load_json(assigned_execution.run_dir / "pipeline-input.json")
    )
    stdout = (
        captured_job["stdout"]
        if captured_job is not None
        else (assigned_execution.run_dir / "pipeline-stdout.log").read_text()
    )
    stderr = (
        captured_job["stderr"]
        if captured_job is not None
        else (assigned_execution.run_dir / "pipeline-stderr.log").read_text()
    )
    chain_id = "chn-" + sha256_bytes(str(branch["instance_id"]).encode())[7:19]
    history = []
    if job_id == job_ids[1]:
        upstream_execution = execution["executions"][job_ids[0]]
        captured_upstream = capture["jobs"][job_ids[0]] if capture is not None else None
        upstream_input = captured_upstream["input"] if captured_upstream is not None else _load_json(upstream_execution.run_dir / "pipeline-input.json")
        upstream_stdout = captured_upstream["stdout"] if captured_upstream is not None else (upstream_execution.run_dir / "pipeline-stdout.log").read_text()
        upstream_stderr = captured_upstream["stderr"] if captured_upstream is not None else (upstream_execution.run_dir / "pipeline-stderr.log").read_text()
        for kind, content in (
            ("task_input", upstream_input),
            ("task_output", execution["outputs"][job_ids[0]]),
            ("stdout", upstream_stdout),
            ("stderr", upstream_stderr),
        ):
            history.append(
                {
                    "ref": f"hist-{instance_token}-{kind.replace('_', '-')}",
                    "job_id": opaque_jobs[job_ids[0]],
                    "kind": kind,
                    "content": content,
                    "source_bearing": False,
                    "scope": "canonical_chain",
                    "chain_id": chain_id,
                }
            )
    inputs = {
        "opaque_ids": {
            "instance_id": "ins-" + sha256_bytes(branch["instance_id"].encode())[7:19],
            "condition_id": branch["condition_id"],
            "branch_id": branch["branch_id"],
        },
        "review_task": "Detect and localize any behaviorally significant fault in the assigned job.",
        "behavioural_criteria": ["preserve the two exact handoffs", "produce the required deterministic recommendation"],
        "top_level_input": {"corpus": scenario["corpus"], "capabilities": scenario["capabilities"]},
        "final_output": execution["outputs"][job_ids[1]],
        "assigned_job": {
            "job_id": opaque_jobs[job_id],
            "input": runtime_input,
            "output": execution["outputs"][job_id],
            "stdout": stdout,
            "stderr": stderr,
        },
        "section": {
            "section_id": "sec-" + sha256_bytes(branch["instance_id"].encode())[7:19],
            "section_index": 0,
            "assigned_boundary_ids": boundary_ids,
            "context_boundary_ids": [],
            "organization": {"kind": "realized_semantic_boundaries"},
        },
        "full_chain_source": [
            {"job_id": opaque_jobs[value], "files": [{"path": file.path, "content": file.content} for file in jobs[value].files]}
            for value in job_ids
        ],
        "history_chain_id": chain_id,
        "history": history,
    }
    return inputs, opaque_jobs


def _materialize_packages(
    repo_root: Path,
    output_root: Path,
    instances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    design = expected_design()
    by_instance = {item["instance_id"]: item for item in instances}
    projection_cache = {}
    random_cache = {}
    materialized = []
    for branch in design["branches"]:
        instance = by_instance[str(branch["instance_id"])]
        jobs = instance["jobs"]
        scenario = load_preflight_inputs(repo_root, EXPERIMENT_ROOT)
        execution = instance["evaluation_execution"]
        job_ids = list(jobs)
        handoffs = [
            {
                "handoff_ref": item["handoff_id"],
                "upstream_job_id": item["upstream_job_id"],
                "downstream_job_id": item["downstream_job_id"],
                "artifact_sha256": item["producer_sha256"],
            }
            for item in execution["handoffs"]
        ]
        instance_number = int(str(branch["instance_id"]).split("-")[-1])
        job_id = (
            str(instance["mutation"]["target_job_id"])
            if instance["mutation"] is not None
            else job_ids[(instance_number - 1) % 2]
        )
        snapshot = execution["executions"][job_id].snapshot
        boundaries = execution["realizations"][job_id]["realized_boundaries"]
        key = (branch["instance_id"], job_id)
        if key not in random_cache:
            selected = graph_selection_for_mode(
                "etiq_selected_fixed", snapshot, boundaries, handoffs=handoffs, include_projection_binding=True
            )
            assert selected is not None
            random_cache[key] = freeze_random_projections(
                output_root / "random-projections" / branch["instance_id"] / job_id,
                snapshot,
                boundaries,
                selected,
                instance_id=str(branch["instance_id"]),
                handoffs=handoffs,
                protocol_content_hash=PROTOCOL_CONTENT_SHA256,
            )
        mode = str(branch["evidence_mode"])
        projection = None
        if mode.startswith("etiq_"):
            pkey = (branch["instance_id"], job_id, mode)
            if pkey not in projection_cache:
                projection_cache[pkey] = graph_selection_for_mode(
                    mode,
                    snapshot,
                    boundaries,
                    handoffs=handoffs,
                    frozen_random_by_boundary=random_cache[key],
                    random_instance_id=str(branch["instance_id"]),
                    random_protocol_content_hash=PROTOCOL_CONTENT_SHA256,
                    include_projection_binding=True,
                )
            projection = projection_cache[pkey]
        inputs, opaque_jobs = _package_inputs(
            jobs, scenario, execution, job_id, branch, instance["capture"]
        )
        package_realization = {
            **execution["realizations"][job_id],
            "realized_boundaries": [
                {
                    **value,
                    "role": "Perform the declared function behavior.",
                    "expected_inputs": ["Values supplied to the function."],
                    "expected_outputs": ["Value returned by the function."],
                }
                for value in boundaries
            ],
        }
        package, manifest = build_n05_condition_package(
            protocol_content_hash=PROTOCOL_CONTENT_SHA256,
            protocol_version="2.2.0",
            evidence_mode=mode,
            source_setting=str(branch["source_setting"]),
            snapshot=snapshot,
            realization=package_realization,
            handoffs=execution["handoffs"],
            frozen_projection=projection,
            controller_job_id_map=opaque_jobs,
            **inputs,
        )
        truth_boundary_id = None
        if instance["mutation"] is not None:
            qualified_name = str(instance["mutation"]["site"]["qualified_function_name"])
            matches = [
                item
                for item in boundaries
                if item["static_identity"]["qualified_function_name"] == qualified_name
            ]
            if len(matches) != 1:
                raise ValueError("N10 injected function does not resolve to one realized boundary")
            truth_boundary_id = manifest["controller_boundary_id_map"][matches[0]["boundary_id"]]
        root = output_root / "packages" / branch["branch_id"]
        materialize_branch_package(root, package, manifest)
        verified = verify_materialized_branch(root)
        record = {
            **branch,
            "assigned_job_id": job_id,
            "instance_capture_sha256": instance["capture"]["capture_sha256"],
            "instance_source_sha256": instance["frozen_record"]["source_sha256"],
            "package_sha256": manifest["package_sha256"],
            "common_base_sha256": manifest["common_base_sha256"],
            "manifest_content_sha256": manifest["manifest_content_sha256"],
            "projection_sha256": manifest.get("canonical_projection", {}).get("projection_sha256"),
            "graph_evidence_sha256": manifest.get("canonical_projection", {}).get("graph_evidence_sha256"),
            "verified": verified["verified"],
            "path": str(root.relative_to(output_root)),
        }
        create_json_exclusive(output_root / "package-records" / f"{branch['branch_id']}.json", record)
        restricted_record = {**record, "ground_truth_boundary_id": truth_boundary_id}
        create_json_exclusive(
            output_root / "restricted/package-records" / f"{branch['branch_id']}.json",
            restricted_record,
        )
        record["ground_truth_boundary_id"] = truth_boundary_id
        materialized.append(record)
    if len(materialized) != 96 or len({item["branch_id"] for item in materialized}) != 96:
        raise ValueError("N07 package freeze did not produce 96 unique branches")
    if {item["instance_id"] for item in materialized} != set(by_instance):
        raise ValueError("N10 packages do not cover all owning instances")
    for instance_id in by_instance:
        owned = [item for item in materialized if item["instance_id"] == instance_id]
        if len({item["common_base_sha256"] for item in owned}) != 1:
            raise ValueError("N12 package arms do not share one byte-identical common base")
        fixed = {
            item["graph_evidence_sha256"]
            for item in owned
            if item["evidence_mode"] == "etiq_selected_fixed"
        }
        adaptive = {
            item["graph_evidence_sha256"]
            for item in owned
            if item["evidence_mode"] == "etiq_selected_adaptive"
        }
        if fixed and adaptive and fixed != adaptive:
            raise ValueError("N12 fixed and adaptive initial evidence is not byte-identical")
        random_values = {
            item["graph_evidence_sha256"]
            for item in owned
            if item["evidence_mode"] == "etiq_random_matched"
        }
        if len(random_values) > 1:
            raise ValueError("N12 random matched evidence is not deterministic")
    create_json_exclusive(
        output_root / "packages.json",
        {
            "packages": [
                {key: value for key, value in item.items() if key != "ground_truth_boundary_id"}
                for item in materialized
            ],
            "count": len(materialized),
        },
    )
    return materialized


USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
)


def _call_usage(response: Mapping[str, Any]) -> dict[str, Any]:
    nested = response.get("usage")
    source = nested if isinstance(nested, Mapping) else response
    result: dict[str, Any] = {}
    unavailable = []
    for field in USAGE_FIELDS:
        value = source.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            result[field] = None
            unavailable.append(field)
        else:
            result[field] = value
    latency = response.get("latency_seconds")
    result["latency_seconds"] = (
        float(latency)
        if isinstance(latency, (int, float)) and not isinstance(latency, bool)
        else None
    )
    result["attempt_count"] = int(response.get("attempt_count") or 1)
    result["call_ids"] = list(map(str, response.get("call_ids", [])))
    result["request_sha256"] = response.get("request_sha256")
    result["real_model_call"] = response.get("real_model_call")
    result["unavailable_fields"] = unavailable
    return result


def _aggregate_usage(calls: list[Mapping[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {}
    unavailable = []
    for field in USAGE_FIELDS:
        values = [call.get(field) for call in calls]
        if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            totals[field] = sum(values)
        else:
            totals[field] = None
            unavailable.append(field)
    latencies = [call.get("latency_seconds") for call in calls]
    totals["latency_seconds"] = (
        sum(float(value) for value in latencies)
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in latencies)
        else None
    )
    totals["logical_call_count"] = len(calls)
    totals["provider_attempt_count"] = sum(int(call.get("attempt_count") or 1) for call in calls)
    totals["usage_unavailable"] = bool(unavailable)
    totals["unavailable_fields"] = unavailable
    return totals


def _operation(
    operation: str,
    status: str,
    *,
    call: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "status": status,
        "call": dict(call) if call is not None else None,
        "details": dict(details or {}),
        "errors": list(errors or []),
    }


def _record_operation_events(
    output_root: Path,
    *,
    owner_type: str,
    owner_id: str,
    events: list[Mapping[str, Any]],
) -> None:
    for sequence, event in enumerate(events, 1):
        record_id = f"{owner_id}-operation-{sequence:02d}"
        record_path = output_root / "ledger/operation-event" / f"{record_id}.json"
        payload = {
            "schema_version": "1",
            "protocol_content_hash": PROTOCOL_CONTENT_SHA256,
            "owner_type": owner_type,
            "owner_id": owner_id,
            "sequence": sequence,
            **dict(event),
        }
        if record_path.is_file():
            if _load_json(record_path).get("payload") != payload:
                raise ValueError("N10 stored operation event differs from the resumed outcome")
            continue
        append_record(
            output_root / "ledger",
            record_type="operation-event",
            record_id=record_id,
            payload=payload,
        )


def _review_receipt_errors(
    package: Mapping[str, Any], response: Mapping[str, Any]
) -> list[str]:
    receipt = response.get("response")
    if not isinstance(receipt, Mapping):
        return ["receipt is not an object"]
    decisions = receipt.get("reviews")
    if not isinstance(decisions, list):
        return ["receipt reviews is not an array"]
    errors = []
    assigned = list(package["common_base"]["section"]["assigned_boundary_ids"])
    observed = [
        str(value.get("unit_id") or "")
        for value in decisions
        if isinstance(value, Mapping)
    ]
    if len(observed) != len(set(observed)) or set(observed) != set(assigned):
        errors.append("receipt must cover every assigned boundary exactly once")
    allowed_refs = set(map(str, package["allowed_evidence_refs"]))
    allowed_decisions = {"trusted", "failed", "suspect", "superseded", "not_pipeline_step"}
    allowed_verdicts = {"met", "not_met", "cannot_judge"}
    allowed_trust = {"trusted_for_reuse", "trusted_for_reporting", "provisionally_trusted", None}
    for decision in decisions:
        if not isinstance(decision, Mapping):
            errors.append("receipt review entry is not an object")
            continue
        unit_id = str(decision.get("unit_id") or "")
        if decision.get("decision") not in allowed_decisions:
            errors.append(f"review {unit_id} has an invalid decision")
        if not isinstance(decision.get("decision_reason"), str):
            errors.append(f"review {unit_id} has no decision reason")
        if decision.get("trust_level") not in allowed_trust:
            errors.append(f"review {unit_id} has an invalid trust level")
        if not isinstance(decision.get("boundary_health_acknowledged"), bool):
            errors.append(f"review {unit_id} has no boundary-health acknowledgement")
        refs = list(decision.get("evidence_refs", []))
        criteria = decision.get("criteria_outcomes", [])
        if not isinstance(criteria, list) or not criteria:
            errors.append(f"review {unit_id} has no criteria outcomes")
            criteria = []
        for criterion in criteria:
            if not isinstance(criterion, Mapping):
                errors.append(f"review {unit_id} has a malformed criterion")
                continue
            if not isinstance(criterion.get("criterion"), str) or criterion.get("verdict") not in allowed_verdicts:
                errors.append(f"review {unit_id} has an invalid criterion outcome")
            refs.extend(criterion.get("evidence_refs", []))
        suspect_refs = decision.get("suspect_node_refs", [])
        if not isinstance(suspect_refs, list):
            errors.append(f"review {unit_id} has malformed suspect node refs")
            suspect_refs = []
        refs.extend(suspect_refs)
        if not refs or not set(map(str, refs)) <= allowed_refs:
            errors.append(
                f"review {unit_id} has missing or non-visible citations"
            )
        inspections_value = decision.get("inspect_artifacts", [])
        expansions_value = decision.get("expand_helper_prefixes", [])
        if not isinstance(inspections_value, list) or not isinstance(expansions_value, list):
            errors.append(f"review {unit_id} has malformed operation requests")
            inspections_value, expansions_value = [], []
        inspections = list(inspections_value)
        expansions = list(expansions_value)
        if inspections and not package["capabilities"]["inspect_visible_artifact"]:
            errors.append("artifact inspection is unavailable in this condition")
        if len(inspections) > 2:
            errors.append("artifact inspection exceeds two requests per follow-up")
        if expansions and not package["capabilities"]["reveal_direct_child"]:
            errors.append("helper expansion is unavailable in this condition")
        if len(expansions) > 1:
            errors.append("helper expansion exceeds one direct child per follow-up")
    return errors


def _review_package(
    output_root: Path,
    call_provider: Provider,
    request: Mapping[str, Any],
    package: Mapping[str, Any],
    *,
    snapshot: Any,
    realization: Mapping[str, Any],
    handoffs: list[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    current_package = dict(package)
    response = _call_provider(
        output_root,
        call_provider,
        "review",
        {**request, "package": current_package},
        parent_id=str(request["trial_id"]),
    )
    call_records = [{"purpose": "initial_review", **_call_usage(response)}]
    operation_events = [
        _operation("review", "completed", call=call_records[-1])
    ]
    operation_records = []
    correction_records = []
    expanded_by_boundary: dict[str, list[list[str]]] = {}
    follow_up_count = 0
    correction_count = 0
    while True:
        errors = _review_receipt_errors(current_package, response)
        operation_events.append(
            _operation(
                "receipt_validation",
                "rejected" if errors else "completed",
                details={"valid": not errors},
                errors=errors,
            )
        )
        if errors:
            if correction_count >= 2:
                return {
                    "valid": False,
                    "response": response,
                    "package": current_package,
                    "operation_records": operation_records,
                    "correction_records": correction_records,
                    "call_records": call_records,
                    "operation_events": operation_events,
                    "usage": _aggregate_usage(call_records),
                    "errors": errors,
                }
            correction_count += 1
            previous_receipt = response.get("response")
            response = _call_provider(
                output_root,
                call_provider,
                "review",
                {
                    **request,
                    "package": current_package,
                    "receipt_correction": {
                        "correction_index": correction_count,
                        "errors": errors,
                        "previous_receipt": previous_receipt,
                    },
                },
                parent_id=f"{request['trial_id']}-receipt-correction-{correction_count:02d}",
            )
            call_record = {
                "purpose": "receipt_correction",
                "correction_index": correction_count,
                **_call_usage(response),
            }
            call_records.append(call_record)
            operation_events.append(
                _operation(
                    "receipt_correction",
                    "completed",
                    call=call_record,
                    details={"correction_index": correction_count},
                    errors=errors,
                )
            )
            correction_records.append(
                {
                    "correction_index": correction_count,
                    "errors": errors,
                    "request_sha256": response["request_sha256"],
                    "call_ids": response["call_ids"],
                }
            )
            continue
        receipt = dict(response["response"])
        operations = []
        for decision in receipt["reviews"]:
            inspections = list(decision.get("inspect_artifacts", []))
            if inspections:
                operations.append(
                    ("artifact_inspection", str(decision.get("unit_id") or ""), inspections)
                )
            for prefix in decision.get("expand_helper_prefixes", []):
                operations.append(
                    ("helper_expansion", str(decision.get("unit_id") or ""), [prefix])
                )
        if not operations:
            return {
                "valid": True,
                "response": response,
                "package": current_package,
                "operation_records": operation_records,
                "correction_records": correction_records,
                "call_records": call_records,
                "operation_events": operation_events,
                "usage": _aggregate_usage(call_records),
                "errors": [],
            }
        operation, opaque_boundary_id, requests = operations[0]
        follow_up_count += 1
        if follow_up_count > 3:
            return {
                "valid": False,
                "response": response,
                "package": current_package,
                "operation_records": operation_records,
                "correction_records": correction_records,
                "call_records": call_records,
                "operation_events": operation_events,
                "usage": _aggregate_usage(call_records),
                "errors": ["review exceeded three operation follow-up calls"],
            }
        try:
            if operation == "artifact_inspection":
                visible = {
                    str(value["node_ref"]): value
                    for value in current_package.get("runtime_evidence", {}).get("nodes", [])
                }
                nodes = {node.node_ref: node for node in snapshot.nodes}
                evidence_added = []
                for inspection_request in requests:
                    ref = str(inspection_request.get("node_ref") or "")
                    if (
                        ref not in visible
                        or ref not in nodes
                        or not visible[ref].get("artifact_available")
                    ):
                        raise ValueError(
                            "artifact inspection targeted non-visible captured evidence"
                        )
                    evidence_added.append(
                        inspect_artifact(nodes[ref], inspection_request)
                    )
            else:
                reverse_ids = {
                    opaque: original
                    for original, opaque in manifest["controller_boundary_id_map"].items()
                }
                if opaque_boundary_id not in reverse_ids:
                    raise ValueError("helper expansion targeted a non-assigned boundary")
                original_boundary_id = reverse_ids[opaque_boundary_id]
                prefix = [str(value) for value in requests[0]]
                collapsed = {
                    (str(value["boundary_id"]), tuple(map(str, value["func_stack"])))
                    for value in current_package.get("runtime_evidence", {}).get(
                        "collapsed_helpers", []
                    )
                }
                if (opaque_boundary_id, tuple(prefix)) not in collapsed:
                    raise ValueError(
                        "helper expansion did not select a visible direct child"
                    )
                expanded_by_boundary.setdefault(original_boundary_id, []).append(prefix)
                selection = graph_selection_for_mode(
                    "etiq_selected_adaptive",
                    snapshot,
                    realization["realized_boundaries"],
                    handoffs=handoffs,
                    expanded_prefixes_by_boundary=expanded_by_boundary,
                )
                assert selection is not None
                selection = dict(selection)
                selection["visible_evidence_by_boundary"] = {
                    manifest["controller_boundary_id_map"][key]: value
                    for key, value in selection["visible_evidence_by_boundary"].items()
                }
                selection["collapsed_helpers"] = [
                    {
                        **value,
                        "boundary_id": manifest["controller_boundary_id_map"][
                            value["boundary_id"]
                        ],
                    }
                    for value in selection["collapsed_helpers"]
                ]
                current_package = _package_with_graph_selection(
                    current_package, snapshot, selection
                )
                evidence_added = {
                    "expanded_boundary_id": opaque_boundary_id,
                    "expanded_prefix": prefix,
                    "node_refs": selection["node_refs"],
                    "relationship_refs": selection["relationship_refs"],
                }
        except (KeyError, TypeError, ValueError) as error:
            operation_events.append(
                _operation(operation, "rejected", errors=[str(error)])
            )
            if correction_count >= 2:
                return {
                    "valid": False,
                    "response": response,
                    "package": current_package,
                    "operation_records": operation_records,
                    "correction_records": correction_records,
                    "call_records": call_records,
                    "operation_events": operation_events,
                    "usage": _aggregate_usage(call_records),
                    "errors": [str(error)],
                }
            correction_count += 1
            response = _call_provider(
                output_root,
                call_provider,
                "review",
                {
                    **request,
                    "package": current_package,
                    "receipt_correction": {
                        "correction_index": correction_count,
                        "errors": [str(error)],
                        "previous_receipt": response.get("response"),
                    },
                },
                parent_id=f"{request['trial_id']}-receipt-correction-{correction_count:02d}",
            )
            call_record = {
                "purpose": "receipt_correction",
                "correction_index": correction_count,
                **_call_usage(response),
            }
            call_records.append(call_record)
            operation_events.append(
                _operation(
                    "receipt_correction",
                    "completed",
                    call=call_record,
                    details={"correction_index": correction_count},
                    errors=[str(error)],
                )
            )
            correction_records.append(
                {
                    "correction_index": correction_count,
                    "errors": [str(error)],
                    "request_sha256": response["request_sha256"],
                    "call_ids": response["call_ids"],
                }
            )
            continue
        operation_records.append(
            {"operation": operation, "request": requests, "evidence_added": evidence_added}
        )
        operation_events.append(
            _operation(
                operation,
                "completed",
                details={"request": requests, "evidence_added": evidence_added},
            )
        )
        response = _call_provider(
            output_root,
            call_provider,
            "review",
            {
                **request,
                "package": current_package,
                "operation_evidence": evidence_added,
            },
            parent_id=f"{request['trial_id']}-follow-up-{follow_up_count:02d}",
        )
        call_record = {
            "purpose": "operation_follow_up",
            "operation": operation,
            "follow_up_index": follow_up_count,
            **_call_usage(response),
        }
        call_records.append(call_record)
        operation_events.append(
            _operation(
                "review",
                "completed",
                call=call_record,
                details={"follow_up_index": follow_up_count, "after": operation},
            )
        )


def _run_reviews(
    output_root: Path,
    instances: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    call_provider: Provider,
) -> list[dict[str, Any]]:
    by_branch = {item["branch_id"]: item for item in packages}
    by_instance = {item["instance_id"]: item for item in instances}
    design = expected_design()
    records = []
    for item in design["review_trials"]:
        record_path = output_root / "reviews" / f"{item['trial_id']}.json"
        if record_path.is_file():
            records.append(_load_json(record_path))
            continue
        branch = by_branch[item["branch_id"]]
        package = _load_json(output_root / "packages" / item["branch_id"] / "evidence/review-package.json")
        instance = by_instance[item["instance_id"]]
        job_id = str(branch["assigned_job_id"])
        execution = instance["evaluation_execution"]
        manifest = _load_json(
            output_root / "packages" / item["branch_id"] / "evidence/package-manifest.json"
        )
        try:
            reviewed = _review_package(
                output_root,
                call_provider,
                {**item, **branch},
                package,
                snapshot=execution["executions"][job_id].snapshot,
                realization=execution["realizations"][job_id],
                handoffs=[
                    {
                        "handoff_ref": value["handoff_id"],
                        "upstream_job_id": value["upstream_job_id"],
                        "downstream_job_id": value["downstream_job_id"],
                        "artifact_sha256": value["producer_sha256"],
                    }
                    for value in execution["handoffs"]
                ],
                manifest=manifest,
            )
            response = reviewed["response"]
            receipt = dict(response.get("response") or {})
            decisions = list(receipt.get("reviews", [])) if reviewed["valid"] else []
            suspects = [
                str(value["unit_id"])
                for value in decisions
                if value.get("decision") in {"failed", "suspect"}
            ]
            top_suspect = suspects[0] if suspects else None
            top_decision = next(
                (value for value in decisions if str(value.get("unit_id")) == top_suspect),
                None,
            )
            citation_refs = []
            if top_decision is not None:
                citation_refs.extend(map(str, top_decision.get("evidence_refs", [])))
                for criterion in top_decision.get("criteria_outcomes", []):
                    if isinstance(criterion, Mapping):
                        citation_refs.extend(map(str, criterion.get("evidence_refs", [])))
            suspect_node_refs = (
                list(map(str, top_decision.get("suspect_node_refs", [])))
                if top_decision is not None
                else []
            )
            truth = branch.get("ground_truth_boundary_id")
            localisation = {
                "frozen": reviewed["valid"],
                "top_suspect_boundary_id": top_suspect,
                "suspect_node_ref": suspect_node_refs[0] if suspect_node_refs else None,
                "citation_refs": list(dict.fromkeys(citation_refs)),
            }
            operation_events = [
                *reviewed["operation_events"],
                _operation(
                    "localisation_frozen",
                    "completed" if reviewed["valid"] else "failed",
                    details=localisation,
                    errors=reviewed["errors"],
                ),
            ]
            record = {
                **item,
                **{
                    key: value
                    for key, value in response.items()
                    if key not in {"real_model_call", "response"}
                },
                "status": "complete" if reviewed["valid"] else "missing",
                "validated_receipt": reviewed["valid"],
                "receipt": receipt,
                "receipt_errors": reviewed["errors"],
                "receipt_correction_count": len(reviewed["correction_records"]),
                "receipt_correction_records": reviewed["correction_records"],
                "operation_follow_up_count": len(reviewed["operation_records"]),
                "operation_records": reviewed["operation_records"],
                "operation_events": operation_events,
                "call_records": reviewed["call_records"],
                **reviewed["usage"],
                "fault_detected": bool(suspects),
                "top_suspect_boundary_id": top_suspect,
                "top_suspect_exact": bool(truth is not None and top_suspect == truth),
                "localisation": localisation,
                "failure_classification": None if reviewed["valid"] else "invalid_receipt",
            }
        except RuntimeError as error:
            usage = _aggregate_usage([{"attempt_count": 1}])
            operation_events = [
                _operation("review", "failed", errors=[str(error)]),
                _operation("localisation_frozen", "failed", errors=[str(error)]),
            ]
            record = {
                **item,
                "status": "missing",
                "validated_receipt": False,
                "receipt": None,
                "receipt_errors": [str(error)],
                "receipt_correction_count": 0,
                "receipt_correction_records": [],
                "operation_follow_up_count": 0,
                "operation_records": [],
                "operation_events": operation_events,
                "call_records": [],
                **usage,
                "fault_detected": False,
                "top_suspect_boundary_id": None,
                "top_suspect_exact": False,
                "localisation": None,
                "failure_classification": "provider_failure",
            }
        create_json_exclusive(record_path, record)
        append_record(output_root / "ledger", record_type="review", record_id=item["trial_id"], payload=record)
        _record_operation_events(
            output_root,
            owner_type="review",
            owner_id=str(item["trial_id"]),
            events=record["operation_events"],
        )
        records.append(record)
    return records


def _source_for_scope(pipeline: Any, target: Mapping[str, Any]) -> str:
    source = next(item.content for item in pipeline.files if item.path == target["file"])
    lines = source.splitlines(keepends=True)
    return "".join(lines[int(target["start_line"]) - 1 : int(target["end_line"])])


def _apply_scoped_source_for_job(
    job_id: str,
    pipeline: Any,
    target: Mapping[str, Any],
    replacement_source: str,
) -> Any:
    payload = _pipeline_payload(pipeline)
    target_file = next(item for item in payload["files"] if item["path"] == target["file"])
    lines = str(target_file["content"]).splitlines(keepends=True)
    indent = lines[int(target["start_line"]) - 1][: len(lines[int(target["start_line"]) - 1]) - len(lines[int(target["start_line"]) - 1].lstrip())]
    replacement_lines = replacement_source.strip("\n").splitlines()
    if replacement_lines and indent and not replacement_lines[0].startswith(indent):
        replacement_lines = [indent + line if line.strip() else line for line in replacement_lines]
    target_file["content"] = "".join(
        [
            *lines[: int(target["start_line"]) - 1],
            "\n".join(replacement_lines) + "\n",
            *lines[int(target["end_line"]) :],
        ]
    )
    return parse_generated_pipeline(job_id, payload)


def _replacement_source_from_response(
    response: Mapping[str, Any], target: Mapping[str, Any]
) -> str:
    pipeline = response.get("pipeline")
    if not isinstance(pipeline, Mapping):
        raise ValueError("repair response has no pipeline object")
    files = pipeline.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise ValueError("repair response must contain exactly one selected-source replacement")
    selected = files[0]
    if not isinstance(selected, Mapping) or selected.get("path") != target.get("file"):
        raise ValueError("repair response path differs from the selected source file")
    if pipeline.get("entry_file") != target.get("file"):
        raise ValueError("repair response entry_file differs from the selected source file")
    if pipeline.get("review_boundaries") != []:
        raise ValueError("repair response must not return declaration or bundle metadata")
    content = selected.get("content")
    if not isinstance(content, str):
        raise ValueError("repair response selected-source replacement is not text")
    return content


def _repair_target_from_review(
    instance: Mapping[str, Any],
    package_record: Mapping[str, Any],
    review: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[str, Any, dict[str, Any]]:
    if (
        review.get("trial_id") is None
        or review.get("branch_id") != package_record.get("branch_id")
        or review.get("instance_id") != instance.get("instance_id")
    ):
        raise ValueError("repair is not paired with its same-trial review and package")
    localisation = review.get("localisation")
    if not isinstance(localisation, Mapping) or localisation.get("frozen") is not True:
        raise ValueError("repair target requires a frozen same-trial localisation")
    opaque_boundary_id = str(localisation.get("top_suspect_boundary_id") or "")
    reverse_ids = {
        str(opaque): str(original)
        for original, opaque in manifest.get("controller_boundary_id_map", {}).items()
    }
    original_boundary_id = reverse_ids.get(opaque_boundary_id)
    if original_boundary_id is None:
        raise ValueError("frozen top suspect is outside the assigned package")
    job_id = str(package_record["assigned_job_id"])
    realization = instance["evaluation_execution"]["realizations"][job_id]
    matches = [
        boundary
        for boundary in realization["realized_boundaries"]
        if str(boundary["boundary_id"]) == original_boundary_id
    ]
    if len(matches) != 1:
        raise ValueError("frozen top suspect does not resolve to one realized boundary")
    qualified_name = str(matches[0]["static_identity"]["qualified_function_name"])
    pipeline = instance["jobs"][job_id]
    target = source_scope(
        pipeline,
        function_name=qualified_name.split(".")[-1],
        mode="boundary",
    )
    if target.get("scope_kind") != "function" or target.get("effective_mode") != "boundary":
        raise ValueError("repair target is not one exact function boundary")
    target.update(
        {
            "boundary_id": opaque_boundary_id,
            "realized_boundary_id": original_boundary_id,
            "qualified_function_name": qualified_name,
            "selection_reason": "same-trial condition-owned frozen top suspect",
        }
    )
    return job_id, pipeline, target


def _record_repair_failure(
    output_root: Path,
    item: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    classification: str,
    reason: str,
    repair_attempted: bool,
    response: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    call_records = (
        [{"purpose": "repair", **_call_usage(response)}]
        if response is not None
        else []
    )
    usage = (
        _aggregate_usage(call_records)
        if call_records
        else _aggregate_usage([{"attempt_count": 1}])
        if repair_attempted
        else _aggregate_usage([])
    )
    operation_events = [
        _operation(
            "scoped_repair",
            "failed" if repair_attempted else "rejected",
            call=call_records[0] if call_records else None,
            details={"repair_attempted": repair_attempted},
            errors=[reason],
        )
    ]
    record = {
        **item,
        "status": "missing" if classification == "provider_failure" else "complete",
        "repair_attempted": repair_attempted,
        "repair_success": False,
        "failure_classification": classification,
        "failure_reason": reason,
        "review_request_sha256": review.get("request_sha256"),
        "paired_review_trial_id": review.get("trial_id"),
        "call_records": call_records,
        "operation_events": operation_events,
        **usage,
    }
    if response is not None:
        record.update(
            {
                key: value
                for key, value in response.items()
                if key not in {"real_model_call", "response"}
            }
        )
        record["provider_response"] = response.get("response")
    path = output_root / "repairs" / f"{item['repair_id']}.json"
    create_json_exclusive(path, record)
    append_record(
        output_root / "ledger",
        record_type="repair",
        record_id=str(item["repair_id"]),
        payload=record,
    )
    _record_operation_events(
        output_root,
        owner_type="repair",
        owner_id=str(item["repair_id"]),
        events=operation_events,
    )
    return record


def _repair_re_review(
    repo_root: Path,
    output_root: Path,
    call_provider: Provider,
    *,
    item: Mapping[str, Any],
    review: Mapping[str, Any],
    package_record: Mapping[str, Any],
    rerun_jobs: Mapping[str, Any],
    rerun: Mapping[str, Any],
    job_id: str,
    branch: Path,
) -> dict[str, Any]:
    scenario = load_preflight_inputs(repo_root, EXPERIMENT_ROOT)
    repaired_inputs, repaired_opaque_jobs = _package_inputs(
        rerun_jobs, scenario, rerun, job_id, package_record
    )
    mode = str(package_record["evidence_mode"])
    projection = None
    repaired_handoffs = [
        {
            "handoff_ref": value["handoff_id"],
            "upstream_job_id": value["upstream_job_id"],
            "downstream_job_id": value["downstream_job_id"],
            "artifact_sha256": value["producer_sha256"],
        }
        for value in rerun["handoffs"]
    ]
    if mode.startswith("etiq_"):
        random_manifests = None
        if mode == "etiq_random_matched":
            fixed = graph_selection_for_mode(
                "etiq_selected_fixed",
                rerun["executions"][job_id].snapshot,
                rerun["realizations"][job_id]["realized_boundaries"],
                handoffs=repaired_handoffs,
                include_projection_binding=True,
            )
            assert fixed is not None
            random_manifests = freeze_random_projections(
                branch / "re-review-random-projections",
                rerun["executions"][job_id].snapshot,
                rerun["realizations"][job_id]["realized_boundaries"],
                fixed,
                instance_id=str(item["instance_id"]),
                handoffs=repaired_handoffs,
                protocol_content_hash=PROTOCOL_CONTENT_SHA256,
            )
        projection = graph_selection_for_mode(
            mode,
            rerun["executions"][job_id].snapshot,
            rerun["realizations"][job_id]["realized_boundaries"],
            handoffs=repaired_handoffs,
            frozen_random_by_boundary=random_manifests,
            random_instance_id=str(item["instance_id"]),
            random_protocol_content_hash=PROTOCOL_CONTENT_SHA256,
            include_projection_binding=True,
        )
    repaired_package, repaired_manifest = build_n05_condition_package(
        protocol_content_hash=PROTOCOL_CONTENT_SHA256,
        protocol_version="2.2.0",
        evidence_mode=mode,
        source_setting=str(package_record["source_setting"]),
        snapshot=rerun["executions"][job_id].snapshot,
        realization=rerun["realizations"][job_id],
        handoffs=rerun["handoffs"],
        frozen_projection=projection,
        controller_job_id_map=repaired_opaque_jobs,
        **repaired_inputs,
    )
    re_review_root = branch / "re-review-package"
    materialize_branch_package(re_review_root, repaired_package, repaired_manifest)
    verify_materialized_branch(re_review_root)
    reviewed = _review_package(
        output_root,
        call_provider,
        {
            "trial_id": f"{item['repair_id']}-re-review",
            "seed": int(review["seed"]),
            "branch_id": item["branch_id"],
            "designation": "no_injection_control",
            "ground_truth_boundary_id": None,
            "package_path": str(re_review_root / "evidence/review-package.json"),
        },
        repaired_package,
        snapshot=rerun["executions"][job_id].snapshot,
        realization=rerun["realizations"][job_id],
        handoffs=repaired_handoffs,
        manifest=repaired_manifest,
    )
    if not reviewed["valid"]:
        raise ValueError("re-review receipt remained invalid: " + "; ".join(reviewed["errors"]))
    suspects = _receipt_suspects(reviewed["package"], reviewed["response"])
    return {
        "request_sha256": str(reviewed["response"]["request_sha256"]),
        "suspect_boundary_ids": suspects,
        "validated_receipt": True,
        "receipt": reviewed["response"].get("response"),
        "package_sha256": repaired_manifest["package_sha256"],
        "call_records": reviewed["call_records"],
        "operation_records": reviewed["operation_records"],
        "correction_records": reviewed["correction_records"],
        "operation_events": reviewed["operation_events"],
        "usage": reviewed["usage"],
    }


def _run_repairs(
    repo_root: Path,
    output_root: Path,
    instances: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    call_provider: Provider,
) -> list[dict[str, Any]]:
    review_by_trial = {item["trial_id"]: item for item in reviews}
    instance_by_id = {item["instance_id"]: item for item in instances}
    package_by_branch = {item["branch_id"]: item for item in packages}
    records = []
    for item in expected_design()["repair_traces"]:
        record_path = output_root / "repairs" / f"{item['repair_id']}.json"
        if record_path.is_file():
            records.append(_load_json(record_path))
            continue
        review = review_by_trial[item["trial_id"]]
        instance = instance_by_id[item["instance_id"]]
        package_record = package_by_branch[item["branch_id"]]
        if (
            review.get("trial_id") != item["trial_id"]
            or review.get("branch_id") != item["branch_id"]
            or review.get("instance_id") != item["instance_id"]
        ):
            raise ValueError("N10 repair pairing differs from the exact same-trial review")
        if not review.get("validated_receipt") or not review.get("top_suspect_exact"):
            classification = (
                "missing_or_invalid_review"
                if not review.get("validated_receipt")
                else "missed_or_wrong_localisation"
            )
            reason = (
                "same-trial review has no valid receipt"
                if not review.get("validated_receipt")
                else "same-trial review missed or selected the wrong boundary"
            )
            record = {
                **item,
                "status": "complete",
                "repair_attempted": False,
                "repair_success": False,
                "failure_classification": classification,
                "failure_reason": reason,
                "review_request_sha256": review.get("request_sha256"),
                "paired_review_trial_id": review.get("trial_id"),
                "call_records": [],
                "operation_events": [
                    _operation(
                        "repair_target_selection",
                        "rejected",
                        details={"top_suspect_boundary_id": review.get("top_suspect_boundary_id")},
                        errors=[reason],
                    )
                ],
                **_aggregate_usage([]),
            }
            create_json_exclusive(record_path, record)
            append_record(output_root / "ledger", record_type="repair", record_id=item["repair_id"], payload=record)
            _record_operation_events(
                output_root,
                owner_type="repair",
                owner_id=str(item["repair_id"]),
                events=record["operation_events"],
            )
            records.append(record)
            continue
        mutation = instance["mutation"]
        if mutation is None:
            raise ValueError("N10 repair subset unexpectedly contains a control")
        manifest = _load_json(
            output_root / "packages" / item["branch_id"] / "evidence/package-manifest.json"
        )
        job_id, faulty_pipeline, target = _repair_target_from_review(
            instance, package_record, review, manifest
        )
        clean_pipeline = instance["clean_jobs"][job_id]
        selected_source = {**target, "content": _source_for_scope(faulty_pipeline, target)}
        clean_target = source_scope(
            clean_pipeline,
            function_name=str(target["function_name"]),
            mode="boundary",
        )
        clean_selected_source = _source_for_scope(clean_pipeline, clean_target)
        try:
            response = _call_provider(
                output_root,
                call_provider,
                "repair",
                {
                    **item,
                    "package_path": str(
                        output_root
                        / "packages"
                        / item["branch_id"]
                        / "evidence/review-package.json"
                    ),
                    "review": {
                        "trial_id": review["trial_id"],
                        "receipt": review["receipt"],
                        "localisation": review["localisation"],
                    },
                    "selected_source": selected_source,
                    "clean_selected_source": clean_selected_source,
                },
                parent_id=item["repair_id"],
            )
        except RuntimeError as error:
            records.append(
                _record_repair_failure(
                    output_root,
                    item,
                    review,
                    classification="provider_failure",
                    reason=str(error),
                    repair_attempted=True,
                )
            )
            continue
        provider_payload = dict(response.get("response") or {})
        try:
            replacement_source = _replacement_source_from_response(provider_payload, target)
            replacement = _apply_scoped_source_for_job(
                job_id,
                faulty_pipeline,
                target,
                replacement_source,
            )
            validate_repair_scope(faulty_pipeline, replacement, dict(target))
        except (KeyError, TypeError, ValueError) as error:
            records.append(
                _record_repair_failure(
                    output_root,
                    item,
                    review,
                    classification="invalid_or_out_of_scope_patch",
                    reason=f"{type(error).__name__}: {error}",
                    repair_attempted=True,
                    response=response,
                )
            )
            continue
        rerun_jobs = dict(instance["jobs"])
        rerun_jobs[job_id] = replacement
        job_ids = list(rerun_jobs)
        rerun_ids = job_ids[job_ids.index(job_id) :]
        branch_id = stable_id("branch", [item["repair_id"], "rerun"], int(review["trial_index"]))
        branch = output_root / "repair-work" / item["repair_id"] / branch_id
        try:
            materialize_opaque_branch(
                branch,
                allowlist={
                    "scenario.json": repo_root / EXPERIMENT_ROOT / "scenario.json",
                    "corpus.json": repo_root / EXPERIMENT_ROOT / "corpus.json",
                    "capabilities.json": repo_root / EXPERIMENT_ROOT / "capabilities.json",
                    "oracles.json": repo_root / EXPERIMENT_ROOT / "oracles.json",
                },
                manifest_identity={"repair_id": item["repair_id"], "purpose": "n10-repair-rerun"},
            )
            copy_etiq_worker_runtime(branch, repo_root / "src")
            rerun = _rerun_dependency_suffix(
                branch,
                repo_root=repo_root,
                jobs=rerun_jobs,
                scenario=load_preflight_inputs(repo_root, EXPERIMENT_ROOT),
                repaired_job_id=job_id,
                canonical_execution=instance["evaluation_execution"],
                run_index=int(review["trial_index"]),
                stage=f"n10-repair-{item['repair_id']}",
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as error:
            records.append(
                _record_repair_failure(
                    output_root,
                    item,
                    review,
                    classification="rerun_crash_schema_or_oracle_failure",
                    reason=f"{type(error).__name__}: {error}",
                    repair_attempted=True,
                    response=response,
                )
            )
            continue
        oracle_passed = bool(rerun["oracle"]["passed"])
        re_review: dict[str, Any] | None = None
        try:
            re_review = _repair_re_review(
                repo_root,
                output_root,
                call_provider,
                item=item,
                review=review,
                package_record=package_record,
                rerun_jobs=rerun_jobs,
                rerun=rerun,
                job_id=job_id,
                branch=branch,
            )
            re_review_suspects = list(re_review["suspect_boundary_ids"])
            repair_success = oracle_passed and not re_review_suspects
            if not oracle_passed:
                failure_classification = "rerun_oracle_failure"
                failure_reason = "repaired suffix failed behavioural oracle"
            elif re_review_suspects:
                failure_classification = "re_review_regression"
                failure_reason = "repaired-run review retained a suspect boundary"
            else:
                failure_classification = None
                failure_reason = None
        except (KeyError, RuntimeError, TypeError, ValueError) as error:
            re_review_suspects = []
            repair_success = False
            failure_classification = "re_review_failure"
            failure_reason = f"{type(error).__name__}: {error}"
        call_records = [{"purpose": "repair", **_call_usage(response)}]
        if re_review is not None:
            call_records.extend(
                {"phase": "re_review", **dict(value)}
                for value in re_review["call_records"]
            )
        operation_events = [
            _operation(
                "repair_target_selection",
                "completed",
                details=target,
            ),
            _operation(
                "scoped_repair",
                "completed",
                call=call_records[0],
                details={"selected_function": target["qualified_function_name"]},
            ),
            _operation(
                "rerun_recapture",
                "completed",
                details={
                    "rerun_job_ids": rerun_ids,
                    "oracle": rerun["oracle"],
                    "handoffs": rerun["handoffs"],
                },
            ),
        ]
        if re_review is not None:
            operation_events.extend(re_review["operation_events"])
        else:
            operation_events.append(
                _operation("re_review", "failed", errors=[failure_reason or "re-review failed"])
            )
        record = {
            **item,
            **{key: value for key, value in response.items() if key not in {"real_model_call", "response"}},
            "status": "complete",
            "repair_attempted": True,
            "repair_success": repair_success,
            "failure_classification": failure_classification,
            "failure_reason": failure_reason,
            "paired_review_trial_id": review["trial_id"],
            "repair_target": target,
            "rerun_job_ids": rerun_ids,
            "rerun_oracle": rerun["oracle"],
            "re_review_request_sha256": (
                re_review["request_sha256"] if re_review is not None else None
            ),
            "re_review_suspect_boundary_ids": re_review_suspects,
            "re_review": re_review,
            "rerun_capture_sha256": {
                current_job_id: sha256_bytes(canonical_json(jsonable(rerun["executions"][current_job_id].snapshot)))
                for current_job_id in rerun_ids
            },
            "package_sha256": package_record["package_sha256"],
            "provider_response": provider_payload,
            "replacement_source_sha256": sha256_bytes(replacement_source.encode()),
            "repair_diff": repair_diff(faulty_pipeline, replacement),
            "repaired_source_sha256": sha256_bytes(
                canonical_json(_pipeline_payload(replacement))
            ),
            "call_records": call_records,
            "operation_events": operation_events,
            **_aggregate_usage(call_records),
        }
        create_json_exclusive(output_root / "repairs" / f"{item['repair_id']}.json", record)
        append_record(output_root / "ledger", record_type="repair", record_id=item["repair_id"], payload=record)
        _record_operation_events(
            output_root,
            owner_type="repair",
            owner_id=str(item["repair_id"]),
            events=operation_events,
        )
        records.append(record)
    return records


def _execution_state(output_root: Path, execution: Mapping[str, Any]) -> dict[str, Any]:
    runs = {}
    for job_id, run in execution["executions"].items():
        run_dir = Path(run.run_dir).resolve()
        try:
            relative_run_dir = run_dir.relative_to(output_root.resolve()).as_posix()
        except ValueError as error:
            raise ValueError("N10 resumable execution path is outside its attempt root") from error
        runs[job_id] = {
            "run_dir": relative_run_dir,
            "snapshot": jsonable(run.snapshot),
        }
    return {
        "executions": runs,
        **{
            key: jsonable(value)
            for key, value in execution.items()
            if key != "executions"
        },
    }


def _restore_execution(output_root: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    runs = {}
    for job_id, value in state["executions"].items():
        snapshot = dict(value["snapshot"])
        runs[job_id] = EtiqExecution(
            snapshot=EtiqEvidenceSnapshot(
                snapshot_id=str(snapshot["snapshot_id"]),
                job_id=str(snapshot["job_id"]),
                run_id=str(snapshot["run_id"]),
                nodes=[EtiqNodeRecord(**item) for item in snapshot["nodes"]],
                relationships=[
                    EtiqRelationshipRecord(**item)
                    for item in snapshot["relationships"]
                ],
                inventories=dict(snapshot["inventories"]),
                scan_errors=list(snapshot["scan_errors"]),
                created_at=str(snapshot["created_at"]),
                schema_version=str(snapshot["schema_version"]),
            ),
            run_dir=output_root / str(value["run_dir"]),
        )
    return {
        "executions": runs,
        **{key: value for key, value in state.items() if key != "executions"},
    }


def _write_pre_review_state(
    output_root: Path,
    instances: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    packages: list[dict[str, Any]],
) -> Path:
    serialized_instances = []
    excluded = {
        "jobs",
        "clean_jobs",
        "clean_execution",
        "evaluation_execution",
        "mutation",
    }
    for instance in instances:
        mutation = instance["mutation"]
        serialized_instances.append(
            {
                **{
                    key: jsonable(value)
                    for key, value in instance.items()
                    if key not in excluded
                },
                "jobs": {
                    job_id: _pipeline_payload(pipeline)
                    for job_id, pipeline in instance["jobs"].items()
                },
                "clean_jobs": {
                    job_id: _pipeline_payload(pipeline)
                    for job_id, pipeline in instance["clean_jobs"].items()
                },
                "evaluation_execution": _execution_state(
                    output_root, instance["evaluation_execution"]
                ),
                "mutation": (
                    {
                        key: jsonable(mutation[key])
                        for key in (
                            "target_job_id",
                            "operator",
                            "schedule_sha256",
                            "site",
                            "validation",
                            "rejections",
                        )
                    }
                    if mutation is not None
                    else None
                ),
            }
        )
    state = {
        "schema_version": "1",
        "instances": serialized_instances,
        "captures": captures,
        "packages": packages,
    }
    state["state_sha256"] = sha256_bytes(canonical_json(state))
    path = output_root / "state/pre-review-state.json"
    create_json_exclusive(path, state)
    return path


def _load_pre_review_state(
    output_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    state = _load_json(output_root / "state/pre-review-state.json")
    recorded = state.get("state_sha256")
    unsigned = dict(state)
    unsigned.pop("state_sha256", None)
    if recorded != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("N10 resumable pre-review state hash mismatch")
    instances = []
    for value in state["instances"]:
        instance = dict(value)
        instance["jobs"] = {
            job_id: parse_generated_pipeline(job_id, payload)
            for job_id, payload in value["jobs"].items()
        }
        instance["clean_jobs"] = {
            job_id: parse_generated_pipeline(job_id, payload)
            for job_id, payload in value["clean_jobs"].items()
        }
        instance["evaluation_execution"] = _restore_execution(
            output_root, value["evaluation_execution"]
        )
        instances.append(instance)
    return instances, list(state["captures"]), list(state["packages"])


def _write_experiment_freeze(
    repo_root: Path,
    output_root: Path,
    instances: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    governance_bindings: Mapping[str, Any] | None = None,
) -> Path:
    if (output_root / "reviews").exists() and any((output_root / "reviews").iterdir()):
        raise ValueError("N10 experiment freeze must precede every experimental review record")
    if (
        len(instances) != 12
        or len(captures) != 12
        or len(packages) != 96
        or any(not value.get("verified") for value in packages)
    ):
        raise ValueError("N10 experiment freeze requires exact verified pre-review counts")
    design = expected_design()
    ground_truth = [
        {
            "instance_id": instance["instance_id"],
            "designation": instance["designation"],
            "target_job_id": (
                instance["mutation"]["target_job_id"]
                if instance["mutation"] is not None
                else None
            ),
            "operator": (
                instance["mutation"]["operator"]
                if instance["mutation"] is not None
                else None
            ),
            "injected_function": (
                instance["mutation"]["site"]["qualified_function_name"]
                if instance["mutation"] is not None
                else None
            ),
        }
        for instance in instances
    ]
    freeze = {
        "schema_version": "1",
        "status": "frozen_before_first_experimental_review",
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "accepted_phase_a_sha256": ACCEPTED_PHASE_A_SHA256,
        "accepted_phase_a_tree_sha256": ACCEPTED_PHASE_A_TREE_SHA256,
        "governance_bindings": dict(governance_bindings or {}),
        "expected_counts": EXPECTED_COUNTS,
        "source_tree": _tree_contract(repo_root, repo_root / "src/use_case_icp"),
        "prompt_tree": _tree_contract(repo_root, repo_root / "prompts/v2_2"),
        "schema_tree": _tree_contract(repo_root, repo_root / "schemas/v2_2"),
        "instances": _tree_contract(repo_root, output_root / "instances"),
        "captures": _tree_contract(repo_root, output_root / "captures"),
        "package_records": _tree_contract(repo_root, output_root / "package-records"),
        "packages": _tree_contract(repo_root, output_root / "packages"),
        "pre_review_state_sha256": sha256_file(
            output_root / "state/pre-review-state.json"
        ),
        "instance_schedule": _protocol_instance_slots(repo_root),
        "review_design_sha256": sha256_bytes(canonical_json(design["review_trials"])),
        "repair_design_sha256": sha256_bytes(canonical_json(design["repair_traces"])),
        "ground_truth": ground_truth,
        "environment": {
            "python": sys.version.split()[0],
            "etiq_copilot": importlib.metadata.version("etiq-copilot"),
            "bubblewrap": bubblewrap_version(),
            "launcher": launch_policy_identity(),
        },
        "authority_consumption_sha256": sha256_file(
            output_root / "authority-consumption.json"
        ),
        "experimental_review_records_at_freeze": 0,
    }
    freeze["freeze_sha256"] = sha256_bytes(canonical_json(freeze))
    path = output_root / "experiment-freeze.json"
    create_json_exclusive(path, freeze)
    return path


def _close_and_analyze(
    output_root: Path,
    instances: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    repairs: list[dict[str, Any]],
    governance_bindings: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    design = expected_design()
    reconciliation = reconcile_records(design, reviews, repairs)
    if not reconciliation["passed"]:
        raise ValueError("N07 ledger reconciliation failed")
    expected_instances = set(design["instances"])
    observed_instances = [str(item.get("instance_id") or "") for item in instances]
    observed_captures = [str(item.get("instance_id") or "") for item in captures]
    expected_branches = {item["branch_id"] for item in design["branches"]}
    observed_branches = [str(item.get("branch_id") or "") for item in packages]
    if (
        set(observed_instances) != expected_instances
        or len(observed_instances) != len(set(observed_instances))
        or set(observed_captures) != expected_instances
        or len(observed_captures) != len(set(observed_captures))
        or set(observed_branches) != expected_branches
        or len(observed_branches) != len(set(observed_branches))
        or any(not item.get("verified") for item in packages)
    ):
        raise ValueError("N10 observed instance, capture, or package membership differs from the frozen design")
    if any(
        item.get("status") not in {"complete", "missing"}
        or (item.get("status") == "missing" and not item.get("failure_classification"))
        or (item.get("status") == "complete" and not item.get("call_records"))
        for item in reviews
    ):
        raise ValueError("N10 observed review outcomes are not completely classified")
    if any(
        item.get("status") not in {"complete", "missing"}
        or (item.get("status") == "missing" and not item.get("failure_classification"))
        for item in repairs
    ):
        raise ValueError("N10 observed repair outcomes are not completely classified")
    instance_authoring_calls = [
        call
        for instance in instances
        for call in instance.get("authoring_call_records", [])
    ]
    instance_stabilization_calls = [
        call
        for instance in instances
        for call in instance.get("stabilization_call_records", [])
    ]
    review_calls = [call for review in reviews for call in review.get("call_records", [])]
    repair_calls = [call for repair in repairs for call in repair.get("call_records", [])]
    usage_by_phase = {
        "instance_authoring": _aggregate_usage(instance_authoring_calls),
        "instance_stabilization": _aggregate_usage(instance_stabilization_calls),
        "treatment_review": _aggregate_usage(review_calls),
        "treatment_repair_and_re_review": _aggregate_usage(repair_calls),
    }
    setup_calls = [
        *instance_authoring_calls,
        *instance_stabilization_calls,
    ]
    treatment_calls = [*review_calls, *repair_calls]
    missingness = {
        "reviews": sum(item.get("status") == "missing" for item in reviews),
        "repairs": sum(item.get("status") == "missing" for item in repairs),
        "review_failure_classifications": {
            classification: sum(item.get("failure_classification") == classification for item in reviews)
            for classification in sorted(
                {str(item.get("failure_classification")) for item in reviews if item.get("failure_classification")}
            )
        },
        "repair_failure_classifications": {
            classification: sum(item.get("failure_classification") == classification for item in repairs)
            for classification in sorted(
                {str(item.get("failure_classification")) for item in repairs if item.get("failure_classification")}
            )
        },
    }
    ledger_call_attempt_records = len(
        list((output_root / "ledger/call-attempt").glob("*.json"))
    )
    real_provider_attempts = _provider_usage_summary(output_root)[
        "real_provider_attempts"
    ]
    closure = {
        "schema_version": "1",
        "status": "closed",
        "observed_counts": {
            "instances": len(instances),
            "captures": len(captures),
            "packages": len(packages),
            "reviews": len(reviews),
            "repairs": len(repairs),
        },
        "reconciliation": reconciliation,
        "provider_attempt_records": real_provider_attempts,
        "ledger_call_attempt_records": ledger_call_attempt_records,
        "non_model_wrapper_records": ledger_call_attempt_records
        - real_provider_attempts,
        "operation_event_records": len(list((output_root / "ledger/operation-event").glob("*.json"))),
        "missingness": missingness,
        "usage_by_phase": usage_by_phase,
        "setup_usage": _aggregate_usage(setup_calls),
        "treatment_usage": _aggregate_usage(treatment_calls),
        "setup_usage_in_treatment_totals": False,
        "governance_bindings": dict(governance_bindings or {}),
    }
    if closure["observed_counts"] != EXPECTED_COUNTS:
        raise ValueError("N07 observed counts differ from the frozen design")
    create_json_exclusive(output_root / "ledger-closure.json", closure)
    analysis = analyze_frozen_results(packages, reviews, repairs)
    output_hashes = write_analysis_outputs(output_root / "analysis", analysis)
    return closure, {"analysis": analysis, "output_hashes": output_hashes}


def _replay(
    output_root: Path,
    reviews: list[dict[str, Any]],
    repairs: list[dict[str, Any]],
    analysis: Mapping[str, Any],
    governance_bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    design = expected_design()
    bundle = output_root / "replay"
    create_json_exclusive(bundle / "design.json", design)
    # offline_replay consumes exact JSON arrays for the result tables.
    create_bytes_exclusive(bundle / "branches.json", canonical_json(design["branches"]) + b"\n")
    create_bytes_exclusive(bundle / "reviews.json", canonical_json(reviews) + b"\n")
    create_bytes_exclusive(bundle / "repairs.json", canonical_json(repairs) + b"\n")
    create_json_exclusive(bundle / "expected-analysis.json", analysis)
    governance_path = bundle / "governance-bindings.json"
    create_json_exclusive(governance_path, dict(governance_bindings or {}))
    create_json_exclusive(
        bundle / "accepted-phase-a-binding.json",
        {
            "phase_a_sha256": ACCEPTED_PHASE_A_SHA256,
            "phase_a_tree_sha256": ACCEPTED_PHASE_A_TREE_SHA256,
        },
    )
    result = offline_replay(bundle)
    if result.get("passed") is not True:
        raise ValueError("N10 offline replay did not return an exact passing verification")
    create_json_exclusive(output_root / "replay-verification.json", result)
    public_files = {
        "analysis.json": output_root / "analysis/analysis.json",
        "instance-results.csv": output_root / "analysis/instance-results.csv",
        "headline-results.csv": output_root / "analysis/headline-results.csv",
        "headline-results.svg": output_root / "analysis/headline-results.svg",
        "replay-verification.json": output_root / "replay-verification.json",
        "governance-bindings.json": governance_path,
    }
    release = build_anonymous_release(output_root / "anonymous-release", public_files=public_files)
    release_verification = verify_anonymous_release(output_root / "anonymous-release")
    if release_verification.get("passed") is not True:
        raise ValueError("N10 anonymous release verification did not pass")
    create_json_exclusive(
        output_root / "release-verification.json", release_verification
    )
    return {
        "offline_replay": result,
        "release": release,
        "release_verification": release_verification,
    }


def _provider_usage_summary(output_root: Path) -> dict[str, Any]:
    attempts = []
    for path in sorted((output_root / "ledger/call-attempt").glob("*.json")):
        payload = _load_json(path).get("payload", {})
        result = payload.get("result", {})
        if isinstance(result, Mapping) and result.get("branch_id"):
            attempts.append(payload)
    values_by_field = {
        "input_tokens": [],
        "cached_input_tokens": [],
        "output_tokens": [],
    }
    unavailable_by_field = {key: [] for key in values_by_field}
    for attempt in attempts:
        usage = attempt.get("result", {}).get("usage")
        if not isinstance(usage, Mapping):
            for key in values_by_field:
                unavailable_by_field[key].append(attempt.get("call_id"))
            continue
        for key in values_by_field:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                values_by_field[key].append(value)
            else:
                unavailable_by_field[key].append(attempt.get("call_id"))
    totals = {
        key: None if unavailable_by_field[key] else sum(values)
        for key, values in values_by_field.items()
    }
    unavailable = sorted(
        {
            str(call_id)
            for values in unavailable_by_field.values()
            for call_id in values
        }
    )
    return {
        "real_provider_attempts": len(attempts),
        "usage": totals,
        "usage_unavailable_call_ids": unavailable,
        "usage_unavailable_by_field": {
            key: sorted(set(map(str, values)))
            for key, values in unavailable_by_field.items()
            if values
        },
    }


def _run_lifecycle(
    repo_root: Path,
    output_root: Path,
    *,
    provider: Provider,
    qualification: bool,
    stop_after: str | None = None,
    governance_bindings: Mapping[str, Any] | None = None,
) -> Path:
    if stop_after is not None and stop_after not in STAGES:
        raise ValueError("unknown N07 stop transition")
    if (output_root / "terminal.json").is_file():
        return output_root / "terminal.json"
    context: dict[str, Any] = {}
    checkpoints = sorted((output_root / "checkpoints").glob("*.json"))
    completed_stages = [path.stem.split("-", 1)[1] for path in checkpoints]
    if completed_stages != list(STAGES[: len(completed_stages)]):
        raise ValueError("N10 checkpoint lineage is not an exact stage prefix")
    start_index = len(completed_stages)
    if start_index:
        if start_index < STAGES.index("package") + 1:
            raise ValueError("N10 pre-results setup resumes in the next append-only attempt")
        (
            context["instances"],
            context["captures"],
            context["packages"],
        ) = _load_pre_review_state(output_root)
        if start_index > STAGES.index("review"):
            context["reviews"] = [
                _load_json(path) for path in sorted((output_root / "reviews").glob("*.json"))
            ]
        if start_index > STAGES.index("repair"):
            context["repairs"] = [
                _load_json(path) for path in sorted((output_root / "repairs").glob("*.json"))
            ]
        if start_index > STAGES.index("closure"):
            context["closure"] = _load_json(output_root / "ledger-closure.json")
            context["analysis_data"] = {
                "analysis": _load_json(output_root / "analysis/analysis.json"),
                "output_hashes": {},
            }
        if start_index > STAGES.index("replay"):
            release_verification = verify_anonymous_release(
                output_root / "anonymous-release"
            )
            if release_verification != _load_json(
                output_root / "release-verification.json"
            ):
                raise ValueError("N10 resumed release verification differs from stored evidence")
            context["replay"] = {
                "offline_replay": _load_json(output_root / "replay-verification.json"),
                "release": _load_json(
                    output_root / "anonymous-release/release-manifest.json"
                ),
                "release_verification": release_verification,
            }
    for index, stage in enumerate(STAGES):
        if index < start_index:
            continue
        if stop_after == stage:
            return _terminal_incomplete(
                output_root,
                stage,
                f"qualified injected failure at {stage}",
                experimental=not qualification,
                governance_bindings=governance_bindings,
            )
        try:
            if stage == "phase_a":
                context["phase_a"] = verify_accepted_phase_a(repo_root)
                payload = {**context["phase_a"], "status": "passed"}
            elif stage == "construction":
                context["instances"] = _construct_instances(repo_root, output_root, context["phase_a"], provider, qualification=qualification)
                payload = {"instances": len(context["instances"])}
            elif stage == "capture":
                context["captures"] = _capture_instances(output_root, context["instances"])
                payload = {"captures": len(context["captures"])}
            elif stage == "package":
                context["packages"] = _materialize_packages(repo_root, output_root, context["instances"])
                state_path = _write_pre_review_state(
                    output_root,
                    context["instances"],
                    context["captures"],
                    context["packages"],
                )
                freeze_path = (
                    None
                    if qualification
                    else _write_experiment_freeze(
                        repo_root,
                        output_root,
                        context["instances"],
                        context["captures"],
                        context["packages"],
                        governance_bindings,
                    )
                )
                payload = {
                    "packages": len(context["packages"]),
                    "all_frozen_before_reviews": True,
                    "pre_review_state_sha256": sha256_file(state_path),
                    "experiment_freeze_sha256": (
                        sha256_file(freeze_path) if freeze_path is not None else None
                    ),
                }
            elif stage == "review":
                if not qualification and not (output_root / "experiment-freeze.json").is_file():
                    raise ValueError("N10 live review requires the pre-review experiment freeze")
                context["reviews"] = _run_reviews(
                    output_root,
                    context["instances"],
                    context["packages"],
                    provider,
                )
                payload = {"reviews": len(context["reviews"])}
            elif stage == "repair":
                context["repairs"] = _run_repairs(
                    repo_root,
                    output_root,
                    context["instances"],
                    context["packages"],
                    context["reviews"],
                    provider,
                )
                payload = {"repairs": len(context["repairs"])}
            elif stage == "closure":
                context["closure"], context["analysis_data"] = _close_and_analyze(
                    output_root,
                    context["instances"],
                    context["captures"],
                    context["packages"],
                    context["reviews"],
                    context["repairs"],
                    governance_bindings,
                )
                payload = {"closed": True, "observed_counts": context["closure"]["observed_counts"], "reconciliation_sha256": context["closure"]["reconciliation"]["reconciliation_sha256"]}
            elif stage == "analysis":
                payload = {"analysis_sha256": context["analysis_data"]["analysis"]["analysis_sha256"], "output_hashes": context["analysis_data"]["output_hashes"]}
            else:
                replay_args = (
                    output_root,
                    context["reviews"],
                    context["repairs"],
                    context["analysis_data"]["analysis"],
                )
                context["replay"] = (
                    _replay(*replay_args, governance_bindings)
                    if governance_bindings is not None
                    else _replay(*replay_args)
                )
                payload = {"passed": True, "analysis_sha256": context["replay"]["offline_replay"]["analysis_sha256"], "release_manifest_sha256": context["replay"]["release"]["manifest_sha256"]}
            if governance_bindings and governance_bindings.get(
                "post_freeze_controller_correction_file_sha256"
            ):
                payload["governance_bindings"] = dict(governance_bindings)
            _checkpoint(output_root, index, stage, payload)
            completed_stages.append(stage)
        except Exception as exc:
            if (output_root / "experiment-freeze.json").is_file():
                resume_index = len(list((output_root / "ledger/resume-event").glob("*.json")))
                append_record(
                    output_root / "ledger",
                    record_type="resume-event",
                    record_id=f"resume-{resume_index:03d}",
                    payload={
                        "stage": stage,
                        "reason": f"{type(exc).__name__}: {exc}",
                        "completed_checkpoints": completed_stages,
                        "code_changes_permitted": False,
                    },
                )
                raise
            return _terminal_incomplete(
                output_root,
                stage,
                f"{type(exc).__name__}: {exc}",
                experimental=not qualification,
                governance_bindings=governance_bindings,
            )
    terminal = {
        "schema_version": "1",
        "status": "completed_experiment_and_analysis",
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "accepted_phase_a_sha256": ACCEPTED_PHASE_A_SHA256,
        "accepted_phase_a_tree_sha256": ACCEPTED_PHASE_A_TREE_SHA256,
        "governance_bindings": dict(governance_bindings or {}),
        "mode": "no_model_qualification" if qualification else "live",
        "observed_counts": context["closure"]["observed_counts"],
        "ledger_closed": True,
        "reconciliation_sha256": context["closure"]["reconciliation"]["reconciliation_sha256"],
        "analysis_sha256": context["analysis_data"]["analysis"]["analysis_sha256"],
        "replay_passed": context["replay"]["offline_replay"]["passed"],
        "release_checksums_verified": context["replay"]["release_verification"]["passed"],
        "real_model_calls": (
            0
            if qualification
            else _provider_usage_summary(output_root)["real_provider_attempts"]
        ),
        "provider_usage": (
            {"real_provider_attempts": 0, "usage": {}, "usage_unavailable_call_ids": []}
            if qualification
            else _provider_usage_summary(output_root)
        ),
        "setup_usage_in_treatment_totals": False,
        "last_checkpoint_sha256": sha256_file(output_root / "checkpoints/08-replay.json"),
    }
    terminal["terminal_sha256"] = sha256_bytes(canonical_json(terminal))
    create_json_exclusive(output_root / "terminal.json", terminal)
    return output_root / "terminal.json"


def run_n07_study(
    repo_root: Path,
    output_root: Path,
    *,
    mode: str,
    call_provider: Provider | None = None,
    qualification_authority: Path | None = None,
    tester_gate_path: Path | None = None,
    stop_after: str | None = None,
) -> Path:
    """Run readiness, no-model qualification, or the continuous live lifecycle."""
    if mode not in {"check_ready", "qualify_lifecycle", "live"}:
        raise ValueError("unknown N07 controller mode")
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    readiness = validate_n07_readiness(
        repo_root,
        output_root,
        qualification_authority=qualification_authority,
        tester_gate_path=tester_gate_path,
        live=mode == "live",
    )
    readiness_path = _write_readiness(output_root, readiness, mode.replace("_", "-"))
    if mode == "check_ready":
        return readiness_path
    qualification = mode == "qualify_lifecycle"
    provider = call_provider or (
        _qualification_provider(repo_root)
        if qualification
        else _live_provider(repo_root, output_root)
    )
    _consume_authority(output_root, readiness, qualification=qualification)
    return _run_lifecycle(
        repo_root,
        output_root,
        provider=provider,
        qualification=qualification,
        stop_after=stop_after,
    )


def run_n08_study(
    repo_root: Path,
    output_root: Path,
    *,
    mode: str,
    source_codex_home: Path | None = None,
) -> Path:
    """Check localized N08 readiness or run the reused lifecycle continuously."""
    if mode not in {"check_ready", "live"}:
        raise ValueError("unknown N08 controller mode")
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    readiness = validate_n08_readiness(
        repo_root,
        output_root,
        source_codex_home=source_codex_home,
        require_correction_readiness=mode == "live",
    )
    readiness_path = _write_readiness(output_root, readiness, mode.replace("_", "-"))
    if mode == "check_ready":
        return readiness_path
    _consume_n08_authority(output_root, readiness)
    provider = _live_provider(
        repo_root,
        output_root,
        source_codex_home=source_codex_home,
    )
    return _run_lifecycle(
        repo_root,
        output_root,
        provider=provider,
        qualification=False,
    )


def run_n09_study(
    repo_root: Path,
    output_root: Path,
    *,
    mode: str,
    source_codex_home: Path | None = None,
) -> Path:
    """Check N09 readiness or continue the existing Phase-A candidate set."""
    if mode not in {"check_ready", "live"}:
        raise ValueError("unknown N09 controller mode")
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    readiness = validate_n09_readiness(
        repo_root,
        output_root,
        source_codex_home=source_codex_home,
        require_correction_readiness=mode == "live",
    )
    readiness_path = _write_readiness(output_root, readiness, mode.replace("_", "-"))
    if mode == "check_ready":
        return readiness_path
    _consume_n09_authority(output_root, readiness)
    provider = _live_provider(
        repo_root,
        output_root,
        source_codex_home=source_codex_home,
    )
    return _run_lifecycle(
        repo_root,
        output_root,
        provider=provider,
        qualification=False,
    )


def build_n07_execution_freeze(
    repo_root: Path,
    output_root: Path,
    *,
    readiness_command: list[str],
    lifecycle_command: list[str],
    readiness_status: Path,
    lifecycle_terminal: Path,
    command_outputs_root: Path,
    test_outputs_root: Path,
    freeze_name: str = "n07-execution-readiness-freeze.json",
    supersedes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze E0 only after the real CLI lifecycle and all zero-skip tests pass."""
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    if Path(freeze_name).name != freeze_name:
        raise ValueError("N07 E0 freeze name must be one file name")
    bindings = _validate_assets(repo_root)
    terminal = _load_json(lifecycle_terminal)
    if terminal.get("status") != "completed_experiment_and_analysis" or terminal.get("observed_counts") != EXPECTED_COUNTS:
        raise ValueError("N07 E0 lifecycle terminal is not a complete exact-count pass")
    if terminal.get("real_model_calls") != 0 or not terminal.get("replay_passed"):
        raise ValueError("N07 E0 lifecycle made a real call or failed replay")
    tests = _tree_contract(repo_root, test_outputs_root)
    for item in tests["files"]:
        text = (repo_root / item["path"]).read_text(errors="replace")
        if "FAILED" in text or "skipped=" in text or not text.rstrip().endswith("OK"):
            raise ValueError(f"N07 test output is not a zero-skip pass: {item['path']}")
    source_paths = (
        "src/use_case_icp/n07_program.py",
        "src/use_case_icp/__main__.py",
        "src/use_case_icp/n05_program.py",
        "src/use_case_icp/n05_runner.py",
        "src/use_case_icp/fault_experiment.py",
        "src/use_case_icp/fault_operations.py",
        "src/use_case_icp/n05_analysis.py",
    )
    freeze = {
        "schema_version": "1",
        "status": "frozen_for_independent_E1",
        "gate": "E0_complete_controller_and_full_lifecycle_qualification",
        "n07_authorization_sha256": N07_AUTHORITY_SHA256,
        "protocol_content_sha256": PROTOCOL_CONTENT_SHA256,
        "bindings": bindings,
        "expected_counts": EXPECTED_COUNTS,
        "commands": {
            "readiness": readiness_command,
            "lifecycle": lifecycle_command,
            "readiness_status_sha256": sha256_file(readiness_status),
            "lifecycle_terminal_sha256": sha256_file(lifecycle_terminal),
            "command_outputs": _tree_contract(repo_root, command_outputs_root),
        },
        "lifecycle_tree": _tree_contract(repo_root, lifecycle_terminal.parent),
        "tests": tests,
        "source": [_file_contract(repo_root, repo_root / path) for path in source_paths],
        "source_tree": _tree_contract(repo_root, repo_root / "src/use_case_icp"),
        "test_tree": _tree_contract(repo_root, repo_root / "tests"),
        "real_model_calls": 0,
        "live_authority_consumed": False,
        "supersedes": dict(supersedes or {}),
    }
    freeze["freeze_sha256"] = sha256_bytes(canonical_json(freeze))
    path = output_root / "e0" / freeze_name
    digest = create_json_exclusive(path, freeze)
    return {**freeze, "file_sha256": digest, "path": str(path)}
