"""Contract tests for process helpers with timeouts and tree termination.

The tests simulate a hanging command and verify: the whole process tree is
terminated (no residual processes), the timeout is reported with the stage
label and command, and the helper never blocks indefinitely. Short, harmless
processes are used so a bug cannot leak a long-running process into the test
host.
"""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from unittest import mock

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


def _partial_output_timeout_command() -> list[str]:
    """Emit partial output through a native shell before a long sleep."""

    if os.name == "nt":
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return [
            comspec,
            "/d",
            "/s",
            "/c",
            "(echo before & echo err-before 1>&2 & ping -n 61 127.0.0.1 >nul)",
        ]
    return [
        "sh",
        "-c",
        "printf 'before\\n'; printf 'err-before\\n' >&2; exec sleep 60",
    ]


class ProcessTreeTimeoutTests(unittest.TestCase):
    maxDiff = None

    def test_timeout_reports_label_command_and_duration(self) -> None:
        command = _sleep_command(60)
        with self.assertRaises(ProcessTimedOutError) as captured:
            run_process_tree_or_raise(
                command,
                timeout=2,
                label="staging",
            )
        error = captured.exception
        self.assertEqual(error.label, "staging")
        self.assertEqual(error.timeout, 2)
        self.assertEqual(error.command, command)
        message = str(error)
        self.assertIn("staging: timed out after 2s", message)
        self.assertIn(command[0], message)

    def test_posix_popen_omits_windows_only_creationflags(self) -> None:
        if os.name != "posix":
            self.skipTest("POSIX-specific Popen contract")

        real_popen = subprocess.Popen
        with mock.patch("tools.aiwf_run_guard.procutil.subprocess.Popen") as popen:
            process = popen.return_value
            process.communicate.return_value = ("", "")
            process.returncode = 0
            run_process_tree([sys.executable, "-c", "pass"], timeout=5)

        kwargs = popen.call_args.kwargs
        self.assertTrue(kwargs["start_new_session"])
        self.assertNotIn("creationflags", kwargs)
        self.assertIsNot(real_popen, popen)

    def test_windows_popen_uses_process_group_flag(self) -> None:
        with mock.patch("tools.aiwf_run_guard.procutil._POSIX", False), mock.patch(
            "tools.aiwf_run_guard.procutil._WINDOWS_CREATION_FLAGS", 0x200
        ), mock.patch("tools.aiwf_run_guard.procutil.subprocess.Popen") as popen:
            process = popen.return_value
            process.communicate.return_value = ("", "")
            process.returncode = 0
            run_process_tree([sys.executable, "-c", "pass"], timeout=5)

        kwargs = popen.call_args.kwargs
        self.assertTrue(kwargs["creationflags"] & 0x200)
        self.assertNotIn("start_new_session", kwargs)

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
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("error", ResourceWarning)
            result = run_process_tree(
                [sys.executable, "-c", "print('ok')"],
                timeout=30,
                label="quick",
            )
            gc.collect()
        self.assertFalse(
            [warning for warning in caught if issubclass(warning.category, ResourceWarning)]
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_nonzero_command_preserves_stdout_and_stderr(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("error", ResourceWarning)
            result = run_process_tree(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
                ],
                timeout=30,
                label="nonzero",
            )
            gc.collect()
        self.assertFalse(
            [warning for warning in caught if issubclass(warning.category, ResourceWarning)]
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout.strip(), "out")
        self.assertEqual(result.stderr.strip(), "err")

    def test_timeout_preserves_partial_stdout_and_stderr(self) -> None:
        command = _partial_output_timeout_command()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("error", ResourceWarning)
            result = run_process_tree(command, timeout=2, label="partial-output")
            gc.collect()
        self.assertFalse(
            [warning for warning in caught if issubclass(warning.category, ResourceWarning)]
        )
        self.assertTrue(result.timed_out)
        self.assertIn("before", result.stdout)
        self.assertIn("err-before", result.stderr)

    def test_repeated_timeouts_have_no_resource_warnings(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("error", ResourceWarning)
            for attempt in range(3):
                with self.assertRaises(ProcessTimedOutError):
                    run_process_tree_or_raise(
                        _sleep_command(60),
                        timeout=1,
                        label=f"repeat-timeout-{attempt}",
                    )
            gc.collect()
        self.assertFalse(
            [warning for warning in caught if issubclass(warning.category, ResourceWarning)]
        )

    def test_all_pipes_close_after_timeout_cleanup(self) -> None:
        with mock.patch("tools.aiwf_run_guard.procutil.subprocess.Popen") as popen:
            process = popen.return_value
            process.stdin = mock.Mock()
            process.stdout = mock.Mock()
            process.stderr = mock.Mock()
            process.communicate.side_effect = [
                subprocess.TimeoutExpired(
                    [sys.executable, "-c", "pass"],
                    1,
                    output="partial-out",
                    stderr="partial-err",
                ),
                ("partial-out", "partial-err"),
            ]
            process.returncode = -15
            process.poll.return_value = -15
            with mock.patch("tools.aiwf_run_guard.procutil._terminate_tree"):
                result = run_process_tree(
                    [sys.executable, "-c", "pass"],
                    timeout=1,
                    label="mock-timeout",
                )

        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout, "partial-out")
        self.assertEqual(result.stderr, "partial-err")
        process.stdin.close.assert_called_once_with()
        process.stdout.close.assert_called_once_with()
        process.stderr.close.assert_called_once_with()

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
