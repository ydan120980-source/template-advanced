# NEXT_CODEX_TASK.md

Task ID: RELEASE-V1.1.0-PUBLISH
Task Size: Full
Workflow Mode: Full
Status: planned; execution starts only after the new Run Guard is initialized

This publication-only task supersedes the historical RELEASE-V1.1.0 task. The
historical task remains recorded as implementation-complete but governance-
failed; its command budget, event ledger, and scope exception are immutable.
The released template onboarding baseline remains TEMPLATE-ONBOARDING-V1.

## Historical closure required before publication work

The original RELEASE-V1.1.0 task has this final status:

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
unchanged. Publication work continues only under this new task packet.

docs/architecture/CODEGRAPH.md was modified before it was included in the
original Task Packet Allowed Paths. Its later addition was a retroactive scope
correction and does not prove that the original scope was respected. The
repository owner accepts the resulting CodeGraph documentation change as
existing input to this publication-only task.

The earlier local implementation-review PASS is not a substitute for an
independent GitHub human approval. The publication gate must use a review from
another GitHub user and may not use self-review, an administrator bypass, or a
fabricated approval.

## Goal

Correct the v1.1.0 publication evidence and release-note wording, push the
final feature branch, verify the final commit's protected CI and Security
checks, obtain an independent human review, merge PR #2 under branch
protection, tag the merge result as v1.1.0, wait for the tag-triggered release
workflow, and independently validate the canonical remote assets.

## Planning decision

- Outcome impact: 5/5 — directly closes the public v1.1.0 delivery gap.
- Project value: 5/5 — makes the already implemented release contract
  remotely auditable and downloadable.
- Verification confidence: 5/5 — local checks, GitHub checks, tag workflow,
  and downloaded-asset verification are all defined.
- Boundary risk: 5/5 — this task crosses protected GitHub state, version tags,
  and public Release assets; Full workflow is required.
- Reversibility: 2/5 — source commits are recoverable, but a published tag
  must never be moved.
- Context completeness: 5/5 — current source, Git refs, PR metadata, Release
  metadata, old ledger, and branch protection were rechecked.
- Reviewer worthiness: 5/5 — independent human approval is a hard gate.

Decision: implement the bounded publication correction with a new Run Guard,
independent GitHub human review, and fail-fast remote gates. CodeGraph remains
optional and unindexed; no project-level indexing is part of this task.

## Live bootstrap baseline

These values were rechecked before this packet was created and are evidence,
not assumptions for later stages:

    local branch: codex/release-v1.1.0
    local HEAD: 547951233e4ea2b90f18ce658cf4e4adc3c7b04
    origin/codex/release-v1.1.0: d1c7a2a5766d39f2e0de240d3d657b1637444677
    local main: d1c7a2a5766d39f2e0de240d3d657b1637444677
    origin/main: 5893027b0c57a121b8726b72b39d133b58978f04
    v1.0.0: 643eac290b00561666692d41c55ceef546f12e15
    v1.1.0: absent
    PR: #2, open, mergeable but blocked, review required
    PR head checks: green for the old d1c7a2a head only

The final branch commit and all remote results must be re-read after each
remote transition. Old d1c7a2a checks must never be used as evidence for
5479512 or a later commit.

## Allowed Paths

Only these repository paths may change in this task:

