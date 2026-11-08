"""Who may sign what, as the escrow sees it: an officer's Safe through ERC-1271, high-s
signatures that the contracts refuse, decisions and votes the chain refused and that can be
signed again, votes while a receipt changes keys, and a stopped project's milestones."""

from decisionkit import fund, milestone_row, reviewing_officer, sign_typed
from eth_account import Account
from eth_utils import keccak
from flowkit import live_example, run
from sqlalchemy import select, update
from support import error, ok

from veritas.core.hashing import sha256
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.models.decisions import Ballot, OfficerDecision, Vote
from veritas.decisions.jobs import chain_now

INVOICE = "0x" + sha256(b"invoice").hex()
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# A stand-in for a Safe: isValidSignature(hash, signature) answers yes for the one digest in
# storage slot 0, whatever the signature bytes, and no for anything else.
SAFE_RUNTIME = (
    "0x60043560005414601a5763ffffffff60e01b60005260206000f35b631626ba7e60e01b60005260206000f3"
)


def digest_of(typed: dict) -> bytes:
    from eth_account.messages import encode_typed_data

    signable = encode_typed_data(full_message=typed)
    return keccak(b"\x19" + signable.version + signable.header + signable.body)


def high_s(signature: str) -> str:
    raw = bytes.fromhex(signature[2:])
    r, s, v = raw[:32], int.from_bytes(raw[32:64], "big"), raw[64]
    return "0x" + (r + (N - s).to_bytes(32, "big") + bytes([55 - v])).hex()


def checked_milestone(
    client, db, chain, w3, accounts, sessions, mocks, login, admin, field_evidence, *fixtures
):
    charity_admin, verified_charity = fixtures
    officer_user = reviewing_officer(client, admin, login)
    project_id, relayer, indexer = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    donor = login("+994 55 500 00 01")
    fund(client, db, mocks, [(donor, accounts["donor1"], 100_000, project_id)])
    run(relayer, indexer, w3)
    field_evidence.anchor(db, project_id)
    run(relayer, indexer, w3)
    assert milestone_row(db, project_id, 0).status == "checked"
    return officer_user, project_id, donor, lambda: run(relayer, indexer, w3)


def approval(project_id, db) -> dict:
    return {
        "approve": True,
        "invoice_hash": INVOICE,
        "amount_qapik": milestone_row(db, project_id, 0).funded_qapik,
    }


