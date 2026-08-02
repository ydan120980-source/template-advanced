"""Workflow static and read-only Remote Gate tests."""

from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.governance_v2.remote import gate_github
from tools.governance_v2.workflow import static_check


SHA = "1" * 40
PINNED_CHECKOUT = "3d3c42e5aac5ba805825da76410c181273ba90b1"
PINNED_SETUP = "5fda3b95a4ea91299a34e894583c3862153e4b97"


def workflow(job: str, trigger: str, steps: str) -> str:
    indented_steps = textwrap.indent(steps, "        ")
    return (
        "name: test\n\n"
        "on:\n"
        f"  {trigger}:\n"
        "  workflow_dispatch:\n\n"
        "permissions:\n"
        "  contents: read\n\n"
        "jobs:\n"
        f"  {job}:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 20\n"
        "    steps:\n"
        f"      - uses: actions/checkout@{PINNED_CHECKOUT}\n"
        f"      - uses: actions/setup-python@{PINNED_SETUP}\n"
        f"{indented_steps}\n"
    )


class GateTests(unittest.TestCase):
    def test_static_check_passes_only_for_the_targeted_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "ci.yml").write_text(workflow("validate", "push", "- name: Unit tests\n  run: true"), encoding="utf-8")
            (workflow_dir / "security.yml").write_text(workflow("codeql", "push", "- name: Scan\n  run: true") + "\n  credential-scan:\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n", encoding="utf-8")
            (workflow_dir / "release-candidate.yml").write_text(
                workflow(
                    "release-candidate",
                    "pull_request",
                    "\n".join(
                        f"- name: {name}\n  run: true"
                        for name in (
                            "Unit tests",
                            "Verify",
                            "Evals",
                            "Workflow static check",
                            "Payload digest",
                            "Provenance summary",
                            "Release-set summary",
                        )
                    ),
                ).replace("  pull_request:\n", "  pull_request:\n  push:\n    branches: [main]\n"),
                encoding="utf-8",
            )
            report = static_check(root)
        self.assertEqual(report["status"], "STATIC_TARGETED_PASS")

    def test_remote_gate_fixture_requires_exact_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "remote.json"
            fixture.write_text(
                json.dumps(
                    {
                        "workflow": {"state": "active"},
                        "workflow_runs": [
                            {"id": 7, "head_sha": SHA, "path": "release-candidate.yml", "status": "completed", "conclusion": "success"}
                        ],
                        "jobs": [{"name": "release-candidate", "conclusion": "success"}],
                        "check_runs": [
                            {"name": "release-candidate", "head_sha": SHA, "status": "completed", "conclusion": "success", "app": {"id": 42}}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            passed = gate_github(
                repo="owner/repo",
                sha=SHA,
                workflow="release-candidate.yml",
                check_name="release-candidate",
                app_id=42,
                fixture=fixture,
            )
            blocked = gate_github(
                repo="owner/repo",
                sha=SHA,
                workflow="release-candidate.yml",
                check_name="release-candidate",
                app_id=43,
                fixture=fixture,
            )
            inactive_fixture = Path(temp_dir) / "inactive-remote.json"
            inactive_payload = json.loads(fixture.read_text(encoding="utf-8"))
            inactive_payload["workflow"]["state"] = "disabled_manually"
            inactive_fixture.write_text(json.dumps(inactive_payload), encoding="utf-8")
            inactive = gate_github(
                repo="owner/repo",
                sha=SHA,
                workflow="release-candidate.yml",
                check_name="release-candidate",
                app_id=42,
                fixture=inactive_fixture,
            )
            missing_run_fixture = Path(temp_dir) / "missing-run-field.json"
            missing_run_payload = json.loads(fixture.read_text(encoding="utf-8"))
            del missing_run_payload["workflow_runs"][0]["path"]
            missing_run_fixture.write_text(json.dumps(missing_run_payload), encoding="utf-8")
            missing_run = gate_github(
                repo="owner/repo",
                sha=SHA,
                workflow="release-candidate.yml",
                check_name="release-candidate",
                app_id=42,
                fixture=missing_run_fixture,
            )
            missing_check_fixture = Path(temp_dir) / "missing-check-field.json"
            missing_check_payload = json.loads(fixture.read_text(encoding="utf-8"))
            del missing_check_payload["check_runs"][0]["head_sha"]
            missing_check_fixture.write_text(json.dumps(missing_check_payload), encoding="utf-8")
            missing_check = gate_github(
                repo="owner/repo",
                sha=SHA,
                workflow="release-candidate.yml",
                check_name="release-candidate",
                app_id=42,
                fixture=missing_check_fixture,
            )
        self.assertEqual(passed["status"], "PASS")
        self.assertFalse(passed["remote_writes"])
        self.assertEqual(blocked["code"], "CHECK_APP_MISMATCH")
        self.assertEqual(inactive["code"], "WORKFLOW_NOT_ACTIVE")
        self.assertEqual(missing_run["status"], "BLOCKED")
        self.assertEqual(missing_run["code"], "WORKFLOW_RUN_RESPONSE_INCOMPLETE")
        self.assertEqual(missing_check["status"], "BLOCKED")
        self.assertEqual(missing_check["code"], "CHECK_RESPONSE_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
