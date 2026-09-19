"""Shared, auditable content selection for Doctor and release packaging.

The repository has two related but deliberately different consumers:

* Template Doctor inspects files that could become repository content.  In a
  Git checkout that means every tracked file plus every untracked,
  non-ignored file.  Git itself is the authority for ignore semantics, so
  project-specific build directories and negation rules work without a
  second hand-maintained ignore implementation.
* Release packaging applies the template's explicit release allowlist and
  exclusions.  A sensitive tracked file can therefore be visible to Doctor
  while still being excluded from an archive.

Both consumers share the same path-safety and template classification rules.
Git pathname protocols are always NUL-delimited and decoded with
``os.fsdecode`` so quoting, spaces, Unicode, and POSIX undecodable bytes are
not rewritten by a text-mode subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from typing import Iterable


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

EXCLUDED_DIR_NAMES = frozenset(
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

CODEX_ALLOWED_FILES = frozenset({"config.toml", "mcp.example.toml"})
CODEX_ALLOWED_AGENT_FILES = frozenset(
    {"architect.toml", "reviewer.toml", "state-compressor.toml", "tester.toml"}
)

EXCLUDED_FILE_NAMES = frozenset(
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
EXCLUDED_SUFFIXES = (
    ".class",
    ".jks",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pid",
    ".pyc",
    ".pyo",
)
SECRET_ENV_SUFFIX = ".env."
EXCLUDED_UNDER_EVALS = frozenset({"artifacts", "results", "tmp"})
EXCLUDED_UNDER_GITHUB_CODEX = frozenset({"logs", "tmp"})
RETIRED_CONTROL_FILES = frozenset(
    {
        "docs/control/NEXT_CODEX_TASK.md",
        "docs/control/CURRENT_PROJECT_STATE.md",
        "docs/control/CHATGPT_HANDOFF.md",
        "docs/control/SPRINT_LEDGER.md",
    }
)

_MANIFEST_SCHEMA = "template-advanced/release-manifest/v1"


class ContentSelectionError(RuntimeError):
    """Repository content could not be selected without losing trust."""


@dataclass(frozen=True, slots=True)
class ContentSelection:
    """One deterministic set of repository-relative content paths."""

    mode: str
    paths: tuple[str, ...]
    manifest: str | None = None


def _safe_relative(relative: str) -> str:
    """Validate and normalize one Git/release pathname without resolving it."""

    if not relative or "\x00" in relative:
        raise ContentSelectionError("content selection returned an empty or NUL pathname")
    normalized = relative.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ContentSelectionError(f"unsafe repository-relative pathname: {relative!r}")
    # A Windows drive prefix is not absolute according to PurePosixPath.
    if len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":":
        raise ContentSelectionError(f"drive-qualified repository pathname: {relative!r}")
    return pure.as_posix()


def decode_nul_paths(payload: bytes) -> list[str]:
    """Decode a Git ``-z`` pathname stream losslessly for the host filesystem."""

    if not payload:
        return []
    values = payload.split(b"\x00")
    if values[-1] == b"":
        values.pop()
    return [_safe_relative(os.fsdecode(item)) for item in values]


def is_template_release_candidate(relative: str) -> bool:
    """Return whether ``relative`` belongs to the template release payload."""

    relative = _safe_relative(relative)
    parts = relative.split("/")
    if parts[0] not in RELEASE_TOP_LEVEL:
        return False
    name = parts[-1]
    if name in EXCLUDED_FILE_NAMES:
        return False
    if name == ".env.example":
        return True
    if name == ".env" or name.startswith(SECRET_ENV_SUFFIX):
        return False
    if name.endswith(EXCLUDED_SUFFIXES):
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return False
    if relative in RETIRED_CONTROL_FILES or relative.startswith("docs/control/evidence/"):
        return False
    if parts[0] == "evals" and any(
        part in EXCLUDED_UNDER_EVALS for part in parts[1:-1]
    ):
        return False
    if parts[:2] == [".github", "codex"] and any(
        part in EXCLUDED_UNDER_GITHUB_CODEX for part in parts[2:-1]
    ):
        return False
    if parts[0] == ".codex":
        if len(parts) == 2:
            return name in CODEX_ALLOWED_FILES
        if len(parts) == 3 and parts[1] == "agents":
            return name in CODEX_ALLOWED_AGENT_FILES
        return False
    return True


def select_template_release_paths(root: Path | str) -> list[str]:
    """Return template release candidates without following directory links."""

    project_root = Path(root).resolve()
    selected: list[str] = []
    for top_level in RELEASE_TOP_LEVEL:
        candidate = project_root / top_level
        try:
            candidate_mode = candidate.lstat().st_mode
        except OSError:
            continue
        if stat.S_ISREG(candidate_mode):
            relative = candidate.relative_to(project_root).as_posix()
            if is_template_release_candidate(relative):
                selected.append(relative)
            continue
        if not stat.S_ISDIR(candidate_mode):
            # Top-level symlinks and special files are never traversed into a
            # release tree.  A Git-backed Doctor scan can still see a tracked
            # symlink as repository content without following its target.
            continue
        for directory, subdirectories, filenames in os.walk(
            candidate, followlinks=False
        ):
            base = Path(directory)
            kept_directories: list[str] = []
            for name in sorted(subdirectories):
                child = base / name
                try:
                    mode = child.lstat().st_mode
                except OSError:
                    continue
                if stat.S_ISDIR(mode) and name not in EXCLUDED_DIR_NAMES:
                    kept_directories.append(name)
            subdirectories[:] = kept_directories
            for filename in sorted(filenames):
                path = base / filename
                try:
                    mode = path.lstat().st_mode
                except OSError:
                    continue
                if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
                    continue
                relative = path.relative_to(project_root).as_posix()
                if is_template_release_candidate(relative):
                    selected.append(relative)
    return sorted(set(selected))


def _git_bytes(root: Path, *arguments: str, timeout: int = 30) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ContentSelectionError("Git executable is unavailable") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContentSelectionError(
            f"Git content selection failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        diagnostic = os.fsdecode(completed.stderr).strip()
        raise ContentSelectionError(
            f"Git content selection failed with exit {completed.returncode}"
            + (f": {diagnostic}" if diagnostic else "")
        )
    return completed.stdout


def _git_mode(root: Path) -> str:
    """Return ``top_level``, ``non_git``, or raise for an unsafe Git state."""

    git_marker = root / ".git"
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree", "--show-prefix"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except FileNotFoundError as exc:
        if git_marker.exists():
            raise ContentSelectionError("Git metadata exists but Git executable is unavailable") from exc
        return "non_git"
    except (OSError, subprocess.TimeoutExpired) as exc:
        if git_marker.exists():
            raise ContentSelectionError(
                f"Git metadata exists but repository probing failed: {type(exc).__name__}"
            ) from exc
        return "non_git"
    if completed.returncode != 0:
        if git_marker.exists():
            diagnostic = os.fsdecode(completed.stderr).strip()
            raise ContentSelectionError(
                "Git metadata exists but repository probing failed"
                + (f": {diagnostic}" if diagnostic else "")
            )
        return "non_git"
    lines = completed.stdout.splitlines()
    if not lines or lines[0].strip() != b"true":
        raise ContentSelectionError("Git did not confirm a working tree")
    # --show-prefix is the second line; an empty prefix means the supplied root
    # is the repository root.  Do not decode a possibly non-ASCII prefix just
    # to decide whether it is empty.
    prefix = lines[1] if len(lines) > 1 else b""
    if prefix.strip():
        raise ContentSelectionError("Doctor root must be the Git work-tree root")
    return "top_level"


def _git_head_paths(root: Path) -> tuple[str, ...]:
    payload = _git_bytes(root, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--")
    return tuple(sorted(set(decode_nul_paths(payload))))


def _git_index_paths(root: Path) -> tuple[str, ...]:
    payload = _git_bytes(root, "ls-files", "-z", "--cached", "--")
    return tuple(sorted(set(decode_nul_paths(payload))))


def _git_untracked_nonignored_paths(root: Path) -> tuple[str, ...]:
    payload = _git_bytes(
        root,
        "ls-files",
        "-z",
        "--others",
        "--exclude-standard",
        "--",
    )
    return tuple(sorted(set(decode_nul_paths(payload))))


def git_repository_candidate_paths(root: Path | str) -> tuple[str, ...]:
    """Return ``HEAD ∪ index ∪ untracked-nonignored`` repository paths."""

    project_root = Path(root).resolve()
    if _git_mode(project_root) != "top_level":
        raise ContentSelectionError("Git candidate selection requires a Git work-tree root")
    return tuple(
        sorted(
            set(_git_head_paths(project_root))
            | set(_git_index_paths(project_root))
            | set(_git_untracked_nonignored_paths(project_root))
        )
    )


def select_release_content_paths(root: Path | str) -> list[str]:
    """Select release candidates with Git ignore semantics when Git is present."""

    project_root = Path(root).resolve()
    mode = _git_mode(project_root)
    if mode == "top_level":
        return [
            path
            for path in git_repository_candidate_paths(project_root)
            if is_template_release_candidate(path)
        ]
    return select_template_release_paths(project_root)


def _manifest_candidates(root: Path) -> list[Path]:
    candidates = sorted(root.glob("*.manifest.json"))
    dist = root / "dist"
    if dist.is_dir():
        candidates.extend(sorted(dist.glob("*.manifest.json")))
    return sorted(set(candidates))


def _manifest_digest(entries: Iterable[tuple[str, int, int, str]]) -> str:
    canonical = "\n".join(
        f"{path}|{mode:o}|{size}|{sha256}"
        for path, mode, size, sha256 in sorted(entries, key=lambda item: item[0])
    )
    return "template-advanced-publication/v1:sha256:" + hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _verified_manifest_paths(root: Path, manifest_path: Path) -> tuple[str, ...]:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentSelectionError(
            f"release manifest {manifest_path.name} is unreadable: {type(exc).__name__}"
        ) from exc
    if not isinstance(raw, dict) or raw.get("schema") != _MANIFEST_SCHEMA:
        raise ContentSelectionError(f"release manifest {manifest_path.name} has an invalid schema")
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        raise ContentSelectionError(f"release manifest {manifest_path.name} has no files")
    entries: list[tuple[str, int, int, str]] = []
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ContentSelectionError(f"release manifest {manifest_path.name} has an invalid file entry")
        try:
            relative = _safe_relative(item["path"])
            size = item["size"]
            digest = item["sha256"]
            mode = int(item["mode"], 8)
        except (KeyError, TypeError, ValueError) as exc:
            raise ContentSelectionError(
                f"release manifest {manifest_path.name} has an invalid file entry"
            ) from exc
        if (
            relative in seen
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise ContentSelectionError(f"release manifest {manifest_path.name} has an invalid file entry")
        path = root / relative
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise ContentSelectionError(
                f"release manifest {manifest_path.name} references a missing file: {relative}"
            ) from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise ContentSelectionError(
                f"release manifest {manifest_path.name} references a non-regular file: {relative}"
            )
        data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest.lower():
            raise ContentSelectionError(
                f"release manifest {manifest_path.name} does not match file bytes: {relative}"
            )
        seen.add(relative)
        entries.append((relative, mode, size, digest.lower()))
    if raw.get("publication_digest") != _manifest_digest(entries):
        raise ContentSelectionError(
            f"release manifest {manifest_path.name} publication digest is invalid"
        )
    return tuple(sorted(seen))


def select_doctor_content(root: Path | str) -> ContentSelection:
    """Select Doctor hygiene candidates and state exactly which mode was used."""

    project_root = Path(root).resolve()
    mode = _git_mode(project_root)
    if mode == "top_level":
        return ContentSelection(
            mode="git",
            paths=git_repository_candidate_paths(project_root),
        )

    manifests = _manifest_candidates(project_root)
    if len(manifests) > 1:
        raise ContentSelectionError(
            "multiple release manifests are present; content authority is ambiguous"
        )
    if manifests:
        manifest = manifests[0]
        return ContentSelection(
            mode="manifest",
            paths=_verified_manifest_paths(project_root, manifest),
            manifest=manifest.relative_to(project_root).as_posix(),
        )
    return ContentSelection(
        mode="template_fallback",
        paths=tuple(select_template_release_paths(project_root)),
    )
