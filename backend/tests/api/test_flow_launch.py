"""Phase 4 end to end: publishing a Passport launches the project on-chain, and the events
come back into PostgreSQL through the indexer."""

import uuid

from eth_account import Account
from flowkit import EXAMPLE_ID, example_doc, launch_example, run, set_charity_key, workers
from sqlalchemy import select
from support import error, ok

from veritas.db.models import Charity, Project, ProjectStatus, User
from veritas.db.models.chain import Alert, ChainEvent, ChainOutbox, OutboxStatus
from veritas.services.passports import create_project


def test_publishing_launches_the_project(
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
    set_charity_key(client, verified_charity["id"], charity_admin, accounts["charity"])
    project_id = launch_example(
        client, db, charity_admin, verified_charity["id"], accounts["charity"]
    )

    queued = {row.kind: row for row in db.scalars(select(ChainOutbox))}
    assert set(queued) == {"register_charity", "register_officer", "launch_project"}
    assert queued["launch_project"].depends_on == max(
        queued["register_charity"].id, queued["register_officer"].id
    )
    assert queued["register_charity"].sender == "admin"

    relayer, indexer = workers(sessions, chain, accounts)
    run(relayer, indexer, w3)

    db.expire_all()
    assert {row.status for row in db.scalars(select(ChainOutbox))} == {OutboxStatus.CONFIRMED}
    project = db.get(Project, uuid.UUID(project_id))
    assert project.status == ProjectStatus.LIVE
    predicted = chain.contracts.factory.functions.predictEscrow(project.id.bytes).call()
    assert project.escrow_address == predicted

    events = {(e.contract, e.event) for e in db.scalars(select(ChainEvent))}
    assert {
        ("VeritasHub", "CharitySet"),
        ("VeritasHub", "OfficerSet"),
        ("EscrowFactory", "ProjectCreated"),
        ("PassportRegistry", "PassportRecorded"),
        ("VeritasHub", "EscrowRegistered"),
    } <= events
    created = db.scalars(select(ChainEvent).where(ChainEvent.event == "ProjectCreated")).one()
    assert created.project_id == project.id
    assert db.scalars(select(Alert)).all() == []

    # Launched means it changes only by amendment: a next version may be drafted, not published.
    base = f"/v1/projects/{project_id}"
    draft = ok(client.put(f"{base}/passport", json={}, headers=charity_admin.headers))
    assert draft["version"] == 2
    error(client.post(f"{base}/publish", headers=charity_admin.headers), 409, "project_locked")
    assert ok(client.get(base))["status"] == "live"


def test_publishing_needs_the_charity_key_signature(
    client, db, chain_app, accounts, charity_admin, verified_charity, verified_contractor, officer
):
    set_charity_key(client, verified_charity["id"], charity_admin, accounts["charity"])
    create_project(
        db,
        db.get(Charity, uuid.UUID(verified_charity["id"])),
        db.get(User, charity_admin.user_id),
        project_id=uuid.UUID(EXAMPLE_ID),
    )
    db.commit()
    base = f"/v1/projects/{EXAMPLE_ID}"
    ok(client.put(f"{base}/passport", json=example_doc(), headers=charity_admin.headers))
    error(client.post(f"{base}/publish", headers=charity_admin.headers), 422, "signature_required")

    typed = ok(client.get(f"{base}/launch-message", headers=charity_admin.headers))
    forged = Account.sign_typed_data(accounts["donor1"].key, full_message=typed)
    body = {"charity_signature": forged.signature.to_0x_hex()}
    error(
        client.post(f"{base}/publish", json=body, headers=charity_admin.headers),
        403,
        "bad_signature",
    )
    assert db.scalars(select(ChainOutbox).where(ChainOutbox.kind == "launch_project")).all() == []
