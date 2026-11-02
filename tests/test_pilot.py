import json
import sys
from pathlib import Path

import pytest

from rdr import pilot
from rdr.freeze import write_manifest

FAKE = (sys.executable, str(Path(__file__).with_name("fake_claude.py")))


def _make_instances(root: Path) -> Path:
    inst_dir = root / "instances"
    layout = [("persistent", True), ("nonpersistent", True), ("clean", False)]
    n = 0
    for gen in ("g1", "g2", "g3", "g4"):
        for variant, faulty in layout:
            n += 1
            iid = f"{gen}_1_{variant[:3]}{n}"
            d = inst_dir / iid
            (d / "packages").mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"instance_id": iid, "generator": gen, "variant": variant}))
            truth = {"instance_id": iid, "is_faulty": faulty, "origin_index": 1 if faulty else None,
                     "stale": ["splitwise.expenses#77", "splitwise.expenses#78"] if faulty else [], "missing": [],
                     "symptom": "splitwise.expenses#78" if faulty else "splitwise.expenses#5", "decoy_index": None,
                     "side_effect": []}
            (d / "truth.json").write_text(json.dumps(truth))
            call = {"index": 1, "app": "splitwise", "api": "x", "args": {}, "response": None,
                    "writes": [{"record": "splitwise.expenses#77", "before": None, "after": {"a": 1}}]}
            (d / "trace.json").write_text(json.dumps({"task_id": gen, "instruction": "i", "final_message": "m",
                                                      "calls": [call]}))
            for arm in pilot.ARMS:
                (d / "packages" / f"{arm}.txt").write_text(f"package {iid} {arm}")
    write_manifest(inst_dir)
    return inst_dir


def test_repeat_choice_is_deterministic_proportional_and_by_crc(tmp_path):
    inst_dir = _make_instances(tmp_path)
    instances = pilot.load_instances(inst_dir)
    chosen = pilot.choose_repeat_instances(instances)
    assert chosen == pilot.choose_repeat_instances(list(reversed(instances)))
    assert len(chosen) == 10
    variants = {i["id"]: i["variant"] for i in instances}
    counts = {v: sum(1 for c in chosen if variants[c] == v) for v in set(variants.values())}
    assert sum(counts.values()) == 10
    assert max(counts.values()) - min(counts.values()) <= 1
    for v in counts:
        ids = sorted(i for i in variants if variants[i] == v)
        picked = [i for i in chosen if variants[i] == v]
        rest = [i for i in ids if i not in picked]
        assert all(pilot._crc(p) <= pilot._crc(r) for p in picked for r in rest)


def test_sign_test_and_bootstrap():
    assert pilot.sign_test_p(0, 0) == 1.0
    assert pilot.sign_test_p(5, 0) == pytest.approx(0.0625)
    assert pilot.sign_test_p(3, 3) == 1.0
    lo, hi = pilot.cluster_bootstrap({"a": (1, 1), "b": (0, 1), "c": (1, 1)})
    assert 0.0 <= lo <= hi <= 1.0
    assert pilot.cluster_bootstrap({"a": (1, 1), "b": (0, 1)}) == pilot.cluster_bootstrap({"a": (1, 1), "b": (0, 1)})


def test_run_resume_analyse_with_fake_cli(tmp_path, monkeypatch):
    inst_dir = _make_instances(tmp_path)
    reviews, log = tmp_path / "reviews", tmp_path / "log.jsonl"
    count = tmp_path / "count.txt"
    monkeypatch.setenv("FAKE_COUNT_FILE", str(count))
    summary = pilot.run(inst_dir, reviews, log, claude_cmd=FAKE, sleep_fn=lambda s: None)
    assert summary == {"planned": 144, "done": 144, "resumed": 0, "failed": 0, "stopped": None}
    assert len(count.read_text().splitlines()) == 144
    again = pilot.run(inst_dir, reviews, log, claude_cmd=FAKE, sleep_fn=lambda s: None)
    assert again["resumed"] == 144 and len(count.read_text().splitlines()) == 144
    result = pilot.analyse(inst_dir, reviews, log, tmp_path / "scores.jsonl", tmp_path / "report.md")
    # the fake always says: wrong, origin 1, record 77 still wrong
    assert result["table"]["A"]["origin"] == (8, 8)
    assert result["table"]["A"]["detect"] == (8, 12)
    assert result["table"]["A"]["false_stale_inst"] == 4
    assert result["facts"]["completed"] == 144 and result["gate2"]["passed"] is False
    text = (tmp_path / "report.md").read_text()
    assert "Gate 2 origin-hit rule: FAIL" in text and "—" not in text and "–" not in text
    scores = [json.loads(line) for line in (tmp_path / "scores.jsonl").read_text().splitlines()]
    assert len(scores) == 144


def test_usage_limit_stops_cleanly_and_missing_counts_as_miss(tmp_path, monkeypatch):
    inst_dir = _make_instances(tmp_path)
    reviews, log = tmp_path / "reviews", tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_MODE", "fail")
    waits = []
    summary = pilot.run(inst_dir, reviews, log, claude_cmd=FAKE, sleep_fn=waits.append)
    assert summary["done"] == 0 and summary["failed"] == 1 and "usage limit" in summary["stopped"]
    assert waits == [60, 300, 1800]
    result = pilot.analyse(inst_dir, reviews, log, tmp_path / "s.jsonl", tmp_path / "r.md")
    assert result["table"]["A"]["failed"] == 12 and result["table"]["A"]["detect"][0] == 0
    assert result["table"]["A"]["origin"][0] == 0


def test_non_limit_failure_is_recorded_and_run_continues(tmp_path, monkeypatch):
    inst_dir = _make_instances(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "garbage")
    summary = pilot.run(inst_dir, tmp_path / "reviews", tmp_path / "log.jsonl", claude_cmd=FAKE,
                        sleep_fn=lambda s: None)
    assert summary["failed"] == 144 and summary["stopped"] is None


def test_run_refuses_a_changed_freeze(tmp_path):
    inst_dir = _make_instances(tmp_path)
    next(inst_dir.glob("*/packages/A.txt")).write_text("tampered")
    with pytest.raises(RuntimeError, match="freeze"):
        pilot.run(inst_dir, tmp_path / "reviews", tmp_path / "log.jsonl", claude_cmd=FAKE)
