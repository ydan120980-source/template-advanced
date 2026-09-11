# Changelog

All notable changes are recorded here. The project follows a
`YYYY-MM-DD` release cadence with semantic versioning once a Git baseline and
release tags exist.

## Unreleased

### Added

- `tools/workflow_eval/`: a standard-library evaluation module with
  `prepare`, `grade`, and `report` entries, definitions for three historical
  repair tasks, and unit tests. It enables repeatable workflow comparison
  experiments from locked historical source snapshots; real-model trial runs
  are never part of per-commit CI.
- `tools/workflow_eval/audit.py`: all-channel audit of a trial sub-agent's
  session record. Counting only shell calls cannot establish independence —
  a trial can read the source repository with a read or search tool — so the
  audit reports out-of-trial targets, source-repository contact, calls that
  named no absolute path, and unanchored Git commands as facts.
- `docs/ai-workflow/WORKFLOW_EVAL_TRIALS.md`: how trials are run and what
  their evidence proves, including the three states of trial validity and the
  narrow scope of `trial_isolated`.

### Changed

- Workflow eval trial validity is now a coordinator attestation rather than
  an inference from a grade record. `trial_validity` carries
  VALID/INVALID/UNVERIFIED plus the audit basis and defaults to UNVERIFIED,
  so a run with no audit — or a record that predates the requirement — never
  fills a valid comparison slot; a VALID or INVALID claim must cite the audit
  record behind it. `trial_isolated` keeps its field name but is documented
  and recorded as one narrow check, the pre-scoring Git root probe.
  `report` now answers record structure, trial protocol validity, and
  functional outcome separately, so a full set of well-formed result files is
  no longer presented as a finished comparison.
- Run Guard command budgets now recognize the current host event forms:
  `custom_tool_call` inputs invoking `tools.exec_command(...)` in addition to
  the historical `tools.shell_command(...)`, plus named `function_call`
  direct shell requests — wrapped in `response_item` or top-level — with
  ISO-8601 or Unix-epoch-millisecond timestamps. The metric semantics are
  unchanged: one outer shell-bearing tool request counts exactly once,
  batched calls in the same request do not split the count, and strings,
  comments, plain messages, and pure-wait operations never count.
  Indirect shell references and corrupted events raise explicit errors
  instead of producing complete-looking zero counts.
- Session JSONL parsing now splits strictly on newline record delimiters, so
  legal U+2028/U+2029/U+0085 characters inside string literals no longer
  corrupt otherwise-valid session evidence.
- Documentation: the architecture README states the GitHub Task Issue
  authority and documents the `governance_v2` and `workflow_eval` module
  boundaries; the README lists the four actual GitHub workflows and
  separates governance tooling, run diagnostics, and release validation;
  onboarding guidance no longer instructs the use of retired control files
  or old planning roles.
- Template Doctor's `planning.single_authority` rule now detects current
  documents re-claiming a retired control file as the sole or active
  planning authority, and the `release.documents` rule requires the
  onboarding README to enumerate every existing GitHub workflow.

### Fixed

