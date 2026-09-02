"""Fault-blind v2 Phase-A mechanics and immutable N02 terminal guard."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Iterable, Mapping

from .codex_runner import CodexInvocationError, CodexRunner
from .etiq_executor import EtiqExecution, EtiqExecutor
from .fault_experiment import (
    MAX_PACKAGE_BYTES,
    build_stabilization_evidence,
    validate_reference_attempt,
    validate_stabilization_replacement,
)
from .fault_preflight import _parse_result, _sha256_tree
from .fault_v2 import (
    PROTOCOL_ID,
    PROTOCOL_VERSION,
    enrich_snapshot_identities_v2,
    freeze_reverse_ordering_order_v2,
    generated_pipeline_from_v2_payload,
    grouped_boundary_selection_v2,
    inject_reverse_ordering_v2,
    materialize_realized_boundaries_v2,
    validate_v2_controller_path,
    validate_v2_model_context_refs,
    validate_v2_output_root,
    v2_output_root,
)
from .job_store import JobStore
from .records import (
    AgentRequest,
    ContextArtifact,
    GeneratedPipeline,
    RootJobState,
    jsonable,
    new_id,
    stable_hash,
)
from .review import frame_name


PROTOCOL_HASH = "sha256:b23b50d50a88d85456ba97bb283e7f6072233f2db85d0cab0b7c46617113b5fb"
N02_DECISION_RELATIVE_PATH = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "N02_v2_fault_blind_phase_a_execution_authorization.json"
)
N02_DECISION_SHA256 = "764259090149000ca8f7689fd4d792e8b5f834dfde56dfc2d4b4cfd044dd38b5"
N01B_DEVELOPER_HANDOFF = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "N01B_v2_execution_readiness_marker_closure_to_overseer.email.md"
)
N01B_DEVELOPER_HANDOFF_SHA256 = "1a01f5863a4ccc3bef61b2faeda62935fffbea83d78f111195fbad995a1592af"
N01B_TESTER_HANDOFF = Path(
    "instructions_between_agent_types/tester/handoffs/"
    "N01B_v2_execution_readiness_to_overseer.email.md"
)
N01B_TESTER_HANDOFF_SHA256 = "fdc95646582b47d38ab0e4d843e560e62ed885525e83d9709d8b5ddc7be3da1f"
N02_ENVIRONMENT_GATE_NAME = "n02-environment-gate.json"
N02_CONSUMPTION_NAME = "n02-authorization-consumption.json"
N02_MARKER_NAME = "n02-phase-a-attempt.json"
N02_HISTORY_NAME = "n02-phase-a-history.jsonl"
N02_DIAGNOSTIC_NAME = "n02-authorization-diagnostics.jsonl"
N02_TERMINAL_OUTPUT_TREE_SHA256 = (
    "c8a5f10ae074bc304ef4179c72d284ca5740598952d7f1516b295ff995847377"
)
N02_TERMINAL_FILE_SHA256 = (
    "7da3fb2b5d382ec36459ab1a1f9af952ee4a12da83c4d69c7ae40f68d491146e"
)
N02_TERMINAL_INTERNAL_SHA256 = (
    "sha256:c72170549ba139ffa67f8daa9be8d385681ea11ca9fd79f8373a04da40aa199e"
)
N02_CONSUMPTION_SHA256 = (
    "5048f1b33ce805e237f280ec5df24a28f6e9eae8001f71648028bb46dac5b12d"
)
N02_PREFLIGHT_ID = "preflight-757510cb85594b83"
N02_SETUP_ID = "setup-449324dafbc44d26"
N03_DECISION_RELATIVE_PATH = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "N03_v2_fault_blind_phase_a_execution_authorization.json"
)
N03_DECISION_SHA256 = "02feb3287cb61284b469fc541016957949821c0709822ae4bb0101db074861a9"
N02B_DEVELOPER_OVERSEER_HANDOFF = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "N02B_v2_provider_error_wiring_to_overseer.email.md"
)
N02B_DEVELOPER_OVERSEER_HANDOFF_SHA256 = (
    "303f700ee53f3af36e98c4b2afef225e454488df149dccd4d008578e0815c54b"
)
N02B_DEVELOPER_TESTER_HANDOFF = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "N02B_v2_provider_error_wiring_to_tester.email.md"
)
N02B_DEVELOPER_TESTER_HANDOFF_SHA256 = (
    "587588052ef47e473b86b091dacad6eb1bec905829e7d3bfc82cf559cfae7b5c"
)
N02B_TESTER_HANDOFF = Path(
    "instructions_between_agent_types/tester/handoffs/"
    "N02B_v2_provider_error_wiring_to_overseer.email.md"
)
N02B_TESTER_HANDOFF_SHA256 = (
    "983b3ac739e8d0693f7b83cc643bb864abed536147b701148fb16f1a1883a798"
)
N03_STATE_DIR = "n03"
N03_ENVIRONMENT_GATE_NAME = "n03-environment-gate.json"
N03_CONSUMPTION_NAME = "n03-authorization-consumption.json"
N03_MARKER_NAME = "n03-phase-a-attempt.json"
N03_HISTORY_NAME = "n03-phase-a-history.jsonl"
N03_DIAGNOSTIC_NAME = "n03-authorization-diagnostics.jsonl"
N04_DECISION_RELATIVE_PATH = Path(
    "instructions_between_agent_types/overseer/decisions/"
    "N04_v2_boundary_qualname_remediation_and_phase_a_execution_authorization.json"
)
N04_DECISION_SHA256 = "2fc90c5b176c36a644322d7380645a627bdd1c2659e4802dfe9f2ba66ad34254"
N04_PRE_EXECUTION_OUTPUT_TREE_SHA256 = (
    "db49253a64a1dee022993d145df3371b3b90445804eb74c28bc65838861d30f6"
)
N04_N03_TREE_SHA256 = (
    "78e0ef12e207ba979f3760200fcfbde585d5cae6c0ca6e7ac6928b0e27850c9b"
)
N04_STATE_DIR = "n04"
N04_ENVIRONMENT_GATE_NAME = "n04-environment-gate.json"
N04_CONSUMPTION_NAME = "n04-authorization-consumption.json"
N04_MARKER_NAME = "n04-phase-a-attempt.json"
N04_HISTORY_NAME = "n04-phase-a-history.jsonl"
N04_DIAGNOSTIC_NAME = "n04-authorization-diagnostics.jsonl"
N03_DEVELOPER_OVERSEER_HANDOFF = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "N03_v2_phase_a_to_overseer.email.md"
)
N03_DEVELOPER_OVERSEER_HANDOFF_SHA256 = (
    "6a6b7a016901fc1b7e2f1a1d6f3452b9486b56b5bee46ec0af658e1976ce4453"
)
N03_DEVELOPER_TESTER_HANDOFF = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "N03_v2_phase_a_to_tester.email.md"
)
N03_DEVELOPER_TESTER_HANDOFF_SHA256 = (
    "45d499c2db0df482ba94b778b55ec970bd223409e096453794e03e1707af4416"
)
N03_DEVELOPER_PAPER_HANDOFF = Path(
    "instructions_between_agent_types/developer/handoffs/"
    "N03_v2_phase_a_to_paper_writer.email.md"
)
N03_DEVELOPER_PAPER_HANDOFF_SHA256 = (
    "a296b33b6db0ee8c2909a7ff54078055fc1d78705e0072e24a5183a4d0bcbd1f"
)
N03_TESTER_HANDOFF = Path(
    "instructions_between_agent_types/tester/handoffs/"
    "N03_v2_phase_a_to_overseer.email.md"
)
N03_TESTER_HANDOFF_SHA256 = (
    "eb25b043d43399aae2174cd723ca4624594709634a4ab363ee488e13591b06ad"
)
V2_PREFLIGHT_JOB_IDS = (
    "v2-evidence-needs-research",
    "v2-coverage-priority-synthesis",
)
V2_FIXTURE_RELATIVE_ROOT = Path(
    "docs/experiments/2026-workshop-fault-localisation-v2/fixtures/preflight"
)
PREDECESSOR_TREES = {
    "preflight-03420ef8721a4358": "4a1d6b02ef80a08b3ef8013096c91a8a8e00e89af7f537e7ec97a38a4dd2f8fb",
    "preflight-d06945d8ba2b4345": "af33dadd44d7aa53ed11ff8697281bdb92d6c1f2eb94c995bf0fecacc9960346",
    "preflight-e8a6bd2f06fb4c58": "288704e7fe007f0fe56a7db6572efdd7bb9d0bde0b993473dfcdf37c91ad6d78",
    "preflight-25f37de3755d421f": "ac5fc03316ccea2a0d2eafaa22174e5c19e45d52cba8bfd38a09aa8cba6f57a6",
}
AUTHORIZED_INPUT_PATHS = {
    "scenario_sha256": V2_FIXTURE_RELATIVE_ROOT / "scenario.json",
    "corpus_sha256": V2_FIXTURE_RELATIVE_ROOT / "corpus.json",
    "capabilities_sha256": V2_FIXTURE_RELATIVE_ROOT / "capabilities.json",
    "oracles_sha256": V2_FIXTURE_RELATIVE_ROOT / "oracles.json",
    "restricted_controller_plan_sha256": V2_FIXTURE_RELATIVE_ROOT
    / "restricted/controller-plan.json",
    "authoring_prompt_sha256": Path("prompts/v2/fault_chain_authoring.md"),
    "stabilization_prompt_sha256": Path("prompts/v2/fault_chain_stabilization.md"),
    "authoring_schema_sha256": Path("schemas/v2/fault_chain_authoring.schema.json"),
    "stabilization_schema_sha256": Path(
        "schemas/v2/fault_chain_stabilization.schema.json"
    ),
    "setup_record_schema_sha256": Path("schemas/v2/fault_setup_record.schema.json"),
    "ground_truth_schema_sha256": Path("schemas/v2/fault_ground_truth.schema.json"),
    "instance_schema_sha256": Path("schemas/v2/fault_instance.schema.json"),
    "arm_isolation_contract_sha256": Path(
        "docs/workshops/neurips-2026-v2/ARM_ISOLATION_CONTRACT.md"
    ),
    "arm_isolation_launch_policy_sha256": Path(
        "docs/workshops/neurips-2026-v2/arm-isolation-launch-policy.json"
    ),
}
AUTHOR_VISIBLE_KEYS = (
    "schema_version",
    "protocol_id",
    "protocol_version",
    "protocol_content_hash",
    "scenario_id",
    "phase",
    "scored",
    "authoring_seed",
    "job_ids",
    "dependencies",
    "authoring_requirements",
    "limits",
    "redistribution",
    "corpus",
    "capabilities",
)
SETUP_RECORD_KINDS = frozenset(
    {
        "preflight",
        "authoring",
        "authoring_request_failure",
        "stabilization_repair",
        "stabilization_request_failure",
        "rejected_candidate",
        "reference_execution",
        "reference_oracle",
        "complexity_gate",
    }
)
V2_MODEL_RESPONSE_SCHEMA_PATHS = (
    Path("schemas/v2/fault_chain_authoring.schema.json"),
    Path("schemas/v2/fault_chain_stabilization.schema.json"),
    Path("schemas/v2/fault_review_receipt.schema.json"),
    Path("schemas/v2/fault_repair_response.schema.json"),
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _encode(value: Any) -> bytes:
    return json.dumps(
        jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else _encode(value)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(payload), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def _create_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    jsonable(payload), indent=2, sort_keys=True, ensure_ascii=False
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(jsonable(payload), sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _artifact(ref: str, content: Any, purpose: str) -> ContextArtifact:
    return ContextArtifact(ref, stable_hash(content), "embedded", purpose, content)


def validate_strict_provider_schema(schema: Any, path: str = "$") -> None:
    """Require every response-schema object to be closed and fully required."""
    if isinstance(schema, Mapping):
        if schema.get("type") == "object":
            properties = schema.get("properties")
            if not isinstance(properties, Mapping):
                raise ValueError(f"{path}: object schema must declare properties")
            if schema.get("additionalProperties") is not False:
                raise ValueError(f"{path}: object schema must set additionalProperties false")
            required = schema.get("required")
            if (
                not isinstance(required, list)
                or len(required) != len(set(required))
                or set(required) != set(properties)
            ):
                raise ValueError(f"{path}: required must exactly match properties")
        for key, value in schema.items():
            validate_strict_provider_schema(value, f"{path}.{key}")
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            validate_strict_provider_schema(value, f"{path}[{index}]")


def validate_v2_model_response_schemas(repo_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in V2_MODEL_RESPONSE_SCHEMA_PATHS:
        path = repo_root / relative
        schema = json.loads(path.read_text(encoding="utf-8"))
        validate_strict_provider_schema(schema, relative.as_posix())
        hashes[relative.as_posix()] = "sha256:" + _sha256_file(path)
    return hashes


def classify_v2_request_failure(error: Exception) -> tuple[str, bool | None]:
    message = f"{error}\n{getattr(error, 'provider_error', '')}".casefold()
    deterministic_markers = (
        "invalid_json_schema",
        "unsupported frozen request",
        "unsupported request configuration",
        "malformed controller request",
        "additionalproperties is required",
        "required must exactly match properties",
    )
    retryable_markers = (
        "rate limit",
        "429",
        "connection",
        "temporarily unavailable",
        "service unavailable",
        "gateway timeout",
        "timed out",
        "timed_out",
        "timeout",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        '"status":"500"',
        '"status":"502"',
        '"status":"503"',
        '"status":"504"',
    )
    if any(marker in message for marker in deterministic_markers):
        return "deterministic_request_contract_failure", False
    if isinstance(error, (TimeoutError, ConnectionError)) or any(
        marker in message for marker in retryable_markers
    ):
        return "retryable_provider_infrastructure_failure", None
    if isinstance(error, CodexInvocationError):
        return "provider_failure_unknown_inference_status", None
    return "deterministic_controller_request_failure", False


def run_v2_request_with_retries(
    request: Callable[[], Any],
    *,
    candidate_number: int,
    request_identity: str,
    cycle: int = 0,
    request_stage: str = "authoring",
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for retry_number in range(3):
        try:
            return {"response": request(), "failures": failures, "stop_category": None}
        except Exception as error:
            category, inference_started = classify_v2_request_failure(error)
            usage = getattr(error, "usage", None)
            record = {
                "failure_category": category,
                "inference_started": inference_started,
                "candidate_number": candidate_number,
                "cycle": cycle,
                "retry_number": retry_number,
                "request_identity": request_identity,
                "request_stage": request_stage,
                "invocation_id": getattr(error, "invocation_id", None),
                "usage_available": bool(
                    isinstance(usage, Mapping)
                    and usage.get("usage_status") == "reported"
                ),
                "reason_type": type(error).__name__,
                "reason": str(error),
                "fresh_session": True,
            }
            failures.append(record)
            if (
                category == "retryable_provider_infrastructure_failure"
                and retry_number < 2
            ):
                continue
            return {
                "response": None,
                "failures": failures,
                "stop_category": category,
            }
    raise AssertionError("unreachable retry accounting state")


def load_v2_preflight_scenario(
    repo_root: Path, *, include_controller_plan: bool = False
) -> dict[str, Any]:
    fixture_root = validate_v2_controller_path(
        repo_root, V2_FIXTURE_RELATIVE_ROOT, operation="read"
    )
    scenario = json.loads((fixture_root / "scenario.json").read_text(encoding="utf-8"))
    scenario["corpus"] = json.loads(
        (fixture_root / scenario["corpus_path"]).read_text(encoding="utf-8")
    )
    scenario["capabilities"] = json.loads(
        (fixture_root / scenario["capability_catalogue_path"]).read_text(
            encoding="utf-8"
        )
    )
    scenario["oracles"] = json.loads(
        (fixture_root / scenario["oracle_path"]).read_text(encoding="utf-8")
    )
    if include_controller_plan:
        plan_path = validate_v2_controller_path(
            repo_root,
            fixture_root / "restricted/controller-plan.json",
            operation="read",
        )
        scenario["controller_plan"] = json.loads(
            plan_path.read_text(encoding="utf-8")
        )
    validate_v2_preflight_scenario(scenario)
    return scenario


def validate_v2_preflight_scenario(scenario: Mapping[str, Any]) -> None:
    if (
        scenario.get("protocol_id") != PROTOCOL_ID
        or scenario.get("protocol_version") != PROTOCOL_VERSION
        or scenario.get("protocol_content_hash") != PROTOCOL_HASH
        or scenario.get("phase") != "A"
        or scenario.get("scored") is not False
        or tuple(scenario.get("job_ids", ())) != V2_PREFLIGHT_JOB_IDS
        or scenario.get("authoring_seed") != 26082841
    ):
        raise ValueError("v2 preflight scenario identity is not frozen N02 input")
    limits = scenario.get("limits", {})
    if (
        limits.get("candidates") != 3
        or limits.get("stabilization_cycles_per_candidate") != 3
        or limits.get("reviewer_calls") != 0
    ):
        raise ValueError("v2 preflight limits differ from N02")
    dependencies = scenario.get("dependencies")
    if dependencies != [
        {
            "upstream": V2_PREFLIGHT_JOB_IDS[0],
            "downstream": V2_PREFLIGHT_JOB_IDS[1],
            "artifacts": ["needs", "evidence_sources"],
        }
    ]:
        raise ValueError("v2 preflight topology differs from N02")
    if not scenario.get("corpus", {}).get("records") or not scenario.get(
        "capabilities", {}
    ).get("capabilities"):
        raise ValueError("v2 author-visible fixtures are empty")
    if "controller_plan" in scenario:
        plan = scenario["controller_plan"]
        if (
            plan.get("storage_classification") != "restricted_controller_only"
            or plan.get("protocol_id") != PROTOCOL_ID
            or plan.get("protocol_version") != PROTOCOL_VERSION
            or plan.get("protocol_content_hash") != PROTOCOL_HASH
            or plan.get("mutation_seed") != 26082897
        ):
            raise ValueError("v2 controller plan identity is invalid")


def author_visible_v2_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    visible = {key: jsonable(scenario[key]) for key in AUTHOR_VISIBLE_KEYS}
    encoded = json.dumps(visible, sort_keys=True).casefold()
    prohibited = (
        "controller_plan",
        "reverse_ordering",
        "sort_values",
        "preferred_occurrence",
        "mutation_seed",
        "fault_class",
        "oracle_id",
    )
    if any(value in encoded for value in prohibited):
        raise ValueError("v2 author-visible context exposes restricted mutation truth")
    return visible


def _canonical_protocol_hash(protocol: Mapping[str, Any]) -> str:
    value = deepcopy(dict(protocol))
    value["integrity"].pop("content_hash")
    for item in value["normative_artifacts"]:
        item.pop("sha256")
    for name in ("contract_arm_isolation", "contract_launch_policy"):
        value["namespace_registry"]["contracts"][name].pop("sha256")
    return _digest(value)


def _environment_identity() -> dict[str, Any]:
    try:
        etiq_version = importlib.metadata.version("etiq-copilot")
    except importlib.metadata.PackageNotFoundError:
        etiq_version = None
    details = {
        "interpreter": str(Path(sys.executable).absolute()),
        "python_version": sys.version,
        "platform": sys.platform,
        "etiq_copilot_version": etiq_version,
    }
    details["environment_sha256"] = _digest(details)
    return details


def n02_code_identity(repo_root: Path) -> dict[str, Any]:
    relative_roots = (
        "src",
        "tests",
        "prompts/v2",
        "schemas/v2",
        "docs/workshops/neurips-2026-v2",
        "docs/experiments/2026-workshop-fault-localisation-v2",
        "pyproject.toml",
        "requirements-etiq.txt",
    )
    listed = subprocess.run(
        [
            "git",
            "ls-files",
            "-co",
            "--exclude-standard",
            "--",
            *relative_roots,
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    files = {
        (repo_root / relative).resolve()
        for relative in listed
        if (repo_root / relative).is_file()
    }
    manifest = [
        {
            "path": path.relative_to(repo_root.resolve()).as_posix(),
            "sha256": _sha256_file(path),
        }
        for path in sorted(files)
    ]
    return {
        "manifest_version": "n02-post-implementation-v1",
        "file_count": len(manifest),
        "files": manifest,
        "code_and_dirty_tree_sha256": _digest(manifest),
    }


def _predecessor_hashes(repo_root: Path) -> dict[str, str]:
    root = repo_root / "outputs/fault-experiments/preflight"
    hashes: dict[str, str] = {}
    for preflight_id, expected in PREDECESSOR_TREES.items():
        target = (root / preflight_id).resolve()
        if not target.is_dir() or target.is_symlink():
            raise ValueError(f"preserved predecessor is absent: {preflight_id}")
        actual = _sha256_tree(target, repo_root)
        if actual != expected:
            raise ValueError(f"preserved predecessor tree changed: {preflight_id}")
        hashes[preflight_id] = actual
    return hashes


def validate_n02_lifecycle_state(repo_root: Path, output_root: Path) -> dict[str, Any]:
    """Accept absence before execution or only the exact immutable N02 terminal tree."""
    validate_v2_output_root(repo_root, output_root)
    if not output_root.exists():
        return {"state": "before_execution", "output_created": False}
    if not output_root.is_dir() or output_root.is_symlink():
        raise ValueError("v2 output root is not a regular directory")
    if _sha256_tree(output_root, repo_root) != N02_TERMINAL_OUTPUT_TREE_SHA256:
        raise ValueError("present v2 output root is not the exact N02 terminal tree")

    consumption_path = output_root / N02_CONSUMPTION_NAME
    marker_path = output_root / N02_MARKER_NAME
    terminal_path = output_root / N02_PREFLIGHT_ID / "phase-a-incomplete.json"
    if (
        _sha256_file(consumption_path) != N02_CONSUMPTION_SHA256
        or _sha256_file(terminal_path) != N02_TERMINAL_FILE_SHA256
    ):
        raise ValueError("N02 consumption or terminal file hash mismatch")
    consumption = json.loads(consumption_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    internal = str(terminal.pop("terminal_record_sha256", ""))
    terminal_binding = terminal.get("n02_terminal_binding", {})
    expected_terminal_binding = {
        **dict(marker.get("n02_binding", {})),
        "consumption_record_sha256": N02_CONSUMPTION_SHA256,
        "setup_id": N02_SETUP_ID,
        "preflight_id": N02_PREFLIGHT_ID,
    }
    if (
        _sha256_file(repo_root / N02_DECISION_RELATIVE_PATH) != N02_DECISION_SHA256
        or
        marker.get("status") != "experiment_incomplete"
        or marker.get("preflight_id") != N02_PREFLIGHT_ID
        or marker.get("setup_id") != N02_SETUP_ID
        or marker.get("consumption_record_sha256") != N02_CONSUMPTION_SHA256
        or marker.get("terminal_record_sha256") != N02_TERMINAL_INTERNAL_SHA256
        or consumption.get("n02_binding") != marker.get("n02_binding")
        or terminal_binding != expected_terminal_binding
        or internal != N02_TERMINAL_INTERNAL_SHA256
        or _digest(terminal) != N02_TERMINAL_INTERNAL_SHA256
        or marker.get("n02_binding", {}).get("decision_sha256")
        != N02_DECISION_SHA256
        or list(output_root.rglob("phase-a-fixture.json"))
    ):
        raise ValueError("N02 decision, consumption, terminal, or fixture binding mismatch")
    predecessor_hashes = _predecessor_hashes(repo_root)
    if marker["n02_binding"].get("predecessor_tree_sha256") != predecessor_hashes:
        raise ValueError("N02 predecessor binding mismatch")
    return {
        "state": "n02_terminal_experiment_incomplete",
        "output_created": True,
        "output_tree_sha256": N02_TERMINAL_OUTPUT_TREE_SHA256,
        "predecessor_tree_sha256": predecessor_hashes,
    }


def n02_authorization_bindings(repo_root: Path, output_root: Path) -> dict[str, Any]:
    validate_v2_output_root(repo_root, output_root)
    authority = validate_v2_controller_path(
        repo_root,
        N02_DECISION_RELATIVE_PATH,
        operation="read",
        additional_authorities={
            N02_DECISION_RELATIVE_PATH: "sha256:" + N02_DECISION_SHA256
        },
    )
    decision = json.loads(authority.read_text(encoding="utf-8"))
    protocol = decision.get("protocol", {})
    authorization = decision.get("authorization", {})
    if (
        decision.get("decision_id")
        != "N02-v2-fault-blind-phase-a-execution-2026-08-28"
        or decision.get("decision_type")
        != "one_use_unscored_v2_phase_a_execution_authorization"
        or decision.get("issued_by") != "Overseer"
        or protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("protocol_version") != PROTOCOL_VERSION
        or protocol.get("canonical_content_hash") != PROTOCOL_HASH
        or protocol.get("exact_json_sha256")
        != "sha256:4d342609b2bc73b4fe0a7339845e15b35577ff15b81f1bed0e6705037793e51b"
        or protocol.get("exact_markdown_sha256")
        != "sha256:a80138899b68b70ce88f72c930f9460417497bf3700ce09eb5a56ee33ecb0456"
        or protocol.get("protocol_change") is not False
        or authorization.get("candidate_sets") != 1
        or authorization.get("maximum_candidates") != 3
        or authorization.get("maximum_stabilization_cycles_per_candidate") != 3
        or authorization.get("reviewer_model_calls") != 0
        or authorization.get("authoring_seed") != 26082841
        or authorization.get("mutation_seed") != 26082897
        or authorization.get("model") != "gpt-5.5"
        or authorization.get("reasoning_effort") != "high"
        or authorization.get("output_root") != "outputs/fault-experiments-v2/"
        or authorization.get("consume_atomically_before_first_authoring_call")
        is not True
    ):
        raise ValueError("N02 decision fields do not authorize this execution")

    acceptance = decision.get("acceptance_basis", {})
    if (
        acceptance.get("final_developer_handoff_sha256")
        != "sha256:" + N01B_DEVELOPER_HANDOFF_SHA256
        or acceptance.get("independent_tester_handoff_sha256")
        != "sha256:" + N01B_TESTER_HANDOFF_SHA256
        or acceptance.get("independent_tester_disposition") != "accept"
        or acceptance.get("environment_identity")
        != "sha256:27329d79912eebae5fd9fd418e33c62eecc9e30f74ac34398a6c1968d033b5d6"
        or set(acceptance.get("n01b_findings", {}).values()) != {"closed"}
    ):
        raise ValueError("N02 acceptance basis is not the accepted N01B state")
    for relative, expected in (
        (N01B_DEVELOPER_HANDOFF, N01B_DEVELOPER_HANDOFF_SHA256),
        (N01B_TESTER_HANDOFF, N01B_TESTER_HANDOFF_SHA256),
    ):
        path = repo_root / relative
        if _sha256_file(path) != expected:
            raise ValueError("accepted N01B handoff hash mismatch")

    protocol_json = repo_root / "docs/workshops/neurips-2026-v2/experiment-protocol.json"
    protocol_markdown = repo_root / "docs/workshops/neurips-2026-v2/EXPERIMENT_PROTOCOL.md"
    loaded_protocol = json.loads(protocol_json.read_text(encoding="utf-8"))
    if (
        _sha256_file(protocol_json)
        != protocol["exact_json_sha256"].removeprefix("sha256:")
        or _sha256_file(protocol_markdown)
        != protocol["exact_markdown_sha256"].removeprefix("sha256:")
        or _canonical_protocol_hash(loaded_protocol) != PROTOCOL_HASH
    ):
        raise ValueError("v2 protocol identity mismatch")

    expected_inputs = dict(decision.get("authorized_inputs", {}))
    actual_inputs = {
        name: "sha256:" + _sha256_file(repo_root / relative)
        for name, relative in AUTHORIZED_INPUT_PATHS.items()
    }
    if actual_inputs != expected_inputs:
        raise ValueError("N02 authorized input hash mismatch")

    decision_trees = {
        item["preflight_id"]: str(item["tree_sha256"]).removeprefix("sha256:")
        for item in decision.get("preservation", {}).get(
            "predecessor_preflight_trees", []
        )
    }
    if decision_trees != PREDECESSOR_TREES:
        raise ValueError("N02 predecessor preservation fields mismatch")
    predecessor_hashes = _predecessor_hashes(repo_root)
    environment = _environment_identity()
    if (
        environment["environment_sha256"] != acceptance["environment_identity"]
        or environment["etiq_copilot_version"] != "2.3.0"
        or Path(sys.executable).resolve() != (repo_root / ".venv/bin/python").resolve()
    ):
        raise ValueError("N02 pinned environment identity mismatch")
    return {
        "decision_path": N02_DECISION_RELATIVE_PATH.as_posix(),
        "decision_sha256": N02_DECISION_SHA256,
        "protocol": {
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "protocol_content_hash": PROTOCOL_HASH,
            "exact_json_sha256": protocol["exact_json_sha256"],
            "exact_markdown_sha256": protocol["exact_markdown_sha256"],
        },
        "accepted_handoffs": {
            "developer_sha256": N01B_DEVELOPER_HANDOFF_SHA256,
            "tester_sha256": N01B_TESTER_HANDOFF_SHA256,
        },
        "authorized_inputs": actual_inputs,
        "predecessor_tree_sha256": predecessor_hashes,
        "code_identity": n02_code_identity(repo_root),
        "environment_identity": environment,
        "model_settings": {
            "model": "gpt-5.5",
            "reasoning_effort": "high",
            "decoding": {
                "temperature": 0.2,
                "top_p": 1.0,
                "max_output_tokens": 16384,
                "supported_parameters": ["reasoning_effort"],
                "unsupported_omitted_parameters": [
                    "temperature",
                    "top_p",
                    "max_output_tokens",
                ],
            },
        },
    }


def _binding_summary(bindings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_sha256": bindings["decision_sha256"],
        "protocol": bindings["protocol"],
        "accepted_handoffs": bindings["accepted_handoffs"],
        "authorized_inputs": bindings["authorized_inputs"],
        "predecessor_tree_sha256": bindings["predecessor_tree_sha256"],
        "code_and_dirty_tree_sha256": bindings["code_identity"][
            "code_and_dirty_tree_sha256"
        ],
        "environment_sha256": bindings["environment_identity"]["environment_sha256"],
        "model_settings": bindings["model_settings"],
    }


def write_n02_environment_gate(
    *,
    repo_root: Path,
    output_root: Path,
    focused_tests: int,
    real_etiq_tests: int,
    complete_tests: int,
) -> Path:
    strict_provider_schemas = validate_v2_model_response_schemas(repo_root)
    bindings = n02_authorization_bindings(repo_root, output_root)
    if min(focused_tests, real_etiq_tests, complete_tests) <= 0:
        raise ValueError("N02 environment gate requires all three passing suites")
    codex_path = shutil.which("codex")
    if codex_path is None:
        raise ValueError("N02 environment gate requires the authenticated Codex CLI")
    catalog_result = subprocess.run(
        [codex_path, "debug", "models"],
        check=True,
        capture_output=True,
        text=True,
    )
    catalog = json.loads(catalog_result.stdout)
    model = next(
        (item for item in catalog.get("models", []) if item.get("slug") == "gpt-5.5"),
        None,
    )
    reasoning_levels = sorted(
        str(item.get("effort")) for item in (model or {}).get("supported_reasoning_levels", [])
    )
    if model is None or "high" not in reasoning_levels:
        raise ValueError("N02 requires available gpt-5.5 with high reasoning effort")
    cli_version = subprocess.run(
        [codex_path, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    path = validate_v2_controller_path(
        repo_root, output_root / N02_ENVIRONMENT_GATE_NAME, operation="write"
    )
    gate = {
        "schema_version": "1",
        **_binding_summary(bindings),
        "implementation_manifest": bindings["code_identity"],
        "environment_identity": bindings["environment_identity"],
        "strict_provider_schemas": strict_provider_schemas,
        "model_availability": {
            "codex_path": str(Path(codex_path).resolve()),
            "codex_version": cli_version,
            "model": "gpt-5.5",
            "available": True,
            "supported_reasoning_efforts": reasoning_levels,
            "required_reasoning_effort": "high",
            "optional_decoding_parameters_unsupported_and_omitted": [
                "temperature",
                "top_p",
                "max_output_tokens",
            ],
        },
        "tests": {
            "focused_n02_and_v2": {
                "tests_run": int(focused_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "real_etiq_contracts": {
                "tests_run": int(real_etiq_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "complete_discovery": {
                "tests_run": int(complete_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
        },
        "status": "passed_before_n02_consumption",
    }
    _write_json(path, gate)
    return path


def validate_n02_environment_gate(
    output_root: Path, bindings: Mapping[str, Any]
) -> dict[str, Any]:
    path = output_root / N02_ENVIRONMENT_GATE_NAME
    if not path.is_file():
        raise ValueError("N02 environment gate is absent")
    gate = json.loads(path.read_text(encoding="utf-8"))
    expected = _binding_summary(bindings)
    strict_provider_schemas = validate_v2_model_response_schemas(output_root.parents[1])
    tests = gate.get("tests", {})
    if (
        any(gate.get(key) != value for key, value in expected.items())
        or gate.get("implementation_manifest") != bindings["code_identity"]
        or gate.get("environment_identity") != bindings["environment_identity"]
        or gate.get("strict_provider_schemas") != strict_provider_schemas
        or gate.get("model_availability", {}).get("model") != "gpt-5.5"
        or gate.get("model_availability", {}).get("available") is not True
        or gate.get("model_availability", {}).get("required_reasoning_effort") != "high"
        or "high"
        not in gate.get("model_availability", {}).get("supported_reasoning_efforts", [])
        or gate.get("model_availability", {}).get(
            "optional_decoding_parameters_unsupported_and_omitted"
        )
        != ["temperature", "top_p", "max_output_tokens"]
        or gate.get("status") != "passed_before_n02_consumption"
        or set(tests)
        != {"focused_n02_and_v2", "real_etiq_contracts", "complete_discovery"}
        or any(
            int(item.get("tests_run", 0)) <= 0
            or any(int(item.get(name, -1)) != 0 for name in ("failures", "errors", "skips"))
            for item in tests.values()
        )
    ):
        raise ValueError("N02 environment gate does not match current execution")
    return gate


def n03_state_root(repo_root: Path, output_root: Path) -> Path:
    validate_v2_output_root(repo_root, output_root)
    return output_root / N03_STATE_DIR


def validate_n03_model_context_refs(
    refs: Iterable[str], *, repo_root: Path | None = None
) -> None:
    values = list(refs)
    validate_v2_model_context_refs(values, repo_root=repo_root)
    forbidden = (
        "outputs/fault-experiments-v2/n03",
        "n02-authorization-consumption.json",
        "n02-phase-a-attempt.json",
        "n02-phase-a-history.jsonl",
        N02_PREFLIGHT_ID,
    )
    if any(
        marker in str(ref).replace("\\", "/").casefold()
        for ref in values
        for marker in forbidden
    ):
        raise ValueError("N02/N03 control state is forbidden in N03 model context")


def n03_n02_projection_sha256(repo_root: Path, output_root: Path) -> str:
    validate_v2_output_root(repo_root, output_root)
    if not output_root.is_dir() or output_root.is_symlink():
        raise ValueError("N03 requires the exact regular N02 output root")
    state_root = n03_state_root(repo_root, output_root)
    if state_root.exists() and (not state_root.is_dir() or state_root.is_symlink()):
        raise ValueError("N03 state root must be a regular directory")
    entries = bytearray()
    files = sorted(
        path
        for path in output_root.rglob("*")
        if path.is_file()
        and path.relative_to(output_root).parts[0]
        not in {N03_STATE_DIR, N04_STATE_DIR}
    )
    for path in files:
        entries.extend(
            f"{_sha256_file(path)}  {path.relative_to(repo_root).as_posix()}\n".encode(
                "utf-8"
            )
        )
    return hashlib.sha256(entries).hexdigest()


def validate_n03_n02_projection(repo_root: Path, output_root: Path) -> str:
    projection = n03_n02_projection_sha256(repo_root, output_root)
    if projection != N02_TERMINAL_OUTPUT_TREE_SHA256:
        raise ValueError("N03 N02 baseline projection changed")
    state_root = n03_state_root(repo_root, output_root)
    if not state_root.exists() and _sha256_tree(output_root, repo_root) != projection:
        raise ValueError("N03 pre-write output tree is not the exact N02 baseline")
    return projection


def n03_code_identity(repo_root: Path) -> dict[str, Any]:
    identity = n02_code_identity(repo_root)
    return {**identity, "manifest_version": "n03-post-implementation-v1"}


def n03_authorization_bindings(repo_root: Path, output_root: Path) -> dict[str, Any]:
    projection = validate_n03_n02_projection(repo_root, output_root)
    authority = validate_v2_controller_path(
        repo_root,
        N03_DECISION_RELATIVE_PATH,
        operation="read",
        additional_authorities={
            N03_DECISION_RELATIVE_PATH: "sha256:" + N03_DECISION_SHA256
        },
    )
    decision = json.loads(authority.read_text(encoding="utf-8"))
    protocol = decision.get("protocol", {})
    authorization = decision.get("authorization", {})
    if (
        decision.get("decision_id")
        != "N03-v2-fault-blind-phase-a-execution-2026-08-28"
        or decision.get("decision_type")
        != "one_use_unscored_v2_phase_a_reexecution_authorization"
        or decision.get("issued_by") != "Overseer"
        or protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("protocol_version") != PROTOCOL_VERSION
        or protocol.get("canonical_content_hash") != PROTOCOL_HASH
        or protocol.get("exact_json_sha256")
        != "sha256:554ec7d5525f7c94036a33c6ad2e5a2ab0f3067530c531be7e6ee28da9bb2dfa"
        or protocol.get("exact_markdown_sha256")
        != "sha256:1a95ec1bc8f156a19c49d8f012d01886e8c5ef72268eaad5f0e3cfd15b39e8d8"
        or protocol.get("exact_patch_sha256")
        != "sha256:9f79ce36988d4808b33868c2ab4501735a90029b2f0b9d0304eeb38fa5623cb5"
        or protocol.get("protocol_change_authorized") is not False
        or authorization.get("authorized") is not True
        or authorization.get("candidate_sets") != 1
        or authorization.get("maximum_candidates") != 3
        or authorization.get("maximum_stabilization_cycles_per_candidate") != 3
        or authorization.get("provider_attempts_per_logical_request") != 3
        or authorization.get("reviewer_model_calls") != 0
        or authorization.get("authoring_seed") != 26082841
        or authorization.get("mutation_seed") != 26082897
        or authorization.get("model") != "gpt-5.5"
        or authorization.get("reasoning_effort") != "high"
        or authorization.get("protocol_output_root")
        != "outputs/fault-experiments-v2/"
        or authorization.get("n03_state_root")
        != "outputs/fault-experiments-v2/n03/"
        or authorization.get("consume_atomically_before_first_authoring_call")
        is not True
    ):
        raise ValueError("N03 decision fields do not authorize this execution")

    acceptance = decision.get("acceptance_basis", {})
    expected_handoffs = (
        (
            N02B_DEVELOPER_OVERSEER_HANDOFF,
            N02B_DEVELOPER_OVERSEER_HANDOFF_SHA256,
            "developer_overseer_handoff_sha256",
        ),
        (
            N02B_DEVELOPER_TESTER_HANDOFF,
            N02B_DEVELOPER_TESTER_HANDOFF_SHA256,
            "developer_tester_handoff_sha256",
        ),
        (
            N02B_TESTER_HANDOFF,
            N02B_TESTER_HANDOFF_SHA256,
            "independent_tester_handoff_sha256",
        ),
    )
    if (
        acceptance.get("n02b_decision_sha256")
        != "sha256:72590f0752e1254d7cf154fa8329786fac6a802549cc173b51f664885050db81"
        or acceptance.get("independent_tester_disposition") != "accept"
        or acceptance.get("accepted_code_and_design_identity")
        != "sha256:559802333cf0760aafc0440b2aa0baf571eee9020db3080af54c5f478fb304f5"
        or acceptance.get("environment_identity")
        != "sha256:27329d79912eebae5fd9fd418e33c62eecc9e30f74ac34398a6c1968d033b5d6"
        or set(acceptance.get("n02b_findings", {}).values()) != {"closed"}
        or any(
            acceptance.get(field) != "sha256:" + expected
            or _sha256_file(repo_root / relative) != expected
            for relative, expected, field in expected_handoffs
        )
    ):
        raise ValueError("N03 acceptance basis is not the accepted N02B state")

    protocol_json = repo_root / "docs/workshops/neurips-2026-v2/experiment-protocol.json"
    protocol_markdown = repo_root / "docs/workshops/neurips-2026-v2/EXPERIMENT_PROTOCOL.md"
    protocol_patch = repo_root / "docs/workshops/neurips-2026-v2/protocol-1.3.1-to-2.0.3.patch"
    loaded_protocol = json.loads(protocol_json.read_text(encoding="utf-8"))
    if (
        _sha256_file(protocol_json)
        != protocol["exact_json_sha256"].removeprefix("sha256:")
        or _sha256_file(protocol_markdown)
        != protocol["exact_markdown_sha256"].removeprefix("sha256:")
        or _sha256_file(protocol_patch)
        != protocol["exact_patch_sha256"].removeprefix("sha256:")
        or _canonical_protocol_hash(loaded_protocol) != PROTOCOL_HASH
    ):
        raise ValueError("N03 protocol identity mismatch")

    actual_inputs = {
        name: "sha256:" + _sha256_file(repo_root / relative)
        for name, relative in AUTHORIZED_INPUT_PATHS.items()
    }
    if actual_inputs != decision.get("authorized_inputs"):
        raise ValueError("N03 authorized input hash mismatch")
    preservation = decision.get("preservation", {})
    expected_predecessors = {
        key: "sha256:" + value for key, value in PREDECESSOR_TREES.items()
    }
    if (
        preservation.get("n02_namespace_rule") is None
        or preservation.get("protocol_2_0_2_archive_tree_sha256")
        != "sha256:8c71da9fe1f8af60b4ce604b9fe9ba97978ec20e9ddbb012d07c59f69342c83b"
        or preservation.get("predecessor_tree_sha256") != expected_predecessors
        or decision.get("n02_disposition", {}).get(
            "n02_output_tree_sha256_before_n03"
        )
        != "sha256:" + projection
    ):
        raise ValueError("N03 preservation bindings are invalid")
    archive = repo_root / "docs/workshops/neurips-2026-v2/archive/excluded-2.0.2-n02"
    if _sha256_tree(archive, repo_root) != "8c71da9fe1f8af60b4ce604b9fe9ba97978ec20e9ddbb012d07c59f69342c83b":
        raise ValueError("N03 protocol 2.0.2 archive changed")
    predecessors = _predecessor_hashes(repo_root)
    environment = _environment_identity()
    if (
        environment["environment_sha256"] != acceptance["environment_identity"]
        or environment["etiq_copilot_version"] != "2.3.0"
        or Path(sys.executable).resolve() != (repo_root / ".venv/bin/python").resolve()
    ):
        raise ValueError("N03 pinned environment identity mismatch")
    return {
        "decision_path": N03_DECISION_RELATIVE_PATH.as_posix(),
        "decision_sha256": N03_DECISION_SHA256,
        "protocol": {
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "protocol_content_hash": PROTOCOL_HASH,
            "exact_json_sha256": protocol["exact_json_sha256"],
            "exact_markdown_sha256": protocol["exact_markdown_sha256"],
            "exact_patch_sha256": protocol["exact_patch_sha256"],
        },
        "accepted_handoffs": {
            "developer_overseer_sha256": N02B_DEVELOPER_OVERSEER_HANDOFF_SHA256,
            "developer_tester_sha256": N02B_DEVELOPER_TESTER_HANDOFF_SHA256,
            "tester_sha256": N02B_TESTER_HANDOFF_SHA256,
        },
        "authorized_inputs": actual_inputs,
        "n02_projection_sha256": projection,
        "archive_tree_sha256": _sha256_tree(archive, repo_root),
        "predecessor_tree_sha256": predecessors,
        "code_identity": n03_code_identity(repo_root),
        "environment_identity": environment,
        "model_settings": {
            "model": "gpt-5.5",
            "reasoning_effort": "high",
            "unsupported_omitted_parameters": [
                "temperature",
                "top_p",
                "max_output_tokens",
            ],
        },
    }


def _n03_binding_summary(bindings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_sha256": bindings["decision_sha256"],
        "protocol": bindings["protocol"],
        "accepted_handoffs": bindings["accepted_handoffs"],
        "authorized_inputs": bindings["authorized_inputs"],
        "n02_projection_sha256": bindings["n02_projection_sha256"],
        "archive_tree_sha256": bindings["archive_tree_sha256"],
        "predecessor_tree_sha256": bindings["predecessor_tree_sha256"],
        "code_and_dirty_tree_sha256": bindings["code_identity"][
            "code_and_dirty_tree_sha256"
        ],
        "environment_sha256": bindings["environment_identity"][
            "environment_sha256"
        ],
        "model_settings": bindings["model_settings"],
    }


def write_n03_environment_gate(
    *,
    repo_root: Path,
    output_root: Path,
    focused_tests: int,
    all_v2_tests: int,
    real_etiq_tests: int,
    complete_tests: int,
) -> Path:
    validate_n03_n02_projection(repo_root, output_root)
    state_root = n03_state_root(repo_root, output_root)
    if state_root.exists():
        raise ValueError("N03 state already exists before environment gate")
    bindings = n03_authorization_bindings(repo_root, output_root)
    strict_provider_schemas = validate_v2_model_response_schemas(repo_root)
    if min(focused_tests, all_v2_tests, real_etiq_tests, complete_tests) <= 0:
        raise ValueError("N03 environment gate requires every passing suite")
    codex_path = shutil.which("codex")
    if codex_path is None:
        raise ValueError("N03 environment gate requires the authenticated Codex CLI")
    catalog = json.loads(
        subprocess.run(
            [codex_path, "debug", "models"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    model = next(
        (item for item in catalog.get("models", []) if item.get("slug") == "gpt-5.5"),
        None,
    )
    reasoning_levels = sorted(
        str(item.get("effort"))
        for item in (model or {}).get("supported_reasoning_levels", [])
    )
    if model is None or "high" not in reasoning_levels:
        raise ValueError("N03 requires available gpt-5.5 with high reasoning effort")
    cli_version = subprocess.run(
        [codex_path, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    gate = {
        "schema_version": "1",
        **_n03_binding_summary(bindings),
        "implementation_manifest": bindings["code_identity"],
        "environment_identity": bindings["environment_identity"],
        "strict_provider_schemas": strict_provider_schemas,
        "model_availability": {
            "codex_path": str(Path(codex_path).resolve()),
            "codex_version": cli_version,
            "model": "gpt-5.5",
            "available": True,
            "supported_reasoning_efforts": reasoning_levels,
            "required_reasoning_effort": "high",
            "optional_decoding_parameters_unsupported_and_omitted": [
                "temperature",
                "top_p",
                "max_output_tokens",
            ],
        },
        "tests": {
            "focused_n03_n02b_n02a_n02": {
                "tests_run": int(focused_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "all_v2": {
                "tests_run": int(all_v2_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "real_etiq_contracts": {
                "tests_run": int(real_etiq_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "complete_discovery": {
                "tests_run": int(complete_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
        },
        "status": "passed_before_n03_consumption",
    }
    path = state_root / N03_ENVIRONMENT_GATE_NAME
    _write_json(path, gate)
    validate_n03_n02_projection(repo_root, output_root)
    return path


def validate_n03_environment_gate(
    repo_root: Path, output_root: Path, bindings: Mapping[str, Any]
) -> dict[str, Any]:
    validate_n03_n02_projection(repo_root, output_root)
    path = n03_state_root(repo_root, output_root) / N03_ENVIRONMENT_GATE_NAME
    if not path.is_file() or path.is_symlink():
        raise ValueError("N03 environment gate is absent")
    gate = json.loads(path.read_text(encoding="utf-8"))
    tests = gate.get("tests", {})
    if (
        any(
            gate.get(key) != value
            for key, value in _n03_binding_summary(bindings).items()
        )
        or gate.get("implementation_manifest") != bindings["code_identity"]
        or gate.get("environment_identity") != bindings["environment_identity"]
        or gate.get("strict_provider_schemas")
        != validate_v2_model_response_schemas(repo_root)
        or gate.get("model_availability", {}).get("model") != "gpt-5.5"
        or gate.get("model_availability", {}).get("available") is not True
        or gate.get("model_availability", {}).get("required_reasoning_effort")
        != "high"
        or "high"
        not in gate.get("model_availability", {}).get(
            "supported_reasoning_efforts", []
        )
        or gate.get("status") != "passed_before_n03_consumption"
        or set(tests)
        != {
            "focused_n03_n02b_n02a_n02",
            "all_v2",
            "real_etiq_contracts",
            "complete_discovery",
        }
        or any(
            int(item.get("tests_run", 0)) <= 0
            or any(
                int(item.get(name, -1)) != 0
                for name in ("failures", "errors", "skips")
            )
            for item in tests.values()
        )
    ):
        raise ValueError("N03 environment gate does not match current execution")
    return gate


def validate_n03_lifecycle_state(
    repo_root: Path, output_root: Path
) -> dict[str, Any]:
    projection = validate_n03_n02_projection(repo_root, output_root)
    state_root = n03_state_root(repo_root, output_root)
    if not state_root.exists():
        return {"state": "before_environment_gate", "n02_projection_sha256": projection}
    for path in state_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("N03 state contains a forbidden symbolic link")
    gate_path = state_root / N03_ENVIRONMENT_GATE_NAME
    consumption_path = state_root / N03_CONSUMPTION_NAME
    marker_path = state_root / N03_MARKER_NAME
    if not gate_path.is_file():
        raise ValueError("N03 state exists without its environment gate")
    if consumption_path.exists() != marker_path.exists():
        raise ValueError("N03 has orphaned consumption or marker state")
    if not consumption_path.exists():
        allowed = {N03_ENVIRONMENT_GATE_NAME}
        if {path.name for path in state_root.iterdir()} != allowed:
            raise ValueError("N03 pre-consumption state contains unexpected files")
        return {"state": "ready_to_consume", "n02_projection_sha256": projection}

    consumption = json.loads(consumption_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    consumption_hash = _sha256_file(consumption_path)
    if (
        consumption.get("status") != "consumed_in_progress"
        or consumption.get("candidate_sets_consumed") != 1
        or consumption.get("maximum_candidates") != 3
        or consumption.get("maximum_stabilization_cycles_per_candidate") != 3
        or consumption.get("reviewer_model_calls_authorized") != 0
        or consumption.get("n03_binding") != marker.get("n03_binding")
        or marker.get("consumption_record_sha256") != consumption_hash
        or marker.get("preflight_id") != consumption.get("preflight_id")
        or marker.get("setup_id") != consumption.get("setup_id")
        or marker.get("n03_binding", {}).get("decision_sha256")
        != N03_DECISION_SHA256
    ):
        raise ValueError("N03 consumption or marker binding is invalid")
    status = str(marker.get("status") or "")
    terminal_statuses = {
        "phase_a_passed",
        "experiment_incomplete",
        "frozen_input_failure",
        "provider_infrastructure_failure",
        "provider_failure_unknown_inference_status",
    }
    return {
        "state": "terminal" if status in terminal_statuses else "in_progress",
        "status": status,
        "preflight_id": str(consumption["preflight_id"]),
        "setup_id": str(consumption["setup_id"]),
        "consumption": consumption,
        "marker": marker,
        "consumption_sha256": consumption_hash,
        "n02_projection_sha256": projection,
    }


def _validate_n03_resume_before_first_call(
    state_root: Path, lifecycle: Mapping[str, Any]
) -> None:
    if lifecycle.get("state") != "in_progress" or lifecycle.get("status") != "consumed_in_progress":
        raise RuntimeError("N03 state is not safely resumable")
    preflight_id = str(lifecycle["preflight_id"])
    setup_id = str(lifecycle["setup_id"])
    root = state_root / preflight_id
    invocation_root = root / "restricted/setup-store" / setup_id / "invocations"
    if invocation_root.exists() and any(invocation_root.iterdir()):
        raise RuntimeError(
            "N03 interrupted after a provider attempt; automatic resume fails closed"
        )
    forbidden = list(root.glob("phase-a-*.json")) + list(
        (root / "restricted").glob("reference-freeze-*.json")
    )
    if forbidden or lifecycle.get("marker", {}).get("last_rejected_candidate"):
        raise RuntimeError("N03 interrupted state is beyond the safe resume point")


def n04_state_root(repo_root: Path, output_root: Path) -> Path:
    validate_v2_output_root(repo_root, output_root)
    return output_root / N04_STATE_DIR


def validate_n04_model_context_refs(
    refs: Iterable[str], *, repo_root: Path | None = None
) -> None:
    values = list(refs)
    validate_v2_model_context_refs(values, repo_root=repo_root)
    forbidden = (
        "outputs/fault-experiments-v2/n03",
        "outputs/fault-experiments-v2/n04",
        "n02-authorization-consumption.json",
        "n02-phase-a-attempt.json",
        "n02-phase-a-history.jsonl",
        N02_PREFLIGHT_ID,
        "preflight-428e78ad00374ab3",
    )
    if any(
        marker in str(ref).replace("\\", "/").casefold()
        for ref in values
        for marker in forbidden
    ):
        raise ValueError("N02/N03/N04 control state is forbidden in N04 model context")


def n04_pre_execution_projection_sha256(
    repo_root: Path, output_root: Path
) -> str:
    validate_v2_output_root(repo_root, output_root)
    if not output_root.is_dir() or output_root.is_symlink():
        raise ValueError("N04 requires the exact regular post-N03 output root")
    state_root = n04_state_root(repo_root, output_root)
    if state_root.exists() and (not state_root.is_dir() or state_root.is_symlink()):
        raise ValueError("N04 state root must be a regular directory")
    entries = bytearray()
    files = sorted(
        path
        for path in output_root.rglob("*")
        if path.is_file()
        and path.relative_to(output_root).parts[0] != N04_STATE_DIR
    )
    for path in files:
        entries.extend(
            f"{_sha256_file(path)}  {path.relative_to(repo_root).as_posix()}\n".encode(
                "utf-8"
            )
        )
    return hashlib.sha256(entries).hexdigest()


def validate_n04_preservation(repo_root: Path, output_root: Path) -> dict[str, str]:
    projection = n04_pre_execution_projection_sha256(repo_root, output_root)
    if projection != N04_PRE_EXECUTION_OUTPUT_TREE_SHA256:
        raise ValueError("N04 pre-execution output projection changed")
    n02_projection = n03_n02_projection_sha256(repo_root, output_root)
    if n02_projection != N02_TERMINAL_OUTPUT_TREE_SHA256:
        raise ValueError("N04 N02 projection changed")
    n03_root = output_root / N03_STATE_DIR
    if (
        not n03_root.is_dir()
        or n03_root.is_symlink()
        or _sha256_tree(n03_root, repo_root) != N04_N03_TREE_SHA256
    ):
        raise ValueError("N04 N03 tree changed")
    state_root = n04_state_root(repo_root, output_root)
    if not state_root.exists() and _sha256_tree(output_root, repo_root) != projection:
        raise ValueError("N04 pre-write output tree is not the exact post-N03 baseline")
    return {
        "pre_n04_projection_sha256": projection,
        "n02_projection_sha256": n02_projection,
        "n03_tree_sha256": N04_N03_TREE_SHA256,
    }


def n04_code_identity(repo_root: Path) -> dict[str, Any]:
    identity = n02_code_identity(repo_root)
    return {**identity, "manifest_version": "n04-post-remediation-v1"}


def n04_authorization_bindings(repo_root: Path, output_root: Path) -> dict[str, Any]:
    preservation = validate_n04_preservation(repo_root, output_root)
    authority = validate_v2_controller_path(
        repo_root,
        N04_DECISION_RELATIVE_PATH,
        operation="read",
        additional_authorities={
            N04_DECISION_RELATIVE_PATH: "sha256:" + N04_DECISION_SHA256
        },
    )
    decision = json.loads(authority.read_text(encoding="utf-8"))
    protocol = decision.get("protocol", {})
    execution = decision.get("conditional_execution_authorization", {})
    if (
        decision.get("decision_id")
        != "N04-v2-boundary-qualname-remediation-and-phase-a-execution-2026-08-28"
        or decision.get("decision_type")
        != "conditional_code_remediation_and_one_use_unscored_v2_phase_a_execution_authorization"
        or decision.get("issued_by") != "Overseer"
        or protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("protocol_version") != PROTOCOL_VERSION
        or protocol.get("canonical_content_hash") != PROTOCOL_HASH
        or protocol.get("exact_json_sha256")
        != "sha256:554ec7d5525f7c94036a33c6ad2e5a2ab0f3067530c531be7e6ee28da9bb2dfa"
        or protocol.get("exact_markdown_sha256")
        != "sha256:1a95ec1bc8f156a19c49d8f012d01886e8c5ef72268eaad5f0e3cfd15b39e8d8"
        or protocol.get("exact_patch_sha256")
        != "sha256:9f79ce36988d4808b33868c2ab4501735a90029b2f0b9d0304eeb38fa5623cb5"
        or protocol.get("protocol_change_authorized") is not False
        or execution.get("candidate_sets") != 1
        or execution.get("maximum_candidates") != 3
        or execution.get("maximum_stabilization_cycles_per_candidate") != 3
        or execution.get("provider_attempts_per_logical_request") != 3
        or execution.get("reviewer_model_calls") != 0
        or execution.get("authoring_seed") != 26082841
        or execution.get("mutation_seed") != 26082897
        or execution.get("model") != "gpt-5.5"
        or execution.get("reasoning_effort") != "high"
        or execution.get("protocol_output_root")
        != "outputs/fault-experiments-v2/"
        or execution.get("n04_state_root")
        != "outputs/fault-experiments-v2/n04/"
        or execution.get("consume_atomically_before_first_authoring_call")
        is not True
    ):
        raise ValueError("N04 decision fields do not authorize this execution")

    disposition = decision.get("n03_disposition", {})
    handoffs = (
        (
            N03_DEVELOPER_OVERSEER_HANDOFF,
            N03_DEVELOPER_OVERSEER_HANDOFF_SHA256,
            "developer_terminal_handoff_sha256",
        ),
        (
            N03_DEVELOPER_TESTER_HANDOFF,
            N03_DEVELOPER_TESTER_HANDOFF_SHA256,
            "developer_tester_handoff_sha256",
        ),
        (
            N03_DEVELOPER_PAPER_HANDOFF,
            N03_DEVELOPER_PAPER_HANDOFF_SHA256,
            "developer_paper_writer_handoff_sha256",
        ),
        (
            N03_TESTER_HANDOFF,
            N03_TESTER_HANDOFF_SHA256,
            "independent_tester_handoff_sha256",
        ),
    )
    if (
        disposition.get("independent_tester_disposition") != "reject"
        or disposition.get("terminal_status")
        != "experiment_incomplete_excluded_engineering_contract_evidence"
        or disposition.get("scientific_candidate_exhaustion_accepted") is not False
        or disposition.get("phase_a_fixture_accepted") is not False
        or disposition.get("reviewer_calls") != 0
        or set(disposition.get("findings", {})) != {"N04-F01", "N04-F02"}
        or any(
            disposition.get(field) != "sha256:" + expected
            or _sha256_file(repo_root / relative) != expected
            for relative, expected, field in handoffs
        )
    ):
        raise ValueError("N04 N03 disposition or handoff binding mismatch")

    baseline = decision.get("accepted_baseline", {})
    n03_terminal = (
        output_root
        / N03_STATE_DIR
        / "preflight-428e78ad00374ab3/phase-a-incomplete.json"
    )
    n03_consumption = output_root / N03_STATE_DIR / N03_CONSUMPTION_NAME
    n03_marker = json.loads(
        (output_root / N03_STATE_DIR / N03_MARKER_NAME).read_text(encoding="utf-8")
    )
    if (
        baseline.get("n03_decision_sha256") != "sha256:" + N03_DECISION_SHA256
        or baseline.get("pre_n04_whole_v2_output_tree_sha256")
        != "sha256:" + preservation["pre_n04_projection_sha256"]
        or baseline.get("n02_projection_sha256")
        != "sha256:" + preservation["n02_projection_sha256"]
        or baseline.get("n03_tree_sha256")
        != "sha256:" + preservation["n03_tree_sha256"]
        or baseline.get("n03_terminal_file_sha256")
        != "sha256:" + _sha256_file(n03_terminal)
        or baseline.get("n03_terminal_semantic_sha256")
        != json.loads(n03_terminal.read_text(encoding="utf-8")).get(
            "terminal_record_sha256"
        )
        or baseline.get("n03_consumption_sha256")
        != "sha256:" + _sha256_file(n03_consumption)
        or baseline.get("pre_remediation_code_and_design_identity")
        != "sha256:26edb342ec92079ee08703bf438b1802c727bf445a67e7ad207c7d95b6439dfe"
        or baseline.get("environment_identity")
        != "sha256:27329d79912eebae5fd9fd418e33c62eecc9e30f74ac34398a6c1968d033b5d6"
    ):
        raise ValueError("N04 accepted post-N03 baseline mismatch")

    protocol_json = repo_root / "docs/workshops/neurips-2026-v2/experiment-protocol.json"
    protocol_markdown = repo_root / "docs/workshops/neurips-2026-v2/EXPERIMENT_PROTOCOL.md"
    protocol_patch = repo_root / "docs/workshops/neurips-2026-v2/protocol-1.3.1-to-2.0.3.patch"
    loaded_protocol = json.loads(protocol_json.read_text(encoding="utf-8"))
    if (
        _sha256_file(protocol_json)
        != protocol["exact_json_sha256"].removeprefix("sha256:")
        or _sha256_file(protocol_markdown)
        != protocol["exact_markdown_sha256"].removeprefix("sha256:")
        or _sha256_file(protocol_patch)
        != protocol["exact_patch_sha256"].removeprefix("sha256:")
        or _canonical_protocol_hash(loaded_protocol) != PROTOCOL_HASH
    ):
        raise ValueError("N04 protocol identity mismatch")

    actual_inputs = {
        name: "sha256:" + _sha256_file(repo_root / relative)
        for name, relative in AUTHORIZED_INPUT_PATHS.items()
    }
    if actual_inputs != n03_marker.get("n03_binding", {}).get("authorized_inputs"):
        raise ValueError("N04 governed input hash mismatch")
    preservation_fields = decision.get("preservation", {})
    expected_predecessors = {
        key: "sha256:" + value for key, value in PREDECESSOR_TREES.items()
    }
    archive = repo_root / "docs/workshops/neurips-2026-v2/archive/excluded-2.0.2-n02"
    if (
        preservation_fields.get("protocol_2_0_2_archive_tree_sha256")
        != "sha256:8c71da9fe1f8af60b4ce604b9fe9ba97978ec20e9ddbb012d07c59f69342c83b"
        or preservation_fields.get("predecessor_tree_sha256")
        != expected_predecessors
        or _sha256_tree(archive, repo_root)
        != "8c71da9fe1f8af60b4ce604b9fe9ba97978ec20e9ddbb012d07c59f69342c83b"
    ):
        raise ValueError("N04 preservation binding mismatch")
    predecessors = _predecessor_hashes(repo_root)
    environment = _environment_identity()
    if (
        environment["environment_sha256"] != baseline["environment_identity"]
        or environment["etiq_copilot_version"] != "2.3.0"
        or Path(sys.executable).resolve() != (repo_root / ".venv/bin/python").resolve()
    ):
        raise ValueError("N04 pinned environment identity mismatch")
    return {
        "decision_path": N04_DECISION_RELATIVE_PATH.as_posix(),
        "decision_sha256": N04_DECISION_SHA256,
        "protocol": {
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "protocol_content_hash": PROTOCOL_HASH,
            "exact_json_sha256": protocol["exact_json_sha256"],
            "exact_markdown_sha256": protocol["exact_markdown_sha256"],
            "exact_patch_sha256": protocol["exact_patch_sha256"],
        },
        "accepted_handoffs": {
            "developer_overseer_sha256": N03_DEVELOPER_OVERSEER_HANDOFF_SHA256,
            "developer_tester_sha256": N03_DEVELOPER_TESTER_HANDOFF_SHA256,
            "developer_paper_writer_sha256": N03_DEVELOPER_PAPER_HANDOFF_SHA256,
            "tester_sha256": N03_TESTER_HANDOFF_SHA256,
        },
        "authorized_inputs": actual_inputs,
        **preservation,
        "archive_tree_sha256": _sha256_tree(archive, repo_root),
        "predecessor_tree_sha256": predecessors,
        "canonicalization_audit": {
            "rule": "remove only exact <locals> qualified-name components",
            "authoritative_identity": "exact job/path/AST lexical qualname/source hash",
            "duplicate_normalized_identities": "rejected",
            "shared_authoring_and_stabilization_parser": "generated_pipeline_from_v2_payload",
        },
        "code_identity": n04_code_identity(repo_root),
        "environment_identity": environment,
        "model_settings": {
            "model": "gpt-5.5",
            "reasoning_effort": "high",
            "unsupported_omitted_parameters": [
                "temperature",
                "top_p",
                "max_output_tokens",
            ],
        },
    }


def _n04_binding_summary(bindings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_sha256": bindings["decision_sha256"],
        "protocol": bindings["protocol"],
        "accepted_handoffs": bindings["accepted_handoffs"],
        "authorized_inputs": bindings["authorized_inputs"],
        "pre_n04_projection_sha256": bindings["pre_n04_projection_sha256"],
        "n02_projection_sha256": bindings["n02_projection_sha256"],
        "n03_tree_sha256": bindings["n03_tree_sha256"],
        "archive_tree_sha256": bindings["archive_tree_sha256"],
        "predecessor_tree_sha256": bindings["predecessor_tree_sha256"],
        "canonicalization_audit": bindings["canonicalization_audit"],
        "code_and_dirty_tree_sha256": bindings["code_identity"][
            "code_and_dirty_tree_sha256"
        ],
        "environment_sha256": bindings["environment_identity"][
            "environment_sha256"
        ],
        "model_settings": bindings["model_settings"],
    }


def write_n04_environment_gate(
    *,
    repo_root: Path,
    output_root: Path,
    focused_tests: int,
    all_v2_tests: int,
    real_etiq_tests: int,
    complete_tests: int,
) -> Path:
    validate_n04_preservation(repo_root, output_root)
    state_root = n04_state_root(repo_root, output_root)
    if state_root.exists():
        raise ValueError("N04 state already exists before environment gate")
    bindings = n04_authorization_bindings(repo_root, output_root)
    strict_provider_schemas = validate_v2_model_response_schemas(repo_root)
    if min(focused_tests, all_v2_tests, real_etiq_tests, complete_tests) <= 0:
        raise ValueError("N04 environment gate requires every passing suite")
    codex_path = shutil.which("codex")
    if codex_path is None:
        raise ValueError("N04 environment gate requires the authenticated Codex CLI")
    catalog = json.loads(
        subprocess.run(
            [codex_path, "debug", "models"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    model = next(
        (item for item in catalog.get("models", []) if item.get("slug") == "gpt-5.5"),
        None,
    )
    reasoning_levels = sorted(
        str(item.get("effort"))
        for item in (model or {}).get("supported_reasoning_levels", [])
    )
    if model is None or "high" not in reasoning_levels:
        raise ValueError("N04 requires available gpt-5.5 with high reasoning effort")
    cli_version = subprocess.run(
        [codex_path, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    gate = {
        "schema_version": "1",
        **_n04_binding_summary(bindings),
        "implementation_manifest": bindings["code_identity"],
        "environment_identity": bindings["environment_identity"],
        "strict_provider_schemas": strict_provider_schemas,
        "model_availability": {
            "codex_path": str(Path(codex_path).resolve()),
            "codex_version": cli_version,
            "model": "gpt-5.5",
            "available": True,
            "supported_reasoning_efforts": reasoning_levels,
            "required_reasoning_effort": "high",
            "optional_decoding_parameters_unsupported_and_omitted": [
                "temperature",
                "top_p",
                "max_output_tokens",
            ],
        },
        "tests": {
            "focused_n04_n03_n02b_n02a_n02": {
                "tests_run": int(focused_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "all_v2": {
                "tests_run": int(all_v2_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "real_etiq_contracts": {
                "tests_run": int(real_etiq_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
            "complete_discovery": {
                "tests_run": int(complete_tests),
                "failures": 0,
                "errors": 0,
                "skips": 0,
            },
        },
        "status": "passed_before_n04_consumption",
    }
    path = state_root / N04_ENVIRONMENT_GATE_NAME
    _write_json(path, gate)
    validate_n04_preservation(repo_root, output_root)
    return path


def validate_n04_environment_gate(
    repo_root: Path, output_root: Path, bindings: Mapping[str, Any]
) -> dict[str, Any]:
    validate_n04_preservation(repo_root, output_root)
    path = n04_state_root(repo_root, output_root) / N04_ENVIRONMENT_GATE_NAME
    if not path.is_file() or path.is_symlink():
        raise ValueError("N04 environment gate is absent")
    gate = json.loads(path.read_text(encoding="utf-8"))
    tests = gate.get("tests", {})
    if (
        any(gate.get(key) != value for key, value in _n04_binding_summary(bindings).items())
        or gate.get("implementation_manifest") != bindings["code_identity"]
        or gate.get("environment_identity") != bindings["environment_identity"]
        or gate.get("strict_provider_schemas")
        != validate_v2_model_response_schemas(repo_root)
        or gate.get("model_availability", {}).get("model") != "gpt-5.5"
        or gate.get("model_availability", {}).get("available") is not True
        or gate.get("model_availability", {}).get("required_reasoning_effort")
        != "high"
        or "high"
        not in gate.get("model_availability", {}).get(
            "supported_reasoning_efforts", []
        )
        or gate.get("status") != "passed_before_n04_consumption"
        or set(tests)
        != {
            "focused_n04_n03_n02b_n02a_n02",
            "all_v2",
            "real_etiq_contracts",
            "complete_discovery",
        }
        or any(
            int(item.get("tests_run", 0)) <= 0
            or any(
                int(item.get(name, -1)) != 0
                for name in ("failures", "errors", "skips")
            )
            for item in tests.values()
        )
    ):
        raise ValueError("N04 environment gate does not match current execution")
    return gate


def validate_n04_lifecycle_state(
    repo_root: Path, output_root: Path
) -> dict[str, Any]:
    preservation = validate_n04_preservation(repo_root, output_root)
    state_root = n04_state_root(repo_root, output_root)
    if not state_root.exists():
        return {"state": "before_environment_gate", **preservation}
    for path in state_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("N04 state contains a forbidden symbolic link")
    gate_path = state_root / N04_ENVIRONMENT_GATE_NAME
    consumption_path = state_root / N04_CONSUMPTION_NAME
    marker_path = state_root / N04_MARKER_NAME
    if not gate_path.is_file():
        raise ValueError("N04 state exists without its environment gate")
    if consumption_path.exists() != marker_path.exists():
        raise ValueError("N04 has orphaned consumption or marker state")
    if not consumption_path.exists():
        if {path.name for path in state_root.iterdir()} != {N04_ENVIRONMENT_GATE_NAME}:
            raise ValueError("N04 pre-consumption state contains unexpected files")
        return {"state": "ready_to_consume", **preservation}
    consumption = json.loads(consumption_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    consumption_hash = _sha256_file(consumption_path)
    if (
        consumption.get("status") != "consumed_in_progress"
        or consumption.get("candidate_sets_consumed") != 1
        or consumption.get("maximum_candidates") != 3
        or consumption.get("maximum_stabilization_cycles_per_candidate") != 3
        or consumption.get("reviewer_model_calls_authorized") != 0
        or consumption.get("n04_binding") != marker.get("n04_binding")
        or marker.get("consumption_record_sha256") != consumption_hash
        or marker.get("preflight_id") != consumption.get("preflight_id")
        or marker.get("setup_id") != consumption.get("setup_id")
        or marker.get("n04_binding", {}).get("decision_sha256")
        != N04_DECISION_SHA256
    ):
        raise ValueError("N04 consumption or marker binding is invalid")
    status = str(marker.get("status") or "")
    terminal_statuses = {
        "phase_a_passed",
        "experiment_incomplete",
        "frozen_input_failure",
        "provider_infrastructure_failure",
        "provider_failure_unknown_inference_status",
    }
    return {
        "state": "terminal" if status in terminal_statuses else "in_progress",
        "status": status,
        "preflight_id": str(consumption["preflight_id"]),
        "setup_id": str(consumption["setup_id"]),
        "consumption": consumption,
        "marker": marker,
        "consumption_sha256": consumption_hash,
        **preservation,
    }


def _validate_n04_resume_before_first_call(
    state_root: Path, lifecycle: Mapping[str, Any]
) -> None:
    if (
        lifecycle.get("state") != "in_progress"
        or lifecycle.get("status") != "consumed_in_progress"
    ):
        raise RuntimeError("N04 state is not safely resumable")
    preflight_id = str(lifecycle["preflight_id"])
    setup_id = str(lifecycle["setup_id"])
    root = state_root / preflight_id
    invocation_root = root / "restricted/setup-store" / setup_id / "invocations"
    if invocation_root.exists() and any(invocation_root.iterdir()):
        raise RuntimeError(
            "N04 interrupted after a provider attempt; automatic resume fails closed"
        )
    forbidden = list(root.glob("phase-a-*.json")) + list(
        (root / "restricted").glob("reference-freeze-*.json")
    )
    if forbidden or lifecycle.get("marker", {}).get("last_rejected_candidate"):
        raise RuntimeError("N04 interrupted state is beyond the safe resume point")


def _persist_setup_record(
    restricted: Path,
    kind: str,
    setup_id: str,
    payload: Mapping[str, Any],
    binding: Mapping[str, Any],
    usage: Mapping[str, Any] | None = None,
    binding_key: str | None = None,
) -> Path:
    normalized_kind = kind.casefold().replace("-", "_")
    if normalized_kind not in SETUP_RECORD_KINDS:
        raise ValueError("unknown v2 setup record kind")
    if binding_key is None:
        decision_sha256 = binding.get("decision_sha256")
        if decision_sha256 == N04_DECISION_SHA256:
            binding_key = "n04_binding"
        elif decision_sha256 == N03_DECISION_SHA256:
            binding_key = "n03_binding"
        else:
            binding_key = "n02_binding"
    record = {
        "schema_version": "1",
        "protocol_content_hash": PROTOCOL_HASH,
        "storage_classification": "restricted_controller_only",
        "record_kind": normalized_kind,
        "setup_id": setup_id,
        "job_ids": list(V2_PREFLIGHT_JOB_IDS),
        "payload": {**dict(payload), binding_key: dict(binding)},
        "setup_usage": dict(usage or {}),
        "excluded_from_experimental_treatment_usage": True,
        "reviewer_visibility": "forbidden",
    }
    record["record_sha256"] = _digest(record)
    restricted.mkdir(parents=True, exist_ok=True)
    path = restricted / f"{setup_id}-{normalized_kind}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    return path


def _v2_authoring_request(
    repo_root: Path, scenario: Mapping[str, Any], candidate_number: int
) -> dict[str, Any]:
    validate_reference_attempt(candidate_number, 0)
    prompt_path = repo_root / "prompts/v2/fault_chain_authoring.md"
    schema_path = repo_root / "schemas/v2/fault_chain_authoring.schema.json"
    refs = [str(prompt_path), str(schema_path), str(repo_root / V2_FIXTURE_RELATIVE_ROOT)]
    validate_v2_model_context_refs(refs, repo_root=repo_root)
    template = prompt_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate_strict_provider_schema(schema, schema_path.relative_to(repo_root).as_posix())
    visible = author_visible_v2_scenario(scenario)
    prompt = (
        template
        + "\n\nFrozen author-visible scenario, corpus, and capabilities:\n"
        + json.dumps(visible, sort_keys=True, ensure_ascii=False)
        + f"\n\nCandidate number: {candidate_number}. Frozen authoring seed: {scenario['authoring_seed']}."
    )
    identity = _digest(
        {
            "candidate_number": candidate_number,
            "authoring_seed": scenario["authoring_seed"],
            "prompt": prompt,
            "output_schema": schema,
            "author_visible_context": visible,
        }
    )
    return {
        "template": template,
        "schema": schema,
        "visible": visible,
        "prompt": prompt,
        "request_identity": identity,
    }


def request_v2_authoring_response(
    codex: CodexRunner,
    *,
    setup_id: str,
    repo_root: Path,
    scenario: Mapping[str, Any],
    candidate_number: int,
    job_type: str = "fault_preflight_v2_authoring",
    purpose: str = "n02_phase_a_authoring",
) -> tuple[Any, str]:
    request = _v2_authoring_request(repo_root, scenario, candidate_number)
    result = codex.run(
        job_id=setup_id,
        job_type=job_type,
        purpose=purpose,
        prompt=request["prompt"],
        output_schema=request["schema"],
        artifacts=[
            _artifact(
                "prompt:v2_fault_chain_authoring",
                request["template"],
                "frozen authoring rules",
            ),
            _artifact(
                "scenario:v2_preflight",
                request["visible"],
                "frozen author-visible setup input",
            ),
        ],
        excluded=[
            {"ref": "repository-tree", "reason": "fresh-chain authoring boundary"},
            {"ref": "controller-plan", "reason": "future mutation is controller-only"},
            {"ref": "oracles", "reason": "semantic oracles are hidden"},
            {"ref": "prior-candidates", "reason": "every candidate is fresh"},
            {"ref": "authorities-and-handoffs", "reason": "model contexts exclude control state"},
            {"ref": "reviewer-information", "reason": "Phase A permits zero reviewer calls"},
        ],
    )
    return result, str(request["request_identity"])


def _parse_v2_authoring_response(
    result: Any,
) -> tuple[dict[str, GeneratedPipeline], dict[str, Any], str, dict[str, Any]]:
    jobs = {
        str(item["job_id"]): generated_pipeline_from_v2_payload(
            str(item["job_id"]), item["pipeline"]
        )
        for item in result.payload["jobs"]
    }
    if tuple(jobs) != V2_PREFLIGHT_JOB_IDS:
        raise ValueError("v2 authoring response changed the exact ordered jobs")
    return (
        jobs,
        dict(result.payload["complexity_claims"]),
        result.invocation_id,
        jsonable(result.usage),
    )


def author_v2_candidate(
    codex: CodexRunner,
    *,
    setup_id: str,
    repo_root: Path,
    scenario: Mapping[str, Any],
    candidate_number: int,
) -> tuple[dict[str, GeneratedPipeline], dict[str, Any], str, dict[str, Any]]:
    result, _request_identity = request_v2_authoring_response(
        codex,
        setup_id=setup_id,
        repo_root=repo_root,
        scenario=scenario,
        candidate_number=candidate_number,
    )
    return _parse_v2_authoring_response(result)


def _oracle_report_v2(
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


def execute_v2_two_job_chain(
    etiq: EtiqExecutor,
    *,
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    run_label: str,
    network_cassette_path: Path | None = None,
) -> dict[str, Any]:
    if tuple(jobs) != V2_PREFLIGHT_JOB_IDS:
        raise ValueError("v2 execution requires its exact ordered two jobs")
    for job_id in V2_PREFLIGHT_JOB_IDS:
        try:
            for item in jobs[job_id].files:
                compile(item.content, item.path, "exec")
        except (SyntaxError, ValueError) as exc:
            raise RuntimeError(
                "v2 candidate compilation/import validation failed",
                {
                    "failure_kind": "compile_import",
                    "failing_job_id": job_id,
                    "stderr": str(exc),
                },
            ) from exc
    upstream_id, downstream_id = V2_PREFLIGHT_JOB_IDS
    try:
        offline = (
            {
                "network_mode": "replay",
                "network_cassette_path": network_cassette_path,
            }
            if network_cassette_path is not None
            else {}
        )
        upstream_execution = etiq.execute(
            job_id=upstream_id,
            segment_id="phase-a-v2",
            stage=f"{run_label}-upstream",
            run_id=new_id("run"),
            pipeline=jobs[upstream_id],
            runtime_input={"corpus": scenario["corpus"]},
            **offline,
        )
        if not upstream_execution.reviewable:
            raise ValueError("Etiq produced no reviewable v2 upstream capture")
        upstream_output = _parse_result(upstream_execution)
        upstream_execution.snapshot = enrich_snapshot_identities_v2(
            upstream_execution.snapshot,
            jobs[upstream_id].review_boundaries,
            job_id=upstream_id,
            pipeline=jobs[upstream_id],
        )
    except Exception as exc:
        raise RuntimeError(
            "v2 upstream runtime validation failed",
            {
                "failure_kind": "runtime",
                "failing_job_id": upstream_id,
                "stderr": str(exc),
                "partial_capture": (
                    jsonable(upstream_execution.snapshot)
                    if "upstream_execution" in locals()
                    else None
                ),
            },
        ) from exc
    downstream_input = {
        "needs": upstream_output.get("needs"),
        "evidence_sources": upstream_output.get("evidence_sources"),
        "capabilities": scenario["capabilities"],
    }
    handoffs = []
    for artifact_name in ("needs", "evidence_sources"):
        digest = _digest(upstream_output.get(artifact_name))
        if _digest(downstream_input[artifact_name]) != digest:
            raise ValueError("v2 downstream handoff changed before execution")
        handoffs.append(
            {
                "handoff_ref": f"v2-handoff-{artifact_name.replace('_', '-')}",
                "upstream_job_id": upstream_id,
                "downstream_job_id": downstream_id,
                "artifact_name": artifact_name,
                "artifact_sha256": digest,
                "provenance_type": "controller_recorded_exact_hash_handoff",
                "etiq_runtime_edge": False,
            }
        )
    try:
        downstream_execution = etiq.execute(
            job_id=downstream_id,
            segment_id="phase-a-v2",
            stage=f"{run_label}-downstream",
            run_id=new_id("run"),
            pipeline=jobs[downstream_id],
            runtime_input=downstream_input,
            **offline,
        )
        if not downstream_execution.reviewable:
            raise ValueError("Etiq produced no reviewable v2 downstream capture")
        downstream_output = _parse_result(downstream_execution)
        downstream_execution.snapshot = enrich_snapshot_identities_v2(
            downstream_execution.snapshot,
            jobs[downstream_id].review_boundaries,
            job_id=downstream_id,
            pipeline=jobs[downstream_id],
        )
    except Exception as exc:
        raise RuntimeError(
            "v2 downstream runtime validation failed",
            {
                "failure_kind": "runtime",
                "failing_job_id": downstream_id,
                "stderr": str(exc),
                "partial_capture": (
                    jsonable(downstream_execution.snapshot)
                    if "downstream_execution" in locals()
                    else None
                ),
            },
        ) from exc
    return {
        "executions": {
            upstream_id: upstream_execution,
            downstream_id: downstream_execution,
        },
        "outputs": {upstream_id: upstream_output, downstream_id: downstream_output},
        "handoffs": handoffs,
        "oracle": _oracle_report_v2(
            upstream_output, downstream_output, scenario["oracles"]
        ),
    }


def _has_join_or_aggregation(pipeline: GeneratedPipeline) -> bool:
    source = "\n".join(item.content.casefold() for item in pipeline.files)
    return any(
        marker in source
        for marker in (".merge(", ".join(", ".groupby(", "aggregate", "coverage")
    )


def complexity_report_v2(
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    realized_by_job: dict[str, list[dict[str, Any]]] = {}
    helper_audit_by_job: dict[str, list[dict[str, Any]]] = {}
    full_bytes = 0
    selected_bytes = 0
    for job_id in V2_PREFLIGHT_JOB_IDS:
        snapshot = execution["executions"][job_id].snapshot
        realized = materialize_realized_boundaries_v2(
            snapshot,
            jobs[job_id].review_boundaries,
            job_id=job_id,
            pipeline=jobs[job_id],
        )
        realized_by_job[job_id] = realized
        full_bytes += len(_encode(snapshot))
        fixed = [grouped_boundary_selection_v2(snapshot, boundary) for boundary in realized]
        selected_bytes += len(_encode(fixed))
        audit: list[dict[str, Any]] = []
        for boundary in realized:
            base = grouped_boundary_selection_v2(snapshot, boundary)
            base_nodes = set(base["node_refs"])
            base_relationships = set(base["relationship_refs"])
            parents = {tuple(value) for value in boundary["matched_prefixes"]}
            for prefix_value in boundary["helper_prefixes"]:
                prefix = tuple(prefix_value)
                if prefix[:-1] not in parents:
                    continue
                expanded = grouped_boundary_selection_v2(
                    snapshot, boundary, expanded_prefixes=[prefix]
                )
                added_nodes = sorted(set(expanded["node_refs"]) - base_nodes)
                added_relationships = sorted(
                    set(expanded["relationship_refs"]) - base_relationships
                )
                expanded_bytes = len(_encode(expanded))
                audit.append(
                    {
                        "boundary_id": boundary["boundary_id"],
                        "func_stack": list(prefix),
                        "added_node_refs": added_nodes,
                        "added_relationship_refs": added_relationships,
                        "expanded_selection_bytes": expanded_bytes,
                        "eligible": bool(added_nodes)
                        and bool(added_relationships)
                        and expanded_bytes <= MAX_PACKAGE_BYTES,
                    }
                )
        helper_audit_by_job[job_id] = audit
    eligible = [
        {**item, "job_id": job_id}
        for job_id, values in helper_audit_by_job.items()
        for item in values
        if item["eligible"]
    ]
    boundary_count = sum(len(values) for values in realized_by_job.values())
    ratio = selected_bytes / full_bytes if full_bytes else 1.0
    checks = {
        "exactly_two_jobs": tuple(jobs) == V2_PREFLIGHT_JOB_IDS,
        "declared_boundaries_minimum": boundary_count
        >= int(scenario["authoring_requirements"]["declared_boundaries_minimum"]),
        "two_exact_handoffs": len(execution["handoffs"]) == 2,
        "join_or_aggregation": _has_join_or_aggregation(jobs[V2_PREFLIGHT_JOB_IDS[1]]),
        "two_operationally_expandable_helpers": len(eligible)
        >= int(
            scenario["authoring_requirements"][
                "directly_executed_nested_helpers_minimum"
            ]
        ),
        "selected_materially_smaller": selected_bytes < full_bytes and ratio <= 0.8,
        "full_graph_fits": full_bytes <= int(scenario["limits"]["max_package_bytes"]),
        "stage_and_end_to_end_oracles": execution["oracle"]["passed"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failed_check_names": sorted(name for name, passed in checks.items() if not passed),
        "declared_boundary_count": boundary_count,
        "full_graph_bytes": full_bytes,
        "selected_graph_bytes": selected_bytes,
        "selected_to_full_ratio": ratio,
        "operationally_expandable_helpers": eligible,
        "helper_eligibility_audit_by_job": helper_audit_by_job,
        "realized_boundaries": realized_by_job,
        "author_claims_consulted": False,
    }


def _v2_stabilization_request(
    repo_root: Path,
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    candidate_number: int,
    cycle: int,
    failure: Mapping[str, Any],
    model_settings: Mapping[str, Any],
) -> dict[str, Any]:
    validate_reference_attempt(candidate_number, cycle)
    failing_job_id = str(failure["failing_job_id"])
    required_keys = (
        ["needs", "evidence_sources", "metadata"]
        if failing_job_id == V2_PREFLIGHT_JOB_IDS[0]
        else ["coverage", "priorities", "recommendation", "metadata"]
    )
    evidence = build_stabilization_evidence(
        failure_kind=str(failure["failure_kind"]),
        failing_job_id=failing_job_id,
        source=jsonable(jobs[failing_job_id].files),
        command=["etiq", "scan_code", jobs[failing_job_id].entry_file],
        exit_status=1,
        stdout=str(failure.get("stdout") or ""),
        stderr=str(failure.get("stderr") or ""),
        expected_interface={
            "entry_file": jobs[failing_job_id].entry_file,
            "review_boundaries": jobs[failing_job_id].review_boundaries,
            "required_output_keys": required_keys,
        },
        frozen_schema_and_criteria={
            "scenario_id": scenario["scenario_id"],
            "failed_checks": list(failure.get("failed_checks", [])),
            "compact_diagnostics": dict(failure.get("compact_diagnostics", {})),
            "graph_evidence": "forbidden_for_validation_failure",
        }
        if failure["failure_kind"] == "validation"
        else {"scenario_id": scenario["scenario_id"], "expected_interface_only": True},
        partial_capture=failure.get("partial_capture"),
    )
    prompt_path = repo_root / "prompts/v2/fault_chain_stabilization.md"
    schema_path = repo_root / "schemas/v2/fault_chain_stabilization.schema.json"
    validate_v2_model_context_refs(
        [str(prompt_path), str(schema_path)], repo_root=repo_root
    )
    template = prompt_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate_strict_provider_schema(schema, schema_path.relative_to(repo_root).as_posix())
    prompt = (
        template
        + "\n\nFrozen failure-specific stabilization evidence:\n"
        + json.dumps(evidence, sort_keys=True, ensure_ascii=False)
    )
    identity = _digest(
        {
            "prompt": prompt,
            "output_schema": schema,
            "failure_evidence": evidence,
            "candidate_number": candidate_number,
            "cycle": cycle,
            "model_settings": dict(model_settings),
        }
    )
    return {
        "failing_job_id": failing_job_id,
        "evidence": evidence,
        "template": template,
        "schema": schema,
        "prompt": prompt,
        "request_identity": identity,
    }


def request_v2_stabilization_response(
    codex: CodexRunner,
    *,
    setup_id: str,
    repo_root: Path,
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    candidate_number: int,
    cycle: int,
    failure: Mapping[str, Any],
    model_settings: Mapping[str, Any],
    job_type: str = "fault_preflight_v2_stabilization",
    purpose: str = "n02_phase_a_stabilization",
) -> tuple[Any, str]:
    request = _v2_stabilization_request(
        repo_root,
        scenario,
        jobs,
        candidate_number,
        cycle,
        failure,
        model_settings,
    )
    result = codex.run(
        job_id=setup_id,
        job_type=job_type,
        purpose=purpose,
        prompt=request["prompt"],
        output_schema=request["schema"],
        artifacts=[
            _artifact(
                "prompt:v2_fault_chain_stabilization",
                request["template"],
                "frozen stabilization rules",
            ),
            _artifact(
                "evidence:v2_stabilization",
                request["evidence"],
                "failing-job-only evidence",
            ),
        ],
        excluded=[
            {"ref": "other-job-source", "reason": "only the failing job may change"},
            {"ref": "controller-plan-and-oracles", "reason": "stabilization is fault blind"},
            {"ref": "prior-candidates", "reason": "candidate isolation"},
            {"ref": "authorities-and-handoffs", "reason": "control state is never model-visible"},
            {"ref": "reviewer-information", "reason": "Phase A permits zero reviewer calls"},
        ],
    )
    return result, str(request["request_identity"])


def _parse_v2_stabilization_response(
    result: Any,
    *,
    jobs: Mapping[str, GeneratedPipeline],
    failing_job_id: str,
) -> tuple[dict[str, GeneratedPipeline], str, dict[str, Any]]:
    response_job_id = str(result.payload.get("job_id") or result.payload.get("failing_job_id") or "")
    if response_job_id != failing_job_id:
        raise ValueError("v2 stabilization response changed the failing job identity")
    replacements = dict(jobs)
    replacements[failing_job_id] = generated_pipeline_from_v2_payload(
        failing_job_id, result.payload["pipeline"]
    )
    validate_stabilization_replacement(
        jobs, replacements, failing_job_id=failing_job_id
    )
    return replacements, result.invocation_id, jsonable(result.usage)


def _mutation_proof(
    execution: Mapping[str, Any], *, job_id: str, site: Mapping[str, Any]
) -> dict[str, Any]:
    snapshot = execution["executions"][job_id].snapshot
    function_name = str(site["qualified_function_name"]).split(".")[-1]
    line = int(site["line"])
    nodes = [
        node.node_ref
        for node in snapshot.nodes
        if function_name in {frame_name(str(value)) for value in node.func_stack}
        and (node.line_no is None or line <= int(node.line_no) <= line + 1)
    ]
    return {
        "mutated_statement_executed": bool(nodes),
        "captured_node_refs": sorted(nodes),
        "line": line,
        "qualified_function_name": site["qualified_function_name"],
    }


def inject_v2_mutant(
    *,
    repo_root: Path,
    etiq: EtiqExecutor,
    scenario: Mapping[str, Any],
    jobs: Mapping[str, GeneratedPipeline],
    reference_execution: Mapping[str, Any],
    run_label: str,
    network_cassette_path: Path | None = None,
) -> dict[str, Any]:
    plan_path = validate_v2_controller_path(
        repo_root,
        repo_root / V2_FIXTURE_RELATIVE_ROOT / "restricted/controller-plan.json",
        operation="read",
    )
    if _sha256_file(plan_path) != AUTHORIZED_INPUT_HASHES["restricted_controller_plan_sha256"]:
        raise ValueError("restricted controller plan changed after reference freeze")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    job_id = str(plan["job_id"])
    target = next(
        (
            dict(boundary)
            for boundary in jobs[job_id].review_boundaries
            if boundary["source_path"] == plan["source_path"]
            and boundary["qualified_function_name"] == plan["qualified_function_name"]
        ),
        None,
    )
    if target is None:
        raise ValueError("v2 mutation target is unavailable in accepted reference")
    target_identity = {
        "job_id": job_id,
        "source_path": target["source_path"],
        "qualified_function_name": target["qualified_function_name"],
        "function_source_sha256": target["function_source_sha256"],
    }
    clean = deepcopy(jobs[job_id])
    clean_bytes = _encode(clean)
    schedule = freeze_reverse_ordering_order_v2(
        clean,
        target_identity=target_identity,
        seed=int(plan["mutation_seed"]),
        preferred_occurrence=int(plan["preferred_occurrence"]),
    )
    rejections: list[dict[str, Any]] = []
    for attempt_number, scheduled in enumerate(schedule["frozen_candidates"], 1):
        occurrence = int(scheduled["occurrence"])
        try:
            injected = inject_reverse_ordering_v2(
                clean, target_identity=target_identity, occurrence=occurrence
            )
            mutant_pipeline = generated_pipeline_from_v2_payload(
                job_id, jsonable(injected["pipeline"])
            )
            mutant_jobs = dict(jobs)
            mutant_jobs[job_id] = mutant_pipeline
            execution = execute_v2_two_job_chain(
                etiq,
                scenario=scenario,
                jobs=mutant_jobs,
                run_label=f"{run_label}-{attempt_number:02d}",
                network_cassette_path=network_cassette_path,
            )
            proof = _mutation_proof(execution, job_id=job_id, site=injected["site"])
            downstream = execution["outputs"][V2_PREFLIGHT_JOB_IDS[1]]
            flags = {
                "compile_success": True,
                "execution_success": True,
                "schema_valid": set(downstream)
                == set(scenario["oracles"]["downstream"]["required_output_fields"]),
                "mutated_statement_executed": proof["mutated_statement_executed"],
                "plausible_final_result": bool(downstream.get("priorities")),
                "semantic_oracle_failed": not execution["oracle"]["passed"],
            }
        except Exception as exc:
            rejections.append(
                {
                    "occurrence": occurrence,
                    "order_key": scheduled["order_key"],
                    "reason_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
            if _encode(clean) != clean_bytes:
                raise ValueError("v2 clean bundle changed after rejected mutant") from exc
            continue
        if _encode(clean) != clean_bytes or _encode(injected["clean_pipeline"]) != clean_bytes:
            raise ValueError("v2 clean bundle was not restored byte-for-byte")
        failed = sorted(name for name, passed in flags.items() if passed is not True)
        if failed:
            rejections.append(
                {
                    "occurrence": occurrence,
                    "order_key": scheduled["order_key"],
                    "failed_flags": failed,
                    "oracle_failed_check_names": execution["oracle"][
                        "failed_check_names"
                    ],
                }
            )
            continue
        return {
            "plan": plan,
            "target_identity": target_identity,
            "schedule": schedule,
            "rejections": rejections,
            "selected_occurrence": occurrence,
            "injection": injected,
            "mutant_jobs": mutant_jobs,
            "execution": execution,
            "execution_proof": proof,
            "validation": flags,
            "reference_restoration_sha256": _digest(clean_bytes),
        }
    raise ValueError(
        "v2 frozen reverse_ordering sites exhausted: "
        + json.dumps({"schedule": schedule, "rejections": rejections}, sort_keys=True)
    )


def _failure_from_exception(exc: RuntimeError) -> dict[str, Any]:
    if len(exc.args) > 1 and isinstance(exc.args[1], Mapping):
        return dict(exc.args[1])
    return {
        "failure_kind": "runtime",
        "failing_job_id": V2_PREFLIGHT_JOB_IDS[0],
        "stderr": str(exc),
    }


def _setup_usage(
    store: JobStore,
    setup_id: str,
    *,
    authoring_purpose: str = "n02_phase_a_authoring",
    stabilization_purpose: str = "n02_phase_a_stabilization",
) -> dict[str, Any]:
    records = []
    for path in sorted((store.job_dir(setup_id) / "invocations").glob("*/usage.json")):
        value = store.read_json(path)
        if isinstance(value, dict):
            records.append(value)
    totals: dict[str, int] = {}
    for record in records:
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            totals[key] = totals.get(key, 0) + int(record.get(key) or 0)
        for key, amount in record.get("extra", {}).items():
            totals[key] = totals.get(key, 0) + int(amount or 0)
    return {
        "model_call_count": len(records),
        "authoring_calls": sum(
            record.get("purpose") == authoring_purpose for record in records
        ),
        "stabilization_calls": sum(
            record.get("purpose") == stabilization_purpose for record in records
        ),
        "reviewer_calls": 0,
        "totals": totals,
        "records": records,
        "excluded_from_experimental_treatment_usage": True,
    }


def _terminal_binding(
    binding: Mapping[str, Any], consumption_hash: str, setup_id: str, preflight_id: str
) -> dict[str, Any]:
    return {
        **dict(binding),
        "consumption_record_sha256": consumption_hash,
        "setup_id": setup_id,
        "preflight_id": preflight_id,
    }


def _reference_fixture_data(
    jobs: Mapping[str, GeneratedPipeline],
    execution: Mapping[str, Any],
    complexity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "jobs": {job_id: jsonable(pipeline) for job_id, pipeline in jobs.items()},
        "normalized_bundle_sha256": {
            job_id: _digest(pipeline) for job_id, pipeline in jobs.items()
        },
        "outputs": execution["outputs"],
        "snapshots": {
            job_id: jsonable(execution["executions"][job_id].snapshot)
            for job_id in V2_PREFLIGHT_JOB_IDS
        },
        "handoffs": execution["handoffs"],
        "oracle": execution["oracle"],
        "complexity": dict(complexity),
    }


def _write_success_fixture(
    *,
    repo_root: Path,
    output_root: Path,
    root: Path,
    restricted: Path,
    marker: Mapping[str, Any],
    reference: Mapping[str, Any],
    mutation: Mapping[str, Any],
    candidate_number: int,
    stabilization_cycles: int,
    rejection_log: list[dict[str, Any]],
    usage: Mapping[str, Any],
    terminal_binding: Mapping[str, Any],
    terminal_binding_key: str = "n02_terminal_binding",
    marker_name: str = N02_MARKER_NAME,
    history_name: str = N02_HISTORY_NAME,
) -> Path:
    ground_truth = {
        "schema_version": "1",
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_HASH,
        "storage_classification": "restricted_controller_only",
        "fault_class": "reverse_ordering",
        "target_identity": mutation["target_identity"],
        "selected_occurrence": mutation["selected_occurrence"],
        "site": mutation["injection"]["site"],
        "clean_bundle_sha256": mutation["injection"]["clean_bundle_sha256"],
        "mutant_bundle_sha256": mutation["injection"]["mutant_bundle_sha256"],
        "frozen_schedule": mutation["schedule"],
        "mutation_rejections": mutation["rejections"],
        "reference_restoration_sha256": mutation[
            "reference_restoration_sha256"
        ],
        "execution_proof": mutation["execution_proof"],
        "validation": mutation["validation"],
        terminal_binding_key: dict(terminal_binding),
    }
    ground_truth["ground_truth_sha256"] = _digest(ground_truth)
    ground_truth_path = restricted / "ground-truth.json"
    _create_json_exclusive(ground_truth_path, ground_truth)
    fixture = {
        "schema_version": "1",
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_HASH,
        "status": "phase_a_passed",
        "phase": "A",
        "scored": False,
        "reviewer_model_calls": 0,
        "downstream_release": "blocked_pending_overseer_reassessment_and_T02",
        "candidate_number": int(candidate_number),
        "stabilization_cycles": int(stabilization_cycles),
        "reference": dict(reference),
        "mutant": {
            "jobs": {
                job_id: jsonable(pipeline)
                for job_id, pipeline in mutation["mutant_jobs"].items()
            },
            "normalized_bundle_sha256": {
                job_id: _digest(pipeline)
                for job_id, pipeline in mutation["mutant_jobs"].items()
            },
            "outputs": mutation["execution"]["outputs"],
            "snapshots": {
                job_id: jsonable(mutation["execution"]["executions"][job_id].snapshot)
                for job_id in V2_PREFLIGHT_JOB_IDS
            },
            "handoffs": mutation["execution"]["handoffs"],
            "oracle": mutation["execution"]["oracle"],
            "execution_proof": mutation["execution_proof"],
            "validation": mutation["validation"],
        },
        "restricted_ground_truth_ref": str(ground_truth_path.relative_to(root)),
        "restricted_ground_truth_sha256": ground_truth["ground_truth_sha256"],
        "restricted_sentinels": {
            "controller_root": str(restricted.resolve()),
            "setup_store": str((restricted / "setup-store").resolve()),
            "reviewer_visibility": "forbidden",
        },
        "setup_usage": dict(usage),
        "candidate_rejections": rejection_log,
        terminal_binding_key: dict(terminal_binding),
    }
    fixture["fixture_sha256"] = _digest(fixture)
    fixture_path = root / "phase-a-fixture.json"
    _write_json(fixture_path, fixture)
    terminal_marker = {
        **dict(marker),
        "status": "phase_a_passed",
        "outcome_ref": str(fixture_path.relative_to(repo_root)),
        "fixture_sha256": fixture["fixture_sha256"],
        "setup_usage": dict(usage),
    }
    _write_json(output_root / marker_name, terminal_marker)
    _append_jsonl(output_root / history_name, terminal_marker)
    return root


def run_phase_a_preflight_v2(
    *,
    repo_root: Path,
    output_root: Path,
    model: str = "gpt-5.5",
    timeout_seconds: int = 1800,
    codex_factory: Callable[[JobStore], CodexRunner] | None = None,
    etiq_factory: Callable[[JobStore], EtiqExecutor] | None = None,
    authority: str = "n02",
) -> Path:
    validate_v2_output_root(repo_root, output_root)
    if authority == "n02":
        state_root = output_root
        authority_label = "N02"
        environment_gate_name = N02_ENVIRONMENT_GATE_NAME
        consumption_name = N02_CONSUMPTION_NAME
        marker_name = N02_MARKER_NAME
        history_name = N02_HISTORY_NAME
        diagnostic_name = N02_DIAGNOSTIC_NAME
        binding_key = "n02_binding"
        terminal_binding_key = "n02_terminal_binding"
        authoring_job_type = "fault_preflight_v2_authoring"
        stabilization_job_type = "fault_preflight_v2_stabilization"
        authoring_purpose = "n02_phase_a_authoring"
        stabilization_purpose = "n02_phase_a_stabilization"
        bindings_loader = n02_authorization_bindings
        binding_summarizer = _binding_summary
        gate_validator = lambda values: validate_n02_environment_gate(
            output_root, values
        )
        preservation_check = lambda: None
    elif authority == "n03":
        state_root = n03_state_root(repo_root, output_root)
        authority_label = "N03"
        environment_gate_name = N03_ENVIRONMENT_GATE_NAME
        consumption_name = N03_CONSUMPTION_NAME
        marker_name = N03_MARKER_NAME
        history_name = N03_HISTORY_NAME
        diagnostic_name = N03_DIAGNOSTIC_NAME
        binding_key = "n03_binding"
        terminal_binding_key = "n03_terminal_binding"
        authoring_job_type = "fault_preflight_v2_authoring"
        stabilization_job_type = "fault_preflight_v2_stabilization"
        authoring_purpose = "v2_phase_a_authoring"
        stabilization_purpose = "v2_phase_a_stabilization"
        bindings_loader = n03_authorization_bindings
        binding_summarizer = _n03_binding_summary
        gate_validator = lambda values: validate_n03_environment_gate(
            repo_root, output_root, values
        )
        preservation_check = lambda: validate_n03_n02_projection(
            repo_root, output_root
        )
    elif authority == "n04":
        state_root = n04_state_root(repo_root, output_root)
        authority_label = "N04"
        environment_gate_name = N04_ENVIRONMENT_GATE_NAME
        consumption_name = N04_CONSUMPTION_NAME
        marker_name = N04_MARKER_NAME
        history_name = N04_HISTORY_NAME
        diagnostic_name = N04_DIAGNOSTIC_NAME
        binding_key = "n04_binding"
        terminal_binding_key = "n04_terminal_binding"
        authoring_job_type = "fault_preflight_v2_authoring"
        stabilization_job_type = "fault_preflight_v2_stabilization"
        authoring_purpose = "v2_phase_a_authoring"
        stabilization_purpose = "v2_phase_a_stabilization"
        bindings_loader = n04_authorization_bindings
        binding_summarizer = _n04_binding_summary
        gate_validator = lambda values: validate_n04_environment_gate(
            repo_root, output_root, values
        )
        preservation_check = lambda: validate_n04_preservation(
            repo_root, output_root
        )
    else:
        raise ValueError("unknown v2 Phase A authority")

    consumption_path = state_root / consumption_name
    marker_path = state_root / marker_name
    resume = False
    lifecycle: dict[str, Any] | None = None
    if authority in {"n03", "n04"}:
        lifecycle_validator = (
            validate_n03_lifecycle_state
            if authority == "n03"
            else validate_n04_lifecycle_state
        )
        resume_validator = (
            _validate_n03_resume_before_first_call
            if authority == "n03"
            else _validate_n04_resume_before_first_call
        )
        lifecycle = lifecycle_validator(repo_root, output_root)
        if lifecycle["state"] == "terminal":
            raise RuntimeError(
                f"{authority_label} authorization already {lifecycle['status']}; terminal state "
                "cannot resume and no runner may be constructed"
            )
        if lifecycle["state"] == "in_progress":
            resume_validator(state_root, lifecycle)
            resume = True
    if (marker_path.exists() or consumption_path.exists()) and not resume:
        status = "consumed"
        if marker_path.is_file():
            status = str(
                json.loads(marker_path.read_text(encoding="utf-8")).get(
                    "status", status
                )
            )
        raise RuntimeError(
            f"{authority_label} authorization already {status}; terminal state cannot resume "
            "and no runner may be constructed"
        )
    try:
        bindings = bindings_loader(repo_root, output_root)
        environment_gate = gate_validator(bindings)
        if model != "gpt-5.5":
            raise ValueError(f"{authority_label} requires exact model gpt-5.5")
        binding = binding_summarizer(bindings)
    except Exception as exc:
        if state_root.exists():
            _append_jsonl(
                state_root / diagnostic_name,
                {
                    "status": "fail_closed_before_model_call",
                    "reason_type": type(exc).__name__,
                    "reason": str(exc),
                    "authorization_consumed": consumption_path.exists(),
                    "model_runner_constructed": False,
                },
            )
        raise

    # The second preservation/input verification is deliberately immediately before
    # the exclusive consumption write and still precedes runner construction.
    bindings = bindings_loader(repo_root, output_root)
    gate_validator(bindings)
    preservation_check()
    binding = binding_summarizer(bindings)
    scenario = load_v2_preflight_scenario(repo_root, include_controller_plan=False)
    if resume:
        assert lifecycle is not None
        preflight_id = str(lifecycle["preflight_id"])
        setup_id = str(lifecycle["setup_id"])
        consumption = dict(lifecycle["consumption"])
        marker = dict(lifecycle["marker"])
        consumption_hash = str(lifecycle["consumption_sha256"])
    else:
        preflight_id = new_id("preflight")
        setup_id = new_id("setup")
        consumption = {
            "schema_version": "1",
            "status": "consumed_in_progress",
            "candidate_sets_consumed": 1,
            "maximum_candidates": 3,
            "maximum_stabilization_cycles_per_candidate": 3,
            "reviewer_model_calls_authorized": 0,
            "preflight_id": preflight_id,
            "setup_id": setup_id,
            binding_key: binding,
        }
        _create_json_exclusive(consumption_path, consumption)
        consumption_hash = _sha256_file(consumption_path)
        marker = {**consumption, "consumption_record_sha256": consumption_hash}
        _write_json(marker_path, marker)
        _append_jsonl(state_root / history_name, marker)
        preservation_check()
    root = state_root / preflight_id

    restricted = root / "restricted"
    store = JobStore(restricted / "setup-store")
    if not (store.job_dir(setup_id) / "state.json").exists():
        store.initialize_job(
            AgentRequest("unscored v2 Phase A", "workshop engineering"),
            RootJobState(job_id=setup_id, status="setup"),
        )
    offline_cassette = validate_v2_controller_path(
        repo_root,
        restricted / f"{authority}-offline-network-cassette.json",
        operation="write",
    )
    if offline_cassette.exists():
        if json.loads(offline_cassette.read_text(encoding="utf-8")) != []:
            raise ValueError(
                f"{authority_label} resume cassette is not the exact empty offline cassette"
            )
    else:
        _write_json(offline_cassette, [])
    codex = (
        codex_factory(store)
        if codex_factory
        else CodexRunner(
            store,
            model="gpt-5.5",
            reasoning_effort="high",
            timeout_seconds=timeout_seconds,
        )
    )
    etiq = (
        etiq_factory(store)
        if etiq_factory
        else EtiqExecutor(store, timeout_seconds=timeout_seconds)
    )
    terminal_binding = _terminal_binding(
        binding, consumption_hash, setup_id, preflight_id
    )
    preflight_record = restricted / "ledger/setup-phase-a-v2-preflight.json"
    if not preflight_record.exists():
        _persist_setup_record(
            restricted / "ledger",
            "preflight",
            "setup-phase-a-v2",
            {
                "phase": "A",
                "scored": False,
                "candidate_limit": 3,
                "stabilization_cycle_limit": 3,
                "reviewer_model_calls": 0,
                "environment_gate_sha256": _sha256_file(
                    state_root / environment_gate_name
                ),
                "terminal_binding": terminal_binding,
            },
            binding,
            binding_key=binding_key,
        )

    accepted: dict[str, Any] | None = None
    rejection_log: list[dict[str, Any]] = []
    request_failures: list[dict[str, Any]] = []
    request_stop_category: str | None = None
    request_stop_stage: str | None = None
    for candidate_number in range(1, 4):
        preservation_check()
        request_identity = str(
            _v2_authoring_request(repo_root, scenario, candidate_number)[
                "request_identity"
            ]
        )
        outcome = run_v2_request_with_retries(
            lambda: request_v2_authoring_response(
                codex,
                setup_id=setup_id,
                repo_root=repo_root,
                scenario=scenario,
                candidate_number=candidate_number,
                job_type=authoring_job_type,
                purpose=authoring_purpose,
            ),
            candidate_number=candidate_number,
            request_identity=request_identity,
        )
        for failure in outcome["failures"]:
            request_failures.append(failure)
            _persist_setup_record(
                restricted / "ledger",
                "authoring_request_failure",
                (
                    f"author-request-c{candidate_number:02d}-"
                    f"r{int(failure['retry_number']):02d}"
                ),
                failure,
                binding,
            )
        if outcome["response"] is None:
            request_stop_category = str(outcome["stop_category"])
            request_stop_stage = "authoring"
            break
        try:
            result, returned_identity = outcome["response"]
            if returned_identity != request_identity:
                raise ValueError("malformed controller request identity")
            jobs, claims, invocation_id, usage = _parse_v2_authoring_response(result)
            _persist_setup_record(
                restricted / "ledger",
                "authoring",
                f"author-{candidate_number:02d}",
                {
                    "candidate_number": candidate_number,
                    "request_identity": request_identity,
                    "retry_count": len(outcome["failures"]),
                    "invocation_id": invocation_id,
                    "fresh_non_resumed_session": True,
                    "fault_target_visible": False,
                    "author_visible_scenario_sha256": _digest(
                        author_visible_v2_scenario(scenario)
                    ),
                    "job_bundle_sha256": {
                        job_id: _digest(pipeline)
                        for job_id, pipeline in jobs.items()
                    },
                    "complexity_claims_recorded_not_trusted": claims,
                },
                binding,
                usage,
            )
        except Exception as exc:
            rejection = {
                "candidate_number": candidate_number,
                "cycle": 0,
                "gate": "authoring_response",
                "reason_type": type(exc).__name__,
                "reason": str(exc),
            }
            rejection_log.append(rejection)
            _persist_setup_record(
                restricted / "ledger",
                "rejected_candidate",
                f"reject-author-{candidate_number:02d}",
                rejection,
                binding,
            )
            continue

        for cycle in range(0, 4):
            preservation_check()
            validate_reference_attempt(candidate_number, cycle)
            failure: dict[str, Any] | None = None
            try:
                execution = execute_v2_two_job_chain(
                    etiq,
                    scenario=scenario,
                    jobs=jobs,
                    run_label=f"reference-c{candidate_number}-s{cycle}",
                    network_cassette_path=offline_cassette,
                )
                complexity = complexity_report_v2(scenario, jobs, execution)
                _persist_setup_record(
                    restricted / "ledger",
                    "complexity_gate",
                    f"complexity-{candidate_number:02d}-{cycle:02d}",
                    {
                        "candidate_number": candidate_number,
                        "cycle": cycle,
                        "report": complexity,
                    },
                    binding,
                )
                if execution["oracle"]["passed"] and complexity["passed"]:
                    reference = _reference_fixture_data(jobs, execution, complexity)
                    _persist_setup_record(
                        restricted / "ledger",
                        "reference_execution",
                        f"reference-execution-{candidate_number:02d}-{cycle:02d}",
                        {
                            "candidate_number": candidate_number,
                            "cycle": cycle,
                            "sources": reference["jobs"],
                            "outputs": reference["outputs"],
                            "snapshots": reference["snapshots"],
                            "handoffs": reference["handoffs"],
                        },
                        binding,
                    )
                    _persist_setup_record(
                        restricted / "ledger",
                        "reference_oracle",
                        f"reference-oracle-{candidate_number:02d}-{cycle:02d}",
                        reference["oracle"],
                        binding,
                    )
                    freeze = {
                        "schema_version": "1",
                        "candidate_number": candidate_number,
                        "stabilization_cycles": cycle,
                        "reference": reference,
                        "candidate_rejections": list(rejection_log),
                        terminal_binding_key: terminal_binding,
                    }
                    freeze["reference_freeze_sha256"] = _digest(freeze)
                    freeze_path = restricted / f"reference-freeze-candidate-{candidate_number:02d}.json"
                    _create_json_exclusive(freeze_path, freeze)
                    marker = {
                        **marker,
                        "status": "reference_frozen_for_mutation_resume",
                        "candidate_number": candidate_number,
                        "stabilization_cycles": cycle,
                        "reference_freeze_ref": str(freeze_path.relative_to(repo_root)),
                        "reference_freeze_file_sha256": _sha256_file(freeze_path),
                    }
                    _write_json(marker_path, marker)
                    _append_jsonl(state_root / history_name, marker)
                    preservation_check()
                    try:
                        mutation = inject_v2_mutant(
                            repo_root=repo_root,
                            etiq=etiq,
                            scenario=scenario,
                            jobs=jobs,
                            reference_execution=execution,
                            run_label=f"mutant-c{candidate_number}-s{cycle}",
                            network_cassette_path=offline_cassette,
                        )
                    except ValueError as exc:
                        rejection = {
                            "candidate_number": candidate_number,
                            "cycle": cycle,
                            "gate": "controller_only_mutation_gate",
                            "reason_type": type(exc).__name__,
                            "reason": str(exc),
                            "model_repair_permitted": False,
                        }
                        rejection_log.append(rejection)
                        _persist_setup_record(
                            restricted / "ledger",
                            "rejected_candidate",
                            f"mutation-reject-{candidate_number:02d}",
                            rejection,
                            binding,
                        )
                        marker = {
                            key: value
                            for key, value in marker.items()
                            if key
                            not in {
                                "candidate_number",
                                "stabilization_cycles",
                                "reference_freeze_ref",
                                "reference_freeze_file_sha256",
                            }
                        }
                        marker["status"] = "consumed_in_progress"
                        marker["last_rejected_candidate"] = candidate_number
                        _write_json(marker_path, marker)
                        _append_jsonl(state_root / history_name, marker)
                        preservation_check()
                        break
                    accepted = {
                        "candidate_number": candidate_number,
                        "stabilization_cycles": cycle,
                        "jobs": jobs,
                        "execution": execution,
                        "complexity": complexity,
                        "reference": reference,
                        "mutation": mutation,
                    }
                    break
                failed_checks = execution["oracle"]["failed_check_names"] + complexity[
                    "failed_check_names"
                ]
                upstream_failed = any(name.startswith("upstream") for name in failed_checks)
                failing_job_id = (
                    V2_PREFLIGHT_JOB_IDS[0]
                    if upstream_failed
                    else V2_PREFLIGHT_JOB_IDS[1]
                )
                failure = {
                    "failure_kind": "validation",
                    "failing_job_id": failing_job_id,
                    "stderr": "reference oracle or complexity validation failed",
                    "failed_checks": failed_checks,
                    "compact_diagnostics": {
                        "declared_boundary_count": complexity["declared_boundary_count"],
                        "expandable_helper_count": len(
                            complexity["operationally_expandable_helpers"]
                        ),
                        "full_graph_bytes": complexity["full_graph_bytes"],
                        "selected_graph_bytes": complexity["selected_graph_bytes"],
                    },
                }
            except RuntimeError as exc:
                failure = _failure_from_exception(exc)
            except Exception as exc:
                failure = {
                    "failure_kind": "validation",
                    "failing_job_id": V2_PREFLIGHT_JOB_IDS[0],
                    "stderr": str(exc),
                    "failed_checks": ["capture_or_static_boundary_identity"],
                    "compact_diagnostics": {"error_type": type(exc).__name__},
                }
            if accepted is not None:
                break
            if failure is None:
                break
            if cycle == 3:
                rejection = {
                    "candidate_number": candidate_number,
                    "cycle": cycle,
                    "gate": "reference_stabilization_limit",
                    "reason": "candidate exhausted three stabilization cycles",
                    "failure_kind": failure["failure_kind"],
                    "failed_checks": failure.get("failed_checks", []),
                }
                rejection_log.append(rejection)
                _persist_setup_record(
                    restricted / "ledger",
                    "rejected_candidate",
                    f"reject-{candidate_number:02d}",
                    rejection,
                    binding,
                )
                break
            stabilization_cycle = cycle + 1
            model_settings = {
                "model": getattr(codex, "model", model),
                "reasoning_effort": getattr(codex, "reasoning_effort", "high"),
            }
            stabilization_request = _v2_stabilization_request(
                repo_root,
                scenario,
                jobs,
                candidate_number,
                stabilization_cycle,
                failure,
                model_settings,
            )
            request_identity = str(stabilization_request["request_identity"])
            outcome = run_v2_request_with_retries(
                lambda: request_v2_stabilization_response(
                    codex,
                    setup_id=setup_id,
                    repo_root=repo_root,
                    scenario=scenario,
                    jobs=jobs,
                    candidate_number=candidate_number,
                    cycle=stabilization_cycle,
                    failure=failure,
                    model_settings=model_settings,
                    job_type=stabilization_job_type,
                    purpose=stabilization_purpose,
                ),
                candidate_number=candidate_number,
                cycle=stabilization_cycle,
                request_identity=request_identity,
                request_stage="stabilization",
            )
            for request_failure in outcome["failures"]:
                request_failures.append(request_failure)
                _persist_setup_record(
                    restricted / "ledger",
                    "stabilization_request_failure",
                    (
                        f"stabilization-request-c{candidate_number:02d}-"
                        f"s{stabilization_cycle:02d}-"
                        f"r{int(request_failure['retry_number']):02d}"
                    ),
                    request_failure,
                    binding,
                )
            if outcome["response"] is None:
                request_stop_category = str(outcome["stop_category"])
                request_stop_stage = "stabilization"
                break
            try:
                result, returned_identity = outcome["response"]
                if returned_identity != request_identity:
                    raise ValueError("malformed controller request identity")
                jobs, repair_invocation, repair_usage = _parse_v2_stabilization_response(
                    result,
                    jobs=jobs,
                    failing_job_id=str(failure["failing_job_id"]),
                )
                _persist_setup_record(
                    restricted / "ledger",
                    "stabilization_repair",
                    f"stabilize-{candidate_number:02d}-{stabilization_cycle:02d}",
                    {
                        "candidate_number": candidate_number,
                        "cycle": stabilization_cycle,
                        "request_identity": request_identity,
                        "retry_count": len(outcome["failures"]),
                        "invocation_id": repair_invocation,
                        "fresh_non_resumed_session": True,
                        "failing_job_id": failure["failing_job_id"],
                        "evidence_sha256": _digest(
                            stabilization_request["evidence"]
                        ),
                        "fault_target_visible": False,
                    },
                    binding,
                    repair_usage,
                )
            except Exception as exc:
                rejection = {
                    "candidate_number": candidate_number,
                    "cycle": cycle + 1,
                    "gate": "stabilization_response",
                    "reason_type": type(exc).__name__,
                    "reason": str(exc),
                }
                rejection_log.append(rejection)
                _persist_setup_record(
                    restricted / "ledger",
                    "rejected_candidate",
                    f"reject-stabilize-{candidate_number:02d}",
                    rejection,
                    binding,
                )
                break
        if accepted is not None:
            break
        if request_stop_category is not None:
            break

    root.mkdir(parents=True, exist_ok=True)
    preservation_check()
    usage = _setup_usage(
        store,
        setup_id,
        authoring_purpose=authoring_purpose,
        stabilization_purpose=stabilization_purpose,
    )
    if accepted is None:
        request_terminal_statuses = {
            "deterministic_request_contract_failure": "frozen_input_failure",
            "deterministic_controller_request_failure": "frozen_input_failure",
            "retryable_provider_infrastructure_failure": "provider_infrastructure_failure",
            "provider_failure_unknown_inference_status": "provider_failure_unknown_inference_status",
        }
        terminal_status = request_terminal_statuses.get(
            request_stop_category, "experiment_incomplete"
        )
        terminal_reason = (
            f"{request_stop_stage} request stopped: {request_stop_category}"
            if request_stop_category
            else "authorized Phase-A candidate set exhausted"
        )
        terminal = {
            "schema_version": "1",
            "status": terminal_status,
            "reason": terminal_reason,
            "candidate_limit": 3,
            "stabilization_cycle_limit": 3,
            "requirements_weakened": False,
            "reviewer_model_calls": 0,
            "setup_usage": usage,
            "rejections": rejection_log,
            "request_failures": request_failures,
            terminal_binding_key: terminal_binding,
        }
        terminal["terminal_record_sha256"] = _digest(terminal)
        terminal_path = root / "phase-a-incomplete.json"
        _write_json(terminal_path, terminal)
        marker = {
            **marker,
            "status": terminal_status,
            "outcome_ref": str(terminal_path.relative_to(repo_root)),
            "terminal_record_sha256": terminal["terminal_record_sha256"],
            "setup_usage": usage,
        }
        _write_json(marker_path, marker)
        _append_jsonl(state_root / history_name, marker)
        preservation_check()
        raise RuntimeError(f"{terminal_reason}; frozen at {root}")

    mutation = accepted["mutation"]
    result = _write_success_fixture(
        repo_root=repo_root,
        output_root=state_root,
        root=root,
        restricted=restricted,
        marker=marker,
        reference=accepted["reference"],
        mutation=mutation,
        candidate_number=accepted["candidate_number"],
        stabilization_cycles=accepted["stabilization_cycles"],
        rejection_log=rejection_log,
        usage=usage,
        terminal_binding=terminal_binding,
        terminal_binding_key=terminal_binding_key,
        marker_name=marker_name,
        history_name=history_name,
    )
    preservation_check()
    return result


def run_phase_a_preflight_v2_n03(
    *,
    repo_root: Path,
    output_root: Path,
    model: str = "gpt-5.5",
    timeout_seconds: int = 1800,
    codex_factory: Callable[[JobStore], CodexRunner] | None = None,
    etiq_factory: Callable[[JobStore], EtiqExecutor] | None = None,
) -> Path:
    return run_phase_a_preflight_v2(
        repo_root=repo_root,
        output_root=output_root,
        model=model,
        timeout_seconds=timeout_seconds,
        codex_factory=codex_factory,
        etiq_factory=etiq_factory,
        authority="n03",
    )


def run_phase_a_preflight_v2_n04(
    *,
    repo_root: Path,
    output_root: Path,
    model: str = "gpt-5.5",
    timeout_seconds: int = 1800,
    codex_factory: Callable[[JobStore], CodexRunner] | None = None,
    etiq_factory: Callable[[JobStore], EtiqExecutor] | None = None,
) -> Path:
    return run_phase_a_preflight_v2(
        repo_root=repo_root,
        output_root=output_root,
        model=model,
        timeout_seconds=timeout_seconds,
        codex_factory=codex_factory,
        etiq_factory=etiq_factory,
        authority="n04",
    )


# Filled from the controlling N02 decision. Keeping this detached from the path
# table makes the post-reference recheck explicit at the point of consumption.
AUTHORIZED_INPUT_HASHES = {
    "restricted_controller_plan_sha256": "892137b4a1683e4504a5c05e55cf10dde4afa14caeecc8e0f4cfef9620eaf01a"
}
