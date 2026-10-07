You are authoring one fresh, deterministic, two-job Python pipeline chain for
an unscored engineering preflight. Return exactly the requested two jobs and no
commentary.

Both jobs must read one JSON object from stdin and write one JSON object to
stdout. Use only the Python standard library and pandas. Do not use network,
filesystem, clocks, randomness, environment variables, subprocesses, dynamic
code execution, or stored repository artifacts.

Implement the supplied semantic requirements directly. Across the two jobs,
declare at least twelve meaningful review boundaries. Give every declaration a
unique opaque boundary ID, normalized generated source path, and qualified
function definition. Include
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
