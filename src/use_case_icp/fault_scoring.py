"""Score a trust signal against a fault whose location is known.

A detector labels every boundary trusted or suspect. Scoring compares those labels
with the injected ground truth, which separates two failures the system currently
cannot tell apart: trusting a poisoned boundary, and resuming from the wrong place.
"""

from __future__ import annotations

import ast
import contextlib
import io
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .fault_injection import GroundTruth
from .records import GeneratedPipeline

TRUSTED = "trusted"
SUSPECT = "suspect"

_DEFINITION_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Import,
    ast.ImportFrom,
)


def capture_stage_outputs(
    pipeline: GeneratedPipeline,
    boundaries: list[str],
) -> dict[str, Any]:
    """Run the pipeline and record what each boundary returned.

    Definitions execute first so the boundary functions can be wrapped, then the
    module-level code runs against the wrapped versions. This is a small stand-in
    for the scanner's capture, so the harness runs without the scanner installed.
    """
    source = next(
        item.content for item in pipeline.files if item.path == pipeline.entry_file
    )
    tree = ast.parse(source)
    definitions = [node for node in tree.body if isinstance(node, _DEFINITION_NODES)]
    remainder = [node for node in tree.body if not isinstance(node, _DEFINITION_NODES)]

    namespace: dict[str, Any] = {"__name__": "__pipeline__"}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), pipeline.entry_file, "exec"), namespace)

    outputs: dict[str, Any] = {}

    def wrap(name: str, function: Any) -> Any:
        def recorded(*args: Any, **kwargs: Any) -> Any:
            value = function(*args, **kwargs)
            outputs[name] = value
            return value

        return recorded

    for name in boundaries:
        if callable(namespace.get(name)):
            namespace[name] = wrap(name, namespace[name])

    with contextlib.redirect_stdout(io.StringIO()):
        exec(
            compile(ast.Module(body=remainder, type_ignores=[]), pipeline.entry_file, "exec"),
            namespace,
        )
    return outputs


class Detector(Protocol):
    def label(
        self,
        boundaries: list[str],
        outputs: Mapping[str, Any],
    ) -> dict[str, str]: ...


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


class SchemaDetector:
    """Structural validation of a stage output against its declared JSON schema."""

    def __init__(self, schemas: Mapping[str, Mapping[str, Any]]) -> None:
        self.schemas = schemas

    def _violations(self, schema: Mapping[str, Any], value: Any) -> list[str]:
        problems: list[str] = []
        expected = schema.get("type")
        if isinstance(expected, str) and not _json_type_matches(value, expected):
            problems.append(f"expected {expected}")
            return problems
        if isinstance(value, dict):
            for required in schema.get("required", []):
                if required not in value:
                    problems.append(f"missing required field {required}")
            for name, subschema in (schema.get("properties") or {}).items():
                if name in value:
                    problems.extend(self._violations(subschema, value[name]))
        return problems

    def label(
        self,
        boundaries: list[str],
        outputs: Mapping[str, Any],
    ) -> dict[str, str]:
        labels: dict[str, str] = {}
        for name in boundaries:
            schema = self.schemas.get(name)
            if schema is None or name not in outputs:
                labels[name] = TRUSTED
                continue
            labels[name] = SUSPECT if self._violations(schema, outputs[name]) else TRUSTED
        return labels


@dataclass(frozen=True)
class Contract:
    """Acceptance criteria attached to a boundary, checked on its captured output."""

    function: str
    required_fields: list[str] = field(default_factory=list)
    min_items: dict[str, int] = field(default_factory=dict)
    field_pattern: dict[str, str] = field(default_factory=dict)
    ordered: bool = False


class ContractDetector:
    """Content validation against invariants the boundary declared in advance."""

    def __init__(self, contracts: Mapping[str, Contract]) -> None:
        self.contracts = contracts

    def _violations(self, contract: Contract, value: Any) -> list[str]:
        problems: list[str] = []
        for name in contract.required_fields:
            if not isinstance(value, dict) or name not in value:
                problems.append(f"missing required field {name}")
        for name, minimum in contract.min_items.items():
            items = value.get(name) if isinstance(value, dict) else None
            if not isinstance(items, (list, tuple)) or len(items) < minimum:
                problems.append(f"{name} holds fewer than {minimum} items")
        for name, pattern in contract.field_pattern.items():
            items = value.get(name) if isinstance(value, dict) else value
            candidates = items if isinstance(items, (list, tuple)) else [items]
            for item in candidates:
                if not isinstance(item, str) or not re.fullmatch(pattern, item):
                    problems.append(f"{name} carries a value outside {pattern}")
                    break
        if contract.ordered:
            items = value if isinstance(value, (list, tuple)) else None
            if items is not None and list(items) != sorted(items):
                problems.append("sequence is not in order")
        return problems

    def label(
        self,
        boundaries: list[str],
        outputs: Mapping[str, Any],
    ) -> dict[str, str]:
        labels: dict[str, str] = {}
        for name in boundaries:
            contract = self.contracts.get(name)
            if contract is None or name not in outputs:
                labels[name] = TRUSTED
                continue
            labels[name] = SUSPECT if self._violations(contract, outputs[name]) else TRUSTED
        return labels


@dataclass(frozen=True)
class Score:
    false_trust: bool
    false_suspects: list[str]
    resume_function: str | None
    localisation_error: int | None
    shipped_contaminated_output: bool


def score(
    ground_truth: GroundTruth,
    boundaries: list[str],
    labels: Mapping[str, str],
) -> Score:
    """Compare one detector's labels with the injected fault.

    The resume point is the earliest suspect boundary, which is where a run that
    trusted these labels would restart. A negative localisation error means it
    restarts upstream of the fault and redoes sound work. A positive one means it
    restarts past the fault and keeps output the fault already contaminated.
    """
    injected = ground_truth.injected_function
    if injected not in boundaries:
        raise ValueError(f"injected boundary is not in the boundary list: {injected!r}")

    suspects = [name for name in boundaries if labels.get(name) == SUSPECT]
    clean = set(boundaries) - set(ground_truth.affected_functions)
    false_suspects = [name for name in suspects if name in clean]

    resume = suspects[0] if suspects else None
    if resume is None:
        return Score(
            false_trust=True,
            false_suspects=false_suspects,
            resume_function=None,
            localisation_error=None,
            shipped_contaminated_output=True,
        )

    error = boundaries.index(resume) - boundaries.index(injected)
    return Score(
        false_trust=labels.get(injected) != SUSPECT,
        false_suspects=false_suspects,
        resume_function=resume,
        localisation_error=error,
        shipped_contaminated_output=error > 0,
    )
