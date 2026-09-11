"""Grade candidate trial trees with frozen independent acceptors.

Trust rules:

- The scope baseline (file manifest) is supplied by the coordinator from a
  location the candidate cannot alter; a candidate tree never decides its
  own comparison baseline.
- The acceptor runs in an isolated subprocess. Its verdict is ACCEPT or
  REJECT only when scenarios actually executed; an infrastructure failure
  is reported as BLOCKED and is never evidence about the candidate.
- Coordinator-recorded budget data (elapsed time, shell-bearing request
  count, human interventions) is stored with the grade record.
- Trial validity is a separate, coordinator-authored attestation. A grade
  record says what the candidate *did*; it never says the run was a valid
  independent trial. ``trial_validity`` carries VALID / INVALID /
  UNVERIFIED plus the audit basis, defaults to UNVERIFIED when the
  coordinator supplies nothing, and must cite an audit record for any
  non-UNVERIFIED state, so a trial agent cannot self-certify. A missing
  attestation is never upgraded to valid.
- ``trial_isolated`` records one narrow check only: that the pre-scoring Git
  root probe passed (the candidate directory owns its ``.git`` and
  ``rev-parse --show-toplevel`` resolves to it). It is a prerequisite for a
  valid trial, not evidence of independence: a run can pass the Git probe
  and still read the source repository through a non-shell tool.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from .prepare import trial_isolation_problem
from .tasks import TaskDefinition


class GradeError(RuntimeError):
    """The candidate tree could not be graded."""


_RUNNER = Path(__file__).resolve().parent / "_acceptor_runner.py"

# Coordinator-owned files inside the trial directory that are expected to
# differ from the exported snapshot and never count as candidate changes.
_COORDINATOR_FILES = {"trial-metadata.json"}

# The three states a trial's protocol validity can take. UNVERIFIED is the
# default and never fills a valid comparison slot.
VALIDITY_STATES = ("VALID", "INVALID", "UNVERIFIED")


def _validate_validity(validity: dict[str, object] | None, *, run_kind: str) -> dict[str, object]:
    """Validate the coordinator's trial-validity attestation.

    A trial that carries no attestation is UNVERIFIED, never valid: the
    absence of an audit is not evidence that the run was independent. Any
    non-UNVERIFIED claim must name both a reason and the audit record it
    rests on, so a claim cannot be asserted without the artefact behind it.
    """

    if run_kind != "trial":
        if validity:
            raise GradeError("trial validity is only defined for run_kind='trial'")
        return {}
    if validity is None:
        return {
            "status": "UNVERIFIED",
            "basis": "no coordinator audit was recorded for this run",
            "audit_record": None,
        }
    if not isinstance(validity, dict):
        raise GradeError("trial validity must be a mapping")
    status = validity.get("status")
    if status not in VALIDITY_STATES:
        raise GradeError(
            f"trial validity status must be one of {VALIDITY_STATES}, got {status!r}"
        )
    basis = validity.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise GradeError("a trial validity attestation requires a non-empty basis")
    record: dict[str, object] = {"status": status, "basis": basis.strip()}
    audit_record = validity.get("audit_record")
    if status != "UNVERIFIED":
        if not isinstance(audit_record, str) or not audit_record.strip():
            raise GradeError(
                "a VALID or INVALID attestation must cite the coordinator audit "
                "record it rests on"
            )
        record["audit_record"] = audit_record.strip()
    elif isinstance(audit_record, str) and audit_record.strip():
        record["audit_record"] = audit_record.strip()
    for key in ("session_record", "checked_channels", "deviation"):
        value = validity.get(key)
        if value is not None:
            record[key] = value
    session_record = record.get("session_record")
    if isinstance(session_record, str) and session_record.strip():
        path = Path(session_record.strip())
        if path.is_file():
            record["session_record_sha256"] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return record


def _tree_files(candidate_root: Path) -> dict[str, str]:
    """Hash every file in the candidate tree except Git metadata."""

    files: dict[str, str] = {}
    for path in sorted(candidate_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(candidate_root).as_posix()
        if relative == ".git" or relative.startswith(".git/") or "/.git/" in f"/{relative}":
            # Trial directories are independent Git repositories; their
            # internal metadata is not candidate content.
            continue
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def scope_check(
    *,
    task: TaskDefinition,
    file_manifest: dict[str, str],
    candidate_root: Path,
) -> dict[str, object]:
    """Diff the candidate tree against the trusted coordinator manifest."""

    current = _tree_files(candidate_root)
    changed: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    for relative, digest in current.items():
        if relative in _COORDINATOR_FILES:
            continue
        if relative not in file_manifest:
            added.append(relative)
        elif file_manifest[relative] != digest:
            changed.append(relative)
    for relative in file_manifest:
        if relative not in current and relative not in _COORDINATOR_FILES:
            removed.append(relative)

    prefixes = [prefix.rstrip("/") for prefix in task.allowed_paths]

    def outside(paths: list[str]) -> list[str]:
        violations = []
        for relative in paths:
            if not any(
                relative == prefix or relative.startswith(prefix + "/")
                for prefix in prefixes
            ):
                violations.append(relative)
        return violations

    return {
        "allowed_paths": list(task.allowed_paths),
        "changed_files": changed,
        "added_files": added,
        "removed_files": removed,
        "scope_violations": outside(changed + added),
        "removed_paths_outside_scope": outside(removed),
    }


def _validate_trusted_manifest(
    *,
    manifest_path: Path,
    manifest: dict[str, object],
    task: TaskDefinition,
    group: str,
    run_kind: str,
    candidate_root: Path,
) -> tuple[str, str]:
    """Validate manifest provenance, identity, and baseline.

    A manifest that sits inside the candidate tree, claims another task or
    group, omits the candidate path it belongs to, carries a SHA that is not
    a baseline locked for this task, or hashes nothing is refused outright
    (operational BLOCKED, never a candidate verdict). Real trials must
    additionally name the task's locked pre-fix baseline, so a manifest
    cannot be replayed against a different revision of the same task.
    Returns ``(source_sha, manifest_sha256)``.
    """

    if manifest_path.resolve().is_relative_to(candidate_root.resolve()):
        raise GradeError(
            "trusted manifest must live outside the candidate tree "
            f"(got {manifest_path}); the candidate never decides its own baseline"
        )
    if manifest.get("record_type") != "trusted_trial_manifest":
        raise GradeError(
            f"manifest record_type must be 'trusted_trial_manifest', got {manifest.get('record_type')!r}"
        )
    if manifest.get("task_id") != task.task_id:
        raise GradeError(
            f"manifest task_id {manifest.get('task_id')!r} does not match grading task {task.task_id!r}"
        )
    if manifest.get("group") != group:
        raise GradeError(
            f"manifest group {manifest.get('group')!r} does not match grading group {group!r}"
        )
    recorded_trial_dir = manifest.get("trial_dir")
    if not isinstance(recorded_trial_dir, str) or not recorded_trial_dir.strip():
        raise GradeError(
            "manifest must record the prepared trial_dir; without it the manifest "
            "cannot be tied to the candidate being graded"
        )
    if Path(recorded_trial_dir).resolve() != candidate_root.resolve():
        raise GradeError(
            "manifest trial_dir does not match the candidate root; the manifest "
            "belongs to a different preparation"
        )
    source_sha = manifest.get("source_sha")
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise GradeError(
            f"manifest source_sha must be a full 40-hex commit SHA, got {source_sha!r}"
        )
    if source_sha not in {task.pre_fix_sha, task.fix_sha}:
        raise GradeError(
            f"manifest source_sha {source_sha} is not a baseline locked for task "
            f"{task.task_id!r} (expected {task.pre_fix_sha} or {task.fix_sha})"
        )
    if run_kind == "trial" and source_sha != task.pre_fix_sha:
        raise GradeError(
            "trial manifests must record the task's locked pre-fix baseline "
            f"({task.pre_fix_sha}), got {source_sha}"
        )
    file_manifest = manifest.get("file_manifest")
    if (
        not isinstance(file_manifest, dict)
        or not file_manifest
        or not all(
            isinstance(key, str)
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in file_manifest.items()
        )
    ):
        raise GradeError(
            "manifest file_manifest must map paths to 64-hex SHA-256 digests and be non-empty"
        )
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return source_sha, manifest_digest


def grade_trial(
    *,
    task: TaskDefinition,
    candidate_root: Path,
    results_dir: Path,
    label: str,
    group: str,
    trial_dir: Path,
    run_kind: str,
    manifest_path: Path,
    budget: dict[str, object] | None = None,
    notes: dict[str, object] | None = None,
    validity: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run the frozen acceptor, derive the scope check, and persist a record.

    ``validity`` is the coordinator's trial-validity attestation
    (``{"status": ..., "basis": ..., "audit_record": ...}``). Omitting it
    records UNVERIFIED, which is never treated as a valid independent trial.
    """

    if run_kind not in {"freeze", "trial"}:
        raise GradeError("run_kind must be 'freeze' or 'trial'")
    if not candidate_root.is_dir():
        raise GradeError(f"candidate root is not a directory: {candidate_root}")
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise GradeError(f"trusted manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GradeError(f"trusted manifest unreadable: {exc}") from exc
    if not isinstance(manifest, dict):
        raise GradeError("trusted manifest must be a JSON object")
    trial_validity = _validate_validity(validity, run_kind=run_kind)
    source_sha, manifest_digest = _validate_trusted_manifest(
        manifest_path=manifest_path,
        manifest=manifest,
        task=task,
        group=group,
        run_kind=run_kind,
        candidate_root=candidate_root,
    )
    file_manifest: dict[str, str] = manifest["file_manifest"]  # type: ignore[assignment]

    # Isolation is re-verified here, not assumed from preparation: a trial
    # whose `.git` disappeared resolves Git discovery to the enclosing source
    # repository, so its sessions can read fixed upstream files while the
    # candidate tree still looks intact. Such a run is operational BLOCKED —
    # never candidate evidence.
    trial_isolated: bool | None = None
    trial_isolation_check: dict[str, object] | None = None
    if run_kind == "trial":
        isolation_problem = trial_isolation_problem(candidate_root)
        if isolation_problem is not None:
            raise GradeError(
                "trial candidate is not Git-isolated, so its evidence cannot be "
                f"trusted: {isolation_problem}"
            )
        trial_isolated = True
        trial_isolation_check = {
            "checked": True,
            "method": "candidate owns .git and git rev-parse --show-toplevel == candidate root",
            "passed": True,
            "scope": "pre-scoring Git root check only; not evidence of read isolation",
        }

    completed = subprocess.run(
        [sys.executable, "-B", str(_RUNNER), task.task_id, str(candidate_root)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise GradeError(
            f"acceptor produced no JSON (exit {completed.returncode}): {completed.stderr[-300:]}"
        )
    try:
        acceptor_report = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise GradeError(f"acceptor JSON unreadable: {exc}") from exc

    verdict = acceptor_report.get("verdict")
    if verdict not in {"ACCEPT", "REJECT", "BLOCKED"}:
        raise GradeError(f"acceptor returned unknown verdict: {verdict!r}")

    scope = scope_check(task=task, file_manifest=file_manifest, candidate_root=candidate_root)
    record = {
        "record_type": "graded_trial",
        "run_kind": run_kind,
        "task_id": task.task_id,
        "group": group,
        "label": label,
        "trial_dir": str(trial_dir),
        "candidate_root": str(candidate_root),
        "source_sha": source_sha,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_digest,
        "graded_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "acceptor": acceptor_report,
        "acceptor_exit_code": completed.returncode,
        "scope": scope,
        "trial_isolated": trial_isolated,
        "trial_isolation_check": trial_isolation_check,
        "trial_validity": trial_validity,
        "budget": dict(budget or {}),
        "notes": dict(notes or {}),
        "verdict": verdict,
        "scope_clean": not scope["scope_violations"] and not scope["removed_paths_outside_scope"],
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / f"{task.task_id}--{group}--{label}.json"
    results_path.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    record["results_path"] = str(results_path)
    return record
