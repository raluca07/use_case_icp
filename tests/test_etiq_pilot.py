from __future__ import annotations

import importlib.util
import json
import socket
import time
from collections import defaultdict
from pathlib import Path

import pytest

from rdr import etiq_pilot
from fixtures.v2.etiq_replay_entry import ReplayApiCollection


DOT_ONLY = pytest.mark.skipif(importlib.util.find_spec("pydot") is None,
                              reason="pydot is isolated to .venv-etiq-pilot")


def empty_index():
    return {"by_line_source": defaultdict(list), "by_expression": defaultdict(list)}


def test_path_containment_and_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(etiq_pilot, "REPOSITORY_ROOT", tmp_path)
    (tmp_path / "entry.py").write_text("x = 1\n", encoding="utf-8")
    assert etiq_pilot.resolve_repository_file("entry.py") == tmp_path / "entry.py"
    with pytest.raises(ValueError, match="stay inside"):
        etiq_pilot.resolve_repository_file("../entry.py")
    assert etiq_pilot.canonical_hash({"b": 2, "a": 1}) == etiq_pilot.canonical_hash({"a": 1, "b": 2})


def test_replay_output_contract_matches_frozen_solution_return_style():
    response = {"message": "done"}
    assert etiq_pilot._expected_solution_output(
        "def solution(apis, requester):\n    apis.supervisor.complete_task()\n", response
    ) is None
    assert etiq_pilot._expected_solution_output(
        "def solution(apis, requester):\n    return apis.supervisor.complete_task()\n", response
    ) == response


class JsonFailsDotWorks:
    def create_full_lineage_graph(self, graph_format):
        if graph_format == "json":
            raise AssertionError("converter")
        return 'digraph G { a [label="payload"]; b [label="action"]; a -> b; }'


class BothFail:
    def create_full_lineage_graph(self, graph_format):
        raise RuntimeError(f"{graph_format} failed")


class EmptyGraphs:
    def create_full_lineage_graph(self, graph_format):
        if graph_format == "json":
            return {"objects": [], "edges": []}
        return "digraph G {}"


class JsonWorks:
    def create_full_lineage_graph(self, graph_format):
        assert graph_format == "json"
        return {"objects": [{"id": "a"}, {"id": "b"}],
                "edges": [{"source": "a", "target": "b"}]}


def slow_dot_parser(dot, native_state_map, index, *, allow_empty=False):
    time.sleep(0.2)
    return etiq_pilot.parse_dot_projection(
        dot, native_state_map, index, allow_empty=allow_empty
    )


def test_json_failure_uses_valid_native_dot_fallback(tmp_path):
    result = etiq_pilot.export_native_graph(JsonFailsDotWorks(), tmp_path, {}, empty_index())
    assert result["native_export_status"] == "dot"
    assert result["projection_status"] == "completed"
    assert result["warnings"] == [{"stage": "json_export", "artifact": "json-export-error.json",
                                   "exception_type": "AssertionError"}]
    assert (tmp_path / "lineage.dot").read_text().startswith("digraph")
    assert json.loads((tmp_path / "etiq_dot_projection.json").read_text())["edge_count"] == 1


def test_both_exports_fail_closed_with_two_error_artifacts(tmp_path):
    result = etiq_pilot.export_native_graph(BothFail(), tmp_path, {}, empty_index())
    assert result["native_export_status"] == "failed"
    assert result["projection_status"] == "not_applicable"
    assert (tmp_path / "json-export-error.json").exists()
    assert (tmp_path / "dot-export-error.json").exists()
    assert len(result["warnings"]) == 2


@pytest.mark.parametrize("dot", [
    'digraph G { a [label="a"]; a -> missing; }',
    "not dot",
])
def test_invalid_empty_or_unresolved_dot_is_rejected(dot):
    with pytest.raises(ValueError):
        etiq_pilot.parse_etiq_dot_projection(dot, {}, empty_index())


