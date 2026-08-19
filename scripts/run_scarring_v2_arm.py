#!/usr/bin/env python3
"""Population-mined scarring, with trust propagation and repair gating.

Healthy runs vary legitimately here, which is the condition single-pair minting cannot
survive. Faults are injected into a member of the healthy population, so what is mined is
the fault and not the difference between two generative processes.
"""
from __future__ import annotations
import copy, json
from collections import Counter
from pathlib import Path
from use_case_icp import cassette_corpus as cc
from use_case_icp.fault_scoring import ContractDetector
from use_case_icp.scarring import (
    CONTAMINATED, ScarDetector, healthy_variants, mint_from_population, mint_scar,
    propagate_trust,
)

POP_N = 8

def main() -> int:
    pipe = cc.build_pipeline()
    pop = healthy_variants(POP_N)
    healthy_caps = [cc.capture(c) for c in pop]
    contract = ContractDetector(cc.CONTRACTS)

    cases = []
    for mut in cc.MUTATIONS:
        for sid, owner in cc.SOURCE_OWNER.items():
            cas = copy.deepcopy(pop[0])
            before = copy.deepcopy(cas[sid])
            cc.MUTATIONS[mut][1](cas[sid])
            if cas[sid] == before: continue
            cases.append((f"{mut}|{sid}", mut, owner, cc.capture(cas)))
    n = len(cases)

    def declared(outs, b): return contract.label(cc.BOUNDARIES, outs, )[b] == "suspect"

    results = {}
    for label, pop_size in (("population n=1", 1), ("population n=4", 4), ("population n=8", POP_N)):
        scars, refused, rows = [], 0, []
        for epoch in (1, 2):
            caught = scar_only = 0
            for cid, mut, b, outs in cases:
                by_decl = contract.label(cc.BOUNDARIES, outs)[b] == "suspect"
                by_scar = ScarDetector(scars).label(cc.BOUNDARIES, outs, pipe)[b] == "suspect"
                if by_decl or by_scar: caught += 1
                if by_scar and not by_decl: scar_only += 1
                if epoch == 1 and not by_decl:
                    try:
                        # Same feature extractor throughout, so the only variable is how
                        # many healthy observations the invariant had to survive.
                        scars.append(mint_from_population(
                            boundary=b, pipeline=pipe,
                            healthy_values=[h[b] for h in healthy_caps[:pop_size]],
                            faulty_value=outs[b], provenance=cid))
                    except ValueError:
                        refused += 1
            rows.append((epoch, caught, scar_only))
        # false suspicion across the whole healthy population
        det = ScarDetector(scars)
        fp = sum(1 for h in healthy_caps
                 for v in det.label(cc.BOUNDARIES, h, pipe).values() if v == "suspect")
        results[label] = {"rows": rows, "scars": len(scars), "refused": refused,
                          "false_suspicion": fp, "healthy_checked": len(healthy_caps)*len(cc.BOUNDARIES),
                          "kinds": dict(Counter(k["kind"] for s in scars for k in s.checks))}

    print(f"corpus: {n} faults, healthy population: {POP_N} legitimately varying runs\n")
    for label, r in results.items():
        e1, e2 = r["rows"][0], r["rows"][1]
        print(f"  {label:12} epoch1 {e1[1]}/{n} = {e1[1]/n:.0%}   epoch2 {e2[1]}/{n} = {e2[1]/n:.0%}"
              f"   scars {r['scars']}  refused {r['refused']}")
        print(f"  {'':12} FALSE SUSPICION across healthy population: "
              f"{r['false_suspicion']}/{r['healthy_checked']}")
        print(f"  {'':12} kinds {r['kinds']}\n")

    # propagation: over every case the declared checks actually flag
    flagged = [(cid, b, outs) for cid, mut, b, outs in cases
               if any(v == "suspect" for v in contract.label(cc.BOUNDARIES, outs).values())]
    reclass = spurious = 0
    for cid, b, outs in flagged:
        raw = contract.label(cc.BOUNDARIES, outs)
        prop = propagate_trust(pipe, cc.BOUNDARIES, raw)
        reclass += sum(1 for v in prop.values() if v == CONTAMINATED)
        # a boundary the raw labels called suspect but that is only downstream of the fault
        spurious += sum(1 for x in cc.BOUNDARIES
                        if raw[x] == "suspect" and x != b and prop[x] == CONTAMINATED)
    print(f"  propagation over {len(flagged)} flagged cases: {reclass} boundary-labels "
          f"reclassified from independently suspect to contaminated")

    # gating: does a repair have to clear the scar that caught it?
    scars = []
    for cid, mut, b, outs in cases:
        if contract.label(cc.BOUNDARIES, outs)[b] == "suspect": continue
        try:
            scars.append((cid, b, mint_from_population(
                boundary=b, pipeline=pipe, healthy_values=[h[b] for h in healthy_caps],
                faulty_value=outs[b], provenance=cid)))
        except ValueError: pass
    cleared = sum(1 for _, b, s in scars if s.clears(healthy_caps[1][b])[0])
    blocked = sum(1 for (cid, b, s), (_, _, outs) in
                  zip(scars, [(c[0], c[2], c[3]) for c in cases[:len(scars)]])
                  if not s.clears(outs[b])[0])
    print(f"  gating: {cleared}/{len(scars)} scars cleared by a genuine repair; "
          f"{blocked} would block a non-repair")

    Path("benchmark-results/scarring_v2.json").write_text(json.dumps(
        {"n": n, "population": POP_N, "results": results}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
