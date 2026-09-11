"""Independent, frozen acceptors for workflow_eval task definitions.

This module runs inside an isolated subprocess (see ``_acceptor_runner.py``)
and must only use the Python standard library. Every acceptor grades one
candidate tree against the observable contract recorded in
``tools/workflow_eval/tasks.py`` and reports a deterministic JSON verdict:

{"task_id": ..., "verdict": "ACCEPT"|"REJECT", "acceptor_status": "OK",
 "scenarios": [{"name", "expectation", "observed", "pass"}]}

Two hard rules:

- Only executed scenario results may produce ACCEPT or REJECT. Acceptors
  never accept a candidate because nothing was observed: every scenario
  compares the observed state against explicit expected values.
- Infrastructure failures (fixture setup, Git unavailability, unexpected
  crashes) raise :class:`AcceptorBlocked`. The runner reports
  ``verdict="BLOCKED"`` with exit code 2; a BLOCKED result is never valid
  negative evidence for a pre-fix tree and never counts as a rejection.

Acceptors never read network state, never trust candidate-side test
results, and are never modified by trial agents.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest.mock
from pathlib import Path
from types import ModuleType


class AcceptorBlocked(RuntimeError):
    """Infrastructure failed; the acceptor produced no verdict."""


class _ExpectationFailed(Exception):
    """Raised by helper assertions with the observed detail as message."""


def _scenario(name: str, expectation: str, observed: str, passed: bool) -> dict:
    return {
        "name": name,
        "expectation": expectation,
        "observed": observed,
        "pass": bool(passed),
    }


def _verdict(scenarios: list[dict]) -> str:
    return "ACCEPT" if scenarios and all(item["pass"] for item in scenarios) else "REJECT"


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


def _init_repo(root: Path) -> None:
    """Create a real one-commit repository for acceptor scenarios.

    Order matters: the file must exist before ``git add`` stages it.
    Failures here are infrastructure problems, not scenario outcomes.
    """

    root.mkdir(parents=True, exist_ok=True)
    (root / "file.txt").write_text("one\n", encoding="utf-8")
    for arguments in (
        ("init", "--initial-branch=main"),
        ("add", "--", "."),
    ):
        completed = _run_git(root, *arguments)
        if completed.returncode != 0:
            raise AcceptorBlocked(
                f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
            )
    completed = _run_git(
        root,
        "-c",
        "user.name=Acceptor Fixture",
        "-c",
        "user.email=acceptor@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "acceptor baseline",
    )
    if completed.returncode != 0:
        raise AcceptorBlocked(f"git commit failed: {completed.stderr.strip()}")


# ---------------------------------------------------------------------------
# Task: publication-digest
# ---------------------------------------------------------------------------


def _extract_digest_selection_block(candidate_root: Path) -> str:
    """Extract the contiguous manifest/digest selection block.

    The block is located behaviorally: it starts at the assignment that
    lists manifests via ``glob("*.manifest.json")`` and ends at the matching
    ``return manifest`` line. Both the historical pre-fix form (inline in
    ``build_release``) and a factored helper form satisfy this shape, so the
    acceptor never demands an internal function name the historical answer
    does not have.
    """

    script = (candidate_root / "evals" / "run-evals.sh").read_text(encoding="utf-8")
    lines = script.splitlines()
    anchor_pattern = re.compile(
        r"^(\s*)[A-Za-z_]\w*\s*=\s*.*\.glob\(\s*['\"]\*\.manifest\.json['\"]\s*\)"
    )
    anchor_index = None
    indent = ""
    for index, line in enumerate(lines):
        match = anchor_pattern.match(line)
        if match:
            anchor_index = index
            indent = match.group(1)
            break
    if anchor_index is None:
        raise _ExpectationFailed(
            "no manifest listing assignment via glob('*.manifest.json') found"
        )
    return_line = None
    return_pattern = re.compile(rf"^{re.escape(indent)}return\b")
    for index in range(anchor_index + 1, len(lines)):
        if return_pattern.match(lines[index]):
            return_line = index
            break
    if return_line is None:
        raise _ExpectationFailed(
            f"no 'return' at indent {len(indent)} after the manifest listing line"
        )
    block = "\n".join(lines[anchor_index : return_line + 1])
    return textwrap.dedent(block)


_PROBE_NAMESPACE: dict[str, object] = {
    "json": json,
    "os": os,
    "sys": sys,
    "shutil": __import__("shutil"),
    "subprocess": subprocess,
    "tempfile": tempfile,
    "zipfile": __import__("zipfile"),
    "Path": Path,
}


def _load_selection_function(candidate_root: Path):
    block = _extract_digest_selection_block(candidate_root)
    probe = "def _acceptor_probe(out_dir):\n" + textwrap.indent(block, "    ")
    namespace: dict[str, object] = {
        "__name__": "candidate_digest_selection",
        **_PROBE_NAMESPACE,
    }
    exec(compile(probe, "<candidate-digest-selection>", "exec"), namespace)
    return namespace["_acceptor_probe"]


def _load_eval_namespace(root: Path) -> dict[str, object]:
    """Execute the candidate's whole eval heredoc and return its namespace.

    ``root`` is the tree the harness should consider its repository root: the
    heredoc resolves ``ROOT`` from ``sys.argv[1]``, so callers pass the
    acceptor-owned staging copy. The heredoc ends with the case dispatch,
    which raises SystemExit for the probe case name; every function
    definition (including the real ``build_release``) is complete at that
    point, so the SystemExit is the expected control flow, not an error.
    """

    script = (root / "evals" / "run-evals.sh").read_text(encoding="utf-8")
    if "<<'PY'" not in script:
        raise _ExpectationFailed("eval script has no embedded Python heredoc")
    body = script.split("<<'PY'", 1)[1]
    body = body.split("\nPY\n", 1)[0]
    namespace: dict[str, object] = {"__name__": "candidate_eval_heredoc"}
    saved_argv = sys.argv
    sys.argv = ["evals-probe", str(root), "__acceptor_probe__"]
    try:
        exec(compile(body, "<candidate-eval-heredoc>", "exec"), namespace)
    except SystemExit:
        pass
    finally:
        sys.argv = saved_argv
    return namespace


def _manifest_dir(
    root: Path,
    manifests: dict[str, str],
    digests: dict[str, str],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, digest in manifests.items():
        (root / name).write_text(json.dumps({"publication_digest": digest}), encoding="utf-8")
    for name, digest in digests.items():
        (root / name).write_text(f"{digest}\n", encoding="utf-8")
    return root


def _is_top_level_work_tree(root: Path) -> bool:
    """Return whether ``root`` is itself the top-level Git work tree.

    Mirrors the candidate builder's trusted-source gate: only a top-level
    work tree can produce a commit-traced build without an explicit
    unverified label. Read-only: this probe never writes.
    """

    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if completed.returncode != 0:
        return False
    resolved_top = os.path.normcase(os.path.abspath(completed.stdout.strip()))
    return resolved_top == os.path.normcase(os.path.abspath(str(root)))


def _stage_candidate_tree(candidate_root: Path, staging_root: Path) -> None:
    """Copy candidate content into an acceptor-owned staging directory.

    The real-entry scenarios drive the candidate's actual ``build_release``,
    whose trusted-source gate requires a clean commit. Committing the
    candidate repository itself would let grading write history into whatever
    directory it was handed — including an ordinary user repository that
    happens to be a root-level work tree, which the earlier toplevel probe
    alone could not rule out. Staging confines every write to a directory the
    acceptor owns, so the candidate's HEAD, index, and worktree are
    byte-identical before and after grading.

    Git metadata is deliberately not copied: the staged copy is either a
    fresh single-commit repository or, for non-Git candidates, a plain
    directory that takes the builder's ``--allow-unverified`` path, which
    preserves the previous behaviour for both shapes.
    """

    staging_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(candidate_root.rglob("*")):
        relative = path.relative_to(candidate_root)
        if ".git" in relative.parts:
            continue
        target = staging_root / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def _commit_staging_repo(staging_root: Path) -> None:
    """Commit the staged copy so the candidate's build can run verified.

    Only the acceptor-owned staging repository is written; the candidate
    repository is never touched. ``core.autocrlf=false`` keeps raw bytes so
    the builder's byte comparison is meaningful, and ``core.longpaths`` is
    repo-local so deeply nested fixtures survive ``git add`` on Windows.
    """

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(staging_root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    for arguments in (
        ("init", "--initial-branch=main"),
        ("config", "core.longpaths", "true"),
        ("config", "core.autocrlf", "false"),
        ("add", "-A", "--"),
    ):
        completed = git(*arguments)
        if completed.returncode != 0:
            raise AcceptorBlocked(
                f"staging repo setup failed ({arguments[0]}): {completed.stderr.strip()}"
            )
    completed = git(
        "-c",
        "user.name=Workflow Eval Acceptor",
        "-c",
        "user.email=acceptor@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "acceptor: staged candidate state for trusted build",
    )
    if completed.returncode != 0:
        raise AcceptorBlocked(f"staging commit failed: {completed.stderr.strip()}")


def accept_publication_digest(candidate_root: Path) -> dict:
    scenarios: list[dict] = []

    script_path = candidate_root / "evals" / "run-evals.sh"
    if not script_path.is_file():
        return {
            "task_id": "publication-digest",
            "acceptor_status": "OK",
            "verdict": "REJECT",
            "scenarios": [
                _scenario(
                    "eval-script-present",
                    "evals/run-evals.sh exists in the candidate tree",
                    "file is missing",
                    False,
                )
            ],
        }

    try:
        function = _load_selection_function(candidate_root)
    except _ExpectationFailed as exc:
        return {
            "task_id": "publication-digest",
            "acceptor_status": "OK",
            "verdict": "REJECT",
            "scenarios": [
                _scenario(
                    "selection-block-locatable",
                    "manifest/digest selection stays a contiguous block that takes "
                    "the output directory and returns the manifest",
                    str(exc),
                    False,
                )
            ],
        }

    def run_function(directory: Path):
        return function(directory)

    def expect_system_exit(name: str, expectation: str, directory: Path) -> None:
        try:
            run_function(directory)
        except SystemExit:
            scenarios.append(_scenario(name, expectation, "raised SystemExit", True))
        except Exception as exc:  # noqa: BLE001
            scenarios.append(
                _scenario(name, expectation, f"{type(exc).__name__}: {exc}", False)
            )
        else:
            scenarios.append(_scenario(name, expectation, "returned normally", False))

    def expect_manifest(name: str, expectation: str, directory: Path, digest: str) -> None:
        try:
            manifest = run_function(directory)
        except Exception as exc:  # noqa: BLE001
            scenarios.append(
                _scenario(name, expectation, f"{type(exc).__name__}: {exc}", False)
            )
            return
        observed = (
            "manifest returned" if isinstance(manifest, dict) else f"{type(manifest).__name__} returned"
        )
        passed = isinstance(manifest, dict) and manifest.get("publication_digest") == digest
        scenarios.append(
            _scenario(
                name,
                expectation,
                f"{observed}; publication_digest={manifest.get('publication_digest')!r}",
                passed,
            )
        )

    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        expect_system_exit(
            "missing-manifest",
            "zero manifests fail with a clear error",
            _manifest_dir(base / "missing", {}, {}),
        )
        expect_system_exit(
            "duplicate-manifest",
            "two manifests fail with a clear error",
            _manifest_dir(
                base / "duplicate",
                {
                    "template-a.manifest.json": "digest-a",
                    "template-b.manifest.json": "digest-b",
                },
                {
                    "template-a.digest.txt": "digest-a",
                    "template-b.digest.txt": "digest-b",
                },
            ),
        )
        expect_system_exit(
            "missing-digest",
            "manifest without its stem digest file fails",
            _manifest_dir(
                base / "no-digest",
                {"template-advanced-2.0.0.manifest.json": "publication-digest"},
                {},
            ),
        )
        expect_system_exit(
            "digest-mismatch",
            "digest content differing from the manifest fails",
            _manifest_dir(
                base / "mismatch",
                {"template-advanced-2.0.0.manifest.json": "publication-digest"},
                {"template-advanced-2.0.0.digest.txt": "different-digest"},
            ),
        )

        decoy_dir = _manifest_dir(
            base / "decoy",
            {"template-advanced-2.0.0.manifest.json": "publication-digest"},
            {
                "template-advanced-2.0.0.digest.txt": "publication-digest",
                "template-advanced-2.0.0.payload.digest.txt": "payload-digest",
            },
        )

        original_glob = Path.glob

        def reject_digest_wildcards(path: Path, pattern: str):
            if "digest" in pattern and "*" in pattern:
                raise _ExpectationFailed(
                    f"digest selection used wildcard glob: {pattern!r}"
                )
            return original_glob(path, pattern)

        # The decoy scenario asserts the RETURNED digest value: a selection
        # that runs without error but yields the payload digest must fail.
        try:
            with unittest.mock.patch.object(Path, "glob", reject_digest_wildcards):
                manifest = run_function(decoy_dir)
        except _ExpectationFailed as exc:
            scenarios.append(
                _scenario(
                    "payload-decoy-ignored",
                    "with a payload digest decoy present, the selection returns the "
                    "stem digest value without any wildcard glob",
                    f"wildcard glob used: {exc}",
                    False,
                )
            )
        except Exception as exc:  # noqa: BLE001
            scenarios.append(
                _scenario(
                    "payload-decoy-ignored",
                    "with a payload digest decoy present, the selection returns the "
                    "stem digest value without any wildcard glob",
                    f"{type(exc).__name__}: {exc}",
                    False,
                )
            )
        else:
            passed = (
                isinstance(manifest, dict)
                and manifest.get("publication_digest") == "publication-digest"
            )
            scenarios.append(
                _scenario(
                    "payload-decoy-ignored",
                    "with a payload digest decoy present, the selection returns the "
                    "stem digest value without any wildcard glob",
                    f"publication_digest={manifest.get('publication_digest')!r}",
                    passed,
                )
            )

        expect_manifest(
            "clean-selection",
            "clean manifest plus matching stem digest returns the manifest",
            _manifest_dir(
                base / "clean",
                {"template-advanced-2.0.0.manifest.json": "publication-digest"},
                {"template-advanced-2.0.0.digest.txt": "publication-digest"},
            ),
            "publication-digest",
        )

    # Real-entry scenarios: drive the candidate's actual build_release so the
    # selection logic must be wired into the real call path. An early wrong
    # return inside build_release, or an unwired orphan block, fails here
    # even when the isolated block scenarios pass. The builder itself writes
    # a <stem>.payload.digest.txt decoy, so the rebuilt output directory is
    # the natural decoy environment.
    #
    # Every build runs against an acceptor-owned staging copy, so grading
    # never commits to — or otherwise writes inside — the candidate
    # repository it was handed.
    with tempfile.TemporaryDirectory() as build_temp:
        build_base = Path(build_temp)
        staging_root = build_base / "candidate"
        try:
            _stage_candidate_tree(candidate_root, staging_root)
            if _is_top_level_work_tree(candidate_root):
                _commit_staging_repo(staging_root)
            namespace = _load_eval_namespace(staging_root)
            build_release = namespace.get("build_release")
            if not callable(build_release):
                raise _ExpectationFailed(
                    "heredoc does not define a callable build_release"
                )
        except _ExpectationFailed as exc:
            scenarios.append(
                _scenario(
                    "real-entry-loadable",
                    "the eval heredoc defines a callable build_release for end-to-end probing",
                    str(exc),
                    False,
                )
            )
        else:
            out_dir = build_base / "out"
            stem_digest_path = out_dir / "template-advanced-2.0.0.digest.txt"
            try:
                manifest = build_release(out_dir)
                on_disk = stem_digest_path.read_text(encoding="utf-8").strip()
                passed = (
                    isinstance(manifest, dict)
                    and manifest.get("publication_digest") == on_disk
                )
                scenarios.append(
                    _scenario(
                        "real-entry-wired",
                        "the real build_release returns the publication digest it just built",
                        f"publication_digest={manifest.get('publication_digest')!r}, "
                        f"on-disk stem digest={on_disk!r}",
                        passed,
                    )
                )
            except SystemExit as exc:
                # The eval harness signals builder failures with SystemExit;
                # for a correct candidate the real build must succeed.
                scenarios.append(
                    _scenario(
                        "real-entry-wired",
                        "the real build_release returns the publication digest it just built",
                        f"SystemExit: {exc}",
                        False,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                scenarios.append(
                    _scenario(
                        "real-entry-wired",
                        "the real build_release returns the publication digest it just built",
                        f"{type(exc).__name__}: {exc}",
                        False,
                    )
                )
            try:
                decoy_path = out_dir / "template-advanced-2.0.0.payload.digest.txt"
                if not decoy_path.is_file():
                    decoy_path.write_text("payload-digest\n", encoding="utf-8")
                on_disk = stem_digest_path.read_text(encoding="utf-8").strip()
                with unittest.mock.patch.object(Path, "glob", reject_digest_wildcards):
                    manifest = build_release(out_dir)
                passed = (
                    isinstance(manifest, dict)
                    and manifest.get("publication_digest") == on_disk
                )
                scenarios.append(
                    _scenario(
                        "real-entry-decoy-ignored",
                        "through the real entry with the payload decoy present, the "
                        "selection returns the on-disk stem digest value without any "
                        "wildcard glob",
                        f"publication_digest={manifest.get('publication_digest')!r}, "
                        f"on-disk stem digest={on_disk!r}",
                        passed,
                    )
                )
            except _ExpectationFailed as exc:
                scenarios.append(
                    _scenario(
                        "real-entry-decoy-ignored",
                        "through the real entry with the payload decoy present, the "
                        "selection returns the on-disk stem digest value without any "
                        "wildcard glob",
                        f"wildcard glob used: {exc}",
                        False,
                    )
                )
            except SystemExit as exc:
                scenarios.append(
                    _scenario(
                        "real-entry-decoy-ignored",
                        "through the real entry with the payload decoy present, the "
                        "selection returns the on-disk stem digest value without any "
                        "wildcard glob",
                        f"SystemExit: {exc}",
                        False,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                scenarios.append(
                    _scenario(
                        "real-entry-decoy-ignored",
                        "through the real entry with the payload decoy present, the "
                        "selection returns the on-disk stem digest value without any "
                        "wildcard glob",
                        f"{type(exc).__name__}: {exc}",
                        False,
                    )
                )

    return {
        "task_id": "publication-digest",
        "acceptor_status": "OK",
        "verdict": _verdict(scenarios),
        "scenarios": scenarios,
    }


# ---------------------------------------------------------------------------
# Task: process-args
# ---------------------------------------------------------------------------


def _load_candidate_module(candidate_root: Path, relative: str, name: str) -> ModuleType:
    path = candidate_root / relative
    if not path.is_file():
        raise FileNotFoundError(f"{relative} is missing")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import machinery
        raise ImportError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses with slots=True resolve the class
    # module through sys.modules and fail when it is absent.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


class _StubProcess:
    def __init__(self) -> None:
        self.pid = 424242
        self.returncode = 0
        self.stdin = None
        self.stdout = None
        self.stderr = None

    def communicate(self, timeout: float | None = None):
        return "captured-out", "captured-err"

    def poll(self):
        return self.returncode

    def wait(self, timeout: float | None = None):
        return self.returncode

    def kill(self):
        return None


def accept_process_args(candidate_root: Path) -> dict:
    scenarios: list[dict] = []
    try:
        module = _load_candidate_module(
            candidate_root,
            "tools/aiwf_run_guard/procutil.py",
            "candidate_procutil",
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "task_id": "process-args",
            "acceptor_status": "OK",
            "verdict": "REJECT",
            "scenarios": [
                _scenario(
                    "procutil-loadable",
                    "tools/aiwf_run_guard/procutil.py loads standalone",
                    f"{type(exc).__name__}: {exc}",
                    False,
                )
            ],
        }

    real_popen = subprocess.Popen
    captured: dict[str, object] = {}

    def recording_popen(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        return _StubProcess()

    def check_contract(name: str, expectation: str, *, posix: bool) -> None:
        captured.clear()
        saved_posix = getattr(module, "_POSIX", None)
        try:
            module._POSIX = posix
            module.subprocess.Popen = recording_popen
            try:
                module.run_process_tree(["stub-command"])
            except Exception as exc:  # noqa: BLE001
                scenarios.append(
                    _scenario(name, expectation, f"run raised {type(exc).__name__}: {exc}", False)
                )
                return
            kwargs = captured.get("kwargs", {})
            if not isinstance(kwargs, dict):
                scenarios.append(_scenario(name, expectation, "no Popen kwargs captured", False))
                return
            if posix:
                passed = kwargs.get("start_new_session") is True and "creationflags" not in kwargs
                observed = (
                    f"start_new_session={kwargs.get('start_new_session')!r}, "
                    f"creationflags={'absent' if 'creationflags' not in kwargs else kwargs['creationflags']!r}"
                )
            else:
                flags = module._WINDOWS_CREATION_FLAGS
                expected = flags
                no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if flags:
                    expected = flags | no_window
                passed = (
                    kwargs.get("creationflags") == expected
                    and "start_new_session" not in kwargs
                )
                observed = (
                    f"creationflags={kwargs.get('creationflags')!r} (expected {expected!r}), "
                    f"start_new_session={'absent' if 'start_new_session' not in kwargs else kwargs['start_new_session']!r}"
                )
            scenarios.append(_scenario(name, expectation, observed, passed))
        finally:
            if saved_posix is not None:
                module._POSIX = saved_posix
            module.subprocess.Popen = real_popen

    check_contract(
        "posix-parameter-contract",
        "[parameter contract] with _POSIX true: start_new_session=True, no creationflags",
        posix=True,
    )
    check_contract(
        "windows-parameter-contract",
        "[parameter contract] with _POSIX false: combined creationflags, no start_new_session",
        posix=False,
    )

    # Dynamic verification (real runs). The module's platform flag must match
    # the actual host: on Windows _POSIX is False, so timeout cleanup takes
    # the real Windows path instead of calling POSIX-only os.killpg.
    module.subprocess.Popen = real_popen
    saved_posix = getattr(module, "_POSIX", None)
    module._POSIX = os.name == "posix"
    try:
        try:
            result = module.run_process_tree(
                [sys.executable, "-c", "print('acceptor-ok')"], timeout=60, label="echo"
            )
            passed = (
                result.returncode == 0
                and "acceptor-ok" in result.stdout
                and not result.timed_out
            )
            scenarios.append(
                _scenario(
                    "real-run-captures-output",
                    "real run captures stdout and exits 0",
                    f"returncode={result.returncode}, stdout={result.stdout.strip()!r}, timed_out={result.timed_out}",
                    passed,
                )
            )
        except Exception as exc:  # noqa: BLE001
            scenarios.append(
                _scenario(
                    "real-run-captures-output",
                    "real run captures stdout and exits 0",
                    f"{type(exc).__name__}: {exc}",
                    False,
                )
            )

        sleeper = "import time; time.sleep(30)"
        try:
            started = time.monotonic()
            result = module.run_process_tree(
                [sys.executable, "-c", sleeper], timeout=2, label="sleep"
            )
            elapsed = time.monotonic() - started
            # The contract is bounded tree termination: timed_out=True and a
            # prompt return. The reaped returncode is platform-dependent
            # (taskkill exit code on Windows, negative signal on POSIX), so
            # only the timing and the timed_out flag are asserted.
            passed = result.timed_out and elapsed < 20
            scenarios.append(
                _scenario(
                    "real-run-timeout-terminates",
                    "real run times out a sleeping child (timed_out=True, tree terminated promptly)",
                    f"timed_out={result.timed_out}, returncode={result.returncode}, elapsed={elapsed:.1f}s",
                    passed,
                )
            )
        except Exception as exc:  # noqa: BLE001
            scenarios.append(
                _scenario(
                    "real-run-timeout-terminates",
                    "real run times out a sleeping child (timed_out=True, returncode None)",
                    f"{type(exc).__name__}: {exc}",
                    False,
                )
            )
    finally:
        if saved_posix is not None:
            module._POSIX = saved_posix
        module.subprocess.Popen = real_popen

    return {
        "task_id": "process-args",
        "acceptor_status": "OK",
        "verdict": _verdict(scenarios),
        "scenarios": scenarios,
    }


# ---------------------------------------------------------------------------
# Task: bootstrap-refs
# ---------------------------------------------------------------------------


def _load_candidate_bootstrap(candidate_root: Path) -> ModuleType:
    package_root = candidate_root / "tools"
    if not (package_root / "governance_v2" / "bootstrap.py").is_file():
        raise FileNotFoundError("tools/governance_v2/bootstrap.py is missing")
    saved_path = list(sys.path)
    saved_modules = {
        name: sys.modules.pop(name)
        for name in (
            "tools",
            "tools.governance_v2",
            "tools.governance_v2.bootstrap",
            "tools.governance_v2.canonical",
        )
        if name in sys.modules
    }
    try:
        sys.path.insert(0, str(candidate_root))
        from tools.governance_v2 import bootstrap  # noqa: PLC0415 - candidate import
    finally:
        sys.path[:] = saved_path
    loaded = bootstrap
    for name, module in saved_modules.items():
        sys.modules[name] = module
    return loaded


def accept_bootstrap_refs(candidate_root: Path) -> dict:
    scenarios: list[dict] = []
    try:
        bootstrap = _load_candidate_bootstrap(candidate_root)
    except Exception as exc:  # noqa: BLE001
        return {
            "task_id": "bootstrap-refs",
            "acceptor_status": "OK",
            "verdict": "REJECT",
            "scenarios": [
                _scenario(
                    "bootstrap-loadable",
                    "tools/governance_v2/bootstrap.py imports from the candidate tree",
                    f"{type(exc).__name__}: {exc}",
                    False,
                )
            ],
        }

    def check_state(name: str, expectation: str, function, expected: dict[str, object]) -> None:
        """Run one scenario and assert the observed state matches expectations.

        A scenario passes only when the function returns and every expected
        key/value pair is present in the returned mapping; unexpected
        exceptions and wrong status codes both fail.
        """

        try:
            value = function()
        except Exception as exc:  # noqa: BLE001
            scenarios.append(
                _scenario(name, expectation, f"raised {type(exc).__name__}: {exc}", False)
            )
            return
        if not isinstance(value, dict):
            scenarios.append(
                _scenario(name, expectation, f"returned {type(value).__name__}, not a mapping", False)
            )
            return
        mismatches = {
            key: (value.get(key), expected_value)
            for key, expected_value in expected.items()
            if value.get(key) != expected_value
        }
        observed = json.dumps(
            {key: value.get(key) for key in expected},
            sort_keys=True,
        )
        passed = not mismatches
        if mismatches:
            observed += f"; mismatches={json.dumps(mismatches, sort_keys=True, default=str)}"
        scenarios.append(_scenario(name, expectation, observed, passed))

    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)

        repo = base / "repo"
        _init_repo(repo)

        def scenario_missing_cached():
            result = bootstrap.snapshot(
                root=repo,
                base_ref="origin/main",
                head_ref="origin/codex/release-v1.1.0",
            )
            return result

        check_state(
            "missing-refs-cached-not-raised",
            "missing refs without expected SHAs -> CACHED/LOCAL_BASELINE_INCOMPLETE",
            scenario_missing_cached,
            {"status": "CACHED", "code": "LOCAL_BASELINE_INCOMPLETE", "local_git_status": "AVAILABLE"},
        )

        def scenario_expected_blocked():
            return bootstrap.snapshot(
                root=repo,
                base_ref="origin/main",
                head_ref="origin/codex/release-v1.1.0",
                expected_base_sha="a" * 40,
            )

        check_state(
            "expected-ref-unavailable-blocked",
            "missing refs with an expected SHA -> BLOCKED/EXPECTED_REF_UNAVAILABLE",
            scenario_expected_blocked,
            {"status": "BLOCKED", "code": "EXPECTED_REF_UNAVAILABLE", "local_git_status": "AVAILABLE"},
        )

        completed = _run_git(repo, "branch", "base-branch")
        if completed.returncode != 0:
            raise AcceptorBlocked(
                f"git branch failed: {completed.stderr.strip()}"
            )

        def scenario_drift():
            return bootstrap.snapshot(
                root=repo,
                base_ref="base-branch",
                head_ref="base-branch",
                expected_base_sha="b" * 40,
            )

        check_state(
            "baseline-drift-blocked",
            "resolvable base with a wrong expected SHA -> BLOCKED/BASELINE_DRIFT",
            scenario_drift,
            {"status": "BLOCKED", "code": "BASELINE_DRIFT", "local_git_status": "AVAILABLE"},
        )

        def scenario_valid_baseline():
            return bootstrap.snapshot(
                root=repo,
                base_ref="base-branch",
                head_ref="base-branch",
            )

        check_state(
            "valid-baseline-cached",
            "valid resolvable baseline -> CACHED/LOCAL_BASELINE_ONLY",
            scenario_valid_baseline,
            {"status": "CACHED", "code": "LOCAL_BASELINE_ONLY", "local_git_status": "AVAILABLE"},
        )

        def scenario_non_repo():
            return bootstrap.snapshot(
                root=base / "not-a-repo",
                base_ref="origin/main",
                head_ref="origin/codex/release-v1.1.0",
            )

        check_state(
            "non-repo-unavailable",
            "empty non-repository directory -> CACHED/LOCAL_BASELINE_UNAVAILABLE",
            scenario_non_repo,
            {"status": "CACHED", "code": "LOCAL_BASELINE_UNAVAILABLE", "local_git_status": "NOT_AVAILABLE"},
        )

        saved_run = bootstrap.subprocess.run

        def scenario_git_error(side_effect) -> str:
            """Inject the failure only into ref classification.

            Commands other than ``git show-ref`` (top-level detection, ref
            resolution) delegate to the real Git so the scenario exercises
            the missing-ref classification stage, where an unclassifiable
            error must surface as BootstrapError instead of being cached as
            missing refs. Injecting into every Git call would instead hit
            the toplevel-unavailability path, whose cached result is the
            documented contract.
            """

            def patched(*arguments, **kwargs):
                command = arguments[0] if arguments else kwargs.get("args", [])
                if isinstance(command, (list, tuple)) and any(
                    str(part) == "show-ref" for part in command
                ):
                    raise side_effect
                return saved_run(*arguments, **kwargs)

            bootstrap.subprocess.run = patched
            try:
                bootstrap.snapshot(
                    root=repo,
                    base_ref="origin/main",
                    head_ref="origin/codex/release-v1.1.0",
                )
            except bootstrap.BootstrapError as exc:
                return f"raised BootstrapError ({getattr(exc, 'code', '?')})"
            except Exception as exc:  # noqa: BLE001
                return f"raised {type(exc).__name__}"
            finally:
                bootstrap.subprocess.run = saved_run
            return "returned normally"

        for error_name, side_effect in (
            ("timeout", subprocess.TimeoutExpired(cmd="git show-ref", timeout=15)),
            ("oserror", OSError("acceptor-injected")),
        ):
            try:
                observed = scenario_git_error(side_effect)
            finally:
                bootstrap.subprocess.run = saved_run
            scenarios.append(
                _scenario(
                    f"git-{error_name}-not-cached",
                    "unclassifiable Git errors during ref classification raise BootstrapError "
                    "and are never cached as missing refs",
                    observed,
                    observed.startswith("raised BootstrapError"),
                )
            )

    return {
        "task_id": "bootstrap-refs",
        "acceptor_status": "OK",
        "verdict": _verdict(scenarios),
        "scenarios": scenarios,
    }


ACCEPTORS = {
    "publication-digest": accept_publication_digest,
    "process-args": accept_process_args,
    "bootstrap-refs": accept_bootstrap_refs,
}


def run_acceptor(task_id: str, candidate_root: Path) -> dict:
    acceptor = ACCEPTORS.get(task_id)
    if acceptor is None:
        return {
            "task_id": task_id,
            "acceptor_status": "OK",
            "verdict": "REJECT",
            "scenarios": [
                _scenario("acceptor-registered", "acceptor exists for the task", "unknown task", False)
            ],
        }
    report = acceptor(candidate_root)
    report["acceptor_version"] = 2
    return report


if __name__ == "__main__":  # pragma: no cover - runner entry
    raise SystemExit("run through _acceptor_runner.py")
