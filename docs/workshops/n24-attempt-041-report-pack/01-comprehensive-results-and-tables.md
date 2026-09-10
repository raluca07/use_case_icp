# Attempt 041 (N24) — comprehensive results and tables

## 1. Experiment status

Attempt 041 is complete and replay-verified.

| Item | Result |
|---|---:|
| Model | GPT-5.5, high reasoning effort |
| Frozen upstream-fault mechanisms | 6 |
| Frozen clean controls | 1 |
| Confirmatory cells per instance | 28 |
| Descriptive cells per instance | 24 |
| Frozen packages | 364 |
| Repetitions per package | 3 |
| Completed terminal reviews | 1,092/1,092 |
| Logical provider calls | 1,302 |
| Required evidence expansions | 126/126 |
| Voluntary expansions | 0/84 |
| Repair calls | 0 |
| Pairwise treatment-isolation checks | 476/476 passed |
| Terminal status | `completed_experiment_and_analysis` |

The six fault mechanisms are the independent faulty units. The three reviews
of a package are repeated measurements, not 18 independent faults. Paired
confidence intervals below first average the three repetitions within each
fault mechanism and then use the six paired fault differences.

The study question was: when the reviewer starts from the observed Job-2
outcome and the fault is in Job 1, which combinations of runtime records,
history, source, semantic declarations, graph evidence, and adaptive
disclosure improve detection and localisation?

## 2. Frozen fault instances

| Instance | Truth function | Fault mechanism |
|---|---|---|
| `select_threshold_omission` | `select_demand` | Omits the score threshold criterion. |
| `select_wrong_source_weight` | `select_demand` | Applies the wrong source weighting. |
| `normalize_top_record_omission` | `normalize` | Omits the highest-ranked selected record. |
| `normalize_middle_record_omission` | `normalize` | Omits a middle-ranked selected record. |
| `provenance_ranking_reversal` | `assemble_provenance` | Reverses provenance ranking. |
| `provenance_join_identity` | `assemble_provenance` | Uses the wrong identity during the provenance join. |
| `n16-clean-control` | none | Clean, no-injection control. |

All scientific assets were reused by exact hash from Attempt 038; no pipeline
was re-authored, reinjected, executed, or recaptured for this experiment.

## 3. Factors and what reviewers actually received

| Factor | Exact meaning |
|---|---|
| `S0` | No separate complete source bundle. It does **not** mean source-free: source naturally embedded in a permitted graph record remains visible. |
| `S1` | Adds the complete mutant Job-1 source and clean Job-2 source as a separate bundle. This adds about 1,612–1,613 source tokens. |
| `B0` | No separate semantic declaration block. Function names or semantics naturally present in source/runtime/graph remain. |
| `B1` | Adds six declarations: the three functions in each job, job ownership, neutral responsibility, expected inputs/outputs, and handoff role. This adds about 655 initial-package tokens. |

The declaration bundle explicitly named `select_demand`, `normalize`,
`assemble_provenance`, `map_coverage`, `prioritize`, and `synthesize`. It was
neutral with respect to the injected fault, but it supplied function-level
answer vocabulary.

### Confirmatory modes

| Code | Mode | Runtime/evidence shown initially | Follow-up |
|---|---|---|---|
| C01 | Current Job 2 | Job-2 input/output and Job-2 stdout/stderr. | None |
| C02 | History Empty | C01 plus an empty `prior_task_records` envelope. | None |
| C03 | History Full | C02 plus Job-1 input/output/logs, chronology, and exact handoff hashes. | None |
| C04 | Etiq Empty Job 2 | C01 plus an empty graph envelope. | None |
| C05 | Compact Fixed Job 2 | C04 plus six real Etiq anchor nodes, captured values, two hidden-child descriptors, and graph-embedded source. | None |
| C06 | Adaptive Required-One Job 2 | Same initial evidence bytes as C05. | Model selects one real nested group; controller discloses it; model answers again. |
| C07 | Reconsideration Job 2 | Same initial evidence bytes as C05/C06. | Model answers again with zero new evidence. |

Every C mode was crossed with `S0/S1 × B0/B1`, producing 28 confirmatory
cells per instance.

### Descriptive modes

| Code | Mode | What it changes |
|---|---|---|
| D01 | I/O Job 2 | Job-2 input/output only; no logs. |
| D02 | I/O Both Jobs | Both jobs' input/output; no logs. |
| D03 | Current Both Jobs | Both jobs' input/output and stdout/stderr. |
| D04 | Etiq Empty Both | D03 plus an empty graph envelope. |
| D05 | Full Graph Job 2 Legacy | Attempt-027 full graph serializer and inspection contract in the new task. |
| D06 | Broad Fixed Job 2 Legacy | Attempt-027 broad selected projection. |
| D07 | Broad Adaptive Job 2 Legacy | Broad selected projection plus optional legacy expansion. |
| D08 | Random Matched Job 2 Legacy | Random graph evidence matched to the historical broad budget. |
| D09 | Compact Adaptive Voluntary Job 2 | C05 compact start with optional nested expansion. |
| D10 | Compact Fixed Both | Both-job runtime base plus the compact graph. |
| D11 | Compact Adaptive Voluntary Both | D10 plus optional nested expansion. |
| D12 | Compact Adaptive Required-One Both | D10 plus one mandatory model-selected nested expansion. |

