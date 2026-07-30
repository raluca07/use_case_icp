# Controlled review–repair comparison

This is the curated record for
`controlled-comparison-25382837f8b34720`, run with GPT-5.5 on 30 July
2026.

All four arms started from the same pipeline, runtime input, and recorded HTTP
corpus. Each arm used fresh ephemeral Codex sessions, an invocation-only read
boundary, and its own repair ancestry. No arm received another arm's reviews,
repairs, source, or outputs.

Each arm had three scoped review → repair → replay cycles. Final outcomes were
evaluated by fresh blind `etiq_selected` judges with on-demand graph and
artifact expansion.

| Context | Repairs | Effective | Reported input tokens | Unresolved boundaries | Time |
| --- | ---: | ---: | ---: | ---: | ---: |
| `semantic_only` | 3 | 0/3 | 568,715 | 4 | 568.1s |
| `history_full` | 3 | 1/3 | 1,824,533 | 4 | unavailable |
| `etiq_full` | 3 | 0/3 | 1,331,686 | 3 | 508.4s |
| `etiq_selected` | 3 | 1/3 | 1,000,797 | 2 | 722.1s |

No arm reached final trust. Compared with `etiq_full`, `etiq_selected` used
24.8% fewer reported input tokens and left one fewer unresolved boundary.
Compared with accumulated history, it used 45.1% fewer input tokens and left
two fewer unresolved boundaries. It cost more than semantic-only, but left two
fewer unresolved boundaries.

The first common full-graph judge exceeded Codex's 1,048,576-character input
limit on the history branch. The already-produced final runs were rejudged
with isolated graph-selected judges. Superseded judge calls are excluded from
the table. The history arm's in-memory duration breakdown was not recoverable
after that failure, so it is reported as unavailable rather than zero.

`comparison-summary.json` contains the compact machine-readable metrics.
Raw pipelines, prompts, network responses, and invocation logs remain under
ignored local `outputs/` storage.
