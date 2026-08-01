# CodeGraph (Optional Capability)

CodeGraph is an **optional maintainer capability** for this repository. It is
not required to run the template, execute tests, build the release archive, or
use Template Doctor or Run Guard.

## Current Status

`CodeGraph configuration prepared; real indexing not verified in this environment.`

No CodeGraph CLI or Codex CodeGraph tool was available in the release
environment, so no index was created and no index was committed. This
repository intentionally does not fabricate an initialization marker.

## Behavior Without An Index

- Template Doctor reports `codegraph.initialized` as a non-blocking `skip` by
  default, with a recommendation to initialize when approved. A `.codegraph`
  database that exists but is unreadable or missing schema tables still fails
  the rule.
- `--strict` promotes the absent index to a blocking `fail`; use it when the
  index is a hard requirement for a release or handoff.
- The CI gate (`scripts/ci-doctor-gate.py`) has no CodeGraph allowlist entry:
  the default non-blocking skip means an absent index never blocks normal CI.
- `.gitignore` excludes `.codegraph/`, so any future index database stays out
  of Git history.

## Initializing When A Tool Is Available

When a maintainer has a working CodeGraph CLI or Codex CodeGraph tool:

1. Complete the Git baseline first so symbols can be anchored to a real commit.
2. Initialize the index at the repository root (the project-local `.codegraph/`
   directory is ignored and never committed).
3. Verify with anchored queries on the public chains:
   - CLI entry points to Run Guard core (`tools/aiwf_run_guard/*`);
   - verify wrapper to tests and evals (`scripts/verify.sh`, `tests/*`,
     `evals/*`);
   - release builder to inventory to manifest
     (`scripts/build-release.py` -> `tools/template_doctor/release_inventory.py`);
   - archive verifier to clean-extraction validation
     (`scripts/verify-release-archive.py`);
   - Template Doctor to release rules (`tools/template_doctor/rules.py`).
4. Do not commit machine-generated cache files or absolute index paths.
5. Rerun Template Doctor; `codegraph.initialized` must flip from `skip` to
   `pass` only when the index is real and readable.

## Architecture Note

CodeGraph output is evidence, not authority. Source, targeted search, tests,
and executed commands remain the binding evidence when the index is missing,
stale, or in conflict with the current tree.
