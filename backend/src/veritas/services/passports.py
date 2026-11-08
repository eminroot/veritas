"""Passport drafts, the checks before publishing, and publishing itself.

A draft is any JSON object, saved as the charity types it: incomplete drafts are
normal, and the problems list says what is still missing. Publishing turns the
draft into a `Passport`, checks it against what Veritas knows (the charity, the
contractor, the officer, the project, the version), and stores the canonical
bytes exactly as they were hashed. Those bytes are what gets served, pinned to
IPFS and anchored on-chain; nothing re-serialises them. The milestones, budget
lines and sites tables are then rebuilt from the published Passport.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from veritas.chain import eip712
from veritas.chain.outbox import enqueue
from veritas.chain.project import ProjectConfig
from veritas.chain.project import launch_message as launch_fields
from veritas.chain.registrations import latest_registration
from veritas.chain.runtime import Chain
from veritas.chain.signatures import signed_by
from veritas.core.hashing import sha256
from veritas.db.models import (
    BudgetLine,
    Charity,
    CharityStatus,
    Contractor,
    ContractorStatus,
    Milestone,
    Officer,
    OfficerStatus,
    PassportStatus,
    PassportVersion,
    Project,
    ProjectStatus,
    RegistryStatus,
    Site,
    User,
)
from veritas.db.models.chain import ChainOutbox, OutboxStatus
from veritas.db.session import db_now
from veritas.passport import models as pm
from veritas.passport.errors import Problem, check_passport
from veritas.passport.models import PASSPORT_FORMAT, Passport
from veritas.services.cid import raw_cid
from veritas.services.errors import (
    Conflict,
    Forbidden,
    NotFound,
    PayloadTooLarge,
    Unprocessable,
)

MAX_DRAFT_BYTES = 1_000_000

# Until the escrow exists nobody has given money, so the charity may still publish
# a corrected version. After that a change needs a donor vote (a later phase).
EDITABLE_PROJECTS = (ProjectStatus.DRAFT, ProjectStatus.PUBLISHED)


def starter_draft(project_id: uuid.UUID, charity: Charity, version: int = 1) -> dict[str, Any]:
    return {
        "format": PASSPORT_FORMAT,
        "project_id": str(project_id),
        "version": version,
        "charity": {"legal_name": charity.legal_name, "voen": charity.voen},
    }


def create_project(
    session: Session, charity: Charity, user: User, *, project_id: uuid.UUID | None = None
) -> tuple[Project, PassportVersion]:
    """A new project with a version 1 draft that already names the charity.

    `project_id` is for seed data and tests; the API always lets it be generated.
    """
    project = Project(id=project_id or uuid.uuid4(), charity_id=charity.id, created_by=user.id)
    session.add(project)
    session.flush()
    draft = PassportVersion(
        project_id=project.id,
        version=1,
        draft_json=starter_draft(project.id, charity),
        created_by=user.id,
    )
    session.add(draft)
    session.flush()
    return project, draft


def current_draft(session: Session, project: Project) -> PassportVersion | None:
    return session.scalars(
        select(PassportVersion).where(
            PassportVersion.project_id == project.id,
            PassportVersion.status == PassportStatus.DRAFT,
        )
    ).first()


def published_version(session: Session, project: Project) -> PassportVersion | None:
    return session.scalars(
        select(PassportVersion).where(
            PassportVersion.project_id == project.id,
            PassportVersion.status == PassportStatus.PUBLISHED,
        )
    ).first()


def save_draft(
    session: Session, project: Project, user: User, data: dict[str, Any]
) -> PassportVersion:
    """Store `data` as the draft, starting the next version's draft if there is none."""
    _check_storable(data)
    if project.status == ProjectStatus.LIVE:
        from veritas.services.amendments import amendment_pending  # amendments imports this module

        if amendment_pending(session, project):
            raise Conflict(
                "amendment_pending",
                "An amendment of this Passport is waiting for the donors' vote.",
            )
    else:
        _check_editable(project, session)
    draft = current_draft(session, project)
    if draft is None:
        latest = session.scalar(
            select(func.max(PassportVersion.version)).where(
                PassportVersion.project_id == project.id
            )
        )
        draft = PassportVersion(
            project_id=project.id, version=(latest or 0) + 1, draft_json=data, created_by=user.id
        )
        session.add(draft)
    else:
        draft.draft_json = data
    session.flush()
    return draft


