#!/usr/bin/env python3
"""Horizon sweep with a frontier model via headless claude -p.

The local 30B fell into fixed-answer behaviour beyond a three-stage chain, so it could
not test a horizon claim: a model returning a constant regardless of input cannot show
an effect of input. Haiku is used here because the task is short and the run is bulk.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path
from use_case_icp import horizon_corpus as hc

KS=[1,2,4,8,16]; MODEL="haiku"
OUT=Path("benchmark-results/horizon_claude.json")

def ask(prompt: str, timeout: int = 180) -> str:
    r = subprocess.run(["claude","-p","--model",MODEL], input=prompt,
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout

def parse(text: str, valid: list[str]) -> str | None:
    text = re.sub(r"```(?:json)?|```", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a: return None
    try: v = str(json.loads(text[a:b+1]).get("faulty_stage","")).strip()
    except json.JSONDecodeError: return None
    return v if v in valid else None

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
                "faulty result. Name the stage where the fault ORIGINATED, not where it became "
                "visible.\n\nStages in order: "+", ".join(bs)+"\n\n"+body+
                '\n\nAnswer with JSON only:\n{"faulty_stage": "<one stage name>"}')
            try: ans=parse(ask(pr),bs)
            except Exception as e: print("err",type(e).__name__,flush=True); ans=None
            ex["runs"].append({"case_id":cid,"mutation":mut,"k":k,"answer":ans,
                "correct":ans=="retrieve_sources",
                "blame_distance":bs.index(ans) if ans in bs else None,
                "chance":1/len(bs),"prompt_chars":len(pr)})
            OUT.write_text(json.dumps(ex,indent=2))
        print(f"k={k} done ({len(ex['runs'])} runs)",flush=True)
    return 0

if __name__=="__main__": sys.exit(main())
