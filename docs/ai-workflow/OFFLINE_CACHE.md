# Offline Cache Boundary

The only project-local runtime areas for v2 governance are:

```text
.aiwf/cache/
.aiwf/runs/
```

`.aiwf/bootstrap/` is intentionally separate. It stores immutable temporary
authority and adoption receipts, not disposable cache, and therefore follows
the bootstrap authority rules in `TASK_ISSUE_CONTRACT.md`.

They are ignored by Git, excluded from the release inventory, and excluded
from payload/provenance digests. They may contain validated TaskContract
copies, migration matrices, bootstrap snapshots/plans, and local diagnostic
logs, but never tokens, secrets, or machine-specific absolute paths.

An offline executor may read a contract cache only after recomputing its
contract digest and checking its schema. It may continue implementation inside
the frozen scope and run local tests. It may not change the contract, widen
paths, freeze a new candidate, claim a remote Check Run, merge, tag, publish,
or close the Task Issue. The CLI must return `CACHED` for this condition, not
`PASS` or `READY_FOR_RELEASE`.

The cache is disposable evidence. For tasks that already have a GitHub Task
Issue, that Issue remains authoritative;
cache contents do not override a later Issue event, base SHA, PR head, or
remote gate result. Delete or rotate runtime cache contents only after an
explicitly scoped cleanup decision.

A cache may not impersonate `local_bootstrap`. If no Issue exists, execution
requires a separately verified bootstrap authority record with the exact
approved digest and repository/base binding. After successful adoption, Issue
and validated cache semantics resume and the local bootstrap is retired.
