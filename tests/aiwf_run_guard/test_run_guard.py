"""Contract tests for the AIWF Run Guard package and CLI."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.aiwf_run_guard.config import (
    ConfigError,
    artifact_identity_key,
    path_matches_prefix,
)
from tools.aiwf_run_guard.gate import evaluate_gate, summarize_run
from tools.aiwf_run_guard.ledger import (
    LEDGER_FILE,
    append_event,
    initialize_run,
    read_events,
)
from tools.aiwf_run_guard.models import LedgerError, TransitionError
from tools.aiwf_run_guard.preflight import _planning, run_preflight
from tools.aiwf_run_guard.reporters import (
    render_json,
    render_report_markdown,
    render_summary_markdown,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def base_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "task_id": "2026-07-31-TEST-RUN",
        "retry_limit": 2,
        "workstreams": [
            {
                "id": "core",
                "owner": "alice",
                "owned_paths": ["tools/core"],
                "require_handoff": True,
            },
            {
                "id": "integration",
                "owner": "coordinator",
                "owned_paths": [],
                "require_handoff": False,
            },
        ],
        "allowed_paths": ["docs", "tools"],
        "forbidden_paths": ["tools/core/secret"],
        "require_validation": True,
        "require_review": True,
        "first_artifact_seconds": None,
    }
    config.update(overrides)
    return config


class IsolatedRun:
    def __init__(self, root: Path, config: dict[str, object] | None = None) -> None:
        self.root = root
        self.plan = root / "plan"
        self.plan.mkdir(parents=True)
        self.config_path = root / "config.json"
        self.config_path.write_text(
            json.dumps(config or base_config(), indent=2), encoding="utf-8"
        )
        initialize_run(self.plan, self.config_path)

    def artifact(self, relative: str = "tools/core/output.txt") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("artifact\n", encoding="utf-8")
        return path

    def complete(self) -> None:
        self.artifact()
        append_event(
            self.plan,
            agent="alice",
            workstream="core",
            kind="workstream_started",
        )
        append_event(
            self.plan,
            agent="alice",
            workstream="core",
            kind="artifact",
            files=["tools/core/output.txt"],
        )
        append_event(
            self.plan,
            agent="alice",
            workstream="core",
            kind="handoff",
        )
        append_event(
            self.plan,
            agent="coordinator",
            workstream="integration",
            kind="workstream_started",
        )
        append_event(
            self.plan,
            agent="coordinator",
            workstream="integration",
            kind="validation_passed",
        )
        append_event(
            self.plan,
            agent="coordinator",
            workstream="integration",
            kind="review_passed",
        )


class RunGuardTests(unittest.TestCase):
    maxDiff = None

    def test_artifact_budget_exact_limit_deduplicates_identical_paths_and_blocks_overage(
        self,
    ) -> None:
        config = base_config(
            artifact_budget={"limit": 1, "metric": "unique_artifact_files"}
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory), config)
            run.complete()
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="artifact",
                files=["tools/core/output.txt"],
            )
            run.artifact("tools/core/note.txt")
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="note",
                files=["tools/core/note.txt"],
            )
            exact = evaluate_gate(run.root, run.plan)
            exact_summary = summarize_run(run.plan)
            run.artifact("tools/core/second.txt")
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="artifact",
                files=["tools/core/second.txt", "tools/core/second.txt"],
            )
            over = evaluate_gate(run.root, run.plan)

        exact_finding = next(
            item for item in exact.findings if item.finding_id == "artifacts.file_budget"
        )
        over_finding = next(
            item for item in over.findings if item.finding_id == "artifacts.file_budget"
        )
        self.assertEqual(exact_finding.status, "pass")
        self.assertIn("1/1", exact_finding.evidence)
        self.assertEqual(exact_summary["artifact_budget"]["total"], 1)
        self.assertEqual(over_finding.status, "fail")
        self.assertIn("2/1", over_finding.evidence)

    def test_artifact_identity_matches_platform_case_semantics(self) -> None:
        with patch("tools.aiwf_run_guard.config.os.name", "nt"):
            self.assertEqual(
                artifact_identity_key("tools/core/Output.txt"),
                artifact_identity_key("tools/core/output.txt"),
            )
            self.assertEqual(
                artifact_identity_key("TOOLS/CORE/OUTPUT.TXT"),
                artifact_identity_key("tools/core/output.txt"),
            )
        with patch("tools.aiwf_run_guard.config.os.name", "posix"):
            self.assertNotEqual(
                artifact_identity_key("tools/core/Output.txt"),
                artifact_identity_key("tools/core/output.txt"),
            )
            self.assertEqual(
                artifact_identity_key("tools/core/output.txt"),
                artifact_identity_key("tools/core/output.txt"),
            )

    def test_artifact_budget_is_optional_and_rejects_invalid_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()
            report = evaluate_gate(run.root, run.plan)
            summary = summarize_run(run.plan)
        self.assertNotIn(
            "artifacts.file_budget", {item.finding_id for item in report.findings}
        )
        self.assertNotIn("artifact_budget", summary)

        invalid_contracts = (
            {"limit": -1, "metric": "unique_artifact_files"},
            {"limit": 1, "metric": "changed_files"},
            {"limit": 1, "metric": "unique_artifact_files", "extra": True},
        )
        for contract in invalid_contracts:
            with self.subTest(contract=contract), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = root / "plan"
                plan.mkdir()
                source = root / "config.json"
                source.write_text(
                    json.dumps(base_config(artifact_budget=contract)), encoding="utf-8"
                )
                with self.assertRaises(ConfigError):
                    initialize_run(plan, source)

    def test_zero_artifact_budget_passes_empty_and_blocks_first_artifact(self) -> None:
        config = base_config(
            artifact_budget={"limit": 0, "metric": "unique_artifact_files"}
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory), config)
            empty = evaluate_gate(run.root, run.plan)
            run.artifact()
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="artifact",
                files=["tools/core/output.txt"],
            )
            first = evaluate_gate(run.root, run.plan)

        empty_finding = next(
            item for item in empty.findings if item.finding_id == "artifacts.file_budget"
        )
        first_finding = next(
            item for item in first.findings if item.finding_id == "artifacts.file_budget"
        )
        self.assertEqual(empty_finding.status, "pass")
        self.assertIn("0/0", empty_finding.evidence)
        self.assertEqual(first_finding.status, "fail")
        self.assertIn("1/0", first_finding.evidence)

    def test_complete_run_passes_gate_and_has_stable_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()

            report = evaluate_gate(run.root, run.plan)
            first = summarize_run(run.plan)
            second = summarize_run(run.plan)

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.exit_code, 0)
        self.assertEqual(first, second)
        self.assertEqual(first["event_count"], 6)
        self.assertEqual(first["retry_count"], 0)
        self.assertEqual(
            [finding.finding_id for finding in report.findings],
            sorted(finding.finding_id for finding in report.findings),
        )

    def test_retry_lineage_with_owner_takeover_stays_within_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.artifact()
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="command_failed",
                failure_id="core-test-1",
            )
            retry = append_event(
                run.plan,
                agent="bob",
                workstream="core",
                kind="retry",
                retry_of="core-test-1",
            )
            append_event(
                run.plan,
                agent="bob",
                workstream="core",
                kind="artifact",
                files=["tools/core/output.txt"],
            )
            append_event(
                run.plan,
                agent="bob",
                workstream="core",
                kind="handoff",
            )
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="workstream_started",
            )
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="validation_passed",
            )
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="review_passed",
            )
            report = evaluate_gate(run.root, run.plan)
            summary = summarize_run(run.plan)

        self.assertEqual(retry.attempt, 2)
        self.assertEqual(report.status, "ready")
        self.assertEqual(summary["retry_count"], 1)
        core = next(item for item in summary["workstreams"] if item["id"] == "core")
        self.assertEqual(core["effective_owner"], "bob")

    def test_retry_budget_exceeded_is_gate_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory), base_config(retry_limit=1))
            append_event(run.plan, agent="alice", workstream="core", kind="workstream_started")
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="command_failed",
                failure_id="failure-1",
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="retry",
                retry_of="failure-1",
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="integration_failed",
                failure_id="failure-2",
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="retry",
                retry_of="failure-2",
            )
            report = evaluate_gate(run.root, run.plan)

        budget = next(item for item in report.findings if item.finding_id == "retry.budget")
        self.assertEqual(report.exit_code, 1)
        self.assertEqual(budget.status, "fail")
        self.assertIn("2/1", budget.evidence)

    def test_missing_and_duplicate_retry_references_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            append_event(run.plan, agent="alice", workstream="core", kind="workstream_started")
            with self.assertRaises(TransitionError):
                append_event(
                    run.plan,
                    agent="alice",
                    workstream="core",
                    kind="retry",
                )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="command_failed",
                failure_id="failure-1",
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="retry",
                retry_of="failure-1",
            )
            with self.assertRaises(TransitionError):
                append_event(
                    run.plan,
                    agent="alice",
                    workstream="core",
                    kind="retry",
                    retry_of="failure-1",
                )

    def test_concurrent_appenders_produce_unique_contiguous_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            append_event(run.plan, agent="alice", workstream="core", kind="workstream_started")

            def heartbeat(index: int) -> None:
                append_event(
                    run.plan,
                    agent="alice",
                    workstream="core",
                    kind="heartbeat",
                    summary=f"heartbeat {index}",
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(heartbeat, range(40)))
            events = read_events(run.plan)

        self.assertEqual(len(events), 41)
        self.assertEqual([event.sequence for event in events], list(range(1, 42)))
        self.assertEqual(len({event.event_id for event in events}), 41)

    def test_configuration_ownership_overlap_is_reported(self) -> None:
        config = base_config()
        config["workstreams"] = [
            {
                "id": "core",
                "owner": "alice",
                "owned_paths": ["tools"],
                "require_handoff": False,
            },
            {
                "id": "nested",
                "owner": "bob",
                "owned_paths": ["tools/core"],
                "require_handoff": False,
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory), config)
            report = evaluate_gate(run.root, run.plan)

        ownership = next(
            item for item in report.findings if item.finding_id == "ownership.no_overlap"
        )
        self.assertEqual(ownership.status, "fail")
        self.assertIn("overlaps", ownership.evidence)

    def test_forbidden_artifact_is_rejected_at_record_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            append_event(run.plan, agent="alice", workstream="core", kind="workstream_started")
            with self.assertRaises(TransitionError):
                append_event(
                    run.plan,
                    agent="alice",
                    workstream="core",
                    kind="artifact",
                    files=["tools/core/secret/token.txt"],
                )

    def test_windows_scope_matching_rejects_case_variant_forbidden_path(self) -> None:
        with patch("tools.aiwf_run_guard.config.os.name", "nt"):
            self.assertTrue(
                path_matches_prefix(
                    "tools/core/SECRET/token.txt", "tools/core/secret"
                )
            )
        with patch("tools.aiwf_run_guard.config.os.name", "posix"):
            self.assertFalse(
                path_matches_prefix(
                    "tools/core/SECRET/token.txt", "tools/core/secret"
                )
            )

    def test_tampered_forbidden_artifact_is_rejected_as_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            start = append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
            )
            raw = start.to_dict()
            raw.update(
                {
                    "sequence": 2,
                    "event_id": "evt-000002",
                    "kind": "artifact",
                    "files": ["tools/core/secret/token.txt"],
                }
            )
            with (run.plan / LEDGER_FILE).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(raw, separators=(",", ":")) + "\n")
            with self.assertRaises(LedgerError):
                evaluate_gate(run.root, run.plan)

    def test_tampered_foreign_owned_artifact_makes_cli_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            (run.root / "docs").mkdir()
            (run.root / "docs/foreign.txt").write_text("foreign\n", encoding="utf-8")
            start = append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
            )
            raw = start.to_dict()
            raw.update(
                {
                    "sequence": 2,
                    "event_id": "evt-000002",
                    "kind": "artifact",
                    "files": ["docs/foreign.txt"],
                }
            )
            with (run.plan / LEDGER_FILE).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(raw, separators=(",", ":")) + "\n")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "tools.aiwf_run_guard",
                    "gate",
                    "--root",
                    str(run.root),
                    "--plan-dir",
                    str(run.plan),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("ownership", completed.stderr)

    def test_tampered_handoff_without_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            start = append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
            )
            raw = start.to_dict()
            raw.update(
                {
                    "sequence": 2,
                    "event_id": "evt-000002",
                    "kind": "handoff",
                }
            )
            with (run.plan / LEDGER_FILE).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(raw, separators=(",", ":")) + "\n")
            with self.assertRaises(LedgerError):
                read_events(run.plan)

    def test_tampered_retry_with_invalid_agent_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
            )
            failure = append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="command_failed",
                failure_id="failure-for-tamper",
            )
            raw = failure.to_dict()
            raw.update(
                {
                    "sequence": 3,
                    "event_id": "evt-000003",
                    "agent": "bad agent",
                    "attempt": 2,
                    "kind": "retry",
                    "status": "started",
                    "failure_id": None,
                    "retry_of": "failure-for-tamper",
                }
            )
            with (run.plan / LEDGER_FILE).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(raw, separators=(",", ":")) + "\n")
            with self.assertRaises(LedgerError):
                read_events(run.plan)

    def test_missing_handoff_validation_review_and_artifact_are_gate_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.artifact()
            append_event(run.plan, agent="alice", workstream="core", kind="workstream_started")
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="artifact",
                files=["tools/core/output.txt"],
            )
            (run.root / "tools/core/output.txt").unlink()
            report = evaluate_gate(run.root, run.plan)

        failed = {
            finding.finding_id for finding in report.findings if finding.status == "fail"
        }
        self.assertTrue(
            {"artifacts.exist", "workstreams.handoff", "gate.validation", "gate.review"}
            .issubset(failed)
        )

    def test_resolved_artifact_escape_is_a_gate_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()
            artifact = (run.root / "tools/core/output.txt").resolve()
            outside = (run.root.parent / "outside-output.txt").resolve()
            path_type = type(run.root)
            original_resolve = path_type.resolve

            def resolve_with_escape(path: Path, strict: bool = False) -> Path:
                resolved = original_resolve(path, strict=strict)
                return outside if resolved == artifact else resolved

            with patch.object(path_type, "resolve", resolve_with_escape):
                report = evaluate_gate(run.root, run.plan)

        containment = next(
            item
            for item in report.findings
            if item.finding_id == "artifacts.root_containment"
        )
        self.assertEqual(report.exit_code, 1)
        self.assertEqual(containment.status, "fail")
        self.assertIn("tools/core/output.txt", containment.evidence)
        self.assertNotIn(str(outside), containment.evidence)

    def test_later_artifact_requires_a_fresh_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()
            later = run.artifact("tools/core/later.txt")
            self.assertTrue(later.is_file())
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="artifact",
                files=["tools/core/later.txt"],
            )
            stale = evaluate_gate(run.root, run.plan)
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="handoff",
            )
            refreshed = evaluate_gate(run.root, run.plan)

        stale_handoff = next(
            item for item in stale.findings if item.finding_id == "workstreams.handoff"
        )
        refreshed_handoff = next(
            item for item in refreshed.findings if item.finding_id == "workstreams.handoff"
        )
        self.assertEqual(stale_handoff.status, "fail")
        self.assertIn("stale", stale_handoff.evidence)
        self.assertEqual(refreshed_handoff.status, "pass")

    def test_retry_requires_artifact_and_handoff_in_current_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="command_failed",
                failure_id="post-handoff-failure",
            )
            append_event(
                run.plan,
                agent="bob",
                workstream="core",
                kind="retry",
                retry_of="post-handoff-failure",
            )
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="validation_passed",
            )
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="review_passed",
            )
            report = evaluate_gate(run.root, run.plan)

        handoff = next(
            item for item in report.findings if item.finding_id == "workstreams.handoff"
        )
        self.assertEqual(report.exit_code, 1)
        self.assertEqual(handoff.status, "fail")
        self.assertIn("attempt 2", handoff.evidence)
        self.assertIn("missing current-attempt handoff", handoff.evidence)

    def test_unresolved_failure_invalidates_completed_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="command_failed",
                failure_id="unresolved-after-review",
            )
            report = evaluate_gate(run.root, run.plan)

        failed = {
            finding.finding_id for finding in report.findings if finding.status == "fail"
        }
        self.assertEqual(report.exit_code, 1)
        self.assertTrue(
            {"retry.unresolved_failures", "gate.validation", "gate.review"}.issubset(
                failed
            )
        )

    def test_new_artifact_makes_validation_and_review_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()
            run.artifact("tools/core/later.txt")
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="artifact",
                files=["tools/core/later.txt"],
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="handoff",
            )
            stale = evaluate_gate(run.root, run.plan)
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="validation_passed",
            )
            validation_only = evaluate_gate(run.root, run.plan)
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="review_passed",
            )
            refreshed = evaluate_gate(run.root, run.plan)

        stale_failed = {
            finding.finding_id for finding in stale.findings if finding.status == "fail"
        }
        validation_failed = {
            finding.finding_id
            for finding in validation_only.findings
            if finding.status == "fail"
        }
        self.assertTrue({"gate.validation", "gate.review"}.issubset(stale_failed))
        self.assertNotIn("gate.validation", validation_failed)
        self.assertIn("gate.review", validation_failed)
        self.assertEqual(refreshed.status, "ready")

    def test_first_artifact_timeout_reports_stale_workstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(
                Path(temporary_directory), base_config(first_artifact_seconds=10)
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
                timestamp="2026-07-31T00:00:00Z",
            )
            report = evaluate_gate(
                run.root,
                run.plan,
                now=datetime(2026, 7, 31, 0, 1, tzinfo=timezone.utc),
            )

        liveness = next(
            item
            for item in report.findings
            if item.finding_id == "liveness.first_artifact"
        )
        self.assertEqual(liveness.status, "fail")
        self.assertIn("core", liveness.evidence)

    def test_non_handoff_workstream_is_exempt_from_artifact_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(
                Path(temporary_directory), base_config(first_artifact_seconds=10)
            )
            append_event(
                run.plan,
                agent="coordinator",
                workstream="integration",
                kind="workstream_started",
                timestamp="2026-07-31T00:00:00Z",
            )
            report = evaluate_gate(
                run.root,
                run.plan,
                now=datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc),
            )

        liveness = next(
            item
            for item in report.findings
            if item.finding_id == "liveness.first_artifact"
        )
        self.assertEqual(liveness.status, "pass")
        self.assertNotIn("integration", liveness.evidence)

    def test_heartbeat_timeout_applies_until_current_attempt_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(
                Path(temporary_directory), base_config(heartbeat_seconds=10)
            )
            run.artifact()
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="workstream_started",
                timestamp="2026-07-31T00:00:00Z",
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="artifact",
                files=["tools/core/output.txt"],
                timestamp="2026-07-31T00:00:01Z",
            )
            stale = evaluate_gate(
                run.root,
                run.plan,
                now=datetime(2026, 7, 31, 0, 1, tzinfo=timezone.utc),
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="heartbeat",
                timestamp="2026-07-31T00:00:59Z",
            )
            active = evaluate_gate(
                run.root,
                run.plan,
                now=datetime(2026, 7, 31, 0, 1, tzinfo=timezone.utc),
            )
            append_event(
                run.plan,
                agent="alice",
                workstream="core",
                kind="handoff",
                timestamp="2026-07-31T00:01:00Z",
            )
            complete = evaluate_gate(
                run.root,
                run.plan,
                now=datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc),
            )

        stale_finding = next(
            item for item in stale.findings if item.finding_id == "liveness.heartbeat"
        )
        active_finding = next(
            item for item in active.findings if item.finding_id == "liveness.heartbeat"
        )
        complete_finding = next(
            item for item in complete.findings if item.finding_id == "liveness.heartbeat"
        )
        self.assertEqual(stale_finding.status, "fail")
        self.assertEqual(active_finding.status, "pass")
        self.assertEqual(complete_finding.status, "pass")

    def test_corrupted_ledger_is_invocation_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            (run.plan / LEDGER_FILE).write_text("{not-json}\n", encoding="utf-8")
            with self.assertRaises(LedgerError):
                read_events(run.plan)

    def test_invalid_absolute_configuration_path_is_rejected(self) -> None:
        config = base_config(allowed_paths=["C:/absolute"])
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            plan = root / "plan"
            plan.mkdir()
            source = root / "config.json"
            source.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ConfigError):
                initialize_run(plan, source)

    def test_json_and_markdown_reports_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            run.complete()
            report = evaluate_gate(run.root, run.plan)
            summary = summarize_run(run.plan)
            rendered = (
                render_json(report),
                render_report_markdown(report),
                render_json(summary),
                render_summary_markdown(summary),
            )
            rerendered = (
                render_json(evaluate_gate(run.root, run.plan)),
                render_report_markdown(evaluate_gate(run.root, run.plan)),
                render_json(summarize_run(run.plan)),
                render_summary_markdown(summarize_run(run.plan)),
            )

        self.assertEqual(rendered, rerendered)
        self.assertIn("Retry remaining", rendered[3])

    def test_preflight_is_deterministic_and_read_only(self) -> None:
        first = run_preflight(REPO_ROOT)
        second = run_preflight(REPO_ROOT)
        self.assertEqual(render_json(first), render_json(second))
        self.assertEqual(first.status, "ready")
        self.assertIn("capability.planning", {item.finding_id for item in first.findings})

    def test_planning_preflight_rejects_unsafe_pointer_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            planning = root / ".planning"
            planning.mkdir()
            for unsafe in ("C:/private/outside", "../outside", "nested/plan"):
                (planning / ".active_plan").write_text(unsafe, encoding="utf-8")
                finding = _planning(root)
                self.assertEqual(finding.status, "skip")
                self.assertNotIn("private", finding.evidence)
                self.assertNotIn("outside", finding.evidence)
                self.assertNotIn("nested", finding.evidence)

    def test_cli_exit_codes_zero_one_and_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run = IsolatedRun(Path(temporary_directory))
            incomplete = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "tools.aiwf_run_guard",
                    "gate",
                    "--root",
                    str(run.root),
                    "--plan-dir",
                    str(run.plan),
                    "--format",
                    "json",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            run.complete()
            complete = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "tools.aiwf_run_guard",
                    "gate",
                    "--root",
                    str(run.root),
                    "--plan-dir",
                    str(run.plan),
                    "--format",
                    "markdown",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            invalid = subprocess.run(
                [sys.executable, "-B", "-m", "tools.aiwf_run_guard", "summary"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(incomplete.returncode, 1, incomplete.stderr)
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("required", invalid.stderr.lower())


if __name__ == "__main__":
    unittest.main()
