from rdr.freeze import MANIFEST_NAME, verify_manifest, write_manifest


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
