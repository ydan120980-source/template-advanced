# Sprint Decision Scorecard

Fill this before generating any implementer prompt. Scores are 1 to 5.

## Copy-Fill Template

```text
Sprint Decision Scorecard

Sprint ID:
Date:
Repo:
Current State:
Current Axis:
Candidate Sprint:

1. Outcome Impact: <1-5>
Reason:

2. Project Value: <1-5>
Reason:

3. Verification Confidence: <1-5>
Reason:

4. Boundary Risk: <1-5>
Reason:

5. Reversibility: <1-5>
Reason:

6. Context Completeness: <1-5>
Reason:

7. Reviewer Worthiness: <1-5>
Reason:

Decision:
- Implement / Do Not Implement:
- Task Type: Large / Medium / Small / preflight / context fill / closeout / switch axis
- Reviewer: required / optional / not needed
- Meta Reviewer: required / not needed
- Rollback Plan Required: yes / no
- Scope Adjustment:
- Next State:
```

## Scoring Standards

### Outcome Impact

- 1 = invisible to current delivery goal
- 3 = indirectly improves user-visible, operator-visible, or delivery-visible clarity
- 5 = directly strengthens the current delivery goal or visible closed loop

### Project Value

- 1 = polish only or low-value busywork
- 3 = improves one secondary workflow or reliability concern
- 5 = closes or unlocks a core current-stage gap

### Verification Confidence

- 1 = cannot be verified locally or through agreed evidence
- 3 = partially verifiable with focused checks
- 5 = directly verifiable with focused + adjacent + default + build checks from validation profile

### Boundary Risk

- 1 = safe local-only change
- 3 = touches shared contract or cross-layer surface
- 5 = approaches forbidden architecture surfaces, execution, ingress, provider, backend, or other high-sensitive boundary

### Reversibility

- 1 = hard to rollback
- 3 = moderate rollback cost
- 5 = isolated and easy to revert

### Context Completeness

- 1 = missing key docs, paths, boundaries, or recent results
- 3 = enough to proceed with constraints
- 5 = current state, boundaries, paths, tests, prior results, and workspace noise are all known

### Reviewer Worthiness

- 1 = reviewer would add little value
- 3 = optional reviewer
- 5 = reviewer required

## Decision Thresholds

- If Outcome Impact + Project Value < 7, do not open an implementation sprint.
- If Boundary Risk >= 4, shrink scope or classify as Large with reviewer.
- If Verification Confidence <= 2, do not implement; open a preflight / read-only probe.
- If Context Completeness <= 2, collect missing context before implementation.
- If Reversibility <= 2, require rollback plan in the implementer prompt.
- If Reviewer Worthiness >= 4, include reviewer prompt.
- If the current axis has already passed multiple rounds and new value is marginal, closeout or switch axis.

## When To Upgrade To Large

Upgrade to Large when any of these are true:

- New axis starts.
- New contract, interface, or public entrypoint is proposed.
- Boundary Risk >= 4.
- Reviewer Worthiness >= 4.
- The sprint crosses three or more meaningful layers.
- Rollback cost is high.

## When Reviewer Is Required

Reviewer is required when:

- Task type is Large.
- Boundary Risk >= 4.
- Reviewer Worthiness >= 4.
- New contract / interface / public entrypoint is touched.
- The sprint approaches execution / ingress or another high-sensitive boundary.

## When Implementation Is Not Allowed

Do not implement when:

- Outcome Impact + Project Value < 7.
- Verification Confidence <= 2.
- Context Completeness <= 2.
- The only path forward requires forbidden architecture surfaces.
- The current axis should be closed or switched.
