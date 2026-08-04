"""Deterministic local Git migration matrices for the v2 bootstrap."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .canonical import canonical_json, sha256_bytes, sha256_canonical


VALID_CLASSIFICATIONS = frozenset({"PORT", "REIMPLEMENT", "SPLIT", "DROP"})
FORBIDDEN_MARKERS = ("TODO", "UNKNOWN", "REVIEW")


class MigrationError(RuntimeError):
    """A Git ref or migration matrix could not be trusted."""

    def __init__(self, message: str, *, status: str = "BLOCKED", code: str = "MIGRATION_FAILED"):
        super().__init__(message)
        self.status = status
        self.code = code


def _git(root: Path, *args: str, timeout: float = 20.0, binary: bool = False) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MigrationError(f"git {args[0]} unavailable or timed out: {type(exc).__name__}", code="GIT_UNAVAILABLE") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raise MigrationError(
            f"git {' '.join(args)} failed: {stderr or completed.returncode}",
            code="GIT_COMMAND_FAILED",
        )
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", "replace")


def _ref_sha(root: Path, ref: str) -> str:
    value = str(_git(root, "rev-parse", "--verify", f"{ref}^{{commit}}"))
    return value.strip()


def _optional_blob(root: Path, ref: str, path: str) -> str | None:
    try:
        value = _git(root, "rev-parse", "--verify", f"{ref}:{path}")
        return str(value).strip()
    except MigrationError:
        return None


def _path_policy(path: str) -> dict[str, Any]:
    """Return a deterministic disposition for each known PR #2 path."""

    if path.startswith("docs/control/"):
        return {
            "classification": "DROP",
            "target_pr": "A",
            "rationale": "Retire the old active control plane; preserve the source only in PR #2 history.",
            "required_validation": ["control-plane migration review"],
            "security_contract_notes": "Do not carry dynamic CI, review, or release claims into v2 Git history.",
        }
    if path in {
        ".github/workflows/ci.yml",
        ".github/workflows/security.yml",
        "docs/ai-workflow/GITHUB_RELEASE_READINESS.md",
        "docs/architecture/CODEGRAPH.md",
        "tests/template_doctor/test_cli.py",
        "tools/template_doctor/__init__.py",
        "tools/template_doctor/release_inventory.py",
        "tools/template_doctor/rules.py",
    }:
        return {
            "classification": "SPLIT",
            "target_pr": "A+B",
            "rationale": "Separate governance-foundation behavior from release/product behavior before porting.",
            "required_validation": ["targeted unit tests", "Template Doctor", "CI Doctor"],
            "security_contract_notes": "Revalidate permissions, path inventory, and control-plane assumptions independently.",
        }
    if path == ".github/workflows/release-artifacts.yml":
        return {
            "classification": "SPLIT",
            "target_pr": "A+B",
            "rationale": "Extract the read-only release-candidate gate for PR A and rebuild tag publishing in PR B.",
            "required_validation": ["workflow targeted check", "release integration", "remote exact-SHA gate"],
            "security_contract_notes": "Keep build read and publish write permissions separated; do not port unreviewed workflow text.",
        }
    if path in {
        "scripts/build-release.py",
        "scripts/integration-test-release.sh",
        "scripts/invoke-git-bash.ps1",
        "scripts/verify-release-archive.py",
        "tests/aiwf_run_guard/test_procutil.py",
        "tests/release_readiness/test_release_archive.py",
        "tests/release_readiness/test_release_notes.py",
        "tests/release_readiness/test_release_source_gate.py",
        "tools/project_version.py",
    }:
        return {
            "classification": "REIMPLEMENT",
            "target_pr": "B",
            "rationale": "Reimplement the validated release/process behavior only after the v2 foundation is merged.",
            "required_validation": ["unit tests", "verify.sh", "release integration", "clean extraction"],
            "security_contract_notes": "Do not copy the PR #2 release workflow or dynamic state claims wholesale.",
        }
    if path in {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md"}:
        return {
            "classification": "SPLIT",
            "target_pr": "A+B",
            "rationale": "Retain stable policy only; rewrite v2 migration and release content after behavior is implemented.",
            "required_validation": ["documentation hygiene", "Template Doctor", "release readiness"],
            "security_contract_notes": "Remove stale v1.1.0 completion claims and keep security guidance factual.",
        }
    if path == "tools/aiwf_run_guard/__init__.py":
        return {
            "classification": "DROP",
            "target_pr": "A",
            "rationale": "Do not port a version-only Run Guard change; its v2 role is handled by a separate governance migration.",
            "required_validation": ["Run Guard compatibility tests"],
            "security_contract_notes": "Preserve the existing local diagnostic tool until its explicit downgrade task.",
        }
    return {
        "classification": "DROP",
        "target_pr": "A",
        "rationale": "Not part of the approved Stage 0/PR A or PR B migration surface; preserve only in PR #2 history.",
        "required_validation": ["migration matrix verification"],
        "security_contract_notes": "No unclassified path may enter v2 without an explicit follow-up task.",
    }


def _commit_policy(paths: Iterable[str]) -> tuple[str, str, str]:
    policies = [_path_policy(path) for path in paths]
    classifications = {item["classification"] for item in policies}
    targets = {item["target_pr"] for item in policies}
    if classifications == {"DROP"}:
        classification = "DROP"
    elif len(classifications) == 1:
        classification = next(iter(classifications))
    else:
        classification = "SPLIT"
    if len(targets) == 1:
        target = next(iter(targets))
    else:
        target = "A+B"
    rationale = "Commit contains: " + "; ".join(sorted({item["rationale"] for item in policies}))
    return classification, target, rationale


def _write_json(path: Path, value: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MigrationError(f"cannot write matrix {path}: {type(exc).__name__}", code="MATRIX_WRITE_FAILED") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MigrationError(f"matrix not found: {path}", code="MATRIX_NOT_FOUND") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"invalid matrix {path}: {type(exc).__name__}", status="FAIL", code="MATRIX_INVALID") from exc
    if not isinstance(value, dict):
        raise MigrationError(f"matrix must be an object: {path}", status="FAIL", code="MATRIX_INVALID")
    return value


def build_matrices(
    *,
    root: Path,
    base_ref: str = "origin/main",
    head_ref: str = "origin/codex/release-v1.1.0",
    output_dir: Path,
) -> dict[str, Any]:
    """Build the two complete matrices from explicit refs, never implicit HEAD."""

    base_sha = _ref_sha(root, base_ref)
    head_sha = _ref_sha(root, head_ref)
    if base_sha == head_sha:
        raise MigrationError("base and head resolve to the same commit", code="EMPTY_MIGRATION")
    merge_base = str(_git(root, "merge-base", base_ref, head_ref)).strip()
    if merge_base != base_sha:
        raise MigrationError(
            f"base is not the merge base; expected {base_sha}, got {merge_base}",
            code="BASE_DRIFT",
        )
    try:
        _git(root, "merge-base", "--is-ancestor", base_ref, head_ref)
    except MigrationError as exc:
        raise MigrationError("head is not a descendant of base", code="NON_LINEAR_MIGRATION") from exc

    commit_shas = [line for line in str(_git(root, "rev-list", "--reverse", "--topo-order", f"{base_ref}..{head_ref}")).splitlines() if line]
    commits: list[dict[str, Any]] = []
    for index, commit_sha in enumerate(commit_shas, start=1):
        parent_line = str(_git(root, "rev-list", "--parents", "-n", "1", commit_sha)).strip().split()
        parents = parent_line[1:]
        subject = str(_git(root, "show", "-s", "--format=%s", commit_sha)).strip()
        changed_paths = [
            line for line in str(_git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha)).splitlines() if line
        ]
        classification, target_pr, rationale = _commit_policy(changed_paths)
        patch = bytes(_git(root, "show", "--format=", "--no-ext-diff", "--no-color", commit_sha, binary=True))
        commits.append(
            {
                "sequence": index,
                "full_commit_sha": commit_sha,
                "parents": parents,
                "subject": subject,
                "changed_paths": sorted(changed_paths),
                "patch_id": sha256_bytes(patch),
                "classification": classification,
                "target_pr": target_pr,
                "rationale": rationale,
                "target_tests": ["matrix verification"],
                "source_preservation_location": "PR #2 history",
            }
        )

    statuses = [line.split("\t", 1) for line in str(_git(root, "diff", "--name-status", "--find-renames", f"{base_ref}..{head_ref}")).splitlines() if line]
    files: list[dict[str, Any]] = []
    for status_parts in statuses:
        status = status_parts[0]
        path = status_parts[-1]
        policy = _path_policy(path)
        diff = bytes(_git(root, "diff", "--no-ext-diff", "--no-color", base_ref, head_ref, "--", path, binary=True))
        origin_commits = [line for line in str(_git(root, "log", "--format=%H", f"{base_ref}..{head_ref}", "--", path)).splitlines() if line]
        files.append(
            {
                "path": path,
                "status": status,
                "base_blob_sha": _optional_blob(root, base_ref, path),
                "pr_head_blob_sha": _optional_blob(root, head_ref, path),
                "net_diff_sha256": sha256_bytes(diff),
                "originating_commits": origin_commits,
                "classification": policy["classification"],
                "target_path": path,
                "target_pr": policy["target_pr"],
                "required_validation": policy["required_validation"],
                "security_contract_notes": policy["security_contract_notes"],
            }
        )
    files.sort(key=lambda item: item["path"])

    commit_payload = {"base_sha": base_sha, "pr_head_sha": head_sha, "commits": commits}
    file_payload = {"base_sha": base_sha, "pr_head_sha": head_sha, "files": files}
    commit_matrix = {
        "schema_version": "governance.migration/v2",
        "kind": "commits",
        "base_ref": base_ref,
        "head_ref": head_ref,
        **commit_payload,
        "count": len(commits),
        "matrix_digest": sha256_canonical(commit_payload),
    }
    file_matrix = {
        "schema_version": "governance.migration/v2",
        "kind": "files",
        "base_ref": base_ref,
        "head_ref": head_ref,
        **file_payload,
        "count": len(files),
        "matrix_digest": sha256_canonical(file_payload),
    }
    commits_path = output_dir / "migration-commits.json"
    files_path = output_dir / "migration-files.json"
    _write_json(commits_path, commit_matrix)
    _write_json(files_path, file_matrix)
    return {
        "status": "PASS",
        "code": "MIGRATION_BUILT",
        "base_sha": base_sha,
        "pr_head_sha": head_sha,
        "commit_count": len(commits),
        "file_count": len(files),
        "commit_matrix": str(commits_path),
        "file_matrix": str(files_path),
    }


