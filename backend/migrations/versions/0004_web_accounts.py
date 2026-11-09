"""Accounts made in the web app: an email and a password, or Google through Firebase.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08

Written by hand. A user now logs in with a code sent to a phone (the app), a password, Google,
or more than one of them, and a CHECK makes sure there is at least one. Emails are stored in
lower case, so one address is one account. Links to set a new password are kept only as hashes.

Going back down needs every account to have a phone again, so it fails while any account made
in the web app exists: delete those first.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_CHECKS = {
    "password_failures_not_negative": "password_failures >= 0",
    "has_a_login": "phone IS NOT NULL OR password_hash IS NOT NULL OR firebase_uid IS NOT NULL",
    "password_needs_email": "password_hash IS NULL OR email IS NOT NULL",
    "email_lower_case": "email = lower(email)",
}


def upgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.Text(), nullable=True)
    op.add_column("users", sa.Column("email", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("password_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "users", sa.Column("password_locked_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("firebase_uid", sa.Text(), nullable=True))
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])
    op.create_unique_constraint(op.f("uq_users_firebase_uid"), "users", ["firebase_uid"])
    for name, condition in USER_CHECKS.items():
        op.create_check_constraint(op.f(f"ck_users_{name}"), "users", condition)

    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_resets")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_resets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_resets_token_hash")),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_password_resets_token_hash_length")
        ),
    )
    op.create_index(op.f("ix_password_resets_user_id"), "password_resets", ["user_id"])


def downgrade() -> None:
    # First, so it fails before anything changes while accounts without a phone exist.
    op.alter_column("users", "phone", existing_type=sa.Text(), nullable=False)
    op.drop_index(op.f("ix_password_resets_user_id"), table_name="password_resets")
    op.drop_table("password_resets")
    for name in USER_CHECKS:
        op.drop_constraint(op.f(f"ck_users_{name}"), "users", type_="check")
    op.drop_constraint(op.f("uq_users_firebase_uid"), "users", type_="unique")
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    for column in ("firebase_uid", "password_locked_until", "password_failures", "password_hash"):
        op.drop_column("users", column)
    op.drop_column("users", "email")
