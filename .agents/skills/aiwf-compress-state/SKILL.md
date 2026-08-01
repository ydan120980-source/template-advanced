---
name: aiwf-compress-state
description: Compress accepted Evidence Ledger history into durable CURRENT_PROJECT_STATE.md and CHATGPT_HANDOFF.md updates.
---

# aiwf-compress-state

Use this skill after accepted Medium/Large work, closeout, axis switch, or several accumulated ledgers.

## Inputs

- Recent accepted Evidence Ledgers
- `docs/control/SPRINT_LEDGER.md`
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/CHATGPT_HANDOFF.md`
- `docs/control/NEXT_CODEX_TASK.md`, if it represents the next planned action
- `docs/ai-workflow/PROJECT_STATE_MACHINE.md`

## Stable Facts Vs Transient Details

Promote to stable facts:

- Accepted capabilities
- Current phase and axis
- Closed axes and bugfix-only areas
- Durable boundaries and forbidden assumptions
- Validation commands that remain canonical
- Active risks with continuing mitigation
- Next highest-value axis or next bounded sprint

Do not promote transient details:

- Temporary command output noise
- One-off implementation attempts
- Failed paths that no longer matter
- Chat-only speculation
- Unaccepted reviewer suggestions
- Historical details already captured in the ledger

## Process

1. Read recent ledger entries and identify accepted outcomes.
2. Update `CURRENT_PROJECT_STATE.md` with current phase, canonical facts, completed capabilities, active priorities, active risks, closed axes, validation summary, and next sprint candidates.
3. Update `CHATGPT_HANDOFF.md` with concise new-session context, last accepted sprint, active risks, default next action, and stale-state warning if needed.
4. Preserve append-only history in `SPRINT_LEDGER.md`; do not rewrite old entries unless correcting factual errors.
5. Clear or replace stale `NEXT_CODEX_TASK.md` only if explicitly asked.

## Outputs

- Proposed or applied `docs/control/CURRENT_PROJECT_STATE.md` update
- Proposed or applied `docs/control/CHATGPT_HANDOFF.md` update
- Active priorities update
- Risks update
- Closed axes / bugfix-only update
- Next axis proposal
- Follow-up task recommendation

## Stop Conditions

Stop if:

- Ledgers are missing or contradictory.
- The latest sprint is not accepted.
- Current repo facts conflict with proposed stable state.
- The update would require guessing project direction.
- The user has not authorized state file edits.
