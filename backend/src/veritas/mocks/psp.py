"""A stand-in card provider for development and the demo.

It behaves like the providers Veritas will use: payments with test card numbers, saved cards
for merchant-initiated charges (Pay-on-Proof), full and partial refunds, idempotency keys,
and webhooks signed with HMAC-SHA256 that it delivers in order. In bank mode the partner bank
is also the acquirer, so every successful payment lands in the bank's escrow account at once.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.mocks.models import MockCard, MockPayment, MockRefund, MockWebhook
from veritas.payments import webhooks

SUCCESS_CARD = "4242424242424242"
DECLINED_CARDS = {
    "4000000000000002": "card_declined",
    "4000000000009995": "insufficient_funds",
}


class PSPError(ValueError):
    """A request the provider refuses outright, like an unknown card number."""


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def payment_json(payment: MockPayment) -> dict[str, Any]:
    return {
        "id": payment.id,
        "amount": payment.amount_qapik,
        "currency": payment.currency,
        "status": payment.status,
        "failure_reason": payment.failure_reason,
        "card_last4": payment.card_last4,
        "card_token": payment.card_token,
        "merchant_initiated": payment.merchant_initiated,
        "refunded": payment.refunded_qapik,
        "metadata": payment.payment_metadata,
    }


def refund_json(refund: MockRefund) -> dict[str, Any]:
    return {
        "id": refund.id,
        "payment_id": refund.payment_id,
        "amount": refund.amount_qapik,
        "status": refund.status,
        "failure_reason": refund.failure_reason,
    }


class MockPSP:
    def __init__(
        self,
        session: Session,
        *,
        on_payment: Callable[[str, int], None] | None = None,
        on_refund: Callable[[str, int], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.session = session
        self.on_payment = on_payment
        self.on_refund = on_refund
        self.clock = clock

    # ------------------------------------------------------------------ cards and payments

    def save_card(self, customer_ref: str, card_number: str) -> MockCard:
        self._check_number(card_number)
        card = MockCard(token=_id("card"), customer_ref=customer_ref, last4=card_number[-4:])
        self.session.add(card)
        self.session.flush()
        return card

    def expire_card(self, token: str) -> None:
        card = self.session.get(MockCard, token)
        if card is None:
            raise PSPError("unknown card")
        card.expired = True

    def pay(
        self,
        *,
        amount: int,
        card_number: str,
        metadata: dict[str, Any],
        save_card: bool = False,
        customer_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> MockPayment:
        existing = self._by_key(idempotency_key)
        if existing is not None:
            return existing
        self._check_number(card_number)
        failure = DECLINED_CARDS.get(card_number)
        token = None
        if save_card and failure is None:
            token = self.save_card(customer_ref or "anonymous", card_number).token
        return self._record(
            amount=amount,
            last4=card_number[-4:],
            failure=failure,
            token=token,
            merchant_initiated=False,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

    def charge(
        self, *, card_token: str, amount: int, metadata: dict[str, Any], idempotency_key: str
    ) -> MockPayment:
        """A merchant-initiated charge on a saved card, as Pay-on-Proof makes."""
        existing = self._by_key(idempotency_key)
        if existing is not None:
            return existing
        card = self.session.get(MockCard, card_token)
        if card is None:
            raise PSPError("unknown card")
        return self._record(
            amount=amount,
            last4=card.last4,
            failure="expired_card" if card.expired else None,
            token=card.token,
            merchant_initiated=True,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

    def refund(self, *, payment_id: str, amount: int, idempotency_key: str) -> MockRefund:
        existing = self.session.scalars(
            select(MockRefund).where(MockRefund.idempotency_key == idempotency_key)
        ).first()
        if existing is not None:
            return existing
        payment = self.session.get(MockPayment, payment_id, with_for_update=True)
        if payment is None or payment.status != "succeeded":
            raise PSPError("only a succeeded payment can be refunded")
        if amount <= 0 or payment.refunded_qapik + amount > payment.amount_qapik:
            raise PSPError("the refund is more than what is left of the payment")
        card = self.session.get(MockCard, payment.card_token) if payment.card_token else None
        failure = "expired_card" if card is not None and card.expired else None
        refund = MockRefund(
            id=_id("re"),
            payment_id=payment_id,
            amount_qapik=amount,
            status="failed" if failure else "succeeded",
            failure_reason=failure,
            idempotency_key=idempotency_key,
        )
        self.session.add(refund)
        if failure is None:
            payment.refunded_qapik += amount
            if self.on_refund:
                self.on_refund(payment_id, amount)
        self.session.flush()
        self._webhook(f"refund.{refund.status}", refund_json(refund))
        return refund

    def get(self, payment_id: str) -> MockPayment | None:
        return self.session.get(MockPayment, payment_id)

    # ------------------------------------------------------------------ webhooks

    def pending_webhooks(self) -> list[MockWebhook]:
        return list(
            self.session.scalars(
                select(MockWebhook)
                .where(MockWebhook.delivered_at.is_(None))
                .order_by(MockWebhook.id)
            )
        )

    def signed(self, webhook: MockWebhook, secret: bytes) -> tuple[bytes, str]:
        """The body and the signature header, signed at delivery time."""
        return webhook.body, webhooks.sign(secret, webhook.body, int(self.clock()))

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _check_number(card_number: str) -> None:
        if card_number != SUCCESS_CARD and card_number not in DECLINED_CARDS:
            raise PSPError("use a test card number")

    def _by_key(self, key: str | None) -> MockPayment | None:
        if key is None:
            return None
        return self.session.scalars(
            select(MockPayment).where(MockPayment.idempotency_key == key)
        ).first()

    def _record(
        self,
        *,
        amount: int,
        last4: str,
        failure: str | None,
        token: str | None,
        merchant_initiated: bool,
        metadata: dict[str, Any],
        idempotency_key: str | None,
    ) -> MockPayment:
        if amount <= 0:
            raise PSPError("the amount must be positive")
        payment = MockPayment(
            id=_id("pay"),
            amount_qapik=amount,
            status="failed" if failure else "succeeded",
            failure_reason=failure,
            card_last4=last4,
            card_token=token,
            merchant_initiated=merchant_initiated,
            idempotency_key=idempotency_key,
            payment_metadata=metadata,
        )
        self.session.add(payment)
        self.session.flush()
        if failure is None and self.on_payment:
            self.on_payment(payment.id, amount)
        self._webhook(f"payment.{payment.status}", payment_json(payment))
        return payment

    def _webhook(self, event_type: str, data: dict[str, Any]) -> None:
        body = json.dumps(
            {"id": _id("evt"), "type": event_type, "created": int(self.clock()), "data": data},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        self.session.add(MockWebhook(event_type=event_type, body=body))
        self.session.flush()
