# Attempt 032 — Overseer full assessment

## Executive assessment

Attempt 032 completed successfully and provides a useful, tightly scoped result.
For this one frozen upstream `select_demand` fault, a reviewer starting from the
downstream result and reviewing both jobs detected the fault and identified the
upstream job in every one of the 30 faulty reviews. The meaningful treatment
difference was exact function localization:

- With source withheld, Current and Compact Fixed localized the exact faulty
  function in 0/3 repetitions.
- Adaptive Required-One localized it in 3/3 repetitions.
- In two of those three Required-One sessions, the reviewer initially blamed
  the adjacent upstream `normalize` function and changed to the correct
  `select_demand` function after nested evidence was disclosed.
- No arm produced a false positive in the 30 matched-control reviews.

This is promising evidence that disclosing the selected nested execution can
resolve ambiguity between adjacent upstream stages. It is not evidence of a
population-level effect: there is only one independent faulty pipeline and one
control pipeline. The three repetitions are repeated model calls over the same
execution, not three independent faults.

The strongest result also bundles three things: actual nested Etiq nodes,
embedded source and artifact content in those nodes, and a mandatory second
review call. The experiment therefore estimates the effect of that complete
Adaptive interaction, not graph topology alone.

One material protocol deviation affects the placebo comparison. All 12 Current
prompts say that a compact graph exists even though Current packages contain no
graph envelope or graph operation. Etiq Empty uses the same prompt plus an empty
envelope. Current is still a no-graph-evidence condition, but Current versus
Etiq Empty is not the clean no-graph-framing versus empty-graph-framing contrast
specified by N18.

## Direct answer to the research question

The question was: when a fault is injected upstream, can a reviewer catch it
while starting from the downstream result and examining both pipelines, and
does Adaptive graph access improve the result?

For this fault:

1. **Detection: yes.** Every evidence mode detected the upstream fault in all
   source-absent repetitions.
2. **Correct job: yes.** Every mode assigned the problem to the upstream job in
   all source-absent repetitions.
3. **Exact root-cause function: Adaptive Required-One helped.** It achieved 3/3
   exact `select_demand` localization without the separate source bundle,
   compared with 0/3 for Current and Compact Fixed.
4. **Optional Adaptive access was not reliably used.** Voluntary expanded in
   only 1/12 total sessions and achieved 1/3 exact localization on the
   source-absent fault.
5. **The result is specific, not general.** It establishes behavior on one
   upstream identifier-corruption fault, not across upstream fault classes or
   independently authored pipelines.

## Experiment design

### Frozen instances

The experiment reused two immutable executions from Attempt 031:

- `n16-nested-fault`: an upstream `select_demand` fault.
- `n16-clean-control`: a matched no-injection control.

The mutation changed one AST string constant inside a captured row-iteration
scope:

```python
# Intended
"need": row.get("need", "")

# Mutant
"need": row.get("source_id", "")
```

This converted natural-language need text into identifiers such as `s01`. The
mutant compiled, ran both jobs, preserved schemas and exact handoffs, produced a
plausible downstream result, and failed the prespecified `top_need` behavioral
check. The exact fault boundary was upstream `select_demand`.

### Downstream-first review scope

Every reviewer was told to begin at the downstream result and assess the same
six boundaries in this order:

1. Downstream `map_coverage`.
2. Downstream `prioritize`.
3. Downstream `synthesize`.
4. Cross the two exact-hash handoffs.
5. Upstream `select_demand`.
6. Upstream `normalize`.
7. Upstream `assemble_provenance`.

The handoffs could be cited but could not be returned as review units. Every
receipt contained exactly one review for each of the six function boundaries.

All modes received the same common base for a given instance: top-level input,
final downstream output, actual input/output/stdout/stderr for both jobs, job
topology, exact handoffs, behavioral criteria and neutral boundary
declarations. Both jobs' records were present in the initial request. Thus this
tests downstream-first reasoning over an already supplied two-job record; it
does not test whether a reviewer will independently request or retrieve the
upstream job.

### Evidence modes

