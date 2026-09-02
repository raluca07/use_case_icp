# Attempt 023 curated publication

This directory describes the Git-published subset of Attempt 023. The publication keeps the original seven-file preservation index unchanged and adds only the evidence needed to inspect the frozen packages, generated pipelines, initial reviews, repair responses, and reported results.

The complete local Attempt 023 archive contains 85,889 files and is approximately 18 GB. It is intentionally not published. In particular, Codex homes, authentication files, caches, runtime installations, logs, duplicated workspaces, and the raw `provider-branches` tree are excluded. Only the 411 response files referenced by the preservation records are selected from provider branches.

The raw ledger is also excluded. Its complete tree remains bound by SHA-256 in the original preservation manifest, while the publication avoids retaining a workstation-specific path found in one ledger record.

## Included material

- the original Attempt 023 preservation README, manifests, results, checksums, and verifier;
- 12 frozen instances and 12 captures;
- 96 package records and all 522 frozen package files;
- 44 generated pipeline sources, 44 pipeline manifests, and 44 pipeline inputs;
- 288 initial-review records and their exact responses;
- 180 repair records and the 123 exact repair responses that were generated;
- experiment freeze, pre-review state, analysis, anonymous release, closure, terminal, and correction records;
- the source, prompts, schemas, protocol, fixtures, and handoff bound by the preservation record.

The post-response repair outcomes remain censored as described by the original preservation README. Publishing their response hashes and response files does not make the invalid downstream outcomes scientific results.

## Verification

From the repository root, run:

```bash
python3 outputs/fault-experiments-v2-2-n10/attempt-023-publication-001/verify_publication.py
```

This verifies every published file against `publication-manifest.json`, validates the original preservation checksums, enforces the expected evidence counts, rejects forbidden transient paths, and scans the publication for common credential formats.

The original `verify_preservation.py` is retained byte-for-byte. It verifies the complete 18 GB local archive and is therefore expected to report missing files in a clone containing only this curated publication.
