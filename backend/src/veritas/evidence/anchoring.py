"""Anchoring a bundle: the charity's key signs it, and the relayer carries it to the escrow.

The charity signs the EIP-712 Evidence message (project, milestone, attempt, bundle hash) on
an admin's phone. With that signature the bundle goes into the outbox as two calls, in one
transaction and in this order: `submitEvidence` with the bundle hash, the public copy's CID
and the signature, then `recordChecks` with the report hash and whether the checks passed.
The relayer sends one sender's calls in order, so the checks are recorded right after the
evidence. A bundle whose checks failed is anchored all the same: the officer decides, and an
approval over failed checks needs a signed reason.

Every rule the escrow enforces is checked here first, so a bundle that would revert is
refused with a reason instead. The escrow takes evidence signed by the charity key it was
launched with (Project.charity_signer), whatever key the charity uses for later projects,
and only while the project is live. If the chain refuses the evidence anyway, the bundle
becomes void (capture.void_refused); if it takes the evidence but not the checks, a job sends
recordChecks again, since nothing else can move the milestone on.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.chain import eip712
from veritas.chain.alerts import raise_alert
from veritas.chain.outbox import enqueue, enqueue_again, failed_reason
from veritas.chain.runtime import Chain
from veritas.chain.signatures import signed_by
from veritas.db.models import Charity, Milestone, MilestoneStatus, Project, ProjectStatus, User
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.models.evidence import BundleStatus, CheckReport, EvidenceBundle
from veritas.db.session import db_now
from veritas.evidence.capture import (
    TAKES_EVIDENCE,
    evidence_deadline,
    signed_bundle,
    void_refused,
)
from veritas.evidence.publish import finalize_public_copy
from veritas.evidence.wording import baku_time
from veritas.services.errors import Conflict, Forbidden

ESCROW = "MilestoneEscrow"


def evidence_message(project: Project, bundle: EvidenceBundle) -> dict[str, Any]:
    return {
        "projectId": project.id.bytes,
        "milestone": bundle.milestone_index,
        "attempt": bundle.attempt,
        "bundleHash": bundle.bundle_hash,
    }


CHECKS_PAUSES = (
    timedelta(minutes=10),
    timedelta(hours=1),
    timedelta(hours=6),
    timedelta(hours=24),
    timedelta(hours=48),
    timedelta(hours=72),
)
"""How long to wait after each refused recordChecks before sending it again: together over
six days, longer than replacing the relayer's key takes (48 hours)."""
MAX_CHECKS_TRIES = len(CHECKS_PAUSES) + 1


def dedupe_keys(bundle: EvidenceBundle) -> tuple[str, str]:
    """One pair per bundle: another bundle for the same attempt, after this one became void,
    gets its own calls."""
    return f"submit_evidence:{bundle.id}", f"record_checks:{bundle.id}"


def check_anchorable(
    session: Session,
    chain: Chain | None,
    project: Project,
    milestone: Milestone,
    bundle: EvidenceBundle,
    now: datetime,
) -> Chain:
    """Refuse, with a reason, a bundle the escrow would not take now. Returns the chain."""
    if chain is None:
        raise Conflict("no_chain", "This API runs without a chain, so evidence cannot be anchored.")
    if project.status != ProjectStatus.LIVE or project.escrow_address is None:
        raise Conflict(
            "project_not_live",
            f"The project is {project.status}; its escrow takes no more evidence.",
        )
    if bundle.status != BundleStatus.PUBLISHED or bundle.charity_signature is not None:
        raise Conflict(
            "not_anchorable",
            f"This bundle is {bundle.status}"
            + (" and already signed" if bundle.charity_signature is not None else "")
            + "; a bundle is signed once, after its public copy is published.",
        )
    if milestone.status not in TAKES_EVIDENCE:
        raise Conflict(
            "milestone_not_open",
            f"Milestone {milestone.index} is {milestone.status.replace('_', ' ')}; it takes "
            "evidence only while it is funding or after a rejection.",
        )
    if milestone.attempt + 1 != bundle.attempt:
        raise Conflict(
            "attempt_moved",
            f"This bundle was captured for attempt {bundle.attempt}, but milestone "
            f"{milestone.index} is waiting for attempt {milestone.attempt + 1}; capture new "
            "evidence.",
        )
    deadline = evidence_deadline(milestone)
    if now > deadline:
        raise Conflict(
            "deadline_passed",
            f"The deadline for milestone {milestone.index}'s evidence was {baku_time(deadline)}.",
        )
    void_refused(session, project.id, milestone.index, bundle.attempt)
    if signed_bundle(session, project.id, milestone.index, bundle.attempt) is not None:
        raise Conflict(
            "evidence_in_flight",
            f"Other evidence for attempt {bundle.attempt} of milestone {milestone.index} is "
            "already signed.",
        )
    if session.scalars(
        select(ChainOutbox.id).where(ChainOutbox.dedupe_key.in_(dedupe_keys(bundle)))
    ).first():
        raise Conflict(
            "evidence_in_flight",
            f"Evidence for attempt {bundle.attempt} of milestone {milestone.index} is already "
            "queued for the chain.",
        )
    return chain


