"""Verification Officers: the independent reviewers a Passport names by their address.

Admins register them. A Passport can only name an active officer, and an officer
linked to a user account can also record contractor registry checks.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain.registrations import officer_changed
from veritas.db.models import Officer, OfficerStatus, User
from veritas.services.errors import Conflict


def create_officer(
    session: Session,
    admin: User,
    *,
    name: str,
    organisation: str,
    address: str,
    user: User | None = None,
) -> Officer:
    if session.scalars(select(Officer.id).where(Officer.address == address)).first():
        raise Conflict("address_taken", "An officer with this address is already registered.")
    if (
        user is not None
        and session.scalars(select(Officer.id).where(Officer.user_id == user.id)).first()
    ):
        raise Conflict("already_officer", "This person is already registered as an officer.")
    officer = Officer(
        name=name,
        organisation=organisation,
        address=address,
        user_id=None if user is None else user.id,
        created_by=admin.id,
    )
    session.add(officer)
    session.flush()
    officer_changed(session, officer)
    return officer


def active_officer(session: Session, user: User) -> Officer | None:
    return session.scalars(
        select(Officer).where(Officer.user_id == user.id, Officer.status == OfficerStatus.ACTIVE)
    ).first()
