## Python simplicity

- Prefer the simplest working implementation.
- Default to module-level functions.
- Introduce a class only when it owns meaningful state, identity, or lifecycle,
  or when an external framework requires one.
- Before adding a class, check whether a function plus a dict, TypedDict, or
  dataclass is sufficient.
- Never create stateless Utils, Helpers, Managers, Services, Factories, or
  wrapper classes.
- Do not create an abstract base class, protocol, strategy, or interface for
  a single implementation.
- Prefer direct function and SDK calls over wrapper layers.
- Keep pipeline stages as functions unless they genuinely share changing state.
- Do not build for hypothetical reuse or future extensibility.
- Three similar lines are better than a premature abstraction.
- Keep one-use logic inline when extracting it would add indirection.
- Avoid excessive defensive checks, fallbacks, retries, and custom exceptions.
- Every new layer and class must justify why a simpler function-based design
  would not work.
- When modifying existing code, look for classes and layers that can be safely
  removed without obscuring behaviour.
