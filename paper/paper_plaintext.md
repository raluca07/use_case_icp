# Compute Over the Graph, Do Not Show It

*What an execution graph is worth to a self-repairing agent, measured against injected faults*

Fabio Rovai (Kampakis and Co Ltd, trading as The Tesseract Academy) and Raluca Crisan (Etiq AI)

Draft for NeurIPS 2026 workshop submission. Authorship and affiliation order to be confirmed.

---

## Abstract

An execution graph records what a generated pipeline did rather than what a model said it did, and is increasingly proposed as the substrate an agent uses to repair itself. We ask what that substrate is worth by injecting faults whose location is known by construction, so trust decisions can be scored instead of trusted. The graph pays off through computation over its structure, not through presentation to a model. Computing over it works: a selector walking the dataflow to the causal root identifies the faulty boundary in 21 of 21 contested cases where a source-order baseline manages none, and its advantage is exactly the extent to which declaration order diverges from execution order. Showing it to a model is more delicate than expected: a context region selected in advance is indistinguishable from a size-matched random one, yet a protocol that withholds nested detail and lets the reviewer request it one step at a time matches sending everything on less context and does separate from random, so the benefit lies in the interaction rather than the slice. The sharpest evidence is where checks are placed. Over 90 data faults, hand-written contracts detect 26 and localise *none*, firing every time on an aggregating stage downstream of the cause, which is the downstream-blame bias the model judges showed reproduced in a signal containing no model. Checks learned from caught faults and placed where they entered detect 60 and localise all 60, with zero false suspicion on held-out healthy runs once vocabulary checks are restricted to domains the healthy population shows to be closed. Five measurement artifacts caught during this work, each of which would have published a confident wrong number, argue that such a benchmark is worth as much for what it invalidates as for what it reports.

 ## Introduction

An agent that works for a long time on one objective will eventually get something wrong, and what happens next is a trust decision. It has to say which earlier steps still stand, which are contaminated, and where to resume. Wrong in one direction it redoes sound work. Wrong in the other it builds on a spoiled result, which is worse and much harder to see.

The architectural answer under study is the execution graph. A scanner captures the artifacts a generated pipeline produced and the functions that produced them, and that record becomes the durable state the agent reasons over. The appeal is that a graph built from execution cannot be talked out of what happened. Recent work treats provenance of this kind as the substrate for agent trust [wang2026traces] and as the basis for recoverable execution from recorded checkpoints [zhuang2026agentrewind].

We take the architecture seriously enough to ask what it is worth, and the answer we find is narrower and more useful than the one usually assumed. \textbf{The graph pays off through computation over its structure, and not through presentation to a model.} Those are different uses of the same artifact and they do not succeed together. A selector that walks the recorded dataflow to the causal root of a set of flagged boundaries is exact where a baseline without that relation is useless. Acceptance criteria attached to boundaries catch faults a model reading the same evidence does not. But handing a model a graph-selected region of context, which is the use the substrate is most often justified by, cannot be distinguished from handing it a size-matched random region, and accumulating history costs two orders of magnitude more context for no gain.

Answering the question at all required a measurement the system does not have. Trust labels here are produced by one model reviewing another, so nothing in the loop holds an independent answer; when a reviewer calls a boundary trusted, no artifact can contradict it. There is good reason not to take that on faith, since judges prefer text they find familiar [wataoka2024selfpreference] and a judge's agreement with itself can be high while its agreement with the truth is not [norman2026reliability], and a verifier checking only what it can express admits confident false positives [helff2026gaming]. We supply the missing answer by injecting a fault into a named boundary through the same scope machinery a repair must pass, so the poisoned boundary is confined by mechanism rather than by assertion, and what it contaminates is read from the pipeline's own dataflow. We are not aware of prior work scoring an agent's own boundary trust labels against faults injected into its own pipeline with known ground truth.

The paper's second contribution is methodological and, we think, the more transferable one. Five times during this work a measurement produced a confident number that was an artifact of how we had built the experiment rather than a property of the system: a static-code arm that scored 75% because our faults were source mutations and collapsed to 0% once they moved into recorded data; two models that returned a fixed answer regardless of input while appearing to score respectably; and a selection result we reported as significant on a third of its eventual sample and had to retract. Each would have survived into a published table. We report them alongside the results because a benchmark for verifying agents that cannot catch its own defects has no standing to measure anyone else's. Extended related work appears in Appendix~(app:related).

 ## The system under test

