"""A donor's receipts, and moving one to a new key.

A receipt is the donor's identity in one project: their votes and refund choices are signed
by the key that controls it. With the old phone at hand, that key signs the move to the new
phone's key and it happens at once. After a lost phone, the donor proves who they are again
from the same account, with a card they paid with, and the move waits 48 hours on-chain.
During that time the old key can refuse it, which protects donors whose number was stolen.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import select

from veritas.api.deps import AdminUser, ChainDep, CurrentCaller, CurrentUser, DbSession
from veritas.api.routes.decisions import Address, Signature, _bytes, _chain, _project
from veritas.api.schemas import Input, Output
from veritas.chain import eip712
from veritas.db.models.money import Donation, Receipt
from veritas.decisions import recovery
from veritas.decisions.recovery import MAX_RECOVERY_FAILURES

router = APIRouter(tags=["receipts"])

BASE = "/v1/projects/{project_id}/receipts/{holder}"
DAY = 24 * 3600


class PendingRotationOut(Output):
    new_key: str
    ready_at: datetime
    """From then on the move can be finished; Veritas finishes it shortly after."""


class ReceiptOut(Output):
    project_id: uuid.UUID
    holder: str
    receipt_id: str
    """The token id, as decimal text."""
    controller: str
    status: str
    pending_rotation: PendingRotationOut | None
    recovery_locked: bool


@router.get("/v1/receipts")
def my_receipts(user: CurrentUser, db: DbSession, chain: ChainDep) -> list[ReceiptOut]:
    """Every receipt for a key this account donated with, a lost phone's keys included."""
    receipts = db.scalars(
        select(Receipt)
        .join(
            Donation,
            (Donation.project_id == Receipt.project_id) & (Donation.holder == Receipt.holder),
        )
        .where(Donation.user_id == user.id)
        .distinct()
        .order_by(Receipt.created_at)
    ).all()
    out = []
    for receipt in receipts:
        pending = (
            recovery.pending_rotation(chain.contracts, receipt)
            if chain is not None and receipt.status == "minted"
            else None
        )
        out.append(
            ReceiptOut(
                project_id=receipt.project_id,
                holder=receipt.holder,
                receipt_id=receipt.token_id,
                controller=receipt.controller,
                status=receipt.status,
                pending_rotation=PendingRotationOut(
                    new_key=pending.new_key,
                    ready_at=datetime.fromtimestamp(pending.ready_at, UTC),
                )
                if pending
                else None,
                recovery_locked=user.recovery_failures >= MAX_RECOVERY_FAILURES,
            )
        )
    return out


# ---------------------------------------------------------------- with the old phone


@router.get(f"{BASE}/rotation-message")
def rotation_message(
    project_id: uuid.UUID,
    holder: str,
    new_key: Annotated[str, Query(pattern=r"^0x[0-9a-fA-F]{40}$")],
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
    deadline: int | None = None,
) -> dict[str, Any]:
    """The KeyRotation message for the receipt's current key to sign."""
    chain = _chain(chain)
    receipt = recovery.receipt_for(db, _project(db, project_id), holder)
    message = recovery.rotation_message(
        chain.contracts, receipt, new_key, deadline or int(time.time()) + DAY
    )
    return eip712.typed_data(chain.domain, "KeyRotation", message)


class RotationIn(Input):
    new_key: Address
    deadline: int
    signature: Signature


@router.post(f"{BASE}/rotation", status_code=202)
def rotate(
    project_id: uuid.UUID,
    holder: str,
    body: RotationIn,
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
) -> dict[str, str]:
    """Moves the receipt at once, signed by its current key."""
    chain = _chain(chain)
    receipt = recovery.receipt_for(db, _project(db, project_id), holder, lock=True)
    recovery.rotate_with_key(
        db,
        chain.domain,
        chain.contracts,
        receipt,
        new_key=body.new_key,
        deadline=body.deadline,
        signature=_bytes(body.signature) or b"",
    )
    return {"status": "queued"}


# ---------------------------------------------------------------- after a lost phone


class RecoveryIn(Input):
    new_key: Address = Field(description="The new phone's key for this project.")
    card_last4: str = Field(pattern=r"^\d{4}$", description="A card this account paid with.")


@router.post(f"{BASE}/recovery", status_code=202)
def recover(
    project_id: uuid.UUID,
    holder: str,
    body: RecoveryIn,
    caller: CurrentCaller,
    db: DbSession,
    chain: ChainDep,
) -> dict[str, Any]:
    """Asks to move a lost phone's receipt to a new key. The move waits 48 hours on-chain.

    The card has to be one the account paid with before the receipt was issued."""
    chain = _chain(chain)
    receipt = recovery.receipt_for(db, _project(db, project_id), holder, lock=True)
    recovery.request_recovery(
        db,
        chain.contracts,
        receipt,
        caller.user,
        new_key=body.new_key,
        card_last4=body.card_last4,
    )
    return {"status": "queued", "wait_hours": 48}


@router.get(f"{BASE}/cancel-message")
def cancel_message(
    project_id: uuid.UUID, holder: str, user: CurrentUser, db: DbSession, chain: ChainDep
) -> dict[str, Any]:
    """The RotationCancel message for the current key to refuse a requested move."""
    chain = _chain(chain)
    receipt = recovery.receipt_for(db, _project(db, project_id), holder)
    message = recovery.cancel_message(chain.contracts, receipt)
    return eip712.typed_data(chain.domain, "RotationCancel", message)


class CancelIn(Input):
    signature: Signature


@router.post(f"{BASE}/cancel", status_code=202)
def cancel(
    project_id: uuid.UUID,
    holder: str,
    body: CancelIn,
    user: CurrentUser,
    db: DbSession,
    chain: ChainDep,
) -> dict[str, str]:
    chain = _chain(chain)
    receipt = recovery.receipt_for(db, _project(db, project_id), holder, lock=True)
    recovery.cancel_rotation(
        db, chain.domain, chain.contracts, receipt, _bytes(body.signature) or b""
    )
    return {"status": "queued"}


@router.post(f"{BASE}/unlock-recovery")
def unlock_recovery(
    project_id: uuid.UUID, holder: str, admin: AdminUser, db: DbSession
) -> dict[str, str]:
    """Support allows new recovery tries once it has checked who the donor is."""
    receipt = recovery.receipt_for(db, _project(db, project_id), holder, lock=True)
    recovery.unlock_recovery(db, receipt)
    return {"status": "unlocked"}
