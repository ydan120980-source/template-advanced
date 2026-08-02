# CURRENT_PROJECT_STATE.md

Last Updated: 2026-08-02
State Version: v2.0
Is state stale?: no

## 1. Current Project Phase

- **Current Phase:** RELEASE-CANDIDATE
- **Phase Status:** v1.0.0 remains published; v1.1.0 implementation and local
  validation are complete, with remote publication pending
- **Phase Goal:** provide a portable, verifiable, publishable starting point
  for a new Codex-governed project

This checkout is the release candidate for the next template version. It is
licensed under the Apache License 2.0, has a public Git baseline on `main`,
and runs GitHub Actions CI for validation and release artifacts. The historical
`v1.0.0` tag and Release remain unchanged while this sprint prepares `v1.1.0`.

## 2. Control Hierarchy

When documents conflict, use this order:

1. the User's latest explicit instruction;
2. repository constitution and `AGENTS.md`;
3. `docs/control/NEXT_CODEX_TASK.md` as the sole sprint authority;
4. `docs/control/CODEX_RUNTIME_PROFILE.md`;
5. this current state;
6. `docs/control/SPRINT_LEDGER.md` as history.

Planning journals are subordinate execution evidence and cannot change Task
Packet scope, budgets, validation, or stop conditions.

## 3. Canonical Facts

- Template Doctor is a Python-standard-library CLI with deterministic
  JSON/Markdown reports, bounded concurrent rules, and exit code 0 for ready,
  1 when readiness findings exist, and 2 for invocation or operational error.
- AIWF Run Guard is a Python-standard-library evidence gate for ownership,
  retry lineage, validation/review ordering, artifact budgets, and cross-session
  shell budgets.
- The release pipeline is a deterministic builder and an independent archive
  verifier under `scripts/`, backed by one shared release inventory in
  `tools/template_doctor/`.
- Release builds read every release file from the Git object database at
  HEAD; a release file that is untracked, deleted, or differs from HEAD
  blocks the build, so dirty workspaces never enter published archives.
  Non-Git trees must opt in with `--allow-unverified` and the result is
  labeled an unverified-source-tree build.
- The committed `.codex/config.toml` keeps safe defaults
  (`approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`,
  network access off); `approval_policy = "never"` is not a default.
- The unit-test suite runs only fast, directed tests; the recursive full
  release validation (setup/verify/evals/doctor on a clean extraction) runs
  in `scripts/integration-test-release.sh`, which release CI executes. All
  validation subprocesses run under bounded timeouts with whole-process-tree
  termination, and the shared process helper explicitly closes its parent-side
  pipes on every exit path.
- The project is licensed under the Apache License 2.0 (`LICENSE`, `NOTICE`).
- The public repository has a Git baseline with `main` as the default branch;
  CI runs on Ubuntu, Windows, and macOS for Python 3.11, 3.12, and 3.13.
- CodeGraph is an optional maintainer capability; an absent index is reported
  as `skip/info` by default, while `--strict` requires a project-local index.
  The Doctor's check is a conservative heuristic: a database must be readable
  by SQLite, pass `PRAGMA quick_check`, and contain at least one currently
  recognized candidate table (such as `nodes` or `edges`); it does not prove
  compatibility with a complete or official CodeGraph schema. A present but
  corrupt or invalid CodeGraph database is always a blocking failure. CI and
  release validation contain no CodeGraph failure allowlist.

## 4. Completed Capabilities

- [x] Executable onboarding Task Packet and single planning authority.
- [x] Dependency-free Template Doctor and Run Guard CLIs with documented
  exit-code and file-format contracts.
- [x] Cross-platform setup, lint, structural-check, test, verify, and eval
  entry points that do not depend on the Unix executable bit.
- [x] Deterministic release builder, manifest, and archive verifier with
  privacy and local-state checks.
- [x] Clean-source release gate: builds read release files from HEAD and
  refuse dirty, untracked, or deleted release files; non-Git trees must opt
  in with an unverified-source-tree label.
- [x] Safe committed Codex defaults enforced by the `config.safe_defaults`
  Doctor rule (on-request approval, workspace-write sandbox, network off).
- [x] Heavy release validation split: the unit suite runs fast directed tests
  only; the recursive full validation lives in
  `scripts/integration-test-release.sh`, and every validation subprocess runs
  with bounded timeouts and whole-process-tree termination. The integration
  runner uses named stage bounds, bounded output tails, and the shared helper.
- [x] Bytecode-write guards so validation runs leave no `__pycache__`.
- [x] Apache License 2.0, NOTICE, community files, Dependabot, and GitHub
  Actions CI, release-artifacts, and security workflows.

