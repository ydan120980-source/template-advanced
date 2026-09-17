"""Canonical, deterministic release inventory for template-advanced.

This module is the single source of truth for which repository files belong in
a release archive. Template Doctor rules, the release builder, and the archive
verifier all use it so a manifest can never disagree with the selection rules
by construction.

Selection policy:

- an explicit top-level allowlist names every release candidate;
- local-state, VCS, cache, secret, and generated output paths are excluded with
  auditable rules that mirror ``.gitignore``;
- entries are sorted by relative path and carry size, SHA-256, and the intended
  POSIX mode (``0755`` for shell scripts, ``0644`` otherwise) so the manifest
  can detect lost executable bits.

Only the Python standard library is used.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from tools.project_version import PROJECT_VERSION
from .content_selection import (
    RELEASE_TOP_LEVEL,
    is_template_release_candidate,
    select_release_content_paths,
)

RELEASE_VERSION = PROJECT_VERSION
RELEASE_ROOT_NAME = "template-advanced"

# Text suffixes scanned for privacy and local-path hygiene by the verifier.
TEXT_FILE_SUFFIXES = frozenset(
    {
        ".gitattributes",
        ".gitignore",
        ".json",
        ".jsonl",
        ".md",
        ".ps1",
        ".py",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)


@dataclass(frozen=True, slots=True)
class ReleaseEntry:
    """One deterministic release file record."""

    path: str
    size: int
    sha256: str
    mode: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "mode": f"{self.mode:o}",
        }

    @classmethod
    def from_dict(cls, raw: object) -> "ReleaseEntry":
        if not isinstance(raw, dict):
            raise ValueError("release manifest file entries must be objects")
        path = raw.get("path")
        size = raw.get("size")
        sha256 = raw.get("sha256")
        mode = raw.get("mode")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or not isinstance(mode, str)
        ):
            raise ValueError("release manifest entry is invalid")
        return cls(path=path, size=size, sha256=sha256.lower(), mode=int(mode, 8))


def _is_excluded(relative: str) -> bool:
    """Compatibility wrapper around the shared release classification."""

    return not is_template_release_candidate(relative)


def select_release_paths(root: Path | str) -> list[str]:
    """Return the sorted, deterministic release file paths for ``root``.

    Selection follows the canonical allowlist and exclusion rules without
    reading file contents. The Git-backed release builder uses this to
    determine the release inventory and then reads every selected path from
    the Git object database instead of the working tree.
    """

    return select_release_content_paths(root)


def iter_release_entries(root: Path | str) -> list[ReleaseEntry]:
    """Return the sorted, deterministic release inventory for ``root``."""

    project_root = Path(root).resolve()
    entries: list[ReleaseEntry] = []
    for relative in select_release_paths(project_root):
        path = project_root / relative
        _append_file_entry(entries, path, project_root)
    entries.sort(key=lambda entry: entry.path)
    return entries


def _append_file_entry(
    entries: list[ReleaseEntry], path: Path, project_root: Path
) -> None:
    relative = path.relative_to(project_root).as_posix()
    if _is_excluded(relative):
        return
    data = path.read_bytes()
    mode = 0o100755 if path.name.endswith(".sh") else 0o100644
    entries.append(
        ReleaseEntry(
            path=relative,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            mode=mode,
        )
    )


def publication_digest(entries: list[ReleaseEntry]) -> str:
    """Return the deterministic publication digest for an entry list."""

    canonical = "\n".join(
        f"{entry.path}|{entry.mode:o}|{entry.size}|{entry.sha256}"
        for entry in sorted(entries, key=lambda item: item.path)
    )
    return f"template-advanced-publication/v1:sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
