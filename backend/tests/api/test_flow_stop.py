"""Phase 8 end to end: a stopped project returns or moves every donor's money.

The charity withdraws. One donor takes a refund to their card, one redirects to another live
project under a new key for it, and one does nothing and gets the Passport's default, a
refund, once the choice window closes. Afterwards the stopped escrow is empty, the cards got
their money back, the redirected money is in escrow in the other project, and the bank, the
chain and our books still agree.

Along the way: the charity changed its key after launch, but the escrow only takes the key
it was launched with; nobody but the donor's own account can send their choice; a choice the
chain refused can be sent again; and the receipt the redirect brings belongs to the donor.
"""

import time
import uuid

from decisionkit import fund, warp
from eth_account import Account
from flowkit import another_project_doc, launch_doc, live_example, run, set_charity_key
from sqlalchemy import select, update
from support import error, ok

from veritas.db.models import Project
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.models.decisions import Claim, Payout
from veritas.db.models.money import Allocation, Donation
from veritas.decisions.jobs import chain_now
from veritas.decisions.payouts import execute_payouts
from veritas.decisions.stops import apply_defaults
from veritas.mocks.models import MockPayment
from veritas.payments.batches import build_batch
from veritas.payments.reconcile import reconcile


def sign(client, path, params, person, key) -> str:
    typed = ok(client.get(path, params=params, headers=person.headers))
    return Account.sign_typed_data(key.key, full_message=typed).signature.to_0x_hex()


def escrow_balance(chain, project_id) -> int:
    escrow = chain.contracts.hub.functions.escrowOf(uuid.UUID(project_id).bytes).call()
    return chain.contracts.vazn.functions.balanceOf(escrow).call()


