"""People and projects: accounts, charities, contractors, officers and Passports.

Revision ID: 0001
Revises:
Create Date: 2026-11-08

Written by hand. Constraint names follow the naming convention in
veritas/db/base.py, and tests/db check that the models and this file agree.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHONE = r"'^\+994[1-9][0-9]{8}$'"
ADDRESS = "'^0x[0-9a-fA-F]{40}$'"
VOEN = "'^[0-9]{10}$'"

# A published Passport is a promise to donors: its bytes, hash and CID never
# change and the row is never deleted. Drafts and the status column stay
# editable, and the charity signature can be added later (Phase 4).
KEEP_PUBLISHED_PASSPORTS = """
CREATE FUNCTION passports_keep_published() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.canonical_bytes IS NULL THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'passport % version % is published and cannot be deleted',
            OLD.project_id, OLD.version
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.canonical_bytes IS DISTINCT FROM OLD.canonical_bytes
        OR NEW.sha256 IS DISTINCT FROM OLD.sha256
        OR NEW.cid IS DISTINCT FROM OLD.cid
        OR NEW.version IS DISTINCT FROM OLD.version
        OR NEW.project_id IS DISTINCT FROM OLD.project_id
        OR NEW.published_at IS DISTINCT FROM OLD.published_at
    THEN
        RAISE EXCEPTION 'passport % version % is published and cannot be changed',
            OLD.project_id, OLD.version
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER passports_keep_published
    BEFORE UPDATE OR DELETE ON passports
    FOR EACH ROW EXECUTE FUNCTION passports_keep_published();
