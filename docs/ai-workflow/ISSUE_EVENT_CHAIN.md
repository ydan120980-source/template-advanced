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

For local-bootstrap handoff, `bootstrap_contract_adopted` is the explicit
transition proof. Its Issue must carry the same task contract and digest as the
local bootstrap. A local `bootstrap adopt` command only reads and verifies this
remote evidence; it does not create the Issue or append the event.

The contract `base_sha` fixes the approved starting commit. The adoption
event's `subject_sha` identifies the subject of its verified Issue event chain;
it may be a later candidate commit. These two SHAs need not be equal. The
existing requirement for one unchanged subject throughout a chain still holds.

Pending handoffs and adoption receipts verify their own digests and bind the
task, repository, base, contract digest, original bootstrap record, and target
Issue identity. A receipt retains the complete adoption event, its subject and
digest, and the pending-record digest. It deliberately does not store a chain
head as an immutable historical fact: the current remote chain can prove that
the retained adoption event still exists, but cannot authenticate which later
event was the head when a local receipt was first written. Multiple matching
adoption events are a conflict. Repeating adoption re-reads the Issue and
verifies the event chain without rewriting the receipt or appending events;
later chain extensions are compatible with the original verified receipt.
Local self-digests detect corruption but do not authenticate remote facts.

Authority, pending, and receipt records are published from a fully written,
synced same-directory temporary file through a create-only atomic link. A torn
temporary write cannot expose partial JSON at the immutable target, and a retry
may recover from the intact pending record without overwriting a conflicting
record or performing a remote write.

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

Likewise, a local bootstrap may not assume adoption from Issue existence alone.
Until the exact contract and matching adoption event verify, handoff remains
pending and local execution is blocked to avoid two simultaneous authorities.

## Append boundary

The CLI constructs a GitHub Issue comment only through the explicit
`issue append ... --confirm-write` command. Normal planning, execution,
review, CI, and release-candidate paths only read or record local evidence.
Each comment should contain one fenced JSON event so that later sync can parse
and verify it without depending on presentation text.
