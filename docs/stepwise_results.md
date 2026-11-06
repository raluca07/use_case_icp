# Step-by-step arms on the Gate 2 pilot set

Raluca asked (2 Nov 2026) whether the reviewer takes the whole graph or walks it step by step. Every arm A to M is one shot. Arm N starts from the reported record and expands one visible node per round, for at most 6 rounds, and may stop early. Arm O is the same walk but must use all 6 expansions. Both then answer with the standard prompt and schema over the explored part. Same frozen 23 instances (9 persistent, 5 non-persistent, 9 clean), same model (`claude-haiku-5-5`, effort `medium`). Other arms are their existing main reviews, not re-run. A failed or missing review is a miss (intention to treat). Distance is the number of graph edges from the reported record to the origin (for a clean twin, to the same write), ignoring edge direction.

## 1. Origin hit

| Arm | Evidence | Origin hit (faulty) | 95% CI (generator bootstrap) | Persistent | Non-persistent | Detection (all) | Stale precision | Clean twins with false-stale claims | Failed |
|---|---|---|---|---|---|---|---|---|---|
| A | output only | 2/14 (14%) | 0% to 29% | 0/9 (0%) | 2/5 (40%) | 14/23 (61%) | 88% | 4/9 (44%) | 0 |
| B | full action log | 10/14 (71%) | 43% to 93% | 5/9 (56%) | 5/5 (100%) | 21/23 (91%) | 100% | 1/9 (11%) | 1 |
| C | full graph | 10/14 (71%) | 43% to 100% | 6/9 (67%) | 4/5 (80%) | 16/23 (70%) | 100% | 5/9 (56%) | 0 |
| D | symptom neighbourhood | 3/14 (21%) | 0% to 50% | 0/9 (0%) | 3/5 (60%) | 17/23 (74%) | 79% | 1/9 (11%) | 0 |
| G | log + graph | 12/14 (86%) | 71% to 100% | 8/9 (89%) | 4/5 (80%) | 21/23 (91%) | 92% | 2/9 (22%) | 0 |
| J | graph without arguments | 6/14 (43%) | 14% to 71% | 2/9 (22%) | 4/5 (80%) | 18/23 (78%) | 83% | 4/9 (44%) | 0 |
| K | neighbourhood + source | 9/14 (64%) | 29% to 93% | 5/9 (56%) | 4/5 (80%) | 16/23 (70%) | 100% | 4/9 (44%) | 0 |
| N | step by step from the symptom, may stop early | 3/14 (21%) | 0% to 50% | 0/9 (0%) | 3/5 (60%) | 16/23 (70%) | 67% | 4/9 (44%) | 0 |

## 2. Paired contrasts on origin hit

Exact two-sided sign test on the discordant pairs, paired by instance. Descriptive only: n is tiny, instances within a generator are not independent, and nothing is corrected for multiplicity.

| Contrast | Question | Group | X rate | Y rate | X only right | Y only right | Sign test p |
|---|---|---|---|---|---|---|---|
| N vs C | walking against the whole graph in one prompt | faulty | 3/14 (21%) | 10/14 (71%) | 0 | 7 | 0.016 |
| N vs C |  | persistent | 0/9 (0%) | 6/9 (67%) | 0 | 6 | 0.031 |
| N vs C |  | nonpersistent | 3/5 (60%) | 4/5 (80%) | 0 | 1 | 1.000 |
| N vs D | walking against the fixed 2-hop neighbourhood | faulty | 3/14 (21%) | 3/14 (21%) | 0 | 0 | 1.000 |
| N vs D |  | persistent | 0/9 (0%) | 0/9 (0%) | 0 | 0 | 1.000 |
| N vs D |  | nonpersistent | 3/5 (60%) | 3/5 (60%) | 0 | 0 | 1.000 |
| N vs K | walking against the neighbourhood with the source forced in | faulty | 3/14 (21%) | 9/14 (64%) | 0 | 6 | 0.031 |
| N vs K |  | persistent | 0/9 (0%) | 5/9 (56%) | 0 | 5 | 0.062 |
| N vs K |  | nonpersistent | 3/5 (60%) | 4/5 (80%) | 0 | 1 | 1.000 |
| N vs B | walking the graph against the full action log | faulty | 3/14 (21%) | 10/14 (71%) | 0 | 7 | 0.016 |
| N vs B |  | persistent | 0/9 (0%) | 5/9 (56%) | 0 | 5 | 0.062 |
| N vs B |  | nonpersistent | 3/5 (60%) | 5/5 (100%) | 0 | 2 | 0.500 |
| N vs A | walking against no graph | faulty | 3/14 (21%) | 2/14 (14%) | 2 | 1 | 1.000 |
| N vs A |  | persistent | 0/9 (0%) | 0/9 (0%) | 0 | 0 | 1.000 |
| N vs A |  | nonpersistent | 3/5 (60%) | 2/5 (40%) | 2 | 1 | 1.000 |

