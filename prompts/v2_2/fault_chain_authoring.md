You are authoring one fresh, deterministic, two-job Python pipeline chain for
the protocol 2.2 experiment. Return exactly the requested
two jobs and no commentary.

Both jobs must read one JSON object from stdin and write one JSON object to
stdout. Use only the Python standard library and pandas. Do not use network,
filesystem, clocks, randomness, environment variables, subprocesses, dynamic
code execution, or stored repository artifacts.

Place stdin loading, calls to the pipeline functions, result assembly, and the
single stdout write directly at module scope. Do not wrap orchestration in a
`main` function or an `if __name__ == "__main__"` block. This is required so
Etiq can bind each executed declared function to its captured definition.

Implement the supplied semantic requirements directly. Give each job one or
more meaningful review boundaries needed for evidence packaging. Give every declaration a
unique opaque boundary ID, normalized generated source path, and qualified
function definition. `qualified_function_name` is the lexical source name:
`normalize` for a top-level function, `outer.inner` for a nested function, and
`outer.inner.normalize` for deeper nesting. Do not include a module name or
the runtime-only `<locals>` component. Invalid examples include
`pipeline.normalize`, `outer.<locals>.inner`, `.normalize`, `outer..inner`,
wrong-case names, leaf-only names for nested functions, and class-qualified
names. Generated classes are prohibited.

Assign every declaration exactly one `semantic_stage` value from the schema.
Declare only DataFrame-processing functions that execute in the clean run and are useful to a
reviewer. Nested helpers and joins are optional. Consume both exact upstream
handoff artifacts. Keep functions deterministic and small enough for bounded
evidence review. Acceptance is based on compilation, execution, schemas,
behavioural oracles, exact handoffs, and observed declared boundaries.
