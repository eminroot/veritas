"""The evidence manifest: everything one phone captured in one capture session, signed with the
phone's key.

The app writes it as canonical JSON (RFC 8785) and the server keeps those bytes exactly. The
bundle hash is their SHA-256: the phone signs it, the charity signs it and the chain stores
it, so a manifest is never re-serialised here. Every field is required, even when its value
is null, and unknown fields are refused, so one set of captures has one spelling.

The phone signs with EIP-191 personal_sign, the call it already uses to prove its key when
it is registered, over this text:

    Veritas evidence manifest
    0x<SHA-256 of the manifest bytes in lower-case hex>

A manifest with one photo (shown on several lines; the real bytes have no whitespace):

    {"attempt":1,"challenge_code":"K7Q2MX","device":"0x<checksummed address>",
     "format":"veritas.evidence.manifest/1",
     "items":[{"captured_at":"2027-03-10T06:01:02Z","content_type":"image/jpeg",
               "kind":"photo","location":{"accuracy_m":8,"latitude":40.7905,
               "longitude":48.151,"mocked":false},"sha256":"0x<64 hex>","size":183245}],
     "milestone":0,"project_id":"<uuid>","session_id":"<uuid>"}
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from eth_utils import is_address, to_checksum_address
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
)

from veritas.chain.leaves import MAX_MILESTONES
from veritas.core.canonical import CanonicalJSONError, parse_canonical
from veritas.core.hashing import to_hex
from veritas.passport.errors import Problem, readable_problems
from veritas.passport.models import MAX_PROOF_FILES, ProofKind
from veritas.services.keys import recover_signer

MANIFEST_FORMAT = "veritas.evidence.manifest/1"
SIGNING_PREFIX = "Veritas evidence manifest\n"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ITEMS = MAX_PROOF_FILES
CODE_PATTERN = r"^[A-HJ-NP-Z2-9]{6}$"
_UTC_TIME = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z$"


class ManifestError(ValueError):
    """Manifest bytes that cannot be accepted, with what is wrong in readable form."""

    def __init__(self, message: str, problems: list[Problem] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.problems = problems or []


def _number(value: Any) -> Any:
    """A JSON number. Canonical JSON writes 8.0 as 8, so whole numbers are fine too."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("must be a number")
    return value


def _utc_time(value: str) -> str:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("is not a real time, write it like 2027-03-10T06:01:02Z") from None
    return value


def _checksummed(value: str) -> str:
    if not is_address(value) or value != to_checksum_address(value):
        raise ValueError("must be the device's address in its checksummed form")
    return value


Number = Annotated[float, BeforeValidator(_number)]
UtcTime = Annotated[str, Field(pattern=_UTC_TIME), AfterValidator(_utc_time)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Location(_Model):
    latitude: Annotated[Number, Field(ge=-90, le=90)]
    longitude: Annotated[Number, Field(ge=-180, le=180)]
    accuracy_m: Annotated[Number, Field(gt=0, le=10_000)]
    """The radius, in metres, the phone says the true position is within."""
    mocked: StrictBool
    """The phone reported that a location-mocking app supplied the position."""


class ManifestItem(_Model):
    kind: ProofKind
    sha256: Annotated[str, Field(pattern=r"^0x[0-9a-f]{64}$")]
    size: Annotated[StrictInt, Field(ge=1)]
    content_type: Literal[
        "image/jpeg", "image/png", "video/mp4", "video/quicktime", "application/pdf"
    ]
    captured_at: UtcTime
    location: Location | None

    @property
    def digest(self) -> bytes:
        return bytes.fromhex(self.sha256[2:])

    @property
    def captured(self) -> datetime:
        return datetime.fromisoformat(self.captured_at)


class Manifest(_Model):
    format: Literal["veritas.evidence.manifest/1"]
    session_id: UUID
    project_id: UUID
    milestone: Annotated[StrictInt, Field(ge=0, lt=MAX_MILESTONES)]
    attempt: Annotated[StrictInt, Field(ge=1)]
    challenge_code: Annotated[str, Field(pattern=CODE_PATTERN)]
    device: Annotated[str, AfterValidator(_checksummed)]
    items: Annotated[list[ManifestItem], Field(min_length=1, max_length=MAX_ITEMS)]


def read_manifest(data: bytes) -> Manifest:
    """Parse manifest bytes, refusing anything that is not a canonical, complete manifest."""
    if len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"The manifest is larger than {MAX_MANIFEST_BYTES // 1024} KB.")
    try:
        value = parse_canonical(data)
    except CanonicalJSONError as exc:
        raise ManifestError(
            f"The manifest must be canonical JSON (RFC 8785), byte for byte: {exc}."
        ) from None
    try:
        return Manifest.model_validate(value)
    except ValidationError as exc:
        raise ManifestError(
            "The manifest has fields that are missing or not valid.", readable_problems(exc)
        ) from None


def signing_text(bundle_hash: bytes) -> str:
    """The exact text the phone signs with personal_sign."""
    return SIGNING_PREFIX + to_hex(bundle_hash)


def manifest_signer(bundle_hash: bytes, signature: bytes) -> str | None:
    """The checksummed address that signed the manifest with this hash, or None."""
    return recover_signer(signing_text(bundle_hash), signature)
