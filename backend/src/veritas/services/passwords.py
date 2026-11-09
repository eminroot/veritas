"""Passwords for the web app's accounts: the rules for choosing one, and how they are kept.

A password is kept only as scrypt from Python's standard library, with a random salt of its
own and the settings OWASP gives for scrypt (N=2^15, r=8, p=3: 32 MiB, and about a quarter of
a second per check, which is the point). The settings are stored with the hash, so they can be
raised later: a login with a password kept under older settings stores it again under the new
ones. Put a rate limit on /v1/auth in front of the API as well (nginx limit_req): each check
costs real CPU.

Passwords are compared as Unicode NFKC, so the same letters typed on another keyboard or phone
(ə, ı, ş, ç composed or not) still match.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import unicodedata

N, R, P = 2**15, 8, 3
MIN_LENGTH = 8
MAX_LENGTH = 128
_MAX_MEMORY = 64 * 1024 * 1024
_PREFIX = f"scrypt${N}${R}${P}$"
# Checked when there is no hash to check against, so an unknown email takes as long to refuse
# as a wrong password.
_DUMMY_SALT = b"\x00" * 16


def normalize(password: str) -> str:
    return unicodedata.normalize("NFKC", password)


def check_new(password: str) -> str:
    """The password as it will be kept, or ValueError saying what is wrong with it."""
    password = normalize(password)
    if len(password) < MIN_LENGTH:
        raise ValueError(f"must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise ValueError(f"must be at most {MAX_LENGTH} characters")
    if not password.strip():
        raise ValueError("cannot be only spaces")
    return password


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(normalize(password), salt, N, R, P)
    return f"{_PREFIX}{_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Whether the password matches. Without a stored hash it still does the work, and says no."""
    password = normalize(password)
    if stored is None:
        _scrypt(password, _DUMMY_SALT, N, R, P)
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, _unb64(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, _unb64(digest))
    except ValueError:
        return False


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(_PREFIX)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAX_MEMORY, dklen=32
    )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text, validate=True)
