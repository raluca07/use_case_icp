# Attempt 057: natural-state multi-fault localisation

Attempt 057 tests whether static or interactively disclosed native Etiq
execution evidence improves fault localisation over complete source code and
the four pipeline jobs' top-level inputs and outputs.

The deterministic bank contains four clean controls and two independently
valued instances of each of six subtle faults:

- premature contribution rounding;
- recorded-time substitution for effective-time admission;
- expiry comparison against recorded time;
- oldest-repeat retention;
- repeat ranking scoped only by source; and
- non-cumulative per-channel budget caps.

Each of the 16 instances is reviewed under six evidence treatments. Three
fresh sessions per instance and treatment produce 288 reviews and 576 logical
model calls. Every arm receives identical complete source and top-level I/O;
the treatments vary only the additional execution evidence and coarse semantic
labels. No repairs are run.

The public runner preserves that design and the original implementation. It
does not require the private authorization messages or the 25 GB partial prior
attempt that the frozen laboratory runner verifies for provenance.
