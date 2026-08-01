# AIWF Run Guard

AIWF Run Guard is a project-local, Python-standard-library audit layer for complex Standard and Full sprints. It records failure/retry lineage while work is running and blocks acceptance when evidence, ownership, budget, validation, or review requirements are incomplete.

It does not start agents, modify global Hooks, or replace the Task Packet.

## Authority And Ledger Boundaries

`docs/control/NEXT_CODEX_TASK.md` remains the only sprint authority.

- planning-with-files stores the plan, human progress notes, attestation, and a small liveness ledger used by planning Hooks;
- Run Guard stores the stronger execution-audit contract used for retry budgets, ownership, handoffs, validation, and review;
- neither ledger may expand Allowed Paths or relax a stop condition.

The audit ledger is separate so updates to the installed planning Skill cannot silently change accepted Run Guard evidence.

## Configure A Run

Create a JSON input in the isolated plan directory:

```json
{
  "task_id": "2026-07-31-EXAMPLE",
  "retry_limit": 6,
  "workstreams": [
    {
      "id": "core",
      "owner": "main",
      "owned_paths": ["tools/example"],
      "require_handoff": true
    },
    {
      "id": "integration",
      "owner": "main",
      "owned_paths": [],
      "require_handoff": false
    }
  ],
  "allowed_paths": ["tools/example", "tests/example"],
  "forbidden_paths": [".github", ".codex"],
  "require_validation": true,
  "require_review": true,
  "first_artifact_seconds": 300,
  "heartbeat_seconds": 300,
  "command_budget": {
    "limit": 90,
    "metric": "shell_command_requests",
    "required_sources": ["main", "reviewer", "tester"]
  },
  "artifact_budget": {
    "limit": 12,
    "metric": "unique_artifact_files"
  }
}
```

Initialize once:

```powershell
py -3 -B -m tools.aiwf_run_guard init `
  --plan-dir .planning/2026-07-31-example `
  --config .planning/2026-07-31-example/run-guard-input.json
```

Initialization normalizes the configuration to `run-guard.json` and creates `run-guard-events.jsonl`. Repeating `init` with the same configuration is safe; changing an initialized run is rejected.

## Record Work

Start a workstream and record its first artifact:

```powershell
py -3 -B -m tools.aiwf_run_guard record --plan-dir $plan `
  --agent main --workstream core --kind workstream_started

py -3 -B -m tools.aiwf_run_guard record --plan-dir $plan `
  --agent main --workstream core --kind artifact `
  --file tools/example/engine.py
```

Record a failure before retrying:

```powershell
py -3 -B -m tools.aiwf_run_guard record --plan-dir $plan `
  --agent main --workstream core --kind command_failed `
  --failure-id core-tests-1 --summary "Focused tests failed"

py -3 -B -m tools.aiwf_run_guard record --plan-dir $plan `
  --agent main --workstream core --kind retry `
  --retry-of core-tests-1 --summary "Retry after targeted fix"
```

A retry may name a new agent. That event transfers effective ownership for the workstream and counts as one retry. Duplicate retry references and cross-workstream references are rejected.

Record an artifact-backed handoff only after the current attempt has an artifact. If review produces a later artifact, record a new handoff; the gate rejects stale handoffs that precede the latest artifact. Record required validation and review in a non-handoff integration workstream.

Each retry starts a new attempt. A required delivery workstream must record a new artifact and handoff for that current attempt. A failure remains unresolved until a later unique retry consumes it. Any later artifact, handoff, failure, or retry invalidates older validation and review evidence.

## Snapshot A Task-Level Command Budget

Declare every participating Codex session as a required source. After review, create one final snapshot using explicit read-only session JSONLs and the UTC task window:

```powershell
py -3 -B -m tools.aiwf_run_guard budget `
  --plan-dir $plan --agent main --workstream integration `
  --source main=C:/path/main.jsonl `
  --source reviewer=C:/path/reviewer.jsonl `
  --source tester=C:/path/tester.jsonl `
  --start 2026-07-31T12:00:00Z --end 2026-07-31T13:00:00Z
```

