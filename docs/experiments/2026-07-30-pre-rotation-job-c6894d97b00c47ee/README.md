# Curated pre-rotation results: job-c6894d97b00c47ee

This is the curated record of the last live job before repair-target rotation
and repair-effectiveness metrics were enabled. It contains the recorded outcome
and dashboard screenshots needed to interpret the experiment.

## Outcome

- Status: failed closed after the three-repair allowance was exhausted.
- Segment: `agent_control_plane_teams`.
- Etiq runs: one baseline plus three repaired executions.
- Captured node counts: 76, 82, 54, and 58.
- Repair target on all three attempts: `collect_runtime_sources`.
- Coverage did not run because market demand did not reach reusable trust.
- Total recorded usage, including the comparison: 800,766 input tokens and
  41,143 output tokens across 17 reported Codex invocations.

## Four-arm comparison

Experiment: `review-comparison-9f0a0a70ded549c3`.

All four modes found the same three issue functions in both the baseline and
latest repaired execution:

- `collect_runtime_sources`
- `extract_evidence_records`
- `synthesize_market_demand`

No issue function was absent after the three repairs. On the latest execution,
the measured input-token counts were:

| Mode | Input tokens |
| --- | ---: |
| `semantic_only` | 31,369 |
| `history_full` | 109,590 |
| `etiq_full` | 78,601 |
| `etiq_selected` | 49,670 |

The run exposed the repair-selection problem: every attempt selected the first
failed function instead of rotating through unresolved boundaries.

## Contents

- `figures/job-overview.png`: dashboard job view.
- `figures/latest-lineage.png`: latest stored Etiq graph view.
- `figures/four-arm-comparison.png`: executed comparison dashboard.
- `SHA256SUMS`: checksums for this curated record.

The raw job directory is deliberately not published. It contained complete
Codex prompts, context payloads, generated source, and machine-local runtime
paths. The figures and summary above preserve the public experimental result
without publishing those invocation internals.

Verify this record from the repository root:

```bash
sha256sum -c docs/experiments/2026-07-30-pre-rotation-job-c6894d97b00c47ee/SHA256SUMS
```
