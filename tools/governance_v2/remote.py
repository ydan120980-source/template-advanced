"""Read-only GitHub Actions Remote Gate checks for exact commit evidence."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class RemoteGateError(RuntimeError):
    """A remote gate input or API response cannot be trusted."""

    def __init__(self, message: str, *, status: str = "BLOCKED", code: str = "REMOTE_GATE_FAILED"):
        super().__init__(message)
        self.status = status
        self.code = code


def _repo_path(repo: str, suffix: str) -> str:
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
        raise RemoteGateError("repository must be owner/name", code="INVALID_REPOSITORY")
    return f"https://api.github.com/repos/{repo}/{suffix.lstrip('/')}"


def _get_json(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "template-advanced-governance-v2",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RemoteGateError(f"GitHub API returned HTTP {exc.code}", code="REMOTE_API_ERROR") from exc
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RemoteGateError(
            f"GitHub API unavailable: {type(exc).__name__}",
            code="REMOTE_API_UNAVAILABLE",
        ) from exc
    if not isinstance(value, dict):
        raise RemoteGateError("GitHub response must be a JSON object", code="REMOTE_RESPONSE_INVALID")
    return value


def _read_fixture(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RemoteGateError(
            f"invalid Remote Gate fixture: {type(exc).__name__}",
            status="FAIL",
            code="FIXTURE_INVALID",
        ) from exc
    if not isinstance(value, dict):
        raise RemoteGateError("Remote Gate fixture must be a JSON object", status="FAIL", code="FIXTURE_INVALID")
    return value


def _items(value: object, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        raise RemoteGateError(f"Remote response has no list: {key}", code="REMOTE_RESPONSE_INVALID")
    items = value[key]
    if not all(isinstance(item, dict) for item in items):
        raise RemoteGateError(f"Remote response list is invalid: {key}", code="REMOTE_RESPONSE_INVALID")
    return items


def _workflow_path_matches(value: object, workflow: str) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.replace("\\", "/")
    return normalized == workflow or normalized.endswith("/" + workflow)


def gate_github(
    *,
    repo: str,
    sha: str,
    workflow: str,
    check_name: str,
    app_id: int | None = None,
    fixture: Path | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Verify successful non-empty Actions evidence without any remote write."""

    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        return {"status": "BLOCKED", "code": "INVALID_SHA", "message": "sha must be a full commit SHA"}
    if not workflow or not check_name:
        return {"status": "BLOCKED", "code": "INPUT_REQUIRED", "message": "workflow and check-name are required"}
    try:
        if fixture is not None:
            source = _read_fixture(fixture)
            workflow_payload = source.get("workflow")
            runs_payload = {"workflow_runs": source.get("workflow_runs")}
            jobs_payload = {"jobs": source.get("jobs")}
            checks_payload = {"check_runs": source.get("check_runs")}
        else:
            encoded_workflow = quote(workflow, safe="")
            workflow_payload = _get_json(
                _repo_path(repo, f"actions/workflows/{encoded_workflow}"),
                timeout=timeout,
            )
            query = urlencode({"head_sha": sha, "per_page": "100"})
            runs_payload = _get_json(
                _repo_path(repo, f"actions/workflows/{encoded_workflow}/runs?{query}"),
                timeout=timeout,
            )
            runs = _items(runs_payload, "workflow_runs")
            if any("head_sha" not in run or "path" not in run for run in runs):
                return {
                    "status": "BLOCKED",
                    "code": "WORKFLOW_RUN_RESPONSE_INCOMPLETE",
                    "message": "workflow run evidence lacks head_sha or path",
                    "remote_writes": False,
                }
            matching_run = next(
                (run for run in runs if run.get("head_sha") == sha and _workflow_path_matches(run.get("path"), workflow)),
                None,
            )
            if matching_run is None or not isinstance(matching_run.get("id"), int):
                return {"status": "FAIL", "code": "WORKFLOW_RUN_NOT_FOUND", "sha": sha, "workflow": workflow}
            jobs_payload = _get_json(
                _repo_path(repo, f"actions/runs/{matching_run['id']}/jobs?per_page=100"),
                timeout=timeout,
            )
            checks_payload = _get_json(
                _repo_path(repo, f"commits/{sha}/check-runs?per_page=100"),
                timeout=timeout,
            )
        runs = _items(runs_payload, "workflow_runs")
        if any("head_sha" not in run or "path" not in run for run in runs):
            return {
                "status": "BLOCKED",
                "code": "WORKFLOW_RUN_RESPONSE_INCOMPLETE",
                "message": "workflow run evidence lacks head_sha or path",
                "remote_writes": False,
            }
        matching_runs = [
            run for run in runs
            if run.get("head_sha") == sha and _workflow_path_matches(run.get("path"), workflow)
        ]
        if not matching_runs:
                return {"status": "FAIL", "code": "WORKFLOW_RUN_NOT_FOUND", "sha": sha, "workflow": workflow}
        if not isinstance(workflow_payload, dict):
            return {
                "status": "BLOCKED",
                "code": "WORKFLOW_RESPONSE_INCOMPLETE",
                "message": "workflow metadata is missing or invalid",
                "remote_writes": False,
            }
        workflow_state = workflow_payload.get("state")
        if not isinstance(workflow_state, str):
            return {
                "status": "BLOCKED",
                "code": "WORKFLOW_STATE_MISSING",
                "message": "workflow metadata has no state",
                "remote_writes": False,
            }
        if workflow_state != "active":
            return {
                "status": "FAIL",
                "code": "WORKFLOW_NOT_ACTIVE",
                "workflow": workflow,
                "workflow_state": workflow_state,
                "remote_writes": False,
            }
        run = matching_runs[0]
        if not isinstance(run.get("status"), str) or not isinstance(run.get("conclusion"), str):
            return {
                "status": "BLOCKED",
                "code": "WORKFLOW_RUN_RESPONSE_INCOMPLETE",
                "message": "workflow run evidence lacks status or conclusion",
                "remote_writes": False,
            }
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            return {
                "status": "FAIL",
                "code": "WORKFLOW_RUN_NOT_SUCCESS",
                "sha": sha,
                "workflow": workflow,
                "run_status": run.get("status"),
                "conclusion": run.get("conclusion"),
            }
        jobs = _items(jobs_payload, "jobs")
        if not jobs:
            return {"status": "FAIL", "code": "JOBS_EMPTY", "sha": sha, "workflow": workflow}
        if any(not isinstance(job.get("conclusion"), str) for job in jobs):
            return {
                "status": "BLOCKED",
                "code": "JOBS_RESPONSE_INCOMPLETE",
                "message": "job evidence lacks conclusion",
                "remote_writes": False,
            }
        bad_jobs = [job.get("name") for job in jobs if job.get("conclusion") != "success"]
        if bad_jobs:
            return {"status": "FAIL", "code": "JOBS_NOT_SUCCESS", "jobs": bad_jobs, "sha": sha}
        check_runs = _items(checks_payload, "check_runs")
        matches = [check for check in check_runs if check.get("name") == check_name]
        if not matches:
            return {"status": "FAIL", "code": "CHECK_RUN_NOT_FOUND", "check_name": check_name, "sha": sha}
        check = matches[0]
        if not all(isinstance(check.get(key), str) for key in ("head_sha", "status", "conclusion")):
            return {
                "status": "BLOCKED",
                "code": "CHECK_RESPONSE_INCOMPLETE",
                "message": "check-run evidence lacks head_sha, status, or conclusion",
                "remote_writes": False,
            }
        if check.get("head_sha") != sha:
            return {"status": "FAIL", "code": "CHECK_SHA_MISMATCH", "check_name": check_name, "sha": sha}
        if check.get("status") != "completed" or check.get("conclusion") != "success":
            return {
                "status": "FAIL",
                "code": "CHECK_NOT_SUCCESS",
                "check_name": check_name,
                "sha": sha,
                "conclusion": check.get("conclusion"),
            }
        if app_id is not None:
            app = check.get("app")
            if not isinstance(app, dict) or "id" not in app:
                return {
                    "status": "BLOCKED",
                    "code": "CHECK_APP_RESPONSE_INCOMPLETE",
                    "message": "check-run evidence lacks app id",
                    "remote_writes": False,
                }
            if app.get("id") != app_id:
                return {
                    "status": "FAIL",
                    "code": "CHECK_APP_MISMATCH",
                    "check_name": check_name,
                    "expected_app_id": app_id,
                    "actual_app_id": app.get("id") if isinstance(app, dict) else None,
                }
        return {
            "status": "PASS",
            "code": "REMOTE_GATE_PASS",
            "sha": sha,
            "workflow": workflow,
            "check_name": check_name,
            "job_count": len(jobs),
            "remote_writes": False,
        }
    except RemoteGateError as exc:
        return {"status": exc.status, "code": exc.code, "message": str(exc), "remote_writes": False}