| Mode | Initial treatment | Follow-up behavior |
|---|---|---|
| Current | Common execution evidence; no graph payload | None |
| Etiq Empty | Common evidence plus empty graph envelope | None |
| Compact Fixed | Six compact boundary anchors and two collapsed-child descriptors | None |
| Adaptive Voluntary | Same initial graph bytes as Fixed | May select a nested child or finalize |
| Adaptive Required-One | Same initial graph bytes as Fixed | Must select one nested child before finalizing |

Each mode was crossed with source present/absent and fault/control. The 20
packages received three fresh reviews each, producing 60 reviews. There were no
repairs by design.

## Execution and integrity audit

| Check | Assessment |
|---|---|
| Terminal | Passed: `completed_experiment_and_analysis` |
| Packages | 20/20 |
| Reviews | 60/60 |
| Provider calls | 73: 60 initial plus 13 expansion follow-ups |
| Repairs | 0, as designed |
| Matrix | Every mode × source × instance package exists exactly once |
| Repetitions | Exactly three per package |
| Common base | Canonically identical across all five modes for each paired instance/source setting |
| Fixed/Adaptive initial graph | Byte-identical within every paired comparison |
| Current graph payload | Absent |
| Etiq Empty graph payload | Present but contains zero anchors, groups, nodes and relationships |
| Review-unit contract | All 60 receipts contain the same six unique boundary IDs |
| Required expansion | 12/12 completed |
| Real disclosures | 117 nodes and 104 relationships across 13 expansions |
| Artifact operations | 0 |
| Replay | All record hashes recomputed; no duplicate logical calls |
| Prior attempt | Attempt 031 preserved; no earlier model response reused |

The package audit confirms that the treatment data, rather than different base
executions, produced the arm differences. The operation ledger confirms every
Required-One expansion disclosed nine captured nodes and eight relationships
from exactly one selected nested execution prefix.

## Primary results: source absent

Source absent is the primary population because the separate complete source
bundle would directly expose the injected assignment.

| Mode | Fault detected | Correct upstream job | Exact `select_demand` | Control FP | Expanded sessions | Calls | Input | Cached input | Output |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Current | 3/3 | 3/3 | 0/3 | 0/3 | 0/6 | 6 | 136,955 | 69,888 | 10,233 |
| Etiq Empty | 3/3 | 3/3 | 1/3 | 0/3 | 0/6 | 6 | 137,645 | 69,888 | 9,629 |
| Compact Fixed | 3/3 | 3/3 | 0/3 | 0/3 | 0/6 | 6 | 148,042 | 69,888 | 9,848 |
| Adaptive Voluntary | 3/3 | 3/3 | 1/3 | 0/3 | 1/6 | 7 | 182,547 | 71,296 | 11,753 |
| Adaptive Required-One | 3/3 | 3/3 | 3/3 | 0/3 | 6/6 | 12 | 356,085 | 119,296 | 21,208 |

Detection and correct-job localization were at ceiling in every mode. The
only discriminating scientific outcome was exact boundary localization.

### Source-absent boundary choices

| Mode | `select_demand` | `normalize` | Interpretation |
|---|---:|---:|---|
| Current | 0/3 | 3/3 | Detected the upstream corruption but blamed the adjacent normalization stage |
| Etiq Empty | 1/3 | 2/3 | One different call chose the exact boundary without graph evidence |
| Compact Fixed | 0/3 | 3/3 | Static anchors did not resolve the ambiguity |
| Adaptive Voluntary | 1/3 | 2/3 | Only the already-correct reviewer chose to expand |
| Adaptive Required-One | 3/3 | 0/3 | All reviewers ended at the exact mutation boundary |

The Etiq Empty 1/3 result is important. It shows that a one-review difference
can arise from model-call variability even without evidence. The Required-One
3/3 result is more persuasive because two of its three reviewers changed from
the same wrong `normalize` diagnosis to `select_demand` after disclosure.

## Source-present interaction

