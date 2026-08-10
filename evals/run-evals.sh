#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

find_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
      "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      PYTHON=("$candidate")
      return 0
    fi
  done

  if command -v py >/dev/null 2>&1 && \
    py -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PYTHON=(py -3)
    return 0
  fi

  echo "evals: Python 3.11 or newer is required." >&2
  return 1
}

run_case() {
  local name="$1"
  shift
  if "${PYTHON[@]}" - "$REPO_ROOT" "$@" <<'PY'
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest.mock
import zipfile
from pathlib import Path


ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))


def run_python(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=cwd or ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def find_bash() -> str:
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
            discovered = None
        else:
            return discovered
    raise SystemExit("evals: bash is required")


def read_release_manifest(out_dir: Path) -> dict[str, object]:
    """Load the one release manifest and its exact publication digest."""

    manifest_paths = sorted(out_dir.glob("*.manifest.json"))
    if len(manifest_paths) != 1:
        raise SystemExit(
            f"evals: expected exactly one release manifest, found {len(manifest_paths)}"
        )

    manifest_path = manifest_paths[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    suffix = ".manifest.json"
    if not manifest_path.name.endswith(suffix):
        raise SystemExit("evals: unexpected release manifest name")

    release_stem = manifest_path.name[: -len(suffix)]
    digest_path = out_dir / f"{release_stem}.digest.txt"

    if not digest_path.is_file():
        raise SystemExit(
            f"evals: publication digest is missing: {digest_path.name}"
        )

    digest_text = digest_path.read_text(encoding="utf-8").strip()
    if digest_text != manifest["publication_digest"]:
        raise SystemExit("evals: digest file disagrees with the manifest")
    return manifest


def build_release(out_dir: Path) -> dict[str, object]:
    from tools.template_doctor.release_source import is_git_work_tree

    arguments = [
        "scripts/build-release.py",
        "--root",
        str(ROOT),
        "--out-dir",
        str(out_dir),
    ]
    if not is_git_work_tree(ROOT):
        # The eval may run inside a release extraction, which has no Git
        # work tree; the trusted-source gate then requires an explicit
        # unverified label.
        arguments.append("--allow-unverified")
    completed = run_python(*arguments)
    if completed.returncode != 0:
        raise SystemExit(
            f"evals: build-release failed: {completed.stderr.strip()[-400:]}"
        )
    return read_release_manifest(out_dir)


case = sys.argv[2] if len(sys.argv) > 2 else ""

if case == "doctor-root-smoke":
    first = run_python("-B", "-m", "tools.template_doctor", "--root", str(ROOT), "--format", "json")
    second = run_python("-B", "-m", "tools.template_doctor", "--root", str(ROOT), "--format", "json")
    if first.stdout != second.stdout or first.returncode != second.returncode:
        raise SystemExit("evals: doctor output is not deterministic")
    if first.returncode not in {0, 1}:
        raise SystemExit(f"evals: unexpected doctor exit {first.returncode}")
    report = json.loads(first.stdout)
    rule_ids = [item["rule_id"] for item in report["results"]]
    if rule_ids != sorted(rule_ids) or len(rule_ids) != len(set(rule_ids)):
        raise SystemExit("evals: doctor rule IDs are not unique and sorted")
    if len(rule_ids) < 18:
        raise SystemExit(f"evals: doctor rule count {len(rule_ids)} is below the contract floor")
    required = {"rule_id", "severity", "status", "evidence", "recommendation"}
    if any(not required.issubset(item) for item in report["results"]):
        raise SystemExit("evals: doctor result contract is missing fields")
    print(f"doctor-root-smoke rules={len(rule_ids)} exit={first.returncode}")

elif case == "run-guard-lifecycle":
    from tools.aiwf_run_guard.config import RunConfig
    from tools.aiwf_run_guard.gate import evaluate_gate
    from tools.aiwf_run_guard.ledger import append_event, initialize_run

    config = {
        "task_id": "EVAL-RUN-GUARD-001",
        "retry_limit": 1,
        "workstreams": [
            {
                "id": "core",
                "owner": "main",
                "owned_paths": ["tools/core"],
                "require_handoff": True,
            },
            {
                "id": "integration",
                "owner": "main",
                "owned_paths": [],
                "require_handoff": False,
            },
        ],
        "allowed_paths": ["docs", "tools"],
        "forbidden_paths": ["tools/core/secret"],
        "require_validation": True,
        "require_review": True,
        "first_artifact_seconds": None,
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        plan = root / "plan"
        plan.mkdir()
        source = root / "config.json"
        source.write_text(json.dumps(config), encoding="utf-8")
        initialize_run(plan, source)
        artifact = root / "tools/core/output.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("artifact\n", encoding="utf-8")
        append_event(plan, agent="main", workstream="core", kind="workstream_started")
        append_event(
            plan,
            agent="main",
            workstream="core",
            kind="artifact",
            files=["tools/core/output.txt"],
        )
        append_event(plan, agent="main", workstream="core", kind="handoff")
        append_event(plan, agent="main", workstream="integration", kind="workstream_started")
        append_event(plan, agent="main", workstream="integration", kind="validation_passed")
        append_event(plan, agent="main", workstream="integration", kind="review_passed")
        report = evaluate_gate(root, plan)
    if report.status != "ready" or report.exit_code != 0:
        raise SystemExit(f"evals: run-guard lifecycle gate not ready: {report.status}")
    print("run-guard-lifecycle gate=ready")

elif case == "run-guard-scope-rejection":
    from tools.aiwf_run_guard.ledger import append_event, initialize_run
    from tools.aiwf_run_guard.models import TransitionError

    config = {
        "task_id": "EVAL-RUN-GUARD-002",
        "retry_limit": 1,
        "workstreams": [
            {
                "id": "core",
                "owner": "main",
                "owned_paths": ["tools/core"],
                "require_handoff": True,
            }
        ],
        "allowed_paths": ["tools"],
        "forbidden_paths": [],
        "require_validation": False,
        "require_review": False,
        "first_artifact_seconds": None,
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        plan = root / "plan"
        plan.mkdir()
        source = root / "config.json"
        source.write_text(json.dumps(config), encoding="utf-8")
        initialize_run(plan, source)
        append_event(plan, agent="main", workstream="core", kind="workstream_started")
        try:
            append_event(
                plan,
                agent="main",
                workstream="core",
                kind="artifact",
                files=["docs/foreign.txt"],
            )
        except TransitionError:
            pass
        else:
            raise SystemExit("evals: out-of-scope artifact was not rejected")
    print("run-guard-scope-rejection rejected")

elif case == "run-guard-case-semantics":
    from tools.aiwf_run_guard.config import artifact_identity_key, path_matches_prefix

    with unittest.mock.patch("tools.aiwf_run_guard.config.os.name", "nt"):
        assert path_matches_prefix("tools/core/SECRET/token.txt", "tools/core/secret")
        assert artifact_identity_key("TOOLS/CORE/OUTPUT.TXT") == artifact_identity_key(
            "tools/core/output.txt"
        )
    with unittest.mock.patch("tools.aiwf_run_guard.config.os.name", "posix"):
        assert not path_matches_prefix("tools/core/SECRET/token.txt", "tools/core/secret")
        assert artifact_identity_key("TOOLS/CORE/OUTPUT.TXT") != artifact_identity_key(
            "tools/core/output.txt"
        )
    print("run-guard-case-semantics nt+posix verified")

elif case == "release-pollution-detection":
    with tempfile.TemporaryDirectory() as directory:
        manifest = build_release(Path(directory))
        paths = {item["path"] for item in manifest["files"]}
        forbidden = {".planning", ".mode", ".nonce", ".stop_blocks", ".active_plan"}
        hits = [
            path
            for path in paths
            if any(
                token in path
                or "__pycache__" in path
                or path.endswith((".pyc", ".pyo"))
                for token in forbidden
            )
        ]
        if hits:
            raise SystemExit(f"evals: release contains pollution: {sorted(hits)}")
        archive = next(Path(directory).glob("*.zip"))
        completed = run_python(
            "scripts/verify-release-archive.py",
            "--archive",
            str(archive),
            "--manifest",
            str(Path(directory) / f"{archive.stem}.manifest.json"),
        )
        if completed.returncode != 0:
            raise SystemExit(f"evals: verifier rejected clean release: {completed.stderr.strip()[-400:]}")
    print(f"release-pollution-detection files={len(paths)} clean")

elif case == "release-determinism":
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        def write_manifest(
            target: Path,
            *,
            name: str = "template-advanced-regression.manifest.json",
            digest: str = "publication-digest",
        ) -> None:
            (target / name).write_text(
                json.dumps({"publication_digest": digest}),
                encoding="utf-8",
            )

        def require_metadata_failure(target: Path, expected: str) -> None:
            try:
                read_release_manifest(target)
            except SystemExit as exc:
                if expected not in str(exc):
                    raise SystemExit(
                        "evals: release metadata failure did not match: "
                        f"expected {expected!r}, got {str(exc)!r}"
                    ) from exc
            else:
                raise SystemExit(
                    f"evals: release metadata unexpectedly passed: {expected}"
                )

        metadata_failures = (
            (
                "missing-manifest",
                (),
                None,
                "expected exactly one release manifest, found 0",
            ),
            (
                "duplicate-manifest",
                ("first.manifest.json", "second.manifest.json"),
                None,
                "expected exactly one release manifest, found 2",
            ),
            (
                "missing-digest",
                ("template-advanced-regression.manifest.json",),
                None,
                "publication digest is missing: template-advanced-regression.digest.txt",
            ),
            (
                "digest-mismatch",
                ("template-advanced-regression.manifest.json",),
                "different-digest",
                "digest file disagrees with the manifest",
            ),
        )
        for name, manifest_names, digest_text, expected in metadata_failures:
            target = root / name
            target.mkdir()
            for manifest_name in manifest_names:
                write_manifest(target, name=manifest_name)
            if digest_text is not None:
                (target / "template-advanced-regression.digest.txt").write_text(
                    f"{digest_text}\n",
                    encoding="utf-8",
                )
            require_metadata_failure(target, expected)

        payload_decoy = root / "payload-decoy"
        payload_decoy.mkdir()
        write_manifest(payload_decoy)
        (payload_decoy / "template-advanced-regression.payload.digest.txt").write_text(
            "payload-digest\n",
            encoding="utf-8",
        )
        (payload_decoy / "template-advanced-regression.digest.txt").write_text(
            "publication-digest\n",
            encoding="utf-8",
        )
        if (
            read_release_manifest(payload_decoy)["publication_digest"]
            != "publication-digest"
        ):
            raise SystemExit("evals: payload digest decoy replaced publication digest")
        print("release-determinism metadata-regressions=5 passed")

        first_dir = root / "first"
        second_dir = root / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        first = build_release(first_dir)
        second = build_release(second_dir)
        first_zip = next(first_dir.glob("*.zip"))
        second_zip = next(second_dir.glob("*.zip"))
        import hashlib

        first_bytes = hashlib.sha256(first_zip.read_bytes()).hexdigest()
        second_bytes = hashlib.sha256(second_zip.read_bytes()).hexdigest()
        if (
            first != second
            or first_bytes != second_bytes
            or first["publication_digest"] != second["publication_digest"]
        ):
            raise SystemExit("evals: release build is not deterministic")
    print(f"release-determinism files={first['file_count']} digest-stable")

elif case == "doctor-drift-detection":
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / "drifted"
        control = fixture / "docs" / "control"
        control.mkdir(parents=True)
        (fixture / "README.md").write_text(
            "Local path leaked: C:\\Users\\owner\\Temp\\codex-template-advanced-publication-v16-20260801\n",
            encoding="utf-8",
        )
        (control / "NEXT_CODEX_TASK.md").write_text(
            "Task ID: TEMPLATE-ONBOARDING-V1\nWorkflow Mode: Lite\n",
            encoding="utf-8",
        )
        (control / "CURRENT_PROJECT_STATE.md").write_text(
            "Last Updated: 2026-08-01\nIs state stale?: no\n",
            encoding="utf-8",
        )
        completed = run_python(
            "-B", "-m", "tools.template_doctor", "--root", str(fixture), "--format", "json"
        )
        if completed.returncode not in {1}:
            raise SystemExit("evals: drifted fixture must exit 1")
        report = json.loads(completed.stdout)
        drift = [
            item
            for item in report["results"]
            if item["rule_id"] in {"control.no_local_state", "control.numeric_status_claims"}
            and item["status"] == "fail"
        ]
        if not drift:
            raise SystemExit("evals: Doctor did not detect state drift")
    print(f"doctor-drift-detection rules={len(drift)} detected")

elif case == "clean-template-init":
    with tempfile.TemporaryDirectory() as directory:
        manifest = build_release(Path(directory) / "build")
        archive = next((Path(directory) / "build").glob("*.zip"))
        extracted = Path(directory) / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive, mode="r") as handle:
            handle.extractall(extracted)
        bash = find_bash()
        setup = subprocess.run(
            [bash, "scripts/setup.sh"],
            cwd=extracted,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if setup.returncode != 0:
            raise SystemExit(f"evals: clean setup failed: {setup.stderr.strip()[-400:]}")
        doctor = subprocess.run(
            [sys.executable, "-B", "-m", "tools.template_doctor", "--root", ".", "--format", "json"],
            cwd=extracted,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if doctor.returncode not in {0, 1}:
            raise SystemExit(f"evals: clean doctor exit {doctor.returncode}")
        report = json.loads(doctor.stdout)
        failed = {
            item["rule_id"]
            for item in report["results"]
            if item["status"] == "fail"
        }
        errors = report["summary"].get("errors", 0)
        from tools.template_doctor.policy import RELEASE_EXTRACTION_ALLOWED_FAILURES

        allowed = RELEASE_EXTRACTION_ALLOWED_FAILURES
        if not failed.issubset(allowed) or errors:
            raise SystemExit(
                f"evals: clean template has unexpected findings {sorted(failed)} errors={errors}"
            )
        with zipfile.ZipFile(archive, mode="r") as handle:
            names = handle.namelist()
        runtime_state = [
            name
            for name in names
            if ".planning" in name or name.startswith((".mode", ".nonce", ".stop_blocks"))
        ]
        if runtime_state:
            raise SystemExit(f"evals: archive contains runtime state: {runtime_state}")
    print("clean-template-init extracted and initialized")

else:
    raise SystemExit(f"evals: unknown case {case!r}")
PY
  then
    echo "evals: passed (case=$name)"
  else
    local status=$?
    echo "evals: FAILED case=$name exit=$status" >&2
    exit 1
  fi
}

find_python
export PYTHONDONTWRITEBYTECODE=1
cd "$REPO_ROOT"

run_case doctor-root-smoke doctor-root-smoke
run_case run-guard-lifecycle run-guard-lifecycle
run_case run-guard-scope-rejection run-guard-scope-rejection
run_case run-guard-case-semantics run-guard-case-semantics
run_case release-pollution-detection release-pollution-detection
run_case release-determinism release-determinism
run_case doctor-drift-detection doctor-drift-detection
run_case clean-template-init clean-template-init

echo "evals: all 8 cases passed"
