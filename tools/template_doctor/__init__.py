"""Template initialization auditing with no third-party dependencies."""

from .engine import MAX_WORKERS, run_checks
from .models import CheckResult, Report, RuleCallable
from tools.project_version import PROJECT_VERSION

__all__ = [
    "CheckResult",
    "MAX_WORKERS",
    "Report",
    "RuleCallable",
    "run_checks",
]

__version__ = PROJECT_VERSION
