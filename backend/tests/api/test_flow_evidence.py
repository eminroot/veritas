"""Phase 6 end to end: evidence goes from a field worker's phone to a check report anchored on
a real escrow, through the API, the evidence worker, the relayer and the indexer.

The example project launches on Anvil as in test_flow_launch.py. Its milestone 0 takes evidence
from 1 to 31 March 2027, so the API's evidence clock is set to 10 March 2027; the chain keeps
its own time, which is before the escrow's evidence deadline of 14 April 2027.
"""

import uuid
from datetime import timedelta

import pytest
from eth_account import Account
from flowkit import launch_example, run, set_charity_key, workers
from sqlalchemy import select
from support import ok

from evidence.kit import (
    IN_WINDOW,
    JUST_NORTH,
    Capture,
    Clock,
    FixedBoxes,
    attest,
    manifest_for,
    near_copy,
    photo,
    proof_set,
    register_device,
    sign_manifest,
    start,
    submit,
    upload,
)
from veritas.api.routes.evidence import evidence_clock
from veritas.db.models import Milestone, Project
from veritas.db.models.chain import Alert, ChainOutbox, OutboxStatus
from veritas.db.models.evidence import CheckReport, EvidenceBundle, EvidenceCheck
from veritas.evidence.ipfs import FakeIpfs
from veritas.evidence.pipeline import EvidencePipeline

CHECKED = 2
"""MilestoneEscrow.Status.Checked."""


@pytest.fixture
def clock(app):
    clock = Clock(IN_WINDOW)
    app.dependency_overrides[evidence_clock] = clock
    yield clock
    app.dependency_overrides.pop(evidence_clock, None)


@pytest.fixture
def launched(
    client,
    db,
    chain_app,
    chain,
    w3,
    accounts,
    sessions,
    charity_admin,
    verified_charity,
    verified_contractor,
    officer,
):
    """The example project, live on Anvil, and the relayer and indexer that launched it."""
    set_charity_key(client, verified_charity["id"], charity_admin, accounts["charity"])
    project_id = launch_example(
        client, db, charity_admin, verified_charity["id"], accounts["charity"]
    )
    relayer, indexer = workers(sessions, chain, accounts)
    run(relayer, indexer, w3)
    return project_id, relayer, indexer


@pytest.fixture
def field_worker(client, login, charity_admin, verified_charity):
    person = login("+994 50 333 33 33")
    body = {"phone": person.phone, "role": "field_worker"}
    url = f"/v1/charities/{verified_charity['id']}/members"
    ok(client.post(url, json=body, headers=charity_admin.headers), 201)
    return person


@pytest.fixture
def phone(client, field_worker):
    account = Account.create()
    register_device(client, field_worker, account)
    return account


@pytest.fixture
def pipeline(sessions, app, settings):
    return EvidencePipeline(
        sessions,
        storage=app.state.storage,
        settings=settings,
        ipfs=FakeIpfs(),
        detector=FixedBoxes(),
    )


def capture(client, settings, clock, person, phone, project_id, captures) -> dict:
    """What the app does on site: a session, every upload, then the signed manifest."""
    session = ok(start(client, person, project_id, phone), 201)
    clock.now = max(c.captured_at for c in captures) + timedelta(minutes=1)
    for item in captures:
        ok(upload(client, person, session["id"], item), 201)
    data = manifest_for(session, phone.address, captures)
    token = attest(settings, phone.address, session["id"], data)
    return ok(submit(client, person, session["id"], data, sign_manifest(phone, data), token), 201)


def sign_off(client, charity_admin, charity_key, bundle, photos=(1, 2, 3, 4)) -> dict:
    """The charity admin's phone signs the Evidence message and the bundle is queued. The
    admin has looked at the redacted photos and confirms these show no face or plate."""
    base = f"/v1/evidence/{bundle['id']}"
    typed = ok(client.get(f"{base}/evidence-message", headers=charity_admin.headers))
    signature = Account.sign_typed_data(charity_key.key, full_message=typed).signature
    body = {"charity_signature": signature.to_0x_hex(), "publish_photos": list(photos)}
    return ok(client.post(f"{base}/anchor", json=body, headers=charity_admin.headers))


def on_chain(chain, db, project_id) -> tuple:
    project = db.get(Project, uuid.UUID(project_id))
    escrow = chain.contracts.escrow(project.escrow_address)
    fields = escrow.functions.milestone(0).call()
    # attempt, status, checksPassed, bundleHash, reportHash (MilestoneEscrow.Milestone)
    return fields[8], fields[9], fields[10], bytes(fields[11]), bytes(fields[12])


