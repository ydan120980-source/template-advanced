#!/usr/bin/env python3
"""Deterministic release archive builder for template-advanced.

Usage (from the repository root):

    py -3 scripts/build-release.py [--version <version>] [--out-dir dist]

The builder selects files with the canonical allowlist and exclusion rules in
``tools/template_doctor/release_inventory.py``, records relative path, size,
SHA-256, and intended POSIX mode for every entry, and writes:

- ``dist/template-advanced-<version>.zip`` (fixed timestamps, sorted entries,
  explicit Unix modes, no compression so bytes are identical on every
  platform);
- ``dist/template-advanced-<version>.manifest.json`` (machine-readable);
- ``dist/template-advanced-<version>.digest.txt`` (publication digest).

Trusted source contract
-----------------------

Inside a Git work tree, the builder refuses to package files that cannot be
traced to a clean commit: any release file with uncommitted modifications,
any untracked release candidate, and any deleted release file blocks the
build and lists the offending paths. File content and modes are read from the
Git object database and index at HEAD, so working-tree edits can never change
published artifact bytes and the result corresponds exactly to one commit.

Outside a Git work tree (for example, a plain extraction of a release ZIP),
the builder refuses to produce a formal artifact and requires
``--allow-unverified``; the resulting archive is labeled an
``unverified-source-tree`` build because its bytes cannot be traced to a
commit.

Building twice from the same commit produces byte-identical archives,
manifests, and digests. Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path


# Never write bytecode caches into the workspace, even when the caller did not
# preset PYTHONDONTWRITEBYTECODE or pass -B.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.template_doctor.release_inventory import (  # noqa: E402
    RELEASE_ROOT_NAME,
    RELEASE_VERSION,
    ReleaseEntry,
    iter_release_entries,
    publication_digest,
    select_release_paths,
)
from tools.template_doctor.release_source import (  # noqa: E402
    ReleaseSourceError,
    resolve_release_source,
)


# Fixed epoch keeps archives byte-identical across builds and platforms.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

MANIFEST_SCHEMA = "template-advanced/release-manifest/v1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py -3 scripts/build-release.py",
        description="Build a deterministic template-advanced release archive.",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    parser.add_argument("--version", default=RELEASE_VERSION, help="release version")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "dist"), help="output directory")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help=(
            "Allow building from a directory that is not a clean Git work "
            "tree and label the result an unverified-source-tree build."
        ),
    )
    return parser


def _manifest(
    *,
    root_name: str,
    version: str,
    entries: list[ReleaseEntry],
    digest: str,
    source_type: str,
    source_label: str,
    commit: str | None,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "root_name": root_name,
        "version": version,
        "file_count": len(entries),
        "publication_digest": digest,
        "source": {
            "type": source_type,
            "label": source_label,
        },
        "files": [entry.to_dict() for entry in entries],
    }
    if commit:
        manifest["source"]["commit"] = commit
    return manifest


def _write_artifacts(
    out_dir: Path,
    version: str,
    entries: list[ReleaseEntry],
    contents: dict[str, bytes],
    manifest: dict[str, object],
    digest: str,
) -> None:
    stem = f"{RELEASE_ROOT_NAME}-{version}"
    archive_path = out_dir / f"{stem}.zip"
    manifest_path = out_dir / f"{stem}.manifest.json"
    digest_path = out_dir / f"{stem}.digest.txt"

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        for entry in entries:
            info = zipfile.ZipInfo(entry.path, date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3  # Unix metadata so modes survive extraction
            info.external_attr = (entry.mode & 0xFFFF) << 16
            archive.writestr(info, contents[entry.path])

    # Explicit UTF-8 + LF bytes so Windows and POSIX produce identical text
    # files regardless of the platform's default newline behavior.
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    digest_path.write_bytes((digest + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    release_paths = select_release_paths(root)
    if not release_paths:
        print("build-release: error: release inventory is empty", file=sys.stderr)
        return 2

    if args.allow_unverified:
        source_type = "unverified-source-tree"
        source_label = "unverified-source-tree build"
        commit: str | None = None
        entries = iter_release_entries(root)
        contents = {entry.path: (root / entry.path).read_bytes() for entry in entries}
        print(
            f"build-release: {source_label}; content cannot be traced to a commit",
            file=sys.stderr,
        )
    else:
        try:
            source = resolve_release_source(root, release_paths)
        except ReleaseSourceError as exc:
            print(
                f"build-release: error: trusted source check failed: {exc}",
                file=sys.stderr,
            )
            print(
                "build-release: commit release files or restore HEAD; no artifact was produced",
                file=sys.stderr,
            )
            return 1
        commit = source.commit
        source_type = "git-commit"
        source_label = f"build from commit {commit[:12]}"
        contents = source.contents
        entries = [
            ReleaseEntry(
                path=path,
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                mode=source.file_modes[path],
            )
            for path, data in sorted(contents.items())
        ]

    digest = publication_digest(entries)
    manifest = _manifest(
        root_name=RELEASE_ROOT_NAME,
        version=args.version,
        entries=entries,
        digest=digest,
        source_type=source_type,
        source_label=source_label,
        commit=commit,
    )
    _write_artifacts(out_dir, args.version, entries, contents, manifest, digest)

    print(
        f"build-release: {source_label}; archive={out_dir / (RELEASE_ROOT_NAME + '-' + args.version + '.zip')}"
        f" files={len(entries)}"
    )
    print(f"build-release: manifest={out_dir / (RELEASE_ROOT_NAME + '-' + args.version + '.manifest.json')}")
    print(f"build-release: digest={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
