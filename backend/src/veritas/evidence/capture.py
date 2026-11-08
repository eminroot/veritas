"""Capture sessions: the one-time challenge code a field worker shows in a photo, and when a
milestone can take evidence at all.

A session is for one milestone and one attempt, captured with one registered phone. Its code
is valid for `capture_session_minutes` (15 by default), and everything has to be captured in
that time; check 3 says how that sits with the milestone's window and its grace period.
Files and the manifest may arrive a little later, until `upload_until`, because work sites
often have a weak signal. A milestone has at
most one open session at a time, and a code is never handed out twice.

A milestone takes evidence while it is funding, until its evidence deadline, and after a
rejection, until its resubmission deadline; the escrow refuses anything else. All times
come from the database clock.

Signed evidence blocks new captures for its attempt while it is on its way to the chain. If
the chain refuses it, the bundle becomes void, with the reason, and the attempt takes new
evidence: the signature stays on record, but nothing waits for a call that will never land.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.chain.outbox import failed_reason
from veritas.db.models import (
    Device,
    Milestone,
    MilestoneStatus,
    PassportVersion,
    Project,
    ProjectStatus,
    Site,
    User,
)
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.models.evidence import BundleStatus, CaptureSession, CaptureStatus, EvidenceBundle
from veritas.db.session import db_now
from veritas.evidence.wording import baku_day, baku_time
from veritas.passport.models import Passport, ProofItem, load_passport
from veritas.services.errors import Conflict, Forbidden, NotFound
from veritas.services.passports import published_version
from veritas.settings import Settings

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
"""No 0 or O, no 1 or I: the code is read off paper and screens, by people and by OCR."""
CODE_LENGTH = 6

TAKES_EVIDENCE = (MilestoneStatus.FUNDING, MilestoneStatus.REJECTED)


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def evidence_deadline(milestone: Milestone) -> datetime:
    """The last moment the escrow takes evidence for the milestone's next attempt."""
    if milestone.status == MilestoneStatus.REJECTED and milestone.resubmit_deadline is not None:
        return milestone.resubmit_deadline
    return milestone.evidence_deadline


def find_milestone(session: Session, project: Project, index: int) -> Milestone:
    milestone = session.scalars(
        select(Milestone).where(Milestone.project_id == project.id, Milestone.index == index)
    ).first()
    if milestone is None:
        raise NotFound("not_found", f"This project has no milestone {index}.")
    return milestone


def signed_bundle(
    session: Session, project_id: uuid.UUID, index: int, attempt: int
) -> EvidenceBundle | None:
    """The bundle the charity signed for this attempt and the chain has not refused. There is
    at most one."""
    return session.scalars(
        select(EvidenceBundle).where(
            EvidenceBundle.project_id == project_id,
            EvidenceBundle.milestone_index == index,
            EvidenceBundle.attempt == attempt,
            EvidenceBundle.charity_signature.is_not(None),
            EvidenceBundle.status != BundleStatus.VOID,
        )
    ).first()


REFUSED = (OutboxStatus.FAILED, OutboxStatus.CANCELLED)


def void_refused(session: Session, project_id: uuid.UUID, index: int, attempt: int) -> None:
    """Void a signed bundle whose submitEvidence the chain refused (a bad signature, a relayer
    key being replaced), so the attempt takes new evidence.

    The relayer never retries a refused call, and the signature cannot be changed or reused,
    so without this the milestone would wait for evidence that never arrives. A bundle whose
    evidence did land stays: only its recordChecks can be missing, and a job sends it again.
    """
    bundle = signed_bundle(session, project_id, index, attempt)
    if bundle is None or bundle.status == BundleStatus.ANCHORED:
        return
    submit = session.get(ChainOutbox, bundle.submit_outbox_id) if bundle.submit_outbox_id else None
    if submit is None or submit.status not in REFUSED:
        return
    now = db_now(session)
    bundle.status = BundleStatus.VOID
    bundle.voided_at = now
    bundle.void_reason = f"The chain refused it: {failed_reason(submit)}"
    raise_alert(
        session,
        kind="evidence_void",
        message=f"Signed evidence for milestone {index}, attempt {attempt} of project "
        f"{project_id} was refused on-chain and is void; the charity can sign new evidence.",
        details={"bundle_id": str(bundle.id), "reason": bundle.void_reason},
        dedupe_key=f"evidence_void:{bundle.id}",
    )
    session.flush()