- The release-determinism eval covers publication digest selection
  deterministically — missing, duplicate, and mismatched digest files plus a
  payload-digest decoy — with a hardened regression guard (#24).
- Cross-platform CI path spellings no longer break the workflow eval harness
  (#25): Git-isolation probes and the acceptor toplevel check compare
  `realpath`-normalised physical paths on both sides, so a symlinked temp
  root (macOS `/var` -> `/private/var`) or an 8.3 short component (Windows
  `RUNNER~1` -> `runneradmin`) no longer rejects a perfectly isolated trial;
  and the session audit classifies the explicitly declared source repository
  before generic scratch roots, so a source repository placed under Linux
  `/tmp` is reported as source-repository contact instead of neutral
  scratch.

## [2.0.0] - 2026-08-04

### Changed

- Final v2 release tooling now reads the authoritative `2.0.0` value from
  `tools/project_version.py` across Run Guard, Template Doctor, the release
  inventory, builder, verifier, workflows, tests, and release documentation.
- Release candidates now produce and independently verify the deterministic
  archive, manifest, publication digest, payload digest, provenance,
  non-self-referential release-set, and `SHA256SUMS` assets.
- Release workflows verify before any publication action, keep the candidate
  workflow read-only, require annotated version tags for publication, and
  refuse to clobber a non-draft Release.
- Process-tree runs now explicitly close stdin, stdout, and stderr on every
  normal, nonzero, timeout, and cleanup path while preserving captured output.
  ResourceWarning regression coverage includes repeated short timeouts and
  mocked pipe-state assertions.
- `scripts/integration-test-release.sh` now routes every release stage through
  the shared bounded process-tree helper. Named stages use practical timeouts,
  retain the bytecode and recursion guards, and report the command, timeout,
  exit code, and bounded stdout/stderr tails on failure.
- Release integration now performs explicit basic archive validation, complete
  clean-extraction validation, corrupted-CodeGraph rejection, and a clean-HEAD
  rebuild comparison.
- The Git source archive is documented as a committed-HEAD content snapshot,
  not a cross-platform byte-deterministic ZIP. Formal release artifacts from
  `scripts/build-release.py` retain the cross-platform byte-determinism
  guarantee. Workspace-compressed ZIP files are not supported for delivery.
- Restored platform-specific process creation arguments: POSIX runs use only
  `start_new_session=True`, while Windows retains its process-group creation
  flag. Timeout tests now assert the actual command, and process-tree cleanup
  continues to terminate and reap descendants.
- Excluded `.claude/settings.local.json` from source delivery and documented
  `git archive HEAD` as the committed-source archive entry point. Release
  archives remain generated by `scripts/build-release.py` from the trusted
  inventory.
- Closed stdin, stdout, and stderr for the Git blob batch reader on normal and
  exceptional paths, preventing unclosed-pipe `ResourceWarning` messages.
- Release builds now require a clean Git commit: `scripts/build-release.py`
  resolves HEAD, verifies every release file is tracked, present, and
  byte-identical to its HEAD blob, and reads all content from the Git object
  database, so dirty workspaces can never leak into published archives.
  Non-Git trees refuse by default and require `--allow-unverified`, which
  labels the result an unverified-source-tree build. The manifest records the
  source type and commit.
- The committed `.codex/config.toml` keeps safe defaults (on-request
  approval, workspace-write sandbox, network access off). Template Doctor
  gained the `config.safe_defaults` rule, which blocks a release when the
  committed configuration departs from those defaults, is unparseable, or
  embeds absolute paths or credentials. `approval_policy = "never"` is never
  a template default.
- The `.codex` release inventory is now a precise allowlist
  (`config.toml`, `mcp.example.toml`, and the four named agent files) instead
  of an open directory, so runtime session and experiment files can never be
  packaged.
- The unit-test suite runs only fast, directed tests. The recursive full
  release validation (setup/verify/evals/doctor on a clean extraction) moved
  to `scripts/integration-test-release.sh`, which also covers double-build
  byte determinism and corrupted-extracted-tree rejection and is executed by
  the release-artifacts workflow.
- Validation subprocesses now run through shared process-tree helpers with
  bounded per-stage timeouts and whole-tree termination (POSIX `killpg`,
  Windows `taskkill /T /F /PID`), so a hung validation stage can neither
  block indefinitely nor leave descendant processes behind.
- CodeGraph detection now has three explicit states: absent index reports
  `skip/info` by default and `fail/error` under `--strict`; a present but
  corrupt or invalid database always reports `fail/error`; a valid candidate
  database reports `pass` with relative-path evidence. The recognition check
  is explicitly a heuristic: a database passes when SQLite `quick_check`
  succeeds and it contains at least one currently recognized candidate table
  such as `nodes` or `edges`; the check does not claim compatibility with a
  complete or official CodeGraph schema.
- CI and release-archive validation share one allowlist
  (`RELEASE_EXTRACTION_ALLOWED_FAILURES`, only `git.baseline`); CodeGraph has
  no failure allowlist anywhere.
- Archive `--validate` reports stage, command, timeout, and output summaries
  on timeout, and always removes its temporary extraction directory.
- GitHub Actions pinned to full commit SHAs with version comments.
- The CodeGraph recognition check is explicitly a heuristic: `nodes`-only,
  `edges`-only, and combined databases pass when `quick_check` succeeds,
  while databases with no recognized candidate table remain blocking. No
  complete-schema guarantee is claimed.

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