The pipeline is a marketing research agent. A model authors Python that discovers market demand from public sources, a scanner executes it and captures the values crossing each function boundary, a reviewing session judges each boundary, and a repairing session returns a change confined to one boundary.

Three properties matter. The generated pipeline declares its own review boundaries as named functions, and the review and repair machinery anchors to those declarations. Stage inputs and outputs pass by argument and return value rather than shared state, which makes a stage replayable against its recorded inputs. And a run records a network cassette, so a pipeline that fetches third-party sources replays against exactly the responses the original run saw. The cassette is what makes this work deterministic, and later what lets us move faults out of the source entirely.

 ## What the published comparison can and cannot settle

The published comparison ran four arms over the same frozen pipeline, input and recorded corpus, differing in what the reviewer sees: stage metadata, accumulated history, the complete graph, or a selected part of it (table in Appendix~(app:published)). It is carefully controlled: the same frozen pipeline, input and recorded corpus across arms, fresh sessions, no cross-arm visibility. Three properties nonetheless prevent it settling which regime is better, and they determine what this paper had to build.

Sample size is the first. One run per arm and three repairs within each makes every quantity a count out of three or a single ordinal, and the recommended arm ties the accumulated-history baseline on effective repairs. Second, the arms were not adjudicated identically: the archived record states the first common full-graph judge exceeded the model's 1{,}048{,}576 character input limit on the history branch, and those runs were rejudged with isolated graph-selected judges, a failure that also removed that arm's timing. Third, and most usefully, the function selecting which boundary to repair differs across arms. The graph arms filter flagged units to causal roots using upstream identifiers; the baselines rotate with no causal step. The comparison is presented as one of context regimes but the arms also differ in how they choose a target. Rather than control that away we make it the treatment, and it produces the paper's largest effect.

 ## Injecting a fault whose location is known

The missing ingredient is an answer. If we know which boundary is wrong, a trust signal stops being something the system relies on and becomes something we can score.

We obtain that answer by injecting the fault ourselves. A fault is a small transformation of one boundary function's source. It is applied by locating the function, rewriting its abstract syntax tree, and splicing the result back through the same scope validator a repair must pass. That last detail is what makes the ground truth trustworthy rather than asserted: an injected fault is confined to one boundary by the same mechanism that confines a repair, so if the confinement is broken the injection fails rather than silently spreading.

Contamination is read from the pipeline rather than declared by us. A boundary is downstream of the injected one when the injected function's result reaches its arguments, either directly as a nested call or through a module-level name bound to that result. Ground truth is therefore a pair: the injected boundary, and the ordered list of boundaries its output reaches.

Two guards keep the corpus honest. An injection that leaves the source unchanged is refused, because a fault nothing can detect would enter the corpus and depress every signal's score equally, making every arm look worse without distinguishing them. And a test asserts that every fault in the catalogue still changes something on a representative pipeline; when we added it, it caught one that did not.

### The fault catalogue

The catalogue separates faults observed in this system's own operational logs from synthetic ones, because the two carry different weight. Three are observed. A field disappears from a stage's output after upstream source reads failed, which this system's logs record alongside HTTP 429, 403 and 500 responses from four source registries. A collected sequence is shortened while the stage still reports success. An identifier is replaced by a plausible placeholder, which is what a schema-bound worker actually returned before a reviewing model discarded its output. Two are synthetic: a comparison operator is inverted, and a ranking is reversed while every value in it stays present and valid.

An invariant here is an acceptance criterion attached to a boundary and checked deterministically against the value it produced; a concrete example is given in Appendix~(app:invariant).

### What a trust signal is scored on

A signal labels every boundary trusted or suspect. Scoring compares those labels with the injected fault and reports four things.

*False trust* is the injected boundary being labelled trusted. This is the safety failure, and a signal that labels everything trusted scores perfectly on cost and fails completely here.

*False suspicion* is a boundary that is neither the injected one nor contaminated by it being flagged. This is the cost, paid in redone work.

*Localisation error* is signed, and the sign carries the finding. The resume point is the earliest suspect boundary, which is where a run acting on these labels would restart. A negative error means it restarts upstream of the fault and redoes sound work. A positive error means it restarts past the fault and keeps output the fault has already contaminated. Averaging the two would hide the second failure inside the first, so we report them separately.

*Shipped contaminated output* records whether the positive case occurred.

