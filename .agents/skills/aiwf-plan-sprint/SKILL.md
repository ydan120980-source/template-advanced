---
name: aiwf-plan-sprint
description: Plan the next bounded AI Coding Workflow sprint and generate docs/control/NEXT_CODEX_TASK.md from current state, ledger, handoff, and scorecard inputs.
---

# aiwf-plan-sprint

Use this skill when planning the next Codex sprint before implementation.

## Inputs

- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/SPRINT_LEDGER.md`, especially recent accepted or blocked entries
- `docs/control/CHATGPT_HANDOFF.md`
- `docs/control/CODEX_RUNTIME_PROFILE.md`
- `docs/ai-workflow/SPRINT_DECISION_SCORECARD.md`
- Relevant project files needed to understand the candidate sprint

Do not read `archive/`, `examples/`, or `references/` unless the user explicitly requests them.

## Process

1. Identify Current Phase, Current Axis, active priorities, risks, closed axes, and stale state warnings.
2. Review the latest ledger evidence and determine whether the previous sprint was accepted, needs follow-up, blocked, or should trigger closeout.
3. Select the highest-value bounded next sprint.
4. Choose Workflow Mode:
   - Lite: small local fix, narrow Allowed Paths, focused validation is enough, no state update required.
   - Standard: medium work, multi-file consistency, shared docs/contracts, adjacent behavior, or local hardening.
   - Full: large work, new axis, state transition, boundary-sensitive work, public interface/contract change, or reviewer-required work.
5. Apply scorecard thresholds:
   - Outcome Impact + Project Value < 7: do not generate implementation; choose closeout, context fill, or switch axis.
   - Verification Confidence <= 2: generate preflight/read-only probe.
   - Context Completeness <= 2: collect context first.
   - Boundary Risk >= 4 or Reviewer Worthiness >= 4: shrink scope or use Full with reviewer.
6. Classify AIWF Run Guard as `required`, `optional`, or `off` in the Task Packet. Default concurrency/retry-sensitive Full work to `required`; use `off` only when the tool is unavailable or disproportionate and state why.
7. Define one task-level shell-command metric for all main/helper sessions. Declare expected source IDs, role allocations, and reserve before execution; never reinterpret the limit as main-only after helpers run.
8. Define a delivery-file budget that counts unique recorded artifact paths, including the generated Task Packet when it is a delivery artifact. Keep isolated planning evidence outside that delivery count and reserve headroom instead of planning exactly to the limit.
9. Require fail-fast validation batches: every native command's exit code must be checked before the next command runs.
10. Draft `docs/control/NEXT_CODEX_TASK.md` with goal, mode, required reading, Allowed Paths, Forbidden Paths, budget, validation, stop conditions, return format, and the Run Guard classification.

## Outputs

- Updated or proposed `docs/control/NEXT_CODEX_TASK.md`
- Scorecard summary for Standard / Full
- Lite decision note for Lite
- Reviewer requirement, if any
- Run Guard classification and required gate command for Standard / Full work
- Aggregate command metric, declared session sources, role allocations, and reserve
- Unique delivery-file metric, limit, planned files, and reserve
- State update recommendation, if planning reveals stale state

## Stop Conditions

Stop and ask for clarification or context if:

- Required control files are missing or contradictory.
- The repo state appears newer than the current handoff or ledger.
- No bounded high-value sprint can be identified.
- The only useful work requires Forbidden Paths.
- Validation cannot be defined.
- The candidate sprint would require unapproved dependency, CI, public interface, or architecture changes.
