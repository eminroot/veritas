"""What every check shares: the catalogue of checks, a result, and the evidence they read."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.db.models import Milestone, PassportVersion, Project
from veritas.db.models.evidence import (
    CaptureSession,
    CheckKind,
    CheckStatus,
    EvidenceBundle,
    EvidenceItem,
)
from veritas.evidence.attestation import AttestationVerifier
from veritas.evidence.capture import find_milestone, published_passport
from veritas.evidence.manifest import Manifest, read_manifest
from veritas.evidence.wording import labels
from veritas.passport.models import Passport
from veritas.settings import Settings
from veritas.storage import PrivateStorage

LATER = "arrives with the AI and document checks (Phase 7); the officer reviews this by hand"


@dataclass(frozen=True)
class Spec:
    number: int
    name: str
    kind: CheckKind
    title: str


CATALOGUE = (
    Spec(
        1,
        "files_and_signatures",
        CheckKind.HARD,
        "Files match the manifest hashes, and the manifest signature and app attestation are valid",
    ),
    Spec(
        2,
        "geofence",
        CheckKind.HARD,
        "GPS inside the geofence, allowing for accuracy, and not a mocked location",
    ),
    Spec(
        3,
        "time_window",
        CheckKind.HARD,
        "Captured while the challenge code was valid and not before the milestone's window; "
        "late captures flagged",
    ),
    Spec(4, "challenge_code", CheckKind.HARD, "Challenge code visible in a photo"),
    Spec(
        5,
        "photo_reuse",
        CheckKind.HARD,
        "Not a reused photo: perceptual hash compared with every photo ever stored",
    ),
    Spec(
        6,
        "content_credentials",
        CheckKind.ADVISORY,
        "C2PA content credentials and an AI-generated image score",
    ),
    Spec(7, "deliverable", CheckKind.ADVISORY, "The photos show the promised deliverable"),
    Spec(8, "invoice", CheckKind.HARD, "Invoice totals, dates and VÖEN"),
    Spec(
        9,
        "fiscal_receipt",
        CheckKind.HARD,
        "The e-kassa receipt QR points to a real fiscal receipt with the same seller, date "
        "and amount",
    ),
    Spec(
        10,
        "contractor_voen",
        CheckKind.HARD,
        "The contractor's VÖEN matches the Passport and is active",
    ),
    Spec(
        11,
        "proof_checklist",
        CheckKind.HARD,
        "Everything on the milestone's proof checklist is there",
    ),
)
SPECS = {spec.number: spec for spec in CATALOGUE}
NOT_YET = (4, 6, 7, 8, 9, 10)


@dataclass(frozen=True)
class Result:
    number: int
    status: CheckStatus
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status != CheckStatus.PASSED and not self.reason:
            raise ValueError(f"check {self.number} did not pass, so it needs a reason")
        if self.status == CheckStatus.FAILED and self.spec.kind != CheckKind.HARD:
            raise ValueError(f"check {self.number} is advisory and cannot fail")

    @property
    def spec(self) -> Spec:
        return SPECS[self.number]


def passed(results: Sequence[Result]) -> bool:
    """Every hard check that ran passed. Advisory results and checks not run do not count."""
    return all(result.status != CheckStatus.FAILED for result in results)


@dataclass(frozen=True)
class Evidence:
    """Everything the checks read about one bundle, loaded once."""

    bundle: EvidenceBundle
    capture: CaptureSession
    manifest: Manifest
    items: list[EvidenceItem]
    """Uploaded items in manifest order: items[i] is manifest.items[i]."""
    labels: list[str]
    """'photo 1', 'invoice 1', ... in manifest order."""
    project: Project
    milestone: Milestone
    passport_version: PassportVersion
    passport: Passport

    def label_of(self, item_id: uuid.UUID) -> str | None:
        for item, label in zip(self.items, self.labels, strict=True):
            if item.id == item_id:
                return label
        return None


@dataclass(frozen=True)
class Tools:
    storage: PrivateStorage
    attestation: AttestationVerifier
    settings: Settings


def load_evidence(session: Session, bundle: EvidenceBundle) -> Evidence:
    capture = session.get_one(CaptureSession, bundle.session_id)
    manifest = read_manifest(bundle.manifest_bytes)
    rows = session.scalars(
        select(EvidenceItem)
        .where(EvidenceItem.session_id == capture.id, EvidenceItem.position.is_not(None))
        .order_by(EvidenceItem.position)
    ).all()
    project = session.get_one(Project, bundle.project_id)
    version, passport = published_passport(session, project)
    return Evidence(
        bundle=bundle,
        capture=capture,
        manifest=manifest,
        items=list(rows),
        labels=labels(entry.kind for entry in manifest.items),
        project=project,
        milestone=find_milestone(session, project, bundle.milestone_index),
        passport_version=version,
        passport=passport,
    )


Check = Callable[[Session, Evidence, Tools], Result]


def not_run(number: int) -> Result:
    return Result(number, CheckStatus.NOT_RUN, LATER)