### Arms

Four signals are in scope. Structural schema validation checks a stage's output against its declared JSON schema. Content invariants check criteria the boundary declared in advance: required fields, minimum counts, value patterns and ordering. Both are deterministic and cost nothing per fault, which is what allows the corpus to be large. The third arm is the reviewing model itself, which is the only arm that costs tokens and the only one whose labels vary between runs on the same input.

 ## Results

The results divide along the paper's claim. Sections~(sec:compute1) to (sec:compute2) concern computing over the graph's structure, where it pays. The final part concerns showing the graph to a model, where it does not.

### Detection: what declared signals catch

A first corpus crashed on seventeen of twenty-eight faults, so execution is itself a strong free detector; but a fault that halts the run never reaches a trust decision, and real generated pipelines read inputs through accessors with defaults. Everything below concerns faults such a pipeline survives silently: 104 cases across two pipelines, the cross product of five fault classes, the boundaries and the applicable parameters, most from classes observed in this system's own logs.

Structural schema validation leaves 78% undetected, declared invariants 27%, and a model judge 18%, none of them raising a single false suspicion. The intervals for the latter two overlap and an exact McNemar test does not separate them (p=0.16), so we make no claim that either is better; what the sample supports is that both are significantly worse than their union, which leaves 7% (p<0.0001 and p=0.0005). The failures are disjoint. Invariants catch twelve faults the judge misses, every one a matter of counting or shape; the judge catches twenty-one the invariants miss, eighteen of them substituted identifiers including every plausible one that defeated the pattern check. Schema validation contributes nothing either does not, detecting only the fault class that changes a record's shape.

### What the graph is actually for

Detection tells a run something is wrong. It does not say what to repair. When several boundaries are flagged, something must choose, and that choice is where the graph does work no cheaper signal can. We measure a selector that walks recorded dataflow to the causal root against one that walks the declared boundary list in order.

The comparison is only meaningful when those two orders differ. In a pipeline whose functions are declared in the order they run, the causal root of any flagged set is simply the first of them, and the selectors cannot disagree. Models writing code do not reliably declare in execution order, so we test both conditions across four shapes: a deep chain, a wide fan-out, a diamond that splits and reconverges, and a short chain.

Shape | Declaration order | Contested | Causal root | Source order
chain-8 | dataflow | 16 | 100% | 100%
chain-8 | scrambled | 16 | 100% | 38%
fan-6 | scrambled | 2 | 100% | 0%
diamond-4 | scrambled | 14 | 100% | 14%
chain-3 | scrambled | 6 | 100% | 0%
all | dataflow | 38 | 100% | 100%
all | scrambled | 38 | **100%** | **21%**
(Repair-target selection across four pipeline shapes. The causal-root selector is exact in every cell. The baseline matches it only when declaration order already encodes execution order.)

The causal-root selector is exact in all 38 contested cases of every shape and both orderings. The baseline matches it perfectly when declaration order happens to encode execution order and falls to 21% when it does not. This gives the graph's value a precise form: \emph{it is worth exactly the extent to which declaration order diverges from execution order}. A team whose pipelines are written in order gains nothing here. A team whose pipelines are model-authored gains the difference between 100 and 21 per cent, and cannot know in advance which case they are in, which is itself an argument for computing the relation rather than assuming it.

### The model judge, and where each signal fails

We expected the language-model judge to be the weak arm. It was not, and reporting what happened instead is more useful than the result we set out to find.

The judge is a 3B model run locally, asked about one boundary at a time and given that stage's declared purpose in prose. Across both corpora, 104 silent faults with three repeats each, it never once disagreed with itself. Every one of the 104 cases came back unanimous over 312 calls, with no parse failures.

A false-trust rate alone would mean nothing, because a judge answering suspect indiscriminately scores perfectly while being useless. We therefore asked the same judge about boundaries known to be sound: every boundary of the clean unfaulted pipeline, and for each case a boundary strictly upstream of the fault, which cannot be contaminated. Across 102 such calls it returned trusted every time, so its false-suspicion rate matches both deterministic signals at zero and the comparison stands.

Signal | Missed | Rate | 95% CI
schema validation | 81/104 | 78% | [69, 85]
declared invariants | 28/104 | 27% | [19, 36]
model judge (3B) | 19/104 | 18% | [12, 27]
invariants + judge | 7/104 | 7% | [3, 13]
(Faults left undetected over 104 cases, with Wilson intervals. The intervals for invariants and the judge overlap; the pair is separated from both.)

