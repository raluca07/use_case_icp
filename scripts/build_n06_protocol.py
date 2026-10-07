"""Reconcile protocol 2.2 exact-file bindings and its byte-identical Markdown copy."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ROOT = ROOT / "docs/workshops/neurips-2026-v2-2"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_content_hash(protocol: dict) -> str:
    value = deepcopy(protocol)
    value["integrity"].pop("content_hash", None)
    for item in value["normative_artifacts"]:
        item.pop("sha256", None)
    for name in ("contract_arm_isolation", "contract_launch_policy"):
        value["namespace_registry"]["contracts"][name].pop("sha256", None)
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def main() -> None:
    path = PROTOCOL_ROOT / "experiment-protocol.json"
    protocol = json.loads(path.read_text())
    for contract in protocol["namespace_registry"]["contracts"].values():
        contract["sha256"] = sha256(ROOT / contract["path"])
    for artifact in protocol["normative_artifacts"]:
        artifact["sha256"] = sha256(ROOT / artifact["path"])
    protocol["integrity"]["content_hash"] = canonical_content_hash(protocol)
    raw = json.dumps(protocol, ensure_ascii=False, indent=2) + "\n"
    path.write_text(raw)
    disclosure = protocol["pilot_informed_disclosure"]["statement"]
    markdown = (
        "# Protocol 2.2.0 — canonical endpoint-complete fault localisation\n\n"
        "Protocol ID: `neurips-2026-workshop-fault-localisation-v2`  \n"
        "Version: `2.2.0`  \n"
        "Status: `pre_results_frozen`\n\n"
        f"{disclosure}\n\n"
        "The JSON block below is byte-identical to `experiment-protocol.json`.\n\n"
        f"```json\n{raw}```\n"
    )
    (PROTOCOL_ROOT / "EXPERIMENT_PROTOCOL.md").write_text(markdown)


if __name__ == "__main__":
    main()
