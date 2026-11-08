"""Check 3: every file was captured while the session's challenge code was valid, before the
server received it, and inside the milestone's window.

The capture time is the phone's clock and the rest is ours, so comparisons between the two
allow `evidence_clock_skew_seconds` either way. Nothing can have been captured before its
challenge code existed, so a session that started after the window closed captured after
the window, whatever the phone says.

The escrow takes first evidence until the window's end plus the grace period, and a
resubmission after a rejection until the resubmission deadline (ARCHITECTURE.md 7.1 and
7.6). So a capture before the window opened fails; one after the window closed fails nothing
by itself: for the first attempt it is an advisory the officer and donors see (the work may
have been done late), and for a resubmission it is what a resubmission is.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from veritas.db.models.evidence import CheckStatus
from veritas.evidence.checks.base import Evidence, Result, Tools
from veritas.evidence.wording import baku_day, baku_time, duration, joined, utc


def check(session: Session, evidence: Evidence, tools: Tools) -> Result:
    skew = timedelta(seconds=tools.settings.evidence_clock_skew_seconds)
    capture, milestone = evidence.capture, evidence.milestone
    resubmission = evidence.bundle.attempt > 1
    received = {item.position: item.received_at for item in evidence.items}
    problems: list[str] = []
    late: list[str] = []
    timeline: list[dict[str, Any]] = []
    for position, (entry, label) in enumerate(
        zip(evidence.manifest.items, evidence.labels, strict=True)
    ):
        moment = entry.captured
        found: list[str] = []
        when = f"{label} was captured at {baku_time(moment)}"
        if moment < milestone.opens_at:
            found.append(
                f"{when}, before milestone {milestone.index}'s window opened on "
                f"{baku_day(milestone.window_opens)}"
            )
        if moment < capture.issued_at - skew:
            found.append(
                f"{when}, {duration((capture.issued_at - moment).total_seconds())} before the "
                f"challenge code was issued at {baku_time(capture.issued_at)}"
            )
        if moment > capture.expires_at + skew:
            found.append(
                f"{when}, {duration((moment - capture.expires_at).total_seconds())} after the "
                f"challenge code expired at {baku_time(capture.expires_at)}"
            )
        arrived = received.get(position)
        if arrived is not None and moment > arrived + skew:
            found.append(
                f"{label} says it was captured at {baku_time(moment)}, "
                f"{duration((moment - arrived).total_seconds())} after the server received it "
                f"at {baku_time(arrived)}: the phone's clock is wrong or the time was changed"
            )
        if arrived is not None and arrived > capture.upload_until:
            found.append(
                f"{label} arrived at {baku_time(arrived)}, after the session stopped taking "
                f"uploads at {baku_time(capture.upload_until)}"
            )
        # The earliest it can really have been captured: not before its code existed.
        after_window = max(moment, capture.issued_at) >= milestone.closes_at
        if after_window and not resubmission and not found:
            late.append(label)
        problems += found
        timeline.append(
            {
                "item": label,
                "captured_at": utc(moment),
                "received_at": None if arrived is None else utc(arrived),
                "on_time": not found,
                "after_window": after_window,
            }
        )

    details = {
        "window": {"opens_at": utc(milestone.opens_at), "closes_at": utc(milestone.closes_at)},
        "attempt": evidence.bundle.attempt,
        "code_issued_at": utc(capture.issued_at),
        "code_expired_at": utc(capture.expires_at),
        "clock_skew_seconds": tools.settings.evidence_clock_skew_seconds,
        "captures": timeline,
    }
    if problems:
        return Result(3, CheckStatus.FAILED, joined(problems), details)
    if late:
        return Result(
            3,
            CheckStatus.ADVISORY,
            f"{_listed(late)} captured after milestone {milestone.index}'s window closed at the "
            f"end of {baku_day(milestone.window_closes)}, during the grace period the escrow "
            "allows for evidence: the work may have been finished late",
            details,
        )
    return Result(3, CheckStatus.PASSED, details=details)


def _listed(labels: list[str]) -> str:
    if len(labels) == 1:
        return f"{labels[0].capitalize()} was"
    return f"{', '.join(labels[:-1]).capitalize()} and {labels[-1]} were"
