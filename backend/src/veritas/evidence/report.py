"""The check report: every check result of one bundle, as canonical JSON.

Its SHA-256 goes on-chain with the pass flag, so the report cannot be rewritten after donors
vote on it, and the report itself is published next to the public copy so anyone can check
that hash. It is written to be safe to publish: files are named by kind and number ("photo
2"), places by their distance from the site, and nothing names the phone or its exact
position. The same results always give the same bytes; there is no timestamp in it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from veritas.core.canonical import canonical_json
from veritas.core.hashing import sha256, to_hex
from veritas.db.models.evidence import CheckReport, EvidenceCheck
from veritas.evidence.checks import Evidence, Result, passed

REPORT_FORMAT = "veritas.evidence.report/1"


def report_document(
    *,
    project_id: uuid.UUID,
    milestone: int,
    attempt: int,
    bundle_hash: bytes,
    passport_version: int,
    passport_sha256: bytes,
    results: Sequence[Result],
) -> dict[str, Any]:
    ordered = sorted(results, key=lambda result: result.number)
    return {
        "format": REPORT_FORMAT,
        "project_id": str(project_id),
        "milestone": milestone,
        "attempt": attempt,
        "bundle_hash": to_hex(bundle_hash),
        "passport": {"version": passport_version, "sha256": to_hex(passport_sha256)},
        "passed": passed(ordered),
        "checks": [
            {
                "number": result.number,
                "name": result.spec.name,
                "title": result.spec.title,
                "kind": str(result.spec.kind),
                "status": str(result.status),
                "reason": result.reason,
                "details": result.details,
            }
            for result in ordered
        ],
    }


def report_bytes(evidence: Evidence, results: Sequence[Result]) -> bytes:
    """The canonical bytes for a bundle's results: exactly what is hashed and published."""
    bundle = evidence.bundle
    version = evidence.passport_version
    assert version.sha256 is not None
    return canonical_json(
        report_document(
            project_id=bundle.project_id,
            milestone=bundle.milestone_index,
            attempt=bundle.attempt,
            bundle_hash=bundle.bundle_hash,
            passport_version=version.version,
            passport_sha256=version.sha256,
            results=results,
        )
    )


def record(session: Session, evidence: Evidence, results: Sequence[Result]) -> CheckReport:
    """Store each result and the report. Both are final once written."""
    for result in results:
        session.add(
            EvidenceCheck(
                bundle_id=evidence.bundle.id,
                number=result.number,
                name=result.spec.name,
                kind=result.spec.kind,
                status=result.status,
                reason=result.reason,
                details=result.details,
            )
        )
    data = report_bytes(evidence, results)
    report = CheckReport(
        bundle_id=evidence.bundle.id,
        canonical_bytes=data,
        sha256=sha256(data),
        passed=passed(results),
    )
    session.add(report)
    session.flush()
    return report
