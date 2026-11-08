"""Login with a code sent to a phone, logout, and the caller's own account."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Response
from pydantic import AfterValidator, BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from veritas.api.deps import CurrentCaller, CurrentUser, DbSession, SettingsDep
from veritas.api.schemas import Input, OfficerOut, Phone, UserOut
from veritas.db.models import AuthSession, Charity, CharityMember, Officer, User
from veritas.db.session import db_now
from veritas.passport.models import Name
from veritas.services import auth

router = APIRouter(prefix="/v1", tags=["auth"])


def _six_digits(value: str) -> str:
    code = re.sub(r"\s+", "", value)
    if not re.fullmatch(r"[0-9]{6}", code):
        raise ValueError("must be the 6 digits from the message")
    return code


class CodeRequest(Input):
    phone: Phone


class CodeSent(BaseModel):
    expires_in_seconds: int


class TokenRequest(Input):
    phone: Phone
    code: Annotated[str, AfterValidator(_six_digits)]


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserOut


class Membership(BaseModel):
    charity_id: uuid.UUID
    charity_name: str
    charity_status: str
    role: str


class Me(BaseModel):
    user: UserOut
    is_admin: bool
    memberships: list[Membership]
    officer: OfficerOut | None


class MeUpdate(Input):
    display_name: Name | None = None


@router.post("/auth/otp", status_code=202)
def request_code(body: CodeRequest, db: DbSession, settings: SettingsDep) -> CodeSent:
    """Send a one-time login code to the phone. At most a few per hour per phone."""
    auth.request_code(db, settings, body.phone)
    return CodeSent(expires_in_seconds=settings.otp_ttl_seconds)


@router.post("/auth/token")
def get_token(body: TokenRequest, db: DbSession, settings: SettingsDep) -> Token:
    """Trade the code for a bearer token. The first login creates the account."""
    user, token, session = auth.log_in(db, settings, body.phone, body.code)
    return Token(
        access_token=token, expires_at=session.expires_at, user=UserOut.model_validate(user)
    )


@router.post("/auth/logout", status_code=204)
def log_out(caller: CurrentCaller, db: DbSession) -> Response:
    """End this session. The token stops working at once."""
    auth.log_out(db, caller.session)
    return Response(status_code=204)


@router.post("/auth/logout-everywhere", status_code=204)
def log_out_everywhere(caller: CurrentCaller, db: DbSession) -> Response:
    """End every other session of this account, for example after losing a phone. This
    session stays."""
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == caller.user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.id != caller.session.id,
        )
        .values(revoked_at=db_now(db))
    )
    return Response(status_code=204)


@router.get("/me", tags=["account"])
def me(user: CurrentUser, db: DbSession) -> Me:
    """The caller: their account, charity memberships and officer record."""
    return _me(db, user)


@router.patch("/me", tags=["account"])
def update_me(body: MeUpdate, user: CurrentUser, db: DbSession) -> Me:
    if "display_name" in body.model_fields_set:
        user.display_name = body.display_name
        db.flush()
    return _me(db, user)


def _me(db: Session, user: User) -> Me:
    rows = db.execute(
        select(CharityMember, Charity)
        .join(Charity, Charity.id == CharityMember.charity_id)
        .where(CharityMember.user_id == user.id)
        .order_by(Charity.legal_name)
    ).all()
    officer = db.scalars(select(Officer).where(Officer.user_id == user.id)).first()
    return Me(
        user=UserOut.model_validate(user),
        is_admin=user.is_admin,
        memberships=[
            Membership(
                charity_id=charity.id,
                charity_name=charity.legal_name,
                charity_status=charity.status,
                role=member.role,
            )
            for member, charity in rows
        ],
        officer=None if officer is None else OfficerOut.model_validate(officer),
    )
