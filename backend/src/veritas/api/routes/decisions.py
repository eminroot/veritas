"""Decisions and money out over the API: the officer's queue and signed decisions, donor
votes, Pay-on-Proof pledges, stopping a project and donors' claims.

Every signed action has two steps. A GET returns the exact EIP-712 message for the phone to
sign, and a POST takes the signature. The server checks the signature itself before queueing
anything for the chain, so a mistake is refused here, not in a reverted transaction.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.api.deps import ChainDep, CurrentUser, DbSession, require_charity_member
from veritas.api.schemas import Input, Output
from veritas.chain import eip712
from veritas.chain.runtime import Chain
from veritas.core.hashing import to_hex
from veritas.db.models import (
    MemberRole,
    Milestone,
    MilestoneStatus,
    Officer,
    OfficerStatus,
    Project,
    ProjectStatus,
    User,
)
from veritas.db.models.decisions import Ballot, BallotStatus, ClaimAction
from veritas.db.models.money import Pledge
from veritas.db.session import db_now
from veritas.decisions import officer as officer_service
from veritas.decisions import pledges as pledge_service
from veritas.decisions import stops, voting
from veritas.payments.intake import current_passport
from veritas.services.errors import Forbidden, NotFound, Unavailable

router = APIRouter(tags=["decisions"])

Hex32 = Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]{64}$")]
Signature = Annotated[
    str,
    Field(
        pattern=r"^0x([0-9a-fA-F]{2})+$",
        max_length=2 + 2 * 65 * 20,
        description="A key's 65-byte signature, or a Safe's (up to 20 owners' signatures).",
    ),
]
Address = Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]{40}$")]


def _chain(chain: Chain | None) -> Chain:
    if chain is None:
        raise Unavailable("no_chain", "This API runs without a chain.")
    return chain


def _bytes(value: str | None) -> bytes | None:
    return bytes.fromhex(value[2:]) if value else None


def _project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFound("not_found", "There is no project with this id.")
    return project


def _milestone(db: Session, project: Project, index: int) -> Milestone:
    milestone = db.scalars(
        select(Milestone).where(Milestone.project_id == project.id, Milestone.index == index)
    ).first()
    if milestone is None:
        raise NotFound("not_found", "This project has no such milestone.")
    return milestone


def _project_officer(db: Session, user: User, project: Project) -> Officer:
    """The caller, if they are the officer this project's Passport names."""
    address = current_passport(db, project.id).officer.address
    officer = db.scalars(
        select(Officer).where(
            Officer.user_id == user.id,
            Officer.address == address,
            Officer.status == OfficerStatus.ACTIVE,
        )
    ).first()
    if officer is None:
        raise Forbidden("not_the_officer", "Only this project's Verification Officer can do this.")
    return officer


# ---------------------------------------------------------------- the officer


class QueueItem(Output):
    project_id: uuid.UUID
    project_title: str | None
    milestone: int
    milestone_title: str
    attempt: int
    bundle_hash: str | None
    evidence_cid: str | None
    report_hash: str | None
    checks_passed: bool | None
    amount_qapik: int


@router.get("/v1/officer/queue")
def officer_queue(user: CurrentUser, db: DbSession) -> list[QueueItem]:
    """Milestones whose checks are done and that wait for this officer's decision."""
    addresses = db.scalars(
        select(Officer.address).where(
            Officer.user_id == user.id, Officer.status == OfficerStatus.ACTIVE
        )
    ).all()
    if not addresses:
        raise Forbidden("not_an_officer", "Only Verification Officers have a review queue.")
    items = []
    rows = db.execute(
        select(Milestone, Project)
        .join(Project, Project.id == Milestone.project_id)
        .where(Milestone.status == MilestoneStatus.CHECKED, Project.status == ProjectStatus.LIVE)
        .order_by(Milestone.updated_at)
    ).all()
    for milestone, project in rows:
        if current_passport(db, project.id).officer.address not in addresses:
            continue
        items.append(
            QueueItem(
                project_id=project.id,
                project_title=project.title,
                milestone=milestone.index,
                milestone_title=milestone.title,
                attempt=milestone.attempt,
                bundle_hash=to_hex(milestone.bundle_hash) if milestone.bundle_hash else None,
                evidence_cid=milestone.evidence_cid,
                report_hash=to_hex(milestone.report_hash) if milestone.report_hash else None,
                checks_passed=milestone.checks_passed,
                amount_qapik=milestone.amount_qapik,
            )
        )
    return items