def test_semantics_ignore_ids_but_preserve_duplicate_multiplicity_and_structure():
    first = 'digraph G { a1 [label="x"]; a2 [label="x"]; b [label="y"]; a1 -> b; a2 -> b; }'
    second = 'digraph G { q [label="y"]; p2 [label="x"]; p1 [label="x"]; p1 -> q; p2 -> q; }'
    collapsed = 'digraph G { p [label="x"]; q [label="y"]; p -> q; }'
    a = etiq_pilot.parse_etiq_dot_projection(first, {}, empty_index())
    b = etiq_pilot.parse_etiq_dot_projection(second, {}, empty_index())
    c = etiq_pilot.parse_etiq_dot_projection(collapsed, {}, empty_index())
    assert a["semantic_sha256"] == b["semantic_sha256"]
    assert a["semantic_sha256"] != c["semantic_sha256"]
    assert a["node_count"] == 3


def test_empty_native_graph_is_not_an_export_failure(tmp_path):
    result = etiq_pilot.export_native_graph(EmptyGraphs(), tmp_path, {}, empty_index())
    assert result["native_export_status"] == "empty"
    assert result["projection_status"] == "not_applicable"
    assert result["native_sha256"] == etiq_pilot.file_sha256(tmp_path / "lineage.dot")
    assert not (tmp_path / "dot-projection-error.json").exists()


def test_fast_parser_accepts_compact_empty_and_multiline_dot():
    empty = etiq_pilot.parse_etiq_dot_projection(
        "digraph G {}", {}, empty_index(), allow_empty=True
    )
    compact = etiq_pilot.parse_etiq_dot_projection(
        'digraph G { a [label="a"]; b [label="b"]; a -> b; }', {}, empty_index()
    )
    multiline = etiq_pilot.parse_etiq_dot_projection(
        'digraph G {\n a [label="a"];\n b [label="b"];\n a -> b;\n}', {}, empty_index()
    )
    assert empty["node_count"] == empty["edge_count"] == 0
    assert compact["semantic_sha256"] == multiline["semantic_sha256"]


def test_fast_parser_preserves_distinct_runtime_occurrences():
    graph = etiq_pilot.parse_etiq_dot_projection(
        'digraph G { a1 [label="value"]; a2 [label="value"]; '
        'b1 [label="use"]; b2 [label="use"]; a1 -> b1; a2 -> b2; }',
        {}, empty_index(),
    )
    assert sorted(node["occurrence_ordinal"] for node in graph["nodes"]) == [0, 1, 2, 3]
    assert sorted(edge["occurrence_ordinal"] for edge in graph["edges"]) == [0, 1]
    assert graph["node_count"] == 4


def test_native_json_arm_is_explicitly_not_assessed(tmp_path):
    result = etiq_pilot.export_native_graph(JsonWorks(), tmp_path, {}, empty_index())
    assert result["native_export_status"] == "json"
    assert result["projection_status"] == "not_applicable"
    eligibility, reason = etiq_pilot.assess_workflow_only_eligibility(
        True, "json", "not_applicable", {"passed": True}, None
    )
    assert eligibility == "not_assessed"
    assert "not implemented" in reason


def test_representative_large_dot_finishes_with_classifiable_timeout(tmp_path):
    labels = "x" * 700
    lines = ["digraph G {"]
    lines.extend(f'n{i} [label="{labels}{i}"];' for i in range(950))
    lines.extend(f"n{i} -> n{i + 1};" for i in range(949))
    lines.append("}")
    dot_path = tmp_path / "lineage.dot"
    dot_path.write_text("\n".join(lines), encoding="utf-8")
    assert dot_path.stat().st_size >= 668_018
    result = etiq_pilot.project_dot_bounded(
        dot_path, tmp_path, {}, empty_index(), timeout_seconds=0.01
    )
    assert result["status"] == "timed_out"
    error = json.loads((tmp_path / "dot-projection-error.json").read_text())
    assert error["status"] == "timed_out"
    assert dot_path.exists()