"""


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), nullable=False)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _check(table: str, name: str, condition: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def _one_of(table: str, column: str, values: Sequence[str]) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return _check(table, column, f"{column} IN ({listed})")


def _fk(table: str, column: str, target: str, ondelete: str | None = None) -> sa.Constraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=op.f(f"fk_{table}_{column}_{target}"), ondelete=ondelete
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "users",
        _id(),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("recovery_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("phone", name=op.f("uq_users_phone")),
        _check("users", "phone_format", f"phone ~ {PHONE}"),
        _check("users", "recovery_failures_not_negative", "recovery_failures >= 0"),
    )

    op.create_table(
        "login_codes",
        _id(),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("code_hmac", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_codes")),
        _check("login_codes", "phone_format", f"phone ~ {PHONE}"),
        _check("login_codes", "code_hmac_length", "octet_length(code_hmac) = 32"),
        _check("login_codes", "attempts_not_negative", "attempts >= 0"),
    )
    op.create_index("ix_login_codes_phone_created_at", "login_codes", ["phone", "created_at"])

    op.create_table(
        "devices",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("attestation", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        _fk("devices", "user_id", "users", ondelete="CASCADE"),
        sa.UniqueConstraint("address", name=op.f("uq_devices_address")),
        _check("devices", "address_format", f"address ~ {ADDRESS}"),
        _one_of("devices", "platform", ["ios", "android", "web"]),
    )
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"])

    op.create_table(
        "sessions",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        _fk("sessions", "user_id", "users", ondelete="CASCADE"),
        _fk("sessions", "device_id", "devices", ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
        _check("sessions", "token_hash_length", "octet_length(token_hash) = 32"),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_index(op.f("ix_sessions_device_id"), "sessions", ["device_id"])

    op.create_table(
        "charities",
        _id(),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("voen", sa.Text(), nullable=False),
        sa.Column("legal_form", sa.Text(), nullable=False),
        sa.Column("legal_address", sa.Text(), nullable=False),
        sa.Column("director_name", sa.Text(), nullable=False),
        sa.Column("contact_email", sa.Text(), nullable=False),
        sa.Column("contact_phone", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("signer_address", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_charities")),
        _fk("charities", "verified_by", "users"),
        _fk("charities", "created_by", "users"),
        sa.UniqueConstraint("voen", name=op.f("uq_charities_voen")),
        sa.UniqueConstraint("signer_address", name=op.f("uq_charities_signer_address")),
        _one_of("charities", "status", ["draft", "submitted", "verified", "rejected", "suspended"]),
        _check("charities", "voen_format", f"voen ~ {VOEN}"),
        _check("charities", "contact_phone_format", f"contact_phone ~ {PHONE}"),
        _check("charities", "signer_address_format", f"signer_address ~ {ADDRESS}"),
    )

    op.create_table(
        "charity_members",
        _id(),
        sa.Column("charity_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_charity_members")),
        _fk("charity_members", "charity_id", "charities", ondelete="CASCADE"),
        _fk("charity_members", "user_id", "users", ondelete="CASCADE"),
        _fk("charity_members", "added_by", "users"),
        sa.UniqueConstraint(
            "charity_id", "user_id", name=op.f("uq_charity_members_charity_id_user_id")
        ),
        _one_of("charity_members", "role", ["admin", "field_worker"]),
    )
    op.create_index(op.f("ix_charity_members_user_id"), "charity_members", ["user_id"])

    op.create_table(
        "device_challenges",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("charity_id", sa.Uuid(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_challenges")),
        _fk("device_challenges", "user_id", "users", ondelete="CASCADE"),
        _fk("device_challenges", "charity_id", "charities", ondelete="CASCADE"),
        sa.UniqueConstraint("nonce", name=op.f("uq_device_challenges_nonce")),
        _one_of("device_challenges", "purpose", ["device", "charity_signer"]),
        _check(
            "device_challenges",
            "charity_only_for_signer",
            "(purpose = 'charity_signer') = (charity_id IS NOT NULL)",
        ),
    )
    op.create_index(op.f("ix_device_challenges_user_id"), "device_challenges", ["user_id"])

    op.create_table(
        "contractors",
        _id(),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("voen", sa.Text(), nullable=False),
        sa.Column("iban", sa.Text(), nullable=False),
        sa.Column("legal_address", sa.Text(), nullable=False),
        sa.Column("director_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="submitted", nullable=False),
        sa.Column("registry_status", sa.Text(), server_default="unchecked", nullable=False),
        sa.Column("registry_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registry_checked_by", sa.Uuid(), nullable=True),
        sa.Column("registry_note", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("charity_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contractors")),
        _fk("contractors", "registry_checked_by", "users"),
        _fk("contractors", "verified_by", "users"),
        _fk("contractors", "charity_id", "charities"),
        _fk("contractors", "created_by", "users"),
        sa.UniqueConstraint("voen", name=op.f("uq_contractors_voen")),
        _one_of("contractors", "status", ["submitted", "verified", "rejected"]),
        _one_of(
            "contractors",
            "registry_status",
            ["unchecked", "active", "inactive", "not_found", "manual_ok"],
        ),
        _check("contractors", "voen_format", f"voen ~ {VOEN}"),
        _check("contractors", "iban_format", "iban ~ '^AZ[0-9]{2}[A-Z]{4}[A-Z0-9]{20}$'"),
    )
    op.create_index(op.f("ix_contractors_charity_id"), "contractors", ["charity_id"])

    op.create_table(
        "kyb_documents",
        _id(),
        sa.Column("owner_type", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kyb_documents")),
        _fk("kyb_documents", "uploaded_by", "users"),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "sha256",
            name=op.f("uq_kyb_documents_owner_type_owner_id_sha256"),
        ),
        _one_of("kyb_documents", "owner_type", ["charity", "contractor"]),
        _one_of(
            "kyb_documents",
            "kind",
            ["registration", "charter", "tax_registration", "director_id", "bank_letter", "other"],
        ),
        _one_of("kyb_documents", "content_type", ["application/pdf", "image/jpeg", "image/png"]),
        _check("kyb_documents", "sha256_length", "octet_length(sha256) = 32"),
        _check("kyb_documents", "size_bytes_positive", "size_bytes > 0"),
    )

    op.create_table(
        "officers",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("organisation", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_officers")),
        _fk("officers", "user_id", "users", ondelete="SET NULL"),
        _fk("officers", "created_by", "users"),
        sa.UniqueConstraint("address", name=op.f("uq_officers_address")),
        sa.UniqueConstraint("user_id", name=op.f("uq_officers_user_id")),
        _one_of("officers", "status", ["active", "inactive"]),
        _check("officers", "address_format", f"address ~ {ADDRESS}"),
    )

    op.create_table(
        "projects",
        _id(),
        sa.Column("charity_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("total_qapik", sa.BigInteger(), nullable=True),
        sa.Column("escrow_address", sa.Text(), nullable=True),
        sa.Column("charity_signer", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        _fk("projects", "charity_id", "charities"),
        _fk("projects", "created_by", "users"),
        _one_of("projects", "status", ["draft", "published", "live", "stopped", "completed"]),
        _one_of(
            "projects",
            "category",
            [
                "education",
                "health",
                "water",
                "housing",
                "environment",
                "community",
                "emergency",
                "other",
            ],
        ),
        _check("projects", "escrow_address_format", f"escrow_address ~ {ADDRESS}"),
        _check("projects", "charity_signer_format", f"charity_signer ~ {ADDRESS}"),
        _check("projects", "total_qapik_positive", "total_qapik > 0"),
    )
    op.create_index(op.f("ix_projects_charity_id"), "projects", ["charity_id"])

    op.create_table(
        "passports",
        _id(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("draft_json", postgresql.JSONB(), nullable=True),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("sha256", sa.LargeBinary(), nullable=True),
        sa.Column("cid", sa.Text(), nullable=True),
        sa.Column("charity_signature", sa.LargeBinary(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passports")),
        _fk("passports", "project_id", "projects", ondelete="CASCADE"),
        _fk("passports", "published_by", "users"),
        _fk("passports", "created_by", "users"),
        sa.UniqueConstraint("project_id", "version", name=op.f("uq_passports_project_id_version")),
        _one_of("passports", "status", ["draft", "published", "superseded"]),
        _check("passports", "version_positive", "version >= 1"),
        _check("passports", "sha256_length", "octet_length(sha256) = 32"),
        _check("passports", "sha256_matches_bytes", "sha256 = sha256(canonical_bytes)"),
        _check("passports", "draft_is_object", "jsonb_typeof(draft_json) = 'object'"),
        _check(
            "passports",
            "draft_or_published",
            "(status = 'draft' AND draft_json IS NOT NULL AND canonical_bytes IS NULL"
            " AND sha256 IS NULL AND cid IS NULL AND published_at IS NULL)"
            " OR (status <> 'draft' AND draft_json IS NULL AND canonical_bytes IS NOT NULL"
            " AND sha256 IS NOT NULL AND cid IS NOT NULL AND published_at IS NOT NULL)",
        ),
    )
    op.create_index(
        "uq_passports_one_draft",
        "passports",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "uq_passports_one_published",
        "passports",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.execute(KEEP_PUBLISHED_PASSPORTS)

    op.create_table(
        "milestones",
        _id(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        sa.Column("window_opens", sa.Date(), nullable=False),
        sa.Column("window_closes", sa.Date(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="funding", nullable=False),
        sa.Column("passport_version", sa.Integer(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
        _fk("milestones", "project_id", "projects", ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "index", name=op.f("uq_milestones_project_id_index")),
        _one_of(
            "milestones",
            "status",
            [
                "funding",
                "evidence_submitted",
                "checked",
                "officer_approved",
                "voting",
                "approved",
                "released",
                "paid",
                "rejected",
                "stopped",
            ],
        ),
        _check("milestones", "index_range", "index >= 0 AND index < 50"),
        _check("milestones", "amount_qapik_positive", "amount_qapik > 0"),
        _check("milestones", "window_in_order", "window_closes >= window_opens"),
        _check("milestones", "times_in_order", "closes_at > opens_at"),
    )

    op.create_table(
        "budget_lines",
        _id(),
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("unit_price_qapik", sa.BigInteger(), nullable=False),
        sa.Column("amount_qapik", sa.BigInteger(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget_lines")),
        _fk("budget_lines", "milestone_id", "milestones", ondelete="CASCADE"),
        sa.UniqueConstraint(
            "milestone_id", "position", name=op.f("uq_budget_lines_milestone_id_position")
        ),
        _check("budget_lines", "position_not_negative", "position >= 0"),
        _check("budget_lines", "quantity_positive", "quantity >= 1"),
        _check("budget_lines", "unit_price_qapik_not_negative", "unit_price_qapik >= 0"),
        _check(
            "budget_lines",
            "amount_is_quantity_times_price",
            "amount_qapik = quantity * unit_price_qapik",
        ),
    )

    op.create_table(
        "sites",
        _id(),
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column(
            "geom",
            Geography(geometry_type="POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sites")),
        _fk("sites", "milestone_id", "milestones", ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_sites_milestone_id"), "sites", ["milestone_id"])
    op.create_index("ix_sites_geom", "sites", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    # PostGIS stays: other objects in the database may use it, and upgrade only
    # creates it when it is missing.
    for table in (
        "sites",
        "budget_lines",
        "milestones",
        "passports",
        "projects",
        "officers",
        "kyb_documents",
        "contractors",
        "device_challenges",
        "charity_members",
        "charities",
        "sessions",
        "devices",
        "login_codes",
        "users",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION passports_keep_published()")
