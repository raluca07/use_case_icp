"""Versioned v2 trace and private truth records; v1 remains loadable unchanged."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rdr.trace import Call, Trace, Write
from rdr.truth import Truth


@dataclass
class CallV2:
    index: int
    app: str
    api: str
    args: dict
    raw_response: object
    observed_response: object
    writes: list[Write] = field(default_factory=list)
    group_ids: list[str] = field(default_factory=list)
    source_span: str | None = None
    invocation_stack: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.app}.{self.api}"


@dataclass
class TraceV2:
    task_id: str
    instruction: str
    final_message: str
    calls: list[CallV2]
    source: dict[str, str]
    schema_version: int = 2
    author: str = "dataset"

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("TraceV2 requires schema_version=2")
        if self.author not in {"dataset", "codex"}:
            raise ValueError("author must be dataset or codex")
        indices = [call.index for call in self.calls]
        if len(indices) != len(set(indices)) or indices != sorted(indices):
            raise ValueError("call indices must be unique and increasing")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_v1_observed(self) -> Trace:
        return Trace(
            self.task_id,
            self.instruction,
            self.final_message,
            [
                Call(
                    call.index,
                    call.app,
                    call.api,
                    call.args,
                    call.observed_response,
                    call.writes,
                )
                for call in self.calls
            ],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "TraceV2":
        calls = []
        for call in data["calls"]:
            calls.append(
                CallV2(
                    call["index"],
                    call["app"],
                    call["api"],
                    call["args"],
                    call["raw_response"],
                    call["observed_response"],
                    [Write(**write) for write in call.get("writes", [])],
                    call.get("group_ids", []),
                    call.get("source_span"),
                    call.get("invocation_stack", []),
                )
            )
        return cls(
            data["task_id"],
            data["instruction"],
            data["final_message"],
            calls,
            data.get("source", {}),
            data.get("schema_version", 2),
            data.get("author", "dataset"),
        )


@dataclass
class TruthV2:
    instance_id: str
    fault_occurred: bool
    residual_harm_present: bool
    fault_id: str | None
    fault_class: str | None
    repair: str | None
    root_cause_source_locations: list[str]
    root_cause_event_indices: list[int]
    historically_affected_artifacts: list[str]
    restored_artifacts: list[str]
    residual_harmful_artifacts: list[str]
    symptom: str
    author: str
    injection_channel: str | None = None
    task_cluster: str | None = None
    generator_cluster: str | None = None
    trace_sha256: str | None = None
    task_input_sha256: str | None = None
    source_sha256: str | None = None
    schema_version: int = 4

    def __post_init__(self) -> None:
        classes = {"action", "source", "runtime", "mixed", "interaction", "amplified"}
        if self.fault_occurred:
            if self.fault_class not in classes or self.repair not in {"repaired", "unrepaired"}:
                raise ValueError("faulty truth requires a v2 class and binary repair value")
            if not self.fault_id:
                raise ValueError("faulty truth requires fault_id")
        elif any((self.fault_id, self.fault_class, self.repair)):
            raise ValueError("clean truth cannot carry fault metadata")
        if not self.fault_occurred and self.residual_harm_present:
            raise ValueError("clean truth cannot carry residual harm")
        if not self.fault_occurred and any((self.root_cause_source_locations,
                                            self.root_cause_event_indices,
                                            self.historically_affected_artifacts,
                                            self.restored_artifacts,
                                            self.residual_harmful_artifacts)):
            raise ValueError("clean truth cannot carry causal fault evidence")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TruthV2":
        legacy_version = data.get("schema_version", 1)
        if "fault_present" in data:
            legacy = dict(data)
            occurred = legacy.pop("fault_present")
            affected = legacy.pop("affected_artifacts", [])
            legacy.update(
                fault_occurred=occurred,
                residual_harm_present=occurred,
                historically_affected_artifacts=affected,
                restored_artifacts=[],
                residual_harmful_artifacts=affected,
                trace_sha256=None,
            )
            data = legacy
        if "source_locations" in data or "runtime_events" in data or "first_harmful_event" in data:
            legacy = dict(data)
            legacy["root_cause_source_locations"] = legacy.pop("source_locations", [])
            legacy["root_cause_event_indices"] = legacy.pop("runtime_events", [])
            legacy.pop("first_harmful_event", None)
            legacy["schema_version"] = 4
            data = legacy
        elif legacy_version < 4:
            raise ValueError("legacy TruthV2 lacks explicit root-cause evidence fields")
        return cls(**data)


def save_v2(value: TraceV2 | TruthV2, path: Path) -> None:
    path.write_text(json.dumps(value.to_dict(), indent=2, sort_keys=True))


def load_trace(path: Path) -> Trace | TraceV2:
    data = json.loads(path.read_text())
    return TraceV2.from_dict(data) if data.get("schema_version") == 2 else Trace.from_dict(data)


def load_truth(path: Path) -> Truth | TruthV2:
    data = json.loads(path.read_text())
    return TruthV2.from_dict(data) if data.get("schema_version", 1) >= 2 else Truth(**data)


def with_observed_response(trace: TraceV2, index: int, observed: object) -> TraceV2:
    """Return a trace where raw service truth is retained and only the workflow observation changes."""
    data = trace.to_dict()
    call = next(call for call in data["calls"] if call["index"] == index)
    call["observed_response"] = observed
    return TraceV2.from_dict(data)


def from_v1_trace(
    trace: Trace,
    source: dict[str, str],
    author: str = "dataset",
    observed_responses: dict[int, object] | None = None,
) -> TraceV2:
    """Promote a captured v1 trace while explicitly retaining raw and workflow-observed responses."""
    observed_responses = observed_responses or {}
    return TraceV2(
        trace.task_id,
        trace.instruction,
        trace.final_message,
        [
            CallV2(
                call.index,
                call.app,
                call.api,
                call.args,
                call.response,
                observed_responses.get(call.index, call.response),
                call.writes,
            )
            for call in trace.calls
        ],
        source,
        author=author,
    )