@DOT_ONLY
def test_deliberately_slow_parser_times_out_without_partial_projection(tmp_path):
    dot_path = tmp_path / "lineage.dot"
    dot_path.write_text('digraph G { a [label="a"]; b [label="b"]; a -> b; }', encoding="utf-8")
    result = etiq_pilot.project_dot_bounded(
        dot_path, tmp_path, {}, empty_index(), timeout_seconds=0.01,
        parser=slow_dot_parser,
    )
    assert result["status"] == "timed_out"
    assert not (tmp_path / "etiq_dot_projection.json").exists()
    assert not (tmp_path / "workflow-lineage-projection.json").exists()
    assert json.loads((tmp_path / "dot-projection-error.json").read_text())["status"] == "timed_out"


def test_origin_classification_and_ambiguous_rejection():
    index = empty_index()
    index["by_line_source"][(1, "x = 1")] = [
        {"role": "frozen_workflow", "path": "workflow.py", "sha256": "a", "scope": ""}
    ]
    origin = etiq_pilot.classify_origin(1, "x = 1", None, index)
    assert origin["classification"] == "frozen_workflow"
    index["by_line_source"][(1, "x = 1")].append(
        {"role": "replay_harness", "path": "entry.py", "sha256": "b", "scope": ""}
    )
    ambiguous = etiq_pilot.classify_origin(1, "x = 1", None, index)
    assert ambiguous == {"classification": "unknown", "path": None, "source_sha256": None, "ambiguous": True}


def test_workflow_projection_removes_replay_scaffolding():
    graph = {
        "nodes": [
            {"id": "w1", "label": "payload", "attributes": {}, "clusters": [],
             "origin": {"classification": "frozen_workflow"}},
            {"id": "w2", "label": "apis.venmo.create_payment_request", "attributes": {}, "clusters": [],
             "origin": {"classification": "frozen_workflow"}},
            {"id": "h", "label": "expected_transcript", "attributes": {}, "clusters": [],
             "origin": {"classification": "replay_harness"}},
        ],
        "edges": [{"source": "w1", "target": "w2", "attributes": {}},
                  {"source": "h", "target": "w1", "attributes": {}}],
    }
    projection, assessment = etiq_pilot.workflow_projection(graph)
    assert {node["id"] for node in projection["nodes"]} == {"w1", "w2"}
    assert "expected_transcript" not in etiq_pilot.canonical_json(projection)
    assert assessment["leakage_matches"] == []
    assert assessment["fault_to_action_paths"]


def test_private_value_hashing_redacts_secrets():
    safe = etiq_pilot._safe_value(
        {"access_token": "eyJabc.def.ghi", "memo": "synthetic"}, ["response"]
    )
    encoded = etiq_pilot.canonical_json(safe)
    assert "eyJabc" not in encoded
    assert safe["access_token"] == "<redacted:sensitive-key>"
    assert len(etiq_pilot.canonical_hash(safe)) == 64


def test_environment_is_allowlisted_and_network_is_denied(tmp_path):
    environment = etiq_pilot.build_worker_environment(tmp_path / "run", None, None)
    assert set(environment) == {
        "PATH", "LANG", "LC_ALL", "HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "TMPDIR", "PYTHONPATH",
        "PYDANTIC_AI_NO_BANNER", "PYTHONDONTWRITEBYTECODE", "ETIQ_NETWORK_DISABLED",
    }
    original_create = socket.create_connection
    original_socket = socket.socket
    try:
        etiq_pilot.install_network_denial()
        assert etiq_pilot.network_denial_probe() is True
    finally:
        socket.create_connection = original_create
        socket.socket = original_socket


