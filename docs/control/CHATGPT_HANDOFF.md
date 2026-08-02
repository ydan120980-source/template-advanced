# CHATGPT_HANDOFF.md

Last Updated: 2026-08-02
Based On State Version: v3.1

## New-session summary

- Historical v1.0.0 remains published and unchanged.
- RELEASE-V1.1.0 remains implementation-complete, locally validated, and
  governance-failed because its command budget was 166/160.
- RELEASE-V1.1.0-PUBLISH is sealed as a blocked publication task.
- Its remote candidate `6e357d55f813bdc6a823ea0f94fd8ef01ee54de4` passed the
  recorded CI/Security checks, but its local stop-state commit
  `37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0` was never pushed.
- The old task used its retry budget 2/2; its final network failure is
  unresolved and its validation evidence is stale under that old plan.
- New task: RELEASE-V1.1.0-FINAL-CLOSEOUT.
- New task goal: close the stop state, add bounded helper/job execution,
  correct PR evidence, then complete protected merge/tag/Release verification
  only after fresh final-head evidence and independent GitHub approval.
- The final closeout commit 38b566b was pushed; its exact-head CI/Security
  passed; PR #2 remains blocked because no independent GitHub approval exists.

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

## Local baseline captured before the new packet

- branch: codex/release-v1.1.0;
- local HEAD: 37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0;
- origin/codex/release-v1.1.0: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4;
- local branch is ahead by one commit;
- worktree is clean;
- v1.0.0 commit: 643eac290b00561666692d41c55ceef546f12e15;
- local v1.1.0 tag is absent.

The previous live GitHub checkpoint had PR #2 open and mergeable, with the
6e357d5 checks passed, `reviewDecision=REVIEW_REQUIRED`, and `reviews=[]`.
Refresh GitHub live state after the new plan is initialized; do not reuse
that checkpoint after pushing a new head.

## Latest exact-head remote checkpoint

- final local and remote feature SHA: 38b566b04139fdd2de9b73035b66e51807966295;
- CI run 30743088855: 9/9 Ubuntu/Windows/macOS Python 3.11/3.12/3.13 jobs
  passed;
- Security run 30743088859: `codeql` and `credential-scan` passed;
- additional CodeQL check: passed;
- PR #2: open, mergeable, `mergeStateStatus=BLOCKED`;
- review: `reviewDecision=REVIEW_REQUIRED`, `reviews=[]`;
- PR body now explicitly says local implementation review is not GitHub
  approval and that another GitHub user must approve;
- v1.1.0 tag, merge, tag workflow, Release, and asset verification: not done.

The last control-document update may change the PR head and would require a
new exact-head check cycle before any protected transition.

## New task boundaries

Allowed repository changes are limited to the new Task Packet, the three
control documents, the redacted stop JSON, `README.md`, the two specified
workflows, the two specified test files, and the narrow Template Doctor state
schema compatibility rule. No product, builder, Run Guard, Doctor redesign,
dependency, branch-protection, or v1.0.0 changes are allowed.

The old local implementation review must be described as local engineering
evidence only. It is not a GitHub review and cannot satisfy the protected
branch requirement.

## Required sequence

1. Initialize the independent FINAL-CLOSEOUT Run Guard before any new network
   command.
2. Complete the bounded state, evidence, timeout, and workflow changes.
3. Run focused and full local validation from the final local commit.
4. Push only the feature branch with initial attempt plus at most two retries.
5. Confirm PR #2 head equals the final local commit, then correct the PR body
   to state that another GitHub user approval is required.
6. Wait for exact-head CI/Security and stop if any check fails or is incomplete.
7. Stop with `BLOCKED: independent GitHub approval required` until a real
   APPROVED review from another user exists.
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
called the current local HEAD.
