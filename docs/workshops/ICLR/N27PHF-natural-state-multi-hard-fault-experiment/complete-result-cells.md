# Complete 96-cell results

One cell is one frozen instance × evidence arm, aggregating its three repeated reviews. The 288 individual reviews, response fields, tokens, hashes and raw paths are in [all-review-results-corrected.csv](all-review-results-corrected.csv).

`D`, `J`, `E` and `FP` mean detected fault, correct job, exact function and false positive. Job and exact are not applicable to controls. `Natural` counts reviews that selected the prespecified natural state. All Job-3 cells use the deterministic correction documented in [scoring-correction.md](scoring-correction.md).

| Instance | Mechanism | Truth | Arm | D/3 | J/3 | E/3 | FP/3 | Natural/3 | Calls | Tokens |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| case-control-01 | Matched clean control | Control | P01 | 0 | — | — | 0 | 0 | 3 | 86,476 |
| case-control-01 | Matched clean control | Control | P02 | 0 | — | — | 0 | 0 | 3 | 181,671 |
| case-control-01 | Matched clean control | Control | P03 | 0 | — | — | 0 | 0 | 3 | 184,030 |
| case-control-01 | Matched clean control | Control | P04 | 0 | — | — | 0 | 0 | 9 | 576,288 |
| case-control-01 | Matched clean control | Control | P05 | 0 | — | — | 0 | 0 | 9 | 570,131 |
| case-control-01 | Matched clean control | Control | P06 | 0 | — | — | 0 | 0 | 9 | 544,977 |
| case-control-02 | Matched clean control | Control | P01 | 0 | — | — | 0 | 0 | 3 | 85,314 |
| case-control-02 | Matched clean control | Control | P02 | 0 | — | — | 0 | 0 | 3 | 181,535 |
| case-control-02 | Matched clean control | Control | P03 | 0 | — | — | 0 | 0 | 3 | 186,932 |
| case-control-02 | Matched clean control | Control | P04 | 0 | — | — | 0 | 0 | 9 | 567,939 |
| case-control-02 | Matched clean control | Control | P05 | 0 | — | — | 0 | 0 | 9 | 569,625 |
| case-control-02 | Matched clean control | Control | P06 | 0 | — | — | 0 | 0 | 9 | 543,676 |
| case-control-03 | Matched clean control | Control | P01 | 0 | — | — | 0 | 0 | 3 | 86,023 |
| case-control-03 | Matched clean control | Control | P02 | 0 | — | — | 0 | 0 | 3 | 181,916 |
| case-control-03 | Matched clean control | Control | P03 | 0 | — | — | 0 | 0 | 3 | 183,906 |
| case-control-03 | Matched clean control | Control | P04 | 0 | — | — | 0 | 0 | 9 | 556,074 |
| case-control-03 | Matched clean control | Control | P05 | 0 | — | — | 0 | 0 | 9 | 565,256 |
| case-control-03 | Matched clean control | Control | P06 | 0 | — | — | 0 | 0 | 9 | 545,504 |
| case-control-04 | Matched clean control | Control | P01 | 0 | — | — | 0 | 0 | 3 | 88,549 |
| case-control-04 | Matched clean control | Control | P02 | 0 | — | — | 0 | 0 | 3 | 181,462 |
| case-control-04 | Matched clean control | Control | P03 | 0 | — | — | 0 | 0 | 3 | 186,764 |
| case-control-04 | Matched clean control | Control | P04 | 0 | — | — | 0 | 0 | 9 | 593,358 |
| case-control-04 | Matched clean control | Control | P05 | 0 | — | — | 0 | 0 | 9 | 565,772 |
| case-control-04 | Matched clean control | Control | P06 | 0 | — | — | 0 | 0 | 9 | 546,093 |
| case-r01 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P01 | 0 | 0 | 0 | 0 | 0 | 3 | 87,724 |
| case-r01 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P02 | 2 | 2 | 2 | 0 | 0 | 3 | 185,696 |
| case-r01 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P03 | 0 | 0 | 0 | 0 | 0 | 3 | 188,423 |
| case-r01 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P04 | 1 | 1 | 1 | 0 | 0 | 9 | 614,176 |
| case-r01 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P05 | 1 | 1 | 1 | 0 | 0 | 9 | 605,741 |
| case-r01 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P06 | 0 | 0 | 0 | 0 | 0 | 9 | 548,607 |
| case-r02 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P01 | 0 | 0 | 0 | 0 | 0 | 3 | 90,725 |
| case-r02 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P02 | 1 | 1 | 1 | 0 | 0 | 3 | 185,474 |
| case-r02 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P03 | 0 | 0 | 0 | 0 | 0 | 3 | 188,434 |
| case-r02 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P04 | 2 | 2 | 2 | 0 | 0 | 9 | 619,646 |
| case-r02 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P05 | 3 | 3 | 3 | 0 | 0 | 9 | 623,995 |
| case-r02 | Premature contribution rounding | job_upstream_demand_provenance / weight_source_reliability | P06 | 0 | 0 | 0 | 0 | 0 | 9 | 550,759 |
| case-s01 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 85,823 |
| case-s01 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 181,216 |
| case-s01 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 184,513 |
| case-s01 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P04 | 3 | 3 | 3 | 0 | 0 | 9 | 567,041 |
| case-s01 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P05 | 3 | 3 | 3 | 0 | 0 | 9 | 577,140 |
| case-s01 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 545,420 |
| case-s02 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 85,555 |
| case-s02 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 181,303 |
| case-s02 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 184,442 |
| case-s02 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P04 | 3 | 3 | 3 | 0 | 0 | 9 | 566,984 |
| case-s02 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P05 | 3 | 3 | 3 | 0 | 0 | 9 | 577,582 |
| case-s02 | Recorded-time snapshot substitution | job_upstream_demand_provenance / select_snapshot_observations | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 544,138 |
| case-e01 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 85,497 |
| case-e01 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 181,501 |
| case-e01 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 184,567 |
| case-e01 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P04 | 3 | 3 | 3 | 0 | 0 | 9 | 566,774 |
| case-e01 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P05 | 3 | 3 | 3 | 0 | 0 | 9 | 575,834 |
| case-e01 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 546,211 |
| case-e02 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 85,395 |
| case-e02 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 181,215 |
| case-e02 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 184,376 |
| case-e02 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P04 | 3 | 3 | 3 | 0 | 0 | 9 | 567,371 |
| case-e02 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P05 | 3 | 3 | 3 | 0 | 0 | 9 | 576,379 |
| case-e02 | Expiry compared with recorded time | job_upstream_demand_provenance / select_snapshot_observations | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 544,543 |
| case-v01 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 83,957 |
| case-v01 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 179,479 |
| case-v01 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 184,219 |
| case-v01 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P04 | 3 | 3 | 3 | 0 | 3 | 9 | 565,018 |
| case-v01 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P05 | 3 | 3 | 3 | 0 | 2 | 9 | 574,432 |
| case-v01 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P06 | 2 | 2 | 2 | 0 | 0 | 9 | 543,080 |
| case-v02 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 84,254 |
| case-v02 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 182,237 |
| case-v02 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 184,076 |
| case-v02 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P04 | 3 | 3 | 3 | 0 | 2 | 9 | 566,233 |
| case-v02 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P05 | 3 | 3 | 3 | 0 | 2 | 9 | 575,613 |
| case-v02 | Oldest repeated observation retained | job_upstream_demand_provenance / reduce_source_repeats | P06 | 2 | 2 | 2 | 0 | 0 | 9 | 541,775 |
| case-d01 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 82,487 |
| case-d01 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 180,448 |
| case-d01 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 182,005 |
| case-d01 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P04 | 3 | 3 | 3 | 0 | 2 | 9 | 561,785 |
| case-d01 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P05 | 3 | 3 | 3 | 0 | 3 | 9 | 569,980 |
| case-d01 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 539,012 |
| case-d02 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 83,157 |
| case-d02 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 180,292 |
| case-d02 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 181,439 |
| case-d02 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P04 | 3 | 3 | 3 | 0 | 2 | 9 | 560,358 |
| case-d02 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P05 | 3 | 3 | 3 | 0 | 3 | 9 | 569,633 |
| case-d02 | Repeat ranking scoped only by source | job_upstream_demand_provenance / reduce_source_repeats | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 538,996 |
| case-c01 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 84,356 |
| case-c01 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 179,820 |
| case-c01 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 182,571 |
| case-c01 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P04 | 3 | 3 | 3 | 0 | 0 | 9 | 550,739 |
| case-c01 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P05 | 3 | 3 | 3 | 0 | 0 | 9 | 560,841 |
| case-c01 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 540,887 |
| case-c02 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P01 | 3 | 3 | 3 | 0 | 0 | 3 | 84,436 |
| case-c02 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P02 | 3 | 3 | 3 | 0 | 0 | 3 | 179,249 |
| case-c02 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P03 | 3 | 3 | 3 | 0 | 0 | 3 | 182,976 |
| case-c02 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P04 | 3 | 3 | 3 | 0 | 0 | 9 | 550,544 |
| case-c02 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P05 | 3 | 3 | 3 | 0 | 0 | 9 | 560,684 |
| case-c02 | Non-cumulative channel cap (Job 3) | job_campaign_portfolio_generation / allocate_campaign_budget | P06 | 3 | 3 | 3 | 0 | 0 | 9 | 539,431 |
