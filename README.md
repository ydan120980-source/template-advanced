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

Python is invoked by platform throughout this document. On Linux and macOS use
`python3`; on Windows Git Bash use `py -3`. On some Windows installations,
`python` may resolve to the Microsoft Store / App Installer execution alias
instead of a real Python interpreter and fail without running Python; Windows
shells may report exit code 9009, while Git Bash or MSYS environments may
surface the low-byte value 49:

```bash
python3 -m unittest discover -s tests        # Linux / macOS
py -3 -m unittest discover -s tests          # Windows (Git Bash)
```

The validation commands never depend on `PYTHONDONTWRITEBYTECODE` being preset:
the suite and the tools suppress bytecode writes themselves (`-B` and internal
guards).

## Full Validation

Run every command from the repository root and report each exit code. Substitute
`python3` on Linux and macOS, `py -3` on Windows (Git Bash):

```bash
bash scripts/setup.sh
python3 -m unittest discover -s tests        # Windows: py -3
bash scripts/verify.sh
bash evals/run-evals.sh
python3 -B -m tools.template_doctor --root . --format json    # Windows: py -3
```

`setup.sh` performs environment checks and installs nothing. `verify.sh` runs
lint, the standard-library structural check (import and annotation contracts,
not full semantic type inference), and the unit-test suites. The eval harness
runs eight deterministic cases covering Run Guard, release determinism,
Doctor drift detection, and clean-template initialization.

Template Doctor exits `1` only for a missing Git baseline (explicitly deferred
external state); the CI gate allows exactly that finding and blocks on anything
else. A missing CodeGraph index is an optional capability reported as a
non-blocking `skip`; pass `--strict` to treat it as a blocking failure. The
Doctor's CodeGraph check is a conservative heuristic — a readable SQLite
database that passes `quick_check` and contains at least one recognized
candidate table such as `nodes` or `edges` — not a complete
schema-compatibility guarantee.

The project's committed Codex configuration keeps safe defaults:
`approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`, and
network access off unless the repository owner explicitly opts in. Template
Doctor's `config.safe_defaults` rule blocks a release when the committed
configuration departs from those defaults.

## Template Doctor

```bash
python3 -B -m tools.template_doctor --root . --format json
python3 -B -m tools.template_doctor --root . --format markdown
```

On Windows Git Bash, substitute `python3` with `py -3`. The report is
deterministic and includes a rule ID, severity, status, evidence, and
recommendation for every check. Independent rules run through a bounded thread
pool with at most four workers.

Exit codes:

- `0`: ready; all blocking checks passed.
- `1`: audit completed and found readiness issues.
- `2`: invalid invocation or operational failure.

CodeGraph is an optional maintainer capability: without an index, its Doctor
rule reports a non-blocking `skip`; the CI gate passes without an allowlist
entry. Use `--strict` when an index is a hard requirement. See
[docs/architecture/CODEGRAPH.md](docs/architecture/CODEGRAPH.md).

## AIWF Run Guard

```bash
python3 -B -m tools.aiwf_run_guard --help
python3 -B -m tools.aiwf_run_guard preflight --root . --format json
```

On Windows Git Bash, substitute `python3` with `py -3`. The PowerShell wrapper
`scripts/aiwf-run-guard.ps1` discovers Python in the order `py -3`, `python`,
`python3` and requires Python 3.11 or newer.

The active GitHub Task Issue is the authoritative sprint contract; planning
journals and Run Guard evidence cannot expand its scope or relax its stop
conditions. See [AIWF Run Guard](docs/ai-workflow/AIWF_RUN_GUARD.md).

## Build A Release

```bash
python3 scripts/build-release.py
python3 scripts/verify-release-archive.py \
  --archive dist/template-advanced-2.1.0.zip \
  --manifest dist/template-advanced-2.1.0.manifest.json \
  --require-release-set
```

On Windows Git Bash, substitute `python3` with `py -3`. The builder uses an
explicit top-level allowlist and auditable exclusion rules shared with Template
Doctor, records relative path, size, SHA-256, and intended POSIX mode for every
file, and writes a fixed-timestamp ZIP so repeated builds are byte-identical.
Inside a Git work tree, the builder reads every release file from the Git
object database at HEAD and refuses to build while any release file is
untracked, deleted, or differs from HEAD — a dirty workspace can never leak
into a published archive. Outside a Git work tree the builder refuses by
default and requires `--allow-unverified`, labeling the result an
unverified-source-tree build. Add `--validate` to extract into a clean
directory and re-run the full validation suite there.

## Build A Source Archive

The source delivery is a Git snapshot, not a ZIP of the mutable workspace:

```bash
git archive --format=zip --output=template-advanced-source.zip HEAD
```

