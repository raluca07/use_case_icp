# Detailed significance tables

## Method

The independent unit is the frozen data instance, not the model repetition. Each instance's three binary review results are averaged, and each arm contrast uses a two-sided exact paired sign-flip randomization test. `W/T/L` counts instances on which the left arm won, tied or lost. `Holm p` adjusts the six confirmatory comparisons within each outcome. Significance is two-sided `Holm p < 0.05`. Mechanism-level tests have only two independent instances and are therefore severely underpowered; their raw p-values are supplied for transparency and Holm adjusted within each mechanism. These are tests of arm differences, not tests that an arm's accuracy differs from zero.

## Confirmatory arm contrasts

| Outcome | Contrast (left − right) | Left | Right | Difference | W/T/L | Raw p | Holm p | Significant? |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Detection | Primary: Adaptive + semantics vs no graph (P05−P01) | 34/36 | 30/36 | +11.11 pp | 2/10/0 | 0.500 | 1.000 | No |
| Detection | Static compact graph vs no graph (P02−P01) | 33/36 | 30/36 | +8.33 pp | 2/10/0 | 0.500 | 1.000 | No |
| Detection | Semantics on static graph (P03−P02) | 30/36 | 33/36 | -8.33 pp | 0/10/2 | 0.500 | 1.000 | No |
| Detection | Adaptive disclosure vs static graph (P04−P02) | 33/36 | 33/36 | +0.00 pp | 1/10/1 | 1.000 | 1.000 | No |
| Detection | Adaptive + semantics vs static + semantics (P05−P03) | 34/36 | 30/36 | +11.11 pp | 2/10/0 | 0.500 | 1.000 | No |
| Detection | Adaptive + semantics vs equal-call reconsideration (P05−P06) | 34/36 | 28/36 | +16.67 pp | 4/8/0 | 0.125 | 0.750 | No |
| Correct job | Primary: Adaptive + semantics vs no graph (P05−P01) | 34/36 | 30/36 | +11.11 pp | 2/10/0 | 0.500 | 1.000 | No |
| Correct job | Static compact graph vs no graph (P02−P01) | 33/36 | 30/36 | +8.33 pp | 2/10/0 | 0.500 | 1.000 | No |
| Correct job | Semantics on static graph (P03−P02) | 30/36 | 33/36 | -8.33 pp | 0/10/2 | 0.500 | 1.000 | No |
| Correct job | Adaptive disclosure vs static graph (P04−P02) | 33/36 | 33/36 | +0.00 pp | 1/10/1 | 1.000 | 1.000 | No |
| Correct job | Adaptive + semantics vs static + semantics (P05−P03) | 34/36 | 30/36 | +11.11 pp | 2/10/0 | 0.500 | 1.000 | No |
| Correct job | Adaptive + semantics vs equal-call reconsideration (P05−P06) | 34/36 | 28/36 | +16.67 pp | 4/8/0 | 0.125 | 0.750 | No |
| Exact function | Primary: Adaptive + semantics vs no graph (P05−P01) | 34/36 | 30/36 | +11.11 pp | 2/10/0 | 0.500 | 1.000 | No |
| Exact function | Static compact graph vs no graph (P02−P01) | 33/36 | 30/36 | +8.33 pp | 2/10/0 | 0.500 | 1.000 | No |
| Exact function | Semantics on static graph (P03−P02) | 30/36 | 33/36 | -8.33 pp | 0/10/2 | 0.500 | 1.000 | No |
| Exact function | Adaptive disclosure vs static graph (P04−P02) | 33/36 | 33/36 | +0.00 pp | 1/10/1 | 1.000 | 1.000 | No |
| Exact function | Adaptive + semantics vs static + semantics (P05−P03) | 34/36 | 30/36 | +11.11 pp | 2/10/0 | 0.500 | 1.000 | No |
| Exact function | Adaptive + semantics vs equal-call reconsideration (P05−P06) | 34/36 | 28/36 | +16.67 pp | 4/8/0 | 0.125 | 0.750 | No |
| Control FP | Primary: Adaptive + semantics vs no graph (P05−P01) | 0/12 | 0/12 | +0.00 pp | 0/4/0 | 1.000 | 1.000 | No |
| Control FP | Static compact graph vs no graph (P02−P01) | 0/12 | 0/12 | +0.00 pp | 0/4/0 | 1.000 | 1.000 | No |
| Control FP | Semantics on static graph (P03−P02) | 0/12 | 0/12 | +0.00 pp | 0/4/0 | 1.000 | 1.000 | No |
| Control FP | Adaptive disclosure vs static graph (P04−P02) | 0/12 | 0/12 | +0.00 pp | 0/4/0 | 1.000 | 1.000 | No |
| Control FP | Adaptive + semantics vs static + semantics (P05−P03) | 0/12 | 0/12 | +0.00 pp | 0/4/0 | 1.000 | 1.000 | No |
| Control FP | Adaptive + semantics vs equal-call reconsideration (P05−P06) | 0/12 | 0/12 | +0.00 pp | 0/4/0 | 1.000 | 1.000 | No |