def test_evidence_goes_from_the_phone_to_an_anchored_report(
    client,
    db,
    settings,
    chain,
    w3,
    accounts,
    clock,
    launched,
    charity_admin,
    field_worker,
    phone,
    pipeline,
):
    project_id, relayer, indexer = launched
    bundle = capture(client, settings, clock, field_worker, phone, project_id, proof_set(clock.now))
    assert bundle["status"] == "draft"

    assert pipeline.run_once() == 2  # checked, then the public copy prepared in private
    assert pipeline.ipfs.files == {}
    queued = sign_off(client, charity_admin, accounts["charity"], bundle, photos=(1, 2, 4))
    assert queued["status"] == "published" and queued["anchoring"]["submit_evidence"] == "pending"
    assert pipeline.run_once() == 1  # the signed copy goes to IPFS: three photos, report, copy
    assert len(pipeline.ipfs.files) == 5

    run(relayer, indexer, w3)

    db.expire_all()
    row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
    report = db.scalars(select(CheckReport).where(CheckReport.bundle_id == row.id)).one()
    assert report.passed is True
    assert on_chain(chain, db, project_id) == (1, CHECKED, True, row.bundle_hash, report.sha256)

    milestone = db.scalars(
        select(Milestone).where(Milestone.project_id == uuid.UUID(project_id), Milestone.index == 0)
    ).one()
    assert milestone.status == "checked" and milestone.attempt == 1
    assert milestone.bundle_hash == row.bundle_hash and milestone.report_hash == report.sha256
    assert milestone.evidence_cid == row.public_cid and milestone.checks_passed is True

    assert row.status == "anchored" and row.anchored_at is not None
    outbox = db.scalars(
        select(ChainOutbox).where(ChainOutbox.kind.in_(["submit_evidence", "record_checks"]))
    ).all()
    assert {r.status for r in outbox} == {OutboxStatus.CONFIRMED}
    assert row.anchored_tx == db.get(ChainOutbox, row.checks_outbox_id).tx_hash
    assert db.scalars(select(Alert)).all() == []

    (public,) = ok(client.get(f"/v1/projects/{project_id}/milestones/0/evidence"))
    assert public["public_cid"] == row.public_cid and public["passed"] is True
    assert public["report_sha256"] == "0x" + report.sha256.hex()
    assert pipeline.ipfs.cat(public["report_cid"]) == report.canonical_bytes


def test_failed_checks_are_anchored_too_and_each_says_why(
    client,
    db,
    settings,
    chain,
    w3,
    accounts,
    clock,
    launched,
    charity_admin,
    field_worker,
    phone,
    pipeline,
):
    project_id, relayer, indexer = launched
    # A photo from an earlier visit that was never submitted.
    earlier = ok(start(client, field_worker, project_id, phone), 201)
    old = Capture("photo", photo(500), clock.now)
    ok(upload(client, field_worker, earlier["id"], old), 201)
    clock.advance(hours=2)

    captures = proof_set(clock.now, seed=6)
    captures[0] = Capture("photo", near_copy(old.data), captures[0].captured_at)
    captures[1] = Capture("photo", photo(601), captures[1].captured_at, at=JUST_NORTH, accuracy_m=5)
    bundle = capture(client, settings, clock, field_worker, phone, project_id, captures)
    pipeline.run_once()
    sign_off(client, charity_admin, accounts["charity"], bundle)
    run(relayer, indexer, w3)

    db.expire_all()
    row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
    report = db.scalars(select(CheckReport).where(CheckReport.bundle_id == row.id)).one()
    assert report.passed is False
    assert on_chain(chain, db, project_id) == (1, CHECKED, False, row.bundle_hash, report.sha256)
    assert row.status == "anchored"

    failed = {
        check.number: check.reason
        for check in db.scalars(select(EvidenceCheck).where(EvidenceCheck.bundle_id == row.id))
        if check.status == "failed"
    }
    assert set(failed) == {2, 5}
    assert failed[2] == "Photo 2 is 22 m outside the site, more than its GPS accuracy of 5 m."
    assert failed[5].startswith(
        "Photo 1 is the same picture as a photo from attempt 1 of this milestone, received on "
        "10 March 2027, in a session never submitted (pHash"
    )
    bundle_view = ok(client.get(f"/v1/evidence/{row.id}", headers=charity_admin.headers))
    reasons = {check["number"]: check["reason"] for check in bundle_view["checks"]}
    assert all(reasons[number] for number in (2, 4, 5, 6, 7, 8, 9, 10))
