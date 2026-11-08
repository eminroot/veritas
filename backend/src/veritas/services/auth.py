"""Phone login with one-time codes, and the bearer sessions it hands out.

A code is six random digits. Only an HMAC of it (keyed with the server secret and
bound to the phone number) is stored, it expires after a few minutes, it works
once, and too many wrong guesses kill it. Only the newest code for a phone counts.

Sending codes by SMS is not built yet. Until it is, `otp_echo` logs them so a
developer can log in, and production simply cannot send them.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.core.hashing import sha256
from veritas.db.models import AuthSession, LoginCode, User
from veritas.db.session import db_now
from veritas.services.errors import BadRequest, TooManyRequests
from veritas.settings import Settings

logger = logging.getLogger("veritas.auth")

CODE_DIGITS = 6
RATE_WINDOW = timedelta(hours=1)


def code_hmac(settings: Settings, phone: str, code: str) -> bytes:
    return hmac.new(settings.hmac_key(), f"{phone}:{code}".encode(), hashlib.sha256).digest()


def token_hash(token: str) -> bytes:
    return sha256(token.encode("utf-8"))


def request_code(session: Session, settings: Settings, phone: str) -> None:
    """Make a new code for `phone`, refusing more than the hourly limit."""
    # One request per phone at a time, so two parallel requests cannot both pass the limit.
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(phone, 0))))
    now = db_now(session)
    recent = session.scalars(
        select(LoginCode.created_at)
        .where(LoginCode.phone == phone, LoginCode.created_at > now - RATE_WINDOW)
        .order_by(LoginCode.created_at)
    ).all()
    if len(recent) >= settings.otp_requests_per_hour:
        wait = math.ceil((recent[0] + RATE_WINDOW - now).total_seconds())
        raise TooManyRequests(
            "too_many_codes",
            "Too many codes were sent to this number. Try again later.",
            headers={"Retry-After": str(max(wait, 1))},
        )
    code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
    session.add(
        LoginCode(
            phone=phone,
            code_hmac=code_hmac(settings, phone, code),
            expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
        )
    )
    if settings.otp_echo:
        logger.info("Login code for %s is %s", phone, code)


def log_in(
    session: Session, settings: Settings, phone: str, code: str
) -> tuple[User, str, AuthSession]:
    """Check a code and start a session. Creates the user on their first login.

    Returns the user, the bearer token (shown once, never stored) and the session.
    """
    now = db_now(session)
    login = session.scalars(
        select(LoginCode)
        .where(LoginCode.phone == phone)
        .order_by(LoginCode.created_at.desc())
        .limit(1)
        .with_for_update()
    ).first()
    if login is None or login.consumed_at is not None:
        raise BadRequest("code_invalid", "There is no code to use for this number. Ask for one.")
    if login.attempts >= settings.otp_max_attempts:
        raise BadRequest("code_locked", "Too many wrong codes were tried. Ask for a new code.")
    if login.expires_at <= now:
        raise BadRequest("code_expired", "This code has expired. Ask for a new one.")
    if not hmac.compare_digest(login.code_hmac, code_hmac(settings, phone, code)):
        login.attempts += 1
        # The wrong guess has to count even though this request fails and rolls back.
        session.commit()
        left = settings.otp_max_attempts - login.attempts
        if left <= 0:
            raise BadRequest(
                "code_locked", "That code is wrong and was the last try. Ask for a new code."
            )
        tries = "try" if left == 1 else "tries"
        raise BadRequest("code_wrong", f"That code is wrong. You have {left} more {tries}.")

    login.consumed_at = now
    user = user_for_phone(session, phone)
    token, auth = start_session(session, settings, user, now)
    return user, token, auth


def user_for_phone(session: Session, phone: str) -> User:
    """The user with this phone, created if needed.

    A charity admin can add a colleague, or an admin an officer, before that
    person has ever logged in; the account is waiting for them when they do.
    """
    user = session.scalars(select(User).where(User.phone == phone)).first()
    if user is None:
        user = User(phone=phone)
        session.add(user)
        session.flush()
    return user


def start_session(
    session: Session, settings: Settings, user: User, now: datetime
) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(32)
    auth = AuthSession(
        user_id=user.id,
        token_hash=token_hash(token),
        expires_at=now + timedelta(days=settings.session_ttl_days),
    )
    session.add(auth)
    session.flush()
    return token, auth


def authenticate(session: Session, token: str) -> tuple[AuthSession, User] | None:
    """The live session and user behind a bearer token, or None."""
    row = session.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(
            AuthSession.token_hash == token_hash(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > func.now(),
        )
    ).first()
    return None if row is None else (row[0], row[1])


def log_out(session: Session, auth: AuthSession) -> None:
    auth.revoked_at = db_now(session)