## Explanatory exact-localisation contrasts

These were added to explain the observed pattern and are not substitutes for the confirmatory comparisons.

| Contrast (left − right) | Left | Right | Difference | W/T/L | Raw p | Holm p | Significant? |
|---|---:|---:|---:|---:|---:|---:|---|
| Adaptive vs equal-call reconsideration, both without semantics (P04−P06) | 33/36 | 28/36 | +13.89 pp | 4/8/0 | 0.125 | 0.500 | No |
| Semantics on Adaptive (P05−P04) | 34/36 | 33/36 | +2.78 pp | 1/11/0 | 1.000 | 1.000 | No |
| Equal-call reconsideration vs static graph (P06−P02) | 28/36 | 33/36 | -13.89 pp | 0/8/4 | 0.125 | 0.500 | No |
| Adaptive + semantics vs static graph (P05−P02) | 34/36 | 33/36 | +2.78 pp | 1/10/1 | 1.000 | 1.000 | No |

## Exact localisation by mechanism

Each row compares only two independent instances (six repeated reviews per arm). No result in this table is significant.

| Mechanism | Contrast | Left | Right | Difference | W/T/L | Raw p | Holm p | Significant? |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Premature contribution rounding | P05−P01 | 4/6 | 0/6 | +66.67 pp | 2/0/0 | 0.500 | 1.000 | No |
| Premature contribution rounding | P02−P01 | 3/6 | 0/6 | +50.00 pp | 2/0/0 | 0.500 | 1.000 | No |
| Premature contribution rounding | P03−P02 | 0/6 | 3/6 | -50.00 pp | 0/0/2 | 0.500 | 1.000 | No |
| Premature contribution rounding | P04−P02 | 3/6 | 3/6 | +0.00 pp | 1/0/1 | 1.000 | 1.000 | No |
| Premature contribution rounding | P05−P03 | 4/6 | 0/6 | +66.67 pp | 2/0/0 | 0.500 | 1.000 | No |
| Premature contribution rounding | P05−P06 | 4/6 | 0/6 | +66.67 pp | 2/0/0 | 0.500 | 1.000 | No |
| Recorded-time snapshot substitution | P05−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Recorded-time snapshot substitution | P02−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Recorded-time snapshot substitution | P03−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Recorded-time snapshot substitution | P04−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Recorded-time snapshot substitution | P05−P03 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Recorded-time snapshot substitution | P05−P06 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Expiry compared with recorded time | P05−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Expiry compared with recorded time | P02−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Expiry compared with recorded time | P03−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Expiry compared with recorded time | P04−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Expiry compared with recorded time | P05−P03 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Expiry compared with recorded time | P05−P06 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Oldest repeated observation retained | P05−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Oldest repeated observation retained | P02−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Oldest repeated observation retained | P03−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Oldest repeated observation retained | P04−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Oldest repeated observation retained | P05−P03 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Oldest repeated observation retained | P05−P06 | 6/6 | 4/6 | +33.33 pp | 2/0/0 | 0.500 | 1.000 | No |
| Repeat ranking scoped only by source | P05−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Repeat ranking scoped only by source | P02−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Repeat ranking scoped only by source | P03−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Repeat ranking scoped only by source | P04−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Repeat ranking scoped only by source | P05−P03 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Repeat ranking scoped only by source | P05−P06 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Non-cumulative channel cap (Job 3) | P05−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Non-cumulative channel cap (Job 3) | P02−P01 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Non-cumulative channel cap (Job 3) | P03−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Non-cumulative channel cap (Job 3) | P04−P02 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Non-cumulative channel cap (Job 3) | P05−P03 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |
| Non-cumulative channel cap (Job 3) | P05−P06 | 6/6 | 6/6 | +0.00 pp | 0/2/0 | 1.000 | 1.000 | No |

## Interpretation

No confirmatory, explanatory or mechanism-level contrast reaches the prespecified two-sided 0.05 threshold. The observed graph gains are therefore descriptive estimates from this small experiment, not statistically established effects. Zero false positives in all arms means there is no observed specificity trade-off, but it also leaves no between-arm false-positive difference to test.
