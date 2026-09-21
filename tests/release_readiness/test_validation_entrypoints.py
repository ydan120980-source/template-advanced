"""Regression tests for the default lint and unittest shell entry points."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(root: Path, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "invoke-git-bash.py"),
            str(root / "scripts" / script),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def _git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode:
        raise AssertionError(completed.stderr)


def _copy_script(root: Path, name: str) -> None:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / "scripts" / name, scripts / name)


class ValidationEntrypointTests(unittest.TestCase):
    def test_lint_uses_git_ignore_without_hiding_tracked_python(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aiwf-lint-git-") as temporary_directory:
            root = Path(temporary_directory)
            _copy_script(root, "lint.sh")
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.invalid")
            _git(root, "config", "user.name", "test")
            (root / ".gitignore").write_text(".venv/\ngenerated/\n", encoding="utf-8")
            source = root / "src" / "good.py"
            source.parent.mkdir(parents=True)
            source.write_text("value = 1\n", encoding="utf-8")
            ignored = root / ".venv" / "Lib" / "site-packages" / "ignored.py"
            ignored.parent.mkdir(parents=True)
            ignored.write_text("def broken(:\n", encoding="utf-8")
            tracked_ignored = root / "generated" / "tracked.py"
            tracked_ignored.parent.mkdir(parents=True)
            tracked_ignored.write_text("def broken(:\n", encoding="utf-8")
            _git(root, "add", ".gitignore", "src/good.py")
            _git(root, "add", "-f", "generated/tracked.py")

            completed = _run(root, "lint.sh")
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertIn("generated/tracked.py", completed.stderr)
            self.assertNotIn(".venv", completed.stdout + completed.stderr)

            tracked_ignored.write_text("value = 2\n", encoding="utf-8")
            completed = _run(root, "lint.sh")
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

            untracked_bad = root / "src" / "new_bad.py"
            untracked_bad.write_text("def broken(:\n", encoding="utf-8")
            completed = _run(root, "lint.sh")
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertIn("src/new_bad.py", completed.stderr)

    def test_lint_non_git_fallback_handles_unicode_spaces_and_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="验证 path ") as temporary_directory:
            root = Path(temporary_directory)
            _copy_script(root, "lint.sh")
            source = root / "源码 目录" / "模块 name.py"
            source.parent.mkdir(parents=True)
            source.write_text("message = 'ok'\n", encoding="utf-8")
            for relative in (".venv/bad.py", "build/bad.py", "node_modules/bad.py"):
                ignored = root / relative
                ignored.parent.mkdir(parents=True, exist_ok=True)
                ignored.write_text("def broken(:\n", encoding="utf-8")

            completed = _run(root, "lint.sh")
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("1 Python files", completed.stdout)

    def test_test_entrypoint_discovers_nested_tests_once(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aiwf-tests-") as temporary_directory:
            root = Path(temporary_directory)
            _copy_script(root, "test.sh")
            tests = root / "tests"
            nested = tests / "nested"
            nested.mkdir(parents=True)
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (nested / "__init__.py").write_text("", encoding="utf-8")
            (tests / "test_root.py").write_text(
                "import unittest\n"
                "class RootTest(unittest.TestCase):\n"
                "    def test_root(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            (nested / "test_nested.py").write_text(
                "import unittest\n"
                "class NestedTest(unittest.TestCase):\n"
                "    def test_nested(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )

            completed = _run(root, "test.sh")
            output = completed.stdout + completed.stderr
            self.assertEqual(completed.returncode, 0, output)
            self.assertIn("test: discovered 2 tests from tests/", output)
            self.assertEqual(output.count("test_root ("), 1, output)
            self.assertEqual(output.count("test_nested ("), 1, output)

    def test_test_entrypoint_preserves_empty_suite_failures(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aiwf-tests-empty-") as temporary_directory:
            root = Path(temporary_directory)
            _copy_script(root, "test.sh")
            (root / "tests").mkdir()

            no_modules = _run(root, "test.sh")
            self.assertNotEqual(no_modules.returncode, 0)
            self.assertIn("test: no unittest modules found.", no_modules.stderr)

            (root / "tests" / "test_empty.py").write_text(
                "import unittest\n",
                encoding="utf-8",
            )
            zero_tests = _run(root, "test.sh")
            self.assertNotEqual(zero_tests.returncode, 0)
            self.assertIn("test: unittest discovery produced zero tests.", zero_tests.stderr)


if __name__ == "__main__":
    unittest.main()
