# NEXT_CODEX_TASK.md

Task ID: `RELEASE-V1.1.0`
Task Size: Large
Workflow Mode: Full
Status: implementation and local validation complete; publication pending

This is a bounded public-release sprint. It promotes the verified current
`main` line to `v1.1.0` without moving or replacing the historical `v1.0.0`
tag or Release.

The released template onboarding baseline remains identified as
`TEMPLATE-ONBOARDING-V1`; this maintenance packet supersedes it only for the
current release sprint.

## Goal

Seal the current release contract, remove drift-prone status wording, provide a
safe Windows Git-Bash entry point, build deterministic `v1.1.0` artifacts, and
publish and independently verify the resulting GitHub Release.

## Planning Decision

- Outcome impact: 5/5 — closes the public-release gap between `main` and the
  downloadable artifacts.
- Project value: 5/5 — makes the current trusted-source, security, and
  process-tree contracts available to users.
- Verification confidence: 5/5 — local, archive, CI, tag, and download checks
  are all executable.
- Boundary risk: 5/5 — changes public versioning, release workflow, and remote
  GitHub state; this is intentionally a Full sprint.
- Reversibility: 3/5 — source commits are reversible, while a published tag
  and Release must never be moved.
- Context completeness: 5/5 — current source, Git, GitHub, release, and
  control-state baselines were rechecked before planning.
- Reviewer worthiness: 5/5 — an independent review is required before the
  final publication decision.

Decision: implement with independent reviewer evidence. CodeGraph remains an
optional capability: its absence must not block the default release gate, and
no indexing success may be claimed.

## Allowed Paths

