"""Stopping a project, and giving every donor's money back or moving it on.

A project stops when the charity withdraws (signed by its key), when a stop vote the officer
proposed passes, or when a milestone's evidence deadline passes with nothing submitted, which
anyone may trigger and a job does. Then each donor signs a choice within the choice window:
a refund to their card, or a redirect to another live project. Whoever has not chosen when
the window closes gets the Passport's default.

A redirect moves the donor's share on-chain in one transaction. Its leaves in the target
project are then anchored in the next batch under the key the donor chose for that project,
so the move does not link their two keys beyond the redirect itself. A default redirect
keeps the donor's key. Only the account a donor key belongs to may send that key's choices,
and a key belongs to one account in every project (payments/holders.py), so the receipt the
redirect brings is the donor's to vote with and to recover.

Signatures are checked the way the escrow checks them: a key or a Safe (chain/signatures.py),
the charity against the key its escrow was launched with, and a donor against the key that
controls the holder on-chain now. A choice the chain refused can be signed again, a few
times; then the API says the chain refused it, and no choice waits for a payout in flight.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from eth_utils import to_checksum_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain import eip712
from veritas.chain.alerts import raise_alert
from veritas.chain.contracts import Contracts
from veritas.chain.leaves import DonationLeaf, new_salt
from veritas.chain.outbox import enqueue_again, require_sent
from veritas.chain.proofs import holder_leaves
from veritas.chain.runtime import Chain
from veritas.chain.signatures import signed_by
from veritas.db.models import Milestone, MilestoneStatus, Officer, Project, ProjectStatus, User
from veritas.db.models.chain import ChainEvent, ChainOutbox, OutboxStatus
from veritas.db.models.decisions import Claim, ClaimAction, ClaimStatus
from veritas.db.models.evidence import BundleStatus, EvidenceBundle
from veritas.db.models.money import (
    Allocation,
    AllocationStatus,
    Donation,
    DonationKind,
    DonationStatus,
    Receipt,
)
from veritas.decisions.officer import reason_hash
from veritas.decisions.recovery import controller_now, moving
from veritas.payments.holders import check_holder, holder_owner, holder_owners
from veritas.payments.intake import current_passport, remaining_needs
from veritas.services.errors import Conflict, Forbidden, NotFound, Unprocessable

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ACTIONS = {ClaimAction.REFUND: eip712.CHOICE_REFUND, ClaimAction.REDIRECT: eip712.CHOICE_REDIRECT}
STATUS = 9
"""Where MilestoneEscrow.milestone(i) returns the status."""
RELEASED = 6
"""MilestoneEscrow.Status.Released: the payout waits for the bank."""


def _live(project: Project) -> None:
    if project.status != ProjectStatus.LIVE or project.escrow_address is None:
        raise Conflict("not_live", "Only a live project can be stopped.")


# ---------------------------------------------------------------- stopping


def withdraw_message(project: Project, reason: str) -> dict[str, Any]:
    return {"projectId": project.id.bytes, "reasonHash": reason_hash(reason)}


def withdraw(
    session: Session,
    chain: Chain,
    project: Project,
    *,
    reason: str,
    signature: bytes,
) -> None:
    """The charity ends its own project, signed by the key the escrow was launched with,
    whatever the charity's key is now. The reason stays off-chain."""
    _live(project)
    if reason_hash(reason) == bytes(32):
        raise Unprocessable("reason_required", "Say why the project stops.")
    message = withdraw_message(project, reason)
    if not signed_by(
        chain.w3, chain.domain, "Withdraw", message, signature, project.charity_signer
    ):
        raise Forbidden(
            "bad_signature",
            f"The withdrawal is not signed by the key this project was launched with, "
            f"{project.charity_signer}.",
        )
    require_sent(
        enqueue_again(
            session,
            kind="withdraw",
            contract="MilestoneEscrow",
            address=project.escrow_address,
            function="withdraw",
            args=[message["reasonHash"], signature],
            dedupe_key=f"withdraw:{project.id}",
            project_id=project.id,
        ),
        "withdrawal",
    )


