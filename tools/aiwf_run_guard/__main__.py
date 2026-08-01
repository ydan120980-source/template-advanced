"""Command-line interface for AIWF Run Guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .budget import parse_source_specs, snapshot_command_budget
from .gate import evaluate_gate, summarize_run
from .ledger import append_event, initialize_run
from .models import RunGuardError
from .preflight import run_preflight
from .reporters import (
    render_json,
    render_report_markdown,
    render_summary_markdown,
)


class GuardArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RunGuardError(message)


def _parser() -> argparse.ArgumentParser:
    parser = GuardArgumentParser(
        prog="python -B -m tools.aiwf_run_guard",
        description="Record and gate auditable concurrent AIWF sprint evidence.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Install a validated run configuration.")
    init.add_argument("--plan-dir", required=True)
    init.add_argument("--config", required=True)

    record = commands.add_parser("record", help="Append one validated execution event.")
    record.add_argument("--plan-dir", required=True)
    record.add_argument("--agent", required=True)
    record.add_argument("--workstream", required=True)
    record.add_argument(
        "--kind",
        required=True,
        choices=(
            "workstream_started",
            "heartbeat",
            "artifact",
            "command_failed",
            "integration_failed",
            "retry",
            "handoff",
            "validation_passed",
            "review_passed",
            "note",
        ),
    )
    record.add_argument("--failure-id")
    record.add_argument("--retry-of")
    record.add_argument("--summary", default="")
    record.add_argument("--file", action="append", default=[])

    summary = commands.add_parser("summary", help="Render deterministic run metrics.")
    summary.add_argument("--plan-dir", required=True)
    summary.add_argument("--format", choices=("json", "markdown"), default="json")

    budget = commands.add_parser(
        "budget", help="Snapshot task-level shell requests across Codex sessions."
    )
    budget.add_argument("--plan-dir", required=True)
    budget.add_argument("--agent", required=True)
    budget.add_argument("--workstream", required=True)
    budget.add_argument("--source", action="append", required=True)
    budget.add_argument("--start", required=True)
    budget.add_argument("--end", required=True)
    budget.add_argument("--format", choices=("json", "markdown"), default="json")

    gate = commands.add_parser("gate", help="Evaluate integration readiness.")
    gate.add_argument("--root", required=True)
    gate.add_argument("--plan-dir", required=True)
    gate.add_argument("--format", choices=("json", "markdown"), default="json")

    preflight = commands.add_parser("preflight", help="Run read-only capability checks.")
    preflight.add_argument("--root", required=True)
    preflight.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "init":
            config = initialize_run(args.plan_dir, args.config)
            print(json.dumps({"status": "initialized", "task_id": config.task_id}))
            return 0
        if args.command == "record":
            event = append_event(
                args.plan_dir,
                agent=args.agent,
                workstream=args.workstream,
                kind=args.kind,
                failure_id=args.failure_id,
                retry_of=args.retry_of,
                summary=args.summary,
                files=args.file,
            )
            print(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.command == "summary":
            summary = summarize_run(args.plan_dir)
            print(render_json(summary) if args.format == "json" else render_summary_markdown(summary))
            return 0
        if args.command == "budget":
            report = snapshot_command_budget(
                args.plan_dir,
                agent=args.agent,
                workstream=args.workstream,
                sessions=parse_source_specs(args.source),
                start=args.start,
                end=args.end,
            )
            print(
                render_json(report)
                if args.format == "json"
                else render_report_markdown(report)
            )
            return report.exit_code
        if args.command == "gate":
            report = evaluate_gate(_root(args.root), args.plan_dir)
            print(render_json(report) if args.format == "json" else render_report_markdown(report))
            return report.exit_code
        if args.command == "preflight":
            report = run_preflight(_root(args.root))
            print(render_json(report) if args.format == "json" else render_report_markdown(report))
            return report.exit_code
        raise RunGuardError("unsupported command")
    except (RunGuardError, ValueError) as exc:
        print(f"aiwf-run-guard: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"aiwf-run-guard: operational error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


def _root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise RunGuardError(f"root is not a directory: {raw}")
    return root


if __name__ == "__main__":
    raise SystemExit(main())
