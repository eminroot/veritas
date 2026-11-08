"""The public copy of a bundle, and publishing it to IPFS.

Three kinds of file go public, each pinned on our node:

- the redacted photos: no metadata, faces and number plates blurred;
- the check report, whose SHA-256 is anchored on-chain;
- the public manifest, which names the private bundle hash, the report's hash and CID, each
  photo's CID and capture time, a location rounded to about a kilometre, and every check's
  result. Its CID is the one anchored on-chain, so everything else is found from it.

Nothing goes to IPFS before the charity signs the bundle. The worker first builds the copy in
private storage: photos redacted, every CID computed here (each file fits one IPFS block, so
its CID is a hash of its bytes). Publishing a face cannot be undone and no detector finds
every face, so when the charity signs, the signer also names the photos they looked at and
confirm show no face or number plate (`finalize_public_copy`); only those stay in the copy,
the rest are listed as withheld. The worker then adds and pins the final copy (`pin_bundle`).

Invoices, receipts and documents stay private until Phase 7 can mask the personal details on
them, and videos until they can be redacted; the public manifest lists them by kind and count.
A photo that cannot be redacted safely, or whose stored original does not match the
manifest, stays private too. Exact positions and anything about the phone never go public:
the location is rounded, and only from fixes check 2 placed on the site, so a photo taken
elsewhere does not reveal where (ARCHITECTURE.md sections 4 and 11).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection
from statistics import fmean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.core.canonical import canonical_json, parse_canonical
from veritas.core.hashing import sha256, to_hex
from veritas.db.models.evidence import (
    CheckReport,
    EvidenceBundle,
    EvidenceCheck,
    EvidenceItem,
)
from veritas.db.session import db_now
from veritas.evidence.checks import Evidence, load_evidence
from veritas.evidence.intake import ON_SITE, public_key
from veritas.evidence.ipfs import CHUNK_SIZE, Ipfs, IpfsError
from veritas.evidence.manifest import ManifestItem
from veritas.evidence.redaction import Detector, RedactionError, can_redact, redact_photo
from veritas.evidence.wording import utc
from veritas.passport.models import ProofKind
from veritas.services.cid import raw_cid
from veritas.services.errors import Unprocessable
from veritas.storage import PrivateStorage

PUBLIC_FORMAT = "veritas.evidence.public/1"
COARSE_DECIMALS = 2
"""0.01 degrees: about 1.1 km north to south, 0.85 km east to west in Azerbaijan."""
PLACE_CHECK = 2

WITHHELD = {
    ProofKind.VIDEO: "videos cannot be redacted yet, so they stay private",
    ProofKind.INVOICE: "personal details on documents are masked from Phase 7 on; until then "
    "they stay private",
    ProofKind.FISCAL_RECEIPT: "personal details on documents are masked from Phase 7 on; until "
    "then they stay private",
    ProofKind.DOCUMENT: "personal details on documents are masked from Phase 7 on; until then "
    "they stay private",
}
NO_DETECTOR = "no detector for faces and number plates runs on this server, so photos stay private"
NOT_INTACT = "the stored original does not match the manifest, so it is not published"
NOT_REDACTABLE = "it could not be redacted safely, so it stays private"
UNCONFIRMED = (
    "nobody confirmed it at signing that no face or number plate shows, so it stays private"
)


def publish_bundle(
    session: Session,
    bundle: EvidenceBundle,
    *,
    storage: PrivateStorage,
    detector: Detector | None,
) -> None:
    """Build the public copy in private storage and record its CIDs; nothing goes to IPFS
    yet. The caller sets the status."""
    evidence = load_evidence(session, bundle)
    report = session.scalars(select(CheckReport).where(CheckReport.bundle_id == bundle.id)).one()
    checks = session.scalars(
        select(EvidenceCheck)
        .where(EvidenceCheck.bundle_id == bundle.id)
        .order_by(EvidenceCheck.number)
    ).all()

    safe = can_redact(detector)
    if not safe and any(entry.kind == ProofKind.PHOTO for entry in evidence.manifest.items):
        raise_alert(
            session,
            kind="redaction_unavailable",
            message="Photos stay out of public evidence copies: no detector for faces and number "
            "plates is available. OpenCV 5 has no Haar cascades; run OpenCV 4 (with "
            "VERITAS_REDACTION_CASCADE_DIR if its files are elsewhere) or plug in a detector.",
            dedupe_key="redaction_unavailable",
        )
    stored = {item.position: item for item in evidence.items}
    photos: list[dict[str, Any]] = []
    withheld: Counter[tuple[str, str]] = Counter()
    for position, (entry, label) in enumerate(
        zip(evidence.manifest.items, evidence.labels, strict=True)
    ):
        item = stored.get(position)
        if entry.kind != ProofKind.PHOTO:
            withheld[(str(entry.kind), WITHHELD[entry.kind])] += 1
        elif not safe or detector is None:
            withheld[(str(entry.kind), NO_DETECTOR)] += 1
        elif item is None:
            withheld[(str(entry.kind), NOT_INTACT)] += 1
        else:
            prepared = _prepare_photo(storage, detector, item, entry, label)
            if isinstance(prepared, str):
                withheld[(str(entry.kind), prepared)] += 1
            else:
                photos.append(prepared)

    if len(report.canonical_bytes) > CHUNK_SIZE:
        raise ValueError("the check report is larger than one IPFS block")
    data = canonical_json(
        public_document(
            evidence,
            report_sha256=report.sha256,
            report_cid=raw_cid(report.canonical_bytes),
            passed=report.passed,
            checks=[
                {"number": c.number, "name": c.name, "kind": c.kind, "status": c.status}
                for c in checks
            ],
            photos=photos,
            withheld=[
                {"kind": kind, "count": count, "reason": reason}
                for (kind, reason), count in sorted(withheld.items())
            ],
            on_site=_placed_on_site(checks),
        )
    )
    if len(data) > CHUNK_SIZE:
        raise ValueError("the public manifest is larger than one IPFS block")
    bundle.public_manifest = data
    bundle.public_cid = raw_cid(data)
    session.flush()


def _prepare_photo(
    storage: PrivateStorage,
    detector: Detector,
    item: EvidenceItem,
    entry: ManifestItem,
    label: str,
) -> dict[str, Any] | str:
    """The photo's public entry once its redacted copy is in private storage, or why it
    stays private."""
    try:
        original = storage.get(item.storage_key)
    except KeyError:
        return NOT_INTACT
    if sha256(original) != entry.digest:
        return NOT_INTACT
    try:
        public = redact_photo(original, entry.content_type, detector)
    except RedactionError:
        return NOT_REDACTABLE
    key = public_key(item.session_id, sha256(public.data))
    storage.put(key, public.data)
    cid = raw_cid(public.data)
    item.redacted_key = key
    item.redacted_cid = cid
    item.blurred_regions = len(public.blurred)
    return {
        "name": label,
        "cid": cid,
        "captured_at": entry.captured_at,
        "width": public.width,
        "height": public.height,
        "blurred_regions": len(public.blurred),
    }


def public_document(
    evidence: Evidence,
    *,
    report_sha256: bytes,
    report_cid: str,
    passed: bool,
    checks: list[dict[str, Any]],
    photos: list[dict[str, Any]],
    withheld: list[dict[str, Any]],
    on_site: set[str],
) -> dict[str, Any]:
    bundle = evidence.bundle
    times = sorted(entry.captured for entry in evidence.manifest.items)
    return {
        "format": PUBLIC_FORMAT,
        "project_id": str(bundle.project_id),
        "milestone": bundle.milestone_index,
        "attempt": bundle.attempt,
        "bundle_hash": to_hex(bundle.bundle_hash),
        "report": {"sha256": to_hex(report_sha256), "cid": report_cid, "passed": passed},
        "checks": checks,
        "captured": {"first": utc(times[0]), "last": utc(times[-1])},
        "location": coarse_location(evidence.manifest.items, evidence.labels, on_site),
        "photos": photos,
        "withheld": withheld,
    }


def _placed_on_site(checks: Collection[EvidenceCheck]) -> set[str]:
    """The captures check 2 placed on the site, by label."""
    for check in checks:
        if check.number == PLACE_CHECK:
            return {row["item"] for row in check.details.get("captures", []) if row.get("on_site")}
    return set()


def coarse_location(
    items: list[ManifestItem], labels: list[str], on_site: set[str]
) -> dict[str, Any] | None:
    """Where the site captures were taken, rounded to about a kilometre. Never the fixes, and
    only fixes check 2 placed on the site: an outlier would move the point where nobody took a
    photo, and a photo taken elsewhere would say where."""
    fixes = [
        entry.location
        for entry, label in zip(items, labels, strict=True)
        if entry.kind in ON_SITE and entry.location is not None and label in on_site
    ]
    if not fixes:
        return None
    return {
        "latitude": round(fmean(fix.latitude for fix in fixes), COARSE_DECIMALS),
        "longitude": round(fmean(fix.longitude for fix in fixes), COARSE_DECIMALS),
        "rounded_to_degrees": 10**-COARSE_DECIMALS,
    }


class PublicCopyError(RuntimeError):
    """One bundle's public files are not what its signed copy names. Its own problem, not the
    IPFS node's: the other bundles can still be pinned."""


