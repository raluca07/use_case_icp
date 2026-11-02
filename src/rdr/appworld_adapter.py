"""Run an AppWorld task's gold code in a subprocess world and record a Trace with per-call row writes.

Design (Gate 0 Q5, Q8, Q11): the live `world.requester.request` is wrapped, so every `apis.<app>.<api>(...)`
call made by the (unmodified) gold code is recorded with its app, API, arguments and response. Row writes are
attributed to the call that made them by a `before_cursor_execute` listener on every app engine: before an
UPDATE or DELETE it reads the row it is about to change (the before image), before an INSERT it notes the
table's highest rowid. When the call returns, every noted row is read again (the after image) and rows with
rowid above the noted maximum are the created rows. Only tables a call actually changed are read, so no full
database copy is needed. FTS shadow tables and `record_hash` columns are ignored. Supervisor and admin rows
are kept out of the agent's records but still enter the end-state digest used by the determinism gate.

A plan can corrupt one argument of one call and schedule a repair call, both inside the hook, so the gold
code's control flow stays real (carry-over adapter recommendation).

Every world runs in its own subprocess with PYTHONHASHSEED=0 (Gate 0 Q7, Q9: one live world per process).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from rdr.trace import Call, Trace, Write

REPO = Path(__file__).resolve().parents[2]
APPWORLD_ROOT = REPO / "appworld_root"
PYTHON = REPO / ".venv" / "bin" / "python"
SYSTEM_APPS = frozenset({"supervisor", "admin"})
DROPPED_COLUMNS = frozenset({"record_hash"})
FINAL_API = ("supervisor", "complete_task")
_STATEMENT = re.compile(r'^\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"?(\w+)"?', re.IGNORECASE)
_REQUEST_OPTIONS = ("client", "raise_on_failure", "show", "track")


class PlanMismatch(RuntimeError):
    """The call the plan targets is not the call the gold code made at that index."""


def parse_statement(statement: str) -> tuple[str, str] | None:
    """`(kind, table)` for a row-changing statement on a non-FTS table, else None."""
    match = _STATEMENT.match(statement)
    if not match:
        return None
    table = match.group(2)
    if "_fts" in table:
        return None
    return match.group(1).split()[0].upper(), table


def _jsonable(value):
    if isinstance(value, bytes):
        return "bytes:" + hashlib.sha256(value).hexdigest()
    return value


def read_row(connection, table: str, rowid) -> dict | None:
    cursor = connection.execute(f'SELECT * FROM "{table}" WHERE rowid = ?', (rowid,))
    row = cursor.fetchone()
    if row is None:
        return None
    names = [d[0] for d in cursor.description]
    return {k: _jsonable(v) for k, v in zip(names, row) if k not in DROPPED_COLUMNS}


class RowCapture:
    """Before and after images of the rows changed between `begin()` and `end()`."""

    def __init__(self, connections: dict) -> None:
        self.connections = connections
        self.active = False
        self._before: dict[tuple[str, str, int], dict | None] = {}
        self._insert_marks: dict[tuple[str, str], int] = {}

    def begin(self) -> None:
        self.active = True
        self._before = {}
        self._insert_marks = {}

    def on_statement(self, app: str, connection, statement: str, parameters, executemany: bool) -> None:
        if not self.active:
            return
        parsed = parse_statement(statement)
        if parsed is None:
            return
        kind, table = parsed
        if kind == "INSERT":
            key = (app, table)
            if key not in self._insert_marks:
                top = connection.execute(f'SELECT coalesce(max(rowid), 0) FROM "{table}"').fetchone()[0]
                self._insert_marks[key] = top
            return
        for params in (parameters if executemany else [parameters]):
            rowid = params[-1]
            key = (app, table, rowid)
            if key not in self._before:
                self._before[key] = read_row(connection, table, rowid)

    def end(self) -> list[tuple[str, dict | None, dict | None]]:
        """Changed rows as `(label, before, after)`, sorted by label; created rows have before None."""
        self.active = False
        before = dict(self._before)
        for (app, table), top in self._insert_marks.items():
            rows = self.connections[app].execute(f'SELECT rowid FROM "{table}" WHERE rowid > ?', (top,))
            for (rowid,) in rows.fetchall():
                before.setdefault((app, table, rowid), None)
        changes = []
        for (app, table, rowid) in sorted(before, key=lambda k: (k[0], k[1], k[2])):
            after = read_row(self.connections[app], table, rowid)
            if before[(app, table, rowid)] != after:
                changes.append((f"{app}.{table}#{rowid}", before[(app, table, rowid)], after))
        return changes


def _plain(value):
    return json.loads(json.dumps(value, default=str))


@dataclass
class Plan:
    """Optional corruption of one argument of call `index` and an optional repair call.

    `repair` keys: `timing` ("immediate": right after the corrupted call returns; "before_final": just before
    the final `supervisor.complete_task` call), `app`, `api`, `args` (fixed arguments), `id_param` and
    `id_table` (the repair targets the row of `id_table` that the corrupted call wrote and whose columns
    match `id_match`).
    """
    index: int | None = None
    app: str | None = None
    api: str | None = None
    arg: str | None = None
    value: object = None
    repair: dict | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "Plan":
        return cls(**(data or {}))


@dataclass
class Recorder:
    """Stands in for a requester's `request`; records top-level calls and applies a Plan.

    `send(app, api, **kwargs)` performs the call and returns `(status_code, response)`; a call whose status is
    not 200 is recorded in `failed` (the world runs with raise_on_failure=False, as `appworld verify` does,
    because some gold code inspects failure messages)."""
    send: object
    capture: RowCapture
    plan: Plan = field(default_factory=Plan)
    calls: list[Call] = field(default_factory=list)
    system_writes: list[tuple[str, dict | None, dict | None]] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    repair_index: int | None = None
    _depth: int = 0
    _repaired: bool = False

    def __call__(self, _app_name: str, _api_name: str, **kwargs):
        if self._depth:
            return self.send(_app_name, _api_name, **kwargs)[1]
        if (_app_name, _api_name) == FINAL_API and self._repair_due("before_final"):
            self._issue_repair()
        index = len(self.calls)
        if self.plan.index is not None and index == self.plan.index:
            if (_app_name, _api_name) != (self.plan.app, self.plan.api) or self.plan.arg not in kwargs:
                raise PlanMismatch(f"call {index} is {_app_name}.{_api_name}, plan expects "
                                   f"{self.plan.app}.{self.plan.api} with argument {self.plan.arg}")
            kwargs[self.plan.arg] = copy.deepcopy(self.plan.value)
        response = self._record(_app_name, _api_name, kwargs)
        if index == self.plan.index and self._repair_due("immediate"):
            self._issue_repair()
        return response

    def _repair_due(self, timing: str) -> bool:
        repair = self.plan.repair
        return bool(repair) and repair["timing"] == timing and not self._repaired and self.plan.index is not None \
            and len(self.calls) > self.plan.index

    def _issue_repair(self) -> None:
        self._repaired = True
        repair = self.plan.repair
        target = self.calls[self.plan.index]
        prefix = f"{repair['id_table']}#"
        rows = [w for w in target.writes if w.record.startswith(prefix) and w.after is not None
                and all(w.after.get(k) == v for k, v in repair.get("id_match", {}).items())]
        if len(rows) != 1:
            raise PlanMismatch(f"repair target in {repair['id_table']} is ambiguous or absent ({len(rows)} rows)")
        args = {**repair["args"], repair["id_param"]: rows[0].after["id"]}
        self.repair_index = len(self.calls)
        self._record(repair["app"], repair["api"], args)

    def _record(self, app: str, api: str, kwargs: dict):
        args = {k: v for k, v in kwargs.items() if k not in _REQUEST_OPTIONS}
        self.capture.begin()
        self._depth += 1
        error, status = None, None
        try:
            status, response = self.send(app, api, **kwargs)
        except Exception as exception:  # recorded, then re-raised to the gold code
            response, error = {"message": str(exception)}, exception
        finally:
            self._depth -= 1
            changes = self.capture.end()
        writes = []
        for label, before, after in changes:
            if label.split(".", 1)[0] in SYSTEM_APPS:
                self.system_writes.append((label, before, after))
            else:
                writes.append(Write(label, before, after))
        index = len(self.calls)
        self.calls.append(Call(index, app, api, _plain(args), _plain(response), writes))
        if error is not None or status != 200:
            self.failed.append(index)
        if error is not None:
            raise error
        return response


def end_state_digest(calls: list[Call], system_writes) -> str:
    """sha256 of the final value of every row the run changed, system rows included."""
    final: dict[str, object] = {}
    for call in calls:
        for write in call.writes:
            final[write.record] = write.after
    for label, _, after in system_writes:
        final[label] = after
    return hashlib.sha256(json.dumps(final, sort_keys=True, default=str).encode()).hexdigest()


def final_message(calls: list[Call]) -> str:
    finals = [c for c in calls if (c.app, c.api) == FINAL_API]
    answer = finals[-1].args.get("answer") if finals else None
    return "Task completed." if answer in (None, "") else f"Task completed. Answer: {answer}"


# ---------------------------------------------------------------- worker side (inside the subprocess)

def _attach(world, plan: Plan) -> Recorder:
    import importlib

    from sqlalchemy import event

    connections, engines = {}, {}
    for app in world.requester.apps:
        database = importlib.import_module(f"appworld.apps.{app}.models").SQLModel.db
        connections[app], engines[app] = database.connection, database.engine
    capture = RowCapture(connections)

    def listener_for(app):
        def listener(conn, cursor, statement, parameters, context, executemany):
            capture.on_statement(app, cursor.connection, statement, parameters, executemany)
        return listener

    for app, engine in engines.items():
        event.listen(engine, "before_cursor_execute", listener_for(app))
    requester = world.requester

    def send(app, api, client=None, raise_on_failure=None, show=False, track=True, **data):
        requester.raise_if_extra_parameters(app_name=app, api_name=api, parameters=data)
        response = requester._request(_app_name=app, _api_name=api, client=client,
                                      raise_on_failure=raise_on_failure, track=track, **data)
        return response.status_code, requester.response_to_json(response, show=show)

    recorder = Recorder(send, capture, plan)
    requester.request = recorder
    return recorder


def run_world(task_id: str, plan: Plan, experiment: str) -> dict:
    from appworld import AppWorld, update_root

    update_root(str(APPWORLD_ROOT))
    world = AppWorld(task_id=task_id, experiment_name=experiment, ground_truth_mode="full", raise_on_failure=False)
    try:
        recorder = _attach(world, plan)
        code = world.task.ground_truth.compiled_solution_code + "\nsolution(apis, requester)\n"
        output = world.execute(code)
        if plan.repair and not recorder._repaired and len(recorder.calls) > (plan.index or 0):
            recorder._issue_repair()  # gold code ended without a final call
        trace = Trace(task_id, world.task.instruction, final_message(recorder.calls), recorder.calls)
        digest = end_state_digest(recorder.calls, recorder.system_writes)
        evaluation = world.evaluate().to_dict()  # last: evaluate re-points the database handles (Q11)
    finally:
        world.close()
        shutil.rmtree(APPWORLD_ROOT / "experiments" / "outputs" / experiment, ignore_errors=True)
    return {"trace": trace.to_dict(), "evaluation": _plain(evaluation), "digest": digest,
            "output": output, "succeeded": output.strip() == "Execution successful.",
            "failed_calls": recorder.failed, "repair_index": recorder.repair_index}


def _worker_main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--plan")
    parser.add_argument("--out", required=True)
    parser.add_argument("--experiment", required=True)
    args = parser.parse_args(argv)
    plan = Plan.from_dict(json.loads(Path(args.plan).read_text()) if args.plan else None)
    try:
        result = run_world(args.task_id, plan, args.experiment)
    except PlanMismatch as exception:
        result = {"plan_mismatch": str(exception)}
    Path(args.out).write_text(json.dumps(result, sort_keys=True))


def dump_schema(path: str) -> None:
    """Foreign-key and JSON columns of every app table (column names only, no data), for rdr.align.Schema."""
    import importlib
    import inspect

    from appworld import update_root

    update_root(str(APPWORLD_ROOT))
    foreign_keys, json_columns = {}, {}
    for app in ("amazon", "file_system", "gmail", "phone", "simple_note", "splitwise", "spotify", "todoist",
                "venmo", "supervisor", "admin"):
        module = importlib.import_module(f"appworld.apps.{app}.models")
        for obj in vars(module).values():
            table = getattr(obj, "__table__", None)
            if not (inspect.isclass(obj) and table is not None and obj.__module__ == module.__name__):
                continue
            key = f"{app}.{table.name}"
            foreign_keys[key] = {c.name: f"{app}." + next(iter(c.foreign_keys)).target_fullname.split(".")[0]
                                 for c in table.columns if c.foreign_keys}
            json_columns[key] = [c.name for c in table.columns if "JSON" in type(c.type).__name__.upper()]
    Path(path).write_text(json.dumps({"foreign_keys": foreign_keys, "json_columns": json_columns},
                                     indent=2, sort_keys=True))


# ---------------------------------------------------------------- parent side

def load_schema(path: Path):
    """rdr.align.Schema for AppWorld, extracted once in a subprocess and cached at `path`."""
    from rdr.align import Schema

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(REPO / "src")}
        subprocess.run([str(PYTHON), "-c", f"from rdr.appworld_adapter import dump_schema; dump_schema({str(path)!r})"],
                       check=True, env=env, cwd=str(REPO), capture_output=True)
    return Schema.from_dict(json.loads(path.read_text()))

@dataclass
class RunResult:
    trace: Trace | None
    evaluation: dict | None
    digest: str | None
    succeeded: bool
    output: str
    failed_calls: list[int]
    repair_index: int | None = None
    plan_mismatch: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "RunResult":
        if "plan_mismatch" in data:
            return cls(None, None, None, False, "", [], None, data["plan_mismatch"])
        return cls(Trace.from_dict(data["trace"]), data["evaluation"], data["digest"], data["succeeded"],
                   data["output"], data["failed_calls"], data.get("repair_index"))


def run_task(task_id: str, plan: dict | None = None, timeout: int = 900) -> RunResult:
    """Run the task's gold code (with an optional plan) in a fresh subprocess world."""
    key = hashlib.sha256(json.dumps([task_id, plan], sort_keys=True, default=str).encode()).hexdigest()[:12]
    experiment = f"rdr_{key}_{os.getpid()}"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        cmd = [str(PYTHON), "-m", "rdr.appworld_adapter", task_id, "--out", str(out), "--experiment", experiment]
        if plan:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(plan))
            cmd += ["--plan", str(plan_path)]
        env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(REPO / "src")}
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(REPO))
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"adapter worker failed for {task_id}: {proc.stderr[-2000:]}")
        return RunResult.from_dict(json.loads(out.read_text()))


if __name__ == "__main__":
    _worker_main(sys.argv[1:])
