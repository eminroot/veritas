"""Projects and their Passports: drafts, problems, publishing, and the public pages.

The published Passport is served as the exact bytes that were hashed, so anyone
can check `sha256(body)` against the hash on-chain without trusting this API.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Path, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from veritas.api.deps import ChainDep, CurrentUser, DbSession, require_charity_member
from veritas.api.schemas import Input, Output, ProblemOut
from veritas.core.hashing import to_hex
from veritas.db.models import (
    BudgetLine,
    Charity,
    MemberRole,
    Milestone,
    PassportStatus,
    PassportVersion,
    Project,
    Site,
    User,
)
from veritas.passport.models import Category
from veritas.services.amendments import amendment_message, propose_amendment
from veritas.services.errors import NotFound
from veritas.services.passports import (
    create_project,
    current_draft,
    draft_problems,
    launch_message,
    publish_passport,
    save_draft,
)

router = APIRouter(prefix="/v1/projects", tags=["projects"])


class ProjectIn(Input):
    charity_id: uuid.UUID


class ProjectOut(Output):
    id: uuid.UUID
    charity_id: uuid.UUID
    status: str
    title: str | None
    category: str | None
    total_qapik: int | None
    escrow_address: str | None
    published_at: datetime | None
    created_at: datetime


class Draft(BaseModel):
    project_id: uuid.UUID
    version: int
    draft: dict[str, Any]
    problems: list[ProblemOut]
    updated_at: datetime


class Validation(BaseModel):
    version: int
    problems: list[ProblemOut]
    sha256: str | None = Field(
        description="SHA-256 of the canonical bytes, once there are no problems left."
    )


class PassportRef(BaseModel):
    version: int
    sha256: str
    cid: str
    published_at: datetime
    url: str = Field(description="The published bytes, exactly as hashed.")


class CharityRef(BaseModel):
    id: uuid.UUID
    legal_name: str
    voen: str


class ProjectSummary(BaseModel):
    id: uuid.UUID
    status: str
    title: str | None
    category: str | None
    total_qapik: int | None
    escrow_address: str | None
    published_at: datetime | None
    charity: CharityRef
    passport: PassportRef


class BudgetLineOut(BaseModel):
    position: int
    item: str
    quantity: int
    unit: str
    unit_price_qapik: int
    amount_qapik: int


class MilestoneOut(BaseModel):
    index: int
    title: str
    amount_qapik: int
    window_opens: date
    window_closes: date
    opens_at: datetime
    closes_at: datetime
    evidence_deadline: datetime
    status: str
    budget: list[BudgetLineOut]
    sites: list[dict[str, Any]] = Field(description="GeoJSON polygons.")


class ProjectDetail(ProjectSummary):
    milestones: list[MilestoneOut]


class CharityProject(BaseModel):
    id: uuid.UUID
    status: str
    title: str | None
    draft_version: int | None
    published_version: int | None
    created_at: datetime


def _member_project(
    db: Session, user: User, project_id: uuid.UUID, role: MemberRole | None = None
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFound("not_found", "There is no project with this id.")
    require_charity_member(db, user, project.charity_id, role)
    return project


def _passport_ref(version: PassportVersion) -> PassportRef:
    assert version.sha256 is not None and version.cid is not None
    assert version.published_at is not None
    return PassportRef(
        version=version.version,
        sha256=to_hex(version.sha256),
        cid=version.cid,
        published_at=version.published_at,
        url=f"/v1/projects/{version.project_id}/passports/{version.version}",
    )


def _draft(db: Session, project: Project, draft: PassportVersion) -> Draft:
    _, problems = draft_problems(db, project, draft)
    return Draft(
        project_id=project.id,
        version=draft.version,
        draft=draft.draft_json or {},
        problems=[ProblemOut(**problem) for problem in problems],
        updated_at=draft.updated_at,
    )


def _published_projects() -> Select[tuple[Project, Charity, PassportVersion]]:
    return (
        select(Project, Charity, PassportVersion)
        .join(Charity, Charity.id == Project.charity_id)
        .join(
            PassportVersion,
            and_(
                PassportVersion.project_id == Project.id,
                PassportVersion.status == PassportStatus.PUBLISHED,
            ),
        )
    )


def _summary(project: Project, charity: Charity, version: PassportVersion) -> dict[str, Any]:
    return {
        "id": project.id,
        "status": project.status,
        "title": project.title,
        "category": project.category,
        "total_qapik": project.total_qapik,
        "escrow_address": project.escrow_address,
        "published_at": project.published_at,
        "charity": CharityRef(id=charity.id, legal_name=charity.legal_name, voen=charity.voen),
        "passport": _passport_ref(version),
    }


@router.post("", status_code=201)
def new_project(body: ProjectIn, user: CurrentUser, db: DbSession) -> ProjectOut:
    """Start a project with a draft Passport that already names the charity."""
    charity = require_charity_member(db, user, body.charity_id)
    project, _ = create_project(db, charity, user)
    return ProjectOut.model_validate(project)


@router.get("")
def list_projects(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    charity_id: uuid.UUID | None = None,
    category: Category | None = None,
) -> list[ProjectSummary]:
    """Published projects, newest first. Public."""
    query = _published_projects().order_by(Project.published_at.desc(), Project.id)
    if charity_id is not None:
        query = query.where(Project.charity_id == charity_id)
    if category is not None:
        query = query.where(Project.category == category)
    rows = db.execute(query.limit(limit).offset(offset)).all()
    return [ProjectSummary(**_summary(*row)) for row in rows]


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, db: DbSession) -> ProjectDetail:
    """A published project with its milestones, budgets and sites. Public."""
    row = db.execute(_published_projects().where(Project.id == project_id)).first()
    if row is None:
        raise NotFound("not_found", "There is no published project with this id.")
    milestones = db.scalars(
        select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.index)
    ).all()
    ids = [milestone.id for milestone in milestones]
    lines: dict[uuid.UUID, list[BudgetLineOut]] = {milestone_id: [] for milestone_id in ids}
    for line in db.scalars(
        select(BudgetLine).where(BudgetLine.milestone_id.in_(ids)).order_by(BudgetLine.position)
    ):
        lines[line.milestone_id].append(
            BudgetLineOut(
                position=line.position,
                item=line.item,
                quantity=line.quantity,
                unit=line.unit,
                unit_price_qapik=line.unit_price_qapik,
                amount_qapik=line.amount_qapik,
            )
        )
    sites: dict[uuid.UUID, list[dict[str, Any]]] = {milestone_id: [] for milestone_id in ids}
    for milestone_id, geojson in db.execute(
        select(Site.milestone_id, func.ST_AsGeoJSON(Site.geom))
        .where(Site.milestone_id.in_(ids))
        .order_by(Site.created_at, Site.id)
    ):
        sites[milestone_id].append(json.loads(geojson))
    return ProjectDetail(
        **_summary(*row),
        milestones=[
            MilestoneOut(
                index=milestone.index,
                title=milestone.title,
                amount_qapik=milestone.amount_qapik,
                window_opens=milestone.window_opens,
                window_closes=milestone.window_closes,
                opens_at=milestone.opens_at,
                closes_at=milestone.closes_at,
                evidence_deadline=milestone.evidence_deadline,
                status=milestone.status,
                budget=lines[milestone.id],
                sites=sites[milestone.id],
            )
            for milestone in milestones
        ],
    )


@router.get("/{project_id}/passport")
def get_draft(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Draft:
    """The draft Passport and what still stops it from being published. Charity members only."""
    project = _member_project(db, user, project_id)
    draft = current_draft(db, project)
    if draft is None:
        raise NotFound("no_draft", "This project has no draft Passport. Save one to start it.")
    return _draft(db, project, draft)


@router.put("/{project_id}/passport")
def put_draft(
    project_id: uuid.UUID,
    body: Annotated[dict[str, Any], Body(description="The draft: any JSON object.")],
    user: CurrentUser,
    db: DbSession,
) -> Draft:
    """Save the draft as it is, complete or not, and list its problems."""
    project = _member_project(db, user, project_id)
    draft = save_draft(db, project, user, body)
    return _draft(db, project, draft)


@router.post("/{project_id}/passport/validate")
def validate_draft(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Validation:
    """Check the saved draft without publishing it."""
    project = _member_project(db, user, project_id)
    draft = current_draft(db, project)
    if draft is None:
        raise NotFound("no_draft", "This project has no draft Passport. Save one to start it.")
    passport, problems = draft_problems(db, project, draft)
    digest = None if passport is None or problems else to_hex(passport.digest())
    return Validation(
        version=draft.version,
        problems=[ProblemOut(**problem) for problem in problems],
        sha256=digest,
    )


class PublishIn(Input):
    charity_signature: str | None = Field(
        default=None,
        pattern=r"^0x([0-9a-fA-F]{2})+$",
        description="The charity key's signature over the launch message. Required once "
        "the API runs with a chain.",
    )


@router.get("/{project_id}/launch-message")
def get_launch_message(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    """The EIP-712 ProjectLaunch message for the charity's key to sign. Charity admins only."""
    project = _member_project(db, user, project_id, MemberRole.ADMIN)
    if chain is None:
        raise NotFound("no_chain", "This API runs without a chain, so nothing launches.")
    return launch_message(db, project, chain)


