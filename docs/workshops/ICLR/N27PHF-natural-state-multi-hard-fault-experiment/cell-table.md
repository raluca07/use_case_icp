# Corrected aggregate and mechanism tables

The original frozen analysis mis-scored all Job-3 channel-cap reviews. The tables below recompute correct-job and exact-function outcomes from the preserved responses and the private instance truth. Detection, false positives, calls and tokens are unchanged. See [the correction note](scoring-correction.md).

## Arm-level results

| Arm | Treatment | Detection | Correct job | Exact function | Control FP | Calls | Total tokens |
|---|---|---:|---:|---:|---:|---:|---:|
| P01 | Source + all-job top-level I/O; no graph or semantics; one call | 30/36 (83.33%) | 30/36 (83.33%) | 30/36 (83.33%) | 0/12 (0.00%) | 48 | 1,369,728 |
| P02 | P01 + compact native Etiq graph; one call | 33/36 (91.67%) | 33/36 (91.67%) | 33/36 (91.67%) | 0/12 (0.00%) | 48 | 2,904,514 |
| P03 | P02 + coarse semantic labels; one call | 30/36 (83.33%) | 30/36 (83.33%) | 30/36 (83.33%) | 0/12 (0.00%) | 48 | 2,953,673 |
| P04 | P02 + required graph expansion and artifact inspection; three calls | 33/36 (91.67%) | 33/36 (91.67%) | 33/36 (91.67%) | 0/12 (0.00%) | 144 | 9,150,328 |
| P05 | P04 + coarse semantic labels; three calls | 34/36 (94.44%) | 34/36 (94.44%) | 34/36 (94.44%) | 0/12 (0.00%) | 144 | 9,218,638 |
| P06 | P02 + two no-new-evidence reconsiderations; three calls | 28/36 (77.78%) | 28/36 (77.78%) | 28/36 (77.78%) | 0/12 (0.00%) | 144 | 8,703,109 |

## Results by faulted job

The Job-3 row incorporates the deterministic truth-binding correction.

| Faulted job | Outcome | P01 | P02 | P03 | P04 | P05 | P06 |
|---|---|---:|---:|---:|---:|---:|---:|
| Job 1 | Detection | 24/30 | 27/30 | 24/30 | 27/30 | 28/30 | 22/30 |
| Job 1 | Correct job | 24/30 | 27/30 | 24/30 | 27/30 | 28/30 | 22/30 |
| Job 1 | Exact function | 24/30 | 27/30 | 24/30 | 27/30 | 28/30 | 22/30 |
| Job 3 | Detection | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| Job 3 | Correct job | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| Job 3 | Exact function | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |

## Exact localisation by fault mechanism

Each mechanism has two independent instances and three repeated reviews per instance.

| Mechanism | P01 | P02 | P03 | P04 | P05 | P06 |
|---|---:|---:|---:|---:|---:|---:|
| Premature contribution rounding | 0/6 | 3/6 | 0/6 | 3/6 | 4/6 | 0/6 |
| Recorded-time snapshot substitution | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| Expiry compared with recorded time | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| Oldest repeated observation retained | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 4/6 |
| Repeat ranking scoped only by source | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| Non-cumulative channel cap (Job 3) | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |

## Control false positives

| Arm | P01 | P02 | P03 | P04 | P05 | P06 |
|---|---:|---:|---:|---:|---:|---:|
| False positives | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 |

## Completeness

- [All 96 instance × arm result cells](complete-result-cells.md)
- [Machine-readable 96-cell table](complete-result-cells.csv)
- [All 288 corrected individual review rows](all-review-results-corrected.csv)
- [Detailed significance table](significance-table.md)
