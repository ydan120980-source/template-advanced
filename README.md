# template-advanced

English | [简体中文](README.zh-CN.md)

**A deterministic, evidence-driven engineering baseline for AI coding agents and Codex workflows.**

[Highlights](#highlights) · [How It Works](#how-it-works) · [Quick Start](#quick-start) · [Validation](#full-validation) · [Core Tools](#core-tools) · [Release](#release) · [CI](#continuous-integration) · [Workflow](#repository-workflow)

**Current release:** v2.2.0 · **Python:** 3.11–3.13 · **Platforms:** Linux, macOS, Windows (Git Bash) · **License:** Apache-2.0

## Highlights

| Capability | What it gives you |
|---|---|
| Explicit task authority | A frozen `governance.task/v2` contract in the GitHub Task Issue, with a verified owner-approved local bootstrap available only before an Issue exists. |
| Evidence-first execution | Bounded execution, append-only diagnostic evidence, explicit retries, validation results, independent review, and an Evidence Ledger instead of completion-by-assertion. |
| Template Doctor | A read-only readiness audit for initialization, release hygiene, safe committed Codex defaults, Git baseline, documentation drift, release inventory, and optional CodeGraph state. |
| Exact-SHA remote gates | Governance v2 binds workflow, jobs, Check Run, repository, and the exact 40-hex commit SHA; missing, skipped, neutral, partial, or inaccessible evidence is never treated as success. |
| Deterministic release artifacts | Release files are read from committed `HEAD`, packed with deterministic metadata, independently verified, and validated again after clean extraction. |
| Cross-platform CI | GitHub Actions exercises Python 3.11, 3.12, and 3.13 across Ubuntu, Windows, and macOS, with separate candidate, release, and security workflows. |

## How It Works

`Verified Task Issue / owner-approved bootstrap → bounded execution → evidence and validation → Template Doctor → exact-SHA remote gates → deterministic release → clean-extraction verification`

The GitHub Task Issue is the normal long-lived planning authority. Before an Issue exists, an independently approved and verified `local_bootstrap` record may authorize the exact frozen contract. Validated cache files, planning journals, chat summaries, and AIWF Run Guard ledgers are evidence only: they cannot widen scope, relax stop conditions, or replace remote release evidence.

Governance v2 verifies authority and remote state, AIWF Run Guard records local execution diagnostics, Template Doctor audits repository readiness, and the release pipeline produces and independently verifies publishable artifacts. See [Task Issue Contract](docs/ai-workflow/TASK_ISSUE_CONTRACT.md), [Remote Gates](docs/ai-workflow/REMOTE_GATES.md), and [architecture](docs/architecture/README.md).

## When To Use / When Not To Use

### Use it when

- You want an auditable, evidence-first workflow for AI-agent coding sprints with explicit scope, retries, review, and acceptance.
- You want repository governance, exact-SHA CI evidence, and deterministic release artifacts to be part of the project from the start.
- You want a reusable Python baseline whose governance and release tooling depends only on the standard library.

### Do not use it when

- You need an application framework with product features, UI components, database abstractions, or web-server runtime behavior.
- Your project will not use the Task Issue / Evidence Ledger governance model and the extra control structure would remain unused.
- You need third-party Python packages as dependencies of these governance tools themselves.

## Requirements

- Python 3.11, 3.12, or 3.13.
- Bash; Git Bash is supported on Windows.
- Git for a real clone and Git baseline.
- GitHub Actions for the repository's remote CI and release gates.

The tools, tests, and release pipeline require no third-party Python package.

## Quick Start

### Verify this repository

From the repository root:

```bash
bash scripts/setup.sh
bash scripts/verify.sh
bash evals/run-evals.sh
```

`setup.sh` performs environment checks and installs nothing. `verify.sh` runs lint, the standard-library structural check, and unit tests. The eval harness runs eight deterministic workflow cases.

### Use it as a project baseline

This repository is **not currently configured as a GitHub Template Repository** (`is_template=false`), so GitHub does not provide the one-click **Use this template** flow.

Start from a clean fork or source copy under your control. Before any governed
remote write, establish the new repository identity and remote, then create the
project-specific Git baseline and governance contract. Follow
[Task Issue Contract](docs/ai-workflow/TASK_ISSUE_CONTRACT.md) and run Template
Doctor until the project-specific readiness findings are resolved. Do not treat
the original repository's planning evidence, authority, or remote identity as
authority for the new project.

## Platform Notes

Use `python3` on Linux and macOS and `py -3` on Windows Git Bash:

```bash
python3 -m unittest discover -s tests        # Linux / macOS
py -3 -m unittest discover -s tests         # Windows (Git Bash)
```

On some Windows installations, `python` resolves to the Microsoft Store / App Installer alias instead of a real interpreter. A Windows shell may report exit code 9009; Git Bash or MSYS may surface the low-byte value 49.

The Python tools do not require PowerShell script execution. If local Execution Policy blocks `.ps1` wrappers, call the modules directly; do not weaken machine/user policy or use `Bypass`:

```powershell
py -3 -B -m tools.governance_v2 --help
py -3 -B -m tools.aiwf_run_guard --help
py -3 -B -m tools.template_doctor --root . --format json
```

To launch repository Bash scripts from a Windows shell:

```powershell
py -3 -B scripts/invoke-git-bash.py scripts/verify.sh
```

The launcher selects Git for Windows Bash, rejects System32 / WindowsApps / WSL launcher paths, preserves arguments and native exit codes, and does not require `PYTHONDONTWRITEBYTECODE`; the suite and tools suppress bytecode writes themselves.

## Full Validation

Run these commands from the repository root and inspect every native exit code:

```bash
bash scripts/setup.sh
python3 -m unittest discover -s tests
bash scripts/verify.sh
bash evals/run-evals.sh
python3 -B -m tools.template_doctor --root . --format json
python3 -B scripts/ci-doctor-gate.py --root .
python3 -B -m tools.governance_v2 gate static --root .
```

On Windows Git Bash, substitute `python3` with `py -3`.

`verify.sh` checks lint, import and annotation contracts, and unit tests; its structural check is not full semantic type inference. The eval harness covers Run Guard, release determinism, Doctor drift detection, and clean-template initialization.

Template Doctor exit codes:

| Code | Meaning |
|---:|---|
| `0` | Audit completed with no readiness-blocking issue. |
| `1` | Audit completed and found one or more readiness issues. |
| `2` | Invalid invocation or operational failure. |

Exit `1` is a normal audit result and can represent **any** readiness finding. The narrower `scripts/ci-doctor-gate.py` policy allows only the deferred `git.baseline` failure; every other failed rule, report error, or operational problem blocks the gate.

CodeGraph remains optional. With no index, `codegraph.initialized` is a non-blocking `skip` by default; `--strict` promotes the absence to a blocking failure. A present but unreadable, corrupt, or unrecognized database is always blocking. The check is deliberately heuristic: it requires a readable SQLite database, `PRAGMA quick_check`, and at least one recognized candidate table such as `nodes` or `edges`; it does not prove compatibility with a complete or official CodeGraph schema. See [CodeGraph](docs/architecture/CODEGRAPH.md).

The committed Codex configuration is also part of readiness. `config.safe_defaults` requires `approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`, and network access off by default.

## Core Tools

### Governance v2

```bash
python3 -B -m tools.governance_v2 --help
python3 -B -m tools.governance_v2 gate static --root .
```

Governance v2 manages the frozen `governance.task/v2` contract, local bootstrap verification/adoption, Issue-backed event chains, static workflow checks, and exact-SHA GitHub gates. Local commands use deterministic result codes: `0` pass, `1` fail, `2` blocked, `3` cached, `4` not run. Remote Issue writes are limited to explicit commands that require `--confirm-write` plus credentials and verify the write through readback; the gate path is read-only. See [Task Issue Contract](docs/ai-workflow/TASK_ISSUE_CONTRACT.md) and [Remote Gates](docs/ai-workflow/REMOTE_GATES.md).

### AIWF Run Guard

```bash
python3 -B -m tools.aiwf_run_guard --help
python3 -B -m tools.aiwf_run_guard preflight --root . --format json
```

Run Guard is an optional local diagnostic layer for paths, failures, retry lineage, handoffs, validation, review, liveness, and command summaries. It does not start agents, replace the Task Issue, or qualify a GitHub release. The PowerShell wrapper `scripts/aiwf-run-guard.ps1` remains supported and discovers Python in the order `py -3`, `python`, `python3`, requiring Python 3.11 or newer. See [AIWF Run Guard](docs/ai-workflow/AIWF_RUN_GUARD.md).

### Template Doctor

```bash
python3 -B -m tools.template_doctor --root . --format json
python3 -B -m tools.template_doctor --root . --format markdown
```

Template Doctor is a read-only standard-library audit. Its deterministic report includes a rule ID, severity, status, evidence, and recommendation for every check. Independent rules run through a bounded thread pool with at most four workers. See [Template Doctor](docs/ai-workflow/TEMPLATE_DOCTOR.md).

## Release

### Formal build

```bash
python3 scripts/build-release.py
python3 scripts/verify-release-archive.py \
  --archive dist/template-advanced-2.2.0.zip \
  --manifest dist/template-advanced-2.2.0.manifest.json \
  --require-release-set \
  --validate
```

On Windows Git Bash, substitute `python3` with `py -3`.

The builder uses an explicit top-level allowlist and auditable exclusion rules shared with Template Doctor. It records each file's relative path, size, SHA-256, and intended POSIX mode and writes a fixed-timestamp ZIP so repeated trusted builds are byte-identical.

Inside a Git work tree, every release file is read from the Git object database at committed `HEAD`. A release file that is untracked, deleted, or different from its `HEAD` blob blocks the build and is named in the failure. Outside a Git work tree, the builder refuses by default; `--allow-unverified` must be explicit and labels the result `unverified-source-tree`. `--validate` extracts the archive into a clean directory and runs the full validation suite there.

### Source snapshot

For source delivery, use a Git snapshot:

```bash
git archive --format=zip --output=template-advanced-source.zip HEAD
```

The snapshot comes only from the committed tree, excluding `.git/`, ignored/untracked local state, caches, build output, and temporary files. Its ZIP bytes may vary across Git, zlib, or operating-system implementations; cross-platform byte determinism applies to the formal artifacts produced by `scripts/build-release.py`. Do not distribute a ZIP made by compressing the mutable working directory.

### Verify a downloaded release

Download the ZIP, manifest, publication digest, payload digest, provenance, release-set, and `SHA256SUMS` from the Draft/Published GitHub Release, then verify them:

```bash
sha256sum -c SHA256SUMS

python3 scripts/verify-release-archive.py \
  --archive template-advanced-2.2.0.zip \
  --manifest template-advanced-2.2.0.manifest.json \
  --require-release-set \
  --validate
```

On Windows Git Bash, substitute `python3` with `py -3`. The verifier checks the release set and clean extraction independently of the builder.

### Artifact set

| Artifact | Purpose |
|---|---|
| `template-advanced-2.2.0.zip` | Deterministic release archive. |
| `template-advanced-2.2.0.manifest.json` | Path, size, SHA-256, intended mode, and publication digest metadata. |
| `template-advanced-2.2.0.digest.txt` | Publication digest. |
| `template-advanced-2.2.0.payload.digest.txt` | SHA-256 of the archive bytes. |
| `template-advanced-2.2.0.provenance.json` | Source and companion-asset provenance. |
| `template-advanced-2.2.0.release-set.json` | Non-self-referential release-set digest and asset summary. |
| `SHA256SUMS` | SHA-256 values for the six release assets above. |

## Continuous Integration

| Workflow | Responsibility |
|---|---|
| `ci.yml` | Ubuntu, Windows, and macOS validation across Python 3.11, 3.12, and 3.13; setup, unit tests, verify, evals, and the Doctor CI gate. |
| `release-candidate.yml` | Read-only candidate validation on pull requests and `main` pushes: payload review, clean extraction, full local validation, and targeted workflow checks. |
| `release-artifacts.yml` | Clean-commit release integration: double build, byte comparison, full clean-extraction validation, archive/release-set verification, checksums, and Draft Release attachment on annotated `v*` tags. |
| `security.yml` | CodeQL, credential scanning, and documentation local-path hygiene. |

GitHub Actions are pinned to full commit SHAs; Dependabot keeps those pins current. macOS validation is performed by GitHub Actions, so only workflow results visible in the repository are evidence for that platform.

## Repository Workflow

1. Read `AGENTS.md` and verify the active GitHub Task Issue; before an Issue exists, verify the explicitly approved local bootstrap instead.
2. Freeze the bounded `governance.task/v2` contract: goal, allowed/forbidden paths, acceptance, base SHA, budget, and stop conditions.
3. Execute within that authority; use an isolated planning journal only for long Standard/Full work.
4. Run focused and required validation, recording native exit codes and material evidence.
5. Obtain independent review when required and return an Evidence Ledger.
6. After acceptance, compress durable results into the Task Issue event chain; local journals and diagnostic ledgers remain subordinate evidence.

## Security

Report vulnerabilities through the repository's private vulnerability reporting channel. See [SECURITY.md](SECURITY.md) for supported versions and the response process. Do not disclose unremediated vulnerabilities in public issues.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for prerequisites, contribution workflow, contract-change rules, validation requirements, and Evidence Ledger expectations.

## Current Limitations

- Trusted release builds require a clean Git commit. Dirty, untracked, deleted, or locally divergent release files are rejected; non-Git source trees require explicit `--allow-unverified` and are labeled `unverified-source-tree`.
- Unit tests are fast, directed checks. Recursive release validation lives in `scripts/integration-test-release.sh` and covers the deterministic double build, clean extraction, companion metadata, and corrupt-tree rejection.
- CodeGraph is optional and no index is committed. An absent index is a default `skip`, `--strict` makes absence blocking, and a corrupt or invalid database is always blocking. Its Doctor check is a health heuristic, not proof of complete schema compatibility.
- External global Codex configuration such as Hooks, memory, and MCP servers is outside this repository's control.
- Some GitHub security features depend on repository permissions and account type; their actual state must be read from repository settings rather than assumed.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.
