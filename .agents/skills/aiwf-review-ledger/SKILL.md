---
name: aiwf-review-ledger
description: Review an Evidence Ledger and exact diff for scope, validation, contract integrity, and next-step readiness.
---

# aiwf-review-ledger

Review the provisional/completed Evidence Ledger, verified Task Issue, relevant diff, validation output, and the stable governance documents under docs/ai-workflow/. During migration, include the transitional Task Packet; after PR A, do not require retired docs/control files.

## Checks

- Contract: Issue digest, base SHA, acceptance, allowed/forbidden paths, and event-chain evidence are consistent.
- Scope: every changed/deleted path is authorized; no PR B, secret, dependency, remote write, or unrelated cleanup is hidden in the diff.
- Validation: each native command has an explicit result; skipped/CACHED/BLOCKED evidence is not promoted to PASS; local checks are separated from exact-SHA remote checks.
- Workflow/security: permissions, action pins, timeouts, read-only release-candidate behavior, and unsupported YAML boundaries are tested.
- Diff quality: changes fit the sprint and preserve rollback/history rules.
- Run Guard: if used, verify diagnostic retry/path/handoff accounting, but do not treat its local gate as release qualification.
- State: only accepted durable facts become Issue summary/events; transient command noise and unaccepted suggestions remain out.

## Review sequence

Issue a clear PASS or FINDINGS verdict with file/line anchors. After a pass, the executor records the review event and rechecks any evidence that changed. Do not authorize squash merge, Bootstrap A/B, Release Freeze, tag, or Release from a local ledger; those are later owner-controlled gates.

## Output

Return verdict, findings by severity, validation/scope assessment, known limitations, and the smallest safe next step.
