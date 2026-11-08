"""Who may see a project's private evidence: the charity's members and the project's officer.

The project's officer is the Verification Officer the published Passport names, by address,
and only while their officer record is active and linked to the caller's account. Everyone
else sees the public copy only.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.db.models import CharityMember, Officer, OfficerStatus, Project, User
from veritas.evidence.capture import published_passport
from veritas.services.errors import Forbidden


def is_member(session: Session, user: User, project: Project) -> bool:
    return (
        session.scalars(
            select(CharityMember.id).where(
                CharityMember.charity_id == project.charity_id, CharityMember.user_id == user.id
            )
        ).first()
        is not None
    )


def project_officer(session: Session, project: Project, user: User) -> Officer | None:
    _, passport = published_passport(session, project)
    return session.scalars(
        select(Officer).where(
            Officer.address == passport.officer.address,
            Officer.user_id == user.id,
            Officer.status == OfficerStatus.ACTIVE,
        )
    ).first()


def can_review(session: Session, user: User, project: Project) -> bool:
    return is_member(session, user, project) or project_officer(session, project, user) is not None


def require_reviewer(session: Session, user: User, project: Project) -> None:
    if not can_review(session, user, project):
        raise Forbidden(
            "not_a_reviewer",
            "Only the charity's members and the project's Verification Officer can see its "
            "evidence.",
        )
