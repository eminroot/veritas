import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select, text, update
from support import error, ok

from veritas.db.models import AuthSession, DeviceChallenge


def sign(account, message):
    return account.sign_message(encode_defunct(text=message)).signature.to_0x_hex()


@pytest.fixture
def person(login):
    return login("+994 50 222 22 22")


def challenge(client, person):
    return ok(client.post("/v1/devices/challenge", headers=person.headers), 201)


def register(client, person, account, nonce, signature, **extra):
    body = {
        "address": account.address,
        "platform": "android",
        "label": "Pixel",
        "nonce": nonce,
        "signature": signature,
        **extra,
    }
    return client.post("/v1/devices", json=body, headers=person.headers)


def test_register_a_device_key(client, person, db):
    account = Account.create()
    issued = challenge(client, person)
    assert issued["nonce"] in issued["message"]
    assert "register a device key" in issued["message"]

    signature = sign(account, issued["message"])
    response = register(client, person, account, issued["nonce"], signature, attestation="mock")
    device = ok(response, 201)
    assert device["address"] == account.address
    assert device["revoked_at"] is None
    assert ok(client.get("/v1/devices", headers=person.headers)) == [device]
    # The session that registered the key now belongs to that device.
    assert db.scalars(select(AuthSession.device_id)).one() is not None


def test_lower_case_address_is_stored_checksummed(client, person):
    account = Account.create()
    issued = challenge(client, person)
    body = {
        "address": account.address.lower(),
        "platform": "ios",
        "nonce": issued["nonce"],
        "signature": sign(account, issued["message"]),
    }
    device = ok(client.post("/v1/devices", json=body, headers=person.headers), 201)
    assert device["address"] == account.address


def test_signature_from_another_key_is_refused(client, person):
    account, forger = Account.create(), Account.create()
    issued = challenge(client, person)
    forged = sign(forger, issued["message"])
    error(register(client, person, account, issued["nonce"], forged), 400, "signature_invalid")


def test_signature_of_another_message_is_refused(client, person):
    account = Account.create()
    issued = challenge(client, person)
    other = sign(account, issued["message"].replace(issued["nonce"], "0" * 32))
    error(register(client, person, account, issued["nonce"], other), 400, "signature_invalid")


def test_garbage_signature_is_refused(client, person):
    account = Account.create()
    issued = challenge(client, person)
    response = register(client, person, account, issued["nonce"], "0x" + "00" * 65)
    error(response, 400, "signature_invalid")
    response = register(client, person, account, issued["nonce"], "0x1234")
    body = error(response, 422, "invalid_request")
    assert body["details"][0]["path"] == "body.signature"


def test_a_challenge_works_once(client, person):
    first, second = Account.create(), Account.create()
    issued = challenge(client, person)
    ok(register(client, person, first, issued["nonce"], sign(first, issued["message"])), 201)
    signature = sign(second, issued["message"])
    error(register(client, person, second, issued["nonce"], signature), 400, "challenge_used")


def test_expired_challenge(client, person, db):
    account = Account.create()
    issued = challenge(client, person)
    db.execute(update(DeviceChallenge).values(expires_at=text("now() - interval '1 second'")))
    db.commit()
    signature = sign(account, issued["message"])
    error(register(client, person, account, issued["nonce"], signature), 400, "challenge_expired")


def test_someone_elses_challenge_is_unknown(client, person, login):
    other = login("+994 50 333 33 33")
    account = Account.create()
    issued = challenge(client, other)
    signature = sign(account, issued["message"])
    error(register(client, person, account, issued["nonce"], signature), 400, "challenge_invalid")


def test_a_key_is_registered_only_once(client, person, login):
    account = Account.create()
    issued = challenge(client, person)
    ok(register(client, person, account, issued["nonce"], sign(account, issued["message"])), 201)

    other = login("+994 50 333 33 33")
    issued = challenge(client, other)
    signature = sign(account, issued["message"])
    error(register(client, other, account, issued["nonce"], signature), 409, "device_exists")


def test_revoking_a_key_ends_its_sessions(client, person, login):
    account = Account.create()
    issued = challenge(client, person)
    response = register(client, person, account, issued["nonce"], sign(account, issued["message"]))
    device = ok(response, 201)

    # The lost phone logged in again later: that session is tied to no key, and must end too.
    later_on_lost_phone = login("+994 50 222 22 22")
    # The new phone revokes the key and carries on.
    elsewhere = login("+994 50 222 22 22")
    revoked = ok(client.post(f"/v1/devices/{device['id']}/revoke", headers=elsewhere.headers))
    assert revoked["revoked_at"] is not None
    error(client.get("/v1/me", headers=person.headers), 401, "not_authenticated")
    error(client.get("/v1/me", headers=later_on_lost_phone.headers), 401, "not_authenticated")
    ok(client.get("/v1/me", headers=elsewhere.headers))

    # A revoked key can never come back.
    issued = challenge(client, elsewhere)
    signature = sign(account, issued["message"])
    error(register(client, elsewhere, account, issued["nonce"], signature), 409, "device_exists")


def test_cannot_revoke_someone_elses_device(client, person, login):
    account = Account.create()
    issued = challenge(client, person)
    response = register(client, person, account, issued["nonce"], sign(account, issued["message"]))
    device = ok(response, 201)
    other = login("+994 50 333 33 33")
    error(
        client.post(f"/v1/devices/{device['id']}/revoke", headers=other.headers), 404, "not_found"
    )


def test_log_out_everywhere_else(client, login):
    phone, laptop, tablet = (login("+994 50 444 44 44") for _ in range(3))
    response = client.post("/v1/auth/logout-everywhere", headers=laptop.headers)
    assert response.status_code == 204
    error(client.get("/v1/me", headers=phone.headers), 401, "not_authenticated")
    error(client.get("/v1/me", headers=tablet.headers), 401, "not_authenticated")
    ok(client.get("/v1/me", headers=laptop.headers))