def evidence_typed_data(chain: Chain, project: Project, bundle: EvidenceBundle) -> dict[str, Any]:
    """The eth_signTypedData_v4 JSON the charity's key signs."""
    return eip712.typed_data(chain.domain, "Evidence", evidence_message(project, bundle))


def anchor_bundle(
    session: Session,
    chain: Chain,
    project: Project,
    bundle: EvidenceBundle,
    charity: Charity,
    user: User,
    signature: bytes,
    now: datetime,
    *,
    photos: Collection[int] = (),
) -> tuple[ChainOutbox, ChainOutbox]:
    """Store the charity's signature and queue both chain calls. `check_anchorable` first.

    `photos` are the photos the signer confirmed may go public; the public copy becomes final
    with only those (publish.finalize_public_copy), and its CID is the one anchored."""
    message = evidence_message(project, bundle)
    if not signed_by(
        chain.w3, chain.domain, "Evidence", message, signature, project.charity_signer
    ):
        raise Forbidden(
            "bad_signature",
            "The evidence is not signed by the key this project was launched with, "
            f"{project.charity_signer}. The escrow keeps that key even after the charity "
            "changes its key for later projects.",
        )
    report = session.scalars(select(CheckReport).where(CheckReport.bundle_id == bundle.id)).one()
    finalize_public_copy(session, bundle, photos)
    assert bundle.public_cid is not None

    bundle.charity_signature = signature
    bundle.signed_by = user.id
    bundle.signed_at = now
    submit_key, checks_key = dedupe_keys(bundle)
    submit = enqueue(
        session,
        kind="submit_evidence",
        contract=ESCROW,
        address=project.escrow_address,
        function="submitEvidence",
        args=[bundle.milestone_index, bundle.bundle_hash, bundle.public_cid, signature],
        dedupe_key=submit_key,
        project_id=project.id,
    )
    checks = enqueue(
        session,
        kind="record_checks",
        contract=ESCROW,
        address=project.escrow_address,
        function="recordChecks",
        args=[bundle.milestone_index, bundle.attempt, report.sha256, report.passed],
        dedupe_key=checks_key,
        project_id=project.id,
    )
    bundle.submit_outbox_id = submit.id
    bundle.checks_outbox_id = checks.id
    session.flush()
    return submit, checks


def resend_checks(session: Session) -> int:
    """Queue recordChecks again for evidence that landed while its checks did not.

    Only the relayer can record checks, so after a refused recordChecks the milestone would
    stay EvidenceSubmitted for good: no decision, no new evidence, no deadline stop. While the
    escrow still waits for this attempt's checks, they are sent again, with a growing pause
    (CHECKS_PAUSES), so a relayer key being replaced does not use the tries up. A row a person
    cancelled is their decision and stays so. When the tries are used up, a person is told.
    """
    now = db_now(session)
    sent = 0
    for bundle in session.scalars(
        select(EvidenceBundle).where(
            EvidenceBundle.status == BundleStatus.PUBLISHED,
            EvidenceBundle.charity_signature.is_not(None),
            EvidenceBundle.checks_outbox_id.is_not(None),
        )
    ):
        submit = session.get(ChainOutbox, bundle.submit_outbox_id)
        checks = session.get(ChainOutbox, bundle.checks_outbox_id)
        if submit is None or submit.status != OutboxStatus.CONFIRMED:
            continue
        if checks is None or checks.status != OutboxStatus.FAILED:
            continue
        project = session.get_one(Project, bundle.project_id)
        milestone = session.scalars(
            select(Milestone).where(
                Milestone.project_id == project.id, Milestone.index == bundle.milestone_index
            )
        ).one()
        if (
            project.status != ProjectStatus.LIVE
            or milestone.status != MilestoneStatus.EVIDENCE_SUBMITTED
            or milestone.attempt != bundle.attempt
        ):
            continue
        key = dedupe_keys(bundle)[1]
        tries = (
            session.scalar(
                select(func.count()).where(
                    (ChainOutbox.dedupe_key == key)
                    | ChainOutbox.dedupe_key.startswith(key + ":", autoescape=True)
                )
            )
            or 1
        )
        if tries >= MAX_CHECKS_TRIES:
            raise_alert(
                session,
                kind="evidence_checks_stuck",
                severity="critical",
                message=f"recordChecks for milestone {bundle.milestone_index}, attempt "
                f"{bundle.attempt} of project {project.id} was refused {tries} times, last "
                f"with {failed_reason(checks)}; the milestone cannot move on until it is sent.",
                details={"bundle_id": str(bundle.id)},
                dedupe_key=f"evidence_checks_stuck:{bundle.id}",
            )
            continue
        if now < checks.updated_at + CHECKS_PAUSES[tries - 1]:
            continue
        report = session.scalars(
            select(CheckReport).where(CheckReport.bundle_id == bundle.id)
        ).one()
        row = enqueue_again(
            session,
            kind="record_checks",
            contract=ESCROW,
            address=project.escrow_address,
            function="recordChecks",
            args=[bundle.milestone_index, bundle.attempt, report.sha256, report.passed],
            dedupe_key=key,
            max_tries=MAX_CHECKS_TRIES,
            project_id=project.id,
        )
        bundle.checks_outbox_id = row.id
        sent += 1
    session.flush()
    return sent
