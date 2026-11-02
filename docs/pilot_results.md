# Gate 2 Haiku pilot results

Model `claude-haiku-5-5`, effort `medium`, one fresh empty working directory per call. Frozen set of 23 instances (9 persistent, 5 non-persistent, 9 clean) over 7 generators, manifest sha256 `ba9299df7bcfd796e416db0ac3f2c14fe1f66210145a34dce79673842def9675`. Counts, names and mechanisms only; no AppWorld data values. A failed or missing review counts as a miss on every metric (intention to treat) and is also counted separately below.

## 1. Run facts

- Calls completed / planned: 220 / 221 (main reviews 161, repeats 60).
- Wall-clock start 2026-11-02 05:09:24 GMT, end 2026-11-02 08:19:33 GMT, 1 session(s), active time 3.17 h.
- Calls per hour sustained: 69.4 (220 new calls logged over the active time).
- Calls per hour excluding calls longer than 10 minutes: 229.8 (219 calls, 0.95 h). The sustained figure above is dragged down by the long calls; this one is the working rate.
- Calls over 10 minutes (they overlap a network outage or machine sleep, cause not recorded): 6c2c621_1_5c28dabe1a/B/rep0 failed took 7,238 s; 6c2c621_1_5c28dabe1a/C/rep0 done took 738 s.
- Failures per arm: A 0, B 1, C 0, D 0, E 0, F 0, G 0. A failed call is a miss on every metric (intention to treat). The one failure ended in an API connection error (DNS lookup failed), not a usage limit, and no usage limit was hit; it was not re-run.

| Arm | main input tokens, median / max | side-call tokens, median / max | wall s per call, median / max |
|---|---|---|---|
| A | 5,626 / 37,140 | 4,372 / 13,876 | 12 / 31 |
| B | 14,690 / 48,229 | 12,412 / 37,057 | 14 / 45 |
| C | 17,566 / 68,019 | 13,950 / 25,488 | 15 / 77 |
| D | 6,794 / 18,143 | 5,308 / 14,115 | 14 / 41 |
| E | 7,796 / 24,544 | 6,156 / 14,784 | 16 / 51 |
| F | 17,566 / 45,082 | 13,950 / 25,494 | 15 / 35 |
| G | 34,522 / 63,569 | 21,986 / 48,876 | 13 / 48 |

Main-call input tokens are input plus cache creation plus cache read from the envelope usage. Side-call tokens are every non-requested model in the envelope's modelUsage, all token kinds summed. Wall seconds are over all completed calls of the arm, repeats included.

## 2. Main table

Detection over all 23. Origin hit on the 14 faulty instances, split into 9 persistent and 5 non-persistent. Precision and recall are means over faulty instances where defined (precision needs at least one claim after removing the symptom and side-effect rows; a failed review scores 0 on both). False-stale count is the total of wrong claimed records on the 9 clean twins, with the number of clean instances that have any in brackets.

| Arm | Detection | Origin hit (faulty) | Origin hit (persistent) | Origin hit (non-persistent) | Stale precision (n defined) | Stale recall (n defined) | False-stale on clean | Clean rate | Named symptom on clean | Unknown labels | Failed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 14/23 (61%) | 2/14 (14%) | 0/9 (0%) | 2/5 (40%) | 88% (9) | 61% (12) | 38 claims (4 inst) | 4/9 (44%) | 7/9 (78%) | 0 | 0 |
| B | 21/23 (91%) | 10/14 (71%) | 5/9 (56%) | 5/5 (100%) | 100% (12) | 100% (12) | 35 claims (1 inst) | 1/9 (11%) | 1/9 (11%) | 0 | 1 |
| C | 16/23 (70%) | 10/14 (71%) | 6/9 (67%) | 4/5 (80%) | 100% (10) | 83% (12) | 53 claims (5 inst) | 5/9 (56%) | 4/9 (44%) | 0 | 0 |
| D | 17/23 (74%) | 3/14 (21%) | 0/9 (0%) | 3/5 (60%) | 79% (10) | 54% (12) | 1 claims (1 inst) | 1/9 (11%) | 5/9 (56%) | 0 | 0 |
| E | 16/23 (70%) | 3/14 (21%) | 0/9 (0%) | 3/5 (60%) | 89% (9) | 54% (12) | 37 claims (3 inst) | 3/9 (33%) | 6/9 (67%) | 0 | 0 |
| F | 19/23 (83%) | 9/14 (64%) | 5/9 (56%) | 4/5 (80%) | 99% (10) | 83% (12) | 36 claims (2 inst) | 2/9 (22%) | 3/9 (33%) | 0 | 0 |
| G | 21/23 (91%) | 12/14 (86%) | 8/9 (89%) | 4/5 (80%) | 92% (12) | 92% (12) | 46 claims (2 inst) | 2/9 (22%) | 2/9 (22%) | 0 | 0 |

## 3. Uncertainty

95% percentile intervals from a cluster bootstrap over generators: 7 clusters, 10,000 resamples, seed 2112145923 (zlib.crc32 of the constant `rdr-pilot-bootstrap-v1`). With only 7 clusters the intervals are wide and rough; read them as a range of what generator-level luck alone could produce, not as precise bounds.

