"""Generate isolated trial directories from locked historical snapshots.

Isolation rules:

- The exported tree becomes its own Git repository whose only commit is the
  starting snapshot, so Git discovery cannot walk up into the surrounding
  repository and expose answer-recoverable history. ``prepare`` verifies
  ``git rev-parse --show-toplevel`` resolves to the trial directory itself.
- The trusted file manifest is written to a coordinator-controlled location
  outside the candidate tree; the candidate never stores its own baseline.
- Candidate-side metadata is minimal and never references the source
  repository path or the locked source SHA.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
from pathlib import Path

from . import CONTROL, EXPERIMENT
from .tasks import TaskDefinition, render_brief


class PrepareError(RuntimeError):
    """The locked snapshot could not be exported into a trial directory."""


def _git(source_repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(source_repo), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def resolve_commit(source_repo: Path, sha: str) -> str:
    completed = _git(source_repo, "rev-parse", "--verify", f"{sha}^{{commit}}")
    if completed.returncode != 0:
        raise PrepareError(f"cannot resolve locked snapshot {sha}: {completed.stderr.strip()}")
    return completed.stdout.strip()


_WINDOWS_LONG_PATH_PREFIX = "\\\\?\\"


def _export_target(destination: Path, relative_name: str) -> Path:
    """Map one archived entry name to its extraction target.

    Windows uses the extended-length prefix so names beyond the classic
    MAX_PATH limit survive extraction. That prefix is a Windows-only
    construct: applied under POSIX path semantics it produces a *relative*
    path such as ``\\\\?\\/tmp/trial\\tools\\example.py``, so every extracted
    file would land outside the destination instead of inside it. Non-Windows
    platforms therefore keep native ``Path`` joins with the archive's own
    forward slashes.
    """

    if os.name == "nt":
        native = relative_name.replace("/", "\\")
        return Path(_WINDOWS_LONG_PATH_PREFIX + str(destination.resolve()) + "\\" + native)
    return destination / relative_name


def _git_tree_paths(source_repo: Path, sha: str) -> list[str]:
    """Return every blob path recorded in one commit's tree.

    Only ``blob`` entries count: ``git archive`` does not materialise
    gitlinks (submodules) or trees, so treating them as expected files would
    report a complete export as incomplete.
    """

    completed = _git(source_repo, "ls-tree", "-r", "-z", sha)
    if completed.returncode != 0:
        raise PrepareError(f"git ls-tree failed for {sha}: {completed.stderr.strip()}")
    paths: list[str] = []
    for record in completed.stdout.split("\0"):
        if not record:
            continue
        metadata, _, name = record.partition("\t")
        fields = metadata.split()
        if len(fields) >= 2 and fields[1] == "blob" and name:
            paths.append(name)
    return paths


def _verify_export_complete(source_repo: Path, sha: str, destination: Path) -> None:
    """Fail when extraction did not materialise exactly the commit's file set.

    A silently truncated export would start a trial from an incomplete tree
    while still looking like a success, so this is a hard error rather than a
    warning.
    """

    expected = set(_git_tree_paths(source_repo, sha))
    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        detail: list[str] = []
        if missing:
            detail.append(f"{len(missing)} missing (e.g. {missing[:3]})")
        if unexpected:
            detail.append(f"{len(unexpected)} unexpected (e.g. {unexpected[:3]})")
        raise PrepareError(
            f"export of {sha} does not match the committed tree: {'; '.join(detail)}"
        )


def _export_tree(source_repo: Path, sha: str, destination: Path) -> None:
    """Export one commit's tree, including names beyond classic MAX_PATH.

    ``git archive --format=zip`` plus explicit extraction is used because
    plain tar extraction silently drops deeply nested fixture files on
    Windows, which later breaks trusted-source builds that verify every
    release file against the working tree. Extraction targets are
    platform-specific (see :func:`_export_target`), and the resulting file
    set is verified against the Git tree so a partial export cannot pass as
    a complete one.
    """

    import io
    import zipfile

    destination.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "-C", str(source_repo), "archive", "--format=zip", sha],
        check=False,
        capture_output=True,
        timeout=120,
    )
    if archive.returncode != 0:
        raise PrepareError(f"git archive failed: {archive.stderr.decode('utf-8', 'replace')[:300]}")
    with zipfile.ZipFile(io.BytesIO(archive.stdout)) as bundle:
        for info in bundle.infolist():
            relative_name = info.filename.strip("/")
            if not relative_name:
                continue
            target = _export_target(destination, relative_name)
            if info.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source_handle, open(str(target), "wb") as target_handle:
                while True:
                    chunk = source_handle.read(1 << 20)
                    if not chunk:
                        break
                    target_handle.write(chunk)
    _verify_export_complete(source_repo, sha, destination)


def export_commit_tree(source_repo: Path, sha: str, destination: Path) -> None:
    """Public export entry used by the coordinator and freeze validation."""

    _export_tree(source_repo, sha, destination)


def _file_manifest(root: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def trial_isolation_problem(trial_dir: Path) -> str | None:
    """Return why ``trial_dir`` is not a Git-isolated trial, else ``None``.

    A trial must own its Git metadata. If ``.git`` is missing, Git discovery
    walks up and silently resolves to whatever repository encloses the trial
    directory — typically the source repository, whose reachable history and
    already-fixed files are exactly the answers a trial must not see. A trial
    whose repository disappeared can therefore look intact while its
    ``git rev-parse HEAD`` / ``git show HEAD:<path>`` calls return upstream
    content, so every consumer re-checks isolation instead of trusting the
    preparation step.
    """

    if not (trial_dir / ".git").exists():
        return (
            "trial directory has no .git: Git discovery would walk up into an "
            "enclosing repository and expose answer-recoverable content"
        )
    completed = subprocess.run(
        ["git", "-C", str(trial_dir), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if completed.returncode != 0:
        return f"cannot resolve the trial repository toplevel: {completed.stderr.strip()}"
    # Git reports the *physical* toplevel: it resolves symlinked ancestors
    # (macOS ``/var`` -> ``/private/var``) and 8.3 short path components
    # (Windows ``RUNNER~1``). The trial directory as handed in may spell the
    # same location logically, so both sides go through ``realpath`` before
    # the case-folded comparison. ``abspath`` alone would reject perfectly
    # isolated trials on CI hosts whose temp roots use those spellings.
    resolved = os.path.normcase(os.path.realpath(completed.stdout.strip()))
    expected = os.path.normcase(os.path.realpath(str(trial_dir)))
    if resolved != expected:
        return (
            "trial directory is not Git-isolated: rev-parse --show-toplevel "
            f"resolved to {resolved!r} instead of {expected!r}"
        )
    return None


def _make_snapshot_repo(trial_dir: Path) -> None:
    """Turn the trial directory into its own single-commit Git repository.

    This blocks Git discovery from walking up to any surrounding repository
    and gives the trial a self-contained starting snapshot instead of
    answer-recoverable history.
    """

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(trial_dir), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    for arguments in (
        ("init", "--initial-branch=main"),
        # Deep fixture paths exceed the classic MAX_PATH limit on Windows;
        # longpaths is repo-local configuration and never touches the
        # user's global Git settings. Raw-byte storage keeps the builder's
        # byte comparison meaningful.
        ("config", "core.longpaths", "true"),
        ("config", "core.autocrlf", "false"),
        ("add", "-A", "--"),
    ):
        completed = git(*arguments)
        if completed.returncode != 0:
            raise PrepareError(f"snapshot repo setup failed ({arguments[0]}): {completed.stderr.strip()}")
    completed = git(
        "-c",
        "user.name=Workflow Eval Coordinator",
        "-c",
        "user.email=workflow-eval@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "trial starting snapshot (no answer history)",
    )
    if completed.returncode != 0:
        raise PrepareError(f"snapshot repo commit failed: {completed.stderr.strip()}")
    isolation_problem = trial_isolation_problem(trial_dir)
    if isolation_problem is not None:
        raise PrepareError(isolation_problem)


def prepare_trial(
    *,
    source_repo: Path,
    task: TaskDefinition,
    group: str,
    out_root: Path,
    run_label: str,
) -> dict[str, object]:
    """Export the locked pre-fix snapshot and write the group's task brief."""

    if group not in {CONTROL, EXPERIMENT}:
        raise PrepareError(f"group must be {CONTROL!r} or {EXPERIMENT!r}")
    sha = resolve_commit(source_repo, task.pre_fix_sha)
    trial_dir = out_root / "trials" / f"{task.task_id}--{group}"
    if trial_dir.exists():
        raise PrepareError(f"trial directory already exists: {trial_dir}")
    _export_tree(source_repo, sha, trial_dir)
    if (trial_dir / ".git").exists():
        raise PrepareError("exported trial tree unexpectedly contains .git metadata")
    (trial_dir / "instructions.md").write_text(render_brief(task, group=group), encoding="utf-8")
    file_manifest = _file_manifest(trial_dir)

    # Minimal candidate-side metadata: no source repository path, no locked
    # SHA, no baseline hashes. It is informational only and never trusted.
    (trial_dir / "trial-metadata.json").write_text(
        json.dumps(
            {
                "record_type": "prepared_trial",
                "task_id": task.task_id,
                "group": group,
                "prepared_at": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # The trusted baseline lives with the coordinator, outside the candidate.
    manifests_dir = out_root / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / f"{task.task_id}--{group}--{run_label}.json"
    manifest_record = {
        "record_type": "trusted_trial_manifest",
        "task_id": task.task_id,
        "group": group,
        "run_label": run_label,
        "trial_dir": str(trial_dir),
        "source_repo": str(source_repo),
        "source_sha": sha,
        "prepared_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "file_manifest": file_manifest,
        "file_count": len(file_manifest),
        "git_history_exported": False,
    }
    manifest_path.write_text(
        json.dumps(manifest_record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    _make_snapshot_repo(trial_dir)

    return {
        "record_type": "prepared_trial",
        "task_id": task.task_id,
        "group": group,
        "run_label": run_label,
        "trial_dir": str(trial_dir),
        "trusted_manifest_path": str(manifest_path),
        "source_sha": sha,
        "file_count": len(file_manifest),
        "git_isolated": True,
    }
