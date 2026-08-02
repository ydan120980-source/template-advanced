---
name: aiwf-compress-state
description: Compress accepted Evidence Ledger results into the GitHub Task Issue summary and durable v2 governance evidence without creating a second authority.
---

# aiwf-compress-state

Use after accepted Medium/Large work, closeout, an axis switch, or an approved PR A/PR B boundary.

## Inputs

- Accepted Evidence Ledger and reviewer verdict
- Verified Task Issue contract and event chain
- Remote-vs-local validation status
- docs/ai-workflow governance references
- Transitional control files only while the v1-to-v2 migration is active

## Rules

Promote only accepted capabilities, current phase/axis, closed areas, durable boundaries, canonical validation, continuing risks, and the next bounded task. Do not promote transient command noise, stale SHAs, one-off failures, chat speculation, unaccepted reviewer suggestions, tokens, or local paths.

After PR A, write the durable summary as a validated Task Issue event/comment; do not recreate CURRENT_PROJECT_STATE.md, CHATGPT_HANDOFF.md, or SPRINT_LEDGER.md as a second control plane. .aiwf runtime data is evidence, not state authority. State compression never creates code commits, tags, releases, or remote protection changes.

## Stop conditions and output

Stop if ledgers contradict the Issue, the current base/head is unknown, the sprint is not accepted, or the update requires guessing product direction. Return the proposed Issue summary/event, accepted facts, risks, closed axes, next sprint, and any owner decision still required.