## 3. The walks

Arm N: walks recorded 23 of 23.

- Faulty instances where no walk can reach the origin (no path in the graph): 2 of 14. Origin hit there anyway: 0.
- Reachable faulty instances where the walk brought the origin into view: 8/12 (67%). Origin hit when it was in view: 3/8 (38%); when it was not: 0/4 (0%).
- Walks that stopped by choice: 20 of 23; by the budget: 3. Nodes expanded per walk, median: 3. Requests that could not be done (not visible or already expanded): 13 in all.

| Instance | Variant | Distance | Rounds | Nodes expanded | Stopped by | Origin in view | Origin expanded | Origin hit |
|---|---|---|---|---|---|---|---|---|
| `22cc237_2_5acf9f0b94` | nonpersistent | 1 | 1 | 0 | answer | yes | no | yes |
| `22cc237_2_5b8fd385b7` | persistent | 3 | 2 | 1 | answer | no | no | no |
| `22cc237_2_f4332b9093` | clean | 3 | 4 | 3 | answer | yes | no |  |
| `34d9492_1_3934fbc442` | nonpersistent | 3 | 5 | 4 | answer | yes | no | no |
| `34d9492_1_3b7ec9a456` | persistent | 3 | 6 | 4 | answer | yes | no | no |
| `34d9492_1_77e7f5e65f` | clean | 3 | 6 | 4 | answer | yes | no |  |
| `37a8675_1_73f9f86557` | nonpersistent | 1 | 4 | 3 | answer | yes | yes | yes |
| `37a8675_2_9f5268227d` | nonpersistent | 1 | 3 | 2 | answer | yes | yes | yes |
| `68ee2c9_2_2360a28943` | persistent | 3 | 6 | 4 | budget | yes | no | no |
| `68ee2c9_2_2a42347f3c` | nonpersistent | 3 | 6 | 4 | budget | yes | no | no |
| `68ee2c9_2_a1bc62741d` | clean | 3 | 5 | 3 | answer | no | no |  |
| `692c77d_1_2232bbdd4f` | persistent | 3 | 2 | 1 | answer | no | no | no |
| `692c77d_1_5b354cfb52` | clean | 3 | 6 | 5 | budget | no | no |  |
| `692c77d_2_38c2133c7c` | persistent | 3 | 6 | 4 | answer | yes | no | no |
| `692c77d_2_ebbb1649f2` | clean | 3 | 5 | 4 | answer | yes | no |  |
| `6c2c621_1_5c28dabe1a` | clean | no path | 4 | 3 | answer | no | no |  |
| `6c2c621_1_69d38efae1` | persistent | no path | 3 | 1 | answer | no | no | no |
| `6c2c621_2_121e943576` | persistent | no path | 6 | 4 | answer | no | no | no |
| `6c2c621_2_14d82baca3` | clean | 5 | 4 | 3 | answer | no | no |  |
| `afc0fce_1_33cd4da941` | clean | 5 | 6 | 4 | answer | no | no |  |
| `afc0fce_1_9d8580042b` | persistent | 5 | 2 | 1 | answer | no | no | no |
| `afc0fce_3_355c37a137` | persistent | 5 | 1 | 0 | answer | no | no | no |
| `afc0fce_3_e7d989b242` | clean | 5 | 6 | 4 | answer | no | no |  |
