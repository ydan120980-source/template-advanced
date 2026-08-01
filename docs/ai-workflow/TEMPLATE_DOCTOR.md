# Template Doctor

Template Doctor is a read-only, Python-standard-library audit for deciding whether a copy of this advanced template has completed project initialization.

## Run

From the template root:

```powershell
py -3 -B -m tools.template_doctor --root . --format json
py -3 -B -m tools.template_doctor --root . --format markdown
```

`--root` must name an existing directory. Output is written to standard output.

## Exit Codes

| Code | Meaning |
|---:|---|
| `0` | The audit completed and no readiness-blocking issue was found. |
| `1` | The audit completed and found one or more readiness issues. |
| `2` | The invocation was invalid or the audit could not run. |

Exit `1` is an expected, successful Doctor result for an uninitialized template. It is different from an operational failure.

## Report Contract

JSON and Markdown reports contain a deterministic list of findings. Every finding has:

- a stable rule ID;
- a severity;
- a status;
- evidence;
- a concrete recommendation.

Independent rules run through a bounded thread pool. The execution engine sorts results by stable rule ID, and each rule emits stable evidence, so scheduling order does not change the serialized report.

## Readiness Rules

The Doctor checks:

- unresolved placeholders in control files;
- whether `NEXT_CODEX_TASK.md` is structurally executable;
- whether `CURRENT_PROJECT_STATE.md` has usable freshness metadata;
- whether control docs and README embed author-local paths, active-plan
  pointers, or historical scan/run identifiers;
- whether the Task Packet, current state, and any active-plan pointer agree;
- whether docs assert drift-prone numeric test/rule counts or pass claims;
- whether a published release manifest still matches the current release tree;
- consistency of the single-planning-authority policy;
- unsupported profile tables in project `.codex/config.toml`;
- placeholder validation and eval scripts;
- TODO architecture documentation;
- Git baseline availability;
- presence and representative behavior of an active `.gitignore`;
- project-local CodeGraph initialization.

Hooks, MCP, and global-memory checks are capability probes only. They report metadata such as availability or an explicit skip; they do not read secret values, disclose global file contents, or modify user/global configuration. Optional unavailable capabilities do not by themselves turn an otherwise initialized project into an operational error.

## Interpretation

Use the summary and individual recommendations to initialize the copied project. Re-run the Doctor after each initialization step. Do not “fix” a finding by weakening a rule or deleting expected evidence; replace template placeholders with real project decisions and validation.

The Doctor deliberately does not initialize Git, create `.gitignore`, initialize CodeGraph, configure Hooks/MCP, edit global memory, or rewrite validation scripts.

### Verification boundaries

- Git readiness is verified by resolving `HEAD^{commit}` with the installed Git executable.
- `.gitignore` behavior is checked against a deterministic representative-path matcher; it is not a complete replacement for `git check-ignore`.
- CodeGraph readiness verifies a healthy, read-only SQLite database with schema tables. It does not bind the Doctor to a private CodeGraph schema version.
- An example MCP file is reported as skipped, not as a configured capability.

## Tests

Fixtures are isolated under `tests/template_doctor/`:

```powershell
py -3 -m unittest discover -s tests/template_doctor -v
```

The suite covers ready, placeholder, configuration-drift, deterministic-concurrency, report-format, and exit-code behavior.
