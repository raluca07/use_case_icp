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


def stale_records(faulty: Trace, gold: Trace, neutralised: dict[str, dict | None] | None = None,
                  ignore_fields=()) -> tuple[list[str], list[str]]:
    """Stale and missing records of the faulty run against gold.

    `neutralised` maps a record to its expected final value after the repair. Such a record is excluded from
    stale/missing, but only after checking that the repair really left that value.
    """
    neutralised = neutralised or {}
    base = dict(gold.base_values())
    for record, before in faulty.base_values().items():
        if record in base and _strip(base[record], ignore_fields) != _strip(before, ignore_fields):
            raise ValueError(f"runs disagree on the starting value of {record}")
        base.setdefault(record, before)
    faulty_final, gold_final = faulty.final_values(), gold.final_values()
    touched = set(faulty.touched_records())
    stale: list[str] = []
    missing: list[str] = []
    for record in sorted(set(faulty_final) | set(gold_final) | set(neutralised)):
        f_value = _strip(faulty_final.get(record, base.get(record)), ignore_fields)
        if record in neutralised:
            if f_value != _strip(neutralised[record], ignore_fields):
                raise ValueError(f"repair did not neutralise {record}")
            continue
        g_value = _strip(gold_final.get(record, base.get(record)), ignore_fields)
        if f_value != g_value:
            (stale if record in touched else missing).append(record)
    return stale, missing


def choose_symptom(instance_id: str, stale: list[str], faulty: Trace) -> str:
    # Same seed expression as packager.seed_for; kept local so the modules stay independent.
    rng = random.Random(zlib.crc32(instance_id.encode("utf-8")))
    if stale:
        return rng.choice(sorted(stale))
    touched = sorted(faulty.touched_records())
    if not touched:
        raise ValueError("the faulty trace touched no records, so there is no symptom to choose")
    return rng.choice(touched)


def make_truth(instance_id: str, faulty: Trace, gold: Trace, origin_index: int | None,
               neutralised: dict[str, dict | None] | None = None, ignore_fields=(),
               decoy_index: int | None = None, min_stale: int = 1) -> Truth:
    stale, missing = stale_records(faulty, gold, neutralised, ignore_fields)
    is_faulty = bool(stale or missing)
    if is_faulty and origin_index is None:
        raise ValueError("a faulty instance needs an origin index")
    if is_faulty and not stale:
        raise ValueError("faulty instance has no stale record the reviewer can name")
    if is_faulty and len(stale) < min_stale:
        raise ValueError(f"faulty instance has {len(stale)} stale records, fewer than min_stale={min_stale}")
    return Truth(instance_id, is_faulty, origin_index if is_faulty else None, stale, missing,
                 choose_symptom(instance_id, stale, faulty), decoy_index)


def check_clean_control(control: Trace, gold: Trace, neutralised: dict[str, dict | None] | None = None,
                        ignore_fields=()) -> None:
    stale, missing = stale_records(control, gold, neutralised, ignore_fields)
    if stale or missing:
        raise ValueError(f"clean control differs from gold: stale={stale} missing={missing}")
