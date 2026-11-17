# Unified V2 result artifacts

This directory contains the sanitized result outputs for the final 32-arm, 42-instance experiment and its
statement-level source-localization re-analysis.

| File | Contents |
|---|---|
| `scores.jsonl` | One deterministic score row for each of 1,344 arm–instance evaluations. |
| `summary.json` | Overall, per-arm, repair, fault-class and fault-ID aggregates. |
| `paired_arm_comparisons.json` | Paired strict-detection wins, losses and ties for every arm pair. |
| `statement-scores.jsonl` | Exact-line and AST-statement localization results for 1,024 faulty arm–instance evaluations. |
| `statement-summary.json` | Per-arm exact and statement-level localization aggregates. |

These files contain metrics, synthetic instance identifiers, fault IDs, package sizes and token counts. They do
not contain prompts, raw AppWorld values, credentials, API responses, reviewer prose, model transcripts or private
qualification artifacts.

See [`docs/v2_latest_detailed_results.md`](../../docs/v2_latest_detailed_results.md) for the complete table and
definitions, and [`docs/v2_methods_and_fault_catalogue.md`](../../docs/v2_methods_and_fault_catalogue.md) for the
experimental method.