def test_replay_registers_only_qualified_collection_and_no_primitives(tmp_path):
    output = tmp_path / "cells" / "run-1"
    output.parent.mkdir()
    bundle = tmp_path / "bundle.json"
    replay = tmp_path / "replay.json"
    etiq_pilot.build_worker_environment(output, bundle, replay)
    config = output.parent / ".run-1-isolation/data/etiq_copilot/capture_targets.yml"
    assert config.read_text(encoding="utf-8") == (
        "!!set\nfixtures.v2.etiq_replay_entry.ReplayApiCollection: null\n"
    )
    assert not any(
        primitive in config.read_text(encoding="utf-8")
        for primitive in ("builtins.dict", "builtins.list", "builtins.str", "builtins.int")
    )


def test_network_denial_is_installed_before_scanner_import(tmp_path, monkeypatch):
    state = {"installed": False}

    def install():
        state["installed"] = True

    def load():
        assert state["installed"] is True
        raise RuntimeError("scanner import reached after denial")

    monkeypatch.setenv("ETIQ_NETWORK_DISABLED", "1")
    monkeypatch.setattr(etiq_pilot, "install_network_denial", install)
    monkeypatch.setattr(etiq_pilot, "network_denial_probe", lambda: state["installed"])
    monkeypatch.setattr(etiq_pilot.importlib.metadata, "version", lambda name: etiq_pilot.ETIQ_VERSION)
    monkeypatch.setattr(etiq_pilot, "load_debugger_scanner", load)
    with pytest.raises(RuntimeError, match="after denial"):
        etiq_pilot.scan_entry(Path("unused.py"), tmp_path / "run")


