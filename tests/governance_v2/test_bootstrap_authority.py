"""Local bootstrap authority trust-boundary regression tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tools.governance_v2.bootstrap import (
    BootstrapError,
    adopt_local_authority,
    init_local_authority,
    verify_local_authority,
)
from tools.governance_v2.canonical import sha256_canonical
from tools.governance_v2.models import TaskEvent


REPOSITORY_ID = "owner/repo"
TASK_ID = "BOOTSTRAP-001"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


def _create_repo(root: Path) -> str:
    root.mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.email", "bootstrap-test@example.invalid")
    _git(root, "config", "user.name", "bootstrap-test")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "seed.txt")
    _git(root, "commit", "-m", "seed")
    return _git(root, "rev-parse", "HEAD")


def _write_contract(
    root: Path,
    base_sha: str,
    *,
    repository_id: str = REPOSITORY_ID,
    allowed_paths: list[str] | None = None,
) -> tuple[Path, dict[str, object]]:
    raw: dict[str, object] = {
        "schema_version": "governance.task/v2",
        "task_id": TASK_ID,
        "task_type": "implementation",
        "repository_id": repository_id,
        "base_sha": base_sha,
        "goal": "Exercise local bootstrap authority.",
        "allowed_paths": allowed_paths or ["src/**"],
        "forbidden_paths": ["secrets/**"],
        "acceptance": ["Local authority is digest-bound."],
    }
    raw["contract_digest"] = sha256_canonical(raw)
    path = root / "contract.json"
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, raw


class BootstrapAuthorityTests(unittest.TestCase):
    def test_init_and_verify_are_local_only_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            base = _create_repo(root)
            contract_path, contract = _write_contract(root, base)
            digest = str(contract["contract_digest"])
            with patch(
                "tools.governance_v2.bootstrap.read_issue_authority",
                side_effect=AssertionError("network must not be used"),
            ):
                first = init_local_authority(
                    root=root,
                    contract_path=contract_path,
                    expected_digest=digest,
                    repository_id=REPOSITORY_ID,
                    authorization_ref="chat:approved-plan",
                )
                second = init_local_authority(
                    root=root,
                    contract_path=contract_path,
                    expected_digest=digest,
                    repository_id=REPOSITORY_ID,
                    authorization_ref="chat:approved-plan",
                )
                verified = verify_local_authority(
                    root=root,
                    task_id=TASK_ID,
                    expected_digest=digest,
                    repository_id=REPOSITORY_ID,
                )
        self.assertEqual(first["code"], "LOCAL_BOOTSTRAP_INITIALIZED")
        self.assertEqual(second["code"], "LOCAL_BOOTSTRAP_ALREADY_INITIALIZED")
        self.assertEqual(first["record_digest"], second["record_digest"])
        self.assertEqual(verified["authority"], "local_bootstrap")
        self.assertEqual(verified["remote_gate"], "NOT_RUN")

    def test_expected_digest_prevents_recomputed_scope_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            base = _create_repo(root)
            _, original = _write_contract(root, base)
            approved_digest = str(original["contract_digest"])
            expanded_path, expanded = _write_contract(
                root,
                base,
                allowed_paths=["src/**", "secrets/**"],
            )
            self.assertNotEqual(approved_digest, expanded["contract_digest"])
            with self.assertRaises(BootstrapError) as raised:
                init_local_authority(
                    root=root,
                    contract_path=expanded_path,
                    expected_digest=approved_digest,
                    repository_id=REPOSITORY_ID,
                    authorization_ref="chat:approved-plan",
                )
        self.assertEqual(raised.exception.code, "EXPECTED_CONTRACT_DIGEST_MISMATCH")

    def test_wrong_repository_and_base_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            base = _create_repo(root)
            contract_path, contract = _write_contract(root, base)
            digest = str(contract["contract_digest"])
            with self.assertRaises(BootstrapError) as wrong_repo:
                init_local_authority(
                    root=root,
                    contract_path=contract_path,
                    expected_digest=digest,
                    repository_id="other/repo",
                    authorization_ref="chat:approved-plan",
                )
            self.assertEqual(wrong_repo.exception.code, "REPOSITORY_CONTRACT_MISMATCH")
            bad_path, bad_contract = _write_contract(root, "f" * 40)
            with self.assertRaises(BootstrapError):
                init_local_authority(
                    root=root,
                    contract_path=bad_path,
                    expected_digest=str(bad_contract["contract_digest"]),
                    repository_id=REPOSITORY_ID,
                    authorization_ref="chat:approved-plan",
                )

    def test_cache_cannot_impersonate_local_bootstrap_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            _create_repo(root)
            cache = root / ".aiwf" / "cache" / "contract.json"
            cache.parent.mkdir(parents=True)
            cache.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(BootstrapError):
                verify_local_authority(
                    root=root,
                    task_id=TASK_ID,
                    expected_digest="0" * 64,
                    repository_id=REPOSITORY_ID,
                )

    def test_adoption_blocks_dual_authority_and_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            base = _create_repo(root)
            contract_path, contract = _write_contract(root, base)
            digest = str(contract["contract_digest"])
            initialized = init_local_authority(
                root=root,
                contract_path=contract_path,
                expected_digest=digest,
                repository_id=REPOSITORY_ID,
                authorization_ref="chat:approved-plan",
            )
            remote_base = {
                "repository": REPOSITORY_ID,
                "issue_number": 7,
                "contract": contract,
                "contract_digest": digest,
                "events": [],
                "issue_url": "https://github.com/owner/repo/issues/7",
            }
            with patch(
                "tools.governance_v2.bootstrap.read_issue_authority",
                return_value=remote_base,
            ):
                with self.assertRaises(BootstrapError) as pending:
                    adopt_local_authority(
                        root=root,
                        task_id=TASK_ID,
                        expected_digest=digest,
                        repo=REPOSITORY_ID,
                        issue_number=7,
                    )
            self.assertEqual(pending.exception.code, "ADOPTION_EVENT_REQUIRED")
            with self.assertRaises(BootstrapError) as blocked:
                verify_local_authority(
                    root=root,
                    task_id=TASK_ID,
                    expected_digest=digest,
                    repository_id=REPOSITORY_ID,
                )
            self.assertEqual(blocked.exception.code, "ADOPTION_HANDOFF_PENDING")
            event = TaskEvent.create(
                sequence=1,
                event_type="bootstrap_contract_adopted",
                task_id=TASK_ID,
                subject_sha=base,
                previous_event_digest=None,
                payload={
                    "contract_digest": digest,
                    "bootstrap_record_digest": initialized["record_digest"],
                },
                actor="owner",
                created_at="2026-09-15T08:00:00Z",
            )
            adopted_remote = {**remote_base, "events": [event.to_dict()]}
            with patch(
                "tools.governance_v2.bootstrap.read_issue_authority",
                return_value=adopted_remote,
            ):
                adopted = adopt_local_authority(
                    root=root,
                    task_id=TASK_ID,
                    expected_digest=digest,
                    repo=REPOSITORY_ID,
                    issue_number=7,
                )
            self.assertEqual(adopted["code"], "LOCAL_BOOTSTRAP_ADOPTED")
            self.assertEqual(adopted["authority"], "issue")
            with self.assertRaises(BootstrapError) as retired:
                verify_local_authority(
                    root=root,
                    task_id=TASK_ID,
                    expected_digest=digest,
                    repository_id=REPOSITORY_ID,
                )
            self.assertEqual(retired.exception.code, "LOCAL_BOOTSTRAP_RETIRED")


class AdoptionIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "bootstrap repo"
        self.base = _create_repo(self.root)
        contract_path, self.contract = _write_contract(self.root, self.base)
        self.digest = str(self.contract["contract_digest"])
        self.initialized = init_local_authority(
            root=self.root, contract_path=contract_path, expected_digest=self.digest,
            repository_id=REPOSITORY_ID, authorization_ref="chat:approved-contract",
        )
        self.directory = self.root / ".aiwf" / "bootstrap" / TASK_ID
        self.pending_path = self.directory / "adoption-pending.json"
        self.receipt_path = self.directory / "adoption-receipt.json"
        self.remote = {
            "repository": REPOSITORY_ID, "issue_number": 7,
            "issue_url": "https://github.com/owner/repo/issues/7",
            "contract": self.contract, "contract_digest": self.digest, "events": [],
        }

    def _event(self, *, subject: str | None = None, previous: TaskEvent | None = None,
               event_type: str = "bootstrap_contract_adopted") -> TaskEvent:
        return TaskEvent.create(
            sequence=previous.sequence + 1 if previous else 1,
            event_type=event_type, task_id=TASK_ID, subject_sha=subject or self.base,
            previous_event_digest=previous.event_digest if previous else None,
            payload={"contract_digest": self.digest,
                     "bootstrap_record_digest": self.initialized["record_digest"]},
            actor="owner", created_at="2026-09-15T08:00:00Z",
        )

    def _adopt(self) -> dict[str, object]:
        with patch("tools.governance_v2.bootstrap.read_issue_authority", return_value=self.remote):
            return adopt_local_authority(
                root=self.root, task_id=TASK_ID, expected_digest=self.digest,
                repo=REPOSITORY_ID, issue_number=7,
            )

    def _verify(self) -> dict[str, object]:
        return verify_local_authority(
            root=self.root, task_id=TASK_ID, expected_digest=self.digest,
            repository_id=REPOSITORY_ID,
        )

    def _pending(self) -> None:
        with self.assertRaises(BootstrapError) as error:
            self._adopt()
        self.assertEqual(error.exception.code, "ADOPTION_EVENT_REQUIRED")

    def _finish(self) -> TaskEvent:
        event = self._event()
        self.remote["events"] = [event.to_dict()]
        self.assertEqual(self._adopt()["code"], "LOCAL_BOOTSTRAP_ADOPTED")
        return event

    def _write_record(self, path: Path, record: dict[str, object], *, rehash: bool = True) -> None:
        if rehash:
            record["record_digest"] = sha256_canonical(
                {key: value for key, value in record.items() if key != "record_digest"}
            )
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def test_later_candidate_subject_is_distinct_from_contract_base(self) -> None:
        (self.root / "seed.txt").write_text("candidate\n", encoding="utf-8")
        _git(self.root, "add", "seed.txt")
        _git(self.root, "commit", "-m", "later candidate")
        candidate = _git(self.root, "rev-parse", "HEAD")
        self.assertNotEqual(candidate, self.base)
        opened = self._event(subject=candidate, event_type="task_opened")
        adopted = self._event(subject=candidate, previous=opened)
        self.remote["events"] = [opened.to_dict(), adopted.to_dict()]
        result = self._adopt()
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(result["adoption_subject_sha"], candidate)
        self.assertEqual(receipt["base_sha"], self.base)
        self.assertEqual(receipt["adoption_subject_sha"], candidate)
        self.assertEqual(receipt["adoption_event_digest"], adopted.event_digest)
        with self.assertRaises(BootstrapError) as retired:
            self._verify()
        self.assertEqual(retired.exception.code, "LOCAL_BOOTSTRAP_RETIRED")

    def test_pending_and_receipt_tampering_is_rejected_before_lifecycle_success(self) -> None:
        self._finish()
        changes = {
            "schema": "forged", "state": "forged", "task_id": "other-task",
            "repository_id": "other/repo", "base_sha": "f" * 40,
            "contract_digest": "e" * 64, "bootstrap_record_digest": "d" * 64,
            "issue_number": 8, "issue_url": "https://github.com/other/repo/issues/7",
            "remote_writes": True,
        }
        for path in (self.pending_path, self.receipt_path):
            original_bytes = path.read_bytes()
            original = json.loads(original_bytes)
            for rehash in (False, True):
                for field, value in changes.items():
                    with self.subTest(file=path.name, rehash=rehash, field=field):
                        self._write_record(path, {**original, field: value}, rehash=rehash)
                        for operation in (self._verify, self._adopt):
                            with self.assertRaises(BootstrapError) as error:
                                operation()
                            self.assertEqual(error.exception.status, "FAIL")
                        path.write_bytes(original_bytes)

    def test_receipt_event_and_pending_bindings_cannot_be_rehashed_away(self) -> None:
        self._finish()
        original = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        changes = {
            "adoption_subject_sha": "f" * 40, "adoption_event_digest": "f" * 64,
            "pending_record_digest": "f" * 64,
            "adoption_event": {},
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self._write_record(self.receipt_path, {**original, field: value})
                for operation in (self._verify, self._adopt):
                    with self.assertRaises(BootstrapError) as error:
                        operation()
                    self.assertEqual(error.exception.status, "FAIL")

    def test_recomputed_forged_event_still_requires_remote_readback(self) -> None:
        self._finish()
        forged = self._event(subject="c" * 40)
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        receipt.update(adoption_event=forged.to_dict(), adoption_event_digest=forged.event_digest,
                       adoption_subject_sha=forged.subject_sha)
        self._write_record(self.receipt_path, receipt)
        with self.assertRaises(BootstrapError) as error:
            self._adopt()
        self.assertEqual(error.exception.code, "ADOPTION_RECEIPT_CONFLICT")

    def test_receipt_retry_is_read_only_and_byte_stable_after_chain_extension(self) -> None:
        adopted = self._finish()
        before = {path: path.read_bytes() for path in self.directory.iterdir()}
        extension = self._event(previous=adopted, event_type="validation_recorded")
        self.remote["events"] = [adopted.to_dict(), extension.to_dict()]
        for _ in range(2):
            with patch("tools.governance_v2.bootstrap.read_issue_authority", return_value=self.remote) as readback:
                result = adopt_local_authority(
                    root=self.root, task_id=TASK_ID, expected_digest=self.digest,
                    repo=REPOSITORY_ID, issue_number=7,
                )
            self.assertEqual(readback.call_count, 1)
            self.assertEqual(result["code"], "LOCAL_BOOTSTRAP_ALREADY_ADOPTED")
            self.assertEqual(result["adoption_event_digest"], adopted.event_digest)
        self.assertEqual(before, {path: path.read_bytes() for path in self.directory.iterdir()})

    def test_receipt_rejects_rehashed_substitute_chain_head_after_extension(self) -> None:
        adopted = self._finish()
        receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        self.assertNotIn("chain_head_digest", receipt)
        extension = self._event(previous=adopted, event_type="validation_recorded")
        self.remote["events"] = [adopted.to_dict(), extension.to_dict()]
        receipt["chain_head_digest"] = extension.event_digest
        self._write_record(self.receipt_path, receipt)
        with self.assertRaises(BootstrapError) as error:
            self._adopt()
        self.assertEqual(error.exception.code, "ADOPTION_RECORD_INVALID")

    def test_pending_retry_is_byte_stable(self) -> None:
        self._pending()
        before = self.pending_path.read_bytes()
        self._pending()
        self.assertEqual(self.pending_path.read_bytes(), before)
        self.assertFalse(self.receipt_path.exists())

    def test_receipt_does_not_claim_success_when_remote_readback_is_unavailable(self) -> None:
        from tools.governance_v2.issue import IssueCommandError

        self._finish()
        before = self.receipt_path.read_bytes()
        with patch("tools.governance_v2.bootstrap.read_issue_authority",
                   side_effect=IssueCommandError("unavailable", code="REMOTE_READ_FAILED")):
            with self.assertRaises(BootstrapError) as error:
                adopt_local_authority(
                    root=self.root, task_id=TASK_ID, expected_digest=self.digest,
                    repo=REPOSITORY_ID, issue_number=7,
                )
        self.assertEqual(error.exception.code, "REMOTE_READ_FAILED")
        self.assertEqual(self.receipt_path.read_bytes(), before)

    def test_pending_without_receipt_rejects_recomputed_identity_tampering(self) -> None:
        self._pending()
        original = json.loads(self.pending_path.read_text(encoding="utf-8"))
        self._write_record(self.pending_path, {**original, "base_sha": "c" * 40})
        for operation in (self._verify, self._adopt):
            with self.assertRaises(BootstrapError) as error:
                operation()
            self.assertEqual(error.exception.code, "ADOPTION_RECORD_CONFLICT")
        self.assertFalse(self.receipt_path.exists())

    def test_authority_cannot_be_loaded_under_another_task_directory(self) -> None:
        import shutil

        other_directory = self.directory.parent / "OTHER-TASK"
        other_directory.mkdir()
        shutil.copyfile(self.directory / "authority.json", other_directory / "authority.json")
        with self.assertRaises(BootstrapError) as error:
            verify_local_authority(root=self.root, task_id="OTHER-TASK", expected_digest=self.digest,
                                   repository_id=REPOSITORY_ID)
        self.assertEqual(error.exception.code, "BOOTSTRAP_RECORD_INVALID")

    def test_multiple_matching_events_fail_even_when_chain_is_valid(self) -> None:
        first = self._event()
        second = self._event(previous=first)
        self.remote["events"] = [first.to_dict(), second.to_dict()]
        with self.assertRaises(BootstrapError) as error:
            self._adopt()
        self.assertEqual(error.exception.code, "ADOPTION_EVENT_CONFLICT")
        self.assertFalse(self.receipt_path.exists())

    def test_multiple_matching_events_also_fail_after_receipt_exists(self) -> None:
        first = self._finish()
        second = self._event(previous=first)
        self.remote["events"] = [first.to_dict(), second.to_dict()]
        with self.assertRaises(BootstrapError) as error:
            self._adopt()
        self.assertEqual(error.exception.code, "ADOPTION_EVENT_CONFLICT")

    def test_chain_subject_change_is_still_rejected(self) -> None:
        opened = self._event(event_type="task_opened")
        adopted = self._event(subject="c" * 40, previous=opened)
        self.remote["events"] = [opened.to_dict(), adopted.to_dict()]
        with self.assertRaises(BootstrapError) as error:
            self._adopt()
        self.assertEqual(error.exception.code, "EVENT_SUBJECT_SHA_MISMATCH")

    def test_remote_issue_identity_mismatch_creates_no_handoff(self) -> None:
        original = deepcopy(self.remote)
        for field, value in (("repository", "other/repo"), ("issue_number", 8), ("issue_url", "https://example.invalid")):
            with self.subTest(field=field):
                self.remote = {**original, field: value}
                with self.assertRaises(BootstrapError) as error:
                    self._adopt()
                self.assertEqual(error.exception.code, "ADOPTION_ISSUE_MISMATCH")
                self.assertFalse(self.pending_path.exists())
                self.assertFalse(self.receipt_path.exists())

    def test_receipt_requires_original_pending_and_bootstrap_record(self) -> None:
        self._finish()
        pending_bytes = self.pending_path.read_bytes()
        self.pending_path.unlink()
        with self.assertRaises(BootstrapError):
            self._verify()
        self.pending_path.write_bytes(pending_bytes)
        authority_path = self.directory / "authority.json"
        changed = json.loads(authority_path.read_text(encoding="utf-8"))
        changed["authorization_ref"] = "chat:changed-authority"
        self._write_record(authority_path, changed)
        with self.assertRaises(BootstrapError) as error:
            self._adopt()
        self.assertEqual(error.exception.code, "ADOPTION_RECORD_CONFLICT")

    def test_receipt_write_failure_recovers_from_pending_without_remote_write(self) -> None:
        from tools.governance_v2 import bootstrap

        self.remote["events"] = [self._event().to_dict()]
        original_write = bootstrap._write_once

        def fail_receipt(path: Path, value: dict[str, object], *, digest_field: str) -> bool:
            if path.name == "adoption-receipt.json":
                raise BootstrapError("simulated disk error", code="OUTPUT_WRITE_FAILED")
            return original_write(path, value, digest_field=digest_field)

        with patch.object(bootstrap, "_write_once", side_effect=fail_receipt):
            with self.assertRaises(BootstrapError) as error:
                self._adopt()
        self.assertEqual(error.exception.code, "OUTPUT_WRITE_FAILED")
        self.assertTrue(self.pending_path.exists())
        self.assertFalse(self.receipt_path.exists())
        self.assertEqual(self._adopt()["code"], "LOCAL_BOOTSTRAP_ADOPTED")

    def test_torn_temporary_receipt_write_leaves_no_partial_target_and_recovers(self) -> None:
        from tools.governance_v2 import bootstrap

        self.remote["events"] = [self._event().to_dict()]
        original_write = bootstrap._write_temp_payload
        calls = 0

        def tear_receipt(stream: object, payload: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                stream.write(payload[: max(1, len(payload) // 3)])
                stream.flush()
                raise OSError("simulated interrupted receipt write")
            original_write(stream, payload)

        with patch.object(bootstrap, "_write_temp_payload", side_effect=tear_receipt):
            with self.assertRaises(BootstrapError) as error:
                self._adopt()
        self.assertEqual(error.exception.code, "OUTPUT_WRITE_FAILED")
        self.assertTrue(self.pending_path.exists())
        self.assertFalse(self.receipt_path.exists())
        self.assertEqual(list(self.directory.glob(".adoption-receipt.json.*.tmp")), [])
        self.assertEqual(self._adopt()["code"], "LOCAL_BOOTSTRAP_ADOPTED")
        self.assertTrue(self.receipt_path.is_file())
        self.assertEqual(list(self.directory.glob(".adoption-receipt.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
