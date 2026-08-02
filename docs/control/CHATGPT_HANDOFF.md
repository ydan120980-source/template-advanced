# CHATGPT_HANDOFF.md

Last Updated: 2026-08-02
Based On State Version: v3.2

## New-session summary

- Historical v1.0.0 remains published and unchanged.
- RELEASE-V1.1.0 remains implementation-complete, locally validated, and
  governance-failed because its command budget was 166/160.
- RELEASE-V1.1.0-PUBLISH is sealed as a blocked publication task.
- RELEASE-V1.1.0-FINAL-CLOSEOUT is sealed at the review gate for exact remote
  candidate `cfcafade749f1efaeb5387b62a6d9feb3fcea390`: its exact-head
  CI/Security passed, independent GitHub approval is missing, and a new
  cross-environment test race was discovered.
- New task: RELEASE-V1.1.0-FLAKE-FIX.
- New task goal: remove the Python-interpreter startup dependency from the
  partial-output timeout test, retain deterministic mock contracts, add the
  no-output timeout contract, then push the new PR head, wait for exact-head
  CI/Security, and stop at the independent GitHub review gate. Merge, tag,
  and Release happen only after a real approval.

## Known issue and fix

The real-process partial-output test
(`test_timeout_preserves_partial_stdout_and_stderr`) started a new Python
interpreter and assumed it would print within one second. On slow Linux, VM,
or high-load hosts the timeout can fire before any output exists, and empty
stdout/stderr are legal results from `run_process_tree()`.

Fix: the test now uses an immediate platform-native shell command before a
bounded long-running wait (`sh` builtin `printf` with `exec sleep` on POSIX;
`cmd.exe` builtin `echo` with a local-loopback `ping` on Windows). A
deterministic mock test still covers preservation of already-captured
partial output, and a new mock test documents that a timeout before any
output legally returns empty streams. Production `run_process_tree()`
semantics are unchanged.

Previous exact remote candidate:

    cfcafade749f1efaeb5387b62a6d9feb3fcea390

Previous candidate approval: not requested as final approval because the PR
head must change. Publication: not completed. Do not describe `cfcafad` as
the final commit awaiting review.

## Exact old publication stop state

    Task ID: RELEASE-V1.1.0-PUBLISH
    Implementation correction: completed
    Remote candidate CI/Security: passed for 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
    Final local stop-state commit: 37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0
    Final local stop-state commit pushed: no
    Retry usage: 2/2
    Latest network failure: unresolved
    Validation state: stale after the latest failure event under the old plan
    GitHub human review: missing
    Publication: not completed
    Final gate: not_ready
    Superseded by: RELEASE-V1.1.0-FINAL-CLOSEOUT

The old plan must not be used for another push. Do not alter its budgets,
delete its failure event, fabricate validation, or report it as successful.
The redacted stop record is
`docs/control/evidence/RELEASE-V1.1.0-PUBLISH_STOP.json`.

## Exact FINAL-CLOSEOUT review-gate stop

    Task ID: RELEASE-V1.1.0-FINAL-CLOSEOUT
    Implementation and evidence correction: completed
    Exact remote candidate: cfcafade749f1efaeb5387b62a6d9feb3fcea390
    Exact-head CI/Security: passed (CI 30743336624, Security 30743336620,
    additional CodeQL passed)
    Independent GitHub approval: missing
    New cross-environment test race discovered: yes
    Publication: not completed
    Final gate: not_ready
    Superseded by: RELEASE-V1.1.0-FLAKE-FIX

## Local baseline captured before the new packet

- branch: codex/release-v1.1.0;
- local HEAD and origin/codex/release-v1.1.0:
  cfcafade749f1efaeb5387b62a6d9feb3fcea390;
- ahead/behind: 0/0;
- worktree: clean;
- v1.0.0 commit: 643eac290b00561666692d41c55ceef546f12e15;
- local v1.1.0 tag: absent.

The previous live GitHub checkpoint had PR #2 open and mergeable with head
`cfcafad`, `reviewDecision=REVIEW_REQUIRED`, and `reviews=[]`. Refresh GitHub
live state after the new head is pushed; do not reuse that checkpoint.

## New task boundaries

Allowed repository changes are limited to `tests/aiwf_run_guard/test_procutil.py`,
`docs/control/NEXT_CODEX_TASK.md`, `docs/control/CURRENT_PROJECT_STATE.md`,
`docs/control/CHATGPT_HANDOFF.md`, and `docs/control/SPRINT_LEDGER.md`.
`tools/aiwf_run_guard/procutil.py` may change only if tests prove a real
output-loss defect; it must not be altered to make tests pass.

Frozen budgets: file 6, artifact 6, retry 2, shell-command 70. A new isolated
Run Guard plan named RELEASE-V1.1.0-FLAKE-FIX lives outside the repository;
it does not reuse earlier budgets or events.

## Required sequence

1. Initialize the independent FLAKE-FIX Run Guard before implementation.
2. Commit the Task Packet, then the test and control-state changes.
3. Run focused repetition validation (10/10 single test, 5/5 module with
   `-W error::ResourceWarning`) and the complete full chain from the final
   local commit.
4. Push only `codex/release-v1.1.0` with initial attempt plus at most two
   retries.
5. Confirm PR #2 head equals the final local commit, then correct the PR body
   so it no longer lists fixed test totals and requires approval from another
   GitHub user.
6. Wait for exact-head CI/Security and stop if any check fails or is
   incomplete.
7. Stop with `BLOCKED: independent GitHub approval required` until a real
   APPROVED review of the new head exists.
8. After approval only: merge through protection, validate merged main, tag
   v1.1.0 from merged main, wait for the tag workflow, and independently
   verify the downloaded canonical assets and tagged source.
9. Clean temporary directories and record the final Run Guard gate.

Never self-review, bypass protection, force-push, move v1.0.0, upload local
artifacts, or report publication success without every gate.

## State label rule

`CURRENT_PROJECT_STATE.md` intentionally uses separate fields for the parent
commit of the state record, last confirmed remote PR head, local stop-state
commit, and live values requiring refresh. A remote checkpoint must never be
called the current local HEAD, and `cfcafad` evidence must never be presented
for a later head.
