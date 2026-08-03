"""Task Issue contract synchronisation and event-chain verification."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .canonical import sha256_canonical
from .models import ContractError, TaskContract, TaskEvent


class IssueCommandError(RuntimeError):
    """A bounded Issue operation could not produce a trustworthy result."""

    def __init__(self, message: str, *, status: str = "BLOCKED", code: str = "OPERATION_FAILED"):
        super().__init__(message)
        self.status = status
        self.code = code


_GITHUB_API_ROOT = "https://api.github.com"
_GITHUB_API_VERSION = "2022-11-28"
_DEFAULT_ISSUE_TIMEOUT = 15.0
_MAX_ISSUE_SEARCH_PAGES = 1000


def _validate_timeout(timeout: float) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise IssueCommandError("timeout must be a finite positive number", code="INVALID_TIMEOUT")
    value = float(timeout)
    if not math.isfinite(value) or value <= 0:
        raise IssueCommandError("timeout must be a finite positive number", code="INVALID_TIMEOUT")
    return value


def _github_token() -> str:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name)
        if value and value.strip():
            return value
    raise IssueCommandError(
        "a GitHub token is required through GH_TOKEN or GITHUB_TOKEN",
        code="AUTH_TOKEN_REQUIRED",
    )


def _github_headers(token: str, *, content_type: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "template-advanced-governance-v2",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }
    if content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _repo_api_root(repo: str) -> str:
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
        raise IssueCommandError("repository must be owner/name", code="INVALID_REPOSITORY")
    return f"{_GITHUB_API_ROOT}/repos/{repo}"


def _response_header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        items = headers.items()
    except (AttributeError, TypeError):
        return None
    for key, value in items:
        if str(key).lower() == name.lower():
            return str(value)
    return None


def _open_json(
    request: Request,
    *,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> tuple[Any, dict[str, str]]:
    """Open one GitHub JSON request without exposing credentials in errors."""

    open_fn = opener or urlopen
    try:
        with open_fn(request, timeout=timeout) as response:
            raw = response.read()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str):
                raise IssueCommandError(
                    "GitHub response body is not text",
                    code="REMOTE_RESPONSE_INVALID",
                )
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise IssueCommandError(
                    "GitHub response is not valid JSON",
                    code="REMOTE_RESPONSE_INVALID",
                ) from exc
            headers: dict[str, str] = {}
            link = _response_header(response, "Link")
            if link is not None:
                headers["Link"] = link
            return payload, headers
    except IssueCommandError:
        raise
    except HTTPError as exc:
        raise IssueCommandError(
            f"GitHub API returned HTTP {exc.code}",
            code="REMOTE_API_ERROR",
        ) from exc
    except (URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise IssueCommandError(
            f"GitHub API unavailable: {type(exc).__name__}",
            code="REMOTE_API_UNAVAILABLE",
        ) from exc


def _link_has_next(headers: dict[str, str]) -> bool:
    link = headers.get("Link")
    if not link:
        return False
    relations = re.findall(r"<[^>]*>\s*;\s*rel=\"?([^\";,\s]+)", link)
    if not relations:
        raise IssueCommandError(
            "Issue search pagination metadata is incomplete",
            code="ISSUE_SEARCH_INCOMPLETE",
        )
    return "next" in relations


def _is_pull_request(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("pull_request") is not None


def _positive_issue_number(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


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


def _issue_search_url(repo: str, page: int) -> str:
    return _repo_api_root(repo) + "/issues?" + urlencode(
        {"state": "all", "per_page": 100, "page": page}
    )


def _authenticated_actor(
    *,
    token: str,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> str:
    request = Request(
        _GITHUB_API_ROOT + "/user",
        headers=_github_headers(token),
        method="GET",
    )
    payload, _ = _open_json(request, timeout=timeout, opener=opener)
    if not isinstance(payload, dict):
        raise IssueCommandError(
            "authenticated-user response is incomplete",
            code="REMOTE_RESPONSE_INVALID",
        )
    user = payload.get("login")
    if not isinstance(user, str) or not user.strip():
        raise IssueCommandError(
            "authenticated-user response has no login",
            code="REMOTE_RESPONSE_INVALID",
        )
    return user


def _search_exact_title(
    *,
    repo: str,
    title: str,
    token: str,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Search every Issue page and return exact-title non-PR matches."""

    matches: list[dict[str, Any]] = []
    for page in range(1, _MAX_ISSUE_SEARCH_PAGES + 1):
        request = Request(
            _issue_search_url(repo, page),
            headers=_github_headers(token),
            method="GET",
        )
        payload, headers = _open_json(request, timeout=timeout, opener=opener)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise IssueCommandError(
                "Issue search response is incomplete",
                code="ISSUE_SEARCH_INCOMPLETE",
            )
        if len(payload) > 100:
            raise IssueCommandError(
                "Issue search response exceeds the requested page size",
                code="ISSUE_SEARCH_INCOMPLETE",
            )
        matches.extend(
            item
            for item in payload
            if item.get("title") == title and not _is_pull_request(item)
        )
        if _link_has_next(headers) or len(payload) == 100:
            continue
        return matches
    raise IssueCommandError(
        "Issue search exceeded the safe pagination bound",
        code="ISSUE_SEARCH_INCOMPLETE",
    )


