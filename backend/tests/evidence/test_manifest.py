"""The signed manifest: it must be canonical, honest about the uploads and signed by the phone."""

from __future__ import annotations

import json

import pytest
from eth_account import Account
from sqlalchemy import select, update

from veritas.core.canonical import canonical_json
from veritas.core.hashing import sha256, to_hex
from veritas.db.models import CharityMember, Device
from veritas.db.models.evidence import CaptureSession, EvidenceBundle, EvidenceItem
from veritas.evidence.manifest import ManifestError, read_manifest, signing_text

from .kit import (
    Capture,
    attest,
    manifest_for,
    photo,
    proof_set,
    sign_manifest,
    start,
    submit,
    upload,
)
from .test_capture import error


@pytest.fixture
def uploaded(client, clock, project, field_worker, phone):
    """An open session with the milestone's proof uploaded, and the captures."""
    session = start(client, field_worker, project.id, phone).json()
    captures = proof_set(clock.now)
    clock.advance(minutes=8)
    for capture in captures:
        assert upload(client, field_worker, session["id"], capture).status_code == 201
    return session, captures


def test_a_signed_manifest_becomes_a_bundle_hashed_over_its_exact_bytes(
    client, clock, db, settings, uploaded, field_worker, phone
):
    session, captures = uploaded
    data = manifest_for(session, phone.address, captures)
    token = attest(settings, phone.address, session["id"], data)
    response = submit(client, field_worker, session["id"], data, sign_manifest(phone, data), token)
    assert response.status_code == 201, response.text
    bundle = response.json()

    assert bundle["status"] == "draft"
    assert bundle["bundle_hash"] == to_hex(sha256(data))
    assert bundle["attempt"] == 1 and bundle["milestone"] == 0
    assert [item["label"] for item in bundle["items"]] == [
        "photo 1",
        "photo 2",
        "photo 3",
        "photo 4",
        "invoice 1",
        "fiscal receipt 1",
    ]
    assert [item["sha256"] for item in bundle["items"]] == [c.sha256 for c in captures]
    assert bundle["checks"] == [] and bundle["report"] is None

    row = db.get(EvidenceBundle, bundle["id"])
    assert row.manifest_bytes == data and row.attestation == token
    assert db.get(CaptureSession, session["id"]).status == "submitted"

    # The session is closed now.
    more = Capture("photo", photo(9), clock.now)
    error(upload(client, field_worker, session["id"], more), 409, "session_submitted")
    again = submit(client, field_worker, session["id"], data, sign_manifest(phone, data))
    error(again, 409, "session_submitted")


def test_the_manifest_may_list_files_in_any_order(client, clock, uploaded, field_worker, phone):
    session, captures = uploaded
    reordered = [captures[4], *captures[:4], captures[5]]
    data = manifest_for(session, phone.address, reordered)
    response = submit(client, field_worker, session["id"], data, sign_manifest(phone, data))
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["kind"] == "invoice"


def test_bytes_that_are_not_canonical_are_refused(client, uploaded, field_worker, phone):
    session, captures = uploaded
    pretty = json.dumps(json.loads(manifest_for(session, phone.address, captures)), indent=2)
    data = pretty.encode()
    body = error(
        submit(client, field_worker, session["id"], data, sign_manifest(phone, data)),
        422,
        "manifest_invalid",
    )
    assert "canonical JSON" in body["message"]


def test_missing_and_unknown_fields_are_named(client, uploaded, field_worker, phone):
    session, captures = uploaded
    document = json.loads(manifest_for(session, phone.address, captures))
    del document["items"][1]["location"]
    document["note"] = "hello"
    data = canonical_json(document)
    body = error(
        submit(client, field_worker, session["id"], data, sign_manifest(phone, data)),
        422,
        "manifest_invalid",
    )
    assert {"path": "items[1].location", "message": "is required"} in body["details"]
    assert {"path": "note", "message": "is not a known field, remove it"} in body["details"]


def test_a_manifest_for_another_session_or_with_another_code_is_refused(
    client, uploaded, field_worker, phone
):
    session, captures = uploaded
    wrong = session | {"challenge_code": "ZZZZZZ", "attempt": 2}
    data = manifest_for(wrong, phone.address, captures)
    body = error(
        submit(client, field_worker, session["id"], data, sign_manifest(phone, data)),
        422,
        "manifest_mismatch",
    )
    paths = {detail["path"] for detail in body["details"]}
    assert paths == {"challenge_code", "attempt"}


