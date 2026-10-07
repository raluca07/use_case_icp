Create exactly two simple Python jobs for the supplied frozen preflight scenario. This is an unscored setup authoring call. Do not browse, use HTTP, inspect a repository, or embed information not present in the supplied scenario.

Use pandas DataFrames as the intermediate input and output of every declared boundary, because the pinned Etiq scanner captures those states and function mappings. Convert DataFrames to JSON-compatible records only in the entry function after all declared boundaries have executed. Define and execute at least two non-declared helper functions directly beneath declared parent boundaries. Each helper must accept and return a pandas DataFrame and produce captured intermediate state. A callback used only by pandas `apply`/`map`, a lambda, or an unexecuted lexical helper does not satisfy this requirement.

Both entry files must read one JSON object from stdin and write exactly one JSON object to stdout, with no other stdout. Keep all logic function-based.

The upstream `market-demand-research` job must consume `corpus`, and output:

- `normalized_demand`: records with `need_id`, `job`, `pain`, `desired_outcome`, `source_ids`, and numeric `demand_score`;
- `provenance`: records with `source_id`, `title`, and `license`;
- `metadata`.

It must declare exactly these six executed boundaries: `parse_corpus`, `extract_demand`, `normalize_demand`, `build_provenance`, `validate_research`, and `run_market_demand`. Normalize the strongest intermediate-state demand to `need-intermediate-state` and the cross-job demand to `need-cross-job-provenance`.

The downstream `coverage-prioritization-synthesis` job must consume `normalized_demand`, `provenance`, and `capabilities`, and output:

- `coverage`: records with `need_id`, `status`, and `capability_ids`;
- `priorities`: records with `need_id`, `priority_score`, `status`, and `source_ids`;
- `recommendation` with `decision`, `top_need_id`, and `rationale`;
- `metadata`.

It must declare exactly these six executed boundaries: `map_capabilities`, `classify_coverage`, `join_demand_coverage`, `rank_priorities`, `synthesize_recommendation`, and `run_coverage_synthesis`. `join_demand_coverage` must perform a real join/aggregation. The correct reference must rank `need-intermediate-state` first and return recommendation decision `prioritize`. Coverage output must include supported, partial, and unsupported statuses.

Every declared boundary must execute and must retain enough named intermediate values for Etiq capture. The response schema still asks for helper claims for audit, but the controller will ignore those claims when deciding helper eligibility. Only a captured undeclared direct-child function prefix that a legal adaptive expansion can reveal with added evidence is eligible. Return only the structured response required by the schema.
