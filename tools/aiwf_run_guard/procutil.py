"""Process helpers with timeouts and process-tree termination.

Validation stages run shell scripts that may spawn descendants. On timeout,
``subprocess.run`` terminates only the direct child, so descendant processes
can keep running (and, on Windows, keep a lock on the extracted directory or
leave orphaned processes behind). These helpers always start the child in its
own process group/session and, on timeout, terminate the entire group:

- POSIX: ``start_new_session=True`` then ``os.killpg`` (SIGTERM, escalated to
  SIGKILL when the group survives);
- Windows: ``CREATE_NEW_PROCESS_GROUP`` then ``taskkill /T /F /PID``, which
  kills the whole tree rooted at the child PID. The kill targets only the PID
  this helper created; it never scans or kills by process name.

Only the Python standard library is used.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence


DEFAULT_TIMEOUT_SECONDS = 60
SHORT_REAP_TIMEOUT_SECONDS = 5

_WINDOWS_CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

_POSIX = os.name == "posix"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Outcome of a timed process-tree run."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


class ProcessTimedOutError(TimeoutError):
    """Raised when a command exceeded its deadline.

    ``label`` and ``command`` are the caller-provided stage name and command
    line so errors can name the exact stage that hung.
    """

    def __init__(self, label: str, command: list[str], timeout: int) -> None:
        super().__init__(
            f"{label}: timed out after {timeout}s; command: {' '.join(command)[-300:]}"
        )
        self.label = label
        self.command = command
        self.timeout = timeout


def _terminate_tree(process: subprocess.Popen) -> None:
    """Terminate the entire process tree owned by ``process``."""

    if _POSIX:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return

    # Windows: kill the tree rooted at the created PID only; never match by
    # process name, so unrelated Python/Codex processes are untouched.
    if process.poll() is None:
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
    # Reap the direct child so no zombie/terminated handle lingers. The tree
    # itself is already dead; the child may take a moment to exit.
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _close_process_pipes(process: subprocess.Popen) -> None:
    """Close every parent-side pipe, including after a failed read."""

    for pipe in (process.stdin, process.stdout, process.stderr):
        if pipe is None:
            continue
        try:
            pipe.close()
        except (OSError, ValueError):
            pass


def _reap_process(process: subprocess.Popen) -> None:
    """Kill and reap a process that survived the normal cleanup path."""

    if process.poll() is None:
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass
    try:
        process.wait(timeout=SHORT_REAP_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _output_as_text(value: object, encoding: str, errors: str) -> str:
    """Normalize text and byte output returned by real or mocked Popen."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode(encoding, errors)
    return str(value)


def run_process_tree(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    label: str = "command",
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> ProcessResult:
    """Run ``command`` in its own process group, bounded by ``timeout``.

    On timeout the whole process tree is terminated and the result has
    ``timed_out=True`` with whatever output was captured so far.
    """

    popen_kwargs: dict[str, object] = {
        "cwd": str(cwd) if cwd is not None else None,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": text,
        "encoding": encoding,
        "errors": errors,
    }
    if _POSIX:
        popen_kwargs["start_new_session"] = True
    else:
        creation_flags = _WINDOWS_CREATION_FLAGS
        if creation_flags:
            creation_flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        popen_kwargs["creationflags"] = creation_flags

    process: subprocess.Popen[str] | None = None
    stdout_value: object = ""
    stderr_value: object = ""
    timed_out = False
    try:
        process = subprocess.Popen(list(command), **popen_kwargs)
        try:
            stdout_value, stderr_value = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as timeout_error:
            timed_out = True
            _terminate_tree(process)
            try:
                # A second bounded communicate collects output already buffered
                # by the first call and closes the streams without a manual,
                # potentially blocking read of either pipe.
                stdout_value, stderr_value = process.communicate(
                    timeout=SHORT_REAP_TIMEOUT_SECONDS
                )
            except (OSError, ValueError, subprocess.TimeoutExpired) as reap_error:
                stdout_value = (
                    getattr(reap_error, "output", None)
                    or timeout_error.output
                    or ""
                )
                stderr_value = (
                    getattr(reap_error, "stderr", None)
                    or timeout_error.stderr
                    or ""
                )
    finally:
        if process is not None:
            _close_process_pipes(process)
            _reap_process(process)

    return ProcessResult(
        returncode=process.returncode if process is not None else None,
        stdout=_output_as_text(stdout_value, encoding, errors),
        stderr=_output_as_text(stderr_value, encoding, errors),
        timed_out=timed_out,
    )


def run_process_tree_or_raise(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    label: str = "command",
    encoding: str = "utf-8",
    errors: str = "replace",
) -> ProcessResult:
    """Like :func:`run_process_tree` but raises on timeout."""

    result = run_process_tree(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        label=label,
        encoding=encoding,
        errors=errors,
    )
    if result.timed_out:
        raise ProcessTimedOutError(label, list(command), timeout)
    return result
