"""Data contracts for Template Doctor checks and reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


CHECK_STATUSES = frozenset({"pass", "fail", "skip", "error"})
SEVERITIES = frozenset({"info", "warning", "error"})
REPORT_STATUSES = frozenset({"ready", "not_ready", "error"})


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The stable, serializable outcome of one independent audit rule."""

    rule_id: str
    severity: str
    status: str
    evidence: str
    recommendation: str

    def __post_init__(self) -> None:
        if not self.rule_id or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"unsupported severity {self.severity!r}; "
                f"expected one of {sorted(SEVERITIES)}"
            )
        if self.status not in CHECK_STATUSES:
            raise ValueError(
                f"unsupported status {self.status!r}; "
                f"expected one of {sorted(CHECK_STATUSES)}"
            )
        if not isinstance(self.evidence, str):
            raise TypeError("evidence must be a string")
        if not isinstance(self.recommendation, str):
            raise TypeError("recommendation must be a string")

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible mapping with a deterministic key order."""

        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "status": self.status,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True, slots=True)
class Report:
    """A complete Template Doctor run without volatile timestamp fields."""

    root: str
    results: tuple[CheckResult, ...]
    summary: dict[str, int]
    status: str

    def __post_init__(self) -> None:
        if self.status not in REPORT_STATUSES:
            raise ValueError(
                f"unsupported report status {self.status!r}; "
                f"expected one of {sorted(REPORT_STATUSES)}"
            )

    @property
    def exit_code(self) -> int:
        """Map report state to the public CLI exit-code contract."""

        if self.status == "ready":
            return 0
        if self.status == "not_ready":
            return 1
        return 2

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible report representation."""

        return {
            "root": self.root,
            "status": self.status,
            "summary": dict(self.summary),
            "results": [result.to_dict() for result in self.results],
        }


class RuleCallable(Protocol):
    """A zero-argument rule bound to a target root by ``build_rules``."""

    def __call__(self) -> CheckResult:
        """Run the rule and return exactly one structured result."""
