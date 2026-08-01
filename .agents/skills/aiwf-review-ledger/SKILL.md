---
name: aiwf-review-ledger
description: Review a completed Codex sprint Evidence Ledger for scope, validation, diff quality, and state update recommendations.
---

# aiwf-review-ledger

Use this skill after a Codex sprint produces a provisional or completed Evidence Ledger.

## Inputs

- The provisional Evidence Ledger plus pre-review gate, or the completed Evidence Ledger
- `docs/control/NEXT_CODEX_TASK.md`
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/SPRINT_LEDGER.md`
- Relevant diff or changed-file summary
- `docs/ai-workflow/EVIDENCE_LEDGER_TEMPLATE.md`
- `docs/ai-workflow/SPRINT_DECISION_SCORECARD.md` for Standard / Full
- Run Guard configuration, audit ledger, summary, and gate report when the Task Packet marks it `required`

## Checks

- Scope: changed files are within Allowed Paths and avoid Forbidden Paths.
- Validation: required commands were run, skipped commands have credible reasons, and failures are classified.
- Batched validation: verify each native command's own exit result; a later successful command must not mask an earlier failure behind outer exit `0`.
- Diff: changes are proportional to Task Size and Workflow Mode, with no unrelated cleanup or hidden contract changes.
- State update: recommendations are reasonable and do not turn transient details into stable facts.
- Evidence quality: files changed, commands, results, risks, limitations, and next step are clear enough for a new session.
- Run Guard: retry lineage is complete, budgets are honored or explicitly waived, ownership is conflict-free, required handoffs exist, and validation/review events match independent evidence.
- Command budget: independently recompute every declared main/helper source under the Task Packet's original metric and window; block main-only, missing, stale, duplicated, or over-limit evidence.
- Delivery-file budget: recompute unique normalized artifact paths from the ledger, include the Task Packet when declared, and block missing enforcement or over-limit evidence.

## Run Guard Review Sequence

When Run Guard requires independent review:

1. review the provisional Evidence Ledger after required validation and a pre-review gate whose only failure is `gate.review`;
2. issue the review verdict;
3. after a pass, the executor records `review_passed`;
4. the executor snapshots all declared command sources after review, runs the final gate, and finalizes the Evidence Ledger;
5. if requested, perform a bounded confirmation that the final ledger accurately includes the prior verdict and final gate. New code or evidence changes require fresh validation and review rather than this bounded confirmation.

## Output

Return one of:

- `pass`: sprint evidence is sufficient and no required follow-up blocks acceptance.
- `pass with follow-up`: sprint can be accepted, but a bounded follow-up is recommended.
- `blocked`: missing evidence, scope violation, validation failure, or state contradiction prevents acceptance.

Also include:

- Scope finding
- Validation finding
- Diff finding
- State update recommendation
- Next task recommendation
- Required fix sprint, if blocked

## Block Conditions

Block the sprint if:

- Forbidden Paths were modified.
- Required validation was not run and no acceptable reason is given.
- The diff exceeds the declared mode or budget.
- Evidence Ledger omits key facts.
- Required Run Guard evidence is corrupted, missing, internally inconsistent, or reports an unresolved gate failure.
- State update recommendations conflict with current project state.
- A contract, interface, dependency, CI, or architecture change happened without explicit permission.
