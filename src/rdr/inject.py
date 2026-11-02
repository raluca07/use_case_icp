"""Generic fault injection on AppWorld gold runs (no per-task code).

A candidate is one argument of one gold write call W, a wrong value for it, and a repair that restores W's
row. Three variants share the wrong action and the repair:

- persistent: W runs with the wrong value, the gold code continues, the repair runs just before the final
  `supervisor.complete_task` call;
- clean twin: the same wrong value, repaired immediately after W, before any consumer;
- non-persistent: the wrong value and no repair.

Consumers of W's wrong value are later gold write calls. Natural consumers are reached from W by graph feeds
or reads edges. Because AppWorld gold code almost never feeds one write's output into another write
(docs/pilot_build.md), a second, documented kind is used: held-value consumers, later calls of the same API
that passed the same value for the same argument (for paths: under the same parent directory). In the
persistent and non-persistent variants the agent keeps using the wrong value in those calls (Plan.held) until
the repair; in the clean twin the immediate repair closes that window, so nothing derives from the wrong value.

The repair is resolved from the API docs: a PATCH API of W's app that takes the corrupted field and addresses
W's row (a path id that maps to the row's table, or a required argument W also passed, such as a file path),
or, for a corrupted destination path, the app's relocation API (`source_<x>` / `destination_<x>`). A candidate
without a repair is skipped.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import asdict, dataclass, field

from rdr.graph import build_graph, call_node, rec_node
from rdr.trace import Call, Trace

SYSTEM_APPS = frozenset({"supervisor", "admin", "api_docs"})
SKIPPED_ARGS = frozenset({"access_token", "page_index", "page_limit", "limit", "offset", "overwrite",
                          "retain_dates", "password", "username"})
VARIANTS = ("persistent", "clean", "nonpersistent")


@dataclass
class Candidate:
    task_id: str
    index: int
    app: str
    api: str
    arg: str
    gold_value: object
    wrong_value: object
    table: str | None
    column: str | None
    repair: dict
    neutral: dict | None
    held: dict | None = None
    consumers: list[int] = field(default_factory=list)
    natural: list[int] = field(default_factory=list)

    @property
    def template(self) -> str:
        return f"{self.app}.{self.api}:{self.arg}"

    @property
    def generator(self) -> str:
        return self.task_id.split("_", 1)[0]

    @property
    def persistent_capable(self) -> bool:
        return bool(self.consumers or self.natural)

    @property
    def key(self) -> str:
        return f"{self.task_id}:{self.index}:{self.arg}"

    def instance_id(self, variant: str) -> str:
        digest = hashlib.sha256(f"{self.key}:{variant}".encode()).hexdigest()[:10]
        return f"{self.task_id}_{digest}"

    def plan(self, variant: str) -> dict:
        if variant not in VARIANTS:
            raise ValueError(variant)
        plan = {"index": self.index, "app": self.app, "api": self.api, "arg": self.arg, "value": self.wrong_value}
        if variant in ("persistent", "nonpersistent") and self.held:
            plan["held"] = self.held
        if variant == "persistent":
            plan["repair"] = {**self.repair, "timing": "before_final"}
        elif variant == "clean":
            plan["repair"] = {**self.repair, "timing": "immediate"}
        return plan

    def to_dict(self) -> dict:
        return asdict(self)


def _is_path(value) -> bool:
    return isinstance(value, str) and " " not in value and (value.startswith("/") or value.startswith("~/")) \
        and len(value) > 2


def _scalars(obj, out: list) -> None:
    if isinstance(obj, dict):
        for value in obj.values():
            _scalars(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _scalars(value, out)
    elif obj is not None:
        out.append(obj)


def _values_under(obj, key: str, out: list) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and not isinstance(v, (dict, list, bool)) and v is not None:
                out.append(v)
            _values_under(v, key, out)
    elif isinstance(obj, list):
        for v in obj:
            _values_under(v, key, out)


def _directories(trace: Trace) -> list[str]:
    seen: set[str] = set()
    for call in trace.calls:
        found: list = []
        _scalars(call.args, found)
        _scalars(call.response, found)
        for value in found:
            if _is_path(value):
                parent = value if value.endswith("/") else posixpath.dirname(value) + "/"
                if parent not in ("/", "~/"):
                    seen.add(parent)
    return sorted(seen)


def wrong_value(gold: Trace, call: Call, key: str, value):
    """A plausible wrong value of the same type, drawn from the run itself where possible; None if none."""
    if isinstance(value, bool):
        return not value
    if _is_path(value):
        parent = posixpath.dirname(value.rstrip("/")) + "/"
        style = "~/" if value.startswith("~/") else "/"
        siblings = [d for d in _directories(gold) if d != parent and not parent.startswith(d)
                    and not d.startswith(parent) and d.startswith(style)]
        grand = posixpath.dirname(parent.rstrip("/"))
        if not siblings and grand.rstrip("/") not in ("", "~"):
            siblings = [grand + "/"]  # one level up: the file lands in the enclosing folder
        if not siblings:
            return None
        siblings.sort(key=lambda d: (posixpath.dirname(d.rstrip("/")) != grand, d))
        return siblings[0] + posixpath.basename(value.rstrip("/"))
    seen: list = []
    for other in gold.calls:
        _values_under(other.response, key, seen)
    others = sorted({v for v in seen if v != value and type(v) is type(value)}, key=str)
    is_id = key == "id" or key.endswith("_id")
    if isinstance(value, int):
        if is_id:
            return others[0] if others else None
        return value - 1 if value > 1 else value + 1
    if isinstance(value, float):
        return round(value + (10.0 if value >= 10 else 1.0), 2)
    if isinstance(value, str):
        if is_id:
            return others[0] if others else None
        match = re.search(r"\d+", value)
        if match:
            return value[: match.start()] + str(int(match.group()) + 1) + value[match.end():]
        if others:
            return others[0]
        words = value.split()
        if len(words) >= 2:
            return " ".join(words[:-1])  # truncated text
        return None
    return None


def _primary_row(call: Call, key: str, value) -> tuple[str, str] | None:
    """(table, column) of the row W wrote in its own app that holds the argument's value."""
    for write in call.writes:
        table = write.record.split("#", 1)[0]
        if table.split(".", 1)[0] != call.app or write.after is None:
            continue
        for column in ([key] if key in write.after else []) + sorted(write.after):
            if write.after.get(column) == value and column != "id":
                return table, column
    return None


