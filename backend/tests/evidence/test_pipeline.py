"""The evidence worker: checks, then a redacted public copy built in private storage, then, once
the charity has signed and confirmed its photos, that copy on IPFS. A bundle that keeps
failing waits its turn and a person hears of it; it never holds up the others."""

from __future__ import annotations

import dataclasses
import io
import json
import uuid
from datetime import timedelta

import numpy as np
from PIL import Image
from sqlalchemy import select, update

from veritas.core.hashing import sha256, to_hex
from veritas.db.models.chain import Alert
from veritas.db.models.evidence import CheckReport, EvidenceBundle, EvidenceCheck, EvidenceItem
from veritas.evidence.ipfs import FakeIpfs, IpfsError
from veritas.evidence.pipeline import ALERT_AFTER, EvidencePipeline
from veritas.evidence.publish import (
    NO_DETECTOR,
    NOT_INTACT,
    NOT_REDACTABLE,
    UNCONFIRMED,
    WITHHELD,
    finalize_public_copy,
)
from veritas.evidence.redaction import PUBLIC_MAX_BYTES, Box
from veritas.services.cid import raw_cid

from .kit import FAR_AWAY, FixedBoxes, photo, proof_set


def bundle_row(db, bundle: dict) -> EvidenceBundle:
    db.expire_all()
    return db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))


def sign(db, bundle: dict, photos) -> EvidenceBundle:
    """What the anchor route does to the bundle, without the chain: the public copy becomes
    final with the confirmed photos, and the charity's signature is stored."""
    row = bundle_row(db, bundle)
    finalize_public_copy(db, row, photos)
    row.charity_signature = bytes(65)
    row.signed_at = row.created_at
    db.commit()
    return row


def pipeline_with(sessions, app, settings, **options) -> EvidencePipeline:
    return EvidencePipeline(
        sessions,
        storage=app.state.storage,
        settings=settings,
        ipfs=options.get("ipfs", FakeIpfs()),
        detector=options.get("detector", FixedBoxes()),
    )


def test_a_bundle_is_checked_and_its_public_copy_prepared_in_private(
    db, app, clock, make, pipeline, phone
):
    bundle = make(proof_set(clock.now))
    assert pipeline.run_once() == 2
    assert pipeline.run_once() == 0

    row = bundle_row(db, bundle)
    assert row.status == "published" and row.pinned_at is None
    report = db.scalars(select(CheckReport)).one()
    assert report.passed is True
    assert len(db.scalars(select(EvidenceCheck)).all()) == 11
    assert pipeline.ipfs.files == {}  # nothing is public before the charity signs

    assert row.public_cid == raw_cid(row.public_manifest)
    public = json.loads(row.public_manifest)
    assert public["format"] == "veritas.evidence.public/1"
    assert public["bundle_hash"] == bundle["bundle_hash"]
    assert public["report"] == {
        "sha256": to_hex(report.sha256),
        "cid": raw_cid(report.canonical_bytes),
        "passed": True,
    }
    assert [check["status"] for check in public["checks"]] == [
        "passed",
        "passed",
        "passed",
        "not_run",
        "passed",
        "not_run",
        "not_run",
        "not_run",
        "not_run",
        "not_run",
        "passed",
    ]
    assert public["captured"] == {"first": "2027-03-10T06:01:00Z", "last": "2027-03-10T06:07:00Z"}
    assert public["location"] == {"latitude": 40.79, "longitude": 48.15, "rounded_to_degrees": 0.01}
    assert public["withheld"] == [
        {"kind": "fiscal_receipt", "count": 1, "reason": WITHHELD["fiscal_receipt"]},
        {"kind": "invoice", "count": 1, "reason": WITHHELD["invoice"]},
    ]

    assert [entry["name"] for entry in public["photos"]] == [f"photo {n}" for n in range(1, 5)]
    items = db.scalars(
        select(EvidenceItem).where(EvidenceItem.kind == "photo").order_by(EvidenceItem.position)
    ).all()
    for entry, item in zip(public["photos"], items, strict=True):
        copy = app.state.storage.get(item.redacted_key)
        assert len(copy) <= PUBLIC_MAX_BYTES and entry["cid"] == raw_cid(copy)
        assert item.redacted_cid == entry["cid"] and item.blurred_regions == 0
        assert item.redacted_key.endswith(f"/public/{sha256(copy).hex()}.jpg")
        assert not Image.open(io.BytesIO(copy)).getexif()

    # Nothing about the phone or the exact positions leaves private storage.
    for document in (row.public_manifest, report.canonical_bytes):
        text = document.decode()
        assert phone.address.lower() not in text.lower()
        assert "40.7905" not in text and "48.151" not in text
        assert bundle["items"][0]["sha256"][2:] not in text


