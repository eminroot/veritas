"""Phase 5 end to end: a demo card payment becomes an "in escrow" receipt whose Merkle proof
verifies on-chain, and the daily reconciliation keeps releases open or freezes them."""

import uuid

from flowkit import deliver_webhooks, donate, leaf_values, live_example, run
from sqlalchemy import select
from support import ok

from veritas.chain.receipts import receipt_id
from veritas.db.models.chain import Alert
from veritas.db.models.money import Batch, BatchStatus, Donation, Receipt
from veritas.mocks.models import MockBankPayment, MockWebhook
from veritas.payments.batches import build_batch
from veritas.payments.reconcile import reconcile


def test_a_card_payment_becomes_an_in_escrow_receipt(
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
    donor = login("+994 55 222 22 22")
    holder = accounts["donor1"].address
    payment = donate(client, donor, project_id, holder, 15_000)
    assert payment["status"] == "succeeded"

    responses = deliver_webhooks(client, db, mocks["settings"])
    assert [r.status_code for r in responses] == [200]
    donation_id = responses[0].json()["donation_id"]
    received = ok(client.get(f"/v1/donations/{donation_id}", headers=donor.headers))
    assert received["status"] == "received"
    # 150 AZN pro rata over the 4 200, 13 830 and 2 460 AZN the milestones still need.
    assert [a["amount_qapik"] for a in received["allocations"]] == [3075, 10124, 1801]

    batch = build_batch(db, mocks["bank"])
    db.commit()
    assert (batch.id, batch.leaf_count, batch.total_qapik) == (1, 3, 15_000)
    run(relayer, indexer, w3)

    db.expire_all()
    assert db.get(Batch, 1).status == BatchStatus.SETTLED
    escrowed = ok(client.get(f"/v1/donations/{donation_id}", headers=donor.headers))
    assert escrowed["status"] == "in_escrow"
    ledger = chain.contracts.ledger
    for allocation in escrowed["allocations"]:
        assert allocation["status"] == "in_escrow"
        assert allocation["anchored_tx"]
        proof = [bytes.fromhex(node[2:]) for node in allocation["proof"]]
        values = leaf_values(allocation["leaf"])
        on_chain = ledger.functions.verifyLeaf(allocation["batch_id"], values, proof).call()
        assert "0x" + on_chain.hex() == allocation["leaf_hash"]

    # The donor got their locked receipt token, and vAZN backs the escrow exactly.
    token = receipt_id(uuid.UUID(project_id), holder)
    assert chain.contracts.receipts.functions.ownerOf(token).call() == holder
    assert db.scalars(select(Receipt)).one().status == "minted"
    escrow = chain.contracts.hub.functions.escrowOf(uuid.UUID(project_id).bytes).call()
    assert chain.contracts.vazn.functions.balanceOf(escrow).call() == 15_000

    # The same webhook delivered again is still one donation.
    for webhook in db.scalars(select(MockWebhook)):
        webhook.delivered_at = None
    db.commit()
    again = deliver_webhooks(client, db, mocks["settings"])
    assert again[0].json()["donation_id"] == donation_id
    assert len(db.scalars(select(Donation)).all()) == 1

    # The bank's daily balance matches the chain and our books: releases may go ahead.
    w3.provider.make_request("anvil_mine", ["0x3"])
    reconciliation = reconcile(db, chain.contracts, mocks["bank"])
    db.commit()
    assert reconciliation.balanced
    assert reconciliation.chain_supply_qapik == reconciliation.bank_balance_qapik == 15_000
    run(relayer, indexer, w3)
    assert chain.contracts.hub.functions.releasesAllowed().call()


def test_a_declined_card_makes_no_donation(
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
    project_id, *_ = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    donor = login("+994 55 222 22 23")
    holder = accounts["donor1"].address
    payment = donate(client, donor, project_id, holder, 5000, "4000000000000002")
    assert payment["status"] == "failed"
    deliver_webhooks(client, db, mocks["settings"])
    assert db.scalars(select(Donation)).all() == []


def test_a_mismatch_freezes_releases(
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
    donor = login("+994 55 222 22 24")
    donate(client, donor, project_id, accounts["donor1"].address, 10_000)
    deliver_webhooks(client, db, mocks["settings"])
    build_batch(db, mocks["bank"])
    db.commit()
    run(relayer, indexer, w3)

    # Money left the escrow account with no confirmation on-chain.
    db.add(
        MockBankPayment(
            instruction_id=999,
            kind="payout",
            amount_qapik=2500,
            status="paid",
            counterparty="AZ00UNKNOWN",
            payment_ref=b"\x01" * 32,
            signature=b"\x00",
        )
    )
    db.commit()
    w3.provider.make_request("anvil_mine", ["0x3"])
    reconciliation = reconcile(db, chain.contracts, mocks["bank"])
    db.commit()
    assert not reconciliation.balanced
    assert reconciliation.bank_balance_qapik == 7500
    run(relayer, indexer, w3)
    assert not chain.contracts.hub.functions.releasesAllowed().call()
    alert = db.scalars(select(Alert).where(Alert.kind == "reconciliation_mismatch")).one()
    assert alert.severity == "critical"
