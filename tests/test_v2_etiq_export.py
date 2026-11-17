from __future__ import annotations

import copy
import hashlib
import json
import random
from pathlib import Path

import pytest

from rdr.trace import Write
from rdr.v2_etiq_export import (
    ALL_ETIQ_CONDITIONS,
    ETIQ_CONDITIONS,
    STATE_GRAPH_CONDITIONS,
    _canonical_hash,
    _lineage_feature_counts,
    _project_native_etiq,
    _scan_inputs,
    _verify_complete_etiq_coverage,
    audit_etiq_conditions,
    audit_state_graph_conditions,
    build_appworld_etiq_composite,
    build_etiq_conditions,
    build_state_graph_conditions,
    export_etiq_native,
    extend_frozen_build_with_etiq,
    import_native_etiq,
    qualify_etiq_repeatability,
)
from rdr.v2_schema import CallV2, TraceV2


def fixture_layers():
    source_hash = "a" * 64
    trace = TraceV2(
        "task", "Create the receipt", "done",
        [
            CallV2(0, "venmo", "create_payment_request", {},
                   {"payment_request_id": 7}, {"payment_request_id": 7}),
            CallV2(1, "file_system", "create_file", {"content": "request_id: 7"},
                   {"ok": True}, {"ok": True},
                   [Write("file_system.files#7", None, {"id": 7})]),
        ],
        {"workflow.py": "def solution(apis, requester):\n    return 7\n"},
    )
    appworld = {
        "schema_version": "2.1.0", "graph_kind": "appworld_execution",
        "source_sha256": source_hash,
        "calls": [{"index": 0}, {"index": 1}],
        "nodes": [
            {"id": "response:observed:0", "kind": "observed_response",
             "value": {"payment_request_id": 7}},
            {"id": "call:1", "kind": "api_call", "index": 1,
             "api": "file_system.create_file", "args": {"content": "request_id: 7"}},
            {"id": "artifact:after:7", "kind": "artifact_after",
             "record": "file_system.files#7", "value": {"id": 7}},
            {"id": "artifact:directory:7", "kind": "artifact_after",
             "record": "file_system.directories#7", "value": {"id": 7}},
        ],
        "edges": [
            {"src": "call:1", "kind": "writes", "dst": "artifact:after:7"},
            {"src": "call:1", "kind": "writes", "dst": "artifact:directory:7"},
        ],
        "manifest": {"content_sha256": "b" * 64},
    }
    etiq = {
        "schema_version": "2.1.0", "graph_kind": "etiq_native", "status": "available",
        "source_sha256": source_hash,
        "nodes": [
            {"id": "node-result", "kind": "etiq_state", "label": "result",
             "state_sha256": _canonical_hash({"payment_request_id": 7}),
             "state_names": ["result"], "source_line": 10},
            {"id": "node-index", "kind": "etiq_operation",
             "label": "result['payment_request_id']"},
            {"id": "node-request", "kind": "etiq_state", "label": "request_id",
             "state_sha256": _canonical_hash(7), "state_names": ["request_id"],
             "source_line": 11},
        ],
        "edges": [
            {"src": "node-result", "kind": "etiq_lineage", "dst": "node-index"},
            {"src": "node-index", "kind": "etiq_lineage", "dst": "node-request"},
        ],
        "manifest": {"content_sha256": "c" * 64},
    }
    return trace, appworld, etiq


def eligible():
    return {
        "deterministic_repeatability": True,
        "workflow_only_eligibility": {
            "status": "eligible", "replay_fidelity": True,
            "isolated_capture_configuration": True, "public_projection": True,
        },
    }


def test_appworld_to_etiq_conversion_remains_forbidden(tmp_path):
    with pytest.raises(ValueError, match="conversion is forbidden"):
        export_etiq_native(tmp_path / "appworld.json", tmp_path / "etiq.json")


