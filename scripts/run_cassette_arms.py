#!/usr/bin/env python3
"""The context arms again, with the fault in the recorded data rather than the code.

The pipeline source is identical in every case, so the static-slice arm is
uninformative by construction. If it still scores well, something other than reading
the fault is driving these numbers.
"""
from __future__ import annotations
import ast, json, random, sys
from pathlib import Path
from use_case_icp import cassette_corpus as cc
from use_case_icp.fault_scoring import ContractDetector
from use_case_icp.selection import select_causal_root
from use_case_icp.fault_injection import _dataflow_edges
from scripts.run_fault_benchmark import ask

ENDPOINT="http://localhost:8093"; MODEL="mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
OUT=Path("benchmark-results/cassette_arms.json")
HEAD=("You are diagnosing one run of an automated market-research pipeline. Exactly one "
      "stage produced a faulty result. Name that stage.\n\n")
TAIL='\n\nAnswer with JSON only:\n{"faulty_stage": "<one stage name>"}'

def stages(): return "Stages: "+", ".join(cc.BOUNDARIES)+"\n\n"
def dump(b,out,cap=700): return f"## {b}\n{json.dumps(out.get(b),default=str)[:cap]}\n"
def parse(t):
    a,b=t.find("{"),t.rfind("}")
    if a<0 or b<=a: return None
    try: v=str(json.loads(t[a:b+1]).get("faulty_stage","")).strip()
    except json.JSONDecodeError: return None
    return v if v in cc.BOUNDARIES else None

def region_of(labels):
    pipe=cc.build_pipeline()
    root=select_causal_root(pipe,cc.BOUNDARIES,labels)
    edges=_dataflow_edges(cc.PIPELINE_SOURCE)
    reg={root} if root else set()
    for p,c in edges:
        if p==root and c in cc.BOUNDARIES: reg.add(c)
    return reg or set(cc.BOUNDARIES)

def func_src(name):
    for n in ast.parse(cc.PIPELINE_SOURCE).body:
        if isinstance(n,(ast.FunctionDef,)) and n.name==name:
            return ast.get_source_segment(cc.PIPELINE_SOURCE,n) or ""
    return ""

def main()->int:
    det=ContractDetector(cc.CONTRACTS)
    corpus=cc.build_corpus()
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["arm"]) for r in ex["runs"]}
    print(f"{len(corpus)} cases x 5 arms",flush=True)
    for i,case in enumerate(corpus):
        out=cc.capture(case.cassette)
        labels=det.label(cc.BOUNDARIES,out)
        reg=region_of(labels)
        sel_body="".join(dump(b,out) for b in cc.BOUNDARIES if b in reg)
        budget=len(sel_body)
        rng=random.Random(hash(case.case_id)%10000)
        pool=list(cc.BOUNDARIES); rng.shuffle(pool)
        picked=[];size=0
        for b in pool:
            blk=dump(b,out)
            if size+len(blk)>budget and picked: break
            picked.append(b); size+=len(blk)
        arms={
         "semantic_only": "Stage purposes only:\n"+"".join(f"- {b}: {cc.INTENT[b]}\n" for b in cc.BOUNDARIES),
         "graph_full": "Every stage's captured value:\n"+"".join(dump(b,out) for b in cc.BOUNDARIES),
         "graph_selected": "Region the execution graph implicates:\n"+sel_body,
         "random_slice": "Randomly chosen stages, size-matched:\n"+"".join(dump(b,out) for b in cc.BOUNDARIES if b in picked),
         "static_slice": "Source of the implicated stages:\n"+"".join(f"## {b}\n{func_src(b)}\n" for b in cc.BOUNDARIES if b in reg),
        }
        for arm,body in arms.items():
            if (case.case_id,arm) in done: continue
            pr=HEAD+stages()+body+TAIL
            try: ans=parse(ask(ENDPOINT,MODEL,pr,timeout=300))
            except Exception as e: print("  err",type(e).__name__,flush=True); ans=None
            ex["runs"].append({"case_id":case.case_id,"mutation":case.mutation,
                "provenance":case.provenance,"true_boundary":case.boundary,"arm":arm,
                "answer":ans,"correct":ans==case.boundary,"prompt_chars":len(pr)})
            OUT.write_text(json.dumps(ex,indent=2))
        if i%10==0: print(f"  case {i}/{len(corpus)}",flush=True)
    return 0

if __name__=="__main__": sys.exit(main())
