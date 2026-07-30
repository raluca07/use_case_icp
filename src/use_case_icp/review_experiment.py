from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .codex_runner import CodexRunner
from .job_store import JobStore
from .records import (
    BoundaryHealth,
    ContextArtifact,
    EtiqEvidenceSnapshot,
    EtiqNodeRecord,
    EtiqRelationshipRecord,
    EvidenceReviewUnit,
    ReviewSection,
    jsonable,
    new_id,
    stable_hash,
)
from .review import frame_name, review_node_payload, review_relationship_payload, visible_evidence


EXPERIMENT_MODES = (
    "semantic_only",
    "history_full",
    "etiq_full",
    "etiq_selected",
)

HISTORY_ROOT_FILES = {
    "events.jsonl",
    "request.json",
    "segments.json",
    "state.json",
}
HISTORY_RUN_FILES = {
    "applied-repair.json",
    "authoring-retry.json",
    "authoring-semantic.json",
    "execution-error.json",
    "parent-run.json",
    "pipeline-input.json",
    "pipeline-stderr.log",
    "pipeline-stdout.log",
    "repair-diff.json",
    "repair-target.json",
    "semantic-result.json",
}


def _run_dir(store: JobStore, job_id: str, run_id: str) -> Path:
    matches = list(store.job_dir(job_id).glob(f"stages/*/*/runs/{run_id}"))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one run named {run_id}, found {len(matches)}")
    return matches[0]


def _snapshot(store: JobStore, run_dir: Path) -> EtiqEvidenceSnapshot:
    summary = store.read_json(run_dir / "etiq-snapshot.json")
    return EtiqEvidenceSnapshot(
        snapshot_id=str(summary["snapshot_id"]),
        job_id=str(summary["job_id"]),
        run_id=str(summary["run_id"]),
        nodes=[
            EtiqNodeRecord(**item)
            for item in store.read_json(run_dir / "etiq-nodes.json", [])
        ],
        relationships=[
            EtiqRelationshipRecord(**item)
            for item in store.read_json(run_dir / "etiq-relationships.json", [])
        ],
        inventories=store.read_json(run_dir / "etiq-inventory.json", {}),
        scan_errors=store.read_json(run_dir / "etiq-scan-errors.json", []),
        created_at=str(summary["created_at"]),
        schema_version=str(summary["schema_version"]),
    )


def _units(store: JobStore, run_dir: Path) -> list[EvidenceReviewUnit]:
    units: list[EvidenceReviewUnit] = []
    for item in store.read_json(run_dir / "review-boundaries.json", []):
        payload = dict(item)
        payload["boundary_health"] = BoundaryHealth(**payload["boundary_health"])
        units.append(EvidenceReviewUnit(**payload))
    return units


def _sections(store: JobStore, run_dir: Path) -> list[ReviewSection]:
    return [
        ReviewSection(**item)
        for item in store.read_json(run_dir / "review-sections.json", [])
    ]


def _source_bundle(store: JobStore, run_dir: Path) -> dict[str, str]:
    manifest = store.read_json(run_dir / "pipeline-manifest.json", {})
    return {
        str(path): (run_dir / "pipeline" / str(path)).read_text(encoding="utf-8")
        for path in manifest.get("file_hashes", {})
    }


def _unit_key(unit: EvidenceReviewUnit) -> str:
    return " > ".join(frame_name(frame) for frame in unit.func_stack_prefix)


