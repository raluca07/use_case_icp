"""N20 boundary-bundled upstream-fault experiment."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator

from . import corrected_experiment as ce
from .n05_program import _pipeline_payload, derive_review_evidence, execute_two_job_chain, load_preflight_inputs
from .n05_runner import copy_etiq_worker_runtime, create_bytes_exclusive, materialize_opaque_branch, verify_record
from .n07_program import EXPERIMENT_ROOT
from .records import GeneratedFile, GeneratedPipeline


ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-034")
SOURCE_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-032")
PRESERVED_ATTEMPT = Path("outputs/fault-experiments-v2-2-n10/attempt-033")
TASK = Path("instructions_between_agent_types/developer/current/N20_boundary_bundled_upstream_faults.email.md")
TASK_SHA256 = "sha256:1a0bb9585d40f7dc86e008de1f9dac166c346ff896fd060d328aebbe307167b7"
AUTHORITY = Path("instructions_between_agent_types/overseer/decisions/N20_boundary_bundled_upstream_faults_authorization.json")
AUTHORITY_SHA256 = "sha256:eedae21b53d1ba52ef49903841e9e22aaf9cb4972e9cac9519e119d00f573e21"
PROMPT = Path("prompts/v2_2/n20_open_review.md")
RESPONSE_SCHEMA = Path("schemas/v2_2/n20_open_review.schema.json")
SOURCE_FREEZE_SHA256 = "sha256:b1d8e808f1951904e6c2a1fdef9658cc50ae77a176a9e26f8d3778a827e3ef59"
CLEAN_CAPTURE_SHA256 = "sha256:61aefc03c9986ee3676dfb39d88417241c317e7b398c4f331187ffda74d128fc"
CLEAN_CAPTURE_FILE_SHA256 = "sha256:265a48537c4fa6c946b185c5a133fd655a308c56a76e7911b42b0849c0d6025b"
CLEAN_CATALOGUE_SHA256 = "sha256:af5666200e69f00c49654d0e63636f7c434c0671168cbb79ff61a306bfd166c5"
CLEAN_SOURCE_SHA256 = {
    "job_upstream_demand_provenance": "sha256:26d680ce5898debbaa8ea106a379925c25f8e8b3b6dde252b4b0ed14ec0ee575",
    "job_downstream_coverage_priority": "sha256:7bca6d6c66afab4833b3ddf0988876dbd74f1a24227a4ac686760aff12bb1cc3",
}
MODES = ("current_open", "etiq_empty_open", "compact_fixed_guided", "adaptive_voluntary_guided", "adaptive_required_one_guided")
FAULTS = (
    "select_threshold_omission", "select_wrong_source_weight",
    "normalize_top_record_omission", "normalize_middle_record_omission",
    "provenance_ranking_reversal", "provenance_join_identity",
)
CLEAN_INSTANCE = "n16-clean-control"
INSTANCES = (*FAULTS, CLEAN_INSTANCE)
TRUTH_FUNCTION = {
    "select_threshold_omission": "select_demand", "select_wrong_source_weight": "select_demand",
    "normalize_top_record_omission": "normalize", "normalize_middle_record_omission": "normalize",
    "provenance_ranking_reversal": "assemble_provenance", "provenance_join_identity": "assemble_provenance",
}
FAULT_GROUP = {
    "select_threshold_omission": "downstream_table_visible",
    "select_wrong_source_weight": "cross_stage_consistency_only",
    "normalize_top_record_omission": "final_output_changing",
    "normalize_middle_record_omission": "downstream_table_visible",
    "provenance_ranking_reversal": "final_output_changing",
    "provenance_join_identity": "cross_stage_consistency_only",
}


def _verify_authority(repo_root: Path) -> dict[str, Any]:
    for relative, expected in ((TASK, TASK_SHA256), (AUTHORITY, AUTHORITY_SHA256)):
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20 authority input changed: {relative}")
    source = repo_root / SOURCE_ATTEMPT
    if ce._verified_self_hash(ce._read_json(source / "experiment-freeze.json"), "freeze_sha256") != SOURCE_FREEZE_SHA256:
        raise ValueError("Attempt-032 logical freeze changed")
    clean_capture_path = source / "captures/n16-clean-control.json"
    clean_capture = ce._read_json(clean_capture_path)
    if ce.sha256(clean_capture_path.read_bytes()) != CLEAN_CAPTURE_FILE_SHA256 or clean_capture["capture_sha256"] != CLEAN_CAPTURE_SHA256:
        raise ValueError("Attempt-032 clean capture changed")
    clean_catalogue = ce._read_json(source / "catalogues/n16-clean-control.json")
    if clean_catalogue["catalogue_sha256"] != CLEAN_CATALOGUE_SHA256 or clean_capture["source_sha256"] != CLEAN_SOURCE_SHA256:
        raise ValueError("Attempt-032 clean catalogue or source changed")
    ce._verify_capture(clean_capture); ce.verify_catalogue(clean_catalogue)
    for relative, expected in ce.N15_PROTECTED_FILE_SHA256.items():
        if ce.sha256((repo_root / relative).read_bytes()) != expected:
            raise ValueError(f"N20 protected boundary changed: {relative}")
    return {"source_freeze_sha256": SOURCE_FREEZE_SHA256, "clean_capture_sha256": CLEAN_CAPTURE_SHA256, "clean_catalogue_sha256": CLEAN_CATALOGUE_SHA256, "clean_source_sha256": deepcopy(CLEAN_SOURCE_SHA256), "protected_hashes": deepcopy(ce.N15_PROTECTED_FILE_SHA256)}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _replace_span(source: str, node: ast.AST, replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    if node.lineno != node.end_lineno:
        raise ValueError("N20 mutation target unexpectedly spans lines")
    line = lines[node.lineno - 1]
    lines[node.lineno - 1] = line[:node.col_offset] + replacement + line[node.end_col_offset:]
    return "".join(lines)


def mutate_upstream(clean_jobs: Mapping[str, GeneratedPipeline], fault_id: str) -> tuple[dict[str, GeneratedPipeline], dict[str, Any]]:
    if fault_id not in FAULTS: raise ValueError("unknown N20 fault")
    upstream_id = "job_upstream_demand_provenance"; pipeline = clean_jobs[upstream_id]; source_file = pipeline.files[0]; source = source_file.content
    tree = ast.parse(source, filename=source_file.path); function_name = TRUTH_FUNCTION[fault_id]; function = _function(tree, function_name)
    target: ast.AST; replacement: str; expected: str
    if fault_id == "select_threshold_omission":
        candidates = [node for node in ast.walk(function) if isinstance(node, ast.Constant) and node.value == 3 and isinstance(getattr(node, "parent", None), ast.Compare)]
        # Parent links are intentionally avoided; the executed threshold is the sole >= 3 comparison.
        candidates = [comp for comp in ast.walk(function) if isinstance(comp, ast.Compare) for node in comp.comparators if isinstance(node, ast.Constant) and node.value == 3]
        if len(candidates) != 1: raise ValueError("threshold mutation site is not unique")
        target = candidates[0].comparators[0]; expected = "3"; replacement = "6"
    elif fault_id in {"normalize_top_record_omission", "normalize_middle_record_omission"}:
        old = "n06-r01" if fault_id == "normalize_top_record_omission" else "n06-r06"
        candidates = [node for node in ast.walk(function) if isinstance(node, ast.Constant) and node.value == old]
        if len(candidates) != 1: raise ValueError("normalization mutation site is not unique")
        target = candidates[0]; expected = repr(old); replacement = repr("n06-r09")
    elif fault_id == "provenance_ranking_reversal":
        candidates = [node for node in ast.walk(function) if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Call) and isinstance(node.operand.func, ast.Attribute) and node.operand.func.attr == "get" and node.operand.args and isinstance(node.operand.args[0], ast.Constant) and node.operand.args[0].value == "demand_score"]
        if len(candidates) != 1: raise ValueError("ranking mutation site is not unique")
        target = candidates[0]; expected = ast.get_source_segment(source, target) or ""; replacement = ast.get_source_segment(source, target.operand) or ""
    else:
        emitted_key = "source_weight" if fault_id == "select_wrong_source_weight" else "record_id"
        new_key = "demand_score" if fault_id == "select_wrong_source_weight" else "source_id"
        candidates = []
        for node in ast.walk(function):
            if not isinstance(node, ast.Dict): continue
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == emitted_key and isinstance(value, ast.Call) and value.args and isinstance(value.args[0], ast.Constant) and value.args[0].value == emitted_key:
                    candidates.append(value.args[0])
        if len(candidates) != 1: raise ValueError("emitted-field mutation site is not unique")
        target = candidates[0]; expected = repr(emitted_key); replacement = repr(new_key)
    original = ast.get_source_segment(source, target) or ""
    if original not in {expected, '"' + expected.strip("'") + '"'} and fault_id != "provenance_ranking_reversal":
        raise ValueError(f"unexpected N20 mutation source: {original}")
    mutant_source = _replace_span(source, target, replacement); compile(mutant_source, source_file.path, "exec")
    mutant_pipeline = GeneratedPipeline(entry_file=pipeline.entry_file, files=[GeneratedFile(item.path, mutant_source if item.path == source_file.path else item.content) for item in pipeline.files], review_boundaries=deepcopy(pipeline.review_boundaries))
    identity = next(x for x in ce.static_definitions(upstream_id, mutant_pipeline) if x["qualified_function_name"] == function_name)
    for boundary in mutant_pipeline.review_boundaries:
        if boundary.get("qualified_function_name") == function_name: boundary["function_source_sha256"] = identity["function_source_sha256"]
    mutant_pipeline.validate(); jobs = {job_id: deepcopy(value) for job_id, value in clean_jobs.items()}; jobs[upstream_id] = mutant_pipeline
    site = {"fault_id": fault_id, "job_id": upstream_id, "qualified_function_name": function_name, "source_path": source_file.path, "ast_site_kind": type(target).__name__, "original_span": {"start_line": target.lineno, "end_line": target.end_lineno, "start_column": target.col_offset, "end_column": target.end_col_offset}, "original_snippet": original, "mutant_snippet": replacement, "candidate_count": 1, "oracle_used_for_site_selection": False}
    site["mutation_sha256"] = ce.sha256(site); return jobs, site


def _ids(output: Mapping[str, Any], field: str = "needs") -> list[str]:
    return [str(x["record_id"]) for x in output[field]]


def qualify_mutant(fault_id: str, clean_capture: Mapping[str, Any], capture: Mapping[str, Any], site: Mapping[str, Any]) -> dict[str, Any]:
    up="job_upstream_demand_provenance"; down="job_downstream_coverage_priority"; clean_up=clean_capture["jobs"][up]["output"]; clean_down=clean_capture["jobs"][down]["output"]; mutant_up=capture["jobs"][up]["output"]; mutant_down=capture["jobs"][down]["output"]
    clean_ids=_ids(clean_up); mutant_ids=_ids(mutant_up); direct: dict[str,bool]
    if fault_id == "select_threshold_omission": direct={"n06_r06_omitted": "n06-r06" in clean_ids and "n06-r06" not in mutant_ids, "fallback_rows_remain": {"n06-r07","n06-r08"} <= set(mutant_ids)}
    elif fault_id == "select_wrong_source_weight":
        corpus={x["record_id"]:x for x in capture["jobs"][up]["input"]["corpus"]}; direct={"weights_equal_demand_score": all(x["source_weight"]==corpus[x["record_id"]]["demand_score"] for x in mutant_up["needs"]), "weights_differ_from_stipulated": any(x["source_weight"]!=corpus[x["record_id"]]["source_weight"] for x in mutant_up["needs"])}
    elif fault_id == "normalize_top_record_omission": direct={"top_record_omitted": "n06-r01" not in mutant_ids, "next_record_promoted": mutant_down["recommendation"]["top_need"]==clean_down["priorities"][1]["need"]}
    elif fault_id == "normalize_middle_record_omission": direct={"middle_record_omitted": "n06-r06" not in mutant_ids, "top_recommendation_preserved": mutant_down["recommendation"]==clean_down["recommendation"]}
    elif fault_id == "provenance_ranking_reversal":
        demand_scores={str(x["record_id"]):x["demand_score"] for x in mutant_up["needs"]}; observed_scores=[demand_scores[x] for x in _ids(mutant_up,"evidence_sources")]; direct={"provenance_demand_order_reversed": observed_scores==sorted(observed_scores) and observed_scores!=sorted(observed_scores,reverse=True), "downstream_order_changed": mutant_down["priorities"]!=clean_down["priorities"]}
    else:
        source_ids=[str(x["source_id"]) for x in mutant_up["needs"]]; provenance_ids=_ids(mutant_up,"evidence_sources"); direct={"provenance_record_ids_are_source_ids": provenance_ids==source_ids, "downstream_rank_correspondence_broken": [x["upstream_rank"] for x in mutant_down["priorities"]]!=[x["upstream_rank"] for x in clean_down["priorities"]]}
    schema_types = set(mutant_up)==set(clean_up) and set(mutant_down)==set(clean_down) and all(type(mutant_up[k]) is type(clean_up[k]) for k in clean_up) and all(type(mutant_down[k]) is type(clean_down[k]) for k in clean_down)
    handoffs_valid=all(x["producer_sha256"]==x["consumer_sha256"] for x in capture["handoffs"])
    target_boundary=next(x for x in capture["jobs"][up]["realization"]["realized_boundaries"] if x["function_name"]==site["qualified_function_name"])
    checks={"exactly_one_ast_site_changed": site["candidate_count"]==1, "changed_function_executed": bool(target_boundary["node_refs"]), "both_jobs_completed": all(capture["jobs"][j]["snapshot"]["nodes"] for j in (up,down)), "schemas_and_types_valid": schema_types, "exact_handoffs_valid": handoffs_valid, "nonempty_plausible_output": bool(mutant_down["priorities"]) and bool(mutant_down["recommendation"]["top_need"]), "clean_fault_specific_oracle_passed": True, "mutant_failed_prespecified_oracle": all(direct.values())}
    if not all(checks.values()): raise ValueError(f"N20 mutation failed qualification: {fault_id}: {checks} {direct}")
    record={"schema_version":"n20-mutation-qualification-1",**deepcopy(dict(site)),"fault_group":FAULT_GROUP[fault_id],"direct_semantic_checks":direct,"validation":checks,"capture_sha256":capture["capture_sha256"]}; record["qualification_sha256"]=ce.sha256(record); return record


def _build_catalogue(capture: Mapping[str, Any]) -> dict[str, Any]:
    temporary=deepcopy(dict(capture)); temporary["instance_id"]="n16-nested-fault"; temporary.pop("capture_sha256",None); temporary["capture_sha256"]=ce.sha256(temporary)
    catalogue=ce.build_disclosure_catalogue(temporary); catalogue["instance_id"]=str(capture["instance_id"]); catalogue["source_capture_id"]=str(capture["capture_id"]); catalogue["source_capture_sha256"]=str(capture["capture_sha256"]); catalogue.pop("catalogue_sha256",None); catalogue["catalogue_sha256"]=ce.sha256(catalogue); ce.verify_catalogue(catalogue); return catalogue


def prepare_attempt(repo_root: Path, attempt_root: Path | None = None) -> dict[str, Any]:
    repo_root=repo_root.resolve(); target=(attempt_root or repo_root/ATTEMPT).resolve()
    if target!=(repo_root/ATTEMPT).resolve(): raise ValueError("N20 is authorized only for Attempt 034")
    _verify_authority(repo_root)
    existing=sorted((target/"captures").glob("*.json"))
    if len(existing)==7:
        captures={path.stem:ce._read_json(path) for path in existing}; catalogues={key:ce._read_json(target/"catalogues"/f"{key}.json") for key in captures}
        for value in captures.values(): ce._verify_capture(value)
        for value in catalogues.values(): ce.verify_catalogue(value)
        return {"captures":captures,"catalogues":catalogues,"reused":True}
    if not {path.stem for path in existing} <= set(INSTANCES): raise ValueError("Attempt 034 has an invalid partial capture set")
    preserved={"attempt-032":ce.sha256(ce._tree_hashes(repo_root/SOURCE_ATTEMPT)),"attempt-033":ce.sha256(ce._tree_hashes(repo_root/PRESERVED_ATTEMPT))}
    clean_jobs,_=ce._n16_clean_base(repo_root)
    if {job_id:ce.sha256(_pipeline_payload(pipeline)) for job_id,pipeline in clean_jobs.items()}!=CLEAN_SOURCE_SHA256: raise ValueError("reconstructed clean pipeline source differs from Attempt 032")
    clean_capture_path=repo_root/SOURCE_ATTEMPT/"captures/n16-clean-control.json"; clean_catalogue_path=repo_root/SOURCE_ATTEMPT/"catalogues/n16-clean-control.json"
    clean_capture=ce._read_json(clean_capture_path); clean_catalogue=ce._read_json(clean_catalogue_path)
    ce._write_immutable(target/"captures"/f"{CLEAN_INSTANCE}.json",clean_capture); ce._write_immutable(target/"catalogues"/f"{CLEAN_INSTANCE}.json",clean_catalogue)
    clean_instance={"schema_version":"n20-instance-1","instance_id":CLEAN_INSTANCE,"designation":"matched_clean_control","source_attempt":"attempt-032","capture_sha256":clean_capture["capture_sha256"],"catalogue_sha256":clean_catalogue["catalogue_sha256"],"source_sha256":deepcopy(clean_capture["source_sha256"]),"truth_function":None,"fault_group":"clean_control","mutation":None}; clean_instance["instance_sha256"]=ce.sha256(clean_instance); ce._write_immutable(target/"instances"/f"{CLEAN_INSTANCE}.json",clean_instance)
    scenario=load_preflight_inputs(repo_root,EXPERIMENT_ROOT); captures={path.stem:ce._read_json(path) for path in existing}; captures[CLEAN_INSTANCE]=clean_capture; catalogues={key:ce._read_json(target/"catalogues"/f"{key}.json") for key in captures if (target/"catalogues"/f"{key}.json").exists()}; catalogues[CLEAN_INSTANCE]=clean_catalogue
    qualifications=[]
    for index,fault_id in enumerate(FAULTS):
        if fault_id in captures:
            qualification=ce._read_json(target/"qualification/mutations"/f"{fault_id}.json"); qualifications.append(qualification); continue
        jobs,site=mutate_upstream(clean_jobs,fault_id); branch=target/"capture-branches"/fault_id; retry=0
        while branch.exists(): retry+=1; branch=target/"capture-branches"/f"{fault_id}-retry-{retry:02d}"
        materialize_opaque_branch(branch,allowlist={name:repo_root/EXPERIMENT_ROOT/name for name in ("scenario.json","corpus.json","capabilities.json","oracles.json")},manifest_identity={"purpose":"n20-mutant-capture","fault_id":fault_id})
        copy_etiq_worker_runtime(branch,repo_root/"src")
        execution=execute_two_job_chain(branch,repo_root=repo_root,jobs=jobs,scenario=scenario,run_index=index,stage=f"n20-{fault_id}")
        execution.update(derive_review_evidence(execution,jobs=jobs,scenario=scenario))
        capture=ce._n16_capture_from_execution(fault_id,jobs,execution); catalogue=_build_catalogue(capture)
        qualification=qualify_mutant(fault_id,clean_capture,capture,site); qualifications.append(qualification)
        instance={"schema_version":"n20-instance-1","instance_id":fault_id,"designation":"upstream_fault","source_attempt":"attempt-032-clean-base","capture_sha256":capture["capture_sha256"],"catalogue_sha256":catalogue["catalogue_sha256"],"source_sha256":deepcopy(capture["source_sha256"]),"truth_job":"job_upstream_demand_provenance","truth_function":TRUTH_FUNCTION[fault_id],"fault_group":FAULT_GROUP[fault_id],"mutation":deepcopy(site),"qualification_sha256":qualification["qualification_sha256"]}; instance["instance_sha256"]=ce.sha256(instance)
        ce._write_immutable(target/"captures"/f"{fault_id}.json",capture); ce._write_immutable(target/"catalogues"/f"{fault_id}.json",catalogue); ce._write_immutable(target/"instances"/f"{fault_id}.json",instance); ce._write_immutable(target/"qualification/mutations"/f"{fault_id}.json",qualification)
        captures[fault_id]=capture; catalogues[fault_id]=catalogue
    summary={"schema_version":"n20-mutation-qualification-summary-1","status":"passed","fault_count":6,"clean_control_reused":True,"qualification_hashes":{x["fault_id"]:x["qualification_sha256"] for x in qualifications},"model_calls":0}; summary["summary_sha256"]=ce.sha256(summary); ce._write_immutable(target/"qualification/mutation-summary.json",summary)
    for name,path in (("attempt-032",repo_root/SOURCE_ATTEMPT),("attempt-033",repo_root/PRESERVED_ATTEMPT)):
        if ce.sha256(ce._tree_hashes(path))!=preserved[name]: raise RuntimeError(f"{name} changed during N20 preparation")
    return {"captures":captures,"catalogues":catalogues,"reused":False,"mutation_qualification":summary}


def _open_common(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    up,down=list(map(str,catalogue["job_order"]))
    return {
        "schema_version":"n20-open-common-1",
        "review_task":"Start from the final downstream result, reason backward across both jobs and exact handoffs, identify the earliest responsible function if a behavioural rule is violated, or return a clean conclusion.",
        "behavioural_criteria":[
            "Treat the supplied corpus and capabilities as stipulated inputs.",
            "Select all qualifying or fallback demand records and preserve record_id, need, demand_score, source_id, and source_weight.",
            "Retain only allowed record identities without silently omitting stipulated records.",
            "Preserve deterministic source provenance identities, weights, and demand-descending rank order.",
            "Preserve both exact upstream-to-downstream handoffs.",
            "Map capabilities without changing need text or record identity.",
            "Rank unsupported needs first, then preserve upstream provenance order, and recommend the first priority.",
        ],
        "top_level":{"input":deepcopy(catalogue["jobs"][up]["input"]),"final_output":deepcopy(catalogue["jobs"][down]["output"])},
        "assigned_job":{"job_id":down,"observation_point":"downstream_result","input":deepcopy(catalogue["jobs"][down]["input"]),"output":deepcopy(catalogue["jobs"][down]["output"]),"stdout":str(catalogue["jobs"][down]["stdout"]),"stderr":str(catalogue["jobs"][down]["stderr"])},
        "job_executions":[{"job_id":job_id,"job_position":"downstream" if job_id==down else "upstream","input":deepcopy(catalogue["jobs"][job_id]["input"]),"output":deepcopy(catalogue["jobs"][job_id]["output"]),"stdout":str(catalogue["jobs"][job_id]["stdout"]),"stderr":str(catalogue["jobs"][job_id]["stderr"])} for job_id in (down,up)],
        "ordered_job_topology":[{"job_id":down,"position":"downstream","observation_point":True},{"job_id":up,"position":"upstream","observation_point":False}],
        "exact_handoffs":deepcopy(list(catalogue["handoffs"])),
    }


def _guided_declarations(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    bindings=ce._n16_binding_rows(catalogue); by={(x["job_id"],x["function_name"]):x for x in bindings}; up,down=list(map(str,catalogue["job_order"])); declarations=[]
    for job_id in (down,up):
        for boundary in catalogue["jobs"][job_id]["realized_boundaries"]:
            binding=by[(job_id,str(boundary["function_name"]))]
            declarations.append({"boundary_id":binding["reviewer_boundary_id"],"job_id":job_id,"job_position":binding["job_position"],"function_name":str(boundary["function_name"]),"role":str(boundary["role"]),"expected_inputs":deepcopy(boundary["expected_inputs"]),"expected_outputs":deepcopy(boundary["expected_outputs"])})
    return {"review_order":"downstream_first","semantic_declarations":declarations,"assigned_boundary_ids":[x["boundary_id"] for x in declarations]}


def _empty_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    value={"job_evidence_order":list(reversed(catalogue["job_order"])),"anchors":[],"nodes":[],"relationships":[],"handoffs":[],"collapsed_child_groups":[],"disclosed_child_groups":[],"collapsed_children":[],"visible_evidence_by_boundary":{}}; value["projection_sha256"]=ce.sha256(value); return value


def _compact_projection(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    value=ce.n16_compact_projection(catalogue); value["handoffs"]=[]; value.pop("projection_sha256",None); value["projection_sha256"]=ce.sha256(value); return value


def build_review_package(catalogue: Mapping[str, Any], mode: str) -> dict[str, Any]:
    if mode not in MODES: raise ValueError("unknown N20 mode")
    adaptive=mode in {"adaptive_voluntary_guided","adaptive_required_one_guided"}
    package: dict[str,Any]={"schema_version":"corrected-four-instance-package-2","common_base":_open_common(catalogue),"available_operations":["helper_expansion"] if adaptive else [],"action_contract":{"permitted_actions":[*(["helper_expansion"] if adaptive else []),"finalize"],"first_action_must_expand_one_model_selected_child_group":mode=="adaptive_required_one_guided","maximum_completed_expansions":1,"finalize_after_completed_expansion":True},"allowed_evidence_refs":[str(x["handoff_id"]) for x in catalogue["handoffs"]],"prior_task_records":[]}
    if mode!="current_open":
        package["integrated_etiq_instructions"]={"framing":"Review the supplied execution graph evidence when judging the run.","semantic_boundaries_supplied":mode!="etiq_empty_open","model_selects_any_expansion":adaptive}
        package["runtime_evidence"]=_empty_projection(catalogue) if mode=="etiq_empty_open" else _compact_projection(catalogue)
    if mode in {"compact_fixed_guided","adaptive_voluntary_guided","adaptive_required_one_guided"}:
        package["boundary_guidance"]=_guided_declarations(catalogue)
        graph=package["runtime_evidence"]; package["allowed_evidence_refs"]=sorted(set(package["allowed_evidence_refs"])|{str(x["boundary_id"]) for x in graph["anchors"]}|{str(x["anchor_id"]) for x in graph["anchors"]}|{str(x["child_group_id"]) for x in graph["collapsed_child_groups"]})
    if "source_bundle" in package: raise ValueError("N20 package must not contain a source bundle")
    return package


def render_request(package: Mapping[str,Any], operation_response: Mapping[str,Any] | None=None) -> dict[str,Any]:
    request={"reviewer_package":deepcopy(dict(package))}
    if operation_response is not None: request["operation_response"]=deepcopy(dict(operation_response))
    forbidden=("mutation","oracle","designation","truth","instance_id","fault_id","evidence_mode","branch_id","trial_id","repetition","seed","source_bundle")
    visible=ce.canonical_json(request).decode()
    if any(f'"{key}"' in visible for key in forbidden): raise ValueError("N20 rendered request leaks controller state")
    return request


def expand_child(catalogue: Mapping[str,Any], package: Mapping[str,Any], boundary_id: str, child_group_id: str) -> tuple[dict[str,Any],dict[str,Any]]:
    internal=deepcopy(dict(package)); internal["common_base"]["semantic_declarations"]=[]; internal["common_base"]["section"]={"section_id":"internal-n20-expansion","section_index":0,"organization":{"kind":"operation_validation_only"},"assigned_boundary_ids":[],"context_boundary_ids":[]}
    updated,event=ce.expand_n16_child(catalogue,internal,boundary_id=boundary_id,child_group_id=child_group_id)
    updated["common_base"].pop("semantic_declarations",None); updated["common_base"].pop("section",None); return updated,event


def schedule() -> dict[str,Any]:
    packages=[{"instance_id":instance,"evidence_mode":mode,"branch_id":f"brn-{ce.sha256(['n20',instance,mode])[7:23]}"} for instance in INSTANCES for mode in MODES]; by={(x["instance_id"],x["evidence_mode"]):x for x in packages}; reviews=[]; block=0
    for repetition in range(1,4):
        instances=INSTANCES[repetition-1:]+INSTANCES[:repetition-1]
        for instance in instances:
            rotation=block%5
            for position,mode in enumerate(MODES[rotation:]+MODES[:rotation],1):
                condition=by[(instance,mode)]; reviews.append({**condition,"repetition":repetition,"trial_id":f"trial-{ce.sha256(['n20',condition['branch_id'],repetition])[7:23]}","schedule_position":len(reviews)+1,"local_block":block+1,"mode_position":position})
            block+=1
    if (len(packages),len(reviews),len({x["trial_id"] for x in reviews}))!=(35,105,105): raise AssertionError("N20 schedule changed")
    return {"packages":packages,"review_trials":reviews,"repair_traces":[]}


def qualify_packages(records: list[Mapping[str,Any]], catalogues: Mapping[str,Mapping[str,Any]], design: Mapping[str,Any]) -> dict[str,Any]:
    if (len(catalogues),len(records),len(design["review_trials"]),len(design["repair_traces"]))!=(7,35,105,0): raise ValueError("N20 package or schedule count changed")
    by={(x["controller_condition"]["instance_id"],x["controller_condition"]["evidence_mode"]):x["reviewer_package"] for x in records}; checks=0
    forbidden_keys=("mutation","oracle","designation","truth","instance_id","fault_id","evidence_mode","branch_id","trial_id","repetition","seed","source_bundle")
    for instance in INSTANCES:
        pair={mode:by[(instance,mode)] for mode in MODES}
        if len({ce.canonical_json(x["common_base"]) for x in pair.values()})!=1: raise ValueError("N20 common runtime evidence differs across arms")
        current=pair["current_open"]; empty=pair["etiq_empty_open"]; fixed=pair["compact_fixed_guided"]; voluntary=pair["adaptive_voluntary_guided"]; required=pair["adaptive_required_one_guided"]
        if any(key in current for key in ("runtime_evidence","integrated_etiq_instructions","boundary_guidance")) or current["available_operations"]: raise ValueError("Current Open contains guided framing or operations")
        if any(key in current["common_base"] for key in ("semantic_declarations","section")): raise ValueError("open common evidence contains boundary hints")
        if "boundary_guidance" in empty or empty["available_operations"] or any(empty["runtime_evidence"].get(key) for key in ("anchors","nodes","relationships","handoffs","collapsed_child_groups")): raise ValueError("Etiq Empty is not boundary-free and empty")
        for guided in (fixed,voluntary,required):
            if len(guided["boundary_guidance"]["semantic_declarations"])!=6 or len(guided["runtime_evidence"]["anchors"])!=6 or guided["runtime_evidence"]["nodes"] or guided["runtime_evidence"]["relationships"]: raise ValueError("guided package lacks six compact declarations and anchors")
        if len({ce.canonical_json(x["boundary_guidance"]) for x in (fixed,voluntary,required)})!=1 or len({ce.canonical_json(x["runtime_evidence"]) for x in (fixed,voluntary,required)})!=1: raise ValueError("Fixed and Adaptive initial guidance differs")
        for package in pair.values():
            visible=ce.canonical_json(render_request(package)).decode()
            if any(f'"{key}"' in visible for key in forbidden_keys): raise ValueError("N20 provider request leaks controller state or source bundle")
        current_visible=ce.canonical_json(render_request(current)).decode().lower(); empty_visible=ce.canonical_json(render_request(empty)).decode().lower()
        if any(word in current_visible for word in ("graph","boundary_id","function_name","expected_inputs","expected_outputs")): raise ValueError("Current Open contains graph or boundary-derived wording")
        if any(word in empty_visible for word in ("boundary_id","function_name","expected_inputs","expected_outputs")): raise ValueError("Etiq Empty contains boundary-derived wording")
        checks+=9
    return {"status":"passed","model_calls":0,"fault_count":6,"clean_control_count":1,"capture_count":7,"catalogue_count":7,"package_count":35,"review_count":105,"required_one_follow_up_count":21,"provider_call_minimum":126,"provider_call_maximum":147,"repair_count":0,"comparison_count":checks}


def build_attempt(repo_root: Path, attempt_root: Path | None=None) -> dict[str,Any]:
    repo_root=repo_root.resolve(); target=(attempt_root or repo_root/ATTEMPT).resolve(); prepared=prepare_attempt(repo_root,target); design=schedule(); records=[]
    for condition in design["packages"]:
        catalogue=prepared["catalogues"][condition["instance_id"]]; package=build_review_package(catalogue,condition["evidence_mode"])
        record={"schema_version":"n20-frozen-package-1","controller_condition":deepcopy(condition),"source_capture_sha256":catalogue["source_capture_sha256"],"catalogue_sha256":catalogue["catalogue_sha256"],"reviewer_package":package}; record["package_sha256"]=ce.sha256(record); records.append(record)
    return {**prepared,"packages":records,"schedule":design,"qualification":qualify_packages(records,prepared["catalogues"],design)}


def _load_frozen(attempt_root: Path) -> tuple[dict[str,Any],dict[str,Any],list[dict[str,Any]]]:
    catalogues={path.stem:ce._read_json(path) for path in sorted((attempt_root/"catalogues").glob("*.json"))}; packages={}; records=[]
    for path in sorted((attempt_root/"controller-manifests").glob("*.json")):
        manifest=ce._read_json(path); package=ce._read_json(attempt_root/manifest["reviewer_package_path"])
        if ce.sha256(package)!=manifest["reviewer_package_sha256"]: raise ValueError("N20 reviewer package hash mismatch")
        record={**manifest,"reviewer_package":package}; unsigned=deepcopy(record); observed=unsigned.pop("package_sha256"); unsigned.pop("reviewer_package_path"); unsigned.pop("reviewer_package_sha256")
        if ce.sha256(unsigned)!=observed: raise ValueError("N20 package record hash mismatch")
        packages[str(manifest["controller_condition"]["branch_id"])]=record; records.append(record)
    return catalogues,packages,records


def freeze_attempt(repo_root: Path, attempt_root: Path | None=None) -> Path:
    repo_root=repo_root.resolve(); target=(attempt_root or repo_root/ATTEMPT).resolve()
    if (target/"experiment-freeze.json").exists(): raise ValueError("Attempt 034 is already frozen")
    if any((target/name).exists() for name in ("packages","controller-manifests","reviews")): raise ValueError("Attempt 034 contains pre-freeze scientific material")
    preserved={"attempt-032":ce.sha256(ce._tree_hashes(repo_root/SOURCE_ATTEMPT)),"attempt-033":ce.sha256(ce._tree_hashes(repo_root/PRESERVED_ATTEMPT))}; built=build_attempt(repo_root,target)
    for record in built["packages"]:
        branch=record["controller_condition"]["branch_id"]; ce._write_immutable(target/"packages"/branch/"reviewer-package.json",record["reviewer_package"]); manifest={key:deepcopy(value) for key,value in record.items() if key!="reviewer_package"}; manifest.update({"reviewer_package_path":f"packages/{branch}/reviewer-package.json","reviewer_package_sha256":ce.sha256(record["reviewer_package"])}); ce._write_immutable(target/"controller-manifests"/f"{branch}.json",manifest)
    ce._write_immutable(target/"review-design.json",{"review_trials":built["schedule"]["review_trials"]}); ce._write_immutable(target/"repair-design.json",{"repair_traces":[]})
    for name,path in (("attempt-032",repo_root/SOURCE_ATTEMPT),("attempt-033",repo_root/PRESERVED_ATTEMPT)):
        if ce.sha256(ce._tree_hashes(path))!=preserved[name]: raise RuntimeError(f"{name} changed during N20 freeze")
    code_paths=(Path("src/use_case_icp/n20_experiment.py"),Path("tests/test_n20_experiment.py"),PROMPT,RESPONSE_SCHEMA)
    freeze={"schema_version":"n20-boundary-bundled-freeze-1","status":"frozen_before_first_experimental_review","attempt":"attempt-034","source_attempt":"attempt-032","authority":{"path":AUTHORITY.as_posix(),"sha256":AUTHORITY_SHA256},"task":{"path":TASK.as_posix(),"sha256":TASK_SHA256},"authority_bindings":_verify_authority(repo_root),"protected_boundaries":deepcopy(ce.N15_PROTECTED_FILE_SHA256),"code_hashes":{path.as_posix():ce.sha256((repo_root/path).read_bytes()) for path in code_paths},"preserved_attempt_tree_hashes":preserved,"capture_hashes":{key:value["capture_sha256"] for key,value in built["captures"].items()},"catalogue_hashes":{key:value["catalogue_sha256"] for key,value in built["catalogues"].items()},"mutation_qualification_hashes":ce._read_json(target/"qualification/mutation-summary.json")["qualification_hashes"],"package_hashes":sorted(x["package_sha256"] for x in built["packages"]),"package_tree_sha256":ce.sha256(ce._tree_hashes(target/"packages")),"common_runtime_hashes":{instance:ce.sha256(next(x for x in built["packages"] if x["controller_condition"]["instance_id"]==instance)["reviewer_package"]["common_base"]) for instance in INSTANCES},"review_design_sha256":ce.sha256(built["schedule"]["review_trials"]),"repair_design_sha256":ce.sha256([]),"expected_counts":{"faults":6,"controls":1,"captures":7,"catalogues":7,"packages":35,"reviews":105,"required_one_follow_ups":21,"provider_calls_max":147,"repairs":0},"qualification":built["qualification"],"model":ce.PROVIDER_MODEL,"reasoning_effort":ce.PROVIDER_REASONING_EFFORT,"experimental_review_records_at_freeze":0}; freeze["freeze_sha256"]=ce.sha256(freeze); path=target/"experiment-freeze.json"; ce._write_immutable(path,freeze); return path


def verify_frozen_attempt(repo_root: Path, attempt_root: Path | None=None) -> dict[str,Any]:
    repo_root=repo_root.resolve(); target=(attempt_root or repo_root/ATTEMPT).resolve(); _verify_authority(repo_root); freeze=ce._read_json(target/"experiment-freeze.json"); observed=ce._verified_self_hash(freeze,"freeze_sha256")
    for relative,expected in freeze["code_hashes"].items():
        if ce.sha256((repo_root/relative).read_bytes())!=expected: raise ValueError(f"N20 frozen code changed: {relative}")
    for relative,expected in freeze["protected_boundaries"].items():
        if ce.sha256((repo_root/relative).read_bytes())!=expected: raise ValueError(f"N20 protected boundary changed: {relative}")
    for name,path in (("attempt-032",repo_root/SOURCE_ATTEMPT),("attempt-033",repo_root/PRESERVED_ATTEMPT)):
        if ce.sha256(ce._tree_hashes(path))!=freeze["preserved_attempt_tree_hashes"][name]: raise ValueError(f"N20 preserved {name} changed")
    catalogues,_,records=_load_frozen(target); design={"packages":[deepcopy(x["controller_condition"]) for x in records],"review_trials":ce._read_json(target/"review-design.json")["review_trials"],"repair_traces":ce._read_json(target/"repair-design.json")["repair_traces"]}; qualification=qualify_packages(records,catalogues,design)
    if sorted(x["package_sha256"] for x in records)!=freeze["package_hashes"] or ce.sha256(design["review_trials"])!=freeze["review_design_sha256"]: raise ValueError("N20 frozen package or schedule changed")
    return {"status":"verified","freeze_sha256":observed,"qualification":qualification,"capture_count":7,"catalogue_count":7,"package_count":35,"review_count":105,"repair_count":0}


def create_live_consumption(repo_root: Path, attempt_root: Path) -> Path:
    path=attempt_root/"live-consumption.json"
    if path.exists(): ce._verified_self_hash(ce._read_json(path),"consumption_sha256"); return path
    if list((attempt_root/"reviews").glob("*.json")): raise ValueError("N20 review exists before live consumption")
    verified=verify_frozen_attempt(repo_root,attempt_root); record={"schema_version":"n20-live-consumption-1","status":"live_authority_consumed_before_first_provider_call","authority":{"path":AUTHORITY.as_posix(),"sha256":AUTHORITY_SHA256},"freeze_sha256":verified["freeze_sha256"],"package_tree_sha256":ce.sha256(ce._tree_hashes(attempt_root/"packages")),"controller_manifest_tree_sha256":ce.sha256(ce._tree_hashes(attempt_root/"controller-manifests")),"review_design_file_sha256":ce.sha256((attempt_root/"review-design.json").read_bytes()),"protected_file_hashes":deepcopy(ce.N15_PROTECTED_FILE_SHA256),"model":ce.PROVIDER_MODEL,"reasoning_effort":ce.PROVIDER_REASONING_EFFORT,"expected_counts":{"packages":35,"reviews":105,"required_one_follow_ups":21,"provider_calls_max":147,"repairs":0}}; record["consumption_sha256"]=ce.sha256(record); ce._write_immutable(path,record); return path


def _normalized_function(value: Any) -> str | None:
    if value is None: return None
    names=re.findall(r"[A-Za-z_][A-Za-z0-9_]*",str(value).strip().lower())
    return names[-1] if names else None


def validate_response(catalogue: Mapping[str,Any], package: Mapping[str,Any], response: Mapping[str,Any]) -> dict[str,Any]:
    scientific={key:deepcopy(response.get(key)) for key in ("fault_detected","suspect_job","suspect_function","suspect_boundary_id","explanation","evidence_refs","next_action")}; Draft202012Validator(ce._read_json(Path(__file__).resolve().parents[2]/RESPONSE_SCHEMA)).validate(scientific)
    detected=bool(scientific["fault_detected"]); job=scientific["suspect_job"]; function=_normalized_function(scientific["suspect_function"]); boundary=scientific["suspect_boundary_id"]
    if detected!=(job is not None and function is not None): raise ValueError("fault decision and suspect job/function are inconsistent")
    guided=package.get("boundary_guidance"); allowed=set(guided["assigned_boundary_ids"]) if guided else set()
    if boundary is not None and str(boundary) not in allowed: raise ValueError("response cites an unseen boundary identifier")
    return {"valid":True,"receipt":scientific,"fault_detected":detected,"suspect_job":job,"normalized_suspect_function":function,"suspect_boundary_id":boundary}


def score_response(instance: Mapping[str,Any], validation: Mapping[str,Any]) -> dict[str,Any]:
    truth=instance.get("truth_function"); detected=bool(validation["fault_detected"])
    if truth is None: return {"designation":"matched_clean_control","fault_detected":detected,"false_positive":detected,"correct_job_attribution":False,"exact_function_localisation":False,"truth_job":None,"truth_function":None}
    return {"designation":"upstream_fault","fault_detected":detected,"false_positive":False,"correct_job_attribution":detected and validation["suspect_job"]=="job_upstream_demand_provenance","exact_function_localisation":detected and validation["suspect_job"]=="job_upstream_demand_provenance" and validation["normalized_suspect_function"]==truth,"truth_job":"job_upstream_demand_provenance","truth_function":truth}


def _provider_review(repo_root: Path, attempt_root: Path, request: Mapping[str,Any], parent_id: str) -> dict[str,Any]:
    return ce._provider_call(repo_root,attempt_root,kind="review",model_request=request,controller_parent_id=parent_id,review_prompt=PROMPT,review_schema=RESPONSE_SCHEMA)


def _call_record(response: Mapping[str,Any]) -> dict[str,Any]:
    return {key:deepcopy(response.get(key)) for key in ("request_sha256","call_ids","retry_lineage","attempt_count") if response.get(key) is not None}


def run_review_session(repo_root: Path, attempt_root: Path, catalogue: Mapping[str,Any], package: Mapping[str,Any], trial_id: str, mode: str) -> dict[str,Any]:
    initial=_provider_review(repo_root,attempt_root,render_request(package),trial_id); pre=validate_response(catalogue,package,initial); usage=[ce.actual_usage_record(initial,purpose="initial_review",phase="n20_review")]; calls=[_call_record(initial)]; current=deepcopy(dict(package)); final=pre; event=None
    action=pre["receipt"]["next_action"]; name=str(action["action"]); required=mode=="adaptive_required_one_guided"; adaptive=mode in {"adaptive_voluntary_guided","adaptive_required_one_guided"}
    if name=="helper_expansion":
        if not adaptive: raise ValueError("non-Adaptive N20 arm requested an unavailable expansion")
        boundary=str(action["boundary_id"]); group=str(action["child_group_id"])
        if not boundary or not group: raise ValueError("N20 expansion lacks one exact target")
        current,event=expand_child(catalogue,current,boundary_id=boundary,child_group_id=group)
        current["available_operations"]=[]; current["action_contract"]["permitted_actions"]=["finalize"]
        response=_provider_review(repo_root,attempt_root,render_request(current,operation_response=event),f"{trial_id}-follow-up-01"); final=validate_response(catalogue,current,response)
        if final["receipt"]["next_action"]["action"]!="finalize": raise ValueError("N20 post-expansion response did not finalize")
        usage.append(ce.actual_usage_record(response,purpose="helper_expansion_follow_up",phase="n20_review")); calls.append(_call_record(response))
    elif name=="finalize":
        if action["boundary_id"] or action["child_group_id"]: raise ValueError("N20 finalize action contains an operation target")
        if required: raise RuntimeError("N20 Required-One did not complete a model-selected expansion")
    else: raise ValueError("unknown N20 action")
    runtime=current.get("runtime_evidence",{}); nodes=runtime.get("nodes",[])
    return {"pre_validation":pre,"final_validation":final,"operation_event":event,"completed_expansion_count":1 if event else 0,"disclosed_node_count":len(nodes),"disclosed_relationship_count":len(runtime.get("relationships",[])),"source_visible":any(node.get("source") is not None for node in nodes),"values_visible":any(node.get("artifact_content") is not None or node.get("value_preview") is not None for node in nodes),"call_records":calls,"usage":ce.aggregate_actual_usage_records(usage)}


def _summary(rows: list[Mapping[str,Any]]) -> dict[str,Any]:
    faults=[x for x in rows if x["designation"]=="upstream_fault"]; controls=[x for x in rows if x["designation"]=="matched_clean_control"]; calls=[call for row in rows for call in row["raw_calls"]]; functions:dict[str,int]={}; jobs:dict[str,int]={}
    for row in rows:
        function=str(row.get("suspect_function") or "no_suspect"); functions[function]=functions.get(function,0)+1; job=str(row.get("suspect_job") or "no_suspect"); jobs[job]=jobs.get(job,0)+1
    return {"reviews":len(rows),"provider_calls":len(calls),"fault_detection":{"numerator":sum(x["fault_detected"] for x in faults),"denominator":len(faults)},"correct_job_attribution":{"numerator":sum(x["correct_job_attribution"] for x in faults),"denominator":len(faults)},"exact_function_localisation":{"numerator":sum(x["exact_function_localisation"] for x in faults),"denominator":len(faults)},"control_false_positives":{"numerator":sum(x["false_positive"] for x in controls),"denominator":len(controls)},"expansion_sessions":sum(x["completed_expansion_count"] for x in rows),"disclosed_nodes":sum(x["disclosed_node_count"] for x in rows),"disclosed_relationships":sum(x["disclosed_relationship_count"] for x in rows),"selected_job_distribution":jobs,"selected_function_distribution":functions,"input_tokens":sum(int(x.get("input_tokens") or 0) for x in calls),"cached_input_tokens":sum(int(x.get("cached_input_tokens") or 0) for x in calls),"output_tokens":sum(int(x.get("output_tokens") or 0) for x in calls)}


def _rate(summary: Mapping[str,Any], key: str) -> float:
    value=summary[key]; return value["numerator"]/value["denominator"] if value["denominator"] else 0.0


def write_analysis(attempt_root: Path, reviews: Mapping[tuple[str,int],Mapping[str,Any]]) -> Path:
    rows=[]; raw_calls=[]
    for record in reviews.values():
        trial=record["controller_trial"]; calls=[]
        for index,call in enumerate(record["usage"].get("calls",[]),1): tagged={"trial_id":trial["trial_id"],"call_index":index,**deepcopy(call)}; calls.append(tagged); raw_calls.append(tagged)
        rows.append({**deepcopy(trial),"designation":record["designation"],"fault_group":record["fault_group"],"truth_function":record["truth_function"],"fault_detected":record["fault_detected"],"false_positive":record["false_positive"],"correct_job_attribution":record["correct_job_attribution"],"exact_function_localisation":record["exact_function_localisation"],"pre_fault_detected":record["pre_fault_detected"],"pre_suspect_job":record["pre_suspect_job"],"pre_suspect_function":record["pre_suspect_function"],"suspect_job":record["suspect_job"],"suspect_function":record["suspect_function"],"suspect_boundary_id":record["suspect_boundary_id"],"completed_expansion_count":record["completed_expansion_count"],"selected_expansion":deepcopy(record["selected_expansion"]),"disclosed_node_count":record["disclosed_node_count"],"disclosed_relationship_count":record["disclosed_relationship_count"],"source_visible":record["source_visible"],"values_visible":record["values_visible"],"diagnosis_changed_after_expansion":record["pre_suspect_job"]!=record["suspect_job"] or record["pre_suspect_function"]!=record["suspect_function"],"raw_calls":calls})
    by_mode={mode:_summary([x for x in rows if x["evidence_mode"]==mode]) for mode in MODES}; by_fault={fault:{mode:_summary([x for x in rows if x["instance_id"]==fault and x["evidence_mode"]==mode]) for mode in MODES} for fault in INSTANCES}; by_group={group:{mode:_summary([x for x in rows if x["fault_group"]==group and x["evidence_mode"]==mode]) for mode in MODES} for group in sorted(set(FAULT_GROUP.values()))}
    pairs=(("required_vs_current","current_open","adaptive_required_one_guided"),("voluntary_vs_current","current_open","adaptive_voluntary_guided"),("fixed_vs_current","current_open","compact_fixed_guided"),("required_vs_fixed","compact_fixed_guided","adaptive_required_one_guided"),("voluntary_vs_fixed","compact_fixed_guided","adaptive_voluntary_guided"),("empty_vs_current","current_open","etiq_empty_open")); contrasts=[]
    for name,left,right in pairs: contrasts.append({"name":name,"left":left,"right":right,**{f"{key}_rate_difference_right_minus_left":_rate(by_mode[right],key)-_rate(by_mode[left],key) for key in ("fault_detection","correct_job_attribution","exact_function_localisation","control_false_positives")}})
    analysis={"schema_version":"n20-boundary-bundled-analysis-1","scope_limitation":"Six prespecified mutants share one clean base pipeline; three repetitions are repeated model calls, not independent faults.","claim_boundary":"Current-to-guided differences are the total effect of the integrated boundary-plus-graph treatment, not graph alone.","review_count":len(rows),"repair_trace_count":0,"mode_summaries":by_mode,"fault_mode_summaries":by_fault,"fault_group_mode_summaries":by_group,"primary_contrasts":contrasts,"adaptive_pre_post":[deepcopy(x) for x in rows if x["evidence_mode"] in {"adaptive_voluntary_guided","adaptive_required_one_guided"}],"voluntary_expansion_uptake":{"numerator":sum(x["completed_expansion_count"] for x in rows if x["evidence_mode"]=="adaptive_voluntary_guided"),"denominator":sum(x["evidence_mode"]=="adaptive_voluntary_guided" for x in rows)},"required_one_completion":{"numerator":sum(x["completed_expansion_count"] for x in rows if x["evidence_mode"]=="adaptive_required_one_guided"),"denominator":sum(x["evidence_mode"]=="adaptive_required_one_guided" for x in rows)},"rows":sorted(rows,key=lambda x:x["schedule_position"]),"raw_per_call_tokens":raw_calls,"actual_usage":ce.aggregate_actual_usage_records(raw_calls)}; analysis["analysis_sha256"]=ce.sha256(analysis); path=attempt_root/"analysis/summary.json"; ce._write_immutable(path,analysis); return path


def _write_report(repo_root: Path, attempt_root: Path) -> Path:
    analysis=ce._read_json(attempt_root/"analysis/summary.json"); replay=ce._read_json(attempt_root/"replay/reconciliation.json")
    labels={"current_open":"Current Open","etiq_empty_open":"Etiq Empty Open","compact_fixed_guided":"Compact Fixed Guided","adaptive_voluntary_guided":"Adaptive Voluntary Guided","adaptive_required_one_guided":"Adaptive Required-One Guided"}
    lines=["# Attempt 034 — boundary-plus-graph upstream-fault comparison","",f"Completed 105 reviews, {replay['observed_counts']['logical_provider_calls']} logical provider calls, and zero repairs.","","The six prespecified mutants share one clean base pipeline. Each package's three repetitions are repeated model calls, not independent faults. Current-to-guided differences estimate the total integrated boundary-plus-graph treatment, not graph alone.","","## Results by fault","","| Fault | Group | Arm | Detected | Job 1 | Exact function | Calls | Input | Cached | Output |","|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for fault in FAULTS:
        for mode in MODES:
            x=analysis["fault_mode_summaries"][fault][mode]; lines.append(f"| {fault} | {FAULT_GROUP[fault]} | {labels[mode]} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['provider_calls']} | {x['input_tokens']} | {x['cached_input_tokens']} | {x['output_tokens']} |")
    lines += ["","## Overall modes and clean control","","| Arm | Detection | Job 1 | Exact function | Control FP | Expansions | Calls | Input | Cached | Output |","|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        x=analysis["mode_summaries"][mode]; lines.append(f"| {labels[mode]} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} | {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']} | {x['expansion_sessions']} | {x['provider_calls']} | {x['input_tokens']} | {x['cached_input_tokens']} | {x['output_tokens']} |")
    lines += ["","## Fault groups","","| Group | Arm | Detected | Job 1 | Exact function |","|---|---|---:|---:|---:|"]
    for group,modes in analysis["fault_group_mode_summaries"].items():
        for mode in MODES:
            x=modes[mode]; lines.append(f"| {group} | {labels[mode]} | {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']} | {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']} | {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']} |")
    lines += ["","## Adaptive pre/post decisions","","| Trial | Instance | Arm | Pre job/function | Final job/function | Selected expansion | Nodes | Relationships | Changed |","|---|---|---|---|---|---|---:|---:|---|"]
    for row in analysis["adaptive_pre_post"]:
        expansion=row["selected_expansion"] or {}; selected=f"{expansion.get('resolved_job_id','none')}:{expansion.get('boundary_id','none')}:{expansion.get('child_group_id','none')}" if expansion else "none"; lines.append(f"| {row['trial_id']} | {row['instance_id']} | {row['evidence_mode']} | {row['pre_suspect_job'] or 'none'}/{row['pre_suspect_function'] or 'none'} | {row['suspect_job'] or 'none'}/{row['suspect_function'] or 'none'} | {selected} | {row['disclosed_node_count']} | {row['disclosed_relationship_count']} | {row['diagnosis_changed_after_expansion']} |")
    lines += ["","## All 105 individual reviews","","| Pos | Trial | Instance | Arm | Rep | Detected/FP | Job | Function | Exact | Expansion | Calls | Input | Cached | Output |","|---:|---|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|"]
    for row in analysis["rows"]:
        calls=row["raw_calls"]; outcome="detected" if row["fault_detected"] else "FP" if row["false_positive"] else "clean/miss"; lines.append(f"| {row['schedule_position']} | {row['trial_id']} | {row['instance_id']} | {row['evidence_mode']} | {row['repetition']} | {outcome} | {row['suspect_job'] or 'none'} | {row['suspect_function'] or 'none'} | {row['exact_function_localisation']} | {row['completed_expansion_count']} | {len(calls)} | {sum(int(x.get('input_tokens') or 0) for x in calls)} | {sum(int(x.get('cached_input_tokens') or 0) for x in calls)} | {sum(int(x.get('output_tokens') or 0) for x in calls)} |")
    lines += ["","## Limitations","","- This compares open review with the complete integrated boundary-plus-graph treatment; it does not isolate graph structure alone.","- All six mutations share one clean base pipeline.","- Repetitions are repeated reviewer calls rather than independent fault instances.","- Cached input tokens are included within input tokens and must not be added to them.",""]
    path=repo_root/"docs/workshops/n20-boundary-bundled-upstream-faults-complete-findings.md"; path.parent.mkdir(parents=True,exist_ok=True); create_bytes_exclusive(path,"\n".join(lines).encode()); return path


def _write_handoff(repo_root: Path, attempt_root: Path) -> Path:
    freeze=ce._read_json(attempt_root/"experiment-freeze.json"); analysis=ce._read_json(attempt_root/"analysis/summary.json"); replay=ce._read_json(attempt_root/"replay/reconciliation.json"); terminal=ce._read_json(attempt_root/"terminal-state.json"); report=repo_root/"docs/workshops/n20-boundary-bundled-upstream-faults-complete-findings.md"
    artifacts={"freeze":attempt_root/"experiment-freeze.json","mutation_qualification":attempt_root/"qualification/mutation-summary.json","captures":attempt_root/"captures","catalogues":attempt_root/"catalogues","packages":attempt_root/"packages","reviews":attempt_root/"reviews","analysis":attempt_root/"analysis/summary.json","replay":attempt_root/"replay/reconciliation.json","terminal":attempt_root/"terminal-state.json","report":report}; hashes={name:ce.sha256(ce._tree_hashes(path)) if path.is_dir() else ce.sha256(path.read_bytes()) for name,path in artifacts.items()}
    lines=["To: Overseer","From: Developer","Subject: N20 Attempt 034 boundary-plus-graph results","",f"Status: {terminal['status']}",f"Authority: `{AUTHORITY}` (`{AUTHORITY_SHA256}`)",f"Freeze logical SHA-256: `{freeze['freeze_sha256']}`","","Counts",f"- Faults: 6; clean controls: 1",f"- Packages: 35; reviews: 105; repairs: 0",f"- Logical provider calls: {replay['observed_counts']['logical_provider_calls']}",f"- Required-One completion: {analysis['required_one_completion']['numerator']}/{analysis['required_one_completion']['denominator']}",f"- Voluntary uptake: {analysis['voluntary_expansion_uptake']['numerator']}/{analysis['voluntary_expansion_uptake']['denominator']}","","Mode results",""]
    for mode in MODES:
        x=analysis["mode_summaries"][mode]; lines.append(f"- {mode}: detected {x['fault_detection']['numerator']}/{x['fault_detection']['denominator']}; Job 1 {x['correct_job_attribution']['numerator']}/{x['correct_job_attribution']['denominator']}; exact function {x['exact_function_localisation']['numerator']}/{x['exact_function_localisation']['denominator']}; control FP {x['control_false_positives']['numerator']}/{x['control_false_positives']['denominator']}.")
    lines += ["","Exact artifact hashes",""]+[f"- `{artifacts[name].relative_to(repo_root)}`: `{digest}`" for name,digest in hashes.items()]+["","Attempts 032 and 033 remained unchanged. No prior model request or response was reused. No source bundle was supplied. The qualified provider, authentication, sandbox, artifact execution and graph operation implementations were unchanged.",""]
    path=repo_root/"instructions_between_agent_types/developer/handoffs/N20_attempt_034_boundary_bundled_results_to_overseer.email.md"; path.parent.mkdir(parents=True,exist_ok=True); create_bytes_exclusive(path,"\n".join(lines).encode()); return path


def execute_lifecycle(repo_root: Path, attempt_root: Path) -> Path:
    repo_root=repo_root.resolve(); attempt_root=attempt_root.resolve(); verified=verify_frozen_attempt(repo_root,attempt_root); create_live_consumption(repo_root,attempt_root); catalogues,packages,records=_load_frozen(attempt_root); trials=ce._read_json(attempt_root/"review-design.json")["review_trials"]; instances={key:ce._read_json(attempt_root/"instances"/f"{key}.json") for key in INSTANCES}; reviews={}
    for trial in trials:
        path=attempt_root/"reviews"/f"{trial['trial_id']}.json"
        if path.exists():
            record=ce._read_json(path); ce._verified_self_hash(record,"review_sha256")
            if record.get("controller_trial")!=trial or record.get("status")!="complete": raise ValueError("invalid N20 partial review")
        else:
            package_record=packages[str(trial["branch_id"])]; package=package_record["reviewer_package"]; session=run_review_session(repo_root,attempt_root,catalogues[str(trial["instance_id"])],package,str(trial["trial_id"]),str(trial["evidence_mode"])); final=session["final_validation"]; pre=session["pre_validation"]; outcome=score_response(instances[str(trial["instance_id"])],final); event=session["operation_event"]
            record={"schema_version":"n20-open-review-record-1","controller_trial":deepcopy(trial),"package_sha256":package_record["package_sha256"],"receipt":deepcopy(final["receipt"]),"pre_fault_detected":pre["fault_detected"],"pre_suspect_job":pre["suspect_job"],"pre_suspect_function":pre["normalized_suspect_function"],"suspect_job":final["suspect_job"],"suspect_function":final["normalized_suspect_function"],"suspect_boundary_id":final["suspect_boundary_id"],**outcome,"fault_group":instances[str(trial["instance_id"])]["fault_group"],"completed_expansion_count":session["completed_expansion_count"],"selected_expansion":({key:deepcopy(event.get(key)) for key in ("resolved_job_id","boundary_id","child_group_id","nodes_added","relationships_added")} if event else None),"disclosed_node_count":session["disclosed_node_count"],"disclosed_relationship_count":session["disclosed_relationship_count"],"source_visible":session["source_visible"],"values_visible":session["values_visible"],"call_records":session["call_records"],"usage":session["usage"],"status":"complete"}; record["review_sha256"]=ce.sha256(record); ce._write_immutable(path,record)
        reviews[(str(trial["branch_id"]),int(trial["repetition"]))]=record
    required=[x for x in reviews.values() if x["controller_trial"]["evidence_mode"]=="adaptive_required_one_guided"]
    if len(reviews)!=105 or len(required)!=21 or any(x["completed_expansion_count"]!=1 for x in required): raise RuntimeError("N20 review or Required-One invariant failed")
    call_ids=[str(call_id) for record in reviews.values() for call in record["call_records"] for call_id in call.get("call_ids",[])]; logical_calls=sum(len(x["call_records"]) for x in reviews.values())
    if not 126<=logical_calls<=147 or len(call_ids)!=len(set(call_ids)): raise ValueError("N20 call count or lineage changed")
    for call_id in call_ids: verify_record(attempt_root/"ledger",record_type="call-attempt",record_id=call_id)
    analysis=ce._read_json(write_analysis(attempt_root,reviews)); replay={"schema_version":"n20-replay-1","freeze_sha256":verified["freeze_sha256"],"review_hashes":sorted(x["review_sha256"] for x in reviews.values()),"observed_counts":{"faults":6,"controls":1,"captures":7,"catalogues":7,"packages":len(records),"reviews":len(reviews),"repairs":0,"logical_provider_calls":logical_calls,"provider_attempt_call_ids":len(call_ids),"completed_helper_expansions":sum(x["completed_expansion_count"] for x in reviews.values()),"disclosed_nodes":sum(x["disclosed_node_count"] for x in reviews.values()),"disclosed_relationships":sum(x["disclosed_relationship_count"] for x in reviews.values())},"all_record_hashes_recomputed":True,"duplicate_logical_calls":False,"required_one_sessions_complete":True,"preserved_attempts_unchanged":all(ce.sha256(ce._tree_hashes(repo_root/path))==ce._read_json(attempt_root/"experiment-freeze.json")["preserved_attempt_tree_hashes"][name] for name,path in (("attempt-032",SOURCE_ATTEMPT),("attempt-033",PRESERVED_ATTEMPT)))}; replay["replay_sha256"]=ce.sha256(replay); ce._write_immutable(attempt_root/"replay/reconciliation.json",replay)
    terminal={"schema_version":"n20-terminal-1","status":"completed_experiment_and_analysis","fault_count":6,"control_count":1,"package_count":35,"review_count":105,"repair_trace_count":0,"analysis_sha256":analysis["analysis_sha256"],"replay_sha256":replay["replay_sha256"]}; terminal["terminal_sha256"]=ce.sha256(terminal); path=attempt_root/"terminal-state.json"; ce._write_immutable(path,terminal); _write_report(repo_root,attempt_root); _write_handoff(repo_root,attempt_root); return path


def run_lifecycle(repo_root: Path, attempt_root: Path | None=None) -> Path:
    target=(attempt_root or repo_root/ATTEMPT).resolve()
    try: return execute_lifecycle(repo_root,target)
    except Exception as exc:
        terminal={"schema_version":"n20-terminal-1","status":"terminal_incomplete","failure_stage":"n20_resumable_lifecycle","error":f"{type(exc).__name__}: {exc}","completed_review_records":len(list((target/"reviews").glob("*.json"))),"completed_repair_records":0}; terminal["terminal_sha256"]=ce.sha256(terminal); path=target/"terminal"/f"terminal-incomplete-{terminal['terminal_sha256'][7:23]}.json"; ce._write_immutable(path,terminal); return path


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("operation",choices=("build","freeze","verify","live")); parser.add_argument("--repo-root",default="."); parser.add_argument("--attempt-root",default=ATTEMPT.as_posix()); args=parser.parse_args(); repo=Path(args.repo_root).resolve(); attempt=Path(args.attempt_root); attempt=attempt if attempt.is_absolute() else repo/attempt
    try:
        if args.operation=="build":
            built=build_attempt(repo,attempt); print(json.dumps({"qualification":built["qualification"],"counts":{"captures":len(built["captures"]),"catalogues":len(built["catalogues"]),"packages":len(built["packages"]),"reviews":len(built["schedule"]["review_trials"]),"repairs":0}},indent=2))
        elif args.operation=="freeze": print(freeze_attempt(repo,attempt))
        elif args.operation=="verify": print(json.dumps(verify_frozen_attempt(repo,attempt),indent=2))
        else:
            path=run_lifecycle(repo,attempt); print(path); return 0 if ce._read_json(path).get("status")=="completed_experiment_and_analysis" else 1
    except Exception as exc: print(f"N20 experiment failed: {type(exc).__name__}: {exc}"); return 1
    return 0


if __name__=="__main__": raise SystemExit(main())
