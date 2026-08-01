"""Append-only, cross-platform execution ledger."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable

from .config import (
    CONFIG_FILE,
    RunConfig,
    load_config,
    normalize_relative_path,
    path_matches_any,
)
from .models import ConfigError, Event, FAILURE_KINDS, LedgerError, TransitionError


LEDGER_FILE = "run-guard-events.jsonl"
LOCK_FILE = ".run-guard.lock"
_AGENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_FAILURE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


class _FileLock(AbstractContextManager["_FileLock"]):
    """Small advisory lock with Windows and POSIX implementations."""

    def __init__(self, path: Path, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = timeout
        self.handle: Any = None

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"\0")
            self.handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise LedgerError(f"timed out acquiring ledger lock: {self.path}")
                time.sleep(0.02)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def initialize_run(plan_dir: Path | str, config_path: Path | str) -> RunConfig:
    """Validate and install a normalized configuration in an existing plan."""

    directory = Path(plan_dir).expanduser().resolve()
    if not directory.is_dir():
        raise LedgerError(f"plan directory does not exist: {plan_dir}")
    config = load_config(config_path)
    destination = directory / CONFIG_FILE
    normalized = json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n"
    with _FileLock(directory / LOCK_FILE):
        if destination.exists():
            try:
                existing = load_config(destination)
            except Exception as exc:
                raise LedgerError(f"installed configuration is invalid: {exc}") from exc
            if existing != config:
                raise LedgerError("plan directory is already initialized with another configuration")
        else:
            destination.write_text(normalized, encoding="utf-8")
        ledger = directory / LEDGER_FILE
        ledger.touch(exist_ok=True)
        _read_events_unlocked(directory, config)
    return config


def read_events(plan_dir: Path | str) -> tuple[Event, ...]:
    directory = Path(plan_dir).expanduser().resolve()
    config = load_config(directory)
    with _FileLock(directory / LOCK_FILE):
        return _read_events_unlocked(directory, config)


def _read_events_unlocked(directory: Path, config: RunConfig) -> tuple[Event, ...]:
    ledger = directory / LEDGER_FILE
    if not ledger.exists():
        raise LedgerError(f"ledger not found: {ledger}")
    events: list[Event] = []
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise LedgerError(f"cannot read ledger: {type(exc).__name__}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise LedgerError(f"blank ledger line at {line_number}")
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError("event must be a JSON object")
            event = Event.from_dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise LedgerError(f"invalid ledger line {line_number}: {exc}") from exc
        events.append(event)
    _validate_existing_events(config, events)
    return tuple(events)


def _validate_existing_events(config: RunConfig, events: list[Event]) -> None:
    replayed: list[Event] = []
    for event in events:
        if tuple(sorted(set(event.files))) != event.files:
            raise LedgerError(f"event {event.event_id} files are not unique and sorted")
        try:
            normalized_files = tuple(normalize_relative_path(path) for path in event.files)
            expected = _build_event(
                config,
                replayed,
                agent=event.agent,
                workstream=event.workstream,
                kind=event.kind,
                failure_id=event.failure_id,
                retry_of=event.retry_of,
                source_id=event.source_id,
                metric_value=event.metric_value,
                summary=event.summary,
                files=normalized_files,
                timestamp=event.timestamp,
            )
        except (ConfigError, LedgerError, TransitionError, ValueError) as exc:
            raise LedgerError(
                f"event {event.event_id} violates the ledger state machine: {exc}"
            ) from exc
        if expected != event:
            raise LedgerError(
                f"event {event.event_id} differs from deterministic state-machine replay"
            )
        replayed.append(event)


def append_event(
    plan_dir: Path | str,
    *,
    agent: str,
    workstream: str,
    kind: str,
    failure_id: str | None = None,
    retry_of: str | None = None,
    source_id: str | None = None,
    metric_value: int | None = None,
    summary: str = "",
    files: Iterable[str] = (),
    timestamp: str | None = None,
) -> Event:
    """Validate and atomically append one event."""

    directory = Path(plan_dir).expanduser().resolve()
    if not _AGENT_PATTERN.fullmatch(agent):
        raise TransitionError("agent must be a portable 1-64 character identifier")
    normalized_summary = " ".join(summary.split())[:500]
    normalized_files = tuple(sorted({normalize_relative_path(path) for path in files}))
    with _FileLock(directory / LOCK_FILE):
        config = load_config(directory)
        events = list(_read_events_unlocked(directory, config))
        event = _build_event(
            config,
            events,
            agent=agent,
            workstream=workstream,
            kind=kind,
            failure_id=failure_id,
            retry_of=retry_of,
            source_id=source_id,
            metric_value=metric_value,
            summary=normalized_summary,
            files=normalized_files,
            timestamp=timestamp or _utc_now(),
        )
        ledger = directory / LEDGER_FILE
        serialized = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with ledger.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event


def _build_event(
    config: RunConfig,
    events: list[Event],
    *,
    agent: str,
    workstream: str,
    kind: str,
    failure_id: str | None,
    retry_of: str | None,
    source_id: str | None,
    metric_value: int | None,
    summary: str,
    files: tuple[str, ...],
    timestamp: str,
) -> Event:
    if not _AGENT_PATTERN.fullmatch(agent):
        raise TransitionError("agent must be a portable 1-64 character identifier")
    if summary != " ".join(summary.split())[:500]:
        raise TransitionError(
            "summary must use normalized whitespace and at most 500 characters"
        )
    if kind == "command_snapshot":
        if config.command_budget is None:
            raise TransitionError("command_snapshot requires configured command_budget")
        if source_id not in config.command_budget.required_sources:
            raise TransitionError("command_snapshot source_id is not declared")
        if (
            isinstance(metric_value, bool)
            or not isinstance(metric_value, int)
            or metric_value < 0
        ):
            raise TransitionError(
                "command_snapshot requires a non-negative metric_value"
            )
    elif source_id is not None or metric_value is not None:
        raise TransitionError(
            "only command_snapshot accepts source_id and metric_value"
        )
    workstream_config = config.workstream_map.get(workstream)
    if workstream_config is None:
        raise TransitionError(f"unknown workstream: {workstream}")
    _parse_timestamp(timestamp)
    stream_events = [item for item in events if item.workstream == workstream]
    effective_owner = workstream_config.owner
    current_attempt = 1
    for item in stream_events:
        if item.kind == "retry":
            effective_owner = item.agent
            current_attempt = item.attempt
    if not stream_events and kind != "workstream_started":
        raise TransitionError("the first workstream event must be workstream_started")
    if stream_events and kind == "workstream_started":
        raise TransitionError("workstream_started may be recorded only once")
    if kind == "retry":
        if not retry_of or failure_id is not None:
            raise TransitionError("retry requires retry_of and forbids failure_id")
        failures = {item.failure_id: item for item in events if item.failure_id}
        failure = failures.get(retry_of)
        if failure is None:
            raise TransitionError(f"retry_of does not reference a prior failure: {retry_of}")
        if failure.workstream != workstream:
            raise TransitionError("retry_of must remain in the same workstream")
        if any(item.retry_of == retry_of for item in events):
            raise TransitionError(f"failure was already retried: {retry_of}")
        attempt = failure.attempt + 1
        status = "started"
    else:
        if agent != effective_owner:
            raise TransitionError(
                f"agent {agent} is not the effective owner of {workstream} ({effective_owner})"
            )
        attempt = current_attempt
        if kind in FAILURE_KINDS:
            if not failure_id or not _FAILURE_PATTERN.fullmatch(failure_id):
                raise TransitionError("failure events require a portable failure_id")
            if retry_of is not None:
                raise TransitionError("failure events cannot set retry_of")
            if any(item.failure_id == failure_id for item in events):
                raise TransitionError(f"duplicate failure_id: {failure_id}")
            status = "failed"
        else:
            if failure_id is not None or retry_of is not None:
                raise TransitionError("non-failure events cannot set lineage fields")
            status = "ok"

    if stream_events:
        latest_material = next(
            (
                item
                for item in reversed(stream_events)
                if item.kind not in {"heartbeat", "note"}
            ),
            None,
        )
        if latest_material and latest_material.kind in FAILURE_KINDS and kind not in {
            "retry",
            "heartbeat",
            "note",
        }:
            raise TransitionError("a failed attempt must be followed by a retry before more work")

    if kind == "artifact":
        if not files:
            raise TransitionError("artifact events require at least one file")
        for path in files:
            if not path_matches_any(path, config.allowed_paths):
                raise TransitionError(f"artifact is outside allowed_paths: {path}")
            if path_matches_any(path, config.forbidden_paths):
                raise TransitionError(f"artifact is forbidden: {path}")
            if not path_matches_any(path, workstream_config.owned_paths):
                raise TransitionError(f"artifact is outside workstream ownership: {path}")
    elif files and kind not in {"handoff", "note"}:
        raise TransitionError(f"{kind} does not accept artifact files")

    if kind == "handoff" and not any(
        item.kind == "artifact" and item.attempt == attempt for item in stream_events
    ):
        raise TransitionError("handoff requires an artifact in the current attempt")

    sequence = len(events) + 1
    return Event(
        sequence=sequence,
        event_id=f"evt-{sequence:06d}",
        timestamp=timestamp,
        task_id=config.task_id,
        agent=agent,
        workstream=workstream,
        attempt=attempt,
        kind=kind,
        status=status,
        failure_id=failure_id,
        retry_of=retry_of,
        source_id=source_id,
        metric_value=metric_value,
        summary=summary,
        files=files,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LedgerError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerError("event timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)
