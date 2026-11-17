import json

from rdr.v2_graphs import build_authoring_graph, check_source_link, execution_graph_summary
from rdr.v2_schema import CallV2, TraceV2
from rdr.trace import Write


def test_graph_kinds_and_final_source_link(tmp_path):
    (tmp_path / "authoring.json").write_text(json.dumps({
        "task_sha256": "t", "api_inventory_sha256": "d", "solution_sha256": "s",
        "served_model": "gpt-5.6-sol", "served_effort": "medium",
    }))
    (tmp_path / "codex_stdout.jsonl").write_text("")
    authoring = build_authoring_graph(tmp_path)
    trace = TraceV2("t", "i", "f", [CallV2(0, "x", "read", {}, {"v": 1}, {"v": 2})], {"w.py": "x"})
    execution = execution_graph_summary(trace, "s", "r1")
    assert authoring["graph_kind"] == "codex_authoring" and authoring["private"]
    assert execution["graph_kind"] == "appworld_execution"
    assert check_source_link(authoring, execution)
    assert execution["calls"][0]["raw_response_sha256"] != execution["calls"][0]["observed_response_sha256"]


def test_created_artifact_is_written_but_not_fabricated_as_read():
    trace = TraceV2("t", "i", "f", [
        CallV2(0, "x", "create", {}, {"id": 1}, {"id": 1},
               [Write("x.rows#1", None, {"id": 1})]),
    ], {"workflow.py": "x"})
    graph = execution_graph_summary(trace, "s", "r")
    kinds = [edge["kind"] for edge in graph["edges"]]
    assert "writes" in kinds
    assert "reads" not in kinds
    assert "observed_as" in kinds


def test_schema_addressed_later_call_reads_the_captured_record_version():
    trace = TraceV2("t", "i", "f", [
        CallV2(0, "venmo", "create_payment_request", {}, {"payment_request_id": 7},
               {"payment_request_id": 7}, [Write("venmo.payment_requests#7", None, {"id": 7})]),
        CallV2(1, "venmo", "update_payment_request", {"payment_request_id": 7}, {}, {}),
    ], {"workflow.py": "x"})
    graph = execution_graph_summary(trace, "s", "r")
    assert any(edge["kind"] == "reads" and edge["dst"] == "call:1"
               and edge["src"].startswith("artifact:after:") for edge in graph["edges"])
