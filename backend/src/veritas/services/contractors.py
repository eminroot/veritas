"""Contractor onboarding: a charity registers the company it will pay, an admin verifies it.

A Passport names its contractor by VÖEN, and publishing checks that the VÖEN
belongs to a verified contractor whose tax registry entry is not known to be
inactive. Automatic registry lookups come in Phase 7; until then an admin or an
officer records what they found by hand.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.db.models import Contractor, ContractorStatus, RegistryStatus, User
from veritas.db.session import db_now
from veritas.services.errors import Conflict

BAD_REGISTRY = (RegistryStatus.INACTIVE, RegistryStatus.NOT_FOUND)
MANUAL_RESULTS = (RegistryStatus.MANUAL_OK, RegistryStatus.INACTIVE, RegistryStatus.NOT_FOUND)


def _voen_free(session: Session, voen: str, contractor_id: uuid.UUID | None = None) -> None:
    query = select(Contractor.id).where(Contractor.voen == voen)
    if contractor_id is not None:
        query = query.where(Contractor.id != contractor_id)
    if session.scalars(query).first() is not None:
        raise Conflict("voen_taken", "A contractor with this VÖEN is already registered.")


def register(
    session: Session, charity_id: uuid.UUID, user: User, fields: Mapping[str, Any]
) -> Contractor:
    _voen_free(session, fields["voen"])
    contractor = Contractor(**fields, charity_id=charity_id, created_by=user.id)
    session.add(contractor)
    session.flush()
    return contractor


def update(session: Session, contractor: Contractor, changes: Mapping[str, Any]) -> Contractor:
    """Edit before verification. A rejected contractor goes back to the review queue."""
    if contractor.status == ContractorStatus.VERIFIED:
        raise Conflict("status_conflict", "A verified contractor cannot be edited.")
    if "voen" in changes:
        _voen_free(session, changes["voen"], contractor.id)
    for name, value in changes.items():
        setattr(contractor, name, value)
    contractor.status = ContractorStatus.SUBMITTED
    session.flush()
    return contractor


def review(
    session: Session,
    contractor: Contractor,
    admin: User,
    decision: ContractorStatus,
    notes: str | None,
) -> Contractor:
    if contractor.status != ContractorStatus.SUBMITTED:
        raise Conflict(
            "status_conflict",
            f"Only a submitted contractor can be reviewed, this one is {contractor.status}.",
        )
    if decision is ContractorStatus.VERIFIED and contractor.registry_status in BAD_REGISTRY:
        raise Conflict(
            "registry_inactive",
            "The tax registry lists this VÖEN as inactive or unknown, so it cannot be verified.",
        )
    contractor.status = decision
    contractor.review_notes = notes
    if decision is ContractorStatus.VERIFIED:
        contractor.verified_at = db_now(session)
        contractor.verified_by = admin.id
    return contractor


def record_registry_check(
    session: Session, contractor: Contractor, user: User, result: RegistryStatus, note: str | None
) -> Contractor:
    """What a person found when they looked the VÖEN up by hand."""
    contractor.registry_status = result
    contractor.registry_note = note
    contractor.registry_checked_at = db_now(session)
    contractor.registry_checked_by = user.id
    return contractor
