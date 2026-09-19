---
name: aiwf-compress-state
description: Compress accepted Evidence Ledger results into the GitHub Task Issue summary and durable v2 governance evidence without creating a second authority.
---

# aiwf-compress-state

Use after accepted Medium/Large work, closeout, an axis switch, or an approved PR A/PR B boundary.

## Inputs

- Accepted Evidence Ledger and reviewer verdict
- Verified Task Issue contract/event chain, or a verified pre-adoption local bootstrap authority when no Issue exists yet
- Remote-vs-local validation status
- docs/ai-workflow governance references
- Transitional control files only while the v1-to-v2 migration is active

## Rules

Promote only accepted capabilities, current phase/axis, closed areas, durable boundaries, canonical validation, continuing risks, and the next bounded task. Do not promote transient command noise, stale SHAs, one-off failures, chat speculation, unaccepted reviewer suggestions, tokens, or local paths.

After PR A, write the durable summary as a validated Task Issue event/comment; do not recreate CURRENT_PROJECT_STATE.md, CHATGPT_HANDOFF.md, or SPRINT_LEDGER.md as a second control plane. Before Issue adoption, a local bootstrap may preserve only the immutable approved contract and local evidence; state compression must not mutate its scope or turn cache into authority. After verified `bootstrap_contract_adopted` handoff, the local bootstrap is retired. State compression never creates code commits, tags, releases, or remote protection changes.

## Stop conditions and output

Stop if ledgers contradict the active authority, bootstrap adoption is pending, the current base/head is unknown, the sprint is not accepted, or the update requires guessing product direction. Return the proposed Issue summary/event (or pre-adoption local handoff proposal), accepted facts, risks, closed axes, next sprint, and any owner decision still required.
