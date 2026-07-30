from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from use_case_icp.codex_runner import (
    DEFAULT_CODEX_MODEL,
    STRICT_PERMISSION_PROFILE,
    CodexRunner,
    _strict_config_overrides,
)
from use_case_icp.records import AgentRequest, ContextArtifact, RootJobState, stable_hash
from use_case_icp.job_store import JobStore


FAKE_CODEX = """#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
last = pathlib.Path(args[args.index('--output-last-message') + 1])
last.write_text(json.dumps({'ok': True}), encoding='utf-8')
print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 23, 'output_tokens': 7}}))
"""


class CodexRunnerTests(unittest.TestCase):
    def test_runner_is_fresh_and_records_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "fake-codex"
            executable.write_text(FAKE_CODEX, encoding="utf-8")
            executable.chmod(0o755)
            store = JobStore(root / "jobs")
            store.initialize_job(AgentRequest("p", "a"), RootJobState("job-1"))
            runner = CodexRunner(store, codex_bin=str(executable), timeout_seconds=5)
            context = {"value": 1}
            prompt_template = "Segment the supplied audience."
            repository_instructions = "Keep generated Python simple."
            result = runner.run(
                job_id="job-1",
                job_type="segment",
                purpose="segment",
                prompt="return ok",
                output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                artifacts=[
                    ContextArtifact("embedded:test", stable_hash(context), "embedded", "test", context),
                    ContextArtifact(
                        "prompt:segment",
                        stable_hash(prompt_template),
                        "embedded",
                        "prompt_template",
                        prompt_template,
                    ),
                    ContextArtifact(
                        "repo:AGENTS.md",
                        stable_hash(repository_instructions),
                        "embedded",
                        "repository_instructions",
                        repository_instructions,
                    ),
                ],
            )
            self.assertEqual(result.payload, {"ok": True})
            self.assertEqual(result.usage.input_tokens, 23)
            invocation = store.job_dir("job-1") / "invocations" / result.invocation_id
            request = store.read_json(invocation / "agent-request.json")
            self.assertTrue(request["context_manifest"]["fresh_session"])
            invocation_record = store.read_json(invocation / "invocation.json")
            self.assertTrue(invocation_record["ephemeral"])
            self.assertEqual(invocation_record["model"], DEFAULT_CODEX_MODEL)
            self.assertEqual(invocation_record["command"][2:4], ["--model", DEFAULT_CODEX_MODEL])
            self.assertNotIn("resume", invocation_record["command"])
            self.assertNotIn("--sandbox", invocation_record["command"])
            self.assertIn("--ignore-user-config", invocation_record["command"])
            self.assertIn("--ignore-rules", invocation_record["command"])
            self.assertEqual(invocation_record["working_directory"], str(invocation))
            self.assertEqual(invocation_record["read_boundary"]["mode"], "invocation-only")
            self.assertEqual(
                (invocation / "resources" / "prompts" / "segment.md").read_text(encoding="utf-8"),
                prompt_template,
            )
            self.assertEqual(
                (invocation / "resources" / "AGENTS.md").read_text(encoding="utf-8"),
                repository_instructions,
            )
            self.assertEqual(invocation_record["read_boundary"]["skills"], [])
            self.assertFalse((invocation / ".agents").exists())
            summary = store.read_json(store.job_dir("job-1") / "usage-summary.json")
            self.assertEqual(summary["totals"]["output_tokens"], 7)

    @unittest.skipUnless(shutil.which("codex"), "Codex CLI is not installed")
    def test_strict_profile_denies_sibling_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invocation = root / "invocation"
            invocation.mkdir()
            (invocation / "visible.txt").write_text("visible", encoding="utf-8")
            outside = root / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            command = [
                "codex",
                "sandbox",
                "--cd",
                str(invocation),
                "--permission-profile",
                STRICT_PERMISSION_PROFILE,
            ]
            for override in _strict_config_overrides("codex"):
                command.extend(["--config", override])
            command.extend(
                [
                    "--",
                    "/bin/sh",
                    "-c",
                    f"test -r visible.txt && ! test -r {outside}",
                ]
            )
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
