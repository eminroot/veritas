"""The relayer: the only process that sends transactions.

It takes outbox rows in order, one sender at a time, with at most one transaction of each
sender in flight, so nonces never collide and a call never overtakes the one it depends on.
Every signed transaction is written to the database before it is broadcast: after a crash the
same bytes go out again instead of a second, different transaction. A transaction that sits
unmined gets its fees raised. A row is confirmed only once its block is final, and one that
reverts is marked failed with an alert for a person, never retried blindly.

The relayer pays the gas and carries other parties' signatures. On its own it can only make
Veritas's own claims; it cannot release money, vote or confirm a payout.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from eth_account.signers.local import LocalAccount
from hexbytes import HexBytes
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker
from web3 import Web3
from web3.exceptions import ContractLogicError, TransactionNotFound

from veritas.chain.alerts import raise_alert
from veritas.chain.codec import decode_args
from veritas.chain.contracts import Contracts
from veritas.db.models.chain import ChainOutbox, OutboxStatus

log = logging.getLogger(__name__)

LOCK_KEY = 0x5645_5249_5441_5301  # "VERITAS" and 1: one relayer at a time
IN_FLIGHT = (OutboxStatus.SENDING, OutboxStatus.SENT)


@dataclass(frozen=True)
class RelayerConfig:
    confirmations: int | None = None
    """None: final means the node's "finalized" block. A number: that many blocks deep."""
    bump_after_seconds: float = 60
    bump_percent: int = 20
    """Nodes replace a pending transaction only for at least 10% more on both fees."""
    min_priority_fee: int = 30 * 10**9
    """Polygon wants at least 25-30 gwei of tip. Anvil is fine with less."""
    max_fee_per_gas: int = 2_000 * 10**9
    gas_margin: float = 1.25


def final_block(w3: Web3, confirmations: int | None) -> int:
    if confirmations is None:
        return w3.eth.get_block("finalized")["number"]
    return max(w3.eth.block_number - confirmations, -1)


