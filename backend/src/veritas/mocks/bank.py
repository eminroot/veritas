"""MockBank: a stand-in for the partner bank that holds the escrow account.

It keeps its own books and signs with its own key, and it checks what Veritas asks it to sign
instead of signing whatever arrives:

- a batch attestation covers exactly the card payments it received and has not attested
  before, and their sum must equal the batch's credits;
- a payout or refund is made only for an instruction that is pending on-chain with the same
  amount (and, for a payout, the same contractor);
- the daily balance is its own escrow balance, which moves only when it attests a batch or
  pays something out.

Received money waits in a pending sub-account until a batch attests it, and vAZN is minted at
that same moment, so the escrow balance and the vAZN supply move together.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from eth_utils import to_checksum_address
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.chain import eip712
from veritas.chain.contracts import Contracts
from veritas.chain.project import Credit, credits_hash
from veritas.core.canonical import canonical_json
from veritas.core.hashing import sha256
from veritas.mocks.models import (
    MockBankAttestation,
    MockBankBatch,
    MockBankPayment,
    MockBankReceipt,
)


class BankRefused(ValueError):
    """The bank will not sign or pay this."""


@dataclass(frozen=True)
class PaymentResult:
    status: str
    """"paid" or "failed"."""
    payment_ref: bytes
    """The bank's reference for a payment, or the hash of the reason it failed."""
    signature: bytes


