"""Tables for the stand-in card provider and partner bank.

They live in the same database for convenience, under a `mock_` prefix, and nothing in
Veritas reads them: Veritas only talks to the mocks over HTTP, exactly as it will talk to the
real provider and bank.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from veritas.db.base import Base, CreatedAt, Qapik, one_of


class MockCard(CreatedAt, Base):
    __tablename__ = "mock_psp_cards"

    token: Mapped[str] = mapped_column(primary_key=True)
    customer_ref: Mapped[str]
    last4: Mapped[str]
    expired: Mapped[bool] = mapped_column(default=False, server_default="false")


class MockPayment(CreatedAt, Base):
    __tablename__ = "mock_psp_payments"
    __table_args__ = (
        one_of("status", ("succeeded", "failed")),
        CheckConstraint("amount_qapik > 0", name="amount_positive"),
        CheckConstraint("refunded_qapik >= 0 AND refunded_qapik <= amount_qapik", name="refunds"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    amount_qapik: Mapped[Qapik]
    currency: Mapped[str] = mapped_column(default="AZN", server_default="AZN")
    status: Mapped[str]
    failure_reason: Mapped[str | None]
    card_last4: Mapped[str]
    card_token: Mapped[str | None]
    """Set when the card was saved, or for a merchant-initiated charge on a saved card."""
    merchant_initiated: Mapped[bool] = mapped_column(default=False, server_default="false")
    idempotency_key: Mapped[str | None] = mapped_column(unique=True)
    payment_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    refunded_qapik: Mapped[Qapik] = mapped_column(default=0, server_default="0")


class MockRefund(CreatedAt, Base):
    __tablename__ = "mock_psp_refunds"
    __table_args__ = (one_of("status", ("succeeded", "failed")),)

    id: Mapped[str] = mapped_column(primary_key=True)
    payment_id: Mapped[str]
    amount_qapik: Mapped[Qapik]
    status: Mapped[str]
    failure_reason: Mapped[str | None]
    idempotency_key: Mapped[str] = mapped_column(unique=True)


class MockWebhook(CreatedAt, Base):
    """Webhooks waiting to be delivered to Veritas, in order."""

    __tablename__ = "mock_psp_webhooks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str]
    body: Mapped[bytes]
    delivered_at: Mapped[datetime | None]
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")


class MockBankReceipt(CreatedAt, Base):
    """A card payment that reached the escrow account. Pending until a batch attests it."""

    __tablename__ = "mock_bank_receipts"

    payment_id: Mapped[str] = mapped_column(primary_key=True)
    amount_qapik: Mapped[Qapik]
    batch_id: Mapped[int | None] = mapped_column(BigInteger, index=True)


class MockBankBatch(CreatedAt, Base):
    __tablename__ = "mock_bank_batches"

    batch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    root: Mapped[bytes]
    total_qapik: Mapped[Qapik]
    signature: Mapped[bytes]


class MockBankPayment(CreatedAt, Base):
    """Money that left the escrow account: a contractor payout or a refund to a card."""

    __tablename__ = "mock_bank_payments"
    __table_args__ = (
        one_of("kind", ("payout", "refund")),
        one_of("status", ("paid", "failed")),
    )

    instruction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    kind: Mapped[str]
    amount_qapik: Mapped[Qapik]
    status: Mapped[str]
    counterparty: Mapped[str]
    """The contractor's IBAN, or the provider's refund ids for a refund."""
    payment_ref: Mapped[bytes]
    reason: Mapped[str | None]
    signature: Mapped[bytes]


class MockBankAttestation(CreatedAt, Base):
    __tablename__ = "mock_bank_attestations"

    day: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    cutoff_block: Mapped[int] = mapped_column(BigInteger)
    cutoff_time: Mapped[int] = mapped_column(BigInteger)
    balance_qapik: Mapped[Qapik]
    statement: Mapped[bytes]
    """The canonical JSON statement whose SHA-256 the bank signed."""
    signature: Mapped[bytes]
