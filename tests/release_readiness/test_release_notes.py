"""Static contracts for protected checks, tag validation, and release notes."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReleaseNotesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release_workflow = (
            REPO_ROOT / ".github" / "workflows" / "release-artifacts.yml"
        ).read_text(encoding="utf-8")
        cls.ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        cls.security_workflow = (
            REPO_ROOT / ".github" / "workflows" / "security.yml"
        ).read_text(encoding="utf-8")
        cls.changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.readiness = (
            REPO_ROOT / "docs" / "ai-workflow" / "GITHUB_RELEASE_READINESS.md"
        ).read_text(encoding="utf-8")
        cls.current_state = (
            REPO_ROOT / "docs" / "control" / "CURRENT_PROJECT_STATE.md"
        ).read_text(encoding="utf-8")
        cls.stop_evidence = json.loads(
            (
                REPO_ROOT
                / "docs"
                / "control"
                / "evidence"
                / "RELEASE-V1.1.0-PUBLISH_STOP.json"
            ).read_text(encoding="utf-8")
        )

    def test_tag_notes_do_not_claim_full_matrix(self) -> None:
        self.assertIn("Protected main/PR checks run on Ubuntu, Windows, and macOS", self.release_workflow)
        self.assertIn(
            "This tag-triggered workflow does not rerun that full cross-platform",
            self.release_workflow,
        )
        self.assertIn(
            "The tag-triggered release workflow does not rerun that full cross-platform",
            self.changelog,
        )
        self.assertNotIn(
            "CI matrix: Ubuntu, Windows, macOS x Python 3.11, 3.12, 3.13",
            self.release_workflow,
        )
        self.assertIn(
            "The tag-triggered release-artifacts workflow is a separate release-critical",
            self.readiness,
        )

    def test_release_permissions_are_job_scoped(self) -> None:
        self.assertIn("build-and-verify:", self.release_workflow)
        self.assertIn("publish:", self.release_workflow)
        self.assertIn("needs: build-and-verify", self.release_workflow)
        self.assertIn("actions: read", self.release_workflow)
        self.assertIn("contents: write", self.release_workflow)
        self.assertIn("security-events: write", self.security_workflow)
        self.assertIn("credential-scan:", self.security_workflow)
        self.assertEqual(self.security_workflow.count("security-events: write"), 1)

    def test_primary_ci_and_release_jobs_have_outer_timeouts(self) -> None:
        self.assertRegex(
            self.ci_workflow,
            r"validate:\s*\n(?:.*\n){0,3}\s+timeout-minutes: 20",
        )
        self.assertRegex(
            self.release_workflow,
            r"build-and-verify:\s*\n(?:.*\n){0,5}\s+timeout-minutes: 20",
        )
        self.assertRegex(
            self.release_workflow,
            r"publish:\s*\n(?:.*\n){0,7}\s+timeout-minutes: 10",
        )

    def test_stop_state_evidence_and_state_schema_are_redacted(self) -> None:
        self.assertEqual(self.stop_evidence["task_id"], "RELEASE-V1.1.0-PUBLISH")
        self.assertEqual(self.stop_evidence["status"], "blocked")
        self.assertEqual(self.stop_evidence["retry_used"], 2)
        self.assertEqual(self.stop_evidence["retry_limit"], 2)
        self.assertEqual(self.stop_evidence["final_gate"], "not_ready")
        evidence_text = json.dumps(self.stop_evidence)
        self.assertNotIn("C:\\Users\\", evidence_text)
        self.assertNotIn("session", evidence_text.lower())
        self.assertIn("State Based On Parent Commit:", self.current_state)
        self.assertIn("Last Confirmed Remote PR Head:", self.current_state)
        self.assertNotIn("Is state stale?:", self.current_state)
        self.assertNotIn("Current Git HEAD:", self.current_state)


if __name__ == "__main__":
    unittest.main()
