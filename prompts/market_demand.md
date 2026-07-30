Create a simple Python market-demand discovery pipeline for the active segment.

The pipeline must research the audience's actual world before considering how the supplied product might fit. Look for evidence of the audience's jobs, working context, current workflow, recurring pain or risk, triggering circumstances, existing alternatives or workarounds, consequences, and desired outcomes.

Prefer authentic evidence from relevant community discussions, GitHub issues and discussions, technical forums, user research, reviews, postmortems, benchmarks, evaluations, surveys, interviews, and observed adoption or switching behaviour. Product pages, vendor documentation, and category articles may establish background or alternatives, but they are not by themselves evidence of market demand.

Treat human agent builders and researchers separately from agents. Humans require practitioner, user, or buyer evidence. Agents are not conventional buyers; assess their operational requirements through observed execution failures, benchmarks, evaluations, tool limitations, and agent behaviour.

Do not perform the market research in this Codex authoring session. Do not use Codex browsing or retrieval to collect findings and embed them as constants. The generated pipeline must discover and retrieve sources at runtime under Etiq, follow the supplied `source_policy`, use only public unauthenticated sources unless the policy authorizes otherwise, and report source failures visibly.

Keep observed evidence separate from interpretation. Do not invent personas, needs, recurrence, urgency, or willingness to pay. If strong evidence is absent, record that gap instead of producing generic industry claims.

Process each retrieved source once into compact evidence records. Avoid repeatedly scanning whole documents for every proposed need. Functions should represent meaningful, reviewable research stages rather than sentence-level mechanics.

Any top-level `needs`, `workflows`, `demand_signals`, `assumptions`, and `gaps` in the authoring response are provisional design context only. The pipeline's runtime result is the evidence-bearing market-demand result.

At runtime, write exactly one JSON object to stdout and no other stdout text. It must contain `needs`, `workflows`, `demand_signals`, `assumptions`, and `gaps`. Send operational diagnostics to stderr and follow the response schema exactly.
