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
  - `budget.py`: privacy-preserving shell-request counting from explicitly supplied session JSONL files.
  - `gate.py`: ownership, artifact, retry, validation, review, liveness, and command-budget evaluation.
  - `preflight.py`: bounded read-only capability probes.
  - `reporters.py`: deterministic JSON and Markdown output.
- `scripts/` and `evals/`: dependency-free orchestration; they may invoke the Python tools and tests but contain no business logic.
- `tests/`: isolated `unittest` coverage and fixtures; production modules never import tests.
- `docs/control/NEXT_CODEX_TASK.md`: sole sprint authority. `.planning/` is local execution evidence and never a second control plane.

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
