# CODEX_RUNTIME_PROFILE.md

This file defines the default runtime, permission, validation, and review rules for Codex execution in this repo.

---

## 1. Default Execution Mode

Default profile:
- workspace-write
- network off unless explicitly approved
- approval required for dependency changes, external writes, secrets, destructive operations, and broad generated changes

Workflow Mode:
- **Lite**: for small, local fixes. Read `AGENTS.md` and the task packet, make the bounded change, run focused validation, and return a compact Evidence Ledger. Do not update control-state files unless explicitly asked.
- **Standard**: for medium tasks or small tasks with shared docs/contracts/adjacent behavior. Read the relevant control-state files and return the normal completion report.
- **Full**: for large tasks, new axes, boundary-sensitive work, reviewer-required work, or state transitions. Use the full control-state loop and include state-update recommendations.

Lite tasks must stop and report if they need broader context, extra files, higher-risk validation, dependency changes, or a larger diff than declared.

Default context rule:
- Codex must treat `docs/control/NEXT_CODEX_TASK.md` as the authority for required reading. Do not load additional workflow files unless the task packet explicitly authorizes them.

Planning authority:
- Lite / Standard / Full are governance modes interpreted from the task packet; they are not `.codex/config.toml` profiles.
- `docs/control/NEXT_CODEX_TASK.md` is the single sprint authority.
- `planning-with-files` may persist execution progress for a long Standard / Full task, but its files are subordinate journals and cannot change task boundaries.

Safer probe mode:
- read-only
- use for ambiguous tasks, repo reconnaissance, or boundary checks

Avoid:
- full access mode unless the user explicitly permits it for a narrow reason

### Runtime Configuration Precedence

Effective permissions are determined by the active Codex host and task, not by this document alone. Interpret runtime settings in this order:

1. Current task / host permission profile and system policy
2. Explicit CLI overrides
3. Project `.codex/config.toml`
4. User-level Codex configuration
5. This document as repository governance

The project config intentionally defines one conservative default (`workspace-write`, `on-request`). Read-only review is enforced by the review agent configuration or the active task permission profile, not by unsupported `[profiles.*]` keys.

After changing `.codex/config.toml`, run `codex doctor` and treat any unsupported project-local key warning as configuration drift that must be removed or documented before relying on it.

### Committed Configuration Contract

The committed `.codex/config.toml` is a release-facing contract, enforced by
the Template Doctor rule `config.safe_defaults`:

- `approval_policy` must be `"on-request"`; `"never"` is never a template
  default.
- `sandbox_mode` must be `"workspace-write"`.
- `sandbox_workspace_write.network_access` must not be `true`; network is off
  unless the repository owner explicitly opts in for a session.
- The file must not contain absolute local paths or credential patterns, and
  evidence for this rule is relative-path only.

Release builds read `.codex/config.toml` (and every other release file) from
the Git object database at HEAD; an uncommitted `approval_policy = "never"`
edit therefore blocks the build instead of silently entering the archive.

---

## 2. Network Policy

Network access is disabled by default.

Network may be requested only when:
- dependency installation is required and explicitly allowed;
- documentation lookup is necessary for a current dependency/API;
- the task explicitly says online access is permitted.

Network must not be used for:
- unrelated research;
- downloading unreviewed scripts;
- sending project data externally;
- changing package versions without permission.

---

## 3. Dependency Policy

Codex must not change dependency files unless listed in Allowed Paths.

Protected files include, unless explicitly allowed:
- `package.json`
- lockfiles
- `pyproject.toml`
- `requirements*.txt`
- `Cargo.toml`
- CI setup files
- Dockerfiles

If dependency change seems necessary:
- stop;
- explain why;
- propose a separate bounded task.

---

## 4. Validation Order

Default validation order:

1. Static inspection / targeted search
2. Focused tests for touched code
3. Script/doctor/readiness command, if relevant
4. Adjacent tests
5. Build/structural-check/lint, if affected
6. Full test suite only if proportional to the change

Codex must report every command attempted and its result.

---

## 5. Review Rules

Small task:
- reviewer usually not required

Medium task:
- reviewer required if touching boundaries, contracts, migration logic, or multiple critical modules

Large task:
- reviewer required
- reviewer must be independent from implementation prompt
- reviewer checks scope drift, missing tests, broken interfaces, hidden behavior changes, docs/implementation mismatch

Helper-generated patch:
- must be integrated and validated by Codex
- cannot be accepted directly as final work

---

## 6. State File Policy

Codex may append:
- `docs/control/SPRINT_LEDGER.md`

Codex may update only if explicitly asked:
- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/CHATGPT_HANDOFF.md`
- `docs/control/NEXT_CODEX_TASK.md`

Context fill / project initialization exception:
- If control files are still in template state, Codex may update `docs/control/CURRENT_PROJECT_STATE.md` and `docs/control/NEXT_CODEX_TASK.md` to compress the User's MVP into executable control state and the first bounded task packet.
- During initialization, Codex must propose rather than directly edit `docs/control/SPRINT_LEDGER.md`, `docs/control/CHATGPT_HANDOFF.md`, `scripts/*`, `.github/*`, dependencies, CI, external-service configuration, public interfaces, or architecture-boundary files unless the User explicitly approves those writes.

State update cadence:
- `docs/control/NEXT_CODEX_TASK.md` may be updated when the current User request, initialization flow, or approved planning workflow calls for planning the next sprint.
- `docs/control/CURRENT_PROJECT_STATE.md` should be updated during initialization, MVP phase completion, important state transitions, or state compression after several accepted sprints.
- `docs/control/SPRINT_LEDGER.md` should remain append-oriented; propose ledger updates first unless the task packet explicitly allows appending.
- `docs/control/CHATGPT_HANDOFF.md` should be updated for phase switches, long handoffs, or stale-state cleanup only when explicitly approved.

Recommended pattern:
- Codex writes the Evidence Ledger.
- Web GPT decides whether to compress it into current state.
- For Medium / Large tasks, Codex may propose a state update in its final report.

---

## 7. Stop Conditions

Stop and report if:

- task requires files outside Allowed Paths;
- repo state contradicts the current task packet;
- validation setup cannot run;
- protected files need changes;
- frozen contracts would need edits;
- broad architecture redesign becomes necessary;
- helper output conflicts with Codex judgment;
- secret or credential access is required;
- the diff exceeds the declared task size.

---

## 8. Required Completion Report

Each Codex run must include:

- files changed;
- behavior changed;
- tests/docs changed;
- commands run;
- exact results;
- skipped validation and reason;
- risks;
- follow-up candidates;
- whether state files should be updated;
- whether reviewer is needed.
