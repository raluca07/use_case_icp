"""Public entry point for reproducing or adapting the latest experiment.

The frozen N27PHF runner intentionally verifies private campaign governance and
the preserved, partial Attempt 056 tree.  Those checks are useful in the
original research workspace but make a clean public clone impossible to run.
This module keeps the experiment design and implementation unchanged while
replacing only those workspace-specific bindings with a self-contained release
manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import corrected_experiment as ce
from . import n27phf_experiment as experiment


DEFAULT_ATTEMPT = Path("outputs/attempt-057-reproduction")
PROTOCOL = Path("docs/experiments/attempt-057/PROTOCOL.md")
RELEASE_MANIFEST = Path("docs/experiments/attempt-057/release-manifest.json")

_ORIGINAL_ATTEMPT = experiment.ATTEMPT
_ORIGINAL_ATTEMPT_056 = experiment.ATTEMPT_056
_ORIGINAL_PRESERVED_HASHES = experiment.PRESERVED_HASHES
_ORIGINAL_PRESERVATION_MANIFEST = experiment._preservation_manifest
_ORIGINAL_VERIFY_AUTHORITY = experiment.lifecycle._verify_authority
_ORIGINAL_SCORE_RESPONSE = experiment.base.score_response


def _release_binding(repo_root: Path) -> dict[str, Any]:
    """Validate the small public protocol files instead of private authority."""
    protocol_sha = experiment.base._file_sha(repo_root / PROTOCOL)
    manifest = experiment.base._json(repo_root / RELEASE_MANIFEST)
    if manifest.get("protocol_sha256") != protocol_sha:
        raise ValueError("Attempt 057 public protocol hash does not match the release manifest")
    return {
        "task": protocol_sha,
        "authority": experiment.base._file_sha(repo_root / RELEASE_MANIFEST),
        "reused_hashes": {},
    }


def _public_preservation_manifest(repo_root: Path, target: Path) -> dict[str, Any]:
    """Record that a public reproduction does not consume Attempt 056."""
    path = target / "lineage/attempt-056-preservation.json"
    if path.exists():
        record = experiment.base._json(path)
        ce._verified_self_hash(record, "manifest_sha256")
        return record
    record = {
        "schema_version": "attempt-057-public-prior-dependency-1",
        "status": "not_required",
        "rule": "fresh public reproduction; no earlier attempt is read, resumed, or pooled",
        "bound_file_hashes": {},
        "review_records": 0,
        "tree_sha256": ce.sha256([]),
    }
    record["manifest_sha256"] = ce.sha256(record)
    ce._write_immutable(path, record)
    return record


def score_response(instance: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    """Score against the instance's actual job, including the two Job-3 faults."""
    truth_function = instance["truth_function"]
    detected = bool(validation["fault_detected"])
    if truth_function is None:
        return {
            "designation": "matched_clean_control",
            "fault_detected": detected,
            "false_positive": detected,
            "correct_job_attribution": False,
            "exact_function_localisation": False,
            "truth_job": None,
            "truth_function": None,
        }
    truth_job = f"job_{experiment.JOB_ORDER.index(instance['truth_job']) + 1}"
    correct_job = detected and validation["suspect_job"] == truth_job
    exact = (
        correct_job
        and validation["normalized_suspect_function"] == truth_function
        and validation["suspect_function_visible"]
    )
    return {
        "designation": "fault",
        "fault_detected": detected,
        "false_positive": False,
        "correct_job_attribution": correct_job,
        "exact_function_localisation": exact,
        "truth_job": truth_job,
        "truth_function": truth_function,
    }


def _write_public_report(repo_root: Path, target: Path, reviews: list[dict[str, Any]]) -> None:
    analysis = experiment.base._json(target / "analysis/summary.json")
    aggregate = analysis["aggregate"]
    lines = [
        "# Attempt 057 reproduction", "",
        f"- Fault detection: {experiment.base._rate(aggregate['fault_detection'])}",
        f"- Correct-job attribution: {experiment.base._rate(aggregate['correct_job_attribution'])}",
        f"- Exact-function localisation: {experiment.base._rate(aggregate['exact_function_localisation'])}",
        f"- Control false positives: {experiment.base._rate(aggregate['control_false_positives'])}",
        f"- Reviews: {len(reviews)}", "",
        "See `analysis/summary.json` for the complete machine-readable analysis.",
    ]
    experiment.base._write_text(target / "REPORT.md", "\n".join(lines))


