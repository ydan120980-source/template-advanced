# Changelog

All notable changes are recorded here. The project follows a
`YYYY-MM-DD` release cadence with semantic versioning once a Git baseline and
release tags exist.

## Unreleased

### Changed

- CodeGraph detection now has three explicit states: absent index reports
  `skip/info` by default and `fail/error` under `--strict`; a present but
  corrupt or invalid database always reports `fail/error`; a valid database
  reports `pass` with relative-path evidence.
- CI and release-archive validation share one allowlist
  (`RELEASE_EXTRACTION_ALLOWED_FAILURES`, only `git.baseline`); CodeGraph has
  no failure allowlist anywhere.
- Archive `--validate` reports stage, command, timeout, and output summaries
  on timeout, and always removes its temporary extraction directory.
- GitHub Actions pinned to full commit SHAs with version comments.

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
