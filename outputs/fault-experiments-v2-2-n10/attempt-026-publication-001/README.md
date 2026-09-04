# Attempt 026 curated terminal-incomplete publication

This directory describes the Git-published subset of the corrected four-instance
Attempt 026. The experiment completed all 192 scheduled initial reviews and 43
of 96 scheduled repair traces before it stopped fail-closed. It did not produce
the prespecified completed analysis, replay, or successful terminal closure.

The final recorded failure was `ValueError: N05 real-Etiq capture is not
reviewable`. The earlier follow-up-limit terminal record is retained because it
is part of the append-only history; N14C authorized its narrow correction and
exact resume. Neither terminal record is presented as a completed experiment.

## Included material

- the exact freeze, live-consumption, qualification, correction, and both
  terminal records;
- four disclosure catalogues, 64 frozen reviewer packages and controller
  manifests, 192 completed initial-review records, and 43 completed repair
  records;
- the 278 exact model response files referenced by completed records;
- generated pipeline source, input, and manifest files for 35 materialized
  repaired-run branches, including the branch at the final failure boundary;
- the source-attempt records needed to verify the four selected instances;
- the relevant source, prompts, schemas, protocol, and experiment fixtures;
- a derived initial-review summary, partial repair accounting, checksums, and a
  verifier.

## Excluded material

The complete local Attempt 026 directory is approximately 13 GB. Raw provider
requests and ledgers, Codex homes, authentication material, caches, installed
plugins, logs, duplicated workspaces, and unselected repair-run artifacts are
excluded. The publication contains only response files from provider branches.

The 43 repair outcomes form an interrupted prefix, not the planned 96-trace
repair comparison. They are preserved but must not be reported as a complete
repair result. The four-instance initial-review findings are descriptive and
not population-powered.

## Verification

From the repository root, run:

```bash
python3 outputs/fault-experiments-v2-2-n10/attempt-026-publication-001/verify_publication.py
```

The verifier checks every selected file and metadata checksum, recomputes the
review summary, validates record self-hashes and response bindings, rejects
forbidden transient paths, and scans the publication for common credentials and
absolute local home-directory paths.
