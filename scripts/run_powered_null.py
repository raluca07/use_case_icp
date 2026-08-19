#!/usr/bin/env python3
"""Power the selection-versus-random-slice comparison properly.

The earlier null could only have detected a 35-point effect. This targets roughly 350
cases per arm: every mutation on every single source, plus every mutation on within-class
source pairs, which keeps ground truth a single boundary while multiplying cases.
"""
from __future__ import annotations
import copy, json, random, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from use_case_icp import cassette_corpus as cc
from use_case_icp.fault_scoring import ContractDetector
from use_case_icp.selection import select_causal_root
from use_case_icp.fault_injection import _dataflow_edges
from itertools import combinations

OUT=Path("benchmark-results/powered_null.json"); MODEL="haiku"
def dump(b,out): return f"## {b}\n{json.dumps(out.get(b),default=str)[:600]}\n"
def ask(p):
    r=subprocess.run(["claude","-p","--model",MODEL],input=p,capture_output=True,text=True,timeout=240)
    return r.stdout
def parse(t):
    t=re.sub(r"```(?:json)?|```","",t); a,b=t.find("{"),t.rfind("}")
    if a<0 or b<=a: return None
    try: v=str(json.loads(t[a:b+1]).get("faulty_stage","")).strip()
    except json.JSONDecodeError: return None
    return v if v in cc.BOUNDARIES else None

def build_cases():
    cases=[]
    by_class={}
    for sid,owner in cc.SOURCE_OWNER.items(): by_class.setdefault(owner,[]).append(sid)
    targets=[(sid,) for sid in cc.SOURCE_OWNER]
    for owner,sids in by_class.items():
        targets+=list(combinations(sids,2))
    for mut,(prov,fn) in cc.MUTATIONS.items():
        for tgt in targets:
            cas=copy.deepcopy(cc.BASE_CASSETTE); changed=False
            for sid in tgt:
                before=copy.deepcopy(cas[sid]); fn(cas[sid])
                changed = changed or cas[sid]!=before
            if not changed: continue
            owner=cc.SOURCE_OWNER[tgt[0]]
            cases.append({"case_id":f"{mut}|{'+'.join(tgt)}","mutation":mut,
                          "boundary":owner,"cassette":cas})
    return cases

HEAD=("You are diagnosing one run of an automated market-research pipeline. Exactly one "
      "stage produced a faulty result. Name the stage where the fault ORIGINATED.\n\n"
      "Stages: "+", ".join(cc.BOUNDARIES)+"\n\n")
lock=threading.Lock()

def run_one(case, ex):
    out=cc.capture(case["cassette"])
    det=ContractDetector(cc.CONTRACTS)
    labels=det.label(cc.BOUNDARIES,out)
    pipe=cc.build_pipeline()
    root=select_causal_root(pipe,cc.BOUNDARIES,labels)
    edges=_dataflow_edges(cc.PIPELINE_SOURCE)
    reg={root} if root else set()
    for p_,c_ in edges:
        if p_==root and c_ in cc.BOUNDARIES: reg.add(c_)
    reg=reg or set(cc.BOUNDARIES)
    sel_body="".join(dump(b,out) for b in cc.BOUNDARIES if b in reg)
    budget=len(sel_body)
    rng=random.Random(hash(case["case_id"])%100000)
    pool=list(cc.BOUNDARIES); rng.shuffle(pool)
    picked=[];size=0
    for b in pool:
        blk=dump(b,out)
        if size+len(blk)>budget and picked: break
        picked.append(b); size+=len(blk)
    arms={"graph_selected":"Region the execution graph implicates:\n"+sel_body,
          "random_slice":"Randomly chosen stages, size-matched:\n"+"".join(dump(b,out) for b in cc.BOUNDARIES if b in picked)}
    for arm,body in arms.items():
        try: ans=parse(ask(HEAD+body+'\n\nJSON only:\n{"faulty_stage": "<stage>"}'))
        except Exception as e: ans=None; print("err",type(e).__name__,flush=True)
        with lock:
            ex["runs"].append({"case_id":case["case_id"],"mutation":case["mutation"],
                "truth":case["boundary"],"arm":arm,"answer":ans,"correct":ans==case["boundary"]})
            OUT.write_text(json.dumps(ex,indent=2))

def main():
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"]) for r in ex["runs"] if True}
    seen={}
    for r in ex["runs"]: seen.setdefault(r["case_id"],set()).add(r["arm"])
    todo=[c for c in build_cases() if len(seen.get(c["case_id"],()))<2]
    print(f"{len(todo)} cases x 2 arms",flush=True)
    with ThreadPoolExecutor(6) as pool:
        for c in todo: pool.submit(run_one,c,ex)
    return 0

if __name__=="__main__": sys.exit(main())
