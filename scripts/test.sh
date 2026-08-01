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
  echo "test: Python 3.11 or newer is required." >&2
  return 1
}

find_python
export PYTHONDONTWRITEBYTECODE=1
cd "$REPO_ROOT"

"${PYTHON[@]}" - "$REPO_ROOT" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys
import unittest

root = Path(sys.argv[1]).resolve()
tests_root = root / "tests"
suite_directories = sorted(
    {
        path.parent
        for path in tests_root.rglob("test*.py")
        if "__pycache__" not in path.parts
    }
)
if not suite_directories:
    raise SystemExit("test: no unittest modules found.")

combined = unittest.TestSuite()
for directory in suite_directories:
    loader = unittest.TestLoader()
    combined.addTests(loader.discover(str(directory), pattern="test*.py"))

count = combined.countTestCases()
if count == 0:
    raise SystemExit("test: unittest discovery produced zero tests.")

print(f"test: discovered {count} tests in {len(suite_directories)} suite directories")
result = unittest.TextTestRunner(verbosity=2, failfast=True).run(combined)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
