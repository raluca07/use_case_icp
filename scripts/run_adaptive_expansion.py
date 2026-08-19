#!/usr/bin/env python3
"""The arm the real system actually has: a selected region plus expansion on request.

Every earlier negative about selection compared against a fixed region, which is weaker
than the deployed method. Here the model sees the causally selected region and may request
specific additional stages once before answering.
"""
from __future__ import annotations
import json, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from use_case_icp import cassette_corpus as cc
from use_case_icp.fault_scoring import ContractDetector
from use_case_icp.selection import select_causal_root
from use_case_icp.fault_injection import _dataflow_edges

OUT=Path("benchmark-results/adaptive_expansion.json")
MODEL="haiku"
def dump(b,out): return f"## {b}\n{json.dumps(out.get(b),default=str)[:600]}\n"
def ask(p):
    r=subprocess.run(["claude","-p","--model",MODEL],input=p,capture_output=True,text=True,timeout=240)
    return r.stdout
def clean_json(t):
    t=re.sub(r"```(?:json)?|```","",t)
    a,b=t.find("{"),t.rfind("}")
    if a<0 or b<=a: return None
    try: return json.loads(t[a:b+1])
    except json.JSONDecodeError: return None

def region_of(out):
    det=ContractDetector(cc.CONTRACTS)
    labels=det.label(cc.BOUNDARIES,out)
    pipe=cc.build_pipeline()
    root=select_causal_root(pipe,cc.BOUNDARIES,labels)
    edges=_dataflow_edges(cc.PIPELINE_SOURCE)
    reg={root} if root else set()
    for p,c in edges:
        if p==root and c in cc.BOUNDARIES: reg.add(c)
    return reg or set(cc.BOUNDARIES)

HEAD=("You are diagnosing one run of an automated market-research pipeline. Exactly one "
      "stage produced a faulty result. Name the stage where the fault ORIGINATED.\n\n"
      "Stages: "+", ".join(cc.BOUNDARIES)+"\n\n")

lock=threading.Lock()
def run_one(case, ex):
    out=cc.capture(case.cassette)
    reg=region_of(out)
    results={}
    for arm in ("graph_selected","graph_full","graph_adaptive"):
        shown=sorted(reg, key=cc.BOUNDARIES.index) if arm!="graph_full" else list(cc.BOUNDARIES)
        body="".join(dump(b,out) for b in shown)
        expanded=[]
        if arm=="graph_adaptive":
            p1=(HEAD+"Captured values for the region the execution graph implicates:\n"+body+
                '\nYou may first request other stages\' captured values. JSON only, one of:\n'
                '{"expand": ["<stage>", ...]}  or  {"faulty_stage": "<stage>"}')
            j=clean_json(ask(p1)) or {}
            if isinstance(j.get("expand"),list):
                expanded=[s for s in j["expand"] if s in cc.BOUNDARIES][:4]
                body+="".join(dump(b,out) for b in expanded if b not in shown)
            elif j.get("faulty_stage") in cc.BOUNDARIES:
                results[arm]={"answer":j["faulty_stage"],"expanded":[]}
                continue
        p=(HEAD+"Captured values:\n"+body+'\n\nJSON only:\n{"faulty_stage": "<stage>"}')
        j=clean_json(ask(p)) or {}
        ans=j.get("faulty_stage")
        results[arm]={"answer":ans if ans in cc.BOUNDARIES else None,"expanded":expanded}
    with lock:
        for arm,res in results.items():
            ex["runs"].append({"case_id":case.case_id,"mutation":case.mutation,
                "truth":case.boundary,"arm":arm,"answer":res["answer"],
                "correct":res["answer"]==case.boundary,"expanded":res["expanded"]})
        OUT.write_text(json.dumps(ex,indent=2))

def main():
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["arm"]) for r in ex["runs"]}
    todo=[c for c in cc.build_corpus() if (c.case_id,"graph_adaptive") not in done]
    print(f"{len(todo)} cases x 3 arms",flush=True)
    with ThreadPoolExecutor(4) as pool:
        for c in todo: pool.submit(run_one,c,ex)
    return 0

if __name__=="__main__": sys.exit(main())