def check_takes_evidence(
    session: Session, project: Project, milestone: Milestone, now: datetime
) -> None:
    """Refuse, in words a field worker can act on, when the milestone cannot take evidence."""
    if project.status != ProjectStatus.LIVE or project.escrow_address is None:
        raise Conflict(
            "project_not_live", "Evidence can be captured once the project is live on-chain."
        )
    if milestone.status not in TAKES_EVIDENCE:
        raise Conflict(
            "milestone_not_open",
            f"Milestone {milestone.index} is {milestone.status.replace('_', ' ')}; it takes "
            "evidence only while it is funding or after a rejection.",
        )
    if now < milestone.opens_at:
        raise Conflict(
            "window_not_open",
            f"Milestone {milestone.index}'s window opens on {baku_day(milestone.opens_at)}; "
            "evidence can be captured from then.",
        )
    deadline = evidence_deadline(milestone)
    if now > deadline:
        raise Conflict(
            "deadline_passed",
            f"The deadline for milestone {milestone.index}'s evidence was {baku_time(deadline)}.",
        )
    void_refused(session, project.id, milestone.index, milestone.attempt + 1)
    if signed_bundle(session, project.id, milestone.index, milestone.attempt + 1) is not None:
        raise Conflict(
            "evidence_in_flight",
            f"Evidence for milestone {milestone.index} is signed and on its way to the chain; "
            "wait until it is anchored.",
        )


def capture_device(session: Session, user: User, address: str) -> Device:
    """The caller's own registered, unrevoked key with this address."""
    device = session.scalars(select(Device).where(Device.address == address)).first()
    if device is None or device.user_id != user.id:
        raise Forbidden(
            "device_not_yours", "Capture with a device key you registered on your account."
        )
    if device.revoked_at is not None:
        raise Forbidden("device_revoked", "This device key was revoked; register the phone again.")
    return device


def expire_stale(session: Session, project_id: uuid.UUID, index: int, now: datetime) -> None:
    """Mark open sessions as expired whose upload time has passed, or whose device key was
    revoked: nothing can finish those, so they must not keep the milestone's one open slot."""
    revoked = select(Device.address).where(Device.revoked_at.is_not(None))
    session.execute(
        update(CaptureSession)
        .where(
            CaptureSession.project_id == project_id,
            CaptureSession.milestone_index == index,
            CaptureSession.status == CaptureStatus.OPEN,
            (CaptureSession.upload_until < now) | CaptureSession.device_address.in_(revoked),
        )
        .values(status=CaptureStatus.EXPIRED)
    )


def start_session(
    session: Session,
    settings: Settings,
    project: Project,
    milestone: Milestone,
    user: User,
    device: Device,
    now: datetime,
) -> CaptureSession:
    """Open a capture session. The caller has checked that `user` is a member of the charity."""
    session.refresh(milestone, with_for_update=True)
    check_takes_evidence(session, project, milestone, now)
    expire_stale(session, project.id, milestone.index, now)
    current = session.scalars(
        select(CaptureSession).where(
            CaptureSession.project_id == project.id,
            CaptureSession.milestone_index == milestone.index,
            CaptureSession.status == CaptureStatus.OPEN,
        )
    ).first()
    if current is not None:
        raise Conflict(
            "session_open",
            f"A capture session for milestone {milestone.index} is open until "
            f"{baku_time(current.upload_until)}; finish it or wait until then.",
        )
    expires_at = now + timedelta(minutes=settings.capture_session_minutes)
    capture = CaptureSession(
        project_id=project.id,
        milestone_index=milestone.index,
        attempt=milestone.attempt + 1,
        created_by=user.id,
        device_address=device.address,
        challenge_code=_unused_code(session),
        issued_at=now,
        expires_at=expires_at,
        upload_until=expires_at + timedelta(minutes=settings.evidence_upload_grace_minutes),
    )
    session.add(capture)
    session.flush()
    return capture


def effective_status(capture: CaptureSession, now: datetime) -> str:
    """The status a person should see: an open session past its upload time has expired."""
    if capture.status == CaptureStatus.OPEN and now > capture.upload_until:
        return CaptureStatus.EXPIRED
    return capture.status


def geofence(session: Session, milestone: Milestone) -> list[dict[str, Any]]:
    """The milestone's sites as GeoJSON polygons, straight from PostGIS."""
    rows = session.scalars(
        select(func.ST_AsGeoJSON(Site.geom))
        .where(Site.milestone_id == milestone.id)
        .order_by(Site.created_at, Site.id)
    )
    return [json.loads(row) for row in rows]


def published_passport(session: Session, project: Project) -> tuple[PassportVersion, Passport]:
    version = published_version(session, project)
    if version is None or version.canonical_bytes is None:
        raise Conflict("not_published", "This project has no published Passport.")
    return version, load_passport(version.canonical_bytes)


def checklist(passport: Passport, index: int) -> list[ProofItem]:
    """What the Passport promised as proof for the milestone."""
    return list(passport.milestones[index].proof)


def _unused_code(session: Session) -> str:
    for _ in range(10):
        code = new_code()
        taken = session.scalars(
            select(CaptureSession.id).where(CaptureSession.challenge_code == code)
        ).first()
        if taken is None:
            return code
    raise Conflict("try_again", "Could not find an unused challenge code; try again.")