def stop_proposal_message(project: Project, chain: Contracts, reason: str) -> dict[str, Any]:
    round_ = chain.escrow(project.escrow_address).functions.stopRound().call() + 1
    return {"projectId": project.id.bytes, "round": round_, "reasonHash": reason_hash(reason)}


def propose_stop(
    session: Session,
    chain: Chain,
    project: Project,
    officer: Officer,
    *,
    reason: str,
    signature: bytes,
) -> None:
    """The officer asks the donors to stop the project."""
    _live(project)
    message = stop_proposal_message(project, chain.contracts, reason)
    if message["reasonHash"] == bytes(32):
        raise Unprocessable("reason_required", "Say why the project should stop.")
    if not signed_by(chain.w3, chain.domain, "StopProposal", message, signature, officer.address):
        raise Forbidden("bad_signature", "The proposal is not signed by the project's officer.")
    require_sent(
        enqueue_again(
            session,
            kind="propose_stop",
            contract="MilestoneEscrow",
            address=project.escrow_address,
            function="proposeStop",
            args=[message["reasonHash"], signature],
            dedupe_key=f"propose_stop:{project.id}:{message['round']}",
            project_id=project.id,
        ),
        "stop proposal",
    )


def stop_missed_deadlines(session: Session, now: datetime) -> int:
    """Stops live projects with a milestone past its evidence or resubmission deadline.

    The mirror follows finalised blocks, so evidence that reached the chain just in time may
    not show yet: a milestone whose signed evidence is still on its way is left alone, and a
    call that failed because the evidence had landed does not stop a later milestone's."""
    rows = session.execute(
        select(Milestone, Project)
        .join(Project, Project.id == Milestone.project_id)
        .where(Project.status == ProjectStatus.LIVE)
        .order_by(Milestone.index)
    ).all()
    stopped: set[uuid.UUID] = set()
    for milestone, project in rows:
        missed = (
            milestone.status == MilestoneStatus.FUNDING and now > milestone.evidence_deadline
        ) or (
            milestone.status == MilestoneStatus.REJECTED
            and milestone.resubmit_deadline is not None
            and now > milestone.resubmit_deadline
        )
        if not missed or project.id in stopped or _evidence_on_its_way(session, milestone):
            continue
        row = enqueue_again(
            session,
            kind="stop_missed_deadline",
            contract="MilestoneEscrow",
            address=project.escrow_address,
            function="stopForMissedDeadline",
            args=[milestone.index],
            dedupe_key=(
                f"stop_missed_deadline:{project.id}:{milestone.index}:{milestone.attempt + 1}"
            ),
            max_tries=3,
            project_id=project.id,
        )
        if row.status != OutboxStatus.FAILED:
            stopped.add(project.id)
    return len(stopped)


def _evidence_on_its_way(session: Session, milestone: Milestone) -> bool:
    """Signed evidence for the milestone's next attempt that the chain has not refused."""
    bundles = session.scalars(
        select(EvidenceBundle).where(
            EvidenceBundle.project_id == milestone.project_id,
            EvidenceBundle.milestone_index == milestone.index,
            EvidenceBundle.attempt == milestone.attempt + 1,
            EvidenceBundle.charity_signature.is_not(None),
            EvidenceBundle.status != BundleStatus.VOID,
        )
    )
    for bundle in bundles:
        call = (
            session.get(ChainOutbox, bundle.submit_outbox_id) if bundle.submit_outbox_id else None
        )
        if call is None or call.status not in (OutboxStatus.FAILED, OutboxStatus.CANCELLED):
            return True
    return False


# ---------------------------------------------------------------- claims


def pending_claim(session: Session, project_id: uuid.UUID, holder: str) -> Claim | None:
    """A choice of this donor's still on its way to the chain. One whose call failed (a
    deadline that passed, say) is marked failed, so it no longer blocks a new choice."""
    for claim in session.scalars(
        select(Claim).where(
            Claim.project_id == project_id,
            Claim.holder == holder,
            Claim.status == ClaimStatus.SUBMITTED,
        )
    ):
        call = session.get(ChainOutbox, claim.outbox_id) if claim.outbox_id else None
        if call is not None and call.status in (OutboxStatus.FAILED, OutboxStatus.CANCELLED):
            claim.status = ClaimStatus.FAILED
            continue
        return claim
    return None


