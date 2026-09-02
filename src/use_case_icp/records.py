from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Mapping


SCHEMA_VERSION = "1"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {item.name: jsonable(getattr(value, item.name)) for item in dataclasses.fields(value)}
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return value


def stable_hash(value: Any) -> str:
    encoded = json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TrustLevel(StrEnum):
    REUSE = "trusted_for_reuse"
    REPORTING = "trusted_for_reporting"
    PROVISIONAL = "provisionally_trusted"


class ReviewDecisionStatus(StrEnum):
    TRUSTED = "trusted"
    FAILED = "failed"
    SUSPECT = "suspect"
    SUPERSEDED = "superseded"
    NOT_PIPELINE_STEP = "not_pipeline_step"


@dataclass(slots=True)
class AgentRequest:
    product: str
    audience: str
    max_segments: int = 5
    segmentation_criteria: list[str] = field(default_factory=list)
    source_policy: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        if not self.product.strip() or not self.audience.strip():
            raise ValueError("product and audience are required")
        if not 1 <= self.max_segments <= 50:
            raise ValueError("max_segments must be between 1 and 50")


@dataclass(slots=True)
class RootJobState:
    job_id: str
    status: str = "created"
    active_segment_id: str | None = None
    segment_cursor: int = 0
    authoring_retry_count: int = 0
    repair_count: int = 0
    evaluated_repair_count: int = 0
    effective_repair_count: int = 0
    last_error: str | None = None
    final_artifact_ref: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION


@dataclass(slots=True)
class JobEvent:
    sequence: int
    event_type: str
    summary: str
    stage: str | None = None
    segment_id: str | None = None
    run_id: str | None = None
    severity: str = "info"
    artifact_refs: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION


@dataclass(slots=True)
class Segment:
    segment_id: str
    name: str
    definition: str
    rank: int
    inclusion_criteria: list[str] = field(default_factory=list)
    exclusion_criteria: list[str] = field(default_factory=list)
    initial_fit_reason: str = ""
    status: str = "pending"


@dataclass(slots=True)
class ContextArtifact:
    ref: str
    content_hash: str
    delivery: str
    purpose: str
    content: Any | None = None


@dataclass(slots=True)
class CodexContextManifest:
    invocation_id: str
    job_type: str
    purpose: str
    artifacts: list[ContextArtifact]
    excluded: list[dict[str, str]] = field(default_factory=list)
    prompt_hash: str = ""
    schema_hash: str = ""
    context_budget: int | None = None
    caused_by_invocation_id: str | None = None
    fresh_session: bool = True
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        if not self.fresh_session:
            raise ValueError("Codex invocations must use fresh sessions")
        for artifact in self.artifacts:
            if artifact.delivery not in {"embedded", "workspace_ref"}:
                raise ValueError(f"unsupported context delivery: {artifact.delivery}")


@dataclass(slots=True)
class CodexUsageRecord:
    invocation_id: str
    purpose: str
    terminal_status: str
    usage_status: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    extra: dict[str, int] = field(default_factory=dict)
    source_event_index: int | None = None
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION


@dataclass(slots=True)
class GeneratedFile:
    path: str
    content: str

    def validate(self) -> None:
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
            raise ValueError(f"unsafe generated Python path: {self.path}")


