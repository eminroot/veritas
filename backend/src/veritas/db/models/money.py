"""Money in: donations, their split across milestones, hourly batches, receipts, and the
daily reconciliation.

A donation row exists only after a signed webhook and a second lookup with the card
provider, and it is unique on the provider's payment id, so no payment is counted twice. Each
donation is split into allocations, one per milestone, and each allocation is one Merkle leaf
with its own random salt. A batch is one hourly tree; its id is the batch id on-chain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, UniqueConstraint
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


class DonationKind(StrEnum):
    CARD = "card"
    PAY_ON_PROOF = "pay_on_proof"
    """A pledge charged after a milestone was approved. Its leaves carry the approval tx."""
    REDIRECT = "redirect"
    """Money a donor moved here from a stopped project. It moved on-chain already, so its
    leaves are anchored for proofs but credit nothing."""


class DonationStatus(StrEnum):
    RECEIVED = "received"
    BATCHED = "batched"
    IN_ESCROW = "in_escrow"
    REFUNDED = "refunded"
    """Returned to the card before it reached escrow, for example because the project stopped."""


class Donation(UUIDPrimaryKey, Timestamps, Base):
    """One payment. Its id is the donationId in every leaf it becomes."""

    __tablename__ = "donations"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id"),
        one_of("kind", DonationKind),
        one_of("status", DonationStatus),
        evm_address("holder"),
        byte_length("trigger", 32),
        CheckConstraint("amount_qapik > 0", name="amount_positive"),
        CheckConstraint(
            "refunded_qapik >= 0 AND refunded_qapik <= amount_qapik", name="refund_in_range"
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    holder: Mapped[str]
    """The donor's key for this project. It names them on-chain and nothing else does."""
    amount_qapik: Mapped[Qapik]
    kind: Mapped[str] = mapped_column(default=DonationKind.CARD, server_default="card")
    provider: Mapped[str]
    provider_payment_id: Mapped[str]
    """For a redirect: the on-chain claim id it came from."""
    card_last4: Mapped[str | None]
    trigger: Mapped[bytes] = mapped_column(default=bytes(32))
    status: Mapped[str] = mapped_column(default=DonationStatus.RECEIVED, server_default="received")
    refunded_qapik: Mapped[Qapik] = mapped_column(default=0, server_default="0")
    pledge_charge_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pledge_charges.id"))


class AllocationStatus(StrEnum):
    RECEIVED = "received"
    BATCHED = "batched"
    IN_ESCROW = "in_escrow"
    CLAIMED = "claimed"
    """The donor took this leaf's share back as a refund or a redirect."""
    VOID = "void"
    """Never anchored: refunded before it reached a batch."""


class Allocation(UUIDPrimaryKey, CreatedAt, Base):
    """The part of one donation that went to one milestone: one Merkle leaf."""

    __tablename__ = "allocations"
    __table_args__ = (
        UniqueConstraint("donation_id", "milestone_index"),
        one_of("status", AllocationStatus),
        evm_address("holder"),
        byte_length("salt", 32),
        byte_length("trigger", 32),
        byte_length("leaf_hash", 32),
        CheckConstraint("amount_qapik > 0", name="amount_positive"),
    )

    donation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donations.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_index: Mapped[int]
    amount_qapik: Mapped[Qapik]
    holder: Mapped[str]
    salt: Mapped[bytes]
    """Random, stored the moment it is made, and given only to the donor."""
    trigger: Mapped[bytes]
    leaf_hash: Mapped[bytes] = mapped_column(unique=True)
    credited: Mapped[bool] = mapped_column(default=True, server_default="true")
    """False for redirect leaves: their money reached the escrow on-chain already."""
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), index=True)
    status: Mapped[str] = mapped_column(
        default=AllocationStatus.RECEIVED, server_default="received"
    )


class BatchStatus(StrEnum):
    BUILT = "built"
    """Tree built and signed, anchoring transaction in the outbox."""
    ANCHORED = "anchored"
    """On-chain, waiting for the bank to settle (provider mode)."""
    SETTLED = "settled"
    """On-chain and backed by vAZN: every leaf in it is "in escrow"."""
    FAILED = "failed"