def _ended(project: Project) -> None:
    if project.status not in (ProjectStatus.STOPPED, ProjectStatus.COMPLETED):
        raise Conflict("project_running", "Claims open once a project stops or completes.")


def claim_target(
    session: Session, action: ClaimAction, target_id: uuid.UUID | None
) -> Project | None:
    if action == ClaimAction.REFUND:
        return None
    target = session.get(Project, target_id) if target_id else None
    if target is None or target.status != ProjectStatus.LIVE or target.escrow_address is None:
        raise NotFound("no_target", "Redirect to a live project.")
    return target


def claim_message(
    chain: Contracts,
    project: Project,
    holder: str,
    action: ClaimAction,
    target: Project | None,
    deadline: int,
) -> dict[str, Any]:
    holder = to_checksum_address(holder)
    nonce = chain.escrow(project.escrow_address).functions.claimNonce(holder).call()
    return {
        "projectId": project.id.bytes,
        "holder": holder,
        "action": ACTIONS[action],
        "target": target.escrow_address if target else ZERO_ADDRESS,
        "nonce": nonce,
        "deadline": deadline,
    }


def submit_claim(
    session: Session,
    chain: Chain,
    project: Project,
    user: User,
    *,
    holder: str,
    action: ClaimAction,
    target_project_id: uuid.UUID | None,
    deadline: int,
    signature: bytes,
    new_holder: str | None = None,
) -> Claim:
    """A donor's signed choice for what is left of their money in a stopped project.

    Only the account the key belongs to may send it: the signature is public in the calldata
    of any earlier attempt, and the key a redirect names in the other project is not signed.
    """
    _ended(project)
    holder = to_checksum_address(holder)
    if holder_owner(session, holder) != user.id:
        raise Forbidden("not_the_donor", "This donor key does not belong to this account.")
    if pending_claim(session, project.id, holder) is not None:
        raise Conflict("claim_pending", "This donor's last choice is still on its way.")
    receipt = session.scalars(
        select(Receipt).where(Receipt.project_id == project.id, Receipt.holder == holder)
    ).first()
    if receipt is not None and moving(session, receipt):
        raise Conflict(
            "key_moving", "This donor's receipt is moving to a new key; choose once that is done."
        )
    target = claim_target(session, action, target_project_id)
    if target is not None:
        check_holder(session, to_checksum_address(new_holder or holder), user.id)
    message = claim_message(chain.contracts, project, holder, action, target, deadline)
    signer = controller_now(chain.contracts, project.id, holder)
    if not signed_by(chain.w3, chain.domain, "Choice", message, signature, signer):
        raise Forbidden("bad_signature", "The choice is not signed by this donor's key.")
    leaves = holder_leaves(session, project.id, holder)
    escrow = chain.contracts.escrow(project.escrow_address)
    retry = escrow.functions.retryBalance(holder).call()
    if not leaves and not retry:
        raise Conflict("nothing_to_claim", "This donor has nothing left in this project.")
    for index in sorted({leaf.milestone for leaf in leaves}):
        if escrow.functions.milestone(index).call()[STATUS] == RELEASED:
            raise Conflict(
                "payout_in_flight",
                f"Milestone {index}'s payout is waiting for the bank; every donor's share is "
                "measured once it is paid or returned, so choose then.",
            )
    details: dict[str, Any] = {}
    if new_holder and target is not None:
        details["new_holder"] = to_checksum_address(new_holder)
    if not leaves and retry:
        # The refund the bank returned: the latest claim that executed, not a later choice
        # the chain refused.
        returned = session.scalars(
            select(Claim)
            .where(
                Claim.project_id == project.id,
                Claim.holder == holder,
                Claim.claim_id.is_not(None),
            )
            .order_by(Claim.created_at.desc())
        ).first()
        if returned is not None:
            details["retry_of"] = returned.claim_id.hex()
    claim = Claim(
        project_id=project.id,
        holder=holder,
        action=action,
        target_project_id=target.id if target else None,
        nonce=message["nonce"],
        deadline=deadline,
        signature=signature,
        allocation_ids=[str(leaf.allocation_id) for leaf in leaves],
        user_id=user.id,
        details=details,
    )
    session.add(claim)
    # The nonce only moves when a claim succeeds, so after a failed one the next choice has
    # the same nonce: it gets a new row instead of the failed one.
    row = enqueue_again(
        session,
        kind="claim",
        contract="MilestoneEscrow",
        address=project.escrow_address,
        function="claim",
        args=[
            holder,
            message["action"],
            message["target"],
            deadline,
            [leaf.abi_value() for leaf in leaves],
            signature,
        ],
        dedupe_key=f"claim:{project.id}:{holder}:{message['nonce']}",
        project_id=project.id,
    )
    require_sent(row, "choice")
    claim.outbox_id = row.id
    session.flush()
    return claim


