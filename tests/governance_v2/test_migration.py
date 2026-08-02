"""Migration matrix tests using a temporary local Git repository."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.governance_v2.migration import build_matrices, verify_matrices


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class MigrationTests(unittest.TestCase):
    def test_build_and_verify_are_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            git(root, "init", "-q")
            env = os.environ.copy()
            env.update({"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"})
            (root / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, env=env, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, env=env, check=True)
            base = git(root, "rev-parse", "HEAD")
            git(root, "branch", "-M", "main")
            (root / "README.md").write_text("base\nfirst\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, env=env, check=True)
            subprocess.run(["git", "commit", "-qm", "first"], cwd=root, env=env, check=True)
            (root / "tools.txt").write_text("second\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, env=env, check=True)
            subprocess.run(["git", "commit", "-qm", "second"], cwd=root, env=env, check=True)
            head = git(root, "rev-parse", "HEAD")
            output = root / "matrices"
            result = build_matrices(root=root, base_ref=base, head_ref=head, output_dir=output)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["commit_count"], 2)
            self.assertEqual(result["file_count"], 2)
            verified = verify_matrices(input_dir=output)
            self.assertEqual(verified["status"], "PASS")
            files = json.loads((output / "migration-files.json").read_text(encoding="utf-8"))
            self.assertTrue(all(item["classification"] in {"PORT", "REIMPLEMENT", "SPLIT", "DROP"} for item in files["files"]))
            self.assertNotIn("UNKNOWN", (output / "migration-files.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