def test_required_native_lineage_features_are_detected():
    nodes = [
        {"kind": "etiq_state", "label": "payload", "state_names": ["payload"]},
        {"kind": "etiq_operation", "label": "payload = json.loads(body)"},
        {"kind": "etiq_operation", "label": "return (payload, None)"},
        {"kind": "etiq_state", "label": "receipt_path", "state_names": ["receipt_path"]},
    ]
    assert _lineage_feature_counts(nodes) == {
        "workflow_assignments": 2,
        "parsing_operations": 1,
        "guard_outcomes": 1,
        "intermediate_values": 2,
    }


def test_dataset_conditional_operation_is_a_genuine_guard_feature():
    nodes = [{"kind": "etiq_operation", "label": "incoming[-1] if incoming else None"}]
    assert _lineage_feature_counts(nodes)["guard_outcomes"] == 1


def test_public_projection_preserves_same_shape_runtime_occurrences(tmp_path, monkeypatch):
    origin = {"classification": "frozen_workflow", "path": "workflow.py",
              "source_sha256": "a" * 64}
    states = [
        {"id": "state-00000", "value_sha256": _canonical_hash({"body": "one"}),
         "names": ["payload"], "source_line": 10, "structure": {"python_type": "dict"}},
        {"id": "state-00001", "value_sha256": _canonical_hash({"body": "two"}),
         "names": ["payload"], "source_line": 10, "structure": {"python_type": "dict"}},
        {"id": "state-00002", "value_sha256": _canonical_hash(7),
         "names": ["request_id"], "source_line": 11, "structure": {"python_type": "int"}},
        {"id": "state-00003", "value_sha256": _canonical_hash(8),
         "names": ["request_id"], "source_line": 11, "structure": {"python_type": "int"}},
        {"id": "state-00004", "value_sha256": _canonical_hash(None),
         "names": ["reason"], "source_line": 12, "structure": {"python_type": "NoneType"}},
    ]
    projection_nodes = [
        {"id": f"raw-{index}", "state_id": state["id"], "label": state["names"][0],
         "clusters": [], "origin": origin, "occurrence_ordinal": index}
        for index, state in enumerate(states)
    ] + [
        {"id": "op-0", "state_id": None, "label": "payload = json.loads(body)",
         "clusters": [], "origin": origin, "occurrence_ordinal": 5},
        {"id": "op-1", "state_id": None, "label": "payload = json.loads(body)",
         "clusters": [], "origin": origin, "occurrence_ordinal": 6},
    ]
    projection = {
        "nodes": projection_nodes,
        "edges": [
            {"source": "raw-0", "target": "op-0", "occurrence_ordinal": 0},
            {"source": "op-0", "target": "raw-2", "occurrence_ordinal": 1},
            {"source": "raw-1", "target": "op-1", "occurrence_ordinal": 2},
            {"source": "op-1", "target": "raw-3", "occurrence_ordinal": 3},
        ],
    }
    result = {
        "scan_source": {"sha256": "a" * 64}, "native_export_status": "dot",
        "native_graph": {"sha256": "b" * 64},
    }
    (tmp_path / "workflow-lineage-projection.json").write_text("{}")
    monkeypatch.setattr(
        "rdr.v2_etiq_export._scan_inputs",
        lambda scan: (result, projection, {"states": states},
                      {"fixtures.v2.etiq_replay_entry.ReplayApiCollection"}),
    )
    graph, _ = _project_native_etiq(tmp_path)
    requests = [node for node in graph["nodes"] if node.get("state_names") == ["request_id"]]
    parses = [node for node in graph["nodes"] if "json.loads" in node.get("label", "")]
    assert len(requests) == len(parses) == 2
    assert len({node["id"] for node in requests}) == 2
    assert len({node["state_sha256"] for node in requests}) == 2
    assert all(node["multiplicity"] == 1 for node in graph["nodes"])
    assert graph["counts"]["edge_instances"] == 4


