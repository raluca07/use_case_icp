#!/usr/bin/env python3
"""Two controls the first design was missing.

random_slice: a budget-matched random subset of boundaries. Without it, a drop from
graph_full to graph_selected cannot be attributed to selection rather than to simply
showing less. This is the control that makes the selection arm interpretable.

static_slice: the source text of the causal region instead of its captured values.
Isolates whether runtime evidence matters or structural knowledge would do.
"""
from __future__ import annotations
import ast, json, random, sys
from pathlib import Path
from use_case_icp import branching_corpus as bc
from use_case_icp.fault_injection import FAULT_CATALOGUE, inject, _dataflow_edges, _entry_source
from use_case_icp.fault_scoring import ContractDetector, capture_stage_outputs
from use_case_icp.selection import select_causal_root
from scripts.run_fault_benchmark import ask
from scripts.run_judge_branching import INTENT
from scripts.run_selection_benchmark import PARAMETERS
from scripts.run_context_depth import HEAD, TAIL, stages, dump, parse, N_CASES

ENDPOINT="http://localhost:8093"; MODEL="mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
OUT=Path("benchmark-results/ablation_controls.json")
SEEDS=[1,2,3]

def selected_region(pipeline, labels):
    root=select_causal_root(pipeline,bc.BOUNDARIES,labels)
    edges=_dataflow_edges(_entry_source(pipeline))
    region={root} if root else set()
    for p,c in edges:
        if p==root and c in bc.BOUNDARIES: region.add(c)
    return region or set(bc.BOUNDARIES)

def func_source(pipeline,name):
    src=_entry_source(pipeline)
    for n in ast.parse(src).body:
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name:
            return ast.get_source_segment(src,n) or ""
    return ""

def main()->int:
    det=ContractDetector(bc.CONTRACTS)
    allc=[]
    for fn,f in FAULT_CATALOGUE.items():
        for b in bc.BOUNDARIES:
            for p in PARAMETERS.get(fn,[""]):
                try: allc.append((f"{fn}|{b}|{p or 'default'}",b,inject(bc.build_pipeline(),f,target=b,parameter=p)))
                except ValueError: pass
    cases=allc[::max(1,len(allc)//N_CASES)][:N_CASES]
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["arm"],r["seed"]) for r in ex["runs"]}
    print(f"{len(cases)} cases",flush=True)
    for cid,truth,inj in cases:
        try: out=capture_stage_outputs(inj.pipeline,bc.BOUNDARIES)
        except Exception: continue
        labels=det.label(bc.BOUNDARIES,out)
        region=selected_region(inj.pipeline,labels)
        budget=len("".join(dump(b,out) for b in bc.BOUNDARIES if b in region))
        # static slice: same region, source text not values
        static_body="Source of the stages the graph implicates:\n"+"".join(
            f"## {b}\n{func_source(inj.pipeline,b)}\n" for b in bc.BOUNDARIES if b in region)
        jobs=[("static_slice",0,HEAD+stages()+static_body+TAIL)]
        for seed in SEEDS:
            rng=random.Random(seed+hash(cid)%1000)
            pool=list(bc.BOUNDARIES); rng.shuffle(pool)
            picked=[]; size=0
            for b in pool:
                blk=dump(b,out)
                if size+len(blk)>budget and picked: break
                picked.append(b); size+=len(blk)
            body="Randomly chosen stages, matched to the selected region's size:\n"+"".join(
                dump(b,out) for b in bc.BOUNDARIES if b in picked)
            jobs.append(("random_slice",seed,HEAD+stages()+body+TAIL))
        for arm,seed,prompt in jobs:
            if (cid,arm,seed) in done: continue
            try: ans=parse(ask(ENDPOINT,MODEL,prompt,timeout=300))
            except Exception as e: print("  err",type(e).__name__,flush=True); ans=None
            ex["runs"].append({"case_id":cid,"true_boundary":truth,"arm":arm,"seed":seed,
                "answer":ans,"correct":ans==truth,"prompt_chars":len(prompt)})
            OUT.write_text(json.dumps(ex,indent=2))
    return 0

if __name__=="__main__": sys.exit(main())
