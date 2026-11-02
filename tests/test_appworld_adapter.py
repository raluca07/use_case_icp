"""Unit tests for the adapter's capture and hook layers on a synthetic sqlite database (no AppWorld needed),
plus one integration test that runs a real gold solution when the AppWorld data is installed."""
import sqlite3

import pytest
from sqlalchemy import create_engine, event, text

from rdr.appworld_adapter import (APPWORLD_ROOT, Plan, PlanMismatch, Recorder, RowCapture, end_state_digest,
                                  final_message, parse_statement)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT, record_hash TEXT);
        CREATE TABLE notes_fts (title TEXT);
        CREATE TABLE tasks (id INTEGER PRIMARY KEY, status TEXT);
        INSERT INTO notes (title, record_hash) VALUES ('a', 'h1'), ('b', 'h2');
        INSERT INTO tasks (status) VALUES ('open');
    """)
    return conn


class FakeApp:
    """Requester stand-in: each API runs SQL and reports statements to the capture, as the engine listener does."""

    def __init__(self, conns, capture):
        self.conns, self.capture, self.log = conns, capture, []

    def _exec(self, app, sql, params=()):
        self.capture.on_statement(app, self.conns[app], sql, params, False)
        cur = self.conns[app].execute(sql, params)
        return cur.lastrowid

    def __call__(self, app, api, **kw):
        if api == "reject":
            return 422, {"message": "Account for this email does not exist."}
        return 200, self._run(app, api, **kw)

    def _run(self, app, api, **kw):
        self.log.append((app, api, dict(kw)))
        if api == "create_note":
            rowid = self._exec("notes_app", "INSERT INTO notes (title, record_hash) VALUES (?, 'x')", (kw["title"],))
            self._exec("notes_app", "INSERT INTO notes_fts (title) VALUES (?)", (kw["title"],))
            return {"note_id": rowid}
        if api == "update_note":
            self._exec("notes_app", "UPDATE notes SET title=?, record_hash='y' WHERE notes.id = ?",
                       (kw["title"], kw["note_id"]))
            return {"message": "ok"}
        if api == "delete_note":
            self._exec("notes_app", "DELETE FROM notes WHERE notes.id = ?", (kw["note_id"],))
            return {"message": "ok"}
        if api == "show_note":
            return {"title": "a"}
        if api == "fail":
            raise RuntimeError("Response status code is 422")
        if api == "complete_task":
            self._exec("supervisor", "UPDATE tasks SET status=? WHERE tasks.id = ?", ("done", 1))
            return {"message": "ok"}
        raise AssertionError(api)


def _recorder(plan=None):
    conns = {"notes_app": _db(), "supervisor": _db()}
    capture = RowCapture(conns)
    app = FakeApp(conns, capture)
    return Recorder(app, capture, plan or Plan()), app


def test_parse_statement_kinds_and_fts():
    assert parse_statement('INSERT INTO notes (title) VALUES (?)') == ("INSERT", "notes")
    assert parse_statement('UPDATE "notes" SET title=? WHERE notes.id = ?') == ("UPDATE", "notes")
    assert parse_statement("DELETE FROM notes WHERE notes.id = ?") == ("DELETE", "notes")
    assert parse_statement("INSERT INTO notes_fts (title) VALUES (?)") is None
    assert parse_statement("SELECT * FROM notes") is None


def test_create_update_delete_are_attributed_to_their_calls():
    rec, _ = _recorder()
    rec("notes_app", "show_note", note_id=1)
    created = rec("notes_app", "create_note", title="c", access_token="t")
    rec("notes_app", "update_note", note_id=1, title="a2")
    rec("notes_app", "delete_note", note_id=2)
    calls = rec.calls
    assert [c.index for c in calls] == [0, 1, 2, 3] and created == {"note_id": 3}
    assert calls[0].writes == []
    [w] = calls[1].writes
    assert (w.record, w.before, w.after) == ("notes_app.notes#3", None, {"id": 3, "title": "c"})
    [w] = calls[2].writes
    assert (w.record, w.before, w.after) == ("notes_app.notes#1", {"id": 1, "title": "a"}, {"id": 1, "title": "a2"})
    [w] = calls[3].writes
    assert (w.record, w.after) == ("notes_app.notes#2", None) and w.before == {"id": 2, "title": "b"}
    assert calls[1].args == {"title": "c", "access_token": "t"} and calls[1].response == {"note_id": 3}


def test_record_hash_and_fts_rows_are_not_writes():
    rec, _ = _recorder()
    rec("notes_app", "create_note", title="c")
    assert [w.record for w in rec.calls[0].writes] == ["notes_app.notes#3"]
    assert "record_hash" not in rec.calls[0].writes[0].after


def test_system_rows_are_kept_out_of_agent_writes_but_enter_the_digest():
    rec, _ = _recorder()
    rec("supervisor", "complete_task", status="success")
    assert rec.calls[0].writes == [] and [w[0] for w in rec.system_writes] == ["supervisor.tasks#1"]
    other, _ = _recorder()
    assert end_state_digest(rec.calls, rec.system_writes) != end_state_digest(other.calls, other.system_writes)


def test_failed_call_is_recorded_and_reraised():
    rec, _ = _recorder()
    with pytest.raises(RuntimeError):
        rec("notes_app", "fail")
    assert rec.failed == [0] and "422" in rec.calls[0].response["message"]


def test_non_200_response_is_returned_to_the_code_and_marked_failed():
    rec, _ = _recorder()
    assert rec("notes_app", "reject", email="x") == {"message": "Account for this email does not exist."}
    rec("notes_app", "show_note", note_id=1)
    assert rec.failed == [0]


def test_nested_calls_are_not_recorded_separately():
    rec, app = _recorder()
    original = app.__call__

    def outer(a, api, **kw):
        if api == "create_note":
            rec("notes_app", "show_note", note_id=1)  # nested: reaches the app, not the call list
        return original(a, api, **kw)

    rec.send = outer
    rec("notes_app", "create_note", title="c")
    assert [c.api for c in rec.calls] == ["create_note"]


def test_plan_corrupts_one_argument_and_repairs_before_the_final_call():
    plan = Plan(index=1, app="notes_app", api="create_note", arg="title", value="WRONG",
                repair={"timing": "before_final", "app": "notes_app", "api": "update_note",
                        "args": {"title": "c"}, "id_param": "note_id", "id_table": "notes_app.notes",
                        "id_match": {"title": "WRONG"}})
    rec, app = _recorder(plan)
    rec("notes_app", "show_note", note_id=1)
    rec("notes_app", "create_note", title="c")
    rec("notes_app", "show_note", note_id=3)
    rec("supervisor", "complete_task", status="success")
    assert [c.api for c in rec.calls] == ["show_note", "create_note", "show_note", "update_note", "complete_task"]
    assert rec.calls[1].args["title"] == "WRONG" and rec.calls[3].args == {"title": "c", "note_id": 3}
    assert rec.repair_index == 3 and rec.calls[3].writes[0].after == {"id": 3, "title": "c"}


def test_plan_immediate_repair_follows_the_corrupted_call():
    plan = Plan(index=0, app="notes_app", api="create_note", arg="title", value="WRONG",
                repair={"timing": "immediate", "app": "notes_app", "api": "update_note", "args": {"title": "c"},
                        "id_param": "note_id", "id_table": "notes_app.notes", "id_match": {}})
    rec, _ = _recorder(plan)
    rec("notes_app", "create_note", title="c")
    rec("notes_app", "show_note", note_id=3)
    assert [c.api for c in rec.calls] == ["create_note", "update_note", "show_note"] and rec.repair_index == 1


def test_patch_changes_what_the_code_sees_but_not_the_recorded_response():
    rec, _ = _recorder(Plan(patch={"index": 0, "value": 3, "replacement": 9}))
    seen = rec("notes_app", "create_note", title="c")
    assert seen == {"note_id": 9} and rec.calls[0].response == {"note_id": 3}


def test_replace_value_compares_numbers_and_numeric_strings_as_text():
    from rdr.appworld_adapter import replace_value
    assert replace_value({"a": [3, "3", 3.0, "x3"], "b": True}, 3, 10) == {"a": [10, "10", 10, "x3"], "b": True}
    assert replace_value({"e": "a@b.c"}, "a@b.c", "z@b.c") == {"e": "z@b.c"}


def test_plan_mismatch_raises():
    rec, _ = _recorder(Plan(index=0, app="notes_app", api="create_note", arg="title", value="x"))
    with pytest.raises(PlanMismatch):
        rec("notes_app", "show_note", note_id=1)


def test_final_message_uses_the_answer():
    rec, _ = _recorder()
    rec("supervisor", "complete_task", status="success")
    assert final_message(rec.calls) == "Task completed."
    rec.calls[0].args["answer"] = 42
    assert final_message(rec.calls) == "Task completed. Answer: 42"


def test_capture_works_through_a_sqlalchemy_before_cursor_execute_listener():
    engine = create_engine("sqlite://", future=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO notes (title) VALUES ('a')"))
        raw = conn.connection.connection
        capture = RowCapture({"x": raw})
        event.listen(engine, "before_cursor_execute",
                     lambda c, cursor, st, params, ctx, many: capture.on_statement("x", cursor.connection, st,
                                                                                   params, many))
        capture.begin()
        conn.execute(text("UPDATE notes SET title=:t WHERE notes.id = :i"), {"t": "b", "i": 1})
        conn.execute(text("INSERT INTO notes (title) VALUES ('c')"))
        changes = capture.end()
    assert changes == [("x.notes#1", {"id": 1, "title": "a"}, {"id": 1, "title": "b"}),
                       ("x.notes#2", None, {"id": 2, "title": "c"})]


@pytest.mark.skipif(not (APPWORLD_ROOT / "data" / "tasks" / "60d0b5b_1").exists(), reason="AppWorld data absent")
def test_gold_run_of_a_real_task_records_writes_and_passes():
    from rdr.appworld_adapter import run_task
    result = run_task("60d0b5b_1")
    assert result.succeeded and result.evaluation["success"] is True and not result.failed_calls
    writers = [c for c in result.trace.calls if c.writes]
    assert len(writers) == 1 and writers[0].api == "create_transaction"
    assert {w.record.split("#")[0] for w in writers[0].writes} == {"venmo.notifications", "venmo.transactions",
                                                                   "venmo.users"}
    assert result.trace.calls[-1].api == "complete_task" and result.trace.calls[-1].writes == []


@pytest.mark.skipif(not (APPWORLD_ROOT / "data").exists(), reason="AppWorld data absent")
def test_schema_lists_foreign_keys_and_json_columns(tmp_path):
    from rdr.appworld_adapter import load_schema
    schema = load_schema(tmp_path / "schema.json")
    assert schema.foreign_keys["venmo.transactions"] == {"sender_id": "venmo.users", "receiver_id": "venmo.users"}
    assert schema.json_columns["venmo.notifications"] == ["data"]
    assert "spotify.playlist_songs" in schema.tables
