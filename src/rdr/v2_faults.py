"""Direct v2 fault builders and deterministic four-cell qualification."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from dataclasses import asdict, dataclass

from rdr.v2_schema import TraceV2, with_observed_response
from rdr.v2_live import run_fresh_cell


@dataclass(frozen=True)
class FaultSpec:
    fault_id: str
    fault_class: str
    mechanism: str
    source_component: str | None = None
    runtime_component: str | None = None
    injection_channel: str | None = None


def _specs(prefix: str, fault_class: str, mechanisms: list[str]) -> list[FaultSpec]:
    return [FaultSpec(f"{prefix}{index:02d}", fault_class, mechanism) for index, mechanism in enumerate(mechanisms, 1)]


ACTION = _specs("L", "action", [
    "wrong scalar write argument", "wrong entity or recipient argument", "wrong destination path",
    "wrong held value propagated to later calls",
])
SOURCE = _specs("S", "source", [
    "wrong scalar expression", "wrong entity expression", "wrong response field", "premature conversion",
    "wrong comparison boundary", "wrong effective-time basis", "wrong first-result selection",
    "wrong filter scope", "non-cumulative aggregation", "wrong fallback branch", "wrong authorization condition",
    "incomplete compensation", "unsafe ordinary path construction",
])
RUNTIME = _specs("R", "runtime", [
    "sibling value substituted", "stale value returned", "results reordered", "item duplicated", "field omitted",
    "parseable malformed field", "failure before commit", "commit with lost acknowledgement",
    "partial multi-operation commit", "delayed event", "concurrent update", "clock skew", "permission change",
    "schema change", "filesystem partial failure", "bounded exhaustion",
])
MIXED_PLANNING = [
    FaultSpec(f"M{i:02d}", "mixed", source, source, runtime)
    for i, (source, runtime) in enumerate([
        ("wrong entity expression", "stale identifier"), ("wrong amount calculation", "wrong rate"),
        ("wrong time comparison", "clock skew"), ("wrong output path", "wrong base directory"),
        ("wrong authorization scope", "stale permission"), ("incomplete compensation", "partial failure"),
        ("wrong parser fallback", "missing field"), ("wrong integration field", "schema drift"),
    ], 1)
]
INTERACTION_PLANNING = [
    FaultSpec(fault_id, "interaction", source, source, runtime)
    for fault_id, source, runtime in [
        ("I01", "trust first result", "reordered results"),
        ("I02", "no identity cross-check", "sibling entity"),
        ("I03", "non-idempotent retry", "lost acknowledgement"),
        ("I04", "reuse cached value", "concurrent update"),
        ("I05", "silent default", "missing field"),
        ("I06", "weak validation", "malformed response"),
        ("I07", "trust permission claim", "stale claim"),
        ("I15", "non-atomic update", "interruption"),
        ("I16", "weak result validation", "corrupted result"),
    ]
]
AMPLIFIED_PLANNING = [
    FaultSpec(fault_id, "amplified", existing, existing, amplifier)
    for fault_id, existing, amplifier in [
        ("A01", "wrong amount", "corrupted rate"),
        ("A02", "wrong entity", "concurrent spread"),
        ("A03", "duplicate-prone retry", "delayed acknowledgements"),
        ("A04", "incomplete repair", "downstream failure"),
    ]
]
MECHANICAL_COMBINED = [
    FaultSpec(
        "M02", "mixed",
        "off-by-one amount expression for INV-V2-001 plus corrupted retrieved amount for INV-V2-002",
        "M02_AMOUNT_OFF_BY_ONE", "M02_SECOND_INVOICE_AMOUNT",
    ),
    FaultSpec(
        "I06", "interaction",
        "trust optional runtime_rate response field plus injected runtime_rate=2",
        "I06_RUNTIME_RATE_TRUST", "I06_RUNTIME_RATE_FIELD",
    ),
    FaultSpec(
        "A01", "amplified",
        "off-by-one amount for INV-V2-001 plus doubled retrieved amount for INV-V2-001",
        "A01_AMOUNT_OFF_BY_ONE", "A01_DOUBLE_RETRIEVED_AMOUNT",
    ),
]
FAULT_SPECS = {
    spec.fault_id: spec
    for spec in [*ACTION, *SOURCE, *RUNTIME, *MECHANICAL_COMBINED]
}
PLANNING_FAULT_SPECS = {
    spec.fault_id: {**asdict(spec), "implementation_status": "not_implemented"}
    for spec in [*MIXED_PLANNING, *INTERACTION_PLANNING, *AMPLIFIED_PLANNING]
    if spec.fault_id not in FAULT_SPECS
}


def root_cause_evidence(
    fault_id: str, source_locations: list[str], plan: dict | None,
) -> tuple[list[str], list[int]]:
    """Bind private causal truth to the admitted intervention, never a reviewer answer."""
    spec = FAULT_SPECS[fault_id]
    locations = (
        sorted(set(source_locations))
        if spec.fault_class in {"source", "mixed", "interaction", "amplified"}
        else []
    )
    plan = plan or {}
    events = []
    if spec.fault_class == "action" and isinstance(plan.get("index"), int):
        events.append(plan["index"])
    if spec.fault_class in {"runtime", "mixed", "interaction", "amplified"}:
        patch = plan.get("patch")
        if isinstance(patch, dict) and isinstance(patch.get("index"), int):
            events.append(patch["index"])
    if spec.fault_class == "action" and not events:
        raise ValueError(f"{fault_id}: action intervention lacks a causal event index")
    if spec.fault_class in {"source", "mixed", "interaction", "amplified"} and not locations:
        raise ValueError(f"{fault_id}: source intervention lacks a causal source location")
    if spec.fault_class in {"runtime", "mixed", "interaction", "amplified"} and not events:
        raise ValueError(f"{fault_id}: runtime intervention lacks a causal event index")
    return locations, sorted(set(events))


SOURCE_REPLACEMENTS = {
    "S01": [( 'amount=invoice["amount_usd"]',
              'amount=(invoice["amount_usd"] + 1 if invoice["invoice_id"] == "INV-V2-001" else invoice["amount_usd"])'),
             ('amount=payload["amount_usd"]',
              'amount=(payload["amount_usd"] + 1 if payload["invoice_id"] == "INV-V2-001" else payload["amount_usd"])')],
    "S02": [( 'user_email=invoice["sender_email"]', 'user_email="alex.invoicer.v2@example.com"'),
             ('user_email=payload["sender_email"]', 'user_email="alex.invoicer.v2@example.com"')],
    "S03": [
        ('request_id = response["payment_request_id"]', 'request_id = response["message"]'),
        ('request_id = result["payment_request_id"]', 'request_id = result["message"]'),
    ],
    "S04": [( 'amount=invoice["amount_usd"]', 'amount=round(invoice["amount_usd"])'),
             ('amount=payload["amount_usd"]', 'amount=round(payload["amount_usd"])')],
    "S05": [
        ("if len(matches) != 1:", "if len(matches) < 1:"),
        ("if len(users) != 1:", "if len(users) < 1:"),
        ("if len(matching_users) != 1:", "if len(matching_users) < 1:"),
    ],
    "S06": [
        ('access_token=gmail_token, read=False', 'access_token=gmail_token, read=False, max_created_at="2020-01-01"'),
        ('            read=False,\n', '            read=False,\n            max_created_at="2020-01-01",\n'),
    ],
    "S07": [
        ("source = incoming[-1]", "source = incoming[0]"),
        ('for candidate in reversed(thread["emails"])', 'for candidate in thread["emails"]'),
        ("email = matching_emails[-1]", "email = matching_emails[0]"),
    ],
    "S08": [
        ('thread["subject"].startswith("Invoice request:")', '"Invoice request:" in thread["subject"]'),
        ('.startswith(SUBJECT_PREFIX)', '.__contains__(SUBJECT_PREFIX)'),
    ],
    "S09": [("created += 1", "created = 1"),
            ('counts["created"] += 1', 'counts["created"] = 1')],
    "S10": [
        ('return None\n    if not isinstance(invoice, dict)', 'return {}\n    if not isinstance(invoice, dict)'),
        ('return None, "invalid_json"', 'return {}, None'),
        ('return None, "invalid_payload"', 'return {}, None'),
    ],
    "S11": [
        ('if user["email"] == invoice["sender_email"]', 'if invoice["sender_email"] in user["email"]'),
        ('if user.get("email") == email', 'if email in user.get("email", "")'),
        ('if user.get("email") == payload["sender_email"]',
         'if payload["sender_email"] in user.get("email", "")'),
    ],
    "S12": [("        apis.gmail.reply_to_email(\n", "        # omitted dependent confirmation\n        (lambda **kwargs: None)(\n")],
    "S13": [
        ('or not SAFE_INVOICE_ID.fullmatch(invoice["invoice_id"])', ''),
        ('INVOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")', 'INVOICE_ID_PATTERN = re.compile(r".*")'),
    ],
}


def mutate_source(source: str, fault_id: str) -> tuple[str, str]:
    """Return actual executable source mutation and its private location description."""
    if fault_id == "I06":
        if 'amount=invoice["amount_usd"]' in source:
            old = 'amount=invoice["amount_usd"]'
            new = 'amount=invoice["amount_usd"] * matches[0].get("runtime_rate", 1)'
        else:
            old = 'amount=payload["amount_usd"]'
            new = 'amount=payload["amount_usd"] * matching_users[0].get("runtime_rate", 1)'
        if old not in source:
            raise ValueError("source span for I06 is absent")
        mutated = source.replace(old, new, 1)
        compile(mutated, "workflow.py", "exec")
        return mutated, f"workflow.py:{source[:source.index(old)].count(chr(10)) + 1}"
    if fault_id == "A01":
        if 'amount=invoice["amount_usd"]' in source:
            old = 'amount=invoice["amount_usd"]'
            new = 'amount=(invoice["amount_usd"] + 1 if invoice["invoice_id"] == "INV-V2-001" else invoice["amount_usd"])'
        else:
            old = 'amount=payload["amount_usd"]'
            new = 'amount=(payload["amount_usd"] + 1 if payload["invoice_id"] == "INV-V2-001" else payload["amount_usd"])'
        if old not in source:
            raise ValueError("source span for A01 is absent")
        mutated = source.replace(old, new, 1)
        compile(mutated, "workflow.py", "exec")
        return mutated, f"workflow.py:{source[:source.index(old)].count(chr(10)) + 1}"
    mapped = fault_id
    if fault_id == "M02":
        mapped = "S01"
    if mapped not in SOURCE_REPLACEMENTS:
        raise ValueError(f"{fault_id} has no executable source component")
    replacement = next(((old, new) for old, new in SOURCE_REPLACEMENTS[mapped] if old in source), None)
    if replacement is None:
        raise ValueError(f"source span for {fault_id} is absent")
    old, new = replacement
    mutated = source.replace(old, new, 1)
    compile(mutated, "workflow.py", "exec")
    line = source[: source.index(old)].count("\n") + 1
    return mutated, f"workflow.py:{line}"


def mutate_action(args: dict, fault_id: str) -> dict:
    changed = copy.deepcopy(args)
    if fault_id == "L01":
        changed["amount"] = float(changed.get("amount", 1)) + 1
    elif fault_id == "L02":
        key = "user_email" if "user_email" in changed else "receiver_email"
        changed[key] = "alex.invoicer.v2@example.com"
    elif fault_id == "L03":
        changed["file_path"] = "~/Documents/payment_requests/wrong.txt"
    elif fault_id == "L04":
        changed["description"] = "held-wrong-value"
    else:
        raise ValueError(f"not an action fault: {fault_id}")
    return changed


def runtime_observation(raw: object, fault_id: str) -> object:
    """Build exactly what workflow code observes while leaving `raw` available privately."""
    value = copy.deepcopy(raw)
    if fault_id == "R03" and isinstance(value, list):
        return list(reversed(value))
    if fault_id == "R04" and isinstance(value, list) and value:
        return [*value, copy.deepcopy(value[0])]
    if fault_id == "R05":
        if isinstance(value, list):
            return value[:-1]
        if isinstance(value, dict) and value:
            value.pop(next(iter(value)))
            return value
    if fault_id == "R06" and isinstance(value, dict) and value:
        key = next(iter(value))
        value[key] = str(value[key]) + ".0"
        return value
    raise ValueError(f"{fault_id} requires a live AppWorld runtime plan, not an offline response marker")


def apply_runtime_fault(trace: TraceV2, index: int, fault_id: str) -> TraceV2:
    raw = next(call.raw_response for call in trace.calls if call.index == index)
    return with_observed_response(trace, index, runtime_observation(raw, fault_id))


def classify_four_cells(cells: dict[str, set[str]]) -> str | None:
    clean = cells["S0R0"]
    source = cells["S1R0"] - clean
    runtime = cells["S0R1"] - clean
    combined = cells["S1R1"] - clean
    if not source and not runtime and combined:
        return "interaction"
    if source and runtime:
        return "amplified" if combined - (source | runtime) else "mixed"
    if (source or runtime) and combined - (source | runtime):
        return "amplified"
    if source and not runtime:
        return "source"
    if runtime and not source:
        return "runtime"
    return None


RUNTIME_COMPONENTS = {
    **{f"R{i:02d}": f"R{i:02d}" for i in range(1, 17)},
    "M02": "M02_SECOND_INVOICE_AMOUNT",
    "I06": "I06_RUNTIME_RATE_FIELD",
    "A01": "A01_DOUBLE_RETRIEVED_AMOUNT",
}


def _harms(clean: dict, result: dict) -> set[str]:
    checks = clean["evaluation"]["checks"]
    faulty = result.get("evaluation", {}).get("checks", {})
    harms = {"check:" + key for key, passed in checks.items() if passed and not faulty.get(key, False)}
    clean_delta = clean.get("state_delta", {})
    faulty_delta = result.get("state_delta", {})
    for change in ("created", "updated", "deleted"):
        tables = set(clean_delta.get(change, {})) | set(faulty_delta.get(change, {}))
        for table in tables:
            if clean_delta.get(change, {}).get(table) != faulty_delta.get(change, {}).get(table):
                harms.add(f"delta:{change}:{table}")
    if result.get("failed_calls"):
        harms.add("runtime:failed_call")
    if result.get("execution_error"):
        harms.add("runtime:execution_error")
    return harms


def _amount_severity(result: dict) -> float:
    expected = {"Design review": 12.5, "Research materials": 37.25}
    deviations = []
    for call in result.get("trace", {}).get("calls", []):
        for write in call.get("writes", []):
            after = write.get("after")
            if write.get("record", "").startswith("venmo.payment_requests#") and isinstance(after, dict):
                amount, description = after.get("amount"), after.get("description")
                if isinstance(amount, (int, float)) and description in expected:
                    deviations.append(abs(float(amount) - expected[description]))
    return max(deviations, default=0.0)


def classify_measured_cells(results: dict[str, dict], clean: dict) -> str | None:
    harms = {name: _harms(clean, result) for name, result in results.items()}
    inferred = classify_four_cells(harms)
    if inferred == "mixed":
        combined = _amount_severity(results["S1R1"])
        singleton = max(_amount_severity(results["S1R0"]), _amount_severity(results["S0R1"]))
        if combined > singleton and combined - singleton >= 1:
            return "amplified"
    return inferred


def _write_cell(root: Path, fault_id: str, name: str, result: dict) -> dict:
    path = root / "cells" / fault_id / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "measured_harms": []}


def _first_call(result: dict, api: str, predicate=None) -> dict:
    for call in result["trace"]["calls"]:
        if call["api"] == api and (predicate is None or predicate(call)):
            return call
    raise ValueError(f"clean execution did not call {api}")


def _nth_call(result: dict, api: str, occurrence: int = 0, predicate=None) -> dict:
    matches = [call for call in result["trace"]["calls"]
               if call["api"] == api and (predicate is None or predicate(call))]
    if occurrence >= len(matches):
        raise ValueError(f"clean execution has no occurrence {occurrence} of {api}")
    return matches[occurrence]


def _runtime_plan(fault_id: str, clean: dict) -> dict:
    component = RUNTIME_COMPONENTS.get(fault_id, fault_id)
    search = _nth_call(clean, "search_users", 0)
    thread = _nth_call(clean, "show_thread", 0)
    inbox = _nth_call(clean, "show_inbox_threads", 0)
    create = _nth_call(clean, "create_payment_request", 0)
    create_file = _nth_call(clean, "create_file", 0)
    if fault_id == "M02":
        second_thread = _nth_call(clean, "show_thread", 1)
        return {"patch": {"index": second_thread["index"], "operation": "replace_text",
                           "value": '"amount_usd":37.25', "replacement": '"amount_usd":38.25'}}
    if fault_id == "I06":
        return {"patch": {"index": search["index"], "operation": "set_field_each",
                           "field": "runtime_rate", "value": 2}}
    if fault_id == "A01":
        return {"patch": {"index": thread["index"], "operation": "replace_text",
                           "value": '"amount_usd":12.5', "replacement": '"amount_usd":25.0'}}
    recipes = {
        "R01": {"index": search["index"], "operation": "replace",
                "value": "alex.invoice.v2@example.com", "replacement": "alex.invoicer.v2@example.com"},
        "R02": {"index": _nth_call(clean, "file_exists", 0)["index"], "operation": "replace",
                "value": False, "replacement": True},
        "R03": {"index": search["index"], "operation": "reverse"},
        "R04": {"index": inbox["index"], "operation": "duplicate_first"},
        "R05": {"index": thread["index"], "operation": "omit_field", "field": "emails"},
        "R06": {"index": search["index"], "operation": "replace",
                "value": "alex.invoice.v2@example.com", "replacement": "alex.invoice.v2@example.com.0"},
        "R07": {"index": create["index"], "operation": "raise_before", "message": "timeout before commit"},
        "R08": {"index": create["index"], "operation": "raise_after", "message": "acknowledgement lost after commit"},
        "R09": {"index": create_file["index"], "operation": "raise_before", "message": "later operation failed"},
        "R10": {"index": inbox["index"], "operation": "reverse"},
        "R11": {"index": create_file["index"], "operation": "concurrent_update", "amount": 13.5},
        "R12": {"index": search["index"], "operation": "set_field_each",
                "field": "registered_at", "value": "2099-01-01T00:00:00"},
        "R13": {"index": create_file["index"], "operation": "invalid_token", "arg": "access_token"},
        "R14": {"index": create["index"], "operation": "rename_field",
                "field": "payment_request_id", "replacement": "request_id_v2"},
        "R15": {"index": create_file["index"], "operation": "partial_file"},
        "R16": {"index": thread["index"], "operation": "resource_exhaustion"},
    }
    return {"patch": recipes[component]}


def _action_plan(fault_id: str, clean: dict, repaired: bool = False) -> dict:
    first_request = _nth_call(clean, "create_payment_request", 0)
    first_file = _nth_call(clean, "create_file", 0)
    if fault_id == "L01":
        return _amount_plan(first_request["index"], repaired)
    if fault_id == "L02":
        return {"index": first_request["index"], "app": "venmo", "api": "create_payment_request",
                "arg": "user_email", "value": "alex.invoicer.v2@example.com"}
    if fault_id == "L03":
        return {"index": first_file["index"], "app": "file_system", "api": "create_file",
                "arg": "file_path", "value": "~/Documents/payment_requests/wrong.txt"}
    if fault_id == "L04":
        return {"index": first_request["index"], "app": "venmo", "api": "create_payment_request",
                "arg": "amount", "value": 13.5,
                "held": {"api": "create_payment_request", "arg": "amount", "value": 37.25,
                         "wrong": 13.5, "mode": "equal"}}
    raise ValueError(f"unknown action fault {fault_id}")


def _run_and_write(root: Path, fault_id: str, cell: str, source: str, author: str,
                   plan: dict | None = None) -> tuple[dict, dict]:
    try:
        result = run_fresh_cell(source, author, plan)
    except Exception as exception:
        result = {
            "execution_error": f"{type(exception).__name__}: {exception}",
            "evaluation": {"passed": False, "checks": {}},
            "trace": {"calls": [], "source": {"workflow.py": source}},
            "failed_calls": [],
            "process": {"fresh_root": True, "cleanup_attempted": True},
        }
    artifact = _write_cell(root, fault_id, cell, result)
    return result, artifact


def _amount_plan(index: int, repaired: bool) -> dict:
    plan = {"index": index, "app": "venmo", "api": "create_payment_request", "arg": "amount", "value": 13.5}
    if repaired:
        plan["repair"] = {
            "timing": "before_final", "app": "venmo", "api": "update_payment_request",
            "args": {"amount": 12.5, "description": "Design review"},
            "copy_args": ["access_token"],
            "id_param": "payment_request_id", "id_table": "venmo.payment_requests",
            "id_match": {"amount": 13.5, "description": "Design review"},
        }
    return plan


def _file_repair(clean: dict, occurrence: int) -> dict:
    call = _nth_call(clean, "create_file", occurrence)
    return {
        "timing": "before_final", "app": "file_system", "api": "update_file",
        "args": {"file_path": call["args"]["file_path"], "content": call["args"]["content"]},
        "copy_from": {"app": "file_system", "api": "create_file", "occurrence": occurrence},
        "copy_args": ["access_token"],
    }


def _source_repair_plan(clean: dict) -> dict:
    plan = _amount_plan(0, True)
    plan.pop("index")
    plan.pop("app")
    plan.pop("api")
    plan.pop("arg")
    plan.pop("value")
    plan["repair_only"] = True
    plan["repair"]["additional"] = [_file_repair(clean, 0)]
    return plan


def _update_amount_repair(bad_amount: float, good_amount: float, description: str,
                          additional: list[dict] | None = None) -> dict:
    repair = {
        "timing": "before_final", "app": "venmo", "api": "update_payment_request",
        "args": {"amount": good_amount, "description": description},
        "copy_args": ["access_token"], "id_param": "payment_request_id",
        "id_table": "venmo.payment_requests",
        "id_match": {"amount": bad_amount, "description": description},
    }
    if additional:
        repair["additional"] = additional
    return {"patch": None, "repair_only": True, "repair": repair}


def _payment_replacement_repairs(bad_amount: float, description: str, user_email: str,
                                 good_amount: float | None = None) -> list[dict]:
    """Delete one bad-recipient request and recreate the intended request through documented APIs."""
    amount = bad_amount if good_amount is None else good_amount
    selector = {"app": "venmo", "api": "create_payment_request", "occurrence": 0}
    return [
        {
            "timing": "before_final", "app": "venmo", "api": "delete_payment_request",
            "args": {}, "copy_args": ["access_token"], "id_param": "payment_request_id",
            "id_table": "venmo.payment_requests",
            "id_match": {"amount": bad_amount, "description": description},
        },
        {
            "timing": "before_final", "app": "venmo", "api": "create_payment_request",
            "args": {"user_email": user_email, "amount": amount, "description": description},
            "copy_from": selector, "copy_args": ["access_token"],
        },
    ]


def _repair_plan_for(fault_id: str, clean: dict) -> dict:
    first_request = _nth_call(clean, "create_payment_request", 0)
    first_file = _nth_call(clean, "create_file", 0)
    if fault_id == "L01":
        return _action_plan(fault_id, clean, True)
    if fault_id == "L02":
        repairs = _payment_replacement_repairs(12.5, "Design review", "alex.invoice.v2@example.com")
        plan = _action_plan(fault_id, clean)
        plan["repair"] = {**repairs[0], "additional": repairs[1:]}
        return plan
    if fault_id == "L03":
        plan = _action_plan(fault_id, clean)
        plan["repair"] = {
            "timing": "before_final", "app": "file_system", "api": "move_file",
            "args": {"source_file_path": "~/Documents/payment_requests/wrong.txt",
                     "destination_file_path": "~/Documents/payment_requests/INV-V2-001.txt"},
            "copy_from": {"app": "file_system", "api": "create_file", "occurrence": 0},
            "copy_args": ["access_token"],
        }
        return plan
    if fault_id == "L04":
        plan = _action_plan(fault_id, clean)
        plan.update(_update_amount_repair(13.5, 12.5, "Design review"))
        plan["index"] = first_request["index"]
        plan["app"], plan["api"], plan["arg"], plan["value"] = (
            "venmo", "create_payment_request", "amount", 13.5)
        return plan
    if fault_id == "S01":
        return _source_repair_plan(clean)
    if fault_id == "S02":
        repairs = [
            *_payment_replacement_repairs(12.5, "Design review", "alex.invoice.v2@example.com"),
            *_payment_replacement_repairs(37.25, "Research materials", "blair.invoice.v2@example.com"),
        ]
        return {"repair_only": True, "repair": {**repairs[0], "additional": repairs[1:]}}
    if fault_id == "S04":
        additional = [
            _update_amount_repair(37.0, 37.25, "Research materials")["repair"],
            _file_repair(clean, 0),
            _file_repair(clean, 1),
        ]
        return _update_amount_repair(12.0, 12.5, "Design review", additional)
    if fault_id == "R01":
        plan = _runtime_plan(fault_id, clean)
        plan["repair_only"] = True
        plan["repair"] = {
            "timing": "before_final", "app": "venmo", "api": "create_payment_request",
            "args": {"user_email": "alex.invoice.v2@example.com", "amount": 12.5,
                     "description": "Design review"},
            "copy_from": {"app": "venmo", "api": "search_users", "occurrence": 0},
            "copy_args": ["access_token"],
        }
        return plan
    if fault_id == "R11":
        plan = _runtime_plan(fault_id, clean)
        plan.update(_update_amount_repair(13.5, 12.5, "Design review"))
        plan["patch"] = _runtime_plan(fault_id, clean)["patch"]
        return plan
    if fault_id == "R15":
        plan = _runtime_plan(fault_id, clean)
        plan["repair_only"] = True
        plan["repair"] = {
            "timing": "before_final", "app": "file_system", "api": "update_file",
            "args": {"file_path": first_file["args"]["file_path"],
                     "content": first_file["args"]["content"]},
            "copy_from": {"app": "file_system", "api": "create_file", "occurrence": 0},
            "copy_args": ["access_token"],
        }
        return plan
    if fault_id == "M02":
        second = _update_amount_repair(38.25, 37.25, "Research materials")["repair"]
        plan = _runtime_plan(fault_id, clean)
        plan.update(_update_amount_repair(13.5, 12.5, "Design review",
                                          [second, _file_repair(clean, 1)]))
        plan["patch"] = _runtime_plan(fault_id, clean)["patch"]
        return plan
    if fault_id == "I06":
        plan = _runtime_plan(fault_id, clean)
        plan.update(_update_amount_repair(25.0, 12.5, "Design review"))
        plan["patch"] = _runtime_plan(fault_id, clean)["patch"]
        return plan
    if fault_id == "A01":
        plan = _runtime_plan(fault_id, clean)
        plan.update(_update_amount_repair(26.0, 12.5, "Design review",
                                          [_file_repair(clean, 0)]))
        plan["patch"] = _runtime_plan(fault_id, clean)["patch"]
        return plan
    raise ValueError(f"no repair plan for {fault_id}")


REPAIR_LIMITATIONS = {
    "S03": "The wrong response field loses the request identifier before downstream artifacts can be addressed.",
    "S06": "The effective-time filter skips work without producing a repairable primary row.",
    "S09": "The fault only corrupts the final supervisor count; no API can revise a completed answer in-pipeline.",
    "S12": "Restoring omitted Gmail confirmations requires reconstructing per-thread dynamic recipients and IDs.",
    "R05": "The omitted emails field aborts before a repairable primary mutation exists.",
    "R06": "The malformed search result causes a skip without producing a repairable primary row.",
    "R07": "The before-commit exception terminates execution before an in-pipeline correction can run.",
    "R08": "The lost acknowledgement terminates control flow after commit before dependent artifacts can be repaired.",
    "R09": "The raised file-system failure terminates execution before a corrective in-pipeline call can run.",
    "R13": "The invalid-token file call terminates execution before a corrective in-pipeline call can run.",
    "R14": "The renamed response field aborts before the workflow can identify its created request.",
    "R16": "Bounded exhaustion terminates execution before a corrective in-pipeline call can run.",
    "M06": "The combined raised file failure terminates before its omitted confirmations can be reconstructed.",
    "M08": "The combined response-field faults lose the dynamic request IDs needed for faithful downstream repair.",
}


def repair_limitation(fault_id: str) -> str:
    return REPAIR_LIMITATIONS.get(fault_id, "No documented API-faithful repair plan restores this measured locus.")


def qualify_faults(source: str, root: Path, author: str = "codex",
                   fault_ids: set[str] | None = None) -> list[dict]:
    """Attempt every registered mechanism in fresh worlds and infer class from measured cells."""
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for spec in FAULT_SPECS.values():
        fault_id = spec.fault_id
        if fault_ids is not None and fault_id not in fault_ids:
            continue
        try:
            clean, clean_artifact = _run_and_write(root, fault_id, "S0R0", source, author)
            clean_artifact["measured_harms"] = []
            results, cells, locations = {"S0R0": clean}, {"S0R0": clean_artifact}, []
            if spec.fault_class == "action":
                faulty, artifact = _run_and_write(root, fault_id, "A1", source, author,
                                                  _action_plan(fault_id, clean))
                results["A1"], cells["A1"] = faulty, artifact
                inferred = "action" if _harms(clean, faulty) else None
            elif spec.fault_class == "source":
                mutated, location = mutate_source(source, fault_id)
                locations.append(location)
                faulty, artifact = _run_and_write(root, fault_id, "S1R0", mutated, author)
                results["S1R0"], cells["S1R0"] = faulty, artifact
                inferred = "source" if _harms(clean, faulty) else None
            elif spec.fault_class == "runtime":
                faulty, artifact = _run_and_write(root, fault_id, "S0R1", source, author,
                                                  _runtime_plan(fault_id, clean))
                results["S0R1"], cells["S0R1"] = faulty, artifact
                inferred = "runtime" if _harms(clean, faulty) else None
            else:
                mutated, location = mutate_source(source, fault_id)
                locations.append(location)
                source_only, source_artifact = _run_and_write(root, fault_id, "S1R0", mutated, author)
                runtime_plan = _runtime_plan(fault_id, clean)
                runtime_only, runtime_artifact = _run_and_write(root, fault_id, "S0R1", source, author, runtime_plan)
                combined, combined_artifact = _run_and_write(root, fault_id, "S1R1", mutated, author, runtime_plan)
                results.update(S1R0=source_only, S0R1=runtime_only, S1R1=combined)
                cells.update(S1R0=source_artifact, S0R1=runtime_artifact, S1R1=combined_artifact)
                inferred = classify_measured_cells(results, clean)
            for name, artifact in cells.items():
                artifact["measured_harms"] = [] if name == "S0R0" else sorted(_harms(clean, results[name]))
            harmful = inferred is not None
            status = "qualified" if harmful and inferred == spec.fault_class else "unqualified"
            reason = (f"Measured classification {inferred or 'none'} from fresh AppWorld cells."
                      if status == "unqualified" else "Declared class reproduced from measured AppWorld harms.")
            admitted = 0
            if status == "qualified":
                try:
                    plan = _repair_plan_for(fault_id, clean)
                except ValueError:
                    reason += " Repair limitation: " + repair_limitation(fault_id)
                else:
                    repair_source = (mutated if spec.fault_class in {
                        "source", "mixed", "interaction", "amplified"
                    } else source)
                    repaired, repaired_artifact = _run_and_write(
                        root, fault_id, "repaired", repair_source, author, plan)
                    repaired_artifact["measured_harms"] = sorted(_harms(clean, repaired))
                    cells["repaired"] = repaired_artifact
                    try:
                        from rdr.v2_pipeline import validate_execution_pair
                        unrepaired = (results.get("S1R1") or results.get("S1R0")
                                      or results.get("S0R1") or results.get("A1"))
                        pair_validation = validate_execution_pair(unrepaired, repaired, clean)
                        if not repaired.get("evaluation", {}).get("passed"):
                            raise ValueError("repaired evaluator did not pass")
                        if not pair_validation["primary_state_restored"]:
                            raise ValueError("repair did not restore its primary final-state artifacts")
                    except ValueError as error:
                        pair_validation = {"passed": False, "reason": str(error)}
                        reason += " Repair was rejected: " + str(error)
                    else:
                        pair_validation["passed"] = True
                        admitted = 1
                        reason += (" Deterministic policy admitted the evaluator-passing in-pipeline repair; "
                                   "historical and residual effects are recorded separately.")
                    record_path = root / "cells" / fault_id / "pair_validation.json"
                    record_path.write_text(json.dumps(pair_validation, indent=2, sort_keys=True))
                    cells["pair_validation"] = {
                        "path": str(record_path), "sha256": hashlib.sha256(record_path.read_bytes()).hexdigest()
                    }
            records.append({**asdict(spec), "status": status, "attempted": len(cells),
                            "admitted": admitted, "variants": ["repaired", "unrepaired"] if admitted else [],
                            "cells": cells, "inferred_classification": inferred,
                            "source_locations": locations, "reason": reason})
        except Exception as exception:
            records.append({**asdict(spec), "status": "blocked", "attempted": 0, "admitted": 0,
                            "variants": [], "cells": {}, "inferred_classification": None,
                            "reason": f"Concrete builder could not bind to exact authored source/API trace: {type(exception).__name__}: {exception}"})
    return records
