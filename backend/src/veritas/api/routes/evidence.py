"""Evidence: capture sessions, uploads, the signed manifest, check results and anchoring.

A field worker starts a capture session for a milestone and gets a one-time challenge code,
the site's geofence and the proof checklist. The app uploads each file it captured, then the
manifest signed by the phone's key. The evidence worker checks, redacts and publishes the
bundle; a charity admin's key then signs it and the relayer anchors it. The charity and the
project's officer see everything; anyone can see what was anchored.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Path, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.api.deps import (
    ChainDep,
    CurrentUser,
    DbSession,
    SettingsDep,
    StorageDep,
    require_charity_member,
)
from veritas.api.schemas import Input, Signature, signature_bytes
from veritas.chain.leaves import MAX_MILESTONES
from veritas.core.hashing import sha256, to_hex
from veritas.db.models import Charity, MemberRole, Project, User
from veritas.db.models.chain import ChainOutbox
from veritas.db.models.evidence import (
    EVIDENCE_TYPES,
    BundleStatus,
    CaptureSession,
    CheckReport,
    EvidenceBundle,
    EvidenceCheck,
    EvidenceItem,
    PhotoHash,
)
from veritas.db.session import db_now
from veritas.evidence import anchoring, capture, intake
from veritas.evidence.access import require_reviewer
from veritas.evidence.checks import SPECS
from veritas.evidence.manifest import MAX_MANIFEST_BYTES, read_manifest
from veritas.evidence.wording import labels
from veritas.passport.models import Address, ProofKind
from veritas.services.cid import raw_cid
from veritas.services.errors import BadRequest, InternalError, NotFound
from veritas.settings import Settings

router = APIRouter(tags=["evidence"])

Index = Annotated[int, Path(ge=0, lt=MAX_MILESTONES, description="The milestone's index.")]


def evidence_clock(db: DbSession) -> datetime:
    """The time the evidence rules use: the database clock, as everywhere else. It is a
    dependency of its own so tests can set a date inside a milestone's window."""
    return db_now(db)


Now = Annotated[datetime, Depends(evidence_clock)]


# ---------------------------------------------------------------- shapes


class ProofOut(BaseModel):
    kind: str
    description: str
    min_count: int


class ItemOut(BaseModel):
    id: uuid.UUID
    position: int | None = Field(description="Where the manifest lists it, once submitted.")
    label: str | None = Field(description='"photo 2", once the manifest is in.')
    kind: str
    sha256: str
    size_bytes: int
    content_type: str
    captured_at: datetime
    latitude: float | None
    longitude: float | None
    accuracy_m: float | None
    mock_location: bool
    received_at: datetime
    phash: str | None
    dhash: str | None
    redacted_cid: str | None
    blurred_regions: int | None


class CaptureSessionIn(Input):
    device_address: Address = Field(description="The registered key that will sign the manifest.")


class CaptureSessionOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    milestone: int
    attempt: int
    status: str
    challenge_code: str = Field(description="Show it in at least one photo.")
    issued_at: datetime
    expires_at: datetime = Field(description="Everything must be captured before this.")
    upload_until: datetime = Field(description="Files and the manifest are taken until this.")
    device_address: str
    window_opens_at: datetime
    window_closes_at: datetime
    geofence: list[dict[str, Any]] = Field(description="The site, as GeoJSON polygons.")
    max_accuracy_m: float = Field(description="A GPS fix less precise than this is not enough.")
    checklist: list[ProofOut]
    accepted_types: dict[str, list[str]]
    max_file_bytes: int
    items: list[ItemOut]
    bundle_id: uuid.UUID | None


class ManifestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: str = Field(
        max_length=MAX_MANIFEST_BYTES,
        description="The canonical JSON manifest (RFC 8785) as text, exactly as signed.",
    )
    signature: Signature = Field(
        description="personal_sign by the device over 'Veritas evidence manifest\\n' and the "
        "manifest's SHA-256 as 0x hex."
    )
    attestation: str | None = Field(
        default=None,
        max_length=20_000,
        pattern=r"^[\x21-\x7e]+$",
        description="App Attest or Play Integrity token: printable ASCII, as base64 or JWS.",
    )

    @field_validator("manifest")
    @classmethod
    def _utf8(cls, value: str) -> str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("the manifest must be UTF-8 text") from None
        return value


class CheckOut(BaseModel):
    number: int
    name: str
    title: str
    kind: str
    status: str
    reason: str | None
    details: dict[str, Any]


class ReportOut(BaseModel):
    sha256: str
    cid: str
    passed: bool
    url: str = Field(description="The report's bytes, exactly as hashed.")


class AnchoringOut(BaseModel):
    signed_at: datetime
    submit_evidence: str = Field(description="The outbox status of submitEvidence.")
    record_checks: str = Field(description="The outbox status of recordChecks.")


class CodeOut(BaseModel):
    """The capture session's challenge code, which a photo must show (check 4). Until Phase 7
    reads it by machine, the officer compares it with the photos by hand."""

    challenge_code: str
    issued_at: datetime
    expires_at: datetime


class ProcessingOut(BaseModel):
    failures: int
    last_error: str | None
    next_try_at: datetime | None


class BundleOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    project_id: uuid.UUID
    milestone: int
    attempt: int
    status: str
    void_reason: str | None = Field(description="Why the chain refused a signed bundle.")
    bundle_hash: str
    device_address: str
    device_signature: str = Field(description="The phone's EIP-191 signature of the bundle hash.")
    attestation: str | None = Field(description="The app attestation token, as sent.")
    manifest_url: str = Field(description="The signed manifest, byte for byte as hashed.")
    code: CodeOut
    created_at: datetime
    items: list[ItemOut]
    checks: list[CheckOut]
    report: ReportOut | None
    public_cid: str | None
    pinned_at: datetime | None = Field(description="When the public copy went to IPFS.")
    processing: ProcessingOut | None = Field(
        description="Set while the evidence worker keeps failing on this bundle."
    )
    anchoring: AnchoringOut | None
    anchored_at: datetime | None


class BundleSummary(BaseModel):
    id: uuid.UUID
    attempt: int
    status: str
    bundle_hash: str
    passed: bool | None
    public_cid: str | None
    signed: bool
    created_at: datetime
    anchored_at: datetime | None


class AnchorIn(Input):
    charity_signature: str = Field(
        pattern=r"^0x[0-9a-fA-F]{130}$",
        description="The charity key's EIP-712 signature over the Evidence message.",
    )
    publish_photos: list[Annotated[int, Field(ge=1)]] = Field(
        default_factory=list,
        max_length=100,
        description="The photos (photo 1, photo 2, ...) whose redacted copies the signer "
        "looked at (GET /v1/evidence/{id}/items/{item_id}/public) and confirms show no face "
        "or number plate. Only these go public; the others stay private.",
    )


class PublicCheck(BaseModel):
    number: int
    name: str
    title: str
    kind: str
    status: str
    reason: str | None


class PublicEvidence(BaseModel):
    attempt: int
    bundle_hash: str
    public_cid: str = Field(description="The public copy on IPFS; anchored on-chain.")
    report_sha256: str = Field(description="Anchored on-chain with the pass flag.")
    report_cid: str
    passed: bool
    checks: list[PublicCheck]
    anchored_at: datetime


# ---------------------------------------------------------------- helpers


def _project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFound("not_found", "There is no project with this id.")
    return project


def _bundle(db: Session, bundle_id: uuid.UUID, *, lock: bool = False) -> EvidenceBundle:
    bundle = db.get(EvidenceBundle, bundle_id, with_for_update=lock)
    if bundle is None:
        raise NotFound("not_found", "There is no evidence bundle with this id.")
    return bundle


