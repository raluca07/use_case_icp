# V2 statement-level source-localization results

Date: 16 November 2026

This is a post-hoc re-analysis of the frozen final experiment. It makes no reviewer calls and changes no
packages, prompts, answers, truth, or existing exact-expression scores. The implementation is
[`src/rdr/v2_statement_localization.py`](../src/rdr/v2_statement_localization.py), with focused tests in
[`tests/test_v2_statement_localization.py`](../tests/test_v2_statement_localization.py).

## Metric

The original metric requires literal equality between every reported `file:line` and the gold expression line.
The supplementary metric maps each reported and gold line to the smallest enclosing Python AST statement. Two
lines therefore match when they belong to the same call, assignment, return, or other statement. Runtime-event
indices remain exact, and the complete root cause still requires the complete source-statement set and complete
event set.

For example, `workflow.py:252` and `workflow.py:254` both normalize to the multiline assignment spanning
`workflow.py:252-257`. This earns statement-level credit but not exact-expression credit.

## Results by arm

All denominators are the 32 faulty instances: 16 unrepaired and 16 repair-variant executions.

| Arm | Exact expression + events | Statement + events | Change | Unrepaired statement | Repair-variant statement |
|---|---:|---:|---:|---:|---:|
| A | 8/32 | 8/32 | 0 | 6/16 | 2/16 |
| B | 12/32 | 12/32 | 0 | 6/16 | 6/16 |
| C | 11/32 | 11/32 | 0 | 5/16 | 6/16 |
| D | 8/32 | 8/32 | 0 | 6/16 | 2/16 |
| E | 9/32 | 9/32 | 0 | 6/16 | 3/16 |
| F | 12/32 | 12/32 | 0 | 6/16 | 6/16 |
| G | 12/32 | 12/32 | 0 | 6/16 | 6/16 |
| H | 12/32 | 12/32 | 0 | 6/16 | 6/16 |
| I | 12/32 | 12/32 | 0 | 6/16 | 6/16 |
| J | 9/32 | 9/32 | 0 | 6/16 | 3/16 |
| K | 10/32 | 10/32 | 0 | 6/16 | 4/16 |
| L | 11/32 | 11/32 | 0 | 6/16 | 5/16 |
| M | 9/32 | 9/32 | 0 | 6/16 | 3/16 |
| N | 8/32 | 8/32 | 0 | 6/16 | 2/16 |
| O | 10/32 | 10/32 | 0 | 6/16 | 4/16 |
| P | 20/32 | 20/32 | 0 | 10/16 | 10/16 |
| Q | 16/32 | 16/32 | 0 | 8/16 | 8/16 |
| R | 16/32 | 16/32 | 0 | 8/16 | 8/16 |
| S | 12/32 | 12/32 | 0 | 6/16 | 6/16 |
| T | 12/32 | 12/32 | 0 | 6/16 | 6/16 |
| U | 20/32 | 20/32 | 0 | 10/16 | 10/16 |
| V | 15/32 | **20/32** | **+5** | 9/16 | 11/16 |
| W | 0/32 | 0/32 | 0 | 0/16 | 0/16 |
| X | 6/32 | **7/32** | **+1** | 3/16 | 4/16 |
| Y | 0/32 | 0/32 | 0 | 0/16 | 0/16 |
| Z | 5/32 | **7/32** | **+2** | 4/16 | 3/16 |
| `STATE_CALLS` | 6/32 | 6/32 | 0 | 6/16 | 0/16 |
| `STATE_CALLS_SOURCE` | 12/32 | **13/32** | **+1** | 10/16 | 3/16 |
| `ETIQ_CODE_LINEAGE` | 9/32 | 9/32 | 0 | 6/16 | 3/16 |
| `APPWORLD_ETIQ_COMPOSITE` | 8/32 | **12/32** | **+4** | 6/16 | 6/16 |
| `STATE_APPWORLD_GRAPH` | 11/32 | **12/32** | **+1** | 6/16 | 6/16 |
| `STATE_ETIQ_GRAPH` | 0/32 | 0/32 | 0 | 0/16 | 0/16 |

Across all arms, complete root-cause recovery rises from `321/1,024` (31.3%) to `335/1,024` (32.7%).
Among the 640 evaluations whose gold root cause contains a source location, exact source-line recovery is
`128/640` (20.0%), while statement-level source recovery is `166/640` (25.9%).

The best score remains `20/32` (62.5%): P and U already achieved it under exact scoring, while V joins them
under statement-level scoring. The composite rises from `8/32` (25.0%) to `12/32` (37.5%), confirming that four
of its apparent failures were line-granularity artifacts. Its remaining 20 failures cannot be attributed to this
line-number issue.

## Interpretation

Fourteen evaluations change from incorrect to correct. All are S01 or S04 source faults where the reviewer
reported another line in the same multiline `create_payment_request` statement. No A01 or I06 result changes:
those disagreements concern runtime-event selection, especially choosing downstream event 25, rather than the
source-line granularity.

Machine-readable results are in
[`results/v2-unified-2026-11-16`](../results/v2-unified-2026-11-16).
