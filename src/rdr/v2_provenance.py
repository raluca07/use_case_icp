"""Capture and verify the exact dirty-tree code snapshot used by V2."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from rdr.freeze import verify_manifest, write_manifest


def _run(*args: str, cwd: Path | None = None) -> bytes:
    return subprocess.check_output(["git", *args], cwd=cwd)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _executable_files(repository_root: Path) -> list[dict]:
    source_root = repository_root / "src" / "rdr"
    paths = [
        *sorted(source_root.rglob("*.py")),
        repository_root / "fixtures" / "v2" / "etiq_replay_entry.py",
    ]
    return [
        {"path": path.relative_to(repository_root).as_posix(), "sha256": _sha(path.read_bytes())}
        for path in paths
        if path.is_file()
    ]


def capture_code_snapshot(root: Path, repository_root: Path | None = None) -> dict:
    repository_root = (repository_root or Path.cwd()).resolve()
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)
    staged = _run("diff", "--binary", "--cached", cwd=repository_root)
    unstaged = _run("diff", "--binary", cwd=repository_root)
    (root / "staged.diff").write_bytes(staged)
    (root / "unstaged.diff").write_bytes(unstaged)
    untracked = []
    for raw_path in _run("ls-files", "--others", "--exclude-standard", "-z", cwd=repository_root).split(b"\0"):
        if not raw_path:
            continue
        path = repository_root / raw_path.decode()
        if path.is_file():
            untracked.append({
                "path": path.relative_to(repository_root).as_posix(),
                "sha256": _sha(path.read_bytes()),
            })
    record = {
        "schema_version": 1,
        "head": _run("rev-parse", "HEAD", cwd=repository_root).decode().strip(),
        "git_status_porcelain": _run("status", "--porcelain=v1", cwd=repository_root).decode(),
        "staged_diff": {"path": "staged.diff", "sha256": _sha(staged), "bytes": len(staged)},
        "unstaged_diff": {"path": "unstaged.diff", "sha256": _sha(unstaged), "bytes": len(unstaged)},
        "untracked_files": untracked,
        "executable_root": "src/rdr",
        "executable_files": _executable_files(repository_root),
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["snapshot_id"] = "dirty-tree-sha256:" + _sha(canonical)
    (root / "code_provenance.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    write_manifest(root)
    return record


def verify_code_snapshot(root: Path) -> list[str]:
    problems = verify_manifest(root)
    if problems:
        return problems
    record = json.loads((root / "code_provenance.json").read_text())
    for field in ("staged_diff", "unstaged_diff"):
        item = record[field]
        path = root / item["path"]
        if _sha(path.read_bytes()) != item["sha256"]:
            problems.append(f"{field} hash differs")
    canonical_record = {key: value for key, value in record.items() if key != "snapshot_id"}
    canonical = json.dumps(canonical_record, sort_keys=True, separators=(",", ":")).encode()
    expected = "dirty-tree-sha256:" + _sha(canonical)
    if record.get("snapshot_id") != expected:
        problems.append("aggregate snapshot hash differs")
    return problems


def verify_current_code_snapshot(root: Path, repository_root: Path | None = None) -> list[str]:
    """Require the live executable tree and Git HEAD to match a frozen reviewer snapshot."""
    problems = verify_code_snapshot(root)
    if problems:
        return problems
    repository_root = (repository_root or Path.cwd()).resolve()
    record = json.loads((root / "code_provenance.json").read_text())
    expected_files = record.get("executable_files")
    if not isinstance(expected_files, list):
        return ["snapshot lacks executable file identity"]
    current_head = _run("rev-parse", "HEAD", cwd=repository_root).decode().strip()
    if current_head != record.get("head"):
        problems.append(f"Git HEAD differs: expected {record.get('head')}, found {current_head}")
    expected = {item["path"]: item["sha256"] for item in expected_files}
    current = {item["path"]: item["sha256"] for item in _executable_files(repository_root)}
    missing = sorted(set(expected) - set(current))
    added = sorted(set(current) - set(expected))
    changed = sorted(path for path in set(expected) & set(current) if expected[path] != current[path])
    if missing:
        problems.append(f"executable files missing: {missing[:5]}")
    if added:
        problems.append(f"executable files added: {added[:5]}")
    if changed:
        problems.append(f"executable files changed: {changed[:5]}")
    return problems


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--out", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify_current = sub.add_parser("verify-current")
    verify_current.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "capture":
        result = capture_code_snapshot(args.out)
    elif args.command == "verify":
        problems = verify_code_snapshot(args.root)
        result = {"problems": problems, "verified": not problems}
        if problems:
            print(json.dumps(result, indent=2, sort_keys=True))
            raise SystemExit(1)
    else:
        problems = verify_current_code_snapshot(args.root)
        result = {"problems": problems, "verified": not problems}
        if problems:
            print(json.dumps(result, indent=2, sort_keys=True))
            raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
