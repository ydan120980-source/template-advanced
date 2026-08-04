"""Conservative, standard-library-only checks for selected GitHub workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class WorkflowCheckError(RuntimeError):
    """A workflow could not be inspected safely."""

    def __init__(self, message: str, *, status: str = "BLOCKED", code: str = "WORKFLOW_CHECK_FAILED"):
        super().__init__(message)
        self.status = status
        self.code = code


_REQUIRED_WORKFLOWS = {
    "ci.yml": ("validate",),
    "security.yml": ("codeql", "credential-scan"),
    "release-candidate.yml": ("release-candidate",),
}
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_USES_RE = re.compile(r"^\s*-\s*uses:\s*([^\s@]+)@([^\s#]+)", re.MULTILINE)
_JOB_RE = re.compile(
    r"(?ms)^  ([A-Za-z0-9_-]+):\s*\n(.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)"
)
_NAMED_STEP_RE = re.compile(
    r"(?ms)^[ ]{6,}- name:\s*([^\n]+)\n(.*?)(?=^[ ]{6,}- name:|\Z)"
)


def _read_workflow(root: Path, relative: str) -> str:
    path = root / ".github" / "workflows" / relative
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorkflowCheckError(
            f"required workflow is missing: {relative}",
            code="WORKFLOW_MISSING",
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise WorkflowCheckError(
            f"cannot read workflow {relative}: {type(exc).__name__}",
            code="WORKFLOW_READ_FAILED",
        ) from exc


def _job_blocks(text: str) -> dict[str, str]:
    return {name: body for name, body in _JOB_RE.findall(text)}


def _check_pinned_actions(text: str, relative: str, findings: list[str]) -> None:
    for action, ref in _USES_RE.findall(text):
        if action.startswith("./"):
            continue
        if not _SHA_RE.fullmatch(ref):
            findings.append(f"{relative}: action {action} is not pinned to a full commit SHA")


def _check_common(relative: str, text: str, required_jobs: tuple[str, ...], findings: list[str]) -> None:
    if re.search(r"(?m)^\s*pull_request_target\s*:", text):
        findings.append(f"{relative}: pull_request_target is not allowed")
    _check_pinned_actions(text, relative, findings)
    if re.search(r"(?m)^    contents:\s*write\s*$", text):
        findings.append(f"{relative}: contents: write is incorrectly placed at job level")
    jobs = _job_blocks(text)
    for job in required_jobs:
        if job not in jobs:
            findings.append(f"{relative}: required job {job!r} is missing")
    for job, body in jobs.items():
        if job in required_jobs and not re.search(r"(?m)^    timeout-minutes:\s*\d+\s*$", body):
            findings.append(f"{relative}: job {job!r} has no timeout-minutes")


def _check_release_candidate(text: str, findings: list[str]) -> None:
    relative = ".github/workflows/release-candidate.yml"
    if not re.search(r"(?m)^  pull_request:\s*$", text):
        findings.append(f"{relative}: pull_request trigger is missing")
    if not re.search(r"(?m)^  push:\s*$", text) or not re.search(
        r"(?m)^\s+branches:\s*(?:\[\s*main\s*\]|main\s*$)", text
    ):
        findings.append(f"{relative}: main push trigger is missing")
    if re.search(r"(?m)^\s+(?:contents|issues|actions):\s*write\s*$", text):
        findings.append(f"{relative}: release-candidate must not request write permissions")
    forbidden = ("gh release", "git tag", "git push", "issues: write")
    for marker in forbidden:
        if marker in text:
            findings.append(f"{relative}: forbidden publish marker {marker!r} is present")
    required_steps = (
        "Unit tests",
        "Verify",
        "Evals",
        "Workflow static check",
        "Payload digest",
    )
    named_steps = {
        name.strip(): body for name, body in _NAMED_STEP_RE.findall(text)
    }
    for step in required_steps:
        body = named_steps.get(step)
        if body is None:
            findings.append(f"{relative}: required step {step!r} is missing")
            continue
        if not re.search(r"(?m)^\s+run:\s*\S", body):
            findings.append(f"{relative}: required step {step!r} has no executable run")
    payload_body = named_steps.get("Payload digest")
    if payload_body is not None and not re.search(
        r"dist-candidate/template-advanced-[^\s/]+\.digest\.txt", payload_body
    ):
        findings.append(f"{relative}: Payload digest step does not read a candidate digest")
    if "READY_FOR_RELEASE" in text:
        findings.append(f"{relative}: unsupported READY_FOR_RELEASE output is present")


def static_check(root: Path | str) -> dict[str, Any]:
    """Run a bounded targeted check without attempting to parse arbitrary YAML."""

    project_root = Path(root).expanduser().resolve()
    if not project_root.is_dir():
        raise WorkflowCheckError(f"root is not a directory: {root}", code="ROOT_INVALID")
    findings: list[str] = []
    loaded: dict[str, str] = {}
    try:
        for relative, jobs in _REQUIRED_WORKFLOWS.items():
            text = _read_workflow(project_root, relative)
            loaded[relative] = text
            _check_common(relative, text, jobs, findings)
    except WorkflowCheckError as exc:
        return {"status": exc.status, "code": exc.code, "message": str(exc)}
    _check_release_candidate(loaded["release-candidate.yml"], findings)
    if findings:
        return {
            "status": "FAIL",
            "code": "STATIC_CHECK_FAILED",
            "findings": sorted(set(findings)),
            "scope": sorted(_REQUIRED_WORKFLOWS),
        }
    return {
        "status": "STATIC_TARGETED_PASS",
        "code": "STATIC_WORKFLOW_CHECK",
        "scope": sorted(_REQUIRED_WORKFLOWS),
        "findings": [],
    }
