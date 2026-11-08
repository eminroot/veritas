"""Keys on users' phones. The app proves it holds a key by signing a challenge with it."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from veritas.api.deps import CurrentCaller, CurrentUser, DbSession, SettingsDep
from veritas.api.schemas import Input, Nonce, Output, Signature, signature_bytes
from veritas.db.models import AuthSession, ChallengePurpose, Device, Platform
from veritas.db.models.evidence import CaptureSession, CaptureStatus
from veritas.db.session import db_now
from veritas.passport.models import Address, Name
from veritas.services.errors import Conflict, NotFound
from veritas.services.keys import issue_challenge, prove_key

router = APIRouter(prefix="/v1/devices", tags=["devices"])


class Challenge(BaseModel):
    nonce: str
    message: str = Field(description="Sign exactly this text with personal_sign (EIP-191).")
    expires_at: datetime


class DeviceIn(Input):
    address: Address
    platform: Platform
    label: Name | None = None
    nonce: Nonce
    signature: Signature
    attestation: str | None = Field(default=None, max_length=20_000)


class DeviceOut(Output):
    id: uuid.UUID
    address: str
    platform: str
    label: str | None
    created_at: datetime
    revoked_at: datetime | None


@router.post("/challenge", status_code=201)
def new_challenge(user: CurrentUser, db: DbSession, settings: SettingsDep) -> Challenge:
    """A one-time message to sign with the key being registered."""
    challenge = issue_challenge(db, settings, user, ChallengePurpose.DEVICE)
    return Challenge(
        nonce=challenge.nonce, message=challenge.message, expires_at=challenge.expires_at
    )


@router.post("", status_code=201)
def register_device(body: DeviceIn, caller: CurrentCaller, db: DbSession) -> DeviceOut:
    """Register the key that signed the challenge. Each key can be registered once, ever."""
    prove_key(
        db,
        caller.user,
        purpose=ChallengePurpose.DEVICE,
        nonce=body.nonce,
        address=body.address,
        signature=signature_bytes(body.signature),
    )
    if db.scalars(select(Device.id).where(Device.address == body.address)).first():
        raise Conflict("device_exists", "This key is already registered.")
    device = Device(
        user_id=caller.user.id,
        address=body.address,
        platform=body.platform,
        label=body.label,
        attestation=body.attestation,
    )
    db.add(device)
    db.flush()
    caller.session.device_id = device.id
    return DeviceOut.model_validate(device)


@router.get("")
def list_devices(user: CurrentUser, db: DbSession) -> list[DeviceOut]:
    devices = db.scalars(
        select(Device).where(Device.user_id == user.id).order_by(Device.created_at, Device.id)
    )
    return [DeviceOut.model_validate(device) for device in devices]


@router.post("/{device_id}/revoke")
def revoke_device(device_id: uuid.UUID, caller: CurrentCaller, db: DbSession) -> DeviceOut:
    """Stop trusting a key, for example when a phone is lost.

    Every other login of the account ends too, not only the one that registered the key: a
    phone that logged in again later has sessions no key is linked to, and a lost phone must
    not keep any of them. The caller's own session stays, unless it is the lost phone's. The
    key's open capture sessions close.
    """
    device = db.get(Device, device_id)
    if device is None or device.user_id != caller.user.id:
        raise NotFound("not_found", "You have no device with this id.")
    if device.revoked_at is None:
        now = db_now(db)
        device.revoked_at = now
        db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == caller.user.id,
                AuthSession.revoked_at.is_(None),
                (AuthSession.id != caller.session.id) | (AuthSession.device_id == device.id),
            )
            .values(revoked_at=now)
        )
        db.execute(
            update(CaptureSession)
            .where(
                CaptureSession.device_address == device.address,
                CaptureSession.status == CaptureStatus.OPEN,
            )
            .values(status=CaptureStatus.EXPIRED)
        )
    return DeviceOut.model_validate(device)
