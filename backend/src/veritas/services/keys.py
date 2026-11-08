"""Proof that a user holds a key: they sign a one-time challenge with it.

The app signs the challenge text with EIP-191 personal_sign, the same call every
wallet library has, and we recover the address from the signature. The text
names the purpose, the account and, for a charity key, the charity, so a
signature made for one purpose is useless for another. Each challenge works once
and expires after a few minutes.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.db.models import ChallengePurpose, DeviceChallenge, User
from veritas.db.session import db_now
from veritas.services.errors import BadRequest
from veritas.settings import Settings

_PURPOSE_TEXT = {
    ChallengePurpose.DEVICE: "register a device key",
    ChallengePurpose.CHARITY_SIGNER: "set the signing key of charity {charity_id}",
}


def issue_challenge(
    session: Session,
    settings: Settings,
    user: User,
    purpose: ChallengePurpose,
    charity_id: uuid.UUID | None = None,
) -> DeviceChallenge:
    now = db_now(session)
    nonce = secrets.token_hex(16)
    expires_at = now + timedelta(seconds=settings.key_challenge_ttl_seconds)
    message = "\n".join(
        [
            "Veritas key check",
            f"Purpose: {_PURPOSE_TEXT[purpose].format(charity_id=charity_id)}",
            f"Account: {user.id}",
            f"Nonce: {nonce}",
            f"Expires: {expires_at.isoformat()}",
        ]
    )
    challenge = DeviceChallenge(
        user_id=user.id,
        nonce=nonce,
        purpose=purpose,
        charity_id=charity_id,
        message=message,
        expires_at=expires_at,
    )
    session.add(challenge)
    session.flush()
    return challenge


def recover_signer(message: str, signature: bytes) -> str | None:
    """The checksummed address that signed `message` with personal_sign, or None."""
    try:
        return Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:  # eth-keys raises several unrelated types for malformed signatures
        return None


def prove_key(
    session: Session,
    user: User,
    *,
    purpose: ChallengePurpose,
    nonce: str,
    address: str,
    signature: bytes,
    charity_id: uuid.UUID | None = None,
) -> DeviceChallenge:
    """Check that `address` signed the challenge `nonce`, and use the challenge up.

    `address` must already be checksummed.
    """
    challenge = session.scalars(
        select(DeviceChallenge)
        .where(
            DeviceChallenge.nonce == nonce,
            DeviceChallenge.user_id == user.id,
            DeviceChallenge.purpose == purpose,
            DeviceChallenge.charity_id.is_(None)
            if charity_id is None
            else DeviceChallenge.charity_id == charity_id,
        )
        .with_for_update()
    ).first()
    if challenge is None:
        raise BadRequest("challenge_invalid", "This challenge is unknown. Ask for a new one.")
    if challenge.used_at is not None:
        raise BadRequest("challenge_used", "This challenge was already used. Ask for a new one.")
    now = db_now(session)
    if challenge.expires_at <= now:
        raise BadRequest("challenge_expired", "This challenge has expired. Ask for a new one.")
    if recover_signer(challenge.message, signature) != address:
        raise BadRequest(
            "signature_invalid", "The signature was not made by this key for this challenge."
        )
    challenge.used_at = now
    return challenge
