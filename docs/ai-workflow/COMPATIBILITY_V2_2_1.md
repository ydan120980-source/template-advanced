# v2.2.1 compatibility evidence

The v2.2.1 candidate contains the local validation fixes already merged after
v2.2.0, plus a version change and release documentation. It introduces no new
public interface or dependency. `v2.2.0` points to commit
`67adc5c0f6db12a6b36c508b5e71e63e1834c9e9`; the pre-version-change template
baseline is `895059351c98ecbdb6a58ff0818b6474c4c8ad2d`.

## Completed baseline matrix

[Validation Issue #27](https://github.com/ydan120980-source/template-advanced-validation/issues/27)
records fifteen PASS results, zero FAIL, zero BLOCKED and zero NOT_RUN, using
the baseline template above and validation framework
`0022cbbc2557887f14248e9ee6904fb6ba61e0dd` throughout. Each cell completed native
baseline tests, integration and task execution, final regression checks,
applicable template checks and successful workspace cleanup. Every cell had
nonzero test execution counts.

| System | Run | Click | Flask | TanStack Query | ripgrep | Petclinic |
| --- | --- | --- | --- | --- | --- | --- |
| Ubuntu | [36822266250](https://github.com/ydan120980-source/template-advanced-validation/actions/runs/36822266250) | PASS | PASS | PASS | PASS | PASS |
| Windows | [36823074916](https://github.com/ydan120980-source/template-advanced-validation/actions/runs/36823074916) | PASS | PASS | PASS | PASS | PASS |
| macOS | [36824319511](https://github.com/ydan120980-source/template-advanced-validation/actions/runs/36824319511) | PASS | PASS | PASS | PASS | PASS |

The runs executed in Ubuntu, Windows, macOS order. Petclinic PostgreSQL and
MySQL container validation completed on Ubuntu; the other systems did not run
those container scenarios. Counts in result files aggregate per-command test
executions and must not be presented as counts of unique tests.

The fixed upstream commits are:

| Project | Commit |
| --- | --- |
| Click | `8b19813f2bfca99f1018a587a8cf54fc959f2e5d` |
| Flask | `22d924701a6ae2e4cd01e9a15bbaf3946094af65` |
| TanStack Query | `413ba6e30b72a89ad71710c91633c3099638fd56` |
| ripgrep | `e89fff89ac9af12e8d4ce9d5fd07beb408ca730f` |
| Petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` |

## Candidate acceptance

The completed baseline matrix is historical evidence. The version and
documentation changes produce a new template commit, whose release readiness
requires its own exact-SHA local gates, CI, Security, release-candidate checks
and complete fifteen-cell matrix. Results from different template or framework
commits cannot be combined into a final matrix.

Final evidence belongs to the verified release-preparation Task Issue and its
Evidence Ledger. Until that ledger binds all gates to the frozen candidate,
this document does not claim that v2.2.1 is ready or published. Account quota
and budget-stop settings remain separate prerequisites for any private-runner
batch; zero current spend alone does not establish available free allowance.

## Integration and local use

Use the release archive and initialization procedure described in the README.
Keep the committed Codex safety defaults for distributed templates. Personal
runtime configuration belongs to the local workspace and must be preserved
when preparing an isolated release candidate.

The validation framework excludes the exact repository-relative `tests/`
prefix when copying template files into a host project, so host tests retain
their own import and discovery behavior. Other paths containing the word
`tests` are handled by the original selection rules. Copying and result-count
validation share the same selection rule; expected host collisions are
preserved and source hashes are checked. This is validation-framework behavior,
not a new template CLI option.

See [Release failure stages](RELEASE_FAILURE_STAGES.md) for failures that prevent
promotion, and [GitHub Release Readiness](GITHUB_RELEASE_READINESS.md) for the
remaining owner decisions and artifact verification.
