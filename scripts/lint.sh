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
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
excluded = {".git", ".planning", "__pycache__", "archive", "examples", "references"}
sources = sorted(
    path
    for path in root.rglob("*.py")
    if not any(part in excluded for part in path.relative_to(root).parts)
)
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
