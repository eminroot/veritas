"""Periodic jobs for decisions and money out.

The ones that depend on time use the chain's clock, because that is the clock the contracts
check: a vote closes, a deadline passes or a choice window ends when the chain says so.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session
from web3 import Web3

from veritas.decisions.payouts import execute_payouts, release_approved
from veritas.decisions.pledges import charge_pledges
from veritas.decisions.recovery import finish_rotations
from veritas.decisions.stops import apply_defaults, stop_missed_deadlines
from veritas.decisions.voting import close_due_ballots

if TYPE_CHECKING:
    from veritas.workers import Context, Schedule


def chain_now(w3: Web3) -> datetime:
    """The time of the latest block: the clock the contracts check."""
    return datetime.fromtimestamp(w3.eth.get_block("latest")["timestamp"], UTC)


def close_ballots(session: Session, context: Context) -> Any:
    return close_due_ballots(session, chain_now(context.chain.w3))


def release(session: Session, context: Context) -> Any:
    return release_approved(session, context.chain.contracts)


def payouts(session: Session, context: Context) -> Any:
    return execute_payouts(session, context.bank, context.chain.contracts)


def pledges(session: Session, context: Context) -> Any:
    return charge_pledges(session, context.psp)


def deadlines(session: Session, context: Context) -> Any:
    return stop_missed_deadlines(session, chain_now(context.chain.w3))


def defaults(session: Session, context: Context) -> Any:
    return apply_defaults(session, context.chain.contracts, chain_now(context.chain.w3))


def rotations(session: Session, context: Context) -> Any:
    return finish_rotations(session, context.chain.contracts, chain_now(context.chain.w3))


def checks(session: Session, context: Context) -> Any:
    from veritas.evidence.anchoring import resend_checks

    return resend_checks(session)


def schedules() -> list[Schedule]:
    from veritas.workers import Schedule

    return [
        Schedule("close_ballots", 60, close_ballots),
        Schedule("release_approved", 60, release),
        Schedule("execute_payouts", 60, payouts),
        Schedule("charge_pledges", 60, pledges),
        Schedule("finish_rotations", 600, rotations),
        Schedule("resend_checks", 600, checks),
        Schedule("stop_missed_deadlines", 3600, deadlines),
        Schedule("apply_defaults", 3600, defaults),
    ]
