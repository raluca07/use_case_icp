# Plan 2 carry-over (from the Plan 1 final review, 1 Nov 2026)

Read together with `docs/gate0_findings.md` and the spec. Items here are decided or must be designed in Plan 2's first task, before any adapter code.

## Decisions taken by Fabio (1 Nov 2026)

1. Arm G (full action log plus full graph) exists so that G vs B isolates the graph's added value.
2. Faulty persistent instances must leave at least 2 stale records: `make_truth(..., min_stale=2)`.
3. H4 natural failures come from our own Claude agent runs (`claude -p`) on the train/dev tasks, executed through the instrumented adapter (logs alone lack responses and before-values). Collateral damage is a failed `no_op_pass` requirement, not `no_op_fail`.
4. The independence unit is the task generator (147 train/dev tasks = 49 generators of 3), not the task. Use cluster-robust tests, split pilot vs main by whole generator, and redo sizing with a design effect.
5. Exclude generators `3c13f5a` and `df61dc5` (nondeterministic across processes). Add a per-task determinism gate: gold run twice in separate processes with `PYTHONHASHSEED=0`, end states must be identical.

## Plan 2 Task 0: design before adapter code

- **C1, created-row id shifts.** Keep in-run labels as real `<app>.<table>#<id>` (read-edge matching and arm B responses depend on them). Give `stale_records` an alignment of created rows (faulty label to gold label) plus a canonicaliser that rewrites foreign-key columns and ids embedded in JSON payloads (e.g. `notifications.data`) into canonical keys before comparison. `Truth` stays in faulty in-run labels. First test: gold pays ann (txn#201) and settles expense with ref 201; faulty pays bob (txn#201), settles with ref 201, refunds 201, pays ann (txn#202). Expected: the expense is stale, ann's payment is not; the matching clean control equals gold. Use SQLModel `__table__.foreign_keys` to list FK columns.
- **I7, side-effect rows.** A wrong action plus its repair creates side-effect rows (notifications, bank transfers, mail, files). Neutralisation must allow partial-field expectations (subset match, e.g. `{"status": "refunded"}`) and a declared side-effect class excluded from stale; `min_stale` counts only non-side-effect rows. Design with C1.
- **I2, graph precision.** Map argument keys to tables from the AppWorld API parameter docs (so `user_id=3` cannot read `venmo.transactions#3`); in responses take numbers only under id keys (except bare scalar responses); take id-context strings of any length and normalise numeric strings; drop values that appear in more than k responses. Audit edge precision on the 147 gold replays before Gate 1 sign-off.
- **I6, matched symptoms.** Clean-control symptoms must be drawn from the faulty twin's stale set (mapped through the C1 alignment), and twins share the same `final_message`, so a reviewer cannot detect "clean" from the type of record named.

## Adapter recommendations

- One AppWorld per subprocess with `PYTHONHASHSEED=0`; run edited gold CODE (real control flow), not replayed recorded arguments: replaying recorded args after an injected create reuses fixed ids that now point at the wrong rows and manufactures stale records.
- Spike first (about 1 hour): hook the live `world.requester` to capture each response and a before/after diff of changed tables against an in-memory mirror, giving per-call attribution without one call per `world.execute` (Q5's constraint applies only to the file-based method). Q8 gap: retrieve `_r` via `world.shell.user_ns`.
- Snapshot DB state before `world.evaluate()` (evaluate re-points DB handles).
- Record response id types (int vs str); exclude supervisor/admin rows from "records the agent changed".

## Instance build and analysis

- Build all arms plus the rewired package atomically, or none; a leakage hit in any arm excludes the instance from every arm. Log exclusions by reason and template.
- Cheap non-LLM screen per instance (e.g. "earliest call that wrote a now-refunded row") to drop instances arm A could solve trivially before spending reviewer calls (Attempt 057's ceiling came from exactly this).
- H3 scoring: besides `followed_decoy`, score "moved off origin" relative to the same instance in arm C (`rewire_one` moves the symptom's writer, not the origin).
- `D_HOPS` is a parameter: as the origin-to-symptom distance dial grows, a fixed 2-hop D excludes the origin by construction; record hops used.
- Seeds: `choose_symptom`, arm E and arm F all draw from `Random(crc32(instance_id))`; salting per purpose would need the global seed constraint amended (low impact, Fabio's call).
