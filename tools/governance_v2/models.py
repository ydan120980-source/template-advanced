"""Validated data models for the governance v2 contract and event chain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import sha256_canonical, without_field


CONTRACT_KEYS = frozenset(
    {
        "schema_version",
        "task_id",
        "task_type",
        "repository_id",
        "base_sha",
        "goal",
        "allowed_paths",
        "forbidden_paths",
        "acceptance",
        "contract_digest",
    }
)

EVENT_KEYS = frozenset(
    {
        "sequence",
        "event_id",
        "event_type",
        "task_id",
        "subject_sha",
        "previous_event_digest",
        "payload",
        "actor",
        "created_at",
        "event_digest",
    }
)

EVENT_TYPES = frozenset(
    {
        "task_opened",
        "decision_recorded",
        "migration_commit_matrix",
        "migration_file_matrix",
        "bootstrap_contract_adopted",
        "bootstrap_snapshot",
        "bootstrap_switch_started",
        "bootstrap_switch_committed",
        "bootstrap_switch_failed",
        "bootstrap_switch_rolled_back",
        "validation_recorded",
        "candidate_frozen",
        "candidate_superseded",
        "checks_passed",
        "blocked",
        "pr_closed",
        "pr_merged",
        "tag_created",
        "release_published",
        "release_verified",
        "task_closed",
    }
)


class ContractError(ValueError):
    """Raised when a contract or event violates the stable v2 schema."""


def _require_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} must be a non-empty string")
    return value


def _require_string_list(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ContractError(f"{key} must be a non-empty list of strings")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class TaskContract:
    """A frozen governance.task/v2 contract."""

    data: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskContract":
        if not isinstance(raw, dict):
            raise ContractError("contract must be a JSON object")
        if set(raw) != CONTRACT_KEYS:
            missing = sorted(CONTRACT_KEYS - set(raw))
            extra = sorted(set(raw) - CONTRACT_KEYS)
            raise ContractError(f"contract keys differ; missing={missing}, extra={extra}")
        schema_version = _require_string(raw, "schema_version")
        if schema_version != "governance.task/v2":
            raise ContractError(f"unsupported schema_version: {schema_version}")
        for key in ("task_id", "task_type", "repository_id", "base_sha", "goal"):
            _require_string(raw, key)
        for key in ("allowed_paths", "forbidden_paths", "acceptance"):
            _require_string_list(raw, key)
        digest = _require_string(raw, "contract_digest")
        expected = sha256_canonical(without_field(raw, "contract_digest"))
        if digest != expected:
            raise ContractError(
                f"contract_digest mismatch: expected {expected}, received {digest}"
            )
        return cls(dict(raw))

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)

    @property
    def digest(self) -> str:
        return self.data["contract_digest"]


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """One append-only Issue event with a self-verifying digest."""

    sequence: int
    event_id: str
    event_type: str
    task_id: str
    subject_sha: str
    previous_event_digest: str | None
    payload: dict[str, Any]
    actor: str
    created_at: str
    event_digest: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskEvent":
        if not isinstance(raw, dict):
            raise ContractError("event must be a JSON object")
        if set(raw) != EVENT_KEYS:
            missing = sorted(EVENT_KEYS - set(raw))
            extra = sorted(set(raw) - EVENT_KEYS)
            raise ContractError(f"event keys differ; missing={missing}, extra={extra}")
        sequence = raw["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ContractError("sequence must be a positive integer")
        if raw["event_id"] != f"evt-{sequence:06d}":
            raise ContractError("event_id must match the sequence")
        event_type = _require_string(raw, "event_type")
        if event_type not in EVENT_TYPES:
            raise ContractError(f"unsupported event_type: {event_type}")
        for key in ("task_id", "subject_sha", "actor", "created_at", "event_digest"):
            _require_string(raw, key)
        previous = raw["previous_event_digest"]
        if previous is not None and (not isinstance(previous, str) or not previous):
            raise ContractError("previous_event_digest must be a digest string or null")
        payload = raw["payload"]
        if not isinstance(payload, dict):
            raise ContractError("payload must be a JSON object")
        expected = sha256_canonical(without_field(raw, "event_digest"))
        if raw["event_digest"] != expected:
            raise ContractError(
                f"event_digest mismatch: expected {expected}, received {raw['event_digest']}"
            )
        return cls(
            sequence=sequence,
            event_id=raw["event_id"],
            event_type=event_type,
            task_id=raw["task_id"],
            subject_sha=raw["subject_sha"],
            previous_event_digest=previous,
            payload=dict(payload),
            actor=raw["actor"],
            created_at=raw["created_at"],
            event_digest=raw["event_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "subject_sha": self.subject_sha,
            "previous_event_digest": self.previous_event_digest,
            "payload": dict(self.payload),
            "actor": self.actor,
            "created_at": self.created_at,
            "event_digest": self.event_digest,
        }

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        event_type: str,
        task_id: str,
        subject_sha: str,
        previous_event_digest: str | None,
        payload: dict[str, Any],
        actor: str,
        created_at: str,
    ) -> "TaskEvent":
        raw = {
            "sequence": sequence,
            "event_id": f"evt-{sequence:06d}",
            "event_type": event_type,
            "task_id": task_id,
            "subject_sha": subject_sha,
            "previous_event_digest": previous_event_digest,
            "payload": dict(payload),
            "actor": actor,
            "created_at": created_at,
        }
        raw["event_digest"] = sha256_canonical(raw)
        return cls.from_dict(raw)
