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
  echo "structural-check: Python 3.11 or newer is required." >&2
  return 1
}

find_python
export PYTHONDONTWRITEBYTECODE=1
cd "$REPO_ROOT"

"${PYTHON[@]}" - "$REPO_ROOT" <<'PY'
from __future__ import annotations

import ast
import importlib
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
source_root = root / "tools"
sources = sorted(
    path for path in source_root.rglob("*.py") if "__pycache__" not in path.parts
)
if not sources:
    raise SystemExit("structural-check: no production Python modules found.")

failures: list[str] = []
module_names: list[str] = []
checked_contracts = 0

for path in sources:
    relative = path.relative_to(root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    module_name = ".".join(parts)
    if module_name and module_name not in module_names:
        module_names.append(module_name)

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative.as_posix())
    except (OSError, UnicodeError, SyntaxError) as exc:
        failures.append(f"{relative.as_posix()}: cannot inspect annotations: {exc}")
        continue

    public_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            public_nodes.append(node)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_"):
                    public_nodes.append(child)

    for node in public_nodes:
        checked_contracts += 1
        if node.returns is None:
            failures.append(f"{relative.as_posix()}:{node.lineno}: {node.name} has no return annotation")
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            if argument.arg in {"self", "cls"}:
                continue
            if argument.annotation is None:
                failures.append(
                    f"{relative.as_posix()}:{node.lineno}: {node.name}.{argument.arg} has no annotation"
                )

for module_name in sorted(module_names):
    try:
        importlib.import_module(module_name)
    except Exception as exc:  # import contract must report any runtime import failure
        failures.append(f"{module_name}: import failed: {type(exc).__name__}: {exc}")

if failures:
    print("structural-check: failed", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    raise SystemExit(1)

print(
    f"structural-check: passed ({len(module_names)} import contracts; "
    f"{checked_contracts} public callable annotation contracts)"
)
print("structural-check: scope=stdlib structural checks; no full semantic type inference")
PY
