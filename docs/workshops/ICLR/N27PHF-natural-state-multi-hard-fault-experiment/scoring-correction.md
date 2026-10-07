# Attempt 057 Job-3 scoring correction

## What was wrong

Attempt 057 contains two Job-3 channel-cap fault instances (`case-c01` and
`case-c02`). Their private truth records identify
`job_campaign_portfolio_generation / allocate_campaign_budget`, which is
reviewer-facing `job_3 / allocate_campaign_budget`. All 36 associated model
responses detected the fault and returned that exact job and function.

The inherited scorer nevertheless compared every faulty response with the
literal `job_1` and wrote `truth_job: job_1`. This is visible in
[`n27phb_experiment.py`](../../../../src/use_case_icp/n27phb_experiment.py),
while a representative private truth record is
[`case-c01.json`](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/qualification-private/instances/case-c01.json)
and a representative raw review is
[`trial-3ad7ba2881c8a417.json`](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/reviews/trial-3ad7ba2881c8a417.json).

## Deterministic correction

The reporting correction reads each frozen private instance truth and each
frozen review response, maps the canonical job IDs to the reviewer-facing
`job_1`–`job_4` aliases, and recomputes correct-job and exact-function scores.
It makes no model call and changes no package, response, capture or frozen
Attempt 057 file.

- Corrected review rows: 36/288, all from the two Job-3 faults.
- Corrections per arm: P01=6, P02=6, P03=6, P04=6, P05=6, P06=6.
- Correct-job attribution: 152/216 → 188/216.
- Exact-function localisation: 152/216 → 188/216.
- Detection remains 188/216; control false positives remain 0/72.
- Every arm gains exactly 6/36 correct-job and exact-function outcomes, so all
  paired between-arm differences and p-values remain unchanged.

## Preservation and audit trail

- Frozen source table SHA-256: `sha256:209c4a68e9e2b6dd16a350c86765b6b21a0fd39d92c76bd95296d5c203025e4e`
- Frozen source summary SHA-256: `sha256:a3da8eae3ee2f5fd9d3607475e273daaba29b8734bdd45f736d6a564d2560b10`
- [Corrected 288-review ledger](all-review-results-corrected.csv)
- [Corrected 96-cell table](complete-result-cells.md)
- [Correction manifest](corrected-rescore.json)

The original frozen [`summary.json`](../../../../outputs/fault-experiments-v2-2-n10/attempt-057/analysis/summary.json)
is preserved as the historical controller output and must not be quoted for
absolute correct-job or exact-function totals without this correction.
