import hashlib
import json
import sys
from pathlib import Path

import pytest

import rdr.runner as runner
from rdr.runner import ReviewError, build_command, review, review_with_backoff

FAKE = (sys.executable, str(Path(__file__).with_name("fake_claude.py")))
MODEL = "claude-haiku-5-5"
SIDE = "claude-haiku-4-5-20251001"
EXPECTED = {"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["splitwise.expenses#77"]}


def _review(tmp_path, name="r.json", package="PACKAGE", model=MODEL, effort="medium", **kwargs):
    workdir = tmp_path / "empty"
    workdir.mkdir(exist_ok=True)
    return review(package, tmp_path / "out" / name, model, effort, workdir, claude_cmd=FAKE, **kwargs)


def test_command_has_isolation_flags():
    cmd = build_command(MODEL, "medium")
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == MODEL and cmd[cmd.index("--effort") + 1] == "medium"
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--system-prompt", "--json-schema"):
        assert flag in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"


@pytest.mark.parametrize("mode", ["result", "structured", "fenced"])
def test_review_parses_each_output_shape(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("FAKE_MODE", mode)
    record = _review(tmp_path)
    assert record["answer"] == EXPECTED
    assert record["model_requested"] == MODEL and record["effort"] == "medium"
    assert MODEL in record["served_models"]


def test_package_arrives_on_stdin(tmp_path):
    record = _review(tmp_path, package="PACKAGE TEXT")
    assert record["usage"]["input_chars"] == len("PACKAGE TEXT")
    assert record["usage"]["input_sha256"] == hashlib.sha256(b"PACKAGE TEXT").hexdigest()
    assert record["package_sha256"] == hashlib.sha256(b"PACKAGE TEXT").hexdigest()


def test_review_resumes_from_saved_output(tmp_path, monkeypatch):
    first = _review(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "fail")
    assert _review(tmp_path) == first


@pytest.mark.parametrize("change", [{"package": "OTHER"}, {"model": "claude-other"}, {"effort": "high"}])
def test_resume_with_a_different_call_raises(tmp_path, monkeypatch, change):
    _review(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "fail")
    with pytest.raises(ReviewError, match="resume"):
        _review(tmp_path, **change)


def test_unreadable_saved_file_raises(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "r.json").write_text("{not json")
    with pytest.raises(ReviewError, match="unreadable"):
        _review(tmp_path)


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path, monkeypatch):
    replaced = []
    real_replace = runner.os.replace
    monkeypatch.setattr(runner.os, "replace", lambda src, dst: (replaced.append((src, dst)), real_replace(src, dst)))
    _review(tmp_path)
    assert len(replaced) == 1 and Path(replaced[0][1]) == tmp_path / "out" / "r.json"
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["r.json"]


def test_wrong_served_model_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVED", SIDE)
    with pytest.raises(ReviewError, match="served"):
        _review(tmp_path)


def test_known_side_model_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVED_EXTRA", SIDE)
    record = _review(tmp_path)
    assert record["served_models"] == sorted([MODEL, SIDE])


def test_unexpected_extra_served_model_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVED_EXTRA", "claude-opus-5-5")
    with pytest.raises(ReviewError, match="served"):
        _review(tmp_path)


def test_is_error_envelope_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "error_envelope")
    with pytest.raises(ReviewError, match="error"):
        _review(tmp_path)


def test_malformed_answer_raises_review_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "malformed")
    with pytest.raises(ReviewError, match="answer"):
        _review(tmp_path)
    assert not (tmp_path / "out" / "r.json").exists()


def test_non_json_output_raises_review_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "garbage")
    with pytest.raises(ReviewError):
        _review(tmp_path)


def test_timeout_raises_review_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "sleep")
    with pytest.raises(ReviewError, match="timed out"):
        _review(tmp_path, timeout=1)


def test_missing_cli_and_missing_workdir_raise_review_error(tmp_path):
    workdir = tmp_path / "empty"
    workdir.mkdir()
    with pytest.raises(ReviewError):
        review("P", tmp_path / "o.json", MODEL, "medium", workdir, claude_cmd=("no-such-claude-binary",))
    with pytest.raises(ReviewError):
        review("P", tmp_path / "o2.json", MODEL, "medium", tmp_path / "nope", claude_cmd=FAKE)


def test_failure_text_joins_stderr_and_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail_stdout")
    monkeypatch.setenv("FAKE_ERR", "stdout-only failure text")
    with pytest.raises(ReviewError, match="stdout-only failure text"):
        _review(tmp_path)


def test_nonempty_workdir_raises(tmp_path):
    workdir = tmp_path / "busy"
    workdir.mkdir()
    (workdir / "answers.json").write_text("{}")
    with pytest.raises(ReviewError, match="empty"):
        review("PACKAGE", tmp_path / "out.json", MODEL, "medium", workdir, claude_cmd=FAKE)


def test_backoff_retries_on_limit_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    waits = []
    workdir = tmp_path / "empty"
    workdir.mkdir()
    with pytest.raises(ReviewError, match="limit"):
        review_with_backoff("PACKAGE", tmp_path / "out.json", MODEL, "medium", workdir,
                            claude_cmd=FAKE, waits=(1, 2), sleep_fn=waits.append)
    assert waits == [1, 2]


