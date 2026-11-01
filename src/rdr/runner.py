"""Isolated `claude -p` reviewer: one fresh session per package, pinned model and effort."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "anything_wrong": {"type": "boolean"},
        "origin_call": {"type": ["integer", "null"]},
        "still_wrong_records": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["anything_wrong", "origin_call", "still_wrong_records"],
    "additionalProperties": False,
}

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
    return json.loads(text[start:end + 1])


def parse_output(stdout: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ReviewError("empty output")
    envelope = json.loads(lines[-1])
    answer = envelope.get("structured_output") or _extract_json(envelope.get("result") or "")
    return {
        "answer": answer,
        "served_models": sorted((envelope.get("modelUsage") or {}).keys()),
        "usage": envelope.get("usage") or {},
        "is_error": bool(envelope.get("is_error")),
    }


def review(package_text: str, out_path: Path, model: str, effort: str, workdir: Path,
           claude_cmd=("claude",), timeout: int = 900) -> dict:
    if out_path.exists():
        return json.loads(out_path.read_text())
    if any(workdir.iterdir()):
        raise ReviewError(f"workdir must be empty: {workdir}")
    proc = subprocess.run(build_command(model, effort, claude_cmd), input=package_text,
                          capture_output=True, text=True, cwd=workdir, timeout=timeout)
    if proc.returncode != 0:
        raise ReviewError((proc.stderr or proc.stdout)[-2000:])
    record = parse_output(proc.stdout)
    if record["is_error"]:
        raise ReviewError(f"reviewer reported an error: {proc.stdout[-500:]}")
    if model not in record["served_models"]:
        raise ReviewError(f"requested {model}, served {record['served_models']}")
    record.update(model_requested=model, effort=effort)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def review_with_backoff(*args, waits=(60, 300, 1800), sleep_fn=time.sleep, **kwargs) -> dict:
    for wait in (*waits, None):
        try:
            return review(*args, **kwargs)
        except ReviewError as err:
            if wait is None or "limit" not in str(err).lower():
                raise
            sleep_fn(wait)
