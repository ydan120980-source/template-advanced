"""Stage 0 snapshots plus bounded local-bootstrap task authority."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .canonical import sha256_canonical
from .issue import IssueCommandError, load_contract, read_issue_authority, verify_event_chain
from .models import ContractError, TaskContract, TaskEvent


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


def _ref_candidates(ref: str) -> tuple[str, ...]:
    """Return the full ref names that Git may resolve from a short ref."""

    if ref.startswith("refs/"):
        return (ref,)
    return (
        ref,
        f"refs/heads/{ref}",
        f"refs/remotes/{ref}",
        f"refs/tags/{ref}",
    )


def _ref_exists(root: Path, ref: str) -> bool | None:
    """Return whether a ref exists, or None when Git cannot be classified."""

    for candidate in _ref_candidates(ref):
        try:
            completed = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", candidate],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode == 0:
            return True
        if completed.returncode != 1:
            return None
    return False


def _missing_refs(root: Path, refs: tuple[str, ...]) -> tuple[str, ...] | None:
    """Find unavailable refs without converting unrelated Git errors to cache."""

    missing: list[str] = []
    for ref in refs:
        exists = _ref_exists(root, ref)
        if exists is None:
            return None
        if not exists:
            missing.append(ref)
    return tuple(missing)


def _write(path: Path, value: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BootstrapError(f"cannot write bootstrap output {path}: {type(exc).__name__}", code="OUTPUT_WRITE_FAILED") from exc


def _write_temp_payload(stream: BinaryIO, payload: bytes) -> None:
    """Finish one temporary record before it can become externally visible."""

    stream.write(payload)
    stream.flush()
    os.fsync(stream.fileno())


def _publish_new(path: Path, value: dict[str, Any]) -> bool:
    """Atomically publish a complete same-directory record without replacement.

    The hard-link publication step is create-only on both Windows and POSIX:
    an existing immutable target is never overwritten.  Writing and syncing a
    private temporary file first also means a torn write cannot expose partial
    JSON at the authority, pending, or receipt path.
    """

    temporary: Path | None = None
    descriptor: int | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            _write_temp_payload(stream, payload)
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        return True
    except (OSError, UnicodeError) as exc:
        raise BootstrapError(
            f"cannot atomically publish bootstrap record {path}: {type(exc).__name__}",
            code="OUTPUT_WRITE_FAILED",
        ) from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # The complete target, if linked, remains valid. A later
                # cleanup or Doctor run may remove an orphaned private temp.
                pass


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

    metadata = {
        "repository_id": repository_id,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "expected_base_sha": expected_base_sha,
        "expected_head_sha": expected_head_sha,
        "remote_fact_status": "NOT_READ",
        "remote_settings": None,
        "remote_writes": False,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    try:
        _git(root, "rev-parse", "--show-toplevel")
    except BootstrapError as exc:
        if expected_base_sha or expected_head_sha:
            result = {
                **metadata,
                "status": "BLOCKED",
                "code": "LOCAL_GIT_UNAVAILABLE",
                "message": str(exc),
                "local_git_status": "NOT_AVAILABLE",
                "base_sha": None,
                "head_sha": None,
                "current_branch": None,
                "current_head_sha": None,
            }
        else:
            result = {
                **metadata,
                "status": "CACHED",
                "code": "LOCAL_BASELINE_UNAVAILABLE",
                "message": str(exc),
                "local_git_status": "NOT_AVAILABLE",
                "base_sha": None,
                "head_sha": None,
                "current_branch": None,
                "current_head_sha": None,
            }
    else:
        base_sha: str | None = None
        head_sha: str | None = None
        try:
            base_sha = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
            head_sha = _git(root, "rev-parse", "--verify", f"{head_ref}^{{commit}}")
        except BootstrapError as exc:
            missing_refs = _missing_refs(root, (base_ref, head_ref))
            if missing_refs:
                missing = ", ".join(missing_refs)
                if expected_base_sha or expected_head_sha:
                    result = {
                        **metadata,
                        "status": "BLOCKED",
                        "code": "EXPECTED_REF_UNAVAILABLE",
                        "message": f"required local ref(s) unavailable: {missing}; {exc}",
                        "local_git_status": "AVAILABLE",
                        "base_sha": base_sha,
                        "head_sha": head_sha,
                        "current_branch": None,
                        "current_head_sha": None,
                    }
                else:
                    result = {
                        **metadata,
                        "status": "CACHED",
                        "code": "LOCAL_BASELINE_INCOMPLETE",
                        "message": f"required local ref(s) unavailable: {missing}; {exc}",
                        "local_git_status": "AVAILABLE",
                        "base_sha": base_sha,
                        "head_sha": head_sha,
                        "current_branch": None,
                        "current_head_sha": None,
                    }
            else:
                raise
        else:
            current_sha = _git(root, "rev-parse", "HEAD")
            branch = _git(root, "branch", "--show-current")
            if expected_base_sha and base_sha != expected_base_sha:
                result = {
                    **metadata,
                    "status": "BLOCKED",
                    "code": "BASELINE_DRIFT",
                    "expected_base_sha": expected_base_sha,
                    "actual_base_sha": base_sha,
                    "local_git_status": "AVAILABLE",
                    "base_sha": base_sha,
                    "head_sha": head_sha,
                    "current_branch": branch,
                    "current_head_sha": current_sha,
                }
            elif expected_head_sha and head_sha != expected_head_sha:
                result = {
                    **metadata,
                    "status": "BLOCKED",
                    "code": "PR_HEAD_DRIFT",
                    "expected_head_sha": expected_head_sha,
                    "actual_head_sha": head_sha,
                    "local_git_status": "AVAILABLE",
                    "base_sha": base_sha,
                    "head_sha": head_sha,
                    "current_branch": branch,
                    "current_head_sha": current_sha,
                }
            else:
                result = {
                    **metadata,
                    "status": "CACHED",
                    "code": "LOCAL_BASELINE_ONLY",
                    "local_git_status": "AVAILABLE",
                    "base_sha": base_sha,
                    "head_sha": head_sha,
                    "current_branch": branch,
                    "current_head_sha": current_sha,
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


_BOOTSTRAP_SCHEMA = "governance.local-bootstrap/v1"
_ADOPTION_SCHEMA = "governance.local-bootstrap-adoption/v1"
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _bootstrap_directory(root: Path, task_id: str) -> Path:
    if not _TASK_ID_RE.fullmatch(task_id):
        raise BootstrapError("task_id is unsafe for a bootstrap path", code="INVALID_TASK_ID")
    return root / ".aiwf" / "bootstrap" / task_id


def _authority_path(root: Path, task_id: str) -> Path:
    return _bootstrap_directory(root, task_id) / "authority.json"


def _adoption_pending_path(root: Path, task_id: str) -> Path:
    return _bootstrap_directory(root, task_id) / "adoption-pending.json"


def _adoption_receipt_path(root: Path, task_id: str) -> Path:
    return _bootstrap_directory(root, task_id) / "adoption-receipt.json"


def _record_digest(value: dict[str, Any], field: str) -> str:
    return sha256_canonical({key: item for key, item in value.items() if key != field})


def _write_once(path: Path, value: dict[str, Any], *, digest_field: str) -> bool:
    """Create one immutable local record, returning False for an identical retry."""

    if path.exists():
        existing = _read(path)
        expected = existing.get(digest_field)
        if not isinstance(expected, str) or expected != _record_digest(existing, digest_field):
            raise BootstrapError(
                f"existing bootstrap record is invalid: {path}",
                status="FAIL",
                code="BOOTSTRAP_RECORD_INVALID",
            )
        if existing != value:
            raise BootstrapError(
                f"immutable bootstrap record already exists with different content: {path}",
                code="BOOTSTRAP_RECORD_CONFLICT",
            )
        return False
    if _publish_new(path, value):
        return True
    existing = _read(path)
    expected = existing.get(digest_field)
    if not isinstance(expected, str) or expected != _record_digest(existing, digest_field):
        raise BootstrapError(
            f"existing bootstrap record is invalid: {path}",
            status="FAIL",
            code="BOOTSTRAP_RECORD_INVALID",
        )
    if existing != value:
        raise BootstrapError(
            f"immutable bootstrap record already exists with different content: {path}",
            code="BOOTSTRAP_RECORD_CONFLICT",
        )
    return False


def _load_authority(root: Path, task_id: str) -> tuple[dict[str, Any], TaskContract]:
    path = _authority_path(root, task_id)
    if not path.is_file():
        raise BootstrapError(
            f"local bootstrap authority not found: {path}",
            code="LOCAL_BOOTSTRAP_NOT_FOUND",
        )
    record = _read(path)
    if record.get("schema") != _BOOTSTRAP_SCHEMA or record.get("authority") != "local_bootstrap":
        raise BootstrapError(
            "local bootstrap authority record has an invalid schema",
            status="FAIL",
            code="BOOTSTRAP_RECORD_INVALID",
        )
    digest = record.get("record_digest")
    if not isinstance(digest, str) or digest != _record_digest(record, "record_digest"):
        raise BootstrapError(
            "local bootstrap authority record digest mismatch",
            status="FAIL",
            code="BOOTSTRAP_RECORD_INVALID",
        )
    raw_contract = record.get("contract")
    try:
        contract = TaskContract.from_dict(raw_contract)
    except ContractError as exc:
        raise BootstrapError(
            f"embedded bootstrap contract is invalid: {exc}",
            status="FAIL",
            code="BOOTSTRAP_CONTRACT_INVALID",
        ) from exc
    if (
        record.get("task_id") != task_id
        or record.get("task_id") != contract.data["task_id"]
        or record.get("repository_id") != contract.data["repository_id"]
        or record.get("base_sha") != contract.data["base_sha"]
        or record.get("contract_digest") != contract.digest
    ):
        raise BootstrapError(
            "bootstrap authority metadata does not match its embedded contract",
            status="FAIL",
            code="BOOTSTRAP_RECORD_INVALID",
        )
    return record, contract


def _load_adoption_record(
    path: Path,
    *,
    state: str,
    authority: dict[str, Any],
    contract: TaskContract,
    issue_number: int | None = None,
    pending: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a handoff record before using it as authority lifecycle evidence."""

    value = _read(path)
    common_keys = {
        "schema", "state", "task_id", "repository_id", "issue_number",
        "issue_url", "base_sha", "contract_digest", "bootstrap_record_digest",
        "remote_writes", "record_digest",
    }
    receipt_keys = {
        "pending_record_digest", "adoption_event", "adoption_event_digest",
        "adoption_subject_sha",
    }
    expected_keys = common_keys | (receipt_keys if state == "adopted" else set())
    if set(value) != expected_keys:
        raise BootstrapError("adoption record fields are invalid", status="FAIL", code="ADOPTION_RECORD_INVALID")
    if value.get("record_digest") != _record_digest(value, "record_digest"):
        raise BootstrapError("adoption record digest mismatch", status="FAIL", code="ADOPTION_RECORD_INVALID")
    number = value.get("issue_number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise BootstrapError("adoption Issue number is invalid", status="FAIL", code="ADOPTION_RECORD_INVALID")
    expected = {
        "schema": _ADOPTION_SCHEMA,
        "state": state,
        "task_id": contract.data["task_id"],
        "repository_id": contract.data["repository_id"],
        "base_sha": contract.data["base_sha"],
        "contract_digest": contract.digest,
        "bootstrap_record_digest": authority["record_digest"],
        "issue_url": f"https://github.com/{contract.data['repository_id']}/issues/{number}",
        "remote_writes": False,
    }
    if (
        any(value.get(key) != item for key, item in expected.items())
        or value.get("remote_writes") is not False
        or (issue_number is not None and number != issue_number)
    ):
        raise BootstrapError("adoption record identity conflicts with authority", status="FAIL", code="ADOPTION_RECORD_CONFLICT")
    if state == "adopted":
        if pending is None or value.get("pending_record_digest") != pending["record_digest"] or number != pending["issue_number"]:
            raise BootstrapError("adoption receipt is not bound to its pending handoff", status="FAIL", code="ADOPTION_RECORD_CONFLICT")
        try:
            event = TaskEvent.from_dict(value.get("adoption_event"))
        except (ContractError, TypeError, KeyError) as exc:
            raise BootstrapError("receipt adoption event is invalid", status="FAIL", code="ADOPTION_RECORD_INVALID") from exc
        if (
            event.event_type != "bootstrap_contract_adopted"
            or event.task_id != contract.data["task_id"]
            or event.payload.get("contract_digest") != contract.digest
            or event.payload.get("bootstrap_record_digest") != authority["record_digest"]
            or event.event_digest != value.get("adoption_event_digest")
            or event.subject_sha != value.get("adoption_subject_sha")
            or not re.fullmatch(r"[0-9a-fA-F]{40}", event.subject_sha)
        ):
            raise BootstrapError("receipt adoption event identity conflicts", status="FAIL", code="ADOPTION_RECORD_CONFLICT")
    return value


def _require_expected_digest(contract: TaskContract, expected_digest: str) -> None:
    if not expected_digest or contract.digest != expected_digest:
        raise BootstrapError(
            "expected contract digest does not match the approved contract",
            code="EXPECTED_CONTRACT_DIGEST_MISMATCH",
        )


def _verify_repository_history(root: Path, contract: TaskContract, *, initial: bool) -> str:
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
        head = _git(root, "rev-parse", "HEAD")
        base = _git(root, "rev-parse", "--verify", f"{contract.data['base_sha']}^{{commit}}")
    except BootstrapError:
        raise
    if top != root.resolve():
        raise BootstrapError("bootstrap root must be the Git work-tree root", code="REPOSITORY_ROOT_MISMATCH")
    if base != contract.data["base_sha"]:
        raise BootstrapError("contract base_sha is not the resolved Git commit", code="BASE_SHA_MISMATCH")
    if initial and head != base:
        raise BootstrapError(
            "initial local bootstrap requires HEAD to equal contract base_sha",
            code="INITIAL_HEAD_BASE_MISMATCH",
        )
    if not initial:
        try:
            ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", base, head],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BootstrapError(
                f"cannot verify Git ancestry: {type(exc).__name__}",
                code="GIT_UNAVAILABLE",
            ) from exc
        if ancestor.returncode != 0:
            raise BootstrapError(
                "contract base_sha is no longer an ancestor of HEAD",
                code="BASE_NOT_IN_CURRENT_HISTORY",
            )
    return head


