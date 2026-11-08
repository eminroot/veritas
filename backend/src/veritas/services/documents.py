"""KYB documents: registration papers, charters, ID scans.

Files go to private storage under a key made from their SHA-256, and the row
records that hash, so anyone reviewing a document later can check it is the file
that was uploaded. Only PDF, JPEG and PNG are taken, and the first bytes must
match the declared type: a renamed executable is not a PDF.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.core.hashing import sha256
from veritas.db.models import DOCUMENT_TYPES, DocumentKind, KybDocument, OwnerType, User
from veritas.services.errors import Conflict, PayloadTooLarge, Unprocessable, UnsupportedMediaType
from veritas.storage import PrivateStorage, kyb_key

_MAGIC = {
    "application/pdf": b"%PDF-",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}
_NAMES = {"application/pdf": "a PDF", "image/png": "a PNG image", "image/jpeg": "a JPEG image"}

MAX_FILENAME = 200


def clean_filename(name: str | None) -> str:
    """The last part of what the browser sent, for display only. Never used as a path."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(char for char in base if char.isprintable()).strip()
    return base[:MAX_FILENAME] or "document"


def store_document(
    session: Session,
    storage: PrivateStorage,
    *,
    owner_type: OwnerType,
    owner_id: uuid.UUID,
    kind: DocumentKind,
    filename: str | None,
    content_type: str | None,
    data: bytes,
    max_bytes: int,
    user: User,
) -> KybDocument:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in DOCUMENT_TYPES:
        raise UnsupportedMediaType("unsupported_file", "Upload a PDF, JPEG or PNG file.")
    if not data:
        raise Unprocessable("empty_file", "The file is empty.")
    if len(data) > max_bytes:
        raise PayloadTooLarge(
            "file_too_large", f"The file is larger than {max_bytes // (1024 * 1024)} MB."
        )
    if not data.startswith(_MAGIC[media_type]):
        raise UnsupportedMediaType(
            "unsupported_file", f"The file is not {_NAMES[media_type]}, as its type says."
        )

    digest = sha256(data)
    duplicate = session.scalars(
        select(KybDocument.id).where(
            KybDocument.owner_type == owner_type,
            KybDocument.owner_id == owner_id,
            KybDocument.sha256 == digest,
        )
    ).first()
    if duplicate is not None:
        raise Conflict("document_exists", "This file has already been uploaded.")

    # Stored before the row: if the transaction fails, a stray file is left under its
    # own hash and the next upload of it simply overwrites it.
    key = kyb_key(owner_id, digest)
    storage.put(key, data)
    document = KybDocument(
        owner_type=owner_type,
        owner_id=owner_id,
        kind=kind,
        filename=clean_filename(filename),
        content_type=media_type,
        size_bytes=len(data),
        sha256=digest,
        storage_key=key,
        uploaded_by=user.id,
    )
    session.add(document)
    session.flush()
    return document


def documents_of(session: Session, owner_type: OwnerType, owner_id: uuid.UUID) -> list[KybDocument]:
    return list(
        session.scalars(
            select(KybDocument)
            .where(KybDocument.owner_type == owner_type, KybDocument.owner_id == owner_id)
            .order_by(KybDocument.created_at, KybDocument.id)
        )
    )