def _contract_matches_issue(payload: dict[str, Any], expected: TaskContract) -> bool:
    body = payload.get("body")
    if not isinstance(body, str):
        return False
    try:
        actual = TaskContract.from_dict(extract_contract(body))
    except (ContractError, IssueCommandError):
        return False
    return actual.to_dict() == expected.to_dict()


def _issue_body(contract: TaskContract) -> str:
    contract_json = json.dumps(
        contract.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    return (
        "# Task Contract\n\n"
        "```json\n"
        f"{contract_json}\n"
        "```\n\n"
        "## Bootstrap provenance\n\n"
        "* Created by: `python -m tools.governance_v2 issue create`\n"
        "* Creation requires explicit `--confirm-write`.\n"
        "* This Issue does not retroactively authorize commits created before its contract.\n"
    )


def _parse_server_timestamp(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise IssueCommandError(
            "Issue readback timestamp is missing",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IssueCommandError(
            "Issue readback timestamp is invalid",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        ) from exc
    if parsed.tzinfo is None:
        raise IssueCommandError(
            "Issue readback timestamp has no timezone",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    return value


def _validate_issue_readback(
    payload: object,
    *,
    repo: str,
    issue_number: int,
    title: str,
    contract: TaskContract,
    actor: str,
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise IssueCommandError(
            "Issue readback is not an object",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    if _positive_issue_number(payload.get("number")) != issue_number:
        raise IssueCommandError(
            "Issue readback number does not match",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    if payload.get("title") != title:
        raise IssueCommandError(
            "Issue readback title does not match",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    if payload.get("state") != "open":
        raise IssueCommandError(
            "Issue readback is not open",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    if _is_pull_request(payload):
        raise IssueCommandError(
            "Issue readback is a Pull Request",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )

    body = payload.get("body")
    if not isinstance(body, str) or not _contract_matches_issue(payload, contract):
        raise IssueCommandError(
            "Issue readback contract does not match",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )

    user = payload.get("user")
    if not isinstance(user, dict) or user.get("login") != actor:
        raise IssueCommandError(
            "Issue readback author does not match authenticated actor",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )

    expected_api_url = _issue_api_url(repo, issue_number)
    expected_html_url = f"https://github.com/{repo}/issues/{issue_number}"
    if payload.get("url") != expected_api_url:
        raise IssueCommandError(
            "Issue readback API URL does not match",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    if payload.get("html_url") != expected_html_url:
        raise IssueCommandError(
            "Issue readback HTML URL does not match",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )

    repository_evidence: list[str] = []
    repository_url = payload.get("repository_url")
    if isinstance(repository_url, str):
        repository_evidence.append(repository_url)
    repository = payload.get("repository")
    if isinstance(repository, dict) and isinstance(repository.get("full_name"), str):
        repository_evidence.append(repository["full_name"])
    if not repository_evidence or any(
        value not in {repo, _repo_api_root(repo)} for value in repository_evidence
    ):
        raise IssueCommandError(
            "Issue readback repository does not match",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )

    created_at = _parse_server_timestamp(payload, "created_at")
    updated_at = _parse_server_timestamp(payload, "updated_at")
    return {
        "issue_url": expected_html_url,
        "api_url": expected_api_url,
        "author": actor,
        "server_created_at": created_at,
        "server_updated_at": updated_at,
    }


def create_issue(
    *,
    contract_path: Path,
    repo: str,
    title: str,
    confirmed: bool,
    timeout: float = _DEFAULT_ISSUE_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Create one Task Issue safely, or verify an identical existing Issue."""

    timeout = _validate_timeout(timeout)
    try:
        contract = load_contract(contract_path)
    except IssueCommandError as exc:
        # The create command's machine-readable result must never disclose a
        # workstation path, even when the local input cannot be read.
        if exc.code in {"READ_FAILED", "INVALID_JSON"}:
            raise IssueCommandError(
                "contract input could not be read or parsed",
                status=exc.status,
                code=exc.code,
            ) from exc
        raise
    task_id = contract.data["task_id"]
    if task_id == "GOV-V2-BOOTSTRAP":
        raise IssueCommandError(
            "the bootstrap Issue is never created by this command",
            code="BOOTSTRAP_ISSUE_SELF_CREATION_FORBIDDEN",
        )
    _repo_api_root(repo)
    if contract.data["repository_id"] != repo:
        raise IssueCommandError(
            "contract repository_id does not match --repo",
            code="REPOSITORY_CONTRACT_MISMATCH",
        )
    if not isinstance(title, str) or not title.strip():
        raise IssueCommandError("title is required", code="INVALID_TITLE")
    expected_title = f"[AIWF Task] {task_id}"
    if title != expected_title:
        raise IssueCommandError(
            "title must equal [AIWF Task] plus task_id",
            code="INVALID_TITLE",
        )
    require_write_confirmation(confirmed)
    token = _github_token()
    body = _issue_body(contract)
    actor = _authenticated_actor(token=token, timeout=timeout, opener=opener)
    matches = _search_exact_title(
        repo=repo,
        title=title,
        token=token,
        timeout=timeout,
        opener=opener,
    )
    if len(matches) > 1:
        raise IssueCommandError(
            "more than one exact-title Issue exists",
            code="ISSUE_TITLE_AMBIGUOUS",
        )

    created = False
    if matches:
        existing = matches[0]
        if not _contract_matches_issue(existing, contract):
            raise IssueCommandError(
                "an exact-title Issue has a different contract",
                code="ISSUE_CONTRACT_CONFLICT",
            )
        issue_number = _positive_issue_number(existing.get("number"))
        if issue_number is None:
            raise IssueCommandError(
                "exact-title Issue has no valid number",
                code="ISSUE_SEARCH_INCOMPLETE",
            )
        result_code = "ISSUE_ALREADY_EXISTS"
    else:
        request = Request(
            _repo_api_root(repo) + "/issues",
            data=json.dumps(
                {"title": title, "body": body},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers=_github_headers(token, content_type=True),
            method="POST",
        )
        payload, _ = _open_json(request, timeout=timeout, opener=opener)
        if not isinstance(payload, dict):
            raise IssueCommandError(
                "Issue create response is not an object",
                code="ISSUE_CREATE_FAILED",
            )
        issue_number = _positive_issue_number(payload.get("number"))
        if issue_number is None:
            raise IssueCommandError(
                "Issue create response has no valid number",
                code="ISSUE_CREATE_FAILED",
            )
        result_code = "ISSUE_CREATED_AND_VERIFIED"
        created = True

    read_request = Request(
        _issue_api_url(repo, issue_number),
        headers=_github_headers(token),
        method="GET",
    )
    read_payload, _ = _open_json(read_request, timeout=timeout, opener=opener)
    verified = _validate_issue_readback(
        read_payload,
        repo=repo,
        issue_number=issue_number,
        title=title,
        contract=contract,
        actor=actor,
    )
    final_matches = _search_exact_title(
        repo=repo,
        title=title,
        token=token,
        timeout=timeout,
        opener=opener,
    )
    if len(final_matches) != 1 or _positive_issue_number(final_matches[0].get("number")) != issue_number:
        raise IssueCommandError(
            "post-write exact-title search does not identify the verified Issue",
            code="ISSUE_CREATE_READBACK_MISMATCH",
        )
    return {
        "status": "PASS",
        "code": result_code,
        "created": created,
        "repository": repo,
        "issue_number": issue_number,
        "issue_url": verified["issue_url"],
        "api_url": verified["api_url"],
        "title": title,
        "task_id": task_id,
        "contract_digest": contract.digest,
        "author": verified["author"],
        "server_created_at": verified["server_created_at"],
        "server_updated_at": verified["server_updated_at"],
        "duplicate_count": len(final_matches),
        "remote_writes": created,
    }


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
    cache: Path | None = None,
    repo: str | None = None,
    issue_number: int | None = None,
    issue_url: str | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Read, verify, and optionally cache a TaskContract without writing GitHub."""

    if cache is not None:
        cached = _read_json(cache)
        raw_cached = cached.get("contract", cached)
        if not isinstance(raw_cached, dict):
            raise IssueCommandError(
                "validated cache has no contract object",
                status="FAIL",
                code="CACHE_INVALID",
            )
        report = verify_contract(raw_cached)
        if report["status"] != "PASS":
            raise IssueCommandError(
                "validated cache contract is invalid",
                status="FAIL",
                code="CACHE_INVALID",
            )
        return {
            "status": "CACHED",
            "code": "VALIDATED_CACHE",
            "source": "cache",
            "cache_path": str(cache),
            "contract": raw_cached,
            "contract_digest": report["contract_digest"],
        }

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


def init_contract(*, contract_path: Path, output: Path | None = None) -> dict[str, Any]:
    """Validate a local TaskContract and optionally write a local seed cache."""

    contract = load_contract(contract_path)
    result: dict[str, Any] = {
        "status": "PASS",
        "code": "CONTRACT_INITIALIZED",
        "source": str(contract_path),
        "contract": contract.to_dict(),
        "contract_digest": contract.digest,
    }
    if output is not None:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, UnicodeError) as exc:
            raise IssueCommandError(
                f"cannot write contract cache {output}: {type(exc).__name__}",
                code="CACHE_WRITE_FAILED",
            ) from exc
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


def _issue_comments_url(repo: str, issue_number: int) -> str:
    return _issue_api_url(repo, issue_number) + "/comments"


def append_issue_event(
    *,
    event_path: Path,
    repo: str | None,
    issue_number: int | None,
    issue_url: str | None,
    confirmed: bool,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Append one validated event as an Issue comment after explicit confirmation."""

    event_raw = _read_json(event_path)
    try:
        event = TaskEvent.from_dict(event_raw)
    except (ContractError, TypeError, KeyError) as exc:
        raise IssueCommandError(str(exc), status="FAIL", code="INVALID_EVENT") from exc
    require_write_confirmation(confirmed)

    resolved_repo = repo
    resolved_number = issue_number
    if issue_url:
        parsed = urlparse(issue_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 4 or parts[0] != "repos":
            raise IssueCommandError("issue_url must be a GitHub API Issue URL", code="INVALID_ISSUE_URL")
        resolved_repo = f"{parts[1]}/{parts[2]}"
        try:
            resolved_number = int(parts[3])
        except ValueError as exc:
            raise IssueCommandError("issue_url has an invalid issue number", code="INVALID_ISSUE_URL") from exc
    if not resolved_repo or resolved_number is None:
        raise IssueCommandError(
            "provide --repo with --issue-number or --issue-url",
            code="INPUT_REQUIRED",
        )
    url = _issue_comments_url(resolved_repo, resolved_number)
    body = "```json\n" + json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    request = Request(
        url,
        data=json.dumps({"body": body}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "template-advanced-governance-v2",
            **(
                {"Authorization": f"Bearer {token}"}
                if (token := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
                else {}
            ),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise IssueCommandError(f"GitHub API returned HTTP {exc.code}", code="REMOTE_API_ERROR") from exc
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IssueCommandError(f"GitHub API unavailable: {type(exc).__name__}", code="REMOTE_API_UNAVAILABLE") from exc
    if not isinstance(payload, dict):
        raise IssueCommandError("GitHub response is not a JSON object", code="REMOTE_RESPONSE_INVALID")
    return {
        "status": "PASS",
        "code": "EVENT_APPENDED",
        "event_digest": event.event_digest,
        "issue_url": issue_url or _issue_api_url(resolved_repo, resolved_number),
        "comment_url": payload.get("html_url") or payload.get("url"),
    }


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
    subject_sha = parsed[0].subject_sha
    for event in parsed:
        if event.sequence != expected_sequence:
            code = "EVENT_CHAIN_GAP" if event.sequence > expected_sequence else "EVENT_CHAIN_OUT_OF_ORDER"
            return {"status": "FAIL", "code": code, "events": len(parsed), "sequence": event.sequence}
        if event.task_id != task_id:
            return {"status": "FAIL", "code": "EVENT_TASK_MISMATCH", "events": len(parsed), "sequence": event.sequence}
        if event.subject_sha != subject_sha:
            return {
                "status": "FAIL",
                "code": "EVENT_SUBJECT_SHA_MISMATCH",
                "events": len(parsed),
                "sequence": event.sequence,
            }
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


def load_event_chain(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array of Issue events from a local cache file."""

    try:
        value = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise IssueCommandError(
            f"invalid event chain in {path}: {exc.msg}",
            status="FAIL",
            code="INVALID_EVENT_CHAIN",
        ) from exc
    if not isinstance(value, list):
        raise IssueCommandError(
            "event chain cache must be a JSON array",
            status="FAIL",
            code="INVALID_EVENT_CHAIN",
        )
    return value