def test_the_manifest_must_list_exactly_what_was_uploaded(client, uploaded, field_worker, phone):
    session, captures = uploaded
    changed = [*captures[:5]]  # the receipt is left out
    changed[0] = Capture("photo", photo(777), captures[0].captured_at)  # never uploaded
    changed[1] = Capture(  # uploaded, but the manifest moves it
        "photo", captures[1].data, captures[1].captured_at, at=(40.7906, 48.151)
    )
    changed[2] = Capture("document", captures[2].data, captures[2].captured_at)  # wrong kind
    changed.append(captures[3])  # listed twice
    data = manifest_for(session, phone.address, changed)
    body = error(
        submit(client, field_worker, session["id"], data, sign_manifest(phone, data)),
        422,
        "manifest_mismatch",
    )
    messages = {(detail["path"], detail["message"]) for detail in body["details"]}
    assert ("items[0].sha256", "no file with this SHA-256 was uploaded") in messages
    assert ("items[1].location", "differs from the GPS fix sent with the upload") in messages
    assert ("items[2].kind", "is document but the upload said photo") in messages
    assert ("items[5].sha256", "lists the same file as items[3]") in messages
    left_out = [message for path, message in messages if path == "items"]
    assert any("fiscal receipt" in message for message in left_out)
    assert any(captures[0].sha256 in message for message in left_out)


def test_a_manifest_signed_by_another_key_is_refused(client, db, uploaded, field_worker, phone):
    session, captures = uploaded
    data = manifest_for(session, phone.address, captures)
    forged = sign_manifest(Account.create(), data)
    error(submit(client, field_worker, session["id"], data, forged), 403, "bad_signature")
    assert db.scalars(select(EvidenceBundle)).all() == []


def test_a_revoked_key_or_a_former_member_cannot_submit(
    client, clock, db, uploaded, field_worker, phone
):
    session, captures = uploaded
    data = manifest_for(session, phone.address, captures)
    signature = sign_manifest(phone, data)

    db.execute(update(Device).where(Device.address == phone.address).values(revoked_at=clock.now))
    db.commit()
    error(submit(client, field_worker, session["id"], data, signature), 403, "device_revoked")

    db.execute(update(Device).where(Device.address == phone.address).values(revoked_at=None))
    db.execute(
        CharityMember.__table__.delete().where(CharityMember.user_id == field_worker.user_id)
    )
    db.commit()
    error(submit(client, field_worker, session["id"], data, signature), 403, "not_a_member")
    assert db.scalars(select(EvidenceItem.position)).all() == [None] * len(captures)


def test_the_signed_text_names_the_hash():
    digest = sha256(b"manifest")
    assert signing_text(digest) == "Veritas evidence manifest\n" + to_hex(digest)


@pytest.mark.parametrize(
    ("change", "path"),
    [
        ({"device": "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65"}, "device"),
        ({"challenge_code": "K7Q2M0"}, "challenge_code"),
        ({"milestone": True}, "milestone"),
        ({"items": []}, "items"),
    ],
)
def test_manifest_values_have_one_spelling(change, path):
    document = {
        "format": "veritas.evidence.manifest/1",
        "session_id": "6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13",
        "project_id": "6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13",
        "milestone": 0,
        "attempt": 1,
        "challenge_code": "K7Q2MX",
        "device": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
        "items": [
            {
                "kind": "photo",
                "sha256": "0x" + "ab" * 32,
                "size": 10,
                "content_type": "image/jpeg",
                "captured_at": "2027-03-10T06:01:02Z",
                "location": {
                    "latitude": 40.79,
                    "longitude": 48.15,
                    "accuracy_m": 5,
                    "mocked": False,
                },
            }
        ],
    }
    assert read_manifest(canonical_json(document)).items[0].location.accuracy_m == 5.0
    with pytest.raises(ManifestError) as caught:
        read_manifest(canonical_json(document | change))
    assert path in {problem["path"].split("[")[0] for problem in caught.value.problems}


@pytest.mark.parametrize(
    "body",
    [
        '{"manifest": "' + "[" * 5000 + "]" * 5000 + '", "signature": "0x' + "11" * 65 + '"}',
        r'{"manifest": "\ud800", "signature": "0x' + "11" * 65 + '"}',
        '{"manifest": "{}", "signature": "0x' + "11" * 65 + r'", "attestation": "dev1.\u0000"}',
    ],
    ids=["nested too deep", "lone surrogate", "attestation with a NUL"],
)
def test_malformed_submissions_get_a_reason_not_a_server_error(
    client, uploaded, field_worker, body
):
    session, _ = uploaded
    response = client.post(
        f"/v1/capture-sessions/{session['id']}/manifest",
        content=body.encode("ascii"),
        headers={**field_worker.headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] in ("manifest_invalid", "invalid_request")
