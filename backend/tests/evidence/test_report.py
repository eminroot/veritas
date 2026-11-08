"""The check report: canonical bytes, their hash, and the same bytes every time."""

from __future__ import annotations

import json
import random
import uuid

from sqlalchemy import select

from veritas.core.canonical import canonical_json
from veritas.core.hashing import sha256, to_hex
from veritas.db.models.evidence import CheckReport, CheckStatus, EvidenceBundle
from veritas.evidence.checks import Result, load_evidence, not_run, run_checks
from veritas.evidence.report import report_bytes, report_document
from veritas.services.cid import raw_cid
from veritas.services.passports import published_version

from .kit import proof_set

SAMPLE = [
    Result(1, CheckStatus.PASSED, details={"files": [{"item": "photo 1", "matches": True}]}),
    Result(
        2,
        CheckStatus.FAILED,
        "Photo 1 is 22 m outside the site, more than its GPS accuracy of 10 m.",
        {"captures": [{"item": "photo 1", "distance_m": 22.2, "on_site": False}]},
    ),
    Result(3, CheckStatus.PASSED),
    not_run(4),
    Result(5, CheckStatus.ADVISORY, "Photo 1 looks very like photo 2 of this bundle."),
    *(not_run(number) for number in (6, 7, 8, 9, 10)),
    Result(11, CheckStatus.PASSED),
]
PINNED = "0x507a051a0061a5f00bf7eb06b0470f9b834b3f3af078450276b816debbb994a0"
SAMPLE_ARGS = {
    "project_id": uuid.UUID("6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13"),
    "milestone": 0,
    "attempt": 1,
    "bundle_hash": bytes(range(32)),
    "passport_version": 1,
    "passport_sha256": bytes(32),
}


def test_the_report_bytes_never_change_for_the_same_results():
    shuffled = SAMPLE.copy()
    random.Random(4).shuffle(shuffled)
    first = canonical_json(report_document(**SAMPLE_ARGS, results=SAMPLE))
    again = canonical_json(report_document(**SAMPLE_ARGS, results=shuffled))
    assert first == again
    # Pinned: a change here changes every report hash from now on. Do it on purpose only.
    assert to_hex(sha256(first)) == PINNED


def test_the_report_says_failed_when_a_hard_check_failed_and_not_otherwise():
    document = report_document(**SAMPLE_ARGS, results=SAMPLE)
    assert document["passed"] is False
    assert [check["status"] for check in document["checks"]][:5] == [
        "passed",
        "failed",
        "passed",
        "not_run",
        "advisory",
    ]
    without_failure = [r for r in SAMPLE if r.number != 2] + [Result(2, CheckStatus.PASSED)]
    assert report_document(**SAMPLE_ARGS, results=without_failure)["passed"] is True


def test_a_stored_report_hashes_to_its_bytes_and_names_its_bundle(
    db, clock, make, pipeline, project
):
    bundle = make(proof_set(clock.now))
    pipeline.run_once()
    report = db.scalars(select(CheckReport)).one()
    assert report.sha256 == sha256(report.canonical_bytes)
    assert canonical_json(json.loads(report.canonical_bytes)) == report.canonical_bytes

    document = json.loads(report.canonical_bytes)
    passport = published_version(db, project)
    assert document["format"] == "veritas.evidence.report/1"
    assert document["bundle_hash"] == bundle["bundle_hash"]
    assert document["passport"] == {"version": 1, "sha256": to_hex(passport.sha256)}
    assert document["passed"] is True
    assert [check["number"] for check in document["checks"]] == list(range(1, 12))
    public = json.loads(db.scalars(select(EvidenceBundle.public_manifest)).one())
    assert public["report"]["cid"] == raw_cid(report.canonical_bytes)


def test_running_the_checks_again_gives_the_same_bytes(db, tools, clock, make):
    bundle = make(proof_set(clock.now))
    row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
    evidence = load_evidence(db, row)
    first = report_bytes(evidence, run_checks(db, evidence, tools))
    second = report_bytes(evidence, list(reversed(run_checks(db, evidence, tools))))
    assert first == second
