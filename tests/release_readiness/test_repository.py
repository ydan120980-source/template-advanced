"""Repository-level release-candidate invariants for template-advanced."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.template_doctor.engine import run_checks


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReleaseReadinessTests(unittest.TestCase):
    maxDiff = None

    def test_release_content_doctor_rules_pass(self) -> None:
        from tools.template_doctor.release_inventory import iter_release_entries

        # Validate against a clean temporary copy of the release file set so
        # this test never depends on the live workspace being free of caches
        # created by the test run itself.
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated = Path(temporary_directory) / "release-content"
            for entry in iter_release_entries(REPO_ROOT):
                target = isolated / entry.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REPO_ROOT / entry.path).read_bytes())
            report = run_checks(isolated)
        results = {result.rule_id: result for result in report.results}
        required_passes = {
            "architecture.documented",
            "config.unsupported_profiles",
            "control.current_state_freshness",
            "control.next_task_executable",
            "control.placeholders",
            "github.workflow_placeholders",
            "gitignore.effective",
            "planning.single_authority",
            "release.documents",
            "repository.generated_artifacts",
            "repository.large_files",
            "repository.sensitive_filenames",
            "validation.placeholder_scripts",
        }
        self.assertTrue(required_passes.issubset(results), sorted(results))
        failures = {
            rule_id: results[rule_id].to_dict()
            for rule_id in sorted(required_passes)
            if results[rule_id].status != "pass"
            and not (
                rule_id
                in {
                    "control.current_state_freshness",
                    "control.next_task_executable",
                }
                and results[rule_id].status == "skip"
            )
        }
        self.assertEqual(failures, {})

    def test_validation_entrypoints_are_real_and_fail_fast(self) -> None:
        paths = (
            "scripts/setup.sh",
            "scripts/lint.sh",
            "scripts/structural-check.sh",
            "scripts/test.sh",
            "scripts/verify.sh",
            "evals/run-evals.sh",
        )
        for relative in paths:
            with self.subTest(path=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("#!/usr/bin/env bash\n"))
                self.assertIn("set -euo pipefail", text)
                self.assertNotIn("ALLOW_PLACEHOLDER_VERIFY", text)
                self.assertNotIn("TODO: Configure", text)

    def test_host_local_planning_and_python_state_is_ignored(self) -> None:
        lines = {
            line.strip()
            for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        required = {
            ".aiwf/",
            ".planning/",
            "/.mode",
            "/.nonce",
            "/.stop_blocks",
            "__pycache__/",
            "*.py[cod]",
        }
        self.assertEqual(required - lines, set())

    def test_workflows_are_real_and_placeholder_free(self) -> None:
        workflow_root = REPO_ROOT / ".github" / "workflows"
        workflows = (
            sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
            if workflow_root.is_dir()
            else []
        )
        self.assertGreaterEqual(len(workflows), 3)
        for workflow in workflows:
            text = workflow.read_text(encoding="utf-8")
            self.assertNotIn("TODO", text)
            self.assertNotIn("placeholder", text.lower())

        prompt_readme = (
            REPO_ROOT / ".github" / "codex" / "prompts" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("inert reference prompts", prompt_readme)

    def test_v2_governance_documents_replace_active_control_state(self) -> None:
        required = (
            "TASK_ISSUE_CONTRACT.md",
            "ISSUE_EVENT_CHAIN.md",
            "OFFLINE_CACHE.md",
            "REMOTE_GATES.md",
            "GITHUB_RELEASE_READINESS.md",
            "V1_TO_V2_MIGRATION.md",
        )
        for name in required:
            with self.subTest(name=name):
                text = (REPO_ROOT / "docs" / "ai-workflow" / name).read_text(encoding="utf-8")
                self.assertRegex(text, r"[A-Za-z0-9]")
                self.assertNotRegex(text, r"[A-Za-z]:\\")
                self.assertNotIn("C:\\Users", text)
        for relative in (
            "docs/control/NEXT_CODEX_TASK.md",
            "docs/control/CURRENT_PROJECT_STATE.md",
            "docs/control/CHATGPT_HANDOFF.md",
            "docs/control/SPRINT_LEDGER.md",
        ):
            self.assertFalse((REPO_ROOT / relative).exists(), relative)

    def test_apache_license_is_complete_and_documented(self) -> None:
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.lstrip().startswith("Apache License"))
        self.assertIn("Version 2.0, January 2004", license_text)
        self.assertIn("END OF TERMS AND CONDITIONS", license_text)
        notice = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("template-advanced", notice)
        self.assertIn("Apache License, Version 2.0", notice)
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        release = (
            REPO_ROOT
            / "docs"
            / "ai-workflow"
            / "GITHUB_RELEASE_READINESS.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Licensed under the Apache License, Version 2.0", readme)
        self.assertIn("Apache License 2.0", release)

    def test_ci_doctor_gate_accepts_expected_findings(self) -> None:
        from tools.template_doctor.release_inventory import iter_release_entries

        import os
        import subprocess
        import sys
        import tempfile

        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated = Path(temporary_directory) / "checkout"
            for entry in iter_release_entries(REPO_ROOT):
                target = isolated / entry.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REPO_ROOT / entry.path).read_bytes())
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "scripts/ci-doctor-gate.py",
                    "--root",
                    str(isolated),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
