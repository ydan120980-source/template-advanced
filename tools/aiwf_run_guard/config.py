"""Validated configuration and path rules for AIWF Run Guard."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable

from .models import ConfigError


CONFIG_FILE = "run-guard.json"


def normalize_relative_path(raw: str) -> str:
    """Normalize a portable project-relative path or reject unsafe input."""

    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError("paths must be non-empty strings")
    value = raw.strip().replace("\\", "/")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ConfigError(f"absolute path is not allowed: {raw}")
    pure = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ConfigError(f"path must stay inside the project root: {raw}")
    return pure.as_posix().rstrip("/")


def path_matches_prefix(path: str, prefix: str) -> bool:
    if os.name == "nt":
        path = path.casefold()
        prefix = prefix.casefold()
    return path == prefix or path.startswith(prefix + "/")


def path_matches_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path_matches_prefix(path, prefix) for prefix in prefixes)


def artifact_identity_key(path: str) -> str:
    """Return the platform-correct identity key used to deduplicate recorded files.

    Windows filesystems are case-insensitive, so ``tools/core/Output.txt`` and
    ``tools/core/output.txt`` denote the same file and must collapse to one
    identity key. POSIX filesystems are case-sensitive, so the two names are
    distinct artifacts and must keep distinct keys. This mirrors the
    platform-aware semantics of :func:`path_matches_prefix`; callers must never
    apply an unconditional ``casefold()`` that disagrees with scope matching.
    """

    if os.name == "nt":
        return path.casefold()
    return path


@dataclass(frozen=True, slots=True)
class WorkstreamConfig:
    workstream_id: str
    owner: str
    owned_paths: tuple[str, ...]
    require_handoff: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.workstream_id,
            "owner": self.owner,
            "owned_paths": list(self.owned_paths),
            "require_handoff": self.require_handoff,
        }


@dataclass(frozen=True, slots=True)
class CommandBudgetConfig:
    limit: int
    metric: str
    required_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "metric": self.metric,
            "required_sources": list(self.required_sources),
        }


@dataclass(frozen=True, slots=True)
class ArtifactBudgetConfig:
    limit: int
    metric: str

    def to_dict(self) -> dict[str, Any]:
        return {"limit": self.limit, "metric": self.metric}


@dataclass(frozen=True, slots=True)
class RunConfig:
    task_id: str
    retry_limit: int
    workstreams: tuple[WorkstreamConfig, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    require_validation: bool
    require_review: bool
    first_artifact_seconds: int | None
    heartbeat_seconds: int | None
    command_budget: CommandBudgetConfig | None
    artifact_budget: ArtifactBudgetConfig | None

    @property
    def workstream_map(self) -> dict[str, WorkstreamConfig]:
        return {item.workstream_id: item for item in self.workstreams}

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "retry_limit": self.retry_limit,
            "workstreams": [item.to_dict() for item in self.workstreams],
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "require_validation": self.require_validation,
            "require_review": self.require_review,
            "first_artifact_seconds": self.first_artifact_seconds,
            "heartbeat_seconds": self.heartbeat_seconds,
            "command_budget": (
                self.command_budget.to_dict() if self.command_budget else None
            ),
            "artifact_budget": (
                self.artifact_budget.to_dict() if self.artifact_budget else None
            ),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RunConfig":
        if not isinstance(raw, dict):
            raise ConfigError("configuration must be a JSON object")
        required = {
            "task_id",
            "retry_limit",
            "workstreams",
            "allowed_paths",
            "forbidden_paths",
            "require_validation",
            "require_review",
            "first_artifact_seconds",
        }
        optional = {"heartbeat_seconds", "command_budget", "artifact_budget"}
        if not required.issubset(raw) or not set(raw).issubset(required | optional):
            raise ConfigError(
                "configuration keys differ; "
                f"missing={sorted(required - set(raw))}, "
                f"extra={sorted(set(raw) - required - optional)}"
            )
        task_id = raw["task_id"]
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}", task_id):
            raise ConfigError("task_id must be 3-128 portable identifier characters")
        retry_limit = raw["retry_limit"]
        if isinstance(retry_limit, bool) or not isinstance(retry_limit, int) or retry_limit < 0:
            raise ConfigError("retry_limit must be a non-negative integer")
        for boolean_key in ("require_validation", "require_review"):
            if not isinstance(raw[boolean_key], bool):
                raise ConfigError(f"{boolean_key} must be boolean")
        timeouts: dict[str, int | None] = {}
        for timeout_key in ("first_artifact_seconds", "heartbeat_seconds"):
            timeout = raw.get(timeout_key)
            if timeout is not None and (
                isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1
            ):
                raise ConfigError(f"{timeout_key} must be null or a positive integer")
            timeouts[timeout_key] = timeout

        command_budget_raw = raw.get("command_budget")
        command_budget: CommandBudgetConfig | None = None
        if command_budget_raw is not None:
            if not isinstance(command_budget_raw, dict) or set(command_budget_raw) != {
                "limit",
                "metric",
                "required_sources",
            }:
                raise ConfigError("command_budget has invalid keys")
            command_limit = command_budget_raw["limit"]
            if (
                isinstance(command_limit, bool)
                or not isinstance(command_limit, int)
                or command_limit < 0
            ):
                raise ConfigError("command_budget.limit must be non-negative")
            if command_budget_raw["metric"] != "shell_command_requests":
                raise ConfigError(
                    "command_budget.metric must be shell_command_requests"
                )
            sources_raw = command_budget_raw["required_sources"]
            if not isinstance(sources_raw, list) or not sources_raw:
                raise ConfigError(
                    "command_budget.required_sources must be a non-empty list"
                )
            if not all(
                isinstance(item, str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", item)
                for item in sources_raw
            ):
                raise ConfigError("command_budget.required_sources contains an invalid ID")
            sources = tuple(sorted(set(sources_raw)))
            if len(sources) != len(sources_raw):
                raise ConfigError("command_budget.required_sources contains duplicates")
            command_budget = CommandBudgetConfig(
                limit=command_limit,
                metric="shell_command_requests",
                required_sources=sources,
            )

        artifact_budget_raw = raw.get("artifact_budget")
        artifact_budget: ArtifactBudgetConfig | None = None
        if artifact_budget_raw is not None:
            if not isinstance(artifact_budget_raw, dict) or set(artifact_budget_raw) != {
                "limit",
                "metric",
            }:
                raise ConfigError("artifact_budget has invalid keys")
            artifact_limit = artifact_budget_raw["limit"]
            if (
                isinstance(artifact_limit, bool)
                or not isinstance(artifact_limit, int)
                or artifact_limit < 0
            ):
                raise ConfigError("artifact_budget.limit must be non-negative")
            if artifact_budget_raw["metric"] != "unique_artifact_files":
                raise ConfigError(
                    "artifact_budget.metric must be unique_artifact_files"
                )
            artifact_budget = ArtifactBudgetConfig(
                limit=artifact_limit,
                metric="unique_artifact_files",
            )

        allowed = _path_list(raw["allowed_paths"], "allowed_paths", require_nonempty=True)
        forbidden = _path_list(raw["forbidden_paths"], "forbidden_paths")
        workstreams_raw = raw["workstreams"]
        if not isinstance(workstreams_raw, list) or not workstreams_raw:
            raise ConfigError("workstreams must be a non-empty list")
        workstreams: list[WorkstreamConfig] = []
        seen: set[str] = set()
        for index, item in enumerate(workstreams_raw):
            if not isinstance(item, dict) or set(item) != {
                "id",
                "owner",
                "owned_paths",
                "require_handoff",
            }:
                raise ConfigError(f"workstreams[{index}] has invalid keys")
            workstream_id = item["id"]
            owner = item["owner"]
            if not isinstance(workstream_id, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", workstream_id
            ):
                raise ConfigError(f"workstreams[{index}].id is invalid")
            if workstream_id in seen:
                raise ConfigError(f"duplicate workstream id: {workstream_id}")
            seen.add(workstream_id)
            if not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", owner):
                raise ConfigError(f"workstreams[{index}].owner is invalid")
            if not isinstance(item["require_handoff"], bool):
                raise ConfigError(f"workstreams[{index}].require_handoff must be boolean")
            owned = _path_list(
                item["owned_paths"],
                f"workstreams[{index}].owned_paths",
                require_nonempty=item["require_handoff"],
            )
            if any(not path_matches_any(path, allowed) for path in owned):
                raise ConfigError(f"workstream {workstream_id} owns a path outside allowed_paths")
            workstreams.append(
                WorkstreamConfig(
                    workstream_id=workstream_id,
                    owner=owner,
                    owned_paths=owned,
                    require_handoff=item["require_handoff"],
                )
            )
        return cls(
            task_id=task_id,
            retry_limit=retry_limit,
            workstreams=tuple(workstreams),
            allowed_paths=allowed,
            forbidden_paths=forbidden,
            require_validation=raw["require_validation"],
            require_review=raw["require_review"],
            first_artifact_seconds=timeouts["first_artifact_seconds"],
            heartbeat_seconds=timeouts["heartbeat_seconds"],
            command_budget=command_budget,
            artifact_budget=artifact_budget,
        )


def _path_list(raw: Any, label: str, require_nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ConfigError(f"{label} must be a list of strings")
    normalized = tuple(sorted({normalize_relative_path(item) for item in raw}))
    if require_nonempty and not normalized:
        raise ConfigError(f"{label} must not be empty")
    return normalized


def load_config(path_or_plan_dir: Path | str) -> RunConfig:
    path = Path(path_or_plan_dir)
    if path.is_dir():
        path = path / CONFIG_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration not found: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read configuration: {type(exc).__name__}: {exc}") from exc
    return RunConfig.from_dict(raw)


def ownership_overlaps(config: RunConfig) -> tuple[tuple[str, str, str, str], ...]:
    conflicts: list[tuple[str, str, str, str]] = []
    items = list(config.workstreams)
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            for left_path in left.owned_paths:
                for right_path in right.owned_paths:
                    if path_matches_prefix(left_path, right_path) or path_matches_prefix(
                        right_path, left_path
                    ):
                        conflicts.append(
                            (left.workstream_id, left_path, right.workstream_id, right_path)
                        )
    return tuple(sorted(conflicts))
