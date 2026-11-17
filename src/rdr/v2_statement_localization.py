"""Post-hoc statement-level source-localization analysis for frozen V2 reviews."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

from rdr.freeze import write_manifest
from rdr.v2_unified_experiment import INTERACTIVE_ARMS, ONE_SHOT_ARMS


def _location(location: str) -> tuple[str, int] | None:
    path, separator, line = location.rpartition(":")
    if not separator or not path:
        return None
    try:
        return path, int(line)
    except ValueError:
        return None


def statement_span(source: str, line: int) -> tuple[int, int] | None:
    """Return the smallest Python statement containing ``line``."""
    candidates = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.stmt):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        if node.lineno <= line <= end:
            candidates.append((end - node.lineno, node.lineno, end))
    if not candidates:
        return None
    _, start, end = min(candidates)
    return start, end


def canonical_statement(location: str, sources: dict[str, str]) -> str:
    """Map ``file:line`` to ``file:start-end`` for its smallest statement."""
    parsed = _location(location)
    if parsed is None:
        return location
    path, line = parsed
    source = sources.get(path)
    if source is None:
        return location
    span = statement_span(source, line)
    if span is None:
        return location
    return f"{path}:{span[0]}-{span[1]}"


def canonical_statements(locations: list[str], sources: dict[str, str]) -> set[str]:
    return {canonical_statement(location, sources) for location in locations}


def _answer(path: Path) -> dict:
    return json.loads(path.read_text())["answer"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyse(build: Path, base_reviews: Path, corrected_o_reviews: Path, output: Path) -> dict:
    """Re-score frozen faulty instances at exact-line and statement-span granularity."""
    rows = []
    truth_root = build / "private/truth"
    trace_root = build / "private/traces"
    for truth_path in sorted(truth_root.glob("*.json")):
        truth = json.loads(truth_path.read_text())
        if not truth["fault_occurred"]:
            continue
        instance = truth_path.stem
        sources = json.loads((trace_root / truth_path.name).read_text())["source"]
        gold_lines = set(truth["root_cause_source_locations"])
        gold_statements = canonical_statements(truth["root_cause_source_locations"], sources)
        gold_events = set(truth["root_cause_event_indices"])
        answer_paths = {
            arm: base_reviews / "one_shot" / instance / f"{arm}.json"
            for arm in ONE_SHOT_ARMS
        }
        answer_paths["N"] = base_reviews / "N" / instance / "N.json"
        answer_paths["O"] = corrected_o_reviews / "O" / instance / "O.json"
        for arm in (*ONE_SHOT_ARMS, *INTERACTIVE_ARMS):
            answer = _answer(answer_paths[arm])
            claimed_lines = set(answer["root_cause_source_locations"])
            claimed_statements = canonical_statements(answer["root_cause_source_locations"], sources)
            claimed_events = set(answer["root_cause_event_indices"])
            rows.append({
                "arm": arm,
                "instance_id": truth["instance_id"],
                "fault_id": truth["fault_id"],
                "fault_class": truth["fault_class"],
                "author": truth["author"],
                "repair": truth["repair"],
                "exact_source_lines_recovered": claimed_lines == gold_lines,
                "source_statements_recovered": claimed_statements == gold_statements,
                "exact_events_recovered": claimed_events == gold_events,
                "complete_exact_root_cause_recovered": (
                    claimed_lines == gold_lines and claimed_events == gold_events
                ),
                "complete_statement_root_cause_recovered": (
                    claimed_statements == gold_statements and claimed_events == gold_events
                ),
                "claimed_source_locations": sorted(claimed_lines),
                "gold_source_locations": sorted(gold_lines),
                "claimed_source_statements": sorted(claimed_statements),
                "gold_source_statements": sorted(gold_statements),
                "claimed_event_indices": sorted(claimed_events),
                "gold_event_indices": sorted(gold_events),
            })

    grouped = {}
    for arm in (*ONE_SHOT_ARMS, *INTERACTIVE_ARMS):
        arm_rows = [row for row in rows if row["arm"] == arm]
        cells = {}
        for repair in ("unrepaired", "repaired"):
            cell = [row for row in arm_rows if row["repair"] == repair]
            cells[repair] = {
                "statement_root_cause": sum(row["complete_statement_root_cause_recovered"] for row in cell),
                "denominator": len(cell),
            }
        grouped[arm] = {
            "exact_source_lines": sum(row["exact_source_lines_recovered"] for row in arm_rows),
            "source_statements": sum(row["source_statements_recovered"] for row in arm_rows),
            "exact_events": sum(row["exact_events_recovered"] for row in arm_rows),
            "exact_root_cause": sum(row["complete_exact_root_cause_recovered"] for row in arm_rows),
            "statement_root_cause": sum(
                row["complete_statement_root_cause_recovered"] for row in arm_rows
            ),
            "denominator": len(arm_rows),
            "by_repair": cells,
        }

    summary = {
        "schema_version": 1,
        "definition": (
            "Source locations match when they resolve to the same smallest enclosing Python AST "
            "statement. Runtime-event indices remain exact."
        ),
        "faulty_instances": len({row["instance_id"] for row in rows}),
        "arms": len(grouped),
        "evaluations": len(rows),
        "grouped_by_arm": grouped,
        "inputs": {
            "build": str(build),
            "build_manifest_sha256": _sha(build / "MANIFEST.sha256.json"),
            "base_reviews": str(base_reviews),
            "base_one_shot_manifest_sha256": _sha(
                base_reviews / "one_shot/MANIFEST.sha256.json"
            ),
            "base_n_manifest_sha256": _sha(base_reviews / "N/MANIFEST.sha256.json"),
            "corrected_o_reviews": str(corrected_o_reviews),
            "corrected_o_reviews_manifest_sha256": _sha(
                corrected_o_reviews / "MANIFEST.sha256.json"
            ),
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "scores.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_manifest(output)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--base-reviews", type=Path, required=True)
    parser.add_argument("--corrected-o-reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = analyse(args.build, args.base_reviews, args.corrected_o_reviews, args.output)
    print(json.dumps({
        "faulty_instances": summary["faulty_instances"],
        "arms": summary["arms"],
        "evaluations": summary["evaluations"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
