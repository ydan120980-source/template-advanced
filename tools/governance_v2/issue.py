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


def _issue_comments_page_url(repo: str, issue_number: int, page: int) -> str:
    return _issue_comments_url(repo, issue_number) + "?" + urlencode(
        {"per_page": 100, "page": page}
    )


def _fetch_issue_payload(
    *,
    repo: str,
    issue_number: int,
    token: str,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    request = Request(
        _issue_api_url(repo, issue_number),
        headers=_github_headers(token),
        method="GET",
    )
    payload, _ = _open_json(request, timeout=timeout, opener=opener)
    if not isinstance(payload, dict):
        raise IssueCommandError(
            "Issue response is not a JSON object",
            code="REMOTE_RESPONSE_INVALID",
        )
    return payload


def _fetch_issue_comments(
    *,
    repo: str,
    issue_number: int,
    token: str,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for page in range(1, _MAX_ISSUE_SEARCH_PAGES + 1):
        request = Request(
            _issue_comments_page_url(repo, issue_number, page),
            headers=_github_headers(token),
            method="GET",
        )
        payload, headers = _open_json(request, timeout=timeout, opener=opener)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise IssueCommandError(
                "Issue comments response is incomplete",
                code="EVENT_CHAIN_READ_INCOMPLETE",
            )
        if len(payload) > 100:
            raise IssueCommandError(
                "Issue comments response exceeds the requested page size",
                code="EVENT_CHAIN_READ_INCOMPLETE",
            )
        for comment in payload:
            if not isinstance(comment.get("body"), str):
                raise IssueCommandError(
                    "Issue comment response has no string body",
                    code="EVENT_CHAIN_READ_INCOMPLETE",
                )
        comments.extend(payload)
        if _link_has_next(headers) or len(payload) == 100:
            continue
        return comments
    raise IssueCommandError(
        "Issue comments pagination exceeded the safe bound",
        code="EVENT_CHAIN_READ_INCOMPLETE",
    )


def _events_from_comment_body(body: str) -> list[TaskEvent]:
    candidates = re.findall(
        r"```(?:json)?\s*\n?(\{.*?\})\s*```",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not candidates and body.lstrip().startswith("{"):
        candidates = [body.strip()]
    event_candidates: list[TaskEvent] = []
    for candidate in candidates:
        try:
            raw = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        if not any(key in raw for key in ("event_digest", "event_id", "event_type")):
            continue
        try:
            event_candidates.append(TaskEvent.from_dict(raw))
        except (ContractError, TypeError, KeyError) as exc:
            raise IssueCommandError(
                f"Issue event comment is invalid: {exc}",
                code="INVALID_EVENT",
            ) from exc
    if len(event_candidates) > 1:
        raise IssueCommandError(
            "Issue comment contains multiple event objects",
            code="EVENT_COMMENT_AMBIGUOUS",
        )
    return event_candidates


def _events_from_comments(comments: Iterable[dict[str, Any]]) -> list[TaskEvent]:
    events: list[TaskEvent] = []
    for comment in comments:
        events.extend(_events_from_comment_body(comment["body"]))
    return events


def _validate_issue_for_append(
    payload: dict[str, Any],
    *,
    repo: str,
    event: TaskEvent,
) -> TaskContract:
    if payload.get("state") != "open":
        raise IssueCommandError("Task Issue is not open", code="ISSUE_NOT_OPEN")
    if _is_pull_request(payload):
        raise IssueCommandError("Task Issue reference is a Pull Request", code="ISSUE_REFERENCE_IS_PR")
    expected_title = f"[AIWF Task] {event.task_id}"
    if payload.get("title") != expected_title:
        raise IssueCommandError("Task Issue title does not match event task_id", code="ISSUE_TITLE_MISMATCH")
    body = payload.get("body")
    if not isinstance(body, str):
        raise IssueCommandError("Task Issue has no string contract body", code="CONTRACT_READ_FAILED")
    try:
        contract = TaskContract.from_dict(extract_contract(body))
    except (ContractError, IssueCommandError) as exc:
        raise IssueCommandError("Task Issue contract is invalid", code="CONTRACT_READ_FAILED") from exc
    if contract.data["task_id"] != event.task_id:
        raise IssueCommandError("Task Issue contract task_id does not match event", code="EVENT_TASK_MISMATCH")
    if contract.data["repository_id"] != repo:
        raise IssueCommandError("Task Issue contract repository does not match", code="REPOSITORY_CONTRACT_MISMATCH")
    return contract


def _validate_existing_event_chain(
    events: list[TaskEvent],
    *,
    contract: TaskContract,
) -> str | None:
    if not events:
        return None
    report = verify_event_chain(event.to_dict() for event in events)
    if report["status"] != "PASS":
        raise IssueCommandError(
            f"existing Issue event chain is not valid: {report['code']}",
            code=str(report["code"]),
        )
    if any(event.task_id != contract.data["task_id"] for event in events):
        raise IssueCommandError(
            "existing Issue event chain task_id does not match contract",
            code="EVENT_TASK_MISMATCH",
        )
    return events[-1].event_digest


def _validate_event_position(
    event: TaskEvent,
    *,
    existing: list[TaskEvent],
    contract: TaskContract,
) -> None:
    expected_sequence = len(existing) + 1
    if event.sequence != expected_sequence:
        code = "EVENT_CHAIN_GAP" if event.sequence > expected_sequence else "EVENT_CHAIN_OUT_OF_ORDER"
        raise IssueCommandError(
            f"event sequence must be {expected_sequence}",
            code=code,
        )
    expected_previous = existing[-1].event_digest if existing else None
    if event.previous_event_digest != expected_previous:
        raise IssueCommandError(
            "event previous_event_digest does not match the current chain head",
            code="EVENT_PREVIOUS_DIGEST_MISMATCH",
        )
    if event.task_id != contract.data["task_id"]:
        raise IssueCommandError(
            "event task_id does not match the Task Issue contract",
            code="EVENT_TASK_MISMATCH",
        )
    if existing and event.subject_sha != existing[0].subject_sha:
        raise IssueCommandError(
            "event subject_sha does not match the existing chain",
            code="EVENT_SUBJECT_SHA_MISMATCH",
        )
    if not re.fullmatch(r"[0-9a-fA-F]{40}", event.subject_sha):
        raise IssueCommandError(
            "event subject_sha is not a full SHA-1",
            code="INVALID_EVENT_SUBJECT_SHA",
        )


def _validate_comment_readback(
    payload: object,
    *,
    event: TaskEvent,
    body: str,
    comment_url: str,
    actor: str,
) -> dict[str, str | int]:
    if not isinstance(payload, dict):
        raise IssueCommandError("comment readback is not an object", code="EVENT_COMMENT_READBACK_MISMATCH")
    comment_id = payload.get("id")
    if isinstance(comment_id, bool) or not isinstance(comment_id, int) or comment_id < 1:
        raise IssueCommandError("comment readback has no valid id", code="EVENT_COMMENT_READBACK_MISMATCH")
    if payload.get("url") != comment_url or payload.get("body") != body:
        raise IssueCommandError("comment readback URL or body does not match", code="EVENT_COMMENT_READBACK_MISMATCH")
    user = payload.get("user")
    if not isinstance(user, dict) or user.get("login") != actor:
        raise IssueCommandError("comment readback author does not match", code="EVENT_COMMENT_READBACK_MISMATCH")
    html_url = payload.get("html_url")
    if not isinstance(html_url, str) or not html_url.strip():
        raise IssueCommandError("comment readback has no HTML URL", code="EVENT_COMMENT_READBACK_MISMATCH")
    try:
        created_at = payload.get("created_at")
        updated_at = payload.get("updated_at")
        if not isinstance(created_at, str) or not isinstance(updated_at, str):
            raise ValueError
        if datetime.fromisoformat(created_at.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
        if datetime.fromisoformat(updated_at.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise IssueCommandError(
            "comment readback timestamp is invalid",
            code="EVENT_COMMENT_READBACK_MISMATCH",
        ) from exc
    try:
        readback_events = _events_from_comment_body(body)
    except IssueCommandError as exc:
        raise IssueCommandError(
            "comment readback event is invalid",
            code="EVENT_COMMENT_READBACK_MISMATCH",
        ) from exc
    if len(readback_events) != 1 or readback_events[0].to_dict() != event.to_dict():
        raise IssueCommandError("comment readback event digest does not match", code="EVENT_COMMENT_READBACK_MISMATCH")
    return {
        "comment_url": html_url,
        "comment_api_url": comment_url,
        "comment_id": comment_id,
        "server_created_at": created_at,
        "server_updated_at": updated_at,
    }


def append_issue_event(
    *,
    event_path: Path,
    repo: str | None,
    issue_number: int | None,
    issue_url: str | None,
    confirmed: bool,
    timeout: float = 15.0,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Append one event only after a verified pre-read and post-write reread."""

    event_raw = _read_json(event_path)
    try:
        event = TaskEvent.from_dict(event_raw)
    except (ContractError, TypeError, KeyError) as exc:
        raise IssueCommandError(str(exc), status="FAIL", code="INVALID_EVENT") from exc
    require_write_confirmation(confirmed)
    timeout = _validate_timeout(timeout)
    token = _github_token()

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
    _repo_api_root(resolved_repo)
    actor = _authenticated_actor(token=token, timeout=timeout, opener=opener)
    issue_payload = _fetch_issue_payload(
        repo=resolved_repo,
        issue_number=resolved_number,
        token=token,
        timeout=timeout,
        opener=opener,
    )
    contract = _validate_issue_for_append(issue_payload, repo=resolved_repo, event=event)
    comments = _fetch_issue_comments(
        repo=resolved_repo,
        issue_number=resolved_number,
        token=token,
        timeout=timeout,
        opener=opener,
    )
    existing_events = _events_from_comments(comments)
    _validate_existing_event_chain(existing_events, contract=contract)
    _validate_event_position(event, existing=existing_events, contract=contract)
    url = _issue_comments_url(resolved_repo, resolved_number)
    body = "```json\n" + json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    request = Request(
        url,
        data=json.dumps({"body": body}).encode("utf-8"),
        headers=_github_headers(token, content_type=True),
        method="POST",
    )
    payload, _ = _open_json(request, timeout=timeout, opener=opener)
    if not isinstance(payload, dict):
        raise IssueCommandError("GitHub comment response is not a JSON object", code="REMOTE_RESPONSE_INVALID")
    comment_api_url = payload.get("url")
    if not isinstance(comment_api_url, str) or not comment_api_url.strip():
        raise IssueCommandError("GitHub comment response has no API URL", code="REMOTE_RESPONSE_INVALID")
    comment_request = Request(
        comment_api_url,
        headers=_github_headers(token),
        method="GET",
    )
    comment_readback, _ = _open_json(comment_request, timeout=timeout, opener=opener)
    verified_comment = _validate_comment_readback(
        comment_readback,
        event=event,
        body=body,
        comment_url=comment_api_url,
        actor=actor,
    )
    final_issue_payload = _fetch_issue_payload(
        repo=resolved_repo,
        issue_number=resolved_number,
        token=token,
        timeout=timeout,
        opener=opener,
    )
    final_contract = _validate_issue_for_append(final_issue_payload, repo=resolved_repo, event=event)
    final_comments = _fetch_issue_comments(
        repo=resolved_repo,
        issue_number=resolved_number,
        token=token,
        timeout=timeout,
        opener=opener,
    )
    final_events = _events_from_comments(final_comments)
    _validate_existing_event_chain(final_events, contract=final_contract)
    expected_digests = [item.event_digest for item in existing_events] + [event.event_digest]
    if [item.event_digest for item in final_events] != expected_digests:
        raise IssueCommandError(
            "Issue event chain changed during append verification",
            code="EVENT_CHAIN_READBACK_MISMATCH",
        )
    return {
        "status": "PASS",
        "code": "EVENT_APPENDED_AND_VERIFIED",
        "event_digest": event.event_digest,
        "issue_url": _issue_api_url(resolved_repo, resolved_number),
        "comment_url": verified_comment["comment_url"],
        "comment_api_url": verified_comment["comment_api_url"],
        "comment_id": verified_comment["comment_id"],
        "author": actor,
        "server_created_at": verified_comment["server_created_at"],
        "server_updated_at": verified_comment["server_updated_at"],
        "chain_head": final_events[-1].event_digest if final_events else None,
        "remote_writes": True,
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
