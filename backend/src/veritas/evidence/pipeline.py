"""The evidence worker: it checks every new bundle, builds its public copy, and puts the copy
on IPFS once the charity has signed it.

A bundle moves draft -> checked -> published here, one step per transaction, so a crash or
an unreachable IPFS node leaves it where it was and a later run picks it up again. After the
charity signs (through the API), the worker adds and pins the public copy (`pinned_at`); the
indexer marks the bundle anchored. Rows are taken with SKIP LOCKED, so several workers can
share the work.

A step that fails is retried with a growing pause, up to six hours, and after a few failures
a person is alerted; meanwhile other bundles go ahead, so no bundle can hold up the rest. A
failure of the IPFS node ends the round's IPFS work, since every other bundle would fail the
same way; a problem with one bundle's own files fails only that bundle.

Run it on its own, `python -m veritas.workers evidence`, or inside the full worker with a
time budget per tick so it never holds up the relayer for long (see veritas.workers).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from veritas.chain.alerts import raise_alert
from veritas.db.models.evidence import BundleStatus, EvidenceBundle
from veritas.db.session import db_now
from veritas.evidence.attestation import AttestationVerifier, attestation_verifier
from veritas.evidence.checks import Tools, load_evidence, run_checks
from veritas.evidence.ipfs import Ipfs, IpfsError, ipfs_for
from veritas.evidence.publish import pin_bundle, publish_bundle
from veritas.evidence.redaction import Detector, load_detector
from veritas.evidence.report import record
from veritas.settings import Settings
from veritas.storage import PrivateStorage

log = logging.getLogger(__name__)

BATCH = 20
FIRST_PAUSE = timedelta(seconds=30)
LONGEST_PAUSE = timedelta(hours=6)
ALERT_AFTER = 5
"""Failures of one step before a person is told."""

WAITING: dict[str, ColumnElement[bool]] = {
    "check": EvidenceBundle.status == BundleStatus.DRAFT,
    "publish": EvidenceBundle.status == BundleStatus.CHECKED,
    "pin": EvidenceBundle.charity_signature.is_not(None)
    & EvidenceBundle.status.in_((BundleStatus.PUBLISHED, BundleStatus.ANCHORED))
    & EvidenceBundle.pinned_at.is_(None),
}


class EvidencePipeline:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        storage: PrivateStorage,
        settings: Settings,
        ipfs: Ipfs,
        detector: Detector | None,
        attestation: AttestationVerifier | None = None,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.settings = settings
        self.ipfs = ipfs
        self.detector = detector
        self.tools = Tools(
            storage=storage,
            attestation=attestation or attestation_verifier(settings),
            settings=settings,
        )

    @classmethod
    def from_settings(
        cls, sessions: sessionmaker[Session], storage: PrivateStorage, settings: Settings
    ) -> EvidencePipeline:
        return cls(
            sessions,
            storage=storage,
            settings=settings,
            ipfs=ipfs_for(settings),
            detector=load_detector(settings.redaction_cascade_dir),
        )

    def run_forever(self, poll_seconds: float = 2.0) -> None:
        while True:
            try:
                busy = self.run_once()
            except Exception:  # the database is away, say: keep the process, try again
                log.exception("evidence round failed")
                busy = 0
            if not busy:
                time.sleep(poll_seconds)

    def run_once(self, budget_seconds: float | None = None) -> int:
        """Checks draft bundles, builds the public copy of checked ones and pins signed ones.
        Returns the steps done. With a budget, takes no new bundle once it is spent."""
        started = time.monotonic()
        steps: tuple[tuple[str, Callable[[uuid.UUID], bool]], ...] = (
            ("check", self.check),
            ("publish", self.publish),
            ("pin", self.pin),
        )
        done = 0
        for name, step in steps:
            for bundle_id in self._waiting(name):
                if budget_seconds is not None and time.monotonic() - started > budget_seconds:
                    return done
                try:
                    done += step(bundle_id)
                except IpfsError as exc:
                    # The node is down or broken: the rest of the round would fail the same way.
                    log.warning("evidence bundle %s: %s failed: %s", bundle_id, name, exc)
                    self._failed(bundle_id, name, exc)
                    break
                except Exception as exc:
                    log.exception("evidence bundle %s: %s failed", bundle_id, name)
                    self._failed(bundle_id, name, exc)
        return done

    def check(self, bundle_id: uuid.UUID) -> bool:
        with self.sessions() as session:
            bundle = self._take(session, bundle_id, "check")
            if bundle is None:
                return False
            evidence = load_evidence(session, bundle)
            results = run_checks(session, evidence, self.tools)
            report = record(session, evidence, results)
            bundle.status = BundleStatus.CHECKED
            _succeeded(bundle)
            session.commit()
            log.info("evidence bundle %s checked, passed=%s", bundle_id, report.passed)
            return True

    def publish(self, bundle_id: uuid.UUID) -> bool:
        with self.sessions() as session:
            bundle = self._take(session, bundle_id, "publish")
            if bundle is None:
                return False
            publish_bundle(session, bundle, storage=self.storage, detector=self.detector)
            bundle.status = BundleStatus.PUBLISHED
            _succeeded(bundle)
            session.commit()
            log.info("evidence bundle %s ready to sign as %s", bundle_id, bundle.public_cid)
            return True

    def pin(self, bundle_id: uuid.UUID) -> bool:
        with self.sessions() as session:
            bundle = self._take(session, bundle_id, "pin")
            if bundle is None:
                return False
            pin_bundle(session, bundle, storage=self.storage, ipfs=self.ipfs)
            _succeeded(bundle)
            session.commit()
            log.info("evidence bundle %s pinned as %s", bundle_id, bundle.public_cid)
            return True

    def _waiting(self, step: str) -> list[uuid.UUID]:
        """The bundles due for a step, those failing longest ago last. A failed one waits out
        its pause, so it cannot keep newer bundles from their turn."""
        with self.sessions() as session:
            return list(
                session.scalars(
                    select(EvidenceBundle.id)
                    .where(
                        WAITING[step],
                        or_(
                            EvidenceBundle.retry_at.is_(None), EvidenceBundle.retry_at <= func.now()
                        ),
                    )
                    .order_by(
                        func.coalesce(EvidenceBundle.retry_at, EvidenceBundle.created_at),
                        EvidenceBundle.id,
                    )
                    .limit(BATCH)
                )
            )

    def _failed(self, bundle_id: uuid.UUID, step: str, exc: Exception) -> None:
        """Remember the failure and when to try again; tell a person once it keeps failing."""
        try:
            with self.sessions() as session:
                bundle = session.get(EvidenceBundle, bundle_id, with_for_update=True)
                if bundle is None:
                    return
                now = db_now(session)
                bundle.tries += 1
                bundle.last_error = f"{step}: {type(exc).__name__}: {exc}"[:1000]
                # The exponent is capped first: 2**42 pauses would not fit a timedelta.
                pause = min(FIRST_PAUSE * 2 ** min(bundle.tries - 1, 16), LONGEST_PAUSE)
                bundle.retry_at = now + pause
                if bundle.tries == ALERT_AFTER:
                    raise_alert(
                        session,
                        kind="evidence_stuck",
                        message=f"Evidence bundle {bundle_id} failed its {step} step "
                        f"{bundle.tries} times; it is retried every few hours until a person "
                        f"looks at it. Last error: {bundle.last_error}",
                        details={"bundle_id": str(bundle_id), "step": step},
                        dedupe_key=f"evidence_stuck:{bundle_id}:{step}",
                    )
                session.commit()
        except Exception:
            log.exception("evidence bundle %s: could not record the failure", bundle_id)

    @staticmethod
    def _take(session: Session, bundle_id: uuid.UUID, step: str) -> EvidenceBundle | None:
        """The bundle, locked, if it is still due: another worker may have failed on it since
        this one listed it."""
        return session.scalars(
            select(EvidenceBundle)
            .where(
                EvidenceBundle.id == bundle_id,
                WAITING[step],
                or_(EvidenceBundle.retry_at.is_(None), EvidenceBundle.retry_at <= func.now()),
            )
            .with_for_update(skip_locked=True)
        ).first()


def _succeeded(bundle: EvidenceBundle) -> None:
    bundle.tries = 0
    bundle.last_error = None
    bundle.retry_at = None