Every D mode ran only at `S0`, once under `B0` and once under `B1`. D05–D08
are descriptive reproductions of historical evidence mechanisms; differences
among them are not pure graph-topology effects because serializer, initial
budget, operation access, and package size also differ.

## 4. How to read the outcome tables

- **Detect**: reviewer declared that the two-job execution was faulty.
- **Job 1**: reviewer assigned responsibility to the true upstream job.
- **Exact**: reviewer named the true injected function. This is the primary
  outcome.
- **Control FP**: reviewer incorrectly declared the clean control faulty.
- Fault denominators are 18 per cell: six mechanisms × three repetitions.
- Control denominators are three per cell: one control × three repetitions.
- Input tokens include cached input tokens. Cost applies the frozen public
  GPT-5.5 rates to provider-reported usage.

## 5. Complete confirmatory-cell results

| Cell | Mode | Detect | Job 1 | Exact | Control FP | Calls | Input | Cached | Output | Cost USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C01-S0-B0 | Current J2 | 18/18 | 15/18 | 0/18 | 3/3 | 21 | 354,177 | 234,368 | 17,568 | 1.24 |
| C01-S0-B1 | Current J2 | 18/18 | 15/18 | 5/18 | 0/3 | 21 | 369,676 | 234,368 | 17,072 | 1.31 |
| C01-S1-B0 | Current J2 | 15/18 | 14/18 | 14/18 | 1/3 | 21 | 396,492 | 244,608 | 16,372 | 1.37 |
| C01-S1-B1 | Current J2 | 15/18 | 14/18 | 14/18 | 0/3 | 21 | 411,986 | 244,608 | 16,385 | 1.45 |
| C02-S0-B0 | History Empty | 18/18 | 14/18 | 0/18 | 3/3 | 21 | 354,393 | 224,128 | 15,964 | 1.24 |
| C02-S0-B1 | History Empty | 18/18 | 15/18 | 5/18 | 0/3 | 21 | 369,887 | 224,128 | 17,028 | 1.35 |
| C02-S1-B0 | History Empty | 15/18 | 14/18 | 14/18 | 1/3 | 21 | 396,692 | 224,128 | 16,079 | 1.46 |
| C02-S1-B1 | History Empty | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 412,200 | 234,368 | 16,512 | 1.50 |
| C03-S0-B0 | History Full | 17/18 | 15/18 | 0/18 | 0/3 | 21 | 393,052 | 234,368 | 14,924 | 1.36 |
| C03-S0-B1 | History Full | 17/18 | 14/18 | 5/18 | 0/3 | 21 | 408,846 | 224,128 | 17,218 | 1.55 |
| C03-S1-B0 | History Full | 15/18 | 13/18 | 13/18 | 0/3 | 21 | 435,360 | 224,128 | 14,471 | 1.60 |
| C03-S1-B1 | History Full | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 451,174 | 242,560 | 15,406 | 1.63 |
| C04-S0-B0 | Etiq Empty J2 | 18/18 | 15/18 | 0/18 | 3/3 | 21 | 357,687 | 247,680 | 16,089 | 1.16 |
| C04-S0-B1 | Etiq Empty J2 | 18/18 | 15/18 | 4/18 | 0/3 | 21 | 372,360 | 244,608 | 17,238 | 1.28 |
| C04-S1-B0 | Etiq Empty J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 399,176 | 244,608 | 15,946 | 1.37 |
| C04-S1-B1 | Etiq Empty J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 414,681 | 244,608 | 16,306 | 1.46 |
| C05-S0-B0 | Compact Fixed J2 | 18/18 | 18/18 | 18/18 | 0/3 | 21 | 491,664 | 234,368 | 16,010 | 1.88 |
| C05-S0-B1 | Compact Fixed J2 | 16/18 | 16/18 | 16/18 | 0/3 | 21 | 507,166 | 234,368 | 16,240 | 1.97 |
| C05-S1-B0 | Compact Fixed J2 | 17/18 | 17/18 | 17/18 | 0/3 | 21 | 533,981 | 234,368 | 15,223 | 2.07 |
| C05-S1-B1 | Compact Fixed J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 549,484 | 244,608 | 15,417 | 2.11 |
| C06-S0-B0 | Adaptive Required J2 | 18/18 | 18/18 | 18/18 | 0/3 | 42 | 1,500,561 | 448,256 | 36,181 | 6.57 |
| C06-S0-B1 | Adaptive Required J2 | 16/18 | 16/18 | 16/18 | 0/3 | 42 | 1,531,630 | 468,736 | 34,741 | 6.59 |
| C06-S1-B0 | Adaptive Required J2 | 18/18 | 18/18 | 18/18 | 0/3 | 42 | 1,585,014 | 468,736 | 32,546 | 6.79 |
| C06-S1-B1 | Adaptive Required J2 | 16/18 | 16/18 | 16/18 | 0/3 | 42 | 1,614,456 | 478,976 | 34,550 | 6.95 |
| C07-S0-B0 | Reconsideration J2 | 18/18 | 18/18 | 18/18 | 0/3 | 42 | 985,725 | 468,736 | 32,704 | 3.80 |
| C07-S0-B1 | Reconsideration J2 | 15/18 | 15/18 | 15/18 | 0/3 | 42 | 1,016,725 | 458,496 | 32,786 | 4.00 |
| C07-S1-B0 | Reconsideration J2 | 18/18 | 18/18 | 18/18 | 0/3 | 42 | 1,070,362 | 468,736 | 32,048 | 4.20 |
| C07-S1-B1 | Reconsideration J2 | 17/18 | 17/18 | 17/18 | 0/3 | 42 | 1,101,354 | 478,976 | 32,736 | 4.33 |

