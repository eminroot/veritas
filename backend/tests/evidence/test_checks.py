"""The deterministic checks, each with evidence that passes and evidence that fails it.

Bundles are made through the API, as the app makes them. Where a check guards against
something the API already refuses (a forged signature, a file changed in storage), the test
does the damage afterwards, as someone with access to the database or the bucket could.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import update

from veritas.db.models import Device, Milestone
from veritas.db.models.evidence import CheckStatus, EvidenceBundle
from veritas.evidence.attestation import PlatformAttestation
from veritas.evidence.checks import (
    LATER,
    NOT_YET,
    Result,
    Tools,
    checklist,
    integrity,
    load_evidence,
    passed,
    place,
    run_checks,
    timing,
)
from veritas.evidence.manifest import signing_text
from veritas.evidence.wording import baku_day, baku_time

from .kit import (
    FAR_AWAY,
    JUST_NORTH,
    Capture,
    mentions,
    photo,
    proof_set,
    run,
    start,
    tamper,
    upload,
)

# ---------------------------------------------------------------- 1: files and signatures


def test_files_signature_and_attestation_pass(db, tools, clock, make):
    result = run(db, make(proof_set(clock.now)), tools, integrity.check)
    assert result.status == CheckStatus.PASSED, result.reason
    assert all(row["matches"] for row in result.details["files"])
    assert result.details["attestation"] == {"scheme": "dev", "valid": True, "reason": None}


def test_a_file_changed_or_lost_in_storage_fails(db, app, tools, clock, make):
    bundle = make(proof_set(clock.now))
    storage = app.state.storage
    keys = {
        item["label"]: f"evidence/{bundle['session_id']}/{item['sha256'][2:]}"
        for item in bundle["items"]
    }
    storage.put(keys["photo 2"], b"\xff\xd8\xff" + b"edited" * 10)
    storage.delete(keys["invoice 1"])

    result = run(db, bundle, tools, integrity.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(
        result,
        "photo 2: the stored file does not match its SHA-256 in the manifest",
        "invoice 1: the original is missing from private storage",
    )
    files = {row["item"]: row["matches"] for row in result.details["files"]}
    assert files == {
        "photo 1": True,
        "photo 2": False,
        "photo 3": True,
        "photo 4": True,
        "invoice 1": False,
        "fiscal receipt 1": True,
    }


def test_a_signature_from_another_key_fails(db, tools, clock, make):
    bundle = make(proof_set(clock.now))
    row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
    message = encode_defunct(text=signing_text(row.bundle_hash))
    forged = Account.sign_message(message, private_key=Account.create().key).signature
    tamper(db, bundle, device_signature=bytes(forged))

    result = run(db, bundle, tools, integrity.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(result, "not signed by the capture session's device key")
    assert result.details["signed_by_capture_device"] is False


def test_a_revoked_device_key_fails(db, tools, clock, make, phone):
    bundle = make(proof_set(clock.now))
    db.execute(
        update(Device)
        .where(Device.address == phone.address)
        .values(revoked_at=datetime(2027, 3, 11, 8, tzinfo=UTC))
    )
    db.commit()
    result = run(db, bundle, tools, integrity.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(result, "the device key was revoked on 11 March 2027")
    assert result.details["device_revoked_at"].startswith("2027-03-11")


def test_a_revoked_key_is_named_first_however_many_files_are_missing(
    db, app, tools, clock, make, phone
):
    """The reason shows four problems; the key's revocation must not be among those cut."""
    bundle = make(proof_set(clock.now))
    for item in bundle["items"]:
        app.state.storage.delete(f"evidence/{bundle['session_id']}/{item['sha256'][2:]}")
    db.execute(
        update(Device)
        .where(Device.address == phone.address)
        .values(revoked_at=datetime(2027, 3, 11, 8, tzinfo=UTC))
    )
    db.commit()
    result = run(db, bundle, tools, integrity.check)
    assert result.reason.startswith("The device key was revoked on 11 March 2027")


