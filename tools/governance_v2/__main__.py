"""Unified ``python -m tools.governance_v2`` command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .bootstrap import BootstrapError, plan as bootstrap_plan, snapshot as bootstrap_snapshot
from .issue import IssueCommandError, load_contract, sync_contract, verify_contract
from .migration import MigrationError, build_matrices, verify_matrices


EXIT_CODES = {"PASS": 0, "FAIL": 1, "BLOCKED": 2, "CACHED": 3, "NOT_RUN": 4}


class UsageError(ValueError):
    """Raised for an invalid CLI shape while preserving JSON-only output."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401 - argparse hook
        raise UsageError(message)


def _path(value: str) -> Path:
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="python -m tools.governance_v2")
    domains = parser.add_subparsers(dest="domain", required=True)

    issue = domains.add_parser("issue")
    issue_commands = issue.add_subparsers(dest="command", required=True)
    sync = issue_commands.add_parser("sync")
    sync.add_argument("--body-file", type=_path)
    sync.add_argument("--repo")
    sync.add_argument("--issue-number", type=int)
    sync.add_argument("--issue-url")
    sync.add_argument("--output", type=_path)
    verify = issue_commands.add_parser("verify")
    verify.add_argument("--contract", type=_path)
    verify.add_argument("--body-file", type=_path)

    migration = domains.add_parser("migration")
    migration_commands = migration.add_subparsers(dest="command", required=True)
    build = migration_commands.add_parser("build")
    build.add_argument("--root", default=".")
    build.add_argument("--base", default="origin/main")
    build.add_argument("--head", default="origin/codex/release-v1.1.0")
    build.add_argument("--output-dir", type=_path, default=Path(".aiwf/cache/migration"))
    migration_verify = migration_commands.add_parser("verify")
    migration_verify.add_argument("--input-dir", type=_path, default=Path(".aiwf/cache/migration"))

    bootstrap = domains.add_parser("bootstrap")
    bootstrap_commands = bootstrap.add_subparsers(dest="command", required=True)
    snapshot = bootstrap_commands.add_parser("snapshot")
    snapshot.add_argument("--root", default=".")
    snapshot.add_argument("--repository-id", default="ydan120980-source/template-advanced")
    snapshot.add_argument("--base", default="origin/main")
    snapshot.add_argument("--head", default="origin/codex/release-v1.1.0")
    snapshot.add_argument("--expected-base-sha")
    snapshot.add_argument("--expected-head-sha")
    snapshot.add_argument("--output", type=_path)
    plan = bootstrap_commands.add_parser("plan")
    plan.add_argument("--snapshot", type=_path)
    plan.add_argument("--output", type=_path)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.domain == "issue" and args.command == "verify":
        if bool(args.contract) == bool(args.body_file):
            raise UsageError("provide exactly one of --contract or --body-file")
        contract = load_contract(args.contract or args.body_file)
        return verify_contract(contract.to_dict())
    if args.domain == "issue" and args.command == "sync":
        return sync_contract(
            body_file=args.body_file,
            repo=args.repo,
            issue_number=args.issue_number,
            issue_url=args.issue_url,
            output=args.output,
        )
    if args.domain == "migration" and args.command == "build":
        return build_matrices(
            root=Path(args.root).resolve(),
            base_ref=args.base,
            head_ref=args.head,
            output_dir=args.output_dir.resolve(),
        )
    if args.domain == "migration" and args.command == "verify":
        return verify_matrices(input_dir=args.input_dir.resolve())
    if args.domain == "bootstrap" and args.command == "snapshot":
        return bootstrap_snapshot(
            root=Path(args.root).resolve(),
            repository_id=args.repository_id,
            base_ref=args.base,
            head_ref=args.head,
            expected_base_sha=args.expected_base_sha,
            expected_head_sha=args.expected_head_sha,
            output=args.output,
        )
    if args.domain == "bootstrap" and args.command == "plan":
        return bootstrap_plan(snapshot_path=args.snapshot, output=args.output)
    raise UsageError("unsupported command")


def _error_report(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, (IssueCommandError, MigrationError, BootstrapError)):
        return {"status": exc.status, "code": exc.code, "message": str(exc)}
    if isinstance(exc, UsageError):
        return {"status": "BLOCKED", "code": "INVALID_ARGUMENTS", "message": str(exc)}
    return {"status": "BLOCKED", "code": "UNEXPECTED_ERROR", "message": f"{type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        result = _run(args)
    except (UsageError, IssueCommandError, MigrationError, BootstrapError, OSError, ValueError) as exc:
        result = _error_report(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return EXIT_CODES.get(str(result.get("status")), EXIT_CODES["BLOCKED"])


if __name__ == "__main__":
    sys.exit(main())
