"""Fast contract tests for the bounded release integration runner."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

from tools.aiwf_run_guard.procutil import run_process_tree


REPO_ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_SCRIPT = REPO_ROOT / "scripts" / "integration-test-release.sh"


class IntegrationRunnerContractTests(unittest.TestCase):
    def test_script_uses_shared_bounded_runner_and_named_stages(self) -> None:
        source = INTEGRATION_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("from tools.aiwf_run_guard.procutil import", source)
        self.assertIn("run_process_tree", source)
        self.assertNotIn("subprocess.run(", source)
        self.assertIn("MAX_OUTPUT_CHARS = 4000", source)
        self.assertIn('"PYTHONDONTWRITEBYTECODE": "1"', source)
        self.assertIn('"AIWF_RELEASE_VALIDATION"', source)
        for label in (
            '"build-a"',
            '"build-b"',
            '"basic-archive-validation"',
            '"full-archive-validation"',
            '"corrupt-codegraph-rejection"',
            '"clean-head-rebuild"',
        ):
            self.assertIn(label, source)
        for detail in (
            "command:",
            "timeout:",
            "exit code:",
            "stdout tail:",
            "stderr tail:",
        ):
            self.assertIn(detail, source)

    def test_shared_runner_success_stage(self) -> None:
        result = run_process_tree(
            [sys.executable, "-c", "print('stage-ok')"],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=5,
            label="test-success-stage",
        )

        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.stdout.strip(), "stage-ok")

    def test_shared_runner_nonzero_stage_preserves_output(self) -> None:
        result = run_process_tree(
            [
                sys.executable,
                "-c",
                "import sys; print('stage-out'); print('stage-err', file=sys.stderr); sys.exit(2)",
            ],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=5,
            label="test-nonzero-stage",
        )

        self.assertEqual(result.returncode, 2)
        self.assertFalse(result.timed_out)
        self.assertIn("stage-out", result.stdout)
        self.assertIn("stage-err", result.stderr)

    def test_shared_runner_timeout_is_bounded(self) -> None:
        result = run_process_tree(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=1,
            label="test-timeout-stage",
        )

        self.assertTrue(result.timed_out)
        self.assertIsNotNone(result.returncode)

    def test_corrupt_codegraph_rule_is_explicit(self) -> None:
        source = INTEGRATION_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("rejected.returncode != 1", source)
        self.assertIn('"codegraph.initialized"', source)
        self.assertIn("corrupt tree was not rejected", source)


if __name__ == "__main__":
    unittest.main()