### What the sample supports, and what it does not

The ranking in Table~(tab:signals) invites a conclusion the data does not carry, so we tested it on the paired outcomes. An exact McNemar test does not separate the judge from declared invariants (12 against 21 discordant, p=0.16), and their confidence intervals overlap. We make no claim that either is the better signal, and the sample is large enough that this is a finding rather than a shrug: two signals of quite different kinds, one a compiled check and one a 3B model, are not distinguishable by error rate.

The combination is a different matter. It improves on invariants alone (0 against 21, p<0.0001) and on the judge alone (0 against 12, p=0.0005). Both single signals are significantly worse than using both; neither is significantly worse than the other. Schema validation is separated from all three at p<0.0001, and adding it to any pair changes nothing, because it catches nothing they do not.

The result is therefore about complementarity rather than ranking. Invariants catch twelve faults the judge misses, and every one is a matter of counting or shape: fields removed from a record, sequences silently shortened. The judge catches twenty-one the invariants miss, and eighteen of those are substituted identifiers, including every plausible one that defeated the pattern check. Each signal is blind close to where the other sees, and it is that disjointness the evidence establishes.

It would be wrong to read this as a model outperforming a static check. The judge was given the stage's declared purpose, for instance that a retrieval stage must fetch every source in every declared class and report what it retrieved. That is an acceptance criterion. It is the same kind of statement the invariant encodes, written in prose and checked by a model rather than compiled into a count and a regular expression.

So the comparison was never between having criteria and not having them. It was between two encodings of the same criteria, and the encodings fail differently. A count is exact about quantity and silent about meaning. A sentence carries meaning and is vague about quantity. That is why the union is so much stronger than either part, and it is a reason to declare criteria at a boundary at all rather than a reason to prefer one checker.

### Showing the graph to a model does not pay

The use an execution graph is most often justified by is presentation: give the agent a relevant slice rather than everything or nothing. Four regimes were asked the same question over a branching corpus, name the faulty stage, with the injected fault as the answer.

Regime | Accuracy | Context | Note
stage purposes only | 15% | 1{,}343 | no captured values
size-matched random slice | 35% | 1{,}402 | control
graph-selected region | 40% | 1{,}466 | p=0.69 vs random
selected plus expansion | 46% | 1{,}466 | the deployed method
complete current run | 50% | 1{,}913 | 
accumulated history, d=64 | 40% | 129{,}246 | 
(Localisation under six context regimes. Selection is not separable from a random slice of the same size, including in the form the system actually deploys; accumulated history costs two orders of magnitude more for less.)

Captured values matter enormously, 15% against 40 to 50 for any regime showing what the code produced, which is the strongest evidence here that execution records are the right substrate. Selecting among them does not help: the graph-selected region is not separable from a size-matched random slice (p=0.69), and adding expansion on request, which is the method as deployed rather than a weakened stand-in, reaches 46% against 50% for simply showing everything. Accumulated history degrades from 52% at depth four or less to 40% at depth sixteen or more while its context grows to 129{,}246 characters against 1{,}913. The mechanism is visible in the failures: shown captured values, a model names a downstream stage in 83% of cases, and selection acts on the prompt rather than on the answer, so a model handed a selected region still blames the most downstream thing in it.

### A protocol that withholds and is asked

The arms above hand the reviewer a slice chosen in advance. The system we study does something different, and the distinction turns out to matter. Its initial package carries nodes at exactly the boundary's function-stack level, names the nested helpers without their contents, and permits the reviewer to request one direct child at a time for at most three rounds. Evaluating that needs a pipeline whose boundaries call helpers, so we built one and planted faults at three depths: visible at the boundary, inside a helper, and inside a sub-helper.

Arm | Faults | Clean | Mean chars | Expansions
collapsed, expansion on request | 5/6 | 4/4 | 841 | 9
everything, flattened | 5/6 | 4/4 | 922 | 0
random subset, budget matched | 4/6 | 3/4 | 831 | 0
(The deployed protocol against sending everything and against a size-matched random subset. It matches the former on nine per cent less context and, unlike every fixed-slice arm we tested, does not tie the latter.)

