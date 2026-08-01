# Codex Fix CI Prompt

Fix the current CI failure with the smallest relevant change.

Required process:

1. Inspect the failing job, logs, and exact command.
2. Reproduce locally if possible.
3. Identify whether the failure is caused by this branch or appears pre-existing.
4. Make the smallest relevant fix.
5. Run `bash scripts/verify.sh`.
6. Avoid unrelated refactors, formatting churn, dependency changes, or architecture changes.
7. Explain clearly if the failure cannot be reproduced.

Respect `AGENTS.md`, `docs/control/NEXT_CODEX_TASK.md`, Allowed Paths, Forbidden Paths, and Stop Conditions. Return an Evidence Ledger with commands run, results, files changed, and remaining risk.
