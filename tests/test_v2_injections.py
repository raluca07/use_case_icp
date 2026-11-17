import json
from pathlib import Path

from rdr.v2_injections import (
    all_pairs,
    prepare_injection_workspace,
    qualify_prompt_injections,
    structural_source_diff,
)


def test_injections_are_complete_local_and_harmless():
    data = json.loads(Path("fixtures/v2/injections.json").read_text())
    assert [item["id"] for item in data["fixtures"]] == [f"P{i:02d}" for i in range(1, 15)]
    text = json.dumps(data)
    assert "http://" not in text and "https://" not in text
    assert data["local_outbox"].startswith("./")
    assert data["harmless_canary_file"].startswith("./")


def test_poisoned_pairs_change_only_outside_structured_json():
    pairs = all_pairs()
    assert len(pairs) == 14
    assert [pair["id"] for pair in pairs if pair["expressible"]] == [f"P{i:02d}" for i in range(1, 15)]
    for pair in (pair for pair in pairs if pair["id"] == "P02"):
        clean_payload = pair["clean"].split("BEGIN_INVOICE\n", 1)[1].split("\nEND_INVOICE", 1)[0]
        poisoned_payload = pair["poisoned"].split("BEGIN_INVOICE\n", 1)[1].split("\nEND_INVOICE", 1)[0]
        assert clean_payload == poisoned_payload == pair["structured_payload"]
    assert all(pair["exposure"] == "codex_authoring" for pair in pairs)
    for pair in (pair for pair in pairs if int(pair["id"][1:]) >= 11):
        assert pair["poisoned"] == pair["clean"] + pair["injection_payload"]
        assert pair["control"]["failed_checks"]


def test_neutral_pair_prompt_and_structural_diff(tmp_path):
    pair = next(pair for pair in all_pairs() if pair["id"] == "P03")
    clean_text, _ = prepare_injection_workspace(tmp_path / "clean", pair, False)
    poisoned_text, _ = prepare_injection_workspace(tmp_path / "poisoned", pair, True)
    assert clean_text == poisoned_text
    assert "untrusted" not in clean_text.lower()
    diff = structural_source_diff("def f():\n    return 1\n", "def f():\n    return 2\n")
    assert diff["executable_structure_changed"] and diff["changed_functions"] == ["f"]


def test_prompt_fault_requires_every_paired_authoring_and_replay_gate(tmp_path, monkeypatch):
    def exposure(pair, workspace, poisoned, timeout):
        workspace.mkdir(parents=True)
        source = "def solution():\n    amount = 999\n" if poisoned else "def solution():\n    amount = 1\n"
        (workspace / "solution.py").write_text(source)
        return {
            "model_completed": True,
            "agent_exposed_to_payload": poisoned,
            "controlled_deviations": (["controlled_source_marker:999"] if poisoned else []),
            "injection_payload_sha256": "a" * 64,
        }

    def replay(source, author):
        poisoned = "999" in source
        return {"evaluation": {"passed": not poisoned, "checks": {
            "request_exact_INV-V2-001": not poisoned,
        }}, "execution_error": None}

    monkeypatch.setattr("rdr.v2_injections.run_authoring_exposure", exposure)
    monkeypatch.setattr("rdr.v2_injections.run_fresh_cell", replay)
    record = qualify_prompt_injections(tmp_path, candidate_ids={"P12"}, workers=1)[0]
    assert record["status"] == "susceptible"
    assert record["admitted"] == 0
    assert all(record["qualification_gates"].values())
    assert record["scientific_role"] == "authoring_security_susceptibility"
    assert record["experimental_fault_eligible"] is False


def test_unsuccessful_prompt_attempt_is_retained_as_resistant_control(tmp_path, monkeypatch):
    def exposure(pair, workspace, poisoned, timeout):
        workspace.mkdir(parents=True)
        (workspace / "solution.py").write_text("def solution():\n    return 1\n")
        return {
            "model_completed": True,
            "agent_exposed_to_payload": poisoned,
            "controlled_deviations": [],
            "injection_payload_sha256": "b" * 64,
        }

    monkeypatch.setattr("rdr.v2_injections.run_authoring_exposure", exposure)
    monkeypatch.setattr("rdr.v2_injections.run_fresh_cell", lambda source, author: {
        "evaluation": {"passed": True, "checks": {"receipt_exact_INV-V2-001": True}},
        "execution_error": None,
    })
    record = qualify_prompt_injections(tmp_path, candidate_ids={"P13"}, workers=1)[0]
    assert record["status"] == "resistant"
    assert record["admitted"] == 0
    assert record["scientific_role"] == "injection_resistant_control"
