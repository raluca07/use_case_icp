# Plan 1: Gate 0 discovery and AppWorld-independent core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer the AppWorld and Etiq unknowns on a real install (Gate 0), and build, test-first, every component of the stale-state experiment that does not depend on AppWorld internals: trace model, ground truth, provenance graph, evidence packager, isolated `claude -p` reviewer runner, scorer and freeze.

**Architecture:** A small Python package `rdr` (repairs don't retract) under `src/rdr/`. Components exchange plain JSON-serialisable dataclasses (`Trace`, `Truth`, `Graph`) and text packages; none calls another's internals. AppWorld and Etiq are touched only by two spike scripts in `spikes/`, whose findings feed Plan 2 (AppWorld adapter, fault templates, Haiku pilot).

**Tech Stack:** Python 3.13, pytest, AppWorld (`pip install appworld`), etiq-copilot 2.3.0 (`etiq_copilot`), Claude Code CLI (`claude -p`).

Spec: `docs/superpowers/specs/2026-11-01-ijcai-stale-state-tests-design.md`.

## Global Constraints

- Python 3.13 venv at `.venv` in the repo root (Etiq ships a CPython 3.13 binary; the machine's shell shim refuses `pip` without a project `.venv`). Always call `.venv/bin/python` / `.venv/bin/pip`.
- AppWorld train and dev splits only. Never load, open or inspect test_normal or test_challenge tasks.
- AppWorld-derived data never enters git: `appworld_root/`, `runs/` and `tests/fixtures/appworld/` are gitignored. Docs record field names and types only, never values.
- Reviewer model is the full ID `claude-haiku-5-5` at effort `medium` (the `haiku` alias serves Haiku 4.5).
- Reviewer isolation flags, exactly: `--tools "" --setting-sources "" --strict-mcp-config --system-prompt <prompt> --no-session-persistence --output-format json`, run from an empty directory.
- All randomness is seeded with `zlib.crc32(instance_id.encode("utf-8"))`. Never use `hash()` (per-process randomised).
- Scoring is deterministic. No LLM judge anywhere.
- No em dashes in any doc or prose file.
- Commit messages end with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | package metadata, pytest config |
| `.gitignore` | keeps venv and AppWorld-derived data out of git |
| `src/rdr/__init__.py` | package marker |
| `src/rdr/trace.py` | `Write`, `Call`, `Trace`: one run's ordered calls and record writes; JSON round trip |
| `src/rdr/truth.py` | `Truth`, `stale_records`, `make_truth`, `check_clean_control`, `choose_symptom` |
| `src/rdr/graph.py` | `Edge`, `Graph`, `build_graph`, `neighbourhood`, `random_subgraph`, `rewire_writes`, `rewire_one`, `render`, `strip_ignored` |
| `src/rdr/packager.py` | arms A to F text packages, rewired-edge package, leakage check |
| `src/rdr/runner.py` | isolated `claude -p` command, output parsing, resume, backoff |
| `src/rdr/scorer.py` | deterministic per-review scores |
| `src/rdr/freeze.py` | sha256 manifest write and verify |
| `tests/builders.py` | hand-built traces (gold, persistent, non-persistent, clean) |
| `tests/fake_claude.py` | fake `claude` executable for runner tests |
| `tests/test_*.py` | one test file per module |
| `spikes/appworld_discovery.py` | Gate 0: prints AppWorld structure (names and types only) |
| `spikes/etiq_appworld_spike.py` | Gate 0: does Etiq capture data flow of AppWorld agent code |
| `spikes/live_reviewer_smoke.py` | two real Haiku reviews on the hand-built fixture |
| `docs/gate0_findings.md` | answers to the Gate 0 questions; input to Plan 2 |

---

### Task 1: Scaffold, AppWorld install and discovery

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/rdr/__init__.py`, `spikes/appworld_discovery.py`, `docs/gate0_findings.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `.venv` (Python 3.13) with `rdr` installed editable plus pytest; `appworld_root/` with data; `docs/gate0_findings.md` answering Q1 to Q11 below; `appworld_root/rdr_gold/<task_id>.py` for one train task (code that, passed to `world.execute`, completes the task so `world.evaluate()` reports success).

- [ ] **Step 1: Write the scaffold files**

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "rdr"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`.gitignore`:
```
.venv/
__pycache__/
*.egg-info/
appworld_root/
runs/
tests/fixtures/appworld/
```

`src/rdr/__init__.py`:
```python
"""Repairs don't retract: stale-state diagnosis experiment."""
```

- [ ] **Step 2: Create the venv and install**

Run:
```bash
cd ~/projects/repairs-dont-retract
python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[dev]' appworld
mkdir -p appworld_root
.venv/bin/appworld install
.venv/bin/appworld download data --root appworld_root
.venv/bin/appworld download experiment-outputs --root appworld_root
.venv/bin/appworld verify tests --root appworld_root
.venv/bin/appworld verify tasks --root appworld_root
```
Expected: both verify commands pass. If `pip install appworld` or either verify fails on Python 3.13, record the exact error under Q9 in `docs/gate0_findings.md`, create `.venv311` with `python3.11 -m venv .venv311`, repeat the AppWorld lines there, and note that Etiq (3.13 only) cannot run in-process with AppWorld (Task 2 then records "value matching" without running).

- [ ] **Step 3: Write the discovery script**

`spikes/appworld_discovery.py`:
```python
"""Gate 0 discovery: print the AppWorld facts Plan 2 depends on.

Prints field NAMES and TYPES only. AppWorld data must not leave this machine in plain text.
"""
import json
from pathlib import Path

from appworld import AppWorld, load_task_ids, update_root

ROOT = Path(__file__).resolve().parents[1] / "appworld_root"
update_root(str(ROOT))


def shape(obj, depth=0):
    if depth > 3:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {k: shape(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shape(obj[0], depth + 1)] if obj else []
    return type(obj).__name__


train, dev = load_task_ids("train"), load_task_ids("dev")
print("Q1 train/dev task counts:", len(train), len(dev))
task_id = train[0]
print("task:", task_id)
gt_dir = ROOT / "data" / "tasks" / task_id / "ground_truth"
print("Q2 ground_truth files:", sorted(p.name for p in gt_dir.iterdir()) if gt_dir.exists() else "MISSING")
with AppWorld(task_id=task_id, experiment_name="rdr_discovery", ground_truth_mode="full") as world:
    gt = world.task.ground_truth
    print("Q2 ground_truth attributes:", [a for a in dir(gt) if not a.startswith("_")])
    calls = gt.api_calls
    print("Q2 api_calls container:", type(calls).__name__, "length", len(calls))
    first = calls[0]
    print("Q2 api_calls[0] shape:", json.dumps(shape(first)) if isinstance(first, (dict, list)) else type(first).__name__)
    print("Q2 compiled_solution_module type:", type(gt.compiled_solution_module).__name__)
    print("Q2 compiled_solution_module attributes:", [a for a in dir(gt.compiled_solution_module) if not a.startswith("_")])
    print("Q11 world attributes:", [a for a in dir(world) if not a.startswith("_")])
    print("Q11 shell namespace probe:", world.execute("print(sorted(k for k in globals() if not k.startswith('_')))"))
out = ROOT / "experiments" / "outputs" / "rdr_discovery" / task_id
print("output dir exists:", out.exists())
if out.exists():
    print("output files:", sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()))
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python spikes/appworld_discovery.py`
Expected: Q1 counts print; Q2 lists ground-truth files and attributes; Q11 lists world attributes and the shell's global names (expect `apis` and `requester` among them).

- [ ] **Step 5: Answer Q1 to Q11 and write `docs/gate0_findings.md`**

Investigate interactively in `.venv/bin/python` (names and types only in the doc). Each answer is a short factual paragraph plus the exact code used. Template to fill (copy verbatim, replace each `Answer:` line):

```markdown
# Gate 0 findings

Q1. Train and dev task counts.
Answer:

Q2. How to run the gold solution for a train task: which ground_truth file or attribute holds it, its entry point, and the exact code string that, passed to world.execute, completes the task so world.evaluate() reports success. Save that code for task <task_id> to appworld_root/rdr_gold/<task_id>.py.
Answer:

Q3. logs/api_calls.jsonl: field names and types of one line. Can each line be matched to app name, API name, arguments and response?
Answer:

Q4. dbs/<app>.jsonl: field names and types of one line. Does it give table, row id, and the row value before and after, or only after?
Answer:

Q5. Are api_calls.jsonl and dbs/*.jsonl rewritten after every world.execute call? (Execute two API calls in two separate world.execute calls and compare line counts after each.)
Answer:

Q6. Row-id stability: run the gold code; then run it again with one extra insert (for example a Venmo payment) before it. Do rows the gold code creates get different ids? If yes, Plan 2 must match created rows by content, not id.
Answer:

Q7. Volatile fields: run the gold code twice in fresh worlds. Which row fields differ between the two runs (timestamps, tokens)? This list becomes ignore_fields.
Answer:

Q8. Does replaying ground_truth.api_calls one call per world.execute reproduce a passing world.evaluate()? If yes, per-call write attribution comes from snapshots between calls.
Answer:

Q9. Python 3.13: did AppWorld install and both verify commands pass?
Answer:

Q10. Released GPT-4o outputs: how many train and dev runs have at least one failed requirement with label no_op_fail (collateral damage)? Path of the evaluation files used.
Answer:

Q11. Is an in-process apis object reachable from Python outside world.execute (for example an attribute of world or the shell namespace)? Give the exact expression or "no".
Answer:
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/rdr/__init__.py spikes/appworld_discovery.py docs/gate0_findings.md
git commit -m "Scaffold the rdr package and record Gate 0 AppWorld discovery findings" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Etiq spike

**Files:**
- Create: `spikes/etiq_appworld_spike.py`
- Modify: `docs/gate0_findings.md` (append Q12)

**Interfaces:**
- Consumes: `appworld_root/rdr_gold/<task_id>.py` and the Q11 answer from Task 1.
- Produces: Q12 decision in `docs/gate0_findings.md`: feeds edges come from `etiq` or from `value matching`.

- [ ] **Step 1: Install Etiq in the 3.13 venv**

Run: `.venv/bin/pip install etiq-copilot==2.3.0 && .venv/bin/python -c "from etiq_copilot.engine.implementations.scanner import DebuggerCodeScanner; print('ok')"`
Expected: `ok`. If the import fails, record the error under Q12 with decision `value matching` and skip to Step 5.

- [ ] **Step 2: Write the spike**

`spikes/etiq_appworld_spike.py`:
```python
"""Gate 0 spike: does Etiq capture data flow of AppWorld agent code?

Usage:
  .venv/bin/python spikes/etiq_appworld_spike.py TASK_ID GOLD_CODE_PATH OUT_JSON --mode exec
  .venv/bin/python spikes/etiq_appworld_spike.py TASK_ID GOLD_CODE_PATH OUT_JSON --mode inline --apis-expr "<Q11 expression>"

exec:   scanned source calls world.execute(gold_code); tests whether Etiq sees inside the shell.
inline: scanned source binds `apis` from the Q11 expression and runs gold_code as top-level statements.
"""
import argparse
import json
import textwrap
from pathlib import Path

from etiq_copilot.engine.implementations.scanner import DebuggerCodeScanner

ROOT = Path(__file__).resolve().parents[1] / "appworld_root"

parser = argparse.ArgumentParser()
parser.add_argument("task_id")
parser.add_argument("gold_code_path", type=Path)
parser.add_argument("out_json", type=Path)
parser.add_argument("--mode", choices=["exec", "inline"], required=True)
parser.add_argument("--apis-expr", default=None)
args = parser.parse_args()
gold_code = args.gold_code_path.read_text()

prelude = (
    "from appworld import AppWorld, update_root\n"
    f"update_root({str(ROOT)!r})\n"
    f"world = AppWorld(task_id={args.task_id!r}, experiment_name='rdr_etiq_spike')\n"
)
if args.mode == "exec":
    source = prelude + f"output = world.execute({gold_code!r})\nprint(output)\nworld.close()\n"
else:
    if not args.apis_expr:
        parser.error("--mode inline needs --apis-expr")
    source = prelude + f"apis = {args.apis_expr}\n" + textwrap.dedent(gold_code) + "\nworld.close()\n"

result = DebuggerCodeScanner().scan_code(code_str=source)
native = result.create_full_lineage_graph(graph_format="json")
args.out_json.parent.mkdir(parents=True, exist_ok=True)
args.out_json.write_text(native if isinstance(native, str) else json.dumps(native))
graph = json.loads(args.out_json.read_text())
labels = [str(o.get("label", "")) for o in graph.get("objects", [])]
print(json.dumps({
    "mode": args.mode,
    "objects": len(graph.get("objects", [])),
    "edges": len(graph.get("edges", [])),
    "objects_mentioning_apis": sum("apis." in label for label in labels),
}, indent=2))
```

- [ ] **Step 3: Run exec mode**

Run: `.venv/bin/python spikes/etiq_appworld_spike.py <task_id> appworld_root/rdr_gold/<task_id>.py runs/etiq_spike/exec.json --mode exec`
Expected: a JSON summary. `objects_mentioning_apis` of 0 means Etiq does not see inside the shell.

- [ ] **Step 4: Run inline mode (only if Q11 gave an expression)**

Run: `.venv/bin/python spikes/etiq_appworld_spike.py <task_id> appworld_root/rdr_gold/<task_id>.py runs/etiq_spike/inline.json --mode inline --apis-expr "<Q11 expression>"`

- [ ] **Step 5: Record Q12 and commit**

Append to `docs/gate0_findings.md`:
```markdown
Q12. Etiq on AppWorld. Decision rule: use Etiq for feeds edges if, in either mode, objects_mentioning_apis is at least the number of API calls in the gold code; otherwise use value matching.
Answer: (exec summary, inline summary, decision)
```
Then:
```bash
git add spikes/etiq_appworld_spike.py docs/gate0_findings.md
git commit -m "Add the Etiq-on-AppWorld spike and record the feeds-edge decision" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Trace model

**Files:**
- Create: `src/rdr/trace.py`, `tests/builders.py`, `tests/test_trace.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Write(record: str, before: dict | None, after: dict | None)`; `Call(index: int, app: str, api: str, args: dict, response: object, writes: list[Write])` with property `name -> "app.api"`; `Trace(task_id: str, instruction: str, final_message: str, calls: list[Call])` with `touched_records() -> list[str]`, `base_values() -> dict[str, dict | None]`, `final_values() -> dict[str, dict | None]`, `to_dict()`, `Trace.from_dict(d)`, `save(path)`, `Trace.load(path)`. Record labels are `"<app>.<table>#<row_id>"`. Test builders `gold_trace()`, `persistent_trace()`, `nonpersistent_trace()`, `clean_trace()`.

- [ ] **Step 1: Write the test builders**

`tests/builders.py`:
```python
"""Hand-built traces: pay ann@x.com 5 on Venmo, then settle Splitwise expense 77 with that payment.

gold:           login, pay ann (txn 201), settle 77 with 201.
persistent:     login, pay bob (txn 101, wrong), settle 77 with 101, refund 101, pay ann (txn 201).
                Expense 77 still points at the refunded payment: stale.
nonpersistent:  login, pay bob (txn 101, wrong), settle 77 with 101. No repair.
clean:          persistent plus re-settling 77 with 201. Matches gold.
"""
from rdr.trace import Call, Trace, Write

INSTRUCTION = "Pay ann@x.com 5 on Venmo and mark Splitwise expense 77 as settled with that payment."
EXP77_BASE = {"settled": False, "payment_ref": None}


def _login():
    return Call(0, "venmo", "login", {"username": "me"}, {"access_token": "tok-abc"})


def _pay(index, receiver, txn_id):
    row = {"receiver": receiver, "amount": 5, "status": "completed"}
    return Call(index, "venmo", "send_money", {"receiver": receiver, "amount": 5},
                {"transaction_id": txn_id}, [Write(f"venmo.transactions#{txn_id}", None, row)])


def _settle(index, before, ref):
    return Call(index, "splitwise", "settle_expense", {"expense_id": 77, "payment_ref": ref}, {"ok": True},
                [Write("splitwise.expenses#77", before, {"settled": True, "payment_ref": ref})])


def _refund(index, txn_id, receiver):
    before = {"receiver": receiver, "amount": 5, "status": "completed"}
    after = {"receiver": receiver, "amount": 5, "status": "refunded"}
    return Call(index, "venmo", "refund", {"transaction_id": txn_id}, {"status": "refunded"},
                [Write(f"venmo.transactions#{txn_id}", before, after)])


def gold_trace():
    return Trace("t1", INSTRUCTION, "Paid and settled.",
                 [_login(), _pay(1, "ann@x.com", 201), _settle(2, EXP77_BASE, 201)])


def persistent_trace():
    return Trace("t1", INSTRUCTION, "Paid and settled.",
                 [_login(), _pay(1, "bob@x.com", 101), _settle(2, EXP77_BASE, 101),
                  _refund(3, 101, "bob@x.com"), _pay(4, "ann@x.com", 201)])


def nonpersistent_trace():
    return Trace("t1", INSTRUCTION, "Paid and settled.",
                 [_login(), _pay(1, "bob@x.com", 101), _settle(2, EXP77_BASE, 101)])


def clean_trace():
    trace = persistent_trace()
    trace.calls.append(_settle(5, {"settled": True, "payment_ref": 101}, 201))
    return trace
```

- [ ] **Step 2: Write the failing tests**

`tests/test_trace.py`:
```python
from builders import persistent_trace

from rdr.trace import Trace


def test_touched_records_in_first_write_order():
    assert persistent_trace().touched_records() == [
        "venmo.transactions#101", "splitwise.expenses#77", "venmo.transactions#201"]


def test_base_values_take_first_before():
    assert persistent_trace().base_values() == {
        "venmo.transactions#101": None,
        "splitwise.expenses#77": {"settled": False, "payment_ref": None},
        "venmo.transactions#201": None,
    }


def test_final_values_take_last_after():
    final = persistent_trace().final_values()
    assert final["venmo.transactions#101"]["status"] == "refunded"
    assert final["splitwise.expenses#77"] == {"settled": True, "payment_ref": 101}


def test_call_name():
    assert persistent_trace().calls[1].name == "venmo.send_money"


def test_round_trip(tmp_path):
    trace = persistent_trace()
    path = tmp_path / "trace.json"
    trace.save(path)
    assert Trace.load(path) == trace
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_trace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rdr.trace'`.

- [ ] **Step 4: Implement**

`src/rdr/trace.py`:
```python
"""Trace of one run: ordered API calls and the record writes each call made."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Write:
    record: str
    before: dict | None
    after: dict | None


@dataclass
class Call:
    index: int
    app: str
    api: str
    args: dict
    response: object
    writes: list[Write] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.app}.{self.api}"


@dataclass
class Trace:
    task_id: str
    instruction: str
    final_message: str
    calls: list[Call]

    def touched_records(self) -> list[str]:
        seen: list[str] = []
        for call in self.calls:
            for write in call.writes:
                if write.record not in seen:
                    seen.append(write.record)
        return seen

    def base_values(self) -> dict[str, dict | None]:
        base: dict[str, dict | None] = {}
        for call in self.calls:
            for write in call.writes:
                base.setdefault(write.record, write.before)
        return base

    def final_values(self) -> dict[str, dict | None]:
        final: dict[str, dict | None] = {}
        for call in self.calls:
            for write in call.writes:
                final[write.record] = write.after
        return final

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Trace":
        calls = [
            Call(c["index"], c["app"], c["api"], c["args"], c["response"], [Write(**w) for w in c["writes"]])
            for c in data["calls"]
        ]
        return cls(data["task_id"], data["instruction"], data["final_message"], calls)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> "Trace":
        return cls.from_dict(json.loads(path.read_text()))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_trace.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/rdr/trace.py tests/builders.py tests/test_trace.py
git commit -m "Add the trace model with base and final record values" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Ground truth

**Files:**
- Create: `src/rdr/truth.py`, `tests/test_truth.py`

**Interfaces:**
- Consumes: `Trace` from Task 3.
- Produces: `Truth(instance_id, is_faulty, origin_index, stale, missing, symptom, decoy_index=None)` with `save(path)` / `Truth.load(path)`; `stale_records(faulty, gold, neutralised=frozenset(), ignore_fields=()) -> tuple[list[str], list[str]]` returning `(stale, missing)`; `choose_symptom(instance_id, stale, faulty) -> str`; `make_truth(instance_id, faulty, gold, origin_index, neutralised=frozenset(), ignore_fields=(), decoy_index=None) -> Truth`; `check_clean_control(control, gold, neutralised=frozenset(), ignore_fields=()) -> None`.

Definitions: a record differs if its final value in the faulty run differs from the gold run (an unwritten record keeps its base value). `neutralised` lists records the repair action is meant to fix (for example the refunded wrong payment); they never count. Differing records the faulty run touched are `stale` (nameable by the reviewer); differing records it never touched are `missing`.

- [ ] **Step 1: Write the failing tests**

`tests/test_truth.py`:
```python
import pytest
from builders import clean_trace, gold_trace, nonpersistent_trace, persistent_trace

from rdr.trace import Call, Trace, Write
from rdr.truth import Truth, check_clean_control, choose_symptom, make_truth, stale_records

REFUNDED = frozenset({"venmo.transactions#101"})


def test_persistent_fault_leaves_only_the_derived_record_stale():
    assert stale_records(persistent_trace(), gold_trace(), REFUNDED) == (["splitwise.expenses#77"], [])


def test_nonpersistent_fault_marks_wrong_record_and_missing_payment():
    stale, missing = stale_records(nonpersistent_trace(), gold_trace())
    assert stale == ["splitwise.expenses#77", "venmo.transactions#101"]
    assert missing == ["venmo.transactions#201"]


def test_clean_control_matches_gold():
    assert stale_records(clean_trace(), gold_trace(), REFUNDED) == ([], [])
    check_clean_control(clean_trace(), gold_trace(), REFUNDED)


def test_check_clean_control_rejects_a_faulty_run():
    with pytest.raises(ValueError, match="differs from gold"):
        check_clean_control(persistent_trace(), gold_trace(), REFUNDED)


def test_ignore_fields_hides_volatile_values():
    gold = gold_trace()
    faulty = gold_trace()
    gold.calls[2].writes[0].after = {**gold.calls[2].writes[0].after, "updated_at": "t1"}
    faulty.calls[2].writes[0].after = {**faulty.calls[2].writes[0].after, "updated_at": "t2"}
    assert stale_records(faulty, gold, ignore_fields=("updated_at",)) == ([], [])


def test_conflicting_base_values_raise():
    gold = gold_trace()
    faulty = Trace("t1", "x", "y", [Call(0, "splitwise", "settle_expense", {}, {}, [
        Write("splitwise.expenses#77", {"settled": True, "payment_ref": 9}, {"settled": True, "payment_ref": 201})])])
    with pytest.raises(ValueError, match="starting value"):
        stale_records(faulty, gold)


def test_make_truth_for_persistent_fault():
    truth = make_truth("i1", persistent_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED)
    assert truth == Truth("i1", True, 1, ["splitwise.expenses#77"], [], "splitwise.expenses#77", None)


def test_make_truth_for_clean_control_has_no_origin_and_a_seeded_symptom():
    truth = make_truth("i2", clean_trace(), gold_trace(), origin_index=1, neutralised=REFUNDED)
    assert truth.is_faulty is False and truth.origin_index is None and truth.stale == []
    assert truth.symptom in clean_trace().touched_records()
    assert truth.symptom == make_truth("i2", clean_trace(), gold_trace(), 1, REFUNDED).symptom


def test_make_truth_requires_origin_for_faulty_runs():
    with pytest.raises(ValueError, match="origin"):
        make_truth("i3", persistent_trace(), gold_trace(), origin_index=None, neutralised=REFUNDED)


def test_choose_symptom_prefers_first_stale_record():
    assert choose_symptom("i4", ["b#2", "a#1"], persistent_trace()) == "a#1"


def test_truth_round_trip(tmp_path):
    truth = make_truth("i1", persistent_trace(), gold_trace(), 1, REFUNDED, decoy_index=4)
    path = tmp_path / "truth.json"
    truth.save(path)
    assert Truth.load(path) == truth
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_truth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rdr.truth'`.

- [ ] **Step 3: Implement**

`src/rdr/truth.py`:
```python
"""Ground truth for one instance, derived mechanically from the faulty run and the gold run."""
from __future__ import annotations

import json
import random
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path

from rdr.trace import Trace


@dataclass
class Truth:
    instance_id: str
    is_faulty: bool
    origin_index: int | None
    stale: list[str]
    missing: list[str]
    symptom: str
    decoy_index: int | None = None

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> "Truth":
        return cls(**json.loads(path.read_text()))


def _strip(row: dict | None, ignore_fields) -> dict | None:
    if row is None:
        return None
    return {k: v for k, v in row.items() if k not in ignore_fields}


def stale_records(faulty: Trace, gold: Trace, neutralised=frozenset(), ignore_fields=()) -> tuple[list[str], list[str]]:
    base = dict(gold.base_values())
    for record, before in faulty.base_values().items():
        if record in base and _strip(base[record], ignore_fields) != _strip(before, ignore_fields):
            raise ValueError(f"runs disagree on the starting value of {record}")
        base.setdefault(record, before)
    faulty_final, gold_final = faulty.final_values(), gold.final_values()
    touched = set(faulty.touched_records())
    stale: list[str] = []
    missing: list[str] = []
    for record in sorted(set(faulty_final) | set(gold_final)):
        if record in neutralised:
            continue
        f_value = _strip(faulty_final.get(record, base.get(record)), ignore_fields)
        g_value = _strip(gold_final.get(record, base.get(record)), ignore_fields)
        if f_value != g_value:
            (stale if record in touched else missing).append(record)
    return stale, missing


def choose_symptom(instance_id: str, stale: list[str], faulty: Trace) -> str:
    if stale:
        return sorted(stale)[0]
    rng = random.Random(zlib.crc32(instance_id.encode("utf-8")))
    return rng.choice(sorted(faulty.touched_records()))


def make_truth(instance_id: str, faulty: Trace, gold: Trace, origin_index: int | None,
               neutralised=frozenset(), ignore_fields=(), decoy_index: int | None = None) -> Truth:
    stale, missing = stale_records(faulty, gold, neutralised, ignore_fields)
    is_faulty = bool(stale or missing)
    if is_faulty and origin_index is None:
        raise ValueError("a faulty instance needs an origin index")
    if is_faulty and not stale:
        raise ValueError("faulty instance has no stale record the reviewer can name")
    return Truth(instance_id, is_faulty, origin_index if is_faulty else None, stale, missing,
                 choose_symptom(instance_id, stale, faulty), decoy_index)


def check_clean_control(control: Trace, gold: Trace, neutralised=frozenset(), ignore_fields=()) -> None:
    stale, missing = stale_records(control, gold, neutralised, ignore_fields)
    if stale or missing:
        raise ValueError(f"clean control differs from gold: stale={stale} missing={missing}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_truth.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rdr/truth.py tests/test_truth.py
git commit -m "Add mechanical ground truth: stale and missing records against the gold run" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Provenance graph

**Files:**
- Create: `src/rdr/graph.py`, `tests/test_graph.py`

**Interfaces:**
- Consumes: `Trace` from Task 3.
- Produces: `Edge(src: str, dst: str, kind: str)` with kind in `writes`, `reads`, `feeds`; `Graph(call_nodes: dict[str, str], record_nodes: list[str], edges: list[Edge])`; `call_node(i) -> "call:i"`; `rec_node(label) -> "rec:label"`; `build_graph(trace) -> Graph`; `edge_counts(graph) -> dict[str, int]`; `neighbourhood(graph, center, hops) -> Graph`; `random_subgraph(graph, counts, seed) -> Graph`; `rewire_writes(graph, seed) -> Graph`; `rewire_one(graph, record_node, decoy_node) -> Graph`; `render(graph) -> str`; `strip_ignored(obj)`; constant `IGNORED_KEYS`.

Edge rules: `writes` from a call to each record it wrote. `reads` from a record to a call whose arguments contain the record's row id, when that call does not write the record. `feeds` from an earlier call to a later call when a value in the earlier response appears in the later arguments. Values under `access_token` or `password` are ignored; strings shorter than 3 characters and numbers shorter than 2 digits never match. If Task 2 decided `etiq`, Plan 2 replaces the `feeds` rule; the other rules stay.

- [ ] **Step 1: Write the failing tests**

`tests/test_graph.py`:
```python
from builders import persistent_trace

from rdr.graph import (Edge, build_graph, call_node, edge_counts, neighbourhood, random_subgraph, rec_node,
                       render, rewire_one, rewire_writes, strip_ignored)

EXP77 = rec_node("splitwise.expenses#77")
TXN101 = rec_node("venmo.transactions#101")


def test_edges_of_persistent_trace():
    g = build_graph(persistent_trace())
    assert set(g.edges) == {
        Edge("call:1", TXN101, "writes"),
        Edge("call:2", EXP77, "writes"),
        Edge("call:3", TXN101, "writes"),
        Edge("call:4", rec_node("venmo.transactions#201"), "writes"),
        Edge(TXN101, "call:2", "reads"),
        Edge("call:1", "call:2", "feeds"),
        Edge("call:1", "call:3", "feeds"),
    }


def test_call_labels_hide_tokens():
    g = build_graph(persistent_trace())
    assert g.call_nodes["call:1"] == "1 venmo.send_money(amount=5, receiver='bob@x.com')"
    assert "tok-abc" not in render(g)


def test_neighbourhood_two_hops_from_symptom():
    d = neighbourhood(build_graph(persistent_trace()), EXP77, 2)
    assert edge_counts(d) == {"writes": 2, "reads": 1, "feeds": 1}
    assert call_node(3) not in d.call_nodes


def test_random_subgraph_matches_counts_and_is_deterministic():
    g = build_graph(persistent_trace())
    counts = {"writes": 2, "reads": 1, "feeds": 1}
    first = random_subgraph(g, counts, seed=7)
    assert edge_counts(first) == counts
    assert set(first.edges) <= set(g.edges)
    assert first.edges == random_subgraph(g, counts, seed=7).edges


def test_rewire_writes_changes_structure_deterministically():
    g = build_graph(persistent_trace())
    fake = rewire_writes(g, seed=3)
    original_writes = {e for e in g.edges if e.kind == "writes"}
    fake_writes = {e for e in fake.edges if e.kind == "writes"}
    assert fake_writes != original_writes
    assert {e for e in fake.edges if e.kind != "writes"} == {e for e in g.edges if e.kind != "writes"}
    assert fake.edges == rewire_writes(g, seed=3).edges


def test_rewire_one_points_the_record_at_the_decoy():
    fake = rewire_one(build_graph(persistent_trace()), EXP77, call_node(4))
    assert Edge("call:4", EXP77, "writes") in fake.edges
    assert Edge("call:2", EXP77, "writes") not in fake.edges


def test_render_orders_calls_numerically():
    text = render(build_graph(persistent_trace()))
    assert text.index("call:2 =") < text.index("call:3 =")
    assert "call:1 -writes-> rec:venmo.transactions#101" in text


def test_strip_ignored_is_recursive():
    assert strip_ignored({"a": 1, "access_token": "x", "b": [{"password": "p", "c": 2}]}) == {"a": 1, "b": [{"c": 2}]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rdr.graph'`.

- [ ] **Step 3: Implement**

`src/rdr/graph.py`:
```python
"""Provenance graph built from a Trace: call nodes, record nodes, typed edges."""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from rdr.trace import Trace

IGNORED_KEYS = frozenset({"access_token", "password"})


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str


@dataclass
class Graph:
    call_nodes: dict[str, str]
    record_nodes: list[str]
    edges: list[Edge] = field(default_factory=list)


def call_node(index: int) -> str:
    return f"call:{index}"


def rec_node(record: str) -> str:
    return f"rec:{record}"


def strip_ignored(obj):
    if isinstance(obj, dict):
        return {k: strip_ignored(v) for k, v in obj.items() if k not in IGNORED_KEYS}
    if isinstance(obj, list):
        return [strip_ignored(v) for v in obj]
    return obj


def _scalars(obj) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key not in IGNORED_KEYS:
                out |= _scalars(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            out |= _scalars(value)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, str):
        if len(obj) >= 3:
            out.add(obj)
    elif isinstance(obj, (int, float)):
        text = str(obj)
        if len(text) >= 2:
            out.add(text)
    return out


def _row_id(record: str) -> str:
    return record.split("#", 1)[1]


def _fmt_args(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in sorted(args.items()) if k not in IGNORED_KEYS)


def _dedupe(edges: list[Edge]) -> list[Edge]:
    seen: set[Edge] = set()
    out: list[Edge] = []
    for edge in edges:
        if edge not in seen:
            seen.add(edge)
            out.append(edge)
    return out


def build_graph(trace: Trace) -> Graph:
    call_nodes = {call_node(c.index): f"{c.index} {c.name}({_fmt_args(c.args)})" for c in trace.calls}
    records = trace.touched_records()
    edges: list[Edge] = []
    for call in trace.calls:
        for write in call.writes:
            edges.append(Edge(call_node(call.index), rec_node(write.record), "writes"))
    for call in trace.calls:
        arg_values = _scalars(call.args)
        written = {w.record for w in call.writes}
        for record in records:
            if record not in written and _row_id(record) in arg_values:
                edges.append(Edge(rec_node(record), call_node(call.index), "reads"))
    for position, later in enumerate(trace.calls):
        later_args = _scalars(later.args)
        for earlier in trace.calls[:position]:
            if _scalars(earlier.response) & later_args:
                edges.append(Edge(call_node(earlier.index), call_node(later.index), "feeds"))
    return Graph(call_nodes, [rec_node(r) for r in records], _dedupe(edges))


def edge_counts(graph: Graph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in graph.edges:
        counts[edge.kind] = counts.get(edge.kind, 0) + 1
    return counts


def _restrict(graph: Graph, keep: set[str], edges: list[Edge] | None = None) -> Graph:
    chosen = edges if edges is not None else [e for e in graph.edges if e.src in keep and e.dst in keep]
    return Graph({k: v for k, v in graph.call_nodes.items() if k in keep},
                 [r for r in graph.record_nodes if r in keep], chosen)


def neighbourhood(graph: Graph, center: str, hops: int) -> Graph:
    adjacent: dict[str, set[str]] = {}
    for edge in graph.edges:
        adjacent.setdefault(edge.src, set()).add(edge.dst)
        adjacent.setdefault(edge.dst, set()).add(edge.src)
    keep = {center}
    frontier = deque([(center, 0)])
    while frontier:
        node, distance = frontier.popleft()
        if distance == hops:
            continue
        for neighbour in adjacent.get(node, ()):
            if neighbour not in keep:
                keep.add(neighbour)
                frontier.append((neighbour, distance + 1))
    return _restrict(graph, keep)


def random_subgraph(graph: Graph, counts: dict[str, int], seed: int) -> Graph:
    rng = random.Random(seed)
    chosen: set[Edge] = set()
    for kind in sorted(counts):
        pool = [e for e in graph.edges if e.kind == kind]
        chosen |= set(rng.sample(pool, min(counts[kind], len(pool))))
    keep = {e.src for e in chosen} | {e.dst for e in chosen}
    return _restrict(graph, keep, [e for e in graph.edges if e in chosen])


def rewire_writes(graph: Graph, seed: int) -> Graph:
    rng = random.Random(seed)
    writes = [e for e in graph.edges if e.kind == "writes"]
    sources = [e.src for e in writes]
    permuted = sources[:]
    for _ in range(100):
        rng.shuffle(permuted)
        if all(new != old for new, old in zip(permuted, sources)):
            break
    replacements = iter(Edge(src, e.dst, "writes") for src, e in zip(permuted, writes))
    edges = [next(replacements) if e.kind == "writes" else e for e in graph.edges]
    return Graph(dict(graph.call_nodes), list(graph.record_nodes), _dedupe(edges))


def rewire_one(graph: Graph, record_node: str, decoy_node: str) -> Graph:
    edges = [Edge(decoy_node, e.dst, "writes") if e.kind == "writes" and e.dst == record_node else e
             for e in graph.edges]
    return Graph(dict(graph.call_nodes), list(graph.record_nodes), _dedupe(edges))


def _node_key(node: str) -> tuple:
    kind, _, rest = node.partition(":")
    return (0, int(rest), "") if kind == "call" else (1, 0, rest)


def render(graph: Graph) -> str:
    lines = ["NODES"]
    lines += [f"{n} = {graph.call_nodes[n]}" for n in sorted(graph.call_nodes, key=_node_key)]
    lines += sorted(graph.record_nodes)
    lines.append("EDGES")
    lines += [f"{e.src} -{e.kind}-> {e.dst}"
              for e in sorted(graph.edges, key=lambda e: (_node_key(e.src), e.kind, _node_key(e.dst)))]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rdr/graph.py tests/test_graph.py
git commit -m "Add the provenance graph with neighbourhood, random and rewired variants" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Evidence packager

**Files:**
- Create: `src/rdr/packager.py`, `tests/test_packager.py`

**Interfaces:**
- Consumes: `Trace` (Task 3); `build_graph`, `edge_counts`, `neighbourhood`, `random_subgraph`, `rewire_writes`, `rewire_one`, `render`, `rec_node`, `call_node`, `strip_ignored` (Task 5).
- Produces: `ARMS = ("A","B","C","D","E","F")`; `build_package(arm, trace, symptom, instance_id) -> str`; `build_rewired_package(trace, symptom, instance_id, decoy_index) -> str`; `check_leakage(text, forbidden=FORBIDDEN)`; `LeakageError`; `seed_for(instance_id) -> int`.

Arm contents (all arms share the header: task, final message, user report naming the symptom, final state of changed records, calls made with index and API only): A adds nothing; B adds the action log (arguments and responses); C adds the full graph; D the graph within 2 hops of the symptom; E a random slice with D's edge counts per kind; F the graph with write edges rewired.

- [ ] **Step 1: Write the failing tests**

`tests/test_packager.py`:
```python
import pytest
from builders import persistent_trace

from rdr.packager import ARMS, LeakageError, build_package, build_rewired_package, check_leakage

SYMPTOM = "splitwise.expenses#77"


def _pkg(arm):
    return build_package(arm, persistent_trace(), SYMPTOM, "i1")


def test_every_arm_has_the_common_header():
    for arm in ARMS:
        text = _pkg(arm)
        assert "A user reports that record splitwise.expenses#77 looks wrong." in text
        assert "CALLS MADE (index and API only)" in text
        assert "\n1 venmo.send_money" in text


def test_arm_a_has_no_log_and_no_graph():
    text = _pkg("A")
    assert "ACTION LOG" not in text and "EDGES" not in text


def test_arm_b_has_the_log_without_tokens():
    text = _pkg("B")
    assert "ACTION LOG" in text and '"transaction_id": 101' in text
    assert "tok-abc" not in text and "EDGES" not in text


def test_arm_c_has_the_full_graph():
    assert _pkg("C").count("-writes->") == 4


def test_arm_d_is_the_symptom_neighbourhood():
    text = _pkg("D")
    assert text.count("-writes->") == 2 and text.count("-reads->") == 1 and text.count("-feeds->") == 1


def test_arm_e_matches_d_edge_counts():
    text = _pkg("E")
    assert text.count("-writes->") == 2 and text.count("-reads->") == 1 and text.count("-feeds->") == 1


def test_arm_f_differs_from_c():
    assert _pkg("F") != _pkg("C")


def test_packages_are_deterministic():
    assert [_pkg(a) for a in ARMS] == [_pkg(a) for a in ARMS]


def test_rewired_package_points_symptom_at_decoy():
    text = build_rewired_package(persistent_trace(), SYMPTOM, "i1", decoy_index=4)
    assert "call:4 -writes-> rec:splitwise.expenses#77" in text
    assert "call:2 -writes-> rec:splitwise.expenses#77" not in text


def test_leakage_is_rejected():
    trace = persistent_trace()
    trace.instruction = "This run has an injected fault."
    with pytest.raises(LeakageError):
        build_package("A", trace, SYMPTOM, "i1")


def test_check_leakage_is_case_insensitive():
    with pytest.raises(LeakageError):
        check_leakage("GOLD solution")


def test_unknown_arm_raises():
    with pytest.raises(ValueError):
        build_package("Z", persistent_trace(), SYMPTOM, "i1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_packager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rdr.packager'`.

- [ ] **Step 3: Implement**

`src/rdr/packager.py`:
```python
"""Evidence packages for the six reviewer arms and the rewired-edge test."""
from __future__ import annotations

import json
import zlib

from rdr.graph import (build_graph, call_node, edge_counts, neighbourhood, random_subgraph, rec_node, render,
                       rewire_one, rewire_writes, strip_ignored)
from rdr.trace import Trace

ARMS = ("A", "B", "C", "D", "E", "F")
FORBIDDEN = ("inject", "fault", "stale", "repair", "decoy", "gold", "truth")
D_HOPS = 2


class LeakageError(ValueError):
    pass


def seed_for(instance_id: str) -> int:
    return zlib.crc32(instance_id.encode("utf-8"))


def check_leakage(text: str, forbidden=FORBIDDEN) -> None:
    lowered = text.lower()
    for word in forbidden:
        if word in lowered:
            raise LeakageError(word)


def _header(trace: Trace, symptom: str) -> list[str]:
    final = trace.final_values()
    lines = ["TASK", trace.instruction, "",
             "AGENT FINAL MESSAGE", trace.final_message, "",
             "USER REPORT", f"A user reports that record {symptom} looks wrong.", "",
             "FINAL STATE OF RECORDS THE AGENT CHANGED"]
    lines += [f"{record} = {json.dumps(final[record], sort_keys=True)}" for record in sorted(final)]
    lines += ["", "CALLS MADE (index and API only)"]
    lines += [f"{call.index} {call.name}" for call in trace.calls]
    return lines


def _action_log(trace: Trace) -> list[str]:
    lines = ["ACTION LOG"]
    for call in trace.calls:
        args = json.dumps(strip_ignored(call.args), sort_keys=True)
        response = json.dumps(strip_ignored(call.response), sort_keys=True, default=str)
        lines.append(f"[{call.index}] {call.name}({args}) -> {response}")
    return lines


def build_package(arm: str, trace: Trace, symptom: str, instance_id: str) -> str:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    graph = build_graph(trace)
    seed = seed_for(instance_id)
    lines = _header(trace, symptom)
    if arm == "B":
        lines += ["", *_action_log(trace)]
    elif arm == "C":
        lines += ["", "PROVENANCE GRAPH", render(graph)]
    elif arm == "D":
        lines += ["", "PROVENANCE GRAPH", render(neighbourhood(graph, rec_node(symptom), D_HOPS))]
    elif arm == "E":
        counts = edge_counts(neighbourhood(graph, rec_node(symptom), D_HOPS))
        lines += ["", "PROVENANCE GRAPH", render(random_subgraph(graph, counts, seed))]
    elif arm == "F":
        lines += ["", "PROVENANCE GRAPH", render(rewire_writes(graph, seed))]
    text = "\n".join(lines)
    check_leakage(text)
    return text


def build_rewired_package(trace: Trace, symptom: str, instance_id: str, decoy_index: int) -> str:
    graph = rewire_one(build_graph(trace), rec_node(symptom), call_node(decoy_index))
    text = "\n".join([*_header(trace, symptom), "", "PROVENANCE GRAPH", render(graph)])
    check_leakage(text)
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_packager.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rdr/packager.py tests/test_packager.py
git commit -m "Add evidence packages for arms A to F with a leakage check" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Isolated reviewer runner

**Files:**
- Create: `src/rdr/runner.py`, `tests/fake_claude.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: package text from Task 6.
- Produces: `ANSWER_SCHEMA`; `SYSTEM_PROMPT`; `ReviewError`; `build_command(model, effort, claude_cmd=("claude",)) -> list[str]`; `parse_output(stdout) -> dict` with keys `answer`, `served_models`, `usage`, `is_error`; `review(package_text, out_path, model, effort, workdir, claude_cmd=("claude",), timeout=900) -> dict` (record plus `model_requested`, `effort`); `review_with_backoff(..., waits=(60, 300, 1800), sleep_fn=time.sleep, **kwargs) -> dict`. Answer keys: `anything_wrong: bool`, `origin_call: int | None`, `still_wrong_records: list[str]`.

The package goes to the CLI on stdin. `workdir` must exist and be empty (the reviewer has no tools, and an empty cwd also keeps project files out of reach). Output JSON is the last non-empty stdout line (a warning line may precede it). The answer is `structured_output` when present, otherwise the first JSON object inside `result`.

- [ ] **Step 1: Write the fake CLI**

`tests/fake_claude.py`:
```python
"""Stand-in for `claude -p` in tests. FAKE_MODE: result | structured | fenced | fail. FAKE_SERVED overrides the served model."""
import json
import os
import sys

args = sys.argv[1:]
prompt = sys.stdin.read()
assert "-p" in args
assert args[args.index("--tools") + 1] == ""
assert args[args.index("--setting-sources") + 1] == ""
assert "--strict-mcp-config" in args and "--no-session-persistence" in args
model = args[args.index("--model") + 1]
mode = os.environ.get("FAKE_MODE", "result")
if mode == "fail":
    print("Claude usage limit reached", file=sys.stderr)
    sys.exit(1)
answer = {"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["splitwise.expenses#77"]}
envelope = {"usage": {"input_tokens": len(prompt)}, "modelUsage": {os.environ.get("FAKE_SERVED", model): {}},
            "is_error": False}
if mode == "structured":
    envelope.update(structured_output=answer, result="")
elif mode == "fenced":
    envelope["result"] = "```json\n" + json.dumps(answer) + "\n```"
else:
    envelope["result"] = json.dumps(answer)
print("[claude-code:unrecognized_model] {}")
print(json.dumps(envelope))
```

- [ ] **Step 2: Write the failing tests**

`tests/test_runner.py`:
```python
import sys
from pathlib import Path

import pytest

from rdr.runner import ReviewError, build_command, review, review_with_backoff

FAKE = (sys.executable, str(Path(__file__).with_name("fake_claude.py")))
MODEL = "claude-haiku-5-5"
EXPECTED = {"anything_wrong": True, "origin_call": 1, "still_wrong_records": ["splitwise.expenses#77"]}


def _review(tmp_path, name="r.json"):
    workdir = tmp_path / "empty"
    workdir.mkdir(exist_ok=True)
    return review("PACKAGE", tmp_path / "out" / name, MODEL, "medium", workdir, claude_cmd=FAKE)


def test_command_has_isolation_flags():
    cmd = build_command(MODEL, "medium")
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == MODEL and cmd[cmd.index("--effort") + 1] == "medium"
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--system-prompt", "--json-schema"):
        assert flag in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"


@pytest.mark.parametrize("mode", ["result", "structured", "fenced"])
def test_review_parses_each_output_shape(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("FAKE_MODE", mode)
    record = _review(tmp_path)
    assert record["answer"] == EXPECTED
    assert record["model_requested"] == MODEL and record["effort"] == "medium"
    assert MODEL in record["served_models"]


def test_review_resumes_from_saved_output(tmp_path, monkeypatch):
    first = _review(tmp_path)
    monkeypatch.setenv("FAKE_MODE", "fail")
    assert _review(tmp_path) == first


def test_wrong_served_model_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SERVED", "claude-haiku-4-5-20251001")
    with pytest.raises(ReviewError, match="served"):
        _review(tmp_path)


def test_nonempty_workdir_raises(tmp_path):
    workdir = tmp_path / "busy"
    workdir.mkdir()
    (workdir / "answers.json").write_text("{}")
    with pytest.raises(ReviewError, match="empty"):
        review("PACKAGE", tmp_path / "out.json", MODEL, "medium", workdir, claude_cmd=FAKE)


def test_backoff_retries_on_limit_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    waits = []
    workdir = tmp_path / "empty"
    workdir.mkdir()
    with pytest.raises(ReviewError, match="limit"):
        review_with_backoff("PACKAGE", tmp_path / "out.json", MODEL, "medium", workdir,
                            claude_cmd=FAKE, waits=(1, 2), sleep_fn=waits.append)
    assert waits == [1, 2]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rdr.runner'`.

- [ ] **Step 4: Implement**

`src/rdr/runner.py`:
```python
"""Isolated `claude -p` reviewer: one fresh session per package, pinned model and effort."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "anything_wrong": {"type": "boolean"},
        "origin_call": {"type": ["integer", "null"]},
        "still_wrong_records": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["anything_wrong", "origin_call", "still_wrong_records"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You review the record of an automated assistant's work in a user's apps. "
    "Use only the evidence in the message. Answer three questions. "
    "anything_wrong: is any record in the final state wrong for the task? "
    "origin_call: the index of the call that started the problem, or null if nothing is wrong. "
    "still_wrong_records: every record label, written exactly as in the evidence, that is still wrong. "
    "Reply with JSON matching the schema and nothing else."
)


class ReviewError(RuntimeError):
    pass


def build_command(model: str, effort: str, claude_cmd=("claude",)) -> list[str]:
    return [*claude_cmd, "-p",
            "--model", model,
            "--effort", effort,
            "--tools", "",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--system-prompt", SYSTEM_PROMPT,
            "--json-schema", json.dumps(ANSWER_SCHEMA, sort_keys=True),
            "--no-session-persistence",
            "--output-format", "json"]


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ReviewError(f"no JSON object in result: {text[:200]!r}")
    return json.loads(text[start:end + 1])


def parse_output(stdout: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ReviewError("empty output")
    envelope = json.loads(lines[-1])
    answer = envelope.get("structured_output") or _extract_json(envelope.get("result") or "")
    return {
        "answer": answer,
        "served_models": sorted((envelope.get("modelUsage") or {}).keys()),
        "usage": envelope.get("usage") or {},
        "is_error": bool(envelope.get("is_error")),
    }


def review(package_text: str, out_path: Path, model: str, effort: str, workdir: Path,
           claude_cmd=("claude",), timeout: int = 900) -> dict:
    if out_path.exists():
        return json.loads(out_path.read_text())
    if any(workdir.iterdir()):
        raise ReviewError(f"workdir must be empty: {workdir}")
    proc = subprocess.run(build_command(model, effort, claude_cmd), input=package_text,
                          capture_output=True, text=True, cwd=workdir, timeout=timeout)
    if proc.returncode != 0:
        raise ReviewError((proc.stderr or proc.stdout)[-2000:])
    record = parse_output(proc.stdout)
    if record["is_error"]:
        raise ReviewError(f"reviewer reported an error: {proc.stdout[-500:]}")
    if model not in record["served_models"]:
        raise ReviewError(f"requested {model}, served {record['served_models']}")
    record.update(model_requested=model, effort=effort)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def review_with_backoff(*args, waits=(60, 300, 1800), sleep_fn=time.sleep, **kwargs) -> dict:
    for wait in (*waits, None):
        try:
            return review(*args, **kwargs)
        except ReviewError as err:
            if wait is None or "limit" not in str(err).lower():
                raise
            sleep_fn(wait)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_runner.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add src/rdr/runner.py tests/fake_claude.py tests/test_runner.py
git commit -m "Add the isolated claude -p reviewer runner with resume and backoff" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Scorer

**Files:**
- Create: `src/rdr/scorer.py`, `tests/test_scorer.py`

**Interfaces:**
- Consumes: `Truth` (Task 4); answer dict (Task 7).
- Produces: `score(answer, truth) -> dict` with keys `instance_id`, `detection_correct` (bool), `origin_hit` (bool, None for clean), `stale_precision` and `stale_recall` (float, None when undefined or clean), `false_stale_count` (int for clean, else None), `followed_decoy` (bool, None without a decoy). The symptom record is excluded from both claimed and actual stale sets, since every arm was told about it.

- [ ] **Step 1: Write the failing tests**

`tests/test_scorer.py`:
```python
from rdr.scorer import score
from rdr.truth import Truth

FAULTY = Truth("i1", True, 1, ["splitwise.expenses#77", "todo.items#5"], [], "splitwise.expenses#77")
CLEAN = Truth("i2", False, None, [], [], "venmo.transactions#201")


def test_perfect_answer():
    s = score({"anything_wrong": True, "origin_call": 1,
               "still_wrong_records": ["splitwise.expenses#77", "todo.items#5"]}, FAULTY)
    assert s == {"instance_id": "i1", "detection_correct": True, "origin_hit": True, "stale_precision": 1.0,
                 "stale_recall": 1.0, "false_stale_count": None, "followed_decoy": None}


def test_wrong_origin_and_extra_record():
    s = score({"anything_wrong": True, "origin_call": 3,
               "still_wrong_records": ["todo.items#5", "venmo.transactions#201"]}, FAULTY)
    assert s["origin_hit"] is False and s["stale_precision"] == 0.5 and s["stale_recall"] == 1.0


def test_no_claims_gives_undefined_precision_and_zero_recall():
    s = score({"anything_wrong": True, "origin_call": 1, "still_wrong_records": []}, FAULTY)
    assert s["stale_precision"] is None and s["stale_recall"] == 0.0


def test_clean_control_correctly_passed():
    s = score({"anything_wrong": False, "origin_call": None, "still_wrong_records": []}, CLEAN)
    assert s["detection_correct"] is True and s["origin_hit"] is None and s["false_stale_count"] == 0


def test_clean_control_false_alarm_excludes_symptom():
    s = score({"anything_wrong": True, "origin_call": 2,
               "still_wrong_records": ["venmo.transactions#201", "splitwise.expenses#77"]}, CLEAN)
    assert s["detection_correct"] is False and s["false_stale_count"] == 1


def test_decoy_follow():
    truth = Truth("i3", True, 1, ["splitwise.expenses#77"], [], "splitwise.expenses#77", decoy_index=4)
    assert score({"anything_wrong": True, "origin_call": 4, "still_wrong_records": []}, truth)["followed_decoy"] is True
    assert score({"anything_wrong": True, "origin_call": 1, "still_wrong_records": []}, truth)["followed_decoy"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rdr.scorer'`.

- [ ] **Step 3: Implement**

`src/rdr/scorer.py`:
```python
"""Deterministic per-review scores. No LLM judge."""
from __future__ import annotations

from rdr.truth import Truth


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def score(answer: dict, truth: Truth) -> dict:
    claimed = set(answer.get("still_wrong_records") or []) - {truth.symptom}
    actual = set(truth.stale) - {truth.symptom}
    hits = len(claimed & actual)
    origin = answer.get("origin_call")
    return {
        "instance_id": truth.instance_id,
        "detection_correct": bool(answer.get("anything_wrong")) == truth.is_faulty,
        "origin_hit": (origin == truth.origin_index) if truth.is_faulty else None,
        "stale_precision": _ratio(hits, len(claimed)) if truth.is_faulty else None,
        "stale_recall": _ratio(hits, len(actual)) if truth.is_faulty else None,
        "false_stale_count": None if truth.is_faulty else len(claimed),
        "followed_decoy": (origin == truth.decoy_index) if truth.decoy_index is not None else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rdr/scorer.py tests/test_scorer.py
git commit -m "Add the deterministic scorer for detection, origin, stale records and decoys" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Freeze

**Files:**
- Create: `src/rdr/freeze.py`, `tests/test_freeze.py`

**Interfaces:**
- Consumes: any directory of files.
- Produces: `MANIFEST_NAME = "MANIFEST.sha256.json"`; `build_manifest(root) -> dict[str, str]`; `write_manifest(root) -> Path`; `verify_manifest(root) -> list[str]` with entries `changed: <path>`, `missing: <path>`, `extra: <path>`; empty list means intact.

- [ ] **Step 1: Write the failing tests**

`tests/test_freeze.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_freeze.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rdr.freeze'`.

- [ ] **Step 3: Implement**

`src/rdr/freeze.py`:
```python
"""sha256 manifest so hypotheses, instances and packages are frozen before any reviewer call."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_NAME = "MANIFEST.sha256.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _sha256(p)
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != MANIFEST_NAME}


def write_manifest(root: Path) -> Path:
    out = root / MANIFEST_NAME
    out.write_text(json.dumps(build_manifest(root), indent=2, sort_keys=True))
    return out


def verify_manifest(root: Path) -> list[str]:
    recorded = json.loads((root / MANIFEST_NAME).read_text())
    current = build_manifest(root)
    problems = [f"changed: {k}" for k in sorted(recorded) if k in current and current[k] != recorded[k]]
    problems += [f"missing: {k}" for k in sorted(recorded) if k not in current]
    problems += [f"extra: {k}" for k in sorted(current) if k not in recorded]
    return problems
```

- [ ] **Step 4: Run tests to verify they pass, then the whole suite**

Run: `.venv/bin/python -m pytest -v`
Expected: all tests pass (5 + 11 + 8 + 12 + 8 + 6 + 2 = 52).

- [ ] **Step 5: Commit**

```bash
git add src/rdr/freeze.py tests/test_freeze.py
git commit -m "Add the sha256 freeze manifest" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Live reviewer smoke test (2 real Haiku calls)

**Files:**
- Create: `spikes/live_reviewer_smoke.py`
- Modify: `docs/gate0_findings.md` (append Q13)

**Interfaces:**
- Consumes: `build_package` (Task 6), `review` (Task 7), `tests/builders.py` (Task 3).
- Produces: Q13 in `docs/gate0_findings.md`: does the real CLI accept stdin and `--json-schema`, which output field holds the answer, served models, input tokens per call.

- [ ] **Step 1: Write the script**

`spikes/live_reviewer_smoke.py`:
```python
"""Two real reviews (arms A and C) of the hand-built persistent fixture with claude-haiku-5-5."""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

from builders import persistent_trace  # noqa: E402

from rdr.packager import build_package  # noqa: E402
from rdr.runner import review  # noqa: E402

OUT = REPO / "runs" / "smoke"
for arm in ("A", "C"):
    package = build_package(arm, persistent_trace(), "splitwise.expenses#77", "smoke-1")
    with tempfile.TemporaryDirectory() as empty:
        record = review(package, OUT / f"{arm}.json", "claude-haiku-5-5", "medium", Path(empty))
    usage = record["usage"]
    total_in = sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    print(json.dumps({"arm": arm, "answer": record["answer"], "served": record["served_models"],
                      "input_tokens_total": total_in, "package_chars": len(package)}, indent=2))
    assert total_in < 5000, f"context larger than expected ({total_in}); isolation may have failed"
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python spikes/live_reviewer_smoke.py`
Expected: two JSON blocks; `served` contains `claude-haiku-5-5`; `answer` has the three keys; `input_tokens_total` under 5000. If the CLI rejects `--json-schema` or stdin input, record the exact error under Q13, adjust `build_command` or `review` in `src/rdr/runner.py` (and its tests) to the working form, and rerun.

- [ ] **Step 3: Record Q13 and commit**

Append to `docs/gate0_findings.md`:
```markdown
Q13. Live reviewer smoke: stdin accepted? --json-schema accepted? answer field (structured_output or result)? served models? input tokens per call for arms A and C?
Answer:
```
Then:
```bash
git add spikes/live_reviewer_smoke.py docs/gate0_findings.md
git commit -m "Add the live Haiku reviewer smoke test and record its findings" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Next: Plan 2 (written after this plan, from `docs/gate0_findings.md`)

AppWorld adapter producing `Trace` objects with per-call writes; three fault templates (wrong recipient then refund with a stale derived record; wrong amount then correction with a stale derived record; duplicate action after a reported failure); non-persistent and clean-control variants; splicing of N unrelated actions; instance builder writing `trace.json`, `truth.json` and seven packages (arms A to G) per instance; freeze; the Haiku pilot driver (Gate 2, about 300 calls) and its pass-rule check.

Plan 2 starts from `docs/plan2_carryover.md`: the decisions taken at the Plan 1 final review and the design items (created-row id alignment, side-effect rows, graph precision, matched clean-control symptoms) to settle in its first task, before any adapter code.
