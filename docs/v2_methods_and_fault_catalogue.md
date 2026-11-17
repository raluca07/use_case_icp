# V2 methods and admitted fault catalogue

Date: 17 November 2026

## Research question

The experiment asks how different execution-evidence packages affect a model's ability to:

1. determine whether harmful behaviour occurred;
2. distinguish historical harm from harmful state remaining at the end;
3. classify the causal fault family;
4. localize the complete causal source and runtime-event set; and
5. identify historically affected, restored and residual artifacts.

The use case processes structured invoice requests from Gmail, resolves the intended Venmo user, creates a payment
request, writes a receipt and replies to the originating email. One workflow was dataset-authored and one was
authored by Codex from the public task in [`fixtures/v2/authoring_task.md`](../fixtures/v2/authoring_task.md).

## Population

The final population contains:

- 10 clean controls;
- eight admitted fault mechanisms;
- two independently authored workflows per mechanism; and
- unrepaired and repair-variant executions for every author/mechanism pair.

This produces `8 × 2 × 2 = 32` faulty instances and 42 total instances per evidence arm. A repair is part of the
recorded execution, not a post-diagnosis intervention. It can restore the primary record while leaving an
irreversible historical notification or another residual artifact.

## Admitted fault mechanisms

| ID | Class | Mechanical intervention | In-pipeline repair and remaining effect |
|---|---|---|---|
| L01 | Action | Change the first `create_payment_request` amount to `13.5` at the API-action boundary; source is unchanged. | Restore the request to `12.5`; the earlier wrong notification remains. |
| S01 | Source | Mutate the amount expression so `INV-V2-001` uses `amount_usd + 1`. | Restore the request and applicable receipt; the wrong notification remains. |
| S04 | Source | Round invoice amounts before creating requests, changing `12.5` and `37.25` to `12` and `37`. | Restore both requests and receipts; two wrong notifications remain. |
| R11 | Runtime | Concurrently update the first request to `13.5` while the workflow continues. | Restore the request to `12.5`; no residual harmful artifact remains. |
| R15 | Runtime | Make the first file creation produce a receipt with partial content while source remains unchanged. | Update the file with the intended complete content; no residual harmful artifact remains. |
| M02 | Mixed | Combine an independently harmful source amount defect with an independently harmful corrupted retrieved amount. | Restore the designated request/file state; historical downstream harm can remain. |
| I06 | Interaction | Mutated source trusts optional `runtime_rate`; runtime supplies `runtime_rate=2`. Neither component is harmful alone. | Restore the request to `12.5`; the wrong notification remains. |
| A01 | Amplified | Source adds one dollar while runtime independently doubles the retrieved amount, producing a more severe combined error. | Restore the request and receipt; the wrong notification remains. |

The executable mutations, runtime plans, repair plans and four-cell qualification logic are in
[`src/rdr/v2_faults.py`](../src/rdr/v2_faults.py). Faults are admitted through deterministic execution checks, not
by placing a descriptive fault label into the reviewer package. Prompt-injection and cybersecurity faults were
excluded from the experiment.

## Evidence conditions

The final comparison contains 32 arms. Their exact contents and results are listed in
[`v2_latest_detailed_results.md`](v2_latest_detailed_results.md). The principal evidence families are:

- complete interleaved AppWorld API action logs;
- executed workflow source;
- real and deterministically rewired flat AppWorld graphs;
- graph neighbourhood and origin ablations;
- interactive one-neighbourhood-at-a-time graph walks;
- collapsed and opened nested AppWorld execution graphs;
- task-scoped initial/final state packages;
- native Etiq coded-pipeline lineage; and
- a joined AppWorld–Etiq graph with fail-closed bridge construction.

The arms are isolated model calls. Every one-shot arm receives exactly one package in a fresh ephemeral reviewer
session. The Codex CLI transport technically exposes its standard read-only tool surface, but each call runs in an
empty temporary working directory, any tool event is rejected, and observed tool use was zero. Interactive N and O
also use isolated turns and reveal only registered neighbourhoods from the same frozen flat graph. Package
construction rejects private labels and known answer metadata.

## Reviewer prompt

