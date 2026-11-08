"""Money at the edges: a project that stops while its donations are on their way, and a
donation bigger than what the project still needs."""

import uuid

from flowkit import another_project_doc, deliver_webhooks, donate, launch_doc, live_example, run
from sqlalchemy import select

from veritas.chain import eip712
from veritas.chain.contracts import send
from veritas.core.hashing import sha256
from veritas.db.models.chain import Alert, ChainOutbox
from veritas.db.models.money import Batch, BatchStatus, Donation
from veritas.mocks.models import MockPayment
from veritas.payments.batches import build_batch, refund_unbatched


def test_a_batch_the_chain_refuses_is_rebuilt_and_stranded_money_goes_back(
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
    stopping, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    donor = login("+994 55 700 00 01")
    donate(client, donor, stopping, accounts["donor1"].address, 10_000)
    deliver_webhooks(client, db, mocks["settings"])
    first = build_batch(db, mocks["bank"])
    db.commit()
    first_root = first.root

    # The charity withdraws straight on-chain before the batch lands, so anchoring fails.
    escrow = chain.contracts.escrow(
        chain.contracts.hub.functions.escrowOf(uuid.UUID(stopping).bytes).call()
    )
    reason = sha256(b"withdrawn")
    signature = eip712.sign(
        accounts["charity"].key,
        chain.domain,
        "Withdraw",
        {"projectId": uuid.UUID(stopping).bytes, "reasonHash": reason},
    )
    charity = accounts["charity"]
    send(
        w3,
        charity,
        escrow.functions.withdraw(reason, signature).build_transaction({"from": charity.address}),
    )
    run(relayer, indexer, w3)
    anchoring = db.scalars(select(ChainOutbox).where(ChainOutbox.kind == "anchor_batch")).one()
    assert anchoring.status == "failed"

    # The next run gives the batch's leaves back; the stopped project's money goes home.
    assert build_batch(db, mocks["bank"]) is None
    db.commit()
    assert db.get(Batch, 1) is None
    assert refund_unbatched(db, mocks["psp"]) == 1
    db.commit()
    db.expire_all()
    donation = db.scalars(select(Donation)).one()
    assert donation.status == "refunded" and donation.refunded_qapik == 10_000
    assert db.scalars(select(MockPayment)).one().refunded_qapik == 10_000
    assert db.scalars(select(Alert).where(Alert.kind == "batch_failed")).one()

    # Batch id 1 was never used on-chain, so the next batch takes it, with the bank's consent.
    other = launch_doc(
        client,
        db,
        charity_admin,
        verified_charity["id"],
        accounts["charity"],
        another_project_doc(),
    )
    run(relayer, indexer, w3)
    donate(client, donor, other, accounts["donor2"].address, 7_000)
    deliver_webhooks(client, db, mocks["settings"])
    second = build_batch(db, mocks["bank"])
    db.commit()
    assert second.id == 1 and second.root != first_root
    run(relayer, indexer, w3)
    db.expire_all()
    assert db.get(Batch, 1).status == BatchStatus.SETTLED


def test_more_than_the_project_needs_is_refunded(
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
    donor = login("+994 55 700 00 02")
    # Two donors raced: this payment passed the check before the other filled the project.
    payment = mocks["psp"].create_payment(
        amount=2_100_000,
        card_number="4242424242424242",
        metadata={
            "project_id": project_id,
            "holder": accounts["donor1"].address,
            "user_id": str(donor.user_id),
        },
        idempotency_key="race",
    )
    deliver_webhooks(client, db, mocks["settings"])
    donation = db.scalars(select(Donation)).one()
    assert donation.amount_qapik == 2_100_000
    assert donation.refunded_qapik == 51_000  # the Passport total is 2 049 000
    assert db.get(MockPayment, payment["id"]).refunded_qapik == 51_000