def _relocation(app_docs: dict, key: str, gold_value, wrong, call: Call):
    """The app's move API (W's own API first): copying would leave the wrong file behind."""
    noun = key.removeprefix("destination_").removeprefix("source_")
    names = sorted(app_docs, key=lambda n: (n != call.api, not n.startswith("move_"), n))
    for name in names:
        if name != call.api and not name.startswith("move_"):
            continue
        doc = app_docs[name]
        params = {p["name"] for p in doc["parameters"]}
        if {f"source_{noun}", f"destination_{noun}"} <= params:
            args = {f"source_{noun}": wrong, f"destination_{noun}": gold_value}
            if "access_token" in params and "access_token" in call.args:
                args["access_token"] = call.args["access_token"]
            return {"app": call.app, "api": name, "args": args}
    return None


def find_repair(call: Call, key: str, gold_value, wrong, row: tuple[str, str] | None, api_docs: dict,
                id_tables: dict) -> tuple[dict, dict | None] | None:
    """(repair template, neutral fields of the repaired row) or None."""
    app_docs = api_docs.get(call.app, {})
    if _is_path(gold_value):
        creates = any(w.before is None and w.record.split(".", 1)[0] == call.app for w in call.writes)
        if not creates or not (key == "file_path" or key.startswith("destination_")):
            return None
        repair = _relocation(app_docs, key, gold_value, wrong, call)
        return (repair, None) if repair else None
    if row is None:
        return None
    table, column = row
    for name, doc in sorted(app_docs.items()):
        if doc.get("method") != "PATCH":
            continue
        params = {p["name"]: p for p in doc["parameters"]}
        field_name = key if key in params else (column if column in params else None)
        if field_name is None:
            continue
        segments = doc["path"].strip("/").split("/")
        mapping = id_tables.get(f"{call.app}.{name}", {})
        path_params = [p for p in params if "{" + p + "}" in segments]
        if any(mapping.get(p) not in (None, table) for p in path_params):
            continue  # the API addresses rows of another table
        id_param = next((p for p in path_params if mapping.get(p) == table), None)
        args = {field_name: gold_value}
        addressed = id_param is not None
        unsatisfied = False
        for p, spec in params.items():
            if p in (field_name, id_param, "access_token") or not spec.get("required"):
                continue
            if p in call.args and p != key and mapping.get(p) in (None, table):
                args[p] = call.args[p]
                addressed = True
            else:
                unsatisfied = True
        if unsatisfied or not addressed:
            continue
        if "access_token" in params and "access_token" in call.args:
            args["access_token"] = call.args["access_token"]
        repair = {"app": call.app, "api": name, "args": args}
        if id_param:
            repair.update({"id_param": id_param, "id_table": table, "id_match": {column: wrong}})
        return repair, {column: gold_value}
    return None


