"""The daily reconciliation: three numbers that must agree.

At a cut-off block the worker reads the vAZN supply on-chain, works out what Veritas's own
ledger says the escrow should hold, and asks the bank for its signed escrow balance. The
bank's signed balance is anchored on-chain either way. If it differs from the supply, the
contracts refuse releases by themselves until a balanced attestation arrives; if anything
differs, a person gets a critical alert.

The three only agree when nothing is half-way: a batch the bank signed but the chain has not
anchored yet, or a payout it made but has not confirmed on-chain. So the worker waits for a
quiet moment, with none of those in the outbox, and takes the cut-off from a finalised block.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.chain.contracts import Contracts
from veritas.chain.outbox import enqueue
from veritas.chain.relayer import final_block
from veritas.core.hashing import sha256
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.models.decisions import Payout, PayoutStatus
from veritas.db.models.money import Batch, BatchStatus, Reconciliation
from veritas.payments.clients import BankClient

BANK_SIGNED = ("anchor_batch", "settle_batch", "confirm_payout", "fail_payout")
OPEN = (OutboxStatus.PENDING, OutboxStatus.SENDING, OutboxStatus.SENT)


def ledger_balance(session: Session) -> int:
    """What Veritas's books say the escrow account holds: settled batches minus every payout
    and refund the bank has confirmed on-chain."""
    settled = session.scalar(
        select(func.coalesce(func.sum(Batch.total_qapik), 0)).where(
            Batch.status == BatchStatus.SETTLED
        )
    )
    paid = session.scalar(
        select(func.coalesce(func.sum(Payout.amount_qapik), 0)).where(
            Payout.status == PayoutStatus.CONFIRMED
        )
    )
    return int(settled) - int(paid)


def quiet(session: Session) -> bool:
    busy = session.scalar(
        select(func.count()).where(ChainOutbox.kind.in_(BANK_SIGNED), ChainOutbox.status.in_(OPEN))
    )
    paid_unconfirmed = session.scalar(
        select(func.count()).where(
            Payout.status.in_((PayoutStatus.BANK_PAID, PayoutStatus.BANK_FAILED))
        )
    )
    return busy == 0 and paid_unconfirmed == 0


def reconcile(
    session: Session,
    chain: Contracts,
    bank: BankClient,
    *,
    confirmations: int | None = None,
) -> Reconciliation | None:
    """Runs today's reconciliation. None if it ran already today or the system is busy."""
    if not quiet(session):
        return None
    w3 = chain.w3
    cutoff = min(final_block(w3, confirmations), w3.eth.block_number - 1)
    if cutoff < 0:
        return None
    cutoff_time = w3.eth.get_block(cutoff)["timestamp"]
    day = cutoff_time // 86_400
    last = session.scalar(select(func.max(Reconciliation.day)))
    if last is not None and day <= last:
        return None

    supply = chain.vazn.functions.totalSupplyAt(cutoff).call()
    ledger = ledger_balance(session)
    attestation = bank.attest_balance(day=day, cutoff_block=cutoff, cutoff_time=cutoff_time)
    statement = attestation["statement"].encode()
    signature = bytes.fromhex(attestation["signature"][2:])
    bank_balance = int(attestation["balance"])
    balanced = supply == ledger == bank_balance

    row = enqueue(
        session,
        kind="attest_balance",
        contract="DonationLedger",
        function="attestBalance",
        args=[day, cutoff, cutoff_time, bank_balance, sha256(statement), signature],
        dedupe_key=f"attest_balance:{day}",
    )
    reconciliation = Reconciliation(
        day=day,
        cutoff_block=cutoff,
        cutoff_time=datetime.fromtimestamp(cutoff_time, UTC),
        chain_supply_qapik=supply,
        ledger_qapik=ledger,
        bank_balance_qapik=bank_balance,
        balanced=balanced,
        statement=statement,
        statement_hash=sha256(statement),
        bank_signature=signature,
        outbox_id=row.id,
    )
    session.add(reconciliation)
    session.flush()
    if not balanced:
        raise_alert(
            session,
            kind="reconciliation_mismatch",
            severity="critical",
            message=(
                f"day {day}: chain {supply}, ledger {ledger}, bank {bank_balance} qəpik; "
                "releases stop if the bank and the chain differ"
            ),
            details={
                "day": day,
                "cutoff_block": cutoff,
                "chain": supply,
                "ledger": ledger,
                "bank": bank_balance,
            },
            dedupe_key=f"reconciliation_mismatch:{day}",
        )
    return reconciliation
