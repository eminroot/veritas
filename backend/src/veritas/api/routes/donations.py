"""Donations: paying by card, the provider's webhook, and a donor's receipts with proofs.

A donation is tracked like a parcel: received, in escrow, and onwards with its milestones.
The donor's receipt carries everything needed to check it without Veritas: the leaf, its
salt, the batch, the Merkle proof and the transaction that anchored the batch.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from veritas.api.deps import CurrentUser, DbSession
from veritas.api.schemas import Input, Output
from veritas.core.hashing import to_hex
from veritas.db.models import Milestone
from veritas.db.models.money import (
    Allocation,
    Batch,
    BatchLeaf,
    Donation,
)
from veritas.payments.intake import handle_webhook, start_payment
from veritas.payments.webhooks import SIGNATURE_HEADER
from veritas.services.errors import NotFound

router = APIRouter(tags=["donations"])


class DonateIn(Input):
    amount_qapik: int = Field(gt=0, description="Whole qəpik: 1250 is 12.50 AZN.")
    holder: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$", description="Your key for this project.")
    card_number: str = Field(min_length=12, max_length=19)
    idempotency_key: str | None = Field(default=None, max_length=100)


class PaymentOut(Output):
    payment_id: str
    status: str
    failure_reason: str | None


@router.post("/v1/projects/{project_id}/donations", status_code=201)
def donate(
    project_id: uuid.UUID, body: DonateIn, user: CurrentUser, db: DbSession, request: Request
) -> PaymentOut:
    """Charge a card for a donation. The donation itself appears when the provider confirms."""
    result = start_payment(
        db,
        request.app.state.psp,
        project_id=project_id,
        user_id=user.id,
        holder=body.holder,
        amount=body.amount_qapik,
        card_number=body.card_number,
        idempotency_key=body.idempotency_key or f"donation-{uuid.uuid4()}",
    )
    return PaymentOut(
        payment_id=result.payment_id, status=result.status, failure_reason=result.failure_reason
    )


@router.post("/v1/webhooks/psp", include_in_schema=False)
async def psp_webhook(
    request: Request,
    signature: Annotated[str | None, Header(alias=SIGNATURE_HEADER)] = None,
) -> dict[str, Any]:
    """The card provider's signed webhook. Only this creates donations."""
    body = await request.body()
    secret = request.app.state.settings.psp_webhook_secret.get_secret_value().encode()

    def receive() -> Donation | None:
        with request.app.state.session_factory() as session:
            donation = handle_webhook(session, request.app.state.psp, secret, body, signature)
            session.commit()
            return donation

    donation = await run_in_threadpool(receive)
    return {"received": True, "donation_id": str(donation.id) if donation else None}


class LeafOut(Output):
    milestone: int
    milestone_title: str
    milestone_status: str
    amount_qapik: int
    status: str
    leaf: dict[str, Any]
    """The leaf's fields as the contract hashes them, salt included. Keep it private."""
    leaf_hash: str
    batch_id: int | None
    batch_root: str | None
    proof: list[str] | None
    anchored_tx: str | None


class DonationOut(Output):
    id: uuid.UUID
    project_id: uuid.UUID
    holder: str
    amount_qapik: int
    refunded_qapik: int
    kind: str
    status: str
    created_at: datetime
    allocations: list[LeafOut]


def _donation_out(db: DbSession, donation: Donation) -> DonationOut:
    rows = db.execute(
        select(Allocation, BatchLeaf, Batch, Milestone)
        .join(BatchLeaf, BatchLeaf.allocation_id == Allocation.id, isouter=True)
        .join(Batch, Batch.id == Allocation.batch_id, isouter=True)
        .join(
            Milestone,
            (Milestone.project_id == Allocation.project_id)
            & (Milestone.index == Allocation.milestone_index),
        )
        .where(Allocation.donation_id == donation.id)
        .order_by(Allocation.milestone_index)
    ).all()
    allocations = []
    for allocation, leaf, batch, milestone in rows:
        allocations.append(
            LeafOut(
                milestone=allocation.milestone_index,
                milestone_title=milestone.title,
                milestone_status=milestone.status,
                amount_qapik=allocation.amount_qapik,
                status=allocation.status,
                leaf={
                    "donationId": "0x" + allocation.donation_id.hex,
                    "holder": allocation.holder,
                    "projectId": "0x" + allocation.project_id.hex,
                    "milestone": allocation.milestone_index,
                    "amount": allocation.amount_qapik,
                    "trigger": to_hex(allocation.trigger),
                    "salt": to_hex(allocation.salt),
                },
                leaf_hash=to_hex(allocation.leaf_hash),
                batch_id=allocation.batch_id,
                batch_root=to_hex(batch.root) if batch else None,
                proof=leaf.proof if leaf else None,
                anchored_tx=to_hex(batch.anchored_tx) if batch and batch.anchored_tx else None,
            )
        )
    return DonationOut(
        id=donation.id,
        project_id=donation.project_id,
        holder=donation.holder,
        amount_qapik=donation.amount_qapik,
        refunded_qapik=donation.refunded_qapik,
        kind=donation.kind,
        status=donation.status,
        created_at=donation.created_at,
        allocations=allocations,
    )


@router.get("/v1/donations")
def my_donations(user: CurrentUser, db: DbSession) -> list[DonationOut]:
    donations = db.scalars(
        select(Donation).where(Donation.user_id == user.id).order_by(Donation.created_at.desc())
    ).all()
    return [_donation_out(db, donation) for donation in donations]


@router.get("/v1/donations/{donation_id}")
def my_donation(donation_id: uuid.UUID, user: CurrentUser, db: DbSession) -> DonationOut:
    """A donation with every leaf and proof. Only the donor sees it: the salts are theirs."""
    donation = db.get(Donation, donation_id)
    if donation is None or donation.user_id != user.id:
        raise NotFound("not_found", "You have no donation with this id.")
    return _donation_out(db, donation)
