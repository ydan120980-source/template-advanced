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

  echo "setup: Python 3.11 or newer is required." >&2
  return 1
}

find_python
export PYTHONDONTWRITEBYTECODE=1

"${PYTHON[@]}" - "$REPO_ROOT" <<'PY'
from __future__ import annotations

from pathlib import Path
import concurrent.futures
import sqlite3
import sys
import tomllib
import unittest

root = Path(sys.argv[1]).resolve()
if not (root / "tools").is_dir() or not (root / "tests").is_dir():
    raise SystemExit("setup: repository root is missing tools/ or tests/.")

print(f"setup: repository={root}")
print(f"setup: python={sys.executable}")
print(f"setup: version={sys.version.split()[0]}")
print("setup: dependencies=Python standard library only (nothing to install)")
print("setup: required stdlib modules=available")
print("setup: ready; run scripts/verify.sh for full local validation")
PY
