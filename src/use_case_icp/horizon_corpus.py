"""Pipelines of varying length, with the fault always at the same place.

If a model localises a fault by following evidence to where output looks wrong, it will
name a stage downstream of the break. Lengthening the chain adds more places downstream
to misattribute to, so the claim that this failure compounds with horizon is testable
directly: hold the fault fixed at the head and vary how many stages follow it.
"""
from __future__ import annotations
import ast, contextlib, copy, io
from typing import Any
from .cassette_corpus import BASE_CASSETTE, MUTATIONS
from .fault_scoring import _DEFINITION_NODES

TRANSFORM_BODIES = [
    '    docs = payload.get("documents", [])\n'
    '    kept = [d for d in docs if d.get("id")]\n'
    '    return {"documents": kept, "source_ids": [d.get("id") for d in kept],\n'
    '            "kept_count": len(kept)}\n',
    '    docs = payload.get("documents", [])\n'
    '    return {"documents": docs, "source_ids": payload.get("source_ids", []),\n'
    '            "quote_count": sum(len(d.get("quotes", [])) for d in docs)}\n',
    '    docs = sorted(payload.get("documents", []), key=lambda d: str(d.get("id")))\n'
    '    return {"documents": docs, "source_ids": [d.get("id") for d in docs],\n'
    '            "ordered": True}\n',
    '    docs = payload.get("documents", [])\n'
    '    dates = [d.get("published") for d in docs]\n'
    '    return {"documents": docs, "source_ids": payload.get("source_ids", []),\n'
    '            "dated_count": len([x for x in dates if x])}\n',
]


def boundaries(k: int) -> list[str]:
    return ["retrieve_sources"] + [f"transform_{i}" for i in range(1, k + 1)]

def source(k: int) -> str:
    parts = ['import json\n\ndef fetch(sid):\n    return CASSETTE[sid]\n\n',
             'def retrieve_sources():\n'
             '    ids = ["registry_alpha", "registry_beta", "registry_gamma",\n'
             '           "tracker_delta", "tracker_epsilon", "docs_zeta", "docs_eta"]\n'
             '    docs = [fetch(i) for i in ids]\n'
             '    return {"documents": docs, "source_ids": [d.get("id") for d in docs]}\n\n']
    for i in range(1, k + 1):
        body = TRANSFORM_BODIES[(i - 1) % len(TRANSFORM_BODIES)]
        parts.append(f'def transform_{i}(payload):\n{body}\n')
    parts.append("state = retrieve_sources()\n")
    for i in range(1, k + 1):
        parts.append(f"state = transform_{i}(state)\n")
    parts.append("print(json.dumps(state, sort_keys=True))\n")
    return "".join(parts)

def capture(k: int, cassette: dict[str, Any]) -> dict[str, Any]:
    src = source(k)
    tree = ast.parse(src)
    defs = [n for n in tree.body if isinstance(n, _DEFINITION_NODES)]
    rest = [n for n in tree.body if not isinstance(n, _DEFINITION_NODES)]
    ns: dict[str, Any] = {"__name__": "__p__", "CASSETTE": cassette}
    exec(compile(ast.Module(body=defs, type_ignores=[]), "p.py", "exec"), ns)
    out: dict[str, Any] = {}
    def wrap(name, fn):
        def rec(*a, **kw):
            v = fn(*a, **kw); out[name] = v; return v
        return rec
    for b in boundaries(k):
        if callable(ns.get(b)): ns[b] = wrap(b, ns[b])
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(ast.Module(body=rest, type_ignores=[]), "p.py", "exec"), ns)
    return out

def cases(k: int) -> list[tuple[str, str, dict]]:
    """Every mutation applied to every source, so n per chain length is 7x larger.

    Heterogeneous transforms are used as well, since identical stages give the model a
    contrast signal that real pipelines would not supply.
    """
    out = []
    for name, (prov, fn) in MUTATIONS.items():
        for sid in BASE_CASSETTE:
            c = copy.deepcopy(BASE_CASSETTE)
            before = copy.deepcopy(c[sid])
            fn(c[sid])
            if c[sid] == before: continue
            out.append((f"{name}|{sid}|k{k}", name, c))
    return out

INTENT_HEAD = "Fetch every source and return its documents and identifiers."
def intent(b: str) -> str:
    return INTENT_HEAD if b == "retrieve_sources" else (
        "Filter documents that have an identifier and recount the quotes.")
