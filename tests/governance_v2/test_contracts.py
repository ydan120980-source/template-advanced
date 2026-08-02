"""Contract, canonical digest, and Issue event-chain tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.governance_v2.canonical import canonical_json, sha256_canonical
from tools.governance_v2.issue import extract_contract, require_write_confirmation, verify_event_chain
from tools.governance_v2.models import ContractError, TaskContract, TaskEvent


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "governance_v2" / "fixtures" / "bootstrap-contract.json"


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_frozen_contract_digest_is_recomputed(self) -> None:
        contract = TaskContract.from_dict(self.raw)
        self.assertEqual(
            contract.digest,
            sha256_canonical({key: value for key, value in self.raw.items() if key != "contract_digest"}),
        )
        self.assertEqual(canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_contract_tamper_is_rejected(self) -> None:
        tampered = dict(self.raw)
        tampered["goal"] = "changed"
        with self.assertRaises(ContractError):
            TaskContract.from_dict(tampered)

    def test_issue_body_contract_extraction(self) -> None:
        body = "prefix\n```json\n" + json.dumps(self.raw) + "\n```\nsuffix"
        self.assertEqual(extract_contract(body)["task_id"], "GOV-V2-BOOTSTRAP")

    def test_event_chain_and_fork_detection(self) -> None:
        first = TaskEvent.create(
            sequence=1,
            event_type="task_opened",
            task_id="GOV-V2-BOOTSTRAP",
            subject_sha=self.raw["base_sha"],
            previous_event_digest=None,
            payload={"goal": "bootstrap"},
            actor="ydan120980-source",
            created_at="2026-08-02T14:00:00Z",
        )
        second = TaskEvent.create(
            sequence=2,
            event_type="bootstrap_contract_adopted",
            task_id=first.task_id,
            subject_sha=first.subject_sha,
            previous_event_digest=first.event_digest,
            payload={"contract_digest": self.raw["contract_digest"]},
            actor="ydan120980-source",
            created_at="2026-08-02T14:01:00Z",
        )
        valid = verify_event_chain([first, second])
        self.assertEqual(valid["status"], "PASS")
        self.assertEqual(valid["chain_head"], second.event_digest)

        fork = TaskEvent.create(
            sequence=2,
            event_type="decision_recorded",
            task_id=first.task_id,
            subject_sha=first.subject_sha,
            previous_event_digest=first.event_digest,
            payload={"decision": "different"},
            actor="ydan120980-source",
            created_at="2026-08-02T14:02:00Z",
        )
        result = verify_event_chain([first, second, fork])
        self.assertEqual(result["code"], "EVENT_CHAIN_FORK")

    def test_write_confirmation_is_explicit(self) -> None:
        with self.assertRaisesRegex(Exception, "confirm-write"):
            require_write_confirmation(False)
        self.assertIsNone(require_write_confirmation(True))


if __name__ == "__main__":
    unittest.main()