def _held(gold: Trace, call: Call, key: str, value, wrong) -> tuple[dict | None, list[int]]:
    later = [c for c in gold.calls if c.index > call.index and (c.app, c.api) == (call.app, call.api) and c.writes]
    if _is_path(value):
        parent = posixpath.dirname(value.rstrip("/")) + "/"
        wrong_parent = posixpath.dirname(str(wrong).rstrip("/")) + "/"
        consumers = [c.index for c in later if isinstance(c.args.get(key), str) and c.args[key].startswith(parent)]
        held = {"api": call.api, "arg": key, "value": parent, "wrong": wrong_parent, "mode": "prefix"}
    else:
        consumers = [c.index for c in later if c.args.get(key) == value and type(c.args.get(key)) is type(value)]
        held = {"api": call.api, "arg": key, "value": value, "wrong": wrong, "mode": "equal"}
    return (held if consumers else None), consumers


def _natural(gold: Trace, graph, call: Call) -> list[int]:
    written = {rec_node(w.record) for w in call.writes}
    targets = set()
    for edge in graph.edges:
        if (edge.kind == "feeds" and edge.src == call_node(call.index)) or (edge.kind == "reads" and edge.src in written):
            targets.add(int(edge.dst.split(":", 1)[1]))
    writers = {c.index for c in gold.calls if c.writes and c.app not in SYSTEM_APPS}
    return sorted(t for t in targets if t > call.index and t in writers)


def find_candidates(gold: Trace, api_docs: dict, id_tables: dict) -> list[Candidate]:
    graph = build_graph(gold, id_tables)
    out: list[Candidate] = []
    for call in gold.calls:
        if not call.writes or call.app in SYSTEM_APPS:
            continue
        if isinstance(call.response, dict) and set(call.response) == {"message"} and "status code" in str(call.response):
            continue
        for key, value in sorted(call.args.items()):
            if key in SKIPPED_ARGS or key.startswith("source_") or value is None or isinstance(value, (dict, list)):
                continue
            wrong = wrong_value(gold, call, key, value)
            if wrong is None or wrong == value:
                continue
            row = None if _is_path(value) else _primary_row(call, key, value)
            found = find_repair(call, key, value, wrong, row, api_docs, id_tables)
            if found is None:
                continue
            repair, neutral = found
            held, consumers = _held(gold, call, key, value, wrong)
            out.append(Candidate(gold.task_id, call.index, call.app, call.api, key, value, wrong,
                                 row[0] if row else None, row[1] if row else None, repair, neutral, held,
                                 consumers, _natural(gold, graph, call)))
    return out


def repaired_record(trace: Trace, candidate: Candidate) -> str | None:
    """Faulty label of W's row that the repair restores (None for relocations, whose row is recreated)."""
    if candidate.table is None:
        return None
    for write in trace.calls[candidate.index].writes:
        if write.record.split("#", 1)[0] == candidate.table and write.after is not None \
                and write.after.get(candidate.column) == candidate.wrong_value:
            return write.record
    return None
