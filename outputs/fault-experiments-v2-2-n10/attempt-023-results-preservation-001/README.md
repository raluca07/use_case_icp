# Attempt 023 results preservation 001

This directory is a read-only preservation index over the unchanged `attempt-023` directory. It contains derived review-only results and exact SHA-256 bindings; it does not contain regenerated experimental evidence.

## Valid findings

The 288 initial review records are valid for fault detection and localisation. `initial-review-results.csv` derives the four primary, source-present condition results directly from those records. Its token columns contain review-only usage. `token-usage.json` keeps all 288 initial-review usage separate from the 123 repair-response calls.

The 57 trials classified as missed or wrong localisation also ended validly at that point. They made no repair call.

## Censored repair material

Exactly 123 repair responses were generated and are preserved by exact response-file hash in `repair-validity.json`. Every outcome after those responses is censored because dependency ordering and re-review package construction were affected by controller bugs. There are zero valid repaired-run re-reviews. The original controller's repair-success aggregate is not a scientific result and must not be reported or used.

## Preservation and recovery

All original Attempt 023 files remain in place and unchanged. `preservation-manifest.json` binds the complete Attempt 023 tree as well as the experiment freeze, pre-review state, 12 instances, 12 captures, 96 packages, 288 reviews, 180 repair records, closure, terminal, analysis, anonymous release, N13 correction, and the relevant repository trees.

Any future recovery must reuse the frozen 96 packages, 288 initial reviews, and 123 repair responses by exact hash. It must not regenerate or replace them.

## Verification

From the repository root, run:

```bash
python3 outputs/fault-experiments-v2-2-n10/attempt-023-results-preservation-001/verify_preservation.py
```

The command exits nonzero for a changed, missing, or unexpected preservation artifact; any changed, missing, or unexpected file in a bound source tree; any source-count or result mismatch; or any changed Attempt 023 file.
