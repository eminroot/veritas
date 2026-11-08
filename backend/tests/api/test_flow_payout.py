"""Phase 8 end to end: from card donations to the contractor's payout.

Donations go into escrow, evidence and the check report are anchored, the officer signs an
approval, the donors vote with their own keys, the milestone is released against the
invoice, MockBank pays the contractor's verified account and its confirmation burns the vAZN.
"""

import uuid

from decisionkit import fund, milestone_row, reviewing_officer, sign_typed, warp
from flowkit import live_example, run
from sqlalchemy import select
from support import CONTRACTOR, error, ok

from veritas.core.hashing import sha256
from veritas.core.identifiers import normalize_az_iban
from veritas.db.models.chain import Alert
from veritas.db.models.decisions import Ballot, Payout, Release, Vote
from veritas.decisions.jobs import chain_now
from veritas.decisions.payouts import execute_payouts, release_approved
from veritas.decisions.voting import close_due_ballots
from veritas.mocks.models import MockBankPayment
from veritas.payments.reconcile import reconcile

INVOICE = sha256(b"invoice DT-2027-014 from Dag Tikinti MMC")


def test_from_donations_to_the_contractors_payout(
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
    donor1, donor2 = login("+994 55 100 00 01"), login("+994 55 100 00 02")
    fund(
        client,
        db,
        mocks,
        [
            (donor1, accounts["donor1"], 150_000, project_id),
            (donor2, accounts["donor2"], 100_000, project_id),
        ],
    )
    run(relayer, indexer, w3)
    funded = milestone_row(db, project_id, 0).funded_qapik
    assert funded > 0

    # The evidence pipeline's output: bundle and report anchored, every hard check passed.
    bundle, report = field_evidence.anchor(db, project_id)
    run(relayer, indexer, w3)
    checked = milestone_row(db, project_id, 0)
    assert checked.status == "checked" and checked.bundle_hash == bundle

    queue = ok(client.get("/v1/officer/queue", headers=officer_user.headers))
    assert [(item["project_id"], item["milestone"]) for item in queue] == [(project_id, 0)]

    # The officer approves the invoice for what the milestone raised, signing on their phone.
    base = f"/v1/projects/{project_id}/milestones/0"
    params = {"approve": True, "invoice_hash": "0x" + INVOICE.hex(), "amount_qapik": funded}
    error(
        client.get(f"{base}/decision-message", params=params, headers=donor1.headers),
        403,
        "not_the_officer",
    )
    signature = sign_typed(
        client, f"{base}/decision-message", params, officer_user, accounts["officer"]
    )
    body = {
        "approve": True,
        "invoice_hash": params["invoice_hash"],
        "amount_qapik": funded,
        "signature": signature,
    }
    ok(client.post(f"{base}/decision", json=body, headers=officer_user.headers), 202)
    run(relayer, indexer, w3)
    ballot = db.scalars(select(Ballot)).one()
    assert milestone_row(db, project_id, 0).status == "voting"
    assert ballot.eligible == 2

    # Both donors vote with their own per-project keys.
    for person, key in ((donor1, accounts["donor1"]), (donor2, accounts["donor2"])):
        path = f"/v1/ballots/0x{ballot.id.hex()}"
        vote_params = {"holder": key.address, "approve": True}
        signature = sign_typed(client, f"{path}/vote-message", vote_params, person, key)
        body = {"holder": key.address, "approve": True, "signature": signature}
        ok(client.post(f"{path}/votes", json=body, headers=person.headers), 202)
    run(relayer, indexer, w3)
    assert {v.status for v in db.scalars(select(Vote))} == {"counted"}

    warp(w3, 72 * 3600 + 60)
    assert close_due_ballots(db, chain_now(w3)) == 1
    db.commit()
    run(relayer, indexer, w3)
    db.expire_all()
    assert db.scalars(select(Ballot)).one().passed
    assert milestone_row(db, project_id, 0).status == "approved"

    # A fresh balanced attestation, then the release and the bank's payout.
    mine_and_reconcile(db, chain, mocks, w3)
    run(relayer, indexer, w3)
    assert release_approved(db, chain.contracts) == 1
    db.commit()
    run(relayer, indexer, w3)
    assert milestone_row(db, project_id, 0).status == "released"
    assert execute_payouts(db, mocks["bank"], chain.contracts) == 1
    db.commit()
    supply_before = chain.contracts.vazn.functions.totalSupply().call()
    run(relayer, indexer, w3)

    db.expire_all()
    assert milestone_row(db, project_id, 0).status == "paid"
    assert db.scalars(select(Release)).one().status == "paid"
    payout = db.scalars(select(Payout)).one()
    assert payout.status == "confirmed" and payout.amount_qapik == funded
    paid = db.scalars(select(MockBankPayment)).one()
    assert paid.counterparty == normalize_az_iban(CONTRACTOR["iban"])
    assert chain.contracts.vazn.functions.totalSupply().call() == supply_before - funded
    escrow = chain.contracts.escrow(
        chain.contracts.hub.functions.escrowOf(uuid.UUID(project_id).bytes).call()
    )
    assert escrow.functions.milestone(0).call()[9] == 7  # Status.Paid
    # Every anchored hash is accounted for by a signed bundle and its report here.
    assert db.scalars(select(Alert.kind).where(Alert.severity == "critical")).all() == []


def mine_and_reconcile(db, chain, mocks, w3):
    w3.provider.make_request("anvil_mine", ["0x3"])
    reconciliation = reconcile(db, chain.contracts, mocks["bank"])
    db.commit()
    assert reconciliation is not None and reconciliation.balanced
    return reconciliation
