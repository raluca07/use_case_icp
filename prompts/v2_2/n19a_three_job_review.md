You are reviewing one deterministic three-job program execution.

Treat the supplied corpus and capability catalogue as stipulated inputs. Begin
with the final campaign brief, reason backward through Job 3 and Job 2 into Job
1, and judge whether the execution satisfies the declared selection,
field-preservation, handoff, ordering, recommendation, and campaign-brief rules.

Return exactly seven reviews: judge every ID in
`common_base.section.assigned_boundary_ids` exactly once and return no other
review units. Handoff IDs are evidence references only and may never be review
units or suspects. Mark at most one boundary `failed` or `suspect`; that first
marked boundary is the earliest root cause. If the full chain satisfies its
contract, mark every boundary trusted.

Return exactly one `next_action` following the package's action contract. Do not
batch speculative actions. After any supplied operation response, reassess all
seven boundaries before choosing the next action.
