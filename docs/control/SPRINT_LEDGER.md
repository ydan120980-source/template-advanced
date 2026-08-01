# SPRINT_LEDGER.md

This file is the append-only sprint history for the project.

A clean template starts with no recorded sprints and no author runtime state.
After each accepted sprint, append a section using the Evidence Ledger format
defined in `docs/ai-workflow/EVIDENCE_LEDGER_TEMPLATE.md`. Keep the ledger
append-only: never rewrite or delete a recorded outcome.

---

```text
Evidence Ledger

Sprint ID: CODEX-CLOSEOUT-2026-08-01
Date: 2026-08-01
Repo: template-advanced
Task Size: Small
Workflow Mode: Lite

Decision Note:
- Why Lite is sufficient: bounded fix sprint over existing contracts; no new
  product axis, no dependency change, no boundary change.
- Allowed Paths: tools/, scripts/, tests/, docs/, README.md, CONTRIBUTING.md,
  AGENTS.md, evals/, .github/workflows/
- Forbidden Paths: dist/, .git/, secrets, dependency files, Run Guard core
  logic, CI workflow structure, v1.0.0 tag, GitHub Release
- Escalation Conditions: none triggered

Files Changed:
- tools/template_doctor/policy.py (new): shared RELEASE_EXTRACTION_ALLOWED_FAILURES
- tools/template_doctor/rules.py: codegraph three-state detection (absent,
  corrupt, valid); expected schema tables {nodes, edges}; relative-path evidence
- tools/template_doctor/engine.py, __main__.py: --strict passthrough
- scripts/ci-doctor-gate.py: ALLOWED_FINDINGS from shared policy
- scripts/verify-release-archive.py: shared policy, timeout diagnostics with
  stage/command/stdout/stderr, temporary-extract cleanup, --extract-dir mkdir
- evals/run-evals.sh: shared policy in clean-template-init
- tests/: 7 new codegraph tests, 4 new policy/verifier tests
- docs/: control docs, CODEGRAPH.md, TEMPLATE_DOCTOR.md,
  GITHUB_RELEASE_READINESS.md, README.md, AGENTS.md, CONTRIBUTING.md,
  evals expected/tasks docs

Commands Actually Run:
- bash scripts/setup.sh (exit 0)
- bash scripts/verify.sh (exit 0; all unit suites in all three suite
  directories pass)
- bash evals/run-evals.sh (exit 0; all eval cases pass)
- py -3 -B -m tools.template_doctor --root . --format json (exit 0, ready)
- py -3 -B -m tools.template_doctor --root . --format json --strict (exit 1,
  codegraph.initialized fail/error as designed)
- py -3 scripts/build-release.py --out-dir dist (exit 0, 107 files)
- py -3 scripts/verify-release-archive.py --archive ... --validate (exit 0,
  22s, no temp dirs left)

Validation Result:
- Passed: unit suites, verify, 8/8 evals, CI doctor gate (exit 0), default
  Doctor (ready), archive --validate, double-build byte determinism
- Notes: corrupt .codegraph db returns fail/error in default AND strict mode;
  mixed valid/corrupt returns fail/error; valid db returns pass with
  relative-path evidence

Escalation Triggered:
- No

Follow-up:
- Rebuild release artifacts before commit (digests recorded in the release
  manifest); owner decides whether to publish v1.0.1
- Initialize CodeGraph when a maintainer tool is available
```
