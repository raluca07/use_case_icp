# Use-Case and ICP Agent

A small local workflow that runs fresh Codex sessions for segmentation, market-demand discovery, coverage, pre-review pipeline rewrites, evidence review, repair, and synthesis. Generated Python pipelines execute only through an Etiq scanner adapter. Captured Etiq nodes and relationships remain the execution-evidence authority.

## Current MVP

- fresh, non-resumed Codex session for every invocation;
- an OS-enforced, read-only invocation boundary for every Codex session;
- reproducible context manifests and raw Codex JSONL events;
- per-session input/output token logs and job-level usage totals;
- atomic job state and append-only events;
- safe generated-Python bundle materialization;
- injectable Etiq execution and captured-evidence serialization;
- runtime pipeline JSON as the downstream semantic result, with the Codex authoring proposal retained separately;
- declaration-first review units with size-based splitting and one-level-on-demand helper expansion;
- bounded, redacted value previews in review and lineage views;
- review receipts, stored retrace paths, and a dependency-aware trusted frontier;
- per-review selected-versus-available context accounting;
- bounded authoring-retry loop for invalid generated bundles and pipelines that fail compilation, execution, runtime-output validation, or Etiq reviewability;
- separate bounded repair loop with `boundary` and `faulty_node` experiment modes, mechanical source-scope validation, and persisted unified diffs;
- isolated production Etiq worker processes with timeout, environment allowlisting, and optional CPU/memory limits;
- standard-library CLI and a lineage dashboard with captured edges, trust state, unit filtering, value previews, context accounting, and review-context comparison pages.

## Setup

The core uses only Python 3.12's standard library. A real run additionally needs the Codex CLI to be authenticated and Etiq installed:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
pip install -r requirements-etiq.txt
use-case-icp doctor
```

Etiq is pinned to the stable
[`etiq-copilot==2.3.0`](https://pypi.org/project/etiq-copilot/2.3.0/) release
from PyPI. It can also be installed with `pip install -e '.[etiq]'`.

Without installation, run commands from the repository with `PYTHONPATH=src`.

## Run

```bash
PYTHONPATH=src python3 -m use_case_icp run \
  --product "Describe the product" \
  --audience "Describe the broad audience" \
  --max-segments 5 \
  --max-authoring-retries 2 \
  --max-repairs 6
