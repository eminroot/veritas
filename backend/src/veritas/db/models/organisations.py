"""Charities, contractors and Verification Officers, and the documents behind them.

A charity or contractor is checked off-chain (KYB) before it can appear in a
published Passport. The checks themselves are people reading documents for now;
VÖEN lookups against the tax registry come in Phase 7.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, UniqueConstraint
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
    voen,
)


class CharityStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class MemberRole(StrEnum):
    ADMIN = "admin"
    FIELD_WORKER = "field_worker"


class ContractorStatus(StrEnum):
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"


class RegistryStatus(StrEnum):
    """What the tax registry says about a VÖEN, or what a person found by hand."""

    UNCHECKED = "unchecked"
    ACTIVE = "active"
    INACTIVE = "inactive"
    NOT_FOUND = "not_found"
    MANUAL_OK = "manual_ok"


class OwnerType(StrEnum):
    CHARITY = "charity"
    CONTRACTOR = "contractor"


class DocumentKind(StrEnum):
    REGISTRATION = "registration"
    CHARTER = "charter"
    TAX_REGISTRATION = "tax_registration"
    DIRECTOR_ID = "director_id"
    BANK_LETTER = "bank_letter"
    OTHER = "other"


class OfficerStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


DOCUMENT_TYPES = ("application/pdf", "image/jpeg", "image/png")


class Charity(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "charities"
    __table_args__ = (
        one_of("status", CharityStatus),
        voen(),
        az_phone("contact_phone"),
        evm_address("signer_address"),
    )

    legal_name: Mapped[str]
    voen: Mapped[str] = mapped_column(unique=True)
    legal_form: Mapped[str]
    legal_address: Mapped[str]
    director_name: Mapped[str]
    contact_email: Mapped[str]
    contact_phone: Mapped[str]
    website: Mapped[str | None]
    status: Mapped[str] = mapped_column(default=CharityStatus.DRAFT, server_default="draft")
    signer_address: Mapped[str | None] = mapped_column(unique=True)
    """The charity's on-chain key. It signs Passports and evidence from Phase 4 on."""
    submitted_at: Mapped[datetime | None]
    verified_at: Mapped[datetime | None]
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_notes: Mapped[str | None]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class CharityMember(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "charity_members"
    __table_args__ = (
        UniqueConstraint("charity_id", "user_id"),
        one_of("role", MemberRole),
    )

    charity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charities.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str]
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Contractor(UUIDPrimaryKey, Timestamps, Base):
    """A company a charity pays through the escrow. Its VÖEN goes into Passports."""

    __tablename__ = "contractors"
    __table_args__ = (
        one_of("status", ContractorStatus),
        one_of("registry_status", RegistryStatus),
        voen(),
        CheckConstraint("iban ~ '^AZ[0-9]{2}[A-Z]{4}[A-Z0-9]{20}$'", name="iban_format"),
    )

    legal_name: Mapped[str]
    voen: Mapped[str] = mapped_column(unique=True)
    iban: Mapped[str]
    legal_address: Mapped[str]
    director_name: Mapped[str]
    status: Mapped[str] = mapped_column(
        default=ContractorStatus.SUBMITTED, server_default="submitted"
    )
    registry_status: Mapped[str] = mapped_column(
        default=RegistryStatus.UNCHECKED, server_default="unchecked"
    )
    registry_checked_at: Mapped[datetime | None]
    registry_checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    registry_note: Mapped[str | None]
    review_notes: Mapped[str | None]
    verified_at: Mapped[datetime | None]
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    charity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charities.id"), index=True)
    """The charity whose member registered the contractor and may edit the record."""
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class KybDocument(UUIDPrimaryKey, CreatedAt, Base):
    """A registration paper, charter or ID scan. The file itself is in private storage."""

    __tablename__ = "kyb_documents"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "sha256"),
        one_of("owner_type", OwnerType),
        one_of("kind", DocumentKind),
        one_of("content_type", DOCUMENT_TYPES),
        byte_length("sha256", 32),
        CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
    )

    owner_type: Mapped[str]
    owner_id: Mapped[uuid.UUID]
    kind: Mapped[str]
    filename: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[bytes]
    storage_key: Mapped[str]
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Officer(UUIDPrimaryKey, Timestamps, Base):
    """A Verification Officer: the independent reviewer a Passport names by address."""

    __tablename__ = "officers"
    __table_args__ = (one_of("status", OfficerStatus), evm_address("address"))

    name: Mapped[str]
    organisation: Mapped[str]
    address: Mapped[str] = mapped_column(unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    status: Mapped[str] = mapped_column(default=OfficerStatus.ACTIVE, server_default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
