# NEXT_CODEX_TASK.md

Task ID: `TEMPLATE-ONBOARDING-V1`
Task Size: Small
Workflow Mode: Lite

## Goal

Initialize this copied template into a new project. Replace the generic
template identity with the project's real name and purpose, keep every
validation entry point green, and return the first Evidence Ledger without
touching forbidden paths.

## Allowed Paths

- `docs/control/NEXT_CODEX_TASK.md`
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/SPRINT_LEDGER.md`
- `docs/control/CHATGPT_HANDOFF.md`
- `README.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `docs/ai-workflow/**`
- `tests/**`
- `tools/**`

## Forbidden Paths

- `.git/**` and any VCS metadata
- `.planning/**` and local runtime evidence
- secrets, credentials, private keys, and session files
- dependency files (`pyproject.toml`, `requirements*.txt`, lockfiles)
- `.github/workflows/**`, CI configuration, and external services
- `dist/**` (generated release output)
- license selection and remote publication

## Budget

- Maximum files changed: 10
- Maximum commands run: 30
- Retry limit: 2

## Validation Commands

Run every command from the repository root and report each native exit code:

```bash
bash scripts/setup.sh
bash scripts/verify.sh
bash evals/run-evals.sh
py -3 -B -m tools.template_doctor --root . --format json
py -3 scripts/build-release.py
py -3 scripts/verify-release-archive.py --archive dist/template-advanced-1.0.0.zip --manifest dist/template-advanced-1.0.0.manifest.json
```

Template Doctor exits `1` for the deferred Git baseline and CodeGraph index
only; any other content failure must be fixed before declaring readiness.

## Stop Conditions

- Stop if a dependency change, license selection, Git initialization, CI
  enablement, or remote publication is required.
- Stop if a validation command fails after a bounded fix attempt.
- Stop if the task needs files outside Allowed Paths.

## Required Return Format

Return an Evidence Ledger with the files changed, every command and its exact
result, validation status, a scope check against Allowed and Forbidden Paths,
remaining risks, and one suggested next step. Stop at User review; do not
publish.