def test_an_attestation_for_something_else_fails(db, settings, tools, clock, make):
    bundle = make(proof_set(clock.now), attestation=False)
    result = run(db, bundle, tools, integrity.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(result, "the app attestation is not valid: the app sent no attestation token")

    tamper(db, bundle, attestation="dev1." + "00" * 32)
    result = run(db, bundle, tools, integrity.check)
    assert mentions(result, "was not made for this device, session and manifest")


def test_without_app_attest_and_play_integrity_nothing_is_attested(db, app, clock, make, settings):
    bundle = make(proof_set(clock.now))
    production_like = Tools(
        storage=app.state.storage, attestation=PlatformAttestation(), settings=settings
    )
    result = run(db, bundle, production_like, integrity.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(result, "App Attest and Play Integrity checks are not built yet")
    attested = result.details["attestation"]
    assert attested["scheme"] == "platform" and attested["valid"] is False
    assert "not built yet" in attested["reason"]


# ---------------------------------------------------------------- 2: on the site


def test_photos_inside_the_site_pass_and_documents_are_not_placed(db, tools, clock, make):
    result = run(db, make(proof_set(clock.now)), tools, place.check)
    assert result.status == CheckStatus.PASSED, result.reason
    assert [row["item"] for row in result.details["captures"]] == [
        "photo 1",
        "photo 2",
        "photo 3",
        "photo 4",
    ]
    assert all(row["distance_m"] == 0 for row in result.details["captures"])


def test_a_fix_just_outside_fails_unless_its_accuracy_reaches_the_site(db, tools, clock, make):
    captures = proof_set(clock.now)
    captures[1] = Capture("photo", photo(11), captures[1].captured_at, at=JUST_NORTH, accuracy_m=10)
    captures[2] = Capture("photo", photo(12), captures[2].captured_at, at=JUST_NORTH, accuracy_m=30)
    result = run(db, make(captures), tools, place.check)

    assert result.status == CheckStatus.FAILED
    assert result.reason == (
        "Photo 2 is 22 m outside the site, more than its GPS accuracy of 10 m."
    )
    rows = {row["item"]: row for row in result.details["captures"]}
    assert rows["photo 2"] == {
        "item": "photo 2",
        "accuracy_m": 10.0,
        "distance_m": 22.2,
        "on_site": False,
    }
    assert rows["photo 3"]["on_site"] is True and rows["photo 3"]["distance_m"] == 22.2


def test_mocked_and_imprecise_fixes_fail(db, tools, clock, make):
    captures = proof_set(clock.now)
    captures[0] = Capture("photo", photo(21), captures[0].captured_at, mocked=True)
    captures[3] = Capture("photo", photo(24), captures[3].captured_at, accuracy_m=80)
    captures.append(
        Capture("video", b"\x00\x00\x00\x18ftypmp42", clock.now, "video/mp4", at=FAR_AWAY)
    )
    result = run(db, make(captures), tools, place.check)

    assert result.status == CheckStatus.FAILED
    assert mentions(
        result,
        "photo 1 was taken with a mocked location",
        "photo 4's GPS fix is too imprecise to place it on the site: accuracy 80 m, at most "
        "50 m is accepted",
        "video 1 is 151.0 km outside the site, more than its GPS accuracy of 8 m",
    )


# ---------------------------------------------------------------- 3: on time


def test_captures_inside_the_window_and_the_session_pass(db, tools, clock, make):
    result = run(db, make(proof_set(clock.now)), tools, timing.check)
    assert result.status == CheckStatus.PASSED, result.reason
    assert result.details["window"] == {
        "opens_at": "2027-02-28T20:00:00Z",
        "closes_at": "2027-03-31T20:00:00Z",
    }
    assert all(row["on_time"] for row in result.details["captures"])


def test_a_capture_before_the_window_opened_fails(db, tools, clock, make):
    clock.now = datetime(2027, 2, 28, 20, 5, tzinfo=UTC)  # 00:05 on 1 March in Baku
    captures = proof_set(clock.now)
    captures[0] = Capture("photo", photo(31), clock.now - timedelta(minutes=7))
    result = run(db, make(captures), tools, timing.check)

    assert result.status == CheckStatus.FAILED
    assert result.reason == (
        "Photo 1 was captured at 2027-02-28 23:58:00 Baku time, before milestone 0's window "
        "opened on 1 March 2027; photo 1 was captured at 2027-02-28 23:58:00 Baku time, "
        "7 minutes before the challenge code was issued at 2027-03-01 00:05:00 Baku time."
    )


def test_a_capture_after_the_window_closed_is_an_advisory_in_the_grace_period(
    db, tools, clock, make
):
    """The escrow takes first evidence until the end of the window plus the grace period, so a
    late capture blocks nothing; the officer and donors see that it was late."""
    clock.now = datetime(2027, 3, 31, 19, 55, tzinfo=UTC)  # 23:55 on 31 March in Baku
    captures = proof_set(clock.now)
    captures[3] = Capture("photo", photo(34), datetime(2027, 3, 31, 20, 2, tzinfo=UTC))
    result = run(db, make(captures), tools, timing.check)

    assert result.status == CheckStatus.ADVISORY
    assert mentions(
        result,
        "Photo 4, invoice 1 and fiscal receipt 1 were captured after milestone 0's window "
        "closed at the end of 31 March 2027, during the grace period",
    )
    late = {row["item"] for row in result.details["captures"] if row["after_window"]}
    assert late == {"photo 4", "invoice 1", "fiscal receipt 1"}  # 00:01 and 00:02 too
    assert all(row["on_time"] for row in result.details["captures"])


def test_a_session_started_after_the_window_captured_after_it_whatever_the_phone_says(
    db, tools, clock, make
):
    """Nothing is captured before its challenge code exists, so a phone setting its clock back
    within the allowed skew does not move a capture into the window."""
    clock.now = datetime(2027, 3, 31, 20, 0, 30, tzinfo=UTC)  # 30 s after the window closed
    captures = [
        Capture(c.kind, c.data, datetime(2027, 3, 31, 19, 59, 30, tzinfo=UTC), c.content_type, c.at)
        for c in proof_set(clock.now)
    ]
    result = run(db, make(captures), tools, timing.check)
    assert result.status == CheckStatus.ADVISORY
    assert all(row["after_window"] for row in result.details["captures"])


def test_a_resubmission_after_a_rejection_is_captured_after_the_window(
    db, tools, clock, make, project
):
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == project.id, Milestone.index == 0)
        .values(
            status="rejected",
            attempt=1,
            resubmit_deadline=datetime(2027, 4, 20, 20, tzinfo=UTC),
        )
    )
    db.commit()
    clock.now = datetime(2027, 4, 3, 6, tzinfo=UTC)
    result = run(db, make(proof_set(clock.now)), tools, timing.check)
    assert result.status == CheckStatus.PASSED, result.reason
    assert result.details["attempt"] == 2


