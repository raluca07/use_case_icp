# Attempt 041 — source, declarations, and hard-fault findings

## Purpose

This report explains how exact upstream-function localisation changed across
all combinations of:

- no separate source bundle (`S0`) versus a complete Job-1 and Job-2 source
  bundle (`S1`);
- no separate semantic declarations (`B0`) versus the six-function semantic
  declaration bundle (`B1`); and
- Current, History, Empty Graph, Compact Fixed, Adaptive, and Reconsideration
  evidence modes.

The primary outcome is exact localisation of the injected Job-1 function.
Each table entry is the number of exact localisations out of three reviewer
repetitions. The full cell-level detection, Job-1 attribution, exact
localisation, false-positive, token, and cost results are in the
[comprehensive reference tables](01-comprehensive-results-and-tables.md#5-complete-confirmatory-cell-results).

`S0` means **no separate complete source bundle**, not necessarily zero source.
Compact graph packages under S0 still contained approximately 1,206 tokens of
source naturally embedded in real Etiq nodes. See the
[actual package-exposure table](01-comprehensive-results-and-tables.md#11-actual-initial-package-exposure).

## Complete exact-localisation split

### S0-B0: no separate source and no declarations

| Fault | Current | History Empty | History Full | Etiq Empty | Fixed | Adaptive | Reconsider |
|---|---:|---:|---:|---:|---:|---:|---:|
| Threshold omission | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Provenance join identity | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Wrong source weight | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Top-record omission | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Middle-record omission | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Provenance ranking reversal | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| **Total** | **0/18** | **0/18** | **0/18** | **0/18** | **18/18** | **18/18** | **18/18** |

This is the largest observed separation. Current and Empty Graph both scored
0/18, so empty graph-review framing did not cause the result. Compact Fixed,
Adaptive, and Reconsideration all scored 18/18. However, the graph treatment
added a package of function identities, embedded source, captured values, and
group descriptions—not connectivity alone.

### S0-B1: no separate source, declarations supplied

| Fault | Current | History Empty | History Full | Etiq Empty | Fixed | Adaptive | Reconsider |
|---|---:|---:|---:|---:|---:|---:|---:|
| Threshold omission | 2/3 | 2/3 | 2/3 | 1/3 | 1/3 | 1/3 | 0/3 |
| Provenance join identity | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Wrong source weight | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Top-record omission | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Middle-record omission | 0/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| Provenance ranking reversal | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| **Total** | **5/18** | **5/18** | **5/18** | **4/18** | **16/18** | **16/18** | **15/18** |

Declarations helped non-graph reviewers name the ranking-reversal fault and
sometimes the threshold fault. They did not localise the other four functions.
Graph evidence remained much stronger, although declarations reduced graph-arm
performance on the threshold omission.

### S1-B0: complete source, no declarations

| Fault | Current | History Empty | History Full | Etiq Empty | Fixed | Adaptive | Reconsider |
|---|---:|---:|---:|---:|---:|---:|---:|
| Threshold omission | 0/3 | 0/3 | 0/3 | 0/3 | 2/3 | 3/3 | 3/3 |
| Provenance join identity | 2/3 | 2/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Wrong source weight | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Top-record omission | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Middle-record omission | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Provenance ranking reversal | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| **Total** | **14/18** | **14/18** | **13/18** | **15/18** | **17/18** | **18/18** | **18/18** |

Complete source solved all four easier fault mechanisms. Remaining differences
were confined to threshold omission and provenance join identity.

### S1-B1: complete source and declarations

| Fault | Current | History Empty | History Full | Etiq Empty | Fixed | Adaptive | Reconsider |
|---|---:|---:|---:|---:|---:|---:|---:|
| Threshold omission | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 1/3 | 2/3 |
| Provenance join identity | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Wrong source weight | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Top-record omission | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Middle-record omission | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Provenance ranking reversal | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| **Total** | **14/18** | **15/18** | **15/18** | **15/18** | **15/18** | **16/18** | **17/18** |

Source and declarations already provided extensive semantic information. Static
compact graph evidence did not improve on the Empty Graph placebo. Additional
passes recovered some threshold cases, but Reconsideration exceeded Adaptive.

## Cross-factor comparisons

### Graph evidence by source setting

The B0 and B1 rows are pooled here only for orientation. The four tables above
retain the fully separated results.

| Source setting | Current | Etiq Empty | Compact Fixed |
|---|---:|---:|---:|
| No separate source, S0 | 5/36 | 4/36 | 34/36 |
| Complete source, S1 | 28/36 | 30/36 | 32/36 |

The compact Etiq package was decisive when no separate source was present.
With complete source, its incremental benefit was much smaller because source
already solved four fault mechanisms.

### Substantive baseline and placebo decomposition

C01 Current is the ordinary no-graph baseline. C04 Etiq Empty is the graph-
framing placebo. C05 Compact Fixed adds real compact Etiq evidence.

| Setting | Current | Etiq Empty | Compact Fixed | Fixed−Current | Empty−Current | Fixed−Empty |
|---|---:|---:|---:|---:|---:|---:|
| S0-B0 | 0/18 | 0/18 | 18/18 | +18 | 0 | +18 |
| S0-B1 | 5/18 | 4/18 | 16/18 | +11 | -1 | +12 |
| S1-B0 | 14/18 | 15/18 | 17/18 | +3 | +1 | +2 |
| S1-B1 | 14/18 | 15/18 | 15/18 | +1 | +1 | 0 |

The paired uncertainty estimates for these contrasts are in the
[prespecified contrast tables](01-comprehensive-results-and-tables.md#8-prespecified-paired-contrasts-primary-exact-function-outcome).

## Hard-fault conclusions

### Threshold omission

The threshold mutation remained internally coherent: the source visibly used
`demand_score >= 6`, so excluding the score-5 record looked intentional. Source
showed how the program behaved but did not independently establish why that
selection policy was wrong.

| Arm, pooled over S/B settings | Exact threshold localisation |
|---|---:|
| Current | 2/12 |
| Etiq Empty | 1/12 |
| Compact Fixed | 6/12 |
| Adaptive | 8/12 |
| Reconsideration | 8/12 |

With complete source specifically, Current and Empty Graph both scored 0/6,
Compact Fixed scored 2/6, Adaptive 4/6, and Reconsideration 5/6. Compact graph
evidence made the disappearance of `n06-r06` between the original corpus and
the Job-2 handoff salient. Because Reconsideration matched or exceeded
Adaptive, the extra recoveries cannot be attributed specifically to nested
disclosure.

### Provenance join identity

This was primarily an attribution problem. Reviewers usually detected an
anomaly but could not determine where the identity corruption originated.

| Arm, pooled over S/B settings | Exact provenance-join localisation |
|---|---:|
| Current | 4/12 |
| Etiq Empty | 6/12 |
| Compact Fixed | 12/12 |
| Adaptive | 12/12 |
| Reconsideration | 12/12 |

Under S0, Current and Empty Graph both scored 0/6 while every compact graph arm
scored 6/6. This is a strong graph-package result. Under S1, Current scored 4/6
and Empty Graph already scored 6/6, so the source-present difference cannot be
assigned specifically to graph contents.

The complete per-fault tables are in the
[fault-mechanism reference section](01-comprehensive-results-and-tables.md#9-fault-mechanism-splits).

## Other conclusions

1. **Four faults were solved by source alone.** Current scored 6/6 with complete
   source for wrong source weight, both normalization omissions, and provenance
   ranking reversal. Graph evidence had no remaining room to improve them.
2. **Declarations were a partial substitute, not an additive improvement.**
   They moved Current from 0/18 to 5/18 under S0 but moved Compact Fixed from
   18/18 to 16/18. The graph-arm losses were entirely threshold cases.
3. **History showed no stable advantage.** History Full tied History Empty in
   three settings and trailed it by one exact review in S1-B0.
4. **The empty-graph placebo was small and fault-specific.** Its two
   source-present gains were provenance-join reviews; it never recovered the
   threshold fault.
5. **Adaptive disclosure did not outperform another reasoning pass.** Fixed,
   Adaptive, and Reconsideration scored 18/18, 18/18, and 18/18 at S0-B0;
   16/18, 16/18, and 15/18 at S0-B1; 17/18, 18/18, and 18/18 at S1-B0; and
   15/18, 16/18, and 17/18 at S1-B1.

The full Adaptive pre/post and selected-group results are in the
[Adaptive reference tables](01-comprehensive-results-and-tables.md#10-adaptive-disclosure-results).

## Overall interpretation

Attempt 041 supports three bounded conclusions:

1. When a separate source bundle and declarations were unavailable, the
   compact Etiq evidence package was decisive: Current 0/18 versus Compact
   Fixed 18/18 at S0-B0.
2. When complete source was available, four faults were already solved. The
   remaining value of actual compact graph contents was concentrated in the
   threshold omission under B0.
3. The study supports compact captured execution evidence as a package, but it
   does not isolate graph connectivity or demonstrate a unique benefit from
   nested Adaptive expansion. Graph nodes also contained source, function
   identities and captured values, while a no-evidence second pass matched
   Adaptive.

## Authoritative references

- [Comprehensive report and all aggregate tables](01-comprehensive-results-and-tables.md)
- [All 1,092 trial outcomes](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/results-by-cell.csv)
- [All 168 paired contrast records](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/summary.json)
- [Adaptive transition ledger](../../../outputs/fault-experiments-v2-2-n10/attempt-041/analysis/adaptive-transitions.csv)
- [Package exposure manifest](../../../outputs/fault-experiments-v2-2-n10/attempt-041/package-exposure-manifest.json)
- [Frozen experiment definition](../../../outputs/fault-experiments-v2-2-n10/attempt-041/experiment-freeze.json)
- [Replay verification](../../../outputs/fault-experiments-v2-2-n10/attempt-041/replay.json)
- [Terminal state](../../../outputs/fault-experiments-v2-2-n10/attempt-041/terminal-state.json)
