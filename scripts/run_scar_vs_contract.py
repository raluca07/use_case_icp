#!/usr/bin/env python3
"""Declared contracts against learned scars, on detection and on localisation.

Localisation is the part that matters: a signal that fires downstream of the fault has
detected something and told you the wrong place to repair, which is the failure the model
judges showed. Contracts are written where an author thought to write them; scars are
placed where faults were actually observed to enter.
"""
from __future__ import annotations
import copy, json
from collections import Counter
from pathlib import Path
from use_case_icp import cassette_corpus as cc
from use_case_icp.fault_scoring import ContractDetector
from use_case_icp.scarring import ScarDetector, healthy_variants, mint_from_population

POP = 8

def main() -> int:
    pipe = cc.build_pipeline()
    pop = healthy_variants(POP + 4)
    train, held_out = pop[:POP], pop[POP:]
    caps = [cc.capture(c) for c in train]
    contract = ContractDetector(cc.CONTRACTS)

    cases = []
    for mut in cc.MUTATIONS:
        for sid, owner in cc.SOURCE_OWNER.items():
            cas = copy.deepcopy(train[0])
            before = copy.deepcopy(cas[sid])
            cc.MUTATIONS[mut][1](cas[sid])
            if cas[sid] == before: continue
            cases.append((f"{mut}|{sid}", mut, owner, cc.capture(cas)))
    n = len(cases)

    # Train scars on epoch one: every fault the contracts miss becomes a scar.
    scars = []
    for cid, mut, owner, outs in cases:
        if contract.label(cc.BOUNDARIES, outs)[owner] == "suspect":
            continue
        try:
            scars.append(mint_from_population(
                boundary=owner, pipeline=pipe,
                healthy_values=[c[owner] for c in caps],
                faulty_value=outs[owner], provenance=cid))
        except ValueError:
            pass
    scar_det = ScarDetector(scars)

    def score(labeller):
        detected = localised = misplaced = 0
        for cid, mut, owner, outs in cases:
            labels = labeller(outs)
            flagged = [b for b in cc.BOUNDARIES if labels.get(b) == "suspect"]
            if flagged: detected += 1
            if owner in flagged: localised += 1
            elif flagged: misplaced += 1
        return detected, localised, misplaced

    c_det, c_loc, c_mis = score(lambda o: contract.label(cc.BOUNDARIES, o))
    s_det, s_loc, s_mis = score(lambda o: scar_det.label(cc.BOUNDARIES, o, pipe))
    both = score(lambda o: {b: ("suspect" if contract.label(cc.BOUNDARIES, o)[b] == "suspect"
                                or scar_det.label(cc.BOUNDARIES, o, pipe)[b] == "suspect"
                                else "trusted") for b in cc.BOUNDARIES})

    print(f"corpus {n} faults, scars trained on contract misses, population {POP}\n")
    print(f"{'signal':22}{'detected':>10}{'localised':>11}{'misplaced':>11}")
    for name, (d, l, m) in (("declared contracts", (c_det, c_loc, c_mis)),
                            ("learned scars", (s_det, s_loc, s_mis)),
                            ("both", both)):
        print(f"{name:22}{d}/{n:<6}{l}/{n:<7}{m}/{n}")

    # false suspicion on held-out healthy runs the scars never saw
    fp = sum(1 for c in held_out
             for v in scar_det.label(cc.BOUNDARIES, cc.capture(c), pipe).values() if v == "suspect")
    print(f"\nfalse suspicion on {len(held_out)} HELD-OUT healthy runs: "
          f"{fp}/{len(held_out)*len(cc.BOUNDARIES)}")
    print(f"scars held: {len(scars)}  check kinds: {dict(Counter(k['kind'] for s in scars for k in s.checks))}")
    Path("benchmark-results/scar_vs_contract.json").write_text(json.dumps(
        {"n": n, "population": POP,
         "contracts": {"detected": c_det, "localised": c_loc, "misplaced": c_mis},
         "scars": {"detected": s_det, "localised": s_loc, "misplaced": s_mis},
         "both": {"detected": both[0], "localised": both[1], "misplaced": both[2]},
         "held_out_false_suspicion": fp, "scars": len(scars)}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
