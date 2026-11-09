"""Accounts with an email and a password: signing up, logging in, the lock after wrong
passwords, links to set a new password, and changing it."""

import logging
import re
from dataclasses import dataclass

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from support import error, ok

from veritas.core.hashing import sha256
from veritas.db.models import PasswordReset, User
from veritas.settings import Settings

PASSWORD = "correct horse 1"
EMAIL = "aysel@example.com"


def sign_up(client, email=EMAIL, password=PASSWORD, **extra):
    return client.post("/v1/auth/signup", json={"email": email, "password": password, **extra})


def log_in(client, email=EMAIL, password=PASSWORD):
    return client.post("/v1/auth/login", json={"email": email, "password": password})


def bearer(body):
    return {"Authorization": f"Bearer {body['access_token']}"}


def ask_for_link(client, email=EMAIL):
    response = client.post("/v1/auth/password-reset", json={"email": email})
    assert response.status_code == 202, response.text


def an_hour_ago():
    return func.now() - text("interval '1 hour'")


@dataclass
class Mail:
    to: str
    subject: str
    body: str


class Mails(logging.Handler):
    """Reads emails from the log, the way a developer does with mail_echo on."""

    PATTERN = re.compile(r"Mail to (\S+): (.*?)\n(.*)", re.S)

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.sent: list[Mail] = []

    def emit(self, record: logging.LogRecord) -> None:
        match = self.PATTERN.match(record.getMessage())
        if match:
            self.sent.append(Mail(*match.groups()))

    def token(self) -> str:
        return re.search(r"#token=([A-Za-z0-9_-]+)", self.sent[-1].body).group(1)


@pytest.fixture
def mails(app, settings):
    """The app writes its emails to the log, and the test reads them there."""
    saved = app.state.settings
    app.state.settings = settings.model_copy(
        update={"mail_echo": True, "web_app_url": "https://veritas.example.az/"}
    )
    handler = Mails()
    logger = logging.getLogger("veritas.mail")
    level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(level)
    app.state.settings = saved


@pytest.fixture
def three_tries(app, settings):
    saved = app.state.settings
    app.state.settings = settings.model_copy(update={"password_max_failures": 3})
    yield 3
    app.state.settings = saved


def test_sign_up_then_log_in(client, db):
    made = ok(sign_up(client, email="  Aysel@Example.COM ", display_name=" Aysel Məmmədova "), 201)
    user = made["user"]
    assert user == {
        **user,
        "email": EMAIL,
        "phone": None,
        "has_password": True,
        "has_google": False,
        "display_name": "Aysel Məmmədova",
        "is_admin": False,
    }
    me = ok(client.get("/v1/me", headers=bearer(made)))
    assert me == {**me, "user": user, "memberships": [], "officer": None}

    again = ok(log_in(client, email="AYSEL@example.com"))
    assert again["user"]["id"] == user["id"]
    assert again["access_token"] != made["access_token"]
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_passwords_are_kept_only_as_salted_scrypt(client, db):
    ok(sign_up(client), 201)
    ok(sign_up(client, email="leyla@example.com"), 201)
    hashes = db.scalars(select(User.password_hash)).all()
    assert all(h.startswith("scrypt$32768$8$3$") for h in hashes)
    assert hashes[0] != hashes[1]
    assert not any(PASSWORD in h for h in hashes)


def test_spaces_in_a_password_count(client):
    ok(sign_up(client, password="  spaced out  "), 201)
    error(log_in(client, password="spaced out"), 401, "login_failed")
    ok(log_in(client, password="  spaced out  "))


@pytest.mark.parametrize(
    "password", ["short 1", " " * 12, "x" * 129], ids=["short", "only spaces", "too long"]
)
def test_a_password_that_breaks_the_rules_is_refused(client, password):
    error(sign_up(client, password=password), 422, "invalid_request")


def test_one_email_is_one_account(client):
    ok(sign_up(client), 201)
    error(
        sign_up(client, email="AYSEL@EXAMPLE.COM", password="something else 2"), 409, "email_taken"
    )


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(client):
    ok(sign_up(client), 201)
    wrong = error(log_in(client, password="not it at all"), 401, "login_failed")
    unknown = error(log_in(client, email="nobody@example.com"), 401, "login_failed")
    assert wrong == unknown


