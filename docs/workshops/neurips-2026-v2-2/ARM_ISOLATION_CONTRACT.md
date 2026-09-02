# Protocol 2.1.0 production isolation contract

Protocol ID: `neurips-2026-workshop-fault-localisation-v2`  
Protocol version: `2.1.0`  
Status: `pre_results_frozen`

The production boundary is the function-based Bubblewrap launcher in
`src/use_case_icp/n05_runner.py`. Opaque names, current working directories,
ordinary permissions, and package filtering are not treated as security
boundaries. Missing or misconfigured Bubblewrap fails closed; there is no
unrestricted fallback.

Each branch receives copied, hash-verified regular evidence files with distinct
inodes, plus its own workspace, home, temporary directory, output, JobStore,
frozen dependencies, and minimal read-only runtime. The repository, common
capture, controller truth, condition map, aggregate ledger, old experiment
roots, host Codex home, and sibling branches are not mounted.

The real Codex CLI is placed inside a filesystem/process-isolated Bubblewrap
view, but its network namespace remains shared so provider transport can work.
The exact Codex permission profile denies network to every command launched by
the model. Only individually allowlisted authentication files are copied into
the private ephemeral Codex home; the host Codex home is never mounted.

Authored and repaired Python run through Bubblewrap with the network namespace
unshared. Their visible filesystem contains only the current branch source,
inputs, frozen dependencies, private output/temp, and minimal runtime. File
descriptors are closed, the environment is minimized, and aggregation happens
only after immutable branch output freezes.

Independent Gate 1 must use the exact production launch functions and known
absolute host paths. It must prove provider transport succeeds while a command
launched by Codex cannot access the network, and prove authored and repaired
Python cannot access the network. Repository, truth, common capture, aggregate
ledger, sibling, and host-home read/write/list/import attempts must fail. Any
skipped, unavailable, stale, mock, tampered, disabled, or misconfigured probe
blocks all scientific model calls.
