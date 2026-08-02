"""Static contracts for protected checks, tag validation, and release notes."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReleaseNotesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release_workflow = (
            REPO_ROOT / ".github" / "workflows" / "release-artifacts.yml"
        ).read_text(encoding="utf-8")
        cls.security_workflow = (
            REPO_ROOT / ".github" / "workflows" / "security.yml"
        ).read_text(encoding="utf-8")
        cls.changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.readiness = (
            REPO_ROOT / "docs" / "ai-workflow" / "GITHUB_RELEASE_READINESS.md"
        ).read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
