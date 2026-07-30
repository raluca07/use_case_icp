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
- bounded, redacted value previews plus on-demand table, record, sequence, and
  document inspection in review;
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

Controlled comparisons are available under
`/jobs/<job_id>/controlled-experiments/<experiment_id>`. They display the
independent review, repair, and replay outcome for each context arm.

## Tests

The deterministic suite uses `unittest` and injected fake Codex/Etiq adapters:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

When the pinned Etiq package is installed, the same suite also runs a real
nested-function scanner contract test; otherwise that one test is skipped.
The suite includes strict filesystem isolation, invalid-bundle
authoring-retry and non-Etiq history-filtering regression tests.

The full design and remaining hardening gates are in `IMPLEMENTATION_PLAN.md`.

Generated pipelines declare their highest meaningful review-stage functions. The
workflow matches these against captured `func_stack` frames, splits only oversized
units, and initially collapses helper evidence. Review can request one exact direct
child at a time. Each run stores the selection decisions, context accounting,
trusted frontier, and any scoped repair target.

## Controlled repair comparison

Run four independent review → repair → replay branches from one recorded
execution:

- `semantic_only`: job request, segments, pipeline input, source, runtime result,
  and logs without Etiq nodes or edges;
- `history_full`: the semantic-only package plus accumulated non-Etiq artifacts
  from the target job and any explicitly supplied earlier jobs;
- `etiq_full`: the complete captured Etiq graph;
- `etiq_selected`: the section-selected Etiq graph, with no full source during
  initial review and on-demand helper/artifact expansion.

Here, a **node** specifically means an Etiq-captured intermediate runtime state
or function invocation. It does not mean a source document, prompt item, text
chunk, or token. The non-Etiq arms therefore have zero Etiq nodes by design.
For comparisons across all four arms, package characters and actual input
tokens are the context-size measures. Node and relationship counts show how
much execution evidence `etiq_selected` retained relative to `etiq_full`.

Run the end-to-end comparison:

```bash
.venv/bin/python -m use_case_icp compare-control JOB_ID \
  --baseline-run RUN_ID \
  --max-repairs 3
```

The baseline is executed once while HTTP responses are recorded. Every branch
then receives the same runtime input and may use only those recorded responses.
Each review and repair is a fresh ephemeral Codex session with an
invocation-only read boundary. Branch artifacts are restricted to that branch's
ancestor chain, and a fresh blind graph-selected Etiq judge—with the same
on-demand expansion rights—evaluates each final result.
The dashboard reports repairs, blind-judge issues and trust, actual token usage,
and elapsed time. A failure in one branch is an outcome for that branch and
does not expose it to or stop another branch.

The older `compare-review` command remains available for diagnostic,
review-only package replays; it is not shown in the dashboard because it does
not measure repair outcomes. Those replays use the same review prompt,
response schema, and immutable runtime artifacts.
`etiq_selected` can expand a collapsed helper when the reviewer requests it,
and both Etiq arms can inspect bounded slices of captured tables and documents.
The comparison records cumulative tokens and package characters across those
follow-up rounds. Use
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

On 30 July 2026, controlled comparison
`controlled-comparison-25382837f8b34720` ran every GPT-5.5 arm from the same
recorded baseline corpus. Each arm had three independent scoped
review → repair → replay cycles, followed by the same fresh blind
`etiq_selected` judge.

| Context | Repairs | Reported input tokens | Blind-judge unresolved boundaries | Measured time |
| --- | ---: | ---: | ---: | ---: |
| `semantic_only` | 3 | 568,715 | 4 | 568.1s |
| `history_full` | 3 | 1,824,533 | 4 | unavailable |
| `etiq_full` | 3 | 1,331,686 | 3 | 508.4s |
| `etiq_selected` | 3 | 1,000,797 | 2 | 722.1s |

No arm reached blind-judge trust within three repairs. `etiq_selected` used
24.8% fewer input tokens than `etiq_full` and 45.1% fewer than
`history_full`, while leaving fewer unresolved boundaries than either and two
fewer than `semantic_only`. It still used 76.0% more tokens and more wall time
than semantic-only, so the result supports better repair outcome and graph
attribution—not universal cost reduction.

The first full-graph judge for `history_full` exceeded Codex's 1,048,576
character input limit. All four already-produced final runs were therefore
rejudged with fresh isolated graph-selected judges; superseded judge calls are
excluded from the table. History's original in-memory duration breakdown was
not recoverable after that judge failure, so it is shown as unavailable rather
than zero.

After starting the dashboard, open:

- `/jobs/<job_id>` for a stored job;
- `/jobs/<job_id>/lineage?run=<run_id>` for a run's Etiq lineage;
- `/jobs/<job_id>/controlled-experiments/<experiment_id>` for an end-to-end
  controlled comparison.

Generated job data under `outputs/` is intentionally not published. Static
dashboard examples are available in the
[`docs/blogpost/figures/`](docs/blogpost/figures/) and
[`docs/experiments/`](docs/experiments/) directories.

The earlier July benchmark blogpost and its curated dashboard figures remain in
[`docs/blogpost/`](docs/blogpost/); they predate this four-arm run.

The current controlled comparison is archived under
[`docs/experiments/2026-07-30-controlled-job-32968d910a7847a7/`](docs/experiments/2026-07-30-controlled-job-32968d910a7847a7/).
The earlier review-only comparison remains under
[`docs/experiments/2026-07-29-four-arm-job-883750474f164113/`](docs/experiments/2026-07-29-four-arm-job-883750474f164113/).
