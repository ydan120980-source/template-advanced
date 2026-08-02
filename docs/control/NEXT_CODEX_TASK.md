# NEXT_CODEX_TASK.md

Task ID: RELEASE-V1.1.0-FINAL-CLOSEOUT
Task Size: Full
Workflow Mode: Full
Status: planned; initialize the new Run Guard before implementation work

This task supersedes the blocked RELEASE-V1.1.0-PUBLISH task. The two older
tasks remain immutable historical evidence; their budgets, events, and failed
gates must not be rewritten.
The released template onboarding baseline remains TEMPLATE-ONBOARDING-V1.

## Goal

Seal the blocked publication task, correct the stop-state and PR evidence,
bound Template Doctor test helpers and the relevant GitHub Actions jobs, then
complete the protected v1.1.0 publication sequence only when every local,
remote, review, merge, tag, workflow, and canonical-asset gate is genuinely
verified.

## Historical task closure required before any network write

RELEASE-V1.1.0-PUBLISH is closed with this exact result:

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

The old task cannot execute another push. Its retry budget is exhausted and
the last network failure was not closed by a legal retry and fresh accepted
validation evidence. Do not call the old task successful, do not delete its
failure events, and do not alter its 2/2 retry or command-budget facts.

## Non-goals

- Do not refactor Template Doctor or AIWF Run Guard.
- Do not redesign the Release builder or add product functionality.
- Do not initialize or claim a real CodeGraph index.
- Do not modify v1.0.0, the Git history before the current branch, or branch
  protection.
- Do not add CI platforms, perform unrelated documentation cleanup, or
  reformat the repository.

## Required work

1. Keep the old RELEASE-V1.1.0-PUBLISH stop state in the control files and add
   the redacted JSON stop-state evidence.
2. Create and use an independent Run Guard plan named
   RELEASE-V1.1.0-FINAL-CLOSEOUT.
3. Replace the misleading state labels that confuse the local HEAD with the
   last confirmed remote PR head. Keep live values explicitly refresh-required.
4. Correct PR #2 body wording so local implementation review is clearly not a
   GitHub approval from another user. Make the change only after the new final
   branch head has been pushed and rechecked.
5. Add bounded timeout handling to the Template Doctor test helpers and their
   direct subprocess calls. Timeout diagnostics must contain the helper name,
   command, timeout, cwd, and bounded stdout/stderr tails.
6. Add regression coverage for normal completion and timeout behavior without
   making ordinary tests wait for the timeout duration.
7. Add explicit outer job timeouts to the main CI matrix and release workflow
   jobs. The timeout is a last line of defense, not a replacement for helper
   timeouts. Do not set a low timeout on CodeQL.
8. Run the complete local validation from the final local commit, then push
   only codex/release-v1.1.0 with an initial attempt plus at most two retries.
9. Revalidate the exact remote PR head, wait for its CI/Security, obtain a real
   APPROVED review from another GitHub user, merge through protection, validate
   merged main, create v1.1.0 from merged main, and validate the remote Release
   assets and tagged source.

## Planning decision

- Outcome impact: 5/5 — closes the remaining public v1.1.0 delivery gap.
- Project value: 5/5 — converts a truthful blocked stop into an auditable
  protected release when external gates are available.
- Verification confidence: 5/5 — local tests, GitHub checks, review, merge,
  tag workflow, and independent download verification are defined.
- Boundary risk: 5/5 — this crosses state transitions, protected GitHub
  writes, an immutable tag, and public Release assets; Full is required.
- Reversibility: 2/5 — commits are recoverable, but a published tag must not
  be moved.
- Context completeness: 5/5 — local Git baseline and previous stop evidence
  were re-read before this packet.
- Reviewer worthiness: 5/5 — independent GitHub approval is a hard gate.

## Current local bootstrap baseline

