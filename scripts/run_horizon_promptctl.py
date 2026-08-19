#!/usr/bin/env python3
"""Control: same model, original prompt wording, to separate model from instruction."""
from __future__ import annotations
import json, sys
from pathlib import Path
from use_case_icp import horizon_corpus as hc
from scripts.run_horizon_claude import ask, parse

KS=[1,2,4,8,16]; OUT=Path("benchmark-results/horizon_promptctl.json")
N_PER_K=12  # subset: enough to separate a large effect, a fraction of the cost

def main()->int:
    ex=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["k"]) for r in ex["runs"]}
    for k in KS:
        bs=hc.boundaries(k)
        for cid,mut,cass in hc.cases(k)[:N_PER_K]:
            if (cid,k) in done: continue
            out=hc.capture(k,cass)
            body="".join(f"## {b}\n{hc.intent(b)}\n{json.dumps(out.get(b),default=str)[:500]}\n" for b in bs)
            # ORIGINAL wording: no "originated, not where it became visible" hint
            pr=("You are diagnosing one run of a data pipeline. Exactly one stage produced a "
                "faulty result. Name that stage.\n\nStages: "+", ".join(bs)+"\n\n"+body+
                '\n\nAnswer with JSON only:\n{"faulty_stage": "<one stage name>"}')
            try: ans=parse(ask(pr),bs)
            except Exception as e: print("err",type(e).__name__,flush=True); ans=None
            ex["runs"].append({"case_id":cid,"mutation":mut,"k":k,"answer":ans,
                "correct":ans=="retrieve_sources",
                "blame_distance":bs.index(ans) if ans in bs else None})
            OUT.write_text(json.dumps(ex,indent=2))
        print(f"ctl k={k} done",flush=True)
    return 0

if __name__=="__main__": sys.exit(main())
