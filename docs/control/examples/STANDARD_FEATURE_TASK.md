# Standard Feature Task Example

## Goal

Implement one bounded feature that touches a small set of related files.

## Workflow Mode

Standard

## Required Reading

- `AGENTS.md`
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/CODEX_RUNTIME_PROFILE.md`
- `docs/control/NEXT_CODEX_TASK.md`
- Relevant feature, test, and documentation files

## Allowed Paths

- `<feature-module>`
- `<feature-tests>`
- `<feature-docs>`

## Forbidden Paths

- dependency manifests and lockfiles unless explicitly authorized
- `.github`
- `.codex`
- auth-sensitive files
- generated artifacts unless listed in Allowed Paths
- broad architecture documents unless the task requires a doc update

## Budget

- Maximum files changed: 8
- Maximum lines changed: 400
- Maximum commands run: 8
- Maximum execution time: 60 minutes
- Maximum retries: 2

## Validation Commands

```bash
<focused feature tests>
<affected integration test, if applicable>
bash scripts/verify.sh
```

## Stop Conditions

- The feature needs new dependencies.
- Public contracts or module boundaries need redesign.
- Security or auth-sensitive files must change.
- Production data is required.
- Validation reveals failures outside the task scope.
- The change exceeds the budget.

## Required Return Format

```text
Evidence Ledger

Sprint ID:
Goal:
Task Size:
Workflow Mode:
Files changed:
Behavior changed:
Commands run:
Command results:
Tests added/updated:
Docs added/updated:
Risks:
Known limitations:
Follow-up candidates:
Blocked items:
State update recommendation:
Suggested next step:
```
