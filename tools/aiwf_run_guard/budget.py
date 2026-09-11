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
# Shell-bearing tool functions recognized inside executable tool-input code.
# `shell_command` is the historical form; `exec_command` is the current host
# form. Indirect-reference patterns must cover both names.
_SHELL_CALL_PATTERN = re.compile(
    r"\btools\s*\.\s*(?:shell_command|exec_command)\s*\("
)
_SHELL_REFERENCE_PATTERN = re.compile(
    r"\btools\s*\.\s*(?:shell_command|exec_command)\b"
)
_SHELL_COMPUTED_PATTERN = re.compile(
    r"\btools\s*\[\s*(['\"])(?:shell_command|exec_command)\1\s*\]"
)
_SHELL_DESTRUCTURE_PATTERN = re.compile(
    r"\{[^{}]*\b(?:shell_command|exec_command)\b[^{}]*\}\s*=\s*tools\b"
)
# Named function_call events whose tool name itself executes shell commands
# count as direct shell requests. The allowlist is deliberately conservative
# and case-insensitive: it covers the documented host variants (Codex `shell`
# / `exec`, host `Bash`, and the legacy `shell_command` / `exec_command`
# names) instead of trying to infer shell semantics from arguments.
_SHELL_FUNCTION_NAMES = frozenset(
    {"exec", "shell", "shell_command", "exec_command", "bash"}
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
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise LedgerError(
            f"cannot read session evidence for source {source_id}: {type(exc).__name__}"
        ) from exc
    # Session JSONL is newline-delimited, but string literals may legally
    # contain U+2028/U+2029/U+0085. str.splitlines() would split inside
    # those strings and corrupt otherwise-valid lines, so split strictly
    # on the record delimiter. One trailing newline is a terminator, not
    # an extra blank record; interior blank lines remain corruption.
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    call_ids: list[str] = []
    for line_number, line in enumerate(lines, 1):
        line = line.rstrip("\r")
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
        if raw.get("type") == "response_item" and not isinstance(
            raw.get("payload"), dict
        ):
            # A wrapped event whose payload is not an object cannot be
            # classified; that is corrupted evidence, not a zero count.
            raise LedgerError(
                f"response_item payload is not an object for source {source_id} "
                f"at {line_number}"
            )
        if not _is_shell_request(raw):
            continue
        observed = _event_time(raw, source_id, line_number)
        if observed < start or observed > end:
            continue
        call_id = _request_identity(raw)
        if not isinstance(call_id, str) or not call_id.strip():
            raise LedgerError(
                f"shell evidence lacks call_id for source {source_id} at {line_number}"
            )
        call_ids.append(call_id)
    return tuple(sorted(call_ids))


def _event_time(raw: Mapping[str, object], source_id: str, line_number: int) -> datetime:
    """Return one shell event's wall-clock time.

    Timestamps are either ISO-8601 strings (Codex rollouts) or numeric Unix
    epoch milliseconds (host session events). Anything else — including
    booleans and implausible epoch values — is corrupted evidence and raises
    instead of silently counting zero.
    """

    timestamp = raw.get("timestamp")
    if isinstance(timestamp, bool):
        raise LedgerError(
            f"shell evidence timestamp is invalid for source {source_id} at {line_number}"
        )
    if isinstance(timestamp, (int, float)):
        millis = float(timestamp)
        # NaN fails this comparison, so it is rejected here as well.
        if not millis >= 1_000_000_000_000:
            raise LedgerError(
                f"shell evidence timestamp is invalid for source {source_id} at {line_number}"
            )
        try:
            return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise LedgerError(
                f"shell evidence timestamp is invalid for source {source_id} at {line_number}"
            ) from exc
    if isinstance(timestamp, str) and timestamp.strip():
        return _parse_timestamp(timestamp)
    raise LedgerError(
        f"shell evidence lacks timestamp for source {source_id} at {line_number}"
    )


def _payload_of(raw: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return the tool-call payload for wrapped or unwrapped event forms."""

    if raw.get("type") == "response_item":
        payload = raw.get("payload")
        return payload if isinstance(payload, Mapping) else None
    if raw.get("type") == "function_call":
        return raw
    return None


def _is_shell_request(raw: Mapping[str, object]) -> bool:
    """Classify one session event as a shell-bearing outer tool request.

    Supported forms:

    - ``response_item`` wrapping a ``custom_tool_call`` whose string input
      invokes ``tools.shell_command(...)`` or ``tools.exec_command(...)``
      (historical and current host forms; the tool name field is not
      required for this classification);
    - a named ``function_call`` — wrapped or top-level — whose tool name is
      in the conservative shell-function allowlist (direct shell call).

    Everything else (messages, reasoning, other tools, pure-wait calls) is
    not a shell request. Corrupted shell-relevant events raise LedgerError
    instead of silently counting zero.
    """

    payload = _payload_of(raw)
    if payload is None:
        return False
    payload_type = payload.get("type")
    if payload_type == "custom_tool_call":
        # A custom_tool_call without a plain-string input cannot be
        # classified; that is corrupted evidence, not a zero count.
        if not isinstance(payload.get("input"), str):
            raise LedgerError("custom_tool_call input is not a plain string")
        return _invokes_shell_command(payload["input"])
    if payload_type == "function_call":
        return _is_shell_function_name(payload.get("name"))
    return False


def _is_shell_function_name(name: object) -> bool:
    if not isinstance(name, str) or not name.strip():
        raise LedgerError("function_call lacks a tool name")
    return name.strip().lower() in _SHELL_FUNCTION_NAMES


def _request_identity(raw: Mapping[str, object]) -> object:
    """Return the outer request identity (``call_id``/``callId``)."""

    payload = _payload_of(raw)
    if payload is None:
        return None
    for key in ("call_id", "callId"):
        if key in payload:
            return payload[key]
    return None


def _invokes_shell_command(value: object) -> bool:
    """Recognize direct shell calls and reject unsafe indirect evidence.

    The check runs on executable code regions only: string literals,
    template literals, and comments are blanked first. Besides direct calls
    of ``tools.shell_command`` / ``tools.exec_command``, any recognizable
    indirect reference (aliasing, computed access, destructuring) is an
    explicit error because the request cannot be attributed reliably.
    """

    if not isinstance(value, str):
        return False
    cleaned = _javascript_code(value)
    direct = list(_SHELL_CALL_PATTERN.finditer(cleaned))
    direct_starts = {match.start() for match in direct}
    if any(
        match.start() not in direct_starts
        for match in _SHELL_REFERENCE_PATTERN.finditer(cleaned)
    ):
        raise LedgerError("unsupported indirect shell reference")
    if _SHELL_DESTRUCTURE_PATTERN.search(cleaned):
        raise LedgerError("unsupported destructured shell reference")
    for match in _SHELL_COMPUTED_PATTERN.finditer(value):
        if cleaned[match.start() : match.start() + len("tools")] == "tools":
            raise LedgerError("unsupported computed shell reference")
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
