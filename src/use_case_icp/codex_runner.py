from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .records import (
    CodexContextManifest,
    CodexUsageRecord,
    ContextArtifact,
    jsonable,
    new_id,
    stable_hash,
)
from .job_store import JobStore


DEFAULT_CODEX_MODEL = "gpt-5.5"
STRICT_PERMISSION_PROFILE = "etiq-invocation-only"
PROVIDER_ERROR_EVENT_LIMIT = 8
PROVIDER_ERROR_TEXT_LIMIT = 2048
STDERR_DIAGNOSTIC_LIMIT = 4096


class CodexInvocationError(RuntimeError):
    def __init__(
        self,
        message: str,
        invocation_id: str,
        *,
        provider_error: str = "",
        terminal_status: str | None = None,
        usage: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.invocation_id = invocation_id
        self.provider_error = provider_error
        self.terminal_status = terminal_status
        self.usage = dict(usage or {})


@dataclass(slots=True)
class CodexResult:
    invocation_id: str
    payload: dict[str, Any]
    usage: CodexUsageRecord
    events: list[dict[str, Any]]


def _codex_runtime_root(codex_bin: str) -> Path:
    executable = shutil.which(codex_bin) or codex_bin
    resolved = Path(executable).resolve()
    if resolved.name == "codex.js" and resolved.parent.name == "bin":
        return resolved.parent.parent
    return resolved.parent


def _strict_config_overrides(codex_bin: str) -> list[str]:
    runtime_root = json.dumps(str(_codex_runtime_root(codex_bin)))
    filesystem = (
        '{":root"="deny",'
        '":minimal"="read",'
        '":workspace_roots"={"."="read"},'
        f"{runtime_root}=\"read\""
        "}"
    )
    return [
        'approval_policy="never"',
        f'default_permissions="{STRICT_PERMISSION_PROFILE}"',
        f"permissions.{STRICT_PERMISSION_PROFILE}.filesystem={filesystem}",
        f"permissions.{STRICT_PERMISSION_PROFILE}.network.enabled=false",
        'shell_environment_policy.inherit="none"',
        'shell_environment_policy.set={PATH="/usr/local/bin:/usr/bin:/bin",HOME="/nonexistent",LANG="C.UTF-8"}',
        "project_doc_max_bytes=0",
        'project_root_markers=["context-manifest.json"]',
        "memories.use_memories=false",
    ]


def _write_readable_resources(invocation_dir: Path, artifacts: list[ContextArtifact]) -> list[str]:
    written: list[str] = ["agent-request.json", "context-manifest.json", "output-schema.json"]
    for artifact in artifacts:
        if artifact.ref.startswith("prompt:") and isinstance(artifact.content, str):
            prompt_name = artifact.ref.removeprefix("prompt:")
            if prompt_name.replace("_", "").isalnum():
                path = invocation_dir / "resources" / "prompts" / f"{prompt_name}.md"
            else:
                continue
        elif artifact.ref == "repo:AGENTS.md" and isinstance(artifact.content, str):
            path = invocation_dir / "resources" / "AGENTS.md"
        else:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")
        written.append(str(path.relative_to(invocation_dir)))
    return written


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _bounded_diagnostic_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    suffix = "...[truncated]"
    return normalized[: limit - len(suffix)] + suffix


def _json_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return None
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, Mapping) else None


def _provider_metadata(value: Any, *, depth: int = 0) -> dict[str, Any]:
    if depth >= 4 or (mapping := _json_mapping(value)) is None:
        return {}
    metadata: dict[str, Any] = {}
    code = _bounded_diagnostic_text(mapping.get("code"), PROVIDER_ERROR_TEXT_LIMIT)
    if code:
        metadata["code"] = code
    status = mapping.get("status")
    if isinstance(status, (int, str)) and not isinstance(status, bool):
        normalized_status = _bounded_diagnostic_text(str(status), 32)
        if normalized_status:
            metadata["status"] = normalized_status

    for key in ("error", "message"):
        nested = _provider_metadata(mapping.get(key), depth=depth + 1)
        for field, item in nested.items():
            metadata.setdefault(field, item)

    message = mapping.get("message")
    if _json_mapping(message) is None:
        normalized_message = _bounded_diagnostic_text(
            message, PROVIDER_ERROR_TEXT_LIMIT
        )
        if normalized_message:
            metadata.setdefault("message", normalized_message)
    return metadata


