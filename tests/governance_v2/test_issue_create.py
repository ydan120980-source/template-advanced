"""Safe Issue creation tests using an in-memory HTTP transport."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from tools.governance_v2.__main__ import main
from tools.governance_v2.canonical import sha256_canonical
from tools.governance_v2.issue import (
    IssueCommandError,
    _issue_body,
    create_issue,
)
from tools.governance_v2.models import TaskContract


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FIXTURE = ROOT / "tests" / "governance_v2" / "fixtures" / "bootstrap-contract.json"
REPOSITORY = "owner/repository"
TOKEN = "test-token-that-must-never-be-printed"
ACTOR = "test-actor"
TITLE = "[AIWF Task] GOV-V2-TEST"


class FakeResponse:
    def __init__(self, payload: object, *, headers: dict[str, str] | None = None, raw: bool = False) -> None:
        self.headers = headers or {}
        if raw:
            self._data = str(payload).encode("utf-8")
        else:
            self._data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


class FakeOpener:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[object, float]] = []

    def __call__(self, request: object, *, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError("fake opener received an unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if not isinstance(response, FakeResponse):
            raise AssertionError("fake response has an invalid type")
        return response


def make_contract(*, task_id: str = "GOV-V2-TEST", goal: str = "test goal") -> TaskContract:
    raw = {
        "schema_version": "governance.task/v2",
        "task_id": task_id,
        "task_type": "test_task",
        "repository_id": REPOSITORY,
        "base_sha": "a" * 40,
        "goal": goal,
        "allowed_paths": ["tools/governance_v2/**"],
        "forbidden_paths": [".git/**"],
        "acceptance": ["the contract is verified"],
    }
    raw["contract_digest"] = sha256_canonical(raw)
    return TaskContract.from_dict(raw)


def write_contract(directory: Path, contract: TaskContract) -> Path:
    path = directory / "contract.json"
    path.write_text(json.dumps(contract.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def issue_payload(
    contract: TaskContract,
    *,
    number: int = 7,
    title: str = TITLE,
    actor: str = ACTOR,
    repository: str = REPOSITORY,
) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "state": "open",
        "body": _issue_body(contract),
        "user": {"login": actor},
        "repository_url": f"https://api.github.com/repos/{repository}",
        "url": f"https://api.github.com/repos/{repository}/issues/{number}",
        "html_url": f"https://github.com/{repository}/issues/{number}",
        "created_at": "2026-08-03T00:00:00Z",
        "updated_at": "2026-08-03T00:00:01Z",
    }


def create_responses(
    contract: TaskContract,
    *,
    readback: dict[str, object] | None = None,
    initial_items: list[dict[str, object]] | None = None,
    final_items: list[dict[str, object]] | None = None,
    number: int = 7,
) -> list[FakeResponse]:
    readback = readback or issue_payload(contract, number=number)
    items = initial_items if initial_items is not None else []
    final = final_items if final_items is not None else [issue_payload(contract, number=number)]
    return [
        FakeResponse({"login": ACTOR}),
        FakeResponse(items),
        FakeResponse({"number": number}),
        FakeResponse(readback),
        FakeResponse(final),
    ]


class IssueCreateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = make_contract()

    def call_create(self, opener: FakeOpener, *, confirmed: bool = True, **kwargs: object) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                return create_issue(
                    contract_path=path,
                    repo=REPOSITORY,
                    title=TITLE,
                    confirmed=confirmed,
                    opener=opener,
                    **kwargs,
                )

    def test_confirmation_is_checked_before_network(self) -> None:
        opener = FakeOpener([])
        with self.assertRaisesRegex(IssueCommandError, "confirm-write") as raised:
            self.call_create(opener, confirmed=False)
        self.assertEqual(raised.exception.code, "CONFIRM_WRITE_REQUIRED")
        self.assertEqual(opener.requests, [])

    def test_token_is_required_before_network(self) -> None:
        opener = FakeOpener([])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo=REPOSITORY,
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "AUTH_TOKEN_REQUIRED")
        self.assertEqual(opener.requests, [])

    def test_invalid_digest_is_rejected_before_network(self) -> None:
        opener = FakeOpener([])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["contract_digest"] = "0" * 64
            path.write_text(json.dumps(raw), encoding="utf-8")
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo=REPOSITORY,
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "INVALID_CONTRACT")
        self.assertEqual(opener.requests, [])

    def test_repository_mismatch_is_rejected_before_network(self) -> None:
        opener = FakeOpener([])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo="other/repository",
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "REPOSITORY_CONTRACT_MISMATCH")
        self.assertEqual(opener.requests, [])

    def test_bootstrap_self_creation_is_forbidden(self) -> None:
        opener = FakeOpener([])
        with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
            with self.assertRaises(IssueCommandError) as raised:
                create_issue(
                    contract_path=BOOTSTRAP_FIXTURE,
                    repo="ydan120980-source/template-advanced",
                    title="[AIWF Task] GOV-V2-BOOTSTRAP",
                    confirmed=True,
                    opener=opener,
                )
        self.assertEqual(raised.exception.code, "BOOTSTRAP_ISSUE_SELF_CREATION_FORBIDDEN")
        self.assertEqual(opener.requests, [])

    def test_missing_title_or_implicit_repository_is_not_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo=REPOSITORY,
                        title="not-the-task-title",
                        confirmed=True,
                        opener=FakeOpener([]),
                    )
        self.assertEqual(raised.exception.code, "INVALID_TITLE")

    def test_create_posts_only_title_and_body_and_verifies_readback(self) -> None:
        opener = FakeOpener(create_responses(self.contract))
        result = self.call_create(opener)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["code"], "ISSUE_CREATED_AND_VERIFIED")
        self.assertTrue(result["created"])
        self.assertEqual(result["duplicate_count"], 1)
        self.assertTrue(result["remote_writes"])
        self.assertEqual(result["author"], ACTOR)
        self.assertEqual(
            [request.get_method() for request, _ in opener.requests],
            ["GET", "GET", "POST", "GET", "GET"],
        )
        post_request = opener.requests[2][0]
        posted = json.loads(post_request.data.decode("utf-8"))
        self.assertEqual(set(posted), {"title", "body"})
        self.assertEqual(posted["title"], TITLE)
        self.assertEqual(post_request.get_header("Authorization"), f"Bearer {TOKEN}")
        headers = {key.lower(): value for key, value in post_request.header_items()}
        self.assertEqual(headers["x-github-api-version"], "2022-11-28")
        self.assertIn("# Task Contract", posted["body"])
        self.assertIn("## Bootstrap provenance", posted["body"])
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_pull_requests_are_excluded_from_exact_issue_matching(self) -> None:
        pull_request = issue_payload(self.contract, number=6)
        pull_request["pull_request"] = {"url": "https://api.github.com/repos/owner/repository/pulls/6"}
        opener = FakeOpener(create_responses(self.contract, initial_items=[pull_request]))
        result = self.call_create(opener)
        self.assertEqual(result["code"], "ISSUE_CREATED_AND_VERIFIED")
        self.assertTrue(result["created"])

    def test_identical_existing_issue_is_idempotent_and_verified(self) -> None:
        existing = issue_payload(self.contract, number=8)
        responses = [
            FakeResponse({"login": ACTOR}),
            FakeResponse([existing]),
            FakeResponse(existing),
            FakeResponse([existing]),
        ]
        opener = FakeOpener(responses)
        result = self.call_create(opener)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["code"], "ISSUE_ALREADY_EXISTS")
        self.assertFalse(result["created"])
        self.assertFalse(result["remote_writes"])
        self.assertEqual([request.get_method() for request, _ in opener.requests], ["GET", "GET", "GET", "GET"])

    def test_same_title_different_contract_is_blocked(self) -> None:
        conflicting = issue_payload(make_contract(goal="a different contract"), number=9)
        opener = FakeOpener([FakeResponse({"login": ACTOR}), FakeResponse([conflicting])])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo=REPOSITORY,
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "ISSUE_CONTRACT_CONFLICT")
        self.assertEqual(len(opener.requests), 2)

    def test_multiple_same_title_issues_are_ambiguous(self) -> None:
        first = issue_payload(self.contract, number=10)
        second = issue_payload(self.contract, number=11)
        opener = FakeOpener([FakeResponse({"login": ACTOR}), FakeResponse([first, second])])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo=REPOSITORY,
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "ISSUE_TITLE_AMBIGUOUS")
        self.assertEqual(len(opener.requests), 2)

    def test_incomplete_pagination_is_blocked(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse({"login": ACTOR}),
                FakeResponse([], headers={"Link": "this-is-not-pagination"}),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo=REPOSITORY,
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "ISSUE_SEARCH_INCOMPLETE")

    def test_exact_title_search_consumes_all_pages_before_deciding(self) -> None:
        first_page = [{"title": "unrelated", "number": index} for index in range(100)]
        second_issue = issue_payload(make_contract(goal="different contract"), number=12)
        opener = FakeOpener(
            [
                FakeResponse({"login": ACTOR}),
                FakeResponse(first_page),
                FakeResponse([second_issue]),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=path,
                        repo=REPOSITORY,
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "ISSUE_CONTRACT_CONFLICT")
        self.assertEqual(len(opener.requests), 3)

    def test_readback_mismatches_are_blocked_without_retry_or_delete(self) -> None:
        mutations = {
            "title": lambda payload: payload.update({"title": "wrong title"}),
            "digest": lambda payload: payload.update({"body": _issue_body(make_contract(goal="wrong"))}),
            "author": lambda payload: payload.update({"user": {"login": "other-actor"}}),
            "timestamp_missing": lambda payload: payload.update({"created_at": None}),
            "timestamp_invalid": lambda payload: payload.update({"updated_at": "not-a-timestamp"}),
            "pull_request": lambda payload: payload.update({"pull_request": {}}),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                readback = issue_payload(self.contract)
                mutate(readback)
                opener = FakeOpener(create_responses(self.contract, readback=readback))
                with self.assertRaises(IssueCommandError) as raised:
                    self.call_create(opener)
                self.assertEqual(raised.exception.code, "ISSUE_CREATE_READBACK_MISMATCH")
                self.assertEqual([request.get_method() for request, _ in opener.requests], ["GET", "GET", "POST", "GET"])

    def test_http_statuses_have_stable_remote_error_mapping(self) -> None:
        for status in (401, 403, 404, 422, 429, 500, 503):
            with self.subTest(status=status):
                opener = FakeOpener([HTTPError("https://api.github.com/user", status, "failure", {}, io.BytesIO())])
                with self.assertRaises(IssueCommandError) as raised:
                    self.call_create(opener)
                self.assertEqual(raised.exception.code, "REMOTE_API_ERROR")
                self.assertIn(str(status), str(raised.exception))
                self.assertNotIn(TOKEN, str(raised.exception))

    def test_timeout_dns_bad_json_and_incomplete_user_are_bounded(self) -> None:
        cases = [
            (TimeoutError(), "REMOTE_API_UNAVAILABLE"),
            (URLError("dns failure"), "REMOTE_API_UNAVAILABLE"),
            (FakeResponse("not json", raw=True), "REMOTE_RESPONSE_INVALID"),
            (FakeResponse({}), "REMOTE_RESPONSE_INVALID"),
        ]
        for response, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                opener = FakeOpener([response])
                with self.assertRaises(IssueCommandError) as raised:
                    self.call_create(opener)
                self.assertEqual(raised.exception.code, expected_code)
                self.assertNotIn(TOKEN, str(raised.exception))

    def test_cli_emits_one_machine_json_result_without_token_or_local_path(self) -> None:
        opener = FakeOpener(create_responses(self.contract))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_contract(Path(temp_dir), self.contract)
            output = io.StringIO()
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with patch("tools.governance_v2.issue.urlopen", opener), patch("sys.stdout", output):
                    return_code = main(
                        [
                            "issue",
                            "create",
                            "--contract",
                            str(path),
                            "--repo",
                            REPOSITORY,
                            "--title",
                            TITLE,
                            "--confirm-write",
                        ]
                    )
        self.assertEqual(return_code, 0)
        text = output.getvalue()
        self.assertEqual(len(text.splitlines()), 1)
        payload = json.loads(text)
        self.assertEqual(payload["code"], "ISSUE_CREATED_AND_VERIFIED")
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("Authorization", text)
        self.assertNotIn(str(path), text)

    def test_unreadable_contract_error_does_not_echo_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing-contract.json"
            opener = FakeOpener([])
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                with self.assertRaises(IssueCommandError) as raised:
                    create_issue(
                        contract_path=missing,
                        repo=REPOSITORY,
                        title=TITLE,
                        confirmed=True,
                        opener=opener,
                    )
        self.assertEqual(raised.exception.code, "READ_FAILED")
        self.assertNotIn(str(missing), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
