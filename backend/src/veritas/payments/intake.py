"""Donation intake: from a card payment to allocations waiting for the next batch.

A donor's payment goes to the card provider with the project and the donor's per-project key
in its metadata. The provider then sends a signed webhook. Only the webhook creates money:

1. its HMAC signature and timestamp are checked;
2. the payment is looked up again with the provider, and only that answer is trusted;
3. the donation is inserted under a unique constraint on the provider's payment id, so a
   webhook delivered twice, or two at once, still makes one donation;
4. the amount is split across the milestones by the Passport's rule, and each part becomes
   an allocation: one Merkle leaf with its own random salt.

If the project cannot take the money any more, the payment (or the part above what the
project still needs) goes straight back to the card.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from eth_utils import is_address, to_checksum_address
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.chain.leaves import NO_TRIGGER, DonationLeaf, new_salt
from veritas.db.models import (
    Milestone,
    MilestoneStatus,
    PassportStatus,
    PassportVersion,
    Project,
    ProjectStatus,
)
from veritas.db.models.chain import AlertSeverity
from veritas.db.models.money import (
    Allocation,
    AllocationStatus,
    Donation,
    DonationKind,
    DonationStatus,
)
from veritas.domain.allocation import allocate
from veritas.passport import Passport, load_passport
from veritas.payments import webhooks
from veritas.payments.clients import PspClient
from veritas.payments.holders import check_holder, holder_owners
from veritas.services.errors import BadRequest, NotFound, Unprocessable

PROVIDER = "mockpsp"
MIN_DONATION_QAPIK = 100
CLOSED_MILESTONES = (MilestoneStatus.RELEASED, MilestoneStatus.PAID, MilestoneStatus.STOPPED)


def current_passport(session: Session, project_id: uuid.UUID) -> Passport:
    row = session.scalars(
        select(PassportVersion).where(
            PassportVersion.project_id == project_id,
            PassportVersion.status == PassportStatus.PUBLISHED,
        )
    ).one()
    return load_passport(row.canonical_bytes)


def remaining_needs(session: Session, project_id: uuid.UUID) -> list[int]:
    """What each milestone can still take: its budget minus everything allocated to it.

    Allocations still waiting for a batch count, so two donations in the same hour cannot
    overfill a milestone. Released and paid milestones take nothing more, like on-chain.
    """
    milestones = session.scalars(
        select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.index)
    ).all()
    allocated = dict(
        session.execute(
            select(Allocation.milestone_index, func.sum(Allocation.amount_qapik))
            .where(
                Allocation.project_id == project_id,
                Allocation.status != AllocationStatus.VOID,
            )
            .group_by(Allocation.milestone_index)
        ).all()
    )
    return [
        0
        if m.status in CLOSED_MILESTONES
        else max(0, m.amount_qapik - int(allocated.get(m.index, 0)))
        for m in milestones
    ]


def accepting(project: Project | None) -> bool:
    return project is not None and project.status == ProjectStatus.LIVE


@dataclass(frozen=True)
class PaymentResult:
    payment_id: str
    status: str
    failure_reason: str | None


def start_payment(
    session: Session,
    psp: PspClient,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    holder: str,
    amount: int,
    card_number: str,
    idempotency_key: str,
) -> PaymentResult:
    """Charges the donor's card. The donation itself is created by the webhook that follows."""
    project = session.get(Project, project_id)
    if not accepting(project):
        raise NotFound("project_not_accepting", "This project is not taking donations.")
    if not isinstance(holder, str) or not is_address(holder):
        raise BadRequest("bad_holder", "The donor key must be an address.")
    check_holder(session, to_checksum_address(holder), user_id)
    if amount < MIN_DONATION_QAPIK:
        raise Unprocessable("amount_too_small", "The smallest donation is 1 AZN.")
    needed = sum(remaining_needs(session, project_id))
    if amount > needed:
        raise Unprocessable(
            "more_than_needed",
            f"This project needs {needed} qəpik more; give that or less.",
            details=[{"needed_qapik": needed}],
        )
    payment = psp.create_payment(
        amount=amount,
        card_number=card_number,
        metadata={
            "project_id": str(project_id),
            "holder": to_checksum_address(holder),
            "user_id": str(user_id),
            "kind": DonationKind.CARD,
        },
        idempotency_key=idempotency_key,
    )
    return PaymentResult(payment["id"], payment["status"], payment.get("failure_reason"))


