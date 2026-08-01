# Codex PR Review Prompt

Review this pull request in read-only mode.

Focus on:

- Correctness
- Missing tests
- Security risks
- Architecture boundary violations
- Backwards compatibility
- Unnecessary complexity

Required checks:

1. Read `AGENTS.md`.
2. Read `docs/control/NEXT_CODEX_TASK.md` if present.
3. Inspect the PR diff and changed files.
4. Compare changes against Allowed Paths, Forbidden Paths, and architecture docs when relevant.
5. Check whether tests and validation evidence match the risk of the change.

Do not modify files. Do not broaden scope. Return findings first, ordered by severity, followed by residual risk and recommended next action.
