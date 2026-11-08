"""Helpers for the evidence tests: photos drawn with Pillow, files captured the way the app
captures them, a manifest signed the way the app signs it, and a clock the API's evidence
rules can be set to.

The example Passport's milestone 0 has its window from 1 to 31 March 2027 and its site is a
small rectangle around (40.7905, 48.151) in Yeni Qala.
"""

from __future__ import annotations

import io
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from PIL import Image, ImageDraw
from sqlalchemy import text, update

from veritas.core.canonical import canonical_json
from veritas.core.hashing import sha256, to_hex
from veritas.db.models.evidence import EvidenceBundle
from veritas.evidence.attestation import dev_token
from veritas.evidence.checks import load_evidence
from veritas.evidence.manifest import MANIFEST_FORMAT, signing_text
from veritas.evidence.redaction import Box

INSIDE = (40.7905, 48.151)
"""Latitude and longitude well inside the example site."""
JUST_NORTH = (40.7917, 48.151)
"""0.0002 degrees north of the site's edge: 22 metres outside it."""
FAR_AWAY = (40.4093, 49.8671)
"""Baku, 150 km from the site."""

IN_WINDOW = datetime(2027, 3, 10, 6, 0, tzinfo=UTC)
"""10:00 on 10 March 2027 in Baku: inside milestone 0's window."""

PDF = b"%PDF-1.7\n%Veritas test invoice\n%%EOF\n"


class Clock:
    """Stands in for the evidence clock dependency, so a test can pick the date."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> datetime:
        self.now += timedelta(**delta)
        return self.now


# ---------------------------------------------------------------- pictures


def scene(seed: int, size: tuple[int, int] = (960, 720)) -> Image.Image:
    """A made-up photo: coloured shapes on a background, different for every seed."""
    rng = random.Random(seed)
    image = Image.new("RGB", size, tuple(rng.randrange(256) for _ in range(3)))
    draw = ImageDraw.Draw(image)
    for _ in range(30):
        x0, y0 = rng.randrange(size[0]), rng.randrange(size[1])
        x1, y1 = x0 + rng.randrange(40, 400), y0 + rng.randrange(40, 300)
        colour = tuple(rng.randrange(256) for _ in range(3))
        if rng.random() < 0.5:
            draw.rectangle((x0, y0, x1, y1), fill=colour)
        else:
            draw.ellipse((x0, y0, x1, y1), fill=colour)
    return image


def jpeg(image: Image.Image, quality: int = 90, **params: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, **params)
    return buffer.getvalue()


def photo(seed: int) -> bytes:
    return jpeg(scene(seed))


def near_copy(data: bytes) -> bytes:
    """The same picture, scaled down and recompressed, as a reused photo usually is."""
    image = Image.open(io.BytesIO(data)).convert("RGB")
    return jpeg(image.resize((image.width * 3 // 4, image.height * 3 // 4)), quality=70)


def reframed(seed: int) -> bytes:
    """The scene with five percent cropped off two sides: close to the original, not the same.
    For seed 8, pHash and dHash are both 10 bits away."""
    image = scene(seed)
    width, height = image.size
    return jpeg(image.crop((width // 20, height // 20, width, height)).resize((width, height)))


def with_gps(image: Image.Image, latitude: float, longitude: float) -> bytes:
    """A JPEG whose EXIF holds a GPS position and a camera model, like a phone writes."""
    exif = Image.Exif()
    exif[0x0110] = "Veritas Test Phone"  # Model
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", _dms(latitude)
    gps[3], gps[4] = "E", _dms(longitude)
    return jpeg(image, exif=exif)


def _dms(value: float) -> tuple[float, float, float]:
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60, 2)
    return (float(degrees), float(minutes), seconds)


@dataclass(frozen=True)
class FixedBoxes:
    """A detector that 'finds' the boxes it was given, everywhere."""

    boxes: tuple[Box, ...] = ()
    name: str = "fixed"
    covers: frozenset[str] = field(default_factory=lambda: frozenset({"faces", "plates"}))

    def detect(self, image: object) -> list[Box]:
        return list(self.boxes)


# ---------------------------------------------------------------- captures and manifests


@dataclass(frozen=True)
class Capture:
    """One file as the phone captured it, with what the phone recorded."""

    kind: str
    data: bytes
    captured_at: datetime
    content_type: str = "image/jpeg"
    at: tuple[float, float] | None = INSIDE
    accuracy_m: float = 8.0
    mocked: bool = False

    @property
    def sha256(self) -> str:
        return to_hex(sha256(self.data))

    def form(self) -> dict[str, str]:
        fields = {
            "kind": self.kind,
            "sha256": self.sha256,
            "captured_at": _utc(self.captured_at),
            "mock_location": "true" if self.mocked else "false",
        }
        if self.at is not None:
            fields |= {
                "latitude": repr(self.at[0]),
                "longitude": repr(self.at[1]),
                "accuracy_m": repr(self.accuracy_m),
            }
        return fields

    def entry(self) -> dict[str, object]:
        location = None
        if self.at is not None:
            location = {
                "latitude": self.at[0],
                "longitude": self.at[1],
                "accuracy_m": self.accuracy_m,
                "mocked": self.mocked,
            }
        return {
            "kind": self.kind,
            "sha256": self.sha256,
            "size": len(self.data),
            "content_type": self.content_type,
            "captured_at": _utc(self.captured_at),
            "location": location,
        }


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def proof_set(start: datetime, seed: int = 1, photos: int = 4) -> list[Capture]:
    """What milestone 0's checklist asks for: four photos, an invoice and a receipt."""
    captures = [
        Capture("photo", photo(seed * 100 + n), start + timedelta(minutes=n + 1))
        for n in range(photos)
    ]
    captures.append(
        Capture("invoice", PDF, start + timedelta(minutes=6), "application/pdf", at=None)
    )
    captures.append(
        Capture(
            "fiscal_receipt",
            jpeg(scene(seed * 100 + 99, (400, 600))),
            start + timedelta(minutes=7),
            at=FAR_AWAY,
        )
    )
    return captures


