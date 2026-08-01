# template-advanced

`template-advanced` is a dependency-free Python toolkit and
repository-governance template for auditable Codex sprints. It combines an
executable Task Packet workflow with two local tools and a reproducible
release pipeline:

- **Template Doctor** audits whether a copied project has completed
  initialization and release-hygiene work.
- **AIWF Run Guard** records append-only execution evidence and gates
  validation, ownership, retry, artifact, review, and cross-session command
  budgets.
- **Release pipeline** builds a deterministic archive plus manifest and
  independently verifies the archive, its modes, and a clean extraction.

## When To Use It

- You want an auditable, evidence-first workflow for AI-agent coding sprints
  with strict scope, retry, and review accounting.
- You want a publishable starting point whose release artifacts are
  reproducible byte-for-byte.
- You want Template Doctor to catch initialization and release-hygiene drift
  in copied projects.

## When Not To Use It

- As an application framework: it provides governance tooling, not product
  features.
- When the workflow itself is not a fit: projects that do not use Codex task
  packets or evidence ledgers will carry unused structure.
- When you need third-party Python dependencies at runtime: the tools are
  standard-library only by design.

## Requirements

- Python 3.11, 3.12, or 3.13 (the supported matrix is exercised by CI).
- Bash; Git Bash is supported on Windows.
- Git for a real clone and baseline; GitHub Actions is enabled on the public
  repository.

No third-party Python package is required for the tools, tests, or release
pipeline.

## Five-Minute Quick Start

From the repository root:

```bash
bash scripts/setup.sh
bash scripts/verify.sh
bash evals/run-evals.sh
```

On Windows, run the same commands from Git Bash, or invoke the Git Bash
executable directly; the documented commands call `bash` by name so no Unix
executable bit is required. On Linux and macOS the identical commands work
natively.

The validation commands never depend on `PYTHONDONTWRITEBYTECODE` being preset:
the suite and the tools suppress bytecode writes themselves (`-B` and internal
guards).

## Full Validation

Run every command from the repository root and report each exit code:

```bash
bash scripts/setup.sh
python -m unittest discover -s tests
bash scripts/verify.sh
bash evals/run-evals.sh
python -B -m tools.template_doctor --root . --format json
```

`setup.sh` performs environment checks and installs nothing. `verify.sh` runs
lint, the standard-library structural check (import and annotation contracts,
not full semantic type inference), and the unit-test suites. The eval harness
runs eight deterministic cases covering Run Guard, release determinism,
Doctor drift detection, and clean-template initialization.

Template Doctor exits `1` only for explicitly deferred external state (a
missing Git baseline or CodeGraph index); the CI gate allows exactly those two
findings and blocks on anything else.

## Template Doctor

```bash
python -B -m tools.template_doctor --root . --format json
python -B -m tools.template_doctor --root . --format markdown
```

The report is deterministic and includes a rule ID, severity, status, evidence,
and recommendation for every check. Independent rules run through a bounded
thread pool with at most four workers.

Exit codes:

- `0`: ready; all blocking checks passed.
- `1`: audit completed and found readiness issues.
- `2`: invalid invocation or operational failure.

CodeGraph is an optional maintainer capability: without an index, its Doctor
rule reports a non-blocking finding that the CI gate explicitly allows. See
[docs/architecture/CODEGRAPH.md](docs/architecture/CODEGRAPH.md).

## AIWF Run Guard

```bash
python -B -m tools.aiwf_run_guard --help
python -B -m tools.aiwf_run_guard preflight --root . --format json
```

The PowerShell wrapper `scripts/aiwf-run-guard.ps1` discovers Python in the
order `py -3`, `python`, `python3` and requires Python 3.11 or newer.

The authoritative sprint plan remains `docs/control/NEXT_CODEX_TASK.md`;
planning journals and Run Guard evidence cannot expand its scope or relax its
stop conditions. See [AIWF Run Guard](docs/ai-workflow/AIWF_RUN_GUARD.md).

## Build A Release

```bash
python scripts/build-release.py
python scripts/verify-release-archive.py \
  --archive dist/template-advanced-1.0.0.zip \
  --manifest dist/template-advanced-1.0.0.manifest.json
```

The builder uses an explicit top-level allowlist and auditable exclusion rules
shared with Template Doctor, records relative path, size, SHA-256, and intended
POSIX mode for every file, and writes a fixed-timestamp ZIP so repeated builds
are byte-identical. Add `--validate` to extract into a clean directory and
re-run the full validation suite there.

## Verify A Downloaded Archive

1. Download the ZIP, manifest, digest, and `SHA256SUMS` from the GitHub
   Release.
2. Verify the checksums:

   ```bash
   sha256sum -c SHA256SUMS
   ```

3. Verify the archive against the manifest:

   ```bash
   python scripts/verify-release-archive.py \
     --archive template-advanced-1.0.0.zip \
     --manifest template-advanced-1.0.0.manifest.json \
     --validate
   ```

4. Optionally extract the ZIP and run `bash scripts/setup.sh`,
   `bash scripts/verify.sh`, `bash evals/run-evals.sh`, and Template Doctor in
   the extracted directory.

## Release Artifacts

- `template-advanced-1.0.0.zip` — the deterministic release archive.
- `template-advanced-1.0.0.manifest.json` — path, size, SHA-256, and mode for
  every file plus the publication digest.
- `template-advanced-1.0.0.digest.txt` — the publication digest.
- `SHA256SUMS` — SHA-256 of the three files above.

## Continuous Integration

The public repository runs three workflows:

- `ci.yml` — Ubuntu, Windows, and macOS runners with Python 3.11, 3.12, and
  3.13; setup, unit tests, verify, evals, and the Doctor CI gate.
- `release-artifacts.yml` — deterministic double build, archive verification,
  `SHA256SUMS`, and Release attachment on `v*` tags.
- `security.yml` — CodeQL, credential scanning, and documentation
  local-path hygiene.

macOS validation is performed by GitHub Actions; only workflow results shown
in the repository are treated as proof for that platform.

## Repository Workflow

1. Read `AGENTS.md` and the current Task Packet.
2. Plan a bounded sprint with the project `aiwf-plan-sprint` Skill.
3. Use an isolated planning journal only for long Standard or Full work.
4. Execute and validate within the Task Packet boundaries.
5. Obtain independent review when required and return an Evidence Ledger.
6. Compress only accepted results into durable control state.

## Security

Report vulnerabilities through the repository's private vulnerability
reporting channel; see [SECURITY.md](SECURITY.md) for supported versions and
the response process. Do not disclose unremediated vulnerabilities in public
issues.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution process, contract
change rules, and local validation requirements.

## Current Limitations

- CodeGraph is an optional maintainer capability; no index is committed and
  no tool was available to verify real indexing in this environment.
- External global Codex configuration (Hooks, memory, MCP servers) is outside
  this repository's control.
- Some GitHub security features depend on repository permissions and account
  type; their actual state is reported by the repository settings, not
  assumed.

## License

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this project except in compliance with the License. You may obtain a copy of
the License at:

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See
[LICENSE](LICENSE) and [NOTICE](NOTICE) for details.
