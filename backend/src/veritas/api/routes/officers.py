"""Verification Officers: registered by Veritas admins, named in Passports by address."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.api.deps import AdminUser, CurrentUser, DbSession
from veritas.api.schemas import Input, OfficerOut, Phone
from veritas.chain.registrations import officer_changed
from veritas.db.models import Officer, OfficerStatus
from veritas.passport.models import Address, Name
from veritas.services.auth import user_for_phone
from veritas.services.errors import NotFound
from veritas.services.officers import create_officer

router = APIRouter(prefix="/v1/officers", tags=["officers"])


class OfficerIn(Input):
    name: Name
    organisation: Name
    address: Address
    phone: Phone | None = None
    """The officer's own phone, if they will use the app to review."""


class OfficerListed(BaseModel):
    id: uuid.UUID
    name: str
    organisation: str
    address: str
    status: str


@router.post("", status_code=201)
def add_officer(body: OfficerIn, admin: AdminUser, db: DbSession) -> OfficerOut:
    user = None if body.phone is None else user_for_phone(db, body.phone)
    officer = create_officer(
        db,
        admin,
        name=body.name,
        organisation=body.organisation,
        address=body.address,
        user=user,
    )
    return OfficerOut.model_validate(officer)


@router.get("")
def list_officers(
    user: CurrentUser,
    db: DbSession,
    include_inactive: Annotated[bool, Query(description="Veritas admins only.")] = False,
) -> list[OfficerListed]:
    """The officers a Passport can name."""
    query = select(Officer).order_by(Officer.organisation, Officer.name, Officer.id)
    if not (include_inactive and user.is_admin):
        query = query.where(Officer.status == OfficerStatus.ACTIVE)
    return [
        OfficerListed(
            id=officer.id,
            name=officer.name,
            organisation=officer.organisation,
            address=officer.address,
            status=officer.status,
        )
        for officer in db.scalars(query)
    ]


@router.post("/{officer_id}/deactivate")
def deactivate_officer(officer_id: uuid.UUID, admin: AdminUser, db: DbSession) -> OfficerOut:
    """New Passports can no longer name this officer."""
    return _set_status(db, officer_id, OfficerStatus.INACTIVE)


@router.post("/{officer_id}/activate")
def activate_officer(officer_id: uuid.UUID, admin: AdminUser, db: DbSession) -> OfficerOut:
    return _set_status(db, officer_id, OfficerStatus.ACTIVE)


def _set_status(db: Session, officer_id: uuid.UUID, status: OfficerStatus) -> OfficerOut:
    officer = db.get(Officer, officer_id, with_for_update=True)
    if officer is None:
        raise NotFound("not_found", "There is no officer with this id.")
    if officer.status != status:
        officer.status = status
        officer_changed(db, officer)
    db.flush()
    return OfficerOut.model_validate(officer)
