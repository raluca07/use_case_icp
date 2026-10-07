# Paper Writer handover — Attempt 057 corrected results

Use this handover for the ICLR paper's Attempt 057 results. Do not quote the
frozen controller's 152/216 correct-job or exact-localisation totals: those
totals contain the documented Job-3 scorer error. Use the corrected reporting
layer linked below. Attempt 057's packages, receipts and frozen outputs remain
unchanged.

## Treatment definitions

Common to every arm: complete actual source for Jobs 1–4; actual top-level
inputs and parsed outputs for Jobs 1–4; Job-4 stdout/stderr only; the same
pipeline topology, marketing objective, review task and response contract.
Jobs 1–3 supplied no logs. The differences below are additions to that common
evidence.

- **P01:** complete source and top-level I/O for all four jobs, without graph or
  semantic labels.
- **P02:** P01 plus a compact native Etiq graph.
- **P03:** P02 plus coarse function-purpose semantics.
- **P04:** P02 plus required nested expansion and artifact inspection.
- **P05:** P04 plus coarse function-purpose semantics.
- **P06:** P02 plus two reconsideration calls that reveal no new evidence.

Reference: [arm table with full treatment text](cell-table.md#arm-level-results).

Representative frozen packages for the same `case-r01` instance:
[P01](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-4e61a93b3929e9c3/reviewer-package.json),
[P02](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-6469f8990209e542/reviewer-package.json),
[P03](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-f481d67028e2ec4b/reviewer-package.json),
[P04](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-45ccb4c59b9e4491/reviewer-package.json),
[P05](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-66de7ba695ecb0d8/reviewer-package.json), and
[P06](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/packages/brn-2d7ac66eb9cf24d6/reviewer-package.json).

## Claims that may be made

1. **Corrected overall performance was 188/216 for detection, correct-job
   attribution and exact-function localisation, with 0/72 clean-control false
   positives.** The equality of the three fault outcomes follows from the fact
   that every detected fault was also assigned to the correct job and exact
   function after the Job-3 correction. References: [correction evidence](scoring-correction.md)
   and [arm totals](cell-table.md#arm-level-results).

2. **The static compact graph had a small descriptive advantage over the
   no-graph arm:** P02 33/36 versus P01 30/36 exact. The gain was confined to
   the rounding mechanism and was not statistically significant (paired
   p=0.500; Holm p=1.000). References: [mechanism table](cell-table.md#exact-localisation-by-fault-mechanism)
   and [confirmatory significance row](significance-table.md#confirmatory-arm-contrasts).

3. **Required Adaptive disclosure did not improve on static compact graph
   evidence when semantics were held absent:** P04 and P02 were both 33/36,
   paired p=1.000. Reference: [confirmatory significance table](significance-table.md#confirmatory-arm-contrasts).

4. **Premature contribution rounding was the only consistently hard fault:**
   10/36 exact across arms, including P01 0/6 and a best arm result of P05 4/6.
   Five other mechanisms were at or near ceiling. References: [mechanism table](cell-table.md#exact-localisation-by-fault-mechanism)
   and [all instance cells](complete-result-cells.md).

5. **Semantic labels had no demonstrated benefit:** P03 was 30/36 versus P02
   33/36; P05 was 34/36 versus P04 33/36. Neither paired comparison was
   significant. References: [arm totals](cell-table.md#arm-level-results) and
   [significance table](significance-table.md#confirmatory-arm-contrasts).

6. **Additional calls without new evidence did not reproduce the best score:**
   P06 was 28/36 versus P02 33/36 and P05 34/36. The P05–P06 comparison was
   descriptive rather than significant (raw p=0.125; Holm p=0.750), and it is
   not a pure disclosure contrast because P05 also contains semantics.
   References: [arm totals](cell-table.md#arm-level-results), [confirmatory tests](significance-table.md#confirmatory-arm-contrasts)
   and [explanatory tests](significance-table.md#explanatory-exact-localisation-contrasts).

7. **Selection of the designated natural state was not shown to cause the
   result.** It occurred in 19/24 eligible Adaptive repeat-order/dedup reviews,
   but exact localisation was 19/19 when selected and 5/5 when not selected;
   the no-graph arm already scored 12/12 on those mechanisms. References:
   [complete cells](complete-result-cells.md) and [frozen selection details](natural-state-selections.json).

8. **Interactive evidence was substantially more expensive.** P02 used
   2,904,514 total tokens and 48 calls; P04 used 9,150,328 and 144 calls for the
   same 33/36 score; P05 used 9,218,638 and 144 calls for 34/36. References:
   [arm table](cell-table.md#arm-level-results) and [per-call accounting](per-call-token-latency.json).

9. **None of the prespecified between-arm effects was statistically
   significant.** Use descriptive language such as “observed,” “in this
   experiment,” and “did not establish”; do not write that graph or Adaptive
   evidence was proven superior. Reference: [complete significance report](significance-table.md).

## Required validity language

- The independent sample is 12 faulty instances plus four clean controls; the
  three model repetitions are repeated measurements.
- Mechanism-specific results have only two independent instances each and are
  underpowered. [Mechanism-level significance](significance-table.md#exact-localisation-by-mechanism)
- All arms received the same complete four-job source and top-level I/O. The
  experiment estimates what graph organization and interaction add on top of
  that common evidence; it is not a source-versus-graph test.
- The Job-3 scorer defect affected absolute correct-job and exact totals but not
  detection, false positives or any between-arm difference, because every arm
  gained six corrected Job-3 successes. [Correction note](scoring-correction.md)
- Do not pool Attempt 056. It remains a preserved partial run.

## Tables and raw references

- [Short corrected findings](findings.md)
- [Corrected aggregate and mechanism tables](cell-table.md)
- [All 96 result cells](complete-result-cells.md)
- [All 288 review rows with raw receipt paths and hashes](all-review-results-corrected.csv)
- [Significance table, including mechanism splits](significance-table.md)
- [Machine-readable correction manifest](corrected-rescore.json)
