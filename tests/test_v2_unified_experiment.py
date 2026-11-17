import json
import hashlib
from collections import Counter
from pathlib import Path

import pytest

from rdr.v2_unified_experiment import ONE_SHOT_ARMS, freeze_one_shot_schedule
from rdr.v2_unified_review import (
    _bind_review_root, _corrected_o_counts, _crossed_summaries, _prior_response_ids,
    _run_identity, _summary, analyse_combined, corrected_o_eligible_nodes,
    corrected_o_step_schema, explore_corrected_o, fake_review, run_corrected_o,
    run_interactive, run_one_shot, validate_canonical_record, validate_corrected_o_step,
)
from rdr.graph import Edge, Graph
from rdr.trace import Trace
from rdr.v2_review import SYSTEM_PROMPT_V2
from rdr.v2_scorer import ANSWER_SCHEMA_V2, validate_answer_v2


def rows():
    return [
        {"instance_id": f"i{instance:02d}", "arm": arm,
         "package_sha256": f"{instance:02d}-{index:02d}"}
        for instance in range(42) for index, arm in enumerate(ONE_SHOT_ARMS)
    ]


def test_unified_arm_count_and_counterbalanced_schedule():
    assert len(ONE_SHOT_ARMS) == 30
    schedule = freeze_one_shot_schedule(rows())
    assert len(schedule["jobs"]) == 1260
    assert Counter(job["arm"] for job in schedule["jobs"]) == Counter({arm: 42 for arm in ONE_SHOT_ARMS})
    assert schedule == freeze_one_shot_schedule(rows())
    assert len(schedule["first_arm_counts"]) > 1


def test_prompt_schema_are_reused_unchanged(tmp_path: Path):
    record = fake_review("TASK\nx", tmp_path / "answer.json", SYSTEM_PROMPT_V2,
                         ANSWER_SCHEMA_V2, validate_answer_v2, "gpt-5.6-sol", "medium")
    assert record["schema_sha256"]
    assert record["system_prompt_sha256"]
    assert record["observed_tool_use"] is False
    attempt = json.loads((tmp_path / "answer.attempt-1.json").read_text())
    assert attempt["response_id"] == record["response_id"]


def test_fake_review_resume_fails_on_changed_package(tmp_path: Path):
    path = tmp_path / "answer.json"
    fake_review("a", path, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                validate_answer_v2, "gpt-5.6-sol", "medium")
    try:
        fake_review("b", path, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                    validate_answer_v2, "gpt-5.6-sol", "medium")
    except ValueError as error:
        assert "identity differs" in str(error)
    else:
        raise AssertionError("changed request identity resumed")


def _row(faulty: bool, class_hit: bool, exact: bool):
    row = {
        "truth_fault_occurred": faulty, "fault_occurred_correct": True,
        "residual_harm_correct": True, "detection_correct": True, "false_alarm": False,
        "fault_class_hit": class_hit, "false_fault_class_claim": not faulty and not class_hit,
        "complete_root_cause_set_recovered": exact,
    }
    for name in (
        "root_cause_source_precision", "root_cause_source_recall", "root_cause_event_precision",
        "root_cause_event_recall", "historical_artifact_precision", "historical_artifact_recall",
        "restored_artifact_precision", "restored_artifact_recall", "residual_artifact_precision",
        "residual_artifact_recall",
    ):
        row[name] = 1.0 if exact else 0.0
    return row


