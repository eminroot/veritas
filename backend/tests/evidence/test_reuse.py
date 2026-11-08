"""Check 5: a photo stored before, anywhere, fails; one that only looks close is advisory."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import delete, select, text

from veritas.db.models import Device, Project, User
from veritas.db.models.evidence import CaptureSession, CheckStatus, EvidenceItem, PhotoHash
from veritas.evidence.checks import reuse
from veritas.evidence.photos import hamming, open_photo, perceptual_hashes

from .kit import (
    Capture,
    jpeg,
    mentions,
    near_copy,
    photo,
    proof_set,
    reframed,
    run,
    start,
    upload,
)


def hashes(data: bytes):
    return perceptual_hashes(open_photo(data, "image/jpeg"))


def test_the_test_pictures_behave_like_photos():
    original = photo(8)
    copy, close, other = hashes(near_copy(original)), hashes(reframed(8)), hashes(photo(9))
    first = hashes(original)
    assert hamming(first.phash, copy.phash) <= 2 and hamming(first.dhash, copy.dhash) <= 2
    assert 6 < hamming(first.phash, close.phash) <= 12
    assert hamming(first.dhash, close.dhash) <= 12
    assert hamming(first.phash, other.phash) > 20 and hamming(first.dhash, other.dhash) > 20


def test_new_photos_pass(db, tools, clock, make):
    make(proof_set(clock.now, seed=1))
    clock.advance(minutes=30)
    result = run(db, make(proof_set(clock.now, seed=2)), tools, reuse.check)
    assert result.status == CheckStatus.PASSED, result.reason
    assert result.details["photos"] == 4
    assert result.details["photos_on_record"] == 8
    assert result.details["matches"] == []


def test_a_copy_of_an_earlier_photo_is_a_hard_fail(db, tools, clock, make):
    earlier = proof_set(clock.now, seed=1)
    make(earlier)
    clock.advance(minutes=30)
    later = proof_set(clock.now, seed=2)
    later[0] = Capture("photo", near_copy(earlier[1].data), later[0].captured_at)
    result = run(db, make(later), tools, reuse.check)

    assert result.status == CheckStatus.FAILED
    assert mentions(
        result,
        "photo 1 is the same picture as photo 2 from attempt 1 of this milestone, received on "
        "10 March 2027 (pHash",
    )
    (match,) = result.details["matches"]
    assert match["item"] == "photo 1" and match["clear"] is True
    assert match["same_bundle"] is False and match["attempt"] == 1


def test_a_photo_that_only_looks_close_is_advisory(db, tools, clock, make):
    earlier = proof_set(clock.now, seed=3)
    earlier[0] = Capture("photo", photo(8), earlier[0].captured_at)
    make(earlier)
    clock.advance(minutes=30)
    later = proof_set(clock.now, seed=4)
    later[2] = Capture("photo", reframed(8), later[2].captured_at)
    result = run(db, make(later), tools, reuse.check)

    assert result.status == CheckStatus.ADVISORY
    assert mentions(result, "photo 3 looks very like photo 1 from attempt 1 of this milestone")
    assert mentions(result, "compare them by eye")
    assert result.details["matches"][0]["clear"] is False


def test_the_same_photo_twice_in_one_bundle_is_reported_once_on_the_later(db, tools, clock, make):
    captures = proof_set(clock.now, seed=5)
    captures[2] = Capture("photo", near_copy(captures[0].data), captures[2].captured_at)
    result = run(db, make(captures), tools, reuse.check)

    assert result.status == CheckStatus.FAILED
    assert mentions(result, "photo 3 is the same picture as photo 1 of this bundle")
    assert [match["item"] for match in result.details["matches"]] == ["photo 3"]
    assert result.details["matches"][0]["same_bundle"] is True


def test_photos_from_abandoned_sessions_still_count(
    client, db, tools, clock, make, project, field_worker, phone
):
    abandoned = start(client, field_worker, project.id, phone).json()
    first = Capture("photo", photo(61), clock.now)
    assert upload(client, field_worker, abandoned["id"], first).status_code == 201
    clock.advance(minutes=80)  # the session is never submitted and runs out

    captures = proof_set(clock.now, seed=6)
    captures[3] = Capture("photo", near_copy(first.data), captures[3].captured_at)
    result = run(db, make(captures), tools, reuse.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(
        result,
        "photo 4 is the same picture as a photo from attempt 1 of this "
        "milestone, received on 10 March 2027, in a session never submitted",
    )


def test_photos_from_other_projects_count_and_are_named(db, tools, clock, make, project):
    """A photo another charity already used for its own project."""
    admin = db.scalars(select(User)).first()
    other = Project(charity_id=project.charity_id, created_by=admin.id)
    db.add(other)
    db.flush()
    used = photo(71)
    session = CaptureSession(
        project_id=other.id,
        milestone_index=2,
        attempt=1,
        created_by=admin.id,
        device_address=_any_device(db),
        challenge_code="ABCDEF",
        issued_at=clock.now - timedelta(days=40),
        expires_at=clock.now - timedelta(days=40) + timedelta(minutes=15),
        upload_until=clock.now - timedelta(days=40) + timedelta(minutes=75),
        status="submitted",
        submitted_at=clock.now - timedelta(days=40),
    )
    db.add(session)
    db.flush()
    item = EvidenceItem(
        session_id=session.id,
        position=0,
        kind="photo",
        sha256=bytes(32),
        size_bytes=len(used),
        content_type="image/jpeg",
        storage_key="evidence/other/0",
        captured_at=session.issued_at,
        latitude=40.0,
        longitude=49.0,
        accuracy_m=5.0,
        received_at=session.issued_at,
    )
    db.add(item)
    db.flush()
    found = hashes(used)
    db.add(PhotoHash(item_id=item.id, phash=found.phash, dhash=found.dhash))
    db.commit()

    captures = proof_set(clock.now, seed=7)
    captures[1] = Capture("photo", near_copy(used), captures[1].captured_at)
    result = run(db, make(captures), tools, reuse.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(
        result,
        f"photo 2 is the same picture as photo 1 from milestone 2 of project {other.id}, "
        "received on 29 January 2027",
    )


def _any_device(db) -> str:
    return db.scalars(select(Device.address)).first()


@pytest.mark.parametrize("bits", [0, 1, 64])
def test_hamming_counts_differing_bits(bits):
    a = bytes(8)
    b = ((1 << bits) - 1).to_bytes(8, "big")
    assert hamming(a, b) == bits


def test_the_original_is_not_failed_for_a_copy_stored_after_it(db, tools, clock, make):
    """The worker may check bundle A after bundle B arrived with a copy of A's photo: the
    copy is B's reuse, not A's."""
    first = proof_set(clock.now, seed=1)
    original = make(first)
    clock.advance(minutes=30)
    later = proof_set(clock.now, seed=2)
    later[0] = Capture("photo", near_copy(first[0].data), later[0].captured_at)
    copied = make(later)

    first = run(db, original, tools, reuse.check)
    assert first.status == CheckStatus.ADVISORY  # named, not blamed
    assert mentions(first, "stored after it: that bundle has to explain it")
    assert run(db, copied, tools, reuse.check).status == CheckStatus.FAILED


def test_close_photos_cannot_crowd_out_a_clear_match(db, tools, clock, make):
    """Ten near-copies earlier in the same bundle used to fill the ten matches kept for a
    photo; clear matches now come first."""
    earlier = proof_set(clock.now, seed=1)
    make(earlier)
    clock.advance(minutes=30)
    later = proof_set(clock.now, seed=2, photos=12)
    picture = Image.open(io.BytesIO(earlier[0].data)).convert("RGB")
    decoys = picture.resize((picture.width - 40, picture.height - 30))
    for n in range(11):
        later[n] = Capture("photo", jpeg(decoys, quality=55 + n), later[n].captured_at)
    later[11] = Capture("photo", near_copy(earlier[0].data), later[11].captured_at)
    result = run(db, make(later), tools, reuse.check)
    assert result.status == CheckStatus.FAILED
    assert any(
        match["item"] == "photo 12" and match["clear"] and not match["same_bundle"]
        for match in result.details["matches"]
    )


def test_later_photos_of_the_same_bundle_cannot_hide_an_earlier_match(db, tools, clock, make):
    """Ten close copies inside one bundle used to fill the ten matches kept for a photo, so the
    clear match from another project never showed."""
    earlier = proof_set(clock.now, seed=1)
    make(earlier)
    clock.advance(minutes=30)
    later = proof_set(clock.now, seed=2, photos=12)
    reused = near_copy(earlier[0].data)
    later[0] = Capture("photo", reused, later[0].captured_at)
    picture = Image.open(io.BytesIO(reused)).convert("RGB")
    for n in range(1, 12):  # the same picture again, each saved a little differently
        later[n] = Capture("photo", jpeg(picture, quality=60 + n), later[n].captured_at)
    result = run(db, make(later), tools, reuse.check)

    assert result.status == CheckStatus.FAILED
    assert any(
        match["item"] == "photo 1" and match["clear"] and not match["same_bundle"]
        for match in result.details["matches"]
    )


def test_a_photo_with_no_upload_row_fails_instead_of_crashing(db, tools, clock, make):
    bundle = make(proof_set(clock.now))
    # Only with database access and the triggers off: a file in a manifest cannot be deleted.
    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(delete(EvidenceItem).where(EvidenceItem.position == 1))
    db.commit()
    result = run(db, bundle, tools, reuse.check)
    assert result.status == CheckStatus.FAILED
    assert mentions(result, "photo 2 is in the manifest but no upload is recorded for it")
    assert result.details["not_compared"] == ["photo 2"]