```

Each invocation is stored under `outputs/jobs/<job_id>/invocations/<invocation_id>/`. The directory contains the exact context manifest, assembled request, Codex events, structured output, and `usage.json`.
Codex starts with that directory as its only readable workspace-data root.
Its permission profile denies the rest of the filesystem, except for Codex's
own executable package and the minimal operating-system runtime paths required
to launch commands. Commands are read-only, network access is disabled, the
subprocess environment is reduced to `PATH`, `HOME`, and `LANG`, and repository
or user `AGENTS.md`, memories, rules, plugins, and configuration are not loaded.
The host Codex process receives authentication through a temporary isolated
Codex home that is removed after the invocation.
The applicable role prompt, shared pipeline prompt when relevant, repository
instructions, and output schema are also materialized inside the invocation
directory. They remain the only approved workflow resources; general user,
system, and cached plugin skills are not copied into job invocations.
Workflow sessions explicitly default to `gpt-5.5`; the CLI rejects GPT model versions above 5.5. Use `--model` only to select an available model at or below that ceiling.

Useful request limits are `review_expansions`, `repair_scope_mode`
(`boundary` or `faulty_node`), `etiq_memory_mb`, and `etiq_cpu_seconds`.
Production Etiq execution is process-isolated, but this is not a complete
security sandbox for untrusted code.

An authoring retry is a new Codex session that receives the failed pipeline and
its persisted diagnostics and returns a complete replacement. It happens before
evidence review and increments `authoring_retry_count`, not `repair_count`. For
each pipeline stage, the initial version plus two retries is the default.

Bundle validation is part of this general retry path. Unsafe paths, non-Python
files such as `requirements.txt`, duplicate paths, missing entry files, and
other invalid bundles are rejected before materialization or execution and sent
to a fresh Codex authoring retry. Executable attempts have their own run
directories; when failure happened before a run existed, the first valid run's
`authoring-retry.json` has a null `previous_run_id`.

Repairs are different from authoring retries. A repair is selected from failed
or suspect review evidence. `faulty_node` permits only the selected statement to
change, while `boundary` permits only the selected function to change. Codex
transports a complete bundle through the response schema, but the workflow
mechanically rejects changes outside the selected source span and persists the
accepted unified diff in `repair-diff.json`. The current runner then
re-executes the complete pipeline as a new Etiq evidence branch; execution is
not yet branch-local. Failed boundaries are selected by fewest prior attempts,
so repeated repairs rotate across unresolved functions instead of always
targeting the first one. The default allowance is six repairs.

Each stage writes `repair-metrics.json`. It distinguishes accepted repairs
(valid in-scope diffs), evaluated repairs (rerun and reviewed), and effective
repairs (the targeted function is no longer failed or suspect after that
rerun). It also records attempts per function and initial, current, and resolved
issue functions.

## Dashboard

```bash
PYTHONPATH=src python3 -m use_case_icp serve --port 8000
```

Open <http://127.0.0.1:8000>.

For each stored run, the lineage page shows captured Etiq nodes and
relationships, review units, trust overlays, the trusted frontier, selected
versus available context, and actual review tokens. The complete graph supports
fit, zoom, and pan. Selecting a review unit filters the graph to that function
boundary and its incident artifacts. Selecting a node then reveals only its
review-unit membership, incident captured relationships, tied derived
annotations, and bounded value preview.

The dashboard explicitly separates:

- **deterministic stored structure:** captured nodes and edges for an immutable
  run;
- **deterministic projections:** review-unit selection, sectioning, filtering,
  context packages, and layout;
- **model judgments:** trust, suspect, and failure labels produced by Codex and
  persisted for audit.

Executed comparisons are available under
`/jobs/<job_id>/experiments/<experiment_id>`. They display semantic-only,
accumulated-history, full-Etiq, and graph-selected arms together with package
size, measured input tokens, issue paths, and recall.

## Tests

The deterministic suite uses `unittest` and injected fake Codex/Etiq adapters:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

When the pinned Etiq package is installed, the same suite also runs a real
nested-function scanner contract test; otherwise that one test is skipped.
The current suite contains 30 passing tests, including strict filesystem
isolation, invalid-bundle
authoring-retry and non-Etiq history-filtering regression tests.

The full design and remaining hardening gates are in `IMPLEMENTATION_PLAN.md`.

Generated pipelines declare their highest meaningful review-stage functions. The
workflow matches these against captured `func_stack` frames, splits only oversized
units, and initially collapses helper evidence. Review can request one exact direct
child at a time. Each run stores the selection decisions, context accounting,
trusted frontier, and any scoped repair target.

## Review-context comparison

Replay the same immutable execution evidence through four review contexts:

- `semantic_only`: job request, segments, pipeline input, source, runtime result,
  and logs without Etiq nodes or edges;
- `history_full`: the semantic-only package plus accumulated non-Etiq artifacts
  from the target job and any explicitly supplied earlier jobs;
- `etiq_full`: the complete captured Etiq graph;
- `etiq_selected`: the current section-selected Etiq graph.

Here, a **node** specifically means an Etiq-captured intermediate runtime state
or function invocation. It does not mean a source document, prompt item, text
chunk, or token. The non-Etiq arms therefore have zero Etiq nodes by design.
For comparisons across all four arms, package characters and actual input
tokens are the context-size measures. Node and relationship counts show how
much execution evidence `etiq_selected` retained relative to `etiq_full`.

Plan package sizes without spending Codex tokens:

```bash
.venv/bin/python -m use_case_icp compare-review JOB_ID \
  --baseline-run RUN_ID \
  --repaired-run REPAIRED_RUN_ID \
  --history-job EARLIER_JOB_ID \
  --section section-001
