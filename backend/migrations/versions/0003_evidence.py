"""Evidence: capture sessions, items, photo hashes, bundles, checks and check reports.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08

Written by hand. Constraint names follow the naming convention in veritas/db/base.py, and
tests/db check that the models and the migrations agree. Triggers keep what has been
checked from changing: check results and reports are final once written; a bundle's
manifest, hash and signatures cannot be edited once set, nor its public copy once the
charity has signed; a void or anchored bundle stays so; and a file listed in a submitted
manifest keeps its hash, place, time and storage key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADDRESS = "'^0x[0-9a-fA-F]{40}$'"
PROOF_KINDS = ["photo", "video", "invoice", "fiscal_receipt", "document"]
EVIDENCE_TYPES = ["image/jpeg", "image/png", "video/mp4", "video/quicktime", "application/pdf"]

KEEP_EVIDENCE_FINAL = """
CREATE FUNCTION evidence_keep_final() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% rows are final: a check result or report is never changed or deleted',
        TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE TRIGGER evidence_checks_keep_final
    BEFORE UPDATE OR DELETE ON evidence_checks
    FOR EACH ROW EXECUTE FUNCTION evidence_keep_final();

CREATE TRIGGER check_reports_keep_final
    BEFORE UPDATE OR DELETE ON check_reports
    FOR EACH ROW EXECUTE FUNCTION evidence_keep_final();

CREATE FUNCTION evidence_bundles_keep_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'evidence bundle % cannot be deleted', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.session_id IS DISTINCT FROM OLD.session_id
        OR NEW.project_id IS DISTINCT FROM OLD.project_id
        OR NEW.milestone_index IS DISTINCT FROM OLD.milestone_index
        OR NEW.attempt IS DISTINCT FROM OLD.attempt
        OR NEW.manifest_bytes IS DISTINCT FROM OLD.manifest_bytes
        OR NEW.bundle_hash IS DISTINCT FROM OLD.bundle_hash
        OR NEW.device_address IS DISTINCT FROM OLD.device_address
        OR NEW.device_signature IS DISTINCT FROM OLD.device_signature
        OR NEW.attestation IS DISTINCT FROM OLD.attestation
        OR (OLD.charity_signature IS NOT NULL
            AND (NEW.public_manifest IS DISTINCT FROM OLD.public_manifest
                OR NEW.public_cid IS DISTINCT FROM OLD.public_cid))
        OR (OLD.charity_signature IS NOT NULL
            AND NEW.charity_signature IS DISTINCT FROM OLD.charity_signature)
        OR (OLD.status IN ('anchored', 'void') AND NEW.status IS DISTINCT FROM OLD.status)
    THEN
        RAISE EXCEPTION 'evidence bundle %: the manifest, hashes and signatures are final',
            OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER evidence_bundles_keep_frozen
    BEFORE UPDATE OR DELETE ON evidence_bundles
    FOR EACH ROW EXECUTE FUNCTION evidence_bundles_keep_frozen();

CREATE FUNCTION evidence_items_keep_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.position IS NULL THEN
        -- Not in a submitted manifest: an upload nothing depends on yet.
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'evidence item % is in a submitted manifest and cannot be deleted',
            OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.session_id IS DISTINCT FROM OLD.session_id
        OR NEW.position IS DISTINCT FROM OLD.position
        OR NEW.kind IS DISTINCT FROM OLD.kind
        OR NEW.sha256 IS DISTINCT FROM OLD.sha256
        OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
        OR NEW.content_type IS DISTINCT FROM OLD.content_type
        OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
        OR NEW.captured_at IS DISTINCT FROM OLD.captured_at
        OR NEW.latitude IS DISTINCT FROM OLD.latitude
        OR NEW.longitude IS DISTINCT FROM OLD.longitude
        OR NEW.accuracy_m IS DISTINCT FROM OLD.accuracy_m
        OR NEW.mock_location IS DISTINCT FROM OLD.mock_location
        OR NEW.received_at IS DISTINCT FROM OLD.received_at
        OR (OLD.redacted_key IS NOT NULL AND NEW.redacted_key IS DISTINCT FROM OLD.redacted_key)
        OR (OLD.redacted_cid IS NOT NULL AND NEW.redacted_cid IS DISTINCT FROM OLD.redacted_cid)
        OR (OLD.blurred_regions IS NOT NULL
            AND NEW.blurred_regions IS DISTINCT FROM OLD.blurred_regions)
    THEN
        RAISE EXCEPTION 'evidence item %: a file in a submitted manifest is final', OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER evidence_items_keep_frozen
    BEFORE UPDATE OR DELETE ON evidence_items
    FOR EACH ROW EXECUTE FUNCTION evidence_items_keep_frozen();
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


