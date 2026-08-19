"""Inject faults into a generated pipeline with ground truth known by construction.

Trust labels in this system are produced by one model reviewing another, so no part
of the loop knows which boundary is actually wrong. A fault injected into a named
boundary supplies that missing answer, which turns a trust signal from something the
system relies on into something that can be scored.

Faults are applied through the same scope machinery a repair uses, so an injected
fault is localised to exactly one boundary rather than merely asserted to be.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from .controlled_experiment import replace_scope
from .records import GeneratedPipeline
from .repair import source_scope

Transform = Callable[[ast.FunctionDef | ast.AsyncFunctionDef, str], None]


@dataclass(frozen=True)
class Fault:
    name: str
    fault_class: str
    provenance: str
    description: str
    transform: Transform = field(repr=False)


@dataclass(frozen=True)
class GroundTruth:
    fault_class: str
    injected_function: str
    parameter: str
    contaminated_functions: list[str]

    @property
    def affected_functions(self) -> list[str]:
        return [self.injected_function, *self.contaminated_functions]


@dataclass(frozen=True)
class InjectedPipeline:
    pipeline: GeneratedPipeline
    ground_truth: GroundTruth


def _entry_source(pipeline: GeneratedPipeline) -> str:
    for item in pipeline.files:
        if item.path == pipeline.entry_file:
            return item.content
    raise ValueError(f"entry file missing from pipeline: {pipeline.entry_file}")


def _definition_order(source: str) -> list[str]:
    return [
        node.name
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _dataflow_edges(source: str) -> set[tuple[str, str]]:
    """Edges producer -> consumer, read from module-level dataflow.

    A consumer is downstream when the producer's result reaches its arguments, either
    directly as a nested call or through a module-level name bound to that result.
    """
    tree = ast.parse(source)
    carries: dict[str, set[str]] = {}
    edges: set[tuple[str, str]] = set()

    def contributors(node: ast.AST) -> set[str]:
        found: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in carries:
                found |= carries[sub.id]
            elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                found.add(sub.func.id)
        return found

    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for call in [
            node
            for node in ast.walk(statement)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]:
            upstream: set[str] = set()
            for argument in [*call.args, *(keyword.value for keyword in call.keywords)]:
                upstream |= contributors(argument)
            for producer in upstream:
                if producer != call.func.id:
                    edges.add((producer, call.func.id))
        if isinstance(statement, ast.Assign):
            produced = contributors(statement.value)
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    carries[target.id] = produced
    return edges


def downstream_functions(pipeline: GeneratedPipeline, function_name: str) -> list[str]:
    """Every function the named function's output reaches, in definition order."""
    source = _entry_source(pipeline)
    edges = _dataflow_edges(source)
    reached: set[str] = set()
    queue: deque[str] = deque([function_name])
    while queue:
        current = queue.popleft()
        for producer, consumer in edges:
            if producer == current and consumer not in reached:
                reached.add(consumer)
                queue.append(consumer)
    reached.discard(function_name)
    return [name for name in _definition_order(source) if name in reached]


class _DropField(ast.NodeTransformer):
    def __init__(self, key: str) -> None:
        self.key = key

    def visit_Dict(self, node: ast.Dict) -> ast.Dict:
        self.generic_visit(node)
        kept = [
            (key, value)
            for key, value in zip(node.keys, node.values)
            if not (isinstance(key, ast.Constant) and key.value == self.key)
        ]
        node.keys = [key for key, _ in kept]
        node.values = [value for _, value in kept]
        return node


class _TruncateSequence(ast.NodeTransformer):
    def __init__(self, _parameter: str) -> None:
        self.done = False

    def visit_List(self, node: ast.List) -> ast.List:
        self.generic_visit(node)
        if not self.done and len(node.elts) > 1:
            node.elts = node.elts[:1]
            self.done = True
        return node


class _FabricateIdentifier(ast.NodeTransformer):
    """Replace identifier values with a plausible placeholder.

    Dict keys are left alone. Rewriting them would change the record's shape, which
    a schema check catches for the wrong reason; the point of this fault is that the
    output stays structurally valid while carrying an invented value.
    """

    def __init__(self, replacement: str) -> None:
        self.replacement = replacement

    def visit_Dict(self, node: ast.Dict) -> ast.Dict:
        node.values = [self.visit(value) for value in node.values]
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str) and node.value:
            return ast.Constant(value=self.replacement)
        return node


