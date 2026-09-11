"""Unified ``python -m tools.workflow_eval`` command line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .grade import GradeError, grade_trial
from .prepare import PrepareError, prepare_trial
from .report import write_report
from .tasks import get_task, task_ids


class UsageError(ValueError):
    """Invalid CLI shape."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.workflow_eval")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--task", required=True, choices=task_ids())
    prepare.add_argument("--group", required=True, choices=("control", "experiment"))
    prepare.add_argument("--source-repo", required=True, type=Path)
    prepare.add_argument("--out-dir", required=True, type=Path)
    prepare.add_argument("--label", required=True)

    grade = commands.add_parser("grade")
    grade.add_argument("--task", required=True, choices=task_ids())
    grade.add_argument("--candidate-dir", required=True, type=Path)
    grade.add_argument("--results-dir", required=True, type=Path)
    grade.add_argument("--label", required=True)
    grade.add_argument("--group", required=True, choices=("control", "experiment"))
    grade.add_argument("--run-kind", required=True, choices=("trial", "freeze"))
    grade.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="trusted coordinator-side manifest JSON (never inside the candidate tree)",
    )
    grade.add_argument(
        "--trial-dir",
        type=Path,
        default=None,
        help="path to record as the trial directory (defaults to --candidate-dir)",
    )
    grade.add_argument("--elapsed-seconds", type=float, default=None)
    grade.add_argument("--shell-requests", type=int, default=None)
    grade.add_argument("--human-interventions", default=None)
    grade.add_argument("--notes-json", default=None, help="JSON object with extra coordinator notes")
    grade.add_argument(
        "--validity-status",
        choices=("VALID", "INVALID", "UNVERIFIED"),
        default=None,
        help=(
            "coordinator trial-validity attestation; omitting it records "
            "UNVERIFIED, which never fills a valid comparison slot"
        ),
    )
    grade.add_argument(
        "--validity-basis",
        default=None,
        help="audit basis for --validity-status (required for VALID and INVALID)",
    )
    grade.add_argument(
        "--validity-audit-record",
        default=None,
        help="path to the coordinator audit artefact the attestation rests on",
    )
    grade.add_argument(
        "--session-record",
        default=None,
        help="path to the trial sub-agent session JSONL being attested",
    )

    report = commands.add_parser("report")
    report.add_argument("--results-dir", required=True, type=Path)
    report.add_argument("--output", required=True, type=Path)
    report.add_argument("--label", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        parsed = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        print(json.dumps({"status": "BLOCKED", "code": "INVALID_ARGUMENTS"}))
        return 2
    try:
        if parsed.command == "prepare":
            task = get_task(parsed.task)
            record = prepare_trial(
                source_repo=parsed.source_repo.resolve(),
                task=task,
                group=parsed.group,
                out_root=parsed.out_dir.resolve(),
                run_label=parsed.label,
            )
            print(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        if parsed.command == "grade":
            manifest_path = parsed.manifest.resolve()
            if not manifest_path.is_file():
                raise GradeError(f"trusted manifest not found: {manifest_path}")
            if manifest_path.is_relative_to(parsed.candidate_dir.resolve()):
                raise GradeError(
                    "trusted manifest must live outside the candidate tree; "
                    "the candidate never decides its own comparison baseline"
                )
            budget: dict[str, object] = {}
            if parsed.elapsed_seconds is not None:
                budget["elapsed_seconds"] = parsed.elapsed_seconds
            if parsed.shell_requests is not None:
                budget["shell_requests"] = parsed.shell_requests
            if parsed.human_interventions is not None:
                budget["human_interventions"] = parsed.human_interventions
            notes: dict[str, object] = {}
            if parsed.notes_json:
                try:
                    loaded_notes = json.loads(parsed.notes_json)
                except json.JSONDecodeError as exc:
                    raise GradeError(f"--notes-json is not valid JSON: {exc}") from exc
                if not isinstance(loaded_notes, dict):
                    raise GradeError("--notes-json must be a JSON object")
                notes = loaded_notes
            validity: dict[str, object] | None = None
            if parsed.validity_status is not None:
                validity = {"status": parsed.validity_status}
                if parsed.validity_basis is not None:
                    validity["basis"] = parsed.validity_basis
                if parsed.validity_audit_record is not None:
                    validity["audit_record"] = parsed.validity_audit_record
                if parsed.session_record is not None:
                    validity["session_record"] = parsed.session_record
            elif parsed.validity_basis or parsed.validity_audit_record:
                raise GradeError(
                    "--validity-basis/--validity-audit-record require --validity-status"
                )
            task = get_task(parsed.task)
            record = grade_trial(
                task=task,
                candidate_root=parsed.candidate_dir.resolve(),
                results_dir=parsed.results_dir.resolve(),
                label=parsed.label,
                group=parsed.group,
                trial_dir=(parsed.trial_dir or parsed.candidate_dir).resolve(),
                run_kind=parsed.run_kind,
                manifest_path=manifest_path,
                budget=budget,
                notes=notes,
                validity=validity,
            )
            print(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2))
            if record["verdict"] == "BLOCKED":
                return 2
            return 0 if record["verdict"] == "ACCEPT" and record["scope_clean"] else 1
        if parsed.command == "report":
            summary = write_report(
                parsed.results_dir.resolve(), parsed.output.resolve(), run_label=parsed.label
            )
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
            # An incomplete evidence set is a report success but must never
            # look like a finished comparison.
            return 0 if summary["status"] == "PASS" else 1
        raise UsageError(f"unsupported command: {parsed.command}")
    except (UsageError, PrepareError, GradeError) as exc:
        print(json.dumps({"status": "BLOCKED", "code": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