All final arms use the same diagnosis contract:

```text
Use only the evidence included in this review package. Do not inspect or use information from outside the package.

Make two independent decisions: whether a fault caused harmful behaviour at any point during execution, and whether any harmful state or artifact still exists at the end of the recorded execution.

Identify the root cause of the harmful behaviour. A root cause is the source defect, incorrect action, or abnormal runtime condition without which the harmful outcome would not have occurred. Report all causal source locations as file:line values in root_cause_source_locations. Report all causal action or runtime events by their event indices in root_cause_event_indices.

Include multiple source locations or event indices when the root cause has multiple necessary components. Do not select a later propagation, state-write, notification, or repair event merely because that is where the harm became visible. Include such an event as a root cause only when the event itself introduced a necessary harmful action or runtime condition. If the supplied evidence does not support a source location or causal event index, return an empty list for that field.

Classify the fault using exactly one of the following definitions:
- action: the executed source is unchanged, but an operation or API call is executed with an incorrect argument or action.
- source: a defect in the executed source causes harm under otherwise normal runtime behaviour.
- runtime: the source is unchanged, but an abnormal response, failure, ordering, concurrent update, filesystem result, clock, permission, or dependency behaviour causes harm.
- mixed: source and runtime faults occur in the same execution, and each is independently harmful.
- interaction: a source condition and runtime condition occur together; neither is harmful alone, but their combination is harmful.
- amplified: at least one component is harmful alone, and combining it with another component creates additional harm or greater severity.

Use null for fault_class when no harmful fault occurred. Otherwise, return only one of the defined category names, not a descriptive fault name.

Report historically_affected_artifacts as artifacts that entered a harmful or incorrect state at any point during execution. Report restored_artifacts as the subset of those artifacts that were later returned to a correct state. Report residual_harmful_artifacts as artifacts that remain harmful or incorrect at the end of the recorded execution.

Later corrective actions do not erase the historical fault. If all harmful state and artifacts are restored, return fault_occurred=true and residual_harm_present=false. If any harmful state or artifact remains, return fault_occurred=true and residual_harm_present=true.

When no harmful fault occurred, return fault_occurred=false, residual_harm_present=false, fault_class=null, and empty root-cause and artifact lists.

Base every claim on evidence visible in the package. Do not invent unseen events, private labels, source lines, or artifact identifiers. Reply only with JSON matching the schema.
```

The executable prompt is `SYSTEM_PROMPT_V2` in [`src/rdr/v2_review.py`](../src/rdr/v2_review.py). The answer schema
and deterministic scorer are in [`src/rdr/v2_scorer.py`](../src/rdr/v2_scorer.py).

## Scoring

Strict detection requires both historical fault occurrence and final residual-harm status to match truth. Class
accuracy requires exact agreement with the admitted class. Complete root-cause recovery requires exact set equality
for causal source locations and runtime/action events; extra and missing elements both fail.

The supplementary statement metric maps reported and gold source lines to the smallest enclosing Python AST
statement while retaining exact runtime-event equality. It corrects multiline-call line-number artifacts without
giving credit for the wrong causal event. Its implementation is
[`src/rdr/v2_statement_localization.py`](../src/rdr/v2_statement_localization.py).

Artifact precision and recall are calculated separately for historical, restored and residual artifact sets.
There is no LLM judge in the scoring path.

## Graph interpretation limits

AppWorld graphs model API calls, arguments, observed responses, source spans, record effects and typed execution
relationships. Native Etiq lineage captures registered coded-pipeline states and operations. It does not reliably
create a distinct state for every primitive scalar occurrence. The joined graph therefore accepts only exact,
unique, reachable hashes and rejects ambiguous bridges.

Composite qualification establishes that a complete cross-layer effect path exists, but it does not guarantee
that the accepted path passes through the current fault's root cause. This distinction is important when
interpreting perfect composite detection alongside substantially lower causal localization.

## Public artifacts

Sanitized machine-readable scores and summaries are published under
[`results/v2-unified-2026-11-16`](../results/v2-unified-2026-11-16). Raw reviewer packages, model transcripts,
credentials, private truth and AppWorld data are intentionally excluded.