- `.github/workflows/release-artifacts.yml`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `README.md`
- `SECURITY.md`
- `docs/ai-workflow/GITHUB_RELEASE_READINESS.md`
- `docs/architecture/README.md`
- `docs/control/NEXT_CODEX_TASK.md`
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/CHATGPT_HANDOFF.md`
- `docs/control/SPRINT_LEDGER.md`
- `scripts/build-release.py`
- `scripts/integration-test-release.sh`
- `scripts/verify-release-archive.py`
- `scripts/invoke-git-bash.ps1`
- `tools/project_version.py`
- `tools/template_doctor/**`
- `tools/aiwf_run_guard/__init__.py`
- `tests/release_readiness/**`
- `tests/template_doctor/**`
- An isolated Run Guard plan directory outside the repository root (local
  evidence only; never commit or publish)

## Forbidden Paths And Actions

- `.git/**`, `dist/**`, `release-a/**`, `release-b/**`, caches, temporary
  directories, and local runtime state in the commit or Release assets;
- `.claude/settings.local.json`, credentials, private paths, or secrets;
- dependency manifests and unrelated core-governance refactors;
- moving, replacing, or force-pushing `v1.0.0`;
- rewriting Git history, squashing the ten post-`v1.0.0` commits, or amending
  existing commits;
- compressing the mutable working directory for source delivery;
- claiming real CodeGraph indexing, official schema validation, or host-level
  pass/skip counts as repository invariants;
- creating a tag or Release before the final commit is pushed and the required
  GitHub workflows have succeeded;
- uploading local release artifacts in place of tag-CI artifacts;
- continuing after a failed required validation or a remote publication error.

## Budget

- Maximum files changed: 32
- Maximum shell-command requests: 160 across the main and reviewer sources
- Retry limit: 2
- Unique published delivery files: 12; local planning and temporary validation
  output do not count as release files.

## Run Guard

Classification: `required`.

Use an isolated Run Guard plan directory outside the repository root. The
normalized run configuration must declare:

- retry limit: 2;
- required validation: true;
- required independent review: true;
- non-overlapping implementation, integration/publication, and reviewer
  workstreams;
- command budget: 160 `shell_command_requests`, with sources `main` and
  `reviewer`, plus reserve for one bounded retry;
- unique delivery-file budget: 12 published files, excluding local planning
  evidence and temporary validation output.

Record workstream starts, changed-file artifacts, validation, handoff, reviewer
result, and the final gate. Do not backfill evidence for commands that ran
before this task packet was initialized; label the preflight and baseline as
bootstrap evidence in the ledger.

## Required Changes

1. Make `tools/project_version.py` the single project version source and set it
   to `1.1.0`; derive package versions, release inventory, builder defaults,
   integration stems, workflow artifact names, and tests from it.
2. Seal `CHANGELOG.md` as `[1.1.0] - 2026-08-02` (or the actual release date),
   retain an empty `[Unreleased]` entry point, and add the `v1.0.0...v1.1.0`
   comparison link. Do not claim CodeGraph indexing.
3. Update README, CONTRIBUTING, SECURITY, release-readiness, architecture, and
   control-state wording to avoid fixed host-dependent file/test/Doctor counts,
   distinguish default/strict Doctor semantics, and distinguish Git source
   archives from deterministic Release archives.
4. Add a tested `scripts/invoke-git-bash.ps1` helper that derives Git Bash from
   `git.exe`, excludes WSL/System32 and WindowsApps launchers, handles spaces,
   forwards stdout/stderr and exit codes, and fails clearly when Git Bash is
   unavailable.
5. Update the release workflow and release scripts/tests for `v1.1.0` without
   weakening the clean-HEAD, deterministic archive, manifest, digest, full
   `--validate`, CodeGraph rejection, or CI/security contracts.
6. Append the accepted release sprint evidence to the control ledger and leave
   current state/handoff aligned with the final published commit and remote
   verification. The current checkpoint has passed implementation review and
   local validation; publication remains blocked until the required remote
   checks and tag workflow succeed.

## Validation Commands

Run fail-fast from the repository root; on Windows use the new PowerShell
helper where a Bash script is required:

```text
py -3 -B -m unittest discover -s tests
powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/setup.sh
powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/verify.sh
powershell -NoProfile -File scripts/invoke-git-bash.ps1 evals/run-evals.sh
py -3 -B -m tools.template_doctor --root . --format json
py -3 -B scripts/ci-doctor-gate.py --root .
powershell -NoProfile -File scripts/invoke-git-bash.ps1 scripts/integration-test-release.sh
py -3 -B scripts/build-release.py --out-dir release-a
py -3 -B scripts/build-release.py --out-dir release-b
py -3 -B scripts/verify-release-archive.py --archive release-a/template-advanced-1.1.0.zip --manifest release-a/template-advanced-1.1.0.manifest.json --validate
git archive --format=zip --output=template-advanced-source-v1.1.0.zip HEAD
```

Before publication, verify both build directories and the source archive are
outside the committed tree or removed, and inspect source type/commit,
publication digest, file set, modes, line endings, `.git/`,
`.claude/settings.local.json`, caches, and local state.

After the final commit:

```text
git push origin main
gh run list --branch main --limit 20
gh run view <ci-run-id>
gh run view <security-run-id>
git tag -a v1.1.0 -m "template-advanced v1.1.0"
git push origin v1.1.0
gh release view v1.1.0
gh release download v1.1.0 --dir <temporary-directory>
```

The tag workflow must succeed before the Release is accepted. Downloaded
assets must pass `sha256sum -c SHA256SUMS` and the `v1.1.0` verifier with
`--validate` using the tagged source.

## Stop Conditions

Stop and report immediately on a failed required validation, dirty or
untracked release source, missing Git Bash, unexpected workflow failure,
unavailable GitHub permission, tag/HEAD mismatch, asset checksum mismatch,
CodeGraph claim that cannot be evidenced, forbidden-path change, or any need
to move `v1.0.0`.

## Required Return Format

Return an Evidence Ledger with the version decision, changed files, exact local
and remote commands/results, final/main/tag/v1.0.0 SHAs, workflow run IDs and
URLs, artifact sizes/SHA-256/publication digest, Release metadata, independent
download verification, scope check, remaining risks, Run Guard gate, and one
follow-up candidate. Do not report publication as complete before remote CI and
download verification are successful.
