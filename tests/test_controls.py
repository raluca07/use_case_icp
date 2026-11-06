import json

import pytest
from builders import clean_trace, persistent_trace

from rdr.controls import analyse, anchor_of, control_jobs, derive
from rdr.freeze import verify_manifest, write_manifest
from rdr.packager import ARMS, CONTROL_ARMS, build_package
from rdr.pilot import load_instances
from rdr.truth import Truth

SYMPTOM = "splitwise.expenses#77"


def _write(root, instance_id, variant, trace, origin, twin_of=None, anchor=1):
    d = root / instance_id
    (d / "packages").mkdir(parents=True)
    trace.save(d / "trace.json")
    Truth(instance_id, origin is not None, origin, [SYMPTOM] if origin is not None else [], [], SYMPTOM).save(
        d / "truth.json")
    meta = {"instance_id": instance_id, "variant": variant, "generator": "g1", "origin_index": origin,
            "twin_of": twin_of}
    (d / "meta.json").write_text(json.dumps(meta))
    for arm in ARMS:
        (d / "packages" / f"{arm}.txt").write_text(
            build_package(arm, trace, SYMPTOM, instance_id, avoid_calls=frozenset({anchor})))


@pytest.fixture
def frozen(tmp_path):
    src = tmp_path / "pilot"
    src.mkdir()
    _write(src, "p1", "persistent", persistent_trace(), 1)
    _write(src, "c1", "clean", clean_trace(), None, twin_of="p1")
    write_manifest(src)
    return src


def test_anchor_of_uses_the_twin_for_a_clean_instance():
    metas = {"p1": {"instance_id": "p1", "origin_index": 4, "twin_of": None},
             "c1": {"instance_id": "c1", "origin_index": None, "twin_of": "p1"}}
    assert anchor_of(metas["p1"], metas) == 4 and anchor_of(metas["c1"], metas) == 4


def test_derive_adds_control_packages_and_leaves_the_source_frozen(frozen, tmp_path):
    out = tmp_path / "controls"
    summary = derive(frozen, out, None)
    assert summary["instances"] == 2 and summary["new_packages"] == 2 * len(CONTROL_ARMS)
    assert verify_manifest(frozen) == [] and verify_manifest(out) == []
    for arm in ARMS + CONTROL_ARMS:
        assert (out / "c1" / "packages" / f"{arm}.txt").exists()
    assert "call:1 =" not in (out / "p1" / "packages" / "M.txt").read_text().split("PROVENANCE GRAPH")[1]


def test_derive_refuses_when_a_rebuilt_package_differs(frozen, tmp_path):
    (frozen / "p1" / "packages" / "C.txt").write_text("tampered")
    write_manifest(frozen)
    with pytest.raises(RuntimeError, match="differs"):
        derive(frozen, tmp_path / "controls", None)


def test_derive_refuses_a_broken_source_manifest(frozen, tmp_path):
    (frozen / "p1" / "meta.json").write_text("{}")
    with pytest.raises(RuntimeError, match="freeze"):
        derive(frozen, tmp_path / "controls", None)


def test_analyse_with_no_reviews_scores_every_arm_as_a_miss(frozen, tmp_path):
    out = tmp_path / "controls"
    derive(frozen, out, None)
    instances = load_instances(out)
    assert len(control_jobs(instances)) == 2 * len(CONTROL_ARMS)
    result = analyse(out, tmp_path / "none", tmp_path / "none2", tmp_path / "report.md")
    assert all(t["origin"] == (0, 1) and t["failed"] == 2 for t in result["table"].values())
    assert "| J vs C |" in (tmp_path / "report.md").read_text()
