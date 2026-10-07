# Attempt 057 corrected findings

Attempt 057 tested six evidence treatments on 12 faulty instances and four
matched clean controls. Every arm received the complete source of all four
jobs, all four jobs' top-level inputs and parsed outputs, and only Job 4's
stdout/stderr. The graph arms added native Etiq execution structure; Adaptive
arms could disclose nested execution state.

The frozen controller analysis contains a Job-3 truth-binding error. This
report applies the deterministic reporting correction documented in
[scoring-correction.md](scoring-correction.md). No experiment artifact or model
response was changed.

## Corrected headline results

- Fault detection: **188/216 (87.04%)**.
- Correct-job attribution: **188/216 (87.04%)**, not the frozen report's 152/216.
- Exact-function localisation: **188/216 (87.04%)**, not 152/216.
- Clean-control false positives: **0/72**.
- Scientific calls: **576**; repairs and calibration calls: **0**.

## Findings

1. **The compact graph produced a small descriptive gain over source and
   top-level I/O alone.** P02 exactly localised 33/36 faults versus 30/36 for
   P01. All three additional successes were premature-rounding reviews. The
   paired test was not significant (difference +8.33 percentage points,
   two-sided p=0.500; Holm p=1.000). [Arm and mechanism results](cell-table.md)
   · [significance](significance-table.md#confirmatory-arm-contrasts)

2. **Adaptive disclosure did not improve on the static compact graph in the
   matched no-semantics comparison.** P04 and P02 both finished at 33/36 exact;
   P04 won one instance and lost one (p=1.000). Thus this run does not establish
   an incremental accuracy benefit from nested disclosure. [Cell results](cell-table.md#arm-level-results)
   · [significance](significance-table.md#confirmatory-arm-contrasts)

3. **Only premature rounding remained genuinely difficult.** Across all arms,
   rounding was localised 10/36 times. P01 scored 0/6, P02 3/6, P03 0/6, P04
   3/6, P05 4/6 and P06 0/6. The other five mechanisms were at ceiling except
   for two P06 misses on oldest-repeat retention. [Mechanism table](cell-table.md#exact-localisation-by-fault-mechanism)
   · [all 96 cells](complete-result-cells.md)

4. **The semantic labels showed no reliable benefit.** On the static graph,
   adding labels reduced exact localisation from 33/36 (P02) to 30/36 (P03).
   On Adaptive, labels increased it from 33/36 (P04) to 34/36 (P05). Neither
   contrast was significant. [Arm table](cell-table.md#arm-level-results) ·
   [confirmatory tests](significance-table.md#confirmatory-arm-contrasts)

5. **Extra calls alone did not explain the best observed score.** P06 received
   the same compact graph as P02 and two additional reconsideration calls but
   no new evidence; it fell from 33/36 to 28/36. P05 scored 34/36 versus P06's
   28/36, but that contrast combines disclosure and semantics and remained
   non-significant after correction (raw p=0.125; Holm p=0.750). [Arm table](cell-table.md#arm-level-results)
   · [significance](significance-table.md#confirmatory-arm-contrasts)

6. **The experiment did not demonstrate that selecting the designated hidden
   natural state caused success.** In the 24 eligible Adaptive reviews for the
   repeat-order and cross-opportunity mechanisms, the model selected
   `ordered_df` or `decision_rank` in 19. It was exact in all 19 selected and
   all five non-selected reviews; P01 already scored 12/12 on those mechanisms.
   [Per-cell selections](complete-result-cells.md) ·
   [frozen selection record](natural-state-selections.json)

7. **All arms avoided false positives on the clean controls.** Each arm scored
   0/12, giving 0/72 overall. This supports specificity in these four controls,
   but it cannot distinguish the arms statistically. [Control table](cell-table.md#control-false-positives)
   · [false-positive tests](significance-table.md#confirmatory-arm-contrasts)

8. **Interactive review was much more expensive without a demonstrated
   accuracy gain over static graph evidence.** P02 used 2,904,514
   input-plus-output tokens and 48 calls. P04 used 9,150,328
   tokens and 144 calls for the same 33/36 exact result; P05 used
   9,218,638 tokens and 144 calls for 34/36.
   [Arm-level token totals](cell-table.md#arm-level-results) ·
   [per-call accounting](per-call-token-latency.json)

## Statistical conclusion

No prespecified arm contrast was significant at two-sided 0.05, either before
or after Holm correction. The graph differences above must therefore be
reported as descriptive estimates from 12 independent faulty instances, not as
established effects. The three model repetitions per instance are repeated
measurements, not additional independent fault cases. [Full significance table](significance-table.md)

## Complete audit trail

- [Corrected aggregate and mechanism tables](cell-table.md)
- [Every one of the 96 instance × arm cells](complete-result-cells.md)
- [Every one of the 288 individual review results](all-review-results-corrected.csv)
- [Detailed significance tables](significance-table.md)
- [Scoring correction and frozen hashes](scoring-correction.md)
- [Frozen analysis](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/analysis/summary.json)
- [Freeze](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/experiment-freeze.json)
- [Replay](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/replay.json)
- [Terminal state](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/terminal-state.json)
