from pathlib import Path
import inspect
import json

from rdr.v2_faults import (FAULT_SPECS, PLANNING_FAULT_SPECS,
                           _runtime_plan, apply_runtime_fault,
                           classify_four_cells, mutate_action, mutate_source,
                           root_cause_evidence)
from rdr.v2_schema import CallV2, TraceV2
import rdr.v2_faults as faults_module


def test_complete_fault_register():
    expected = {*(f"L{i:02d}" for i in range(1, 5)), *(f"S{i:02d}" for i in range(1, 14)),
                *(f"R{i:02d}" for i in range(1, 17)), "M02", "I06", "A01"}
    assert set(FAULT_SPECS) == expected
    assert all(not fault_id.startswith("P") for fault_id in FAULT_SPECS)
    assert all(spec.injection_channel is None for spec in FAULT_SPECS.values())
    assert all(item["implementation_status"] == "not_implemented"
               for item in PLANNING_FAULT_SPECS.values())
    assert not any(fault_id.startswith("P") for fault_id in PLANNING_FAULT_SPECS)
    assert not ({"I08", "I09", "I10", "I11", "I12", "I13", "I14", "A05", "A08"}
                & set(PLANNING_FAULT_SPECS))


def test_source_action_and_raw_observed_builders_are_real():
    source = Path("fixtures/v2/reference_solution.py").read_text()
    mutated, location = mutate_source(source, "S01")
    assert mutated != source and location.startswith("workflow.py:")
    assert mutate_action({"amount": 2}, "L01")["amount"] == 3
    trace = TraceV2("t", "x", "x", [CallV2(0, "x", "list", {}, [{"id": 1}, {"id": 2}], [{"id": 1}, {"id": 2}])], {"w.py": source})
    changed = apply_runtime_fault(trace, 0, "R03")
    assert changed.calls[0].raw_response == [{"id": 1}, {"id": 2}]
    assert changed.calls[0].observed_response == [{"id": 2}, {"id": 1}]
    interaction, _ = mutate_source(source, "I06")
    assert 'matches[0].get("runtime_rate", 1)' in interaction


def test_four_cell_classes():
    assert classify_four_cells({"S0R0": set(), "S1R0": set(), "S0R1": set(), "S1R1": {"x"}}) == "interaction"
    assert classify_four_cells({"S0R0": set(), "S1R0": {"s"}, "S0R1": {"r"}, "S1R1": {"s", "r"}}) == "mixed"
    assert classify_four_cells({"S0R0": set(), "S1R0": {"s"}, "S0R1": set(), "S1R1": {"s", "extra"}}) == "amplified"


def _clean_result():
    calls = []
    for index, api in enumerate(("search_users", "show_thread", "show_thread",
                                 "show_inbox_threads", "create_payment_request", "create_file")):
        calls.append({"index": index, "api": api, "app": "x", "args": {}})
    return {"trace": {"calls": calls}}


def test_combined_fault_descriptions_match_the_executable_mechanisms():
    source = Path("fixtures/v2/reference_solution.py").read_text()
    m02, _ = mutate_source(source, "M02")
    i06, _ = mutate_source(source, "I06")
    a01, _ = mutate_source(source, "A01")
    plans = {fault_id: _runtime_plan(fault_id, _clean_result())
             for fault_id in ("M02", "I06", "A01")}
    assert "INV-V2-001" in m02 and "+ 1" in m02
    assert plans["M02"]["patch"]["value"] == '"amount_usd":37.25'
    assert plans["M02"]["patch"]["replacement"] == '"amount_usd":38.25'
    assert FAULT_SPECS["M02"].mechanism == (
        "off-by-one amount expression for INV-V2-001 plus corrupted retrieved amount for INV-V2-002")
    assert 'get("runtime_rate", 1)' in i06
    assert plans["I06"]["patch"]["field"] == "runtime_rate"
    assert plans["I06"]["patch"]["value"] == 2
    assert FAULT_SPECS["I06"].mechanism == (
        "trust optional runtime_rate response field plus injected runtime_rate=2")
    assert "INV-V2-001" in a01 and "+ 1" in a01
    assert plans["A01"]["patch"]["replacement"] == '"amount_usd":25.0'


def test_no_security_fault_mechanism_is_executable():
    forbidden = ("prompt", "injection", "exfiltrat", "shell", "poison", "agent handoff", "credential")
    descriptions = "\n".join(spec.mechanism.lower() for spec in FAULT_SPECS.values())
    assert not any(term in descriptions for term in forbidden)
    assert "S14" not in faults_module.SOURCE_REPLACEMENTS


def test_mechanical_qualification_has_no_codex_transport():
    source = inspect.getsource(faults_module.qualify_faults)
    assert "run_authoring" not in source and "v2_review" not in source
    assert "subprocess" not in source


def test_admission_requires_primary_restoration_and_preserves_residual_reporting():
    source = inspect.getsource(faults_module.qualify_faults)
    assert 'pair_validation["primary_state_restored"]' in source
    assert 'pair_validation["residual_harmful_artifacts"]' not in source


def test_every_admitted_fault_has_intervention_bound_root_cause_for_both_repairs():
    records = json.loads(Path(
        "runs/v2/qualification-v8r2-reliability-20261114/qualification.json"
    ).read_text())
    cell_by_class = {
        "action": "A1", "source": "S1R0", "runtime": "S0R1",
        "mixed": "S1R1", "interaction": "S1R1", "amplified": "S1R1",
    }
    admitted = [record for record in records if record["admitted"]]
    assert {record["fault_id"] for record in admitted} == {
        "L01", "S01", "S04", "R11", "R15", "M02", "I06", "A01",
    }
    for record in admitted:
        evidence = []
        for variant in (cell_by_class[record["fault_class"]], "repaired"):
            run = json.loads(Path(record["cells"][variant]["path"]).read_text())
            evidence.append(root_cause_evidence(
                record["fault_id"], record["source_locations"],
                run.get("fault_plan") or run.get("plan"),
            ))
        assert evidence[0] == evidence[1]
        locations, events = evidence[0]
        assert bool(locations) == (record["fault_class"] in {
            "source", "mixed", "interaction", "amplified",
        })
        assert bool(events) == (record["fault_class"] in {
            "action", "runtime", "mixed", "interaction", "amplified",
        })
