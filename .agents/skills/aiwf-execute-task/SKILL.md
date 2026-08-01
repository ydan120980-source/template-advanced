---
name: aiwf-execute-task
description: Execute the current docs/control/NEXT_CODEX_TASK.md within scope, validate the result, and return an Evidence Ledger.
---

# aiwf-execute-task

Use this skill when implementing the current Codex task packet.

## Required Reading

1. `AGENTS.md`
2. `docs/control/NEXT_CODEX_TASK.md`
3. For Standard / Full: `docs/control/CURRENT_PROJECT_STATE.md`
4. For Standard / Full: `docs/control/CODEX_RUNTIME_PROFILE.md`
5. Task-specific files listed in the task packet

Read `docs/ai-workflow/` only when the task packet requires scorecard, ledger, state machine, or low-cost workflow reference.

## Scope Rules

- Modify only Allowed Paths listed in `NEXT_CODEX_TASK.md`.
- Treat read-only paths as context only.
- Do not modify Forbidden Paths.
- Do not add dependencies, CI, workflows, public entrypoints, or architecture surfaces unless explicitly allowed.
- Do not update state files unless the task explicitly asks.

## Budget Rules

- Track maximum files changed, commands run, retries, helper calls, and execution time from the task packet.
- Count the declared shell-command metric across every main/helper session from the authorized task start; role allocations are subdivisions of one task-level limit.
- Count unique recorded delivery artifacts against the original file limit; duplicate or case-variant paths do not create extra budget, while the Task Packet counts when declared as a delivery artifact.
- Stop before exceeding budget.
- If scope legitimately needs to grow, report escalation instead of silently expanding.

## Run Guard

- Read the Task Packet's Run Guard classification before implementation.
- When `required`, initialize `tools.aiwf_run_guard` in the active isolated plan before implementation work.
- Record `command_failed` or `integration_failed` before any counted retry, then record exactly one `retry` with `retry_of` for the next attempt.
- Record workstream starts, artifacts, handoffs, validation, and review evidence. Do not backfill automatic evidence for events that predate initialization; label them bootstrap evidence instead.
- After implementation and validation, run a pre-review gate. When independent review is required, `gate.review` must be its only unresolved finding; otherwise stop and fix or escalate before review.
- Draft a provisional Evidence Ledger for the independent reviewer. After a pass, record `review_passed`; do not finalize until command snapshots and the final gate are current. A bounded final confirmation may check only that the finalized ledger incorporates the issued review accurately.
- After `review_passed`, snapshot every declared main/helper JSONL in one aggregate budget operation, then run the final gate. Missing, stale, duplicated, main-only, or over-limit evidence blocks acceptance.
- Stop on corrupted evidence, ownership conflicts, stale validation/review evidence, unresolved failures, or an unapproved budget overrun.
- Treat expected domain exit codes, monitoring, helper messages, and successful revalidation as non-retries.
- After every native command in a batched shell request, inspect its exit code before running the next command. In PowerShell, `$ErrorActionPreference='Stop'` alone is insufficient for native executables; explicitly stop when `$LASTEXITCODE` is non-zero.

## Validation Rules

- Run the validation commands listed in the task packet.
- Use focused validation for Lite.
- Use focused plus relevant adjacent/default checks for Standard / Full when specified.
- Report every command attempted and its exact result.
- Never report a batch as passed from its final outer exit code when an earlier inner command failed.
- If validation cannot run, report the command, reason, and whether this blocks acceptance.

## Failure Handling

- Fix only failures caused by this sprint.
- Do not chase unrelated pre-existing failures.
- If failed, partial, or blocked, classify the failure as scope creep, boundary violation, verification failure, context missing, wrong task size, low value work, workspace noise mix-in, fake confidence, architecture drift, or product drift.

## Output

Return an Evidence Ledger containing:

- Sprint ID, goal, task size, and workflow mode
- Files changed and behavior changed
- Commands run and results
- Tests/docs added or updated
- Scope check against Allowed Paths and Forbidden Paths
- Risks and known limitations
- Failure taxonomy if relevant
- Run Guard gate result, event/retry counts, and bootstrap evidence limitation when enabled
- State files updated or state update recommendation
- Follow-up candidates and suggested next step
