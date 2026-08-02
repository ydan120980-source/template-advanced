# CHATGPT_HANDOFF.md

Last Updated: 2026-08-02
Based On State Version: v2.2

## New-session summary

- Current phase: RELEASE-CANDIDATE.
- Historical v1.0.0 remains published and unchanged.
- Historical task RELEASE-V1.1.0 is closed as implementation-complete,
  locally validated, governance-failed, and publication-incomplete.
- Current task: RELEASE-V1.1.0-PUBLISH.
- Current task goal: correct publication evidence, push the final PR branch,
  obtain final-commit CI/Security and independent human approval, merge through
  protection, tag the merged main as v1.1.0, and validate the remote Release.
- Current Run Guard: a new external plan was initialized with a 100 shell-
  command budget, two retries, and a 12-file artifact budget. Do not reuse the
  old plan.
- Current hard stop: final feature-branch CI and Security checks passed, but
  no GitHub independent human review is present; PR #2 remains blocked.

## Historical task facts

The old task must remain described exactly as follows:

    Implementation: completed
    Local validation: passed
    Governance final gate: failed
    Reason: command budget exceeded, 166/160
    Scope compliance: PARTIAL
    Owner exception required: YES
    Publication: not completed

The original RELEASE-V1.1.0 task exceeded its command budget by six
shell-command requests. The historical budget and event ledger remain
unchanged. Publication work continues only under RELEASE-V1.1.0-PUBLISH.

docs/architecture/CODEGRAPH.md was modified before it was included in the
original Task Packet Allowed Paths. Its later addition was a retroactive scope
correction and does not prove that the original scope was respected. The
repository owner accepts the resulting documentation change as existing input
to the new publication-only task.

The prior 21/22 discrepancy is recorded as final Git diff 21, execution-time
unique touched files 22, and Run Guard artifact files 12. The additional
execution-time path was the temporary .planning/RELEASE-V1.1.0/run-guard-
input.json bootstrap configuration, later moved outside the repository.

## Live baseline before the new task

- local feature branch: codex/release-v1.1.0
- local candidate: 547951233e4ea2b90f18ce658cf4e4adc3c7b04a
- remote PR branch: d1c7a2a5766d39f2e0de240d3d657b1637444677
- local main: d1c7a2a5766d39f2e0de240d3d657b1637444677
- origin/main: 5893027b0c57a121b8726b72b39d133b58978f04
- v1.0.0: 643eac290b00561666692d41c55ceef546f12e15
- v1.1.0: absent
- PR #2: open, mergeable, blocked, review required
- old PR checks: successful for old d1c7a2a only

Re-read all values after every GitHub transition. Old-commit checks cannot
prove final-commit readiness.

## Final feature-branch checkpoint

- final feature-branch SHA: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
- remote feature-branch SHA: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
- PR #2: open, mergeable, `mergeStateStatus=BLOCKED`
- review state: `reviewDecision=REVIEW_REQUIRED`, `reviews=[]`
- CI run 30737700031: Ubuntu/Windows/macOS Python 3.11/3.12/3.13, 9/9
  passed
- Security run 30737700025: `codeql` and `credential-scan` passed
- additional CodeQL check: passed
- v1.1.0 tag and Release: absent; merge, tag, Release, and asset download
  were not performed
- Run Guard: 8 events, 0/2 retries, 11/12 artifacts, validation 2/2 passed;
  gate `not_ready` solely because review is required; command budget remains
  unsnapshotted while review is pending

## Technical contracts

- Release builds require a clean Git HEAD and read release files from Git
  objects; non-Git builds require explicit unverified labeling.
- Canonical Release artifacts come from the successful tag workflow, not from a
  local mutable workspace or an old Release.
- SHA256SUMS, the manifest, the publication digest, and the tagged-source
  verifier with full validation must all pass after download.
- git archive provides committed-tree traceability but not cross-platform ZIP
  byte determinism.
- Protected main/PR checks are Ubuntu, Windows, and macOS with Python 3.11,
  3.12, and 3.13, plus CodeQL and credential scan.
- The tag workflow runs its configured Ubuntu/Python 3.13 release-critical
  chain and does not claim to run the full cross-platform matrix.
- Release build-and-verify reads contents; publish alone writes contents.
  CodeQL alone writes security events. Credential scan stays contents read.
- CodeGraph is optional and unindexed for v1.1.0. Default missing-index
  behavior is non-blocking; strict missing-index behavior is blocking; corrupt
  or structurally unrecognized databases block all modes.
- Exact Doctor, Preflight, and platform-specific pass/skip totals are
  environment evidence and must not become fixed long-term claims.

## Required sequence

1. Finish only the allowed docs, workflow, and static-test correction.
2. Run local validation and inspect the exact diff.
3. Commit without amending 5479512.
4. Push codex/release-v1.1.0 with bounded retries.
5. Confirm PR #2 head equals the pushed commit and wait for final checks.
6. Final checks passed, but stop because reviewDecision is REVIEW_REQUIRED;
   report BLOCKED: independent human approval required.
7. After real approval, merge through branch protection and confirm local
   main equals origin/main cleanly.
8. Re-run merged-main validation, then create and push v1.1.0 exactly once.
9. Wait for the tag workflow, download its Release assets, and independently
   verify all canonical files with the tagged-source verifier.
10. Clean temporary evidence and record the final Run Guard gate.

Never force-push, bypass protection, self-review, move v1.0.0, upload local
artifacts, or report an incomplete gate as publication success.
