"""The relayer and the indexer on their own: failures, crashes, fee bumps and repeats."""

from flowkit import workers
from sqlalchemy import select, update

from chainkit import mine
from veritas.chain.outbox import enqueue
from veritas.db.models.chain import (
    Alert,
    ChainCursor,
    ChainEvent,
    ChainOutbox,
    OutboxStatus,
    Sender,
)

SOMEONE = "0x000000000000000000000000000000000000dEaD"


def queue(db, kind, function, args, sender=Sender.ADMIN, key=None):
    row = enqueue(
        db,
        kind=kind,
        contract="VeritasHub",
        function=function,
        args=args,
        dedupe_key=key or f"{kind}:{function}:{args}",
        sender=sender,
    )
    db.commit()
    return row


def settle(relayer, indexer, w3, rounds=12):
    for _ in range(rounds):
        relayer.run_once()
        mine(w3, 1)
        indexer.run_once()


def test_a_call_that_would_revert_is_failed_with_an_alert(db, chain, w3, accounts, sessions):
    # Only the admin may register charities; from the relayer key it reverts.
    row = queue(db, "register_charity", "setCharity", [SOMEONE, True], sender=Sender.RELAYER)
    relayer, _ = workers(sessions, chain, accounts)
    relayer.run_once()
    db.expire_all()
    row = db.get(ChainOutbox, row.id)
    assert row.status == OutboxStatus.FAILED
    assert "would revert" in row.last_error
    assert row.nonce is None  # nothing was sent, so no nonce was used
    alert = db.scalars(select(Alert)).one()
    assert alert.kind == "outbox_failed"


def test_the_same_key_twice_is_one_row(db):
    first = queue(db, "register_charity", "setCharity", [SOMEONE, True], key="same")
    second = queue(db, "register_charity", "setCharity", [SOMEONE, False], key="same")
    assert first.id == second.id
    assert db.scalars(select(ChainOutbox)).one().args == [SOMEONE, True]


def test_a_crash_after_signing_rebroadcasts_the_same_transaction(db, chain, w3, accounts, sessions):
    row = queue(db, "register_charity", "setCharity", [SOMEONE, True])
    relayer, indexer = workers(sessions, chain, accounts)
    # Sign and record as the relayer does, then "crash" before broadcasting.
    w3.provider.make_request("evm_setAutomine", [False])
    original = relayer._broadcast
    relayer._broadcast = lambda session, outbox_row, raw: None
    relayer.run_once()
    relayer._broadcast = original
    db.expire_all()
    signed = db.get(ChainOutbox, row.id)
    assert signed.status == OutboxStatus.SENDING
    tx_hash = signed.tx_hash

    w3.provider.make_request("evm_setAutomine", [True])
    settle(relayer, indexer, w3)
    db.expire_all()
    done = db.get(ChainOutbox, row.id)
    assert done.status == OutboxStatus.CONFIRMED
    assert done.tx_hash == tx_hash and len(done.tx_hashes) == 1
    assert chain.contracts.hub.functions.isCharity(SOMEONE).call()


def test_a_dependency_that_failed_fails_what_waits_for_it(db, chain, w3, accounts, sessions):
    bad = queue(db, "register_charity", "setCharity", [SOMEONE, True], sender=Sender.RELAYER)
    waiting = queue(db, "register_officer", "setOfficer", [SOMEONE, True])
    db.execute(update(ChainOutbox).where(ChainOutbox.id == waiting.id).values(depends_on=bad.id))
    db.commit()
    relayer, _ = workers(sessions, chain, accounts)
    relayer.drain()
    db.expire_all()
    assert db.get(ChainOutbox, waiting.id).status == OutboxStatus.FAILED
    assert "waits for outbox" in db.get(ChainOutbox, waiting.id).last_error


def test_a_stuck_transaction_gets_higher_fees(db, chain, w3, accounts, sessions):
    row = queue(db, "register_charity", "setCharity", [SOMEONE, True])
    relayer, indexer = workers(sessions, chain, accounts)
    now = [1_900_000_000.0]
    relayer.clock = lambda: now[0]
    w3.provider.make_request("evm_setAutomine", [False])
    relayer.run_once()
    db.expire_all()
    first = db.get(ChainOutbox, row.id)
    fees = (first.max_fee_per_gas, first.max_priority_fee_per_gas)

    now[0] += 3601  # past bump_after_seconds
    relayer.run_once()
    db.expire_all()
    bumped = db.get(ChainOutbox, row.id)
    assert len(bumped.tx_hashes) == 2
    assert bumped.max_fee_per_gas >= fees[0] * 120 // 100
    assert bumped.max_priority_fee_per_gas >= fees[1] * 120 // 100

    w3.provider.make_request("evm_setAutomine", [True])
    mine(w3, 1)
    settle(relayer, indexer, w3)
    db.expire_all()
    done = db.get(ChainOutbox, row.id)
    assert done.status == OutboxStatus.CONFIRMED
    assert done.tx_hash.hex() == bumped.tx_hashes[1][2:]


def test_indexing_a_chunk_twice_stores_each_event_once(db, chain, w3, accounts, sessions):
    queue(db, "register_charity", "setCharity", [SOMEONE, True])
    relayer, indexer = workers(sessions, chain, accounts)
    settle(relayer, indexer, w3)
    before = db.scalars(select(ChainEvent)).all()
    assert any(e.event == "CharitySet" for e in before)
    db.execute(update(ChainCursor).values(block_number=chain.deployment.start_block - 1))
    db.commit()
    indexer.catch_up()
    assert len(db.scalars(select(ChainEvent)).all()) == len(before)


def test_a_confirmed_call_without_its_event_raises_an_alert(db, chain, w3, accounts, sessions):
    # Labelled as a launch, but the call is something else, so ProjectCreated never comes.
    queue(db, "launch_project", "setOfficer", [SOMEONE, True])
    relayer, indexer = workers(sessions, chain, accounts)
    settle(relayer, indexer, w3)
    alerts = db.scalars(select(Alert)).all()
    assert [a.kind for a in alerts] == ["expected_event_missing"]
    assert alerts[0].severity == "critical"
