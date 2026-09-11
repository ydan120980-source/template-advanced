"""Contract tests for the workflow_eval tooling.

Trust rules under test:

- trials are Git-isolated (single-commit snapshot repo, verified toplevel),
  and isolation is re-verified at grading time: a trial that lost its `.git`
  would otherwise let Git discovery resolve to the source repository and
  expose the fixed files, so such a run is refused instead of graded;
- the scope baseline lives with the coordinator, outside the candidate;
- grading never writes into the candidate repository: real-entry builds run
  against an acceptor-owned staging copy, so an ordinary root-level user
  repository handed in as a candidate keeps its HEAD, index, and worktree;
- snapshot export uses platform-appropriate path semantics (the Windows
  extended-length prefix would otherwise produce relative POSIX paths) and
  fails when the extracted file set does not match the committed tree;
- frozen acceptors reject each pre-fix tree on target defects and accept
  each historical fix with executed scenarios (explicit integration: only
  runs where the locked historical commits are reachable);
- deliberately wrong implementations — including ones that pass the
  isolated selection block but are not wired into the real entry, or that
  return the payload digest — are rejected;
- manifests inside the candidate tree, with mismatched identity, without a
  candidate path, or with a SHA that is not a baseline locked for the task
  are refused;
- report output states evidence completeness and consistency instead of
  counting filled slots: contradictory verdicts, REJECT records with no
  failing scenario, freeze evidence from the wrong revision, and negative
  budgets are all flagged.

Ordinary tests are self-contained (synthetic repositories and synthetic
task definitions), so shallow clones, fresh verification repositories, and
release packages can run the suite without repository history.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PosixPath, PureWindowsPath, WindowsPath
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.workflow_eval import prepare as prepare_module  # noqa: E402
from tools.workflow_eval.acceptors import accept_publication_digest  # noqa: E402
from tools.workflow_eval.audit import audit_session  # noqa: E402
from tools.workflow_eval.grade import grade_trial  # noqa: E402
from tools.workflow_eval.prepare import (  # noqa: E402
    PrepareError,
    _export_target,
    export_commit_tree,
    prepare_trial,
    trial_isolation_problem,
)
from tools.workflow_eval.report import write_report  # noqa: E402
from tools.workflow_eval.tasks import TASK_ORDER, TASKS, TaskDefinition  # noqa: E402


def _run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=60,
    )


def _source_repo() -> Path:
    """Return the repository that holds the locked historical commits.

    In a full checkout (and in CI with full history) that is this
    repository itself; in an isolated single-commit verification repository
    the coordinator points ``WORKFLOW_EVAL_SOURCE_REPO`` at the full source
    repository instead.
    """

    override = os.environ.get("WORKFLOW_EVAL_SOURCE_REPO", "")
    if override.strip():
        return Path(override.strip())
    return REPO_ROOT


def _locked_history_available() -> bool:
    for task in TASKS.values():
        for sha in (task.pre_fix_sha, task.fix_sha):
            completed = _run_git(_source_repo(), "rev-parse", "--verify", f"{sha}^{{commit}}")
            if completed.returncode != 0:
                return False
    return True


def _make_synthetic_source_repo(root: Path) -> tuple[Path, str]:
    """Create a one-commit Git repository as a self-contained source."""

    repo = root / "synthetic-src"
    repo.mkdir(parents=True)
    (repo / "file.txt").write_text("synthetic\n", encoding="utf-8")
    for arguments in (["init", "--initial-branch=main"], ["add", "-A", "--"]):
        completed = _run_git(repo, *arguments)
        if completed.returncode != 0:
            raise AssertionError(f"git {arguments[0]} failed: {completed.stderr.strip()}")
    completed = _run_git(
        repo,
        "-c",
        "user.name=Synthetic Source",
        "-c",
        "user.email=synthetic@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "synthetic baseline",
    )
    if completed.returncode != 0:
        raise AssertionError(f"git commit failed: {completed.stderr.strip()}")
    sha = _run_git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, sha


def _make_synthetic_task(sha: str) -> TaskDefinition:
    return TaskDefinition(
        task_id="synthetic-isolation",
        title="Synthetic isolation task",
        pre_fix_sha=sha,
        fix_sha=sha,
        allowed_paths=("README.md",),
        brief_goal="synthetic",
        brief_contract=("synthetic contract",),
        brief_acceptance=("synthetic acceptance",),
        brief_context="synthetic context",
    )


def _write_manifest(
    path: Path,
    *,
    task_id: str,
    group: str,
    trial_dir: Path,
    source_sha: str,
    file_manifest: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(
                {
                    "record_type": "trusted_trial_manifest",
                    "task_id": task_id,
                    "group": group,
                    "run_label": path.stem,
                    "trial_dir": str(trial_dir),
                    "source_sha": source_sha,
                    "file_manifest": file_manifest,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    )


def _hash_tree(root: Path) -> dict[str, str]:
    file_manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        file_manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return file_manifest


def _export_fixed_tree(sha: str, destination: Path) -> dict[str, str]:
    destination.mkdir(parents=True, exist_ok=True)
    export_commit_tree(_source_repo(), sha, destination)
    return _hash_tree(destination)


_WRONG_PUBLICATION_PAYLOAD_PREFERENCE = """\
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
if python -B - "$REPO_ROOT" "$@" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


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


