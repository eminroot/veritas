"""Taking evidence in: each captured file, then the signed manifest that freezes them into a
bundle.

A file is refused at once when it cannot be what it says: the SHA-256 the app computed must
be the SHA-256 of the bytes that arrived, the type must suit the kind of proof and the first
bytes must match the type, and a photo must decode. Accepted originals go to private storage
under a key made from their hash. Each photo's perceptual hashes are recorded immediately, so
a photo is never new again, even if its session is abandoned.

Whether the evidence is good (on site, on time, not reused, complete) is not decided here:
that is what the checks are for, and every failure they find is reported with a reason.
What is decided here is whether the manifest is the honest list of what was uploaded and is
signed by the session's phone; a manifest that is not is refused with what to fix.

A capture time that cannot be true is refused at upload: later than the server's clock (with
the allowed skew), or a day or more before the session started. Check 3 reports the times
that are merely wrong; these would only be noise, or, at the end of time, a crash.

A file is checked and decoded before the session row is locked (`prepare`), so a slow file
holds no lock and no database connection, and the session takes files only while its key is
registered and its maker is still in the charity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.core.hashing import sha256, to_hex
from veritas.db.models import CharityMember, Device, Project
from veritas.db.models.evidence import (
    BundleStatus,
    CaptureSession,
    CaptureStatus,
    EvidenceBundle,
    EvidenceItem,
    PhotoHash,
)
from veritas.evidence import photos
from veritas.evidence.manifest import (
    MAX_ITEMS,
    Manifest,
    ManifestError,
    ManifestItem,
    manifest_signer,
    read_manifest,
)
from veritas.evidence.photos import (
    DECODING,
    HASH_SIDE,
    PerceptualHashes,
    PhotoError,
    open_photo,
    perceptual_hashes,
)
from veritas.evidence.wording import baku_time, kind_name
from veritas.passport.errors import Problem
from veritas.passport.models import ProofKind
from veritas.services.errors import (
    BadRequest,
    Conflict,
    Forbidden,
    NotFound,
    PayloadTooLarge,
    Unavailable,
    Unprocessable,
    UnsupportedMediaType,
)
from veritas.storage import PrivateStorage

_DOCUMENT_TYPES = ("image/jpeg", "image/png", "application/pdf")
ACCEPTED_TYPES: dict[str, tuple[str, ...]] = {
    ProofKind.PHOTO: ("image/jpeg", "image/png"),
    ProofKind.VIDEO: ("video/mp4", "video/quicktime"),
    ProofKind.INVOICE: _DOCUMENT_TYPES,
    ProofKind.FISCAL_RECEIPT: _DOCUMENT_TYPES,
    ProofKind.DOCUMENT: _DOCUMENT_TYPES,
}
ON_SITE = (ProofKind.PHOTO, ProofKind.VIDEO)
"""Kinds captured at the work site. They need a GPS fix, and check 2 places them."""

_TYPE_NAMES = {
    "image/jpeg": "a JPEG image",
    "image/png": "a PNG image",
    "video/mp4": "an MP4 video",
    "video/quicktime": "a QuickTime video",
    "application/pdf": "a PDF",
}


@dataclass(frozen=True)
class Fix:
    latitude: float
    longitude: float
    accuracy_m: float


@dataclass(frozen=True)
class Upload:
    """One captured file and what the app says about it."""

    kind: ProofKind
    declared_sha256: bytes
    content_type: str
    data: bytes
    captured_at: datetime
    fix: Fix | None
    mock_location: bool


EARLIEST_CAPTURE = timedelta(days=1)
"""How long before its session a capture time may say it was taken, before it is refused."""


@dataclass(frozen=True)
class Prepared:
    """An upload that passed every check that needs no lock: its hash and, for a photo, its
    perceptual hashes."""

    upload: Upload
    digest: bytes
    hashes: PerceptualHashes | None


def original_key(session_id: object, digest: bytes) -> str:
    return f"evidence/{session_id}/{digest.hex()}"


def public_key(session_id: object, digest: bytes) -> str:
    return f"evidence/{session_id}/public/{digest.hex()}.jpg"


def open_session_for(
    session: Session, session_id: object, user_id: object, now: datetime, *, lock: bool = True
) -> CaptureSession:
    """The capture session, locked, if `user_id` started it, still belongs to its charity, its
    key is still registered, and it still takes files."""
    # Locked, it is read again: another request may have changed it since this one read it.
    capture = session.get(CaptureSession, session_id, with_for_update=lock, populate_existing=lock)
    if capture is None:
        raise NotFound("not_found", "There is no capture session with this id.")
    if capture.created_by != user_id:
        raise Forbidden(
            "not_your_session", "Only the person who started this capture session can add to it."
        )
    project = session.get_one(Project, capture.project_id)
    member = session.scalars(
        select(CharityMember.id).where(
            CharityMember.charity_id == project.charity_id, CharityMember.user_id == user_id
        )
    ).first()
    if member is None:
        raise Forbidden("not_a_member", "You are no longer a member of this project's charity.")
    device = session.scalars(select(Device).where(Device.address == capture.device_address)).first()
    if device is None or device.revoked_at is not None:
        raise Forbidden(
            "device_revoked",
            "This session's device key was revoked, so the session is closed; start a new one "
            "with a registered phone.",
        )
    if capture.status == CaptureStatus.SUBMITTED:
        raise Conflict(
            "session_submitted",
            "This session's manifest is already in; start a new session to capture more.",
        )
    if capture.status == CaptureStatus.EXPIRED or now > capture.upload_until:
        raise Conflict(
            "session_expired",
            f"This capture session ended at {baku_time(capture.upload_until)}; start a new one.",
        )
    return capture


def prepare(
    upload: Upload,
    capture: CaptureSession,
    *,
    max_bytes: int,
    clock_skew: timedelta,
    now: datetime,
) -> Prepared:
    """Check one uploaded file and, for a photo, decode it and hash it. Needs no lock."""
    _check_file(upload, max_bytes)
    _check_time(upload, capture, clock_skew, now)
    digest = sha256(upload.data)
    if digest != upload.declared_sha256:
        raise Unprocessable(
            "hash_mismatch",
            f"The file's SHA-256 is {to_hex(digest)}, not {to_hex(upload.declared_sha256)} as "
            "the app said; it was damaged on the way or changed. Upload it again.",
        )
    hashes = None
    if upload.kind == ProofKind.PHOTO:
        # A few at a time: each photo may take hundreds of megabytes. Waiting holds one of the
        # API's worker threads, so an upload that finds them all busy is sent away.
        if not DECODING.acquire(timeout=photos.DECODE_WAIT_SECONDS):
            raise Unavailable(
                "photos_busy",
                "The server is reading other photos right now; upload this one again in a minute.",
                headers={"Retry-After": "60"},
            )
        try:
            image = open_photo(upload.data, upload.content_type, max_side=HASH_SIDE)
            hashes = perceptual_hashes(image)
        except PhotoError as exc:
            raise Unprocessable("unreadable_photo", f"The photo cannot be used: {exc}.") from None
        finally:
            DECODING.release()
    return Prepared(upload=upload, digest=digest, hashes=hashes)


def _check_time(upload: Upload, capture: CaptureSession, skew: timedelta, now: datetime) -> None:
    if upload.captured_at.tzinfo is None:
        return  # _check_file has refused it
    if upload.captured_at > now + skew:
        raise Unprocessable(
            "capture_in_future",
            f"The file says it was captured at {baku_time(upload.captured_at)}, later than now "
            f"({baku_time(now)}): set the phone's clock and capture it again.",
        )
    if upload.captured_at < capture.issued_at - EARLIEST_CAPTURE:
        raise Unprocessable(
            "capture_too_early",
            f"The file says it was captured at {baku_time(upload.captured_at)}, long before "
            f"this session started at {baku_time(capture.issued_at)}; capture it in the "
            "session.",
        )


def add_item(
    session: Session,
    storage: PrivateStorage,
    capture: CaptureSession,
    prepared: Prepared,
    *,
    now: datetime,
) -> EvidenceItem:
    """Store a prepared file's original and record it in the session, which is locked."""
    upload, digest = prepared.upload, prepared.digest
    existing = session.scalars(
        select(EvidenceItem.id).where(
            EvidenceItem.session_id == capture.id, EvidenceItem.sha256 == digest
        )
    ).first()
    if existing is not None:
        raise Conflict(
            "item_exists",
            "This file is already uploaded in this session.",
            details=[{"item_id": str(existing)}],
        )
    count = session.scalar(
        select(func.count()).select_from(EvidenceItem).where(EvidenceItem.session_id == capture.id)
    )
    if (count or 0) >= MAX_ITEMS:
        raise Conflict("too_many_items", f"A capture session takes at most {MAX_ITEMS} files.")
    hashes = prepared.hashes

    # Stored before the row, under its own hash: if the transaction fails, the next upload of
    # the same file simply writes the same object again.
    key = original_key(capture.id, digest)
    storage.put(key, upload.data)
    item = EvidenceItem(
        session_id=capture.id,
        kind=upload.kind,
        sha256=digest,
        size_bytes=len(upload.data),
        content_type=upload.content_type,
        storage_key=key,
        captured_at=upload.captured_at,
        latitude=upload.fix.latitude if upload.fix else None,
        longitude=upload.fix.longitude if upload.fix else None,
        accuracy_m=upload.fix.accuracy_m if upload.fix else None,
        mock_location=upload.mock_location,
        received_at=now,
    )
    session.add(item)
    session.flush()
    if hashes is not None:
        session.add(PhotoHash(item_id=item.id, phash=hashes.phash, dhash=hashes.dhash))
        session.flush()
    return item