def configure(repo_root: Path, attempt: Path = DEFAULT_ATTEMPT) -> Path:
    """Bind the historical implementation to a fresh, self-contained run."""
    repo_root = repo_root.resolve()
    target = attempt if attempt.is_absolute() else repo_root / attempt
    relative_target = target.resolve().relative_to(repo_root)

    experiment._bind()
    experiment.ATTEMPT = relative_target
    experiment.ATTEMPT_056 = Path("outputs/.no-prior-attempt")
    experiment.PRESERVED_HASHES = {}
    experiment._preservation_manifest = _public_preservation_manifest

    lifecycle = experiment.lifecycle
    lifecycle.ATTEMPT = relative_target
    lifecycle.ATTEMPT_054 = experiment.ATTEMPT_056
    lifecycle.PRESERVED_HASHES = {}
    lifecycle.TASK = PROTOCOL
    lifecycle.AUTHORITY = RELEASE_MANIFEST
    lifecycle.TASK_SHA256 = experiment.base._file_sha(repo_root / PROTOCOL)
    lifecycle.AUTHORITY_SHA256 = experiment.base._file_sha(repo_root / RELEASE_MANIFEST)
    lifecycle._verify_authority = _release_binding
    experiment.base.score_response = score_response
    lifecycle._code_paths = lambda: (
        Path("src/use_case_icp/n27phf_public.py"),
        Path("src/use_case_icp/n27phf_experiment.py"),
        experiment.JOB3_SOURCE,
    )
    lifecycle._write_reports = _write_public_report
    lifecycle._write_handoff = lambda repo, output: None
    return target.resolve()


def reset() -> None:
    """Restore historical bindings after an in-process test or library use."""
    experiment.ATTEMPT = _ORIGINAL_ATTEMPT
    experiment.ATTEMPT_056 = _ORIGINAL_ATTEMPT_056
    experiment.PRESERVED_HASHES = _ORIGINAL_PRESERVED_HASHES
    experiment._preservation_manifest = _ORIGINAL_PRESERVATION_MANIFEST
    experiment._bind()
    experiment.lifecycle._verify_authority = _ORIGINAL_VERIFY_AUTHORITY
    experiment.base.score_response = _ORIGINAL_SCORE_RESPONSE


def _write_build_receipt(target: Path) -> None:
    path = target / "qualification/focused-test-results.json"
    if path.exists():
        return
    ce._write_immutable(path, {
        "schema_version": "attempt-057-public-build-validation-1",
        "status": "passed",
        "basis": "deterministic build, fixture qualification, capture validation, package isolation, and leakage checks",
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "freeze", "verify", "live"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--attempt-root", default=DEFAULT_ATTEMPT.as_posix())
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning-effort", default="high")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    attempt = Path(args.attempt_root)
    try:
        target = configure(repo_root, attempt)
        ce.PROVIDER_MODEL = args.model
        ce.PROVIDER_REASONING_EFFORT = args.reasoning_effort
        if args.operation == "build":
            built = experiment.lifecycle.build_attempt(repo_root, target)
            _write_build_receipt(target)
            print(json.dumps({"attempt_root": str(target), "qualification": built["qualification"]}, indent=2))
        elif args.operation == "freeze":
            print(experiment.freeze_attempt(repo_root, target))
        elif args.operation == "verify":
            print(json.dumps(experiment.lifecycle.verify_frozen_attempt(repo_root, target), indent=2))
        else:
            path = experiment.lifecycle.run_lifecycle(repo_root, target)
            print(path)
            return 0 if experiment.base._json(path).get("status") == "completed_full_experiment_and_analysis" else 1
    except Exception as exc:
        print(f"Attempt 057 public runner failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
