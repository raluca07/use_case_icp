"""One fresh-workspace Codex authoring run with pinned model and captured settings."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rdr.appworld_adapter import REPO


MODEL = "gpt-5.6-sol"
EFFORT = "medium"
CLI = "codex"
TASK = REPO / "fixtures" / "v2" / "authoring_task.md"
DOCS = REPO / "fixtures" / "v2" / "api_inventory.md"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _author_command(workspace: Path) -> list[str]:
    return [
        CLI, "-a", "never", "exec", "--json", "--sandbox", "workspace-write", "--ignore-user-config",
        "-m", MODEL, "-c", f'model_reasoning_effort="{EFFORT}"', "-C", str(workspace),
        "--skip-git-repo-check", "Read TASK.md and api_inventory.md, then implement the task exactly.",
    ]


def _revision_command(thread_id: str, prompt: str) -> list[str]:
    return [
        CLI, "exec", "resume", "--json", "--skip-git-repo-check", "--ignore-user-config",
        "-m", MODEL, "-c", f'model_reasoning_effort="{EFFORT}"',
        "-c", 'approval_policy="never"', "-c", 'sandbox_mode="workspace-write"',
        thread_id, prompt,
    ]


def _snapshot(workspace: Path, solution: Path, turn: int) -> dict | None:
    if not solution.is_file():
        return None
    directory = workspace / "source_revisions"
    directory.mkdir(exist_ok=True)
    path = directory / f"turn_{turn}.py"
    shutil.copy2(solution, path)
    return {"path": str(path.relative_to(workspace)), "sha256": _sha(path)}


def prepare_workspace(workspace: Path) -> None:
    if workspace.exists():
        raise FileExistsError(f"authoring workspace already exists: {workspace}")
    workspace.mkdir(parents=True)
    shutil.copy2(TASK, workspace / "TASK.md")
    shutil.copy2(DOCS, workspace / "api_inventory.md")


def _settings_for_thread(thread_id: str) -> dict:
    codex_home = Path.home() / ".codex" / "sessions"
    matches = list(codex_home.rglob(f"*{thread_id}.jsonl"))
    if len(matches) != 1:
        return {"thread_id": thread_id, "rollout": None, "served_model": None, "served_effort": None}
    settings = None
    for line in matches[0].read_text().splitlines():
        event = json.loads(line)
        if event.get("type") == "turn_context":
            payload = event["payload"]
            settings = {
                "thread_id": thread_id,
                "rollout": str(matches[0]),
                "served_model": payload.get("model"),
                "served_effort": payload.get("effort"),
            }
            break
    return settings or {"thread_id": thread_id, "rollout": str(matches[0]), "served_model": None, "served_effort": None}


def author(workspace: Path, timeout: int = 900, archive: Path | None = None) -> dict:
    prepare_workspace(workspace)
    command = _author_command(workspace)
    started = time.monotonic()
    process = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    elapsed = time.monotonic() - started
    (workspace / "codex_stdout.jsonl").write_text(process.stdout)
    (workspace / "codex_stderr.txt").write_text(process.stderr)
    thread_ids = []
    usage = None
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_ids.append(event["thread_id"])
        if event.get("type") == "turn.completed":
            usage = event.get("usage")
    solution = workspace / "solution.py"
    settings = _settings_for_thread(thread_ids[-1]) if thread_ids else {}
    snapshot = _snapshot(workspace, solution, 0)
    result = {
        "requested_model": MODEL,
        "requested_effort": EFFORT,
        **settings,
        "cli_version": subprocess.run([CLI, "--version"], text=True, capture_output=True).stdout.strip(),
        "returncode": process.returncode,
        "command": command,
        "stdout_sha256": _sha(workspace / "codex_stdout.jsonl"),
        "stderr_sha256": _sha(workspace / "codex_stderr.txt"),
        "elapsed_seconds": round(elapsed, 3),
        "usage": usage,
        "task_sha256": _sha(TASK),
        "api_inventory_sha256": _sha(DOCS),
        "solution_exists": solution.is_file(),
        "solution_sha256": _sha(solution) if solution.is_file() else None,
        "source_snapshot": snapshot,
        "passed": process.returncode == 0 and solution.is_file()
                  and settings.get("served_model") == MODEL and settings.get("served_effort") == EFFORT,
    }
    (workspace / "authoring.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    if archive is not None:
        if archive.exists():
            raise FileExistsError(f"authoring archive already exists: {archive}")
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(workspace, archive)
    return result


def revise(workspace: Path, prompt_path: Path, timeout: int = 900, archive: Path | None = None) -> dict:
    """Continue the pinned authoring session after deterministic evaluator feedback."""
    result_path = workspace / "authoring.json"
    result = json.loads(result_path.read_text())
    result.setdefault("initial_solution_sha256", result.get("solution_sha256"))
    thread_id = result["thread_id"]
    revisions = result.setdefault("revisions", [])
    number = len(revisions) + 1
    prompt = prompt_path.read_text()
    command = _revision_command(thread_id, prompt)
    started = time.monotonic()
    process = subprocess.run(command, text=True, capture_output=True, timeout=timeout, cwd=workspace)
    elapsed = time.monotonic() - started
    stdout_path = workspace / f"revision_{number}_stdout.jsonl"
    stderr_path = workspace / f"revision_{number}_stderr.txt"
    stdout_path.write_text(process.stdout)
    stderr_path.write_text(process.stderr)
    usage = None
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            usage = event.get("usage")
    settings = _settings_for_thread(thread_id)
    solution = workspace / "solution.py"
    revision = {
        "number": number,
        "prompt_sha256": _sha(prompt_path),
        "returncode": process.returncode,
        "command": command,
        "stdout_sha256": _sha(stdout_path),
        "stderr_sha256": _sha(stderr_path),
        "elapsed_seconds": round(elapsed, 3),
        "usage": usage,
        "solution_sha256": _sha(solution) if solution.is_file() else None,
        "source_snapshot": _snapshot(workspace, solution, number),
    }
    revisions.append(revision)
    result.update(settings)
    result.update(
        solution_exists=solution.is_file(),
        solution_sha256=revision["solution_sha256"],
        passed=process.returncode == 0 and solution.is_file()
        and settings.get("served_model") == MODEL and settings.get("served_effort") == EFFORT,
    )
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    if archive is not None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(workspace, archive, dirs_exist_ok=True)
    return result


def backfill_metadata(workspace: Path) -> dict:
    """Add reconstructible command/output evidence to an older archive without rerunning Codex."""
    path = workspace / "authoring.json"
    result = json.loads(path.read_text())
    original_workspace = workspace
    for line in (workspace / "codex_stdout.jsonl").read_text().splitlines():
        event = json.loads(line)
        item = event.get("item") or {}
        output = item.get("aggregated_output") or ""
        if item.get("type") == "command_execution" and output.startswith("/"):
            candidate = output.splitlines()[0]
            if Path(candidate).name.startswith("rdr-v2-author-"):
                original_workspace = Path(candidate)
                break
    result["command"] = _author_command(original_workspace)
    result["original_workspace"] = str(original_workspace)
    result["stdout_sha256"] = _sha(workspace / "codex_stdout.jsonl")
    result["stderr_sha256"] = _sha(workspace / "codex_stderr.txt")
    prompts = sorted(workspace.glob("revision_feedback*.md"))
    for revision, prompt_path in zip(result.get("revisions", []), prompts, strict=True):
        number = revision["number"]
        revision["command"] = _revision_command(result["thread_id"], prompt_path.read_text())
        revision["stdout_sha256"] = _sha(workspace / f"revision_{number}_stdout.jsonl")
        revision["stderr_sha256"] = _sha(workspace / f"revision_{number}_stderr.txt")
    if result.get("revisions") and result["revisions"][-1].get("solution_sha256") == result.get("solution_sha256"):
        result["revisions"][-1]["source_snapshot"] = _snapshot(
            workspace, workspace / "solution.py", result["revisions"][-1]["number"]
        )
    path.write_text(json.dumps(result, indent=2, sort_keys=True))
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--revise", type=Path, help="resume using deterministic feedback from this file")
    parser.add_argument("--backfill-metadata", action="store_true")
    args = parser.parse_args(argv)
    if args.backfill_metadata:
        action = backfill_metadata(args.workspace)
    else:
        action = revise(args.workspace, args.revise, args.timeout, args.archive) if args.revise else author(
            args.workspace, args.timeout, args.archive
        )
    print(json.dumps(action, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
