"""Contractor onboarding: registered by a charity, verified by Veritas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
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
from veritas.api.schemas import DocumentOut, Iban, Input, Output
from veritas.db.models import (
    CharityMember,
    Contractor,
    ContractorStatus,
    DocumentKind,
    OwnerType,
    RegistryStatus,
    User,
)
from veritas.passport.models import Name, Prose, Voen
from veritas.services import contractors
from veritas.services.documents import documents_of, store_document
from veritas.services.errors import Forbidden, NotFound, Unprocessable
from veritas.services.officers import active_officer

router = APIRouter(prefix="/v1/contractors", tags=["contractors"])


class ContractorIn(Input):
    charity_id: uuid.UUID
    """The charity registering the contractor. The caller must be one of its members."""
    legal_name: Name
    voen: Voen
    iban: Iban
    legal_address: Name
    director_name: Name


class ContractorPatch(Input):
    legal_name: Name | None = None
    voen: Voen | None = None
    iban: Iban | None = None
    legal_address: Name | None = None
    director_name: Name | None = None


class ContractorOut(Output):
    id: uuid.UUID
    charity_id: uuid.UUID
    legal_name: str
    voen: str
    iban: str
    legal_address: str
    director_name: str
    status: str
    registry_status: str
    registry_checked_at: datetime | None
    registry_note: str | None
    review_notes: str | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ContractorDetail(ContractorOut):
    documents: list[DocumentOut]


class Decision(Input):
    notes: Prose | None = None


class Rejection(Input):
    notes: Prose


class RegistryCheck(Input):
    status: Literal["manual_ok", "inactive", "not_found"]
    note: Prose | None = None


def _is_reviewer(db: Session, user: User) -> bool:
    return user.is_admin or active_officer(db, user) is not None


def _readable(db: Session, user: User, contractor_id: uuid.UUID) -> Contractor:
    """Admins and officers see every contractor, members of the registering charity theirs."""
    contractor = db.get(Contractor, contractor_id)
    if contractor is None:
        raise NotFound("not_found", "There is no contractor with this id.")
    if not _is_reviewer(db, user) and charity_membership(db, user, contractor.charity_id) is None:
        raise Forbidden("forbidden", "Only the charity that registered this contractor can see it.")
    return contractor


def _editable(db: Session, user: User, contractor_id: uuid.UUID) -> Contractor:
    contractor = db.get(Contractor, contractor_id, with_for_update=True)
    if contractor is None:
        raise NotFound("not_found", "There is no contractor with this id.")
    require_charity_member(db, user, contractor.charity_id)
    return contractor


def _detail(db: Session, contractor: Contractor) -> ContractorDetail:
    return ContractorDetail(
        **ContractorOut.model_validate(contractor).model_dump(),
        documents=[
            DocumentOut.model_validate(document)
            for document in documents_of(db, OwnerType.CONTRACTOR, contractor.id)
        ],
    )


@router.post("", status_code=201)
def register_contractor(body: ContractorIn, user: CurrentUser, db: DbSession) -> ContractorDetail:
    """Register the company a charity will pay. It waits for a Veritas admin to verify it."""
    require_charity_member(db, user, body.charity_id)
    contractor = contractors.register(
        db, body.charity_id, user, body.model_dump(exclude={"charity_id"})
    )
    return _detail(db, contractor)


@router.get("")
def list_contractors(
    user: CurrentUser,
    db: DbSession,
    status: Annotated[ContractorStatus | None, Query()] = None,
    voen: Annotated[str | None, Query(pattern=r"^[0-9]{10}$")] = None,
) -> list[ContractorOut]:
    query = select(Contractor).order_by(Contractor.created_at, Contractor.id)
    if not _is_reviewer(db, user):
        mine = select(CharityMember.charity_id).where(CharityMember.user_id == user.id)
        query = query.where(Contractor.charity_id.in_(mine))
    if status is not None:
        query = query.where(Contractor.status == status)
    if voen is not None:
        query = query.where(Contractor.voen == voen)
    return [ContractorOut.model_validate(contractor) for contractor in db.scalars(query)]


@router.get("/{contractor_id}")
def get_contractor(contractor_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ContractorDetail:
    return _detail(db, _readable(db, user, contractor_id))


@router.patch("/{contractor_id}")
def update_contractor(
    contractor_id: uuid.UUID, body: ContractorPatch, user: CurrentUser, db: DbSession
) -> ContractorDetail:
    """Correct the details before verification. A rejected contractor is reviewed again."""
    contractor = _editable(db, user, contractor_id)
    changes = body.model_dump(exclude_unset=True)
    missing = [name for name, value in changes.items() if value is None]
    if missing:
        raise Unprocessable(
            "invalid_request",
            "Some fields are missing or not valid.",
            details=[{"path": f"body.{name}", "message": "cannot be empty"} for name in missing],
        )
    contractors.update(db, contractor, changes)
    return _detail(db, contractor)


@router.post("/{contractor_id}/documents", status_code=201)
def upload_document(
    contractor_id: uuid.UUID,
    kind: Annotated[DocumentKind, Form()],
    file: Annotated[UploadFile, File(description="PDF, JPEG or PNG, at most 20 MB.")],
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    storage: StorageDep,
) -> DocumentOut:
    contractor = _editable(db, user, contractor_id)
    document = store_document(
        db,
        storage,
        owner_type=OwnerType.CONTRACTOR,
        owner_id=contractor.id,
        kind=kind,
        filename=file.filename,
        content_type=file.content_type,
        data=read_upload(file, settings.max_upload_bytes),
        max_bytes=settings.max_upload_bytes,
        user=user,
    )
    return DocumentOut.model_validate(document)


@router.post("/{contractor_id}/verify")
def verify_contractor(
    contractor_id: uuid.UUID, body: Decision, admin: AdminUser, db: DbSession
) -> ContractorDetail:
    contractor = _locked(db, contractor_id)
    contractors.review(db, contractor, admin, ContractorStatus.VERIFIED, body.notes)
    return _detail(db, contractor)


@router.post("/{contractor_id}/reject")
def reject_contractor(
    contractor_id: uuid.UUID, body: Rejection, admin: AdminUser, db: DbSession
) -> ContractorDetail:
    contractor = _locked(db, contractor_id)
    contractors.review(db, contractor, admin, ContractorStatus.REJECTED, body.notes)
    return _detail(db, contractor)


@router.put("/{contractor_id}/registry")
def record_registry_check(
    contractor_id: uuid.UUID, body: RegistryCheck, user: CurrentUser, db: DbSession
) -> ContractorDetail:
    """Record what the tax registry said when someone looked the VÖEN up by hand.
    Veritas admins and active officers only."""
    if not _is_reviewer(db, user):
        raise Forbidden(
            "reviewer_only", "Only Veritas admins and officers can record registry checks."
        )
    contractor = _locked(db, contractor_id)
    contractors.record_registry_check(db, contractor, user, RegistryStatus(body.status), body.note)
    return _detail(db, contractor)


def _locked(db: Session, contractor_id: uuid.UUID) -> Contractor:
    contractor = db.get(Contractor, contractor_id, with_for_update=True)
    if contractor is None:
        raise NotFound("not_found", "There is no contractor with this id.")
    return contractor
