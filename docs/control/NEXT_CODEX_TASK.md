# NEXT_CODEX_TASK.md

Task ID: `TEMPLATE-POSIX-RELEASE-HYGIENE-2026-08-02`
Task Size: Small
Workflow Mode: Lite
Status: implementation and validation complete; awaiting local commit and
User review

The released template onboarding baseline remains identified as
`TEMPLATE-ONBOARDING-V1`; this bounded maintenance packet supersedes it only
for the current repair sprint.

## Goal

Restore cross-platform process-tree execution and remove local-workspace
pollution from source delivery without changing the trusted release-source,
CodeGraph, CI pinning, release-inventory, or deterministic-build contracts.

## Allowed Paths

- `.gitignore`
- `tools/aiwf_run_guard/procutil.py`
- `tools/template_doctor/release_source.py`
- `tests/aiwf_run_guard/test_procutil.py`
- `tests/release_readiness/**`
- `README.md`
- `CHANGELOG.md`
- `docs/ai-workflow/GITHUB_RELEASE_READINESS.md`
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/CHATGPT_HANDOFF.md`
- `docs/control/NEXT_CODEX_TASK.md`
- `docs/control/SPRINT_LEDGER.md`

## Budget

- Maximum files changed: 12
- Maximum commands run: 60
- Retry limit: 2

## Forbidden Paths And Actions

- `.git/**`, `dist/**`, caches, temporary directories, and local runtime state
- `.claude/settings.local.json` must not be tracked or delivered
- dependency files, CI workflow structure, external services, and secrets
- rollback of the existing CodeGraph or trusted-source fixes
- `amend`, `rebase`, history rewriting, moving `v1.0.0`, Release creation, or
  automatic push
- global process-name kills such as `taskkill /IM python.exe` or `killall`

## Required Changes

- POSIX Popen calls omit `creationflags` and use `start_new_session=True`.
- Windows Popen calls retain `CREATE_NEW_PROCESS_GROUP` and do not depend on
  POSIX-only session behavior.
- Timeout tests assert the actual command and preserve parent/child cleanup
  coverage.
- `.claude/settings.local.json` is precisely ignored; source delivery uses
  `git archive --format=zip ... HEAD`, distinct from the release builder.
- Git blob batch-reader stdin, stdout, and stderr are closed on all exit paths
  without weakening trusted HEAD reads.

## Validation Commands

Run from the repository root and report every native exit code:

```bash
bash scripts/setup.sh
py -3 -B -m unittest discover -s tests
bash scripts/verify.sh
bash evals/run-evals.sh
py -3 -B -m tools.template_doctor --root . --format json
py -3 -B -m tools.template_doctor --root . --format json --strict
py -3 -B scripts/ci-doctor-gate.py --root .
py -3 -B scripts/build-release.py --out-dir dist-a
py -3 -B scripts/build-release.py --out-dir dist-b
py -3 -B scripts/verify-release-archive.py --archive dist-a/template-advanced-1.0.0.zip --manifest dist-a/template-advanced-1.0.0.manifest.json
py -3 -B scripts/verify-release-archive.py --archive dist-a/template-advanced-1.0.0.zip --manifest dist-a/template-advanced-1.0.0.manifest.json --validate
bash scripts/integration-test-release.sh
git archive --format=zip --output=template-advanced-source.zip HEAD
```

The default Doctor must be ready. Strict Doctor may fail only because the
real CodeGraph index is absent. Release builds, archive validation, integration
validation, source-archive hygiene, and clean-HEAD reproducibility must pass.

## Stop Conditions

Stop and report if a dependency, secret, external service, forbidden path,
unapproved architecture change, unsafe process kill, failed validation after a
bounded fix, or publication action is required.

## Required Return Format

Return an Evidence Ledger with files changed, behavior changed, every command
and exact result, tests and docs updated, scope check, remaining risks, source
and release artifact evidence, Git commit state, and one suggested next step.
Stop at User review; do not push or create a Release.
