"""Privacy-preserving cross-session shell-command budget evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Mapping

from .config import load_config
from .ledger import _parse_timestamp, append_event
from .models import AuditReport, Finding, LedgerError, build_report


_SOURCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_SHELL_CALL_PATTERN = re.compile(r"\btools\s*\.\s*shell_command\s*\(")
_SHELL_REFERENCE_PATTERN = re.compile(r"\btools\s*\.\s*shell_command\b")
_SHELL_COMPUTED_PATTERN = re.compile(
    r"\btools\s*\[\s*(['\"])shell_command\1\s*\]"
)
_SHELL_DESTRUCTURE_PATTERN = re.compile(
    r"\{[^{}]*\bshell_command\b[^{}]*\}\s*=\s*tools\b"
)


def parse_source_specs(specs: Iterable[str]) -> dict[str, Path]:
    """Parse explicit source_id=path arguments without rendering source paths."""

    parsed: dict[str, Path] = {}
    for spec in specs:
        if not isinstance(spec, str) or "=" not in spec:
            raise LedgerError("each --source must use source_id=JSONL_path")
        source_id, raw_path = spec.split("=", 1)
        if not _SOURCE_PATTERN.fullmatch(source_id):
            raise LedgerError("a --source ID is invalid")
        if source_id in parsed:
            raise LedgerError(f"duplicate --source ID: {source_id}")
        if not raw_path.strip():
            raise LedgerError(f"source {source_id} has an empty JSONL path")
        parsed[source_id] = Path(raw_path).expanduser()
    return parsed


def snapshot_command_budget(
    plan_dir: Path | str,
    *,
    agent: str,
    workstream: str,
    sessions: Mapping[str, Path | str],
    start: str,
    end: str,
) -> AuditReport:
    """Count declared sessions, append compact snapshots, and report the budget."""

    config = load_config(plan_dir)
    budget = config.command_budget
    if budget is None:
        raise LedgerError("command_budget is not configured")
    expected_sources = set(budget.required_sources)
    provided_sources = set(sessions)
    if provided_sources != expected_sources:
        missing = sorted(expected_sources - provided_sources)
        extra = sorted(provided_sources - expected_sources)
        raise LedgerError(
            f"command sources differ; missing={missing}, extra={extra}"
        )
    start_time = _window_time(start, "start")
    end_time = _window_time(end, "end")
    if end_time < start_time:
        raise LedgerError("command-budget end must not precede start")

    counts: dict[str, int] = {}
    fingerprints: dict[str, str] = {}
    seen_call_ids: set[str] = set()
    duplicates = 0
    for source_id in sorted(sessions):
        call_ids = _session_shell_call_ids(
            source_id,
            Path(sessions[source_id]),
            start=start_time,
            end=end_time,
        )
        for call_id in call_ids:
            if call_id in seen_call_ids:
                duplicates += 1
            seen_call_ids.add(call_id)
        counts[source_id] = len(call_ids)
        fingerprints[source_id] = hashlib.sha256(
            "\n".join(call_ids).encode("utf-8")
        ).hexdigest()[:16]
    if duplicates:
        raise LedgerError(
            f"duplicate tool-call IDs across command sources: {duplicates}"
        )

    window = f"{_utc_text(start_time)}..{_utc_text(end_time)}"
    for source_id in sorted(counts):
        append_event(
            plan_dir,
            agent=agent,
            workstream=workstream,
            kind="command_snapshot",
            source_id=source_id,
            metric_value=counts[source_id],
            summary=(
                f"metric=shell_command_requests window={window} "
                f"evidence={fingerprints[source_id]}"
            ),
        )

    total = sum(counts.values())
    over = total > budget.limit
    evidence = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
    finding = Finding(
        finding_id="budget.commands",
        severity="error" if over else "info",
        status="fail" if over else "pass",
        evidence=(
            f"shell_command_requests total={total}/{budget.limit}; {evidence}; "
            f"unique_call_ids={len(seen_call_ids)}"
        ),
        recommendation=(
            "Stop and request an explicit task-level command-budget decision."
            if over
            else "Keep all participating sessions within the shared limit."
        ),
    )
    return build_report(
        "command_budget",
        [finding],
        {
            "task_id": config.task_id,
            "metric": budget.metric,
            "limit": budget.limit,
            "total": total,
            "remaining": max(budget.limit - total, 0),
            "source_counts": {key: counts[key] for key in sorted(counts)},
            "unique_call_ids": len(seen_call_ids),
        },
    )


def _session_shell_call_ids(
    source_id: str,
    path: Path,
    *,
    start: datetime,
    end: datetime,
) -> tuple[str, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise LedgerError(
            f"cannot read session evidence for source {source_id}: {type(exc).__name__}"
        ) from exc
    call_ids: list[str] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise LedgerError(
                f"blank session evidence line for source {source_id} at {line_number}"
            )
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(
                f"invalid JSON session evidence for source {source_id} at {line_number}"
            ) from exc
        if not isinstance(raw, dict):
            raise LedgerError(
                f"non-object session evidence for source {source_id} at {line_number}"
            )
        payload = raw.get("payload")
        if (
            raw.get("type") != "response_item"
            or not isinstance(payload, dict)
            or payload.get("type") != "custom_tool_call"
            or not _invokes_shell_command(payload.get("input"))
        ):
            continue
        timestamp = raw.get("timestamp")
        if not isinstance(timestamp, str):
            raise LedgerError(
                f"shell evidence lacks timestamp for source {source_id} at {line_number}"
            )
        observed = _parse_timestamp(timestamp)
        if observed < start or observed > end:
            continue
        call_id = payload.get("call_id")
        if not isinstance(call_id, str) or not call_id.strip():
            raise LedgerError(
                f"shell evidence lacks call_id for source {source_id} at {line_number}"
            )
        call_ids.append(call_id)
    return tuple(sorted(call_ids))


def _invokes_shell_command(value: object) -> bool:
    """Recognize direct shell calls and reject unsafe indirect evidence."""

    if not isinstance(value, str):
        return False
    cleaned = _javascript_code(value)
    direct = list(_SHELL_CALL_PATTERN.finditer(cleaned))
    direct_starts = {match.start() for match in direct}
    if any(
        match.start() not in direct_starts
        for match in _SHELL_REFERENCE_PATTERN.finditer(cleaned)
    ):
        raise LedgerError("unsupported indirect shell_command reference")
    if _SHELL_DESTRUCTURE_PATTERN.search(cleaned):
        raise LedgerError("unsupported destructured shell_command reference")
    for match in _SHELL_COMPUTED_PATTERN.finditer(value):
        if cleaned[match.start() : match.start() + len("tools")] == "tools":
            raise LedgerError("unsupported computed shell_command reference")
    return bool(direct)


def _javascript_code(value: str) -> str:
    """Return executable JavaScript regions with strings/comments blanked."""

    code: list[str] = []
    index = 0
    frames: list[dict[str, object]] = [{"kind": "code", "depth": None}]
    while index < len(value):
        char = value[index]
        following = value[index + 1] if index + 1 < len(value) else ""
        frame = frames[-1]
        kind = frame["kind"]
        if kind == "code":
            if char in {"'", '"'}:
                code.append(" ")
                frames.append({"kind": "string", "quote": char})
                index += 1
            elif char == "`":
                code.append(" ")
                frames.append({"kind": "template"})
                index += 1
            elif char == "/" and following == "/":
                code.extend((" ", " "))
                frames.append({"kind": "line_comment"})
                index += 2
            elif char == "/" and following == "*":
                code.extend((" ", " "))
                frames.append({"kind": "block_comment"})
                index += 2
            elif frame["depth"] is not None and char == "{":
                frame["depth"] = int(frame["depth"]) + 1
                code.append(char)
                index += 1
            elif frame["depth"] is not None and char == "}":
                frame["depth"] = int(frame["depth"]) - 1
                code.append(" ")
                index += 1
                if frame["depth"] == 0:
                    frames.pop()
            else:
                code.append(char)
                index += 1
        elif kind == "string":
            if char == "\\" and following:
                code.extend((" ", " "))
                index += 2
            else:
                code.append("\n" if char == "\n" else " ")
                index += 1
                if char == frame["quote"]:
                    frames.pop()
        elif kind == "line_comment":
            code.append("\n" if char == "\n" else " ")
            index += 1
            if char == "\n":
                frames.pop()
        elif kind == "block_comment":
            if char == "*" and following == "/":
                code.extend((" ", " "))
                frames.pop()
                index += 2
            else:
                code.append("\n" if char == "\n" else " ")
                index += 1
        else:
            if char == "\\" and following:
                code.extend((" ", " "))
                index += 2
            elif char == "`":
                code.append(" ")
                frames.pop()
                index += 1
            elif char == "$" and following == "{":
                code.extend((" ", " "))
                frames.append({"kind": "code", "depth": 1})
                index += 2
            else:
                code.append("\n" if char == "\n" else " ")
                index += 1
    return "".join(code)


def _window_time(value: str, label: str) -> datetime:
    try:
        parsed = _parse_timestamp(value)
    except LedgerError as exc:
        raise LedgerError(f"command-budget {label} is invalid: {exc}") from exc
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
