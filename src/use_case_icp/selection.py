"""Repair-target selectors, scored against the boundary a fault was injected into.

The published comparison's graph arms filter failed units to causal roots using
upstream identifiers; its baseline arms rotate over failed units with no causal step.
That difference is the thing an execution graph actually buys, so it is measured here
as the treatment rather than controlled away as a nuisance.
"""

from __future__ import annotations

from .fault_injection import _dataflow_edges, _entry_source
from .records import GeneratedPipeline

SUSPECT = "suspect"


def flagged_boundaries(boundaries: list[str], labels: dict[str, str]) -> list[str]:
    return [name for name in boundaries if labels.get(name) == SUSPECT]


def select_source_order(
    pipeline: GeneratedPipeline,
    boundaries: list[str],
    labels: dict[str, str],
) -> str | None:
    """Baseline: the first flagged boundary in the order the source declares them.

    Needs no graph. This is what rotation reduces to on a first repair attempt.
    """
    flagged = flagged_boundaries(boundaries, labels)
    return flagged[0] if flagged else None


def select_causal_root(
    pipeline: GeneratedPipeline,
    boundaries: list[str],
    labels: dict[str, str],
) -> str | None:
    """Graph selector: a flagged boundary with no flagged boundary upstream of it.

    Ties are broken by declaration order so the selector stays deterministic.
    """
    flagged = flagged_boundaries(boundaries, labels)
    if not flagged:
        return None
    edges = _dataflow_edges(_entry_source(pipeline))
    upstream: dict[str, set[str]] = {name: set() for name in boundaries}
    changed = True
    while changed:
        changed = False
        for producer, consumer in edges:
            if consumer not in upstream:
                continue
            new = {producer} | upstream.get(producer, set())
            if not new <= upstream[consumer]:
                upstream[consumer] |= new
                changed = True
    roots = [name for name in flagged if not (upstream[name] & set(flagged))]
    return (roots or flagged)[0]


SELECTORS = {
    "source_order": select_source_order,
    "causal_root": select_causal_root,
}
