# Runtime diagnosis evidence experiment

This repository evaluates which evidence helps a model detect and localize faults in an AppWorld invoice-payment
workflow. The final experiment compares sequential API logs, executed source, flat and nested AppWorld execution
graphs, native Etiq lineage, joined AppWorld–Etiq graphs, endpoint-state packages, and interactive graph walks.

The experimental unit is one complete workflow execution. The final population contains 42 instances: 10 clean
controls, 16 unrepaired faulty executions, and 16 repair-variant faulty executions. Eight admitted fault mechanisms
cover action, source, runtime, mixed, interaction, and amplified faults. Prompt-injection and cybersecurity faults
are not part of this experiment.

## Results

- [Latest detailed results, arm definitions and metric definitions](docs/v2_latest_detailed_results.md)
- [Statement-level source-localization analysis](docs/v2_statement_localization_results.md)
- [Methods and admitted fault catalogue](docs/v2_methods_and_fault_catalogue.md)
- [Machine-readable final results](results/v2-unified-2026-11-16/README.md)

The complete action log was the strongest simple detection baseline, reaching `42/42` strict detection. Adding
executed source improved causal diagnosis: arms P, U and V recovered `20/32` complete root causes under the
statement-level metric. Real flat-graph topology did not outperform the matched rewired topology in this
population. The matched AppWorld graph substantially outperformed native Etiq lineage, while the joined composite
reached perfect detection but only `12/32` statement-level root-cause recovery.

## Repository structure

```text
fixtures/   Public experimental tasks, fault inputs and Etiq replay fixture
schemas/    Public schemas for execution and graph artifacts
src/rdr/    Experiment construction, isolation, review and deterministic scoring
tests/      Unit, integration and isolation tests
docs/       Public methods and results
results/    Sanitized aggregate and per-instance metric outputs
```

Raw reviewer packages, private truth, AppWorld installations, authentication state and model transcripts are not
published. They are excluded through `.gitignore`.

## Environments and tests

The main package requires Python 3.13. AppWorld and development dependencies are declared in `pyproject.toml`.
Etiq is deliberately isolated because its dependency set is incompatible with the AppWorld environment; its
resolved requirements are in `requirements-etiq-pilot.txt`.

The publication audit completed these checks:

```text
Main non-live suite: 470 passed, 1 skipped, 2 deselected
Isolated Etiq suite: 49 passed
```

The model-review transport uses authenticated Codex CLI sessions rather than storing an API key in this
repository. No credentials are required to inspect the published results.