def test_composite_preserves_layers_namespaces_and_verified_effect_path():
    trace, appworld, etiq = fixture_layers()
    before = json.dumps(appworld, sort_keys=True, separators=(",", ":"))
    graph, report = build_appworld_etiq_composite(appworld, trace, etiq, eligible())
    assert graph["graph_kind"] == "appworld_etiq_composite"
    assert json.dumps(appworld, sort_keys=True, separators=(",", ":")) == before
    assert all(node["id"].startswith(("aw:", "etiq:")) for node in graph["nodes"])
    assert {edge["kind"] for edge in graph["edges"]} >= {
        "etiq_lineage", "bridge_response_to_code", "bridge_code_to_argument", "writes",
    }
    assert report["verified_effect_path"]["edge_kinds"] == [
        "bridge_response_to_code", "etiq_lineage", "etiq_lineage",
        "bridge_code_to_argument", "writes",
    ]
    assert report["verified_effect_path"]["nodes"][-1] == "aw:artifact:after:7"
    assert report["composite_eligibility"]["status"] == "eligible"
    assert not any("value" in node for node in graph["nodes"] if node["id"].startswith("aw:"))


def test_state_graph_conditions_have_identical_state_evidence_and_one_graph_each():
    trace, appworld, etiq = fixture_layers()
    initial = {"gmail_threads": [{"subject": "Invoice request"}], "requests": []}
    final = {"gmail_threads": [{"subject": "Invoice request"}], "requests": [{"id": 7}]}

    packages = build_state_graph_conditions(trace, appworld, etiq, initial, final)

    assert [package.arm for package in packages] == list(STATE_GRAPH_CONDITIONS)
    assert packages[0].common == packages[1].common
    assert set(packages[0].sections) == set(packages[1].sections) == {"common", "graph"}
    assert "INITIAL TASK INPUTS" in packages[0].common
    assert "CALLS MADE" not in packages[0].text
    assert "EXECUTED WORKFLOW SOURCE" not in packages[0].text
    assert packages[0].sections["graph"].startswith(
        "PROVENANCE GRAPH kind=appworld_execution"
    )
    assert packages[1].sections["graph"].startswith("PROVENANCE GRAPH kind=etiq_native")
    assert "kind=etiq_native" not in packages[0].sections["graph"]
    assert "kind=appworld_execution" not in packages[1].sections["graph"]
    assert audit_state_graph_conditions(packages, ["private-value-not-present"])["passed"]
    assert set(ALL_ETIQ_CONDITIONS) == set(ETIQ_CONDITIONS) | set(STATE_GRAPH_CONDITIONS)


def test_ambiguous_state_join_is_recorded_and_not_guessed():
    trace, appworld, etiq = fixture_layers()
    for suffix in ("a", "b"):
        etiq["nodes"].append({
            "id": f"node-ok-{suffix}", "kind": "etiq_state", "label": "ok",
            "state_sha256": _canonical_hash({"ok": True}), "state_names": ["ok"],
            "source_line": 20,
        })
        etiq["edges"].append(
            {"src": "node-request", "kind": "etiq_lineage", "dst": f"node-ok-{suffix}"}
        )
    graph, report = build_appworld_etiq_composite(appworld, trace, etiq, eligible())
    assert report["ambiguous_join_count"] >= 1
    assert not any(
        edge["kind"] == "bridge_response_to_code"
        and edge["join"]["call_index"] == 1
        for edge in graph["edges"]
    )


