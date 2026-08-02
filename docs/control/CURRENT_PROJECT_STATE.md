# CURRENT_PROJECT_STATE.md

Last Updated: 2026-08-02
State Version: v2.2
Is state stale?: no
Based On Commit: manual record - validated remote checkpoint 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
Current Git HEAD: manual record - validated remote checkpoint 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4

## 1. Current Project Phase

- Current Phase: RELEASE-CANDIDATE
- Phase Status: the original v1.1.0 implementation sprint is closed as a
  governance failure; the publication-only correction sprint is blocked at
  the required independent GitHub human-review gate.
- Phase Goal: publish only the exact, protected, independently reviewed
  v1.1.0 merge result and validate the canonical remote artifacts.
- Historical v1.0.0 remains published and immutable.

## 2. Current Sprint

- Task ID: RELEASE-V1.1.0-PUBLISH
- Mode: Full
- State: final feature-branch commit was pushed; its protected CI and Security
  checks passed; no independent GitHub human approval is present, so no merge,
  tag, or Release action is permitted.
- Required review: independent GitHub human approval; local implementation
  review is not sufficient.
- CodeGraph: optional maintainer capability; no real project-level index is
  claimed for v1.1.0.

## 3. Historical RELEASE-V1.1.0 Closure

The prior task is not a complete PASS:

    Implementation: completed
    Local validation: passed
    Governance final gate: failed
    Reason: command budget exceeded, 166/160
    Scope compliance: PARTIAL
    Owner exception required: YES
    Publication: not completed
    Superseded by: RELEASE-V1.1.0-PUBLISH

The original RELEASE-V1.1.0 task exceeded its command budget by six
shell-command requests. The historical budget and event ledger remain
unchanged. Publication work continues only under the new task packet.

docs/architecture/CODEGRAPH.md was modified before it was included in the
original Task Packet Allowed Paths. Its later addition was a retroactive scope
correction and does not prove that the original scope was respected. The
repository owner accepts that documentation change as existing input to the
new publication-only task.

The earlier Run Guard summary remains preserved externally with retry use 2/2,
unique artifact files 12/12, command use 166/160, and gate not_ready. The
earlier implementation-review PASS is not an independent GitHub human
approval.

## 4. Live Bootstrap Baseline

The following was rechecked before the new packet:

- Feature branch: codex/release-v1.1.0
- Local candidate before this task: 547951233e4ea2b90f18ce658cf4e4adc3c7b04a
- Remote PR branch before this task:
  d1c7a2a5766d39f2e0de240d3d657b1637444677
- Local main before this task: d1c7a2a5766d39f2e0de240d3d657b1637444677
- origin/main: 5893027b0c57a121b8726b72b39d133b58978f04
- v1.0.0 commit: 643eac290b00561666692d41c55ceef546f12e15
- v1.1.0: absent
- PR #2: open, mergeable, blocked by required review
- Old PR checks: green for d1c7a2a only; they are not final-commit evidence

## 5. Final Feature-Branch Checkpoint

The final candidate was committed and pushed without amending the historical
5479512 commit:

- Final feature-branch SHA: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
- Remote feature-branch SHA: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
- PR #2: open, mergeable, `mergeStateStatus=BLOCKED`
- PR review state: `reviewDecision=REVIEW_REQUIRED`, `reviews=[]`
- CI run: 30737700031; Ubuntu/Windows/macOS Python 3.11/3.12/3.13 = 9/9
  passed
- Security run: 30737700025; `codeql` and `credential-scan` passed
- Additional CodeQL check: passed
- v1.1.0 tag and Release: still absent
- Merge, tag, Release creation, and asset download: not performed because the
  independent review stop condition is active

The current branch, remote branch, merged main SHA, tag SHA, workflow run IDs,
and Release metadata must be refreshed from GitHub after each transition.

## 6. Control Hierarchy

When documents conflict, use this order:

1. the User latest explicit instruction;
2. repository constitution and AGENTS.md;
3. docs/control/NEXT_CODEX_TASK.md as the sole sprint authority;
4. docs/control/CODEX_RUNTIME_PROFILE.md;
5. this current state;
6. docs/control/SPRINT_LEDGER.md as history.

Planning journals and Run Guard evidence may record execution but cannot expand
the packet scope, relax a stop condition, or alter a historical result.

## 7. Canonical Contracts

- Template Doctor is a Python-standard-library CLI with deterministic reports
  and blocking-failure semantics.
- AIWF Run Guard is a Python-standard-library evidence gate for ownership,
  retry lineage, validation/review ordering, artifact budgets, and shell
  command budgets.
- Release builds read release files from the Git object database at HEAD and
  refuse dirty, missing, or untracked release files.
- Canonical Release artifacts are deterministic ZIP, manifest, digest, and
  SHA256SUMS outputs produced by the tag workflow.
- A Git source archive is a traceable convenience archive from a committed
  tree; its ZIP bytes are not promised to be cross-platform deterministic.
- Protected main/PR validation is the Ubuntu/Windows/macOS Python 3.11-3.13
  matrix plus CodeQL and credential scanning.
- The tag workflow is a separate configured Ubuntu/Python 3.13 release chain;
  it does not claim to rerun the full protected matrix.
- Release build-and-verify has contents read; publish alone has contents
  write. CodeQL alone has security-events write; credential scan has contents
  read.
- CodeGraph is optional. Missing index is skip/info by default and fail/error
  in strict mode. A corrupt or structurally unrecognized database blocks all
  modes. No official schema or real index is claimed.

## 8. Active Priorities

1. Await an independent GitHub human approval for PR #2; do not self-review
   or bypass branch protection.
2. If approval arrives, re-read the final PR head and required checks before
   protected merge, then continue with merged-main validation and tag-only
   publication in the task-packet order.
3. Keep v1.0.0 unchanged and never move or replace its tag or Release.
4. Keep exact host-dependent Doctor and Preflight counts in evidence only.
5. Keep source archives separate from canonical deterministic Release assets.

## 9. File-Count Evidence

The prior task must distinguish:

- final Git diff: 21 tracked files;
- execution-time unique touched files: 22;
- Run Guard artifact-file count: 12.

The documented reason for the extra execution-time file is the temporary
Run Guard bootstrap configuration
.planning/RELEASE-V1.1.0/run-guard-input.json, which was created during task
initialization and then moved to an external plan directory. It is not part of
the final tracked diff or published Release. If later evidence disproves this
reason, the next Ledger entry must correct it rather than silently changing a
count.

## 10. Risks And Stop Rules

- No independent GitHub human approval is currently present.
- The final feature-branch CI and Security checks are green, but branch
  protection still blocks the PR because review is required.
- GitHub branch protection and required checks are external state and must be
  reported from live results.
- A failed final check, merge, tag workflow, checksum, manifest, digest, or
  tagged-source validation blocks every later publication action.
- Network failures are not code failures; record BLOCKED: network unavailable
  and preserve local work.

## 11. State Freshness

The commit fields above identify the validated parent checkpoint because a
committed file cannot self-reference the commit that contains it. Remote
publication facts must be refreshed live after each transition.