## 5. Active Priorities

1. Keep the `main` branch green across the CI matrix.
2. Keep the release artifact digest and manifest aligned with the source tree
   on every tag.
3. Keep POSIX and Windows process-tree validation bounded and leak-free.
4. Initialize CodeGraph when a maintainer tool is available and verify it with
   anchored queries (documented in `docs/architecture/CODEGRAPH.md`).
5. Add regression tests for every behavior change.

## 6. Active Risks And Mitigations

- **CodeGraph not indexed:** no CodeGraph tool was available in the release
  environment. Portable configuration and documentation are included.
  Template Doctor reports the absent optional capability as `skip/info` by
  default, while `--strict` requires a project-local index. The Doctor's
  check is a conservative heuristic (readable SQLite, passing `quick_check`,
  at least one recognized candidate table such as `nodes` or `edges`); it
  does not prove compatibility with a complete or official CodeGraph schema.
  CI and release validation contain no CodeGraph failure allowlist. A present
  but corrupt or invalid CodeGraph database is always a blocking error.
- **External global Codex configuration:** Hooks, memory, and MCP servers are
  outside repository control. Mitigation: capability probes report metadata
  only.
- **GitHub feature availability:** branch protection and security settings
  depend on account type and permissions. Mitigation: real API results are
  reported, not assumed.
- **Executable-bit portability:** ZIP archives do not preserve POSIX modes on
  every extractor. Mitigation: docs use `bash scripts/...`, and the verifier
  records and checks the intended mode for every shell script.

## 7. Default Validation Profile

Use fail-fast execution and `PYTHONDONTWRITEBYTECODE=1` (the tools and tests
also guard bytecode writes themselves):

1. `bash scripts/setup.sh`
2. `python -m unittest discover -s tests`
3. `bash scripts/verify.sh` (lint, structural check, unit tests)
4. `bash evals/run-evals.sh`
5. `python -B -m tools.template_doctor --root . --format json`
6. `python -B scripts/ci-doctor-gate.py --root .`
7. `python scripts/build-release.py` and the archive verifier

## 8. Recent Sprint Summary

See `docs/control/SPRINT_LEDGER.md`. The v1.0.0 release prep established the
license, Git baseline, CI, security workflow, and release artifacts. The
CodeGraph alignment sprint fixed corrupt-database detection (three-state
semantics), unified the CI and release allowlist behind one shared policy
constant (`RELEASE_EXTRACTION_ALLOWED_FAILURES`), and added per-stage
validation timeouts plus temporary-extract cleanup to the archive verifier.
A follow-up sprint named the check a conservative heuristic: databases with
`nodes`-only, `edges`-only, or combined candidate tables pass when
`quick_check` succeeds, while databases with no recognized candidate table
remain blocking, and no complete-schema guarantee is claimed.

The final release-hygiene closeout explicitly closes the Run Guard process
pipes after normal, nonzero, timeout, and cleanup paths while preserving
captured output. `scripts/integration-test-release.sh` now uses the shared
process-tree helper for every external stage, with explicit build, archive,
full-validation, corrupted-CodeGraph, and clean-HEAD rebuild stages. The Git
source archive remains a HEAD-content delivery mechanism; its ZIP byte form
may vary across Git, zlib, and operating systems, while custom release
artifacts retain their cross-platform byte-determinism contract.

## 9. Current Sprint

- **Task ID:** `RELEASE-V1.1.0`
- **Mode:** Full
- **State:** implementation review and local validation passed; publication is
  gated on remote CI, security, tag, and download verification
- **Scope:** seal the v1.1.0 version and changelog, remove drift-prone status
  counts, provide a tested Windows Git-Bash entry point, build deterministic
  artifacts, publish only after required CI succeeds, and independently verify
  downloaded assets. CodeGraph remains optional and unindexed.

## 10. State Freshness

- **Last Updated:** 2026-08-02
- **Based On Commit:** manual record — refresh after each accepted sprint
- **Current Git HEAD:** manual record — refresh after each accepted sprint
- **Is state stale?**: no
- **Freshness basis:** the commit fields are a manual record because a
  committed file cannot self-reference the commit that contains it; Template
  Doctor validates the date, stale flag, placeholders, and sprint consistency
  instead of pretending to verify commit identity.

## 11. Stop Conditions

Stop and escalate on an unapproved boundary decision, forbidden-path edit,
dependency or secret requirement, external write, budget overrun, failed
validation, or inability to distinguish current facts from stale history.