def test_repeated_iterations_keep_distinct_response_and_argument_paths():
    source_hash = "d" * 64
    trace = TraceV2(
        "task", "process two invoices", "done",
        [
            CallV2(0, "venmo", "create_payment_request", {}, {"payment_request_id": 7},
                   {"payment_request_id": 7}),
            CallV2(1, "file_system", "create_file", {"content": "request_id: 7"},
                   {"ok": True}, {"ok": True},
                   [Write("file_system.files#7", None, {"id": 7})]),
            CallV2(2, "venmo", "create_payment_request", {}, {"payment_request_id": 8},
                   {"payment_request_id": 8}),
            CallV2(3, "file_system", "create_file", {"content": "request_id: 8"},
                   {"ok": True}, {"ok": True},
                   [Write("file_system.files#8", None, {"id": 8})]),
        ],
        {"workflow.py": "def solution(apis, requester):\n    return requester\n"},
    )
    appworld = {
        "graph_kind": "appworld_execution", "source_sha256": source_hash,
        "calls": [{"index": index} for index in range(4)],
        "nodes": [
            {"id": "response:observed:0", "kind": "observed_response",
             "value": {"payment_request_id": 7}},
            {"id": "response:observed:2", "kind": "observed_response",
             "value": {"payment_request_id": 8}},
            {"id": "call:1", "kind": "api_call"},
            {"id": "call:3", "kind": "api_call"},
            {"id": "artifact:7", "kind": "artifact_after",
             "record": "file_system.files#7", "value": {"id": 7}},
            {"id": "artifact:8", "kind": "artifact_after",
             "record": "file_system.files#8", "value": {"id": 8}},
        ],
        "edges": [
            {"src": "call:1", "kind": "writes", "dst": "artifact:7"},
            {"src": "call:3", "kind": "writes", "dst": "artifact:8"},
        ],
        "manifest": {"content_sha256": "e" * 64},
    }
    etiq = {
        "graph_kind": "etiq_native", "status": "available", "source_sha256": source_hash,
        "nodes": [], "edges": [], "manifest": {"content_sha256": "f" * 64},
    }
    for iteration, request_id in enumerate((7, 8)):
        response = f"response-{iteration}"
        operation = f"index-{iteration}"
        argument = f"request-{iteration}"
        etiq["nodes"].extend([
            {"id": response, "kind": "etiq_state", "label": "result",
             "state_sha256": _canonical_hash({"payment_request_id": request_id}),
             "occurrence_index": iteration},
            {"id": operation, "kind": "etiq_operation", "label": "result[index]",
             "occurrence_index": iteration},
            {"id": argument, "kind": "etiq_state", "label": "request_id",
             "state_sha256": _canonical_hash(request_id), "occurrence_index": iteration},
        ])
        etiq["edges"].extend([
            {"src": response, "kind": "etiq_lineage", "dst": operation},
            {"src": operation, "kind": "etiq_lineage", "dst": argument},
        ])
    graph, report = build_appworld_etiq_composite(appworld, trace, etiq, eligible())
    code_bridges = [edge for edge in graph["edges"]
                    if edge["kind"] == "bridge_code_to_argument"]
    assert {tuple(edge["join"]["upstream_response_call_indices"])
            for edge in code_bridges} == {(0,), (2,)}
    assert {edge["src"] for edge in code_bridges} == {
        "etiq:request-0", "etiq:request-1",
    }
    assert report["composite_eligibility"]["status"] == "eligible"


