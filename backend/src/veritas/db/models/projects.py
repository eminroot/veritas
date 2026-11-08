"""Projects, their Passport versions, and the milestones a published Passport promises.

`passports` keeps every version: drafts as editable JSON, published versions as
the exact canonical bytes that were hashed. The database itself checks that the
stored hash is the SHA-256 of the stored bytes, and a trigger (in the migration)
refuses to change or delete a published version.

`milestones`, `budget_lines` and `sites` are a queryable copy of the current
published Passport, rebuilt every time a version is published.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from veritas.chain.leaves import MAX_MILESTONES
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
from veritas.passport.models import Category


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    LIVE = "live"
    """The escrow exists on-chain. Set by the indexer from Phase 4 on."""
    STOPPED = "stopped"
    COMPLETED = "completed"


class PassportStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


class MilestoneStatus(StrEnum):
    """The milestone states in ARCHITECTURE.md section 6, mirrored from the chain in Phase 4."""

    FUNDING = "funding"
    EVIDENCE_SUBMITTED = "evidence_submitted"
    CHECKED = "checked"
    OFFICER_APPROVED = "officer_approved"
    VOTING = "voting"
    APPROVED = "approved"
    RELEASED = "released"
    PAID = "paid"
    REJECTED = "rejected"
    STOPPED = "stopped"


_DRAFT_OR_PUBLISHED = (
    "(status = 'draft' AND draft_json IS NOT NULL AND canonical_bytes IS NULL"
    " AND sha256 IS NULL AND cid IS NULL AND published_at IS NULL)"
    " OR (status <> 'draft' AND draft_json IS NULL AND canonical_bytes IS NOT NULL"
    " AND sha256 IS NOT NULL AND cid IS NOT NULL AND published_at IS NOT NULL)"
)


class Project(UUIDPrimaryKey, Timestamps, Base):
    """A project. Its id is the Passport's project_id."""

    __tablename__ = "projects"
    __table_args__ = (
        one_of("status", ProjectStatus),
        one_of("category", Category),
        evm_address("escrow_address"),
        evm_address("charity_signer"),
        CheckConstraint("total_qapik > 0", name="total_qapik_positive"),
    )

    charity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charities.id"), index=True)
    status: Mapped[str] = mapped_column(default=ProjectStatus.DRAFT, server_default="draft")
    title: Mapped[str | None]
    """From the current published Passport, for listings."""
    category: Mapped[str | None]
    total_qapik: Mapped[Qapik | None]
    escrow_address: Mapped[str | None]
    charity_signer: Mapped[str | None]
    """The charity key the escrow was launched with. The escrow keeps it for good, so the
    project's evidence, withdrawal and amendments are signed with it even after the charity
    changes its key for later projects."""
    published_at: Mapped[datetime | None]
    """When the first version was published."""
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    milestones: Mapped[list[Milestone]] = relationship(order_by="Milestone.index", viewonly=True)


class PassportVersion(UUIDPrimaryKey, Timestamps, Base):
    """One version of a project's Passport: a draft, or published bytes that never change."""

    __tablename__ = "passports"
    __table_args__ = (
        UniqueConstraint("project_id", "version"),
        Index(
            "uq_passports_one_draft",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
        Index(
            "uq_passports_one_published",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        one_of("status", PassportStatus),
        CheckConstraint("version >= 1", name="version_positive"),
        byte_length("sha256", 32),
        CheckConstraint("sha256 = sha256(canonical_bytes)", name="sha256_matches_bytes"),
        CheckConstraint("jsonb_typeof(draft_json) = 'object'", name="draft_is_object"),
        CheckConstraint(_DRAFT_OR_PUBLISHED, name="draft_or_published"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(default=PassportStatus.DRAFT, server_default="draft")
    draft_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    """Python None must be SQL NULL here, not the JSON value null."""
    canonical_bytes: Mapped[bytes | None]
    """Exactly what was hashed and published. Served as is, never re-serialised."""
    sha256: Mapped[bytes | None]
    cid: Mapped[str | None]
    charity_signature: Mapped[bytes | None]
    """The charity's signature over the hash. Required from Phase 4 on."""
    published_at: Mapped[datetime | None]
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Milestone(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("project_id", "index"),
        one_of("status", MilestoneStatus),
        CheckConstraint(f"index >= 0 AND index < {MAX_MILESTONES}", name="index_range"),
        CheckConstraint("amount_qapik > 0", name="amount_qapik_positive"),
        CheckConstraint("window_closes >= window_opens", name="window_in_order"),
        CheckConstraint("closes_at > opens_at", name="times_in_order"),
        CheckConstraint("funded_qapik >= 0 AND funded_qapik <= amount_qapik", name="funded_range"),
        byte_length("bundle_hash", 32),
        byte_length("report_hash", 32),
        byte_length("invoice_hash", 32),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    index: Mapped[int]
    title: Mapped[str]
    amount_qapik: Mapped[Qapik]
    window_opens: Mapped[date]
    window_closes: Mapped[date]
    opens_at: Mapped[datetime]
    closes_at: Mapped[datetime]
    evidence_deadline: Mapped[datetime]
    status: Mapped[str] = mapped_column(default=MilestoneStatus.FUNDING, server_default="funding")
    passport_version: Mapped[int]
    """The Passport version this row was last built from."""

    # Mirrored from the escrow's events by the indexer. The chain is the source of truth.
    funded_qapik: Mapped[Qapik] = mapped_column(default=0, server_default="0")
    """What the escrow has credited to this milestone, from batches and redirects."""
    attempt: Mapped[int] = mapped_column(default=0, server_default="0")
    """How many evidence bundles were anchored. Decisions and votes are per attempt."""
    bundle_hash: Mapped[bytes | None]
    evidence_cid: Mapped[str | None]
    report_hash: Mapped[bytes | None]
    checks_passed: Mapped[bool | None]
    invoice_hash: Mapped[bytes | None]
    approved_qapik: Mapped[Qapik | None]
    """The amount the officer approved for payment against the invoice."""
    resubmit_deadline: Mapped[datetime | None]

    budget_lines: Mapped[list[BudgetLine]] = relationship(
        order_by="BudgetLine.position", viewonly=True
    )
    sites: Mapped[list[Site]] = relationship(viewonly=True)


class BudgetLine(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "budget_lines"
    __table_args__ = (
        UniqueConstraint("milestone_id", "position"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint("unit_price_qapik >= 0", name="unit_price_qapik_not_negative"),
        CheckConstraint(
            "amount_qapik = quantity * unit_price_qapik", name="amount_is_quantity_times_price"
        ),
    )

    milestone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("milestones.id", ondelete="CASCADE"))
    position: Mapped[int]
    item: Mapped[str]
    quantity: Mapped[int]
    unit: Mapped[str]
    unit_price_qapik: Mapped[Qapik]
    amount_qapik: Mapped[Qapik]


class Site(UUIDPrimaryKey, CreatedAt, Base):
    """A milestone's geofence. Geography, so distances and areas come out in metres."""

    __tablename__ = "sites"
    __table_args__ = (Index("ix_sites_geom", "geom", postgresql_using="gist"),)

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"), index=True
    )
    geom: Mapped[Any] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326, spatial_index=False), nullable=False
    )
