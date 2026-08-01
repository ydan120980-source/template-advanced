# Codex Advanced Agent Rules

Codex is the local execution agent for this repository. It executes bounded sprint tasks, coordinates optional review agents, runs validation, and returns auditable evidence. Keep long workflow procedures out of this file; put reusable procedures in `.agents/skills/` and reference material in `docs/ai-workflow/`.

## User / Codex Governance

Default project governance:
- The User provides stage MVP documents, process review, and final decisions.
- Codex owns project initialization, sprint planning, task packet generation, implementation, validation, Evidence Ledger output, and next-step recommendations.
- Codex should not ask the User to hand-write `docs/control/NEXT_CODEX_TASK.md`; generating and maintaining the current task packet is part of Codex's workflow responsibility.
- Codex should stop for User decision only when product tradeoffs, architecture forks, boundary changes, dependencies, secrets, CI, external services, public interfaces, validation ambiguity, or sprint budget overruns require explicit approval.

Minimum stage MVP input:
- Stage goal: what this phase should achieve.
- User-visible capability: what the MVP must let a user do.
- Non-goals: what this phase explicitly does not do.
- Acceptance criteria: how the User will judge whether the phase is acceptable.
- Constraints: technology, data, performance, security, deployment, dependency, time, or scope limits.

If missing MVP details do not affect product direction or architecture, Codex should make conservative assumptions and continue. If missing details would affect product tradeoffs or architecture decisions, Codex must stop and ask.

After each completed sprint, Codex must stop at a review point and return the Evidence Ledger plus a suggested next step. Do not automatically execute the next sprint unless the User explicitly approves continuing.

## Default Reading Order

1. `AGENTS.md`
2. `docs/control/NEXT_CODEX_TASK.md`
3. `docs/control/CURRENT_PROJECT_STATE.md`
4. `docs/control/CODEX_RUNTIME_PROFILE.md`
5. Task-specific files listed in `docs/control/NEXT_CODEX_TASK.md`

Do not read `archive/`, `examples/`, or `references/` by default. Use `docs/ai-workflow/` and `docs/architecture/` only when the task packet, a skill, or a review role requires them.

## Workflow Modes

- **Lite**: small local fixes. Read the task packet, respect paths, run focused validation, and return a compact Evidence Ledger.
- **Standard**: medium work or shared docs/contracts/adjacent behavior. Use the relevant control files, scorecard, and full Evidence Ledger.
- **Full**: large work, new axes, boundary-sensitive changes, state transitions, or reviewer-required work. Use the full control-state loop and reviewer/state-compression recommendations.

Workflow Modes are repository governance labels, not Codex CLI configuration profiles.

## Single Planning Authority

`docs/control/NEXT_CODEX_TASK.md` is the only authoritative sprint plan. The `aiwf-plan-sprint` skill creates or updates that task packet; no other plan file may change its Goal, Allowed Paths, Forbidden Paths, Budget, Validation Commands, Stop Conditions, or Required Return Format.

`planning-with-files` is an optional execution-journal mechanism, not a second control plane:

- Do not create `task_plan.md`, `findings.md`, or `progress.md` for routine Lite work.
- Use it only when the User explicitly asks for persistent planning, or when a Standard / Full task is long enough to span many tool calls or context compaction.
- Prefer an isolated `.planning/<task-id>/` directory rather than root-level planning files.
- The active `task_plan.md` must name the current Task ID and state that it mirrors `docs/control/NEXT_CODEX_TASK.md`.
- Planning journals may subdivide execution steps, record findings, and track progress, but may not expand task scope or relax a stop condition.
- If a planning journal conflicts with the task packet, the task packet wins and execution must stop until the journal is corrected.
- Planning journal contents are not acceptance evidence by themselves; material results must be copied into the final Evidence Ledger.

## Skills

- Planning: use `.agents/skills/aiwf-plan-sprint/SKILL.md` to choose the next bounded sprint and generate `docs/control/NEXT_CODEX_TASK.md`.
- Execution: use `.agents/skills/aiwf-execute-task/SKILL.md` to execute the current task packet.
- Review: use `.agents/skills/aiwf-review-ledger/SKILL.md` to review a completed Evidence Ledger.
- State compression: use `.agents/skills/aiwf-compress-state/SKILL.md` to update durable project state from accepted ledgers.

## Subagents

Subagents are optional local review roles, not autonomous scope expanders. Large tasks may use:

- `reviewer`: `.codex/agents/reviewer.toml` for scope drift, missing tests, risky diffs, architecture risk, and Evidence Ledger quality.
- `tester`: `.codex/agents/tester.toml` for lint, structural checks, unit/integration tests, build results, and validation failure interpretation.
- `architect`: `.codex/agents/architect.toml` for module boundaries, public contracts, dependency direction, generated files, and migration risk.
- `state-compressor`: `.codex/agents/state-compressor.toml` for maintaining `CURRENT_PROJECT_STATE`, `SPRINT_LEDGER`, `CHATGPT_HANDOFF`, closed axes, stable facts, and next priority.

State maintenance can use `state-compressor` after accepted Medium/Large work, closeout, or axis switch.

## GitHub Automation

GitHub automation is real and configured for the public repository:

- `ci.yml` runs the cross-platform validation matrix on `main` and pull requests.
- `release-artifacts.yml` runs the release integration script (double build,
  byte comparison, clean-extraction validation), builds and verifies release
  artifacts, and attaches them to `v*` tag releases. Release builds require a
  clean Git commit and read release files from HEAD.
- `security.yml` runs CodeQL, credential scanning, and documentation hygiene.
- `dependabot.yml` updates GitHub Actions weekly with a bounded pull-request
  limit.

Release builds must never be run from a dirty workspace: uncommitted changes
to any release file (including `.codex/config.toml`) block the build, and the
committed Codex configuration must keep safe defaults (on-request approval,
workspace-write sandbox, network off).

The prompt files under `.github/codex/prompts/` remain inert reference text and
are not connected to the workflows above.

- PR review uses `.github/codex/prompts/review.md`.
- CI failure repair uses `.github/codex/prompts/fix-ci.md`.
- Control-state gardening uses `.github/codex/prompts/garden-control-state.md`.

## Eval Harness

Use `evals/` for reusable workflow test cases. `evals/run-evals.sh` runs the
eight deterministic cases and is enforced in CI (`ci.yml` and
`release-artifacts.yml`). Do not let eval setup modify the current branch or
application code.

## Architecture Docs

Use `docs/architecture/README.md` for module boundaries, dependency direction, public contracts, generated files, and migration rules. Architect review should cite this document when judging boundary or contract risk.

## MCP Policy

MCP is an optional external capability. It is not enabled by default, and tasks must not depend on MCP unless the project owner explicitly configures and authorizes it.

## Boundaries

`docs/control/NEXT_CODEX_TASK.md` is the sprint authority. Follow its Goal, Allowed Paths, Forbidden Paths, Budget, Validation Commands, Stop Conditions, and Required Return Format.

If the task needs files outside Allowed Paths, touches Forbidden Paths, exceeds budget, or needs broader architecture decisions, stop and report escalation.

## Validation And Evidence

Run the validation commands required by the task packet. If validation cannot run, report the exact command and reason.

Every completion must output an Evidence Ledger with files changed, commands run, validation results, scope check, risks, known TODOs, state update recommendation, and recommended next step.
