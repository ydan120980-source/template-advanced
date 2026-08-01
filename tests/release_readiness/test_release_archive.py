"""Release build, archive verification, and clean-template contract tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tools.template_doctor.release_inventory import (
    ReleaseEntry,
    publication_digest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "1.0.0"
STEM = f"template-advanced-{RELEASE_VERSION}"


def _run_python(
    root: Path,
    *arguments: str,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, *arguments],
        cwd=cwd or root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"command failed with exit {completed.returncode}: "
            f"{completed.stderr.strip()[-500:]}"
        )
    return completed


def _write_archive_and_manifest(
    directory: Path,
    paths: list[str],
    contents: list[str],
    *,
    mode: int = 0o100644,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    archive_path = directory / "sample.zip"
    entries: list[ReleaseEntry] = []
    with zipfile.ZipFile(archive_path, mode="w") as archive:
        for path, content in zip(paths, contents):
            data = content.encode("utf-8")
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (mode & 0xFFFF) << 16
            archive.writestr(info, data)
            entries.append(
                ReleaseEntry(
                    path=path,
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    mode=mode,
                )
            )
    manifest_path = directory / "sample.manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "template-advanced/release-manifest/v1",
                "root_name": "template-advanced",
                "version": RELEASE_VERSION,
                "file_count": len(entries),
                "publication_digest": publication_digest(entries),
                "files": [entry.to_dict() for entry in entries],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return archive_path, manifest_path


class ReleasePipelineTests(unittest.TestCase):
    maxDiff = None

    def test_build_release_is_deterministic_and_pollution_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "first"
            second = Path(temporary_directory) / "second"
            first.mkdir()
            second.mkdir()
            for out_dir in (first, second):
                _run_python(
                    REPO_ROOT,
                    "scripts/build-release.py",
                    "--out-dir",
                    str(out_dir),
                )
            first_manifest = (first / f"{STEM}.manifest.json").read_bytes()
            second_manifest = (second / f"{STEM}.manifest.json").read_bytes()
            first_zip = (first / f"{STEM}.zip").read_bytes()
            second_zip = (second / f"{STEM}.zip").read_bytes()
            first_digest_bytes = (first / f"{STEM}.digest.txt").read_bytes()
            second_digest_bytes = (second / f"{STEM}.digest.txt").read_bytes()
            first_digest = (first / f"{STEM}.digest.txt").read_text(
                encoding="utf-8"
            ).strip()
            second_digest = (second / f"{STEM}.digest.txt").read_text(
                encoding="utf-8"
            ).strip()

        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_zip, second_zip)
        self.assertEqual(first_digest_bytes, second_digest_bytes)
        self.assertEqual(first_digest, second_digest)
        self.assertNotIn(b"\r\n", first_manifest)
        self.assertTrue(first_manifest.endswith(b"\n"))
        self.assertNotIn(b"\r\n", first_digest_bytes)
        self.assertTrue(first_digest_bytes.endswith(b"\n"))
        manifest = json.loads(first_manifest)
        self.assertEqual(manifest["file_count"], len(manifest["files"]))
        self.assertEqual(manifest["publication_digest"], first_digest)
        paths = [entry["path"] for entry in manifest["files"]]
        self.assertEqual(paths, sorted(paths))
        pollution = [
            path
            for path in paths
            if path.startswith((".planning", ".mode", ".nonce", ".stop_blocks"))
            or "__pycache__" in path
            or path.endswith((".pyc", ".pyo"))
        ]
        self.assertEqual(pollution, [])
        shell_modes = {
            entry["path"]: entry["mode"]
            for entry in manifest["files"]
            if entry["path"].endswith(".sh")
        }
        self.assertTrue(shell_modes)
        self.assertTrue(all(mode == "100755" for mode in shell_modes.values()))

    def test_verifier_accepts_built_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_dir = Path(temporary_directory) / "build"
            out_dir.mkdir()
            _run_python(
                REPO_ROOT,
                "scripts/build-release.py",
                "--out-dir",
                str(out_dir),
            )
            completed = _run_python(
                REPO_ROOT,
                "scripts/verify-release-archive.py",
                "--archive",
                str(out_dir / f"{STEM}.zip"),
                "--manifest",
                str(out_dir / f"{STEM}.manifest.json"),
            )

        self.assertIn("passed", completed.stdout)

    def test_verifier_rejects_pollution_and_case_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            polluted_archive, polluted_manifest = _write_archive_and_manifest(
                root / "polluted",
                ["README.md", ".planning/.active_plan"],
                ["readme\n", "2026-08-01-TEMPLATE-ONBOARDING-V1\n"],
            )
            collision_archive, collision_manifest = _write_archive_and_manifest(
                root / "collision",
                ["docs/A.txt", "docs/a.txt"],
                ["one\n", "two\n"],
            )
            polluted = _run_python(
                REPO_ROOT,
                "scripts/verify-release-archive.py",
                "--archive",
                str(polluted_archive),
                "--manifest",
                str(polluted_manifest),
                check=False,
            )
            collision = _run_python(
                REPO_ROOT,
                "scripts/verify-release-archive.py",
                "--archive",
                str(collision_archive),
                "--manifest",
                str(collision_manifest),
                check=False,
            )

        self.assertEqual(polluted.returncode, 1, polluted.stderr)
        self.assertIn(".planning", polluted.stderr)
        self.assertEqual(collision.returncode, 1, collision.stderr)
        self.assertIn("case collision", collision.stderr)

    def test_validate_without_bytecode_env_guard_is_clean(self) -> None:
        if os.environ.get("AIWF_RELEASE_VALIDATION") == "1":
            self.skipTest(
                "skipped inside extracted-release validation to avoid recursion"
            )
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if key != "PYTHONDONTWRITEBYTECODE"
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_dir = Path(temporary_directory) / "build"
            out_dir.mkdir()
            _run_python(
                REPO_ROOT,
                "scripts/build-release.py",
                "--out-dir",
                str(out_dir),
            )
            extract_dir = Path(temporary_directory) / "extract"
            extract_dir.mkdir()
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/verify-release-archive.py",
                    "--archive",
                    str(out_dir / f"{STEM}.zip"),
                    "--manifest",
                    str(out_dir / f"{STEM}.manifest.json"),
                    "--validate",
                    "--extract-dir",
                    str(extract_dir),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=clean_env,
            )
            bytecode = [
                path.relative_to(extract_dir).as_posix()
                for path in extract_dir.rglob("*")
                if path.is_dir() and path.name == "__pycache__"
            ] + [
                path.relative_to(extract_dir).as_posix()
                for path in extract_dir.rglob("*.pyc")
            ]

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("passed", completed.stdout)
        self.assertEqual(bytecode, [])

    def test_readme_documents_release_entrypoints_without_exec_bit_dependence(
        self,
    ) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("scripts/build-release.py", readme)
        self.assertIn("scripts/verify-release-archive.py", readme)
        self.assertIn("bash scripts/verify.sh", readme)
        self.assertNotIn("./scripts/", readme)
        self.assertNotIn("./evals/", readme)
        self.assertNotIn("E:\\Program Files", readme)
        contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertNotIn("./scripts/", contributing)
        self.assertNotIn("E:\\Program Files", contributing)
        for path in (
            (REPO_ROOT / "README.md"),
            (REPO_ROOT / "CONTRIBUTING.md"),
            *sorted((REPO_ROOT / "docs").rglob("*.md")),
            *sorted((REPO_ROOT / "evals" / "tasks").rglob("*.md")),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"[A-Za-z]:\\", str(path))
            self.assertNotIn("C:\\Users", text)

    def test_powershell_wrapper_discovers_python(self) -> None:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            self.skipTest("PowerShell is not available on this host")
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(REPO_ROOT / "scripts" / "aiwf-run-guard.ps1"),
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage", completed.stdout.lower())

    def test_shared_policy_has_exactly_git_baseline_allowed(self) -> None:
        from tools.template_doctor.policy import (
            RELEASE_EXTRACTION_ALLOWED_FAILURES,
        )

        self.assertEqual(RELEASE_EXTRACTION_ALLOWED_FAILURES, frozenset({"git.baseline"}))
        self.assertNotIn("codegraph.initialized", RELEASE_EXTRACTION_ALLOWED_FAILURES)

    def test_ci_gate_uses_shared_policy(self) -> None:
        import importlib.util

        from tools.template_doctor.policy import (
            RELEASE_EXTRACTION_ALLOWED_FAILURES,
        )

        gate_path = REPO_ROOT / "scripts" / "ci-doctor-gate.py"
        spec = importlib.util.spec_from_file_location("ci_doctor_gate", gate_path)
        assert spec is not None and spec.loader is not None
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        self.assertIs(gate.ALLOWED_FINDINGS, RELEASE_EXTRACTION_ALLOWED_FAILURES)

    def test_extracted_validation_rejects_corrupt_codegraph_database(self) -> None:
        if os.environ.get("AIWF_RELEASE_VALIDATION") == "1":
            self.skipTest(
                "skipped inside extracted-release validation to avoid recursion"
            )
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_dir = Path(temporary_directory) / "build"
            out_dir.mkdir()
            _run_python(
                REPO_ROOT,
                "scripts/build-release.py",
                "--out-dir",
                str(out_dir),
            )
            extract_dir = Path(temporary_directory) / "extract"
            with zipfile.ZipFile(out_dir / f"{STEM}.zip", mode="r") as archive:
                archive.extractall(extract_dir)
            corrupt = extract_dir / ".codegraph" / "index.db"
            corrupt.parent.mkdir(exist_ok=True)
            corrupt.write_bytes(b"not a sqlite database")
            completed = _run_python(
                REPO_ROOT,
                "scripts/verify-release-archive.py",
                "--archive",
                str(out_dir / f"{STEM}.zip"),
                "--manifest",
                str(out_dir / f"{STEM}.manifest.json"),
                "--validate",
                "--extract-dir",
                str(extract_dir),
                check=False,
            )

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("unexpected findings", completed.stderr)
        self.assertIn("codegraph.initialized", completed.stderr)

    def test_validation_timeout_reports_stage_name_and_command(self) -> None:
        import importlib.util
        import unittest.mock

        from tools.template_doctor.policy import (
            RELEASE_EXTRACTION_ALLOWED_FAILURES,
        )

        verifier_path = REPO_ROOT / "scripts" / "verify-release-archive.py"
        spec = importlib.util.spec_from_file_location("verify_release_archive", verifier_path)
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        with tempfile.TemporaryDirectory() as temporary_directory:
            extracted = Path(temporary_directory) / "extracted"
            extracted.mkdir()
            with unittest.mock.patch.object(
                verifier.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(
                    ["bash", "scripts/setup.sh"], timeout=120, output="partial output"
                ),
            ):
                problems = verifier._run_validation(
                    extracted, "bash", [sys.executable]
                )

        self.assertTrue(problems)
        self.assertIn("setup: timed out after 120s", problems[0])
        self.assertIn("bash scripts/setup.sh", problems[0])
        self.assertIn("partial output", problems[0])

    def test_clean_template_has_no_author_state_or_active_plan(self) -> None:
        for relative in (".planning", ".mode", ".nonce", ".stop_blocks"):
            self.assertFalse((REPO_ROOT / relative).exists(), relative)
        packet = (REPO_ROOT / "docs" / "control" / "NEXT_CODEX_TASK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("TEMPLATE-ONBOARDING-V1", packet)
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                (REPO_ROOT / "README.md"),
                (REPO_ROOT / "CONTRIBUTING.md"),
                *sorted((REPO_ROOT / "docs").rglob("*.md")),
            )
        )
        self.assertNotRegex(combined, r"[A-Za-z]:\\")
        self.assertNotIn("C:\\Users", combined)
        self.assertNotIn("codex-template-advanced-pyc-v9", combined)
        self.assertNotIn("codex-template-advanced-publication-v16", combined)


if __name__ == "__main__":
    unittest.main()
