"""The other roads through Phase 8: Pay-on-Proof, overrides and rejections, a payout the
bank cannot make, and a project stopped by a missed deadline."""

import uuid

from decisionkit import fund, milestone_row, reviewing_officer, sign_typed, warp
from flowkit import deliver_webhooks, live_example, run
from sqlalchemy import select, update
from support import CONTRACTOR, error, ok

from veritas.core.hashing import sha256
from veritas.core.identifiers import normalize_az_iban
from veritas.db.models import Milestone, Project
from veritas.db.models.chain import Alert, ChainOutbox, OutboxStatus
from veritas.db.models.decisions import Ballot, Payout, Release
from veritas.db.models.money import Allocation, Donation, PledgeCharge
from veritas.decisions.jobs import chain_now
from veritas.decisions.payouts import execute_payouts, release_approved
from veritas.decisions.pledges import charge_pledges
from veritas.decisions.stops import stop_missed_deadlines
from veritas.decisions.voting import close_due_ballots
from veritas.payments.batches import build_batch
from veritas.payments.reconcile import reconcile

INVOICE = "0x" + sha256(b"invoice").hex()


def decide(client, officer_user, accounts, project_id, **params):
    base = f"/v1/projects/{project_id}/milestones/0"
    query = {key: value for key, value in params.items() if value is not None}
    signature = sign_typed(
        client, f"{base}/decision-message", query, officer_user, accounts["officer"]
    )
    body = {**query, "signature": signature}
    return client.post(f"{base}/decision", json=body, headers=officer_user.headers)


def approve_by_vote(client, db, w3, relayer, indexer, voters):
    ballot = db.scalars(select(Ballot)).one()
    for person, key in voters:
        path = f"/v1/ballots/0x{ballot.id.hex()}"
        params = {"holder": key.address, "approve": True}
        signature = sign_typed(client, f"{path}/vote-message", params, person, key)
        body = {"holder": key.address, "approve": True, "signature": signature}
        ok(client.post(f"{path}/votes", json=body, headers=person.headers), 202)
    run(relayer, indexer, w3)
    warp(w3, 72 * 3600 + 60)
    close_due_ballots(db, chain_now(w3))
    db.commit()
    run(relayer, indexer, w3)


def test_pay_on_proof_charges_once_per_approval_and_funds_the_next_milestone(
    client,
    db,
    chain_app,
    chain,
    w3,
    accounts,
    sessions,
    mocks,
    login,
    admin,
    charity_admin,
    verified_charity,
    verified_contractor,
    field_evidence,
):
    officer_user = reviewing_officer(client, admin, login)
    project_id, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    backer, pledger = login("+994 55 400 00 01"), login("+994 55 400 00 02")
    fund(client, db, mocks, [(backer, accounts["donor1"], 100_000, project_id)])
    run(relayer, indexer, w3)
    body = {
        "amount_qapik": 2_000,
        "holder": accounts["donor2"].address,
        "card_number": "4242424242424242",
    }
    pledge = ok(
        client.post(f"/v1/projects/{project_id}/pledges", json=body, headers=pledger.headers), 201
    )
    assert pledge["status"] == "active" and pledge["card_last4"] == "4242"

    field_evidence.anchor(db, project_id)
    run(relayer, indexer, w3)
    funded = milestone_row(db, project_id, 0).funded_qapik
    ok(
        decide(
            client,
            officer_user,
            accounts,
            project_id,
            approve=True,
            invoice_hash=INVOICE,
            amount_qapik=funded,
        ),
        202,
    )
    run(relayer, indexer, w3)
    approve_by_vote(client, db, w3, relayer, indexer, [(backer, accounts["donor1"])])
    assert milestone_row(db, project_id, 0).status == "approved"

    charge = db.scalars(select(PledgeCharge)).one()
    assert charge.milestone_index == 0 and charge.status == "pending"
    assert charge_pledges(db, mocks["psp"]) == 1
    db.commit()
    assert charge_pledges(db, mocks["psp"]) == 0  # one approval, one charge
    deliver_webhooks(client, db, mocks["settings"])

    donation = db.scalars(select(Donation).where(Donation.kind == "pay_on_proof")).one()
    approval_tx = db.get(PledgeCharge, charge.id).approval_tx
    assert donation.trigger == approval_tx and donation.amount_qapik == 2_000
    parts = db.scalars(select(Allocation).where(Allocation.donation_id == donation.id)).all()
    assert {p.milestone_index for p in parts} <= {1, 2}  # the next milestones, not the approved one
    assert all(p.trigger == approval_tx for p in parts)
    build_batch(db, mocks["bank"])
    db.commit()
    run(relayer, indexer, w3)
    db.expire_all()
    assert db.get(Donation, donation.id).status == "in_escrow"


