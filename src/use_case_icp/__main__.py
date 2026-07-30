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
from .etiq_executor import EXPECTED_ETIQ_VERSION, EtiqExecutor
from .workflow import WorkflowRunner
from .records import AgentRequest
from .review_experiment import assess_review_experiment, run_review_experiment
from .job_store import JobStore
from .dashboard import serve


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
