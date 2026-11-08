"""Money out: releasing approved milestones, and the bank's side of every instruction.

An approved milestone is released once the contracts allow releases (not paused, and a
fresh balanced bank attestation). The escrow moves the vAZN to the payout vault with an
instruction naming the Passport's contractor and the approved invoice. A job then asks the
bank to pay the contractor's verified account, or to refund a donor's cards, and anchors the
bank's signed answer: a confirmation burns the vAZN, a failure sends it back to the escrow.

A payout that comes back is not released again automatically: whatever made the bank refuse
needs a person, so an alert goes out instead.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.chain.contracts import Contracts
from veritas.chain.outbox import enqueue
from veritas.chain.project import contractor_hash
from veritas.db.models import Contractor, Milestone, MilestoneStatus, Project, ProjectStatus
from veritas.db.models.chain import ChainEvent
from veritas.db.models.decisions import (
    Claim,
    Payout,
    PayoutKind,
    PayoutStatus,
    Release,
    ReleaseStatus,
)
from veritas.db.models.money import Allocation, Donation, DonationKind
from veritas.payments.clients import BankClient, ProviderError
from veritas.payments.intake import current_passport


def release_approved(session: Session, chain: Contracts) -> int:
    """Queues `release` for every approved milestone, while the contracts allow releases."""
    if not chain.hub.functions.releasesAllowed().call():
        return 0
    approved = session.execute(
        select(Milestone, Project)
        .join(Project, Project.id == Milestone.project_id)
        .where(Milestone.status == MilestoneStatus.APPROVED, Project.status == ProjectStatus.LIVE)
    ).all()
    queued = 0
    for milestone, project in approved:
        earlier = session.scalars(
            select(Release).where(
                Release.project_id == project.id, Release.milestone_index == milestone.index
            )
        ).all()
        if any(r.status in (ReleaseStatus.REQUESTED, ReleaseStatus.INSTRUCTED) for r in earlier):
            continue
        if any(r.status == ReleaseStatus.RETURNED for r in earlier):
            continue  # the bank refused once; a person decides what happens next
        release = Release(
            project_id=project.id,
            milestone_index=milestone.index,
            amount_qapik=milestone.approved_qapik or 0,
            invoice_hash=milestone.invoice_hash or bytes(32),
        )
        session.add(release)
        row = enqueue(
            session,
            kind="release",
            contract="MilestoneEscrow",
            address=project.escrow_address,
            function="release",
            args=[milestone.index],
            dedupe_key=f"release:{project.id}:{milestone.index}:{len(earlier) + 1}",
            project_id=project.id,
        )
        release.outbox_id = row.id
        queued += 1
    session.flush()
    return queued


def _contractor_account(session: Session, project: Project) -> tuple[bytes, str]:
    passport = current_passport(session, project.id)
    contractor = session.scalars(
        select(Contractor).where(Contractor.voen == passport.contractor.voen)
    ).one()
    return contractor_hash(contractor.voen), contractor.iban


def refund_parts(session: Session, chain: Contracts, payout: Payout) -> list[tuple[str, int]]:
    """Which card payments a refund goes back to, and how much of each.

    Each claimed leaf is worth its share of what its milestone still held, as the escrow
    worked it out; the shares are summed per card payment. A refund of money that came back
    from a failed refund goes to the cards that one was for.
    """
    claim = session.scalars(select(Claim).where(Claim.claim_id == payout.claim_id)).first()
    if claim is None:
        return []
    if not claim.allocation_ids and claim.details.get("retry_of"):
        earlier = session.scalars(
            select(Claim).where(Claim.claim_id == bytes.fromhex(claim.details["retry_of"]))
        ).first()
        parts = [tuple(part) for part in (earlier.details.get("parts", []) if earlier else [])]
        claim.details = {**claim.details, "parts": [list(part) for part in parts]}
        return parts
    project = session.get(Project, payout.project_id)
    escrow = chain.escrow(project.escrow_address)
    milestones: dict[int, Any] = {}
    shares: dict[str, int] = defaultdict(int)
    for allocation_id in claim.allocation_ids:
        allocation = session.get(Allocation, allocation_id)
        donation = session.get(Donation, allocation.donation_id)
        if donation.kind == DonationKind.REDIRECT:
            continue  # money redirected here: its card is in another project's claims
        index = allocation.milestone_index
        if index not in milestones:
            milestones[index] = escrow.functions.milestone(index).call()
        funded, released = milestones[index][1], milestones[index][2]
        if funded:
            share = allocation.amount_qapik * (funded - released) // funded
            shares[donation.provider_payment_id] += share
    parts = [(payment, amount) for payment, amount in shares.items() if amount > 0]
    claim.details = {**claim.details, "parts": [list(part) for part in parts]}
    return parts


def execute_payouts(session: Session, bank: BankClient, chain: Contracts) -> int:
    """Asks the bank to act on every new instruction and anchors what it signed."""
    pending = session.scalars(
        select(Payout).where(Payout.status == PayoutStatus.INSTRUCTED).order_by(Payout.id)
    ).all()
    done = 0
    for payout in pending:
        project = session.get(Project, payout.project_id)
        try:
            if payout.kind == PayoutKind.PAYOUT:
                hashed, iban = _contractor_account(session, project)
                result = bank.payout(
                    instruction_id=payout.instruction_id,
                    amount=payout.amount_qapik,
                    contractor_hash=hashed,
                    iban=iban,
                )
            else:
                parts = refund_parts(session, chain, payout)
                if sum(amount for _, amount in parts) != payout.amount_qapik:
                    raise_alert(
                        session,
                        kind="refund_needs_a_person",
                        message=f"refund {payout.instruction_id} does not map onto card payments",
                        details={"instruction_id": payout.instruction_id, "parts": parts},
                        dedupe_key=f"refund_unmapped:{payout.instruction_id}",
                    )
                    continue
                result = bank.refund(
                    instruction_id=payout.instruction_id, amount=payout.amount_qapik, payments=parts
                )
        except ProviderError as exc:
            raise_alert(
                session,
                kind="bank_refused",
                message=f"the bank refused instruction {payout.instruction_id}: {exc}",
                details={"instruction_id": payout.instruction_id},
                dedupe_key=f"bank_refused:{payout.instruction_id}",
            )
            continue
        reference = bytes.fromhex(result["payment_ref"][2:])
        signature = bytes.fromhex(result["signature"][2:])
        payout.payment_ref = reference
        payout.bank_signature = signature
        paid = result["status"] == "paid"
        payout.status = PayoutStatus.BANK_PAID if paid else PayoutStatus.BANK_FAILED
        row = enqueue(
            session,
            kind="confirm_payout" if paid else "fail_payout",
            contract="BankPayoutVault",
            function="confirm" if paid else "fail",
            args=[payout.instruction_id, reference, signature],
            dedupe_key=f"settle_payout:{payout.instruction_id}",
            project_id=payout.project_id,
        )
        payout.outbox_id = row.id
        done += 1
    session.flush()
    return done


# ---------------------------------------------------------------- indexer handlers


def on_release_instructed(session: Session, event: ChainEvent) -> None:
    args = event.args
    release = session.scalars(
        select(Release)
        .where(
            Release.project_id == event.project_id,
            Release.milestone_index == args["milestone"],
            Release.status == ReleaseStatus.REQUESTED,
        )
        .order_by(Release.created_at.desc())
    ).first()
    if release is not None:
        release.instruction_id = args["instructionId"]
        release.status = ReleaseStatus.INSTRUCTED
    if session.scalar(select(Payout.id).where(Payout.instruction_id == args["instructionId"])):
        return
    session.add(
        Payout(
            instruction_id=args["instructionId"],
            kind=PayoutKind.PAYOUT,
            project_id=event.project_id,
            milestone_index=args["milestone"],
            amount_qapik=args["amount"],
        )
    )
    session.flush()


def on_refund_instructed(session: Session, event: ChainEvent) -> None:
    args = event.args
    if session.scalar(select(Payout.id).where(Payout.instruction_id == args["instructionId"])):
        return
    session.add(
        Payout(
            instruction_id=args["instructionId"],
            kind=PayoutKind.REFUND,
            project_id=event.project_id,
            holder=args["holder"],
            amount_qapik=args["amount"],
            claim_id=bytes.fromhex(args["claimId"][2:]),
        )
    )
    session.flush()


def on_payout_confirmed(session: Session, event: ChainEvent) -> None:
    payout = session.scalars(
        select(Payout).where(Payout.instruction_id == event.args["instructionId"])
    ).first()
    if payout is None:
        return
    payout.status = PayoutStatus.CONFIRMED
    if payout.kind == PayoutKind.PAYOUT:
        release = session.scalars(
            select(Release).where(Release.instruction_id == payout.instruction_id)
        ).first()
        if release is not None:
            release.status = ReleaseStatus.PAID


def on_payout_failed(session: Session, event: ChainEvent) -> None:
    payout = session.scalars(
        select(Payout).where(Payout.instruction_id == event.args["instructionId"])
    ).first()
    if payout is None:
        return
    payout.status = PayoutStatus.RETURNED
    if payout.kind == PayoutKind.PAYOUT:
        release = session.scalars(
            select(Release).where(Release.instruction_id == payout.instruction_id)
        ).first()
        if release is not None:
            release.status = ReleaseStatus.RETURNED
        raise_alert(
            session,
            kind="payout_returned",
            message=(
                f"the bank could not pay milestone {payout.milestone_index}; the money is back "
                "in escrow and waits for a person"
            ),
            details={"instruction_id": payout.instruction_id, "project_id": str(payout.project_id)},
            dedupe_key=f"payout_returned:{payout.instruction_id}",
        )
    else:
        # The escrow keeps the amount as the donor's retry balance; they choose again.
        claim = session.scalars(select(Claim).where(Claim.claim_id == payout.claim_id)).first()
        if claim is not None:
            claim.details = {**claim.details, "refund_failed": True}


def open_count(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count()).where(
                Payout.status.in_((PayoutStatus.INSTRUCTED, PayoutStatus.BANK_PAID))
            )
        )
        or 0
    )