def test_fault_class_denominator_is_faulty_only_and_localization_is_counted():
    summary = _summary([_row(True, True, True), _row(True, False, False), _row(False, True, True)])
    assert summary["fault_class_accuracy_faulty_only"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert summary["complete_gold_root_cause_set_recovered"] == {
        "numerator": 1, "denominator": 2, "value": 0.5,
    }


def test_canonical_validation_requires_stateless_completed_usage(tmp_path: Path):
    path = tmp_path / "answer.json"
    record = fake_review("TASK\nx", path, SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2,
                         validate_answer_v2, "gpt-5.6-sol", "medium")
    assert validate_canonical_record(
        record, "TASK\nx", SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2, validate_answer_v2, set()
    ) == record["response_id"]
    broken = dict(record, previous_response_id="prior")
    with pytest.raises(ValueError, match="previous_response_id"):
        validate_canonical_record(
            broken, "TASK\nx", SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2, validate_answer_v2, set()
        )


def test_attempt_sidecars_are_not_calls_but_distinct_canonical_duplicates_fail(tmp_path: Path, monkeypatch):
    public, reviews = tmp_path / "public", tmp_path / "reviews"
    jobs = []
    for index in range(2):
        package = public / "instances" / f"i{index}" / "packages" / "A.txt"
        package.parent.mkdir(parents=True)
        package.write_text(f"TASK\n{index}")
        jobs.append({"instance_id": f"i{index}", "arm": "A",
                     "package_sha256": __import__("hashlib").sha256(package.read_bytes()).hexdigest()})
        fake_review(package.read_text(), reviews / "one_shot" / f"i{index}" / "A.json",
                    SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2, validate_answer_v2,
                    "gpt-5.6-sol", "medium")
    monkeypatch.setattr("rdr.v2_unified_review._one_shot_schedule", lambda _: {"jobs": jobs})
    ids = _prior_response_ids(public, reviews, ("one_shot",))
    assert len(ids) == 2  # each matching attempt sidecar carries the same ID but is not canonical
    first = json.loads((reviews / "one_shot/i0/A.json").read_text())["response_id"]
    second_path = reviews / "one_shot/i1/A.json"
    second = json.loads(second_path.read_text())
    second["response_id"] = first
    second_path.write_text(json.dumps(second))
    with pytest.raises(ValueError, match="duplicate response ID"):
        _prior_response_ids(public, reviews, ("one_shot",))


def test_early_run_identity_mismatch_is_rejected(tmp_path: Path):
    _bind_review_root(tmp_path / "reviews", {"build": "one"})
    with pytest.raises(ValueError, match="identity differs"):
        _bind_review_root(tmp_path / "reviews", {"build": "two"})


def test_real_shaped_fake_run_resumes_then_transitions_one_shot_to_n_to_o(tmp_path: Path, monkeypatch):
    build = Path("runs/v2/build-unified-v2-final-20261116")
    if not build.is_dir():
        pytest.skip("frozen unified build is not installed")
    public = build / "public"
    identity = json.loads((public / "build_identity.json").read_text())
    monkeypatch.setattr("rdr.v2_unified_review._review_preflight", lambda _: (public, identity))
    reviews = tmp_path / "reviews"
    expected_identity = _run_identity(build, public, identity)
    _bind_review_root(reviews, expected_identity)
    first = json.loads((public / "one_shot_job_order.json").read_text())["jobs"][0]
    package = public / "instances" / first["instance_id"] / "packages" / f"{first['arm']}.txt"
    fake_review(package.read_text(), reviews / "one_shot" / first["instance_id"] / f"{first['arm']}.json",
                SYSTEM_PROMPT_V2, ANSWER_SCHEMA_V2, validate_answer_v2,
                "gpt-5.6-sol", "medium")
    one = run_one_shot(build, reviews, fake_review, live=False)
    assert one["resumed"] == 1
    manifest = (reviews / "one_shot/MANIFEST.sha256.json").read_bytes()
    immutable = run_one_shot(build, reviews, fake_review, live=False)
    assert immutable["immutable_completed_stage"] is True
    assert (reviews / "one_shot/MANIFEST.sha256.json").read_bytes() == manifest
    n = run_interactive(build, reviews, "N", fake_review, live=False)
    assert n["instances"] == 42 and n["reviewer_calls"] == 84
    o = run_interactive(build, reviews, "O", fake_review, live=False)
    assert o["instances"] == 42 and o["reviewer_calls"] == 294
    canonical = reviews / "one_shot" / first["instance_id"] / f"{first['arm']}.json"
    canonical.write_text(canonical.read_text() + "\n")
    with pytest.raises(ValueError, match="stage is incomplete or changed"):
        run_one_shot(build, reviews, fake_review, live=False)


def test_crossed_summaries_are_per_arm_and_fault_dimension():
    repaired = _row(True, True, True) | {
        "arm": "A", "repair": "repaired", "fault_class": "source", "fault_id": "S01",
    }
    unrepaired = _row(True, False, False) | {
        "arm": "A", "repair": "unrepaired", "fault_class": "runtime", "fault_id": "R11",
    }
    clean = _row(False, True, True) | {
        "arm": "A", "repair": None, "fault_class": None, "fault_id": None,
    }
    crossed = _crossed_summaries([repaired, unrepaired, clean])
    assert set(crossed["arm_x_status"]["A"]) == {"clean", "repaired", "unrepaired"}
    assert set(crossed["arm_x_repair"]["A"]) == {"repaired", "unrepaired"}
    assert set(crossed["arm_x_fault_class"]["A"]) == {"runtime", "source"}
    assert set(crossed["arm_x_fault_id"]["A"]) == {"R11", "S01"}
    metric = crossed["arm_x_fault_id"]["A"]["S01"]["metrics"]["strict_joint_detection"]
    assert metric == {"numerator": 1, "denominator": 1, "value": 1.0}


def _chain_graph(length: int) -> Graph:
    calls = {f"call:{index}": f"{index} app.api()" for index in range(1, length + 1)}
    edges = [Edge("rec:db.table#1", "call:1", "reads")]
    edges += [Edge(f"call:{index}", f"call:{index + 1}", "feeds") for index in range(1, length)]
    return Graph(calls, ["rec:db.table#1"], edges)


def _walk_chain(length: int) -> tuple[dict, list[dict]]:
    graph = _chain_graph(length)
    schemas = []

    def ask(kind, package, round_number, schema, validator):
        if kind == "step":
            schemas.append(schema)
            answer = {"action": "expand", "node": schema["properties"]["node"]["enum"][0], "note": "ok"}
        else:
            answer = _empty_answer_for_test()
        validator(answer)
        return {"answer": answer, "response_id": f"r-{kind}-{round_number}",
                "usage": {"input_tokens": 1}, "wall_seconds": 0}

    result = explore_corrected_o(
        Trace("t", "instruction", "done", []), "db.table#1", "instance", ask, graph,
        "TASK\ninstruction\n\nFINAL MESSAGE\ndone",
    )
    return result, schemas


def _empty_answer_for_test() -> dict:
    return {"fault_occurred": False, "residual_harm_present": False, "fault_class": None,
            "root_cause_source_locations": [], "root_cause_event_indices": [],
            "historically_affected_artifacts": [], "restored_artifacts": [],
            "residual_harmful_artifacts": []}


def test_corrected_o_exhausts_frontier_before_six_and_dynamic_schema_is_exact():
    result, schemas = _walk_chain(2)
    assert result["valid_expansions"] == 2
    assert result["stopped_by"] == "frontier_exhausted"
    assert [schema["properties"]["node"]["enum"] for schema in schemas] == [["call:1"], ["call:2"]]
    assert result["eligible_nodes_before_requests"] == [
        {"round": 1, "nodes": ["call:1"]}, {"round": 2, "nodes": ["call:2"]},
    ]


def test_corrected_o_stops_at_six_valid_expansions_when_frontier_remains():
    graph = Graph(
        {f"call:{index}": f"{index} app.api()" for index in range(1, 9)},
        ["rec:db.table#1"],
        [Edge("rec:db.table#1", f"call:{index}", "reads") for index in range(1, 9)],
    )
    schemas = []

    def ask(kind, package, round_number, schema, validator):
        if kind == "step":
            schemas.append(schema)
            answer = {"action": "expand", "node": schema["properties"]["node"]["enum"][0], "note": "ok"}
        else:
            answer = _empty_answer_for_test()
        validator(answer)
        return {"answer": answer, "response_id": f"r-{kind}-{round_number}",
                "usage": {"input_tokens": 1}, "wall_seconds": 0}

    result = explore_corrected_o(
        Trace("t", "instruction", "done", []), "db.table#1", "instance", ask, graph,
        "TASK\ninstruction\n\nFINAL MESSAGE\ndone",
    )
    assert result["valid_expansions"] == 6
    assert result["stopped_by"] == "budget"
    assert len(schemas) == 6
    assert len(schemas[0]["properties"]["node"]["enum"]) == 8
    assert corrected_o_eligible_nodes(graph, ["rec:db.table#1", *result["selected_nodes"]])


@pytest.mark.parametrize("node", ["", "call:1", "call:999"])
def test_corrected_o_rejects_empty_repeated_and_invisible_nodes(node: str):
    with pytest.raises(ValueError, match="non-empty|not currently eligible"):
        validate_corrected_o_step({"action": "expand", "node": node, "note": "x"}, ["call:2"])
    assert corrected_o_step_schema(["call:2", "rec:x#1"])["properties"]["node"] == {
        "enum": ["call:2", "rec:x#1"]
    }


def _tree_digest(root: Path) -> tuple[int, str]:
    rows = [
        f"{path.relative_to(root).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(root.rglob("*")) if path.is_file()
    ]
    return len(rows), hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def test_completed_live_base_root_is_byte_identical():
    root = Path("runs/v2/reviews-unified-v2-final-correction-live-r1-20261116")
    if not root.is_dir():
        pytest.skip("completed live base review root is not installed")
    assert _tree_digest(root) == (5245, "bdd6cc81b3d7af53550b079cb1ac75717cb8a0c2452bc305dedfbc25eafd9585")


def test_corrected_o_all_42_simulation_resume_and_immutability(tmp_path: Path, monkeypatch):
    build = Path("runs/v2/build-unified-v2-o-correction-20261116")
    if not build.is_dir():
        pytest.skip("corrected O frozen build is not installed")
    public = build / "public"
    identity = json.loads((public / "build_identity.json").read_text())
    monkeypatch.setattr("rdr.v2_unified_review._review_preflight", lambda _: (public, identity))
    reviews = tmp_path / "corrected-o"
    calls = 0

    def interrupted(*args):
        nonlocal calls
        calls += 1
        if calls == 6:
            raise RuntimeError("simulated interruption")
        return fake_review(*args)

    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_corrected_o(build, reviews, interrupted, live=False)
    assert not (reviews / "O/MANIFEST.sha256.json").exists()
    result = run_corrected_o(build, reviews, fake_review, live=False)
    assert result["valid_expansions"] == 122
    assert result["final_calls"] == 42
    assert result["total_calls"] == 164
    assert result["repeated_or_invisible_or_empty"] == 0
    assert result["resumed"] == 5
    manifest = (reviews / "O/MANIFEST.sha256.json").read_bytes()
    immutable = run_corrected_o(build, reviews, fake_review, live=False)
    assert immutable["immutable_completed_stage"] is True
    assert immutable["new_reviewer_calls"] == 0
    assert (reviews / "O/MANIFEST.sha256.json").read_bytes() == manifest
    assert _corrected_o_counts(public, reviews)["total_calls"] == 164


def test_combined_analysis_uses_fake_base_one_shot_n_and_separate_corrected_o(tmp_path: Path, monkeypatch):
    base_build = Path("runs/v2/build-unified-v2-final-correction-20261116")
    corrected_build = Path("runs/v2/build-unified-v2-o-correction-20261116")
    if not base_build.is_dir() or not corrected_build.is_dir():
        pytest.skip("both unified frozen builds are not installed")

    def preflight(build: Path):
        public = build / "public"
        return public, json.loads((public / "build_identity.json").read_text())

    monkeypatch.setattr("rdr.v2_unified_review._review_preflight", preflight)
    base_reviews, corrected_reviews = tmp_path / "base", tmp_path / "corrected"
    run_one_shot(base_build, base_reviews, fake_review, live=False)
    run_interactive(base_build, base_reviews, "N", fake_review, live=False)
    assert not (base_reviews / "O").exists()
    run_corrected_o(corrected_build, corrected_reviews, fake_review, live=False)
    result = analyse_combined(
        base_build, corrected_build, base_reviews, corrected_reviews, tmp_path / "analysis",
    )
    assert result == {"evaluations": 1344, "arms": 32, "paired_comparisons": 496}
    identity = json.loads((tmp_path / "analysis/analysis_identity.json").read_text())
    assert identity["base_O_excluded"] is True
    assert identity["base_review_root"] != identity["corrected_O_review_root"]
