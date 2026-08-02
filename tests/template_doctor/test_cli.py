"""Black-box contract tests for the Template Doctor CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools.template_doctor.engine import MAX_WORKERS, run_checks
from tools.template_doctor.models import CheckResult
from tools.template_doctor.rules import _state_freshness


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOCTOR_TIMEOUT_SECONDS = 30
GIT_TIMEOUT_SECONDS = 15
MAX_DIAGNOSTIC_CHARS = 4000


def _diagnostic_tail(value: object) -> str:
    if value is None:
        return "<none>"
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[-MAX_DIAGNOSTIC_CHARS:]


def _run_bounded(
    helper_name: str,
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        kwargs: dict[str, object] = {
            "cwd": cwd,
            "check": False,
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "timeout": timeout,
        }
        if env is not None:
            kwargs["env"] = env
        return subprocess.run(command, **kwargs)
    except subprocess.TimeoutExpired as error:
        stdout = getattr(error, "stdout", None) or getattr(error, "output", None)
        raise RuntimeError(
            f"{helper_name} timed out after {timeout} seconds.\n"
            f"command: {command!r}\n"
            f"cwd: {cwd}\n"
            f"stdout tail: {_diagnostic_tail(stdout)}\n"
            f"stderr tail: {_diagnostic_tail(getattr(error, 'stderr', None))}"
        ) from error


def run_doctor(
    root: Path,
    report_format: str = "json",
    *,
    strict: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the public module entry point without depending on implementation details."""

    command = [
        sys.executable,
        "-B",
        "-m",
        "tools.template_doctor",
        "--root",
        str(root),
        "--format",
        report_format,
    ]
    if strict:
        command.append("--strict")
    return _run_bounded(
        "run_doctor",
        command,
        cwd=REPO_ROOT,
        timeout=DOCTOR_TIMEOUT_SECONDS,
    )