MAX_PASSPORT_BYTES = 256 * 1024
"""One IPFS block: the Passport's CID is computed here as a single raw block, so a larger
document would get a CID that IPFS would not give it."""


def draft_problems(
    session: Session, project: Project, draft: PassportVersion
) -> tuple[Passport | None, list[Problem]]:
    """Everything that stops the draft from being published, in readable form.

    First the Passport's own rules. Once those pass, the references: the ids and
    VÖENs must match this project and charity, the contractor must be verified
    and the officer active. The Passport is returned once its own rules pass.
    """
    passport, problems = check_passport(draft.draft_json)
    if passport is None:
        return None, problems
    return passport, _reference_problems(session, project, draft, passport)


def _reference_problems(
    session: Session, project: Project, draft: PassportVersion, passport: Passport
) -> list[Problem]:
    problems: list[Problem] = []
    size = len(passport.canonical_bytes())
    if size > MAX_PASSPORT_BYTES:
        problems.append(
            _problem(
                "",
                f"the Passport is {size} bytes as canonical JSON; it is published as one IPFS "
                f"block, so at most {MAX_PASSPORT_BYTES} bytes. Draw the sites with fewer points",
            )
        )
    if passport.project_id != project.id:
        problems.append(_problem("project_id", f"must be {project.id}, the id of this project"))
    if passport.version != draft.version:
        problems.append(
            _problem("version", f"must be {draft.version}, the next version of this Passport")
        )
    charity = session.get_one(Charity, project.charity_id)
    if passport.charity.voen != charity.voen:
        problems.append(
            _problem("charity.voen", f"must be {charity.voen}, the VÖEN of your charity")
        )

    contractor = session.scalars(
        select(Contractor).where(Contractor.voen == passport.contractor.voen)
    ).first()
    if contractor is None:
        problems.append(
            _problem("contractor.voen", "no contractor with this VÖEN is registered yet")
        )
    elif contractor.status != ContractorStatus.VERIFIED:
        problems.append(_problem("contractor.voen", "this contractor is not verified yet"))
    elif contractor.registry_status in (RegistryStatus.INACTIVE, RegistryStatus.NOT_FOUND):
        problems.append(
            _problem("contractor.voen", "the tax registry lists this VÖEN as inactive or unknown")
        )

    officer = session.scalars(
        select(Officer).where(Officer.address == passport.officer.address)
    ).first()
    if officer is None:
        problems.append(
            _problem("officer.address", "no Verification Officer is registered with this address")
        )
    elif officer.status != OfficerStatus.ACTIVE:
        problems.append(_problem("officer.address", "this Verification Officer is not active"))
    return problems


def _publishable(session: Session, project: Project) -> tuple[Charity, PassportVersion, Passport]:
    charity = session.get_one(Charity, project.charity_id)
    if charity.status != CharityStatus.VERIFIED:
        raise Conflict(
            "charity_not_verified", "The charity must be verified before it can publish a Passport."
        )
    _check_editable(project, session)
    draft = current_draft(session, project)
    if draft is None:
        raise NotFound("no_draft", "There is no draft Passport to publish.")
    passport, problems = draft_problems(session, project, draft)
    if passport is None or problems:
        raise Unprocessable(
            "passport_invalid",
            "The Passport has problems to fix before it can be published.",
            details=list(problems),
        )
    return charity, draft, passport