- .github/workflows/release-artifacts.yml
- .github/workflows/security.yml
- CHANGELOG.md
- README.md
- docs/ai-workflow/GITHUB_RELEASE_READINESS.md
- docs/architecture/CODEGRAPH.md
- docs/control/NEXT_CODEX_TASK.md
- docs/control/CURRENT_PROJECT_STATE.md
- docs/control/CHATGPT_HANDOFF.md
- docs/control/SPRINT_LEDGER.md
- tests/release_readiness/**
- An isolated Run Guard plan directory outside the repository root, used only
  for local evidence and never committed or published

The external GitHub state touched by this task is limited to the existing PR
#2, its feature branch, the protected main merge, the new v1.1.0 tag, and the
tag-triggered Release workflow.

## Forbidden Paths and Actions

- .git/**, .claude/settings.local.json, credentials, secrets, private paths,
  dist/, release-a/, release-b/, __pycache__/, *.pyc, *.pyo, .planning/, and
  temporary build/download directories in the repository;
- changing dependency manifests, product code, Release builder design,
  Doctor/Run Guard core logic, CI matrix dimensions, or unrelated documents;
- changing the historical 160 command budget, deleting old Run Guard events,
  fabricating a lower command count, or changing the old gate to PASS;
- amend, rebase, history rewrite, force-push, protected-branch bypass, or
  moving/replacing v1.0.0;
- self-review, administrator bypass, review deletion, or fabricated
  independent approval;
- creating v1.1.0 before the merged main commit and all required checks are
  confirmed;
- uploading local artifacts instead of the successful tag workflow artifacts;
- continuing after a stop condition, unbounded network retry, or new budget
  overrun.

## Budget

- Maximum changed repository files: 12
- Maximum shell-command requests: 100 across the single declared main source
- Retry limit: 2
- Unique Run Guard artifact-file budget: 12
- Reserve: two file slots and ten shell-command requests remain unallocated
  until a concrete validation need appears

The task packet itself counts as one changed repository file. Local Run Guard
JSONL evidence and temporary validation output do not count as published
Release files.

## Run Guard

Classification: required.

Initialize a new isolated plan directory outside the repository before the
first implementation edit. The normalized configuration must use task ID
RELEASE-V1.1.0-PUBLISH, retry limit 2, required validation, required review,
non-overlapping implementation/publication/review workstreams, a 100-request
shell-command budget, and a 12-file unique-artifact budget.

The command source is main. The independent GitHub human review is remote
evidence rather than a second Codex shell session; it must be recorded only
after GitHub reports an actual approval. Do not reuse or amend the old
RELEASE-V1.1.0 Run Guard plan.

Record bootstrap evidence separately for actions taken before initialization.
Record workstream starts, changed-file artifacts, the implementation handoff,
validation, remote review evidence, publication milestones, and the final
gate. The final gate must be PASS only when every required remote and local
condition is evidenced.

## Required changes before the final push

1. Append an immutable historical closure for RELEASE-V1.1.0 to the Sprint
   Ledger. Preserve 166/160, retry 2/2, artifact 12/12, the failed gate, the
   partial scope compliance, the owner exception, and the retroactive
   CodeGraph-path correction.
2. Correct Release Notes and durable publication guidance:
   - protected main/PR checks: Ubuntu, Windows, and macOS x Python 3.11,
     3.12, and 3.13, plus CodeQL and credential scan;
   - tag workflow: its configured Ubuntu/Python 3.13 release-critical chain
     (unit tests, Verify, Eval, Release integration, deterministic build,
     archive verification, and upload);
   - do not claim that a tag push reruns the full cross-platform matrix;
   - exact Doctor, Preflight, and platform skip counts depend on the host and
     optional capabilities and are not repository invariants.
3. Keep CodeGraph wording honest:
   optional maintainer capability; no real project-level v1.1.0 index claimed;
   absent index is non-blocking in default Doctor and blocking in strict mode;
   present but corrupt or structurally unrecognized databases are blocking in
   all modes.
4. Explain the file-count discrepancy as:
   final Git diff = 21 tracked files; execution-time unique touched files =
   22 because the Run Guard bootstrap configuration was temporarily created
   under .planning/RELEASE-V1.1.0/run-guard-input.json and then moved outside
   the repository; artifact-file count = 12. If current evidence contradicts
   this explanation, record the evidence and correct the Ledger.
5. Tighten GitHub Actions permissions within this scope:
   release build-and-verify reads contents, release publish alone writes
   contents (and reads workflow artifacts if required), CodeQL alone writes
   security events, and credential scan uses contents read.
6. Add or update a static release-notes contract test so an inaccurate
   full-matrix tag claim fails locally.

## Validation

Run fail-fast from the repository root. Every native command in a PowerShell
batch must be checked immediately for its own exit code.

    py -3 -B -m unittest discover -s tests
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/verify.sh
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 evals/run-evals.sh
    py -3 -B -m tools.template_doctor --root . --format json
    py -3 -B scripts/ci-doctor-gate.py --root .
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/integration-test-release.sh
    git diff --check
    git diff --name-only origin/main...HEAD
    git diff --name-only origin/main...HEAD | Sort-Object -Unique

The local release integration must retain double-build determinism, clean-HEAD
rebuild equality, full archive --validate, corrupted CodeGraph rejection,
bounded process-tree cleanup, and temporary-directory cleanup. No local
artifact may be committed or uploaded.

## Remote publication sequence

1. Review the exact diff, scope, permissions, and release-note test; commit
   without amending 5479512.
2. Push only codex/release-v1.1.0. Use at most three bounded network rounds
   for a push failure and stop on persistent failure.
3. Confirm PR #2 headRefOid equals the final pushed commit. Wait for the
   final-commit CI and Security checks; old-commit results do not count.
4. Confirm an independent GitHub human review reports APPROVED. If it reports
   REVIEW_REQUIRED, stop with BLOCKED: independent human approval required.
5. Merge PR #2 only through the repository's protected method. Fetch and
   fast-forward local main to origin/main; record the merge/main SHA.
6. Re-run the required local validation on the merged main. Only a clean,
   fully validated merged main may receive a tag.
7. Confirm v1.1.0 is absent, create an annotated tag on the merged main SHA,
   push it once, and confirm the remote tag. Never touch v1.0.0.
8. Find the release-artifacts tag run for v1.1.0 and the merged SHA. Require
   success for build-and-verify and publish, a non-draft/non-prerelease
   Release, and the four canonical assets.
9. Download the Release assets to an external temporary directory. Verify
   SHA256SUMS, manifest version/source commit/file count, publication digest,
   and the tagged-source verifier with --validate. Generate a source archive
   with git archive v1.1.0 and verify its committed-tree hygiene; do not treat
   its ZIP bytes as deterministic Release bytes.
10. Clean all task temporary directories and confirm a clean repository.

## Stop conditions

Stop all later publication actions on any of the following:

- final commit cannot be pushed, or the remote branch does not equal it;
- final-commit CI or Security fails, is incomplete, or cannot be identified;
- independent human review is missing or not APPROVED;
- PR protection blocks merge, merge SHA cannot be confirmed, or local main
  cannot equal origin/main cleanly;
- v1.1.0 already exists and is absent or points to another commit;
- merged-main validation fails;
- tag workflow fails or canonical assets cannot be identified;
- downloaded checksum, manifest, digest, or tagged-source validation fails;
- a forbidden path changes, a real CodeGraph claim is needed, or a budget is
  exceeded.

Failure wording must distinguish:

    BLOCKED: network unavailable
    FAIL: final PR head checks failed
    BLOCKED: independent human approval required

Do not report publication complete after any stop condition.

## Required return format

Return an Evidence Ledger containing:

- old task closure table with 160, 166, failed gate, PARTIAL scope, YES owner
  exception, and preserved historical evidence;
- new task ID, packet commit, file/retry/command budgets, actual usage, and
  final Run Guard gate;
- feature branch, final branch SHA, remote branch SHA, PR URL/review/merge
  state, merge SHA, and final main SHA;
- only final-commit or merged-commit CI/Security checks, run IDs, results, and
  URLs;
- v1.0.0 SHA, v1.1.0 tag SHA, Release URL and metadata;
- remote asset sizes, SHA-256 values, checksum result, publication digest,
  manifest source commit, and tagged-source --validate result;
- source archive hygiene result;
- files added/modified/deleted, environment-specific Windows/Linux/macOS
  validation, scope check, remaining risks, and one bounded next step.

The final status must separate old-task governance failure from new-task
publication status. A missing human review, network, CI, merge, tag workflow,
or remote asset proof is BLOCKED or FAIL, never PASS.
