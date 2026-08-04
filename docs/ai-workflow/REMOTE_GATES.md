# Remote Gates

Remote gates answer questions that local source inspection cannot answer. They
are read-only checks bound to an exact commit SHA and must never infer success
from a missing, skipped, neutral, or partial response.

## Static gate

```powershell
py -3 -B -m tools.governance_v2 gate static --root .
```

The standard-library checker targets the selected CI, Security, and
release-candidate workflow shapes. It checks required jobs and steps,
job-level timeouts, read/write permission placement, dangerous triggers,
full-SHA action pins, release-candidate read-only behavior, and the three
summary layers. It deliberately does not claim to fully parse YAML anchors,
expressions, matrices, reusable workflows, or the GitHub Actions schema.

Its only successful output is `STATIC_TARGETED_PASS`; unsupported structure is
`BLOCKED`, and a detected violation is `FAIL`.

## GitHub gate

```powershell
py -3 -B -m tools.governance_v2 gate github \
  --repo owner/name --sha <40-hex-sha> \
  --workflow release-candidate.yml \
  --check-name release-candidate --app-id <id>
```

The gate reads workflow runs, jobs, and Check Runs. It requires the exact SHA,
the expected active workflow path, a completed successful run, non-empty jobs
whose conclusions are successful, the named successful Check Run, and the
expected GitHub App ID when configured. Startup failure, `jobs=[]`, missing or
partial API fields, permission errors, API unavailability, `neutral`, and
`skipped` are never success. A fixture input is available for deterministic
local tests; it does not simulate a live remote approval.

The API adapter uses GET only and has no Issue, PR, branch-protection, tag, or
Release mutation path. The release-candidate workflow uses `contents: read`
and does not create tags or releases. PR A does not add release-candidate to
required checks; that is a later Bootstrap B decision.
