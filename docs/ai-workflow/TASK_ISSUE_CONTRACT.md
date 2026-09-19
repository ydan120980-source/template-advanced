# Task Issue Contract

The normal v2 active task is a GitHub Task Issue. The Issue body is the
long-lived authoritative contract; local files under `.aiwf/cache/` are
validated offline copies and never a second authority.

Before a Task Issue exists, an owner may explicitly approve the exact same
`governance.task/v2` contract for temporary `local_bootstrap` authority. That
record is stored under `.aiwf/bootstrap/<task-id>/`, not `.aiwf/cache/`, and is
valid only for the independently supplied expected digest, repository identity,
and Git base. It cannot be used to widen scope or claim remote evidence.

## Contract body

The body contains one `governance.task/v2` JSON object with exactly these keys:

```text
schema_version, task_id, task_type, repository_id, base_sha,
goal, allowed_paths, forbidden_paths, acceptance, contract_digest
```

`contract_digest` is the SHA-256 of canonical UTF-8 JSON for the same object
with `contract_digest` removed. Canonical JSON uses sorted keys, compact
separators, UTF-8, and no platform-specific path spelling. Every path is a
repository-relative non-empty string; absolute paths, drive prefixes, and
parent traversal are invalid.

The contract freezes the base commit, scope, acceptance rules, and stop
conditions. A changed base, digest, allowed path, or forbidden path is a new
contract and must not be silently accepted from cache.

## CLI boundary

```powershell
py -3 -B -m tools.governance_v2 issue verify --contract <contract.json>
py -3 -B -m tools.governance_v2 issue sync --repo owner/name --issue-number 3 --output <cache.json>
py -3 -B -m tools.governance_v2 issue sync --cache <validated-cache.json>
py -3 -B -m tools.governance_v2 issue append --event-file <event.json> --repo owner/name --issue-number 3 --confirm-write
py -3 -B -m tools.governance_v2 bootstrap init --root . --contract <contract.json> --expected-digest <approved-digest> --repository-id owner/name --authorization-ref <approved-context-ref>
py -3 -B -m tools.governance_v2 bootstrap verify --root . --task-id <task-id> --expected-digest <approved-digest> --repository-id owner/name
py -3 -B -m tools.governance_v2 bootstrap adopt --root . --task-id <task-id> --expected-digest <approved-digest> --repo owner/name --issue-number 3
```

`sync` performs a read-only GET and returns `PASS`; a validated offline cache
returns `CACHED`. Network errors, incomplete responses, invalid contracts, and
unknown task scope are not promoted to success. `append` validates the event
before it can construct a request and refuses without the explicit
`--confirm-write` flag. CI workflows have no `issues: write` permission.

`bootstrap init` requires HEAD to equal the contract base on first creation and
stores an immutable authorization record. Re-running the same approved context
is idempotent; a different digest or authorization context is rejected.
`bootstrap verify` accepts later local commits only while the original base
remains in current Git history. The expected digest is mandatory so editing a
contract and recomputing its own digest cannot self-authorize wider scope.
`bootstrap adopt` is read-only: remote Issue creation/comment append still goes
through `issue create` / `issue append --confirm-write`. Adoption succeeds only
when the Issue carries the exact same contract/digest and a matching
`bootstrap_contract_adopted` event. Once handoff begins, dual-authority execution
is blocked until adoption completes.

All commands emit JSON. `PASS`, `FAIL`, `BLOCKED`, and `CACHED` exit with 0, 1,
2, and 3 respectively; `NOT_RUN` is a recorded state, never success.

## Security and ownership

Do not place tokens, credentials, local absolute paths, or personal runtime
state in the Issue body, event payload, cache, or release artifacts. The
contract specifies what an executor may touch; it does not grant remote write
authority. Remote writes remain owner-approved operations outside ordinary CI.
The same restriction applies to local bootstrap: it grants bounded local task
authority only, never GitHub write, CI, merge, tag, release, or external-service
authority.