## 6. Complete descriptive-cell results

| Cell | Mode | Detect | Job 1 | Exact | Control FP | Calls | Input | Cached | Output | Cost USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D01-S0-B0 | I/O J2 | 18/18 | 14/18 | 0/18 | 3/3 | 21 | 340,774 | 244,608 | 15,988 | 1.08 |
| D01-S0-B1 | I/O J2 | 18/18 | 15/18 | 5/18 | 0/3 | 21 | 356,789 | 249,728 | 17,286 | 1.18 |
| D02-S0-B0 | I/O Both | 18/18 | 15/18 | 0/18 | 0/3 | 21 | 362,226 | 240,512 | 14,121 | 1.15 |
| D02-S0-B1 | I/O Both | 18/18 | 15/18 | 6/18 | 0/3 | 21 | 377,131 | 234,368 | 16,622 | 1.33 |
| D03-S0-B0 | Current Both | 18/18 | 15/18 | 0/18 | 0/3 | 21 | 385,564 | 250,752 | 13,593 | 1.21 |
| D03-S0-B1 | Current Both | 18/18 | 16/18 | 8/18 | 0/3 | 21 | 400,724 | 244,608 | 17,815 | 1.44 |
| D04-S0-B0 | Etiq Empty Both | 18/18 | 15/18 | 0/18 | 0/3 | 21 | 387,917 | 244,608 | 13,205 | 1.23 |
| D04-S0-B1 | Etiq Empty Both | 17/18 | 16/18 | 7/18 | 0/3 | 21 | 403,719 | 222,080 | 16,223 | 1.51 |
| D05-S0-B0 | Full Graph Legacy J2 | 16/18 | 16/18 | 16/18 | 0/3 | 21 | 1,370,324 | 213,888 | 17,102 | 6.40 |
| D05-S0-B1 | Full Graph Legacy J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 1,385,827 | 224,128 | 18,071 | 6.46 |
| D06-S0-B0 | Broad Fixed Legacy J2 | 18/18 | 18/18 | 18/18 | 0/3 | 21 | 1,054,572 | 234,368 | 21,057 | 4.85 |
| D06-S0-B1 | Broad Fixed Legacy J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 1,070,367 | 213,888 | 17,954 | 4.93 |
| D07-S0-B0 | Broad Adaptive Legacy J2 | 16/18 | 16/18 | 16/18 | 0/3 | 21 | 1,054,782 | 234,368 | 17,888 | 4.76 |
| D07-S0-B1 | Broad Adaptive Legacy J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 1,070,281 | 234,368 | 18,298 | 4.85 |
| D08-S0-B0 | Random Matched Legacy J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 1,074,345 | 232,320 | 20,007 | 4.93 |
| D08-S0-B1 | Random Matched Legacy J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 1,089,556 | 224,128 | 18,297 | 4.99 |
| D09-S0-B0 | Adaptive Voluntary J2 | 18/18 | 18/18 | 18/18 | 0/3 | 21 | 493,202 | 203,648 | 17,079 | 2.06 |
| D09-S0-B1 | Adaptive Voluntary J2 | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 508,701 | 213,888 | 17,442 | 2.10 |
| D10-S0-B0 | Compact Fixed Both | 16/18 | 16/18 | 16/18 | 0/3 | 21 | 522,723 | 244,608 | 14,405 | 1.95 |
| D10-S0-B1 | Compact Fixed Both | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 538,220 | 234,368 | 14,731 | 2.08 |
| D11-S0-B0 | Adaptive Voluntary Both | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 524,247 | 222,080 | 15,966 | 2.10 |
| D11-S0-B1 | Adaptive Voluntary Both | 15/18 | 15/18 | 15/18 | 0/3 | 21 | 540,049 | 213,888 | 17,002 | 2.25 |
| D12-S0-B0 | Adaptive Required Both | 17/18 | 17/18 | 17/18 | 0/3 | 42 | 1,699,575 | 583,296 | 33,627 | 6.88 |
| D12-S0-B1 | Adaptive Required Both | 16/18 | 16/18 | 16/18 | 0/3 | 42 | 1,593,473 | 489,216 | 32,003 | 6.73 |

## 7. Mode-level totals across factor settings

These totals are useful for orientation but are not causal estimates because
they pool source/declaration settings. Confirmatory modes contain 72 faulty and
12 control reviews; descriptive modes contain 36 faulty and six control
reviews.

