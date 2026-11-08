"""The deterministic evidence checks (ARCHITECTURE.md section 9) and how their results add up.

Each check reads one bundle and gives a result: passed, failed, advisory or not run, and,
whenever it did not pass, a reason a person can act on: which file, how far outside the
fence, which earlier photo it matches. The checks read the signed manifest, not what the app
said at upload time, because the manifest is what the bundle hash commits to.

A bundle passes when every hard check that ran passed. Checks 4 and 6 to 10 need OCR, the
vision model and outside registries; they arrive in Phase 7 and are recorded as not run, so
the report says plainly what nobody has checked by machine yet.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from veritas.evidence.checks import checklist, integrity, place, reuse, timing
from veritas.evidence.checks.base import (
    CATALOGUE,
    LATER,
    NOT_YET,
    SPECS,
    Check,
    Evidence,
    Result,
    Spec,
    Tools,
    load_evidence,
    not_run,
    passed,
)

RUN: dict[int, Check] = {
    1: integrity.check,
    2: place.check,
    3: timing.check,
    5: reuse.check,
    11: checklist.check,
}


def run_checks(session: Session, evidence: Evidence, tools: Tools) -> list[Result]:
    """Every check in the catalogue, in order of number."""
    return [
        RUN[spec.number](session, evidence, tools) if spec.number in RUN else not_run(spec.number)
        for spec in CATALOGUE
    ]


__all__ = [
    "CATALOGUE",
    "LATER",
    "NOT_YET",
    "RUN",
    "SPECS",
    "Check",
    "Evidence",
    "Result",
    "Spec",
    "Tools",
    "load_evidence",
    "not_run",
    "passed",
    "run_checks",
]
