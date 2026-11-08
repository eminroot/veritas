"""Charity onboarding: details, KYB documents, review, members and the signing key."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.api.deps import (
    AdminUser,
    CurrentUser,
    DbSession,
    SettingsDep,
    StorageDep,
    charity_membership,
    require_charity_member,
)
from veritas.api.routes.documents import read_upload
from veritas.api.routes.projects import CharityProject, charity_projects
from veritas.api.schemas import (
    DocumentOut,
    Email,
    Input,
    Nonce,
    Output,
    Phone,
    Signature,
    Website,
    signature_bytes,
)
from veritas.db.models import (
    ChallengePurpose,
    Charity,
    CharityMember,
    CharityStatus,
    DocumentKind,
    MemberRole,
    OwnerType,
    User,
)
from veritas.passport.models import Address, Name, Prose, Voen
from veritas.services import charities
from veritas.services.documents import documents_of, store_document
from veritas.services.errors import Conflict, NotFound, Unprocessable
from veritas.services.keys import issue_challenge

router = APIRouter(prefix="/v1/charities", tags=["charities"])


class CharityIn(Input):
    legal_name: Name
    voen: Voen
    legal_form: Name
    legal_address: Name
    director_name: Name
    contact_email: Email
    contact_phone: Phone
    website: Website | None = None


class CharityPatch(Input):
    legal_name: Name | None = None
    voen: Voen | None = None
    legal_form: Name | None = None
    legal_address: Name | None = None
    director_name: Name | None = None
    contact_email: Email | None = None
    contact_phone: Phone | None = None
    website: Website | None = None


class CharityOut(Output):
    id: uuid.UUID
    legal_name: str
    voen: str
    legal_form: str
    legal_address: str
    director_name: str
    contact_email: str
    contact_phone: str
    website: str | None
    status: str
    signer_address: str | None
    submitted_at: datetime | None
    verified_at: datetime | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class CharityDetail(CharityOut):
    your_role: str | None
    documents: list[DocumentOut]


class Decision(Input):
    notes: Prose | None = None


class Rejection(Input):
    notes: Prose


class MemberIn(Input):
    phone: Phone
    role: MemberRole = MemberRole.FIELD_WORKER


class MemberOut(BaseModel):
    user_id: uuid.UUID
    phone: str
    display_name: str | None
    role: str
    added_at: datetime


class Challenge(BaseModel):
    nonce: str
    message: str
    expires_at: datetime


class SignerIn(Input):
    address: Address
    nonce: Nonce
    signature: Signature


def _detail(db: Session, charity: Charity, user: User) -> CharityDetail:
    member = charity_membership(db, user, charity.id)
    return CharityDetail.model_validate(
        {
            **CharityOut.model_validate(charity).model_dump(),
            "your_role": None if member is None else member.role,
            "documents": [
                DocumentOut.model_validate(document)
                for document in documents_of(db, OwnerType.CHARITY, charity.id)
            ],
        }
    )


def _charity_for_reader(db: Session, user: User, charity_id: uuid.UUID) -> Charity:
    """Members and Veritas admins can see everything about a charity."""
    if user.is_admin:
        charity = db.get(Charity, charity_id)
        if charity is None:
            raise NotFound("not_found", "There is no charity with this id.")
        return charity
    return require_charity_member(db, user, charity_id)


def _admin_charity(db: Session, charity_id: uuid.UUID) -> Charity:
    charity = db.get(Charity, charity_id, with_for_update=True)
    if charity is None:
        raise NotFound("not_found", "There is no charity with this id.")
    return charity


@router.post("", status_code=201)
def create_charity(body: CharityIn, user: CurrentUser, db: DbSession) -> CharityDetail:
    """Start a charity's registration. The caller becomes its first admin."""
    charity = charities.create_charity(db, user, body.model_dump())
    return _detail(db, charity, user)


@router.get("")
def list_charities(
    user: CurrentUser,
    db: DbSession,
    status: Annotated[CharityStatus | None, Query()] = None,
) -> list[CharityOut]:
    """Veritas admins see every charity (the review queue with status=submitted).
    Everyone else sees the charities they belong to."""
    query = select(Charity).order_by(Charity.created_at, Charity.id)
    if not user.is_admin:
        query = query.join(CharityMember, CharityMember.charity_id == Charity.id).where(
            CharityMember.user_id == user.id
        )
    if status is not None:
        query = query.where(Charity.status == status)
    return [CharityOut.model_validate(charity) for charity in db.scalars(query)]


@router.get("/{charity_id}")
def get_charity(charity_id: uuid.UUID, user: CurrentUser, db: DbSession) -> CharityDetail:
    return _detail(db, _charity_for_reader(db, user, charity_id), user)


@router.patch("/{charity_id}")
def update_charity(
    charity_id: uuid.UUID, body: CharityPatch, user: CurrentUser, db: DbSession
) -> CharityDetail:
    """Change details while the charity is a draft or was rejected. Charity admins only."""
    charity = require_charity_member(db, user, charity_id, MemberRole.ADMIN)
    changes = body.model_dump(exclude_unset=True)
    missing = [name for name, value in changes.items() if value is None and name != "website"]
    if missing:
        raise Unprocessable(
            "invalid_request",
            "Some fields are missing or not valid.",
            details=[{"path": f"body.{name}", "message": "cannot be empty"} for name in missing],
        )
    charities.update_charity(db, charity, changes)
    return _detail(db, charity, user)


