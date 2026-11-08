"""The chain outbox, the indexed events and the alerts they raise.

Application code never calls the chain. It writes a `chain_outbox` row in the same transaction
as the change that needs it, so the transaction and the chain write either both happen or
neither does. The relayer sends the rows in order. The indexer copies events from finalised
blocks into `chain_events` and moves records forward from them, so what the database says
always comes from what the chain says.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from veritas.db.base import (
    Base,
    CreatedAt,
    Timestamps,
    UUIDPrimaryKey,
    byte_length,
    evm_address,
    one_of,
)


class OutboxStatus(StrEnum):
    PENDING = "pending"
    """Waiting its turn."""
    SENDING = "sending"
    """Signed and recorded, being broadcast. A restart re-broadcasts the same bytes."""
    SENT = "sent"
    """In the mempool or mined, not final yet."""
    CONFIRMED = "confirmed"
    """Mined in a finalised block and succeeded."""
    FAILED = "failed"
    """Reverted, or would revert. Needs a person; never retried automatically."""
    CANCELLED = "cancelled"


class Sender(StrEnum):
    RELAYER = "relayer"
    ADMIN = "admin"
    """Only on Anvil and in the demo. In production admin calls go through the Safe."""


class ChainOutbox(Timestamps, Base):
    __tablename__ = "chain_outbox"
    __table_args__ = (
        one_of("status", OutboxStatus),
        one_of("sender", Sender),
        evm_address("address"),
        byte_length("tx_hash", 32),
        Index(
            "ix_chain_outbox_open",
            "sender",
            "id",
            postgresql_where=text("status IN ('pending', 'sending', 'sent')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    """Rows go out in id order, per sender."""
    kind: Mapped[str]
    """What the business change was, like "launch_project". Tells the indexer what to expect."""
    dedupe_key: Mapped[str] = mapped_column(unique=True)
    """Writing the same chain call twice returns the first row."""
    contract: Mapped[str]
    """Artifact name. System contracts are found in the deployment by this name."""
    address: Mapped[str | None]
    """Set for calls to an escrow clone."""
    function: Mapped[str]
    args: Mapped[list[Any]] = mapped_column(JSONB)
    sender: Mapped[str] = mapped_column(default=Sender.RELAYER, server_default="relayer")
    status: Mapped[str] = mapped_column(default=OutboxStatus.PENDING, server_default="pending")
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    depends_on: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))
    """A call from another sender that must be confirmed first, like the admin registering
    the charity before its project launches. Calls from one sender already go in order."""

    nonce: Mapped[int | None] = mapped_column(BigInteger)
    gas_limit: Mapped[int | None] = mapped_column(BigInteger)
    max_fee_per_gas: Mapped[int | None] = mapped_column(BigInteger)
    max_priority_fee_per_gas: Mapped[int | None] = mapped_column(BigInteger)
    raw_tx: Mapped[bytes | None]
    tx_hash: Mapped[bytes | None]
    """The latest broadcast. Every one of them is in `tx_hashes`; any of them may be mined."""
    tx_hashes: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    sent_at: Mapped[datetime | None]
    mined_block: Mapped[int | None] = mapped_column(BigInteger)
    confirmed_at: Mapped[datetime | None]
    events_checked_at: Mapped[datetime | None]
    """When the indexer checked that the transaction emitted the event its kind promises."""
    last_error: Mapped[str | None]


class ChainContract(CreatedAt, Base):
    """Every address the indexer reads: the system contracts and each project's escrow."""

    __tablename__ = "chain_contracts"
    __table_args__ = (evm_address("address"),)

    address: Mapped[str] = mapped_column(primary_key=True)
    contract: Mapped[str]
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    from_block: Mapped[int] = mapped_column(BigInteger)


class ChainCursor(Timestamps, Base):
    """How far the indexer has read. One row per indexer."""

    __tablename__ = "chain_cursor"

    name: Mapped[str] = mapped_column(primary_key=True)
    block_number: Mapped[int] = mapped_column(BigInteger)


class ChainEvent(CreatedAt, Base):
    __tablename__ = "chain_events"
    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index"),
        byte_length("tx_hash", 32),
        byte_length("block_hash", 32),
        evm_address("address"),
        Index("ix_chain_events_contract_event", "contract", "event"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    block_number: Mapped[int] = mapped_column(BigInteger, index=True)
    block_hash: Mapped[bytes]
    tx_hash: Mapped[bytes] = mapped_column(index=True)
    log_index: Mapped[int]
    address: Mapped[str]
    contract: Mapped[str]
    event: Mapped[str]
    args: Mapped[dict[str, Any]] = mapped_column(JSONB)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Alert(UUIDPrimaryKey, CreatedAt, Base):
    """Something a person has to look at: a mismatch between the chain and the database, a
    transaction that failed or got stuck, a reconciliation that did not balance."""

    __tablename__ = "alerts"
    __table_args__ = (one_of("severity", AlertSeverity),)

    severity: Mapped[str]
    kind: Mapped[str] = mapped_column(index=True)
    message: Mapped[str]
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    dedupe_key: Mapped[str | None] = mapped_column(unique=True)
    """The same problem seen again does not raise a second alert."""
    resolved_at: Mapped[datetime | None]
