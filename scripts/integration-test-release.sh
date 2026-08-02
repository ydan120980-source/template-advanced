#!/usr/bin/env bash
# Full release integration test for template-advanced.
#
# This script runs the heavy end-to-end release validation that the normal
# `python -m unittest discover -s tests` suite must NOT run: building twice,
# comparing artifacts byte-for-byte, validating a clean extraction, and
# rejecting a corrupted extracted tree. Release CI and pre-publication
# validation execute this script so release strength is never reduced.
#
# Usage (from the repository root):
#
#     bash scripts/integration-test-release.sh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

find_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
      "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      PYTHON=("$candidate")
      return 0
    fi
  done
  if command -v py >/dev/null 2>&1 && \
    py -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PYTHON=(py -3)
    return 0
  fi
  echo "integration-test-release: Python 3.11 or newer is required." >&2
  return 1
}

find_python
export PYTHONDONTWRITEBYTECODE=1
cd "$REPO_ROOT"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/template-advanced-release-it-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "integration-test-release: work=$WORK"

"${PYTHON[@]}" -B - "$WORK" <<'PY'
from __future__ import annotations

import json
import os
import shlex
import sys
import zipfile
from pathlib import Path

from tools.aiwf_run_guard.procutil import ProcessResult, run_process_tree
from tools.template_doctor.release_inventory import RELEASE_VERSION


ROOT = Path(sys.argv[1]).resolve()  # work dir
REPO = Path.cwd().resolve()
STEM = f"template-advanced-{RELEASE_VERSION}"
MAX_OUTPUT_CHARS = 4000
BUILD_TIMEOUT_SECONDS = 120
BASIC_VALIDATION_TIMEOUT_SECONDS = 120
FULL_VALIDATION_TIMEOUT_SECONDS = 300
CORRUPT_VALIDATION_TIMEOUT_SECONDS = 300
CLEAN_HEAD_STATUS_TIMEOUT_SECONDS = 30
CLEAN_HEAD_REBUILD_TIMEOUT_SECONDS = 180


def _tail(value: str) -> str:
    text = value.strip()
    return text[-MAX_OUTPUT_CHARS:] if text else "<empty>"


class IntegrationFailure(RuntimeError):
    """A bounded integration stage failed with actionable evidence."""

    def __init__(
        self,
        label: str,
        command: list[str],
        timeout: int,
        returncode: int | None,
        stdout: str,
        stderr: str,
        detail: str,
    ) -> None:
        exit_code = "<none>" if returncode is None else str(returncode)
        super().__init__(
            "\n".join(
                [
                    f"integration-test-release: {label}: {detail}",
                    f"command: {shlex.join(command)}",
                    f"timeout: {timeout}s",
                    f"exit code: {exit_code}",
                    f"stdout tail: {_tail(stdout)}",
                    f"stderr tail: {_tail(stderr)}",
                ]
            )
        )
        self.label = label
        self.command = command
        self.timeout = timeout
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _raise_for_result(
    label: str,
    command: list[str],
    timeout: int,
    result: ProcessResult,
    detail: str,
) -> None:
    raise IntegrationFailure(
        label,
        command,
        timeout,
        result.returncode,
        result.stdout,
        result.stderr,
        detail,
    )


