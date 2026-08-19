#!/usr/bin/env python3
"""Does stale history cause false positives? The recovered 29 July run observed one:
accumulated history retained build_research_plan as an issue after the other arms treated
it as resolved. This converts that observation into an intervention.

Four cells. History is either clean prior iterations or contains a superseded faulty run
that was since repaired; the current run is either clean or carries a NEW fault elsewhere.
If stale versions remain salient, the stale-history cells should blame the previously
faulty stage: a false positive when the current run is clean, a misdirection when it is not.
"""
from __future__ import annotations
import json, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from use_case_icp import cassette_corpus as cc

OUT=Path("benchmark-results/stale_history.json")
MODEL="haiku"
MUTS=["truncated_response","empty_response","mislabelled_id","null_identifier","stale_copy"]
# (stale-fault source, current-fault source) with different owning boundaries
PAIRS=[("registry_alpha","tracker_delta"),("tracker_delta","docs_zeta"),
       ("docs_zeta","registry_beta"),("registry_gamma","tracker_epsilon")]

def mutate(source_id, mut):
    import copy
    c=copy.deepcopy(cc.BASE_CASSETTE)
    cc.MUTATIONS[mut][1](c[source_id])
    return c

def dump(out):
    return "".join(f"## {b}\n{json.dumps(out.get(b),default=str)[:600]}\n" for b in cc.BOUNDARIES)

def ask(prompt):
    r=subprocess.run(["claude","-p","--model",MODEL],input=prompt,capture_output=True,text=True,timeout=240)
    return r.stdout

def parse(t):
    t=re.sub(r"```(?:json)?|```","",t)
    a,b=t.find("{"),t.rfind("}")
    if a<0 or b<=a: return None
    try: v=str(json.loads(t[a:b+1]).get("faulty_stage","")).strip()
    except json.JSONDecodeError: return None
    return v if v in list(cc.BOUNDARIES)+["none"] else None

def build_cases():
    cases=[]
    clean=cc.capture(cc.BASE_CASSETTE)
    for mut in MUTS:
        for s1,s2 in PAIRS:
            b1,b2=cc.SOURCE_OWNER[s1],cc.SOURCE_OWNER[s2]
            if b1==b2: continue
            stale=cc.capture(mutate(s1,mut))
            cur_f=cc.capture(mutate(s2,mut))
            for cell,hist,cur,truth in (
                ("stale_clean",stale,clean,"none"),
                ("clean_clean",clean,clean,"none"),
                ("stale_fault",stale,cur_f,b2),
                ("clean_fault",clean,cur_f,b2)):
                cases.append({"case_id":f"{mut}|{s1}|{s2}|{cell}","cell":cell,"mutation":mut,
                    "stale_boundary":b1,"truth":truth,"hist":hist,"cur":cur})
    return cases[:96]

lock=threading.Lock()
def run_one(case, ex):
    pr=("You are reviewing an automated pipeline that runs repeatedly. You are shown one "
        "PRIOR iteration (superseded, and any issue in it may have been repaired since) and "
        "then the CURRENT run. Judge ONLY the current run.\n\n"
        "Stages: "+", ".join(cc.BOUNDARIES)+"\n\n"
        "### Prior iteration (superseded)\n"+dump(case["hist"])+
        "\n### CURRENT run\n"+dump(case["cur"])+
        '\n\nIf exactly one stage of the CURRENT run is faulty, name it; if the current run '
        'is clean, answer none. JSON only:\n{"faulty_stage": "<stage name or none>"}')
    try: ans=parse(ask(pr))
    except Exception as e: ans=None; print("err",type(e).__name__,flush=True)
    with lock:
        ex["runs"].append({k:case[k] for k in ("case_id","cell","mutation","stale_boundary","truth")}
                          |{"answer":ans,"correct":ans==case["truth"],
                            "blamed_stale":ans==case["stale_boundary"]})
        OUT.write_text(json.dumps(ex,indent=2))

def main():
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={r["case_id"] for r in ex["runs"]}
    todo=[c for c in build_cases() if c["case_id"] not in done]
    print(f"{len(todo)} calls",flush=True)
    with ThreadPoolExecutor(4) as pool:
        for c in todo: pool.submit(run_one,c,ex)
    return 0

if __name__=="__main__": sys.exit(main())