def manifest_for(session: dict, device: str, captures: list[Capture]) -> bytes:
    """The canonical manifest the app builds for a session."""
    return canonical_json(
        {
            "format": MANIFEST_FORMAT,
            "session_id": session["id"],
            "project_id": session["project_id"],
            "milestone": session["milestone"],
            "attempt": session["attempt"],
            "challenge_code": session["challenge_code"],
            "device": device,
            "items": [capture.entry() for capture in captures],
        }
    )


def sign_manifest(account, data: bytes) -> str:
    message = encode_defunct(text=signing_text(sha256(data)))
    return Account.sign_message(message, private_key=account.key).signature.to_0x_hex()


def attest(settings, device: str, session_id: str, data: bytes) -> str:
    return dev_token(
        settings.attestation_dev_secret.get_secret_value().encode(),
        device=device,
        session_id=uuid.UUID(session_id),
        bundle_hash=sha256(data),
    )


# ---------------------------------------------------------------- checks


def run(db, bundle: dict, tools, check):
    """One check on a bundle the API made, reading what is committed now."""
    db.expire_all()
    row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
    return check(db, load_evidence(db, row), tools)


def mentions(result, *phrases: str) -> bool:
    """The reason says each phrase, whether or not it starts the sentence."""
    reason = (result.reason or "").lower()
    return all(phrase.lower() in reason for phrase in phrases)


def tamper(db, bundle: dict, **values) -> None:
    """Change a bundle row behind the API's back, as someone with database access could.
    Triggers are off for this one transaction."""
    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(
        update(EvidenceBundle).where(EvidenceBundle.id == uuid.UUID(bundle["id"])).values(**values)
    )
    db.commit()


# ---------------------------------------------------------------- the API


def register_device(client, person, account, platform: str = "android") -> dict:
    issued = client.post("/v1/devices/challenge", headers=person.headers).json()
    signature = account.sign_message(encode_defunct(text=issued["message"])).signature
    body = {
        "address": account.address,
        "platform": platform,
        "nonce": issued["nonce"],
        "signature": signature.to_0x_hex(),
    }
    response = client.post("/v1/devices", json=body, headers=person.headers)
    assert response.status_code == 201, response.text
    return response.json()


def start(client, person, project_id, account, index: int = 0):
    return client.post(
        f"/v1/projects/{project_id}/milestones/{index}/capture-sessions",
        json={"device_address": account.address},
        headers=person.headers,
    )


def upload(client, person, session_id: str, capture: Capture):
    return client.post(
        f"/v1/capture-sessions/{session_id}/items",
        data=capture.form(),
        files={"file": ("capture", capture.data, capture.content_type)},
        headers=person.headers,
    )


def submit(client, person, session_id: str, data: bytes, signature: str, attestation=None):
    body = {"manifest": data.decode("utf-8"), "signature": signature}
    if attestation is not None:
        body["attestation"] = attestation
    return client.post(
        f"/v1/capture-sessions/{session_id}/manifest", json=body, headers=person.headers
    )


def capture_bundle(
    client,
    settings,
    clock: Clock,
    person,
    project_id,
    account,
    captures: list[Capture],
    *,
    attestation: bool = True,
    uploads_at: datetime | None = None,
) -> dict:
    """Start a session now, upload every capture a minute after the last one was taken (or at
    `uploads_at`), and submit the signed manifest. Returns the bundle."""
    response = start(client, person, project_id, account)
    assert response.status_code == 201, response.text
    session = response.json()
    if uploads_at is None:
        uploads_at = max(clock.now, max(c.captured_at for c in captures) + timedelta(minutes=1))
    clock.now = uploads_at
    for capture in captures:
        response = upload(client, person, session["id"], capture)
        assert response.status_code == 201, response.text
    data = manifest_for(session, account.address, captures)
    token = attest(settings, account.address, session["id"], data) if attestation else None
    response = submit(client, person, session["id"], data, sign_manifest(account, data), token)
    assert response.status_code == 201, response.text
    return response.json()
