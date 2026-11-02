"""Ground truth across runs whose created rows received different ids (carry-over C1 and I7).

AppWorld assigns created rows the next free rowid, so a faulty run that creates one extra row shifts the ids of
every later created row in that table, and every foreign key or JSON payload that names them (Gate 0 Q6).
In-run labels stay real (`<app>.<table>#<id>`); before comparing, this module:

1. aligns created rows of the faulty run with created rows of the gold run, table by table, first by equal
   canonical final content (exact), then, for rows left over on both sides, by greatest column agreement
   (paired: the same logical row written with different content), repeating until nothing changes;
2. canonicalises every row: the id of a created row, foreign-key columns (SQLModel `__table__.foreign_keys`)
   and ids inside JSON payload columns (`<x>_id` / `<x>_ids` keys, `<x>_ids` columns) that name a created row
   become a token shared by aligned rows (`new:<faulty label>`); ids of pre-existing rows stay as they are;
3. relabels gold created rows to their faulty counterpart (or `absent:<gold label>` when the faulty run never
   made them), so `truth.stale_records` compares the two runs in faulty labels;
4. sets aside side-effect rows (notifications, transfers, and rows of one app written by a call to another,
   such as mail and files produced by a balance top-up; Gate 0 Q6). They are excluded from stale and missing,
   so `min_stale` counts only the rest, and are reported separately as `Truth.side_effect`.
"""
from __future__ import annotations

import json
import random
import zlib
from dataclasses import dataclass, field

from rdr.trace import Call, Trace, Write
from rdr.truth import Truth, make_truth, stale_records

IGNORE_FIELDS = ("record_hash",)
PAIR_MIN_AGREEMENT = 0.5


@dataclass(frozen=True)
class Schema:
    """Column facts per table, keyed `app.table`: foreign keys (`{column: "app.target"}`) and JSON columns."""
    foreign_keys: dict = field(default_factory=dict)
    json_columns: dict = field(default_factory=dict)

    @property
    def tables(self) -> frozenset:
        return frozenset(self.foreign_keys) | frozenset(self.json_columns)

    def to_dict(self) -> dict:
        return {"foreign_keys": self.foreign_keys, "json_columns": self.json_columns}

    @classmethod
    def from_dict(cls, data: dict) -> "Schema":
        return cls(data.get("foreign_keys", {}), data.get("json_columns", {}))


def table_of(label: str) -> str:
    return label.split("#", 1)[0]


