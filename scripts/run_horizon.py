#!/usr/bin/env python3
"""Localisation accuracy and blame distance against chain length."""
from __future__ import annotations
import json, sys
from pathlib import Path
from use_case_icp import horizon_corpus as hc
from scripts.run_fault_benchmark import ask

ENDPOINT="http://localhost:8093"; MODEL="mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit"
KS=[1,2,4,8,16]; OUT=Path("benchmark-results/horizon.json")

def main()->int:
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["k"]) for r in ex["runs"]}
    for k in KS:
        bs=hc.boundaries(k)
        for cid,mut,cass in hc.cases(k):
            if (cid,k) in done: continue
            out=hc.capture(k,cass)
            body="".join(f"## {b}\n{hc.intent(b)}\n{json.dumps(out.get(b),default=str)[:500]}\n" for b in bs)
            pr=("You are diagnosing one run of a data pipeline. Exactly one stage produced a "
                "faulty result. Name that stage.\n\nStages: "+", ".join(bs)+"\n\n"+body+
                '\n\nAnswer with JSON only:\n{"faulty_stage": "<one stage name>"}')
            try:
                t=ask(ENDPOINT,MODEL,pr,timeout=300)
                a,b=t.find("{"),t.rfind("}")
                ans=str(json.loads(t[a:b+1]).get("faulty_stage","")).strip() if a>=0 else None
                ans=ans if ans in bs else None
            except Exception as e:
                print("err",type(e).__name__,flush=True); ans=None
            dist=bs.index(ans) if ans in bs else None
            ex["runs"].append({"case_id":cid,"mutation":mut,"k":k,"answer":ans,
                "correct":ans=="retrieve_sources","blame_distance":dist,
                "chance":1/len(bs),"prompt_chars":len(pr)})
            OUT.write_text(json.dumps(ex,indent=2))
        print(f"k={k} done",flush=True)
    return 0

if __name__=="__main__": sys.exit(main())