| Mode | Detect | Job 1 | Exact | Control FP |
|---|---:|---:|---:|---:|
| C01 Current J2 | 66/72 | 58/72 | 33/72 | 4/12 |
| C02 History Empty | 66/72 | 58/72 | 34/72 | 4/12 |
| C03 History Full | 64/72 | 57/72 | 33/72 | 0/12 |
| C04 Etiq Empty J2 | 66/72 | 60/72 | 34/72 | 3/12 |
| C05 Compact Fixed J2 | 66/72 | 66/72 | 66/72 | 0/12 |
| C06 Adaptive Required J2 | 68/72 | 68/72 | 68/72 | 0/12 |
| C07 Reconsideration J2 | 68/72 | 68/72 | 68/72 | 0/12 |
| D01 I/O J2 | 36/36 | 29/36 | 5/36 | 3/6 |
| D02 I/O Both | 36/36 | 30/36 | 6/36 | 0/6 |
| D03 Current Both | 36/36 | 31/36 | 8/36 | 0/6 |
| D04 Etiq Empty Both | 35/36 | 31/36 | 7/36 | 0/6 |
| D05 Full Graph Legacy J2 | 31/36 | 31/36 | 31/36 | 0/6 |
| D06 Broad Fixed Legacy J2 | 33/36 | 33/36 | 33/36 | 0/6 |
| D07 Broad Adaptive Legacy J2 | 31/36 | 31/36 | 31/36 | 0/6 |
| D08 Random Matched Legacy J2 | 30/36 | 30/36 | 30/36 | 0/6 |
| D09 Adaptive Voluntary J2 | 33/36 | 33/36 | 33/36 | 0/6 |
| D10 Compact Fixed Both | 31/36 | 31/36 | 31/36 | 0/6 |
| D11 Adaptive Voluntary Both | 30/36 | 30/36 | 30/36 | 0/6 |
| D12 Adaptive Required Both | 33/36 | 33/36 | 33/36 | 0/6 |

## 8. Prespecified paired contrasts: primary exact-function outcome

Differences are percentage points in the left arm minus the right arm. The
95% intervals are unadjusted paired t intervals over six fault-mechanism
averages. Bounds are not clipped to the logical -100% to +100% range.

### Source and declaration contrasts

| Contrast | Left − right | Exact Δ pp | 95% t CI pp |
|---|---|---:|---:|
| Separate source | Current S1B0 − Current S0B0 | +77.8 | [+35.4, +120.1] |
| Separate source | Current S1B1 − Current S0B1 | +50.0 | [-22.6, +122.6] |
| Declarations | Current S0B1 − Current S0B0 | +27.8 | [-18.7, +74.3] |
| Declarations | Current S1B1 − Current S1B0 | +0.0 | [0.0, 0.0] |
| Separate source | History Empty S1B0 − S0B0 | +77.8 | [+35.4, +120.1] |
| Separate source | History Empty S1B1 − S0B1 | +55.6 | [-20.0, +131.1] |
| Declarations | History Empty S0B1 − S0B0 | +27.8 | [-18.7, +74.3] |
| Declarations | History Empty S1B1 − S1B0 | +5.6 | [-8.7, +19.8] |
| Separate source | History Full S1B0 − S0B0 | +72.2 | [+25.7, +118.7] |
| Separate source | History Full S1B1 − S0B1 | +55.6 | [-20.0, +131.1] |
| Declarations | History Full S0B1 − S0B0 | +27.8 | [-18.7, +74.3] |
| Declarations | History Full S1B1 − S1B0 | +11.1 | [-17.5, +39.7] |
| Separate source | Etiq Empty S1B0 − S0B0 | +83.3 | [+40.5, +126.2] |
| Separate source | Etiq Empty S1B1 − S0B1 | +61.1 | [-3.1, +125.3] |
| Declarations | Etiq Empty S0B1 − S0B0 | +22.2 | [-20.1, +64.6] |
| Declarations | Etiq Empty S1B1 − S1B0 | +0.0 | [0.0, 0.0] |
| Separate source | Compact Fixed S1B0 − S0B0 | -5.6 | [-19.8, +8.7] |
| Separate source | Compact Fixed S1B1 − S0B1 | -5.6 | [-19.8, +8.7] |
| Declarations | Compact Fixed S0B1 − S0B0 | -11.1 | [-39.7, +17.5] |
| Declarations | Compact Fixed S1B1 − S1B0 | -11.1 | [-39.7, +17.5] |
| Separate source | Adaptive Required S1B0 − S0B0 | +0.0 | [0.0, 0.0] |
| Separate source | Adaptive Required S1B1 − S0B1 | +0.0 | [0.0, 0.0] |
| Declarations | Adaptive Required S0B1 − S0B0 | -11.1 | [-39.7, +17.5] |
| Declarations | Adaptive Required S1B1 − S1B0 | -11.1 | [-39.7, +17.5] |
| Separate source | Reconsideration S1B0 − S0B0 | +0.0 | [0.0, 0.0] |
| Separate source | Reconsideration S1B1 − S0B1 | +11.1 | [-17.5, +39.7] |
| Declarations | Reconsideration S0B1 − S0B0 | -16.7 | [-59.5, +26.2] |
| Declarations | Reconsideration S1B1 − S1B0 | -5.6 | [-19.8, +8.7] |

### History, graph framing, compact graph, and adaptive contrasts

