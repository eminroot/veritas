"""Charities, contractors and officers, from registration to verification."""

from eth_account import Account
from eth_account.messages import encode_defunct
from support import CHARITY, CONTRACTOR, OFFICER, PDF, PNG, error, ok, upload

from veritas.core.hashing import sha256, to_hex
from veritas.storage import kyb_key


def test_charity_registration_review_and_verification(
    client, charity_admin, admin, new_charity, settings
):
    charity = new_charity()
    assert charity["status"] == "draft"
    assert charity["voen"] == "1700000011"
    assert charity["contact_phone"] == "+994123456789"
    assert charity["your_role"] == "admin"
    base = f"/v1/charities/{charity['id']}"

    error(client.post(f"{base}/submit", headers=charity_admin.headers), 409, "documents_missing")
    document = ok(upload(client, f"{base}/documents", charity_admin), 201)
    assert document["sha256"] == to_hex(sha256(PDF))
    assert document["size_bytes"] == len(PDF)
    stored = settings.storage_dir.joinpath(*kyb_key(charity["id"], sha256(PDF)).split("/"))
    assert stored.read_bytes() == PDF
    ok(
        upload(
            client,
            f"{base}/documents",
            charity_admin,
            data=PNG,
            content_type="image/png",
            kind="director_id",
            filename="C:\\scans\\id card.png",
        ),
        201,
    )

    submitted = ok(client.post(f"{base}/submit", headers=charity_admin.headers))
    assert submitted["status"] == "submitted"
    assert [d["filename"] for d in submitted["documents"]] == ["registration.pdf", "id card.png"]
    error(
        client.patch(base, json={"website": None}, headers=charity_admin.headers),
        409,
        "status_conflict",
    )

    queue = ok(client.get("/v1/charities?status=submitted", headers=admin.headers))
    assert [c["id"] for c in queue] == [charity["id"]]
    error(client.post(f"{base}/verify", json={}, headers=charity_admin.headers), 403, "admin_only")
    rejected = ok(
        client.post(f"{base}/reject", json={"notes": "Charter is unsigned."}, headers=admin.headers)
    )
    assert rejected["status"] == "rejected"
    assert rejected["review_notes"] == "Charter is unsigned."

    fixed = ok(client.patch(base, json={"legal_form": "Foundation"}, headers=charity_admin.headers))
    assert fixed["legal_form"] == "Foundation"
    ok(client.post(f"{base}/submit", headers=charity_admin.headers))
    verified = ok(client.post(f"{base}/verify", json={"notes": "All good."}, headers=admin.headers))
    assert verified["status"] == "verified"
    assert verified["verified_at"] is not None

    # The admin can read the uploaded file back, byte for byte.
    response = client.get(f"/v1/documents/{document['id']}", headers=admin.headers)
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-content-sha256"] == to_hex(sha256(PDF))


def test_charity_input_is_checked(client, charity_admin, new_charity):
    response = client.post(
        "/v1/charities",
        json={**CHARITY, "voen": "17", "contact_email": "nope", "legal_name": "  "},
        headers=charity_admin.headers,
    )
    details = {d["path"]: d["message"] for d in error(response, 422, "invalid_request")["details"]}
    assert details["body.legal_name"] == "must not be empty"
    assert "VÖEN" in details["body.voen"]
    assert details["body.contact_email"] == "is not in the expected format"

    new_charity()
    response = client.post("/v1/charities", json=CHARITY, headers=charity_admin.headers)
    error(response, 409, "voen_taken")


def test_documents_are_checked(client, charity_admin, new_charity, settings):
    charity = new_charity()
    url = f"/v1/charities/{charity['id']}/documents"
    error(upload(client, url, charity_admin, content_type="text/plain"), 415, "unsupported_file")
    error(upload(client, url, charity_admin, data=PNG), 415, "unsupported_file")
    error(upload(client, url, charity_admin, data=b""), 422, "empty_file")
    too_big = b"%PDF-" + bytes(settings.max_upload_bytes)
    error(upload(client, url, charity_admin, data=too_big), 413, "file_too_large")
    ok(upload(client, url, charity_admin), 201)
    error(upload(client, url, charity_admin), 409, "document_exists")
    response = client.post(
        url, data={"kind": "selfie"}, files={"file": ("a.pdf", PDF)}, headers=charity_admin.headers
    )
    assert error(response, 422, "invalid_request")["details"][0]["path"] == "body.kind"


