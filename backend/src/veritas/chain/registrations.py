"""Who may act on-chain: the charities and officers the hub knows.

The admin (a Safe in production, a configured key on Anvil and in the demo) registers a
charity's signing key once the charity is verified and has set one, and an officer when they
are created or reactivated. Suspending a charity, changing its key or deactivating an officer
takes the old key off the hub, so it can launch nothing new. A live escrow keeps the charity
key it was launched with all the same (Project.charity_signer): its evidence, withdrawal and
amendments are still signed with that key. Each change is an outbox row from the admin, in
the same transaction as the database change.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.chain.outbox import enqueue
from veritas.db.models import Charity, CharityStatus, Officer, OfficerStatus
from veritas.db.models.chain import ChainOutbox, Sender


def _set(session: Session, kind: str, function: str, address: str, on: bool) -> ChainOutbox:
    # The count makes each flip its own row: off, on and off again are three calls.
    count = session.scalar(
        select(func.count()).where(ChainOutbox.dedupe_key.like(f"{kind}:{address}:%"))
    )
    return enqueue(
        session,
        kind=kind,
        contract="VeritasHub",
        function=function,
        args=[address, on],
        dedupe_key=f"{kind}:{address}:{'on' if on else 'off'}:{(count or 0) + 1}",
        sender=Sender.ADMIN,
    )


def charity_key_changed(session: Session, charity: Charity, old_signer: str | None) -> None:
    """Call after a charity's status or signing key changed."""
    if old_signer and old_signer != charity.signer_address:
        _set(session, "register_charity", "setCharity", old_signer, False)
    if charity.signer_address:
        on = charity.status == CharityStatus.VERIFIED
        if on or old_signer == charity.signer_address:
            _set(session, "register_charity", "setCharity", charity.signer_address, on)


def officer_changed(session: Session, officer: Officer) -> None:
    _set(
        session,
        "register_officer",
        "setOfficer",
        officer.address,
        officer.status == OfficerStatus.ACTIVE,
    )


def latest_registration(session: Session, kind: str, address: str) -> ChainOutbox | None:
    """The newest registration call for an address, which a launch has to wait for."""
    return session.scalars(
        select(ChainOutbox)
        .where(ChainOutbox.kind == kind, ChainOutbox.dedupe_key.like(f"{kind}:{address}:%"))
        .order_by(ChainOutbox.id.desc())
        .limit(1)
    ).first()