def test_one_argument_occurrence_reachable_from_calls_25_and_38_is_ambiguous():
    source_hash = "1" * 64
    trace = TraceV2(
        "task", "process", "done",
        [
            CallV2(25, "gmail", "show_thread", {}, {"invoice": "A"}, {"invoice": "A"}),
            CallV2(38, "gmail", "show_thread", {}, {"invoice": "B"}, {"invoice": "B"}),
            CallV2(50, "file_system", "create_file", {"content": "request_id: 7"},
                   {"ok": True}, {"ok": True},
                   [Write("file_system.files#7", None, {"id": 7})]),
            CallV2(60, "venmo", "create_payment_request", {}, {"payment_request_id": 8},
                   {"payment_request_id": 8}),
            CallV2(61, "file_system", "create_file", {"content": "request_id: 8"},
                   {"ok": True}, {"ok": True},
                   [Write("file_system.files#8", None, {"id": 8})]),
        ],
        {"workflow.py": "def solution(apis, requester):\n    return requester\n"},
    )
    appworld = {
        "graph_kind": "appworld_execution", "source_sha256": source_hash,
        "calls": [
            {"index": 25}, {"index": 38}, {"index": 50}, {"index": 60}, {"index": 61},
        ],
        "nodes": [
            {"id": "response:observed:25", "kind": "observed_response", "value": {"invoice": "A"}},
            {"id": "response:observed:38", "kind": "observed_response", "value": {"invoice": "B"}},
            {"id": "call:50", "kind": "api_call"},
            {"id": "artifact:7", "kind": "artifact_after",
             "record": "file_system.files#7", "value": {"id": 7}},
            {"id": "response:observed:60", "kind": "observed_response",
             "value": {"payment_request_id": 8}},
            {"id": "call:61", "kind": "api_call"},
            {"id": "artifact:8", "kind": "artifact_after",
             "record": "file_system.files#8", "value": {"id": 8}},
        ],
        "edges": [
            {"src": "call:50", "kind": "writes", "dst": "artifact:7"},
            {"src": "call:61", "kind": "writes", "dst": "artifact:8"},
        ],
        "manifest": {"content_sha256": "2" * 64},
    }
    etiq = {
        "graph_kind": "etiq_native", "status": "available", "source_sha256": source_hash,
        "nodes": [
            {"id": "response-25", "kind": "etiq_state", "label": "a",
             "state_sha256": _canonical_hash({"invoice": "A"})},
            {"id": "response-38", "kind": "etiq_state", "label": "b",
             "state_sha256": _canonical_hash({"invoice": "B"})},
            {"id": "shared", "kind": "etiq_state", "label": "request_id",
             "state_sha256": _canonical_hash(7)},
            {"id": "response-60", "kind": "etiq_state", "label": "result",
             "state_sha256": _canonical_hash({"payment_request_id": 8})},
            {"id": "request-8", "kind": "etiq_state", "label": "request_id",
             "state_sha256": _canonical_hash(8)},
        ],
        "edges": [
            {"src": "response-25", "kind": "etiq_lineage", "dst": "shared"},
            {"src": "response-38", "kind": "etiq_lineage", "dst": "shared"},
            {"src": "response-60", "kind": "etiq_lineage", "dst": "request-8"},
        ],
        "manifest": {"content_sha256": "3" * 64},
    }
    graph, report = build_appworld_etiq_composite(appworld, trace, etiq, eligible())
    assert not any(
        edge["kind"] == "bridge_code_to_argument" and edge["join"]["call_index"] == 50
        for edge in graph["edges"]
    )
    ambiguity = next(item for item in report["ambiguous_joins"]
                     if item["bridge"] == "code_to_argument")
    assert ambiguity["candidate_upstream_response_call_indices"] == {
        "etiq:shared": [25, 38],
    }
    assert ambiguity["reason"] == "candidate has multiple upstream response occurrences"


def test_separate_conditions_do_not_add_or_rename_existing_arms():
    from rdr.v2_packager import ARMS_V2

    trace, appworld, etiq = fixture_layers()
    graph, _ = build_appworld_etiq_composite(appworld, trace, etiq, eligible())
    packages = build_etiq_conditions(trace, "file_system.files#7", etiq, graph)
    assert ARMS_V2 == (
        *tuple(chr(code) for code in range(ord("A"), ord("Z") + 1)),
        "STATE_CALLS", "STATE_CALLS_SOURCE",
    )
    assert tuple(package.arm for package in packages) == ETIQ_CONDITIONS
    audit = audit_etiq_conditions(packages, ["not-present-private-secret"])
    assert audit["passed"] is True
    assert all(package.metadata["utf8_bytes"] > 0 for package in packages)


def test_generic_reviewer_scheduler_consumes_both_condition_packages(tmp_path):
    from rdr.v2_review import plan_jobs

    packages = tmp_path / "instances" / "example" / "packages"
    packages.mkdir(parents=True)
    for condition in ETIQ_CONDITIONS:
        (packages / f"{condition}.txt").write_text(condition)
    assert {arm for _, arm, _ in plan_jobs(tmp_path)} == set(ETIQ_CONDITIONS)


def test_composite_manifest_binds_both_provenance_layers():
    trace, appworld, etiq = fixture_layers()
    graph, _ = build_appworld_etiq_composite(appworld, trace, etiq, eligible())
    assert graph["layers"]["appworld"]["content_sha256"] == "b" * 64
    assert graph["layers"]["etiq"]["content_sha256"] == "c" * 64
    payload = {key: value for key, value in graph.items() if key != "manifest"}
    assert graph["manifest"]["content_sha256"] == hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                   default=str).encode()
    ).hexdigest()


