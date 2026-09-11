"""Locked task definitions for workflow comparison trials.

Each definition freezes one historical repair: the pre-fix baseline commit
the trial starts from, the historical fix commit the acceptor must accept,
the observed contract the acceptor grades, and the task statement handed to
trial agents. Definitions are data, not code paths: acceptors read the
contract fields below and never trust trial-side claims.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    task_id: str
    title: str
    pre_fix_sha: str
    fix_sha: str
    allowed_paths: tuple[str, ...]
    brief_goal: str
    brief_contract: tuple[str, ...]
    brief_acceptance: tuple[str, ...]
    brief_context: str

    @property
    def allowed_paths_text(self) -> str:
        return "\n".join(f"- {path}" for path in self.allowed_paths)

    @property
    def contract_text(self) -> str:
        return "\n".join(f"- {item}" for item in self.brief_contract)

    @property
    def acceptance_text(self) -> str:
        return "\n".join(f"- {item}" for item in self.brief_acceptance)


TASKS: dict[str, TaskDefinition] = {
    "publication-digest": TaskDefinition(
        task_id="publication-digest",
        title="Publication digest selection",
        pre_fix_sha="66fcca247b3bbd515aace83643b9d4dd3e1028f7",
        fix_sha="01d565b31ef12bd7be16555e6f1152eda3e348aa",
        allowed_paths=("evals/",),
        brief_goal=(
            "In this source tree, `evals/run-evals.sh` embeds a Python eval "
            "harness. Inside its `build_release(out_dir)` helper, release "
            "metadata is selected with wildcard globs: "
            "`next(out_dir.glob(\"*.manifest.json\"))` picks the manifest and "
            "`next(out_dir.glob(\"*.digest.txt\"))` picks the publication "
            "digest, so empty results raise bare StopIteration errors and a "
            "`<stem>.payload.digest.txt` decoy can be selected instead of the "
            "real publication digest. Harden digest selection so release "
            "metadata can never be misread."
        ),
        brief_contract=(
            "The manifest/digest selection logic must keep working on a given "
            "build-output directory and must:",
            "require exactly one `*.manifest.json` in the directory and exit "
            "with a clear error when zero or multiple manifests exist;",
            "derive the publication digest file name from the manifest stem "
            "(`<stem>.digest.txt`) instead of any wildcard glob, and exit "
            "with a clear error when that exact file is missing;",
            "compare the digest file content against the manifest's "
            "`publication_digest` and exit on disagreement;",
            "select the publication digest deterministically even when a "
            "`<stem>.payload.digest.txt` decoy file is present next to the "
            "real digest file.",
            "Keep the selection logic contiguous inside the eval heredoc: it "
            "must start at the assignment that lists manifests via "
            "`glob(\"*.manifest.json\")` and end by returning the manifest "
            "dict, so it stays directly executable against a given output "
            "directory.",
        ),
        brief_acceptance=(
            "zero manifests -> clear failure; duplicate manifests -> clear "
            "failure; manifest without its stem digest file -> clear failure; "
            "digest file content differing from the manifest -> clear failure; "
            "payload-digest decoy present -> the real stem digest is selected "
            "and its content matches the manifest.",
        ),
        brief_context=(
            "The selection logic is exercised by the existing "
            "`release-determinism` and `clean-template-init` eval cases; do "
            "not break them. Keep the standard-library-only constraint of the "
            "harness and keep the whole change inside `evals/`.",
        ),
    ),
    "process-args": TaskDefinition(
        task_id="process-args",
        title="Cross-platform process start arguments",
        pre_fix_sha="6e8c9053fd2e01df80641b8fe719548646be1eb9",
        fix_sha="f5e3b53182be2d8adf34872c0311e737028aa09e",
        allowed_paths=("tools/aiwf_run_guard/procutil.py", "tests/aiwf_run_guard/"),
        brief_goal=(
            "In this source tree, `tools/aiwf_run_guard/procutil.py` provides "
            "`run_process_tree(...)` for bounded validation commands. Its "
            "`subprocess.Popen` call currently passes "
            "`creationflags=creation_flags if creation_flags else None` on "
            "every platform, which raises `ValueError: creationflags is only "
            "supported on Windows platforms` on POSIX. Separate the platform "
            "start arguments so POSIX execution works again."
        ),
        brief_contract=(
            "`run_process_tree` must call `subprocess.Popen` with platform "
            "separated arguments built as a kwargs mapping:",
            "on POSIX (`module global _POSIX` true): pass "
            "`start_new_session=True` and no `creationflags` key;",
            "on Windows (`_POSIX` false): pass `creationflags` combining the "
            "module's `_WINDOWS_CREATION_FLAGS` with `CREATE_NO_WINDOW` when "
            "that flag is available, and no `start_new_session` key;",
            "timeout, process-tree termination, and captured-output behavior "
            "must keep working as before.",
        ),
        brief_acceptance=(
            "with `_POSIX` true, Popen receives `start_new_session=True` and "
            "no `creationflags`; with `_POSIX` false, Popen receives the "
            "combined `creationflags` and no `start_new_session`; a real run "
            "captures output and exits 0; a real run against a sleeping "
            "process reports `timed_out=True` and the whole child tree is "
            "terminated promptly (the reaped exit code is platform-dependent).",
        ),
        brief_context=(
            "Callers live in `scripts/integration-test-release.sh` stages and "
            "release tooling; they rely on the current signature "
            "(`command, *, cwd, env, timeout, label, text, encoding`) and the "
            "`ProcessResult` contract. Keep the standard-library-only rule.",
        ),
    ),
    "bootstrap-refs": TaskDefinition(
        task_id="bootstrap-refs",
        title="Bootstrap missing-reference handling",
        pre_fix_sha="0226dbea76d0113992f8f5f9606ad0bd0ab8ef21",
        fix_sha="35f19d550a67711a93febd2db06583f9e932a9e1",
        allowed_paths=("tools/governance_v2/bootstrap.py", "tests/governance_v2/"),
        brief_goal=(
            "In this source tree, `tools/governance_v2/bootstrap.py` "
            "implements `snapshot(...)` for read-only Stage 0 bootstrap "
            "snapshots. When a required local ref such as `origin/main` is "
            "absent, the current code raises a raw `BootstrapError` from "
            "`rev-parse`, so CI jobs cannot distinguish an expected incomplete "
            "baseline from a real Git failure. Classify unavailable refs "
            "instead of failing blindly."
        ),
        brief_contract=(
            "`snapshot(...)` must return a result dict (never raise) in these "
            "ref-unavailability cases, while preserving all existing codes:",
            "required refs missing in an available repository, no expected "
            "SHAs given -> status `CACHED`, code `LOCAL_BASELINE_INCOMPLETE`;",
            "required refs missing in an available repository, an expected "
            "`base_sha`/`head_sha` given -> status `BLOCKED`, code "
            "`EXPECTED_REF_UNAVAILABLE`;",
            "`BASELINE_DRIFT` and `PR_HEAD_DRIFT` classification must keep "
            "working when refs do resolve;",
            "Git unavailability or other unclassifiable Git errors must never "
            "be reported as missing refs: the snapshot stays `CACHED` / "
            "`LOCAL_BASELINE_UNAVAILABLE` outside a repository and raises "
            "`BootstrapError` when Git itself fails; missing-ref "
            "classification must consult `git show-ref --verify` candidates "
            "(`ref`, `refs/heads/<ref>`, `refs/remotes/<ref>`, "
            "`refs/tags/<ref>`) and treat only exit code 1 as 'ref absent'.",
        ),
        brief_acceptance=(
            "temp repository without the requested refs and without expected "
            "SHAs -> CACHED/LOCAL_BASELINE_INCOMPLETE; same repository with "
            "an expected base SHA -> BLOCKED/EXPECTED_REF_UNAVAILABLE; "
            "resolvable base with a wrong expected SHA -> BLOCKED/"
            "BASELINE_DRIFT; empty non-repository directory -> CACHED/"
            "LOCAL_BASELINE_UNAVAILABLE; Git timeouts or OSErrors raise "
            "BootstrapError instead of being cached; a valid baseline still "
            "returns CACHED/LOCAL_BASELINE_ONLY.",
        ),
        brief_context=(
            "Callers treat snapshot results as evidence: never cache an "
            "unverified fact. Keep the standard-library-only rule and the "
            "existing result keys (`status`, `code`, `local_git_status`, "
            "`base_sha`, `head_sha`, `current_branch`, `current_head_sha`, "
            "`snapshot_digest`, metadata).",
        ),
    ),
}

TASK_ORDER = ("publication-digest", "process-args", "bootstrap-refs")


def get_task(task_id: str) -> TaskDefinition:
    try:
        return TASKS[task_id]
    except KeyError:
        raise KeyError(f"unknown task {task_id!r}; known: {', '.join(TASK_ORDER)}") from None


def task_ids() -> tuple[str, ...]:
    return tuple(TASK_ORDER)


CONTROL_HEADER = """\
# Task: {title}

