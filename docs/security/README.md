# Security Handling Guide

The public reporting policy is in the repository-root `SECURITY.md`. This guide defines how local Codex work should handle security-relevant material.

## Data And Secret Boundary

- Treat environment variables, credentials, tokens, session files, signing material, private keys, production data, and personal information as sensitive.
- Report names, paths, counts, hashes, or redacted metadata only when those facts are needed; never place values in prompts, terminal output, logs, fixtures, or Evidence Ledgers.
- Use sanitized local fixtures. Do not access production systems or send project data to an external service without explicit authorization.
- Do not modify user-level or global Codex configuration, Hooks, Skills, plugins, MCP configuration, or memory during a repository audit.

## Repository Audit Method

A release-readiness audit should be read-only and value-safe:

1. Enumerate filenames for sensitive suffixes and conventional secret locations without opening matched files.
2. Search tracked text candidates for credential *patterns* and report only file, line, pattern class, and redacted status.
3. Inventory large files, reparse points, generated caches, logs, build output, and local planning evidence.
4. Confirm `.gitignore` covers representative local artifacts, but do not claim it protects files already committed to a future Git history.
5. Run Template Doctor and the bounded security scan; triage confirmed findings before publication.

Never print matching secret values. If a real credential is suspected, stop, notify the owner privately, rotate it outside this workflow, and remove it from both the working tree and any established history.

## Tool Threat Boundaries

Template Doctor performs local read-only checks and bounded subprocess probes. AIWF Run Guard writes only its explicitly selected planning evidence and reads session JSONL metadata for command counting. Neither tool is a sandbox or an authorization layer; the Task Packet and host policy remain authoritative.

JSON and JSONL inputs are untrusted. Maintain path containment, schema validation, deterministic serialization, bounded concurrency, append-only ledger validation, and secret-safe reporting. Changes to these invariants require focused tests and independent security review.

## Incident Workflow

1. Stop the affected operation and preserve minimal redacted evidence.
2. Report through the private process in `SECURITY.md`.
3. Reproduce with sanitized fixtures in a bounded Task Packet.
4. Fix the root cause, add regression coverage, and rerun the full local verifier.
5. Review public notes for accidental disclosure before coordinated release.

Destructive cleanup, credential rotation, history rewriting, external notification, and publication require explicit owner authorization and a rollback or recovery plan.
