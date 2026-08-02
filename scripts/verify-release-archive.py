#!/usr/bin/env python3
"""Verify a template-advanced release archive against its manifest.

Usage (from the repository root):

    py -3 scripts/verify-release-archive.py --archive dist/template-advanced-<version>.zip --manifest dist/template-advanced-<version>.manifest.json

Optional:

    --extract-dir <dir>   extract the archive to an existing empty directory
    --validate            after extraction, run setup/verify/eval/doctor/preflight

Checks:

1. manifest schema, file count, and digest;
2. no path escape, duplicate path, case-collision, or symlink entry;
3. every entry matches the manifest path, size, SHA-256, and POSIX mode;
4. every ``.sh`` entry carries executable mode;
5. no local-state, cache, VCS, or generated paths;
6. text contents contain no author absolute paths or credential patterns;
7. user-facing docs do not depend on the executable bit (no ``./scripts/``);
8. optional full validation in the extracted tree.

Exit 0 verifies, 1 fails verification, 2 is an invocation error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


# Never write bytecode caches into the workspace or an extracted validation
# tree, even when the caller did not preset PYTHONDONTWRITEBYTECODE or pass -B.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.template_doctor.policy import (  # noqa: E402
    RELEASE_EXTRACTION_ALLOWED_FAILURES,
)
from tools.template_doctor.release_inventory import (  # noqa: E402
    TEXT_FILE_SUFFIXES,
    iter_release_entries,
    publication_digest,
)


MANIFEST_SCHEMA = "template-advanced/release-manifest/v1"

FORBIDDEN_PATH_FRAGMENTS = (
    ".active_plan",
    ".codegraph/",
    ".git/",
    ".mode",
    ".nonce",
    ".planning/",
    ".stop_blocks",
    "__pycache__/",
    "dist/",
)
FORBIDDEN_PATH_SUFFIXES = (".pyc", ".pyo")

CREDENTIAL_PATTERNS = (
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{10,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA" + r"[A-Z0-9]{16}"),
    # Character-class spelling keeps the verifier's own source from matching.
    re.compile(r"BEGIN\s+PR[IV]ATE\s+K[EY]"),
)

# Local-path patterns apply only to user-facing documentation; tests and
# fixtures legitimately embed these strings to exercise the scanner.
LOCAL_PATH_PATTERNS = (
    re.compile(r"C:\\Users\\"),
    re.compile(r"/Users/"),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"AppData"),
    re.compile(r"codex-template-advanced-(?:pyc|publication)-"),
    re.compile(r"\.planning/\.active_plan"),
)

EXEC_BIT_DOC_PATTERNS = (
    re.compile(r"\./scripts/"),
    re.compile(r"\./evals/"),
)
EXEC_BIT_DOC_PATHS = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs",
    ".github/codex/prompts",
    "evals/tasks",
)
LOCAL_PATH_DOC_PATHS = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs",
    ".github/codex/prompts",
    "evals/tasks",
    "evals/expected",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py -3 scripts/verify-release-archive.py",
        description="Verify a release archive against its manifest and hygiene rules.",
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--extract-dir")
    parser.add_argument("--validate", action="store_true")
    return parser


def _fail(message: str) -> int:
    print(f"verify-release-archive: FAIL: {message}", file=sys.stderr)
    return 1


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest: {type(exc).__name__}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported manifest schema: {raw.get('schema')!r}")
    return raw


def _check_entry_hygiene(names: list[str]) -> list[str]:
    problems: list[str] = []
    lowered: dict[str, str] = {}
    for name in names:
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            problems.append(f"absolute path: {name}")
        if ".." in name.split("/"):
            problems.append(f"parent traversal: {name}")
        if name.startswith((".active_plan", ".mode", ".nonce", ".stop_blocks")):
            problems.append(f"local-state file: {name}")
        for fragment in FORBIDDEN_PATH_FRAGMENTS:
            if fragment in name:
                problems.append(f"forbidden path {fragment!r}: {name}")
        if name.endswith(FORBIDDEN_PATH_SUFFIXES):
            problems.append(f"generated artifact: {name}")
        folded = name.casefold()
        previous = lowered.get(folded)
        if previous is not None and previous != name:
            problems.append(f"case collision: {previous} vs {name}")
        lowered[folded] = name
    return problems


def _content_scan(archive: zipfile.ZipFile) -> list[str]:
    problems: list[str] = []
    for info in archive.infolist():
        name = info.filename
        if not any(name.endswith(suffix) for suffix in TEXT_FILE_SUFFIXES):
            continue
        try:
            text = archive.read(info).decode("utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text):
                problems.append(f"{name}: credential pattern {pattern.pattern}")
        is_documentation = any(
            name == relative or name.startswith(relative + "/")
            for relative in LOCAL_PATH_DOC_PATHS
        )
        if not is_documentation:
            continue
        for pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(text):
                problems.append(f"{name}: local-path pattern {pattern.pattern}")
    return problems


def _doc_exec_bit_scan(archive: zipfile.ZipFile) -> list[str]:
    problems: list[str] = []
    for info in archive.infolist():
        name = info.filename
        if not any(
            name == relative or name.startswith(relative + "/")
            for relative in EXEC_BIT_DOC_PATHS
        ):
            continue
        if not name.endswith((".md", ".txt")):
            continue
        try:
            text = archive.read(info).decode("utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in EXEC_BIT_DOC_PATTERNS:
            if pattern.search(text):
                problems.append(f"{name}: exec-bit-dependent invocation {pattern.pattern}")
    return problems


def _find_bash() -> str:
    override = os.environ.get("AIWF_BASH")
    if override and Path(override).is_file():
        return override
    git = shutil.which("git")
    if git:
        git_bash = Path(git).resolve().parent.parent / "bin" / "bash.exe"
        if git_bash.is_file():
            return str(git_bash)
    discovered = shutil.which("bash")
    if discovered:
        windows_dir = os.environ.get("WINDIR")
        if windows_dir and str(Path(discovered)).lower().startswith(
            Path(windows_dir).resolve().as_posix().lower()
        ):
            # The system32 bash launcher is WSL and cannot reliably run
            # Windows-relative validation from a Python subprocess.
            discovered = None
        else:
            return discovered
    raise ValueError(
        "bash is required for --validate; install Git for Windows or set AIWF_BASH"
    )


# Per-stage bounds so validation can never wait indefinitely. Every stage runs
# through ``run_process_tree`` which starts the command in its own process
# group and terminates the entire tree on timeout.
VALIDATION_TIMEOUTS = {
    "setup": 120,
    "verify": 900,
    "evals": 900,
    "doctor": 300,
    "preflight": 120,
}


def _run_validation(extracted: Path, bash: str, python: list[str]) -> list[str]:
    from tools.aiwf_run_guard.procutil import (
        ProcessTimedOutError,
        run_process_tree_or_raise,
    )

    problems: list[str] = []
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        # Lets released pipeline tests skip themselves when they run inside a
        # validation of an extracted release, preventing recursive --validate.
        "AIWF_RELEASE_VALIDATION": "1",
    }

    def run(
        label: str,
        command: list[str],
        *,
        expected: set[int],
        timeout: int,
    ) -> None:
        try:
            completed = run_process_tree_or_raise(
                command,
                cwd=extracted,
                env=env,
                timeout=timeout,
                label=label,
            )
        except ProcessTimedOutError as exc:
            problems.append(str(exc))
            return
        if completed.returncode not in expected:
            problems.append(
                f"{label}: exit {completed.returncode} (expected {sorted(expected)}); "
                f"{completed.stdout.strip()[-400:]}; {completed.stderr.strip()[-400:]}"
            )

    run("setup", [bash, "scripts/setup.sh"], expected={0}, timeout=VALIDATION_TIMEOUTS["setup"])
    run("verify", [bash, "scripts/verify.sh"], expected={0}, timeout=VALIDATION_TIMEOUTS["verify"])
    run("evals", [bash, "evals/run-evals.sh"], expected={0}, timeout=VALIDATION_TIMEOUTS["evals"])

    doctor_command = [
        *python,
        "-B",
        "-m",
        "tools.template_doctor",
        "--root",
        ".",
        "--format",
        "json",
    ]
    try:
        doctor = run_process_tree_or_raise(
            doctor_command,
            cwd=extracted,
            env=env,
            timeout=VALIDATION_TIMEOUTS["doctor"],
            label="doctor",
        )
    except ProcessTimedOutError as exc:
        problems.append(str(exc))
        return problems
    if doctor.returncode not in {0, 1}:
        problems.append(f"doctor: exit {doctor.returncode} (expected 0 or 1)")
    elif doctor.returncode == 1:
        try:
            report = json.loads(doctor.stdout)
            failed = {
                item["rule_id"]
                for item in report.get("results", [])
                if item.get("status") == "fail"
            }
            errors = report.get("summary", {}).get("errors", 0)
            allowed = RELEASE_EXTRACTION_ALLOWED_FAILURES
            if not failed.issubset(allowed) or errors:
                problems.append(
                    f"doctor: unexpected findings failed={sorted(failed)} errors={errors}"
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            problems.append(f"doctor: unparseable report: {type(exc).__name__}")

    run(
        "preflight",
        [
            *python,
            "-B",
            "-m",
            "tools.aiwf_run_guard",
            "preflight",
            "--root",
            ".",
            "--format",
            "json",
        ],
        expected={0},
        timeout=VALIDATION_TIMEOUTS["preflight"],
    )
    return problems


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    archive_path = Path(args.archive).resolve()
    manifest_path = Path(args.manifest).resolve()

    try:
        manifest = _read_manifest(manifest_path)
        files_raw = manifest.get("files")
        if not isinstance(files_raw, list) or not files_raw:
            return _fail("manifest contains no files")
        from tools.template_doctor.release_inventory import ReleaseEntry

        manifest_entries = [ReleaseEntry.from_dict(item) for item in files_raw]
        if manifest.get("file_count") != len(manifest_entries):
            return _fail(
                f"manifest file_count {manifest.get('file_count')} != {len(manifest_entries)}"
            )
        expected_digest = manifest.get("publication_digest")
        if expected_digest != publication_digest(manifest_entries):
            return _fail("manifest publication_digest does not match its own entries")

        with zipfile.ZipFile(archive_path, mode="r") as archive:
            bad_file = archive.testzip()
            if bad_file is not None:
                return _fail(f"archive CRC failure: {bad_file}")
            names = [info.filename for info in archive.infolist()]
            if len(names) != len(set(names)):
                return _fail("archive contains duplicate paths")
            hygiene = _check_entry_hygiene(names)
            if hygiene:
                return _fail("path hygiene: " + "; ".join(hygiene[:10]))
            if sorted(names) != [entry.path for entry in manifest_entries]:
                return _fail(
                    "archive path set differs from manifest "
                    f"({len(names)} vs {len(manifest_entries)})"
                )

            problems: list[str] = []
            by_path = {entry.path: entry for entry in manifest_entries}
            for info in archive.infolist():
                entry = by_path.get(info.filename)
                if entry is None:
                    continue
                mode = (info.external_attr >> 16) & 0o777
                if info.create_system == 3 and (info.external_attr >> 28) & 0xF != 0o10:
                    problems.append(f"{info.filename}: not a regular file entry")
                if mode != (entry.mode & 0o777):
                    problems.append(
                        f"{info.filename}: mode {mode:o} != manifest {entry.mode & 0o777:o}"
                    )
                if info.filename.endswith(".sh") and mode != 0o755:
                    problems.append(f"{info.filename}: shell script lacks exec mode 755")
                data = archive.read(info)
                if len(data) != entry.size:
                    problems.append(
                        f"{info.filename}: size {len(data)} != manifest {entry.size}"
                    )
                digest = hashlib.sha256(data).hexdigest()
                if digest != entry.sha256:
                    problems.append(f"{info.filename}: SHA-256 mismatch")

            problems.extend(_content_scan(archive))
            problems.extend(_doc_exec_bit_scan(archive))
            if problems:
                return _fail("; ".join(problems[:10]))

        if args.validate:
            temporary_extract = False
            if args.extract_dir:
                extract_dir = Path(args.extract_dir).resolve()
                extract_dir.mkdir(parents=True, exist_ok=True)
            else:
                extract_dir = Path(
                    tempfile.mkdtemp(prefix="template-advanced-release-verify-")
                )
                temporary_extract = True
            try:
                with zipfile.ZipFile(archive_path, mode="r") as archive:
                    archive.extractall(extract_dir)
                bash = _find_bash()
                python = [sys.executable]
                problems = _run_validation(extract_dir, bash, python)
                if problems:
                    return _fail("extracted validation: " + "; ".join(problems[:10]))
            finally:
                if temporary_extract:
                    shutil.rmtree(extract_dir, ignore_errors=True)
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as exc:
        print(f"verify-release-archive: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(
        f"verify-release-archive: passed ({len(manifest_entries)} files; "
        "hygiene, digest, mode, and validation checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
