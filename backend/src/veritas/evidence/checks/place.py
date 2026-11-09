"""Check 2: every photo and video was taken on the milestone's site.

A capture is on the site when its GPS fix lies inside one of the milestone's polygons, or no
farther from one than the fix's accuracy: PostGIS measures on the geography, in metres. A fix
less precise than `evidence_max_accuracy_m` cannot place anything, and a position the phone
reports as mocked counts for nothing. Invoices and documents can be photographed anywhere,
so only on-site kinds are placed. The report is public, so how far off the site a capture was
is given only roughly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.db.models import Milestone, Site
from veritas.db.models.evidence import CheckStatus
from veritas.evidence.checks.base import Evidence, Result, Tools
from veritas.evidence.intake import ON_SITE
from veritas.evidence.manifest import Location
from veritas.evidence.wording import joined, metres


def check(session: Session, evidence: Evidence, tools: Tools) -> Result:
    limit = tools.settings.evidence_max_accuracy_m
    problems: list[str] = []
    placed: list[dict[str, Any]] = []
    for entry, label in zip(evidence.manifest.items, evidence.labels, strict=True):
        if entry.kind not in ON_SITE:
            continue
        location = entry.location
        if location is None:
            problems.append(f"{label} has no GPS fix")
            placed.append({"item": label, "on_site": False})
            continue
        accuracy = location.accuracy_m
        row = {"item": label, "accuracy_m": round(accuracy, 1)}
        if location.mocked:
            problems.append(
                f"{label} was taken with a mocked location: the phone said a location app "
                "supplied the position"
            )
            placed.append({**row, "on_site": False, "mocked": True})
            continue
        if accuracy > limit:
            problems.append(
                f"{label}'s GPS fix is too imprecise to place it on the site: accuracy "
                f"{metres(accuracy)}, at most {metres(limit)} is accepted"
            )
            placed.append({**row, "on_site": False})
            continue
        distance, within = _distance(session, evidence.milestone, location)
        if distance is None:
            problems.append("the milestone has no site to check positions against")
            break
        if not within:
            distance, far = _coarse(distance)
            problems.append(
                f"{label} is {far} outside the site, more than its GPS accuracy "
                f"of {metres(accuracy)}"
            )
        placed.append({**row, "distance_m": round(distance, 1), "on_site": within})

    details = {"max_accuracy_m": limit, "captures": placed}
    if problems:
        return Result(2, CheckStatus.FAILED, joined(problems), details)
    return Result(2, CheckStatus.PASSED, details=details)


COARSE_FROM_M = 100
"""Closer than this, an off-site fix is the site's edge and a GPS slip, and is given exactly."""


def _coarse(metres_off: float) -> tuple[float, str]:
    """An off-site distance as the public report gives it, and in words. At the site's edge
    it is exact; farther off it is only 'less than 1 km' or the nearest whole kilometre, so
    the report and the site's public outline do not say where an off-site photo was taken, a
    home, say. The officer has the exact fix."""
    if metres_off < COARSE_FROM_M:
        return metres_off, metres(metres_off)
    if metres_off < 1_000:
        return 1_000.0, "less than 1 km"
    km = round(metres_off / 1_000)
    return float(km * 1_000), f"about {km} km"


def _distance(
    session: Session, milestone: Milestone, location: Location
) -> tuple[float | None, bool]:
    """Metres from the fix to the nearest site (0 inside one), and whether the fix is within
    its accuracy of a site."""
    point = func.geography(
        func.ST_SetSRID(func.ST_MakePoint(location.longitude, location.latitude), 4326)
    )
    distance, within = session.execute(
        select(
            func.min(func.ST_Distance(Site.geom, point)),
            func.bool_or(func.ST_DWithin(Site.geom, point, location.accuracy_m)),
        ).where(Site.milestone_id == milestone.id)
    ).one()
    return (None if distance is None else float(distance)), bool(within)
