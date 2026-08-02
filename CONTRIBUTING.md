# Contributing

Contributions should preserve the repository's bounded, evidence-first workflow
and standard-library runtime.

## Prerequisites

- Python 3.11 or newer (`py -3` is recommended on Windows; `python3` on macOS
  and Linux).
- Bash; Git Bash is supported on Windows.
- Git only when working from a real initialized clone. This source checkout may
  not yet have a Git baseline.

No third-party Python package is required for the current tools or tests.

## Prepare A Change

1. Read `AGENTS.md`, `docs/control/NEXT_CODEX_TASK.md`, and the relevant
   architecture section.
2. Keep the change inside the Task Packet's Allowed Paths and stop at any
   listed boundary.
3. Preserve deterministic output, standard-library-only imports, and documented
   exit-code/file-format contracts.
4. Add or update `unittest` coverage for behavior changes.
5. Do not commit local planning journals, generated caches, logs, secrets, test
   output, or production data.

## Validate Locally

Run every command from the repository root:

```bash
bash scripts/setup.sh
bash scripts/verify.sh
bash evals/run-evals.sh
py -3 -B -m tools.template_doctor --root . --format json
py -3 scripts/build-release.py
py -3 scripts/verify-release-archive.py --archive dist/template-advanced-1.1.0.zip --manifest dist/template-advanced-1.1.0.manifest.json
```

From Windows PowerShell, invoke Bash scripts through
`powershell -NoProfile -File scripts/invoke-git-bash.ps1 <script>` so a WSL
launcher cannot be selected accidentally.

`verify.sh` runs lint, the standard-library structural check (import and
annotation contracts, not full semantic type inference), and the unit-test
suites. Template Doctor may exit `1` solely for the explicitly deferred
missing-Git-baseline finding; a missing CodeGraph index is an optional
capability reported as a non-blocking `skip`. Invocation or operational exit
`2` is always a failure.

The `build-release.py` command requires a clean Git commit: any release file
that is untracked, deleted, or differs from its HEAD blob blocks the build
and names the offending paths. Non-Git trees require `--allow-unverified`
and are labeled unverified-source-tree builds. Do not commit a Codex
configuration that departs from the safe defaults (on-request approval,
workspace-write sandbox, network off); the `config.safe_defaults` Doctor rule
enforces the contract at release time.

The unit-test suite runs only fast, directed tests. The recursive full
release validation runs in `scripts/integration-test-release.sh`; run it
before any release build and whenever the release pipeline changes.

Before requesting review:

- confirm the unit-test suites pass through `bash scripts/test.sh`;
- confirm no placeholder validation path or bootstrap bypass remains;
- inspect changed files for credentials, private paths, large binaries, and
  generated artifacts;
- update user-facing and architecture documentation when contracts change;
- provide an Evidence Ledger with commands, results, changed files, risks, and
  known limitations.

## Review And Compatibility

Changes to CLI arguments, exit codes, JSON or JSONL shapes, rule IDs, event
kinds, lifecycle order, release manifest fields, or public documentation are
contract changes. They require explicit Task Packet authorization, regression
tests, and independent review. Prefer additive, backwards-compatible evolution;
document migrations and rollback steps before removing an existing contract.

Do not enable CI, select a license, initialize external services, or publish
changes unless the repository owner has explicitly authorized that action.

## Legal Status

This repository is licensed under the Apache License, Version 2.0. See
`LICENSE` and `NOTICE` for the full terms and attribution. By submitting a
contribution for inclusion in this project, you agree that your contribution
is provided under the same license terms (Section 5 of the Apache License
2.0).