def _items(
    db: Session, session_id: uuid.UUID, manifest_bytes: bytes | None = None
) -> list[ItemOut]:
    """The session's files. With the signed manifest, each listed file is named as the manifest
    names it (photo 1, photo 2, ...), the numbers the signer confirms photos by."""
    rows = db.execute(
        select(EvidenceItem, PhotoHash)
        .outerjoin(PhotoHash, PhotoHash.item_id == EvidenceItem.id)
        .where(EvidenceItem.session_id == session_id)
        .order_by(EvidenceItem.position.nulls_last(), EvidenceItem.received_at, EvidenceItem.id)
    ).all()
    listed = [item for item, _ in rows if item.position is not None]
    if manifest_bytes is not None:
        named = labels(entry.kind for entry in read_manifest(manifest_bytes).items)
        names = {item.id: named[item.position] for item in listed if item.position < len(named)}
    else:
        names = dict(
            zip((item.id for item in listed), labels(item.kind for item in listed), strict=True)
        )
    return [
        ItemOut(
            id=item.id,
            position=item.position,
            label=names.get(item.id),
            kind=item.kind,
            sha256=to_hex(item.sha256),
            size_bytes=item.size_bytes,
            content_type=item.content_type,
            captured_at=item.captured_at,
            latitude=item.latitude,
            longitude=item.longitude,
            accuracy_m=item.accuracy_m,
            mock_location=item.mock_location,
            received_at=item.received_at,
            phash=None if hashes is None else hashes.phash.hex(),
            dhash=None if hashes is None else hashes.dhash.hex(),
            redacted_cid=item.redacted_cid,
            blurred_regions=item.blurred_regions,
        )
        for item, hashes in rows
    ]


def _session_out(
    db: Session, capture_session: CaptureSession, settings: Settings, now: datetime
) -> CaptureSessionOut:
    project = db.get_one(Project, capture_session.project_id)
    milestone = capture.find_milestone(db, project, capture_session.milestone_index)
    _, passport = capture.published_passport(db, project)
    bundle_id = db.scalars(
        select(EvidenceBundle.id).where(EvidenceBundle.session_id == capture_session.id)
    ).first()
    return CaptureSessionOut(
        id=capture_session.id,
        project_id=project.id,
        milestone=capture_session.milestone_index,
        attempt=capture_session.attempt,
        status=capture.effective_status(capture_session, now),
        challenge_code=capture_session.challenge_code,
        issued_at=capture_session.issued_at,
        expires_at=capture_session.expires_at,
        upload_until=capture_session.upload_until,
        device_address=capture_session.device_address,
        window_opens_at=milestone.opens_at,
        window_closes_at=milestone.closes_at,
        geofence=capture.geofence(db, milestone),
        max_accuracy_m=settings.evidence_max_accuracy_m,
        checklist=[
            ProofOut(kind=line.kind, description=line.description, min_count=line.min_count)
            for line in capture.checklist(passport, milestone.index)
        ],
        accepted_types={kind: list(types) for kind, types in intake.ACCEPTED_TYPES.items()},
        max_file_bytes=settings.max_upload_bytes,
        items=_items(db, capture_session.id),
        bundle_id=bundle_id,
    )


def _report(db: Session, bundle: EvidenceBundle) -> CheckReport | None:
    return db.scalars(select(CheckReport).where(CheckReport.bundle_id == bundle.id)).first()


