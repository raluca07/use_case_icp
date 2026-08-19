#!/usr/bin/env python3
"""Does causal-root selection beat a source-order baseline across pipeline shapes?"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from use_case_icp import topologies as tp
from use_case_icp.fault_injection import FAULT_CATALOGUE, inject
from use_case_icp.fault_scoring import ContractDetector, capture_stage_outputs
from use_case_icp.selection import SELECTORS

rows=[]
import random
for topo in tp.TOPOLOGIES:
  for order in ("dataflow", "scrambled"):
    pipe, names = tp.build(topo)
    if order == "scrambled":
        # Declaration order shuffled away from execution order, which is what a model
        # writing code actually produces. The boundary list is what a selector without
        # a graph must walk.
        names = list(names); random.Random(7).shuffle(names)
        pipe.review_boundaries = [{"function_name": n} for n in names]
    det = ContractDetector(tp.contracts(names))
    for fname, fault in FAULT_CATALOGUE.items():
        for b in names:
            for param in (["items","n","tag"] if fname=="drop_field" else [""]):
                try: inj = inject(pipe, fault, target=b, parameter=param)
                except ValueError: continue
                try: out = capture_stage_outputs(inj.pipeline, names)
                except Exception: continue
                labels = det.label(names, out)
                flagged = [n for n in names if labels.get(n)=="suspect"]
                picks = {s: sel(inj.pipeline, names, labels) for s, sel in SELECTORS.items()}
                rows.append({"topology":topo,"order":order,"fault":fname,"boundary":b,"param":param,
                    "n_flagged":len(flagged),
                    **{f"{s}_correct": picks[s]==b for s in picks}})
Path("benchmark-results/topology_selection.json").write_text(json.dumps({"rows":rows},indent=2))
print(f"{'topology':12}{'order':11}{'contested':>10}{'causal':>9}{'source':>9}")
for t in tp.TOPOLOGIES:
    for o in ("dataflow","scrambled"):
        con=[r for r in rows if r["topology"]==t and r["order"]==o and r["n_flagged"]>1]
        if not con: continue
        c=sum(r["causal_root_correct"] for r in con); s2=sum(r["source_order_correct"] for r in con)
        print(f"{t:12}{o:11}{len(con):>10}{c/len(con):>9.0%}{s2/len(con):>9.0%}")
for o in ("dataflow","scrambled"):
    con=[r for r in rows if r["order"]==o and r["n_flagged"]>1]
    c=sum(r["causal_root_correct"] for r in con); s2=sum(r["source_order_correct"] for r in con)
    print(f"\nALL {o:10} contested n={len(con)}: causal {c}/{len(con)} ({c/len(con):.0%})  source {s2}/{len(con)} ({s2/len(con):.0%})")
