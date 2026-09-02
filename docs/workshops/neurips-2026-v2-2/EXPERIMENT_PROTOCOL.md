# Protocol 2.2.0 — canonical endpoint-complete fault localisation

Protocol ID: `neurips-2026-workshop-fault-localisation-v2`  
Version: `2.2.0`  
Status: `pre_results_frozen`

Protocol 2.2.0 includes the N12 pre-results amendment issued after excluded engineering attempts 001–010 and before any experimental reviewer call, repair, or outcome. N12 resumes after the accepted Phase-A checkpoint `sha256:f4c04cdbb841a4749053a0d38cae2dba84fda17ee7102e5d96b8ec89d0b0cf10` with exact 11-file tree `sha256:20a44c62c120afed1f9dba82cdd87817fc0cc38b1c979023b0a36e5ea7a2b736`, removes the model-dependent Phase-B rehearsal, places deterministic readiness checks at the construction, capture, package, and ordinary test boundaries, and leaves the 12-instance evidence-condition experiment and frozen analysis unchanged.

The JSON block below is byte-identical to `experiment-protocol.json`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "protocol_id": "neurips-2026-workshop-fault-localisation-v2",
  "protocol_version": "2.2.0",
  "status": "pre_results_frozen",
  "integrity": {
    "algorithm": "sha256",
    "canonicalization": "UTF-8 JSON with lexicographically sorted object keys and compact separators",
    "scope": "complete JSON except integrity.content_hash, each normative_artifacts item sha256, and namespace_registry contract_arm_isolation/contract_launch_policy sha256; these detached exact-byte hashes are omitted only to break protocol-identity embedding cycles and remain exact-file bindings in the final JSON",
    "content_hash": "sha256:bcfcd1afc192a37b2619934ac62a85c17ee80b2dfd45157d92185be03c4145c1"
  },
  "authority": {
    "human_readable_specification": "docs/workshops/neurips-2026-v2-2/EXPERIMENT_PROTOCOL.md",
    "machine_readable_configuration": "docs/workshops/neurips-2026-v2-2/experiment-protocol.json",
    "controlling_plan": "instructions_between_agent_types/00_overall_plan.md",
    "design_decisions": [
      {
        "path": "instructions_between_agent_types/overseer/decisions/N01_v2_study_design_authorization.json",
        "sha256": "sha256:c90c5c41c0f076b5730819a055e7daca62dcf96d6ac43a5762827de705b38186"
      },
      {
        "path": "instructions_between_agent_types/overseer/decisions/N01A_v2_design_remediation_authorization.json",
        "sha256": "sha256:4c35eeeed87c6549cdc6d0b1989a8c0b91a051d1e8573c805dd046176efd9479"
      },
      {
        "path": "instructions_between_agent_types/overseer/decisions/N01B_v2_execution_readiness_remediation_authorization.json",
        "sha256": "sha256:727b8612a906a59788fce0450b7294a1e610c02d05eab4df8f8cffe1a3b08ae4"
      },
      {
        "path": "instructions_between_agent_types/overseer/decisions/N02_v2_fault_blind_phase_a_execution_authorization.json",
        "sha256": "sha256:764259090149000ca8f7689fd4d792e8b5f834dfde56dfc2d4b4cfd044dd38b5"
      },
      {
        "path": "instructions_between_agent_types/overseer/decisions/N02A_v2_phase_a_transport_remediation_authorization.json",
        "sha256": "sha256:bf1f0fa875e226101c88134a34f9910c20b3256864a86513b18344518f809abd"
      },
      {
        "path": "instructions_between_agent_types/overseer/decisions/N05_v2_1_end_to_end_completion_program_authorization.json",
        "sha256": "sha256:2928e57ecd8423365a53758424282b07928727bade71f8ff4fb1ce205df43a95"
      },
      {
        "path": "instructions_between_agent_types/overseer/decisions/N06_v2_2_projection_correction_and_experiment_completion_authorization.json",
        "sha256": "sha256:71e769ea20900179cebbb1dd4909d6e1d6e0512cb86d7f424609baa413c2b6a2"
      },
      {
        "path": "instructions_between_agent_types/overseer/decisions/N12_v2_2_phase_b_removal_and_experiment_execution_authorization.json",
        "sha256": "sha256:9549b6ff9d38ab138270b9a420277c9b7857d6f7efbae1bd1b8f6d1c0c3f40f0"
      }
    ],
    "execution_authority": "N12 starts from verified accepted Phase-A artifact sha256:f4c04cdbb841a4749053a0d38cae2dba84fda17ee7102e5d96b8ec89d0b0cf10, removes live Phase B, permits the governed implementation corrections, and authorizes continuous execution after 12 instances, 12 canonical captures, 96 verified packages, and production isolation pass; no further Overseer approval is required",
    "later_manifest_fields": [
      "protocol_id",
      "protocol_version",
      "protocol_content_hash"
    ]
  },
  "scope": {
    "research_question": "How do graph-linked intermediate runtime states, structural evidence selection, adaptive graph operations, and separate source-bundle availability affect coding-agent fault detection, localisation, repair success, and token use?",
    "unit_of_independence": "fresh independently authored two-job chain created against the common frozen experimental task",
    "pilot_preservation": {
      "unchanged_files": [
        "src/use_case_icp/review_experiment.py",
        "src/use_case_icp/controlled_experiment.py"
      ],
      "unchanged_commands": [
        "compare-review",
        "compare-control"
      ],
      "unchanged_legacy_arm_names_and_behaviour": true,
      "preserved_artifact": "docs/experiments/2026-07-30-controlled-job-32968d910a7847a7/"
    },
    "new_command_namespace": "fault-experiment-v2-2",
    "new_output_namespace": "outputs/fault-experiments-v2-2/",
    "stored_pipeline_policy": "Every 2.2 reference is freshly authored from frozen 2.2 inputs. N02-N05 and protocol-1.3.1/2.1.0 responses, sources, diagnostics, captures, candidates, histories, and outputs are excluded engineering evidence and are never model context or experimental input.",
    "permitted_claims": [
      "measured detection and localisation differences",
      "oracle-validated repair differences",
      "selected versus equal-budget random graph evidence differences",
      "adaptive versus fixed selection differences",
      "measured token-use differences",
      "separate source-bundle present versus withheld differences"
    ],
    "prohibited_claims": [
      "improved end-to-end long-horizon-agent performance",
      "universal cost reduction",
      "an optimal selector",
      "generalisation beyond the frozen generated instances",
      "model trust judgments are ground truth",
      "Etiq invents semantic task boundaries",
      "more graph context must help"
    ]
  },
  "lifecycle": {
    "ordered_phases": [
      "verify_existing_deterministic_phase_a_artifact",
      "tester_t02_production_path_gate",
      "frozen_experimental_task",
      "fresh_two_job_reference_authoring",
      "bounded_reference_stabilization",
      "oracle_passing_reference_acceptance",
      "automatic_single_fault_injection_or_blinded_no_injection_control",
      "complete_two_job_mutant_execution",
      "one_canonical_evaluation_execution",
      "immutable_common_capture",
      "isolated_opaque_arm_fan_out",
      "post_freeze_aggregation"
    ],
    "preflight": {
      "scored": false,
      "instance_member": false,
      "phase_a": "reuse the already accepted controller-owned deterministic two-job artifact by exact hash; do not rerun, regenerate, stabilize, mutate, replace, or append to it; it remains a controller-only execution/capture/mutation smoke test with zero authoring, stabilization, reviewer, repair, re-review, or experimental calls",
      "phase_a_fixture_path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight-base-v1/fixture.json",
      "phase_a_accepted_artifact_root": "outputs/fault-experiments-v2-2-phase-a-001/phase-a/",
      "phase_a_accepted_summary_path": "outputs/fault-experiments-v2-2-phase-a-001/phase-a/fixture.json",
      "phase_a_accepted_sha256": "sha256:f4c04cdbb841a4749053a0d38cae2dba84fda17ee7102e5d96b8ec89d0b0cf10",
      "phase_a_summary_file_sha256": "sha256:bad8742936c1c102e29c9470beb125374b095bec2c95329de98cc7615933fbdb",
      "phase_a_tree_sha256": "sha256:20a44c62c120afed1f9dba82cdd87817fc0cc38b1c979023b0a36e5ea7a2b736",
      "phase_a_tree_hash_rule": "SHA-256 of canonical JSON for the lexicographically path-sorted list of all 11 regular files under the artifact root, with relative path, byte size, and exact-byte sha256 per item.",
      "phase_a_binding_rule": "Recompute the canonical Phase-A hash after removing phase_a_sha256 from fixture.json; recompute the exact 11-file tree hash; verify stored source hashes and self-hashes for boundaries.json, both capture manifests, and mutation.json; bind the Phase-A and tree hashes into readiness, attempt, experiment freeze, replay, and terminal records. The artifact is never model-visible and is not an experimental instance.",
      "phase_a_artifact_limit": "The accepted directory has capture manifests with snapshot hashes/counts but lacks full Etiq snapshot nodes/relationships and runtime logs. It is an accepted resume checkpoint, not a package or repair-test fixture. Separate deterministic repository fixtures exercise mechanics; fresh experimental executions supply every canonical experimental capture.",
      "phase_a_model_calls": 0,
      "phase_a_review_calls": 0,
      "phase_a_repair_calls": 0,
      "phase_a_artifact_visibility": "controller-only; contributes no experimental result or treatment token",
      "phase_a_mutation_target": {
        "job_id": "preflight-downstream",
        "source_path": "downstream.py",
        "qualified_function_name": "prioritize_needs",
        "operator": "reverse_ordering"
      },
      "phase_b_status": "removed by N12; no live pre-experiment reviewer, repair, rerun-review, package, report, or checkpoint stage",
      "history_visibility": "never visible to experimental reviewers",
      "reviewer_calls_before_phase_a_pass": 0,
      "scenario_id": "n06-unscored-preflight-runtime-recovery",
      "scenario_path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/scenario.json",
      "corpus_path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/corpus.json",
      "capability_catalogue_path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/capabilities.json",
      "oracle_path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/oracles.json",
      "restricted_controller_plan_path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/restricted/controller-plan.json",
      "execution_authorization_required": "exact N06 Gate-0 design freeze and signed independent N06 Gate-1 artifact",
      "strict_provider_schema_gate": "before output-root creation or authority consumption, recursively require every object in the authoring, stabilization, review-receipt, and repair-response schemas to set additionalProperties false and require exactly its declared properties",
      "phase_a_failure_policy": "execution failures are pipeline failures; boundary matching or projection failures are controller errors; neither invokes stabilization"
    },
    "authoring_session": "fresh, ephemeral, non-resumed Codex session",
    "reference_acceptance_claim": "oracle-passing reference chain, not defect-free or clean chain",
    "stabilization_cycles_per_candidate": 1,
    "authoring_candidates_per_slot": 2,
    "evaluation_execution_count_per_instance": 1,
    "reuse_capture_across_trials": true,
    "allow_live_http": false,
    "allow_results_dependent_design_change": false
  },
  "instance_design": {
    "total_instances": 12,
    "no_injection_controls": 2,
    "single_fault_instances": 10,
    "ablation_subset_size": 6,
    "experimental_fixture_root": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/experiment-v1",
    "experimental_fixture_separation": "The experimental task, corpus, capabilities, and oracles are frozen separately from Phase A. The common task may be reused across slots; authored source and execution may not be reused.",
    "authoring_visibility": "Only the frozen experimental task/corpus/capabilities, exact two-job I/O contracts, authoring seed, and opaque instance ID are model-visible. Designation, injection operator, target job/stage, injection seed, nested-helper diagnostic, ablation membership, repair membership, and all controller truth are forbidden.",
    "ablation_no_injection_controls": 1,
    "ablation_faulty_instances": 5,
    "repair_subset_size": 5,
    "instance_slots": [
      {
        "instance_id": "instance-01",
        "designation": "no_injection_control",
        "semantic_fault_class": null,
        "injection_operator": null,
        "target_job": null,
        "stage": null,
        "ablation": true,
        "repair": false,
        "authoring_seed": 1101,
        "injection_seed": null
      },
      {
        "instance_id": "instance-02",
        "designation": "faulty",
        "semantic_fault_class": "query_filtering",
        "injection_operator": "invert_comparison",
        "target_job": "upstream",
        "stage": "early",
        "ablation": true,
        "repair": true,
        "authoring_seed": 1102,
        "injection_seed": 2102
      },
      {
        "instance_id": "instance-03",
        "designation": "faulty",
        "semantic_fault_class": "query_filtering",
        "injection_operator": "invert_comparison",
        "target_job": "downstream",
        "stage": "middle",
        "ablation": false,
        "repair": false,
        "authoring_seed": 1103,
        "injection_seed": 2103
      },
      {
        "instance_id": "instance-04",
        "designation": "faulty",
        "semantic_fault_class": "retrieval_omission_truncation",
        "injection_operator": "truncate_sequence",
        "target_job": "upstream",
        "stage": "middle",
        "ablation": true,
        "repair": true,
        "authoring_seed": 1104,
        "injection_seed": 2104
      },
      {
        "instance_id": "instance-05",
        "designation": "faulty",
        "semantic_fault_class": "retrieval_omission_truncation",
        "injection_operator": "truncate_sequence",
        "target_job": "downstream",
        "stage": "late",
        "ablation": false,
        "repair": false,
        "authoring_seed": 1105,
        "injection_seed": 2105
      },
      {
        "instance_id": "instance-06",
        "designation": "faulty",
        "semantic_fault_class": "extraction",
        "injection_operator": "drop_field",
        "target_job": "upstream",
        "stage": "early",
        "ablation": true,
        "repair": true,
        "authoring_seed": 1106,
        "injection_seed": 2106
      },
      {
        "instance_id": "instance-07",
        "designation": "faulty",
        "semantic_fault_class": "extraction",
        "injection_operator": "drop_field",
        "target_job": "downstream",
        "stage": "late",
        "ablation": false,
        "repair": false,
        "authoring_seed": 1107,
        "injection_seed": 2107
      },
      {
        "instance_id": "instance-08",
        "designation": "faulty",
        "semantic_fault_class": "transformation_identifier_corruption",
        "injection_operator": "fabricate_identifier",
        "target_job": "upstream",
        "stage": "middle",
        "ablation": true,
        "repair": true,
        "authoring_seed": 1108,
        "injection_seed": 2108
      },
      {
        "instance_id": "instance-09",
        "designation": "faulty",
        "semantic_fault_class": "transformation_identifier_corruption",
        "injection_operator": "fabricate_identifier",
        "target_job": "downstream",
        "stage": "early",
        "ablation": false,
        "repair": false,
        "authoring_seed": 1109,
        "injection_seed": 2109
      },
      {
        "instance_id": "instance-10",
        "designation": "faulty",
        "semantic_fault_class": "aggregation_ranking_synthesis",
        "injection_operator": "reverse_ordering",
        "target_job": "upstream",
        "stage": "late",
        "ablation": true,
        "repair": true,
        "authoring_seed": 1110,
        "injection_seed": 2110
      },
      {
        "instance_id": "instance-11",
        "designation": "faulty",
        "semantic_fault_class": "aggregation_ranking_synthesis",
        "injection_operator": "reverse_ordering",
        "target_job": "downstream",
        "stage": "middle",
        "ablation": false,
        "repair": false,
        "authoring_seed": 1111,
        "injection_seed": 2111
      },
      {
        "instance_id": "instance-12",
        "designation": "no_injection_control",
        "semantic_fault_class": null,
        "injection_operator": null,
        "target_job": null,
        "stage": null,
        "ablation": false,
        "repair": false,
        "authoring_seed": 1112,
        "injection_seed": null
      }
    ],
    "required_jobs": [
      "market_demand_research",
      "coverage_prioritization_and_synthesis"
    ],
    "executed_jobs_exactly": 2,
    "downstream_required_boundaries": [
      "coverage",
      "synthesis"
    ],
    "review_boundary_requirement": "only the realized boundaries required to construct the assigned review packages",
    "minimum_exact_hash_handoffs": 2,
    "expandable_helper_eligibility": "A helper may be offered only when it is a captured, undeclared, direct-child function prefix exposed by the fixed structural projection and one legal adaptive expansion adds captured evidence. There is no per-chain helper quota; no legal expansion is recorded as such.",
    "dependency_shape_requirement": "exactly two dependent jobs joined by the two exact-hash handoffs; no additional aggregation-shape quota",
    "oracle_requirements": [
      "output schema for every job",
      "stage-level semantic oracle for every job",
      "end-to-end semantic oracle"
    ],
    "graph_size_gate": "Using one canonical endpoint-complete production projection per job, initial selected fixed/adaptive graph evidence must be byte-identical, selected references must be subsets of full, and every complete reviewer package must fit the 360000-byte hard budget without arbitrary truncation. No selected/full ratio, per-boundary ratio, or helper-count quota applies.",
    "authoring_candidate_limit_per_slot": 2,
    "stabilization_cycle_limit_per_candidate": 1,
    "reference_acceptance": "Both offline real-Etiq jobs and all schemas and behavioural oracles pass; the exact handoffs pass; and the review boundaries required for assigned package construction resolve uniquely to observed execution. Valid unmatched declarations are controller-only audit records. Declaration-count, semantic-stage-count, helper-count, aggregation-shape, and selected/full-ratio quotas do not apply.",
    "validation_stabilization_context": "Only an attributable compile, runtime, schema, or clean-oracle failure may be returned once to the failing-job source-correction session, with that job's source, expected interface, failed check names, and compact fault-blind diagnostics. Controller, capture, identity, projection, package, and mutation-search failures stop as engineering failures and are never model correction prompts. Provide no hidden oracle, future designation, mutation target, graph, captured values, sibling state, excluded evidence, or controller truth.",
    "authoring_failure_policy": "Count a candidate only after a successful structured authoring response yields source. Deterministic request-contract and controller failures stop without model correction. Retryable provider infrastructure failures use the frozen infrastructure retry policy. After source exists, allow one attributable source correction and then advance under the frozen two-candidate limit. If no candidate is accepted, stop incomplete; do not replace it after results or reduce denominators.",
    "fault_injection": {
      "mutations_per_faulty_instance": 1,
      "source_basis": "instructions_between_agent_types/references/fault_injection_supplied.py",
      "primary_ground_truth": "injected_function",
      "requirements": [
        "mutate exactly one selected AST occurrence",
        "record exact original and mutated spans",
        "normalize reference and mutant formatting",
        "compile and execute successfully",
        "preserve output schemas",
        "execute the mutated statement",
        "produce a plausible final result",
        "fail a semantic oracle passed by the hidden oracle-passing reference chain",
        "freeze an oracle-blind deterministic eligible-site order before mutation attempts",
        "execute both jobs for every attempted mutant",
        "advance after no-op, crash, schema failure, uncaptured mutation, or oracle ineffectiveness without reviewer information"
      ],
      "reject_mutants": [
        "equivalent",
        "crashing",
        "uncaptured",
        "schema_invalid",
        "trivially_disclosed"
      ],
      "reviewer_hidden_artifacts": [
        "preflight records",
        "reference authoring and stabilization records",
        "reference source and execution",
        "injection implementation and manifest",
        "mutant rejection log",
        "oracle results",
        "fault label and target"
      ]
    },
    "minimum_declarations_per_job": 8,
    "minimum_realized_static_boundaries": 12,
    "mandatory_realized_semantic_stages": [
      "upstream_demand_selection",
      "upstream_evidence_normalization",
      "upstream_provenance_assembly",
      "downstream_coverage_mapping",
      "downstream_prioritization",
      "downstream_synthesis"
    ]
  },
  "execution_graph_contract": {
    "within_job_graph": "For job j, Etiq captures G_j=(V_j,E_j). Only captured nodes and captured relationships are graph evidence.",
    "chain_graph": "C=(disjoint union of G_j) union A",
    "handoff_relation": "A contains a controller-recorded artifact handoff only when the SHA-256 hash of an upstream output artifact exactly equals the hash of the downstream input artifact.",
    "handoff_is_etiq_edge": false,
    "semantic_inference_allowed": false,
    "declaration": "D_f=(boundary_id,job_id,normalized_source_path,lexical_qualified_function_name,normalized_function_source_sha256,semantic_stage,role,expected_inputs,expected_outputs)",
    "matched_prefix": "Each captured runtime prefix is independently enriched only when captured function-definition evidence resolves to exactly one executed-job static identity; the realized set is the exact intersection of those identities and valid declarations.",
    "realized_boundary": {
      "formula": "B_f=(V_f,E_f,I_f,O_f,H_f,P_f)",
      "P_f": "all contributing captured prefixes resolving to the same exact job/path/qualified-definition/function-source-hash identity",
      "V_f": "stable union of captured state and function nodes whose canonical stacks begin with any prefix in P_f, deduplicated by node_ref",
      "E_f": "stable union of captured relationships internal or incident to V_f, deduplicated by relationship_ref",
      "I_f": "captured relationships entering V_f from outside",
      "O_f": "captured relationships leaving V_f",
      "H_f": "observed descendant helper-stack prefixes beneath a member of P_f"
    },
    "unmatched_declaration_policy": "A valid exact static declaration without a captured identity match is recorded controller-side as unmatched_declaration and is excluded from reviewer packages and realized counts. It does not alone invalidate the chain. Invalid, ambiguous, conflicting, forged, partial, wrong-job, wrong-source, duplicate-identity, duplicate-reference, or missing-endpoint evidence fails closed.",
    "boundary_health_visibility": "internal capture-quality diagnostic only; never reviewer evidence",
    "non_etiq_boundary_visibility": "The controller may match the same function internally, but the reviewer receives only D_f, task evidence, and the separate source bundle when supplied; it receives no B_f, captured values, crossing edges, helper stacks, or runtime relationships.",
    "structural_projection": {
      "inside": "inside(v,P_f) iff v canonical stack begins with at least one prefix in P_f",
      "direct": "direct(v,P_f) iff v canonical stack equals a prefix in P_f",
      "descendant": "descendant(v,P_f) iff inside(v,P_f) and its stack is deeper than its contributing prefix",
      "V0": "{v | direct(v,P_f)} union endpoints(I_f union O_f)",
      "E0": "I_f union O_f union {e in E_f | both endpoints of e are in V0}",
      "includes": [
        "bounded values or previews for visible state nodes",
        "direct descendant helpers as collapsed choices",
        "incident typed exact-hash handoffs"
      ],
      "selector_kind": "deterministic rule-based structural selector, not top-k truncation"
    },
    "random_mandatory_interface": "M_f contains I_f, O_f, their endpoints, the matched function node, and incident mandatory handoffs"
  },
  "conditions": {
    "evidence_modes": {
      "current_run": {
        "visible_treatment_evidence": "shared base package only",
        "history": false,
        "graph": false,
        "artifact_inspection": false,
        "helper_expansion": false,
        "graph_retrace_after_scoring": false
      },
      "history_full": {
        "visible_treatment_evidence": "allowed textual ancestry of the canonical executed no-injection or mutant chain plus shared base",
        "history": true,
        "graph": false,
        "artifact_inspection": false,
        "helper_expansion": false,
        "graph_retrace_after_scoring": false
      },
      "etiq_full": {
        "visible_treatment_evidence": "complete captured graph for assigned realized boundaries plus typed handoffs",
        "history": false,
        "graph": true,
        "artifact_inspection": true,
        "helper_expansion": false,
        "graph_retrace_after_scoring": true
      },
      "etiq_selected_fixed": {
        "visible_treatment_evidence": "initial structural projection plus typed handoffs",
        "history": false,
        "graph": true,
        "artifact_inspection": true,
        "helper_expansion": false,
        "graph_retrace_after_scoring": true
      },
      "etiq_selected_adaptive": {
        "visible_treatment_evidence": "byte-identical fixed initial structural projection plus legal requested direct-child expansions and typed handoffs",
        "history": false,
        "graph": true,
        "artifact_inspection": true,
        "helper_expansion": true,
        "graph_retrace_after_scoring": true
      },
      "etiq_random_matched": {
        "visible_treatment_evidence": "M_f plus frozen equal-budget random residual from the same B_f and typed handoffs",
        "history": false,
        "graph": true,
        "artifact_inspection": true,
        "helper_expansion": false,
        "graph_retrace_after_scoring": true
      }
    },
    "source_settings": {
      "source_present": "The same complete generated chain source is supplied as a separate source bundle during review in every evidence mode.",
      "source_absent": "No separate complete source bundle is supplied. Source files and source-bearing diffs are removed from history, and historical prompts that embed source are withheld. Otherwise-visible Etiq nodes are serialized identically across source settings, including node source fields, source-bearing previews, and source-bearing artifacts or values. This legacy key means source bundle withheld, not source-free. At repair time only the independently selected function source is separately revealed."
    },
    "primary_configurations": [
      {
        "evidence_mode": "current_run",
        "source_setting": "source_present"
      },
      {
        "evidence_mode": "history_full",
        "source_setting": "source_present"
      },
      {
        "evidence_mode": "etiq_full",
        "source_setting": "source_present"
      },
      {
        "evidence_mode": "etiq_selected_adaptive",
        "source_setting": "source_present"
      }
    ],
    "primary_instance_count": 12,
    "ablation_subset_instance_ids": [
      "instance-01",
      "instance-02",
      "instance-04",
      "instance-06",
      "instance-08",
      "instance-10"
    ],
    "ablation_matrix": {
      "evidence_modes": [
        "current_run",
        "history_full",
        "etiq_full",
        "etiq_selected_fixed",
        "etiq_selected_adaptive",
        "etiq_random_matched"
      ],
      "source_settings": [
        "source_present",
        "source_absent"
      ],
      "total_configurations_per_subset_instance": 12,
      "already_supplied_by_primary": 4,
      "additional_configurations_per_subset_instance": 8
    },
    "repair_subset_instance_ids": [
      "instance-02",
      "instance-04",
      "instance-06",
      "instance-08",
      "instance-10"
    ],
    "condition_blinding": {
      "reviewer_visible_ids": "opaque random identifiers",
      "restricted_mapping": true,
      "forbidden_reviewer_terms": [
        "current_run",
        "history_full",
        "etiq_full",
        "selected",
        "adaptive",
        "fixed",
        "random",
        "source_present",
        "source_absent",
        "complete arm matrix"
      ],
      "reviewer_capability_description": "neutral operation capability flags only"
    }
  },
  "review_packages": {
    "shared_base": [
      "review task and behavioural criteria",
      "exact top-level chain input and final output",
      "assigned job input, output, stdout, and stderr",
      "opaque instance, branch, condition, section, and boundary IDs",
      "author-declared function name, role, expected inputs, and expected outputs",
      "same assigned executed boundaries and section organization",
      "separate complete generated-chain source bundle only under source_present; node-embedded source follows graph visibility in both settings"
    ],
    "never_reviewer_visible": [
      "boundary_health",
      "fault identity or injection manifest",
      "oracle results",
      "sibling condition review, repair, paths, IDs, prompts, responses, or usage",
      "semantic condition labels or full matrix",
      "prior trust judgments that reveal the fault",
      "reference-validation artifacts or reference outputs",
      "injection code",
      "authoring deliberation",
      "preflight, authoring, stabilization-repair, rejected-candidate, reference-execution, reference-oracle, or complexity-gate records",
      "setup calls or token totals"
    ],
    "history_policy": "History starts only from permitted records of the canonical executed no-injection or mutant two-job chain and, after fan-out, the current branch's own repair ancestry. Reference authoring/stabilization prompts, diffs, graphs, failures, outputs, oracles, and all other setup records are forbidden. Under source_present it may contain permitted canonical/branch source versions. Under source_absent source files, source-bearing diffs, and historical prompts embedding source are withheld; this never alters otherwise-visible Etiq nodes or artifacts.",
    "restricted_setup_record_kinds": [
      "preflight",
      "authoring",
      "stabilization_repair",
      "rejected_candidate",
      "reference_execution",
      "reference_oracle",
      "complexity_gate"
    ],
    "source_bundle_factor_contract": {
      "intervention": "presence or absence of a separately supplied complete generated-chain source bundle",
      "paper_labels": {
        "source_present": "separate source bundle present",
        "source_absent": "separate source bundle withheld"
      },
      "graph_node_policy": "source setting must not alter any otherwise-visible Etiq node, node field, value preview, artifact value, artifact-inspection permission, or graph serialization",
      "paired_graph_evidence_identity": "Within a fixed graph evidence mode, visible node references, node serializations, relationship references, handoffs, and artifact-inspection eligibility are identical across the two source-bundle settings before adding the separate bundle and applying the allowed history filter.",
      "non_etiq_withheld_policy": "no graph evidence and no separate source bundle",
      "interpretation_limit": "this is not a source versus no-source comparison; graph modes may expose node-embedded source in both settings",
      "token_accounting": "node-embedded source counts as graph evidence; separate source-bundle tokens are counted as bundle evidence"
    },
    "package_manifest_fields": [
      "opaque IDs",
      "artifact allowlist",
      "artifact SHA-256 hashes",
      "canonical serialized UTF-8 bytes",
      "estimated input tokens",
      "separate-source-bundle and source-history filtering status",
      "capability flags",
      "upstream and downstream job IDs",
      "explicit setup-record exclusion status"
    ]
  },
  "physical_isolation": {
    "security_boundary": "production runner; package filtering and naming conventions are not security boundaries",
    "controller_visibility": "only the controller may see the repository, common capture, restricted truth, condition map, aggregate ledger, and all branches",
    "common_evidence": "the controller copies only an immutable hash-verified allowlist into each branch; the common/controller tree is not mounted or exposed to arm processes",
    "branch_roots": "separate opaque launch roots containing allowlisted evidence, own workspace, and private home/temp/output only",
    "branch_write_access": "own workspace, home, temp, and output only",
    "codex_sessions": "fresh, ephemeral, non-resumed; invocation JobStore inside the branch; root-deny filesystem policy permits only the current invocation/branch package and minimal read-only model runtime",
    "generated_subprocesses": "process-level filesystem sandbox, container, mount namespace, or equivalent whose visible root contains only branch source/input/frozen dependencies/private output and minimal read-only runtime; no sibling, repository, or restricted-controller access",
    "isolation_contract_path": "docs/workshops/neurips-2026-v2-2/ARM_ISOLATION_CONTRACT.md",
    "launch_policy_manifest_path": "docs/workshops/neurips-2026-v2-2/arm-isolation-launch-policy.json",
    "launch_policy_hash_binding": [
      "experiment preflight",
      "signed Tester isolation gate",
      "every reviewer, follow-up, repair, rerun-review, and other model-call trial record"
    ],
    "insufficient_controls": [
      "changing cwd",
      "opaque path names",
      "chmod or ordinary Unix ownership while branches share an OS user"
    ],
    "path_and_process_hygiene": {
      "reject_escaping_symlinks": true,
      "resolve_and_validate_allowlisted_paths_before_launch": true,
      "close_inherited_file_descriptors": true,
      "minimal_environment": true,
      "private_home": true,
      "private_temp": true,
      "private_output": true
    },
    "sandbox_unavailable_policy": "fail preflight closed; never fall back to an unrestricted subprocess",
    "tester_gate": {
      "required_before": "every reviewer-model call, including initial review, operation follow-up, receipt correction, repair, and repaired-run review",
      "independent_signoff_required": true,
      "launcher": "the exact production launch path and policy; mock or simulated launchers are invalid",
      "probe_processes": [
        "Codex invocation",
        "hostile generated Python job",
        "hostile repaired Python job"
      ],
      "probe_actions": [
        "read",
        "write",
        "list",
        "import"
      ],
      "known_exact_host_path_targets": [
        "repository",
        "controller code and restricted truth",
        "immutable common capture",
        "sibling branch"
      ],
      "additional_probes": [
        "environment leakage",
        "private home isolation",
        "private temp isolation",
        "symlink escape",
        "path traversal and resolved-path escape",
        "inherited file-descriptor access",
        "sandbox disabled",
        "sandbox misconfigured"
      ],
      "signed_artifact_template": "docs/experiments/2026-workshop-fault-localisation-v2/runs/<experiment_id>/restricted/isolation-gate.json",
      "signed_artifact_bindings": [
        "protocol content hash",
        "production launcher hash",
        "machine-readable launch-policy manifest hash",
        "sandbox backend name and version",
        "probe fixture and expected-result hash",
        "Tester identity/signature and timestamp"
      ],
      "freshness_rule": "the gate is current only for the exact bound protocol, launcher, launch policy, backend/version, and probe fixture",
      "blocking_failures": [
        "missing sign-off",
        "failed probe",
        "skipped probe",
        "stale gate",
        "mock or simulated launcher",
        "sandbox unavailable",
        "sandbox disabled or misconfigured"
      ],
      "tester_authority": "the Tester blocks all reviewer and repair model calls until every production-path probe passes"
    },
    "history_ancestry": "own branch only after fan-out",
    "condition_mapping": "restricted controller area only",
    "aggregation": "only after branch outputs are frozen",
    "network": "The Bubblewrap-isolated Codex control plane retains provider transport; its exact permission profile denies network to model-executed commands. Authored and repaired Python use Bubblewrap with the network namespace unshared.",
    "arm_order": "randomized and recorded",
    "codex_authentication": "copy only individually allowlisted authentication files into the private ephemeral Codex home; never mount the host Codex home"
  },
  "model_and_prompts": {
    "provider": "OpenAI via Codex CLI",
    "model": "gpt-5.5",
    "model_snapshot_policy": "Record the dated model version and provider/system fingerprint when returned. A model identifier change requires a protocol amendment.",
    "reasoning_effort": "high",
    "decoding": {
      "temperature": 0.2,
      "top_p": 1.0,
      "max_output_tokens": 16384,
      "response_format": "strict JSON Schema",
      "unsupported_parameter_policy": "Preflight records each unsupported parameter. Unsupported temperature/top_p/max_output_tokens are omitted rather than silently substituted; all trials must use the same supported parameter set."
    },
    "trial_seed_policy": "Send the frozen trial seed if the model interface supports seeding. If it does not, record trial index, request time, model version, and provider/system fingerprint; seeds still identify repetitions but are not claimed to make LLM output deterministic.",
    "strict_response_schema_contract": "Every object in the authoring, stabilization, review-receipt, and repair-response schemas explicitly forbids additional properties and requires exactly every declared property. The environment gate validates this recursively without a provider call.",
    "request_failure_recording": "Record failure category, inference-started status when known, candidate number, retry number, stable request identity, invocation identity when available, and whether provider usage is available.",
    "tool_settings": {
      "network": "disabled",
      "conversation_resume": false,
      "memory": false,
      "automatic_external_instructions": false,
      "review_filesystem": "read-only allowlisted common evidence plus own writable branch",
      "repair_edit_scope": "one selected declared function"
    },
    "prompt_contracts": {
      "prompt_authoring": {
        "path": "prompts/v2_2/fault_chain_authoring.md",
        "sha256": "sha256:e273415da22401bd7d6286b162d2160e42cf6587246f39ef95b5ba8e2589b656"
      },
      "prompt_stabilization": {
        "path": "prompts/v2_2/fault_chain_stabilization.md",
        "sha256": "sha256:797e9720c37a2c314e3be5c23b68a532210e87a14be27c0b355fa98b7073a647"
      },
      "prompt_review": {
        "path": "prompts/v2_2/fault_review.md",
        "sha256": "sha256:1a59763cce79f307b0b86501ee4d272726c6df793d7827a9c155b8b8fd22ea44"
      },
      "prompt_repair": {
        "path": "prompts/v2_2/fault_repair.md",
        "sha256": "sha256:dfec3251466b79ea2c3ab61620b1e60665632a7b42ea9fbc6a771681116e4f6a"
      },
      "schema_authoring": {
        "path": "schemas/v2_2/fault_chain_authoring.schema.json",
        "sha256": "sha256:73638606663573f870b0869359de5acdb096edea61d2a24899ca2f2dc7578290"
      },
      "schema_stabilization": {
        "path": "schemas/v2_2/fault_chain_stabilization.schema.json",
        "sha256": "sha256:28e0f170db156c337e3237f242c0ecc2c59a949f608c6bb1708ebff4881d7b49"
      },
      "schema_setup": {
        "path": "schemas/v2_2/fault_setup_record.schema.json",
        "sha256": "sha256:c1337c0359bb6e091c8f0f5ab8c9c8555d309c7ee85a06c4aaf65a49f54795ba"
      },
      "schema_condition_manifest": {
        "path": "schemas/v2_2/fault_condition_manifest.schema.json",
        "sha256": "sha256:378a8173a71e69a68fa068235dfbab840e9933b447f6963c90282a6d5146f329"
      },
      "schema_ground_truth": {
        "path": "schemas/v2_2/fault_ground_truth.schema.json",
        "sha256": "sha256:b47281f2c69daee450c57171fb8f5b1991379ae225716763a985e3e4407e4f59"
      },
      "schema_operation_event": {
        "path": "schemas/v2_2/fault_operation_event.schema.json",
        "sha256": "sha256:678daef65667213599705fa553bf195d103083ee19fad959da1af6a634967071"
      },
      "schema_package_manifest": {
        "path": "schemas/v2_2/fault_package_manifest.schema.json",
        "sha256": "sha256:7df3fccb8aad391fe5be8d7e320d640913bebbced6ecce3f3f4c5da8099d931a"
      },
      "schema_review_package": {
        "path": "schemas/v2_2/fault_review_package.schema.json",
        "sha256": "sha256:e44aab91d4c43691ff8eb12f7098591acb912cc368fd74d96528ce50fc469cdd"
      },
      "schema_review_receipt": {
        "path": "schemas/v2_2/fault_review_receipt.schema.json",
        "sha256": "sha256:3cebce8ef00c20f8316a4ed0998fd53ebff9e62a9471b7b635305ad7a5cbd075"
      },
      "schema_random_projection": {
        "path": "schemas/v2_2/random_projection_manifest.schema.json",
        "sha256": "sha256:6b9e7f7f9d6f58c2e0ac930e967a656279ddb175d0f3812d9cbec23bb73250cd"
      },
      "schema_repair_response": {
        "path": "schemas/v2_2/fault_repair_response.schema.json",
        "sha256": "sha256:3fd4dfd17b4fe20ee3f200c0e7c12fba3123d436250a64a3701eeb2b23243044"
      },
      "schema_instance": {
        "path": "schemas/v2_2/fault_instance.schema.json",
        "sha256": "sha256:bd54f36df09215705731ea06252252cbc81d042b6bb0992f87c66a2c12a67e81"
      },
      "schema_isolation_gate": {
        "path": "schemas/v2_2/fault_isolation_gate.schema.json",
        "sha256": "sha256:2739ffecae990e1edaf3fc115d42d79c19638ad274203a229ae4efae83ca7aab"
      }
    }
  },
  "budgets": {
    "model_input": {
      "max_estimated_input_tokens": 120000,
      "max_evidence_estimated_tokens": 90000,
      "reserved_prompt_and_output_tokens": 30000,
      "max_evidence_utf8_bytes": 360000,
      "gate": "both estimated-token and exact-byte limits must pass",
      "token_estimator": "provider tokenizer when available; record tokenizer name/version; otherwise use UTF-8 bytes as the enforceable gate and mark token count estimated_unavailable"
    },
    "section_construction": {
      "max_assigned_boundaries": 8,
      "context_overlap_boundaries_each_side": 1,
      "max_context_nodes": 300,
      "max_context_relationships": 512,
      "max_collapsed_helpers": 128,
      "single_boundary_overflow_policy": "exclude the entire instance before review; never arbitrarily truncate a boundary"
    },
    "values": {
      "inline_preview_max_serialized_characters": 4000,
      "artifact_inspection_max_rows_or_items": 100,
      "artifact_inspection_max_document_characters": 20000,
      "artifact_inspection_max_requests_per_call": 2
    },
    "history": {
      "max_serialized_utf8_bytes": 240000,
      "truncation_order": "oldest allowed history first, with a manifest of omitted artifacts; the current-run shared base is never truncated",
      "source_bundle_and_history_filtering_precedes_budgeting": true,
      "visible_graph_evidence_identical_across_paired_source_settings_within_evidence_mode": true,
      "graph_embedded_source_counts_toward_graph_budget": true
    },
    "random_matched": {
      "primary_measure": "canonical serialized UTF-8 bytes of residual graph evidence after M_f",
      "relative_tolerance": 0.05,
      "absolute_tolerance_bytes": 2048,
      "acceptance_formula": "absolute(random_residual_bytes-structural_residual_bytes) <= max(2048, ceil(0.05*structural_residual_bytes))",
      "token_difference": "recorded diagnostic, not the matching criterion",
      "no_match_policy": "invalidate the entire instance before model calls"
    }
  },
  "operation_permissions": {
    "common_sequence": [
      "capture",
      "review",
      "cite",
      "inspect_visible_artifact_when_allowed",
      "expand_direct_child_when_allowed",
      "judge",
      "identify_top_suspect",
      "validate_or_correct_receipt",
      "freeze_and_score_localisation",
      "retrace_when_allowed",
      "select_own_repair_target",
      "repair",
      "rerun_and_recapture",
      "re_review",
      "recompute_trusted_frontier",
      "resume_or_block"
    ],
    "judgments": [
      "trusted",
      "suspect",
      "failed",
      "not_pipeline_step"
    ],
    "citation_rule": "every citation must resolve to an exact reference visible in the current package",
    "artifact_inspection": "Graph conditions may reveal a bounded slice of an already visible value; inspection adds no nodes.",
    "helper_expansion": "Only etiq_selected_adaptive may request one direct collapsed child per follow-up call. The revealed nodes have exactly that child prefix; only relationships with visible endpoints are added; the child's direct children become collapsed choices.",
    "retrace": "After localisation is frozen, graph conditions may follow stored captured relationships upstream from their own suspect. Retrace cannot alter localisation.",
    "repair_target": "Each condition's single required top suspect determines the repair target; no oracle fallback is allowed.",
    "repair_source": "All conditions receive only the exact source of their independently selected function at repair time.",
    "edit_permission": "one complete declared function boundary; any change outside it is rejected",
    "rerun_policy": "For the exact two-job chain, an upstream-job repair reruns upstream then downstream; a downstream-job repair reruns downstream only using that branch's hash-verified upstream artifacts copied from the canonical evaluation execution. Recapture each rerun job, rebuild affected exact-hash handoffs, and never import sibling artifacts.",
    "resume_meaning": "workflow continuation from the recomputed trusted frontier, never LLM conversation resumption",
    "call_limits": {
      "review_operation_follow_up_calls_per_section": 3,
      "helper_expansions_per_follow_up_call": 1,
      "receipt_correction_calls_per_section": 2,
      "accepted_repair_generation_calls_per_trial": 1,
      "infrastructure_retry_attempts_after_initial_call": 2,
      "canonical_or_repaired_execution_infrastructure_retries_after_initial_attempt": 2,
      "model_api_infrastructure_retries_after_initial_call": 2,
      "repair_caused_code_schema_or_oracle_failure_is_retryable": false,
      "repair_scope_or_oracle_failure_is_retryable": false,
      "re_review_uses_same_limits_as_initial_review": true
    },
    "illegal_operation_policy": "reject and record the capability violation without adding evidence"
  },
  "randomization": {
    "trial_seeds": [
      104729,
      130363,
      155921
    ],
    "random_projection_master_seed": 8675309,
    "arm_order_master_seed": 314159,
    "random_projection_identity_scope": "one immutable projection per realized boundary",
    "random_projection_identity_fields": [
      "protocol_content_hash",
      "instance_id",
      "job_id",
      "boundary_id"
    ],
    "section_id_used_in_random_projection_identity": false,
    "seed_derivation": "first unsigned 64 bits of SHA-256 over '<purpose-master-seed>:<protocol-content-hash>:<instance-id>:<job-id>:<boundary-id>' encoded as UTF-8",
    "random_projection_draws_per_boundary": 1,
    "reuse_random_projection_across_trials": true,
    "reuse_random_projection_across_section_appearances": "The assigned appearance and every overlap-context appearance reference the same stored projection manifest and projection hash.",
    "section_assembly_rule": "Resolve each boundary to its stored projection; union evidence by exact node and relationship reference; deduplicate repeated references; never derive a new seed, redraw, or refill a residual budget because of section placement or deduplication.",
    "random_projection_manifest_fields": [
      "projection_id",
      "protocol_content_hash",
      "instance_id",
      "job_id",
      "boundary_id",
      "realized_boundary_hash",
      "serializer_name_and_version",
      "mandatory_interface_hash",
      "structural_residual_budget_bytes",
      "derived_seed",
      "ordered_candidate_universe_hash",
      "selected_node_refs",
      "selected_relationship_refs",
      "random_residual_bytes",
      "structural_residual_bytes",
      "absolute_and_relative_byte_difference",
      "projection_hash"
    ],
    "freeze_before_model_calls": true,
    "oracle_or_fault_truth_used_for_randomization": false,
    "random_candidate_order": "captured relationship reference then node reference, both lexicographic, before seeded sampling",
    "random_bundle_rule": "sample endpoint-complete relationship bundles from B_f residual evidence only; add a standalone node only if the structural residual contains standalone nodes and budget remains; never create dangling relationships"
  },
  "repetitions_and_counts": {
    "model_trials_per_configuration": 3,
    "primary_review_trials": {
      "formula": "12 instances x 4 primary configurations x 3 trials",
      "count": 144
    },
    "additional_ablation_review_trials": {
      "formula": "6 subset instances x 8 additional configurations x 3 trials",
      "count": 144
    },
    "total_review_trials": 288,
    "unique_primary_branches_before_repetition": 48,
    "unique_additional_ablation_branches_before_repetition": 48,
    "total_unique_review_branches_before_repetition": 96,
    "operational_repair_trials": {
      "formula": "5 faulty ablation instances x 12 configurations x 3 trials",
      "count": 180
    },
    "repair_pairing": "repair trial t uses the review output and top suspect from the same instance, configuration, and trial t",
    "independence_statement": "The 12 instances are independent; the three trials are repeated model measurements on the same immutable instance and package.",
    "retry_identity": "transport, rate-limit, timeout, schema, and infrastructure retries retain the same trial ID and receive incrementing attempt/call IDs; they are not extra trials"
  },
  "headline_metrics": {
    "fault_detection": {
      "definition": "percentage of faulty instance-trials with at least one failed or suspect boundary",
      "no_injection_companion": "false-positive percentage of no-injection-control trials with at least one failed or suspect boundary",
      "missing_or_invalid_trial": "failure to detect"
    },
    "fault_localisation": {
      "definition": "percentage of faulty instance-trials whose single reviewer-selected top suspect boundary function equals injected_function",
      "secondary": "helper/node localisation accuracy",
      "missing_multiple_or_unresolved_top_suspect": "incorrect"
    },
    "repair_success": {
      "definition": "percentage of designated operational trials whose repaired chain executes, passes all affected stage and end-to-end semantic oracles, preserves schemas, and introduces no regression",
      "missed_fault_or_wrong_boundary": "unsuccessful with no oracle target disclosure"
    },
    "token_use": {
      "primary_value": "cumulative provider-reported input tokens",
      "included_calls": [
        "review",
        "artifact inspection follow-up",
        "helper expansion follow-up",
        "receipt correction",
        "repair",
        "repaired-run review"
      ],
      "derived_values": [
        "input tokens per successful repair",
        "successful repairs per 100000 input tokens"
      ],
      "unavailable_usage": "never treated as zero; result is marked incomplete"
    }
  },
  "prespecified_comparisons": {
    "primary_12_instance_source_present": [
      "etiq_selected_adaptive versus current_run",
      "etiq_selected_adaptive versus history_full",
      "etiq_selected_adaptive versus etiq_full",
      "etiq_full versus current_run as descriptive more-evidence-alone control"
    ],
    "ablation_6_instance_only": [
      "etiq_selected_fixed versus etiq_random_matched",
      "etiq_selected_adaptive versus etiq_selected_fixed",
      "separate source bundle present versus withheld within every evidence mode",
      "change in detection, localisation, and repair",
      "tokens added or saved by the separate source bundle"
    ],
    "reporting": "paired per-instance results and wins/ties/losses; average trials within instance/configuration before across-instance summaries; separately report trial agreement/dispersion; do not claim n=36 or report the 12-configuration matrix as running on all 12 instances"
  },
  "exclusions_and_failures": {
    "pre_model_instance_exclusions": [
      "reference chain fails compilation, offline execution, schema oracle, semantic oracle, or end-to-end oracle",
      "a complete required review package exceeds the hard context budget without a non-arbitrary split",
      "declared boundary cannot match an observed stack",
      "exact-hash handoff requirement fails",
      "full boundary package cannot fit without arbitrary truncation",
      "random matched package cannot meet tolerance",
      "faulty mutant is equivalent, crashing, uncaptured, schema-invalid, trivially disclosed, not executed, or does not fail the intended semantic oracle",
      "reference candidate exhausts its one permitted source correction",
      "reference slot exhausts two candidates",
      "frozen mutation-site order is exhausted"
    ],
    "paired_exclusion_rule": "Any pre-model exclusion invalidates the entire instance across all configurations. Regeneration is permitted only within its frozen slot and attempt limit before any reviewer result is observed.",
    "post_model_policy": "Never exclude a completed branch because of its result. After initial plus two infrastructure retries, retain the failed trial in the ledger as missing/failed; do not add a favorable fourth trial.",
    "behavioural_failures_count_as": {
      "no_fault_flag": "detection and localisation failure on faulty cases",
      "wrong_boundary": "localisation and repair failure",
      "invalid_or_out_of_scope_patch": "repair failure",
      "rerun_crash_schema_failure_or_oracle_failure": "repair failure",
      "no_injection_fault_flag": "false positive"
    },
    "protocol_completion_gate": "Do not begin model review runs unless all 12 instance slots, all six ablation slots, all five repair slots, all package hashes, all expected count preflights, and the current signed Tester production-isolation gate pass. Otherwise amend the protocol before observing results or report the experiment incomplete."
  },
  "determinism": {
    "frozen_capture_reuse": "The same immutable canonical capture is used by every condition and trial for an instance.",
    "etiq_capture": "Claim deterministic captured G_j for a frozen execution only if the pinned Etiq/environment replay check verifies that property. Until verified, describe the recorded capture as fixed and immutable, not the capture process as unconditionally deterministic.",
    "deterministic_given_frozen_inputs": [
      "exact-hash handoff construction",
      "declaration-to-stack matching and B_f materialization",
      "structural initial projection",
      "separate source-bundle and source-history filtering",
      "section construction",
      "random matched projection given graph, serializer, seed, and budget",
      "artifact slice returned for a valid request",
      "nodes and relationships revealed for a valid helper request",
      "receipt validation",
      "upstream retrace with lexicographic tie-breaking",
      "rerun job-set selection"
    ],
    "nondeterministic_or_conditionally_seeded": [
      "two-job reference authoring and bounded stabilization",
      "review judgments",
      "artifact-inspection requests",
      "helper-expansion requests",
      "suspect selection",
      "repair generation",
      "repaired-run review judgments"
    ],
    "seed_caveat": "A supported model seed improves repeatability but is not treated as a determinism guarantee."
  },
  "recording": {
    "immutable_manifest_before_calls": true,
    "preflight_required_artifacts": [
      "protocol version and content hash",
      "accepted deterministic Phase-A smoke-test artifact sha256:f4c04cdbb841a4749053a0d38cae2dba84fda17ee7102e5d96b8ec89d0b0cf10",
      "Phase-3 construction, Phase-4 canonical-capture, and Phase-5 package-freeze readiness records",
      "production launcher hash",
      "machine-readable launch-policy manifest hash",
      "current signed Tester isolation-gate artifact"
    ],
    "append_only_attempts": true,
    "stable_id_levels": [
      "experiment_id",
      "protocol_version",
      "preflight_id",
      "scenario_id",
      "authoring_id",
      "instance_id",
      "chain_id",
      "job_id",
      "capture_set_id",
      "job_capture_id",
      "condition_id",
      "trial_id",
      "branch_id",
      "call_id",
      "repair_id",
      "rerun_capture_set_id"
    ],
    "required_hashes": [
      "protocol",
      "git commit and dirty patch",
      "environment",
      "model settings",
      "prompts and schemas",
      "scenario, corpus, and capability catalogue",
      "reference and mutant sources",
      "oracles",
      "per-job captures and capture set",
      "handoffs",
      "source-bundle/history filtering and condition packages",
      "branch allowlists",
      "production launcher and machine-readable launch policy",
      "signed Tester isolation gate",
      "random projections",
      "requests and responses",
      "repairs and rerun captures"
    ],
    "usage_fields": "provider-reported input, cached-input, output, reasoning, and total tokens when available, plus normalized input/output totals",
    "setup_usage": "Record authoring, stabilization, preflight, reference execution, and oracle calls/tokens separately in the controller-only tree; never include them in reviewer manifests or experimental treatment-token totals.",
    "restricted_setup_record_kinds": [
      "preflight",
      "authoring",
      "stabilization_repair",
      "rejected_candidate",
      "reference_execution",
      "reference_oracle",
      "complexity_gate"
    ],
    "operation_log": "record every request, response, citation, inspection, expansion, correction, suspect, retrace, capability rejection, patch, rerun, oracle, re-review, frontier, and resume/blocked event",
    "truth_separation": "fault and oracle truth remain in the restricted controller area and are joined only during scoring",
    "checkpointing": "verify hashes, skip completed immutable records, and append attempts when resuming",
    "publication": "Publish replay materials and redacted captures only after release approval, including the explicit post-pilot disclosure. Do not publish private Etiq capture implementation, secrets, author/company identity, copyrighted full pages, or controller-only condition mapping during double-blind review. Protocol 1.3.1 engineering preflights remain excluded and are never pooled with v2."
  },
    "tester_invariants": [
    "protocol version and recomputed content hash match every run manifest",
    "the Markdown and JSON describe the same counts, slots, conditions, budgets, permissions, metrics, and failure rules",
    "the July commands, arm names, code paths, and pilot artifact remain unchanged",
    "there are 12 fresh instance slots, not stored baseline pipelines",
    "every accepted chain has exactly two dependent executed jobs, two exact handoffs, the realized boundaries required for its assigned packages, and passing hidden reference oracles, with no declaration, stage, helper, aggregation-shape, or selected/full-ratio quota",
    "authoring and source-correction requests contain no designation, fault class, target job or stage, injection seed, helper target, ablation membership, repair membership, or controller truth",
    "handoffs are exact-hash controller provenance and never labelled as Etiq edges",
    "valid unmatched declarations are controller-only audit records and do not alone invalidate an instance; boundary_health is absent from reviewer packages",
    "all conditions share the same non-treatment base package and source-bundle-present variants receive the same separate chain-source bundle bytes",
    "source-bundle-withheld packages contain no separate source bundle or source history",
    "visible Etiq nodes and inspectable node artifacts are serialized identically across paired source-bundle settings, including node-embedded source",
    "non-Etiq packages contain no graph evidence",
    "fixed and adaptive selected initial packages are byte-identical",
    "random residuals are boundary-contained, endpoint-complete, oracle-blind, deterministic from the frozen seed, and within byte tolerance",
    "a boundary has one random projection manifest and hash reused unchanged in assigned and overlap section appearances, with section assembly deduplicating references without resampling",
    "only adaptive selected can expand and every expansion is one visible direct child",
    "artifact inspection adds no nodes and targets visible values only",
    "localisation is frozen before retrace and repair",
    "every repair edits only the branch-selected function and reruns the repaired job plus all downstream jobs",
    "branches cannot read or name siblings, restricted truth, condition mappings, or mutable common evidence",
    "the Tester gate uses the exact production launcher and denies read, write, list, and import access to exact-path repository, controller, common-capture, and sibling targets from Codex and hostile generated/repaired jobs",
    "the Tester gate covers environment leakage, private home/temp, symlink and resolved-path traversal, inherited file descriptors, and sandbox disablement or misconfiguration",
    "the signed Tester gate binds protocol, production launcher, launch-policy manifest, sandbox backend/version, probe fixture, Tester signature, and timestamp; a missing, stale, skipped, failed, or mock gate blocks every model call",
    "packages and random projections are identical across three trials while model sessions are fresh",
    "the schedule is 144 primary plus 144 additional ablation review trials, not 12x12x3",
    "the five faulty ablation instances yield 180 paired operational repair trials",
    "failed or missing trials remain in the ledger and receive no favorable replacement",
    "headline metrics use behavioral oracles for repair success and provider-reported input tokens for cost",
    "accepted Phase-A artifact sha256:f4c04cdbb841a4749053a0d38cae2dba84fda17ee7102e5d96b8ec89d0b0cf10 and exact 11-file tree sha256:20a44c62c120afed1f9dba82cdd87817fc0cc38b1c979023b0a36e5ea7a2b736 are verified and reused without rerun or regeneration; the artifact remains unscored, controller-only, excluded from the 12 instances and all model context, and is not used as a package or repair-test fixture",
    "Phase A makes zero authoring, stabilization, reviewer, and repair model calls and freezes one oracle-passing reference plus one predefined oracle-effective mutant",
    "setup record kinds and setup usage are controller-only and absent from packages, histories, graph operations, repair ancestry, model-visible errors, and treatment-token totals",
    "upstream repairs rerun both jobs while downstream repairs rerun only downstream from canonical hash-verified upstream artifacts",
    "eligible mutation sites use one frozen oracle-blind order and invalid mutants advance without reviewer information",
    "every v2 declaration and realized boundary retains the exact selected-job, normalized-path, qualified-definition, and normalized-function-source-hash identity",
    "every direct captured node at every grouped prefix has a complete recomputable enrichment identity; a partial, forged, wrong-job, or ambiguous node invalidates the instance",
    "the exact restricted preferred mutation occurrence is first when eligible and every fallback order key binds the complete target identity and site subidentity",
    "every governed prompt and schema resolves to its v2 namespace path and exact protocol-recorded hash without predecessor fallback",
    "resolved predecessor read, list, import, resume, patch, consume, and write targets are rejected before I/O, including dot-dot and symlink aliases into the complete predecessor output root"
  ],
  "design_date": "2026-08-29",
  "v2_design_history": {
    "label": "v2 design history; every version is post-pilot, and N02 consumed 2.0.2 only through excluded pre-inference transport failures",
    "versions": [
      {
        "version": "2.0.0",
        "classification": "N01 rejected design",
        "status": "rejected_not_executed",
        "post_pilot": true,
        "executed": false,
        "archive_manifest": "docs/workshops/neurips-2026-v2/archive/rejected-2.0.0/archive-manifest.json",
        "authority_path": "instructions_between_agent_types/overseer/decisions/N01_v2_study_design_authorization.json",
        "authority_sha256": "sha256:c90c5c41c0f076b5730819a055e7daca62dcf96d6ac43a5762827de705b38186"
      },
      {
        "version": "2.0.1",
        "classification": "N01A design remediation",
        "status": "unaccepted_not_executed",
        "post_pilot": true,
        "executed": false,
        "archive_manifest": "docs/workshops/neurips-2026-v2/archive/unaccepted-2.0.1/archive-manifest.json",
        "authority_path": "instructions_between_agent_types/overseer/decisions/N01A_v2_design_remediation_authorization.json",
        "authority_sha256": "sha256:4c35eeeed87c6549cdc6d0b1989a8c0b91a051d1e8573c805dd046176efd9479"
      },
      {
        "version": "2.0.2",
        "classification": "N01B execution-readiness remediation without scientific design change",
        "status": "n02_consumed_excluded_pre_inference_invalid_execution_readiness",
        "post_pilot": true,
        "executed": false,
        "n02_authority_consumed": true,
        "authoring_invocation_attempts": 3,
        "successful_authoring_responses": 0,
        "completed_model_inferences": 0,
        "etiq_executions": 0,
        "mutation_attempts": 0,
        "reviewer_model_calls": 0,
        "archive_manifest": "docs/workshops/neurips-2026-v2/archive/excluded-2.0.2-n02/archive-manifest.json",
        "authority_path": "instructions_between_agent_types/overseer/decisions/N01B_v2_execution_readiness_remediation_authorization.json",
        "authority_sha256": "sha256:727b8612a906a59788fce0450b7294a1e610c02d05eab4df8f8cffe1a3b08ae4"
      },
      {
        "version": "2.0.3",
        "classification": "N02A transport and execution-readiness remediation without scientific design change",
        "status": "pending_independent_tester_acceptance_not_executed",
        "post_pilot": true,
        "executed": false,
        "model_calls": 0,
        "preflight_runs": 0,
        "authority_path": "instructions_between_agent_types/overseer/decisions/N02A_v2_phase_a_transport_remediation_authorization.json",
        "authority_sha256": "sha256:bf1f0fa875e226101c88134a34f9910c20b3256864a86513b18344518f809abd"
      },
      {
        "version": "2.1.0",
        "classification": "material pre-results redesign informed only by excluded N02-N04 engineering preflights",
        "status": "terminal_incomplete_excluded_engineering_evidence",
        "post_pilot": true,
        "reviewer_model_calls_observed_before_change": 0,
        "experimental_outcomes_observed_before_change": 0,
        "authority_path": "instructions_between_agent_types/overseer/decisions/N05_v2_1_end_to_end_completion_program_authorization.json",
        "authority_sha256": "sha256:2928e57ecd8423365a53758424282b07928727bade71f8ff4fb1ce205df43a95"
      },
      {
        "version": "2.2.0",
        "classification": "material pre-results projection correction plus N12 removal of the model-dependent Phase-B rehearsal, informed only by excluded engineering preflights",
        "status": "pre_results_frozen",
        "post_pilot": true,
        "reviewer_model_calls_observed_before_change": 0,
        "repair_model_calls_observed_before_change": 0,
        "experimental_instances_observed_before_change": 0,
        "experimental_outcomes_observed_before_change": 0,
        "authority_path": "instructions_between_agent_types/overseer/decisions/N12_v2_2_phase_b_removal_and_experiment_execution_authorization.json",
        "authority_sha256": "sha256:9549b6ff9d38ab138270b9a420277c9b7857d6f7efbae1bd1b8f6d1c0c3f40f0"
      }
    ],
    "execution_authority": "N12 continuous execution authority after implementation verification and the 12-instance, 12-capture, 96-package pre-review freeze"
  },
  "pilot_informed_disclosure": {
    "engineering_preflight_outputs_observed": true,
    "reported_experiment_results_observed": false,
    "reviewer_model_calls_observed": 0,
    "experimental_outcomes_observed": 0,
    "statement": "Protocol 2.2.0 and the N12 pre-results amendment were finalized after excluded engineering attempts 001-010, with zero experimental reviewer calls, repairs, or outcomes. N12 removes the model-dependent Phase-B rehearsal, retains deterministic readiness checks, and leaves the 12-instance evidence-condition experiment and its analysis unchanged."
  },
  "reverse_ordering_v2": {
    "supported_sites": [
      "built-in sorted with absent reverse",
      "built-in sorted with literal Boolean reverse",
      "DataFrame.sort_values with literal Boolean ascending",
      "each element of a non-empty literal Boolean-list ascending value as its own subsite"
    ],
    "unsupported_sites": [
      "computed reverse or ascending",
      "dynamic reverse or ascending",
      "non-Boolean reverse or ascending",
      "positional or ambiguous ascending",
      "empty or mixed ascending lists",
      "any transform requiring multiple AST edits"
    ],
    "target_identity_fields": [
      "job_id",
      "normalized_source_path",
      "qualified_function_name",
      "normalized_function_source_sha256"
    ],
    "frozen_order_key_fields": [
      "mutation_seed",
      "normalized_clean_bundle_sha256",
      "job_id",
      "normalized_source_path",
      "qualified_function_name",
      "normalized_function_source_sha256",
      "site_kind",
      "occurrence",
      "list_subsite"
    ],
    "preferred_occurrence": "place the restricted controller requested occurrence first when eligible, then traverse the SHA-256-sorted deterministic fallback order",
    "freeze_timing": "after reference freeze and before any semantic-oracle result",
    "attempt_rule": "toggle exactly one selected AST subsite, change exactly one contiguous normalized source region, execute the changed statement, validate both jobs and hidden oracles, and restore the normalized clean bundle byte-for-byte after every attempt",
    "rejection_rule": "invalid or ineffective sites advance without repair or model information; exhaustion rejects the candidate"
  },
  "namespace_registry": {
    "fallback_to_protocol_1_3_1_permitted": false,
    "contracts": {
      "prompt_authoring": {
        "path": "prompts/v2_2/fault_chain_authoring.md",
        "sha256": "sha256:e273415da22401bd7d6286b162d2160e42cf6587246f39ef95b5ba8e2589b656"
      },
      "prompt_stabilization": {
        "path": "prompts/v2_2/fault_chain_stabilization.md",
        "sha256": "sha256:42d4730c4e7c9872e6f5215cc1c9b2c6d36831aefeb4a7ff5fe1f13420410bbd"
      },
      "prompt_review": {
        "path": "prompts/v2_2/fault_review.md",
        "sha256": "sha256:1a59763cce79f307b0b86501ee4d272726c6df793d7827a9c155b8b8fd22ea44"
      },
      "prompt_repair": {
        "path": "prompts/v2_2/fault_repair.md",
        "sha256": "sha256:dfec3251466b79ea2c3ab61620b1e60665632a7b42ea9fbc6a771681116e4f6a"
      },
      "schema_authoring": {
        "path": "schemas/v2_2/fault_chain_authoring.schema.json",
        "sha256": "sha256:73638606663573f870b0869359de5acdb096edea61d2a24899ca2f2dc7578290"
      },
      "schema_stabilization": {
        "path": "schemas/v2_2/fault_chain_stabilization.schema.json",
        "sha256": "sha256:000889f15606d9d237c07fb544089268329a83354c0d889a785a416b3e69a713"
      },
      "schema_setup": {
        "path": "schemas/v2_2/fault_setup_record.schema.json",
        "sha256": "sha256:c1337c0359bb6e091c8f0f5ab8c9c8555d309c7ee85a06c4aaf65a49f54795ba"
      },
      "schema_condition_manifest": {
        "path": "schemas/v2_2/fault_condition_manifest.schema.json",
        "sha256": "sha256:378a8173a71e69a68fa068235dfbab840e9933b447f6963c90282a6d5146f329"
      },
      "schema_ground_truth": {
        "path": "schemas/v2_2/fault_ground_truth.schema.json",
        "sha256": "sha256:b47281f2c69daee450c57171fb8f5b1991379ae225716763a985e3e4407e4f59"
      },
      "schema_operation_event": {
        "path": "schemas/v2_2/fault_operation_event.schema.json",
        "sha256": "sha256:678daef65667213599705fa553bf195d103083ee19fad959da1af6a634967071"
      },
      "schema_package_manifest": {
        "path": "schemas/v2_2/fault_package_manifest.schema.json",
        "sha256": "sha256:7df3fccb8aad391fe5be8d7e320d640913bebbced6ecce3f3f4c5da8099d931a"
      },
      "schema_review_package": {
        "path": "schemas/v2_2/fault_review_package.schema.json",
        "sha256": "sha256:e44aab91d4c43691ff8eb12f7098591acb912cc368fd74d96528ce50fc469cdd"
      },
      "schema_review_receipt": {
        "path": "schemas/v2_2/fault_review_receipt.schema.json",
        "sha256": "sha256:3cebce8ef00c20f8316a4ed0998fd53ebff9e62a9471b7b635305ad7a5cbd075"
      },
      "schema_random_projection": {
        "path": "schemas/v2_2/random_projection_manifest.schema.json",
        "sha256": "sha256:6b9e7f7f9d6f58c2e0ac930e967a656279ddb175d0f3812d9cbec23bb73250cd"
      },
      "schema_repair_response": {
        "path": "schemas/v2_2/fault_repair_response.schema.json",
        "sha256": "sha256:3fd4dfd17b4fe20ee3f200c0e7c12fba3123d436250a64a3701eeb2b23243044"
      },
      "schema_instance": {
        "path": "schemas/v2_2/fault_instance.schema.json",
        "sha256": "sha256:bd54f36df09215705731ea06252252cbc81d042b6bb0992f87c66a2c12a67e81"
      },
      "schema_isolation_gate": {
        "path": "schemas/v2_2/fault_isolation_gate.schema.json",
        "sha256": "sha256:2739ffecae990e1edaf3fc115d42d79c19638ad274203a229ae4efae83ca7aab"
      },
      "contract_arm_isolation": {
        "path": "docs/workshops/neurips-2026-v2-2/ARM_ISOLATION_CONTRACT.md",
        "sha256": "sha256:310644ffd54db385dd9d3e13bedffb2ffa47867238ff4fe62750baa41bf0f183"
      },
      "contract_launch_policy": {
        "path": "docs/workshops/neurips-2026-v2-2/arm-isolation-launch-policy.json",
        "sha256": "sha256:fa07c11616ca6ab58c3af35b43d9c6c72c7e9ae4218b171767cfd35c50763eb5"
      }
    },
    "phase_contracts": {
      "authoring": [
        "prompt_authoring",
        "schema_authoring"
      ],
      "stabilization": [
        "prompt_stabilization",
        "schema_stabilization"
      ],
      "setup_and_construction": [
        "schema_setup",
        "schema_ground_truth",
        "schema_instance"
      ],
      "fan_out": [
        "schema_condition_manifest",
        "schema_package_manifest",
        "schema_review_package",
        "schema_random_projection"
      ],
      "review_and_operations": [
        "prompt_review",
        "schema_review_receipt",
        "schema_operation_event"
      ],
      "repair": [
        "prompt_repair",
        "schema_repair_response"
      ],
      "tester_gate": [
        "contract_arm_isolation",
        "contract_launch_policy",
        "schema_isolation_gate"
      ]
    }
  },
  "predecessor_isolation": {
    "forbidden_operations": [
      "read",
      "list",
      "import",
      "resume",
      "patch",
      "consume",
      "write"
    ],
    "predecessor_roots": [
      "outputs/fault-experiments/",
      "instructions_between_agent_types/developer/handoffs/",
      "docs/experiments/2026-workshop-fault-localisation/",
      "docs/workshops/neurips-2026/"
    ],
    "namespace_rule": "all 2.2 prompt and schema access is confined to prompts/v2_2 and schemas/v2_2",
    "resolution_rule": "resolve absolute, relative, dot-dot, and symlink paths before any operation; reject a resolved predecessor target before caller I/O",
    "model_context_rule": "authoring, stabilization, review, repair, and judge contexts reject every authority decision, handoff, restricted controller path, and predecessor decision, marker, history, setup, candidate, fixture, prompt, schema, capture, response, rejection, or output; v2 output-package references are allowed",
    "controller_authority_rule": "controller read/consume permits only the exact resolved hash-verified N01, N01A, N01B, or caller-supplied future N02 decision path; all other decisions including every C07 authority are denied",
    "controller_state_rule": "controller writes are confined to outputs/fault-experiments-v2-2; every old output remains read-only excluded engineering evidence",
    "output_root": "outputs/fault-experiments-v2-2/",
    "v2_output_lifecycle_rule": "append-only N06 gate state; exact-hash resume only; immutable completed records are never overwritten"
  },
  "predecessor_protocol_history": {
    "label": "preserved predecessor history; these are not versions of the separate v2 protocol ID",
    "protocol_id": "neurips-2026-workshop-fault-localisation",
    "protocol_version": "1.3.1",
    "path": "docs/workshops/neurips-2026/experiment-protocol.json",
    "exact_json_sha256": "sha256:9f5dbf3fe465ce86bc06b4c75cd9f6e743357c97eedfe0eb58fe4a18614976c8",
    "canonical_content_hash": "sha256:c5af2acbe1aa7ab473efad4d2fc3adb4183edaadf23165831cfb7b052a3b1d9f",
    "amendments": [
      {
        "version": "1.0.1",
        "date": "2026-08-25",
        "classification": "pre-results protocol clarification",
        "change": "Random matched projection identity is boundary-scoped. Section ID is excluded from seed derivation, and assigned or overlap appearances reuse one immutable projection manifest without resampling.",
        "results_observed_before_change": false
      },
      {
        "version": "1.1.0",
        "date": "2026-08-25",
        "classification": "pre-results protocol amendment",
        "change": "The source factor is redefined as separate complete source bundle present versus withheld. Withholding the bundle does not redact source fields, source-bearing previews, or source-bearing artifacts from otherwise-visible Etiq nodes. The factor is not described as source versus no source.",
        "results_observed_before_change": false
      },
      {
        "version": "1.2.0",
        "date": "2026-08-25",
        "classification": "pre-results production-isolation amendment",
        "change": "Arm isolation becomes a production-runner security boundary with controller-only privileged access, copied hash-verified branch allowlists, branch-local Codex invocation storage, private runtime directories, root-deny Codex permissions, process-level sandboxing for generated and repaired jobs, fail-closed launch policy, and a mandatory independently signed Tester gate through the production launcher.",
        "results_observed_before_change": false
      },
      {
        "version": "1.3.0",
        "date": "2026-08-27",
        "classification": "pre-results two-job foundation amendment",
        "change": "Replace the three-job clean-chain design with one unscored two-phase preflight and exactly two dependent executed jobs per experimental instance; accept only bounded-stabilized oracle-passing references, hide all setup ancestry, freeze upstream/downstream suffix reruns and oracle-blind mutation-site fallback, and separate setup usage from treatment usage.",
        "results_observed_before_change": false
      },
      {
        "version": "1.3.1",
        "date": "2026-08-28",
        "classification": "pre-results preflight helper-eligibility amendment",
        "change": "Preserve the exhausted 1.3.0 preflight and all 591158 setup tokens unchanged; determine helper eligibility only from captured direct-child function prefixes that a legal adaptive expansion can reveal with additional evidence; use old Candidate 1 only as detector regression evidence; prohibit graph evidence for oracle/complexity stabilization; and authorize exactly one fresh three-candidate Phase-A set before freezing the experiment incomplete.",
        "reviewer_results_observed_before_change": false,
        "setup_results_observed_before_change": true,
        "preserved_failed_preflight_id": "preflight-03420ef8721a4358",
        "preserved_failed_preflight_tree_sha256": "sha256:4a1d6b02ef80a08b3ef8013096c91a8a8e00e89af7f537e7ec97a38a4dd2f8fb",
        "preserved_setup_tokens": 591158
      }
    ]
  },
  "normative_artifacts": [
    {
      "id": "preflight_scenario",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/scenario.json",
      "sha256": "sha256:6bd6c5bca0c65a219c61e4ce3f85dedaa48f5c5377acdc4562e7b3048d89ebdd"
    },
    {
      "id": "preflight_corpus",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/corpus.json",
      "sha256": "sha256:30deeaf6d2a4ccfe6200429ef80d2a027a4d588bb86318bf265bf51a507a3d04"
    },
    {
      "id": "preflight_capabilities",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/capabilities.json",
      "sha256": "sha256:9dab835301e4e07f1fe987039913544928a69481b3bd77701535a759a2d2ae35"
    },
    {
      "id": "preflight_oracles",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/oracles.json",
      "sha256": "sha256:08c62ba851ccc6edb813d32dfb66b4db4b9128dc80cefbd1641fe4f0487c5895"
    },
    {
      "id": "restricted_controller_plan",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/preflight/restricted/controller-plan.json",
      "sha256": "sha256:7c4936e4a3e04d56e4e9cea1633bf3547a0778058ed7cf1728a3ce66e7f19fe3"
    },
    {
      "id": "minimum_qualification_fixture",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/qualification-minimum/fixture.json",
      "sha256": "sha256:0d15324305b7d0b6fb3f2b9843aaada0a33290e17e7a05ecab98ae024d81a481"
    },
    {
      "id": "minimum_qualification_upstream",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/qualification-minimum/upstream.py",
      "sha256": "sha256:d1ac5836cf885cc10c72ec307abbb3d3915c2530e9e5c627fce332ec74f24639"
    },
    {
      "id": "minimum_qualification_downstream",
      "path": "docs/experiments/2026-workshop-fault-localisation-v2-2/fixtures/qualification-minimum/downstream.py",
      "sha256": "sha256:afa4a8698b2c69e69ec64a9da1aabced3baf387200dc5eea57255757b02d1e5d"
    },
    {
      "id": "protocol_2_1_archive_json",
      "path": "docs/workshops/neurips-2026-v2-2/archive/protocol-2.1.0/experiment-protocol.json",
      "sha256": "sha256:ac0ba80ed17b083f11148540bf11fb48d640900441f5a46c564c9e620fd26967"
    },
    {
      "id": "protocol_2_1_archive_markdown",
      "path": "docs/workshops/neurips-2026-v2-2/archive/protocol-2.1.0/EXPERIMENT_PROTOCOL.md",
      "sha256": "sha256:5b160af62f7b67ad396382829de41d3c7d769bd74bf9840965a4cf2b8c79e859"
    },
    {
      "id": "n05_preservation_baseline",
      "path": "outputs/fault-experiments-v2-2/gate-0/n05-preservation-baseline.json",
      "sha256": "sha256:8a4cb4558b5800bfd51d2d45dc870fba31fb19bccdd79086569cb9a405f62399"
    },
    {
      "id": "arm_isolation_contract",
      "path": "docs/workshops/neurips-2026-v2-2/ARM_ISOLATION_CONTRACT.md",
      "sha256": "sha256:310644ffd54db385dd9d3e13bedffb2ffa47867238ff4fe62750baa41bf0f183"
    },
    {
      "id": "arm_isolation_launch_policy",
      "path": "docs/workshops/neurips-2026-v2-2/arm-isolation-launch-policy.json",
      "sha256": "sha256:fa07c11616ca6ab58c3af35b43d9c6c72c7e9ae4218b171767cfd35c50763eb5"
    }
  ],
  "boundary_identity_v22": {
    "canonical_name": "one or more non-keyword Python identifiers joined by one dot, lexical source order only; module names, classes, and runtime-only <locals> are excluded",
    "transport_normalization": "remove only components exactly equal to <locals>, then require exact job, normalized source path, lexical name, and one AST definition",
    "static_identity": [
      "job_id",
      "normalized_source_path",
      "lexical_qualified_function_name",
      "normalized_function_source_sha256"
    ],
    "realization": "independently enrich exact captured definition identities, intersect them with valid static declarations, group repeated prefixes only for the same identity, and retain every prefix and captured evidence ID",
    "unmatched_audit_visibility": "controller only; never reviewer evidence"
  },
  "n06_program": {
    "ordered_gates": [
      "G0_engineering_and_design",
      "G1_independent_qualification",
      "G2_verify_existing_phase_a_artifact",
      "G3_12_instances",
      "G4_12_canonical_captures",
      "G5_96_verified_packages",
      "G6_288_reviews_180_repairs",
      "G7_analysis_and_anonymous_replay"
    ],
    "terminal_outcomes": [
      "completed_experiment_and_analysis",
      "experiment_incomplete_at_named_gate",
      "fail_closed_binding_or_preservation_error"
    ],
    "no_overseer_reapproval_between_passing_gates": true,
    "post_gate_1_governed_changes": "Before the first experimental reviewer call, N12 permits the smallest controller correction followed by complete readiness rerun; after the first call governed bytes freeze.",
    "former_phase_b_mechanical_tests": [
      "an upstream target reruns both jobs",
      "a downstream target reruns only downstream from the canonical hash-verified upstream artifact",
      "repair scope, recapture, handoff rebuilding, repackaging, capabilities, and isolation pass without reviewer or repair model calls"
    ]
  }
}
```
