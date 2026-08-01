"""Shared validation policy for release and CI gates.

Single source of truth for which Template Doctor findings are acceptable as
blocking failures in a validation context. ``codegraph.initialized`` is
deliberately absent: a missing CodeGraph index is expressed by the Doctor
itself as a non-blocking ``skip`` (``--strict`` promotes it to a blocking
failure), and a corrupt or invalid CodeGraph database must never be allowed.
"""

from __future__ import annotations

# Findings that are explicitly deferred external state and never block
# CI or release extraction validation.
RELEASE_EXTRACTION_ALLOWED_FAILURES = frozenset({"git.baseline"})
