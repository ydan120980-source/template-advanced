"""Command-line entry point for Template Doctor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .engine import run_checks


class InvocationError(Exception):
    """A user-facing invocation error that maps to exit code 2."""


class DoctorArgumentParser(argparse.ArgumentParser):
    """Argument parser that lets ``main`` own the exit-code contract."""

    def error(self, message: str) -> None:
        raise InvocationError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = DoctorArgumentParser(
        prog="python -B -m tools.template_doctor",
        description="Audit whether a template copy has completed initialization.",
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Project root directory to audit.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Report format (default: json).",
    )
    return parser


def _validated_root(raw_root: str) -> Path:
    try:
        root = Path(raw_root).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise InvocationError(f"cannot resolve root: {exc}") from exc
    if not root.exists():
        raise InvocationError(f"root does not exist: {raw_root}")
    if not root.is_dir():
        raise InvocationError(f"root is not a directory: {raw_root}")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    """Run Template Doctor and return 0 ready, 1 findings, or 2 error."""

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        root = _validated_root(args.root)
        report = run_checks(root)

        from .reporters import render_json, render_markdown

        rendered = (
            render_json(report)
            if args.format == "json"
            else render_markdown(report)
        )
        print(rendered)
        return report.exit_code
    except InvocationError as exc:
        print(f"template-doctor: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"template-doctor: operational error: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
