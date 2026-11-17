import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rdr.v2_openai_runner import (REVIEWER_EFFORT, REVIEWER_MODEL, ReviewError,
                                   codex_cli_version, parse_codex_jsonl,
                                   request_identity, review)
from rdr.v2_scorer import ANSWER_SCHEMA_V2, validate_answer_v2


ANSWER = {
    "fault_occurred": False, "residual_harm_present": False, "fault_class": None,
    "root_cause_source_locations": [], "root_cause_event_indices": [],
    "historically_affected_artifacts": [], "restored_artifacts": [],
    "residual_harmful_artifacts": [],
}


def jsonl(*events):
    return "".join(json.dumps(event) + "\n" for event in events)


def successful_jsonl(answer=ANSWER):
    return jsonl(
        {"type": "thread.started", "thread_id": "thread-unique"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {
            "id": "item-0", "type": "agent_message", "text": json.dumps(answer),
        }},
        {"type": "turn.completed", "usage": {
            "input_tokens": 12, "cached_input_tokens": 3, "output_tokens": 8,
            "reasoning_output_tokens": 2,
        }},
    )


@pytest.fixture(autouse=True)
def clear_version_cache():
    codex_cli_version.cache_clear()
    yield
    codex_cli_version.cache_clear()


def test_successful_structured_jsonl_has_usage_and_no_tools():
    result = parse_codex_jsonl(successful_jsonl(), REVIEWER_MODEL)
    assert result["response_id"] == "thread-unique"
    assert result["usage"]["input_tokens"] == 12
    assert result["observed_tool_use"] is False
    assert result["served_model_verification"] == "not_exposed_by_cli"
    assert result["item_types"] == ["agent_message"]


@pytest.mark.parametrize("item_type", [
    "command_execution", "file_change", "web_search", "mcp_tool_call", "subagent_call",
])
def test_every_tool_item_fails_closed(item_type):
    output = jsonl(
        {"type": "thread.started", "thread_id": "thread"},
        {"type": "turn.started"},
        {"type": "item.started", "item": {"type": item_type}},
        {"type": "item.completed", "item": {
            "type": "agent_message", "text": json.dumps(ANSWER),
        }},
        {"type": "turn.completed", "usage": {"input_tokens": 1}},
    )
    with pytest.raises(ReviewError, match="tool event"):
        parse_codex_jsonl(output, REVIEWER_MODEL)


@pytest.mark.parametrize("output,match", [
    ("not-json\n", "malformed Codex JSONL"),
    (jsonl({"type": "turn.started"},
           {"type": "turn.completed", "usage": {"input_tokens": 1}}), "final agent"),
    (jsonl({"type": "turn.started"}, {"type": "item.completed", "item": {
        "type": "agent_message", "text": json.dumps(ANSWER),
    }}, {"type": "turn.completed", "usage": {}}), "no usage"),
])
def test_malformed_missing_final_or_usage_fails_closed(output, match):
    with pytest.raises(ReviewError, match=match):
        parse_codex_jsonl(output, REVIEWER_MODEL)


def test_resume_identity_includes_cli_transport_and_invocation_settings():
    base = request_identity(
        "package", REVIEWER_MODEL, REVIEWER_EFFORT, "system", ANSWER_SCHEMA_V2, "codex-cli 1",
    )
    assert base["reviewer_transport"] == "codex_cli"
    assert base["codex_cli_version"] == "codex-cli 1"
    assert base["invocation_settings_sha256"]
    assert base["rendered_prompt_sha256"]
    changed = request_identity(
        "package", REVIEWER_MODEL, REVIEWER_EFFORT, "system", ANSWER_SCHEMA_V2, "codex-cli 2",
    )
    assert changed != base


def test_fresh_empty_ephemeral_call_and_api_credentials_not_consulted(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-forwarded")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "must-not-be-forwarded")

    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="codex-cli 0.test\n", stderr="")
        cwd = kwargs["cwd"]
        schema_path = Path(command[command.index("--output-schema") + 1])
        calls.append({"command": command, "cwd": cwd, "env": kwargs["env"],
                      "input": kwargs["input"], "contents": list(cwd.iterdir()),
                      "schema": json.loads(schema_path.read_text())})
        return SimpleNamespace(returncode=0, stdout=successful_jsonl(), stderr="")

    monkeypatch.setattr("rdr.v2_openai_runner.subprocess.run", fake_run)
    for number in (1, 2):
        record = review(
            f"package-{number}", tmp_path / f"review-{number}.json", "system",
            ANSWER_SCHEMA_V2, validate_answer_v2, waits=(), codex_binary="fake-codex",
        )
        assert record["answer"] == ANSWER
    assert len(calls) == 2 and calls[0]["cwd"] != calls[1]["cwd"]
    for call in calls:
        command = call["command"]
        assert call["contents"] == []
        assert "--ephemeral" in command and "--ignore-user-config" in command
        assert "--ignore-rules" in command and "read-only" in command
        assert "resume" not in command
        assert command[-1] == "-"
        assert "OPENAI_API_KEY" not in call["env"] and "OPENAI_ADMIN_KEY" not in call["env"]
        assert "package-" in call["input"]
        assert call["schema"] == ANSWER_SCHEMA_V2
        assert call["schema"]["properties"]["fault_class"]["enum"] == [
            None, "action", "source", "runtime", "mixed", "interaction", "amplified",
        ]


def test_nonzero_model_unavailable_is_terminal_and_not_retried(tmp_path, monkeypatch):
    executions = []

    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="codex-cli 0.test\n", stderr="")
        executions.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="model gpt-5.6-sol unavailable")

    monkeypatch.setattr("rdr.v2_openai_runner.subprocess.run", fake_run)
    with pytest.raises(ReviewError, match="unavailable"):
        review("package", tmp_path / "review.json", "system", ANSWER_SCHEMA_V2,
               validate_answer_v2, waits=(0,), codex_binary="fake-codex")
    assert len(executions) == 1


def test_malformed_final_answer_is_terminal(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="codex-cli 0.test\n", stderr="")
        return SimpleNamespace(returncode=0, stdout=successful_jsonl(answer={}), stderr="")

    monkeypatch.setattr("rdr.v2_openai_runner.subprocess.run", fake_run)
    with pytest.raises(ReviewError, match="schema mismatch"):
        review("package", tmp_path / "review.json", "system", ANSWER_SCHEMA_V2,
               validate_answer_v2, waits=(), codex_binary="fake-codex")
