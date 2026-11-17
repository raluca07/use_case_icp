import json

from rdr.trace import Call, Trace, Write
from rdr.truth import Truth
from rdr.v2_schema import CallV2, TraceV2, TruthV2, load_trace, load_truth, save_v2, with_observed_response


def test_v2_raw_and_observed_responses_are_distinct(tmp_path):
    trace = TraceV2("t", "do", "done", [CallV2(0, "x", "read", {}, {"v": 1}, {"v": 1})], {"w.py": "x"})
    changed = with_observed_response(trace, 0, {"v": 2})
    assert changed.calls[0].raw_response == {"v": 1}
    assert changed.calls[0].observed_response == {"v": 2}


def test_explicit_v1_v2_loaders(tmp_path):
    v1_trace = Trace("t", "do", "done", [Call(0, "x", "write", {}, {}, [Write("x.rows#1", None, {})])])
    v1_path = tmp_path / "v1_trace.json"
    v1_trace.save(v1_path)
    assert isinstance(load_trace(v1_path), Trace)
    v1_truth = Truth("i", True, 0, ["x.rows#1"], [], "x.rows#1")
    v1_truth_path = tmp_path / "v1_truth.json"
    v1_truth.save(v1_truth_path)
    assert isinstance(load_truth(v1_truth_path), Truth)

    v2 = TraceV2("t", "do", "done", [CallV2(0, "x", "read", {}, 1, 1)], {"w.py": "x"})
    v2_path = tmp_path / "v2.json"
    save_v2(v2, v2_path)
    assert isinstance(load_trace(v2_path), TraceV2)
    truth = TruthV2("i", True, True, "R01", "runtime", "unrepaired", [], [0],
                    ["x.rows#1"], [], ["x.rows#1"], "x.rows#1", "dataset")
    truth_path = tmp_path / "truth2.json"
    save_v2(truth, truth_path)
    assert isinstance(load_truth(truth_path), TruthV2)


def test_legacy_v2_truth_remains_loadable(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "instance_id": "old", "fault_present": True, "fault_id": "L01",
        "fault_class": "action", "repair": "repaired", "source_locations": [],
        "runtime_events": [1], "first_harmful_event": 1,
        "affected_artifacts": ["x#1"], "symptom": "x#1", "author": "codex",
        "schema_version": 2,
    }))
    truth = load_truth(path)
    assert isinstance(truth, TruthV2)
    assert truth.fault_occurred and truth.residual_harm_present
    assert truth.root_cause_source_locations == []
    assert truth.root_cause_event_indices == [1]
    assert truth.schema_version == 4
