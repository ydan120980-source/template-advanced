"""Contract tests for process helpers with timeouts and tree termination.

The tests simulate a hanging command and verify: the whole process tree is
terminated (no residual processes), the timeout is reported with the stage
label and command, and the helper never blocks indefinitely. Short, harmless
processes are used so a bug cannot leak a long-running process into the test
host.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest

from tools.aiwf_run_guard.procutil import (
    ProcessResult,
    ProcessTimedOutError,
    run_process_tree,
    run_process_tree_or_raise,
)


def _sleep_command(seconds: int) -> list[str]:
    """A command that sleeps ``seconds``, or longer, then exits cleanly."""
    if os.name == "nt":
        return [
            sys.executable,
            "-c",
            f"import time; time.sleep({seconds}); print('done')",
        ]
    return ["sh", "-c", f"sleep {seconds}; echo done"]


class ProcessTreeTimeoutTests(unittest.TestCase):
    maxDiff = None

    def test_timeout_reports_label_command_and_duration(self) -> None:
        with self.assertRaises(ProcessTimedOutError) as captured:
            run_process_tree_or_raise(
                _sleep_command(60),
                timeout=2,
                label="staging",
            )
        error = captured.exception
        self.assertEqual(error.label, "staging")
        self.assertEqual(error.timeout, 2)
        message = str(error)
        self.assertIn("staging: timed out after 2s", message)
        self.assertIn("python", message)

    def test_timeout_returns_result_with_timed_out_flag(self) -> None:
        result = run_process_tree(
            _sleep_command(60),
            timeout=2,
            label="probe",
        )
        self.assertIsInstance(result, ProcessResult)
        self.assertTrue(result.timed_out)
        self.assertIsNotNone(result.returncode)

    def test_completed_command_returns_zero_and_not_timed_out(self) -> None:
        result = run_process_tree(
            [sys.executable, "-c", "print('ok')"],
            timeout=30,
            label="quick",
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_tree_kill_leaves_no_residual_processes(self) -> None:
        """A killed tree must not leave descendants running afterwards."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            marker = os.path.join(temporary_directory, "child.done")
            if os.name == "nt":
                # The grandchild would write the marker after 2s; the parent
                # sleeps for 60s, so a surviving tree would produce the marker.
                child = os.path.join(temporary_directory, "child_sleeper.py")
                with open(child, "w", encoding="utf-8") as handle:
                    handle.write(
                        "import sys, time\n"
                        "time.sleep(2)\n"
                        "with open(sys.argv[1], 'w', encoding='utf-8') as f:\n"
                        "    f.write('done')\n"
                    )
                script = (
                    "import subprocess, sys, time\n"
                    f"subprocess.Popen([sys.executable, {child!r}, {marker!r}])\n"
                    "time.sleep(60)\n"
                )
                command = [sys.executable, "-c", script]
            else:
                command = [
                    "sh",
                    "-c",
                    f"(sleep 2; touch {marker}) & sleep 60",
                ]
            result = run_process_tree(
                command,
                timeout=1,
                label="tree-kill",
            )
            self.assertTrue(result.timed_out)
            # Give any surviving descendant a chance to write the marker.
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if os.path.exists(marker):
                    break
                time.sleep(0.1)
            self.assertFalse(
                os.path.exists(marker),
                "a descendant survived the process-tree kill",
            )


if __name__ == "__main__":
    unittest.main()
