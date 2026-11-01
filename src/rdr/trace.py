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

    def __post_init__(self) -> None:
        indices = [c.index for c in self.calls]
        if any(later <= earlier for earlier, later in zip(indices, indices[1:])):
            raise ValueError(f"call indices must be unique and strictly increasing, got {indices}")

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
