import sys
from pathlib import Path

import pytest

from rdr.runner import ReviewError, build_command, review, review_with_backoff

FAKE = (sys.executable, str(Path(__file__).with_name("fake_claude.py")))
MODEL = "claude-haiku-5-5"
EXPECTED = {"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["splitwise.expenses#77"]}


def _review(tmp_path, name="r.json"):
    workdir = tmp_path / "empty"
    workdir.mkdir(exist_ok=True)
    return review("PACKAGE", tmp_path / "out" / name, MODEL, "medium", workdir, claude_cmd=FAKE)


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


def test_review_resumes_from_saved_output(tmp_path, monkeypatch):
    first = _review(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "fail")
    assert _review(tmp_path) == first


def test_wrong_served_model_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVED", "claude-haiku-4-5-20251001")
    with pytest.raises(ReviewError, match="served"):
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
