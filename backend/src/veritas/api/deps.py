"""What every router depends on: a database session, settings, storage and the caller.

The session commits when the handler returns and before the response is sent
(scope="function"), so a client never sees success for a write that then fails
to commit. Any exception rolls it back.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain.runtime import Chain
from veritas.db.models import AuthSession, Charity, CharityMember, MemberRole, User
from veritas.db.session import session_scope
from veritas.services.auth import authenticate
from veritas.services.errors import Forbidden, NotAuthenticated, NotFound
from veritas.settings import Settings
from veritas.storage import PrivateStorage


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)


def app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> PrivateStorage:
    return request.app.state.storage


def get_chain(request: Request) -> Chain | None:
    return request.app.state.chain


DbSession = Annotated[Session, Depends(get_session, scope="function")]
ChainDep = Annotated[Chain | None, Depends(get_chain)]
SettingsDep = Annotated[Settings, Depends(app_settings)]
StorageDep = Annotated[PrivateStorage, Depends(get_storage)]

bearer = HTTPBearer(auto_error=False, description="The access_token from POST /v1/auth/token.")


@dataclass(frozen=True)
class Caller:
    user: User
    session: AuthSession


def current_caller(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Caller:
    if credentials is None:
        raise NotAuthenticated()
    found = authenticate(db, credentials.credentials)
    if found is None:
        raise NotAuthenticated("Your session has ended. Log in again.")
    auth, user = found
    return Caller(user=user, session=auth)


CurrentCaller = Annotated[Caller, Depends(current_caller)]


def current_user(caller: CurrentCaller) -> User:
    return caller.user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    """A Veritas admin: the staff who verify charities, contractors and officers."""
    if not user.is_admin:
        raise Forbidden("admin_only", "Only Veritas admins can do this.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]

_ROLE_NAMES = {MemberRole.ADMIN: "admins", MemberRole.FIELD_WORKER: "field workers"}


def require_charity_member(
    db: Session, user: User, charity_id: uuid.UUID, role: MemberRole | None = None
) -> Charity:
    """The charity, if `user` is a member of it (with `role`, when one is given)."""
    charity = db.get(Charity, charity_id)
    if charity is None:
        raise NotFound("not_found", "There is no charity with this id.")
    member = charity_membership(db, user, charity_id)
    if member is None:
        raise Forbidden("not_a_member", "You are not a member of this charity.")
    if role is not None and member.role != role:
        raise Forbidden("role_required", f"Only {_ROLE_NAMES[role]} of this charity can do this.")
    return charity


def charity_membership(db: Session, user: User, charity_id: uuid.UUID) -> CharityMember | None:
    return db.scalars(
        select(CharityMember).where(
            CharityMember.charity_id == charity_id, CharityMember.user_id == user.id
        )
    ).first()