@router.post("/{project_id}/publish")
def publish(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
    body: Annotated[PublishIn | None, Body()] = None,
) -> PassportRef:
    """Publish the draft, and with a chain launch it. Its bytes and hash never change after
    this. Charity admins only."""
    project = _member_project(db, user, project_id, MemberRole.ADMIN)
    signature = body.charity_signature if body else None
    version = publish_passport(
        db,
        project,
        user,
        charity_signature=bytes.fromhex(signature[2:]) if signature else None,
        chain=chain,
    )
    return _passport_ref(version)


class AmendmentIn(Input):
    charity_signature: str = Field(pattern=r"^0x([0-9a-fA-F]{2})+$")


@router.get("/{project_id}/amendment-message")
def get_amendment_message(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    """The EIP-712 Amendment message for the charity's key to sign over the drafted next
    version. Charity admins only."""
    project = _member_project(db, user, project_id, MemberRole.ADMIN)
    if chain is None:
        raise NotFound("no_chain", "This API runs without a chain, so nothing is amended.")
    return amendment_message(db, project, chain)


@router.post("/{project_id}/amendment", status_code=202)
def post_amendment(
    project_id: uuid.UUID, body: AmendmentIn, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, str]:
    """Propose the drafted next version to the donors. It is published only if they vote for
    it. Charity admins only."""
    project = _member_project(db, user, project_id, MemberRole.ADMIN)
    if chain is None:
        raise NotFound("no_chain", "This API runs without a chain, so nothing is amended.")
    propose_amendment(db, chain, project, bytes.fromhex(body.charity_signature[2:]))
    return {"status": "queued"}


@router.get(
    "/{project_id}/passports/{version}",
    response_class=Response,
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "The published Passport, byte for byte as hashed.",
        }
    },
)
def published_passport(
    project_id: uuid.UUID, version: Annotated[int, Path(ge=1)], db: DbSession
) -> Response:
    """A published Passport version, exactly as hashed. Public, and never changes."""
    row = db.scalars(
        select(PassportVersion).where(
            PassportVersion.project_id == project_id,
            PassportVersion.version == version,
            PassportVersion.status != PassportStatus.DRAFT,
        )
    ).first()
    if row is None or row.canonical_bytes is None or row.sha256 is None or row.cid is None:
        raise NotFound("not_found", "This Passport version is not published.")
    return Response(
        content=row.canonical_bytes,
        media_type="application/json",
        headers={
            "X-Passport-SHA256": to_hex(row.sha256),
            "X-Passport-CID": row.cid,
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


def charity_projects(db: Session, charity_id: uuid.UUID) -> list[CharityProject]:
    projects = db.scalars(
        select(Project)
        .where(Project.charity_id == charity_id)
        .order_by(Project.created_at, Project.id)
    ).all()
    versions = db.scalars(
        select(PassportVersion).where(
            PassportVersion.project_id.in_([project.id for project in projects]),
            PassportVersion.status.in_([PassportStatus.DRAFT, PassportStatus.PUBLISHED]),
        )
    ).all()
    drafts = {v.project_id: v for v in versions if v.status == PassportStatus.DRAFT}
    published = {v.project_id: v for v in versions if v.status == PassportStatus.PUBLISHED}
    result = []
    for project in projects:
        draft = drafts.get(project.id)
        title = project.title
        if title is None and draft is not None and isinstance(draft.draft_json, dict):
            draft_title = draft.draft_json.get("title")
            title = draft_title if isinstance(draft_title, str) else None
        result.append(
            CharityProject(
                id=project.id,
                status=project.status,
                title=title,
                draft_version=None if draft is None else draft.version,
                published_version=None
                if project.id not in published
                else published[project.id].version,
                created_at=project.created_at,
            )
        )
    return result
