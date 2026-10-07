You are reviewing one deterministic two-job program execution.

Treat the supplied corpus and capability catalogue as stipulated test inputs. Judge only whether the program and execution satisfy the declared selection, field-preservation, handoff, ordering, and recommendation rules. Do not demand external customer, market-research, or source evidence that the deterministic contract does not require.

Start at the downstream result and trace across the two handoffs when warranted. Return exactly six reviews: judge each ID in `common_base.section.assigned_boundary_ids` exactly once and return no other review units. Handoff IDs are contextual evidence references only: you may cite them in `evidence_refs`, but never use a handoff ID as `unit_id`. Mark at most one boundary `failed` or `suspect`; that first marked boundary is your top root cause. If the execution satisfies the contract, mark every boundary trusted.

The compact graph initially contains one executed anchor per boundary and opaque eligible child-group identifiers. A helper expansion reveals only the model-selected captured child group. Never infer hidden child contents from its identifier or count.

Return exactly one `next_action`:

- `helper_expansion`: name one currently listed boundary ID and one child-group ID; leave `requests` empty.
- `artifact_inspection`: when the package lists it as available, provide one or two inspections of currently visible actual nodes; leave boundary and child-group IDs empty.
- `finalize`: leave boundary ID, child-group ID, and requests empty.

Obey the package's action contract. Do not batch speculative later actions. After receiving an operation response, reassess all six boundaries and choose exactly one next action again.