```

Repeat `--history-job` in chronological order to simulate context growth across
multiple jobs. The target job is always included automatically. `history_full`
includes requests, segments, events, pipeline inputs and sources, semantic
results, logs, repair targets, and repair diffs. It excludes Etiq graph files,
prior review judgments, comparison outputs, and raw invocation packages so the
arm does not receive graph evidence or answer leakage. For the target job it
includes only the target run and its ancestors, omits the target run's later
repair artifacts, and excludes final state/events that would leak future
outcomes.

Add `--execute` to invoke Codex. All arms use the same model, assigned units,
prompt contract, response schema, and immutable runtime artifacts. Use
`--repetitions 3` for a less fragile comparison; be aware that each repetition
creates one fresh invocation per run, section, and mode.

The dashboard always separates all-arm consensus from disputed paths. To add
source-verified recall, precision, attribution-error, false-positive, and
secondary-finding metrics, attach a reviewed assessment:

```bash
.venv/bin/python -m use_case_icp assess-review JOB_ID EXPERIMENT_ID assessment.json
```

The latest run's `issue-assessment.json` is a complete example. Manual
assessment is explicit because neither `etiq_selected` nor any other arm is
automatically treated as ground truth.

## Latest recorded run and comparison

On 30 July 2026, job `job-64d77ce3936e40dc` ran market-demand discovery with
GPT-5.5. The initial run captured 136 Etiq nodes. Six accepted repairs rotated
across discovery, retrieval, extraction, and synthesis, but none removed its
target from the next review, so repair effectiveness was 0/6 and the job failed
closed before coverage.

The comparison `review-comparison-44bad695fad64885` replayed the initial and
latest immutable results once through all four context modes. The issue-quality
metrics use a manual source-code and runtime assessment rather than treating one
arm as ground truth:

| Run | Context | Input tokens | Verified core recall | Verified precision | Attribution errors | Useful secondary detail |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Initial | `semantic_only` | 32,043 | 3/3 | 75% | 1 | — |
| Initial | `history_full` | 32,661 | 3/3 | 100% | 0 | — |
| Initial | `etiq_full` | 134,996 | 3/3 | 100% | 0 | — |
| Initial | `etiq_selected` | 65,491 | 3/3 | 75% | 1 | — |
| Latest repaired | `semantic_only` | 26,937 | 3/3 | 75% | 1 | source failures, missing propagation, retrieval completeness |
| Latest repaired | `history_full` | 127,017 | 3/3 | 100% | 0 | — |
| Latest repaired | `etiq_full` | 103,657 | 3/3 | 75% | 1 | source failures, retrieval completeness |
| Latest repaired | `etiq_selected` | 77,703 | 3/3 | 100% | 0 | — |

The three verified core defects are broad source admission in
`discover_public_sources`, regex false positives in `extract_evidence_records`,
and overconfident/gap-suppressing output in `synthesize_market_demand`. All
arms found all three. The disputed `retrieve_sources` path is counted as an
attribution error for the observed causal failure, while its separate
completeness risk remains a secondary finding. No four-arm comparison mode
produced a pure false-positive path.

Graph selection used 36/136 nodes and 51% fewer input tokens than full Etiq on
the initial run. On the latest run it used 50/86 nodes and 25% fewer input
tokens. Flat history grew from one to 61 artifacts and from 32,661 to 127,017
input tokens. With one repetition, the run demonstrates context reduction
against full Etiq and flat history, but not better core-defect recall than the
smaller semantic package.

After starting the dashboard, open:

- `/jobs/<job_id>` for a stored job;
- `/jobs/<job_id>/lineage?run=<run_id>` for a run's Etiq lineage;
- `/jobs/<job_id>/experiments/<experiment_id>` for an executed comparison.

Generated job data under `outputs/` is intentionally not published. Static
dashboard examples are available in the
[`docs/blogpost/figures/`](docs/blogpost/figures/) and
[`docs/experiments/`](docs/experiments/) directories.

The manual assessment behind the table also recorded the workflow reviewer’s
separate `collect_runtime_context` false positive and that all seven workflow
receipts were invalid. Neither finding is attributed to a four-arm comparison
mode.

The earlier July benchmark blogpost and its curated dashboard figures remain in
[`docs/blogpost/`](docs/blogpost/); they predate this four-arm run.

The complete curated record of this four-arm run is archived under
[`docs/experiments/2026-07-29-four-arm-job-883750474f164113/`](docs/experiments/2026-07-29-four-arm-job-883750474f164113/).