def _launch_fields(
    session: Session, project: Project, charity: Charity, passport: Passport
) -> dict[str, Any]:
    if charity.signer_address is None:
        raise Conflict("no_signing_key", "Set the charity's signing key before launching.")
    if passport.version != 1:
        raise Conflict("not_a_launch", "Only version 1 launches; later versions are amendments.")
    data = passport.canonical_bytes()
    config = ProjectConfig.from_passport(passport, charity.signer_address)
    return launch_fields(passport, config, sha256(data), raw_cid(data))


def launch_message(session: Session, project: Project, chain: Chain) -> dict[str, Any]:
    """The ProjectLaunch message the charity's key signs to publish and launch the draft.

    It binds the Passport's hash and CID to the exact rules the escrow will enforce, so a
    signature for this draft cannot launch anything else.
    """
    charity, _, passport = _publishable(session, project)
    fields = _launch_fields(session, project, charity, passport)
    return eip712.typed_data(chain.domain, "ProjectLaunch", fields)


def publish_passport(
    session: Session,
    project: Project,
    user: User,
    *,
    charity_signature: bytes | None = None,
    chain: Chain | None = None,
) -> PassportVersion:
    """Publish the project's draft. The caller has checked `user` is an admin of its charity.

    Refuses unless the charity is verified and the draft has no problems at all.
    Stores the canonical bytes, their SHA-256 and CID, supersedes the previous
    version, and rebuilds the milestone tables. With a chain, publishing is the launch:
    the charity's signature over the ProjectLaunch message is required, and the
    factory call goes into the outbox in this same transaction.
    """
    session.refresh(project, with_for_update=True)
    charity, draft, passport = _publishable(session, project)
    launching = chain is not None
    if chain is not None:
        if not charity_signature:
            raise Unprocessable(
                "signature_required", "Sign the launch message with the charity's key to publish."
            )
        fields = _launch_fields(session, project, charity, passport)
        signer = charity.signer_address or ""
        if not signed_by(
            chain.w3, chain.domain, "ProjectLaunch", fields, charity_signature, signer
        ):
            raise Forbidden("bad_signature", "The launch is not signed by the charity's key.")

    publish_version(
        session, project, draft, passport, published_by=user.id, charity_signature=charity_signature
    )
    project.status = ProjectStatus.PUBLISHED
    session.flush()
    if launching:
        data = passport.canonical_bytes()
        _queue_launch(session, project, charity, passport, data, charity_signature or b"")
    return draft


def publish_version(
    session: Session,
    project: Project,
    draft: PassportVersion,
    passport: Passport,
    *,
    published_by: uuid.UUID | None,
    charity_signature: bytes | None,
) -> None:
    """Turn a draft into the published version: its exact canonical bytes, their hash and
    CID. The previous version is superseded and the milestone tables are rebuilt. Used at
    launch, and when the chain records an amendment the donors voted for."""
    data = passport.canonical_bytes()
    now = db_now(session)
    previous = published_version(session, project)
    if previous is not None:
        previous.status = PassportStatus.SUPERSEDED
        # Flush first: a partial unique index allows one published version at a time.
        session.flush()

    draft.status = PassportStatus.PUBLISHED
    draft.draft_json = None
    draft.canonical_bytes = data
    draft.sha256 = sha256(data)
    draft.cid = raw_cid(data)
    draft.charity_signature = charity_signature
    draft.published_at = now
    draft.published_by = published_by

    project.title = passport.title
    project.category = passport.category
    project.total_qapik = passport.total_qapik
    project.published_at = project.published_at or now
    session.flush()
    _rebuild_milestones(session, project, passport)


def _queue_launch(
    session: Session,
    project: Project,
    charity: Charity,
    passport: Passport,
    data: bytes,
    signature: bytes,
) -> ChainOutbox:
    """The factory call, waiting for the admin's registration of the charity and officer."""
    config = ProjectConfig.from_passport(passport, charity.signer_address or "")
    project.charity_signer = config.charity
    waits = [
        row
        for row in (
            latest_registration(session, "register_charity", config.charity),
            latest_registration(session, "register_officer", config.officer),
        )
        if row is not None and row.status != OutboxStatus.CONFIRMED
    ]
    row = enqueue(
        session,
        kind="launch_project",
        contract="EscrowFactory",
        function="createProject",
        args=[config.abi_value(), sha256(data), raw_cid(data), signature],
        dedupe_key=f"launch_project:{project.id}",
        project_id=project.id,
    )
    if waits:
        row.depends_on = max(item.id for item in waits)
    session.flush()
    return row


