"""Uploading captured files: what is stored, and what is refused before anything is stored."""

from __future__ import annotations

import contextlib
import io
import struct
import uuid
import zlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from eth_account import Account
from PIL import Image, ImageOps
from sqlalchemy import select, update

from veritas.core.hashing import sha256, to_hex
from veritas.db.models import Device
from veritas.db.models.evidence import CaptureSession, EvidenceItem, PhotoHash
from veritas.evidence.intake import Upload, original_key, prepare
from veritas.evidence.photos import PhotoError, open_photo
from veritas.passport.models import ProofKind
from veritas.services.errors import PayloadTooLarge

from .kit import PDF, Capture, jpeg, photo, register_device, scene, start, upload
from .test_capture import error


@pytest.fixture
def session(client, clock, project, field_worker, phone):
    response = start(client, field_worker, project.id, phone)
    assert response.status_code == 201, response.text
    clock.advance(minutes=5)
    return response.json()


def test_a_photo_is_stored_under_its_hash_with_its_perceptual_hashes(
    client, clock, db, app, session, field_worker
):
    capture = Capture("photo", photo(1), clock.now - timedelta(minutes=2))
    response = upload(client, field_worker, session["id"], capture)
    assert response.status_code == 201, response.text
    item = response.json()

    assert item["sha256"] == capture.sha256
    assert item["size_bytes"] == len(capture.data)
    assert datetime.fromisoformat(item["received_at"]) == clock.now
    assert datetime.fromisoformat(item["captured_at"]) == capture.captured_at
    assert (item["latitude"], item["longitude"], item["accuracy_m"]) == (40.7905, 48.151, 8.0)
    assert item["mock_location"] is False
    assert len(item["phash"]) == 16 and len(item["dhash"]) == 16
    assert item["position"] is None and item["label"] is None

    key = original_key(session["id"], sha256(capture.data))
    assert app.state.storage.get(key) == capture.data
    assert db.scalars(select(PhotoHash)).one().phash.hex() == item["phash"]

    listed = client.get(f"/v1/capture-sessions/{session['id']}", headers=field_worker.headers)
    assert [row["id"] for row in listed.json()["items"]] == [item["id"]]


def test_documents_need_no_position(client, clock, session, field_worker):
    invoice = Capture("invoice", PDF, clock.now, "application/pdf", at=None)
    response = upload(client, field_worker, session["id"], invoice)
    assert response.status_code == 201, response.text
    assert response.json()["latitude"] is None and response.json()["phash"] is None


def test_a_hash_that_does_not_match_is_refused_and_nothing_is_kept(
    client, clock, db, app, session, field_worker
):
    capture = Capture("photo", photo(1), clock.now)
    form = capture.form() | {"sha256": to_hex(sha256(b"something else"))}
    response = client.post(
        f"/v1/capture-sessions/{session['id']}/items",
        data=form,
        files={"file": ("capture", capture.data, "image/jpeg")},
        headers=field_worker.headers,
    )
    body = error(response, 422, "hash_mismatch")
    assert capture.sha256 in body["message"]
    assert db.scalars(select(EvidenceItem)).all() == []
    assert not app.state.storage.exists(original_key(session["id"], sha256(capture.data)))


@pytest.mark.parametrize(
    ("kind", "data", "content_type", "code"),
    [
        ("photo", PDF, "application/pdf", "unsupported_file"),
        ("photo", b"\x89PNG\r\n\x1a\n" + bytes(40), "image/jpeg", "unsupported_file"),
        ("video", b"not a video at all", "video/mp4", "unsupported_file"),
        ("invoice", b"<html>", "text/html", "unsupported_file"),
        ("photo", b"\xff\xd8\xff" + bytes(100), "image/jpeg", "unreadable_photo"),
    ],
)
def test_files_that_are_not_what_they_say_are_refused(
    client, clock, session, field_worker, kind, data, content_type, code
):
    capture = Capture(kind, data, clock.now, content_type)
    status = 422 if code == "unreadable_photo" else 415
    error(upload(client, field_worker, session["id"], capture), status, code)


def test_a_png_that_claims_to_be_a_jpeg_is_refused(client, clock, session, field_worker):
    buffer = io.BytesIO()
    scene(3).save(buffer, format="PNG")
    capture = Capture("photo", buffer.getvalue(), clock.now, "image/png")
    assert upload(client, field_worker, session["id"], capture).status_code == 201
    disguised = Capture("photo", buffer.getvalue()[:-1] + b"\x00", clock.now, "image/jpeg")
    error(upload(client, field_worker, session["id"], disguised), 415, "unsupported_file")


