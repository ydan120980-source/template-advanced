# Advanced MCP Policy

MCP is optional and not enabled by default.
Projects should copy `.codex/mcp.example.toml` to a real local config only after deciding which servers are needed and which tasks may use them.

## Default Principle

All MCP use starts read-only.
Write access must be explicitly authorized in the Task Packet, scoped to named tools and target resources, and reported in the Evidence Ledger.

## Read-Only Defaults

- GitHub: read issues, pull requests, checks, and files by default; do not merge, push, label, comment, or change settings unless authorized.
- Figma: read design context and assets by default; do not write design files or publish changes unless authorized.
- Browser: read documentation or inspect local app behavior by default; do not submit forms, change accounts, or trigger purchases unless authorized.
- Logs: read redacted logs only; do not access raw secrets, tokens, or PII.

## Forbidden Unless Explicitly Authorized

- production writes;
- deployments;
- secret access;
- changing repository, project, or organization settings;
- writing to external systems;
- accessing production data;
- sending sensitive logs or source data to third-party services.

## Task Packet Requirements

Any task that uses MCP should state:

- which MCP server is allowed;
- read-only or write scope;
- exact target resources;
- forbidden actions;
- validation and Evidence Ledger requirements.
