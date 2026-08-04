"""Unified ``python -m tools.governance_v2`` command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .bootstrap import BootstrapError, plan as bootstrap_plan, snapshot as bootstrap_snapshot
from .issue import (
    IssueCommandError,
    append_issue_event,
    create_issue,
    init_contract,
    load_contract,
    load_event_chain,
    sync_contract,
    verify_contract,
    verify_event_chain,
)
from .migration import MigrationError, build_matrices, verify_matrices
from .remote import RemoteGateError, gate_github
from .workflow import WorkflowCheckError, static_check


EXIT_CODES = {
    "PASS": 0,
    "STATIC_TARGETED_PASS": 0,
    "FAIL": 1,
    "BLOCKED": 2,
    "CACHED": 3,
    "NOT_RUN": 4,
}


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
    sync.add_argument("--cache", type=_path)
    sync.add_argument("--output", type=_path)
    init = issue_commands.add_parser("init")
    init.add_argument("--contract", required=True, type=_path)
    init.add_argument("--output", type=_path)
    create = issue_commands.add_parser("create")
    create.add_argument("--contract", required=True, type=_path)
    create.add_argument("--repo", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--confirm-write", action="store_true")
    create.add_argument("--timeout", type=float, default=15.0)
    append = issue_commands.add_parser("append")
    append.add_argument("--event-file", required=True, type=_path)
    append.add_argument("--repo")
    append.add_argument("--issue-number", type=int)
    append.add_argument("--issue-url")
    append.add_argument("--confirm-write", action="store_true")
    verify = issue_commands.add_parser("verify")
    verify.add_argument("--contract", type=_path)
    verify.add_argument("--body-file", type=_path)
    verify.add_argument("--events-file", type=_path)

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

    gate = domains.add_parser("gate")
    gate_commands = gate.add_subparsers(dest="command", required=True)
    static = gate_commands.add_parser("static")
    static.add_argument("--root", default=".")
    github = gate_commands.add_parser("github")
    github.add_argument("--repo", required=True)
    github.add_argument("--sha", required=True)
    github.add_argument("--workflow", required=True)
    github.add_argument("--check-name", required=True)
    github.add_argument("--app-id", type=int)
    github.add_argument("--fixture", type=_path)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.domain == "issue" and args.command == "init":
        return init_contract(contract_path=args.contract, output=args.output)
    if args.domain == "issue" and args.command == "create":
        return create_issue(
            contract_path=args.contract,
            repo=args.repo,
            title=args.title,
            confirmed=args.confirm_write,
            timeout=args.timeout,
        )
    if args.domain == "issue" and args.command == "append":
        return append_issue_event(
            event_path=args.event_file,
            repo=args.repo,
            issue_number=args.issue_number,
            issue_url=args.issue_url,
            confirmed=args.confirm_write,
        )
    if args.domain == "issue" and args.command == "verify":
        provided = [args.contract, args.body_file, args.events_file]
        if sum(value is not None for value in provided) != 1:
            raise UsageError("provide exactly one of --contract, --body-file, or --events-file")
        if args.events_file is not None:
            return verify_event_chain(load_event_chain(args.events_file))
        contract = load_contract(args.contract or args.body_file)
        return verify_contract(contract.to_dict())
    if args.domain == "issue" and args.command == "sync":
        return sync_contract(
            body_file=args.body_file,
            cache=args.cache,
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
    if args.domain == "gate" and args.command == "static":
        return static_check(Path(args.root).resolve())
    if args.domain == "gate" and args.command == "github":
        return gate_github(
            repo=args.repo,
            sha=args.sha,
            workflow=args.workflow,
            check_name=args.check_name,
            app_id=args.app_id,
            fixture=args.fixture,
        )
    raise UsageError("unsupported command")


def _error_report(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, (IssueCommandError, MigrationError, BootstrapError, WorkflowCheckError, RemoteGateError)):
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
