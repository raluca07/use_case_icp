#!/usr/bin/env python3
"""Scarring as an arm: does a learned deterministic check ratchet the detection floor?

Streams every corpus case twice. On first exposure, any fault the declared signals miss
is assumed caught by something expensive (a model judge, or a run that failed loudly) and
distilled into a scar. On second exposure the scar is free. Reports the ratchet, the
false-suspicion cost, and what remains unlearnable.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from use_case_icp.fault_corpus import BOUNDARIES, CONTRACTS, SCHEMAS, build_corpus, build_pipeline
from use_case_icp.fault_scoring import ContractDetector, SchemaDetector, capture_stage_outputs
from use_case_icp.scarring import ScarDetector, mint_scar

def main() -> int:
    pipe = build_pipeline()
    clean = capture_stage_outputs(pipe, BOUNDARIES)
    corpus = build_corpus()
    schema, contract = SchemaDetector(SCHEMAS), ContractDetector(CONTRACTS)
    judge = {}
    for v in json.load(open("benchmark-results/judge.json"))["verdicts"]:
        if v["verdict"]: judge.setdefault(v["case_id"], []).append(v["verdict"])
    maj = {k: (vs.count("suspect") > len(vs) / 2) for k, vs in judge.items()}

    cases = []
    for c in corpus:
        try: cases.append((c, capture_stage_outputs(c.injected.pipeline, BOUNDARIES)))
        except Exception: pass

    def declared(c, outs):
        b = c.boundary
        return schema.label(BOUNDARIES, outs)[b] == "suspect" or \
               contract.label(BOUNDARIES, outs)[b] == "suspect"

    scars, refused, rows = [], 0, []
    for epoch in (1, 2):
        caught = scar_only = 0
        for c, outs in cases:
            b = c.boundary
            by_scar = ScarDetector(scars).label(BOUNDARIES, outs, pipe)[b] == "suspect"
            by_decl = declared(c, outs)
            if by_scar or by_decl: caught += 1
            if by_scar and not by_decl: scar_only += 1
            if epoch == 1 and not by_decl:
                try:
                    scars.append(mint_scar(boundary=b, pipeline=pipe, clean_value=clean[b],
                                           faulty_value=outs[b], provenance=c.case_id))
                except ValueError:
                    refused += 1
        rows.append((epoch, caught, scar_only, len(scars)))

    n = len(cases)
    print(f"corpus: {n} silent faults\n")
    for epoch, caught, scar_only, ns in rows:
        print(f"  epoch {epoch}: caught {caught}/{n} = {caught/n:.0%}"
              f"   (scar-only {scar_only})   scars held {ns}")
    print(f"  scars refused as inexpressible: {refused}")
    lab = ScarDetector(scars).label(BOUNDARIES, clean, pipe)
    print(f"  false suspicion on the clean run: {sum(1 for v in lab.values() if v=='suspect')}/{len(BOUNDARIES)}")

    sd = ScarDetector(scars)
    hard = [(c, o) for c, o in cases if not declared(c, o) and not maj.get(c.case_id, False)]
    rescued = [(c, o) for c, o in hard if sd.label(BOUNDARIES, o, pipe)[c.boundary] == "suspect"]
    print(f"\n  hard core (missed by schema, invariants AND judge): {len(hard)}")
    print(f"  of those, caught by a scar on recurrence: {len(rescued)}")
    print(f"  remaining unlearnable: {dict(Counter(c.fault_name for c, _ in hard if (c, _) not in rescued))}")
    kinds = Counter(k["kind"] for s in scars for k in s.checks)
    print(f"\n  check kinds minted: {dict(kinds)}")
    Path("benchmark-results/scarring.json").write_text(json.dumps(
        {"epochs": rows, "refused": refused, "n": n,
         "hard_core": len(hard), "rescued": len(rescued),
         "check_kinds": dict(kinds)}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
