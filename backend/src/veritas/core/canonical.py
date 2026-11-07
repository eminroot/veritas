"""Canonical JSON (RFC 8785, the JSON Canonicalization Scheme).

A Passport, an evidence manifest or a check report is hashed over its canonical
bytes: keys sorted, no whitespace, numbers and strings in one fixed form. The JS
side uses the `canonicalize` package, which follows the same RFC, so the app and
the verifier page get the same bytes and the same hash.

Hash what you publish. Keep the canonical bytes next to the hash, and never
re-serialise an old document with a newer model, or the hash can change.
"""

from __future__ import annotations

import json
from typing import Any

import rfc8785

from veritas.core.hashing import sha256


class CanonicalJSONError(ValueError):
    """A value that cannot be canonicalised, or bytes that are not canonical."""


def canonical_json(value: Any) -> bytes:
    """Canonical UTF-8 bytes for a JSON value."""
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError) as exc:
        raise CanonicalJSONError(str(exc) or type(exc).__name__) from exc


def canonical_hash(value: Any) -> bytes:
    """SHA-256 of the canonical bytes."""
    return sha256(canonical_json(value))


def parse_canonical(data: bytes) -> Any:
    """Parse JSON bytes, refusing anything that is not already in canonical form."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalJSONError(f"not valid JSON: {exc}") from exc
    if canonical_json(value) != data:
        raise CanonicalJSONError("document is not in canonical form")
    return value