This is the only selection arm in the paper that separates from a size-matched random control, and it forces a narrower statement of the result above. A selected region handed over in advance is not better than a random one of the same size. A protocol that withholds nested detail and lets the reviewer pull what it needs is a different mechanism, and on this evidence it works: the same accuracy as sending everything, for less, and better than random at equal cost. What we can say is that the benefit lies in the interaction rather than in the choice of slice, which is not what we expected and not what the fixed-slice arms could have shown.

Two details qualify it. Faults planted two levels deep were caught with zero and one expansions, because a deep fault usually surfaces in the boundary's own output, so the reviewer rarely has to drill to where the fault lives. And the single miss is a reversed ranking judged clean after an expansion was spent, which is precisely the fault an ordering scar catches deterministically in Section~(sec:scars). With ten cases per arm this is directional rather than sized, and we implemented the collapsed-helper half of the protocol but not its artifact inspection.

### External validity: three recovered runs of the real system

Everything above runs on pipelines we authored, which is the weakest thing about it. Three records of the real system, deleted in a cleanup commit but recoverable from its git history, supply the external check.

A four-arm run of 29 July 2026, on the real model-authored pipeline with a frontier model, reports that graph-selected context matched the full graph's issue coverage with 46% fewer input tokens on the initial run and 47% on the latest, while accumulated flat history grew from 71{,}470 to 303{,}757 characters and became 29% more expensive than the selected region. A second run of 30 July shows the same shape at 31{,}369 tokens for stage metadata against 109{,}590 for accumulated history, all arms finding the same three issue functions. This is the efficiency half of our claim, measured on the system itself.

The same 29 July record contains one further observation we regard as the most important sentence in either dataset: accumulated history \emph{retained a previously repaired boundary as an open issue after every other arm treated it as resolved}, which its authors attribute to stale prior versions remaining salient in flat history. Our synthetic history sweep never produced this, and the recovered run shows why: our accumulated history was clean prior iterations, which hand the model a helpful baseline to diff against, whereas real history contains superseded versions of boundaries that have since changed. Staleness, not volume, is the active ingredient. Section~(sec:stale) tests that as an intervention.

### Staleness, briefly

Accumulated history harms a model judge, and what it does depends on the model. A superseded faulty run in context halves one judge's detection of genuine new faults; another judge cannot recognise a clean run without one, inventing a fault in sixteen of twenty clean cases and naming the final stage every time; the deployed system's own record shows a third model resurrecting a resolved issue from flat history. Neither of ours re-flagged the repaired boundary, which was the predicted failure. The stable conclusion is a dependence rather than a direction: history content modulates judge behaviour in model-specific ways that no prompt here controlled, while deterministic signals are unaffected by context by construction. Full cells in Appendix~(app:stale); the detection drop does not survive the multiplicity correction of Section~(sec:power).

### Checks placed where faults enter

Every signal so far was written in advance by an author deciding what to assert. The alternative is to learn a check from a fault once it has been caught, place it on the boundary where it entered, and pay for that fault only once.

We adopt the term *scar* from prior work on coupling kernels, where a scar is a low-rank invariant subspace that lets a query be *read* exactly rather than searched over an intractably large state space [rovai2026worldkernel], and from its use in agent goal induction, where a goal is treated as a low-rank commitment set read in a number of probes proportional to its rank [rovai2026civex]. The move transfers directly. A caught fault commits a small set of properties; rather than re-deriving them on every subsequent run, they are read off once and pinned to the boundary that produced them. What is new here is the application to trust decisions and the measurement of what it buys, which separates the two halves of this paper more sharply than anything else.

A scar is minted from a population of healthy observations of one boundary and one faulty observation of the same boundary, keeping only structural properties that held across the whole population and broke in the faulty one: a field present throughout and now absent, a count below its healthy floor, a list that stopped being homogeneous, an ordering that held and no longer does. A property expressible as no such check is refused rather than stored as vague suspicion, because the deterministic signals' zero false-suspicion rate is the thing that makes them worth having.

Signal | Detected | Localised | Misplaced
declared contracts | 26/90 | **0/90** | 26/90
learned scars | 60/90 | **60/90** | 0/90
(Ninety data faults. Localisation is whether the flagged boundary is the one the fault entered. Declared contracts never localise: every detection fires on an aggregating stage downstream of the cause.)