| Contrast | Left − right | Exact Δ pp | 95% t CI pp |
|---|---|---:|---:|
| Empty-history framing | History Empty S0B0 − Current S0B0 | +0.0 | [0.0, 0.0] |
| Empty-history framing | History Empty S0B1 − Current S0B1 | +0.0 | [0.0, 0.0] |
| Empty-history framing | History Empty S1B0 − Current S1B0 | +0.0 | [0.0, 0.0] |
| Empty-history framing | History Empty S1B1 − Current S1B1 | +5.6 | [-8.7, +19.8] |
| Actual history | History Full S0B0 − History Empty S0B0 | +0.0 | [0.0, 0.0] |
| Actual history | History Full S0B1 − History Empty S0B1 | +0.0 | [0.0, 0.0] |
| Actual history | History Full S1B0 − History Empty S1B0 | -5.6 | [-19.8, +8.7] |
| Actual history | History Full S1B1 − History Empty S1B1 | +0.0 | [0.0, 0.0] |
| Empty-graph framing | Etiq Empty S0B0 − Current S0B0 | +0.0 | [0.0, 0.0] |
| Empty-graph framing | Etiq Empty S0B1 − Current S0B1 | -5.6 | [-19.8, +8.7] |
| Empty-graph framing | Etiq Empty S1B0 − Current S1B0 | +5.6 | [-8.7, +19.8] |
| Empty-graph framing | Etiq Empty S1B1 − Current S1B1 | +5.6 | [-8.7, +19.8] |
| Compact graph | Compact Fixed S0B0 − Etiq Empty S0B0 | +100.0 | [+100.0, +100.0] |
| Compact graph | Compact Fixed S0B1 − Etiq Empty S0B1 | +66.7 | [+12.5, +120.9] |
| Compact graph | Compact Fixed S1B0 − Etiq Empty S1B0 | +11.1 | [-17.5, +39.7] |
| Compact graph | Compact Fixed S1B1 − Etiq Empty S1B1 | +0.0 | [0.0, 0.0] |
| Second pass, no evidence | Reconsider S0B0 − Compact Fixed S0B0 | +0.0 | [0.0, 0.0] |
| Second pass, no evidence | Reconsider S0B1 − Compact Fixed S0B1 | -5.6 | [-19.8, +8.7] |
| Second pass, no evidence | Reconsider S1B0 − Compact Fixed S1B0 | +5.6 | [-8.7, +19.8] |
| Second pass, no evidence | Reconsider S1B1 − Compact Fixed S1B1 | +11.1 | [-17.5, +39.7] |
| Expansion vs second pass | Adaptive Required S0B0 − Reconsider S0B0 | +0.0 | [0.0, 0.0] |
| Expansion vs second pass | Adaptive Required S0B1 − Reconsider S0B1 | +5.6 | [-8.7, +19.8] |
| Expansion vs second pass | Adaptive Required S1B0 − Reconsider S1B0 | +0.0 | [0.0, 0.0] |
| Expansion vs second pass | Adaptive Required S1B1 − Reconsider S1B1 | -5.6 | [-19.8, +8.7] |
| Required expansion combined | Adaptive Required S0B0 − Compact Fixed S0B0 | +0.0 | [0.0, 0.0] |
| Required expansion combined | Adaptive Required S0B1 − Compact Fixed S0B1 | +0.0 | [0.0, 0.0] |
| Required expansion combined | Adaptive Required S1B0 − Compact Fixed S1B0 | +5.6 | [-8.7, +19.8] |
| Required expansion combined | Adaptive Required S1B1 − Compact Fixed S1B1 | +5.6 | [-8.7, +19.8] |

The machine-readable analysis contains the same 56 contrasts for fault
detection and correct-job attribution as well as exact localisation, for 168
contrast rows in total. See [`summary.json`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/summary.json).

### Substantive no-graph comparison and placebo decomposition

C01 Current is the ordinary no-graph baseline. C04 Etiq Empty is a separate
placebo arm used to estimate the effect of graph-review framing without graph
evidence. Therefore the substantive total comparison is C05 versus C01; C04
allows that total to be decomposed into framing and supplied graph contents.

| Setting | Current exact | Etiq Empty exact | Compact Fixed exact | Total graph package: C05−C01 | Framing placebo: C04−C01 | Graph contents after framing: C05−C04 |
|---|---:|---:|---:|---:|---:|---:|
| S0-B0 | 0/18 | 0/18 | 18/18 | +18 | 0 | +18 |
| S0-B1 | 5/18 | 4/18 | 16/18 | +11 | -1 | +12 |
| S1-B0 | 14/18 | 15/18 | 17/18 | +3 | +1 | +2 |
| S1-B1 | 14/18 | 15/18 | 15/18 | +1 | +1 | 0 |

For the primary exact-function outcome, the six-fault paired estimates for the
total C05-minus-C01 graph-package contrast were: +100 points [100, 100] at
S0-B0; +61.1 [-3.1, 125.3] at S0-B1; +16.7 [-12.6, 45.9] at S1-B0; and +5.6
[-8.7, 19.8] at S1-B1. Only the first was uniform across all six faults.

## 9. Fault-mechanism splits

### Pooled confirmatory outcomes by fault

Each denominator is 84 reviews: 28 confirmatory cells × three repetitions.
These are descriptive difficulty summaries because they pool evidence
conditions.

| Fault | Detect | Job 1 | Exact |
|---|---:|---:|---:|
| Threshold omission | 45/84 | 45/84 | 29/84 |
| Wrong source weight | 84/84 | 83/84 | 60/84 |
| Top-record omission | 84/84 | 84/84 | 60/84 |
| Middle-record omission | 84/84 | 84/84 | 60/84 |
| Provenance ranking reversal | 84/84 | 84/84 | 72/84 |
| Provenance join identity | 83/84 | 55/84 | 55/84 |

### Exact localisation by fault: non-graph confirmatory modes

