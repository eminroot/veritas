"""People who log in, their sessions and the keys on their phones.

The app logs in with a code sent to a phone. The web app's accounts log in with an email and a
password, checked here, or with Google through Firebase. An account has at least one way in.

Login codes, passwords, reset links and session tokens are stored only as hashes, so a copy of
the database is not a way to log in.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, false, text
from sqlalchemy.orm import Mapped, mapped_column

from veritas.db.base import (
    Base,
    CreatedAt,
    Timestamps,
    UUIDPrimaryKey,
    az_phone,
    byte_length,
    evm_address,
    one_of,
)


class Platform(StrEnum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class ChallengePurpose(StrEnum):
    DEVICE = "device"
    CHARITY_SIGNER = "charity_signer"


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        az_phone("phone"),
        CheckConstraint("recovery_failures >= 0", name="recovery_failures_not_negative"),
        CheckConstraint("password_failures >= 0", name="password_failures_not_negative"),
        CheckConstraint(
            "phone IS NOT NULL OR password_hash IS NOT NULL OR firebase_uid IS NOT NULL",
            name="has_a_login",
        ),
        CheckConstraint("password_hash IS NULL OR email IS NOT NULL", name="password_needs_email"),
        CheckConstraint("email = lower(email)", name="email_lower_case"),
    )

    phone: Mapped[str | None] = mapped_column(unique=True)
    """For logging in with a code sent to it, in the app. Unset for accounts made on the web."""
    email: Mapped[str | None] = mapped_column(unique=True)
    """Lower case. Password logins use it, and the links to set a new password go to it."""
    password_hash: Mapped[str | None]
    """scrypt, as veritas.services.passwords writes it. Unset: no password login."""
    password_failures: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    """Wrong passwords since the last right one."""
    password_locked_until: Mapped[datetime | None]
    firebase_uid: Mapped[str | None] = mapped_column(unique=True)
    """The Google account, through Firebase, that signs in to this account."""
    display_name: Mapped[str | None]
    is_admin: Mapped[bool] = mapped_column(default=False, server_default=false())
    """A Veritas staff member who reviews charities, contractors and officers."""
    recovery_failures: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    """Wrong answers given to recover a receipt after a lost phone, across all of the
    account's receipts: the answer is a card the account paid with, so it is one secret."""

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def has_google(self) -> bool:
        return self.firebase_uid is not None


class PasswordReset(UUIDPrimaryKey, CreatedAt, Base):
    """A link to set a new password, sent by email. Only the token's SHA-256 is kept."""

    __tablename__ = "password_resets"
    __table_args__ = (byte_length("token_hash", 32),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class LoginCode(UUIDPrimaryKey, CreatedAt, Base):
    """A one-time code sent to a phone. Only an HMAC of it is kept."""

    __tablename__ = "login_codes"
    __table_args__ = (
        az_phone("phone"),
        byte_length("code_hmac", 32),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        Index("ix_login_codes_phone_created_at", "phone", "created_at"),
    )

    phone: Mapped[str]
    code_hmac: Mapped[bytes]
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    consumed_at: Mapped[datetime | None]


class Device(UUIDPrimaryKey, CreatedAt, Base):
    """A key held in a phone's secure storage, shown as its address.

    An address is registered once. A revoked key stays in the table, so it can
    never be registered again.
    """

    __tablename__ = "devices"
    __table_args__ = (evm_address("address"), one_of("platform", Platform))

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    address: Mapped[str] = mapped_column(unique=True)
    platform: Mapped[str]
    label: Mapped[str | None]
    attestation: Mapped[str | None]
    """App Attest or Play Integrity token as the app sent it. Not checked until Phase 6."""
    revoked_at: Mapped[datetime | None]


class AuthSession(UUIDPrimaryKey, CreatedAt, Base):
    """A bearer token. Only its SHA-256 is stored."""

    __tablename__ = "sessions"
    __table_args__ = (byte_length("token_hash", 32),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), index=True
    )
    """The device key registered from this session. Revoking the key ends the session."""


class DeviceChallenge(UUIDPrimaryKey, CreatedAt, Base):
    """A one-time message a user signs to prove they hold a key."""

    __tablename__ = "device_challenges"
    __table_args__ = (
        one_of("purpose", ChallengePurpose),
        CheckConstraint(
            "(purpose = 'charity_signer') = (charity_id IS NOT NULL)",
            name="charity_only_for_signer",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    nonce: Mapped[str] = mapped_column(unique=True)
    purpose: Mapped[str]
    charity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("charities.id", ondelete="CASCADE")
    )
    message: Mapped[str]
    """The exact text to sign. Kept, so the signature is checked against what was sent."""
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
