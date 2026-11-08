"""Signed webhooks from the card provider.

The provider signs `<timestamp>.<raw body>` with HMAC-SHA256 under a secret only it and
Veritas know, and sends `t=<timestamp>,v1=<hex>` in a header. Veritas recomputes the HMAC
over the exact bytes it received, compares in constant time, and refuses anything older than
a few minutes so a captured webhook cannot be replayed later. A valid signature is still not
enough to count money: the payment is looked up again with the provider before any donation
row is written.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "Veritas-PSP-Signature"
TOLERANCE_SECONDS = 300


class WebhookError(ValueError):
    """A webhook that is not signed, signed wrongly, or too old."""


def sign(secret: bytes, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verify(
    secret: bytes,
    header: str | None,
    body: bytes,
    now: float,
    tolerance: int = TOLERANCE_SECONDS,
) -> int:
    """Returns the signed timestamp, or raises WebhookError."""
    if not header:
        raise WebhookError("the webhook is not signed")
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, ValueError) as exc:
        raise WebhookError("the signature has no timestamp") from exc
    if abs(now - timestamp) > tolerance:
        raise WebhookError("the webhook is too old or from the future")
    expected = hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, given) for given in parts.get("v1", [])):
        raise WebhookError("the signature does not match")
    return timestamp
