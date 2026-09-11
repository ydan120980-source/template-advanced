"""Document-contract rule tests: retired-authority re-claims and workflow enumeration.

Positive, negative, migration-history, and legacy-fixture cases for the
extended ``planning.single_authority`` and ``release.documents`` rules.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.template_doctor.test_cli import materialize_ready_fixture, run_doctor


def finding_for(report: dict, rule_id: str) -> dict:
    return next(item for item in report["results"] if item["rule_id"] == rule_id)


def run_single_authority(root: Path) -> dict:
    completed = run_doctor(root)
    report = json.loads(completed.stdout)
    return finding_for(report, "planning.single_authority")


class RetiredAuthorityContractTests(unittest.TestCase):
    V2_MARKER = "docs/ai-workflow/TASK_ISSUE_CONTRACT.md"

    def make_v2_tree(self, root: Path) -> Path:
        """Materialize the portable fixture and mark it as a v2 repository."""

        materialize_ready_fixture(root)
        (root / "AGENTS.md").write_text(
            "The verified GitHub Task Issue is the active planning "
            "authority; planning journals stay subordinate.\n",
            encoding="utf-8",
        )
        marker = root / self.V2_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            "# Task Issue Contract\n\nThe GitHub Task Issue is the single "
            "long-lived planning authority.\n",
            encoding="utf-8",
        )
        return root

    def test_current_v2_documents_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.make_v2_tree(Path(temporary_directory) / "v2")
            finding = run_single_authority(root)

        self.assertEqual(finding["status"], "pass")

    def test_reintroduced_sole_authority_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.make_v2_tree(Path(temporary_directory) / "drift")
            architecture = root / "docs" / "architecture" / "README.md"
            architecture.write_text(
                "# Architecture\n\n"
                "- `docs/control/NEXT_CODEX_TASK.md`: sole sprint authority.\n",
                encoding="utf-8",
            )
            finding = run_single_authority(root)

        self.assertEqual(finding["status"], "fail")
        self.assertIn("docs/architecture/README.md", finding["evidence"])

    def test_readded_retired_file_with_authority_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.make_v2_tree(Path(temporary_directory) / "readded")
            # Re-adding the file does not legitimize a present-tense sole
            # authority claim inside a v2 repository.
            control = root / "docs" / "control"
            control.mkdir(parents=True, exist_ok=True)
            (control / "NEXT_CODEX_TASK.md").write_text(
                "Task ID: REINTRODUCED\n", encoding="utf-8"
            )
            architecture = root / "docs" / "architecture" / "README.md"
            architecture.write_text(
                "# Architecture\n\n"
                "- `docs/control/NEXT_CODEX_TASK.md` is the single sprint "
                "authority.\n",
                encoding="utf-8",
            )
            finding = run_single_authority(root)

        self.assertEqual(finding["status"], "fail")
        self.assertIn("docs/architecture/README.md", finding["evidence"])

    def test_migration_history_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self.make_v2_tree(Path(temporary_directory) / "history")
            migration = root / "docs" / "ai-workflow" / "V1_TO_V2_MIGRATION.md"
            migration.write_text(
                "# V1 to V2 Migration\n\n"
                "PR A retires the active local files `NEXT_CODEX_TASK.md`, "
                "`CURRENT_PROJECT_STATE.md`, `CHATGPT_HANDOFF.md`, and "
                "`SPRINT_LEDGER.md` from the final source tree; their history "
                "remains in Git.\n\n"
                "Historical note: `NEXT_CODEX_TASK.md` was the sole sprint "
                "authority before v2.\n",
                encoding="utf-8",
            )
            finding = run_single_authority(root)

        self.assertEqual(finding["status"], "pass", finding["evidence"])

    def test_legacy_layout_with_live_control_files_is_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = materialize_ready_fixture(Path(temporary_directory) / "legacy")
            # The ready fixture keeps docs/control/*.md present, declares
            # NEXT_CODEX_TASK.md the single authority in its AGENTS.md, and
            # carries no v2 marker: a legitimate legacy compatibility state.
            finding = run_single_authority(root)

        self.assertEqual(finding["status"], "pass", finding["evidence"])


class OnboardingWorkflowEnumerationTests(unittest.TestCase):
    WORKFLOWS = ("ci.yml", "release-candidate.yml", "release-artifacts.yml", "security.yml")

    def add_workflows(self, root: Path) -> None:
        workflow_root = root / ".github" / "workflows"
        workflow_root.mkdir(parents=True)
        for name in self.WORKFLOWS:
            (workflow_root / name).write_text(
                f"name: {name[:-4]}\non: [push]\njobs: {{}}\n",
                encoding="utf-8",
            )

    def release_documents_finding(self, root: Path) -> dict:
        completed = run_doctor(root)
        report = json.loads(completed.stdout)
        return finding_for(report, "release.documents")

    def test_readme_without_workflow_enumeration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = materialize_ready_fixture(Path(temporary_directory) / "underlisted")
            self.add_workflows(root)
            finding = self.release_documents_finding(root)

        self.assertEqual(finding["status"], "fail")
        for name in self.WORKFLOWS:
            self.assertIn(name, finding["evidence"])

    def test_readme_enumerating_all_workflows_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = materialize_ready_fixture(Path(temporary_directory) / "listed")
            self.add_workflows(root)
            readme = root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + "\nWorkflows: "
                + ", ".join(f"`{name}`" for name in self.WORKFLOWS)
                + "\n",
                encoding="utf-8",
            )
            finding = self.release_documents_finding(root)

        self.assertEqual(finding["status"], "pass", finding["evidence"])

    def test_no_workflows_directory_requires_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = materialize_ready_fixture(Path(temporary_directory) / "noworkflows")
            finding = self.release_documents_finding(root)

        self.assertEqual(finding["status"], "pass", finding["evidence"])


if __name__ == "__main__":
    unittest.main()
