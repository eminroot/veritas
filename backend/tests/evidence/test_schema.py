"""What the database guarantees about evidence, whatever the application gets wrong."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, InternalError

from veritas.core.hashing import sha256
from veritas.db.models.evidence import (
    CaptureSession,
    CheckReport,
    EvidenceBundle,
    EvidenceCheck,
)

from .kit import proof_set


def refused(db, statement, reason):
    with pytest.raises((IntegrityError, InternalError), match=reason):
        db.execute(statement)
        db.flush()
    db.rollback()


@pytest.fixture
def published(db, clock, make, pipeline):
    bundle = make(proof_set(clock.now))
    pipeline.run_once()
    db.expire_all()
    return db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))


def test_the_bundle_hash_must_be_the_sha256_of_the_manifest_bytes(db, published):
    row = EvidenceBundle.__table__
    refused(
        db,
        update(row).where(row.c.id == published.id).values(bundle_hash=sha256(b"other")),
        "final|bundle_hash_matches_bytes",
    )


def test_a_bundles_manifest_public_copy_and_signatures_are_final(db, published):
    table = EvidenceBundle.__table__
    for values in (
        {"manifest_bytes": b"{}"},
        {"device_signature": bytes(65)},
        {"attestation": "dev1.changed"},
    ):
        refused(db, update(table).where(table.c.id == published.id).values(**values), "final")
    refused(db, delete(table).where(table.c.id == published.id), "cannot be deleted")

    # What the workflow still needs to move is allowed, the public copy too until it is signed.
    this = table.c.id == published.id
    db.execute(update(table).where(this).values(status="published"))
    db.execute(update(table).where(this).values(public_cid=published.public_cid))
    db.execute(
        update(table)
        .where(this)
        .values(charity_signature=bytes(65), signed_at=published.created_at)
    )
    db.commit()
    for values in (
        {"public_cid": "bafkreiother"},
        {"public_manifest": b"{}"},
        {"charity_signature": b"\x01" * 65},
    ):
        refused(db, update(table).where(this).values(**values), "final")


def test_check_results_and_reports_are_never_changed_or_deleted(db, published):
    for table in (CheckReport.__table__, EvidenceCheck.__table__):
        refused(db, update(table).values(created_at=table.c.created_at), "rows are final")
        refused(db, delete(table), "rows are final")
    report = db.scalars(select(CheckReport)).one()
    assert report.sha256 == sha256(report.canonical_bytes)


def test_a_reason_is_required_whenever_a_check_did_not_pass(db, published):
    refused(
        db,
        EvidenceCheck.__table__.insert().values(
            id=uuid.uuid4(),
            bundle_id=published.id,
            number=12,
            name="future",
            kind="hard",
            status="failed",
            reason=None,
        ),
        "reason_unless_passed",
    )
    refused(
        db,
        EvidenceCheck.__table__.insert().values(
            id=uuid.uuid4(),
            bundle_id=published.id,
            number=13,
            name="future",
            kind="advisory",
            status="failed",
            reason="advisory checks only advise",
        ),
        "advisory_never_fails",
    )


def test_one_open_session_per_milestone_and_codes_in_the_alphabet(db, published):
    session = db.get_one(CaptureSession, published.session_id)
    copy = {
        column.name: getattr(session, column.key)
        for column in CaptureSession.__table__.columns
        if column.name not in ("id", "created_at", "updated_at")
    }
    opened = copy | {"status": "open", "submitted_at": None}
    table = CaptureSession.__table__
    db.execute(table.insert().values(id=uuid.uuid4(), **opened | {"challenge_code": "ABCDE2"}))
    refused(
        db,
        table.insert().values(id=uuid.uuid4(), **opened | {"challenge_code": "ABCDE3"}),
        "uq_capture_sessions_one_open",
    )
    refused(
        db,
        table.insert().values(id=uuid.uuid4(), **copy | {"challenge_code": "ABCDE0"}),
        "challenge_code_format",
    )


def test_one_signed_bundle_per_attempt(db, clock, make, pipeline, published):
    clock.advance(hours=2)
    second = make(proof_set(clock.now, seed=9))
    pipeline.run_once()
    table = EvidenceBundle.__table__
    signed = {"charity_signature": bytes(65), "signed_at": clock.now}
    db.execute(update(table).where(table.c.id == published.id).values(**signed))
    db.commit()
    refused(
        db,
        update(table).where(table.c.id == uuid.UUID(second["id"])).values(**signed),
        "uq_evidence_bundles_one_signed",
    )
