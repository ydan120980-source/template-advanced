#!/usr/bin/env python3
"""Deterministic release archive builder for template-advanced.

Usage (from the repository root):

    py -3 scripts/build-release.py [--version 1.0.0] [--out-dir dist]

The builder selects files with the canonical allowlist and exclusion rules in
``tools/template_doctor/release_inventory.py``, records relative path, size,
SHA-256, and intended POSIX mode for every entry, and writes:

- ``dist/template-advanced-<version>.zip`` (fixed timestamps, sorted entries,
  explicit Unix modes, no compression so bytes are identical on every
  platform);
- ``dist/template-advanced-<version>.manifest.json`` (machine-readable);
- ``dist/template-advanced-<version>.digest.txt`` (publication digest).

Building twice from the same tree produces byte-identical archives, manifests,
and digests. Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
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
    iter_release_entries,
    publication_digest,
)


# Fixed epoch keeps archives byte-identical across builds and platforms.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py -3 scripts/build-release.py",
        description="Build a deterministic template-advanced release archive.",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    parser.add_argument("--version", default=RELEASE_VERSION, help="release version")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "dist"), help="output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = iter_release_entries(root)
    if not entries:
        print("build-release: error: release inventory is empty", file=sys.stderr)
        return 2

    digest = publication_digest(entries)
    stem = f"{RELEASE_ROOT_NAME}-{args.version}"
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
            archive.writestr(info, (root / entry.path).read_bytes())

    manifest = {
        "schema": "template-advanced/release-manifest/v1",
        "root_name": RELEASE_ROOT_NAME,
        "version": args.version,
        "file_count": len(entries),
        "publication_digest": digest,
        "files": [entry.to_dict() for entry in entries],
    }
    # Explicit UTF-8 + LF bytes so Windows and POSIX produce identical text
    # files regardless of the platform's default newline behavior.
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    digest_path.write_bytes((digest + "\n").encode("utf-8"))

    print(f"build-release: archive={archive_path.name} files={len(entries)}")
    print(f"build-release: manifest={manifest_path.name}")
    print(f"build-release: digest={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
