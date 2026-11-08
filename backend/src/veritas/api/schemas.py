"""Request and response shapes shared by several routers.

Requests refuse unknown fields, so a typo in a field name is an error and not a
silently ignored value. Text goes through the same rules as the Passport (Unicode
NFC, no control characters), and identifiers through the same normalisers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

from veritas.core.hashing import to_hex
from veritas.core.identifiers import normalize_az_iban, normalize_az_phone


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


Phone = Annotated[
    str,
    AfterValidator(normalize_az_phone),
    Field(examples=["+994 50 123 45 67"], description="Any common way of writing it."),
]
Iban = Annotated[
    str, AfterValidator(normalize_az_iban), Field(examples=["AZ21NABZ00000000137010001944"])
]
Email = Annotated[
    str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", examples=["info@example.az"])
]
Website = Annotated[str, Field(max_length=200, pattern=r"^https?://\S+$")]
Nonce = Annotated[str, Field(min_length=1, max_length=64)]
Signature = Annotated[
    str,
    Field(
        pattern=r"^0x[0-9a-fA-F]{130}$",
        description="An EIP-191 personal_sign signature: 0x and 130 hex characters.",
    ),
]
Hex32 = Annotated[bytes, PlainSerializer(to_hex, return_type=str)]
"""A SHA-256, sent as 0x and 64 hex characters."""


def signature_bytes(signature: str) -> bytes:
    return bytes.fromhex(signature[2:])


class UserOut(Output):
    id: uuid.UUID
    phone: str
    display_name: str | None
    is_admin: bool
    created_at: datetime


class DocumentOut(Output):
    id: uuid.UUID
    owner_type: str
    owner_id: uuid.UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: Hex32
    created_at: datetime


class OfficerOut(Output):
    id: uuid.UUID
    name: str
    organisation: str
    address: str
    status: str
    user_id: uuid.UUID | None


class ProblemOut(BaseModel):
    path: str = Field(examples=["milestones[0].budget[1].amount_qapik"])
    message: str = Field(examples=["must be quantity times unit price, which is 120000"])
