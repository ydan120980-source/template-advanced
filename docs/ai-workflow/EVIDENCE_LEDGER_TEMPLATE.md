# Evidence Ledger Template

Every sprint must leave an auditable Evidence Ledger entry. The required weight depends on Workflow Mode.

- **Lite**: use the compact template. It records the lightweight decision note, focused validation, changed files, and whether escalation was triggered.
- **Standard / Full**: use the full template. It records the complete scorecard, control-state inputs, validation, git state, reviewer / next-state decisions, and follow-up.

Fill the appropriate template at the end of the sprint, before closeout or handoff.

## Compact Evidence Ledger For Lite

```text
Evidence Ledger

Sprint ID:
Date:
Repo:
Task Size:
Workflow Mode: Lite

Decision Note:
- Why Lite is sufficient:
- Allowed Paths:
- Forbidden Paths:
- Escalation Conditions:

Files Changed:
- ...

Commands Actually Run:
- Focused:
- Other:

Validation Result:
- Passed / Failed / Not Run:
- Notes:

Escalation Triggered:
- Yes / No
- Reason:

Follow-up:
- ...
```

## Full Evidence Ledger For Standard / Full

```text
Evidence Ledger

Sprint ID:
Date:
Repo:
Current State:
Current Axis:
Task Type: Large / Medium / Small / preflight / closeout / fix / shrink
Workflow Mode: Standard / Full

Decision Scorecard:
- Outcome Impact:
- Project Value:
- Verification Confidence:
- Boundary Risk:
- Reversibility:
- Context Completeness:
- Reviewer Worthiness:
- Decision:

Input Docs Read:
- <MAIN_CHARTER_DOC>
- <AGENTS_DOC>
- <BOUNDARY_DOCS>
- <HANDOFF_DOCS>
- PROJECT_STATE_MACHINE.md
- SPRINT_DECISION_SCORECARD.md
- EVIDENCE_LEDGER_TEMPLATE.md
- Other:

Prompt Asset Used:
- <PROMPT-LARGE-BOOTSTRAP / PROMPT-LARGE-NEW-CONTRACT / PROMPT-LARGE-BUSINESS-SLICE / PROMPT-MEDIUM-HARDENING / PROMPT-MEDIUM-REUSE-SLICE / PROMPT-SMALL-FIX / PROMPT-SMALL-CLOSEOUT / PROMPT-REVIEWER-LARGE / PROMPT-META-REVIEWER / PROMPT-FAILURE-POSTMORTEM / PROMPT-HANDOFF-NEW-SESSION>

Allowed Paths:
- ...

Forbidden Paths:
- ...

Stop Conditions:
- ...

Commands Actually Run:
- Focused:
- Adjacent:
- Default:
- Build:
- Other:

Test Result:
- Passed:
- Failed:
- Not Run:
- Notes:

Build Result:
- Passed:
- Failed:
- Not Run:
- Notes:

Git Status Before:
<paste status>

Git Status After:
<paste status>

Files Changed:
- ...

Commit Hash:
- <hash / none>

Reviewer Result:
- pass / pass with fixes / blocked / not applicable
- Notes:

Failure Taxonomy:
- Scope Creep: yes/no
- Boundary Violation: yes/no
- Verification Failure: yes/no
- Context Missing: yes/no
- Wrong Task Size: yes/no
- Low Value Work: yes/no
- Workspace Noise Mix-in: yes/no
- Fake Confidence: yes/no
- Architecture Drift: yes/no
- Product Drift: yes/no
- Next Action: fix sprint / shrink sprint / context fill / rollback / closeout / switch axis / blocked escalation / none

Cloud AI Decision:
- pass / fix / shrink / closeout / switch axis / blocked escalation
- Reason:

Next State:
- DISCOVERY / FOUNDATION / FIRST_DELIVERY_SLICE / SECOND_SLICE_REUSE / HARDENING / DELIVERY_READY / BUGFIX_ONLY / NEXT_AXIS

Deferred Items:
- ...

Known Workspace Noise:
- ...
```

## Completion Rule

A sprint is not fully closed until the Evidence Ledger contains enough information for a new session to understand what changed, what was verified, what remains deferred, and why the selected Workflow Mode was valid. For Standard / Full, it must also explain why the next state is valid.
