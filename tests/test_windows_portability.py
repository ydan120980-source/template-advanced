from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.template_doctor.content_selection import git_repository_candidate_paths

ROOT = Path(__file__).resolve().parents[1]

def _git(root: Path, *args: str) -> str:
    cp = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if cp.returncode:
        raise AssertionError(cp.stderr)
    return cp.stdout.strip()

def _load_launcher():
    path = ROOT / "scripts" / "invoke-git-bash.py"
    spec = importlib.util.spec_from_file_location("invoke_git_bash", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_ci_doctor_gate():
    path = ROOT / "scripts" / "ci-doctor-gate.py"
    spec = importlib.util.spec_from_file_location("ci_doctor_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class WindowsPortabilityTests(unittest.TestCase):
    def test_git_candidate_paths_round_trip_unicode_spaces_and_ignore(self) -> None:
        cn_dir = "\u4e2d\u6587 \u76ee\u5f55"
        cn_file = "\u6587\u4ef6 name.txt"
        ignored_dir = "\u5ffd\u7565 \u8f93\u51fa"
        new_file = "\u65b0\u589e \u6587\u4ef6.txt"
        with tempfile.TemporaryDirectory(prefix="aiwf-space-") as td:
            root = Path(td)
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.invalid")
            _git(root, "config", "user.name", "test")
            (root / ".gitignore").write_text(ignored_dir + "/\n", encoding="utf-8")
            tracked = root / cn_dir / cn_file
            tracked.parent.mkdir(parents=True)
            tracked.write_text("tracked\n", encoding="utf-8")
            ignored = root / ignored_dir / "cache.bin"
            ignored.parent.mkdir(parents=True)
            ignored.write_bytes(b"ignored")
            untracked = root / new_file
            untracked.write_text("new\n", encoding="utf-8")
            _git(root, "add", ".gitignore", tracked.relative_to(root).as_posix())
            _git(root, "commit", "-m", "seed")
            selected = set(git_repository_candidate_paths(root))
        self.assertIn(f"{cn_dir}/{cn_file}", selected)
        self.assertIn(new_file, selected)
        self.assertNotIn(f"{ignored_dir}/cache.bin", selected)

    @unittest.skipUnless(os.name == "nt", "Windows-only launcher semantics")
    def test_python_git_bash_launcher_rejects_system32(self) -> None:
        module = _load_launcher()
        env = {"WINDIR": r"C:\\Windows", "LOCALAPPDATA": r"C:\\Users\\u\\AppData\\Local"}
        self.assertTrue(module._blocked(Path(r"C:\\Windows\\System32\\bash.exe"), env))
        self.assertTrue(module._blocked(Path(r"C:\\Users\\u\\AppData\\Local\\Microsoft\\WindowsApps\\bash.exe"), env))
        self.assertFalse(module._blocked(Path(r"C:\\Program Files\\Git\\bin\\bash.exe"), env))

    def test_controlled_python_child_overrides_cp936_parent_with_utf8_protocol(self) -> None:
        module = _load_ci_doctor_gate()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"results": [], "summary": {"errors": 0, "total": 0}}',
            stderr="",
        )
        with patch.dict(
            os.environ,
            {"PYTHONIOENCODING": "cp936", "PYTHONUTF8": "0"},
            clear=False,
        ), patch.object(module.subprocess, "run", return_value=completed) as run:
            result = module.main(["--root", str(ROOT), "--python", sys.executable])
        self.assertEqual(result, 0)
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(child_env["PYTHONUTF8"], "1")
        self.assertEqual(child_env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")

if __name__ == "__main__":
    unittest.main()
