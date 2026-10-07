"""Deterministic mechanics for the separate pilot-informed v2 study."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import textwrap
from typing import Any, Callable, Iterable, Mapping

from .controlled_experiment import replace_scope
from .fault_injection import (
    REQUIRED_VALIDATION_FLAGS,
    _bundle_sha256,
    _changed_source_regions,
    _indented_function_source,
    _scope_nodes,
    normalize_pipeline,
)
from .records import EtiqEvidenceSnapshot, GeneratedPipeline, stable_hash
from .review import frame_name


PROTOCOL_ID = "neurips-2026-workshop-fault-localisation-v2"
PROTOCOL_VERSION = "2.0.3"
V2_OUTPUT_RELATIVE_PATH = PurePosixPath("outputs/fault-experiments-v2")
V1_FORBIDDEN_CONTEXT_MARKERS = (
    "instructions_between_agent_types/overseer/decisions/",
    "instructions_between_agent_types/developer/handoffs/",
    "docs/experiments/2026-workshop-fault-localisation/",
    "docs/workshops/neurips-2026/",
    "protocol-1.3.1-phase-a-attempt",
    "c07b-authorization-consumption",
    "c07d-authorization-consumption",
    "c07b-phase-a-history",
    "c07d-phase-a-history",
    "preflight-03420ef8721a4358",
    "preflight-d06945d8ba2b4345",
    "preflight-e8a6bd2f06fb4c58",
    "preflight-25f37de3755d421f",
)
V2_PATH_OPERATIONS = frozenset(
    {"read", "list", "import", "resume", "patch", "consume", "write"}
)
V2_DESIGN_AUTHORITIES = {
    "instructions_between_agent_types/overseer/decisions/N01_v2_study_design_authorization.json": "sha256:c90c5c41c0f076b5730819a055e7daca62dcf96d6ac43a5762827de705b38186",
    "instructions_between_agent_types/overseer/decisions/N01A_v2_design_remediation_authorization.json": "sha256:4c35eeeed87c6549cdc6d0b1989a8c0b91a051d1e8573c805dd046176efd9479",
    "instructions_between_agent_types/overseer/decisions/N01B_v2_execution_readiness_remediation_authorization.json": "sha256:727b8612a906a59788fce0450b7294a1e610c02d05eab4df8f8cffe1a3b08ae4",
    "instructions_between_agent_types/overseer/decisions/N02A_v2_phase_a_transport_remediation_authorization.json": "sha256:bf1f0fa875e226101c88134a34f9910c20b3256864a86513b18344518f809abd",
}


def v2_output_root(repo_root: Any) -> Any:
    """Return, but never create, the only permitted v2 output namespace."""
    return repo_root / V2_OUTPUT_RELATIVE_PATH.as_posix()


def validate_v2_output_root(repo_root: Any, output_root: Any) -> None:
    if output_root.resolve() != v2_output_root(repo_root).resolve():
        raise ValueError("v2 execution output must use its separate reserved root")


def validate_v2_model_context_refs(
    refs: Iterable[str], *, repo_root: Path | None = None
) -> None:
    for ref in refs:
        normalized = str(ref).replace("\\", "/").casefold()
        parts = [part for part in normalized.split("/") if part not in {"", "."}]
        predecessor_output = any(
            parts[index : index + 2] == ["outputs", "fault-experiments"]
            for index in range(len(parts) - 1)
        )
        restricted_controller_state = (
            normalized.rstrip("/").endswith("/restricted")
            or "/restricted/" in f"/{normalized.lstrip('/')}"
        )
        if predecessor_output or restricted_controller_state or any(
            marker in normalized for marker in V1_FORBIDDEN_CONTEXT_MARKERS
        ):
            raise ValueError("protocol 1.3.1 state is forbidden in v2 model context")
        if repo_root is not None:
            try:
                validate_v2_path_operation(repo_root, ref, operation="read")
            except ValueError as error:
                raise ValueError(
                    "protocol 1.3.1 state is forbidden in v2 model context"
                ) from error


def validate_v2_path_operation(
    repo_root: Path, path: str | Path, *, operation: str
) -> Path:
    """Resolve a v2 path and reject predecessor access before caller I/O."""
    if operation not in V2_PATH_OPERATIONS:
        raise ValueError(f"unknown v2 path operation: {operation}")
    root = repo_root.resolve()
    requested = Path(path)
    target = (requested if requested.is_absolute() else root / requested).resolve(
        strict=False
    )
    forbidden_roots = (
        root / "outputs/fault-experiments",
        root / "instructions_between_agent_types/overseer/decisions",
        root / "instructions_between_agent_types/developer/handoffs",
        root / "docs/experiments/2026-workshop-fault-localisation",
        root / "docs/workshops/neurips-2026",
    )
    prompt_root = (root / "prompts").resolve()
    schema_root = (root / "schemas").resolve()
    v2_prompt_root = (prompt_root / "v2").resolve()
    v2_schema_root = (schema_root / "v2").resolve()

    def within(candidate: Path, parent: Path) -> bool:
        return candidate == parent or parent in candidate.parents

    predecessor_namespace = (
        within(target, prompt_root) and not within(target, v2_prompt_root)
    ) or (within(target, schema_root) and not within(target, v2_schema_root))
    if predecessor_namespace or any(
        within(target, forbidden.resolve()) for forbidden in forbidden_roots
    ):
        raise ValueError(
            f"v2 {operation} is forbidden for protocol 1.3.1 state"
        )
    return target


def validate_v2_controller_path(
    repo_root: Path,
    path: str | Path,
    *,
    operation: str,
    additional_authorities: Mapping[str | Path, str] | None = None,
) -> Path:
    """Allow exact v2 state or hash-bound authorities for the controller only."""
    if operation not in V2_PATH_OPERATIONS:
        raise ValueError(f"unknown v2 controller operation: {operation}")
    root = repo_root.resolve()
    requested = Path(path)
    target = (requested if requested.is_absolute() else root / requested).resolve(
        strict=False
    )
    v2_state_root = v2_output_root(root).resolve()
    if target == v2_state_root or v2_state_root in target.parents:
        return target
    decision_root = (
        root / "instructions_between_agent_types/overseer/decisions"
    ).resolve()
    if target == decision_root or decision_root in target.parents:
        if operation not in {"read", "consume"}:
            raise ValueError("v2 controller authorities permit read or consume only")
        authorities = {
            (root / relative).resolve(): digest
            for relative, digest in V2_DESIGN_AUTHORITIES.items()
        }
        for authority_path, digest in (additional_authorities or {}).items():
            supplied = Path(authority_path)
            resolved = (
                supplied if supplied.is_absolute() else root / supplied
            ).resolve(strict=False)
            if not resolved.name.startswith(("N02", "N03", "N04")) or resolved.suffix != ".json":
                raise ValueError(
                    "v2 controller additional authority must be an explicit N02/N03/N04 JSON path"
                )
            authorities[resolved] = str(digest)
        expected = authorities.get(target)
        if expected is None:
            raise ValueError("v2 controller authority path is not explicitly allowlisted")
        if not target.is_file():
            raise ValueError("v2 controller authority file is absent")
        observed = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        if observed != expected:
            raise ValueError("v2 controller authority hash mismatch")
        return target
    return validate_v2_path_operation(root, target, operation=operation)


def _normalized_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"invalid generated source path: {value!r}")
    return path.as_posix()


def _source_sha256(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    normalized = ast.unparse(ast.fix_missing_locations(deepcopy(node))).strip() + "\n"
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonicalize_v2_qualified_function_name(value: str) -> str:
    """Remove only exact Python ``<locals>`` qualname components."""
    components = str(value).split(".")
    if any(not component for component in components):
        raise ValueError("v2 qualified function name contains an empty component")
    canonical: list[str] = []
    for component in components:
        if component == "<locals>":
            continue
        if "<" in component or ">" in component:
            raise ValueError("v2 qualified function name has a malformed angle-bracket component")
        canonical.append(component)
    if not canonical:
        raise ValueError("v2 qualified function name is empty after canonicalization")
    return ".".join(canonical)


def _definition_node_v2(
    pipeline: GeneratedPipeline, *, source_path: str, qualified_function_name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    expected_path = _normalized_path(source_path)
    source = next(
        (item.content for item in pipeline.files if _normalized_path(item.path) == expected_path),
        None,
    )
    if source is None:
        raise ValueError("v2 definition source path is absent from generated job")
    matches: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def visit(body: Iterable[ast.stmt], parents: tuple[str, ...]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = ".".join((*parents, node.name))
                if qualified == qualified_function_name:
                    matches.append(node)
                visit(node.body, (*parents, node.name))
            elif isinstance(node, ast.ClassDef):
                visit(node.body, (*parents, node.name))

    visit(ast.parse(source, filename=expected_path).body, ())
    if len(matches) != 1:
        raise ValueError("v2 definition does not resolve to one generated AST function")
    return matches[0]


def _definitions(pipeline: GeneratedPipeline, job_id: str) -> list[dict[str, str]]:
    pipeline.validate()
    found: list[dict[str, str]] = []

    def visit(body: Iterable[ast.stmt], path: str, parents: tuple[str, ...]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = ".".join((*parents, node.name))
                found.append(
                    {
                        "job_id": str(job_id),
                        "source_path": path,
                        "qualified_function_name": qualified,
                        "function_source_sha256": _source_sha256(node),
                    }
                )
                visit(node.body, path, (*parents, node.name))
            elif isinstance(node, ast.ClassDef):
                visit(node.body, path, (*parents, node.name))

    for item in sorted(pipeline.files, key=lambda value: value.path):
        path = _normalized_path(item.path)
        visit(ast.parse(item.content, filename=path).body, path, ())
    return found


def generated_pipeline_from_v2_payload(
    job_id: str, payload: Mapping[str, Any]
) -> GeneratedPipeline:
    """Parse one schema-shaped v2 job without discarding boundary identity."""
    pipeline = GeneratedPipeline.from_payload(payload)
    boundaries: list[dict[str, Any]] = []
    resolved_identities: set[tuple[str, str, str, str]] = set()
    for declaration in pipeline.review_boundaries:
        boundary_id = str(declaration.get("boundary_id") or "").strip()
        if not boundary_id:
            raise ValueError("v2 review boundary requires boundary_id")
        identity = declared_boundary_identity_v2(
            job_id,
            pipeline,
            source_path=str(declaration.get("source_path") or ""),
            qualified_function_name=str(
                declaration.get("qualified_function_name") or ""
            ),
        )
        identity_key = (
            identity["job_id"],
            identity["source_path"],
            identity["qualified_function_name"],
            identity["function_source_sha256"],
        )
        if identity_key in resolved_identities:
            raise ValueError("v2 boundary declarations resolve to a duplicate static definition")
        resolved_identities.add(identity_key)
        boundaries.append({**declaration, **identity, "boundary_id": boundary_id})
    pipeline.review_boundaries = boundaries
    pipeline.validate()
    return pipeline


def declared_boundary_identity_v2(
    job_id: str,
    pipeline: GeneratedPipeline,
    *,
    source_path: str,
    qualified_function_name: str,
) -> dict[str, str]:
    expected_path = _normalized_path(source_path)
    expected_qualified_name = canonicalize_v2_qualified_function_name(
        qualified_function_name
    )
    matches = [
        value
        for value in _definitions(pipeline, job_id)
        if value["source_path"] == expected_path
        and value["qualified_function_name"] == expected_qualified_name
    ]
    if len(matches) != 1:
        raise ValueError("declared v2 boundary does not resolve to one static definition")
    return matches[0]


def _canonical_stack(stack: Iterable[str]) -> tuple[str, ...]:
    return tuple(frame_name(str(value)) for value in stack)


def _starts_with(stack: Iterable[str], prefix: tuple[str, ...]) -> bool:
    canonical = _canonical_stack(stack)
    return len(canonical) >= len(prefix) and canonical[: len(prefix)] == prefix


def _runtime_identity(nodes: list[Any]) -> tuple[str, str, str, str]:
    if not nodes:
        raise ValueError("captured prefix has no direct nodes")
    identities = set()
    for node in nodes:
        metadata = node.raw_metadata
        required = (
            metadata.get("v2_job_id"),
            metadata.get("v2_source_path"),
            metadata.get("v2_qualified_function_name"),
            metadata.get("v2_function_source_sha256"),
        )
        if not all(required):
            raise ValueError(
                "captured direct node lacks complete v2 static identity"
            )
        identity = (
            str(required[0]),
            _normalized_path(str(required[1])),
            str(required[2]),
            str(required[3]),
        )
        identities.add(identity)
    if len(identities) != 1:
        raise ValueError(
            "captured prefix lacks one exact v2 job/path/qualified-function/source-hash identity"
        )
    return next(iter(identities))


def _captured_prefix_derivation_v2(
    nodes: list[Any],
    *,
    prefix: tuple[str, ...],
    identity: Mapping[str, str],
    generated_start_line: int,
) -> dict[str, Any]:
    evidence: list[dict[str, str]] = []
    for node in nodes:
        source_node_type = str(node.raw_metadata.get("source_node_type") or "")
        if not source_node_type:
            raise ValueError("captured direct node lacks source-node type evidence")
        declares_function = source_node_type in {"FunctionDef", "AsyncFunctionDef"}
        parsed_function: ast.FunctionDef | ast.AsyncFunctionDef | None = None
        parsed_source_type = ""
        if node.source:
            try:
                body = ast.parse(textwrap.dedent(str(node.source))).body
            except (IndentationError, SyntaxError):
                body = []
            if len(body) == 1:
                parsed_source_type = type(body[0]).__name__
            if len(body) == 1 and isinstance(
                body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                parsed_function = body[0]
        if parsed_source_type and parsed_source_type != source_node_type:
            raise ValueError("captured source-node type conflicts with captured source")
        if declares_function and parsed_function is None:
            raise ValueError("captured function-definition source is unparseable or incomplete")
        if parsed_function is None:
            continue
        if not declares_function:
            raise ValueError("captured function-definition source has a non-function marker")
        if node.scope_type not in {"FunctionDef", "AsyncFunctionDef"}:
            continue
        if parsed_function.name != identity["qualified_function_name"].split(".")[-1]:
            raise ValueError("captured function-definition source names another function")
        captured_hash = _source_sha256(parsed_function)
        if captured_hash != identity["function_source_sha256"]:
            raise ValueError("captured function-definition source hash conflicts with generated source")
        if node.line_no is not None and int(node.line_no) != generated_start_line:
            raise ValueError("captured function-definition line conflicts with generated source")
        evidence.append(
            {
                "node_ref": node.node_ref,
                "scope_type": node.scope_type,
                "normalized_captured_source_sha256": captured_hash,
            }
        )
    if not evidence:
        raise ValueError("captured prefix lacks complete function-definition evidence")
    hashes = {item["normalized_captured_source_sha256"] for item in evidence}
    if hashes != {identity["function_source_sha256"]}:
        raise ValueError("captured function-definition evidence is internally conflicting")
    return {
        "captured_definition_evidence": sorted(evidence, key=lambda item: item["node_ref"]),
        "prefix": list(prefix),
        "selected_job_id": identity["job_id"],
        "normalized_source_path": identity["source_path"],
        "qualified_function_name": identity["qualified_function_name"],
        "generated_function_source_sha256": identity["function_source_sha256"],
        "generated_definition_start_line": generated_start_line,
    }


def enrich_snapshot_identities_v2(
    snapshot: EtiqEvidenceSnapshot,
    declarations: Iterable[Mapping[str, Any]],
    *,
    job_id: str,
    pipeline: GeneratedPipeline,
) -> EtiqEvidenceSnapshot:
    """Bind raw capture prefixes to unique definitions in the executed job."""
    if snapshot.job_id != job_id:
        raise ValueError("v2 capture belongs to a different selected job")
    enriched = deepcopy(snapshot)
    all_definitions = _definitions(pipeline, job_id)
    by_simple: dict[str, list[dict[str, str]]] = {}
    for definition in all_definitions:
        simple = definition["qualified_function_name"].split(".")[-1]
        by_simple.setdefault(simple, []).append(definition)
    identity_keys = (
        "v2_job_id",
        "v2_source_path",
        "v2_qualified_function_name",
        "v2_function_source_sha256",
    )
    claimed_prefixes: set[tuple[str, ...]] = set()
    for declaration in declarations:
        identity = declared_boundary_identity_v2(
            job_id,
            pipeline,
            source_path=str(declaration.get("source_path") or ""),
            qualified_function_name=str(
                declaration.get("qualified_function_name") or ""
            ),
        )
        declared_hash = str(declaration.get("function_source_sha256") or "")
        if declared_hash != identity["function_source_sha256"]:
            raise ValueError("declared v2 function-source hash mismatch")
        simple_name = identity["qualified_function_name"].split(".")[-1]
        generated_definition = _definition_node_v2(
            pipeline,
            source_path=identity["source_path"],
            qualified_function_name=identity["qualified_function_name"],
        )
        if by_simple.get(simple_name) != [identity]:
            raise ValueError(
                "captured function name does not resolve to one generated definition"
            )
        prefixes = {
            prefix
            for node in enriched.nodes
            for depth in range(1, len(node.func_stack) + 1)
            if (prefix := _canonical_stack(node.func_stack[:depth]))[-1]
            == simple_name
        }
        if not prefixes:
            raise ValueError("declared v2 boundary has no captured runtime prefix")
        for prefix in prefixes:
            if prefix in claimed_prefixes:
                raise ValueError("captured prefix resolves to multiple declarations")
            claimed_prefixes.add(prefix)
            direct = [
                node
                for node in enriched.nodes
                if _canonical_stack(node.func_stack) == prefix
            ]
            if not direct:
                raise ValueError("captured prefix has no direct nodes")
            derivation = _captured_prefix_derivation_v2(
                direct,
                prefix=prefix,
                identity=identity,
                generated_start_line=int(generated_definition.lineno),
            )
            derivation_sha256 = stable_hash(derivation)
            for node in direct:
                present = [key in node.raw_metadata for key in identity_keys]
                if any(present) and not all(present):
                    raise ValueError("captured direct node has partial forged v2 identity")
                expected_values = (
                    identity["job_id"],
                    identity["source_path"],
                    identity["qualified_function_name"],
                    identity["function_source_sha256"],
                )
                if all(present):
                    observed = tuple(str(node.raw_metadata[key]) for key in identity_keys)
                    if observed != expected_values:
                        raise ValueError("captured direct node identity conflicts with source")
                node.raw_metadata.update(dict(zip(identity_keys, expected_values)))
                node.raw_metadata["v2_identity_derivation"] = deepcopy(derivation)
                node.raw_metadata["v2_identity_derivation_sha256"] = derivation_sha256
    return enriched


def materialize_realized_boundaries_v2(
    snapshot: EtiqEvidenceSnapshot,
    declarations: Iterable[Mapping[str, Any]],
    *,
    job_id: str,
    pipeline: GeneratedPipeline,
) -> list[dict[str, Any]]:
    """Group repeated runtime prefixes only for one exact static identity."""
    if snapshot.job_id != job_id:
        raise ValueError("v2 boundary snapshot belongs to a different selected job")
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {value.relationship_ref: value for value in snapshot.relationships}
    if len(node_by_ref) != len(snapshot.nodes) or len(relationship_by_ref) != len(
        snapshot.relationships
    ):
        raise ValueError("v2 capture contains duplicate evidence references")
    if any(
        relationship.source_ref not in node_by_ref
        or relationship.target_ref not in node_by_ref
        for relationship in snapshot.relationships
    ):
        raise ValueError("v2 capture relationship has a missing endpoint")

    realized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for declaration in declarations:
        boundary_id = str(declaration.get("boundary_id") or "").strip()
        if not boundary_id or boundary_id in seen_ids:
            raise ValueError("v2 boundary IDs must be present and unique")
        seen_ids.add(boundary_id)
        identity = declared_boundary_identity_v2(
            job_id,
            pipeline,
            source_path=str(declaration.get("source_path") or ""),
            qualified_function_name=str(
                declaration.get("qualified_function_name") or ""
            ),
        )
        declared_hash = str(declaration.get("function_source_sha256") or "")
        if declared_hash != identity["function_source_sha256"]:
            raise ValueError("declared v2 function-source hash mismatch")
        simple_name = identity["qualified_function_name"].split(".")[-1]
        generated_definition = _definition_node_v2(
            pipeline,
            source_path=identity["source_path"],
            qualified_function_name=identity["qualified_function_name"],
        )
        same_name = [
            value
            for value in _definitions(pipeline, job_id)
            if value["qualified_function_name"].split(".")[-1] == simple_name
        ]
        if same_name != [identity]:
            raise ValueError(
                "captured function name does not resolve to one generated definition"
            )
        prefixes = sorted(
            {
                prefix
                for node in snapshot.nodes
                for depth in range(1, len(node.func_stack) + 1)
                if (prefix := _canonical_stack(node.func_stack[:depth]))[-1]
                == simple_name
            }
        )
        if not prefixes:
            raise ValueError("declared v2 boundary has no captured runtime prefix")
        for prefix in prefixes:
            direct = [
                node
                for node in snapshot.nodes
                if _canonical_stack(node.func_stack) == prefix
            ]
            runtime = _runtime_identity(direct)
            derivation = _captured_prefix_derivation_v2(
                direct,
                prefix=prefix,
                identity=identity,
                generated_start_line=int(generated_definition.lineno),
            )
            derivation_sha256 = stable_hash(derivation)
            if any(
                node.raw_metadata.get("v2_identity_derivation") != derivation
                or node.raw_metadata.get("v2_identity_derivation_sha256")
                != derivation_sha256
                for node in direct
            ):
                raise ValueError("captured prefix derivation does not recompute")
            expected = (
                identity["job_id"],
                identity["source_path"],
                identity["qualified_function_name"],
                identity["function_source_sha256"],
            )
            if runtime != expected:
                raise ValueError(
                    "same-name runtime prefixes resolve to different v2 static identities"
                )

        inside_refs = {
            node.node_ref
            for node in snapshot.nodes
            if any(_starts_with(node.func_stack, prefix) for prefix in prefixes)
        }
        relationships = {
            value.relationship_ref
            for value in snapshot.relationships
            if value.source_ref in inside_refs or value.target_ref in inside_refs
        }
        inputs = {
            value.relationship_ref
            for value in snapshot.relationships
            if value.source_ref not in inside_refs and value.target_ref in inside_refs
        }
        outputs = {
            value.relationship_ref
            for value in snapshot.relationships
            if value.source_ref in inside_refs and value.target_ref not in inside_refs
        }
        helper_prefixes = sorted(
            {
                canonical[:depth]
                for node in snapshot.nodes
                if any(_starts_with(node.func_stack, prefix) for prefix in prefixes)
                for canonical in [_canonical_stack(node.func_stack)]
                for prefix in prefixes
                if canonical[: len(prefix)] == prefix
                for depth in range(len(prefix) + 1, len(canonical) + 1)
            },
            key=lambda value: (len(value), value),
        )
        function_refs = sorted(
            node.node_ref
            for node in snapshot.nodes
            if _canonical_stack(node.func_stack) in prefixes
            and node.state_type.casefold().replace("_", "") == "functionmapping"
        )
        boundary = {
            "boundary_id": boundary_id,
            "static_identity": identity,
            "function_name": simple_name,
            "matched_prefix": list(prefixes[0]),
            "matched_prefixes": [list(value) for value in prefixes],
            "prefix_multiplicity": len(prefixes),
            "matched_function_node_refs": function_refs,
            "matched_function_node_ref": function_refs[0]
            if function_refs
            else sorted(inside_refs)[0],
            "node_refs": sorted(inside_refs),
            "relationship_refs": sorted(relationships),
            "input_relationship_refs": sorted(inputs),
            "output_relationship_refs": sorted(outputs),
            "helper_prefixes": [list(value) for value in helper_prefixes],
        }
        boundary["realized_boundary_sha256"] = stable_hash(boundary)
        realized.append(boundary)
    if not realized:
        raise ValueError("v2 requires at least one declared boundary")
    return sorted(realized, key=lambda value: value["boundary_id"])


def grouped_boundary_selection_v2(
    snapshot: EtiqEvidenceSnapshot,
    boundary: Mapping[str, Any],
    *,
    expanded_prefixes: Iterable[Iterable[str]] = (),
) -> dict[str, Any]:
    base_prefixes = {tuple(value) for value in boundary["matched_prefixes"]}
    allowed = {tuple(value) for value in boundary["helper_prefixes"]}
    requested = {tuple(str(item) for item in value) for value in expanded_prefixes}
    if not requested.issubset(allowed):
        raise ValueError("v2 expansion is not a captured helper of the grouped boundary")
    if any(prefix[:-1] not in base_prefixes | requested for prefix in requested):
        raise ValueError("v2 expansion must include its visible parent prefix")
    visible_prefixes = base_prefixes | requested
    selected_nodes = {
        node.node_ref
        for node in snapshot.nodes
        if _canonical_stack(node.func_stack) in visible_prefixes
    }
    boundary_relationships = set(boundary["input_relationship_refs"]) | set(
        boundary["output_relationship_refs"]
    )
    selected_relationships = {
        value.relationship_ref
        for value in snapshot.relationships
        if value.relationship_ref in boundary_relationships
        or (value.source_ref in selected_nodes and value.target_ref in selected_nodes)
    }
    for relationship in snapshot.relationships:
        if relationship.relationship_ref in boundary_relationships:
            selected_nodes.add(relationship.source_ref)
            selected_nodes.add(relationship.target_ref)
    result = {
        "boundary_id": boundary["boundary_id"],
        "node_refs": sorted(selected_nodes),
        "relationship_refs": sorted(selected_relationships),
        "expanded_prefixes": [list(value) for value in sorted(requested)],
    }
    result["selection_sha256"] = stable_hash(result)
    return result


def _reverse_sites(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    sites: list[dict[str, Any]] = []
    for node in _scope_nodes(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "sorted":
            reverse = next((value for value in node.keywords if value.arg == "reverse"), None)
            if reverse is not None and not (
                isinstance(reverse.value, ast.Constant)
                and isinstance(reverse.value.value, bool)
            ):
                raise ValueError("v2 reverse_ordering rejects dynamic sorted reverse")
            sites.append(
                {
                    "kind": "sorted",
                    "node": node,
                    "subsite": None,
                    "line": node.lineno,
                    "column": node.col_offset,
                }
            )
            continue
        if not (
            isinstance(node.func, ast.Attribute) and node.func.attr == "sort_values"
        ):
            continue
        ascending = next(
            (value for value in node.keywords if value.arg == "ascending"), None
        )
        if ascending is None:
            if len(node.args) > 1:
                raise ValueError(
                    "v2 reverse_ordering rejects positional or ambiguous ascending"
                )
            continue
        value = ascending.value
        if isinstance(value, ast.Constant) and isinstance(value.value, bool):
            sites.append(
                {
                    "kind": "sort_values_scalar",
                    "node": node,
                    "subsite": None,
                    "line": value.lineno,
                    "column": value.col_offset,
                }
            )
        elif isinstance(value, ast.List) and value.elts and all(
            isinstance(item, ast.Constant) and isinstance(item.value, bool)
            for item in value.elts
        ):
            for index, item in enumerate(value.elts):
                sites.append(
                    {
                        "kind": "sort_values_list",
                        "node": node,
                        "subsite": index,
                        "line": item.lineno,
                        "column": item.col_offset,
                    }
                )
        else:
            raise ValueError("v2 reverse_ordering rejects unsupported ascending value")
    return sorted(
        sites,
        key=lambda value: (
            value["line"],
            value["column"],
            -1 if value["subsite"] is None else value["subsite"],
        ),
    )


def _target_definition_v2(
    pipeline: GeneratedPipeline, target_identity: Mapping[str, Any]
) -> tuple[dict[str, Any], ast.FunctionDef | ast.AsyncFunctionDef, dict[str, str]]:
    job_id = str(target_identity.get("job_id") or "")
    expected = declared_boundary_identity_v2(
        job_id,
        pipeline,
        source_path=str(target_identity.get("source_path") or ""),
        qualified_function_name=str(
            target_identity.get("qualified_function_name") or ""
        ),
    )
    if any(str(target_identity.get(key) or "") != value for key, value in expected.items()):
        raise ValueError("v2 mutation target identity conflicts with generated source")
    source = next(
        item.content for item in pipeline.files if item.path == expected["source_path"]
    )
    matches: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def visit(body: Iterable[ast.stmt], parents: tuple[str, ...]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = ".".join((*parents, node.name))
                if qualified == expected["qualified_function_name"]:
                    matches.append(node)
                visit(node.body, (*parents, node.name))
            elif isinstance(node, ast.ClassDef):
                visit(node.body, (*parents, node.name))

    visit(ast.parse(source, filename=expected["source_path"]).body, ())
    if len(matches) != 1:
        raise ValueError("v2 mutation target does not resolve to one exact definition")
    function = matches[0]
    scope = {
        "requested_mode": "boundary",
        "effective_mode": "boundary",
        "scope_kind": "function",
        "function_name": function.name,
        "file": expected["source_path"],
        "start_line": function.lineno,
        "end_line": int(function.end_lineno or function.lineno),
    }
    return scope, function, expected


def enumerate_reverse_ordering_sites_v2(
    pipeline: GeneratedPipeline, *, target_identity: Mapping[str, Any]
) -> list[dict[str, Any]]:
    clean = normalize_pipeline(pipeline)
    scope, function, identity = _target_definition_v2(clean, target_identity)
    return [
        {
            "file": scope["file"],
            "job_id": identity["job_id"],
            "qualified_function_name": identity["qualified_function_name"],
            "function_source_sha256": identity["function_source_sha256"],
            "occurrence": occurrence,
            "kind": site["kind"],
            "subsite": site["subsite"],
            "line": site["line"],
            "column": site["column"],
        }
        for occurrence, site in enumerate(_reverse_sites(function))
    ]


def inject_reverse_ordering_v2(
    pipeline: GeneratedPipeline,
    *,
    target_identity: Mapping[str, Any],
    occurrence: int,
) -> dict[str, Any]:
    clean = normalize_pipeline(pipeline)
    scope, original_function, identity = _target_definition_v2(
        clean, target_identity
    )
    function = deepcopy(original_function)
    sites = _reverse_sites(function)
    if occurrence < 0 or occurrence >= len(sites):
        raise ValueError("v2 reverse_ordering occurrence is unavailable")
    site = sites[occurrence]
    node = site["node"]
    if site["kind"] == "sorted":
        reverse = next((value for value in node.keywords if value.arg == "reverse"), None)
        if reverse is None:
            node.keywords.append(ast.keyword(arg="reverse", value=ast.Constant(True)))
        else:
            reverse.value.value = not reverse.value.value
    else:
        ascending = next(value for value in node.keywords if value.arg == "ascending")
        target = (
            ascending.value
            if site["kind"] == "sort_values_scalar"
            else ascending.value.elts[int(site["subsite"])]
        )
        target.value = not target.value
    function = ast.fix_missing_locations(function)
    original_source = _indented_function_source(original_function)
    mutant_source = _indented_function_source(function)
    original_span, mutant_span, original_snippet, mutant_snippet = (
        _changed_source_regions(
            original_source,
            mutant_source,
            file_start_line=int(scope["start_line"]),
        )
    )
    mutant = replace_scope(clean, scope, mutant_source)
    for item in mutant.files:
        compile(item.content, item.path, "exec")
    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "fault_class": "reverse_ordering",
        "clean_pipeline": clean,
        "pipeline": mutant,
        "site": {
            "file": scope["file"],
            "job_id": identity["job_id"],
            "qualified_function_name": identity["qualified_function_name"],
            "function_source_sha256": identity["function_source_sha256"],
            "function_name": identity["qualified_function_name"].split(".")[-1],
            "occurrence": occurrence,
            "candidate_count": len(sites),
            "kind": site["kind"],
            "subsite": site["subsite"],
            "original_span": original_span,
            "mutant_span": mutant_span,
            "original_snippet": original_snippet,
            "mutant_snippet": mutant_snippet,
            "original_snippet_sha256": "sha256:"
            + hashlib.sha256(original_snippet.encode("utf-8")).hexdigest(),
            "mutant_snippet_sha256": "sha256:"
            + hashlib.sha256(mutant_snippet.encode("utf-8")).hexdigest(),
        },
        "clean_bundle_sha256": _bundle_sha256(clean),
        "mutant_bundle_sha256": _bundle_sha256(mutant),
    }


def freeze_reverse_ordering_order_v2(
    pipeline: GeneratedPipeline,
    *,
    target_identity: Mapping[str, Any],
    seed: int,
    preferred_occurrence: int | None,
) -> dict[str, Any]:
    clean = normalize_pipeline(pipeline)
    _scope, _function, identity = _target_definition_v2(clean, target_identity)
    sites = enumerate_reverse_ordering_sites_v2(
        clean, target_identity=identity
    )
    clean_hash = _bundle_sha256(clean)
    candidates = []
    for site in sites:
        bound = {
            "mutation_seed": int(seed),
            "clean_bundle_sha256": clean_hash,
            "job_id": identity["job_id"],
            "source_path": identity["source_path"],
            "qualified_function_name": identity["qualified_function_name"],
            "function_source_sha256": identity["function_source_sha256"],
            "site_kind": site["kind"],
            "occurrence": site["occurrence"],
            "list_subsite": site["subsite"],
        }
        candidates.append(
            {
                **site,
                "order_key": "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        bound, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest(),
            }
        )
    preferred = next(
        (
            item
            for item in candidates
            if item["occurrence"] == preferred_occurrence
        ),
        None,
    )
    fallback = sorted(
        (item for item in candidates if item is not preferred),
        key=lambda item: (item["order_key"], item["occurrence"]),
    )
    ordered = ([preferred] if preferred is not None else []) + fallback
    schedule = {
        "mutation_seed": int(seed),
        "clean_bundle_sha256": clean_hash,
        "target_identity": identity,
        "preferred_occurrence": preferred_occurrence,
        "preferred_occurrence_eligible": preferred is not None,
        "candidates_in_source_order": candidates,
        "frozen_candidates": ordered,
    }
    schedule["frozen_schedule_sha256"] = stable_hash(schedule)
    return schedule


def inject_reverse_ordering_with_fallback_v2(
    pipeline: GeneratedPipeline,
    *,
    target_identity: Mapping[str, Any],
    seed: int,
    preferred_occurrence: int | None,
    validator: Callable[[GeneratedPipeline, Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    clean = normalize_pipeline(pipeline)
    schedule = freeze_reverse_ordering_order_v2(
        clean,
        target_identity=target_identity,
        seed=seed,
        preferred_occurrence=preferred_occurrence,
    )
    rejections: list[dict[str, Any]] = []
    for candidate in schedule["frozen_candidates"]:
        occurrence = int(candidate["occurrence"])
        injected = inject_reverse_ordering_v2(
            clean,
            target_identity=schedule["target_identity"],
            occurrence=occurrence,
        )
        validation = dict(
            validator(deepcopy(injected["pipeline"]), deepcopy(injected["site"]))
        )
        failed = [
            name for name in REQUIRED_VALIDATION_FLAGS if validation.get(name) is not True
        ]
        if injected["clean_pipeline"].files != clean.files or injected[
            "clean_pipeline"
        ].review_boundaries != clean.review_boundaries:
            raise ValueError("v2 clean bundle was not restored byte-for-byte")
        if not failed:
            if _bundle_sha256(injected["clean_pipeline"]) != injected[
                "clean_bundle_sha256"
            ]:
                raise ValueError("v2 clean restoration hash changed")
            return {
                **injected,
                "frozen_schedule": schedule,
                "selected_occurrence": occurrence,
                "rejections": rejections,
                "validation": validation,
            }
        rejections.append(
            {
                "occurrence": occurrence,
                "order_key": candidate["order_key"],
                "failed_flags": failed,
            }
        )
    raise ValueError(
        "v2 frozen reverse_ordering sites exhausted: "
        + json.dumps(
            {"frozen_schedule": schedule, "rejections": rejections},
            sort_keys=True,
        )
    )
