"""Ballots and votes.

A vote opens on-chain when the officer approves a milestone, the officer proposes a stop, or
the charity proposes an amendment; the indexer records each ballot from its VoteOpened event.
A donor signs their vote on their phone. The API attaches their leaves and Merkle proofs and
the relayer submits it, so the contract can check eligibility without knowing who they are.
A job closes each ballot once its window ends.

The signature is checked against the key that controls the holder on-chain now, and no vote
is taken while the donor's receipt is moving to a new key, since it would revert behind the
move. A vote the chain refused does not count, so the donor may sign again, a few times,
unless it counted after all (anyone may send a signed vote); the chain says which.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from eth_utils import to_checksum_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain import eip712
from veritas.chain.outbox import enqueue, enqueue_again, require_sent
from veritas.chain.proofs import holder_leaves
from veritas.chain.runtime import Chain
from veritas.chain.signatures import signed_by
from veritas.db.models import Project
from veritas.db.models.chain import ChainEvent, ChainOutbox, OutboxStatus
from veritas.db.models.decisions import Ballot, BallotKind, BallotStatus, Vote, VoteStatus
from veritas.db.models.money import Receipt
from veritas.decisions.recovery import controller_now, moving
from veritas.services.errors import Conflict, Forbidden, NotFound, Unprocessable

KIND_CODES = {
    BallotKind.MILESTONE: eip712.BALLOT_MILESTONE,
    BallotKind.AMENDMENT: eip712.BALLOT_AMENDMENT,
    BallotKind.STOP: eip712.BALLOT_STOP,
}
KINDS_BY_CODE = {code: kind for kind, code in KIND_CODES.items()}


def vote_message(ballot: Ballot, holder: str, approve: bool) -> dict[str, Any]:
    return {
        "projectId": ballot.project_id.bytes,
        "holder": to_checksum_address(holder),
        "kind": KIND_CODES[BallotKind(ballot.kind)],
        "milestone": ballot.milestone_index,
        "round": ballot.round,
        "approve": approve,
    }


def submit_vote(
    session: Session,
    chain: Chain,
    ballot: Ballot,
    *,
    holder: str,
    approve: bool,
    signature: bytes,
    min_amount: int,
    now: datetime,
) -> Vote:
    holder = to_checksum_address(holder)
    if ballot.status != BallotStatus.OPEN or now >= ballot.ends_at:
        raise Conflict("ballot_closed", "This vote has closed.")
    earlier = session.scalars(
        select(Vote).where(
            Vote.ballot_id == ballot.id, Vote.holder == holder, Vote.status != VoteStatus.FAILED
        )
    ).first()
    if earlier is not None:
        call = session.get(ChainOutbox, earlier.outbox_id) if earlier.outbox_id else None
        refused = call is not None and call.status in (OutboxStatus.FAILED, OutboxStatus.CANCELLED)
        # Anyone may send a signed vote, so the relayer's copy can fail because the vote
        # already counted: only the chain says whether it did.
        voting = chain.contracts.get("VotingModule")
        if not refused or voting.functions.hasVoted(ballot.id, holder).call():
            raise Conflict("already_voted", "This donor has voted already.")
        earlier.status = VoteStatus.FAILED  # the chain refused it; it never counted
        session.flush()
    receipt = session.scalars(
        select(Receipt).where(Receipt.project_id == ballot.project_id, Receipt.holder == holder)
    ).first()
    if receipt is not None and moving(session, receipt):
        raise Conflict(
            "key_moving", "This donor's receipt is moving to a new key; vote once that is done."
        )
    message = vote_message(ballot, holder, approve)
    signer = controller_now(chain.contracts, ballot.project_id, holder)
    if not signed_by(chain.w3, chain.domain, "Vote", message, signature, signer):
        raise Forbidden("bad_signature", "The vote is not signed by this donor's key.")
    milestone = ballot.milestone_index if ballot.kind == BallotKind.MILESTONE else None
    leaves = holder_leaves(session, ballot.project_id, holder, milestone=milestone)
    weight = sum(leaf.amount for leaf in leaves)
    if weight < min_amount:
        raise Unprocessable(
            "not_eligible",
            f"Voting needs at least {min_amount} qəpik in escrow here; this donor has {weight}.",
        )
    vote = Vote(
        ballot_id=ballot.id,
        holder=holder,
        approve=approve,
        weight_qapik=weight,
        signature=signature,
    )
    session.add(vote)
    row = enqueue_again(
        session,
        kind="cast_vote",
        contract="VotingModule",
        function="castVoteBySig",
        args=[ballot.id, holder, approve, [leaf.abi_value() for leaf in leaves], signature],
        dedupe_key=f"cast_vote:{ballot.id.hex()}:{holder}",
        project_id=ballot.project_id,
    )
    require_sent(row, "vote")
    vote.outbox_id = row.id
    session.flush()
    return vote


def close_due_ballots(session: Session, now: datetime) -> int:
    """Queues `close` for every open ballot whose window has ended."""
    due = session.scalars(
        select(Ballot).where(
            Ballot.status == BallotStatus.OPEN,
            Ballot.ends_at <= now,
            Ballot.close_outbox_id.is_(None),
        )
    ).all()
    for ballot in due:
        row = enqueue(
            session,
            kind="close_ballot",
            contract="VotingModule",
            function="close",
            args=[ballot.id],
            dedupe_key=f"close_ballot:{ballot.id.hex()}:{int(ballot.ends_at.timestamp())}",
            project_id=ballot.project_id,
        )
        ballot.close_outbox_id = row.id
    session.flush()
    return len(due)


def get_ballot(session: Session, ballot_id: bytes) -> Ballot:
    ballot = session.get(Ballot, ballot_id)
    if ballot is None:
        raise NotFound("no_ballot", "There is no such vote.")
    return ballot


# ---------------------------------------------------------------- indexer handlers


def on_vote_opened(session: Session, event: ChainEvent) -> None:
    args = event.args
    ballot_id = bytes.fromhex(args["ballotId"][2:])
    if session.get(Ballot, ballot_id) is not None:
        return
    project_id = event.project_id
    if project_id is None or session.get(Project, project_id) is None:
        return
    session.add(
        Ballot(
            id=ballot_id,
            project_id=project_id,
            kind=KINDS_BY_CODE[args["kind"]],
            milestone_index=args["milestone"],
            round=args["round"],
            eligible=args["eligible"],
            ends_at=datetime.fromtimestamp(args["end"], UTC),
        )
    )
    session.flush()


def on_vote_cast(session: Session, event: ChainEvent) -> None:
    ballot = session.get(Ballot, bytes.fromhex(event.args["ballotId"][2:]), with_for_update=True)
    if ballot is None:
        return
    if event.args["approve"]:
        ballot.yes += 1
    else:
        ballot.no += 1
    vote = session.scalars(
        select(Vote).where(
            Vote.ballot_id == ballot.id,
            Vote.holder == event.args["holder"],
            Vote.status != VoteStatus.FAILED,
        )
    ).first()
    if vote is not None:
        vote.status = VoteStatus.COUNTED


def on_vote_extended(session: Session, event: ChainEvent) -> None:
    ballot = session.get(Ballot, bytes.fromhex(event.args["ballotId"][2:]))
    if ballot is not None:
        ballot.ends_at = datetime.fromtimestamp(event.args["end"], UTC)
        ballot.close_outbox_id = None  # close again when the extension ends


def on_vote_closed(session: Session, event: ChainEvent) -> None:
    ballot = session.get(Ballot, bytes.fromhex(event.args["ballotId"][2:]))
    if ballot is None:
        return
    ballot.status = BallotStatus.CLOSED
    ballot.passed = event.args["passed"]
    ballot.yes, ballot.no = event.args["yes"], event.args["no"]
    ballot.turnout_fallback = event.args["turnoutFallback"]
