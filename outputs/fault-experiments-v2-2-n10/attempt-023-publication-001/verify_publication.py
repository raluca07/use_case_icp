#!/usr/bin/env python3
"""Build or verify the curated Attempt 023 Git publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


PUBLICATION_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PUBLICATION_ROOT.parents[2]
ATTEMPT_ROOT = PUBLICATION_ROOT.parent / "attempt-023"
PRESERVATION_ROOT = PUBLICATION_ROOT.parent / "attempt-023-results-preservation-001"
MANIFEST_PATH = PUBLICATION_ROOT / "publication-manifest.json"
CHECKSUMS_PATH = PUBLICATION_ROOT / "checksums.sha256"
HANDOFF_PATH = REPO_ROOT / (
    "instructions_between_agent_types/developer/handoffs/"
    "N13_attempt_023_results_preservation_001_to_overseer.email.md"
)
PRESERVATION_FILES = {
    "README.md",
    "checksums.sha256",
    "initial-review-results.csv",
    "preservation-manifest.json",
    "repair-validity.json",
    "token-usage.json",
    "verify_preservation.py",
}
PUBLICATION_FILES = {
    "README.md",
    "checksums.sha256",
    "publication-manifest.json",
    "verify_publication.py",
}
SECRET_PATTERNS = {
    "private_key": re.compile(
        rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    ),
    "aws_access_key": re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "google_api_key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "github_token": re.compile(
        rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"
    ),
    "openai_or_anthropic_key": re.compile(
        rb"(?:sk-ant-[A-Za-z0-9_-]{20,}|"
        rb"(?:^|[^A-Za-z0-9_-])sk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{20,})"
    ),
    "slack_token": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "bearer_token": re.compile(rb"Bearer\s+[A-Za-z0-9._~+/-]{20,}"),
    "credentialed_url": re.compile(rb"https?://[^/@\s]+:[^/@\s]+@"),
    "jwt": re.compile(
        rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
}


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": relative(path), "bytes": len(data), "sha256": sha256_bytes(data)}


def add_referenced_paths(value: Any, selected: set[Path]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "path" and isinstance(child, str):
                path = REPO_ROOT / child
                if path.is_file():
                    selected.add(path.resolve())
            else:
                add_referenced_paths(child, selected)
    elif isinstance(value, list):
        for child in value:
            add_referenced_paths(child, selected)
    elif isinstance(value, str) and value.endswith("/output/response.json"):
        path = REPO_ROOT / value
        if path.is_file():
            selected.add(path.resolve())


def is_generated_pipeline_file(path: Path) -> bool:
    if path.name in {"pipeline-manifest.json", "pipeline-input.json"}:
        return True
    return path.suffix == ".py" and "/pipeline/generated/" in path.as_posix()


def is_raw_ledger_file(path: Path) -> bool:
    try:
        parts = path.relative_to(ATTEMPT_ROOT).parts
    except ValueError:
        return False
    return bool(parts) and parts[0] == "ledger"


def select_publication_files() -> list[Path]:
    selected = {
        path.resolve()
        for path in PRESERVATION_ROOT.iterdir()
        if path.is_file() and path.name in PRESERVATION_FILES
    }
    selected.add(HANDOFF_PATH.resolve())
    selected.add((ATTEMPT_ROOT / "packages.json").resolve())
    for name in ("preservation-manifest.json", "repair-validity.json"):
        add_referenced_paths(load_json(PRESERVATION_ROOT / name), selected)
    for path in (ATTEMPT_ROOT / "instance-work").rglob("*"):
        if path.is_file() and is_generated_pipeline_file(path):
            selected.add(path.resolve())
    return sorted(path for path in selected if not is_raw_ledger_file(path))


def group(path: Path) -> str:
    try:
        parts = path.relative_to(ATTEMPT_ROOT).parts
    except ValueError:
        parts = ()
    if parts:
        if parts[0] == "provider-branches":
            return "provider_responses"
        if parts[0] == "instance-work":
            return "pipelines"
        return parts[0]
    try:
        path.relative_to(PRESERVATION_ROOT)
        return "preservation"
    except ValueError:
        pass
    if path == HANDOFF_PATH.resolve():
        return "handoff"
    return "repository_" + path.relative_to(REPO_ROOT).parts[0]


def check_forbidden_paths(paths: list[Path]) -> None:
    for path in paths:
        rel = relative(path)
        parts = path.parts
        if ".codex" in parts or "auth.json" == path.name:
            raise ValueError(f"forbidden authentication path: {rel}")
        if path.suffix == ".log" or "__pycache__" in parts or path.suffix == ".pyc":
            raise ValueError(f"forbidden transient path: {rel}")
        if is_raw_ledger_file(path):
            raise ValueError(f"raw ledger must not be published: {rel}")
        try:
            attempt_parts = path.relative_to(ATTEMPT_ROOT).parts
        except ValueError:
            attempt_parts = ()
        if attempt_parts and attempt_parts[0] == "provider-branches":
            if attempt_parts[-2:] != ("output", "response.json"):
                raise ValueError(f"unexpected provider-branch file: {rel}")
        if attempt_parts and attempt_parts[0] == "instance-work":
            if not is_generated_pipeline_file(path):
                raise ValueError(f"unexpected instance-work file: {rel}")
        if path.stat().st_size >= 100_000_000:
            raise ValueError(f"file exceeds GitHub's individual-file limit: {rel}")


def scan_secrets(paths: list[Path]) -> None:
    matches: list[str] = []
    for path in paths:
        data = path.read_bytes()
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                matches.append(f"{name}: {relative(path)}")
    if matches:
        raise ValueError("credential-like material found:\n" + "\n".join(matches))


def validate_counts(counts: Counter[str]) -> None:
    expected = {
        "preservation": 7,
        "handoff": 1,
        "instances": 12,
        "captures": 12,
        "package-records": 96,
        "packages": 522,
        "packages.json": 1,
        "pipelines": 132,
        "reviews": 288,
        "repairs": 180,
        "provider_responses": 411,
        "analysis": 4,
        "anonymous-release": 8,
        "experiment-freeze.json": 1,
        "state": 1,
        "post-freeze-controller-correction.json": 1,
        "ledger-closure.json": 1,
        "release-verification.json": 1,
        "terminal.json": 1,
        "repository_src": 28,
        "repository_prompts": 4,
        "repository_schemas": 13,
        "repository_docs": 10,
    }
    observed = {name: counts[name] for name in expected}
    if observed != expected:
        raise ValueError(f"publication counts changed: {observed!r}")


def write_checksums() -> None:
    names = ("README.md", "publication-manifest.json", "verify_publication.py")
    lines = []
    for name in names:
        digest = hashlib.sha256((PUBLICATION_ROOT / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}\n")
    CHECKSUMS_PATH.write_text("".join(lines), encoding="utf-8")


def build() -> None:
    paths = select_publication_files()
    check_forbidden_paths(paths)
    scan_secrets(paths)
    records = [file_record(path) for path in paths]
    counts = Counter(group(path) for path in paths)
    validate_counts(counts)
    source_manifest = load_json(PRESERVATION_ROOT / "preservation-manifest.json")
    manifest = {
        "schema_version": "1",
        "publication_id": "attempt-023-publication-001",
        "source_preservation_id": source_manifest["preservation_id"],
        "complete_attempt_tree_sha256": source_manifest["complete_attempt_tree"][
            "tree_sha256"
        ],
        "selection_policy": {
            "included": [
                "all file paths explicitly bound by the preservation manifest except raw ledger files",
                "all 123 repair responses bound by repair-validity.json",
                "all frozen package records and package files",
                "generated pipeline sources, pipeline manifests, and pipeline inputs",
                "packages.json and the preservation handoff",
            ],
            "excluded": [
                "raw ledger files (tree hash retained in source preservation manifest)",
                "Codex homes, authentication, caches, runtime installations, and logs",
                "provider branch content other than 411 exact response.json files",
                "unreferenced work directories and transient controller state",
            ],
        },
        "file_count": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "category_counts": dict(sorted(counts.items())),
        "files": records,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_checksums()


def verify_checksums() -> None:
    for line in CHECKSUMS_PATH.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        observed = hashlib.sha256((PUBLICATION_ROOT / name).read_bytes()).hexdigest()
        if observed != digest:
            raise ValueError(f"publication metadata checksum mismatch: {name}")


def verify_preservation_checksums() -> None:
    path = PRESERVATION_ROOT / "checksums.sha256"
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        observed = hashlib.sha256((PRESERVATION_ROOT / name).resolve().read_bytes()).hexdigest()
        if observed != digest:
            raise ValueError(f"source preservation checksum mismatch: {name}")


def verify() -> None:
    unexpected = {
        path.name for path in PUBLICATION_ROOT.iterdir() if path.is_file()
    } - PUBLICATION_FILES
    if unexpected:
        raise ValueError(f"unexpected publication metadata files: {sorted(unexpected)!r}")
    verify_checksums()
    verify_preservation_checksums()
    manifest = load_json(MANIFEST_PATH)
    records = manifest.get("files")
    if not isinstance(records, list):
        raise ValueError("publication manifest lacks file records")
    paths: list[Path] = []
    seen: set[str] = set()
    for record in records:
        rel = str(record["path"])
        if rel in seen:
            raise ValueError(f"duplicate publication path: {rel}")
        seen.add(rel)
        path = REPO_ROOT / rel
        if not path.is_file():
            raise ValueError(f"missing publication file: {rel}")
        observed = file_record(path)
        if observed != record:
            raise ValueError(f"publication file changed: {rel}")
        paths.append(path.resolve())
    counts = Counter(group(path) for path in paths)
    validate_counts(counts)
    if manifest.get("file_count") != len(paths):
        raise ValueError("publication file count changed")
    if manifest.get("total_bytes") != sum(path.stat().st_size for path in paths):
        raise ValueError("publication byte count changed")
    source_manifest = load_json(PRESERVATION_ROOT / "preservation-manifest.json")
    if manifest.get("complete_attempt_tree_sha256") != source_manifest[
        "complete_attempt_tree"
    ]["tree_sha256"]:
        raise ValueError("complete-attempt hash binding changed")
    check_forbidden_paths(paths)
    scan_secrets(paths)
    print(
        f"PASS: {len(paths)} curated files and every publication binding verify exactly"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        build()
    verify()


if __name__ == "__main__":
    main()
