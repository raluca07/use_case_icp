"""Deterministically render the protocol-2.1 JSON and Markdown pair."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/workshops/neurips-2026-v2/experiment-protocol.json"
TARGET_ROOT = ROOT / "docs/workshops/neurips-2026-v2-1"


def digest(path: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def contract(path: str) -> dict[str, str]:
    return {"path": path, "sha256": digest(path)}


def main() -> None:
    protocol = json.loads(SOURCE.read_text())
    protocol["protocol_version"] = "2.1.0"
    protocol["status"] = "pre_results_frozen"
    protocol["design_date"] = "2026-08-29"
    protocol["integrity"]["content_hash"] = ""
    protocol["authority"].update(
        {
            "human_readable_specification": "docs/workshops/neurips-2026-v2-1/EXPERIMENT_PROTOCOL.md",
            "machine_readable_configuration": "docs/workshops/neurips-2026-v2-1/experiment-protocol.json",
            "execution_authority": "N05 standing conditional authorization; Gate 0 permits zero model calls, a signed exact-hash Gate 1 activates the one-use model Phase A, and later passing gates continue without further Overseer approval",
        }
    )
    n05_path = "instructions_between_agent_types/overseer/decisions/N05_v2_1_end_to_end_completion_program_authorization.json"
    protocol["authority"]["design_decisions"].append(
        {"path": n05_path, "sha256": digest(n05_path)}
    )
    protocol["scope"]["new_command_namespace"] = "fault-experiment-v2-1"
    protocol["scope"]["new_output_namespace"] = "outputs/fault-experiments-v2-1/"
    protocol["scope"]["stored_pipeline_policy"] = (
        "Every 2.1 reference is freshly authored from frozen 2.1 inputs. N02-N04 and protocol-1.3.1 responses, sources, diagnostics, captures, candidates, histories, and outputs are excluded engineering evidence and are never model context or experimental input."
    )
    preflight = protocol["lifecycle"]["preflight"]
    preflight.update(
        {
            "scenario_id": "n05-unscored-preflight-runtime-recovery",
            "scenario_path": "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/scenario.json",
            "corpus_path": "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/corpus.json",
            "capability_catalogue_path": "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/capabilities.json",
            "oracle_path": "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/oracles.json",
            "restricted_controller_plan_path": "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/restricted/controller-plan.json",
            "authoring_seed": 26082941,
            "mutation_seed": 26082997,
            "execution_authorization_required": "exact Gate-0 design freeze and signed independent Gate-1 artifact under N05",
        }
    )
    design = protocol["instance_design"]
    design["minimum_declarations_per_job"] = 8
    design["minimum_realized_static_boundaries"] = 12
    design["mandatory_realized_semantic_stages"] = [
        "upstream_demand_selection",
        "upstream_evidence_normalization",
        "upstream_provenance_assembly",
        "downstream_coverage_mapping",
        "downstream_prioritization",
        "downstream_synthesis",
    ]
    design["reference_acceptance"] = (
        "Both offline real-Etiq jobs and all oracles pass; at least 12 exact declaration/capture-intersection boundaries realize all six mandatory semantic stages; valid unmatched declarations are audited but do not alone reject the chain; every invalid, ambiguous, conflicting, forged, partial, wrong-job, wrong-source, or duplicate identity fails closed; handoff, topology, helper, graph-size, mutation, and restoration gates pass."
    )
    graph = protocol["execution_graph_contract"]
    graph["declaration"] = (
        "D_f=(boundary_id,job_id,normalized_source_path,lexical_qualified_function_name,normalized_function_source_sha256,semantic_stage,role,expected_inputs,expected_outputs)"
    )
    graph["matched_prefix"] = (
        "Each captured runtime prefix is independently enriched only when captured function-definition evidence resolves to exactly one executed-job static identity; the realized set is the exact intersection of those identities and valid declarations."
    )
    graph["unmatched_declaration_policy"] = (
        "A valid exact static declaration without a captured identity match is recorded controller-side as unmatched_declaration and is excluded from reviewer packages and realized counts. It does not alone invalidate the chain. Invalid, ambiguous, conflicting, forged, partial, wrong-job, wrong-source, duplicate-identity, duplicate-reference, or missing-endpoint evidence fails closed."
    )
    isolation = protocol["physical_isolation"]
    isolation.update(
        {
            "isolation_contract_path": "docs/workshops/neurips-2026-v2-1/ARM_ISOLATION_CONTRACT.md",
            "launch_policy_manifest_path": "docs/workshops/neurips-2026-v2-1/arm-isolation-launch-policy.json",
            "network": "The Bubblewrap-isolated Codex control plane retains provider transport; its exact permission profile denies network to model-executed commands. Authored and repaired Python use Bubblewrap with the network namespace unshared.",
            "codex_authentication": "copy only individually allowlisted authentication files into the private ephemeral Codex home; never mount the host Codex home",
        }
    )
    prompt_paths = {
        "prompt_authoring": "prompts/v2_1/fault_chain_authoring.md",
        "prompt_stabilization": "prompts/v2_1/fault_chain_stabilization.md",
        "prompt_review": "prompts/v2_1/fault_review.md",
        "prompt_repair": "prompts/v2_1/fault_repair.md",
        "schema_authoring": "schemas/v2_1/fault_chain_authoring.schema.json",
        "schema_stabilization": "schemas/v2_1/fault_chain_stabilization.schema.json",
        "schema_setup": "schemas/v2_1/fault_setup_record.schema.json",
        "schema_condition_manifest": "schemas/v2_1/fault_condition_manifest.schema.json",
        "schema_ground_truth": "schemas/v2_1/fault_ground_truth.schema.json",
        "schema_operation_event": "schemas/v2_1/fault_operation_event.schema.json",
        "schema_package_manifest": "schemas/v2_1/fault_package_manifest.schema.json",
        "schema_review_package": "schemas/v2_1/fault_review_package.schema.json",
        "schema_review_receipt": "schemas/v2_1/fault_review_receipt.schema.json",
        "schema_random_projection": "schemas/v2_1/random_projection_manifest.schema.json",
        "schema_repair_response": "schemas/v2_1/fault_repair_response.schema.json",
        "schema_instance": "schemas/v2_1/fault_instance.schema.json",
        "schema_isolation_gate": "schemas/v2_1/fault_isolation_gate.schema.json",
        "contract_arm_isolation": "docs/workshops/neurips-2026-v2-1/ARM_ISOLATION_CONTRACT.md",
        "contract_launch_policy": "docs/workshops/neurips-2026-v2-1/arm-isolation-launch-policy.json",
    }
    registry = protocol["namespace_registry"]
    for name, path in prompt_paths.items():
        registry["contracts"][name] = contract(path)
    for name in ("prompt_authoring", "prompt_stabilization", "prompt_review", "prompt_repair", "schema_authoring", "schema_stabilization", "schema_setup", "schema_condition_manifest", "schema_ground_truth", "schema_operation_event", "schema_package_manifest", "schema_review_package", "schema_review_receipt", "schema_random_projection", "schema_repair_response", "schema_instance", "schema_isolation_gate"):
        if name in protocol["model_and_prompts"]["prompt_contracts"]:
            protocol["model_and_prompts"]["prompt_contracts"][name] = contract(prompt_paths[name])
    protocol["predecessor_isolation"].update(
        {
            "namespace_rule": "all 2.1 prompt and schema access is confined to prompts/v2_1 and schemas/v2_1",
            "controller_state_rule": "controller writes are confined to outputs/fault-experiments-v2-1; every old output remains read-only excluded engineering evidence",
            "output_root": "outputs/fault-experiments-v2-1/",
            "v2_output_lifecycle_rule": "append-only N05 gate state; exact-hash resume only; immutable completed records are never overwritten",
        }
    )
    history = protocol["v2_design_history"]
    history["versions"].append(
        {
            "version": "2.1.0",
            "classification": "material pre-results redesign informed only by excluded N02-N04 engineering preflights",
            "status": "pre_results_frozen",
            "post_pilot": True,
            "reviewer_model_calls_observed_before_change": 0,
            "experimental_outcomes_observed_before_change": 0,
            "authority_path": n05_path,
            "authority_sha256": digest(n05_path),
        }
    )
    history["execution_authority"] = (
        "N05 standing conditional gate authority; Gate 0 has zero model calls and Gate 1 is independently signed before one-use model Phase A"
    )
    protocol["pilot_informed_disclosure"] = {
        "engineering_preflight_outputs_observed": True,
        "reported_experiment_results_observed": False,
        "reviewer_model_calls_observed": 0,
        "experimental_outcomes_observed": 0,
        "statement": "Protocol 2.1.0 was designed after excluded N02-N04 engineering runs. No reviewer calls or experimental outcomes existed. The redesign changes qualification and boundary realization before a new fresh model preflight.",
    }
    protocol["boundary_identity_v21"] = {
        "canonical_name": "one or more non-keyword Python identifiers joined by one dot, lexical source order only; module names, classes, and runtime-only <locals> are excluded",
        "transport_normalization": "remove only components exactly equal to <locals>, then require exact job, normalized source path, lexical name, and one AST definition",
        "static_identity": ["job_id", "normalized_source_path", "lexical_qualified_function_name", "normalized_function_source_sha256"],
        "realization": "independently enrich exact captured definition identities, intersect them with valid static declarations, group repeated prefixes only for the same identity, and retain every prefix and captured evidence ID",
        "unmatched_audit_visibility": "controller only; never reviewer evidence",
    }
    protocol["n05_program"] = {
        "ordered_gates": ["G0_engineering_and_design", "G1_independent_qualification", "G2_one_use_model_phase_a", "G3_two_subtrace_unscored_phase_b", "G4_12_instances_12_captures_96_packages", "G5_288_reviews_180_repairs", "G6_analysis_and_anonymous_replay"],
        "terminal_outcomes": ["completed_experiment_and_analysis", "experiment_incomplete_at_named_gate", "fail_closed_binding_or_preservation_error"],
        "no_overseer_reapproval_between_passing_gates": True,
        "post_gate_1_governed_changes": "terminal experiment_incomplete",
        "phase_b_subtraces": ["upstream target reruns both jobs", "downstream target reruns only downstream from branch-local hash-verified upstream artifacts"],
    }
    protocol.pop("boundary_identity_v2", None)
    protocol["tester_invariants"] = [
        (
            "every accepted chain has exactly two dependent executed jobs, at least eight declarations per job, at least 12 exact realized boundaries covering all six mandatory semantic stages, two exact handoffs, a join/aggregation, two expandable helpers, and passing hidden reference oracles"
            if item.startswith("every accepted chain has exactly two dependent executed jobs")
            else "valid unmatched declarations are controller-only audit records and do not alone invalidate an instance; boundary_health is absent from reviewer packages"
            if item.startswith("unmatched declarations invalidate")
            else item
        )
        for item in protocol["tester_invariants"]
    ]
    artifact_paths = [
        ("preflight_scenario", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/scenario.json"),
        ("preflight_corpus", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/corpus.json"),
        ("preflight_capabilities", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/capabilities.json"),
        ("preflight_oracles", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/oracles.json"),
        ("restricted_controller_plan", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/preflight/restricted/controller-plan.json"),
        ("qualification_fixture", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/qualification/fixture.json"),
        ("qualification_upstream", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/qualification/upstream.py"),
        ("qualification_downstream", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/qualification/downstream.py"),
        ("qualification_operators", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/qualification/operators.py"),
        ("qualification_negative_variants", "docs/experiments/2026-workshop-fault-localisation-v2-1/fixtures/qualification/negative-variants.json"),
        ("protocol_2_0_3_archive_manifest", "docs/workshops/neurips-2026-v2-1/archive/protocol-2.0.3/archive-manifest.json"),
        ("arm_isolation_contract", "docs/workshops/neurips-2026-v2-1/ARM_ISOLATION_CONTRACT.md"),
        ("arm_isolation_launch_policy", "docs/workshops/neurips-2026-v2-1/arm-isolation-launch-policy.json"),
    ]
    protocol["normative_artifacts"] = [
        {"id": name, **contract(path)} for name, path in artifact_paths
    ]
    canonical = deepcopy(protocol)
    canonical["integrity"].pop("content_hash", None)
    for item in canonical["normative_artifacts"]:
        item.pop("sha256", None)
    for name in ("contract_arm_isolation", "contract_launch_policy"):
        canonical["namespace_registry"]["contracts"][name].pop("sha256", None)
    protocol["integrity"]["content_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    encoded = json.dumps(protocol, indent=2, ensure_ascii=False) + "\n"
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    (TARGET_ROOT / "experiment-protocol.json").write_text(encoded)
    markdown = (
        "# Protocol 2.1.0 — execution-grounded fault localisation\n\n"
        "Protocol ID: `neurips-2026-workshop-fault-localisation-v2`  \n"
        "Version: `2.1.0`  \n"
        "Status: `pre_results_frozen`\n\n"
        "Protocol 2.1.0 was designed after excluded N02–N04 engineering runs. "
        "No reviewer calls or experimental outcomes existed. The redesign changes "
        "qualification and boundary realization before a fresh model preflight.\n\n"
        "The JSON block below is byte-identical to `experiment-protocol.json`.\n\n"
        "```json\n" + encoded + "```\n"
    )
    (TARGET_ROOT / "EXPERIMENT_PROTOCOL.md").write_text(markdown)


if __name__ == "__main__":
    main()