This is local read-only evidence captured before the new Run Guard. GitHub live
state must be refreshed after the new plan is initialized and before every
remote transition:

    branch: codex/release-v1.1.0
    local HEAD: 37fb3b4e75fa424bc6871dc140e1518ea0ea4fa0
    origin/codex/release-v1.1.0: 6e357d55f813bdc6a823ea0f94fd8ef01ee54de4
    ahead/behind: local is ahead by 1 commit
    worktree: clean
    local tags: v1.0.0 only; v1.1.0 absent
    v1.0.0 commit: 643eac290b00561666692d41c55ceef546f12e15

The previous live GitHub query confirmed PR #2 was open, its 6e357d5 head had
passed the protected checks, `reviewDecision=REVIEW_REQUIRED`, and
`reviews=[]`. Those results must not be reused as final evidence after a new
head is pushed.

## Allowed Paths

Only these repository paths may change in this task:

- .github/workflows/ci.yml
- .github/workflows/release-artifacts.yml
- README.md
- docs/control/NEXT_CODEX_TASK.md
- docs/control/CURRENT_PROJECT_STATE.md
- docs/control/CHATGPT_HANDOFF.md
- docs/control/SPRINT_LEDGER.md
- docs/control/evidence/RELEASE-V1.1.0-PUBLISH_STOP.json
- tests/template_doctor/test_cli.py
- tests/release_readiness/test_release_notes.py
- tools/template_doctor/rules.py (narrow state-schema compatibility only)
- An isolated Run Guard plan outside the repository root

The narrow Template Doctor rule change is allowed only because the requested
stop-state schema intentionally removes the old `Is state stale?` and
`Current Git HEAD` labels. It must preserve the existing legacy schema tests
and add compatibility coverage; it is not a Doctor refactor.

External GitHub writes are limited to PR #2, its existing feature branch, the
protected main merge, the new v1.1.0 tag, the tag workflow, and its Release.

## Forbidden Paths and Actions

- .git/, .claude/settings.local.json, credentials, secrets, .env, .env.*,
  dist/, release-a/, release-b/, __pycache__/, *.pyc, *.pyo, .planning/, and
  repository temporary build/download directories;
- dependency manifests, product code, Release builder redesign, Doctor or Run
  Guard redesign, CI matrix dimensions, and unrelated documents;
- changing old budgets, deleting old events, changing the old gate to PASS, or
  fabricating validation/review events;
- amend, rebase, history rewrite, force-push, self-review, administrator
  bypass, review deletion, or branch-protection changes;
- creating v1.1.0 before a protected merge and merged-main validation;
- uploading local artifacts instead of successful tag-workflow artifacts;
- infinite GitHub polling, infinite network retries, or any action after a
  stop condition.

## Budget

- Maximum changed repository files: 12
- Unique Run Guard artifact-file budget: 10
- Retry limit: 2, with initial attempt plus at most two retries for push
- Shell-command budget: 90 requests across the single declared main source
- Planned delivery files: 10, leaving two file slots in reserve
- The Task Packet and stop-state JSON count as delivery artifacts.
- External Run Guard JSONL and temporary validation output are not Release
  files and must not enter the repository.

## Run Guard

Classification: required.

Initialize a new isolated plan named RELEASE-V1.1.0-FINAL-CLOSEOUT before any
new network command. Do not reuse or amend RELEASE-V1.1.0-PUBLISH. The new
configuration must use retry 2, required validation, required review, a
90-request `shell_command_requests` budget, and a 10-file
`unique_artifact_files` budget. The main Codex source is the only declared
command source; GitHub human review is remote evidence, not a helper session.

Use separate non-overlapping workstreams: implementation owns the allowed
repository files and handoff; publication owns no repository files and records
remote milestones; review owns no repository files and can record only real
GitHub approval evidence.

Record workstream starts, artifacts, handoffs, failures, retries, validation,
remote checks, review, merge, tag, Release, asset validation, and the final
gate. Do not backfill an accepted validation event for the old plan.

