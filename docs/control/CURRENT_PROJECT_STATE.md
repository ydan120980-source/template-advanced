# CURRENT_PROJECT_STATE.md

Last Updated: 2026-08-01
State Version: v2.0
Is state stale?: no

## 1. Current Project Phase

- **Current Phase:** RELEASED
- **Phase Status:** v1.0.0 published under Apache License 2.0
- **Phase Goal:** provide a portable, verifiable, publishable starting point
  for a new Codex-governed project

This checkout is the released template. It is licensed under the Apache
License 2.0, has a public Git baseline on `main`, and runs GitHub Actions CI
for validation and release artifacts. A new project starts by following the
onboarding packet in `docs/control/NEXT_CODEX_TASK.md`.

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
- The project is licensed under the Apache License 2.0 (`LICENSE`, `NOTICE`).
- The public repository has a Git baseline with `main` as the default branch;
  CI runs on Ubuntu, Windows, and macOS for Python 3.11, 3.12, and 3.13.
- CodeGraph is an optional maintainer capability; an absent index is reported
  as `skip/info` by default, while `--strict` requires a valid project-local
  index. A present but corrupt or invalid CodeGraph database is always a
  blocking failure. CI and release validation contain no CodeGraph failure
  allowlist.

## 4. Completed Capabilities

- [x] Executable onboarding Task Packet and single planning authority.
- [x] Dependency-free Template Doctor and Run Guard CLIs with documented
  exit-code and file-format contracts.
- [x] Cross-platform setup, lint, structural-check, test, verify, and eval
  entry points that do not depend on the Unix executable bit.
- [x] Deterministic release builder, manifest, and archive verifier with
  privacy and local-state checks.
- [x] Bytecode-write guards so validation runs leave no `__pycache__`.
- [x] Apache License 2.0, NOTICE, community files, Dependabot, and GitHub
  Actions CI, release-artifacts, and security workflows.

## 5. Active Priorities

1. Keep the `main` branch green across the CI matrix.
2. Keep the release artifact digest and manifest aligned with the source tree
   on every tag.
3. Initialize CodeGraph when a maintainer tool is available and verify it with
   anchored queries (documented in `docs/architecture/CODEGRAPH.md`).
4. Add regression tests for every behavior change.

## 6. Active Risks And Mitigations

- **CodeGraph not indexed:** no CodeGraph tool was available in the release
  environment. Portable configuration and documentation are included.
  Template Doctor reports the absent optional capability as `skip/info` by
  default, while `--strict` requires a valid project-local index. CI and
  release validation contain no CodeGraph failure allowlist. A present but
  corrupt or invalid CodeGraph database is always a blocking error.
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

## 9. Current Sprint

- **Task ID:** `CODEX-CLOSEOUT-2026-08-01` (CodeGraph validation and release
  policy alignment)
- **Mode:** Lite
- **State:** validation complete; awaiting commit and User review

## 10. State Freshness

- **Last Updated:** 2026-08-01
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