@dataclass(slots=True)
class GeneratedPipeline:
    entry_file: str
    files: list[GeneratedFile]
    review_boundaries: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        if not self.files:
            raise ValueError("pipeline bundle is empty")
        for item in self.files:
            item.validate()
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("pipeline bundle contains duplicate paths")
        if self.entry_file not in paths:
            raise ValueError("entry_file must be included in files")
        boundary_keys: list[tuple[str, ...]] = []
        for boundary in self.review_boundaries:
            source_path = str(boundary.get("source_path") or "").strip()
            qualified_name = str(
                boundary.get("qualified_function_name") or ""
            ).strip()
            if source_path or qualified_name:
                if not source_path or not qualified_name:
                    raise ValueError(
                        "v2 review boundary requires source_path and qualified_function_name"
                    )
                path = PurePosixPath(source_path.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or not path.parts:
                    raise ValueError("v2 review boundary source_path is unsafe")
                derived_name = qualified_name.split(".")[-1]
                supplied_name = str(boundary.get("function_name") or "").strip()
                if supplied_name and supplied_name != derived_name:
                    raise ValueError(
                        "v2 compatibility function_name disagrees with qualified name"
                    )
                boundary["function_name"] = derived_name
                boundary["source_path"] = path.as_posix()
                boundary["qualified_function_name"] = qualified_name
                boundary_keys.append((path.as_posix(), qualified_name))
                continue
            name = str(boundary.get("function_name") or "").strip()
            if not name:
                raise ValueError("review boundary requires function_name")
            boundary_keys.append((name,))
        if len(boundary_keys) != len(set(boundary_keys)):
            raise ValueError("review boundary identities must be unique")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "GeneratedPipeline":
        pipeline = cls(
            entry_file=str(payload.get("entry_file") or "pipeline.py"),
            files=[GeneratedFile(path=str(item["path"]), content=str(item["content"])) for item in payload.get("files", [])],
            review_boundaries=[],
        )
        for item in payload.get("review_boundaries", []):
            qualified_name = str(item.get("qualified_function_name") or "").strip()
            boundary = {
                "function_name": str(
                    item.get("function_name")
                    or (qualified_name.split(".")[-1] if qualified_name else "")
                ),
                "role": str(item.get("role") or ""),
                "expected_inputs": [
                    str(value) for value in item.get("expected_inputs", [])
                ],
                "expected_outputs": [
                    str(value) for value in item.get("expected_outputs", [])
                ],
            }
            if item.get("semantic_stage") is not None:
                boundary["semantic_stage"] = str(item["semantic_stage"])
            if "boundary_id" in item:
                boundary["boundary_id"] = str(item.get("boundary_id") or "")
            if "source_path" in item or "qualified_function_name" in item:
                boundary["source_path"] = str(item.get("source_path") or "")
                boundary["qualified_function_name"] = qualified_name
            if item.get("function_source_sha256") is not None:
                boundary["function_source_sha256"] = str(
                    item["function_source_sha256"]
                )
            if item.get("job_id") is not None:
                boundary["job_id"] = str(item["job_id"])
            pipeline.review_boundaries.append(boundary)
        pipeline.validate()
        return pipeline


@dataclass(slots=True)
class EtiqNodeRecord:
    node_ref: str
    raw_id: str | None
    names: list[str]
    line_no: int | None
    state_type: str
    value_type: str | None
    func_stack: list[str]
    source: str | None
    scope_type: str | None
    raw_metadata: dict[str, Any]
    value_preview: Any | None = None
    preview_truncated: bool = False
    artifact_kind: str | None = None
    artifact_content: Any | None = None
    artifact_truncated: bool = False
    artifact_size: dict[str, int] | None = None


@dataclass(slots=True)
class EtiqRelationshipRecord:
    relationship_ref: str
    source_ref: str
    target_ref: str
    relationship_type: str
    direction: str
    raw_metadata: dict[str, Any]


@dataclass(slots=True)
class EtiqEvidenceSnapshot:
    snapshot_id: str
    job_id: str
    run_id: str
    nodes: list[EtiqNodeRecord]
    relationships: list[EtiqRelationshipRecord]
    inventories: dict[str, Any]
    scan_errors: list[Any]
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION


@dataclass(slots=True)
class BoundaryHealth:
    grouping_mode: str
    input_count: int
    output_count: int
    invocation_count: int
    ordering_source: str = "pending"
    findings: list[str] = field(default_factory=list)
    degraded: bool = False


@dataclass(slots=True)
class EvidenceReviewUnit:
    unit_id: str
    run_id: str
    function_name: str
    func_stack_prefix: list[str]
    node_refs: list[str]
    relationship_refs: list[str]
    input_relationship_refs: list[str]
    output_relationship_refs: list[str]
    helper_prefixes: list[list[str]]
    boundary_health: BoundaryHealth
    nesting_summary: dict[str, Any] = field(default_factory=dict)
    upstream_unit_ids: list[str] = field(default_factory=list)
    downstream_unit_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReviewSection:
    section_id: str
    section_index: int
    assigned_unit_ids: list[str]
    context_unit_ids: list[str]
    start_ordinal: int
    end_ordinal: int
    excluded_context_unit_ids: list[str] = field(default_factory=list)
    construction_summary: dict[str, Any] = field(default_factory=dict)
    section_input_hash: str = ""


@dataclass(slots=True)
class ReviewDecision:
    unit_id: str
    decision: str
    decision_reason: str
    evidence_refs: list[str]
    reviewer_type: str = "codex"
    trust_level: str | None = None
    criteria_outcomes: list[dict[str, Any]] = field(default_factory=list)
    boundary_health_acknowledged: bool = False
    expand_helper_prefixes: list[list[str]] = field(default_factory=list)
    inspect_artifacts: list[dict[str, Any]] = field(default_factory=list)
    suspect_node_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TrustAnnotation:
    annotation_id: str
    unit_id: str
    status: str
    authority: str
    review_job_id: str
    run_id: str
    receipt_ref: str
    evidence_refs: list[str]
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION


@dataclass(slots=True)
class ReviewReceipt:
    receipt_id: str
    section_id: str
    section_input_hash: str
    result: str
    reviewed_unit_ids: list[str]
    reusable_trusted_unit_ids: list[str]
    non_pipeline_unit_ids: list[str]
    failed_or_suspect_unit_ids: list[str]
    invalidated_unit_ids: list[str]
    suspect_node_refs: list[str]
    errors: list[str]
    next_action: str
    created_at: str = field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION
