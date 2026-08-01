"""Concurrent, deterministic execution engine for Template Doctor rules."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from .models import CheckResult, Report, RuleCallable


MAX_WORKERS = 4


def _callable_name(rule: RuleCallable) -> str:
    raw_name = getattr(rule, "rule_id", None) or getattr(
        rule, "__name__", rule.__class__.__name__
    )
    name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(raw_name)).strip("-")
    return name or "anonymous"


def _clean_exception_message(exc: BaseException) -> str:
    message = " ".join(str(exc).split())
    if len(message) > 240:
        message = f"{message[:237]}..."
    return message or "no exception message"


def _execute_rule(index: int, rule: RuleCallable) -> tuple[int, CheckResult]:
    try:
        result = rule()
        if not isinstance(result, CheckResult):
            raise TypeError(
                f"rule returned {type(result).__name__}, expected CheckResult"
            )
        return index, result
    except Exception as exc:  # A failed probe must not cancel sibling probes.
        name = _callable_name(rule)
        return index, CheckResult(
            rule_id=f"engine.rule_exception.{index:03d}.{name}",
            severity="error",
            status="error",
            evidence=(
                f"{type(exc).__name__}: {_clean_exception_message(exc)}"
            ),
            recommendation=(
                "Inspect this rule implementation and rerun Template Doctor."
            ),
        )


def _summary(results: tuple[CheckResult, ...]) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(result.status == "pass" for result in results),
        "failed": sum(result.status == "fail" for result in results),
        "skipped": sum(result.status == "skip" for result in results),
        "errors": sum(result.status == "error" for result in results),
    }


def _report_status(summary: dict[str, int]) -> str:
    if summary["errors"]:
        return "error"
    if summary["failed"]:
        return "not_ready"
    return "ready"


def run_checks(
    root: Path | str,
    rules: Iterable[RuleCallable] | None = None,
    max_workers: int = MAX_WORKERS,
    strict: bool = False,
) -> Report:
    """Run independent rules concurrently and return deterministically ordered results.

    ``max_workers`` is always clamped to the package-wide bound. When ``rules``
    is omitted, the rule registry is built lazily to keep the engine independent
    of individual rule implementations. ``strict`` promotes optional-capability
    findings (such as a missing CodeGraph index) to blocking failures.
    """

    target_root = Path(root).resolve()
    if rules is None:
        from .rules import build_rules

        rules = build_rules(target_root, strict=strict)

    rule_list = list(rules)
    if not rule_list:
        results = (
            CheckResult(
                rule_id="engine.no_rules",
                severity="error",
                status="error",
                evidence="No audit rules were registered.",
                recommendation="Register at least one Template Doctor rule.",
            ),
        )
    else:
        try:
            requested_workers = int(max_workers)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_workers must be an integer") from exc
        if requested_workers < 1:
            raise ValueError("max_workers must be at least 1")
        worker_count = min(requested_workers, MAX_WORKERS, len(rule_list))

        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="template-doctor",
        ) as executor:
            indexed_results = list(
                executor.map(
                    lambda indexed_rule: _execute_rule(*indexed_rule),
                    enumerate(rule_list),
                )
            )
        indexed_results.sort(key=lambda item: (item[1].rule_id, item[0]))
        results = tuple(result for _, result in indexed_results)

    summary = _summary(results)
    return Report(
        root=str(target_root),
        results=results,
        summary=summary,
        status=_report_status(summary),
    )