def test_site_photos_need_a_full_gps_fix(client, clock, session, field_worker):
    no_fix = Capture("photo", photo(1), clock.now, at=None)
    error(upload(client, field_worker, session["id"], no_fix), 422, "location_required")

    half = Capture("photo", photo(1), clock.now).form()
    del half["accuracy_m"]
    response = client.post(
        f"/v1/capture-sessions/{session['id']}/items",
        data=half,
        files={"file": ("capture", photo(1), "image/jpeg")},
        headers=field_worker.headers,
    )
    error(response, 400, "incomplete_location")


def test_capture_times_need_a_time_zone(client, clock, session, field_worker):
    form = Capture("photo", photo(1), clock.now).form() | {"captured_at": "2027-03-10T10:01:00"}
    response = client.post(
        f"/v1/capture-sessions/{session['id']}/items",
        data=form,
        files={"file": ("capture", photo(1), "image/jpeg")},
        headers=field_worker.headers,
    )
    error(response, 400, "time_zone_required")


def test_the_same_file_twice_is_refused(client, clock, session, field_worker):
    capture = Capture("photo", photo(1), clock.now)
    first = upload(client, field_worker, session["id"], capture).json()
    body = error(upload(client, field_worker, session["id"], capture), 409, "item_exists")
    assert body["details"] == [{"item_id": first["id"]}]


def test_only_the_person_who_started_the_session_uploads(
    client, clock, session, charity_admin, stranger
):
    capture = Capture("photo", photo(1), clock.now)
    error(upload(client, charity_admin, session["id"], capture), 403, "not_your_session")
    error(upload(client, stranger, session["id"], capture), 403, "not_your_session")


def test_uploads_stop_when_the_session_ends(client, clock, session, field_worker):
    clock.advance(minutes=71)  # 76 minutes after it started: past the upload time
    capture = Capture("photo", photo(1), clock.now)
    body = error(upload(client, field_worker, session["id"], capture), 409, "session_expired")
    assert "start a new one" in body["message"]


def test_files_above_the_size_limit_are_refused(db, app, clock, session):
    capture = SimpleNamespace(id=session["id"])
    upload = Upload(
        kind=ProofKind.INVOICE,
        declared_sha256=sha256(PDF),
        content_type="application/pdf",
        data=PDF,
        captured_at=clock.now,
        fix=None,
        mock_location=False,
    )
    with pytest.raises(PayloadTooLarge):
        prepare(upload, capture, max_bytes=len(PDF) - 1, clock_skew=timedelta(0), now=clock.now)


def refused(response, code: str) -> dict:
    assert response.status_code in (403, 409, 413, 415, 422), response.text
    body = response.json()["error"]
    assert body["code"] == code, body
    return body


def png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def test_photos_built_to_exhaust_the_server_are_refused_before_decoding(
    client, clock, session, field_worker
):
    # 60 megapixels of nothing as a PNG, which cannot be decoded at a smaller scale.
    bomb = png(Image.new("L", (7745, 7745)))
    body = refused(
        upload(client, field_worker, session["id"], Capture("photo", bomb, clock.now, "image/png")),
        "unreadable_photo",
    )
    assert "at most 25 megapixels are accepted in a PNG" in body["message"]
    # 25 megapixels of nothing, padded with a large private chunk to look like a photo.
    small = png(Image.new("L", (5000, 5000)))
    padded = small[:-12] + chunk(b"pAdD", bytes(400_000)) + small[-12:]
    body = refused(
        upload(
            client, field_worker, session["id"], Capture("photo", padded, clock.now, "image/png")
        ),
        "unreadable_photo",
    )
    assert "bytes of picture data" in body["message"]
    # A progressive JPEG whose last scan is repeated over and over: each repeat is another
    # pass over every pixel.
    rescanned = repeat_last_scan(progressive(scene(70, (960, 720))), 70)
    body = refused(
        upload(client, field_worker, session["id"], Capture("photo", rescanned, clock.now)),
        "unreadable_photo",
    )
    assert "scans" in body["message"]
    # Data after the picture, like a phone's motion clip, is not a scan and is not refused.
    clip = photo(71) + bytes([0xFF, 0xDA]) * 70 + bytes(1_000_000)
    response = upload(client, field_worker, session["id"], Capture("photo", clip, clock.now))
    assert response.status_code == 201, response.text
    # A line of pixels, which no camera takes and which once crashed the face detector.
    thin = png(scene(71, (4000, 1)).convert("RGB"))
    body = refused(
        upload(client, field_worker, session["id"], Capture("photo", thin, clock.now, "image/png")),
        "unreadable_photo",
    )
    assert "4000 x 1" in body["message"]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_a_portrait_photo_is_turned_upright_even_when_its_exif_is_damaged():
    """Only the orientation tag is read; nothing rewrites the rest of the EXIF, which a
    damaged tag used to make fail with an error nobody could act on."""
    exif = Image.Exif()
    exif[0x0112] = 6  # rotated: the camera was held upright
    exif[0x0110] = "Veritas Test Phone"
    exif[0x011A] = exif[0x011B] = 72.0  # resolution, stored as fractions
    gps = exif.get_ifd(0x8825)
    gps[2], gps[4] = (40.0, 47.0, 25.8), (48.0, 9.0, 3.6)
    original = jpeg(scene(72, (400, 200)), exif=exif.tobytes())
    assert open_photo(original, "image/jpeg").size == (200, 400)

    start = original.index(b"Exif")
    end = start + int.from_bytes(original[start - 2 : start], "big")
    broken = 0
    for seed in range(4000):  # files damaged a few bytes at a time, the same ones every run
        mutant = bytearray(original)
        for n in range(1 + seed % 6):
            mutant[start + 6 + (seed * 7919 + n * 104729) % (end - start - 6)] ^= (
                1 + (seed * 31 + n) % 255
            )
        data = bytes(mutant)
        try:
            ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
            continue
        except (TypeError, AttributeError, struct.error):
            broken += 1
        except Exception:
            continue
        with contextlib.suppress(PhotoError):  # refused with a reason is fine; a crash is not
            open_photo(data, "image/jpeg")
    assert broken > 0  # the damage that used to escape as a server error was really made


