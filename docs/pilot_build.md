# Pilot build: AppWorld runs to frozen reviewer packages

Date: 2 Nov 2026. Branch `fabio-dev`. Counts, names and mechanisms only; no AppWorld data values appear here. All AppWorld-derived files (gold traces, runs, instances, packages, truths, audit rows) live under gitignored `runs/` and `appworld_root/`.

Result in one line: the pipeline works end to end and is tested, but the pilot set reaches 9 persistent, 5 non-persistent and 9 clean instances over 7 generators, not 20 / 10 / 10. AppWorld gold code almost never feeds one write into another, and only 14 of the 47 eligible generators have a write that the API docs let us repair. The cap of 2 faulty instances per generator then limits faulty instances to 14. The specified propagation mechanism needed a documented deviation, described in section 6.

## 1. Pipeline and commands

| Step | Module | Command (all via `.venv/bin/python`, `PYTHONPATH=src`) | Output |
|---|---|---|---|
| Gold runs and determinism gate | `rdr.gold` | `-m rdr.gold --workers 10` | `runs/gold/<task>/{trace,evaluation,failed_calls}.json`, `runs/gold/determinism.json` |
| Schema facts | `rdr.appworld_adapter.load_schema` | called by the builder | `runs/schema.json` (column names only) |
| Graph precision audit | `rdr.graph_audit` | `-m rdr.graph_audit --sample 240` | `runs/audit/graph_audit.json` |
| Instance build and freeze | `rdr.build_instances` | `-m rdr.build_instances --workers 10` | `runs/pilot/instances/`, `runs/pilot/exclusions.jsonl`, `runs/pilot/build_summary.json` |

No `claude -p` reviewer call was made.

## 2. Adapter (`src/rdr/appworld_adapter.py`)

- Each run happens in its own subprocess (`run_task`) with `PYTHONHASHSEED=0`, one world per process, a unique experiment name, and the experiment output directory removed afterwards. The world uses `raise_on_failure=False`, as `appworld verify` does: 11 of the 141 gold solutions inspect failure messages on purpose (Gate 0 Q2), and with the default they crash.
- The gold code runs unmodified (`compiled_solution_code` plus `solution(apis, requester)`). `world.requester.request` is replaced by a recorder, so every top-level `apis.<app>.<api>(...)` call is recorded with its app, API, arguments, response and HTTP status. Nested requester calls are passed through and are not recorded as separate calls.
- Per-call row writes come from a `before_cursor_execute` listener on every app engine. Before an UPDATE or DELETE, the listener reads the row it is about to change (the before image). Before an INSERT, it notes the table's highest rowid. When the call returns, the noted rows are read again (the after image), and rows above the noted rowid are the created rows. Only tables the call changed are read, so no copy of the 130 MB database is made. FTS shadow tables and the `record_hash` column are ignored.
- Supervisor and admin rows are kept out of `Call.writes`, so they are never among the records the agent changed. They still enter the end-state digest.
- Record labels are the real in-run `<app>.<table>#<id>`. The adapter returns `rdr.trace.Trace` with per-call `Write(before, after)`, plus the `world.evaluate()` dict, which is taken after the trace is captured because evaluate re-points the database handles (Q11).
- The plan, applied inside the hook so the gold code's control flow stays real, has five parts. `index/arg/value` corrupt one argument of one call (if the call at that index is not the expected API, the run is rejected). `repair` issues one call either immediately after the corrupted call or just before the final `supervisor.complete_task`, addressing W's row by its id or by fixed arguments. `held` covers the held-value deviation in section 6. `patch` changes what the code sees of one response, and is used only by the precision audit. A repair whose target row is absent is recorded, not raised.

## 3. Determinism gate

Eligible: the 141 train and dev tasks of 47 generators, after excluding generators `3c13f5a` and `df61dc5`. Each gold solution ran twice in separate processes. **141 of 141 pass**: both runs execute, pass `world.evaluate()`, reach the same end-state digest (every changed row, system rows included) and produce identical traces. Nondeterministic tasks are therefore not a source of loss.

## 4. Ground-truth alignment (`src/rdr/align.py`, carry-over C1 and I7)

- Created rows are rows whose first write in the run has no before image. They are aligned faulty to gold one table at a time. Exact pass: equal canonical final content, with the row's own id left out. Paired pass: rows left over on both sides are paired by the highest share of agreeing columns, with at least 0.5 agreement, as the same logical row written with different content. The two passes alternate until nothing changes. Unpaired faulty rows are extra rows. Unpaired gold rows are reported as missing, as `absent:<gold label>`.
- Canonicaliser rules:
  - The `id` of a created row becomes a token shared by aligned rows (`new:<faulty label>`).
  - Foreign-key columns come from SQLModel `__table__.foreign_keys`. A foreign key that names a created row becomes that row's token.
  - In JSON payload columns (SQLModel JSON type, for example `notifications.data`, `*_ids` lists), values under `<x>_id` / `<x>_ids` keys that name a created row of `<app>.<x>s` become that row's token. A `<x>_ids` column is treated the same way.
  - Ids of pre-existing rows are left unchanged, because the base database is the same in both runs.
  - `record_hash` is ignored.