def _validate_matrix(matrix: dict[str, Any], *, kind: str) -> list[str]:
    errors: list[str] = []
    if matrix.get("schema_version") != "governance.migration/v2" or matrix.get("kind") != kind:
        errors.append("schema or kind mismatch")
    items_key = "commits" if kind == "commits" else "files"
    items = matrix.get(items_key)
    if not isinstance(items, list) or not items:
        errors.append(f"{items_key} must be a non-empty list")
        return errors
    if matrix.get("count") != len(items):
        errors.append("count mismatch")
    forbidden = [marker for marker in FORBIDDEN_MARKERS if marker in json.dumps(matrix, ensure_ascii=False)]
    if forbidden:
        errors.append("forbidden marker: " + ",".join(forbidden))
    classifications = {item.get("classification") for item in items if isinstance(item, dict)}
    if not classifications.issubset(VALID_CLASSIFICATIONS):
        errors.append("invalid classification")
    payload = {"base_sha": matrix.get("base_sha"), "pr_head_sha": matrix.get("pr_head_sha"), items_key: items}
    if matrix.get("matrix_digest") != sha256_canonical(payload):
        errors.append("matrix_digest mismatch")
    return errors


def verify_matrices(*, input_dir: Path) -> dict[str, Any]:
    """Verify both generated matrices and their self-digests."""

    try:
        commits = _read_json(input_dir / "migration-commits.json")
        files = _read_json(input_dir / "migration-files.json")
    except MigrationError as exc:
        return {"status": exc.status, "code": exc.code, "message": str(exc)}
    errors = _validate_matrix(commits, kind="commits") + _validate_matrix(files, kind="files")
    if commits.get("base_sha") != files.get("base_sha") or commits.get("pr_head_sha") != files.get("pr_head_sha"):
        errors.append("commit/file ref mismatch")
    if errors:
        return {"status": "FAIL", "code": "MIGRATION_INVALID", "errors": sorted(set(errors))}
    return {
        "status": "PASS",
        "code": "MIGRATION_VALID",
        "base_sha": commits["base_sha"],
        "pr_head_sha": commits["pr_head_sha"],
        "commit_count": commits["count"],
        "file_count": files["count"],
        "commit_matrix_digest": commits["matrix_digest"],
        "file_matrix_digest": files["matrix_digest"],
    }
