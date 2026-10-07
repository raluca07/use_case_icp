You are authoring one fresh, deterministic, two-job Python pipeline chain for
an unscored engineering preflight. Return exactly the requested two jobs and no
commentary.

Both jobs must read one JSON object from stdin and write one JSON object to
stdout. Use only the Python standard library and pandas. Do not use network,
filesystem, clocks, randomness, environment variables, subprocesses, dynamic
code execution, or stored repository artifacts.

Implement the supplied semantic requirements directly. Across the two jobs,
declare at least eight meaningful review boundaries per job. Give every declaration a
unique opaque boundary ID, normalized generated source path, and qualified
function definition. `qualified_function_name` is the lexical source name:
`normalize` for a top-level function, `outer.inner` for a nested function, and
`outer.inner.normalize` for deeper nesting. Do not include a module name or
the runtime-only `<locals>` component. Invalid examples include
`pipeline.normalize`, `outer.<locals>.inner`, `.normalize`, `outer..inner`,
wrong-case names, leaf-only names for nested functions, and class-qualified
names. Generated classes are prohibited.

Assign every declaration exactly one `semantic_stage` value from the schema.
Across the chain, cover all six non-supporting stages with executed functions;
use `supporting` only for additional meaningful boundaries. Include
at least two directly executed nested DataFrame helpers whose intermediate
inputs and outputs are capturable. Include a downstream join or aggregation and
consume both exact upstream handoff artifacts. Keep functions deterministic and
small enough for bounded evidence review.

Return `complexity_claims` with exactly these four keys:
`declared_boundary_count`, `exact_handoff_count`,
`directly_executed_nested_helper_count`, and `has_join_or_aggregation`. Use
non-negative integers for the three counts and a Boolean for the final key.
These claims are untrusted diagnostics, not evidence. Acceptance derives its
counts and topology only from execution, semantic checks, captured structure,
and legal evidence operations.