- Gold rows are relabelled into faulty labels, and the existing `truth.stale_records` then compares the two runs. `Truth` stays in faulty in-run labels.
- Neutralised records accept a `truth.Partial` expectation (a subset match on some fields). The repaired row is checked this way: it must hold the gold value of the corrupted field.
- Clean-twin symptoms (carry-over I6) are drawn from the persistent twin's stale set. Each record is mapped to its gold label through the persistent alignment, then to the clean twin's label through the clean alignment, and kept only if the clean twin touched it. The choice is seeded by the clean instance id. Twins share `final_message`. Every variant reports the gold run's final message, so the agent always reports success.
- The carry-over toy (ann and bob payments with shifted ids) is the first test. The expense is stale, ann's payment is not, and the clean control equals gold.

## 5. Side-effect classes

Derived from Gate 0 Q6 (a balance top-up wrote venmo transfer rows plus gmail and file_system rows) and from the schema. A written row is a side effect when any of these holds:
- its table is `<app>.notifications` and the calling API is not a notification API (venmo, splitwise, todoist);
- its table is `venmo.bank_transfers` and the calling API is not a transfer or balance API;
- the row belongs to a different app than the calling API. This covers mail and files written as by-products.

Side-effect rows are excluded from stale and missing. `min_stale` counts only the remaining rows. Side-effect rows that differ are listed in the new `Truth.side_effect` field, and the scorer treats a reviewer naming one as neither a hit nor a false claim. No instance in the frozen pilot set has a side-effect row; notification rows in the chosen templates matched gold after alignment.

## 6. Injection rules and the deviation (`src/rdr/inject.py`)

**What the data showed.** The brief asked for a write W whose written value later gold writes consume through graph feeds or reads edges. On the 141 gold traces:
- 34 of 47 generators write anything at all, and 26 have two or more writes.
- Feeds or reads edges from one write call to a later write call appear in 10 tasks of 4 generators. The only real feed is a created playlist id passed to later song additions. Corrupting the playlist's title does not reach those rows, and repairing it leaves no stale state: 6 of 6 such persistent runs ended equal to gold.
- An empirical probe corrupted one argument of 177 gold writes without repair. 144 ran cleanly, and only 3 of them (2 generators) changed any later call's arguments. The other row differences were created-row id shifts, which the alignment removes.
- The reason is structural: gold code computes values once in local variables and writes them. It does not read its own writes back.

**Deviation (minimal, generic, documented).** Consumers are of two kinds:
1. Natural consumers: later write calls reached from W by feeds or reads edges. These are kept as specified, but no chosen instance relies on one.
2. Held-value consumers: later calls of the same API that passed the same value for the same argument, or for paths, a path under the same parent directory. This is the agent's held value, a loop-invariant variable in the gold code.

In the persistent and non-persistent variants, the hook gives these calls the wrong value from W until the repair (`Plan.held`). The agent keeps using the wrong value it had when it made W. In the clean twin the immediate repair closes that window, so nothing derives from the wrong value. All 9 chosen persistent instances use held-value consumers. Consequence for the paper: in these instances W is linked to the stale records through the repair's writes edge on W's row and through shared feeds sources, not by a W-to-consumer data edge.

**Rules (no per-task code).**
- Candidate W: any non-system gold write call whose response is not a failure. Arguments: scalars only, never credentials, pagination, or `source_*` paths.
- Wrong value by type:
  - booleans are flipped;
  - integer ids take another value under the same key seen in the run's responses;
  - other integers are shifted by 1;
  - floats get +10 (or +1 below 10);
  - text gets its first number incremented; otherwise another value under the same key from the responses, otherwise the last word is dropped (truncated text);
  - paths move to a sibling directory seen in the run, otherwise to the enclosing directory.
