# IJCAI 2027 test design: diagnosing stale state after agent repairs

Date: 1 Nov 2026. Status: design approved in brainstorming, pending spec review.
Target: IJCAI 2027 main track (abstract 4 Jan 2027, full paper 11 Jan 2027, 23:59 AoE; 7 body pages + 2 reference pages).
Working title: *When Repairs Don't Retract: Diagnosing Persistent Faults in Agentic Workflows from Execution Provenance*.

## 1. Why the tests change

Attempt 057 (use_case_icp, main, 7 Oct 2026) reached 188/216 exact localisation with source code and top-level I/O alone. Five of six fault mechanisms sat at ceiling, the compact graph added 3/36 (all rounding, paired p = 0.500), and the sample was 12 independent instances. The faults were visible in the source the reviewer already had, so the graph had nothing to add.

Five rules for every test in this design:

1. The fault is invisible in the final output and final state alone (arm A's evidence); finding its origin requires the run's history or graph.
2. Ground truth is fixed per role (origin, stale records, symptom) before any reviewer call.
3. Instances are generated, giving hundreds of independent cases.
4. Each test has a difficulty dial, so results are curves, not points.
5. A control shows the reviewer reads the graph's edges, not only extra tokens.

## 2. Data

- **AppWorld** (Trivedi et al., ACL 2024): 9 apps (venmo, splitwise, amazon, gmail, spotify, phone, file_system, simple_note, todoist), 457 APIs, 100+ database tables, about 100 simulated people. Agents act by writing Python in an IPython shell (`apis.<app>.<api>(...)`). Evaluation uses database-state unit tests that check for collateral damage. Per run it logs `api_calls.jsonl` and database changes against the base database. Released GPT-4o runs exist for train and dev.
  - Use **train and dev splits only**. The test split stays untouched.
  - Licence: code Apache-2.0; bundle-derived data must be redistributed encrypted and must not be posted in plain text or images. All AppWorld-derived packages stay local or encrypted, and no AppWorld record appears in a paper figure.
- **tau-bench** retail and airline (MIT licence): payment methods, refunds, travel certificates, released historical trajectories. Second domain, and the source of the worked example printed in the paper. The newer tau2/tau3 repository is checked before use because the original repository marks its tasks as outdated.

## 3. Reviewer evidence arms

Every package contains the task instruction, the agent's final message, a user report naming one record that looks wrong (the symptom: one stale record for faulty instances, a deterministically chosen correct record for clean controls), the final state of touched records, and the list of calls made (index and API name only, so every arm can name an origin). Arms add evidence on top:

| Arm | Added evidence |
|---|---|
| A | nothing (output only) |
| B | full action log as text: code and API responses in order |
| C | full provenance graph: actions, records written, records read |
| D | graph neighbourhood selected around the symptom |
| E | random graph slice matched on size and node type |
| F | fake graph with rewired edges |
| G | full action log plus full provenance graph (G vs B isolates the graph's added value) |

The reviewer answers three questions as JSON: (1) is anything wrong; (2) which action started it; (3) which records are still wrong.

## 4. Tests and hypotheses

Hypotheses are frozen in writing before the first reviewer call.

| Test | Instances | Measures | Hypothesis |
|---|---|---|---|
| Stale-data core | about 300 injected wrong-action + partial-repair faults (persistent; every faulty persistent instance must leave at least 2 stale records, enforced with `make_truth(..., min_stale=2)`; detection and origin still count on all instances), the same wrong actions with no repair (non-persistent contrast: origin and symptom coincide), and clean full-repair controls | detection; origin hit; stale-record precision and recall; false stale records on clean controls | H2: graph advantage is larger on persistent faults than on non-persistent ones |
| Graph vs history curve | N = 0, 5, 20, 50 unrelated actions spliced in | arm B vs arm C by N | H1: history wins at small N, graph wins at large N |
| Rewired edge | one write edge pointed at a decoy action | rate at which the answer moves to the decoy | H3: answers follow edges |
| Natural failures | released GPT-4o train/dev runs that fail collateral-damage tests | all arms | H4: H1 to H3 hold on faults nobody injected |

Dropped for page budget: bad-data-with-correct-code faults and masked double faults.

Independence: each AppWorld task is a cluster. Repeated reviewer runs are repeated measurements of one instance, not new instances.

## 5. Components

Each component reads and writes files; none calls another directly.

1. **AppWorld setup.** Python 3.11+, git LFS, `pip install appworld`, `appworld install`, `appworld download data`, plus released experiment outputs.
2. **Fault injector.** Edits a gold solution to insert a wrong action and a partial repair, then executes it in AppWorld. Ground truth is mechanical: origin = the injected action; stale records = rows where the final database differs from the gold run's final database. Clean controls insert the same action with a full repair; the injector rejects any control whose final state differs from gold. For the curve test it splices in N actions from other tasks and verifies, by database diff, that they never touch the stale records.
3. **Graph builder.** Executes one statement at a time and snapshots the database after each, attributing every write to its call. Read edges come from record IDs in API responses that later calls consume. Etiq (`etiq_copilot`, statement-level value capture) cannot see database rows behind the API layer, so this builder always supplies record nodes and write edges. A first-day spike decides whether call-to-call data-flow ("feeds") edges come from Etiq's captured lineage or from value matching between responses and later arguments; Raluca is told the result. Etiq ships a CPython 3.13 binary, so the project venv is Python 3.13.
4. **Evidence packager.** Builds arms A to G from the same run. A leakage check removes anything that reveals the injection (comments, variable names, unnatural repair wording).
5. **Reviewer runner.** One fresh isolated `claude -p` session per review:
   `claude -p <package> --model claude-haiku-5-5 --effort medium --tools "" --setting-sources "" --strict-mcp-config --system-prompt <reviewer prompt> --json-schema <answer schema> --no-session-persistence --output-format json`, run from an empty directory. Measured overhead of this recipe: about 630 tokens (the default `claude -p` loads about 36k tokens of user configuration and must not be used). Use full model IDs: the `haiku` alias serves Haiku 4.5. Temperature cannot be set on current models, so reproducibility is the pinned model ID, the pinned effort and repeated runs. Raw output, served model (`modelUsage`) and token usage are stored per call. The runner resumes after interruption and backs off on subscription limits.
6. **Scorer.** Deterministic, no LLM judge: detection, origin hit, stale-record precision and recall, false stale records, decoy-follow rate.
7. **Freeze and analysis.** Hypotheses, instances and packages are hashed and frozen before any reviewer call. Analysis treats the task as the cluster.

tau-bench reuses components 4 to 7, with its tool-call logs replacing components 2 and 3.

## 6. Pilot and gates

All pilot reviews use `claude-haiku-5-5` at effort `medium`. Sonnet 5.5 and Opus 5.5 are added only by a later decision.

- **Gate 0 (about 2 days, no reviewer calls).** AppWorld installed; gold solutions run; per-statement snapshots attribute writes; Etiq spike decides the graph source.
- **Gate 1 (about 3 days, no reviewer calls).** Three fault templates on about 10 tasks; every clean control matches gold; every faulty persistent instance leaves at least 2 stale records; leakage check passes.
- **Gate 2 (Haiku pilot, about 340 calls).** 30 faulty + 10 clean instances x 7 arms (280 calls), plus 10 instances x arms B and C x 3 repeats (60 calls), about 340 calls in all. Record tokens per call, time per call, sustainable calls per hour on the subscription, and per-arm accuracy. Pass rule for origin hit: at least one arm between 20% and 80%, and arm A below 80%. If arm A is at ceiling, raise N and origin-to-symptom distance and rerun; if all arms are near 0%, lower them. Pilot instances come from tasks excluded from the main analysis.
- **Gate 3 (sizing).** The pilot's between-arm discordance sets the main-run size. Planning figure: about 195 paired cases per contrast for a 10-point effect at 25% discordance (McNemar, alpha 0.05, power 0.8).

Calendar: weeks 1 to 2 gates 0 to 2; weeks 3 to 6 main runs and tau-bench; weeks 7 to 9 writing.

## 7. Open items and risks

- Etiq compatibility with AppWorld's execution shell (decided at gate 0).
- Subscription throughput for several thousand reviewer calls (measured at gate 2).
- AppWorld licence limits on figures and on any public benchmark release (released form must be encrypted).
- Fault templates must map Table C patterns onto real AppWorld APIs; the API explorer is checked before templates are written.
- AppWorld created-row ids shift between runs, so the Plan 2 adapter must give created rows content-based labels before `stale_records` compares runs.
- Repository: this private local repository; Raluca gets access when she joins the build.