def test_members_and_roles(client, charity_admin, new_charity, login):
    charity = new_charity()
    base = f"/v1/charities/{charity['id']}"
    member = ok(
        client.post(
            f"{base}/members", json={"phone": "055 444 44 44"}, headers=charity_admin.headers
        ),
        201,
    )
    assert member["phone"] == "+994554444444"
    assert member["role"] == "field_worker"
    response = client.post(
        f"{base}/members", json={"phone": "+994554444444"}, headers=charity_admin.headers
    )
    error(response, 409, "already_member")

    # The account was waiting for them; on login they see the membership.
    worker = login("+994554444444")
    me = ok(client.get("/v1/me", headers=worker.headers))
    assert me["memberships"] == [
        {
            "charity_id": charity["id"],
            "charity_name": CHARITY["legal_name"],
            "charity_status": "draft",
            "role": "field_worker",
        }
    ]
    ok(client.get(base, headers=worker.headers))
    response = client.patch(base, json={"website": None}, headers=worker.headers)
    error(response, 403, "role_required")
    error(
        client.post(f"{base}/members", json={"phone": "+994555555555"}, headers=worker.headers),
        403,
        "role_required",
    )

    stranger = login("+994 70 666 66 66")
    error(client.get(base, headers=stranger.headers), 403, "not_a_member")
    assert ok(client.get("/v1/charities", headers=stranger.headers)) == []
    assert len(ok(client.get(f"{base}/members", headers=charity_admin.headers))) == 2


def test_signing_key_needs_a_verified_charity_and_proof(
    client, charity_admin, new_charity, verified_charity
):
    account = Account.create()
    base = f"/v1/charities/{verified_charity['id']}"
    issued = ok(client.post(f"{base}/signer/challenge", headers=charity_admin.headers), 201)
    assert verified_charity["id"] in issued["message"]
    signature = account.sign_message(encode_defunct(text=issued["message"])).signature.to_0x_hex()
    body = {"address": account.address, "nonce": issued["nonce"], "signature": signature}
    charity = ok(client.put(f"{base}/signer", json=body, headers=charity_admin.headers))
    assert charity["signer_address"] == account.address

    # A device challenge cannot be used to set a charity key.
    device = ok(client.post("/v1/devices/challenge", headers=charity_admin.headers), 201)
    signature = account.sign_message(encode_defunct(text=device["message"])).signature.to_0x_hex()
    body = {"address": account.address, "nonce": device["nonce"], "signature": signature}
    error(
        client.put(f"{base}/signer", json=body, headers=charity_admin.headers),
        400,
        "challenge_invalid",
    )

    draft = new_charity(voen="1700000022")
    issued = ok(
        client.post(f"/v1/charities/{draft['id']}/signer/challenge", headers=charity_admin.headers),
        201,
    )
    signature = account.sign_message(encode_defunct(text=issued["message"])).signature.to_0x_hex()
    body = {"address": account.address, "nonce": issued["nonce"], "signature": signature}
    response = client.put(
        f"/v1/charities/{draft['id']}/signer", json=body, headers=charity_admin.headers
    )
    error(response, 409, "charity_not_verified")


