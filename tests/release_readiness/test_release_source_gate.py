"""Regression tests: the release build must refuse dirty sources.

Every scenario builds a small disposable Git repository and runs the real
``scripts/build-release.py`` against it, so the tests exercise the trusted
source gate end to end (scenario set P0-1 through P0-7 of the release fix
contract). Scenarios use the same re-usable fixture tree: a committed
``.codex/config.toml`` plus an excluded scratch file, which keeps the surface
small while still traversing the real release inventory selection.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.template_doctor.release_source import resolve_release_source


# Name of a scratch file that is deliberately NOT a release candidate. It can
# be present and uncommitted without ever blocking a trusted build.
EXCLUDED_SCRATCH = "scratch.tmp"


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=60,
    )


def _make_fixture_root(destination: Path) -> Path:
    """Create a minimal release fixture: committed config + excluded scratch."""

    destination.mkdir(parents=True, exist_ok=True)
    config = destination / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_bytes(
        b'approval_policy = "on-request"\n'
        b'sandbox_mode = "workspace-write"\n'
        b'[sandbox_workspace_write]\n'
        b'network_access = false\n'
    )
    (destination / EXCLUDED_SCRATCH).write_bytes(b"scratch\n")
    return destination


def _commit_all(root: Path) -> None:
    for command in (
        ("init", "--initial-branch=main"),
        ("add", "--", "."),
        (
            "-c",
            "user.name=Release Source Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "fixture baseline",
        ),
    ):
        completed = _git(root, *command)
        if completed.returncode != 0:
            raise AssertionError(completed.stderr or completed.stdout)


def _run_builder(
    root: Path, out_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run the real builder against ``root`` with PYTHONDONTWRITEBYTECODE."""

    return subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/build-release.py",
            "--root",
            str(root),
            "--out-dir",
            str(out_dir),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=120,
    )


def _zip_entry(archive_path: Path, entry_path: str) -> bytes:
    import zipfile

    with zipfile.ZipFile(archive_path, mode="r") as archive:
        return archive.read(entry_path)


class ReleaseSourceGateTests(unittest.TestCase):
    maxDiff = None

    def test_uncommitted_dirty_release_file_blocks_build(self) -> None:
        """P0-1: a dirty tracked release file must block the build."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "repo")
            _commit_all(root)
            (root / ".codex" / "config.toml").write_bytes(
                b'approval_policy = "never"\n'
            )
            completed = _run_builder(root, Path(temporary_directory) / "out")

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn(".codex/config.toml", completed.stderr)

    def test_untracked_allowlisted_release_file_blocks_build(self) -> None:
        """P0-2: a new allowlisted file that is not committed must block."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "repo")
            _commit_all(root)
            untracked = root / ".codex" / "mcp.example.toml"
            untracked.write_bytes(b"[mcp_servers]\n")
            completed = _run_builder(root, Path(temporary_directory) / "out")

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn(".codex/mcp.example.toml", completed.stderr)

    def test_unrelated_excluded_file_does_not_block_build(self) -> None:
        """P0-3: an uncommitted file outside the release set must not block."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "repo")
            _commit_all(root)
            (root / EXCLUDED_SCRATCH).write_bytes(b"changed but excluded\n")
            completed = _run_builder(root, Path(temporary_directory) / "out")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest_path = next((Path(temporary_directory) / "out").glob("*.manifest.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"]["type"], "git-commit")
            paths = {entry["path"] for entry in manifest["files"]}
            self.assertNotIn(EXCLUDED_SCRATCH, paths)

    def test_safe_committed_config_enters_archive(self) -> None:
        """P0-4: a committed safe config must be released from HEAD bytes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "repo")
            _commit_all(root)
            completed = _run_builder(root, Path(temporary_directory) / "out")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            out_dir = Path(temporary_directory) / "out"
            manifest_path = next(out_dir.glob("*.manifest.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            archive = next(out_dir.glob("*.zip"))
            payload = _zip_entry(archive, ".codex/config.toml")
            self.assertIn(b'approval_policy = "on-request"', payload)
            self.assertNotIn(b'"never"', payload)
            self.assertEqual(manifest["source"]["type"], "git-commit")
            self.assertIn("commit", manifest["source"])

    def test_worktree_approval_policy_never_blocks_build(self) -> None:
        """P0-5: worktree bytes must never enter the archive, even to block."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "repo")
            _commit_all(root)
            (root / ".codex" / "config.toml").write_bytes(
                b'approval_policy = "never"\n'
            )
            completed = _run_builder(root, Path(temporary_directory) / "out")

            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                [".codex", ".git", EXCLUDED_SCRATCH],
                "blocked build must not create any artifact",
            )

    def test_archive_bytes_equal_head_blob_not_worktree(self) -> None:
        """P0-6: the archive must contain HEAD bytes, never worktree bytes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "repo")
            _commit_all(root)
            source = resolve_release_source(root)
            head_config = source.contents[".codex/config.toml"]
            self.assertIn(b'approval_policy = "on-request"', head_config)
            (root / ".codex" / "config.toml").write_bytes(
                b'approval_policy = "never"\n'
            )
            completed = _run_builder(root, Path(temporary_directory) / "out")

            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn(".codex/config.toml", completed.stderr)

    def test_clean_double_build_is_byte_identical(self) -> None:
        """P0-7: two clean builds from one commit must be byte-identical."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "repo")
            _commit_all(root)
            first = Path(temporary_directory) / "first"
            second = Path(temporary_directory) / "second"
            first.mkdir()
            second.mkdir()
            for out_dir in (first, second):
                completed = _run_builder(root, out_dir)
                self.assertEqual(completed.returncode, 0, completed.stderr)

            stem = "template-advanced-1.0.0"
            self.assertEqual(
                (first / f"{stem}.zip").read_bytes(),
                (second / f"{stem}.zip").read_bytes(),
            )
            self.assertEqual(
                (first / f"{stem}.manifest.json").read_bytes(),
                (second / f"{stem}.manifest.json").read_bytes(),
            )
            self.assertEqual(
                (first / f"{stem}.digest.txt").read_bytes(),
                (second / f"{stem}.digest.txt").read_bytes(),
            )

    def test_non_git_tree_refuses_without_allow_unverified(self) -> None:
        """P0-8: a non-Git tree must refuse formal builds and label fallback."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = _make_fixture_root(Path(temporary_directory) / "plain")
            refused = _run_builder(root, Path(temporary_directory) / "out")

        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("Git work tree", refused.stderr)


if __name__ == "__main__":
    unittest.main()