def test_manifest_requires_dot_projection_inventory_output_and_error(tmp_path):
    files = {
        "scan-result.json": {
            "native_export_status": "dot", "projection_status": "completed",
            "native_graph": {"path": "lineage.dot"},
        },
        "state-inventory.json": {}, "etiq_dot_projection.json": {},
        "workflow-lineage-projection.json": {}, "json-export-error.json": {},
    }
    for name, value in files.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    for name in ("lineage.dot", "stdout.txt", "stderr.txt"):
        (tmp_path / name).write_text("digraph G {}" if name.endswith(".dot") else "", encoding="utf-8")
    freeze = ["etiq-copilot==2.3.2"]
    artifacts = {path.name: etiq_pilot.file_sha256(path) for path in tmp_path.iterdir()}
    (tmp_path / "manifest.json").write_text(json.dumps({
        "environment_freeze": freeze, "environment_freeze_sha256": etiq_pilot.canonical_hash(freeze),
        "artifacts": artifacts,
    }), encoding="utf-8")
    assert etiq_pilot.verify_manifest(tmp_path)["artifacts"] == artifacts
    del artifacts["workflow-lineage-projection.json"]
    (tmp_path / "manifest.json").write_text(json.dumps({
        "environment_freeze": freeze, "environment_freeze_sha256": etiq_pilot.canonical_hash(freeze),
        "artifacts": artifacts,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="omits"):
        etiq_pilot.verify_manifest(tmp_path)


def test_manifest_rejects_bytecode_artifacts(tmp_path):
    bytecode = tmp_path / "__pycache__" / "entry.cpython-312.pyc"
    bytecode.parent.mkdir()
    bytecode.write_bytes(b"not bytecode")
    with pytest.raises(ValueError, match="bytecode"):
        etiq_pilot.write_root_manifest(tmp_path)


def test_exact_source_binding_for_source_fault_and_repair():
    for cell in (Path("S01/S1R0.json"), Path("S01/repaired.json")):
        bundle, source = etiq_pilot.build_replay_bundle(cell, Path("runs/private/source.py"))
        assert bundle["workflow_sha256"] == __import__("hashlib").sha256(source.encode()).hexdigest()
        assert bundle["workflow_sha256"] == "c5006ab57a406e5284b7208ef3352f9993708ed335bfddf431efbbbdc728a927"
    repaired, _ = etiq_pilot.build_replay_bundle(Path("S01/repaired.json"), Path("runs/private/source.py"))
    assert repaired["calls"][-2]["injected_hook"] is True


def test_replay_applies_private_argument_intervention_before_hash_validation():
    truncated = "abcdefgh"[:4]
    args = {"content": truncated, "file_path": "x"}
    bundle = {
        "calls": [{"app": "file_system", "method": "create_file",
                   "args_sha256": etiq_pilot.canonical_hash(args), "response": {"ok": True}}],
        "argument_interventions": {"0": {"operation": "partial_file", "arg": "content"}},
    }
    transcript = []
    apis = ReplayApiCollection(bundle, transcript)
    assert apis.file_system.create_file(content="abcdefgh", file_path="x") == {"ok": True}
    apis.assert_complete()


def test_replay_consumes_all_private_repair_hooks_before_final_call():
    calls = [
        {"app": "venmo", "method": "update_payment_request",
         "args_sha256": etiq_pilot.canonical_hash({"amount": 12.5}),
         "response": {"ok": True}, "injected_hook": True, "hook_args": {"amount": 12.5}},
        {"app": "file_system", "method": "update_file",
         "args_sha256": etiq_pilot.canonical_hash({"content": "fixed"}),
         "response": {"ok": True}, "injected_hook": True, "hook_args": {"content": "fixed"}},
        {"app": "supervisor", "method": "complete_task",
         "args_sha256": etiq_pilot.canonical_hash({}), "response": {"done": True}},
    ]
    transcript = []
    apis = ReplayApiCollection({"calls": calls}, transcript)
    assert apis.supervisor.complete_task() == {"done": True}
    apis.assert_complete()
    assert [item["method"] for item in transcript] == [
        "update_payment_request", "update_file", "complete_task"
    ]


def test_replay_consumes_runtime_hook_before_the_workflow_call():
    calls = [
        {"app": "venmo", "method": "update_payment_request",
         "args_sha256": etiq_pilot.canonical_hash({"amount": 13.5}),
         "response": {"ok": True}, "injected_hook": True, "hook_args": {"amount": 13.5}},
        {"app": "file_system", "method": "create_file",
         "args_sha256": etiq_pilot.canonical_hash({"content": "receipt"}),
         "response": {"ok": True}},
    ]
    transcript = []
    apis = ReplayApiCollection({"calls": calls}, transcript)
    assert apis.file_system.create_file(content="receipt") == {"ok": True}
    apis.assert_complete()
    assert [item["method"] for item in transcript] == ["update_payment_request", "create_file"]


def test_concurrent_update_is_marked_as_a_private_runtime_hook():
    assert etiq_pilot._is_injected_hook(
        {"patch": {"index": 26, "operation": "concurrent_update"}}, None,
        26, 55, "complete_task",
    )


def test_replay_scan_parses_exact_workflow_source_and_injects_globals(tmp_path, monkeypatch):
    source = "def solution(apis, requester):\n    return 'ok'\n"
    workflow = tmp_path / "workflow.py"
    workflow.write_text(source, encoding="utf-8")
    monkeypatch.setattr(etiq_pilot, "REPOSITORY_ROOT", tmp_path)
    bundle = {
        "workflow_path": "workflow.py",
        "workflow_sha256": __import__("hashlib").sha256(source.encode()).hexdigest(),
        "calls": [],
    }
    result_path = tmp_path / "result.json"
    program, scan_globals, finalize, metadata = etiq_pilot.build_replay_scan(bundle, result_path)
    assert program[:len(source)] == source
    assert program[len(source):].startswith("\n# ETIQ_REPLAY_INVOCATION")
    assert metadata["sha256"] == bundle["workflow_sha256"]
    assert metadata["invocation_role"] == "replay_harness"
    exec(program, scan_globals)
    finalize()
    result = json.loads(result_path.read_text())
    assert result["final_output"] == "ok"
    assert result["transcript"] == []


def test_scan_entry_passes_exact_workflow_prefix_to_etiq(tmp_path, monkeypatch):
    source = "def solution(apis, requester):\n    return 'ok'\n"
    workflow = tmp_path / "workflow.py"
    workflow.write_text(source, encoding="utf-8")
    entry = tmp_path / "entry.py"
    entry.write_text("raise AssertionError('harness must not be scanned')\n", encoding="utf-8")
    source_hash = __import__("hashlib").sha256(source.encode()).hexdigest()
    bundle = {
        "workflow_path": "workflow.py", "workflow_sha256": source_hash,
        "calls": [], "expected_transcript": [], "expected_actions": [],
        "expected_final_output": "ok", "qualification": {"expected_passed": True},
    }
    captured = {}

    class EmptyScan:
        scan_errors = None

        def get_dataframes(self):
            return []

        def get_models(self):
            return []

        def get_agent_states(self):
            return []

        def get_unstructured_states(self):
            return []

        def list_dataframes(self):
            return []

        def list_models(self):
            return []

        def list_agents(self):
            return []

    class RecordingScanner:
        def scan_code(self, *, code_str, scan_globals):
            captured.update(code_str=code_str, scan_globals=scan_globals)
            exec(code_str, scan_globals)
            return EmptyScan()

    def export_empty(scan, output_dir, native_state_map, index):
        del scan, native_state_map, index
        native = output_dir / "lineage.json"
        native.write_text("{}", encoding="utf-8")
        return {
            "native_export_status": "empty", "native_path": native,
            "native_sha256": etiq_pilot.file_sha256(native),
            "projection_status": "not_applicable", "dot_projection": None,
            "projection_assessment": None, "projection_error": None, "warnings": [],
        }

    monkeypatch.setattr(etiq_pilot, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(etiq_pilot, "install_network_denial", lambda: None)
    monkeypatch.setattr(etiq_pilot, "network_denial_probe", lambda: True)
    monkeypatch.setattr(etiq_pilot.importlib.metadata, "version", lambda name: etiq_pilot.ETIQ_VERSION)
    monkeypatch.setattr(etiq_pilot, "load_debugger_scanner", lambda: RecordingScanner)
    monkeypatch.setattr(etiq_pilot, "source_index", lambda specs: empty_index())
    monkeypatch.setattr(etiq_pilot, "_source_specs", lambda entry_path, bundle_path: (
        [
            {"role": "replay_harness", "path": "entry.py",
             "sha256": etiq_pilot.file_sha256(entry)},
            {"role": "frozen_workflow", "path": "workflow.py", "sha256": source_hash},
        ],
        bundle,
    ))
    monkeypatch.setattr(etiq_pilot, "export_native_graph", export_empty)
    monkeypatch.setenv("ETIQ_NETWORK_DISABLED", "1")
    result = etiq_pilot.scan_entry(
        Path("entry.py"), tmp_path / "output", bundle_path=tmp_path / "bundle.json",
        replay_result_path=tmp_path / "replay.json",
    )

    assert captured["code_str"][:len(source)] == source
    assert "harness must not be scanned" not in captured["code_str"]
    assert "apis" not in captured["scan_globals"]
    assert type(captured["scan_globals"]["__etiq_replay_apis__"]).__qualname__ == "ReplayApiCollection"
    assert result["scan_source"]["sha256"] == source_hash
    assert result["replay_fidelity"]["passed"] is True


def test_runtime_and_interaction_bundles_bind_faulted_responses_and_labels():
    runtime, _ = etiq_pilot.build_replay_bundle(Path("R01/S0R1.json"), Path("runs/private/r.py"))
    interaction, _ = etiq_pilot.build_replay_bundle(Path("I06/S1R1.json"), Path("runs/private/i.py"))
    assert runtime["qualification"]["expected_passed"] is False
    assert interaction["qualification"]["expected_passed"] is False
    assert runtime["calls"][19]["response"] != interaction["calls"][19]["response"]
    assert runtime["expected_transcript_sha256"] == etiq_pilot.canonical_hash(runtime["expected_transcript"])