def test_only_the_photos_the_signer_confirms_go_to_ipfs_after_signing(db, clock, make, pipeline):
    bundle = make(proof_set(clock.now))
    pipeline.run_once()
    row = sign(db, bundle, [1, 3])
    public = json.loads(row.public_manifest)
    assert [entry["name"] for entry in public["photos"]] == ["photo 1", "photo 3"]
    assert {"kind": "photo", "count": 2, "reason": UNCONFIRMED} in public["withheld"]

    assert pipeline.run_once() == 1  # pinned
    row = bundle_row(db, bundle)
    assert row.pinned_at is not None
    ipfs = pipeline.ipfs
    assert ipfs.cat(row.public_cid) == row.public_manifest
    report = db.scalars(select(CheckReport)).one()
    assert ipfs.cat(public["report"]["cid"]) == report.canonical_bytes
    unconfirmed = db.scalars(
        select(EvidenceItem.redacted_cid).where(EvidenceItem.position.in_((1, 3)))
    ).all()
    assert len(ipfs.files) == 4  # two photos, the report, the manifest
    assert not any(cid in ipfs.files for cid in unconfirmed)
    assert pipeline.run_once() == 0


def test_faces_the_detector_finds_are_blurred_in_the_copy(sessions, app, settings, db, clock, make):
    face = Box(x=300, y=200, width=200, height=200, label="face")
    pipeline = pipeline_with(sessions, app, settings, detector=FixedBoxes((face,)))
    make(proof_set(clock.now))
    pipeline.run_once()
    public = json.loads(db.scalars(select(EvidenceBundle.public_manifest)).one())
    assert [entry["blurred_regions"] for entry in public["photos"]] == [1, 1, 1, 1]
    first = db.scalars(select(EvidenceItem).where(EvidenceItem.position == 0)).one()
    copy = np.asarray(Image.open(io.BytesIO(app.state.storage.get(first.redacted_key))))
    region = copy[220:380, 320:480].astype(float)
    assert np.abs(np.diff(region, axis=1)).mean() < 2  # smooth: no edges left to recognise


def test_without_a_detector_photos_stay_private(sessions, app, settings, db, clock, make):
    pipeline = pipeline_with(sessions, app, settings, detector=None)
    make(proof_set(clock.now))
    pipeline.run_once()

    public = json.loads(db.scalars(select(EvidenceBundle.public_manifest)).one())
    assert public["photos"] == []
    assert {"kind": "photo", "count": 4, "reason": NO_DETECTOR} in public["withheld"]
    alert = db.scalars(select(Alert)).one()
    assert alert.kind == "redaction_unavailable"
    assert db.scalars(select(EvidenceItem.redacted_cid)).all() == [None] * 6


class Crashes:
    """A detector that cannot read the photo, as OpenCV's resize did on a 4000 x 1 picture."""

    name = "crashes"
    covers = frozenset({"faces", "plates"})

    def detect(self, image):
        raise RuntimeError("(-215:Assertion failed) !dsize.empty() in function 'cv::resize'")


def test_a_photo_the_detector_cannot_read_stays_private(sessions, app, settings, db, clock, make):
    pipeline = pipeline_with(sessions, app, settings, detector=Crashes())
    bundle = make(proof_set(clock.now))
    assert pipeline.run_once() == 2
    row = bundle_row(db, bundle)
    assert row.status == "published"
    public = json.loads(row.public_manifest)
    assert public["photos"] == []
    assert {"kind": "photo", "count": 4, "reason": NOT_REDACTABLE} in public["withheld"]


def test_a_changed_original_is_checked_as_failed_and_never_published(
    db, app, clock, make, pipeline
):
    bundle = make(proof_set(clock.now))
    second = bundle["items"][1]
    app.state.storage.put(f"evidence/{bundle['session_id']}/{second['sha256'][2:]}", b"edited")
    pipeline.run_once()

    row = bundle_row(db, bundle)
    assert row.status == "published"
    assert db.scalars(select(CheckReport.passed)).one() is False
    public = json.loads(row.public_manifest)
    assert [entry["name"] for entry in public["photos"]] == ["photo 1", "photo 3", "photo 4"]
    assert {"kind": "photo", "count": 1, "reason": NOT_INTACT} in public["withheld"]
    assert public["report"]["passed"] is False
    assert public["checks"][0] == {
        "number": 1,
        "name": "files_and_signatures",
        "kind": "hard",
        "status": "failed",
    }


