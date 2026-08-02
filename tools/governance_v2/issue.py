"""Task Issue contract synchronisation and event-chain verification."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .canonical import sha256_canonical
from .models import ContractError, TaskContract, TaskEvent


class IssueCommandError(RuntimeError):
    """A bounded Issue operation could not produce a trustworthy result."""

    def __init__(self, message: str, *, status: str = "BLOCKED", code: str = "OPERATION_FAILED"):
        super().__init__(message)
        self.status = status
        self.code = code


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise IssueCommandError(f"cannot read {path}: {type(exc).__name__}", code="READ_FAILED") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise IssueCommandError(f"invalid JSON in {path}: {exc.msg}", status="FAIL", code="INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise IssueCommandError("JSON input must be an object", status="FAIL", code="INVALID_JSON")
    return value


def extract_contract(body: str) -> dict[str, Any]:
    """Extract the first governance contract JSON object from an Issue body."""

    candidates = re.findall(r"```(?:json)?\s*\n?(\{.*?\})\s*```", body, flags=re.IGNORECASE | re.DOTALL)
    candidates.append(body.strip())
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("schema_version") == "governance.task/v2":
            return value
    raise IssueCommandError(
        "no governance.task/v2 JSON contract found in Issue body",
        status="FAIL",
        code="CONTRACT_NOT_FOUND",
    )


def load_contract(path: Path) -> TaskContract:
    """Load either a JSON contract file or a Markdown Issue body."""

    if path.suffix.lower() in {".md", ".markdown", ".txt"}:
        raw = extract_contract(_read_text(path))
    else:
        raw = _read_json(path)
    try:
        return TaskContract.from_dict(raw)
    except ContractError as exc:
        raise IssueCommandError(str(exc), status="FAIL", code="INVALID_CONTRACT") from exc


def verify_contract(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw contract and return a deterministic PASS report."""

    try:
        contract = TaskContract.from_dict(raw)
    except ContractError as exc:
        return {"status": "FAIL", "code": "INVALID_CONTRACT", "message": str(exc)}
    return {
        "status": "PASS",
        "code": "CONTRACT_VALID",
        "task_id": contract.data["task_id"],
        "repository_id": contract.data["repository_id"],
        "base_sha": contract.data["base_sha"],
        "contract_digest": contract.digest,
    }


def _issue_api_url(repo: str, issue_number: int) -> str:
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
        raise IssueCommandError("repository must be owner/name", code="INVALID_REPOSITORY")
    if issue_number < 1:
        raise IssueCommandError("issue number must be positive", code="INVALID_ISSUE_NUMBER")
    return f"https://api.github.com/repos/{repo}/issues/{issue_number}"


def fetch_issue_body(*, repo: str, issue_number: int, timeout: float = 15.0) -> tuple[str, str]:
    """Fetch an Issue body through the read-only GitHub REST API."""

    url = _issue_api_url(repo, issue_number)
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "template-advanced-governance-v2",
            **(
                {"Authorization": f"Bearer {token}"}
                if (token := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
                else {}
            ),
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise IssueCommandError(f"GitHub API returned HTTP {exc.code}", code="REMOTE_API_ERROR") from exc
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IssueCommandError(f"GitHub API unavailable: {type(exc).__name__}", code="REMOTE_API_UNAVAILABLE") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("body"), str):
        raise IssueCommandError("GitHub response has no string Issue body", code="REMOTE_RESPONSE_INVALID")
    return payload["body"], url


