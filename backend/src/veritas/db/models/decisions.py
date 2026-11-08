"""Decisions and money out: officer decisions, ballots and votes, releases, the bank's
payouts and refunds, and donors' claims on a stopped or finished project.

Every row here is the off-chain side of something signed and anchored: the signature is kept
next to the outbox row that carried it, and the indexer fills in what the chain recorded.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from veritas.db.base import (
    Base,
    CreatedAt,
    Qapik,
    Timestamps,
    UUIDPrimaryKey,
    byte_length,
    evm_address,
    one_of,
)


class OfficerDecision(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "officer_decisions"
    __table_args__ = (
        Index(
            "uq_officer_decisions_one_per_attempt",
            "project_id",
            "milestone_index",
            "attempt",
            unique=True,
            postgresql_where=text("failed_at IS NULL"),
        ),
        byte_length("invoice_hash", 32),
        byte_length("reason_hash", 32),
        CheckConstraint("NOT override_checks OR reason IS NOT NULL", name="override_has_reason"),
        CheckConstraint("approve OR reason IS NOT NULL", name="rejection_has_reason"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_index: Mapped[int]
    attempt: Mapped[int]
    approve: Mapped[bool]
    invoice_hash: Mapped[bytes | None]
    amount_qapik: Mapped[Qapik | None]
    override_checks: Mapped[bool] = mapped_column(default=False, server_default="false")
    reason: Mapped[str | None]
    """Stays off-chain. Its SHA-256 is anchored with the decision."""
    reason_hash: Mapped[bytes | None]
    signature: Mapped[bytes]
    officer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("officers.id"))
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))
    failed_at: Mapped[datetime | None]
    """Set when the chain refused the decision. A failed decision does not count, so the
    officer can sign the attempt again."""


class BallotKind(StrEnum):
    MILESTONE = "milestone"
    AMENDMENT = "amendment"
    STOP = "stop"


class BallotStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Ballot(Timestamps, Base):
    """A vote as the chain sees it. The id is the ballotId the VotingModule computes."""

    __tablename__ = "ballots"
    __table_args__ = (
        one_of("kind", BallotKind),
        one_of("status", BallotStatus),
        byte_length("id", 32),
    )

    id: Mapped[bytes] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str]
    milestone_index: Mapped[int]
    round: Mapped[int]
    eligible: Mapped[int]
    ends_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(default=BallotStatus.OPEN, server_default="open")
    yes: Mapped[int] = mapped_column(default=0, server_default="0")
    no: Mapped[int] = mapped_column(default=0, server_default="0")
    passed: Mapped[bool | None]
    turnout_fallback: Mapped[bool | None]
    close_outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))


class VoteStatus(StrEnum):
    SUBMITTED = "submitted"
    COUNTED = "counted"
    FAILED = "failed"


class Vote(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "votes"
    __table_args__ = (
        Index(
            "uq_votes_one_per_holder",
            "ballot_id",
            "holder",
            unique=True,
            postgresql_where=text("status <> 'failed'"),
        ),
        one_of("status", VoteStatus),
        evm_address("holder"),
    )

    ballot_id: Mapped[bytes] = mapped_column(ForeignKey("ballots.id"), index=True)
    holder: Mapped[str]
    approve: Mapped[bool]
    weight_qapik: Mapped[Qapik]
    signature: Mapped[bytes]
    status: Mapped[str] = mapped_column(default=VoteStatus.SUBMITTED, server_default="submitted")
    """A failed vote, one the chain refused, does not count: the donor may sign again."""
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))


class ReleaseStatus(StrEnum):
    REQUESTED = "requested"
    INSTRUCTED = "instructed"
    PAID = "paid"
    RETURNED = "returned"
    """The bank could not pay; the money went back to the escrow."""


class Release(UUIDPrimaryKey, Timestamps, Base):
    """An approved milestone sent to the payout vault for the contractor."""

    __tablename__ = "releases"
    __table_args__ = (one_of("status", ReleaseStatus), byte_length("invoice_hash", 32))

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_index: Mapped[int]
    amount_qapik: Mapped[Qapik]
    invoice_hash: Mapped[bytes]
    instruction_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    status: Mapped[str] = mapped_column(default=ReleaseStatus.REQUESTED, server_default="requested")
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))


class PayoutKind(StrEnum):
    PAYOUT = "payout"
    REFUND = "refund"


class PayoutStatus(StrEnum):
    INSTRUCTED = "instructed"
    """On-chain instruction seen; the bank has not acted yet."""
    BANK_PAID = "bank_paid"
    BANK_FAILED = "bank_failed"
    CONFIRMED = "confirmed"
    """The bank's confirmation is on-chain and the vAZN burned."""
    RETURNED = "returned"
    """The bank's failure is on-chain and the vAZN went back to the escrow."""


class Payout(UUIDPrimaryKey, Timestamps, Base):
    """The bank's side of one payout-vault instruction: a contractor payout or a refund."""

    __tablename__ = "payouts"
    __table_args__ = (
        one_of("kind", PayoutKind),
        one_of("status", PayoutStatus),
        byte_length("payment_ref", 32),
        byte_length("claim_id", 32),
    )

    instruction_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    kind: Mapped[str]
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_index: Mapped[int | None]
    holder: Mapped[str | None]
    claim_id: Mapped[bytes | None]
    """For a refund: the claim it pays out."""
    amount_qapik: Mapped[Qapik]
    status: Mapped[str] = mapped_column(
        default=PayoutStatus.INSTRUCTED, server_default="instructed"
    )
    payment_ref: Mapped[bytes | None]
    bank_signature: Mapped[bytes | None]
    reason: Mapped[str | None]
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))


class ClaimAction(StrEnum):
    REFUND = "refund"
    REDIRECT = "redirect"


class ClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    EXECUTED = "executed"
    FAILED = "failed"


class Claim(UUIDPrimaryKey, Timestamps, Base):
    """A donor's choice on a stopped or finished project, or the default applied for them."""

    __tablename__ = "claims"
    __table_args__ = (
        one_of("action", ClaimAction),
        one_of("status", ClaimStatus),
        evm_address("holder"),
        byte_length("claim_id", 32),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    holder: Mapped[str]
    action: Mapped[str]
    target_project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    by_default: Mapped[bool] = mapped_column(default=False, server_default="false")
    nonce: Mapped[int | None]
    deadline: Mapped[int | None] = mapped_column(BigInteger)
    signature: Mapped[bytes | None]
    allocation_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    claim_id: Mapped[bytes | None]
    amount_qapik: Mapped[Qapik | None]
    """Known once the Claimed event is indexed."""
    status: Mapped[str] = mapped_column(default=ClaimStatus.SUBMITTED, server_default="submitted")
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    """The account that sent the donor's choice through the API. A redirect's receipt in the
    other project belongs to this account."""
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
