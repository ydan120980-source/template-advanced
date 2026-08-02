# CURRENT_PROJECT_STATE.md

Last Updated: 2026-08-02
State Version: v3.2
State Based On Parent Commit: cfcafade749f1efaeb5387b62a6d9feb3fcea390
Last Confirmed Remote PR Head: cfcafade749f1efaeb5387b62a6d9feb3fcea390
Local Stop-State Commit: cfcafade749f1efaeb5387b62a6d9feb3fcea390
Current Closeout Commit: cfcafad is the last pre-fix head and must be
superseded by the new RELEASE-V1.1.0-FLAKE-FIX head once committed and pushed
Live Local HEAD: must be resolved with git rev-parse HEAD
Live Remote PR Head: must be refreshed from GitHub before push, review,
merge, tag, or Release

Repository state record:
current for the documented stop condition

Remote state:
must be refreshed live before every remote transition

## 1. Current Project Phase

- Current Phase: RELEASE-CANDIDATE
- Phase Status: v1.1.0 publication is blocked at the independent GitHub
  review gate; a cross-environment test race in the partial-output timeout
  test was discovered after the previous exact-head checks passed, so the
  new FLAKE-FIX task is active and the PR head must change.
- Phase Goal: fix the test race, re-establish exact-head CI/Security for the
  new PR head, obtain an independent GitHub approval, then complete protected
  merge, v1.1.0 tag, tag workflow, and canonical asset verification.
- Historical v1.0.0 remains published and immutable.

## 2. Current Task

- Task ID: RELEASE-V1.1.0-FLAKE-FIX
- Mode: Full
- State: Task Packet committed (`a99e502`); the partial-output timeout test
  no longer depends on Python interpreter startup speed; focused Windows
  validation passed (repeated single-test runs and repeated module runs with
  `-W error::ResourceWarning`, no residual test processes). Full validation
  from the final local commit, push, and exact-head remote checks are the
  next steps.
- Required review: approval from another GitHub user on the new PR head;
  local implementation review is not sufficient.
- CodeGraph: optional maintainer capability; no real project-level index is
  claimed for v1.1.0.

## 3. Known Issue Record

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

`cfcafad` is no longer described as the final commit awaiting review.

## 4. Immutable RELEASE-V1.1.0 Closure

    Implementation: completed
    Local validation: passed
    Governance final gate: failed
    Reason: command budget exceeded, 166/160
    Scope compliance: PARTIAL
    Owner exception required: YES
    Publication: not completed
    Superseded by: RELEASE-V1.1.0-PUBLISH

The original task exceeded its command budget by six shell-command requests.
Its historical budget and event ledger remain unchanged. The CodeGraph path
was added retroactively to that task and remains an owner-accepted scope
exception; this does not prove the old scope was respected.

## 5. Immutable RELEASE-V1.1.0-PUBLISH Stop State

    Implementation correction: completed
    Remote candidate: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
    Remote candidate CI/Security: passed for that commit
    Final local stop-state commit: 37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0
    Final local stop-state commit pushed: no
    Retry usage: 2/2
    Latest network failure: unresolved
    Validation state: stale after the latest failure event under the old plan
    GitHub human review: missing
    Publication: not completed
    Final gate: not_ready
    Superseded by: RELEASE-V1.1.0-FINAL-CLOSEOUT

The old publication task cannot execute another push. Its retry budget is
exhausted, its final network failure remains unresolved, and the last
validation evidence is stale under that plan. No old validation or review
event is being recreated or deleted.

The redacted machine-readable record is
`docs/control/evidence/RELEASE-V1.1.0-PUBLISH_STOP.json`.

## 6. Immutable RELEASE-V1.1.0-FINAL-CLOSEOUT Review-Gate Stop

    Task ID: RELEASE-V1.1.0-FINAL-CLOSEOUT
    Implementation and evidence correction: completed
    Exact remote candidate: cfcafade749f1efaeb5387b62a6d9feb3fcea390
    Exact-head CI/Security: passed
    Independent GitHub approval: missing
    New cross-environment test race discovered: yes
    Publication: not completed
    Final gate: not_ready
    Superseded by: RELEASE-V1.1.0-FLAKE-FIX