class DecisionIn(Input):
    approve: bool
    invoice_hash: Hex32 | None = None
    amount_qapik: int | None = Field(default=None, gt=0)
    override_checks: bool = False
    reason: str | None = Field(default=None, max_length=4000)
    signature: Signature


@router.get("/v1/projects/{project_id}/milestones/{index}/decision-message")
def decision_message(
    project_id: uuid.UUID,
    index: int,
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
    approve: bool,
    invoice_hash: Annotated[str | None, Query(pattern=r"^0x[0-9a-fA-F]{64}$")] = None,
    amount_qapik: int | None = None,
    override_checks: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    """The Decision message for the officer to sign, checked against the escrow's rules."""
    chain = _chain(chain)
    project = _project(db, project_id)
    _project_officer(db, user, project)
    milestone = _milestone(db, project, index)
    fields = {
        "approve": approve,
        "invoice_hash": _bytes(invoice_hash),
        "amount": amount_qapik,
        "override_checks": override_checks,
        "reason": reason,
    }
    officer_service.check_decision(project, milestone, **fields)
    message = officer_service.decision_message(project, milestone, **fields)
    return eip712.typed_data(chain.domain, "Decision", message)


@router.post("/v1/projects/{project_id}/milestones/{index}/decision", status_code=202)
def decide(
    project_id: uuid.UUID,
    index: int,
    body: DecisionIn,
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
) -> dict[str, Any]:
    chain = _chain(chain)
    project = _project(db, project_id)
    officer = _project_officer(db, user, project)
    milestone = _milestone(db, project, index)
    decision = officer_service.submit_decision(
        db,
        chain,
        project,
        milestone,
        officer,
        approve=body.approve,
        invoice_hash=_bytes(body.invoice_hash),
        amount=body.amount_qapik,
        override_checks=body.override_checks,
        reason=body.reason,
        signature=_bytes(body.signature) or b"",
    )
    return {"decision_id": str(decision.id), "status": "queued"}


# ---------------------------------------------------------------- votes


class BallotOut(Output):
    id: str
    kind: str
    milestone: int
    round: int
    eligible: int
    ends_at: datetime
    status: str
    yes: int
    no: int
    passed: bool | None


def _ballot_out(ballot: Ballot) -> BallotOut:
    return BallotOut(
        id=to_hex(ballot.id),
        kind=ballot.kind,
        milestone=ballot.milestone_index,
        round=ballot.round,
        eligible=ballot.eligible,
        ends_at=ballot.ends_at,
        status=ballot.status,
        yes=ballot.yes,
        no=ballot.no,
        passed=ballot.passed,
    )


@router.get("/v1/projects/{project_id}/ballots")
def project_ballots(project_id: uuid.UUID, db: DbSession) -> list[BallotOut]:
    ballots = db.scalars(
        select(Ballot).where(Ballot.project_id == project_id).order_by(Ballot.created_at)
    ).all()
    return [_ballot_out(b) for b in ballots]


@router.get("/v1/ballots/{ballot_id}/vote-message")
def vote_message(
    ballot_id: str, holder: str, approve: bool, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    chain = _chain(chain)
    ballot = voting.get_ballot(db, _bytes(ballot_id) or b"")
    return eip712.typed_data(chain.domain, "Vote", voting.vote_message(ballot, holder, approve))


class VoteIn(Input):
    holder: Address
    approve: bool
    signature: Signature


@router.post("/v1/ballots/{ballot_id}/votes", status_code=202)
def cast_vote(
    ballot_id: str, body: VoteIn, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    chain = _chain(chain)
    ballot = voting.get_ballot(db, _bytes(ballot_id) or b"")
    if ballot.status != BallotStatus.OPEN:
        raise NotFound("ballot_closed", "This vote has closed.")
    minimum = current_passport(db, ballot.project_id).decision.min_vote_qapik
    vote = voting.submit_vote(
        db,
        chain,
        ballot,
        holder=body.holder,
        approve=body.approve,
        signature=_bytes(body.signature) or b"",
        min_amount=minimum,
        now=db_now(db),
    )
    return {"vote_id": str(vote.id), "weight_qapik": vote.weight_qapik, "status": "queued"}


# ---------------------------------------------------------------- Pay-on-Proof


class PledgeIn(Input):
    amount_qapik: int = Field(gt=0, description="Charged each time a milestone is approved.")
    holder: Address
    card_number: str = Field(min_length=12, max_length=19)


class PledgeOut(Output):
    id: uuid.UUID
    project_id: uuid.UUID
    amount_qapik: int
    card_last4: str | None
    status: str


@router.post("/v1/projects/{project_id}/pledges", status_code=201)
def pledge(
    project_id: uuid.UUID, body: PledgeIn, user: CurrentUser, db: DbSession, request: Request
) -> PledgeOut:
    created = pledge_service.create_pledge(
        db,
        request.app.state.psp,
        project_id=project_id,
        user=user,
        holder=body.holder,
        amount=body.amount_qapik,
        card_number=body.card_number,
    )
    return PledgeOut.model_validate(created)


@router.get("/v1/pledges")
def my_pledges(user: CurrentUser, db: DbSession) -> list[PledgeOut]:
    rows = db.scalars(select(Pledge).where(Pledge.user_id == user.id)).all()
    return [PledgeOut.model_validate(row) for row in rows]


# ---------------------------------------------------------------- stopping


class ReasonIn(Input):
    reason: str = Field(min_length=1, max_length=4000)
    signature: Signature


@router.get("/v1/projects/{project_id}/withdraw-message")
def withdraw_message(
    project_id: uuid.UUID, reason: str, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    chain = _chain(chain)
    project = _project(db, project_id)
    require_charity_member(db, user, project.charity_id, MemberRole.ADMIN)
    return eip712.typed_data(chain.domain, "Withdraw", stops.withdraw_message(project, reason))


@router.post("/v1/projects/{project_id}/withdraw", status_code=202)
def withdraw(
    project_id: uuid.UUID, body: ReasonIn, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, str]:
    """The charity ends its project. Every donor then chooses a refund or a redirect."""
    chain = _chain(chain)
    project = _project(db, project_id)
    require_charity_member(db, user, project.charity_id, MemberRole.ADMIN)
    stops.withdraw(
        db,
        chain,
        project,
        reason=body.reason,
        signature=_bytes(body.signature) or b"",
    )
    return {"status": "queued"}


@router.get("/v1/projects/{project_id}/stop-message")
def stop_message(
    project_id: uuid.UUID, reason: str, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    chain = _chain(chain)
    project = _project(db, project_id)
    _project_officer(db, user, project)
    message = stops.stop_proposal_message(project, chain.contracts, reason)
    return eip712.typed_data(chain.domain, "StopProposal", message)


@router.post("/v1/projects/{project_id}/stop-proposal", status_code=202)
def propose_stop(
    project_id: uuid.UUID, body: ReasonIn, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, str]:
    """The officer asks the donors whether to stop the project."""
    chain = _chain(chain)
    project = _project(db, project_id)
    officer = _project_officer(db, user, project)
    stops.propose_stop(
        db,
        chain,
        project,
        officer,
        reason=body.reason,
        signature=_bytes(body.signature) or b"",
    )
    return {"status": "queued"}


# ---------------------------------------------------------------- claims


@router.get("/v1/projects/{project_id}/claim-message")
def claim_message(
    project_id: uuid.UUID,
    holder: str,
    action: ClaimAction,
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
    target_project_id: uuid.UUID | None = None,
    deadline: int | None = None,
) -> dict[str, Any]:
    """The Choice message for a donor to sign: a refund, or a redirect to a live project."""
    chain = _chain(chain)
    project = _project(db, project_id)
    target = stops.claim_target(db, action, target_project_id)
    deadline = deadline or int(time.time()) + 24 * 3600
    message = stops.claim_message(chain.contracts, project, holder, action, target, deadline)
    return eip712.typed_data(chain.domain, "Choice", message)


class ClaimIn(Input):
    holder: Address
    action: ClaimAction
    target_project_id: uuid.UUID | None = None
    deadline: int
    signature: Signature
    new_holder: Address | None = Field(
        default=None, description="Your key for the target project, for a redirect."
    )


@router.post("/v1/projects/{project_id}/claims", status_code=202)
def submit_claim(
    project_id: uuid.UUID, body: ClaimIn, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    chain = _chain(chain)
    project = _project(db, project_id)
    claim = stops.submit_claim(
        db,
        chain,
        project,
        user,
        holder=body.holder,
        action=body.action,
        target_project_id=body.target_project_id,
        deadline=body.deadline,
        signature=_bytes(body.signature) or b"",
        new_holder=body.new_holder,
    )
    return {"claim_id": str(claim.id), "status": "queued", "leaves": len(claim.allocation_ids)}
