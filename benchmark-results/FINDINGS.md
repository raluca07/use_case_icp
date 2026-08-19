# Findings

Every number here traces to a JSON file in this directory. Where a comparison is
paired, the test is exact McNemar; proportions carry Wilson intervals. Nine
significance tests appear across the study and a Holm-Bonferroni correction is applied
to all of them.

## Computing over the graph

**Repair-target selection** (`topology_selection.json`). A selector walking recorded
dataflow to the causal root is exact in all 38 contested cases, across four pipeline
shapes and both declaration orders. A source-order baseline matches it perfectly when
declaration order already encodes execution order and falls to 21 per cent when it does
not. The graph is worth exactly the extent to which the two orders diverge, which a team
cannot know in advance.

**Learned checks** (`scar_vs_contract.json`, `scarring_v2.json`). Over 90 data faults,
hand-written contracts detect 26 and localise none: every detection fires on an
aggregating stage downstream of the cause. Checks learned from caught faults and placed
where they entered detect 60 and localise all 60. The downstream-blame bias is therefore
a property of where checks sit, not of language models, since it reproduces in a signal
containing no model.

Population size does not change detection, identical at 1, 4 and 8 healthy observations;
it buys false suspicion, 21 of 56 boundary-checks at n=1 falling to zero at n=8. A
vocabulary check is minted only where the population shows the domain closed. Enforcing
that costs detection, 73 to 60, and takes false suspicion on held-out healthy runs from
3 of 28 to zero.

**Detection complementarity** (`deterministic.json`, `judge.json`, `judge_branching.json`).
Over 104 silent faults: schema validation misses 78 per cent, declared invariants 27,
a 3B judge 18, the pair 7. Invariants and the judge are not separable (p=0.16); both are
significantly worse than their union (p<0.0001, p=0.0005). The judge's false-suspicion
rate is zero across 102 control calls on boundaries known sound.

## Showing the graph to a model

**Selection as context is worse than random** (`powered_null.json`). 244 paired cases per
arm, powered to detect roughly 12 points. A size-matched random slice scores 160 of 244
against the graph-selected region's 129, 66 per cent against 53, discordant pairs 21
favouring selection and 52 favouring random, exact McNemar p=0.0004. Handing a model a
slice chosen in advance is significantly worse than handing it an arbitrary one of the
same size. This supersedes an earlier underpowered null which could only have detected a
35-point effect.

**But a protocol that withholds and is asked does work** (`collapsed_protocol.json`).
Nodes at exactly the boundary's stack level, nested helpers named but withheld, one
direct child per request for at most three rounds: 9 of 10 at 841 characters, against 9
of 10 at 922 for sending everything and 7 of 10 for a random subset at the same budget.
The only selection arm that separates from random. The benefit is the interaction, not
the slice. Ten cases per arm, so directional rather than sized.

**Scale note.** The comparison above is budget-matched on both arms, so it is
independent of scale. Separately, the real system's full-graph package runs to 382,071
characters against a 1,048,576 character judge limit, so at that size selection becomes
mandatory for capacity. Size forces selection; it does not make selection informative.

## Where every signal fails

**Wrong-sense faults** (`wrong_sense.json`). A pipeline researching software agent
tooling receives sources about insurance agents: same counts, identifiers, dates and
shape, only the meaning wrong. Invariants flag nothing, 60 scars trained on every other
fault class flag nothing, and scar minting is refused because the difference is not
expressible as a structural check. A judge shown only the retrieval stages names the
right one 11 of 13 times but also names a stage on all 6 clean runs, so its precision is
11 of 19 against 1 of 19 for the full graph. No signal detects this class reliably.

**Staleness** (`stale_history.json`, `stale_history_sonnet.json`). Accumulated history
harms a judge in model-specific directions. One judge, given a superseded faulty prior,
misses genuine new faults, 18 of 20 falling to 11 (p=0.03 uncorrected, not surviving
correction). Another cannot recognise a clean run without one, inventing a fault in 16 of
20 clean cases. The real system's record shows a third model resurrecting a resolved
issue. Staleness rather than volume is the active ingredient.

## What we could not have detected

Minimum detectable difference at 80 per cent power: 23 points for history shallow versus
deep and 19 for invariants versus judge, against observed gaps of 12 and 9. Those nulls
are underpowered rather than negative. The selection null is the exception: it is now
powered, and it did not stay null.

## Measurement artifacts caught

Six confident numbers turned out to be artifacts of how the experiment was built: a
static-code arm reading our own source mutations (75 per cent, collapsing to 0 once
faults moved into recorded data); a 3B and a 30B model each returning a fixed answer
regardless of input; a selection result reported as significant on a third of its
eventual sample and retracted; a chance baseline of 42 per cent mistaken for 14 because
data faults concentrate on the stages that fetch; and a dump cap truncating evidence
before the judge saw it. Each would have survived into a table.
