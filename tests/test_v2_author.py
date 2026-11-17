from pathlib import Path

from rdr.v2_author import DOCS, EFFORT, MODEL, TASK, prepare_workspace


def test_authoring_inputs_and_fresh_workspace(tmp_path):
    workspace = tmp_path / "author"
    prepare_workspace(workspace)
    assert MODEL == "gpt-5.6-sol" and EFFORT == "medium"
    assert (workspace / "TASK.md").read_text() == TASK.read_text()
    assert (workspace / "api_inventory.md").read_text() == DOCS.read_text()
