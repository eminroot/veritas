"""A donor moves a receipt to a new key: at once with the old phone, or, when the phone is
lost, after 48 hours and a card the account paid with, while the old key can still refuse."""

import uuid
from datetime import timedelta

import pytest
from decisionkit import fund, sign_typed, warp
from eth_account import Account
from flowkit import live_example, run
from sqlalchemy import select, update
from support import error, ok

from veritas.db.models import User
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.models.money import Donation, Receipt
from veritas.decisions.jobs import chain_now
from veritas.decisions.recovery import finish_rotations

CARD = "4242"  # flowkit.donate pays with 4242 4242 4242 4242
PHONE = "+994 55 960 00 01"


@pytest.fixture
def funded(
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
    donor = login(PHONE)
    fund(client, db, mocks, [(donor, accounts["donor1"], 60_000, project_id)])
    run(relayer, indexer, w3)
    base = f"/v1/projects/{project_id}/receipts/{accounts['donor1'].address}"
    return project_id, donor, base, lambda: run(relayer, indexer, w3)


def receipt_row(db, project_id, holder) -> Receipt:
    db.expire_all()
    return db.scalars(
        select(Receipt).where(Receipt.project_id == uuid.UUID(project_id), Receipt.holder == holder)
    ).one()


def wrong_answers(db, person) -> int:
    db.expire_all()
    return db.get_one(User, person.user_id).recovery_failures


def controller_on_chain(chain, project_id, holder) -> str:
    receipts = chain.contracts.receipts
    return receipts.functions.controllerOf(uuid.UUID(project_id).bytes, holder).call()


def test_the_old_phone_moves_the_receipt_at_once(client, db, chain, w3, accounts, funded):
    project_id, donor, base, settle = funded
    old, new = accounts["donor1"], Account.create()
    [listed] = ok(client.get("/v1/receipts", headers=donor.headers))
    assert listed["controller"] == old.address and listed["pending_rotation"] is None

    params = {"new_key": new.address, "deadline": int(chain_now(w3).timestamp()) + 3600}
    forged = sign_typed(client, f"{base}/rotation-message", params, donor, new)
    error(
        client.post(
            f"{base}/rotation", json={**params, "signature": forged}, headers=donor.headers
        ),
        403,
        "bad_signature",
    )
    signed = sign_typed(client, f"{base}/rotation-message", params, donor, old)
    body = {**params, "signature": signed}
    ok(client.post(f"{base}/rotation", json=body, headers=donor.headers), 202)
    error(
        client.post(f"{base}/rotation", json=body, headers=donor.headers), 409, "rotation_pending"
    )
    settle()

    assert receipt_row(db, project_id, old.address).controller == new.address
    assert controller_on_chain(chain, project_id, old.address) == new.address
    # The old key signs for nothing now.
    third = {"new_key": Account.create().address, "deadline": params["deadline"]}
    stale = sign_typed(client, f"{base}/rotation-message", third, donor, old)
    error(
        client.post(f"{base}/rotation", json={**third, "signature": stale}, headers=donor.headers),
        403,
        "bad_signature",
    )


def test_a_lost_phone_waits_48_hours_and_the_old_key_can_refuse(
    client, db, chain, w3, accounts, login, funded
):
    project_id, donor, base, settle = funded
    old, new = accounts["donor1"], Account.create()
    asked = {"new_key": new.address, "card_last4": CARD}
    donor = login(PHONE)  # the new phone

    stranger = login("+994 55 960 00 02")
    error(
        client.post(f"{base}/recovery", json=asked, headers=stranger.headers), 403, "not_the_donor"
    )
    wrong = asked | {"card_last4": "1111"}
    refused = error(
        client.post(f"{base}/recovery", json=wrong, headers=donor.headers), 403, "card_mismatch"
    )
    assert "4 tries left" in refused["message"]
    assert wrong_answers(db, donor) == 1

    ok(client.post(f"{base}/recovery", json=asked, headers=donor.headers), 202)
    assert wrong_answers(db, donor) == 0
    error(
        client.post(f"{base}/recovery", json=asked, headers=donor.headers), 409, "rotation_pending"
    )
    settle()
    [listed] = ok(client.get("/v1/receipts", headers=donor.headers))
    assert listed["pending_rotation"]["new_key"] == new.address

    # The phone was not lost after all, or the number was stolen: the old key refuses.
    forged = sign_typed(client, f"{base}/cancel-message", {}, donor, new)
    error(
        client.post(f"{base}/cancel", json={"signature": forged}, headers=donor.headers),
        403,
        "bad_signature",
    )
    refusal = sign_typed(client, f"{base}/cancel-message", {}, donor, old)
    ok(client.post(f"{base}/cancel", json={"signature": refusal}, headers=donor.headers), 202)
    settle()
    [listed] = ok(client.get("/v1/receipts", headers=donor.headers))
    assert listed["pending_rotation"] is None
    error(client.get(f"{base}/cancel-message", headers=donor.headers), 404, "no_pending_rotation")

    # Asked again and not refused: once 48 hours have passed, the move is finished. The
    # refusal of the first request names its readyAt, so it cannot refuse this one.
    ok(client.post(f"{base}/recovery", json=asked, headers=donor.headers), 202)
    settle()
    error(
        client.post(f"{base}/cancel", json={"signature": refusal}, headers=donor.headers),
        403,
        "bad_signature",
    )
    assert finish_rotations(db, chain.contracts, chain_now(w3)) == 0
    warp(w3, 48 * 3600 + 60)
    assert finish_rotations(db, chain.contracts, chain_now(w3)) == 1
    db.commit()
    settle()

    assert controller_on_chain(chain, project_id, old.address) == new.address
    assert receipt_row(db, project_id, old.address).controller == new.address
    [listed] = ok(client.get("/v1/receipts", headers=donor.headers))
    assert listed["controller"] == new.address and listed["pending_rotation"] is None


def test_guessing_the_card_locks_recovery_until_support_unlocks_it(
    client, db, accounts, admin, login, funded
):
    project_id, donor, base, _ = funded
    donor = login(PHONE)
    asked = {"new_key": Account.create().address, "card_last4": CARD}
    wrong = asked | {"card_last4": "0000"}
    for _ in range(4):
        error(
            client.post(f"{base}/recovery", json=wrong, headers=donor.headers), 403, "card_mismatch"
        )
    last = error(
        client.post(f"{base}/recovery", json=wrong, headers=donor.headers), 403, "card_mismatch"
    )
    assert "now locked" in last["message"]

    # Even the right card is refused now, so four digits cannot be found by trying them all.
    error(
        client.post(f"{base}/recovery", json=asked, headers=donor.headers), 429, "recovery_locked"
    )
    [listed] = ok(client.get("/v1/receipts", headers=donor.headers))
    assert listed["recovery_locked"] is True

    error(client.post(f"{base}/unlock-recovery", headers=donor.headers), 403, "admin_only")
    ok(client.post(f"{base}/unlock-recovery", headers=admin.headers))
    ok(client.post(f"{base}/recovery", json=asked, headers=donor.headers), 202)
    assert wrong_answers(db, donor) == 0


def test_a_stranger_cannot_donate_under_a_donors_key_to_claim_the_receipt(
    client, db, accounts, login, funded
):
    """Holder keys are public on-chain. A small donation under someone else's key used to
    make that receipt look like the stranger's."""
    project_id, donor, base, _ = funded
    stranger = login("+994 55 960 00 02")
    body = {"amount_qapik": 100, "holder": accounts["donor1"].address, "card_number": "4242" * 4}
    url = f"/v1/projects/{project_id}/donations"
    error(client.post(url, json=body, headers=stranger.headers), 409, "holder_taken")
    pledge = {"amount_qapik": 500, "holder": accounts["donor1"].address, "card_number": "4242" * 4}
    error(
        client.post(f"/v1/projects/{project_id}/pledges", json=pledge, headers=stranger.headers),
        409,
        "holder_taken",
    )
    asked = {"new_key": Account.create().address, "card_last4": CARD}
    error(
        client.post(f"{base}/recovery", json=asked, headers=stranger.headers), 403, "not_the_donor"
    )
    # A stranger's tries cost the donor nothing.
    assert wrong_answers(db, donor) == 0
    assert ok(client.get("/v1/receipts", headers=stranger.headers)) == []


def test_only_a_card_paid_before_the_receipt_was_issued_counts(client, db, accounts, login, funded):
    """Someone who took over the phone number could pay with a card of their own and then
    name it. Logging in again moves nothing: the cutoff is the receipt's own date."""
    project_id, donor, base, _ = funded
    thief = login(PHONE)
    db.execute(
        update(Donation)
        .where(Donation.project_id == uuid.UUID(project_id))
        .values(created_at=Donation.created_at + timedelta(days=1))
    )
    db.commit()
    asked = {"new_key": Account.create().address, "card_last4": CARD}
    for person in (thief, login(PHONE)):
        error(
            client.post(f"{base}/recovery", json=asked, headers=person.headers),
            403,
            "card_too_recent",
        )
    assert wrong_answers(db, donor) == 0  # naming the account's own card is not a guess


def test_wrong_answers_sent_at_once_all_count(client, db, accounts, login, funded):
    """Each answer locks the account's row, so parallel guesses cannot share one count."""
    from concurrent.futures import ThreadPoolExecutor

    _, donor, base, _ = funded
    donor = login(PHONE)
    wrong = {"new_key": Account.create().address, "card_last4": "0000"}
    with ThreadPoolExecutor(8) as pool:
        answers = list(
            pool.map(
                lambda _: client.post(f"{base}/recovery", json=wrong, headers=donor.headers),
                range(8),
            )
        )
    assert sorted(answer.status_code for answer in answers).count(403) == 5
    assert wrong_answers(db, donor) == 5
    right = wrong | {"card_last4": CARD}
    error(
        client.post(f"{base}/recovery", json=right, headers=donor.headers), 429, "recovery_locked"
    )


def test_a_move_the_chain_refused_can_be_signed_again(client, db, chain, w3, accounts, funded):
    project_id, donor, base, settle = funded
    old, new = accounts["donor1"], Account.create()
    now = int(chain_now(w3).timestamp())

    too_soon = {"new_key": new.address, "deadline": now + 60}
    signed = sign_typed(client, f"{base}/rotation-message", too_soon, donor, old)
    error(
        client.post(
            f"{base}/rotation", json={**too_soon, "signature": signed}, headers=donor.headers
        ),
        422,
        "deadline_too_soon",
    )

    # Signed with 20 minutes to spare, but the relayer only gets to it an hour later.
    late = {"new_key": new.address, "deadline": now + 20 * 60}
    signed = sign_typed(client, f"{base}/rotation-message", late, donor, old)
    body = {**late, "signature": signed}
    ok(client.post(f"{base}/rotation", json=body, headers=donor.headers), 202)
    warp(w3, 3600)
    settle()
    db.expire_all()
    [failed] = db.scalars(select(ChainOutbox).where(ChainOutbox.kind == "rotate_key")).all()
    assert failed.status == OutboxStatus.FAILED
    assert controller_on_chain(chain, project_id, old.address) == old.address

    # The same signature again would only fail again; a fresh one goes through.
    error(
        client.post(f"{base}/rotation", json=body, headers=donor.headers), 422, "deadline_too_soon"
    )
    again = {"new_key": new.address, "deadline": int(chain_now(w3).timestamp()) + 3600}
    signed = sign_typed(client, f"{base}/rotation-message", again, donor, old)
    ok(
        client.post(f"{base}/rotation", json={**again, "signature": signed}, headers=donor.headers),
        202,
    )
    settle()
    assert controller_on_chain(chain, project_id, old.address) == new.address
    assert receipt_row(db, project_id, old.address).controller == new.address


def test_after_too_many_refusals_the_api_says_so_instead_of_queued(
    client, db, chain, w3, accounts, funded
):
    _, donor, base, _ = funded
    old, new = accounts["donor1"], Account.create()
    move = {"new_key": new.address, "deadline": int(chain_now(w3).timestamp()) + 3600}
    signed = sign_typed(client, f"{base}/rotation-message", move, donor, old)
    body = {**move, "signature": signed}
    for _ in range(5):
        ok(client.post(f"{base}/rotation", json=body, headers=donor.headers), 202)
        db.execute(
            update(ChainOutbox)
            .where(ChainOutbox.kind == "rotate_key", ChainOutbox.status == OutboxStatus.PENDING)
            .values(status=OutboxStatus.FAILED, last_error="would revert: 0x203d82d8")
        )
        db.commit()
    refused = error(
        client.post(f"{base}/rotation", json=body, headers=donor.headers), 409, "refused_on_chain"
    )
    assert "Expired" in refused["message"]
