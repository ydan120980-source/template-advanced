# Full Boundary Review Task Example

## Goal

Complete a boundary-sensitive change with independent review, validation interpretation, architecture review, and optional state compression.

## Workflow Mode

Full

## Required Reading

- `AGENTS.md`
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/CODEX_RUNTIME_PROFILE.md`
- `docs/control/NEXT_CODEX_TASK.md`
- `docs/architecture/README.md`
- `docs/security/README.md`
- `docs/dependencies/README.md`
- Relevant contracts, modules, tests, and migration notes

## Allowed Paths

- `<boundary-module>`
- `<public-contract-file>`
- `<boundary-tests>`
- `<approved-docs>`

## Forbidden Paths

- dependencies and lockfiles unless explicitly approved
- auth-sensitive files
- production data access paths
- deployment configuration
- generated artifacts unless listed in Allowed Paths
- unrelated modules

## Subagents

- `reviewer`: use `.codex/agents/reviewer.toml` for scope drift, missing tests, risky diffs, architecture risk, and Evidence Ledger quality.
- `tester`: use `.codex/agents/tester.toml` for validation command interpretation.
- `architect`: use `.codex/agents/architect.toml` for module boundaries, contracts, dependency direction, generated files, and migration risk.
- `state-compressor`: use `.codex/agents/state-compressor.toml` only after accepted work, and only for allowed control-state writes.

## MCP Allowed / Forbidden

Allowed:
- Read-only GitHub issue or pull request context, if explicitly authorized.
- Read-only Figma design context, if explicitly authorized.
- Read-only browser documentation lookup, if explicitly authorized.
- Read-only logs with secrets and PII redacted, if explicitly authorized.

Forbidden:
- production writes;
- deployments;
- secret access;
- changing repository settings;
- writing to external systems;
- sending production data or sensitive logs to external services.

## Budget

- Maximum files changed: 15
- Maximum lines changed: 900
- Maximum commands run: 12
- Maximum execution time: 2 hours
- Maximum retries: 2
- Maximum subagent calls: 4

## Validation Commands

```bash
<focused boundary tests>
<contract tests>
<affected integration tests>
bash scripts/verify.sh
```

## Stop Conditions

- The change requires unapproved dependency changes.
- The public contract change is not authorized.
- Security policy conflicts with implementation needs.
- MCP access would require writes, secrets, deployment, or production data.
- Subagents disagree on a blocking boundary or validation issue.
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
Subagents used:
Reviewer result:
Tester result:
Architect result:
State compressor recommendation:
Tests added/updated:
Docs added/updated:
Risks:
Known limitations:
Follow-up candidates:
Blocked items:
Suggested next step:
```
