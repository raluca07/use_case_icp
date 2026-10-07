"""N19A append-only three-job campaign-brief experiment."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from .n05_program import _parse_output, _pipeline_payload, derive_review_evidence, execute_pipeline_in_branch
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, stable_id, verify_record
from .records import GeneratedFile, GeneratedPipeline, jsonable


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-033")
SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-032")
TASK = Path("instructions_between_agent_types/developer/current/N19A_three_job_campaign_brief_visibility.email.md")
TASK_SHA256 = "sha256:5df00ac6dc124479a9bac9b0c72a81df148bca4a2ea03452fb72bfd01a8e23d9"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N19A_three_job_campaign_brief_visibility_authorization.json")
AUTHORITY_SHA256 = "sha256:80647668f7b350acf5f4e556918bec91736940f8da5034ddd17f6b19c8de027a"
SOURCE_FREEZE_SHA256 = "sha256:b1d8e808f1951904e6c2a1fdef9658cc50ae77a176a9e26f8d3778a827e3ef59"
SOURCE_PACKAGE_TREE_SHA256 = "sha256:eefae54e7d300da1351861719260318eb581c483813dc8afa8544fef4535de19"
PROMPT = Path("prompts/v2_2/n19a_three_job_review.md")
RESPONSE_SCHEMA = Path("schemas/v2_2/n19a_three_job_review.schema.json")
REQUIRED_SCHEMA = Path("schemas/v2_2/n19a_three_job_required_one.schema.json")
OUTPUT_SCHEMA = Path("schemas/v2_2/n19a_campaign_brief_output.schema.json")
JOB3_SOURCE = Path("src/use_case_icp/n19a_campaign_brief.py")
JOB3_ID = "job_campaign_brief_generation"
INSTANCES = ("n19a-three-job-upstream-fault", "n19a-three-job-clean-control")
SOURCE_INSTANCE = {
    "n19a-three-job-upstream-fault": "n16-nested-fault",
    "n19a-three-job-clean-control": "n16-clean-control",
}
MODES = ce.N18_MODES
SOURCE_SETTINGS = ce.SOURCE_SETTINGS
TASK_TEXT = (
    "Begin with the final campaign brief, trace backward through Job 3 and Job 2 "
    "into Job 1, assess all seven declared function boundaries, and return one "
    "earliest root-cause boundary or no suspect."
)


def _verify_authority(repo_root: Path) -> dict[str, str]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N19A authority input changed: {relative}")
    source = repo_root / SOURCE_ATTEMPT
    freeze = ce._read_json(source / "experiment-freeze.json")
    if ce._verified_self_hash(freeze, "freeze_sha256") != SOURCE_FREEZE_SHA256:
        raise ValueError("Attempt-032 logical freeze changed")
    if ce.sha256(ce._tree_hashes(source / "packages")) != SOURCE_PACKAGE_TREE_SHA256:
        raise ValueError("Attempt-032 package tree changed")
    if ce._read_json(source / "terminal-state.json").get("status") != "completed_experiment_and_analysis":
        raise ValueError("Attempt-032 is not complete")
    for relative, expected in ce.N15_PROTECTED_FILE_SHA256.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"protected boundary changed: {relative}")
    return {
        "source_freeze_sha256": SOURCE_FREEZE_SHA256,
        "source_package_tree_sha256": SOURCE_PACKAGE_TREE_SHA256,
        "task_sha256": TASK_SHA256,
        "authority_sha256": AUTHORITY_SHA256,
    }


def campaign_pipeline(repo_root: Path) -> GeneratedPipeline:
    source = (repo_root / JOB3_SOURCE).read_text(encoding="utf-8")
    pipeline = GeneratedPipeline(
        entry_file="generated/protocol_2_2/campaign_brief_generation.py",
        files=[GeneratedFile("generated/protocol_2_2/campaign_brief_generation.py", source)],
        review_boundaries=[{
            "boundary_id": "rb_n19a_campaign_brief",
            "function_name": "build_campaign_brief",
            "qualified_function_name": "build_campaign_brief",
            "source_path": "generated/protocol_2_2/campaign_brief_generation.py",
            "role": "Transform the inherited recommendation and ordered priorities into a campaign brief without changing their values.",
            "expected_inputs": ["complete ordered priorities array", "recommendation with top_need and decision"],
            "expected_outputs": ["campaign_brief", "metadata recording both consumed handoffs"],
            "semantic_stage": "campaign_brief_generation",
        }],
    )
    pipeline.validate()
    return pipeline


def _job3_input(source_capture: Mapping[str, Any]) -> dict[str, Any]:
    downstream = source_capture["jobs"]["job_downstream_coverage_priority"]["output"]
    return {
        "priorities": deepcopy(downstream["priorities"]),
        "recommendation": deepcopy(downstream["recommendation"]),
    }


def _check_job3_contract(value: Mapping[str, Any], runtime_input: Mapping[str, Any]) -> None:
    Draft202012Validator(ce._read_json(Path(__file__).resolve().parents[2] / OUTPUT_SCHEMA)).validate(dict(value))
    recommendation = runtime_input["recommendation"]
    brief = value["campaign_brief"]
    expected_points = [
        {key: row.get(key) for key in ("priority_rank", "record_id", "need", "capability_id", "coverage", "unsupported")}
        for row in runtime_input["priorities"][:3]
    ]
    if brief != {
        "audience_need": recommendation["top_need"],
        "recommended_action": recommendation["decision"],
        "message_strategy": "lead_with_unmet_need" if recommendation["decision"] == "prioritize" else "reinforce_supported_need",
        "primary_message": f"Focus campaign on: {recommendation['top_need']}",
        "supporting_points": expected_points,
    }:
        raise ValueError("Job 3 changed an inherited value or templating rule")
    if value["metadata"] != {"supporting_point_count": len(expected_points), "consumed_handoffs": ["priorities", "recommendation"]}:
        raise ValueError("Job 3 metadata changed")


def _combined_capture(
    instance_id: str,
    source_capture: Mapping[str, Any],
    pipeline: GeneratedPipeline,
    execution: Any,
    output: Mapping[str, Any],
    realization: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_input = _job3_input(source_capture)
    handoffs = deepcopy(list(source_capture["handoffs"]))
    for artifact in ("priorities", "recommendation"):
        digest = ce.sha256(runtime_input[artifact])
        handoffs.append({
            "artifact_name": artifact,
            "consumer_sha256": digest,
            "downstream_job_id": JOB3_ID,
            "etiq_runtime_edge": False,
            "handoff_id": f"handoff-{artifact}",
            "producer_sha256": digest,
            "provenance_type": "controller_recorded_exact_hash_handoff",
            "upstream_job_id": "job_downstream_coverage_priority",
        })
    jobs = deepcopy(dict(source_capture["jobs"]))
    jobs[JOB3_ID] = {
        "input": runtime_input,
        "output": deepcopy(dict(output)),
        "stdout": (execution.run_dir / "pipeline-stdout.log").read_text(encoding="utf-8"),
        "stderr": (execution.run_dir / "pipeline-stderr.log").read_text(encoding="utf-8"),
        "snapshot": jsonable(execution.snapshot),
        "realization": deepcopy(dict(realization)),
    }
    capture = {
        "schema_version": "1",
        "capture_id": stable_id("rerun-capture", ["n19a", instance_id], 0),
        "instance_id": instance_id,
        "job_ids": [*source_capture["job_ids"], JOB3_ID],
        "jobs": jobs,
        "handoffs": handoffs,
        "source_sha256": {**deepcopy(dict(source_capture["source_sha256"])), JOB3_ID: ce.sha256(_pipeline_payload(pipeline))},
        "canonical": True,
        "attempt_count": 1,
    }
    capture["capture_sha256"] = ce.sha256(capture)
    ce._verify_capture(capture)
    return capture


def _eligible_job3_child(catalogue: Mapping[str, Any]) -> list[str]:
    boundary = catalogue["jobs"][JOB3_ID]["realized_boundaries"][0]
    root = ce.canonical_stack(boundary["matched_prefix"])
    children = [
        list(ce.canonical_stack(prefix))
        for prefix in boundary["helper_prefixes"]
        if ce.canonical_stack(prefix)[:-1] == root
        and any(ce.canonical_stack(node.get("func_stack", [])) == ce.canonical_stack(prefix) for node in catalogue["jobs"][JOB3_ID]["nodes"])
    ]
    if not children:
        raise ValueError(f"Job 3 has no captured nested child: root={root!r} helpers={boundary['helper_prefixes']!r}")
    return children[0]


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (attempt_root or repo_root / ATTEMPT).resolve()
    if target != (repo_root / ATTEMPT).resolve():
        raise ValueError("N19A is authorized only for Attempt 033")
    _verify_authority(repo_root)
    existing = sorted((target / "captures").glob("*.json"))
    if existing:
        if len(existing) != 2:
            raise ValueError("Attempt 033 has a partial capture set")
        captures = {path.stem: ce._read_json(path) for path in existing}
        catalogues = {key: ce._read_json(target / "catalogues" / f"{key}.json") for key in captures}
        for value in captures.values(): ce._verify_capture(value)
        for value in catalogues.values(): ce.verify_catalogue(value)
        return {"captures": captures, "catalogues": catalogues, "reused": True}
    source_tree_before = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    pipeline = campaign_pipeline(repo_root)
    captures: dict[str, Any] = {}
    catalogues: dict[str, Any] = {}
    for index, instance_id in enumerate(INSTANCES):
        source_id = SOURCE_INSTANCE[instance_id]
        source_capture_path = repo_root / SOURCE_ATTEMPT / "captures" / f"{source_id}.json"
        source_capture = ce._read_json(source_capture_path)
        ce._verify_capture(source_capture)
        runtime_input = _job3_input(source_capture)
        branch = target / "capture-branches" / instance_id
        retry = 0
        while branch.exists():
            retry += 1
            branch = target / "capture-branches" / f"{instance_id}-retry-{retry:02d}"
        materialize_opaque_branch(branch, allowlist={}, manifest_identity={"purpose": "n19a-job3-capture", "instance": instance_id})
        copy_etiq_worker_runtime(branch, repo_root / "src")
        execution = execute_pipeline_in_branch(
            branch, repo_root=repo_root, job_id=JOB3_ID, pipeline=pipeline,
            runtime_input=runtime_input, run_index=index, stage=f"n19a-{instance_id}",
        )
        output = _parse_output(execution)
        _check_job3_contract(output, runtime_input)
        evidence = derive_review_evidence(
            {"executions": {JOB3_ID: execution}}, jobs={JOB3_ID: pipeline}, scenario={"protocol_version": "2.2.0"}, simple_boundary_matching=True,
        )
        realized = evidence["realizations"][JOB3_ID]
        boundary = realized["realized_boundaries"][0]
        root = ce.canonical_stack(boundary["matched_prefix"])
        boundary["helper_prefixes"] = [
            list(stack)
            for stack in sorted({ce.canonical_stack(node.func_stack) for node in execution.snapshot.nodes})
            if len(stack) > len(root) and stack[:len(root)] == root
        ]
        capture = _combined_capture(instance_id, source_capture, pipeline, execution, output, realized)
        catalogue = ce.build_disclosure_catalogue(capture)
        ce.verify_catalogue(catalogue)
        child = _eligible_job3_child(catalogue)
        if len(catalogue["job_order"]) != 3 or sum(len(job["realized_boundaries"]) for job in catalogue["jobs"].values()) != 7 or len(catalogue["handoffs"]) != 4:
            raise ValueError("N19A capture lacks three jobs, four handoffs, or seven boundaries")
        source_bundle = ce._read_json(repo_root / SOURCE_ATTEMPT / "source-bundles" / f"{source_id}.json")["source_bundle"]
        source_bundle = [*source_bundle, {"job_id": JOB3_ID, "files": [{"path": pipeline.files[0].path, "content": pipeline.files[0].content}]}]
        old_instance = ce._read_json(repo_root / SOURCE_ATTEMPT / "instances" / f"{source_id}.json")
        original_need = source_capture["jobs"]["job_upstream_demand_provenance"]["input"]["corpus"][0]["need"]
        actual_need = output["campaign_brief"]["audience_need"]
        propagated = actual_need == runtime_input["recommendation"]["top_need"] and output["campaign_brief"]["primary_message"] == f"Focus campaign on: {actual_need}"
        oracle = {
            "inherited_attempt_032_oracle": deepcopy(old_instance["oracle"]),
            "job3_schema_and_contract_passed": True,
            "fault_value_propagated_verbatim": propagated,
            "expected_need": original_need,
            "actual_campaign_need": actual_need,
            "end_to_end_expected_need_passed": actual_need == original_need,
        }
        if not propagated or ((source_id == "n16-clean-control") != oracle["end_to_end_expected_need_passed"]):
            raise ValueError("N19A clean/fault end-to-end qualification changed")
        mutation = deepcopy(old_instance.get("mutation"))
        record = {
            "schema_version": "n19a-three-job-instance-1", "instance_id": instance_id,
            "source_attempt": "attempt-032", "source_instance_id": source_id,
            "designation": "nested_fault" if mutation else "matched_clean_control",
            "reused_capture_file_sha256": ce.sha256(source_capture_path.read_bytes()),
            "reused_job_hashes": {job_id: ce.sha256(source_capture["jobs"][job_id]) for job_id in source_capture["job_ids"]},
            "capture_sha256": capture["capture_sha256"], "source_sha256": deepcopy(capture["source_sha256"]),
            "mutation": mutation, "oracle": oracle, "job3_nested_child_prefix": child,
        }
        record["instance_sha256"] = ce.sha256(record)
        ce._write_immutable(target / "captures" / f"{instance_id}.json", capture)
        ce._write_immutable(target / "catalogues" / f"{instance_id}.json", catalogue)
        ce._write_immutable(target / "source-bundles" / f"{instance_id}.json", {"source_bundle": source_bundle})
        ce._write_immutable(target / "instances" / f"{instance_id}.json", record)
        captures[instance_id] = capture
        catalogues[instance_id] = catalogue
    mutation_source = repo_root / SOURCE_ATTEMPT / "qualification/n16-nested-mutation.json"
    ce._write_immutable(target / "qualification/n16-nested-mutation.json", ce._read_json(mutation_source))
    job3_record = {"path": JOB3_SOURCE.as_posix(), "exact_file_sha256": ce.sha256((repo_root / JOB3_SOURCE).read_bytes()), "pipeline_sha256": ce.sha256(_pipeline_payload(pipeline))}
    job3_record["record_sha256"] = ce.sha256(job3_record)
    ce._write_immutable(target / "qualification/n19a-job3-source.json", job3_record)
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != source_tree_before:
        raise RuntimeError("Attempt 032 changed during Job-3 capture")
    return {"captures": captures, "catalogues": catalogues, "reused": False}


def _source_common(repo_root: Path, source_id: str) -> dict[str, Any]:
    manifests = [ce._read_json(path) for path in (repo_root / SOURCE_ATTEMPT / "controller-manifests").glob("*.json")]
    manifest = next(value for value in manifests if value["controller_condition"] == {
        "instance_id": source_id, "evidence_mode": "current_run", "source_setting": "source_absent",
        "branch_id": value["controller_condition"]["branch_id"],
    })
    return deepcopy(ce._read_json(repo_root / SOURCE_ATTEMPT / manifest["reviewer_package_path"])["common_base"])


def _common_base(repo_root: Path, catalogue: Mapping[str, Any]) -> dict[str, Any]:
    source_id = SOURCE_INSTANCE[str(catalogue["instance_id"])]
    common = _source_common(repo_root, source_id)
    order = list(map(str, catalogue["job_order"]))
    bindings = ce._n16_binding_rows(catalogue)
    binding_by_pair = {(x["job_id"], x["function_name"]): x for x in bindings}
    desired = [
        (JOB3_ID, "build_campaign_brief"),
        ("job_downstream_coverage_priority", "synthesize"),
        ("job_downstream_coverage_priority", "prioritize"),
        ("job_downstream_coverage_priority", "map_coverage"),
        ("job_upstream_demand_provenance", "assemble_provenance"),
        ("job_upstream_demand_provenance", "normalize"),
        ("job_upstream_demand_provenance", "select_demand"),
    ]
    declarations = []
    for job_id, function in desired:
        boundary = next(x for x in catalogue["jobs"][job_id]["realized_boundaries"] if x["function_name"] == function)
        binding = binding_by_pair[(job_id, function)]
        declarations.append({
            "boundary_id": binding["reviewer_boundary_id"], "job_id": job_id,
            "job_position": binding["job_position"], "function_name": function,
            "role": boundary["role"], "expected_inputs": deepcopy(boundary["expected_inputs"]),
            "expected_outputs": deepcopy(boundary["expected_outputs"]),
        })
    common.update({
        "review_task": TASK_TEXT,
        "behavioural_criteria": [
            "Treat the supplied corpus and capabilities as stipulated test inputs.",
            "Select every qualifying demand row while preserving its need and provenance fields.",
            "Preserve the exact needs and evidence_sources handoffs from Job 1 to Job 2.",
            "Map coverage and prioritize without changing stipulated need text.",
            "Construct the recommendation from the first ranked priority.",
            "Preserve exact priorities and recommendation handoffs from Job 2 to Job 3.",
            "Build the campaign brief by verbatim copying top_need and decision and the declared first-three priority fields.",
        ],
        "top_level": {"input": deepcopy(catalogue["jobs"][order[0]]["input"]), "final_output": deepcopy(catalogue["jobs"][JOB3_ID]["output"])},
        "assigned_job": {"job_id": JOB3_ID, "observation_point": "final_campaign_brief", "input": deepcopy(catalogue["jobs"][JOB3_ID]["input"]), "output": deepcopy(catalogue["jobs"][JOB3_ID]["output"]), "stdout": catalogue["jobs"][JOB3_ID]["stdout"], "stderr": catalogue["jobs"][JOB3_ID]["stderr"]},
        "semantic_declarations": declarations,
        "exact_handoffs": deepcopy(list(catalogue["handoffs"])),
        "job_executions": [{"job_id": job_id, "job_position": f"job_{order.index(job_id)+1}", "input": deepcopy(catalogue["jobs"][job_id]["input"]), "output": deepcopy(catalogue["jobs"][job_id]["output"]), "stdout": catalogue["jobs"][job_id]["stdout"], "stderr": catalogue["jobs"][job_id]["stderr"]} for job_id in reversed(order)],
        "ordered_job_topology": [{"job_id": job_id, "position": f"job_{index+1}", "observation_point": job_id == JOB3_ID} for index, job_id in enumerate(order)],
        "review_scope_sequence": [
            {"kind": "job_boundaries", "job_id": JOB3_ID, "boundary_ids": [declarations[0]["boundary_id"]]},
            {"kind": "handoffs", "handoffs": deepcopy(list(catalogue["handoffs"])[2:])},
            {"kind": "job_boundaries", "job_id": order[1], "boundary_ids": [x["boundary_id"] for x in declarations[1:4]]},
            {"kind": "handoffs", "handoffs": deepcopy(list(catalogue["handoffs"])[:2])},
            {"kind": "job_boundaries", "job_id": order[0], "boundary_ids": [x["boundary_id"] for x in declarations[4:]]},
        ],
    })
    common["section"] = {"section_id": "sec-n19a-three-job", "section_index": 0, "organization": {"kind": "downstream_first_three_job_boundaries"}, "assigned_boundary_ids": [x["boundary_id"] for x in declarations], "context_boundary_ids": []}
    return common


def _empty_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    value = {"job_evidence_order": list(reversed(catalogue["job_order"])), "anchors": [], "nodes": [], "relationships": [], "handoffs": [], "collapsed_child_groups": [], "disclosed_child_groups": [], "collapsed_children": [], "visible_evidence_by_boundary": {}}
    value["projection_sha256"] = ce.sha256(value)
    return value


def _compact_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    value = ce.n16_compact_projection(catalogue)
    value["handoffs"] = []
    value.pop("projection_sha256", None)
    value["projection_sha256"] = ce.sha256(value)
    return value


def build_review_package(repo_root: Path, catalogue: Mapping[str, Any], mode: str, source_setting: str, source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    common = _common_base(repo_root, catalogue)
    adaptive = mode in {"adaptive_voluntary", "adaptive_required_one"}
    package: dict[str, Any] = {
        "schema_version": "corrected-four-instance-package-2", "common_base": common,
        "available_operations": ["helper_expansion"] if adaptive else [],
        "action_contract": {"exactly_one_next_action": True, "permitted_actions": [*(["helper_expansion"] if adaptive else []), "finalize"], "first_action_must_expand_one_model_selected_child_group": mode == "adaptive_required_one", "maximum_completed_follow_ups": 3, "batch_actions_prohibited": True},
        "prior_task_records": [],
    }
    if mode != "current_run":
        package["graph_review_instructions"] = {"framing": "Runtime execution evidence is supplied in a graph envelope.", "anchors_are_compact": mode != "etiq_empty", "expansion_is_model_selected": adaptive}
        package["runtime_evidence"] = _empty_projection(catalogue) if mode == "etiq_empty" else _compact_projection(catalogue)
    refs = {x["boundary_id"] for x in common["semantic_declarations"]} | {str(x["handoff_id"]) for x in common["exact_handoffs"]}
    graph = package.get("runtime_evidence", {})
    refs |= {str(x["anchor_id"]) for x in graph.get("anchors", [])} | {str(x["child_group_id"]) for x in graph.get("collapsed_child_groups", [])}
    package["allowed_evidence_refs"] = sorted(refs)
    if source_setting == "source_present": package["source_bundle"] = deepcopy(source_bundle)
    ce._validate_schema(package, ce.PACKAGE_SCHEMA)
    return package


def schedule() -> dict[str, Any]:
    packages = [{"instance_id": instance, "evidence_mode": mode, "source_setting": source, "branch_id": f"brn-{ce.sha256(['n19a', instance, mode, source])[7:23]}"} for instance in INSTANCES for mode in MODES for source in SOURCE_SETTINGS]
    by_key = {(x["instance_id"], x["evidence_mode"], x["source_setting"]): x for x in packages}
    reviews = []
    block = 0
    for repetition in range(1, 4):
        sources = SOURCE_SETTINGS if repetition % 2 else tuple(reversed(SOURCE_SETTINGS))
        for source_index, source in enumerate(sources):
            instances = INSTANCES if (repetition + source_index) % 2 else tuple(reversed(INSTANCES))
            for instance in instances:
                rotation = block % len(MODES)
                for position, mode in enumerate(MODES[rotation:] + MODES[:rotation], 1):
                    condition = by_key[(instance, mode, source)]
                    reviews.append({**condition, "repetition": repetition, "trial_id": f"trial-{ce.sha256(['n19a', condition['branch_id'], repetition])[7:23]}", "schedule_position": len(reviews)+1, "local_block": block+1, "mode_position": position})
                block += 1
    if (len(packages), len(reviews)) != (20, 60): raise AssertionError("N19A matrix changed")
    return {"packages": packages, "review_trials": reviews, "repair_traces": []}


def qualify_packages(records: list[Mapping[str, Any]], catalogues: Mapping[str, Mapping[str, Any]], design: Mapping[str, Any]) -> dict[str, Any]:
    if (len(records), len(design["review_trials"]), len(design["repair_traces"])) != (20, 60, 0): raise ValueError("N19A count invariant failed")
    by = {(r["controller_condition"]["instance_id"], r["controller_condition"]["evidence_mode"], r["controller_condition"]["source_setting"]): r["reviewer_package"] for r in records}
    checks = 0
    for instance in INSTANCES:
        for source in SOURCE_SETTINGS:
            pair = {mode: by[(instance, mode, source)] for mode in MODES}
            if len({ce.canonical_json(x["common_base"]) for x in pair.values()}) != 1: raise ValueError("common base differs by arm")
            if "runtime_evidence" in pair["current_run"] or "graph_review_instructions" in pair["current_run"]: raise ValueError("Current contains graph framing")
            empty = pair["etiq_empty"]["runtime_evidence"]
            if any(empty.get(key) for key in ("anchors", "nodes", "relationships", "handoffs", "collapsed_child_groups")): raise ValueError("Etiq Empty is not empty")
            fixed = pair["compact_fixed"]["runtime_evidence"]
            if len(fixed["anchors"]) != 7 or fixed["nodes"] or fixed["relationships"] or fixed["handoffs"]: raise ValueError("compact evidence is not seven anchors")
            if len({ce.canonical_json(pair[m]["runtime_evidence"]) for m in ("compact_fixed", "adaptive_voluntary", "adaptive_required_one")}) != 1: raise ValueError("Fixed/Adaptive initial evidence differs")
            checks += 4
        for mode in MODES:
            present, absent = by[(instance, mode, "source_present")], by[(instance, mode, "source_absent")]
            if ce._differing_top_level_keys(present, absent) != {"source_bundle"}: raise ValueError("source pair differs outside source bundle")
            checks += 1
    for record in records:
        package = record["reviewer_package"]
        if [x["job_id"] for x in package["common_base"]["job_executions"]] != [JOB3_ID, "job_downstream_coverage_priority", "job_upstream_demand_provenance"]: raise ValueError("review is not downstream-first")
        if len(package["common_base"]["exact_handoffs"]) != 4 or len(package["common_base"]["section"]["assigned_boundary_ids"]) != 7: raise ValueError("common evidence scope incomplete")
        visible = ce.canonical_json(ce.render_provider_request(package)).decode()
        if any(f'"{key}"' in visible for key in ("mutation", "oracle", "designation", "truth", "instance_id", "repetition")): raise ValueError("condition or truth leakage")
    return {"status": "passed", "model_calls": 0, "capture_count": 2, "catalogue_count": 2, "package_count": 20, "review_count": 60, "repair_count": 0, "comparison_count": checks}


def build_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve(); target = (attempt_root or repo_root / ATTEMPT).resolve()
    prepared = prepare_attempt(repo_root, target)
    design = schedule(); records = []
    bundles = {x: ce._read_json(target / "source-bundles" / f"{x}.json")["source_bundle"] for x in INSTANCES}
    for condition in design["packages"]:
        catalogue = prepared["catalogues"][condition["instance_id"]]
        package = build_review_package(repo_root, catalogue, condition["evidence_mode"], condition["source_setting"], bundles[condition["instance_id"]])
        record = {"schema_version": "n19a-frozen-package-1", "controller_condition": deepcopy(condition), "source_capture_sha256": catalogue["source_capture_sha256"], "catalogue_sha256": catalogue["catalogue_sha256"], "reviewer_package": package}
        record["package_sha256"] = ce.sha256(record); records.append(record)
    return {**prepared, "packages": records, "schedule": design, "qualification": qualify_packages(records, prepared["catalogues"], design)}


def _load_frozen(attempt_root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    catalogues = {path.stem: ce._read_json(path) for path in sorted((attempt_root / "catalogues").glob("*.json"))}
    packages: dict[str, Any] = {}
    records = []
    for path in sorted((attempt_root / "controller-manifests").glob("*.json")):
        manifest = ce._read_json(path)
        package = ce._read_json(attempt_root / manifest["reviewer_package_path"])
        if ce.sha256(package) != manifest["reviewer_package_sha256"]: raise ValueError("reviewer package hash mismatch")
        record = {**manifest, "reviewer_package": package}
        unsigned = deepcopy(record); observed = unsigned.pop("package_sha256")
        unsigned.pop("reviewer_package_path"); unsigned.pop("reviewer_package_sha256")
        if ce.sha256(unsigned) != observed: raise ValueError("package record hash mismatch")
        packages[str(manifest["controller_condition"]["branch_id"])] = record
        records.append(record)
    return catalogues, packages, records


def freeze_attempt(repo_root: Path, attempt_root: Path | None = None) -> Path:
    repo_root = repo_root.resolve(); target = (attempt_root or repo_root / ATTEMPT).resolve()
    if (target / "experiment-freeze.json").exists(): raise ValueError("Attempt 033 is already frozen")
    if any((target / name).exists() for name in ("packages", "controller-manifests", "reviews")): raise ValueError("Attempt 033 contains pre-freeze scientific material")
    source_tree = ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT))
    built = build_attempt(repo_root, target)
    for record in built["packages"]:
        branch = record["controller_condition"]["branch_id"]
        package_path = target / "packages" / branch / "reviewer-package.json"
        ce._write_immutable(package_path, record["reviewer_package"])
        manifest = {key: deepcopy(value) for key, value in record.items() if key != "reviewer_package"}
        manifest.update({"reviewer_package_path": f"packages/{branch}/reviewer-package.json", "reviewer_package_sha256": ce.sha256(record["reviewer_package"])})
        ce._write_immutable(target / "controller-manifests" / f"{branch}.json", manifest)
    ce._write_immutable(target / "review-design.json", {"review_trials": built["schedule"]["review_trials"]})
    ce._write_immutable(target / "repair-design.json", {"repair_traces": []})
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != source_tree: raise RuntimeError("Attempt 032 changed during freeze")
    code_paths = (Path("src/use_case_icp/n19a_experiment.py"), JOB3_SOURCE, Path("src/use_case_icp/corrected_experiment.py"), Path("src/use_case_icp/__main__.py"), Path("tests/test_corrected_experiment.py"), PROMPT, RESPONSE_SCHEMA, REQUIRED_SCHEMA, OUTPUT_SCHEMA)
    freeze = {
        "schema_version": "n19a-three-job-campaign-brief-freeze-1", "status": "frozen_before_first_experimental_review", "attempt": "attempt-033", "source_attempt": "attempt-032",
        "source_freeze_sha256": SOURCE_FREEZE_SHA256, "source_package_tree_sha256": SOURCE_PACKAGE_TREE_SHA256,
        "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256}, "task": {"path": TASK.as_posix(), "sha256": TASK_SHA256},
        "protected_boundaries": deepcopy(ce.N15_PROTECTED_FILE_SHA256), "authority_bindings": _verify_authority(repo_root),
        "code_hashes": {path.as_posix(): ce.sha256((repo_root / path).read_bytes()) for path in code_paths},
        "preserved_attempt_tree_hashes": {"attempt-032": source_tree},
        "reused_job_hashes": {instance: ce._read_json(target / "instances" / f"{instance}.json")["reused_job_hashes"] for instance in INSTANCES},
        "job3_source": ce._read_json(target / "qualification/n19a-job3-source.json"),
        "capture_hashes": {key: value["capture_sha256"] for key, value in built["captures"].items()},
        "capture_file_hashes": {key: ce.sha256((target / "captures" / f"{key}.json").read_bytes()) for key in INSTANCES},
        "catalogue_hashes": {key: value["catalogue_sha256"] for key, value in built["catalogues"].items()},
        "package_hashes": sorted(x["package_sha256"] for x in built["packages"]),
        "package_tree_sha256": ce.sha256(ce._tree_hashes(target / "packages")),
        "common_base_hashes": sorted({ce.sha256(x["reviewer_package"]["common_base"]) for x in built["packages"]}),
        "review_design_sha256": ce.sha256(built["schedule"]["review_trials"]), "repair_design_sha256": ce.sha256([]),
        "expected_counts": {"captures": 2, "catalogues": 2, "packages": 20, "reviews": 60, "repairs": 0, "provider_calls_min": 72, "provider_calls_max": 132},
        "qualification": built["qualification"], "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT, "experimental_review_records_at_freeze": 0,
    }
    freeze["freeze_sha256"] = ce.sha256(freeze)
    path = target / "experiment-freeze.json"; ce._write_immutable(path, freeze); return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve(); target = (attempt_root or repo_root / ATTEMPT).resolve(); _verify_authority(repo_root)
    freeze = ce._read_json(target / "experiment-freeze.json"); observed = ce._verified_self_hash(freeze, "freeze_sha256")
    for relative, expected in freeze["code_hashes"].items():
        current = ce.sha256((repo_root / relative).read_bytes())
        if current != expected:
            correction_path = target / "qualification/n19a-post-live-validator-correction.json"
            correction = ce._read_json(correction_path) if correction_path.exists() else {}
            binding = correction.get("code_hash_binding", {}).get(relative, {})
            if binding != {"before": expected, "after": current}:
                raise ValueError(f"N19A frozen code changed: {relative}")
    for relative, expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected: raise ValueError(f"N19A protected boundary changed: {relative}")
    if ce.sha256(ce._tree_hashes(repo_root / SOURCE_ATTEMPT)) != freeze["preserved_attempt_tree_hashes"]["attempt-032"]: raise ValueError("Attempt 032 changed after freeze")
    catalogues, _, records = _load_frozen(target)
    design = {"packages": [deepcopy(x["controller_condition"]) for x in records], "review_trials": ce._read_json(target / "review-design.json")["review_trials"], "repair_traces": ce._read_json(target / "repair-design.json")["repair_traces"]}
    qualification = qualify_packages(records, catalogues, design)
    if sorted(x["package_sha256"] for x in records) != freeze["package_hashes"] or ce.sha256(design["review_trials"]) != freeze["review_design_sha256"]: raise ValueError("N19A package or schedule changed")
    return {"status": "verified", "freeze_sha256": observed, "qualification": qualification, "capture_count": 2, "catalogue_count": 2, "package_count": 20, "review_count": 60, "repair_count": 0}


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path = attempt_root / "live-consumption.json"
    if path.exists(): ce._verified_self_hash(ce._read_json(path), "consumption_sha256"); return path
    if list((attempt_root / "reviews").glob("*.json")): raise ValueError("review exists before N19A live consumption")
    verified = verify_frozen_attempt(repo_root, attempt_root)
    record = {"schema_version": "n19a-live-consumption-1", "status": "live_authority_consumed_before_first_provider_call", "authority": {"path": AUTHORITY.as_posix(), "sha256": AUTHORITY_SHA256}, "freeze_sha256": verified["freeze_sha256"], "package_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "packages")), "controller_manifest_tree_sha256": ce.sha256(ce._tree_hashes(attempt_root / "controller-manifests")), "review_design_file_sha256": ce.sha256((attempt_root / "review-design.json").read_bytes()), "protected_file_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256), "model": ce.PROVIDER_MODEL, "reasoning_effort": ce.PROVIDER_REASONING_EFFORT, "expected_counts": {"packages": 20, "reviews": 60, "repairs": 0, "provider_calls_min": 72, "provider_calls_max": 132}}
    record["consumption_sha256"] = ce.sha256(record); ce._write_immutable(path, record); return path


def validate_response(catalogue: Mapping[str, Any], package: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    scientific_response = {"reviews": deepcopy(response.get("reviews")), "next_action": deepcopy(response.get("next_action"))}
    Draft202012Validator(ce._read_json(Path(__file__).resolve().parents[2] / RESPONSE_SCHEMA)).validate(scientific_response)
    assigned = list(package["common_base"]["section"]["assigned_boundary_ids"])
    reviewed = [str(x["unit_id"]) for x in response["reviews"]]
    if sorted(reviewed) != sorted(assigned) or len(reviewed) != len(set(reviewed)): raise ValueError("response must judge all seven boundaries exactly once")
    suspects = []
    for review in response["reviews"]:
        refs = [*map(str, review["evidence_refs"]), *map(str, review["suspect_node_refs"])]
        refs += [str(ref) for criterion in review["criteria_outcomes"] for ref in criterion["evidence_refs"]]
        for ref in refs: ce.validate_visible_reference(package, ref)
        if review["decision"] in {"failed", "suspect"}: suspects.append(str(review["unit_id"]))
    if len(suspects) > 1: raise ValueError("response selected more than one root cause")
    selected = suspects[0] if suspects else None
    binding = next((x for x in ce._n16_binding_rows(catalogue) if x["reviewer_boundary_id"] == selected), None)
    return {"valid": True, "receipt": {"reviews": deepcopy(response["reviews"]), "next_action": deepcopy(response["next_action"])}, "suspect_boundary_ids": suspects, "selected_suspect_boundary_id": selected, "selected_job_id": binding["job_id"] if binding else None, "selected_job_position": binding["job_position"] if binding else None, "selected_function_name": binding["function_name"] if binding else None}


def _preserved_initial_response(attempt_root: Path, trial_id: str) -> dict[str, Any] | None:
    matches = []
    for path in sorted((attempt_root / "ledger/call-attempt").glob("*.json")):
        record = ce._read_json(path); payload = record.get("payload", {})
        if payload.get("parent_id") == trial_id and int(payload.get("attempt_index", -1)) == 0 and payload.get("status") == "completed":
            matches.append((path, record))
    if not matches: return None
    if len(matches) != 1: raise ValueError("multiple preserved initial calls exist for one N19A trial")
    path, record = matches[0]; payload = record["payload"]; result = payload["result"]
    response = deepcopy(result["response"])
    response.update({"usage": deepcopy(result["usage"]), "request_sha256": result.get("response_sha256"), "ledger_request_sha256": payload["request_sha256"], "call_ids": [payload["call_id"]], "retry_lineage": [{"call_id": payload["call_id"], "attempt_index": 0, "status": "completed", "failure_classification": None, "record": {"path": f"call-attempt/{path.name}", "sha256": ce.sha256(path.read_bytes())}}], "attempt_count": 1})
    return response


def score(instance_record: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    mutation = instance_record.get("mutation")
    if not mutation:
        detected = bool(validation["suspect_boundary_ids"])
        return {"designation": "matched_clean_control", "fault_detected": detected, "false_positive": detected, "correct_job_localisation": False, "exact_boundary_localisation": False, "truth_job_id": None, "truth_reviewer_boundary_id": None, "truth_function_name": None}
    truth_id = "bnd-8e4e0db29e4a3223"
    return {"designation": "nested_fault", "fault_detected": bool(validation["suspect_boundary_ids"]), "false_positive": False, "correct_job_localisation": validation["selected_job_id"] == "job_upstream_demand_provenance", "exact_boundary_localisation": validation["selected_suspect_boundary_id"] == truth_id, "truth_job_id": "job_upstream_demand_provenance", "truth_reviewer_boundary_id": truth_id, "truth_function_name": "select_demand"}


def _provider_review(repo_root: Path, attempt_root: Path, request: Mapping[str, Any], controller_parent_id: str, required_initial: bool = False) -> dict[str, Any]:
    return ce._provider_call(repo_root, attempt_root, kind="review", model_request=request, controller_parent_id=controller_parent_id, review_prompt=PROMPT, review_schema=REQUIRED_SCHEMA if required_initial else RESPONSE_SCHEMA)


def _exposure(runtime: Mapping[str, Any]) -> dict[str, bool]:
    nodes = runtime.get("nodes", [])
    return {
        "source_visible": any(node.get("source") is not None or node.get("source_code") is not None for node in nodes),
        "values_visible": any(node.get("artifact_content") is not None or node.get("value") is not None for node in nodes),
        "artifacts_visible": any(node.get("artifact_content") is not None or node.get("artifact_kind") is not None for node in nodes),
    }


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    fault = [x for x in rows if x["designation"] == "nested_fault"]
    control = [x for x in rows if x["designation"] == "matched_clean_control"]
    calls = [call for row in rows for call in row["raw_calls"]]
    jobs: dict[str, int] = {}; boundaries: dict[str, int] = {}
    for row in rows:
        job = str(row.get("final_selected_job_id") or "no_suspect"); jobs[job] = jobs.get(job, 0) + 1
        boundary = str(row.get("final_selected_boundary_id") or "no_suspect"); boundaries[boundary] = boundaries.get(boundary, 0) + 1
    return {
        "reviews": len(rows), "provider_calls": len(calls),
        "fault_detection": {"numerator": sum(x["fault_detected"] for x in fault), "denominator": len(fault)},
        "correct_upstream_job": {"numerator": sum(x["correct_job_localisation"] for x in fault), "denominator": len(fault)},
        "exact_select_demand": {"numerator": sum(x["exact_boundary_localisation"] for x in fault), "denominator": len(fault)},
        "control_false_positives": {"numerator": sum(x["false_positive"] for x in control), "denominator": len(control)},
        "selected_job_distribution": jobs, "selected_boundary_distribution": boundaries,
        "expanded_sessions": sum(x["completed_expansion_count"] > 0 for x in rows),
        "disclosed_nodes": sum(x["disclosed_node_count"] for x in rows), "disclosed_relationships": sum(x["disclosed_relationship_count"] for x in rows),
        "source_exposed_sessions": sum(x["source_visible"] for x in rows), "value_exposed_sessions": sum(x["values_visible"] for x in rows), "artifact_exposed_sessions": sum(x["artifacts_visible"] for x in rows),
        "artifact_operations": sum(x["artifact_operation_count"] for x in rows),
        "input_tokens": sum(int(x.get("input_tokens") or 0) for x in calls), "cached_input_tokens": sum(int(x.get("cached_input_tokens") or 0) for x in calls), "output_tokens": sum(int(x.get("output_tokens") or 0) for x in calls),
    }


def _rate(summary: Mapping[str, Any], key: str) -> float:
    value = summary[key]; return value["numerator"] / value["denominator"] if value["denominator"] else 0.0


def write_analysis(repo_root: Path, attempt_root: Path, reviews: Mapping[tuple[str, int], Mapping[str, Any]]) -> Path:
    rows = []; raw_calls = []
    for record in reviews.values():
        trial = record["controller_trial"]; calls = []
        for index, call in enumerate(record["usage"].get("calls", []), 1):
            tagged = {"trial_id": trial["trial_id"], "call_index": index, **deepcopy(call)}; calls.append(tagged); raw_calls.append(tagged)
        rows.append({**deepcopy(trial), "designation": record["designation"], "fault_detected": bool(record["fault_detected"]), "false_positive": bool(record["false_positive"]), "correct_job_localisation": bool(record["correct_job_localisation"]), "exact_boundary_localisation": bool(record["exact_boundary_localisation"]), "pre_expansion_selected_boundary_id": record.get("pre_expansion_selected_boundary_id"), "pre_expansion_selected_job_id": record.get("pre_expansion_selected_job_id"), "final_selected_boundary_id": record.get("selected_suspect_boundary_id"), "final_selected_job_id": record.get("selected_job_id"), "completed_expansion_count": record["completed_expansion_count"], "expanded_child_group_ids": deepcopy(record["expanded_child_group_ids"]), "selected_expansions": deepcopy(record["selected_expansions"]), "disclosed_node_count": record["disclosed_node_count"], "disclosed_relationship_count": record["disclosed_relationship_count"], "source_visible": record["source_visible"], "values_visible": record["values_visible"], "artifacts_visible": record["artifacts_visible"], "artifact_operation_count": record["artifact_operation_count"], "diagnosis_changed_after_expansion": record.get("pre_expansion_selected_boundary_id") != record.get("selected_suspect_boundary_id") if record["completed_expansion_count"] else False, "operation_events": deepcopy(record["operation_events"]), "raw_calls": calls})
    arm_source = {f"{mode}__{source}": _summary([x for x in rows if x["evidence_mode"] == mode and x["source_setting"] == source]) for source in ("source_absent", "source_present") for mode in MODES}
    source_analysis = ce._read_json(repo_root / SOURCE_ATTEMPT / "analysis/summary.json")
    comparison = []
    for source in ("source_absent", "source_present"):
        for mode in MODES:
            current = arm_source[f"{mode}__{source}"]; prior = source_analysis["arm_source_summaries"][f"{mode}__{source}"]
            comparison.append({"evidence_mode": mode, "source_setting": source, "attempt_032": {key: deepcopy(prior[key]) for key in ("fault_detection", "correct_upstream_job", "exact_select_demand")}, "attempt_033": {key: deepcopy(current[key]) for key in ("fault_detection", "correct_upstream_job", "exact_select_demand")}, "rate_difference_attempt_033_minus_032": {key: _rate(current, key) - _rate(prior, key) for key in ("fault_detection", "correct_upstream_job", "exact_select_demand")}})
    selected_jobs: dict[str, int] = {}; selected_boundaries: dict[str, int] = {}
    for row in rows:
        job = str(row["final_selected_job_id"] or "no_suspect"); selected_jobs[job] = selected_jobs.get(job, 0)+1
        boundary = str(row["final_selected_boundary_id"] or "no_suspect"); selected_boundaries[boundary] = selected_boundaries.get(boundary, 0)+1
    analysis = {
        "schema_version": "n19a-three-job-campaign-brief-analysis-1", "scope_limitation": "One faulty pipeline and one matched clean control, with three fresh reviewer repetitions per package; this is descriptive and not a population-significance claim.", "primary_population": "source_absent", "review_count": len(rows), "repair_trace_count": 0,
        "overall": _summary(rows), "arm_source_summaries": arm_source,
        "adaptive_pre_post": [deepcopy(x) for x in rows if x["evidence_mode"] in {"adaptive_voluntary", "adaptive_required_one"}],
        "voluntary_expansion_uptake": {"numerator": sum(x["completed_expansion_count"] > 0 for x in rows if x["evidence_mode"] == "adaptive_voluntary"), "denominator": sum(x["evidence_mode"] == "adaptive_voluntary" for x in rows)},
        "required_one_expansion_completion": {"numerator": sum(x["completed_expansion_count"] > 0 for x in rows if x["evidence_mode"] == "adaptive_required_one"), "denominator": sum(x["evidence_mode"] == "adaptive_required_one" for x in rows)},
        "selected_job_distribution": selected_jobs, "selected_boundary_distribution": selected_boundaries,
        "attempt_032_arm_matched_comparison": comparison, "rows": sorted(rows, key=lambda x: x["schedule_position"]), "raw_per_call_tokens": raw_calls, "actual_usage": ce.aggregate_actual_usage_records(raw_calls),
        "limitations": ["Required-One combines evidence disclosure with another model call.", "Source Present may expose the fault directly.", "The repetitions reuse the same faulty and clean pipeline executions."],
    }
    analysis["analysis_sha256"] = ce.sha256(analysis); path = attempt_root / "analysis/summary.json"; ce._write_immutable(path, analysis); return path


def _report(repo_root: Path, attempt_root: Path) -> Path:
    analysis = ce._read_json(attempt_root / "analysis/summary.json"); replay = ce._read_json(attempt_root / "replay/reconciliation.json")
    labels = {"current_run": "Current Run", "etiq_empty": "Etiq Empty", "compact_fixed": "Compact Fixed", "adaptive_voluntary": "Adaptive Voluntary", "adaptive_required_one": "Adaptive Required-One"}
    lines = ["# Attempt 033 — three-job campaign-brief fault visibility", "", "One faulty pipeline and one matched clean control were each reviewed three fresh times per package. Results are descriptive, not population-significance estimates.", "", f"Completed 60 reviews with {replay['observed_counts']['logical_provider_calls']} logical provider calls and zero repairs."]
    for source in ("source_absent", "source_present"):
        lines += ["", f"## {'Source-absent primary results' if source == 'source_absent' else 'Source-present results'}", "", "| Arm | Detected | Job 1 | Exact select_demand | Control FP | Calls | Input | Cached | Output |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for mode in MODES:
            x=analysis["arm_source_summaries"][f"{mode}__{source}"]
            lines.append(f"| {labels[mode]} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_upstream_job']['numerator']}/{x['correct_upstream_job']['denominator']} | {x['exact_select_demand']['numerator']}/{x['exact_select_demand']['denominator']} | {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']} | {x['provider_calls']} | {x['input_tokens']} | {x['cached_input_tokens']} | {x['output_tokens']} |")
    lines += ["", "## Adaptive pre/post", "", "| Trial | Arm | Source | Pre boundary | Final boundary | Expansion | Nodes | Relationships | Source | Values | Artifacts |", "|---|---|---|---|---|---|---:|---:|---|---|---|"]
    for row in analysis["adaptive_pre_post"]:
        selection = ", ".join(f"{x.get('resolved_job_id')}:{x.get('boundary_id')}:{x.get('child_group_id')}" for x in row["selected_expansions"]) or "none"
        lines.append(f"| {row['trial_id']} | {row['evidence_mode']} | {row['source_setting']} | {row['pre_expansion_selected_boundary_id'] or 'none'} | {row['final_selected_boundary_id'] or 'none'} | {selection} | {row['disclosed_node_count']} | {row['disclosed_relationship_count']} | {row['source_visible']} | {row['values_visible']} | {row['artifacts_visible']} |")
    lines += ["", "## All 60 trials", "", "| Pos | Trial | Instance | Arm | Source | Rep | Detected/FP | Job | Boundary | Calls | Input | Cached | Output |", "|---:|---|---|---|---|---:|---|---|---|---:|---:|---:|---:|"]
    for row in analysis["rows"]:
        calls=row["raw_calls"]; outcome="detected" if row["fault_detected"] else "FP" if row["false_positive"] else "clean/miss"
        lines.append(f"| {row['schedule_position']} | {row['trial_id']} | {row['instance_id']} | {row['evidence_mode']} | {row['source_setting']} | {row['repetition']} | {outcome} | {row['final_selected_job_id'] or 'none'} | {row['final_selected_boundary_id'] or 'none'} | {len(calls)} | {sum(int(x.get('input_tokens') or 0) for x in calls)} | {sum(int(x.get('cached_input_tokens') or 0) for x in calls)} | {sum(int(x.get('output_tokens') or 0) for x in calls)} |")
    lines += ["", "## Distributions", "", f"Selected jobs: `{json.dumps(analysis['selected_job_distribution'], sort_keys=True)}`", "", f"Selected boundaries: `{json.dumps(analysis['selected_boundary_distribution'], sort_keys=True)}`", "", "## Attempt 032 arm-matched comparison", "", "Differences are Attempt 033 minus Attempt 032 and are not pooled.", "", "| Arm | Source | Detection Δ | Job 1 Δ | Exact Δ |", "|---|---|---:|---:|---:|"]
    for x in analysis["attempt_032_arm_matched_comparison"]:
        d=x["rate_difference_attempt_033_minus_032"]; lines.append(f"| {x['evidence_mode']} | {x['source_setting']} | {d['fault_detection']:.3f} | {d['correct_upstream_job']:.3f} | {d['exact_select_demand']:.3f} |")
    lines += ["", "## Limitations", "", "- Required-One combines evidence disclosure with another model call.", "- Source Present may expose the fault directly.", "- This is one fault and one control, not a sample of fault classes.", ""]
    path=repo_root/"docs/workshops/n19a-three-job-campaign-brief-complete-findings.md"; path.parent.mkdir(parents=True,exist_ok=True); create_bytes_exclusive(path,"\n".join(lines).encode()); return path


def _handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze=ce._read_json(attempt_root/"experiment-freeze.json"); analysis=ce._read_json(attempt_root/"analysis/summary.json"); replay=ce._read_json(attempt_root/"replay/reconciliation.json"); terminal=ce._read_json(attempt_root/"terminal-state.json"); report=repo_root/"docs/workshops/n19a-three-job-campaign-brief-complete-findings.md"
    artifacts={"freeze": attempt_root/"experiment-freeze.json", "job3_source_record": attempt_root/"qualification/n19a-job3-source.json", "captures": attempt_root/"captures", "packages": attempt_root/"packages", "reviews": attempt_root/"reviews", "analysis": attempt_root/"analysis/summary.json", "replay": attempt_root/"replay/reconciliation.json", "terminal": attempt_root/"terminal-state.json", "report": report}
    hashes={name: ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name,path in artifacts.items()}
    lines=["To: Overseer", "From: Developer", "Subject: N19A Attempt 033 three-job campaign-brief results", "", f"Status: {terminal['status']}", f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)", f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`", "", "Counts and usage", "", f"- Packages: 20", f"- Reviews: 60", f"- Repairs: 0", f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}", f"- Usage: `{json.dumps(analysis['actual_usage'], sort_keys=True)}`", "", "Exact artifact hashes", ""]
    lines += [f"- `{artifacts[name].relative_to(repo_root)}`: `{digest}`" for name,digest in hashes.items()]
    lines += ["", "Source-absent arm results", ""]
    for mode in MODES:
        x=analysis["arm_source_summaries"][f"{mode}__source_absent"]; lines.append(f"- {mode}: detected {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']}; Job 1 {x['correct_upstream_job']['numerator']}/{x['correct_upstream_job']['denominator']}; exact select_demand {x['exact_select_demand']['numerator']}/{x['exact_select_demand']['denominator']}; control FP {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']}.")
    lines += ["", "Attempt 032 was preserved by the tree hash bound in the freeze. Job 1 and Job 2 were not reexecuted. Protected provider, authentication, sandbox, artifact-operation, prompt and legacy schema boundaries were unchanged.", ""]
    path=repo_root/"instructions_between_agent_types/developer/handoffs/N19A_attempt_033_three_job_campaign_brief_results_to_overseer.email.md"; path.parent.mkdir(parents=True,exist_ok=True); create_bytes_exclusive(path,"\n".join(lines).encode()); return path


def execute_lifecycle(repo_root: Path, attempt_root: Path) -> Path:
    repo_root=repo_root.resolve(); attempt_root=attempt_root.resolve(); verified=verify_frozen_attempt(repo_root,attempt_root); create_live_consumption(repo_root,attempt_root)
    catalogues, packages, records=_load_frozen(attempt_root); trials=ce._read_json(attempt_root/"review-design.json")["review_trials"]
    if len(trials)!=60 or ce._read_json(attempt_root/"repair-design.json")["repair_traces"]: raise ValueError("N19A frozen schedule changed")
    gate=ce._read_json(repo_root/ce.N15_HISTORICAL_GATE); python_executor=ce.signed_catalogue_python_executor(gate=gate,expected_gate_sha256=ce.sha256(gate),repo_root=repo_root)
    instances={instance:ce._read_json(attempt_root/"instances"/f"{instance}.json") for instance in INSTANCES}
    mutation=ce._read_json(attempt_root/"qualification/n16-nested-mutation.json"); reviews={}
    for trial in trials:
        path=attempt_root/"reviews"/f"{trial['trial_id']}.json"
        if path.exists():
            record=ce._read_json(path); ce._verified_self_hash(record,"review_sha256")
            if record.get("controller_trial")!=trial or record.get("status")!="complete": raise ValueError("invalid partial N19A review")
        else:
            package_record=packages[str(trial["branch_id"])]; package=package_record["reviewer_package"]; required=trial["evidence_mode"]=="adaptive_required_one"
            initial=_preserved_initial_response(attempt_root,str(trial["trial_id"])) or _provider_review(repo_root,attempt_root,ce.render_provider_request(package),str(trial["trial_id"]),required)
            pre=validate_response(catalogues[str(trial["instance_id"])],package,initial)
            def follow_up(request: Mapping[str,Any], *, controller_parent_id: str="") -> Mapping[str,Any]: return _provider_review(repo_root,attempt_root,request,controller_parent_id)
            followed=ce.run_n16_follow_up_loop(catalogue=catalogues[str(trial["instance_id"])],package=package,initial_response=initial,reviewer=follow_up,controller_parent_id=str(trial["trial_id"]),required_one=required,python_executor=python_executor)
            final=validate_response(catalogues[str(trial["instance_id"])],followed["package"],followed["response"]); outcome=score(instances[str(trial["instance_id"])],final)
            events=[x for x in followed["operation_events"] if x.get("operation")=="helper_expansion" and x.get("status")=="completed"]
            runtime=followed["package"].get("runtime_evidence",{}); exposure=_exposure(runtime); groups=[str(x["child_group_id"]) for x in events]
            record={"schema_version":"n19a-three-job-review-1","controller_trial":deepcopy(trial),"package_sha256":package_record["package_sha256"],"receipt":final["receipt"],"pre_expansion_selected_boundary_id":pre["selected_suspect_boundary_id"],"pre_expansion_selected_job_id":pre["selected_job_id"],"selected_suspect_boundary_id":final["selected_suspect_boundary_id"],"selected_job_id":final["selected_job_id"],"selected_job_position":final["selected_job_position"],"selected_function_name":final["selected_function_name"],**outcome,"operation_events":followed["operation_events"],"completed_expansion_count":followed["completed_expansion_count"],"expanded_child_group_ids":groups,"selected_expansions":[{key:deepcopy(x.get(key)) for key in ("resolved_job_id","boundary_id","child_group_id","nodes_added","relationships_added")} for x in events],"expanded_group_contained_mutation":trial["instance_id"]==INSTANCES[0] and mutation["child_group_id"] in groups,"disclosed_node_count":len(runtime.get("nodes",[])),"disclosed_relationship_count":len(runtime.get("relationships",[])),**exposure,"artifact_operation_count":sum(x.get("operation")=="artifact_inspection" and x.get("status")=="completed" for x in followed["operation_events"]),"call_records":followed["call_records"],"usage":followed["usage"],"status":"complete"}
            record["review_sha256"]=ce.sha256(record); ce._write_immutable(path,record)
        reviews[(str(trial["branch_id"]),int(trial["repetition"]))]=record
    required=[x for x in reviews.values() if x["controller_trial"]["evidence_mode"]=="adaptive_required_one"]
    if len(reviews)!=60 or len(required)!=12 or any(x["completed_expansion_count"]<1 for x in required): raise RuntimeError("N19A review or Required-One invariant failed")
    call_ids=[str(call_id) for record in reviews.values() for call in record.get("call_records",[]) for call_id in call.get("call_ids",[])]
    logical_calls=sum(len(x.get("call_records",[])) for x in reviews.values())
    if not 72<=logical_calls<=132 or len(call_ids)!=len(set(call_ids)): raise ValueError("N19A provider-call count or lineage changed")
    for call_id in call_ids: verify_record(attempt_root/"ledger",record_type="call-attempt",record_id=call_id)
    analysis=ce._read_json(write_analysis(repo_root,attempt_root,reviews))
    replay={"schema_version":"n19a-three-job-replay-1","freeze_sha256":verified["freeze_sha256"],"review_hashes":sorted(x["review_sha256"] for x in reviews.values()),"observed_counts":{"captures":2,"catalogues":len(catalogues),"packages":len(records),"reviews":len(reviews),"repairs":0,"logical_provider_calls":logical_calls,"provider_attempt_call_ids":len(call_ids),"completed_helper_expansions":sum(x["completed_expansion_count"] for x in reviews.values()),"disclosed_nodes":sum(x["disclosed_node_count"] for x in reviews.values()),"disclosed_relationships":sum(x["disclosed_relationship_count"] for x in reviews.values()),"artifact_operations":sum(x["artifact_operation_count"] for x in reviews.values())},"all_record_hashes_recomputed":True,"duplicate_logical_calls":False,"required_one_sessions_complete":True,"source_attempt_preserved":ce.sha256(ce._tree_hashes(repo_root/SOURCE_ATTEMPT))==ce._read_json(attempt_root/"experiment-freeze.json")["preserved_attempt_tree_hashes"]["attempt-032"]}
    replay["replay_sha256"]=ce.sha256(replay); ce._write_immutable(attempt_root/"replay/reconciliation.json",replay)
    terminal={"schema_version":"n19a-three-job-terminal-1","status":"completed_experiment_and_analysis","package_count":20,"review_count":60,"repair_trace_count":0,"analysis_sha256":analysis["analysis_sha256"],"replay_sha256":replay["replay_sha256"]}; terminal["terminal_sha256"]=ce.sha256(terminal); path=attempt_root/"terminal-state.json"; ce._write_immutable(path,terminal)
    _report(repo_root,attempt_root); _handoff(repo_root,attempt_root); return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None=None) -> Path:
    target=(attempt_root or repo_root/ATTEMPT).resolve()
    try: return execute_lifecycle(repo_root,target)
    except Exception as exc:
        terminal={"schema_version":"n19a-three-job-terminal-1","status":"terminal_incomplete","failure_stage":"n19a_resumable_lifecycle","error":f"{type(exc).__name__}: {exc}","completed_review_records":len(list((target/"reviews").glob("*.json"))),"completed_repair_records":0}; terminal["terminal_sha256"]=ce.sha256(terminal); path=target/"terminal"/f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"; ce._write_immutable(path,terminal); return path