def _run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git only against an isolated fixture root with inert user config."""

    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return _run_bounded(
        "_run_git",
        ["git", "-C", str(root), *arguments],
        cwd=REPO_ROOT,
        timeout=GIT_TIMEOUT_SECONDS,
        env=environment,
    )


def materialize_ready_fixture(destination: Path) -> Path:
    """Copy portable source files and create real temp Git/CodeGraph evidence."""

    source = FIXTURES / "ready"
    embedded = [path for path in (source / ".git", source / ".codegraph") if path.exists()]
    if embedded:
        raise AssertionError(f"ready source fixture contains runtime state: {embedded}")

    shutil.copytree(source, destination)
    commands = [
        ("init", "--initial-branch=main"),
        ("add", "--", "README.md"),
        (
            "-c",
            "user.name=Template Doctor Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=NUL",
            "commit",
            "-m",
            "fixture baseline",
        ),
    ]
    for command in commands:
        completed = _run_git(destination, *command)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout)

    head_result = _run_git(destination, "rev-parse", "--verify", "HEAD^{commit}")
    if head_result.returncode != 0:
        raise RuntimeError(head_result.stderr or head_result.stdout)
    head = head_result.stdout.strip()
    state_path = destination / "docs" / "control" / "CURRENT_PROJECT_STATE.md"
    state_lines = state_path.read_text(encoding="utf-8").splitlines()
    state_path.write_text(
        "\n".join(
            f"Based On Commit: {head}"
            if line.startswith("Based On Commit:")
            else f"Current Git HEAD: {head}"
            if line.startswith("Current Git HEAD:")
            else line
            for line in state_lines
        )
        + "\n",
        encoding="utf-8",
    )

    database = destination / ".codegraph" / "index.db"
    database.parent.mkdir()
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE nodes (id INTEGER PRIMARY KEY, qualified_name TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO nodes (qualified_name) VALUES (?)",
            ("fixture.ready",),
        )
        connection.commit()
    finally:
        connection.close()
    return destination


class TemplateDoctorCliTests(unittest.TestCase):
    maxDiff = None

    def test_run_doctor_helper_completes_with_timeout(self) -> None:
        expected = subprocess.CompletedProcess(
            args=["doctor"],
            returncode=0,
            stdout="{}",
            stderr="",
        )
        with patch.object(subprocess, "run", return_value=expected) as mocked:
            completed = run_doctor(FIXTURES / "ready")

        self.assertIs(completed, expected)
        self.assertEqual(mocked.call_args.kwargs["timeout"], DOCTOR_TIMEOUT_SECONDS)

    def test_run_git_helper_completes_with_timeout(self) -> None:
        expected = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        with patch.object(subprocess, "run", return_value=expected) as mocked:
            completed = _run_git(FIXTURES / "ready", "status")

        self.assertIs(completed, expected)
        self.assertEqual(mocked.call_args.kwargs["timeout"], GIT_TIMEOUT_SECONDS)

    def test_run_doctor_timeout_reports_bounded_diagnostics(self) -> None:
        timeout = subprocess.TimeoutExpired(
            ["python", "-m", "tools.template_doctor"],
            DOCTOR_TIMEOUT_SECONDS,
            output="doctor stdout",
            stderr="doctor stderr",
        )
        with patch.object(subprocess, "run", side_effect=timeout):
            with self.assertRaises(RuntimeError) as context:
                run_doctor(FIXTURES / "ready")

        message = str(context.exception)
        self.assertIn("run_doctor timed out after 30 seconds", message)
        self.assertIn("tools.template_doctor", message)
        self.assertIn(str(REPO_ROOT), message)
        self.assertIn("doctor stdout", message)
        self.assertIn("doctor stderr", message)

    def test_run_git_timeout_reports_bounded_diagnostics(self) -> None:
        timeout = subprocess.TimeoutExpired(
            ["git", "status"],
            GIT_TIMEOUT_SECONDS,
            output="git stdout",
            stderr="git stderr",
        )
        with patch.object(subprocess, "run", side_effect=timeout):
            with self.assertRaises(RuntimeError) as context:
                _run_git(FIXTURES / "ready", "status")

        message = str(context.exception)
        self.assertIn("_run_git timed out after 15 seconds", message)
        self.assertIn("git", message)
        self.assertIn(str(REPO_ROOT), message)
        self.assertIn("git stdout", message)
        self.assertIn("git stderr", message)

    def test_timeout_diagnostics_are_bounded(self) -> None:
        long_output = "x" * (MAX_DIAGNOSTIC_CHARS + 100)
        timeout = subprocess.TimeoutExpired(
            ["git", "status"],
            GIT_TIMEOUT_SECONDS,
            output=long_output,
            stderr=long_output,
        )
        with patch.object(subprocess, "run", side_effect=timeout):
            with self.assertRaises(RuntimeError) as context:
                _run_git(FIXTURES / "ready", "status")

        message = str(context.exception)
        self.assertNotIn("x" * (MAX_DIAGNOSTIC_CHARS + 1), message)
        self.assertIn("x" * MAX_DIAGNOSTIC_CHARS, message)

    def test_ready_fixture_returns_zero_and_complete_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "ready")
        self.assertIn("root", report)
        self.assertIn("summary", report)
        self.assertGreater(report["summary"]["total"], 0)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertTrue(report["results"])
        for result in report["results"]:
            self.assertTrue(
                {
                    "rule_id",
                    "severity",
                    "status",
                    "evidence",
                    "recommendation",
                }.issubset(result),
                result,
            )

    def test_absent_codegraph_is_non_blocking_skip_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            shutil.rmtree(ready / ".codegraph")
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "ready")
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "skip")
        self.assertEqual(finding["severity"], "info")

    def test_absent_codegraph_blocks_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            shutil.rmtree(ready / ".codegraph")
            completed = run_doctor(ready)
            strict_completed = run_doctor(ready, strict=True)

        self.assertEqual(strict_completed.returncode, 1, strict_completed.stderr)
        strict_report = json.loads(strict_completed.stdout)
        self.assertEqual(strict_report["status"], "not_ready")
        finding = next(
            item
            for item in strict_report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertEqual(finding["severity"], "error")

    def test_corrupt_codegraph_blocks_in_default_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            (ready / ".codegraph" / "index.db").write_bytes(b"not a sqlite database")
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "not_ready")
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertEqual(finding["severity"], "error")
        self.assertIn(".codegraph/index.db", finding["evidence"])
        self.assertIn("DatabaseError", finding["evidence"])
        self.assertNotIn(str(ready).replace("\\", "/"), finding["evidence"])

    def test_corrupt_codegraph_blocks_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            (ready / ".codegraph" / "index.db").write_bytes(b"not a sqlite database")
            strict_completed = run_doctor(ready, strict=True)

        self.assertEqual(strict_completed.returncode, 1, strict_completed.stderr)
        strict_report = json.loads(strict_completed.stdout)
        finding = next(
            item
            for item in strict_report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertEqual(finding["severity"], "error")
        self.assertIn(".codegraph/index.db", finding["evidence"])
        self.assertIn("DatabaseError", finding["evidence"])

    def test_valid_codegraph_passes_with_relative_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "pass")
        self.assertIn(".codegraph/index.db", finding["evidence"])
        self.assertIn("recognized candidate table(s)", finding["evidence"])
        self.assertIn("nodes", finding["evidence"])
        self.assertNotIn(str(ready).replace("\\", "/"), finding["evidence"])

    def test_mixed_valid_and_corrupt_codegraph_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            codegraph_dir = ready / ".codegraph"
            shutil.copy2(codegraph_dir / "index.db", codegraph_dir / "valid.db")
            (codegraph_dir / "corrupt.db").write_bytes(b"not a sqlite database")
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertEqual(finding["severity"], "error")
        self.assertIn(".codegraph/corrupt.db", finding["evidence"])
        self.assertIn("DatabaseError", finding["evidence"])
        self.assertNotIn(str(ready).replace("\\", "/"), finding["evidence"])

    def test_codegraph_without_schema_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            database = ready / ".codegraph" / "index.db"
            database.unlink()
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE unrelated (id INTEGER)")
                connection.commit()
            finally:
                connection.close()
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertEqual(finding["severity"], "error")
        self.assertIn("no recognized CodeGraph candidate tables", finding["evidence"])
        self.assertIn(".codegraph/index.db", finding["evidence"])
        self.assertNotIn(str(ready).replace("\\", "/"), finding["evidence"])

    def test_nodes_only_codegraph_database_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            database = ready / ".codegraph" / "index.db"
            database.unlink()
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "CREATE TABLE nodes (id TEXT PRIMARY KEY)"
                )
                connection.commit()
            finally:
                connection.close()
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "ready")
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "pass")
        self.assertEqual(finding["severity"], "info")
        self.assertIn("recognized candidate table(s)", finding["evidence"])
        self.assertIn("nodes", finding["evidence"])
        self.assertNotIn(str(ready).replace("\\", "/"), finding["evidence"])

    def test_edges_only_codegraph_database_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            database = ready / ".codegraph" / "index.db"
            database.unlink()
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "CREATE TABLE edges (source TEXT, target TEXT)"
                )
                connection.commit()
            finally:
                connection.close()
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "ready")
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "pass")
        self.assertEqual(finding["severity"], "info")
        self.assertIn("recognized candidate table(s)", finding["evidence"])
        self.assertIn("edges", finding["evidence"])
        self.assertNotIn(str(ready).replace("\\", "/"), finding["evidence"])

    def test_empty_sqlite_codegraph_database_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            database = ready / ".codegraph" / "index.db"
            database.unlink()
            connection = sqlite3.connect(database)
            connection.close()
            completed = run_doctor(ready)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "codegraph.initialized"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertEqual(finding["severity"], "error")
        self.assertIn("no recognized CodeGraph candidate tables", finding["evidence"])
        self.assertNotIn(str(ready).replace("\\", "/"), finding["evidence"])

    def test_manual_commit_metadata_does_not_block_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "manual_metadata"
            materialize_ready_fixture(isolated_root)
            state_path = (
                isolated_root / "docs" / "control" / "CURRENT_PROJECT_STATE.md"
            )
            state_lines = state_path.read_text(encoding="utf-8").splitlines()
            state_path.write_text(
                "\n".join(
                    "Based On Commit: manual record - refresh after each accepted sprint"
                    if line.startswith("Based On Commit:")
                    else "Current Git HEAD: manual record - refresh after each accepted sprint"
                    if line.startswith("Current Git HEAD:")
                    else line
                    for line in state_lines
                )
                + "\n",
                encoding="utf-8",
            )
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "control.current_state_freshness"
        )
        self.assertEqual(finding["status"], "pass")

    def test_stop_state_schema_does_not_require_legacy_head_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "stop_state"
            materialize_ready_fixture(isolated_root)
            state_path = (
                isolated_root / "docs" / "control" / "CURRENT_PROJECT_STATE.md"
            )
            state_path.write_text(
                "# CURRENT_PROJECT_STATE.md\n\n"
                "Last Updated: 2026-08-02\n"
                "State Based On Parent Commit: parent\n"
                "Last Confirmed Remote PR Head: remote\n"
                "Local Stop-State Commit: local\n"
                "Live Local HEAD: must be resolved with git rev-parse HEAD\n"
                "Live Remote PR Head: must be refreshed from GitHub\n\n"
                "Repository state record:\n"
                "current for the documented stop condition\n\n"
                "Remote state:\n"
                "must be refreshed live before every remote transition\n",
                encoding="utf-8",
            )
            result = _state_freshness(isolated_root)

        self.assertEqual(result.status, "pass")
        self.assertIn("stop-state schema", result.evidence)

    def test_placeholder_fixture_returns_one_and_reports_findings(self) -> None:
        completed = run_doctor(FIXTURES / "placeholder")

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "not_ready")
        self.assertGreater(report["summary"]["failed"], 0)
        failed_text = json.dumps(
            [item for item in report["results"] if item["status"] == "fail"],
            ensure_ascii=False,
        ).lower()
        self.assertTrue(
            "placeholder" in failed_text or "todo" in failed_text,
            failed_text,
        )

    def test_config_drift_fixture_reports_unsupported_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "config_drift"
            materialize_ready_fixture(isolated_root)
            shutil.copyfile(
                FIXTURES / "config_drift" / ".codex" / "config.toml",
                isolated_root / ".codex" / "config.toml",
            )
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        config_findings = [
            item
            for item in report["results"]
            if "config" in item["rule_id"].lower()
            or "profile" in str(item["evidence"]).lower()
        ]
        self.assertTrue(config_findings, report["results"])
        self.assertTrue(
            any(item["status"] == "fail" for item in config_findings),
            config_findings,
        )
        self.assertIn("profile", json.dumps(config_findings).lower())

    def test_missing_release_document_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "missing_release_doc"
            materialize_ready_fixture(isolated_root)
            (isolated_root / "SECURITY.md").unlink()
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item for item in report["results"] if item["rule_id"] == "release.documents"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("SECURITY.md", finding["evidence"])

    def test_release_docs_accept_both_verification_wordings_only(self) -> None:
        accepted = {
            "heading": "## Verification\n\nRun the local checks before release.\n",
            "script": "Run scripts/verify.sh before release.\n",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            for label, wording in accepted.items():
                with self.subTest(wording=label):
                    isolated_root = temporary_root / label
                    materialize_ready_fixture(isolated_root)
                    (isolated_root / "README.md").write_text(
                        "# Ready Project\n\n"
                        "Template Doctor and AIWF Run Guard are enabled.\n\n"
                        f"{wording}",
                        encoding="utf-8",
                    )
                    completed = run_doctor(isolated_root)
                    self.assertEqual(
                        completed.returncode,
                        0,
                        completed.stderr or completed.stdout,
                    )

            invalid_root = temporary_root / "missing_wording"
            materialize_ready_fixture(invalid_root)
            (invalid_root / "README.md").write_text(
                "# Ready Project\n\n"
                "Template Doctor and AIWF Run Guard are enabled for releases.\n",
                encoding="utf-8",
            )
            completed = run_doctor(invalid_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item for item in report["results"] if item["rule_id"] == "release.documents"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("README.md", finding["evidence"])

    def test_generated_artifact_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "generated_artifact"
            materialize_ready_fixture(isolated_root)
            cache = isolated_root / "tools" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "module.pyc").write_bytes(b"not executable bytecode")
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "repository.generated_artifacts"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("module.pyc", finding["evidence"])

    def test_sensitive_filename_is_reported_without_reading_secret(self) -> None:
        secret = "do-not-render-this-secret"
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "sensitive_filename"
            materialize_ready_fixture(isolated_root)
            (isolated_root / ".env").write_text(f"TOKEN={secret}\n", encoding="utf-8")
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        self.assertNotIn(secret, completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "repository.sensitive_filenames"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn(".env", finding["evidence"])

    def test_placeholder_github_workflow_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "placeholder_workflow"
            materialize_ready_fixture(isolated_root)
            workflow = isolated_root / ".github" / "workflows" / "example.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: Example\n# TODO: configure\n", encoding="utf-8")
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "github.workflow_placeholders"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("example.yml", finding["evidence"])

    def test_large_file_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "large_file"
            materialize_ready_fixture(isolated_root)
            payload = isolated_root / "large-source.dat"
            payload.write_bytes(b"x" * (1024 * 1024 + 1))
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "repository.large_files"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("large-source.dat", finding["evidence"])

    def test_ready_fixture_has_real_git_commit_and_sqlite_database(self) -> None:
        source = FIXTURES / "ready"
        self.assertFalse((source / ".git").exists())
        self.assertFalse((source / ".codegraph").exists())
        source_state = (source / "docs" / "control" / "CURRENT_PROJECT_STATE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("generated-at-test-runtime", source_state)

        with tempfile.TemporaryDirectory() as temporary_directory:
            ready = materialize_ready_fixture(Path(temporary_directory) / "ready")
            git_result = _run_git(ready, "rev-parse", "--verify", "HEAD^{commit}")
            self.assertEqual(git_result.returncode, 0, git_result.stderr)
            head = git_result.stdout.strip()
            self.assertRegex(head, r"^[0-9a-f]{40,64}$")
            runtime_state = (
                ready / "docs" / "control" / "CURRENT_PROJECT_STATE.md"
            ).read_text(encoding="utf-8")
            self.assertNotIn("generated-at-test-runtime", runtime_state)
            self.assertEqual(runtime_state.count(head), 2)

            database = ready / ".codegraph" / "index.db"
            uri = f"{database.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
            try:
                self.assertEqual(connection.execute("PRAGMA quick_check").fetchone(), ("ok",))
                table_count = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()
            finally:
                connection.close()
            self.assertIsNotNone(table_count)
            self.assertGreater(table_count[0], 0)

    def test_missing_planning_authority_policy_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "missing_policy"
            materialize_ready_fixture(isolated_root)
            (isolated_root / "AGENTS.md").unlink()
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        planning = next(
            item for item in report["results"] if item["rule_id"] == "planning.single_authority"
        )
        self.assertEqual(planning["status"], "fail")

    def test_leaked_local_path_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "leaked_path"
            materialize_ready_fixture(isolated_root)
            readme = isolated_root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + "\nReference: C:\\Users\\owner\\Temp\\codex-template-advanced-pyc-v9\n",
                encoding="utf-8",
            )
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "control.no_local_state"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("README.md", finding["evidence"])

    def test_numeric_status_claim_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "stale_counts"
            materialize_ready_fixture(isolated_root)
            readme = isolated_root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + "\nAll 18 tests passed in the last run.\n",
                encoding="utf-8",
            )
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "control.numeric_status_claims"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("README.md", finding["evidence"])

    def test_active_plan_pointer_mismatch_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "plan_mismatch"
            materialize_ready_fixture(isolated_root)
            planning = isolated_root / ".planning"
            planning.mkdir()
            (planning / ".active_plan").write_text(
                "OTHER-PLAN-001\n", encoding="utf-8"
            )
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "control.sprint_consistency"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("OTHER-PLAN-001", finding["evidence"])

    def test_stale_release_manifest_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "stale_manifest"
            materialize_ready_fixture(isolated_root)
            dist = isolated_root / "dist"
            dist.mkdir()
            (dist / "stale.manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "template-advanced/release-manifest/v1",
                        "root_name": "template-advanced",
                        "version": "1.0.0",
                        "file_count": 1,
                        "publication_digest": (
                            "template-advanced-publication/v1:sha256:"
                            + "0" * 64
                        ),
                        "files": [
                            {
                                "path": "does-not-exist.txt",
                                "size": 0,
                                "sha256": "0" * 64,
                                "mode": "100644",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        finding = next(
            item
            for item in report["results"]
            if item["rule_id"] == "release.manifest_consistency"
        )
        self.assertEqual(finding["status"], "fail")
        self.assertIn("stale.manifest.json", finding["evidence"])

    def test_empty_required_task_section_blocks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "empty_goal"
            materialize_ready_fixture(isolated_root)
            task_path = isolated_root / "docs" / "control" / "NEXT_CODEX_TASK.md"
            task_text = task_path.read_text(encoding="utf-8")
            task_path.write_text(
                task_text.replace(
                    "## Goal\n\nVerify that the initialized sample project remains healthy.",
                    "## Goal\n\n",
                ),
                encoding="utf-8",
            )
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        next_task = next(
            item
            for item in report["results"]
            if item["rule_id"] == "control.next_task_executable"
        )
        self.assertEqual(next_task["status"], "fail")
        self.assertIn("Goal", next_task["evidence"])

    def test_equivalent_task_packet_headings_are_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory) / "equivalent_headings"
            materialize_ready_fixture(isolated_root)
            task_path = isolated_root / "docs" / "control" / "NEXT_CODEX_TASK.md"
            task_text = task_path.read_text(encoding="utf-8")
            task_text = task_text.replace("## Budget", "## Budgets And Stop Conditions")
            task_text = task_text.replace(
                "\n## Stop Conditions\n\n- Stop if a dependency change is required.\n",
                "\n",
            )
            task_text = task_text.replace(
                "## Required Return Format", "## Required Return"
            )
            task_path.write_text(task_text, encoding="utf-8")
            completed = run_doctor(isolated_root)

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        next_task = next(
            item
            for item in report["results"]
            if item["rule_id"] == "control.next_task_executable"
        )
        self.assertEqual(next_task["status"], "pass")

    def test_invalid_root_returns_two_without_traceback(self) -> None:
        missing = FIXTURES / "does-not-exist"
        completed = run_doctor(missing)

        self.assertEqual(completed.returncode, 2)
        self.assertFalse(completed.stdout.strip())
        self.assertTrue(completed.stderr.strip())
        self.assertNotIn("Traceback", completed.stderr)

    def test_markdown_report_contains_each_required_result_field(self) -> None:
        completed = run_doctor(FIXTURES / "placeholder", "markdown")

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        report = completed.stdout.lower()
        for label in (
            "rule id",
            "severity",
            "status",
            "evidence",
            "recommendation",
        ):
            self.assertIn(label, report)

    def test_concurrent_json_output_is_stable_and_sorted(self) -> None:
        runs = [run_doctor(FIXTURES / "placeholder") for _ in range(5)]

        for completed in runs:
            self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        self.assertTrue(
            all(completed.stdout == runs[0].stdout for completed in runs[1:]),
            "JSON output changed across repeated concurrent runs",
        )
        report = json.loads(runs[0].stdout)
        rule_ids = [item["rule_id"] for item in report["results"]]
        self.assertEqual(rule_ids, sorted(rule_ids))

    def test_engine_uses_bounded_concurrency_and_sorts_results(self) -> None:
        barrier = threading.Barrier(MAX_WORKERS, timeout=5)
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def make_rule(rule_id: str):
            def rule() -> CheckResult:
                nonlocal active, maximum_active
                with lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                try:
                    barrier.wait()
                    return CheckResult(
                        rule_id=rule_id,
                        severity="info",
                        status="pass",
                        evidence=f"{rule_id} completed",
                        recommendation="No action required.",
                    )
                finally:
                    with lock:
                        active -= 1

            rule.rule_id = rule_id
            return rule

        rules = [make_rule(f"fixture.rule.{index:02d}") for index in reversed(range(8))]
        report = run_checks(FIXTURES / "ready", rules=rules, max_workers=99)

        self.assertEqual(report.status, "ready")
        self.assertEqual(maximum_active, MAX_WORKERS)
        self.assertLessEqual(maximum_active, MAX_WORKERS)
        rule_ids = [item.rule_id for item in report.results]
        self.assertEqual(rule_ids, sorted(rule_ids))

    def test_argparse_rejects_unsupported_format_with_exit_two(self) -> None:
        completed = _run_bounded(
            "run_doctor",
            [
                sys.executable,
                "-B",
                "-m",
                "tools.template_doctor",
                "--root",
                str(FIXTURES / "ready"),
                "--format",
                "xml",
            ],
            cwd=REPO_ROOT,
            timeout=DOCTOR_TIMEOUT_SECONDS,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid choice", completed.stderr.lower())

    def _config_rule(self, root: Path) -> dict[str, object]:
        from tools.template_doctor.rules import _codex_config_safe_defaults

        return _codex_config_safe_defaults(root).to_dict()

    def test_config_safe_defaults_accepts_safe_committed_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "safe"
            config = root / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'approval_policy = "on-request"\n'
                'sandbox_mode = "workspace-write"\n'
                "[sandbox_workspace_write]\n"
                "network_access = false\n",
                encoding="utf-8",
            )
            result = self._config_rule(root)

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["rule_id"], "config.safe_defaults")
        self.assertIn(".codex/config.toml", result["evidence"])
        self.assertNotIn("\\", result["evidence"])

    def test_config_safe_defaults_rejects_never_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "never"
            config = root / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text('approval_policy = "never"\n', encoding="utf-8")
            result = self._config_rule(root)

        self.assertEqual(result["status"], "fail")
        self.assertIn("approval_policy is 'never'", result["evidence"])

    def test_config_safe_defaults_rejects_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "network"
            config = root / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'approval_policy = "on-request"\n'
                'sandbox_mode = "workspace-write"\n'
                "[sandbox_workspace_write]\n"
                "network_access = true\n",
                encoding="utf-8",
            )
            result = self._config_rule(root)

        self.assertEqual(result["status"], "fail")
        self.assertIn("network_access is enabled", result["evidence"])

    def test_config_safe_defaults_rejects_corrupt_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "corrupt"
            config = root / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text('approval_policy = "on-request\n', encoding="utf-8")
            result = self._config_rule(root)

        self.assertEqual(result["status"], "fail")
        self.assertIn("not valid TOML", result["evidence"])

    def test_config_safe_defaults_requires_committed_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "missing"
            root.mkdir()
            result = self._config_rule(root)

        self.assertEqual(result["status"], "fail")
        self.assertIn("is missing", result["evidence"])

    def test_config_safe_defaults_evidence_uses_only_relative_paths(self) -> None:
        """Evidence must never embed the absolute fixture path."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "path"
            config = root / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'approval_policy = "on-request"\n'
                "# C:\\Users\\owner secret\n",
                encoding="utf-8",
            )
            result = self._config_rule(root)

        self.assertEqual(result["status"], "fail")
        self.assertIn("absolute local path", result["evidence"])
        self.assertNotIn(str(temporary_directory).replace("\\", "/"), result["evidence"])


if __name__ == "__main__":
    unittest.main()
