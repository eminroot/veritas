"""The Verification Officer's decision on a checked milestone.

The officer signs a Decision message on their phone. It names the evidence bundle and the
check report they reviewed, so a decision can never be moved onto other evidence, and on
approval the contractor's invoice and the amount to pay. Approving a milestone whose hard
checks failed is an override and needs a written reason; so does any rejection. The reason
text stays off-chain and its SHA-256 goes on-chain with the decision.

The rules the escrow enforces are checked here first, so a bad decision is refused with a
clear message instead of a reverted transaction. The officer may sign with a key or a Safe
(chain/signatures.py). A decision the chain refused anyway does not count, so the officer can
sign the attempt again, a few times, as long as the escrow still waits for a decision.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain.outbox import enqueue_again, require_sent
from veritas.chain.runtime import Chain
from veritas.chain.signatures import signed_by
from veritas.core.hashing import sha256
from veritas.db.models import Milestone, MilestoneStatus, Officer, Project, ProjectStatus
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.models.decisions import OfficerDecision
from veritas.db.session import db_now
from veritas.services.errors import Conflict, Forbidden, Unprocessable

ZERO = bytes(32)
STATUS = 9
"""Where MilestoneEscrow.milestone(i) returns the status."""
CHECKED = 2
"""MilestoneEscrow.Status.Checked: waiting for the officer."""


def reason_hash(reason: str | None) -> bytes:
    return sha256(reason.strip().encode("utf-8")) if reason and reason.strip() else ZERO


def decision_message(
    project: Project,
    milestone: Milestone,
    *,
    approve: bool,
    invoice_hash: bytes | None,
    amount: int | None,
    override_checks: bool,
    reason: str | None,
) -> dict[str, Any]:
    if milestone.bundle_hash is None or milestone.report_hash is None:
        raise Conflict("not_checked", "This milestone has no checked evidence to decide on.")
    return {
        "projectId": project.id.bytes,
        "milestone": milestone.index,
        "attempt": milestone.attempt,
        "approve": approve,
        "bundleHash": milestone.bundle_hash,
        "reportHash": milestone.report_hash,
        "invoiceHash": (invoice_hash or ZERO) if approve else ZERO,
        "amount": (amount or 0) if approve else 0,
        "overrideChecks": override_checks,
        "reasonHash": reason_hash(reason),
    }


def check_decision(
    project: Project,
    milestone: Milestone,
    *,
    approve: bool,
    invoice_hash: bytes | None,
    amount: int | None,
    override_checks: bool,
    reason: str | None,
) -> None:
    """The escrow's rules, in words a person can act on."""
    if project.status != ProjectStatus.LIVE:
        raise Conflict(
            "project_not_live", f"The project is {project.status}; its milestones take no decision."
        )
    if milestone.status != MilestoneStatus.CHECKED:
        raise Conflict("not_checked", "Only a milestone whose checks are done can be decided.")
    has_reason = reason_hash(reason) != ZERO
    if not approve:
        if not has_reason:
            raise Unprocessable("reason_required", "Say why the milestone is rejected.")
        if override_checks:
            raise Unprocessable("override_on_reject", "Only an approval can override checks.")
        return
    if not invoice_hash or len(invoice_hash) != 32 or invoice_hash == ZERO:
        raise Unprocessable("invoice_required", "Approving needs the contractor's invoice.")
    if not amount or amount <= 0 or amount > milestone.amount_qapik:
        raise Unprocessable(
            "bad_amount",
            f"The amount must be between 1 qəpik and the milestone budget, "
            f"{milestone.amount_qapik} qəpik.",
        )
    if milestone.checks_passed and override_checks:
        raise Unprocessable("nothing_to_override", "Every hard check passed; no override.")
    if not milestone.checks_passed and not (override_checks and has_reason):
        raise Unprocessable(
            "override_required",
            "Some hard checks failed. Approving anyway is an override and needs a reason.",
        )


def submit_decision(
    session: Session,
    chain: Chain,
    project: Project,
    milestone: Milestone,
    officer: Officer,
    *,
    approve: bool,
    invoice_hash: bytes | None,
    amount: int | None,
    override_checks: bool,
    reason: str | None,
    signature: bytes,
) -> OfficerDecision:
    check_decision(
        project,
        milestone,
        approve=approve,
        invoice_hash=invoice_hash,
        amount=amount,
        override_checks=override_checks,
        reason=reason,
    )
    message = decision_message(
        project,
        milestone,
        approve=approve,
        invoice_hash=invoice_hash,
        amount=amount,
        override_checks=override_checks,
        reason=reason,
    )
    if not signed_by(chain.w3, chain.domain, "Decision", message, signature, officer.address):
        raise Forbidden("bad_signature", "The signature is not the officer's for this decision.")
    decided = session.scalars(
        select(OfficerDecision).where(
            OfficerDecision.project_id == project.id,
            OfficerDecision.milestone_index == milestone.index,
            OfficerDecision.attempt == milestone.attempt,
            OfficerDecision.failed_at.is_(None),
        )
    ).first()
    if decided is not None:
        call = session.get(ChainOutbox, decided.outbox_id) if decided.outbox_id else None
        refused = call is not None and call.status in (OutboxStatus.FAILED, OutboxStatus.CANCELLED)
        # A signed decision can reach the chain from any sender; only the escrow says whether
        # the milestone still waits for one.
        escrow = chain.contracts.escrow(project.escrow_address)
        still_checked = escrow.functions.milestone(milestone.index).call()[STATUS] == CHECKED
        if not refused or not still_checked:
            raise Conflict("already_decided", "This evidence already has the officer's decision.")
        decided.failed_at = db_now(session)  # the chain refused it; it never counted
        session.flush()
    decision = OfficerDecision(
        project_id=project.id,
        milestone_index=milestone.index,
        attempt=milestone.attempt,
        approve=approve,
        invoice_hash=message["invoiceHash"] if approve else None,
        amount_qapik=message["amount"] if approve else None,
        override_checks=override_checks,
        reason=reason.strip() if reason and reason.strip() else None,
        reason_hash=message["reasonHash"] if message["reasonHash"] != ZERO else None,
        signature=signature,
        officer_id=officer.id,
    )
    session.add(decision)
    row = enqueue_again(
        session,
        kind="officer_decision",
        contract="MilestoneEscrow",
        address=project.escrow_address,
        function="officerDecide",
        args=[
            (
                milestone.index,
                milestone.attempt,
                approve,
                message["invoiceHash"],
                message["amount"],
                override_checks,
                message["reasonHash"],
            ),
            signature,
        ],
        dedupe_key=f"officer_decision:{project.id}:{milestone.index}:{milestone.attempt}",
        project_id=project.id,
    )
    require_sent(row, "decision")
    decision.outbox_id = row.id
    session.flush()
    return decision
