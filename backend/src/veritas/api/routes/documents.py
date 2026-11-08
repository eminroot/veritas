"""Downloading KYB documents, for the reviewers and the organisation that owns them."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Response, UploadFile

from veritas.api.deps import CurrentUser, DbSession, StorageDep, charity_membership
from veritas.core.hashing import sha256, to_hex
from veritas.db.models import Contractor, KybDocument, OwnerType
from veritas.services.errors import Forbidden, InternalError, NotFound
from veritas.services.officers import active_officer

router = APIRouter(prefix="/v1/documents", tags=["documents"])


def read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """The uploaded bytes, reading at most one byte past the limit so size can be checked."""
    return file.file.read(max_bytes + 1)


@router.get(
    "/{document_id}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}, "image/jpeg": {}, "image/png": {}}}},
)
def download_document(
    document_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> Response:
    """The file as uploaded. Admins, and members of the owning charity, may read it."""
    document = db.get(KybDocument, document_id)
    if document is None:
        raise NotFound("not_found", "There is no document with this id.")
    if document.owner_type == OwnerType.CHARITY:
        charity_id = document.owner_id
    else:
        contractor = db.get_one(Contractor, document.owner_id)
        charity_id = contractor.charity_id
    allowed = (
        user.is_admin
        or charity_membership(db, user, charity_id) is not None
        or (document.owner_type == OwnerType.CONTRACTOR and active_officer(db, user) is not None)
    )
    if not allowed:
        raise Forbidden("forbidden", "You cannot read this document.")
    try:
        data = storage.get(document.storage_key)
    except KeyError:
        raise InternalError("document_missing", "The stored file is missing.") from None
    if sha256(data) != document.sha256:
        raise InternalError("document_damaged", "The stored file does not match its hash.")
    filename = quote(document.filename)
    return Response(
        content=data,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-SHA256": to_hex(document.sha256),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