| Mode | Fault detected | Correct upstream job | Exact `select_demand` | Control FP | Expanded sessions | Calls | Input | Cached input | Output |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Current | 3/3 | 3/3 | 3/3 | 0/3 | 0/6 | 6 | 149,033 | 69,888 | 10,157 |
| Etiq Empty | 3/3 | 3/3 | 3/3 | 0/3 | 0/6 | 6 | 149,728 | 69,888 | 9,672 |
| Compact Fixed | 3/3 | 3/3 | 3/3 | 0/3 | 0/6 | 6 | 160,124 | 69,888 | 9,944 |
| Adaptive Voluntary | 3/3 | 3/3 | 3/3 | 0/3 | 0/6 | 6 | 160,176 | 69,888 | 9,942 |
| Adaptive Required-One | 3/3 | 3/3 | 3/3 | 0/3 | 6/6 | 12 | 380,251 | 129,536 | 20,931 |

All source-present arms were perfect, confirming the predicted ceiling. The
separate source bundle exposes the erroneous assignment, so graph evidence has
no measurable room to improve exact localization on this fault.

## Adaptive behavior

### Required-One

- Completion: 12/12 sessions.
- Fault sessions selecting the mutation-containing upstream child: 6/6.
- Control sessions: 6/6 selected the clean downstream row-iteration child and
  retained no suspect.
- Each expansion disclosed nine actual nodes and eight relationships.
- Final exact localization: 6/6 fault sessions across both source settings.
- Source-absent pre-expansion exact localization: 1/3.
- Source-absent final exact localization: 3/3.
- Source-absent corrections caused by disclosure: 2/3 sessions.

### Voluntary

- Uptake: 1/12 sessions.
- The only expansion occurred on a source-absent fault review.
- That reviewer had already selected `select_demand` before expanding and kept
  the same final diagnosis afterward.
- The other two source-absent fault reviewers finalized at `normalize` without
  requesting the available nested evidence.

The Voluntary result is therefore primarily a tool-uptake finding: merely
making expansion available did not cause most reviewers to use it. Required
interaction ensured uptake and resolved two otherwise persistent
mislocalizations.

### What the expansion actually revealed

The selected upstream child contained the captured loop execution. Its node
records included:

- the actual source statement showing `"need": row.get("source_id", "")`;
- eight per-row captured state nodes;
- artifact content and value previews for those rows;
- raw Etiq metadata; and
- eight captured-flow relationships.

Therefore, “source absent” means that no separate complete source bundle was
provided. It does not mean source-free after graph expansion: source embedded
in a disclosed runtime node remained visible. Likewise, no separate artifact
inspection operation was needed because the expanded nodes already carried
artifact content and previews.

This is faithful to the frozen treatment, but it narrows the causal claim. The
result demonstrates the value of the complete nested disclosure payload. It
does not separate the effects of graph structure, embedded source, artifact
values, and an additional reasoning pass.

## Token and call cost

Across the whole experiment:

| Measure | Total |
|---|---:|
| Reviews | 60 |
| Provider calls | 73 |
| Input tokens | 1,960,586 |
| Cached input tokens | 809,344 |
| Output tokens | 123,317 |
| Reasoning tokens | Unavailable from provider records |
| Total tokens | Unavailable from provider records |

Cached input is included within input and must not be added to it.

For the primary source-absent comparison, Required-One used 356,085 input
tokens versus 136,955 for Current: approximately 2.60× as many. Relative to
Current it added 219,130 input tokens, 10,975 output tokens and six calls while
moving exact localization from 0/3 to 3/3. Relative to Compact Fixed it added
208,043 input tokens and six calls for the same three-observation improvement.

Voluntary used 182,547 input tokens, approximately 1.33× Current. Most of its
increment came from the one session that chose expansion; intention-to-treat
exact localization was only 1/3.

## Prespecified contrasts and interpretation

All differences are descriptive because there is one independent fault
pipeline.

### Current versus Etiq Empty

The source-absent exact rate was 0/3 versus 1/3. This cannot be attributed to
graph evidence because Etiq Empty contained none. Moreover, all Current prompts
already included compact-graph instructions. Treat this as reviewer-call
variation, not a placebo effect estimate.

