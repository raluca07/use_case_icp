#!/usr/bin/env python3
"""Four context regimes, one task: name the faulty boundary.

This is the published comparison's arm structure with a known answer to score
against. The arms differ in what the agent is shown, which is the claim the
execution graph actually makes: that a selected region beats both everything and
nothing.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from use_case_icp import branching_corpus as bc
from use_case_icp.fault_injection import FAULT_CATALOGUE, inject, _dataflow_edges, _entry_source
from use_case_icp.fault_scoring import ContractDetector, capture_stage_outputs
from use_case_icp.selection import select_causal_root
from scripts.run_fault_benchmark import ask, parse_verdict
from scripts.run_judge_branching import INTENT
from scripts.run_selection_benchmark import PARAMETERS

ENDPOINT="http://localhost:8091"; MODEL="mlx-community/Qwen2.5-3B-Instruct-4bit"
REPEATS=1
OUT=Path("benchmark-results/context_arms.json")

HEAD=("You are diagnosing one run of an automated market-research pipeline. Exactly one "
      "stage produced a faulty result. Using only what is shown below, name the single "
      "stage most likely to be at fault.\n\n")
TAIL=("\n\nAnswer with JSON only, no other text:\n"
      '{"faulty_stage": "<one stage name from the list>", "reason": "<one short sentence>"}')

def stage_list() -> str:
    return "Stages in this pipeline: " + ", ".join(bc.BOUNDARIES) + "\n"

def build_prompt(arm, outputs, pipeline, labels):
    if arm == "no_graph":
        body = ("Final pipeline output:\n"
                + json.dumps(outputs.get("synthesize_market_demand"), indent=2, default=str)[:2000])
    elif arm == "semantic_only":
        body = "Stage purposes, with no captured values:\n" + "\n".join(
            f"- {b}: {INTENT[b]}" for b in bc.BOUNDARIES)
    elif arm == "graph_full":
        body = "Captured value produced by every stage:\n" + "\n".join(
            f"\n## {b}\n{INTENT[b]}\n{json.dumps(outputs.get(b), indent=2, default=str)[:900]}"
            for b in bc.BOUNDARIES)
    elif arm == "graph_selected":
        root = select_causal_root(pipeline, bc.BOUNDARIES, labels)
        edges = _dataflow_edges(_entry_source(pipeline))
        region = {root} if root else set()
        # the selected region: the causal root plus what it directly feeds
        for producer, consumer in edges:
            if producer == root and consumer in bc.BOUNDARIES:
                region.add(consumer)
        if not region:
            region = set(bc.BOUNDARIES)
        ordered = [b for b in bc.BOUNDARIES if b in region]
        body = ("Captured values for the region the execution graph selected as causally "
                "upstream:\n" + "\n".join(
            f"\n## {b}\n{INTENT[b]}\n{json.dumps(outputs.get(b), indent=2, default=str)[:900]}"
            for b in ordered))
    else:
        raise ValueError(arm)
    return HEAD + stage_list() + body + TAIL

def parse_stage(text):
    a,b=text.find("{"),text.rfind("}")
    if a<0 or b<=a: return None
    try: v=json.loads(text[a:b+1]).get("faulty_stage")
    except json.JSONDecodeError: return None
    v=str(v).strip()
    return v if v in bc.BOUNDARIES else None

def main()->int:
    detector=ContractDetector(bc.CONTRACTS)
    cases=[]
    for fname,fault in FAULT_CATALOGUE.items():
        for b in bc.BOUNDARIES:
            for param in PARAMETERS.get(fname,[""]):
                try: inj=inject(bc.build_pipeline(),fault,target=b,parameter=param)
                except ValueError: continue
                cases.append((f"{fname}|{b}|{param or 'default'}",fname,b,inj))
    existing=json.loads(OUT.read_text()) if OUT.exists() else {"runs":[]}
    done={(r["case_id"],r["arm"],r["repeat"]) for r in existing["runs"]}
    arms=["no_graph","semantic_only","graph_full","graph_selected"]
    total=len(cases)*len(arms)*REPEATS; count=0
    print(f"{len(cases)} cases x {len(arms)} arms x {REPEATS} = {total}",flush=True)
    for cid,fname,boundary,inj in cases:
        try: outputs=capture_stage_outputs(inj.pipeline,bc.BOUNDARIES)
        except Exception: continue
        labels=detector.label(bc.BOUNDARIES,outputs)
        for arm in arms:
            prompt=build_prompt(arm,outputs,inj.pipeline,labels)
            for rep in range(REPEATS):
                count+=1
                if (cid,arm,rep) in done: continue
                try: answer=parse_stage(ask(ENDPOINT,MODEL,prompt))
                except Exception as e: print("  err",type(e).__name__,flush=True); answer=None
                existing["runs"].append({"case_id":cid,"fault":fname,"true_boundary":boundary,
                    "arm":arm,"repeat":rep,"answer":answer,"correct":answer==boundary,
                    "prompt_chars":len(prompt)})
                OUT.write_text(json.dumps(existing,indent=2))
            if count%40==0: print(f"  {count}/{total}",flush=True)
    return 0

if __name__=="__main__": sys.exit(main())