def finalize_public_copy(session: Session, bundle: EvidenceBundle, photos: Collection[int]) -> None:
    """Make the public copy final at the charity's signature: keep only the photos the signer
    looked at and confirmed show no face or number plate, by number (photo 1, photo 2, ...).
    The others move to the withheld list and never reach IPFS. No detector catches every
    face, so no photo goes public without a person's word.

    Raises Unprocessable for a number that is not a photo of the prepared public copy.
    """
    assert bundle.public_manifest is not None and bundle.charity_signature is None
    document = parse_canonical(bundle.public_manifest)
    offered = {_photo_number(entry["name"]): entry for entry in document["photos"]}
    unknown = sorted(set(photos) - set(offered))
    if unknown:
        raise Unprocessable(
            "unknown_photo",
            f"Photo {unknown[0]} is not in the public copy of this bundle; only "
            + (", ".join(f"photo {n}" for n in sorted(offered)) or "no photo")
            + " can be published.",
        )
    kept = [offered[n] for n in sorted(offered) if n in set(photos)]
    dropped = len(offered) - len(kept)
    if dropped:
        withheld = Counter(
            {(entry["kind"], entry["reason"]): entry["count"] for entry in document["withheld"]}
        )
        withheld[(str(ProofKind.PHOTO), UNCONFIRMED)] += dropped
        document["photos"] = kept
        document["withheld"] = [
            {"kind": kind, "count": count, "reason": reason}
            for (kind, reason), count in sorted(withheld.items())
        ]
    data = canonical_json(document)
    bundle.public_manifest = data
    bundle.public_cid = raw_cid(data)
    session.flush()


