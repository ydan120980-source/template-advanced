"""Read-before-write and read-after-write Issue event-chain tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.governance_v2.canonical import sha256_canonical
from tools.governance_v2.issue import IssueCommandError, _issue_body, append_issue_event
from tools.governance_v2.models import TaskContract, TaskEvent


REPOSITORY = "owner/repository"
TOKEN = "append-token-that-must-never-be-printed"
ACTOR = "append-actor"
TASK_ID = "GOV-V2-APPEND"
SUBJECT_SHA = "a" * 40


class FakeResponse:
    def __init__(self, payload: object, *, headers: dict[str, str] | None = None) -> None:
        self._data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.headers = headers or {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


class FakeOpener:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[object] = []

    def __call__(self, request: object, *, timeout: float) -> FakeResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("fake opener received an unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if not isinstance(response, FakeResponse):
            raise AssertionError("fake response has an invalid type")
        return response


def make_contract() -> TaskContract:
    raw = {
        "schema_version": "governance.task/v2",
        "task_id": TASK_ID,
        "task_type": "test_task",
        "repository_id": REPOSITORY,
        "base_sha": SUBJECT_SHA,
        "goal": "append events safely",
        "allowed_paths": ["tools/governance_v2/**"],
        "forbidden_paths": [".git/**"],
        "acceptance": ["read before write and verify after write"],
    }
    raw["contract_digest"] = sha256_canonical(raw)
    return TaskContract.from_dict(raw)


def make_event(
    *,
    sequence: int = 1,
    previous_event_digest: str | None = None,
    task_id: str = TASK_ID,
    subject_sha: str = SUBJECT_SHA,
) -> TaskEvent:
    return TaskEvent.create(
        sequence=sequence,
        event_type="task_opened" if sequence == 1 else "validation_recorded",
        task_id=task_id,
        subject_sha=subject_sha,
        previous_event_digest=previous_event_digest,
        payload={"sequence": sequence},
        actor=ACTOR,
        created_at="2026-08-03T15:00:00Z",
    )


def comment_payload(event: TaskEvent, *, comment_id: int = 99) -> dict[str, object]:
    body = "```json\n" + json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    return {
        "id": comment_id,
        "body": body,
        "user": {"login": ACTOR},
        "url": f"https://api.github.com/repos/{REPOSITORY}/issues/comments/{comment_id}",
        "html_url": f"https://github.com/{REPOSITORY}/issues/4#issuecomment-{comment_id}",
        "created_at": "2026-08-03T15:00:01Z",
        "updated_at": "2026-08-03T15:00:01Z",
    }


def issue_payload(contract: TaskContract) -> dict[str, object]:
    return {
        "number": 4,
        "title": f"[AIWF Task] {TASK_ID}",
        "state": "open",
        "body": _issue_body(contract),
        "user": {"login": ACTOR},
        "repository_url": f"https://api.github.com/repos/{REPOSITORY}",
        "url": f"https://api.github.com/repos/{REPOSITORY}/issues/4",
        "html_url": f"https://github.com/{REPOSITORY}/issues/4",
        "created_at": "2026-08-03T15:00:00Z",
        "updated_at": "2026-08-03T15:00:01Z",
    }


def append_responses(
    contract: TaskContract,
    event: TaskEvent,
    *,
    existing_comments: list[dict[str, object]] | None = None,
    final_comments: list[dict[str, object]] | None = None,
    comment_readback: dict[str, object] | None = None,
    comment_post: dict[str, object] | None = None,
    initial_comment_headers: dict[str, str] | None = None,
) -> list[FakeResponse]:
    posted = comment_post or comment_payload(event)
    readback = comment_readback or posted
    initial = existing_comments or []
    final = final_comments if final_comments is not None else [posted]
    return [
        FakeResponse({"login": ACTOR}),
        FakeResponse(issue_payload(contract)),
        FakeResponse(initial, headers=initial_comment_headers),
        FakeResponse(posted),
        FakeResponse(readback),
        FakeResponse(issue_payload(contract)),
        FakeResponse(final),
    ]


class IssueAppendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = make_contract()

    def call_append(
        self,
        opener: FakeOpener,
        event: TaskEvent,
        *,
        confirmed: bool = True,
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "event.json"
            event_path.write_text(json.dumps(event.to_dict()), encoding="utf-8")
            with patch.dict(os.environ, {"GH_TOKEN": TOKEN}, clear=True):
                return append_issue_event(
                    event_path=event_path,
                    repo=REPOSITORY,
                    issue_number=4,
                    issue_url=None,
                    confirmed=confirmed,
                    opener=opener,
                )

    def test_confirmation_is_checked_before_network(self) -> None:
        opener = FakeOpener([])
        with self.assertRaises(IssueCommandError) as raised:
            self.call_append(opener, make_event(), confirmed=False)
        self.assertEqual(raised.exception.code, "CONFIRM_WRITE_REQUIRED")
        self.assertEqual(opener.requests, [])

    def test_invalid_existing_chain_blocks_before_post(self) -> None:
        first = make_event()
        gap = make_event(sequence=3, previous_event_digest=first.event_digest)
        existing = [comment_payload(first, comment_id=1), comment_payload(gap, comment_id=2)]
        opener = FakeOpener(
            append_responses(
                self.contract,
                make_event(sequence=4, previous_event_digest=gap.event_digest),
                existing_comments=existing,
                final_comments=existing,
            )[:3]
        )
        with self.assertRaises(IssueCommandError) as raised:
            self.call_append(opener, make_event(sequence=4, previous_event_digest=gap.event_digest))
        self.assertEqual(raised.exception.code, "EVENT_CHAIN_GAP")
        self.assertEqual([request.get_method() for request in opener.requests], ["GET", "GET", "GET"])

    def test_sequence_and_subject_are_checked_before_post(self) -> None:
        first = make_event()
        for event, expected in (
            (make_event(sequence=2), "EVENT_CHAIN_GAP"),
            (
                make_event(
                    sequence=2,
                    previous_event_digest=first.event_digest,
                    subject_sha="b" * 40,
                ),
                "EVENT_SUBJECT_SHA_MISMATCH",
            ),
        ):
            with self.subTest(expected=expected):
                existing = [comment_payload(first, comment_id=1)] if expected == "EVENT_SUBJECT_SHA_MISMATCH" else []
                opener = FakeOpener(
                    append_responses(
                        self.contract,
                        event,
                        existing_comments=existing,
                    )[:3]
                )
                with self.assertRaises(IssueCommandError) as raised:
                    self.call_append(opener, event)
                self.assertEqual(raised.exception.code, expected)
                self.assertEqual([request.get_method() for request in opener.requests], ["GET", "GET", "GET"])

    def test_fork_is_rejected_before_post(self) -> None:
        first = make_event()
        left = make_event(sequence=2, previous_event_digest=first.event_digest)
        right = TaskEvent.create(
            sequence=2,
            event_type="decision_recorded",
            task_id=TASK_ID,
            subject_sha=SUBJECT_SHA,
            previous_event_digest=first.event_digest,
            payload={"sequence": "right"},
            actor=ACTOR,
            created_at="2026-08-03T15:00:02Z",
        )
        existing = [
            comment_payload(first, comment_id=1),
            comment_payload(left, comment_id=2),
            comment_payload(right, comment_id=3),
        ]
        opener = FakeOpener(append_responses(self.contract, make_event(sequence=3, previous_event_digest=left.event_digest), existing_comments=existing)[:3])
        with self.assertRaises(IssueCommandError) as raised:
            self.call_append(opener, make_event(sequence=3, previous_event_digest=left.event_digest))
        self.assertEqual(raised.exception.code, "EVENT_CHAIN_FORK")

    def test_append_posts_only_body_and_verifies_comment_and_chain(self) -> None:
        event = make_event()
        opener = FakeOpener(append_responses(self.contract, event))
        result = self.call_append(opener, event)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["code"], "EVENT_APPENDED_AND_VERIFIED")
        self.assertEqual(result["event_digest"], event.event_digest)
        self.assertEqual(result["author"], ACTOR)
        self.assertTrue(result["remote_writes"])
        self.assertEqual(
            [request.get_method() for request in opener.requests],
            ["GET", "GET", "GET", "POST", "GET", "GET", "GET"],
        )
        post = opener.requests[3]
        self.assertEqual(json.loads(post.data.decode("utf-8")).keys(), {"body"})
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_comment_readback_mismatch_blocks_without_reread_or_rollback(self) -> None:
        event = make_event()
        readback = comment_payload(event)
        readback["user"] = {"login": "other-actor"}
        opener = FakeOpener(append_responses(self.contract, event, comment_readback=readback))
        with self.assertRaises(IssueCommandError) as raised:
            self.call_append(opener, event)
        self.assertEqual(raised.exception.code, "EVENT_COMMENT_READBACK_MISMATCH")
        self.assertEqual([request.get_method() for request in opener.requests], ["GET", "GET", "GET", "POST", "GET"])

    def test_all_comment_pages_are_read_before_write(self) -> None:
        event = make_event()
        opener = FakeOpener(
            append_responses(
                self.contract,
                event,
                initial_comment_headers={"Link": '<https://api.github.com/repos/owner/repository/issues/4/comments?page=2>; rel="next"'},
            )
        )
        # Add the empty second page before the POST and keep the final page in place.
        responses = opener.responses
        responses.insert(3, FakeResponse([]))
        result = self.call_append(opener, event)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual([request.get_method() for request in opener.requests], ["GET", "GET", "GET", "GET", "POST", "GET", "GET", "GET"])


if __name__ == "__main__":
    unittest.main()
