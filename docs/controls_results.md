# Control arms H to M on the Gate 2 pilot set

Raluca's review of the pilot (6 Nov 2026) asked whether inputs alone are enough and asked for arms with the source present in both graph and non-graph evidence. Six control arms answer that on the same frozen 23 instances (9 persistent, 5 non-persistent, 9 clean), same model (`claude-haiku-5-5`, effort `medium`), one main review each. Arms A to G are the pilot's own main reviews, not re-run. The anchor call is the origin, or in a clean twin the same write position. Counts, names and mechanisms only. A failed or missing review is a miss (intention to treat).

## 1. Origin hit by arm

| Arm | Evidence | Origin hit (faulty) | 95% CI (generator bootstrap) | Persistent | Non-persistent | Detection (all) | Stale precision | Clean twins with false-stale claims | Failed |
|---|---|---|---|---|---|---|---|---|---|
| A | output only | 2/14 (14%) | 0% to 29% | 0/9 (0%) | 2/5 (40%) | 14/23 (61%) | 88% | 4/9 (44%) | 0 |
| B | full action log | 10/14 (71%) | 43% to 93% | 5/9 (56%) | 5/5 (100%) | 21/23 (91%) | 100% | 1/9 (11%) | 1 |
| C | full graph | 10/14 (71%) | 43% to 100% | 6/9 (67%) | 4/5 (80%) | 16/23 (70%) | 100% | 5/9 (56%) | 0 |
| D | symptom neighbourhood | 3/14 (21%) | 0% to 50% | 0/9 (0%) | 3/5 (60%) | 17/23 (74%) | 79% | 1/9 (11%) | 0 |
| E | random slice matched to D | 3/14 (21%) | 0% to 50% | 0/9 (0%) | 3/5 (60%) | 16/23 (70%) | 89% | 3/9 (33%) | 0 |
| F | fake graph | 9/14 (64%) | 36% to 86% | 5/9 (56%) | 4/5 (80%) | 19/23 (83%) | 99% | 2/9 (22%) | 0 |
| G | log + graph | 12/14 (86%) | 71% to 100% | 8/9 (89%) | 4/5 (80%) | 21/23 (91%) | 92% | 2/9 (22%) | 0 |
| H | log + fake graph | 9/14 (64%) | 36% to 86% | 4/9 (44%) | 5/5 (100%) | 22/23 (96%) | 83% | 1/9 (11%) | 0 |
| I | call inputs only | 10/14 (71%) | 43% to 100% | 6/9 (67%) | 4/5 (80%) | 18/23 (78%) | 100% | 2/9 (22%) | 0 |
| J | graph without arguments | 6/14 (43%) | 14% to 71% | 2/9 (22%) | 4/5 (80%) | 18/23 (78%) | 83% | 4/9 (44%) | 0 |
| K | neighbourhood + source | 9/14 (64%) | 29% to 93% | 5/9 (56%) | 4/5 (80%) | 16/23 (70%) | 100% | 4/9 (44%) | 0 |
| L | random slice + source, matched to K | 9/14 (64%) | 36% to 86% | 5/9 (56%) | 4/5 (80%) | 20/23 (87%) | 99% | 1/9 (11%) | 0 |
| M | graph without the source | 2/14 (14%) | 0% to 29% | 0/9 (0%) | 2/5 (40%) | 20/23 (87%) | 100% | 2/9 (22%) | 0 |

## 2. Paired contrasts on origin hit

Exact two-sided sign test on the discordant pairs, paired by instance. Descriptive only: n is tiny, instances within a generator are not independent, and nothing is corrected for multiplicity.

| Contrast | Question | Group | X rate | Y rate | X only right | Y only right | Sign test p |
|---|---|---|---|---|---|---|---|
| J vs C | structure only against the full graph: do the arguments in the labels carry C? | faulty | 6/14 (43%) | 10/14 (71%) | 0 | 4 | 0.125 |
| J vs C |  | persistent | 2/9 (22%) | 6/9 (67%) | 0 | 4 | 0.125 |
| J vs C |  | nonpersistent | 4/5 (80%) | 4/5 (80%) | 0 | 0 | 1.000 |
| J vs A | structure only against nothing: does graph structure alone help? | faulty | 6/14 (43%) | 2/14 (14%) | 4 | 0 | 0.125 |
| J vs A |  | persistent | 2/9 (22%) | 0/9 (0%) | 2 | 0 | 0.500 |
| J vs A |  | nonpersistent | 4/5 (80%) | 2/5 (40%) | 2 | 0 | 0.500 |
| I vs B | inputs only against the full log: do responses add anything? | faulty | 10/14 (71%) | 10/14 (71%) | 1 | 1 | 1.000 |
| I vs B |  | persistent | 6/9 (67%) | 5/9 (56%) | 1 | 0 | 1.000 |
| I vs B |  | nonpersistent | 4/5 (80%) | 5/5 (100%) | 0 | 1 | 1.000 |
| I vs A | inputs only against nothing | faulty | 10/14 (71%) | 2/14 (14%) | 8 | 0 | 0.008 |
| I vs A |  | persistent | 6/9 (67%) | 0/9 (0%) | 6 | 0 | 0.031 |
| I vs A |  | nonpersistent | 4/5 (80%) | 2/5 (40%) | 2 | 0 | 0.500 |
| I vs C | inputs only against the full graph | faulty | 10/14 (71%) | 10/14 (71%) | 0 | 0 | 1.000 |
| I vs C |  | persistent | 6/9 (67%) | 6/9 (67%) | 0 | 0 | 1.000 |
| I vs C |  | nonpersistent | 4/5 (80%) | 4/5 (80%) | 0 | 0 | 1.000 |
| G vs H | log + real graph against log + fake graph: the graph's added value, controlled | faulty | 12/14 (86%) | 9/14 (64%) | 4 | 1 | 0.375 |
| G vs H |  | persistent | 8/9 (89%) | 4/9 (44%) | 4 | 0 | 0.125 |
| G vs H |  | nonpersistent | 4/5 (80%) | 5/5 (100%) | 0 | 1 | 1.000 |
| K vs D | neighbourhood with the source forced in against the plain neighbourhood | faulty | 9/14 (64%) | 3/14 (21%) | 6 | 0 | 0.031 |
| K vs D |  | persistent | 5/9 (56%) | 0/9 (0%) | 5 | 0 | 0.062 |
| K vs D |  | nonpersistent | 4/5 (80%) | 3/5 (60%) | 1 | 0 | 1.000 |
| K vs L | targeted against random slice, source present in both | faulty | 9/14 (64%) | 9/14 (64%) | 2 | 2 | 1.000 |
| K vs L |  | persistent | 5/9 (56%) | 5/9 (56%) | 2 | 2 | 1.000 |
| K vs L |  | nonpersistent | 4/5 (80%) | 4/5 (80%) | 0 | 0 | 1.000 |
| C vs M | full graph against the same graph with the source removed | faulty | 10/14 (71%) | 2/14 (14%) | 8 | 0 | 0.008 |
| C vs M |  | persistent | 6/9 (67%) | 0/9 (0%) | 6 | 0 | 0.031 |
| C vs M |  | nonpersistent | 4/5 (80%) | 2/5 (40%) | 2 | 0 | 0.500 |
| M vs A | graph without the source against nothing | faulty | 2/14 (14%) | 2/14 (14%) | 0 | 0 | 1.000 |
| M vs A |  | persistent | 0/9 (0%) | 0/9 (0%) | 0 | 0 | 1.000 |
| M vs A |  | nonpersistent | 2/5 (40%) | 2/5 (40%) | 0 | 0 | 1.000 |