Each cell is the number of exact localisations out of three repetitions.

| Fault | C01-S0-B0 | C01-S0-B1 | C01-S1-B0 | C01-S1-B1 | C02-S0-B0 | C02-S0-B1 | C02-S1-B0 | C02-S1-B1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Middle-record omission | 0 | 0 | 3 | 3 | 0 | 0 | 3 | 3 |
| Top-record omission | 0 | 0 | 3 | 3 | 0 | 0 | 3 | 3 |
| Provenance join identity | 0 | 0 | 2 | 2 | 0 | 0 | 2 | 3 |
| Provenance ranking reversal | 0 | 3 | 3 | 3 | 0 | 3 | 3 | 3 |
| Threshold omission | 0 | 2 | 0 | 0 | 0 | 2 | 0 | 0 |
| Wrong source weight | 0 | 0 | 3 | 3 | 0 | 0 | 3 | 3 |

| Fault | C03-S0-B0 | C03-S0-B1 | C03-S1-B0 | C03-S1-B1 | C04-S0-B0 | C04-S0-B1 | C04-S1-B0 | C04-S1-B1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Middle-record omission | 0 | 0 | 3 | 3 | 0 | 0 | 3 | 3 |
| Top-record omission | 0 | 0 | 3 | 3 | 0 | 0 | 3 | 3 |
| Provenance join identity | 0 | 0 | 1 | 3 | 0 | 0 | 3 | 3 |
| Provenance ranking reversal | 0 | 3 | 3 | 3 | 0 | 3 | 3 | 3 |
| Threshold omission | 0 | 2 | 0 | 0 | 0 | 1 | 0 | 0 |
| Wrong source weight | 0 | 0 | 3 | 3 | 0 | 0 | 3 | 3 |

### Exact localisation by fault: compact-graph confirmatory modes

| Fault | C05-S0-B0 | C05-S0-B1 | C05-S1-B0 | C05-S1-B1 | C06-S0-B0 | C06-S0-B1 | C06-S1-B0 | C06-S1-B1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Middle-record omission | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Top-record omission | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Provenance join identity | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Provenance ranking reversal | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Threshold omission | 3 | 1 | 2 | 0 | 3 | 1 | 3 | 1 |
| Wrong source weight | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |

| Fault | C07-S0-B0 | C07-S0-B1 | C07-S1-B0 | C07-S1-B1 |
|---|---:|---:|---:|---:|
| Middle-record omission | 3 | 3 | 3 | 3 |
| Top-record omission | 3 | 3 | 3 | 3 |
| Provenance join identity | 3 | 3 | 3 | 3 |
| Provenance ranking reversal | 3 | 3 | 3 | 3 |
| Threshold omission | 3 | 0 | 3 | 2 |
| Wrong source weight | 3 | 3 | 3 | 3 |

All misses in the compact-graph conditions were concentrated entirely in the
threshold-omission fault. The other five fault mechanisms were exactly
localised in every C05–C07 review under every source/declaration setting.

## 10. Adaptive disclosure results

### Pre/post diagnosis transitions

| Cell | Fault sessions | Pre exact | Post exact | Improved | Worsened |
|---|---:|---:|---:|---:|---:|
| C06-S0-B0 required expansion | 18 | 18 | 18 | 0 | 0 |
| C06-S0-B1 required expansion | 18 | 16 | 16 | 1 | 1 |
| C06-S1-B0 required expansion | 18 | 15 | 18 | 3 | 0 |
| C06-S1-B1 required expansion | 18 | 12 | 16 | 4 | 0 |
| C07-S0-B0 no-evidence reconsideration | 18 | 17 | 18 | 1 | 0 |
| C07-S0-B1 no-evidence reconsideration | 18 | 16 | 15 | 0 | 1 |
| C07-S1-B0 no-evidence reconsideration | 18 | 18 | 18 | 0 | 0 |
| C07-S1-B1 no-evidence reconsideration | 18 | 15 | 17 | 2 | 0 |
| D12-S0-B0 required expansion, both jobs | 18 | 15 | 17 | 2 | 0 |
| D12-S0-B1 required expansion, both jobs | 18 | 15 | 16 | 1 | 0 |

Across C06's 72 faulty sessions, expansion improved eight first diagnoses and
worsened one, changing exact accuracy from 61/72 before disclosure to 68/72
after disclosure. Across C07's 72 faulty sessions, a second pass with no new
evidence improved three and worsened one, changing 66/72 to 68/72. Because
the two arms used separate stochastic model sessions, the larger within-arm
gain in C06 did not translate into a superior final arm result.

### Which nested group reviewers selected

Every capture exposed exactly two direct nested groups: the loop inside
upstream `select_demand` and the loop inside downstream `map_coverage`. There
was no nested-group option inside `normalize` or `assemble_provenance`.

| Cell | Sessions incl. control | Upstream group | Downstream group | Selected group was the truth function |
|---|---:|---:|---:|---:|
| C06-S0-B0 | 21 | 19 | 2 | 6 |
| C06-S0-B1 | 21 | 17 | 4 | 5 |
| C06-S1-B0 | 21 | 20 | 1 | 6 |
| C06-S1-B1 | 21 | 13 | 8 | 3 |
| D12-S0-B0 | 21 | 19 | 2 | 6 |
| D12-S0-B1 | 21 | 15 | 6 | 3 |

