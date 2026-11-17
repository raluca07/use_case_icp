import json
import subprocess

import pytest

from rdr.v2_provenance import (capture_code_snapshot, verify_code_snapshot,
                               verify_current_code_snapshot)
from rdr.v2_review import _reviewer_snapshot_id


def test_code_snapshot_verification_detects_tampering(tmp_path):
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "staged.diff").write_bytes(b"staged")
    (root / "unstaged.diff").write_bytes(b"unstaged")
    import hashlib
    record = {
        "schema_version": 1, "head": "abc", "git_status_porcelain": "",
        "staged_diff": {"path": "staged.diff", "sha256": hashlib.sha256(b"staged").hexdigest(),
                        "bytes": 6},
        "unstaged_diff": {"path": "unstaged.diff", "sha256": hashlib.sha256(b"unstaged").hexdigest(),
                          "bytes": 8},
        "untracked_files": [],
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["snapshot_id"] = "dirty-tree-sha256:" + hashlib.sha256(canonical).hexdigest()
    (root / "code_provenance.json").write_text(json.dumps(record))
    from rdr.freeze import write_manifest
    write_manifest(root)
    assert verify_code_snapshot(root) == []
    (root / "staged.diff").write_text("changed")
    assert verify_code_snapshot(root)


def test_modifying_reviewer_code_after_freezing_prevents_execution(tmp_path):
    repository = tmp_path / "repository"
    source = repository / "src" / "rdr"
    source.mkdir(parents=True)
    reviewer = source / "reviewer.py"
    reviewer.write_text("MODEL = 'frozen'\n")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "frozen reviewer"], cwd=repository, check=True)

    snapshot = tmp_path / "snapshot"
    record = capture_code_snapshot(snapshot, repository)
    assert verify_current_code_snapshot(snapshot, repository) == []
    assert _reviewer_snapshot_id(snapshot, repository) == record["snapshot_id"]

    reviewer.write_text("MODEL = 'modified-after-freeze'\n")
    assert verify_current_code_snapshot(snapshot, repository)
    with pytest.raises(RuntimeError, match="current reviewer code differs"):
        _reviewer_snapshot_id(snapshot, repository)


def test_modifying_etiq_replay_harness_after_freezing_prevents_execution(tmp_path):
    repository = tmp_path / "repository"
    source = repository / "src" / "rdr"
    fixture = repository / "fixtures" / "v2"
    source.mkdir(parents=True)
    fixture.mkdir(parents=True)
    (source / "reviewer.py").write_text("MODEL = 'frozen'\n")
    harness = fixture / "etiq_replay_entry.py"
    harness.write_text("VALUE = 'frozen'\n")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "frozen harness"], cwd=repository, check=True)
    snapshot = tmp_path / "snapshot"
    capture_code_snapshot(snapshot, repository)
    assert verify_current_code_snapshot(snapshot, repository) == []
    harness.write_text("VALUE = 'changed'\n")
    assert verify_current_code_snapshot(snapshot, repository)
