# AIWF Run Guard

AIWF Run Guard is an optional local diagnostic layer for complex sprints. It
records paths, failures, retry lineage, handoffs, validation, review, liveness,
and command summaries. It does not start agents, edit global Hooks, replace a
Task Issue, or qualify a GitHub release by itself.

## Authority boundary

The GitHub Task Issue is the active task authority. A validated cache under
`.aiwf/cache/` can support offline execution but cannot change scope or
acceptance. `.aiwf/runs/` stores disposable local diagnostics. Neither runtime
directory is released or included in a payload digest.

The v1 control files (`docs/control/NEXT_CODEX_TASK.md` and siblings) are
retired; their history remains in Git and
`docs/control/CODEX_RUNTIME_PROFILE.md` survives only as legacy compatibility
reference.

## Diagnostics

The existing CLI remains available:

```powershell
py -3 -B -m tools.aiwf_run_guard init --plan-dir <run-dir> --config <config.json>
py -3 -B -m tools.aiwf_run_guard record --plan-dir <run-dir> --agent main --workstream core --kind artifact --file tools/example.py
py -3 -B -m tools.aiwf_run_guard summary --plan-dir <run-dir> --format json
py -3 -B -m tools.aiwf_run_guard gate --root . --plan-dir <run-dir> --format json
```

It still rejects corrupted JSONL, invalid ownership, out-of-scope artifacts,
unresolved failures, and invalid retry lineage. A configured local gate may
report unresolved diagnostics, but those findings are advisory to release
qualification: CI, Security, release-candidate, payload/provenance, and the
Remote Gate are evaluated independently. No workflow may use Run Guard as a
replacement for those checks.

## Command budget metric

The `budget` command counts `shell_command_requests` from session JSONL files
that are explicitly supplied as evidence. One outer tool request that bears
shell calls counts exactly once; batched calls inside the same request do not
split the count. The metric is a request count for diagnostics: it is not a
process count, not a number of actual command executions, and not a token or
cost estimate.

Recognized event forms:

- a `response_item` wrapping a `custom_tool_call` whose executable input
  invokes `tools.shell_command(...)` (historical) or `tools.exec_command(...)`
  (current host);
- a named `function_call` — wrapped or top-level — whose tool name is a known
  shell tool (`exec`, `shell`, `shell_command`, `exec_command`, `bash`),
  including Unix-epoch-millisecond timestamps.

Strings, comments, plain messages, and pure-wait tool calls never count. An
indirect shell reference (aliasing, computed access, destructuring) or a
corrupted event raises an explicit error instead of producing a
complete-looking zero count. Output keeps only counts, source identifiers,
and fingerprints; command bodies are never copied.

## Evidence discipline

Record a failure before a retry, record an artifact before a required handoff,
and keep validation/review evidence newer than the last material artifact. A
command budget is useful for diagnosing runaway work; it is not a release
policy. A reviewer can use the summary and ledger to explain local execution,
but a successful summary does not prove a remote Check Run or Release.

Use standard-library validation with `-B`, inspect each native exit code, and
report CACHED/NOT_RUN/BLOCKED states honestly. Do not edit JSONL to repair
evidence; a corrupted diagnostic ledger is itself a diagnostic finding.
