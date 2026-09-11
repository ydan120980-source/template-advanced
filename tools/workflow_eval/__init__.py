"""Workflow comparison evaluation tooling (standard library only).

``tools.workflow_eval`` prepares isolated trial trees from locked historical
source snapshots, grades candidate modifications with frozen independent
acceptors, and renders a deterministic Markdown comparison report. It exists
to answer workflow questions (does structured AIWF contracting change trial
outcomes?) with auditable evidence; real-model trial runs are never part of
per-commit CI.
"""

from __future__ import annotations

CONTROL = "control"
EXPERIMENT = "experiment"
