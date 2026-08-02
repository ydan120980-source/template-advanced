# NEXT_CODEX_TASK.md

Task ID: RELEASE-V1.1.0-FLAKE-FIX
Task Size: Full
Workflow Mode: Full
Status: planned; initialize the new Run Guard before implementation work

This task supersedes the review-gate-blocked RELEASE-V1.1.0-FINAL-CLOSEOUT
task. The old task and all earlier tasks remain immutable historical
evidence; their budgets, events, failure facts, and gates must not be
rewritten or reused.

## Historical closure

RELEASE-V1.1.0-FINAL-CLOSEOUT is sealed with this exact result:

    Task ID: RELEASE-V1.1.0-FINAL-CLOSEOUT
    Implementation and evidence correction: completed
    Exact remote candidate: cfcafade749f1efaeb5387b62a6d9feb3fcea390
    Exact-head CI/Security: passed
    Independent GitHub approval: missing
    New cross-environment test race discovered: yes
    Publication: not completed
    Final gate: not_ready
    Superseded by: RELEASE-V1.1.0-FLAKE-FIX

The old task used its full artifact budget and its exact-head evidence becomes
invalid once the PR head changes. Do not fold the new test-file change into
the old task and do not expand the old artifact budget.

The released template onboarding baseline remains TEMPLATE-ONBOARDING-V1.

## Known issue record

    Known issue:
    The real-process partial-output test depended on a new Python interpreter
    starting and printing within one second.

    Classification:
    Cross-environment test race, not confirmed production output loss.

    Fix:
    Use immediate platform-native shell output before a bounded long-running
    command, and retain deterministic mock coverage for partial-output
    preservation.

    Previous exact remote candidate:
    cfcafade749f1efaeb5387b62a6d9feb3fcea390

    Previous candidate approval:
    not requested as final approval because the PR head must change

    Publication:
    not completed

Do not continue to describe `cfcafad` as the final commit awaiting review.

## Goal

Only:

1. Fix the timeout partial-output test startup race;
2. add the corresponding contract regression tests;
3. update the necessary control state;
4. run the complete local validation;
5. push the existing PR branch;
6. wait for the new exact-head CI/Security;
7. stop at the independent GitHub review gate;
8. after a real independent approval, complete the protected merge, tag
   v1.1.0 from merged main, and verify the remote canonical artifacts.

## Non-goals

- Do not modify the production behavior of `run_process_tree()` unless tests
  prove a real output-loss defect.
- Do not refactor the process execution framework.
- Do not add arbitrary sleeps or global delays.
- Do not expand the CI platform matrix.
- Do not modify CodeGraph contracts.
- Do not change the version selection.
- Do not redesign the Release pipeline.
- Do not modify v1.0.0.
- Do not perform unrelated documentation cleanup.
- Do not initialize a fake CodeGraph index.

## Allowed Paths

- tests/aiwf_run_guard/test_procutil.py
- docs/control/NEXT_CODEX_TASK.md
- docs/control/CURRENT_PROJECT_STATE.md
- docs/control/CHATGPT_HANDOFF.md
- docs/control/SPRINT_LEDGER.md

`tools/aiwf_run_guard/procutil.py` is permitted only if the tests prove that
the production contract actually loses already-captured output. It is not a
planned change and must not be modified to make a test pass or to fabricate
output.

External GitHub writes are limited to PR #2 and its existing feature branch
`codex/release-v1.1.0`. No merge, tag, or Release action may occur before a
real independent GitHub approval and fresh exact-head checks.

## Forbidden Paths and Actions

- .git/, .claude/settings.local.json, dist/, release-a/, release-b/,
  __pycache__/, *.pyc, *.pyo, .planning/, .env, .env.*;
- credentials, secrets, dependency manifests, CI platform changes, Release
  builder redesign, unrelated documents;
- changing old budgets, deleting old events, changing old gates to PASS, or
  fabricating validation/review events;
- amend, rebase, history rewrite, force-push, self-review, administrator
  bypass, review deletion, or branch-protection changes;
- making the timeout test pass by lengthening the timeout beyond the bounded
  platform helper window, skipping slow environments, waiting for specific
  output in production code, restarting timed-out commands, or filling empty
  output with placeholder text;
- creating v1.1.0 before a protected merge and merged-main validation;
- uploading local artifacts instead of successful tag-workflow artifacts;
- infinite GitHub polling, infinite network retries, or any action after a
  stop condition.

## Budget

Frozen before the first change:

    file budget: 6
    artifact budget: 6
    retry budget: 2
    shell-command budget: 70

Budgets must not be expanded later. The Task Packet counts as a delivery
artifact. The isolated Run Guard plan and its JSONL live outside the
repository and do not enter the Release.

## Run Guard

Classification: required.

