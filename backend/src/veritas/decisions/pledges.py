"""Pay-on-Proof: a donor pledges an amount per verified milestone and saves a card.

When a milestone is approved on-chain, every active pledge on the project gets one charge,
unique on (pledge, milestone, approval round), so an approval never charges twice. A
successful charge becomes a normal donation through the provider's webhook, and its leaves
carry the transaction that approved the milestone, so the donor can check that every charge
on their card follows a real approval. By default the money funds the milestones after the
approved one, so a contractor's payout never depends on card charges going through. A failed
charge is retried once; then the pledge pauses and the donor is told.
"""

from __future__ import annotations

import uuid

from eth_utils import is_address, to_checksum_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.db.models import Project, ProjectStatus, User
from veritas.db.models.chain import ChainEvent
from veritas.db.models.money import (
    DonationKind,
    Pledge,
    PledgeCharge,
    PledgeChargeStatus,
    PledgeStatus,
)
from veritas.payments.clients import ProviderError, PspClient
from veritas.payments.holders import check_holder
from veritas.payments.intake import accepting, current_passport, remaining_needs
from veritas.services.errors import BadRequest, NotFound, Unprocessable

MAX_ATTEMPTS = 2


def create_pledge(
    session: Session,
    psp: PspClient,
    *,
    project_id: uuid.UUID,
    user: User,
    holder: str,
    amount: int,
    card_number: str,
) -> Pledge:
    project = session.get(Project, project_id)
    if not accepting(project):
        raise NotFound("project_not_accepting", "This project is not taking pledges.")
    if not is_address(holder):
        raise BadRequest("bad_holder", "The donor key must be an address.")
    check_holder(session, to_checksum_address(holder), user.id)
    if amount < 100:
        raise Unprocessable("amount_too_small", "The smallest pledge is 1 AZN per milestone.")
    try:
        card = psp.save_card(customer_ref=str(user.id), card_number=card_number)
    except ProviderError as exc:
        raise BadRequest("card_refused", f"The card provider refused the card: {exc}") from exc
    pledge = Pledge(
        user_id=user.id,
        project_id=project_id,
        holder=to_checksum_address(holder),
        amount_qapik=amount,
        card_token=card["token"],
        card_last4=card.get("last4"),
    )
    session.add(pledge)
    session.flush()
    return pledge


def funded_milestones(session: Session, project_id: uuid.UUID, approved: int) -> list[int]:
    """Which milestones a charge triggered by `approved` may fund, by the Passport's rule."""
    passport = current_passport(session, project_id)
    count = len(passport.milestones)
    if passport.pay_on_proof.funds == "approved_milestone":
        return [approved]
    later = list(range(approved + 1, count))
    return later or [approved]


def on_milestone_approved(session: Session, event: ChainEvent) -> None:
    """One charge per active pledge for this approval."""
    if event.project_id is None:
        return
    pledges = session.scalars(
        select(Pledge).where(
            Pledge.project_id == event.project_id, Pledge.status == PledgeStatus.ACTIVE
        )
    ).all()
    for pledge in pledges:
        exists = session.scalar(
            select(PledgeCharge.id).where(
                PledgeCharge.pledge_id == pledge.id,
                PledgeCharge.milestone_index == event.args["milestone"],
                PledgeCharge.approval_round == event.args["attempt"],
            )
        )
        if exists is None:
            session.add(
                PledgeCharge(
                    pledge_id=pledge.id,
                    milestone_index=event.args["milestone"],
                    approval_round=event.args["attempt"],
                    approval_tx=event.tx_hash,
                    amount_qapik=pledge.amount_qapik,
                )
            )
    session.flush()


def charge_pledges(session: Session, psp: PspClient) -> int:
    """Charges every pending pledge charge, retrying a failed one once."""
    charges = session.scalars(
        select(PledgeCharge)
        .where(PledgeCharge.status == PledgeChargeStatus.PENDING)
        .order_by(PledgeCharge.created_at)
        .with_for_update(skip_locked=True)
    ).all()
    made = 0
    for charge in charges:
        pledge = session.get(Pledge, charge.pledge_id)
        project = session.get(Project, pledge.project_id)
        if project is None or project.status != ProjectStatus.LIVE:
            charge.status = PledgeChargeStatus.SKIPPED
            charge.failure_reason = "the project is no longer live"
            continue
        funds = funded_milestones(session, project.id, charge.milestone_index)
        needs = remaining_needs(session, project.id)
        room = sum(needs[i] for i in funds) or sum(needs)
        amount = min(charge.amount_qapik, room)
        if amount == 0:
            charge.status = PledgeChargeStatus.SKIPPED
            charge.failure_reason = "the project needs nothing more"
            continue
        charge.attempts += 1
        try:
            payment = psp.charge(
                card_token=pledge.card_token,
                amount=amount,
                metadata={
                    "project_id": str(project.id),
                    "holder": pledge.holder,
                    "user_id": str(pledge.user_id),
                    "kind": DonationKind.PAY_ON_PROOF,
                    "pledge_charge_id": str(charge.id),
                    "approval_tx": "0x" + charge.approval_tx.hex(),
                    "approved_milestone": charge.milestone_index,
                },
                idempotency_key=f"pledge-charge-{charge.id}-{charge.attempts}",
            )
        except ProviderError as exc:
            payment = {"status": "failed", "failure_reason": str(exc), "id": None}
        if payment["status"] == "succeeded":
            charge.status = PledgeChargeStatus.SUCCEEDED
            charge.provider_payment_id = payment["id"]
            charge.amount_qapik = amount
            made += 1
            continue
        charge.failure_reason = payment.get("failure_reason")
        if charge.attempts >= MAX_ATTEMPTS:
            charge.status = PledgeChargeStatus.FAILED
            pledge.status = PledgeStatus.PAUSED
            raise_alert(
                session,
                kind="pledge_paused",
                severity="info",
                message=f"a pledge on {project.title} paused after two failed charges",
                details={"pledge_id": str(pledge.id), "reason": charge.failure_reason},
                dedupe_key=f"pledge_paused:{pledge.id}:{charge.id}",
            )
    session.flush()
    return made
