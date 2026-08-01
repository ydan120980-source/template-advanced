# Lite Bugfix Task Example

## Goal

Fix one small, local bug with minimal context and focused validation.

## Workflow Mode

Lite

## Required Reading

- `AGENTS.md`
- `docs/control/NEXT_CODEX_TASK.md`
- The affected source file
- The focused test file, if one exists

## Allowed Paths

- `<buggy-file>`
- `<focused-test-file>`

## Forbidden Paths

- dependency manifests and lockfiles
- CI configuration
- generated files
- unrelated modules
- docs/control state files unless explicitly requested

## Budget

- Maximum files changed: 2
- Maximum lines changed: 80
- Maximum commands run: 4
- Maximum execution time: 20 minutes
- Maximum retries: 1

## Validation Commands

```bash
<focused test command>
bash scripts/verify.sh
```

## Stop Conditions

- The bug spans multiple modules.
- The fix requires dependency changes.
- Validation scripts are missing or broken.
- The needed file is outside Allowed Paths.
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
Suggested next step:
```