def test_an_officers_safe_signs_through_erc1271_and_high_s_is_refused(
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
    officer_user, project_id, _, settle = checked_milestone(
        client,
        db,
        chain,
        w3,
        accounts,
        sessions,
        mocks,
        login,
        admin,
        field_evidence,
        charity_admin,
        verified_charity,
    )
    base = f"/v1/projects/{project_id}/milestones/0"
    params = approval(project_id, db)
    typed = ok(client.get(f"{base}/decision-message", params=params, headers=officer_user.headers))

    # The contracts refuse the high-s twin of a valid signature; so does the API now.
    signature = Account.sign_typed_data(accounts["officer"].key, full_message=typed).signature
    twin = {**params, "signature": high_s(signature.to_0x_hex())}
    error(
        client.post(f"{base}/decision", json=twin, headers=officer_user.headers),
        403,
        "bad_signature",
    )

    # The officer's address becomes a Safe that approved exactly this decision.
    officer = accounts["officer"].address
    w3.provider.make_request("anvil_setCode", [officer, SAFE_RUNTIME])
    w3.provider.make_request("anvil_setStorageAt", [officer, "0x0", "0x" + digest_of(typed).hex()])
    safe_signature = {**params, "signature": "0x" + "00" * 130}  # two owners' worth of bytes
    other = {**params, "amount_qapik": params["amount_qapik"] - 1, "signature": "0x" + "00" * 130}
    error(
        client.post(f"{base}/decision", json=other, headers=officer_user.headers),
        403,
        "bad_signature",
    )
    ok(client.post(f"{base}/decision", json=safe_signature, headers=officer_user.headers), 202)
    settle()
    assert milestone_row(db, project_id, 0).status == "voting"


def test_refused_decisions_and_votes_can_be_signed_again_and_votes_wait_for_a_key_move(
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
    officer_user, project_id, donor, settle = checked_milestone(
        client,
        db,
        chain,
        w3,
        accounts,
        sessions,
        mocks,
        login,
        admin,
        field_evidence,
        charity_admin,
        verified_charity,
    )
    base = f"/v1/projects/{project_id}/milestones/0"
    params = approval(project_id, db)
    signature = sign_typed(
        client, f"{base}/decision-message", params, officer_user, accounts["officer"]
    )
    body = {**params, "signature": signature}
    ok(client.post(f"{base}/decision", json=body, headers=officer_user.headers), 202)
    error(
        client.post(f"{base}/decision", json=body, headers=officer_user.headers),
        409,
        "already_decided",
    )
    # Say the chain refused it (the relayer key was being replaced, say): it never counted.
    db.execute(
        update(ChainOutbox)
        .where(ChainOutbox.kind == "officer_decision")
        .values(status=OutboxStatus.FAILED)
    )
    db.commit()
    ok(client.post(f"{base}/decision", json=body, headers=officer_user.headers), 202)
    db.expire_all()
    assert len(db.scalars(select(OfficerDecision)).all()) == 2
    assert db.scalars(select(OfficerDecision.failed_at.is_not(None))).all().count(True) == 1
    settle()
    assert milestone_row(db, project_id, 0).status == "voting"

    # The donor's receipt is moving to a new phone's key: no vote until it has moved.
    ballot = db.scalars(select(Ballot)).one()
    path = f"/v1/ballots/0x{ballot.id.hex()}"
    old, new = accounts["donor1"], Account.create()
    receipt = f"/v1/projects/{project_id}/receipts/{old.address}"
    move = {"new_key": new.address, "deadline": int(chain_now(w3).timestamp()) + 3600}
    moved = sign_typed(client, f"{receipt}/rotation-message", move, donor, old)
    ok(
        client.post(
            f"{receipt}/rotation", json={**move, "signature": moved}, headers=donor.headers
        ),
        202,
    )
    vote = {"holder": old.address, "approve": True}
    by_old = sign_typed(client, f"{path}/vote-message", vote, donor, old)
    error(
        client.post(f"{path}/votes", json={**vote, "signature": by_old}, headers=donor.headers),
        409,
        "key_moving",
    )
    settle()
    error(
        client.post(f"{path}/votes", json={**vote, "signature": by_old}, headers=donor.headers),
        403,
        "bad_signature",
    )
    by_new = sign_typed(client, f"{path}/vote-message", vote, donor, new)
    ok(client.post(f"{path}/votes", json={**vote, "signature": by_new}, headers=donor.headers), 202)
    error(
        client.post(f"{path}/votes", json={**vote, "signature": by_new}, headers=donor.headers),
        409,
        "already_voted",
    )
    # Say the chain refused that vote: the donor signs again and it counts.
    db.execute(
        update(ChainOutbox)
        .where(ChainOutbox.kind == "cast_vote")
        .values(status=OutboxStatus.FAILED)
    )
    db.commit()
    ok(client.post(f"{path}/votes", json={**vote, "signature": by_new}, headers=donor.headers), 202)
    settle()
    db.expire_all()
    assert sorted(v.status for v in db.scalars(select(Vote))) == ["counted", "failed"]
    assert db.get(Ballot, ballot.id).yes == 1


def test_a_stopped_projects_milestones_take_no_decision(
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
    officer_user, project_id, _, settle = checked_milestone(
        client,
        db,
        chain,
        w3,
        accounts,
        sessions,
        mocks,
        login,
        admin,
        field_evidence,
        charity_admin,
        verified_charity,
    )
    assert [
        item["project_id"]
        for item in ok(client.get("/v1/officer/queue", headers=officer_user.headers))
    ] == [project_id]
    reason = "The state rebuilt the school roof this spring."
    withdraw = f"/v1/projects/{project_id}/withdraw"
    signature = sign_typed(
        client,
        f"/v1/projects/{project_id}/withdraw-message",
        {"reason": reason},
        charity_admin,
        accounts["charity"],
    )
    ok(
        client.post(
            withdraw, json={"reason": reason, "signature": signature}, headers=charity_admin.headers
        ),
        202,
    )
    settle()

    assert ok(client.get("/v1/officer/queue", headers=officer_user.headers)) == []
    base = f"/v1/projects/{project_id}/milestones/0"
    error(
        client.get(
            f"{base}/decision-message",
            params=approval(project_id, db),
            headers=officer_user.headers,
        ),
        409,
        "project_not_live",
    )


def test_a_wallet_that_writes_while_it_answers_is_refused_as_the_chain_refuses_it(w3):
    """OpenZeppelin asks a contract signer with STATICCALL; one that writes storage while
    answering reverts there, so the API refuses it too."""
    from veritas.chain import eip712
    from veritas.chain.signatures import signed_by

    domain = eip712.Domain(31337, "0x" + "11" * 20)
    message = {"projectId": bytes(16), "reasonHash": bytes(32)}
    writes = Account.create().address
    # SSTORE(0, 1), then answer yes.
    w3.provider.make_request(
        "anvil_setCode", [writes, "0x6001600055631626ba7e60e01b60005260206000f3"]
    )
    assert not signed_by(w3, domain, "Withdraw", message, bytes(65), writes)
    reads = Account.create().address
    w3.provider.make_request("anvil_setCode", [reads, "0x631626ba7e60e01b60005260206000f3"])
    assert signed_by(w3, domain, "Withdraw", message, bytes(65), reads)