def sync_contract(
    *,
    body: str | None = None,
    body_file: Path | None = None,
    repo: str | None = None,
    issue_number: int | None = None,
    issue_url: str | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Read, verify, and optionally cache a TaskContract without writing GitHub."""

    source = "provided_body"
    resolved_url = issue_url
    if body is None and body_file is not None:
        body = _read_text(body_file)
        source = "body_file"
    if body is None:
        if issue_url:
            parsed = urlparse(issue_url)
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) < 4 or parts[0] != "repos":
                raise IssueCommandError("issue_url must be a GitHub API Issue URL", code="INVALID_ISSUE_URL")
            repo = f"{parts[1]}/{parts[2]}"
            try:
                issue_number = int(parts[3])
            except ValueError as exc:
                raise IssueCommandError("issue_url has an invalid issue number", code="INVALID_ISSUE_URL") from exc
        if not repo or issue_number is None:
            raise IssueCommandError(
                "provide --body-file, --issue-url, or --repo with --issue-number",
                code="INPUT_REQUIRED",
            )
        body, resolved_url = fetch_issue_body(repo=repo, issue_number=issue_number)
        source = "github_api"
    raw = extract_contract(body)
    report = verify_contract(raw)
    if report["status"] != "PASS":
        raise IssueCommandError(report["message"], status="FAIL", code=report["code"])
    result: dict[str, Any] = {
        "status": "PASS",
        "code": "CONTRACT_SYNCED",
        "source": source,
        "issue_url": resolved_url,
        "issue_number": issue_number,
        "repository": repo,
        "synced_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "contract": raw,
    }
    if output is not None:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise IssueCommandError(f"cannot write cache {output}: {type(exc).__name__}", code="CACHE_WRITE_FAILED") from exc
        result["cache_path"] = str(output)
    return result


def require_write_confirmation(confirmed: bool) -> None:
    """Reject a future Issue mutation unless explicit confirmation is present."""

    if not confirmed:
        raise IssueCommandError(
            "remote Issue writes require explicit --confirm-write",
            status="BLOCKED",
            code="CONFIRM_WRITE_REQUIRED",
        )


def verify_event_chain(events: Iterable[dict[str, Any] | TaskEvent]) -> dict[str, Any]:
    """Verify event ordering, digests, and predecessor uniqueness."""

    raw_events = [event.to_dict() if isinstance(event, TaskEvent) else event for event in events]
    if not raw_events:
        return {"status": "FAIL", "code": "EMPTY_EVENT_CHAIN", "events": 0}
    parsed: list[TaskEvent] = []
    try:
        parsed = [TaskEvent.from_dict(item) for item in raw_events]
    except (ContractError, TypeError, KeyError) as exc:
        return {"status": "FAIL", "code": "INVALID_EVENT", "message": str(exc), "events": len(raw_events)}
    successors: dict[str | None, list[str]] = {}
    for event in parsed:
        successors.setdefault(event.previous_event_digest, []).append(event.event_digest)
    forks = [key for key, values in successors.items() if len(set(values)) > 1]
    if forks:
        return {"status": "FAIL", "code": "EVENT_CHAIN_FORK", "events": len(parsed)}
    expected_sequence = 1
    previous_digest: str | None = None
    task_id = parsed[0].task_id
    for event in parsed:
        if event.sequence != expected_sequence:
            code = "EVENT_CHAIN_GAP" if event.sequence > expected_sequence else "EVENT_CHAIN_OUT_OF_ORDER"
            return {"status": "FAIL", "code": code, "events": len(parsed), "sequence": event.sequence}
        if event.task_id != task_id:
            return {"status": "FAIL", "code": "EVENT_TASK_MISMATCH", "events": len(parsed), "sequence": event.sequence}
        if event.previous_event_digest != previous_digest:
            return {"status": "FAIL", "code": "EVENT_PREVIOUS_DIGEST_MISMATCH", "events": len(parsed), "sequence": event.sequence}
        previous_digest = event.event_digest
        expected_sequence += 1
    return {
        "status": "PASS",
        "code": "EVENT_CHAIN_VALID",
        "events": len(parsed),
        "chain_head": parsed[-1].event_digest,
    }


def event_digest(raw: dict[str, Any]) -> str:
    """Return the digest for an event object without its event_digest field."""

    value = dict(raw)
    value.pop("event_digest", None)
    return sha256_canonical(value)
