"""Deterministic JSON and Markdown renderers for Template Doctor."""

from __future__ import annotations

import json

from .models import Report


def render_json(report: Report) -> str:
    """Render the public JSON contract with stable ordering and UTF-8 text."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    )


def _markdown_text(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def render_markdown(report: Report) -> str:
    """Render a complete, deterministic human-readable report."""

    summary = report.summary
    lines = [
        "# Template Doctor Report",
        "",
        f"- Root: `{_markdown_text(report.root)}`",
        f"- Status: **{report.status}**",
        (
            "- Summary: "
            f"{summary['total']} total, {summary['passed']} passed, "
            f"{summary['failed']} failed, {summary['skipped']} skipped, "
            f"{summary['errors']} errors"
        ),
        "",
        "## Findings",
        "",
    ]
    for result in report.results:
        lines.extend(
            [
                f"### `{_markdown_text(result.rule_id)}`",
                "",
                f"- Rule ID: `{_markdown_text(result.rule_id)}`",
                f"- Severity: **{result.severity}**",
                f"- Status: **{result.status}**",
                f"- Evidence: {_markdown_text(result.evidence)}",
                f"- Recommendation: {_markdown_text(result.recommendation)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()
