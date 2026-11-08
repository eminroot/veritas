"""The hourly batch: new allocations into one Merkle tree, signed by the bank, anchored.

One batch is in flight at a time, so batch ids on-chain follow the database exactly. A batch
takes whole donations, never part of one, so the bank can check every card payment it
attests. Redirect leaves ride along for their proofs but credit nothing: their money already
moved on-chain. Once the ledger's BatchSettled event is indexed, every leaf in the batch is
"in escrow" and new donors get their receipt token.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.chain.leaves import DonationLeaf, donation_tree
from veritas.chain.outbox import enqueue
from veritas.chain.project import Credit, credits_hash
from veritas.chain.receipts import receipt_id
from veritas.core.hashing import from_hex, to_hex
from veritas.db.models import Milestone, Project, ProjectStatus
from veritas.db.models.chain import ChainEvent, ChainOutbox, OutboxStatus
from veritas.db.models.money import (
    Allocation,
    AllocationStatus,
    Batch,
    BatchLeaf,
    BatchStatus,
    Donation,
    DonationKind,
    DonationStatus,
    Receipt,
    ReceiptStatus,
)
from veritas.db.session import db_now
from veritas.payments.clients import BankClient, PspClient

MAX_LEAVES = 2_000


def build_batch(session: Session, bank: BankClient) -> Batch | None:
    """Builds, signs and queues the next batch. None if one is in flight or nothing waits."""
    in_flight = session.scalars(select(Batch).where(Batch.status == BatchStatus.BUILT)).first()
    if in_flight is not None:
        anchoring = session.get(ChainOutbox, in_flight.outbox_id) if in_flight.outbox_id else None
        if anchoring is None or anchoring.status != OutboxStatus.FAILED:
            return None
        # The chain refused it, for example because a project in it stopped meanwhile. Its
        # leaves go into the next batch, which reuses the id the chain never took.
        fail_batch(session, in_flight, anchoring.last_error or "the anchoring call failed")
    donations = session.scalars(
        select(Donation)
        .join(Project, Project.id == Donation.project_id)
        .where(Donation.status == DonationStatus.RECEIVED, Project.status == ProjectStatus.LIVE)
        .order_by(Donation.created_at, Donation.id)
        .with_for_update(of=Donation, skip_locked=True)
    ).all()
    chosen: list[Donation] = []
    allocations: list[Allocation] = []
    for donation in donations:
        parts = session.scalars(
            select(Allocation)
            .where(
                Allocation.donation_id == donation.id,
                Allocation.status == AllocationStatus.RECEIVED,
            )
            .order_by(Allocation.milestone_index)
        ).all()
        if allocations and len(allocations) + len(parts) > MAX_LEAVES:
            break
        chosen.append(donation)
        allocations.extend(parts)
    if not allocations:
        return None

    leaves = [
        DonationLeaf(
            donation_id=a.donation_id,
            holder=a.holder,
            project_id=a.project_id,
            milestone=a.milestone_index,
            amount=a.amount_qapik,
            trigger=a.trigger,
            salt=a.salt,
        )
        for a in allocations
    ]
    tree = donation_tree(leaves)
    credits = _credits(session, allocations)
    batch_id = (session.scalar(select(func.max(Batch.id))) or 0) + 1
    payments = [d.provider_payment_id for d in chosen if _credits_money(d, allocations)]
    signature = bank.attest_batch(
        batch_id=batch_id,
        root=tree.root,
        leaf_count=len(leaves),
        credits=credits,
        payments=payments,
    )
    batch = Batch(
        id=batch_id,
        root=tree.root,
        leaf_count=len(leaves),
        total_qapik=sum(sum(c.amounts) for c in credits),
        credits=[{"project_id": str(c.project_id), "amounts": list(c.amounts)} for c in credits],
        credits_hash=credits_hash(credits),
        tree=tree.dump(),
        bank_signature=signature,
    )
    session.add(batch)
    session.flush()
    for position, allocation in enumerate(allocations):
        allocation.batch_id = batch_id
        allocation.status = AllocationStatus.BATCHED
        session.add(
            BatchLeaf(
                allocation_id=allocation.id,
                batch_id=batch_id,
                tree_index=tree.tree_indices[position],
                proof=[to_hex(node) for node in tree.proof(position)],
            )
        )
    for donation in chosen:
        donation.status = DonationStatus.BATCHED
    row = enqueue(
        session,
        kind="anchor_batch",
        contract="DonationLedger",
        function="anchorBatch",
        args=[batch_id, tree.root, len(leaves), [c.abi_value() for c in credits], signature],
        # The root is in the key: after a failed anchoring the same id comes back with
        # different leaves, and must not be mistaken for the call that failed.
        dedupe_key=f"anchor_batch:{batch_id}:{tree.root.hex()}",
    )
    batch.outbox_id = row.id
    session.flush()
    return batch


def _credits_money(donation: Donation, allocations: list[Allocation]) -> bool:
    return any(a.donation_id == donation.id and a.credited for a in allocations)


def _credits(session: Session, allocations: list[Allocation]) -> list[Credit]:
    """Per project, in order of first appearance, qəpik per milestone."""
    totals: dict[uuid.UUID, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    order: list[uuid.UUID] = []
    for allocation in allocations:
        if not allocation.credited:
            continue
        if allocation.project_id not in totals:
            order.append(allocation.project_id)
        totals[allocation.project_id][allocation.milestone_index] += allocation.amount_qapik
    credits = []
    for project_id in order:
        count = session.scalar(select(func.count()).where(Milestone.project_id == project_id))
        amounts = tuple(totals[project_id].get(i, 0) for i in range(count))
        credits.append(Credit(project_id, amounts))
    return credits


def fail_batch(session: Session, batch: Batch, reason: str) -> None:
    """The anchoring transaction failed: give the allocations back to the next batch."""
    session.execute(delete(BatchLeaf).where(BatchLeaf.batch_id == batch.id))
    allocation_ids = select(Allocation.id).where(Allocation.batch_id == batch.id)
    donation_ids = select(Allocation.donation_id).where(Allocation.batch_id == batch.id)
    session.execute(
        update(Donation).where(Donation.id.in_(donation_ids)).values(status=DonationStatus.RECEIVED)
    )
    session.execute(
        update(Allocation)
        .where(Allocation.id.in_(allocation_ids))
        .values(batch_id=None, status=AllocationStatus.RECEIVED)
    )
    raise_alert(
        session,
        kind="batch_failed",
        severity="critical",
        message=f"batch {batch.id} could not be anchored: {reason}",
        details={"batch_id": batch.id, "root": to_hex(batch.root)},
        dedupe_key=f"batch_failed:{batch.id}:{to_hex(batch.root)}",
    )
    session.delete(batch)
    session.flush()


def refund_unbatched(session: Session, psp: PspClient) -> int:
    """Gives back money that never reached escrow because its project stopped or completed
    before the next batch. It goes straight back to the card."""
    stranded = session.scalars(
        select(Donation)
        .join(Project, Project.id == Donation.project_id)
        .where(
            Donation.status == DonationStatus.RECEIVED,
            Donation.kind != DonationKind.REDIRECT,
            Project.status.in_((ProjectStatus.STOPPED, ProjectStatus.COMPLETED)),
        )
        .with_for_update(of=Donation, skip_locked=True)
    ).all()
    for donation in stranded:
        left = donation.amount_qapik - donation.refunded_qapik
        if left > 0:
            psp.refund(
                payment_id=donation.provider_payment_id,
                amount=left,
                idempotency_key=f"unbatched-{donation.provider_payment_id}",
            )
        donation.refunded_qapik = donation.amount_qapik
        donation.status = DonationStatus.REFUNDED
        session.execute(
            update(Allocation)
            .where(Allocation.donation_id == donation.id)
            .values(status=AllocationStatus.VOID)
        )
    session.flush()
    return len(stranded)


# ---------------------------------------------------------------- indexer handlers


def on_batch_anchored(session: Session, event: ChainEvent) -> None:
    batch = session.get(Batch, int(event.args["batchId"]), with_for_update=True)
    if batch is None or batch.root != from_hex(event.args["root"]):
        raise_alert(
            session,
            kind="event_mismatch",
            severity="critical",
            message=f"batch {event.args['batchId']} on-chain is not the one in the database",
            details={"tx_hash": "0x" + event.tx_hash.hex(), "root": event.args["root"]},
            dedupe_key=f"batch_mismatch:{event.tx_hash.hex()}",
        )
        return
    batch.anchored_block = event.block_number
    batch.anchored_tx = event.tx_hash
    if batch.status == BatchStatus.BUILT:
        batch.status = BatchStatus.ANCHORED


def on_batch_settled(session: Session, event: ChainEvent) -> None:
    """Every leaf in the batch is now in escrow, and new donors get a receipt."""
    batch = session.get(Batch, int(event.args["batchId"]), with_for_update=True)
    if batch is None:
        return  # on_batch_anchored raised the alert
    batch.status = BatchStatus.SETTLED
    batch.settled_at = db_now(session)
    session.execute(
        update(Allocation)
        .where(Allocation.batch_id == batch.id, Allocation.status == AllocationStatus.BATCHED)
        .values(status=AllocationStatus.IN_ESCROW)
    )
    session.execute(
        update(Donation)
        .where(
            Donation.id.in_(select(Allocation.donation_id).where(Allocation.batch_id == batch.id)),
            Donation.status == DonationStatus.BATCHED,
        )
        .values(status=DonationStatus.IN_ESCROW)
    )
    _queue_receipts(session, batch)


def _queue_receipts(session: Session, batch: Batch) -> None:
    rows = session.execute(
        select(Allocation, BatchLeaf)
        .join(BatchLeaf, BatchLeaf.allocation_id == Allocation.id)
        .where(Allocation.batch_id == batch.id)
        .order_by(BatchLeaf.tree_index)
    ).all()
    for allocation, leaf in rows:
        exists = session.scalar(
            select(Receipt.id).where(
                Receipt.project_id == allocation.project_id, Receipt.holder == allocation.holder
            )
        )
        if exists is not None:
            continue
        token = receipt_id(allocation.project_id, allocation.holder)
        row = enqueue(
            session,
            kind="mint_receipt",
            contract="ReceiptToken",
            function="mint",
            args=[
                batch.id,
                (
                    allocation.donation_id.bytes,
                    allocation.holder,
                    allocation.project_id.bytes,
                    allocation.milestone_index,
                    allocation.amount_qapik,
                    allocation.trigger,
                    allocation.salt,
                ),
                [from_hex(node) for node in leaf.proof],
            ],
            dedupe_key=f"mint_receipt:{allocation.project_id}:{allocation.holder}",
            project_id=allocation.project_id,
        )
        session.add(
            Receipt(
                project_id=allocation.project_id,
                holder=allocation.holder,
                token_id=str(token),
                controller=allocation.holder,
                status=ReceiptStatus.PENDING,
                outbox_id=row.id,
            )
        )
        session.flush()


def on_receipt_minted(session: Session, event: ChainEvent) -> None:
    receipt = session.scalars(
        select(Receipt).where(Receipt.token_id == str(int(event.args["receiptId"])))
    ).first()
    if receipt is not None:
        receipt.status = ReceiptStatus.MINTED


def on_key_rotated(session: Session, event: ChainEvent) -> None:
    receipt = session.scalars(
        select(Receipt).where(Receipt.token_id == str(int(event.args["receiptId"])))
    ).first()
    if receipt is not None:
        receipt.controller = event.args["newKey"]