{goal}

## Observed contract to satisfy

{contract}

## Acceptance

{acceptance}

## Context

{context}

You may modify exactly these paths: {allowed}.

Work independently: implement the change, then verify it yourself with the
commands you consider sufficient. Budget: at most 15 minutes and 25
shell-bearing tool requests; exhausted budgets are recorded honestly. Do not
rewrite unrelated code. When finished, return a short summary: what changed,
which files, how you verified it, and any residual risk.
"""

AIWF_HEADER = """\
# [AIWF Task] Workflow trial: {title}

## Goal

{goal}

## Observed contract to satisfy

{contract}

## Acceptance

{acceptance}

## Context

{context}

## Task contract (AIWF structured flow)

- Allowed Paths:
{allowed}
- Forbidden Paths: everything outside Allowed Paths; acceptor and eval
  definitions outside this tree are read-only for you.
- Budget: at most 15 minutes, at most 25 shell-bearing tool requests, at
  most 1 retry per failing validation.
- Validation: run focused commands that demonstrate the Acceptance bullets;
  report each native exit code honestly (CACHED/NOT_RUN/BLOCKED states are
  not passes).
- Stop Conditions: a required file is missing; the change needs paths
  outside Allowed Paths; a public contract beyond the described one must
  change; validation cannot run; the budget is exhausted.
- Required Return Format: an Evidence Ledger with (1) Goal, (2) Files
  changed, (3) Commands run with native exit codes, (4) Validation result,
  (5) Scope check against Allowed Paths, (6) Risks and known TODOs,
  (7) Follow-up recommendation.

Execute only within this contract; do not expand scope silently.
"""


def render_brief(task: TaskDefinition, *, group: str) -> str:
    fields = {
        "title": task.title,
        "goal": task.brief_goal,
        "contract": task.contract_text,
        "acceptance": task.acceptance_text,
        "context": task.brief_context,
        "allowed": task.allowed_paths_text,
    }
    if group == "experiment":
        return AIWF_HEADER.format(**fields)
    return CONTROL_HEADER.format(**fields)
