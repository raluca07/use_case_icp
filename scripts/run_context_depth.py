#!/usr/bin/env python3
"""Localisation accuracy against accumulated context depth, across four regimes.

The hypothesis under test is not that focused context beats unfocused context flatly.
It is that the gap grows with accumulated history: near zero on a short trajectory,
widening as prior iterations pile up. A single-depth experiment measures the left end
of that curve, where no difference is predicted, so depth is swept here.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from use_case_icp import branching_corpus as bc
from use_case_icp.fault_injection import FAULT_CATALOGUE, inject, _dataflow_edges, _entry_source
from use_case_icp.fault_scoring import ContractDetector, capture_stage_outputs
from use_case_icp.selection import select_causal_root
from scripts.run_fault_benchmark import ask
from scripts.run_judge_branching import INTENT
from scripts.run_selection_benchmark import PARAMETERS

ENDPOINT="http://localhost:8093"; MODEL="mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
DEPTHS=[16,32,64]; ARMS=["semantic_only","history_full","graph_full","graph_selected"]
N_CASES=20
OUT=Path("benchmark-results/context_depth_deep.json")

HEAD=("You are diagnosing one run of an automated market-research pipeline. Exactly one "
      "stage of the CURRENT run produced a faulty result. Name that stage.\n\n")
TAIL=('\n\nAnswer with JSON only:\n{"faulty_stage": "<one stage name>"}')

def stages(): return "Stages: " + ", ".join(bc.BOUNDARIES) + "\n\n"

def dump(b, out, cap=700):
    return f"## {b}\n{json.dumps(out.get(b), default=str)[:cap]}\n"

def history_block(clean, depth):
    if depth == 0: return ""
    parts=[f"### prior iteration {i+1}\n" + "".join(dump(b, clean) for b in bc.BOUNDARIES)
           for i in range(depth)]
    return "Accumulated history from earlier iterations:\n" + "".join(parts) + "\n"

def build(arm, outputs, clean, pipeline, labels, depth):
    if arm=="semantic_only":
        body="Stage purposes only, no captured values:\n" + "".join(
            f"- {b}: {INTENT[b]}\n" for b in bc.BOUNDARIES)
    elif arm=="history_full":
        body=history_block(clean,depth) + "Current run, every stage:\n" + "".join(
            dump(b,outputs) for b in bc.BOUNDARIES)
    elif arm=="graph_full":
        body="Current run, every stage:\n" + "".join(dump(b,outputs) for b in bc.BOUNDARIES)
    else:
        root=select_causal_root(pipeline,bc.BOUNDARIES,labels)
        edges=_dataflow_edges(_entry_source(pipeline))
        region={root} if root else set()
        for p,c in edges:
            if p==root and c in bc.BOUNDARIES: region.add(c)
        if not region: region=set(bc.BOUNDARIES)
        body=("Region the execution graph selected as causally implicated:\n" + "".join(
            dump(b,outputs) for b in bc.BOUNDARIES if b in region))
    return HEAD+stages()+body+TAIL

def parse(t):
    a,b=t.find("{"),t.rfind("}")
    if a<0 or b<=a: return None
    try: v=str(json.loads(t[a:b+1]).get("faulty_stage","")).strip()
    except json.JSONDecodeError: return None
    return v if v in bc.BOUNDARIES else None

def main()->int:
    det=ContractDetector(bc.CONTRACTS)
    clean=capture_stage_outputs(bc.build_pipeline(),bc.BOUNDARIES)
    allc=[]
    for fn,f in FAULT_CATALOGUE.items():
        for b in bc.BOUNDARIES:
            for p in PARAMETERS.get(fn,[""]):
                try: allc.append((f"{fn}|{b}|{p or 'default'}",b,inject(bc.build_pipeline(),f,target=b,parameter=p)))
                except ValueError: pass
    cases=allc[::max(1,len(allc)//N_CASES)][:N_CASES]
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["arm"],r["depth"]) for r in ex["runs"]}
    total=len(cases)*len(ARMS)*len(DEPTHS); n=0
    print(f"{len(cases)} cases x {len(ARMS)} arms x {len(DEPTHS)} depths = {total}",flush=True)
    for cid,truth,inj in cases:
        try: out=capture_stage_outputs(inj.pipeline,bc.BOUNDARIES)
        except Exception: continue
        labels=det.label(bc.BOUNDARIES,out)
        for depth in DEPTHS:
            for arm in ARMS:
                n+=1
                if (cid,arm,depth) in done: continue
                pr=build(arm,out,clean,inj.pipeline,labels,depth)
                try: ans=parse(ask(ENDPOINT,MODEL,pr,timeout=300))
                except Exception as e: print("  err",type(e).__name__,flush=True); ans=None
                ex["runs"].append({"case_id":cid,"true_boundary":truth,"arm":arm,"depth":depth,
                    "answer":ans,"correct":ans==truth,"prompt_chars":len(pr)})
                OUT.write_text(json.dumps(ex,indent=2))
            if n%40==0: print(f"  {n}/{total}",flush=True)
    return 0

if __name__=="__main__": sys.exit(main())
