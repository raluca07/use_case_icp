"""Stateless Codex CLI transport for the active V2 reviewer."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path


REVIEWER_MODEL = "gpt-5.6-sol"
REVIEWER_EFFORT = "medium"
REVIEWER_TRANSPORT = "codex_cli"
REVIEWER_HARNESS = "codex_agent"
PROMPT_BEGIN = "<BEGIN_FROZEN_REVIEW_EVIDENCE>"
PROMPT_END = "<END_FROZEN_REVIEW_EVIDENCE>"
ALLOWED_ITEM_TYPES = {"agent_message", "reasoning"}
TRANSIENT_PATTERNS = ("timed out", "timeout", "rate limit", "connection", "network", "temporarily unavailable")
ENV_KEYS = (
    "HOME", "CODEX_HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
)


class ReviewError(RuntimeError):
    pass


def _sha(value: str | dict) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _minimal_env() -> dict[str, str]:
    """Pass auth location and process essentials, never API credentials."""
    return {key: os.environ[key] for key in ENV_KEYS if key in os.environ}


@functools.lru_cache(maxsize=1)
def codex_cli_version(codex_binary: str = "codex") -> str:
    process = subprocess.run(
        [codex_binary, "--version"], capture_output=True, text=True, env=_minimal_env(), timeout=30,
    )
    if process.returncode != 0 or not process.stdout.strip():
        raise ReviewError(f"Codex CLI version check failed: {(process.stderr or process.stdout).strip()}")
    return process.stdout.strip()


def codex_login_preflight(codex_binary: str = "codex") -> dict:
    process = subprocess.run(
        [codex_binary, "login", "status"], capture_output=True, text=True,
        env=_minimal_env(), timeout=30,
    )
    status = (process.stdout or process.stderr).strip()
    if process.returncode != 0 or "logged in" not in status.lower():
        raise ReviewError(f"Codex CLI is not authenticated: {status}")
    return {
        "authenticated": True,
        "status": status,
        "codex_cli_version": codex_cli_version(codex_binary),
        "api_credentials_consulted": False,
    }


def render_prompt(system_prompt: str, package: str) -> str:
    return f"{system_prompt}\n\n{PROMPT_BEGIN}\n{package}\n{PROMPT_END}\n"


def _invocation_settings(model: str, effort: str) -> dict:
    return {
        "approval": "never", "ephemeral": True, "ignore_user_config": True,
        "ignore_rules": True, "sandbox": "read-only", "skip_git_repo_check": True,
        "color": "never", "jsonl": True, "stdin_prompt": True,
        "output_schema": True, "model": model, "reasoning_effort": effort,
    }


def request_identity(package: str, model: str, effort: str, system_prompt: str, schema: dict,
                     cli_version: str | None = None) -> dict:
    prompt = render_prompt(system_prompt, package)
    version = cli_version or codex_cli_version()
    return {
        "model_requested": model,
        "reasoning_effort": effort,
        "reviewer_transport": REVIEWER_TRANSPORT,
        "reviewer_harness": REVIEWER_HARNESS,
        "codex_cli_version": version,
        "invocation_settings_sha256": _sha(_invocation_settings(model, effort)),
        "system_prompt_sha256": _sha(system_prompt),
        "rendered_prompt_sha256": _sha(prompt),
        "schema_sha256": _sha(schema),
        "package_sha256": _sha(package),
    }


def _command(codex_binary: str, model: str, effort: str, cwd: Path, schema_path: Path) -> list[str]:
    return [
        codex_binary, "-a", "never", "exec", "--json", "--ephemeral",
        "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only",
        "--skip-git-repo-check", "--color", "never", "-m", model,
        "-c", f'model_reasoning_effort="{effort}"', "-C", str(cwd),
        "--output-schema", str(schema_path), "-",
    ]


def _normalized_command(command: list[str], cwd: Path, schema_path: Path) -> list[str]:
    return ["<EMPTY_WORKDIR>" if item == str(cwd) else "<SCHEMA>" if item == str(schema_path) else item
            for item in command]


def _served_model(events: list[dict]) -> str | None:
    for event in events:
        for key in ("model", "model_slug"):
            value = event.get(key)
            if isinstance(value, str):
                return value
        thread = event.get("thread")
        if isinstance(thread, dict):
            for key in ("model", "model_slug"):
                value = thread.get(key)
                if isinstance(value, str):
                    return value
    return None


def parse_codex_jsonl(stdout: str, model: str) -> dict:
    events = []
    for line_number, line in enumerate(stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReviewError(f"malformed Codex JSONL at line {line_number}: {error}") from error
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ReviewError(f"malformed Codex event at line {line_number}")
        events.append(event)
    if not events:
        raise ReviewError("Codex JSONL is empty")

    event_types = [event["type"] for event in events]
    item_types = []
    final_messages = []
    tool_events = []
    for event in events:
        event_type = event["type"]
        lowered = event_type.lower()
        if any(word in lowered for word in ("command", "file", "web", "mcp", "subagent", "tool", "shell")):
            tool_events.append(event_type)
        item = event.get("item")
        if isinstance(item, dict):
            item_type = item.get("type")
            item_types.append(item_type)
            if item_type not in ALLOWED_ITEM_TYPES:
                tool_events.append(str(item_type))
            if event_type == "item.completed" and item_type == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    final_messages.append(text)
    if tool_events:
        raise ReviewError(f"Codex emitted prohibited tool event(s): {sorted(set(tool_events))}")
    if event_types.count("turn.started") > 1:
        raise ReviewError("Codex emitted more than one user turn")
    if event_types.count("turn.started") != 1:
        raise ReviewError("Codex did not emit exactly one user turn")
    completed = [event for event in events if event["type"] == "turn.completed"]
    if len(completed) != 1:
        raise ReviewError("Codex did not emit exactly one turn.completed event")
    usage = completed[0].get("usage")
    if not isinstance(usage, dict) or not usage:
        raise ReviewError("Codex turn.completed event has no usage")
    if not final_messages:
        raise ReviewError("Codex response has no final agent message")
    served_model = _served_model(events)
    if served_model is not None and served_model != model:
        raise ReviewError(f"requested {model}, CLI reported served model {served_model}")
    thread_ids = [event.get("thread_id") for event in events
                  if event["type"] == "thread.started" and event.get("thread_id")]
    return {
        "response_id": thread_ids[0] if thread_ids else None,
        "thread_id": thread_ids[0] if thread_ids else None,
        "status": "completed",
        "output_text": final_messages[-1],
        "usage": usage,
        "event_types": event_types,
        "item_types": item_types,
        "served_model": served_model,
        "served_model_verification": "exposed_and_matched" if served_model else "not_exposed_by_cli",
        "observed_tool_use": False,
    }


def _observed_types(stdout: str) -> tuple[list[str], list[str]]:
    event_types, item_types = [], []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if isinstance(event.get("type"), str):
            event_types.append(event["type"])
        item = event.get("item")
        if isinstance(item, dict) and isinstance(item.get("type"), str):
            item_types.append(item["type"])
    return event_types, item_types


def _sanitize_jsonl(stdout: str) -> tuple[str, dict]:
    sanitized = stdout
    home = os.environ.get("HOME")
    home_replacements = 0
    if home:
        home_replacements = sanitized.count(home)
        sanitized = sanitized.replace(home, "<HOME>")
    credential_patterns = (
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*"),
    )
    credential_replacements = 0
    for pattern in credential_patterns:
        sanitized, count = pattern.subn("<REDACTED_CREDENTIAL>", sanitized)
        credential_replacements += count
    return sanitized, {
        "home_paths_replaced": home_replacements,
        "credential_patterns_replaced": credential_replacements,
        "authentication_material_archived": False,
    }


def _load_resumable(path: Path, identity: dict) -> dict | None:
    if not path.is_file():
        return None
    saved = json.loads(path.read_text())
    differing = [key for key, value in identity.items() if saved.get(key) != value]
    if differing:
        raise ReviewError(f"cannot resume {path}: identity differs in {sorted(differing)}")
    if saved.get("terminal_status") != "completed":
        return None
    return saved


def _transient(stderr: str) -> bool:
    lowered = stderr.lower()
    if "model" in lowered and any(word in lowered for word in ("unavailable", "not found", "unsupported")):
        return False
    return any(pattern in lowered for pattern in TRANSIENT_PATTERNS)


def review(package: str, out_path: Path, system_prompt: str, schema: dict, validate,
           model: str = REVIEWER_MODEL, effort: str = REVIEWER_EFFORT,
           timeout_seconds: int = 900, waits: tuple[int, ...] = (60, 300), sleep_fn=time.sleep,
           codex_binary: str = "codex") -> dict:
    if (model, effort) != (REVIEWER_MODEL, REVIEWER_EFFORT):
        raise ReviewError(f"reviewer is fixed to {REVIEWER_MODEL}/{REVIEWER_EFFORT}")
    version = codex_cli_version(codex_binary)
    identity = request_identity(package, model, effort, system_prompt, schema, version)
    saved = _load_resumable(out_path, identity)
    if saved is not None:
        return saved
    prompt = render_prompt(system_prompt, package)
    attempts = []
    for attempt in range(1, len(waits) + 2):
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="rdr-v2-codex-") as temporary:
            temporary_path = Path(temporary)
            empty_cwd = temporary_path / "empty-workdir"
            empty_cwd.mkdir()
            schema_path = temporary_path / "review-schema.json"
            schema_path.write_text(json.dumps(schema, sort_keys=True, separators=(",", ":")))
            if any(empty_cwd.iterdir()):
                raise ReviewError("Codex temporary working directory was not empty")
            command = _command(codex_binary, model, effort, empty_cwd, schema_path)
            try:
                process = subprocess.run(
                    command, input=prompt, capture_output=True, text=True,
                    cwd=empty_cwd, env=_minimal_env(), timeout=timeout_seconds,
                )
                stderr = process.stderr or ""
                stdout = process.stdout or ""
                if process.returncode != 0:
                    status = "transport_error" if _transient(stderr) else "terminal_error"
                    result = {
                        "terminal_status": status, "error_type": "CodexCLIError",
                        "error": stderr[-2000:] or f"Codex CLI exited {process.returncode}",
                        "returncode": process.returncode,
                    }
                else:
                    try:
                        parsed = parse_codex_jsonl(stdout, model)
                        result = {"terminal_status": "completed", **parsed}
                    except ReviewError as error:
                        event_types, item_types = _observed_types(stdout)
                        result = {"terminal_status": "terminal_error", "error_type": "ReviewError",
                                  "error": str(error), "returncode": process.returncode,
                                  "event_types": event_types, "item_types": item_types,
                                  "observed_tool_use": "prohibited tool event" in str(error)}
            except subprocess.TimeoutExpired as error:
                stdout = error.stdout or ""
                stderr = error.stderr or ""
                result = {"terminal_status": "transport_error", "error_type": "TimeoutExpired",
                          "error": f"Codex CLI timed out after {timeout_seconds} seconds"}
            sanitized, sanitization = _sanitize_jsonl(stdout)
            normalized_command = _normalized_command(command, empty_cwd, schema_path)
        wall_seconds = time.monotonic() - started
        evidence_path = out_path.with_name(out_path.stem + f".attempt-{attempt}.codex.jsonl")
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(sanitized)
        attempt_record = {
            **identity, "attempt": attempt, **result, "wall_seconds": wall_seconds,
            "cli_command": normalized_command,
            "stdout_sha256": _sha(stdout), "stderr_sha256": _sha(stderr),
            "sanitized_jsonl_path": evidence_path.name,
            "sanitized_jsonl_sha256": _sha(sanitized), "jsonl_sanitization": sanitization,
        }
        attempts.append(attempt_record)
        attempt_path = out_path.with_name(out_path.stem + f".attempt-{attempt}.json")
        attempt_path.write_text(json.dumps(attempt_record, indent=2, sort_keys=True))
        if result.get("terminal_status") == "completed":
            try:
                answer = json.loads(result["output_text"])
            except json.JSONDecodeError as error:
                raise ReviewError(f"malformed reviewer JSON: {error}") from error
            try:
                validate(answer)
            except ValueError as error:
                raise ReviewError(f"reviewer schema mismatch: {error}") from error
            usage = result["usage"]
            record = {
                **identity, **result, "answer": answer, "attempt": attempt, "attempts": attempts,
                "wall_seconds": wall_seconds, "cli_command": normalized_command,
                "stdout_sha256": _sha(stdout), "stderr_sha256": _sha(stderr),
                "sanitized_jsonl_path": evidence_path.name,
                "sanitized_jsonl_sha256": _sha(sanitized), "jsonl_sanitization": sanitization,
                "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                "cached_tokens": usage.get("cached_input_tokens"),
                "reasoning_tokens": usage.get("reasoning_output_tokens"),
                "package_characters": len(package), "package_utf8_bytes": len(package.encode()),
                "package_lines": len(package.splitlines()),
                "package_reviewer_tokens": len(re.findall(r"\w+|[^\w\s]", package, re.UNICODE)),
                "tool_surface_available": True, "fabio_evidence_arm_compatible": True,
                "fabio_transport_replication": False,
                "previous_response_id": None, "conversation": None, "session": None,
            }
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(record, indent=2, sort_keys=True))
            return record
        if result.get("terminal_status") != "transport_error" or attempt > len(waits):
            raise ReviewError(f"reviewer request failed: {result.get('error_type')}: {result.get('error')}")
        sleep_fn(waits[attempt - 1])
    raise AssertionError("unreachable")