def test_a_stopped_project_returns_or_moves_every_donors_money(
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
    stopped, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    other = launch_doc(
        client,
        db,
        charity_admin,
        verified_charity["id"],
        accounts["charity"],
        another_project_doc(),
    )
    run(relayer, indexer, w3)
    assert db.get(Project, uuid.UUID(other)).status == "live"

    refunder, mover, silent = (login(f"+994 55 300 00 0{n}") for n in (1, 2, 3))
    fund(
        client,
        db,
        mocks,
        [
            (refunder, accounts["donor1"], 50_000, stopped),
            (mover, accounts["donor2"], 40_000, stopped),
            (silent, accounts["donor3"], 30_000, stopped),
        ],
    )
    run(relayer, indexer, w3)
    assert escrow_balance(chain, stopped) == 120_000
    # Holder keys are public once minted. A stranger cannot take one in the project a default
    # redirect would move its donor's money to.
    stranger = login("+994 55 300 00 09")
    taken = {"amount_qapik": 100, "holder": accounts["donor3"].address, "card_number": "4242" * 4}
    error(
        client.post(f"/v1/projects/{other}/donations", json=taken, headers=stranger.headers),
        409,
        "holder_taken",
    )

    # The charity has a new phone and key by now, but its escrows keep the launch key.
    replaced = Account.create()
    set_charity_key(client, verified_charity["id"], charity_admin, replaced)
    run(relayer, indexer, w3)
    base = f"/v1/projects/{stopped}"
    reason = "The state rebuilt the school roof this spring."
    signature = sign(
        client, f"{base}/withdraw-message", {"reason": reason}, charity_admin, replaced
    )
    refused = error(
        client.post(
            f"{base}/withdraw",
            json={"reason": reason, "signature": signature},
            headers=charity_admin.headers,
        ),
        403,
        "bad_signature",
    )
    assert accounts["charity"].address in refused["message"]

    # The charity withdraws, signed by the key the project was launched with.
    signature = sign(
        client, f"{base}/withdraw-message", {"reason": reason}, charity_admin, accounts["charity"]
    )
    ok(
        client.post(
            f"{base}/withdraw",
            json={"reason": reason, "signature": signature},
            headers=charity_admin.headers,
        ),
        202,
    )
    run(relayer, indexer, w3)
    assert db.get(Project, uuid.UUID(stopped)).status == "stopped"

    # One donor takes a refund to their card.
    deadline = int(time.time()) + 3600 * 24 * 60
    params = {"holder": accounts["donor1"].address, "action": "refund", "deadline": deadline}
    signature = sign(client, f"{base}/claim-message", params, refunder, accounts["donor1"])
    body = {**params, "signature": signature}
    error(client.post(f"{base}/claims", json=body, headers=mover.headers), 403, "not_the_donor")
    ok(client.post(f"{base}/claims", json=body, headers=refunder.headers), 202)
    # Say the chain refuses it (a payout in flight, say). The same choice can be sent again,
    # and goes out as a new call instead of being swallowed by the failed one.
    db.execute(
        update(ChainOutbox).where(ChainOutbox.kind == "claim").values(status=OutboxStatus.FAILED)
    )
    db.commit()
    ok(client.post(f"{base}/claims", json=body, headers=refunder.headers), 202)
    db.expire_all()
    calls = db.scalars(select(ChainOutbox).where(ChainOutbox.kind == "claim")).all()
    assert sorted(call.status for call in calls) == ["failed", "pending"]

    # One moves their money to the other project, under a new key for it.
    new_key = Account.create()
    params = {
        "holder": accounts["donor2"].address,
        "action": "redirect",
        "target_project_id": other,
        "deadline": deadline,
    }
    signature = sign(client, f"{base}/claim-message", params, mover, accounts["donor2"])
    body = {**params, "signature": signature, "new_holder": new_key.address}
    ok(client.post(f"{base}/claims", json=body, headers=mover.headers), 202)
    run(relayer, indexer, w3)

    assert execute_payouts(db, mocks["bank"], chain.contracts) == 1
    db.commit()
    build_batch(db, mocks["bank"])  # anchors the redirected leaves in the other project
    db.commit()
    run(relayer, indexer, w3)

    # The third did nothing. After the choice window the Passport's default, a refund, applies.
    warp(w3, 30 * 24 * 3600 + 60)
    assert apply_defaults(db, chain.contracts, chain_now(w3)) == 1
    db.commit()
    run(relayer, indexer, w3)
    assert execute_payouts(db, mocks["bank"], chain.contracts) == 1
    db.commit()
    run(relayer, indexer, w3)

    db.expire_all()
    assert escrow_balance(chain, stopped) == 0
    assert escrow_balance(chain, other) == 40_000
    statuses = {
        a.status
        for a in db.scalars(select(Allocation).where(Allocation.project_id == uuid.UUID(stopped)))
    }
    assert statuses == {"claimed"}
    assert db.scalars(select(Claim.status).where(Claim.amount_qapik.is_(None))).all() == ["failed"]
    claims = db.scalars(select(Claim).where(Claim.status == "executed")).all()
    assert sorted((c.action, c.by_default, c.amount_qapik) for c in claims) == [
        ("redirect", False, 40_000),
        ("refund", False, 50_000),
        ("refund", True, 30_000),
    ]
    assert {p.status for p in db.scalars(select(Payout))} == {"confirmed"}

    refunds = {
        db.scalars(select(Donation).where(Donation.provider_payment_id == p.id)).one().holder: (
            p.refunded_qapik
        )
        for p in db.scalars(select(MockPayment))
    }
    assert refunds == {
        accounts["donor1"].address: 50_000,
        accounts["donor2"].address: 0,
        accounts["donor3"].address: 30_000,
    }

    moved = db.scalars(select(Donation).where(Donation.kind == "redirect")).one()
    assert moved.project_id == uuid.UUID(other) and moved.holder == new_key.address
    assert moved.status == "in_escrow" and moved.amount_qapik == 40_000
    # The receipt the redirect brought is the donor's: listed, and theirs to recover.
    assert moved.user_id == mover.user_id
    listed = ok(client.get("/v1/receipts", headers=mover.headers))
    assert {(r["project_id"], r["holder"]) for r in listed} == {
        (stopped, accounts["donor2"].address),
        (other, new_key.address),
    }

    w3.provider.make_request("anvil_mine", ["0x3"])
    reconciliation = reconcile(db, chain.contracts, mocks["bank"])
    db.commit()
    assert reconciliation.balanced
    assert reconciliation.chain_supply_qapik == 40_000
