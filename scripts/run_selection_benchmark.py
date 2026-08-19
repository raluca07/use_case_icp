#!/usr/bin/env python3
"""Score repair-target selectors against the boundary a fault was injected into."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from use_case_icp import branching_corpus as bc
from use_case_icp.fault_injection import FAULT_CATALOGUE, inject
from use_case_icp.fault_scoring import ContractDetector, SchemaDetector, capture_stage_outputs
from use_case_icp.selection import SELECTORS

PARAMETERS = {
    "drop_field": ["questions", "source_classes", "source_ids", "source_class",
                   "records", "needs", "record_count", "classes_merged", "quote", "support"],
    "fabricate_identifier": ["PLACEHOLDER-001", "registry_alpha", "tracker_delta",
                             "docs_zeta", "registries", "observed practitioner statement"],
    "truncate_sequence": [""],
    "invert_comparison": [""],
    "reverse_ordering": [""],
}


def build() -> list:
    cases = []
    for fault_name, fault in FAULT_CATALOGUE.items():
        for boundary in bc.BOUNDARIES:
            for parameter in PARAMETERS.get(fault_name, [""]):
                try:
                    injected = inject(bc.build_pipeline(), fault,
                                      target=boundary, parameter=parameter)
                except ValueError:
                    continue
                cases.append((f"{fault_name}|{boundary}|{parameter or 'default'}",
                              fault_name, fault.provenance, boundary, injected))
    return cases


def main() -> int:
    cases = build()
    detectors = {"schema": SchemaDetector(bc.SCHEMAS), "contract": ContractDetector(bc.CONTRACTS)}
    rows = []
    for case_id, fault, provenance, boundary, injected in cases:
        try:
            outputs = capture_stage_outputs(injected.pipeline, bc.BOUNDARIES)
        except Exception as exc:
            rows.append({"case_id": case_id, "crashed": True, "error": str(exc)})
            continue
        row = {"case_id": case_id, "fault": fault, "provenance": provenance,
               "boundary": boundary, "crashed": False, "detectors": {}}
        for dname, detector in detectors.items():
            labels = detector.label(bc.BOUNDARIES, outputs)
            flagged = [b for b in bc.BOUNDARIES if labels.get(b) == "suspect"]
            picks = {}
            for sname, selector in SELECTORS.items():
                pick = selector(injected.pipeline, bc.BOUNDARIES, labels)
                picks[sname] = {"pick": pick, "correct": pick == boundary}
            row["detectors"][dname] = {"n_flagged": len(flagged), "flagged": flagged,
                                       "selectors": picks}
        rows.append(row)

    out = Path("benchmark-results/selection.json")
    out.write_text(json.dumps({"boundaries": bc.BOUNDARIES, "rows": rows}, indent=2))

    live = [r for r in rows if not r["crashed"]]
    print(f"branching corpus: {len(rows)} cases, {len(rows)-len(live)} crashed, {len(live)} silent")
    for dname in detectors:
        contested = [r for r in live if r["detectors"][dname]["n_flagged"] > 1]
        print(f"\n-- detector: {dname}   cases with >1 boundary flagged: {len(contested)}/{len(live)}")
        for sname in SELECTORS:
            allc = sum(1 for r in live if r["detectors"][dname]["selectors"][sname]["correct"])
            conc = sum(1 for r in contested if r["detectors"][dname]["selectors"][sname]["correct"])
            print(f"   {sname:13} correct overall {allc}/{len(live)} ({allc/max(len(live),1):.0%})"
                  f"   on contested {conc}/{max(len(contested),1)} ({conc/max(len(contested),1):.0%})")
        dis = [r for r in contested
               if r["detectors"][dname]["selectors"]["source_order"]["pick"]
               != r["detectors"][dname]["selectors"]["causal_root"]["pick"]]
        print(f"   selectors disagree on {len(dis)} contested cases")
        if dis:
            w = sum(1 for r in dis if r["detectors"][dname]["selectors"]["causal_root"]["correct"])
            l = sum(1 for r in dis if r["detectors"][dname]["selectors"]["source_order"]["correct"])
            print(f"     of those: causal_root right {w}, source_order right {l}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