Table~(tab:scars) contains the result we consider most important in this paper. Hand-written contracts detect 26 of 90 faults and localise *none* of them. A stage that faithfully passes on a bad input satisfies every criterion anyone thought to write about its own behaviour, so the checks fire on the aggregating stages downstream and the suspect set sits entirely past the cause. This is the same failure the model judges showed, in a signal with no model in it, which tells us the downstream-blame bias is not a property of language models but of where checks are placed. Scars localise every fault they detect, because a scar is placed where the fault was observed to enter rather than where an author's attention happened to fall.

Two further results bound the method. Population size does not affect detection at all, identical at one, four and eight healthy observations; what it buys is false suspicion, falling from 21 of 56 boundary-checks at n=1 to zero at n=8. A single healthy observation cannot separate an invariant from that run's value, so scars minted from one pair fire on honest variation, and only a population can tell the difference. Second, a vocabulary check is minted only when the population shows the domain closed: identifiers drawn from a fixed registry stop admitting new values, dates and free text do not, and a vocabulary check over an open domain is guaranteed to fire on an honest run eventually. Enforcing that costs detection, 73 falling to 60, and takes false suspicion on held-out healthy runs the scars never saw from 3 of 28 to zero. We regard that trade as the correct one, and the refusal of faults visible only in an open domain as a feature of the design.

We also implemented the two graph computations this suggests, and both are negative. Forward propagation of contamination reclassifies nothing, because the declared checks fire downstream of the fault and there is nothing to propagate forward from. Backward attribution narrows to seven boundaries of seven, because in a pipeline that funnels through a merge every branch is an ancestor of the first suspect. Both failures have one cause: exoneration requires a check that the fault *would have violated*, not merely a check that passed, and a hand-written contract does not supply one where a scar does.

 ## Defects, in the system and in the measurement

### In the trust machinery

Four defects, detailed in Appendix~(app:defects): the repair-scope validator silently skipped enforcement whenever a declared boundary name failed to resolve, a branch the authoring model controls and that the entire workflow test suite unknowingly ran through; the module producing the published numbers had no tests; resource limits around generated code were inactive by default; and the real home directory, with credentials, reached model-written code that has network access outside replay [greshake2023injection].

### In our own measurement

A benchmark built to verify agents has no standing to measure anyone else if it cannot catch its own defects, and five times a confident number here turned out to be an artifact of how we built the experiment.

A control arm shown the source text of the implicated region scored 75%, appearing to refute the premise that captured values matter; our faults were source mutations, so it was reading the fault rather than diagnosing it, and moving faults into recorded responses with the source byte-identical across all 48 cases dropped it to 0%. A 3B judge scored 0% on seven-way localisation while returning valid stage names, answering one of two regardless of input; a 30B model later returned `transform_3` for all 48 cases at every chain length from five to seventeen stages, producing a flat apparent degradation with horizon that was a constant. Both look like results until the answer distribution is examined, and neither can exhibit an effect of context because neither depends on context. We reported that graph-selected context beat a size-matched random slice, 40 against 28%, on a third of the eventual sample; at full sample the difference vanished (p=0.69), and the claim was retracted, having been made in the same paragraph as a criticism of single-run reporting. Because data-level faults land on the stage that fetches the corrupted response, ground truth concentrated on three of seven boundaries, making the correct chance baseline 42% rather than 14%, and an arm shown no captured values scored exactly that by always naming the most common answer. Finally, a dump cap truncated retrieval evidence before the judge saw it, so faults on later sources were invisible and the judge blamed downstream aggregates. Each would have survived into a table, and we take the frequency as evidence that scoring against constructed ground truth is worth as much for what it invalidates as for what it establishes.

 ## Limitations

Three judges appear here, a 3B, a 30B mixture and one frontier model, with large and non-uniform capability differences, so no rate should be read as a property of models in general; and the judge was never asked to choose among boundaries the way the selector does, so the selection and detection results are not one story.

Faults are injected rather than arising from a model, and model-authored faults would differ systematically from ours; scars inherit this doubly, learning only differences observable at the boundary where the fault entered, and evaluated on one fault taxonomy. Our contamination model follows module-level dataflow, so state passed through a file, a global or a side effect defeats it, which makes it sound for conforming pipelines and unsound for the ones most likely broken. Whether the unresolvable-target defect fired during the published run cannot be determined from the repository, and the recovered records corroborate the efficiency claim without bearing on detection rates. Finally, no pipeline exceeds seventeen stages, so nothing measures the true long-horizon regime [chen2026horizon].

 ## References

