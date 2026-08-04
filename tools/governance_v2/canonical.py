"""Deterministic JSON and digest helpers for governance v2."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Return the UTF-8 canonical JSON representation used by v2 contracts."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_text(value: str) -> str:
    """Hash text as UTF-8 and return a lowercase hexadecimal digest."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    """Hash bytes and return a lowercase hexadecimal digest."""

    return hashlib.sha256(value).hexdigest()


def sha256_canonical(value: Any) -> str:
    """Hash a JSON-compatible value using :func:`canonical_json`."""

    return sha256_text(canonical_json(value))


def without_field(value: dict[str, Any], field: str) -> dict[str, Any]:
    """Copy a mapping without one digest field."""

    result = dict(value)
    result.pop(field, None)
    return result
