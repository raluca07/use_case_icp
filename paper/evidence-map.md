# Evidence map

Every quantitative claim in the paper traces to one of these. Nothing is quoted
from conversation memory. Re-read the artifact before writing its numbers.

| Claim | Artifact | Status |
|---|---|---|
| Four-arm table: repairs, effective repairs, input tokens, unresolved boundaries | `docs/experiments/2026-07-30-controlled-job-32968d910a7847a7/comparison-summary.json` | verified 19 Aug |
| Judge exceeded 1,048,576 char limit on the history branch; those runs rejudged | same directory, `README.md` | verified 19 Aug |
| `history_full` duration unrecoverable (`duration_seconds: null`) | `comparison-summary.json` | verified 19 Aug |
| Unresolved-boundary sets form a strict nesting chain | computed from `comparison-summary.json` | verified 19 Aug |
| `validate_repair_scope` returned early for `module_fallback` | `src/use_case_icp/repair.py` pre-`46e6fb5`; issue #3 | verified 19 Aug |
| Workflow repair tests never exercised scope enforcement | `FakeResult` vs `FakeCodex` in `tests/test_core.py` pre-`46e6fb5` | verified 19 Aug |
| `choose_target` selects causal roots for etiq arms only | `tests/test_controlled_experiment.py::test_etiq_modes_pick_the_causal_root_and_baseline_modes_do_not` | verified 19 Aug |
| `controlled_experiment.py` had zero test imports | issue #5; test suite pre-`46e6fb5` | verified 19 Aug |
| Worker resource limits defaulted to zero; HOME on the allowlist | `src/use_case_icp/etiq_executor.py` pre-`7445fd2`; issue #1 | verified 19 Aug |
| Schema catches 1 of 4 observed faults; contract catches 4 of 4 | sweep over `fault_injection` + `fault_scoring`, commit `f7d6a00` | verified 19 Aug |
| Plausible substitution evades both deterministic arms | `tests/test_fault_scoring.py::EvasionTests` | verified 19 Aug |
| Suite grew 41 -> 80 passing | `pytest tests/ -q` at `a5af896` and `f7d6a00` | verified 19 Aug |

## NOT yet evidenced (must not be claimed)

- Any LLM-judge arm result. The judge arm is specified but has not been run.
- Any repeated-sample rate for the four-arm comparison. n = 1.
- Whether `module_fallback` actually fired during the 30 July run. The repair
  records live under an ignored `outputs/` path and are not in the repository.
- Any claim about horizon length beyond the pipeline as it stands.
