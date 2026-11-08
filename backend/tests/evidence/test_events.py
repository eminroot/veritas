"""The indexer handlers: a bundle is anchored only when the chain recorded what was signed."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from veritas.core.hashing import to_hex
from veritas.db.models.chain import Alert, ChainEvent
from veritas.db.models.evidence import CheckReport, EvidenceBundle
from veritas.evidence.events import on_checks_recorded, on_evidence_submitted

from .conftest import ESCROW, EXAMPLE_ID
from .kit import proof_set


def event(name: str, log_index: int = 0, project_id=EXAMPLE_ID, **args) -> ChainEvent:
    return ChainEvent(
        block_number=10,
        block_hash=bytes(32),
        tx_hash=bytes([9]) * 32,
        log_index=log_index,
        address=ESCROW,
        contract="MilestoneEscrow",
        event=name,
        args={"milestone": 0, "attempt": 1, **args},
        project_id=project_id,
    )


@pytest.fixture
def signed(db, clock, make, pipeline) -> EvidenceBundle:
    bundle = make(proof_set(clock.now))
    pipeline.run_once()
    db.expire_all()
    row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
    row.charity_signature = bytes(65)
    row.signed_at = row.created_at
    db.commit()
    return row


def alerts(db) -> list[Alert]:
    return list(db.scalars(select(Alert).where(Alert.kind == "evidence_mismatch")))


def test_matching_events_anchor_the_bundle(db, signed):
    report = db.scalars(select(CheckReport)).one()
    on_evidence_submitted(
        db,
        event("EvidenceSubmitted", bundleHash=to_hex(signed.bundle_hash), cid=signed.public_cid),
    )
    assert signed.status == "published"
    on_checks_recorded(
        db, event("ChecksRecorded", 1, reportHash=to_hex(report.sha256), passed=report.passed)
    )
    db.commit()
    db.refresh(signed)
    assert signed.status == "anchored"
    assert signed.anchored_tx == bytes([9]) * 32 and signed.anchored_at is not None
    assert alerts(db) == []


def test_evidence_the_charity_did_not_sign_raises_an_alert(db, signed):
    other_hash = event("EvidenceSubmitted", bundleHash=to_hex(bytes(32)), cid=signed.public_cid)
    unknown_attempt = event(
        "EvidenceSubmitted",
        1,
        bundleHash=to_hex(signed.bundle_hash),
        cid=signed.public_cid,
        attempt=2,
    )
    on_evidence_submitted(db, other_hash)
    on_evidence_submitted(db, unknown_attempt)
    db.commit()
    messages = sorted(alert.message for alert in alerts(db))
    assert messages == [
        "MilestoneEscrow.EvidenceSubmitted: evidence was anchored that no signed bundle here "
        "matches",
        "MilestoneEscrow.EvidenceSubmitted: the anchored bundle hash or CID is not what the "
        "charity signed",
    ]
    assert all(alert.severity == "critical" for alert in alerts(db))


def test_a_report_that_is_not_this_bundles_raises_an_alert_and_anchors_nothing(db, signed):
    on_checks_recorded(db, event("ChecksRecorded", reportHash=to_hex(bytes(32)), passed=True))
    db.commit()
    db.refresh(signed)
    assert signed.status == "published"
    (alert,) = alerts(db)
    assert "not this bundle's report" in alert.message
    assert alert.details["attempt"] == 1