def _check_file(upload: Upload, max_bytes: int) -> None:
    accepted = ACCEPTED_TYPES[upload.kind]
    if upload.content_type not in accepted:
        names = " or ".join(_TYPE_NAMES[name] for name in accepted)
        raise UnsupportedMediaType(
            "unsupported_file", f"A {kind_name(upload.kind)} must be {names}."
        )
    if not upload.data:
        raise Unprocessable("empty_file", "The file is empty.")
    if len(upload.data) > max_bytes:
        raise PayloadTooLarge(
            "file_too_large", f"The file is larger than {max_bytes // (1024 * 1024)} MB."
        )
    if not _starts_like(upload.data, upload.content_type):
        raise UnsupportedMediaType(
            "unsupported_file",
            f"The file is not {_TYPE_NAMES[upload.content_type]}, as its type says.",
        )
    if upload.captured_at.tzinfo is None:
        raise BadRequest(
            "time_zone_required",
            "captured_at must say its time zone, like 2027-03-10T06:01:02Z.",
        )
    if upload.fix is None and upload.kind in ON_SITE:
        raise Unprocessable(
            "location_required",
            f"A {kind_name(upload.kind)} needs the phone's GPS fix: latitude, longitude and "
            "accuracy.",
        )
    if upload.fix is not None and not all(
        math.isfinite(value)
        for value in (upload.fix.latitude, upload.fix.longitude, upload.fix.accuracy_m)
    ):
        raise Unprocessable("bad_location", "The GPS fix must be finite numbers.")


