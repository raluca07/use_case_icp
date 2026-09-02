from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

from .codex_runner import DEFAULT_CODEX_MODEL, CodexRunner
from .controlled_experiment import run_controlled_experiment
from .etiq_executor import EXPECTED_ETIQ_VERSION, EtiqExecutor
from .workflow import WorkflowRunner
from .records import AgentRequest
from .review_experiment import assess_review_experiment, run_review_experiment
from .job_store import JobStore
from .dashboard import serve
from .fault_preflight import run_phase_a_preflight
from .fault_preflight_v2 import (
    run_phase_a_preflight_v2,
    run_phase_a_preflight_v2_n03,
    run_phase_a_preflight_v2_n04,
)


def _repo_root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    current = Path.cwd().resolve()
    if (current / "IMPLEMENTATION_PLAN.md").exists():
        return current
    return Path(__file__).resolve().parents[2]


def _job_model(value: str) -> str:
    match = re.match(r"^gpt-(\d+)\.(\d+)(?:-|$)", value)
    if match and (int(match.group(1)), int(match.group(2))) > (5, 5):
        raise argparse.ArgumentTypeError("job model must be GPT-5.5 or below")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="use-case-icp")
    parser.add_argument("--repo-root", help="repository containing prompts and schemas")
    parser.add_argument("--output-root", default="outputs/jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="check runtime integrations")
    doctor.set_defaults(action="doctor")

    run = subparsers.add_parser("run", help="run the synchronous workflow")
    run.add_argument("--product", required=True)
    run.add_argument("--audience", required=True)
    run.add_argument("--max-segments", type=int, default=5)
    run.add_argument("--model", type=_job_model, default=DEFAULT_CODEX_MODEL)
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument(
        "--max-authoring-retries",
        type=int,
        default=2,
        help="fresh Codex rewrites allowed when a generated pipeline cannot reach review",
    )
    run.add_argument("--max-repairs", type=int, default=6)
    run.set_defaults(action="run")

    show = subparsers.add_parser("show", help="print a job state")
    show.add_argument("job_id")
    show.set_defaults(action="show")

    compare = subparsers.add_parser(
        "compare-review",
        help="compare compact semantic, accumulated history, full-Etiq, and selected-Etiq review context",
    )
    compare.add_argument("job_id")
    compare.add_argument("--baseline-run", required=True)
    compare.add_argument("--repaired-run")
    compare.add_argument("--repetitions", type=int, default=1)
    compare.add_argument(
        "--section",
        action="append",
        dest="sections",
        help="limit comparison to one section ID; repeat for multiple sections",
    )
    compare.add_argument(
        "--history-job",
        action="append",
        dest="history_jobs",
        help=(
            "add an earlier job to history_full context; repeat in chronological "
            "order (the target job is always included)"
        ),
    )
    compare.add_argument(
        "--execute",
        action="store_true",
        help="invoke Codex; without this flag only package sizes are planned",
    )
    compare.add_argument("--model", type=_job_model, default=DEFAULT_CODEX_MODEL)
    compare.add_argument("--timeout", type=int, default=1800)
    compare.set_defaults(action="compare_review")

    assess = subparsers.add_parser(
        "assess-review",
        help="attach a source-verified issue assessment to a review comparison",
    )
    assess.add_argument("job_id")
    assess.add_argument("experiment_id")
    assess.add_argument("assessment_json")
    assess.set_defaults(action="assess_review")

    controlled = subparsers.add_parser(
        "compare-control",
        help="run isolated review-repair-replay branches against one frozen corpus",
    )
    controlled.add_argument("job_id")
    controlled.add_argument("--baseline-run", required=True)
    controlled.add_argument("--max-repairs", type=int, default=3)
    controlled.add_argument("--model", type=_job_model, default=DEFAULT_CODEX_MODEL)
    controlled.add_argument("--timeout", type=int, default=1800)
    controlled.set_defaults(action="compare_control")

    preflight = subparsers.add_parser(
        "fault-preflight-phase-a",
        help="author, stabilize, validate, and mutate the excluded C07 Phase-A fixture",
    )
    preflight.add_argument("--model", type=_job_model, default=DEFAULT_CODEX_MODEL)
    preflight.add_argument("--timeout", type=int, default=1800)
    preflight.add_argument(
        "--preflight-output-root",
        default="outputs/fault-experiments/preflight",
    )
    preflight.set_defaults(action="fault_preflight_phase_a")

    preflight_v2 = subparsers.add_parser(
        "fault-preflight-phase-a-v2",
        help="refuse the consumed terminal N02 Phase-A authority",
    )
    preflight_v2.add_argument("--model", type=_job_model, default="gpt-5.5")
    preflight_v2.add_argument("--timeout", type=int, default=1800)
    preflight_v2.set_defaults(action="fault_preflight_phase_a_v2")

    preflight_v2_n03 = subparsers.add_parser(
        "fault-preflight-phase-a-v2-n03",
        help="consume the one-use N03 v2 Phase-A authority",
    )
    preflight_v2_n03.add_argument("--model", type=_job_model, default="gpt-5.5")
    preflight_v2_n03.add_argument("--timeout", type=int, default=1800)
    preflight_v2_n03.set_defaults(action="fault_preflight_phase_a_v2_n03")

    preflight_v2_n04 = subparsers.add_parser(
        "fault-preflight-phase-a-v2-n04",
        help="consume the one-use N04 v2 Phase-A authority",
    )
    preflight_v2_n04.add_argument("--model", type=_job_model, default="gpt-5.5")
    preflight_v2_n04.add_argument("--timeout", type=int, default=1800)
    preflight_v2_n04.set_defaults(action="fault_preflight_phase_a_v2_n04")

    n05 = subparsers.add_parser(
        "fault-experiment-v2-1",
        help="run a zero-model N05 qualification, isolation, operational, or replay gate",
    )
    n05.add_argument(
        "operation",
        choices=("qualification", "isolation", "operational", "replay"),
    )
    n05.add_argument("--gate-output-root")
    n05.set_defaults(action="fault_experiment_v2_1")

    n07 = subparsers.add_parser(
        "fault-experiment-v2-2-n07",
        help="validate or execute the continuous protocol-2.2 N07 lifecycle",
    )
    mode = n07.add_mutually_exclusive_group()
    mode.add_argument("--check-ready", action="store_true")
    mode.add_argument("--qualify-lifecycle", action="store_true")
    n07.add_argument("--qualification-authority")
    n07.add_argument("--tester-gate")
    n07.add_argument(
        "--output-root",
        dest="n07_output_root",
        default="outputs/fault-experiments-v2-2-n07",
    )
    n07.add_argument(
        "--stop-after",
        choices=(
            "phase_a", "construction", "capture", "package",
            "review", "repair", "closure", "analysis", "replay",
        ),
        help=argparse.SUPPRESS,
    )
    n07.set_defaults(action="fault_experiment_v2_2_n07")

    n08 = subparsers.add_parser(
        "fault-experiment-v2-2-n08",
        help="check the localized correction or execute the continuous N08 lifecycle",
    )
    n08.add_argument("--check-ready", action="store_true")
    n08.add_argument(
        "--output-root",
        dest="n08_output_root",
        default="outputs/fault-experiments-v2-2-n08",
    )
    n08.set_defaults(action="fault_experiment_v2_2_n08")

    n09 = subparsers.add_parser(
        "fault-experiment-v2-2-n09",
        help="check N09 correction readiness or continue the existing candidate set",
    )
    n09.add_argument("--check-ready", action="store_true")
    n09.add_argument(
        "--output-root",
        dest="n09_output_root",
        default="outputs/fault-experiments-v2-2-n09",
    )
    n09.set_defaults(action="fault_experiment_v2_2_n09")

    n10 = subparsers.add_parser(
        "fault-experiment-v2-2-n10",
        help="qualify or continuously execute the complete N10 protocol-2.2 controller",
    )
    n10_mode = n10.add_mutually_exclusive_group()
    n10_mode.add_argument("--check-ready", action="store_true")
    n10_mode.add_argument("--qualify-lifecycle", action="store_true")
    n10_mode.add_argument("--finalize-readiness", action="store_true")
    n10.add_argument(
        "--output-root",
        dest="n10_output_root",
        default="outputs/fault-experiments-v2-2-n10",
    )
    n10.set_defaults(action="fault_experiment_v2_2_n10")

    server = subparsers.add_parser("serve", help="serve the local dashboard")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    server.set_defaults(action="serve")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _repo_root(args.repo_root)
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = repo_root / output_root
    store = JobStore(output_root)

    if args.action == "doctor":
        codex_path = shutil.which("codex")
        etiq_available = importlib.util.find_spec("etiq_copilot") is not None
        etiq_version = None
        if etiq_available:
            etiq_version = importlib.metadata.version("etiq-copilot")
        etiq_compatible = etiq_version == EXPECTED_ETIQ_VERSION
        print(
            json.dumps(
                {
                    "python": sys.version.split()[0],
                    "codex": codex_path,
                    "etiq_copilot": etiq_available,
                    "etiq_version": etiq_version,
                    "etiq_compatible": etiq_compatible,
                    "etiq_source": f"PyPI (etiq-copilot=={EXPECTED_ETIQ_VERSION})",
                },
                indent=2,
            )
        )
        return 0 if codex_path and etiq_compatible else 1
    if args.action == "show":
        state = store.read_json(store.job_dir(args.job_id) / "state.json")
        if state is None:
            print(f"unknown job: {args.job_id}", file=sys.stderr)
            return 2
        print(json.dumps(state, indent=2))
        return 0
    if args.action == "serve":
        serve(store, args.host, args.port)
        return 0
    if args.action == "compare_review":
        codex = CodexRunner(
            store,
            model=args.model,
            timeout_seconds=args.timeout,
        )
        try:
            experiment_id = run_review_experiment(
                repo_root=repo_root,
                store=store,
                codex=codex,
                job_id=args.job_id,
                baseline_run_id=args.baseline_run,
                repaired_run_id=args.repaired_run,
                repetitions=args.repetitions,
                section_ids=set(args.sections or []),
                history_job_ids=args.history_jobs or [],
                execute=args.execute,
            )
        except Exception as exc:
            print(f"review comparison failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(experiment_id)
        return 0
    if args.action == "assess_review":
        assessment_path = Path(args.assessment_json).resolve()
        try:
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
            assess_review_experiment(
                store=store,
                job_id=args.job_id,
                experiment_id=args.experiment_id,
                issue_assessment=assessment,
            )
        except Exception as exc:
            print(f"review assessment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(args.experiment_id)
        return 0
    if args.action == "compare_control":
        try:
            experiment_id = run_controlled_experiment(
                repo_root=repo_root,
                store=store,
                codex=CodexRunner(
                    store,
                    model=args.model,
                    timeout_seconds=args.timeout,
                ),
                etiq=EtiqExecutor(store, timeout_seconds=args.timeout),
                job_id=args.job_id,
                baseline_run_id=args.baseline_run,
                max_repairs=args.max_repairs,
            )
        except Exception as exc:
            print(
                f"controlled comparison failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(experiment_id)
        return 0
    if args.action == "fault_preflight_phase_a":
        preflight_output_root = Path(args.preflight_output_root)
        if not preflight_output_root.is_absolute():
            preflight_output_root = repo_root / preflight_output_root
        try:
            root = run_phase_a_preflight(
                repo_root=repo_root,
                output_root=preflight_output_root,
                model=args.model,
                timeout_seconds=args.timeout,
            )
        except Exception as exc:
            print(
                f"C07 Phase-A preflight failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(root)
        return 0
    if args.action == "fault_preflight_phase_a_v2":
        try:
            root = run_phase_a_preflight_v2(
                repo_root=repo_root,
                output_root=repo_root / "outputs/fault-experiments-v2",
                model=args.model,
                timeout_seconds=args.timeout,
            )
        except Exception as exc:
            print(
                f"N02 v2 Phase-A preflight failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(root)
        return 0
    if args.action == "fault_preflight_phase_a_v2_n03":
        try:
            root = run_phase_a_preflight_v2_n03(
                repo_root=repo_root,
                output_root=repo_root / "outputs/fault-experiments-v2",
                model=args.model,
                timeout_seconds=args.timeout,
            )
        except Exception as exc:
            print(
                f"N03 v2 Phase-A preflight failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(root)
        return 0
    if args.action == "fault_preflight_phase_a_v2_n04":
        try:
            root = run_phase_a_preflight_v2_n04(
                repo_root=repo_root,
                output_root=repo_root / "outputs/fault-experiments-v2",
                model=args.model,
                timeout_seconds=args.timeout,
            )
        except Exception as exc:
            print(
                f"N04 v2 Phase-A preflight failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(root)
        return 0
    if args.action == "fault_experiment_v2_1":
        from .n05_analysis import miniature_replay_fixture
        from .n05_program import (
            run_deterministic_qualification,
            run_isolation_dry_run,
            run_negative_qualifications,
            run_operator_qualification,
            run_review_repair_dry_run,
        )

        gate_root = Path(
            args.gate_output_root
            or repo_root / "outputs/fault-experiments-v2-1/gate-0-cli"
        ).resolve()
        try:
            if args.operation == "qualification":
                result = {
                    "positive": run_deterministic_qualification(
                        repo_root, gate_root / "positive"
                    )["result_sha256"],
                    "operators": run_operator_qualification(
                        repo_root, gate_root / "operators"
                    )["report_sha256"],
                    "negative": run_negative_qualifications(
                        repo_root, gate_root / "negative"
                    )["report_sha256"],
                }
            elif args.operation == "isolation":
                result = run_isolation_dry_run(repo_root, gate_root)
            elif args.operation == "operational":
                result = run_review_repair_dry_run(repo_root, gate_root)
            else:
                result = miniature_replay_fixture(gate_root)["replay"]
        except Exception as exc:
            print(f"N05 {args.operation} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, default=str))
        return 0
    if args.action == "fault_experiment_v2_2_n07":
        from .n07_program import run_n07_study

        n07_output_root = Path(args.n07_output_root)
        if not n07_output_root.is_absolute():
            n07_output_root = repo_root / n07_output_root
        qualification_authority = (
            Path(args.qualification_authority).resolve()
            if args.qualification_authority
            else None
        )
        tester_gate = Path(args.tester_gate).resolve() if args.tester_gate else None
        mode = (
            "check_ready"
            if args.check_ready
            else "qualify_lifecycle"
            if args.qualify_lifecycle
            else "live"
        )
        try:
            status_path = run_n07_study(
                repo_root,
                n07_output_root,
                mode=mode,
                qualification_authority=qualification_authority,
                tester_gate_path=tester_gate,
                stop_after=args.stop_after,
            )
        except Exception as exc:
            print(f"N07 execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(status_path)
        status = json.loads(status_path.read_text())
        return 0 if status.get("status") in {"ready", "completed_experiment_and_analysis"} else 1
    if args.action == "fault_experiment_v2_2_n08":
        from .n07_program import run_n08_study

        n08_output_root = Path(args.n08_output_root)
        if not n08_output_root.is_absolute():
            n08_output_root = repo_root / n08_output_root
        try:
            status_path = run_n08_study(
                repo_root,
                n08_output_root,
                mode="check_ready" if args.check_ready else "live",
            )
        except Exception as exc:
            print(f"N08 execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(status_path)
        status = json.loads(status_path.read_text())
        return 0 if status.get("status") in {"ready", "completed_experiment_and_analysis"} else 1
    if args.action == "fault_experiment_v2_2_n09":
        from .n07_program import run_n09_study

        n09_output_root = Path(args.n09_output_root)
        if not n09_output_root.is_absolute():
            n09_output_root = repo_root / n09_output_root
        try:
            status_path = run_n09_study(
                repo_root,
                n09_output_root,
                mode="check_ready" if args.check_ready else "live",
            )
        except Exception as exc:
            print(f"N09 execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(status_path)
        status = json.loads(status_path.read_text())
        return 0 if status.get("status") in {"ready", "completed_experiment_and_analysis"} else 1
    if args.action == "fault_experiment_v2_2_n10":
        from .n10_program import run_n10_study

        n10_output_root = Path(args.n10_output_root)
        if not n10_output_root.is_absolute():
            n10_output_root = repo_root / n10_output_root
        mode = (
            "check_ready"
            if args.check_ready
            else "finalize_readiness"
            if args.finalize_readiness
            else "qualify_lifecycle"
            if args.qualify_lifecycle
            else "live"
        )
        try:
            status_path = run_n10_study(
                repo_root,
                n10_output_root,
                mode=mode,
            )
        except Exception as exc:
            print(f"N10 execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(status_path)
        status = json.loads(status_path.read_text())
        return 0 if status.get("status") in {"ready", "completed_experiment_and_analysis"} else 1
    if args.action == "run":
        codex = CodexRunner(
            store,
            model=args.model,
            timeout_seconds=args.timeout,
        )
        etiq = EtiqExecutor(store)
        workflow = WorkflowRunner(repo_root=repo_root, store=store, codex=codex, etiq=etiq)
        request = AgentRequest(
            product=args.product,
            audience=args.audience,
            max_segments=args.max_segments,
            limits={
                "authoring_retries": args.max_authoring_retries,
                "repairs": args.max_repairs,
            },
        )
        try:
            job_id = workflow.run(request)
        except Exception as exc:
            print(f"workflow failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(job_id)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
