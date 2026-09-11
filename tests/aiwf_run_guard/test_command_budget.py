"""Cross-session command-budget contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.aiwf_run_guard.budget import _invokes_shell_command, snapshot_command_budget
from tools.aiwf_run_guard.gate import evaluate_gate
from tools.aiwf_run_guard.ledger import LEDGER_FILE, append_event, initialize_run, read_events
from tools.aiwf_run_guard.models import LedgerError
from tools.aiwf_run_guard.reporters import render_json


REPO_ROOT = Path(__file__).resolve().parents[2]
START = "2026-07-31T00:00:00Z"
END = "2026-07-31T00:10:00Z"


def budget_config(
    *,
    limit: int,
    sources: tuple[str, ...],
    require_validation: bool = False,
    require_review: bool = False,
) -> dict[str, object]:
    return {
        "task_id": "2026-07-31-BUDGET-TEST",
        "retry_limit": 1,
        "workstreams": [
            {
                "id": "integration",
                "owner": "main",
                "owned_paths": [],
                "require_handoff": False,
            }
        ],
        "allowed_paths": ["tools"],
        "forbidden_paths": [],
        "require_validation": require_validation,
        "require_review": require_review,
        "first_artifact_seconds": None,
        "heartbeat_seconds": None,
        "command_budget": {
            "limit": limit,
            "metric": "shell_command_requests",
            "required_sources": list(sources),
        },
    }


class BudgetRun:
    def __init__(self, root: Path, config: dict[str, object]) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.plan = root / "plan"
        self.plan.mkdir()
        source = root / "config.json"
        source.write_text(json.dumps(config), encoding="utf-8")
        initialize_run(self.plan, source)
        append_event(
            self.plan,
            agent="main",
            workstream="integration",
            kind="workstream_started",
        )

    def snapshot(self, sessions: dict[str, Path]):
        return snapshot_command_budget(
            self.plan,
            agent="main",
            workstream="integration",
            sessions=sessions,
            start=START,
            end=END,
        )


def write_session(
    path: Path,
    source_id: str,
    count: int,
    *,
    call_ids: list[str] | None = None,
    secret: str = "",
    first_timestamp: datetime | None = None,
) -> Path:
    start = first_timestamp or datetime(2026, 7, 31, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        timestamp = start + timedelta(seconds=index)
        rows.append(
            {
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": (
                        call_ids[index]
                        if call_ids is not None
                        else f"call-{source_id}-{index:04d}"
                    ),
                    "input": (
                        "await tools.shell_command({command:\"probe "
                        + secret
                        + "\"})"
                    ),
                },
            }
        )
    rows.append(
        {
            "timestamp": START,
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "call_id": f"ignored-{source_id}",
                "input": "await tools.apply_patch('not a shell request')",
            },
        }
    )
    rows.append(
        {
            "timestamp": START,
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "call_id": f"ignored-marker-{source_id}",
                "input": (
                    "const patch = \"tools.shell_command({command:'text only'})\"; "
                    "await tools.apply_patch(patch)"
                ),
            },
        }
    )
    path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def write_rows(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _ts(seconds: int) -> str:
    moment = datetime(2026, 7, 31, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return moment.isoformat().replace("+00:00", "Z")


class CommandBudgetTests(unittest.TestCase):
    def test_shell_classifier_excludes_literals_and_comments(self) -> None:
        self.assertTrue(_invokes_shell_command("await tools.shell_command({command:'x'})"))
        self.assertTrue(_invokes_shell_command("await tools . shell_command ({command:'x'})"))
        self.assertFalse(_invokes_shell_command("const x = 'tools.shell_command({})'"))
        self.assertFalse(_invokes_shell_command("const x = `tools.shell_command({})`"))
        self.assertTrue(
            _invokes_shell_command("const x = `${await tools.shell_command({command:'x'})}`")
        )
        self.assertFalse(_invokes_shell_command("// tools.shell_command({})\nawait tools.apply_patch('x')"))
        self.assertFalse(_invokes_shell_command("/* tools.shell_command({}) */ tools.apply_patch('x')"))
        with self.assertRaises(LedgerError):
            _invokes_shell_command("const run = tools.shell_command; await run({})")
        with self.assertRaises(LedgerError):
            _invokes_shell_command("await tools['shell_command']({})")
        with self.assertRaises(LedgerError):
            _invokes_shell_command("const {shell_command: run} = tools; await run({})")

    def test_shell_classifier_covers_exec_command_like_shell_command(self) -> None:
        self.assertTrue(_invokes_shell_command("await tools.exec_command({command:'x'})"))
        self.assertTrue(_invokes_shell_command("await tools . exec_command ({command:'x'})"))
        self.assertFalse(_invokes_shell_command("const x = 'tools.exec_command({})'"))
        self.assertFalse(_invokes_shell_command("const x = `tools.exec_command({})`"))
        self.assertTrue(
            _invokes_shell_command("const x = `${await tools.exec_command({command:'x'})}`")
        )
        self.assertFalse(_invokes_shell_command("// tools.exec_command({})\nawait tools.apply_patch('x')"))
        self.assertFalse(_invokes_shell_command("/* tools.exec_command({}) */ tools.apply_patch('x')"))
        with self.assertRaises(LedgerError):
            _invokes_shell_command("const run = tools.exec_command; await run({})")
        with self.assertRaises(LedgerError):
            _invokes_shell_command("await tools['exec_command']({})")
        with self.assertRaises(LedgerError):
            _invokes_shell_command("const {exec_command: run} = tools; await run({})")

    def test_current_host_forms_count_once_per_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main",)))
            session = write_rows(
                root / "current-host.jsonl",
                [
                    # Current confirmed form: custom_tool_call named exec whose
                    # input invokes tools.exec_command(...).
                    {
                        "timestamp": _ts(10),
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "call_id": "exec-001",
                            "input": "await tools.exec_command({command:'probe'})",
                        },
                    },
                    # One outer request batching other tool calls with shell
                    # calls counts exactly once.
                    {
                        "timestamp": _ts(20),
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "call_id": "exec-002",
                            "input": (
                                "await tools.web__run({}); "
                                "await tools.exec_command({command:'a'}); "
                                "await tools.shell_command({command:'b'})"
                            ),
                        },
                    },
                    # Named function_call whose tool name is a shell tool is a
                    # direct shell request; arguments are not interpreted.
                    {
                        "timestamp": _ts(30),
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "shell",
                            "call_id": "fn-shell-001",
                            "arguments": '{"command": ["probe"]}',
                        },
                    },
                    # Named function_call for a non-shell tool is not counted.
                    {
                        "timestamp": _ts(40),
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "request_user_input",
                            "call_id": "fn-rui-001",
                            "arguments": '{"question": "tools.exec_command({})"}',
                        },
                    },
                    # Unwrapped top-level host function_call with a shell tool
                    # name counts using its callId identity.
                    {
                        "timestamp": _ts(50),
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-001",
                        "arguments": '{"command": "probe"}',
                    },
                    # Unwrapped non-shell function_call is not counted.
                    {
                        "timestamp": _ts(60),
                        "type": "function_call",
                        "name": "Read",
                        "callId": "wb-002",
                        "arguments": '{"file": "x.py"}',
                    },
                    # Pure-wait tool requests are not shell requests.
                    {
                        "timestamp": _ts(70),
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "call_id": "wait-001",
                            "input": "await tools.wait({seconds: 5})",
                        },
                    },
                    # String-literal and comment mentions never count.
                    {
                        "timestamp": _ts(80),
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "call_id": "str-001",
                            "input": (
                                "const s = 'tools.exec_command({})'; "
                                "await tools.apply_patch(s)"
                            ),
                        },
                    },
                    {
                        "timestamp": _ts(90),
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "call_id": "cmt-001",
                            "input": "// tools.exec_command({})\nawait tools.apply_patch('x')",
                        },
                    },
                ],
            )
            report = run.snapshot({"main": session})

        self.assertEqual(report.exit_code, 0)
        self.assertEqual(report.metadata["total"], 4)
        self.assertEqual(report.metadata["source_counts"], {"main": 4})
        self.assertEqual(report.metadata["unique_call_ids"], 4)

    def test_corrupted_current_host_events_raise(self) -> None:
        cases: list[list[dict[str, object]]] = [
            # A custom_tool_call input that is not a plain string cannot be
            # classified and must not look like a complete zero count.
            [
                {
                    "timestamp": _ts(10),
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": "exec-bad",
                        "input": {"command": "ls"},
                    },
                }
            ],
            # A named-function_call event without a tool name is corrupted.
            [
                {
                    "timestamp": _ts(10),
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "call_id": "fn-noname",
                        "arguments": "{}",
                    },
                }
            ],
            # A shell function_call without any request identity is corrupted.
            [
                {
                    "timestamp": _ts(10),
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "shell",
                        "arguments": "{}",
                    },
                }
            ],
            # An unwrapped shell function_call without call_id/callId fails.
            [
                {
                    "timestamp": _ts(10),
                    "type": "function_call",
                    "name": "Bash",
                    "arguments": "{}",
                }
            ],
            # Indirect exec_command references stay rejected.
            [
                {
                    "timestamp": _ts(10),
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": "exec-alias",
                        "input": "const run = tools.exec_command; await run({})",
                    },
                }
            ],
        ]
        for rows in cases:
            with tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                run = BudgetRun(root, budget_config(limit=5, sources=("main",)))
                session = write_rows(root / "corrupt.jsonl", rows)
                with self.assertRaises(LedgerError):
                    run.snapshot({"main": session})

    def test_window_boundaries_apply_to_new_host_forms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main",)))
            session = write_rows(
                root / "window.jsonl",
                [
                    # One second before the window opens: excluded.
                    {
                        "timestamp": _ts(-1),
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "call_id": "exec-early",
                            "input": "await tools.exec_command({command:'x'})",
                        },
                    },
                    # Exactly at window start: included.
                    {
                        "timestamp": START,
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "shell",
                            "call_id": "fn-at-start",
                            "arguments": "{}",
                        },
                    },
                    # Exactly at window end: included.
                    {
                        "timestamp": END,
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-at-end",
                        "arguments": "{}",
                    },
                    # One second after the window closes: excluded.
                    {
                        "timestamp": _ts(601),
                        "type": "function_call",
                        "name": "bash",
                        "callId": "wb-late",
                        "arguments": "{}",
                    },
                ],
            )
            report = run.snapshot({"main": session})

        self.assertEqual(report.metadata["total"], 2)
        self.assertEqual(report.metadata["unique_call_ids"], 2)

    def test_duplicate_ids_across_old_and_new_forms_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main", "reviewer")))
            legacy = write_session(root / "legacy.jsonl", "main", 1, call_ids=["dup"])
            modern = write_rows(
                root / "modern.jsonl",
                [
                    {
                        "timestamp": START,
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "call_id": "dup",
                            "input": "await tools.exec_command({command:'x'})",
                        },
                    }
                ],
            )
            with self.assertRaises(LedgerError):
                run.snapshot({"main": legacy, "reviewer": modern})

    def test_mixed_legacy_and_current_formats_replay_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main", "reviewer")))
            legacy = write_session(root / "legacy.jsonl", "main", 2)
            modern = write_rows(
                root / "modern.jsonl",
                [
                    {
                        "timestamp": _ts(30),
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "call_id": "exec-mixed",
                            "input": "await tools.exec_command({command:'x'})",
                        },
                    },
                    {
                        "timestamp": _ts(31),
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-mixed",
                        "arguments": "{}",
                    },
                ],
            )
            legacy_only = run.snapshot({"main": legacy, "reviewer": write_rows(root / "empty-legacy.jsonl", [
                {
                    "timestamp": START,
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": "legacy-keep",
                        "input": "await tools.apply_patch('not shell')",
                    },
                }
            ])})
            combined = run.snapshot({"main": legacy, "reviewer": modern})

        # The historical replay alone counts only shell_command requests; the
        # combined replay counts old and new formats once per request.
        self.assertEqual(legacy_only.exit_code, 0)
        self.assertEqual(legacy_only.metadata["total"], 2)
        self.assertEqual(combined.exit_code, 0)
        self.assertEqual(combined.metadata["total"], 4)
        self.assertEqual(combined.metadata["source_counts"], {"main": 2, "reviewer": 2})


    def test_historical_shape_aggregates_134_and_redacts_command_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(
                root,
                budget_config(limit=90, sources=("main", "reviewer", "tester")),
            )
            sessions = {
                "main": write_session(root / "main.jsonl", "main", 67, secret="MAIN_SECRET"),
                "reviewer": write_session(root / "reviewer.jsonl", "reviewer", 49),
                "tester": write_session(root / "tester.jsonl", "tester", 18),
            }
            first = run.snapshot(sessions)
            second = run.snapshot(sessions)
            rendered = render_json(first)

        self.assertEqual(first.exit_code, 1)
        self.assertEqual(first.metadata["total"], 134)
        self.assertEqual(first.metadata["unique_call_ids"], 134)
        self.assertEqual(first.metadata["source_counts"], {"main": 67, "reviewer": 49, "tester": 18})
        self.assertEqual(rendered, render_json(second))
        self.assertNotIn("MAIN_SECRET", rendered)
        self.assertNotIn("main.jsonl", rendered)

    def test_exact_limit_passes_and_limit_plus_one_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            sessions = {
                "main": write_session(root / "main.jsonl", "main", 2),
                "reviewer": write_session(root / "reviewer.jsonl", "reviewer", 1),
            }
            exact = BudgetRun(root / "exact", budget_config(limit=3, sources=("main", "reviewer")))
            over = BudgetRun(root / "over", budget_config(limit=2, sources=("main", "reviewer")))
            exact_report = exact.snapshot(sessions)
            over_report = over.snapshot(sessions)

        self.assertEqual(exact_report.exit_code, 0)
        self.assertEqual(over_report.exit_code, 1)

    def test_missing_source_and_duplicate_call_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main", "reviewer")))
            main = write_session(root / "main.jsonl", "main", 1, call_ids=["duplicate"])
            reviewer = write_session(root / "reviewer.jsonl", "reviewer", 1, call_ids=["duplicate"])
            with self.assertRaises(LedgerError):
                run.snapshot({"main": main})
            with self.assertRaises(LedgerError):
                run.snapshot({"main": main, "reviewer": reviewer})

    def test_malformed_evidence_and_window_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=2, sources=("main",)))
            malformed = root / "malformed.jsonl"
            malformed.write_text("{bad-json}\n", encoding="utf-8")
            with self.assertRaises(LedgerError):
                run.snapshot({"main": malformed})
            session = write_session(
                root / "window.jsonl",
                "main",
                2,
                first_timestamp=datetime(2026, 7, 30, 23, 59, 59, tzinfo=timezone.utc),
            )
            report = run.snapshot({"main": session})

        self.assertEqual(report.metadata["total"], 1)

    def test_gate_requires_all_sources_and_post_review_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(
                root,
                budget_config(
                    limit=5,
                    sources=("main", "reviewer"),
                    require_validation=True,
                    require_review=True,
                ),
            )
            append_event(run.plan, agent="main", workstream="integration", kind="validation_passed")
            pre_review = evaluate_gate(run.root, run.plan)
            append_event(run.plan, agent="main", workstream="integration", kind="review_passed")
            append_event(
                run.plan,
                agent="main",
                workstream="integration",
                kind="command_snapshot",
                source_id="main",
                metric_value=2,
            )
            missing = evaluate_gate(run.root, run.plan)
            sessions = {
                "main": write_session(root / "main.jsonl", "main", 2),
                "reviewer": write_session(root / "reviewer.jsonl", "reviewer", 1),
            }
            run.snapshot(sessions)
            current = evaluate_gate(run.root, run.plan)
            append_event(run.plan, agent="main", workstream="integration", kind="review_passed")
            stale = evaluate_gate(run.root, run.plan)
            run.snapshot(sessions)
            refreshed = evaluate_gate(run.root, run.plan)

        missing_budget = next(item for item in missing.findings if item.finding_id == "budget.commands")
        pre_review_budget = next(
            item for item in pre_review.findings if item.finding_id == "budget.commands"
        )
        stale_budget = next(item for item in stale.findings if item.finding_id == "budget.commands")
        self.assertEqual(missing_budget.status, "fail")
        self.assertEqual(pre_review_budget.status, "skip")
        self.assertIn("missing=reviewer", missing_budget.evidence)
        self.assertEqual(current.status, "ready")
        self.assertEqual(stale_budget.status, "fail")
        self.assertIn("stale=main,reviewer", stale_budget.evidence)
        self.assertEqual(refreshed.status, "ready")

    def test_v1_config_and_ledger_remain_readable(self) -> None:
        config = budget_config(limit=1, sources=("main",))
        config.pop("command_budget")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, config)
            ledger = run.plan / LEDGER_FILE
            raw = json.loads(ledger.read_text(encoding="utf-8"))
            raw.pop("source_id")
            raw.pop("metric_value")
            ledger.write_text(json.dumps(raw, separators=(",", ":")) + "\n", encoding="utf-8")
            events = read_events(run.plan)
            report = evaluate_gate(run.root, run.plan)

        self.assertEqual(len(events), 1)
        budget_finding = next(item for item in report.findings if item.finding_id == "budget.commands")
        self.assertEqual(budget_finding.status, "skip")
        self.assertEqual(report.status, "ready")

    def test_session_strings_with_unicode_line_separators_stay_intact(self) -> None:
        # Real session JSONL may contain raw U+2028/U+0085 inside string
        # literals. Splitting on anything but the newline record delimiter
        # would corrupt the JSON and must not happen.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main",)))
            payload_input = (
                "await tools.exec_command({command:'probe \u2028 next \u0085 line'})"
            )
            rows = [
                {
                    "timestamp": _ts(10),
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "exec",
                        "call_id": "exec-u2028",
                        "input": payload_input,
                    },
                },
                {
                    "timestamp": _ts(11),
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "exec",
                        "call_id": "exec-after",
                        "input": "await tools.exec_command({command:'ok'})",
                    },
                },
            ]
            body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
            assert "\u2028" in body and "\u0085" in body
            session = root / "unicode-line-seps.jsonl"
            session.write_text(body, encoding="utf-8")
            report = run.snapshot({"main": session})

        self.assertEqual(report.exit_code, 0)
        self.assertEqual(report.metadata["total"], 2)

    def test_numeric_epoch_millisecond_timestamps_are_supported(self) -> None:
        # Host session events carry Unix epoch milliseconds; ISO strings stay
        # supported; implausible numerics are corrupted evidence.
        window_start_ms = 1788965320857  # inside-window reference (int millis)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main",)))
            start_iso = (
                datetime.fromtimestamp(window_start_ms / 1000, tz=timezone.utc)
                - timedelta(seconds=30)
            ).isoformat()
            end_iso = (
                datetime.fromtimestamp(window_start_ms / 1000, tz=timezone.utc)
                + timedelta(seconds=30)
            ).isoformat()
            session = write_rows(
                root / "millis.jsonl",
                [
                    {
                        "timestamp": window_start_ms,
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-millis",
                        "arguments": "{}",
                    },
                    {
                        "timestamp": window_start_ms + 1000,
                        "type": "function_call",
                        "name": "bash",
                        "callId": "wb-millis-2",
                        "arguments": "{}",
                    },
                    {
                        "timestamp": window_start_ms - 60_000,
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-millis-early",
                        "arguments": "{}",
                    },
                ],
            )
            report = snapshot_command_budget(
                run.plan,
                agent="main",
                workstream="integration",
                sessions={"main": session},
                start=start_iso,
                end=end_iso,
            )
            seconds_plan = BudgetRun(
                root / "seconds", budget_config(limit=5, sources=("main",))
            )
            seconds_session = write_rows(
                root / "seconds.jsonl",
                [
                    {
                        "timestamp": 1_788_965_320,  # epoch seconds: not millis
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-seconds",
                        "arguments": "{}",
                    }
                ],
            )
            with self.assertRaises(LedgerError):
                snapshot_command_budget(
                    seconds_plan.plan,
                    agent="main",
                    workstream="integration",
                    sessions={"main": seconds_session},
                    start=start_iso,
                    end=end_iso,
                )

        self.assertEqual(report.exit_code, 0)
        self.assertEqual(report.metadata["total"], 2)

    def test_corrupted_payload_and_extreme_timestamps_raise(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run = BudgetRun(root, budget_config(limit=5, sources=("main",)))
            corrupted_payload = write_rows(
                root / "corrupt-payload.jsonl",
                [
                    {
                        "timestamp": START,
                        "type": "response_item",
                        # A wrapped event whose payload is not an object
                        # cannot be classified: explicit corruption.
                        "payload": "not-an-object",
                    },
                    {
                        "timestamp": START,
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "call_id": "after-corrupt",
                            "input": "await tools.exec_command({command:'x'})",
                        },
                    },
                ],
            )
            infinite_timestamp = write_rows(
                root / "infinite-timestamp.jsonl",
                [
                    {
                        "timestamp": float("inf"),
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-inf",
                        "arguments": "{}",
                    }
                ],
            )
            huge_timestamp = write_rows(
                root / "huge-timestamp.jsonl",
                [
                    {
                        "timestamp": 1e300,
                        "type": "function_call",
                        "name": "Bash",
                        "callId": "wb-huge",
                        "arguments": "{}",
                    }
                ],
            )
            with self.assertRaises(LedgerError):
                run.snapshot({"main": corrupted_payload})
            with self.assertRaises(LedgerError):
                run.snapshot({"main": infinite_timestamp})
            with self.assertRaises(LedgerError):
                run.snapshot({"main": huge_timestamp})

    def test_budget_cli_exit_codes_zero_one_and_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            session = write_session(root / "main.jsonl", "main", 1)
            ready = BudgetRun(root / "ready", budget_config(limit=1, sources=("main",)))
            over = BudgetRun(root / "over", budget_config(limit=0, sources=("main",)))

            def invoke(run: BudgetRun, source: Path) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "tools.aiwf_run_guard",
                        "budget",
                        "--plan-dir",
                        str(run.plan),
                        "--agent",
                        "main",
                        "--workstream",
                        "integration",
                        "--source",
                        f"main={source}",
                        "--start",
                        START,
                        "--end",
                        END,
                    ],
                    cwd=REPO_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )

            zero = invoke(ready, session)
            one = invoke(over, session)
            two = invoke(ready, root / "missing.jsonl")

        self.assertEqual(zero.returncode, 0, zero.stderr)
        self.assertEqual(one.returncode, 1, one.stderr)
        self.assertEqual(two.returncode, 2)
        self.assertNotIn(str(root), two.stderr)


if __name__ == "__main__":
    unittest.main()
