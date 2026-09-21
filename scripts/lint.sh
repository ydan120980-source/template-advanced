#!/usr/bin/env bash
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
  echo "lint: Python 3.11 or newer is required." >&2
  return 1
}

find_python
export PYTHONDONTWRITEBYTECODE=1
cd "$REPO_ROOT"

"${PYTHON[@]}" - "$REPO_ROOT" <<'PY'
from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
excluded = {
    ".aiwf",
    ".cache",
    ".git",
    ".mypy_cache",
    ".nox",
    ".planning",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "archive",
    "build",
    "coverage",
    "dist",
    "env",
    "examples",
    "htmlcov",
    "node_modules",
    "out",
    "references",
    "venv",
}


def git_sources() -> list[Path] | None:
    git_marker = root / ".git"
    try:
        probe = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "rev-parse",
                "--is-inside-work-tree",
                "--show-prefix",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except FileNotFoundError:
        if git_marker.exists():
            raise SystemExit("lint: Git metadata exists but Git is unavailable.")
        return None
    except (OSError, subprocess.TimeoutExpired) as exc:
        if git_marker.exists():
            raise SystemExit(
                f"lint: Git repository probing failed: {type(exc).__name__}"
            ) from exc
        return None

    if probe.returncode != 0:
        if git_marker.exists():
            diagnostic = os.fsdecode(probe.stderr).strip()
            message = "lint: Git metadata exists but repository probing failed"
            if diagnostic:
                message += f": {diagnostic}"
            raise SystemExit(message)
        return None

    lines = probe.stdout.splitlines()
    if not lines or lines[0].strip() != b"true":
        return None
    prefix = lines[1] if len(lines) > 1 else b""
    if prefix.strip():
        # A source copy can live inside another repository. In that case the
        # parent repository's ignore/index state is not authoritative here.
        return None

    selected = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.py",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if selected.returncode != 0:
        diagnostic = os.fsdecode(selected.stderr).strip()
        message = f"lint: Git path selection failed with exit {selected.returncode}"
        if diagnostic:
            message += f": {diagnostic}"
        raise SystemExit(message)

    paths: list[Path] = []
    for raw in selected.stdout.split(b"\x00"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        candidate = root / relative
        if candidate.is_file():
            paths.append(candidate)
    return sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())


def fallback_sources() -> list[Path]:
    paths: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories[:] = sorted(
            name
            for name in subdirectories
            if name.casefold() not in excluded
        )
        base = Path(directory)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                paths.append(base / filename)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


sources = git_sources()
if sources is None:
    sources = fallback_sources()
if not sources:
    raise SystemExit("lint: no Python sources found.")

failures: list[str] = []
for path in sources:
    relative = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        failures.append(f"{relative}: UTF-8 read failed: {exc}")
        continue

    if "\x00" in text:
        failures.append(f"{relative}: contains a NUL byte")

    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.endswith((" ", "\t")):
            failures.append(f"{relative}:{line_number}: trailing whitespace")
        indentation = line[: len(line) - len(line.lstrip(" \t"))]
        if "\t" in indentation:
            failures.append(f"{relative}:{line_number}: tab used for indentation")

    try:
        ast.parse(text, filename=relative)
    except SyntaxError as exc:
        failures.append(f"{relative}:{exc.lineno or 0}: syntax error: {exc.msg}")

if failures:
    print("lint: failed", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    raise SystemExit(1)

print(f"lint: passed ({len(sources)} Python files; UTF-8, AST, whitespace, indentation)")
PY
