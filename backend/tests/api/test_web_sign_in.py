"""Signing in from the web app: a Firebase ID token traded for a Veritas session.

The tokens here are made the way Firebase makes them (RS256, Google's claims), signed with a
key made for the test; the app is given that key in place of Google's.
"""

import base64
import json
import time

import httpx
import pytest
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from support import CHARITY, error, ok

from veritas.api.app import create_app
from veritas.db.models import User
from veritas.services.errors import Unavailable
from veritas.services.firebase import GoogleKeys

PROJECT = "veritas-test"
KID = "key-1"
KEY = RSA.generate(1024)
OTHER_KEY = RSA.generate(1024)
UID = "kZ3wq9fMXbT2cR7vHn1sYdLp0aE4"
DROP = object()


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_token(key=KEY, header=None, **claims):
    now = int(time.time())
    payload = {
        "name": "Aysel Məmmədova",
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "auth_time": now - 30,
        "user_id": UID,
        "sub": UID,
        "iat": now - 5,
        "exp": now + 3600,
        "email": "aysel@example.com",
        "email_verified": True,
        "firebase": {"identities": {"google.com": ["1234"]}, "sign_in_provider": "google.com"},
    }
    payload.update(claims)
    payload = {name: value for name, value in payload.items() if value is not DROP}
    head = {"alg": "RS256", "kid": KID, "typ": "JWT", **(header or {})}
    signed = f"{b64(json.dumps(head).encode())}.{b64(json.dumps(payload).encode())}"
    signature = pkcs1_15.new(key).sign(SHA256.new(signed.encode()))
    return f"{signed}.{b64(signature)}"


class FakeKeys:
    """Stands in for Google's keys."""

    def __init__(self, keys):
        self.keys = keys

    def get(self, kid):
        return self.keys.get(kid)


@pytest.fixture
def web_app(app, settings):
    saved = app.state.settings, app.state.google_keys
    app.state.settings = settings.model_copy(update={"firebase_project_id": PROJECT})
    app.state.google_keys = FakeKeys({KID: KEY.public_key()})
    yield app
    app.state.settings, app.state.google_keys = saved


def sign_in(client, token):
    return client.post("/v1/auth/firebase", json={"id_token": token})


def bearer(body):
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_first_sign_in_creates_the_account(web_app, client, db):
    body = ok(sign_in(client, make_token()))
    assert body["token_type"] == "bearer"
    user = body["user"]
    assert user == {
        **user,
        "phone": None,
        "email": "aysel@example.com",
        "has_password": False,
        "has_google": True,
        "display_name": "Aysel Məmmədova",
        "is_admin": False,
    }
    me = ok(client.get("/v1/me", headers=bearer(body)))
    assert me == {**me, "user": user, "memberships": [], "officer": None}

    # The same Firebase account finds the same user. The email follows Firebase; the name,
    # once set, is the person's own.
    ok(client.patch("/v1/me", json={"display_name": "Aysel M."}, headers=bearer(body)))
    again = ok(sign_in(client, make_token(email="aysel@new.example.com", name="Someone Else")))
    assert again["user"]["id"] == user["id"]
    assert again["user"]["email"] == "aysel@new.example.com"
    assert again["user"]["display_name"] == "Aysel M."
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_a_name_that_would_be_refused_is_left_out(web_app, client):
    body = ok(sign_in(client, make_token(name="Bad\x00name")))
    assert body["user"]["display_name"] is None
    other = ok(sign_in(client, make_token(sub="another-uid", email="leyla@example.com", name=DROP)))
    assert other["user"]["display_name"] is None
    assert other["user"]["id"] != body["user"]["id"]


def test_sign_out_ends_the_session(web_app, client):
    body = ok(sign_in(client, make_token()))
    assert client.post("/v1/auth/logout", headers=bearer(body)).status_code == 204
    error(client.get("/v1/me", headers=bearer(body)), 401, "not_authenticated")


def tampered():
    good = make_token().split(".")
    other = make_token(sub="someone-else").split(".")
    return f"{good[0]}.{other[1]}.{good[2]}"


def unsigned():
    head = b64(json.dumps({"alg": "none", "kid": KID}).encode())
    return f"{head}.{make_token().split('.')[1]}."


BAD_TOKENS = {
    "expired": lambda: make_token(exp=int(time.time()) - 5),
    "for another project": lambda: make_token(aud="someone-elses-project"),
    "from another issuer": lambda: make_token(iss="https://accounts.example.com"),
    "issued in the future": lambda: make_token(iat=int(time.time()) + 600),
    "no auth time": lambda: make_token(auth_time=DROP),
    "no subject": lambda: make_token(sub=""),
    "subject not a string": lambda: make_token(sub=12345),
    "unknown key": lambda: make_token(header={"kid": "key-2"}),
    "signed with another key": lambda: make_token(key=OTHER_KEY),
    "another algorithm": lambda: make_token(header={"alg": "HS256"}),
    "unsigned": unsigned,
    "payload swapped": tampered,
    "expiry not a number": lambda: make_token(exp="tomorrow"),
    "not a token": lambda: "not-a-token",
    "not base64": lambda: "a$.b$.c$",
}


