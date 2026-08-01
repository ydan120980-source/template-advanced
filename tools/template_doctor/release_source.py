"""Trusted Git-backed release source for deterministic archive builds.

The release builder must never read release files from a dirty working tree:
uncommitted edits would silently change published artifact bytes. This module
gates a release build against the Git index and HEAD, then reads every release
file from the Git object database so the archive corresponds exactly to one
commit.

Checks performed for a Git work tree:

- the repository root is a Git work tree with a resolvable HEAD;
- every release file is tracked at HEAD (no untracked candidate);
- every release file is present in the work tree (no deleted candidate);
- every release file's working-tree bytes are byte-identical to its blob at
  HEAD (no uncommitted modification).

Modes come from the Git index (the current index entry for a file), and file
content is read through ``git cat-file --batch`` so working-tree bytes never
enter the artifact. The byte comparison is done by this module directly;
``git diff`` is intentionally not used because its text normalization treats
CRLF/LF variants as equal, which would let dirty release files slip through.
Only the Python standard library is used.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class ReleaseSourceError(RuntimeError):
    """A release source cannot be traced to a clean Git commit."""


@dataclass(frozen=True, slots=True)
class GitReleaseSource:
    """A clean, commit-traceable release source.

    ``contents`` holds the exact bytes of every release file at ``commit``.
    """

    commit: str
    file_modes: dict[str, int]
    contents: dict[str, bytes]


def _run_git(root: Path, *arguments: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _git_top_level(root: Path) -> str | None:
    try:
        completed = _run_git(root, "rev-parse", "--show-toplevel", timeout=10)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _is_regular_blob(mode: str) -> bool:
    return mode.startswith("100")


def _tracked_modes(root: Path, relative_paths: list[str]) -> dict[str, int]:
    if not relative_paths:
        return {}
    completed = _run_git(root, "ls-files", "--stage", "--", *relative_paths)
    modes: dict[str, int] = {}
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        meta = parts[0].split(" ")
        if len(meta) < 2:
            continue
        mode_text = meta[0]
        path = parts[1]
        if not _is_regular_blob(mode_text):
            continue
        try:
            mode = int(mode_text, 8)
        except ValueError:
            continue
        modes[path] = mode
    return modes


def _read_blobs_at_commit(
    root: Path, commit: str, relative_paths: list[str]
) -> dict[str, bytes]:
    """Read exact blob bytes for every path at ``commit``."""

    contents: dict[str, bytes] = {}
    try:
        process = subprocess.Popen(
            ["git", "-C", str(root), "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert process.stdin is not None and process.stdout is not None
            for path in relative_paths:
                spec = f"{commit}:{path}".encode("utf-8")
                process.stdin.write(spec + b"\n")
                process.stdin.flush()
                header = process.stdout.readline()
                if not header:
                    raise ReleaseSourceError(
                        f"git cat-file returned no entry for {path}"
                    )
                parts = header.decode("utf-8", errors="replace").split()
                if len(parts) == 2 and parts[1] == "missing":
                    raise ReleaseSourceError(
                        f"{path} is not present at {commit[:12]}; "
                        "commit the file before building"
                    )
                if len(parts) < 3:
                    raise ReleaseSourceError(
                        f"git cat-file header is malformed for {path}"
                    )
                try:
                    size = int(parts[2])
                except ValueError as exc:
                    raise ReleaseSourceError(
                        f"git cat-file size is malformed for {path}"
                    ) from exc
                data = process.stdout.read(size)
                newline = process.stdout.read(1)
                if newline != b"\n":
                    raise ReleaseSourceError(
                        f"git cat-file framing is malformed for {path}"
                    )
                contents[path] = data
        finally:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    except (OSError, ValueError) as exc:
        raise ReleaseSourceError(
            f"cannot read release files from Git: {type(exc).__name__}: {exc}"
        ) from exc

    missing = [path for path in relative_paths if path not in contents]
    if missing:
        raise ReleaseSourceError(
            "release files are not present at HEAD: " + ", ".join(sorted(missing))
        )
    return contents


def resolve_release_source(
    root: Path | str,
    relative_paths: list[str] | None = None,
) -> GitReleaseSource:
    """Resolve a clean Git-backed release source for ``root``.

    Raises :class:`ReleaseSourceError` naming the specific dirty files when any
    release file cannot be traced to HEAD. Returns the resolved HEAD commit,
    the index mode of every release file, and the exact HEAD bytes of every
    release file.
    """

    project_root = Path(root).resolve()
    top_level = _git_top_level(project_root)
    if top_level is None:
        raise ReleaseSourceError(
            f"{project_root} is not a Git work tree; a formal release build "
            "requires a clean Git commit. Use the release integration test "
            "only from a Git checkout, or explicitly accept an unverified "
            "local build."
        )
    if Path(top_level).resolve() != project_root:
        raise ReleaseSourceError(
            f"release root {project_root} is not the Git top-level work tree"
        )

    release_paths = [path for path in relative_paths if path] if relative_paths else []
    if not release_paths:
        from .release_inventory import select_release_paths

        release_paths = select_release_paths(project_root)

    tracked = _tracked_modes(project_root, release_paths)
    untracked = [
        path for path in release_paths if path not in tracked
    ]
    if untracked:
        raise ReleaseSourceError(
            "release files are not tracked at HEAD: " + ", ".join(sorted(untracked))
        )

    deleted = [
        path
        for path in release_paths
        if not (project_root / path).is_file()
    ]
    if deleted:
        raise ReleaseSourceError(
            "release files are missing from the working tree: "
            + ", ".join(sorted(deleted))
        )

    commit = _head_commit(project_root)
    contents = _read_blobs_at_commit(project_root, commit, release_paths)

    # Byte-for-byte worktree comparison: git diff's text normalization would
    # treat CRLF/LF variants as equal and let dirty release files slip through.
    modified = [
        path
        for path in release_paths
        if (project_root / path).read_bytes() != contents[path]
    ]
    if modified:
        raise ReleaseSourceError(
            "release files differ from HEAD (uncommitted changes): "
            + ", ".join(sorted(modified))
        )

    return GitReleaseSource(commit=commit, file_modes=tracked, contents=contents)


def _head_commit(root: Path) -> str:
    completed = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if completed.returncode != 0:
        raise ReleaseSourceError(
            "Git could not resolve HEAD to a commit object; a formal release "
            "build requires a clean Git commit"
        )
    value = completed.stdout.strip()
    if not value:
        raise ReleaseSourceError("Git HEAD did not resolve to a commit object")
    return value
