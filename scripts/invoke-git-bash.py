#!/usr/bin/env python3
"""Invoke a repository Bash script with Git for Windows Bash without PowerShell."""
from __future__ import annotations
import argparse, os, shutil, subprocess, sys
from pathlib import Path

class LauncherError(RuntimeError): pass

def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))

def _blocked(path: Path, env: dict[str,str]) -> bool:
    blocked=[]
    windows=env.get("WINDIR") or env.get("SystemRoot")
    local=env.get("LOCALAPPDATA")
    if windows: blocked.append(Path(windows)/"System32"/"bash.exe")
    if local: blocked.append(Path(local)/"Microsoft"/"WindowsApps"/"bash.exe")
    return any(_norm(path)==_norm(item) for item in blocked)

def resolve_git_bash(*, env: dict[str,str] | None=None) -> Path:
    env=dict(os.environ if env is None else env); candidates=[]
    def add(path: Path | None):
        if path and path.is_file() and not _blocked(path, env):
            r=path.resolve()
            if r not in candidates: candidates.append(r)
    git=shutil.which("git.exe",path=env.get("PATH")) or shutil.which("git",path=env.get("PATH"))
    if git:
        root=Path(git).resolve().parent.parent
        add(root/"bin"/"bash.exe"); add(root/"usr"/"bin"/"bash.exe")
    for key in ("ProgramFiles","ProgramFiles(x86)"):
        if env.get(key):
            root=Path(env[key])/"Git"
            add(root/"bin"/"bash.exe"); add(root/"usr"/"bin"/"bash.exe")
    bash=shutil.which("bash.exe",path=env.get("PATH")) or shutil.which("bash",path=env.get("PATH"))
    add(Path(bash) if bash else None)
    if not candidates:
        raise LauncherError("Git for Windows Bash was not found; WSL/System32 and WindowsApps bash launchers are intentionally rejected.")
    return candidates[0]

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("script",type=Path); parser.add_argument("arguments",nargs=argparse.REMAINDER); args=parser.parse_args(argv)
    script=args.script.resolve()
    if not script.is_file(): print(f"invoke-git-bash: script not found: {script}",file=sys.stderr); return 2
    try: return subprocess.run([str(resolve_git_bash()),str(script),*args.arguments],check=False).returncode
    except (LauncherError,OSError) as exc: print(f"invoke-git-bash: {exc}",file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
