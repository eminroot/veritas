"""The chain outbox and events, money in, decisions and money out, and the mocks' tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08

Generated from the models, then reviewed by hand: PostGIS's own spatial_ref_sys table is
left alone, and the CHECKs on the new milestone columns, which autogenerate does not emit,
are added explicitly. tests/db check that the models and the migrations agree.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name=op.f("ck_alerts_severity")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_alerts_dedupe_key")),
    )
    op.create_index(op.f("ix_alerts_kind"), "alerts", ["kind"], unique=False)
    op.create_table(
        "chain_cursor",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_chain_cursor")),
    )
    op.create_table(
        "mock_bank_attestations",
        sa.Column("day", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("cutoff_block", sa.BigInteger(), nullable=False),
        sa.Column("cutoff_time", sa.BigInteger(), nullable=False),
        sa.Column("balance_qapik", sa.BigInteger(), nullable=False),
        sa.Column("statement", sa.LargeBinary(), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_mock_bank_attestations")),
    )
    op.create_table(
        "mock_bank_batches",
        sa.Column("batch_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("root", sa.LargeBinary(), nullable=False),
        sa.Column("total_qapik", sa.BigInteger(), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("batch_id", name=op.f("pk_mock_bank_batches")),
    )
    op.create_table(
        "mock_bank_payments",
        sa.Column("instruction_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("counterparty", sa.Text(), nullable=False),
        sa.Column("payment_ref", sa.LargeBinary(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('payout', 'refund')", name=op.f("ck_mock_bank_payments_kind")),
        sa.CheckConstraint(
            "status IN ('paid', 'failed')", name=op.f("ck_mock_bank_payments_status")
        ),
        sa.PrimaryKeyConstraint("instruction_id", name=op.f("pk_mock_bank_payments")),
    )
    op.create_table(
        "mock_bank_receipts",
        sa.Column("payment_id", sa.Text(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("payment_id", name=op.f("pk_mock_bank_receipts")),
    )
    op.create_index(
        op.f("ix_mock_bank_receipts_batch_id"), "mock_bank_receipts", ["batch_id"], unique=False
    )
    op.create_table(
        "mock_psp_cards",
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("customer_ref", sa.Text(), nullable=False),
        sa.Column("last4", sa.Text(), nullable=False),
        sa.Column("expired", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_mock_psp_cards")),
    )
    op.create_table(
        "mock_psp_payments",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), server_default="AZN", nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("card_last4", sa.Text(), nullable=False),
        sa.Column("card_token", sa.Text(), nullable=True),
        sa.Column("merchant_initiated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("refunded_qapik", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name=op.f("ck_mock_psp_payments_status")
        ),
        sa.CheckConstraint("amount_qapik > 0", name=op.f("ck_mock_psp_payments_amount_positive")),
        sa.CheckConstraint(
            "refunded_qapik >= 0 AND refunded_qapik <= amount_qapik",
            name=op.f("ck_mock_psp_payments_refunds"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_psp_payments")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_mock_psp_payments_idempotency_key")),
    )
    op.create_table(
        "mock_psp_refunds",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("payment_id", sa.Text(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name=op.f("ck_mock_psp_refunds_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_psp_refunds")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_mock_psp_refunds_idempotency_key")),
    )
    op.create_table(
        "mock_psp_webhooks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_psp_webhooks")),
    )
    op.create_table(
        "chain_contracts",
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("from_block", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "address ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_chain_contracts_address_format")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_chain_contracts_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("address", name=op.f("pk_chain_contracts")),
    )
    op.create_index(
        op.f("ix_chain_contracts_project_id"), "chain_contracts", ["project_id"], unique=False
    )
    op.create_table(
        "chain_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_hash", sa.LargeBinary(), nullable=False),
        sa.Column("tx_hash", sa.LargeBinary(), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "address ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_chain_events_address_format")
        ),
        sa.CheckConstraint(
            "octet_length(block_hash) = 32", name=op.f("ck_chain_events_block_hash_length")
        ),
        sa.CheckConstraint(
            "octet_length(tx_hash) = 32", name=op.f("ck_chain_events_tx_hash_length")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_chain_events_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chain_events")),
        sa.UniqueConstraint("tx_hash", "log_index", name=op.f("uq_chain_events_tx_hash_log_index")),
    )
    op.create_index(
        op.f("ix_chain_events_block_number"), "chain_events", ["block_number"], unique=False
    )
    op.create_index(
        "ix_chain_events_contract_event", "chain_events", ["contract", "event"], unique=False
    )
    op.create_index(
        op.f("ix_chain_events_project_id"), "chain_events", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_chain_events_tx_hash"), "chain_events", ["tx_hash"], unique=False)
    op.create_table(
        "chain_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("contract", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("function", sa.Text(), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sender", sa.Text(), server_default="relayer", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("depends_on", sa.BigInteger(), nullable=True),
        sa.Column("nonce", sa.BigInteger(), nullable=True),
        sa.Column("gas_limit", sa.BigInteger(), nullable=True),
        sa.Column("max_fee_per_gas", sa.BigInteger(), nullable=True),
        sa.Column("max_priority_fee_per_gas", sa.BigInteger(), nullable=True),
        sa.Column("raw_tx", sa.LargeBinary(), nullable=True),
        sa.Column("tx_hash", sa.LargeBinary(), nullable=True),
        sa.Column(
            "tx_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mined_block", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "address ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_chain_outbox_address_format")
        ),
        sa.CheckConstraint("sender IN ('relayer', 'admin')", name=op.f("ck_chain_outbox_sender")),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'confirmed', 'failed', 'cancelled')",
            name=op.f("ck_chain_outbox_status"),
        ),
        sa.CheckConstraint(
            "octet_length(tx_hash) = 32", name=op.f("ck_chain_outbox_tx_hash_length")
        ),
        sa.ForeignKeyConstraint(
            ["depends_on"],
            ["chain_outbox.id"],
            name=op.f("fk_chain_outbox_depends_on_chain_outbox"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_chain_outbox_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chain_outbox")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_chain_outbox_dedupe_key")),
    )
    op.create_index(
        "ix_chain_outbox_open",
        "chain_outbox",
        ["sender", "id"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'sending', 'sent')"),
    )
    op.create_index(
        op.f("ix_chain_outbox_project_id"), "chain_outbox", ["project_id"], unique=False
    )
    op.create_table(
        "pledges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("card_token", sa.Text(), nullable=False),
        sa.Column("card_last4", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("holder ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_pledges_holder_format")),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'cancelled')", name=op.f("ck_pledges_status")
        ),
        sa.CheckConstraint("amount_qapik > 0", name=op.f("ck_pledges_amount_positive")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_pledges_project_id_projects")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_pledges_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pledges")),
    )
    op.create_index(op.f("ix_pledges_project_id"), "pledges", ["project_id"], unique=False)
    op.create_index(op.f("ix_pledges_user_id"), "pledges", ["user_id"], unique=False)
    op.create_table(
        "ballots",
        sa.Column("id", sa.LargeBinary(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("eligible", sa.Integer(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("yes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("no", sa.Integer(), server_default="0", nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("turnout_fallback", sa.Boolean(), nullable=True),
        sa.Column("close_outbox_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('milestone', 'amendment', 'stop')", name=op.f("ck_ballots_kind")
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_ballots_status")),
        sa.CheckConstraint("octet_length(id) = 32", name=op.f("ck_ballots_id_length")),
        sa.ForeignKeyConstraint(
            ["close_outbox_id"],
            ["chain_outbox.id"],
            name=op.f("fk_ballots_close_outbox_id_chain_outbox"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_ballots_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ballots")),
    )
    op.create_index(op.f("ix_ballots_project_id"), "ballots", ["project_id"], unique=False)
    op.create_table(
        "batches",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("root", sa.LargeBinary(), nullable=False),
        sa.Column("leaf_count", sa.Integer(), nullable=False),
        sa.Column("total_qapik", sa.BigInteger(), nullable=False),
        sa.Column("credits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("credits_hash", sa.LargeBinary(), nullable=False),
        sa.Column("tree", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mode", sa.Text(), server_default="bank", nullable=False),
        sa.Column("bank_signature", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.Text(), server_default="built", nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column("anchored_block", sa.BigInteger(), nullable=True),
        sa.Column("anchored_tx", sa.LargeBinary(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("mode IN ('bank', 'provider')", name=op.f("ck_batches_mode")),
        sa.CheckConstraint(
            "status IN ('built', 'anchored', 'settled', 'failed')", name=op.f("ck_batches_status")
        ),
        sa.CheckConstraint("id > 0", name=op.f("ck_batches_id_positive")),
        sa.CheckConstraint("leaf_count > 0", name=op.f("ck_batches_leaf_count_positive")),
        sa.CheckConstraint(
            "octet_length(credits_hash) = 32", name=op.f("ck_batches_credits_hash_length")
        ),
        sa.CheckConstraint("octet_length(root) = 32", name=op.f("ck_batches_root_length")),
        sa.ForeignKeyConstraint(
            ["outbox_id"], ["chain_outbox.id"], name=op.f("fk_batches_outbox_id_chain_outbox")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batches")),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_project_id", sa.Uuid(), nullable=True),
        sa.Column("by_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("nonce", sa.Integer(), nullable=True),
        sa.Column("deadline", sa.BigInteger(), nullable=True),
        sa.Column("signature", sa.LargeBinary(), nullable=True),
        sa.Column("allocation_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("claim_id", sa.LargeBinary(), nullable=True),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), server_default="submitted", nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("action IN ('refund', 'redirect')", name=op.f("ck_claims_action")),
        sa.CheckConstraint("holder ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_claims_holder_format")),
        sa.CheckConstraint(
            "status IN ('submitted', 'executed', 'failed')", name=op.f("ck_claims_status")
        ),
        sa.CheckConstraint("octet_length(claim_id) = 32", name=op.f("ck_claims_claim_id_length")),
        sa.ForeignKeyConstraint(
            ["outbox_id"], ["chain_outbox.id"], name=op.f("fk_claims_outbox_id_chain_outbox")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_claims_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["target_project_id"],
            ["projects.id"],
            name=op.f("fk_claims_target_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_claims_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claims")),
    )
    op.create_index(op.f("ix_claims_project_id"), "claims", ["project_id"], unique=False)
    op.create_table(
        "officer_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("approve", sa.Boolean(), nullable=False),
        sa.Column("invoice_hash", sa.LargeBinary(), nullable=True),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=True),
        sa.Column("override_checks", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reason_hash", sa.LargeBinary(), nullable=True),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("officer_id", sa.Uuid(), nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT override_checks OR reason IS NOT NULL",
            name=op.f("ck_officer_decisions_override_has_reason"),
        ),
        sa.CheckConstraint(
            "approve OR reason IS NOT NULL", name=op.f("ck_officer_decisions_rejection_has_reason")
        ),
        sa.CheckConstraint(
            "octet_length(invoice_hash) = 32", name=op.f("ck_officer_decisions_invoice_hash_length")
        ),
        sa.CheckConstraint(
            "octet_length(reason_hash) = 32", name=op.f("ck_officer_decisions_reason_hash_length")
        ),
        sa.ForeignKeyConstraint(
            ["officer_id"], ["officers.id"], name=op.f("fk_officer_decisions_officer_id_officers")
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"],
            ["chain_outbox.id"],
            name=op.f("fk_officer_decisions_outbox_id_chain_outbox"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_officer_decisions_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_officer_decisions")),
    )
    op.create_index(
        op.f("ix_officer_decisions_project_id"), "officer_decisions", ["project_id"], unique=False
    )
    # One decision per attempt; a decision the chain refused does not count.
    op.create_index(
        "uq_officer_decisions_one_per_attempt",
        "officer_decisions",
        ["project_id", "milestone_index", "attempt"],
        unique=True,
        postgresql_where=sa.text("failed_at IS NULL"),
    )
    op.create_table(
        "payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instruction_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=True),
        sa.Column("holder", sa.Text(), nullable=True),
        sa.Column("claim_id", sa.LargeBinary(), nullable=True),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="instructed", nullable=False),
        sa.Column("payment_ref", sa.LargeBinary(), nullable=True),
        sa.Column("bank_signature", sa.LargeBinary(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("octet_length(claim_id) = 32", name=op.f("ck_payouts_claim_id_length")),
        sa.CheckConstraint("kind IN ('payout', 'refund')", name=op.f("ck_payouts_kind")),
        sa.CheckConstraint(
            "status IN ('instructed', 'bank_paid', 'bank_failed', 'confirmed', 'returned')",
            name=op.f("ck_payouts_status"),
        ),
        sa.CheckConstraint(
            "octet_length(payment_ref) = 32", name=op.f("ck_payouts_payment_ref_length")
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"], ["chain_outbox.id"], name=op.f("fk_payouts_outbox_id_chain_outbox")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_payouts_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payouts")),
        sa.UniqueConstraint("instruction_id", name=op.f("uq_payouts_instruction_id")),
    )
    op.create_index(op.f("ix_payouts_project_id"), "payouts", ["project_id"], unique=False)
    op.create_table(
        "pledge_charges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pledge_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=False),
        sa.Column("approval_round", sa.Integer(), nullable=False),
        sa.Column("approval_tx", sa.LargeBinary(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'skipped')",
            name=op.f("ck_pledge_charges_status"),
        ),
        sa.CheckConstraint(
            "octet_length(approval_tx) = 32", name=op.f("ck_pledge_charges_approval_tx_length")
        ),
        sa.ForeignKeyConstraint(
            ["pledge_id"], ["pledges.id"], name=op.f("fk_pledge_charges_pledge_id_pledges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pledge_charges")),
        sa.UniqueConstraint(
            "pledge_id",
            "milestone_index",
            "approval_round",
            name=op.f("uq_pledge_charges_pledge_id_milestone_index_approval_round"),
        ),
    )
    op.create_index(
        op.f("ix_pledge_charges_pledge_id"), "pledge_charges", ["pledge_id"], unique=False
    )
    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("controller", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "controller ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_receipts_controller_format")
        ),
        sa.CheckConstraint(
            "holder ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_receipts_holder_format")
        ),
        sa.CheckConstraint("status IN ('pending', 'minted')", name=op.f("ck_receipts_status")),
        sa.ForeignKeyConstraint(
            ["outbox_id"], ["chain_outbox.id"], name=op.f("fk_receipts_outbox_id_chain_outbox")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_receipts_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
        sa.UniqueConstraint("project_id", "holder", name=op.f("uq_receipts_project_id_holder")),
        sa.UniqueConstraint("token_id", name=op.f("uq_receipts_token_id")),
    )
    op.create_index(op.f("ix_receipts_project_id"), "receipts", ["project_id"], unique=False)
    op.create_table(
        "reconciliations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.BigInteger(), nullable=False),
        sa.Column("cutoff_block", sa.BigInteger(), nullable=False),
        sa.Column("cutoff_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chain_supply_qapik", sa.BigInteger(), nullable=False),
        sa.Column("ledger_qapik", sa.BigInteger(), nullable=False),
        sa.Column("bank_balance_qapik", sa.BigInteger(), nullable=False),
        sa.Column("balanced", sa.Boolean(), nullable=False),
        sa.Column("statement", sa.LargeBinary(), nullable=False),
        sa.Column("statement_hash", sa.LargeBinary(), nullable=False),
        sa.Column("bank_signature", sa.LargeBinary(), nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "octet_length(statement_hash) = 32",
            name=op.f("ck_reconciliations_statement_hash_length"),
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"],
            ["chain_outbox.id"],
            name=op.f("fk_reconciliations_outbox_id_chain_outbox"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliations")),
        sa.UniqueConstraint("day", name=op.f("uq_reconciliations_day")),
    )
    op.create_table(
        "releases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("invoice_hash", sa.LargeBinary(), nullable=False),
        sa.Column("instruction_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), server_default="requested", nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'instructed', 'paid', 'returned')",
            name=op.f("ck_releases_status"),
        ),
        sa.CheckConstraint(
            "octet_length(invoice_hash) = 32", name=op.f("ck_releases_invoice_hash_length")
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"], ["chain_outbox.id"], name=op.f("fk_releases_outbox_id_chain_outbox")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_releases_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_releases")),
        sa.UniqueConstraint("instruction_id", name=op.f("uq_releases_instruction_id")),
    )
    op.create_index(op.f("ix_releases_project_id"), "releases", ["project_id"], unique=False)
    op.create_table(
        "donations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), server_default="card", nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=False),
        sa.Column("card_last4", sa.Text(), nullable=True),
        sa.Column("trigger", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.Text(), server_default="received", nullable=False),
        sa.Column("refunded_qapik", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("pledge_charge_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "holder ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_donations_holder_format")
        ),
        sa.CheckConstraint(
            "kind IN ('card', 'pay_on_proof', 'redirect')", name=op.f("ck_donations_kind")
        ),
        sa.CheckConstraint(
            "status IN ('received', 'batched', 'in_escrow', 'refunded')",
            name=op.f("ck_donations_status"),
        ),
        sa.CheckConstraint("amount_qapik > 0", name=op.f("ck_donations_amount_positive")),
        sa.CheckConstraint("octet_length(trigger) = 32", name=op.f("ck_donations_trigger_length")),
        sa.CheckConstraint(
            "refunded_qapik >= 0 AND refunded_qapik <= amount_qapik",
            name=op.f("ck_donations_refund_in_range"),
        ),
        sa.ForeignKeyConstraint(
            ["pledge_charge_id"],
            ["pledge_charges.id"],
            name=op.f("fk_donations_pledge_charge_id_pledge_charges"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_donations_project_id_projects")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_donations_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_donations")),
        sa.UniqueConstraint(
            "provider",
            "provider_payment_id",
            name=op.f("uq_donations_provider_provider_payment_id"),
        ),
    )
    op.create_index(op.f("ix_donations_project_id"), "donations", ["project_id"], unique=False)
    op.create_index(op.f("ix_donations_user_id"), "donations", ["user_id"], unique=False)
    op.create_table(
        "votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ballot_id", sa.LargeBinary(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("approve", sa.Boolean(), nullable=False),
        sa.Column("weight_qapik", sa.BigInteger(), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.Text(), server_default="submitted", nullable=False),
        sa.Column("outbox_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("holder ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_votes_holder_format")),
        sa.CheckConstraint(
            "status IN ('submitted', 'counted', 'failed')", name=op.f("ck_votes_status")
        ),
        sa.ForeignKeyConstraint(
            ["ballot_id"], ["ballots.id"], name=op.f("fk_votes_ballot_id_ballots")
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"], ["chain_outbox.id"], name=op.f("fk_votes_outbox_id_chain_outbox")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_votes")),
    )
    op.create_index(op.f("ix_votes_ballot_id"), "votes", ["ballot_id"], unique=False)
    # One vote per holder and ballot; a vote the chain refused does not count, so the
    # donor can sign again.
    op.create_index(
        "uq_votes_one_per_holder",
        "votes",
        ["ballot_id", "holder"],
        unique=True,
        postgresql_where=sa.text("status <> 'failed'"),
    )
    op.create_table(
        "allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("donation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("trigger", sa.LargeBinary(), nullable=False),
        sa.Column("leaf_hash", sa.LargeBinary(), nullable=False),
        sa.Column("credited", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), server_default="received", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "holder ~ '^0x[0-9a-fA-F]{40}$'", name=op.f("ck_allocations_holder_format")
        ),
        sa.CheckConstraint(
            "status IN ('received', 'batched', 'in_escrow', 'claimed', 'void')",
            name=op.f("ck_allocations_status"),
        ),
        sa.CheckConstraint("amount_qapik > 0", name=op.f("ck_allocations_amount_positive")),
        sa.CheckConstraint(
            "octet_length(leaf_hash) = 32", name=op.f("ck_allocations_leaf_hash_length")
        ),
        sa.CheckConstraint("octet_length(salt) = 32", name=op.f("ck_allocations_salt_length")),
        sa.CheckConstraint(
            "octet_length(trigger) = 32", name=op.f("ck_allocations_trigger_length")
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["batches.id"], name=op.f("fk_allocations_batch_id_batches")
        ),
        sa.ForeignKeyConstraint(
            ["donation_id"], ["donations.id"], name=op.f("fk_allocations_donation_id_donations")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_allocations_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allocations")),
        sa.UniqueConstraint(
            "donation_id",
            "milestone_index",
            name=op.f("uq_allocations_donation_id_milestone_index"),
        ),
        sa.UniqueConstraint("leaf_hash", name=op.f("uq_allocations_leaf_hash")),
    )
    op.create_index(op.f("ix_allocations_batch_id"), "allocations", ["batch_id"], unique=False)
    op.create_index(
        op.f("ix_allocations_donation_id"), "allocations", ["donation_id"], unique=False
    )
    op.create_index(op.f("ix_allocations_project_id"), "allocations", ["project_id"], unique=False)
    op.create_table(
        "batch_leaves",
        sa.Column("allocation_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("tree_index", sa.Integer(), nullable=False),
        sa.Column("proof", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["allocation_id"],
            ["allocations.id"],
            name=op.f("fk_batch_leaves_allocation_id_allocations"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["batches.id"], name=op.f("fk_batch_leaves_batch_id_batches")
        ),
        sa.PrimaryKeyConstraint("allocation_id", name=op.f("pk_batch_leaves")),
    )
    op.create_index(op.f("ix_batch_leaves_batch_id"), "batch_leaves", ["batch_id"], unique=False)
    op.add_column(
        "milestones", sa.Column("funded_qapik", sa.BigInteger(), server_default="0", nullable=False)
    )
    op.add_column(
        "milestones", sa.Column("attempt", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("milestones", sa.Column("bundle_hash", sa.LargeBinary(), nullable=True))
    op.add_column("milestones", sa.Column("evidence_cid", sa.Text(), nullable=True))
    op.add_column("milestones", sa.Column("report_hash", sa.LargeBinary(), nullable=True))
    op.add_column("milestones", sa.Column("checks_passed", sa.Boolean(), nullable=True))
    op.add_column("milestones", sa.Column("invoice_hash", sa.LargeBinary(), nullable=True))
    op.add_column("milestones", sa.Column("approved_qapik", sa.BigInteger(), nullable=True))
    op.add_column(
        "milestones", sa.Column("resubmit_deadline", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_milestones_funded_range"),
        "milestones",
        "funded_qapik >= 0 AND funded_qapik <= amount_qapik",
    )
    for column in ("bundle_hash", "report_hash", "invoice_hash"):
        op.create_check_constraint(
            op.f(f"ck_milestones_{column}_length"), "milestones", f"octet_length({column}) = 32"
        )


def downgrade() -> None:
    for column in ("bundle_hash", "report_hash", "invoice_hash"):
        op.drop_constraint(op.f(f"ck_milestones_{column}_length"), "milestones", type_="check")
    op.drop_constraint(op.f("ck_milestones_funded_range"), "milestones", type_="check")
    op.drop_column("milestones", "resubmit_deadline")
    op.drop_column("milestones", "approved_qapik")
    op.drop_column("milestones", "invoice_hash")
    op.drop_column("milestones", "checks_passed")
    op.drop_column("milestones", "report_hash")
    op.drop_column("milestones", "evidence_cid")
    op.drop_column("milestones", "bundle_hash")
    op.drop_column("milestones", "attempt")
    op.drop_column("milestones", "funded_qapik")
    op.drop_index(op.f("ix_batch_leaves_batch_id"), table_name="batch_leaves")
    op.drop_table("batch_leaves")
    op.drop_index(op.f("ix_allocations_project_id"), table_name="allocations")
    op.drop_index(op.f("ix_allocations_donation_id"), table_name="allocations")
    op.drop_index(op.f("ix_allocations_batch_id"), table_name="allocations")
    op.drop_table("allocations")
    op.drop_index("uq_votes_one_per_holder", table_name="votes")
    op.drop_index(op.f("ix_votes_ballot_id"), table_name="votes")
    op.drop_table("votes")
    op.drop_index(op.f("ix_donations_user_id"), table_name="donations")
    op.drop_index(op.f("ix_donations_project_id"), table_name="donations")
    op.drop_table("donations")
    op.drop_index(op.f("ix_releases_project_id"), table_name="releases")
    op.drop_table("releases")
    op.drop_table("reconciliations")
    op.drop_index(op.f("ix_receipts_project_id"), table_name="receipts")
    op.drop_table("receipts")
    op.drop_index(op.f("ix_pledge_charges_pledge_id"), table_name="pledge_charges")
    op.drop_table("pledge_charges")
    op.drop_index(op.f("ix_payouts_project_id"), table_name="payouts")
    op.drop_table("payouts")
    op.drop_index("uq_officer_decisions_one_per_attempt", table_name="officer_decisions")
    op.drop_index(op.f("ix_officer_decisions_project_id"), table_name="officer_decisions")
    op.drop_table("officer_decisions")
    op.drop_index(op.f("ix_claims_project_id"), table_name="claims")
    op.drop_table("claims")
    op.drop_table("batches")
    op.drop_index(op.f("ix_ballots_project_id"), table_name="ballots")
    op.drop_table("ballots")
    op.drop_index(op.f("ix_pledges_user_id"), table_name="pledges")
    op.drop_index(op.f("ix_pledges_project_id"), table_name="pledges")
    op.drop_table("pledges")
    op.drop_index(op.f("ix_chain_outbox_project_id"), table_name="chain_outbox")
    op.drop_index(
        "ix_chain_outbox_open",
        table_name="chain_outbox",
        postgresql_where=sa.text("status IN ('pending', 'sending', 'sent')"),
    )
    op.drop_table("chain_outbox")
    op.drop_index(op.f("ix_chain_events_tx_hash"), table_name="chain_events")
    op.drop_index(op.f("ix_chain_events_project_id"), table_name="chain_events")
    op.drop_index("ix_chain_events_contract_event", table_name="chain_events")
    op.drop_index(op.f("ix_chain_events_block_number"), table_name="chain_events")
    op.drop_table("chain_events")
    op.drop_index(op.f("ix_chain_contracts_project_id"), table_name="chain_contracts")
    op.drop_table("chain_contracts")
    op.drop_table("mock_psp_webhooks")
    op.drop_table("mock_psp_refunds")
    op.drop_table("mock_psp_payments")
    op.drop_table("mock_psp_cards")
    op.drop_index(op.f("ix_mock_bank_receipts_batch_id"), table_name="mock_bank_receipts")
    op.drop_table("mock_bank_receipts")
    op.drop_table("mock_bank_payments")
    op.drop_table("mock_bank_batches")
    op.drop_table("mock_bank_attestations")
    op.drop_table("chain_cursor")
    op.drop_index(op.f("ix_alerts_kind"), table_name="alerts")
    op.drop_table("alerts")