class Batch(Timestamps, Base):
    __tablename__ = "batches"
    __table_args__ = (
        one_of("status", BatchStatus),
        one_of("mode", ("bank", "provider")),
        byte_length("root", 32),
        byte_length("credits_hash", 32),
        CheckConstraint("id > 0", name="id_positive"),
        CheckConstraint("leaf_count > 0", name="leaf_count_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    """The on-chain batch id. Batches go on-chain in this order, one after another."""
    root: Mapped[bytes]
    leaf_count: Mapped[int]
    total_qapik: Mapped[Qapik]
    credits: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    credits_hash: Mapped[bytes]
    tree: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """The StandardMerkleTree dump, so any proof can be rebuilt and checked."""
    mode: Mapped[str] = mapped_column(default="bank", server_default="bank")
    bank_signature: Mapped[bytes | None]
    status: Mapped[str] = mapped_column(default=BatchStatus.BUILT, server_default="built")
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))
    anchored_block: Mapped[int | None] = mapped_column(BigInteger)
    anchored_tx: Mapped[bytes | None]
    settled_at: Mapped[datetime | None]


class BatchLeaf(Base):
    """Where an allocation sits in its batch's tree, and its proof."""

    __tablename__ = "batch_leaves"

    allocation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("allocations.id"), primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    tree_index: Mapped[int]
    proof: Mapped[list[str]] = mapped_column(JSONB)


class ReceiptStatus(StrEnum):
    PENDING = "pending"
    MINTED = "minted"


class Receipt(UUIDPrimaryKey, Timestamps, Base):
    """A donor's locked receipt token for a project, one per holder."""

    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("project_id", "holder"),
        one_of("status", ReceiptStatus),
        evm_address("holder"),
        evm_address("controller"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    holder: Mapped[str]
    token_id: Mapped[str] = mapped_column(unique=True)
    """The uint256 receipt id as decimal text."""
    controller: Mapped[str]
    """The key that signs for this holder now. Changes with a key rotation."""
    status: Mapped[str] = mapped_column(default=ReceiptStatus.PENDING, server_default="pending")
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))


class Reconciliation(UUIDPrimaryKey, CreatedAt, Base):
    """One day's comparison of the three numbers that must agree."""

    __tablename__ = "reconciliations"
    __table_args__ = (byte_length("statement_hash", 32),)

    day: Mapped[int] = mapped_column(BigInteger, unique=True)
    cutoff_block: Mapped[int] = mapped_column(BigInteger)
    cutoff_time: Mapped[datetime]
    chain_supply_qapik: Mapped[Qapik]
    ledger_qapik: Mapped[Qapik]
    bank_balance_qapik: Mapped[Qapik]
    balanced: Mapped[bool]
    statement: Mapped[bytes]
    statement_hash: Mapped[bytes]
    bank_signature: Mapped[bytes]
    outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))


class PledgeStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    """A charge failed twice. The donor is told and can resume with a new card."""
    CANCELLED = "cancelled"


class Pledge(UUIDPrimaryKey, Timestamps, Base):
    """Pay-on-Proof: an amount charged to a saved card each time a milestone is approved."""

    __tablename__ = "pledges"
    __table_args__ = (
        one_of("status", PledgeStatus),
        evm_address("holder"),
        CheckConstraint("amount_qapik > 0", name="amount_positive"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    holder: Mapped[str]
    amount_qapik: Mapped[Qapik]
    card_token: Mapped[str]
    """The provider's token for the saved card. Veritas never sees the card itself."""
    card_last4: Mapped[str | None]
    status: Mapped[str] = mapped_column(default=PledgeStatus.ACTIVE, server_default="active")


class PledgeChargeStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    """Nothing left to fund, so no charge was made."""


class PledgeCharge(UUIDPrimaryKey, Timestamps, Base):
    """One charge of a pledge for one approval. Unique, so an approval charges once."""

    __tablename__ = "pledge_charges"
    __table_args__ = (
        UniqueConstraint("pledge_id", "milestone_index", "approval_round"),
        one_of("status", PledgeChargeStatus),
        byte_length("approval_tx", 32),
    )

    pledge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pledges.id"), index=True)
    milestone_index: Mapped[int]
    """The milestone whose approval triggered the charge."""
    approval_round: Mapped[int]
    approval_tx: Mapped[bytes]
    """The transaction that approved the milestone. It becomes the leaves' trigger."""
    amount_qapik: Mapped[Qapik]
    status: Mapped[str] = mapped_column(
        default=PledgeChargeStatus.PENDING, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    provider_payment_id: Mapped[str | None]
    failure_reason: Mapped[str | None]