The FINAL-CLOSEOUT exact-head evidence (CI run 30743336624, Security run
30743336620, additional CodeQL check) is historical evidence for `cfcafad`
only. It must not be presented as evidence for the new FLAKE-FIX head.

## 7. FLAKE-FIX Baseline and Checkpoint

The read-only baseline captured before the new Task Packet was created was:

- branch: codex/release-v1.1.0;
- local HEAD: cfcafade749f1efaeb5387b62a6d9feb3fcea390;
- origin/codex/release-v1.1.0: cfcafade749f1efaeb5387b62a6d9feb3fcea390;
- ahead/behind: 0/0;
- worktree: clean;
- v1.0.0: commit 643eac290b00561666692d41c55ceef546f12e15;
- local v1.1.0 tag: absent.

The previous live GitHub query confirmed PR #2 was open and mergeable with
head `cfcafad`, `reviewDecision=REVIEW_REQUIRED`, and `reviews=[]`. That is a
prior remote checkpoint, not current live state after the new head is pushed.

New task budgets are frozen at file 6, artifact 6, retry 2, and
shell-command 70. The Task Packet commit is `a99e502`; the test-fix commit
and exact local SHA are resolved from Git.

## 8. Canonical Contracts

- Release builds read release files from the Git object database at HEAD and
  refuse dirty, missing, or untracked release files.
- Canonical Release artifacts are deterministic ZIP, manifest, digest, and
  SHA256SUMS outputs produced by the tag workflow.
- A Git source archive is traceable committed-tree content; its ZIP bytes are
  not promised to be cross-platform deterministic.
- Protected main/PR validation is the Ubuntu/Windows/macOS Python 3.11-3.13
  matrix plus CodeQL and credential scanning.
- The tag workflow is a separate configured Ubuntu/Python 3.13 release chain;
  it does not claim to rerun the full protected matrix.
- Release build-and-verify has contents read; publish alone has contents
  write. CodeQL alone has security-events write; credential scan has contents
  read.
- CodeGraph is optional. Missing index is non-blocking in default mode and
  blocking in strict mode. A corrupt or structurally unrecognized database
  blocks all modes. No official schema or real index is claimed.
- The real-process timeout tests use immediate platform-native shell output
  and must not depend on Python interpreter startup speed.

## 9. Active Priorities

1. Complete full validation from the final local FLAKE-FIX commit, push the
   branch, and confirm the new PR head.
2. Wait for the new exact-head CI/Security; any failure or incomplete check
   stops merge, tag, and Release.
3. Stop at `BLOCKED: independent GitHub approval required` until a real
   APPROVED review of the new head exists; do not self-review or bypass
   branch protection.
4. Keep v1.0.0 unchanged and keep canonical remote artifacts separate from
   local mutable workspaces.

## 10. File-Count and Evidence Boundaries

The old tasks' counts remain historical evidence:

- original RELEASE-V1.1.0: 21 tracked files in the final Git diff, 22
  execution-time unique touched files, 12/12 old Run Guard artifact files;
- RELEASE-V1.1.0-PUBLISH: 12 changed files, 12 artifact files, 100 shell
  requests, 2 retries;
- RELEASE-V1.1.0-FINAL-CLOSEOUT: 12 changed files, 10 artifact files, 90
  shell requests, 2 retries.

The new task has its own frozen budgets (file 6, artifact 6, retry 2, shell
70) and its own isolated Run Guard plan outside the repository root. These
counts must not be substituted for old-task counts.

## 11. Stop Rules

- A new budget overrun, forbidden path, stale or corrupted Run Guard
  evidence, failed final check, missing independent review, blocked
  protected merge, failed merged-main validation, existing conflicting tag,
  failed tag workflow, or failed remote asset verification blocks all later
  publication.
- A network failure is not a code failure. Record `BLOCKED: network
  unavailable` and preserve the local commit and evidence.
- A missing independent approval must be reported as
  `BLOCKED: independent GitHub approval required`.

## 12. State Refresh Rule

The labels above intentionally separate the parent commit used to generate
this state record, the last confirmed remote PR head, the local stop-state
commit, and the live values that must be refreshed. Do not turn a remote
checkpoint into a claim about the current local HEAD, and do not present
`cfcafad` CI/Security evidence as proof for a later head.