def extract_provider_error(
    events: list[dict[str, Any]], stderr: str
) -> str:
    """Return bounded provider failure metadata plus stderr diagnostics."""
    provider_events: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("type")
        if event_type not in {"error", "turn.failed"}:
            continue
        metadata = _provider_metadata(event)
        if "status" not in metadata:
            status = event.get("status")
            if isinstance(status, (int, str)) and not isinstance(status, bool):
                normalized_status = _bounded_diagnostic_text(str(status), 32)
                if normalized_status:
                    metadata["status"] = normalized_status
        if event_type == "turn.failed" and "message" in metadata:
            metadata["terminal_error_message"] = metadata["message"]
        if metadata:
            provider_events.append({"event_type": event_type, **metadata})
        if len(provider_events) == PROVIDER_ERROR_EVENT_LIMIT:
            break

    summary: dict[str, Any] = {"provider_events": provider_events}
    stderr_diagnostics = _bounded_diagnostic_text(stderr, STDERR_DIAGNOSTIC_LIMIT)
    if stderr_diagnostics:
        summary["stderr_diagnostics"] = stderr_diagnostics
    if not provider_events and not stderr_diagnostics:
        return ""
    return json.dumps(summary, sort_keys=True, separators=(",", ":"))


def _usage_candidates(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        lowered = {str(key).lower(): item for key, item in value.items()}
        if any(key in lowered for key in ("input_tokens", "inputtokens", "output_tokens", "outputtokens")):
            yield value
        for item in value.values():
            yield from _usage_candidates(item)
    elif isinstance(value, list):
        for item in value:
            yield from _usage_candidates(item)


def extract_usage(events: list[dict[str, Any]], invocation_id: str, purpose: str, terminal_status: str) -> CodexUsageRecord:
    aliases = {
        "input_tokens": ("input_tokens", "inputtokens"),
        "output_tokens": ("output_tokens", "outputtokens"),
        "total_tokens": ("total_tokens", "totaltokens"),
    }
    for event_index in range(len(events) - 1, -1, -1):
        for candidate in _usage_candidates(events[event_index]):
            lowered = {str(key).lower(): item for key, item in candidate.items()}
            found: dict[str, int | None] = {}
            for output_key, keys in aliases.items():
                found[output_key] = next((_int_value(lowered[key]) for key in keys if key in lowered), None)
            if found["input_tokens"] is None or found["output_tokens"] is None:
                continue
            if found["total_tokens"] is None:
                found["total_tokens"] = found["input_tokens"] + found["output_tokens"]
            known = {alias for names in aliases.values() for alias in names}
            extra = {
                str(key): amount
                for key, value in candidate.items()
                if str(key).lower() not in known and (amount := _int_value(value)) is not None
            }
            return CodexUsageRecord(
                invocation_id=invocation_id,
                purpose=purpose,
                terminal_status=terminal_status,
                usage_status="reported",
                input_tokens=found["input_tokens"],
                output_tokens=found["output_tokens"],
                total_tokens=found["total_tokens"],
                extra=extra,
                source_event_index=event_index,
            )
    return CodexUsageRecord(
        invocation_id=invocation_id,
        purpose=purpose,
        terminal_status=terminal_status,
        usage_status="unavailable",
    )


class CodexRunner:
    def __init__(
        self,
        store: JobStore,
        *,
        codex_bin: str = "codex",
        model: str | None = DEFAULT_CODEX_MODEL,
        reasoning_effort: str | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        self.store = store
        self.codex_bin = codex_bin
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        *,
        job_id: str,
        job_type: str,
        purpose: str,
        prompt: str,
        output_schema: Mapping[str, Any],
        artifacts: list[ContextArtifact],
        excluded: list[dict[str, str]] | None = None,
        caused_by_invocation_id: str | None = None,
        context_budget: int | None = None,
    ) -> CodexResult:
        invocation_id = new_id("inv")
        invocation_dir = self.store.invocation_dir(job_id, invocation_id)
        schema_path = invocation_dir / "output-schema.json"
        last_message_path = invocation_dir / "last-message.json"
        prompt_hash = stable_hash(prompt)
        schema_hash = stable_hash(output_schema)
        manifest = CodexContextManifest(
            invocation_id=invocation_id,
            job_type=job_type,
            purpose=purpose,
            artifacts=artifacts,
            excluded=list(excluded or []),
            prompt_hash=prompt_hash,
            schema_hash=schema_hash,
            context_budget=context_budget,
            caused_by_invocation_id=caused_by_invocation_id,
        )
        manifest.validate()
        self.store.write_json(invocation_dir / "context-manifest.json", manifest)
        self.store.write_json(
            invocation_dir / "agent-request.json",
            {"prompt": prompt, "output_schema": output_schema, "context_manifest": jsonable(manifest)},
        )
        self.store.write_json(schema_path, output_schema)
        readable_resources = _write_readable_resources(invocation_dir, artifacts)

        command = [
            self.codex_bin,
            "exec",
            "--ephemeral",
            "--json",
            "--color",
            "never",
            "--ignore-user-config",
            "--ignore-rules",
            "--cd",
            str(invocation_dir),
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(last_message_path),
            "-",
        ]
        for override in _strict_config_overrides(self.codex_bin):
            command[2:2] = ["--config", override]
        if self.reasoning_effort:
            command[2:2] = [
                "--config",
                f'model_reasoning_effort="{self.reasoning_effort}"',
            ]
        if self.model:
            command[2:2] = ["--model", self.model]
        self.store.write_json(
            invocation_dir / "invocation.json",
            {
                "invocation_id": invocation_id,
                "fresh_session": True,
                "ephemeral": True,
                "model": self.model,
                "reasoning_effort": self.reasoning_effort,
                "profile": STRICT_PERMISSION_PROFILE,
                "working_directory": str(invocation_dir),
                "read_boundary": {
                    "mode": "invocation-only",
                    "workspace": str(invocation_dir),
                    "runtime_exception": str(_codex_runtime_root(self.codex_bin)),
                    "network": "disabled",
                    "shell_environment": "minimal",
                    "automatic_external_instructions": "disabled",
                    "readable_resources": readable_resources,
                    "skills": [],
                },
                "command": command,
            },
        )

        terminal_status = "failed"
        stdout = ""
        stderr = ""
        return_code: int | None = None
        source_codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve()
        with tempfile.TemporaryDirectory(prefix="etiq-codex-home-") as temporary_codex_home:
            isolated_codex_home = Path(temporary_codex_home)
            source_auth = source_codex_home / "auth.json"
            if source_auth.is_file():
                (isolated_codex_home / "auth.json").symlink_to(source_auth)
            environment = os.environ.copy()
            environment["CODEX_HOME"] = str(isolated_codex_home)
            try:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    env=environment,
                )
                stdout = completed.stdout
                stderr = completed.stderr
                return_code = completed.returncode
                terminal_status = "succeeded" if return_code == 0 else "failed"
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                terminal_status = "timed_out"

        (invocation_dir / "codex-events.jsonl").write_text(stdout, encoding="utf-8")
        (invocation_dir / "stderr.log").write_text(stderr, encoding="utf-8")
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        usage = extract_usage(events, invocation_id, purpose, terminal_status)
        self.store.write_json(invocation_dir / "usage.json", usage)
        self.store.update_usage_summary(job_id)

        payload: dict[str, Any] = {}
        if last_message_path.exists():
            try:
                loaded = json.loads(last_message_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except json.JSONDecodeError:
                pass
        self.store.write_json(
            invocation_dir / "agent-output.json",
            {"terminal_status": terminal_status, "return_code": return_code, "payload": payload},
        )
        if terminal_status != "succeeded":
            raise CodexInvocationError(
                f"Codex invocation {terminal_status}; see {invocation_dir.relative_to(self.store.output_root)}",
                invocation_id,
                provider_error=extract_provider_error(events, stderr),
                terminal_status=terminal_status,
                usage=jsonable(usage),
            )
        if not payload:
            raise CodexInvocationError(
                "Codex returned no valid structured payload",
                invocation_id,
                terminal_status=terminal_status,
                usage=jsonable(usage),
            )
        return CodexResult(invocation_id=invocation_id, payload=payload, usage=usage, events=events)