class _InvertComparison(ast.NodeTransformer):
    FLIP = {
        ast.Lt: ast.GtE,
        ast.LtE: ast.Gt,
        ast.Gt: ast.LtE,
        ast.GtE: ast.Lt,
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
    }

    def __init__(self, _parameter: str) -> None:
        pass

    def visit_Compare(self, node: ast.Compare) -> ast.Compare:
        self.generic_visit(node)
        node.ops = [
            self.FLIP[type(op)]() if type(op) in self.FLIP else op for op in node.ops
        ]
        return node


class _DropSortStability(ast.NodeTransformer):
    """Reverse an ordering, which is invisible in every field-level check."""

    def __init__(self, _parameter: str) -> None:
        pass

    def visit_Call(self, node: ast.Call) -> ast.Call:
        self.generic_visit(node)
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name == "sorted":
            node.keywords = [
                keyword for keyword in node.keywords if keyword.arg != "reverse"
            ]
            node.keywords.append(
                ast.keyword(arg="reverse", value=ast.Constant(value=True))
            )
        return node


def _transformer(builder: type[ast.NodeTransformer]) -> Transform:
    def apply(function: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str) -> None:
        builder(parameter).visit(function)  # type: ignore[call-arg]

    return apply


FAULT_CATALOGUE: dict[str, Fault] = {
    "drop_field": Fault(
        name="drop_field",
        fault_class="drop_field",
        provenance="observed",
        description=(
            "A key disappears from the stage output. Observed when upstream source "
            "reads failed and the stage emitted a record without them."
        ),
        transform=_transformer(_DropField),
    ),
    "truncate_sequence": Fault(
        name="truncate_sequence",
        fault_class="truncate_sequence",
        provenance="observed",
        description=(
            "A collected sequence is shortened while the stage still reports success. "
            "Observed when source reads returned 429, 403 and 500."
        ),
        transform=_transformer(_TruncateSequence),
    ),
    "fabricate_identifier": Fault(
        name="fabricate_identifier",
        fault_class="fabricate_identifier",
        provenance="observed",
        description=(
            "An identifier is replaced by a plausible placeholder. Observed when a "
            "worker returned schema-valid output carrying invented need IDs."
        ),
        transform=_transformer(_FabricateIdentifier),
    ),
    "invert_comparison": Fault(
        name="invert_comparison",
        fault_class="invert_comparison",
        provenance="synthetic",
        description="A comparison operator is flipped, inverting a filter or gate.",
        transform=_transformer(_InvertComparison),
    ),
    "reverse_ordering": Fault(
        name="reverse_ordering",
        fault_class="reverse_ordering",
        provenance="synthetic",
        description="A ranking is reversed while every value stays present and valid.",
        transform=_transformer(_DropSortStability),
    ),
}


def inject(
    pipeline: GeneratedPipeline,
    fault: Fault,
    *,
    target: str,
    parameter: str = "",
) -> InjectedPipeline:
    """Apply one fault to one boundary and record what it contaminates."""
    scope = source_scope(pipeline, function_name=target, mode="boundary")
    if scope.get("scope_kind") != "function":
        raise ValueError(f"fault target does not resolve to a function: {target!r}")

    source = _entry_source(pipeline)
    original = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == target
    )
    before = ast.unparse(original)
    fault.transform(original, parameter)
    after = ast.unparse(ast.fix_missing_locations(original))
    if before == after:
        raise ValueError(
            f"fault {fault.name!r} changed nothing at {target!r}; an undetectable "
            "fault would score every trust signal as a false negative"
        )

    mutated = replace_scope(pipeline, scope, after)
    return InjectedPipeline(
        pipeline=mutated,
        ground_truth=GroundTruth(
            fault_class=fault.fault_class,
            injected_function=target,
            parameter=parameter,
            contaminated_functions=downstream_functions(pipeline, target),
        ),
    )
