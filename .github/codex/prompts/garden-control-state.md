# Codex Control-State Gardening Prompt

Maintain control-state documents only.

Required process:

1. Read `AGENTS.md`.
2. Read all files in `docs/control/`.
3. Read relevant reference files in `docs/ai-workflow/`.
4. Do not modify application code.
5. Find stale state, outdated priorities, stale handoff notes, and contradictions.
6. Compress completed priorities into durable state.
7. Propose or apply updates to `docs/control/CURRENT_PROJECT_STATE.md` and `docs/control/CHATGPT_HANDOFF.md`, according to the task scope.
8. Return an Evidence Ledger.

Allowed default write paths:

- `docs/control/CURRENT_PROJECT_STATE.md`
- `docs/control/CHATGPT_HANDOFF.md`
- `docs/control/SPRINT_LEDGER.md`
- `docs/control/NEXT_CODEX_TASK.md`, only when explicitly requested

Do not touch business code, dependencies, GitHub workflow files, generated files, or unrelated docs.