def _starts_like(data: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "application/pdf":
        return data.startswith(b"%PDF-")
    # MP4 and QuickTime files start with a box whose type is "ftyp".
    return data[4:8] == b"ftyp"


def submit_manifest(
    session: Session,
    capture: CaptureSession,
    *,
    data: bytes,
    signature: bytes,
    attestation: str | None,
    now: datetime,
) -> EvidenceBundle:
    """Turn the session into a bundle, if the manifest lists exactly what was uploaded and the
    session's phone signed it. The session must come from `open_session_for`."""
    try:
        manifest = read_manifest(data)
    except ManifestError as exc:
        raise Unprocessable("manifest_invalid", exc.message, details=list(exc.problems)) from None
    items = session.scalars(
        select(EvidenceItem)
        .where(EvidenceItem.session_id == capture.id)
        .order_by(EvidenceItem.received_at, EvidenceItem.id)
    ).all()
    problems = _session_problems(capture, manifest) + _item_problems(manifest, items)
    if problems:
        raise Unprocessable(
            "manifest_mismatch",
            "The manifest does not match this capture session and its uploads.",
            details=problems,
        )

    bundle_hash = sha256(data)
    if manifest_signer(bundle_hash, signature) != capture.device_address:
        raise Forbidden(
            "bad_signature", "The manifest is not signed by this capture session's device key."
        )
    _check_device(session, capture)

    by_digest = {item.sha256: item for item in items}
    for position, listed in enumerate(manifest.items):
        by_digest[listed.digest].position = position
    capture.status = CaptureStatus.SUBMITTED
    capture.submitted_at = now
    bundle = EvidenceBundle(
        session_id=capture.id,
        project_id=capture.project_id,
        milestone_index=capture.milestone_index,
        attempt=capture.attempt,
        manifest_bytes=data,
        bundle_hash=bundle_hash,
        device_address=capture.device_address,
        device_signature=signature,
        attestation=attestation,
        status=BundleStatus.DRAFT,
        created_by=capture.created_by,
    )
    session.add(bundle)
    session.flush()
    return bundle


def _check_device(session: Session, capture: CaptureSession) -> None:
    """The signing key is still trusted, and its owner is still in the charity."""
    device = session.scalars(select(Device).where(Device.address == capture.device_address)).one()
    if device.revoked_at is not None:
        raise Forbidden("device_revoked", "The device key that signed this manifest was revoked.")
    project = session.get_one(Project, capture.project_id)
    member = session.scalars(
        select(CharityMember.id).where(
            CharityMember.charity_id == project.charity_id, CharityMember.user_id == device.user_id
        )
    ).first()
    if member is None:
        raise Forbidden(
            "not_a_member", "The device key belongs to someone who is no longer in the charity."
        )


def _session_problems(capture: CaptureSession, manifest: Manifest) -> list[Problem]:
    expected = {
        "session_id": (manifest.session_id, capture.id),
        "project_id": (manifest.project_id, capture.project_id),
        "milestone": (manifest.milestone, capture.milestone_index),
        "attempt": (manifest.attempt, capture.attempt),
        "challenge_code": (manifest.challenge_code, capture.challenge_code),
        "device": (manifest.device, capture.device_address),
    }
    return [
        Problem(path=path, message=f"must be {wanted}, as in the capture session")
        for path, (given, wanted) in expected.items()
        if given != wanted
    ]


def _item_problems(manifest: Manifest, items: list[EvidenceItem]) -> list[Problem]:
    uploads = {item.sha256: item for item in items}
    problems: list[Problem] = []
    listed: dict[bytes, int] = {}
    for position, entry in enumerate(manifest.items):
        path = f"items[{position}]"
        if entry.digest in listed:
            problems.append(
                Problem(
                    path=f"{path}.sha256",
                    message=f"lists the same file as items[{listed[entry.digest]}]",
                )
            )
            continue
        listed[entry.digest] = position
        upload = uploads.get(entry.digest)
        if upload is None:
            problems.append(
                Problem(path=f"{path}.sha256", message="no file with this SHA-256 was uploaded")
            )
            continue
        problems += [
            Problem(path=f"{path}.{field}", message=message)
            for field, message in _differences(entry, upload)
        ]
    for digest, upload in uploads.items():
        if digest not in listed:
            problems.append(
                Problem(
                    path="items",
                    message=f"the {kind_name(upload.kind)} {to_hex(digest)} was uploaded but is "
                    "not in the manifest",
                )
            )
    return problems


def _differences(entry: ManifestItem, upload: EvidenceItem) -> list[tuple[str, str]]:
    said = "but the upload said"
    found: list[tuple[str, str]] = []
    if entry.kind != upload.kind:
        found.append(("kind", f"is {entry.kind} {said} {upload.kind}"))
    if entry.size != upload.size_bytes:
        found.append(("size", f"is {entry.size} {said} {upload.size_bytes}"))
    if entry.content_type != upload.content_type:
        found.append(("content_type", f"is {entry.content_type} {said} {upload.content_type}"))
    if entry.captured != upload.captured_at:
        found.append(
            ("captured_at", f"is {entry.captured_at} {said} {upload.captured_at.isoformat()}")
        )
    location = entry.location
    if location is None:
        if upload.latitude is not None:
            found.append(("location", f"is null {said} there was a GPS fix"))
    elif (
        location.latitude,
        location.longitude,
        location.accuracy_m,
        location.mocked,
    ) != (upload.latitude, upload.longitude, upload.accuracy_m, upload.mock_location):
        found.append(("location", "differs from the GPS fix sent with the upload"))
    return found
