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
  corrupt, valid); heuristic candidate tables {nodes, edges}; relative-path
  evidence
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

```text
Evidence Ledger

Sprint ID: CODEX-CODEGRAPH-HEURISTIC-2026-08-01
Date: 2026-08-01
Repo: template-advanced
Task Size: Small
Workflow Mode: Lite

Decision Note:
- Why Lite is sufficient: bounded contract clarification over existing
  three-state detection; no product axis, dependency, or boundary change.
- Allowed Paths: tools/, tests/, docs/
- Forbidden Paths: dist/, .git/, secrets, dependency files, Run Guard core
  logic, CI workflow structure, v1.0.0 tag, GitHub Release
- Escalation Conditions: none triggered

Files Changed:
- tools/template_doctor/rules.py: renamed the recognized-table set to
  recognized_candidate_tables and documented it as a heuristic; pass
  evidence names the candidate tables found; no-recognized-table and
  failed-quick_check failures are now reported distinctly
- tests/template_doctor/test_cli.py: assertions for rule_id, status,
  severity, relative-path evidence, absence of absolute temporary paths,
  and candidate-table names; new nodes-only, edges-only, and empty-database
  cases; unrelated-table database fixture reused
- docs/: CODEGRAPH.md, TEMPLATE_DOCTOR.md, CURRENT_PROJECT_STATE.md, and
  this ledger no longer claim that nodes and edges must both be present or
  that a complete CodeGraph schema is verified

Commands Actually Run:
- py -3 -B -m unittest discover -s tests (exit 0)
- bash scripts/verify.sh (exit 0; lint, structural check, unit suites)
- bash evals/run-evals.sh (exit 0; all eval cases)
- py -3 -B -m tools.template_doctor --root . --format json (exit 0, ready)
- py -3 -B -m tools.template_doctor --root . --format json --strict (exit 1,
  codegraph.initialized fail/error as designed)
- py -3 -B scripts/ci-doctor-gate.py --root . (exit 0)
- py -3 -B scripts/build-release.py --out-dir dist (exit 0; double build
  byte-identical)
- py -3 -B scripts/verify-release-archive.py --archive ... --validate
  (exit 0)

Validation Result:
- Passed: unit suites, verify, all evals, CI doctor gate (exit 0), default
  Doctor (ready), archive --validate, double-build byte determinism
- Notes: nodes-only, edges-only, and nodes+edges databases pass as
  recognized candidates when SQLite quick_check succeeds; readable databases
  with no recognized candidate table remain blocking; corrupt databases
  remain blocking in default and strict modes; this is a heuristic health
  check, not a complete CodeGraph schema compatibility guarantee

Escalation Triggered:
- No

Follow-up:
- Rebuild release artifacts before commit (digests recorded in the release
  manifest); owner decides whether to publish v1.0.1
- Real CodeGraph indexing and the authoritative CodeGraph database schema
  remain unverified because no CodeGraph tool was available in this
  environment
```

```text
Evidence Ledger

Sprint ID: CODEX-CLEAN-RELEASE-SAFE-DEFAULTS-2026-08-01
Date: 2026-08-01
Repo: template-advanced
Task Size: Small
Workflow Mode: Lite

Decision Note:
- Why Lite is sufficient: bounded release-hygiene fix over existing
  contracts; no new product axis, no dependency change, no boundary change.
- Allowed Paths: tools/, scripts/, tests/, docs/, README.md, CONTRIBUTING.md,
  AGENTS.md, CHANGELOG.md, evals/, .github/workflows/, .codex/config.toml,
  .gitignore
- Forbidden Paths: dist/, .git/, secrets, dependency files, Run Guard core
  logic, v1.0.0 tag, GitHub Release
- Escalation Conditions: none triggered

Files Changed:
- .codex/config.toml: committed safe defaults (on-request approval,
  workspace-write sandbox, network access off with opt-in comment)
- tools/template_doctor/release_inventory.py: precise .codex allowlist
  (config.toml, mcp.example.toml, four named agent files)
- tools/template_doctor/release_source.py (new): clean-source gate — release
  files must be tracked at HEAD, present, and byte-identical to HEAD blobs;
  reads content from the Git object database
- scripts/build-release.py: reads release files from HEAD; refuses dirty
  sources; non-Git trees require --allow-unverified (unverified-source-tree
  label)
- tools/template_doctor/rules.py: config.safe_defaults rule (on-request,
  workspace-write, no network, no absolute paths/credentials)
- tools/aiwf_run_guard/procutil.py (new): process-tree helpers with bounded
  timeouts and whole-tree termination (POSIX killpg, Windows taskkill /T /F
  /PID)
- scripts/verify-release-archive.py: validation stages run through the
  process-tree helpers with per-stage timeouts; AIWF_RELEASE_VALIDATION
  recursion guard retained
- tests/: 8 release-source gate scenarios (P0-1..P0-8), 6 config.safe_defaults
  contract tests, 4 procutil timeout/tree-kill tests; the unit suite no
  longer runs the recursive full --validate
- scripts/integration-test-release.sh (new): double build byte-compare,
  clean extraction --validate, corrupted-tree rejection
- .github/workflows/release-artifacts.yml: run the release integration script
  before building the canonical artifact
- docs/: README, AGENTS, CONTRIBUTING, CHANGELOG, CODEX_RUNTIME_PROFILE,
  GITHUB_RELEASE_READINESS, CURRENT_PROJECT_STATE, CHATGPT_HANDOFF,
  NEXT_CODEX_TASK, and this ledger updated for the clean-source gate, safe
  defaults, and split validation

Commands Actually Run:
- py -3 -B -m unittest discover -s tests (exit 0 after commit)
- bash scripts/setup.sh (exit 0)
- bash scripts/verify.sh (exit 0; lint, structural check, unit suites)
- bash evals/run-evals.sh (exit 0; all eval cases)
- py -3 -B -m tools.template_doctor --root . --format json (exit 0, ready)
- py -3 -B -m tools.template_doctor --root . --format json --strict (exit 1,
  codegraph.initialized fail/error as designed)
- py -3 -B scripts/ci-doctor-gate.py --root . (exit 0)
- py -3 -B scripts/build-release.py --out-dir dist-a / dist-b (exit 0;
  double build byte-identical)
- py -3 -B scripts/verify-release-archive.py --archive ... --validate
  (exit 0; clean extraction validation)
- bash scripts/integration-test-release.sh (exit 0)
- git archive / fresh checkout rebuild (artifact bytes identical to the
  committed-tree build)

Validation Result:
- Passed: unit suites, verify, all evals, CI doctor gate (exit 0), default
  Doctor (ready), archive --validate, double-build byte determinism, dirty
  workspace block (dirty config, untracked allowlisted file), non-Git
  refusal, and commit-reproducibility byte comparison
- Notes: the release ZIP built from the final commit is byte-identical to a
  rebuild from a fresh clone/archive of that commit; blocked builds produce
  no artifacts

Escalation Triggered:
- No

Follow-up:
- Owner decides whether to publish v1.0.1
- Real CodeGraph indexing remains unverified; no CodeGraph tool was
  available in this environment
```
