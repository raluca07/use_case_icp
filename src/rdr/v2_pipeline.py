"""Validation of real repaired/unrepaired AppWorld execution pairs."""
from __future__ import annotations

import json

from rdr.v2_schema import TraceV2


def _final_values(trace: TraceV2) -> dict[str, object]:
    final = {}
    for call in trace.calls:
        for write in call.writes:
            final[write.record] = write.after
    return final


def _call_payload(call) -> str:
    return json.dumps({"name": call.name, "args": call.args, "raw": call.raw_response,
                       "observed": call.observed_response,
                       "writes": [write.__dict__ for write in call.writes]},
                      sort_keys=True, default=str)


def validate_execution_pair(unrepaired: dict, repaired: dict, clean: dict) -> dict:
    """Prove independent harm, real correction calls and complete primary restoration."""
    if any(result.get("process", {}).get("fresh_root") is not True
           for result in (unrepaired, repaired, clean)):
        raise ValueError("all pair results must be fresh-world executions")
    run_ids = [result.get("execution_graph", {}).get("run_id")
               for result in (unrepaired, repaired, clean)]
    if len(set(run_ids)) != 3:
        raise ValueError("fault variants and clean reference must be independent AppWorld executions")
    unrepaired_trace = TraceV2.from_dict(unrepaired["trace"])
    repaired_trace = TraceV2.from_dict(repaired["trace"])
    clean_trace = TraceV2.from_dict(clean["trace"])
    repair_index = repaired.get("repair_index")
    corrective_apis = {
        "venmo.update_payment_request", "venmo.delete_payment_request",
        "venmo.create_payment_request",
        "file_system.move_file", "file_system.update_file",
        "file_system.create_file",
        "gmail.reply_to_email", "gmail.label_thread",
        "gmail.mark_thread_read",
    }
    repairs = [call for call in repaired_trace.calls
               if call.name in corrective_apis and repair_index is not None and call.index >= repair_index]
    if not repairs or repair_index != repairs[0].index:
        raise ValueError("repaired execution does not contain a real recorded repair action")
    if repaired.get("repair_error"):
        raise ValueError(f"repair failed: {repaired['repair_error']}")
    if unrepaired["evaluation"]["passed"] is not False:
        raise ValueError("unrepaired execution has no measured harm")
    repair_writes = [write for call in repairs for write in call.writes]
    if not repair_writes:
        raise ValueError("repair calls produced no measured AppWorld state change")

    clean_by_index = {call.index: call for call in clean_trace.calls}
    harmful_indices = []
    for call in repaired_trace.calls:
        if call.index >= repair_index:
            continue
        clean_call = clean_by_index.get(call.index)
        if clean_call is None or _call_payload(call) != _call_payload(clean_call):
            harmful_indices.append(call.index)
    planned = repaired.get("fault_plan", {})
    for index in [planned.get("index"), *repaired.get("substituted", [])]:
        if isinstance(index, int) and index < repair_index:
            harmful_indices.append(index)
    harmful_indices = sorted(set(harmful_indices))
    if not harmful_indices:
        raise ValueError("no measured harmful event before repair")
    if any(index >= repair_index for index in harmful_indices):
        raise ValueError("a corrective call was classified as harmful")

    historical = sorted({write.record for call in repaired_trace.calls
                         if call.index in harmful_indices for write in call.writes})
    unrepaired_harmful = sorted(call.index for call in unrepaired_trace.calls
                                if call.index not in clean_by_index
                                or _call_payload(call) != _call_payload(clean_by_index[call.index]))
    clean_final, repaired_final = _final_values(clean_trace), _final_values(repaired_trace)
    unrepaired_final = _final_values(unrepaired_trace)
    repair_targets = sorted({write.record for write in repair_writes})
    restoration = {record: repaired_final.get(record) == clean_final.get(record)
                   for record in repair_targets}
    restored_records = sorted(record for record, restored in restoration.items() if restored)
    primary_state_restored = bool(repair_targets) and all(restoration.values())
    residual_records = sorted(record for record in set(historical) | set(repair_targets)
                              if repaired_final.get(record) != clean_final.get(record))
    irreversible = sorted(record for record, value in repaired_final.items()
                          if value != clean_final.get(record) and record not in repair_targets)
    residual_checks = sorted(key for key, passed in repaired["evaluation"]["checks"].items() if not passed)
    residual_labels = sorted(set(residual_records) | set(irreversible))
    unrepaired_residual = sorted(record for record, value in unrepaired_final.items()
                                 if value != clean_final.get(record))
    if any(label.startswith("check:") for label in residual_labels):
        raise ValueError("private evaluator check leaked into scored artifacts")
    return {
        "variants": ["repaired", "unrepaired"],
        "independent_run_ids": run_ids,
        "repair_call_indices": [call.index for call in repairs],
        "corrective_call_indices": [call.index for call in repairs],
        "harmful_runtime_indices": harmful_indices,
        "unrepaired_harmful_runtime_indices": unrepaired_harmful,
        "first_harmful_event": harmful_indices[0],
        "primary_restoration_by_artifact": restoration,
        "primary_state_restored": primary_state_restored,
        "historically_corrupted_artifacts": historical,
        "restored_artifacts": restored_records,
        "residual_harmful_artifacts": residual_labels,
        "unrepaired_residual_harmful_artifacts": unrepaired_residual,
        "irreversible_side_effect_artifacts": irreversible,
        "residual_failed_checks": residual_checks,
    }
