Review every assigned unit using only the supplied experiment package. This is an
evaluation replay: do not repair or execute anything.

Apply the same strict market-demand criteria as the production review: observed jobs,
pain, triggers, alternatives, consequences, and outcomes must support claims; generic
keyword matches and unrelated candidates are issues; background research cannot by
itself establish customer demand; and missing or contradictory evidence must remain
visible. Use `not_pipeline_step` only for plumbing helpers.

`semantic_only` contains the target input, source, output, and logs without Etiq.
`history_full` adds accumulated non-Etiq artifacts from the target job and any
explicitly supplied earlier jobs. Do not treat repetition in that history as
independent corroboration.

When a context mode omits evidence, record `cannot_judge` rather than inventing a
specific defect. In `etiq_selected`, request an exact direct-child prefix in
`expand_helper_prefixes` when a collapsed helper is required. In either Etiq mode,
request a bounded table, document, sequence, or record slice in `inspect_artifacts`
when the node preview is insufficient. Use `start`, `count`, optional `columns`, and
either a search `query` or an empty query for positional inspection. Non-Etiq modes
must return both request lists empty.

Every evidence reference must be an exact identifier in `allowed_evidence_refs`.
For modes without graph nodes, use the supplied semantic/source/log references and
return an empty `suspect_node_refs` list. Follow the response schema exactly.
