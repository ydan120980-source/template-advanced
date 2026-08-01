# CHATGPT_HANDOFF.md

Last Updated: 2026-08-01
Based On State Version: v2.0

## New-Session Summary

- **Current phase:** RELEASED — v1.0.0 published under Apache License 2.0
- **Current axis:** public, auditable, reproducible template
- **Current Sprint:** none active
- **Default action:** follow `docs/control/NEXT_CODEX_TASK.md` (the onboarding
  packet) to initialize a real project; keep `bash scripts/verify.sh`,
  `bash evals/run-evals.sh`, and Template Doctor green.

## Technical Baseline

- Python 3.11, 3.12, and 3.13 and Bash are supported; Git Bash is supported on
  Windows.
- Template Doctor, Run Guard, and the release pipeline use only the Python
  standard library.
- The release archive is built deterministically and verified independently.
- CI runs on Ubuntu, Windows, and macOS; release artifacts are attached to
  `v*` tags by the release-artifacts workflow.
- CodeGraph is optional; `docs/architecture/CODEGRAPH.md` documents the
  portable configuration and honest verification status.

## Boundaries

Do not commit credentials, private paths, planning journals, caches, or
release archives to Git. Do not rewrite pushed history or force-push. Do not
claim GitHub features are enabled unless the API reports them.

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