@pytest.mark.parametrize("make", BAD_TOKENS.values(), ids=BAD_TOKENS.keys())
def test_tokens_that_do_not_check_out_are_refused(web_app, client, db, make):
    body = error(sign_in(client, make()), 401, "token_invalid")
    assert body["message"].startswith("Sign in again")
    assert db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize(
    "claims",
    [{"email_verified": False}, {"email_verified": DROP}, {"email": DROP}],
    ids=["unverified", "verified unknown", "no email"],
)
def test_an_unverified_email_is_refused(web_app, client, db, claims):
    error(sign_in(client, make_token(**claims)), 403, "email_not_verified")
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_without_a_firebase_project_google_sign_in_is_refused(client):
    error(sign_in(client, make_token()), 503, "google_not_configured")


def test_google_takes_over_a_password_account_with_its_email(web_app, client, db):
    password = {"email": "Aysel@Example.com", "password": "correct horse 1"}
    made = ok(client.post("/v1/auth/signup", json=password), 201)
    google = ok(sign_in(client, make_token()))
    assert google["user"]["id"] == made["user"]["id"]
    assert google["user"]["has_google"] is True
    assert google["user"]["has_password"] is False
    # Nobody proved who chose the password: it stops working and its session ends.
    error(client.get("/v1/me", headers=bearer(made)), 401, "not_authenticated")
    error(client.post("/v1/auth/login", json=password), 401, "use_google")
    again = {"email": "aysel@example.com", "password": "another one 22"}
    error(client.post("/v1/auth/signup", json=again), 409, "use_google")
    ok(client.get("/v1/me", headers=bearer(google)))
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_a_new_google_email_never_takes_another_accounts(web_app, client):
    taken = {"email": "taken@example.com", "password": "correct horse 1"}
    ok(client.post("/v1/auth/signup", json=taken), 201)
    google = ok(sign_in(client, make_token()))
    again = ok(sign_in(client, make_token(email="Taken@example.com")))
    assert again["user"]["id"] == google["user"]["id"]
    assert again["user"]["email"] == "aysel@example.com"


def test_when_googles_keys_cannot_be_fetched_the_answer_says_try_later(web_app, client):
    failing = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    web_app.state.google_keys = GoogleKeys("https://keys.example/jwks", failing)
    response = sign_in(client, make_token())
    error(response, 503, "sign_in_unavailable")
    assert response.headers["retry-after"] == "60"


def test_a_web_account_can_register_a_charity(web_app, client):
    body = ok(sign_in(client, make_token()))
    charity = ok(client.post("/v1/charities", json=CHARITY, headers=bearer(body)), 201)
    members = ok(client.get(f"/v1/charities/{charity['id']}/members", headers=bearer(body)))
    assert [(m["phone"], m["email"], m["role"]) for m in members] == [
        (None, "aysel@example.com", "admin")
    ]
    me = ok(client.get("/v1/me", headers=bearer(body)))
    assert [m["charity_id"] for m in me["memberships"]] == [charity["id"]]


def test_an_account_needs_a_way_to_log_in(db):
    db.add(User(display_name="Nobody"))
    with pytest.raises(IntegrityError, match="ck_users_has_a_login"):
        db.flush()


def jwks(*pairs):
    def number(value):
        return b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))

    return {
        "keys": [
            {
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "kid": kid,
                "n": number(key.n),
                "e": number(key.e),
            }
            for kid, key in pairs
        ]
    }


def test_googles_keys_are_kept_as_long_as_google_says_and_fetched_again_for_a_new_key():
    calls = []

    def answer(request):
        calls.append(request.url)
        return httpx.Response(
            200, json=jwks((KID, KEY)), headers={"Cache-Control": "public, max-age=600"}
        )

    now = [1000.0]
    client = httpx.Client(transport=httpx.MockTransport(answer))
    keys = GoogleKeys("https://keys.example/jwks", client, clock=lambda: now[0])

    assert keys.get(KID).n == KEY.n and len(calls) == 1
    assert keys.get(KID) is not None and len(calls) == 1  # kept
    assert keys.get("rotated") is None and len(calls) == 1  # fetched less than a minute ago
    now[0] += 61
    assert keys.get("rotated") is None and len(calls) == 2  # a new key may be out: fetch
    now[0] += 600
    assert keys.get(KID) is not None and len(calls) == 3  # Google's max-age is over


def test_a_failed_fetch_keeps_the_keys_until_they_run_out():
    answers = [httpx.Response(200, json=jwks((KID, KEY)), headers={"Cache-Control": "max-age=600"})]

    def answer(request):
        return answers.pop(0) if answers else httpx.Response(503)

    now = [0.0]
    client = httpx.Client(transport=httpx.MockTransport(answer))
    keys = GoogleKeys("https://keys.example/jwks", client, clock=lambda: now[0])
    assert keys.get(KID) is not None
    now[0] += 120
    assert keys.get("rotated") is None  # the fetch failed, the keys we have still count
    assert keys.get(KID) is not None
    now[0] += 600
    with pytest.raises(Unavailable):
        keys.get(KID)


def test_cors_lets_only_the_configured_origins_call_from_a_browser(settings):
    app = create_app(settings.model_copy(update={"cors_origins": ["https://web.example.az"]}))
    client = TestClient(app)
    preflight = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }

    allowed = client.options(
        "/v1/auth/firebase", headers={"Origin": "https://web.example.az", **preflight}
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://web.example.az"
    assert "access-control-allow-credentials" not in allowed.headers

    other = client.options(
        "/v1/auth/firebase", headers={"Origin": "https://evil.example", **preflight}
    )
    assert "access-control-allow-origin" not in other.headers
