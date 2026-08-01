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
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(sys.argv[1]).resolve()  # work dir
REPO = Path.cwd().resolve()
STEM = "template-advanced-1.0.0"


def run_python(*arguments: str, cwd: Path | None = None, check: bool = True):
    completed = subprocess.run(
        [sys.executable, "-B", *arguments],
        cwd=cwd or REPO,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if check and completed.returncode != 0:
        raise SystemExit(
            f"integration-test-release: command failed ({completed.stderr.strip()[-400:]})"
        )
    return completed


def sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


first_dir = ROOT / "build-a"
second_dir = ROOT / "build-b"
first_dir.mkdir()
second_dir.mkdir()

run_python("scripts/build-release.py", "--out-dir", str(first_dir))
run_python("scripts/build-release.py", "--out-dir", str(second_dir))

first_manifest = json.loads(
    (first_dir / f"{STEM}.manifest.json").read_text(encoding="utf-8")
)
if first_manifest["source"]["type"] != "git-commit":
    raise SystemExit(f"integration-test-release: unexpected source {first_manifest['source']}")

for name in (f"{STEM}.zip", f"{STEM}.manifest.json", f"{STEM}.digest.txt"):
    if (first_dir / name).read_bytes() != (second_dir / name).read_bytes():
        raise SystemExit(f"integration-test-release: {name} differs between builds")
print("integration-test-release: double build byte-identical")

# Full validation of a clean extraction (all stages, no recursion).
validate = run_python(
    "scripts/verify-release-archive.py",
    "--archive",
    str(first_dir / f"{STEM}.zip"),
    "--manifest",
    str(first_dir / f"{STEM}.manifest.json"),
    "--validate",
)
if "passed" not in validate.stdout:
    raise SystemExit(f"integration-test-release: clean --validate failed: {validate.stderr.strip()[-400:]}")
print("integration-test-release: clean extraction --validate passed")

# Corrupt extracted tree must be rejected by the Doctor policy.
extract = ROOT / "corrupt-extract"
extract.mkdir()
with zipfile.ZipFile(first_dir / f"{STEM}.zip", mode="r") as archive:
    archive.extractall(extract)
corrupt = extract / ".codegraph" / "index.db"
corrupt.parent.mkdir(exist_ok=True)
corrupt.write_bytes(b"not a sqlite database")
rejected = run_python(
    "scripts/verify-release-archive.py",
    "--archive",
    str(first_dir / f"{STEM}.zip"),
    "--manifest",
    str(first_dir / f"{STEM}.manifest.json"),
    "--validate",
    "--extract-dir",
    str(extract),
    check=False,
)
if rejected.returncode != 1 or "codegraph.initialized" not in rejected.stderr:
    raise SystemExit(
        f"integration-test-release: corrupt tree was not rejected: {rejected.stderr.strip()[-400:]}"
    )
print("integration-test-release: corrupt extracted tree rejected")

print("integration-test-release: passed")
PY

echo "integration-test-release: passed"