def history_artifacts(
    store: JobStore,
    job_ids: list[str],
    *,
    exclude: set[Path] | None = None,
    target_job_id: str | None = None,
    target_run_dir: Path | None = None,
) -> list[dict[str, Any]]:
    excluded = {path.resolve() for path in (exclude or set())}
    visible_target_runs: set[str] = set()
    if target_job_id and target_run_dir:
        current = target_run_dir
        while current.name not in visible_target_runs:
            visible_target_runs.add(current.name)
            parent = store.read_json(current / "parent-run.json", {})
            parent_run_id = str(parent.get("parent_run_id") or "")
            if not parent_run_id:
                break
            matches = list(
                store.job_dir(target_job_id).glob(
                    f"stages/*/*/runs/{parent_run_id}"
                )
            )
            if len(matches) != 1:
                raise FileNotFoundError(
                    f"history parent run not found: {parent_run_id}"
                )
            current = matches[0]
    artifacts: list[dict[str, Any]] = []
    for job_id in job_ids:
        job_dir = store.job_dir(job_id)
        if not job_dir.exists():
            raise FileNotFoundError(f"history job not found: {job_id}")
        candidates = [
            *(job_dir / name for name in sorted(HISTORY_ROOT_FILES)),
            *sorted(job_dir.glob("final/result.json")),
            *sorted(job_dir.glob("stages/*/*/runs/*/pipeline/*.py")),
            *(
                path
                for name in sorted(HISTORY_RUN_FILES)
                for path in sorted(job_dir.glob(f"stages/*/*/runs/*/{name}"))
            ),
        ]
        for path in candidates:
            if not path.is_file() or path.resolve() in excluded:
                continue
            relative = path.relative_to(job_dir).as_posix()
            parts = Path(relative).parts
            if job_id == target_job_id:
                if relative in {"events.jsonl", "state.json", "final/result.json"}:
                    continue
                if "runs" in parts:
                    run_id = parts[parts.index("runs") + 1]
                    if run_id not in visible_target_runs:
                        continue
                    if (
                        target_run_dir
                        and run_id == target_run_dir.name
                        and path.name in {"repair-diff.json", "repair-target.json"}
                    ):
                        continue
            text = path.read_text(encoding="utf-8")
            content: Any = text
            if path.suffix == ".json":
                content = json.loads(text)
            artifacts.append(
                {
                    "ref": f"history:{job_id}:{relative}",
                    "job_id": job_id,
                    "path": relative,
                    "content": content,
                }
            )
    return artifacts


def build_experiment_package(
    mode: str,
    *,
    store: JobStore,
    run_dir: Path,
    snapshot: EtiqEvidenceSnapshot,
    units: list[EvidenceReviewUnit],
    section: ReviewSection,
    history_job_ids: list[str] | None = None,
) -> dict[str, Any]:
    if mode not in EXPERIMENT_MODES:
        raise ValueError(f"unknown review experiment mode: {mode}")
    unit_by_id = {unit.unit_id: unit for unit in units}
    assigned = [unit_by_id[unit_id] for unit_id in section.assigned_unit_ids]
    context_units = [unit_by_id[unit_id] for unit_id in section.context_unit_ids]
    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    relationship_by_ref = {
        relationship.relationship_ref: relationship
        for relationship in snapshot.relationships
    }
    node_refs: set[str] = set()
    relationship_refs: set[str] = set()
    if mode == "etiq_full":
        node_refs.update(node_by_ref)
        relationship_refs.update(relationship_by_ref)
    elif mode == "etiq_selected":
        for unit in context_units:
            selection = visible_evidence(unit, snapshot)
            node_refs.update(selection["node_refs"])
            relationship_refs.update(selection["relationship_refs"])

    job_dir = store.job_dir(snapshot.job_id)
    source_paths = set((run_dir / "pipeline").rglob("*.py"))
    core_paths = {
        job_dir / "request.json",
        job_dir / "segments.json",
        run_dir / "pipeline-input.json",
        run_dir / "semantic-result.json",
        run_dir / "pipeline-stdout.log",
        run_dir / "pipeline-stderr.log",
        *source_paths,
    }
    accumulated_history = (
        history_artifacts(
            store,
            history_job_ids or [snapshot.job_id],
            exclude=core_paths,
            target_job_id=snapshot.job_id,
            target_run_dir=run_dir,
        )
        if mode == "history_full"
        else []
    )
    allowed_refs = {
        "job_request",
        "segments",
        "pipeline_input",
        "pipeline_source",
        "semantic_result",
        "pipeline_stdout",
        "pipeline_stderr",
        *(unit.unit_id for unit in assigned),
        *node_refs,
        *relationship_refs,
        *(artifact["ref"] for artifact in accumulated_history),
    }
    return {
        "mode": mode,
        "run_id": snapshot.run_id,
        "section": jsonable(section),
        "assigned_units": [
            {
                "unit_id": unit.unit_id,
                "unit_key": _unit_key(unit),
                "function_name": unit.function_name,
                "func_stack_prefix": unit.func_stack_prefix,
                "boundary_health": (
                    jsonable(unit.boundary_health) if mode != "semantic_only" else None
                ),
            }
            for unit in assigned
        ],
        "job_request": store.read_json(job_dir / "request.json", {}),
        "segments": store.read_json(job_dir / "segments.json", {}),
        "pipeline_input": store.read_json(run_dir / "pipeline-input.json", {}),
        "pipeline_source": _source_bundle(store, run_dir),
        "semantic_result": store.read_json(run_dir / "semantic-result.json", {}),
        "pipeline_stdout": (run_dir / "pipeline-stdout.log").read_text(encoding="utf-8"),
        "pipeline_stderr": (run_dir / "pipeline-stderr.log").read_text(encoding="utf-8"),
        "accumulated_history": accumulated_history,
        "captured_nodes": [
            review_node_payload(node_by_ref[ref])
            for ref in sorted(node_refs)
        ],
        "captured_relationships": [
            review_relationship_payload(relationship_by_ref[ref])
            for ref in sorted(relationship_refs)
        ],
        "allowed_evidence_refs": sorted(allowed_refs),
    }


