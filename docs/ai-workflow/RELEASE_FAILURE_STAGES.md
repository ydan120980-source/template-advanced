# Release failure stages

Record the failing command, native exit code, exact source and framework SHAs,
raw diagnostic and resulting classification in the Evidence Ledger. Preserve
failed results; a later success does not rewrite historical evidence.

| Stage | Evidence required | Failure response |
| --- | --- | --- |
| Authority and scope | Verified Task Issue contract, base and allowed paths | Stop on an invalid contract, drift or a required scope change. |
| Local candidate | Clean committed source; tests, lint, structural checks, evals, Doctor and static gate | Repair the demonstrated defect within contract scope, then repeat affected checks. |
| Release build | Deterministic double build, seven attachments, checksums, payload digest, provenance and release-set | Reject dirty or divergent release inputs and inconsistent artifacts. |
| Clean extraction | Independent archive verification and tests in a fresh directory | Preserve the failed directory and use the verifier's fresh temporary extraction for acceptance. |
| Remote budget | Fresh zero-paid spend, adequate free allowance and budget-stop evidence | Pause before dispatch if any required fact is missing or insufficient. |
| Project cell | Nonzero native baseline, task and final tests; applicable template checks; cleanup | Reject failure, cancellation, timeout, zero tests, missing results and failed cleanup. |
| Exact-SHA remote gates | Successful expected CI, Security and release-candidate jobs bound to the candidate | Reject missing, skipped, partial or inaccessible evidence. |
| Main and publication | Owner approval, accepted main tree, annotated tag and independently verified Draft Release | Keep draft artifacts unpublished until all owner decisions and checks complete. |
| Published artifacts | Download, checksum, provenance, release-set and clean extraction verification | Report an incomplete release if post-publication acceptance cannot be proven. |

## Distinguishing local configuration from product failures

`.codex/config.toml` is release content. Unsafe local preferences can make
Doctor report `not_ready` and make the release builder reject the source as
untrusted. Preserve the user's workspace preferences and validate committed
safe defaults in a clean isolated worktree. Do not change the product's safety
rules to accommodate local preferences.

An explicitly supplied extraction directory may be reused by the archive
verifier. Earlier test outputs can therefore contaminate a later verification.
A directory nested inside another Git worktree can also resolve to the parent
Git root and violate Doctor's root identity check. Follow the CI recipe that
omits `--extract-dir` and creates a fresh temporary extraction; neither a
contaminated directory nor an inherited Git root proves an archive defect.

## Distinguishing project and framework failures

Compare the fixed upstream without integration against the integrated project.
Record framework diagnostics and project behavior separately. A failure in the
pristine upstream needs preserved control evidence; rerunning until green does
not establish a repair. Template defects are repaired in the template repository;
validation adapters and result-checking defects belong in the validation repository.

Only terminate processes and release resources shown to belong to the current
task. Workspace deletion must succeed for the cell to pass. Do not remove host
tests, introduce evasive skip/xfail markers, relax result counts or bypass
security checks to obtain a green matrix.

Changing a frozen candidate invalidates its final matrix. Establish a new
complete matrix on one template commit, one validation-framework commit and
the five fixed upstream commits. Preserve prior matrices as historical evidence.
