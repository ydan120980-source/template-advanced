---
name: aiwf-execute-task
description: Execute the current verified Task Issue and transitional Task Packet within scope, validate the result, and return an auditable Evidence Ledger.
---

# aiwf-execute-task

## Required reading

Read AGENTS.md, the verified Task Issue contract, the task-specific docs/ai-workflow references, and (during migration) the current docs/control/NEXT_CODEX_TASK.md. Read source and tests before changing public contracts. Use issue sync --cache only when the cache digest verifies.

## Scope rules

- Modify only Issue/Task-Packet Allowed Paths.
- Never use a cache to widen scope or claim a remote Check Run.
- Do not add dependencies, CI permissions, public interfaces, or architecture surfaces unless the contract explicitly allows them.
- Do not invoke --confirm-write, merge, push, tag, Release, or ruleset changes unless the owner explicitly authorizes that exact remote action.
- Preserve unrelated worktree changes and never use history-rewriting or broad destructive commands.

## Execution and validation

Choose disjoint workstreams when parallel work materially helps; declare ownership and return all results to the main thread. Run every native command separately, inspect its own exit code, and record PASS/FAIL/BLOCKED/CACHED/NOT_RUN honestly. Use -B and keep runtime output in .aiwf, never in source.

Run Guard may record paths, retries, handoffs, and local summaries when the Task Issue calls for diagnostic evidence. Its budget/review findings do not qualify a release and cannot override CI, Security, release-candidate, payload/provenance, or Remote Gate evidence.

## Failure handling

Fix only failures caused by this sprint. Record a failure before a retry and stop on an over-budget retry, scope conflict, unsupported workflow shape, remote mutation requirement, secret, or unresolved validation failure.

## Output

Return an Evidence Ledger with task/contract identity, files changed/deleted, behavior changes, commands and native results, tests/docs, scope/budget, local-vs-remote evidence, risks/TODOs, reviewer result, Git state, and one next step. Stop at the plan's user review point.
