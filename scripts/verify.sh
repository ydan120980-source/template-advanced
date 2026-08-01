#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

echo "verify: lint"
bash "$SCRIPT_DIR/lint.sh"
echo "verify: structural-check"
bash "$SCRIPT_DIR/structural-check.sh"
echo "verify: tests"
bash "$SCRIPT_DIR/test.sh"
echo "verify: passed"
