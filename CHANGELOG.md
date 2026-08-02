# Changelog

All notable changes are recorded here. The project follows a
`YYYY-MM-DD` release cadence with semantic versioning once a Git baseline and
release tags exist.

## [Unreleased]

## [1.1.0] - 2026-08-02

### Added

- Trusted Git-commit release sources, manifest source metadata, and explicit
  `--allow-unverified` labeling for builds outside a Git work tree.
- Safe project-level Codex configuration validation: on-request approval,
  workspace-write sandbox, network access off, and rejection of absolute paths
  or credential patterns.
- Full release integration validation with double-build comparison, clean
  extraction, corrupted-CodeGraph rejection, and clean-HEAD rebuild checks.
- Bounded process-tree execution and a Windows PowerShell Git-Bash resolver
  that ignores WSL/System32 launchers and forwards output and exit codes.
- CodeGraph heuristic health checks with honest optional/default/strict state
  semantics. No real indexing is claimed for this release.

### Changed

- Formal release builds require a clean Git source and read release files from
  the committed `HEAD`; a non-Git build must opt in to `--allow-unverified`.
- Release artifacts remain the cross-platform byte-deterministic delivery;
  `git archive HEAD` is the traceable source archive but does not promise
  identical ZIP bytes across Git, zlib, and operating systems.
- The release pipeline now derives artifact names and package versions from one
  project version source.
- Doctor and Run Guard documentation now states that exact pass/skip counts
  depend on optional host capabilities and existing manifests; release gates
  use blocking-failure semantics instead.

### Verification and publication

- Protected main-branch and pull-request checks run on Ubuntu, Windows, and
  macOS with Python 3.11, 3.12, and 3.13, together with CodeQL and credential
  scanning.
- The tag-triggered release workflow does not rerun that full cross-platform
  matrix. It reruns the configured release-critical chain on Ubuntu with
  Python 3.13: unit tests, Verify, Eval, Release integration, deterministic
  artifact construction, archive verification, and workflow-artifact checksum
  validation before GitHub Release upload.
- Exact Doctor, Run Guard preflight, and platform-specific pass/skip totals
  depend on the host capabilities and operating system; they are release
  evidence, not fixed repository invariants.

### Fixed

- POSIX launches no longer pass the Windows-only `creationflags` argument;
  Windows process groups retain their platform-specific behavior.
- Timeout cleanup now terminates and reaps process trees while closing parent
  stdin/stdout/stderr pipes without dropping captured output or emitting
  `ResourceWarning` noise.
- Cross-platform path-case semantics, release file modes, line endings,
  manifest determinism, and clean-source archive hygiene are now enforced.
- `.git/`, `.claude/settings.local.json`, caches, temporary state, and dirty
  working-tree bytes cannot enter a trusted release artifact.

### Security

- GitHub Actions remain pinned to full commit SHAs.
- Release build-and-verify uses contents read; only the publish job receives
  contents write. CodeQL alone receives security-events write, while the
  credential scan remains contents read.
- CI and archive validation reject unexpected Doctor failures; CodeGraph has no
  failure allowlist.
- Corrupt or invalid project-local CodeGraph databases remain blocking errors,
  while a missing optional index is non-blocking only in default Doctor mode.

## [1.0.0] - 2026-08-01

### Added

- Apache License 2.0 (`LICENSE`) and attribution notice (`NOTICE`).
- Public Git baseline with `main` as the default branch and annotated
  `v1.0.0` tag.
- GitHub Actions CI for Ubuntu, Windows, and macOS across Python 3.11, 3.12,
  and 3.13.
- Deterministic release-artifacts workflow: double build, byte comparison,
  full archive verification, `SHA256SUMS`, and Release attachment.
- Security workflow with CodeQL, credential scanning, and documentation
  local-path hygiene; Dependabot for GitHub Actions.
- Issue templates and a pull request template.
- Standard-library Template Doctor with bounded concurrent checks,
  deterministic JSON/Markdown reports, and distinct ready/finding/error exits.
- AIWF Run Guard with append-only JSONL evidence, retry lineage, ownership and
  artifact budgets, validation/review lifecycle gates, and cross-session
  command snapshots.
- Deterministic release builder, manifest, and independent archive verifier
  with path, digest, mode, and privacy checks.
- Platform-aware Run Guard artifact identity: case-insensitive on Windows and
  case-sensitive on POSIX.
- Template Doctor drift-detection rules for author-local state, numeric status
  claims, sprint consistency, and stale release manifests.
- Bytecode-write guards so unit tests, Doctor, and release tools run without
  setting `PYTHONDONTWRITEBYTECODE` or leaving `__pycache__` behind.

### Changed

- Replaced template-only control and validation guidance with executable
  local workflow documentation.
- Renamed the standard-library annotation/import contract check to
  `scripts/structural-check.sh` so its name matches its actual capability.
- Made all documented validation commands invoke Bash by name, so no Unix
  executable bit is required on Windows, macOS, or Linux.
- Replaced author-specific control history with a clean, portable onboarding
  state.

### Removed

- Non-operational GitHub Actions placeholders that requested permissions and
  implied unavailable automation.
- Author runtime state files from the template working tree.

### Known Limitations

- CodeGraph is an optional maintainer capability; real indexing was not
  verified in the release environment.
- External global Codex configuration is outside project control.
- Some GitHub security features depend on repository permissions and account
  type.

[Unreleased]: https://github.com/ydan120980-source/template-advanced/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/ydan120980-source/template-advanced/compare/v1.0.0...v1.1.0