The source archive contents are derived exclusively from the committed Git
tree at `HEAD`; it therefore excludes `.git/`, untracked local state such as
`.claude/settings.local.json`, build output, caches, and temporary files. Its
ZIP byte representation may vary across Git, zlib, or operating-system
implementations. Cross-platform byte determinism is guaranteed for the custom
release artifacts produced by `scripts/build-release.py`, not for this
convenience Git source archive.

Do not distribute a ZIP created by compressing the working directory. It may
include `.git/`, ignored files, untracked files, and local tool state. Use
`git archive HEAD` for source delivery or `scripts/build-release.py` for
release artifacts.

## Verify A Downloaded Archive

1. Download the ZIP, manifest, publication digest, payload digest, provenance,
   release-set, and `SHA256SUMS` from the Draft/Published GitHub Release.
2. Verify the checksums:

   ```bash
   sha256sum -c SHA256SUMS
   ```

3. Verify the archive against the manifest:

   ```bash
   python3 scripts/verify-release-archive.py \
     --archive template-advanced-2.1.0.zip \
     --manifest template-advanced-2.1.0.manifest.json \
     --require-release-set \
     --validate
   ```

   On Windows Git Bash, substitute `python3` with `py -3`.

4. Optionally extract the ZIP and run `bash scripts/setup.sh`,
   `bash scripts/verify.sh`, `bash evals/run-evals.sh`, and Template Doctor in
   the extracted directory.

## Release Artifacts

- `template-advanced-2.1.0.zip` — the deterministic release archive.
- `template-advanced-2.1.0.manifest.json` — path, size, SHA-256, and mode for
  every file plus the publication digest.
- `template-advanced-2.1.0.digest.txt` — the publication digest.
- `template-advanced-2.1.0.payload.digest.txt` — the archive-byte SHA-256.
- `template-advanced-2.1.0.provenance.json` — source and companion-asset
  provenance.
- `template-advanced-2.1.0.release-set.json` — the non-self-referential
  release-set digest and asset summary.
- `SHA256SUMS` — SHA-256 of the six release assets above.

## Continuous Integration

The public repository runs four workflows:

- `ci.yml` — Ubuntu, Windows, and macOS runners with Python 3.11, 3.12, and
  3.13; setup, unit tests, verify, evals, and the Doctor CI gate.
- `release-candidate.yml` — read-only candidate validation (payload review,
  clean extraction, full local validation, and targeted workflow checks) on
  pull requests and `main` pushes.
- `release-artifacts.yml` — clean-commit release integration (double build,
  byte comparison, full clean-extraction validation), archive verification,
  the release-set checksums, and Draft Release attachment on annotated `v*`
  tags.
- `security.yml` — CodeQL, credential scanning, and documentation
  local-path hygiene.

Together these separate three concerns: repository governance tooling is
validated by `ci.yml`, run diagnostics (Run Guard, Template Doctor) ship with
the toolkit and are exercised by the same matrix, and release validation is
owned by `release-candidate.yml` plus `release-artifacts.yml` with `security.yml`
running alongside. GitHub Actions are pinned to full commit SHAs; Dependabot
keeps them current.

macOS validation is performed by GitHub Actions; only workflow results shown
in the repository are treated as proof for that platform.

## Repository Workflow

1. Read `AGENTS.md` and the verified GitHub Task Issue.
2. Plan a bounded sprint with the project `aiwf-plan-sprint` Skill and record
   the contract on the Task Issue.
3. Use an isolated planning journal only for long Standard or Full work.
4. Execute and validate within the Task Issue boundaries.
5. Obtain independent review when required and return an Evidence Ledger.
6. Compress only accepted results into the Task Issue event chain.

## Security

Report vulnerabilities through the repository's private vulnerability
reporting channel; see [SECURITY.md](SECURITY.md) for supported versions and
the response process. Do not disclose unremediated vulnerabilities in public
issues.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution process, contract
change rules, and local validation requirements.

## Current Limitations

- Release builds require a clean Git commit: the builder reads release files
  from the Git object database at HEAD and refuses dirty, untracked, or
  deleted release files. Non-Git trees must opt in with
  `--allow-unverified`, which labels the archive as an unverified-source-tree
  build.
- The unit-test suite runs only fast, directed tests; the full release
  validation (recursive setup/verify/evals/doctor on a clean extraction) runs
  in `scripts/integration-test-release.sh`, which release CI executes.
- CodeGraph is an optional maintainer capability; no index is committed and
  no tool was available to verify real indexing in this environment. Without
  an index, Template Doctor reports `skip/info` by default and `fail/error`
  under `--strict`; a present but corrupt or invalid database is always a
  blocking failure. The Doctor's check is a heuristic and does not prove
  compatibility with a complete or official CodeGraph schema.
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
