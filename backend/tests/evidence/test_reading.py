"""Reading evidence: everything for the charity and the officer, the anchored summary for all."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update

from veritas.core.hashing import sha256, to_hex
from veritas.db.models import Officer
from veritas.db.models.chain import ChainEvent
from veritas.db.models.evidence import CaptureSession, CheckReport, EvidenceBundle, EvidenceItem
from veritas.evidence.events import on_checks_recorded

from .conftest import ESCROW, OFFICER_ADDRESS
from .kit import proof_set
from .test_capture import error


@pytest.fixture
def published(clock, make, pipeline):
    bundle = make(proof_set(clock.now))
    pipeline.run_once()
    return bundle


@pytest.fixture
def project_officer(db, login, project):
    person = login("+994 50 555 55 55")
    db.execute(
        update(Officer).where(Officer.address == OFFICER_ADDRESS).values(user_id=person.user_id)
    )
    db.commit()
    return person


def test_the_charity_and_the_projects_officer_read_everything(
    client, published, charity_admin, project_officer
):
    for person in (charity_admin, project_officer):
        bundle = client.get(f"/v1/evidence/{published['id']}", headers=person.headers).json()
        assert bundle["status"] == "published"
        assert [check["number"] for check in bundle["checks"]] == list(range(1, 12))
        assert bundle["checks"][3]["title"] == "Challenge code visible in a photo"
        assert bundle["report"]["passed"] is True
        assert bundle["items"][0]["latitude"] == 40.7905  # exact, for the reviewers only
        assert bundle["items"][0]["redacted_cid"].startswith("bafkrei")


def test_others_see_nothing_private(client, published, stranger, db):
    base = f"/v1/evidence/{published['id']}"
    item = published["items"][0]["id"]
    for path in (base, f"{base}/report", f"{base}/items/{item}/original"):
        error(client.get(path, headers=stranger.headers), 403, "not_a_reviewer")
    error(client.get(base), 401, "not_authenticated")
    # An officer who is not this project's officer is a stranger here too.
    db.add(
        Officer(
            name="Other",
            organisation="Other audit",
            address="0x" + "22" * 20,
            user_id=stranger.user_id,
            created_by=stranger.user_id,
        )
    )
    db.commit()
    error(client.get(base, headers=stranger.headers), 403, "not_a_reviewer")


def test_the_report_and_originals_are_served_byte_for_byte(client, db, published, charity_admin):
    base = f"/v1/evidence/{published['id']}"
    response = client.get(f"{base}/report", headers=charity_admin.headers)
    report = db.scalars(select(CheckReport)).one()
    assert response.content == report.canonical_bytes
    assert response.headers["x-report-sha256"] == to_hex(sha256(response.content))

    item = published["items"][0]
    original = client.get(f"{base}/items/{item['id']}/original", headers=charity_admin.headers)
    assert original.status_code == 200
    assert to_hex(sha256(original.content)) == item["sha256"]
    assert original.headers["content-type"] == "image/jpeg"
    assert original.headers["cache-control"] == "private, no-store"


def test_reviewers_get_the_signed_manifest_and_the_challenge_code(
    client, db, app, published, project_officer
):
    """The officer reviews check 4 by hand until Phase 7, so needs the code; and the manifest
    is what ties every original to the hash on-chain."""
    base = f"/v1/evidence/{published['id']}"
    bundle = client.get(base, headers=project_officer.headers).json()
    row = db.get_one(EvidenceBundle, uuid.UUID(published["id"]))
    session = db.get_one(CaptureSession, row.session_id)
    assert bundle["code"]["challenge_code"] == session.challenge_code
    assert bundle["device_signature"] == "0x" + row.device_signature.hex()

    manifest = client.get(bundle["manifest_url"], headers=project_officer.headers)
    assert manifest.content == row.manifest_bytes
    assert to_hex(sha256(manifest.content)) == bundle["bundle_hash"]
    assert manifest.headers["x-bundle-hash"] == bundle["bundle_hash"]

    # A file in a submitted manifest cannot be swapped in the database...
    item = db.get_one(EvidenceItem, uuid.UUID(published["items"][0]["id"]))
    with pytest.raises(Exception, match="final"):
        db.execute(update(EvidenceItem).where(EvidenceItem.id == item.id).values(sha256=bytes(32)))
        db.flush()
    db.rollback()
    # ...and one swapped in storage is not served as the original.
    app.state.storage.put(item.storage_key, b"something else")
    error(
        client.get(f"{base}/items/{item.id}/original", headers=project_officer.headers),
        500,
        "file_damaged",
    )


def test_a_milestones_bundles_are_all_listed_for_reviewers(
    client, clock, make, pipeline, published, charity_admin
):
    clock.advance(hours=2)
    second = make(proof_set(clock.now, seed=3))
    response = client.get(
        f"/v1/projects/{published['project_id']}/milestones/0/bundles",
        headers=charity_admin.headers,
    )
    listed = response.json()
    assert [row["id"] for row in listed] == [second["id"], published["id"]]
    assert [row["status"] for row in listed] == ["draft", "published"]
    assert listed[1]["passed"] is True and listed[0]["passed"] is None


def test_the_public_sees_what_was_anchored_and_only_that(client, db, published):
    url = f"/v1/projects/{published['project_id']}/milestones/0/evidence"
    assert client.get(url).json() == []

    row = db.get_one(EvidenceBundle, uuid.UUID(published["id"]))
    report = db.scalars(select(CheckReport)).one()
    row.charity_signature = bytes(65)
    row.signed_at = row.created_at
    db.commit()
    on_checks_recorded(
        db,
        ChainEvent(
            block_number=10,
            block_hash=bytes(32),
            tx_hash=bytes([7]) * 32,
            log_index=1,
            address=ESCROW,
            contract="MilestoneEscrow",
            event="ChecksRecorded",
            args={
                "milestone": 0,
                "attempt": 1,
                "reportHash": to_hex(report.sha256),
                "passed": True,
            },
            project_id=row.project_id,
        ),
    )
    db.commit()

    (anchored,) = client.get(url).json()
    assert anchored["attempt"] == 1
    assert anchored["bundle_hash"] == published["bundle_hash"]
    assert anchored["public_cid"] == row.public_cid
    assert anchored["report_sha256"] == to_hex(report.sha256)
    assert anchored["passed"] is True
    assert [check["status"] for check in anchored["checks"]][:3] == ["passed"] * 3
    assert "details" not in anchored["checks"][0]


def test_the_signer_sees_each_redacted_copy_before_confirming_it(
    client, db, published, charity_admin, login
):
    """The copy that would go public, byte for byte, for the charity and the officer only."""
    photo_item = published["items"][0]
    url = f"/v1/evidence/{published['id']}/items/{photo_item['id']}/public"
    response = client.get(url, headers=charity_admin.headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    item = db.get_one(EvidenceItem, uuid.UUID(photo_item["id"]))
    assert response.headers["x-content-cid"] == item.redacted_cid
    assert response.headers["cache-control"] == "private, no-store"
    outsider = login("+994 55 777 77 77")
    assert client.get(url, headers=outsider.headers).status_code == 403
