"""Checking a Firebase ID token, for the web app's "Continue with Google".

The web app signs people in to Google through Firebase Authentication and sends us the ID
token Firebase gives it. (Email and password accounts do not touch Firebase: the API checks
those itself, see veritas.services.passwords.) The token is a JWT signed by Google with RS256.
It counts only when everything Firebase documents for checking one holds: the signature is
by one of Google's current keys, it was issued for our project, it has not expired, and it
names an account. We also want a verified email, since that is all we know about the person.

Google's public keys are fetched from its JWKS address and kept for as long as Google's
Cache-Control says. A key id we have not seen makes us fetch again, at most once a minute,
because Google rotates the keys every few hours.

pycryptodome checks the signature. It is installed with eth-hash[pycryptodome].
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from pydantic import TypeAdapter, ValidationError

from veritas.passport.models import Name
from veritas.services.errors import Forbidden, ServiceError, Unavailable
from veritas.settings import Settings

CLOCK_SKEW_SECONDS = 60
"""How far in the future an issue time may be, for a server clock a little behind Google's."""
REFETCH_AFTER_SECONDS = 60
"""The soonest we fetch the keys again because a token names a key we do not have."""
DEFAULT_KEYS_TTL_SECONDS = 3600
MAX_KEYS_TTL_SECONDS = 24 * 3600


class TokenInvalid(ServiceError):
    status = 401

    def __init__(self, message: str = "Sign in again: your sign-in could not be checked.") -> None:
        super().__init__("token_invalid", message, headers={"WWW-Authenticate": "Bearer"})


@dataclass(frozen=True)
class Identity:
    """Who a checked token says the person is."""

    uid: str
    email: str
    name: str | None


class GoogleKeys:
    """Google's current token-signing keys, by key id, fetched when needed."""

    def __init__(
        self,
        url: str,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.client = client or httpx.Client(timeout=5)
        self.clock = clock
        self._keys: dict[str, RSA.RsaKey] = {}
        self._expires = 0.0
        self._fetched = 0.0
        self._lock = threading.Lock()

    def get(self, kid: str) -> RSA.RsaKey | None:
        with self._lock:
            now = self.clock()
            stale = now >= self._expires
            unknown = kid not in self._keys and now - self._fetched >= REFETCH_AFTER_SECONDS
            if stale or unknown:
                self._fetch(now)
            return self._keys.get(kid)

    def _fetch(self, now: float) -> None:
        self._fetched = now
        try:
            response = self.client.get(self.url)
            response.raise_for_status()
            keys = _parse_jwks(response.json())
        except (httpx.HTTPError, ValueError) as error:
            if self._keys and now < self._expires:
                return  # keep the keys we have until they run out
            raise Unavailable(
                "sign_in_unavailable",
                "Sign-in cannot be checked right now. Try again in a minute.",
                headers={"Retry-After": "60"},
            ) from error
        self._keys = keys
        self._expires = now + _max_age(response.headers.get("cache-control", ""))


def verify_id_token(token: str, settings: Settings, keys: GoogleKeys) -> Identity:
    """The identity in a Firebase ID token, or an error saying why it does not count."""
    project = settings.firebase_project_id
    if not project:
        raise Unavailable(
            "google_not_configured",
            "Signing in with Google is not set up on this server.",
        )
    try:
        header_part, payload_part, signature_part = token.split(".")
        header = json.loads(_unb64(header_part))
        payload = json.loads(_unb64(payload_part))
        signature = _unb64(signature_part)
    except (ValueError, binascii.Error):
        raise TokenInvalid() from None
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise TokenInvalid()
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise TokenInvalid()

    key = keys.get(header["kid"])
    if key is None:
        raise TokenInvalid()
    signed = f"{header_part}.{payload_part}".encode("ascii")
    try:
        pkcs1_15.new(key).verify(SHA256.new(signed), signature)
    except (ValueError, TypeError):
        raise TokenInvalid() from None

    now = time.time()
    if payload.get("iss") != f"https://securetoken.google.com/{project}":
        raise TokenInvalid()
    if payload.get("aud") != project:
        raise TokenInvalid()
    if not _number(payload.get("exp")) or payload["exp"] <= now:
        raise TokenInvalid("Sign in again: the sign-in token has expired.")
    for claim in ("iat", "auth_time"):
        if not _number(payload.get(claim)) or payload[claim] > now + CLOCK_SKEW_SECONDS:
            raise TokenInvalid()
    uid = payload.get("sub")
    if not isinstance(uid, str) or not 0 < len(uid) <= 128:
        raise TokenInvalid()

    email = payload.get("email")
    if not isinstance(email, str) or not email or payload.get("email_verified") is not True:
        raise Forbidden(
            "email_not_verified",
            "Google has not confirmed the email address of this account, so it cannot sign in.",
        )
    return Identity(uid=uid, email=email, name=_name(payload.get("name")))


_NAME = TypeAdapter(Name)


def _name(value: Any) -> str | None:
    """The account's display name, if it is one we would accept from the person."""
    if not isinstance(value, str):
        return None
    try:
        return _NAME.validate_python(value.strip())
    except ValidationError:
        return None


def _number(value: Any) -> bool:
    """A real time: Python's JSON reader would also give NaN and infinity."""
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _unb64(part: str) -> bytes:
    """Base64url without padding, as JWTs use it."""
    if not re.fullmatch(r"[A-Za-z0-9_-]*", part):
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _parse_jwks(body: Any) -> dict[str, RSA.RsaKey]:
    keys = {}
    for jwk in body.get("keys", []) if isinstance(body, dict) else []:
        if not isinstance(jwk, dict) or jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
            continue
        kid, n, e = jwk.get("kid"), jwk.get("n"), jwk.get("e")
        if not all(isinstance(value, str) for value in (kid, n, e)):
            continue
        keys[kid] = RSA.construct(
            (int.from_bytes(_unb64(n), "big"), int.from_bytes(_unb64(e), "big"))
        )
    if not keys:
        raise ValueError("no RSA signing keys")
    return keys


def _max_age(cache_control: str) -> float:
    match = re.search(r"max-age=(\d+)", cache_control)
    if not match:
        return DEFAULT_KEYS_TTL_SECONDS
    return min(int(match.group(1)), MAX_KEYS_TTL_SECONDS)