def _redirect_target(session: Session, project: Project, amount: int) -> Project | None:
    """For a default redirect: a live project in the same category with room for the money,
    the one that needs the most."""
    best, best_need = None, 0
    candidates = session.scalars(
        select(Project).where(
            Project.status == ProjectStatus.LIVE,
            Project.category == project.category,
            Project.id != project.id,
        )
    ).all()
    for candidate in candidates:
        need = sum(remaining_needs(session, candidate.id))
        if need >= amount and need > best_need:
            best, best_need = candidate, need
    return best


def apply_defaults(session: Session, chain: Contracts, now: datetime) -> int:
    """After the choice window, applies the Passport's default for every donor who did not
    choose."""
    applied = 0
    projects = session.scalars(
        select(Project).where(Project.status.in_((ProjectStatus.STOPPED, ProjectStatus.COMPLETED)))
    ).all()
    for project in projects:
        escrow = chain.escrow(project.escrow_address)
        if now.timestamp() <= escrow.functions.choiceDeadline().call():
            continue
        redirects = current_passport(session, project.id).stop.unclaimed == "redirect_same_category"
        holders = session.scalars(
            select(Allocation.holder)
            .where(
                Allocation.project_id == project.id,
                Allocation.status == AllocationStatus.IN_ESCROW,
            )
            .group_by(Allocation.holder)
        ).all()
        for holder in holders:
            if pending_claim(session, project.id, holder) is not None:
                continue
            leaves = holder_leaves(session, project.id, holder)
            target = None
            if redirects:
                target = _redirect_target(session, project, sum(leaf.amount for leaf in leaves))
                if target is None:
                    raise_alert(
                        session,
                        kind="no_redirect_target",
                        message=f"no live {project.category} project can take a default redirect",
                        details={"project_id": str(project.id), "holder": holder},
                        dedupe_key=f"no_redirect_target:{project.id}:{holder}",
                    )
                    continue
            owners = holder_owners(session, holder)
            claim = Claim(
                project_id=project.id,
                holder=holder,
                action=ClaimAction.REDIRECT if target else ClaimAction.REFUND,
                target_project_id=target.id if target else None,
                by_default=True,
                allocation_ids=[str(leaf.allocation_id) for leaf in leaves],
                # The donor's: the redirected money's receipt in the target is theirs.
                user_id=next(iter(owners)) if len(owners) == 1 else None,
            )
            session.add(claim)
            row = enqueue_again(
                session,
                kind="claim_default",
                contract="MilestoneEscrow",
                address=project.escrow_address,
                function="claimDefault",
                args=[
                    holder,
                    target.escrow_address if target else ZERO_ADDRESS,
                    [leaf.abi_value() for leaf in leaves],
                ],
                dedupe_key=f"claim_default:{project.id}:{holder}",
                max_tries=3,
                project_id=project.id,
            )
            claim.outbox_id = row.id
            applied += 1
    session.flush()
    return applied


# ---------------------------------------------------------------- indexer handlers


