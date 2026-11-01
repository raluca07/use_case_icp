"""sha256 manifest so hypotheses, instances and packages are frozen before any reviewer call."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_NAME = "MANIFEST.sha256.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _included(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if relative.as_posix() == MANIFEST_NAME or path.name == ".DS_Store" or "__pycache__" in relative.parts:
        return False
    return path.is_file()


def build_manifest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _sha256(p) for p in sorted(root.rglob("*")) if _included(root, p)}


def write_manifest(root: Path) -> Path:
    out = root / MANIFEST_NAME
    out.write_text(json.dumps(build_manifest(root), indent=2, sort_keys=True))
    return out


def verify_manifest(root: Path) -> list[str]:
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return ["missing manifest"]
    recorded = json.loads(manifest.read_text())
    current = build_manifest(root)
    problems = [f"changed: {k}" for k in sorted(recorded) if k in current and current[k] != recorded[k]]
    problems += [f"missing: {k}" for k in sorted(recorded) if k not in current]
    problems += [f"extra: {k}" for k in sorted(current) if k not in recorded]
    return problems
