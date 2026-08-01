# Optional Codex Prompt References

The Markdown files in this directory are inert reference prompts. They are not
Codex CLI custom prompts, are not connected to GitHub Actions, do not run
automatically, and do not request or consume repository secrets.

- `review.md`: read-only pull-request review guidance.
- `fix-ci.md`: bounded guidance for a separately authorized CI-repair task.
- `garden-control-state.md`: bounded control-state maintenance guidance.

The repository's real automation lives in `.github/workflows/` and is separate
from these prompt references. Adopting new automation requires a separate
owner-approved design that selects an official integration, pins dependencies,
uses least-privilege permissions, defines safe triggers, handles untrusted
pull requests, scopes secrets, and has independent review and rollback
instructions. Do not copy a reference prompt into an action and treat that as
a secure workflow.

Reusable local Codex procedures belong in `.agents/skills/`. The current Task Packet remains the sole sprint authority.