def _issue_keys(
    reviews: list[dict[str, Any]],
    units: list[EvidenceReviewUnit],
) -> list[str]:
    key_by_id = {unit.unit_id: _unit_key(unit) for unit in units}
    return sorted(
        {
            key_by_id[str(review["unit_id"])]
            for review in reviews
            if review.get("decision") in {"failed", "suspect"}
            and str(review.get("unit_id")) in key_by_id
        }
    )


def summarize_experiment(
    records: list[dict[str, Any]],
    issue_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    arms: dict[str, dict[str, Any]] = {}
    for record in records:
        key = f"{record['run_label']}:{record['mode']}"
        arm = arms.setdefault(
            key,
            {
                "run_label": record["run_label"],
                "mode": record["mode"],
                "invocations": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "package_chars": 0,
                "etiq_node_count": 0,
                "etiq_relationship_count": 0,
                "history_artifact_count": 0,
                "issue_keys": set(),
            },
        )
        arm["invocations"] += 1
        arm["input_tokens"] += int(record.get("input_tokens") or 0)
        arm["output_tokens"] += int(record.get("output_tokens") or 0)
        arm["package_chars"] += int(record["package_chars"])
        arm["etiq_node_count"] += int(record.get("etiq_node_count") or 0)
        arm["etiq_relationship_count"] += int(
            record.get("etiq_relationship_count") or 0
        )
        arm["history_artifact_count"] += int(
            record.get("history_artifact_count") or 0
        )
        arm["issue_keys"].update(record["issue_keys"])

    for arm in arms.values():
        arm["issue_keys"] = sorted(arm["issue_keys"])
        arm["issue_count"] = len(arm["issue_keys"])
        arm["average_input_tokens"] = (
            round(arm["input_tokens"] / arm["invocations"])
            if arm["invocations"]
            else None
        )
        arm["average_package_chars"] = (
            round(arm["package_chars"] / arm["invocations"])
            if arm["invocations"]
            else None
        )
        arm["average_etiq_node_count"] = (
            round(arm["etiq_node_count"] / arm["invocations"])
            if arm["invocations"]
            else None
        )
        arm["average_etiq_relationship_count"] = (
            round(arm["etiq_relationship_count"] / arm["invocations"])
            if arm["invocations"]
            else None
        )
        arm["average_history_artifact_count"] = (
            round(arm["history_artifact_count"] / arm["invocations"])
            if arm["invocations"]
            else None
        )

    consensus_by_run: dict[str, dict[str, list[str]]] = {}
    for run_label in sorted({record["run_label"] for record in records}):
        run_arms = [
            set(arm["issue_keys"])
            for arm in arms.values()
            if arm["run_label"] == run_label
        ]
        consensus = set.intersection(*run_arms) if run_arms else set()
        all_issues = set.union(*run_arms) if run_arms else set()
        consensus_by_run[run_label] = {
            "consensus_core_issue_keys": sorted(consensus),
            "disputed_issue_keys": sorted(all_issues - consensus),
        }

    for arm in arms.values():
        reference = arms.get(f"{arm['run_label']}:etiq_selected")
        reference_issues = set(reference["issue_keys"]) if reference else set()
        found = set(arm["issue_keys"])
        arm["issue_recall_vs_selected"] = (
            round(len(found & reference_issues) / len(reference_issues), 4)
            if reference_issues
            else None
        )
        arm["additional_issue_keys_vs_selected"] = sorted(found - reference_issues)

    assessment = issue_assessment or {}
    verified_core = set(assessment.get("core_issue_keys", []))
    assessed_arms = assessment.get("arms", {})
    if verified_core:
        for key, arm in arms.items():
            found = set(arm["issue_keys"])
            arm_assessment = assessed_arms.get(key, {})
            misattributed = set(
                arm_assessment.get("misattributed_issue_keys", [])
            )
            false_positives = set(
                arm_assessment.get("false_positive_issue_keys", [])
            )
            verified_found = found & verified_core
            classified = verified_core | misattributed | false_positives
            arm["verified_core_issue_keys"] = sorted(verified_found)
            arm["verified_core_issue_count"] = len(verified_found)
            arm["verified_core_recall"] = round(
                len(verified_found) / len(verified_core), 4
            )
            arm["misattributed_issue_keys"] = sorted(found & misattributed)
            arm["misattributed_issue_count"] = len(found & misattributed)
            arm["false_positive_issue_keys"] = sorted(found & false_positives)
            arm["false_positive_issue_count"] = len(found & false_positives)
            arm["unclassified_issue_keys"] = sorted(found - classified)
            arm["secondary_findings"] = list(
                arm_assessment.get("secondary_findings", [])
            )
            denominator = (
                len(verified_found)
                + len(found & misattributed)
                + len(found & false_positives)
            )
            arm["verified_issue_precision"] = (
                round(len(verified_found) / denominator, 4)
                if denominator
                else None
            )

    run_labels = {record["run_label"] for record in records}
    resolved: dict[str, list[str]] = {}
    if {"baseline", "repaired"} <= run_labels:
        for mode in EXPERIMENT_MODES:
            baseline = set(arms[f"baseline:{mode}"]["issue_keys"])
            repaired = set(arms[f"repaired:{mode}"]["issue_keys"])
            resolved[mode] = sorted(baseline - repaired)
    return {
        "arms": arms,
        "consensus_by_run": consensus_by_run,
        "verified_core_issue_keys": sorted(verified_core),
        "resolved_issue_keys": resolved,
    }


def assess_review_experiment(
    *,
    store: JobStore,
    job_id: str,
    experiment_id: str,
    issue_assessment: dict[str, Any],
) -> None:
    if not experiment_id or "/" in experiment_id or ".." in experiment_id:
        raise ValueError("invalid experiment ID")
    experiment_dir = store.job_dir(job_id) / "experiments" / experiment_id
    result = store.read_json(experiment_dir / "result.json")
    if not isinstance(result, dict):
        raise FileNotFoundError(f"comparison not found: {experiment_id}")
    result["issue_assessment"] = issue_assessment
    result["summary"] = summarize_experiment(
        result.get("records", []),
        issue_assessment,
    )
    store.write_json(experiment_dir / "issue-assessment.json", issue_assessment)
    store.write_json(experiment_dir / "result.json", result)


def run_review_experiment(
    *,
    repo_root: Path,
    store: JobStore,
    codex: CodexRunner,
    job_id: str,
    baseline_run_id: str,
    repaired_run_id: str | None = None,
    repetitions: int = 1,
    section_ids: set[str] | None = None,
    history_job_ids: list[str] | None = None,
    execute: bool = False,
) -> str:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    experiment_id = new_id("review-comparison")
    experiment_dir = store.job_dir(job_id) / "experiments" / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=False)
    runs = [("baseline", baseline_run_id)]
    if repaired_run_id:
        runs.append(("repaired", repaired_run_id))
    accumulated_job_ids = list(
        dict.fromkeys([*(history_job_ids or []), job_id])
    )
    for history_job_id in accumulated_job_ids:
        if not store.job_dir(history_job_id).exists():
            raise FileNotFoundError(f"history job not found: {history_job_id}")
    config = {
        "experiment_id": experiment_id,
        "job_id": job_id,
        "model": codex.model,
        "baseline_run_id": baseline_run_id,
        "repaired_run_id": repaired_run_id,
        "modes": list(EXPERIMENT_MODES),
        "repetitions": repetitions,
        "section_ids": sorted(section_ids or []),
        "history_job_ids": accumulated_job_ids,
        "execute": execute,
    }
    store.write_json(experiment_dir / "experiment.json", config)
    prompt_template = (repo_root / "prompts" / "review_experiment.md").read_text(
        encoding="utf-8"
    )
    repository_instructions = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    schema = json.loads(
        (repo_root / "schemas" / "review.schema.json").read_text(encoding="utf-8")
    )
    records: list[dict[str, Any]] = []
    for run_label, run_id in runs:
        run_dir = _run_dir(store, job_id, run_id)
        snapshot = _snapshot(store, run_dir)
        units = _units(store, run_dir)
        sections = [
            section
            for section in _sections(store, run_dir)
            if not section_ids or section.section_id in section_ids
        ]
        if section_ids and len(sections) != len(section_ids):
            found = {section.section_id for section in sections}
            raise ValueError(
                f"unknown section IDs for {run_id}: {sorted(section_ids - found)}"
            )
        for section in sections:
            for mode in EXPERIMENT_MODES:
                package = build_experiment_package(
                    mode,
                    store=store,
                    run_dir=run_dir,
                    snapshot=snapshot,
                    units=units,
                    section=section,
                    history_job_ids=accumulated_job_ids,
                )
                for repetition in range(1, repetitions + 1):
                    if not execute:
                        records.append(
                            {
                                "run_label": run_label,
                                "run_id": run_id,
                                "section_id": section.section_id,
                                "mode": mode,
                                "repetition": repetition,
                                "invocation_id": None,
                                "input_tokens": None,
                                "output_tokens": None,
                                "package_chars": len(
                                    json.dumps(
                                        package,
                                        sort_keys=True,
                                        ensure_ascii=False,
                                    )
                                ),
                                "etiq_node_count": len(package["captured_nodes"]),
                                "etiq_relationship_count": len(
                                    package["captured_relationships"]
                                ),
                                "history_artifact_count": len(
                                    package["accumulated_history"]
                                ),
                                "issue_keys": [],
                                "reviews": [],
                            }
                        )
                        continue
                    context = {
                        "experiment": config,
                        "run_label": run_label,
                        "repetition": repetition,
                        "review_package": package,
                    }
                    prompt = (
                        "## Repository instructions\n\n"
                        f"{repository_instructions.strip()}\n\n"
                        f"{prompt_template.strip()}\n\n"
                        "## Context\n\n"
                        f"{json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False)}\n"
                    )
                    purpose = (
                        f"{experiment_id}_{run_label}_{mode}_"
                        f"{section.section_id}_r{repetition}"
                    )
                    result = codex.run(
                        job_id=job_id,
                        job_type="review_experiment",
                        purpose=purpose,
                        prompt=prompt,
                        output_schema=schema,
                        artifacts=[
                            ContextArtifact(
                                ref=f"experiment:{purpose}",
                                content_hash=stable_hash(context),
                                delivery="embedded",
                                purpose="review_context_comparison",
                                content=context,
                            )
                        ],
                    )
                    record = {
                        "run_label": run_label,
                        "run_id": run_id,
                        "section_id": section.section_id,
                        "mode": mode,
                        "repetition": repetition,
                        "invocation_id": result.invocation_id,
                        "input_tokens": result.usage.input_tokens,
                        "output_tokens": result.usage.output_tokens,
                        "package_chars": len(
                            json.dumps(package, sort_keys=True, ensure_ascii=False)
                        ),
                        "etiq_node_count": len(package["captured_nodes"]),
                        "etiq_relationship_count": len(
                            package["captured_relationships"]
                        ),
                        "history_artifact_count": len(
                            package["accumulated_history"]
                        ),
                        "issue_keys": _issue_keys(result.payload["reviews"], units),
                        "reviews": result.payload["reviews"],
                    }
                    records.append(record)
                    store.write_json(experiment_dir / "records.json", records)
    config["planned_or_completed_invocations"] = len(records)
    store.write_json(
        experiment_dir / "result.json",
        {
            **config,
            "records": records,
            "summary": summarize_experiment(records),
        },
    )
    return experiment_id