def _rebuild_milestones(session: Session, project: Project, passport: Passport) -> None:
    """Make milestones, budget_lines and sites match the published Passport.

    Milestone rows are updated in place, so their ids stay the same from one
    version to the next. Budget lines and sites are simply replaced.
    """
    rows = {
        row.index: row
        for row in session.scalars(select(Milestone).where(Milestone.project_id == project.id))
    }
    if rows:
        ids = [row.id for row in rows.values()]
        session.execute(delete(BudgetLine).where(BudgetLine.milestone_id.in_(ids)))
        session.execute(delete(Site).where(Site.milestone_id.in_(ids)))

    current: list[tuple[Milestone, pm.Milestone]] = []
    for spec in passport.milestones:
        row = rows.pop(spec.index, None)
        if row is None:
            row = Milestone(project_id=project.id, index=spec.index)
            session.add(row)
        row.title = spec.title
        row.amount_qapik = spec.amount_qapik
        row.window_opens = spec.window.opens
        row.window_closes = spec.window.closes
        row.opens_at = spec.window.opens_at()
        row.closes_at = spec.window.closes_at()
        row.evidence_deadline = passport.evidence_deadline(spec.index)
        row.passport_version = passport.version
        current.append((row, spec))
    for stale in rows.values():
        session.delete(stale)
    session.flush()

    for row, spec in current:
        for position, line in enumerate(spec.budget):
            session.add(
                BudgetLine(
                    milestone_id=row.id,
                    position=position,
                    item=line.item,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price_qapik=line.unit_price_qapik,
                    amount_qapik=line.amount_qapik,
                )
            )
        session.add(Site(milestone_id=row.id, geom=WKTElement(polygon_wkt(spec.site), srid=4326)))
    session.flush()


def polygon_wkt(site: pm.Site) -> str:
    """The Passport's GeoJSON polygon as WKT, longitude first like GeoJSON."""
    rings = (", ".join(f"{lon!r} {lat!r}" for lon, lat in ring) for ring in site.coordinates)
    return "POLYGON(" + ", ".join(f"({ring})" for ring in rings) + ")"


def _problem(path: str, message: str) -> Problem:
    return Problem(path=path, message=message)


def _check_editable(project: Project, session: Session | None = None) -> None:
    if project.status not in EDITABLE_PROJECTS:
        raise Conflict(
            "project_locked",
            f"This project is {project.status}, so its Passport can no longer change here.",
        )
    if session is not None and session.scalar(
        select(ChainOutbox.id).where(
            ChainOutbox.project_id == project.id, ChainOutbox.kind == "launch_project"
        )
    ):
        raise Conflict(
            "project_locked",
            "This project is launching on-chain, so its Passport can only change by amendment.",
        )


def _check_storable(data: dict[str, Any]) -> None:
    """Refuse what PostgreSQL's JSONB cannot hold, before it becomes a server error."""
    try:
        text = json.dumps(data, allow_nan=False, ensure_ascii=False)
    except ValueError:
        raise Unprocessable(
            "draft_not_storable",
            "Numbers in the draft must be finite, NaN and Infinity are not JSON.",
        ) from None
    if _has_nul(data):
        raise Unprocessable(
            "draft_not_storable", "Text in the draft cannot contain NUL characters."
        )
    if len(text.encode("utf-8")) > MAX_DRAFT_BYTES:
        raise PayloadTooLarge(
            "draft_too_large", f"The draft is larger than {MAX_DRAFT_BYTES // 1000} KB."
        )


def _has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(key) or _has_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_nul(item) for item in value)
    return False