class MockBank:
    def __init__(
        self,
        session: Session,
        *,
        key: bytes,
        domain: eip712.Domain,
        chain: Contracts | None = None,
        refund_card: Callable[[str, int, str], bool] | None = None,
        closed_accounts: Sequence[str] = (),
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.session = session
        self.key = key
        self.domain = domain
        self.chain = chain
        self.refund_card = refund_card
        """Asks the card provider to refund (payment id, amount, idempotency key)."""
        self.closed_accounts = set(closed_accounts)
        self.clock = clock

    def _sign(self, primary: str, message: dict[str, Any]) -> bytes:
        return eip712.sign(self.key, self.domain, primary, message)

    # ------------------------------------------------------------------ money in

    def receive_card_payment(self, payment_id: str, amount: int) -> None:
        if self.session.get(MockBankReceipt, payment_id) is None:
            self.session.add(MockBankReceipt(payment_id=payment_id, amount_qapik=amount))
            self.session.flush()

    def card_refunded(self, payment_id: str, amount: int) -> None:
        """A refund before any batch attested the payment: the money leaves pending.

        Refunds of attested money go through refund instructions on-chain instead, and the
        bank books those itself in execute_refund.
        """
        receipt = self.session.get(MockBankReceipt, payment_id, with_for_update=True)
        if receipt is not None and receipt.batch_id is None:
            receipt.amount_qapik -= amount
            self.session.flush()

    def attest_batch(
        self,
        *,
        batch_id: int,
        root: bytes,
        leaf_count: int,
        credits: Sequence[Credit],
        payments: Sequence[str],
    ) -> bytes:
        existing = self.session.get(MockBankBatch, batch_id)
        if existing is not None:
            if existing.root == root:
                return existing.signature
            if not self._never_anchored(batch_id):
                raise BankRefused(f"batch {batch_id} was already attested with another root")
            # Veritas's anchoring failed, so the chain never used this id: take it back.
            for receipt in self.session.scalars(
                select(MockBankReceipt).where(MockBankReceipt.batch_id == batch_id)
            ):
                receipt.batch_id = None
            self.session.delete(existing)
            self.session.flush()
        total = sum(sum(credit.amounts) for credit in credits)
        received = 0
        for payment_id in payments:
            receipt = self.session.get(MockBankReceipt, payment_id, with_for_update=True)
            if receipt is None:
                raise BankRefused(f"no card payment {payment_id} reached the escrow account")
            if receipt.batch_id is not None:
                raise BankRefused(f"payment {payment_id} is already in batch {receipt.batch_id}")
            receipt.batch_id = batch_id
            received += receipt.amount_qapik
        if received != total:
            raise BankRefused(f"the batch credits {total} qəpik but {received} arrived")
        signature = self._sign(
            "BatchAttestation",
            {
                "batchId": batch_id,
                "root": root,
                "leafCount": leaf_count,
                "total": total,
                "creditsHash": credits_hash(credits),
            },
        )
        self.session.add(
            MockBankBatch(batch_id=batch_id, root=root, total_qapik=total, signature=signature)
        )
        self.session.flush()
        return signature

    def _never_anchored(self, batch_id: int) -> bool:
        if self.chain is None:
            return False
        root = self.chain.ledger.functions.batches(batch_id).call()[0]
        return root == bytes(32)

    # ------------------------------------------------------------------ money out

    def _instruction(self, instruction_id: int) -> dict[str, Any] | None:
        if self.chain is None:
            return None
        values = self.chain.vault.functions.instruction(instruction_id).call()
        fields = (
            "escrow",
            "projectId",
            "isRefund",
            "milestone",
            "amount",
            "status",
            "holder",
            "contractorHash",
            "invoiceHash",
            "claimId",
        )
        return dict(zip(fields, values, strict=True))

    def _check_instruction(
        self, instruction_id: int, amount: int, refund: bool, contractor_hash: bytes | None
    ) -> None:
        on_chain = self._instruction(instruction_id)
        if on_chain is None:
            return  # no chain connection: the mock trusts the caller, a real bank never would
        if on_chain["status"] != 1:
            raise BankRefused(f"instruction {instruction_id} is not pending on-chain")
        if on_chain["isRefund"] != refund or on_chain["amount"] != amount:
            raise BankRefused(f"instruction {instruction_id} does not match the request")
        if contractor_hash is not None and on_chain["contractorHash"] != contractor_hash:
            raise BankRefused(f"instruction {instruction_id} names another contractor")

    def _settle(
        self,
        instruction_id: int,
        kind: str,
        amount: int,
        counterparty: str,
        failure: str | None,
    ) -> PaymentResult:
        if failure is None:
            reference = sha256(f"MOCKBANK-{kind.upper()}-{instruction_id:08d}".encode())
            signature = self._sign(
                "PayoutConfirmation",
                {"instructionId": instruction_id, "amount": amount, "paymentRef": reference},
            )
        else:
            reference = sha256(failure.encode())
            signature = self._sign(
                "PayoutFailure", {"instructionId": instruction_id, "reasonHash": reference}
            )
        self.session.add(
            MockBankPayment(
                instruction_id=instruction_id,
                kind=kind,
                amount_qapik=amount,
                status="failed" if failure else "paid",
                counterparty=counterparty,
                payment_ref=reference,
                reason=failure,
                signature=signature,
            )
        )
        self.session.flush()
        return PaymentResult("failed" if failure else "paid", reference, signature)

    def execute_payout(
        self, *, instruction_id: int, amount: int, contractor_hash: bytes, iban: str
    ) -> PaymentResult:
        """Pays the contractor for a released milestone and signs what happened."""
        done = self.session.get(MockBankPayment, instruction_id)
        if done is not None:
            return PaymentResult(done.status, done.payment_ref, done.signature)
        self._check_instruction(instruction_id, amount, False, contractor_hash)
        failure = "the receiving account is closed" if iban in self.closed_accounts else None
        return self._settle(instruction_id, "payout", amount, iban, failure)

    def execute_refund(
        self, *, instruction_id: int, amount: int, payments: Sequence[tuple[str, int]]
    ) -> PaymentResult:
        """Refunds a donor's cards for a refund instruction. `payments` names which card
        payments and how much of each, adding up to the instruction's amount."""
        done = self.session.get(MockBankPayment, instruction_id)
        if done is not None:
            return PaymentResult(done.status, done.payment_ref, done.signature)
        if sum(part for _, part in payments) != amount:
            raise BankRefused("the card refunds do not add up to the instruction")
        self._check_instruction(instruction_id, amount, True, None)
        failure = None
        for payment_id, part in payments:
            key = f"refund-{instruction_id}-{payment_id}"
            if self.refund_card is not None and not self.refund_card(payment_id, part, key):
                failure = "the card refund failed"
                break
        counterparty = ",".join(payment_id for payment_id, _ in payments)
        return self._settle(instruction_id, "refund", amount, counterparty, failure)

    # ------------------------------------------------------------------ the daily statement

    def escrow_balance(self) -> int:
        attested = self.session.scalar(
            select(func.coalesce(func.sum(MockBankBatch.total_qapik), 0))
        )
        paid = self.session.scalar(
            select(func.coalesce(func.sum(MockBankPayment.amount_qapik), 0)).where(
                MockBankPayment.status == "paid"
            )
        )
        return int(attested) - int(paid)

    def pending_balance(self) -> int:
        """Money that arrived and waits for a batch, outside the escrow balance."""
        return int(
            self.session.scalar(
                select(func.coalesce(func.sum(MockBankReceipt.amount_qapik), 0)).where(
                    MockBankReceipt.batch_id.is_(None)
                )
            )
        )

    def attest_balance(
        self, *, day: int, cutoff_block: int, cutoff_time: int, hub: str | None = None
    ) -> MockBankAttestation:
        existing = self.session.get(MockBankAttestation, day)
        if existing is not None:
            return existing
        balance = self.escrow_balance()
        statement = canonical_json(
            {
                "bank": "MockBank",
                "account": "veritas-escrow",
                "day": day,
                "cutoff_block": cutoff_block,
                "cutoff_time": cutoff_time,
                "escrow_balance_qapik": balance,
                "pending_qapik": self.pending_balance(),
                "hub": to_checksum_address(hub) if hub else None,
            }
        )
        signature = self._sign(
            "BalanceAttestation",
            {
                "day": day,
                "cutoffBlock": cutoff_block,
                "cutoffTime": cutoff_time,
                "balance": balance,
                "statementHash": sha256(statement),
            },
        )
        attestation = MockBankAttestation(
            day=day,
            cutoff_block=cutoff_block,
            cutoff_time=cutoff_time,
            balance_qapik=balance,
            statement=statement,
            signature=signature,
        )
        self.session.add(attestation)
        self.session.flush()
        return attestation