| Arm | Origin hit (faulty) | 95% CI | Detection (all) | 95% CI |
|---|---|---|---|---|
| A | 2/14 (14%) | 0% to 29% | 14/23 (61%) | 39% to 77% |
| B | 10/14 (71%) | 43% to 93% | 21/23 (91%) | 81% to 100% |
| C | 10/14 (71%) | 43% to 100% | 16/23 (70%) | 57% to 80% |
| D | 3/14 (21%) | 0% to 50% | 17/23 (74%) | 59% to 86% |
| E | 3/14 (21%) | 0% to 50% | 16/23 (70%) | 61% to 79% |
| F | 9/14 (64%) | 36% to 86% | 19/23 (83%) | 64% to 96% |
| G | 12/14 (86%) | 71% to 100% | 21/23 (91%) | 81% to 100% |

## 4. Paired contrasts

Paired by instance, main reviews only. The sign test is exact and two-sided on the discordant pairs. It is descriptive: n is tiny, instances within a generator are not independent, and no multiplicity correction is applied.

| Contrast (X vs Y) | Metric | X rate | Y rate | X only right | Y only right | Sign test p |
|---|---|---|---|---|---|---|
| G vs B | origin hit | 12/14 (86%) | 10/14 (71%) | 3 | 1 | 0.625 |
| G vs B | detection | 21/23 (91%) | 21/23 (91%) | 1 | 1 | 1.000 |
| C vs A | origin hit | 10/14 (71%) | 2/14 (14%) | 8 | 0 | 0.008 |
| C vs A | detection | 16/23 (70%) | 14/23 (61%) | 3 | 1 | 0.625 |
| G vs C | origin hit | 12/14 (86%) | 10/14 (71%) | 3 | 1 | 0.625 |
| G vs C | detection | 21/23 (91%) | 16/23 (70%) | 6 | 1 | 0.125 |
| F vs C | origin hit | 9/14 (64%) | 10/14 (71%) | 1 | 2 | 1.000 |
| F vs C | detection | 19/23 (83%) | 16/23 (70%) | 4 | 1 | 0.375 |
| D vs C | origin hit | 3/14 (21%) | 10/14 (71%) | 0 | 7 | 0.016 |
| D vs C | detection | 17/23 (74%) | 16/23 (70%) | 5 | 4 | 1.000 |
| E vs D | origin hit | 3/14 (21%) | 3/14 (21%) | 0 | 0 | 1.000 |
| E vs D | detection | 16/23 (70%) | 17/23 (74%) | 1 | 2 | 1.000 |

G vs B asks what the graph adds to the log. C vs A asks what a graph adds to nothing. G vs C asks what the log adds to the graph. F vs C is the fake-graph control. D vs C is the neighbourhood against the full graph. E vs D is the random slice against the targeted one.

## 5. Repeat consistency

10 instances were repeated three more times on arms B and C: `22cc237_2_f4332b9093` (clean), `34d9492_1_77e7f5e65f` (clean), `37a8675_1_73f9f86557` (nonpersistent), `68ee2c9_2_2360a28943` (persistent), `68ee2c9_2_2a42347f3c` (nonpersistent), `68ee2c9_2_a1bc62741d` (clean), `692c77d_1_2232bbdd4f` (persistent), `692c77d_1_5b354cfb52` (clean), `692c77d_2_38c2133c7c` (persistent), `afc0fce_1_9d8580042b` (persistent). Agreement is on the origin_call value across the 4 runs (main plus 3 repeats); an instance with any failed run is left out of the agreement counts.

| Arm | Instances with 4 valid runs | All 4 runs name the same origin | Pairwise agreement | Origin hits in main / rep1 / rep2 / rep3 (of 10) |
|---|---|---|---|---|
| B | 10 | 6/10 (60%) | 46/60 (77%) | 4 / 4 / 2 / 2 |
| C | 10 | 2/10 (20%) | 33/60 (55%) | 4 / 4 / 3 / 6 |

## 6. Gate 2 pass rule

- Arm A origin hit 2/14 = 14%: below 80%.
- Arms with origin hit between 20% and 80% inclusive: B 71%, C 71%, D 21%, E 21%, F 64%.
- **Gate 2 origin-hit rule: PASS.**

## 7. Caveats

- Held-value fault model. All 9 persistent instances use held-value consumers: the agent keeps using the wrong value it had when it made the write W, and the wrong value does not travel from W to the stale records through the API. W is linked to the stale records through the repair's writes edge on W's row and through shared feeds sources, not through a W-to-consumer data edge. This is a fault of the agent's belief carried across calls.
- Arm C contains the origin node in all 14 faulty instances, and the rewritten-row cue (the repair rewrites W's row) names the origin of 9 of 9 persistent instances. Arm D's 2-hop neighbourhood around the symptom contains an edge of the origin in 0 of 9 persistent instances (3 of 5 non-persistent). Expect C and G to be strong and D to be weak on persistent faults by construction, so C vs D differences here do not show that the graph in general beats a neighbourhood.
- Only 7 generators contribute (the pilot set is 9 persistent, 5 non-persistent and 9 clean, not 20 / 10 / 10), at most 2 faulty instances per generator. Intervals and p-values are descriptive.
- The arm-A screen keeps only W positions that are not the first call of their API, a selection effect on instance shape. Package sizes are 10 to 100 times the Gate 0 smoke packages, so throughput here reflects long inputs.
