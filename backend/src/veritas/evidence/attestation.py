"""App attestation: proof that a manifest came from the genuine Veritas app on an unmodified
phone (ARCHITECTURE.md section 11).

Production will verify App Attest assertions on iOS and Play Integrity verdicts on Android.
Neither is built yet, so `PlatformAttestation` refuses every token and check 1 fails until
they are: the report then says plainly that the app's integrity was not confirmed.

Development and tests use `DevAttestation`, which anyone with the development secret can
produce, so production refuses to start with it (see Settings). Its token is "dev1." and
the hex HMAC-SHA256, keyed with attestation_dev_secret, of these four lines:

    Veritas dev attestation
    <device address, checksummed>
    <capture session id>
    <bundle hash as 0x hex>

It binds the phone's key, the capture session and the exact manifest, as an App Attest
assertion does with its client data hash: a token is good for one manifest only.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from typing import Protocol

from veritas.core.hashing import to_hex
from veritas.settings import Settings

DEV_TOKEN_PREFIX = "dev1."


@dataclass(frozen=True)
class Attestation:
    valid: bool
    scheme: str
    reason: str | None = None
    """Why the token was not accepted, worded to end a sentence."""


class AttestationVerifier(Protocol):
    scheme: str

    def verify(
        self,
        token: str | None,
        *,
        platform: str,
        device: str,
        session_id: uuid.UUID,
        bundle_hash: bytes,
    ) -> Attestation: ...


def dev_message(device: str, session_id: uuid.UUID, bundle_hash: bytes) -> bytes:
    return f"Veritas dev attestation\n{device}\n{session_id}\n{to_hex(bundle_hash)}".encode()


def dev_token(secret: bytes, *, device: str, session_id: uuid.UUID, bundle_hash: bytes) -> str:
    """What the development build sends. Tests use it to play the app."""
    digest = hmac.new(secret, dev_message(device, session_id, bundle_hash), hashlib.sha256)
    return DEV_TOKEN_PREFIX + digest.hexdigest()


class DevAttestation:
    scheme = "dev"

    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def verify(
        self,
        token: str | None,
        *,
        platform: str,
        device: str,
        session_id: uuid.UUID,
        bundle_hash: bytes,
    ) -> Attestation:
        if not token:
            return Attestation(False, self.scheme, "the app sent no attestation token")
        if not token.startswith(DEV_TOKEN_PREFIX):
            return Attestation(
                False, self.scheme, "the attestation token is not one this server knows"
            )
        expected = dev_token(
            self._secret, device=device, session_id=session_id, bundle_hash=bundle_hash
        )
        if not hmac.compare_digest(token.encode(), expected.encode()):
            return Attestation(
                False,
                self.scheme,
                "the attestation token was not made for this device, session and manifest",
            )
        return Attestation(True, self.scheme)


class PlatformAttestation:
    """App Attest and Play Integrity. Not built yet, so nothing passes."""

    scheme = "platform"

    def verify(
        self,
        token: str | None,
        *,
        platform: str,
        device: str,
        session_id: uuid.UUID,
        bundle_hash: bytes,
    ) -> Attestation:
        if platform == "web":
            return Attestation(
                False, self.scheme, "evidence must come from the phone app, a browser cannot attest"
            )
        return Attestation(
            False,
            self.scheme,
            "App Attest and Play Integrity checks are not built yet, so this server cannot "
            "confirm the evidence came from the genuine app",
        )


def attestation_verifier(settings: Settings) -> AttestationVerifier:
    if settings.attestation_scheme == "dev":
        return DevAttestation(settings.attestation_dev_secret.get_secret_value().encode())
    return PlatformAttestation()
