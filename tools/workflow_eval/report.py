"""Aggregate graded trial records into a deterministic Markdown comparison.

The report closes the evidence loop: it distinguishes frozen-validation
results from real trial runs, lists unreadable result files as broken
evidence instead of skipping them silently, and states explicitly whether
the expected six trial results (three tasks x two groups) are present.

Three different questions are answered separately, because conflating them
is exactly how "six JSON files exist" gets mistaken for "a valid
comparison was run":

1. **Record structure** — is every record internally consistent, is the
   expected slot set present, and is the batch labelled consistently?
2. **Trial protocol validity** — did the coordinator attest each run as a
   valid independent trial (VALID), and does the record carry the audit
   basis behind that claim? Trials with no attestation are UNVERIFIED and
   never fill a valid slot.
3. **Functional outcome** — how did the ``VALID`` trials actually grade
   (ACCEPT / REJECT)?

A slot only counts as filled when its record is internally consistent: the
outer verdict, the acceptor verdict, the native exit code, and the executed
scenarios must all agree; budgets must be finite and non-negative; and the
recorded source SHA must be the baseline the task locks for that run kind
(pre-fix for trials and for pre-fix REJECT freeze evidence, the historical
fix for fixed ACCEPT freeze evidence).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re

from .tasks import TASK_ORDER, TASKS

_UNKNOWN = "unknown (not measurable in this environment)"
EXPECTED_TRIAL_RESULTS = len(TASK_ORDER) * 2

VALIDITY_VALID = "VALID"
VALIDITY_INVALID = "INVALID"
VALIDITY_UNVERIFIED = "UNVERIFIED"
_VALIDITY_STATES = (VALIDITY_VALID, VALIDITY_INVALID, VALIDITY_UNVERIFIED)


def _load_records(results_dir: Path) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    records: list[dict[str, object]] = []
    broken: list[dict[str, str]] = []
    if not results_dir.is_dir():
        return records, [{"path": str(results_dir), "problem": "results directory does not exist"}]
    for path in sorted(results_dir.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            broken.append({"path": path.name, "problem": f"{type(exc).__name__}: {exc}"})
            continue
        if not isinstance(value, dict) or value.get("record_type") != "graded_trial":
            broken.append({"path": path.name, "problem": "not a graded_trial record"})
            continue
        records.append(value)
    return records, broken


def _budget_problems(record: dict[str, object]) -> list[str]:
    """Check coordinator-recorded budget data; empty list means usable.

    Values must be finite and non-negative: a type-only check would let a
    forged or corrupted negative budget count as recorded evidence.
    """

    problems: list[str] = []
    budget = record.get("budget") if isinstance(record.get("budget"), dict) else {}
    elapsed = budget.get("elapsed_seconds")
    requests = budget.get("shell_requests")
    interventions = budget.get("human_interventions")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        problems.append("trial budget elapsed_seconds must be a finite non-negative number")
    if isinstance(requests, bool) or not isinstance(requests, int) or requests < 0:
        problems.append("trial budget shell_requests must be a non-negative integer")
    if not (isinstance(interventions, str) and interventions.strip()):
        problems.append("trial budget missing human_interventions")
    return problems


def _baseline_problem(record: dict[str, object]) -> str | None:
    """Check the recorded source SHA against the task's locked baselines.

    Trial records must name the pre-fix baseline the trial started from.
    Freeze records must additionally distinguish the two locked revisions:
    pre-fix REJECT evidence has to come from the pre-fix commit and fixed
    ACCEPT evidence from the historical fix commit, so freeze evidence cannot
    be assembled from two runs of the same revision.
    """

    task = TASKS.get(str(record.get("task_id")))
    if task is None:
        return f"unknown task_id {record.get('task_id')!r}"
    source_sha = record.get("source_sha")
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        return f"record missing a full 40-hex source_sha (got {source_sha!r})"
    run_kind = record.get("run_kind")
    verdict = record.get("verdict")
    if run_kind == "trial":
        if source_sha != task.pre_fix_sha:
            return "trial record does not use the task's locked pre-fix baseline"
        return None
    if run_kind == "freeze":
        if verdict == "ACCEPT" and source_sha != task.fix_sha:
            return "fixed-ACCEPT freeze evidence does not match the task's locked fix SHA"
        if verdict == "REJECT" and source_sha != task.pre_fix_sha:
            return "pre-fix REJECT freeze evidence does not match the task's locked pre-fix SHA"
        if verdict not in {"ACCEPT", "REJECT"}:
            return None
        return None
    return f"unknown run_kind {run_kind!r}"


def _record_problems(record: dict[str, object]) -> list[str]:
    """Check one record for internal consistency; empty list means usable.

    A slot only counts as filled when its record is internally consistent:
    the outer verdict and the acceptor verdict agree, the verdict matches the
    native exit code, the executed scenarios support it (every scenario
    passed for ACCEPT, at least one failed for REJECT), the recorded baseline
    is the one the task locks for this run kind, and trial records carry
    finite non-negative coordinator-recorded budget data. This prevents an
    ACCEPT wrapper around BLOCKED infrastructure, empty scenarios, or
    contradictory REJECT evidence from counting as evidence.
    """

    problems: list[str] = []
    verdict = record.get("verdict")
    acceptor = record.get("acceptor") if isinstance(record.get("acceptor"), dict) else {}
    status = acceptor.get("acceptor_status")
    acceptor_verdict = acceptor.get("verdict")
    exit_code = record.get("acceptor_exit_code")
    scenarios = acceptor.get("scenarios")
    scenarios = scenarios if isinstance(scenarios, list) else []
    if status != "OK":
        problems.append(f"acceptor_status={status!r}: infrastructure, not a verdict")
    if acceptor_verdict is not None and acceptor_verdict != verdict:
        problems.append(
            f"record verdict {verdict!r} disagrees with acceptor verdict {acceptor_verdict!r}"
        )
    if verdict == "ACCEPT":
        if exit_code != 0:
            problems.append(f"ACCEPT with acceptor_exit_code={exit_code!r}")
        if not scenarios:
            problems.append("ACCEPT with no executed scenarios")
        elif not all(
            isinstance(item, dict) and item.get("pass") for item in scenarios
        ):
            problems.append("ACCEPT with failing scenarios")
        if not record.get("scope_clean"):
            problems.append("ACCEPT with scope violations")
    elif verdict == "REJECT":
        if exit_code != 1:
            problems.append(f"REJECT with acceptor_exit_code={exit_code!r}")
        if not scenarios:
            problems.append("REJECT with no executed scenarios")
        elif not any(
            isinstance(item, dict) and not item.get("pass") for item in scenarios
        ):
            problems.append("REJECT with no failing scenario")
    elif verdict == "BLOCKED":
        problems.append("BLOCKED result carries no candidate evidence")
    else:
        problems.append(f"unknown verdict {verdict!r}")
    if record.get("run_kind") == "trial":
        problems.extend(_budget_problems(record))
    baseline_problem = _baseline_problem(record)
    if baseline_problem is not None:
        problems.append(baseline_problem)
    return problems


def trial_validity(record: dict[str, object]) -> tuple[str, str]:
    """Return ``(status, basis)`` for one record's protocol validity.

    Anything absent, malformed, or unsupported degrades to UNVERIFIED. That
    direction is deliberate: an unreadable attestation must never be read as
    a clean run, and a record that predates the attestation requirement must
    not silently count as valid evidence.
    """

    raw = record.get("trial_validity")
    if not isinstance(raw, dict) or raw.get("status") is None:
        return VALIDITY_UNVERIFIED, "no coordinator validity attestation present"
    status = raw.get("status")
    if status not in _VALIDITY_STATES:
        return VALIDITY_UNVERIFIED, f"unrecognised validity status {status!r}"
    basis = raw.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        return VALIDITY_UNVERIFIED, "validity attestation carries no audit basis"
    return str(status), basis.strip()


def _valid_slot_problems(
    record: dict[str, object], structural_problems: list[str]
) -> list[str]:
    """Return why a trial record cannot fill a *valid* comparison slot.

    Four independent gates, each with its own reason so the report can say
    which one failed instead of a single opaque "not valid":

    - the record is internally consistent (structure, budget, baseline);
    - the coordinator attested the run VALID rather than INVALID/UNVERIFIED;
    - the pre-scoring Git root probe passed (``trial_isolated``);
    - the candidate stayed inside its allowed paths.
    """

    if record.get("run_kind") != "trial":
        return []
    problems: list[str] = []
    if structural_problems:
        problems.append("record is not internally consistent")
    status, _ = trial_validity(record)
    if status != VALIDITY_VALID:
        problems.append(f"trial protocol validity is {status}, not VALID")
    if record.get("trial_isolated") is not True:
        problems.append("pre-scoring Git root probe did not pass")
    if not record.get("scope_clean"):
        problems.append("candidate changed files outside the allowed paths")
    return problems


def _completeness(records: list[dict[str, object]]) -> dict[str, object]:
    trials = [item for item in records if item.get("run_kind") == "trial"]
    freezes = [item for item in records if item.get("run_kind") == "freeze"]
    problems = {index: _record_problems(item) for index, item in enumerate(records)}
    consistent = [
        item
        for index, item in enumerate(records)
        if not problems[index]
    ]
    consistent_trials = [item for item in consistent if item.get("run_kind") == "trial"]
    seen = {
        (str(item.get("task_id")), str(item.get("group")))
        for item in consistent_trials
        if item.get("verdict") in {"ACCEPT", "REJECT"}
    }
    expected = {
        (task_id, group)
        for task_id in TASK_ORDER
        for group in ("control", "experiment")
    }
    missing = sorted(f"{task}/{group}" for task, group in expected - seen)
    unexpected = sorted(f"{task}/{group}" for task, group in seen - expected)

    # Protocol validity is counted separately from structure: a structurally
    # perfect record whose run was never independently validated is not a
    # comparison result.
    validity_problems = {
        index: _valid_slot_problems(item, problems[index])
        for index, item in enumerate(records)
        if item.get("run_kind") == "trial"
    }
    valid_records = [
        item
        for index, item in enumerate(records)
        if item.get("run_kind") == "trial" and not validity_problems.get(index)
    ]
    invalid_count = sum(
        1
        for item in consistent_trials
        if trial_validity(item)[0] == VALIDITY_INVALID
    )
    unverified_count = sum(
        1
        for item in consistent_trials
        if trial_validity(item)[0] == VALIDITY_UNVERIFIED
    )
    valid_outcomes = {
        "ACCEPT": sum(1 for item in valid_records if item.get("verdict") == "ACCEPT"),
        "REJECT": sum(1 for item in valid_records if item.get("verdict") == "REJECT"),
    }
    valid_seen = {
        (str(item.get("task_id")), str(item.get("group")))
        for item in valid_records
        if item.get("verdict") in {"ACCEPT", "REJECT"}
    }
    missing_valid = sorted(
        f"{task}/{group}" for task, group in expected - valid_seen
    )

    freeze_accept = {
        str(item.get("task_id"))
        for item in consistent
        if item.get("run_kind") == "freeze" and item.get("verdict") == "ACCEPT"
    }
    freeze_reject = {
        str(item.get("task_id"))
        for item in consistent
        if item.get("run_kind") == "freeze" and item.get("verdict") == "REJECT"
    }
    missing_freeze = sorted(
        f"{task_id}: pre-fix REJECT evidence"
        for task_id in TASK_ORDER
        if task_id not in freeze_reject
    ) + sorted(
        f"{task_id}: fixed ACCEPT evidence"
        for task_id in TASK_ORDER
        if task_id not in freeze_accept
    )

    trial_labels = sorted({str(item.get("label")) for item in consistent_trials})
    inconsistent_batch = len(trial_labels) > 1

    # Structure completeness: enough internally consistent trial records, the
    # right slots, frozen acceptors validated on both locked revisions, and a
    # single batch label.
    structure_complete = (
        len(consistent_trials) == EXPECTED_TRIAL_RESULTS
        and not unexpected
        and len(seen) == EXPECTED_TRIAL_RESULTS
        and not missing_freeze
        and not inconsistent_batch
    )
    # Comparison completeness additionally requires every slot to be a valid
    # independent run. Functional failures (REJECT) are allowed.
    complete = structure_complete and len(valid_records) == EXPECTED_TRIAL_RESULTS
    return {
        "trial_results_present": len(consistent_trials),
        "trial_results_expected": EXPECTED_TRIAL_RESULTS,
        "missing_trial_slots": missing,
        "unexpected_trial_slots": unexpected,
        "structure_complete": structure_complete,
        "valid_trial_results_present": len(valid_records),
        "invalid_trial_results": invalid_count,
        "unverified_trial_results": unverified_count,
        "missing_valid_trial_slots": missing_valid,
        "valid_outcomes": valid_outcomes,
        "validity_problems": {
            str(index): problem_list
            for index, problem_list in validity_problems.items()
            if problem_list
        },
        "frozen_validation_results": len(freezes),
        "missing_freeze_evidence": missing_freeze,
        "inconsistent_batch": inconsistent_batch,
        "trial_batch_labels": trial_labels,
        "inconsistent_records": {
            str(index): problem_list
            for index, problem_list in problems.items()
            if problem_list
        },
        "complete": complete,
    }


def render_report(
    records: list[dict[str, object]],
    *,
    run_label: str,
    broken: list[dict[str, str]] | None = None,
) -> str:
    broken = broken or []
    order = {task_id: index for index, task_id in enumerate(TASK_ORDER)}
    group_rank = {"experiment": 0, "control": 1}
    rows = sorted(
        records,
        key=lambda item: (
            order.get(str(item.get("task_id")), 99),
            group_rank.get(str(item.get("group")), 9),
            str(item.get("label")),
        ),
    )
    completeness = _completeness(records)
    structure_text = (
        "complete"
        if completeness["structure_complete"]
        else f"INCOMPLETE — {completeness['trial_results_present']} of "
        f"{completeness['trial_results_expected']} consistent trial records present"
    )
    validity_text = (
        f"{completeness['valid_trial_results_present']} of "
        f"{completeness['trial_results_expected']} VALID "
        f"({completeness['invalid_trial_results']} INVALID, "
        f"{completeness['unverified_trial_results']} UNVERIFIED)"
    )
    outcomes = completeness["valid_outcomes"]
    outcomes_text = (
        f"{outcomes['ACCEPT']} ACCEPT / {outcomes['REJECT']} REJECT"
        if completeness["valid_trial_results_present"]
        else "no valid trials to score"
    )
    comparison_text = (
        "complete — a valid three-task comparison"
        if completeness["complete"]
        else "NOT complete — the three-task comparison is not established"
    )
    lines: list[str] = [
        f"# Workflow Comparison Report — {run_label}",
        "",
        f"- Record structure: **{structure_text}**",
        f"- Trial protocol validity: **{validity_text}**",
        f"- Functional outcome (VALID trials only): **{outcomes_text}**",
        f"- Valid comparison: **{comparison_text}**",
        "",
        "These three questions are answered separately on purpose. A full set",
        "of well-formed result files proves only that records exist; it is not",
        "evidence that the trials ran independently, and neither substitutes",
        "for the functional outcome.",
        "",
        "Deterministic comparison of independent trial runs. Grades come from",
        "frozen acceptors rerun on the main thread; budgets and interventions",
        "are recorded by the trial coordinator. Data the environment cannot",
        "measure is marked unknown, never guessed. Frozen-acceptance results",
        "(`run_kind=freeze`) are tool validation records, not trial outcomes.",
        "",
        "| Task | Group | Kind | Verdict | Scenarios | Scope | Elapsed (s) | Shell requests | Human interventions |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for record in rows:
        acceptor = record.get("acceptor", {})
        scenarios = acceptor.get("scenarios", []) if isinstance(acceptor, dict) else []
        passed = sum(1 for item in scenarios if item.get("pass"))
        scope = record.get("scope", {})
        violations = scope.get("scope_violations", []) if isinstance(scope, dict) else []
        scope_text = (
            "clean"
            if record.get("scope_clean")
            else f"violations: {', '.join(map(str, violations)) or 'removed paths out of scope'}"
        )
        budget = record.get("budget", {}) if isinstance(record.get("budget"), dict) else {}
        elapsed = budget.get("elapsed_seconds", _UNKNOWN)
        requests = budget.get("shell_requests", _UNKNOWN)
        interventions = budget.get("human_interventions", "none recorded")
        lines.append(
            f"| {record.get('task_id')} | {record.get('group')} | {record.get('run_kind')} "
            f"| {record.get('verdict')} | {passed}/{len(scenarios)} | {scope_text} "
            f"| {elapsed} | {requests} | {interventions} |"
        )
    lines.extend(["", "## Scenario detail", ""])
    for record in rows:
        lines.append(
            f"### {record.get('task_id')} — {record.get('group')} — {record.get('run_kind')} ({record.get('label')})"
        )
        lines.append("")
        acceptor = record.get("acceptor", {})
        scenarios = acceptor.get("scenarios", []) if isinstance(acceptor, dict) else []
        for scenario in scenarios:
            marker = "pass" if scenario.get("pass") else "FAIL"
            lines.append(
                f"- [{marker}] {scenario.get('name')}: expected {scenario.get('expectation')}; "
                f"observed {scenario.get('observed')}"
            )
        if acceptor.get("acceptor_status") == "BLOCKED" or record.get("verdict") == "BLOCKED":
            lines.append(
                f"- [BLOCKED] acceptor could not run: {acceptor.get('message', 'see record')}"
            )
        scope = record.get("scope", {})
        if isinstance(scope, dict):
            lines.append(
                f"- Changed files: {', '.join(map(str, scope.get('changed_files', []))) or 'none'}"
            )
            lines.append(
                f"- Added files: {', '.join(map(str, scope.get('added_files', []))) or 'none'}"
            )
            if scope.get("scope_violations"):
                lines.append(
                    f"- Scope violations: {', '.join(map(str, scope['scope_violations']))}"
                )
        if record.get("run_kind") == "trial":
            status, basis = trial_validity(record)
            lines.append(f"- Trial protocol validity: {status} — {basis}")
            if record.get("trial_isolated") is not None:
                lines.append(
                    "- Pre-scoring Git root probe: "
                    f"{'passed' if record.get('trial_isolated') else 'failed'} "
                    "(a prerequisite for validity, not evidence of independence)"
                )
        if isinstance(record.get("budget"), dict) and record["budget"]:
            lines.append(
                f"- Budget: {json.dumps(record['budget'], ensure_ascii=False, sort_keys=True)}"
            )
        if isinstance(record.get("notes"), dict) and record["notes"]:
            lines.append(
                f"- Notes: {json.dumps(record['notes'], ensure_ascii=False, sort_keys=True)}"
            )
        lines.append("")

    if broken:
        lines.extend(["## Broken evidence files", ""])
        for item in broken:
            lines.append(f"- `{item['path']}`: {item['problem']}")
        lines.append("")

    inconsistent = completeness.get("inconsistent_records", {})
    if inconsistent:
        lines.extend(["## Inconsistent evidence records", ""])
        for index_text, problem_list in sorted(
            inconsistent.items(), key=lambda item: int(item[0])
        ):
            record = records[int(index_text)]
            identity = (
                f"{record.get('task_id')} / {record.get('group')} / "
                f"{record.get('run_kind')} / {record.get('label')}"
            )
            for problem in problem_list:
                lines.append(f"- `{identity}`: {problem}")
        lines.append("")

    missing = completeness["missing_trial_slots"]
    if completeness["frozen_validation_results"] == 0:
        lines.extend(
            [
                "## Frozen-acceptance warning",
                "",
                "No frozen-validation results are present in this evidence set.",
                "Acceptors must have rejected each pre-fix tree and accepted each",
                "historical fix before any trial verdict can be trusted.",
                "",
            ]
        )

    validity_problems = completeness.get("validity_problems", {})
    if validity_problems:
        lines.extend(
            [
                "## Why runs do not count as valid trials",
                "",
                "These records exist and may grade fine, but they cannot fill a",
                "valid comparison slot:",
                "",
            ]
        )
        for index_text, problem_list in sorted(
            validity_problems.items(), key=lambda item: int(item[0])
        ):
            record = records[int(index_text)]
            status, basis = trial_validity(record)
            identity = (
                f"{record.get('task_id')} / {record.get('group')} / "
                f"{record.get('label')}"
            )
            lines.append(f"- `{identity}` — {status}: {basis}")
            for problem in problem_list:
                lines.append(f"  - {problem}")
        lines.append("")
        missing_valid = completeness["missing_valid_trial_slots"]
        if missing_valid:
            lines.append(
                f"Valid trial slots still unfilled: {', '.join(map(str, missing_valid))}"
            )
            lines.append("")
    lines.extend(
        [
            "## Data provenance and limitations",
            "",
            "- Grades: frozen acceptors (version recorded per result), rerun on the main",
            "  thread after each trial; trial agents cannot modify acceptors.",
            "- Elapsed time and shell-request counts: recorded by the trial coordinator",
            "  from the trial session; wall-clock limits are enforced there.",
            f"- Token usage, cost, and rework counts: {_UNKNOWN}.",
            "- Source snapshots: exported via `git archive` from locked commits into",
            "  self-contained single-commit Git repositories, so the exported tree",
            "  itself carries no answer-recoverable history. That guarantee covers the",
            "  exported copy only. Trial independence is a separate judgement: each run",
            "  is audited on every tool channel (not only shell calls) by",
            "  `tools/workflow_eval/audit.py`, and the coordinator records the result as",
            "  `trial_validity` (VALID/INVALID/UNVERIFIED) with its audit basis. This",
            "  report counts a slot as valid only for an attested VALID run whose",
            "  pre-scoring Git root probe passed and whose candidate stayed in scope;",
            "  record structure alone is never evidence of trial isolation.",
            "- Scope baselines: kept by the coordinator outside the candidate tree;",
            "  candidates never decide their own comparison baseline.",
            "- Trial outcomes are exploratory for these repository tasks; a single",
            "  round does not establish a general workflow effect.",
            "",
        ]
    )
    if missing:
        lines.append(f"Missing trial slots: {', '.join(map(str, missing))}")
        lines.append("")
    return "\n".join(lines)


def write_report(results_dir: Path, output: Path, *, run_label: str) -> dict[str, object]:
    records, broken = _load_records(results_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_report(records, run_label=run_label, broken=broken),
        encoding="utf-8",
    )
    completeness = _completeness(records)
    return {
        "status": "PASS" if completeness["complete"] and not broken else "PASS_INCOMPLETE",
        "structure_status": (
            "PASS"
            if completeness["structure_complete"] and not broken
            else "PASS_INCOMPLETE"
        ),
        "report_path": str(output),
        "completeness": completeness,
        "broken_evidence": broken,
    }
