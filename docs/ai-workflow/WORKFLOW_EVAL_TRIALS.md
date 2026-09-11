# Workflow Eval Trials

How `tools/workflow_eval` runs real-model comparison trials, and what its
evidence does and does not prove.

## The three questions

A comparison batch answers three different questions, and they are recorded
separately because conflating them is the failure mode this document exists
to prevent:

1. **Record structure** — is every result file internally consistent, is the
   expected slot set present, and is the batch labelled consistently?
2. **Trial protocol validity** — was each run an independently executed
   trial, with no contact with the answer, no acceptor tampering, and no
   scope violation?
3. **Functional outcome** — how did the valid trials actually grade?

A full set of well-formed result files answers only the first question. Six
JSON files are not a comparison.

## Validity states

`trial_validity` on a graded record carries one of:

| State | Meaning |
|---|---|
| `VALID` | The coordinator audited the run and found no disqualifying issue. |
| `INVALID` | The audit found a disqualifying issue; the run is preserved, not replaced. |
| `UNVERIFIED` | No audit is attached. This is the default and never fills a valid slot. |

Rules:

- The classification belongs to the coordinator. A trial agent cannot
  certify its own run: any `VALID` or `INVALID` claim must cite the audit
  record it rests on, and a claim without a basis degrades to `UNVERIFIED`.
- A record that predates the attestation requirement is `UNVERIFIED`, never
  silently valid. Missing evidence is not evidence.
- Functional grading is independent of validity. A run can grade `ACCEPT`
  and still be `INVALID`; its score stays on the record and is excluded from
  the valid comparison.

## What makes a run INVALID

- Contact with the answer: reading the source repository's fixed file, or
  reaching upstream history through Git discovery.
- A lost trial repository: if the trial's `.git` disappears, Git discovery
  walks up into the enclosing source repository. `grade.py` refuses such a
  run before grading, so it produces no record at all.
- Contact with the acceptors, or any modification of them.
- Candidate edits outside the task's allowed paths.

A run that only touched a neutral scratch directory (for example a throwaway
repository under the system temp directory) is reported as a deviation and
judged against the frozen rule in use; it cannot leak the answer.

## Auditing every channel

Independence cannot be judged from shell calls alone. A trial can read the
source repository with a file-read or search tool and never issue a shell
command, so an audit that only inspects `Bash` returns a clean result that
means nothing.

`tools/workflow_eval/audit.py` walks the trial sub-agent's session record and
reports, per call: the tool, the channel, the absolute targets and their
scope (trial / scratch / source repository / other), calls that named no
absolute path and therefore ran against the host's default working
directory, and `git` commands that were not anchored inside the trial
directory. It reports facts; it does not decide validity. It stays
standard-library-only, so a test pins its shell-request classification
against the frozen Run Guard parser the coordinator reports budgets from.

Audit results feed the coordinator's attestation, which is recorded as
`trial_validity` on the graded record.

## `trial_isolated` is narrow

`trial_isolated` records exactly one check: the pre-scoring Git root probe
passed, meaning the candidate directory owns its `.git` and
`git rev-parse --show-toplevel` resolves to the candidate itself. It is a
prerequisite for a valid trial and nothing more. A run can pass the Git
probe and still read the source repository through a non-shell tool, which
is why validity is a separate attestation rather than a derived flag.
`trial_isolation_check` states this scope on the record.

## Budgets

A trial budget is at most 15 minutes wall clock and at most 25 shell-bearing
tool requests. Requests are counted from the session record with the frozen
Run Guard parser (`tools/aiwf_run_guard/budget.py`), not from the agent's own
report. Exhausted budgets are recorded honestly as timeout or incomplete and
are never re-run to look better.

## Host constraints

Some properties of the execution host cannot be fixed by trial setup and are
recorded as limitations instead of being presented as sandboxing:

- The host fixes each sub-agent's default working directory to the workspace
  root, not to the trial directory. Relative paths therefore resolve against
  the source repository. Trials must anchor every command with an absolute
  path, and the audit reports unanchored `git` commands.
- Directory layout and Git checks are preparation hygiene, not an operating
  system sandbox. Nothing prevents a sub-agent from reading an arbitrary
  path; the audit detects it afterwards.
- The host exposes a model identifier; the backend version behind it is
  `unknown` unless the host reports one.

If a session record is unavailable, or a read channel cannot be audited, the
run is `UNVERIFIED` and the batch stops rather than running trials whose
independence cannot be checked.

## Batch separation

Each round of trials is its own batch with its own label and its own report.
Batches are never concatenated, and a later batch never replaces an earlier
batch's records. Superseded or invalid records stay in place with their
validity annotation, so the difference between what was run and what counts
is visible.

## Trial outcomes are exploratory

Three tasks and two groups per batch is an exploration, not a statistical
result. A single round does not establish a general workflow effect, and no
report should claim one.
