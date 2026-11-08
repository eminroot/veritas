"""Check 1: the stored files are the ones the manifest lists, the manifest is signed by the
capture session's phone, and the app's attestation is valid.

The originals are read back from private storage and hashed again, so a file that was lost
or changed after it arrived fails here instead of going on to the officer unnoticed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.core.hashing import sha256
from veritas.db.models import Device
from veritas.db.models.evidence import CheckStatus
from veritas.evidence.checks.base import Evidence, Result, Tools
from veritas.evidence.manifest import manifest_signer
from veritas.evidence.wording import baku_day, joined


def check(session: Session, evidence: Evidence, tools: Tools) -> Result:
    """The signature, key and attestation problems come first: a long list of file problems is
    cut short in the reason, and these must never be the part that is cut. The details hold
    every one of them too."""
    problems: list[str] = []
    file_problems: list[str] = []
    files = _files(evidence, tools, file_problems)

    bundle = evidence.bundle
    signer = manifest_signer(bundle.bundle_hash, bundle.device_signature)
    signed = signer is not None and signer == evidence.capture.device_address
    if not signed:
        problems.append("the manifest is not signed by the capture session's device key")
    device = session.scalars(select(Device).where(Device.address == bundle.device_address)).first()
    if device is None:
        problems.append("the device key that signed the manifest is not registered")
    elif device.revoked_at is not None:
        problems.append(f"the device key was revoked on {baku_day(device.revoked_at)}")

    attestation = tools.attestation.verify(
        bundle.attestation,
        platform=device.platform if device is not None else "unknown",
        device=bundle.device_address,
        session_id=evidence.capture.id,
        bundle_hash=bundle.bundle_hash,
    )
    if not attestation.valid:
        problems.append(f"the app attestation is not valid: {attestation.reason}")

    details = {
        "files": files,
        "signed_by_capture_device": signed,
        "device_revoked_at": None
        if device is None or device.revoked_at is None
        else device.revoked_at.isoformat(),
        "attestation": {
            "scheme": attestation.scheme,
            "valid": attestation.valid,
            "reason": None if attestation.valid else attestation.reason,
        },
    }
    problems += file_problems
    if problems:
        return Result(1, CheckStatus.FAILED, joined(problems), details)
    return Result(1, CheckStatus.PASSED, details=details)


def _files(evidence: Evidence, tools: Tools, problems: list[str]) -> list[dict[str, Any]]:
    """Each listed file, read back from storage and hashed again."""
    stored = {item.position: item for item in evidence.items}
    files = []
    for position, (entry, label) in enumerate(
        zip(evidence.manifest.items, evidence.labels, strict=True)
    ):
        item = stored.get(position)
        if item is None:
            problems.append(f"{label} is in the manifest but no upload is recorded for it")
            files.append({"item": label, "matches": False})
            continue
        try:
            data = tools.storage.get(item.storage_key)
        except KeyError:
            problems.append(f"{label}: the original is missing from private storage")
            files.append({"item": label, "matches": False})
            continue
        matches = sha256(data) == entry.digest and len(data) == entry.size
        if not matches:
            problems.append(f"{label}: the stored file does not match its SHA-256 in the manifest")
        files.append({"item": label, "matches": matches})
    return files
