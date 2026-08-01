"""Read-only, bounded preflight checks for concurrent AIWF work."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Callable

from .models import AuditReport, Finding, build_report


MAX_WORKERS = 4


def run_preflight(root: Path | str) -> AuditReport:
    project_root = Path(root).expanduser().resolve()
    if not project_root.is_dir():
        raise ValueError(f"root is not a directory: {root}")
    checks: tuple[tuple[str, Callable[[], Finding]], ...] = (
        ("capability.codegraph", lambda: _codegraph(project_root)),
        ("capability.git", lambda: _git(project_root)),
        ("capability.git_bash", _git_bash),
        ("capability.planning", lambda: _planning(project_root)),
        ("capability.powershell", _powershell),
        ("capability.python", _python),
        ("policy.host_limits", _host_policy),
    )
    with ThreadPoolExecutor(
        max_workers=min(MAX_WORKERS, len(checks)),
        thread_name_prefix="aiwf-preflight",
    ) as executor:
        findings = list(executor.map(lambda item: item[1](), checks))
    return build_report(
        "preflight",
        findings,
        {"root_name": project_root.name, "platform": os.name},
    )


def _python() -> Finding:
    return _finding(
        "capability.python",
        "pass",
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} is active.",
        "Use the active standard-library runtime for Run Guard.",
    )


def _powershell() -> Finding:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    return _finding(
        "capability.powershell",
        "pass" if executable else "skip",
        f"PowerShell executable is available as {Path(executable).name}." if executable else "PowerShell was not found on PATH.",
        "Use the module entry point directly when PowerShell is unavailable.",
    )


def _git(root: Path) -> Finding:
    executable = shutil.which("git")
    if not executable:
        return _finding(
            "capability.git",
            "skip",
            "Git is unavailable; diff-based scope evidence cannot run.",
            "Install Git or use explicit inventories without fabricating a diff.",
        )
    try:
        completed = subprocess.run(
            [executable, "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed and completed.returncode == 0:
        return _finding(
            "capability.git",
            "pass",
            f"Git baseline resolves to {completed.stdout.strip()[:12]}.",
            "Use status and diff as additional scope evidence.",
        )
    return _finding(
        "capability.git",
        "skip",
        "Git executable exists, but the project has no resolvable baseline.",
        "Use recorded artifacts and explicit inventories; do not fabricate diff evidence.",
    )


def _git_bash() -> Finding:
    candidates: list[Path] = []
    git = shutil.which("git")
    if git:
        root = Path(git).resolve().parent.parent
        candidates.extend((root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"))
    available = next((path for path in candidates if path.is_file()), None)
    return _finding(
        "capability.git_bash",
        "pass" if available else "skip",
        f"Git Bash is available as {available.name}." if available else "A Git-associated Bash executable was not found.",
        "Prefer native PowerShell commands when Git Bash is unavailable.",
    )


def _planning(root: Path) -> Finding:
    pointer = root / ".planning" / ".active_plan"
    try:
        plan_id = pointer.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        plan_id = ""
    valid_id = bool(
        plan_id
        and plan_id not in {".", ".."}
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", plan_id)
    )
    planning_root = (root / ".planning").resolve()
    plan = planning_root / plan_id / "task_plan.md" if valid_id else None
    contained = False
    if plan is not None:
        try:
            plan.resolve().relative_to(planning_root)
            contained = True
        except (OSError, ValueError):
            contained = False
    if plan and contained and plan.is_file():
        return _finding(
            "capability.planning",
            "pass",
            f"Active isolated plan {plan_id} resolves to task_plan.md.",
            "Keep the plan attested after approved edits.",
        )
    return _finding(
        "capability.planning",
        "skip",
        "No valid active isolated planning pointer was found.",
        "Initialize planning-with-files for long Standard or Full work.",
    )


def _codegraph(root: Path) -> Finding:
    directory = root / ".codegraph"
    databases = sorted(directory.glob("*.db")) if directory.is_dir() else []
    return _finding(
        "capability.codegraph",
        "pass" if databases else "skip",
        f"Project-local CodeGraph metadata contains {len(databases)} database file(s)." if databases else "No project-local CodeGraph index is present.",
        "Use source tools unless the project owner separately authorizes indexing.",
    )


def _host_policy() -> Finding:
    return _finding(
        "policy.host_limits",
        "skip",
        "Destructive-command and approval policy cannot be proven from repository files alone.",
        "Probe safely and prefer recoverable, project-scoped operations.",
    )


def _finding(finding_id: str, status: str, evidence: str, recommendation: str) -> Finding:
    return Finding(
        finding_id=finding_id,
        severity="info" if status in {"pass", "skip"} else "error",
        status=status,
        evidence=evidence,
        recommendation=recommendation,
    )