def _bundle_out(db: Session, bundle: EvidenceBundle) -> BundleOut:
    report = _report(db, bundle)
    checks = db.scalars(
        select(EvidenceCheck)
        .where(EvidenceCheck.bundle_id == bundle.id)
        .order_by(EvidenceCheck.number)
    ).all()
    anchoring_out = None
    if bundle.signed_at is not None:
        outbox = {
            row.id: row.status
            for row in db.scalars(
                select(ChainOutbox).where(
                    ChainOutbox.id.in_([bundle.submit_outbox_id, bundle.checks_outbox_id])
                )
            )
        }
        anchoring_out = AnchoringOut(
            signed_at=bundle.signed_at,
            submit_evidence=outbox.get(bundle.submit_outbox_id or -1, "unknown"),
            record_checks=outbox.get(bundle.checks_outbox_id or -1, "unknown"),
        )
    capture_session = db.get_one(CaptureSession, bundle.session_id)
    return BundleOut(
        id=bundle.id,
        session_id=bundle.session_id,
        project_id=bundle.project_id,
        milestone=bundle.milestone_index,
        attempt=bundle.attempt,
        status=bundle.status,
        void_reason=bundle.void_reason,
        bundle_hash=to_hex(bundle.bundle_hash),
        device_address=bundle.device_address,
        device_signature="0x" + bundle.device_signature.hex(),
        attestation=bundle.attestation,
        manifest_url=f"/v1/evidence/{bundle.id}/manifest",
        code=CodeOut(
            challenge_code=capture_session.challenge_code,
            issued_at=capture_session.issued_at,
            expires_at=capture_session.expires_at,
        ),
        created_at=bundle.created_at,
        items=_items(db, bundle.session_id, bundle.manifest_bytes),
        checks=[
            CheckOut(
                number=check.number,
                name=check.name,
                title=SPECS[check.number].title,
                kind=check.kind,
                status=check.status,
                reason=check.reason,
                details=check.details,
            )
            for check in checks
        ],
        report=None
        if report is None
        else ReportOut(
            sha256=to_hex(report.sha256),
            cid=raw_cid(report.canonical_bytes),
            passed=report.passed,
            url=f"/v1/evidence/{bundle.id}/report",
        ),
        public_cid=bundle.public_cid,
        pinned_at=bundle.pinned_at,
        processing=ProcessingOut(
            failures=bundle.tries, last_error=bundle.last_error, next_try_at=bundle.retry_at
        )
        if bundle.tries
        else None,
        anchoring=anchoring_out,
        anchored_at=bundle.anchored_at,
    )


# ---------------------------------------------------------------- capture


@router.post("/v1/projects/{project_id}/milestones/{index}/capture-sessions", status_code=201)
def start_capture_session(
    project_id: uuid.UUID,
    index: Index,
    body: CaptureSessionIn,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    now: Now,
) -> CaptureSessionOut:
    """Start capturing evidence for a milestone: a one-time challenge code, the geofence and the
    proof checklist. Charity members only, with their own registered device key."""
    project = _project(db, project_id)
    require_charity_member(db, user, project.charity_id)
    milestone = capture.find_milestone(db, project, index)
    device = capture.capture_device(db, user, body.device_address)
    capture_session = capture.start_session(db, settings, project, milestone, user, device, now)
    return _session_out(db, capture_session, settings, now)


@router.get("/v1/capture-sessions/{session_id}")
def get_capture_session(
    session_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: SettingsDep, now: Now
) -> CaptureSessionOut:
    """A capture session and the files uploaded to it so far. Charity members only."""
    capture_session = db.get(CaptureSession, session_id)
    if capture_session is None:
        raise NotFound("not_found", "There is no capture session with this id.")
    project = db.get_one(Project, capture_session.project_id)
    require_charity_member(db, user, project.charity_id)
    return _session_out(db, capture_session, settings, now)