def test_zero_reachable_candidates_are_unlinked_not_ambiguous():
    trace, appworld, etiq = fixture_layers()
    etiq["nodes"].append({
        "id": "node-local", "kind": "etiq_state", "label": "local_constant",
        "state_sha256": _canonical_hash("request_id: 7"),
        "state_names": ["local_constant"], "source_line": 2,
    })
    graph, report = build_appworld_etiq_composite(appworld, trace, etiq, eligible())
    assert graph["graph_kind"] == "appworld_etiq_composite"
    assert any(item["candidate_count"] == 0 for item in report["unlinked_joins"]
               if item["bridge"] == "code_to_argument")
    assert all(item["candidate_count"] > 1 for item in report["ambiguous_joins"]
               if item["bridge"] == "code_to_argument")


def test_pre_occurrence_captures_do_not_pass_the_new_repeatability_gate():
    first = Path("runs/v2/etiq-composite-capture-v1-20261112/native/S01/S0R0/run-1")
    second = Path("runs/v2/etiq-composite-capture-v2-20261112/native/S01/S0R0/run-1")
    if not first.is_dir() or not second.is_dir():
        pytest.skip("versioned ETIQ regression captures are not installed")
    qualification = qualify_etiq_repeatability(first, second)
    assert qualification["deterministic_repeatability"] is False
    assert qualification["reason"] == "capture lacks occurrence-level projection metadata"


@pytest.mark.parametrize("instance_id", [
    "v8r2-1c7e03d76cdbb249",  # eight differing raw argument-binding edges
    "v8r2-37ef93242affb1ab",  # four differing raw argument-binding edges
])
def test_real_rejected_pairs_are_order_independent_and_packageable(instance_id, monkeypatch):
    capture_root = Path("runs/v2/build-v8r9-reliability-etiq-20261114/private/etiq")
    core = Path("runs/v2/build-v8r2-reliability-core-20261114")
    first, second = capture_root / instance_id / "run-1", capture_root / instance_id / "run-2"
    if not first.is_dir() or not second.is_dir():
        pytest.skip("V8R9 native regression captures are not installed")

    first_graph, _ = _project_native_etiq(first)
    second_graph, _ = _project_native_etiq(second)
    assert first_graph["counts"]["state_instances"] == second_graph["counts"]["state_instances"]
    assert first_graph["counts"]["operation_instances"] == second_graph["counts"]["operation_instances"]
    assert first_graph["counts"]["edge_instances"] == second_graph["counts"]["edge_instances"]
    assert json.dumps(first_graph, sort_keys=True) == json.dumps(second_graph, sort_keys=True)
    assert all(node["multiplicity"] == 1 for node in first_graph["nodes"])
    assert (first_graph["counts"]["edges"]
            + first_graph["counts"]["unattributed_edge_instances"]
            == first_graph["counts"]["edge_instances"])

    result, projection, inventory, targets = _scan_inputs(first)
    shuffled = copy.deepcopy(projection)
    random.Random(20261114).shuffle(shuffled["nodes"])
    random.Random(20261115).shuffle(shuffled["edges"])
    monkeypatch.setattr(
        "rdr.v2_etiq_export._scan_inputs",
        lambda scan: (result, shuffled, inventory, targets),
    )
    shuffled_graph, _ = _project_native_etiq(first)
    assert json.dumps(first_graph, sort_keys=True) == json.dumps(shuffled_graph, sort_keys=True)
    monkeypatch.undo()

    qualification = qualify_etiq_repeatability(first, second)
    etiq = import_native_etiq(first, qualification)
    trace = TraceV2.from_dict(json.loads(
        (core / "private/traces" / f"{instance_id}.json").read_text()
    ))
    appworld = json.loads(
        (core / "appworld_execution" / f"{instance_id}.json").read_text()
    )
    truth = json.loads((core / "private/truth" / f"{instance_id}.json").read_text())
    composite, report = build_appworld_etiq_composite(appworld, trace, etiq, qualification)
    packages = build_etiq_conditions(trace, truth["symptom"], etiq, composite)
    appworld = json.loads(
        (core / "appworld_execution" / f"{instance_id}.json").read_text()
    )
    truth = json.loads((core / "private/truth" / f"{instance_id}.json").read_text())
    composite, report = build_appworld_etiq_composite(appworld, trace, etiq, qualification)
    packages = build_etiq_conditions(trace, truth["symptom"], etiq, composite)
    for graph, schema_path in (
        (etiq, Path("schemas/v2/etiq_native.schema.json")),
        (composite, Path("schemas/v2/appworld_etiq_composite.schema.json")),
    ):
        schema = json.loads(schema_path.read_text())
        assert set(schema["required"]) <= set(graph)
        assert set(graph) <= set(schema["properties"])
        assert graph["graph_kind"] == schema["properties"]["graph_kind"]["const"]
    assert report["composite_eligibility"]["status"] == "eligible"
    assert audit_etiq_conditions(packages, ["private-value-not-present"])["passed"] is True


