# Attempt 032 — downstream-first Adaptive versus no graph

Generated from the immutable Attempt-032 freeze, all 60 raw review records, operation ledgers, replay reconciliation, and completed terminal.

## Status and scope

| Item | Result |
|---|---|
| Terminal | `completed_experiment_and_analysis` |
| Packages | 20 |
| Reviews | 60/60 |
| Repairs | 0, by design |
| Provider calls | 73 |
| Instances | One upstream `select_demand` fault and one matched clean control |
| Primary population | Source absent |

Every arm started at the same downstream result, received both jobs' actual execution records and two exact-hash handoffs, and assessed the same six downstream-first boundaries. Only graph framing, compact graph evidence, and Adaptive operations varied.

## Source-absent primary results

| Mode | Fault detected | Correct upstream job | Exact `select_demand` | Control FP | Expansions | Calls | Input | Cached | Output |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Current / no graph | 3/3 | 3/3 | 0/3 | 0/3 | 0 | 6 | 136955 | 69888 | 10233 |
| Etiq Empty | 3/3 | 3/3 | 1/3 | 0/3 | 0 | 6 | 137645 | 69888 | 9629 |
| Compact Fixed | 3/3 | 3/3 | 0/3 | 0/3 | 0 | 6 | 148042 | 69888 | 9848 |
| Adaptive Voluntary | 3/3 | 3/3 | 1/3 | 0/3 | 1 | 7 | 182547 | 71296 | 11753 |
| Adaptive Required-One | 3/3 | 3/3 | 3/3 | 0/3 | 6 | 12 | 356085 | 119296 | 21208 |

## Source-present interaction

| Mode | Fault detected | Correct upstream job | Exact `select_demand` | Control FP | Expansions | Calls | Input | Cached | Output |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Current / no graph | 3/3 | 3/3 | 3/3 | 0/3 | 0 | 6 | 149033 | 69888 | 10157 |
| Etiq Empty | 3/3 | 3/3 | 3/3 | 0/3 | 0 | 6 | 149728 | 69888 | 9672 |
| Compact Fixed | 3/3 | 3/3 | 3/3 | 0/3 | 0 | 6 | 160124 | 69888 | 9944 |
| Adaptive Voluntary | 3/3 | 3/3 | 3/3 | 0/3 | 0 | 6 | 160176 | 69888 | 9942 |
| Adaptive Required-One | 3/3 | 3/3 | 3/3 | 0/3 | 6 | 12 | 380251 | 129536 | 20931 |

## Prespecified contrasts

Differences below are right minus left and are descriptive, not population estimates.

| Source | Contrast | Detection | Correct job | Exact boundary | Control FP |
|---|---|---:|---:|---:|---:|
| source_absent | current_vs_etiq_empty | 0.000 | 0.000 | 0.333 | 0.000 |
| source_absent | etiq_empty_vs_compact_fixed | 0.000 | 0.000 | -0.333 | 0.000 |
| source_absent | current_vs_adaptive_voluntary | 0.000 | 0.000 | 0.333 | 0.000 |
| source_absent | current_vs_adaptive_required_one | 0.000 | 0.000 | 1.000 | 0.000 |
| source_absent | compact_fixed_vs_adaptive_voluntary | 0.000 | 0.000 | 0.333 | 0.000 |
| source_absent | compact_fixed_vs_adaptive_required_one | 0.000 | 0.000 | 1.000 | 0.000 |
| source_present | current_vs_etiq_empty | 0.000 | 0.000 | 0.000 | 0.000 |
| source_present | etiq_empty_vs_compact_fixed | 0.000 | 0.000 | 0.000 | 0.000 |
| source_present | current_vs_adaptive_voluntary | 0.000 | 0.000 | 0.000 | 0.000 |
| source_present | current_vs_adaptive_required_one | 0.000 | 0.000 | 0.000 | 0.000 |
| source_present | compact_fixed_vs_adaptive_voluntary | 0.000 | 0.000 | 0.000 | 0.000 |
| source_present | compact_fixed_vs_adaptive_required_one | 0.000 | 0.000 | 0.000 | 0.000 |

## Adaptive operations

Voluntary uptake: 1/12. Required-One completion: 12/12.

| Trial | Pre-expansion suspect | Final suspect | Expanded child groups |
|---|---|---|---|
| trial-10b9f7fdeea7da4c | bnd-8e4e0db29e4a3223 | bnd-8e4e0db29e4a3223 | grp-5b4092c8e1b4e04f |
| trial-e8df7df813e2efc4 | none | none | grp-90fcd5760e439ad2 |
| trial-0a4dd0e517cabba6 | none | none | grp-90fcd5760e439ad2 |
| trial-95ca6a44fb23f3f0 | bnd-8e4e0db29e4a3223 | bnd-8e4e0db29e4a3223 | grp-5b4092c8e1b4e04f |
| trial-cc924c9ac9f272da | none | none | grp-90fcd5760e439ad2 |
| trial-5760506436130026 | bnd-c4af215f98a887d0 | bnd-8e4e0db29e4a3223 | grp-5b4092c8e1b4e04f |
| trial-54a7526fb063d156 | bnd-8e4e0db29e4a3223 | bnd-8e4e0db29e4a3223 | grp-5b4092c8e1b4e04f |
| trial-14e57340096b3729 | none | none | grp-90fcd5760e439ad2 |
| trial-d6c4752fb7144578 | bnd-8e4e0db29e4a3223 | bnd-8e4e0db29e4a3223 | grp-5b4092c8e1b4e04f |
| trial-c099e528a9de2fb5 | none | none | grp-90fcd5760e439ad2 |
| trial-5221bd1288e15761 | none | none | grp-90fcd5760e439ad2 |
| trial-9af4b3b5ede5192b | bnd-8e4e0db29e4a3223 | bnd-8e4e0db29e4a3223 | grp-5b4092c8e1b4e04f |
| trial-1783eba07d299c69 | bnd-c4af215f98a887d0 | bnd-8e4e0db29e4a3223 | grp-5b4092c8e1b4e04f |

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

## Integrity and limitations

- All package, review, operation and call-attempt hashes were replayed; Required-One completion was checked from operation records.
- Attempt 031 remained unchanged and no Attempt-031 request or response was reused.
- Cached input is included within input and must not be added to it.
- This is one frozen upstream fault pipeline and one matched control. It answers the question for this fault but does not establish performance across upstream fault classes.
- Repetitions are fresh reviewer calls over the same two pipelines, not independent pipeline instances.

## Bound artifacts

- `outputs/fault-experiments-v2-2-n10/attempt-032/experiment-freeze.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/live-consumption.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/analysis/summary.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/replay/reconciliation.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/terminal-state.json`
- `outputs/fault-experiments-v2-2-n10/attempt-032/qualification/developer-n18-results-handoff.json`
