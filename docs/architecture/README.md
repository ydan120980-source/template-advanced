# Architecture

This document records the current module boundaries and public contracts that must survive across Codex sessions.

## Runtime And Module Boundaries

The repository targets Python 3.11+ and the Python standard library only.

- `tools/template_doctor/`
  - `__main__.py`: CLI parsing, root validation, output selection, and exit mapping.
  - `engine.py`: bounded concurrent execution and deterministic result ordering.
  - `rules.py`: independent, read-only repository checks.
  - `models.py`: immutable check and report contracts.
  - `reporters.py`: deterministic JSON and Markdown rendering.
- `tools/aiwf_run_guard/`
  - `__main__.py`: `init`, `record`, `summary`, `budget`, `gate`, and `preflight` commands.
  - `config.py` and `models.py`: normalized configuration, event, finding, and report schemas.
  - `ledger.py`: locked, append-only JSONL event persistence and deterministic replay validation.
  - `budget.py`: privacy-preserving shell-request counting from explicitly supplied
    session JSONL files (wrapped `custom_tool_call` inputs invoking shell tools and
    named `function_call` direct shell requests; corrupted evidence raises instead
    of counting zero).
  - `gate.py`: ownership, artifact, retry, validation, review, liveness, and command-budget evaluation.
  - `preflight.py`: bounded read-only capability probes.
  - `reporters.py`: deterministic JSON and Markdown output.
- `tools/governance_v2/`
  - `__main__.py`: `issue` (`init`, `sync`, `verify`, `create`, `append`), `migration`
    (`build`, `verify`), `bootstrap` (`snapshot`, `plan`), and `gate` (`static`, `github`) commands.
  - `models.py`: frozen `governance.task/v2` contract and self-verifying event schemas.
  - `canonical.py`: deterministic canonical JSON digest used by contracts and events.
  - `issue.py`: contract load/verify/sync, verified Issue creation and readback, verified
    event appending, and event-chain verification.
  - `bootstrap.py`: read-only Stage 0 snapshots and desired-plan previews; unavailable refs
    are distinguished from expected states instead of being cached as facts.
  - `migration.py`: commit/file matrix build and verify for audited migrations.
  - `remote.py`: read-only Remote Gate evaluation of GitHub check runs.
  - `workflow.py`: static workflow/workflow-permission checks.
- `tools/workflow_eval/`
  - `__main__.py`: `prepare`, `grade`, and `report` commands for repeatable
    workflow comparison experiments.
  - `tasks.py`: task definitions (historical fix, pre-fix baseline, acceptance).
  - `prepare.py`: generates isolated trial directories and task briefs from a locked
    historical source snapshot.
  - `grade.py`: independently executes acceptance against candidate trees and records
    native command results, scope checks, the narrow pre-scoring Git root probe, and the
    coordinator's trial-validity attestation.
  - `audit.py`: audits a trial sub-agent's session record on every tool channel
    (read, search, write, shell) and reports out-of-trial targets, source-repository
    contact, path-less calls, and unanchored Git commands as facts.
  - `report.py`: aggregates trial JSON records into a deterministic Markdown comparison
    that reports record structure, trial protocol validity, and functional outcome
    separately.
- `scripts/` and `evals/`: dependency-free orchestration; they may invoke the Python tools and tests but contain no business logic.
- `tests/`: isolated `unittest` coverage and fixtures; production modules never import tests.

## Task Authority And Evidence Responsibility

The verified GitHub Task Issue is the long-lived planning authority: its contract fixes
the goal, allowed and forbidden paths, acceptance, base SHA, budget, and stop conditions.
`docs/control/NEXT_CODEX_TASK.md` and the other v1 control files are retired; their
history remains in Git and `docs/control/CODEX_RUNTIME_PROFILE.md` survives only as
legacy compatibility reference. Validated offline caches under `.aiwf/cache/`,
planning journals under `.planning/`, and Run Guard ledgers are execution evidence:
they may record and subdivide work but cannot expand Issue scope or relax a stop
condition. Governance evidence events appended to the Task Issue are the durable
record; local files are supporting evidence only.

## Dependency Direction

CLI entry points may import engines, reporters, and models. Engines and gates may import rules/configuration, ledgers, and models. Rules and persistence may depend on models and standard-library adapters. Models must not import CLI, reporters, repository scripts, tests, or host-specific Codex integration.

Template Doctor and Run Guard are sibling tools; neither may make the other required for its core CLI contract. Workflow scripts may compose both. Circular package imports, production imports from `tests`, and hidden third-party dependencies are forbidden.

