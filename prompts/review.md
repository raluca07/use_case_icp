Review only the assigned evidence units in the supplied immutable section. Return one decision for every assigned `unit_id`. Use the captured Etiq states and relationships and acknowledge boundary health.

Every item in `evidence_refs`, including criterion evidence, must be an exact identifier supplied by the package: a `unit_id`, `node_ref`, `relationship_ref`, or one of the top-level evidence file references. Do not turn evidence into descriptive citation strings.

When `stage` is `market_demand`, also judge whether the executed evidence supports genuine market-demand discovery:

- audience jobs, context, pain, triggers, alternatives, consequences, and desired outcomes must come from observed evidence rather than inference from the product;
- the cited source must support the stated signal, not merely mention a related feature or category;
- vendor documentation and product pages are background or alternative evidence, not sufficient customer-demand evidence;
- recurrence, urgency, and willingness to pay must not be invented;
- human practitioner or buyer evidence must remain distinct from agent operational evidence;
- generic keyword matches, fabricated personas, and unsupported market claims fail review;
- missing or contradictory evidence must remain visible.

Use `trusted_for_reuse` only when all criteria are met with adequate executed evidence. Follow the response schema exactly.

If the assigned boundary cannot be judged without a nested helper, return the exact
direct-child `func_stack` prefix in `expand_helper_prefixes`. Expand only the branch
needed for the unresolved criterion. When a result is failed or suspect, identify any
specific faulty captured artifacts in `suspect_node_refs`; use an empty list when the
problem can only be localized to the whole boundary.
