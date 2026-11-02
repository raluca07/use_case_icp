# Haiku pilot, 2 Nov 2026

Reviewer: claude-haiku-5-5 (effort medium) via isolated `claude -p`. 23 frozen instances (manifest sha256 ba9299df7bcfd796e416db0ac3f2c14fe1f66210145a34dce79673842def9675) over 7 AppWorld task generators: 9 persistent faults, 5 non-persistent faults, 9 clean twins. 7 evidence arms, plus 3 repeats of arms B and C on 10 instances. 220 of 221 calls completed (1 network failure, scored as a miss). Full analysis: `docs/pilot_results.md`. Per-review scores: `scores.jsonl` (metrics and ids only, no AppWorld data).

## In plain words

An assistant did a job in someone's apps and made one mistake. In "persistent" cases it later fixed the mistake, but other records it had already built from the wrong value stayed wrong. A reviewer model is told "this record looks wrong" and must say where the problem started. We change only what evidence the reviewer sees.

- Seeing only the end result (arm A), the reviewer finds the starting point 2 times out of 14. The mistake is truly hidden in the output, so the test is hard enough.
- Seeing the step-by-step log (arm B), it finds it 10 out of 14 times.
- Seeing the log plus the graph of which step fed which (arm G), it finds it 12 out of 14 times. On the persistent cases the gain is largest: 8 out of 9 with the graph, 5 out of 9 without. On the non-persistent cases the log alone already gets 5 out of 5.
- But a deliberately wrong graph (arm F) works almost as well as the real one (9 versus 10 out of 14). So we cannot yet claim the graph's connections are what helps; it may just be seeing the steps listed again.
- With the graph alone (arm C), the reviewer often calls clean cases broken (5 of 9), because it sees the mistake and the fix but does not reason about their order.

Sample sizes are tiny, so all of this is direction, not proof.

| Arm | Evidence | Detection | Origin found, faulty (14) | Persistent (9) | Non-persistent (5) | False alarm on clean (9) |
|---|---|---|---|---|---|---|
| A | output only | 61% | 2/14 | 0/9 | 2/5 | 4/9 |
| B | action log | 91% | 10/14 | 5/9 | 5/5 | 1/9 |
| C | full graph | 70% | 10/14 | 6/9 | 4/5 | 5/9 |
| D | 2-step neighbourhood | 74% | 3/14 | 0/9 | 3/5 | 1/9 |
| E | random slice | 70% | 3/14 | 0/9 | 3/5 | 3/9 |
| F | fake graph | 83% | 9/14 | 5/9 | 4/5 | 2/9 |
| G | log plus graph | 91% | 12/14 | 8/9 | 4/5 | 2/9 |

## Open issues

1. Missing control: log plus fake graph, to test whether the graph's connections matter.
2. AppWorld yields only 23 usable instances, because its tasks rarely build one record from another; the main run needs another fault source.
3. Haiku is unstable on the graph-only view: the same case gave the same answer in all 4 runs only 2 of 10 times (6 of 10 for the log).
