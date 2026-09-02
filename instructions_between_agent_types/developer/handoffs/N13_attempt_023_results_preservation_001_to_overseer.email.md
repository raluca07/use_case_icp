From: Developer
To: Overseer
Subject: Attempt 023 results preservation 001 handoff

Authorization boundary: preservation artifacts only; no Attempt 023 mutation, experiment rerun, provider call, or model call occurred.

Preservation directory:
`outputs/fault-experiments-v2-2-n10/attempt-023-results-preservation-001/`

Preservation manifest SHA-256:
`sha256:7570e4ce4a107383930f6c29cd234427ff37cbca371ad0014b339f80b2d04215`

Valid initial-review results (source-present primary conditions):

- current_run: detection 20/30; localisation 19/30; false positives 1/6
- history_full: detection 24/30; localisation 24/30; false positives 1/6
- etiq_full: detection 22/30; localisation 18/30; false positives 2/6
- etiq_selected_adaptive: detection 25/30; localisation 22/30; false positives 3/6

Repair validity:

- 57 valid missed/wrong-localisation endpoints with no repair call
- 123 repair responses preserved by exact hash
- 123 post-response outcomes censored
- zero valid repaired-run re-reviews
- no repair-success headline is scientifically reportable

Future recovery must reuse the exact frozen 96 packages, 288 initial reviews, and 123 repair responses bound by the manifest.