def handle_webhook(
    session: Session,
    psp: PspClient,
    secret: bytes,
    body: bytes,
    signature: str | None,
    now: float | None = None,
) -> Donation | None:
    """Turns a signed payment webhook into a donation, exactly once."""
    try:
        webhooks.verify(secret, signature, body, time.time() if now is None else now)
    except webhooks.WebhookError as exc:
        raise BadRequest("bad_webhook_signature", str(exc)) from exc
    try:
        event = json.loads(body)
        event_type, payment_id = event["type"], event["data"]["id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BadRequest("bad_webhook", "The webhook body is not a payment event.") from exc
    if event_type != "payment.succeeded":
        return None  # failures and refunds need no action here
    payment = psp.get_payment(payment_id)  # the second lookup: only this answer counts
    if payment.get("status") != "succeeded" or payment.get("currency") != "AZN":
        raise BadRequest("payment_not_succeeded", "The provider does not confirm this payment.")
    metadata = payment.get("metadata") or {}
    if metadata.get("kind") == DonationKind.PAY_ON_PROOF:
        # Its leaves carry the approval that caused the charge, and it funds what the
        # Passport says Pay-on-Proof money funds.
        from veritas.decisions.pledges import funded_milestones

        try:
            trigger = bytes.fromhex(metadata["approval_tx"].removeprefix("0x"))
            project_id = uuid.UUID(metadata["project_id"])
            approved = int(metadata["approved_milestone"])
        except (KeyError, ValueError) as exc:
            raise BadRequest(
                "bad_payment_metadata", "A Pay-on-Proof charge names no approval."
            ) from exc
        funds = funded_milestones(session, project_id, approved)
        return record_payment(session, psp, payment, trigger=trigger, funds=funds)
    return record_payment(session, psp, payment)


def record_payment(
    session: Session,
    psp: PspClient,
    payment: dict[str, Any],
    *,
    trigger: bytes = NO_TRIGGER,
    funds: Sequence[int] | None = None,
) -> Donation:
    """Inserts the donation once and allocates it. `funds` limits which milestones it may
    fund (Pay-on-Proof); by default any milestone that still needs money."""
    metadata = payment.get("metadata") or {}
    try:
        project_id = uuid.UUID(metadata["project_id"])
        holder = to_checksum_address(metadata["holder"])
        user_id = uuid.UUID(metadata["user_id"]) if metadata.get("user_id") else None
    except (KeyError, ValueError) as exc:
        raise BadRequest("bad_payment_metadata", "The payment does not name a project.") from exc
    kind = metadata.get("kind", DonationKind.CARD)
    inserted = session.scalars(
        insert(Donation)
        .values(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            holder=holder,
            amount_qapik=int(payment["amount"]),
            kind=kind,
            provider=PROVIDER,
            provider_payment_id=payment["id"],
            card_last4=payment.get("card_last4"),
            trigger=trigger,
            pledge_charge_id=uuid.UUID(metadata["pledge_charge_id"])
            if metadata.get("pledge_charge_id")
            else None,
        )
        .on_conflict_do_nothing(index_elements=["provider", "provider_payment_id"])
        .returning(Donation)
    ).first()
    if inserted is None:  # this payment was counted already
        return session.scalars(
            select(Donation).where(
                Donation.provider == PROVIDER, Donation.provider_payment_id == payment["id"]
            )
        ).one()
    if len(holder_owners(session, holder)) > 1:
        # Two accounts started payments under one new key at the same moment. The money is
        # real, so it counts; who the receipt belongs to needs a person.
        raise_alert(
            session,
            kind="holder_shared",
            message=f"Donor key {holder} in project {project_id} is used by two accounts.",
            severity=AlertSeverity.CRITICAL,
            dedupe_key=f"holder_shared:{project_id}:{holder}",
        )
    _allocate(session, psp, inserted, funds)
    return inserted


def _allocate(
    session: Session, psp: PspClient, donation: Donation, funds: Sequence[int] | None
) -> None:
    project = session.get(Project, donation.project_id, with_for_update=True)
    needs = remaining_needs(session, donation.project_id) if accepting(project) else []
    if funds is not None and needs:
        restricted = [need if i in funds else 0 for i, need in enumerate(needs)]
        needs = restricted if sum(restricted) else needs
    take = min(donation.amount_qapik, sum(needs))
    if take < donation.amount_qapik:
        excess = donation.amount_qapik - take
        psp.refund(
            payment_id=donation.provider_payment_id,
            amount=excess,
            # Keyed on the payment, not the row: a webhook retried after a rollback makes a
            # new row, and must not refund the excess twice.
            idempotency_key=f"excess-{donation.provider_payment_id}",
        )
        donation.refunded_qapik = excess
    if take == 0:
        donation.status = DonationStatus.REFUNDED
        return
    rule = current_passport(session, donation.project_id).allocation
    for index, part in enumerate(allocate(take, needs, rule)):
        if part == 0:
            continue
        leaf = DonationLeaf(
            donation_id=donation.id,
            holder=donation.holder,
            project_id=donation.project_id,
            milestone=index,
            amount=part,
            trigger=donation.trigger,
            salt=new_salt(),
        )
        session.add(
            Allocation(
                donation_id=donation.id,
                project_id=donation.project_id,
                milestone_index=index,
                amount_qapik=part,
                holder=donation.holder,
                salt=leaf.salt,
                trigger=leaf.trigger,
                leaf_hash=leaf.hash(),
                credited=donation.kind != DonationKind.REDIRECT,
            )
        )
    session.flush()