def test_import_requires_explicit_passed_repeatability_eligibility():
    scan = Path("runs/v2/etiq-composite-capture-v1-20261112/native/S01/S0R0/run-1")
    if not scan.is_dir():
        pytest.skip("versioned ETIQ regression capture is not installed")
    with pytest.raises(ValueError, match="eligibility did not pass"):
        import_native_etiq(scan, {
            "deterministic_repeatability": False,
            "workflow_only_eligibility": {"status": "blocked"},
        })


def test_frozen_extension_does_not_require_security_cases(tmp_path, monkeypatch):
    build = Path("runs/v2/build-v6-20261111")
    provenance = Path("runs/v2/reviewer-code-v6-codex-cli-final-20261111")
    if not build.is_dir() or not provenance.is_dir():
        pytest.skip("frozen V6 fixtures are not installed")
    output = tmp_path / "extension"
    monkeypatch.setattr("rdr.v2_provenance.verify_current_code_snapshot", lambda *args: [])
    monkeypatch.setattr("shutil.copytree", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("reached copy")))
    with pytest.raises(RuntimeError, match="reached copy"):
        extend_frozen_build_with_etiq(build, output, provenance)


def test_complete_etiq_coverage_requires_same_balanced_42_instances_in_both_conditions():
    truths = [{"instance_id": f"instance-{index:02d}"} for index in range(42)]
    authors = {
        truth["instance_id"]: "codex" if index < 21 else "dataset"
        for index, truth in enumerate(truths)
    }
    rows = [
        {"instance_id": truth["instance_id"], "arm": arm,
         "author": authors[truth["instance_id"]]}
        for truth in truths for arm in ETIQ_CONDITIONS
    ]
    audits = [{"instance_id": truth["instance_id"], "passed": True} for truth in truths]

    coverage = _verify_complete_etiq_coverage(truths, rows, audits, [])
    assert coverage["condition_packages"] == 84
    assert coverage["authors_by_condition"] == {
        arm: {"codex": 21, "dataset": 21} for arm in ETIQ_CONDITIONS
    }

    with pytest.raises(ValueError, match="exactly the frozen 42-instance population"):
        _verify_complete_etiq_coverage(truths, rows[:-1], audits, [])
    with pytest.raises(ValueError, match="coverage blocked"):
        _verify_complete_etiq_coverage(
            truths, rows, audits,
            [{"instance_id": "instance-00", "status": "blocked"}],
        )


def test_complete_graph_coverage_includes_the_two_state_graph_conditions():
    truths = [{"instance_id": f"instance-{index:02d}"} for index in range(42)]
    rows = [
        {
            "instance_id": truth["instance_id"],
            "arm": arm,
            "author": "codex" if index < 21 else "dataset",
        }
        for index, truth in enumerate(truths)
        for arm in ALL_ETIQ_CONDITIONS
    ]
    audits = [{"instance_id": truth["instance_id"], "passed": True} for truth in truths]

    coverage = _verify_complete_etiq_coverage(
        truths, rows, audits, [], ALL_ETIQ_CONDITIONS
    )

    assert coverage["condition_packages"] == 42 * len(ALL_ETIQ_CONDITIONS)
    assert set(coverage["authors_by_condition"]) == set(ALL_ETIQ_CONDITIONS)
