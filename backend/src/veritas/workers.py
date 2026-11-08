"""Background work: the relayer, the indexer, the periodic jobs and the evidence pipeline.

    uv run python -m veritas.workers            # everything in one process, for development
    uv run python -m veritas.workers chain      # the relayer, the indexer and the jobs
    uv run python -m veritas.workers evidence   # only the evidence pipeline, no chain needed

In production run `chain` and `evidence` as two processes: checking and redacting photos can
take minutes, and the relayer must not wait for them, or a vote sent near the end of its
window could arrive too late. In the all-in-one process the pipeline takes no new bundle
after a few seconds of a tick, though one bundle's step can take longer. Evidence bundles
are taken with SKIP LOCKED, so several evidence processes can share the work. A failing part
(the RPC endpoint timing out, the database failing over) is logged and tried again on the next
tick; it never ends the process.

Each job runs in its own transaction, so one failing job never undoes another, and every job
is safe to run twice: each is idempotent through unique keys or the state it moves forward.
ARCHITECTURE.md names Procrastinate for jobs. A plain loop with PostgreSQL advisory locks
covers the demo's handful of periodic jobs; Procrastinate comes in when jobs need queues of
their own.
"""

from __future__ import annotations

import logging
import sys
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from veritas.chain.contracts import Deployment
from veritas.chain.handlers import build_handlers
from veritas.chain.indexer import Indexer, IndexerConfig
from veritas.chain.relayer import Relayer, RelayerConfig
from veritas.chain.runtime import Chain
from veritas.db.session import make_engine, make_session_factory
from veritas.evidence.pipeline import EvidencePipeline
from veritas.payments.batches import build_batch, refund_unbatched
from veritas.payments.clients import BankClient, PspClient
from veritas.payments.reconcile import reconcile
from veritas.settings import Settings, get_settings
from veritas.storage import LocalStorage

log = logging.getLogger("veritas.workers")

EVIDENCE_SECONDS_PER_TICK = 5.0
"""In the all-in-one worker, how long the evidence pipeline may take new bundles each tick."""


@dataclass
class Context:
    """What jobs need besides their session."""

    settings: Settings
    chain: Chain
    psp: PspClient
    bank: BankClient
    clock: Callable[[], float] = time.time

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.clock(), UTC)


Job = Callable[[Session, Context], Any]


@dataclass
class Schedule:
    name: str
    every_seconds: float
    job: Job
    last_run: float = field(default=-1e18)


def default_jobs() -> list[Schedule]:
    from veritas.decisions import jobs as decision_jobs

    return [
        Schedule("build_batch", 3600, lambda s, c: build_batch(s, c.bank)),
        Schedule("refund_unbatched", 600, lambda s, c: refund_unbatched(s, c.psp)),
        Schedule(
            "reconcile",
            3600,
            lambda s, c: reconcile(
                s, c.chain.contracts, c.bank, confirmations=c.settings.chain_confirmations
            ),
        ),
        *decision_jobs.schedules(),
    ]


class Worker:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        context: Context,
        signers: dict[str, LocalAccount],
        jobs: list[Schedule] | None = None,
        evidence: EvidencePipeline | None = None,
    ) -> None:
        self.sessions = sessions
        self.context = context
        self.evidence = evidence
        confirmations = context.settings.chain_confirmations
        self.relayer = Relayer(
            sessions,
            context.chain.contracts,
            signers,
            RelayerConfig(
                confirmations=confirmations,
                min_priority_fee=context.settings.relayer_min_priority_fee_gwei * 10**9,
            ),
            clock=context.clock,
        )
        self.indexer = Indexer(
            sessions,
            context.chain.contracts,
            build_handlers(),
            IndexerConfig(confirmations=confirmations),
        )
        self.jobs = default_jobs() if jobs is None else jobs

    def run_job(self, name: str) -> Any:
        schedule = next(s for s in self.jobs if s.name == name)
        return self._run(schedule)

    def _run(self, schedule: Schedule) -> Any:
        # One copy of each job at a time, across every worker process. crc32, not hash():
        # Python salts str hashes per process, and the key must be the same everywhere.
        key = zlib.crc32(schedule.name.encode()) & 0x7FFF_FFFF
        with self.sessions() as session:
            try:
                if not session.scalar(text("SELECT pg_try_advisory_xact_lock(42, :k)"), {"k": key}):
                    session.rollback()
                    return None
                result = schedule.job(session, self.context)
                session.commit()
            except Exception:
                session.rollback()
                log.exception("job %s failed", schedule.name)
                return None
        schedule.last_run = self.context.clock()
        return result

    def tick(self) -> None:
        for name, part in (
            ("relayer", self.relayer.run_once),
            ("indexer", self.indexer.run_once),
            ("evidence", self._evidence),
        ):
            try:
                part()
            except Exception:
                log.exception("%s failed; trying again next tick", name)
        now = self.context.clock()
        for schedule in self.jobs:
            if now - schedule.last_run >= schedule.every_seconds:
                self._run(schedule)

    def _evidence(self) -> None:
        if self.evidence is not None:
            self.evidence.run_once(budget_seconds=EVIDENCE_SECONDS_PER_TICK)

    def run_forever(self, pause: float = 2.0) -> None:
        with self.relayer.lock() as held:
            if not held:
                raise RuntimeError("another worker runs the relayer")
            while True:
                self.tick()
                time.sleep(pause)


def build_worker(settings: Settings | None = None, *, evidence: bool = True) -> Worker:
    """The worker for the chain. With `evidence`, it runs the evidence pipeline too."""
    settings = settings or get_settings()
    if not settings.chain_enabled or settings.relayer_key is None:
        raise SystemExit(
            "the worker needs VERITAS_CHAIN_RPC_URL, VERITAS_DEPLOYMENT_FILE and "
            "VERITAS_RELAYER_KEY"
        )
    chain = Chain.connect(settings.chain_rpc_url, Deployment.load(settings.deployment_file))
    signers = {"relayer": Account.from_key(settings.relayer_key.get_secret_value())}
    if settings.admin_key is not None:
        signers["admin"] = Account.from_key(settings.admin_key.get_secret_value())
    context = Context(
        settings=settings,
        chain=chain,
        psp=PspClient(
            httpx.Client(base_url=settings.psp_base_url, timeout=15),
            settings.psp_api_key.get_secret_value(),
        ),
        bank=BankClient(
            httpx.Client(base_url=settings.bank_base_url, timeout=15),
            settings.bank_api_key.get_secret_value(),
        ),
    )
    sessions = make_session_factory(make_engine(settings.database_url))
    pipeline = build_evidence_pipeline(settings, sessions) if evidence else None
    return Worker(sessions, context, signers, evidence=pipeline)


def build_evidence_pipeline(
    settings: Settings, sessions: sessionmaker[Session] | None = None
) -> EvidencePipeline:
    sessions = sessions or make_session_factory(make_engine(settings.database_url))
    return EvidencePipeline.from_settings(sessions, LocalStorage(settings.storage_dir), settings)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    role = sys.argv[1:] if argv is None else argv
    if role == ["evidence"]:
        build_evidence_pipeline(get_settings()).run_forever()
    elif role == ["chain"]:
        build_worker(evidence=False).run_forever()
    elif not role:
        build_worker().run_forever()
    else:
        raise SystemExit("usage: python -m veritas.workers [chain | evidence]")


if __name__ == "__main__":
    main()
