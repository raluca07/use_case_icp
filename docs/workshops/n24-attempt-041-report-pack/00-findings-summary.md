# Attempt 041 (N24) — findings summary

## Bottom line

Attempt 041 completed the unified downstream-first experiment: a reviewer
started from the observed Job-2 result while every injected fault was in Job 1.
The experiment used six fault mechanisms, one clean control, 364 frozen
packages, three reviewer repetitions per package, and 1,092 completed reviews.

The strongest result is about **exact localisation**, not detection. Fault
detection was already close to ceiling in most arms. In the cleanest
source/declaration-free comparison, Current—the ordinary no-graph baseline—and
the Empty Graph placebo each detected 18/18 faulty reviews but localised the
responsible function 0/18 times. Compact Fixed detected and exactly localised
18/18. The total Compact-versus-Current difference and the graph-content
Compact-versus-Empty difference were both +100 percentage points; the empty
graph framing itself contributed zero.

This should be described as an effect of the **compact Etiq evidence package**,
not pure graph topology. Even under `S0` (“no separate source bundle”), the
compact graph exposed 1,206–1,207 tokens of source naturally embedded in six
captured anchor nodes, together with captured values and two nested-group
descriptors. Empty Graph exposed none of those items.

## Main findings

1. **Compact Etiq evidence enabled upstream function localisation when the
   ordinary package supplied neither source nor declarations.** At `S0-B0`,
   Current scored 18/18 detection, 15/18 correct Job 1, and 0/18 exact
   function. Empty Graph produced the same three scores, showing no framing
   placebo. Compact Fixed scored 18/18 on all three outcomes and reduced the
   clean-control false positives from 3/3 to 0/3. The gain was localisation and
   discrimination, not merely willingness to declare a fault.

2. **A separate complete source bundle was a strong substitute for graph
   evidence in non-graph arms.** Under `B0`, adding source changed exact
   localisation from 0/18 to 14/18 for Current, 0/18 to 14/18 for History
   Empty, 0/18 to 13/18 for History Full, and 0/18 to 15/18 for Empty Graph.
   The corresponding paired exact-function estimates were +72.2 to +83.3
   percentage points. Source did not add a clear benefit once compact graph
   evidence was present, partly because the graph already contained captured
   source.

3. **The semantic declaration bundle helped provide function vocabulary when
   source and graph were absent, but it was weaker and fault-dependent.** At
   `S0`, declarations raised exact localisation from 0/18 to 5/18 for Current
   and History Empty, to 5/18 for History Full, and to 4/18 for Empty Graph.
   These estimates had wide intervals crossing zero. Declarations also changed
   the one clean control from 3/3 false positives to 0/3 in Current, History
   Empty, Empty Graph, and Job-2 I/O. With source or compact graph already
   available, declarations showed no consistent additional benefit.

4. **History, logs, and empty-envelope framing did not materially improve exact
   localisation.** History Full versus History Empty produced exact-function
   differences of 0, 0, -1, and 0 reviews out of 18 across the four source ×
   declaration settings. History Empty versus Current and Empty Graph versus
   Current were also essentially null. Job-2 logs and both-job logs changed
   exact localisation by at most two reviews in the descriptive comparisons.
   History Full and both-job I/O did remove false positives in the single
   control under `S0-B0`, but one control instance is not enough for a stable
   false-positive estimate.

5. **Required nested disclosure executed correctly but did not beat the compact
   starting graph or a matched second reasoning pass at the arm level.** All
   126 required expansions completed: 84 in Job-2-base Adaptive Required-One
   and 42 in the both-job version. Job-2-base Adaptive versus Reconsideration
   differed by 0, +1, 0, and -1 exact reviews out of 18 across the four factor
   settings. Adaptive versus Compact Fixed differed by 0, 0, +1, and +1. All
   paired intervals included zero. Within Adaptive sessions, expansion improved
   eight of 72 faulty diagnoses and worsened one, but Adaptive began from a less
   accurate stochastic first response and finished tied with Reconsideration
   overall (68/72 exact in each arm). Thus the transition evidence shows that
   disclosures can change a diagnosis, but this run does not show a net
   accuracy advantage over simply reconsidering the compact graph.

6. **Voluntary expansion was never used.** Reviewers made zero optional
   expansions in 84 eligible sessions. A compact graph with an optional tool
   therefore behaved as a static compact-graph condition in this run.

7. **Compact evidence was substantially cheaper than full or broad graph
   serialization without losing accuracy.** Under `S0-B0`, Compact Fixed
   exactly localised 18/18 using initial packages of 8.8k–9.1k estimated tokens
   and cost $1.88 across its 21 calls. Full Graph scored 16/18 with 46.4k–47.9k
   initial tokens and cost $6.40; Broad Fixed scored 18/18 with 33.1k–33.7k
   initial tokens and cost $4.85; Random Matched scored 15/18 and cost $4.93.
   Required-One Adaptive cost $6.57 in the same `S0-B0` cell, versus $1.88 for
   Compact Fixed and $3.80 for a no-evidence second pass.

8. **Fault mechanism mattered considerably.** Pooled across the 28
   confirmatory cells, the subtle threshold omission was detected in only
   45/84 reviews and exactly localised in 29/84. Provenance join identity was
   detected 83/84 times but assigned to Job 1 and exactly localised only 55/84
   times. The other four mechanisms were detected 84/84 and exactly localised
   in 60–72/84. These pooled numbers are descriptive, but they show why the
   experiment should not be reduced to one overall accuracy.

## What the experiment supports

It supports the conclusion that, for this pipeline and these six upstream
faults, a compact package of captured cross-job Etiq execution evidence can
make the responsible Job-1 function localisable from a downstream-first review
when ordinary runtime evidence cannot. It also shows that complete source can
provide much of the same function-level diagnostic vocabulary.

It does **not** isolate graph connectivity from the source, function identity,
captured values, and grouping semantics embedded in graph nodes. It also does
not demonstrate that adding semantic declarations or one nested disclosure
improves an already informative compact graph.

## Evidence and detailed tables

- [Source/declaration and hard-fault findings](02-source-declaration-and-hard-fault-findings.md)
- [Comprehensive report and tables](01-comprehensive-results-and-tables.md)
- [Frozen package-level outcomes](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/results-by-cell.csv)
- [Machine-readable paired contrasts](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/summary.json)
- [Adaptive transitions](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/adaptive-transitions.csv)
- [Raw token and cost ledger](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/token-and-costs.csv)
- [Package exposure manifest](../../../outputs/fault-experiments-v2-2-n10/attempt-041/package-exposure-manifest.json)
- [Terminal state](../../../outputs/fault-experiments-v2-2-n10/attempt-041/terminal-state.json)
