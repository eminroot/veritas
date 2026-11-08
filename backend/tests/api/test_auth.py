from sqlalchemy import func, select, text, update
from support import error, ok

from veritas.core.hashing import sha256
from veritas.db.models import AuthSession, LoginCode, User

PHONE = "+994501234567"


def ask_code(client, login_codes, phone=PHONE):
    ok(client.post("/v1/auth/otp", json={"phone": phone}), 202)
    return login_codes.latest(phone)


def test_first_login_creates_the_account(client, login_codes, db):
    response = client.post("/v1/auth/otp", json={"phone": "050 123 45 67"})
    assert ok(response, 202) == {"expires_in_seconds": 300}
    code = login_codes.latest(PHONE)
    assert len(code) == 6 and code.isdigit()

    body = ok(client.post("/v1/auth/token", json={"phone": "+994 50 123 45 67", "code": code}))
    assert body["token_type"] == "bearer"
    assert body["user"]["phone"] == PHONE
    assert body["user"]["is_admin"] is False
    me = ok(client.get("/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"}))
    assert me["user"]["id"] == body["user"]["id"]
    assert me == {**me, "is_admin": False, "memberships": [], "officer": None}

    # Logging in again finds the same account.
    code = ask_code(client, login_codes)
    again = ok(client.post("/v1/auth/token", json={"phone": PHONE, "code": code}))
    assert again["user"]["id"] == body["user"]["id"]
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_codes_and_tokens_are_stored_only_as_hashes(client, login_codes, db):
    code = ask_code(client, login_codes)
    token = ok(client.post("/v1/auth/token", json={"phone": PHONE, "code": code}))["access_token"]
    stored = db.scalars(select(LoginCode)).one()
    assert len(stored.code_hmac) == 32
    assert code.encode() not in stored.code_hmac
    assert stored.consumed_at is not None
    session = db.scalars(select(AuthSession)).one()
    assert session.token_hash == sha256(token.encode())


def test_wrong_code_counts_and_too_many_kill_the_code(client, login_codes, db):
    code = ask_code(client, login_codes)
    wrong = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1):
        body = error(
            client.post("/v1/auth/token", json={"phone": PHONE, "code": wrong}), 400, "code_wrong"
        )
        assert f"{left} more" in body["message"]
    error(client.post("/v1/auth/token", json={"phone": PHONE, "code": wrong}), 400, "code_locked")
    # Even the right code is refused now.
    error(client.post("/v1/auth/token", json={"phone": PHONE, "code": code}), 400, "code_locked")
    assert db.scalars(select(LoginCode.attempts)).one() == 5


def test_expired_code(client, login_codes, db):
    code = ask_code(client, login_codes)
    db.execute(update(LoginCode).values(expires_at=text("now() - interval '1 second'")))
    db.commit()
    response = client.post("/v1/auth/token", json={"phone": PHONE, "code": code})
    error(response, 400, "code_expired")


def test_a_code_works_once(client, login_codes):
    code = ask_code(client, login_codes)
    ok(client.post("/v1/auth/token", json={"phone": PHONE, "code": code}))
    response = client.post("/v1/auth/token", json={"phone": PHONE, "code": code})
    error(response, 400, "code_invalid")


def test_only_the_newest_code_counts(client, login_codes):
    first = ask_code(client, login_codes)
    second = ask_code(client, login_codes)
    if first != second:
        response = client.post("/v1/auth/token", json={"phone": PHONE, "code": first})
        error(response, 400, "code_wrong")
    ok(client.post("/v1/auth/token", json={"phone": PHONE, "code": second}))


def test_no_code_was_asked_for(client):
    response = client.post("/v1/auth/token", json={"phone": PHONE, "code": "123456"})
    error(response, 400, "code_invalid")


def test_code_must_be_six_digits(client):
    body = error(
        client.post("/v1/auth/token", json={"phone": PHONE, "code": "12ab"}), 422, "invalid_request"
    )
    assert body["details"] == [
        {"path": "body.code", "message": "must be the 6 digits from the message"}
    ]


def test_five_codes_per_phone_per_hour(client, login_codes):
    for _ in range(5):
        ask_code(client, login_codes)
    response = client.post("/v1/auth/otp", json={"phone": PHONE})
    error(response, 429, "too_many_codes")
    assert 0 < int(response.headers["Retry-After"]) <= 3600
    # Another phone is not affected.
    ask_code(client, login_codes, "+994551234567")


def test_logout_ends_the_session(client, login):
    person = login(PHONE)
    ok(client.get("/v1/me", headers=person.headers))
    response = client.post("/v1/auth/logout", headers=person.headers)
    assert response.status_code == 204
    error(client.get("/v1/me", headers=person.headers), 401, "not_authenticated")


def test_expired_session(client, login, db):
    person = login(PHONE)
    db.execute(update(AuthSession).values(expires_at=text("now() - interval '1 second'")))
    db.commit()
    error(client.get("/v1/me", headers=person.headers), 401, "not_authenticated")


def test_set_display_name(client, login):
    person = login(PHONE)
    body = ok(client.patch("/v1/me", json={"display_name": "Aysel"}, headers=person.headers))
    assert body["user"]["display_name"] == "Aysel"
