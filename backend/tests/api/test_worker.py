"""The worker process wires the relayer, the indexer, the evidence pipeline and every job
together."""

import pytest
from flowkit import deliver_webhooks, donate, live_example
from sqlalchemy import select

from chainkit import mine
from veritas.db.models.money import Donation
from veritas.workers import EVIDENCE_SECONDS_PER_TICK, Context, Worker, main


class CountingPipeline:
    """Stands in for the evidence pipeline, which tests/evidence covers on its own."""

    def __init__(self) -> None:
        self.runs = 0
        self.budgets: set[float | None] = set()

    def run_once(self, budget_seconds: float | None = None) -> int:
        self.runs += 1
        self.budgets.add(budget_seconds)
        return 0


class BrokenIndexer:
    """An RPC endpoint that times out on every call."""

    def __init__(self) -> None:
        self.calls = 0

    def run_once(self) -> int:
        self.calls += 1
        raise ConnectionError("the RPC endpoint timed out")


def test_ticks_take_a_donation_into_escrow(
    client,
    db,
    chain_app,
    chain,
    w3,
    accounts,
    sessions,
    mocks,
    login,
    settings,
    charity_admin,
    verified_charity,
    verified_contractor,
    officer,
):
    project_id, *_ = live_example(
        client, db, chain, w3, accounts, sessions, charity_admin, verified_charity
    )
    donate(client, login("+994 55 800 00 01"), project_id, accounts["donor1"].address, 9_000)
    deliver_webhooks(client, db, mocks["settings"])

    context = Context(
        settings=settings.model_copy(update={"relayer_min_priority_fee_gwei": 1}),
        chain=chain,
        psp=mocks["psp"],
        bank=mocks["bank"],
    )
    evidence = CountingPipeline()
    worker = Worker(
        sessions,
        context,
        {"relayer": accounts["relayer"], "admin": accounts["deployer"]},
        evidence=evidence,
    )
    names = [schedule.name for schedule in worker.jobs]
    assert names[:2] == ["build_batch", "refund_unbatched"]
    assert {"reconcile", "close_ballots", "release_approved", "execute_payouts"} <= set(names)

    for _ in range(12):
        worker.tick()
        mine(w3, 1)
    db.expire_all()
    assert db.scalars(select(Donation)).one().status == "in_escrow"
    assert evidence.runs == 12  # every tick also checks and publishes waiting evidence
    assert evidence.budgets == {EVIDENCE_SECONDS_PER_TICK}  # a few seconds, never longer
    # Jobs that ran recently wait for their interval before running again.
    assert worker.run_job("build_batch") is None

    # One part failing, the RPC endpoint timing out, say, ends nothing: the rest runs on.
    worker.indexer = BrokenIndexer()
    for _ in range(3):
        worker.tick()
    assert worker.indexer.calls == 3 and evidence.runs == 15


def test_the_worker_runs_everything_or_only_evidence():
    with pytest.raises(SystemExit, match="usage"):
        main(["relayer"])
