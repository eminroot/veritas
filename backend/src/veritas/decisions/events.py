"""The indexer handlers for decisions and money out.

Opening a vote is a Veritas claim (how many donors may vote), so it is queued here, in the
indexer's transaction, the moment the event that calls for it is final.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from veritas.chain.indexer import Handlers
from veritas.chain.outbox import enqueue
from veritas.chain.proofs import eligible_voters
from veritas.db.models import Project
from veritas.db.models.chain import ChainEvent
from veritas.decisions import payouts, pledges, stops, voting
from veritas.payments.intake import current_passport
from veritas.services import amendments

ESCROW = "MilestoneEscrow"
MAX_UINT32 = 2**32 - 1


def _project_and_minimum(session: Session, event: ChainEvent) -> tuple[Project, int] | None:
    project = session.get(Project, event.project_id) if event.project_id else None
    if project is None or project.escrow_address is None:
        return None
    return project, current_passport(session, project.id).decision.min_vote_qapik


def open_milestone_vote(session: Session, event: ChainEvent) -> None:
    if not event.args["approve"]:
        return
    found = _project_and_minimum(session, event)
    if found is None:
        return
    project, minimum = found
    index = event.args["milestone"]
    eligible = min(eligible_voters(session, project.id, minimum, index), MAX_UINT32)
    enqueue(
        session,
        kind="open_vote",
        contract=ESCROW,
        address=project.escrow_address,
        function="openMilestoneVote",
        args=[index, eligible],
        dedupe_key=f"open_vote:{project.id}:{index}:{event.args['attempt']}",
        project_id=project.id,
    )


def open_stop_vote(session: Session, event: ChainEvent) -> None:
    found = _project_and_minimum(session, event)
    if found is None:
        return
    project, minimum = found
    eligible = min(eligible_voters(session, project.id, minimum), MAX_UINT32)
    enqueue(
        session,
        kind="open_stop_vote",
        contract=ESCROW,
        address=project.escrow_address,
        function="openStopVote",
        args=[eligible],
        dedupe_key=f"open_stop_vote:{project.id}:{event.args['round']}",
        project_id=project.id,
    )


def open_amendment_vote(session: Session, event: ChainEvent) -> None:
    found = _project_and_minimum(session, event)
    if found is None:
        return
    project, minimum = found
    eligible = min(eligible_voters(session, project.id, minimum), MAX_UINT32)
    enqueue(
        session,
        kind="open_amendment_vote",
        contract="PassportRegistry",
        function="openAmendmentVote",
        args=[project.id.bytes, eligible],
        dedupe_key=f"open_amendment_vote:{project.id}:{event.args['round']}",
        project_id=project.id,
    )


def register(handlers: Handlers) -> None:
    handlers.on("VotingModule", "VoteOpened")(voting.on_vote_opened)
    handlers.on("VotingModule", "VoteCast")(voting.on_vote_cast)
    handlers.on("VotingModule", "VoteExtended")(voting.on_vote_extended)
    handlers.on("VotingModule", "VoteClosed")(voting.on_vote_closed)
    handlers.on(ESCROW, "OfficerDecided")(open_milestone_vote)
    handlers.on(ESCROW, "StopProposed")(open_stop_vote)
    handlers.on("PassportRegistry", "AmendmentProposed")(open_amendment_vote)
    handlers.on(ESCROW, "MilestoneApproved")(pledges.on_milestone_approved)
    handlers.on("BankPayoutVault", "ReleaseInstructed")(payouts.on_release_instructed)
    handlers.on("BankPayoutVault", "RefundInstructed")(payouts.on_refund_instructed)
    handlers.on("BankPayoutVault", "PayoutConfirmed")(payouts.on_payout_confirmed)
    handlers.on("BankPayoutVault", "PayoutFailed")(payouts.on_payout_failed)
    handlers.on(ESCROW, "Claimed")(stops.on_claimed)
    handlers.on("PassportRegistry", "PassportRecorded")(amendments.on_passport_recorded)

    handlers.expect("open_vote", "VotingModule", "VoteOpened")
    handlers.expect("open_stop_vote", "VotingModule", "VoteOpened")
    handlers.expect("open_amendment_vote", "VotingModule", "VoteOpened")
    handlers.expect("cast_vote", "VotingModule", "VoteCast")
    handlers.expect("release", ESCROW, "MilestoneReleased")
    handlers.expect("confirm_payout", "BankPayoutVault", "PayoutConfirmed")
    handlers.expect("fail_payout", "BankPayoutVault", "PayoutFailed")
    handlers.expect("withdraw", ESCROW, "ProjectStopped")
    handlers.expect("stop_missed_deadline", ESCROW, "ProjectStopped")
    handlers.expect("propose_stop", ESCROW, "StopProposed")
    handlers.expect("claim", ESCROW, "Claimed")
    handlers.expect("claim_default", ESCROW, "Claimed")
    handlers.expect("propose_amendment", "PassportRegistry", "AmendmentProposed")
    handlers.expect("request_rotation", "ReceiptToken", "RotationRequested")
    handlers.expect("cancel_rotation", "ReceiptToken", "RotationCancelled")
    handlers.expect("finalize_rotation", "ReceiptToken", "KeyRotated")
    handlers.expect("rotate_key", "ReceiptToken", "KeyRotated")