def pin_bundle(
    session: Session, bundle: EvidenceBundle, *, storage: PrivateStorage, ipfs: Ipfs
) -> None:
    """Add and pin the signed public copy: its confirmed photos, the report and the manifest.
    Every CID must be the one the copy names; anything else is an error to retry."""
    assert bundle.public_manifest is not None and bundle.charity_signature is not None
    document = parse_canonical(bundle.public_manifest)
    by_cid = {
        item.redacted_cid: item
        for item in session.scalars(
            select(EvidenceItem).where(
                EvidenceItem.session_id == bundle.session_id, EvidenceItem.redacted_cid.is_not(None)
            )
        )
    }
    files: list[tuple[str, bytes, str]] = []
    for photo in document["photos"]:
        item = by_cid.get(photo["cid"])
        try:
            data = storage.get(item.redacted_key) if item and item.redacted_key else None
        except KeyError:
            data = None
        if data is None:
            raise PublicCopyError(f"{photo['name']}'s redacted copy is not in private storage")
        files.append((photo["cid"], data, photo["name"].replace(" ", "-") + ".jpg"))
    report = session.scalars(select(CheckReport).where(CheckReport.bundle_id == bundle.id)).one()
    files.append((document["report"]["cid"], report.canonical_bytes, "report.json"))
    files.append((bundle.public_cid or "", bundle.public_manifest, "evidence.json"))
    # Every file is checked before the first goes out: what reaches IPFS stays there.
    for expected, data, name in files:
        if len(data) > CHUNK_SIZE or raw_cid(data) != expected:
            raise PublicCopyError(f"the stored {name} is not the file the signed copy names")
    for expected, data, name in files:
        added = ipfs.add(data, name=name)
        if added != expected:
            raise IpfsError(
                f"IPFS gave {name} the CID {added}, but the public copy names {expected}"
            )
    bundle.pinned_at = db_now(session)
    session.flush()


def _photo_number(name: str) -> int:
    """'photo 3' -> 3."""
    return int(name.rsplit(" ", 1)[1])
