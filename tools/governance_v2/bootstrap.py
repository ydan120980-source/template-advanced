"""Read-only Stage 0 bootstrap snapshots and desired-plan previews."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import sha256_canonical


class BootstrapError(RuntimeError):
    """A local bootstrap fact or plan could not be trusted."""

    def __init__(self, message: str, *, status: str = "BLOCKED", code: str = "BOOTSTRAP_FAILED"):
        super().__init__(message)
        self.status = status
        self.code = code


def _git(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"git unavailable or timed out: {type(exc).__name__}", code="GIT_UNAVAILABLE") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise BootstrapError(f"git {' '.join(args)} failed: {detail or completed.returncode}", code="GIT_COMMAND_FAILED")
    return completed.stdout.decode("utf-8", "replace").strip()


def _write(path: Path, value: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BootstrapError(f"cannot write bootstrap output {path}: {type(exc).__name__}", code="OUTPUT_WRITE_FAILED") from exc


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootstrapError(f"snapshot not found: {path}", code="SNAPSHOT_NOT_FOUND") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"invalid snapshot {path}: {type(exc).__name__}", status="FAIL", code="SNAPSHOT_INVALID") from exc
    if not isinstance(value, dict):
        raise BootstrapError("snapshot must be an object", status="FAIL", code="SNAPSHOT_INVALID")
    return value


def snapshot(
    *,
    root: Path,
    repository_id: str = "ydan120980-source/template-advanced",
    base_ref: str = "origin/main",
    head_ref: str = "origin/codex/release-v1.1.0",
    expected_base_sha: str | None = None,
    expected_head_sha: str | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Capture local refs without claiming remote branch settings."""

    base_sha = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    head_sha = _git(root, "rev-parse", "--verify", f"{head_ref}^{{commit}}")
    current_sha = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    if expected_base_sha and base_sha != expected_base_sha:
        result = {"status": "BLOCKED", "code": "BASELINE_DRIFT", "expected_base_sha": expected_base_sha, "actual_base_sha": base_sha}
    elif expected_head_sha and head_sha != expected_head_sha:
        result = {"status": "BLOCKED", "code": "PR_HEAD_DRIFT", "expected_head_sha": expected_head_sha, "actual_head_sha": head_sha}
    else:
        result = {
            "status": "CACHED",
            "code": "LOCAL_BASELINE_ONLY",
            "repository_id": repository_id,
            "base_ref": base_ref,
            "base_sha": base_sha,
            "head_ref": head_ref,
            "head_sha": head_sha,
            "current_branch": branch,
            "current_head_sha": current_sha,
            "remote_fact_status": "NOT_READ",
            "remote_settings": None,
            "remote_writes": False,
            "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
    result["snapshot_digest"] = sha256_canonical({key: value for key, value in result.items() if key != "snapshot_digest"})
    if output is not None:
        _write(output, result)
        result["snapshot_path"] = str(output)
    return result


def plan(*, snapshot_path: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    """Create a non-mutating desired/rollback preview from a snapshot."""

    source: dict[str, Any] = {}
    if snapshot_path is not None:
        source = _read(snapshot_path)
        expected = source.get("snapshot_digest")
        actual = sha256_canonical({key: value for key, value in source.items() if key not in {"snapshot_digest", "snapshot_path"}})
        if expected and expected != actual:
            return {"status": "FAIL", "code": "SNAPSHOT_DIGEST_MISMATCH"}
    result: dict[str, Any] = {
        "status": "CACHED",
        "code": "READ_ONLY_PLAN",
        "remote_writes": False,
        "requires_confirm_write": True,
        "source_snapshot": str(snapshot_path) if snapshot_path else None,
        "snapshot_digest": source.get("snapshot_digest"),
        "desired_payload": {
            "merge_method": "squash",
            "allow_auto_merge": False,
            "delete_branch_on_merge": False,
            "required_approving_review_count": 0,
            "required_checks": "preserve_existing_until_verified",
        },
        "rollback_payload": {
            "source": "snapshot_required",
            "restore_order": "reverse",
        },
        "not_applied": True,
    }
    result["plan_digest"] = sha256_canonical({key: value for key, value in result.items() if key != "plan_digest"})
    if output is not None:
        _write(output, result)
        result["plan_path"] = str(output)
    return result
