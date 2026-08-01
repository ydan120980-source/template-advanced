"""Read-only readiness rules for Template Doctor."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import subprocess
import tomllib
from typing import Callable

from .models import CheckResult, RuleCallable


PLACEHOLDER_PATTERNS = (
    re.compile(r"^\s*(?:[-*]\s*)?TODO(?::|\s*$)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:[-*]\s*)?<[^>\n]+>\s*$", re.MULTILINE),
    re.compile(
        r"^(?:Task ID|Last Updated|Repo|Current Phase|Current State|Current Axis|"
        r"Based On Commit|Current Git HEAD):\s*(?:YYYY-MM-DD[^ \n]*|<[^>\n]+>)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^##\s+Sprint\s+YYYY-MM-DD-[A-Z]\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^(?:Task Size|Workflow Mode):\s*(?:Small\s*/\s*Medium\s*/\s*Large|"
        r"Lite\s*/\s*Standard\s*/\s*Full)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
)
REQUIRED_NEXT_SECTIONS = {
    "Goal": ("Goal",),
    "Allowed Paths": ("Allowed Paths",),
    "Forbidden Paths": ("Forbidden Paths",),
    "Budget": ("Budget", "Budgets And Stop Conditions"),
    "Validation": ("Validation", "Validation Commands"),
    "Stop Conditions": ("Stop Conditions", "Budgets And Stop Conditions"),
    "Required Return Format": ("Required Return Format", "Required Return"),
}
VALIDATION_PATHS = (
    "scripts/lint.sh",
    "scripts/structural-check.sh",
    "scripts/test.sh",
    "scripts/verify.sh",
    "evals/run-evals.sh",
)
REPRESENTATIVE_IGNORED_PATHS = (
    "__pycache__/module.pyc",
    ".coverage",
    ".planning/run/progress.md",
    ".env",
    "node_modules/package/index.js",
    "dist/app.js",
)
REQUIRED_RELEASE_DOCS = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/ai-workflow/GITHUB_RELEASE_READINESS.md",
    ".gitattributes",
)
REPOSITORY_WALK_EXCLUDES = {
    ".git",
    ".codegraph",
    ".planning",
    "dist",
    "archive",
    "examples",
    "references",
}
SENSITIVE_FILENAMES = {
    ".env",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
SENSITIVE_SUFFIXES = (".key", ".p12", ".pem", ".pfx")
MAX_RELEASE_FILE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_id: str
    check: Callable[[], CheckResult]

    def __call__(self) -> CheckResult:
        return self.check()


def _result(
    rule_id: str,
    *,
    status: str,
    evidence: str,
    recommendation: str,
    severity: str | None = None,
) -> CheckResult:
    if severity is None:
        severity = "info" if status in {"pass", "skip"} else "error"
    return CheckResult(
        rule_id=rule_id,
        severity=severity,
        status=status,
        evidence=evidence,
        recommendation=recommendation,
    )


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError):
        return None
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _placeholder_labels(text: str) -> list[str]:
    labels: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            labels.append(pattern.pattern)
    return labels


def _section_present(text: str, section: str) -> bool:
    return bool(
        re.search(
            rf"(?im)^##?\s+(?:\d+[A-Z]?\.\s+)?{re.escape(section)}(?:\s|$)",
            text,
        )
    )


def _section_body(text: str, section: str) -> str | None:
    match = re.search(
        rf"(?im)^##\s+(?:\d+[A-Z]?\.\s+)?{re.escape(section)}[^\n]*\n",
        text,
    )
    if not match:
        return None
    end = re.search(r"(?m)^##\s+", text[match.end() :])
    body_end = match.end() + end.start() if end else len(text)
    return text[match.end() : body_end].strip()


def _control_placeholders(root: Path) -> CheckResult:
    rule_id = "control.placeholders"
    paths = (
        "docs/control/NEXT_CODEX_TASK.md",
        "docs/control/CURRENT_PROJECT_STATE.md",
        "docs/control/SPRINT_LEDGER.md",
        "docs/control/CHATGPT_HANDOFF.md",
    )
    missing_required: list[str] = []
    affected: list[str] = []
    for relative in paths:
        text = _read_text(root / relative)
        if text is None:
            if relative.endswith(("NEXT_CODEX_TASK.md", "CURRENT_PROJECT_STATE.md")):
                missing_required.append(relative)
            continue
        if _placeholder_labels(text):
            affected.append(relative)
    if missing_required or affected:
        evidence_parts = []
        if missing_required:
            evidence_parts.append("missing required: " + ", ".join(sorted(missing_required)))
        if affected:
            evidence_parts.append("placeholder markers: " + ", ".join(sorted(affected)))
        return _result(
            rule_id,
            status="fail",
            evidence="; ".join(evidence_parts),
            recommendation=(
                "Replace template markers with current project facts and create all "
                "required control files."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence="Required control files exist and scanned control files contain no template markers.",
        recommendation="Keep control files current as the project changes.",
    )


def _next_task_executable(root: Path) -> CheckResult:
    rule_id = "control.next_task_executable"
    relative = "docs/control/NEXT_CODEX_TASK.md"
    text = _read_text(root / relative)
    if text is None:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} is missing.",
            recommendation="Generate an executable Task Packet with aiwf-plan-sprint.",
        )
    missing: list[str] = []
    for section, aliases in REQUIRED_NEXT_SECTIONS.items():
        body = next(
            (candidate for alias in aliases if (candidate := _section_body(text, alias)) is not None),
            None,
        )
        if body is None:
            missing.append(section)
        elif not re.search(r"[A-Za-z0-9]", body) or _placeholder_labels(body):
            missing.append(f"non-empty {section}")
    task_id = re.search(r"(?im)^Task ID:\s*(\S.*?)\s*$", text)
    mode = re.search(r"(?im)^(?:Workflow Mode|Mode):\s*(Lite|Standard|Full)\s*$", text)
    if not task_id:
        missing.append("Task ID value")
    if not mode:
        missing.append("Workflow Mode value")
    if _placeholder_labels(text):
        missing.append("placeholder-free content")
    if missing:
        return _result(
            rule_id,
            status="fail",
            evidence="Task Packet is not executable; missing or invalid: " + ", ".join(sorted(set(missing))),
            recommendation=(
                "Regenerate NEXT_CODEX_TASK.md with a real Task ID, mode, scope, "
                "validation, stop conditions, and return format."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence=f"Executable Task Packet detected for {task_id.group(1).strip()}.",
        recommendation="Keep the Task Packet bounded and authoritative.",
    )


def _state_freshness(root: Path) -> CheckResult:
    rule_id = "control.current_state_freshness"
    relative = "docs/control/CURRENT_PROJECT_STATE.md"
    text = _read_text(root / relative)
    if text is None:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} is missing.",
            recommendation="Create current state with a real update date and explicit stale flag.",
        )
    match = re.search(r"(?im)^(?:[-*]\s*\*\*)?Last Updated(?:\*\*)?:\s*(\d{4}-\d{2}-\d{2})\s*$", text)
    stale = re.search(r"(?im)^(?:[-*]\s*\*\*)?Is state stale\?(?:\*\*)?:\s*(yes|no)\s*$", text)
    problems: list[str] = []
    if not match:
        problems.append("parseable Last Updated")
    else:
        try:
            from datetime import date

            date.fromisoformat(match.group(1))
        except ValueError:
            problems.append("valid Last Updated date")
    if not stale:
        problems.append("explicit Is state stale? flag")
    elif stale.group(1).lower() != "no":
        problems.append("Is state stale? must be no")
    if _placeholder_labels(text):
        problems.append("placeholder-free state")
    based_on = re.search(
        r"(?im)^(?:[-*]\s*\*\*)?Based On Commit(?:\*\*)?:\s*(\S.*?)\s*$",
        text,
    )
    recorded_head = re.search(
        r"(?im)^(?:[-*]\s*\*\*)?Current Git HEAD(?:\*\*)?:\s*(\S.*?)\s*$",
        text,
    )
    if not based_on or not recorded_head:
        problems.append("Based On Commit and Current Git HEAD fields")
    else:
        based_value = based_on.group(1).strip()
        head_value = recorded_head.group(1).strip()
        actual_head = _git_head_commit(root)
        if actual_head and (
            re.fullmatch(r"[0-9a-f]{40,64}", based_value)
            or re.fullmatch(r"[0-9a-f]{40,64}", head_value)
        ):
            # Machine-claimed commit identity must match the actual HEAD. A
            # committed file cannot self-reference the commit that contains
            # it, so maintainers may mark the fields as a manual record
            # instead of claiming a commit identity at all.
            if (
                based_value.lower() != actual_head
                or head_value.lower() != actual_head
            ):
                problems.append("state commit metadata matching current Git HEAD")
    if problems:
        return _result(
            rule_id,
            status="fail",
            evidence="State freshness is not established: " + ", ".join(problems) + ".",
            recommendation="Refresh CURRENT_PROJECT_STATE.md from current repository evidence.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence=(
            f"State date {match.group(1)} is valid, explicitly not stale"
            + (
                ", and matches current Git HEAD."
                if actual_head
                and re.fullmatch(r"[0-9a-f]{40,64}", based_value)
                and re.fullmatch(r"[0-9a-f]{40,64}", head_value)
                else "."
            )
        ),
        recommendation="Refresh state metadata after accepted Medium or Large work.",
    )


def _single_planning_authority(root: Path) -> CheckResult:
    rule_id = "planning.single_authority"
    texts: list[tuple[str, str]] = []
    for relative in ("AGENTS.md", "docs/control/CODEX_RUNTIME_PROFILE.md"):
        text = _read_text(root / relative)
        if text is not None:
            texts.append((relative, text))
    if not texts:
        return _result(
            rule_id,
            status="fail",
            evidence="AGENTS.md and CODEX_RUNTIME_PROFILE.md are both absent.",
            recommendation="Document NEXT_CODEX_TASK.md as the single sprint authority before declaring readiness.",
        )
    inconsistent: list[str] = []
    for relative, text in texts:
        mentions_task = "NEXT_CODEX_TASK.md" in text
        authority = bool(
            re.search(
                r"(?:single|sole|only)\s+(?:authoritative\s+)?(?:sprint\s+)?(?:plan|authority)",
                text,
                re.IGNORECASE,
            )
            or re.search(r"only authoritative sprint plan", text, re.IGNORECASE)
        )
        subordinate = "planning-with-files" not in text or bool(
            re.search(r"planning-with-files.{0,120}(?:subordinate|journal)", text, re.IGNORECASE | re.DOTALL)
        )
        if not (mentions_task and authority and subordinate):
            inconsistent.append(relative)
    if inconsistent:
        return _result(
            rule_id,
            status="fail",
            evidence="Single planning authority is not consistently stated in: " + ", ".join(sorted(inconsistent)),
            recommendation=(
                "Declare NEXT_CODEX_TASK.md as the sole sprint authority and planning-with-files "
                "as a subordinate execution journal."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence="Available governance files consistently identify NEXT_CODEX_TASK.md as planning authority.",
        recommendation="Preserve this authority boundary in future governance edits.",
    )


def _codex_config_safe_defaults(root: Path) -> CheckResult:
    """Fail when the project Codex configuration departs from safe defaults.

    The release-facing contract is: interactive approval is ``on-request``,
    sandbox mode is ``workspace-write``, network access is absent or ``false``,
    and no absolute path or credential appears in the file. Evidence uses only
    relative paths.
    """

    rule_id = "config.safe_defaults"
    relative = ".codex/config.toml"
    path = root / relative
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} is missing; the release contract requires a committed project configuration.",
            recommendation="Commit a project Codex configuration with approval_policy = \"on-request\".",
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} is not valid TOML ({type(exc).__name__}); parseable configuration is required.",
            recommendation="Repair the TOML and re-run the release validation.",
        )

    problems: list[str] = []
    if data.get("approval_policy") != "on-request":
        problems.append(
            f"approval_policy is {data.get('approval_policy', 'missing')!r}; expected \"on-request\""
        )
    if data.get("sandbox_mode") != "workspace-write":
        problems.append(
            f"sandbox_mode is {data.get('sandbox_mode', 'missing')!r}; expected \"workspace-write\""
        )
    workspace = data.get("sandbox_workspace_write")
    if isinstance(workspace, dict) and workspace.get("network_access") is True:
        problems.append("network_access is enabled; network must be off by default")

    raw = _read_text(path) or ""
    lines = raw.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if re.search(r"[A-Za-z]:[\\/]|/Users/|C:\\\\Users", line):
            problems.append(f"line {line_number} contains an absolute local path")
        if re.search(
            r"\bgithub_pat_[A-Za-z0-9_]{10,}|\bghp_[A-Za-z0-9]{20,}|"
            r"\bAKIA[A-Z0-9]{16}|BEGIN\s+PR[IV]ATE\s+K[EY]",
            line,
        ):
            problems.append(f"line {line_number} contains a credential pattern")
    if problems:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} departs from safe defaults: " + "; ".join(problems),
            recommendation=(
                "Restore approval_policy = \"on-request\", sandbox_mode = "
                "\"workspace-write\", and keep network access off by default."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence=(
            f"{relative} is parseable and keeps safe defaults: on-request "
            "approval, workspace-write sandbox, network access off."
        ),
        recommendation="Review configuration changes against the runtime profile before release.",
    )


def _codex_config_profiles(root: Path) -> CheckResult:
    rule_id = "config.unsupported_profiles"
    relative = ".codex/config.toml"
    path = root / relative
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} is missing.",
            recommendation="Create a supported project-local Codex configuration without profile tables.",
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} is not valid TOML ({type(exc).__name__}).",
            recommendation="Repair the TOML and validate it with codex --strict-config --version.",
        )
    profile_keys = sorted(key for key in data if key.lower() in {"profile", "profiles"})
    raw = _read_text(path) or ""
    table_match = re.search(r"(?im)^\s*\[\[?\s*profiles?(?:[.\]\s])", raw)
    if profile_keys or table_match:
        return _result(
            rule_id,
            status="fail",
            evidence="Unsupported project profile configuration detected.",
            recommendation=(
                "Remove [profile.*]/[profiles.*] tables; Lite, Standard, and Full are "
                "repository governance modes, not Codex CLI profiles."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence="Project Codex TOML parses and contains no unsupported profile tables.",
        recommendation="Re-run strict configuration validation after config changes.",
    )


def _validation_scripts(root: Path) -> CheckResult:
    rule_id = "validation.placeholder_scripts"
    missing: list[str] = []
    placeholders: list[str] = []
    for relative in VALIDATION_PATHS:
        text = _read_text(root / relative)
        if text is None:
            missing.append(relative)
        elif re.search(r"\b(?:TODO|placeholder)\b", text, re.IGNORECASE):
            placeholders.append(relative)
    if missing or placeholders:
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(sorted(missing)))
        if placeholders:
            parts.append("placeholder: " + ", ".join(sorted(placeholders)))
        return _result(
            rule_id,
            status="fail",
            evidence="; ".join(parts),
            recommendation="Replace placeholder validation/eval commands with project-specific checks.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence="Required validation and eval scripts exist without placeholder markers.",
        recommendation="Keep validation commands aligned with the project stack.",
    )


def _architecture_documented(root: Path) -> CheckResult:
    rule_id = "architecture.documented"
    relative = "docs/architecture/README.md"
    text = _read_text(root / relative)
    if text is None:
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} is missing.",
            recommendation="Document module boundaries, contracts, generated files, and migration rules.",
        )
    if re.search(r"\bTODO\b", text, re.IGNORECASE):
        return _result(
            rule_id,
            status="fail",
            evidence=f"{relative} still contains TODO architecture entries.",
            recommendation="Replace architecture TODOs with project-specific boundary decisions.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence="Architecture documentation contains no TODO markers.",
        recommendation="Update architecture notes when public boundaries change.",
    )


def _release_documents(root: Path) -> CheckResult:
    rule_id = "release.documents"
    missing: list[str] = []
    incomplete: list[str] = []
    for relative in REQUIRED_RELEASE_DOCS:
        text = _read_text(root / relative)
        if text is None:
            missing.append(relative)
            continue
        minimum_length = 10 if relative == ".gitattributes" else 40
        if len(text.strip()) < minimum_length:
            incomplete.append(relative)

    expectations = {
        "README.md": ("Template Doctor", "Run Guard"),
        "CONTRIBUTING.md": ("Contributing",),
        "SECURITY.md": ("Report",),
        "docs/ai-workflow/GITHUB_RELEASE_READINESS.md": ("Git", "License"),
        ".gitattributes": ("*.sh",),
    }
    for relative, markers in expectations.items():
        text = _read_text(root / relative)
        if text is not None and any(marker.lower() not in text.lower() for marker in markers):
            incomplete.append(relative)
    readme = _read_text(root / "README.md") or ""
    if not re.search(r"\bverification\b|verify\.sh", readme, re.IGNORECASE):
        incomplete.append("README.md")
    contributing = _read_text(root / "CONTRIBUTING.md") or ""
    if not re.search(r"validat(?:e|ion)", contributing, re.IGNORECASE):
        incomplete.append("CONTRIBUTING.md")

    if missing or incomplete:
        parts: list[str] = []
        if missing:
            parts.append("missing: " + ", ".join(sorted(missing)))
        if incomplete:
            parts.append("incomplete: " + ", ".join(sorted(set(incomplete))))
        return _result(
            rule_id,
            status="fail",
            evidence="; ".join(parts),
            recommendation=(
                "Provide actionable README, contribution, security, changelog, "
                "release-readiness, and line-ending documentation."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence=f"All {len(REQUIRED_RELEASE_DOCS)} release-documentation artifacts are present and substantive.",
        recommendation="Keep release documentation aligned with actual validation and publication boundaries.",
    )


def _walk_release_files(root: Path) -> Iterator[Path]:
    """Yield repository files without following local evidence or VCS metadata."""

    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories[:] = sorted(
            name for name in subdirectories if name not in REPOSITORY_WALK_EXCLUDES
        )
        base = Path(directory)
        for filename in sorted(filenames):
            yield base / filename


def _generated_artifacts(root: Path) -> CheckResult:
    rule_id = "repository.generated_artifacts"
    generated = sorted(
        path.relative_to(root).as_posix()
        for path in _walk_release_files(root)
        if path.suffix.lower() in {".pyc", ".pyo"} or "__pycache__" in path.parts
    )
    if generated:
        sample = ", ".join(generated[:10])
        suffix = f" (+{len(generated) - 10} more)" if len(generated) > 10 else ""
        return _result(
            rule_id,
            status="fail",
            evidence=f"Generated Python artifacts found: {sample}{suffix}",
            recommendation="Remove generated Python caches and keep them covered by the active .gitignore.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence="No Python bytecode or __pycache__ artifacts were found in release content.",
        recommendation="Run validation with PYTHONDONTWRITEBYTECODE=1 before packaging.",
    )


def _sensitive_filenames(root: Path) -> CheckResult:
    rule_id = "repository.sensitive_filenames"
    candidates: list[str] = []
    for path in _walk_release_files(root):
        name = path.name.lower()
        if name == ".env.example":
            continue
        if name in SENSITIVE_FILENAMES or name.endswith(SENSITIVE_SUFFIXES):
            candidates.append(path.relative_to(root).as_posix())
    if candidates:
        return _result(
            rule_id,
            status="fail",
            evidence="Sensitive filename candidates found (contents not read): " + ", ".join(sorted(candidates)),
            recommendation="Remove, redact, or explicitly review each named file before publication.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence="No common secret-bearing filenames were found; file contents were not opened by this rule.",
        recommendation="Also run an approved content-level secret scan before public release.",
    )


def _large_release_files(root: Path) -> CheckResult:
    rule_id = "repository.large_files"
    oversized: list[str] = []
    for path in _walk_release_files(root):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_RELEASE_FILE_BYTES:
            oversized.append(f"{path.relative_to(root).as_posix()} ({size} bytes)")
    if oversized:
        return _result(
            rule_id,
            status="fail",
            evidence="Files over 1 MiB require explicit release review: " + ", ".join(sorted(oversized)),
            recommendation="Remove generated payloads or document why each large source artifact belongs in the release.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence="No release-content file exceeds 1 MiB.",
        recommendation="Review large-file policy again before creating a Git baseline.",
    )


def _github_workflow_placeholders(root: Path) -> CheckResult:
    rule_id = "github.workflow_placeholders"
    workflow_root = root / ".github" / "workflows"
    workflows = (
        sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
        if workflow_root.is_dir()
        else []
    )
    affected: list[str] = []
    for workflow in workflows:
        text = _read_text(workflow) or ""
        if re.search(r"\b(?:TODO|placeholder)\b|intentionally non-operational", text, re.IGNORECASE):
            affected.append(workflow.relative_to(root).as_posix())
    if affected:
        return _result(
            rule_id,
            status="fail",
            evidence="Non-operational GitHub workflows found: " + ", ".join(affected),
            recommendation="Remove inert workflows or replace them only after triggers, permissions, and secrets are approved.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence=(
            f"Scanned {len(workflows)} GitHub workflow file(s); none contains placeholder execution."
        ),
        recommendation="Keep workflow permissions minimal and never imply unconfigured automation is active.",
    )


def _git_head_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip().lower()
    if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value):
        return value
    return None


def _no_local_state(root: Path) -> CheckResult:
    """Fail when release documentation embeds author-local paths or runtime state."""

    rule_id = "control.no_local_state"
    patterns = (
        re.compile(r"C:\\Users\\"),
        re.compile(r"/Users/"),
        re.compile(r"[A-Za-z]:\\"),
        re.compile(r"AppData"),
        re.compile(r"codex-template-advanced-(?:pyc|publication)-"),
        re.compile(r"\.planning/\.active_plan"),
        re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
    )
    scanned: list[str] = []
    for relative in sorted((root / "docs").rglob("*.md")):
        scanned.append(relative.relative_to(root).as_posix())
    for relative in (
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CHANGELOG.md",
    ):
        if (root / relative).is_file():
            scanned.append(relative)
    prompt_root = root / ".github" / "codex" / "prompts"
    if prompt_root.is_dir():
        scanned.extend(
            path.relative_to(root).as_posix() for path in sorted(prompt_root.glob("*.md"))
        )
    hits: list[str] = []
    for relative in sorted(set(scanned)):
        text = _read_text(root / relative)
        if text is None:
            continue
        for pattern in patterns:
            if pattern.search(text):
                hits.append(f"{relative} ({pattern.pattern})")
    if hits:
        return _result(
            rule_id,
            status="fail",
            evidence="Author-local path or runtime-state reference in release docs: "
            + "; ".join(sorted(hits)[:10]),
            recommendation=(
                "Remove machine-specific absolute paths, active-plan pointers, "
                "and historical scan/run identifiers from user-facing documentation."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence=f"Scanned {len(scanned)} release documentation files; none contains author-local paths or runtime state.",
        recommendation="Keep release documentation portable and machine-agnostic.",
    )


def _sprint_consistency(root: Path) -> CheckResult:
    """Fail when the Task Packet, current state, and active-plan pointer disagree."""

    rule_id = "control.sprint_consistency"
    packet = _read_text(root / "docs" / "control" / "NEXT_CODEX_TASK.md")
    state = _read_text(root / "docs" / "control" / "CURRENT_PROJECT_STATE.md")
    task_id: str | None = None
    if packet is not None:
        match = re.search(r"(?im)^Task ID:\s*(\S.*?)\s*$", packet)
        if match:
            task_id = match.group(1).strip()
    state_sprint: str | None = None
    if state is not None:
        match = re.search(
            r"(?im)^(?:[-*]\s*\*\*)?(?:Current Sprint|Current Task ID)(?:\*\*)?:\s*(\S.*?)\s*$",
            state,
        )
        if match:
            state_sprint = match.group(1).strip()
    none_words = {"-", "none", "none declared", "no active sprint", "no current sprint"}
    pointer: str | None = None
    active_plan = root / ".planning" / ".active_plan"
    if active_plan.is_file():
        pointer = (active_plan.read_text(encoding="utf-8") or "").strip()
    problems: list[str] = []
    if pointer:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}", pointer):
            problems.append("active-plan pointer is not a portable plan identifier")
        elif task_id and pointer != task_id:
            problems.append(
                f"active-plan pointer {pointer} differs from Task Packet {task_id}"
            )
        if state_sprint and state_sprint not in none_words and task_id and state_sprint != task_id:
            problems.append("state current sprint differs from the active-plan pointer")
    elif state_sprint and state_sprint not in none_words:
        if task_id and state_sprint != task_id:
            problems.append(
                f"state declares {state_sprint} but the Task Packet declares {task_id}"
            )
    if problems:
        return _result(
            rule_id,
            status="fail",
            evidence="Sprint evidence is inconsistent: " + "; ".join(problems) + ".",
            recommendation=(
                "Keep the Task Packet, CURRENT_PROJECT_STATE.md, and the active "
                "planning pointer on the same task, or remove stale pointers."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence=(
            f"Task Packet {task_id or '<none>'} is consistent with declared state "
            f"and the active-plan pointer."
        ),
        recommendation="Update all three control surfaces together when a sprint changes.",
    )


def _numeric_status_claims(root: Path) -> CheckResult:
    """Fail when docs assert numeric test/rule counts or pass claims that drift."""

    rule_id = "control.numeric_status_claims"
    patterns = (
        re.compile(r"\b\d+\s+(?:test|tests)\b", re.IGNORECASE),
        re.compile(r"\b\d+\s+(?:rule|rules)\b", re.IGNORECASE),
        re.compile(r"\b\d+\s+(?:finding|findings)\b", re.IGNORECASE),
        re.compile(r"\bverify\s+(?:all\s+)?tests?\s+passed?\b", re.IGNORECASE),
        re.compile(r"\ball\s+tests?\s+passed?\b", re.IGNORECASE),
        re.compile(r"\b(?:total|count)\s+of\s+\d+\s+tests?\b", re.IGNORECASE),
    )
    scanned: list[str] = []
    for relative in sorted((root / "docs").rglob("*.md")):
        scanned.append(relative.relative_to(root).as_posix())
    for relative in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md"):
        if (root / relative).is_file():
            scanned.append(relative)
    hits: list[str] = []
    for relative in sorted(set(scanned)):
        text = _read_text(root / relative)
        if text is None:
            continue
        for pattern in patterns:
            if pattern.search(text):
                hits.append(f"{relative} ({pattern.pattern})")
    if hits:
        return _result(
            rule_id,
            status="fail",
            evidence="Drift-prone numeric status claim in docs: "
            + "; ".join(sorted(hits)[:10]),
            recommendation=(
                "Remove hard-coded test/rule counts and pass claims from prose; "
                "read the current values from the validation scripts instead."
            ),
        )
    return _result(
        rule_id,
        status="pass",
        evidence=f"Scanned {len(scanned)} documentation files; none asserts a drift-prone numeric status.",
        recommendation="Keep counts machine-generated or absent from user documentation.",
    )


def _release_manifest_consistency(root: Path) -> CheckResult:
    """Fail when a published manifest no longer matches the current release tree."""

    rule_id = "release.manifest_consistency"
    dist = root / "dist"
    manifests = sorted(dist.glob("*.manifest.json")) if dist.is_dir() else []
    if not manifests:
        return _result(
            rule_id,
            status="skip",
            evidence="No release manifest exists under dist/; nothing to compare.",
            recommendation="Run scripts/build-release.py to publish a manifest and archive.",
        )
    manifest_path = manifests[0]
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _result(
            rule_id,
            status="fail",
            evidence=f"Release manifest is unreadable: {type(exc).__name__}: {exc}.",
            recommendation="Rebuild the release with scripts/build-release.py.",
        )
    try:
        from .release_inventory import ReleaseEntry, iter_release_entries, publication_digest

        current = iter_release_entries(root)
        manifest_entries = [
            ReleaseEntry.from_dict(item) for item in raw.get("files", [])
        ]
    except (TypeError, ValueError, KeyError) as exc:
        return _result(
            rule_id,
            status="fail",
            evidence=f"Release manifest entries are invalid: {exc}.",
            recommendation="Rebuild the release with scripts/build-release.py.",
        )
    current_paths = [entry.path for entry in current]
    manifest_paths = [entry.path for entry in manifest_entries]
    problems: list[str] = []
    if current_paths != manifest_paths:
        problems.append("file set differs from the current release tree")
    if raw.get("publication_digest") != publication_digest(manifest_entries):
        problems.append("publication digest does not match the manifest entries")
    if problems:
        return _result(
            rule_id,
            status="fail",
            evidence=(
                f"{manifest_path.name} is stale: " + "; ".join(problems) + " "
                f"(current {len(current_paths)} files vs manifest {len(manifest_paths)})."
            ),
            recommendation="Rebuild the release and re-verify it before publishing.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence=(
            f"{manifest_path.name} matches the current tree "
            f"({len(manifest_paths)} files; digest verified)."
        ),
        recommendation="Rebuild the manifest after any release-content change.",
    )


def _git_baseline(root: Path) -> CheckResult:
    rule_id = "git.baseline"
    commit = _git_head_commit(root)
    if commit is None:
        return _result(
            rule_id,
            status="fail",
            evidence="Git could not resolve HEAD to a commit object.",
            recommendation="Initialize or copy the project into an approved Git repository and create a baseline commit.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence=f"Git resolves HEAD to commit {commit[:12]}.",
        recommendation="Use Git status and diff as acceptance evidence for future sprints.",
    )


def _matches_ignore_pattern(path: str, pattern: str) -> bool:
    normalized = path.strip("/")
    pattern = pattern.strip().replace("\\", "/")
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")
    if not pattern:
        return False
    if pattern.endswith("/"):
        directory = pattern.rstrip("/")
        return normalized == directory or normalized.startswith(directory + "/") or (
            not anchored and f"/{directory}/" in f"/{normalized}/"
        )
    pure = PurePosixPath(normalized)
    return pure.match(pattern) or (
        "/" not in pattern and any(fnmatch.fnmatch(part, pattern) for part in pure.parts)
    )


def _is_ignored(path: str, patterns: list[str]) -> bool:
    ignored = False
    for raw in patterns:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        if _matches_ignore_pattern(path, line):
            ignored = not negated
    return ignored


def _gitignore_effective(root: Path) -> CheckResult:
    rule_id = "gitignore.effective"
    relative = ".gitignore"
    text = _read_text(root / relative)
    if text is None:
        return _result(
            rule_id,
            status="fail",
            evidence="No active .gitignore exists; a .gitignore.template is not active.",
            recommendation="Merge the approved ignore rules into a real project .gitignore.",
        )
    patterns = text.splitlines()
    uncovered = sorted(
        sample
        for sample in REPRESENTATIVE_IGNORED_PATHS
        if not _is_ignored(sample, patterns)
    )
    if uncovered:
        return _result(
            rule_id,
            status="fail",
            evidence="Representative generated paths not ignored: " + ", ".join(uncovered),
            recommendation="Add project-appropriate ignore patterns and verify representative generated paths.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence=f"Active .gitignore covers {len(REPRESENTATIVE_IGNORED_PATHS)} representative generated paths.",
        recommendation="Extend ignore rules when new generated outputs are introduced.",
    )


def _codegraph_initialized(root: Path, *, strict: bool = False) -> CheckResult:
    rule_id = "codegraph.initialized"
    directory = root / ".codegraph"
    databases = sorted(directory.glob("*.db")) if directory.is_dir() else []
    # Heuristic candidate detection: there is no authoritative schema contract
    # for CodeGraph databases, so any readable SQLite database passing
    # quick_check with at least one currently recognized candidate table is
    # accepted. This is a health check, not full schema validation.
    recognized_candidate_tables = frozenset({"nodes", "edges"})
    verified_databases: list[str] = []
    invalid_databases: list[str] = []
    for database in databases:
        relative_name = database.relative_to(root).as_posix()
        if not database.is_file():
            invalid_databases.append(f"{relative_name}: not a regular file")
            continue
        try:
            uri = f"{database.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=1) as connection:
                quick_check = connection.execute("PRAGMA quick_check").fetchone()
                table_rows = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            invalid_databases.append(f"{relative_name}: {type(exc).__name__}")
            continue
        table_names = {row[0] for row in table_rows if isinstance(row, tuple)}
        recognized_tables_present = table_names & recognized_candidate_tables
        database_is_healthy_candidate = (
            quick_check == ("ok",) and bool(recognized_tables_present)
        )
        if database_is_healthy_candidate:
            recognized = sorted(recognized_tables_present)
            verified_databases.append(
                f"{relative_name} contains recognized candidate table(s): "
                + ", ".join(recognized)
            )
        elif quick_check == ("ok",):
            invalid_databases.append(
                f"{relative_name}: no recognized CodeGraph candidate tables"
            )
        else:
            invalid_databases.append(f"{relative_name}: failed SQLite quick_check")
    if invalid_databases:
        return _result(
            rule_id,
            status="fail",
            evidence="Invalid project-local CodeGraph database(s): " + ", ".join(invalid_databases),
            recommendation="Repair or remove the invalid CodeGraph database, then reinitialize it with a working tool.",
        )
    if verified_databases:
        return _result(
            rule_id,
            status="pass",
            evidence="Project-local CodeGraph candidate database(s) passed SQLite quick_check: " + "; ".join(verified_databases),
            recommendation="Check CodeGraph pending changes before relying on indexed results.",
        )
    if strict:
        return _result(
            rule_id,
            status="fail",
            evidence="No project-local .codegraph candidate SQLite database was found (strict mode).",
            recommendation="Run codegraph init at the real project root, or drop --strict if the index is not required.",
        )
    return _result(
        rule_id,
        status="skip",
        evidence="No project-local .codegraph candidate SQLite database was found; CodeGraph is an optional capability.",
        recommendation="When approved, run codegraph init at the real project root; do not initialize it implicitly.",
    )


def _hooks_capability(_: Path) -> CheckResult:
    rule_id = "capability.hooks"
    path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "hooks.json"
    if not path.is_file():
        return _result(
            rule_id,
            status="skip",
            evidence="Global Hook registration metadata is unavailable.",
            recommendation="Validate Hooks with the supported host diagnostics if the project depends on them.",
        )
    try:
        size = path.stat().st_size
    except OSError:
        return _result(
            rule_id,
            status="skip",
            evidence="Global Hook registration exists but its filesystem metadata is unavailable.",
            recommendation="Use host Hook diagnostics; do not expose registration contents.",
        )
    return _result(
        rule_id,
        status="pass",
        evidence=f"Global Hook metadata exists ({size} bytes); the file was not opened.",
        recommendation="Use plan-doctor or host diagnostics to verify live Hook execution.",
    )


def _mcp_capability(root: Path) -> CheckResult:
    rule_id = "capability.mcp"
    project_markers = (
        root / ".codex" / "mcp.toml",
        root / ".codex" / "mcp.example.toml",
    )
    live = project_markers[0]
    example = project_markers[1]
    if live.is_file():
        return _result(
            rule_id,
            status="pass",
            evidence="Project contains live MCP configuration metadata; values were not read.",
            recommendation="Confirm live server health with redacted Codex diagnostics before depending on MCP.",
        )
    if example.is_file():
        return _result(
            rule_id,
            status="skip",
            evidence="Only mcp.example.toml is present; an example is not a configured capability.",
            recommendation="Keep MCP optional unless the project owner explicitly configures and authorizes it.",
        )
    return _result(
        rule_id,
        status="skip",
        evidence="No project-local MCP metadata is present; live host configuration was intentionally not parsed.",
        recommendation="Keep MCP optional unless the project owner explicitly configures and authorizes it.",
    )


def _memory_capability(_: Path) -> CheckResult:
    rule_id = "capability.global_memory"
    memory_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "memories"
    registry = memory_root / "MEMORY.md"
    summary = memory_root / "memory_summary.md"
    if not memory_root.is_dir():
        return _result(
            rule_id,
            status="skip",
            evidence="Global memory directory metadata is unavailable.",
            recommendation="Treat project files as authoritative even when global memory is unavailable.",
        )
    flags = f"registry={registry.is_file()}, summary={summary.is_file()}"
    return _result(
        rule_id,
        status="pass",
        evidence=f"Global memory metadata exists ({flags}); memory contents were not read.",
        recommendation="Verify drift-prone facts against current source, configuration, and tests.",
    )


def build_rules(root: Path | str, *, strict: bool = False) -> list[RuleCallable]:
    """Bind all independent, read-only rules to ``root`` in stable order.

    ``strict`` promotes optional-capability findings (such as a missing
    CodeGraph index) to blocking failures.
    """

    target = Path(root).resolve()
    definitions: tuple[tuple[str, Callable[[Path], CheckResult]], ...] = (
        ("architecture.documented", _architecture_documented),
        ("capability.global_memory", _memory_capability),
        ("capability.hooks", _hooks_capability),
        ("capability.mcp", _mcp_capability),
        ("codegraph.initialized", lambda path: _codegraph_initialized(path, strict=strict)),
        ("config.safe_defaults", _codex_config_safe_defaults),
        ("config.unsupported_profiles", _codex_config_profiles),
        ("control.current_state_freshness", _state_freshness),
        ("control.next_task_executable", _next_task_executable),
        ("control.no_local_state", _no_local_state),
        ("control.numeric_status_claims", _numeric_status_claims),
        ("control.placeholders", _control_placeholders),
        ("control.sprint_consistency", _sprint_consistency),
        ("git.baseline", _git_baseline),
        ("gitignore.effective", _gitignore_effective),
        ("github.workflow_placeholders", _github_workflow_placeholders),
        ("planning.single_authority", _single_planning_authority),
        ("release.documents", _release_documents),
        ("release.manifest_consistency", _release_manifest_consistency),
        ("repository.generated_artifacts", _generated_artifacts),
        ("repository.large_files", _large_release_files),
        ("repository.sensitive_filenames", _sensitive_filenames),
        ("validation.placeholder_scripts", _validation_scripts),
    )
    return [
        _Rule(rule_id, lambda check=check: check(target))
        for rule_id, check in definitions
    ]
