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
