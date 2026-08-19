#!/usr/bin/env python3
"""The fault class no structural check can express: right shape, wrong sense.

Every quote is the right count, the right type, attached to the right identifier and
dated correctly; the words are ordinary and plausible; only the sense is wrong, an
insurance agent where a software agent was meant. Deterministic signals are blind to this
by construction, and scar minting refuses it, so it is the case where a model judge has to
earn its cost or nothing detects it at all.
"""
from __future__ import annotations
import copy, json, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from use_case_icp import cassette_corpus as cc

OUT=Path("benchmark-results/wrong_sense.json"); MODEL="haiku"
INTENT=cc.INTENT

def dump(b,out,cap=900): return f"## {b}\n{json.dumps(out.get(b),default=str)[:cap]}\n"
def ask(p):
    r=subprocess.run(["claude","-p","--model",MODEL],input=p,capture_output=True,text=True,timeout=240)
    return r.stdout
def parse(t):
    t=re.sub(r"```(?:json)?|```","",t); a,b=t.find("{"),t.rfind("}")
    if a<0 or b<=a: return None
    try: v=str(json.loads(t[a:b+1]).get("faulty_stage","")).strip()
    except json.JSONDecodeError: return None
    return v if v in list(cc.BOUNDARIES)+["none"] else None

HEAD=("You are diagnosing one run of a pipeline researching demand for AI agent tooling "
      "among software teams. Either exactly one stage produced a faulty result, or the run "
      "is clean.\n\nStages: "+", ".join(cc.BOUNDARIES)+"\n\n")
TAIL=('\n\nName the stage where the fault ORIGINATED, or none if the run is clean. '
      'JSON only:\n{"faulty_stage": "<stage name or none>"}')

lock=threading.Lock()
def run_one(case, ex):
    outs=cc.capture(case["cassette"])
    arms={
      "no_values": "Stage purposes only:\n"+"".join(f"- {b}: {INTENT[b]}\n" for b in cc.BOUNDARIES),
      "graph_full": "Every stage's captured value:\n"+"".join(dump(b,outs) for b in cc.BOUNDARIES),
      "retrieval_only": "Captured values for the retrieval stages:\n"+"".join(
          dump(b,outs) for b in cc.BOUNDARIES if b.startswith("retrieve_")),
    }
    for arm,body in arms.items():
        if (case["case_id"],arm) in {(r["case_id"],r["arm"]) for r in ex["runs"]}: continue
        try: ans=parse(ask(HEAD+body+TAIL))
        except Exception as e: ans=None; print("err",type(e).__name__,flush=True)
        with lock:
            ex["runs"].append({"case_id":case["case_id"],"kind":case["kind"],
                "truth":case["truth"],"arm":arm,"answer":ans,
                "correct":ans==case["truth"]})
            OUT.write_text(json.dumps(ex,indent=2))

def main():
    from use_case_icp.scarring import healthy_variants
    pop=healthy_variants(6)
    cases=[]
    # clean controls: does it invent a fault when there is none?
    for i,c in enumerate(pop[:6]):
        cases.append({"case_id":f"clean|{i}","kind":"clean","truth":"none","cassette":c})
    # wrong-sense faults across every source
    for sid,owner in cc.SOURCE_OWNER.items():
        cas=copy.deepcopy(pop[0]); cc.MUTATIONS["wrong_sense"][1](cas[sid])
        cases.append({"case_id":f"wrong_sense|{sid}","kind":"wrong_sense",
                      "truth":owner,"cassette":cas})
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    print(f"{len(cases)} cases x 3 arms",flush=True)
    with ThreadPoolExecutor(5) as pool:
        for c in cases: pool.submit(run_one,c,ex)
    return 0

if __name__=="__main__": sys.exit(main())