def test_a_jpeg_with_a_second_picture_is_read_as_its_first(client, clock, session, field_worker):
    """An MPF segment holds HDR gain maps, depth and stereo views; the photo is the first."""
    buffer = io.BytesIO()
    first, second = scene(73), scene(74)
    first.save(buffer, format="MPO", save_all=True, append_images=[second])
    data = buffer.getvalue()
    assert data.startswith(b"\xff\xd8\xff")
    response = upload(client, field_worker, session["id"], Capture("photo", data, clock.now))
    assert response.status_code == 201, response.text


def test_capture_times_that_cannot_be_true_are_refused(client, clock, session, field_worker):
    ahead = Capture("photo", photo(75), clock.now + timedelta(minutes=10))
    refused(upload(client, field_worker, session["id"], ahead), "capture_in_future")
    ages_ago = Capture("photo", photo(76), clock.now - timedelta(days=3))
    refused(upload(client, field_worker, session["id"], ages_ago), "capture_too_early")


def test_a_revoked_key_closes_its_session_and_frees_the_milestone(
    client, db, clock, session, field_worker, phone, project
):
    db.execute(update(Device).where(Device.address == phone.address).values(revoked_at=clock.now))
    db.commit()
    late = Capture("photo", photo(77), clock.now)
    refused(upload(client, field_worker, session["id"], late), "device_revoked")
    # A new phone starts the milestone's next session at once: the dead one does not block it.
    new_phone = Account.create()
    register_device(client, field_worker, new_phone)
    response = start(client, field_worker, project.id, new_phone)
    assert response.status_code == 201, response.text


def chunk(kind: bytes, data: bytes) -> bytes:
    """A PNG chunk with its length and CRC."""
    return len(data).to_bytes(4, "big") + kind + data + zlib.crc32(kind + data).to_bytes(4, "big")


def progressive(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, progressive=True)
    return buffer.getvalue()


def repeat_last_scan(data: bytes, times: int) -> bytes:
    """The JPEG with its last scan (its SOS marker and coded data) repeated before the end."""
    last = data.rindex(bytes([0xFF, 0xDA]))
    end = data.rindex(bytes([0xFF, 0xD9]))
    return data[:end] + data[last:end] * times + data[end:]


def test_an_upload_racing_the_manifest_does_not_join_the_submitted_session(
    client, sessions, clock, session, field_worker, monkeypatch
):
    """The file is decoded with no lock held; once the lock is taken the session is read
    again, so a manifest submitted meanwhile closes it."""
    from veritas.evidence import intake as intake_module

    real_prepare = intake_module.prepare

    def prepare_while_the_manifest_lands(upload_, capture, **options):
        prepared = real_prepare(upload_, capture, **options)
        with sessions() as other:
            row = other.get_one(CaptureSession, uuid.UUID(session["id"]))
            row.status, row.submitted_at = "submitted", clock.now
            other.commit()
        return prepared

    monkeypatch.setattr(intake_module, "prepare", prepare_while_the_manifest_lands)
    late = Capture("photo", photo(78), clock.now)
    refused(upload(client, field_worker, session["id"], late), "session_submitted")