def on_claimed(session: Session, event: ChainEvent) -> None:
    args = event.args
    holder = args["holder"]
    claim = session.scalars(
        select(Claim)
        .where(
            Claim.project_id == event.project_id,
            Claim.holder == holder,
            Claim.status == ClaimStatus.SUBMITTED,
        )
        .order_by(Claim.created_at)
    ).first()
    if claim is None:  # claimed outside this API: still record it
        owners = holder_owners(session, holder)
        claim = Claim(
            project_id=event.project_id,
            holder=holder,
            action=ClaimAction.REFUND
            if args["action"] == eip712.CHOICE_REFUND
            else ClaimAction.REDIRECT,
            by_default=args["byDefault"],
            allocation_ids=[],
            user_id=next(iter(owners)) if len(owners) == 1 else None,
        )
        session.add(claim)
    claim.claim_id = bytes.fromhex(args["claimId"][2:])
    claim.amount_qapik = args["amount"]
    claim.status = ClaimStatus.EXECUTED
    for allocation_id in claim.allocation_ids:
        allocation = session.get(Allocation, uuid.UUID(allocation_id))
        if allocation is not None:
            allocation.status = AllocationStatus.CLAIMED
    session.flush()
    if args["action"] == eip712.CHOICE_REDIRECT:
        _redirected_donation(session, event, claim)


def _redirected_donation(session: Session, event: ChainEvent, claim: Claim) -> None:
    """New leaves in the target project for the money a redirect brought there."""
    received = session.scalars(
        select(ChainEvent).where(
            ChainEvent.tx_hash == event.tx_hash, ChainEvent.event == "RedirectReceived"
        )
    ).first()
    target = session.scalars(
        select(Project).where(Project.escrow_address == event.args["target"])
    ).first()
    if received is None or target is None:
        raise_alert(
            session,
            kind="redirect_unmatched",
            severity="critical",
            message="a redirect left this project but its arrival was not found",
            details={"tx_hash": "0x" + event.tx_hash.hex()},
            dedupe_key=f"redirect_unmatched:{event.tx_hash.hex()}",
        )
        return
    # The account the donor key belongs to: whoever sent the choice, or for a default, a
    # retried refund or a claim made outside the API, the key's account in this project.
    owners = holder_owners(session, claim.holder)
    donor = claim.user_id or (next(iter(owners)) if len(owners) == 1 else None)
    if donor is not None and owners - {donor}:
        raise_alert(
            session,
            kind="holder_shared",
            severity="critical",
            message=f"Redirected money lands under key {claim.holder}, which another account "
            "has used too; who its receipt belongs to needs a person.",
            details={"tx_hash": "0x" + event.tx_hash.hex(), "holder": claim.holder},
            dedupe_key=f"holder_shared:{claim.holder}",
        )
    if donor is None:
        raise_alert(
            session,
            kind="redirect_without_owner",
            severity="critical",
            message="money redirected into another project belongs to no account",
            details={"tx_hash": "0x" + event.tx_hash.hex(), "holder": claim.holder},
            dedupe_key=f"redirect_without_owner:{event.tx_hash.hex()}",
        )
    holder = claim.details.get("new_holder", claim.holder)
    donation = Donation(
        id=uuid.uuid4(),
        project_id=target.id,
        user_id=donor,
        holder=holder,
        amount_qapik=event.args["amount"],
        kind=DonationKind.REDIRECT,
        provider="redirect",
        provider_payment_id="0x" + claim.claim_id.hex(),
        trigger=claim.claim_id,
        status=DonationStatus.RECEIVED,
    )
    session.add(donation)
    session.flush()
    for index, part in enumerate(received.args["parts"]):
        if not part:
            continue
        leaf = DonationLeaf(
            donation_id=donation.id,
            holder=holder,
            project_id=target.id,
            milestone=index,
            amount=part,
            trigger=claim.claim_id,
            salt=new_salt(),
        )
        session.add(
            Allocation(
                donation_id=donation.id,
                project_id=target.id,
                milestone_index=index,
                amount_qapik=part,
                holder=holder,
                salt=leaf.salt,
                trigger=leaf.trigger,
                leaf_hash=leaf.hash(),
                credited=False,
            )
        )
    session.flush()
