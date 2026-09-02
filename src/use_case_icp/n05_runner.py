"""N05 stable identities, append-only records, and Bubblewrap launch paths."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
from typing import Any, Callable, Iterable, Mapping


N05_OUTPUT_RELATIVE = Path("outputs/fault-experiments-v2-1")
SANDBOX_BACKEND = "bubblewrap"
MODEL_COMMAND_PERMISSION_PROFILE = "n05-branch-command"
ID_KINDS = frozenset(
    {
        "protocol",
        "setup",
        "preflight",
        "scenario",
        "candidate",
        "stabilization",
        "instance",
        "chain",
        "job",
        "capture-set",
        "capture-attempt",
        "condition",
        "trial",
        "branch",
        "call",
        "repair",
        "rerun-capture",
    }
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_id(kind: str, hierarchy: Iterable[str | int], index: int) -> str:
    """Derive an identity from frozen hierarchy and index, never content alone."""
    if kind not in ID_KINDS:
        raise ValueError(f"unknown N05 identity kind: {kind}")
    if isinstance(index, bool) or int(index) < 0:
        raise ValueError("N05 identity index must be a non-negative integer")
    parents = [str(item) for item in hierarchy]
    if not parents or any(not item for item in parents):
        raise ValueError("N05 identity requires a non-empty frozen hierarchy")
    payload = {"kind": kind, "hierarchy": parents, "index": int(index)}
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()[:16]
    return f"{kind}-{index:03d}-{digest}"


def create_json_exclusive(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json(payload) + b"\n"
    return create_bytes_exclusive(path, encoded)


def create_bytes_exclusive(path: Path, encoded: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise ValueError(f"immutable N05 record conflicts: {path}") from None
    return sha256_bytes(encoded)


def append_record(
    ledger_root: Path,
    *,
    record_type: str,
    record_id: str,
    payload: Mapping[str, Any],
) -> dict[str, str]:
    if not record_type or not record_id:
        raise ValueError("N05 ledger record type and ID are required")
    relative = Path(record_type) / f"{record_id}.json"
    path = ledger_root / relative
    record = {
        "schema_version": "1",
        "record_type": record_type,
        "record_id": record_id,
        "payload": dict(payload),
        "payload_sha256": sha256_bytes(canonical_json(payload)),
    }
    digest = create_json_exclusive(path, record)
    return {"path": relative.as_posix(), "sha256": digest}


def verify_record(
    ledger_root: Path, *, record_type: str, record_id: str
) -> dict[str, Any]:
    path = ledger_root / record_type / f"{record_id}.json"
    record = json.loads(path.read_text())
    if record.get("record_type") != record_type or record.get("record_id") != record_id:
        raise ValueError("N05 ledger record identity mismatch")
    expected = sha256_bytes(canonical_json(record.get("payload")))
    if record.get("payload_sha256") != expected:
        raise ValueError("N05 ledger record payload hash mismatch")
    return record


def run_with_identical_retries(
    ledger_root: Path,
    *,
    parent_id: str,
    call_class: str,
    logical_request: Mapping[str, Any],
    launch: Callable[[str, bytes], Mapping[str, Any]],
    max_infrastructure_retries: int = 2,
) -> dict[str, Any]:
    """Keep every attempt while retrying only identical infrastructure failures."""
    request_bytes = canonical_json(logical_request)
    request_sha256 = sha256_bytes(request_bytes)
    attempts: list[dict[str, Any]] = []
    for attempt_index in range(max_infrastructure_retries + 1):
        call_id = stable_id("call", [parent_id, call_class], attempt_index)
        record_path = ledger_root / "call-attempt" / f"{call_id}.json"
        if record_path.is_file():
            stored = verify_record(
                ledger_root,
                record_type="call-attempt",
                record_id=call_id,
            )
            attempt = dict(stored["payload"])
            if (
                attempt.get("parent_id") != parent_id
                or attempt.get("call_class") != call_class
                or attempt.get("attempt_index") != attempt_index
                or attempt.get("request_sha256") != request_sha256
            ):
                raise ValueError("N05 recorded retry attempt does not match the logical request")
            attempt["record"] = {
                "path": f"call-attempt/{call_id}.json",
                "sha256": sha256_file(record_path),
            }
            result = dict(attempt["result"])
            attempts.append(attempt)
            status = str(attempt.get("status") or "")
            failure_class = str(attempt.get("failure_classification") or "")
            if status != "failed":
                return {
                    "status": "completed",
                    "request_sha256": request_sha256,
                    "attempts": attempts,
                    "result": result,
                }
            if failure_class != "infrastructure_failure":
                return {
                    "status": "scientific_failure",
                    "request_sha256": request_sha256,
                    "attempts": attempts,
                    "result": result,
                }
            continue
        result = dict(launch(call_id, request_bytes))
        if canonical_json(logical_request) != request_bytes:
            raise RuntimeError("N05 logical request mutated during retry execution")
        failure_class = str(result.get("failure_classification") or "")
        status = str(result.get("status") or "")
        attempt = {
            "call_id": call_id,
            "parent_id": parent_id,
            "call_class": call_class,
            "attempt_index": attempt_index,
            "request_sha256": request_sha256,
            "status": status,
            "failure_classification": failure_class or None,
            "result": result,
        }
        attempt["record"] = append_record(
            ledger_root,
            record_type="call-attempt",
            record_id=call_id,
            payload=attempt,
        )
        attempts.append(attempt)
        if status != "failed":
            return {
                "status": "completed",
                "request_sha256": request_sha256,
                "attempts": attempts,
                "result": result,
            }
        if failure_class != "infrastructure_failure":
            return {
                "status": "scientific_failure",
                "request_sha256": request_sha256,
                "attempts": attempts,
                "result": result,
            }
    return {
        "status": "infrastructure_failure",
        "request_sha256": request_sha256,
        "attempts": attempts,
        "result": attempts[-1]["result"],
    }


def validate_n05_output_root(repo_root: Path, output_root: Path) -> Path:
    expected = (repo_root / N05_OUTPUT_RELATIVE).resolve()
    if output_root.resolve() != expected:
        raise ValueError("N05 output must use outputs/fault-experiments-v2-1")
    return expected


def _relative_allowlist_path(value: str) -> Path:
    pure = PurePosixPath(str(value).replace("\\", "/"))
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise ValueError("branch allowlist path must be normalized and relative")
    return Path(*pure.parts)


def _copy_regular_file(source: Path, destination: Path) -> dict[str, Any]:
    resolved = source.resolve(strict=True)
    if source.is_symlink() or not resolved.is_file():
        raise ValueError("branch allowlist accepts regular files only")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())
    source_stat = resolved.stat()
    destination_stat = destination.stat()
    if (source_stat.st_dev, source_stat.st_ino) == (
        destination_stat.st_dev,
        destination_stat.st_ino,
    ):
        raise ValueError("branch evidence must not be a hard link")
    if sha256_file(resolved) != sha256_file(destination):
        raise ValueError("branch evidence copy hash mismatch")
    destination.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return {
        "path": destination.name,
        "sha256": sha256_file(destination),
        "size": destination_stat.st_size,
        "source_inode": [source_stat.st_dev, source_stat.st_ino],
        "branch_inode": [destination_stat.st_dev, destination_stat.st_ino],
    }


def materialize_opaque_branch(
    branch_root: Path,
    *,
    allowlist: Mapping[str, Path],
    manifest_identity: Mapping[str, str],
) -> dict[str, Any]:
    """Copy one immutable allowlist into a new branch with private writable roots."""
    if branch_root.exists():
        raise FileExistsError(f"N05 branch already exists: {branch_root}")
    branch_root.mkdir(parents=True)
    evidence_root = branch_root / "evidence"
    evidence_root.mkdir()
    copied: list[dict[str, Any]] = []
    for relative_name, source in sorted(allowlist.items()):
        relative = _relative_allowlist_path(relative_name)
        destination = evidence_root / relative
        item = _copy_regular_file(Path(source), destination)
        item["path"] = relative.as_posix()
        copied.append(item)
    for name in ("workspace", "home", "temp", "output", "jobstore", "dependencies"):
        (branch_root / name).mkdir()
    manifest = {
        "schema_version": "1",
        "identity": dict(manifest_identity),
        "evidence": copied,
        "visible_roots": {
            "evidence": "/evidence",
            "workspace": "/workspace",
            "home": "/home/codex",
            "temp": "/tmp",
            "output": "/output",
            "jobstore": "/jobstore",
            "dependencies": "/runtime",
        },
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(manifest))
    create_json_exclusive(branch_root / "branch-manifest.json", manifest)
    return manifest


def verify_opaque_branch(branch_root: Path) -> dict[str, Any]:
    manifest_path = branch_root / "branch-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    observed = dict(manifest)
    recorded = observed.pop("manifest_sha256", None)
    if recorded != sha256_bytes(canonical_json(observed)):
        raise ValueError("N05 branch manifest hash mismatch")
    expected_paths = {item["path"] for item in manifest["evidence"]}
    actual_paths = {
        path.relative_to(branch_root / "evidence").as_posix()
        for path in (branch_root / "evidence").rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        raise ValueError("N05 branch evidence contains an unexpected or missing file")
    for item in manifest["evidence"]:
        path = branch_root / "evidence" / item["path"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("N05 branch evidence is not a regular copied file")
        if sha256_file(path) != item["sha256"]:
            raise ValueError("N05 branch evidence was modified")
        current = path.stat()
        if [current.st_dev, current.st_ino] == item["source_inode"]:
            raise ValueError("N05 branch evidence became a hard link")
    return manifest


def bubblewrap_version(bwrap_bin: str = "bwrap") -> str:
    executable = shutil.which(bwrap_bin)
    if executable is None:
        raise RuntimeError("Bubblewrap is required; unrestricted fallback is forbidden")
    completed = subprocess.run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        check=False,
        close_fds=True,
    )
    if completed.returncode != 0 or not completed.stdout.strip().startswith("bubblewrap "):
        raise RuntimeError("Bubblewrap availability check failed")
    return completed.stdout.strip()


def _runtime_binds() -> list[str]:
    binds: list[str] = []
    for path in ("/usr", "/lib", "/lib64"):
        if Path(path).exists():
            binds.extend(["--ro-bind", path, path])
    if Path("/bin").is_symlink():
        binds.extend(["--symlink", os.readlink("/bin"), "/bin"])
    elif Path("/bin").exists():
        binds.extend(["--ro-bind", "/bin", "/bin"])
    return binds


def python_bubblewrap_command(
    branch_root: Path,
    command: Iterable[str],
    *,
    role: str,
    venv_root: Path | None = None,
    bwrap_bin: str = "bwrap",
) -> list[str]:
    if role not in {"authored_python", "repaired_python"}:
        raise ValueError("N05 Python sandbox role is invalid")
    bubblewrap_version(bwrap_bin)
    verify_opaque_branch(branch_root)
    executable = shutil.which(bwrap_bin)
    assert executable is not None
    venv = venv_root.resolve(strict=True) if venv_root is not None else None
    venv_bind = ["--ro-bind", str(venv), "/venv"] if venv is not None else []
    return [
        executable,
        "--unshare-all",
        "--unshare-net",
        "--die-with-parent",
        "--new-session",
        *_runtime_binds(),
        *venv_bind,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--ro-bind",
        str((branch_root / "evidence").resolve()),
        "/evidence",
        "--bind",
        str((branch_root / "workspace").resolve()),
        "/workspace",
        "--bind",
        str((branch_root / "temp").resolve()),
        "/tmp",
        "--bind",
        str((branch_root / "output").resolve()),
        "/output",
        "--dir",
        "/home",
        "--dir",
        "/home/runner",
        "--setenv",
        "HOME",
        "/home/runner",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "PATH",
        "/venv/bin:/usr/bin:/bin" if venv is not None else "/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--chdir",
        "/workspace",
        "--",
        *[str(value) for value in command],
    ]


def run_python_in_branch(
    branch_root: Path,
    command: Iterable[str],
    *,
    role: str,
    venv_root: Path | None = None,
    input_text: str | None = None,
    timeout_seconds: int = 300,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        python_bubblewrap_command(
            branch_root, command, role=role, venv_root=venv_root
        ),
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        close_fds=True,
    )


def copy_etiq_worker_runtime(branch_root: Path, source_root: Path) -> list[dict[str, Any]]:
    """Copy only the controller-free worker modules needed for real Etiq capture."""
    destination = branch_root / "dependencies" / "use_case_icp"
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for name in ("__init__.py", "etiq_worker.py", "etiq_graph.py", "job_store.py", "records.py"):
        item = _copy_regular_file(source_root / "use_case_icp" / name, destination / name)
        item["path"] = f"use_case_icp/{name}"
        copied.append(item)
    return copied


def etiq_worker_bubblewrap_command(
    branch_root: Path,
    *,
    venv_root: Path,
    request_relative_path: str,
    bwrap_bin: str = "bwrap",
) -> list[str]:
    """Launch the real Etiq worker with the authored program in a network namespace."""
    bubblewrap_version(bwrap_bin)
    verify_opaque_branch(branch_root)
    request = _relative_allowlist_path(request_relative_path)
    host_request = branch_root / "jobstore" / request
    if not host_request.is_file():
        raise ValueError("Etiq worker request is absent from the branch-local JobStore")
    venv = venv_root.resolve(strict=True)
    if not (venv / "bin/python").exists():
        raise ValueError("pinned Python environment is unavailable")
    runtime = branch_root / "dependencies"
    if not (runtime / "use_case_icp/etiq_worker.py").is_file():
        raise ValueError("branch-local Etiq worker runtime is unavailable")
    executable = shutil.which(bwrap_bin)
    assert executable is not None
    return [
        executable,
        "--unshare-all",
        "--unshare-net",
        "--die-with-parent",
        "--new-session",
        *_runtime_binds(),
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--ro-bind",
        str(venv),
        "/venv",
        "--ro-bind",
        str(runtime.resolve()),
        "/runtime",
        "--bind",
        str((branch_root / "jobstore").resolve()),
        "/jobstore",
        "--bind",
        str((branch_root / "temp").resolve()),
        "/tmp",
        "--dir",
        "/home",
        "--dir",
        "/home/runner",
        "--setenv",
        "HOME",
        "/home/runner",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "PATH",
        "/venv/bin:/usr/bin:/bin",
        "--setenv",
        "PYTHONPATH",
        "/runtime",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--chdir",
        "/jobstore",
        "--",
        "/venv/bin/python",
        "-m",
        "use_case_icp.etiq_worker",
        f"/jobstore/{request.as_posix()}",
    ]


def copy_codex_auth(
    branch_root: Path, *, source_codex_home: Path, names: Iterable[str] = ("auth.json",)
) -> list[dict[str, str]]:
    destination_root = branch_root / "home" / ".codex"
    destination_root.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    for name in names:
        if Path(name).name != name:
            raise ValueError("Codex authentication allowlist accepts file names only")
        source = (source_codex_home / name).resolve(strict=True)
        destination = destination_root / name
        item = _copy_regular_file(source, destination)
        copied.append({"name": name, "sha256": item["sha256"]})
    return copied


def _codex_permission_overrides() -> list[str]:
    filesystem = (
        '{":root"="deny",":minimal"="read",'
        '":workspace_roots"="write","/evidence"="read",'
        '"/output"="write","/tmp"="write","/opt/codex"="read"}'
    )
    return [
        'approval_policy="never"',
        f'default_permissions="{MODEL_COMMAND_PERMISSION_PROFILE}"',
        f"permissions.{MODEL_COMMAND_PERMISSION_PROFILE}.filesystem={filesystem}",
        f"permissions.{MODEL_COMMAND_PERMISSION_PROFILE}.network.enabled=false",
        'shell_environment_policy.inherit="none"',
        'shell_environment_policy.set={PATH="/usr/bin:/bin",HOME="/home/codex",LANG="C.UTF-8",TMPDIR="/tmp"}',
        "project_doc_max_bytes=0",
        'project_root_markers=["context-manifest.json"]',
        "memories.use_memories=false",
    ]


def codex_permission_profile_probe_command(
    branch_root: Path,
    *,
    codex_runtime_root: Path,
    bwrap_bin: str = "bwrap",
) -> list[str]:
    """Parse the exact permission profile locally without starting inference."""
    command = ["/usr/bin/node", "/opt/codex/bin/codex.js"]
    for override in _codex_permission_overrides():
        command.extend(["--config", override])
    command.extend(["debug", "models"])
    return codex_control_plane_bubblewrap_command(
        branch_root,
        codex_runtime_root=codex_runtime_root,
        child_command=command,
        bwrap_bin=bwrap_bin,
    )


def codex_bubblewrap_command(
    branch_root: Path,
    *,
    codex_runtime_root: Path,
    prompt_file: str,
    schema_file: str,
    output_file: str,
    model: str = "gpt-5.5",
    reasoning_effort: str = "high",
    bwrap_bin: str = "bwrap",
) -> list[str]:
    """Build the provider-capable control plane with command network denied by policy."""
    command = [
        "/usr/bin/node",
        "/opt/codex/bin/codex.js",
        "exec",
        "--ephemeral",
        "--json",
        "--color",
        "never",
        "--ignore-user-config",
        "--ignore-rules",
        "--cd",
        "/workspace",
        "--skip-git-repo-check",
        "--output-schema",
        f"/evidence/{schema_file}",
        "--output-last-message",
        f"/output/{output_file}",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
    ]
    for override in _codex_permission_overrides():
        command.extend(["--config", override])
    command.append("-")
    return codex_control_plane_bubblewrap_command(
        branch_root,
        codex_runtime_root=codex_runtime_root,
        child_command=command,
        bwrap_bin=bwrap_bin,
    )


def codex_control_plane_bubblewrap_command(
    branch_root: Path,
    *,
    codex_runtime_root: Path,
    child_command: Iterable[str],
    bwrap_bin: str = "bwrap",
) -> list[str]:
    """Apply the exact provider-capable filesystem/process boundary to a child."""
    bubblewrap_version(bwrap_bin)
    verify_opaque_branch(branch_root)
    runtime = codex_runtime_root.resolve(strict=True)
    if not (runtime / "bin/codex.js").is_file():
        raise ValueError("Codex runtime root does not contain bin/codex.js")
    auth_root = branch_root / "home" / ".codex"
    if not (auth_root / "auth.json").is_file():
        raise ValueError("private Codex home lacks copied authentication")
    executable = shutil.which(bwrap_bin)
    assert executable is not None
    network_files: list[str] = []
    for path in (
        "/etc/ssl/certs",
        "/etc/resolv.conf",
        "/etc/hosts",
        "/etc/nsswitch.conf",
    ):
        if Path(path).exists():
            network_files.extend(["--ro-bind", path, path])
    return [
        executable,
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--die-with-parent",
        "--new-session",
        *_runtime_binds(),
        *network_files,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--ro-bind",
        str(runtime),
        "/opt/codex",
        "--ro-bind",
        str((branch_root / "evidence").resolve()),
        "/evidence",
        "--bind",
        str((branch_root / "workspace").resolve()),
        "/workspace",
        "--bind",
        str((branch_root / "home").resolve()),
        "/home/codex",
        "--bind",
        str((branch_root / "temp").resolve()),
        "/tmp",
        "--bind",
        str((branch_root / "output").resolve()),
        "/output",
        "--bind",
        str((branch_root / "jobstore").resolve()),
        "/jobstore",
        "--setenv",
        "CODEX_HOME",
        "/home/codex/.codex",
        "--setenv",
        "HOME",
        "/home/codex",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--chdir",
        "/workspace",
        "--",
        *[str(value) for value in child_command],
    ]


def launch_codex_in_branch(
    branch_root: Path,
    *,
    codex_runtime_root: Path,
    prompt_file: str,
    schema_file: str,
    output_file: str,
    model: str = "gpt-5.5",
    reasoning_effort: str = "high",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Run one fresh provider call; model-executed commands retain network denial."""
    prompt_path = branch_root / "evidence" / _relative_allowlist_path(prompt_file)
    schema_path = branch_root / "evidence" / _relative_allowlist_path(schema_file)
    if not prompt_path.is_file() or not schema_path.is_file():
        raise ValueError("N05 Codex prompt or schema is absent from branch evidence")
    command = codex_bubblewrap_command(
        branch_root,
        codex_runtime_root=codex_runtime_root,
        prompt_file=prompt_file,
        schema_file=schema_file,
        output_file=output_file,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    try:
        completed = subprocess.run(
            command,
            input=prompt_path.read_text(),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            close_fds=True,
        )
    except subprocess.TimeoutExpired as error:
        def bounded_text(value: str | bytes | None) -> str:
            if isinstance(value, bytes):
                value = value.decode(errors="replace")
            return (value or "")[-1_000_000:]

        stdout = bounded_text(error.stdout)
        stderr = bounded_text(error.stderr)
        timeout_message = f"Codex provider call timed out after {timeout_seconds} seconds"
        create_bytes_exclusive(
            branch_root / "output" / "codex-events.jsonl", stdout.encode()
        )
        create_bytes_exclusive(
            branch_root / "output" / "codex-stderr.log",
            (stderr + ("\n" if stderr else "") + timeout_message + "\n").encode(),
        )
        return {
            "status": "failed",
            "failure_classification": "infrastructure_failure",
            "returncode": None,
            "error": timeout_message,
            "timeout_seconds": timeout_seconds,
            "partial_stdout_bytes": len(stdout.encode()),
            "partial_stderr_bytes": len(stderr.encode()),
            "usage": {},
        }
    create_bytes_exclusive(
        branch_root / "output" / "codex-events.jsonl", completed.stdout.encode()
    )
    create_bytes_exclusive(
        branch_root / "output" / "codex-stderr.log", completed.stderr.encode()
    )
    response_path = branch_root / "output" / _relative_allowlist_path(output_file)
    events = []
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    usage: dict[str, int] = {}
    for event in events:
        candidate = event.get("usage")
        if isinstance(candidate, Mapping):
            for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                if isinstance(candidate.get(key), int):
                    usage[key] = int(candidate[key])
    if completed.returncode != 0:
        return {
            "status": "failed",
            "failure_classification": "infrastructure_failure",
            "returncode": completed.returncode,
            "error": completed.stderr.strip() or "Codex provider call failed",
            "usage": usage,
        }
    if not response_path.is_file():
        return {
            "status": "failed",
            "failure_classification": "infrastructure_failure",
            "returncode": completed.returncode,
            "error": "Codex did not create the schema-constrained response",
            "usage": usage,
        }
    try:
        response = json.loads(response_path.read_text())
    except json.JSONDecodeError as error:
        return {
            "status": "failed",
            "failure_classification": "infrastructure_failure",
            "returncode": completed.returncode,
            "error": f"Codex response is malformed JSON: {error}",
            "usage": usage,
        }
    return {
        "status": "completed",
        "returncode": completed.returncode,
        "response": response,
        "response_sha256": sha256_file(response_path),
        "usage": usage,
    }


def validate_signed_tester_gate(
    design_freeze_path: Path,
    tester_gate_path: Path,
) -> dict[str, Any]:
    """Fail closed unless Gate 1 binds this exact design and production launcher."""
    freeze = json.loads(design_freeze_path.read_text())
    gate = json.loads(tester_gate_path.read_text())
    required = {
        "status": "passed",
        "design_freeze_sha256": sha256_file(design_freeze_path),
        "freeze_content_sha256": freeze.get("freeze_sha256"),
        "production_launcher_sha256": launch_policy_identity()[
            "production_launcher_sha256"
        ],
        "sandbox_backend": SANDBOX_BACKEND,
    }
    if any(gate.get(key) != value for key, value in required.items()):
        raise ValueError("N05 Tester gate does not bind the exact frozen production design")
    probes = gate.get("probe_results")
    if not isinstance(probes, list) or not probes or any(
        item.get("status") != "passed" or item.get("skipped") is True
        for item in probes
    ):
        raise ValueError("N05 Tester gate contains failed, missing, or skipped probes")
    signature = str(gate.get("tester_signature") or "")
    unsigned = dict(gate)
    unsigned.pop("tester_signature", None)
    if signature != sha256_bytes(canonical_json(unsigned)):
        raise ValueError("N05 Tester gate signature is invalid")
    return gate


def launch_policy_identity() -> dict[str, Any]:
    source = Path(__file__).resolve()
    return {
        "sandbox_backend": SANDBOX_BACKEND,
        "sandbox_backend_version": bubblewrap_version(),
        "production_launcher_sha256": sha256_file(source),
        "model_command_permission_profile": MODEL_COMMAND_PERMISSION_PROFILE,
        "codex_control_plane_network_unshared": False,
        "model_commands_network_enabled": False,
        "authored_python_network_unshared": True,
        "repaired_python_network_unshared": True,
        "unrestricted_fallback_allowed": False,
    }
