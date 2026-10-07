"""Deterministic, construction-time fault injection for fresh experiment chains.

This module starts from the supplied workshop injector, but makes a mutation site
an explicit, seeded occurrence and treats the injected function as the primary
localisation truth.  Clean source, candidate details, validation, and the returned
ground-truth manifest are controller-only artifacts; reviewer packages must never
receive them.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import textwrap
import tokenize
from io import StringIO
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .controlled_experiment import replace_scope
from .fault_experiment import PROTOCOL_CONTENT_HASH, PROTOCOL_VERSION
from .records import EtiqEvidenceSnapshot, GeneratedFile, GeneratedPipeline
from .repair import source_scope
from .review import frame_name


SUPPORTED_FAULTS = (
    "drop_field",
    "truncate_sequence",
    "fabricate_identifier",
    "invert_comparison",
    "reverse_ordering",
)
PROVENANCE = {
    "drop_field": "observed-inspired",
    "truncate_sequence": "observed-inspired",
    "fabricate_identifier": "observed-inspired",
    "invert_comparison": "synthetic",
    "reverse_ordering": "synthetic",
}
COMPARISON_FLIPS: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}
REQUIRED_VALIDATION_FLAGS = (
    "compile_success",
    "execution_success",
    "schema_valid",
    "mutated_statement_executed",
    "plausible_final_result",
    "semantic_oracle_failed",
)


@dataclass(frozen=True)
class Fault:
    name: str
    fault_class: str
    provenance: str
    description: str


@dataclass(frozen=True)
class FaultSelection:
    fault_class: str
    function_name: str
    occurrence: int
    parameter: str = ""
    seed: int = 0
    job_id: str = ""


@dataclass(frozen=True)
class MutationSite:
    file: str
    function_name: str
    helper: bool
    original_span: dict[str, int]
    mutant_span: dict[str, int]
    ast_operator: str
    occurrence: int
    candidate_count: int
    original_snippet: str
    mutant_snippet: str
    original_snippet_sha256: str
    mutant_snippet_sha256: str


@dataclass(frozen=True)
class GroundTruth:
    fault_class: str
    provenance: str
    injected_function: str
    injected_job_id: str
    parameter: str
    seed: int
    site: MutationSite
    clean_bundle_sha256: str
    mutant_bundle_sha256: str
    clean_function_sha256: str
    mutant_function_sha256: str
    normalized_formatting: bool = True
    primary_localisation_truth: str = "injected_function"
    downstream_contamination: list[str] = field(default_factory=list)
    captured_fault_node_refs: list[str] = field(default_factory=list)
    capture_snapshot_ids: list[str] = field(default_factory=list)
    capture_finalized: bool = False
    validation: dict[str, Any] = field(default_factory=dict)

    @property
    def affected_functions(self) -> list[str]:
        """Compatibility view; contamination is diagnostic, never scoring truth."""
        return [self.injected_function, *self.downstream_contamination]

    def manifest(self, *, final: bool = False) -> dict[str, Any]:
        if any(self.validation.get(name) is not True for name in REQUIRED_VALIDATION_FLAGS):
            raise ValueError("ground-truth manifest requires an accepted validation log")
        if not self.injected_job_id:
            raise ValueError("ground-truth manifest requires a frozen injected job ID")
        if final and not self.capture_finalized:
            raise ValueError("final ground-truth manifest requires post-capture resolution")
        value = asdict(self)
        value.update(
            {
                "schema_version": "1",
                "protocol_version": PROTOCOL_VERSION,
                "protocol_content_hash": PROTOCOL_CONTENT_HASH,
                "storage_classification": "restricted_controller_only",
                "protocol_decision": "inject_single_fault",
                "manifest_status": (
                    "finalized_post_capture" if self.capture_finalized else "draft_pre_capture"
                ),
            }
        )
        return value


@dataclass(frozen=True)
class InjectedPipeline:
    pipeline: GeneratedPipeline
    clean_pipeline: GeneratedPipeline = field(repr=False)
    ground_truth: GroundTruth


@dataclass(frozen=True)
class InjectionOutcome:
    """Controller state retained from clean acceptance through D09 capture."""

    evaluation_pipeline: GeneratedPipeline
    protocol_decision: dict[str, Any]
    clean_execution: dict[str, Any]
    candidate_records: list[dict[str, Any]] = field(default_factory=list)
    rejection_records: list[dict[str, Any]] = field(default_factory=list)
    injector_output: dict[str, Any] = field(default_factory=dict)
    injected: InjectedPipeline | None = field(default=None, repr=False)


FAULT_CATALOGUE: dict[str, Fault] = {
    "drop_field": Fault(
        "drop_field",
        "drop_field",
        PROVENANCE["drop_field"],
        "Remove one selected literal dictionary field.",
    ),
    "truncate_sequence": Fault(
        "truncate_sequence",
        "truncate_sequence",
        PROVENANCE["truncate_sequence"],
        "Shorten one selected literal sequence while preserving its type.",
    ),
    "fabricate_identifier": Fault(
        "fabricate_identifier",
        "fabricate_identifier",
        PROVENANCE["fabricate_identifier"],
        "Replace one selected string value with a plausible identifier.",
    ),
    "invert_comparison": Fault(
        "invert_comparison",
        "invert_comparison",
        PROVENANCE["invert_comparison"],
        "Flip one selected comparison operator.",
    ),
    "reverse_ordering": Fault(
        "reverse_ordering",
        "reverse_ordering",
        PROVENANCE["reverse_ordering"],
        "Toggle reverse ordering on one selected sorted call.",
    ),
}


def _sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _bundle_sha256(pipeline: GeneratedPipeline) -> str:
    payload = {
        "entry_file": pipeline.entry_file,
        "files": [
            {"path": item.path, "content": item.content}
            for item in sorted(pipeline.files, key=lambda item: item.path)
        ],
        "review_boundaries": pipeline.review_boundaries,
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def normalize_pipeline(pipeline: GeneratedPipeline) -> GeneratedPipeline:
    """Canonicalize Python formatting before retaining either clean or mutant."""
    files = []
    for item in pipeline.files:
        tree = ast.parse(item.content, filename=item.path)
        content = ast.unparse(ast.fix_missing_locations(tree)).rstrip() + "\n"
        compile(content, item.path, "exec")
        files.append(GeneratedFile(item.path, content))
    normalized = GeneratedPipeline(
        pipeline.entry_file, files, deepcopy(pipeline.review_boundaries)
    )
    normalized.validate()
    return normalized


def _target_function(
    pipeline: GeneratedPipeline, function_name: str
) -> tuple[dict[str, Any], str, ast.FunctionDef | ast.AsyncFunctionDef]:
    scope = source_scope(pipeline, function_name=function_name, mode="boundary")
    if scope.get("scope_kind") != "function":
        raise ValueError(f"fault target does not resolve to a function: {function_name!r}")
    source = next(item.content for item in pipeline.files if item.path == scope["file"])
    matches = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
        and node.lineno == scope["start_line"]
    ]
    if len(matches) != 1:
        raise ValueError(f"fault target is ambiguous: {function_name!r}")
    return scope, source, matches[0]


def _scope_nodes(root: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterable[ast.AST]:
    """Walk a function but not definitions nested below the selected function."""
    stack: list[ast.AST] = list(reversed(root.body))
    while stack:
        node = stack.pop()
        yield node
        children: list[ast.AST] = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            children.append(child)
        stack.extend(reversed(children))


def _parent_map(root: ast.AST) -> dict[int, ast.AST]:
    return {
        id(child): parent
        for parent in ast.walk(root)
        for child in ast.iter_child_nodes(parent)
    }


def _candidates(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    fault_class: str,
    parameter: str,
) -> list[tuple[ast.AST, Any]]:
    nodes = list(_scope_nodes(function))
    parents = _parent_map(function)
    found: list[tuple[ast.AST, Any]] = []
    if fault_class == "drop_field":
        for node in nodes:
            if not isinstance(node, ast.Dict):
                continue
            for index, key in enumerate(node.keys):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if not parameter or key.value == parameter:
                        found.append((node, index))
    elif fault_class == "truncate_sequence":
        found = [(node, None) for node in nodes if isinstance(node, ast.List) and len(node.elts) > 1]
    elif fault_class == "fabricate_identifier":
        if not parameter:
            raise ValueError("fabricate_identifier requires a non-empty replacement parameter")
        for node in nodes:
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or not node.value:
                continue
            parent = parents.get(id(node))
            if isinstance(parent, ast.Dict) and node in parent.keys:
                continue
            if isinstance(parent, ast.Expr) and function.body and parent is function.body[0]:
                continue
            found.append((node, None))
    elif fault_class == "invert_comparison":
        for node in nodes:
            if isinstance(node, ast.Compare):
                for index, operator in enumerate(node.ops):
                    if type(operator) in COMPARISON_FLIPS:
                        found.append((node, index))
    elif fault_class == "reverse_ordering":
        found = [
            (node, None)
            for node in nodes
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sorted"
        ]
    else:
        raise ValueError(f"unknown fault class: {fault_class!r}")
    return found


def enumerate_candidates(
    pipeline: GeneratedPipeline,
    *,
    fault_class: str,
    function_name: str,
    parameter: str = "",
) -> list[dict[str, Any]]:
    """Return restricted candidate metadata in deterministic source order."""
    normalized = normalize_pipeline(pipeline)
    scope, source, function = _target_function(normalized, function_name)
    result = []
    for occurrence, (node, detail) in enumerate(_candidates(function, fault_class, parameter)):
        result.append(
            {
                "file": scope["file"],
                "function_name": function_name,
                "occurrence": occurrence,
                "ast_operator": _operator_name(fault_class, node, detail),
                "source_span": _site_span(fault_class, node, detail),
                "snippet": ast.get_source_segment(source, node) or ast.unparse(node),
            }
        )
    return result


def _span(node: ast.AST) -> dict[str, int]:
    return {
        "start_line": int(node.lineno),
        "start_column": int(node.col_offset),
        "end_line": int(getattr(node, "end_lineno", node.lineno)),
        "end_column": int(getattr(node, "end_col_offset", node.col_offset)),
    }


def _site_span(fault_class: str, node: ast.AST, detail: Any) -> dict[str, int]:
    if fault_class == "drop_field":
        assert isinstance(node, ast.Dict)
        key = node.keys[int(detail)]
        value = node.values[int(detail)]
        return {
            "start_line": int(key.lineno),
            "start_column": int(key.col_offset),
            "end_line": int(getattr(value, "end_lineno", value.lineno)),
            "end_column": int(getattr(value, "end_col_offset", value.col_offset)),
        }
    if fault_class == "invert_comparison":
        assert isinstance(node, ast.Compare)
        index = int(detail)
        left = node.left if index == 0 else node.comparators[index - 1]
        right = node.comparators[index]
        return {
            "start_line": int(getattr(left, "end_lineno", left.lineno)),
            "start_column": int(getattr(left, "end_col_offset", left.col_offset)),
            "end_line": int(right.lineno),
            "end_column": int(right.col_offset),
        }
    return _span(node)


def _operator_name(fault_class: str, node: ast.AST, detail: Any) -> str:
    if fault_class == "drop_field":
        assert isinstance(node, ast.Dict)
        key = node.keys[int(detail)]
        return f"DictField[{ast.literal_eval(key)!r}]"
    if fault_class == "truncate_sequence":
        return "ListTruncation"
    if fault_class == "fabricate_identifier":
        return "StringConstantReplacement"
    if fault_class == "invert_comparison":
        assert isinstance(node, ast.Compare)
        old = type(node.ops[int(detail)])
        return f"{old.__name__}->{COMPARISON_FLIPS[old].__name__}"
    return "sorted(reverse=toggle)"


def _indented_function_source(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    return textwrap.indent(ast.unparse(function), " " * int(function.col_offset))


def _position(source: str, offset: int, file_start_line: int) -> tuple[int, int]:
    prefix = source[:offset]
    return file_start_line + prefix.count("\n"), len(prefix.rsplit("\n", 1)[-1])


def _source_offset(source: str, position: tuple[int, int]) -> int:
    lines = source.splitlines(keepends=True)
    return sum(len(line) for line in lines[: position[0] - 1]) + position[1]


def _tokens(source: str) -> list[tokenize.TokenInfo]:
    return [
        token
        for token in tokenize.generate_tokens(StringIO(source).readline)
        if token.type != tokenize.ENDMARKER
    ]


def _token_region(
    source: str, tokens: list[tokenize.TokenInfo], start: int, end: int
) -> tuple[int, int]:
    if start < end:
        return (
            _source_offset(source, tokens[start].start),
            _source_offset(source, tokens[end - 1].end),
        )
    if start < len(tokens):
        anchor = _source_offset(source, tokens[start].start)
    elif tokens:
        anchor = _source_offset(source, tokens[-1].end)
    else:
        anchor = 0
    return anchor, anchor


def _changed_source_regions(
    original: str, mutant: str, *, file_start_line: int
) -> tuple[dict[str, int], dict[str, int], str, str]:
    original_tokens = _tokens(original)
    mutant_tokens = _tokens(mutant)
    changes = [
        opcode
        for opcode in difflib.SequenceMatcher(
            a=[(token.type, token.string) for token in original_tokens],
            b=[(token.type, token.string) for token in mutant_tokens],
        ).get_opcodes()
        if opcode[0] != "equal"
    ]
    if len(changes) != 1:
        raise ValueError(
            "fault mutation must produce exactly one contiguous normalized source change; "
            f"observed {len(changes)}"
        )
    _, old_token_start, old_token_end, new_token_start, new_token_end = changes[0]
    old_start, old_end = _token_region(
        original, original_tokens, old_token_start, old_token_end
    )
    new_start, new_end = _token_region(
        mutant, mutant_tokens, new_token_start, new_token_end
    )
    old_start_position = _position(original, old_start, file_start_line)
    old_end_position = _position(original, old_end, file_start_line)
    new_start_position = _position(mutant, new_start, file_start_line)
    new_end_position = _position(mutant, new_end, file_start_line)
    return (
        {
            "start_line": old_start_position[0],
            "start_column": old_start_position[1],
            "end_line": old_end_position[0],
            "end_column": old_end_position[1],
        },
        {
            "start_line": new_start_position[0],
            "start_column": new_start_position[1],
            "end_line": new_end_position[0],
            "end_column": new_end_position[1],
        },
        original[old_start:old_end],
        mutant[new_start:new_end],
    )


def _mutate(fault_class: str, node: ast.AST, detail: Any, parameter: str) -> None:
    if fault_class == "drop_field":
        assert isinstance(node, ast.Dict)
        index = int(detail)
        del node.keys[index]
        del node.values[index]
    elif fault_class == "truncate_sequence":
        assert isinstance(node, ast.List)
        node.elts = node.elts[:1]
    elif fault_class == "fabricate_identifier":
        assert isinstance(node, ast.Constant)
        node.value = parameter
    elif fault_class == "invert_comparison":
        assert isinstance(node, ast.Compare)
        index = int(detail)
        node.ops[index] = COMPARISON_FLIPS[type(node.ops[index])]()
    elif fault_class == "reverse_ordering":
        assert isinstance(node, ast.Call)
        reverse = next((item for item in node.keywords if item.arg == "reverse"), None)
        if reverse is None:
            node.keywords.append(ast.keyword(arg="reverse", value=ast.Constant(True)))
        elif isinstance(reverse.value, ast.Constant) and isinstance(reverse.value.value, bool):
            reverse.value.value = not reverse.value.value
        else:
            raise ValueError("selected sorted call has a non-literal reverse argument")


def inject(
    pipeline: GeneratedPipeline,
    fault: Fault | str,
    *,
    target: str,
    parameter: str = "",
    occurrence: int = 0,
    seed: int = 0,
    job_id: str = "",
) -> InjectedPipeline:
    """Normalize a fresh chain and mutate exactly one selected AST occurrence."""
    fault_class = fault.fault_class if isinstance(fault, Fault) else str(fault)
    if fault_class not in FAULT_CATALOGUE:
        raise ValueError(f"unknown fault class: {fault_class!r}")
    clean = normalize_pipeline(pipeline)
    scope, source, original_function = _target_function(clean, target)
    function = deepcopy(original_function)
    candidates = _candidates(function, fault_class, parameter)
    if occurrence < 0 or occurrence >= len(candidates):
        raise ValueError(
            f"fault {fault_class!r} occurrence {occurrence} is unavailable in "
            f"{target!r}; candidate count is {len(candidates)}"
        )
    node, detail = candidates[occurrence]
    operator = _operator_name(fault_class, node, detail)
    original_function_source = _indented_function_source(original_function)
    before = ast.dump(function, include_attributes=False)
    _mutate(fault_class, node, detail, parameter)
    function = ast.fix_missing_locations(function)
    after = ast.dump(function, include_attributes=False)
    if before == after:
        raise ValueError(f"fault {fault_class!r} changed nothing at {target!r}")
    mutant_function_source = _indented_function_source(function)
    original_span, mutant_span, original_occurrence, mutant_occurrence = (
        _changed_source_regions(
            original_function_source,
            mutant_function_source,
            file_start_line=int(scope["start_line"]),
        )
    )
    mutant = replace_scope(clean, scope, mutant_function_source)
    for item in mutant.files:
        compile(item.content, item.path, "exec")
    site = MutationSite(
        file=str(scope["file"]),
        function_name=target,
        helper=bool(original_function.col_offset),
        original_span=original_span,
        mutant_span=mutant_span,
        ast_operator=operator,
        occurrence=occurrence,
        candidate_count=len(candidates),
        original_snippet=original_occurrence,
        mutant_snippet=mutant_occurrence,
        original_snippet_sha256=_sha256(original_occurrence),
        mutant_snippet_sha256=_sha256(mutant_occurrence),
    )
    truth = GroundTruth(
        fault_class=fault_class,
        provenance=FAULT_CATALOGUE[fault_class].provenance,
        injected_function=target,
        injected_job_id=job_id,
        parameter=parameter,
        seed=seed,
        site=site,
        clean_bundle_sha256=_bundle_sha256(clean),
        mutant_bundle_sha256=_bundle_sha256(mutant),
        clean_function_sha256=_sha256(original_function_source),
        mutant_function_sha256=_sha256(mutant_function_source),
    )
    return InjectedPipeline(mutant, clean, truth)


def restore_clean(injected: InjectedPipeline) -> GeneratedPipeline:
    """Recreate normalized clean source from the mutant and verify exact hashes."""
    truth = injected.ground_truth
    clean_scope, _, clean_function = _target_function(
        injected.clean_pipeline, truth.injected_function
    )
    mutant_scope = source_scope(
        injected.pipeline, function_name=truth.injected_function, mode="boundary"
    )
    if clean_scope["file"] != mutant_scope.get("file"):
        raise ValueError("mutant function moved to another file")
    restored = replace_scope(
        injected.pipeline, mutant_scope, _indented_function_source(clean_function)
    )
    digest = _bundle_sha256(restored)
    if digest != truth.clean_bundle_sha256:
        raise ValueError("clean source restoration hash mismatch")
    return restored


def validate_mutant(
    injected: InjectedPipeline,
    validator: Callable[[GeneratedPipeline, GroundTruth], Mapping[str, Any]],
) -> InjectedPipeline:
    """Require executable, captured, schema-valid, semantically failing mutation."""
    result = dict(validator(injected.pipeline, injected.ground_truth))
    missing = [name for name in REQUIRED_VALIDATION_FLAGS if name not in result]
    if missing:
        raise ValueError(f"mutant validation omitted required flags: {missing}")
    failed = [name for name in REQUIRED_VALIDATION_FLAGS if result.get(name) is not True]
    if failed:
        raise ValueError(f"mutant rejected by validation: {failed}")
    truth = replace(injected.ground_truth, validation=result)
    return replace(injected, ground_truth=truth)


def freeze_mutation_site_order(
    pipeline: GeneratedPipeline,
    selection: FaultSelection,
) -> list[dict[str, Any]]:
    """Return the oracle-blind deterministic order for eligible exact sites."""
    candidates = [
        {**value, "job_id": selection.job_id}
        for value in enumerate_candidates(
            pipeline,
            fault_class=selection.fault_class,
            function_name=selection.function_name,
            parameter=selection.parameter,
        )
    ]
    source_hash = _bundle_sha256(normalize_pipeline(pipeline))
    for candidate in candidates:
        material = (
            f"{selection.seed}:{source_hash}:{selection.job_id}:"
            f"{selection.function_name}:{candidate['occurrence']}"
        )
        candidate["order_key"] = _sha256(material)
    return sorted(
        candidates,
        key=lambda value: (
            value["occurrence"] != selection.occurrence,
            value["order_key"],
            value["occurrence"],
        ),
    )


def resolve_captured_fault_nodes(
    injected: InjectedPipeline, snapshot: EtiqEvidenceSnapshot
) -> InjectedPipeline:
    """Attach captured nodes in the injected function/span when capture permits."""
    truth = injected.ground_truth
    truth = replace(
        truth,
        capture_snapshot_ids=sorted(
            {*truth.capture_snapshot_ids, snapshot.snapshot_id}
        ),
    )
    if truth.injected_job_id and snapshot.job_id != truth.injected_job_id:
        return replace(injected, ground_truth=truth)
    span = truth.site.mutant_span
    refs = sorted(
        set(truth.captured_fault_node_refs)
        | {
            node.node_ref
            for node in snapshot.nodes
            if truth.injected_function
            in {frame_name(str(frame)) for frame in node.func_stack}
            and (
                node.line_no is None
                or span["start_line"] <= node.line_no <= span["end_line"] + 1
            )
        }
    )
    by_ref = {node.node_ref: node for node in snapshot.nodes}
    adjacency: dict[str, set[str]] = {}
    for relationship in snapshot.relationships:
        adjacency.setdefault(relationship.source_ref, set()).add(relationship.target_ref)
    reached: set[str] = set()
    pending = list(refs)
    while pending:
        current = pending.pop()
        for target in adjacency.get(current, set()):
            if target not in reached:
                reached.add(target)
                pending.append(target)
    contamination = sorted(
        set(truth.downstream_contamination)
        | {
            node.func_stack[-1]
            for ref in reached
            if (node := by_ref.get(ref)) is not None
            and node.func_stack
            and truth.injected_function
            not in {frame_name(str(frame)) for frame in node.func_stack}
        }
    )
    return replace(
        injected,
        ground_truth=replace(
            truth,
            captured_fault_node_refs=refs,
            downstream_contamination=contamination,
            capture_finalized=bool(refs),
        ),
    )


def inject_after_clean_acceptance(
    pipeline: GeneratedPipeline,
    *,
    fresh_chain: bool,
    clean_control: bool,
    clean_execution: Mapping[str, Any],
    expected_job_ids: Iterable[str] | None = None,
    reference_chain_accepted: bool | None = None,
    clean_chain_accepted: bool | None = None,
    selection: FaultSelection | None = None,
    validator: Callable[[GeneratedPipeline, GroundTruth], Mapping[str, Any]] | None = None,
) -> InjectionOutcome:
    """D07 hook: retain injection state until D09 capture finalizes ground truth."""
    accepted_reference = (
        reference_chain_accepted
        if reference_chain_accepted is not None
        else clean_chain_accepted
    )
    if not accepted_reference:
        raise ValueError("fault injection requires the oracle-passing reference-chain acceptance gate")
    if not fresh_chain:
        raise ValueError("stored pilot pipelines are not eligible for fault injection")
    if clean_control:
        if selection is not None:
            raise ValueError("clean-control protocol decision cannot include a fault selection")
        decision = {
            "schema_version": "1",
            "protocol_version": PROTOCOL_VERSION,
            "protocol_content_hash": PROTOCOL_CONTENT_HASH,
            "storage_classification": "restricted_controller_only",
            "protocol_decision": "skip_injection_clean_control",
            "clean_bundle_sha256": _bundle_sha256(pipeline),
        }
        return InjectionOutcome(
            evaluation_pipeline=pipeline,
            protocol_decision=decision,
            clean_execution=dict(clean_execution),
        )
    if selection is None or validator is None:
        raise ValueError("faulty instances require a frozen selection and mutant validator")
    if not selection.job_id:
        raise ValueError("faulty instances require a frozen selected job ID")
    candidates = freeze_mutation_site_order(pipeline, selection)
    accepted = None
    selected = None
    rejections: list[dict[str, Any]] = []
    for candidate in candidates:
        occurrence = int(candidate["occurrence"])
        try:
            injected = inject(
                pipeline,
                selection.fault_class,
                target=selection.function_name,
                parameter=selection.parameter,
                occurrence=occurrence,
                seed=selection.seed,
                job_id=selection.job_id,
            )
            accepted = validate_mutant(injected, validator)
            if expected_job_ids is not None:
                expected = [str(value) for value in expected_job_ids]
                observed = [
                    str(value)
                    for value in accepted.ground_truth.validation.get(
                        "executed_job_ids", []
                    )
                ]
                if len(expected) != 2 or len(set(expected)) != 2 or observed != expected:
                    raise ValueError(
                        "mutant validation must execute the ordered upstream and downstream jobs"
                    )
            restore_clean(accepted)
            selected = candidate
            break
        except Exception:
            rejections.append(
                {
                    "stage": "mutation_site_validation",
                    "reason_code": "invalid_mutant",
                    "reason": "mutant failed frozen validation",
                    "job_id": selection.job_id,
                    "function_name": selection.function_name,
                    "occurrence": occurrence,
                }
            )
    if accepted is None or selected is None:
        raise ValueError("frozen mutation-site order exhausted without an oracle-effective mutant")
    decision = {
        "schema_version": "1",
        "protocol_version": PROTOCOL_VERSION,
        "protocol_content_hash": PROTOCOL_CONTENT_HASH,
        "storage_classification": "restricted_controller_only",
        "protocol_decision": "inject_single_fault",
        "seed": selection.seed,
        "job_id": selection.job_id,
        "selected_occurrence": selected["occurrence"],
        "ordered_candidate_universe_sha256": _sha256(
            json.dumps(candidates, sort_keys=True, separators=(",", ":"))
        ),
    }
    return InjectionOutcome(
        evaluation_pipeline=accepted.pipeline,
        protocol_decision=decision,
        clean_execution=dict(clean_execution),
        candidate_records=candidates,
        rejection_records=rejections,
        injector_output={
            "selected_candidate": selected,
            "clean_bundle_sha256": accepted.ground_truth.clean_bundle_sha256,
            "mutant_bundle_sha256": accepted.ground_truth.mutant_bundle_sha256,
            "draft_ground_truth": accepted.ground_truth.manifest(),
        },
        injected=accepted,
    )


def finalize_injection_after_capture(
    outcome: InjectionOutcome, snapshot: EtiqEvidenceSnapshot
) -> InjectionOutcome:
    """D09 hook: resolve captured nodes while retaining the original injection."""
    if outcome.injected is None:
        return outcome
    finalized = resolve_captured_fault_nodes(outcome.injected, snapshot)
    return replace(outcome, injected=finalized)


def finalize_injection_after_captures(
    outcome: InjectionOutcome, snapshots: Iterable[EtiqEvidenceSnapshot]
) -> InjectionOutcome:
    """Finalize against every per-job snapshot in one canonical capture set."""
    finalized = outcome
    count = 0
    for snapshot in snapshots:
        finalized = finalize_injection_after_capture(finalized, snapshot)
        count += 1
    if count == 0:
        raise ValueError("post-capture finalization requires at least one snapshot")
    if finalized.injected is not None and not finalized.injected.ground_truth.capture_finalized:
        raise ValueError(
            "mutated statement was not captured in the frozen selected-job snapshot"
        )
    return finalized


def restricted_injection_records(
    outcome: InjectionOutcome, *, require_final: bool = False
) -> dict[str, Any]:
    records: dict[str, Any] = {
        "protocol-decision.json": outcome.protocol_decision,
        "clean-execution.json": outcome.clean_execution,
        "candidates.json": outcome.candidate_records,
        "candidate-rejections.json": outcome.rejection_records,
        "injector-output.json": outcome.injector_output,
    }
    if outcome.injected is not None:
        records["validation.json"] = outcome.injected.ground_truth.validation
        records["ground-truth-draft.json"] = outcome.injector_output.get(
            "draft_ground_truth", outcome.injected.ground_truth.manifest()
        )
        if outcome.injected.ground_truth.capture_finalized:
            records["ground-truth.json"] = outcome.injected.ground_truth.manifest(
                final=True
            )
        elif require_final:
            raise ValueError("restricted records require finalized post-capture ground truth")
    return records


def persist_restricted_injection_records(
    outcome: InjectionOutcome,
    restricted_root: Path | str,
    *,
    sandbox_visible_roots: Iterable[Path | str] = (),
    require_final: bool = False,
) -> list[str]:
    """Atomically persist controller-only records outside every visible root."""
    root = Path(restricted_root).resolve()
    for visible_root in sandbox_visible_roots:
        visible = Path(visible_root).resolve()
        if root == visible or visible in root.parents or root in visible.parents:
            raise ValueError("restricted controller root overlaps a sandbox-visible root")
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for name, value in restricted_injection_records(
        outcome, require_final=require_final
    ).items():
        encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
        temporary = root / f".{name}.tmp"
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(root / name)
        written.append(name)
    return sorted(written)