For the 72 faulty C06 sessions, reviewers selected the upstream nested group
66 times. For the two `select_demand` fault mechanisms, the selected group was
inside the true function 20/24 times. For the four faults in `normalize` or
`assemble_provenance`, no offered nested group could itself be the true
function. Those faults were generally already localised from the compact
anchor evidence.

All C06 and D12 required selections were valid and completed. Reviewers made
zero optional expansion requests across the 84 D09/D11 voluntary sessions.

## 11. Actual initial-package exposure

Counts and token ranges below come from the frozen package exposure manifest,
not from mode labels. Token ranges reflect differences among the seven
instances. They describe the initial request; follow-up disclosures are not
included.

### Confirmatory exposure

| Mode | S0-B0 tokens | S0-B1 tokens | S1-B0 tokens | S1-B1 tokens | Initial graph | Graph-embedded source under S0 | Operations |
|---|---:|---:|---:|---:|---|---:|---|
| C01 Current | 2,767–3,049 | 3,422–3,704 | 4,770–5,052 | 5,425–5,707 | none | 0 | none |
| C02 History Empty | 2,775–3,057 | 3,430–3,712 | 4,778–5,060 | 5,433–5,715 | none | 0 | none |
| C03 History Full | 4,296–4,689 | 4,951–5,344 | 6,299–6,693 | 6,954–7,348 | none; one history record | 0 | none |
| C04 Etiq Empty | 2,882–3,164 | 3,537–3,819 | 4,885–5,167 | 5,540–5,822 | empty | 0 | none |
| C05 Compact Fixed | 8,811–9,148 | 9,466–9,803 | 10,814–11,151 | 11,469–11,806 | 6 nodes, 0 relationships, 2 hidden groups, 6 values | 1,206–1,207 tokens | none |
| C06 Adaptive Required | 8,842–9,179 | 9,497–9,834 | 10,845–11,182 | 11,500–11,837 | same substantive start as C05 | 1,206–1,207 tokens | expand one group |
| C07 Reconsideration | 8,835–9,172 | 9,490–9,827 | 10,838–11,175 | 11,493–11,830 | same substantive start as C05 | 1,206–1,207 tokens | no-evidence second pass |

`S1` increased total visible source in compact graph arms from about 1,206 to
2,818–2,820 tokens. Therefore the compact `S1-S0` comparison adds a separate
source bundle to an arm that already contains graph-embedded source.

### Descriptive exposure at B0

Adding B1 supplied six declarations and roughly 655 tokens to each row without
changing its graph selection.

| Mode | B0 initial tokens | Nodes | Relationships | Groups | Captured values | Visible source tokens | Operations |
|---|---:|---:|---:|---:|---:|---:|---|
| D01 I/O J2 | 2,177–2,382 | 0 | 0 | 0 | 0 | 0 | none |
| D02 I/O Both | 2,914–3,176 | 0 | 0 | 0 | 0 | 0 | none |
| D03 Current Both | 3,956–4,354 | 0 | 0 | 0 | 0 | 0 | none |
| D04 Etiq Empty Both | 4,071–4,469 | 0 | 0 | 0 | 0 | 0 | none |
| D05 Full Graph | 46,374–47,927 | 73–75 | 103–107 | 0 | 73–75 | 4,893–5,054 | artifact inspection |
| D06 Broad Fixed | 33,108–33,651 | 53 | 69 | 2 | 53 | 3,629–3,631 | artifact inspection |
| D07 Broad Adaptive | 33,116–33,659 | 53 | 69 | 2 | 53 | 3,629–3,631 | artifact inspection, optional expansion |
| D08 Random Matched | 33,785–34,716 | 53 | 69 | 0 | 53 | 4,004–4,334 | artifact inspection |
| D09 Compact Voluntary J2 | 8,842–9,179 | 6 | 0 | 2 | 6 | 1,206–1,207 | optional expansion |
| D10 Compact Fixed Both | 10,000–10,453 | 6 | 0 | 2 | 6 | 1,206–1,207 | none |
| D11 Compact Voluntary Both | 10,031–10,484 | 6 | 0 | 2 | 6 | 1,206–1,207 | optional expansion |
| D12 Compact Required Both | 10,031–10,484 | 6 | 0 | 2 | 6 | 1,206–1,207 | required expansion |

## 12. Logs, I/O, history, and placebo comparisons

| Comparison | B0 exact | B1 exact | Control-FP observation |
|---|---:|---:|---|
| Job-2 logs: C01 Current vs D01 I/O J2 | 0/18 vs 0/18 | 5/18 vs 5/18 | unchanged: 3/3 at B0, 0/3 at B1 |
| Job-1 I/O: D02 I/O Both vs D01 I/O J2 | 0/18 vs 0/18 | 6/18 vs 5/18 | B0 fell from 3/3 to 0/3 |
| Both-job logs: D03 Current Both vs D02 I/O Both | 0/18 vs 0/18 | 8/18 vs 6/18 | both 0/3 |
| Empty graph: D04 vs D03, both-job base | 0/18 vs 0/18 | 7/18 vs 8/18 | both 0/3 |
| Empty history: C02 vs C01, Job-2 base | 0/18 vs 0/18 at S0-B0 | 5/18 vs 5/18 at S0-B1 | unchanged in every matched setting |
| Full history: C03 vs C02, Job-2 base | 0/18 vs 0/18 at S0-B0 | 5/18 vs 5/18 at S0-B1 | S0-B0 fell from 3/3 to 0/3 |

