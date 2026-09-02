Repair only the supplied failing job in the fresh protocol 2.2 two-job preflight chain.
Return the failing `job_id`, complete replacement source for every supplied source
path, and, only when the replacement moved a declared semantic boundary to a
different function, a `boundary_relinks` item containing exactly that
`boundary_id` and its new lexical `qualified_function_name`. Return no
commentary.

The controller owns the entry path and complete boundary declarations. Do not
reproduce or change source paths, semantic stages, roles, expected inputs, or
expected outputs. Do not add, remove, merge, or split boundaries. Return an
empty `boundary_relinks` list when every declaration still resolves to its
supplied function.

Use lexical source names for every `qualified_function_name`: `normalize`,
`outer.inner`, or `outer.inner.normalize`. Never include a module/import name,
`<locals>`, a class component, an empty component, a wrong-case spelling, or a
leaf-only abbreviation for a nested function.

The compact diagnostics contain all currently and simultaneously observable
fault-blind qualification failures, plus any immediately preceding response
scope rejection. Satisfy the complete supplied set in this replacement. Use
only the supplied failing source, compact failure diagnostics, relevant
semantic inputs, and any exact upstream artifact explicitly provided. Do not
infer hidden evaluation details. Do not use repository artifacts, prior
candidates, execution graphs, external state, network, filesystem, clocks,
randomness, subprocesses, or dynamic code execution.
