"""JSON CLI and read-only bootstrap tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "governance_v2" / "fixtures" / "bootstrap-contract.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", "tools.governance_v2", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_issue_verify_returns_pass_json(self) -> None:
        result = run_cli("issue", "verify", "--contract", str(FIXTURE))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["contract_digest"], "210bc61087f463a0aca5f9092da39162b5e74008b94c92692ac1aec77ac8b9eb")

    def test_issue_append_is_not_an_implicit_write_path(self) -> None:
        result = run_cli("issue", "append")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "BLOCKED")

    def test_sync_body_and_snapshot_are_read_only(self) -> None:
        body = "```json\n" + FIXTURE.read_text(encoding="utf-8") + "\n```\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            body_path = temp / "issue.md"
            cache_path = temp / "cache.json"
            body_path.write_text(body, encoding="utf-8")
            synced = run_cli("issue", "sync", "--body-file", str(body_path), "--output", str(cache_path))
            self.assertEqual(synced.returncode, 0, synced.stderr)
            self.assertEqual(json.loads(synced.stdout)["status"], "PASS")
            self.assertTrue(cache_path.exists())

            snapshot_path = temp / "snapshot.json"
            snapshot = run_cli("bootstrap", "snapshot", "--root", str(ROOT), "--output", str(snapshot_path))
            self.assertEqual(snapshot.returncode, 3, snapshot.stderr)
            self.assertEqual(json.loads(snapshot.stdout)["status"], "CACHED")
            self.assertTrue(snapshot_path.exists())

            plan = run_cli("bootstrap", "plan", "--snapshot", str(snapshot_path))
            self.assertEqual(plan.returncode, 3, plan.stderr)
            self.assertFalse(json.loads(plan.stdout)["remote_writes"])


if __name__ == "__main__":
    unittest.main()