def test_the_rough_location_only_uses_captures_placed_on_the_site(db, clock, make, pipeline):
    """A photo taken 150 km away fails check 2; it must not drag the published point off
    the site, nor say where it was taken."""
    captures = proof_set(clock.now)
    captures[0] = dataclasses.replace(captures[0], at=FAR_AWAY)
    bundle = make(captures)
    pipeline.run_once()
    public = json.loads(bundle_row(db, bundle).public_manifest)
    assert public["checks"][1]["status"] == "failed"
    assert public["location"] == {"latitude": 40.79, "longitude": 48.15, "rounded_to_degrees": 0.01}


class Unreachable(FakeIpfs):
    def add(self, data: bytes, *, name: str = "file") -> str:
        raise IpfsError("cannot reach the IPFS node at http://127.0.0.1:5001: refused")


def test_an_unreachable_ipfs_node_leaves_the_signed_copy_for_later(
    sessions, app, settings, db, clock, make
):
    bundle = make(proof_set(clock.now))
    down = pipeline_with(sessions, app, settings, ipfs=Unreachable())
    assert down.run_once() == 2  # checked and prepared: neither needs IPFS
    sign(db, bundle, [1, 2, 3, 4])
    assert down.run_once() == 0
    row = bundle_row(db, bundle)
    assert row.pinned_at is None and row.tries == 1 and "IpfsError" in row.last_error
    assert down.run_once() == 0  # waits out its pause

    up = pipeline_with(sessions, app, settings)
    db.execute(update(EvidenceBundle).values(retry_at=None))
    db.commit()
    assert up.run_once() == 1
    row = bundle_row(db, bundle)
    assert row.pinned_at is not None and row.tries == 0 and row.last_error is None
    assert len(db.scalars(select(CheckReport)).all()) == 1  # the checks did not run twice


class FailsFor(EvidencePipeline):
    """A worker whose checks always crash on one bundle, as a corrupt row would make them."""

    poisoned: uuid.UUID

    def check(self, bundle_id):
        if bundle_id == self.poisoned:
            raise OverflowError("date value out of range")
        return super().check(bundle_id)


def test_a_bundle_that_keeps_failing_waits_and_a_person_hears_of_it(
    sessions, app, settings, db, clock, make
):
    pipeline = FailsFor(
        sessions, storage=app.state.storage, settings=settings, ipfs=FakeIpfs(), detector=None
    )
    poisoned = make(proof_set(clock.now))
    pipeline.poisoned = uuid.UUID(poisoned["id"])
    clock.advance(minutes=90)
    healthy = make(proof_set(clock.now, seed=2))

    assert pipeline.run_once() == 2  # the healthy one is checked and prepared all the same
    assert bundle_row(db, healthy).status == "published"
    row = bundle_row(db, poisoned)
    assert row.status == "draft" and row.tries == 1 and "OverflowError" in row.last_error
    first_pause = row.retry_at - row.updated_at
    assert timedelta(seconds=20) < first_pause < timedelta(minutes=1)
    assert pipeline.run_once() == 0  # not retried before its pause is over

    for _ in range(ALERT_AFTER - 1):
        db.execute(update(EvidenceBundle).values(retry_at=None))
        db.commit()
        pipeline.run_once()
    row = bundle_row(db, poisoned)
    assert row.tries == ALERT_AFTER
    assert row.retry_at - row.updated_at > first_pause * 8  # it backs off
    assert db.scalars(select(Alert.kind).where(Alert.kind == "evidence_stuck")).all() == [
        "evidence_stuck"
    ]


def test_the_pause_stops_growing_at_six_hours_however_often_a_step_fails(
    sessions, app, settings, db, clock, make
):
    pipeline = FailsFor(
        sessions, storage=app.state.storage, settings=settings, ipfs=FakeIpfs(), detector=None
    )
    poisoned = make(proof_set(clock.now))
    pipeline.poisoned = uuid.UUID(poisoned["id"])
    db.execute(update(EvidenceBundle).values(tries=60))
    db.commit()
    pipeline.run_once()
    row = bundle_row(db, poisoned)
    assert row.tries == 61  # recorded: no overflow at a large count
    assert timedelta(hours=5) < row.retry_at - row.updated_at <= timedelta(hours=6, minutes=1)


def test_a_stored_copy_that_is_not_the_signed_one_is_never_added(db, app, clock, make, pipeline):
    """Every file is checked against the CID the signed copy names before the first one goes
    out, and the problem is that bundle's own: other bundles still get pinned."""
    bundle = make(proof_set(clock.now))
    pipeline.run_once()
    sign(db, bundle, [1, 2, 3, 4])
    first = db.scalars(select(EvidenceItem).where(EvidenceItem.position == 0)).one()
    app.state.storage.put(first.redacted_key, photo(99))  # a mix-up in storage
    assert pipeline.run_once() == 0
    assert pipeline.ipfs.files == {}
    row = bundle_row(db, bundle)
    assert row.pinned_at is None and "PublicCopyError" in row.last_error
