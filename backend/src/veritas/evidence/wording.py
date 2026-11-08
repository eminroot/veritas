"""How evidence findings are worded for people: item names, Baku times, durations, metres.

Every failed check names the file it is about ("photo 2"), so the officer and the field
worker can find it. Files are numbered per kind in the order the manifest lists them. Times
are shown in Baku time, which is what the people reading them live in.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime

from veritas.passport.models import BAKU, ProofKind

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_NAMES = {
    ProofKind.PHOTO: ("photo", "photos"),
    ProofKind.VIDEO: ("video", "videos"),
    ProofKind.INVOICE: ("invoice", "invoices"),
    ProofKind.FISCAL_RECEIPT: ("fiscal receipt", "fiscal receipts"),
    ProofKind.DOCUMENT: ("document", "documents"),
}


def kind_name(kind: str, count: int = 1) -> str:
    singular, plural = _NAMES[ProofKind(kind)]
    return singular if count == 1 else plural


def counted(count: int, kind: str) -> str:
    """'1 invoice', '4 photos', 'no videos'."""
    if count == 0:
        return f"no {kind_name(kind, 2)}"
    return f"{count} {kind_name(kind, count)}"


def labels(kinds: Iterable[str]) -> list[str]:
    """Names for files in manifest order: photo 1, photo 2, invoice 1, photo 3, ..."""
    seen: dict[str, int] = {}
    names = []
    for kind in kinds:
        seen[kind] = seen.get(kind, 0) + 1
        names.append(f"{kind_name(kind)} {seen[kind]}")
    return names


def baku_time(moment: datetime) -> str:
    """'2027-03-10 10:04:30 Baku time'. A moment so late that Baku time would pass the year
    9999 is written in UTC instead: wording never fails on what a phone claimed."""
    try:
        return f"{moment.astimezone(BAKU):%Y-%m-%d %H:%M:%S} Baku time"
    except OverflowError:
        return moment.isoformat()  # as the phone wrote it: no conversion can overflow


def baku_day(moment: datetime | date) -> str:
    """'1 March 2027', the Baku date of a moment. Never depends on the server's locale."""
    try:
        day = moment.astimezone(BAKU).date() if isinstance(moment, datetime) else moment
    except OverflowError:
        day = moment.date() if isinstance(moment, datetime) else moment  # the phone's own day
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def utc(moment: datetime) -> str:
    """An RFC 3339 UTC time, '2027-03-10T06:04:30Z', as documents for machines write it."""
    try:
        return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except OverflowError:
        return moment.isoformat()


def duration(seconds: float) -> str:
    """'45 seconds', '6 minutes', '2 hours 5 minutes', '3 days'."""
    seconds = round(abs(seconds))
    if seconds < 60:
        return _plural(seconds, "second")
    minutes = round(seconds / 60)
    if minutes < 60:
        return _plural(minutes, "minute")
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return _plural(hours, "hour") + (f" {_plural(minutes, 'minute')}" if minutes else "")
    return _plural(round(hours / 24), "day")


def metres(value: float) -> str:
    """'0.4 m', '8 m', '143 m', and from a kilometre on '151.2 km'."""
    if value >= 1000:
        return f"{value / 1000:.1f} km"
    if value < 10 and round(value, 1) != round(value):
        return f"{value:.1f} m"
    return f"{round(value)} m"


def joined(problems: list[str], limit: int = 4) -> str:
    """Problems as one reason: the first few in full, then how many more the details hold."""
    shown = "; ".join(problems[:limit])
    more = len(problems) - limit
    if more > 0:
        shown += f"; and {more} more (see the details)"
    return shown[:1].upper() + shown[1:] + "."


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"
