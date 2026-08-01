"""Deterministic summaries and integration gates for Run Guard evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    RunConfig,
    artifact_identity_key,
    load_config,
    ownership_overlaps,
    path_matches_any,
)
from .ledger import _parse_timestamp, read_events
from .models import AuditReport, Event, Finding, build_report


def summarize_run(plan_dir: Path | str) -> dict[str, Any]:
    config = load_config(plan_dir)
    events = read_events(plan_dir)
    return _summarize_events(config, events)


def _summarize_events(
    config: RunConfig, events: tuple[Event, ...]
) -> dict[str, Any]:
    kind_counts = {
        kind: sum(event.kind == kind for event in events)
        for kind in sorted({event.kind for event in events})
    }
    workstreams = []
    for workstream in config.workstreams:
        stream_events = [
            event for event in events if event.workstream == workstream.workstream_id
        ]
        owner = workstream.owner
        for event in stream_events:
            if event.kind == "retry":
                owner = event.agent
        workstreams.append(
            {
                "id": workstream.workstream_id,
                "configured_owner": workstream.owner,
                "effective_owner": owner,
                "event_count": len(stream_events),
                "last_event": stream_events[-1].kind if stream_events else None,
                "attempt": max((event.attempt for event in stream_events), default=0),
            }
        )
    retries = sum(event.kind == "retry" for event in events)
    latest_snapshots: dict[str, Event] = {}
    for event in events:
        if event.kind == "command_snapshot" and event.source_id is not None:
            latest_snapshots[event.source_id] = event
    summary = {
        "task_id": config.task_id,
        "event_count": len(events),
        "retry_count": retries,
        "retry_limit": config.retry_limit,
        "retry_remaining": max(config.retry_limit - retries, 0),
        "kind_counts": kind_counts,
        "workstreams": workstreams,
    }
    if config.command_budget is not None:
        total = sum(
            event.metric_value or 0 for event in latest_snapshots.values()
        )
        summary["command_budget"] = {
            "metric": config.command_budget.metric,
            "total": total,
            "limit": config.command_budget.limit,
            "remaining": max(config.command_budget.limit - total, 0),
            "sources": {
                key: latest_snapshots[key].metric_value
                for key in sorted(latest_snapshots)
            },
        }
    if config.artifact_budget is not None:
        unique_files = {
            artifact_identity_key(path)
            for event in events
            if event.kind == "artifact"
            for path in event.files
        }
        summary["artifact_budget"] = {
            "metric": config.artifact_budget.metric,
            "total": len(unique_files),
            "limit": config.artifact_budget.limit,
            "remaining": max(config.artifact_budget.limit - len(unique_files), 0),
        }
    return summary


def evaluate_gate(
    root: Path | str,
    plan_dir: Path | str,
    *,
    now: datetime | None = None,
) -> AuditReport:
    project_root = Path(root).expanduser().resolve()
    if not project_root.is_dir():
        raise ValueError(f"root is not a directory: {root}")
    config = load_config(plan_dir)
    events = read_events(plan_dir)
    findings: list[Finding] = []

    conflicts = ownership_overlaps(config)
    if conflicts:
        evidence = "; ".join(
            f"{left}:{left_path} overlaps {right}:{right_path}"
            for left, left_path, right, right_path in conflicts
        )
        findings.append(
            _finding(
                "ownership.no_overlap",
                "fail",
                evidence,
                "Assign non-overlapping path prefixes before concurrent work begins.",
            )
        )
    else:
        findings.append(
            _finding(
                "ownership.no_overlap",
                "pass",
                f"{len(config.workstreams)} workstreams have non-overlapping declared paths.",
                "Preserve explicit ownership in future task packets.",
            )
        )

    retries = [event for event in events if event.kind == "retry"]
    findings.append(
        _finding(
            "retry.lineage",
            "pass",
            f"All {len(retries)} retries reference one unique earlier failure in the same workstream.",
            "Continue recording failure IDs before retry attempts.",
        )
    )
    findings.append(
        _finding(
            "retry.budget",
            "pass" if len(retries) <= config.retry_limit else "fail",
            f"Retry use is {len(retries)}/{config.retry_limit}.",
            "Stop and request a budget decision before another retry." if len(retries) > config.retry_limit else "Keep retry use within the declared limit.",
        )
    )
    retried_failures = {event.retry_of for event in retries}
    unresolved_failures = [
        event
        for event in events
        if event.kind in {"command_failed", "integration_failed"}
        and event.failure_id not in retried_failures
    ]
    findings.append(
        _finding(
            "retry.unresolved_failures",
            "fail" if unresolved_failures else "pass",
            "Unresolved failures: "
            + ", ".join(
                f"{event.failure_id} ({event.workstream}, seq {event.sequence})"
                for event in unresolved_failures
            )
            if unresolved_failures
            else "Every recorded failure has one later retry event.",
            "Record a retry that references each failure before integration approval."
            if unresolved_failures
            else "No action required.",
        )
    )

    started = {event.workstream for event in events if event.kind == "workstream_started"}
    missing_started = sorted(set(config.workstream_map) - started)
    findings.append(
        _finding(
            "workstreams.started",
            "fail" if missing_started else "pass",
            "Missing starts: " + ", ".join(missing_started)
            if missing_started
            else f"All {len(config.workstreams)} workstreams were started.",
            "Record workstream_started before other events." if missing_started else "No action required.",
        )
    )

    required_handoffs = {
        item.workstream_id for item in config.workstreams if item.require_handoff
    }
    missing_handoffs: list[str] = []
    missing_current_artifacts: list[str] = []
    stale_handoffs: list[str] = []
    for workstream_id in sorted(required_handoffs):
        stream = [event for event in events if event.workstream == workstream_id]
        current_attempt = max((event.attempt for event in stream), default=0)
        current = [event for event in stream if event.attempt == current_attempt]
        handoffs = [event for event in current if event.kind == "handoff"]
        artifacts = [event for event in current if event.kind == "artifact"]
        if not artifacts:
            missing_current_artifacts.append(
                f"{workstream_id} (attempt {current_attempt})"
            )
        if not handoffs:
            missing_handoffs.append(workstream_id)
        elif artifacts and handoffs[-1].sequence < artifacts[-1].sequence:
            stale_handoffs.append(workstream_id)
    handoff_failures = (
        missing_current_artifacts + missing_handoffs + stale_handoffs
    )
    handoff_evidence = []
    if missing_current_artifacts:
        handoff_evidence.append(
            "missing current-attempt artifact: "
            + ", ".join(missing_current_artifacts)
        )
    if missing_handoffs:
        handoff_evidence.append(
            "missing current-attempt handoff: " + ", ".join(missing_handoffs)
        )
    if stale_handoffs:
        handoff_evidence.append("stale after later artifact: " + ", ".join(stale_handoffs))
    findings.append(
        _finding(
            "workstreams.handoff",
            "fail" if handoff_failures else "pass",
            "; ".join(handoff_evidence)
            if handoff_failures
            else f"All {len(required_handoffs)} required handoffs are recorded.",
            "Record an artifact and then a handoff for the current attempt before validation."
            if handoff_failures
            else "No action required.",
        )
    )

    recorded_files = sorted(
        {path for event in events for path in event.files}
    )
    path_problems = sorted(
        path
        for path in recorded_files
        if not path_matches_any(path, config.allowed_paths)
        or path_matches_any(path, config.forbidden_paths)
    )
    findings.append(
        _finding(
            "artifacts.path_scope",
            "fail" if path_problems else "pass",
            "Out-of-scope recorded paths: " + ", ".join(path_problems)
            if path_problems
            else f"All {len(recorded_files)} recorded paths satisfy allowed/forbidden prefixes.",
            "Remove or explicitly re-scope out-of-bound artifacts." if path_problems else "No action required.",
        )
    )
    unique_artifact_count = len(
        {
            artifact_identity_key(path)
            for event in events
            if event.kind == "artifact"
            for path in event.files
        }
    )
    artifact_budget = config.artifact_budget
    if artifact_budget is not None:
        over_artifact_budget = unique_artifact_count > artifact_budget.limit
        findings.append(
            _finding(
                "artifacts.file_budget",
                "fail" if over_artifact_budget else "pass",
                f"Unique artifact-file use is {unique_artifact_count}/{artifact_budget.limit}; "
                f"remaining={max(artifact_budget.limit - unique_artifact_count, 0)}.",
                "Stop and request an explicit delivery-file budget decision."
                if over_artifact_budget
                else "Keep the recorded delivery set within the declared limit.",
            )
        )
    escaped_files: list[str] = []
    missing_files: list[str] = []
    for path in recorded_files:
        candidate = project_root / path
        try:
            candidate.resolve(strict=False).relative_to(project_root)
        except (OSError, RuntimeError, ValueError):
            escaped_files.append(path)
        if not candidate.is_file():
            missing_files.append(path)
    findings.append(
        _finding(
            "artifacts.root_containment",
            "fail" if escaped_files else "pass",
            "Recorded paths resolving outside the project root: "
            + ", ".join(escaped_files)
            if escaped_files
            else f"All {len(recorded_files)} recorded artifacts resolve inside the project root.",
            "Replace junction/symlink escapes with project-contained artifacts."
            if escaped_files
            else "No action required.",
        )
    )
    findings.append(
        _finding(
            "artifacts.exist",
            "fail" if missing_files else "pass",
            "Missing recorded files: " + ", ".join(missing_files)
            if missing_files
            else f"All {len(recorded_files)} recorded artifacts exist as files.",
            "Restore the artifacts or correct the handoff evidence." if missing_files else "No action required.",
        )
    )

    invalidating_kinds = {
        "artifact",
        "handoff",
        "command_failed",
        "integration_failed",
        "retry",
    }
    evidence_boundary = max(
        (event.sequence for event in events if event.kind in invalidating_kinds),
        default=0,
    )
    validation_events = [event for event in events if event.kind == "validation_passed"]
    current_validation_events = [
        event for event in validation_events if event.sequence > evidence_boundary
    ]
    validation_ok = bool(current_validation_events) or not config.require_validation
    findings.append(
        _finding(
            "gate.validation",
            "pass" if validation_ok else "fail",
            f"Current validation events after evidence boundary seq {evidence_boundary}: "
            f"{len(current_validation_events)}/{len(validation_events)}; "
            f"required={config.require_validation}.",
            "Rerun and record successful required validation after the latest artifact, handoff, failure, or retry."
            if not validation_ok
            else "No action required.",
        )
    )
    review_events = [event for event in events if event.kind == "review_passed"]
    latest_validation = max(
        (event.sequence for event in current_validation_events), default=evidence_boundary
    )
    current_review_events = [
        event for event in review_events if event.sequence > latest_validation
    ]
    review_ok = bool(current_review_events) or not config.require_review
    findings.append(
        _finding(
            "gate.review",
            "pass" if review_ok else "fail",
            f"Current review events after seq {latest_validation}: "
            f"{len(current_review_events)}/{len(review_events)}; required={config.require_review}.",
            "Obtain and record independent review after the current validation evidence."
            if not review_ok
            else "No action required.",
        )
    )
    current_review_boundary = max(
        (event.sequence for event in current_review_events),
        default=latest_validation,
    )
    findings.append(
        _command_budget_finding(
            config,
            events,
            freshness_boundary=current_review_boundary,
            review_pending=config.require_review and not current_review_events,
        )
    )

    findings.extend(_liveness_findings(config, events, now=now))
    summary = _summarize_events(config, events)
    metadata = {
        "task_id": config.task_id,
        "event_count": summary["event_count"],
        "retry_count": summary["retry_count"],
        "retry_limit": config.retry_limit,
        "recorded_file_count": len(recorded_files),
        "unique_artifact_file_count": unique_artifact_count,
    }
    return build_report("integration_gate", findings, metadata)


def _command_budget_finding(
    config: RunConfig,
    events: tuple[Event, ...],
    *,
    freshness_boundary: int,
    review_pending: bool,
) -> Finding:
    budget = config.command_budget
    if budget is None:
        return _finding(
            "budget.commands",
            "skip",
            "No task-level command budget is configured.",
            "Declare command budgeting for multi-agent or command-sensitive work.",
            severity="info",
        )
    if review_pending:
        return _finding(
            "budget.commands",
            "skip",
            "Independent review is pending; final command snapshots must follow review evidence.",
            "Review the provisional ledger, then snapshot every declared source before the final gate.",
            severity="info",
        )
    latest: dict[str, Event] = {}
    for event in events:
        if event.kind == "command_snapshot" and event.source_id is not None:
            latest[event.source_id] = event
    missing = sorted(set(budget.required_sources) - set(latest))
    stale = sorted(
        source_id
        for source_id in budget.required_sources
        if source_id in latest
        and latest[source_id].sequence <= freshness_boundary
    )
    counts = {
        source_id: latest[source_id].metric_value or 0
        for source_id in budget.required_sources
        if source_id in latest
    }
    total = sum(counts.values())
    over = total > budget.limit
    failures = bool(missing or stale or over)
    evidence_parts = [
        f"total={total}/{budget.limit}",
        "sources="
        + ",".join(f"{key}:{counts[key]}" for key in sorted(counts)),
    ]
    if missing:
        evidence_parts.append("missing=" + ",".join(missing))
    if stale:
        evidence_parts.append("stale=" + ",".join(stale))
    return _finding(
        "budget.commands",
        "fail" if failures else "pass",
        "; ".join(evidence_parts),
        (
            "Record fresh snapshots for every declared source after current review evidence and remain within the shared limit."
            if failures
            else "Preserve aggregate accounting across all participating sessions."
        ),
    )


def _liveness_findings(
    config: RunConfig,
    events: tuple[Event, ...],
    *,
    now: datetime | None,
) -> tuple[Finding, Finding]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    stale_first_artifact: list[str] = []
    stale_heartbeat: list[str] = []
    for workstream in config.workstreams:
        if not workstream.require_handoff or not workstream.owned_paths:
            continue
        stream = [event for event in events if event.workstream == workstream.workstream_id]
        if not stream:
            continue
        current_attempt = max(event.attempt for event in stream)
        attempt_events = [event for event in stream if event.attempt == current_attempt]
        artifacts = [event for event in attempt_events if event.kind == "artifact"]
        start = next(
            (
                event
                for event in attempt_events
                if event.kind in {"workstream_started", "retry"}
            ),
            None,
        )
        if not artifacts:
            if config.first_artifact_seconds is None or start is None:
                continue
            age = (
                current.astimezone(timezone.utc) - _parse_timestamp(start.timestamp)
            ).total_seconds()
            if age > config.first_artifact_seconds:
                stale_first_artifact.append(
                    f"{workstream.workstream_id} (attempt {current_attempt})"
                )
            continue
        handoffs = [event for event in attempt_events if event.kind == "handoff"]
        if handoffs and handoffs[-1].sequence > artifacts[-1].sequence:
            continue
        if config.heartbeat_seconds is None:
            continue
        activity = max(
            (
                event
                for event in attempt_events
                if event.kind in {"artifact", "heartbeat", "retry", "workstream_started"}
            ),
            key=lambda event: event.sequence,
        )
        age = (
            current.astimezone(timezone.utc) - _parse_timestamp(activity.timestamp)
        ).total_seconds()
        if age > config.heartbeat_seconds:
            stale_heartbeat.append(
                f"{workstream.workstream_id} (attempt {current_attempt})"
            )
    first_artifact = _finding(
        "liveness.first_artifact",
        "fail" if stale_first_artifact else (
            "skip" if config.first_artifact_seconds is None else "pass"
        ),
        "Workstreams beyond first-artifact deadline: "
        + ", ".join(sorted(stale_first_artifact))
        if stale_first_artifact
        else (
            "No first-artifact timeout is configured."
            if config.first_artifact_seconds is None
            else "No current attempt is beyond the configured first-artifact deadline."
        ),
        "Interrupt or reassign stale workstreams and record failure/retry lineage."
        if stale_first_artifact
        else "No action required.",
        severity="info" if not stale_first_artifact else None,
    )
    heartbeat = _finding(
        "liveness.heartbeat",
        "fail" if stale_heartbeat else (
            "skip" if config.heartbeat_seconds is None else "pass"
        ),
        "Active workstreams beyond heartbeat deadline: "
        + ", ".join(sorted(stale_heartbeat))
        if stale_heartbeat
        else (
            "No heartbeat timeout is configured."
            if config.heartbeat_seconds is None
            else "No active post-artifact workstream is beyond the heartbeat deadline."
        ),
        "Record a heartbeat, interrupt the stale workstream, or record failure/retry lineage."
        if stale_heartbeat
        else "No action required.",
        severity="info" if not stale_heartbeat else None,
    )
    return first_artifact, heartbeat


def _finding(
    finding_id: str,
    status: str,
    evidence: str,
    recommendation: str,
    *,
    severity: str | None = None,
) -> Finding:
    if severity is None:
        severity = "error" if status == "fail" else "info"
    return Finding(finding_id, severity, status, evidence, recommendation)
