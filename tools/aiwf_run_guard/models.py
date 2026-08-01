"""Stable data contracts for AIWF Run Guard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EVENT_KINDS = frozenset(
    {
        "workstream_started",
        "heartbeat",
        "artifact",
        "command_failed",
        "integration_failed",
        "retry",
        "handoff",
        "validation_passed",
        "review_passed",
        "command_snapshot",
        "note",
    }
)
FAILURE_KINDS = frozenset({"command_failed", "integration_failed"})
EVENT_STATUSES = frozenset({"ok", "failed", "started"})
FINDING_STATUSES = frozenset({"pass", "fail", "skip"})
SEVERITIES = frozenset({"info", "warning", "error"})


class RunGuardError(Exception):
    """Base class for user-facing Run Guard failures."""


class ConfigError(RunGuardError):
    """The run configuration is missing or invalid."""


class LedgerError(RunGuardError):
    """The append-only ledger is corrupted or internally inconsistent."""


class TransitionError(RunGuardError):
    """An event would violate the run state machine."""


@dataclass(frozen=True, slots=True)
class Event:
    """One append-only execution event."""

    sequence: int
    event_id: str
    timestamp: str
    task_id: str
    agent: str
    workstream: str
    attempt: int
    kind: str
    status: str
    failure_id: str | None
    retry_of: str | None
    source_id: str | None
    metric_value: int | None
    summary: str
    files: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        if self.event_id != f"evt-{self.sequence:06d}":
            raise ValueError("event_id does not match sequence")
        if self.attempt < 1:
            raise ValueError("attempt must be positive")
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"unsupported event kind: {self.kind}")
        if self.status not in EVENT_STATUSES:
            raise ValueError(f"unsupported event status: {self.status}")
        for field_name in ("timestamp", "task_id", "agent", "workstream"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.summary, str):
            raise TypeError("summary must be a string")
        if self.source_id is not None and not isinstance(self.source_id, str):
            raise TypeError("source_id must be a string or null")
        if self.metric_value is not None and (
            isinstance(self.metric_value, bool)
            or not isinstance(self.metric_value, int)
            or self.metric_value < 0
        ):
            raise ValueError("metric_value must be a non-negative integer or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "agent": self.agent,
            "workstream": self.workstream,
            "attempt": self.attempt,
            "kind": self.kind,
            "status": self.status,
            "failure_id": self.failure_id,
            "retry_of": self.retry_of,
            "source_id": self.source_id,
            "metric_value": self.metric_value,
            "summary": self.summary,
            "files": list(self.files),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Event":
        required = {
            "sequence",
            "event_id",
            "timestamp",
            "task_id",
            "agent",
            "workstream",
            "attempt",
            "kind",
            "status",
            "failure_id",
            "retry_of",
            "summary",
            "files",
        }
        optional = {"source_id", "metric_value"}
        if not required.issubset(raw) or not set(raw).issubset(required | optional):
            missing = sorted(required - set(raw))
            extra = sorted(set(raw) - required - optional)
            raise ValueError(f"event keys differ; missing={missing}, extra={extra}")
        files = raw["files"]
        if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
            raise ValueError("event files must be a list of strings")
        return cls(
            sequence=raw["sequence"],
            event_id=raw["event_id"],
            timestamp=raw["timestamp"],
            task_id=raw["task_id"],
            agent=raw["agent"],
            workstream=raw["workstream"],
            attempt=raw["attempt"],
            kind=raw["kind"],
            status=raw["status"],
            failure_id=raw["failure_id"],
            retry_of=raw["retry_of"],
            source_id=raw.get("source_id"),
            metric_value=raw.get("metric_value"),
            summary=raw["summary"],
            files=tuple(files),
        )


@dataclass(frozen=True, slots=True)
class Finding:
    """One deterministic gate or preflight result."""

    finding_id: str
    severity: str
    status: str
    evidence: str
    recommendation: str

    def __post_init__(self) -> None:
        if self.status not in FINDING_STATUSES:
            raise ValueError(f"unsupported finding status: {self.status}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unsupported severity: {self.severity}")

    def to_dict(self) -> dict[str, str]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "status": self.status,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True, slots=True)
class AuditReport:
    """A deterministic summary of gate or preflight findings."""

    report_type: str
    status: str
    summary: dict[str, int]
    findings: tuple[Finding, ...]
    metadata: dict[str, Any]

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "ready" else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "status": self.status,
            "summary": dict(self.summary),
            "metadata": dict(self.metadata),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def build_report(
    report_type: str,
    findings: list[Finding],
    metadata: dict[str, Any] | None = None,
) -> AuditReport:
    ordered = tuple(sorted(findings, key=lambda item: item.finding_id))
    summary = {
        "total": len(ordered),
        "passed": sum(item.status == "pass" for item in ordered),
        "failed": sum(item.status == "fail" for item in ordered),
        "skipped": sum(item.status == "skip" for item in ordered),
    }
    return AuditReport(
        report_type=report_type,
        status="not_ready" if summary["failed"] else "ready",
        summary=summary,
        findings=ordered,
        metadata=metadata or {},
    )
