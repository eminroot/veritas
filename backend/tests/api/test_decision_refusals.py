"""The decision and stop endpoints refuse what the contracts would refuse, with a reason."""

import time

from decisionkit import fund, milestone_row, reviewing_officer, sign_typed
from eth_account import Account
from flowkit import live_example, run
from sqlalchemy import select
from support import error, ok

from veritas.core.hashing import sha256
from veritas.db.models.decisions import Ballot

INVOICE = "0x" + sha256(b"invoice").hex()


def test_refusals(
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
    big, small = login("+994 55 900 00 01"), login("+994 55 900 00 02")
    # 10 AZN pro rata puts about 2 AZN on milestone 0: under the 5 AZN needed to vote on it.
    fund(
        client,
        db,
        mocks,
        [
            (big, accounts["donor1"], 100_000, project_id),
            (small, accounts["donor2"], 1_000, project_id),
        ],
    )
    run(relayer, indexer, w3)

    # Claims open only once the project has stopped or completed.
    base = f"/v1/projects/{project_id}"
    params = {
        "holder": accounts["donor1"].address,
        "action": "refund",
        "deadline": int(time.time()) + 3600,
    }
    signature = sign_typed(client, f"{base}/claim-message", params, big, accounts["donor1"])
    error(
        client.post(f"{base}/claims", json={**params, "signature": signature}, headers=big.headers),
        409,
        "project_running",
    )

    # A withdrawal signed by anyone but the charity key is refused.
    reason = "Moving the work to another charity."
    forged = sign_typed(
        client, f"{base}/withdraw-message", {"reason": reason}, charity_admin, accounts["donor3"]
    )
    error(
        client.post(
            f"{base}/withdraw",
            json={"reason": reason, "signature": forged},
            headers=charity_admin.headers,
        ),
        403,
        "bad_signature",
    )

    field_evidence.anchor(db, project_id)
    run(relayer, indexer, w3)
    funded = milestone_row(db, project_id, 0).funded_qapik
    decision = f"{base}/milestones/0"
    query = {"approve": True, "invoice_hash": INVOICE, "amount_qapik": funded}
    signature = sign_typed(
        client, f"{decision}/decision-message", query, officer_user, accounts["officer"]
    )
    body = {**query, "signature": signature}
    ok(client.post(f"{decision}/decision", json=body, headers=officer_user.headers), 202)
    error(
        client.post(f"{decision}/decision", json=body, headers=officer_user.headers),
        409,
        "already_decided",  # one decision per evidence attempt
    )
    run(relayer, indexer, w3)

    ballot = db.scalars(select(Ballot)).one()
    assert ballot.eligible == 1  # only the big donor has 5 AZN on milestone 0
    path = f"/v1/ballots/0x{ballot.id.hex()}"

    def vote(person, key, holder, approve=True):
        params = {"holder": holder, "approve": approve}
        signature = sign_typed(client, f"{path}/vote-message", params, person, key)
        body = {"holder": holder, "approve": approve, "signature": signature}
        return client.post(f"{path}/votes", json=body, headers=person.headers)

    error(vote(small, accounts["donor2"], accounts["donor2"].address), 422, "not_eligible")
    error(vote(small, Account.create(), accounts["donor1"].address), 403, "bad_signature")
    ok(vote(big, accounts["donor1"], accounts["donor1"].address), 202)
    error(vote(big, accounts["donor1"], accounts["donor1"].address), 409, "already_voted")
