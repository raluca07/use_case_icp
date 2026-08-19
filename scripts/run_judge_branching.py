#!/usr/bin/env python3
"""Judge arm over the branching corpus, to raise n for the detection comparison."""
from __future__ import annotations
import json, sys
from pathlib import Path
from use_case_icp import branching_corpus as bc
from use_case_icp.fault_injection import FAULT_CATALOGUE, inject
from use_case_icp.fault_scoring import capture_stage_outputs
from scripts.run_fault_benchmark import JUDGE_PROMPT, ask, parse_verdict
from scripts.run_selection_benchmark import PARAMETERS

ENDPOINT="http://localhost:8091"; MODEL="mlx-community/Qwen2.5-3B-Instruct-4bit"; REPEATS=3
OUT=Path("benchmark-results/judge_branching.json")
INTENT={
 "define_research_plan":"Declare the research questions and the classes of public source to consult, and the minimum number of sources a finding needs.",
 "retrieve_registries":"Fetch every registry source and report the identifiers retrieved and which class they belong to.",
 "retrieve_trackers":"Fetch every issue-tracker source and report the identifiers retrieved and which class they belong to.",
 "retrieve_vendor_docs":"Fetch every vendor-documentation source and report the identifiers retrieved and which class they belong to.",
 "merge_sources":"Combine the identifiers from every retrieval branch into one list and report how many classes were merged.",
 "extract_evidence_records":"Turn retrieved sources into evidence records, each carrying its source and a supporting quote observed in it.",
 "synthesize_market_demand":"Turn evidence records into ranked market needs, each traceable to supporting evidence, in a stable declared order.",
}

def main()->int:
    cases=[]
    for fname,fault in FAULT_CATALOGUE.items():
        for b in bc.BOUNDARIES:
            for param in PARAMETERS.get(fname,[""]):
                try: inj=inject(bc.build_pipeline(),fault,target=b,parameter=param)
                except ValueError: continue
                cases.append((f"{fname}|{b}|{param or 'default'}",b,inj))
    existing=json.loads(OUT.read_text()) if OUT.exists() else {"verdicts":[]}
    done={(v["case_id"],v["repeat"]) for v in existing["verdicts"]}
    print(f"branching judge: {len(cases)} cases x {REPEATS}",flush=True)
    for i,(cid,boundary,inj) in enumerate(cases):
        try: out=capture_stage_outputs(inj.pipeline,bc.BOUNDARIES)
        except Exception: continue
        prompt=JUDGE_PROMPT.format(boundary=boundary,intent=INTENT[boundary],
              output=json.dumps(out.get(boundary),indent=2,default=str)[:2000])
        for rep in range(REPEATS):
            if (cid,rep) in done: continue
            try: verdict=parse_verdict(ask(ENDPOINT,MODEL,prompt))
            except Exception as e: print("  err",type(e).__name__,flush=True); verdict=None
            existing["verdicts"].append({"case_id":cid,"boundary":boundary,"repeat":rep,"verdict":verdict})
            OUT.write_text(json.dumps(existing,indent=2))
        if i%10==0: print(f"  {i}/{len(cases)}",flush=True)
    return 0

if __name__=="__main__": sys.exit(main())
