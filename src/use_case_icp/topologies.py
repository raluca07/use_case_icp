"""Several pipeline shapes, so a selection result is not a property of one topology.

The causal-root selector was first measured on a single branching pipeline. If it wins
there because of that shape rather than because of the graph, the paper's headline does
not generalise. These four shapes differ in how evidence flows, and the fault is injected
into every boundary of each.
"""
from __future__ import annotations
from typing import Any
from .fault_scoring import Contract
from .records import GeneratedFile, GeneratedPipeline

def _stage(name: str, body: str) -> str:
    return f"def {name}(payload):\n{body}\n"

HEAD = "import json\n\ndef seed():\n    return {'items': ['a','b','c','d','e','f'], 'n': 6}\n\n"
PASS = ("    items = payload.get('items', [])\n"
        "    return {'items': items, 'n': len(items), 'tag': '%s'}\n")
MERGE = ("    items = []\n    for p in parts:\n        items.extend(p.get('items', []))\n"
         "    return {'items': items, 'n': len(items), 'tag': '%s'}\n")

def chain(k: int) -> tuple[str, list[str]]:
    """Deep chain: seed -> s1 -> s2 -> ... -> sk."""
    names = ["seed"] + [f"s{i}" for i in range(1, k + 1)]
    src = HEAD + "".join(_stage(f"s{i}", PASS % f"s{i}") for i in range(1, k + 1))
    src += "state = seed()\n" + "".join(f"state = s{i}(state)\n" for i in range(1, k + 1))
    return src + "print(json.dumps(state, sort_keys=True))\n", names

def fan(width: int) -> tuple[str, list[str]]:
    """Wide fan-out: seed feeds `width` siblings, all merged once."""
    names = ["seed"] + [f"b{i}" for i in range(1, width + 1)] + ["collect"]
    src = HEAD + "".join(_stage(f"b{i}", PASS % f"b{i}") for i in range(1, width + 1))
    src += ("def collect(*parts):\n" + MERGE % "collect")
    src += "root = seed()\n"
    src += "".join(f"p{i} = b{i}(root)\n" for i in range(1, width + 1))
    src += "state = collect(" + ", ".join(f"p{i}" for i in range(1, width + 1)) + ")\n"
    return src + "print(json.dumps(state, sort_keys=True))\n", names

def diamond(depth: int) -> tuple[str, list[str]]:
    """Diamond: split into two arms of `depth`, then reconverge."""
    names = ["seed"] + [f"l{i}" for i in range(1, depth + 1)] + \
            [f"r{i}" for i in range(1, depth + 1)] + ["join"]
    src = HEAD
    for side in ("l", "r"):
        src += "".join(_stage(f"{side}{i}", PASS % f"{side}{i}") for i in range(1, depth + 1))
    src += "def join(*parts):\n" + MERGE % "join"
    src += "root = seed()\nleft = root\n"
    src += "".join(f"left = l{i}(left)\n" for i in range(1, depth + 1))
    src += "right = root\n"
    src += "".join(f"right = r{i}(right)\n" for i in range(1, depth + 1))
    src += "state = join(left, right)\n"
    return src + "print(json.dumps(state, sort_keys=True))\n", names

TOPOLOGIES = {
    "chain-8": lambda: chain(8),
    "fan-6": lambda: fan(6),
    "diamond-4": lambda: diamond(4),
    "chain-3": lambda: chain(3),
}

def build(name: str) -> tuple[GeneratedPipeline, list[str]]:
    src, names = TOPOLOGIES[name]()
    return GeneratedPipeline("pipeline.py",
                             [GeneratedFile("pipeline.py", src)],
                             [{"function_name": n} for n in names]), names

def contracts(names: list[str]) -> dict[str, Contract]:
    return {n: Contract(n, required_fields=["items", "n"], min_items={"items": 6})
            for n in names}