def build_release(out_dir: Path) -> dict[str, object]:
    completed = run_python(
        "scripts/build-release.py", "--root", str(ROOT), "--out-dir", str(out_dir)
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"evals: build-release failed: {completed.stderr.strip()[-400:]}"
        )
    manifest_paths = sorted(out_dir.glob("*.manifest.json"))
    if len(manifest_paths) != 1:
        raise SystemExit(
            f"evals: expected exactly one release manifest, found {len(manifest_paths)}"
        )
    manifest_path = manifest_paths[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    release_stem = manifest_path.name[: -len(".manifest.json")]
    payload_digest_path = out_dir / f"{release_stem}.payload.digest.txt"
    if payload_digest_path.is_file():
        # WRONG implementation: prefers the payload digest decoy.
        manifest["publication_digest"] = payload_digest_path.read_text(
            encoding="utf-8"
        ).strip()
        return manifest
    digest_path = out_dir / f"{release_stem}.digest.txt"
    digest_text = digest_path.read_text(encoding="utf-8").strip()
    if digest_text != manifest["publication_digest"]:
        raise SystemExit("evals: digest file disagrees with the manifest")
    return manifest

case = sys.argv[2] if len(sys.argv) > 2 else ""
if case == "__acceptor_probe__":
    pass
else:
    raise SystemExit(f"evals: unknown case {case!r}")
PY
then
  :
fi
"""

_WRONG_PUBLICATION_EARLY_RETURN = """\
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
if python -B - "$REPO_ROOT" "$@" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


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


def build_release(out_dir: Path) -> dict[str, object]:
    # WRONG implementation: returns before building or selecting anything.
    # The correct-looking selection block below is orphaned, unwired code.
    if True:
        return {"publication_digest": "tampered"}
    manifest_paths = sorted(out_dir.glob("*.manifest.json"))
    if len(manifest_paths) != 1:
        raise SystemExit(
            f"evals: expected exactly one release manifest, found {len(manifest_paths)}"
        )
    manifest_path = manifest_paths[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    release_stem = manifest_path.name[: -len(".manifest.json")]
    digest_path = out_dir / f"{release_stem}.digest.txt"
    digest_text = digest_path.read_text(encoding="utf-8").strip()
    if digest_text != manifest["publication_digest"]:
        raise SystemExit("evals: digest file disagrees with the manifest")
    return manifest

case = sys.argv[2] if len(sys.argv) > 2 else ""
if case == "__acceptor_probe__":
    pass
else:
    raise SystemExit(f"evals: unknown case {case!r}")
PY
then
  :
fi
"""

_EXCLUDED_COPY_DIRS = {
    ".git",
    ".planning",
    ".workbuddy",
    "__pycache__",
    ".aiwf",
    ".claude",
    ".codegraph",
    "dist",
    ".codex",
    "node_modules",
}


def _make_publication_candidate(base: Path, name: str, evals_sh: str) -> Path:
    """Build a full candidate tree from the current working tree files.

    Self-contained: only tracked working-tree content is copied (no Git
    history), then the eval script is replaced with the variant under test.
    """

    candidate = base / name
    for source_path in REPO_ROOT.rglob("*"):
        relative_parts = source_path.relative_to(REPO_ROOT).parts
        if any(part in _EXCLUDED_COPY_DIRS for part in relative_parts):
            continue
        target = candidate.joinpath(*relative_parts)
        if source_path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source_path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
    evals_script = candidate / "evals" / "run-evals.sh"
    evals_script.write_bytes(evals_sh.encode("utf-8"))
    return candidate


class PrepareIsolationTests(unittest.TestCase):
    def test_prepare_creates_git_isolated_trial_with_external_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            source_repo, sha = _make_synthetic_source_repo(out_root / "source")
            task = _make_synthetic_task(sha)
            prepared = prepare_trial(
                source_repo=source_repo,
                task=task,
                group="control",
                out_root=out_root / "trials-root",
                run_label="unit",
            )
            trial_dir = Path(str(prepared["trial_dir"]))

            self.assertTrue((trial_dir / "instructions.md").is_file())
            metadata_text = (trial_dir / "trial-metadata.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(str(source_repo), metadata_text)
            metadata = json.loads(metadata_text)
            self.assertNotIn("file_manifest", metadata)
            self.assertNotIn("source_sha", metadata)

            manifest_path = Path(str(prepared["trusted_manifest_path"]))
            self.assertFalse(manifest_path.resolve().is_relative_to(trial_dir.resolve()))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("file.txt", manifest["file_manifest"])

            toplevel = _run_git(trial_dir, "rev-parse", "--show-toplevel")
            self.assertEqual(toplevel.returncode, 0, toplevel.stderr)
            self.assertEqual(
                os.path.normcase(os.path.abspath(toplevel.stdout.strip())),
                os.path.normcase(os.path.abspath(str(trial_dir))),
            )
            log = _run_git(trial_dir, "log", "--oneline")
            self.assertEqual(len(log.stdout.strip().splitlines()), 1)


class FreezeAcceptanceTests(unittest.TestCase):
    """Explicit integration validation over the locked historical commits.

    Skipped — with a stated reason — in environments without the history
    (shallow clones, fresh verification repositories, release packages);
    run it explicitly with ``WORKFLOW_EVAL_SOURCE_REPO`` pointing at the
    full source repository.
    """

    def setUp(self) -> None:
        if not _locked_history_available():
            self.skipTest(
                "locked historical commits are unreachable from "
                f"{_source_repo()}; set WORKFLOW_EVAL_SOURCE_REPO to the full "
                "source repository to run the freeze integration validation"
            )

    def test_acceptors_reject_prefix_trees_and_accept_historical_fixes(self) -> None:
        for task_id in TASK_ORDER:
            with self.subTest(task=task_id):
                task = TASKS[task_id]
                with tempfile.TemporaryDirectory() as temporary_directory:
                    out_root = Path(temporary_directory)
                    prepared = prepare_trial(
                        source_repo=_source_repo(),
                        task=task,
                        group="control",
                        out_root=out_root,
                        run_label="freeze",
                    )
                    manifest_path = Path(str(prepared["trusted_manifest_path"]))
                    pre_record = grade_trial(
                        task=task,
                        candidate_root=Path(str(prepared["trial_dir"])),
                        results_dir=out_root / "results",
                        label="freeze-pre",
                        group="control",
                        trial_dir=Path(str(prepared["trial_dir"])),
                        run_kind="freeze",
                        manifest_path=manifest_path,
                    )
                self.assertEqual(pre_record["verdict"], "REJECT")
                self.assertEqual(pre_record["acceptor"]["acceptor_status"], "OK")
                self.assertTrue(
                    any(not item["pass"] for item in pre_record["acceptor"]["scenarios"])
                )

                with tempfile.TemporaryDirectory() as temporary_directory:
                    out_root = Path(temporary_directory)
                    fixed_tree = out_root / "fixed"
                    file_manifest = _export_fixed_tree(task.fix_sha, fixed_tree)
                    manifest_path = out_root / "manifest.json"
                    _write_manifest(
                        manifest_path,
                        task_id=task_id,
                        group="control",
                        trial_dir=fixed_tree,
                        source_sha=task.fix_sha,
                        file_manifest=file_manifest,
                    )
                    fixed_record = grade_trial(
                        task=task,
                        candidate_root=fixed_tree,
                        results_dir=out_root / "results",
                        label="freeze-fixed",
                        group="control",
                        trial_dir=fixed_tree,
                        run_kind="freeze",
                        manifest_path=manifest_path,
                    )
                self.assertEqual(fixed_record["verdict"], "ACCEPT")
                self.assertEqual(fixed_record["acceptor"]["acceptor_status"], "OK")
                self.assertTrue(
                    all(item["pass"] for item in fixed_record["acceptor"]["scenarios"])
                )

    def test_prepared_trial_scores_pre_fix_tree_as_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            task = TASKS["bootstrap-refs"]
            prepared = prepare_trial(
                source_repo=_source_repo(),
                task=task,
                group="experiment",
                out_root=out_root,
                run_label="unit",
            )
            manifest_path = Path(str(prepared["trusted_manifest_path"]))
            record = grade_trial(
                task=task,
                candidate_root=Path(str(prepared["trial_dir"])),
                results_dir=out_root / "results",
                label="unit",
                group="experiment",
                trial_dir=Path(str(prepared["trial_dir"])),
                run_kind="trial",
                manifest_path=manifest_path,
                budget={"elapsed_seconds": 1.0, "shell_requests": 0, "human_interventions": "none"},
            )

        self.assertEqual(record["verdict"], "REJECT")
        self.assertEqual(record["acceptor"]["acceptor_status"], "OK")
        failed = [
            item["name"]
            for item in record["acceptor"]["scenarios"]
            if not item["pass"]
        ]
        self.assertIn("missing-refs-cached-not-raised", failed)


class WrongImplementationTests(unittest.TestCase):
    def test_wrong_bootstrap_status_codes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            candidate = out_root / "candidate"
            package = candidate / "tools" / "governance_v2"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "canonical.py").write_text(
                (REPO_ROOT / "tools" / "governance_v2" / "canonical.py").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            (package / "bootstrap.py").write_text(
                "import subprocess as _subprocess_module\n"
                "subprocess = _subprocess_module\n"
                "\n"
                "\n"
                "class BootstrapError(RuntimeError):\n"
                "    def __init__(self, message, *, status='BLOCKED', code='BOOTSTRAP_FAILED'):\n"
                "        super().__init__(message)\n"
                "        self.status = status\n"
                "        self.code = code\n"
                "\n"
                "\n"
                "def snapshot(**kwargs):\n"
                "    return {'status': 'WRONG', 'code': 'WRONG', 'local_git_status': 'WRONG'}\n",
                encoding="utf-8",
            )
            manifest_path = out_root / "manifest.json"
            _write_manifest(
                manifest_path,
                task_id="bootstrap-refs",
                group="control",
                trial_dir=candidate,
                source_sha=TASKS["bootstrap-refs"].pre_fix_sha,
                file_manifest=_hash_tree(candidate),
            )
            record = grade_trial(
                task=TASKS["bootstrap-refs"],
                candidate_root=candidate,
                results_dir=out_root / "results",
                label="wrong-impl",
                group="control",
                trial_dir=candidate,
                run_kind="freeze",
                manifest_path=manifest_path,
            )

        self.assertEqual(record["verdict"], "REJECT")
        self.assertEqual(record["acceptor"]["acceptor_status"], "OK")
        failed = {
            item["name"]
            for item in record["acceptor"]["scenarios"]
            if not item["pass"]
        }
        self.assertIn("missing-refs-cached-not-raised", failed)
        self.assertIn("baseline-drift-blocked", failed)

    def test_wrong_publication_impl_preferring_payload_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            candidate = _make_publication_candidate(
                out_root, "payload-preference", _WRONG_PUBLICATION_PAYLOAD_PREFERENCE
            )
            manifest_path = out_root / "manifest.json"
            _write_manifest(
                manifest_path,
                task_id="publication-digest",
                group="control",
                trial_dir=candidate,
                source_sha=TASKS["publication-digest"].pre_fix_sha,
                file_manifest=_hash_tree(candidate),
            )
            record = grade_trial(
                task=TASKS["publication-digest"],
                candidate_root=candidate,
                results_dir=out_root / "results",
                label="wrong-impl",
                group="control",
                trial_dir=candidate,
                run_kind="freeze",
                manifest_path=manifest_path,
            )

        self.assertEqual(record["verdict"], "REJECT")
        failed = {
            item["name"]
            for item in record["acceptor"]["scenarios"]
            if not item["pass"]
        }
        # The value assertion catches the decoy preference in the isolated
        # block AND through the real entry.
        self.assertIn("payload-decoy-ignored", failed)
        self.assertIn("real-entry-wired", failed)
        self.assertIn("real-entry-decoy-ignored", failed)

    def test_wrong_publication_impl_with_unwired_early_return_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            candidate = _make_publication_candidate(
                out_root, "early-return", _WRONG_PUBLICATION_EARLY_RETURN
            )
            manifest_path = out_root / "manifest.json"
            _write_manifest(
                manifest_path,
                task_id="publication-digest",
                group="control",
                trial_dir=candidate,
                source_sha=TASKS["publication-digest"].pre_fix_sha,
                file_manifest=_hash_tree(candidate),
            )
            record = grade_trial(
                task=TASKS["publication-digest"],
                candidate_root=candidate,
                results_dir=out_root / "results",
                label="wrong-impl",
                group="control",
                trial_dir=candidate,
                run_kind="freeze",
                manifest_path=manifest_path,
            )

        self.assertEqual(record["verdict"], "REJECT")
        failed = {
            item["name"]
            for item in record["acceptor"]["scenarios"]
            if not item["pass"]
        }
        # The isolated block scenarios can pass for the orphaned correct
        # block, but the real-entry wiring scenarios fail.
        self.assertIn("real-entry-wired", failed)
        self.assertIn("real-entry-decoy-ignored", failed)


class TrialIsolationRegressionTests(unittest.TestCase):
    """A trial that lost its Git metadata must never produce trial evidence.

    Observed failure mode: a trial session removed the trial directory's
    ``.git``, so ``git rev-parse HEAD`` resolved to the enclosing source
    repository and ``git show HEAD:<path>`` returned the already-fixed
    upstream file, while the candidate tree still looked intact. Grading must
    therefore re-verify isolation instead of trusting preparation.
    """

    @staticmethod
    def _prepared(
        out_root: Path,
    ) -> tuple[TaskDefinition, Path, Path]:
        source_repo, sha = _make_synthetic_source_repo(out_root / "source")
        task = _make_synthetic_task(sha)
        prepared = prepare_trial(
            source_repo=source_repo,
            task=task,
            group="control",
            out_root=out_root / "trials-root",
            run_label="unit",
        )
        return (
            task,
            Path(str(prepared["trial_dir"])),
            Path(str(prepared["trusted_manifest_path"])),
        )

    @staticmethod
    def _detach_repository(trial_dir: Path) -> None:
        """Reproduce the incident: the trial loses its own Git metadata.

        Renaming is used rather than deleting because Git object files are
        read-only on Windows, and because the failure mode under test is the
        *absence* of ``.git`` — which is what makes Git discovery walk up to
        the enclosing repository.
        """

        (trial_dir / ".git").rename(trial_dir.parent / f"{trial_dir.name}--git-detached")

    def test_isolation_probe_accepts_a_prepared_trial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            trial_dir, _ = TrialIsolationRegressionTests._prepared(
                Path(temporary_directory)
            )[1:]
            self.assertIsNone(trial_isolation_problem(trial_dir))

    def test_isolation_probe_reports_a_trial_that_lost_its_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            trial_dir = TrialIsolationRegressionTests._prepared(
                Path(temporary_directory)
            )[1]
            TrialIsolationRegressionTests._detach_repository(trial_dir)
            problem = trial_isolation_problem(trial_dir)

        self.assertIsNotNone(problem)
        self.assertIn(".git", problem)

    def test_grading_refuses_a_trial_that_lost_its_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            task, trial_dir, manifest_path = (
                TrialIsolationRegressionTests._prepared(out_root)
            )
            TrialIsolationRegressionTests._detach_repository(trial_dir)

            with self.assertRaises(Exception) as caught:
                grade_trial(
                    task=task,
                    candidate_root=trial_dir,
                    results_dir=out_root / "results",
                    label="unit",
                    group="control",
                    trial_dir=trial_dir,
                    run_kind="trial",
                    manifest_path=manifest_path,
                    budget={
                        "elapsed_seconds": 1.0,
                        "shell_requests": 1,
                        "human_interventions": "none",
                    },
                )
            recorded = sorted((out_root / "results").glob("*.json"))

        self.assertIn("not Git-isolated", str(caught.exception))
        # A refused run must not leave a grade record behind.
        self.assertEqual(recorded, [])

    def test_isolated_trial_records_positive_isolation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            task, trial_dir, manifest_path = (
                TrialIsolationRegressionTests._prepared(out_root)
            )
            record = grade_trial(
                task=task,
                candidate_root=trial_dir,
                results_dir=out_root / "results",
                label="unit",
                group="control",
                trial_dir=trial_dir,
                run_kind="trial",
                manifest_path=manifest_path,
                budget={
                    "elapsed_seconds": 1.0,
                    "shell_requests": 1,
                    "human_interventions": "none",
                },
            )

        self.assertIs(record["trial_isolated"], True)


class TrialValidityAttestationTests(unittest.TestCase):
    """Trial validity is coordinator-authored and defaults to UNVERIFIED.

    A grade record says what the candidate did. It must never imply the run
    was a valid independent trial, and a trial agent must not be able to
    certify its own run: the attestation has to cite the audit it rests on.
    """

    @staticmethod
    def _grade(out_root: Path, **overrides: object) -> dict[str, object]:
        source_repo, sha = _make_synthetic_source_repo(out_root / "source")
        task = _make_synthetic_task(sha)
        prepared = prepare_trial(
            source_repo=source_repo,
            task=task,
            group="control",
            out_root=out_root / "trials-root",
            run_label="unit",
        )
        trial_dir = Path(str(prepared["trial_dir"]))
        manifest_path = Path(str(prepared["trusted_manifest_path"]))
        arguments: dict[str, object] = {
            "task": task,
            "candidate_root": trial_dir,
            "results_dir": out_root / "results",
            "label": "unit",
            "group": "control",
            "trial_dir": trial_dir,
            "run_kind": "trial",
            "manifest_path": manifest_path,
            "budget": {
                "elapsed_seconds": 1.0,
                "shell_requests": 1,
                "human_interventions": "none",
            },
        }
        arguments.update(overrides)
        return grade_trial(**arguments)  # type: ignore[arg-type]

    def test_trial_without_attestation_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            record = self._grade(Path(temporary_directory))

        self.assertEqual(record["trial_validity"]["status"], "UNVERIFIED")
        self.assertIs(record["trial_isolated"], True)
        # The Git probe is recorded with its narrow scope stated explicitly.
        check = record["trial_isolation_check"]
        self.assertTrue(check["passed"])
        self.assertIn("not evidence of read isolation", check["scope"])

    def test_attestation_requires_a_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(Exception) as caught:
                self._grade(
                    Path(temporary_directory),
                    validity={"status": "VALID", "audit_record": "audit.json"},
                )

        self.assertIn("non-empty basis", str(caught.exception))

    def test_valid_attestation_must_cite_an_audit_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(Exception) as caught:
                self._grade(
                    Path(temporary_directory),
                    validity={"status": "VALID", "basis": "looks fine"},
                )

        self.assertIn("must cite the coordinator audit record", str(caught.exception))

    def test_valid_attestation_is_recorded_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            session_record = out_root / "session.jsonl"
            session_record.write_text("{}\n", encoding="utf-8")
            # Windows text mode adds a carriage return to the on-disk bytes.
            expected_sha = hashlib.sha256(session_record.read_bytes()).hexdigest()
            record = self._grade(
                out_root,
                validity={
                    "status": "VALID",
                    "basis": "audited: no out-of-trial access",
                    "audit_record": str(out_root / "audit.json"),
                    "session_record": str(session_record),
                    "checked_channels": ["Bash", "Read", "Grep"],
                },
            )

        validity = record["trial_validity"]
        self.assertEqual(validity["status"], "VALID")
        self.assertEqual(validity["basis"], "audited: no out-of-trial access")
        self.assertEqual(validity["checked_channels"], ["Bash", "Read", "Grep"])
        self.assertEqual(validity["session_record_sha256"], expected_sha)

    def test_freeze_records_cannot_carry_trial_validity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(Exception) as caught:
                self._grade(
                    Path(temporary_directory),
                    run_kind="freeze",
                    validity={
                        "status": "VALID",
                        "basis": "x",
                        "audit_record": "audit.json",
                    },
                )

        self.assertIn("only defined for run_kind='trial'", str(caught.exception))


class SessionAuditTests(unittest.TestCase):
    """The audit must cover every tool channel, not only shell calls."""

    @staticmethod
    def _session(path: Path, events: list[dict]) -> Path:
        path.write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )
        return path

    def test_read_channel_leak_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            trial = out_root / "trial"
            source = out_root / "source-repo"
            trial.mkdir()
            source.mkdir()
            session = self._session(
                out_root / "session.jsonl",
                [
                    {
                        "type": "function_call",
                        "name": "Read",
                        "callId": "c1",
                        "timestamp": 1789041306839,
                        "cwd": str(source),
                        "arguments": json.dumps(
                            {"file_path": str(source / "evals" / "run-evals.sh")}
                        ),
                    },
                    {
                        "type": "function_call",
                        "name": "Read",
                        "callId": "c2",
                        "timestamp": 1789041306840,
                        "cwd": str(source),
                        "arguments": json.dumps(
                            {"file_path": str(trial / "instructions.md")}
                        ),
                    },
                ],
            )
            audit = audit_session(session, trial_dir=trial, source_repo=source)

        self.assertEqual(audit["shell_requests"], 0)
        # The Read channel, not Bash, is what caught this leak.
        self.assertEqual(len(audit["source_repo_accesses"]), 1)
        self.assertEqual(audit["source_repo_accesses"][0]["tool"], "Read")
        self.assertEqual(audit["audited_channels"], ["Read"])

    def test_pathless_grep_is_reported_against_the_default_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            trial = out_root / "trial"
            source = out_root / "source-repo"
            trial.mkdir()
            source.mkdir()
            session = self._session(
                out_root / "session.jsonl",
                [
                    {
                        "type": "function_call",
                        "name": "Grep",
                        "callId": "c1",
                        "timestamp": 1789041306839,
                        "cwd": str(source),
                        "arguments": json.dumps(
                            {"pattern": "digest", "glob": "scripts/build-release.py"}
                        ),
                    }
                ],
            )
            audit = audit_session(session, trial_dir=trial, source_repo=source)

        self.assertEqual(len(audit["calls_without_explicit_path"]), 1)
        self.assertEqual(audit["calls_without_explicit_path"][0]["tool"], "Grep")

    def test_anchored_git_command_is_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            trial = out_root / "trial"
            source = out_root / "source-repo"
            trial.mkdir()
            source.mkdir()
            session = self._session(
                out_root / "session.jsonl",
                [
                    {
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "c1",
                        "timestamp": 1789041306839,
                        "cwd": str(source),
                        "arguments": json.dumps(
                            {"command": f'cd "{trial}" && git status --short'}
                        ),
                    }
                ],
            )
            audit = audit_session(session, trial_dir=trial, source_repo=source)

        self.assertEqual(audit["git_commands_without_trial_anchor"], [])
        self.assertEqual(audit["shell_requests"], 1)

    def test_shell_count_matches_the_frozen_run_guard_parser(self) -> None:
        """Two independent implementations must agree on the same fixture.

        ``tools.workflow_eval`` stays standard-library-only, so it carries its
        own copy of the classification rules. This pins the copy against the
        frozen Run Guard parser the coordinator reports budgets from.
        """

        from datetime import datetime, timezone

        from tools.aiwf_run_guard.budget import _session_shell_call_ids

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            trial = out_root / "trial"
            trial.mkdir()
            session = self._session(
                out_root / "session.jsonl",
                [
                    {
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "shell-1",
                        "timestamp": 1789041306839,
                        "arguments": json.dumps({"command": "ls"}),
                    },
                    {
                        "type": "function_call",
                        "name": "Read",
                        "callId": "read-1",
                        "timestamp": 1789041306840,
                        "arguments": json.dumps({"file_path": str(trial / "a.md")}),
                    },
                    {
                        "type": "response_item",
                        "timestamp": 1789041306841,
                        "payload": {
                            "type": "custom_tool_call",
                            "call_id": "shell-2",
                            "input": "const r = await tools.exec_command({cmd:'ls'});",
                        },
                    },
                    {
                        "type": "response_item",
                        "timestamp": 1789041306842,
                        "payload": {
                            "type": "custom_tool_call",
                            "call_id": "not-shell",
                            "input": "const note = 'tools.exec_command is the host form';",
                        },
                    },
                ],
            )
            audit = audit_session(session, trial_dir=trial)
            frozen = _session_shell_call_ids(
                "fixture",
                session,
                start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                end=datetime(2027, 1, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(audit["shell_requests"], len(frozen))
        self.assertEqual(audit["shell_requests"], 2)

    def test_network_and_extra_execution_channels_are_reported(self) -> None:
        """Channels outside the shell metric must still be auditable.

        The host exposes network-capable tools and a PowerShell tool that the
        frozen Run Guard shell allowlist does not count. Both must surface in
        the audit, otherwise a trial could reach a code host or run commands
        entirely outside its recorded budget.
        """

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            trial = out_root / "trial"
            trial.mkdir()
            session = self._session(
                out_root / "session.jsonl",
                [
                    {
                        "type": "function_call",
                        "name": "WebFetch",
                        "callId": "c1",
                        "timestamp": 1789041306839,
                        "arguments": json.dumps(
                            {
                                "url": "https://github.com/example/repo/blob/main/evals/run-evals.sh"
                            }
                        ),
                    },
                    {
                        "type": "function_call",
                        "name": "PowerShell",
                        "callId": "c2",
                        "timestamp": 1789041306840,
                        "arguments": json.dumps({"command": "Get-Content x"}),
                    },
                ],
            )
            audit = audit_session(session, trial_dir=trial)

        self.assertTrue(audit["network_channel_present"])
        self.assertEqual(audit["network_tool_calls"][0]["tool"], "WebFetch")
        self.assertIn("github.com", audit["network_tool_calls"][0]["urls"][0])
        self.assertEqual(
            audit["execution_channels_not_in_shell_metric"][0]["tool"], "PowerShell"
        )
        # The frozen shell metric deliberately does not count PowerShell.
        self.assertEqual(audit["shell_requests"], 0)
        # URLs are not mistaken for filesystem paths.
        self.assertEqual(
            [item for item in audit["outside_accesses"] if "github" in item["target"]],
            [],
        )

    def test_msys_style_source_paths_are_still_classified_as_source(self) -> None:
        """Git Bash reports ``/e/...``; folding it onto ``E:/...`` matters."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            trial = out_root / "trial"
            trial.mkdir()
            session = self._session(
                out_root / "session.jsonl",
                [
                    {
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "c1",
                        "timestamp": 1789041306839,
                        "arguments": json.dumps(
                            {"command": "cat /e/source-repo/evals/run-evals.sh"}
                        ),
                    }
                ],
            )
            audit = audit_session(
                session, trial_dir=trial, source_repo="E:/source-repo"
            )

        scopes = {item["scope"] for item in audit["outside_accesses"]}
        self.assertIn("source_repo", scopes)


class AcceptorStagingTests(unittest.TestCase):
    """Grading must never write history into the repository it is handed.

    The earlier protection only refused to commit when Git resolved a
    *different* toplevel, so an ordinary root-level repository — exactly the
    shape a candidate directory takes — still passed the probe and could be
    committed. These tests pin the stronger contract: real-entry builds run
    against an acceptor-owned staging copy and the candidate repository keeps
    its HEAD, index, and worktree.
    """

    def test_acceptor_does_not_commit_an_ordinary_candidate_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            evals_script = (REPO_ROOT / "evals" / "run-evals.sh").read_text(
                encoding="utf-8"
            )
            candidate = _make_publication_candidate(out_root, "plain-repo", evals_script)
            # A plain repository with one owner commit and no trial marker.
            for arguments in (
                ["init", "--initial-branch=main"],
                [
                    "-c",
                    "user.name=Owner",
                    "-c",
                    "user.email=owner@example.invalid",
                    "add",
                    "-A",
                    "--",
                ],
                [
                    "-c",
                    "user.name=Owner",
                    "-c",
                    "user.email=owner@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-m",
                    "owner baseline",
                ],
            ):
                completed = _run_git(candidate, *arguments)
                self.assertEqual(completed.returncode, 0, completed.stderr)

            (candidate / "README.md").write_text("owner edit\n", encoding="utf-8")
            head_before = _run_git(candidate, "rev-parse", "HEAD").stdout.strip()
            status_before = _run_git(candidate, "status", "--porcelain").stdout
            log_before = _run_git(candidate, "log", "--oneline").stdout

            accept_publication_digest(candidate)

            head_after = _run_git(candidate, "rev-parse", "HEAD").stdout.strip()
            status_after = _run_git(candidate, "status", "--porcelain").stdout
            log_after = _run_git(candidate, "log", "--oneline").stdout

        self.assertEqual(head_after, head_before)
        self.assertEqual(status_after, status_before)
        self.assertEqual(log_after, log_before)
        self.assertNotIn("Workflow Eval Acceptor", log_after)


class ExportPathSemanticsTests(unittest.TestCase):
    """Export must use platform-appropriate path semantics.

    The extended-length prefix is a Windows-only construct. Applied under
    POSIX semantics it yields a relative path such as
    ``\\\\?\\/tmp/trial\\tools\\example.py`` which is neither absolute nor
    under the destination, so exported files would land outside the trial
    directory instead of inside it.
    """

    def test_posix_targets_stay_absolute_and_inside_the_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "trial"
            with unittest.mock.patch.object(os, "name", "posix"):
                target = _export_target(destination, "tools/example.py")
            expected_destination = destination.resolve()

        self.assertEqual(target, destination / "tools" / "example.py")
        self.assertTrue(target.is_absolute())
        self.assertFalse(str(target).startswith("\\\\?\\"))
        # ``TemporaryDirectory`` may hand out a path spelled with an 8.3
        # short component (Windows CI: ``RUNNER~1``) while ``resolve()``
        # expands it (``runneradmin``). Both spell the same directory, so
        # the containment check compares physical forms on both sides.
        resolved_target = os.path.realpath(str(target))
        resolved_destination = os.path.realpath(str(expected_destination))
        self.assertTrue(
            resolved_target.startswith(resolved_destination),
            f"{resolved_target} is not under the expected destination "
            f"{resolved_destination}",
        )

    def test_foreign_concrete_path_types_are_not_instantiable(self) -> None:
        """Pin the pathlib constraint the Windows test deliberately avoids.

        ``pathlib`` binds the supported concrete path type at import time, so
        the other platform's concrete type always raises (``NotImplementedError``
        on 3.11/3.12, ``UnsupportedOperation`` -- a subclass -- on 3.13+).
        Pure flavours stay usable everywhere. If this ever stops holding, the
        recording-factory workaround below can be simplified.
        """

        foreign = PosixPath if os.name == "nt" else WindowsPath
        with self.assertRaises(NotImplementedError):
            foreign("x")
        # Pure flavours remain host-independent.
        self.assertEqual(PureWindowsPath("a/b").parts, ("a", "b"))

    def test_windows_targets_use_the_extended_length_prefix(self) -> None:
        """Windows semantics are checked without building a foreign Path.

        ``pathlib`` fixes which concrete path types exist when the module is
        imported, so patching ``os.name`` afterwards cannot make
        ``WindowsPath`` usable on POSIX: python 3.11/3.12 raise
        ``NotImplementedError: cannot instantiate 'WindowsPath' on your
        system``, and 3.13+ no longer reads the runtime ``os.name`` when
        choosing a concrete type, which would make the assertion silently
        vacuous. The Windows branch is therefore driven through a recording
        path factory, and the composed text is checked with
        ``PureWindowsPath``, which is valid on every host.
        """

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "trial"
            expected_destination = destination.resolve()
            composed: list[str] = []

            def recording_factory(value: str) -> Path:
                composed.append(str(value))
                return destination

            with unittest.mock.patch.object(prepare_module, "Path", recording_factory):
                with unittest.mock.patch.object(os, "name", "nt"):
                    returned = _export_target(destination, "tools/example.py")

        # Exactly one path was composed: the nt branch is the one selected.
        self.assertEqual(len(composed), 1, composed)
        windows_text = composed[0]
        self.assertTrue(windows_text.startswith("\\\\?\\"), windows_text)
        # Anchored at the resolved destination, so files land inside it.
        self.assertTrue(
            windows_text.startswith("\\\\?\\" + str(expected_destination) + "\\"),
            windows_text,
        )
        # Archive separators are rewritten to backslashes.
        self.assertTrue(windows_text.endswith("\\tools\\example.py"), windows_text)
        # The composed text is the expected Windows path, read in its own
        # flavour so no foreign concrete path type is instantiated.
        self.assertEqual(
            PureWindowsPath(windows_text).parts[-2:], ("tools", "example.py")
        )
        # The host path type is never replaced by a foreign one.
        self.assertIsInstance(returned, type(destination))


class ExportCompletenessTests(unittest.TestCase):
    def test_export_matches_the_committed_file_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            source_repo, _ = _make_synthetic_source_repo(out_root / "source")
            (source_repo / "tools").mkdir()
            (source_repo / "tools" / "example.py").write_text("x = 1\n", encoding="utf-8")
            (source_repo / "docs").mkdir()
            (source_repo / "docs" / "guide.md").write_text("# guide\n", encoding="utf-8")
            self.assertEqual(
                _run_git(source_repo, "add", "-A", "--").returncode,
                0,
            )
            committed = _run_git(
                source_repo,
                "-c",
                "user.name=Synthetic Source",
                "-c",
                "user.email=synthetic@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-m",
                "add nested files",
            )
            self.assertEqual(committed.returncode, 0, committed.stderr)
            sha = _run_git(source_repo, "rev-parse", "HEAD").stdout.strip()

            destination = out_root / "export"
            export_commit_tree(source_repo, sha, destination)
            exported = sorted(
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            )
            expected = sorted(
                _run_git(source_repo, "ls-tree", "-r", "--name-only", sha).stdout.split()
            )

        self.assertEqual(exported, expected)
        self.assertIn("tools/example.py", exported)
        self.assertIn("file.txt", exported)

    def test_partial_export_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            source_repo, sha = _make_synthetic_source_repo(out_root / "source")
            destination = out_root / "export"
            with unittest.mock.patch.object(
                prepare_module,
                "_git_tree_paths",
                return_value=["file.txt", "missing.txt"],
            ):
                with self.assertRaises(PrepareError) as caught:
                    export_commit_tree(source_repo, sha, destination)

        message = str(caught.exception)
        self.assertIn("does not match the committed tree", message)
        self.assertIn("missing.txt", message)


class ScopeBaselineTests(unittest.TestCase):
    def test_out_of_scope_change_is_detected_and_metadata_tampering_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            source_repo, sha = _make_synthetic_source_repo(out_root / "source")
            task = _make_synthetic_task(sha)
            prepared = prepare_trial(
                source_repo=source_repo,
                task=task,
                group="control",
                out_root=out_root / "trials-root",
                run_label="unit",
            )
            trial_dir = Path(str(prepared["trial_dir"]))
            manifest_path = Path(str(prepared["trusted_manifest_path"]))
            # Out-of-scope modification: file.txt is not in allowed_paths.
            (trial_dir / "file.txt").write_text("tampered\n", encoding="utf-8")
            # The candidate also rewrites its own metadata: the trusted
            # baseline must not care.
            (trial_dir / "trial-metadata.json").write_text(
                json.dumps({"record_type": "forged", "note": "tamper"}),
                encoding="utf-8",
            )
            record = grade_trial(
                task=task,
                candidate_root=trial_dir,
                results_dir=out_root / "results",
                label="unit",
                group="control",
                trial_dir=trial_dir,
                run_kind="freeze",
                manifest_path=manifest_path,
            )
            manifest_digest = record["manifest_sha256"]
            expected_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        self.assertIn("file.txt", record["scope"]["changed_files"])
        self.assertIn("file.txt", record["scope"]["scope_violations"])
        self.assertFalse(record["scope_clean"])
        self.assertNotIn("trial-metadata.json", record["scope"]["changed_files"])
        self.assertEqual(manifest_digest, expected_digest)

    def test_manifest_inside_candidate_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            source_repo, sha = _make_synthetic_source_repo(out_root / "source")
            task = _make_synthetic_task(sha)
            prepared = prepare_trial(
                source_repo=source_repo,
                task=task,
                group="control",
                out_root=out_root / "trials-root",
                run_label="unit",
            )
            trial_dir = Path(str(prepared["trial_dir"]))
            inside_manifest = trial_dir / "inside-manifest.json"
            manifest = json.loads(
                Path(str(prepared["trusted_manifest_path"])).read_text(encoding="utf-8")
            )
            inside_manifest.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(Exception) as caught:
                grade_trial(
                    task=task,
                    candidate_root=trial_dir,
                    results_dir=out_root / "results",
                    label="unit",
                    group="control",
                    trial_dir=trial_dir,
                    run_kind="freeze",
                    manifest_path=inside_manifest,
                )

        self.assertIn("outside the candidate tree", str(caught.exception))

    def test_manifest_with_wrong_identity_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            source_repo, sha = _make_synthetic_source_repo(out_root / "source")
            task = _make_synthetic_task(sha)
            prepared = prepare_trial(
                source_repo=source_repo,
                task=task,
                group="control",
                out_root=out_root / "trials-root",
                run_label="unit",
            )
            trial_dir = Path(str(prepared["trial_dir"]))
            manifest_path = out_root / "forged-manifest.json"
            _write_manifest(
                manifest_path,
                task_id="another-task",
                group="experiment",
                trial_dir=trial_dir,
                source_sha="not-a-commit",
                file_manifest=_hash_tree(trial_dir),
            )

            with self.assertRaises(Exception) as caught:
                grade_trial(
                    task=task,
                    candidate_root=trial_dir,
                    results_dir=out_root / "results",
                    label="unit",
                    group="control",
                    trial_dir=trial_dir,
                    run_kind="freeze",
                    manifest_path=manifest_path,
                )

        message = str(caught.exception)
        self.assertTrue(
            "task_id" in message or "group" in message or "source_sha" in message,
            message,
        )

    def test_manifest_candidate_path_and_locked_baseline_are_required(self) -> None:
        """A manifest must name this candidate and a task-locked baseline.

        Omitting ``trial_dir`` or supplying a 40-hex SHA unrelated to the task
        previously passed validation, so a manifest could describe a
        different preparation, or a different revision of the same task.
        """

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            candidate = out_root / "candidate"
            candidate.mkdir()
            (candidate / "file.txt").write_text("x\n", encoding="utf-8")
            task = TaskDefinition(
                task_id="baseline-task",
                title="Baseline task",
                pre_fix_sha="a" * 40,
                fix_sha="b" * 40,
                allowed_paths=("file.txt",),
                brief_goal="g",
                brief_contract=("c",),
                brief_acceptance=("a",),
                brief_context="x",
            )
            manifest_path = out_root / "manifest.json"

            def write_manifest(**overrides: object) -> None:
                payload: dict[str, object] = {
                    "record_type": "trusted_trial_manifest",
                    "task_id": "baseline-task",
                    "group": "control",
                    "trial_dir": str(candidate),
                    "source_sha": "a" * 40,
                    "file_manifest": {"file.txt": "0" * 64},
                }
                payload.update(overrides)
                manifest_path.write_text(json.dumps(payload), encoding="utf-8")

            def grade(run_kind: str = "freeze") -> dict[str, object]:
                return grade_trial(
                    task=task,
                    candidate_root=candidate,
                    results_dir=out_root / "results",
                    label="baseline",
                    group="control",
                    trial_dir=candidate,
                    run_kind=run_kind,
                    manifest_path=manifest_path,
                )

            write_manifest(trial_dir=None)
            with self.assertRaises(Exception) as missing_dir:
                grade()
            self.assertIn("trial_dir", str(missing_dir.exception))

            write_manifest(source_sha="c" * 40)
            with self.assertRaises(Exception) as unrelated_sha:
                grade()
            self.assertIn("source_sha", str(unrelated_sha.exception))

            write_manifest(source_sha="b" * 40)
            with self.assertRaises(Exception) as wrong_baseline:
                grade(run_kind="trial")
            self.assertIn("pre-fix", str(wrong_baseline.exception))

            # The happy path stays open: a frozen run may use either locked
            # baseline, and the record carries the SHA it validated.
            write_manifest()
            accepted = grade()
            self.assertEqual(accepted["source_sha"], "a" * 40)
            self.assertEqual(accepted["run_kind"], "freeze")


class ReportEvidenceLoopTests(unittest.TestCase):
    @staticmethod
    def _write_record(
        results_dir: Path,
        task_id: str,
        group: str,
        *,
        verdict: str = "ACCEPT",
        run_kind: str = "trial",
        acceptor_status: str = "OK",
        exit_code: int | None = None,
        scenarios: list[dict] | None = None,
        budget: bool | dict = True,
        label: str = "unit",
        source_sha: str | None = None,
        acceptor_verdict: str | None = None,
        validity: dict | None = None,
        trial_isolated: bool | None = True,
        scope_clean: bool = True,
    ) -> None:
        if exit_code is None:
            exit_code = {"ACCEPT": 0, "REJECT": 1, "BLOCKED": 2}.get(verdict, 1)
        if scenarios is None:
            scenarios = [
                {
                    "name": "s",
                    "expectation": "e",
                    "observed": "o",
                    "pass": verdict == "ACCEPT",
                }
            ]
        task = TASKS[task_id]
        if source_sha is None:
            if run_kind == "freeze" and verdict == "ACCEPT":
                source_sha = task.fix_sha
            else:
                # Trials and pre-fix freeze evidence both start from the
                # task's locked pre-fix baseline.
                source_sha = task.pre_fix_sha
        if acceptor_verdict is None:
            acceptor_verdict = verdict
        if isinstance(budget, dict):
            budget_record = budget
        elif budget:
            budget_record = {
                "elapsed_seconds": 1.0,
                "shell_requests": 2,
                "human_interventions": "none",
            }
        else:
            budget_record = {}
        record = {
            "record_type": "graded_trial",
            "run_kind": run_kind,
            "task_id": task_id,
            "group": group,
            "label": label,
            "verdict": verdict,
            "source_sha": source_sha,
            "acceptor": {
                "acceptor_status": acceptor_status,
                "verdict": acceptor_verdict,
                "scenarios": scenarios,
            },
            "acceptor_exit_code": exit_code,
            "scope": {"scope_violations": [] if scope_clean else ["file.txt"]},
            "scope_clean": scope_clean,
            "budget": budget_record,
        }
        if run_kind == "trial":
            if validity is None:
                validity = {
                    "status": "VALID",
                    "basis": "unit fixture: coordinator audit found no out-of-trial access",
                    "audit_record": "unit-fixture-audit.json",
                }
            record["trial_validity"] = validity
            record["trial_isolated"] = trial_isolated
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / f"{task_id}--{group}--{label}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )

    @classmethod
    def _write_full_batch(
        cls, results: Path, **overrides: object
    ) -> None:
        """Write a structurally complete batch (freeze evidence + six trials)."""

        for task_id in TASK_ORDER:
            cls._write_record(
                results,
                task_id,
                "control",
                verdict="REJECT",
                run_kind="freeze",
                label="freeze-pre",
            )
            cls._write_record(
                results,
                task_id,
                "control",
                verdict="ACCEPT",
                run_kind="freeze",
                label="freeze-fixed",
            )
            for group in ("control", "experiment"):
                cls._write_record(results, task_id, group, **overrides)

    def test_empty_results_are_reported_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            summary = write_report(
                out_root / "results",
                out_root / "report.md",
                run_label="unit",
            )
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        self.assertEqual(summary["status"], "PASS_INCOMPLETE")
        self.assertFalse(summary["completeness"]["complete"])
        self.assertIn("INCOMPLETE", report_text)

    def test_broken_evidence_files_are_listed_not_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            results.mkdir()
            (results / "broken.json").write_text("{not-json", encoding="utf-8")
            self._write_record(results, "bootstrap-refs", "control", verdict="REJECT")
            summary = write_report(
                results, out_root / "report.md", run_label="unit"
            )
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        self.assertEqual(len(summary["broken_evidence"]), 1)
        self.assertEqual(summary["broken_evidence"][0]["path"], "broken.json")
        self.assertIn("broken.json", report_text)

    def test_inconsistent_accept_wrappers_do_not_fill_slots(self) -> None:
        # Six records whose top level says ACCEPT but whose internals say
        # BLOCKED: they must not complete the evidence set, and the report
        # must name them.
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            for task_id in TASK_ORDER:
                for group in ("control", "experiment"):
                    self._write_record(
                        results,
                        task_id,
                        group,
                        verdict="ACCEPT",
                        acceptor_status="BLOCKED",
                        exit_code=2,
                        scenarios=[],
                        budget=False,
                    )
            summary = write_report(
                results, out_root / "report.md", run_label="unit"
            )
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        self.assertEqual(summary["status"], "PASS_INCOMPLETE")
        self.assertFalse(summary["completeness"]["complete"])
        self.assertTrue(summary["completeness"]["inconsistent_records"])
        self.assertIn("Inconsistent evidence records", report_text)

    def test_contradictory_records_and_invalid_freeze_evidence_are_not_complete(self) -> None:
        """Reproduce the reported counterexample.

        A pre-fix REJECT whose scenarios all passed and whose inner verdict
        said ACCEPT, freeze records with all-zero source SHAs, and trial
        budgets of ``-1`` seconds and ``-25`` shell requests previously
        produced ``complete: true``. Each defect must now be flagged and no
        freeze slot may count as filled.
        """

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            for task_id in TASK_ORDER:
                self._write_record(
                    results,
                    task_id,
                    "control",
                    verdict="REJECT",
                    run_kind="freeze",
                    label="freeze-pre",
                    source_sha="0" * 40,
                    acceptor_verdict="ACCEPT",
                    scenarios=[
                        {"name": "s", "expectation": "e", "observed": "o", "pass": True}
                    ],
                )
                self._write_record(
                    results,
                    task_id,
                    "control",
                    verdict="ACCEPT",
                    run_kind="freeze",
                    label="freeze-fixed",
                    source_sha="0" * 40,
                )
                for group in ("control", "experiment"):
                    self._write_record(
                        results,
                        task_id,
                        group,
                        budget={
                            "elapsed_seconds": -1,
                            "shell_requests": -25,
                            "human_interventions": "none",
                        },
                    )
            summary = write_report(
                results, out_root / "report.md", run_label="unit"
            )

        completeness = summary["completeness"]
        problems = [
            problem
            for problem_list in completeness["inconsistent_records"].values()
            for problem in problem_list
        ]
        self.assertEqual(summary["status"], "PASS_INCOMPLETE")
        self.assertFalse(completeness["complete"])
        self.assertTrue(completeness["missing_freeze_evidence"])
        self.assertTrue(
            any("disagrees with acceptor verdict" in item for item in problems), problems
        )
        self.assertTrue(
            any("no failing scenario" in item for item in problems), problems
        )
        self.assertTrue(any("locked fix SHA" in item for item in problems), problems)
        self.assertTrue(any("locked pre-fix SHA" in item for item in problems), problems)
        self.assertTrue(any("non-negative" in item for item in problems), problems)

    def test_complete_consistent_trial_set_reports_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            self._write_full_batch(results)
            summary = write_report(
                results, out_root / "report.md", run_label="unit"
            )
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        self.assertEqual(summary["status"], "PASS")
        self.assertTrue(summary["completeness"]["complete"])
        self.assertTrue(summary["completeness"]["structure_complete"])
        self.assertEqual(summary["completeness"]["valid_trial_results_present"], 6)
        self.assertEqual(summary["completeness"]["invalid_trial_results"], 0)
        self.assertEqual(summary["completeness"]["unverified_trial_results"], 0)
        self.assertEqual(
            summary["completeness"]["valid_outcomes"], {"ACCEPT": 6, "REJECT": 0}
        )
        self.assertIn("Valid comparison: **complete", report_text)

    def test_unattested_trials_do_not_complete_the_comparison(self) -> None:
        """Well-formed records are not a valid comparison.

        The six trial records here are internally consistent and the frozen
        evidence is present, so record structure is complete. None carries a
        coordinator validity attestation, so none may fill a valid slot, and
        the report must say so instead of reading "six files present" as a
        finished comparison.
        """

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            self._write_full_batch(results, validity={})
            summary = write_report(results, out_root / "report.md", run_label="unit")
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        completeness = summary["completeness"]
        self.assertEqual(summary["status"], "PASS_INCOMPLETE")
        self.assertEqual(summary["structure_status"], "PASS")
        self.assertTrue(completeness["structure_complete"])
        self.assertFalse(completeness["complete"])
        self.assertEqual(completeness["trial_results_present"], 6)
        self.assertEqual(completeness["valid_trial_results_present"], 0)
        self.assertEqual(completeness["unverified_trial_results"], 6)
        self.assertEqual(len(completeness["missing_valid_trial_slots"]), 6)
        self.assertIn("Trial protocol validity: **0 of 6 VALID", report_text)
        self.assertIn("Valid comparison: **NOT complete", report_text)
        self.assertIn("Why runs do not count as valid trials", report_text)
        self.assertIn("no coordinator validity attestation present", report_text)

    def test_invalid_trial_leaves_its_slot_unfilled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            self._write_full_batch(results)
            # Overwrite one slot with an INVALID attestation, as the run1
            # publication-digest experiment run was recorded.
            (results / "publication-digest--experiment--unit.json").unlink()
            self._write_record(
                results,
                "publication-digest",
                "experiment",
                validity={
                    "status": "INVALID",
                    "basis": "protocol violation: the trial lost its .git and git "
                    "discovery resolved to the source repository",
                    "audit_record": "run1-audit.json",
                },
            )
            summary = write_report(results, out_root / "report.md", run_label="unit")
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        completeness = summary["completeness"]
        self.assertEqual(summary["status"], "PASS_INCOMPLETE")
        self.assertTrue(completeness["structure_complete"])
        self.assertFalse(completeness["complete"])
        self.assertEqual(completeness["valid_trial_results_present"], 5)
        self.assertEqual(completeness["invalid_trial_results"], 1)
        self.assertEqual(completeness["valid_outcomes"], {"ACCEPT": 5, "REJECT": 0})
        self.assertEqual(
            completeness["missing_valid_trial_slots"], ["publication-digest/experiment"]
        )
        self.assertIn("1 INVALID", report_text)
        # The functional verdict is still reported for the record itself.
        self.assertIn("publication-digest | experiment | trial | ACCEPT", report_text)

    def test_valid_attestation_without_basis_is_treated_as_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            self._write_full_batch(
                results, validity={"status": "VALID", "basis": "   "}
            )
            summary = write_report(results, out_root / "report.md", run_label="unit")
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        completeness = summary["completeness"]
        self.assertEqual(completeness["valid_trial_results_present"], 0)
        self.assertEqual(completeness["unverified_trial_results"], 6)
        self.assertIn("carries no audit basis", report_text)

    def test_failed_git_probe_or_scope_violation_blocks_a_valid_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            # Structurally consistent, VALID attestation, but the pre-scoring
            # Git root probe is not recorded as passing, so the run cannot fill
            # a valid slot.
            self._write_full_batch(results, trial_isolated=False)
            summary = write_report(results, out_root / "report.md", run_label="unit")
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        completeness = summary["completeness"]
        self.assertEqual(completeness["valid_trial_results_present"], 0)
        self.assertTrue(completeness["structure_complete"])
        self.assertFalse(completeness["complete"])
        self.assertIn("pre-scoring Git root probe did not pass", report_text)

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            results = out_root / "results"
            self._write_full_batch(results, scope_clean=False)
            summary = write_report(results, out_root / "report.md", run_label="unit")
            report_text = (out_root / "report.md").read_text(encoding="utf-8")

        self.assertEqual(
            summary["completeness"]["valid_trial_results_present"], 0
        )
        self.assertIn("outside the allowed paths", report_text)


class CommandLineTests(unittest.TestCase):
    def test_report_cli_exit_codes_reflect_completeness(self) -> None:
        def run_report(results_dir: Path, output: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "tools.workflow_eval",
                    "report",
                    "--results-dir",
                    str(results_dir),
                    "--output",
                    str(output),
                    "--label",
                    "cli",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            empty = run_report(out_root / "empty", out_root / "empty-report.md")
            self.assertEqual(empty.returncode, 1, empty.stdout)

            results = out_root / "results"
            ReportEvidenceLoopTests._write_full_batch(results)
            complete = run_report(results, out_root / "report.md")
            self.assertEqual(complete.returncode, 0, complete.stdout)

            # Same structure, no validity attestation: the CLI must report an
            # incomplete *comparison* even though record structure is complete.
            unattested = out_root / "unattested"
            ReportEvidenceLoopTests._write_full_batch(unattested, validity={})
            unattested_result = run_report(
                unattested, out_root / "unattested-report.md"
            )
            self.assertEqual(unattested_result.returncode, 1, unattested_result.stdout)

    def test_grade_cli_requires_trusted_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "tools.workflow_eval",
                    "grade",
                    "--task",
                    "publication-digest",
                    "--candidate-dir",
                    str(out_root / "missing-candidate"),
                    "--results-dir",
                    str(out_root / "results"),
                    "--label",
                    "cli",
                    "--group",
                    "control",
                    "--run-kind",
                    "trial",
                    "--manifest",
                    str(out_root / "missing-manifest.json"),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertIn("BLOCKED", completed.stdout)

    def test_grade_cli_refuses_manifest_inside_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            out_root = Path(temporary_directory)
            candidate = out_root / "candidate"
            candidate.mkdir()
            inside = candidate / "inside-manifest.json"
            inside.write_text("{}", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "tools.workflow_eval",
                    "grade",
                    "--task",
                    "publication-digest",
                    "--candidate-dir",
                    str(candidate),
                    "--results-dir",
                    str(out_root / "results"),
                    "--label",
                    "cli",
                    "--group",
                    "control",
                    "--run-kind",
                    "trial",
                    "--manifest",
                    str(inside),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertIn("outside the candidate tree", completed.stdout)


if __name__ == "__main__":
    unittest.main()