### Etiq Empty versus Compact Fixed

The source-absent exact rate was 1/3 versus 0/3. Compact anchors alone did not
improve localization. With only three repeated calls, the negative one-review
difference should not be treated as evidence that anchors are harmful.

### Current or Fixed versus Adaptive Voluntary

Voluntary was 1/3 exact versus 0/3 in both comparators. Uptake was only one
session, and that session was already correct before expansion. This does not
show that optional expansion caused the improvement.

### Current or Fixed versus Adaptive Required-One

Required-One was 3/3 exact versus 0/3 for both comparators. Two within-session
changes from `normalize` to `select_demand` support the mechanism: the disclosed
nested statement directly identified where the field substitution occurred.
This is the clearest finding in the experiment.

## Protocol-conformance assessment

### Requirements that passed

- One fresh append-only Attempt 032 was used.
- Attempt 031 scientific inputs were reused by hash; prior model calls were not.
- All five modes used both the fault and control pipeline with both source
  settings.
- The schedule was interleaved rather than completing one arm first.
- Common evidence was identical across modes for each paired instance.
- Fixed and both Adaptive modes began with identical runtime-evidence bytes.
- Fault designation, mutation target and oracle result remained controller-side.
- Current had no graph payload or graph operation.
- Etiq Empty had an empty graph payload and no operation.
- All Required-One sessions disclosed actual nested Etiq nodes.
- All reviews covered the same six function boundaries exactly once.
- Replay found no duplicate logical calls and recomputed all record hashes.

### Material deviation

The N18 design described Current as common evidence only and Etiq Empty as the
same evidence plus graph-review framing and an empty envelope. In practice, the
shared prompt for every mode included:

> The compact graph initially contains one executed anchor per boundary...

That statement appeared in 12/12 Current prompts even though Current supplied
no graph. Consequently:

- Current remains a valid no-graph-**evidence** comparator for the main Adaptive
  contrast.
- Current is not a clean no-graph-**framing** comparator.
- The Current-versus-Etiq-Empty placebo contrast should not be interpreted as
  specified.
- The misleading statement may have primed or confused Current reviewers, but
  the direction and magnitude of any effect cannot be recovered after the run.

No experimental record should be changed. This limitation belongs in any use
or publication of Attempt 032.

## Validity assessment

### What is supported

- Reviewers can trace this corrupted final result back to the upstream job when
  given both jobs' execution records and exact handoffs.
- The common evidence is sufficient for fault detection and job localization.
- Static compact anchors did not resolve the `select_demand` versus `normalize`
  ambiguity in the source-absent repetitions.
- Mandatory nested disclosure resolved that ambiguity in two of three
  within-session cases and achieved 3/3 final exact localization.
- The clean control remained clean in all 30 reviews.

### What is not supported

- A claim that Adaptive improves detection: detection was already 100% without
  graph evidence.
- A claim about general upstream faults or production pipelines.
- A population effect size or statistical significance claim.
- A claim that graph structure alone caused the localization improvement.
- A claim that optional tool availability is sufficient; uptake was 1/12.
- A valid placebo-framing estimate from Current versus Etiq Empty.
- A conclusion about artifact-inspection tools; none were used.
- A conclusion about reviewers discovering upstream context on demand; both
  jobs were supplied in the initial request.

## Overall verdict

Attempt 032 is a successful targeted mechanics experiment with a meaningful
positive result: on this upstream nested fault, forced Adaptive disclosure made
exact localization reliable where no-graph and static-anchor review repeatedly
stopped one function too late. It also demonstrates safe behavior on the
matched control.

It should be reported as a descriptive case study or pilot, not as the final
comparison experiment. The next confirmatory run should use multiple
independently authored upstream faults and controls, correct the Current prompt,
and add a matched mandatory-second-pass arm that receives no new nested evidence.
That would separate the value of disclosed Etiq content from the value of simply
asking the model to reconsider.

## All 60 individual results