def test_failed_checks_need_an_override_and_a_rejection_needs_a_reason(
    client,
    db,
    chain_app,
    chain,
    w3,
    accounts,
    sessions,
    mocks,
    login,
    admin,
    charity_admin,
    verified_charity,
    verified_contractor,
    field_evidence,
):
    officer_user = reviewing_officer(client, admin, login)
    project_id, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    donor = login("+994 55 500 00 01")
    fund(client, db, mocks, [(donor, accounts["donor1"], 50_000, project_id)])
    run(relayer, indexer, w3)
    field_evidence.anchor(db, project_id, passed=False)
    run(relayer, indexer, w3)
    funded = milestone_row(db, project_id, 0).funded_qapik
    base = f"/v1/projects/{project_id}/milestones/0/decision-message"
    error(
        client.get(
            base,
            params={"approve": True, "invoice_hash": INVOICE, "amount_qapik": funded},
            headers=officer_user.headers,
        ),
        422,
        "override_required",
    )
    error(
        client.get(base, params={"approve": False}, headers=officer_user.headers),
        422,
        "reason_required",
    )

    reason = "The fence check failed because GPS drifted; I visited the site on 2027-03-20."
    ok(
        decide(
            client,
            officer_user,
            accounts,
            project_id,
            approve=True,
            invoice_hash=INVOICE,
            amount_qapik=funded,
            override_checks=True,
            reason=reason,
        ),
        202,
    )
    run(relayer, indexer, w3)
    milestone = milestone_row(db, project_id, 0)
    assert milestone.status == "voting"
    escrow = chain.contracts.escrow(db.get(Project, uuid.UUID(project_id)).escrow_address)
    assert escrow.functions.milestone(0).call()[9] == 4  # Status.Voting on-chain too


def test_a_payout_the_bank_cannot_make_comes_back_and_waits_for_a_person(
    client,
    db,
    chain_app,
    chain,
    w3,
    accounts,
    sessions,
    mocks,
    login,
    admin,
    charity_admin,
    verified_charity,
    verified_contractor,
    field_evidence,
):
    officer_user = reviewing_officer(client, admin, login)
    project_id, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    donor = login("+994 55 600 00 01")
    fund(client, db, mocks, [(donor, accounts["donor1"], 50_000, project_id)])
    run(relayer, indexer, w3)
    field_evidence.anchor(db, project_id)
    run(relayer, indexer, w3)
    funded = milestone_row(db, project_id, 0).funded_qapik
    ok(
        decide(
            client,
            officer_user,
            accounts,
            project_id,
            approve=True,
            invoice_hash=INVOICE,
            amount_qapik=funded,
        ),
        202,
    )
    run(relayer, indexer, w3)
    approve_by_vote(client, db, w3, relayer, indexer, [(donor, accounts["donor1"])])
    w3.provider.make_request("anvil_mine", ["0x3"])
    reconcile(db, chain.contracts, mocks["bank"])
    db.commit()
    run(relayer, indexer, w3)
    release_approved(db, chain.contracts)
    db.commit()
    run(relayer, indexer, w3)

    # The contractor's account was closed since it was verified.
    mocks["settings"].mockbank_closed_accounts.append(normalize_az_iban(CONTRACTOR["iban"]))
    try:
        execute_payouts(db, mocks["bank"], chain.contracts)
        db.commit()
        run(relayer, indexer, w3)
    finally:
        mocks["settings"].mockbank_closed_accounts.clear()
    db.expire_all()
    assert db.scalars(select(Payout)).one().status == "returned"
    assert db.scalars(select(Release)).one().status == "returned"
    assert milestone_row(db, project_id, 0).status == "approved"
    assert release_approved(db, chain.contracts) == 0  # not again on its own
    alert = db.scalars(select(Alert).where(Alert.kind == "payout_returned")).one()
    assert "back in escrow" in alert.message


def test_a_missed_evidence_deadline_stops_the_project(
    client,
    db,
    chain_app,
    chain,
    w3,
    accounts,
    sessions,
    mocks,
    login,
    charity_admin,
    verified_charity,
    verified_contractor,
    officer,
):
    project_id, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    assert stop_missed_deadlines(db, chain_now(w3)) == 0
    deadline = milestone_row(db, project_id, 0).evidence_deadline
    warp(w3, int(deadline.timestamp() - chain_now(w3).timestamp()) + 3600)
    assert stop_missed_deadlines(db, chain_now(w3)) == 1
    db.commit()

    # Say evidence for milestone 0 had landed just in time, in blocks the indexer had not
    # reached: the stop reverts, and the mirror then shows the milestone checked. That
    # failure must not use up the project's one chance to stop when a later milestone misses
    # its deadline.
    db.execute(
        update(ChainOutbox)
        .where(ChainOutbox.kind == "stop_missed_deadline")
        .values(status=OutboxStatus.FAILED)
    )
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == uuid.UUID(project_id), Milestone.index == 0)
        .values(status="checked")
    )
    db.commit()
    assert stop_missed_deadlines(db, chain_now(w3)) == 0
    deadline = milestone_row(db, project_id, 1).evidence_deadline
    warp(w3, int(deadline.timestamp() - chain_now(w3).timestamp()) + 3600)
    assert stop_missed_deadlines(db, chain_now(w3)) == 1
    db.commit()
    run(relayer, indexer, w3)
    db.expire_all()
    assert db.get(Project, uuid.UUID(project_id)).status == "stopped"
