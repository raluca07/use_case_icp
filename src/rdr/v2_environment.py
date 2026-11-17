"""Generate environment manifests from installed distributions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from rdr.freeze import write_manifest


def inspect_environment(label: str) -> dict:
    distributions = sorted(
        ({"name": dist.metadata["Name"], "version": dist.version} for dist in importlib.metadata.distributions()),
        key=lambda item: item["name"].lower(),
    )
    return {"schema_version": 1, "environment": label, "python": platform.python_version(),
            "executable": sys.executable, "distributions": distributions}


def write_manifests(appworld_python: Path, etiq_python: Path, reviewer_python: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for label, interpreter in (("appworld", appworld_python), ("etiq", etiq_python),
                               ("reviewer", reviewer_python)):
        command = [str(interpreter), "-m", "rdr.v2_environment", "inspect", "--label", label]
        source_root = Path(__file__).resolve().parents[1]
        environment = {**os.environ, "PYTHONPATH": str(source_root)}
        completed = subprocess.run(command, check=True, capture_output=True, text=True, env=environment)
        data = json.loads(completed.stdout)
        path = output / f"{label}.environment.json"
        path.write_text(json.dumps(data, indent=2, sort_keys=True))
        result[label] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "packages": len(data["distributions"])}
    (output / "environment_manifests.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    write_manifest(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--label", required=True)
    write = sub.add_parser("write")
    write.add_argument("--appworld-python", type=Path, required=True)
    write.add_argument("--etiq-python", type=Path, required=True)
    write.add_argument("--reviewer-python", type=Path, required=True)
    write.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(inspect_environment(args.label), sort_keys=True))
    else:
        print(json.dumps(write_manifests(args.appworld_python, args.etiq_python, args.reviewer_python, args.out), indent=2,
                         sort_keys=True))


if __name__ == "__main__":
    main()
