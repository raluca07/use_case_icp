"""Isolated `claude -p` reviewer: one fresh session per package, pinned model and effort."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from rdr.answer import ANSWER_SCHEMA, validate_answer

__all__ = ["ANSWER_SCHEMA", "KNOWN_SIDE_MODELS", "ReviewError", "build_command", "parse_output", "review",
           "review_with_backoff"]

KNOWN_SIDE_MODELS = frozenset({"claude-haiku-4-5-20251001"})
RETRY_PATTERN = re.compile(r"usage limit|rate limit|rate_limit|overloaded|\b429\b")

SYSTEM_PROMPT = (
    "You review the record of an automated assistant's work in a user's apps. "
    "Use only the evidence in the message. Answer three questions. "
    "anything_wrong: is any record in the final state wrong for the task? "
    "origin_call: the index of the call that started the problem, or null if nothing is wrong. "
    "still_wrong_records: every record label, written exactly as in the evidence, that is still wrong. "
    "Reply with JSON matching the schema and nothing else."
)


class ReviewError(RuntimeError):
    pass


def build_command(model: str, effort: str, claude_cmd=("claude",)) -> list[str]:
    return [*claude_cmd, "-p",
            "--model", model,
            "--effort", effort,
            "--tools", "",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--system-prompt", SYSTEM_PROMPT,
            "--json-schema", json.dumps(ANSWER_SCHEMA, sort_keys=True),
            "--no-session-persistence",
            "--output-format", "json"]


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ReviewError(f"no JSON object in result: {text[:200]!r}")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as err:
        raise ReviewError(f"result is not valid JSON: {err}") from err


def parse_output(stdout: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ReviewError("empty output")
    try:
        envelope = json.loads(lines[-1])
    except json.JSONDecodeError as err:
        raise ReviewError(f"envelope is not valid JSON: {lines[-1][:200]!r}") from err
    if not isinstance(envelope, dict):
        raise ReviewError(f"envelope is not an object: {lines[-1][:200]!r}")
    is_error = bool(envelope.get("is_error"))
    answer = None
    if not is_error:
        answer = envelope.get("structured_output")
        if answer is None:
            answer = _extract_json(envelope.get("result") or "")
    return {
        "answer": answer,
        "served_models": sorted((envelope.get("modelUsage") or {}).keys()),
        "usage": envelope.get("usage") or {},
        "is_error": is_error,
        "envelope": envelope,
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _command_sha256(model: str, effort: str) -> str:
    return _sha256(json.dumps(build_command(model, effort)[1:]))


def _load_saved(out_path: Path, package_sha256: str, model: str, effort: str) -> dict:
    try:
        saved = json.loads(out_path.read_text())
    except (OSError, ValueError) as err:
        raise ReviewError(f"saved review is unreadable: {out_path}: {err}") from err
    if not isinstance(saved, dict):
        raise ReviewError(f"saved review is unreadable: {out_path}: not an object")
    current = {"package_sha256": package_sha256, "model_requested": model, "effort": effort,
               "command_sha256": _command_sha256(model, effort)}
    differing = sorted(k for k, v in current.items() if saved.get(k) != v)
    if differing:
        raise ReviewError(f"cannot resume {out_path}: saved review differs in {differing}")
    return saved


def _write_atomic(out_path: Path, record: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=out_path.parent, prefix=out_path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(record, indent=2, sort_keys=True))
        os.replace(tmp_name, out_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def review(package_text: str, out_path: Path, model: str, effort: str, workdir: Path,
           claude_cmd=("claude",), timeout: int = 900) -> dict:
    package_sha256 = _sha256(package_text)
    if out_path.exists():
        return _load_saved(out_path, package_sha256, model, effort)
    started = time.monotonic()
    try:
        if any(workdir.iterdir()):
            raise ReviewError(f"workdir must be empty: {workdir}")
        proc = subprocess.run(build_command(model, effort, claude_cmd), input=package_text,
                              capture_output=True, text=True, cwd=workdir, timeout=timeout)
    except FileNotFoundError as err:
        raise ReviewError(f"cannot run reviewer: {err}") from err
    except subprocess.TimeoutExpired as err:
        raise ReviewError(f"reviewer timed out after {timeout}s") from err
    wall_seconds = time.monotonic() - started
    try:
        record = _check_run(proc, model)
    except ReviewError as err:
        _write_atomic(out_path.with_name(out_path.stem + ".failed.json"), {
            "stdout": proc.stdout, "stderr": proc.stderr, "reason": str(err), "model": model, "effort": effort,
            "package_sha256": package_sha256, "wall_seconds": wall_seconds})
        raise
    record.update(model_requested=model, effort=effort, package_sha256=package_sha256,
                  command_sha256=_command_sha256(model, effort), wall_seconds=wall_seconds,
                  stdout_sha256=_sha256(proc.stdout))
    _write_atomic(out_path, record)
    return record


def _check_run(proc, model: str) -> dict:
    if proc.returncode != 0:
        raise ReviewError("\n".join(part for part in (proc.stderr, proc.stdout) if part)[-2000:])
    record = parse_output(proc.stdout)
    if record["is_error"]:
        raise ReviewError(f"reviewer reported an error: {proc.stdout[-500:]}")
    try:
        validate_answer(record["answer"])
    except ValueError as err:
        raise ReviewError(f"malformed answer: {err}") from err
    served = record["served_models"]
    if model not in served or any(m != model and m not in KNOWN_SIDE_MODELS for m in served):
        raise ReviewError(f"requested {model}, served {served}")
    return record


def review_with_backoff(*args, waits=(60, 300, 1800), sleep_fn=time.sleep, **kwargs) -> dict:
    for wait in (*waits, None):
        try:
            return review(*args, **kwargs)
        except ReviewError as err:
            if wait is None or not RETRY_PATTERN.search(str(err).lower()):
                raise
            sleep_fn(wait)
