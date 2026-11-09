"""Logging in, every way there is, and the bearer sessions they all hand out.

In the app, with a code sent to a phone. A code is six random digits. Only an HMAC of it
(keyed with the server secret and bound to the phone number) is stored, it expires after a
few minutes, it works once, and too many wrong guesses kill it. Only the newest code for a
phone counts. Sending codes by SMS is not built yet. Until it is, `otp_echo` logs them so a
developer can log in, and production simply cannot send them.

In the web app, with an email and a password checked here (veritas.services.passwords).
Too many wrong passwords in a row stop password logins for a while. A forgotten password is
replaced through a one-time link sent by email, kept only as a hash, that expires and ends
every session of the account. Or with Google, through a Firebase ID token
(veritas.services.firebase).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from veritas.core.hashing import sha256
from veritas.db.models import AuthSession, LoginCode, PasswordReset, User
from veritas.db.session import db_now
from veritas.services import mail, passwords
from veritas.services.errors import BadRequest, Conflict, ServiceError, TooManyRequests
from veritas.services.firebase import Identity
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


class LoginFailed(ServiceError):
    status = 401


def sign_up(
    session: Session, settings: Settings, email: str, password: str, display_name: str | None
) -> tuple[User, str, AuthSession]:
    """Make an account with an email and a password, and start its first session."""
    _lock(session, f"email:{email}")
    existing = session.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        if existing.password_hash is None and existing.firebase_uid is not None:
            raise Conflict("use_google", "This email signs in with Google. Continue with Google.")
        raise Conflict(
            "email_taken",
            "There is already an account with this email. Sign in, or reset its password.",
        )
    user = User(
        email=email, password_hash=passwords.hash_password(password), display_name=display_name
    )
    session.add(user)
    session.flush()
    token, auth = start_session(session, settings, user, db_now(session))
    return user, token, auth


def log_in_with_password(
    session: Session, settings: Settings, email: str, password: str
) -> tuple[User, str, AuthSession]:
    """Check an email and a password and start a session.

    An unknown email and a wrong password get the same answer, after the same amount of work.
    """
    now = db_now(session)
    user = session.scalars(select(User).where(User.email == email).with_for_update()).first()
    if user is not None:
        _refuse_while_locked(user, now)
    if not passwords.verify_password(password, user.password_hash if user else None):
        if user is not None and user.password_hash is None and user.firebase_uid is not None:
            raise LoginFailed(
                "use_google", "This account signs in with Google. Continue with Google."
            )
        if user is not None and user.password_hash is not None:
            _count_failure(session, settings, user, now)
        raise LoginFailed("login_failed", "The email or the password is wrong.")
    _password_worked(user, password)
    token, auth = start_session(session, settings, user, now)
    return user, token, auth


def change_password(
    session: Session, settings: Settings, user: User, current: AuthSession, old: str, new: str
) -> None:
    """Replace the password, knowing the old one. Every other session of the account ends."""
    now = db_now(session)
    session.refresh(user, with_for_update=True)
    _refuse_while_locked(user, now)
    if user.password_hash is None:
        raise BadRequest(
            "no_password", "This account has no password yet. Ask for a link to set one by email."
        )
    if not passwords.verify_password(old, user.password_hash):
        _count_failure(session, settings, user, now)
        raise BadRequest("password_wrong", "The current password is wrong.")
    user.password_hash = passwords.hash_password(new)
    user.password_failures = 0
    user.password_locked_until = None
    _end_sessions(session, user, now, keep=current)


def request_password_reset(session: Session, settings: Settings, email: str) -> None:
    """Email a link to set a new password, when an account has this email.

    Says nothing either way, so nobody can use it to find out which emails have accounts. An
    account gets a few links an hour at most; past that, the request is quietly dropped.
    """
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is None:
        return
    _lock(session, f"reset:{user.id}")
    now = db_now(session)
    recent = session.scalar(
        select(func.count())
        .select_from(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.created_at > now - RATE_WINDOW)
    )
    if (recent or 0) >= settings.password_resets_per_hour:
        logger.warning("No more password links this hour for account %s", user.id)
        return
    token = secrets.token_urlsafe(32)
    session.add(
        PasswordReset(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    session.flush()
    # In the fragment, which browsers never send to a server or in a Referer header.
    link = f"{settings.web_app_url.rstrip('/')}/reset-password#token={token}"
    greeting = f"Hello {user.display_name}," if user.display_name else "Hello,"
    body = (
        f"{greeting}\n\n"
        f"Someone asked to set a new password for the Veritas account {email}. If it was you, "
        f"open this link within {settings.password_reset_ttl_minutes} minutes:\n\n{link}\n\n"
        "If it was not you, ignore this email: the password stays as it is.\n\nVeritas\n"
    )
    try:
        mail.send(settings, email, "Set a new password for Veritas", body)
    except mail.MailNotSent as error:
        logger.error("The password link for account %s was not sent: %s", user.id, error)


def reset_password(
    session: Session, settings: Settings, token: str, password: str
) -> tuple[User, str, AuthSession]:
    """Set a new password with an emailed link, and sign in.

    The link works once. Every other link of the account stops working, and every session ends:
    whoever knew the old password is out.
    """
    now = db_now(session)
    reset = session.scalars(
        select(PasswordReset).where(PasswordReset.token_hash == token_hash(token)).with_for_update()
    ).first()
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise BadRequest(
            "reset_link_invalid", "This link has expired or was used already. Ask for a new one."
        )
    user = session.get(User, reset.user_id, with_for_update=True)
    assert user is not None  # the foreign key cascades
    user.password_hash = passwords.hash_password(password)
    user.password_failures = 0
    user.password_locked_until = None
    session.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    _end_sessions(session, user, now)
    new_token, auth = start_session(session, settings, user, now)
    return user, new_token, auth


def user_for_firebase(session: Session, identity: Identity) -> User:
    """The user behind a checked Google sign-in, found, linked or created.

    A first Google sign-in with the email of an existing account links Google to that account
    instead of making a second one. Google has just proven who owns the email, while nobody
    has proven who chose that account's password: there is no email check at sign-up yet. So,
    the way Firebase does it, the password is dropped and the account's sessions end. Whoever
    owns the email can set a new password by email.

    The email follows the Google account's, unless another account has the new one. The
    display name is taken only while the account has none: after that it is the person's.
    """
    email = identity.email.strip().lower()
    # One sign-in per email and per Google account at a time, so two tabs cannot both make it.
    _lock(session, f"email:{email}")
    _lock(session, f"firebase:{identity.uid}")
    user = session.scalars(select(User).where(User.firebase_uid == identity.uid)).first()
    if user is None:
        user = session.scalars(select(User).where(User.email == email)).first()
        if user is None:
            user = User(firebase_uid=identity.uid, email=email, display_name=identity.name)
            session.add(user)
            session.flush()
            return user
        user.firebase_uid = identity.uid
        user.password_hash = None
        user.password_failures = 0
        user.password_locked_until = None
        _end_sessions(session, user, db_now(session))
    elif user.email != email:
        taken = session.scalars(select(User.id).where(User.email == email, User.id != user.id))
        if taken.first() is None:
            user.email = email
    if user.display_name is None:
        user.display_name = identity.name
    session.flush()
    return user


def _lock(session: Session, key: str) -> None:
    """Wait for any other request holding this key; held until the transaction ends."""
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


def _refuse_while_locked(user: User, now: datetime) -> None:
    if user.password_locked_until is not None and user.password_locked_until > now:
        wait = math.ceil((user.password_locked_until - now).total_seconds())
        raise TooManyRequests(
            "login_locked",
            "Too many wrong passwords. Try again in a few minutes, or set a new password by email.",
            headers={"Retry-After": str(max(wait, 1))},
        )


def _count_failure(session: Session, settings: Settings, user: User, now: datetime) -> None:
    user.password_failures += 1
    if user.password_failures >= settings.password_max_failures:
        user.password_failures = 0
        user.password_locked_until = now + timedelta(minutes=settings.password_lock_minutes)
    # The wrong password has to count even though this request fails and rolls back.
    session.commit()


def _password_worked(user: User, password: str) -> None:
    user.password_failures = 0
    user.password_locked_until = None
    if user.password_hash is not None and passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)


def _end_sessions(
    session: Session, user: User, now: datetime, keep: AuthSession | None = None
) -> None:
    query = update(AuthSession).where(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
    )
    if keep is not None:
        query = query.where(AuthSession.id != keep.id)
    session.execute(query.values(revoked_at=now))


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