Initialize a new isolated plan named RELEASE-V1.1.0-FLAKE-FIX before
implementation work. Do not reuse the budgets or events of the three previous
tasks. The new plan records:

- the known failing test and failure environment;
- reproduction attempts;
- modified files;
- focused and full validation;
- push;
- new PR head;
- new exact-head CI/Security;
- GitHub review;
- merge, tag, Release, and remote assets only after approval;
- the final gate.

Historical gates and failure facts of earlier tasks remain unchanged.

## Validation

Run fail-fast from the repository root and check every native exit code
before the next command.

Focused (Windows):

    py -3 -B -m unittest tests.aiwf_run_guard.test_procutil.ProcessTreeTimeoutTests.test_timeout_preserves_partial_stdout_and_stderr

Run the single test 10 times and the whole procutil module 5 times with
`-W error::ResourceWarning`. Confirm no ResourceWarning and no residual
test-created process tree. Never kill processes globally by name.

Focused (POSIX/Linux):

    python3 -B -m unittest tests.aiwf_run_guard.test_procutil.ProcessTreeTimeoutTests.test_timeout_preserves_partial_stdout_and_stderr

Same repetition requirements: 10/10 single tests and 5/5 module runs, no
ResourceWarning, no residual `sleep`, `sh`, or test child processes.

Full local chain (Windows):

    py -3 -B -m unittest discover -s tests
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/verify.sh
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 evals/run-evals.sh
    py -3 -B -m tools.template_doctor --root . --format json
    py -3 -B scripts/ci-doctor-gate.py --root .
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/integration-test-release.sh
    git diff --check

POSIX equivalents use `python3 -B`, `bash scripts/verify.sh`,
`bash evals/run-evals.sh`, `python3 -B -m tools.template_doctor --root .
--format json`, `python3 -B scripts/ci-doctor-gate.py --root .`, and
`bash scripts/integration-test-release.sh`.

Acceptance: all applicable unit tests pass (platform-specific skips only as
designed), Verify passes, Eval 8/8, default Doctor has no blocking failure,
CI Doctor gate passes, Release integration passes, no ResourceWarning, no
hang, no cache, no residual process, and the worktree is clean before push.

## Publication sequence

1. Commit the new Task Packet, then commit the test and control-state changes
   without amending `cfcafad`.
2. Run the complete validation from the final local commit.
3. Push only `codex/release-v1.1.0` with an initial attempt plus at most two
   retries.
4. Fetch and confirm the PR head equals the final local commit.
5. Correct the PR body so it no longer lists fixed test totals and explicitly
   requires approval from another GitHub user.
6. Wait for the new exact-head CI/Security; any failure or incomplete check
   stops merge, tag, and Release.
7. Require `reviewDecision=APPROVED` from another GitHub user. If review is
   missing, stop with `BLOCKED: independent GitHub approval required`.
8. After approval only: merge through protection, update local main with a
   fast-forward, revalidate merged main, create annotated v1.1.0 from merged
   main, wait for the tag workflow and non-draft/non-prerelease Release, and
   verify checksum/manifest/digest/tagged-source/source-archive hygiene.

## Stop Conditions

Stop all later publication actions on any of:

- new budget overrun, forbidden path change, or corrupted Run Guard evidence;
- final branch cannot be pushed or PR head differs from the final commit;
- final-head CI/Security fails, is incomplete, or cannot be identified;
- another GitHub user has not approved the PR;
- protected merge, merged-main equality, or merged-main validation fails;
- v1.1.0 already exists and is absent or points to a different commit;
- tag workflow, Release metadata, checksum, manifest, digest, tagged-source
  validation, or source-archive hygiene fails;
- the new Run Guard final gate is not ready.

Use exact failure labels:

    BLOCKED: network unavailable
    FAIL: final PR head checks failed
    BLOCKED: independent GitHub approval required

Never report publication complete after a stop condition.

## Required Return Format

Return an Evidence Ledger with:

- immutable closure facts for RELEASE-V1.1.0-FINAL-CLOSEOUT and the new
  RELEASE-V1.1.0-FLAKE-FIX task;
- race-fix table (Python startup dependency removed, POSIX immediate-output
  command, Windows immediate-output command, partial-output mock contract,
  no-output timeout contract, production semantics unchanged);
- stability repetition table (Windows and Linux/POSIX single-test and module
  runs, ResourceWarning, residual processes);
- full validation results;
- Git/PR facts (Task Packet commit, fix commit, local/remote SHA, PR head and
  URL, review decision, merge/main SHA only when reached);
- only new exact-final-head CI/Security run IDs and URLs;
- tag/Release/remote-asset facts only when reached;
- Run Guard task ID, events, artifacts, retries, command budget, and final
  gate;
- remaining risks and one bounded next step.

Missing evidence is BLOCKED or FAIL, never PASS.