@pytest.mark.parametrize("text", ["Rate limit hit", "API rate_limit_error", "server overloaded", "HTTP 429 too many"])
def test_backoff_retries_on_other_transient_markers(tmp_path, monkeypatch, text):
    monkeypatch.setenv("FAKE_MODE", "fail")
    monkeypatch.setenv("FAKE_ERR", text)
    waits = []
    workdir = tmp_path / "empty"
    workdir.mkdir()
    with pytest.raises(ReviewError):
        review_with_backoff("PACKAGE", tmp_path / "out.json", MODEL, "medium", workdir,
                            claude_cmd=FAKE, waits=(1,), sleep_fn=waits.append)
    assert waits == [1]


def test_backoff_does_not_retry_a_non_limit_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    monkeypatch.setenv("FAKE_ERR", "Prompt exceeds the context length limit")
    count = tmp_path / "count.txt"
    monkeypatch.setenv("FAKE_COUNT_FILE", str(count))
    waits = []
    workdir = tmp_path / "empty"
    workdir.mkdir()
    with pytest.raises(ReviewError, match="context length"):
        review_with_backoff("PACKAGE", tmp_path / "out.json", MODEL, "medium", workdir,
                            claude_cmd=FAKE, waits=(1, 2), sleep_fn=waits.append)
    assert waits == [] and len(count.read_text().splitlines()) == 1


def test_record_keeps_the_full_envelope_wall_time_and_stdout_hash(tmp_path):
    record = _review(tmp_path)
    assert record["envelope"]["is_error"] is False
    assert set(record["envelope"]["modelUsage"]) == {MODEL}
    assert json.loads(record["envelope"]["result"]) == EXPECTED
    assert isinstance(record["wall_seconds"], float) and record["wall_seconds"] >= 0
    assert len(record["stdout_sha256"]) == 64
    saved = json.loads((tmp_path / "out" / "r.json").read_text())
    assert saved["envelope"] == record["envelope"] and saved["stdout_sha256"] == record["stdout_sha256"]


def _failed(tmp_path, name="r.failed.json"):
    return json.loads((tmp_path / "out" / name).read_text())


@pytest.mark.parametrize("mode, env, reason", [
    ("fail", {"FAKE_ERR": "boom on stderr"}, "boom on stderr"),
    ("fail_stdout", {"FAKE_ERR": "boom on stdout"}, "boom on stdout"),
    ("garbage", {}, "envelope"),
    ("malformed", {}, "malformed answer"),
    ("error_envelope", {}, "error"),
    ("result", {"FAKE_SERVED": SIDE}, "served"),
])
def test_failures_after_the_subprocess_ran_leave_a_failed_record(tmp_path, monkeypatch, mode, env, reason):
    monkeypatch.setenv("FAKE_MODE", mode)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ReviewError):
        _review(tmp_path, package="PKG")
    failed = _failed(tmp_path)
    assert reason in failed["reason"]
    assert {"stdout", "stderr", "reason", "model", "effort", "package_sha256"} <= set(failed)
    assert failed["model"] == MODEL and failed["effort"] == "medium"
    assert failed["package_sha256"] == hashlib.sha256(b"PKG").hexdigest()
    assert not (tmp_path / "out" / "r.json").exists()
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["r.failed.json"]


def test_failed_record_keeps_raw_stdout_and_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    monkeypatch.setenv("FAKE_ERR", "visible failure text")
    with pytest.raises(ReviewError):
        _review(tmp_path)
    assert "visible failure text" in _failed(tmp_path)["stderr"]
    monkeypatch.setenv("FAKE_MODE", "malformed")
    with pytest.raises(ReviewError):
        _review(tmp_path)
    assert "anything_wrong" in _failed(tmp_path)["stdout"]


def test_a_later_success_still_writes_the_normal_record(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    with pytest.raises(ReviewError):
        _review(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "result")
    assert _review(tmp_path)["answer"] == EXPECTED


def test_resume_with_a_different_system_prompt_raises(tmp_path, monkeypatch):
    first = _review(tmp_path)
    assert len(first["command_sha256"]) == 64
    monkeypatch.setenv("FAKE_MODE", "fail")
    monkeypatch.setattr(runner, "SYSTEM_PROMPT", runner.SYSTEM_PROMPT + " Be brief.")
    with pytest.raises(ReviewError, match="command_sha256"):
        _review(tmp_path)


def test_command_hash_excludes_the_executable(tmp_path):
    expected = hashlib.sha256(json.dumps(build_command(MODEL, "medium")[1:]).encode()).hexdigest()
    assert _review(tmp_path)["command_sha256"] == expected


def test_backoff_does_not_retry_when_429_is_part_of_a_longer_number(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    monkeypatch.setenv("FAKE_ERR", "Prompt has 1429 tokens")
    waits = []
    workdir = tmp_path / "empty"
    workdir.mkdir()
    with pytest.raises(ReviewError, match="1429"):
        review_with_backoff("PACKAGE", tmp_path / "out.json", MODEL, "medium", workdir,
                            claude_cmd=FAKE, waits=(1, 2), sleep_fn=waits.append)
    assert waits == []


def test_saved_record_is_valid_json_with_integrity_fields(tmp_path):
    _review(tmp_path)
    saved = json.loads((tmp_path / "out" / "r.json").read_text())
    assert {"package_sha256", "model_requested", "effort", "answer", "served_models", "usage"} <= set(saved)
