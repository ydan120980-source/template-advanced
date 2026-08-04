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
import os
from pathlib import Path

from tools.project_version import PROJECT_VERSION

RELEASE_VERSION = PROJECT_VERSION
RELEASE_ROOT_NAME = "template-advanced"

# Explicit top-level allowlist. Anything not named here is never a release
# candidate, including author-local runtime directories.
RELEASE_TOP_LEVEL = (
    ".agents",
    ".codex",
    ".github",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
    "docs",
    "evals",
    "scripts",
    "tests",
    "tools",
)

# Directory names that are never release candidates (VCS metadata, caches,
# virtual environments, build output, and local runtime evidence).
_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".cache",
        ".codegraph",
        ".git",
        ".aiwf",
        ".local-tools",
        ".mypy_cache",
        ".next",
        ".nox",
        ".nuxt",
        ".planning",
        ".pytest_cache",
        ".ruff_cache",
        ".secrets",
        ".tool-cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "logs",
        "node_modules",
        "out",
        "playwright-report",
        "screenshots",
        "temp",
        "test-results",
        "tmp",
        "venv",
        "videos",
    }
)

# Precise file allowlist for .codex. Only explicitly named project files are
# release candidates; runtime session state, caches, and future experiment
# files must never enter the archive.
_CODEX_ALLOWED_FILES = frozenset({"config.toml", "mcp.example.toml"})
_CODEX_ALLOWED_AGENT_FILES = frozenset({"architect.toml", "reviewer.toml", "state-compressor.toml", "tester.toml"})

# File names that are never release candidates.
_EXCLUDED_FILE_NAMES = frozenset(
    {
        ".active_plan",
        ".coverage",
        ".DS_Store",
        ".env",
        ".mode",
        ".nonce",
        ".stop_blocks",
        "Desktop.ini",
        "Thumbs.db",
    }
)

_EXCLUDED_SUFFIXES = (".class", ".jks", ".key", ".log", ".p12", ".pem", ".pfx", ".pid", ".pyc", ".pyo")
_SECRET_ENV_SUFFIX = ".env."
_EXCLUDED_UNDER_EVALS = frozenset({"artifacts", "results", "tmp"})
_EXCLUDED_UNDER_GITHUB_CODEX = frozenset({"logs", "tmp"})
_RETIRED_CONTROL_FILES = frozenset(
    {
        "docs/control/NEXT_CODEX_TASK.md",
        "docs/control/CURRENT_PROJECT_STATE.md",
        "docs/control/CHATGPT_HANDOFF.md",
        "docs/control/SPRINT_LEDGER.md",
    }
)

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
    """Return True when a project-relative path must not be released."""

    parts = relative.split("/")
    name = parts[-1]
    if name in _EXCLUDED_FILE_NAMES:
        return True
    if name == ".env.example":
        return False
    if name == ".env" or name.startswith(_SECRET_ENV_SUFFIX):
        return True
    if name.endswith(_EXCLUDED_SUFFIXES):
        return True
    if any(part in _EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return True
    if relative in _RETIRED_CONTROL_FILES or relative.startswith("docs/control/evidence/"):
        return True
    if parts[0] == "evals" and any(part in _EXCLUDED_UNDER_EVALS for part in parts[1:-1]):
        return True
    if parts[:2] == [".github", "codex"] and any(
        part in _EXCLUDED_UNDER_GITHUB_CODEX for part in parts[2:-1]
    ):
        return True
    if parts[0] == ".codex":
        # Precise file allowlist: .codex is not an open directory. Anything
        # that is not a named project file (config, example, agent defs) is a
        # runtime or experiment file and is never a release candidate.
        if len(parts) == 2:
            return name not in _CODEX_ALLOWED_FILES
        if len(parts) == 3 and parts[1] == "agents":
            return name not in _CODEX_ALLOWED_AGENT_FILES
        return True
    return False


def select_release_paths(root: Path | str) -> list[str]:
    """Return the sorted, deterministic release file paths for ``root``.

    Selection follows the canonical allowlist and exclusion rules without
    reading file contents. The Git-backed release builder uses this to
    determine the release inventory and then reads every selected path from
    the Git object database instead of the working tree.
    """

    project_root = Path(root).resolve()
    paths: list[str] = []
    for top_level in RELEASE_TOP_LEVEL:
        candidate = project_root / top_level
        if candidate.is_file():
            relative = candidate.relative_to(project_root).as_posix()
            if not _is_excluded(relative):
                paths.append(relative)
        elif candidate.is_dir():
            for directory, subdirectories, filenames in os.walk(
                candidate, followlinks=False
            ):
                subdirectories[:] = sorted(
                    name
                    for name in subdirectories
                    if name not in _EXCLUDED_DIR_NAMES
                )
                for filename in sorted(filenames):
                    relative = (
                        Path(directory) / filename
                    ).relative_to(project_root).as_posix()
                    if _is_excluded(relative):
                        continue
                    paths.append(relative)
    paths.sort()
    return paths


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
