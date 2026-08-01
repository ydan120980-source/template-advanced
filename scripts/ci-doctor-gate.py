#!/usr/bin/env python3
"""CI gate for Template Doctor.

Runs Template Doctor against a checkout and passes only when every failed
rule is an explicitly deferred external state (a missing Git baseline).
Unknown findings, project pollution, and release-rule failures block CI.
CodeGraph is an optional capability: without an index the Doctor reports a
non-blocking skip by default, so no CodeGraph allowlist entry is needed here;
pass ``--strict`` to the Doctor when an index is a hard requirement. A corrupt
or invalid CodeGraph database is always a blocking failure.
Invocation or operational errors also block CI.

Usage (from the repository root):

    python -B scripts/ci-doctor-gate.py --root .

Exit 0 means the gate passed, 1 means an unexpected Doctor finding or error,
and 2 means the Doctor invocation or the gate itself failed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.template_doctor.policy import (  # noqa: E402
    RELEASE_EXTRACTION_ALLOWED_FAILURES,
)

# Findings that are explicitly deferred external state and never block CI.
ALLOWED_FINDINGS = RELEASE_EXTRACTION_ALLOWED_FAILURES


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -B scripts/ci-doctor-gate.py",
        description="Block CI only on unexpected Template Doctor findings.",
    )
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to run Template Doctor",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        completed = subprocess.run(
            [
                args.python,
                "-B",
                "-m",
                "tools.template_doctor",
                "--root",
                str(root),
                "--format",
                "json",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"ci-doctor-gate: invocation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if completed.returncode == 2:
        print(
            f"ci-doctor-gate: Doctor invocation error (exit 2): "
            f"{completed.stderr.strip()[-500:]}",
            file=sys.stderr,
        )
        return 2
    try:
        report = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeError) as exc:
        print(f"ci-doctor-gate: unparseable Doctor report: {type(exc).__name__}", file=sys.stderr)
        return 2
    results = report.get("results", [])
    failures = {
        item.get("rule_id")
        for item in results
        if item.get("status") == "fail"
    }
    errors = report.get("summary", {}).get("errors", 0)
    unexpected = sorted(failures - ALLOWED_FINDINGS)
    if unexpected or errors:
        print(
            "ci-doctor-gate: FAIL "
            f"unexpected={unexpected} errors={errors}",
            file=sys.stderr,
        )
        return 1
    print(
        "ci-doctor-gate: passed "
        f"(rules={report.get('summary', {}).get('total', len(results))}, "
        f"failures={sorted(failures)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
