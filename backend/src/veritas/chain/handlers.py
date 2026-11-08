"""What the indexer does with each event: move database records forward from the chain.

Each handler checks the event against what the database expected and raises an alert when
they differ. The database follows the chain, never the other way round. Projects and the
milestone mirror live here; money, evidence and decisions register their own handlers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.chain.indexer import Handlers
from veritas.db.models import (
    Milestone,
    MilestoneStatus,
    PassportStatus,
    PassportVersion,
    Project,
    ProjectStatus,
)
from veritas.db.models.chain import ChainEvent

ESCROW = "MilestoneEscrow"


def _bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("0x"))


def _mismatch(session: Session, event: ChainEvent, what: str, **details: object) -> None:
    raise_alert(
        session,
        kind="event_mismatch",
        severity="critical",
        message=f"{event.contract}.{event.event}: {what}",
        details={"tx_hash": "0x" + event.tx_hash.hex(), "log_index": event.log_index, **details},
        dedupe_key=f"event_mismatch:{event.tx_hash.hex()}:{event.log_index}",
    )


def _project(session: Session, event: ChainEvent) -> Project | None:
    if event.project_id is None:
        return None
    return session.get(Project, event.project_id, with_for_update=True)


def _milestone(session: Session, event: ChainEvent, index: int | None = None) -> Milestone | None:
    if event.project_id is None:
        return None
    index = event.args["milestone"] if index is None else index
    return session.scalars(
        select(Milestone)
        .where(Milestone.project_id == event.project_id, Milestone.index == index)
        .with_for_update()
    ).first()


# ---------------------------------------------------------------- projects


def project_created(session: Session, event: ChainEvent) -> None:
    project = _project(session, event)
    if project is None:
        return  # the indexer already raised an alert for a project it does not know
    published = session.scalars(
        select(PassportVersion).where(
            PassportVersion.project_id == project.id,
            PassportVersion.version == 1,
            PassportVersion.status != PassportStatus.DRAFT,
        )
    ).first()
    on_chain = _bytes(event.args["passportHash"])
    if published is None or published.sha256 != on_chain:
        _mismatch(
            session,
            event,
            "the launched Passport hash is not the one this database published",
            project_id=str(project.id),
            on_chain="0x" + on_chain.hex(),
        )
        return
    project.escrow_address = event.args["escrow"]
    if project.status == ProjectStatus.PUBLISHED:
        project.status = ProjectStatus.LIVE


def project_stopped(session: Session, event: ChainEvent) -> None:
    project = _project(session, event)
    if project is not None:
        project.status = ProjectStatus.STOPPED


def all_milestones_paid(session: Session, event: ChainEvent) -> None:
    project = _project(session, event)
    if project is not None and project.status == ProjectStatus.LIVE:
        project.status = ProjectStatus.COMPLETED


# ---------------------------------------------------------------- the milestone mirror


def credited(session: Session, event: ChainEvent) -> None:
    for index, amount in enumerate(event.args["amounts"]):
        if amount:
            milestone = _milestone(session, event, index)
            if milestone is not None:
                milestone.funded_qapik += amount


def redirect_received(session: Session, event: ChainEvent) -> None:
    for index, amount in enumerate(event.args["parts"]):
        if amount:
            milestone = _milestone(session, event, index)
            if milestone is not None:
                milestone.funded_qapik += amount


def evidence_submitted(session: Session, event: ChainEvent) -> None:
    milestone = _milestone(session, event)
    if milestone is None:
        return
    milestone.status = MilestoneStatus.EVIDENCE_SUBMITTED
    milestone.attempt = event.args["attempt"]
    milestone.bundle_hash = _bytes(event.args["bundleHash"])
    milestone.evidence_cid = event.args["cid"]
    milestone.report_hash = None
    milestone.checks_passed = None
    milestone.invoice_hash = None
    milestone.approved_qapik = None


def checks_recorded(session: Session, event: ChainEvent) -> None:
    milestone = _milestone(session, event)
    if milestone is None:
        return
    if milestone.attempt != event.args["attempt"]:
        _mismatch(session, event, "checks recorded for an attempt the database does not have")
        return
    milestone.status = MilestoneStatus.CHECKED
    milestone.report_hash = _bytes(event.args["reportHash"])
    milestone.checks_passed = event.args["passed"]


def officer_decided(session: Session, event: ChainEvent) -> None:
    milestone = _milestone(session, event)
    if milestone is None or not event.args["approve"]:
        return  # a rejection arrives as MilestoneRejected in the same transaction
    milestone.status = MilestoneStatus.OFFICER_APPROVED
    milestone.invoice_hash = _bytes(event.args["invoiceHash"])
    milestone.approved_qapik = event.args["amount"]


def milestone_status(status: MilestoneStatus):
    def handler(session: Session, event: ChainEvent) -> None:
        milestone = _milestone(session, event)
        if milestone is not None:
            milestone.status = status

    return handler


def milestone_rejected(session: Session, event: ChainEvent) -> None:
    milestone = _milestone(session, event)
    if milestone is None:
        return
    milestone.status = MilestoneStatus.REJECTED
    milestone.resubmit_deadline = datetime.fromtimestamp(event.args["resubmitDeadline"], UTC)


def vote_opened_for_milestone(session: Session, event: ChainEvent) -> None:
    if event.args["kind"] != 0:  # BALLOT_MILESTONE
        return
    milestone = _milestone(session, event)
    if milestone is not None:
        milestone.status = MilestoneStatus.VOTING


def build_handlers() -> Handlers:
    handlers = Handlers()
    handlers.on("EscrowFactory", "ProjectCreated")(project_created)
    handlers.on(ESCROW, "ProjectStopped")(project_stopped)
    handlers.on(ESCROW, "AllMilestonesPaid")(all_milestones_paid)

    handlers.on(ESCROW, "Credited")(credited)
    handlers.on(ESCROW, "RedirectReceived")(redirect_received)
    handlers.on(ESCROW, "EvidenceSubmitted")(evidence_submitted)
    handlers.on(ESCROW, "ChecksRecorded")(checks_recorded)
    handlers.on(ESCROW, "OfficerDecided")(officer_decided)
    handlers.on(ESCROW, "MilestoneApproved")(milestone_status(MilestoneStatus.APPROVED))
    handlers.on(ESCROW, "MilestoneRejected")(milestone_rejected)
    handlers.on(ESCROW, "MilestoneReleased")(milestone_status(MilestoneStatus.RELEASED))
    handlers.on(ESCROW, "MilestonePaid")(milestone_status(MilestoneStatus.PAID))
    handlers.on(ESCROW, "PayoutReturned")(milestone_status(MilestoneStatus.APPROVED))
    handlers.on("VotingModule", "VoteOpened")(vote_opened_for_milestone)

    handlers.expect("launch_project", "EscrowFactory", "ProjectCreated")
    handlers.expect("register_charity", "VeritasHub", "CharitySet")
    handlers.expect("register_officer", "VeritasHub", "OfficerSet")
    handlers.expect("submit_evidence", ESCROW, "EvidenceSubmitted")
    handlers.expect("record_checks", ESCROW, "ChecksRecorded")
    handlers.expect("officer_decision", ESCROW, "OfficerDecided")

    # Each area adds its own; imported here so the chain layer does not depend on them.
    from veritas.decisions import events as decision_events
    from veritas.evidence import events as evidence_events
    from veritas.payments import events as payment_events

    payment_events.register(handlers)
    evidence_events.register(handlers)
    decision_events.register(handlers)
    return handlers