@router.post("/{charity_id}/documents", status_code=201)
def upload_document(
    charity_id: uuid.UUID,
    kind: Annotated[DocumentKind, Form()],
    file: Annotated[UploadFile, File(description="PDF, JPEG or PNG, at most 20 MB.")],
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    storage: StorageDep,
) -> DocumentOut:
    """Add a KYB document: registration certificate, charter, director's ID and so on."""
    charity = require_charity_member(db, user, charity_id, MemberRole.ADMIN)
    if charity.status not in charities.EDITABLE:
        raise Conflict(
            "status_conflict", f"Documents cannot be added while the charity is {charity.status}."
        )
    document = store_document(
        db,
        storage,
        owner_type=OwnerType.CHARITY,
        owner_id=charity.id,
        kind=kind,
        filename=file.filename,
        content_type=file.content_type,
        data=read_upload(file, settings.max_upload_bytes),
        max_bytes=settings.max_upload_bytes,
        user=user,
    )
    return DocumentOut.model_validate(document)


@router.post("/{charity_id}/submit")
def submit_charity(charity_id: uuid.UUID, user: CurrentUser, db: DbSession) -> CharityDetail:
    """Send the charity to Veritas for review."""
    charity = require_charity_member(db, user, charity_id, MemberRole.ADMIN)
    charities.submit(db, charity)
    return _detail(db, charity, user)


@router.post("/{charity_id}/verify")
def verify_charity(
    charity_id: uuid.UUID, body: Decision, admin: AdminUser, db: DbSession
) -> CharityDetail:
    charity = charities.review(
        db, _admin_charity(db, charity_id), admin, CharityStatus.VERIFIED, body.notes
    )
    return _detail(db, charity, admin)


@router.post("/{charity_id}/reject")
def reject_charity(
    charity_id: uuid.UUID, body: Rejection, admin: AdminUser, db: DbSession
) -> CharityDetail:
    """Send the charity back with notes on what to fix. It can then edit and resubmit."""
    charity = charities.review(
        db, _admin_charity(db, charity_id), admin, CharityStatus.REJECTED, body.notes
    )
    return _detail(db, charity, admin)


@router.post("/{charity_id}/suspend")
def suspend_charity(
    charity_id: uuid.UUID, body: Rejection, admin: AdminUser, db: DbSession
) -> CharityDetail:
    """Stop a verified charity from publishing, with notes on why."""
    charity = charities.review(
        db, _admin_charity(db, charity_id), admin, CharityStatus.SUSPENDED, body.notes
    )
    return _detail(db, charity, admin)


@router.get("/{charity_id}/members")
def list_members(charity_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[MemberOut]:
    _charity_for_reader(db, user, charity_id)
    rows = db.execute(
        select(CharityMember, User)
        .join(User, User.id == CharityMember.user_id)
        .where(CharityMember.charity_id == charity_id)
        .order_by(CharityMember.created_at, CharityMember.id)
    ).all()
    return [_member(member, person) for member, person in rows]


@router.post("/{charity_id}/members", status_code=201)
def add_member(
    charity_id: uuid.UUID, body: MemberIn, user: CurrentUser, db: DbSession
) -> MemberOut:
    """Add a colleague by phone number. Charity admins only."""
    charity = require_charity_member(db, user, charity_id, MemberRole.ADMIN)
    member, person = charities.add_member(db, charity, body.phone, body.role, user)
    return _member(member, person)


def _member(member: CharityMember, person: User) -> MemberOut:
    return MemberOut(
        user_id=person.id,
        phone=person.phone,
        display_name=person.display_name,
        role=member.role,
        added_at=member.created_at,
    )


@router.post("/{charity_id}/signer/challenge", status_code=201)
def signer_challenge(
    charity_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: SettingsDep
) -> Challenge:
    """A one-time message to sign with the key that will sign for the charity."""
    charity = require_charity_member(db, user, charity_id, MemberRole.ADMIN)
    challenge = issue_challenge(db, settings, user, ChallengePurpose.CHARITY_SIGNER, charity.id)
    return Challenge(
        nonce=challenge.nonce, message=challenge.message, expires_at=challenge.expires_at
    )


@router.put("/{charity_id}/signer")
def set_signer(
    charity_id: uuid.UUID, body: SignerIn, user: CurrentUser, db: DbSession
) -> CharityDetail:
    """Set the charity's on-chain signing key. Verified charities only, charity admins only."""
    charity = require_charity_member(db, user, charity_id, MemberRole.ADMIN)
    charities.set_signer(
        db,
        charity,
        user,
        address=body.address,
        nonce=body.nonce,
        signature=signature_bytes(body.signature),
    )
    return _detail(db, charity, user)


@router.get("/{charity_id}/projects")
def list_charity_projects(
    charity_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[CharityProject]:
    """Every project of the charity, drafts included."""
    _charity_for_reader(db, user, charity_id)
    return charity_projects(db, charity_id)
