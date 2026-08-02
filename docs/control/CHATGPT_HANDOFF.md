# CHATGPT_HANDOFF.md

Last Updated: 2026-08-02
Based On State Version: v2.0

## New-Session Summary

- **Current phase:** RELEASE-CANDIDATE — v1.0.0 remains published while the
  reviewed and locally validated v1.1.0 is pending remote publication under
  Apache License 2.0
- **Current axis:** public, auditable, reproducible template
- **Current Sprint:** `RELEASE-V1.1.0` — seal the current release contract,
  update versioned artifacts and docs, add the Windows Git-Bash helper, then
  publish and independently verify the new Release only after CI succeeds.
- **Default action:** follow `docs/control/NEXT_CODEX_TASK.md`; keep the
  default Doctor free of blocking failures, wait for required remote checks
  before tagging, and keep the historical `v1.0.0` tag and Release unchanged.

## Technical Baseline

- Python 3.11, 3.12, and 3.13 and Bash are supported; Git Bash is supported on
  Windows.
- Template Doctor, Run Guard, and the release pipeline use only the Python
  standard library.
- The release archive is built deterministically and verified independently.
- Release builds require a clean Git commit: release files are read from the
  Git object database at HEAD, and dirty, untracked, or deleted release files
  block the build. Non-Git trees must opt in with `--allow-unverified` and
  are labeled unverified-source-tree builds.
- The committed `.codex/config.toml` keeps safe defaults (on-request
  approval, workspace-write sandbox, network off); `approval_policy =
  "never"` is never a template default.
- The unit-test suite runs fast directed tests only; the recursive full
  release validation runs in `scripts/integration-test-release.sh`, which
  release CI executes. Validation subprocesses have bounded timeouts and
  whole-process-tree termination. The integration runner uses the shared
  process helper for named stages and reports bounded output tails on failure.
- Run Guard process launches explicitly close stdin, stdout, and stderr on
  normal, nonzero, timeout, and cleanup paths while preserving output; strict
  `ResourceWarning` regression tests cover repeated timeouts and pipe state.
- POSIX process launches pass `start_new_session=True` without the Windows-only
  `creationflags` keyword; Windows uses its process-group creation flag.
  Timeout errors identify the actual command, and the Git blob batch reader
  closes all three pipes.
- Source deliveries use `git archive HEAD`, which excludes `.git/`, untracked
  local state such as `.claude/settings.local.json`, caches, and build output.
  Its ZIP byte representation may vary across Git, zlib, or operating-system
  implementations; formal release archives from `scripts/build-release.py`
  retain the cross-platform byte-determinism guarantee. Do not distribute a
  ZIP made by compressing the working directory.
- CI runs on Ubuntu, Windows, and macOS; release artifacts are attached to
  `v*` tags by the release-artifacts workflow.
- CodeGraph is optional; `docs/architecture/CODEGRAPH.md` documents the
  portable configuration and honest verification status. Template Doctor
  reports an absent index as `skip/info` by default and `fail/error` under
  `--strict`. The Doctor's check is a conservative heuristic: a project-local
  database must be readable by SQLite, pass `quick_check`, and contain at
  least one currently recognized candidate table (such as `nodes` or
  `edges`); it does not prove compatibility with a complete or official
  CodeGraph schema. A corrupt or invalid project-local database is always a
  blocking failure, and no CI or release allowlist covers it.

## Boundaries

Do not commit credentials, private paths, planning journals, caches, or
release archives to Git. Do not rewrite pushed history or force-push. Do not
claim GitHub features are enabled unless the API reports them. Do not build
release artifacts from a dirty workspace; release builds read from HEAD and
refuse uncommitted release files.

The project is licensed under the Apache License 2.0; attribute changes belong
in `NOTICE`.

## Required Reading Order

1. `AGENTS.md`
2. `docs/control/NEXT_CODEX_TASK.md`
3. `docs/control/CURRENT_PROJECT_STATE.md`
4. `docs/control/CODEX_RUNTIME_PROFILE.md`
5. this handoff

Use current source, targeted search, and tests as evidence. Planning journals
are subordinate evidence only.

## Acceptance Rule

A sprint is accepted only when its Evidence Ledger records real validation
results, the Task Packet scope was respected, and no forbidden action occurred.