def _time(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _check(table: str, name: str, condition: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def _one_of(table: str, column: str, values: Sequence[str]) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return _check(table, column, f"{column} IN ({listed})")


def _length(table: str, column: str, size: int) -> sa.CheckConstraint:
    return _check(table, f"{column}_length", f"octet_length({column}) = {size}")


def _fk(
    table: str, column: str, target: str, target_column: str = "id", ondelete: str | None = None
) -> sa.Constraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.{target_column}"],
        name=op.f(f"fk_{table}_{column}_{target}"),
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.create_table(
        "capture_sessions",
        _id(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("device_address", sa.Text(), nullable=False),
        sa.Column("challenge_code", sa.Text(), nullable=False),
        _time("issued_at"),
        _time("expires_at"),
        _time("upload_until"),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        _time("submitted_at", nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capture_sessions")),
        _fk("capture_sessions", "project_id", "projects"),
        _fk("capture_sessions", "created_by", "users"),
        _fk("capture_sessions", "device_address", "devices", "address"),
        sa.UniqueConstraint("challenge_code", name=op.f("uq_capture_sessions_challenge_code")),
        _one_of("capture_sessions", "status", ["open", "submitted", "expired"]),
        _check("capture_sessions", "device_address_format", f"device_address ~ {ADDRESS}"),
        _check(
            "capture_sessions",
            "challenge_code_format",
            "challenge_code ~ '^[A-HJ-NP-Z2-9]{6}$'",
        ),
        _check("capture_sessions", "milestone_index_not_negative", "milestone_index >= 0"),
        _check("capture_sessions", "attempt_positive", "attempt >= 1"),
        _check("capture_sessions", "expires_after_issue", "expires_at > issued_at"),
        _check("capture_sessions", "uploads_after_capture", "upload_until >= expires_at"),
        _check(
            "capture_sessions",
            "submitted_at_when_submitted",
            "(status = 'submitted') = (submitted_at IS NOT NULL)",
        ),
    )
    op.create_index(op.f("ix_capture_sessions_project_id"), "capture_sessions", ["project_id"])
    op.create_index(
        "uq_capture_sessions_one_open",
        "capture_sessions",
        ["project_id", "milestone_index"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "evidence_items",
        _id(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        _time("captured_at"),
        sa.Column("latitude", sa.Double(), nullable=True),
        sa.Column("longitude", sa.Double(), nullable=True),
        sa.Column("accuracy_m", sa.Double(), nullable=True),
        sa.Column("mock_location", sa.Boolean(), server_default="false", nullable=False),
        _time("received_at"),
        sa.Column("redacted_key", sa.Text(), nullable=True),
        sa.Column("redacted_cid", sa.Text(), nullable=True),
        sa.Column("blurred_regions", sa.Integer(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_items")),
        _fk("evidence_items", "session_id", "capture_sessions"),
        sa.UniqueConstraint(
            "session_id", "sha256", name=op.f("uq_evidence_items_session_id_sha256")
        ),
        sa.UniqueConstraint(
            "session_id", "position", name=op.f("uq_evidence_items_session_id_position")
        ),
        _one_of("evidence_items", "kind", PROOF_KINDS),
        _one_of("evidence_items", "content_type", EVIDENCE_TYPES),
        _length("evidence_items", "sha256", 32),
        _check("evidence_items", "size_bytes_positive", "size_bytes > 0"),
        _check("evidence_items", "position_not_negative", "position >= 0"),
        _check("evidence_items", "latitude_range", "latitude >= -90 AND latitude <= 90"),
        _check("evidence_items", "longitude_range", "longitude >= -180 AND longitude <= 180"),
        _check("evidence_items", "accuracy_m_positive", "accuracy_m > 0"),
        _check(
            "evidence_items",
            "fix_complete",
            "(latitude IS NULL) = (longitude IS NULL)"
            " AND (latitude IS NULL) = (accuracy_m IS NULL)",
        ),
        _check(
            "evidence_items",
            "site_capture_has_fix",
            "kind NOT IN ('photo', 'video') OR latitude IS NOT NULL",
        ),
        _check(
            "evidence_items",
            "redacted_copy_complete",
            "(redacted_key IS NULL) = (redacted_cid IS NULL)",
        ),
        _check("evidence_items", "blurred_regions_not_negative", "blurred_regions >= 0"),
    )

    op.create_table(
        "photo_hashes",
        _id(),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("phash", sa.LargeBinary(), nullable=False),
        sa.Column("dhash", sa.LargeBinary(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo_hashes")),
        _fk("photo_hashes", "item_id", "evidence_items", ondelete="CASCADE"),
        sa.UniqueConstraint("item_id", name=op.f("uq_photo_hashes_item_id")),
        _length("photo_hashes", "phash", 8),
        _length("photo_hashes", "dhash", 8),
    )

    op.create_table(
        "evidence_bundles",
        _id(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_index", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("manifest_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("bundle_hash", sa.LargeBinary(), nullable=False),
        sa.Column("device_address", sa.Text(), nullable=False),
        sa.Column("device_signature", sa.LargeBinary(), nullable=False),
        sa.Column("attestation", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("public_manifest", sa.LargeBinary(), nullable=True),
        sa.Column("public_cid", sa.Text(), nullable=True),
        sa.Column("charity_signature", sa.LargeBinary(), nullable=True),
        sa.Column("signed_by", sa.Uuid(), nullable=True),
        _time("signed_at", nullable=True),
        sa.Column("submit_outbox_id", sa.BigInteger(), nullable=True),
        sa.Column("checks_outbox_id", sa.BigInteger(), nullable=True),
        _time("anchored_at", nullable=True),
        sa.Column("anchored_tx", sa.LargeBinary(), nullable=True),
        _time("pinned_at", nullable=True),
        _time("voided_at", nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("tries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        _time("retry_at", nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_bundles")),
        _fk("evidence_bundles", "session_id", "capture_sessions"),
        _fk("evidence_bundles", "project_id", "projects"),
        _fk("evidence_bundles", "signed_by", "users"),
        _fk("evidence_bundles", "submit_outbox_id", "chain_outbox"),
        _fk("evidence_bundles", "checks_outbox_id", "chain_outbox"),
        _fk("evidence_bundles", "created_by", "users"),
        sa.UniqueConstraint("session_id", name=op.f("uq_evidence_bundles_session_id")),
        _one_of(
            "evidence_bundles", "status", ["draft", "checked", "published", "anchored", "void"]
        ),
        _check("evidence_bundles", "device_address_format", f"device_address ~ {ADDRESS}"),
        _length("evidence_bundles", "bundle_hash", 32),
        _check(
            "evidence_bundles", "bundle_hash_matches_bytes", "bundle_hash = sha256(manifest_bytes)"
        ),
        _length("evidence_bundles", "device_signature", 65),
        _length("evidence_bundles", "charity_signature", 65),
        _length("evidence_bundles", "anchored_tx", 32),
        _check(
            "evidence_bundles",
            "public_copy_complete",
            "(public_manifest IS NULL) = (public_cid IS NULL)",
        ),
        _check(
            "evidence_bundles",
            "published_has_cid",
            "status IN ('draft', 'checked') OR public_cid IS NOT NULL",
        ),
        _check(
            "evidence_bundles",
            "signed_once_published",
            "charity_signature IS NULL OR status IN ('published', 'anchored', 'void')",
        ),
        _check(
            "evidence_bundles",
            "signed_at_when_signed",
            "(charity_signature IS NULL) = (signed_at IS NULL)",
        ),
        _check(
            "evidence_bundles",
            "anchored_is_signed",
            "status <> 'anchored' OR (charity_signature IS NOT NULL AND anchored_at IS NOT NULL)",
        ),
        _check(
            "evidence_bundles", "voided_at_when_void", "(status = 'void') = (voided_at IS NOT NULL)"
        ),
        _check(
            "evidence_bundles",
            "void_is_signed",
            "status <> 'void' OR (charity_signature IS NOT NULL AND void_reason IS NOT NULL)",
        ),
        _check(
            "evidence_bundles",
            "pinned_once_signed",
            "pinned_at IS NULL OR charity_signature IS NOT NULL",
        ),
        _check("evidence_bundles", "tries_not_negative", "tries >= 0"),
    )
    op.create_index(op.f("ix_evidence_bundles_project_id"), "evidence_bundles", ["project_id"])
    op.create_index(
        "uq_evidence_bundles_one_signed",
        "evidence_bundles",
        ["project_id", "milestone_index", "attempt"],
        unique=True,
        postgresql_where=sa.text("charity_signature IS NOT NULL AND status <> 'void'"),
    )

    op.create_table(
        "evidence_checks",
        _id(),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_checks")),
        _fk("evidence_checks", "bundle_id", "evidence_bundles"),
        sa.UniqueConstraint(
            "bundle_id", "number", name=op.f("uq_evidence_checks_bundle_id_number")
        ),
        _one_of("evidence_checks", "kind", ["hard", "advisory"]),
        _one_of("evidence_checks", "status", ["passed", "failed", "advisory", "not_run"]),
        _check("evidence_checks", "number_positive", "number >= 1"),
        _check(
            "evidence_checks", "reason_unless_passed", "status = 'passed' OR reason IS NOT NULL"
        ),
        _check("evidence_checks", "advisory_never_fails", "kind = 'hard' OR status <> 'failed'"),
    )

    op.create_table(
        "check_reports",
        _id(),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_reports")),
        _fk("check_reports", "bundle_id", "evidence_bundles"),
        sa.UniqueConstraint("bundle_id", name=op.f("uq_check_reports_bundle_id")),
        _length("check_reports", "sha256", 32),
        _check("check_reports", "sha256_matches_bytes", "sha256 = sha256(canonical_bytes)"),
    )

    op.execute(KEEP_EVIDENCE_FINAL)


def downgrade() -> None:
    for table in (
        "check_reports",
        "evidence_checks",
        "evidence_bundles",
        "photo_hashes",
        "evidence_items",
        "capture_sessions",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION evidence_items_keep_frozen()")
    op.execute("DROP FUNCTION evidence_bundles_keep_frozen()")
    op.execute("DROP FUNCTION evidence_keep_final()")
