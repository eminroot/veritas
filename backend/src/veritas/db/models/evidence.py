"""Evidence: capture sessions, the files captured in them, the bundle a session's manifest
makes, the deterministic checks on that bundle, its report, and the perceptual hash of every
photo ever stored.

A capture session hands out a one-time challenge code that is valid for a few minutes. The
files captured in it are uploaded one by one and kept in private storage under their SHA-256.
The app then submits a manifest that lists every file, signed by the capturing phone's key:
the bundle hash is the SHA-256 of those exact manifest bytes, and the database checks that it
is. Checks and their report are written once and never change; triggers in the migration
refuse to edit them, to edit a bundle's manifest, hash or signatures once they are set, its
public copy once the charity has signed, and a file once a submitted manifest lists it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Double,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
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
from veritas.passport.models import ProofKind


class CaptureStatus(StrEnum):
    OPEN = "open"
    """Taking uploads and the manifest until `upload_until`."""
    SUBMITTED = "submitted"
    """The manifest arrived and became a bundle. Nothing more is added."""
    EXPIRED = "expired"
    """`upload_until` passed without a manifest. Set when the next session starts."""


class BundleStatus(StrEnum):
    DRAFT = "draft"
    """The manifest is in; the checks have not run yet."""
    CHECKED = "checked"
    """Every check has a result and the report is stored."""
    PUBLISHED = "published"
    """The public copy is built and its CIDs are known, with the photos redacted in private
    storage. Waiting for the charity's signature, which also confirms, photo by photo, what
    goes public; the files are added to IPFS after that (`pinned_at`)."""
    ANCHORED = "anchored"
    """The bundle hash, its CID and the report hash are on-chain (set by the indexer)."""
    VOID = "void"
    """Signed, but the chain refused it, so it never got anchored. The signature stays for the
    record; the milestone's attempt takes other evidence."""


class CheckKind(StrEnum):
    HARD = "hard"
    """A failure blocks the milestone unless the officer overrides it with a signed reason."""
    ADVISORY = "advisory"
    """Shown to the officer and donors, never blocks anything on its own."""


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ADVISORY = "advisory"
    """Something worth a look that does not block, like a photo close to an earlier one."""
    NOT_RUN = "not_run"
    """Arrives in a later phase. The officer checks it by hand until then."""


EVIDENCE_TYPES = ("image/jpeg", "image/png", "video/mp4", "video/quicktime", "application/pdf")


