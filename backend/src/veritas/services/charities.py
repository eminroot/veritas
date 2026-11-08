"""Charity onboarding: a draft, KYB documents, review by a Veritas admin.

A charity is created as a draft by one of its staff, who becomes its first admin.
It can be edited while it is a draft or after a rejection, is submitted for
review with at least one document, and is verified or rejected with notes. Only
a verified charity can set its signing key and publish a Passport.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.chain.registrations import charity_key_changed
from veritas.db.models import (
    ChallengePurpose,
    Charity,
    CharityMember,
    CharityStatus,
    KybDocument,
    MemberRole,
    OwnerType,
    User,
)
from veritas.db.session import db_now
from veritas.services.auth import user_for_phone
from veritas.services.errors import Conflict
from veritas.services.keys import prove_key

EDITABLE = (CharityStatus.DRAFT, CharityStatus.REJECTED)


def _voen_free(session: Session, voen: str, charity_id: uuid.UUID | None = None) -> None:
    query = select(Charity.id).where(Charity.voen == voen)
    if charity_id is not None:
        query = query.where(Charity.id != charity_id)
    if session.scalars(query).first() is not None:
        raise Conflict("voen_taken", "A charity with this VÖEN is already registered.")


def create_charity(session: Session, user: User, fields: Mapping[str, Any]) -> Charity:
    _voen_free(session, fields["voen"])
    charity = Charity(**fields, created_by=user.id)
    session.add(charity)
    session.flush()
    session.add(CharityMember(charity_id=charity.id, user_id=user.id, role=MemberRole.ADMIN))
    session.flush()
    return charity


def update_charity(session: Session, charity: Charity, changes: Mapping[str, Any]) -> Charity:
    if charity.status not in EDITABLE:
        raise Conflict(
            "status_conflict",
            f"A {charity.status} charity cannot be edited, only a draft or a rejected one.",
        )
    if "voen" in changes:
        _voen_free(session, changes["voen"], charity.id)
    for name, value in changes.items():
        setattr(charity, name, value)
    session.flush()
    return charity


def submit(session: Session, charity: Charity) -> Charity:
    if charity.status not in EDITABLE:
        raise Conflict("status_conflict", f"A {charity.status} charity cannot be submitted again.")
    documents = session.scalar(
        select(func.count())
        .select_from(KybDocument)
        .where(KybDocument.owner_type == OwnerType.CHARITY, KybDocument.owner_id == charity.id)
    )
    if not documents:
        raise Conflict(
            "documents_missing", "Upload the charity's registration documents before submitting."
        )
    charity.status = CharityStatus.SUBMITTED
    charity.submitted_at = db_now(session)
    return charity


def review(
    session: Session, charity: Charity, admin: User, decision: CharityStatus, notes: str | None
) -> Charity:
    """Verify or reject a submitted charity, or suspend a verified one."""
    allowed_from = {
        CharityStatus.VERIFIED: CharityStatus.SUBMITTED,
        CharityStatus.REJECTED: CharityStatus.SUBMITTED,
        CharityStatus.SUSPENDED: CharityStatus.VERIFIED,
    }
    if charity.status != allowed_from[decision]:
        raise Conflict(
            "status_conflict",
            f"Only a {allowed_from[decision]} charity can be {decision}, "
            f"this one is {charity.status}.",
        )
    charity.status = decision
    charity.review_notes = notes
    if decision is CharityStatus.VERIFIED:
        charity.verified_at = db_now(session)
        charity.verified_by = admin.id
    charity_key_changed(session, charity, charity.signer_address)
    return charity


def add_member(
    session: Session, charity: Charity, phone: str, role: MemberRole, added_by: User
) -> tuple[CharityMember, User]:
    """Add a person by phone. They need no account yet: it is there when they first log in."""
    user = user_for_phone(session, phone)
    exists = session.scalars(
        select(CharityMember).where(
            CharityMember.charity_id == charity.id, CharityMember.user_id == user.id
        )
    ).first()
    if exists is not None:
        raise Conflict("already_member", "This person is already a member of the charity.")
    member = CharityMember(charity_id=charity.id, user_id=user.id, role=role, added_by=added_by.id)
    session.add(member)
    session.flush()
    return member, user


def set_signer(
    session: Session,
    charity: Charity,
    user: User,
    *,
    address: str,
    nonce: str,
    signature: bytes,
) -> Charity:
    """Set the charity's signing key after the user proves they hold it."""
    if charity.status != CharityStatus.VERIFIED:
        raise Conflict("charity_not_verified", "Only a verified charity can set its signing key.")
    prove_key(
        session,
        user,
        purpose=ChallengePurpose.CHARITY_SIGNER,
        nonce=nonce,
        address=address,
        signature=signature,
        charity_id=charity.id,
    )
    taken = session.scalars(
        select(Charity.id).where(Charity.signer_address == address, Charity.id != charity.id)
    ).first()
    if taken is not None:
        raise Conflict("address_taken", "Another charity already uses this key.")
    old_signer = charity.signer_address
    charity.signer_address = address
    charity_key_changed(session, charity, old_signer)
    return charity