| Position | Trial | Instance | Mode | Source | Rep | Detected/FP | Selected boundary | Nodes | Relationships | Artifact ops | Calls | Input | Cached | Output |
|---:|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | trial-bf693d32445c261a | n16-nested-fault | current_run | source_present | 1 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 24466 | 11648 | 1823 |
| 2 | trial-31ed26f0004f558f | n16-nested-fault | etiq_empty | source_present | 1 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 24582 | 11648 | 1805 |
| 3 | trial-4c46df39d5af45f0 | n16-nested-fault | compact_fixed | source_present | 1 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 26314 | 11648 | 1769 |
| 4 | trial-56d60f623d647995 | n16-nested-fault | adaptive_voluntary | source_present | 1 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 26323 | 11648 | 1611 |
| 5 | trial-10b9f7fdeea7da4c | n16-nested-fault | adaptive_required_one | source_present | 1 | detected | bnd-8e4e0db29e4a3223 | 9 | 8 | 0 | 2 | 62686 | 23296 | 3699 |
| 6 | trial-8eb6c730677d5ccd | n16-clean-control | etiq_empty | source_present | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 25329 | 11648 | 1491 |
| 7 | trial-ddc8bb567b6760e5 | n16-clean-control | compact_fixed | source_present | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 27061 | 11648 | 1580 |
| 8 | trial-7631340160286728 | n16-clean-control | adaptive_voluntary | source_present | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 27070 | 11648 | 1686 |
| 9 | trial-e8df7df813e2efc4 | n16-clean-control | adaptive_required_one | source_present | 1 | clean/miss | none | 9 | 8 | 0 | 2 | 64066 | 13056 | 3313 |
| 10 | trial-78edfc84276b4025 | n16-clean-control | current_run | source_present | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 25212 | 11648 | 1751 |
| 11 | trial-ee7ac742fe2e4e16 | n16-clean-control | compact_fixed | source_absent | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 25047 | 11648 | 1710 |
| 12 | trial-ee5f07cba477772e | n16-clean-control | adaptive_voluntary | source_absent | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 25056 | 11648 | 1650 |
| 13 | trial-0a4dd0e517cabba6 | n16-clean-control | adaptive_required_one | source_absent | 1 | clean/miss | none | 9 | 8 | 0 | 2 | 60036 | 13056 | 3634 |
| 14 | trial-dfad5e08cf140c9e | n16-clean-control | current_run | source_absent | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 23198 | 11648 | 1634 |
| 15 | trial-4cb933a3fee47303 | n16-clean-control | etiq_empty | source_absent | 1 | clean/miss | none | 0 | 0 | 0 | 1 | 23313 | 11648 | 1463 |
| 16 | trial-c1c522c79421f1bb | n16-nested-fault | adaptive_voluntary | source_absent | 1 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 24310 | 11648 | 1568 |
| 17 | trial-95ca6a44fb23f3f0 | n16-nested-fault | adaptive_required_one | source_absent | 1 | detected | bnd-8e4e0db29e4a3223 | 9 | 8 | 0 | 2 | 58658 | 23296 | 3639 |
| 18 | trial-0e98ce9747736a33 | n16-nested-fault | current_run | source_absent | 1 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 22452 | 11648 | 1729 |
| 19 | trial-751fd216f813b3af | n16-nested-fault | etiq_empty | source_absent | 1 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 22569 | 11648 | 1663 |
| 20 | trial-aec7d1ac3703ad93 | n16-nested-fault | compact_fixed | source_absent | 1 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 24300 | 11648 | 1532 |
| 21 | trial-cc924c9ac9f272da | n16-clean-control | adaptive_required_one | source_absent | 2 | clean/miss | none | 9 | 8 | 0 | 2 | 60038 | 23296 | 3383 |
| 22 | trial-9a0afc6832754c56 | n16-clean-control | current_run | source_absent | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 23200 | 11648 | 1709 |
| 23 | trial-074ebdba36b38311 | n16-clean-control | etiq_empty | source_absent | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 23315 | 11648 | 1662 |
| 24 | trial-9f635f1ff1743c4e | n16-clean-control | compact_fixed | source_absent | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 25047 | 11648 | 1670 |
| 25 | trial-4e68fec92d0d814a | n16-clean-control | adaptive_voluntary | source_absent | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 25057 | 11648 | 1630 |
| 26 | trial-9cdb7ef1c91f7a74 | n16-nested-fault | current_run | source_absent | 2 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 22453 | 11648 | 1672 |
| 27 | trial-2785dc221c337166 | n16-nested-fault | etiq_empty | source_absent | 2 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 22567 | 11648 | 1565 |
| 28 | trial-c1b5c1b4158fa6d4 | n16-nested-fault | compact_fixed | source_absent | 2 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 24301 | 11648 | 1643 |
| 29 | trial-b39c2b6be4bebb76 | n16-nested-fault | adaptive_voluntary | source_absent | 2 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 24309 | 11648 | 1690 |
| 30 | trial-5760506436130026 | n16-nested-fault | adaptive_required_one | source_absent | 2 | detected | bnd-8e4e0db29e4a3223 | 9 | 8 | 0 | 2 | 58659 | 23296 | 3386 |
| 31 | trial-e92527bfc5a07708 | n16-nested-fault | etiq_empty | source_present | 2 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 24581 | 11648 | 1643 |
| 32 | trial-8cc6dbcd92c905b0 | n16-nested-fault | compact_fixed | source_present | 2 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 26314 | 11648 | 1683 |
| 33 | trial-a449d953d54ce465 | n16-nested-fault | adaptive_voluntary | source_present | 2 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 26323 | 11648 | 1537 |
| 34 | trial-54a7526fb063d156 | n16-nested-fault | adaptive_required_one | source_present | 2 | detected | bnd-8e4e0db29e4a3223 | 9 | 8 | 0 | 2 | 62686 | 23296 | 3552 |
| 35 | trial-fdfd76ce4a4488a5 | n16-nested-fault | current_run | source_present | 2 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 24467 | 11648 | 1311 |
| 36 | trial-d7c72451c537c405 | n16-clean-control | compact_fixed | source_present | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 27061 | 11648 | 1663 |
| 37 | trial-b0ba0c21a5f446cb | n16-clean-control | adaptive_voluntary | source_present | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 27069 | 11648 | 1669 |
| 38 | trial-14e57340096b3729 | n16-clean-control | adaptive_required_one | source_present | 2 | clean/miss | none | 9 | 8 | 0 | 2 | 64064 | 23296 | 3409 |
| 39 | trial-990ab29285f68c92 | n16-clean-control | current_run | source_present | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 25211 | 11648 | 1788 |
| 40 | trial-117c0d8c89eca233 | n16-clean-control | etiq_empty | source_present | 2 | clean/miss | none | 0 | 0 | 0 | 1 | 25328 | 11648 | 1701 |
| 41 | trial-adec48e0dfdfc7ab | n16-nested-fault | adaptive_voluntary | source_present | 3 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 26323 | 11648 | 1749 |
| 42 | trial-d6c4752fb7144578 | n16-nested-fault | adaptive_required_one | source_present | 3 | detected | bnd-8e4e0db29e4a3223 | 9 | 8 | 0 | 2 | 62686 | 23296 | 3389 |
| 43 | trial-5aadfb94f58613e6 | n16-nested-fault | current_run | source_present | 3 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 24465 | 11648 | 1861 |
| 44 | trial-5445871ff71124f2 | n16-nested-fault | etiq_empty | source_present | 3 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 24581 | 11648 | 1797 |
| 45 | trial-5eb169e762aaf439 | n16-nested-fault | compact_fixed | source_present | 3 | detected | bnd-8e4e0db29e4a3223 | 0 | 0 | 0 | 1 | 26313 | 11648 | 1594 |
| 46 | trial-c099e528a9de2fb5 | n16-clean-control | adaptive_required_one | source_present | 3 | clean/miss | none | 9 | 8 | 0 | 2 | 64063 | 23296 | 3569 |
| 47 | trial-a260e30dbab39608 | n16-clean-control | current_run | source_present | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 25212 | 11648 | 1623 |
| 48 | trial-6d129b936a19c0ea | n16-clean-control | etiq_empty | source_present | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 25327 | 11648 | 1235 |
| 49 | trial-e0783c4a92a38443 | n16-clean-control | compact_fixed | source_present | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 27061 | 11648 | 1655 |
| 50 | trial-d655f576a78c2229 | n16-clean-control | adaptive_voluntary | source_present | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 27068 | 11648 | 1690 |
| 51 | trial-87806659ca8329d8 | n16-clean-control | current_run | source_absent | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 23199 | 11648 | 1732 |
| 52 | trial-46e123c826baf68e | n16-clean-control | etiq_empty | source_absent | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 23315 | 11648 | 1687 |
| 53 | trial-58dc3da50231ac9e | n16-clean-control | compact_fixed | source_absent | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 25046 | 11648 | 1674 |
| 54 | trial-fb498648f9ac0317 | n16-clean-control | adaptive_voluntary | source_absent | 3 | clean/miss | none | 0 | 0 | 0 | 1 | 25058 | 11648 | 1661 |
| 55 | trial-5221bd1288e15761 | n16-clean-control | adaptive_required_one | source_absent | 3 | clean/miss | none | 9 | 8 | 0 | 2 | 60036 | 13056 | 3603 |
| 56 | trial-887e41d589c84e5f | n16-nested-fault | etiq_empty | source_absent | 3 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 22566 | 11648 | 1589 |
| 57 | trial-8c4021b6e0abf151 | n16-nested-fault | compact_fixed | source_absent | 3 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 24301 | 11648 | 1619 |
| 58 | trial-9af4b3b5ede5192b | n16-nested-fault | adaptive_voluntary | source_absent | 3 | detected | bnd-8e4e0db29e4a3223 | 9 | 8 | 0 | 2 | 58757 | 13056 | 3554 |
| 59 | trial-1783eba07d299c69 | n16-nested-fault | adaptive_required_one | source_absent | 3 | detected | bnd-8e4e0db29e4a3223 | 9 | 8 | 0 | 2 | 58658 | 23296 | 3563 |
| 60 | trial-8f0ad183eae8c0ff | n16-nested-fault | current_run | source_absent | 3 | detected | bnd-c4af215f98a887d0 | 0 | 0 | 0 | 1 | 22453 | 11648 | 1757 |

