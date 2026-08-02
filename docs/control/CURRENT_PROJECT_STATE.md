# CURRENT_PROJECT_STATE.md

Last Updated: 2026-08-02
State Version: v3.0
State Based On Parent Commit: 37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0
Last Confirmed Remote PR Head: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
Local Stop-State Commit: 37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0
Live Local HEAD: must be resolved with git rev-parse HEAD
Live Remote PR Head: must be refreshed from GitHub before push, review, merge, tag, or Release

Repository state record:
current for the documented stop condition

Remote state:
must be refreshed live before every remote transition

## 1. Current Project Phase

- Current Phase: RELEASE-CANDIDATE
- Phase Status: the original implementation sprint and the first
  publication-only sprint are both closed without a publication PASS; the
  final closeout task is planned and has not yet performed a new network write.
- Phase Goal: complete only the bounded final closeout sequence and publish
  v1.1.0 from a protected, independently reviewed merged main commit.
- Historical v1.0.0 remains published and immutable.

## 2. Current Task

- Task ID: RELEASE-V1.1.0-FINAL-CLOSEOUT
- Mode: Full
- State: new Task Packet is being established from the local stop baseline;
  the old publication task is sealed and cannot be used for another push.
- Required review: approval from another GitHub user; local implementation
  review is not sufficient.
- CodeGraph: optional maintainer capability; no real project-level index is
  claimed for v1.1.0.

## 3. Immutable RELEASE-V1.1.0 Closure

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

## 4. Immutable RELEASE-V1.1.0-PUBLISH Stop State

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

## 5. Local Stop Baseline Before the New Task

The read-only baseline captured before this Task Packet was created was:

- branch: codex/release-v1.1.0;
- local HEAD: 37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0;
- origin/codex/release-v1.1.0: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4;
- ahead/behind: local branch ahead by one commit;
- worktree: clean;
- v1.0.0: commit 643eac290b00561666692d41c55ceef546f12e15;
- local v1.1.0 tag: absent.

The previous live GitHub query confirmed that PR #2 was open and mergeable,
the 6e357d5 head passed its CI/Security checks, `reviewDecision` was
`REVIEW_REQUIRED`, and `reviews` was empty. That is a prior remote checkpoint,
not current live state after this task starts.

## 6. Canonical Contracts

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
- Template Doctor test helpers and primary CI/release jobs must remain bounded;
  outer job timeouts do not replace subprocess timeouts.

## 7. Active Priorities

1. Initialize the independent FINAL-CLOSEOUT Run Guard and record this
   stop-state bootstrap.
2. Complete only the bounded control, test-helper, and workflow-timeout
   changes in the new packet.
3. Validate and commit without amending 6e357d5 or 37fb3b4.
4. Push the final branch with the new plan's retry budget, then refresh all
   GitHub state before PR, review, merge, tag, or Release transitions.
5. Keep v1.0.0 unchanged and keep canonical remote artifacts separate from
   local mutable workspaces.

## 8. File-Count and Evidence Boundaries

The old task's counts remain historical evidence:

- final Git diff: 21 tracked files;
- execution-time unique touched files: 22;
- old Run Guard artifact files: 12/12;
- the extra execution-time path was the temporary `.planning/RELEASE-V1.1.0`
  bootstrap configuration later moved outside the repository.

The new task has its own artifact budget and stop-state JSON. These counts
must not be substituted for the old task's counts.

## 9. Stop Rules

- A new budget overrun, forbidden path, stale or corrupted Run Guard evidence,
  failed final check, missing independent review, blocked protected merge,
  failed merged-main validation, existing conflicting tag, failed tag
  workflow, or failed remote asset verification blocks all later publication.
- A network failure is not a code failure. Record `BLOCKED: network unavailable`
  and preserve the local commit and evidence.
- A missing independent approval must be reported as
  `BLOCKED: independent GitHub approval required`.

## 10. State Refresh Rule

The labels above intentionally separate the parent commit used to generate
this state record, the last confirmed remote PR head, the local stop-state
commit, and the live values that must be refreshed. Do not turn a remote
checkpoint into a claim about the current local HEAD.