def resource_table(app: str, key: str, tables) -> str | None:
    """`transaction_id` / `transaction_ids` / `transactions` -> `<app>.transactions` when that table exists."""
    stem = key
    for suffix in ("_ids", "_id"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        if key == "id":
            return None
    stem = stem.removeprefix("queue_")
    for name in (stem, stem + "s", stem + "es", stem[:-1] + "ies" if stem.endswith("y") else None):
        if name and f"{app}.{name}" in tables:
            return f"{app}.{name}"
    return None


def _created(trace: Trace) -> dict[str, int]:
    """Records whose first write in the run created them, with their creation order."""
    order: dict[str, int] = {}
    seen: set[str] = set()
    for call in trace.calls:
        for write in call.writes:
            if write.record not in seen:
                seen.add(write.record)
                if write.before is None:
                    order[write.record] = len(order)
    return order


class _Canon:
    """Canonicalises rows of one run given a token for each of its created records."""

    def __init__(self, schema: Schema, created: dict[str, int], token, ignore_fields=IGNORE_FIELDS):
        self.schema, self.created, self.token, self.ignore = schema, created, token, set(ignore_fields)
        self.tables = schema.tables | {table_of(r) for r in created}

    def _ref(self, table: str | None, value):
        if table is None or isinstance(value, bool) or not isinstance(value, (int, str)):
            return value
        label = f"{table}#{value}"
        return self.token(label) if label in self.created else value

    def _payload(self, app: str, value, key_table: str | None = None):
        if isinstance(value, dict):
            return {k: self._payload(app, v, resource_table(app, k, self.tables)) for k, v in value.items()}
        if isinstance(value, list):
            return [self._payload(app, v, key_table) for v in value]
        return self._ref(key_table, value)

    def row(self, label: str, row: dict | None) -> dict | None:
        if row is None:
            return None
        table = table_of(label)
        app = table.split(".", 1)[0]
        fks = self.schema.foreign_keys.get(table, {})
        json_cols = set(self.schema.json_columns.get(table, ()))
        out = {}
        for column, value in row.items():
            if column in self.ignore:
                continue
            if column == "id":
                out[column] = self.token(label) if label in self.created else value
            elif column in fks and value is not None:
                out[column] = self._ref(fks[column], value)
            elif column in json_cols and value is not None:
                parsed = value
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                    except ValueError:
                        parsed = value
                out[column] = self._payload(app, parsed, resource_table(app, column, self.tables))
            else:
                out[column] = value
        return out


@dataclass
class Alignment:
    pairs: dict[str, str]  # faulty created label -> gold created label
    exact: set[str]
    faulty_only: list[str]
    gold_only: list[str]

    def to_gold(self, label: str, faulty_created) -> str | None:
        if label in self.pairs:
            return self.pairs[label]
        return None if label in faulty_created else label

    def from_gold(self, label: str) -> str | None:
        inverse = {g: f for f, g in self.pairs.items()}
        if label in inverse:
            return inverse[label]
        return None if label in set(self.gold_only) else label


def _without_id(row):
    return None if row is None else {k: v for k, v in row.items() if k != "id"}


def align(faulty: Trace, gold: Trace, schema: Schema, ignore_fields=IGNORE_FIELDS) -> Alignment:
    f_created, g_created = _created(faulty), _created(gold)
    f_final, g_final = faulty.final_values(), gold.final_values()
    pairs: dict[str, str] = {}
    exact: set[str] = set()

    def f_token(label):
        return f"new:{label}" if label in pairs else f"?f:{label}"

    def g_token(label):
        inverse = {g: f for f, g in pairs.items()}
        return f"new:{inverse[label]}" if label in inverse else f"?g:{label}"

    f_canon = _Canon(schema, f_created, f_token, ignore_fields)
    g_canon = _Canon(schema, g_created, g_token, ignore_fields)

    def open_rows():
        matched = set(pairs.values())
        by_table: dict[str, tuple[list[str], list[str]]] = {}
        for label in sorted(f_created, key=f_created.get):
            if label not in pairs:
                by_table.setdefault(table_of(label), ([], []))[0].append(label)
        for label in sorted(g_created, key=g_created.get):
            if label not in matched:
                by_table.setdefault(table_of(label), ([], []))[1].append(label)
        return {t: v for t, v in by_table.items() if v[0] and v[1]}

    while True:
        progress = False
        for table, (f_open, g_open) in sorted(open_rows().items()):
            g_rows = {g: _without_id(g_canon.row(g, g_final.get(g))) for g in g_open}
            taken: set[str] = set()
            for f in f_open:
                f_row = _without_id(f_canon.row(f, f_final.get(f)))
                for g in g_open:
                    if g not in taken and g_rows[g] == f_row:
                        pairs[f] = g
                        exact.add(f)
                        taken.add(g)
                        progress = True
                        break
        if progress:
            continue
        for table, (f_open, g_open) in sorted(open_rows().items()):
            best = None
            for fi, f in enumerate(f_open):
                f_row = _without_id(f_canon.row(f, f_final.get(f))) or {}
                for gi, g in enumerate(g_open):
                    g_row = _without_id(g_canon.row(g, g_final.get(g))) or {}
                    columns = set(f_row) | set(g_row)
                    agree = sum(f_row.get(c) == g_row.get(c) for c in columns) / len(columns) if columns else 0.0
                    key = (agree, -fi, -gi)
                    if agree >= PAIR_MIN_AGREEMENT and (best is None or key > best[0]):
                        best = (key, f, g)
            if best is not None:
                pairs[best[1]] = best[2]
                progress = True
        if not progress:
            break
    faulty_only = [f for f in sorted(f_created, key=f_created.get) if f not in pairs]
    matched = set(pairs.values())
    gold_only = [g for g in sorted(g_created, key=g_created.get) if g not in matched]
    return Alignment(pairs, exact, faulty_only, gold_only)


# ---------------------------------------------------------------- side effects

def is_side_effect(record: str, call: Call) -> bool:
    """Notifications and bank transfers written as by-products, and rows of one app written by another app."""
    app, table = table_of(record).split(".", 1)
    if app != call.app:
        return True
    if table == "notifications" and "notification" not in call.api:
        return True
    if table == "bank_transfers" and not any(w in call.api for w in ("transfer", "balance")):
        return True
    return False


def side_effect_records(trace: Trace) -> set[str]:
    return {w.record for c in trace.calls for w in c.writes if is_side_effect(w.record, c)}


# ---------------------------------------------------------------- canonical traces and truth

def canonical_traces(faulty: Trace, gold: Trace, schema: Schema, alignment: Alignment,
                     ignore_fields=IGNORE_FIELDS, drop_faulty=frozenset(), drop_gold=frozenset()) -> tuple[Trace, Trace]:
    """Both runs rewritten into faulty labels with canonical row values; the dropped records (in each run's own
    labels) are left out."""
    f_created, g_created = _created(faulty), _created(gold)
    inverse = {g: f for f, g in alignment.pairs.items()}
    f_canon = _Canon(schema, f_created, lambda label: f"new:{label}", ignore_fields)
    g_canon = _Canon(schema, g_created,
                     lambda label: f"new:{inverse[label]}" if label in inverse else f"absent:{label}", ignore_fields)

    def g_label(label):
        if label in inverse:
            return inverse[label]
        return f"absent:{label}" if label in g_created else label

    def rewrite(trace, canon, relabel, drop):
        calls = []
        for c in trace.calls:
            writes = [Write(relabel(w.record), canon.row(w.record, w.before), canon.row(w.record, w.after))
                      for w in c.writes if w.record not in drop]
            calls.append(Call(c.index, c.app, c.api, c.args, c.response, writes))
        return Trace(trace.task_id, trace.instruction, trace.final_message, calls)

    return rewrite(faulty, f_canon, lambda label: label, drop_faulty), rewrite(gold, g_canon, g_label, drop_gold)


@dataclass
class Comparison:
    stale: list[str]
    missing: list[str]
    side_effect: list[str]
    alignment: Alignment
    faulty_canonical: Trace
    gold_canonical: Trace


def compare(faulty: Trace, gold: Trace, schema: Schema, neutralised=None, ignore_fields=IGNORE_FIELDS) -> Comparison:
    """Stale and missing records of `faulty` against `gold` under the alignment, side effects set aside.
    `neutralised` is keyed by faulty labels; values are full rows or `truth.Partial` field subsets."""
    alignment = align(faulty, gold, schema, ignore_fields)
    f_side = side_effect_records(faulty)
    g_side = side_effect_records(gold)
    f_c, g_c = canonical_traces(faulty, gold, schema, alignment, ignore_fields, f_side, g_side)
    stale, missing = stale_records(f_c, g_c, neutralised or {}, ignore_fields)
    f_full, g_full = canonical_traces(faulty, gold, schema, alignment, ignore_fields)
    side_stale, side_missing = stale_records(f_full, g_full, {k: v for k, v in (neutralised or {}).items()
                                                              if k in f_side}, ignore_fields)
    side = sorted(r for r in set(side_stale) | set(side_missing) if r in f_side or r.removeprefix("absent:") in g_side)
    return Comparison(stale, missing, side, alignment, f_c, g_c)


def make_aligned_truth(instance_id: str, faulty: Trace, gold: Trace, schema: Schema, origin_index: int | None,
                       neutralised=None, min_stale: int = 1, decoy_index: int | None = None, *,
                       expect_faulty: bool, ignore_fields=IGNORE_FIELDS) -> Truth:
    comparison = compare(faulty, gold, schema, neutralised, ignore_fields)
    truth = make_truth(instance_id, comparison.faulty_canonical, comparison.gold_canonical, origin_index,
                       neutralised, ignore_fields, decoy_index, min_stale, expect_faulty=expect_faulty)
    truth.side_effect = comparison.side_effect
    return truth


def check_aligned_clean_control(control: Trace, gold: Trace, schema: Schema, neutralised=None,
                                ignore_fields=IGNORE_FIELDS) -> Comparison:
    comparison = compare(control, gold, schema, neutralised, ignore_fields)
    if comparison.stale or comparison.missing:
        raise ValueError(f"clean control differs from gold: stale={comparison.stale} missing={comparison.missing}")
    return comparison


def matched_symptom(instance_id: str, persistent: Comparison, clean: Comparison, clean_trace: Trace,
                    persistent_trace: Trace) -> str:
    """Carry-over I6: the clean twin's symptom is drawn from the persistent twin's stale set, mapped to gold
    labels through the persistent alignment and on to clean labels through the clean alignment."""
    p_created = set(_created(persistent_trace))
    touched = set(clean_trace.touched_records())
    candidates = []
    for label in persistent.stale:
        gold_label = persistent.alignment.to_gold(label, p_created)
        if gold_label is None:
            continue
        clean_label = clean.alignment.from_gold(gold_label)
        if clean_label is not None and clean_label in touched:
            candidates.append(clean_label)
    if not candidates:
        raise ValueError("no stale record of the persistent twin maps onto a record the clean twin touched")
    rng = random.Random(zlib.crc32(instance_id.encode("utf-8")))
    return rng.choice(sorted(set(candidates)))
