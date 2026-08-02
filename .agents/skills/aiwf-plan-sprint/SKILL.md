---
name: aiwf-plan-sprint
description: Plan the next bounded AI Coding Workflow sprint from the verified GitHub Task Issue, current repository evidence, and the approved execution plan.
---

# aiwf-plan-sprint

Use this Skill before implementation when a new bounded sprint is needed.

## Authority and inputs

1. Read AGENTS.md and the current user instruction.
2. Read the verified GitHub Task Issue body with issue sync or issue verify.
3. Use a validated .aiwf/cache only when the remote Issue is unavailable; label the result CACHED and never change the contract from cache.
4. Read the stable governance documents under docs/ai-workflow/ and the task-specific source/tests named by the contract.
5. During the v1-to-v2 migration, read the transitional docs/control/NEXT_CODEX_TASK.md; it may narrow but never expand Issue scope.

Do not treat Run Guard JSONL, planning journals, chat summaries, or old state documents as a second authority.

## Process

Identify the current phase, axis, accepted evidence, active risks, closed areas, and stale facts. Select one bounded high-value sprint. Choose Lite, Standard, or Full based on scope, contract/public-interface risk, and reviewer need. Define Allowed Paths, Forbidden Paths, native validation, stop conditions, delivery-file budget, and one aggregate shell-command metric.

For Full work, initialize Run Guard only as optional diagnostic evidence unless the Task Issue explicitly requires it; it must not become a release gate. If the contract, base SHA, remote state, architecture, dependency, CI, public interface, or product direction is ambiguous, stop for the owner decision.

During migration, generate/update the local Task Packet. After PR A, record the next plan as an Issue event or Issue comment instead of creating a durable repository-local planning authority.

## Stop conditions

Stop if the Issue is missing/invalid, cache validation fails, the base SHA drifts, no bounded sprint can be defined, validation cannot be stated, or the candidate needs forbidden paths, remote mutation, a secret, a dependency, or an unapproved architecture/product decision.

## Output

Return the Task Packet or Issue event proposal, scope/budget, validation commands, reviewer requirement, Run Guard diagnostic classification, risks, and the next explicit decision.