def run_stage(
    label: str,
    command: list[str],
    *,
    timeout: int,
    check: bool = True,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> ProcessResult:
    """Run one integration stage with a shared, bounded process tree."""

    stage_env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if env:
        stage_env.update(env)
    try:
        result = run_process_tree(
            command,
            cwd=cwd or REPO,
            env=stage_env,
            timeout=timeout,
            label=label,
        )
    except OSError as exc:
        raise IntegrationFailure(
            label,
            command,
            timeout,
            None,
            "",
            "",
            f"could not start ({type(exc).__name__}: {exc})",
        ) from exc
    if result.timed_out:
        _raise_for_result(label, command, timeout, result, "timed out")
    if check and result.returncode != 0:
        _raise_for_result(label, command, timeout, result, "command failed")
    print(
        f"integration-test-release: {label}: exit={result.returncode} "
        f"timeout={timeout}s"
    )
    return result


def run_python(
    label: str,
    *arguments: str,
    timeout: int,
    check: bool = True,
    release_validation: bool = False,
    cwd: Path | None = None,
) -> ProcessResult:
    env = {"PYTHONDONTWRITEBYTECODE": "1"}
    if release_validation:
        # Prevent the extracted validation from recursively launching the
        # release integration chain. The top-level integration script itself
        # never skips because of this marker.
        env["AIWF_RELEASE_VALIDATION"] = "1"
    return run_stage(
        label,
        [sys.executable, "-B", *arguments],
        timeout=timeout,
        check=check,
        env=env,
        cwd=cwd,
    )


def require_output(
    label: str,
    command: list[str],
    timeout: int,
    result: ProcessResult,
    text: str,
) -> None:
    if text not in result.stdout:
        _raise_for_result(
            label,
            command,
            timeout,
            result,
            f"expected output marker {text!r} was absent",
        )


def compare_artifacts(
    label: str,
    first: Path,
    second: Path,
    names: tuple[str, ...],
) -> None:
    for name in names:
        if (first / name).read_bytes() != (second / name).read_bytes():
            raise IntegrationFailure(
                label,
                ["compare", str(first / name), str(second / name)],
                0,
                None,
                "",
                "",
                f"{name} differs between builds",
            )


first_dir = ROOT / "build-a"
second_dir = ROOT / "build-b"
clean_head_dir = ROOT / "clean-head-rebuild"
first_dir.mkdir()
second_dir.mkdir()
clean_head_dir.mkdir()

run_python(
    "build-a",
    "scripts/build-release.py",
    "--out-dir",
    str(first_dir),
    timeout=BUILD_TIMEOUT_SECONDS,
)
run_python(
    "build-b",
    "scripts/build-release.py",
    "--out-dir",
    str(second_dir),
    timeout=BUILD_TIMEOUT_SECONDS,
)

clean_status_command = ["git", "status", "--porcelain", "--untracked-files=all"]
clean_status = run_stage(
    "clean-head-rebuild",
    clean_status_command,
    timeout=CLEAN_HEAD_STATUS_TIMEOUT_SECONDS,
)
if clean_status.stdout.strip():
    _raise_for_result(
        "clean-head-rebuild",
        clean_status_command,
        CLEAN_HEAD_STATUS_TIMEOUT_SECONDS,
        clean_status,
        "working tree is not clean",
    )
run_python(
    "clean-head-rebuild",
    "scripts/build-release.py",
    "--out-dir",
    str(clean_head_dir),
    timeout=CLEAN_HEAD_REBUILD_TIMEOUT_SECONDS,
)

first_manifest = json.loads(
    (first_dir / f"{STEM}.manifest.json").read_text(encoding="utf-8")
)
if first_manifest["source"]["type"] != "git-commit":
    raise IntegrationFailure(
        "build-a",
        [
            sys.executable,
            "-B",
            "scripts/build-release.py",
            "--out-dir",
            str(first_dir),
        ],
        BUILD_TIMEOUT_SECONDS,
        0,
        "",
        "",
        f"unexpected source {first_manifest['source']}",
    )

artifact_names = (f"{STEM}.zip", f"{STEM}.manifest.json", f"{STEM}.digest.txt")
compare_artifacts("build-b", first_dir, second_dir, artifact_names)
compare_artifacts("clean-head-rebuild", first_dir, clean_head_dir, artifact_names)
print("integration-test-release: double build byte-identical")
print("integration-test-release: clean HEAD rebuild byte-identical")

basic_command = [
    sys.executable,
    "-B",
    "scripts/verify-release-archive.py",
    "--archive",
    str(first_dir / f"{STEM}.zip"),
    "--manifest",
    str(first_dir / f"{STEM}.manifest.json"),
]
basic = run_stage(
    "basic-archive-validation",
    basic_command,
    timeout=BASIC_VALIDATION_TIMEOUT_SECONDS,
)
require_output(
    "basic-archive-validation",
    basic_command,
    BASIC_VALIDATION_TIMEOUT_SECONDS,
    basic,
    "passed",
)

# Full validation of a clean extraction (all stages, no recursion).
full_command = [
    "scripts/verify-release-archive.py",
    "--archive",
    str(first_dir / f"{STEM}.zip"),
    "--manifest",
    str(first_dir / f"{STEM}.manifest.json"),
    "--validate",
]
validate = run_python(
    "full-archive-validation",
    *full_command,
    timeout=FULL_VALIDATION_TIMEOUT_SECONDS,
    release_validation=True,
)
require_output(
    "full-archive-validation",
    [sys.executable, "-B", *full_command],
    FULL_VALIDATION_TIMEOUT_SECONDS,
    validate,
    "passed",
)
print("integration-test-release: clean extraction --validate passed")

# Corrupt extracted tree must be rejected by the Doctor policy.
extract = ROOT / "corrupt-extract"
extract.mkdir()
with zipfile.ZipFile(first_dir / f"{STEM}.zip", mode="r") as archive:
    archive.extractall(extract)
corrupt = extract / ".codegraph" / "index.db"
corrupt.parent.mkdir(exist_ok=True)
corrupt.write_bytes(b"not a sqlite database")
corrupt_command = [
    "scripts/verify-release-archive.py",
    "--archive",
    str(first_dir / f"{STEM}.zip"),
    "--manifest",
    str(first_dir / f"{STEM}.manifest.json"),
    "--validate",
    "--extract-dir",
    str(extract),
]
rejected = run_python(
    "corrupt-codegraph-rejection",
    *corrupt_command,
    check=False,
    timeout=CORRUPT_VALIDATION_TIMEOUT_SECONDS,
    release_validation=True,
)
if rejected.returncode != 1 or "codegraph.initialized" not in (
    rejected.stdout + "\n" + rejected.stderr
):
    _raise_for_result(
        "corrupt-codegraph-rejection",
        [sys.executable, "-B", *corrupt_command],
        CORRUPT_VALIDATION_TIMEOUT_SECONDS,
        rejected,
        "corrupt tree was not rejected with codegraph.initialized",
    )
print("integration-test-release: corrupt extracted tree rejected")

print("integration-test-release: passed")
PY

echo "integration-test-release: passed"
