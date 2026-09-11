"""Audit trial sub-agent sessions on every tool channel.

The coordinator records budget and independence evidence from the session
JSONL the host writes for each trial sub-agent. Counting only shell calls is
not enough: a trial can read the source repository, an acceptor, or the fixed
upstream file through non-shell tools (``Read``, ``Grep``, ``Glob``) without
issuing a single shell command. An audit that only looks at ``Bash`` therefore
cannot establish independence, and its "clean" result is not evidence.

This module reports facts:

- every tool call in a session record, whatever the tool;
- the shell-bearing request count under the same conservative rules as the
  frozen Run Guard parser, so the two independent implementations can be
  cross-checked by test;
- each call's absolute path arguments classified as inside the trial
  directory, inside the source repository, inside a declared neutral
  scratch root, or elsewhere;
- read/search calls that name no explicit path, which therefore run against
  the host's default working directory rather than the trial directory;
- shell commands that mention ``git`` without anchoring themselves inside the
  trial directory, for the same reason.

It deliberately does **not** decide VALID / INVALID / UNVERIFIED. That
classification is the coordinator's, recorded per run in the graded record's
``trial_validity`` field, and it must cite this audit's output as its basis.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

# Same allowlist the frozen Run Guard parser uses for named shell functions.
SHELL_FUNCTION_NAMES = frozenset(
    {"exec", "shell", "shell_command", "exec_command", "bash"}
)

_SHELL_CALL_PATTERN = re.compile(
    r"\btools\s*\.\s*(?:shell_command|exec_command)\s*\("
)

_READ_TOOLS = frozenset({"read", "notebookread"})
_WRITE_TOOLS = frozenset({"write", "edit", "multiedit", "notebookedit", "applypatch"})
_SEARCH_TOOLS = frozenset({"grep", "glob", "search", "list"})
_EXECUTE_TOOLS = SHELL_FUNCTION_NAMES

# Host tools that execute commands but are not in the frozen Run Guard shell
# allowlist, so their requests are *not* counted by the frozen budget metric.
# They are still execution channels and must appear in the audit, otherwise a
# trial could run commands that never show up in its reported budget.
_EXTRA_EXECUTION_TOOLS = frozenset({"powershell"})

# Tools that can retrieve content from outside the machine. The call itself is
# auditable, so a trial that reached a code host is detectable after the fact.
_NETWORK_TOOLS = frozenset({"webfetch", "websearch", "fetch"})

_URL_PATTERN = re.compile(r"https?://[^\s\"'`<>\\]+")

# Argument keys that carry a path. Relative values are deliberately ignored:
# a relative path is resolved against the host's default working directory,
# which is exactly the ambiguity this audit exists to expose, so it is
# reported through the "no explicit path" finding instead of being guessed at.
_PATH_ARGUMENT_KEYS = (
    "file_path",
    "path",
    "filepath",
    "notebook_path",
    "directory",
    "target_file",
)

# Tokens that look like absolute paths but never denote task content.
_PATH_NOISE = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/zero"})

# Parentheses are allowed inside the class because this repository's own
# workspace path contains them ("Agentic_Engineering(codex)"); excluding them
# would truncate every path in the record and manufacture false violations.
# Both patterns require real path characters after the root so JSON escape
# artefacts such as ``y:\n`` or a bare ``/`` are not mistaken for paths.
_WINDOWS_ABSOLUTE = re.compile(
    r"[A-Za-z]:[\\/][A-Za-z0-9_.\-][^\s\"'`|&;<>,\[\]]*"
)
# An optional single-letter first segment keeps MSYS-style ``/e/project``
# paths visible while a minimum two-character segment rejects ``/5``.
_POSIX_ABSOLUTE = re.compile(
    r"(?<![\w.:)\]])/(?:[A-Za-z]/)?[A-Za-z0-9_.\-]{2,}(?:/[^\s\"'`|&;<>\\\[\]]*)?"
)
_MSYS_DRIVE = re.compile(r"^/([A-Za-z])/(.*)$")

# Temp scratch is neutral: it cannot carry repository answers, so a trial that
# writes a throwaway script there has deviated from "work only inside this
# directory" without gaining access to the solution. Still reported.
# These roots are a heuristic fallback, not an override: the explicitly
# declared source repository is checked *before* them (see ``_scope_of``),
# because a source repository that happens to live under a default scratch
# root -- Linux CI's ``/tmp`` -- is still the source repository.
_DEFAULT_SCRATCH = (
    "c:/windows/temp",
    "/tmp",
    "/var/tmp",
    "/private/tmp",
)


class SessionAuditError(RuntimeError):
    """The session record could not be audited at all."""


def _normalise(value: str) -> str:
    value = value.replace("\\", "/").rstrip("/")
    # Git Bash reports the same Windows path as ``/e/project/...``; fold it
    # onto the drive-letter form so both spellings compare equal.
    match = _MSYS_DRIVE.match(value)
    if match:
        value = f"{match.group(1)}:/{match.group(2)}"
    return value.lower()


def _is_within(candidate: str, root: str) -> bool:
    candidate = _normalise(candidate)
    root = _normalise(root)
    if not root:
        return False
    return candidate == root or candidate.startswith(root + "/")


def _is_absolute(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("/"))


def _scope_of(target: str, *, trial_dir: str, source_repo: str, scratch) -> str:
    if _is_within(target, trial_dir):
        return "trial"
    # The source repository outranks scratch roots. ``source_repo`` is an
    # explicit, caller-declared location that holds the fixed answer, while
    # the scratch roots are generic heuristics: on Linux CI the synthesised
    # source repository itself sits under ``/tmp``, and classifying it as
    # neutral scratch would hide exactly the violation the audit exists to
    # report. Caller-declared scratch roots lose to the source repository for
    # the same reason -- a scratch root that encloses the answer repository
    # is a misconfiguration, and the conservative reading reports the leak.
    if source_repo and _is_within(target, source_repo):
        return "source_repo"
    for root in scratch:
        if _is_within(target, root):
            return "scratch"
    return "other"


def _iter_strings(value: object):
    """Yield every decoded string inside a tool-call argument structure.

    Extraction runs on decoded values, never on re-serialised JSON: a
    re-serialised blob re-escapes newlines as the two characters ``\n``, so a
    line like ``print("y:\\n")`` would yield the bogus target ``y:\n``.
    """

    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _extract_targets(arguments: object) -> list[str]:
    """Return the absolute path-like targets one tool call names.

    Extraction is deliberately literal. A heuristic that also guessed at
    relative paths would report confident nonsense, so relative values are
    left to the "no explicit path" finding.
    """

    candidates: list[str] = []
    if isinstance(arguments, dict):
        for key in _PATH_ARGUMENT_KEYS:
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
    for text in _iter_strings(arguments):
        # URLs are not filesystem paths, and the path patterns below would
        # otherwise read ``https://host/path`` as a target ``/host/path``.
        text = _URL_PATTERN.sub(" ", text)
        candidates.extend(match.group(0) for match in _WINDOWS_ABSOLUTE.finditer(text))
        candidates.extend(match.group(0) for match in _POSIX_ABSOLUTE.finditer(text))

    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item in _PATH_NOISE or not _is_absolute(item):
            continue
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _has_explicit_path_argument(arguments: object) -> bool:
    if not isinstance(arguments, dict):
        return False
    for key in _PATH_ARGUMENT_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip() and _is_absolute(value.strip()):
            return True
    return False


def _tool_kind(tool: str) -> str:
    lowered = tool.strip().lower()
    if lowered in _EXECUTE_TOOLS or lowered in _EXTRA_EXECUTION_TOOLS:
        return "execute"
    if lowered in _NETWORK_TOOLS:
        return "network"
    if lowered in _READ_TOOLS:
        return "read"
    if lowered in _WRITE_TOOLS:
        return "write"
    if lowered in _SEARCH_TOOLS:
        return "search"
    return "other"


def _urls_in(arguments: object) -> list[str]:
    urls: list[str] = []
    for text in _iter_strings(arguments):
        urls.extend(match.group(0) for match in _URL_PATTERN.finditer(text))
    seen: set[str] = set()
    return [item for item in urls if not (item in seen or seen.add(item))]


def _iter_records(session_path: Path) -> tuple[list[dict], list[str]]:
    """Return (events, integrity_problems).

    Corruption is reported, never swallowed: a record that cannot be parsed
    cannot support a validity claim, and the caller must treat it as
    UNVERIFIED rather than as a clean zero.
    """

    try:
        text = session_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SessionAuditError(
            f"cannot read session record {session_path}: {type(exc).__name__}"
        ) from exc
    problems: list[str] = []
    events: list[dict] = []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for number, line in enumerate(lines, 1):
        line = line.rstrip("\r")
        if not line.strip():
            problems.append(f"blank session line at {number}")
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"invalid JSON at line {number}: {exc.msg}")
            continue
        if not isinstance(value, dict):
            problems.append(f"non-object session line at {number}")
            continue
        events.append(value)
    return events, problems


def _call_of(event: dict) -> dict | None:
    """Return the tool-call payload of a wrapped or unwrapped event."""

    if event.get("type") == "function_call":
        return event
    if event.get("type") == "response_item":
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("type") in {
            "function_call",
            "custom_tool_call",
        }:
            return payload
    return None


def _call_identity(call: dict) -> object:
    for key in ("call_id", "callId", "id"):
        if key in call:
            return call[key]
    return None


def _is_shell_request(call: dict) -> bool:
    """Classify one tool call as shell-bearing under the frozen rules.

    Mirrors ``tools.aiwf_run_guard.budget``: a ``custom_tool_call`` whose
    string input invokes ``tools.shell_command(...)`` / ``tools.exec_command``
    (historical and current host forms), or a named function call whose tool
    name is in the conservative shell allowlist. ``tools.workflow_eval`` stays
    standard-library-only, so this is a second implementation rather than an
    import; a test pins the two against the same fixture.
    """

    payload_type = call.get("type")
    if payload_type == "custom_tool_call":
        raw_input = call.get("input")
        if not isinstance(raw_input, str):
            raise SessionAuditError("custom_tool_call input is not a plain string")
        return bool(_SHELL_CALL_PATTERN.search(raw_input))
    if payload_type == "function_call":
        name = call.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SessionAuditError("function_call lacks a tool name")
        return name.strip().lower() in SHELL_FUNCTION_NAMES
    return False


def _argument_mapping(call: dict) -> object:
    raw_arguments = call.get("arguments")
    if isinstance(raw_arguments, str):
        try:
            return json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {"_raw": raw_arguments}
    if raw_arguments is None:
        return {"input": call.get("input")}
    return raw_arguments


def audit_session(
    session_path: Path | str,
    *,
    trial_dir: Path | str,
    source_repo: Path | str | None = None,
    scratch_roots: tuple[str, ...] = (),
) -> dict[str, object]:
    """Audit one trial sub-agent session record.

    Returns facts only. ``outside_accesses`` lists every observed tool call
    that named an absolute target outside the trial directory;
    ``source_repo_accesses`` is the subset that reached into the source
    repository, which is where the fixed upstream answer lives.
    """

    session_path = Path(session_path)
    trial_text = str(trial_dir)
    source_text = str(source_repo) if source_repo else ""
    scratch = tuple(scratch_roots) + _DEFAULT_SCRATCH

    events, integrity_problems = _iter_records(session_path)
    accesses: list[dict[str, object]] = []
    tool_counts: dict[str, int] = {}
    shell_ids: list[str] = []
    call_total = 0
    observed_cwds: dict[str, int] = {}
    unanchored_git: list[dict[str, object]] = []
    unanchored_reads: list[dict[str, object]] = []
    network_calls: list[dict[str, object]] = []
    execution_not_counted: list[dict[str, object]] = []

    for number, event in enumerate(events, 1):
        call = _call_of(event)
        if call is None:
            continue
        call_total += 1
        tool = str(call.get("name") or call.get("type") or "unknown")
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
        arguments = _argument_mapping(call)

        cwd = call.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            observed_cwds[cwd] = observed_cwds.get(cwd, 0) + 1

        if _is_shell_request(call):
            identity = _call_identity(call)
            shell_ids.append(str(identity) if identity is not None else f"line-{number}")
        elif tool.strip().lower() in _EXTRA_EXECUTION_TOOLS:
            # An execution channel the frozen shell metric does not count.
            execution_not_counted.append(
                {
                    "line": number,
                    "tool": tool,
                    "reason": (
                        "executes commands but is not in the frozen Run Guard shell "
                        "allowlist, so it is outside the recorded shell-request budget"
                    ),
                }
            )

        if tool.strip().lower() in _NETWORK_TOOLS:
            network_calls.append(
                {"line": number, "tool": tool, "urls": _urls_in(arguments)}
            )

        kind = _tool_kind(tool)
        targets = _extract_targets(arguments)
        for target in targets:
            scope = _scope_of(
                target, trial_dir=trial_text, source_repo=source_text, scratch=scratch
            )
            if scope == "trial":
                continue
            accesses.append(
                {
                    "line": number,
                    "tool": tool,
                    "kind": kind,
                    "target": target,
                    "scope": scope,
                }
            )

        # A call with no absolute path runs wherever the host puts it: the
        # default working directory, which is the source repository. That is a
        # real access even though no path was written.
        unanchored = False
        command = ""
        if isinstance(arguments, dict):
            command = str(arguments.get("command") or arguments.get("_raw") or "")
        if kind == "execute":
            # Only git commands matter here: `ls`, `python -V` and the like do
            # not read repository content by themselves. A git command is
            # anchored when it explicitly `cd`s into (or names) the trial
            # directory, which the extracted absolute targets show.
            if re.search(r"\bgit\b", command) and not any(
                _scope_of(
                    target,
                    trial_dir=trial_text,
                    source_repo=source_text,
                    scratch=scratch,
                )
                == "trial"
                for target in targets
            ):
                unanchored = True
        elif kind in {"read", "search"} and not _has_explicit_path_argument(
            arguments
        ):
            unanchored = True
        if unanchored:
            entry = {
                "line": number,
                "tool": tool,
                "kind": kind,
                "cwd": cwd,
                "reason": (
                    "the call names no absolute path inside the trial directory, so "
                    "it resolved against the host's default working directory instead"
                ),
            }
            if command:
                entry["command"] = command
            unanchored_reads.append(entry)
            if kind == "execute":
                unanchored_git.append(entry)

    source_accesses = [item for item in accesses if item["scope"] == "source_repo"]
    return {
        "record_type": "trial_session_audit",
        "session_path": str(session_path),
        "trial_dir": trial_text,
        "source_repo": source_text or None,
        "scratch_roots": list(scratch_roots) + list(_DEFAULT_SCRATCH),
        "call_total": call_total,
        "tool_call_counts": {key: tool_counts[key] for key in sorted(tool_counts)},
        "audited_channels": sorted(tool_counts),
        "shell_requests": len(shell_ids),
        "shell_call_ids": sorted(shell_ids),
        "execution_channels_not_in_shell_metric": execution_not_counted,
        "network_tool_calls": network_calls,
        "network_channel_present": bool(network_calls),
        "outside_accesses": accesses,
        "source_repo_accesses": source_accesses,
        "calls_without_explicit_path": unanchored_reads,
        "git_commands_without_trial_anchor": unanchored_git,
        "observed_cwds": {key: observed_cwds[key] for key in sorted(observed_cwds)},
        "integrity_problems": integrity_problems,
        "auditable": not integrity_problems and call_total > 0,
    }


def observed_working_directory(audit: dict[str, object]) -> str | None:
    """Return the host's default working directory, when exactly one was seen."""

    cwds = audit.get("observed_cwds")
    if isinstance(cwds, dict) and len(cwds) == 1:
        return next(iter(cwds))
    return None


def first_user_prompt(session_path: Path | str) -> str:
    """Return the first user message text, used to show the sub-agent's context.

    A fresh sub-agent's record opens with exactly the coordinator's prompt. If
    the record opened with parent conversation content, the trial context was
    inherited rather than fresh, so this is part of the independence evidence.
    """

    events, _ = _iter_records(Path(session_path))
    for event in events:
        if event.get("type") == "message" and event.get("role") == "user":
            content = event.get("content")
            if isinstance(content, list):
                return "".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict)
                )
            if isinstance(content, str):
                return content
    return ""
