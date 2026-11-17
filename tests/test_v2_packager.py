import pytest

from rdr.trace import Write
from rdr.v2_packager import ARMS_V2, audit_packages, build_package_v2
from rdr.v2_graphs import execution_graph_summary
from rdr.v2_schema import CallV2, TraceV2


def sample_trace():
    source = "def solution(apis, requester):\n    return apis.payments.create(amount=5)\n"
    calls = [
        CallV2(0, "users", "search", {"query": "a"}, [{"id": 1}], [{"id": 1}], [], ["solution/search"]),
        CallV2(1, "payments", "create", {"user_id": 1, "amount": 5}, {"id": 8}, {"id": 8},
               [Write("payments.requests#8", None, {"amount": 5})], ["solution/create"]),
        CallV2(2, "files", "create", {"file_path": "~/r.txt"}, {"ok": True}, {"ok": True},
               [Write("files.files#3", None, {"path": "~/r.txt"})], ["solution/create"]),
    ]
    return TraceV2("t", "Create a request and receipt.", "done", calls, {"workflow.py": source}, author="codex")


def task_states():
    return ({"messages": [{"amount": 5}], "requests": []},
            {"messages": [{"amount": 5}], "requests": [{"amount": 5}]})


def package(arm, trace=None):
    initial, final = task_states()
    return build_package_v2(
        arm, trace or sample_trace(), "payments.requests#8", "i", 1,
        initial_task_state=initial, final_task_state=final,
    )


def test_all_arms_and_isolation():
    trace = sample_trace()
    arms = [arm for arm in ARMS_V2 if arm not in {"N", "O"}]
    initial, final = task_states()
    packages = [build_package_v2(
        arm, trace, "payments.requests#8", "i", anchor_index=1,
        initial_task_state=initial, final_task_state=final,
    ) for arm in arms]
    assert [package.arm for package in packages] == arms
    audit = audit_packages(packages, ["R01", "unrepaired", "workflow.py:2"])
    assert audit["passed"]
    assert all(package.metadata["package_sha256"] for package in packages)
    assert all(package.metadata["truncated"] is False for package in packages)
    assert all(package.metadata["context_preflight_passed"] for package in packages)
    assert all(package.metadata["section_sizes"] for package in packages)


def test_source_only_in_source_arms_and_nested_pairs_share_open_graph():
    trace = sample_trace()
    initial, final = task_states()
    packages = {arm: build_package_v2(
                    arm, trace, "payments.requests#8", "i", 1,
                    initial_task_state=initial, final_task_state=final)
                for arm in ARMS_V2 if arm not in {"N", "O"}}
    assert "EXECUTED WORKFLOW SOURCE" not in packages["B"].text
    assert "EXECUTED WORKFLOW SOURCE" in packages["P"].text
    assert packages["S"].common == packages["T"].common == packages["U"].common == packages["V"].common
    assert "COLLAPSED EXECUTION GROUPS" in packages["S"].text
    assert "PROVENANCE GRAPH" in packages["T"].text


def test_user_report_is_removed_and_w_omits_call_index():
    trace = sample_trace()
    packages = {arm: build_package_v2(arm, trace, "payments.requests#8", "i", 1)
                for arm in ("A", "I", "W")}
    assert all("USER REPORT" not in package.text for package in packages.values())
    assert "CALLS MADE (index and API only)" in packages["A"].text
    assert "CALLS MADE (index and API only)" in packages["I"].text
    assert "CALL INPUTS" in packages["I"].text
    assert "CALLS MADE (index and API only)" not in packages["W"].text
    assert set(packages["W"].sections) == {"common"}
    assert packages["A"].common == packages["I"].common == packages["W"].common


def test_state_and_source_ablations_are_factorial():
    packages = {arm: package(arm) for arm in (
        "W", "X", "Y", "Z", "STATE_CALLS", "STATE_CALLS_SOURCE"
    )}
    assert set(packages["W"].sections) == {"common"}
    assert set(packages["X"].sections) == {"common", "source"}
    assert set(packages["Y"].sections) == {"common"}
    assert set(packages["Z"].sections) == {"common", "source"}
    assert set(packages["STATE_CALLS"].sections) == {"common", "call_index"}
    assert set(packages["STATE_CALLS_SOURCE"].sections) == {"common", "call_index", "source"}
    assert "INITIAL TASK INPUTS" not in packages["W"].text
    assert "INITIAL TASK INPUTS" in packages["Y"].text
    assert "FINAL TASK STATE" in packages["Y"].text
    assert "CALLS MADE" not in packages["Y"].text
    assert "CALLS MADE" in packages["STATE_CALLS"].text
    assert "EXECUTED WORKFLOW SOURCE" in packages["X"].text
    assert "EXECUTED WORKFLOW SOURCE" in packages["Z"].text


def test_state_ablations_accept_the_frozen_execution_graph_used_by_live_builds():
    trace = sample_trace()
    initial, final = task_states()
    execution = execution_graph_summary(trace, "source-hash", "run-1")
    packages = {
        arm: build_package_v2(
            arm, trace, "payments.requests#8", "i", 1, execution,
            initial_task_state=initial, final_task_state=final,
        )
        for arm in ("Y", "Z", "STATE_CALLS", "STATE_CALLS_SOURCE")
    }
    assert all("INITIAL TASK INPUTS" in package.text for package in packages.values())
    assert "PROVENANCE GRAPH" not in packages["STATE_CALLS_SOURCE"].text


def test_interactive_arms_cannot_be_serialized_as_static_instructions():
    for arm in ("N", "O"):
        with pytest.raises(ValueError, match="interactive"):
            build_package_v2(arm, sample_trace(), "payments.requests#8", "i", 1)


def test_fabio_flat_and_nested_views_share_one_frozen_execution_graph():
    trace = sample_trace()
    execution = execution_graph_summary(trace, "source-hash", "run-1")
    packages = {
        arm: build_package_v2(arm, trace, "payments.requests#8", "i", 1, execution)
        for arm in ("B", "C", "G", "J", "P", "Q", "S", "T", "U", "V")
    }
    assert "response:raw:" not in packages["C"].sections["graph"]
    assert "invocation:" not in packages["C"].sections["graph"]
    assert "amount=5" in packages["G"].sections["graph"]
    assert "amount=5" not in packages["J"].sections["graph"]
    assert {key: value for key, value in packages["Q"].sections.items() if key != "source"} == packages["G"].sections
    assert packages["S"].metadata["underlying_graph_sha256"] == packages["T"].metadata["underlying_graph_sha256"]
    assert packages["U"].metadata["underlying_graph_sha256"] == packages["V"].metadata["underlying_graph_sha256"]


def test_fabio_log_arms_are_complete_and_interleaved():
    trace = sample_trace()
    for arm in ("B", "G", "H"):
        package = build_package_v2(arm, trace, "payments.requests#8", "i", 1)
        log = package.sections["action_log"]
        assert "CALL INPUTS" not in log and "OBSERVED RESPONSES" not in log
        assert log.index("[0] users.search") < log.index("[0] ->") < log.index("[1] payments.create")
