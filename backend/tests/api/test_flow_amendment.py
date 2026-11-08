"""Amending a live Passport: the charity proposes a new contractor, the donors vote for it,
and only then does version 2 become the Passport, byte for byte what they voted on."""

import copy
import uuid

from decisionkit import fund, sign_typed, warp
from eth_account import Account
from flowkit import example_doc, live_example, run
from sqlalchemy import select
from support import CONTRACTOR, error, ok

from veritas.chain.project import contractor_hash
from veritas.core.hashing import sha256
from veritas.db.models import PassportVersion
from veritas.db.models.decisions import Ballot
from veritas.decisions.jobs import chain_now
from veritas.decisions.voting import close_due_ballots

NEW_VOEN = "1300000039"


def az_iban(bank: str, account: str) -> str:
    """A valid Azerbaijani IBAN for the bank code and the 20-character account."""
    rearranged = f"{bank}{account}AZ00"
    digits = int("".join(str(int(char, 36)) for char in rearranged))
    return f"AZ{98 - digits % 97:02d}{bank}{account}"


def test_a_new_contractor_needs_the_donors_vote(
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
    officer,
):
    project_id, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    donor = login("+994 55 950 00 01")
    fund(client, db, mocks, [(donor, accounts["donor1"], 60_000, project_id)])
    run(relayer, indexer, w3)

    body = {
        **CONTRACTOR,
        "legal_name": "Yeni Tikinti MMC",
        "voen": NEW_VOEN,
        "iban": az_iban("NABZ", "00000000137010002222"),
        "charity_id": verified_charity["id"],
    }
    replacement = ok(client.post("/v1/contractors", json=body, headers=charity_admin.headers), 201)
    ok(client.post(f"/v1/contractors/{replacement['id']}/verify", json={}, headers=admin.headers))

    base = f"/v1/projects/{project_id}"
    version2 = example_doc()
    version2["version"] = 2
    version2["contractor"] = {"legal_name": "Yeni Tikinti MMC", "voen": NEW_VOEN}

    # Amounts and rules are the escrow's; an amendment cannot touch them.
    greedy = copy.deepcopy(version2)
    greedy["decision"]["min_turnout_bps"] = 100
    ok(client.put(f"{base}/passport", json=greedy, headers=charity_admin.headers))
    error(
        client.get(f"{base}/amendment-message", headers=charity_admin.headers),
        422,
        "amendment_changes_rules",
    )

    ok(client.put(f"{base}/passport", json=version2, headers=charity_admin.headers))
    signature = sign_typed(
        client, f"{base}/amendment-message", {}, charity_admin, accounts["charity"]
    )
    forged = sign_typed(client, f"{base}/amendment-message", {}, charity_admin, Account.create())
    error(
        client.post(
            f"{base}/amendment", json={"charity_signature": forged}, headers=charity_admin.headers
        ),
        403,
        "bad_signature",
    )
    ok(
        client.post(
            f"{base}/amendment",
            json={"charity_signature": signature},
            headers=charity_admin.headers,
        ),
        202,
    )
    error(
        client.put(f"{base}/passport", json=version2, headers=charity_admin.headers),
        409,
        "amendment_pending",
    )
    run(relayer, indexer, w3)

    ballot = db.scalars(select(Ballot)).one()
    assert ballot.kind == "amendment" and ballot.eligible == 1
    path = f"/v1/ballots/0x{ballot.id.hex()}"
    params = {"holder": accounts["donor1"].address, "approve": True}
    vote = sign_typed(client, f"{path}/vote-message", params, donor, accounts["donor1"])
    ok(client.post(f"{path}/votes", json={**params, "signature": vote}, headers=donor.headers), 202)
    run(relayer, indexer, w3)
    # Until the vote passes, version 1 is the Passport and the old contractor is paid.
    assert chain.contracts.registry.functions.versionOf(uuid.UUID(project_id).bytes).call() == 1

    warp(w3, 72 * 3600 + 60)
    close_due_ballots(db, chain_now(w3))
    db.commit()
    run(relayer, indexer, w3)

    db.expire_all()
    registry = chain.contracts.registry
    entry = registry.functions.current(uuid.UUID(project_id).bytes).call()
    assert entry[0] == 2 and entry[2] == contractor_hash(NEW_VOEN)
    versions = {
        v.version: v.status
        for v in db.scalars(
            select(PassportVersion).where(PassportVersion.project_id == uuid.UUID(project_id))
        )
    }
    assert versions == {1: "superseded", 2: "published"}
    published = client.get(f"{base}/passports/2")
    assert sha256(published.content) == entry[1]