class CaptureSession(UUIDPrimaryKey, Timestamps, Base):
    """One visit to a site: a challenge code, the phone that captures, and a short window."""

    __tablename__ = "capture_sessions"
    __table_args__ = (
        Index(
            "uq_capture_sessions_one_open",
            "project_id",
            "milestone_index",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        one_of("status", CaptureStatus),
        evm_address("device_address"),
        CheckConstraint("challenge_code ~ '^[A-HJ-NP-Z2-9]{6}$'", name="challenge_code_format"),
        CheckConstraint("milestone_index >= 0", name="milestone_index_not_negative"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        CheckConstraint("expires_at > issued_at", name="expires_after_issue"),
        CheckConstraint("upload_until >= expires_at", name="uploads_after_capture"),
        CheckConstraint(
            "(status = 'submitted') = (submitted_at IS NOT NULL)",
            name="submitted_at_when_submitted",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_index: Mapped[int]
    attempt: Mapped[int]
    """The milestone's attempt this evidence is for: one more than the attempts anchored."""
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    device_address: Mapped[str] = mapped_column(ForeignKey("devices.address"))
    """The registered key that captures and signs the manifest."""
    challenge_code: Mapped[str] = mapped_column(unique=True)
    """Six characters with no 0, O, 1 or I. Never handed out twice."""
    issued_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    """Captures must happen before this."""
    upload_until: Mapped[datetime]
    """Uploads and the manifest are taken until this, for places with a weak signal."""
    status: Mapped[str] = mapped_column(default=CaptureStatus.OPEN, server_default="open")
    submitted_at: Mapped[datetime | None]


class EvidenceItem(UUIDPrimaryKey, CreatedAt, Base):
    """One captured file. The original stays in private storage, addressed by its SHA-256."""

    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("session_id", "sha256"),
        UniqueConstraint("session_id", "position"),
        one_of("kind", ProofKind),
        one_of("content_type", EVIDENCE_TYPES),
        byte_length("sha256", 32),
        CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="longitude_range"),
        CheckConstraint("accuracy_m > 0", name="accuracy_m_positive"),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)"
            " AND (latitude IS NULL) = (accuracy_m IS NULL)",
            name="fix_complete",
        ),
        CheckConstraint(
            "kind NOT IN ('photo', 'video') OR latitude IS NOT NULL", name="site_capture_has_fix"
        ),
        CheckConstraint(
            "(redacted_key IS NULL) = (redacted_cid IS NULL)", name="redacted_copy_complete"
        ),
        CheckConstraint("blurred_regions >= 0", name="blurred_regions_not_negative"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capture_sessions.id"))
    position: Mapped[int | None]
    """Where the manifest lists the item. Set when the manifest is accepted."""
    kind: Mapped[str]
    sha256: Mapped[bytes]
    """Computed here and equal to what the app declared; uploads that differ are refused."""
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str]
    storage_key: Mapped[str]
    captured_at: Mapped[datetime]
    """The phone's clock. Check 3 compares it with the session and the server's receipt."""
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    accuracy_m: Mapped[float | None] = mapped_column(Double)
    mock_location: Mapped[bool] = mapped_column(default=False, server_default="false")
    """The phone said the position came from a location-mocking app."""
    received_at: Mapped[datetime]
    """The server clock when the upload arrived."""
    redacted_key: Mapped[str | None]
    """The public copy of a photo: metadata stripped, faces and number plates blurred."""
    redacted_cid: Mapped[str | None]
    blurred_regions: Mapped[int | None]


class PhotoHash(UUIDPrimaryKey, CreatedAt, Base):
    """The perceptual hashes of every photo ever stored, for spotting a photo used twice.

    One row per photo item, written when the photo is uploaded, whether or not its bundle is
    ever submitted: a photo from an abandoned session is still not new.
    """

    __tablename__ = "photo_hashes"
    __table_args__ = (byte_length("phash", 8), byte_length("dhash", 8))

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"), unique=True
    )
    phash: Mapped[bytes]
    """64-bit pHash (DCT), most significant bit first, as imagehash writes it in hex."""
    dhash: Mapped[bytes]
    """64-bit dHash (gradients), in the same layout."""