def test_contractor_registration_and_verification(
    client, charity_admin, admin, verified_charity, login
):
    body = {**CONTRACTOR, "charity_id": verified_charity["id"]}
    contractor = ok(client.post("/v1/contractors", json=body, headers=charity_admin.headers), 201)
    assert contractor["status"] == "submitted"
    assert contractor["iban"] == "AZ21NABZ00000000137010001944"
    assert contractor["registry_status"] == "unchecked"
    base = f"/v1/contractors/{contractor['id']}"
    document = ok(upload(client, f"{base}/documents", charity_admin, kind="tax_registration"), 201)
    assert document["owner_type"] == "contractor"

    error(
        client.post("/v1/contractors", json=body, headers=charity_admin.headers), 409, "voen_taken"
    )
    stranger = login("+994 70 666 66 66")
    error(client.post("/v1/contractors", json=body, headers=stranger.headers), 403, "not_a_member")
    error(client.get(base, headers=stranger.headers), 403, "forbidden")
    error(client.get(f"/v1/documents/{document['id']}", headers=stranger.headers), 403, "forbidden")

    # Manual registry results: admins and officers only.
    check = {"status": "manual_ok", "note": "Checked on e-taxes.gov.az"}
    error(
        client.put(f"{base}/registry", json=check, headers=charity_admin.headers),
        403,
        "reviewer_only",
    )
    officer_person = login("+994 50 777 77 77")
    ok(
        client.post(
            "/v1/officers", json={**OFFICER, "phone": officer_person.phone}, headers=admin.headers
        ),
        201,
    )
    checked = ok(client.put(f"{base}/registry", json=check, headers=officer_person.headers))
    assert checked["registry_status"] == "manual_ok"
    assert checked["registry_checked_at"] is not None
    response = client.get(f"/v1/documents/{document['id']}", headers=officer_person.headers)
    assert response.status_code == 200
    assert response.content == PDF

    verified = ok(client.post(f"{base}/verify", json={}, headers=admin.headers))
    assert verified["status"] == "verified"
    response = client.patch(base, json={"director_name": "Someone"}, headers=charity_admin.headers)
    error(response, 409, "status_conflict")
    assert [
        c["id"] for c in ok(client.get("/v1/contractors?voen=1300000021", headers=admin.headers))
    ] == [contractor["id"]]


def test_contractor_with_an_inactive_registry_entry_is_not_verified(
    client, charity_admin, admin, verified_charity
):
    body = {**CONTRACTOR, "charity_id": verified_charity["id"]}
    contractor = ok(client.post("/v1/contractors", json=body, headers=charity_admin.headers), 201)
    base = f"/v1/contractors/{contractor['id']}"
    ok(client.put(f"{base}/registry", json={"status": "inactive"}, headers=admin.headers))
    error(client.post(f"{base}/verify", json={}, headers=admin.headers), 409, "registry_inactive")
    rejected = ok(
        client.post(f"{base}/reject", json={"notes": "Inactive VÖEN."}, headers=admin.headers)
    )
    assert rejected["status"] == "rejected"
    # Fixing the details puts it back in the queue.
    again = ok(client.patch(base, json={"voen": "1300000032"}, headers=charity_admin.headers))
    assert again["status"] == "submitted"


def test_officers(client, admin, login):
    person = login("+994 50 888 88 88")
    error(client.post("/v1/officers", json=OFFICER, headers=person.headers), 403, "admin_only")
    officer = ok(client.post("/v1/officers", json=OFFICER, headers=admin.headers), 201)
    assert officer["address"] == "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
    assert officer["status"] == "active"
    error(client.post("/v1/officers", json=OFFICER, headers=admin.headers), 409, "address_taken")

    listed = ok(client.get("/v1/officers", headers=person.headers))
    assert listed == [
        {
            "id": officer["id"],
            "name": "Nərmin Əliyeva",
            "organisation": "Sample Audit Partners",
            "address": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
            "status": "active",
        }
    ]
    ok(client.post(f"/v1/officers/{officer['id']}/deactivate", headers=admin.headers))
    assert ok(client.get("/v1/officers", headers=person.headers)) == []
    everyone = ok(client.get("/v1/officers?include_inactive=true", headers=admin.headers))
    assert [o["status"] for o in everyone] == ["inactive"]
    error(
        client.post("/v1/officers", json={**OFFICER, "address": "0x1234"}, headers=admin.headers),
        422,
        "invalid_request",
    )
