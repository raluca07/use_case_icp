"""Confinement tests for the generated-pipeline worker.

The authoring session is confined; the code it produces is what actually runs.
These pin the two controls that were inert by default. See issue #1.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from use_case_icp.etiq_executor import EtiqExecutor, worker_limits
from use_case_icp.job_store import JobStore


class WorkerLimitTests(unittest.TestCase):
    def test_limits_are_applied_when_the_caller_supplies_none(self) -> None:
        limits = worker_limits(None)
        self.assertGreater(limits["memory_limit_mb"], 0)
        self.assertGreater(limits["cpu_limit_seconds"], 0)

    def test_caller_supplied_limits_win(self) -> None:
        limits = worker_limits(
            {"request": {"limits": {"etiq_memory_mb": 64, "etiq_cpu_seconds": 5}}}
        )
        self.assertEqual(limits["memory_limit_mb"], 64)
        self.assertEqual(limits["cpu_limit_seconds"], 5)


class WorkerEnvironmentTests(unittest.TestCase):
    def test_worker_home_is_not_the_real_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executor = EtiqExecutor(JobStore(root / "outputs" / "jobs"))
            sandbox_home = root / "run" / "home"
            with patch.dict(os.environ, {"HOME": "/Users/someone"}):
                environment = executor._worker_environment(None, home=sandbox_home)
            # HOME reaching the generated pipeline is a path to ~/.codex/auth.json,
            # ~/.ssh and ~/.aws/credentials.
            self.assertNotEqual(environment.get("HOME"), "/Users/someone")
            self.assertEqual(environment["HOME"], str(sandbox_home))
            self.assertTrue(sandbox_home.is_dir())

    def test_source_policy_cannot_reintroduce_the_real_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executor = EtiqExecutor(JobStore(root / "outputs" / "jobs"))
            sandbox_home = root / "run" / "home"
            runtime_input = {
                "request": {"source_policy": {"environment_allowlist": ["HOME"]}}
            }
            with patch.dict(os.environ, {"HOME": "/Users/someone"}):
                environment = executor._worker_environment(
                    runtime_input, home=sandbox_home
                )
            self.assertEqual(environment["HOME"], str(sandbox_home))


if __name__ == "__main__":
    unittest.main()
