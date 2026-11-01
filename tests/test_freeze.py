from rdr.freeze import MANIFEST_NAME, build_manifest, verify_manifest, write_manifest


def _tree(root):
    (root / "packages").mkdir()
    (root / "packages" / "a.txt").write_text("A")
    (root / "hypotheses.md").write_text("H1")


def test_intact_tree_verifies(tmp_path):
    _tree(tmp_path)
    assert write_manifest(tmp_path).name == MANIFEST_NAME
    assert verify_manifest(tmp_path) == []


def test_changes_are_reported(tmp_path):
    _tree(tmp_path)
    write_manifest(tmp_path)
    (tmp_path / "packages" / "a.txt").write_text("B")
    (tmp_path / "hypotheses.md").unlink()
    (tmp_path / "new.txt").write_text("N")
    assert verify_manifest(tmp_path) == ["changed: packages/a.txt", "missing: hypotheses.md", "extra: new.txt"]


def test_ds_store_and_pycache_are_ignored(tmp_path):
    _tree(tmp_path)
    write_manifest(tmp_path)
    (tmp_path / ".DS_Store").write_bytes(b"x")
    (tmp_path / "packages" / ".DS_Store").write_bytes(b"y")
    (tmp_path / "pkg" / "__pycache__").mkdir(parents=True)
    (tmp_path / "pkg" / "__pycache__" / "m.pyc").write_bytes(b"z")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "n.pyc").write_bytes(b"z")
    assert verify_manifest(tmp_path) == []
    assert all("DS_Store" not in k and "__pycache__" not in k for k in build_manifest(tmp_path))


def test_manifest_is_excluded_only_at_the_root(tmp_path):
    _tree(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / MANIFEST_NAME).write_text("nested")
    write_manifest(tmp_path)
    assert f"sub/{MANIFEST_NAME}" in build_manifest(tmp_path)
    assert MANIFEST_NAME not in build_manifest(tmp_path)
    (tmp_path / "sub" / MANIFEST_NAME).write_text("tampered")
    assert verify_manifest(tmp_path) == [f"changed: sub/{MANIFEST_NAME}"]


def test_missing_manifest_is_reported(tmp_path):
    _tree(tmp_path)
    assert verify_manifest(tmp_path) == ["missing manifest"]


def test_appledouble_files_and_ipynb_checkpoints_are_ignored(tmp_path):
    _tree(tmp_path)
    write_manifest(tmp_path)
    (tmp_path / "packages" / "._a.txt").write_bytes(b"x")
    (tmp_path / "._hypotheses.md").write_bytes(b"x")
    (tmp_path / "nb" / ".ipynb_checkpoints").mkdir(parents=True)
    (tmp_path / "nb" / ".ipynb_checkpoints" / "n-checkpoint.ipynb").write_text("{}")
    assert verify_manifest(tmp_path) == []
    assert all("._" not in k and ".ipynb_checkpoints" not in k for k in build_manifest(tmp_path))


def test_names_that_merely_contain_the_ignored_markers_are_kept(tmp_path):
    _tree(tmp_path)
    (tmp_path / "a._b.txt").write_text("keep")
    (tmp_path / "ipynb_checkpoints.txt").write_text("keep")
    assert {"a._b.txt", "ipynb_checkpoints.txt"} <= set(build_manifest(tmp_path))
