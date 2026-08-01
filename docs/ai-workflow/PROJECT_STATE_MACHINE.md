# Project State Machine

This file defines the default cross-project state machine for the v2 ChatGPT + Codex Operating System. Project profiles may map local wording to these states, but should not introduce project-specific states into Workflow Core.

## Required Decision Record

Every cloud AI decision must state:

- Current State
- Proposed Next State
- Why the transition is valid
- What is forbidden in the new state
- What evidence supports the transition

State Transition Decision Record

Current State:
Proposed Next State:
Why this transition is valid:
Evidence supporting the transition:
What is forbidden in the new state:
Reviewer Strategy:
Meta Reviewer Required:
Contract / Interface / Public Entrypoint Policy:
Next Allowed Action:
Stop Conditions:

## States

### DISCOVERY

- Allowed: read docs, map project goals, inspect boundaries, identify implementation/test paths, run read-only probes.
- Forbidden: implementation sprint, new public entrypoint, contract changes, broad refactors.
- Entry Conditions: context is incomplete, project is new to the session, or Context Completeness <= 2.
- Exit Conditions: main charter, boundaries, current axis, validation profile, and recent state are known.
- Recommended Next State: FOUNDATION.
- Reviewer Strategy: Meta Reviewer optional if the next axis is ambiguous.
- Contract / Interface / Public Entrypoint: not allowed.

### FOUNDATION

- Allowed: establish minimal mainline, document boundaries, create safe scaffolding, set validation baseline.
- Forbidden: execution / ingress, broad feature expansion, irreversible architecture choices without reviewer.
- Entry Conditions: DISCOVERY is complete and a foundation gap blocks delivery.
- Exit Conditions: mainline is coherent, validation path exists, and first delivery slice can be scoped.
- Recommended Next State: FIRST_DELIVERY_SLICE.
- Reviewer Strategy: reviewer required for Large bootstrap or new contract.
- Contract / Interface / Public Entrypoint: allowed only when explicitly scoped and reviewed.

### FIRST_DELIVERY_SLICE

- Allowed: implement one bounded user-visible, operator-visible, or delivery-visible slice.
- Forbidden: multiple slices at once, backend/payment/auth/execution expansion unless project profile explicitly allows it.
- Entry Conditions: foundation is sufficient and scorecard supports delivery work.
- Exit Conditions: first slice is implemented, verified, and captured in Evidence Ledger.
- Recommended Next State: SECOND_SLICE_REUSE or HARDENING.
- Reviewer Strategy: reviewer required if first slice crosses layers or Boundary Risk >= 4.
- Contract / Interface / Public Entrypoint: allowed only with Large + reviewer.

### SECOND_SLICE_REUSE

- Allowed: reuse an established pattern on a second bounded slice; validate repeatability.
- Forbidden: changing the original contract shape unless explicitly scoped.
- Entry Conditions: first slice passed and a similar high-value slice is available.
- Exit Conditions: reuse pattern is proven or a limitation is documented.
- Recommended Next State: HARDENING or NEXT_AXIS.
- Reviewer Strategy: usually implementer-only unless scorecard triggers reviewer.
- Contract / Interface / Public Entrypoint: usually not allowed; use project profile exception only.

### HARDENING

- Allowed: improve validation, edge states, docs, diagnostics, reliability, and focused polish.
- Forbidden: new broad capability, new architecture surface, reopening closed axes without evidence.
- Entry Conditions: delivery slice exists and needs quality or operability strengthening.
- Exit Conditions: validation confidence is high and residual work is clear.
- Recommended Next State: DELIVERY_READY or NEXT_AXIS.
- Reviewer Strategy: reviewer optional; required for high boundary risk.
- Contract / Interface / Public Entrypoint: not allowed unless explicitly approved by project profile and scorecard.

### DELIVERY_READY

- Allowed: closeout, handoff, final validation, Context Compression, bugfix-only marking.
- Forbidden: new feature work, new contract, new public entrypoint, large refactor.
- Entry Conditions: current delivery goal is complete, verified, and evidence-backed.
- Exit Conditions: CURRENT_PROJECT_STATE or equivalent handoff is updated.
- Recommended Next State: BUGFIX_ONLY or NEXT_AXIS.
- Reviewer Strategy: Meta Reviewer recommended before final closeout.
- Contract / Interface / Public Entrypoint: not allowed.

### BUGFIX_ONLY

- Allowed: focused fixes, validation repairs, documentation corrections, evidence cleanup.
- Forbidden: new capability, new delivery slice, new contract, new public entrypoint.
- Entry Conditions: an axis or area has been closed and marked stable.
- Exit Conditions: explicit project decision reopens the area with scorecard and reviewer.
- Recommended Next State: NEXT_AXIS, or remain BUGFIX_ONLY.
- Reviewer Strategy: usually not required for small fixes; required if reopening scope.
- Contract / Interface / Public Entrypoint: not allowed.

### NEXT_AXIS

- Allowed: choose and scope the next highest-value axis, run Meta Reviewer, prepare scorecard.
- Forbidden: implementation before scorecard and context are ready.
- Entry Conditions: previous axis is closed, low-value, blocked, or bugfix-only.
- Exit Conditions: next axis is selected and classified.
- Recommended Next State: DISCOVERY, FOUNDATION, FIRST_DELIVERY_SLICE, or HARDENING depending on context.
- Reviewer Strategy: Meta Reviewer required before starting a high-risk new axis.
- Contract / Interface / Public Entrypoint: not allowed until the next state permits it.