There is no systematic exact-localisation placebo effect from either an empty
history envelope or an empty graph envelope. The false-positive observations
are informative diagnostics but are based on one clean instance.

## 13. Resource use

| Block | Calls | Input tokens | Cached input | Output tokens | Estimated cost | Sum of call latency |
|---|---:|---:|---:|---:|---:|---:|
| Confirmatory | 756 | 18,785,961 | 8,458,752 | 591,760 | $73.62 | 14,610 s |
| Descriptive | 546 | 18,605,088 | 6,147,712 | 435,782 | $78.43 | 10,755 s |
| Total | 1,302 | 37,391,049 | 14,606,464 | 1,027,542 | $152.05 | 25,365 s |

The sum of per-call latency is not wall-clock experiment duration. Provider
records did not supply a separate reasoning-token count.

## 14. Interpretation

1. Detection alone is not discriminating here: several source/declaration-free
   arms detected every fault while naming no correct function.
2. Relative to Current, the compact Etiq package moved exact localisation from
   0/18 to 18/18 in the central `S0-B0` comparison; Empty Graph remained 0/18,
   so graph framing did not explain that result.
3. Complete source gave non-graph reviewers much of the same function-level
   capability. It did not reliably improve an already informative compact
   graph.
4. Separately stated function responsibilities sometimes supplied useful
   answer vocabulary, especially without source, but did not consistently add
   to source or graph evidence.
5. Full and broad graph serializations were several times larger and more
   expensive than compact evidence without achieving better accuracy.
6. Required expansion affected individual diagnoses, but its final accuracy
   did not exceed the matched compact graph or the no-evidence second pass.
7. The threshold omission remains the principal hard case. Adding source or
   declarations sometimes coincided with worse decisions on that mechanism,
   showing that more context was not monotonically beneficial.

## 15. Limitations and claim boundaries

- The experiment covers one two-job pipeline family, six upstream mutations,
  one clean control, one model/configuration, and three repeated calls.
- The compact graph effect is not topology-only. Its nodes include function
  identity, source, captured values, and grouping semantics.
- `B1` is not a content-free boundary marker; it explicitly describes six
  functions and their responsibilities.
- The single control cannot support a precise false-positive-rate estimate.
- C06 and C07 use necessarily different action wording, so their difference is
  not a perfectly pure evidence-only intervention.
- Adaptive menus contained nested groups only for `select_demand` and
  `map_coverage`, not for the four faults in `normalize` or
  `assemble_provenance`.
- Optional expansion was never selected, so the run provides no evidence about
  the value of model-initiated voluntary disclosure.
- D05–D08 reproduce historical evidence mechanisms in the N24 common task;
  they are not byte-identical replications of the earlier full packages.
- No repairs were run; all conclusions concern review/detection/localisation.
- Confidence intervals are unadjusted across many prespecified comparisons,
  and higher-order source × declaration × mode interactions are descriptive.

## 16. Execution integrity and provenance

The run initially stopped twice on provider-schema incompatibilities. N24A and
N24B applied narrowly authorized response-schema corrections, preserved the
original freeze and completed reviews, and resumed without changing packages,
prompts, model configuration, treatments, scoring, source/declaration
allocation, or operation limits. Replay verifies unchanged package bytes,
preserved receipts, unique provider-call IDs, 1,092 review hashes, and zero
repairs.

| Artifact | Exact-file SHA-256 |
|---|---|
| Terminal state | `e7008ebcbe0a96b629138e0db156fe472541b2dbc75df0124890bb91f8e81217` |
| Analysis summary | `7ae66303757d48f2ebd95658d5c90868edeb3965c7243f2d37425ee3f14adbe4` |
| Results by cell | `6549e7d476a454600d00ef2575caf7c7e355f8106139fa6c73ea787a7395c781` |
| Adaptive transitions | `0684970df5992ccf7e7baa7140252253cb9c35a289fd0c98ad5303e4b696ac3d` |
| Token/cost ledger | `64a9b3bcd2b93cc5f0e3f310815c81b1c10905a1042d19883186cab89abdd748` |
| Exposure manifest | `3384650a253031e8a949b9cff6ef55aca2c43011e19b6d8edc7a4440a0fbbfd3` |
| Pairwise package report | `0b8283b1007f97a060d02ea405cb22a8dcb4a1dc865f897b4420967aa7663cc8` |
| Replay | `253d58982c3ce5c112fbdb4bee247479a59d1bff9f78746b5241c13019c5c501` |

Authoritative artifacts:

- [`terminal-state.json`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/terminal-state.json)
- [`experiment-freeze.json`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/experiment-freeze.json)
- [`results-by-cell.csv`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/results-by-cell.csv)
- [`summary.json`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/summary.json)
- [`adaptive-transitions.csv`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/adaptive-transitions.csv)
- [`token-and-costs.csv`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/token-and-costs.csv)
- [`package-exposure-manifest.json`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/package-exposure-manifest.json)
- [`pairwise-package-differences.json`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/pairwise-package-differences.json)
- [`replay.json`](../../../outputs/fault-experiments-v2-2-n10/attempt-041/replay.json)

For the concise interpretation, see [the findings summary](00-findings-summary.md).
