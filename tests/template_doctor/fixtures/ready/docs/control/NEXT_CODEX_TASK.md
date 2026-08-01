# Current Task

Task ID: READY-FIXTURE-001
Workflow Mode: Standard

## Goal

Verify that the initialized sample project remains healthy.

## Allowed Paths

- `src/**`
- `tests/**`

## Forbidden Paths

- `.git/**`
- credential files

## Budget

- Maximum files changed: 4
- Maximum commands run: 10

## Validation Commands

```powershell
py -3 -m unittest discover -s tests -v
```

## Stop Conditions

- Stop if a dependency change is required.

## Required Return Format

Return changed files, command results, risks, and one suggested next step.