Dependency manifests, lockfiles, CI, global Codex configuration, Hooks, Skills, MCP, and external-service integration require an explicitly authorized Task Packet and owner decision.

## Public Contracts

### Template Doctor

`python -B -m tools.template_doctor --root <path> --format json|markdown`

- Exit `0`: ready; exit `1`: completed with findings; exit `2`: invocation or operational error.
- Every result exposes `rule_id`, `severity`, `status`, `evidence`, and `recommendation`.
- Top-level reports expose `root`, `status`, `summary`, and deterministically ordered `results`.
- Rule execution is capped at four threads; concurrency must not change report ordering.

### AIWF Run Guard

`python -B -m tools.aiwf_run_guard <init|record|summary|budget|gate|preflight> ...`

- `run-guard.json` is the normalized immutable run configuration.
- `run-guard-events.jsonl` is an append-only, UTF-8, one-event-per-line ledger with monotonic sequence/event IDs and validated lifecycle transitions.
- Failures require unique lineage IDs; retries must consume exactly one prior same-workstream failure.
- Required delivery workstreams need current-attempt artifacts and handoffs. Validation must follow material evidence, independent review must follow validation, and final all-source command snapshots must follow review.
- Audit commands return `0` ready, `1` valid but not ready, and `2` invalid invocation/configuration/ledger operation.

Rule IDs, event kinds, CLI flags, exit codes, JSON keys, JSONL semantics, ordering, privacy redaction, and lifecycle order are compatibility-sensitive. Changes require explicit scope, regression tests, documentation, and independent review.

### Governance v2

`python -m tools.governance_v2 <issue|migration|bootstrap|gate> <command> ...`

- Contracts use the frozen `governance.task/v2` schema with a self-verifying
  `contract_digest`; events use a self-verifying digest chain per Task Issue.
- `issue create` and `issue append` require explicit `--confirm-write` plus a
  `GH_TOKEN`/`GITHUB_TOKEN` credential, verify every write through a readback,
  and are the only remote-write paths; every other command is local or read-only.
- Local commands report JSON with deterministic exit codes: `0` pass,
  `1` fail, `2` blocked, `3` cached, `4` not run.
- Failure codes (for example `CONFIRM_WRITE_REQUIRED`, `ISSUE_CONTRACT_CONFLICT`,
  `EVENT_CHAIN_FORK`) are compatibility-sensitive; never disclose credentials or
  workstation paths in command results.

### Workflow Eval

`python -m tools.workflow_eval <prepare|grade|report> ...`

- `prepare` materializes isolated trial directories from a locked historical
  source snapshot plus one task definition; trial copies carry no
  answer-recoverable Git history.
- `grade` runs an acceptor against a candidate tree, records the native
  command exit codes, and enforces the task's scope check.
- `report` merges trial JSON records into a deterministic Markdown comparison.
- Trial agents never modify task definitions or acceptors; grades are final
  only when recomputed on the main thread.
- Trial validity is never inferred from a grade record. `trial_isolated` records
  only the pre-scoring Git root probe; `trial_validity` carries the coordinator's
  VALID / INVALID / UNVERIFIED attestation plus its audit basis. An unattested
  record is UNVERIFIED and cannot fill a valid comparison slot, and `report`
  answers record structure, protocol validity, and functional outcome separately.

## Generated And Local Files

- `.planning/<task-id>/run-guard.json`, `run-guard-events.jsonl`, attestations, and planning journals are generated local evidence. Their source is the active Task Packet plus the run configuration and recorded execution; they are ignored by Git and must not be hand-edited to repair evidence.
- `__pycache__/`, `*.pyc`, coverage output, test results, eval results, logs, and build directories are generated and ignored. Delete them only after resolving and verifying exact in-workspace targets.
- There are no checked-in generated source files. If code generation is introduced, document the generator, inputs, deterministic command, review method, and whether outputs are tracked before adoption.

## Migration And Review Rules

- Prefer additive, backwards-compatible schema and CLI changes.
- A breaking contract change requires an explicit migration plan, compatibility tests, changelog entry, rollback approach, and architect/reviewer approval.
- Ledger formats must remain replayable or provide a versioned, tested reader; never rewrite accepted evidence in place.
- Path handling, secret-bearing inputs, subprocess use, locking, or cross-platform behavior require targeted Windows and POSIX reasoning and source-level verification.
- No database or remote-service migration exists today. Introducing one is a new architecture axis and requires a separate owner-approved sprint.

An architect review must cite the affected section, identify consumers, verify dependency direction and generated-file impact, and state whether rollback and compatibility evidence are sufficient.