def test_wrong_passwords_in_a_row_lock_password_logins(client, db, three_tries):
    ok(sign_up(client), 201)
    for _ in range(three_tries - 1):
        error(log_in(client, password="not it at all"), 401, "login_failed")
    ok(log_in(client))  # a right one starts the count again
    for _ in range(three_tries):
        error(log_in(client, password="not it at all"), 401, "login_failed")
    locked = error(log_in(client), 429, "login_locked")
    assert "set a new password" in locked["message"]

    # Once the lock has passed, the right password works again.
    db.execute(update(User).values(password_locked_until=an_hour_ago()))
    db.commit()
    ok(log_in(client))


def test_a_link_sets_a_new_password_and_ends_every_session(client, mails, db):
    made = ok(sign_up(client), 201)
    other = ok(log_in(client))
    ask_for_link(client, "Aysel@Example.com")
    mail = mails.sent[-1]
    assert mail.to == EMAIL
    assert "https://veritas.example.az/reset-password#token=" in mail.body
    token = mails.token()

    reset = ok(
        client.post(
            "/v1/auth/password-reset/confirm", json={"token": token, "password": "new one 345"}
        )
    )
    assert reset["user"]["id"] == made["user"]["id"]
    for old in (made, other):
        error(client.get("/v1/me", headers=bearer(old)), 401, "not_authenticated")
    ok(client.get("/v1/me", headers=bearer(reset)))
    error(log_in(client), 401, "login_failed")
    ok(log_in(client, password="new one 345"))

    # A link works once, and only its hash was ever stored.
    again = {"token": token, "password": "yet another 678"}
    error(client.post("/v1/auth/password-reset/confirm", json=again), 400, "reset_link_invalid")
    stored = db.scalars(select(PasswordReset)).one()
    assert stored.token_hash == sha256(token.encode())
    assert stored.used_at is not None


def test_a_link_for_an_unknown_email_sends_nothing(client, mails):
    ask_for_link(client, "nobody@example.com")
    assert mails.sent == []


def test_links_are_limited_per_hour(client, mails, settings, db):
    ok(sign_up(client), 201)
    for _ in range(settings.password_resets_per_hour + 2):
        ask_for_link(client)
    assert len(mails.sent) == settings.password_resets_per_hour
    # An hour later, there can be another.
    db.execute(update(PasswordReset).values(created_at=an_hour_ago()))
    db.commit()
    ask_for_link(client)
    assert len(mails.sent) == settings.password_resets_per_hour + 1


def test_an_expired_link_does_not_work(client, mails, db):
    ok(sign_up(client), 201)
    ask_for_link(client)
    db.execute(update(PasswordReset).values(expires_at=an_hour_ago()))
    db.commit()
    expired = {"token": mails.token(), "password": "new one 345"}
    error(client.post("/v1/auth/password-reset/confirm", json=expired), 400, "reset_link_invalid")
    ok(log_in(client))


def test_without_a_way_to_send_mail_the_answer_is_the_same(client, caplog):
    ok(sign_up(client), 201)
    with caplog.at_level(logging.ERROR, logger="veritas.auth"):
        ask_for_link(client)
    assert "was not sent" in caplog.text


def test_changing_the_password_needs_the_current_one_and_ends_other_sessions(client):
    first = ok(sign_up(client), 201)
    second = ok(log_in(client))

    def change(current, new):
        body = {"current_password": current, "new_password": new}
        return client.post("/v1/me/password", json=body, headers=bearer(first))

    error(change("not it at all", "new one 345"), 400, "password_wrong")
    error(change(PASSWORD, "short"), 422, "invalid_request")
    assert change(PASSWORD, "new one 345").status_code == 204
    ok(client.get("/v1/me", headers=bearer(first)))
    error(client.get("/v1/me", headers=bearer(second)), 401, "not_authenticated")
    error(log_in(client), 401, "login_failed")
    ok(log_in(client, password="new one 345"))


def test_a_phone_account_has_no_password_to_change(client, login):
    person = login("+994 50 222 22 22")
    body = {"current_password": "anything 1", "new_password": "new one 345"}
    error(client.post("/v1/me/password", json=body, headers=person.headers), 400, "no_password")


def test_the_database_keeps_the_account_rules(db):
    db.add(User(password_hash="scrypt$x"))
    with pytest.raises(IntegrityError, match="ck_users_password_needs_email"):
        db.flush()
    db.rollback()
    db.add(User(email="Aysel@example.com", password_hash="scrypt$x"))
    with pytest.raises(IntegrityError, match="ck_users_email_lower_case"):
        db.flush()


def test_production_refuses_to_write_emails_to_the_log():
    with pytest.raises(ValidationError, match="VERITAS_MAIL_ECHO"):
        Settings(_env_file=None, env="prod", mail_echo=True)