class Relayer:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        contracts: Contracts,
        signers: Mapping[str, LocalAccount],
        config: RelayerConfig | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.sessions = sessions
        self.contracts = contracts
        self.w3 = contracts.w3
        self.signers = dict(signers)
        self.config = config or RelayerConfig()
        self.clock = clock

    @contextmanager
    def lock(self) -> Iterator[bool]:
        """Holds the relayer lock on its own connection for as long as the block runs."""
        with self.sessions() as session:
            got = session.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})
            try:
                yield bool(got)
            finally:
                if got:
                    session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
                session.commit()

    def run_forever(self, poll_seconds: float = 2.0) -> None:
        with self.lock() as held:
            if not held:
                raise RuntimeError("another relayer holds the lock")
            while True:
                if not self.run_once():
                    time.sleep(poll_seconds)

    def run_once(self) -> bool:
        """One step for every sender. True if anything moved."""
        moved = False
        for sender in self.signers:
            try:
                moved |= self._step(sender)
            except Exception:
                log.exception("relayer step failed for %s", sender)
        return moved

    def drain(self, max_steps: int = 100) -> None:
        """Run until nothing moves. For tests and scripts, not production."""
        for _ in range(max_steps):
            if not self.run_once():
                return

    # ------------------------------------------------------------------ one step

    def _step(self, sender: str) -> bool:
        """Follows this sender's open transactions, then sends its next row once none of them
        is still waiting to be mined. A mined transaction only waits for finality, and the
        next one may go out meanwhile: nonce order keeps them in sequence, and a row from
        another sender that depends on one still waits for it to be final."""
        with self.sessions() as session:
            open_rows = session.scalars(
                select(ChainOutbox)
                .where(ChainOutbox.sender == sender, ChainOutbox.status.in_(IN_FLIGHT))
                .order_by(ChainOutbox.nonce)
                .with_for_update()
            ).all()
            moved = False
            for row in open_rows:
                moved |= self._follow(session, row)
            if any(row.status in IN_FLIGHT and row.mined_block is None for row in open_rows):
                return moved
            row = session.scalars(
                select(ChainOutbox)
                .where(ChainOutbox.sender == sender, ChainOutbox.status == OutboxStatus.PENDING)
                .order_by(ChainOutbox.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return moved
            if row.depends_on is not None:
                needed = session.get(ChainOutbox, row.depends_on)
                if needed is not None and needed.status in (
                    OutboxStatus.FAILED,
                    OutboxStatus.CANCELLED,
                ):
                    self._fail(session, row, f"it waits for outbox {needed.id}, which failed")
                    return True
                if needed is not None and needed.status != OutboxStatus.CONFIRMED:
                    return moved  # keeps this sender's order: nothing overtakes it
            return self._send(session, row) or moved

    def _call(self, row: ChainOutbox) -> Any:
        if row.address:
            contract = self.contracts.escrow(row.address)
        else:
            contract = self.contracts.get(row.contract)
        args = decode_args(row.contract, row.function, row.args)
        return contract.functions[row.function](*args)

    def _fees(self, floor: tuple[int, int] | None = None) -> tuple[int, int]:
        base = self.w3.eth.get_block("latest").get("baseFeePerGas", 0)
        try:
            suggested = self.w3.eth.max_priority_fee
        except Exception:
            suggested = 0
        priority = max(self.config.min_priority_fee, suggested)
        max_fee = 2 * base + priority
        if floor:
            bump = 100 + self.config.bump_percent
            priority = max(priority, floor[1] * bump // 100)
            max_fee = max(max_fee, floor[0] * bump // 100)
        max_fee = min(max_fee, self.config.max_fee_per_gas)
        return max_fee, min(priority, max_fee)

    def _next_nonce(self, session: Session, sender: str, address: str) -> int:
        chain = self.w3.eth.get_transaction_count(address, "pending")
        used = session.scalar(
            select(func.max(ChainOutbox.nonce)).where(
                ChainOutbox.sender == sender, ChainOutbox.nonce.is_not(None)
            )
        )
        return max(chain, (used + 1) if used is not None else 0)

    def _sign(self, row: ChainOutbox, account: LocalAccount, fees: tuple[int, int]) -> HexBytes:
        call = self._call(row)
        transaction = call.build_transaction(
            {
                "from": account.address,
                "nonce": row.nonce,
                "gas": row.gas_limit,
                "maxFeePerGas": fees[0],
                "maxPriorityFeePerGas": fees[1],
                "chainId": self.contracts.deployment.chain_id,
            }
        )
        signed = account.sign_transaction(transaction)
        row.max_fee_per_gas, row.max_priority_fee_per_gas = fees
        row.raw_tx = bytes(signed.raw_transaction)
        row.tx_hash = bytes(signed.hash)
        row.tx_hashes = [*row.tx_hashes, "0x" + bytes(signed.hash).hex()]
        row.attempts += 1
        return HexBytes(signed.raw_transaction)

    def _send(self, session: Session, row: ChainOutbox) -> bool:
        account = self.signers[row.sender]
        try:
            call = self._call(row)
            gas = call.estimate_gas({"from": account.address}, block_identifier="pending")
        except ContractLogicError as exc:
            self._fail(session, row, f"would revert: {exc.message or exc}")
            return True
        row.gas_limit = int(gas * self.config.gas_margin) + 25_000
        row.nonce = self._next_nonce(session, row.sender, account.address)
        raw = self._sign(row, account, self._fees())
        row.status = OutboxStatus.SENDING
        session.commit()  # the signed bytes are safe before they leave
        self._broadcast(session, row, raw)
        return True

    def _broadcast(self, session: Session, row: ChainOutbox, raw: HexBytes) -> None:
        try:
            self.w3.eth.send_raw_transaction(raw)
        except Exception as exc:
            message = str(exc).lower()
            if "already known" not in message and "known transaction" not in message:
                row.last_error = f"broadcast failed: {exc}"
                session.commit()
                log.warning("broadcast of outbox %s failed: %s", row.id, exc)
                return
        row.status = OutboxStatus.SENT
        row.sent_at = datetime.fromtimestamp(self.clock(), UTC)
        row.last_error = None
        session.commit()
        log.info("sent outbox %s %s.%s nonce %s", row.id, row.contract, row.function, row.nonce)

    def _receipt(self, row: ChainOutbox) -> Any | None:
        for tx_hash in reversed(row.tx_hashes):
            try:
                return self.w3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                continue
        return None

    def _follow(self, session: Session, row: ChainOutbox) -> bool:
        # Count first, receipt second: a transaction mined in between is then still found.
        used = self.w3.eth.get_transaction_count(self.signers[row.sender].address, "latest")
        receipt = self._receipt(row)
        if receipt is None:
            if row.mined_block is not None:
                row.mined_block = None  # dropped by a reorg: back to waiting
                session.commit()
                return True
            if used > row.nonce:
                # The nonce is spent, by none of our hashes: something else sent with this key.
                self._fail(session, row, "nonce used by an unknown transaction", "critical")
                return True
            if row.status == OutboxStatus.SENDING:
                self._broadcast(session, row, HexBytes(row.raw_tx))
                return True
            return self._maybe_bump(session, row)
        if receipt["status"] != 1:
            self._fail(session, row, f"reverted in block {receipt['blockNumber']}")
            return True
        if row.mined_block != receipt["blockNumber"]:
            row.mined_block = receipt["blockNumber"]
            row.tx_hash = bytes(receipt["transactionHash"])
            session.commit()
        if receipt["blockNumber"] <= final_block(self.w3, self.config.confirmations):
            row.status = OutboxStatus.CONFIRMED
            row.confirmed_at = datetime.fromtimestamp(self.clock(), UTC)
            session.commit()
            log.info("confirmed outbox %s in block %s", row.id, receipt["blockNumber"])
            return True
        return False

    def _maybe_bump(self, session: Session, row: ChainOutbox) -> bool:
        waited = self.clock() - (row.sent_at.timestamp() if row.sent_at else 0)
        if waited < self.config.bump_after_seconds:
            return False
        account = self.signers[row.sender]
        floor = (row.max_fee_per_gas or 0, row.max_priority_fee_per_gas or 0)
        fees = self._fees(floor)
        if fees[0] <= floor[0] and fees[1] <= floor[1]:
            raise_alert(
                session,
                kind="outbox_stuck",
                severity="warning",
                message=f"outbox {row.id} is stuck at the fee cap",
                details={"outbox_id": row.id, "tx_hashes": row.tx_hashes},
                dedupe_key=f"outbox_stuck:{row.id}",
            )
            session.commit()
            return False
        raw = self._sign(row, account, fees)
        row.status = OutboxStatus.SENDING
        session.commit()
        self._broadcast(session, row, raw)
        log.info("raised fees for outbox %s to %s", row.id, fees)
        return True

    def _fail(
        self, session: Session, row: ChainOutbox, reason: str, severity: str = "warning"
    ) -> None:
        row.status = OutboxStatus.FAILED
        row.last_error = reason
        raise_alert(
            session,
            kind="outbox_failed",
            severity=severity,
            message=f"{row.kind}: {row.contract}.{row.function} failed: {reason}",
            details={"outbox_id": row.id, "dedupe_key": row.dedupe_key},
            dedupe_key=f"outbox_failed:{row.id}",
        )
        session.commit()
        log.warning("outbox %s failed: %s", row.id, reason)
