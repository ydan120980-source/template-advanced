# V1 to V2 Migration

V2 moves active task authority from repository-local control documents to a
GitHub Task Issue plus a validated offline cache. The migration is staged so
that old history remains auditable while the new control plane is introduced.

## PR #2 matrix

Before closing the existing release PR, build and verify deterministic
`migration-commits.json` and `migration-files.json` from the explicit
`origin/main` and PR-head refs. The approved frozen facts are 12 commits, 28
paths, base `5893027b0c57a121b8726b72b39d133b58978f04`, and PR head
`35aabc2299c6768e3e6924e396cfc0e5983827cc`. A changed head invalidates both
matrices and requires a full rebuild. No rebase, force-push, history deletion,
or branch deletion is part of this migration.

## PR A: Governance Foundation

PR A adds the Task Issue/event chain, read-only cache, static/Remote Gate,
read-only release-candidate workflow, minimum job permissions/timeouts, and
new governance documentation. It retires the active local files
`NEXT_CODEX_TASK.md`, `CURRENT_PROJECT_STATE.md`, `CHATGPT_HANDOFF.md`,
`SPRINT_LEDGER.md`, and `docs/control/evidence/**` from the final source tree;
their history remains in Git. `CODEX_RUNTIME_PROFILE.md` and example material
remain runtime/reference documentation.

Run Guard remains available for local path, retry, handoff, and diagnostic
summaries. Its ledger is not the Task Issue and its local gate is not a global
release qualification. A broken or missing Run Guard report cannot invalidate
independently passed CI, Security, payload, provenance, or Remote Gate assets.

PR A ends at a mandatory user review before squash merge, Bootstrap A,
Bootstrap B, Release Freeze, or any remote protection/release action.

## PR B and rollback boundary

PR B is a separate task from the latest post-PR-A `main`. It contains product
and release migration, v2.0.0, formal release workflow/notes, payload and
immutable release provenance, and the PR B candidate freeze. None of those
changes may be smuggled into PR A.

Rollback before a remote merge means abandoning the local PR A branch or
reverting its committed changes after review; do not rewrite history. Remote
Bootstrap A/B, required checks, rulesets, tags, Releases, and Issue closure
require their own exact-SHA evidence and explicit owner approval.