class EvidenceBundle(UUIDPrimaryKey, Timestamps, Base):
    """A session's frozen manifest, its checks, its public copy and its way onto the chain."""

    __tablename__ = "evidence_bundles"
    __table_args__ = (
        Index(
            "uq_evidence_bundles_one_signed",
            "project_id",
            "milestone_index",
            "attempt",
            unique=True,
            postgresql_where=text("charity_signature IS NOT NULL AND status <> 'void'"),
        ),
        one_of("status", BundleStatus),
        evm_address("device_address"),
        byte_length("bundle_hash", 32),
        CheckConstraint("bundle_hash = sha256(manifest_bytes)", name="bundle_hash_matches_bytes"),
        byte_length("device_signature", 65),
        byte_length("charity_signature", 65),
        byte_length("anchored_tx", 32),
        CheckConstraint(
            "(public_manifest IS NULL) = (public_cid IS NULL)", name="public_copy_complete"
        ),
        CheckConstraint(
            "status IN ('draft', 'checked') OR public_cid IS NOT NULL", name="published_has_cid"
        ),
        CheckConstraint(
            "charity_signature IS NULL OR status IN ('published', 'anchored', 'void')",
            name="signed_once_published",
        ),
        CheckConstraint(
            "(charity_signature IS NULL) = (signed_at IS NULL)", name="signed_at_when_signed"
        ),
        CheckConstraint(
            "status <> 'anchored' OR (charity_signature IS NOT NULL AND anchored_at IS NOT NULL)",
            name="anchored_is_signed",
        ),
        CheckConstraint("(status = 'void') = (voided_at IS NOT NULL)", name="voided_at_when_void"),
        CheckConstraint(
            "status <> 'void' OR (charity_signature IS NOT NULL AND void_reason IS NOT NULL)",
            name="void_is_signed",
        ),
        CheckConstraint(
            "pinned_at IS NULL OR charity_signature IS NOT NULL", name="pinned_once_signed"
        ),
        CheckConstraint("tries >= 0", name="tries_not_negative"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capture_sessions.id"), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_index: Mapped[int]
    attempt: Mapped[int]
    manifest_bytes: Mapped[bytes]
    """The canonical manifest exactly as the phone signed it. Never re-serialised."""
    bundle_hash: Mapped[bytes]
    """SHA-256 of manifest_bytes: the hash the charity signs and the chain stores."""
    device_address: Mapped[str]
    device_signature: Mapped[bytes]
    """EIP-191 personal_sign by the device over the manifest's hash."""
    attestation: Mapped[str | None]
    """App Attest or Play Integrity token as the app sent it. Verified by check 1."""
    status: Mapped[str] = mapped_column(default=BundleStatus.DRAFT, server_default="draft")
    public_manifest: Mapped[bytes | None]
    """The public copy's canonical JSON, exactly as it is added to IPFS. Final once signed."""
    public_cid: Mapped[str | None]
    """CID of public_manifest. This is the CID anchored on-chain."""
    charity_signature: Mapped[bytes | None]
    """The charity key's EIP-712 Evidence signature over the bundle hash."""
    signed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    signed_at: Mapped[datetime | None]
    submit_outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))
    checks_outbox_id: Mapped[int | None] = mapped_column(ForeignKey("chain_outbox.id"))
    anchored_at: Mapped[datetime | None]
    anchored_tx: Mapped[bytes | None]
    """The transaction that recorded the checks, the last of the two."""
    pinned_at: Mapped[datetime | None]
    """When the public manifest, the report and the confirmed photos were added to IPFS."""
    voided_at: Mapped[datetime | None]
    void_reason: Mapped[str | None]
    """Why the chain refused the signed bundle: the contract's error, by name."""
    tries: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    """Failed attempts at the evidence worker's current step for this bundle."""
    last_error: Mapped[str | None]
    retry_at: Mapped[datetime | None]
    """The worker leaves the bundle alone until then, backing off after each failure."""
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class EvidenceCheck(UUIDPrimaryKey, CreatedAt, Base):
    """One check's result for one bundle. ARCHITECTURE.md section 9 numbers them."""

    __tablename__ = "evidence_checks"
    __table_args__ = (
        UniqueConstraint("bundle_id", "number"),
        one_of("kind", CheckKind),
        one_of("status", CheckStatus),
        CheckConstraint("number >= 1", name="number_positive"),
        CheckConstraint("status = 'passed' OR reason IS NOT NULL", name="reason_unless_passed"),
        CheckConstraint("kind = 'hard' OR status <> 'failed'", name="advisory_never_fails"),
    )

    bundle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_bundles.id"))
    number: Mapped[int]
    name: Mapped[str]
    kind: Mapped[str]
    status: Mapped[str]
    reason: Mapped[str | None]
    """Why it did not pass, in words a person can act on."""
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class CheckReport(UUIDPrimaryKey, CreatedAt, Base):
    """Every check result of a bundle as canonical JSON. Its SHA-256 goes on-chain."""

    __tablename__ = "check_reports"
    __table_args__ = (
        byte_length("sha256", 32),
        CheckConstraint("sha256 = sha256(canonical_bytes)", name="sha256_matches_bytes"),
    )

    bundle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_bundles.id"), unique=True)
    canonical_bytes: Mapped[bytes]
    sha256: Mapped[bytes]
    passed: Mapped[bool]
    """Every hard check that ran passed. Checks that did not run are not counted."""
