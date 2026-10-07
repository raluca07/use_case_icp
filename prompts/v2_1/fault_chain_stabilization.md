Repair only the supplied failing job in the fresh two-job preflight chain.
Preserve job IDs, source paths, declared semantic boundaries, output schema,
handoff names, and deterministic behavior. Return the complete replacement job
and no commentary.

Use lexical source names for every `qualified_function_name`: `normalize`,
`outer.inner`, or `outer.inner.normalize`. Never include a module/import name,
`<locals>`, a class component, an empty component, a wrong-case spelling, or a
leaf-only abbreviation for a nested function. Preserve each declaration's
exact `semantic_stage` enum value.

Use only the supplied failing source, compact failure diagnostics, relevant
semantic inputs, and any exact upstream artifact explicitly provided. Do not
infer hidden evaluation details. Do not use repository artifacts, prior
candidates, execution graphs, external state, network, filesystem, clocks,
randomness, subprocesses, or dynamic code execution.
