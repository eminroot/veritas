"""Check 5: no photo in the bundle is one that was stored before, here or anywhere else.

Each photo's pHash and dHash are compared in PostgreSQL with those of every photo ever
stored, including photos from sessions that were never submitted. Both hashes within
`photo_reuse_clear_bits` of another photo's is a clear match and a hard fail: it is the same
picture, perhaps resized or recompressed. Both within `photo_reuse_close_bits` is close, an
advisory for the officer to compare by eye, since real photos of one spot taken again later
can come that close. Two matching photos inside one bundle are reported once, on the later.

Every photo on record counts, but only one stored earlier makes this photo a reuse. A copy
stored later elsewhere is the later bundle's reuse, however late the worker gets to this
bundle, so here it is only an advisory naming it: the original is not blamed, and the copy
is never missed, even when the two uploads raced. Photos of this bundle that come later in its
manifest are left out of the query, and clear matches are ranked first, so near-copies cannot
fill the matches reported and hide a clear one.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from veritas.db.models.evidence import CaptureStatus, CheckStatus, PhotoHash
from veritas.evidence.checks.base import Evidence, Result, Tools
from veritas.evidence.wording import baku_day, joined
from veritas.passport.models import ProofKind

MATCHES_PER_PHOTO = 10
"""The closest matches reported for one photo; one match already makes the point."""


def _distance(stored: str, given: str) -> str:
    """SQL for how many bits two 8-byte hashes differ in."""

    def bits(value: str) -> str:
        return f"('x' || encode({value}, 'hex'))::bit(64)"

    return f"bit_count({bits(stored)} # {bits(given)})"


_NEAR = text(
    f"""
    SELECT * FROM (
        SELECT ph.item_id,
               item.session_id,
               item.position,
               item.received_at,
               capture.project_id,
               capture.milestone_index,
               capture.attempt,
               capture.status AS session_status,
               (SELECT count(*) FROM evidence_items other
                 WHERE other.session_id = item.session_id
                   AND other.kind = 'photo'
                   AND other.position <= item.position) AS ordinal,
               {_distance("ph.phash", ":phash")} AS phash_distance,
               {_distance("ph.dhash", ":dhash")} AS dhash_distance,
               (item.session_id = :session_id
                OR (item.received_at, item.id) < (:received_at, :item_id)) AS earlier
          FROM photo_hashes ph
          JOIN evidence_items item ON item.id = ph.item_id
          JOIN capture_sessions capture ON capture.id = item.session_id
         WHERE ph.item_id <> :item_id
           AND (item.session_id <> :session_id
                OR (item.position IS NOT NULL AND item.position < :position))
    ) AS near
    WHERE phash_distance <= :close AND dhash_distance <= :close
    ORDER BY (phash_distance <= :clear AND dhash_distance <= :clear) DESC,
             earlier DESC,
             phash_distance + dhash_distance,
             received_at,
             item_id
    LIMIT :limit
    """
)


def check(session: Session, evidence: Evidence, tools: Tools) -> Result:
    clear_bits = tools.settings.photo_reuse_clear_bits
    close_bits = tools.settings.photo_reuse_close_bits
    clear: list[str] = []
    close: list[str] = []
    matches: list[dict[str, Any]] = []
    unchecked: list[str] = []
    stored = {item.position: item for item in evidence.items}
    photos = [
        (position, label)
        for position, (entry, label) in enumerate(
            zip(evidence.manifest.items, evidence.labels, strict=True)
        )
        if entry.kind == ProofKind.PHOTO
    ]
    for position, label in photos:
        item = stored.get(position)
        if item is None:
            clear.append(f"{label} is in the manifest but no upload is recorded for it")
            unchecked.append(label)
            continue
        hashes = session.scalars(select(PhotoHash).where(PhotoHash.item_id == item.id)).first()
        if hashes is None:
            clear.append(f"{label} has no perceptual hash on record, so it cannot be compared")
            unchecked.append(label)
            continue
        rows = session.execute(
            _NEAR,
            {
                "item_id": item.id,
                "session_id": item.session_id,
                "position": position,
                "received_at": item.received_at,
                "phash": hashes.phash,
                "dhash": hashes.dhash,
                "clear": clear_bits,
                "close": close_bits,
                "limit": MATCHES_PER_PHOTO,
            },
        ).all()
        for row in rows:
            same_bundle = row.session_id == evidence.capture.id
            is_clear = row.phash_distance <= clear_bits and row.dhash_distance <= clear_bits
            other = _other(evidence, row, same_bundle)
            bits = f"(pHash {row.phash_distance} and dHash {row.dhash_distance} bits apart of 64)"
            if not row.earlier:
                close.append(
                    f"{other[0].upper()}{other[1:]} is {'a copy' if is_clear else 'very like'} "
                    f"of {label} {bits}, stored after it: that bundle has to explain it"
                )
            elif is_clear:
                clear.append(f"{label} is the same picture as {other} {bits}")
            else:
                close.append(f"{label} looks very like {other} {bits}; compare them by eye")
            matches.append(
                {
                    "item": label,
                    "clear": is_clear,
                    "phash_distance": row.phash_distance,
                    "dhash_distance": row.dhash_distance,
                    "same_bundle": same_bundle,
                    "stored_earlier": bool(row.earlier),
                    "project_id": str(row.project_id),
                    "milestone": row.milestone_index,
                    "attempt": row.attempt,
                    "received_on": baku_day(row.received_at),
                }
            )

    details = {
        "clear_bits": clear_bits,
        "close_bits": close_bits,
        "photos": len(photos),
        "photos_on_record": session.scalar(select(func.count()).select_from(PhotoHash)),
        "matches": matches,
        "not_compared": unchecked,
    }
    if clear:
        return Result(5, CheckStatus.FAILED, joined(clear + close), details)
    if close:
        return Result(5, CheckStatus.ADVISORY, joined(close), details)
    return Result(5, CheckStatus.PASSED, details=details)


def _other(evidence: Evidence, row: Row[Any], same_bundle: bool) -> str:
    """Which photo it matches, in words: where it came from and when it arrived."""
    name = f"photo {row.ordinal}" if row.ordinal else "a photo"
    if same_bundle:
        return f"{name} of this bundle"
    if row.project_id != evidence.project.id:
        where = f"milestone {row.milestone_index} of project {row.project_id}"
    elif row.milestone_index != evidence.milestone.index:
        where = f"milestone {row.milestone_index} of this project"
    else:
        where = f"attempt {row.attempt} of this milestone"
    unsent = (
        "" if row.session_status == CaptureStatus.SUBMITTED else ", in a session never submitted"
    )
    return f"{name} from {where}, received on {baku_day(row.received_at)}{unsent}"
