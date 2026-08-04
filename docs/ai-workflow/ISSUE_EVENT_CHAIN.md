# Issue Event Chain

Every Task Issue state change is one append-only JSON event in an Issue
comment. The chain is tamper-evident evidence, not a claim of legal
non-repudiation or WORM storage.

## Event schema

Each event contains exactly:

```text
sequence, event_id, event_type, task_id, subject_sha,
previous_event_digest, payload, actor, created_at, event_digest
```

`event_id` is `evt-<six digit sequence>`. The first event has a null
`previous_event_digest`; each later event names the immediately preceding
digest. Every event in one chain must keep the exact same `task_id` and
`subject_sha`; a changed subject SHA starts a new chain and is not continuity.
`event_digest` is SHA-256 of canonical JSON with that field removed.
Supported event types include task opening/decisions, migration matrices,
bootstrap transitions, validation/check results, candidate freeze/supersede,
PR transitions, tag/release evidence, blocking, and task closure.

## Verification

`issue verify --events-file` checks exact keys, event IDs, positive sequence,
allowed event type, digest recomputation, one task ID, predecessor continuity,
gaps, duplicates, and ordering. If two distinct successors use the same
`previous_event_digest`, verification returns:

```text
status: FAIL
code: EVENT_CHAIN_FORK
```

The verifier never chooses a branch. A missing comment, an incomplete API
response, a changed subject SHA, or a cache digest mismatch is failure or
blocked evidence, not a successful check.

## Append boundary

The CLI constructs a GitHub Issue comment only through the explicit
`issue append ... --confirm-write` command. Normal planning, execution,
review, CI, and release-candidate paths only read or record local evidence.
Each comment should contain one fenced JSON event so that later sync can parse
and verify it without depending on presentation text.
