# Four-arm review-context experiment

Recorded 29 July 2026 from job `job-883750474f164113`.

The clean GPT-5.5 workflow produced one initial market-demand run and three
source-scoped repairs. Captured Etiq node counts were 110, 94, 98, and 116.
The workflow failed closed when the final strict review requested a fourth
repair after the configured three-repair allowance. Coverage did not run.

Repair targets were:

1. `build_research_plan`
2. `build_research_plan`
3. `retrieve_sources`

The nested `extract_evidence` failure remained unresolved.

## Comparison

| Run | Context | Package characters | Input tokens | Issue paths |
| --- | ---: | ---: | ---: | ---: |
| Initial | `semantic_only` | 69,843 | 29,910 | 3 |
| Initial | `history_full` | 71,470 | 30,405 | 3 |
| Initial | `etiq_selected` | 199,075 | 69,957 | 3 |
| Initial | `etiq_full` | 382,071 | 129,204 | 3 |
| Latest repaired | `semantic_only` | 68,165 | 29,916 | 2 |
| Latest repaired | `history_full` | 303,757 | 89,209 | 3 |
| Latest repaired | `etiq_selected` | 197,825 | 69,331 | 2 |
| Latest repaired | `etiq_full` | 386,978 | 130,173 | 2 |

Graph-selected context matched full-Etiq issue coverage with 46% fewer input
tokens on the initial run and 47% fewer on the latest run.

Accumulated non-Etiq history grew from 71,470 to 303,757 characters and became
29% more expensive than graph-selected context. It retained
`build_research_plan` as an additional issue after the other three arms treated
that issue as resolved. This is consistent with stale prior versions remaining
salient in flat accumulated history.

Corrected semantic-only context found the same current issue paths as both Etiq
arms in this one repetition. This run therefore demonstrates context reduction
relative to the full graph and stale-history pressure, but not an issue-count
advantage over semantic-only review.

## Archived artifacts

- [Complete comparison result](comparison-result.json)
- [Job state](state.json)
- [Job request](request.json)
- [Usage summary](usage-summary.json)
- [Repair diffs](repair-diffs/)
- [Job dashboard](figures/job-overview.png)
- [Latest lineage view](figures/latest-lineage.png)
- [Four-arm comparison view](figures/four-arm-comparison.png)

This directory intentionally contains curated experiment evidence only. Raw
invocation packages, generated pipelines, and the active runtime job directory
were not retained here.
