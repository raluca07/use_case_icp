import inspect

import rdr.v2_dry_run as module


def test_dry_run_has_no_hand_authored_trace_or_reviewer_call():
    assert not hasattr(module, "sample_faulty_trace")
    source = inspect.getsource(module.dry_run)
    assert "_real_pair" in source
    assert "reviewer_calls" in source
    assert "review_with_backoff" not in source


def test_source_bearing_classes_replay_mutated_source_in_build():
    source = inspect.getsource(module._real_pair)
    assert '{"source", "mixed", "interaction", "amplified"}' in source
    assert "mutate_source(source, fault_id)" in source


def test_interactive_arms_are_excluded_from_one_shot_build():
    assert "N" not in module.NON_INTERACTIVE_ARMS
    assert "O" not in module.NON_INTERACTIVE_ARMS


def test_clean_and_faulty_instances_share_one_arm_builder_and_walk_graph():
    source = inspect.getsource(module._write_instance)
    assert source.count("build_package_v2") == 1
    assert "_flat_graph" in source
    assert "interactive_flat_graph_matches_c" in source


def test_public_ids_and_manifest_hide_causal_metadata(tmp_path):
    root = tmp_path / "build"
    (root / "public").mkdir(parents=True)
    (root / "private").mkdir()
    row = {"instance_id": module._public_id("live-codex-L01-repaired"), "arm": "A",
           "package_sha256": "abc", "tokens": 1, "fault_id": "L01", "fault_class": "action",
           "repair": "repaired", "fault_occurred": True, "residual_harm_present": False,
           "author": "codex", "generator_cluster": "L01", "trace_sha256": "trace",
           "task_input_sha256": "task", "source_sha256": "source"}
    interactive = root / "public" / "interactive" / row["instance_id"]
    interactive.mkdir(parents=True)
    for name in ("walk.json", "N.initial.txt", "O.initial.txt"):
        (interactive / name).write_text(name)
    module._write_package_manifests(root, [row])
    public = (root / "public" / "package_manifest.jsonl").read_text()
    assert row["instance_id"].startswith("v6-") and "L01" not in row["instance_id"]
    assert not any(value in public for value in ("L01", "action", "repaired", "fault_occurred"))
    assert "L01" in (root / "private" / "package_truth_manifest.jsonl").read_text()