## Reproducibility and bound artifacts

The original Developer report remains unchanged because its exact file hash is
bound into the results handoff. The 60-row trial table from that report is
reproduced above so this assessment is self-contained:

- [Complete Developer findings](n18-downstream-first-adaptive-vs-no-graph-complete-findings.md)

Immutable experiment records:

- `outputs/fault-experiments-v2-2-n10/attempt-032/experiment-freeze.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/live-consumption.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/analysis/summary.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/replay/reconciliation.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/terminal-state.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/qualification/developer-n18-results-handoff.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/reviews/`
- `outputs/fault-experiments-v2-2-n10/attempt-032/ledger/call-attempt/`

Key logical hashes:

| Artifact | SHA-256 |
|---|---|
| Freeze | `sha256:b1d8e808f1951904e6c2a1fdef9658cc50ae77a176a9e26f8d3778a827e3ef59` |
| Package tree | `sha256:eefae54e7d300da1351861719260318eb581c483813dc8afa8544fef4535de19` |
| Review tree | `sha256:d9785ee3547a5c26a0eceb92e4e467dc9fd398c0ab2253555825ae269513bb97` |
| Analysis | `sha256:b34f9c879e947f3097fe155e187378d8d6b25c93f76a7a33cd3c3e313d942438` |
| Replay | `sha256:a11aefb84d82605d65c9680414d1ebd61043774df374e8ca090bdeb3cf23930a` |
| Terminal | `sha256:b481df61a5c19223f4518f371297487f89dac30e447ab60b9f3627ebfd2c2adf` |
| Results handoff | `sha256:c047b9fc6b08b234bc3ffc48f5674ce52dd09ed7258b2f7388020bb27054febf` |
