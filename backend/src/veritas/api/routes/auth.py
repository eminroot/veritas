"""Logging in (a code sent to a phone, an email and a password, or Google), passwords,
logging out, and the caller's own account."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from veritas.api.deps import CurrentCaller, CurrentUser, DbSession, SettingsDep
from veritas.api.schemas import AccountEmail, Input, OfficerOut, Phone, UserOut
from veritas.db.models import AuthSession, Charity, CharityMember, Officer, User
from veritas.db.session import db_now
from veritas.passport.models import Name
from veritas.services import auth, demo, firebase, passwords
from veritas.services.errors import NotFound

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


class FirebaseSignIn(Input):
    id_token: Annotated[str, Field(min_length=1, max_length=8192)]


class PasswordInput(BaseModel):
    """Like Input, but spaces are left alone: in a password they count."""

    model_config = ConfigDict(extra="forbid")


NewPassword = Annotated[str, AfterValidator(passwords.check_new)]
GivenPassword = Annotated[str, Field(min_length=1, max_length=4 * passwords.MAX_LENGTH)]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


class SignUp(PasswordInput):
    email: AccountEmail
    password: NewPassword
    display_name: Annotated[Name | None, BeforeValidator(_blank_to_none)] = None


class PasswordLogin(PasswordInput):
    email: AccountEmail
    password: GivenPassword


class ResetRequest(Input):
    email: AccountEmail


class ResetConfirm(PasswordInput):
    token: Annotated[str, Field(min_length=20, max_length=200)]
    password: NewPassword


class PasswordChange(PasswordInput):
    current_password: GivenPassword
    new_password: NewPassword


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
    return _token(user, token, session)


@router.post("/auth/signup", status_code=201)
def sign_up(body: SignUp, db: DbSession, settings: SettingsDep) -> Token:
    """Make an account in the web app with an email and a password, and sign in to it."""
    user, token, session = auth.sign_up(db, settings, body.email, body.password, body.display_name)
    return _token(user, token, session)


@router.post("/auth/login")
def password_login(body: PasswordLogin, db: DbSession, settings: SettingsDep) -> Token:
    """Sign in with an email and a password. Too many wrong passwords in a row stop password
    logins to the account for a while."""
    user, token, session = auth.log_in_with_password(db, settings, body.email, body.password)
    return _token(user, token, session)


@router.post("/auth/password-reset", status_code=202)
def request_password_reset(body: ResetRequest, db: DbSession, settings: SettingsDep) -> Response:
    """Email a link to set a new password, if an account has this email. The answer is the
    same either way."""
    auth.request_password_reset(db, settings, body.email)
    return Response(status_code=202)


@router.post("/auth/password-reset/confirm")
def reset_password(body: ResetConfirm, db: DbSession, settings: SettingsDep) -> Token:
    """Set a new password with the token from the emailed link, and sign in. Every other
    session of the account ends."""
    user, token, session = auth.reset_password(db, settings, body.token, body.password)
    return _token(user, token, session)


@router.post("/auth/firebase")
def firebase_sign_in(
    body: FirebaseSignIn, request: Request, db: DbSession, settings: SettingsDep
) -> Token:
    """Trade a Firebase ID token from the web app (email and password, or Google) for a
    bearer token. The email must be verified. The first sign-in creates the account."""
    identity = firebase.verify_id_token(body.id_token, settings, request.app.state.google_keys)
    user = auth.user_for_firebase(db, identity)
    token, session = auth.start_session(db, settings, user, db_now(db))
    return _token(user, token, session)


def _token(user: User, token: str, session: AuthSession) -> Token:
    return Token(
        access_token=token, expires_at=session.expires_at, user=UserOut.model_validate(user)
    )


class DemoLogin(Input):
    kind: demo.DemoKind = "donor"


@router.post("/auth/demo")
def demo_login(body: DemoLogin, db: DbSession, settings: SettingsDep) -> Token:
    """Sign in to a shared demo account, a donor or a verified organisation, with no
    password. Only where VERITAS_DEMO_LOGIN is on; the accounts are made on first use."""
    if not settings.demo_login:
        raise NotFound("demo_off", "The demo accounts are not open on this server.")
    user = demo.demo_user(db, body.kind)
    token, session = auth.start_session(db, settings, user, db_now(db))
    return _token(user, token, session)


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


@router.post("/me/password", status_code=204, tags=["account"])
def change_password(
    body: PasswordChange, caller: CurrentCaller, db: DbSession, settings: SettingsDep
) -> Response:
    """Change the password, knowing the current one. Every other session of the account ends."""
    auth.change_password(
        db, settings, caller.user, caller.session, body.current_password, body.new_password
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