def test_a_capture_time_at_the_end_of_time_is_reported_not_crashed_on():
    moment = datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)
    assert baku_time(moment) == "9999-12-31T23:59:59+00:00"
    assert baku_day(moment) == "31 December 9999"
    # With an offset the UTC moment itself is past the calendar: still words, never a crash.
    for edge in ("9999-12-31T23:00:00-05:00", "0001-01-01T00:00:00+14:00"):
        assert baku_time(datetime.fromisoformat(edge)) == edge


def test_captures_outside_the_session_or_ahead_of_the_server_fail(db, tools, clock, make):
    issued = clock.now
    captures = proof_set(issued)
    captures[0] = Capture("photo", photo(41), issued - timedelta(minutes=1))  # within the skew
    captures[1] = Capture("photo", photo(42), issued - timedelta(minutes=5))
    captures[2] = Capture("photo", photo(43), issued + timedelta(minutes=20))
    bundle = make(captures)  # uploads arrive at issued + 21 minutes
    captures_late = run(db, bundle, tools, timing.check)

    assert captures_late.status == CheckStatus.FAILED
    assert "photo 1" not in captures_late.reason.lower()
    assert mentions(
        captures_late,
        "photo 2 was captured at 2027-03-10 09:55:00 Baku time, 5 minutes before the challenge "
        "code was issued at 2027-03-10 10:00:00 Baku time",
        "photo 3 was captured at 2027-03-10 10:20:00 Baku time, 5 minutes after the challenge "
        "code expired at 2027-03-10 10:15:00 Baku time",
    )


def test_a_phone_clock_ahead_of_the_server_is_refused_at_upload(
    client, clock, field_worker, phone, project
):
    """A capture cannot come from the future; such a time is refused before it is stored, so
    no check ever has to word a time at the end of the calendar."""
    session = start(client, field_worker, project.id, phone).json()
    clock.advance(minutes=8)
    ahead = Capture("photo", photo(51), clock.now + timedelta(minutes=4))
    refused = upload(client, field_worker, session["id"], ahead)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "capture_in_future"
    doomsday = Capture("photo", photo(52), datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC))
    refused = upload(client, field_worker, session["id"], doomsday)
    assert refused.json()["error"]["code"] == "capture_in_future"


# ---------------------------------------------------------------- 11: the checklist


def test_a_complete_bundle_meets_the_checklist(db, tools, clock, make):
    result = run(db, make(proof_set(clock.now)), tools, checklist.check)
    assert result.status == CheckStatus.PASSED
    assert result.details["present"] == {"fiscal_receipt": 1, "invoice": 1, "photo": 4}


def test_missing_proof_is_named_with_what_the_passport_asked_for(db, tools, clock, make):
    captures = proof_set(clock.now, photos=3)[:-1]  # three photos and the invoice
    result = run(db, make(captures), tools, checklist.check)
    assert result.status == CheckStatus.FAILED
    assert result.reason == (
        "The checklist asks for 4 photos (The bare frame from each side of the building, "
        "challenge code visible) and the bundle has 3; the checklist asks for 1 fiscal receipt "
        "(e-kassa receipt for the timber) and the bundle has 0."
    )


# ---------------------------------------------------------------- all of them


def test_every_check_has_a_result_and_the_later_ones_say_why_they_did_not_run(
    db, tools, clock, make
):
    bundle = make(proof_set(clock.now))
    db.expire_all()
    row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
    results = run_checks(db, load_evidence(db, row), tools)

    assert [result.number for result in results] == list(range(1, 12))
    for result in results:
        if result.number in NOT_YET:
            assert result.status == CheckStatus.NOT_RUN
            assert result.reason == LATER
        else:
            assert result.status == CheckStatus.PASSED, (result.number, result.reason)
    assert passed(results)


def test_only_hard_failures_count():
    assert passed([Result(5, CheckStatus.ADVISORY, "close"), Result(4, CheckStatus.NOT_RUN, "x")])
    assert not passed([Result(1, CheckStatus.FAILED, "broken"), Result(2, CheckStatus.PASSED)])
    with pytest.raises(ValueError, match="needs a reason"):
        Result(2, CheckStatus.FAILED)
    with pytest.raises(ValueError, match="cannot fail"):
        Result(7, CheckStatus.FAILED, "advisory checks only advise")