def init_local_authority(
    *,
    root: Path,
    contract_path: Path,
    expected_digest: str,
    repository_id: str,
    authorization_ref: str,
) -> dict[str, Any]:
    """Create one immutable local authority record for a user-approved v2 contract."""

    if not authorization_ref.strip():
        raise BootstrapError("authorization_ref must be non-empty", code="AUTHORIZATION_REF_REQUIRED")
    contract = load_contract(contract_path)
    _require_expected_digest(contract, expected_digest)
    if contract.data["repository_id"] != repository_id:
        raise BootstrapError(
            "approved repository identity does not match contract",
            code="REPOSITORY_CONTRACT_MISMATCH",
        )
    head = _verify_repository_history(root, contract, initial=True)
    path = _authority_path(root, contract.data["task_id"])
    if path.exists():
        existing, existing_contract = _load_authority(root, contract.data["task_id"])
        if (
            existing_contract.to_dict() != contract.to_dict()
            or existing.get("authorization_ref") != authorization_ref
            or existing.get("repository_id") != repository_id
        ):
            raise BootstrapError(
                "immutable bootstrap authority already exists with different approved context",
                code="BOOTSTRAP_RECORD_CONFLICT",
            )
        return {
            "status": "PASS",
            "code": "LOCAL_BOOTSTRAP_ALREADY_INITIALIZED",
            "authority": "local_bootstrap",
            "task_id": contract.data["task_id"],
            "repository_id": repository_id,
            "base_sha": contract.data["base_sha"],
            "current_head_sha": head,
            "contract_digest": contract.digest,
            "record_digest": existing["record_digest"],
            "authority_path": str(path),
            "remote_gate": "NOT_RUN",
            "remote_writes": False,
        }
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record: dict[str, Any] = {
        "schema": _BOOTSTRAP_SCHEMA,
        "authority": "local_bootstrap",
        "task_id": contract.data["task_id"],
        "repository_id": contract.data["repository_id"],
        "base_sha": contract.data["base_sha"],
        "contract_digest": contract.digest,
        "authorization_ref": authorization_ref,
        "contract": contract.to_dict(),
        "created_at": now,
        "remote_gate": "NOT_RUN",
        "remote_writes": False,
    }
    record["record_digest"] = _record_digest(record, "record_digest")
    created = _write_once(path, record, digest_field="record_digest")
    return {
        "status": "PASS",
        "code": "LOCAL_BOOTSTRAP_INITIALIZED" if created else "LOCAL_BOOTSTRAP_ALREADY_INITIALIZED",
        "authority": "local_bootstrap",
        "task_id": contract.data["task_id"],
        "repository_id": contract.data["repository_id"],
        "base_sha": contract.data["base_sha"],
        "current_head_sha": head,
        "contract_digest": contract.digest,
        "record_digest": record["record_digest"],
        "authority_path": str(path),
        "remote_gate": "NOT_RUN",
        "remote_writes": False,
    }