The counter reads only tool-call metadata needed to identify an outer `tools.shell_command(...)` JavaScript call and ignores the same text inside quoted strings or comments. It globally rejects duplicate call IDs and reports source IDs and counts without rendering commands, prompts, session paths, or unrelated message contents. A main-only snapshot cannot satisfy a configuration that declares helpers. The final gate requires fresh snapshots after current review evidence.

Before independent review, `budget.commands` is an informational `skip` because reviewer commands do not exist yet; `gate.review` remains the only blocking pre-review finding. After `review_passed`, missing or stale command snapshots become blocking findings until every declared source is aggregated.

## Inspect And Gate

```powershell
py -3 -B -m tools.aiwf_run_guard summary --plan-dir $plan --format markdown
py -3 -B -m tools.aiwf_run_guard gate --root . --plan-dir $plan --format json
```

The gate checks:

- JSONL integrity and retry lineage;
- retry budget;
- declared ownership overlap;
- platform-aware recorded path scope, resolved project-root containment, and artifact existence;
- an optional unique artifact-file budget whose identity keys follow the host platform's filesystem semantics: case-insensitive on Windows and case-sensitive on POSIX, matching the same platform-aware rule used for path scope, so duplicate records never inflate the count while genuinely distinct POSIX files are never collapsed;
- required workstream starts and handoffs;
- validation after the latest material evidence, then independent review after that validation;
- task-level shell-command snapshots for every declared main/helper source;
- first-artifact and active-work heartbeat liveness when configured.

Exit `0` means ready, `1` means the audit ran but found unresolved gate findings, and `2` means the invocation, configuration, transition, or ledger is invalid.

## Preflight

```powershell
.\scripts\aiwf-run-guard.ps1 preflight --root . --format json
```

Preflight is read-only and runs independent checks with at most four threads. Optional missing Git baseline, Git Bash, CodeGraph, or planning metadata is reported as `skip`; it is never fabricated as success.

## Operating Rules

- Initialize before implementation when the Task Packet marks Run Guard `required`.
- Never create a retry without a prior failure event.
- Do not count expected application exit codes, monitoring, messages, or successful revalidation as retries.
- Stop before a new retry would exceed the configured budget.
- In PowerShell validation batches, set `$ErrorActionPreference='Stop'` and check `$LASTEXITCODE` immediately after every native command. Never let a later success turn an earlier failure into an outer exit `0`.
- Record only valid failure kinds (`command_failed` or `integration_failed`), followed by `retry --retry-of <failure-id>` when another attempt is actually made.
- Do not edit JSONL to repair evidence. A corrupted real ledger is a stop condition.
- Treat the gate as recorded-evidence validation, not proof of undisclosed workspace changes. Without Git, use explicit inventories and state that full diff proof is unavailable.

## Review Lifecycle

For a run with `require_review=true`, use this non-circular sequence:

1. finish implementation, handoffs, and required validation;
2. run a pre-review gate and confirm that `gate.review` is the only blocking failure; configured informational skips such as disabled liveness checks are allowed;
3. draft a provisional Evidence Ledger and give it, the inventory, validation results, configuration, JSONL, summary, and pre-review gate to the independent reviewer;
4. if review passes, record `review_passed`;
5. snapshot all declared command sources after `review_passed`;
6. run the final gate, then finalize the Evidence Ledger. A bounded reviewer confirmation may verify only that the final ledger accurately incorporates the already-issued review; it must not introduce new implementation changes without another validation/review cycle.

## Bootstrap Limitation

The sprint that creates Run Guard cannot automatically capture actions that happened before the first passing tool build. Record those actions separately as bootstrap evidence and do not backfill them into the JSONL as if they had been observed live.