- Cemri, Mert and Pan, Melissa Z. and Yang, Shuyi and Agrawal, Lakshya A. and Chopra, Bhavya and Tiwari, Rishabh and Keutzer, Kurt and Parameswaran, Aditya and Klein, Dan and Ramchandran, Kannan and Zaharia, Matei and Gonzalez, Joseph E. and Stoica, Ion. Why Do Multi-Agent LLM Systems Fail?. arXiv preprint arXiv:2503.13657. 2025. https://arxiv.org/abs/2503.13657
- Wataoka, Koki and Takahashi, Tsubasa and Ri, Ryokan. Self-Preference Bias in LLM-as-a-Judge. arXiv preprint arXiv:2410.21819. 2024. https://arxiv.org/abs/2410.21819
- Norman, Justin D. and Rivera, Michael U. and Hughes, D. Alex. Reliability without Validity: A Systematic, Large-Scale Evaluation of LLM-as-a-Judge Models Across Agreement, Consistency, and Bias. arXiv preprint arXiv:2606.19544. 2026. https://arxiv.org/abs/2606.19544
- Greshake, Kai and Abdelnabi, Sahar and Mishra, Shailesh and Endres, Christoph and Holz, Thorsten and Fritz, Mario. Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection. arXiv preprint arXiv:2302.12173. 2023. https://arxiv.org/abs/2302.12173
- Jia, Yue and Harman, Mark. An Analysis and Survey of the Development of Mutation Testing. IEEE Transactions on Software Engineering. 2011. doi:10.1109/TSE.2010.62
- Freire, Juliana and Koop, David and Santos, Emanuele and Silva, Claudio. Provenance for Computational Tasks: A Survey. Computing in Science & Engineering. 2008. doi:10.1109/MCSE.2008.79
- Wang, Yiqi and Zhang, Jiaqi and Cai, Taotao and Liu, Zirui. From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents. arXiv preprint arXiv:2606.04990. 2026. https://arxiv.org/abs/2606.04990
- Zhuang, Yu and Chen, Kefei and Duan, Yitong and Zheng, Shuxin. AgentRewind: Recoverable Execution for Long-Horizon LLM Agents. arXiv preprint arXiv:2608.14380. 2026. https://arxiv.org/abs/2608.14380
- Helff, Lukas and Delfosse, Quentin and Steinmann, David and H"arle, Ruben. LLMs Gaming Verifiers: RLVR can Lead to Reward Hacking. arXiv preprint arXiv:2604.15149. 2026. https://arxiv.org/abs/2604.15149
- Chen, Mingguang and Wang, Licheng and Qu, Bo. The Horizon Gap: Planning, Memory, Execution, Training, and Evaluation for Long-Horizon LLM Agents. arXiv preprint arXiv:2608.06663. 2026. https://arxiv.org/abs/2608.06663
- Thaman, Kunvar. Reward Hacking Benchmark: Measuring Exploits in LLM Agents with Tool Use. arXiv preprint arXiv:2605.02964. 2026. https://arxiv.org/abs/2605.02964
- Rovai, Fabio. WorldKernel: A World Model is the Coupling Kernel of Admissible Possible Worlds. arXiv preprint arXiv:2606.10934. 2026. https://arxiv.org/abs/2606.10934
- Rovai, Fabio. CIVeX: Causal Intervention Verification for Language Agents. arXiv preprint arXiv:2605.09168. 2026. https://arxiv.org/abs/2605.09168



## Artifact availability

The benchmark, every corpus, all result files and the analysis scripts accompany this submission as an anonymized artifact and will be released publicly on acceptance; the recovered records of Section~(sec:external) are identified by the commit hash of the repository they were recovered from.

## The published comparison

Arm | Repairs | Effective | Input tokens | Unresolved boundaries
`semantic_only` | 3 | 0 | 568{,}715 | 4
`history_full` | 3 | 1 | 1{,}824{,}533 | 4
`etiq_full` | 3 | 0 | 1{,}331{,}686 | 3
`etiq_selected` | 3 | 1 | 1{,}000{,}797 | 2
(The published comparison, one run per arm, 30 July 2026, taken from the archived machine-readable summary. Its own record notes that ``no arm reached final trust''.)

## Defects in the trust machinery, in detail

