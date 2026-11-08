"""The indexer handlers for evidence.

The milestone mirror (status, attempt, bundle and report hashes) is kept by
veritas.chain.handlers. Handlers registered here only update the evidence tables: a bundle is
anchored once the chain has recorded its checks, and only if what the chain recorded is what
the charity signed here. Anything else raises an alert, because then the chain and this
database tell donors different stories.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain.alerts import raise_alert
from veritas.chain.indexer import Handlers
from veritas.db.models.chain import ChainEvent
from veritas.db.models.evidence import BundleStatus, CheckReport, EvidenceBundle
from veritas.db.session import db_now

ESCROW = "MilestoneEscrow"


def _bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("0x"))


def _signed_bundle(session: Session, event: ChainEvent) -> EvidenceBundle | None:
    if event.project_id is None:
        return None
    return session.scalars(
        select(EvidenceBundle)
        .where(
            EvidenceBundle.project_id == event.project_id,
            EvidenceBundle.milestone_index == event.args["milestone"],
            EvidenceBundle.attempt == event.args["attempt"],
            EvidenceBundle.charity_signature.is_not(None),
            EvidenceBundle.status != BundleStatus.VOID,
        )
        .with_for_update()
    ).first()


def _mismatch(session: Session, event: ChainEvent, what: str) -> None:
    raise_alert(
        session,
        kind="evidence_mismatch",
        severity="critical",
        message=f"{event.contract}.{event.event}: {what}",
        details={
            "tx_hash": "0x" + event.tx_hash.hex(),
            "log_index": event.log_index,
            "project_id": None if event.project_id is None else str(event.project_id),
            "milestone": event.args.get("milestone"),
            "attempt": event.args.get("attempt"),
        },
        dedupe_key=f"evidence_mismatch:{event.tx_hash.hex()}:{event.log_index}",
    )


def on_evidence_submitted(session: Session, event: ChainEvent) -> None:
    if event.project_id is None:
        return  # the indexer already raised an alert for an escrow it does not know
    bundle = _signed_bundle(session, event)
    if bundle is None:
        _mismatch(session, event, "evidence was anchored that no signed bundle here matches")
        return
    if (
        bundle.bundle_hash != _bytes(event.args["bundleHash"])
        or bundle.public_cid != (event.args["cid"])
    ):
        _mismatch(session, event, "the anchored bundle hash or CID is not what the charity signed")


def on_checks_recorded(session: Session, event: ChainEvent) -> None:
    if event.project_id is None:
        return
    bundle = _signed_bundle(session, event)
    if bundle is None:
        _mismatch(session, event, "checks were recorded for evidence no signed bundle here matches")
        return
    report = session.scalars(select(CheckReport).where(CheckReport.bundle_id == bundle.id)).first()
    if (
        report is None
        or report.sha256 != _bytes(event.args["reportHash"])
        or report.passed != event.args["passed"]
    ):
        _mismatch(session, event, "the recorded report hash or result is not this bundle's report")
        return
    if bundle.status != BundleStatus.ANCHORED:
        now = db_now(session)  # read first: the query would flush a half-made change
        bundle.status = BundleStatus.ANCHORED
        bundle.anchored_at = now
        bundle.anchored_tx = event.tx_hash


def register(handlers: Handlers) -> None:
    handlers.on(ESCROW, "EvidenceSubmitted")(on_evidence_submitted)
    handlers.on(ESCROW, "ChecksRecorded")(on_checks_recorded)
