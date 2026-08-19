#!/usr/bin/env python3
"""Raluca's etiq_selected protocol, implemented as described, against two baselines.

The initial package carries nodes at exactly the boundary's stack level and names its
nested helpers without their contents. The reviewer may request one direct child at a
time, for at most three rounds. The comparison is against sending everything flattened,
and against a random subset matched to the collapsed package's size.
"""
from __future__ import annotations
import json, random, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from use_case_icp import nested_corpus as nc

OUT=Path("benchmark-results/collapsed_protocol.json"); MODEL="haiku"; ROUNDS=3
lock=threading.Lock()

def ask(p):
    r=subprocess.run(["claude","-p","--model",MODEL],input=p,capture_output=True,text=True,timeout=240)
    return r.stdout

def jparse(t):
    t=re.sub(r"```(?:json)?|```","",t); a,b=t.find("{"),t.rfind("}")
    if a<0 or b<=a: return None
    try: return json.loads(t[a:b+1])
    except json.JSONDecodeError: return None

HEAD=("You are reviewing one stage of a pipeline that researches demand for AI agent "
      "tooling. A clean run yields 12 evidence records from 6 sources, two quotes each, "
      "each attributed to its own source.\n\n")

def ask_verdict(pkg, boundary, may_expand):
    body=(f"Stage under review: {boundary}\n\n"
          f"Captured values at this stage:\n{json.dumps(pkg['visible'], indent=1, default=str)[:3000]}\n")
    if pkg["collapsed_helpers"]:
        body+=("\nNested helpers inside this stage, contents withheld:\n"
               +"".join(f"- {h}\n" for h in pkg["collapsed_helpers"]))
    if may_expand and pkg["collapsed_helpers"]:
        tail=('\n\nEither answer, or request ONE helper to expand. JSON only:\n'
              '{"verdict": "faulty"|"clean"} or {"expand": "<one helper name>"}')
    else:
        tail='\n\nJSON only:\n{"verdict": "faulty"|"clean"}'
    return jparse(ask(HEAD+body+tail)) or {}

def run_case(case, ex):
    fault, boundary, truth = case["fault"], case["boundary"], case["truth"]
    trace, children = nc.run(fault)
    results={}

    # A. collapsed + bounded expansion, her protocol
    expanded=[]; rounds=0; verdict=None
    for _ in range(ROUNDS):
        pkg=nc.package(trace, children, boundary, expanded)
        r=ask_verdict(pkg, boundary, may_expand=True)
        if isinstance(r.get("expand"), str) and r["expand"] in pkg["collapsed_helpers"]:
            expanded.append(r["expand"]); rounds+=1; continue
        verdict=r.get("verdict"); break
    if verdict is None:
        pkg=nc.package(trace, children, boundary, expanded)
        verdict=ask_verdict(pkg, boundary, may_expand=False).get("verdict")
    cost=len(json.dumps(nc.package(trace,children,boundary,expanded),default=str))
    results["collapsed_expand"]={"verdict":verdict,"rounds":rounds,"chars":cost}

    # B. everything flattened
    pf=nc.full_package(trace, boundary)
    results["flat_full"]={"verdict":ask_verdict(pf,boundary,False).get("verdict"),
                          "rounds":0,"chars":len(json.dumps(pf,default=str))}

    # C. random subset matched to the collapsed package's size
    keys=[k for k in trace if k==boundary or k.startswith(boundary+".")]
    rng=random.Random(hash(fault or "clean")%9999); rng.shuffle(keys)
    picked={}; size=0
    for k in keys:
        blob=len(json.dumps({k:trace[k]},default=str))
        if size+blob>cost and picked: break
        picked[k]=trace[k]; size+=blob
    pr={"visible":picked,"collapsed_helpers":[]}
    results["random_matched"]={"verdict":ask_verdict(pr,boundary,False).get("verdict"),
                               "rounds":0,"chars":len(json.dumps(pr,default=str))}

    with lock:
        for arm,r in results.items():
            ex["runs"].append({"case_id":case["case_id"],"fault":fault,"depth":case["depth"],
                "boundary":boundary,"truth":truth,"arm":arm,
                "verdict":r["verdict"],"correct":r["verdict"]==truth,
                "rounds":r["rounds"],"chars":r["chars"]})
            OUT.write_text(json.dumps(ex,indent=2))

def main():
    cases=[]
    for fault,spec in nc.FAULTS.items():
        cases.append({"case_id":f"fault|{fault}","fault":fault,"boundary":spec["boundary"],
                      "depth":spec["depth"],"truth":"faulty"})
    for b in nc.BOUNDARIES:                      # clean controls, one per boundary
        cases.append({"case_id":f"clean|{b}","fault":None,"boundary":b,
                      "depth":-1,"truth":"clean"})
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["arm"]) for r in ex["runs"]}
    todo=[c for c in cases if (c["case_id"],"collapsed_expand") not in done]
    print(f"{len(todo)} cases x 3 arms",flush=True)
    with ThreadPoolExecutor(4) as pool:
        for c in todo: pool.submit(run_case,c,ex)
    return 0

if __name__=="__main__": sys.exit(main())