def verify_local_authority(
    *,
    root: Path,
    task_id: str,
    expected_digest: str,
    repository_id: str,
) -> dict[str, Any]:
    """Verify immutable local authority against approved digest and current Git history."""

    record, contract = _load_authority(root, task_id)
    _require_expected_digest(contract, expected_digest)
    if contract.data["repository_id"] != repository_id:
        raise BootstrapError(
            "approved repository identity does not match local authority",
            code="REPOSITORY_CONTRACT_MISMATCH",
        )
    receipt_path = _adoption_receipt_path(root, task_id)
    pending_path = _adoption_pending_path(root, task_id)
    pending = (
        _load_adoption_record(pending_path, state="pending", authority=record, contract=contract)
        if pending_path.exists() else None
    )
    if receipt_path.exists():
        _load_adoption_record(receipt_path, state="adopted", authority=record, contract=contract, pending=pending)
        raise BootstrapError(
            "local bootstrap authority has been retired by remote adoption",
            code="LOCAL_BOOTSTRAP_RETIRED",
        )
    if pending is not None:
        raise BootstrapError(
            "remote adoption is pending; local execution is blocked to avoid dual authority",
            code="ADOPTION_HANDOFF_PENDING",
        )
    head = _verify_repository_history(root, contract, initial=False)
    return {
        "status": "PASS",
        "code": "LOCAL_BOOTSTRAP_VALID",
        "authority": "local_bootstrap",
        "task_id": task_id,
        "repository_id": contract.data["repository_id"],
        "base_sha": contract.data["base_sha"],
        "current_head_sha": head,
        "contract_digest": contract.digest,
        "record_digest": record["record_digest"],
        "remote_gate": "NOT_RUN",
        "remote_writes": False,
    }