@router.post("/v1/capture-sessions/{session_id}/items", status_code=201)
def upload_item(
    session_id: uuid.UUID,
    kind: Annotated[ProofKind, Form()],
    sha256_hex: Annotated[
        str,
        Form(
            alias="sha256",
            pattern=r"^0x[0-9a-fA-F]{64}$",
            description="The SHA-256 the app computed, as 0x hex.",
        ),
    ],
    captured_at: Annotated[datetime, Form(description="When it was captured, with time zone.")],
    file: Annotated[UploadFile, File(description="The captured file, as the camera wrote it.")],
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    storage: StorageDep,
    now: Now,
    latitude: Annotated[float | None, Form(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Form(ge=-180, le=180)] = None,
    accuracy_m: Annotated[float | None, Form(gt=0, le=10_000)] = None,
    mock_location: Annotated[bool, Form(description="The phone said the fix was mocked.")] = False,
) -> ItemOut:
    """Upload one captured file with what the phone recorded about it. Refused at once when
    its SHA-256 is not what the app computed. Only the person who started the session."""
    capture_session = intake.open_session_for(db, session_id, user.id, now, lock=False)
    given = (latitude, longitude, accuracy_m)
    if any(value is not None for value in given) and None in given:
        raise BadRequest(
            "incomplete_location", "Send latitude, longitude and accuracy_m together, or none."
        )
    fix = (
        intake.Fix(latitude=latitude, longitude=longitude, accuracy_m=accuracy_m)
        if latitude is not None and longitude is not None and accuracy_m is not None
        else None
    )
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    upload = intake.Upload(
        kind=kind,
        declared_sha256=bytes.fromhex(sha256_hex[2:]),
        content_type=content_type,
        data=file.file.read(settings.max_upload_bytes + 1),
        captured_at=captured_at,
        fix=fix,
        mock_location=mock_location,
    )
    # The connection goes back to the pool while the file is checked and a photo decoded,
    # and the session row is locked only to record it.
    db.commit()
    prepared = intake.prepare(
        upload,
        capture_session,
        max_bytes=settings.max_upload_bytes,
        clock_skew=timedelta(seconds=settings.evidence_clock_skew_seconds),
        now=now,
    )
    capture_session = intake.open_session_for(db, session_id, user.id, now)
    item = intake.add_item(db, storage, capture_session, prepared, now=now)
    return next(row for row in _items(db, capture_session.id) if row.id == item.id)


@router.post("/v1/capture-sessions/{session_id}/manifest", status_code=201)
def submit_manifest(
    session_id: uuid.UUID, body: ManifestIn, user: CurrentUser, db: DbSession, now: Now
) -> BundleOut:
    """Submit the manifest the phone signed. It must list exactly the uploaded files; it
    becomes the bundle the checks run on. Only the person who started the session."""
    capture_session = intake.open_session_for(db, session_id, user.id, now)
    bundle = intake.submit_manifest(
        db,
        capture_session,
        data=body.manifest.encode("utf-8"),
        signature=signature_bytes(body.signature),
        attestation=body.attestation,
        now=now,
    )
    return _bundle_out(db, bundle)


# ---------------------------------------------------------------- bundles


@router.get("/v1/projects/{project_id}/milestones/{index}/bundles")
def list_bundles(
    project_id: uuid.UUID, index: Index, user: CurrentUser, db: DbSession
) -> list[BundleSummary]:
    """Every bundle submitted for a milestone, anchored or not, newest first. The charity's
    members and the project's officer only."""
    project = _project(db, project_id)
    require_reviewer(db, user, project)
    rows = db.execute(
        select(EvidenceBundle, CheckReport.passed)
        .outerjoin(CheckReport, CheckReport.bundle_id == EvidenceBundle.id)
        .where(EvidenceBundle.project_id == project.id, EvidenceBundle.milestone_index == index)
        .order_by(EvidenceBundle.created_at.desc(), EvidenceBundle.id)
    ).all()
    return [
        BundleSummary(
            id=bundle.id,
            attempt=bundle.attempt,
            status=bundle.status,
            bundle_hash=to_hex(bundle.bundle_hash),
            passed=report_passed,
            public_cid=bundle.public_cid,
            signed=bundle.charity_signature is not None,
            created_at=bundle.created_at,
            anchored_at=bundle.anchored_at,
        )
        for bundle, report_passed in rows
    ]


@router.get("/v1/evidence/{bundle_id}")
def get_bundle(bundle_id: uuid.UUID, user: CurrentUser, db: DbSession) -> BundleOut:
    """A bundle with its files, every check result and the report. The charity's members and
    the project's officer only."""
    bundle = _bundle(db, bundle_id)
    require_reviewer(db, user, db.get_one(Project, bundle.project_id))
    return _bundle_out(db, bundle)


@router.get(
    "/v1/evidence/{bundle_id}/report",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}, "description": "As hashed."}},
)
def get_report(bundle_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """The check report, byte for byte as hashed. The same bytes are public on IPFS once the
    bundle is published."""
    bundle = _bundle(db, bundle_id)
    require_reviewer(db, user, db.get_one(Project, bundle.project_id))
    report = _report(db, bundle)
    if report is None:
        if bundle.tries:
            raise NotFound(
                "not_checked",
                f"The checks on this bundle have failed {bundle.tries} times so far; Veritas "
                "is told after a few and the worker keeps trying.",
            )
        raise NotFound("not_checked", "The checks on this bundle have not run yet.")
    return Response(
        content=report.canonical_bytes,
        media_type="application/json",
        headers={
            "X-Report-SHA256": to_hex(report.sha256),
            "Cache-Control": "private, max-age=31536000, immutable",
        },
    )


@router.get(
    "/v1/evidence/{bundle_id}/manifest",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}, "description": "As signed."}},
)
def get_manifest(bundle_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """The manifest the phone signed, byte for byte. Its SHA-256 is the bundle hash on-chain,
    and it lists every original's SHA-256, so anyone it is shown to can check the originals and
    the phone's signature without trusting this database. The charity's members and the
    project's officer only."""
    bundle = _bundle(db, bundle_id)
    require_reviewer(db, user, db.get_one(Project, bundle.project_id))
    return Response(
        content=bundle.manifest_bytes,
        media_type="application/json",
        headers={
            "X-Bundle-Hash": to_hex(bundle.bundle_hash),
            "X-Device-Signature": "0x" + bundle.device_signature.hex(),
            "Cache-Control": "private, max-age=31536000, immutable",
        },
    )


@router.get(
    "/v1/evidence/{bundle_id}/items/{item_id}/public",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def get_public_copy(
    bundle_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> Response:
    """A photo's redacted copy, exactly as it would go to IPFS: what the signer looks at before
    confirming that it shows no face or number plate. Before the signature it is private, so
    only the charity's members and the project's officer see it here."""
    bundle = _bundle(db, bundle_id)
    require_reviewer(db, user, db.get_one(Project, bundle.project_id))
    item = db.get(EvidenceItem, item_id)
    if item is None or item.session_id != bundle.session_id or item.redacted_key is None:
        raise NotFound("not_found", "This bundle has no redacted copy of this file.")
    try:
        data = storage.get(item.redacted_key)
    except KeyError:
        raise InternalError("file_missing", "The redacted copy is missing.") from None
    if raw_cid(data) != item.redacted_cid:
        raise InternalError("file_damaged", "The stored copy is not the one its CID names.")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "X-Content-CID": item.redacted_cid or "",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/v1/evidence/{bundle_id}/items/{item_id}/original",
    response_class=Response,
    responses={200: {"content": {media: {} for media in EVIDENCE_TYPES}}},
)
def get_original(
    bundle_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> Response:
    """An original file as captured, from private storage, checked against the SHA-256 the
    signed manifest gives for it. The charity's members and the project's officer only."""
    bundle = _bundle(db, bundle_id)
    require_reviewer(db, user, db.get_one(Project, bundle.project_id))
    item = db.get(EvidenceItem, item_id)
    if item is None or item.session_id != bundle.session_id or item.position is None:
        raise NotFound("not_found", "This bundle has no file with this id.")
    signed = read_manifest(bundle.manifest_bytes).items[item.position].digest
    try:
        data = storage.get(item.storage_key)
    except KeyError:
        raise InternalError("file_missing", "The stored original is missing.") from None
    if sha256(data) != signed:
        raise InternalError(
            "file_damaged", "The stored original is not the file the signed manifest lists."
        )
    filename = quote(f"{item.kind}-{item.sha256.hex()[:12]}")
    return Response(
        content=data,
        media_type=item.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-SHA256": to_hex(item.sha256),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


# ---------------------------------------------------------------- anchoring


def _anchor_context(
    db: Session, bundle_id: uuid.UUID, user: User, *, lock: bool
) -> tuple[EvidenceBundle, Project, Charity]:
    bundle = _bundle(db, bundle_id, lock=lock)
    project = db.get_one(Project, bundle.project_id)
    charity = require_charity_member(db, user, project.charity_id, MemberRole.ADMIN)
    return bundle, project, charity


@router.get("/v1/evidence/{bundle_id}/evidence-message")
def get_evidence_message(
    bundle_id: uuid.UUID, user: CurrentUser, db: DbSession, chain: ChainDep, now: Now
) -> dict[str, Any]:
    """The EIP-712 Evidence message for the charity's key to sign. Charity admins only."""
    bundle, project, _ = _anchor_context(db, bundle_id, user, lock=False)
    milestone = capture.find_milestone(db, project, bundle.milestone_index)
    ready = anchoring.check_anchorable(db, chain, project, milestone, bundle, now)
    return anchoring.evidence_typed_data(ready, project, bundle)


@router.post("/v1/evidence/{bundle_id}/anchor")
def anchor(
    bundle_id: uuid.UUID,
    body: AnchorIn,
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
    now: Now,
) -> BundleOut:
    """Sign off the bundle with the charity's key and queue it for the chain: the evidence,
    then the check report. Charity admins only."""
    bundle, project, charity = _anchor_context(db, bundle_id, user, lock=True)
    milestone = capture.find_milestone(db, project, bundle.milestone_index)
    db.refresh(milestone, with_for_update=True)
    ready = anchoring.check_anchorable(db, chain, project, milestone, bundle, now)
    anchoring.anchor_bundle(
        db,
        ready,
        project,
        bundle,
        charity,
        user,
        signature_bytes(body.charity_signature),
        now,
        photos=body.publish_photos,
    )
    return _bundle_out(db, bundle)


# ---------------------------------------------------------------- public


@router.get("/v1/projects/{project_id}/milestones/{index}/evidence")
def public_evidence(project_id: uuid.UUID, index: Index, db: DbSession) -> list[PublicEvidence]:
    """What was anchored for a milestone, attempt by attempt: the public copy's CID, the
    report's hash and CID, and every check's result. Public."""
    _project(db, project_id)
    rows = db.execute(
        select(EvidenceBundle, CheckReport)
        .join(CheckReport, CheckReport.bundle_id == EvidenceBundle.id)
        .where(
            EvidenceBundle.project_id == project_id,
            EvidenceBundle.milestone_index == index,
            EvidenceBundle.status == BundleStatus.ANCHORED,
        )
        .order_by(EvidenceBundle.attempt)
    ).all()
    result = []
    for bundle, report in rows:
        checks = db.scalars(
            select(EvidenceCheck)
            .where(EvidenceCheck.bundle_id == bundle.id)
            .order_by(EvidenceCheck.number)
        )
        assert bundle.public_cid is not None and bundle.anchored_at is not None
        result.append(
            PublicEvidence(
                attempt=bundle.attempt,
                bundle_hash=to_hex(bundle.bundle_hash),
                public_cid=bundle.public_cid,
                report_sha256=to_hex(report.sha256),
                report_cid=raw_cid(report.canonical_bytes),
                passed=report.passed,
                checks=[
                    PublicCheck(
                        number=check.number,
                        name=check.name,
                        title=SPECS[check.number].title,
                        kind=check.kind,
                        status=check.status,
                        reason=check.reason,
                    )
                    for check in checks
                ],
                anchored_at=bundle.anchored_at,
            )
        )
    return result
