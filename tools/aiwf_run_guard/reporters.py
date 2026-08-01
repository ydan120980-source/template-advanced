"""Deterministic JSON and Markdown rendering."""

from __future__ import annotations

import json
from typing import Any

from .models import AuditReport


def render_json(value: AuditReport | dict[str, Any]) -> str:
    payload = value.to_dict() if isinstance(value, AuditReport) else value
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


def render_report_markdown(report: AuditReport) -> str:
    summary = report.summary
    lines = [
        f"# AIWF Run Guard {report.report_type.replace('_', ' ').title()}",
        "",
        f"- Status: **{report.status}**",
        (
            "- Summary: "
            f"{summary['total']} total, {summary['passed']} passed, "
            f"{summary['failed']} failed, {summary['skipped']} skipped"
        ),
        "",
        "## Findings",
        "",
    ]
    for finding in report.findings:
        lines.extend(
            [
                f"### `{_text(finding.finding_id)}`",
                "",
                f"- Status: **{finding.status}**",
                f"- Severity: **{finding.severity}**",
                f"- Evidence: {_text(finding.evidence)}",
                f"- Recommendation: {_text(finding.recommendation)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# AIWF Run Guard Summary",
        "",
        f"- Task ID: `{_text(str(summary['task_id']))}`",
        f"- Events: {summary['event_count']}",
        f"- Retries: {summary['retry_count']}/{summary['retry_limit']}",
        f"- Retry remaining: {summary['retry_remaining']}",
        "",
        "## Workstreams",
        "",
    ]
    for item in summary["workstreams"]:
        lines.append(
            "- "
            f"`{_text(item['id'])}`: owner={_text(item['effective_owner'])}, "
            f"attempt={item['attempt']}, events={item['event_count']}, "
            f"last={_text(str(item['last_event']))}"
        )
    return "\n".join(lines)


def _text(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())