## Validation

Run fail-fast from the repository root. Check every native exit code before
starting the next command:

    py -3 -B -m unittest tests.template_doctor.test_cli tests.release_readiness.test_release_notes
    py -3 -B -m unittest discover -s tests
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/verify.sh
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 evals/run-evals.sh
    py -3 -B -m tools.template_doctor --root . --format json
    py -3 -B scripts/ci-doctor-gate.py --root .
    powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/integration-test-release.sh
    git diff --check
    git diff --name-only origin/main...HEAD
    git diff --name-only origin/main...HEAD | Sort-Object -Unique

The integration test must retain deterministic double-build equality,
clean-HEAD rebuild equality, full archive validation, corrupt CodeGraph
rejection, bounded process cleanup, and temporary-directory cleanup.

After a new push failure, do not reuse pre-failure validation. Record the
failure, consume only a legal retry, rerun the required post-failure validation
and record a fresh accepted validation event. If the retry budget is exhausted,
stop and report the network blocker.

## Remote publication sequence

1. Review exact scope and commit the new local changes without amending
   6e357d5 or 37fb3b4.
2. Run complete validation from the final local commit.
3. Push only codex/release-v1.1.0 with the new plan's bounded retries.
4. Fetch and confirm the PR head equals the final local commit. Only then fix
   the PR body wording and wait for the exact-head CI/Security checks.
5. Require `reviewDecision=APPROVED` from another GitHub user. If review is
   missing or `REVIEW_REQUIRED`, stop with
   `BLOCKED: independent GitHub approval required`.
6. Merge only through branch protection with an expected head, then fast-
   forward local main to origin/main and confirm a clean equal state.
7. Re-run merged-main validation. Only the validated merged main may receive
   an annotated v1.1.0 tag; never touch v1.0.0.
8. Wait for the tag workflow, verify build-and-verify and publish, confirm the
   non-draft/non-prerelease Release and all four canonical assets.
9. Download the assets to an external temporary directory. Verify checksums,
   manifest/source commit/file count, publication digest, tagged-source
   `--validate`, and committed-tree archive hygiene.
10. Clean temporary directories and record the new Run Guard final gate.

## Stop Conditions

Stop all later publication actions on any of the following:

- new budget overrun, forbidden path change, or corrupted Run Guard evidence;
- final branch cannot be pushed or PR head differs from the final commit;
- final-head CI/Security fails, is incomplete, or cannot be identified;
- another GitHub user has not approved the PR;
- protected merge, merged-main equality, or merged-main validation fails;
- v1.1.0 already exists and is absent or points to a different commit;
- tag workflow, Release metadata, checksum, manifest, digest, tagged-source
  validation, or source-archive hygiene fails;
- new Run Guard final gate is not ready.

Use exact failure labels:

    BLOCKED: network unavailable
    FAIL: final PR head checks failed
    BLOCKED: independent GitHub approval required

Never report publication complete after a stop condition.

## Required Return Format

Return an Evidence Ledger with:

- immutable closure tables for RELEASE-V1.1.0 and RELEASE-V1.1.0-PUBLISH;
- new task ID, packet commit, budgets, actual usage, and Run Guard gate;
- changed files and scope check;
- final local/remote feature SHA, PR review/merge state, merge SHA, and main
  SHA;
- only exact-final-head or merged-main CI/Security run IDs and URLs;
- v1.0.0 and v1.1.0 tag facts, Release metadata, canonical asset sizes and
  SHA-256 values, checksum, manifest, digest, tagged-source, and source-
  archive results;
- Windows/Linux/macOS validation separated by environment;
- remaining risks and one bounded next step.

The final status must keep old governance failure, old publication stop,
current closeout status, independent review, network, CI, merge, tag, and
remote asset evidence separate. Missing evidence is BLOCKED or FAIL, never
PASS.
