"""Check 11: the bundle holds everything the Passport's proof checklist asks for.

Counts go by kind of proof. When the checklist names one kind twice, say photos of the frame
and photos of the yard, the bundle needs both counts together: files are not labelled with the
line of the checklist they answer, so a lower total cannot cover both.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from veritas.db.models.evidence import CheckStatus
from veritas.evidence.checks.base import Evidence, Result, Tools
from veritas.evidence.wording import counted, joined


def check(session: Session, evidence: Evidence, tools: Tools) -> Result:
    proof = evidence.passport.milestones[evidence.bundle.milestone_index].proof
    needed: Counter[str] = Counter()
    descriptions: dict[str, list[str]] = {}
    for line in proof:
        needed[str(line.kind)] += line.min_count
        descriptions.setdefault(str(line.kind), []).append(line.description)
    present = Counter(str(entry.kind) for entry in evidence.manifest.items)

    problems = [
        f"the checklist asks for {counted(count, kind)} ({'; '.join(descriptions[kind])}) "
        f"and the bundle has {present[kind]}"
        for kind, count in needed.items()
        if present[kind] < count
    ]
    details = {
        "passport_version": evidence.passport_version.version,
        "required": [
            {"kind": str(line.kind), "min_count": line.min_count, "description": line.description}
            for line in proof
        ],
        "present": dict(sorted(present.items())),
    }
    if problems:
        return Result(11, CheckStatus.FAILED, joined(problems), details)
    return Result(11, CheckStatus.PASSED, details=details)