- Repair, resolved from the API docs. Field update: a PATCH API of W's app that takes the corrupted field and addresses W's row, either through a path id that maps to the row's table or through a required argument W also passed (such as a file path). APIs whose path ids map to another table are skipped. The restored field is the neutralised record (a `Partial` expectation). Relocation: for a corrupted destination of a call that creates the row, the app's move API (W's own first; copy APIs are never used, because they would leave the wrong file behind). The moved row is recreated, so nothing needs neutralising. W without a repair is skipped.
- Variants share the wrong action and the repair. Persistent: repair just before the final call. Clean twin: repair immediately after W, then `check_aligned_clean_control`. Non-persistent: no repair. Origin is W's call index in the faulty run, the same as in gold. Persistent instances need `min_stale=2` non-side-effect stale records; non-persistent need 1.
- Run validation: the run executes; the call at W is the planned call; W succeeds; the repair succeeds; no more calls fail than in gold; at least one held consumer received the wrong value (or there is a natural consumer); and the repair has a target, so the corruption changed a row.
- Positions: for each (task, template), the first, second, middle and last occurrence are run.

## 7. Instance builder (`src/rdr/build_instances.py`)

- Writes are atomic. Each instance is staged in full, with `trace.json`, `truth.json`, `gold_trace.json`, `meta.json` and `packages/A..G.txt`, then renamed into `runs/pilot/instances/<instance_id>/`. Instance ids are `<task>_<hash>` and carry no variant name.
- A leakage hit in any arm excludes the instance from every arm. Arm F gets `avoid_calls={origin}`, which is W for clean twins. Reads edges use the API-doc table map (section 9).
- Every exclusion goes to `runs/pilot/exclusions.jsonl` with its reason, template, variant and generator.
- Selection fills generator capacity (at most 2 faulty instances per generator, and different tasks before one task repeats), aiming at the requested 2:1 persistent to non-persistent ratio. Where a generator has room, the non-persistent twin of a chosen persistent instance's wrong action is preferred. Clean twins are taken from the chosen persistent instances.

## 8. Heuristic screen

The screen drops an instance when a cheap heuristic that sees only arm A's evidence names the origin. There are two such heuristics:
1. the earliest acting call whose API nouns cover the symptom table's nouns;
2. the earliest acting call whose API nouns cover those of the last acting call before the final call.

The brief's example heuristic (earliest call writing a row a later call changed) is computed but not used to drop. Every update repair rewrites W's row, so that heuristic names the origin of every persistent instance by construction. In the frozen set it names the origin of 9 of 9 persistent instances. That is the writes-edge cue that graph arms C, D and G can use; it does not show that arm A could solve them.

**Screen drops: 59 instances** (17 persistent, 42 non-persistent). Most non-persistent drops come from tasks where W is the first or only acting call of its API, which arm A can name from the call list.

## 9. Graph precision (carry-over I2, `src/rdr/graph.py`, `src/rdr/graph_audit.py`)

Rules:
- id-like arguments map to tables from the API docs, in this order: a path parameter whose preceding segment names a table, or the unique table ending in `_<segment>`; a foreign-key column of the same name; the pluralised key; a unique `_<stem>s` table, preferring the `user_` view. This resolves 225 of 251 id parameters by path or name; the rest resolve by foreign key or `user_` view, or get no reads edges.
- Numbers in responses count only under id keys, except bare scalar responses.
- Strings under id keys count at any length, and numeric strings normalise to numbers.
- A value returned by more than k = 2 calls makes no feeds edge.

Without the API-doc map, as in synthetic traces, reads edges keep the old behaviour, and all earlier graph tests pass unchanged.

Feeds audit, counterfactual oracle. A sample of 240 of the 12,322 uncut feeds edges was drawn from all 141 gold traces (seed 20261102). For each edge, the gold code was re-run with the matched value replaced by a sentinel in what the producer's response shows the code. An edge is true when the consumer's arguments pick up the sentinel or otherwise change. It is refuted when the consumer is unchanged, and excluded when the run no longer reaches that call.

| cut-off k | feeds edges kept | sampled, decided | true | precision (95% Wilson) |
|---|---|---|---|---|
| 1 | 980 | 24 | 21 | 0.875 (0.69 to 0.96) |
| **2 (chosen)** | **4,321** | **74** | **61** | **0.824 (0.72 to 0.89)** |
| 3 | 6,303 | 111 | 79 | 0.712 (0.62 to 0.79) |
| 5 | 9,335 | 165 | 92 | 0.558 |
| none | 12,322 | 201 | 99 | 0.493 |

k = 2 is the largest cut-off whose estimated precision stays above 0.8, and it keeps 62% of the true edges found without a cut-off (61 of 99).

Reads edges with the API-doc map: 453, against 595 with the old any-table matching (142 cross-table edges removed). 58 are confirmed by row evidence: the consumer writes a foreign key to the row, or its response holds the row's id beside another of the row's values. 395 are path-addressed, meaning the documented API path addresses that row by the argument. 0 are unverified. The reads-edge precision estimate is 453 of 453 by API contract, with 58 independently evidenced.

## 10. Pilot set (frozen)

Pilot generators (7): `22cc237`, `34d9492`, `37a8675`, `68ee2c9`, `692c77d`, `6c2c621`, `afc0fce`. The other 40 eligible generators are reserved for the main run, although only 7 of them have any candidate (section 11).

| Generator | persistent | non-persistent | clean |
|---|---|---|---|
| 22cc237 | 1 | 1 | 1 |
| 34d9492 | 1 | 1 | 1 |
| 37a8675 | 0 | 2 | 0 |
| 68ee2c9 | 1 | 1 | 1 |
| 692c77d | 2 | 0 | 2 |
| 6c2c621 | 2 | 0 | 2 |
| afc0fce | 2 | 0 | 2 |
| **total** | **9** | **5** | **9** |

By template:

| Template | persistent | non-persistent | clean |
|---|---|---|---|
| `file_system.move_file:destination_file_path` | 2 | 2 | 2 |
| `file_system.create_file:file_path` | 2 | 0 | 2 |
| `spotify.review_song:rating` | 2 | 0 | 2 |
| `venmo.create_transaction_comment:comment` | 2 | 0 | 2 |
| `venmo.create_payment_request:description` | 1 | 1 | 1 |
| `venmo.create_transaction:private` | 0 | 2 | 0 |

- 3 of the 5 non-persistent instances share their wrong action with a chosen persistent instance.
- Stale records per persistent instance: 2 to 18 (median 12). Per non-persistent instance: 1 to 19.
- Every persistent instance has its clean twin in the set.
- Valid but not selected (generator cap or ratio): 24 persistent, 67 non-persistent and 24 clean.

Manifest (`rdr.freeze.write_manifest` on `runs/pilot/instances/`): `MANIFEST.sha256.json` sha256 **`ba9299df7bcfd796e416db0ac3f2c14fe1f66210145a34dce79673842def9675`**. `verify_manifest` reports no problems.

## 11. Exclusions

| Reason | persistent | non-persistent | clean | total |
|---|---|---|---|---|
| heuristic screen | 17 | 42 | 0 | 59 |
| leakage: `repair` (a word in AppWorld content) | 4 | 6 | 0 | 10 |
| faulty run has only missing records | 0 | 8 | 0 | 8 |
| final state equals gold (create_playlist title: consumers reference the playlist by id) | 6 | 0 | 0 | 6 |
| fewer than 2 non-side-effect stale records | 5 | 0 | 0 | 5 |
| corrupted call changed no row the repair could address (no-op corruption) | 5 | 0 | 0 | 5 |
| corrupted call failed | 0 | 1 | 0 | 1 |

Candidates: 625 in 14 generators (9 persistent-capable). 129 were run, which covers every candidate of every generator that yielded nothing. The 496 not run are further positions in generators already at the cap; 333 of them are move_file positions in 2 generators. Running more candidates therefore cannot add instances under the cap.

Why 20 / 10 / 10 is out of reach:
- 33 eligible generators have no write that a PATCH or move API can repair. 13 of them write nothing at all. The other 20 write only likes, follows, removals, deletions, approvals and similar, and the brief says to skip such a W.
- Of the 14 generators with candidates, 7 yield no valid unscreened instance: single-write tasks are screened, the corruption is a no-op, or the title does not propagate.
- 7 generators × 2 = 14 faulty is the ceiling. The selection splits these 9 : 5, near the requested 2 : 1.

Neither the screen nor the leakage check was relaxed.

## 12. Package size (characters, frozen set of 23 instances)

| Arm | min | median | max |
|---|---|---|---|
| A | 1,427 | 9,030 | 34,920 |
| B | 5,577 | 28,643 | 99,327 |
| C | 2,440 | 32,358 | 66,761 |
| D | 1,958 | 11,280 | 35,555 |
| E | 2,094 | 13,323 | 37,580 |
| F | 2,440 | 32,349 | 66,760 |
| G | 6,590 | 51,971 | 131,168 |

These are 10 to 100 times the Gate 0 smoke packages (arm A 607 and arm C 1,251 characters). The largest G package is about 33k tokens. Long move_file traces (about 200 calls) dominate the maxima.

## 13. Concerns for the pilot and the main run

1. The main run's planned size (about 300 persistent instances, generator-clustered) is not reachable on AppWorld gold with this fault model. At most 14 generators can contribute, 7 on present yield. A different fault source is needed: tau-bench, our own agent runs (H4), or a repair model other than update-in-place.
2. All persistent instances depend on the held-value deviation. That is a fault of the agent's belief carried across calls, not data flow through the API. The paper must describe it as such.
3. The rewritten-row cue gives the origin away to graph arms (9 of 9). Arm D's 2-hop neighbourhood around the symptom contains no edge of the origin in 0 of 9 persistent instances (3 of 5 non-persistent), because held consumers are not adjacent to W. Arm C contains it in all 14. Expect C and G to be strong and D to be weak on persistent faults by construction.
4. The arm-A screen keeps only W positions that are not the first call of their API, which is a selection effect on instance shape.
5. Package sizes in arms B and G may raise token use well above the Q13 figures, so the subscription throughput measured at Gate 2 should use these packages.
