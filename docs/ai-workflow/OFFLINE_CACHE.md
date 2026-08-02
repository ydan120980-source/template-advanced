# Offline Cache Boundary

The only project-local runtime areas for v2 governance are:

```text
.aiwf/cache/
.aiwf/runs/
```

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

The cache is disposable evidence. The GitHub Task Issue remains authoritative;
cache contents do not override a later Issue event, base SHA, PR head, or
remote gate result. Delete or rotate runtime cache contents only after an
explicitly scoped cleanup decision.