def adopt_local_authority(
    *,
    root: Path,
    task_id: str,
    expected_digest: str,
    repo: str,
    issue_number: int,
    timeout: float = 15.0,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Read remote Issue authority and retire local authority only after a matching adoption event."""

    record, contract = _load_authority(root, task_id)
    _require_expected_digest(contract, expected_digest)
    if repo != contract.data["repository_id"]:
        raise BootstrapError("remote repository does not match contract", code="REPOSITORY_CONTRACT_MISMATCH")
    if isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number < 1:
        raise BootstrapError("Issue number must be positive", code="INVALID_ISSUE_NUMBER")
    _verify_repository_history(root, contract, initial=False)

    pending_path = _adoption_pending_path(root, task_id)
    pending = (
        _load_adoption_record(pending_path, state="pending", authority=record, contract=contract, issue_number=issue_number)
        if pending_path.exists() else None
    )
    receipt_path = _adoption_receipt_path(root, task_id)
    receipt = (
        _load_adoption_record(receipt_path, state="adopted", authority=record, contract=contract, issue_number=issue_number, pending=pending)
        if receipt_path.exists() else None
    )

    try:
        remote = read_issue_authority(
            repo=repo,
            issue_number=issue_number,
            timeout=timeout,
            opener=opener,
        )
    except IssueCommandError as exc:
        raise BootstrapError(str(exc), status=exc.status, code=exc.code) from exc
    if remote.get("contract_digest") != contract.digest or remote.get("contract") != contract.to_dict():
        raise BootstrapError(
            "remote Issue contract is not byte-equivalent in canonical v2 meaning",
            code="ADOPTION_CONTRACT_MISMATCH",
        )

    issue_url = f"https://github.com/{repo}/issues/{issue_number}"
    if remote.get("repository") != repo or remote.get("issue_number") != issue_number or remote.get("issue_url") != issue_url:
        raise BootstrapError("remote Issue identity conflicts with requested handoff", code="ADOPTION_ISSUE_MISMATCH")
    pending_value: dict[str, Any] = {
        "schema": _ADOPTION_SCHEMA,
        "state": "pending",
        "task_id": task_id,
        "repository_id": repo,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "base_sha": contract.data["base_sha"],
        "contract_digest": contract.digest,
        "bootstrap_record_digest": record["record_digest"],
        "remote_writes": False,
    }
    pending_value["record_digest"] = _record_digest(pending_value, "record_digest")
    _write_once(pending_path, pending_value, digest_field="record_digest")

    raw_events = remote.get("events", [])
    if not isinstance(raw_events, list):
        raise BootstrapError("remote events must be an array", status="FAIL", code="INVALID_EVENT")
    verified_chain = verify_event_chain(raw_events)
    if raw_events and verified_chain.get("status") != "PASS":
        raise BootstrapError("remote adoption event chain is invalid", status="FAIL", code=str(verified_chain["code"]))
    matching_events: list[TaskEvent] = []
    for raw_event in raw_events:
        try:
            event = TaskEvent.from_dict(raw_event)
        except ContractError as exc:
            raise BootstrapError(
                f"remote adoption event chain contains an invalid event: {exc}",
                status="FAIL",
                code="INVALID_EVENT",
            ) from exc
        if event.event_type != "bootstrap_contract_adopted":
            continue
        if (
            event.task_id == task_id
            and event.payload.get("contract_digest") == contract.digest
            and event.payload.get("bootstrap_record_digest") == record["record_digest"]
        ):
            if not re.fullmatch(r"[0-9a-fA-F]{40}", event.subject_sha):
                raise BootstrapError("adoption subject must be a full commit SHA", status="FAIL", code="INVALID_EVENT")
            matching_events.append(event)
    if len(matching_events) > 1:
        raise BootstrapError("multiple matching adoption events conflict", status="FAIL", code="ADOPTION_EVENT_CONFLICT")
    if not matching_events:
        raise BootstrapError(
            "matching bootstrap_contract_adopted event is not present; local execution is now blocked pending handoff",
            code="ADOPTION_EVENT_REQUIRED",
        )

    matching_event = matching_events[0]
    if receipt is not None:
        if (
            receipt["adoption_event"] != matching_event.to_dict()
        ):
            raise BootstrapError("receipt differs from verified remote adoption evidence", status="FAIL", code="ADOPTION_RECEIPT_CONFLICT")
        return {
            "status": "PASS",
            "code": "LOCAL_BOOTSTRAP_ALREADY_ADOPTED",
            "authority": "issue",
            "task_id": task_id,
            "repository_id": repo,
            "contract_digest": contract.digest,
            "issue_number": issue_number,
            "adoption_event_digest": matching_event.event_digest,
            "adoption_subject_sha": matching_event.subject_sha,
            "remote_writes": False,
        }
    receipt_value: dict[str, Any] = {
        "schema": _ADOPTION_SCHEMA,
        "state": "adopted",
        "task_id": task_id,
        "repository_id": repo,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "base_sha": contract.data["base_sha"],
        "contract_digest": contract.digest,
        "bootstrap_record_digest": record["record_digest"],
        "adoption_event_digest": matching_event.event_digest,
        "adoption_subject_sha": matching_event.subject_sha,
        "adoption_event": matching_event.to_dict(),
        "pending_record_digest": pending_value["record_digest"],
        "remote_writes": False,
    }
    receipt_value["record_digest"] = _record_digest(receipt_value, "record_digest")
    _write_once(receipt_path, receipt_value, digest_field="record_digest")
    return {
        "status": "PASS",
        "code": "LOCAL_BOOTSTRAP_ADOPTED",
        "authority": "issue",
        "task_id": task_id,
        "repository_id": repo,
        "issue_number": issue_number,
        "contract_digest": contract.digest,
        "adoption_event_digest": matching_event.event_digest,
        "adoption_subject_sha": matching_event.subject_sha,
        "receipt_path": str(receipt_path),
        "remote_writes": False,
    }