The validator confining a repair to one boundary returned early whenever the target could not be resolved to a function, so in that branch a repair could rewrite the whole target file. The branch is reached whenever a declared boundary name does not resolve in the generated source, and the authoring model writes both, so it is reachable by ordinary error and steerable on purpose; the harness splices over the same span, so an unresolvable target produced a whole-file substitution the validator accepted. It was untested, because the scanner fixture reported a call stack inside functions the authoring fixture never defined, so no target ever resolved and every workflow test of repair ran through the unenforced branch. Separately, the module producing the published numbers was imported by no test, resource limits around generated code defaulted to inactive, and the home directory reached the generated pipeline, which has network access outside replay mode; captured third-party text now reaches the reviewer inside a digest-keyed fence it cannot close [greshake2023injection].

## A declared invariant, concretely

The retrieval stage of the branching pipeline carries: `retrieve_registries` must return `source_ids` and `source_class`; `source_ids` must hold at least three entries; every entry must match `\^{`[a-z]+_[a-z]+\$}. Three clauses catching a disappeared field, a silently shortened retrieval, and a malformed identifier; what none can catch is an identifier that is correctly shaped and simply wrong, which is measured rather than assumed in the body.

## Extended related work

Empirical work on why multi-agent systems fail supplies the closest framing for our problem: Cemri et al.\ build a taxonomy from more than two hundred annotated traces and make task verification one of its three top-level categories [cemri2025multiagent], though their failures are annotated by human experts rather than detected by the system at runtime; Chen et al.\ survey the same territory as a gap between what long-horizon agents are asked to do and what their planning, memory and evaluation machinery supports [chen2026horizon]. The assumption our benchmark tests is that a language model supplies that verification, and there is reason for caution: judges favour text more familiar to themselves [wataoka2024selfpreference], which matters because reviewer and reviewed here share a model family; a judge's self-agreement can be high while its agreement with the truth is not [norman2026reliability], the distinction our localisation metric operationalises; verifiers checking only what they can express admit confident false positives [helff2026gaming]; and multi-step agents exploit naturalistic chances to tamper with what evaluates them [thaman2026rewardhacking]. Provenance-based trust for agents [wang2026traces] and recoverable execution from recorded checkpoints [zhuang2026agentrewind] are the constructive lines this work measures rather than proposes.

Our method borrows its central move from mutation testing, a defect of known location measuring whether a suite detects it, including the equivalent-mutant problem we meet as an injection that changes nothing [jia2011mutation]. The substrate is execution provenance [freire2008provenance], whose distinction between a record of what a computation did and a claim about what it meant locates this paper's difficulty: the graph is a record, the trust label is a claim, and only the first is checkable. The fencing of Section~(sec:defects) addresses indirect prompt injection through fetched content [greshake2023injection], a designed-in exposure here since the pipeline must retrieve third-party sources at runtime.

## Staleness intervention, full results

We crossed two factors, twenty cases per cell on each of two judges: the history shown (clean prior iterations, or a superseded run carrying a fault since repaired) and the current run (clean, or carrying a new fault at a different boundary), asking for the faulty stage of the current run or none.

History | Current run | Judge A | Judge B
clean | clean | 18/20 | 4/20
stale | clean | 17/20 | 13/20
clean | new fault | 18/20 | 19/20
stale | new fault | 11/20 | 19/20
(Correct decisions under the staleness intervention. Each judge fails in a different place: A dismisses genuine new faults when a stale prior is present, B cannot recognise a clean run unless one is.)

Neither judge re-flagged the repaired boundary, which was the predicted failure; that happened once in 160 stale-history calls. Judge A, handed a superseded faulty prior, misses genuine new faults, 18/20 falling to 11/20 (Fisher exact, p=0.03 uncorrected, suggestive after the multiplicity correction of Section~(sec:power)); the prior appears to act as a contrast anchor, and a current run that looks better than the old one reads as fine. Judge B shows the opposite defect: it detects the new fault regardless of history, 19/20 in both cells, but cannot recognise a clean run, inventing a fault in 16 of 20 clean-history cases and naming the final stage in every one, which is the downstream-blame bias with nothing to blame; a superseded faulty prior partially restores its ability to answer clean, 13/20 against 4/20. The deployed system's own record supplies a third signature, a frontier model resurrecting a resolved issue from flat history.

Three judges, three failure shapes from one manipulation. The stable conclusion is a dependence rather than a direction: the content of accumulated history modulates a model judge's trust decisions in model-specific ways that no prompt here controlled, while deterministic signals are unaffected by context by construction. 